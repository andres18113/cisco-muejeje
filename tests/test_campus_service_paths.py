"""Multi-access wired paths through the public tool, over a SIMULATED campus.

The campus is the one the real planner and compiler produce for the intent;
only what lies beyond the bridge is simulated (see `campus_product_simulation`),
so every result below is offline behaviour of the product, not Packet Tracer
behaviour. The public MCP tool, its shared session composition, the product
use case, both runtimes and the readiness gate are the production ones.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from campus_product_simulation import (
    campus_payload,
    compose_campus,
    run_public_campus,
)

from packet_tracer_mcp.domain.enterprise.services.service_path_closure import (
    ROUTED_PATH_CONTRACT,
    PathKind,
    PathTopology,
    classify_path,
)

SERVER = "HQ-DEFAULT-SERVER-01"
SW1 = "HQ-DEFAULT-ACCESS-SW-01"
SW2 = "HQ-DEFAULT-ACCESS-SW-02"


@pytest.fixture(scope="module")
def campus30():
    """Thirty static clients on two access switches, compiled once."""
    return compose_campus(campus_payload(30))


def _checks(public) -> dict[str, dict]:
    """Return each client's HTTP check row by deployed client name."""
    rows = {}
    for client in public["clients"]:
        for result in client["results"].values():
            for check in result["checks"]:
                rows[client["deployed_name"]] = check
    return rows


def _switch_of(plans, client_name: str) -> str:
    topology = PathTopology(plans.configuration_plan.actions)
    ids = {value: key for key, value in plans.deployed_names.items()}
    placement = topology.placements[ids[client_name]][0]
    return plans.deployed_names[placement.switch_device_id]


def _positions(terminal, prefix: str) -> list[int]:
    return [
        index for index, event in enumerate(terminal.events) if event.startswith(prefix)
    ]


def test_the_planner_puts_the_thirty_clients_on_two_access_switches(campus30):
    """The fixture is what the planner compiled, not a hand-drawn topology."""
    switches = {_switch_of(campus30, name) for name in _checks_names(campus30)}

    assert switches == {SW1, SW2}
    topology = PathTopology(campus30.configuration_plan.actions)
    ids = {value: key for key, value in campus30.deployed_names.items()}
    kinds = {
        classify_path(
            topology, client_device_id=ids[name], host_device_id=ids[SERVER]
        ).kind
        for name in _checks_names(campus30)
    }
    assert kinds == {PathKind.LOCAL_ACCESS, PathKind.L2_MULTI_ACCESS}


def _checks_names(plans) -> list[str]:
    return sorted(
        name
        for identifier, name in plans.deployed_names.items()
        if "/user_pc/" in identifier
    )


def test_a_multi_access_campus_is_verified_through_the_public_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, campus30
):
    """Same VLAN across switches: admitted once the trunks are proven."""
    public, terminal = run_public_campus(tmp_path, monkeypatch, campus30)

    assert public["status"] == "verified", public["blocked_reason"]
    checks = _checks(public)
    assert len(checks) == 30
    assert {row["status"] for row in checks.values()} == {"verified"}
    rows = public["operational_readiness"]
    access = [row for row in rows if "kind" not in row]
    continuity = [row for row in rows if row.get("kind") == "trunk_continuity"]
    assert {row["switch_device_name"] for row in access} == {SW1, SW2}
    assert len(continuity) == 1 and continuity[0]["status"] == "admitted"
    assert continuity[0]["sample"]["episode_end_reason"] == "required_pairs_joined"
    remote = [row for row in continuity[0]["dependents"] if row["admitted"]]
    assert len(remote) == sum(1 for name in checks if _switch_of(campus30, name) != SW2)
    assert not terminal.unhandled


def test_every_request_follows_every_group_its_path_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, campus30
):
    """A remote client's first request follows its switch, the server's and the trunks."""
    public, terminal = run_public_campus(tmp_path, monkeypatch, campus30)
    assert public["status"] == "verified"

    for name in _checks_names(campus30):
        start = _positions(terminal, f"http_start:{name}")[0]
        own = _switch_of(campus30, name)
        assert max(_positions(terminal, f"ios_read:{own}:show spanning-tree")) < start
        assert max(_positions(terminal, f"ios_read:{SW2}:show spanning-tree")) < start
        if own != SW2:
            trunk_reads = _positions(terminal, "ios_read:") and [
                index
                for index, event in enumerate(terminal.events)
                if event.endswith(":show interfaces trunk")
            ]
            assert trunk_reads and max(trunk_reads) < start


def test_a_routed_server_segment_is_refused_before_any_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """B7: the planner routes it; no registered action or reader can prove it."""
    plans = compose_campus(campus_payload(30, server_segment_role="servers"))

    public, terminal = run_public_campus(tmp_path, monkeypatch, plans)

    assert public["status"] == "refused"
    assert public["refusal_code"] == "service_path_unsupported"
    assert ROUTED_PATH_CONTRACT in public["blocked_reason"]
    kinds = {kind for _, kind in terminal.log}
    assert not kinds & {"send", "e6_apply", "http_start", "readiness"}


def test_the_routed_closure_names_the_gateways_it_would_need():
    """The completed safe component: the derived routed dependency is concrete."""
    plans = compose_campus(campus_payload(30, server_segment_role="servers"))
    topology = PathTopology(plans.configuration_plan.actions)
    requirements = {
        item.device_id: item.segment_id
        for item in plans.service_plan.foundational_requirements
    }
    ids = {value: key for key, value in plans.deployed_names.items()}

    path = classify_path(
        topology,
        client_device_id=ids["HQ-DEFAULT-PC-01"],
        host_device_id=ids[SERVER],
        segments=requirements,
    )

    assert path.kind is PathKind.ROUTED
    assert path.reason == ROUTED_PATH_CONTRACT
    assert {item.action_type for item in path.gateways} == {"configure_svi"}
    assert len({item.segment_id for item in path.gateways}) == 2


# -- faults are dependency-local ------------------------------------------------------


def _uplinks(terminal, switch: str) -> set[str]:
    return {end.link_id for end in terminal.network.switches[switch].trunks.values()}


def test_an_unreadable_switch_off_the_forwarding_path_blocks_nobody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, campus30
):
    """A switch with no selected client and no forwarding edge on any path."""

    def unreadable(terminal):
        network = terminal.network
        states = network.stp_states(10)
        forwarding = {
            (name, end.peer)
            for name, switch in network.switches.items()
            for port, end in switch.trunks.items()
            if states.get((name, port)) == "FWD"
            and states.get((end.peer, end.peer_interface)) == "FWD"
        }

        def joined_without(excluded: str) -> bool:
            seen, pending = {SW1}, [SW1]
            while pending:
                current = pending.pop()
                for left, right in forwarding:
                    if left == current and excluded not in (left, right):
                        if right not in seen:
                            seen.add(right)
                            pending.append(right)
            return SW2 in seen

        candidates = [
            name
            for name, switch in sorted(network.switches.items())
            if not switch.access and joined_without(name)
        ]
        assert candidates, "the simulated campus has no redundant switch"
        terminal.unreadable.add(candidates[0])

    public, _ = run_public_campus(tmp_path, monkeypatch, campus30, configure=unreadable)

    assert public["status"] == "verified", public["blocked_reason"]
    assert len(_checks(public)) == 30


def test_a_fault_in_an_unselected_branch_is_never_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A second site with no service: its switches are never asked, never matter."""
    payload = campus_payload(20, sites=2)
    payload["sites"][1]["services"] = []
    plans = compose_campus(payload)
    branch = sorted(name for name in plans.deployed_names.values() if "BR01" in name)

    def break_branch(terminal):
        for name in branch:
            if name in terminal.network.switches:
                terminal.unreadable.add(name)
                terminal.network.down_links |= _uplinks(terminal, name)
                terminal.access_forwarding_after[name] = math.inf

    public, terminal = run_public_campus(
        tmp_path, monkeypatch, plans, configure=break_branch
    )

    assert public["status"] == "verified", public["blocked_reason"]
    selected = _checks(public)
    assert selected and all(not name.startswith("BR01") for name in selected)
    assert not any(event.startswith("ios_read:BR01") for event in terminal.events)
