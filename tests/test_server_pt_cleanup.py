"""Owned C31 cleanup preserves results and proves two workspace restorations."""

from __future__ import annotations

from pathlib import Path

from test_server_pt_cleanup_ownership import _verified_e4

from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from packet_tracer_mcp.domain.enterprise.models.execution import MutationDisposition
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceLinkObservation,
    PhysicalWorkspaceObservation,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)

ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


class _OwnedCampus:
    def __init__(self, topology, *, foreign: bool = False) -> None:
        self.topology = topology
        self.devices = {item.name: item.model for item in topology.devices}
        if foreign:
            self.devices["Foreign"] = "PC-PT"
        self.links = {
            item.id: PhysicalWorkspaceLinkObservation(
                class_name=item.cable,
                device_a=item.device_a,
                port_a=item.port_a,
                device_b=item.device_b,
                port_b=item.port_b,
            )
            for item in topology.links
        }
        self.removals: list[str] = []

    def observe_workspace(self):
        return PhysicalWorkspaceObservation(
            devices=[
                PhysicalWorkspaceDeviceObservation(name=name, model=model)
                for name, model in sorted(self.devices.items())
            ],
            links=list(self.links.values()),
        )

    def adopt_verified_deployment_for_cleanup(self, topology, result):
        assert result.manifest is not None
        return frozenset(item.name for item in topology.devices)

    def remove_device(self, device):
        self.removals.append(device.name)
        self.devices.pop(device.name)
        self.links = {
            identifier: link
            for identifier, link in self.links.items()
            if device.name not in {link.device_a, link.device_b}
        }
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )


def _store(tmp_path: Path, topology, e4):
    store = ServerPtCommissioningStore(tmp_path)
    bundle = prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT)
    store.save_bundle(ATTEMPT, bundle)
    store.save_baseline(ATTEMPT, PhysicalWorkspaceObservation())
    store.save_e4(ATTEMPT, e4)
    return store


def test_cleanup_removes_only_owned_devices_and_records_two_empty_reads(tmp_path: Path):
    """Client release is followed by actual owned workspace restoration."""
    from packet_tracer_mcp.application.use_cases.cleanup_server_pt_commissioning import (
        run_server_pt_cleanup,
    )

    topology, e4 = _verified_e4()
    store = _store(tmp_path, topology, e4)
    physical = _OwnedCampus(topology)

    result = run_server_pt_cleanup(
        ATTEMPT, store=store, physical_runtime=physical, admission=lambda: ()
    )

    assert result.restored is True, result.errors
    assert len(physical.removals) == 35
    assert result.first_restoration is not None
    assert result.second_restoration is not None
    assert result.first_restoration.safe_for_disposable_mutation
    assert result.second_restoration.safe_for_disposable_mutation
    assert store.load_cleanup(ATTEMPT) == result


def test_foreign_precleanup_object_stops_before_any_removal(tmp_path: Path):
    """A foreign device cannot be swept away by the owned cleanup grant."""
    from packet_tracer_mcp.application.use_cases.cleanup_server_pt_commissioning import (
        run_server_pt_cleanup,
    )

    topology, e4 = _verified_e4()
    store = _store(tmp_path, topology, e4)
    physical = _OwnedCampus(topology, foreign=True)

    result = run_server_pt_cleanup(
        ATTEMPT, store=store, physical_runtime=physical, admission=lambda: ()
    )

    assert result.restored is False
    assert "precleanup_workspace_drift" in result.errors
    assert physical.removals == []
