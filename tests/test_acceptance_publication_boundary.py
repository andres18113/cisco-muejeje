"""One publication boundary for timeliness and cancellation.

The terminal link is the publication point. Every controlled step that shapes
the published bytes -- the evidence join, the verdict, the budget assembly,
and inside the store the begun envelope's reload, the serialization and the
flush -- consumes the one absolute deadline; past it acceptance is withheld,
the evidence is kept and the boundary is named. The link itself is bounded,
not claimed: a write-once publication fact records the last checkpoint before
it and the instant it returned, and acceptance is established only when that
upper bound is within the deadline.

Everything runs through the real coordinator and the real envelope store over
the legacy two-client harness (simulated Packet Tracer, fake clock, 420 s).
Delays and interruptions are injected into the store's own filesystem steps.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from cold_http_acceptance_harness import ATTEMPT, build_harness

from packet_tracer_mcp.application.use_cases import accept_cold_http
from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    ColdHttpAcceptanceEnvelope,
    publication_claim,
)
from packet_tracer_mcp.infrastructure.persistence import (
    cold_http_acceptance_store as store_module,
)

LATE = 500.0
COMPLETED = f"{ATTEMPT}.completed.json"
PUBLICATION = f"{ATTEMPT}.publication.json"


def _files(harness) -> list[str]:
    return sorted(item.name for item in harness.envelope_store.base_dir.iterdir())


def _delay_link(monkeypatch, harness, *, before=None, after=None, times=1):
    """Wrap the store's `os.link` for the terminal file only."""
    real = store_module.os.link
    state = {"left": times}

    def link(source, destination):
        terminal = str(destination).endswith(COMPLETED) and state["left"] > 0
        if terminal:
            state["left"] -= 1
            if before is not None:
                before()
        real(source, destination)
        if terminal and after is not None:
            after()

    monkeypatch.setattr(store_module.os, "link", link)


# -- timely success ----------------------------------------------------------------


def test_a_timely_attempt_is_accepted_with_its_publication_fact(tmp_path: Path):
    """R3a: the verdict, the checkpoint and the link all fit the deadline."""
    harness = build_harness(tmp_path)

    result = harness.run()

    assert result.accepted is True
    assert result.exit_code == 0
    publication = result.publication
    stored = harness.envelope_store.load_publication(ATTEMPT)
    assert stored == publication
    assert publication.observed_by == "coordinator"
    assert publication.provisional_http_accepted is True
    assert publication.link_within_deadline is True
    assert publication.http_accepted is True
    assert (
        publication.decided_offset_seconds
        <= publication.link_checked_offset_seconds
        <= publication.link_returned_offset_seconds
        <= publication.deadline_offset_seconds
    )
    terminal = harness.envelope_store.completed_path_for(ATTEMPT)
    assert (
        publication.terminal_sha256 == hashlib.sha256(terminal.read_bytes()).hexdigest()
    )
    assert _files(harness) == sorted([f"{ATTEMPT}.json", COMPLETED, PUBLICATION])
    summary = result.compact_summary()
    assert summary["http_accepted"] is True
    assert summary["publication"] == "accepted"
    envelope = harness.envelope_store.load(ATTEMPT)
    assert publication_claim(envelope, stored) == (True, "")


# -- R3b: a step after the verdict that crosses the deadline ----------------------


def _late_budget(harness, monkeypatch):
    real = accept_cold_http._budget

    def budget(grant, ledger, attempt):
        built = real(grant, ledger, attempt)
        if attempt.phase == "publication":
            harness.clock.now += LATE
        return built

    monkeypatch.setattr(accept_cold_http, "_budget", budget)


def _late_reload(harness, monkeypatch):
    store = harness.envelope_store
    real = store._read
    state = {"fired": False}

    def read(path):
        found = real(path)
        if not state["fired"]:
            state["fired"] = True
            harness.clock.now += LATE
        return found

    monkeypatch.setattr(store, "_read", read)


def _late_serialization(harness, monkeypatch):
    real = ColdHttpAcceptanceEnvelope.model_dump_json
    state = {"fired": False}

    def dump(self, *args, **kwargs):
        text = real(self, *args, **kwargs)
        if self.completed_at is not None and not state["fired"]:
            state["fired"] = True
            harness.clock.now += LATE
        return text

    monkeypatch.setattr(ColdHttpAcceptanceEnvelope, "model_dump_json", dump)


def _late_flush(harness, monkeypatch):
    """Delay the flush of the first terminal write, and nothing else.

    `os.fsync` is process-wide, so the delay is scoped to the envelope
    store's own `complete`; the product record store flushes too.
    """
    store = harness.envelope_store
    real_fsync, real_complete = store_module.os.fsync, store.complete
    state = {"completing": False, "fired": False}

    def fsync(descriptor):
        real_fsync(descriptor)
        if state["completing"] and not state["fired"]:
            state["fired"] = True
            harness.clock.now += LATE

    def complete(envelope, **kwargs):
        state["completing"] = True
        try:
            return real_complete(envelope, **kwargs)
        finally:
            state["completing"] = False

    monkeypatch.setattr(store_module.os, "fsync", fsync)
    monkeypatch.setattr(store, "complete", complete)


@pytest.mark.parametrize(
    ("delay", "boundary"),
    [
        (_late_budget, "budget"),
        (_late_reload, "envelope_reload"),
        (_late_serialization, "envelope_serialization"),
        (_late_flush, "envelope_flush"),
    ],
)
def test_a_step_after_the_verdict_that_crosses_the_deadline_withholds_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delay, boundary
):
    """R3b: the same evidence is published once, late, naming the boundary."""
    harness = build_harness(tmp_path)
    delay(harness, monkeypatch)

    result = harness.run()

    reason = f"acceptance_deadline_exceeded:{boundary}"
    envelope = result.envelope
    assert result.accepted is False
    assert result.exit_code == 1
    assert envelope.http_accepted is False
    assert envelope.temporal["exceeded_at"] == boundary
    assert reason in envelope.reasons
    assert envelope.primary_failure == reason
    # The late evidence is kept: every client was judged and accepted.
    assert envelope.clients and all(item.accepted for item in envelope.clients)
    assert len(envelope.product["record_sha256"]) == 64
    stored = harness.envelope_store.load(ATTEMPT)
    assert stored.http_accepted is False
    assert reason in stored.reasons
    assert result.persisted is True
    assert result.publication.provisional_http_accepted is False
    assert result.publication.http_accepted is False
    assert _files(harness) == sorted([f"{ATTEMPT}.json", COMPLETED, PUBLICATION])


# -- R3c: a link that returns after the deadline ----------------------------------


def test_a_link_that_returns_after_the_deadline_does_not_establish_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """R3c: the verdict was on time; when it was published is only bounded."""
    harness = build_harness(tmp_path)

    def late():
        harness.clock.now += LATE

    _delay_link(monkeypatch, harness, after=late)

    result = harness.run()

    stored = harness.envelope_store.load(ATTEMPT)
    publication = harness.envelope_store.load_publication(ATTEMPT)
    # The immutable terminal envelope keeps its provisional verdict ...
    assert stored.http_accepted is True
    # ... and the fact beside it says the link was not established in time.
    assert publication.link_checked_offset_seconds <= 420.0
    assert publication.link_returned_offset_seconds > 420.0
    assert publication.link_within_deadline is False
    assert publication.http_accepted is False
    assert publication_claim(stored, publication) == (
        False,
        "publication_not_established_within_deadline",
    )
    assert result.accepted is False
    assert result.exit_code == 1
    summary = result.compact_summary()
    assert summary["http_accepted"] is False
    assert summary["provisional_http_accepted"] is True
    assert summary["publication"] == "publication_not_established_within_deadline"


# -- R3d: persistence errors and interruptions at the publication point -----------


def test_a_persistence_error_withdraws_a_timely_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """R3d: nothing linked, nothing claimed, the failure named apart."""
    harness = build_harness(tmp_path)

    def refused():
        raise PermissionError("read-only store")

    _delay_link(monkeypatch, harness, before=refused)

    result = harness.run()

    envelope = result.envelope
    assert result.persisted is False
    assert result.accepted is False
    assert envelope.http_accepted is False
    assert "envelope_not_completed:RunRecordPersistenceError" in (
        envelope.persistence_failures
    )
    assert result.publication is None
    assert COMPLETED not in _files(harness)


def test_a_late_decision_whose_late_write_fails_keeps_the_first_failure_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """R3d: the deadline is the first failure; the lost write is a second one."""
    harness = build_harness(tmp_path)
    _late_flush(harness, monkeypatch)

    def refused():
        raise PermissionError("read-only store")

    _delay_link(monkeypatch, harness, before=refused)

    result = harness.run()

    envelope = result.envelope
    assert envelope.primary_failure == "acceptance_deadline_exceeded:envelope_flush"
    assert "envelope_not_completed:RunRecordPersistenceError" in (
        envelope.persistence_failures
    )
    assert result.persisted is False
    assert result.accepted is False
    assert COMPLETED not in _files(harness)


def test_an_interruption_immediately_before_the_link_is_a_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """R3d: nothing was published, so the attempt completes as cancelled."""
    harness = build_harness(tmp_path)

    def interrupted():
        raise KeyboardInterrupt

    _delay_link(monkeypatch, harness, before=interrupted)

    with pytest.raises(KeyboardInterrupt):
        harness.run()

    stored = harness.envelope_store.load(ATTEMPT)
    assert stored.cancellation.startswith("cancelled:KeyboardInterrupt@")
    assert stored.primary_failure == stored.cancellation
    assert stored.http_accepted is False
    publication = harness.envelope_store.load_publication(ATTEMPT)
    assert publication.provisional_http_accepted is False
    assert publication.http_accepted is False
    assert _files(harness) == sorted([f"{ATTEMPT}.json", COMPLETED, PUBLICATION])


@pytest.mark.parametrize("late", [False, True], ids=["in_time", "late"])
def test_an_interruption_immediately_after_the_link_keeps_the_published_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, late: bool
):
    """R3d: the verdict stands; its fact is recorded from the store's answer."""
    harness = build_harness(tmp_path)

    def interrupted():
        if late:
            harness.clock.now += LATE
        raise KeyboardInterrupt

    _delay_link(monkeypatch, harness, after=interrupted)

    with pytest.raises(KeyboardInterrupt):
        harness.run()

    stored = harness.envelope_store.load(ATTEMPT)
    publication = harness.envelope_store.load_publication(ATTEMPT)
    assert stored.http_accepted is True
    assert stored.cancellation == ""
    assert publication.observed_by == "interruption_recovery"
    assert publication.interruption == "KeyboardInterrupt"
    assert publication.link_within_deadline is (not late)
    assert publication_claim(stored, publication)[0] is (not late)
    assert _files(harness) == sorted([f"{ATTEMPT}.json", COMPLETED, PUBLICATION])


def test_an_interruption_while_recording_the_fact_still_records_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """R3d: the owed fact is recovered once; the envelope is never rewritten."""
    harness = build_harness(tmp_path)
    store = harness.envelope_store
    real = store.record_publication
    state = {"fired": False}

    def record(publication):
        if not state["fired"]:
            state["fired"] = True
            raise KeyboardInterrupt
        return real(publication)

    monkeypatch.setattr(store, "record_publication", record)

    with pytest.raises(KeyboardInterrupt):
        harness.run()

    stored = store.load(ATTEMPT)
    publication = store.load_publication(ATTEMPT)
    assert stored.http_accepted is True
    assert publication.observed_by == "interruption_recovery"
    assert publication_claim(stored, publication) == (True, "")
