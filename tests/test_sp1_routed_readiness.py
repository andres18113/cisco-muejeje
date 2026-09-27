"""SP-1 A-5 (SP1-02): the routed forwarding rule over fresh router readings.

Each case breaks exactly one observed fact of the healthy three-router chain
and expects the refusing dimension and the device it names. The rule reads
only the rows; configuration or acceptance of a setter is never an input.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from sp1_routed_readings import (
    NAMES,
    dependent,
    healthy,
    observation,
    requirement,
    round_of,
    with_interface,
    with_routes,
)

from packet_tracer_mcp.domain.enterprise.models.routed_forwarding import (
    ObservedInterface,
    ObservedRoute,
)
from packet_tracer_mcp.domain.enterprise.services.routed_readiness import (
    ROUTED_DEADLINE,
    ROUTED_INTERFACE,
    ROUTED_NOT_OBSERVED,
    ROUTED_ROUTE,
    ROUTED_UNREADABLE,
    observed_routed_result,
    revoked_dependents,
    routed_facts,
    routed_verdict,
    routed_verdicts,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import parse_show_ip_route


def test_the_healthy_chain_is_admitted_in_both_directions():
    """Every hop carries the planned next hop and both ends deliver."""
    verdict = routed_verdict(dependent(), healthy())

    assert verdict.admitted and verdict.cause == ""


@pytest.mark.parametrize(
    ("connected", "extra", "static", "cause"),
    [
        (
            "C       10.12.0.0/30 is directly connected, GigabitEthernet0/0",
            "",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2, GigabitEthernet0/1",
            "route_output_interface",
        ),
        (
            "C       10.12.0.0/30 is directly connected, GigabitEthernet0/0",
            "C       10.12.0.2/32 is directly connected, GigabitEthernet0/1",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2",
            "next_hop_egress",
        ),
        (
            "C       10.12.0.0/30 is directly connected, GigabitEthernet0/0",
            "S       10.12.0.2/32 [1/0] via 10.3.0.10",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2",
            "next_hop_not_direct",
        ),
        (
            "",
            "",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2",
            "next_hop_unresolved",
        ),
        (
            "C       10.12.0.0/30 is directly connected, GigabitEthernet0/0",
            "C       10.12.0.0/30 is directly connected, GigabitEthernet0/1",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2",
            "next_hop_ambiguous",
        ),
        (
            "C       10.12.0.0/30 is directly connected, GigabitEthernet0/0",
            "L       10.12.0.2/32 is directly connected, GigabitEthernet0/0",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2",
            "next_hop_not_direct",
        ),
    ],
)
def test_parsed_route_must_prove_effective_forward_egress(
    connected, extra, static, cause
):
    """A literal next hop alone cannot authorize a different resolved egress."""
    text = "\n".join(
        (
            "Gateway of last resort is not set",
            "C       10.1.0.0/24 is directly connected, GigabitEthernet0/1",
            connected,
            extra,
            static,
        )
    )
    readings = dict(healthy())
    readings["r1"] = replace(readings["r1"], route_table=parse_show_ip_route(text))

    verdict = routed_verdict(dependent(), readings)

    assert not verdict.admitted
    assert cause in verdict.cause


def test_parsed_return_route_must_prove_direct_next_hop_egress():
    """The same lookup is required in the reverse direction."""
    output = "\n".join(
        (
            "Gateway of last resort is not set",
            "C       10.3.0.0/24 is directly connected, GigabitEthernet0/1",
            "C       10.23.0.0/30 is directly connected, GigabitEthernet0/0",
            "C       10.23.0.1/32 is directly connected, GigabitEthernet0/9",
            "S       10.1.0.0/24 [1/0] via 10.23.0.1",
        )
    )
    readings = dict(healthy())
    readings["r3"] = replace(readings["r3"], route_table=parse_show_ip_route(output))

    verdict = routed_verdict(dependent(), readings)

    assert not verdict.admitted
    assert verdict.cause == "return_next_hop_egress:R3:10.23.0.1:GigabitEthernet0/9"


def test_parsed_matching_printed_egress_admits_both_directions():
    """An explicit correct egress is supported alongside a via-only route."""
    forward = "\n".join(
        (
            "Gateway of last resort is not set",
            "C       10.1.0.0/24 is directly connected, GigabitEthernet0/1",
            "C       10.12.0.0/30 is directly connected, GigabitEthernet0/0",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2, GigabitEthernet0/0",
        )
    )
    reverse = "\n".join(
        (
            "Gateway of last resort is not set",
            "C       10.3.0.0/24 is directly connected, GigabitEthernet0/1",
            "C       10.23.0.0/30 is directly connected, GigabitEthernet0/0",
            "S       10.1.0.0/24 [1/0] via 10.23.0.1, GigabitEthernet0/0",
        )
    )
    readings = dict(healthy())
    readings["r1"] = replace(readings["r1"], route_table=parse_show_ip_route(forward))
    readings["r3"] = replace(readings["r3"], route_table=parse_show_ip_route(reverse))

    assert routed_verdict(dependent(), readings).admitted


def test_conflicting_equal_prefix_printed_interfaces_refuse():
    """All installed best rows must agree on the compiled output interface."""
    output = "\n".join(
        (
            "Gateway of last resort is not set",
            "C       10.1.0.0/24 is directly connected, GigabitEthernet0/1",
            "C       10.12.0.0/30 is directly connected, GigabitEthernet0/0",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2, GigabitEthernet0/0",
            "S       10.3.0.0/24 [1/0] via 10.12.0.2, GigabitEthernet0/9",
        )
    )
    readings = dict(healthy())
    readings["r1"] = replace(readings["r1"], route_table=parse_show_ip_route(output))

    verdict = routed_verdict(dependent(), readings)

    assert not verdict.admitted
    assert "route_output_interface:R1" in verdict.cause


@pytest.mark.parametrize(
    ("device", "rows", "cause"),
    [
        (
            "r2",
            (
                ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
                ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/1"),
                ObservedRoute("S", "10.1.0.0", 24, next_hop="10.12.0.1"),
            ),
            "route_missing:R2:10.3.0.10",
        ),
        (
            "r1",
            (
                ObservedRoute("C", "10.1.0.0", 24, interface="GigabitEthernet0/1"),
                ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
                ObservedRoute("S", "10.3.0.0", 24, next_hop="10.12.0.9"),
            ),
            "route_next_hop:R1:10.3.0.10:10.12.0.9",
        ),
        (
            "r1",
            (
                ObservedRoute("C", "10.1.0.0", 24, interface="GigabitEthernet0/1"),
                ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
                ObservedRoute("S", "10.3.0.0", 24, next_hop="10.12.0.2"),
                ObservedRoute("S", "10.3.0.0", 24, next_hop="10.12.0.6"),
            ),
            "route_next_hop:R1:10.3.0.10:10.12.0.2,10.12.0.6",
        ),
        (
            "r3",
            (
                ObservedRoute("C", "10.3.0.0", 24, interface="GigabitEthernet0/1"),
                ObservedRoute("S", "10.3.0.0", 25, next_hop="10.23.0.1"),
                ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/0"),
                ObservedRoute("S", "10.1.0.0", 24, next_hop="10.23.0.1"),
            ),
            "destination_not_connected:R3:10.3.0.10:S/10.23.0.1",
        ),
    ],
)
def test_a_forward_route_fault_refuses_naming_its_router(device, rows, cause):
    """Missing, wrong, extra-equal-cost and shadowing rows all refuse."""
    verdict = routed_verdict(dependent(), with_routes(healthy(), device, *rows))

    assert not verdict.admitted
    assert verdict.dimension == ROUTED_ROUTE
    assert verdict.cause == cause


def test_a_missing_return_route_refuses_the_return_direction():
    """The forward chain can be perfect while nothing comes back."""
    readings = with_routes(
        healthy(),
        "r2",
        ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
        ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/1"),
        ObservedRoute("S", "10.3.0.0", 24, next_hop="10.23.0.2"),
    )

    verdict = routed_verdict(dependent(), readings)

    assert verdict.dimension == ROUTED_ROUTE
    assert verdict.cause == "return_route_missing:R2:10.1.0.11"


def test_a_loop_shows_up_as_a_wrong_next_hop():
    """R2 sending server traffic back to R1 is refused at R2."""
    readings = with_routes(
        healthy(),
        "r2",
        ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
        ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/1"),
        ObservedRoute("S", "10.1.0.0", 24, next_hop="10.12.0.1"),
        ObservedRoute("S", "10.3.0.0", 24, next_hop="10.12.0.1"),
    )

    assert routed_verdict(dependent(), readings).cause == (
        "route_next_hop:R2:10.3.0.10:10.12.0.1"
    )


@pytest.mark.parametrize(
    ("row", "cause"),
    [
        (
            ObservedInterface("GigabitEthernet0/0", "10.23.0.2", "up", "down"),
            "interface_down:R3:GigabitEthernet0/0:up/down",
        ),
        (
            ObservedInterface("GigabitEthernet0/0", "10.23.0.99", "up", "up"),
            "interface_address:R3:GigabitEthernet0/0:10.23.0.99",
        ),
    ],
)
def test_a_transit_interface_fault_refuses(row, cause):
    """A route over a down or misaddressed link does not forward."""
    verdict = routed_verdict(dependent(), with_interface(healthy(), "r3", row))

    assert verdict.dimension == ROUTED_INTERFACE and verdict.cause == cause


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"observed_device_name": "R9"}, "not_authoritative"),
        ({"after_deadline": True}, "not_authoritative"),
        ({"output_complete": False}, "not_authoritative"),
        ({"call_budget_exhausted": True}, "not_authoritative"),
        (
            {"failure_reason": "pager_truncated", "fresh_output_observed": False},
            "pager_truncated",
        ),
    ],
)
def test_an_unreadable_router_neither_admits_nor_blames_a_route(override, reason):
    """Wrong device, late, paged or exhausted readings are not evidence."""
    readings = dict(healthy())
    readings["r2"] = replace(readings["r2"], **override)

    verdict = routed_verdict(dependent(), readings)

    assert verdict.dimension == ROUTED_UNREADABLE
    assert verdict.cause == f"unreadable:R2:{reason}"


def test_a_router_not_read_at_all_is_not_observed():
    """An absent reading is its own answer, distinct from a bad one."""
    readings = dict(healthy())
    del readings["r3"]

    verdict = routed_verdict(dependent(), readings)

    assert verdict.dimension == ROUTED_NOT_OBSERVED and verdict.cause == "not_read:r3"


def test_only_a_settled_episode_admits():
    """A window that ran out admits nothing, even if its last round forwarded."""
    group = requirement(2)
    good = round_of(0, healthy())

    settled = routed_verdicts(group, observation(good), NAMES)
    unsettled = routed_verdicts(group, observation(good, end="deadline"), NAMES)

    assert {item.admitted for item in settled.values()} == {True}
    assert {item.dimension for item in unsettled.values()} == {ROUTED_DEADLINE}


def test_the_record_keeps_exactly_the_rows_the_decision_used():
    """Facts name each router's asked interfaces and longest-match rows."""
    group = requirement(1)
    facts = routed_facts(group, observation(round_of(0, healthy())), NAMES)
    result = observed_routed_result(
        group,
        verdicts=routed_verdicts(group, observation(round_of(0, healthy())), NAMES),
        sample=facts,
    )

    assert result.status == "admitted"
    r2 = facts["devices"]["r2"]
    assert set(r2["interfaces"]) == {"GigabitEthernet0/0", "GigabitEthernet0/1"}
    assert r2["routes"]["10.3.0.10"] == [
        {"code": "S", "prefix": "10.3.0.0/24", "next_hop": "10.23.0.2", "interface": ""}
    ]
    assert result.as_row()["kind"] == "routed_forwarding"


def test_revocation_uses_the_newest_readings_and_only_pending_dependents():
    """A refuted route withdraws pending permits; decided ones are kept."""
    group = requirement(2)
    admitted = observed_routed_result(
        group,
        verdicts=routed_verdicts(group, observation(round_of(0, healthy())), NAMES),
        sample={},
    )
    drifted = with_routes(
        healthy(),
        "r2",
        ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
        ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/1"),
        ObservedRoute("S", "10.1.0.0", 24, next_hop="10.12.0.1"),
    )

    revoked = revoked_dependents(admitted, drifted, {"r2"}, {"verify-2"})

    assert revoked == {"verify-2": "route_missing:R2:10.3.0.10"}
    # A re-read of an unrelated router changes nothing.
    assert revoked_dependents(admitted, drifted, {"r9"}, {"verify-2"}) == {}
