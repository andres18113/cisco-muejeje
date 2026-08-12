"""Aplicación E9 offline con hashes, DAG, evidencia y escenarios separados."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from time import monotonic
from typing import Protocol

from ...domain.enterprise.models.configuration_runtime import (
    mutation_execution_status,
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
    requires_deployment_manifest,
    resolve_manifest_targets,
    validate_manifest_environment,
)
from ...infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
from ...domain.enterprise.models.execution import (
    CompensationStatus,
    DirtyState,
    MutationDisposition,
    journal_from_action_results,
    satisfies_apply_dependency,
)
from ...domain.enterprise.models.evidence import (
    EvidenceRecord,
    evidence_from_legacy_result,
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
    FailureTransitionPhase,
    RuntimeControlPlaneVerification,
    RuntimeFailureScenarioResult,
)
from ...domain.enterprise.models.security_plan import SecurityCapabilityStatus
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


def _profiles_in_environment_scope(
    profiles: Mapping[str, ControlPlaneCapabilityProfile],
    declared_version: str,
) -> Mapping[str, ControlPlaneCapabilityProfile]:
    """Aplica el alcance de la evidencia, no sólo lo registra.

    Reutiliza la regla que `capability_resolver._evidence_matches_version` ya
    fija para la evidencia de runtime/probe: sólo se reutiliza con versión
    EXACTA. Un perfil que no declara versión no afirma alcance y se conserva;
    uno que sí la declara queda fuera cuando el entorno declarado no coincide,
    incluido el caso en que el entorno no se declaró en absoluto.

    Quedar fuera significa que el modelo no tiene perfil, y el gate lo resuelve
    como UNKNOWN. Una versión desconocida nunca hereda SUPPORTED.
    """
    return {
        model: profile
        for model, profile in profiles.items()
        if profile.packet_tracer_version is None
        or profile.packet_tracer_version == declared_version
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

    def __init__(
        self,
        runtime: ControlPlaneRuntime,
        *,
        capability_provider: Callable[
            [], Mapping[str, ControlPlaneCapabilityProfile]
        ] | None = None,
    ) -> None:
        self._runtime = runtime
        # El producto resuelve capacidades desde el catálogo de evidencia viva.
        # Antes el valor por defecto era "ninguna evidencia", asi que toda
        # accion tipada de control plane quedaba en CAPABILITY_UNKNOWN y nadie
        # podia ejecutarla sin inyectar un perfil de test.
        self._capability_provider = (
            capability_provider or packet_tracer_control_plane_capabilities
        )

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
        deployment_manifest: DeploymentManifest | None = None,
    ) -> ControlPlaneApplicationResult:
        started = monotonic()
        context = runtime_context or ConfigurationRuntimeContext()
        deployment_id = deployment_manifest.deployment_id if deployment_manifest else ""
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
                deployment_id=deployment_id,
            )
        if (
            deployment_manifest is not None
            and deployment_manifest.physical_topology_hash != plan.source_topology_hash
        ):
            return self._failure(
                plan,
                ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
                "DeploymentManifest physical topology hash does not match ControlPlanePlan.",
                context=context,
                started=started,
                deployment_id=deployment_id,
            )
        if (
            deployment_manifest is None
            and requires_deployment_manifest(plan.source_topology_hash_schema)
        ):
            return self._failure(
                plan,
                ConfigurationFailureCode.DEPLOYMENT_MANIFEST_REQUIRED,
                "ControlPlanePlan uses physical-topology-v2 identity and requires a "
                "DeploymentManifest; name-only runtime fallback is legacy-only.",
                context=context,
                started=started,
                deployment_id=deployment_id,
            )
        if deployment_manifest is not None:
            try:
                validate_manifest_environment(
                    deployment_manifest,
                    context.environment_fingerprint,
                )
            except DeploymentIdentityError as exc:
                return self._failure(
                    plan,
                    ConfigurationFailureCode.ENVIRONMENT_FINGERPRINT_MISMATCH,
                    str(exc),
                    context=context,
                    started=started,
                    deployment_id=deployment_id,
                )

        try:
            ordered = order_dependency_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._failure(
                plan, ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                str(exc), context=context, started=started,
                deployment_id=deployment_id,
            )
        if [item.id for item in ordered] != [item.id for item in plan.actions]:
            return self._failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "ControlPlanePlan actions are not in deterministic dependency order.",
                context=context,
                started=started,
                deployment_id=deployment_id,
            )
        try:
            verification_plan = self._normalized_verification_plan(plan)
        except VerificationDependencyError as exc:
            return self._failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                str(exc),
                context=context,
                started=started,
                deployment_id=deployment_id,
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
                deployment_id=deployment_id,
            )

        try:
            inventory_items = self._runtime.inventory()
        except Exception as exc:
            return self._failure(
                plan, ConfigurationFailureCode.SESSION_FAILED,
                f"Control-plane runtime inventory failed: {exc}",
                context=context, started=started,
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
                    context=context,
                    started=started,
                    deployment_id=deployment_id,
                )
        inventory = {item.device_name: item for item in inventory_items}
        target_errors = self._target_errors(runtime_plan, inventory)
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
                deployment_id=deployment_id,
            )

        # `None` significa "resuelve la evidencia autoritativa". Un mapping
        # explicito, incluido `{}`, se respeta tal cual: los tests que quieren
        # aislar el gate siguen pudiendo declarar ausencia de evidencia.
        profiles = _profiles_in_environment_scope(
            capabilities if capabilities is not None else self._capability_provider(),
            context.evidence_backend_version,
        )
        action_results = self._apply_actions(runtime_plan, profiles)
        by_action = {item.action_id: item for item in action_results}
        verification_statuses: dict[str, ActionExecutionStatus] = {}
        observed_results = self._verify_stage(
            runtime_plan,
            [
                item for item in runtime_plan.verification_expectations
                if item.kind in _OBSERVED_KINDS
            ],
            ControlPlaneExecutionStage.OBSERVED,
            by_action,
            profiles,
            verification_statuses=verification_statuses,
            resource_statuses=dict(foundational_statuses),
        )
        verification_statuses.update({
            item.expectation_id: item.status for item in observed_results
        })
        behavior_results = self._verify_stage(
            runtime_plan,
            [
                item for item in runtime_plan.verification_expectations
                if item.kind in _BEHAVIOR_KINDS
            ],
            ControlPlaneExecutionStage.BEHAVIOR,
            by_action,
            profiles,
            verification_statuses=verification_statuses,
            resource_statuses=dict(foundational_statuses),
        )
        verification_statuses.update({
            item.expectation_id: item.status for item in behavior_results
        })
        bound_scenario_expectations = {
            expectation_id
            for scenario in runtime_plan.failure_scenarios
            for expectation_id in scenario.verification_expectation_ids
        }
        failover_results = self._unbound_failover_results(
            runtime_plan, by_action, profiles, bound_scenario_expectations,
            verification_statuses, dict(foundational_statuses),
        )
        verification_statuses.update({
            item.expectation_id: item.status for item in failover_results
        })
        scenario_results = self._execute_scenarios(
            runtime_plan, by_action, inventory, profiles,
            verification_statuses, dict(foundational_statuses),
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
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=action_results,
        )
        self._record_scenario_restore(journal, scenario_results)
        evidence_records = self._evidence_records(
            runtime_plan,
            [*observed_results, *behavior_results, *failover_results],
            scenario_results,
            context,
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
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            evidence_records=evidence_records,
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
    def _normalized_verification_plan(plan: ControlPlanePlan) -> ControlPlanePlan:
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
    def _semantic_device_ids(plan: ControlPlanePlan) -> list[str]:
        identifiers = {item.device_id for item in plan.actions if item.device_id}
        for expectation in plan.verification_expectations:
            if expectation.device_id:
                identifiers.add(expectation.device_id)
            if expectation.peer_device_id:
                identifiers.add(expectation.peer_device_id)
        for scenario in plan.failure_scenarios:
            identifiers.update(filter(None, (
                scenario.device_a_id,
                scenario.device_b_id,
                scenario.target_device_id,
                scenario.peer_device_id,
                scenario.probe_source_device_id,
                scenario.probe_destination_device_id,
            )))
        return sorted(identifiers)

    @staticmethod
    def _runtime_plan(
        plan: ControlPlanePlan,
        deployed_names: dict[str, str],
    ) -> ControlPlanePlan:
        def resolve(identifier: str, label: str) -> str:
            if not identifier:
                raise DeploymentIdentityError(f"{label} has no semantic device ID.")
            try:
                return deployed_names[identifier]
            except KeyError as exc:
                raise DeploymentIdentityError(
                    f"DeploymentManifest has no resolved target for {identifier!r}."
                ) from exc

        actions = [
            item.model_copy(update={
                "device_name": resolve(
                    item.device_id, f"Control-plane action {item.id}",
                ),
            })
            for item in plan.actions
        ]
        expectations = []
        for item in plan.verification_expectations:
            expected = dict(item.expected)
            if item.device_id:
                expected["source_device_name"] = resolve(
                    item.device_id, f"Control-plane expectation {item.id}",
                )
            expectations.append(item.model_copy(update={"expected": expected}))
        scenarios = [
            item.model_copy(update={
                "target_device_name": resolve(
                    item.target_device_id, f"Failure scenario {item.id} target",
                ),
                "peer_device_name": resolve(
                    item.peer_device_id, f"Failure scenario {item.id} peer",
                ),
                "probe_source_device_name": resolve(
                    item.probe_source_device_id,
                    f"Failure scenario {item.id} probe source",
                ),
                "probe_destination_device_name": resolve(
                    item.probe_destination_device_id,
                    f"Failure scenario {item.id} probe destination",
                ),
            })
            for item in plan.failure_scenarios
        ]
        return plan.model_copy(update={
            "actions": actions,
            "verification_expectations": expectations,
            "failure_scenarios": scenarios,
        })

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
                operation=action.operation,
                disposition=MutationDisposition.SKIPPED,
            )

        pending = [item for item in plan.actions if item.id not in results]
        while pending:
            progress = False
            for action in list(pending):
                blocked = [
                    dependency for dependency in action.depends_on
                    if dependency in results
                    and not satisfies_apply_dependency(results[dependency].status)
                ]
                if not blocked:
                    continue
                results[action.id] = ActionApplicationResult(
                    action_id=action.id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(sorted(blocked)),
                    operation=action.operation,
                    disposition=MutationDisposition.BLOCKED,
                )
                pending.remove(action)
                progress = True

            ready = [
                action for action in pending
                if all(
                    dependency in results
                    and satisfies_apply_dependency(results[dependency].status)
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
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=(
                            self._mutation_status(mutation)
                            if mutation else ActionExecutionStatus.FAILED
                        ),
                        failure_code=(
                            ConfigurationFailureCode.NONE
                            if mutation and mutation.applied else mutation.failure_code
                            if mutation
                            and mutation.failure_code is not ConfigurationFailureCode.NONE
                            else ConfigurationFailureCode.APPLICATION_FAILED
                        ),
                        message=(
                            mutation.message
                            if mutation else "Runtime returned no mutation result."
                        ),
                        batch_id=mutation.batch_id if mutation else "",
                        operation=action.operation,
                        disposition=(
                            mutation.disposition
                            if mutation else MutationDisposition.UNKNOWN
                        ),
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
                        operation=action.operation,
                        disposition=MutationDisposition.BLOCKED,
                    )
                break
        return [results[item.id] for item in plan.actions]

    @staticmethod
    def _mutation_status(mutation: RuntimeActionMutation) -> ActionExecutionStatus:
        # Una sola definicion, en el dominio: encolar no es aplicar.
        return mutation_execution_status(mutation)

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
        *,
        verification_statuses: Mapping[str, ActionExecutionStatus],
        resource_statuses: Mapping[str, ActionExecutionStatus],
    ) -> list[ControlPlaneVerificationResult]:
        actions_by_id = {item.id: item for item in plan.actions}
        action_statuses = {
            identifier: result.status for identifier, result in actions.items()
        }
        current_statuses = dict(verification_statuses)
        results: list[ControlPlaneVerificationResult] = []
        for expectation in expectations:
            satisfied, blocked = prerequisites_satisfied(
                expectation.verification_prerequisites,
                action_statuses=action_statuses,
                verification_statuses=current_statuses,
                resource_statuses=dict(resource_statuses),
            )
            if not satisfied:
                item = RuntimeControlPlaneVerification(
                    expectation_id=expectation.id,
                    stage=stage,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    evidence_method="verification_prerequisite_gate",
                    fields={"prerequisites": FieldVerificationStatus.UNOBSERVABLE},
                    message="Blocked by: " + ", ".join(blocked),
                )
            else:
                action = actions_by_id.get(expectation.action_id)
                support = self._capability_status(
                    profiles,
                    action.model if action else "",
                    expectation.required_capability,
                )
                if support not in _RUNNABLE_CAPABILITIES:
                    item = RuntimeControlPlaneVerification(
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
                else:
                    observed = self._safe_verify([expectation], stage)
                    item = observed[0] if observed else RuntimeControlPlaneVerification(
                        expectation_id=expectation.id,
                        stage=stage,
                        status=ActionExecutionStatus.UNKNOWN,
                        message="Runtime returned no verification result.",
                    )
            results.append(self._verification_result(expectation, item, stage))
            current_statuses[expectation.id] = results[-1].status
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
        verification_statuses: Mapping[str, ActionExecutionStatus],
        resource_statuses: Mapping[str, ActionExecutionStatus],
    ) -> list[ControlPlaneVerificationResult]:
        actions_by_id = {item.id: item for item in plan.actions}
        action_statuses = {
            identifier: result.status for identifier, result in actions.items()
        }
        current_statuses = dict(verification_statuses)
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
            satisfied, blocked = prerequisites_satisfied(
                expectation.verification_prerequisites,
                action_statuses=action_statuses,
                verification_statuses=current_statuses,
                resource_statuses=dict(resource_statuses),
            )
            action = actions_by_id.get(expectation.action_id)
            support = self._capability_status(
                profiles,
                action.model if action else "",
                expectation.required_capability,
            )
            if not satisfied:
                runtime_result = RuntimeControlPlaneVerification(
                    expectation_id=expectation.id,
                    stage=stage,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    evidence_method="verification_prerequisite_gate",
                    fields={"prerequisites": FieldVerificationStatus.UNOBSERVABLE},
                    message="Blocked by: " + ", ".join(blocked),
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
            current_statuses[expectation.id] = results[-1].status
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

    @staticmethod
    def _evidence_records(
        plan: ControlPlanePlan,
        verification: Sequence[ControlPlaneVerificationResult],
        scenarios: Sequence[FailureScenarioResult],
        context: ConfigurationRuntimeContext,
    ) -> list[EvidenceRecord]:
        expectations = {
            item.id: item for item in plan.verification_expectations
        }
        actions = {item.id: item for item in plan.actions}
        scenario_plans = {item.id: item for item in plan.failure_scenarios}
        records = []
        for item in verification:
            expectation = expectations[item.expectation_id]
            action = actions.get(expectation.action_id)
            subject = expectation.device_id or (
                action.device_id if action else expectation.action_id
            )
            records.append(evidence_from_legacy_result(
                identifier=(
                    f"evidence/control-plane/{item.expectation_id}/{item.stage.value}"
                ),
                subject=subject,
                claim=f"{item.kind.value}:{item.stage.value}",
                status=item.status,
                evidence_method=item.evidence_method,
                fresh_evidence=item.fresh_evidence,
                observed_value={
                    "stage": item.stage.value,
                    "fields": {
                        name: value.value
                        for name, value in sorted(item.fields.items())
                    },
                    "convergence": (
                        item.convergence.model_dump(mode="json")
                        if item.convergence else None
                    ),
                },
                backend=context.evidence_backend,
                backend_version=context.evidence_backend_version,
                environment_fingerprint=context.environment_semantic_hash,
                capability_snapshot_hash=context.capability_snapshot_hash,
                limitations=[item.message] if item.message else [],
            ))
        for scenario in scenarios:
            scenario_plan = scenario_plans.get(scenario.scenario_id)
            subject = (
                scenario_plan.probe_source_device_id
                if scenario_plan else scenario.scenario_id
            )
            runtime_stages = [
                item for item in (scenario.before, scenario.during, scenario.after)
                if item is not None
            ]
            for item in runtime_stages:
                expectation = expectations.get(item.expectation_id)
                records.append(evidence_from_legacy_result(
                    identifier=(
                        f"evidence/control-plane/{item.expectation_id}/{item.stage.value}"
                    ),
                    subject=(expectation.device_id if expectation else subject),
                    claim=(
                        f"{expectation.kind.value}:{item.stage.value}"
                        if expectation else f"failure_scenario:{item.stage.value}"
                    ),
                    status=item.status,
                    evidence_method=(
                        item.evidence_method or "behavioral_failure_scenario"
                    ),
                    fresh_evidence=item.fresh_evidence,
                    observed_value={
                        "scenario_id": scenario.scenario_id,
                        "stage": item.stage.value,
                        "fields": {
                            name: value.value
                            for name, value in sorted(item.fields.items())
                        },
                        "convergence": (
                            item.convergence.model_dump(mode="json")
                            if item.convergence else None
                        ),
                    },
                    backend=context.evidence_backend,
                    backend_version=context.evidence_backend_version,
                    environment_fingerprint=context.environment_semantic_hash,
                    capability_snapshot_hash=context.capability_snapshot_hash,
                    limitations=[item.message] if item.message else [],
                ))
            records.append(evidence_from_legacy_result(
                identifier=f"evidence/control-plane/scenario/{scenario.scenario_id}",
                subject=subject,
                claim="failure_scenario:composed",
                status=scenario.status,
                evidence_method=(
                    "behavioral_failure_scenario" if runtime_stages else ""
                ),
                fresh_evidence=(
                    bool(runtime_stages)
                    and all(item.fresh_evidence for item in runtime_stages)
                ),
                observed_value={
                    "baseline": scenario.baseline_status.value,
                    "injection": scenario.injection_status.value,
                    "failover": scenario.failover_status.value,
                    "restore": scenario.restore_status.value,
                    "recovery": scenario.recovery_status.value,
                    "restore_attempted": scenario.restore_attempted,
                    "transitions": [
                        item.model_dump(mode="json")
                        for item in scenario.transitions
                    ],
                },
                backend=context.evidence_backend,
                backend_version=context.evidence_backend_version,
                environment_fingerprint=context.environment_semantic_hash,
                capability_snapshot_hash=context.capability_snapshot_hash,
                limitations=[scenario.message] if scenario.message else [],
            ))
        return records

    def _execute_scenarios(
        self,
        plan,
        actions,
        inventory,
        profiles,
        verification_statuses,
        resource_statuses,
    ):
        expectations = {item.id: item for item in plan.verification_expectations}
        actions_by_id = {item.id: item for item in plan.actions}
        action_statuses = {
            identifier: result.status for identifier, result in actions.items()
        }
        current_verification_statuses = dict(verification_statuses)
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
            satisfied, blocked = prerequisites_satisfied(
                failure.verification_prerequisites,
                action_statuses=action_statuses,
                verification_statuses=current_verification_statuses,
                resource_statuses=dict(resource_statuses),
            )
            if not satisfied:
                results.append(FailureScenarioResult(
                    scenario_id=scenario.id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(blocked),
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
            recovery_verification_statuses = dict(current_verification_statuses)
            if runtime_result.during is not None:
                recovery_verification_statuses[failure.id] = (
                    runtime_result.during.status
                )
            recovery_ready, recovery_blocked = prerequisites_satisfied(
                recovery.verification_prerequisites,
                action_statuses=action_statuses,
                verification_statuses=recovery_verification_statuses,
                resource_statuses=dict(resource_statuses),
            )
            if not recovery_ready:
                runtime_result = runtime_result.model_copy(update={
                    "after": RuntimeControlPlaneVerification(
                        expectation_id=recovery.id,
                        stage=ControlPlaneExecutionStage.RESTORE,
                        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        evidence_method="verification_prerequisite_gate",
                        fields={
                            "prerequisites": FieldVerificationStatus.UNOBSERVABLE,
                        },
                        message="Blocked by: " + ", ".join(recovery_blocked),
                    ),
                })
            scenario_result = self._scenario_result(
                scenario, failure, recovery, runtime_result,
            )
            results.append(scenario_result)
            current_verification_statuses[failure.id] = (
                scenario_result.failover_status
            )
            current_verification_statuses[recovery.id] = (
                scenario_result.recovery_status
            )
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
            ControlPlaneApplicator._mutation_status(runtime.injection)
            if runtime.injection
            else ActionExecutionStatus.UNKNOWN
        )
        failover = (
            runtime.during.status if runtime.during else ActionExecutionStatus.UNKNOWN
        )
        restore = (
            ControlPlaneApplicator._mutation_status(runtime.restore)
            if runtime.restore
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
        transitions = list(runtime.transitions)
        if transitions:
            sequences = [item.sequence for item in transitions]
            elapsed = [item.elapsed_ms for item in transitions]
            canonical = {
                phase: index
                for index, phase in enumerate((
                    FailureTransitionPhase.BASELINE_OBSERVED,
                    FailureTransitionPhase.FAULT_INJECTED,
                    FailureTransitionPhase.FAILOVER_OBSERVED,
                    FailureTransitionPhase.RESTORE_DISPATCHED,
                    FailureTransitionPhase.RECOVERY_OBSERVED,
                ))
            }
            phase_order = [canonical[item.phase] for item in transitions]
            if (
                sequences != list(range(len(transitions)))
                or elapsed != sorted(elapsed)
                or phase_order != sorted(set(phase_order))
            ):
                contract_errors.append("transitions")
        if contract_errors:
            cleanup_failed = (
                runtime.injection is not None
                and runtime.injection.applied
                and not runtime.restore_attempted
            ) or (
                runtime.restore_attempted
                and not satisfies_apply_dependency(restore)
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
                transitions=transitions,
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
        elif runtime.restore_attempted and not satisfies_apply_dependency(restore):
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.CLEANUP_FAILED
        elif runtime.injection is not None and not satisfies_apply_dependency(injection):
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.APPLICATION_FAILED
        elif baseline is not ActionExecutionStatus.VERIFIED:
            status = ActionExecutionStatus.FAILED
            code = ConfigurationFailureCode.BEHAVIORAL_VERIFICATION_FAILED
        elif not satisfies_apply_dependency(injection):
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
            transitions=transitions,
            message=message,
        )

    @staticmethod
    def _record_scenario_restore(journal, scenarios) -> None:
        uncertain_restore = any(
            item.failure_code is ConfigurationFailureCode.CLEANUP_FAILED
            and item.restore_status is ActionExecutionStatus.UNKNOWN
            for item in scenarios
        )
        if uncertain_restore:
            journal.mark_cleanup(CompensationStatus.UNKNOWN)
            return
        injected = [
            item for item in scenarios
            if satisfies_apply_dependency(item.injection_status)
        ]
        if not injected:
            return
        restored = all(
            item.restore_attempted
            and satisfies_apply_dependency(item.restore_status)
            for item in injected
        )
        if not restored:
            journal.mark_cleanup(CompensationStatus.FAILED)
            return
        restore_observed = all(
            item.recovery_status is ActionExecutionStatus.VERIFIED
            and item.failure_code is not ConfigurationFailureCode.SESSION_FAILED
            for item in injected
        )
        if not restore_observed:
            journal.mark_cleanup(CompensationStatus.UNKNOWN)
            return
        # El bypass que antes vivia aqui existia porque `mark_cleanup` limpiaba
        # sin evidencia: un restore de escenario no puede borrar la suciedad de
        # una aplicacion anterior. Esa proteccion ahora es del propio
        # `mark_cleanup`, que sólo limpia lo que la compensación puede probar,
        # así que la ruta vuelve a ser una sola.
        journal.mark_cleanup(CompensationStatus.SUCCEEDED)

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
        if success is ActionExecutionStatus.APPLIED and all(
            satisfies_apply_dependency(item) for item in statuses
        ):
            return ActionExecutionStatus.APPLIED
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
        deployment_id="",
    ):
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=[],
        )
        for message in messages:
            journal.mark_preflight_failure(message)
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
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            duration_ms=int((monotonic() - started) * 1000),
        )
