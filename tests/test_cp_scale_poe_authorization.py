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
    CleanupStatus,
    LiveSessionSafetyEvidence,
    ProbeContext,
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
from src.packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    PoEDeliveryClaimScope,
    PoEDeliveryTestedBinding,
    encode_poe_delivery_dimensions,
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
    stable_sha256 = "a" * 64
    live_context = ProbeContext(
        probe_id="poe-delivery-qualification",
        probe_version="2",
        device_model="3560-24PS",
        inventory_restored=True,
        mutations=["temporary-device-attempt:fixture"],
        cleanup_status=CleanupStatus.CLEAN,
        result_status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        live_session_safety=LiveSessionSafetyEvidence(
            canonical_path="C:/fixture/canonical.pts",
            canonical_pre_run_sha256=stable_sha256,
            canonical_observed_post_run_sha256=stable_sha256,
            canonical_verified_sha256=stable_sha256,
            disposable_path="C:/fixture/disposable.pts",
            disposable_pre_run_sha256=stable_sha256,
            disposable_post_run_sha256=stable_sha256,
            unexpected_canonical_modification=False,
            disposable_modified=False,
            runtime_healthy=True,
            crash_detected=False,
            integrity_verified=True,
            session_reusable=True,
            positive_claim_allowed=True,
        ),
    )
    access_ports = tuple(
        f"FastEthernet0/{index}" for index in range(1, 25)
    )
    tested = tuple(
        PoEDeliveryTestedBinding(
            switch_port=port,
            comparison_port=port,
            endpoint_model="7960",
            endpoint_port="Switch",
            candidate_state="powered",
            comparison_state="not_powered",
            candidate_indicator="test fixture powered",
            comparison_indicator="test fixture dark",
            candidate_ready=True,
            comparison_ready=True,
        )
        for port in access_ports
    )
    dimensions = encode_poe_delivery_dimensions(PoEDeliveryClaimScope(
        candidate_model="3560-24PS",
        packet_tracer_build=version,
        access_ports=access_ports,
        tested_bindings=tested,
        active_bindings=tuple(item.authorized_binding for item in tested),
        simultaneous_active_ports=24,
        comparison_model="2960-24TT",
        observation_method="manual_visible_power_state",
        observer_id="synthetic-test-reviewer",
        observed_at="2026-09-04T15:00:00Z",
        cleanup_status="clean",
        inventory_restoration="restored",
    ))
    ap_tested = tuple(
        PoEDeliveryTestedBinding(
            switch_port=port,
            comparison_port=port,
            endpoint_model="AccessPoint-PT",
            endpoint_port="Port 0",
            candidate_state="powered",
            comparison_state="not_powered",
            candidate_indicator="test AP fixture powered",
            comparison_indicator="test AP fixture dark",
            candidate_ready=True,
            comparison_ready=True,
        )
        for port in access_ports
    )
    ap_dimensions = encode_poe_delivery_dimensions(PoEDeliveryClaimScope(
        candidate_model="3560-24PS",
        packet_tracer_build=version,
        access_ports=access_ports,
        tested_bindings=ap_tested,
        active_bindings=tuple(
            item.authorized_binding for item in ap_tested
        ),
        simultaneous_active_ports=24,
        comparison_model="2960-24TT",
        observation_method="manual_visible_power_state",
        observer_id="synthetic-test-reviewer",
        observed_at="2026-09-04T15:00:00Z",
        cleanup_status="clean",
        inventory_restoration="restored",
    ))
    results = [
        CapabilityProbeResult(
            probe_id="poe-inventory-v2",
            model="3560-24PS",
            capability="supports_poe",
            status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.MANUAL_VERIFICATION,
            verified=True,
            observed_value=24,
            packet_tracer_version=version,
            context=live_context,
            dimensions=dimensions,
        ),
        CapabilityProbeResult(
            probe_id="poe-delivery-ap-test-fixture",
            model="3560-24PS",
            capability="supports_poe",
            status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.MANUAL_VERIFICATION,
            verified=True,
            observed_value=24,
            packet_tracer_version=version,
            context=live_context,
            dimensions=ap_dimensions,
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
