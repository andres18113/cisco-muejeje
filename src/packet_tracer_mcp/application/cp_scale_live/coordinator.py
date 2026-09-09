"""CP-SCALE coordination; only this owner replaces immutable run snapshots."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .backend import CPScaleBackendQualification
from .build_policy import CPScaleBuildPolicy, CPScalePhysicalStages
from .cleanup import attempted_device_ids
from .completion import CPScaleCompletion
from .checkpoint import CPScaleCheckpointDecision
from .contracts import CPScaleLiveRequest, CPScalePreflightOutcome, CPScaleStageExecutionInput, CPScaleStageContinuity, CPScaleLiveStageResult, CPScaleObservationRecord
from .errors import CanonicalLiveFailure
from .lifecycle import finalize_session, report_terminal_errors
from .run_contracts import (
    CPScaleRunReport, CPScaleLiveFinalResult, CPScaleRunOutcome, CPScaleStageProgress,
    CPScaleCapabilityQualification, CPScaleCleanupAttestation, CPScaleCleanupResult, stage_secondary_failures,
)
from .run_state import CPScaleQualificationState, CPScaleProgressState, CPScaleTerminalState, publication_snapshot
from .run_ports import CPScalePreflightPort, CPScaleEvidencePort, CPScaleCheckpointPort, CPScaleStageExecutorPort, CPScalePresentationPort
from .session import CPScaleSessionPort, CPScaleRunObservationPort, CPScaleRuntimeResources
from .sequence import execute_stage_sequence, StageStepResult
from .step_policy import CPScaleStepContinuity, canonical_step_decision, canonical_step_result_error, advance_canonical_continuity
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStage, CPScaleCanonicalTarget, CPScaleCanonicalStageProjection
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ..use_cases.deploy_enterprise_topology import disposable_workspace_error
from ..use_cases.qualify_cp_scale_live import CPScaleFinalDisposition, CPScaleEvidenceArchive
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.physical_deployment import PhysicalDeploymentResult
from ...domain.models.plans import TopologyPlan


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
        qualification = CPScaleQualificationState()
        progress = CPScaleProgressState()
        terminal = CPScaleTerminalState()

        def snapshot() -> CPScaleRunReport:
            return publication_snapshot(preflight, run_identity, started_at, request.packet_tracer_version,
                                        qualification, progress, terminal)

        def report_errors(errors: tuple[str, ...]) -> None:
            nonlocal terminal
            terminal = replace(terminal, secondary_failures=(), finalization_errors=errors)
            self.presentation.finalization_incomplete(snapshot())

        if preflight.outcome is CPScalePreflightOutcome.REJECTED:
            terminal = replace(terminal, hard_stop=" ".join(preflight.issues) or "Local preflight evidence is incomplete or inconsistent.")
        elif preflight.identity is None:
            terminal = replace(terminal, hard_stop="Local preflight did not produce a session identity.")
        if terminal.hard_stop:
            try:
                self.persistence.write_progress(snapshot())
            except Exception as exc:
                errors = report_terminal_errors((f"preflight_evidence_write: {type(exc).__name__}: {exc}",), report_errors)
                terminal = replace(terminal, finalization_errors=errors)
            return CPScaleLiveFinalResult.from_report(CPScaleRunOutcome.REJECTED, snapshot())

        session = self.session_factory()
        observations = None
        physical_stages = None

        def qualify_backend() -> EnterpriseReferenceComposition:
            nonlocal qualification
            version = request.packet_tracer_version
            composition = self.backend.compose(packet_tracer_version=version)
            qualification = replace(qualification, composition=composition)
            self.backend.validate_composition(composition)
            required = tuple((model, tuple(capabilities)) for model, capabilities in self.backend.requirements(composition).items())
            discovery = self.backend.discovery_factory(session, version)
            acquired = CPScaleCapabilityQualification(required, ())
            for model, capabilities in required:
                probe = self.backend.probe(discovery, version, model, capabilities)
                acquired = replace(acquired, sessions=(*acquired.sessions, probe))
                qualification = replace(qualification, capabilities=acquired)
                if probe.error:
                    raise CanonicalLiveFailure(probe.error)
            first = session.physical.observe_workspace()
            acquired = replace(acquired, first=first)
            qualification = replace(qualification, capabilities=acquired)
            second = session.physical.observe_workspace()
            error = self.backend.restoration_error(qualification.baseline, first, second)
            acquired = replace(acquired, second=second, restoration_error=error)
            qualification = replace(qualification, capabilities=acquired)
            if error:
                raise CanonicalLiveFailure(error)
            composition = self.backend.compose(packet_tracer_version=version)
            qualification = replace(qualification, composition=composition)
            self.backend.validate_composition(composition, post_probe=True)
            unresolved = self.backend.unresolved(composition, required)
            qualification = replace(qualification, capabilities=replace(acquired, unresolved=unresolved))
            if unresolved:
                raise CanonicalLiveFailure("Canonical composition did not consume VERIFIED capability evidence: " + ", ".join(unresolved))
            return composition

        def checkpoint(stage: str) -> CPScaleCheckpointDecision:
            nonlocal progress
            prepared = self.checkpoint.prepare(stage)
            progress = replace(progress, checkpoint=prepared)
            decision = self.checkpoint.publish_and_prompt(prepared, snapshot())
            resumed = self.checkpoint.resume(preflight.identity.source_head)
            progress = replace(progress, checkpoint_resumption=resumed.repository)
            self.checkpoint.publish_resumed(resumed, snapshot())
            if resumed.error:
                raise CanonicalLiveFailure(resumed.error)
            return decision

        def resume(stage: str, continuity: CPScaleStageContinuity, topology: TopologyPlan, *, full: bool = False) -> None:
            nonlocal progress
            acquired = self.build.resume(session=session, continuity=continuity, topology=topology, stage=stage, full=full)
            if acquired.gate is not None:
                progress = replace(progress, resume_gates=(*progress.resume_gates, acquired.gate))
            if acquired.error:
                raise CanonicalLiveFailure(acquired.error)

        def prepare_stage(projection: CPScaleCanonicalStageProjection, continuity: CPScaleStageContinuity,
                          *, router0: bool) -> tuple[PhysicalDeploymentResult, PhysicalDeploymentResult, tuple[CPScaleObservationRecord, ...]]:
            nonlocal progress
            first = continuity.previous_projection is None
            progress = replace(progress, active_stage=CPScaleStageProgress(projection))
            observations.activate(projection)
            boundaries = ()
            if first:
                delta_topology = projection.topology
            else:
                previous = continuity.previous_projection
                resume(projection.stage.value, continuity, previous.topology)
                boundary = observations.before_delta(previous)
                boundaries = (boundary,)
                progress = replace(progress, network_boundaries=(*progress.network_boundaries, (projection.stage.value, boundary)))
                delta_topology = self.build.delta(previous.topology, projection.topology)
                if router0:
                    transition = self.build.transition(previous, projection)
                    progress = replace(progress, active_stage=replace(progress.active_stage, transition=transition),
                                       router0_transition=transition)
                    self.persistence.write_progress(snapshot())
                    if previous.stage is not CPScaleCanonicalStage.FLOOR3 or not transition.mutation_scope_disjoint:
                        raise CanonicalLiveFailure("Router0 target refused its incremental boundary: " + transition.claim)
            delta = physical_stages.deploy(projection, delta_topology, first=first)
            progress = replace(progress, active_stage=replace(progress.active_stage, delta=delta),
                physical=replace(progress.physical, owned=progress.physical.owned | attempted_device_ids(delta)))
            self.persistence.write_progress(snapshot())
            physical_stages.require_delta(None if first else continuity.previous_projection.topology, delta_topology, delta, projection.stage)
            if first:
                deployment = delta
                progress = replace(progress, physical=replace(progress.physical, core_topology=projection.topology, core_deployment=deployment))
            else:
                deployment = physical_stages.cumulative(projection, f"cp-scale-canonical/{projection.stage.value}/cumulative", progress.physical)
            progress = replace(progress, active_stage=replace(progress.active_stage, deployment=deployment))
            self.persistence.write_progress(snapshot())
            physical_stages.require_cumulative(deployment, projection.stage)
            return deployment, delta, boundaries

        def archive(phase: str, payload: CPScaleRunReport | CPScaleCleanupAttestation) -> CPScaleEvidenceArchive:
            nonlocal terminal
            receipt = self.persistence.archive(phase, payload, run_identity=run_identity)
            terminal = replace(terminal, archives=(*terminal.archives, receipt))
            return receipt

        def complete(command: CPScaleCheckpointDecision) -> None:
            nonlocal terminal
            router0 = preflight.target.target is CPScaleCanonicalTarget.ROUTER0_BRANCH
            if router0:
                review = self.completion.review_router0(preflight.target, progress.stages)
                terminal = replace(terminal, replay=review.replay)
                if review.error:
                    raise CanonicalLiveFailure(review.error)
            plan = self.completion.plan(preflight.target, command, retain_authorized=request.retain_on_full_verification)
            terminal = replace(terminal, disposition=plan.disposition, closure=plan.precleanup_closure,
                               closure_scope=plan.scope, completed_at=self.completion.clock())
            self.persistence.write_progress(snapshot())
            receipt = archive("precleanup", snapshot())
            terminal = replace(terminal, precleanup=receipt)
            if plan.disposition is CPScaleFinalDisposition.RETAIN:
                terminal = replace(terminal, retained=True, closure=plan.retained_closure)
                self.persistence.write_progress(snapshot())
                self.persistence.checkpoint(plan.checkpoint, snapshot(), final=True)
                terminal = replace(terminal, event=plan.event)
                return
            cleanup = self.completion.cleanup.restore(session.physical, qualification.composition.topology,
                progress.physical.owned, qualification.baseline)
            terminal = replace(terminal, cleanup=cleanup, cleanup_attempted=True)
            realtime = observations.cleanup_realtime()
            terminal = replace(terminal, realtime=realtime)
            review = self.completion.review_cleanup(cleanup, realtime, router0=router0)
            terminal = replace(terminal, secondary_failures=terminal.secondary_failures + review.secondary_failures)
            if review.error:
                raise CanonicalLiveFailure(review.error)
            completed_at = self.completion.clock()
            if not router0:
                terminal = replace(terminal, closure=plan.cleaned_closure, cleanup_completed_at=completed_at)
            attestation = CPScaleCleanupAttestation(run_identity, preflight.identity.source_head,
                receipt, cleanup, realtime, completed_at, closure=plan.cleaned_closure,
                target_stage=preflight.target.target.value if router0 else "", closure_scope=plan.scope,
                replay=terminal.replay if router0 else None)
            receipt = archive("cleanup", attestation)
            terminal = replace(terminal, attestation=receipt, closure=plan.cleaned_closure, cleanup_completed_at=completed_at)
            self.persistence.write_progress(snapshot())
            self.persistence.checkpoint(plan.checkpoint, snapshot(), final=plan.final_checkpoint)
            terminal = replace(terminal, terminal_cleanup_complete=router0, event=plan.event)

        def prepare_finalization() -> None:
            nonlocal terminal
            if (session.physical is None or qualification.baseline is None or terminal.retained
                or terminal.terminal_cleanup_complete or qualification.composition is None):
                return
            if terminal.precleanup is None:
                try:
                    receipt = archive("failure-precleanup", snapshot())
                    terminal = replace(terminal, precleanup=receipt)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    terminal = replace(terminal, precleanup_archive_error=error,
                        secondary_failures=(*terminal.secondary_failures, "precleanup_archive: " + error))
            if not terminal.cleanup_attempted:
                try:
                    cleanup = self.completion.cleanup.restore(session.physical, qualification.composition.topology,
                        progress.physical.owned, qualification.baseline)
                    terminal = replace(terminal, cleanup=cleanup, cleanup_attempted=True)
                    errors = (("cleanup: " + cleanup.error,) if cleanup.error else ()) + (
                        ("cleanup_restoration: " + cleanup.restoration_error,) if cleanup.restoration_error else ())
                    terminal = replace(terminal, secondary_failures=terminal.secondary_failures + errors)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    terminal = replace(terminal, cleanup=CPScaleCleanupResult(False, error=error),
                        secondary_failures=(*terminal.secondary_failures, "cleanup: " + error))
            realtime = observations.cleanup_realtime()
            terminal = replace(terminal, realtime=realtime, secondary_failures=terminal.secondary_failures + (
                ("cleanup_realtime: " + realtime.error,) if realtime.error else ()))
            if terminal.attestation is None:
                try:
                    attestation = CPScaleCleanupAttestation(run_identity, preflight.identity.source_head,
                        terminal.precleanup, terminal.cleanup, realtime, self.completion.clock(), failure=terminal.failure)
                    phase = "cleanup" if terminal.cleanup and terminal.cleanup.verified and realtime.verified else "cleanup-incomplete"
                    receipt = archive(phase, attestation)
                    terminal = replace(terminal, attestation=receipt)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    terminal = replace(terminal, cleanup_archive_error=error,
                        secondary_failures=(*terminal.secondary_failures, "cleanup_archive: " + error))

        def execute_session() -> CPScaleRunOutcome:
            nonlocal qualification, progress, terminal, observations, physical_stages
            if not session.start():
                status = self.backend.polling_failure_status(session)
                qualification = replace(qualification, bridge=status)
                raise CanonicalLiveFailure("Authenticated Packet Tracer HTTP bridge did not obtain fresh polling: " + self.backend.polling_error(status))
            qualification = replace(qualification, bridge=session.status())
            baseline = session.physical.observe_workspace()
            qualification = replace(qualification, baseline=baseline)
            baseline_error = self.baseline_policy(baseline)
            if baseline_error:
                terminal = replace(terminal, hard_stop=baseline_error)
                self.persistence.write_progress(snapshot())
                return CPScaleRunOutcome.REJECTED
            observations = self.observations_factory(session)
            composition = qualify_backend()
            statistics_target = observations.dhcp_target(self.build.statistics_projection(composition))
            fingerprint = EnvironmentFingerprint(backend="packet_tracer", backend_version=request.packet_tracer_version,
                bridge_transport=session.channel, runtime_mode="live")
            physical_stages = CPScalePhysicalStages(self.build, session, fingerprint)
            executor = self.stage_factory(session, session.acquire_runtimes())

            def step(stage: CPScaleCanonicalStage, continuity: CPScaleStepContinuity) -> StageStepResult[CPScaleStepContinuity, CPScaleLiveStageResult]:
                nonlocal progress, terminal
                decision = canonical_step_decision(preflight.target, stage)
                projection = self.build.projection(composition, stage)
                deployment, delta, boundaries = prepare_stage(projection, continuity.stage, router0=decision.site_forwarding)
                acquired = executor.execute(CPScaleStageExecutionInput(projection, composition, deployment, delta, fingerprint,
                    request.packet_tracer_version, continuity.stage,
                    statistics_target if decision.floor1_statistics else None,
                    continuity.dhcp_baseline if decision.floor1_statistics else None,
                    boundaries, projection.branch_forwarding_checks if decision.site_forwarding else ()))
                errors = stage_secondary_failures(acquired)
                progress = replace(progress, active_stage=replace(progress.active_stage, result=acquired))
                terminal = replace(terminal, secondary_failures=terminal.secondary_failures + errors)
                if acquired.outcome == "failed":
                    return StageStepResult(acquired, continuity, False, errors)
                baseline = observations.dhcp_baseline(statistics_target) if decision.acquire_dhcp_baseline else continuity.dhcp_baseline
                if decision.acquire_dhcp_baseline:
                    progress = replace(progress, active_stage=replace(progress.active_stage, dhcp_baseline=baseline))
                progress = replace(progress, stages=(*progress.stages, progress.active_stage), active_stage=None,
                    live_devices=len(projection.topology.devices), live_links=len(projection.topology.links))
                error = canonical_step_result_error(acquired)
                if error:
                    raise CanonicalLiveFailure(error)
                following = advance_canonical_continuity(continuity, acquired, decision, baseline)
                if decision.capture_serial_core:
                    self.presentation.core_rematerialized()
                if decision.checkpoint_required and checkpoint(stage.value) is CPScaleCheckpointDecision.RETAIN:
                    raise CanonicalLiveFailure("Retention is forbidden before full CP-SCALE qualification.")
                return StageStepResult(acquired, following, True, errors)

            sequence = execute_stage_sequence(preflight.target.build_stages, CPScaleStepContinuity(), step)
            terminal = replace(terminal, secondary_failures=sequence.secondary_failures)
            if not sequence.succeeded:
                raise CanonicalLiveFailure(sequence.steps[-1].value.failure)
            if preflight.target.target is CPScaleCanonicalTarget.ROUTER0_BRANCH:
                complete(CPScaleCheckpointDecision.CONTINUE)
                return CPScaleRunOutcome.COMPLETED
            assert preflight.target.run_remaining_reconciliation
            assert preflight.target.run_full_qualification
            continuity = sequence.continuity.stage
            remaining = self.build.remaining_projection(composition, continuity)
            deployment = physical_stages.cumulative(remaining, "cp-scale-canonical/remaining/reconciliation", progress.physical)
            physical_stages.require_cumulative(deployment, remaining.stage, remaining=True)
            progress = replace(progress, stages=(*progress.stages, CPScaleStageProgress(remaining, deployment=deployment, remaining=True)))
            if checkpoint(CPScaleCanonicalStage.REMAINING.value) is CPScaleCheckpointDecision.RETAIN:
                raise CanonicalLiveFailure("Retention is forbidden before full CP-SCALE qualification.")
            resume("full-qualification", continuity, remaining.topology, full=True)
            projection = self.build.full_projection(composition)
            observations.activate(projection)
            deployment = physical_stages.cumulative(projection, "cp-scale-canonical/full-qualification", progress.physical)
            acquired = executor.execute(CPScaleStageExecutionInput(projection, composition, deployment, None,
                fingerprint, request.packet_tracer_version, continuity))
            terminal = replace(terminal, secondary_failures=terminal.secondary_failures + stage_secondary_failures(acquired))
            if acquired.outcome == "failed":
                progress = replace(progress, active_stage=CPScaleStageProgress(projection, deployment=deployment, result=acquired))
                raise CanonicalLiveFailure(acquired.failure)
            progress = replace(progress, full_qualification=acquired, live_devices=len(composition.topology.devices),
                               live_links=len(composition.topology.links))
            complete(checkpoint("full-qualification"))
            return CPScaleRunOutcome.COMPLETED

        try:
            outcome = execute_session()
            terminal = replace(terminal, outcome=outcome)
        except Exception as exc:
            terminal = replace(terminal, failure=f"{type(exc).__name__}: {exc}", outcome=CPScaleRunOutcome.FAILED)
            if progress.active_stage is not None:
                failed = replace(progress.active_stage, failed=True, failure_details=getattr(exc, "partial_stage", None))
                progress = replace(progress, stages=(*progress.stages, failed), active_stage=None)
        finally:
            final = finalize_session(prepare=prepare_finalization, write=lambda: self.persistence.write_progress(snapshot()),
                session=session, report=report_errors, secondary_failures=lambda: terminal.secondary_failures)
            terminal = replace(terminal, finalization_errors=final.errors)
            if final.errors and terminal.outcome is CPScaleRunOutcome.COMPLETED:
                terminal = replace(terminal, outcome=CPScaleRunOutcome.FAILED)
        if terminal.outcome is CPScaleRunOutcome.COMPLETED:
            try:
                self.presentation.terminal(terminal.event, snapshot())
            except Exception as exc:
                errors = report_terminal_errors((f"terminal_presentation: {type(exc).__name__}: {exc}",), report_errors)
                terminal = replace(terminal, outcome=CPScaleRunOutcome.FAILED, finalization_errors=errors)
        return CPScaleLiveFinalResult.from_report(terminal.outcome, snapshot())
