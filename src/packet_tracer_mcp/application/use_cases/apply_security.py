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
    ) -> SecurityApplicationResult:
        started = monotonic()
        context = runtime_context or ConfigurationRuntimeContext()
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
            )
        try:
            ordered = order_dependency_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                str(exc), context, started,
            )
        if [item.id for item in ordered] != [item.id for item in plan.actions]:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "SecurityPlan actions are not in deterministic dependency order.",
                context, started,
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
            )
        try:
            inventory = {item.device_name: item for item in self._runtime.inventory()}
        except Exception as exc:
            return self._failure(
                plan, ConfigurationFailureCode.SESSION_FAILED,
                f"Security runtime inventory failed: {exc}", context, started,
            )
        target_errors = self._validate_targets(plan, inventory)
        if target_errors:
            return self._failure(
                plan, ConfigurationFailureCode.TARGET_NOT_FOUND,
                " ".join(target_errors), context, started,
            )

        verification: dict[str, SecurityVerificationResult] = {
            item.id: SecurityVerificationResult(
                expectation_id=item.id,
                action_id=item.action_id,
                policy_id=item.policy_id,
            )
            for item in plan.verification_expectations
        }
        baseline = [
            item for item in plan.verification_expectations
            if item.kind is SecurityVerificationKind.TRAFFIC_POLICY
            and item.baseline_required
        ]
        capability_profiles = capabilities or {}
        if baseline:
            runnable, gated = self._gate_verification_capabilities(
                plan, baseline, capability_profiles,
                SecurityVerificationStage.BASELINE,
            )
            observed = [
                *gated,
                *self._safe_behavior(runnable, SecurityVerificationStage.BASELINE),
            ]
            self._merge_verification(verification, observed)
            if any(item.status is not ActionExecutionStatus.VERIFIED for item in observed):
                return self._failure(
                    plan,
                    ConfigurationFailureCode.SECURITY_BASELINE_FAILED,
                    "A deny control had no verified working baseline; no policy was mutated.",
                    context,
                    started,
                    verification_results=list(verification.values()),
                )

        action_results = self._apply_actions(plan, capability_profiles)
        applied_ids = {
            item.action_id for item in action_results
            if item.status is ActionExecutionStatus.APPLIED
        }
        direct = [
            item for item in plan.verification_expectations
            if item.probe_kind is SecurityProbeKind.DIRECT_READBACK
            and item.action_id in applied_ids
        ]
        if direct:
            runnable, gated = self._gate_verification_capabilities(
                plan, direct, capability_profiles,
                SecurityVerificationStage.DIRECT_STATE,
            )
            self._merge_verification(
                verification, [*gated, *self._safe_observe(runnable)],
            )
        behavior = [
            item for item in plan.verification_expectations
            if item.probe_kind is not SecurityProbeKind.DIRECT_READBACK
            and item.action_id in applied_ids
        ]
        if behavior:
            runnable, gated = self._gate_verification_capabilities(
                plan, behavior, capability_profiles,
                SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
            )
            self._merge_verification(
                verification,
                [*gated, *self._safe_behavior(
                    runnable, SecurityVerificationStage.ENFORCEMENT_BEHAVIOR,
                )],
            )

        cleanup_results: list[ActionApplicationResult] = []
        if cleanup_control:
            cleanup_results = self._cleanup(plan, action_results)
            recovery = [item for item in behavior if item.cleanup_recovery_required]
            if recovery and all(
                item.status is ActionExecutionStatus.APPLIED for item in cleanup_results
            ):
                runnable, gated = self._gate_verification_capabilities(
                    plan, recovery, capability_profiles,
                    SecurityVerificationStage.CLEANUP_RECOVERY,
                )
                self._merge_verification(
                    verification,
                    [*gated, *self._safe_behavior(
                        runnable, SecurityVerificationStage.CLEANUP_RECOVERY,
                    )],
                )

        verification_results = [
            verification[item.id] for item in plan.verification_expectations
        ]
        status, failure_code = self._overall(
            action_results, verification_results, cleanup_results, cleanup_control,
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
                        and results[dependency].status is ActionExecutionStatus.APPLIED
                        for dependency in action.depends_on
                    )
                ]
                if not ready:
                    for action in pending:
                        blocked = [
                            dependency for dependency in action.depends_on
                            if dependency not in results
                            or results[dependency].status is not ActionExecutionStatus.APPLIED
                        ]
                        results[action.id] = ActionApplicationResult(
                            action_id=action.id,
                            status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                            failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                            message="Blocked by: " + ", ".join(sorted(blocked)),
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
                    applied = bool(mutation and mutation.applied)
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=(
                            ActionExecutionStatus.APPLIED if applied
                            else ActionExecutionStatus.FAILED
                        ),
                        failure_code=(
                            ConfigurationFailureCode.NONE if applied
                            else mutation.failure_code if mutation
                            else ConfigurationFailureCode.SECURITY_APPLICATION_FAILED
                        ),
                        message=(
                            mutation.message if mutation
                            else "Runtime returned no mutation."
                        ),
                        batch_id=mutation.batch_id if mutation else "",
                    )
                    pending.remove(action)
        return [results[item.id] for item in plan.actions]

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
            if item.status is ActionExecutionStatus.APPLIED
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
                ActionExecutionStatus.APPLIED
                if mutations.get(item.id) and mutations[item.id].applied
                else ActionExecutionStatus.FAILED
            ),
            failure_code=(
                ConfigurationFailureCode.NONE
                if mutations.get(item.id) and mutations[item.id].applied
                else ConfigurationFailureCode.SECURITY_CLEANUP_FAILED
            ),
            message=mutations[item.id].message if item.id in mutations else "No cleanup result.",
        ) for item in actions]

    @staticmethod
    def _overall(actions, verification, cleanup, cleanup_control):
        if any(item.status is ActionExecutionStatus.FAILED for item in actions):
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.SECURITY_APPLICATION_FAILED,
            )
        if cleanup_control and any(
            item.status is not ActionExecutionStatus.APPLIED for item in cleanup
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
    ):
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
            duration_ms=int((monotonic() - started) * 1000),
        )
