"""Execution can measure unknown PoE without acquiring delivery authority."""
from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage, compose_cp_scale_canonical,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    canonical_required_capability_probes, canonical_stage_configuration_error,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus, EvidenceSource, PoEAuthorizedBinding,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult, ActionExecutionStatus, ConfigurationApplicationResult,
    ConfigurationApplicationStatus, FieldVerificationStatus, VerificationResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilitySnapshot, ProbeSession, ProbeSessionResult,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)
from tests.test_poe_delivery_provider import _manual_delivery_result

BUILD = "9.0.1.0858"
EXACT = PoEAuthorizedBinding("FastEthernet0/1", "7960", "Switch")


def _store(tmp_path, *, evidence="none"):
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    if evidence == "none":
        return store
    result = _manual_delivery_result(with_session_safety=evidence != "legacy")
    result.packet_tracer_version = BUILD
    result.dimensions["poe_delivery_packet_tracer_build"] = BUILD
    if evidence in {"phone_ip", "voice_registration", "ap_connectivity"}:
        result.probe_id = evidence
        result.evidence_source = EvidenceSource.PACKET_TRACER_RUNTIME
        result.dimensions = {"operational_observation": evidence}
    if evidence == "incomplete":
        result.dimensions.pop("poe_delivery_comparison_states")
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=BUILD,
        session=ProbeSessionResult(
            session=ProbeSession(session_id="synthetic-admission", packet_tracer_version=BUILD),
            results=[result],
        ),
    ))
    return store


def _compose(store):
    composition = compose_cp_scale_canonical(
        packet_tracer_version=BUILD, capability_store=store,
    )
    assert composition.valid, composition.issues
    assert composition.topology is not None
    return composition


def test_exact_verified_binding_survives_executable_canonical_composition(tmp_path):
    composition = _compose(_store(tmp_path, evidence="exact"))
    capabilities = composition.capabilities["3560-24PS"]
    assert capabilities.supports_poe is CapabilityStatus.SUPPORTED
    assert capabilities.poe_ports == 1
    assert capabilities.poe_authorized_bindings == [EXACT]
    switches = [d for s in composition.hardware_plan.site_hardware for d in s.devices
                if d.selected_model == "3560-24PS"]
    assert all(d.poe_capacity == 1 for d in switches)
    assert all(d.poe_authorized_bindings == [EXACT] for d in switches)


def test_unverified_bindings_are_carried_without_supported_claims(tmp_path):
    composition = _compose(_store(tmp_path, evidence="exact"))
    mls5 = next(d for s in composition.hardware_plan.site_hardware for d in s.devices
                if d.semantic_name == "MLS5")
    assert mls5.poe_uncertainty is not None
    assert mls5.poe_uncertainty.required_simultaneous_ports == 8
    assert EXACT not in mls5.poe_uncertainty.unverified_bindings
    assert PoEAuthorizedBinding("FastEthernet0/2", "7960", "Switch") in (
        mls5.poe_uncertainty.unverified_bindings
    )
    link = next(link for link in composition.topology.links
                if link.device_a_id == mls5.id and link.port_a == "FastEthernet0/2")
    assert link.metadata["poe_delivery_claim"] == "unknown"
    assert composition.capabilities["3650-24PS"].supports_poe is CapabilityStatus.UNKNOWN


def test_unknown_poe_alone_does_not_remove_any_canonical_devices_or_links(tmp_path):
    composition = _compose(_store(tmp_path))
    assert len(composition.topology.devices) == 314
    assert len(composition.topology.links) == 219
    assert composition.hardware_plan.status.value == "executable_with_unverified_poe"
    uncertainties = [d.poe_uncertainty for s in composition.hardware_plan.site_hardware
                     for d in s.devices if d.poe_uncertainty is not None]
    assert sum(len(u.required_bindings) for u in uncertainties) == 86
    assert sum(d.requires_poe for d in composition.topology.devices) == 86
    for model in ("3560-24PS", "3650-24PS"):
        assert composition.capabilities[model].supports_poe is CapabilityStatus.UNKNOWN
        assert composition.capabilities[model].poe_authorized_bindings == []


def test_router0_live_projection_keeps_phone_ap_uncertainty_and_runtime_plans(tmp_path):
    composition = _compose(_store(tmp_path))
    stage = project_cp_scale_canonical_stage(composition, CPScaleCanonicalStage.ROUTER0_BRANCH)
    assert len(stage.topology.devices) == 290
    assert len(stage.topology.links) == 202
    assert sum(d.enterprise_role == "ip_phone" for d in stage.topology.devices) == 62
    assert sum(d.enterprise_role == "access_point" for d in stage.topology.devices) == 15
    assert stage.voice is not None and stage.configuration.actions
    assert stage.control_plane.actions
    assert any(link.metadata.get("poe_delivery_claim") == "unknown"
               for link in stage.topology.links)
    assert all("supports_poe" not in probes
               for probes in canonical_required_capability_probes(composition).values())


@pytest.mark.parametrize("observation", ["phone_ip", "voice_registration", "ap_connectivity"])
def test_operational_success_never_acquires_poe_delivery_authority(tmp_path, observation):
    composition = _compose(_store(tmp_path, evidence=observation))
    capabilities = composition.capabilities["3560-24PS"]
    assert capabilities.supports_poe is CapabilityStatus.UNKNOWN
    assert capabilities.poe_ports is None
    assert capabilities.poe_authorized_bindings == []


@pytest.mark.parametrize("status", [ActionExecutionStatus.FAILED, ActionExecutionStatus.UNKNOWN])
def test_executable_unknown_poe_does_not_accept_failed_or_unknown_runtime_verification(tmp_path, status):
    composition = _compose(_store(tmp_path))
    stage = project_cp_scale_canonical_stage(composition, CPScaleCanonicalStage.ROUTER0_BRANCH)
    plan = stage.configuration
    result = ConfigurationApplicationResult(
        config_plan_id=plan.id, config_semantic_hash=plan.semantic_hash,
        source_topology_hash=plan.source_topology_hash,
        status=ConfigurationApplicationStatus.FAILED,
        action_results=[ActionApplicationResult(action_id=a.id, status=ActionExecutionStatus.APPLIED)
                        for a in plan.actions],
        mutation_action_ids=[a.id for a in plan.actions],
        verification_results=[VerificationResult(
            expectation_id=e.id, action_id=e.action_id,
            status=status, fresh_evidence=status is ActionExecutionStatus.FAILED,
            fields={"runtime_state": FieldVerificationStatus(status.value)},
        ) for e in plan.verification_expectations],
    )
    reason = canonical_stage_configuration_error(plan, result)
    assert status.value in reason.casefold()
    assert all(r.status is status for r in result.verification_results)
    assert composition.capabilities["3560-24PS"].supports_poe is CapabilityStatus.UNKNOWN


@pytest.mark.parametrize("evidence", ["legacy", "incomplete"])
def test_legacy_or_incomplete_poe_remains_unknown_while_execution_is_admitted(tmp_path, evidence):
    composition = _compose(_store(tmp_path, evidence=evidence))
    capabilities = composition.capabilities["3560-24PS"]
    assert capabilities.supports_poe is CapabilityStatus.UNKNOWN
    assert capabilities.poe_ports is None
    assert capabilities.poe_authorized_bindings == []


@pytest.mark.parametrize("corruption", ["count", "extra", "missing_member", "missing_simultaneous_uncertainty"])
def test_compiler_reconciles_uncertainty_with_actual_powered_attachment_scope(tmp_path, corruption):
    from src.packet_tracer_mcp.application.use_cases.compile_enterprise import compile_enterprise_topology
    from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import PacketTracerTopologyCatalogAdapter

    composition = _compose(_store(tmp_path, evidence="exact"))
    hardware = composition.hardware_plan.model_copy(deep=True)
    switch = next(d for s in hardware.site_hardware for d in s.devices if d.semantic_name == "MLS5")
    uncertainty = switch.poe_uncertainty
    if corruption == "count":
        uncertainty.required_simultaneous_ports += 1
    elif corruption == "extra":
        extra = PoEAuthorizedBinding("FastEthernet0/24", "7960", "Switch")
        uncertainty.required_bindings.append(extra)
        uncertainty.unverified_bindings.append(extra)
        uncertainty.required_simultaneous_ports += 1
    elif corruption == "missing_member":
        uncertainty.required_bindings.remove(EXACT)
        uncertainty.required_simultaneous_ports -= 1
    else:
        # Exact union of independent single-port episodes is not simultaneous capacity.
        switch.poe_authorized_bindings = list(uncertainty.required_bindings)
        switch.poe_uncertainty = None
        assert switch.poe_capacity == 1
    catalog = PacketTracerTopologyCatalogAdapter()
    result = compile_enterprise_topology(composition.enterprise, hardware,
                                        catalog.compilation_profile(), catalog.cable_for)
    assert not result.is_valid
    assert result.plan is None
    assert any("PoE" in issue.message and "uncertainty" in issue.message for issue in result.issues)


def test_range_assigned_endpoint_link_preserves_its_unverified_poe_marker(tmp_path):
    from src.packet_tracer_mcp.application.use_cases.compile_enterprise import compile_enterprise_topology
    from src.packet_tracer_mcp.domain.enterprise.models.hardware import PortAssignmentRange
    from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
    from src.packet_tracer_mcp.infrastructure.catalog.enterprise_topology import PacketTracerTopologyCatalogAdapter

    composition = _compose(_store(tmp_path))
    hardware = composition.hardware_plan.model_copy(deep=True)
    site = next(s for s in hardware.site_hardware if any(d.semantic_name == "MLS5" for d in s.devices))
    switch = next(d for d in site.devices if d.semantic_name == "MLS5")
    binding = next(b for b in site.endpoint_bindings if b.device_id == switch.id and b.device_port == "FastEthernet0/2")
    endpoint = next(d for d in composition.topology.devices if d.id == binding.endpoint_id)
    site.endpoint_bindings.remove(binding)
    block = next(b for b in site.access_blocks if switch.id in b.switches)
    block.port_assignments.append(PortAssignmentRange(
        device_id=switch.id, source_group=endpoint.metadata["source_group"],
        roles=[DeviceRole.IP_PHONE], start_index=int(endpoint.metadata["source_index"]),
        count=1, first_port=binding.device_port, last_port=binding.device_port, requires_poe=True,
    ))
    catalog = PacketTracerTopologyCatalogAdapter()
    result = compile_enterprise_topology(composition.enterprise, hardware,
                                        catalog.compilation_profile(), catalog.cable_for)
    assert result.is_valid, result.issues
    link = next(link for link in result.plan.links if link.device_b_id == endpoint.id)
    assert link.metadata.get("poe_delivery_claim") == "unknown"


def test_stage_poe_journal_retains_exact_claim_ceiling_and_unverified_demand(tmp_path):
    import json
    from src.packet_tracer_mcp.application.use_cases import qualify_cp_scale_live as live

    composition = _compose(_store(tmp_path, evidence="exact"))
    stage = project_cp_scale_canonical_stage(composition, CPScaleCanonicalStage.ROUTER0_BRANCH)
    switch = next(d for d in stage.topology.devices if d.name == "MLS5")
    assert json.loads(switch.metadata.get("poe_authorized_bindings", "[]")) == [
        {"switch_port": "FastEthernet0/1", "endpoint_model": "7960", "endpoint_port": "Switch"},
    ]
    snapshot = live.canonical_stage_poe_admission(stage.topology)
    record = next(item for item in snapshot if item["device_name"] == "MLS5")
    assert record["evidenced_simultaneous_ports"] == 1
    assert record["authorized_bindings"] == json.loads(switch.metadata["poe_authorized_bindings"])
    assert record["uncertainty"]["required_simultaneous_ports"] == 8
    assert len(record["uncertainty"]["unverified_bindings"]) == 7
    assert json.loads(json.dumps(snapshot)) == snapshot
