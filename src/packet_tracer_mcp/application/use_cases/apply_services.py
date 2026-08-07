"""Aplicación E6 con preflight, DAG y verificación conductual independiente."""

from __future__ import annotations

from collections.abc import Sequence
from time import monotonic
from typing import Protocol

from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.deployment import (
    DeploymentIdentityError,
    DeploymentManifest,
    resolve_manifest_targets,
)
from ...domain.enterprise.models.execution import (
    MutationDisposition,
    journal_from_action_results,
    satisfies_apply_dependency,
)
from ...domain.enterprise.models.evidence import evidence_from_legacy_result
from ...domain.enterprise.models.service_plan import (
    ServiceAction,
    ServiceCapabilityProfile,
    ServiceEvidenceKind,
    ServicePlan,
    ServiceVerificationExpectation,
)
from ...domain.enterprise.models.service_runtime import (
    RuntimeServiceVerification,
    ServiceApplicationResult,
    ServiceOutcome,
    ServiceVerificationResult,
)
from ...domain.enterprise.services.configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)
from ...domain.enterprise.models.verification import (
    PrerequisiteKind,
    VerificationPrerequisite,
    order_verification_expectations,
    prerequisites_satisfied,
)


class ServiceRuntime(Protocol):
    def inventory(self) -> list[RuntimeConfigurationTarget]: ...

    def apply_actions(
        self, actions: Sequence[ServiceAction],
    ) -> list[RuntimeActionMutation]: ...

    def verify(
        self, expectation: ServiceVerificationExpectation,
    ) -> RuntimeServiceVerification: ...


class ServiceApplicator:
    """Ejecuta un ServicePlan; nunca compila ni aplica configuración E5."""

    def __init__(self, runtime: ServiceRuntime) -> None:
        self._runtime = runtime

    def apply(
        self,
        plan: ServicePlan,
        *,
        actual_source_topology_hash: str,
        actual_source_configuration_hash: str,
        foundational_statuses: dict[str, ActionExecutionStatus],
        capabilities: dict[str, ServiceCapabilityProfile] | None = None,
        runtime_context: ConfigurationRuntimeContext | None = None,
        deployment_manifest: DeploymentManifest | None = None,
    ) -> ServiceApplicationResult:
        started = monotonic()
        runtime_context = runtime_context or ConfigurationRuntimeContext()
        deployment_id = deployment_manifest.deployment_id if deployment_manifest else ""
        if actual_source_topology_hash != plan.source_topology_hash:
            return self._failure(
                plan, ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH,
                "ServicePlan source hash does not match the deployed E4 topology.",
                context=runtime_context, deployment_id=deployment_id, started=started,
            )
        if (
            deployment_manifest is not None
            and deployment_manifest.physical_topology_hash != plan.source_topology_hash
        ):
            return self._failure(
                plan, ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
                "DeploymentManifest physical topology hash does not match ServicePlan.",
                context=runtime_context, deployment_id=deployment_id, started=started,
            )
        if actual_source_configuration_hash != plan.source_configuration_hash:
            return self._failure(
                plan, ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH,
                "ServicePlan source hash does not match the applied E5 configuration.",
                context=runtime_context, deployment_id=deployment_id, started=started,
            )
        try:
            ordered = order_dependency_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED, str(exc),
                context=runtime_context, deployment_id=deployment_id, started=started,
            )
        if [item.id for item in ordered] != [item.id for item in plan.actions]:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "ServicePlan actions are not in deterministic dependency order.",
                context=runtime_context, deployment_id=deployment_id, started=started,
            )
        missing_foundation = sorted(
            item.configuration_action_id
            for item in plan.foundational_requirements
            if foundational_statuses.get(item.configuration_action_id)
            is not ActionExecutionStatus.VERIFIED
        )
        if missing_foundation:
            return self._failure(
                plan, ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                "Foundational E5 actions are not VERIFIED: " + ", ".join(missing_foundation),
                context=runtime_context, deployment_id=deployment_id, started=started,
            )
        try:
            runtime_inventory = self._runtime.inventory()
        except Exception as exc:
            return self._failure(
                plan, ConfigurationFailureCode.SESSION_FAILED,
                f"Runtime inventory failed: {exc}", context=runtime_context,
                deployment_id=deployment_id, started=started,
            )
        deployed_names: dict[str, str] = {}
        if deployment_manifest is not None:
            semantic_device_ids = [
                item.device_id for item in plan.foundational_requirements
            ] + [
                item.host_device_id for item in plan.actions
            ] + [
                identifier
                for item in plan.verification_expectations
                for identifier in (item.host_device_id, item.client_device_id)
                if identifier
            ]
            try:
                semantic_targets = resolve_manifest_targets(
                    deployment_manifest,
                    physical_topology_hash=plan.source_topology_hash,
                    semantic_device_ids=semantic_device_ids,
                    inventory=runtime_inventory,
                )
            except DeploymentIdentityError as exc:
                return self._failure(
                    plan, ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH, str(exc),
                    context=runtime_context, deployment_id=deployment_id, started=started,
                )
            deployed_names = {
                identifier: target.device_name
                for identifier, target in semantic_targets.items()
            }
            targets = semantic_targets
        else:
            inventory_by_name = {item.device_name: item for item in runtime_inventory}
            deployed_names = {
                item.device_id: item.device_name
                for item in plan.foundational_requirements
            }
            deployed_names.update({
                item.host_device_id: item.host_device_name
                for item in plan.actions
            })
            deployed_names.update({
                identifier: name
                for item in plan.verification_expectations
                for identifier, name in (
                    (item.host_device_id, item.host_device_name),
                    (item.client_device_id, item.client_device_name),
                )
                if identifier
            })
            targets = {
                item.device_id: inventory_by_name[item.device_name]
                for item in plan.foundational_requirements
                if item.device_name in inventory_by_name
            }
        target_errors = []
        for requirement in plan.foundational_requirements:
            target = targets.get(requirement.device_id)
            if target is None:
                target_errors.append(f"Target {requirement.device_name} was not found.")
            elif target.model.casefold() != requirement.model.casefold():
                target_errors.append(
                    f"Target {requirement.device_name} model {target.model} does not match "
                    f"{requirement.model}."
                )
        if target_errors:
            code = (
                ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
                if any("model" in item.casefold() for item in target_errors)
                else ConfigurationFailureCode.TARGET_NOT_FOUND
            )
            return self._failure(
                plan, code, *sorted(target_errors), context=runtime_context, started=started,
                deployment_id=deployment_id,
            )

        capabilities = capabilities or {}
        results: dict[str, ActionApplicationResult] = {}
        for action in plan.actions:
            profile = capabilities.get(f"{action.host_model}:{action.service_type.value}")
            support = (
                profile.action_application_support.get(
                    action.action_type.value, profile.application_support,
                )
                if profile else CapabilityStatus.UNKNOWN
            )
            if support is CapabilityStatus.SUPPORTED:
                continue
            failure = (
                ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                if support is CapabilityStatus.UNSUPPORTED
                else ConfigurationFailureCode.CAPABILITY_UNKNOWN
            )
            results[action.id] = ActionApplicationResult(
                action_id=action.id,
                status=ActionExecutionStatus.SKIPPED,
                failure_code=failure,
                message=(
                    f"{action.host_model}:{action.service_type.value}:"
                    f"{action.action_type.value} is {support.value}."
                ),
            )

        pending = [item for item in plan.actions if item.id not in results]
        while pending:
            progress = False
            for action in list(pending):
                failed_dependencies = [
                    dependency for dependency in action.depends_on
                    if dependency in results
                    and not satisfies_apply_dependency(results[dependency].status)
                ]
                if failed_dependencies:
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message="Blocked by: " + ", ".join(sorted(failed_dependencies)),
                    )
                    pending.remove(action)
                    progress = True
            ready = [
                item for item in pending
                if all(
                    dependency in results
                    and satisfies_apply_dependency(results[dependency].status)
                    for dependency in item.depends_on
                )
            ]
            if ready:
                first = ready[0]
                batch = [
                    item for item in ready
                    if item.phase == first.phase and item.host_device_id == first.host_device_id
                ]
                try:
                    runtime_batch = [
                        item.model_copy(update={
                            "host_device_name": deployed_names[item.host_device_id],
                        })
                        for item in batch
                    ]
                    mutations = {
                        item.action_id: item
                        for item in self._runtime.apply_actions(runtime_batch)
                    }
                except Exception as exc:
                    mutations = {
                        item.id: RuntimeActionMutation(
                            action_id=item.id,
                            applied=False,
                            failure_code=ConfigurationFailureCode.SESSION_FAILED,
                            message=str(exc),
                        )
                        for item in batch
                    }
                for item in batch:
                    mutation = mutations.get(item.id)
                    applied = bool(mutation and mutation.applied)
                    results[item.id] = ActionApplicationResult(
                        action_id=item.id,
                        status=(
                            self._mutation_status(mutation)
                            if mutation else ActionExecutionStatus.FAILED
                        ),
                        failure_code=(
                            ConfigurationFailureCode.NONE if applied
                            else mutation.failure_code if mutation
                            and mutation.failure_code is not ConfigurationFailureCode.NONE
                            else ConfigurationFailureCode.APPLICATION_FAILED
                        ),
                        message=mutation.message if mutation else "Runtime returned no mutation result.",
                        batch_id=mutation.batch_id if mutation else "",
                        operation=item.operation,
                        disposition=(
                            mutation.disposition if mutation
                            else MutationDisposition.FAILED
                        ),
                    )
                    pending.remove(item)
                progress = True
            if not progress:
                for item in pending:
                    results[item.id] = ActionApplicationResult(
                        action_id=item.id,
                        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message="No executable dependency frontier remained.",
                    )
                break

        action_results = [results[item.id] for item in plan.actions]
        verification = self._verify(plan, results, capabilities, deployed_names)
        outcomes = self._outcomes(plan, results, verification)
        status, failure_code = self._overall(action_results, outcomes)
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=action_results,
        )
        expectations_by_id = {
            item.id: item for item in plan.verification_expectations
        }
        evidence_records = [
            evidence_from_legacy_result(
                identifier=f"evidence/{item.expectation_id}",
                subject=item.service_id,
                claim=expectations_by_id[item.expectation_id].kind.value,
                status=item.status,
                evidence_method=item.evidence_method,
                fresh_evidence=item.fresh_evidence,
                observed_value=item.observed,
                backend=runtime_context.backend,
                backend_version=runtime_context.backend_version,
                environment_fingerprint=runtime_context.capability_snapshot_hash,
                limitations=[item.message] if item.message else [],
            )
            for item in verification
        ]
        return ServiceApplicationResult(
            service_plan_id=plan.id,
            service_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            runtime_context=runtime_context,
            status=status,
            failure_code=failure_code,
            action_results=action_results,
            verification_results=verification,
            services=outcomes,
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            evidence_records=evidence_records,
            duration_ms=int((monotonic() - started) * 1000),
        )

    @staticmethod
    def _mutation_status(mutation: RuntimeActionMutation) -> ActionExecutionStatus:
        if not mutation.applied:
            return ActionExecutionStatus.FAILED
        if mutation.disposition is MutationDisposition.NO_OP:
            return ActionExecutionStatus.NO_OP
        if mutation.disposition is MutationDisposition.REASSERTED:
            return ActionExecutionStatus.REASSERTED
        return ActionExecutionStatus.APPLIED

    def _verify(self, plan, action_results, capabilities, deployed_names):
        results: dict[str, ServiceVerificationResult] = {}
        services = {item.id: item for item in plan.services}
        action_statuses = {
            identifier: result.status for identifier, result in action_results.items()
        }
        dag_expectations = [
            expectation
            if expectation.verification_prerequisites
            else expectation.model_copy(update={
                "verification_prerequisites": [
                    VerificationPrerequisite(
                        kind=PrerequisiteKind.ACTION_APPLIED,
                        reference_id=expectation.action_id,
                    ),
                    *[
                        VerificationPrerequisite(
                            kind=PrerequisiteKind.VERIFICATION_VERIFIED,
                            reference_id=identifier,
                        )
                        for identifier in expectation.depends_on
                    ],
                ],
            })
            for expectation in plan.verification_expectations
        ]
        try:
            ordered = order_verification_expectations(dag_expectations)
        except Exception as exc:
            return [ServiceVerificationResult(
                expectation_id=expectation.id,
                service_id=expectation.service_id,
                status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                evidence_kind=expectation.evidence_kind,
                failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                message=str(exc),
            ) for expectation in plan.verification_expectations]
        for expectation in ordered:
            prerequisites = expectation.verification_prerequisites or [
                VerificationPrerequisite(
                    kind=PrerequisiteKind.ACTION_APPLIED,
                    reference_id=expectation.action_id,
                ),
                *[
                    VerificationPrerequisite(
                        kind=PrerequisiteKind.VERIFICATION_VERIFIED,
                        reference_id=identifier,
                    )
                    for identifier in expectation.depends_on
                ],
            ]
            satisfied, blocked = prerequisites_satisfied(
                prerequisites,
                action_statuses=action_statuses,
                verification_statuses={
                    identifier: result.status for identifier, result in results.items()
                },
                resource_statuses={},
            )
            if not satisfied:
                results[expectation.id] = ServiceVerificationResult(
                    expectation_id=expectation.id,
                    service_id=expectation.service_id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    evidence_kind=expectation.evidence_kind,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(blocked),
                )
                continue
            service = services[expectation.service_id]
            profile = capabilities.get(f"{service.host_model}:{service.service_type.value}")
            support = CapabilityStatus.UNKNOWN
            if profile is not None:
                support = (
                    profile.direct_readback_support
                    if expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
                    else profile.behavioral_verification_support
                )
            if support is not CapabilityStatus.SUPPORTED:
                results[expectation.id] = ServiceVerificationResult(
                    expectation_id=expectation.id,
                    service_id=expectation.service_id,
                    status=ActionExecutionStatus.PARTIAL,
                    evidence_kind=expectation.evidence_kind,
                    failure_code=(
                        ConfigurationFailureCode.DIRECT_READBACK_UNOBSERVABLE
                        if expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
                        else ConfigurationFailureCode.CAPABILITY_UNKNOWN
                    ),
                    message=f"Verification capability is {support.value}.",
                )
                continue
            try:
                runtime_expectation = expectation.model_copy(update={
                    "host_device_name": deployed_names[expectation.host_device_id],
                    "client_device_name": (
                        deployed_names[expectation.client_device_id]
                        if expectation.client_device_id else expectation.client_device_name
                    ),
                })
                observed = self._runtime.verify(runtime_expectation)
                failure = (
                    ConfigurationFailureCode.NONE
                    if observed.status is ActionExecutionStatus.VERIFIED
                    else ConfigurationFailureCode.BEHAVIORAL_VERIFICATION_FAILED
                    if expectation.evidence_kind is not ServiceEvidenceKind.DIRECT_STATE
                    else ConfigurationFailureCode.VERIFICATION_FAILED
                )
                results[expectation.id] = ServiceVerificationResult(
                    **observed.model_dump(),
                    service_id=expectation.service_id,
                    failure_code=failure,
                )
            except Exception as exc:
                results[expectation.id] = ServiceVerificationResult(
                    expectation_id=expectation.id,
                    service_id=expectation.service_id,
                    status=ActionExecutionStatus.FAILED,
                    evidence_kind=expectation.evidence_kind,
                    failure_code=ConfigurationFailureCode.SESSION_FAILED,
                    message=str(exc),
                )
        return [results[item.id] for item in plan.verification_expectations]

    @staticmethod
    def _outcomes(plan, actions, verification):
        outcomes = []
        for service in plan.services:
            service_actions = [actions[item] for item in service.action_ids]
            application = (
                ActionExecutionStatus.APPLIED
                if service_actions and all(
                    satisfies_apply_dependency(item.status) for item in service_actions
                )
                else ActionExecutionStatus.FAILED
                if any(item.status is ActionExecutionStatus.FAILED for item in service_actions)
                else ActionExecutionStatus.PARTIAL
            )
            observed = [item for item in verification if item.service_id == service.id]
            direct = [item for item in observed if item.evidence_kind is ServiceEvidenceKind.DIRECT_STATE]
            behavior = [item for item in observed if item.evidence_kind is not ServiceEvidenceKind.DIRECT_STATE]
            direct_status = ServiceApplicator._aggregate(direct)
            behavior_status = ServiceApplicator._aggregate(behavior)
            usability = (
                ActionExecutionStatus.VERIFIED
                if behavior and behavior_status is ActionExecutionStatus.VERIFIED
                else ActionExecutionStatus.FAILED
                if behavior_status is ActionExecutionStatus.FAILED
                else ActionExecutionStatus.PARTIAL
                if behavior
                else application
            )
            outcomes.append(ServiceOutcome(
                service_id=service.id,
                service_type=service.service_type,
                application_status=application,
                direct_readback_status=direct_status,
                behavioral_status=behavior_status,
                usability_status=usability,
            ))
        return outcomes

    @staticmethod
    def _aggregate(items):
        if not items:
            return ActionExecutionStatus.UNKNOWN
        if any(item.status is ActionExecutionStatus.FAILED for item in items):
            return ActionExecutionStatus.FAILED
        if any(item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED for item in items):
            return ActionExecutionStatus.PARTIAL
        if all(item.status is ActionExecutionStatus.VERIFIED for item in items):
            return ActionExecutionStatus.VERIFIED
        return ActionExecutionStatus.PARTIAL

    @staticmethod
    def _overall(actions, outcomes):
        if any(item.status is ActionExecutionStatus.FAILED for item in actions):
            return ConfigurationApplicationStatus.FAILED, ConfigurationFailureCode.APPLICATION_FAILED
        if any(item.status in {
            ActionExecutionStatus.SKIPPED, ActionExecutionStatus.DEPENDENCY_BLOCKED,
        } for item in actions):
            return ConfigurationApplicationStatus.PARTIAL, ConfigurationFailureCode.NONE
        if outcomes and all(
            item.usability_status is ActionExecutionStatus.VERIFIED for item in outcomes
        ):
            return ConfigurationApplicationStatus.VERIFIED, ConfigurationFailureCode.NONE
        if any(item.usability_status is ActionExecutionStatus.FAILED for item in outcomes):
            return (
                ConfigurationApplicationStatus.PARTIAL,
                ConfigurationFailureCode.BEHAVIORAL_VERIFICATION_FAILED,
            )
        if actions:
            return ConfigurationApplicationStatus.PARTIAL, ConfigurationFailureCode.NONE
        return ConfigurationApplicationStatus.SKIPPED, ConfigurationFailureCode.NONE

    @staticmethod
    def _failure(plan, code, *messages, context, deployment_id="", started):
        journal = journal_from_action_results(
            plan_id=plan.id, deployment_id=deployment_id,
            actions=list(plan.actions), results=[],
        )
        for message in messages:
            journal.mark_preflight_failure(message)
        return ServiceApplicationResult(
            service_plan_id=plan.id,
            service_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            runtime_context=context,
            status=ConfigurationApplicationStatus.FAILED,
            failure_code=code,
            preflight_errors=list(messages),
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            duration_ms=int((monotonic() - started) * 1000),
        )
