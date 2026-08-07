"""Aplicación E5 con preflight, dependencias y verificación independiente."""

from __future__ import annotations

from collections.abc import Sequence
from time import monotonic
from typing import Protocol

from ...domain.enterprise.models.capabilities import CapabilityStatus, DeviceCapabilities
from ...domain.enterprise.models.configuration import (
    ConfigurationAction,
    ConfigurationPlan,
    ConfigureAccessPort,
    ConfigureRoutedInterface,
    ConfigureSubinterface,
    ConfigureTrunk,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
    VerificationExpectation,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
    VerificationResult,
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
from ...domain.enterprise.models.verification import (
    legacy_action_prerequisites,
    prerequisites_satisfied,
)
from ...domain.enterprise.services.configuration_dependencies import (
    ConfigurationDependencyError,
    order_configuration_actions,
)


class ConfigurationRuntime(Protocol):
    def inventory(self) -> list[RuntimeConfigurationTarget]: ...

    def apply_actions(
        self, actions: Sequence[ConfigurationAction],
    ) -> list[RuntimeActionMutation]: ...

    def verify(
        self, expectations: Sequence[VerificationExpectation],
    ) -> list[RuntimeVerification]: ...


class ConfigurationApplicator:
    """No planifica: ejecuta exactamente las acciones ya compiladas."""

    def __init__(self, runtime: ConfigurationRuntime) -> None:
        self._runtime = runtime

    def apply(
        self,
        plan: ConfigurationPlan,
        *,
        actual_source_topology_hash: str,
        capabilities: dict[str, DeviceCapabilities] | None = None,
        runtime_context: ConfigurationRuntimeContext | None = None,
        deployment_manifest: DeploymentManifest | None = None,
    ) -> ConfigurationApplicationResult:
        started = monotonic()
        runtime_context = runtime_context or ConfigurationRuntimeContext()
        if actual_source_topology_hash != plan.source_topology_hash:
            return self._preflight_failure(
                plan,
                ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH,
                "ConfigurationPlan source hash does not match the deployed E4 topology.",
                runtime_context=runtime_context,
                deployment_id=deployment_manifest.deployment_id if deployment_manifest else "",
                started=started,
            )
        if (
            deployment_manifest is not None
            and deployment_manifest.physical_topology_hash != plan.source_topology_hash
        ):
            return self._preflight_failure(
                plan,
                ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
                "DeploymentManifest physical topology hash does not match ConfigurationPlan.",
                runtime_context=runtime_context,
                deployment_id=deployment_manifest.deployment_id,
                started=started,
            )

        try:
            ordered = order_configuration_actions(plan.actions)
        except ConfigurationDependencyError as exc:
            return self._preflight_failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                str(exc),
                runtime_context=runtime_context,
                deployment_id=deployment_manifest.deployment_id if deployment_manifest else "",
                started=started,
            )
        if [action.id for action in ordered] != [action.id for action in plan.actions]:
            return self._preflight_failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                "ConfigurationPlan actions are not in deterministic dependency order.",
                runtime_context=runtime_context,
                deployment_id=deployment_manifest.deployment_id if deployment_manifest else "",
                started=started,
            )

        try:
            inventory = self._runtime.inventory()
        except Exception as exc:
            return self._preflight_failure(
                plan, ConfigurationFailureCode.SESSION_FAILED,
                f"Runtime inventory failed: {exc}", runtime_context=runtime_context,
                deployment_id=deployment_manifest.deployment_id if deployment_manifest else "",
                started=started,
            )
        if deployment_manifest is not None:
            try:
                semantic_targets = resolve_manifest_targets(
                    deployment_manifest,
                    physical_topology_hash=plan.source_topology_hash,
                    semantic_device_ids=[item.device_id for item in plan.devices],
                    inventory=inventory,
                )
            except DeploymentIdentityError as exc:
                return self._preflight_failure(
                    plan, ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH, str(exc),
                    runtime_context=runtime_context,
                    deployment_id=deployment_manifest.deployment_id,
                    started=started,
                )
            targets = {
                item.device_name: semantic_targets[item.device_id]
                for item in plan.devices
            }
        else:
            targets = {item.device_name: item for item in inventory}
        deployed_names = {
            item.device_id: targets[item.device_name].device_name
            for item in plan.devices
            if item.device_name in targets
        }
        preflight_errors = self._validate_targets(plan, targets)
        if preflight_errors:
            code = (
                ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
                if any("model" in message.casefold() for message in preflight_errors)
                else ConfigurationFailureCode.TARGET_NOT_FOUND
            )
            if any("interface" in message.casefold() for message in preflight_errors):
                code = ConfigurationFailureCode.INTERFACE_NOT_FOUND
            return self._preflight_failure(
                plan, code, *preflight_errors,
                runtime_context=runtime_context, started=started,
                deployment_id=deployment_manifest.deployment_id if deployment_manifest else "",
            )

        results: dict[str, ActionApplicationResult] = {}
        self._apply_capability_gates(plan, targets, capabilities, results)

        for phase in sorted({action.phase for action in plan.actions}):
            ready: list[ConfigurationAction] = []
            for action in (item for item in plan.actions if item.phase == phase):
                if action.id in results:
                    continue
                blocked = [
                    dependency for dependency in action.depends_on
                    if dependency not in results
                    or not satisfies_apply_dependency(results[dependency].status)
                ]
                if blocked:
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message="Blocked by: " + ", ".join(sorted(blocked)),
                    )
                    continue
                ready.append(action)
            if not ready:
                continue
            try:
                runtime_ready = [
                    item.model_copy(update={
                        "device_name": deployed_names.get(item.device_id, item.device_name),
                    })
                    for item in ready
                ]
                mutations = {
                    item.action_id: item for item in self._runtime.apply_actions(runtime_ready)
                }
            except Exception as exc:
                mutations = {
                    action.id: RuntimeActionMutation(
                        action_id=action.id, applied=False,
                        failure_code=ConfigurationFailureCode.SESSION_FAILED,
                        message=str(exc),
                    )
                    for action in ready
                }
            for action in ready:
                mutation = mutations.get(action.id)
                if mutation is None:
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=ActionExecutionStatus.FAILED,
                        failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                        message="Runtime returned no mutation result.",
                    )
                else:
                    disposition = mutation.disposition
                    status = self._mutation_status(mutation)
                    results[action.id] = ActionApplicationResult(
                        action_id=action.id,
                        status=status,
                        failure_code=(
                            ConfigurationFailureCode.NONE
                            if mutation.applied else mutation.failure_code
                            if mutation.failure_code is not ConfigurationFailureCode.NONE
                            else ConfigurationFailureCode.APPLICATION_FAILED
                        ),
                        message=mutation.message,
                        batch_id=mutation.batch_id,
                        operation=action.operation,
                        disposition=disposition,
                    )

        action_results = [results[action.id] for action in plan.actions]
        action_statuses = {item.action_id: item.status for item in action_results}
        ready_expectations: list[VerificationExpectation] = []
        blocked_verification: dict[str, VerificationResult] = {}
        for item in plan.verification_expectations:
            prerequisites = (
                item.verification_prerequisites
                or legacy_action_prerequisites([item.action_id])
            )
            satisfied, blocked = prerequisites_satisfied(
                prerequisites,
                action_statuses=action_statuses,
                verification_statuses={},
                resource_statuses={},
            )
            if satisfied:
                ready_expectations.append(item)
            else:
                blocked_verification[item.id] = VerificationResult(
                    expectation_id=item.id,
                    action_id=item.action_id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(blocked),
                )
        runtime_expectations = [
            item.model_copy(update={
                "device_name": deployed_names.get(item.device_id, item.device_name),
            })
            for item in ready_expectations
        ]
        observed_verification = {
            item.expectation_id: item
            for item in self._verify(plan, runtime_expectations)
        }
        verification_results = [
            blocked_verification.get(item.id) or observed_verification[item.id]
            for item in plan.verification_expectations
        ]
        status, failure_code = self._overall_status(action_results, verification_results)
        deployment_id = deployment_manifest.deployment_id if deployment_manifest else ""
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
                subject=expectations_by_id[item.expectation_id].device_id,
                claim=expectations_by_id[item.expectation_id].kind.value,
                status=item.status,
                evidence_method=item.evidence_method,
                fresh_evidence=item.fresh_evidence,
                observed_value={
                    name: value.value for name, value in sorted(item.fields.items())
                },
                backend=runtime_context.backend,
                backend_version=runtime_context.backend_version,
                environment_fingerprint=runtime_context.capability_snapshot_hash,
                limitations=[item.message] if item.message else [],
            )
            for item in verification_results
        ]
        return ConfigurationApplicationResult(
            config_plan_id=plan.id,
            config_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            runtime_context=runtime_context,
            status=status,
            failure_code=failure_code,
            action_results=action_results,
            verification_results=verification_results,
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

    @staticmethod
    def _validate_targets(
        plan: ConfigurationPlan,
        targets: dict[str, RuntimeConfigurationTarget],
    ) -> list[str]:
        errors: list[str] = []
        device_plans = {item.device_id: item for item in plan.devices}
        for device in plan.devices:
            target = targets.get(device.device_name)
            if target is None:
                errors.append(f"Target {device.device_name} was not found.")
            elif target.model.casefold() != device.model.casefold():
                errors.append(
                    f"Target {device.device_name} model {target.model} does not match {device.model}."
                )
        for action in plan.actions:
            target = targets.get(action.device_name)
            if target is None or not target.interfaces:
                continue
            interface = ConfigurationApplicator._physical_interface(action)
            if interface and interface.casefold() not in {
                item.casefold() for item in target.interfaces
            }:
                expected_model = device_plans[action.device_id].model
                errors.append(
                    f"Target {action.device_name} ({expected_model}) interface {interface} was not found."
                )
        return sorted(set(errors))

    @staticmethod
    def _physical_interface(action: ConfigurationAction) -> str:
        if isinstance(action, (ConfigureAccessPort, ConfigureTrunk, ConfigureRoutedInterface,
                               SetEndpointStaticAddress, SetEndpointDhcp)):
            return action.interface
        if isinstance(action, ConfigureSubinterface):
            return action.parent_interface
        return ""

    @staticmethod
    def _apply_capability_gates(
        plan: ConfigurationPlan,
        targets: dict[str, RuntimeConfigurationTarget],
        capabilities: dict[str, DeviceCapabilities] | None,
        results: dict[str, ActionApplicationResult],
    ) -> None:
        capabilities = capabilities or {}
        for action in plan.actions:
            if not action.required_capability or action.required_capability.startswith("endpoint_"):
                continue
            target = targets[action.device_name]
            profile = capabilities.get(target.model)
            status = (
                getattr(profile, action.required_capability, CapabilityStatus.UNKNOWN)
                if profile else CapabilityStatus.UNKNOWN
            )
            if status is CapabilityStatus.SUPPORTED:
                continue
            failure = (
                ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                if status is CapabilityStatus.UNSUPPORTED
                else ConfigurationFailureCode.CAPABILITY_UNKNOWN
            )
            results[action.id] = ActionApplicationResult(
                action_id=action.id,
                status=ActionExecutionStatus.SKIPPED,
                failure_code=failure,
                message=f"{action.required_capability} is {status.value} for {target.model}.",
            )

    def _verify(
        self,
        plan: ConfigurationPlan,
        expectations: list[VerificationExpectation],
    ) -> list[VerificationResult]:
        if not expectations:
            return []
        try:
            observed = {item.expectation_id: item for item in self._runtime.verify(expectations)}
        except Exception as exc:
            observed = {
                expectation.id: RuntimeVerification(
                    expectation_id=expectation.id,
                    status=ActionExecutionStatus.FAILED,
                    message=str(exc),
                )
                for expectation in expectations
            }
        results: list[VerificationResult] = []
        for expectation in expectations:
            item = observed.get(expectation.id)
            if item is None:
                results.append(VerificationResult(
                    expectation_id=expectation.id,
                    action_id=expectation.action_id,
                    status=ActionExecutionStatus.UNKNOWN,
                    message="Runtime returned no verification result.",
                ))
                continue
            results.append(VerificationResult(
                expectation_id=expectation.id,
                action_id=expectation.action_id,
                status=item.status,
                evidence_method=item.evidence_method,
                fresh_evidence=item.fresh_evidence,
                fields=item.fields,
                message=item.message,
                convergence=item.convergence,
            ))
        return results

    @staticmethod
    def _overall_status(
        actions: list[ActionApplicationResult],
        verification: list[VerificationResult],
    ) -> tuple[ConfigurationApplicationStatus, ConfigurationFailureCode]:
        if any(item.status is ActionExecutionStatus.FAILED for item in actions):
            return ConfigurationApplicationStatus.FAILED, ConfigurationFailureCode.APPLICATION_FAILED
        if any(item.status in {
            ActionExecutionStatus.SKIPPED, ActionExecutionStatus.DEPENDENCY_BLOCKED,
        } for item in actions):
            return ConfigurationApplicationStatus.PARTIAL, ConfigurationFailureCode.NONE
        if any(
            item.status is ActionExecutionStatus.UNOBSERVABLE
            for item in verification
        ) and not any(
            item.status is ActionExecutionStatus.FAILED
            for item in verification
        ):
            return (
                ConfigurationApplicationStatus.PARTIAL,
                ConfigurationFailureCode.OBSERVABILITY_LIMITATION,
            )
        if any(item.status is not ActionExecutionStatus.VERIFIED for item in verification):
            return ConfigurationApplicationStatus.PARTIAL, ConfigurationFailureCode.VERIFICATION_FAILED
        if verification:
            return ConfigurationApplicationStatus.VERIFIED, ConfigurationFailureCode.NONE
        if actions:
            return ConfigurationApplicationStatus.APPLIED, ConfigurationFailureCode.NONE
        return ConfigurationApplicationStatus.SKIPPED, ConfigurationFailureCode.NONE

    @staticmethod
    def _preflight_failure(
        plan: ConfigurationPlan,
        code: ConfigurationFailureCode,
        *messages: str,
        runtime_context: ConfigurationRuntimeContext,
        deployment_id: str = "",
        started: float,
    ) -> ConfigurationApplicationResult:
        journal = journal_from_action_results(
            plan_id=plan.id, deployment_id=deployment_id,
            actions=list(plan.actions), results=[],
        )
        for message in messages:
            journal.mark_preflight_failure(message)
        return ConfigurationApplicationResult(
            config_plan_id=plan.id,
            config_semantic_hash=plan.semantic_hash,
            source_topology_hash=plan.source_topology_hash,
            runtime_context=runtime_context,
            status=ConfigurationApplicationStatus.FAILED,
            failure_code=code,
            preflight_errors=list(messages),
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            duration_ms=int((monotonic() - started) * 1000),
        )
