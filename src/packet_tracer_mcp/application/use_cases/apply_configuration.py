"""Aplicación E5 con preflight, dependencias y verificación independiente."""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from time import monotonic
from typing import Protocol

from ...domain.enterprise.models.capabilities import CapabilityStatus, DeviceCapabilities
from ...domain.enterprise.models.configuration import (
    ConfigurationAction,
    ConfigurationPlan,
    ConfigureAccessPort,
    ConfigureRoutedInterface,
    ConfigureSerialClock,
    ConfigureSubinterface,
    ConfigureTrunk,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
    VerificationExpectation,
    VerificationKind,
)
from ...domain.enterprise.models.configuration_runtime import (
    mutation_execution_status,
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
    VerificationResult,
    VoiceSignalBarrierResult,
)
from ...domain.enterprise.models.deployment import (
    DeploymentIdentityError,
    DeploymentManifest,
    requires_deployment_manifest,
    resolve_manifest_targets,
    validate_manifest_environment,
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

    def wait_for_voice_access_forwarding(
        self, expectations: Sequence[VerificationExpectation],
    ) -> list[RuntimeVerification]: ...


class ConfigurationApplicator:
    """No planifica: ejecuta exactamente las acciones ya compiladas."""

    def __init__(self, runtime: ConfigurationRuntime) -> None:
        self._runtime = runtime

    _VOICE_FOUNDATION_KINDS = frozenset({
        VerificationKind.VLAN,
        VerificationKind.TRUNK,
        VerificationKind.L3_INTERFACE,
        VerificationKind.DHCP_POOL,
    })

    def apply(
        self,
        plan: ConfigurationPlan,
        *,
        actual_source_topology_hash: str,
        capabilities: dict[str, DeviceCapabilities] | None = None,
        runtime_context: ConfigurationRuntimeContext | None = None,
        deployment_manifest: DeploymentManifest | None = None,
        defer_voice_signal_until_bootstrap: bool = False,
        mutation_action_ids: Collection[str] | None = None,
        retained_action_results: Sequence[ActionApplicationResult] = (),
        phase_observer: (
            Callable[[int, tuple[str, ...]], None] | None
        ) = None,
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
        if (
            deployment_manifest is None
            and requires_deployment_manifest(plan.source_topology_hash_schema)
        ):
            return self._preflight_failure(
                plan,
                ConfigurationFailureCode.DEPLOYMENT_MANIFEST_REQUIRED,
                "ConfigurationPlan uses physical-topology-v2 identity and requires a "
                "DeploymentManifest; name-only runtime fallback is legacy-only.",
                runtime_context=runtime_context,
                started=started,
            )
        if deployment_manifest is not None:
            try:
                validate_manifest_environment(
                    deployment_manifest,
                    runtime_context.environment_fingerprint,
                )
            except DeploymentIdentityError as exc:
                return self._preflight_failure(
                    plan,
                    ConfigurationFailureCode.ENVIRONMENT_FINGERPRINT_MISMATCH,
                    str(exc),
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

        (
            mutation_ids,
            retained_results,
            mutation_scope_errors,
        ) = self._mutation_scope(
            plan,
            mutation_action_ids=mutation_action_ids,
            retained_action_results=retained_action_results,
        )
        if mutation_scope_errors:
            return self._preflight_failure(
                plan,
                ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                *mutation_scope_errors,
                runtime_context=runtime_context,
                deployment_id=(
                    deployment_manifest.deployment_id
                    if deployment_manifest else ""
                ),
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
            try:
                for action in plan.actions:
                    if not isinstance(action, ConfigureSerialClock):
                        continue
                    if not action.source_link_id:
                        raise DeploymentIdentityError(
                            f"Serial clock action {action.id!r} has no source link identity."
                        )
                    deployment_manifest.resolve_serial_clock_target(
                        action.source_link_id,
                        action.device_id,
                        inventory,
                        observed_interface=action.interface,
                    )
            except DeploymentIdentityError as exc:
                return self._preflight_failure(
                    plan,
                    ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH,
                    str(exc),
                    runtime_context=runtime_context,
                    deployment_id=deployment_manifest.deployment_id,
                    started=started,
                )
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

        # El conjunto REQUERIDO del plan es UNA unidad de preflight. Si alguna
        # accion critica no esta autorizada, el plan no se aplica en parte:
        # mutar un device en vivo por una transaccion que ya se sabe
        # incompletable es exactamente lo que midio MEG-4 run 4, donde el reloj
        # serial llego al router mientras doce acciones requeridas ya estaban
        # resueltas UNKNOWN. `critical` es la distincion tipada que el modelo
        # declara; una accion NO critica sigue pudiendo saltarse.
        refusals = self._capability_refusals(
            plan,
            targets,
            capabilities,
            action_ids=mutation_ids,
        )
        blocked = self._unexecutable_closure(plan, refusals)
        required_blocked = sorted(
            (action for action in plan.actions if action.critical and action.id in blocked),
            key=lambda item: item.id,
        )
        if required_blocked:
            refused_status = {action.id: status for action, status, _model in refusals}
            refused_model = {action.id: model for action, _status, model in refusals}
            return self._preflight_failure(
                plan,
                (
                    ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                    if any(
                        status is CapabilityStatus.UNSUPPORTED
                        for status in refused_status.values()
                    )
                    else ConfigurationFailureCode.CAPABILITY_UNKNOWN
                ),
                *sorted({
                    (
                        f"{action.id} ({action.device_name}): required capability "
                        f"{action.required_capability} is "
                        f"{refused_status[action.id].value} for {refused_model[action.id]}."
                    )
                    if action.id in refused_status else (
                        f"{action.id} ({action.device_name}): required action depends on "
                        "a refused action and can never execute."
                    )
                    for action in required_blocked
                }),
                runtime_context=runtime_context,
                deployment_id=deployment_manifest.deployment_id if deployment_manifest else "",
                started=started,
            )

        deferred_voice_actions = {
            action.id: action
            for action in plan.actions
            if (
                action.id in mutation_ids
                and isinstance(action, ConfigureAccessPort)
                and action.voice_vlan_id is not None
            )
        }
        deferred_voice_ids = frozenset(deferred_voice_actions)
        results = dict(retained_results)
        self._capability_refusal_results(refusals, results)

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
            results.update(self._apply_ready_actions(
                ready,
                deployed_names,
                data_only_action_ids=deferred_voice_ids,
            ))
            if phase_observer is not None:
                phase_observer(
                    int(phase),
                    tuple(item.id for item in ready),
                )

        (
            action_results,
            verification_results,
            voice_signal_barrier,
        ) = self._verify_with_voice_signal_barrier(
            plan,
            results,
            deferred_voice_actions,
            deployed_names,
            defer_voice_signal_until_bootstrap=(
                defer_voice_signal_until_bootstrap
            ),
        )
        status, failure_code = self._overall_status(action_results, verification_results)
        if (
            voice_signal_barrier is not None
            and voice_signal_barrier.signal_status
            is ActionExecutionStatus.DEPENDENCY_BLOCKED
        ):
            failure_code = (
                ConfigurationFailureCode.OBSERVABILITY_LIMITATION
                if voice_signal_barrier.foundation_status
                is ActionExecutionStatus.UNOBSERVABLE
                else ConfigurationFailureCode.VERIFICATION_FAILED
            )
        deployment_id = deployment_manifest.deployment_id if deployment_manifest else ""
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=[
                item for item in action_results
                if item.action_id in mutation_ids
            ],
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
                backend=runtime_context.evidence_backend,
                backend_version=runtime_context.evidence_backend_version,
                environment_fingerprint=runtime_context.environment_semantic_hash,
                capability_snapshot_hash=runtime_context.capability_snapshot_hash,
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
            mutation_action_ids=[
                item.id for item in plan.actions if item.id in mutation_ids
            ],
            retained_action_ids=[
                item.id for item in plan.actions if item.id not in mutation_ids
            ],
            verification_results=verification_results,
            deployment_id=deployment_id,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            evidence_records=evidence_records,
            voice_signal_barrier=voice_signal_barrier,
            duration_ms=int((monotonic() - started) * 1000),
        )

    def complete_deferred_voice_signals(
        self,
        plan: ConfigurationPlan,
        application: ConfigurationApplicationResult,
        *,
        deployment_manifest: DeploymentManifest | None = None,
        lifecycle_observer: Callable[[str], None] | None = None,
    ) -> ConfigurationApplicationResult:
        """Dispatch and verify Voice VLANs after bootstrap has been applied."""
        started = monotonic()
        barrier = application.voice_signal_barrier
        if (
            application.config_plan_id != plan.id
            or application.config_semantic_hash != plan.semantic_hash
            or barrier is None
            or not barrier.required
            or barrier.foundation_status is not ActionExecutionStatus.VERIFIED
            or barrier.signal_status is not ActionExecutionStatus.INTENDED
        ):
            return self._voice_signal_completion_failure(
                application,
                "Configuration result is not a prepared deferred Voice signal.",
                started,
            )
        deferred_ids = frozenset(barrier.deferred_action_ids)
        deferred_actions = [
            item for item in plan.actions if item.id in deferred_ids
        ]
        if (
            len(deferred_actions) != len(deferred_ids)
            or any(
                not isinstance(item, ConfigureAccessPort)
                or item.voice_vlan_id is None
                for item in deferred_actions
            )
        ):
            return self._voice_signal_completion_failure(
                application,
                "Deferred Voice action identities do not match the plan.",
                started,
            )

        try:
            inventory = self._runtime.inventory()
            if deployment_manifest is not None:
                validate_manifest_environment(
                    deployment_manifest,
                    application.runtime_context.environment_fingerprint,
                )
                semantic_targets = resolve_manifest_targets(
                    deployment_manifest,
                    physical_topology_hash=plan.source_topology_hash,
                    semantic_device_ids=[
                        item.device_id for item in plan.devices
                    ],
                    inventory=inventory,
                )
                deployed_names = {
                    item.device_id: semantic_targets[item.device_id].device_name
                    for item in plan.devices
                }
            else:
                targets = {item.device_name: item for item in inventory}
                missing = [
                    item.device_name for item in plan.devices
                    if item.device_name not in targets
                ]
                if missing:
                    raise DeploymentIdentityError(
                        "Deferred Voice targets not found: "
                        + ", ".join(sorted(missing))
                    )
                deployed_names = {
                    item.device_id: targets[item.device_name].device_name
                    for item in plan.devices
                }
        except Exception as exc:
            return self._voice_signal_completion_failure(
                application,
                f"Deferred Voice target resolution failed: {exc}",
                started,
            )

        signal_by_id = self._apply_ready_actions(
            deferred_actions,
            deployed_names,
        )
        action_by_id = {
            item.action_id: item for item in application.action_results
        }
        action_by_id.update(signal_by_id)
        action_results = [
            action_by_id[item.id] for item in plan.actions
        ]
        voice_action_ids = {
            item.id for item in plan.actions
            if (
                isinstance(item, ConfigureAccessPort)
                and item.voice_vlan_id is not None
            )
        }
        expectations = [
            item for item in plan.verification_expectations
            if item.action_id in voice_action_ids
        ]
        runtime_expectations = [
            item.model_copy(update={
                "device_name": deployed_names.get(
                    item.device_id, item.device_name,
                ),
            })
            for item in expectations
        ]
        direct_by_id = {
            item.expectation_id: item
            for item in self._verify(plan, runtime_expectations)
        }
        if (
            lifecycle_observer is not None
            and signal_by_id
            and all(
                satisfies_apply_dependency(item.status)
                for item in signal_by_id.values()
            )
            and direct_by_id
            and all(
                item.status is ActionExecutionStatus.VERIFIED
                for item in direct_by_id.values()
            )
        ):
            lifecycle_observer("VOICE_SIGNAL_VERIFIED")
        try:
            wait_for_forwarding = getattr(
                self._runtime, "wait_for_voice_access_forwarding",
            )
            forwarding_raw = {
                item.expectation_id: item
                for item in wait_for_forwarding(runtime_expectations)
            }
        except Exception as exc:
            forwarding_raw = {
                item.id: RuntimeVerification(
                    expectation_id=item.id,
                    status=ActionExecutionStatus.UNOBSERVABLE,
                    message=(
                        "Voice access forwarding could not be observed: "
                        f"{exc}"
                    ),
                )
                for item in runtime_expectations
            }
        forwarding_results: list[VerificationResult] = []
        verified_by_id: dict[str, VerificationResult] = {}
        for expectation in runtime_expectations:
            observed = forwarding_raw.get(expectation.id)
            if observed is None:
                observed = RuntimeVerification(
                    expectation_id=expectation.id,
                    status=ActionExecutionStatus.UNOBSERVABLE,
                    message=(
                        "Runtime returned no Voice access forwarding result."
                    ),
                )
            forwarding = VerificationResult(
                expectation_id=expectation.id,
                action_id=expectation.action_id,
                status=observed.status,
                evidence_method=observed.evidence_method,
                fresh_evidence=observed.fresh_evidence,
                fields=observed.fields,
                message=observed.message,
                convergence=observed.convergence,
            )
            forwarding_results.append(forwarding)
            verified_by_id[expectation.id] = (
                self._merge_voice_signal_verification(
                    direct_by_id[expectation.id],
                    forwarding,
                )
            )
        if (
            lifecycle_observer is not None
            and forwarding_results
            and len(forwarding_results) == len(runtime_expectations)
            and len({
                item.expectation_id for item in forwarding_results
            }) == len(runtime_expectations)
            and all(
                item.status is ActionExecutionStatus.VERIFIED
                and item.fields.get("voice_forwarding")
                is FieldVerificationStatus.VERIFIED
                for item in forwarding_results
            )
        ):
            lifecycle_observer("PHONE_ACCESS_FWD_VERIFIED")
        verification_by_id = {
            item.expectation_id: item
            for item in application.verification_results
        }
        verification_by_id.update(verified_by_id)
        verification_results = [
            verification_by_id[item.id]
            for item in plan.verification_expectations
        ]
        signal_status = self._voice_signal_status(
            list(signal_by_id.values()),
            list(verified_by_id.values()),
            barrier.foundation_status,
        )
        completed_barrier = barrier.model_copy(update={
            "signal_results": list(signal_by_id.values()),
            "post_signal_convergence_results": forwarding_results,
            "signal_status": signal_status,
            "message": (
                "Voice bootstrap completed; the original typed access actions "
                "were dispatched and independently verified."
                if signal_status is ActionExecutionStatus.VERIFIED
                else "Deferred Voice signalling or verification failed."
            ),
        })
        status, failure_code = self._overall_status(
            action_results,
            verification_results,
        )
        deployment_id = application.deployment_id
        journal = journal_from_action_results(
            plan_id=plan.id,
            deployment_id=deployment_id,
            actions=list(plan.actions),
            results=[
                item for item in action_results
                if item.action_id in set(application.mutation_action_ids)
            ],
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
                    name: value.value
                    for name, value in sorted(item.fields.items())
                },
                backend=application.runtime_context.evidence_backend,
                backend_version=(
                    application.runtime_context.evidence_backend_version
                ),
                environment_fingerprint=(
                    application.runtime_context.environment_semantic_hash
                ),
                capability_snapshot_hash=(
                    application.runtime_context.capability_snapshot_hash
                ),
                limitations=[item.message] if item.message else [],
            )
            for item in verification_results
        ]
        return application.model_copy(update={
            "status": status,
            "failure_code": failure_code,
            "action_results": action_results,
            "verification_results": verification_results,
            "execution_journal": journal,
            "dirty_state": journal.dirty_state,
            "evidence_records": evidence_records,
            "voice_signal_barrier": completed_barrier,
            "duration_ms": (
                application.duration_ms
                + int((monotonic() - started) * 1000)
            ),
        })

    @staticmethod
    def _voice_signal_completion_failure(
        application: ConfigurationApplicationResult,
        message: str,
        started: float,
    ) -> ConfigurationApplicationResult:
        barrier = application.voice_signal_barrier
        if barrier is not None:
            barrier = barrier.model_copy(update={
                "signal_status": ActionExecutionStatus.FAILED,
                "message": message,
            })
        return application.model_copy(update={
            "status": ConfigurationApplicationStatus.FAILED,
            "failure_code": ConfigurationFailureCode.APPLICATION_FAILED,
            "preflight_errors": [*application.preflight_errors, message],
            "voice_signal_barrier": barrier,
            "duration_ms": (
                application.duration_ms
                + int((monotonic() - started) * 1000)
            ),
        })

    @staticmethod
    def _merge_voice_signal_verification(
        direct: VerificationResult,
        forwarding: VerificationResult,
    ) -> VerificationResult:
        forwarding_fields = dict(forwarding.fields)
        forwarding_fields.setdefault(
            "voice_forwarding",
            (
                FieldVerificationStatus.VERIFIED
                if forwarding.status is ActionExecutionStatus.VERIFIED
                else FieldVerificationStatus.FAILED
                if forwarding.status is ActionExecutionStatus.FAILED
                else FieldVerificationStatus.UNOBSERVABLE
            ),
        )
        if (
            direct.status is ActionExecutionStatus.FAILED
            or forwarding.status is ActionExecutionStatus.FAILED
        ):
            status = ActionExecutionStatus.FAILED
        elif (
            direct.status is ActionExecutionStatus.VERIFIED
            and forwarding.status is ActionExecutionStatus.VERIFIED
        ):
            status = ActionExecutionStatus.VERIFIED
        else:
            status = ActionExecutionStatus.PARTIAL
        return direct.model_copy(update={
            "status": status,
            "evidence_method": "+".join(filter(None, (
                direct.evidence_method,
                forwarding.evidence_method,
            ))),
            "fresh_evidence": (
                direct.fresh_evidence and forwarding.fresh_evidence
            ),
            "fields": {**direct.fields, **forwarding_fields},
            "message": " ".join(filter(None, (
                direct.message,
                forwarding.message,
            ))),
            "convergence": forwarding.convergence,
        })

    def _verify_with_voice_signal_barrier(
        self,
        plan: ConfigurationPlan,
        results: dict[str, ActionApplicationResult],
        deferred_voice_actions: dict[str, ConfigureAccessPort],
        deployed_names: dict[str, str],
        *,
        defer_voice_signal_until_bootstrap: bool,
    ) -> tuple[
        list[ActionApplicationResult],
        list[VerificationResult],
        VoiceSignalBarrierResult | None,
    ]:
        deferred_ids = frozenset(deferred_voice_actions)

        def verify_subset(
            expectations: list[VerificationExpectation],
            action_statuses: dict[str, ActionExecutionStatus],
        ) -> dict[str, VerificationResult]:
            ready: list[VerificationExpectation] = []
            settled: dict[str, VerificationResult] = {}
            for item in expectations:
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
                    ready.append(item)
                    continue
                settled[item.id] = VerificationResult(
                    expectation_id=item.id,
                    action_id=item.action_id,
                    status=ActionExecutionStatus.DEPENDENCY_BLOCKED,
                    message="Blocked by: " + ", ".join(blocked),
                )
            runtime_expectations = [
                item.model_copy(update={
                    "device_name": deployed_names.get(
                        item.device_id, item.device_name,
                    ),
                })
                for item in ready
            ]
            settled.update({
                item.expectation_id: item
                for item in self._verify(plan, runtime_expectations)
            })
            return settled

        initial_action_results = [
            results[action.id] for action in plan.actions
        ]
        initial_statuses = {
            item.action_id: item.status for item in initial_action_results
        }
        if not deferred_ids:
            observed = verify_subset(
                list(plan.verification_expectations),
                initial_statuses,
            )
            return (
                initial_action_results,
                [observed[item.id] for item in plan.verification_expectations],
                None,
            )

        preparation_results = [
            results[action.id] for action in plan.actions
            if action.id in deferred_ids
        ]
        pre_signal_expectations = [
            item for item in plan.verification_expectations
            if item.action_id not in deferred_ids
        ]
        pre_signal_results = verify_subset(
            pre_signal_expectations,
            initial_statuses,
        )
        foundation_expectations = [
            item for item in pre_signal_expectations
            if item.kind in self._VOICE_FOUNDATION_KINDS
        ]
        foundation_results = [
            pre_signal_results[item.id] for item in foundation_expectations
        ]
        foundation_status = self._voice_signal_foundation_status(
            preparation_results,
            foundation_expectations,
            foundation_results,
            list(pre_signal_results.values()),
        )

        signal_deferred = bool(
            defer_voice_signal_until_bootstrap
            and foundation_status is ActionExecutionStatus.VERIFIED
        )
        if signal_deferred:
            signal_results = {
                action_id: ActionApplicationResult(
                    action_id=action_id,
                    status=ActionExecutionStatus.PARTIAL,
                    message=(
                        "Data-only access preparation is applied; Voice VLAN "
                        "signalling is pending successful Voice bootstrap."
                    ),
                )
                for action_id in deferred_voice_actions
            }
        elif foundation_status is ActionExecutionStatus.VERIFIED:
            signal_results = self._apply_ready_actions(
                list(deferred_voice_actions.values()),
                deployed_names,
            )
        else:
            preparation_by_id = {
                item.action_id: item for item in preparation_results
            }
            signal_results = {
                action_id: (
                    ActionApplicationResult(
                        action_id=action_id,
                        status=ActionExecutionStatus.PARTIAL,
                        failure_code=ConfigurationFailureCode.DEPENDENCY_BLOCKED,
                        message=(
                            "The data-only access preparation was applied, but "
                            "Voice VLAN signalling requires VERIFIED VLAN, trunk "
                            "and L3 foundations; DHCP-pool UNOBSERVABLE is the "
                            "only admitted measured ceiling."
                        ),
                    )
                    if satisfies_apply_dependency(
                        preparation_by_id[action_id].status
                    )
                    else preparation_by_id[action_id]
                )
                for action_id in deferred_voice_actions
            }
        results.update(signal_results)

        final_action_results = [
            results[action.id] for action in plan.actions
        ]
        final_statuses = {
            item.action_id: item.status for item in final_action_results
        }
        post_signal_expectations = [
            item for item in plan.verification_expectations
            if item.action_id in deferred_ids
        ]
        if signal_deferred:
            post_signal_results = {
                item.id: VerificationResult(
                    expectation_id=item.id,
                    action_id=item.action_id,
                    status=ActionExecutionStatus.PARTIAL,
                    message=(
                        "Voice VLAN verification is pending successful Voice "
                        "bootstrap and deferred signal dispatch."
                    ),
                )
                for item in post_signal_expectations
            }
        else:
            post_signal_results = verify_subset(
                post_signal_expectations,
                final_statuses,
            )
        observed = {**pre_signal_results, **post_signal_results}
        verification_results = [
            observed[item.id] for item in plan.verification_expectations
        ]
        signal_status = (
            ActionExecutionStatus.INTENDED
            if signal_deferred
            else self._voice_signal_status(
                list(signal_results.values()),
                list(post_signal_results.values()),
                foundation_status,
            )
        )
        barrier = VoiceSignalBarrierResult(
            required=True,
            deferred_action_ids=sorted(deferred_ids),
            foundation_expectation_ids=[
                item.id for item in foundation_expectations
            ],
            preparation_results=preparation_results,
            foundation_verification_results=foundation_results,
            signal_results=list(signal_results.values()),
            foundation_status=foundation_status,
            signal_status=signal_status,
            message=(
                "Phone access ports were prepared without a Voice VLAN; "
                "signalling is pending Voice bootstrap."
                if signal_deferred
                else "Phone access ports were prepared without a Voice VLAN; "
                "the original typed actions were dispatched only after the "
                "network foundation verification barrier."
                if signal_status is ActionExecutionStatus.VERIFIED
                else "Voice VLAN signalling did not cross its verification barrier."
            ),
        )
        return final_action_results, verification_results, barrier

    @classmethod
    def _voice_signal_foundation_status(
        cls,
        preparation: list[ActionApplicationResult],
        expectations: list[VerificationExpectation],
        foundation: list[VerificationResult],
        all_pre_signal: list[VerificationResult],
    ) -> ActionExecutionStatus:
        if not preparation or any(
            not satisfies_apply_dependency(item.status)
            for item in preparation
        ):
            return ActionExecutionStatus.FAILED
        if not expectations or len(expectations) != len(foundation):
            return ActionExecutionStatus.UNOBSERVABLE
        by_id = {item.expectation_id: item for item in foundation}
        unresolved: list[ActionExecutionStatus] = []
        for expectation in expectations:
            status = by_id[expectation.id].status
            if (
                expectation.kind is VerificationKind.DHCP_POOL
                and status in {
                    ActionExecutionStatus.VERIFIED,
                    ActionExecutionStatus.UNOBSERVABLE,
                }
            ):
                continue
            if status is not ActionExecutionStatus.VERIFIED:
                unresolved.append(status)
        if any(
            item.status in {
                ActionExecutionStatus.FAILED,
                ActionExecutionStatus.UNKNOWN,
                ActionExecutionStatus.DEPENDENCY_BLOCKED,
                ActionExecutionStatus.SKIPPED,
            }
            for item in all_pre_signal
        ):
            return ActionExecutionStatus.FAILED
        if ActionExecutionStatus.FAILED in unresolved:
            return ActionExecutionStatus.FAILED
        for status in (
            ActionExecutionStatus.DEPENDENCY_BLOCKED,
            ActionExecutionStatus.UNKNOWN,
            ActionExecutionStatus.SKIPPED,
            ActionExecutionStatus.UNOBSERVABLE,
            ActionExecutionStatus.PARTIAL,
        ):
            if status in unresolved:
                return status
        if unresolved:
            return ActionExecutionStatus.UNKNOWN
        return ActionExecutionStatus.VERIFIED

    @staticmethod
    def _voice_signal_status(
        signal_results: list[ActionApplicationResult],
        verification_results: list[VerificationResult],
        foundation_status: ActionExecutionStatus,
    ) -> ActionExecutionStatus:
        if foundation_status is not ActionExecutionStatus.VERIFIED:
            return ActionExecutionStatus.DEPENDENCY_BLOCKED
        if not signal_results or any(
            not satisfies_apply_dependency(item.status)
            for item in signal_results
        ):
            return ActionExecutionStatus.FAILED
        if not verification_results:
            return ActionExecutionStatus.UNOBSERVABLE
        if all(
            item.status is ActionExecutionStatus.VERIFIED
            for item in verification_results
        ):
            return ActionExecutionStatus.VERIFIED
        if any(
            item.status is ActionExecutionStatus.FAILED
            for item in verification_results
        ):
            return ActionExecutionStatus.FAILED
        return ActionExecutionStatus.UNOBSERVABLE

    def _apply_ready_actions(
        self,
        actions: Sequence[ConfigurationAction],
        deployed_names: dict[str, str],
        *,
        data_only_action_ids: frozenset[str] = frozenset(),
    ) -> dict[str, ActionApplicationResult]:
        runtime_actions = []
        for item in actions:
            updates: dict[str, object] = {
                "device_name": deployed_names.get(
                    item.device_id, item.device_name,
                ),
            }
            if item.id in data_only_action_ids:
                updates["voice_vlan_id"] = None
            runtime_actions.append(item.model_copy(update=updates))
        try:
            mutations = {
                item.action_id: item
                for item in self._runtime.apply_actions(runtime_actions)
            }
        except Exception as exc:
            mutations = {
                action.id: RuntimeActionMutation(
                    action_id=action.id,
                    applied=False,
                    failure_code=ConfigurationFailureCode.SESSION_FAILED,
                    message=str(exc),
                )
                for action in actions
            }

        results: dict[str, ActionApplicationResult] = {}
        for action in actions:
            mutation = mutations.get(action.id)
            if mutation is None:
                results[action.id] = ActionApplicationResult(
                    action_id=action.id,
                    status=ActionExecutionStatus.FAILED,
                    failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                    message="Runtime returned no mutation result.",
                )
                continue
            results[action.id] = ActionApplicationResult(
                action_id=action.id,
                status=self._mutation_status(mutation),
                failure_code=(
                    ConfigurationFailureCode.NONE
                    if mutation.applied else mutation.failure_code
                    if mutation.failure_code
                    is not ConfigurationFailureCode.NONE
                    else ConfigurationFailureCode.APPLICATION_FAILED
                ),
                message=mutation.message,
                batch_id=mutation.batch_id,
                operation=action.operation,
                disposition=mutation.disposition,
            )
        return results

    @staticmethod
    def _mutation_status(mutation: RuntimeActionMutation) -> ActionExecutionStatus:
        # Una sola definicion, en el dominio: encolar no es aplicar.
        return mutation_execution_status(mutation)

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
    def _mutation_scope(
        plan: ConfigurationPlan,
        *,
        mutation_action_ids: Collection[str] | None,
        retained_action_results: Sequence[ActionApplicationResult],
    ) -> tuple[
        frozenset[str],
        dict[str, ActionApplicationResult],
        list[str],
    ]:
        """Validate one explicit mutation delta without weakening verification."""

        plan_ids = {item.id for item in plan.actions}
        if mutation_action_ids is None:
            if retained_action_results:
                return (
                    frozenset(),
                    {},
                    [
                        "Retained action results require an explicit mutation "
                        "action scope."
                    ],
                )
            return frozenset(plan_ids), {}, []

        mutation_ids = frozenset(mutation_action_ids)
        unknown = sorted(mutation_ids - plan_ids)
        retained_by_id = {
            item.action_id: item.model_copy(deep=True)
            for item in retained_action_results
        }
        errors: list[str] = []
        if unknown:
            errors.append(
                "Mutation scope contains actions outside the typed plan: "
                + ", ".join(unknown)
            )
        if len(retained_by_id) != len(retained_action_results):
            errors.append("Retained action results contain duplicate identities.")
        expected_retained = plan_ids - mutation_ids
        missing = sorted(expected_retained - set(retained_by_id))
        extra = sorted(set(retained_by_id) - expected_retained)
        if missing:
            errors.append(
                "Mutation scope lacks retained application results for: "
                + ", ".join(missing)
            )
        if extra:
            errors.append(
                "Retained application results are outside the retained scope: "
                + ", ".join(extra)
            )
        invalid = sorted(
            f"{identifier}:{retained_by_id[identifier].status.value}"
            for identifier in expected_retained & set(retained_by_id)
            if not satisfies_apply_dependency(retained_by_id[identifier].status)
        )
        if invalid:
            errors.append(
                "Retained actions were not previously applied: "
                + ", ".join(invalid)
            )
        reverse_dependencies = sorted(
            item.id
            for item in plan.actions
            if item.id in expected_retained
            and any(
                dependency in mutation_ids
                for dependency in [*item.depends_on, *item.apply_dependencies]
            )
        )
        if reverse_dependencies:
            errors.append(
                "Retained actions depend on newly mutated actions: "
                + ", ".join(reverse_dependencies)
            )
        return mutation_ids, retained_by_id, errors

    @staticmethod
    def _physical_interface(action: ConfigurationAction) -> str:
        if isinstance(action, (ConfigureAccessPort, ConfigureTrunk, ConfigureRoutedInterface,
                               SetEndpointStaticAddress, SetEndpointDhcp)):
            return action.interface
        if isinstance(action, ConfigureSubinterface):
            return action.parent_interface
        return ""

    @staticmethod
    def _capability_refusals(
        plan: ConfigurationPlan,
        targets: dict[str, RuntimeConfigurationTarget],
        capabilities: dict[str, DeviceCapabilities] | None,
        *,
        action_ids: Collection[str] | None = None,
    ) -> list[tuple[ConfigurationAction, CapabilityStatus, str]]:
        """Resuelve TODA capacidad requerida antes de que exista una mutacion.

        Las acciones con prefijo `endpoint_` quedan fuera por contrato: su
        autorizacion no es una capacidad de modelo. Las que no declaran
        requisito tampoco se evaluan aca -- no porque no tengan autorizacion,
        sino porque la suya es de otra clase y vive en su propia barrera, como
        el reloj serial, que se autoriza con evidencia de version exacta y un
        DCE observado y ligado al manifiesto.
        """
        capabilities = capabilities or {}
        selected = set(action_ids) if action_ids is not None else None
        refusals: list[tuple[ConfigurationAction, CapabilityStatus, str]] = []
        for action in plan.actions:
            if selected is not None and action.id not in selected:
                continue
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
            refusals.append((action, status, target.model))
        return refusals

    @staticmethod
    def _unexecutable_closure(
        plan: ConfigurationPlan,
        refusals: list[tuple[ConfigurationAction, CapabilityStatus, str]],
    ) -> set[str]:
        """Lo rechazado, mas todo lo que depende de ello, transitivamente.

        Saltarse una accion OPCIONAL es legitimo; dejar una REQUERIDA colgando
        de ella no lo es. `satisfies_apply_dependency` ya impide que la
        dependiente se ejecute, pero eso se descubre a mitad del lote, con
        mutaciones ya hechas. Se sabe antes, asi que se decide antes.

        Las acciones se compilan en orden de dependencia, de modo que una sola
        pasada hacia adelante alcanza el cierre completo.
        """
        blocked = {action.id for action, _status, _model in refusals}
        for action in plan.actions:
            if action.id in blocked:
                continue
            if any(dependency in blocked for dependency in action.depends_on):
                blocked.add(action.id)
        return blocked

    @staticmethod
    def _capability_refusal_results(
        refusals: list[tuple[ConfigurationAction, CapabilityStatus, str]],
        results: dict[str, ActionApplicationResult],
    ) -> None:
        for action, status, model in refusals:
            results[action.id] = ActionApplicationResult(
                action_id=action.id,
                status=ActionExecutionStatus.SKIPPED,
                failure_code=(
                    ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
                    if status is CapabilityStatus.UNSUPPORTED
                    else ConfigurationFailureCode.CAPABILITY_UNKNOWN
                ),
                message=f"{action.required_capability} is {status.value} for {model}.",
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
