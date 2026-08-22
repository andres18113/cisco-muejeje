"""Point A hardware admission consumes only exact-build typed PoE evidence."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
    plan_enterprise_hardware,
)
from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
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


def _save_supported_3560(store: CapabilitySnapshotStore, version: str = BUILD) -> None:
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


def test_stage_a_switches_become_eligible_only_from_matching_poe_evidence(tmp_path):
    store = CapabilitySnapshotStore(tmp_path / "capabilities")

    before = plan_enterprise_hardware(
        _stage_a_plan(), packet_tracer_version=BUILD, capability_store=store,
    )
    before_access = _access_devices(before)
    assert before.plan.status.value == "partially_resolved"
    assert {item.provisional_model for item in before_access} == {"2950T-24"}
    assert all(item.selected_model is None for item in before_access)

    _save_supported_3560(store)
    after = plan_enterprise_hardware(
        _stage_a_plan(), packet_tracer_version=BUILD, capability_store=store,
    )
    after_access = _access_devices(after)
    assert after.plan.status.value == "valid"
    assert len(after_access) == 2
    assert {item.selected_model for item in after_access} == {"3560-24PS"}
    assert all(item.provisional_model is None for item in after_access)
    assert all(item.poe_capacity == 24 for item in after_access)


def test_poe_evidence_does_not_cross_model_or_build_and_names_do_not_promote(tmp_path):
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _save_supported_3560(store)
    adapter = packet_tracer_enterprise_capability_adapter(BUILD, store=store)

    measured = adapter.capabilities_for("3560-24PS", BUILD)
    wrong_model = adapter.capabilities_for("2950T-24", BUILD)
    wrong_build = adapter.capabilities_for("3560-24PS", "9.0.1.9999")
    unmeasured_named_model = packet_tracer_enterprise_capability_adapter(
        BUILD, store=CapabilitySnapshotStore(tmp_path / "empty"),
    ).capabilities_for("3560-24PS", BUILD)

    assert measured is not None and measured.supports_poe is CapabilityStatus.SUPPORTED
    assert wrong_model is not None and wrong_model.supports_poe is CapabilityStatus.UNKNOWN
    assert wrong_build is not None and wrong_build.supports_poe is CapabilityStatus.UNKNOWN
    assert unmeasured_named_model is not None
    assert unmeasured_named_model.supports_poe is CapabilityStatus.UNKNOWN


def test_stage_a_does_not_allocate_the_819_duplicate_port_alias(tmp_path):
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    _save_supported_3560(store)

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
    assert router_ports == {"FastEthernet0", "FastEthernet1"}
    assert "Ethernet1" not in router_ports
