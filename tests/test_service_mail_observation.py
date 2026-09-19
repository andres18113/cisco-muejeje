"""What one mailbox scan must be before it may support a presence claim.

The reader's subject is the bounded scan its own generated script performs: it
walks the recipient's mailbox newest first, stops at `MAILBOX_SCAN_LIMIT`, and
reports five counters and two flags. Those numbers are not independent. A
payload whose counters cannot have come from that scan is not a mailbox that
held nothing; it is an answer the reader cannot use, and it establishes
neither presence nor absence.

The channel here returns exactly the payload each case names, so the rules are
exercised on inputs a well-behaved engine would never produce. The relations
are derived from the scanner in `_verify_smtp_delivered`, never from a new
assumption about Packet Tracer: no case below claims anything about how a
`Mail` field is spelled or typed, which stays unqualified until Q2 measures it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from test_service_mail_script_harness import _delivered

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import ObservationFact
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    MAILBOX_SCAN_LIMIT,
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

#: The counters a scan of an empty, present mailbox reports.
_EMPTY: dict[str, Any] = {
    "found_user": True,
    "count": 0,
    "scanned": 0,
    "matches": 0,
    "mismatched": 0,
    "truncated": False,
}


def _scan(**fields: Any) -> dict[str, Any]:
    """Return one scan payload with the named counters overridden."""
    return {**_EMPTY, **fields}


class _Clock:
    """A monotonic clock that advances only when the reader sleeps."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance instead of waiting."""
        self.now += seconds


class _Answers:
    """A channel that answers every command with one prepared body."""

    def __init__(self, payload: Any) -> None:
        """Bind the payload this channel reports as a correlated result."""
        self.payload = payload
        self.scripts: list[str] = []

    def dispatch_and_wait(self, script: str, _timeout: float):
        """Return the prepared payload as a correlated answer."""
        self.scripts.append(script)
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=json.dumps(self.payload),
        )


def _read(payload: Any, *, timeout: float = 0.0):
    """Run the real reader over one prepared scan answer."""
    channel = _Answers(payload)
    clock = _Clock()
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda script, timeout_seconds: None,
        dispatch_and_wait=channel.dispatch_and_wait,
        mail_timeout_seconds=timeout,
        convergence_interval_seconds=0.5,
        clock=clock,
        sleeper=clock.sleep,
    )
    return runtime.verify(_delivered()), channel


#: Every payload whose counters contradict the scan that produced them, with
#: the relation it breaks. None of them is a mailbox with no message in it.
_INCOHERENT = [
    pytest.param(_scan(matches=1), "match_total_exceeds_scanned", id="match_unscanned"),
    pytest.param(_scan(count=-1), "negative_counter", id="negative_count"),
    pytest.param(
        _scan(count=1, scanned=1, matches=-1), "negative_counter", id="negative_matches"
    ),
    pytest.param(
        _scan(count=MAILBOX_SCAN_LIMIT + 1, scanned=MAILBOX_SCAN_LIMIT + 1),
        "scan_exceeds_bound",
        id="over_the_bound",
    ),
    pytest.param(
        _scan(count=1, scanned=2, truncated=False),
        "scan_not_the_bounded_walk",
        id="scanned_over_count",
    ),
    pytest.param(
        _scan(count=5, scanned=5, truncated=True),
        "truncation_contradicts_counts",
        id="truncation_without_a_remainder",
    ),
    pytest.param(
        _scan(
            count=MAILBOX_SCAN_LIMIT + 5,
            scanned=MAILBOX_SCAN_LIMIT,
            truncated=False,
        ),
        "truncation_contradicts_counts",
        id="remainder_without_truncation",
    ),
    pytest.param(
        _scan(found_user=False, count=3, scanned=3),
        "absent_subject_carries_counters",
        id="absent_user_with_counters",
    ),
    pytest.param(
        _scan(count=2, scanned=2, matches=1, mismatched=2),
        "match_total_exceeds_scanned",
        id="more_outcomes_than_messages",
    ),
]


@pytest.mark.parametrize(("payload", "relation"), _INCOHERENT)
def test_an_incoherent_scan_establishes_neither_presence_nor_absence(payload, relation):
    """S2-06.1: the counters are checked against the scan, not just typed."""
    row, _ = _read(payload)

    assert row.observation is ObservationFact.MALFORMED
    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.cause == f"mailbox_scan_incoherent:{relation}"
    assert row.claim_level == "server_mailbox_presence"
    assert "supporting_evidence_only" not in row.limitations


def test_a_payload_missing_a_field_stays_a_typed_shape_refusal():
    """A missing key is not a zero, and it is not an incoherence either."""
    payload = _scan()
    del payload["matches"]

    row, _ = _read(payload)

    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == "typed_shape_missing"


def test_a_match_inside_a_truncated_scan_is_still_presence():
    """Truncation bounds what absence can mean, never what presence means."""
    row, _ = _read(
        _scan(
            count=MAILBOX_SCAN_LIMIT + 5,
            scanned=MAILBOX_SCAN_LIMIT,
            matches=1,
            truncated=True,
        )
    )

    assert row.observation is ObservationFact.OBSERVED
    assert row.status is ActionExecutionStatus.PARTIAL
    assert "supporting_evidence_only" in row.limitations
    assert "not_pop3_retrieval_evidence" in row.limitations


def test_a_coherent_scan_without_the_nonce_stays_unknown():
    """A complete scan that found nothing is unknown, never a failure."""
    row, _ = _read(_scan(count=3, scanned=3))

    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.cause == "message_not_observed_within_deadline"
    assert row.observed == {"scanned": 3, "matches": 0, "truncated": False}


def test_an_incoherent_scan_never_settles_the_poll():
    """An unusable answer does not end the wait the way a real one does."""
    settling, coherent = _read(_scan(found_user=False), timeout=2.0)
    row, channel = _read(_scan(found_user=False, count=3, scanned=3), timeout=2.0)

    # A subject that is genuinely absent settles the poll at once. The same
    # flag carried by counters the scan cannot have produced must not, or an
    # inadmissible answer would end the wait as if it had been an answer.
    assert settling.observation is ObservationFact.SUBJECT_NOT_FOUND
    assert len(coherent.scripts) == 1
    assert len(channel.scripts) > 1
    assert row.observation is ObservationFact.MALFORMED
