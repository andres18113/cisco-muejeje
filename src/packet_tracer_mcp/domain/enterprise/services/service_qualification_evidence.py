"""Decide what each Q0/Q1 observation supports, and nothing more.

The probes report typed readings; this module turns them into conclusions.
It is pure on purpose: the same rules must judge a LIVE run and an offline
simulation, and the tests that exercise them must be able to hand in any
reading, including ones a well-behaved engine would never produce.

Four distinctions run through every rule:

- a reading that was not observed is never a negative. A lost response, an
  engine error or a malformed payload decides nothing about the subject;
- an expected negative is established only by a fresh, completed observation
  that shows the negative, and only when a positive control shows the path can
  succeed at all;
- a contradiction of a candidate model is a stop signal, not a failure to be
  retried;
- a bounded sample supports its sample. No conclusion here generalizes to
  another channel, build, SHA or to universal behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models.execution import DispatchFact, ResultFact
from ..models.service_qualification import MeasurementConclusion
from ..models.service_runtime import ObservationFact, RuntimeServiceVerification

SUPPORTED = MeasurementConclusion.SUPPORTED_IN_SAMPLE
NEGATIVE = MeasurementConclusion.NEGATIVE_OBSERVED
CONTRADICTED = MeasurementConclusion.CONTRADICTED
INCONCLUSIVE = MeasurementConclusion.INCONCLUSIVE

#: The label every use of the extension's unregister call carries: the
#: maintained extension calls it (`main.js`), no Cisco page documents it, and
#: its return value has no documented meaning.
UNDOCUMENTED_UNREGISTER = (
    "undocumented_existing_usage:_ScriptModule.unregisterIpcEventByID"
)

#: What a declared negative control would need in order to *establish* the
#: listener-isolation model: an observation that this request was refused. The
#: production web reader has none. A refused request and a slow or lost one
#: both surface as `no_response_within_deadline`, and fresh non-marker content
#: proves a marker mismatch rather than a refusal. Until such an observable
#: exists, a negative control can only contradict the model, never support it,
#: and no HTTP code, `onDone` semantic or timeout may be invented to stand in
#: for one.
NO_QUALIFIED_NEGATIVE_OBSERVABLE = "no_qualified_listener_refusal_observable"


@dataclass(frozen=True)
class ProbeReading:
    """One correlated probe answer, or the reason there is none.

    `observed` is true only for a correlated JSON object whose shape the probe
    parser accepted. Everything else is carried as `cause`, and `payload` is
    then empty: a rule must not read fields from an answer it cannot trust.
    """

    step: str
    dispatch: DispatchFact
    result: ResultFact
    observed: bool
    payload: Mapping[str, Any] = field(default_factory=dict)
    cause: str = ""


@dataclass(frozen=True)
class QueueReceipt:
    """The channel's answer to one fire-and-forget dispatch."""

    step: str
    accepted: bool
    dispatch: DispatchFact


@dataclass
class Assessment:
    """A conclusion plus the facts, causes and limitations behind it."""

    conclusion: MeasurementConclusion
    facts: dict[str, Any] = field(default_factory=dict)
    causes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    outcome_unknown: bool = False


def _unobserved(reading: ProbeReading) -> str:
    return f"{reading.step}_unobserved:{reading.cause or reading.result.value}"


# -- M-ENG-1 -------------------------------------------------------------------


def assess_bag_persistence(
    write: ProbeReading, read: ProbeReading | None, *, channel: str
) -> Assessment:
    """Judge whether a run-owned value survived to a separate evaluation."""
    facts: dict[str, Any] = {"channel": channel}
    if write.observed:
        facts["receiver_is_global_at_write"] = write.payload["receiver_is_global"]
        facts["run_key_written"] = write.payload["written"]
        facts["run_key_owned"] = write.payload["owned"]
        if write.payload["run_bag_preexisting"]:
            # The claim proved the key already existed and reported that it
            # wrote nothing, so this refusal has nothing to undo. The outcome
            # is unknown only if the probe contradicts itself by claiming both.
            return Assessment(
                CONTRADICTED,
                facts,
                [
                    "run_key_collision: the run bag existed before this run "
                    "claimed it, and nothing was written"
                ],
                ["no_measurement_is_possible_under_a_foreign_run_key"],
                outcome_unknown=bool(write.payload["written"]),
            )
    if read is None or not read.observed:
        cause = _unobserved(read) if read is not None else "read_not_dispatched"
        return Assessment(
            INCONCLUSIVE,
            facts,
            [cause],
            ["sentinel_release_unresolved"],
            outcome_unknown=not write.observed,
        )
    facts["receiver_is_global_at_read"] = read.payload["receiver_is_global"]
    facts["owned_at_read"] = read.payload["owned"]
    facts["found"] = read.payload["found"]
    facts["nonce_matches"] = read.payload["nonce_matches"]
    facts["sentinel_released"] = read.payload["released"]
    limitations = [] if write.observed else ["write_acknowledgement_unobserved"]
    if read.payload["found"] and read.payload["nonce_matches"]:
        return Assessment(SUPPORTED, facts, [], limitations)
    if read.payload["found"]:
        return Assessment(
            CONTRADICTED,
            facts,
            ["foreign_value_under_run_key"],
            limitations,
            outcome_unknown=True,
        )
    if write.observed and write.payload["written"]:
        return Assessment(NEGATIVE, facts, ["value_absent_in_separate_evaluation"])
    return Assessment(
        INCONCLUSIVE,
        facts,
        ["absent_but_write_unobserved"],
        limitations,
        outcome_unknown=True,
    )


# -- ATOM-1 --------------------------------------------------------------------

_CONTENDERS = ("A", "B")
_TERMINAL = ("claimed", "refused")


def _log_entries(log: object) -> list[tuple[str, str, int]] | None:
    if not isinstance(log, list) or len(log) > 16:
        return None
    entries: list[tuple[str, str, int]] = []
    for item in log:
        if not isinstance(item, Mapping):
            return None
        contender, step, number = item.get("c"), item.get("s"), item.get("n")
        if (
            contender not in _CONTENDERS
            or step not in ("check", *_TERMINAL)
            or isinstance(number, bool)
            or not isinstance(number, int)
        ):
            return None
        entries.append((contender, step, number))
    numbers = [item[2] for item in entries]
    if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
        return None
    return entries


def assess_atomicity(
    contenders: Sequence[QueueReceipt], collect: ProbeReading | None, *, channel: str
) -> Assessment:
    """Search one queued pair's ordered log for an interleaving counterexample."""
    limitations = [
        "bounded_sample:one_pair",
        "not_universal_atomicity",
        "not_cross_channel_mutual_exclusion",
        "not_exactly_once_delivery",
    ]
    if channel == "http":
        limitations.append("http_channel_may_join_queued_commands_into_one_batch")
    facts: dict[str, Any] = {
        "channel": channel,
        "evaluation_scope": (
            "separate_evaluations" if channel == "file" else "unknown"
        ),
        "queued": {item.step: item.accepted for item in contenders},
    }
    if not all(item.accepted for item in contenders):
        return Assessment(
            INCONCLUSIVE,
            facts,
            ["contender_acceptance_unknown"],
            limitations,
            outcome_unknown=True,
        )
    if collect is None or not collect.observed:
        cause = _unobserved(collect) if collect is not None else "collect_not_run"
        return Assessment(INCONCLUSIVE, facts, [cause], limitations, True)
    if not collect.payload["present"]:
        return Assessment(
            INCONCLUSIVE, facts, ["no_contender_observed"], limitations, True
        )
    entries = _log_entries(collect.payload["log"])
    if entries is None:
        return Assessment(
            INCONCLUSIVE, facts, ["malformed_contender_log"], limitations, True
        )
    facts["log"] = [{"c": c, "s": s, "n": n} for c, s, n in entries]
    facts["released"] = collect.payload["released"]
    positions: dict[str, dict[str, int]] = {name: {} for name in _CONTENDERS}
    for index, (contender, step, _number) in enumerate(entries):
        kind = "terminal" if step in _TERMINAL else "check"
        if kind in positions[contender]:
            return Assessment(
                INCONCLUSIVE, facts, ["repeated_contender_step"], limitations, True
            )
        positions[contender][kind] = index
    if any(len(steps) != 2 for steps in positions.values()):
        return Assessment(
            INCONCLUSIVE, facts, ["contender_incomplete"], limitations, True
        )
    claimed = [c for c, s, _n in entries if s == "claimed"]
    if len(claimed) > 1:
        return Assessment(CONTRADICTED, facts, ["double_claim"], limitations)
    for contender in _CONTENDERS:
        start, end = positions[contender]["check"], positions[contender]["terminal"]
        if start > end or any(
            entries[index][0] != contender for index in range(start + 1, end)
        ):
            return Assessment(
                CONTRADICTED,
                facts,
                [f"interleaving_within_contender_{contender}"],
                limitations,
            )
    if len(claimed) != 1:
        return Assessment(INCONCLUSIVE, facts, ["no_claim_recorded"], limitations)
    if channel != "file":
        return Assessment(
            INCONCLUSIVE,
            facts,
            ["separate_evaluations_not_observed"],
            limitations,
        )
    return Assessment(SUPPORTED, facts, [], limitations)


# -- M-UNREG-1 / M-UNREG-2 -------------------------------------------------------


def _count(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def assess_observer_release(
    register: ProbeReading,
    evidence: ProbeReading | None,
    release: ProbeReading | None,
    after: ProbeReading | None,
) -> tuple[Assessment, Assessment]:
    """Judge event delivery, identity release and the zero-event fallback.

    The control observer cb3 is what gives the post-release reading meaning:
    without an invocation of the never-released control after trigger Y there
    is no evidence that Y produced an event at all, so neither an absent cb1
    invocation nor an absent cb2 invocation proves anything.
    """
    first: dict[str, Any] = {"release_call_label": UNDOCUMENTED_UNREGISTER}
    second: dict[str, Any] = {
        "safe_zero_event_release_established": False,
        "release_path": "inert_fallback",
        "unregister_attempted": False,
        "reason": "no source identity exists without an event; none is invented",
    }
    if not register.observed:
        cause = _unobserved(register)
        return (
            Assessment(INCONCLUSIVE, first, [cause], outcome_unknown=True),
            Assessment(INCONCLUSIVE, second, [cause], outcome_unknown=True),
        )
    first["registration"] = {
        "device_found": register.payload["found"],
        "acknowledged": register.payload["registered1"],
        "error": register.payload["register1_error"],
    }
    if not register.payload["found"] or not register.payload["registered1"]:
        cause = "registration_not_established"
        return (
            Assessment(INCONCLUSIVE, first, [cause]),
            Assessment(INCONCLUSIVE, second, [cause]),
        )
    if evidence is None or not evidence.observed:
        cause = _unobserved(evidence) if evidence else "evidence_not_read"
        return (
            Assessment(INCONCLUSIVE, first, [cause], outcome_unknown=True),
            Assessment(INCONCLUSIVE, second, [cause], outcome_unknown=True),
        )
    # The event name comes from the probe's own report of what it registered,
    # so the rule never assumes which vendor event the probe chose.
    event = str(register.payload["event"])
    first["event"] = second["event"] = event
    trigger_x = _count(register.payload, "trigger_x")
    events = [
        item
        for item in evidence.payload["cb1_events"]
        if isinstance(item, Mapping)
        and item.get("eventName") == event
        and _count(item, "seq") > trigger_x
    ]
    delivered = bool(events)
    first["callback_evidence"] = {
        "delivered": delivered,
        "events_after_trigger": len(events),
        "source": (
            {
                "className": str(events[0].get("className", ""))[:64],
                "objectUuid": str(events[0].get("uuid", ""))[:64],
                "eventName": event,
                "arg_keys": list(events[0].get("arg_keys", []))[:8],
            }
            if delivered
            else {}
        ),
    }
    second["cb2_registered"] = evidence.payload["registered2"]
    if release is None or not release.observed:
        cause = _unobserved(release) if release else "release_not_run"
        return (
            Assessment(INCONCLUSIVE, first, [cause], outcome_unknown=True),
            Assessment(INCONCLUSIVE, second, [cause], outcome_unknown=True),
        )
    attempt = release.payload["release1"]
    first["release_attempt"] = dict(attempt)
    precondition = (
        evidence.payload["registered2"]
        and _count(release.payload, "cb2_calls_before_inert") == 0
    )
    second["zero_event_precondition"] = precondition
    if after is None or not after.observed:
        cause = _unobserved(after) if after else "post_release_not_read"
        return (
            Assessment(INCONCLUSIVE, first, [cause], outcome_unknown=True),
            Assessment(INCONCLUSIVE, second, [cause], outcome_unknown=True),
        )
    control = _count(after.payload, "cb3_calls") - _count(
        release.payload, "cb3_calls_before_y"
    )
    cb1_after = _count(after.payload, "cb1_calls") - _count(
        release.payload, "cb1_calls_before_y"
    )
    cb2_after = _count(after.payload, "cb2_calls") - _count(
        release.payload, "cb2_calls_before_y"
    )
    control_seen = release.payload["registered3"] and control > 0
    first["post_release"] = {
        "cb1_invocations_after_release": cb1_after,
        "control_invocations_after_trigger": control,
    }
    second["post_release"] = {
        "cb2_invocations_after_inert": cb2_after,
        "cb2_events_recorded_after_inert": _count(
            after.payload, "cb2_events_after_inert"
        ),
        "control_invocations_after_trigger": control,
    }
    results = (
        _first_conclusion(first, delivered, attempt, control_seen, cb1_after),
        _second_conclusion(second, precondition, control_seen, cb2_after, after),
    )
    # A setter that threw may explain an absent event; it is carried as a
    # cause and never turned into evidence either way.
    if register.payload["trigger_error"]:
        results[0].causes.append(
            "trigger_x_failed:" + register.payload["trigger_error"]
        )
    if release.payload["trigger_error"]:
        for item in results:
            item.causes.append("trigger_y_failed:" + release.payload["trigger_error"])
    return results


def _first_conclusion(
    facts: dict[str, Any],
    delivered: bool,
    attempt: Mapping[str, Any],
    control_seen: bool,
    cb1_after: int,
) -> Assessment:
    causes: list[str] = []
    if attempt.get("attempted") is True and not attempt.get("threw"):
        if not control_seen:
            release = INCONCLUSIVE
            causes.append("no_control_event_after_release")
        elif cb1_after > 0:
            release = CONTRADICTED
            causes.append("released_callback_invoked_again")
        else:
            release = SUPPORTED
    else:
        release = INCONCLUSIVE
        causes.append(
            "release_threw"
            if attempt.get("threw")
            else "release_not_attempted:"
            + ("unregister_unavailable" if delivered else "identity_unobserved")
        )
    facts["release_conclusion"] = release.value
    facts["delivery_conclusion"] = (SUPPORTED if delivered else INCONCLUSIVE).value
    if not delivered:
        causes.append("no_event_observed_after_trigger")
    limitations = [
        "one_source_object_one_event_kind",
        "release_proven_only_by_absence_after_a_control_event",
    ]
    if release is CONTRADICTED:
        return Assessment(CONTRADICTED, facts, causes, limitations)
    if delivered and release is SUPPORTED:
        return Assessment(SUPPORTED, facts, causes, limitations)
    return Assessment(INCONCLUSIVE, facts, causes, limitations)


def _second_conclusion(
    facts: dict[str, Any],
    precondition: bool,
    control_seen: bool,
    cb2_after: int,
    after: ProbeReading,
) -> Assessment:
    limitations = ["fallback_set_of_R-EVT-05_applies"]
    if not precondition:
        return Assessment(
            INCONCLUSIVE, facts, ["zero_event_precondition_violated"], limitations
        )
    if not control_seen:
        return Assessment(
            INCONCLUSIVE, facts, ["no_control_event_after_release"], limitations
        )
    if _count(after.payload, "cb2_events_after_inert") > 0:
        return Assessment(
            CONTRADICTED, facts, ["inert_observer_recorded_events"], limitations
        )
    if cb2_after > 0:
        return Assessment(SUPPORTED, facts, [], limitations)
    return Assessment(
        CONTRADICTED,
        facts,
        ["inert_observer_not_invoked_while_control_was"],
        limitations,
    )


# -- M-HTTPS-1 -----------------------------------------------------------------


#: What the page probes cannot establish, on every M-HTTPS-1 record.
_PAGE_LIMITATIONS = (
    "reference_equality_is_not_page_ownership",
    "existing_page_content_only",
)


def _page_cell(value: Any) -> dict[str, Any] | None:
    """Validate one bounded page read; `None` when it is not the typed shape."""
    if not isinstance(value, Mapping):
        return None
    spec = {"read": bool, "error": str, "content": str, "truncated": bool}
    for key, kind in spec.items():
        if not isinstance(value.get(key), kind):
            return None
    length = value.get("length")
    if isinstance(length, bool) or not isinstance(length, int):
        return None
    return {**{key: value[key] for key in spec}, "length": length}


def _page_cells(
    reading: ProbeReading, key: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    cells = reading.payload.get(key)
    if not isinstance(cells, Mapping):
        return None, None
    return _page_cell(cells.get("http")), _page_cell(cells.get("https"))


def _unreadable(
    step: str, cells: tuple[dict[str, Any] | None, dict[str, Any] | None]
) -> list[str]:
    """Name every cell of one step that is not a complete, untruncated read."""
    causes: list[str] = []
    for name, cell in zip(("http", "https"), cells, strict=True):
        if cell is None:
            causes.append(f"{step}_malformed:{name}")
        elif not cell["read"]:
            causes.append(f"{step}_unreadable:{name}:{cell['error'][:120]}")
        elif cell["truncated"]:
            causes.append(f"{step}_truncated:{name}")
    return causes


def page_read_admits_second_write(read: ProbeReading | None, http_marker: str) -> bool:
    """Whether the first write was independently seen and the next may run.

    The second write is admitted only after both handles were read completely
    and the HTTP handle shows its own marker; otherwise the procedure has
    nothing coherent to compare the second write with.
    """
    if read is None or not read.observed:
        return False
    cells = _page_cells(read, "cells")
    if _unreadable("read", cells):
        return False
    return http_marker in cells[0]["content"]


def page_write_established(write: ProbeReading | None) -> bool:
    """Whether one page write was observed to complete in its evaluation."""
    return bool(write is not None and write.observed and write.payload["written"])


def assess_page_tables(
    write_http: ProbeReading,
    read_http: ProbeReading | None,
    write_https: ProbeReading | None,
    read_https: ProbeReading | None,
    *,
    http_marker: str,
    https_marker: str,
) -> Assessment:
    """Distinguish one shared page table from two separate ones.

    The procedure writes a run marker to the existing `index.html` through
    `HttpServer`, reads the page independently through both handles, then does
    the same through `HttpsServer`. Each write is bracketed by a complete read
    of both handles in its own evaluation.

    Shared is supported only by coherent cross-visibility in both directions.
    Separate is supported only when both own writes are visible and the
    opposite handle is unchanged both times. A failed, empty or truncated
    read, an exception, a lost answer or a mixed result is INCONCLUSIVE:
    none of them is the absence of a table. Reference equality is recorded
    and decides nothing.
    """
    limitations = list(_PAGE_LIMITATIONS)
    if not write_http.observed:
        return Assessment(
            INCONCLUSIVE,
            {},
            [_unobserved(write_http)],
            limitations,
            outcome_unknown=True,
        )
    payload = write_http.payload
    facts: dict[str, Any] = {
        "page": "index.html",
        "http_process_found": payload["http_found"],
        "https_process_found": payload["https_found"],
        "object_identity_equal": payload["reference_equal"],
    }
    if not payload["http_found"] or not payload["https_found"]:
        return Assessment(INCONCLUSIVE, facts, ["process_absent"], limitations)
    baseline = _page_cells(write_http, "before")
    causes = _unreadable("baseline", baseline)
    causes += [
        f"baseline_page_empty:{name}"
        for name, cell in zip(("http", "https"), baseline, strict=True)
        if cell is not None and cell["read"] and cell["length"] == 0
    ]
    if causes:
        if payload["written"]:
            causes.append("written_without_a_readable_baseline")
        return Assessment(INCONCLUSIVE, facts, causes, limitations)
    if not payload["written"]:
        return Assessment(
            INCONCLUSIVE,
            facts,
            ["marker_write_failed:http", str(payload["write_error"])[:200]],
            limitations,
        )
    if read_http is None or not read_http.observed:
        cause = _unobserved(read_http) if read_http else "read_not_run:http"
        return Assessment(INCONCLUSIVE, facts, [cause], limitations)
    after_http = _page_cells(read_http, "cells")
    causes = _unreadable("read_after_http_write", after_http)
    if causes:
        return Assessment(INCONCLUSIVE, facts, causes, limitations)
    visibility: dict[str, bool] = {
        "http_write_visible_via_http": http_marker in after_http[0]["content"],
        "http_write_visible_via_https": http_marker in after_http[1]["content"],
        "https_unchanged_after_http_write": (
            after_http[1]["content"] == baseline[1]["content"]
        ),
    }
    facts["visibility"] = visibility
    if not visibility["http_write_visible_via_http"]:
        return Assessment(
            INCONCLUSIVE, facts, ["own_write_not_visible:http"], limitations
        )
    if write_https is None:
        return Assessment(INCONCLUSIVE, facts, ["write_not_run:https"], limitations)
    if not write_https.observed:
        return Assessment(
            INCONCLUSIVE,
            facts,
            [_unobserved(write_https)],
            limitations,
            outcome_unknown=True,
        )
    bracket = _page_cells(write_https, "before")
    causes = _unreadable("bracket", bracket)
    if causes:
        return Assessment(INCONCLUSIVE, facts, causes, limitations)
    if (bracket[0]["content"], bracket[1]["content"]) != (
        after_http[0]["content"],
        after_http[1]["content"],
    ):
        return Assessment(
            INCONCLUSIVE, facts, ["page_changed_between_steps"], limitations
        )
    if not write_https.payload["written"]:
        return Assessment(
            INCONCLUSIVE,
            facts,
            [
                "marker_write_failed:https",
                str(write_https.payload["write_error"])[:200],
            ],
            limitations,
        )
    if read_https is None or not read_https.observed:
        cause = _unobserved(read_https) if read_https else "read_not_run:https"
        return Assessment(INCONCLUSIVE, facts, [cause], limitations)
    after_https = _page_cells(read_https, "cells")
    causes = _unreadable("read_after_https_write", after_https)
    if causes:
        return Assessment(INCONCLUSIVE, facts, causes, limitations)
    visibility.update(
        {
            "https_write_visible_via_https": https_marker in after_https[1]["content"],
            "https_write_visible_via_http": https_marker in after_https[0]["content"],
            "http_unchanged_after_https_write": (
                after_https[0]["content"] == after_http[0]["content"]
            ),
        }
    )
    if not visibility["https_write_visible_via_https"]:
        return Assessment(
            INCONCLUSIVE, facts, ["own_write_not_visible:https"], limitations
        )
    if (
        visibility["http_write_visible_via_https"]
        and visibility["https_write_visible_via_http"]
    ):
        facts["page_table_model"] = "shared"
        return Assessment(SUPPORTED, facts, [], limitations)
    if (
        not visibility["http_write_visible_via_https"]
        and visibility["https_unchanged_after_http_write"]
        and not visibility["https_write_visible_via_http"]
        and visibility["http_unchanged_after_https_write"]
    ):
        facts["page_table_model"] = "separate"
        return Assessment(SUPPORTED, facts, [], limitations)
    return Assessment(INCONCLUSIVE, facts, ["mixed_visibility"], limitations)


# -- M-HTTPS-2 -----------------------------------------------------------------

#: Observations the repaired listener procedure names instead of inventing.
LISTENER_UNAVAILABLE_OBSERVATIONS = (
    "request_url_not_read_back:no_documented_http_client_url_getter",
    "http_client_mode_not_read_back:http_reader_does_not_call_isHttps",
    "switch_port_stp_state:no_documented_reader",
    "port_light_status:undocumented_enum",
)
_MODE_CONFIRMED_CAUSES = frozenset(
    {"no_response_within_deadline", "client_go_false", "marker_present_before_request"}
)


def fetch_outcome(row: RuntimeServiceVerification | None) -> str:
    """Name what one production fetch row established, and nothing beyond it.

    Only the production reader decides freshness and mode. A contradicted row
    with no cause is its "fresh content without the marker" exit: a completed
    read that returned other content. On a page this run marked, that
    contradicts the expectation; it is not, by itself, evidence that a
    disabled listener refused the request. The mode exit carries its own cause
    and establishes nothing about the listener either.
    """
    if row is None:
        return "not_run"
    if row.observation is ObservationFact.OBSERVED:
        return "marker_retrieved"
    if row.observation is ObservationFact.CONTRADICTED and not row.cause:
        return "fresh_without_marker"
    if row.observation is ObservationFact.CONTRADICTED:
        return f"mode_unconfirmed:{row.cause}"
    return f"unestablished:{row.observation.value}:{row.cause}"


def fetch_client_mode(row: RuntimeServiceVerification | None, scheme: str) -> str:
    """Name what the production reader established about the client's mode.

    The HTTPS start payload is validated in a fixed order -- client
    ownership, shape, `isHttps()` after `setHttps(true)`, then `go()` -- so a
    row that reached a later exit has had its mode confirmed. The HTTP reader
    does not read the mode at all, and its golden script is not changed to
    make it.
    """
    if scheme != "https":
        return "not_read_back"
    if row is None:
        return "not_run"
    if row.observation is ObservationFact.CONTRADICTED and row.cause:
        return "https_not_confirmed"
    past_mode_check = (
        row.observation is ObservationFact.OBSERVED
        or (row.observation is ObservationFact.CONTRADICTED and not row.cause)
        or (
            row.observation is ObservationFact.INCONCLUSIVE
            and row.cause in _MODE_CONFIRMED_CAUSES
        )
    )
    return "https_confirmed_by_isHttps" if past_mode_check else "unobserved"


def listener_toggle_established(
    reading: ProbeReading | None, *, http: bool, https: bool
) -> bool:
    """Return whether one toggle was read back, in its own evaluation, as asked.

    The coordinator calls this before admitting the effect that would follow a
    toggle: an unestablished setup is an effect whose outcome nobody observed,
    and it authorizes no further experimental mutation.
    """
    return bool(
        reading is not None
        and reading.observed
        and not reading.payload["error"]
        and reading.payload["http_enabled"] is http
        and reading.payload["https_enabled"] is https
    )


def marker_page_established(reading: ProbeReading | None) -> bool:
    """Whether the marked page was written and read back through both handles.

    Both listeners must still read back enabled, because the first fetch is
    the HTTP-mode positive control and needs the HTTP listener serving.
    """
    if not listener_toggle_established(reading, http=True, https=True):
        return False
    written = reading.payload["index_written"]
    readback = reading.payload["readback"]
    return all(
        isinstance(written.get(name), bool)
        and written[name]
        and isinstance(readback.get(name), Mapping)
        and readback[name].get("read") is True
        and readback[name].get("contains_marker") is True
        for name in ("http", "https")
    )


def _positive_control(
    outcome: str, *, setup_established: bool
) -> tuple[MeasurementConclusion, list[str]]:
    """Classify one declared positive control."""
    if not setup_established:
        return INCONCLUSIVE, ["listener_state_not_read_back"]
    if outcome == "marker_retrieved":
        return SUPPORTED, []
    if outcome == "fresh_without_marker":
        # A completed read of the page this run marked returned other
        # content. That contradicts this expectation whatever the listener is
        # doing, and it stops the stage.
        return CONTRADICTED, ["marked_page_returned_other_content"]
    return INCONCLUSIVE, [f"observed:{outcome}"]


def _negative_control(
    outcome: str, *, disabled_confirmed: bool, same_mode_positive: bool
) -> tuple[MeasurementConclusion, list[str]]:
    """Classify one declared negative control, and say what it could not settle.

    A retrieval contradicts the model when the listener was read back as
    disabled. Nothing here establishes the model: see
    `NO_QUALIFIED_NEGATIVE_OBSERVABLE`. A negative whose same-mode positive
    did not work was not run, and would have had no discriminating power.
    """
    if outcome == "not_run":
        causes = ["not_run"]
        if not same_mode_positive:
            causes.insert(0, "no_same_mode_positive_control")
        return INCONCLUSIVE, causes
    if not disabled_confirmed:
        return INCONCLUSIVE, ["listener_state_not_read_back"]
    if outcome == "marker_retrieved":
        return CONTRADICTED, ["listener_served_while_read_back_as_disabled"]
    causes = [f"observed:{outcome}", NO_QUALIFIED_NEGATIVE_OBSERVABLE]
    if not same_mode_positive:
        causes.insert(0, "no_same_mode_positive_control")
    return INCONCLUSIVE, causes


def _readiness_facts(reading: ProbeReading | None) -> dict[str, Any]:
    """Copy the typed readiness fields; name an unobserved reading."""
    if reading is None:
        return {"observed": False, "cause": "not_run"}
    if not reading.observed:
        return {"observed": False, "cause": _unobserved(reading)}
    listeners = reading.payload["listeners"]
    ports: dict[str, Any] = {}
    for name, value in sorted(reading.payload["ports"].items()):
        if not isinstance(value, Mapping):
            ports[str(name)[:80]] = {"malformed": True}
            continue
        ports[str(name)[:80]] = {
            key: value.get(key)
            for key in ("found", "port_up", "protocol_up", "linked", "ip", "mask")
            if isinstance(value.get(key), (bool, str)) or value.get(key) is None
        } | {"error": str(value.get("error") or "")[:120]}
    return {
        "observed": True,
        "listeners": {
            key: listeners.get(key)
            for key in ("http_enabled", "https_enabled", "https_process_enabled")
            if isinstance(listeners.get(key), bool) or listeners.get(key) is None
        },
        "ports": ports,
    }


def assess_https_listener(
    *,
    readiness: ProbeReading | None,
    marker_page: ProbeReading | None,
    http_positive: RuntimeServiceVerification | None,
    http_off: ProbeReading | None,
    https_positive: RuntimeServiceVerification | None,
    http_negative: RuntimeServiceVerification | None,
    https_off: ProbeReading | None,
    https_negative: RuntimeServiceVerification | None,
    request_urls: Mapping[str, str],
    readiness_after: ProbeReading | None = None,
) -> Assessment:
    """Judge both same-mode positives and both declared negative controls.

    The order is fixed by the coordinator: an HTTP-mode positive with both
    listeners enabled, then HTTP off and an HTTPS-mode positive, then the
    HTTP-mode negative, then HTTPS off and the HTTPS-mode negative. A negative
    is interpreted only against a working positive in its own mode.

    The model claims that a listener *fails* when it is disabled, and this
    reader has no observation that establishes a refusal, so SUPPORTED is
    unreachable here by construction. The measurement records every
    descriptive observation, contradicts the model when a marked positive
    page returned other content or a listener read back as disabled still
    served the marker, and is otherwise INCONCLUSIVE.
    """
    page_ready = marker_page_established(marker_page)
    https_only = listener_toggle_established(http_off, http=False, https=True)
    both_off = listener_toggle_established(https_off, http=False, https=False)
    outcomes = {
        "http_positive": fetch_outcome(http_positive),
        "https_positive": fetch_outcome(https_positive),
        "http_negative": fetch_outcome(http_negative),
        "https_negative": fetch_outcome(https_negative),
    }
    http_p, http_p_causes = _positive_control(
        outcomes["http_positive"], setup_established=page_ready
    )
    https_p, https_p_causes = _positive_control(
        outcomes["https_positive"], setup_established=page_ready and https_only
    )
    http_n, http_n_causes = _negative_control(
        outcomes["http_negative"],
        disabled_confirmed=https_only,
        same_mode_positive=http_p is SUPPORTED,
    )
    https_n, https_n_causes = _negative_control(
        outcomes["https_negative"],
        disabled_confirmed=both_off,
        same_mode_positive=https_p is SUPPORTED,
    )

    def fetch(name: str, scheme: str, row, conclusion, **extra) -> dict[str, Any]:
        return {
            **extra,
            "fetch": outcomes[name],
            "request_url": request_urls.get(scheme, ""),
            "client_mode": fetch_client_mode(row, scheme),
            "conclusion": conclusion.value,
        }

    facts: dict[str, Any] = {
        "readiness_before": _readiness_facts(readiness),
        "marker_page": (
            {
                "established": page_ready,
                "index_written": dict(marker_page.payload["index_written"]),
                "readback": {
                    name: {
                        key: value
                        for key, value in dict(
                            marker_page.payload["readback"].get(name) or {}
                        ).items()
                        if key in ("read", "contains_marker", "length", "error")
                    }
                    for name in ("http", "https")
                },
            }
            if marker_page is not None and marker_page.observed
            else {"established": False}
        ),
        "positive_http_mode_both_enabled": fetch(
            "http_positive", "http", http_positive, http_p, setup_established=page_ready
        ),
        "positive_https_only": fetch(
            "https_positive",
            "https",
            https_positive,
            https_p,
            setup_established=page_ready and https_only,
        ),
        "negative_http_mode_http_disabled": fetch(
            "http_negative",
            "http",
            http_negative,
            http_n,
            same_mode_positive_control=http_p is SUPPORTED,
        ),
        "negative_https_mode_https_disabled": fetch(
            "https_negative",
            "https",
            https_negative,
            https_n,
            setup_established=both_off,
            same_mode_positive_control=https_p is SUPPORTED,
        ),
        "unavailable_observations": list(LISTENER_UNAVAILABLE_OBSERVATIONS),
    }
    if readiness_after is not None:
        facts["readiness_after_failed_positive"] = _readiness_facts(readiness_after)
    limitations = [
        "fresh_content_not_retained",
        NO_QUALIFIED_NEGATIVE_OBSERVABLE,
        "request_url_not_read_back",
    ]
    causes = (
        [f"positive_http:{item}" for item in http_p_causes]
        + [f"positive_https:{item}" for item in https_p_causes]
        + [f"negative_http:{item}" for item in http_n_causes]
        + [f"negative_https:{item}" for item in https_n_causes]
    )
    # A setup that was dispatched and never read back is an effect with an
    # unknown outcome, which the coordinator must treat as a stop signal.
    unknown_setup = [
        name
        for name, reading in (
            ("marker_page", marker_page),
            ("http_off", http_off),
            ("https_off", https_off),
        )
        if reading is not None and not reading.observed
    ]
    causes += [f"setup_unobserved:{name}" for name in unknown_setup]
    conclusion = (
        CONTRADICTED
        if CONTRADICTED in (http_p, https_p, http_n, https_n)
        else INCONCLUSIVE
    )
    return Assessment(
        conclusion, facts, causes, limitations, outcome_unknown=bool(unknown_setup)
    )


# -- M-DNS-3 -------------------------------------------------------------------


def _client_reading(clients: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = clients.get(name)
    if not isinstance(value, Mapping):
        return {"found": False, "value": None, "error": "not_reported"}
    return {
        "found": value.get("found") is True,
        "value": value.get("value") if isinstance(value.get("value"), str) else None,
        "error": str(value.get("error") or "")[:200],
    }


def assess_client_resolver(
    read: ProbeReading | None,
    *,
    configured_client: str,
    unset_client: str,
    intended: str,
    e5_dispatch_accepted: bool,
) -> Assessment:
    """Compare the configured PC's resolver with its intended address.

    The unset client's raw value is recorded as the measured representation of
    "no resolver"; nothing is concluded from it beyond that.
    """
    if read is None or not read.observed:
        cause = _unobserved(read) if read else "read_not_run"
        return Assessment(INCONCLUSIVE, {}, [cause])
    configured = _client_reading(read.payload["clients"], configured_client)
    unset = _client_reading(read.payload["clients"], unset_client)
    facts: dict[str, Any] = {
        "intended_resolver": intended,
        "configured_client": {"name": configured_client, **configured},
        "unset_client_representation": {"name": unset_client, **unset},
        "e5_dispatch_accepted": e5_dispatch_accepted,
    }
    value = configured["value"]
    if not configured["found"] or configured["error"]:
        return Assessment(INCONCLUSIVE, facts, ["configured_client_not_read"])
    if value == intended:
        return Assessment(SUPPORTED, facts, [], ["one_client_one_value"])
    if isinstance(value, str) and value and e5_dispatch_accepted:
        return Assessment(CONTRADICTED, facts, ["resolver_differs_from_e5_intent"])
    return Assessment(INCONCLUSIVE, facts, ["resolver_not_attributable_to_e5"])
