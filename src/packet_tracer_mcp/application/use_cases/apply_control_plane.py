"""Aplicación E9 offline con hashes, DAG, evidencia y escenarios separados."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
from ...domain.enterprise.models.control_plane import (
    ConfigureEtherChannel,
    ConfigureHsrp,
    ConfigureStpEdgePort,
    ControlPlaneAction,
    ControlPlaneCapabilityDimension,
    ControlPlaneCapabilityProfile,
    ControlPlanePlan,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    LinkFailureScenario,
)
from ...domain.enterprise.models.control_plane_runtime import (
    ControlPlaneApplicationResult,
    ControlPlaneExecutionStage,
    ControlPlaneVerificationResult,
    FailureScenarioResult,
    RuntimeControlPlaneVerification,
    RuntimeFailureScenarioResult,
)
from ...domain.enterprise.models.security_plan import SecurityCapabilityStatus
from ...domain.enterprise.services.configuration_dependencies import (
    ConfigurationDependencyError,
    order_dependency_actions,
)


_OBSERVED_KINDS = {
    ControlPlaneVerificationKind.STP_STATE,
    ControlPlaneVerificationKind.ETHERCHANNEL_STATE,
    ControlPlaneVerificationKind.HSRP_STATE,
    ControlPlaneVerificationKind.ROUTING_PROCESS,
    ControlPlaneVerificationKind.ROUTING_NEIGHBOR,
    ControlPlaneVerificationKind.ROUTE_PRESENT,
}
_BEHAVIOR_KINDS = {ControlPlaneVerificationKind.END_TO_END_REACHABILITY}
_SCENARIO_KINDS = {
    ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE,
    ControlPlaneVerificationKind.RESTORE_RECOVERY,
}
_RUNNABLE_CAPABILITIES = {
    SecurityCapabilityStatus.SUPPORTED,
    SecurityCapabilityStatus.PARTIAL,
}


class ControlPlaneRuntime(Protocol):
    def inventory(self) -> list[RuntimeConfigurationTarget]: ...

    def apply_actions(
        self, actions: Sequence[ControlPlaneAction],
    ) -> list[RuntimeActionMutation]: ...

    def verify(
        self, expectations: Sequence[ControlPlaneVerificationExpectation],
    ) -> list[RuntimeControlPlaneVerification]: ...

    def execute_failure_scenario(
        self,
        scenario: LinkFailureScenario,
        failure_expectation: ControlPlaneVerificationExpectation,
        recovery_expectation: ControlPlaneVerificationExpectation,
    ) -> RuntimeFailureScenarioResult: ...


class ControlPlaneApplicator:
    """Ejecuta únicamente un ControlPlanePlan ya compilado y cerrado."""

    def __init__(self, runtime: ControlPlaneRuntime) -> None:
        self._runtime = runtime

    def apply(
        self,
        plan: ControlPlanePlan,
        *,
        actual_source_topology_hash: str,
        actual_source_configuration_hash: str,
        foundational_statuses: Mapping[str, ActionExecutionStatus],
        actual_source_security_hash: str = "",
        foundational_hashes: Mapping[str, str] | None = None,
        capabilities: Mapping[str, ControlPlaneCapabilityProfile] | None = None,
        runtime_context: ConfigurationRuntimeContext | None = None,
    ) -> ControlPlaneApplicationResult:
        started = monotonic()
        context = runtime_context or ConfigurationRuntimeContext()
        mismatch = self._source_mismatch(
            plan,
            actual_source_topology_hash,
            actual_source_configuration_hash,
            actual_source_security_hash,
        )
        if mismatch:
            code, message = mismatch
            return self._failure(
                plan, code, message, context=context, started=started,
            )

        try:
            ordered = order_dependency_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                str(exc), context=context, started=started,
            )
        if [item.id for item in ordered] != [item.id for item in plan.actions]:
            return self._failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "ControlPlanePlan actions are not in deterministic dependency order.",
                context=context,
                started=started,
            )

        foundation_errors = self._foundation_errors(
            plan, foundational_statuses, foundational_hashes or {},
        )
        if foundation_errors:
            return self._failure(
                plan,
                ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING,
                *foundation_errors,
                context=context,
                started=started,
            )

        try:
            inventory = {item.device_name: item for item in self._runtime.inventory()}
        except Exception as exc:
            return self._failure(
                plan, ConfigurationFailureCode.SESSION_FAILED,
                f"Control-plane runtime inventory failed: {exc}",
                context=context, started=started,
            )
        target_errors = self._target_errors(plan, inventory)
        if target_errors:
            code = (
                ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
                if any("model" in item.casefold() for item in target_errors)
                else ConfigurationFailureCode.INTERFACE_NOT_FOUND
                if any("interface" in item.casefold() for item in target_errors)
                else ConfigurationFailureCode.TARGET_NOT_FOUND
            )
            return self._failure(
                plan, code, *target_errors, context=context, started=started,
            )

        profiles = capabilities or {}
        action_results = self._apply_actions(plan, profiles)
        by_action = {item.action_id: item for item in action_results}
        observed_results = self._verify_stage(
            plan,
            [
                item for item in plan.verification_expectations
                if item.kind in _OBSERVED_KINDS
            ],
            ControlPlaneExecutionStage.OBSERVED,
            by_action,
            profiles,
        )
        behavior_results = self._verify_stage(
            plan,
            [
                item for item in plan.verification_expectations
                if item.kind in _BEHAVIOR_KINDS
            ],
            ControlPlaneExecutionStage.BEHAVIOR,
            by_action,
            profiles,
        )
        bound_scenario_expectations = {
            expectation_id
            for scenario in plan.failure_scenarios
            for expectation_id in scenario.verification_expectation_ids
        }
        failover_results = self._unbound_failover_results(
            plan, by_action, profiles, bound_scenario_expectations,
        )
        scenario_results = self._execute_scenarios(
            plan, by_action, inventory, profiles,
        )

        applied_status = self._aggregate(
            [item.status for item in action_results], ActionExecutionStatus.APPLIED,
        )
        observed_status = self._aggregate(
            [item.status for item in observed_results], ActionExecutionStatus.VERIFIED,
        )
        behavior_status = self._aggregate(
            [item.status for item in behavior_results], ActionExecutionStatus.VERIFIED,
        )
        failover_status = self._aggregate(
            [
                *(item.status for item in failover_results),
                *(item.status for item in scenario_results),
            ],
            ActionExecutionStatus.VERIFIED,
        )
        status, failure_code = self._overall(
            action_results,
            observed_results,
            behavior_results,
            failover_results,
            scenario_results,
        )
        return ControlPlaneApplicationResult(
            control_plane_plan_id=plan.id,
            control_plane_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            source_security_hash=plan.source_security_hash,
            runtime_context=context,
            status=status,
            failure_code=failure_code,
            configured_status=ActionExecutionStatus.COMPILED,
            applied_status=applied_status,
            observed_status=observed_status,
            behavior_status=behavior_status,
            failover_status=failover_status,
            action_results=action_results,
            observed_results=observed_results,
            behavior_results=behavior_results,
            failover_results=failover_results,
            scenario_results=scenario_results,
            duration_ms=int((monotonic() - started) * 1000),
        )

    @staticmethod
    def _source_mismatch(plan, topology_hash, configuration_hash, security_hash):
        if topology_hash != plan.source_topology_hash:
            return (
                ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH,
                "ControlPlanePlan source hash does not match deployed E4.",
            )
        if configuration_hash != plan.source_configuration_hash:
            return (
                ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH,
                "ControlPlanePlan source hash does not match applied E5.",
            )
        if plan.source_security_hash and security_hash != plan.source_security_hash:
            return (
                ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH,
                "ControlPlanePlan source hash does not match applied E8.",
            )
        return None

    @staticmethod
    def _foundation_errors(plan, statuses, hashes) -> list[str]:
        errors: list[str] = []
        for requirement in plan.foundational_requirements:
            if statuses.get(requirement.source_id) is not ActionExecutionStatus.VERIFIED:
                errors.append(
                    f"Foundation {requirement.source_id} is not VERIFIED."
                )
            if (
                requirement.source_hash
                and hashes.get(requirement.source_id) != requirement.source_hash
            ):
                errors.append(
                    f"Foundation {requirement.source_id} source hash does not match."
                )
        return sorted(set(errors))

    @staticmethod
    def _target_errors(
        plan: ControlPlanePlan,
        inventory: Mapping[str, RuntimeConfigurationTarget],
    ) -> list[str]:
        errors: list[str] = []
        for action in plan.actions:
            target = inventory.get(action.device_name)
            if target is None:
                errors.append(f"Target {action.device_name} was not found.")
            elif target.model.casefold() != action.model.casefold():
                errors.append(
                    f"Target {action.device_name} model {target.model} does not match "
                    f"{action.model}."
                )
            elif target.interfaces:
                available = {item.casefold() for item in target.interfaces}
                for interface in ControlPlaneApplicator._action_interfaces(action):
                    if interface.casefold() in available:
                        continue
                    errors.append(
                        f"Target {action.device_name} interface {interface} was not found."
                    )
        for scenario in plan.failure_scenarios:
            for name, interface in (
                (scenario.target_device_name, scenario.target_interface),
                (scenario.peer_device_name, scenario.peer_interface),
            ):
                target = inventory.get(name)
                if target is None:
                    errors.append(f"Failure scenario target {name} was not found.")
                elif target.interfaces and interface.casefold() not in {
                    item.casefold() for item in target.interfaces
                }:
                    errors.append(
                        f"Failure scenario target {name} interface {interface} was not found."
                    )
        return sorted(set(errors))

    @staticmethod
    def _action_interfaces(action: ControlPlaneAction) -> list[str]:
        if isinstance(action, (ConfigureStpEdgePort, ConfigureHsrp)):
            return [action.interface]
        if isinstance(action, ConfigureEtherChannel):
            return list(action.member_interfaces)
        return []

    def _apply_actions(
        self,
        plan: ControlPlanePlan,
        profiles: Mapping[str, ControlPlaneCapabilityProfile],
    ) -> list[ActionApplicationResult]:
        results: dict[str, ActionApplicationResult] = {}
        for action in plan.actions:
            support = self._capability_status(
                profiles, action.model, action.required_capability,
            )
            if support in _RUNNABLE_CAPABILITIES:
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

        pending = [item for item in plan.actions if item.id not in results]
        while pending:
            progress = False
            for action in list(pending):
                blocked = [
                    dependency for dependency in action.depends_on
                    if dependency in results
                    and results[dependency].status is not ActionExecutionStatus.APPLIED
                ]
                if not blocked:
                    continue
                results[action.id] = ActionApplicationResult(
                    action_id=action.id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(sorted(blocked)),
                )
                pending.remove(action)
                progress = True

            ready = [
                action for action in pending
                if all(
                    dependency in results
                    and results[dependency].status is ActionExecutionStatus.APPLIED
                    for dependency in action.depends_on
                )
            ]
            if ready:
                first = ready[0]
                batch = [
                    item for item in ready
                    if item.phase == first.phase and item.device_id == first.device_id
                ]
                mutations = self._safe_apply(batch)
                for action in batch:
                    mutation = mutations.get(action.id)
                    applied = bool(mutation and mutation.applied)
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=(
                            ActionExecutionStatus.APPLIED
                            if applied else ActionExecutionStatus.FAILED
                        ),
                        failure_code=(
                            ConfigurationFailureCode.NONE
                            if applied else mutation.failure_code
                            if mutation
                            and mutation.failure_code is not ConfigurationFailureCode.NONE
                            else ConfigurationFailureCode.APPLICATION_FAILED
                        ),
                        message=(
                            mutation.message
                            if mutation else "Runtime returned no mutation result."
                        ),
                        batch_id=mutation.batch_id if mutation else "",
                    )
                    pending.remove(action)
                progress = True
            if not progress:
                for action in pending:
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message="No executable dependency frontier remained.",
                    )
                break
        return [results[item.id] for item in plan.actions]

    def _safe_apply(
        self, actions: Sequence[ControlPlaneAction],
    ) -> dict[str, RuntimeActionMutation]:
        try:
            return {
                item.action_id: item for item in self._runtime.apply_actions(actions)
            }
        except Exception as exc:
            return {
                action.id: RuntimeActionMutation(
                    action_id=action.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.SESSION_FAILED,
                    message=str(exc),
                )
                for action in actions
            }

    def _verify_stage(
        self,
        plan: ControlPlanePlan,
        expectations: list[ControlPlaneVerificationExpectation],
        stage: ControlPlaneExecutionStage,
        actions: Mapping[str, ActionApplicationResult],
        profiles: Mapping[str, ControlPlaneCapabilityProfile],
    ) -> list[ControlPlaneVerificationResult]:
        actions_by_id = {item.id: item for item in plan.actions}
        immediate: dict[str, RuntimeControlPlaneVerification] = {}
        runnable: list[ControlPlaneVerificationExpectation] = []
        for expectation in expectations:
            blocked = [
                dependency for dependency in expectation.depends_on
                if dependency not in actions
                or actions[dependency].status is not ActionExecutionStatus.APPLIED
            ]
            if blocked:
                immediate[expectation.id] = RuntimeControlPlaneVerification(
                    expectation_id=expectation.id,
                    stage=stage,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(sorted(blocked)),
                )
                continue
            action = actions_by_id.get(expectation.action_id)
            support = self._capability_status(
                profiles,
                action.model if action else "",
                expectation.required_capability,
            )
            if support not in _RUNNABLE_CAPABILITIES:
                immediate[expectation.id] = RuntimeControlPlaneVerification(
                    expectation_id=expectation.id,
                    stage=stage,
                    status=ActionExecutionStatus.UNOBSERVABLE,
                    evidence_method="control_plane_capability_gate",
                    fields={"capability": FieldVerificationStatus.UNOBSERVABLE},
                    message=(
                        f"{action.model if action else 'unknown'}:"
                        f"{expectation.required_capability.value} is {support.value}."
                    ),
                )
                continue
            runnable.append(expectation)

        observed = self._safe_verify(runnable, stage)
        by_id = {**immediate, **{item.expectation_id: item for item in observed}}
        results: list[ControlPlaneVerificationResult] = []
        for expectation in expectations:
            item = by_id.get(expectation.id)
            if item is None:
                item = RuntimeControlPlaneVerification(
                    expectation_id=expectation.id,
                    stage=stage,
                    status=ActionExecutionStatus.UNKNOWN,
                    message="Runtime returned no verification result.",
                )
            results.append(self._verification_result(expectation, item, stage))
        return results

    def _safe_verify(self, expectations, stage):
        if not expectations:
            return []
        try:
            return self._runtime.verify(expectations)
        except Exception as exc:
            return [
                RuntimeControlPlaneVerification(
                    expectation_id=item.id,
                    stage=stage,
                    status=ActionExecutionStatus.FAILED,
                    message=str(exc),
                )
                for item in expectations
            ]

    def _unbound_failover_results(
        self,
        plan: ControlPlanePlan,
        actions: Mapping[str, ActionApplicationResult],
        profiles: Mapping[str, ControlPlaneCapabilityProfile],
        bound_expectation_ids: set[str],
    ) -> list[ControlPlaneVerificationResult]:
        actions_by_id = {item.id: item for item in plan.actions}
        results: list[ControlPlaneVerificationResult] = []
        for expectation in plan.verification_expectations:
            if (
                expectation.kind not in _SCENARIO_KINDS
                or expectation.id in bound_expectation_ids
            ):
                continue
            stage = (
                ControlPlaneExecutionStage.FAILOVER
                if expectation.kind
                is ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE
                else ControlPlaneExecutionStage.RESTORE
            )
            blocked = [
                dependency for dependency in expectation.depends_on
                if dependency not in actions
                or actions[dependency].status is not ActionExecutionStatus.APPLIED
            ]
            action = actions_by_id.get(expectation.action_id)
            support = self._capability_status(
                profiles,
                action.model if action else "",
                expectation.required_capability,
            )
            if blocked:
                runtime_result = RuntimeControlPlaneVerification(
                    expectation_id=expectation.id,
                    stage=stage,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(sorted(blocked)),
                )
            else:
                supported = support in _RUNNABLE_CAPABILITIES
                runtime_result = RuntimeControlPlaneVerification(
                    expectation_id=expectation.id,
                    stage=stage,
                    status=ActionExecutionStatus.UNOBSERVABLE,
                    evidence_method=(
                        "failure_scenario_binding_gate"
                        if supported else "control_plane_capability_gate"
                    ),
                    fields={"scenario": FieldVerificationStatus.UNOBSERVABLE},
                    message=(
                        "Failover expectation has no compiled typed failure scenario."
                        if supported else (
                            f"{action.model if action else 'unknown'}:"
                            f"{expectation.required_capability.value} is {support.value}."
                        )
                    ),
                )
            results.append(self._verification_result(
                expectation, runtime_result, stage,
            ))
        return results

    @staticmethod
    def _verification_result(expectation, item, stage):
        if item.stage is not stage:
            return ControlPlaneVerificationResult(
                expectation_id=expectation.id,
                action_id=expectation.action_id,
                kind=expectation.kind,
                stage=stage,
                status=ActionExecutionStatus.UNKNOWN,
                message=(
                    f"Runtime returned {item.stage.value} evidence for "
                    f"the {stage.value} stage."
                ),
            )
        return ControlPlaneVerificationResult(
            expectation_id=expectation.id,
            action_id=expectation.action_id,
            kind=expectation.kind,
            stage=stage,
            status=item.status,
            evidence_method=item.evidence_method,
            fresh_evidence=item.fresh_evidence,
            fields=item.fields,
            message=item.message,
            convergence=item.convergence,
        )

    def _execute_scenarios(self, plan, actions, inventory, profiles):
        expectations = {item.id: item for item in plan.verification_expectations}
        actions_by_id = {item.id: item for item in plan.actions}
        results: list[FailureScenarioResult] = []
        for scenario in plan.failure_scenarios:
            if not scenario.restore_required:
                results.append(FailureScenarioResult(
                    scenario_id=scenario.id,
                    status=ActionExecutionStatus.FAILED,
                    failure_code=ConfigurationFailureCode.CLEANUP_FAILED,
                    message="Failure scenarios require a mandatory inverse restore.",
                ))
                continue
            bound = [
                expectations[item]
                for item in scenario.verification_expectation_ids
                if item in expectations
            ]
            failure = next((
                item for item in bound
                if item.kind is ControlPlaneVerificationKind.LINK_FAILURE_CONVERGENCE
            ), None)
            recovery = next((
                item for item in bound
                if item.kind is ControlPlaneVerificationKind.RESTORE_RECOVERY
            ), None)
            if failure is None or recovery is None:
                results.append(FailureScenarioResult(
                    scenario_id=scenario.id,
                    status=ActionExecutionStatus.FAILED,
                    failure_code=ConfigurationFailureCode.VERIFICATION_FAILED,
                    message="Failure scenario lacks its failure or recovery expectation.",
                ))
                continue
            blocked = [
                dependency for dependency in failure.depends_on
                if dependency not in actions
                or actions[dependency].status is not ActionExecutionStatus.APPLIED
            ]
            if blocked:
                results.append(FailureScenarioResult(
                    scenario_id=scenario.id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(sorted(blocked)),
                ))
                continue
            target = inventory.get(scenario.target_device_name)
            fault_support = self._capability_status(
                profiles,
                target.model if target else "",
                ControlPlaneCapabilityDimension.LINK_FAILURE_CONTROL,
            )
            anchor = actions_by_id.get(failure.action_id)
            verification_support = self._capability_status(
                profiles,
                anchor.model if anchor else target.model if target else "",
                failure.required_capability,
            )
            recovery_anchor = actions_by_id.get(recovery.action_id)
            recovery_support = self._capability_status(
                profiles,
                recovery_anchor.model
                if recovery_anchor else target.model if target else "",
                recovery.required_capability,
            )
            if (
                fault_support is not SecurityCapabilityStatus.SUPPORTED
                or verification_support not in _RUNNABLE_CAPABILITIES
                or recovery_support not in _RUNNABLE_CAPABILITIES
            ):
                results.append(FailureScenarioResult(
                    scenario_id=scenario.id,
                    status=ActionExecutionStatus.UNOBSERVABLE,
                    failure_code=(
                        ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                        if SecurityCapabilityStatus.UNSUPPORTED in {
                            fault_support, verification_support, recovery_support,
                        }
                        else ConfigurationFailureCode.CAPABILITY_UNKNOWN
                    ),
                    message=(
                        "Failure control or failover verification capability is not supported."
                    ),
                ))
                continue
            try:
                runtime_result = self._runtime.execute_failure_scenario(
                    scenario, failure, recovery,
                )
            except Exception as exc:
                results.append(FailureScenarioResult(
                    scenario_id=scenario.id,
                    status=ActionExecutionStatus.FAILED,
                    failure_code=ConfigurationFailureCode.CLEANUP_FAILED,
                    restore_status=ActionExecutionStatus.UNKNOWN,
                    message=f"Failure scenario runtime raised: {exc}",
                ))
                continue
            results.append(self._scenario_result(
                scenario, failure, recovery, runtime_result,
            ))
        return results

    @staticmethod
    def _scenario_result(scenario, failure, recovery, runtime):
        if runtime.scenario_id != scenario.id:
            return FailureScenarioResult(
                scenario_id=scenario.id,
                status=ActionExecutionStatus.FAILED,
                failure_code=ConfigurationFailureCode.SESSION_FAILED,
                message="Runtime returned a result for a different failure scenario.",
            )
        baseline = (
            runtime.before.status if runtime.before else ActionExecutionStatus.UNKNOWN
        )
        injection = (
            ActionExecutionStatus.APPLIED
            if runtime.injection and runtime.injection.applied
            else ActionExecutionStatus.FAILED
            if runtime.injection else ActionExecutionStatus.UNKNOWN
        )
        failover = (
            runtime.during.status if runtime.during else ActionExecutionStatus.UNKNOWN
        )
        restore = (
            ActionExecutionStatus.APPLIED
            if runtime.restore and runtime.restore.applied
            else ActionExecutionStatus.FAILED
            if runtime.restore_attempted else ActionExecutionStatus.SKIPPED
        )
        recovery_status = (
            runtime.after.status if runtime.after else ActionExecutionStatus.UNKNOWN
        )
        contract_errors: list[str] = []
        for label, item, expectation_id, stage in (
            (
                "before", runtime.before, failure.id,
                ControlPlaneExecutionStage.BEHAVIOR,
            ),
            (
                "during", runtime.during, failure.id,
                ControlPlaneExecutionStage.FAILOVER,
            ),
            (
                "after", runtime.after, recovery.id,
                ControlPlaneExecutionStage.RESTORE,
            ),
        ):
            if item is None:
                continue
            if item.expectation_id != expectation_id or item.stage is not stage:
                contract_errors.append(label)
        if contract_errors:
            cleanup_failed = (
                runtime.injection is not None
                and runtime.injection.applied
                and not runtime.restore_attempted
            ) or (
                runtime.restore_attempted
                and restore is not ActionExecutionStatus.APPLIED
            )
            return FailureScenarioResult(
                scenario_id=scenario.id,
                status=ActionExecutionStatus.FAILED,
                failure_code=(
                    ConfigurationFailureCode.CLEANUP_FAILED
                    if cleanup_failed
                    else ConfigurationFailureCode.SESSION_FAILED
                ),
                baseline_status=baseline,
                injection_status=injection,
                failover_status=failover,
                restore_status=restore,
                recovery_status=recovery_status,
                restore_attempted=runtime.restore_attempted,
                before=runtime.before,
                during=runtime.during,
                after=runtime.after,
                message=(
                    "Runtime returned invalid scenario evidence for: "
                    + ", ".join(contract_errors) + "."
                ),
            )

        status = ActionExecutionStatus.VERIFIED
        code = ConfigurationFailureCode.NONE
        message = runtime.message
        if runtime.injection and runtime.injection.applied and not runtime.restore_attempted:
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.CLEANUP_FAILED
            message = "An applied fault was not followed by a restore attempt."
        elif runtime.restore_attempted and restore is not ActionExecutionStatus.APPLIED:
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.CLEANUP_FAILED
        elif runtime.injection is not None and injection is not ActionExecutionStatus.APPLIED:
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.APPLICATION_FAILED
        elif baseline is not ActionExecutionStatus.VERIFIED:
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.BEHAVIORAL_VERIFICATION_FAILED
        elif injection is not ActionExecutionStatus.APPLIED:
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.APPLICATION_FAILED
        elif failover is not ActionExecutionStatus.VERIFIED:
            status = ActionExecutionStatus.FAILED
            code = (
                ConfigurationFailureCode.CONVERGENCE_TIMEOUT
                if runtime.during and runtime.during.convergence
                else ConfigurationFailureCode.VERIFICATION_FAILED
            )
        elif recovery_status is not ActionExecutionStatus.VERIFIED:
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.VERIFICATION_FAILED
        return FailureScenarioResult(
            scenario_id=scenario.id,
            status=status,
            failure_code=code,
            baseline_status=baseline,
            injection_status=injection,
            failover_status=failover,
            restore_status=restore,
            recovery_status=recovery_status,
            restore_attempted=runtime.restore_attempted,
            before=runtime.before,
            during=runtime.during,
            after=runtime.after,
            message=message,
        )

    @staticmethod
    def _capability_status(profiles, model, dimension):
        profile = profiles.get(model)
        return (
            profile.status(dimension)
            if profile else SecurityCapabilityStatus.UNKNOWN
        )

    @staticmethod
    def _aggregate(statuses, success):
        if not statuses:
            return ActionExecutionStatus.SKIPPED
        if any(item is ActionExecutionStatus.FAILED for item in statuses):
            return ActionExecutionStatus.FAILED
        if all(item is success for item in statuses):
            return success
        for candidate in (
            ActionExecutionStatus.DEPENDENCY_BLOCKED,
            ActionExecutionStatus.UNKNOWN,
            ActionExecutionStatus.UNOBSERVABLE,
            ActionExecutionStatus.PARTIAL,
            ActionExecutionStatus.SKIPPED,
        ):
            if any(item is candidate for item in statuses):
                return candidate
        return ActionExecutionStatus.PARTIAL

    @staticmethod
    def _overall(actions, observed, behavior, failover, scenarios):
        for item in scenarios:
            if (
                item.status is ActionExecutionStatus.FAILED
                and item.failure_code is ConfigurationFailureCode.CLEANUP_FAILED
            ):
                return ConfigurationApplicationStatus.FAILED, item.failure_code
        if any(item.status is ActionExecutionStatus.FAILED for item in actions):
            return (
                ConfigurationApplicationStatus.FAILED,
                ConfigurationFailureCode.APPLICATION_FAILED,
            )
        failed_scenario = next((
            item for item in scenarios
            if item.status is ActionExecutionStatus.FAILED
        ), None)
        if failed_scenario:
            return ConfigurationApplicationStatus.FAILED, failed_scenario.failure_code
        evidence = [*observed, *behavior, *failover]
        if any(item.status is ActionExecutionStatus.FAILED for item in evidence):
            return (
                ConfigurationApplicationStatus.PARTIAL,
                ConfigurationFailureCode.VERIFICATION_FAILED,
            )
        incomplete = {
            ActionExecutionStatus.SKIPPED,
            ActionExecutionStatus.DEPENDENCY_BLOCKED,
            ActionExecutionStatus.UNKNOWN,
            ActionExecutionStatus.UNOBSERVABLE,
            ActionExecutionStatus.PARTIAL,
        }
        if any(item.status in incomplete for item in [*actions, *evidence, *scenarios]):
            return ConfigurationApplicationStatus.PARTIAL, ConfigurationFailureCode.NONE
        if evidence or scenarios:
            return ConfigurationApplicationStatus.VERIFIED, ConfigurationFailureCode.NONE
        if actions:
            return ConfigurationApplicationStatus.APPLIED, ConfigurationFailureCode.NONE
        return ConfigurationApplicationStatus.SKIPPED, ConfigurationFailureCode.NONE

    @staticmethod
    def _failure(
        plan,
        code,
        *messages,
        context,
        started,
    ):
        return ControlPlaneApplicationResult(
            control_plane_plan_id=plan.id,
            control_plane_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            source_configuration_hash=plan.source_configuration_hash,
            source_security_hash=plan.source_security_hash,
            runtime_context=context,
            status=ConfigurationApplicationStatus.FAILED,
            failure_code=code,
            configured_status=ActionExecutionStatus.COMPILED,
            preflight_errors=list(messages),
            duration_ms=int((monotonic() - started) * 1000),
        )
