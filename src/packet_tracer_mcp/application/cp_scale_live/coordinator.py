"""Persistent CP-SCALE orchestration over named, injected effect boundaries."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .backend import CPScaleBackendQualification
from .build_policy import CPScaleBuildPolicy, CPScalePhysicalStages
from .completion import CPScaleCompletion
from .checkpoint import CPScaleCheckpointDecision
from .contracts import CPScaleLiveRequest, CPScalePreflightOutcome, CPScaleStageContinuity, CPScaleStageExecutionInput
from .errors import CanonicalLiveFailure
from .lifecycle import finalize_session, report_terminal_errors
from .run_contracts import CPScaleRunReport, CPScaleFinalizationState, CPScaleBackendProgress, CPScaleLiveFinalResult, CPScaleRunOutcome, CPScaleStageProgress
from .run_ports import CPScalePreflightPort, CPScaleEvidencePort, CPScaleCheckpointPort, CPScaleStageExecutorPort, CPScalePresentationPort
from .session import CPScaleSessionPort, CPScaleRunObservationPort, CPScaleRuntimeResources
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStage, CPScaleCanonicalTarget
from ..use_cases.deploy_enterprise_topology import disposable_workspace_error
from ..use_cases.qualify_cp_scale_live import canonical_bridge_polling_error
from ...domain.enterprise.models.deployment import EnvironmentFingerprint


class CPScaleLiveCoordinator:
    def __init__(self, *, preflight: CPScalePreflightPort,
                 session_factory: Callable[[], CPScaleSessionPort], backend: CPScaleBackendQualification,
                 stage_factory: Callable[[CPScaleSessionPort, CPScaleRuntimeResources], CPScaleStageExecutorPort],
                 observations_factory: Callable[[CPScaleSessionPort], CPScaleRunObservationPort],
                 build: CPScaleBuildPolicy, checkpoint: CPScaleCheckpointPort,
                 persistence: CPScaleEvidencePort, completion: CPScaleCompletion,
                 presentation: CPScalePresentationPort, baseline_policy=disposable_workspace_error,
                 clock=lambda: datetime.now(timezone.utc)) -> None:
        self.preflight = preflight
        self.session_factory = session_factory
        self.backend = backend
        self.stage_factory = stage_factory
        self.observations_factory = observations_factory
        self.build = build
        self.checkpoint = checkpoint
        self.persistence = persistence
        self.completion = completion
        self.presentation = presentation
        self.baseline_policy = baseline_policy
        self.clock = clock

    def run(self, request: CPScaleLiveRequest) -> CPScaleLiveFinalResult:
        started_at = self.clock()
        run_identity = "canonical-cp-scale-voice-" + started_at.strftime("%Y%m%dT%H%M%S%fZ") + "-" + (request.expected_head[:12] or "unknown-head")
        preflight = self.preflight.inspect(request, run_identity=run_identity, started_at=started_at)
        report = CPScaleRunReport(preflight, run_identity, started_at, request.packet_tracer_version)
        if preflight.outcome is CPScalePreflightOutcome.REJECTED:
            report.hard_stop = " ".join(preflight.issues) or "Local preflight evidence is incomplete or inconsistent."
            self.persistence.write_progress(report)
            return CPScaleLiveFinalResult.from_report(CPScaleRunOutcome.REJECTED, report)
        if preflight.identity is None:
            report.hard_stop = "Local preflight did not produce a session identity."
            self.persistence.write_progress(report)
            return CPScaleLiveFinalResult.from_report(CPScaleRunOutcome.REJECTED, report)
        session = self.session_factory()  # Allocated before any acquisition.
        finalization = CPScaleFinalizationState()
        backend_progress = CPScaleBackendProgress()
        physical_stages = None
        observations = None
        settled = None
        terminal_event = None
        def execute_session() -> CPScaleRunOutcome:
            nonlocal physical_stages, observations, settled, terminal_event
            if not session.start():
                report.http_bridge = self.backend.polling_failure_status(session)
                raise CanonicalLiveFailure("Authenticated Packet Tracer HTTP bridge did not obtain fresh polling: " + canonical_bridge_polling_error(report.http_bridge))
            report.http_bridge = session.status()
            report.baseline = session.physical.observe_workspace()
            baseline_error = self.baseline_policy(report.baseline)
            if baseline_error:
                report.hard_stop = baseline_error
                self.persistence.write_progress(report)
                settled = CPScaleRunOutcome.REJECTED
                return settled
            observations = self.observations_factory(session)
            composition = self.backend.qualify(session, report, backend_progress)
            statistics_projection = self.build.statistics_projection(composition)
            statistics_target = observations.dhcp_target(statistics_projection)
            fingerprint = EnvironmentFingerprint(backend="packet_tracer", backend_version=request.packet_tracer_version,
                bridge_transport=session.channel, runtime_mode="live")
            physical_stages = CPScalePhysicalStages(self.build, session, self.persistence, observations, fingerprint)
            resources = session.acquire_runtimes()
            executor = self.stage_factory(session, resources)
            continuity = CPScaleStageContinuity()
            dhcp_baseline = None
            for stage in preflight.target.build_stages:
                projection = self.build.projection(composition, stage)
                deployment, delta, boundaries = physical_stages.prepare(projection, continuity, report)
                stage_request = CPScaleStageExecutionInput(projection, composition, deployment, delta, fingerprint,
                    request.packet_tracer_version, continuity,
                    statistics_target if stage is CPScaleCanonicalStage.FLOOR1 else None,
                    dhcp_baseline if stage is CPScaleCanonicalStage.FLOOR1 else None,
                    boundaries, projection.branch_forwarding_checks if (
                        preflight.target.target is CPScaleCanonicalTarget.ROUTER0_BRANCH
                        and stage is CPScaleCanonicalStage.ROUTER0_BRANCH) else ())
                result = executor.execute(stage_request)
                report.record_stage_failures(result)
                report.active_stage = replace(report.active_stage, result=result)
                if result.outcome == "failed":
                    raise CanonicalLiveFailure(result.failure)
                if stage is CPScaleCanonicalStage.ROUTER4_SWITCH10:
                    dhcp_baseline = observations.dhcp_baseline(statistics_target)
                    report.active_stage = replace(report.active_stage, dhcp_baseline=dhcp_baseline)
                report.stages += (report.active_stage,)
                report.active_stage = None
                report.live_devices = len(projection.topology.devices)
                report.live_links = len(projection.topology.links)
                if result.voice is None and projection.voice is not None and projection.voice.actions:
                    raise CanonicalLiveFailure(f"Verified stage {stage.value!r} did not retain its Voice application results.")
                if result.control_plane is None:
                    raise CanonicalLiveFailure(f"Verified stage {stage.value!r} did not retain its control-plane result.")
                continuity = CPScaleStageContinuity(projection, result.configuration,
                    tuple(result.voice.action_results) if result.voice else continuity.previous_voice_action_results,
                    tuple(result.control_plane.action_results),
                    projection.topology if stage is CPScaleCanonicalStage.ROUTING_CORE else continuity.verified_serial_topology,
                    result.manifest if stage is CPScaleCanonicalStage.ROUTING_CORE else continuity.verified_serial_manifest,
                    result.workspace)
                if stage is CPScaleCanonicalStage.ROUTING_CORE:
                    self.presentation.core_rematerialized()
                if preflight.target.target is CPScaleCanonicalTarget.ROUTER0_BRANCH and stage is preflight.target.terminal_stage:
                    terminal_event = self.completion.complete(report=report, state=finalization, session=session, composition=composition,
                        owned=physical_stages.state.owned, observations=observations, router0=True)
                    settled = CPScaleRunOutcome.COMPLETED
                    return settled
                self._continue(stage.value, report)
            assert preflight.target.run_remaining_reconciliation
            assert preflight.target.run_full_qualification
            remaining = physical_stages.remaining(composition, continuity, report)
            self._continue(CPScaleCanonicalStage.REMAINING.value, report)
            self.build.resume(session=session, report=report, continuity=continuity,
                topology=remaining.topology, stage="full-qualification", full=True)
            projection = self.build.full_projection(composition)
            observations.activate(projection)
            deployment = physical_stages.cumulative(projection, "cp-scale-canonical/full-qualification")
            result = executor.execute(CPScaleStageExecutionInput(projection, composition, deployment, None,
                fingerprint, request.packet_tracer_version, continuity))
            report.record_stage_failures(result)
            if result.outcome == "failed":
                # Legacy failure evidence lives in the stages journal. Keep
                # the original typed result there, not a success-only full slot.
                report.active_stage = CPScaleStageProgress(projection, deployment=deployment, result=result)
                raise CanonicalLiveFailure(result.failure)
            report.full_qualification = result
            report.live_devices = len(composition.topology.devices)
            report.live_links = len(composition.topology.links)
            command = self.checkpoint.decide("full-qualification", report, session_source_head=preflight.identity.source_head)
            terminal_event = self.completion.complete(report=report, state=finalization, session=session, composition=composition,
                owned=physical_stages.state.owned, observations=observations, command=command,
                retain_authorized=request.retain_on_full_verification)
            settled = CPScaleRunOutcome.COMPLETED
            return settled

        try:
            settled = execute_session()
        except Exception as exc:
            finalization.precleanup_archive = finalization.precleanup_archive or report.canonical_evidence_precleanup
            finalization.cleanup_attempted |= report.cleanup is not None
            finalization.cleanup_attestation_archived |= report.cleanup_attestation is not None
            report.failure = f"{type(exc).__name__}: {exc}"
            if report.active_stage is not None:
                report.stages += (replace(report.active_stage, failed=True,
                    failure_details=getattr(exc, "partial_stage", None)),)
                report.active_stage = None
            settled = CPScaleRunOutcome.FAILED

        finally:
            def prepare() -> None:
                self.completion.prepare_finalization(report=report, state=finalization, session=session,
                    composition=backend_progress.composition, owned=physical_stages.state.owned if physical_stages else frozenset(),
                    observations=observations)

            def report_errors(errors: tuple[str, ...]) -> None:
                report.finalization_errors = errors
                self.presentation.finalization_incomplete(report)

            final = finalize_session(prepare=prepare, write=lambda: self.persistence.write_progress(report),
                session=session, report=report_errors)
            report.finalization_errors = final.errors
            if (final.errors or report.secondary_failures) and settled is CPScaleRunOutcome.COMPLETED:
                settled = CPScaleRunOutcome.FAILED
        # A cancellation never reaches this point. Publication follows every
        # terminal obligation, including final write and the sole close.
        if settled is CPScaleRunOutcome.COMPLETED:
            try:
                self.presentation.terminal(terminal_event, report)
            except Exception as exc:
                settled = CPScaleRunOutcome.FAILED
                report.finalization_errors = report_terminal_errors(
                    (f"terminal_presentation: {type(exc).__name__}: {exc}",), report_errors)
        return CPScaleLiveFinalResult.from_report(settled, report)

    def _continue(self, stage: str, report: CPScaleRunReport) -> None:
        command = self.checkpoint.decide(stage, report, session_source_head=report.preflight.identity.source_head)
        if command is CPScaleCheckpointDecision.RETAIN:
            raise CanonicalLiveFailure("Retention is forbidden before full CP-SCALE qualification.")
