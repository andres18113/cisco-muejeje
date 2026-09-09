"""Offline contracts for the extracted coordinator and sole session owner."""
from __future__ import annotations

import importlib.util

import pytest

from tests.test_cp_scale_router0_live_runner import RUN_DOUBLES, _probe


def test_application_coordinator_is_available_without_loading_the_tool():
    spec = importlib.util.find_spec(
        "src.packet_tracer_mcp.application.cp_scale_live.coordinator"
    )
    assert spec is not None, "The coordinator still lives in the executable tool"


@pytest.mark.parametrize("failure", ["start", "physical", "configuration", "cancel"])
def test_partial_session_acquisition_closes_the_acquired_transport_once(failure):
    spec = importlib.util.find_spec(
        "src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_session"
    )
    assert spec is not None, "There is no session owner before partial acquisition"
    from src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_session import (
        PacketTracerCPScaleSession,
    )

    events = []

    class Transport:
        def start(self, **kwargs):
            events.append("start")
            if failure == "start":
                raise RuntimeError("start failed")
            if failure == "cancel":
                raise KeyboardInterrupt("cancelled")
            return True

        def stop(self):
            events.append("stop")

    transport = Transport()

    def physical_factory(transport):
        events.append("physical")
        if failure == "physical":
            raise RuntimeError("physical failed")
        return object()

    def runtime_factory(transport, physical):
        events.append("configuration")
        raise RuntimeError("configuration failed")

    session = PacketTracerCPScaleSession(
        transport_factory=lambda: transport,
        physical_factory=physical_factory,
        runtime_factory=runtime_factory,
    )
    try:
        with pytest.raises((RuntimeError, KeyboardInterrupt)):
            session.start()
            session.acquire_runtimes()
    finally:
        session.close()
    session.close()
    assert events == {
        "start": ["start", "stop"],
        "cancel": ["start", "stop"],
        "physical": ["start", "physical", "stop"],
        "configuration": ["start", "physical", "configuration", "stop"],
    }[failure]


def test_session_reuses_resources_and_marks_close_before_a_failing_stop():
    spec = importlib.util.find_spec(
        "src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_session"
    )
    assert spec is not None, "Session identity and idempotent close are missing"
    from src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_session import (
        PacketTracerCPScaleSession,
    )

    calls = []
    physical = object()
    runtimes = object()

    class Transport:
        def start(self, **kwargs):
            calls.append("start")
            return True

        def stop(self):
            calls.append("stop")
            raise OSError("closed channel")

    transport = Transport()

    def acquire(value, physical_value):
        assert value is transport and physical_value is physical
        calls.append("runtimes")
        return runtimes

    session = PacketTracerCPScaleSession(
        transport_factory=lambda: transport,
        physical_factory=lambda value: physical,
        runtime_factory=acquire,
    )
    assert session.start() is True
    assert session.start() is True
    assert session.physical is physical
    assert session.acquire_runtimes() is runtimes
    assert session.acquire_runtimes() is runtimes
    with pytest.raises(OSError, match="closed channel"):
        session.close()
    session.close()
    assert calls == ["start", "runtimes", "stop"]


def test_real_coordinator_keeps_typed_continuity_identity_and_terminal_order():
    verdict = _probe(RUN_DOUBLES + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
coordinator = offline_coordinator(request)
assert type(coordinator) is CPScaleLiveCoordinator
result = coordinator.run(request)
completed = result.progress.completed_stages
assert len(stage_requests) == len(completed) == 6
for index in range(1, 6):
    continuity = stage_requests[index].continuity
    prior = completed[index - 1]
    assert continuity.previous_projection is prior.projection
    assert continuity.previous_configuration is prior.configuration
    assert continuity.last_workspace is prior.workspace
    assert continuity.previous_control_plane_action_results == prior.control_plane.action_results
    assert continuity.verified_serial_manifest is completed[0].manifest
print(json.dumps({"outcome": result.outcome.value, "stages": [item.stage.value for item in completed],
    "calls": [item["event"] for item in calls[-6:]], "retained": result.presentation_retained,
    "cleanup": result.cleanup.verified, "primary": result.primary_failure,
    "secondary": result.secondary_failures}))
''')
    assert verdict == {
        "outcome": "completed", "stages": ["routing-core", "router4-switch10", "floor1", "floor2", "floor3", "router0-branch"],
        "calls": ["execute_stage", "archive", "cleanup", "archive", "summary", "transport.stop"],
        "retained": False, "cleanup": True, "primary": None, "secondary": [],
    }


@pytest.mark.parametrize("cancel", [False, True])
def test_generic_terminal_obligations_preserve_order_and_cancellation(cancel):
    from src.packet_tracer_mcp.application.cp_scale_live.lifecycle import finalize_session

    calls = []
    reports = []

    class Session:
        def close(self):
            calls.append("close")
            raise OSError("close failed")

    def write():
        calls.append("write")
        if cancel:
            raise KeyboardInterrupt("cancel write")
        raise OSError("write failed")

    def invoke():
        return finalize_session(prepare=lambda: calls.append("prepare"), write=write,
                                session=Session(), report=reports.append)

    if cancel:
        with pytest.raises(KeyboardInterrupt, match="cancel write"):
            invoke()
        assert reports == [("transport_stop: OSError: close failed",)]
    else:
        result = invoke()
        assert result.errors == ("final_evidence_write: OSError: write failed", "transport_stop: OSError: close failed")
        assert reports == [result.errors]
    assert calls == ["prepare", "write", "close"]


def test_backend_qualification_exposes_original_snapshot_before_serialization():
    from types import SimpleNamespace
    from src.packet_tracer_mcp.application.cp_scale_live import run_contracts
    assert hasattr(run_contracts, "CPScaleCapabilityQualification"), "Backend still serializes capability evidence inside application"
    from src.packet_tracer_mcp.application.cp_scale_live.backend import CPScaleBackendQualification
    from src.packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus

    def forbidden_serialization():
        raise AssertionError("Application serialized the acquired capability snapshot")

    snapshot = SimpleNamespace(compact_summary=forbidden_serialization)
    composition = SimpleNamespace(valid=True, topology=object(), configuration=object(), control_plane=object(),
                                  capabilities={"switch": SimpleNamespace(poe=CapabilityStatus.SUPPORTED)})
    first, second = object(), object()
    reads = iter((first, second))
    session = SimpleNamespace(physical=SimpleNamespace(observe_workspace=lambda: next(reads)))
    report = SimpleNamespace(packet_tracer_version="9.0.1.0858", baseline=object())
    backend = CPScaleBackendQualification(compose=lambda **kwargs: composition,
        discovery_factory=lambda session, version: SimpleNamespace(run=lambda request: (snapshot, False)),
        requirements=lambda composition: {"switch": ["poe"]}, probe_error=lambda *args, **kwargs: "",
        restoration_error=lambda *args: "")
    backend.validate_composition(composition)
    discovery = backend.discovery_factory(session, report.packet_tracer_version)
    acquired = backend.probe(discovery, report.packet_tracer_version, "switch", ("poe",))
    assert acquired.snapshot is snapshot
    assert acquired.model == "switch" and acquired.required == ("poe",)
    assert backend.unresolved(composition, (("switch", ("poe",)),)) == ()


def test_same_coordinator_mechanism_accepts_a_second_synthetic_target_sequence():
    verdict = _probe(RUN_DOUBLES + r'''
from dataclasses import replace
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False)
coordinator = offline_coordinator(request)
original_preflight = coordinator.preflight
def inspect(request, **kwargs):
    result = original_preflight.inspect(request, **kwargs)
    return replace(result, target=replace(result.target, build_stages=(CPScaleCanonicalStage.FLOOR3, CPScaleCanonicalStage.ROUTING_CORE)))
coordinator.preflight = SimpleNamespace(inspect=inspect)
coordinator.build.reconcile = lambda topology, physical, **kwargs: Deployment()
coordinator.build.full_projection = lambda composition: projection_for(composition, CPScaleCanonicalStage.REMAINING)
coordinator.backend.compose = lambda **kwargs: SimpleNamespace(valid=True, topology=SimpleNamespace(devices=[], links=[]),
    configuration=object(), control_plane=object(), capabilities={}, voice=None)
seams._write_checkpoint_summary = lambda stage, evidence, **kwargs: record("summary", stage=stage)
result = coordinator.run(request)
assert stage_requests[1].continuity.previous_projection is result.progress.completed_stages[0].projection
assert result.progress.full_qualification.projection is stage_requests[-1].projection
print(json.dumps({"outcome": result.outcome.value,
    "stages": [item.stage.value for item in result.progress.completed_stages],
    "remaining": result.progress.remaining_reconciled,
    "archives": len(result.archives), "closed": [item for item in calls if item["event"] == "transport.stop"]}))
''')
    assert verdict == {"outcome": "completed", "stages": ["floor3", "routing-core"],
                       "remaining": True, "archives": 2, "closed": [{"event": "transport.stop"}]}


@pytest.mark.parametrize("publication_failure", ["", "write", "cancel"])
def test_integrated_real_executor_persistence_cleanup_and_session_preserve_failure(tmp_path, publication_failure):
    import json
    from dataclasses import replace
    from types import SimpleNamespace
    from tests.cp_scale_stage_fixture import stage_fixture
    from tests.test_cp_scale_live_local_preflight import _service, _request
    from src.packet_tracer_mcp.application.cp_scale_live.backend import CPScaleBackendQualification
    from src.packet_tracer_mcp.application.cp_scale_live.build_policy import CPScaleBuildPolicy
    from src.packet_tracer_mcp.application.cp_scale_live.cleanup import CPScaleCleanup
    from src.packet_tracer_mcp.application.cp_scale_live.completion import CPScaleCompletion
    from src.packet_tracer_mcp.application.cp_scale_live.coordinator import CPScaleLiveCoordinator
    from src.packet_tracer_mcp.application.cp_scale_live.stage_executor import CPScaleStageExecutor
    from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import CPScaleCleanupRealtime, CPScaleRealtimeState
    from src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_session import PacketTracerCPScaleSession
    from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_live import CPScaleLivePersistence
    from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
        PhysicalDeploymentItemResult, PhysicalDeploymentItemStatus, PhysicalObjectKind,
        PhysicalMutationResult, PhysicalWorkspaceObservation,
    )
    from src.packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint, deployment_manifest_semantic_hash

    fixture = stage_fixture(CPScaleStageExecutor, unobservable=True)
    projection = fixture.request.projection
    deployment = fixture.request.deployment.model_copy(update={"item_results": [
        PhysicalDeploymentItemResult(target_id="r", target_kind=PhysicalObjectKind.DEVICE,
            status=PhysicalDeploymentItemStatus.APPLIED),
        PhysicalDeploymentItemResult(target_id="foreign", target_kind=PhysicalObjectKind.DEVICE,
            status=PhysicalDeploymentItemStatus.NOT_ATTEMPTED),
    ]})
    fingerprint = EnvironmentFingerprint(backend_version="9.0.1.0858", bridge_transport="http", runtime_mode="live")
    deployment.environment_fingerprint = fingerprint
    deployment.manifest.environment_fingerprint = fingerprint
    deployment.manifest.backend_version = fingerprint.backend_version
    deployment.manifest.semantic_hash = deployment_manifest_semantic_hash(deployment.manifest)
    composition = replace(fixture.request.composition, topology=projection.topology,
                          configuration=projection.configuration, control_plane=projection.control_plane)
    calls = []

    class Transport:
        bridge_transport = "http"
        is_connected = True
        def start(self, **kwargs):
            calls.append("start")
            return True
        def status_dict(self):
            return {"connected": True}
        def stop(self):
            calls.append("stop")

    class Physical:
        def observe_workspace(self):
            calls.append("workspace")
            return PhysicalWorkspaceObservation()
        def remove_device(self, device):
            calls.append("remove:" + device.id)
            return PhysicalMutationResult(target_id=device.id, target_kind=PhysicalObjectKind.DEVICE, applied=True)

    physical = Physical()
    session = PacketTracerCPScaleSession(transport_factory=Transport, physical_factory=lambda transport: physical,
                                        runtime_factory=lambda *args: SimpleNamespace())
    persistence = CPScaleLivePersistence(tmp_path)
    original_write = persistence.write_progress
    interrupted = []

    def write_progress(report):
        if publication_failure and report.active_stage and report.active_stage.delta and not interrupted:
            interrupted.append(True)
            if publication_failure == "cancel":
                raise KeyboardInterrupt("cancel acquired physical delta")
            raise OSError("cannot publish acquired physical delta")
        original_write(report)

    persistence.write_progress = write_progress
    presentation = SimpleNamespace(core_rematerialized=lambda: calls.append("core"),
        terminal=lambda *args: calls.append("terminal"), finalization_incomplete=lambda report: calls.append("report"))
    observations = SimpleNamespace(dhcp_target=lambda projection: None, activate=lambda projection: None,
                                   cleanup_realtime=lambda: CPScaleCleanupRealtime(True, state=CPScaleRealtimeState(observed=True, simulation_mode=False,
                                       present=("observed", "simulation_mode"))))
    coordinator = CPScaleLiveCoordinator(preflight=_service(), session_factory=lambda: session,
        stage_factory=lambda *args: fixture.executor, observations_factory=lambda session: observations,
        backend=CPScaleBackendQualification(compose=lambda **kwargs: composition,
            discovery_factory=lambda *args: object(), requirements=lambda composition: {}),
        build=CPScaleBuildPolicy(capabilities={}, project=lambda *args, **kwargs: projection,
            deployer_factory=lambda physical: SimpleNamespace(deploy=lambda *args, **kwargs: deployment),
            ownership_error=lambda *args: ""),
        checkpoint=SimpleNamespace(decide=lambda *args, **kwargs: pytest.fail("Failed stage reached checkpoint")),
        persistence=persistence, completion=CPScaleCompletion(cleanup=CPScaleCleanup()),
        presentation=presentation)
    if publication_failure:
        if publication_failure == "cancel":
            with pytest.raises(KeyboardInterrupt, match="cancel acquired physical delta"):
                coordinator.run(_request())
        else:
            result = coordinator.run(_request())
            assert result.primary_failure == "OSError: cannot publish acquired physical delta"
        assert calls == ["start", "workspace", "workspace", "workspace", "remove:r", "workspace", "workspace", "stop"]
        payload = json.loads(persistence.evidence_path.read_text(encoding="utf-8"))
        assert payload["cleanup"]["verified"] is True
        assert payload["cleanup"]["mutations"][0]["target_id"] == "r"
        assert [item["phase"] for item in payload["archives"]] == ["failure-precleanup", "cleanup"]
        return
    result = coordinator.run(_request())
    assert result.outcome.value == "failed"
    assert result.progress.completed_stages[0].configuration is fixture.configuration_results[0]
    assert result.progress.first_failed_boundary == "configuration"
    assert result.primary_failure == ("CanonicalLiveFailure: Configuration at 'routing-core' exceeded its governed "
                                      "observability envelope: Synthetic required readback was unobservable")
    assert result.cleanup.verified is True
    assert calls == ["start", "workspace", "workspace", "workspace", "remove:r", "workspace", "workspace", "stop"]
    payload = json.loads(persistence.evidence_path.read_text(encoding="utf-8"))
    assert payload["stages"][0]["stage_outcome"] == "failed"
    assert payload["stages"][0]["configuration_acceptance_error"] == "Synthetic required readback was unobservable"
    assert payload["failure"] == result.primary_failure
    assert [item.phase for item in result.archives] == ["failure-precleanup", "cleanup"]
