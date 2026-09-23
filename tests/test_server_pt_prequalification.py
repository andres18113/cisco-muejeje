"""Authorized preliminary Server-PT port and 2950 trunk qualifications."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilityVerificationMethod,
    ProbeExecutionStatus,
    RuntimeDeviceObservation,
)
from packet_tracer_mcp.domain.enterprise.models.execution import MutationDisposition
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeviceObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)


class _Physical:
    def __init__(self) -> None:
        self.devices: dict[str, str] = {}
        self.events: list[str] = []

    def observe_workspace(self):
        self.events.append("workspace")
        return PhysicalWorkspaceObservation(
            devices=[
                PhysicalWorkspaceDeviceObservation(name=name, model=model)
                for name, model in sorted(self.devices.items())
            ]
        )

    def ensure_device(self, device):
        self.events.append("create:" + device.name)
        self.devices[device.name] = device.model
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def observe_device(self, device):
        self.events.append("observe:" + device.name)
        return PhysicalDeviceObservation(
            target_id=device.id,
            observed=device.name in self.devices,
            deployed_name=device.name,
            model=self.devices.get(device.name, ""),
            interfaces=["FastEthernet0"],
        )

    def remove_device(self, device):
        self.events.append("remove:" + device.name)
        self.devices.pop(device.name, None)
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )


class _TrunkProbe:
    def __init__(self, physical: _Physical, *, supported: bool = True) -> None:
        self.physical = physical
        self.supported = supported
        self.calls: list[str] = []

    def create_temporary_device(self, model, name):
        self.calls.append("create")
        self.physical.devices[name] = model
        return RuntimeDeviceObservation(found=True, runtime_id=model, display_name=name)

    def probe_capability(self, name, capability, definition):
        self.calls.append("probe:" + capability)
        return CapabilityProbeResult(
            probe_id=definition.id,
            model="2950T-24",
            capability=capability,
            status=(
                CapabilityStatus.SUPPORTED
                if self.supported
                else CapabilityStatus.UNKNOWN
            ),
            execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE,
            verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
            configured=True,
            verified=self.supported,
            raw_summary="controlled exact-build trunk readback",
            packet_tracer_version="9.0.1.0858",
        )

    def delete_temporary_device(self, name):
        self.calls.append("delete")
        self.physical.devices.pop(name, None)
        return True


def test_prequalification_retains_both_results_and_two_restoration_reads(
    tmp_path: Path,
):
    """The existing port qualifier and trunk probe both return observed data."""
    from packet_tracer_mcp.application.use_cases.prequalify_server_pt import (
        prequalify_server_pt,
    )
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    physical = _Physical()
    probe = _TrunkProbe(physical)
    result = prequalify_server_pt(physical, probe, attempt_token="0f1e2d")

    assert result.ready_for_catalog_review is True
    assert result.server_port_inventory is not None
    assert result.server_port_inventory.ports == ["FastEthernet0"]
    assert result.trunk_probe is not None
    assert result.trunk_probe.status is CapabilityStatus.SUPPORTED
    assert result.first_restoration is not None
    assert result.second_restoration is not None
    assert physical.devices == {}
    assert probe.calls == ["create", "probe:supports_trunk", "delete"]
    store = ServerPtCommissioningStore(tmp_path)
    store.save_prequalification("attempt-01", result)
    assert store.load_prequalification("attempt-01") == result


def test_unknown_trunk_result_stays_unqualified_after_cleanup():
    """Cleanup does not promote an unverified trunk observation."""
    from packet_tracer_mcp.application.use_cases.prequalify_server_pt import (
        prequalify_server_pt,
    )

    physical = _Physical()
    result = prequalify_server_pt(
        physical, _TrunkProbe(physical, supported=False), attempt_token="0f1e2d"
    )

    assert result.ready_for_catalog_review is False
    assert result.server_port_inventory is not None
    assert physical.devices == {}


def test_duplicate_trunk_name_is_never_deleted_without_creation_proof():
    """A raced foreign name remains untouched when creation is refused."""
    from packet_tracer_mcp.application.use_cases.prequalify_server_pt import (
        prequalify_server_pt,
    )

    physical = _Physical()

    class Duplicate(_TrunkProbe):
        def create_temporary_device(self, model, name):
            self.physical.devices[name] = model
            self.calls.append("duplicate")
            return RuntimeDeviceObservation(found=False, error="duplicate probe name")

    probe = Duplicate(physical)
    result = prequalify_server_pt(physical, probe, attempt_token="0f1e2d")

    assert result.ready_for_catalog_review is False
    assert probe.calls == ["duplicate"]
    assert physical.devices[result.trunk_name] == "2950T-24"


def test_owned_cleanup_uses_the_reserved_phase_scope():
    """Both temporary removals can still dispatch after ordinary probes stop."""
    from packet_tracer_mcp.application.use_cases.prequalify_server_pt import (
        prequalify_server_pt,
    )

    active = [False]

    @contextmanager
    def cleanup_scope():
        active[0] = True
        try:
            yield
        finally:
            active[0] = False

    class Physical(_Physical):
        def remove_device(self, device):
            assert active[0]
            return super().remove_device(device)

    class Probe(_TrunkProbe):
        def delete_temporary_device(self, name):
            assert active[0]
            return super().delete_temporary_device(name)

    physical = Physical()
    result = prequalify_server_pt(
        physical,
        Probe(physical),
        attempt_token="0f1e2d",
        cleanup_scope=cleanup_scope,
    )

    assert result.ready_for_catalog_review
    assert active == [False]


def test_preliminary_probe_can_bound_its_operational_boot_wait():
    """The C31 probe need not spend the generic 90-second boot allowance."""
    from packet_tracer_mcp.infrastructure.execution.probe_runtime import (
        PacketTracerBridgeProbeRuntime,
    )

    runtime = PacketTracerBridgeProbeRuntime(
        lambda _script, _timeout: '{"found":true,"booting":true,"terminal":false}',
        operational_readiness_seconds=0.0,
    )
    result = runtime._wait_for_operational_readiness("__MCP_PROBE_C31", "2950T-24")

    assert result.attempts == 1
    assert result.configuration_channel is False


def test_scoped_evidence_admits_setup_without_global_capability_promotion():
    """Only this measured campaign uses Server ports and 2950 trunk support."""
    from packet_tracer_mcp.application.use_cases.prequalify_server_pt import (
        prequalify_server_pt,
    )
    from packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
        backend_verified_port_inventory,
    )
    from packet_tracer_mcp.infrastructure.catalog.server_pt_commissioning_evidence import (
        scoped_setup_evidence,
    )

    physical = _Physical()
    result = prequalify_server_pt(
        physical, _TrunkProbe(physical), attempt_token="0f1e2d"
    )
    catalog, ports = scoped_setup_evidence(result)

    assert catalog.capabilities_for("2950T-24", "9.0.1.0858").supports_trunk is (
        CapabilityStatus.SUPPORTED
    )
    assert ports("Server-PT", backend_version="9.0.1.0858").permits(["FastEthernet0"])
    assert not backend_verified_port_inventory(
        "Server-PT", backend_version="9.0.1.0858"
    ).backend_verified
