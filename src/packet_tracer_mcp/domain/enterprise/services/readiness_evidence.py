"""Re-derive each client's readiness permission from recorded raw observations.

A scalable acceptance never takes the product's word for readiness. Each record
row is parsed strictly back into the observation it renders, bound to the group
the derived scope names, and decided again by the canonical rules: an access
sample by `access_forwarding_admission`, a continuity round by
`usable_links` and `trunk_continuity_verdicts`. Labels, summaries and counts in
the row (`admitted`, `complete`, `usable_links`, `authoritative_readings`) must
agree with that re-derivation; they never grant anything on their own.

Permission is then bound per client. The gate marks the one dependent entry
whose verdict it used, per group, with the revision it decided at; the row
carries the episode's ordinal and the revision it was observed at; the ledger
labels that episode's dispatches `readiness:<group key>#<ordinal>`. A client is
admitted by a group only when exactly one such decision exists, it agrees with
its episode, the re-derivation admits the client's own ports or switch pair,
the whole episode was dispatched before the client's first request, and no
episode of a later revision of that group was dispatched before that request.

Everything is built once per evaluation: one validation per row (one canonical
admission per access episode, one connectivity derivation per continuity
episode), one decision index and, per group, the earliest dispatch of every
later revision. A client then costs lookups in its own relationships.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models.forwarding import (
    AccessForwardingObservation,
    AccessForwardingRow,
    AccessForwardingSampleEvidence,
)
from ..models.scalable_http_acceptance import (
    AcceptanceScope,
    ReadinessGroupScope,
    ScopedClient,
)
from .acceptance_evidence_index import LedgerIndex, readiness_episode_spans
from .access_forwarding import access_forwarding_admission
from .service_access_readiness import (
    access_group_key,
    continuity_group_key,
    trunk_link_ends,
)
from .service_path_closure import L2Component, TrunkLink
from .trunk_continuity import (
    TrunkContinuityObservation,
    TrunkContinuityRound,
    TrunkPortReading,
    TrunkSwitchReading,
    trunk_continuity_verdicts,
    usable_links,
)


class _Malformed(ValueError):
    """One recorded field is absent or of the wrong type."""


def _field(source: Mapping[str, Any], name: str, kind: type | tuple[type, ...]):
    """Return one required field of exactly this type; a bool is never an int."""
    if name not in source:
        raise _Malformed(name)
    value = source[name]
    if isinstance(value, bool) != (kind is bool) or not isinstance(value, kind):
        raise _Malformed(name)
    return value


def _names(source: Mapping[str, Any], name: str) -> tuple[str, ...]:
    value = _field(source, name, list)
    if not all(isinstance(item, str) for item in value):
        raise _Malformed(name)
    return tuple(value)


def _optional_vlans(source: Mapping[str, Any], name: str) -> tuple[int, ...] | None:
    if name not in source:
        raise _Malformed(name)
    value = source[name]
    if value is None:
        return None
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        raise _Malformed(name)
    return tuple(value)


def row_group_key(row: Mapping[str, Any]) -> str | None:
    """Return the text identity of the group one record row reports, if any."""
    vlan = row.get("vlan_id")
    if not isinstance(vlan, int) or isinstance(vlan, bool):
        return None
    if row.get("kind") == "trunk_continuity":
        names = row.get("switch_device_names")
        if isinstance(names, list) and all(isinstance(item, str) for item in names):
            return continuity_group_key(vlan, names)
        return None
    if "kind" in row:
        return None
    name = row.get("switch_device_name")
    return access_group_key(name, vlan) if isinstance(name, str) and name else None


# -- access samples ---------------------------------------------------------------


def _access_rows(items: object, name: str) -> tuple[AccessForwardingRow, ...]:
    if not isinstance(items, list):
        raise _Malformed(name)
    rows = []
    for item in items:
        if not isinstance(item, Mapping):
            raise _Malformed(name)
        rows.append(
            AccessForwardingRow(
                interface=_field(item, "interface", str),
                matches=_field(item, "matches", int),
                state=_field(item, "state", str),
                role=_field(item, "role", str),
            )
        )
    return tuple(rows)


def _history_entry(item: object) -> AccessForwardingSampleEvidence:
    if not isinstance(item, Mapping):
        raise _Malformed("sample_history")
    return AccessForwardingSampleEvidence(
        elapsed_ms=_field(item, "elapsed_ms", int),
        rows=_access_rows(item.get("rows"), "sample_history.rows"),
        executed=_field(item, "executed", bool),
        fresh_output_observed=_field(item, "fresh_output_observed", bool),
        output_complete=_field(item, "output_complete", bool),
        observed_device_name=_field(item, "observed_device_name", str),
        device_identity_provenance=_field(item, "device_identity_provenance", str),
        vlan_present=_field(item, "vlan_present", bool),
        channel_calls=_field(item, "channel_calls", int),
        sample_budget_exhausted=_field(item, "sample_budget_exhausted", bool),
        deadline_reached=_field(item, "deadline_reached", bool),
    )


def parse_access_sample(sample: Mapping[str, Any]) -> AccessForwardingObservation:
    """Rebuild the observation one recorded access sample renders.

    Raises `ValueError` naming the first field that is absent or of the wrong
    type. Nothing is defaulted: a missing fact is not a negative one.
    """
    history = _field(sample, "sample_history", list)
    return AccessForwardingObservation(
        switch_name=_field(sample, "switch", str),
        vlan_id=_field(sample, "vlan_id", int),
        requested_interfaces=_names(sample, "requested_interfaces"),
        rows=_access_rows(sample.get("rows"), "rows"),
        executed=_field(sample, "executed", bool),
        fresh_output_observed=_field(sample, "fresh_output_observed", bool),
        output_complete=_field(sample, "output_complete", bool),
        observed_device_name=_field(sample, "observed_device_name", str),
        device_identity_provenance=_field(sample, "device_identity_provenance", str),
        vlan_present=_field(sample, "vlan_present", bool),
        samples=_field(sample, "samples", int),
        sample_history=tuple(_history_entry(item) for item in history),
        max_samples=_field(sample, "max_samples", int),
        deadline_seconds=float(_field(sample, "deadline_seconds", (int, float))),
        elapsed_ms=_field(sample, "elapsed_ms", int),
        deadline_reached=_field(sample, "deadline_reached", bool),
        deadline_cause=_field(sample, "deadline_cause", str),
        deadline_scope=_field(sample, "deadline_scope", str),
        sample_call_budget=_field(sample, "sample_call_budget", int),
        channel_calls=_field(sample, "channel_calls", int),
        sample_budget_exhausted=_field(sample, "sample_budget_exhausted", bool),
        sample_after_deadline=_field(sample, "sample_after_deadline", bool),
        episode_budget_exhausted=_field(sample, "episode_budget_exhausted", bool),
        episode_end_reason=_field(sample, "episode_end_reason", str),
        auxiliary_budget_exhausted=_field(sample, "auxiliary_budget_exhausted", bool),
        auxiliary_read_after_deadline=_field(
            sample, "auxiliary_read_after_deadline", bool
        ),
        simulation_time=_field(sample, "simulation_time", str),
        failure_reason=_field(sample, "failure_reason", str),
    )


def _history_disagreement(observation: AccessForwardingObservation) -> str:
    """Name the first authorizing fact the last retained sample does not show."""
    if observation.samples < 1 or observation.samples != len(
        observation.sample_history
    ):
        return "samples"
    last = observation.sample_history[-1]
    for name, top, kept in (
        ("rows", observation.rows, last.rows),
        ("executed", observation.executed, last.executed),
        (
            "fresh_output_observed",
            observation.fresh_output_observed,
            last.fresh_output_observed,
        ),
        ("output_complete", observation.output_complete, last.output_complete),
        (
            "observed_device_name",
            observation.observed_device_name,
            last.observed_device_name,
        ),
        (
            "device_identity_provenance",
            observation.device_identity_provenance,
            last.device_identity_provenance,
        ),
        ("vlan_present", observation.vlan_present, last.vlan_present),
        (
            "sample_budget_exhausted",
            observation.sample_budget_exhausted,
            last.sample_budget_exhausted,
        ),
        (
            "sample_after_deadline",
            observation.sample_after_deadline,
            last.deadline_reached,
        ),
    ):
        if top != kept:
            return name
    return ""


def _repeated_interfaces(rows: Sequence[AccessForwardingRow]) -> bool:
    counts = Counter(item.interface for item in rows)
    return any(count > 1 for count in counts.values())


# -- continuity rounds -------------------------------------------------------------


def _trunk_ports(items: object) -> tuple[TrunkPortReading, ...]:
    if not isinstance(items, list):
        raise _Malformed("ports")
    ports = []
    for item in items:
        if not isinstance(item, Mapping):
            raise _Malformed("ports")
        ports.append(
            TrunkPortReading(
                interface=_field(item, "interface", str),
                matches=_field(item, "matches", int),
                status=_field(item, "status", str),
                allowed_vlans=_optional_vlans(item, "allowed_vlans"),
                active_vlans=_optional_vlans(item, "active_vlans"),
                forwarding_vlans=_optional_vlans(item, "forwarding_vlans"),
            )
        )
    return tuple(ports)


def parse_trunk_reading(item: object) -> TrunkSwitchReading:
    """Rebuild one recorded `show interfaces trunk` reading, strictly."""
    if not isinstance(item, Mapping):
        raise _Malformed("reading")
    return TrunkSwitchReading(
        switch_name=_field(item, "switch_name", str),
        executed=_field(item, "executed", bool),
        fresh_output_observed=_field(item, "fresh_output_observed", bool),
        output_complete=_field(item, "output_complete", bool),
        observed_device_name=_field(item, "observed_device_name", str),
        device_identity_provenance=_field(item, "device_identity_provenance", str),
        ports=_trunk_ports(item.get("ports")),
        channel_calls=_field(item, "channel_calls", int),
        call_budget_exhausted=_field(item, "call_budget_exhausted", bool),
        after_deadline=_field(item, "after_deadline", bool),
        failure_reason=_field(item, "failure_reason", str),
    )


# -- one validated row -------------------------------------------------------------


@dataclass
class _Episode:
    """One record row, validated once against its group in the derived scope."""

    key: str
    row: Mapping[str, Any]
    ordinal: int | None = None
    revision: int | None = None
    #: Refusals that hold for every decision this row carries.
    findings: list[str] = field(default_factory=list)
    #: Access: the interfaces the canonical admission admitted.
    forwarding: frozenset[str] = frozenset()
    #: Continuity: switch id -> deployed name, and each dependent pair's
    #: canonical verdict `(admitted, cause)`.
    names: dict[str, str] = field(default_factory=dict)
    pairs: dict[tuple[str, str], tuple[bool, str]] = field(default_factory=dict)


def _episode_identity(episode: _Episode) -> None:
    identity = episode.row.get("episode")
    if not isinstance(identity, Mapping):
        return
    ordinal, revision = identity.get("ordinal"), identity.get("revision")
    if (
        isinstance(ordinal, int)
        and not isinstance(ordinal, bool)
        and ordinal >= 1
        and isinstance(revision, int)
        and not isinstance(revision, bool)
        and revision >= 0
        and isinstance(identity.get("narrowed"), bool)
    ):
        episode.ordinal, episode.revision = ordinal, revision


def _validate_access(episode: _Episode, group: ReadinessGroupScope) -> None:
    row, found = episode.row, episode.findings
    switch = group.switches[0] if group.switches else ""
    requested = row.get("requested_interfaces")
    if (
        row.get("switch_device_name") != switch
        or row.get("vlan_id") != group.vlan_id
        or not isinstance(requested, list)
        or not requested
        or len(set(requested)) != len(requested)
        or not set(requested) <= set(group.interfaces)
    ):
        found.append(f"access_row_not_the_group:{switch}")
        return
    sample = row.get("sample")
    if not isinstance(sample, Mapping) or not sample:
        found.append(f"access_sample_absent:{switch}")
        return
    try:
        observation = parse_access_sample(sample)
        labels = (
            _field(sample, "admitted", bool),
            _field(sample, "dimension", str),
            _names(sample, "forwarding_interfaces"),
        )
    except _Malformed as exc:
        found.append(f"access_sample_malformed:{exc}:{switch}")
        return
    if (
        observation.switch_name != switch
        or observation.vlan_id != group.vlan_id
        or observation.requested_interfaces != tuple(requested)
    ):
        found.append(f"access_sample_is_not_the_group:{switch}")
        return
    if _repeated_interfaces(observation.rows) or any(
        _repeated_interfaces(item.rows) for item in observation.sample_history
    ):
        found.append(f"access_interface_rows_repeated:{switch}")
        return
    disagreement = _history_disagreement(observation)
    if disagreement:
        found.append(f"access_history_disagrees:{disagreement}:{switch}")
        return
    admission = access_forwarding_admission(observation)
    if labels != (
        admission.admitted,
        admission.dimension,
        tuple(admission.forwarding_interfaces),
    ):
        found.append(f"access_sample_labels_contradict:{switch}")
        return
    if not admission.admitted:
        found.append(f"access_not_admitted:{admission.dimension}:{switch}")
        return
    episode.forwarding = frozenset(admission.forwarding_interfaces)


def _component(episode: _Episode, group: ReadinessGroupScope) -> L2Component | None:
    row, found, key = episode.row, episode.findings, episode.key
    ids, names = row.get("switch_device_ids"), row.get("switch_device_names")
    if (
        row.get("vlan_id") != group.vlan_id
        or not isinstance(ids, list)
        or not isinstance(names, list)
        or tuple(names) != group.switches
        or len(ids) != len(names)
        or len(set(ids)) != len(ids)
        or not all(isinstance(item, str) for item in ids)
    ):
        found.append(f"continuity_row_not_the_group:{key}")
        return None
    episode.names = dict(zip(ids, names, strict=True))
    links: list[TrunkLink] = []
    for item in row.get("links") if isinstance(row.get("links"), list) else [None]:
        if not (
            isinstance(item, Mapping)
            and isinstance(item.get("link_id"), str)
            and item.get("switch_a_id") in episode.names
            and item.get("switch_b_id") in episode.names
            and isinstance(item.get("interface_a"), str)
            and isinstance(item.get("interface_b"), str)
        ):
            found.append(f"continuity_links_malformed:{key}")
            return None
        links.append(
            TrunkLink(
                link_id=item["link_id"],
                switch_a_id=item["switch_a_id"],
                switch_a_name=episode.names[item["switch_a_id"]],
                interface_a=item["interface_a"],
                switch_b_id=item["switch_b_id"],
                switch_b_name=episode.names[item["switch_b_id"]],
                interface_b=item["interface_b"],
                allowed_vlans=(group.vlan_id,),
            )
        )
    ends = sorted(
        trunk_link_ends(
            link.switch_a_name, link.interface_a, link.switch_b_name, link.interface_b
        )
        for link in links
    )
    if ends != list(group.links) or len({link.link_id for link in links}) != len(links):
        found.append(f"continuity_links_differ_from_scope:{key}")
        return None
    return L2Component(
        vlan_id=group.vlan_id,
        switch_device_ids=tuple(ids),
        switch_device_names=tuple(names),
        links=tuple(links),
    )


def _deciding_round(
    episode: _Episode, group: ReadinessGroupScope, component: L2Component
) -> tuple[TrunkContinuityRound, Mapping[str, Any]] | None:
    found, key = episode.findings, episode.key
    sample = episode.row.get("sample")
    if (
        not isinstance(sample, Mapping)
        or sample.get("vlan_id") != group.vlan_id
        or sample.get("switch_names") != list(group.switches)
    ):
        found.append(f"continuity_sample_not_the_group:{key}")
        return None
    rounds = sample.get("rounds")
    deciding = rounds[-1] if isinstance(rounds, list) and rounds else None
    readings = deciding.get("readings") if isinstance(deciding, Mapping) else None
    if not isinstance(readings, list) or not readings:
        found.append(f"continuity_readings_absent:{key}")
        return None
    try:
        parsed = tuple(parse_trunk_reading(item) for item in readings)
        complete = _field(deciding, "complete", bool)
        index = _field(deciding, "index", int)
        elapsed = _field(deciding, "elapsed_ms", int)
        summary = _names(deciding, "usable_links")
        authoritative = _field(deciding, "authoritative_readings", int)
        _field(sample, "episode_end_reason", str)
    except _Malformed as exc:
        found.append(f"continuity_reading_malformed:{exc}:{key}")
        return None
    expected = component.interfaces_by_switch()
    by_name = {
        name: set(expected.get(switch_id, ()))
        for switch_id, name in episode.names.items()
    }
    counts = Counter(item.switch_name for item in parsed)
    for reading in parsed:
        # The first fault names the row: a reading of a switch outside the
        # component, a second reading of one switch, or a reading that does
        # not answer exactly the trunk ports of its switch once each (the
        # runtime asks every one, so a missing port is an unanswered one).
        name = reading.switch_name
        ports = Counter(item.interface for item in reading.ports)
        if name not in by_name:
            found.append(f"continuity_reading_foreign:{name}:{key}")
        elif counts[name] > 1:
            found.append(f"continuity_reading_repeated:{name}:{key}")
        elif set(ports) != by_name[name] or any(value > 1 for value in ports.values()):
            found.append(f"continuity_ports_not_the_trunks:{name}:{key}")
        if found:
            return None
    if complete != (set(counts) == set(by_name)):
        found.append(f"continuity_completeness_contradicted:{key}")
        return None
    round_ = TrunkContinuityRound(
        index=index, elapsed_ms=elapsed, readings=parsed, complete=complete
    )
    derived = usable_links(component, episode.names, round_)
    if sorted(summary) != sorted(derived) or authoritative != sum(
        1 for item in parsed if item.authoritative
    ):
        found.append(f"continuity_summary_contradicts_readings:{key}")
        return None
    return round_, sample


def _validate_continuity(episode: _Episode, group: ReadinessGroupScope) -> None:
    component = _component(episode, group)
    if component is None:
        return
    decided = _deciding_round(episode, group, component)
    if decided is None:
        return
    round_, sample = decided
    observation = TrunkContinuityObservation(
        vlan_id=group.vlan_id,
        switch_names=group.switches,
        rounds=(round_,),
        episode_end_reason=sample["episode_end_reason"],
    )
    pairs = sorted(
        {
            (item.get("client_switch_id"), item.get("host_switch_id"))
            for item in episode.row.get("dependents") or []
            if isinstance(item, Mapping)
            and item.get("client_switch_id") in episode.names
            and item.get("host_switch_id") in episode.names
        }
    )
    for verdict in trunk_continuity_verdicts(
        component, episode.names, observation, pairs
    ):
        episode.pairs[(verdict.client_switch_id, verdict.host_switch_id)] = (
            verdict.admitted,
            verdict.cause or verdict.dimension,
        )


# -- the evaluation context --------------------------------------------------------


@dataclass
class ReadinessEvidence:
    """Every readiness row of one record, validated once, and its decisions."""

    groups: dict[str, ReadinessGroupScope] = field(default_factory=dict)
    members: dict[str, frozenset[str]] = field(default_factory=dict)
    decisions: dict[tuple[str, str], list[tuple[_Episode, Mapping[str, Any]]]] = field(
        default_factory=dict
    )
    repeated: set[tuple[str, str]] = field(default_factory=set)
    group_findings: dict[str, list[str]] = field(default_factory=dict)
    spans: dict[str, dict[int, tuple[int, int]]] = field(default_factory=dict)
    #: Per group: revisions in ascending order, and the earliest first dispatch
    #: among episodes of that revision or any later one.
    later: dict[str, tuple[list[int], list[int]]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        rows: Sequence[object],
        scope: AcceptanceScope,
        ledger: LedgerIndex,
        spans: Mapping[str, Mapping[int, tuple[int, int]]] | None = None,
    ) -> ReadinessEvidence:
        """Validate each row of a scoped group once; ignore every other row."""
        evidence = cls(
            groups={item.key: item for item in scope.groups},
            members={item.key: frozenset(item.dependents) for item in scope.groups},
            spans={
                key: dict(value)
                for key, value in (
                    readiness_episode_spans(ledger) if spans is None else spans
                ).items()
            },
        )
        ordinals: dict[str, Counter[int]] = {}
        revisions: dict[str, dict[int, int]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            key = row_group_key(row)
            group = evidence.groups.get(key or "")
            if group is None:
                # Not a group of this scope: it cannot speak for any client.
                continue
            episode = _Episode(key=group.key, row=row)
            _episode_identity(episode)
            if group.kind == "access":
                _validate_access(episode, group)
            else:
                _validate_continuity(episode, group)
            if episode.ordinal is not None:
                ordinals.setdefault(group.key, Counter())[episode.ordinal] += 1
                span = evidence.spans.get(group.key, {}).get(episode.ordinal)
                if span is not None:
                    earliest = revisions.setdefault(group.key, {})
                    earliest[episode.revision] = min(
                        span[0], earliest.get(episode.revision, span[0])
                    )
            dependents = [
                item
                for item in (row.get("dependents") or [])
                if isinstance(item, Mapping)
            ]
            listed = Counter(str(item.get("expectation_id")) for item in dependents)
            for item in dependents:
                expectation = str(item.get("expectation_id"))
                if listed[expectation] > 1:
                    evidence.repeated.add((group.key, expectation))
                if "decision" in item:
                    evidence.decisions.setdefault((group.key, expectation), []).append(
                        (episode, item)
                    )
        for key in evidence.groups:
            found = evidence.group_findings.setdefault(key, [])
            counted = ordinals.get(key, Counter())
            found.extend(
                f"readiness_episode_repeated:{key}#{ordinal}"
                for ordinal, count in sorted(counted.items())
                if count > 1
            )
            found.extend(
                f"readiness_episode_unrecorded:{key}#{ordinal}"
                for ordinal in sorted(evidence.spans.get(key, {}))
                if ordinal not in counted
            )
            earliest = revisions.get(key, {})
            ordered = sorted(earliest)
            suffix: list[int] = []
            for revision in reversed(ordered):
                value = earliest[revision]
                suffix.append(min(value, suffix[-1]) if suffix else value)
            evidence.later[key] = (ordered, list(reversed(suffix)))
        return evidence

    def evidence_findings(self) -> list[str]:
        """Return every group-level inconsistency, each once, in group order.

        A repeated episode ordinal and a ledger episode no row records are
        faults of the record itself, not of any one client's path.
        """
        return [item for key in self.groups for item in self.group_findings[key]]

    def _superseded_from(self, key: str, revision: int) -> int | None:
        """Return the earliest dispatch of any episode of a later revision."""
        ordered, suffix = self.later.get(key, ([], []))
        position = bisect_right(ordered, revision)
        return suffix[position] if position < len(ordered) else None

    def findings_for(
        self, client: ScopedClient, first_request: int | None
    ) -> list[str]:
        """Require every group the client's path names to have admitted it."""
        found: list[str] = []
        if not client.groups:
            found.append("no_readiness_group")
        for key in client.groups:
            group = self.groups.get(key)
            if group is None:
                found.append(f"group_not_in_scope:{key}")
                continue
            found.extend(self._group_findings(client, group, first_request))
        return found

    def _group_findings(
        self,
        client: ScopedClient,
        group: ReadinessGroupScope,
        first_request: int | None,
    ) -> list[str]:
        key, expectation = group.key, client.expectation_id
        found: list[str] = []
        if self.group_findings.get(key):
            # Each inconsistency is reported once for the attempt
            # (`evidence_findings`); every client of the group gets one
            # bounded reference to it, never a copy of the list.
            found.append(f"readiness_group_evidence_inconsistent:{key}")
        if expectation not in self.members.get(key, frozenset()):
            found.append(f"readiness_dependent_not_in_scope:{key}")
        if (key, expectation) in self.repeated:
            found.append(f"readiness_dependent_repeated:{key}")
        marks = self.decisions.get((key, expectation), [])
        if not marks:
            return [*found, f"readiness_decision_absent:{key}"]
        if len(marks) > 1:
            return [*found, f"readiness_decision_ambiguous:{key}"]
        episode, dependent = marks[0]
        found.extend(episode.findings)
        if episode.ordinal is None:
            return [*found, f"readiness_episode_identity_absent:{key}"]
        decision = dependent.get("decision")
        revision = decision.get("revision") if isinstance(decision, Mapping) else None
        if revision != episode.revision or isinstance(revision, bool):
            found.append(f"readiness_permission_stale:{key}")
        if dependent.get("admitted") is not True:
            found.append(f"readiness_group_refused:{key}")
        if group.kind == "access":
            found.extend(_access_dependent(episode, group, client, dependent))
        else:
            found.extend(_continuity_dependent(episode, client, dependent))
        if first_request is not None:
            span = self.spans.get(key, {}).get(episode.ordinal)
            if span is None:
                found.append(f"readiness_episode_not_dispatched:{key}")
            elif span[1] >= first_request:
                found.append(f"readiness_episode_not_before_request:{key}")
            superseded = self._superseded_from(key, episode.revision)
            if superseded is not None and superseded < first_request:
                found.append(f"readiness_permission_superseded_before_request:{key}")
        return found


def _access_dependent(
    episode: _Episode,
    group: ReadinessGroupScope,
    client: ScopedClient,
    dependent: Mapping[str, Any],
) -> list[str]:
    switch = group.switches[0] if group.switches else ""
    covered = dependent.get("interfaces")
    covered = set(covered) if isinstance(covered, list) else set()
    found: list[str] = []
    for owner, port in (
        (client.switch, client.port),
        (client.server_switch, client.server_port),
    ):
        if owner != switch:
            continue
        if port not in episode.forwarding:
            found.append(f"access_port_not_forwarding:{switch}:{port}")
        if port not in covered:
            found.append(f"access_dependent_does_not_cover:{switch}:{port}")
    return found


def _continuity_dependent(
    episode: _Episode, client: ScopedClient, dependent: Mapping[str, Any]
) -> list[str]:
    pair = (dependent.get("client_switch_id"), dependent.get("host_switch_id"))
    names = episode.names
    if (names.get(pair[0]), names.get(pair[1])) != (
        client.switch,
        client.server_switch,
    ):
        return [f"continuity_dependent_is_not_the_path:{episode.key}"]
    admitted, cause = episode.pairs.get(pair, (False, "pair_not_rederived"))
    return [] if admitted else [f"continuity_pair_not_joined:{episode.key}:{cause}"]
