"""Progressive CP-SCALE gates and evidence lifecycle, without live mutation."""

from __future__ import annotations

import json
from pathlib import Path

from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    EnterpriseReferenceComposition,
)
from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    EnterpriseExecutionResult,
    EnterpriseExecutionStage,
    EnterpriseExecutionStatus,
    EnterpriseRuntimes,
)
from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    CPScaleLivePointResult,
    CPScaleLiveQualification,
    CPScalePointStatus,
    CPScalePreparedPoint,
    CPScaleRepositoryState,
    canonical_stage_workspace_error,
    qualify_cp_scale_progressive,
    read_git_repository_state,
    write_cp_scale_live_artifacts,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import ControlPlaneIntent
from src.packet_tracer_mcp.domain.enterprise.models.compilation import EnterpriseCompileSummary
from src.packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import VoiceIntent
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale import CPScalePoint
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.models.plans import (
    DevicePlan,
    LinkPlan,
    TopologyPlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceLinkObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)


_FINGERPRINT = EnvironmentFingerprint(
    backend_version="9.0.1.0858",
    bridge_transport="file",
    runtime_mode="live",
)
_REPOSITORY = CPScaleRepositoryState(
    branch="feature/runtime-ripv2",
    upstream="personal/feature/runtime-ripv2",
    head="0123456789abcdef",
)


class _UnusedRuntime:
    pass


_RUNTIMES = EnterpriseRuntimes(
    physical=_UnusedRuntime(),
    serial_orientation=_UnusedRuntime(),
    configuration=_UnusedRuntime(),
    control_plane=_UnusedRuntime(),
    voice=_UnusedRuntime(),
)


def _preflight() -> ImportIsolationPreflight:
    return ImportIsolationPreflight(Path(__file__).resolve().parents[1])


def _prepare(point, intent):
    designed = EnterpriseDesigner().design(intent)
    assert designed.validation.is_valid and designed.plan is not None
    topology = TopologyPlan(id=f"topology-{point.value}", name=point.value)
    workload_count = int(intent.metadata["workload_endpoints"])
    access_points = int(intent.metadata["access_points"])
    composition = EnterpriseReferenceComposition(
        enterprise=designed.plan,
        topology=topology,
        topology_summary=EnterpriseCompileSummary(
            plan_id=topology.id,
            workload_endpoints=workload_count,
            access_points=access_points,
            endpoints=workload_count + access_points,
        ),
    )
    return CPScalePreparedPoint(
        intent=intent,
        composition=composition,
        control_plane_intent=ControlPlaneIntent(id=f"control-{point.value}"),
        voice_intent=VoiceIntent(id=f"voice-{point.value}"),
    )


def _execution(status=EnterpriseExecutionStatus.COMPLETED):
    completed = status is EnterpriseExecutionStatus.COMPLETED
    return EnterpriseExecutionResult(
        status=status,
        stopped_at=(
            EnterpriseExecutionStage.COMPLETED
            if completed else EnterpriseExecutionStage.CONFIGURATION_APPLY
        ),
        cleanup_confirmed_twice=True if completed else False,
        inventory_restored=True if completed else False,
        errors=[] if completed else ["controlled point failure"],
    )


def test_repository_or_fingerprint_mismatch_blocks_before_any_executor_call():
    calls = []

    result = qualify_cp_scale_progressive(
        _RUNTIMES,
        environment_fingerprint=_FINGERPRINT,
        environment_probe=lambda: _FINGERPRINT,
        repository_state_provider=lambda: _REPOSITORY.model_copy(
            update={"upstream": "origin/main"},
        ),
        import_preflight=_preflight(),
        packet_tracer_version="9.0.1.0858",
        point_preparer=_prepare,
        execution_use_case=lambda *args, **kwargs: calls.append(args),
    )

    assert calls == []
    assert [item.status for item in result.points] == [
        CPScalePointStatus.BLOCKED,
        CPScalePointStatus.NOT_RUN,
        CPScalePointStatus.NOT_RUN,
        CPScalePointStatus.NOT_RUN,
    ]
    assert all(
        metric.status == "not_run" and metric.count == 0
        for metric in result.points[0].dimensions.values()
    )


def test_progressive_runner_stops_at_first_failure_and_retains_lower_envelope():
    calls = []

    def execute(intent, *args, **kwargs):
        point = CPScalePoint(intent.metadata["scale_point"])
        calls.append(point)
        return _execution(
            EnterpriseExecutionStatus.FAILED
            if point is CPScalePoint.C else EnterpriseExecutionStatus.COMPLETED
        )

    result = qualify_cp_scale_progressive(
        _RUNTIMES,
        environment_fingerprint=_FINGERPRINT,
        environment_probe=lambda: _FINGERPRINT,
        repository_state_provider=lambda: _REPOSITORY,
        import_preflight=_preflight(),
        packet_tracer_version="9.0.1.0858",
        point_preparer=_prepare,
        execution_use_case=execute,
    )

    assert calls == [CPScalePoint.A, CPScalePoint.B, CPScalePoint.C]
    assert [item.status for item in result.points] == [
        CPScalePointStatus.COMPLETED,
        CPScalePointStatus.COMPLETED,
        CPScalePointStatus.FAILED,
        CPScalePointStatus.NOT_RUN,
    ]
    assert result.reliable_workload_envelope == 118
    assert result.closure == "MECHANICALLY_VERIFIED_ENVELOPE"
    assert result.points[-1].dimensions["voice"].count == 0


def test_full_progression_keeps_wireless_and_iot_function_claims_bounded(tmp_path):
    result = qualify_cp_scale_progressive(
        _RUNTIMES,
        environment_fingerprint=_FINGERPRINT,
        environment_probe=lambda: _FINGERPRINT,
        repository_state_provider=lambda: _REPOSITORY,
        import_preflight=_preflight(),
        packet_tracer_version="9.0.1.0858",
        point_preparer=_prepare,
        execution_use_case=lambda *args, **kwargs: _execution(),
    )

    assert result.reliable_workload_envelope == 279
    assert result.full_scale_executed
    assert result.closure != "FULL_TARGET_VERIFIED"
    assert all(
        item.dimensions["wireless_association"].status == "not_run"
        and item.dimensions["iot_function"].status == "not_run"
        for item in result.points
    )

    output = write_cp_scale_live_artifacts(result, tmp_path, "progressive evidence")
    assert output == tmp_path / "progressive_evidence"
    assert {item.name for item in output.iterdir()} == {
        "summary.json", "point-a.json", "point-b.json", "point-c.json", "point-d.json",
    }
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["reliable_workload_envelope"] == 279


def test_repository_reader_observes_current_exact_branch_upstream_and_head():
    state = read_git_repository_state(Path(__file__).resolve().parents[1])

    assert state.error == ""
    assert state.branch == "feature/runtime-ripv2"
    assert state.upstream == "personal/feature/runtime-ripv2"
    assert len(state.head) == 40


def test_canonical_stage_resume_gate_requires_exact_device_and_link_ownership():
    topology = TopologyPlan(
        id="owned-stage",
        devices=[
            DevicePlan(id="r4", name="Router4", model="2811", category="router"),
            DevicePlan(
                id="sw10", name="Switch10", model="2960-24TT", category="switch",
            ),
        ],
        links=[LinkPlan(
            id="edge",
            device_a="Router4",
            port_a="FastEthernet0/0",
            device_b="Switch10",
            port_b="GigabitEthernet0/1",
            device_a_id="r4",
            device_b_id="sw10",
        )],
    )
    exact = PhysicalWorkspaceObservation(
        devices=[
            PhysicalWorkspaceDeviceObservation(
                name="Router4", model="2811", ports=["FastEthernet0/0"],
            ),
            PhysicalWorkspaceDeviceObservation(
                name="Switch10", model="2960-24TT", ports=["GigabitEthernet0/1"],
            ),
        ],
        links=[PhysicalWorkspaceLinkObservation(
            device_a="Switch10",
            port_a="GigabitEthernet0/1",
            device_b="Router4",
            port_b="FastEthernet0/0",
        )],
        message="fresh_complete_workspace_inventory",
    )

    assert canonical_stage_workspace_error(exact, topology) == ""
    assert "model" in canonical_stage_workspace_error(
        exact.model_copy(update={
            "devices": [
                exact.devices[0],
                exact.devices[1].model_copy(update={"model": "3560-24PS"}),
            ],
        }),
        topology,
    ).casefold()
    assert "link" in canonical_stage_workspace_error(
        exact.model_copy(update={"links": []}), topology,
    ).casefold()
    assert "device" in canonical_stage_workspace_error(
        exact.model_copy(update={
            "devices": [
                *exact.devices,
                PhysicalWorkspaceDeviceObservation(
                    name="ManualPC", model="PC-PT", ports=["FastEthernet0"],
                ),
            ],
        }),
        topology,
    ).casefold()


def test_canonical_stage_resume_gate_accepts_only_owned_implicit_antennas():
    topology = TopologyPlan(
        id="wireless-stage",
        devices=[
            DevicePlan(
                id="ap1",
                name="AP1",
                model="AccessPoint-PT",
                category="accesspoint",
            ),
            DevicePlan(
                id="iot1",
                name="SMOKE1",
                model="Smoke Detector",
                category="iot",
                wireless=True,
            ),
        ],
    )
    exact = PhysicalWorkspaceObservation(
        devices=[
            PhysicalWorkspaceDeviceObservation(
                name="AP1", model="AccessPoint-PT", ports=["Port 0", "Port 1"],
            ),
            PhysicalWorkspaceDeviceObservation(
                name="SMOKE1", model="Smoke Detector", ports=["Wireless0"],
            ),
        ],
        links=[
            PhysicalWorkspaceLinkObservation(
                class_name="Antenna", device_a="AP1", port_a="Port 1",
            ),
            PhysicalWorkspaceLinkObservation(
                class_name="Antenna", device_a="SMOKE1", port_a="Wireless0",
            ),
        ],
        message="fresh_complete_workspace_inventory",
    )

    assert canonical_stage_workspace_error(exact, topology) == ""
    foreign = exact.model_copy(update={
        "links": [
            *exact.links,
            PhysicalWorkspaceLinkObservation(
                class_name="Antenna", device_a="ManualAP", port_a="Port 1",
            ),
        ],
    })
    assert "antenna" in canonical_stage_workspace_error(foreign, topology).casefold()
