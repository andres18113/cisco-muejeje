"""Typed stage execution; the outer coordinator owns deployment and the session."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone

from ..use_cases.compose_cp_scale_canonical import (
    canonical_stage_configuration_mutation_ids,
    canonical_stage_control_plane_mutation_ids,
    canonical_stage_voice_mutation_ids,
)
from ..use_cases.foundational_evidence import derive_foundational_statuses
from ..use_cases.qualify_cp_scale_live import (
    CanonicalMutationSurfaceObservation, canonical_cp_scale_voice_evidence,
    canonical_stage_mutation_replay_audit,
)
from ...domain.enterprise.models.configuration import ConfigurationPhase
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus, ConfigurationApplicationStatus, ConfigurationRuntimeContext,
)
from ...domain.enterprise.models.physical_deployment import PhysicalDeploymentStatus
from .configuration_stage import CPScaleConfigurationStage
from .control_plane_stage import CPScaleControlPlaneStage
from .contracts import (
    CPScaleDiagnosticRecord, CPScaleDiagnosticRequest, CPScaleLiveStageResult,
    CPScaleMutationScope, CPScaleObservationRecord, CPScaleRealtimeWindow,
    CPScaleStageContinuity, CPScaleStageExecutionInput, CPScaleStageReport,
    CPScaleStageSecondaryFailure, CPScaleVoiceLifecycleEvent,
)
from .forwarding_stage import CPScaleForwardingStage
from .observation import CPScaleDiagnosticPort, CPScaleRequiredObservations
from .reconciliation import CPScaleReconciliation
from .voice_stage import CPScaleVoiceStage, realtime_boundary_error


class _StageStopped(RuntimeError):
    pass


def stage_mutation_scope(request: CPScaleStageExecutionInput) -> CPScaleMutationScope:
    previous = request.continuity.previous_projection
    current = request.projection
    if (previous is None) != (request.continuity.previous_configuration is None):
        raise _StageStopped("Previous canonical projection and configuration must be retained together.")
    configuration = (
        canonical_stage_configuration_mutation_ids(previous.configuration, current.configuration)
        if previous is not None else tuple(item.id for item in current.configuration.actions)
    )
    control = (
        canonical_stage_control_plane_mutation_ids(previous.control_plane, current.control_plane)
        if previous is not None else tuple(item.id for item in current.control_plane.actions)
    )
    previous_voice = getattr(previous, "voice", None)
    voice_plan = getattr(current, "voice", None)
    voice = (
        () if voice_plan is None
        else canonical_stage_voice_mutation_ids(previous_voice, voice_plan)
        if previous_voice is not None and previous_voice.actions
        else tuple(item.id for item in voice_plan.actions)
    )
    retained_control = tuple(sorted({item.id for item in current.control_plane.actions} - set(control)))
    retained_voice = tuple(sorted(
        ({item.id for item in voice_plan.actions} if voice_plan is not None else set()) - set(voice)
    ))
    control_facts = tuple(
        item for item in request.continuity.previous_control_plane_action_results
        if item.action_id in retained_control
    )
    if len(control_facts) != len(retained_control):
        raise _StageStopped(
            "Canonical control-plane delta lacks retained application facts "
            f"before {current.stage.value!r}."
        )
    voice_facts = tuple(
        item for item in request.continuity.previous_voice_action_results
        if item.action_id in retained_voice
    )
    if len(voice_facts) != len(retained_voice):
        raise _StageStopped(
            f"Canonical Voice delta lacks retained application facts before {current.stage.value!r}."
        )
    return CPScaleMutationScope(
        configuration, tuple(sorted({item.id for item in current.configuration.actions} - set(configuration))),
        control, retained_control, voice, retained_voice,
    )


class CPScaleStageExecutor:
    """One bounded invocation; no ownership, transport, lifecycle or persistence."""

    def __init__(
        self, *, configuration: CPScaleConfigurationStage, voice: CPScaleVoiceStage,
        control_plane: CPScaleControlPlaneStage, forwarding: CPScaleForwardingStage,
        reconciliation: CPScaleReconciliation, observations: CPScaleRequiredObservations,
        diagnostics: CPScaleDiagnosticPort,
    ) -> None:
        self.configuration = configuration
        self.voice = voice
        self.control_plane = control_plane
        self.forwarding = forwarding
        self.reconciliation = reconciliation
        self.observations = observations
        self.diagnostics = diagnostics

    def execute(self, request: CPScaleStageExecutionInput) -> CPScaleLiveStageResult:
        projection = request.projection
        deployment = request.deployment
        scope = None
        configuration = None
        configuration_accepted = False
        configuration_attempts = []
        configuration_report = None
        control = None
        voice = None
        replay_audit = None
        orientation = None
        manifest = None
        reconciled = None
        forwarded = None
        window = None
        canonical_voice = None
        canonical_voice_error = ""
        observations = list(request.network_boundaries)
        diagnostics = []
        secondary_failures = []
        lifecycle = []
        boundary = "physical_delta"
        failure = ""

        def observe(kind, payload, status="observed", error=""):
            record = CPScaleObservationRecord(
                kind, projection.stage, "required_stage_observation", status, payload, error,
            )
            observations.append(record)
            return record

        def record_lifecycle(event: str) -> None:
            lifecycle.append(CPScaleVoiceLifecycleEvent(
                event, len(lifecycle) + 1, time.monotonic_ns(), datetime.now(timezone.utc),
            ))

        def configuration_phase_observer(phase: int, action_ids: tuple[str, ...]) -> None:
            edge = {
                int(ConfigurationPhase.L2_DEFINITIONS): "after_l2_definitions",
                int(ConfigurationPhase.L2_INTERFACES): "after_l2_interfaces",
            }.get(phase)
            if edge is not None:
                payload = self.observations.network_state(projection, boundary=edge)
                observe("network_state", dict(payload, mutation_action_ids=list(action_ids)))

        try:
            scope = stage_mutation_scope(request)
            if deployment.status is not PhysicalDeploymentStatus.VERIFIED or deployment.manifest is None:
                raise _StageStopped(
                    f"Physical stage {projection.stage.value!r} was not VERIFIED: "
                    + "; ".join(deployment.errors)
                )
            observe("network_state", self.observations.network_state(projection, boundary="after_physical_delta"))
            continuity = request.continuity
            if (continuity.verified_serial_topology is None) != (continuity.verified_serial_manifest is None):
                raise _StageStopped("Verified serial topology and manifest must be provided together.")
            orientation = self.observations.serial_orientation(
                projection, deployment.manifest,
                continuity.verified_serial_topology, continuity.verified_serial_manifest,
            )
            if not orientation.verified or orientation.oriented_manifest is None:
                raise _StageStopped(
                    f"Serial orientation at {projection.stage.value!r} was not VERIFIED: "
                    + "; ".join(orientation.errors)
                )
            manifest = orientation.oriented_manifest
            voice_plan = getattr(projection, "voice", None)
            has_voice = bool(voice_plan is not None and voice_plan.actions)
            boundary = "configuration"
            configured = self.configuration.execute(
                request, manifest, scope.configuration,
                defer_voice_signal=bool(has_voice and scope.voice),
                configuration_phase_observer=configuration_phase_observer,
            )
            configuration = configured.configuration
            configuration_attempts.extend(configured.attempts)
            configuration_report = configured.report
            if configured.report.serial_interfaces is not None:
                observations.append(configured.report.serial_interfaces)
            configuration_accepted = configured.accepted
            if configured.error:
                raise _StageStopped(configured.error)

            boundary = "voice"
            statuses = derive_foundational_statuses(configuration_result=configuration, physical_result=deployment)
            barrier = getattr(configuration, "voice_signal_barrier", None)
            if (
                has_voice and barrier is not None
                and barrier.foundation_status is ActionExecutionStatus.VERIFIED
                and barrier.signal_status is ActionExecutionStatus.INTENDED
            ):
                record_lifecycle("DATA_ONLY_ACCESS_APPLIED")
                record_lifecycle("NETWORK_VERIFIED")
            elif has_voice and not scope.voice:
                record_lifecycle("NETWORK_VERIFIED")

            if has_voice:
                before = observe("voice_window_before", self.observations.voice_window_state())
                before_error = realtime_boundary_error(before.evidence, "before")
                window = CPScaleRealtimeWindow(before, failure_reason=before_error)
                if before_error:
                    raise _StageStopped(f"Voice at {projection.stage.value!r} was not attempted: " + before_error)
            observe("stp_realtime_before_voice", self.observations.stp(projection, edge="before"))

            def complete_voice_signal():
                nonlocal configuration, statuses, configuration_accepted
                configuration = self.configuration.applicator.complete_deferred_voice_signals(
                    projection.configuration, configuration, deployment_manifest=manifest,
                    lifecycle_observer=record_lifecycle, retained_state_only=not scope.voice,
                )
                configuration_attempts.append(configuration)
                completion_error = self.configuration.acceptance_policy(projection.configuration, configuration)
                configuration_accepted = not completion_error
                if completion_error:
                    raise RuntimeError(completion_error)
                statuses = derive_foundational_statuses(configuration_result=configuration, physical_result=deployment)
                return statuses

            voice = self.voice.apply(
                projection, composition=request.composition, configuration=configuration,
                statuses=statuses, context=ConfigurationRuntimeContext(environment_fingerprint=request.fingerprint),
                manifest=manifest, voice_mutation_ids=scope.voice,
                retained_voice_action_results=tuple(
                    item for item in continuity.previous_voice_action_results if item.action_id in scope.retained_voice
                ),
                complete_voice_signal=(
                    complete_voice_signal
                    if ((barrier is not None and barrier.signal_status is ActionExecutionStatus.INTENDED)
                        or (has_voice and not scope.voice)) else None
                ),
                lifecycle_observer=record_lifecycle,
            )
            observe("stp_realtime_after_voice", self.observations.stp(projection, edge="after"))
            if window is not None:
                after = observe("voice_window_after", self.observations.voice_window_state())
                after_error = realtime_boundary_error(after.evidence, "after")
                window = replace(window, after=after, verified=not after_error, failure_reason=after_error)
                if after_error:
                    raise _StageStopped(f"Voice at {projection.stage.value!r} is not interpretable: " + after_error)

            # Only two valid Realtime boundaries make this acquired E7 error
            # authoritative. Later reads enrich its evidence, never replace it.
            attributable_voice_failure = bool(voice.error and window is not None and window.verified)
            bindings = None
            try:
                bindings = self.observations.bindings(projection) if voice.staged else []
                observe("dhcp_server_bindings", {"bindings": bindings})
            except Exception as exc:
                if not attributable_voice_failure:
                    raise
                error = f"{type(exc).__name__}: {exc}"
                secondary_failures.append(CPScaleStageSecondaryFailure("bindings", error))
                observe("dhcp_server_bindings", {"bindings": None}, "failed", error)
            if voice.staged and bindings is not None:
                try:
                    if request.dhcp_statistics_target is not None and request.dhcp_statistics_baseline is not None:
                        exchange = self.observations.dhcp_exchange(
                            bindings, request.dhcp_statistics_target, request.dhcp_statistics_baseline,
                        )
                    else:
                        exchange = {
                            "baseline": request.dhcp_statistics_baseline.evidence if request.dhcp_statistics_baseline else None, "post": None,
                            "voice_binding_count": None, "delta_readable": False, "counters": None,
                            "control_counters": None, "scope_discriminated": False, "fork": "UNOBSERVABLE",
                            "failure_reason": "A unique voice DHCP statistics target or baseline was unavailable at this stage.",
                        }
                    observe("dhcp_voice_exchange", exchange)
                except Exception as exc:
                    if not attributable_voice_failure:
                        raise
                    error = f"{type(exc).__name__}: {exc}"
                    secondary_failures.append(CPScaleStageSecondaryFailure("statistics", error))
                    observe("dhcp_voice_exchange", {"fork": "UNOBSERVABLE", "failure_reason": error}, "failed", error)
            if voice.staged and voice_plan is not None and voice.result is not None and bindings is not None:
                try:
                    canonical_voice = canonical_cp_scale_voice_evidence(
                        stage=projection.stage.value, configuration_plan=projection.configuration,
                        configuration_result=configuration, voice_plan=voice_plan, voice_result=voice.result,
                        dhcp_server_bindings=bindings, lifecycle_events=[item.event for item in lifecycle],
                    )
                except Exception as exc:
                    canonical_voice_error = f"{type(exc).__name__}: {exc}"
                    if not attributable_voice_failure:
                        raise _StageStopped(
                            "Canonical Voice evidence could not be correlated: " + canonical_voice_error
                        ) from exc
                    secondary_failures.append(CPScaleStageSecondaryFailure("correlation", canonical_voice_error))
            if voice.error:
                try:
                    diagnostics.append(self.diagnostics.diagnose(CPScaleDiagnosticRequest(
                        projection, voice, realtime_failure_established=bool(window is not None and window.verified),
                    )))
                except Exception as exc:
                    diagnostics.append(CPScaleDiagnosticRecord(
                        projection.stage, {}, error=f"{type(exc).__name__}: {exc}",
                    ))
                raise _StageStopped(f"Voice at {projection.stage.value!r} did not close: " + voice.error)
            if canonical_voice is not None and not canonical_voice.complete:
                raise _StageStopped(
                    "Canonical Voice evidence failed closed at "
                    f"{canonical_voice.first_contradicted_boundary}; "
                    f"{len(canonical_voice.failed_phone_identities)} of "
                    f"{canonical_voice.expected_phone_count} phone identities "
                    "did not satisfy the exact correlated contract."
                )

            boundary = "control_plane"
            control = self.control_plane.execute(
                request, manifest, statuses, scope.control_plane,
                tuple(item for item in continuity.previous_control_plane_action_results
                      if item.action_id in scope.retained_control_plane),
            )
            if control.status is not ConfigurationApplicationStatus.VERIFIED:
                raise _StageStopped(
                    f"Control plane at {projection.stage.value!r} was not VERIFIED: "
                    f"{control.status.value}/{control.failure_code.value}"
                )
            replay_audit = canonical_stage_mutation_replay_audit(projection.stage.value, (
                CanonicalMutationSurfaceObservation(
                    surface="configuration", plan_action_ids=tuple(item.id for item in projection.configuration.actions),
                    authorized_mutation_ids=scope.configuration, results=tuple(configuration_attempts),
                ),
                CanonicalMutationSurfaceObservation(
                    surface="control-plane", plan_action_ids=tuple(item.id for item in projection.control_plane.actions),
                    authorized_mutation_ids=scope.control_plane, results=(control,),
                ),
                CanonicalMutationSurfaceObservation(
                    surface="voice", plan_action_ids=tuple(item.id for item in voice_plan.actions) if voice_plan else (),
                    authorized_mutation_ids=scope.voice, results=(voice.result,) if voice.result is not None else (),
                ),
            ))
            boundary = "forwarding"
            forwarded = self.forwarding.execute(request)
            if not forwarded.verified:
                raise _StageStopped(forwarded.error)
            boundary = "reconciliation"
            reconciled = self.reconciliation.execute(projection.topology)
            if not reconciled.verified:
                raise _StageStopped(
                    f"Canonical workspace reconciliation failed at {projection.stage.value!r}: "
                    + next(error for error in reconciled.errors if error)
                )
        except Exception as exc:
            failure = str(exc) if isinstance(exc, _StageStopped) else f"{type(exc).__name__}: {exc}"

        workspace = reconciled.second if reconciled is not None else None
        next_continuity = request.continuity
        if not failure:
            next_continuity = CPScaleStageContinuity(
                projection, configuration,
                tuple(voice.result.action_results) if voice and voice.result else (),
                tuple(control.action_results) if control else (),
                projection.topology, manifest, workspace,
            )
        return CPScaleLiveStageResult(
            stage=projection.stage, outcome="failed" if failure else "verified",
            projection=projection, deployment=deployment, delta_deployment=request.delta_deployment,
            manifest=manifest, workspace=workspace, configuration=configuration,
            configuration_accepted=configuration_accepted, configuration_attempts=tuple(configuration_attempts),
            control_plane=control, voice=voice.result if voice else None, replay_audit=replay_audit,
            orientation=orientation, required_observations=tuple(observations), diagnostics=tuple(diagnostics),
            first_failed_boundary=boundary if failure else None, failure=failure, continuity=next_continuity,
            secondary_failures=tuple(secondary_failures),
            report=CPScaleStageReport(
                scope, configuration_report, voice, tuple(lifecycle), window, canonical_voice,
                canonical_voice_error, forwarded,
                reconciled.first if reconciled else None, workspace,
                reconciled.verified if reconciled else None, request.site_forwarding_checks,
            ),
        )
