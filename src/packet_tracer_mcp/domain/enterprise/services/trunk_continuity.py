"""Trunk and VLAN continuity between two access switches, from observed trunks.

A request between endpoints on two access switches crosses trunk links. The
registered `show interfaces trunk` reader states, per trunk port, whether it is
trunking and which VLANs are allowed, active, and forwarding and not pruned.
This module keeps what one bounded observation of a component returned and
decides, per dependent, whether a forwarding trunk path joined its two access
switches in one timely round.

An edge is usable only when both of its ends were read in the same round by an
authoritative reading (executed, fresh, complete, attributed to exactly that
switch), before the window closed, and each end shows exactly one trunking row
that carries the VLAN as allowed, active and forwarding. A switch that could
not be read makes its edges unusable; nothing is assumed about it. Spanning
tree blocking a redundant trunk is therefore not a failure: a path either
exists through forwarding edges or it does not.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass

from .access_forwarding import CONFIRMED_UNIQUE
from .service_path_closure import L2Component

#: Dimensions of a continuity verdict, most specific first.
CONTINUITY_NOT_OBSERVED = "NOT_OBSERVED"
CONTINUITY_DEADLINE = "DEADLINE"
CONTINUITY_NO_PATH = "NO_FORWARDING_TRUNK_PATH"
CONTINUITY_NONE = "NONE"

CAUSE_NO_ROUND = "no_continuity_round_taken"
CAUSE_WINDOW_ENDED_UNSETTLED = "continuity_window_ended_before_every_pair_joined"


@dataclass(frozen=True)
class TrunkPortReading:
    """One requested trunk port as one reading described it."""

    interface: str
    matches: int
    status: str = ""
    allowed_vlans: tuple[int, ...] | None = None
    active_vlans: tuple[int, ...] | None = None
    forwarding_vlans: tuple[int, ...] | None = None

    def carries(self, vlan_id: int) -> bool:
        """Whether this port trunks the VLAN in all three columns."""
        return bool(
            self.matches == 1
            and self.status.casefold() == "trunking"
            and self.allowed_vlans is not None
            and self.active_vlans is not None
            and self.forwarding_vlans is not None
            and vlan_id in self.allowed_vlans
            and vlan_id in self.active_vlans
            and vlan_id in self.forwarding_vlans
        )


@dataclass(frozen=True)
class TrunkSwitchReading:
    """One bounded `show interfaces trunk` reading of one switch."""

    switch_name: str
    executed: bool = False
    fresh_output_observed: bool = False
    output_complete: bool = False
    observed_device_name: str = ""
    device_identity_provenance: str = ""
    ports: tuple[TrunkPortReading, ...] = ()
    channel_calls: int = 0
    call_budget_exhausted: bool = False
    after_deadline: bool = False
    failure_reason: str = ""

    @property
    def authoritative(self) -> bool:
        """Whether this reading may speak for its switch at all."""
        return bool(
            self.executed
            and self.fresh_output_observed
            and self.output_complete
            and not self.call_budget_exhausted
            and not self.after_deadline
            and self.observed_device_name == self.switch_name
            and self.device_identity_provenance == CONFIRMED_UNIQUE
        )

    def port(self, interface: str) -> TrunkPortReading | None:
        """Return the reading of one requested interface."""
        return next((item for item in self.ports if item.interface == interface), None)


@dataclass(frozen=True)
class TrunkContinuityRound:
    """Every switch of the component read once, or as many as time allowed."""

    index: int
    elapsed_ms: int
    readings: tuple[TrunkSwitchReading, ...]
    complete: bool

    def reading(self, switch_name: str) -> TrunkSwitchReading | None:
        """Return this round's reading of one switch, if it was taken."""
        return next(
            (item for item in self.readings if item.switch_name == switch_name), None
        )


@dataclass(frozen=True)
class TrunkContinuityObservation:
    """One bounded continuity episode over one component, as observed."""

    vlan_id: int
    switch_names: tuple[str, ...]
    rounds: tuple[TrunkContinuityRound, ...] = ()
    deadline_seconds: float = 0.0
    elapsed_ms: int = 0
    deadline_reached: bool = False
    deadline_cause: str = ""
    episode_end_reason: str = ""
    channel_calls: int = 0


@dataclass(frozen=True)
class ContinuityPairVerdict:
    """Whether one dependent's two access switches were joined."""

    client_switch_id: str
    host_switch_id: str
    admitted: bool
    dimension: str
    cause: str = ""


def usable_links(
    component: L2Component,
    names: Mapping[str, str],
    round_: TrunkContinuityRound,
) -> tuple[str, ...]:
    """Return the ids of the links one round shows forwarding the VLAN."""
    usable: list[str] = []
    for link in component.links:
        readings = (
            round_.reading(names.get(link.switch_a_id, link.switch_a_name)),
            round_.reading(names.get(link.switch_b_id, link.switch_b_name)),
        )
        ports = (
            readings[0].port(link.interface_a) if readings[0] else None,
            readings[1].port(link.interface_b) if readings[1] else None,
        )
        if all(item is not None and item.authoritative for item in readings) and all(
            item is not None and item.carries(component.vlan_id) for item in ports
        ):
            usable.append(link.link_id)
    return tuple(usable)


def _connected(component: L2Component, links: Iterable[str]) -> Mapping[str, str]:
    chosen = set(links)
    parent = {item: item for item in component.switch_device_ids}

    def root(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for link in component.links:
        if link.link_id in chosen:
            left, right = root(link.switch_a_id), root(link.switch_b_id)
            if left != right:
                parent[max(left, right)] = min(left, right)
    return {item: root(item) for item in parent}


def round_joins(
    component: L2Component,
    names: Mapping[str, str],
    round_: TrunkContinuityRound,
    pairs: Iterable[tuple[str, str]],
) -> bool:
    """Whether one round joins every required pair; the episode's stop rule."""
    roots = _connected(component, usable_links(component, names, round_))
    return all(
        left in roots and right in roots and roots[left] == roots[right]
        for left, right in pairs
    )


def _settled(observation: TrunkContinuityObservation) -> bool:
    """Whether the episode ended because its deciding round joined every pair."""
    if (
        observation.episode_end_reason != "required_pairs_joined"
        or not observation.rounds
    ):
        return False
    deciding = observation.rounds[-1]
    return deciding.complete and not any(
        item.after_deadline for item in deciding.readings
    )


def _last_timely_round(
    observation: TrunkContinuityObservation,
) -> TrunkContinuityRound | None:
    return next(
        (
            item
            for item in reversed(observation.rounds)
            if item.complete
            and not any(reading.after_deadline for reading in item.readings)
        ),
        None,
    )


def trunk_continuity_verdicts(
    component: L2Component,
    names: Mapping[str, str],
    observation: TrunkContinuityObservation,
    pairs: Sequence[tuple[str, str]],
) -> tuple[ContinuityPairVerdict, ...]:
    """Decide each required pair, with the access rule's own timeliness.

    Permission comes only from an episode that ended because a complete,
    timely round joined every required pair. An episode that ran out of its
    window authorizes nothing, whatever an earlier round showed: the window is
    the permission, as it is for access samples. The cause still says which
    pairs were joined by the last timely round and which were never joined,
    so a caller can narrow to the pairs that were.
    """
    if not observation.rounds:
        return tuple(
            ContinuityPairVerdict(
                left, right, False, CONTINUITY_NOT_OBSERVED, CAUSE_NO_ROUND
            )
            for left, right in pairs
        )
    if _settled(observation):
        roots = _connected(
            component, usable_links(component, names, observation.rounds[-1])
        )
        return tuple(
            ContinuityPairVerdict(left, right, True, CONTINUITY_NONE)
            if left in roots and right in roots and roots[left] == roots[right]
            else ContinuityPairVerdict(
                left,
                right,
                False,
                CONTINUITY_NO_PATH,
                f"no_forwarding_trunk_path:{left}->{right}",
            )
            for left, right in pairs
        )
    joined = set(joined_pairs(component, names, observation, pairs))
    return tuple(
        ContinuityPairVerdict(
            left,
            right,
            False,
            CONTINUITY_DEADLINE,
            CAUSE_WINDOW_ENDED_UNSETTLED,
        )
        if (left, right) in joined
        else ContinuityPairVerdict(
            left,
            right,
            False,
            CONTINUITY_NO_PATH,
            f"no_forwarding_trunk_path:{left}->{right}",
        )
        for left, right in pairs
    )


def joined_pairs(
    component: L2Component,
    names: Mapping[str, str],
    observation: TrunkContinuityObservation,
    pairs: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    """Return the pairs the last complete, timely round joined.

    This grants nothing. It names the pairs a narrowed, fresh episode may be
    asked about after an episode that other pairs kept from settling.
    """
    round_ = _last_timely_round(observation)
    if round_ is None:
        return ()
    roots = _connected(component, usable_links(component, names, round_))
    return tuple(
        (left, right)
        for left, right in pairs
        if left in roots and right in roots and roots[left] == roots[right]
    )


def continuity_facts(
    component: L2Component,
    names: Mapping[str, str],
    observation: TrunkContinuityObservation,
) -> dict[str, object]:
    """Render the observation for the durable record.

    The first and the deciding round keep every reading. A round between them
    was superseded before any decision and keeps its summary: when it was
    taken, whether it was complete, how many readings were authoritative and
    which links it showed usable. That bounds a long episode on a large
    component without dropping anything a verdict rests on.
    """
    last = len(observation.rounds) - 1

    def rendered(position: int, item: TrunkContinuityRound) -> dict[str, object]:
        row: dict[str, object] = {
            "index": item.index,
            "elapsed_ms": item.elapsed_ms,
            "complete": item.complete,
            "authoritative_readings": sum(
                1 for reading in item.readings if reading.authoritative
            ),
            "usable_links": list(usable_links(component, names, item)),
        }
        if position in (0, last):
            row["readings"] = [asdict(reading) for reading in item.readings]
        return row

    return {
        "vlan_id": observation.vlan_id,
        "switch_names": list(observation.switch_names),
        "deadline_seconds": observation.deadline_seconds,
        "elapsed_ms": observation.elapsed_ms,
        "deadline_reached": observation.deadline_reached,
        "deadline_cause": observation.deadline_cause,
        "episode_end_reason": observation.episode_end_reason,
        "channel_calls": observation.channel_calls,
        "rounds": [
            rendered(position, item) for position, item in enumerate(observation.rounds)
        ],
    }
