"""SP-2 relay requirements through the real intent, E4 and E5 compilers."""

from __future__ import annotations

import copy
from ipaddress import ip_address, ip_network

import pytest
from sp1_routed_fixture import compose, topology_payload

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    _path_admission,
    _plan_for,
)
from packet_tracer_mcp.infrastructure.generator.configuration_renderer import (
    PacketTracerIosRenderer,
)


def _remote_dhcp_payload():
    base = topology_payload(sites=2, users=2)
    first = compose(base, services=False)
    ids = first.ids()
    payload = copy.deepcopy(base)
    payload["sites"][0]["endpoints"][0]["addressing_preference"] = "dhcp"
    payload["sites"][1]["endpoints"][0]["addressing_preference"] = "dhcp"
    payload["sites"][0]["services"] = [
        {
            "name": "hq-dhcp",
            "service_type": "dhcp",
            "host_device_id": ids["HQ-DEFAULT-DNS-01"],
            "segment_id": "hq-data",
            "client_device_ids": [ids["HQ-DEFAULT-PC-01"], ids["HQ-DEFAULT-PC-02"]],
            "dhcp_pool": {"dns_server": first.endpoint("HQ-DEFAULT-DNS-01").ipv4},
        }
    ]
    payload["sites"][1]["services"] = [
        {
            "name": "branch-dhcp",
            "service_type": "dhcp",
            "host_device_id": ids["HQ-DEFAULT-DNS-01"],
            "segment_id": "br1-data",
            "client_device_ids": [ids["BR1-DEFAULT-PC-01"], ids["BR1-DEFAULT-PC-02"]],
            "dhcp_pool": {"dns_server": first.endpoint("HQ-DEFAULT-DNS-01").ipv4},
        }
    ]
    return payload, ids


def test_remote_dhcp_authority_compiles_exact_client_gateway_helpers():
    """Each remote client segment gets one helper to the static server host."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload, services=False)
    assert plans.composition.service_policy_issues == []
    assert plans.composition.configuration_policy.delegated_dhcp_segment_ids == [
        "br1-data",
        "hq-data",
    ]
    server = plans.endpoint("HQ-DEFAULT-DNS-01")
    relays = [
        item
        for item in plans.configuration.actions
        if item.action_type.value == "configure_dhcp_relay"
    ]
    assert len(relays) == 2
    assert {item.segment_id for item in relays} == {"hq-data", "br1-data"}
    assert all(item.server_address == server.ipv4 for item in relays)
    assert all(item.device_id != ids["HQ-DEFAULT-DNS-01"] for item in relays)
    assert not any(
        item.action_type.value == "configure_dhcp_pool"
        and item.segment_id in {"hq-data", "br1-data"}
        for item in plans.configuration.actions
    )


def test_relay_renders_only_validated_client_interface_and_server_ip():
    """The IOS effect is exactly the selected interface's helper command."""
    payload, _ids = _remote_dhcp_payload()
    plans = compose(payload, services=False)
    relay = next(
        item
        for item in plans.configuration.actions
        if item.action_type.value == "configure_dhcp_relay"
        and item.segment_id == "br1-data"
    )
    rendered = PacketTracerIosRenderer().render_device_batches(
        relay.device_name, "2911", [relay]
    )
    assert len(rendered) == 1
    assert rendered[0].ios_payload.splitlines() == [
        "enable",
        "configure terminal",
        f"interface {relay.interface}",
        f" ip helper-address {relay.server_address}",
        " exit",
        "end",
        "write memory",
    ]


def test_remote_segments_compile_distinct_server_policies_without_ios_substitution():
    """The selected Server-PT owns both remote client segments in E6."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload)
    assert plans.services is not None
    pools = [
        item
        for item in plans.services.actions
        if item.action_type.value == "configure_server_dhcp_pool"
    ]
    assert {item.segment_id for item in pools} == {"hq-data", "br1-data"}
    assert len({item.pool_name for item in pools}) == 2
    assert all(item.host_device_id == ids["HQ-DEFAULT-DNS-01"] for item in pools)
    assert {
        service.segment_id
        for service in plans.services.services
        if service.service_type.value == "dhcp"
    } == {"hq-data", "br1-data"}
    server_address = ip_address(plans.endpoint("HQ-DEFAULT-DNS-01").ipv4)
    assert all(
        server_address not in ip_network(f"{item.network}/{item.prefix}")
        for item in pools
    )


def test_shared_server_configures_every_pool_before_enabling_dhcp():
    """One process cannot start between policies for two client segments."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload)
    assert plans.services is not None
    actions = plans.services.actions
    pools = [
        item
        for item in actions
        if item.action_type.value == "configure_server_dhcp_pool"
        and item.host_device_id == ids["HQ-DEFAULT-DNS-01"]
    ]
    enables = [
        item
        for item in actions
        if item.action_type.value == "enable_server_dhcp"
        and item.host_device_id == ids["HQ-DEFAULT-DNS-01"]
    ]
    assert len(pools) == len(enables) == 2
    pool_ids = {item.id for item in pools}
    enable_ids = {item.id for item in enables}
    by_id = {item.id: item for item in actions}

    def prerequisites(action_id):
        found = set()
        pending = list(by_id[action_id].depends_on)
        while pending:
            identifier = pending.pop()
            if identifier in found:
                continue
            found.add(identifier)
            pending.extend(by_id[identifier].depends_on)
        return found

    assert all(not enable_ids.intersection(item.depends_on) for item in pools)
    assert all(pool_ids.issubset(prerequisites(item.id)) for item in enables)
    assert sum(len(item.depends_on) for item in enables) < len(pools) * len(enables)
    assert all(item.apply_dependencies == item.depends_on for item in enables)
    assert max(actions.index(item) for item in pools) < min(
        actions.index(item) for item in enables
    )


@pytest.mark.parametrize("admitted_segment", ["hq-data", "br1-data"])
def test_optional_pool_exclusion_keeps_the_admitted_dhcp_process_order(
    admitted_segment,
):
    """A9 can drop one optional segment without stranding the other."""
    payload, _ids = _remote_dhcp_payload()
    optional_site = 1 if admitted_segment == "hq-data" else 0
    payload["sites"][optional_site]["services"][0]["required"] = False
    plans = compose(payload)
    assert plans.services is not None
    admitted = [
        item for item in plans.services.services if item.segment_id == admitted_segment
    ]

    selected = _plan_for(plans.services, admitted, {})

    assert {item.service_id for item in selected.actions} == {admitted[0].id}
    action_ids = {item.id for item in selected.actions}
    assert all(set(item.depends_on) <= action_ids for item in selected.actions)
    assert all(set(item.apply_dependencies) <= action_ids for item in selected.actions)


def test_same_host_dhcp_service_dependency_refuses_before_effects():
    """A completed-service dependency conflicts with pool-before-enable."""
    payload, _ids = _remote_dhcp_payload()
    payload["sites"][1]["services"][0]["depends_on"] = ["hq-dhcp"]

    plans = compose(payload)

    assert plans.services is None
    assert any(
        "same-host DHCP service dependency" in issue
        for issue in plans.composition.issues
    )


def test_remote_dhcp_paths_close_over_relay_and_both_route_directions():
    """A selected remote PC gets a plan route proof without a static IP."""
    payload, _ids = _remote_dhcp_payload()
    plans = compose(payload)
    unsupported, routed = _path_admission(
        plans.configuration,
        plans.services,
        plans.services.services,
        links=plans.composition.topology.links,
    )
    assert unsupported == []
    assert len(routed) == 4
    relays = {
        item.id
        for item in plans.configuration.actions
        if item.action_type.value == "configure_dhcp_relay"
    }
    assert all(path.admitted for path in routed.values())
    assert all(path.client_ipv4 == "" for path in routed.values())
    assert all(path.action_ids & relays for path in routed.values())


def test_a_more_specific_wrong_return_route_refuses_the_whole_client_prefix():
    """One route to the network address cannot stand for all future leases."""
    payload, _ids = _remote_dhcp_payload()
    plans = compose(payload)
    configuration = plans.configuration.model_copy(deep=True)
    original = next(
        item
        for item in configuration.actions
        if item.action_type.value == "configure_static_route"
        and item.destination_segment_id == "br1-data"
    )
    configuration.actions.append(
        original.model_copy(
            update={
                "id": "cfg/route/shadow-sp2",
                "network": "10.40.0.18",
                "prefix": 32,
                "netmask": "255.255.255.255",
                "next_hop": "10.40.0.99",
            }
        )
    )
    unsupported, _routed = _path_admission(
        configuration,
        plans.services,
        plans.services.services,
        links=plans.composition.topology.links,
    )
    assert any("route_shadows_client_network" in item for item in unsupported)


def test_a_covering_aggregate_return_route_admits_the_entire_client_prefix():
    """A route covering all future leases need not equal the data prefix."""
    payload, _ids = _remote_dhcp_payload()
    plans = compose(payload)
    configuration = plans.configuration.model_copy(deep=True)
    original = next(
        item
        for item in configuration.actions
        if item.action_type.value == "configure_static_route"
        and item.destination_segment_id == "br1-data"
    )
    configuration.actions = [
        item for item in configuration.actions if item.id != original.id
    ] + [
        original.model_copy(
            update={
                "network": "10.40.0.0",
                "prefix": 16,
                "netmask": "255.255.0.0",
            }
        )
    ]
    unsupported, routed = _path_admission(
        configuration,
        plans.services,
        plans.services.services,
        links=plans.composition.topology.links,
    )
    assert unsupported == []
    assert all(path.admitted for path in routed.values())


def test_native_lease_gates_each_clients_gateway_and_resolver_readbacks():
    """The intended DHCP gateway and resolver are independently observable."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload)
    expectations = plans.services.verification_expectations
    for client_id in (
        ids["HQ-DEFAULT-PC-01"],
        ids["HQ-DEFAULT-PC-02"],
        ids["BR1-DEFAULT-PC-01"],
        ids["BR1-DEFAULT-PC-02"],
    ):
        lease = next(
            item
            for item in expectations
            if item.kind.value == "dhcp_lease" and item.client_device_id == client_id
        )
        readings = [
            item
            for item in expectations
            if item.client_device_id == client_id
            and item.kind.value in {"client_gateway", "client_dns_server"}
            and item.service_id == lease.service_id
        ]
        assert {item.kind.value for item in readings} == {
            "client_gateway",
            "client_dns_server",
        }
        assert all(lease.id in item.depends_on for item in readings)
        assert all(item.required for item in readings)
        assert (
            next(
                item.expected["gateway"]
                for item in readings
                if item.kind.value == "client_gateway"
            )
            == lease.expected["gateway"]
        )
        assert (
            next(
                item.expected["server_address"]
                for item in readings
                if item.kind.value == "client_dns_server"
            )
            == lease.expected["dns_server"]
        )


def test_cold_http_waits_for_lease_gateway_and_resolver_of_its_own_client():
    """No routed application request uses only the lease row as permission."""
    payload, ids = _remote_dhcp_payload()
    first = compose(payload, services=False)
    payload["sites"][0]["services"].append(
        {
            "name": "sp2-web",
            "service_type": "http",
            "host_device_id": ids["HQ-DEFAULT-WEB-01"],
            "address": first.endpoint("HQ-DEFAULT-WEB-01").ipv4,
            "http_content": "SP2_COLD_MARKER",
            "client_device_ids": [
                ids["BR1-DEFAULT-PC-01"],
                ids["BR1-DEFAULT-PC-02"],
            ],
        }
    )
    plans = compose(payload)
    rows = plans.services.verification_expectations
    for client_id in (ids["BR1-DEFAULT-PC-01"], ids["BR1-DEFAULT-PC-02"]):
        dhcp_prerequisites = {
            item.id
            for item in rows
            if item.client_device_id == client_id
            and item.kind.value in {"dhcp_lease", "client_gateway", "client_dns_server"}
            and item.service_id.startswith("service/br1/branch-dhcp")
        }
        assert len(dhcp_prerequisites) == 3
        fetch = next(
            item
            for item in rows
            if item.kind.value == "http_fetch" and item.client_device_id == client_id
        )
        assert dhcp_prerequisites <= set(fetch.depends_on)
