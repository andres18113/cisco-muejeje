"""Terminal and cleanup failures retain the last facts actually acquired."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.application.cp_scale_live.backend import (
    CPScaleBackendQualification,
)
from src.packet_tracer_mcp.application.cp_scale_live.build_policy import (
    CPScaleBuildPolicy,
)
from src.packet_tracer_mcp.application.cp_scale_live.cleanup import CPScaleCleanup
from src.packet_tracer_mcp.application.cp_scale_live.completion import (
    CPScaleClosurePlan,
    CPScaleCompletion,
    CPScaleRouter0Review,
)
from src.packet_tracer_mcp.application.cp_scale_live.coordinator import (
    CPScaleLiveCoordinator,
)
from src.packet_tracer_mcp.application.cp_scale_live.contracts import (
    CPScaleRealtimeState,
)
from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import (
    CPScaleBridgeStatus,
    CPScaleCleanupRealtime,
    CPScaleRunOutcome,
    CPScaleTerminalEvent,
)
from src.packet_tracer_mcp.application.cp_scale_live.stage_executor import (
    CPScaleStageExecutor,
)
from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
)
from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    CPScaleFinalDisposition,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemResult,
    PhysicalDeploymentItemStatus,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_session import (
    PacketTracerCPScaleSession,
)
from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_live import (
    CPScaleLivePersistence,
)
from tests.cp_scale_stage_fixture import stage_fixture
from tests.test_cp_scale_live_local_preflight import _request, _service


FIXED_TIME = datetime(2026, 9, 9, tzinfo=timezone.utc)


def _controlled_coordinator(
    root: Path,
    *,
    stop_error: str = "",
    terminal_error: str = "",
    terminal_write_error: str = "",
    incomplete_error: str = "",
    cleanup_failure: str = "",
):
    request = _request(target_stage="router0-branch")
    fixture = stage_fixture(CPScaleStageExecutor)
    base_stage = fixture.executor.execute(fixture.request)
    devices = []
    if cleanup_failure == "second_read":
        devices = [DevicePlan(id="r", name="R", model="2911", category="router")]
    elif cleanup_failure in {"second_remove", "cancel_second_remove"}:
        devices = [
            DevicePlan(id="r", name="R", model="2911", category="router"),
            DevicePlan(id="s", name="S", model="2911", category="router"),
        ]
    topology = TopologyPlan(
        id="terminal-persistence",
        physical_topology_hash="synthetic-physical",
        semantic_hash="synthetic-physical",
        devices=devices,
    )
    projection = replace(fixture.request.projection, topology=topology)
    item_results = [
        PhysicalDeploymentItemResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            status=PhysicalDeploymentItemStatus.APPLIED,
        )
        for device in devices
    ]
    deployment = fixture.request.deployment.model_copy(
        update={"topology_id": topology.id, "item_results": item_results},
    )
    stage_result = replace(
        base_stage,
        projection=projection,
        deployment=deployment,
        delta_deployment=deployment,
        manifest=deployment.manifest,
    )
    build_stages = (CPScaleCanonicalStage.ROUTING_CORE,) if devices else ()
    preflight = _service()

    class Preflight:
        def inspect(self, value, *, run_identity, started_at):
            acquired = preflight.inspect(
                value,
                run_identity=run_identity,
                started_at=started_at,
            )
            return replace(
                acquired,
                target=replace(
                    acquired.target,
                    build_stages=build_stages,
                    terminal_stage=CPScaleCanonicalStage.ROUTING_CORE,
                ),
            )

    calls: list[str] = []
    first_cleanup_read = PhysicalWorkspaceObservation(message="FIRST_CLEANUP_READ")

    class Physical:
        def __init__(self) -> None:
            self.workspace_reads = 0

        def observe_workspace(self):
            self.workspace_reads += 1
            calls.append(f"workspace:{self.workspace_reads}")
            if cleanup_failure == "second_read" and self.workspace_reads == 4:
                return first_cleanup_read
            if cleanup_failure == "second_read" and self.workspace_reads == 5:
                raise RuntimeError("SECOND_CLEANUP_READ_FAILED")
            return PhysicalWorkspaceObservation()

        def remove_device(self, device):
            calls.append("remove:" + device.id)
            if cleanup_failure == "second_remove" and device.id == "r":
                raise RuntimeError("SECOND_REMOVE_FAILED")
            if cleanup_failure == "cancel_second_remove" and device.id == "r":
                raise KeyboardInterrupt("CANCELLED_DURING_SECOND_REMOVE")
            return PhysicalMutationResult(
                target_id=device.id,
                target_kind=PhysicalObjectKind.DEVICE,
                applied=True,
            )

    physical = Physical()

    class Transport:
        bridge_transport = "offline"
        is_connected = True

        def start(self, **kwargs):
            calls.append("start")
            return True

        def status_dict(self):
            return {"connected": True}

        def stop(self):
            calls.append("stop")
            if stop_error:
                raise OSError(stop_error)

    session = PacketTracerCPScaleSession(
        transport_factory=Transport,
        physical_factory=lambda transport: physical,
        runtime_factory=lambda *args: SimpleNamespace(),
    )
    composition = SimpleNamespace(
        valid=True,
        issues=(),
        topology=topology,
        configuration=object(),
        control_plane=object(),
        capabilities={},
    )
    realtime = CPScaleCleanupRealtime(
        True,
        state=CPScaleRealtimeState(
            observed=True,
            simulation_mode=False,
            present=("observed", "simulation_mode"),
        ),
    )
    observations = SimpleNamespace(
        dhcp_target=lambda projection: None,
        cleanup_realtime=lambda: realtime,
        activate=lambda projection: None,
    )
    persistence = CPScaleLivePersistence(root)
    original_write = persistence.write_progress
    write_reports = []

    def write_progress(report):
        write_reports.append(report)
        if terminal_write_error and report.finalization_errors:
            raise OSError(terminal_write_error)
        original_write(report)

    persistence.write_progress = write_progress
    terminal_file_before_attempt: list[bytes] = []
    incomplete_reports: list[tuple[str, ...]] = []

    class Presentation:
        def core_rematerialized(self):
            calls.append("core")

        def terminal(self, event, report):
            calls.append("terminal_attempt")
            terminal_file_before_attempt.append(persistence.evidence_path.read_bytes())
            if terminal_error:
                raise OSError(terminal_error)
            calls.append("terminal_published")

        def finalization_incomplete(self, report):
            incomplete_reports.append(report.finalization_errors)
            calls.append("finalization_incomplete")
            if incomplete_error:
                raise OSError(incomplete_error)

    completion = CPScaleCompletion(cleanup=CPScaleCleanup(), clock=lambda: FIXED_TIME)
    completion.review_router0 = lambda *args: CPScaleRouter0Review(None, "")
    completion.plan = lambda *args, **kwargs: CPScaleClosurePlan(
        CPScaleFinalDisposition.CLEANUP,
        "ROUTER0_BRANCH_VERIFIED_PRECLEANUP",
        "ROUTER0_BRANCH_VERIFIED_AND_CLEANED",
        "",
        "router0-branch",
        "router0-branch",
        False,
        True,
        CPScaleTerminalEvent.ROUTER0_CLEANED,
    )
    build = CPScaleBuildPolicy(
        capabilities={},
        project=lambda *args, **kwargs: projection,
        deployer_factory=lambda runtime: SimpleNamespace(
            deploy=lambda *args, **kwargs: deployment,
        ),
        ownership_error=lambda *args: "",
    )
    coordinator = CPScaleLiveCoordinator(
        preflight=Preflight(),
        session_factory=lambda: session,
        backend=CPScaleBackendQualification(
            compose=lambda **kwargs: composition,
            discovery_factory=lambda *args: object(),
            requirements=lambda value: {},
        ),
        stage_factory=lambda *args: SimpleNamespace(execute=lambda request: stage_result),
        observations_factory=lambda value: observations,
        build=build,
        checkpoint=SimpleNamespace(),
        persistence=persistence,
        completion=completion,
        presentation=Presentation(),
        clock=lambda: FIXED_TIME,
    )
    return SimpleNamespace(
        coordinator=coordinator,
        request=request,
        persistence=persistence,
        calls=calls,
        first_cleanup_read=first_cleanup_read,
        write_reports=write_reports,
        terminal_file_before_attempt=terminal_file_before_attempt,
        incomplete_reports=incomplete_reports,
    )


def test_stop_failure_is_durably_published_when_the_writer_remains_available(
    tmp_path: Path,
) -> None:
    fixture = _controlled_coordinator(tmp_path, stop_error="STOP_FAILED")

    result = fixture.coordinator.run(fixture.request)

    evidence = json.loads(fixture.persistence.evidence_path.read_text(encoding="utf-8"))
    assert result.outcome is CPScaleRunOutcome.FAILED
    assert result.primary_failure is None
    assert result.secondary_failures == ("transport_stop: OSError: STOP_FAILED",)
    assert evidence["finalization_errors"] == list(result.secondary_failures)
    assert fixture.incomplete_reports[-1] == result.secondary_failures
    assert "terminal_attempt" not in fixture.calls
    assert fixture.calls.count("stop") == 1


def test_terminal_presentation_failure_is_durably_published(
    tmp_path: Path,
) -> None:
    fixture = _controlled_coordinator(
        tmp_path,
        terminal_error="TERMINAL_PRESENTATION_FAILED",
    )

    result = fixture.coordinator.run(fixture.request)

    evidence = json.loads(fixture.persistence.evidence_path.read_text(encoding="utf-8"))
    assert result.outcome is CPScaleRunOutcome.FAILED
    assert result.secondary_failures == (
        "terminal_presentation: OSError: TERMINAL_PRESENTATION_FAILED",
    )
    assert evidence["finalization_errors"] == list(result.secondary_failures)
    assert fixture.incomplete_reports[-1] == result.secondary_failures
    assert fixture.calls.count("terminal_attempt") == 1
    assert "terminal_published" not in fixture.calls
    assert fixture.calls.count("stop") == 1


def test_failed_terminal_publication_preserves_the_previous_file_and_reports_absence(
    tmp_path: Path,
) -> None:
    fixture = _controlled_coordinator(
        tmp_path,
        terminal_error="TERMINAL_PRESENTATION_FAILED",
        terminal_write_error="TERMINAL_PUBLICATION_FAILED",
    )

    result = fixture.coordinator.run(fixture.request)

    assert result.outcome is CPScaleRunOutcome.FAILED
    assert result.secondary_failures == (
        "terminal_presentation: OSError: TERMINAL_PRESENTATION_FAILED",
        "terminal_evidence_write: OSError: TERMINAL_PUBLICATION_FAILED",
    )
    assert fixture.persistence.evidence_path.read_bytes() == fixture.terminal_file_before_attempt[0]
    previous = json.loads(fixture.terminal_file_before_attempt[0])
    assert "finalization_errors" not in previous
    assert fixture.incomplete_reports[-1] == result.secondary_failures
    assert "terminal_published" not in fixture.calls
    assert fixture.calls.count("stop") == 1


def test_failed_finalization_report_is_added_to_the_durable_outcome(
    tmp_path: Path,
) -> None:
    fixture = _controlled_coordinator(
        tmp_path,
        stop_error="STOP_FAILED",
        incomplete_error="FINALIZATION_REPORT_FAILED",
    )

    result = fixture.coordinator.run(fixture.request)

    assert result.secondary_failures == (
        "transport_stop: OSError: STOP_FAILED",
        "finalization_report: OSError: FINALIZATION_REPORT_FAILED",
    )
    evidence = json.loads(fixture.persistence.evidence_path.read_text(encoding="utf-8"))
    assert evidence["finalization_errors"] == list(result.secondary_failures)
    assert fixture.calls.count("finalization_incomplete") == 1
    assert fixture.calls.count("stop") == 1


def test_second_cleanup_read_failure_retains_mutation_and_first_observation(
    tmp_path: Path,
) -> None:
    fixture = _controlled_coordinator(tmp_path, cleanup_failure="second_read")

    result = fixture.coordinator.run(fixture.request)

    assert result.outcome is CPScaleRunOutcome.FAILED
    assert "SECOND_CLEANUP_READ_FAILED" in result.primary_failure
    assert result.cleanup is not None
    assert result.cleanup.verified is False
    assert result.cleanup.error == "RuntimeError: SECOND_CLEANUP_READ_FAILED"
    assert result.cleanup.first is fixture.first_cleanup_read
    assert result.cleanup.second is None
    assert tuple(item.target_id for item in result.cleanup.mutations) == ("r",)
    assert fixture.calls.count("remove:r") == 1
    assert fixture.calls.count("workspace:5") == 1
    evidence = json.loads(fixture.persistence.evidence_path.read_text(encoding="utf-8"))
    assert evidence["failure"] == result.primary_failure
    assert evidence["cleanup"]["error"] == "RuntimeError: SECOND_CLEANUP_READ_FAILED"
    assert evidence["cleanup"]["first"]["message"] == "FIRST_CLEANUP_READ"
    assert "second" not in evidence["cleanup"]
    assert [item["target_id"] for item in evidence["cleanup"]["mutations"]] == ["r"]


def test_second_remove_failure_retains_only_the_confirmed_prior_mutation(
    tmp_path: Path,
) -> None:
    fixture = _controlled_coordinator(tmp_path, cleanup_failure="second_remove")

    result = fixture.coordinator.run(fixture.request)

    assert result.outcome is CPScaleRunOutcome.FAILED
    assert "SECOND_REMOVE_FAILED" in result.primary_failure
    assert result.cleanup is not None
    assert result.cleanup.verified is False
    assert result.cleanup.error == "RuntimeError: SECOND_REMOVE_FAILED"
    assert result.cleanup.first is None
    assert result.cleanup.second is None
    assert tuple(item.target_id for item in result.cleanup.mutations) == ("s",)
    assert [call for call in fixture.calls if call.startswith("remove:")] == [
        "remove:s",
        "remove:r",
    ]
    evidence = json.loads(fixture.persistence.evidence_path.read_text(encoding="utf-8"))
    assert evidence["failure"] == result.primary_failure
    assert evidence["cleanup"]["error"] == "RuntimeError: SECOND_REMOVE_FAILED"
    assert [item["target_id"] for item in evidence["cleanup"]["mutations"]] == ["s"]
    assert "first" not in evidence["cleanup"]
    assert "second" not in evidence["cleanup"]


def test_cleanup_cancellation_is_not_retried_or_converted_to_a_result(
    tmp_path: Path,
) -> None:
    fixture = _controlled_coordinator(
        tmp_path,
        cleanup_failure="cancel_second_remove",
    )

    with pytest.raises(KeyboardInterrupt, match="CANCELLED_DURING_SECOND_REMOVE"):
        fixture.coordinator.run(fixture.request)

    assert [call for call in fixture.calls if call.startswith("remove:")] == [
        "remove:s",
        "remove:r",
    ]
    assert fixture.calls.count("stop") == 1
    evidence = json.loads(fixture.persistence.evidence_path.read_text(encoding="utf-8"))
    assert "cleanup" not in evidence
    assert "finalization_errors" not in evidence
