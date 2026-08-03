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
    ) -> ServiceApplicationResult:
        started = monotonic()
        runtime_context = runtime_context or ConfigurationRuntimeContext()
        if actual_source_topology_hash != plan.source_topology_hash:
            return self._failure(
                plan, ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH,
                "ServicePlan source hash does not match the deployed E4 topology.",
                context=runtime_context, started=started,
            )
        if actual_source_configuration_hash != plan.source_configuration_hash:
            return self._failure(
                plan, ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH,
                "ServicePlan source hash does not match the applied E5 configuration.",
                context=runtime_context, started=started,
            )
        try:
            ordered = order_dependency_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED, str(exc),
                context=runtime_context, started=started,
            )
        if [item.id for item in ordered] != [item.id for item in plan.actions]:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "ServicePlan actions are not in deterministic dependency order.",
                context=runtime_context, started=started,
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
                context=runtime_context, started=started,
            )
        try:
            inventory = {item.device_name: item for item in self._runtime.inventory()}
        except Exception as exc:
            return self._failure(
                plan, ConfigurationFailureCode.SESSION_FAILED,
                f"Runtime inventory failed: {exc}", context=runtime_context, started=started,
            )
        target_errors = []
        for requirement in plan.foundational_requirements:
            target = inventory.get(requirement.device_name)
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
            )

        capabilities = capabilities or {}
        results: dict[str, ActionApplicationResult] = {}
        for action in plan.actions:
            profile = capabilities.get(f"{action.host_model}:{action.service_type.value}")
            support = (
                profile.application_support if profile else CapabilityStatus.UNKNOWN
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
                message=f"{action.host_model}:{action.service_type.value} is {support.value}.",
            )

        pending = [item for item in plan.actions if item.id not in results]
        while pending:
            progress = False
            for action in list(pending):
                failed_dependencies = [
                    dependency for dependency in action.depends_on
                    if dependency in results
                    and results[dependency].status is not ActionExecutionStatus.APPLIED
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
                    and results[dependency].status is ActionExecutionStatus.APPLIED
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
                    mutations = {
                        item.action_id: item for item in self._runtime.apply_actions(batch)
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
                        status=(ActionExecutionStatus.APPLIED if applied else ActionExecutionStatus.FAILED),
                        failure_code=(
                            ConfigurationFailureCode.NONE if applied
                            else mutation.failure_code if mutation
                            and mutation.failure_code is not ConfigurationFailureCode.NONE
                            else ConfigurationFailureCode.APPLICATION_FAILED
                        ),
                        message=mutation.message if mutation else "Runtime returned no mutation result.",
                        batch_id=mutation.batch_id if mutation else "",
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
        verification = self._verify(plan, results, capabilities)
        outcomes = self._outcomes(plan, results, verification)
        status, failure_code = self._overall(action_results, outcomes)
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
            duration_ms=int((monotonic() - started) * 1000),
        )

    def _verify(self, plan, action_results, capabilities):
        results: dict[str, ServiceVerificationResult] = {}
        services = {item.id: item for item in plan.services}
        for expectation in plan.verification_expectations:
            action = action_results.get(expectation.action_id)
            blocked = [
                item for item in expectation.depends_on
                if item not in results or results[item].status is not ActionExecutionStatus.VERIFIED
            ]
            if action is None or action.status is not ActionExecutionStatus.APPLIED:
                blocked.append(expectation.action_id)
            if blocked:
                results[expectation.id] = ServiceVerificationResult(
                    expectation_id=expectation.id,
                    service_id=expectation.service_id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    evidence_kind=expectation.evidence_kind,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(sorted(set(blocked))),
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
                observed = self._runtime.verify(expectation)
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
                    item.status is ActionExecutionStatus.APPLIED for item in service_actions
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
    def _failure(plan, code, *messages, context, started):
        return ServiceApplicationResult(
            service_plan_id=plan.id,
            service_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            runtime_context=context,
            status=ConfigurationApplicationStatus.FAILED,
            failure_code=code,
            preflight_errors=list(messages),
            duration_ms=int((monotonic() - started) * 1000),
        )
