"""Canonical CP-SCALE E5 plan preserves the documented VLAN/ROAS policy."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from tests.test_cp_scale_canonical_physical import _compile


def _configuration():
    enterprise, _, topology = _compile()
    assert topology.plan is not None
    result = compile_enterprise_configuration(enterprise, topology.plan)
    assert result.is_valid, [item.model_dump(mode="json") for item in result.issues]
    assert result.plan is not None
    return topology.plan, result.plan


def test_only_vlans_10_20_30_are_created_and_allowed_on_every_trunk():
    _, plan = _configuration()
    vlans = plan.actions_of_type(ConfigurationActionType.CREATE_VLAN)
    trunks = plan.actions_of_type(ConfigurationActionType.CONFIGURE_TRUNK)

    assert len(vlans) == 45
    assert {item.vlan_id for item in vlans} == {10, 20, 30}
    assert len(trunks) == 27
    assert all(item.allowed_vlans == [10, 20, 30] for item in trunks)
    assert all(1 not in item.allowed_vlans for item in trunks)


def test_every_phone_port_uses_data_vlan_10_and_voice_vlan_20():
    topology, plan = _configuration()
    devices = {item.id: item for item in topology.devices}
    access = plan.actions_of_type(ConfigurationActionType.CONFIGURE_ACCESS_PORT)
    phone_actions = [
        item
        for item in access
        if any(
            devices[endpoint_id].enterprise_role == DeviceRole.IP_PHONE.value
            for endpoint_id in item.endpoint_ids
        )
    ]

    assert len(phone_actions) == 69
    assert all(item.data_vlan_id == 10 for item in phone_actions)
    assert all(item.voice_vlan_id == 20 for item in phone_actions)


def test_router_on_a_stick_and_serial_addresses_are_exact():
    _, plan = _configuration()
    subinterfaces = plan.actions_of_type(
        ConfigurationActionType.CONFIGURE_SUBINTERFACE,
    )
    routed = plan.actions_of_type(
        ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE,
    )

    assert {
        (item.device_name, item.parent_interface, item.vlan_id, item.ipv4)
        for item in subinterfaces
    } == {
        (router, "FastEthernet0/0", vlan, f"172.{site}.{vlan}.1")
        for router, site in (("Router4", 16), ("Router3", 17), ("Router0", 18))
        for vlan in (10, 20, 30)
    }
    assert {
        (item.device_name, item.interface, item.ipv4)
        for item in routed
    } == {
        ("Router4", "Serial1/0", "10.0.0.1"),
        ("Router0", "Serial1/0", "10.0.0.2"),
        ("Router4", "Serial1/1", "10.0.0.5"),
        ("Router3", "Serial1/1", "10.0.0.6"),
        ("Router3", "Serial1/0", "10.0.0.9"),
        ("Router0", "Serial1/1", "10.0.0.10"),
    }


def test_every_network_hostname_is_the_exact_semantic_name():
    topology, plan = _configuration()
    expected = {item.name for item in topology.devices if item.network_layer}
    hostnames = plan.actions_of_type(ConfigurationActionType.CONFIGURE_HOSTNAME)

    assert {item.hostname for item in hostnames} == expected
    assert {item.device_name for item in hostnames} == expected
