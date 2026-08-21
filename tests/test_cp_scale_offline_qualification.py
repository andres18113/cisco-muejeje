"""Authoritative offline qualification for the canonical CP-SCALE intent."""

from __future__ import annotations

import json

from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_offline import (
    qualify_cp_scale_offline,
    write_cp_scale_offline_artifacts,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneActionType,
    ControlPlaneVerificationKind,
    DynamicRoutingProtocol,
    StpMode,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import VoiceActionType
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from tests.test_cp_scale_layout import _LAYOUT


def _qualify():
    catalog = EnterpriseCapabilityAdapter()
    switch = next(
        item for item in catalog.hardware_candidates("switch")
        if item.model == "2960-24TT"
    )
    switch = switch.model_copy(update={
        "capabilities": switch.capabilities.model_copy(update={
            "supports_poe": CapabilityStatus.SUPPORTED,
            "poe_ports": 24,
            "layer3": CapabilityStatus.SUPPORTED,
        }),
    })
    router = next(
        item for item in catalog.hardware_candidates("router")
        if item.model == "2911"
    )
    return qualify_cp_scale_offline(
        switch_candidates=[switch],
        router_candidates=[router],
        layout_profile=_LAYOUT,
    )


def test_offline_qualification_covers_existing_scope_without_protocol_expansion():
    qualified = _qualify()

    assert qualified.valid
    assert qualified.topology is not None and qualified.topology.plan is not None
    assert qualified.configuration is not None and qualified.configuration.plan is not None
    assert qualified.control_plane is not None and qualified.control_plane.plan is not None
    assert qualified.voice is not None and qualified.voice.plan is not None
    assert qualified.topology.summary.workload_endpoints == 279
    assert qualified.topology.summary.access_points == 17
    assert qualified.topology.summary.devices == 318

    configuration = qualified.configuration.plan
    assert len(configuration.actions_of_type(
        ConfigurationActionType.CONFIGURE_SERIAL_CLOCK,
    )) == 3
    assert len(configuration.actions_of_type(
        ConfigurationActionType.CONFIGURE_DHCP_POOL,
    )) == 9
    assert all(
        30 in item.allowed_vlans
        for item in configuration.actions_of_type(ConfigurationActionType.CONFIGURE_TRUNK)
    )

    control = qualified.control_plane.plan
    stp = control.actions_of_type(ControlPlaneActionType.CONFIGURE_STP)
    assert {item.site_id for item in stp} == {
        "large-branch", "multilayer-branch", "small-branch",
    }
    assert all(item.mode is StpMode.PVST for item in stp)
    routing = control.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
    assert len(routing) == 3 and all(item.version == 2 for item in routing)
    assert not control.actions_of_type(ControlPlaneActionType.CONFIGURE_OSPFV2)
    assert not control.actions_of_type(ControlPlaneActionType.CONFIGURE_EIGRP_IPV4)
    reachability = {
        item.source_traffic_flow_id
        for item in control.verification_expectations
        if item.kind is ControlPlaneVerificationKind.END_TO_END_REACHABILITY
        and item.source_traffic_flow_id
    }
    assert reachability == {item.id for item in qualified.enterprise.traffic_flows}
    assert qualified.intent.routing_preference == DynamicRoutingProtocol.RIPV2.value

    voice = qualified.voice.plan
    capacity = {
        item.site_id: item.max_phones
        for item in voice.actions_of_type(VoiceActionType.ENABLE_CALL_CONTROL)
    }
    assert capacity == {
        "large-branch": 51,
        "multilayer-branch": 11,
        "small-branch": 7,
    }
    assert len(voice.actions_of_type(
        VoiceActionType.CONFIGURE_VOICE_DHCP_OPTION,
    )) == 3


def test_offline_qualification_is_stable_and_reports_every_stage():
    runs = [_qualify() for _ in range(10)]

    assert all(item.valid for item in runs)
    hashes = {
        (
            item.topology.physical_topology_hash,
            item.topology.layout_hash,
            item.topology.artifact_hash,
            item.configuration.semantic_hash,
            item.control_plane.semantic_hash,
            item.voice.semantic_hash,
        )
        for item in runs
    }
    assert len(hashes) == 1
    assert [item.stage for item in runs[0].stages] == [
        "design",
        "hardware",
        "topology",
        "structural_manifest",
        "traffic",
        "configuration",
        "control_plane",
        "voice",
    ]
    assert all(item.duration_ms >= 0 for item in runs[0].stages)
    assert all(item.item_count > 0 for item in runs[0].stages)


def test_offline_evidence_writer_confines_full_artifacts_to_run_directory(tmp_path):
    qualified = _qualify()

    output = write_cp_scale_offline_artifacts(qualified, tmp_path, "full scale")

    assert output == tmp_path / "full_scale"
    expected = {
        "intent.json", "enterprise.json", "hardware.json", "topology.json",
        "structural-manifest.json", "traffic.json", "configuration.json",
        "control-plane.json", "voice.json", "summary.json",
    }
    assert {item.name for item in output.iterdir()} == expected
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["valid"] is True
    assert summary["workload_endpoints"] == 279
    assert "plan" not in summary
