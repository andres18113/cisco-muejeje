"""SP-1 A-5 (SP1-02): routed groups inside the readiness gate, as sequences.

The observer is scripted (it replaces only the router reads) and follows the
runtime's episode contract: rounds in order, each taking simulated time, the
episode ending when `settled` accepts a complete round or the script runs
out. The gate, the rule and the memo are production code.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest
from sp1_routed_readings import (
    NAMES,
    dependent,
    healthy,
    requirement,
    round_of,
    with_routes,
)

from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    ServiceAccessReadinessGate,
)
from packet_tracer_mcp.domain.enterprise.models.routed_forwarding import (
    ObservedRoute,
    RoutedForwardingObservation,
)
from packet_tracer_mcp.domain.enterprise.services.routed_readiness import (
    RoutedRequirement,
)
from packet_tracer_mcp.domain.enterprise.services.service_access_readiness import (
    AccessReadinessPlan,
)


@dataclass
class _Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass
class _Observer:
    """Answer each episode from the next script, one round per `step` seconds."""

    clock: _Clock
    scripts: list[list[dict]]
    step: float = 1.0
    calls: list[tuple[str, ...]] = field(default_factory=list)
    names: tuple[str, ...] | None = None

    def observe_routed_forwarding(self, devices, *, settled, **bounds):
        self.calls.append(tuple(devices))
        script = self.scripts.pop(0)
        rounds = []
        end = "deadline"
        deadline = self.clock.now + bounds["deadline_seconds"]
        for index, readings in enumerate(script):
            self.clock.now += self.step
            # As the runtime does: a reading taken past the window says so.
            late = self.clock.now >= deadline
            round_ = round_of(
                index,
                {
                    key: replace(value, after_deadline=late)
                    for key, value in readings.items()
                },
            )
            rounds.append(round_)
            if settled(round_):
                end = "required_paths_forwarding"
                break
        return RoutedForwardingObservation(
            device_names=self.names or tuple(devices),
            rounds=tuple(rounds),
            deadline_seconds=bounds["deadline_seconds"],
            episode_end_reason=end,
        )


def _gate(groups: list[RoutedRequirement], observer) -> ServiceAccessReadinessGate:
    plan = AccessReadinessPlan(
        routed=tuple(groups),
        groups_by_expectation={
            item.expectation_id: (group.key,)
            for group in groups
            for item in group.dependents
        },
    )
    return ServiceAccessReadinessGate(
        plan,
        None,
        clock=observer.clock if observer is not None else _Clock(),
        device_names=NAMES,
        routed_observer=observer,
    )


def _missing_server_route():
    return with_routes(
        healthy(),
        "r2",
        ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
        ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/1"),
        ObservedRoute("S", "10.1.0.0", 24, next_hop="10.12.0.1"),
    )


def test_a_route_that_installs_within_the_window_is_admitted():
    """Missing, missing, then present: one episode, every dependent admitted."""
    clock = _Clock()
    observer = _Observer(
        clock, [[_missing_server_route(), _missing_server_route(), healthy()]]
    )
    gate = _gate([requirement(3)], observer)

    verdicts = [gate.decide(f"verify-{index}") for index in (1, 2, 3)]

    assert [item.admitted for item in verdicts] == [True, True, True]
    assert len(observer.calls) == 1


def test_an_exhausted_reading_then_a_valid_one_is_admitted_on_the_valid_round():
    """A reading cut by its call budget is not evidence either way."""
    clock = _Clock()
    exhausted = dict(healthy())
    exhausted["r2"] = replace(exhausted["r2"], call_budget_exhausted=True)
    observer = _Observer(clock, [[exhausted, healthy()]])

    assert _gate([requirement(1)], observer).decide("verify-1").admitted


def test_a_window_that_ends_unsettled_refuses_with_the_last_cause():
    """Nothing forwards by the end: the named hop, never a pass."""
    clock = _Clock()
    observer = _Observer(
        clock, [[_missing_server_route()] * 3, [_missing_server_route()]]
    )

    verdict = _gate([requirement(1)], observer).decide("verify-1")

    assert not verdict.admitted
    assert verdict.cause == "route_missing:R2:10.3.0.10"


def test_a_route_that_appears_only_after_the_window_is_late():
    """Late rows are kept in the report and authorize nothing.

    The three-router window is 3 x 30 s; the healthy round lands at 93 s.
    """
    clock = _Clock()
    observer = _Observer(
        clock,
        [[_missing_server_route(), _missing_server_route(), healthy()]],
        step=31.0,
    )

    verdict = _gate([requirement(1)], observer).decide("verify-1")

    assert not verdict.admitted and "deadline" in verdict.cause


def test_one_failing_client_is_narrowed_away_from_the_others():
    """A host route breaks one client's return path; the other is admitted."""
    clock = _Clock()
    broken = with_routes(
        healthy(),
        "r2",
        ObservedRoute("C", "10.12.0.0", 30, interface="GigabitEthernet0/0"),
        ObservedRoute("C", "10.23.0.0", 30, interface="GigabitEthernet0/1"),
        ObservedRoute("S", "10.1.0.0", 24, next_hop="10.12.0.1"),
        ObservedRoute("S", "10.1.0.12", 32, next_hop="10.23.0.2"),
        ObservedRoute("S", "10.3.0.0", 24, next_hop="10.23.0.2"),
    )
    observer = _Observer(clock, [[broken, broken], [broken]])
    gate = _gate([requirement(2)], observer)

    first, second = gate.decide("verify-1"), gate.decide("verify-2")

    assert first.admitted
    assert not second.admitted
    assert second.cause == "return_route_next_hop:R2:10.1.0.12:10.23.0.2"
    assert len(observer.calls) == 2


def _two_groups():
    one = requirement(2, segment="client-a")
    two = RoutedRequirement(
        client_segment_id="client-b",
        host_segment_id="servers",
        device_ids=("r1", "r2", "r3"),
        dependents=(replace(dependent(7), expectation_id="verify-b"),),
    )
    three = RoutedRequirement(
        client_segment_id="client-c",
        host_segment_id="servers",
        device_ids=("r1", "r2", "r3"),
        dependents=(replace(dependent(8), expectation_id="verify-c"),),
    )
    return one, two, three


def test_route_drift_after_an_admission_withdraws_the_pending_permits():
    """A later reading of a shared router refutes; it is never regained."""
    clock = _Clock()
    one, two, three = _two_groups()
    observer = _Observer(clock, [[healthy()], [_missing_server_route()], [healthy()]])
    gate = _gate([one, two, three], observer)

    assert gate.decide("verify-1").admitted  # group one admitted, verify-2 pending
    assert not gate.decide("verify-b").admitted  # group two sees the drift
    assert gate.decide("verify-c").admitted  # group three sees it healthy again
    revoked = gate.decide("verify-2")

    assert not revoked.admitted
    assert "ROUTE_DRIFT_AFTER_ADMISSION:route_missing:R2:10.3.0.10" in revoked.cause
    assert gate.decide("verify-1").admitted  # a decided permit is not rewritten
    assert any(row.get("kind") == "routed_revocations" for row in gate.rows())


def test_bad_then_good_rounds_in_one_later_episode_still_revoke_pending():
    """The first complete contradiction remains after that episode recovers."""
    clock = _Clock()
    one, two, _ = _two_groups()
    observer = _Observer(clock, [[healthy()], [_missing_server_route(), healthy()]])
    gate = _gate([one, two], observer)

    assert gate.decide("verify-1").admitted
    assert gate.decide("verify-b").admitted
    pending = gate.decide("verify-2")

    assert not pending.admitted
    assert "ROUTE_DRIFT_AFTER_ADMISSION:route_missing:R2:10.3.0.10" in pending.cause
    assert gate.decide("verify-1").admitted
    [row] = [row for row in gate.rows() if row.get("kind") == "routed_revocations"]
    assert row["revoked"][0]["expectation_id"] == "verify-2"
    assert row["revoked"][0]["source_group"] == list(two.key)
    assert row["revoked"][0]["episode"]["ordinal"] == 1
    assert row["revoked"][0]["round"] == 0
    assert row["evidence"][0]["devices"]["r2"]["routes"]["10.3.0.10"] == []


def test_permanent_bad_round_revokes_only_pending_dependents():
    """A lasting contradiction does not rewrite already used permission."""
    clock = _Clock()
    one, two, _ = _two_groups()
    observer = _Observer(clock, [[healthy()], [_missing_server_route()]])
    gate = _gate([one, two], observer)

    assert gate.decide("verify-1").admitted
    assert not gate.decide("verify-b").admitted
    assert not gate.decide("verify-2").admitted
    assert gate.decide("verify-1").admitted


def test_an_unknown_round_followed_by_healthy_does_not_revoke():
    """An unreadable route sample cannot claim that a route disappeared."""
    clock = _Clock()
    one, two, _ = _two_groups()
    unknown = dict(_missing_server_route())
    unknown["r2"] = replace(unknown["r2"], output_complete=False)
    observer = _Observer(clock, [[healthy()], [unknown, healthy()]])
    gate = _gate([one, two], observer)

    assert gate.decide("verify-1").admitted
    assert gate.decide("verify-b").admitted
    assert gate.decide("verify-2").admitted
    assert not any(row.get("kind") == "routed_revocations" for row in gate.rows())


def test_unrelated_route_drift_does_not_revoke_the_admitted_chain():
    """A changed prefix off this path leaves its dependent permits intact."""
    clock = _Clock()
    one, two, _ = _two_groups()
    unrelated = with_routes(
        healthy(),
        "r2",
        *healthy()["r2"].route_table.rows,
        ObservedRoute("S", "192.0.2.0", 24, next_hop="10.12.0.1"),
    )
    observer = _Observer(clock, [[healthy()], [unrelated]])
    gate = _gate([one, two], observer)

    assert gate.decide("verify-1").admitted
    assert gate.decide("verify-b").admitted
    assert gate.decide("verify-2").admitted


def test_return_only_drift_revokes_with_return_cause():
    """The reverse chain is just as capable of revoking a pending request."""
    clock = _Clock()
    one, two, _ = _two_groups()
    no_return = with_routes(
        healthy(),
        "r2",
        *(row for row in healthy()["r2"].route_table.rows if row.network != "10.1.0.0"),
    )
    observer = _Observer(clock, [[healthy()], [no_return]])
    gate = _gate([one, two], observer)

    assert gate.decide("verify-1").admitted
    assert not gate.decide("verify-b").admitted
    verdict = gate.decide("verify-2")
    assert not verdict.admitted
    assert "return_route_missing:R2:10.1.0.12" in verdict.cause


@pytest.mark.parametrize("malformation", ["incomplete", "duplicate", "foreign"])
def test_malformed_bad_round_cannot_revoke(malformation):
    """Incomplete, duplicated and foreign rounds cannot refute a permit."""
    clock = _Clock()
    one, two, _ = _two_groups()
    observer = _Observer(clock, [[healthy()], [_missing_server_route(), healthy()]])
    original = observer.observe_routed_forwarding

    def malformed(devices, *, settled, **bounds):
        observation = original(devices, settled=settled, **bounds)
        if len(observer.calls) == 2:
            first, second = observation.rounds
            if malformation == "incomplete":
                first = replace(first, complete=False)
            elif malformation == "duplicate":
                first = replace(first, readings=(first.readings[0],) * 3)
            else:
                first = replace(
                    first,
                    readings=(
                        *first.readings[:2],
                        replace(first.readings[2], device_name="R9"),
                    ),
                )
            return replace(observation, rounds=(first, second))
        return observation

    observer.observe_routed_forwarding = malformed
    gate = _gate([one, two], observer)

    assert gate.decide("verify-1").admitted
    assert gate.decide("verify-b").admitted
    assert gate.decide("verify-2").admitted


def test_many_pending_clients_reference_one_shared_bad_round():
    """A group-sized revocation keeps one round projection, not one per client."""
    clock = _Clock()
    one = requirement(200, segment="client-a")
    _, two, _ = _two_groups()
    observer = _Observer(clock, [[healthy()], [_missing_server_route(), healthy()]])
    gate = _gate([one, two], observer)

    assert gate.decide("verify-1").admitted
    assert gate.decide("verify-b").admitted
    [row] = [item for item in gate.rows() if item.get("kind") == "routed_revocations"]

    assert len(row["revoked"]) == 199
    assert len(row["evidence"]) == 1
    assert {item["evidence_ref"] for item in row["revoked"]} == {0}


def test_a_local_read_failure_revokes_nothing_but_a_later_contradiction_does():
    """Unreadable is not refuted; the shared contradiction after it is."""
    clock = _Clock()
    one, two, three = _two_groups()
    unreadable = dict(healthy())
    unreadable["r2"] = replace(unreadable["r2"], observed_device_name="")
    observer = _Observer(clock, [[healthy()], [unreadable], [_missing_server_route()]])
    gate = _gate([one, two, three], observer)

    assert gate.decide("verify-1").admitted
    assert not gate.decide("verify-b").admitted  # its own read failed
    assert not gate.decide("verify-c").admitted  # the contradiction
    assert not gate.decide("verify-2").admitted


def test_an_answer_about_other_routers_is_not_a_sample():
    """A self-consistent episode about the wrong devices refuses nothing."""
    clock = _Clock()
    observer = _Observer(clock, [[healthy()]], names=("R1", "R2", "R4"))

    verdict = _gate([requirement(1)], observer).decide("verify-1")

    assert not verdict.admitted
    assert "observation_does_not_answer_the_request:routed" in verdict.cause


def test_without_a_routed_observer_every_dependent_is_refused():
    """The composition must provide the reader; silence is not permission."""
    verdict = _gate([requirement(1)], None).decide("verify-1")

    assert not verdict.admitted and "observer_unavailable" in verdict.cause


def test_one_episode_serves_every_client_of_the_group():
    """Observation cost follows the routers, not the client count."""
    clock = _Clock()
    observer = _Observer(clock, [[healthy()]])
    gate = _gate([requirement(50)], observer)

    assert all(gate.decide(f"verify-{index}").admitted for index in range(1, 51))
    assert observer.calls == [("R1", "R2", "R3")]


def test_a_three_router_group_gets_a_window_per_router():
    """LIVE at 6e5e527: one round over three routers took 32.4 s.

    A fixed 30 s window refused the group while every table was correct. The
    window scales with the routers read, so two such rounds fit.
    """
    clock = _Clock()
    observer = _Observer(clock, [[_missing_server_route(), healthy()]], step=32.4)

    verdict = _gate([requirement(1)], observer).decide("verify-1")

    assert verdict.admitted, verdict
    assert len(observer.calls) == 1
