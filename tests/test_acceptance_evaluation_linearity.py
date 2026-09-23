"""The scalable evaluator's cost grows linearly with the evidence it judges.

Evidence comes from real attempts over SIMULATED campuses of growing size:
more clients, more access groups, more E5 readback entries and more shared
continuity components (one per site). The evaluator then judges that evidence
while every container it reads counts the elements it hands out, and every
canonical rule it derives permission with counts its calls. Wall time is not
the measure; element visits and builds are, and they are deterministic.
"""

from __future__ import annotations

import copy
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from campus_product_simulation import campus_payload, compose_campus
from cold_http_acceptance_harness import MARKER
from scalable_http_acceptance_harness import build_scalable_harness

from packet_tracer_mcp.application.use_cases import accept_cold_http
from packet_tracer_mcp.domain.enterprise.services import (
    acceptance_evidence_index,
    readiness_evidence,
)
from packet_tracer_mcp.domain.enterprise.services import (
    scalable_http_acceptance_evidence as evaluator,
)

#: (clients, sites): each site is one shared continuity component.
SIZES = ((30, 1), (90, 3), (240, 3))


class CountingList(list):
    """A list that counts every element it hands out, by tag."""

    def __init__(self, items, tag: str, counts: Counter) -> None:
        """Hold the elements and the shared counter they are charged to."""
        super().__init__(items)
        self._tag = tag
        self._counts = counts

    def __iter__(self):
        """Yield each element, counting it."""
        for item in super().__iter__():
            self._counts[self._tag] += 1
            yield item

    def __getitem__(self, index):
        """Return an element or a slice, counting what it hands out."""
        value = super().__getitem__(index)
        self._counts[self._tag] += len(value) if isinstance(index, slice) else 1
        return value


def _captured(tmp_path: Path, clients: int, sites: int) -> dict[str, Any]:
    plans = compose_campus(campus_payload(clients, marker=MARKER, sites=sites))
    harness = build_scalable_harness(tmp_path, clients, plans=plans)
    captured: dict[str, Any] = {}
    real = accept_cold_http.evaluate_scalable_attempt

    def spy(grant, scope, **kwargs):
        captured.update(copy.deepcopy(kwargs), grant=grant, scope=scope)
        return real(grant, scope, **kwargs)

    patch = pytest.MonkeyPatch()
    patch.setattr(accept_cold_http, "evaluate_scalable_attempt", spy)
    try:
        result = harness.run()
    finally:
        patch.undo()
    assert result.envelope.http_accepted is True, result.envelope.reasons[:5]
    return captured


@pytest.fixture(scope="module")
def evidence(tmp_path_factory) -> dict[tuple[int, int], dict[str, Any]]:
    """Evidence of one real attempt per size, captured once."""
    return {
        size: _captured(tmp_path_factory.mktemp(f"linear{size[0]}"), *size)
        for size in SIZES
    }


def _measure(captured: dict[str, Any], monkeypatch: pytest.MonkeyPatch):
    """Judge one capture with counting containers and counting rules."""
    counts: Counter = Counter()
    builds: Counter = Counter()
    rows = []
    for item in copy.deepcopy(
        [dict(row) for row in captured["record"].operational_readiness]
    ):
        item["dependents"] = CountingList(item["dependents"], "dependents", counts)
        if "links" in item:
            item["links"] = CountingList(item["links"], "links", counts)
            deciding = item["sample"]["rounds"][-1]
            deciding["readings"] = CountingList(
                deciding["readings"], "readings", counts
            )
        rows.append(item)
    record = captured["record"].model_copy(
        update={"operational_readiness": CountingList(rows, "rows", counts)}
    )
    real_build = acceptance_evidence_index.LedgerIndex.build.__func__

    def counting_build(cls, entries):
        index = real_build(cls, entries)
        index.dispatched = {
            purpose: CountingList(
                positions,
                "e5_verify" if purpose == "e5_verify" else "positions",
                counts,
            )
            for purpose, positions in index.dispatched.items()
        }
        return index

    monkeypatch.setattr(
        acceptance_evidence_index.LedgerIndex, "build", classmethod(counting_build)
    )
    for name in (
        "access_forwarding_admission",
        "trunk_continuity_verdicts",
        "usable_links",
    ):
        real = getattr(readiness_evidence, name)

        def counted(*args, _real=real, _name=name, **kwargs):
            builds[_name] += 1
            return _real(*args, **kwargs)

        monkeypatch.setattr(readiness_evidence, name, counted)
    entries = CountingList(captured["entries"], "entries", counts)
    evaluation = evaluator.evaluate_scalable_attempt(
        captured["grant"],
        captured["scope"],
        closure=captured["closure"],
        record=record,
        record_problems=list(captured["record_problems"]),
        summary=captured["summary"],
        record_path=captured["record_path"],
        entries=entries,
        answers=captured["answers"],
        stop_facts=list(captured["stop_facts"]),
    )
    monkeypatch.undo()
    return evaluation, counts, builds


def _size(captured: dict[str, Any]) -> dict[str, int]:
    rows = captured["record"].operational_readiness
    return {
        "entries": len(captured["entries"]),
        "e5_verify": sum(
            1 for item in captured["entries"] if item.purpose == "e5_verify"
        ),
        "rows": len(rows),
        "access_rows": sum(1 for item in rows if "kind" not in item),
        "continuity_rows": sum(1 for item in rows if item.get("kind")),
        "dependents": sum(len(item["dependents"]) for item in rows),
        "links": sum(len(item.get("links", [])) for item in rows),
        "readings": sum(
            len(item["sample"]["rounds"][-1]["readings"])
            for item in rows
            if item.get("kind")
        ),
        "clients": len(captured["scope"].clients),
        "groups": len(captured["scope"].groups),
    }


def test_the_evidence_grows_in_every_dimension(evidence):
    """The sizes really grow in clients, groups, E5 entries and components."""
    sizes = [_size(evidence[size]) for size in SIZES]
    for smaller, larger in pairwise(sizes):
        for dimension in ("clients", "groups", "e5_verify", "dependents"):
            assert larger[dimension] > smaller[dimension], dimension
    assert [item["continuity_rows"] for item in sizes] == [1, 3, 3]
    assert sizes[-1]["links"] > sizes[0]["links"]


@pytest.mark.parametrize("size", SIZES, ids=lambda item: f"{item[0]}x{item[1]}")
def test_each_episode_is_derived_once_and_each_element_read_a_bounded_number_of_times(
    evidence, size, monkeypatch: pytest.MonkeyPatch
):
    """Builds equal episodes; visits stay within a constant of the evidence."""
    captured = evidence[size]
    measured = _size(captured)

    evaluation, counts, builds = _measure(captured, monkeypatch)

    # Full outcomes: every client judged and accepted, nothing sampled.
    assert len(evaluation.clients) == measured["clients"]
    assert all(item.accepted for item in evaluation.clients)
    # One canonical derivation per episode, never per client or dependent.
    assert builds["access_forwarding_admission"] == measured["access_rows"]
    assert builds["trunk_continuity_verdicts"] == measured["continuity_rows"]
    assert builds["usable_links"] == measured["continuity_rows"]
    # The E5 boundary's maximum is read once, whatever the number of clients.
    assert counts["e5_verify"] == 1
    # Every other element is handed out a bounded number of times: once by the
    # readiness evidence and once by the reload comparison, which serializes
    # the record; dependents once more for the continuity pairs.
    assert counts["rows"] == 2 * measured["rows"]
    assert counts["dependents"] <= 3 * measured["dependents"]
    assert counts["links"] == 2 * measured["links"]
    assert counts["readings"] == 2 * measured["readings"]
    assert counts["entries"] <= 2 * measured["entries"]
    assert counts["positions"] <= 3 * measured["entries"]


def test_the_counting_apparatus_sees_a_per_client_scan(evidence):
    """Control: a maximum taken inside the client loop is N x E5 visits."""
    for size in SIZES:
        captured = evidence[size]
        counts: Counter = Counter()
        e5 = CountingList(
            [
                position
                for position, item in enumerate(captured["entries"])
                if item.purpose == "e5_verify"
            ],
            "e5",
            counts,
        )
        for _ in captured["scope"].clients:
            max(e5)
        measured = _size(captured)
        assert counts["e5"] == measured["clients"] * measured["e5_verify"]
