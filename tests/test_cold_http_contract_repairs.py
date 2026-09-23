"""Causal regressions for the four execution-contract repairs (A1-A4).

Everything below the terminal, the clock, git, the process table and the
campaign scope is the production code: the acceptance coordinator, the shared
session composition, the product use case, both runtimes, the readiness loop,
the ledger and every store. Each test reproduces one way the contract failed
before its repair and names what it proves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cold_http_acceptance_harness import (
    ATTEMPT,
    PC1,
    PC2,
    ColdHttpTerminal,
    build_harness,
    paired_process,
)
from service_entry_fixture import DEPLOYMENT_ID

from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.application.use_cases import accept_cold_http
from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    AcceptanceSubject,
    CampaignOutcome,
    receiver_continuity_findings,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
)
from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    LOCK_NAME,
)

REPLACEMENT = "2026-09-22T09:05:00.0000000-05:00"

#: What the process table can say once the paired receiver is gone or shared.
REPLACEMENTS = {
    "different_pid": paired_process(process_id=4243, process_incarnation=REPLACEMENT),
    "same_pid_new_incarnation": paired_process(process_incarnation=REPLACEMENT),
    "receiver_gone": DiagnosticLifecycleObservation(
        error="packet_tracer_process_count:0"
    ),
    "two_receivers": DiagnosticLifecycleObservation(
        error="packet_tracer_process_count:2"
    ),
    "identity_unreadable": paired_process(process_incarnation=""),
}

#: Transport milestones: the E5 endpoint batch, the first readiness sample and
#: the first client start. The replacement happens while that dispatch is in
#: flight, so it is the last one the paired receiver could have answered.
MILESTONES = ("send", "readiness", "http_start")


def _replace_at(harness, milestone: str, observation) -> None:
    fired = {"done": False}

    def replace(kind: str) -> None:
        if kind == milestone and not fired["done"]:
            fired["done"] = True
            harness.receiver.replace_with(observation)

    harness.terminal.on_dispatch = replace


# -- A1: receiver continuity at each governed dispatch ------------------------------


@pytest.mark.parametrize("milestone", MILESTONES)
@pytest.mark.parametrize("replacement", sorted(REPLACEMENTS))
def test_no_governed_dispatch_reaches_a_replaced_receiver(
    tmp_path: Path, milestone: str, replacement: str
):
    """A1: after the milestone the replacement receives nothing, releases included."""
    harness = build_harness(tmp_path)
    _replace_at(harness, milestone, REPLACEMENTS[replacement])

    result = harness.run()

    envelope = result.envelope
    kinds = harness.product_dispatches()
    first = kinds.index(milestone)
    assert kinds[first + 1 :] == [], kinds[first:]
    assert envelope.primary_failure.startswith("authority_lost:process_instance:")
    assert envelope.http_accepted is False
    assert envelope.campaign_outcome is CampaignOutcome.STOPPED
    refused = [item for item in envelope.budget.entries if item.refused]
    assert refused and refused[0].refused.startswith(
        "execution_authority_lost:process_instance:"
    )
    if milestone == "http_start":
        # The owned client's protected release is not sent to the replacement;
        # ownership is left unresolved and said so.
        started = next(item for item in envelope.clients if item.dispatches)
        assert started.release_dispatches == 0
        assert "client_ownership_unresolved" in started.findings


def test_every_governed_dispatch_is_decided_by_its_own_fresh_reading(
    tmp_path: Path,
):
    """A1: one reading per counted dispatch; nothing about permission is reused."""
    harness = build_harness(tmp_path)

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons
    assert harness.receiver.checks == envelope.budget.used_operations
    assert envelope.budget.receiver_observations == harness.receiver.checks
    assert (
        harness.receiver.bound_to.process_incarnation
        == paired_process().process_incarnation
    )
    assert harness.receiver.closed is True
    assert envelope.process_preflight["receiver_binding"] == "FakeReceiver"


def test_a_failed_read_sample_with_an_unchanged_receiver_is_still_accepted(
    tmp_path: Path,
):
    """A1 positive control: a lost product answer is not a lost receiver."""
    harness = build_harness(tmp_path)
    undelivered = {"left": 1}

    def latency(script: str) -> float:
        if ColdHttpTerminal._kind(script) == "readiness" and undelivered["left"]:
            undelivered["left"] -= 1
            return 1e9
        return 0.0

    harness.terminal.latency = latency

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons
    history = envelope.readiness[0]["sample"]["sample_history"]
    assert len(history) >= 2
    assert history[0]["executed"] is False or not history[0]["rows"]
    assert envelope.primary_failure == ""


def test_a_receiver_that_cannot_be_bound_refuses_before_contact(tmp_path: Path):
    """A1: no binding, no channel: the attempt is refused and recorded."""
    harness = build_harness(tmp_path)
    harness.receiver.bind_error = OSError("access denied")

    result = harness.run()

    assert harness.opened_channels == []
    assert harness.terminal.log == []
    assert result.envelope.admission[0].subject is AcceptanceSubject.PROCESS
    assert "receiver_binding_failed:OSError" in result.envelope.primary_failure
    assert harness.envelope_store.load(ATTEMPT).completed_at is not None


def test_lost_campaign_ownership_still_blocks_every_later_effect(tmp_path: Path):
    """A1: the claim is still checked first and still sticky."""
    harness = build_harness(tmp_path)
    lock = harness.coordinator.scope / LOCK_NAME

    def lose_claim(kind: str) -> None:
        if kind == "e6_apply" and lock.exists():
            lock.unlink()

    harness.terminal.on_dispatch = lose_claim

    result = harness.run()

    kinds = harness.product_dispatches()
    assert kinds[-1] == "e6_apply"
    assert "http_start" not in kinds
    assert result.envelope.primary_failure.startswith("authority_lost:campaign")


@pytest.mark.parametrize(
    ("observed", "finding"),
    [
        (paired_process(), None),
        (paired_process(mailbox_entries=("req_1.js",)), None),
        (paired_process(process_incarnation=REPLACEMENT), "process_instance:changed"),
        (paired_process(process_path=r"C:\other\PacketTracer.exe"), "changed"),
        (paired_process(product_version="", file_version=""), "changed"),
        (
            DiagnosticLifecycleObservation(error="packet_tracer_process_count:2"),
            "unobservable:packet_tracer_process_count:2",
        ),
    ],
)
def test_the_receiver_rule_is_the_continuity_rule_without_mailbox_traffic(
    observed, finding
):
    """A1: the per-dispatch rule is the existing lifecycle rule, plus the build."""
    found = receiver_continuity_findings("9.0.1.0858", paired_process(), observed)

    if finding is None:
        assert found == ()
    else:
        assert any(finding in item for item in found), found


def test_a_reading_without_the_granted_build_is_never_the_same_receiver():
    """A1: a reading that names no build does not borrow the preflight's."""
    preflight = paired_process(product_version="", file_version="")
    found = receiver_continuity_findings(
        "9.0.1.0858", preflight, paired_process(product_version="", file_version="")
    )

    assert "process_instance:build_not_observed" in found


# -- A2: durable reserved refusals ----------------------------------------------------


def _earlier_run() -> ServiceRunRecord:
    return ServiceRunRecord(
        run_id="earlier",
        created_at="2026-09-01T00:00:00Z",
        deployment_id=DEPLOYMENT_ID,
        status="verified",
    )


@pytest.mark.parametrize("refusal", ["process", "history", "manifest"])
def test_a_reserved_refusal_is_reloaded_with_its_identity_and_reason(
    tmp_path: Path, refusal: str
):
    """A2: a spent attempt keeps why it was refused, in the real store."""
    harness = build_harness(tmp_path)
    grant = None
    if refusal == "process":
        harness.lifecycle.observations = [paired_process(process_id=4243)]
    elif refusal == "history":
        harness.record_store.begin(_earlier_run())
    else:
        grant = harness.grant(manifest_hash="a" * 64)

    result = harness.run(**({"grant": grant} if grant else {}))

    assert result.persisted is True
    stored = harness.envelope_store.load(ATTEMPT)
    assert stored.attempt_id == ATTEMPT
    assert stored.completed_at is not None
    assert stored.campaign_outcome is CampaignOutcome.REFUSED
    assert stored.admission[0].subject is AcceptanceSubject(refusal)
    assert stored.primary_failure == result.envelope.primary_failure
    assert stored.reasons and stored.reasons == result.envelope.reasons
    begun = json.loads(
        harness.envelope_store.path_for(ATTEMPT).read_text(encoding="utf-8")
    )
    assert begun["completed_at"] is None
    assert harness.terminal.log == []


def test_an_unwritable_store_is_a_persistence_failure_not_a_refusal_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A2: a reason that could not be kept is reported as not kept."""
    harness = build_harness(tmp_path)

    def unwritable(envelope):
        raise RunRecordPersistenceError("read-only volume")

    monkeypatch.setattr(harness.envelope_store, "begin", unwritable)

    result = harness.run()

    assert result.persisted is False
    assert result.compact_summary()["envelope_persisted"] is False
    assert result.envelope.admission[0].subject is AcceptanceSubject.ENVELOPE
    assert "envelope_not_begun:RunRecordPersistenceError" in (
        result.envelope.persistence_failures
    )
    assert harness.terminal.log == []


def test_a_refusal_before_reservation_owes_no_envelope(tmp_path: Path):
    """A2: nothing was reserved, so nothing is written and nothing is missing."""
    harness = build_harness(tmp_path)

    result = harness.run(grant=harness.grant(channel="http"))

    assert result.persisted is None
    assert not harness.envelope_store.path_for(ATTEMPT).exists()


# -- A3: cancellation is a terminal path ----------------------------------------------


def _interrupt_at(harness, kind: str, occurrence: int = 1) -> None:
    seen = {"count": 0}

    def interrupt(dispatched: str) -> None:
        if dispatched == kind:
            seen["count"] += 1
            if seen["count"] == occurrence:
                raise KeyboardInterrupt

    harness.terminal.on_dispatch = interrupt


@pytest.mark.parametrize(
    ("boundary", "released", "expected_outcome"),
    [
        ("http_start", 1, "ownership_unknown"),
        ("http_inspect", 1, "released"),
        ("http_release", 1, "release_unanswered"),
    ],
)
def test_an_interruption_after_ownership_finalizes_once_and_propagates(
    tmp_path: Path, boundary: str, released: int, expected_outcome: str
):
    """A3: one release attempt at most, a terminal envelope, the exception kept."""
    harness = build_harness(tmp_path)
    _interrupt_at(harness, boundary)

    with pytest.raises(KeyboardInterrupt):
        harness.run()

    kinds = harness.product_dispatches()
    assert kinds.count("http_start") == 1
    assert kinds.count("http_release") == released
    assert kinds[-1] == "http_release"
    stored = harness.envelope_store.load(ATTEMPT)
    assert stored.completed_at is not None
    assert stored.http_accepted is False
    assert stored.campaign_outcome is CampaignOutcome.STOPPED
    assert stored.primary_failure.startswith("cancelled:KeyboardInterrupt@")
    assert stored.cancellation == stored.primary_failure
    assert stored.reasons[0] == stored.cancellation
    started = next(item for item in stored.clients if item.dispatches)
    assert started.release_outcome == expected_outcome
    untouched = [item for item in stored.clients if item is not started]
    assert all(item.dispatches == 0 for item in untouched)
    # The claim lock is released, the attempt identity stays spent.
    assert not (harness.coordinator.scope / LOCK_NAME).exists()
    assert stored.campaign["release"] == "released"
    assert stored.product.get("unreturned_records"), stored.product


def test_an_interruption_during_finalization_is_never_an_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A3: a verified product interrupted at the record reload is not accepted."""
    harness = build_harness(tmp_path)
    store = harness.record_store

    def interrupted(deployment_id, run_id):
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "load_evidence", interrupted)

    with pytest.raises(KeyboardInterrupt):
        harness.run()

    stored = harness.envelope_store.load(ATTEMPT)
    assert stored.completed_at is not None
    assert stored.product["status"] == "verified"
    assert stored.http_accepted is False
    assert stored.primary_failure == "cancelled:KeyboardInterrupt@finalization"
    assert harness.product_dispatches().count("http_release") == 2


def test_a_second_run_of_a_cancelled_attempt_is_still_refused(tmp_path: Path):
    """A3: cancellation never resets the permanent attempt reservation."""
    harness = build_harness(tmp_path)
    _interrupt_at(harness, "http_inspect")
    with pytest.raises(KeyboardInterrupt):
        harness.run()
    harness.terminal.on_dispatch = None
    dispatched = len(harness.terminal.log)

    second = harness.run()

    assert "campaign_attempt_already_reserved" in second.envelope.primary_failure
    assert len(harness.terminal.log) == dispatched


# -- A4: the deadline includes the evidence join ------------------------------------


def _slow_reload(harness, monkeypatch, seconds: float) -> None:
    store = harness.record_store
    original = store.load_evidence

    def slow(deployment_id, run_id):
        loaded = original(deployment_id, run_id)
        harness.clock.now += seconds
        return loaded

    monkeypatch.setattr(store, "load_evidence", slow)


def test_a_reload_that_crosses_the_deadline_withholds_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A4: a successful run whose evidence join ends late is not timely."""
    harness = build_harness(tmp_path)
    _slow_reload(harness, monkeypatch, 500.0)

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is False
    assert "acceptance_deadline_exceeded:record_reload" in envelope.reasons
    assert envelope.temporal["exceeded_at"] == "record_reload"
    assert envelope.temporal["publication_offset_seconds"] > 420
    assert envelope.budget.elapsed_seconds > 420
    # The late evidence is kept, and it is still what the verdict read.
    assert len(envelope.product["record_sha256"]) == 64
    assert all(item.accepted for item in envelope.clients)
    assert harness.envelope_store.load(ATTEMPT).http_accepted is False


def test_an_on_time_evidence_join_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A4 control: the same slow reload inside the deadline is accepted."""
    harness = build_harness(tmp_path)
    _slow_reload(harness, monkeypatch, 1.0)

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons
    assert envelope.temporal["exceeded_at"] == ""
    assert envelope.temporal["deadline_offset_seconds"] == 420.0
    assert result.completion_seconds >= 0.0


def test_a_verdict_reached_after_the_deadline_names_the_verdict_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A4: the judge's own time is inside the contract too."""
    harness = build_harness(tmp_path)
    original = accept_cold_http.evaluate_attempt

    def slow_judge(*args, **kwargs):
        verdict = original(*args, **kwargs)
        harness.clock.now += 500.0
        return verdict

    monkeypatch.setattr(accept_cold_http, "evaluate_attempt", slow_judge)

    result = harness.run()

    assert result.envelope.http_accepted is False
    assert result.envelope.temporal["exceeded_at"] == "verdict"
    assert result.envelope.clients and all(
        item.client in {PC1, PC2} for item in result.envelope.clients
    )


def test_the_legacy_worst_case_fits_with_receiver_and_dispatch_cost(tmp_path: Path):
    """A1 feasibility is not a zero-latency trace: every read and check costs time."""
    harness = build_harness(tmp_path)
    terminal = harness.terminal
    terminal.ios_ready_after = 90.0
    terminal.vlan_present_after = 5.0
    terminal.endpoint_ready_after = 30.0
    terminal.forwarding_after = 29.0
    terminal.page_visible_after = 8.0
    terminal.latency = lambda script: 0.05
    # The Win32 reading measured on the delivery machine: max 15 ms.
    harness.receiver.cost = 0.015

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons
    budget = envelope.budget
    assert budget.receiver_observations == budget.used_operations
    assert budget.receiver_observation_seconds == pytest.approx(
        0.015 * budget.used_operations, rel=1e-6
    )
    assert budget.elapsed_seconds <= 420
    assert envelope.temporal["publication_offset_seconds"] <= 420
