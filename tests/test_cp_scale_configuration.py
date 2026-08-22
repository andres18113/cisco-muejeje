"""CP-SCALE existing-scope configuration, PVST, RIPv2, and voice."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from tests.test_cp_scale_layout import _compile
from tests.test_stage3a4_product_composition import _oriented_manifest


def test_wireless_iot_vlan_is_carried_structurally_without_claiming_association():
    enterprise, _, compiled = _compile()
    topology = compiled.plan
    configuration = compile_enterprise_configuration(
        enterprise,
        topology,
        deployment_manifest=_oriented_manifest(topology),
        packet_tracer_version="9.0.1.0858",
    )

    assert configuration.is_valid and configuration.plan is not None
    created = {
        (item.site_id, item.vlan_id)
        for item in configuration.plan.actions
        if item.action_type is ConfigurationActionType.CREATE_VLAN
    }
    assert {
        vlan for site, vlan in created if site == "large-branch"
    } == {10, 20, 30, 40, 99}
    assert {
        vlan for site, vlan in created if site == "multilayer-branch"
    } == {10, 20, 30, 99}
    assert {
        vlan for site, vlan in created if site == "small-branch"
    } == {10, 20, 30, 99}
    trunks = configuration.plan.actions_of_type(ConfigurationActionType.CONFIGURE_TRUNK)
    assert trunks and all(30 in item.allowed_vlans for item in trunks)
    assert all(
        item.metadata.get("requirement.wireless_association") == "unqualified"
        for item in topology.devices
        if item.enterprise_role in {
            "webcam", "smoke_detector", "motion_detector",
            "humiture_monitor", "temperature_monitor",
        }
    )


def test_router_on_a_stick_and_distribution_peer_links_are_fully_governed():
    enterprise, _, compiled = _compile()
    topology = compiled.plan
    configuration = compile_enterprise_configuration(
        enterprise,
        topology,
        deployment_manifest=_oriented_manifest(topology),
        packet_tracer_version="9.0.1.0858",
    )

    assert configuration.is_valid and configuration.plan is not None
    edge_links = [link for link in topology.links if link.link_role == "edge_link"]
    distribution_peers = [
        link for link in topology.links
        if link.link_role == "redundant_link"
        and all(
            next(item for item in topology.devices if item.id == device_id).network_layer
            == "distribution"
            for device_id in (link.device_a_id, link.device_b_id)
        )
    ]
    assert len(edge_links) == len(enterprise.sites)

    trunks = configuration.plan.actions_of_type(
        ConfigurationActionType.CONFIGURE_TRUNK,
    )
    governed = {
        (action.device_id, action.interface): action
        for action in trunks
    }
    governed_links = [
        link for link in topology.links
        if link.link_role in {
            "access_uplink", "distribution_uplink", "core_link",
            "redundant_link", "edge_link",
        }
    ]
    assert distribution_peers or any(
        item.network_layer == "core" for item in topology.devices
    )
    for link in governed_links:
        for device_id, interface in (
            (link.device_a_id, link.port_a),
            (link.device_b_id, link.port_b),
        ):
            device = next(item for item in topology.devices if item.id == device_id)
            if device.category == "switch":
                assert (device_id, interface) in governed
                assert 1 not in governed[(device_id, interface)].allowed_vlans

    subinterfaces = configuration.plan.actions_of_type(
        ConfigurationActionType.CONFIGURE_SUBINTERFACE,
    )
    assert subinterfaces
    assert all(
        action.parent_interface.startswith("GigabitEthernet")
        for action in subinterfaces
    )

    hostnames = {
        (action.device_id, action.hostname)
        for action in configuration.plan.actions
        if action.action_type.value == "configure_hostname"
    }
    network_devices = {
        (item.id, item.name)
        for item in topology.devices
        if item.category in {"router", "switch"}
    }
    assert hostnames == network_devices
