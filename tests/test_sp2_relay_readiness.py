"""A routed DHCP client has no application permission before lease binding."""

from __future__ import annotations

from dataclasses import replace
from time import monotonic

import pytest
from sp1_routed_fixture import compose
from sp1_routed_readings import NAMES, round_of
from sp1_routed_readings import dependent as static_dependent
from sp1_routed_readings import healthy as healthy_routed_readings
from test_sp2_relay_composition import _remote_dhcp_payload

from packet_tracer_mcp.application.use_cases.apply_services import (
    bind_routed_lease_result,
)
from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    ServiceAccessReadinessGate,
)
from packet_tracer_mcp.application.use_cases.service_path_admission import (
    dhcp_prelease_paths,
    path_admission,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.routed_forwarding import (
    ObservedRoute,
    RouteTableReading,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    ServiceVerificationResult,
)
from packet_tracer_mcp.domain.enterprise.services.routed_readiness import (
    network_route_coverage_cause,
    routed_round_facts,
    routed_verdict,
    unobserved_routed_result,
)
from packet_tracer_mcp.domain.enterprise.services.service_access_readiness import (
    DHCP_ACQUISITION_KINDS,
    derive_access_readiness_plan,
)


def test_unbound_remote_client_is_refused_without_a_router_read():
    """An empty DHCP address cannot turn into ungated routed permission."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload)
    unsupported, routed = path_admission(
        plans.configuration,
        plans.services,
        plans.services.services,
        links=plans.composition.topology.links,
    )
    assert unsupported == []
    readiness = derive_access_readiness_plan(
        configuration_actions=plans.configuration.actions,
        verification_expectations=plans.services.verification_expectations,
        request_kinds=DHCP_ACQUISITION_KINDS,
        routed_paths={
            (path.client_device_id, path.host_device_id): path
            for path in routed.values()
        },
    )
    gate = ServiceAccessReadinessGate(readiness, None, clock=monotonic)
    assert all(group.key[0] == "dhcp_relay_forwarding" for group in gate._plan.routed)
    client_id = ids["BR1-DEFAULT-PC-01"]
    lease = next(
        item
        for item in plans.services.verification_expectations
        if item.kind.value == "dhcp_lease" and item.client_device_id == client_id
    )
    refused = gate.decide(lease.id)
    assert refused is not None
    assert refused.admitted is False
    assert refused.cause == "dhcp_lease_not_bound"
    assert gate.observations == []

    unrelated = gate._routed[("dhcp_relay_forwarding", "hq-data", "hq-servers")]
    gate.bind_verified_lease(client_id, "10.40.0.18", "255.255.255.248")
    assert gate._routed[unrelated.key] is unrelated
    bound = next(
        dependent
        for group in (gate._bound_routed(item) for item in gate._routed.values())
        for dependent in group.dependents
        if dependent.client_device_id == client_id
    )
    assert bound.client_ipv4 == "10.40.0.18"

    with pytest.raises(ValueError, match="identity changed"):
        gate.bind_verified_lease(client_id, "10.40.0.19", "255.255.255.248")


def test_prelease_readiness_uses_an_explicit_network_route_target():
    """The network target is scoped to DHCP readiness, not a client address."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload)
    _unsupported, routed = path_admission(
        plans.configuration,
        plans.services,
        plans.services.services,
        links=plans.composition.topology.links,
    )
    provisional = dhcp_prelease_paths(routed, plans.services.services)
    branch = provisional[(ids["BR1-DEFAULT-PC-01"], ids["HQ-DEFAULT-DNS-01"])]
    assert branch.client_network == "10.40.0.16/29"
    assert branch.client_ipv4 == "10.40.0.16"
    assert (
        routed[("service/br1/branch-dhcp", ids["BR1-DEFAULT-PC-01"])].client_ipv4 == ""
    )


@pytest.mark.parametrize(
    ("address", "mask"),
    [
        ("10.40.0.18", "255.255.255.0"),
        ("10.40.0.24", "255.255.255.248"),
        ("10.40.0.16", "255.255.255.248"),
    ],
)
def test_lease_binding_refuses_wrong_mask_outside_or_network_address(address, mask):
    """The route target can only be an assigned host in the selected subnet."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload)
    _unsupported, routed = path_admission(
        plans.configuration,
        plans.services,
        plans.services.services,
        links=plans.composition.topology.links,
    )
    readiness = derive_access_readiness_plan(
        configuration_actions=plans.configuration.actions,
        verification_expectations=plans.services.verification_expectations,
        request_kinds=DHCP_ACQUISITION_KINDS,
        routed_paths={
            (path.client_device_id, path.host_device_id): path
            for path in routed.values()
        },
    )
    gate = ServiceAccessReadinessGate(readiness, None, clock=monotonic)
    with pytest.raises(ValueError, match="outside its selected routed network"):
        gate.bind_verified_lease(ids["BR1-DEFAULT-PC-01"], address, mask)


def test_failed_peer_lease_is_omitted_from_a_bound_clients_route_round():
    """One local lease failure cannot contaminate another client's router read."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload)
    _unsupported, routed = path_admission(
        plans.configuration,
        plans.services,
        plans.services.services,
        links=plans.composition.topology.links,
    )
    readiness = derive_access_readiness_plan(
        configuration_actions=plans.configuration.actions,
        verification_expectations=plans.services.verification_expectations,
        request_kinds=DHCP_ACQUISITION_KINDS,
        routed_paths={
            (path.client_device_id, path.host_device_id): path
            for path in routed.values()
        },
    )
    gate = ServiceAccessReadinessGate(readiness, None, clock=monotonic)
    good = ids["BR1-DEFAULT-PC-01"]
    gate.bind_verified_lease(good, "10.40.0.18", "255.255.255.248")
    seen = []

    def observe_active(requirement):
        seen.append(requirement)
        return unobserved_routed_result(requirement, cause="sample"), None

    gate._observe_routed = observe_active
    group = next(
        item for item in gate._plan.routed if item.client_segment_id == "br1-data"
    )
    gate._routed_group(group)
    assert len(seen) == 1
    assert {item.client_device_id for item in seen[0].dependents} == {good}


def test_only_a_stable_attributed_physical_pool_row_binds_routed_readiness():
    """A successful status alone cannot supply a routed DHCP client address."""
    payload, ids = _remote_dhcp_payload()
    plans = compose(payload)
    _unsupported, routed = path_admission(
        plans.configuration,
        plans.services,
        plans.services.services,
        links=plans.composition.topology.links,
    )
    readiness = derive_access_readiness_plan(
        configuration_actions=plans.configuration.actions,
        verification_expectations=plans.services.verification_expectations,
        request_kinds=DHCP_ACQUISITION_KINDS,
        routed_paths={
            (path.client_device_id, path.host_device_id): path
            for path in routed.values()
        },
    )
    client_id = ids["BR1-DEFAULT-PC-01"]
    lease = next(
        item
        for item in plans.services.verification_expectations
        if item.kind.value == "dhcp_lease" and item.client_device_id == client_id
    )
    lease.expected["state_only"] = True

    def result(pool, *, address="10.40.0.18", fresh=True):
        return ServiceVerificationResult(
            expectation_id=lease.id,
            service_id=lease.service_id,
            status=ActionExecutionStatus.VERIFIED,
            evidence_kind=lease.evidence_kind,
            fresh_evidence=fresh,
            observation=ObservationFact.OBSERVED,
            claim_level="attributed_to_effective_server_pool",
            observed={
                "client_ipv4": address,
                "client_netmask": "255.255.255.248",
                "client_mac": "0001.0203.0401",
                "effective_pool_name": pool,
                "stable_samples": 2,
            },
        )

    wrong = ServiceAccessReadinessGate(readiness, None, clock=monotonic)
    refused = bind_routed_lease_result(wrong, lease, result("serverPool"))
    assert refused.status is not ActionExecutionStatus.VERIFIED
    assert wrong._unbound

    stale = ServiceAccessReadinessGate(readiness, None, clock=monotonic)
    stale_row = bind_routed_lease_result(
        stale, lease, result("serverPool", fresh=False)
    )
    assert stale_row.status is ActionExecutionStatus.UNKNOWN
    assert stale._unbound

    outside = ServiceAccessReadinessGate(readiness, None, clock=monotonic)
    outside_row = bind_routed_lease_result(
        outside,
        lease,
        result(str(lease.expected["effective_pool_name"]), address="10.40.0.20"),
    )
    assert outside_row.status is not ActionExecutionStatus.VERIFIED
    assert outside._unbound

    exact = ServiceAccessReadinessGate(readiness, None, clock=monotonic)
    accepted = bind_routed_lease_result(
        exact, lease, result(str(lease.expected["effective_pool_name"]))
    )
    assert accepted.status is ActionExecutionStatus.VERIFIED
    assert not any(
        item.client_device_id == client_id for item in exact._unbound.values()
    )


def test_prelease_route_table_covers_every_address_or_refuses_a_shadow():
    """One network-address lookup cannot hide a wrong more specific route."""
    covering = ObservedRoute(
        code="S",
        network="10.40.0.0",
        prefix_length=16,
        next_hop="10.50.0.2",
        interface="GigabitEthernet0/0",
    )
    target = "10.40.8.0/24"
    assert (
        network_route_coverage_cause(
            RouteTableReading(rows=(covering,), header_seen=True),
            target,
            next_hop="10.50.0.2",
            interface="GigabitEthernet0/0",
        )
        == ""
    )
    shadow = ObservedRoute(
        code="S",
        network="10.40.8.100",
        prefix_length=32,
        next_hop="10.50.0.9",
        interface="GigabitEthernet0/1",
    )
    assert "shadow" in network_route_coverage_cause(
        RouteTableReading(rows=(covering, shadow), header_seen=True),
        target,
        next_hop="10.50.0.2",
        interface="GigabitEthernet0/0",
    )


def test_prelease_routed_verdict_uses_full_prefix_while_sp1_uses_exact_ip():
    """An observed wrong host route blocks DHCP before client mode is changed."""
    prelease = replace(
        static_dependent(),
        kind=ServiceVerificationKind.DHCP_LEASE,
        client_ipv4="10.1.0.0",
        client_network="10.1.0.0/24",
    )
    readings = healthy_routed_readings()
    assert routed_verdict(prelease, readings).admitted
    shadow = ObservedRoute(
        code="S",
        network="10.1.0.100",
        prefix_length=32,
        next_hop="10.23.0.9",
        interface="GigabitEthernet0/9",
    )
    readings["r3"] = replace(
        readings["r3"],
        route_table=replace(
            readings["r3"].route_table,
            rows=(*readings["r3"].route_table.rows, shadow),
        ),
    )
    verdict = routed_verdict(prelease, readings)
    assert not verdict.admitted
    assert "network_route_shadow" in verdict.cause
    assert routed_verdict(static_dependent(), healthy_routed_readings()).admitted


def test_prelease_evidence_retains_overlapping_route_rows_once_per_router():
    """The archived group facts let a reviewer recompute the shadow refusal."""
    prelease = replace(
        static_dependent(),
        kind=ServiceVerificationKind.DHCP_LEASE,
        client_ipv4="10.1.0.0",
        client_network="10.1.0.0/24",
    )
    readings = healthy_routed_readings()
    shadow = ObservedRoute(
        code="S",
        network="10.1.0.100",
        prefix_length=32,
        next_hop="10.23.0.9",
        interface="GigabitEthernet0/9",
    )
    readings["r3"] = replace(
        readings["r3"],
        route_table=replace(
            readings["r3"].route_table,
            rows=(*readings["r3"].route_table.rows, shadow),
        ),
    )
    facts = routed_round_facts((prelease,), round_of(1, readings), NAMES)
    overlaps = facts["r3"]["network_routes"]["10.1.0.0/24"]
    assert {item["prefix"] for item in overlaps} == {
        "10.1.0.0/24",
        "10.1.0.100/32",
    }


def test_connected_gateway_local_route_does_not_shadow_dhcp_client_prefix():
    """IOS's L /32 for the router's own gateway is not a host forwarding path."""
    connected = ObservedRoute(
        code="C",
        network="10.72.32.0",
        prefix_length=29,
        interface="GigabitEthernet0/1",
    )
    gateway_local = ObservedRoute(
        code="L",
        network="10.72.32.1",
        prefix_length=32,
        interface="GigabitEthernet0/1",
    )
    table = RouteTableReading(rows=(connected, gateway_local), header_seen=True)
    assert (
        network_route_coverage_cause(
            table,
            "10.72.32.0/29",
            interface="GigabitEthernet0/1",
            connected=True,
            local_address="10.72.32.1",
        )
        == ""
    )


def test_another_local_host_route_still_shadows_a_dhcp_client_prefix():
    """Only the selected gateway's own L row may be ignored."""
    connected = ObservedRoute(
        code="C",
        network="10.72.32.0",
        prefix_length=29,
        interface="GigabitEthernet0/1",
    )
    gateway_local = ObservedRoute(
        code="L",
        network="10.72.32.1",
        prefix_length=32,
        interface="GigabitEthernet0/1",
    )
    competing_local = ObservedRoute(
        code="L",
        network="10.72.32.4",
        prefix_length=32,
        interface="GigabitEthernet0/1",
    )
    table = RouteTableReading(
        rows=(connected, gateway_local, competing_local), header_seen=True
    )
    assert (
        network_route_coverage_cause(
            table,
            "10.72.32.0/29",
            interface="GigabitEthernet0/1",
            connected=True,
            local_address="10.72.32.1",
        )
        == "network_route_shadow"
    )
