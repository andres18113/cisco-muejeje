"""Aplicación E8 con baseline, enforcement, read-back y cleanup separados."""

from __future__ import annotations

from collections.abc import Sequence
from time import monotonic
from typing import Protocol

from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.deployment import (
    DeploymentIdentityError,
    DeploymentManifest,
    resolve_manifest_targets,
)
from ...domain.enterprise.models.execution import (
    CompensationStatus,
    MutationDisposition,
    journal_from_action_results,
    satisfies_apply_dependency,
)
from ...domain.enterprise.models.evidence import (
    EvidenceRecord,
    evidence_from_legacy_result,
)
from ...domain.enterprise.models.security_plan import (
    ConfigureEndpointPortSecurity,
    SecurityAction,
    SecurityCapabilityProfile,
    SecurityCapabilityStatus,
    SecurityPlan,
    SecurityProbeKind,
    SecurityVerificationExpectation,
    SecurityVerificationKind,
    security_verification_capability,
)
from ...domain.enterprise.models.security_runtime import (
    RuntimeSecurityVerification,
    SecurityApplicationResult,
    SecurityVerificationResult,
    SecurityVerificationStage,
)
from ...domain.enterprise.models.verification import (
    PrerequisiteKind,
    VerificationDependencyError,
    VerificationPrerequisite,
    order_verification_expectations,
    prerequisites_satisfied,
)
from ...domain.enterprise.services.configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)


class SecurityRuntime(Protocol):
    def inventory(self) -> list[RuntimeConfigurationTarget]: ...

    def apply_actions(
        self, actions: Sequence[SecurityAction],
    ) -> list[RuntimeActionMutation]: ...

    def observe(
        self, expectations: Sequence[SecurityVerificationExpectation],
    ) -> list[RuntimeSecurityVerification]: ...

    def verify_behavior(
        self,
        expectations: Sequence[SecurityVerificationExpectation],
        stage: SecurityVerificationStage,
    ) -> list[RuntimeSecurityVerification]: ...

    def cleanup_actions(
        self, actions: Sequence[SecurityAction],
    ) -> list[RuntimeActionMutation]: ...


class SecurityApplicator:
    """Ejecuta un SecurityPlan; nunca recompila E4-E7 ni controla UI de voz."""

    def __init__(self, runtime: SecurityRuntime) -> None:
        self._runtime = runtime

    def apply(
        self,
        plan: SecurityPlan,
        *,
        actual_source_topology_hash: str,
        actual_source_configuration_hash: str,
        foundational_statuses: dict[str, ActionExecutionStatus],
        actual_source_service_hash: str = "",
        actual_source_voice_hash: str = "",
        capabilities: dict[str, SecurityCapabilityProfile] | None = None,
        runtime_context: ConfigurationRuntimeContext | None = None,
        cleanup_control: bool = False,
        deployment_manifest: DeploymentManifest | None = None,
    ) -> SecurityApplicationResult:
        started = monotonic()
        context = runtime_context or ConfigurationRuntimeContext()
        deployment_id = deployment_manifest.deployment_id if deployment_manifest else ""
        mismatch = self._source_mismatch(
            plan,
            actual_source_topology_hash,
            actual_source_configuration_hash,
            actual_source_service_hash,
            actual_source_voice_hash,
        )
        if mismatch:
            return self._failure(
                plan,
                ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH,
                mismatch,
                context,
                started,
                deployment_id=deployment_id,
            )
        if (
            deployment_manifest is not None
            and deployment_manifest.physical_topology_hash != plan.source_topology_hash
        ):
            return self._failure(
                plan,
                ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
                "DeploymentManifest physical topology hash does not match SecurityPlan.",
                context,
                started,
                deployment_id=deployment_id,
            )
        try:
            ordered = order_dependency_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                str(exc), context, started, deployment_id=deployment_id,
            )
        if [item.id for item in ordered] != [item.id for item in plan.actions]:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "SecurityPlan actions are not in deterministic dependency order.",
                context, started, deployment_id=deployment_id,
            )
        try:
            verification_plan = self._normalized_verification_plan(plan)
        except VerificationDependencyError as exc:
            return self._failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                str(exc),
                context,
                started,
                deployment_id=deployment_id,
            )
        missing_foundations = sorted(
            item.source_id for item in plan.foundational_requirements
            if foundational_statuses.get(item.source_id) is not ActionExecutionStatus.VERIFIED
        )
        if missing_foundations:
            return self._failure(
                plan,
                ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                "Security foundations are not VERIFIED: " + ", ".join(missing_foundations),
                context,
                started,
                deployment_id=deployment_id,
            )
        try:
            inventory_items = self._runtime.inventory()
        except Exception as exc:
            return self._failure(
                plan, ConfigurationFailureCode.SESSION_FAILED,
                f"Security runtime inventory failed: {exc}", context, started,
                deployment_id=deployment_id,
            )
        runtime_plan = verification_plan
        if deployment_manifest is not None:
            try:
                semantic_targets = resolve_manifest_targets(
                    deployment_manifest,
                    physical_topology_hash=plan.source_topology_hash,
                    semantic_device_ids=self._semantic_device_ids(plan),
                    inventory=inventory_items,
                )
                runtime_plan = self._runtime_plan(
                    verification_plan,
                    {
                        identifier: target.device_name
                        for identifier, target in semantic_targets.items()
                    },
                )
            except DeploymentIdentityError as exc:
                return self._failure(
                    plan,
                    ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
                    str(exc),
                    context,
                    started,
                    deployment_id=deployment_id,
                )
        inventory = {item.device_name: item for item in inventory_items}
        target_errors = self._validate_targets(runtime_plan, inventory)
        if target_errors:
            return self._failure(
                plan, ConfigurationFailureCode.TARGET_NOT_FOUND,
                " ".join(target_errors), context, started,
                deployment_id=deployment_id,
            )

        verification: dict[str, SecurityVerificationResult] = {
            item.id: SecurityVerificationResult(
                expectation_id=item.id,
                action_id=item.action_id,
                policy_id=item.policy_id,
            )
            for item in runtime_plan.verification_expectations
        }
        baseline = [
            item for item in runtime_plan.verification_expectations
            if item.kind is SecurityVerificationKind.TRAFFIC_POLICY
            and item.baseline_required
        ]
        capability_profiles = capabilities or {}
        runtime_evidence: list[RuntimeSecurityVerification] = []
        if baseline:
            observed = self._run_verification_stage(
                runtime_plan,
                baseline,
                capability_profiles,
                SecurityVerificationStage.BASELINE,
                action_statuses={},
                verification_statuses={},
                resource_statuses=foundational_statuses,
                ignore_action_prerequisites=True,
            )
            runtime_evidence.extend(observed)
            self._merge_verification(verification, observed)
            if any(item.status is not ActionExecutionStatus.VERIFIED for item in observed):
                return self._failure(
                    plan,
                    ConfigurationFailureCode.SECURITY_BASELINE_FAILED,
                    "A deny control had no verified working baseline; no policy was mutated.",
                    context,
                    started,
                    verification_results=list(verification.values()),
                    deployment_id=deployment_id,
                    evidence_records=self._evidence_records(
                        runtime_plan, runtime_evidence, context,
                    ),
                )

        action_results = self._apply_actions(runtime_plan, capability_profiles)
        action_statuses = {
            item.action_id: item.status for item in action_results
        }
        applied_ids = {
            item.action_id for item in action_results
            if satisfies_apply_dependency(item.status)
        }
        direct = [
            item for item in runtime_plan.verification_expectations
            if item.probe_kind is SecurityProbeKind.DIRECT_READBACK
        ]
        verification_statuses: dict[str, ActionExecutionStatus] = {}
        if direct:
            observed = self._run_verification_stage(
                runtime_plan,
                direct,
                capability_profiles,
                SecurityVerificationStage.DIRECT_STATE,
                action_statuses=action_statuses,
                verification_statuses=verification_statuses,
                resource_statuses=foundational_statuses,
            )
            runtime_evidence.extend(observed)
            self._merge_verification(verification, observed)
            verification_statuses.update({
                item.expectation_id: item.status for item in observed
            })
        behavior = [
            item for item in runtime_plan.verification_expectations
            if item.probe_kind is not SecurityProbeKind.DIRECT_READBACK
        ]
        if behavior:
            observed = self._run_verification_stage(
                runtime_plan,
                behavior,
                capability_profiles,
                SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
                action_statuses=action_statuses,
                verification_statuses=verification_statuses,
                resource_statuses=foundational_statuses,
            )
            runtime_evidence.extend(observed)
            self._merge_verification(verification, observed)
            verification_statuses.update({
                item.expectation_id: item.status for item in observed
            })

        cleanup_results: list[ActionApplicationResult] = []
        if cleanup_control:
            cleanup_results = self._cleanup(runtime_plan, action_results)
            recovery = [item for item in behavior if item.cleanup_recovery_required]
            if recovery and all(
                satisfies_apply_dependency(item.status) for item in cleanup_results
            ):
                observed = self._run_verification_stage(
                    runtime_plan,
                    recovery,
                    capability_profiles,
                    SecurityVerificationStage.CLEANUP_RECOVERY,
                    action_statuses=action_statuses,
                    verification_statuses=verification_statuses,
                    resource_statuses=foundational_statuses,
                )
                runtime_evidence.extend(observed)
                self._merge_verification(verification, observed)

        verification_results = [
            verification[item.id] for item in plan.verification_expectations
        ]
        status, failure_code = self._overall(
            action_results, verification_results, cleanup_results, cleanup_control,
        )
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=action_results,
        )
        mutated = any(
            satisfies_apply_dependency(item.status) for item in action_results
        )
        if cleanup_control and mutated:
            cleanup_applied = bool(cleanup_results) and all(
                satisfies_apply_dependency(item.status) for item in cleanup_results
            )
            recovery_results = [
                verification[item.id]
                for item in runtime_plan.verification_expectations
                if item.cleanup_recovery_required and item.action_id in applied_ids
            ]
            recovery_known = not recovery_results or all(
                item.cleanup_status is ActionExecutionStatus.VERIFIED
                for item in recovery_results
            )
            if cleanup_applied and recovery_known:
                journal.mark_cleanup(CompensationStatus.SUCCEEDED)
            elif cleanup_applied:
                journal.mark_cleanup(CompensationStatus.UNKNOWN)
            elif any(
                item.disposition is MutationDisposition.UNKNOWN
                for item in cleanup_results
            ):
                journal.mark_cleanup(CompensationStatus.UNKNOWN)
            else:
                journal.mark_cleanup(CompensationStatus.FAILED)
        evidence_records = self._evidence_records(
            runtime_plan, runtime_evidence, context,
        )
        return SecurityApplicationResult(
            security_plan_id=plan.id,
            security_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            source_service_hash=plan.source_service_hash,
            source_voice_hash=plan.source_voice_hash,
            runtime_context=context,
            status=status,
            failure_code=failure_code,
            action_results=action_results,
            verification_results=verification_results,
            cleanup_results=cleanup_results,
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            evidence_records=evidence_records,
            duration_ms=int((monotonic() - started) * 1000),
        )

    @staticmethod
    def _source_mismatch(plan, topology_hash, configuration_hash, service_hash, voice_hash):
        if topology_hash != plan.source_topology_hash:
            return "SecurityPlan source hash does not match deployed E4."
        if configuration_hash != plan.source_configuration_hash:
            return "SecurityPlan source hash does not match applied E5."
        if plan.source_service_hash and service_hash != plan.source_service_hash:
            return "SecurityPlan source hash does not match applied E6."
        if plan.source_voice_hash and voice_hash != plan.source_voice_hash:
            return "SecurityPlan source hash does not match applied E7."
        return ""

    @staticmethod
    def _normalized_verification_plan(plan: SecurityPlan) -> SecurityPlan:
        verification_ids = {item.id for item in plan.verification_expectations}
        action_ids = {item.id for item in plan.actions}
        normalized = []
        for item in plan.verification_expectations:
            if item.verification_prerequisites:
                prerequisites = [
                    prerequisite.model_copy(update={
                        "kind": PrerequisiteKind.VERIFICATION_VERIFIED,
                    })
                    if (
                        prerequisite.kind is PrerequisiteKind.ACTION_APPLIED
                        and prerequisite.reference_id in verification_ids
                        and prerequisite.reference_id not in action_ids
                    )
                    else prerequisite
                    for prerequisite in item.verification_prerequisites
                ]
                normalized.append(item.model_copy(update={
                    "verification_prerequisites": prerequisites,
                }))
                continue
            references = [item.action_id, *item.depends_on]
            normalized.append(item.model_copy(update={
                "verification_prerequisites": [
                    VerificationPrerequisite(
                        kind=(
                            PrerequisiteKind.VERIFICATION_VERIFIED
                            if identifier in verification_ids
                            else PrerequisiteKind.ACTION_APPLIED
                        ),
                        reference_id=identifier,
                    )
                    for identifier in sorted(set(filter(None, references)))
                ],
            }))
        ordered = order_verification_expectations(normalized)
        return plan.model_copy(update={"verification_expectations": list(ordered)})

    @staticmethod
    def _semantic_device_ids(plan: SecurityPlan) -> list[str]:
        identifiers = {item.device_id for item in plan.actions if item.device_id}
        for expectation in plan.verification_expectations:
            if expectation.source_device_id:
                identifiers.add(expectation.source_device_id)
            if expectation.destination_device_id:
                identifiers.add(expectation.destination_device_id)
        return sorted(identifiers)

    @staticmethod
    def _runtime_plan(
        plan: SecurityPlan,
        deployed_names: dict[str, str],
    ) -> SecurityPlan:
        def resolve(identifier: str, planned_name: str, label: str) -> str:
            if not identifier:
                if planned_name:
                    raise DeploymentIdentityError(
                        f"{label} has a planned runtime name but no semantic device ID."
                    )
                return ""
            try:
                return deployed_names[identifier]
            except KeyError as exc:
                raise DeploymentIdentityError(
                    f"DeploymentManifest has no resolved target for {identifier!r}."
                ) from exc

        actions = [
            item.model_copy(update={
                "device_name": resolve(
                    item.device_id, item.device_name, f"Security action {item.id}",
                ),
            })
            for item in plan.actions
        ]
        expectations = []
        for item in plan.verification_expectations:
            updates: dict[str, str] = {}
            if item.source_device_id or item.source_device_name:
                updates["source_device_name"] = resolve(
                    item.source_device_id,
                    item.source_device_name,
                    f"Security expectation {item.id} source",
                )
            if item.destination_device_id or item.destination_device_name:
                updates["destination_device_name"] = resolve(
                    item.destination_device_id,
                    item.destination_device_name,
                    f"Security expectation {item.id} destination",
                )
            expectations.append(item.model_copy(update=updates))
        return plan.model_copy(update={
            "actions": actions,
            "verification_expectations": expectations,
        })

    @staticmethod
    def _validate_targets(
        plan: SecurityPlan,
        inventory: dict[str, RuntimeConfigurationTarget],
    ) -> list[str]:
        errors: list[str] = []
        for action in plan.actions:
            target = inventory.get(action.device_name)
            if target is None:
                errors.append(f"Target {action.device_name} was not found.")
                continue
            if target.model.casefold() != action.model.casefold():
                errors.append(
                    f"Target {action.device_name} model {target.model} does not match "
                    f"{action.model}."
                )
            if isinstance(action, ConfigureEndpointPortSecurity) and target.interfaces:
                if action.interface.casefold() not in {
                    item.casefold() for item in target.interfaces
                }:
                    errors.append(
                        f"Target {action.device_name} interface {action.interface} was not found."
                    )
        return sorted(set(errors))

    def _apply_actions(
        self,
        plan: SecurityPlan,
        capabilities: dict[str, SecurityCapabilityProfile],
    ) -> list[ActionApplicationResult]:
        results: dict[str, ActionApplicationResult] = {}
        for action in plan.actions:
            profile = capabilities.get(action.model)
            support = (
                profile.status(action.required_capability)
                if profile else SecurityCapabilityStatus.UNKNOWN
            )
            if support in {
                SecurityCapabilityStatus.SUPPORTED,
                SecurityCapabilityStatus.PARTIAL,
            }:
                continue
            results[action.id] = ActionApplicationResult(
                action_id=action.id,
                status=ActionExecutionStatus.SKIPPED,
                failure_code=(
                    ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                    if support is SecurityCapabilityStatus.UNSUPPORTED
                    else ConfigurationFailureCode.CAPABILITY_UNKNOWN
                ),
                message=(
                    f"{action.model}:{action.required_capability.value} is "
                    f"{support.value}."
                ),
                operation=action.operation,
                disposition=MutationDisposition.SKIPPED,
            )

        for phase in sorted({item.phase for item in plan.actions}):
            pending = [
                item for item in plan.actions
                if item.phase == phase and item.id not in results
            ]
            while pending:
                ready = [
                    action for action in pending
                    if all(
                        dependency in results
                        and satisfies_apply_dependency(results[dependency].status)
                        for dependency in action.depends_on
                    )
                ]
                if not ready:
                    for action in pending:
                        blocked = [
                            dependency for dependency in action.depends_on
                            if dependency not in results
                            or not satisfies_apply_dependency(results[dependency].status)
                        ]
                        results[action.id] = ActionApplicationResult(
                            action_id=action.id,
                            status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                            failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                            message="Blocked by: " + ", ".join(sorted(blocked)),
                            operation=action.operation,
                            disposition=MutationDisposition.BLOCKED,
                        )
                    break
                try:
                    mutations = {
                        item.action_id: item for item in self._runtime.apply_actions(ready)
                    }
                except Exception as exc:
                    mutations = {
                        item.id: RuntimeActionMutation(
                            action_id=item.id,
                            applied=False,
                            failure_code=ConfigurationFailureCode.SESSION_FAILED,
                            message=str(exc),
                        )
                        for item in ready
                    }
                for action in ready:
                    mutation = mutations.get(action.id)
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=(
                            self._mutation_status(mutation) if mutation
                            else ActionExecutionStatus.FAILED
                        ),
                        failure_code=(
                            ConfigurationFailureCode.NONE
                            if mutation and mutation.applied
                            else mutation.failure_code if mutation
                            else ConfigurationFailureCode.SECURITY_APPLICATION_FAILED
                        ),
                        message=(
                            mutation.message if mutation
                            else "Runtime returned no mutation."
                        ),
                        batch_id=mutation.batch_id if mutation else "",
                        operation=action.operation,
                        disposition=(
                            mutation.disposition
                            if mutation else MutationDisposition.UNKNOWN
                        ),
                    )
                    pending.remove(action)
        return [results[item.id] for item in plan.actions]

    @staticmethod
    def _mutation_status(mutation: RuntimeActionMutation) -> ActionExecutionStatus:
        if not mutation.applied:
            return ActionExecutionStatus.FAILED
        if mutation.disposition is MutationDisposition.NO_OP:
            return ActionExecutionStatus.NO_OP
        if mutation.disposition is MutationDisposition.REASSERTED:
            return ActionExecutionStatus.REASSERTED
        return ActionExecutionStatus.APPLIED

    def _run_verification_stage(
        self,
        plan: SecurityPlan,
        expectations: Sequence[SecurityVerificationExpectation],
        capabilities: dict[str, SecurityCapabilityProfile],
        stage: SecurityVerificationStage,
        *,
        action_statuses: dict[str, ActionExecutionStatus],
        verification_statuses: dict[str, ActionExecutionStatus],
        resource_statuses: dict[str, ActionExecutionStatus],
        ignore_action_prerequisites: bool = False,
    ) -> list[RuntimeSecurityVerification]:
        current_statuses = dict(verification_statuses)
        observed: list[RuntimeSecurityVerification] = []
        for expectation in expectations:
            prerequisites = list(expectation.verification_prerequisites)
            if ignore_action_prerequisites:
                # A deny baseline is intentionally measured before its security
                # action. Resource and prior-verification prerequisites still apply.
                prerequisites = [
                    item for item in prerequisites
                    if item.kind not in {
                        PrerequisiteKind.ACTION_APPLIED,
                        PrerequisiteKind.ACTION_VERIFIED,
                    }
                ]
            satisfied, blocked = prerequisites_satisfied(
                prerequisites,
                action_statuses=action_statuses,
                verification_statuses=current_statuses,
                resource_statuses=resource_statuses,
            )
            if not satisfied:
                item = RuntimeSecurityVerification(
                    expectation_id=expectation.id,
                    stage=stage,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    evidence_method="verification_prerequisite_gate",
                    fields={"prerequisites": FieldVerificationStatus.UNOBSERVABLE},
                    message="Blocked by: " + ", ".join(blocked),
                )
            else:
                runnable, gated = self._gate_verification_capabilities(
                    plan, [expectation], capabilities, stage,
                )
                if gated:
                    item = gated[0]
                elif stage is SecurityVerificationStage.DIRECT_STATE:
                    item = self._safe_observe(runnable)[0]
                else:
                    item = self._safe_behavior(runnable, stage)[0]
            observed.append(item)
            current_statuses[expectation.id] = item.status
        return observed

    @staticmethod
    def _evidence_records(
        plan: SecurityPlan,
        observed: Sequence[RuntimeSecurityVerification],
        context: ConfigurationRuntimeContext,
    ) -> list[EvidenceRecord]:
        expectations = {
            item.id: item for item in plan.verification_expectations
        }
        actions = {item.id: item for item in plan.actions}
        records = []
        for item in observed:
            expectation = expectations[item.expectation_id]
            action = actions.get(expectation.action_id)
            subject = expectation.source_device_id or (
                action.device_id if action else expectation.policy_id
            )
            records.append(evidence_from_legacy_result(
                identifier=(
                    f"evidence/security/{item.expectation_id}/{item.stage.value}"
                ),
                subject=subject,
                claim=f"{expectation.kind.value}:{item.stage.value}",
                status=item.status,
                evidence_method=item.evidence_method,
                fresh_evidence=item.fresh_evidence,
                observed_value={
                    "stage": item.stage.value,
                    "expected_decision": expectation.expected_decision.value,
                    "protocol": expectation.protocol,
                    "destination_ports": list(expectation.destination_ports),
                    "fields": {
                        name: value.value
                        for name, value in sorted(item.fields.items())
                    },
                },
                backend=context.backend,
                backend_version=context.backend_version,
                environment_fingerprint=context.capability_snapshot_hash,
                limitations=[item.message] if item.message else [],
            ))
        return records

    def _safe_observe(self, expectations):
        if not expectations:
            return []
        try:
            observed = self._runtime.observe(expectations)
        except Exception as exc:
            observed = [RuntimeSecurityVerification(
                expectation_id=item.id,
                stage=SecurityVerificationStage.DIRECT_STATE,
                status=ActionExecutionStatus.FAILED,
                message=str(exc),
            ) for item in expectations]
        return self._complete_observations(
            expectations, observed, SecurityVerificationStage.DIRECT_STATE,
        )

    def _safe_behavior(self, expectations, stage):
        if not expectations:
            return []
        try:
            observed = self._runtime.verify_behavior(expectations, stage)
        except Exception as exc:
            observed = [RuntimeSecurityVerification(
                expectation_id=item.id,
                stage=stage,
                status=ActionExecutionStatus.FAILED,
                message=str(exc),
            ) for item in expectations]
        return self._complete_observations(expectations, observed, stage)

    @staticmethod
    def _gate_verification_capabilities(plan, expectations, capabilities, stage):
        actions = {item.id: item for item in plan.actions}
        runnable = []
        gated = []
        for expectation in expectations:
            dimension = security_verification_capability(expectation)
            action = actions.get(expectation.action_id)
            profile = capabilities.get(action.model) if action else None
            support = (
                profile.status(dimension) if profile
                else SecurityCapabilityStatus.UNKNOWN
            )
            if support in {
                SecurityCapabilityStatus.SUPPORTED,
                SecurityCapabilityStatus.PARTIAL,
            }:
                runnable.append(expectation)
                continue
            gated.append(RuntimeSecurityVerification(
                expectation_id=expectation.id,
                stage=stage,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method="security_capability_gate",
                fresh_evidence=False,
                fields={"capability": FieldVerificationStatus.UNOBSERVABLE},
                message=(
                    f"{action.model if action else 'unknown'}:"
                    f"{dimension.value} is {support.value}."
                ),
            ))
        return runnable, gated

    @staticmethod
    def _complete_observations(expectations, observed, stage):
        by_id = {item.expectation_id: item for item in observed}
        return [by_id.get(item.id, RuntimeSecurityVerification(
            expectation_id=item.id,
            stage=stage,
            status=ActionExecutionStatus.UNKNOWN,
            message="Runtime returned no verification result.",
        )) for item in expectations]

    @staticmethod
    def _merge_verification(results, observed):
        for item in observed:
            result = results[item.expectation_id]
            if item.stage is SecurityVerificationStage.BASELINE:
                result.baseline_status = item.status
            elif item.stage is SecurityVerificationStage.DIRECT_STATE:
                result.direct_status = item.status
            elif item.stage is SecurityVerificationStage.ENFORCEMENT_BEHAVIOR:
                result.enforcement_status = item.status
            elif item.stage is SecurityVerificationStage.CLEANUP_RECOVERY:
                result.cleanup_status = item.status
            if item.evidence_method:
                result.evidence_methods.append(item.evidence_method)
            result.fresh_evidence = result.fresh_evidence or item.fresh_evidence
            result.fields.update(item.fields)
            if item.message:
                result.message = " ".join(filter(None, (result.message, item.message)))

    def _cleanup(self, plan, action_results):
        applied = {
            item.action_id for item in action_results
            if satisfies_apply_dependency(item.status)
        }
        actions = [item for item in reversed(plan.actions) if item.id in applied]
        try:
            mutations = {
                item.action_id: item for item in self._runtime.cleanup_actions(actions)
            }
        except Exception as exc:
            mutations = {
                item.id: RuntimeActionMutation(
                    action_id=item.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.SECURITY_CLEANUP_FAILED,
                    message=str(exc),
                ) for item in actions
            }
        return [ActionApplicationResult(
            action_id=item.id,
            status=(
                self._mutation_status(mutations[item.id])
                if item.id in mutations
                else ActionExecutionStatus.FAILED
            ),
            failure_code=(
                ConfigurationFailureCode.NONE
                if mutations.get(item.id) and mutations[item.id].applied
                else ConfigurationFailureCode.SECURITY_CLEANUP_FAILED
            ),
            message=mutations[item.id].message if item.id in mutations else "No cleanup result.",
            batch_id=mutations[item.id].batch_id if item.id in mutations else "",
            operation=item.operation,
            disposition=(
                mutations[item.id].disposition
                if item.id in mutations else MutationDisposition.UNKNOWN
            ),
        ) for item in actions]

    @staticmethod
    def _overall(actions, verification, cleanup, cleanup_control):
        if any(item.status is ActionExecutionStatus.FAILED for item in actions):
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.SECURITY_APPLICATION_FAILED,
            )
        if cleanup_control and any(
            not satisfies_apply_dependency(item.status) for item in cleanup
        ):
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.SECURITY_CLEANUP_FAILED,
            )
        if any(
            item.enforcement_status in {
                ActionExecutionStatus.FAILED,
                ActionExecutionStatus.UNKNOWN,
            }
            for item in verification
        ):
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.SECURITY_ENFORCEMENT_FAILED,
            )
        if cleanup_control and any(
            item.cleanup_status not in {
                ActionExecutionStatus.SKIPPED,
                ActionExecutionStatus.VERIFIED,
            }
            for item in verification
        ):
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.SECURITY_CLEANUP_FAILED,
            )
        direct = [
            item.direct_status for item in verification
            if item.direct_status is not ActionExecutionStatus.SKIPPED
        ]
        if any(item is ActionExecutionStatus.FAILED for item in direct):
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.SECURITY_DIRECT_READBACK_FAILED,
            )
        if any(item.status in {
            ActionExecutionStatus.SKIPPED,
            ActionExecutionStatus.DEPENDENCY_BLOCKED,
        } for item in actions):
            return ConfigurationApplicationStatus.PARTIAL, ConfigurationFailureCode.NONE
        if any(item.enforcement_status in {
            ActionExecutionStatus.UNOBSERVABLE,
            ActionExecutionStatus.PARTIAL,
        } for item in verification):
            return (
                ConfigurationApplicationStatus.PARTIAL,
                ConfigurationFailureCode.SECURITY_BEHAVIOR_UNOBSERVABLE,
            )
        if any(item in {
            ActionExecutionStatus.UNKNOWN,
            ActionExecutionStatus.UNOBSERVABLE,
            ActionExecutionStatus.PARTIAL,
        } for item in direct):
            return (
                ConfigurationApplicationStatus.PARTIAL,
                ConfigurationFailureCode.DIRECT_READBACK_UNOBSERVABLE,
            )
        if verification:
            return ConfigurationApplicationStatus.VERIFIED, ConfigurationFailureCode.NONE
        if actions:
            return ConfigurationApplicationStatus.APPLIED, ConfigurationFailureCode.NONE
        return ConfigurationApplicationStatus.SKIPPED, ConfigurationFailureCode.NONE

    @staticmethod
    def _failure(
        plan,
        code,
        message,
        context,
        started,
        *,
        verification_results=None,
        deployment_id="",
        evidence_records=None,
    ):
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=[],
        )
        journal.mark_preflight_failure(message)
        return SecurityApplicationResult(
            security_plan_id=plan.id,
            security_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            source_service_hash=plan.source_service_hash,
            source_voice_hash=plan.source_voice_hash,
            runtime_context=context,
            status=ConfigurationApplicationStatus.FAILED,
            failure_code=code,
            verification_results=verification_results or [],
            preflight_errors=[message],
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            evidence_records=evidence_records or [],
            duration_ms=int((monotonic() - started) * 1000),
        )
