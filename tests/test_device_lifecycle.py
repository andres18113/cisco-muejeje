"""E3.6.2: ciclo de vida temporal y bloqueo de probes configurables."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.capability_discovery import CapabilityDiscoveryService
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    DeviceInitializationState,
    ProbeExecutionStatus,
    ProbeRequest,
    RuntimeDeviceObservation,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import EnterpriseCapabilityAdapter
from src.packet_tracer_mcp.infrastructure.execution.device_lifecycle import DeviceReadinessWaiter
from src.packet_tracer_mcp.infrastructure.execution.fake_probe_runtime import FakePacketTracerProbeRuntime
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import CapabilitySnapshotStore


def test_readiness_waiter_returns_ready_after_bounded_polling():
    values = iter((
        {"found": True, "configuration_channel": False},
        {"found": True, "configuration_channel": True, "components_seen": ["VlanManager"]},
    ))
    now = [0.0]
    waiter = DeviceReadinessWaiter(
        lambda: next(values), timeout_seconds=1.0, interval_seconds=0.1,
        clock=lambda: now[0], sleeper=lambda interval: now.__setitem__(0, now[0] + interval),
    )

    result = waiter.wait()

    assert result.state is DeviceInitializationState.CONFIGURATION_READY
    assert result.attempts == 2
    assert result.components_seen == ["VlanManager"]


def test_readiness_waiter_times_out_with_last_diagnostics():
    now = [0.0]
    waiter = DeviceReadinessWaiter(
        lambda: {"found": True, "configuration_channel": False, "command_prompt": False},
        timeout_seconds=0.2, interval_seconds=0.1,
        clock=lambda: now[0], sleeper=lambda interval: now.__setitem__(0, now[0] + interval),
    )

    result = waiter.wait()

    assert result.state is DeviceInitializationState.TIMEOUT
    assert result.attempts == 3
    assert not result.configuration_channel


def test_no_configurable_probe_runs_when_configuration_channel_is_unavailable(tmp_path):
    unavailable = CapabilityProbeResult(
        probe_id="configuration-channel", model="2960-24TT", capability="configuration_channel",
        execution_status=ProbeExecutionStatus.TIMEOUT, evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
    )
    vlan = CapabilityProbeResult(
        probe_id="vlan-probe", model="2960-24TT", capability="supports_vlan",
        status=CapabilityStatus.SUPPORTED, execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.CONTROLLED_PROBE,
    )
    runtime = FakePacketTracerProbeRuntime(
        {"2960-24TT": RuntimeDeviceObservation(found=True, runtime_id="2960-24TT")},
        {("2960-24TT", "configuration_channel"): unavailable, ("2960-24TT", "supports_vlan"): vlan},
    )
    service = CapabilityDiscoveryService(
        runtime, CapabilitySnapshotStore(tmp_path / "capabilities"), EnterpriseCapabilityAdapter().identity_for,
    )

    snapshot, _ = service.run(ProbeRequest(models=["2960-24TT"], capabilities=["supports_vlan"], force=True))
    results = {result.capability: result for result in snapshot.session.results}

    assert results["configuration_channel"].execution_status is ProbeExecutionStatus.TIMEOUT
    assert results["supports_vlan"].execution_status is ProbeExecutionStatus.SKIPPED
