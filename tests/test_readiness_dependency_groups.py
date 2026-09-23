"""Readiness per dependency: groups, continuity, reuse, invalidation, narrowing.

The plans are the ones the real planner compiles for a two-access-switch
campus. The observers are stand-ins whose answers the tests set, so each rule
of the gate is shown on its own: which groups a request names, that a failed
group blocks only its dependents, that an answer is reused only while its
identity and revision hold, and that a narrowed episode admits exactly the
dependents it covers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import pytest
from campus_product_simulation import campus_payload, compose_campus
from service_entry_fixture import ForwardingBackend

from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    READINESS_MAX_GROUPS,
    READINESS_TOTAL_BUDGET_SECONDS,
    ServiceAccessReadinessGate,
    readiness_limits,
)
from packet_tracer_mcp.domain.enterprise.models.forwarding import AccessForwardingRow
from packet_tracer_mcp.domain.enterprise.services.service_access_readiness import (
    derive_access_readiness_plan,
)
from packet_tracer_mcp.domain.enterprise.services.service_path_closure import (
    L2Component,
    TrunkLink,
)
from packet_tracer_mcp.domain.enterprise.services.trunk_continuity import (
    CAUSE_WINDOW_ENDED_UNSETTLED,
    CONTINUITY_DEADLINE,
    CONTINUITY_NO_PATH,
    TrunkContinuityObservation,
    TrunkContinuityRound,
    TrunkPortReading,
    TrunkSwitchReading,
    joined_pairs,
    round_joins,
    trunk_continuity_verdicts,
)


@pytest.fixture(scope="module")
def campus():
    """Thirty clients on two access switches, as the real planner compiles them."""
    return compose_campus(campus_payload(30))


def _plan(campus):
    return derive_access_readiness_plan(
        configuration_actions=campus.configuration_plan.actions,
        verification_expectations=campus.service_plan.verification_expectations,
    )


@dataclass
class PortBackend(ForwardingBackend):
    """The shared timed backend, with `(switch, port)` pairs that never forward."""

    never: set[tuple[str, str]] = field(default_factory=set)

    def observe_access_forwarding(self, device_name, vlan_id, interfaces, **bounds):
        """Answer as the timed backend does, then hold the named ports in LIS."""
        observed = super().observe_access_forwarding(
            device_name, vlan_id, interfaces, **bounds
        )
        return replace(
            observed,
            rows=tuple(
                AccessForwardingRow(
                    interface=row.interface,
                    matches=row.matches,
                    state=(
                        "LIS"
                        if (device_name, row.interface) in self.never
                        else row.state
                    ),
                    role=row.role,
                )
                for row in observed.rows
            ),
        )


@dataclass
class ContinuityBackend:
    """A continuity observer that joins every pair unless told otherwise."""

    joins: bool = True
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def observe_trunk_continuity(self, switches, vlan_id, **bounds: Any):
        """Answer one episode: one round, settled or not."""
        self.calls.append(tuple(name for name, _ in switches))
        readings = tuple(
            TrunkSwitchReading(
                switch_name=name,
                executed=True,
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name=name,
                device_identity_provenance="confirmed_unique",
                ports=tuple(
                    TrunkPortReading(
                        interface=port,
                        matches=1,
                        status="trunking",
                        allowed_vlans=(vlan_id,),
                        active_vlans=(vlan_id,),
                        forwarding_vlans=(vlan_id,) if self.joins else (),
                    )
                    for port in ports
                ),
            )
            for name, ports in switches
        )
        round_ = TrunkContinuityRound(0, 0, readings, True)
        settled = bounds["settled"](round_)
        return TrunkContinuityObservation(
            vlan_id=vlan_id,
            switch_names=tuple(name for name, _ in switches),
            rounds=(round_,),
            deadline_seconds=30.0,
            episode_end_reason="required_pairs_joined" if settled else "deadline",
            deadline_reached=not settled,
        )


def _gate(campus, backend=None, continuity=None):
    backend = backend if backend is not None else PortBackend()
    return (
        ServiceAccessReadinessGate(
            _plan(campus),
            backend,
            clock=backend.clock,
            device_names=campus.deployed_names,
            continuity_observer=continuity or ContinuityBackend(),
        ),
        backend,
    )


def test_a_remote_request_names_both_access_groups_and_the_component(campus):
    """Three groups for a request across switches, one for a local request."""
    plan = _plan(campus)

    shapes = {len(keys) for keys in plan.groups_by_expectation.values()}
    assert shapes == {1, 3}
    remote = next(
        keys for keys in plan.groups_by_expectation.values() if len(keys) == 3
    )
    assert remote[2][0] == "trunk_continuity"
    assert remote[2] == plan.continuity[0].key
    assert len(plan.requirements) == 2 and len(plan.continuity) == 1


def test_one_grouped_observation_serves_every_dependent_of_each_group(campus):
    """Thirty requests cost two access episodes and one continuity episode."""
    gate, backend = _gate(campus)
    continuity = gate._continuity_observer
    plan = _plan(campus)

    verdicts = [gate.decide(item) for item in plan.groups_by_expectation]

    assert all(item is not None and item.admitted for item in verdicts)
    assert len(backend.calls) == 2
    assert len(continuity.calls) == 1


def test_a_failed_component_blocks_only_the_requests_that_cross_it(campus):
    """Local requests stay admitted when the trunks never forward."""
    gate, _ = _gate(campus, continuity=ContinuityBackend(joins=False))
    plan = _plan(campus)

    verdicts = {item: gate.decide(item) for item in plan.groups_by_expectation}

    for expectation, keys in plan.groups_by_expectation.items():
        verdict = verdicts[expectation]
        if len(keys) == 1:
            assert verdict.admitted, verdict.cause
        else:
            assert not verdict.admitted
            assert verdict.cause.startswith("trunk_continuity:10:")


def test_a_relevant_change_invalidates_the_reused_answer(campus):
    """A new revision observes again; the superseded answer stays reported."""
    gate, backend = _gate(campus)
    plan = _plan(campus)
    first, second = list(plan.groups_by_expectation)[:2]
    requirement = plan.requirements[0]

    assert gate.decide(first).admitted
    calls = len(backend.calls)
    gate.invalidate_devices({requirement.switch_device_id})
    gate.decide(first)
    gate.decide(second)

    assert gate.revision(requirement.key) == 1
    assert len(backend.calls) > calls
    rows = [
        row
        for row in gate.rows()
        if row.get("switch_device_id") == requirement.switch_device_id
    ]
    assert len(rows) >= 2


def test_an_unrelated_change_keeps_the_answer(campus):
    """Only a device the group depends on advances its revision."""
    gate, backend = _gate(campus)
    plan = _plan(campus)
    first = next(iter(plan.groups_by_expectation))
    gate.decide(first)
    calls = len(backend.calls)

    gate.invalidate_devices({"device-that-no-group-names"})
    gate.decide(first)

    assert len(backend.calls) == calls
    assert all(gate.revision(item.key) == 0 for item in plan.requirements)


def test_a_narrowed_episode_admits_only_the_dependents_it_fully_covers(campus):
    """One client port never forwards: that client is refused, its neighbours not."""
    plan = _plan(campus)
    requirement = max(plan.requirements, key=lambda item: len(item.dependents))
    victim, client_port = next(
        (dependent, port)
        for dependent in requirement.dependents
        for port in dependent.interfaces
        if all(
            port not in other.interfaces
            for other in requirement.dependents
            if other is not dependent
        )
    )
    switch = campus.deployed_names[requirement.switch_device_id]
    gate, backend = _gate(campus, backend=PortBackend(never={(switch, client_port)}))

    verdicts = {
        item.expectation_id: gate.decide(item.expectation_id)
        for item in requirement.dependents
    }

    assert verdicts[victim.expectation_id].admitted is False
    assert all(
        verdict.admitted
        for expectation, verdict in verdicts.items()
        if expectation != victim.expectation_id
        and len(plan.groups_by_expectation[expectation]) == 1
    )
    on_switch = [call for call in backend.calls if call[0] == switch]
    assert len(on_switch) == 2  # the refused episode, then the narrowed one
    narrowed = on_switch[1]
    assert client_port not in narrowed[2]
    rows = [row for row in gate.rows() if row.get("narrowed_from_group")]
    assert rows and client_port not in rows[0]["requested_interfaces"]


def test_the_legacy_ceilings_hold_for_a_plan_that_fits_them(campus):
    """A single-group plan keeps 4 groups and 120 s; a larger one derives its own."""
    single = derive_access_readiness_plan(
        configuration_actions=campus.configuration_plan.actions,
        verification_expectations=[
            item
            for item in campus.service_plan.verification_expectations
            if item.kind.value != "http_fetch"
        ],
    )
    assert readiness_limits(single) == (
        READINESS_MAX_GROUPS,
        READINESS_TOTAL_BUDGET_SECONDS,
    )
    big = compose_campus(campus_payload(200))
    plan = _plan(big)
    episodes, seconds = readiness_limits(plan)
    groups = len(plan.requirements) + len(plan.continuity)
    assert groups > READINESS_MAX_GROUPS
    # One own episode and at most one narrowed episode per group.
    assert episodes == 2 * groups
    assert seconds == 30.0 * episodes


# -- the continuity rule --------------------------------------------------------------


def _component() -> L2Component:
    """A-B, B-C and a redundant A-C link, all compiled for VLAN 10."""
    return L2Component(
        vlan_id=10,
        switch_device_ids=("a", "b", "c"),
        switch_device_names=("A", "B", "C"),
        links=(
            TrunkLink("ab", "a", "A", "Gi0/1", "b", "B", "Gi0/1", (10,)),
            TrunkLink("bc", "b", "B", "Gi0/2", "c", "C", "Gi0/1", (10,)),
            TrunkLink("ac", "a", "A", "Gi0/2", "c", "C", "Gi0/2", (10,)),
        ),
    )


NAMES = {"a": "A", "b": "B", "c": "C"}


def _reading(name: str, forwarding: dict[str, bool], **overrides) -> TrunkSwitchReading:
    values = {
        "switch_name": name,
        "executed": True,
        "fresh_output_observed": True,
        "output_complete": True,
        "observed_device_name": name,
        "device_identity_provenance": "confirmed_unique",
        "ports": tuple(
            TrunkPortReading(
                interface=port,
                matches=1,
                status="trunking",
                allowed_vlans=(10,),
                active_vlans=(10,),
                forwarding_vlans=(10,) if state else (),
            )
            for port, state in forwarding.items()
        ),
    }
    values.update(overrides)
    return TrunkSwitchReading(**values)


def _round(**readings) -> TrunkContinuityRound:
    return TrunkContinuityRound(0, 0, tuple(readings.values()), True)


def test_a_blocked_redundant_trunk_is_not_a_missing_path():
    """A-C blocked at C: A and C are still joined through B."""
    round_ = _round(
        a=_reading("A", {"Gi0/1": True, "Gi0/2": True}),
        b=_reading("B", {"Gi0/1": True, "Gi0/2": True}),
        c=_reading("C", {"Gi0/1": True, "Gi0/2": False}),
    )
    observation = TrunkContinuityObservation(
        vlan_id=10,
        switch_names=("A", "B", "C"),
        rounds=(round_,),
        episode_end_reason="required_pairs_joined",
    )

    assert round_joins(_component(), NAMES, round_, [("a", "c")])
    verdicts = trunk_continuity_verdicts(_component(), NAMES, observation, [("a", "c")])
    assert verdicts[0].admitted is True


@pytest.mark.parametrize(
    "fault",
    [
        {"executed": False},
        {"fresh_output_observed": False},
        {"output_complete": False},
        {"observed_device_name": "SOMEONE"},
        {"device_identity_provenance": "ambiguous"},
        {"after_deadline": True},
        {"call_budget_exhausted": True},
    ],
)
def test_an_unauthoritative_transit_reading_makes_its_edges_unusable(fault):
    """B unreadable in any dimension: nothing joins A and C through it."""
    round_ = _round(
        a=_reading("A", {"Gi0/1": True, "Gi0/2": False}),
        b=_reading("B", {"Gi0/1": True, "Gi0/2": True}, **fault),
        c=_reading("C", {"Gi0/1": True, "Gi0/2": False}),
    )

    assert not round_joins(_component(), NAMES, round_, [("a", "c")])


def test_an_unsettled_episode_grants_nothing_but_names_the_joined_pairs():
    """The window is the permission; the joined pairs are only a narrowing hint."""
    round_ = _round(
        a=_reading("A", {"Gi0/1": True, "Gi0/2": False}),
        b=_reading("B", {"Gi0/1": True, "Gi0/2": False}),
        c=_reading("C", {"Gi0/1": False, "Gi0/2": False}),
    )
    observation = TrunkContinuityObservation(
        vlan_id=10,
        switch_names=("A", "B", "C"),
        rounds=(round_,),
        episode_end_reason="deadline",
        deadline_reached=True,
    )
    pairs = [("a", "b"), ("a", "c")]

    verdicts = trunk_continuity_verdicts(_component(), NAMES, observation, pairs)

    assert [item.admitted for item in verdicts] == [False, False]
    assert verdicts[0].dimension == CONTINUITY_DEADLINE
    assert verdicts[0].cause == CAUSE_WINDOW_ENDED_UNSETTLED
    assert verdicts[1].dimension == CONTINUITY_NO_PATH
    assert joined_pairs(_component(), NAMES, observation, pairs) == (("a", "b"),)


def test_a_narrowed_group_never_starves_a_later_group():
    """Each group may take a narrowed second episode inside the derived ceilings."""
    big = compose_campus(campus_payload(200))
    plan = _plan(big)
    first = plan.requirements[0]
    victim, port = next(
        (dependent, interface)
        for dependent in first.dependents
        for interface in dependent.interfaces
        if all(
            interface not in other.interfaces
            for other in first.dependents
            if other is not dependent
        )
    )
    backend = PortBackend(never={(big.deployed_names[first.switch_device_id], port)})
    gate = ServiceAccessReadinessGate(
        plan,
        backend,
        clock=backend.clock,
        device_names=big.deployed_names,
        continuity_observer=ContinuityBackend(),
    )

    verdicts = {item: gate.decide(item) for item in plan.groups_by_expectation}

    refused = {key for key, verdict in verdicts.items() if not verdict.admitted}
    assert refused == {victim.expectation_id}
    assert not any("budget_exhausted" in verdict.cause for verdict in verdicts.values())
