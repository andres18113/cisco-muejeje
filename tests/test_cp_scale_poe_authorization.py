"""Point A hardware admission consumes only exact-build typed PoE evidence."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
    plan_enterprise_hardware,
)
from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    compose_cp_scale_canonical,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilitySnapshot,
    ProbeExecutionStatus,
    ProbeSession,
    ProbeSessionResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale import (
    CPScalePoint,
    cp_scale_intent_for,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    packet_tracer_enterprise_capability_adapter,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


BUILD = "9.0.1.0858"


def _stage_a_plan():
    designed = EnterpriseDesigner().design(cp_scale_intent_for(CPScalePoint.A))
    assert designed.validation.is_valid and designed.plan is not None
    return designed.plan


def _save_delivery_supported_3560(
    store: CapabilitySnapshotStore, version: str = BUILD,
) -> None:
    results = [
        CapabilityProbeResult(
            probe_id="poe-inventory-v2",
            model="3560-24PS",
            capability="supports_poe",
            status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
            verified=True,
            observed_value=24,
            packet_tracer_version=version,
            dimensions={
                "poe_access_port_count": "24",
                "poe_delivery_tested_ports": "24",
                "poe_delivery_active_ports": "24",
            },
        ),
        CapabilityProbeResult(
            probe_id="multilayer-intervlan-probe",
            model="3560-24PS",
            capability="layer3",
            status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE,
            verified=True,
            packet_tracer_version=version,
        ),
    ]
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=version,
        session=ProbeSessionResult(
            session=ProbeSession(session_id="poe-exact-build", packet_tracer_version=version),
            results=results,
        ),
    ))


def _access_devices(composition):
    return [
        device
        for site in composition.plan.site_hardware
        for device in site.devices
        if device.role is DeviceRole.ACCESS_SWITCH
    ]


def test_stage_a_switches_fail_closed_on_control_only_poe_baseline(tmp_path):
    store = CapabilitySnapshotStore(tmp_path / "capabilities")

    planned = plan_enterprise_hardware(
        _stage_a_plan(), packet_tracer_version=BUILD, capability_store=store,
    )
    access = _access_devices(planned)

    assert planned.plan.status.value == "partially_resolved"
    assert len(access) == 2
    assert all(item.selected_model is None for item in access)
    assert all(item.provisional_model is not None for item in access)
    assert all(item.poe_capacity is None for item in access)
    assert all(item.selection_status.value == "needs_verification" for item in access)
    assert all("PoE requiere evidencia" in item.warnings[0] for item in access)


def test_canonical_product_stops_before_topology_without_delivery_evidence():
    composition = compose_cp_scale_canonical(packet_tracer_version=BUILD)

    assert not composition.valid
    assert composition.topology is None
    assert composition.hardware_plan is not None
    assert composition.hardware_plan.status.value == "partially_resolved"
    assert any("hardware" in issue.casefold() for issue in composition.issues)


def test_poe_evidence_does_not_cross_model_or_build_and_names_do_not_promote(tmp_path):
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _save_delivery_supported_3560(store)
    adapter = packet_tracer_enterprise_capability_adapter(BUILD, store=store)

    measured = adapter.capabilities_for("3560-24PS", BUILD)
    wrong_model = adapter.capabilities_for("2950T-24", BUILD)
    wrong_build = adapter.capabilities_for("3560-24PS", "9.0.1.9999")

    assert measured is not None and measured.supports_poe is CapabilityStatus.SUPPORTED
    assert wrong_model is not None and wrong_model.supports_poe is CapabilityStatus.UNKNOWN
    assert wrong_build is not None and wrong_build.supports_poe is CapabilityStatus.UNKNOWN


def test_stage_a_uses_one_exact_routed_819_uplink_without_the_duplicate_alias(tmp_path):
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _save_delivery_supported_3560(store)

    composition = compose_enterprise_reference(
        cp_scale_intent_for(CPScalePoint.A),
        packet_tracer_version=BUILD,
        capability_store=store,
    )

    assert composition.valid and composition.topology is not None
    router = next(
        item for item in composition.topology.devices
        if item.model == "819HG-4G-IOX"
    )
    router_ports = {
        link.port_a if link.device_a_id == router.id else link.port_b
        for link in composition.topology.links
        if router.id in {link.device_a_id, link.device_b_id}
    }
    assert router_ports == {"GigabitEthernet0"}
    assert "Ethernet1" not in router_ports

    edge_links = [
        link for link in composition.topology.links
        if link.link_role == "edge_link"
    ]
    distribution_peers = [
        link for link in composition.topology.links
        if link.link_role == "redundant_link"
        and {link.device_a_id, link.device_b_id}.issubset({
            item.id for item in composition.topology.devices
            if item.network_layer == "distribution"
        })
    ]
    assert len(edge_links) == 1
    assert len(distribution_peers) == 1


def test_corrected_stage_a_identity_preserves_only_phone_and_ap_poe_demand(
    tmp_path,
):
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _save_delivery_supported_3560(store)

    composition = compose_enterprise_reference(
        cp_scale_intent_for(CPScalePoint.A),
        packet_tracer_version=BUILD,
        capability_store=store,
    )

    assert composition.valid and composition.topology is not None
    poe_devices = [
        item for item in composition.topology.devices if item.requires_poe
    ]
    assert {
        role: sum(item.enterprise_role == role for item in poe_devices)
        for role in {DeviceRole.IP_PHONE.value, DeviceRole.ACCESS_POINT.value}
    } == {
        DeviceRole.IP_PHONE.value: 21,
        DeviceRole.ACCESS_POINT.value: 3,
    }
    smoke = [
        item for item in composition.topology.devices
        if item.enterprise_role == DeviceRole.SMOKE_DETECTOR.value
    ]
    assert len(smoke) == 11
    assert {item.model for item in smoke} == {"Smoke Detector"}
    assert not any(item.requires_poe for item in smoke)

    blocks = [
        block
        for site in composition.hardware_plan.site_hardware
        for block in site.access_blocks
    ]
    assert len(blocks) == 1
    assert blocks[0].required_poe_ports == 29
