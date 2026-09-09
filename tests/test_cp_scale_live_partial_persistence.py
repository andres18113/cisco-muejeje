"""Acquired partial CP-LIVE facts remain serializable without invented reads."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.application.cp_scale_live.backend import CPScaleBackendQualification
from src.packet_tracer_mcp.application.cp_scale_live.cleanup import CPScaleCleanup
from src.packet_tracer_mcp.application.cp_scale_live.completion import CPScaleCompletion
from src.packet_tracer_mcp.application.cp_scale_live.coordinator import CPScaleLiveCoordinator
from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import (
    CPScaleBridgeStatus,
    CPScaleCapabilityQualification,
    CPScaleCleanupRealtime,
    CPScaleCleanupResult,
)
from src.packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleRealtimeState
from src.packet_tracer_mcp.application.cp_scale_live.run_state import (
    CPScaleProgressState,
    CPScaleQualificationState,
    CPScaleTerminalState,
    publication_snapshot,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_live import (
    CPScaleLivePersistence,
)
from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_run_evidence import (
    cleanup_evidence,
    run_evidence,
)
from tests.cp_scale_stage_fixture import stage_fixture
from tests.test_cp_scale_live_local_preflight import _request, _service


FIXED_TIME = datetime(2026, 9, 9, tzinfo=timezone.utc)
EMPTY_WORKSPACE = {
    "observed": True,
    "semantic_device_count": 0,
    "backend_managed_device_count": 0,
    "link_count": 0,
    "devices": [],
    "links": [],
    "message": "",
}


def _report(qualification: CPScaleCapabilityQualification):
    request = _request(target_stage="router0-branch")
    preflight = _service().inspect(request, run_identity="partial", started_at=FIXED_TIME)
    return publication_snapshot(
        preflight,
        "partial",
        FIXED_TIME,
        request.packet_tracer_version,
        CPScaleQualificationState(capabilities=qualification),
        CPScaleProgressState(),
        CPScaleTerminalState(),
    )


@pytest.mark.parametrize(
    "first,second,unresolved,expected",
    [
        (
            PhysicalWorkspaceObservation(),
            None,
            None,
            {
                "requirements": {"switch": ["poe"]},
                "sessions": [],
                "workspace_first": EMPTY_WORKSPACE,
                "workspace_second": None,
                "restoration_error": "",
            },
        ),
        (
            None,
            PhysicalWorkspaceObservation(),
            None,
            {
                "requirements": {"switch": ["poe"]},
                "sessions": [],
                "workspace_first": None,
                "workspace_second": EMPTY_WORKSPACE,
                "restoration_error": "",
            },
        ),
        (
            None,
            None,
            ("switch:poe",),
            {
                "requirements": {"switch": ["poe"]},
                "sessions": [],
                "workspace_first": None,
                "workspace_second": None,
                "restoration_error": "",
                "unresolved_after_composition": ["switch:poe"],
            },
        ),
    ],
)
def test_capability_serializer_preserves_each_optional_fact_independently(
    first,
    second,
    unresolved,
    expected,
) -> None:
    qualification = CPScaleCapabilityQualification(
        (("switch", ("poe",)),),
        (),
        first=first,
        second=second,
        unresolved=unresolved,
    )

    assert run_evidence(_report(qualification))["capability_prequalification"] == expected


def test_capability_serializer_keeps_the_historical_probe_only_list_shape() -> None:
    qualification = CPScaleCapabilityQualification((("switch", ("poe",)),), ())

    assert run_evidence(_report(qualification))["capability_prequalification"] == []


def test_cleanup_serializer_does_not_drop_a_later_restoration_failure() -> None:
    result = CPScaleCleanupResult(
        False,
        restoration_error="SECOND_RESTORATION_READ_FAILED",
        error="REMOVE_DEVICE_FAILED",
    )

    assert cleanup_evidence(result) == {
        "verified": False,
        "error": "REMOVE_DEVICE_FAILED",
        "restoration_error": "SECOND_RESTORATION_READ_FAILED",
    }


def test_second_capability_workspace_failure_persists_first_observation_and_primary_cause(
    tmp_path: Path,
) -> None:
    from src.packet_tracer_mcp.application.cp_scale_live.stage_executor import CPScaleStageExecutor

    fixture = stage_fixture(CPScaleStageExecutor)
    projection = fixture.request.projection
    composition = replace(
        fixture.request.composition,
        topology=projection.topology,
        configuration=projection.configuration,
        control_plane=projection.control_plane,
    )
    workspaces = iter((
        PhysicalWorkspaceObservation(),
        PhysicalWorkspaceObservation(),
        RuntimeError("SECOND_WORKSPACE_READ_FAILED"),
        PhysicalWorkspaceObservation(),
        PhysicalWorkspaceObservation(),
    ))
    calls: list[str] = []

    class Physical:
        def observe_workspace(self):
            calls.append("workspace")
            value = next(workspaces)
            if isinstance(value, BaseException):
                raise value
            return value

        def remove_device(self, device):
            pytest.fail("No device was owned before backend qualification failed")

    class Session:
        physical = Physical()
        connected = True
        channel = "offline"

        def start(self):
            calls.append("start")
            return True

        def status(self):
            return CPScaleBridgeStatus(True)

        def acquire_runtimes(self):
            pytest.fail("Stage runtimes were acquired after backend qualification failed")

        def close(self):
            calls.append("close")

    realtime = CPScaleCleanupRealtime(
        True,
        state=CPScaleRealtimeState(
            observed=True,
            simulation_mode=False,
            present=("observed", "simulation_mode"),
        ),
    )
    observations = SimpleNamespace(cleanup_realtime=lambda: realtime)
    persistence = CPScaleLivePersistence(tmp_path)
    coordinator = CPScaleLiveCoordinator(
        preflight=_service(),
        session_factory=Session,
        backend=CPScaleBackendQualification(
            compose=lambda **kwargs: composition,
            discovery_factory=lambda *args: object(),
            requirements=lambda value: {},
        ),
        stage_factory=lambda *args: pytest.fail("Stage executor was constructed"),
        observations_factory=lambda session: observations,
        build=SimpleNamespace(),
        checkpoint=SimpleNamespace(),
        persistence=persistence,
        completion=CPScaleCompletion(cleanup=CPScaleCleanup()),
        presentation=SimpleNamespace(
            core_rematerialized=lambda: None,
            terminal=lambda *args: None,
            finalization_incomplete=lambda report: None,
        ),
        clock=lambda: FIXED_TIME,
    )

    result = coordinator.run(_request())

    assert result.primary_failure == "RuntimeError: SECOND_WORKSPACE_READ_FAILED"
    assert calls == ["start", "workspace", "workspace", "workspace", "workspace", "workspace", "close"]
    evidence = json.loads(persistence.evidence_path.read_text(encoding="utf-8"))
    qualification = evidence["capability_prequalification"]
    assert qualification["workspace_first"] == EMPTY_WORKSPACE
    assert qualification["workspace_second"] is None
    assert qualification["restoration_error"] == ""
    assert evidence["failure"] == "RuntimeError: SECOND_WORKSPACE_READ_FAILED"
    assert "verified" not in qualification
    assert "http_bridge" in evidence
    assert [item["phase"] for item in evidence["archives"]] == [
        "failure-precleanup",
        "cleanup",
    ]
