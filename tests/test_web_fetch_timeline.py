"""The instrumented owned-background-client lifecycle (unit level).

The product web reader is the one component that observes a fetch, and the
diagnostic needs everything it saw rather than only the reading it returned
on. These tests pin what it retains, what it refuses to coerce, and that the
default composition still behaves exactly as it did before the schedule, the
late read and the timeline existed.
"""

from __future__ import annotations

import json

import pytest

from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import ObservationFact
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)

MARKER = "AUDIT_MARKER"
PAGE = f"<html><body>{MARKER}</body></html>"
RELEASED = json.dumps({"found": True, "deleted": True, "present": False, "error": ""})


def _started(**overrides) -> str:
    payload = {
        "started": True,
        "go_result": True,
        "go_result_type": "boolean",
        "content_before": "",
        "https_mode": False,
        "https_mode_type": "boolean",
        "owner_device": "PC1",
        "owner_read": True,
        "owned": True,
    }
    payload.update(overrides)
    return json.dumps(payload)


def _page(content: str = PAGE) -> str:
    return json.dumps({"found": True, "content": content})


class _Clock:
    """A clock that only moves when the reader sleeps, plus a per-read cost."""

    def __init__(self, read_cost: float = 0.0) -> None:
        self.now = 0.0
        self.read_cost = read_cost
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _runtime(responses, *, clock=None, **kwargs):
    queue = list(responses)
    calls: list[str] = []
    clock = clock or _Clock()

    def send_and_wait(js, _timeout):
        calls.append(js)
        clock.now += clock.read_cost
        return queue.pop(0) if queue else None

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        send_and_wait,
        http_timeout_seconds=8.0,
        convergence_interval_seconds=8.0,
        clock=clock,
        sleeper=clock.sleep,
        **kwargs,
    )
    return runtime, calls, clock


def _expectation() -> ServiceVerificationExpectation:
    return ServiceVerificationExpectation(
        id="web-1",
        service_id="web",
        action_id="fixture",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="SRV",
        host_device_name="SRV",
        client_device_id="PC1",
        client_device_name="PC1",
        expected={"scheme": "http", "address": "192.0.2.10", "marker": MARKER},
        host_model="Server-PT",
        client_model="PC-PT",
    )


def test_the_default_composition_keeps_the_behaviour_it_always_had():
    """No schedule, no late read: the interval poll and its two inspections."""
    runtime, calls, _clock = _runtime([_started(), _page(), RELEASED])

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.OBSERVED
    assert len(calls) == 3
    assert [item.label for item in row.trace] == ["start", "inspect"]
    assert all(item.performed for item in row.trace)
    # Without a budget reader the record says so rather than reporting zeros.
    assert not any(item.budget_observed for item in row.trace)


def test_the_request_inputs_are_recorded_as_inputs():
    """No documented getter returns the URL, so it is never a read-back."""
    runtime, _calls, _clock = _runtime([_started(), _page(), RELEASED])

    row = runtime.verify(_expectation())

    assert row.observed["selected_url"] == "http://192.0.2.10/"
    assert row.observed["selected_path"] == "/"
    assert row.observed["selected_url_is_input"] is True
    assert row.observed["owner_device"] == "PC1"
    assert row.observed["client_mode"] == "http"
    assert row.observed["client_mode_type"] == "boolean"


@pytest.mark.parametrize(
    "go_type", ["number", "string", "object", "undefined", "function"]
)
def test_a_non_boolean_go_result_is_malformed_not_a_refusal(go_type):
    """`!!p.go(...)` turned `undefined` into "the client did not start"."""
    runtime, _calls, _clock = _runtime(
        [_started(started=False, go_result=None, go_result_type=go_type), RELEASED]
    )

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == f"go_result_not_boolean:{go_type}"
    assert row.observed["go_result_type"] == go_type


def test_an_absent_native_go_result_is_malformed_not_assumed_from_started():
    """The strict `started` projection cannot replace the native observation."""
    runtime, _calls, _clock = _runtime(
        [_started(go_result=None, go_result_type="absent"), RELEASED]
    )

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == "go_result_not_boolean:absent"


def test_a_boolean_go_type_requires_an_actual_consistent_boolean_value():
    """A type label alone cannot manufacture the native return value."""
    runtime, _calls, _clock = _runtime(
        [_started(go_result=None, go_result_type="boolean"), RELEASED]
    )

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == "go_result_value_not_boolean"


def test_an_actual_false_go_result_is_still_the_refusal_it_always_was():
    """The strict rule adds a case; it does not reinterpret the old one."""
    runtime, _calls, _clock = _runtime(
        [_started(started=False, go_result=False), RELEASED]
    )

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "client_go_false"
    assert row.observed["go_result"] is False


def test_a_guarded_getter_that_raised_is_an_engine_error_about_that_member():
    """A named refusal beats one undifferentiated wrapper exception."""
    runtime, _calls, _clock = _runtime(
        [_started(https_mode=None, https_mode_type="threw"), RELEASED]
    )

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.ENGINE_ERROR
    assert row.cause == "client_mode_reader_threw"


def test_http_mode_is_observed_and_must_match_the_selected_scheme():
    """Reading mode in HTTP is evidence only when it actually reports HTTP."""
    runtime, _calls, _clock = _runtime([_started(https_mode=True), RELEASED])

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.CONTRADICTED
    assert row.cause == "http_mode_not_confirmed"


def test_the_owned_client_must_be_attributed_to_the_selected_endpoint():
    """An owned but unattributed client is not this request's client."""
    runtime, _calls, _clock = _runtime(
        [_started(owner_device="", owner_read=False), RELEASED]
    )

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.NOT_OBSERVED
    assert row.cause == "client_owner_not_observed"


def test_a_different_observed_owner_is_a_contradiction():
    """A real owner name that differs from the selected PC is retained."""
    runtime, _calls, _clock = _runtime([_started(owner_device="OTHER"), RELEASED])

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.CONTRADICTED
    assert row.cause == "client_owner_mismatch:OTHER"


def test_the_explicit_schedule_records_a_missed_slot_instead_of_replaying_it():
    """A slot whose moment has passed is recorded, never fired late in a burst."""
    clock = _Clock(read_cost=4.0)
    runtime, calls, _clock = _runtime(
        [_started(), _page("nothing yet"), _page("still nothing"), RELEASED],
        clock=clock,
        web_inspection_schedule=(1.0, 3.0, 6.0),
        budget_reader=lambda: (12, 34.5),
    )

    row = runtime.verify(_expectation())

    labels = [(item.label, item.performed) for item in row.trace]
    assert ("inspect", False) in labels
    missed = [item for item in row.trace if not item.performed]
    assert missed and missed[0].outcome == "slot_missed"
    # A missed slot costs no dispatch: only the performed reads are calls.
    performed = [item for item in row.trace if item.performed]
    assert len(calls) == len(performed) + 1  # + the release
    assert all(item.budget_observed for item in row.trace)
    assert row.trace[0].remaining_operations == 12


def test_an_entirely_missed_schedule_dispatches_no_fallback_inspection():
    """Missed slots stay missed; no unscheduled read replaces the last one."""
    clock = _Clock(read_cost=10.0)
    runtime, calls, _clock = _runtime(
        [_started(), RELEASED],
        clock=clock,
        web_inspection_schedule=(1.0, 3.0, 6.0),
    )

    row = runtime.verify(_expectation())

    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "inspection_schedule_elapsed_without_read"
    assert [item.performed for item in row.trace] == [True, False, False, False]
    assert len(calls) == 2  # start plus owned release; no page inspection


def test_the_late_read_is_one_counted_read_that_starts_no_request():
    """It separates late content from content that never arrived."""
    clock = _Clock()
    runtime, calls, _clock = _runtime(
        # The scheduled read sees the page the request started with, so the
        # window closes with no response; the late read then finds the marker.
        [_started(), _page(""), _page(), RELEASED],
        clock=clock,
        web_inspection_schedule=(1.0,),
        web_late_read_offset=10.0,
    )

    row = runtime.verify(_expectation())

    late = [item for item in row.trace if item.label == "late_control"]
    assert len(late) == 1
    assert late[0].offset_seconds == 10.0
    assert late[0].marker_present is True
    # One `go` in the whole lifecycle, and the late read is not another one.
    assert len([item for item in calls if "p.go(" in item]) == 1
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "no_response_within_deadline"
    assert "late_content_observed_after_deadline" in row.limitations


def test_every_timeline_entry_survives_a_model_round_trip():
    """The record has to be able to store what the reader saw."""
    runtime, _calls, _clock = _runtime(
        [_started(), _page(), RELEASED],
        web_inspection_schedule=(1.0,),
        web_late_read_offset=2.0,
    )

    row = runtime.verify(_expectation())
    reloaded = type(row).model_validate_json(row.model_dump_json())

    assert [item.model_dump() for item in reloaded.trace] == [
        item.model_dump() for item in row.trace
    ]
