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
from ..models.forwarding import AccessForwardingObservation
from ..models.service_qualification import (
    Q3_OBSERVED_NATIVE_DEFAULT_POOL,
    MeasurementConclusion,
)
from ..models.service_runtime import ObservationFact, RuntimeServiceVerification
from .access_forwarding import (
    access_forwarding_admission,
    access_forwarding_facts,
    interpret_port_light,
)

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

#: What this procedure established about its OWN effect on the page, which is
#: a different question from what it established about the table model.
#:
#: NOT_ATTEMPTED means the probe's guard stopped before `setPageContents`.
#: RECONCILED means a setter ran and both handles were then read completely,
#: so the page is known. UNRESOLVED means a setter may have run and the page
#: was not read after it: the setter can change `index.html` and then throw,
#: and a caught exception is no more an observation of the final page than a
#: return value is. Only UNRESOLVED stops the rest of the stage; an
#: inconclusive table model is a conclusion about the subject, not a loose
#: effect.
_EFFECT_NOT_ATTEMPTED = "not_attempted"
_EFFECT_RECONCILED = "reconciled"
_EFFECT_UNRESOLVED = "unresolved"


def _page_assessment(
    conclusion: MeasurementConclusion,
    facts: dict[str, Any],
    causes: list[str],
    limitations: list[str],
    effect: str,
) -> Assessment:
    """Record one page-procedure outcome together with its own effect state."""
    return Assessment(
        conclusion,
        {**facts, "page_effect": effect},
        causes,
        limitations,
        outcome_unknown=effect == _EFFECT_UNRESOLVED,
    )


def _write_blocked(step: str, cells) -> list[str]:
    """Name every reading that proves the probe stopped before its setter.

    `write_index_marker` calls `setPageContents` only when both handles read
    the page completely, non-empty and untruncated in that same evaluation.
    So an empty list here means the setter was reached, whatever the reported
    `written` flag says afterwards.
    """
    return _unreadable(step, cells) + [
        f"{step}_page_empty:{name}"
        for name, cell in zip(("http", "https"), cells, strict=True)
        if cell is not None and cell["read"] and cell["length"] == 0
    ]


def _page_effect_unresolved(write: ProbeReading, blocked: Sequence[str]) -> bool:
    """Whether one write may have changed the page without being read after.

    A reported write, a caught setter exception and a reached setter all mean
    the page may differ now. Only the probe's own guard, which `blocked`
    reports, excludes the effect.
    """
    payload = write.payload
    return bool(payload["written"] or payload["write_error"] or not blocked)


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

    Every exit also states what happened to this procedure's own effect, as
    `page_effect`. That is a separate question from the table model, and only
    `unresolved` -- a setter that may have run with no complete read after it
    -- sets `outcome_unknown` and ends the experimental phase. Deciding
    nothing about shared versus separate is not, by itself, a reason to stop.
    """
    limitations = list(_PAGE_LIMITATIONS)
    if not write_http.observed:
        # A lost answer says nothing about the setter: it may have run.
        return _page_assessment(
            INCONCLUSIVE,
            {},
            [_unobserved(write_http)],
            limitations,
            _EFFECT_UNRESOLVED,
        )
    payload = write_http.payload
    facts: dict[str, Any] = {
        "page": "index.html",
        "http_process_found": payload["http_found"],
        "https_process_found": payload["https_found"],
        "object_identity_equal": payload["reference_equal"],
    }
    if not payload["http_found"] or not payload["https_found"]:
        return _page_assessment(
            INCONCLUSIVE, facts, ["process_absent"], limitations, _EFFECT_NOT_ATTEMPTED
        )
    baseline = _page_cells(write_http, "before")
    causes = _write_blocked("baseline", baseline)
    if causes:
        # The guard stopped before the setter, so nothing was attributed to a
        # write here -- unless the payload contradicts itself by reporting one.
        unresolved = _page_effect_unresolved(write_http, causes)
        if payload["written"]:
            causes.append("written_without_a_readable_baseline")
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            causes,
            limitations,
            _EFFECT_UNRESOLVED if unresolved else _EFFECT_NOT_ATTEMPTED,
        )
    # Past the guard the setter was reached, so from here every exit before a
    # complete read of both handles leaves this write unresolved.
    if not payload["written"]:
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            ["marker_write_failed:http", str(payload["write_error"])[:200]],
            limitations,
            _EFFECT_UNRESOLVED,
        )
    if read_http is None or not read_http.observed:
        cause = _unobserved(read_http) if read_http else "read_not_run:http"
        return _page_assessment(
            INCONCLUSIVE, facts, [cause], limitations, _EFFECT_UNRESOLVED
        )
    after_http = _page_cells(read_http, "cells")
    causes = _unreadable("read_after_http_write", after_http)
    if causes:
        return _page_assessment(
            INCONCLUSIVE, facts, causes, limitations, _EFFECT_UNRESOLVED
        )
    # Both handles were read completely after the write: the page is known.
    visibility: dict[str, bool] = {
        "http_write_visible_via_http": http_marker in after_http[0]["content"],
        "http_write_visible_via_https": http_marker in after_http[1]["content"],
        "https_unchanged_after_http_write": (
            after_http[1]["content"] == baseline[1]["content"]
        ),
    }
    facts["visibility"] = visibility
    if not visibility["http_write_visible_via_http"]:
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            ["own_write_not_visible:http"],
            limitations,
            _EFFECT_RECONCILED,
        )
    if write_https is None:
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            ["write_not_run:https"],
            limitations,
            _EFFECT_RECONCILED,
        )
    if not write_https.observed:
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            [_unobserved(write_https)],
            limitations,
            _EFFECT_UNRESOLVED,
        )
    bracket = _page_cells(write_https, "before")
    causes = _write_blocked("bracket", bracket)
    if causes:
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            causes,
            limitations,
            _EFFECT_UNRESOLVED
            if _page_effect_unresolved(write_https, causes)
            else _EFFECT_RECONCILED,
        )
    # The second setter was reached too, so the same rule applies to it.
    if (bracket[0]["content"], bracket[1]["content"]) != (
        after_http[0]["content"],
        after_http[1]["content"],
    ):
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            ["page_changed_between_steps"],
            limitations,
            _EFFECT_UNRESOLVED,
        )
    if not write_https.payload["written"]:
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            [
                "marker_write_failed:https",
                str(write_https.payload["write_error"])[:200],
            ],
            limitations,
            _EFFECT_UNRESOLVED,
        )
    if read_https is None or not read_https.observed:
        cause = _unobserved(read_https) if read_https else "read_not_run:https"
        return _page_assessment(
            INCONCLUSIVE, facts, [cause], limitations, _EFFECT_UNRESOLVED
        )
    after_https = _page_cells(read_https, "cells")
    causes = _unreadable("read_after_https_write", after_https)
    if causes:
        return _page_assessment(
            INCONCLUSIVE, facts, causes, limitations, _EFFECT_UNRESOLVED
        )
    visibility.update(
        {
            "https_write_visible_via_https": https_marker in after_https[1]["content"],
            "https_write_visible_via_http": https_marker in after_https[0]["content"],
            "http_unchanged_after_https_write": (
                after_https[0]["content"] == after_http[0]["content"]
            ),
        }
    )
    # Both writes are reconciled from here: each was followed by a complete
    # read of both handles, so the page is known whatever the model is.
    if not visibility["https_write_visible_via_https"]:
        return _page_assessment(
            INCONCLUSIVE,
            facts,
            ["own_write_not_visible:https"],
            limitations,
            _EFFECT_RECONCILED,
        )
    if (
        visibility["http_write_visible_via_https"]
        and visibility["https_write_visible_via_http"]
    ):
        facts["page_table_model"] = "shared"
        return _page_assessment(SUPPORTED, facts, [], limitations, _EFFECT_RECONCILED)
    if (
        not visibility["http_write_visible_via_https"]
        and visibility["https_unchanged_after_http_write"]
        and not visibility["https_write_visible_via_http"]
        and visibility["http_unchanged_after_https_write"]
    ):
        facts["page_table_model"] = "separate"
        return _page_assessment(SUPPORTED, facts, [], limitations, _EFFECT_RECONCILED)
    return _page_assessment(
        INCONCLUSIVE, facts, ["mixed_visibility"], limitations, _EFFECT_RECONCILED
    )


# -- M-HTTPS-2 -----------------------------------------------------------------

#: Observations the repaired listener procedure names instead of inventing.
#:
#: Three entries were removed because they were false. Both client starts now
#: read `isHttps()`. A usable registered STP observation exists through
#: `OperationalQueryId.SHOW_SPANNING_TREE` with the maintained parser, and
#: `Port::getLightStatus()` has a documented enumeration. The latter two are
#: not read by *this* procedure, which is a scope statement, not an absence:
#: what Q1 does not observe here is named below, and what the diagnostic stage
#: observes lives in its own record.
LISTENER_UNAVAILABLE_OBSERVATIONS = (
    "request_url_not_read_back:no_documented_http_client_url_getter",
    "switch_port_stp_state:not_read_by_this_procedure",
    "port_light_status:not_read_by_this_procedure",
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

    Both start paths now validate in one order -- client ownership, the native
    `isHttps()` value, then `go()` and its native return. The observed mode is
    carried on every later exit, so this rule reads that fact directly rather
    than inferring a mode from how far the reader happened to get.
    """
    if row is None:
        return "not_run"
    observed = str(row.observed.get("client_mode") or "")
    if observed == scheme:
        return f"{scheme}_confirmed_by_isHttps"
    if observed in ("http", "https") or row.cause == f"{scheme}_mode_not_confirmed":
        return f"{scheme}_not_confirmed"
    return "unobserved"


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


#: Everything one readiness row carries. The `*_type` companions exist so that
#: a missing reader, a non-boolean return and an actual `false` stay three
#: different observations in the record instead of collapsing into one.
READINESS_PORT_KEYS = (
    "device",
    "interface",
    "found",
    "linked",
    "link_type",
    "port_up",
    "port_up_type",
    "protocol_up",
    "protocol_up_type",
    "light_status",
    "light_status_type",
    "ip",
    "mask",
)

#: The listener fields one readiness reading carries. The port numbers come
#: from `getPortNumber()`; their `*_type` companions keep an absent reader
#: apart from a number the engine actually returned.
READINESS_LISTENER_KEYS = (
    "http_enabled",
    "https_enabled",
    "https_process_enabled",
    "http_port_number",
    "http_port_number_type",
    "https_port_number",
    "https_port_number_type",
)

#: The fields a network attempt needs to be true before it may start. The link
#: light is deliberately absent: it is auxiliary evidence, and requiring or
#: accepting it here would turn a lamp into a forwarding permission.
READINESS_REQUIRED_BOOLEANS = ("found", "linked", "port_up", "protocol_up")


def _readiness_value(value: Any) -> bool:
    """Whether one readiness field may be copied into the record as itself."""
    return isinstance(value, (bool, str, int)) or value is None


def _readiness_facts(reading: ProbeReading | None) -> dict[str, Any]:
    """Copy the typed readiness fields; name an unobserved reading."""
    if reading is None:
        return {"observed": False, "cause": "not_run"}
    if not reading.observed:
        return {"observed": False, "cause": _unobserved(reading)}
    ports: dict[str, Any] = {}
    rows = reading.payload.get("ports")
    for name, value in sorted((rows or {}).items()):
        if not isinstance(value, Mapping):
            ports[str(name)[:80]] = {"malformed": True}
            continue
        row = {
            key: value.get(key)
            for key in READINESS_PORT_KEYS
            if _readiness_value(value.get(key))
        } | {"error": str(value.get("error") or "")[:120]}
        # The documented meaning of the light is resolved here, from the raw
        # value and its `typeof` alone. An unknown code stays unknown.
        row["light_status_name"] = interpret_port_light(
            row.get("light_status"), str(value.get("light_status_type") or "absent")
        )
        ports[str(name)[:80]] = row
    facts: dict[str, Any] = {"observed": True, "ports": ports}
    listeners = reading.payload.get("listeners")
    if isinstance(listeners, Mapping):
        facts["listeners"] = {
            key: listeners.get(key)
            for key in READINESS_LISTENER_KEYS
            if _readiness_value(listeners.get(key))
        }
    return facts


@dataclass(frozen=True)
class ReadinessSample:
    """One aggregate readiness reading over the exact fixture endpoints.

    The three flags are deliberately separate. `observed` says the channel
    returned a payload the parser accepted, `complete` says every requested
    port answered with actual booleans and no error, and `ready` says those
    booleans are all true. Only `ready` admits a network attempt, and none of
    them says anything about STP forwarding, reachability or HTTP success.
    """

    observed: bool
    complete: bool
    ready: bool
    cause: str = ""
    facts: Mapping[str, Any] = field(default_factory=dict)


def assess_port_readiness(
    reading: ProbeReading | None, endpoints: Sequence[tuple[str, str]]
) -> ReadinessSample:
    """Judge one aggregate readiness reading against the exact endpoints."""
    facts = _readiness_facts(reading)
    if reading is None:
        return ReadinessSample(False, False, False, "readiness_not_read", facts)
    if not reading.observed:
        return ReadinessSample(False, False, False, _unobserved(reading), facts)
    rows = reading.payload.get("ports")
    if not isinstance(rows, Mapping):
        return ReadinessSample(True, False, False, "readiness_ports_malformed", facts)
    wanted = [f"{device}/{interface}" for device, interface in endpoints]
    if sorted(rows) != sorted(wanted):
        return ReadinessSample(
            True, False, False, "readiness_endpoints_incomplete", facts
        )
    for (device, interface), key in zip(endpoints, wanted, strict=True):
        row = rows[key]
        if not isinstance(row, Mapping):
            return ReadinessSample(
                True, False, False, f"readiness_row_malformed:{key}", facts
            )
        if row.get("device") != device or row.get("interface") != interface:
            return ReadinessSample(
                True, False, False, f"readiness_subject_mismatch:{key}", facts
            )
        if row.get("error"):
            return ReadinessSample(
                True, False, False, f"readiness_read_error:{key}", facts
            )
        for name in READINESS_REQUIRED_BOOLEANS:
            if not isinstance(row.get(name), bool):
                return ReadinessSample(
                    True, False, False, f"readiness_non_boolean:{key}:{name}", facts
                )
    for key in wanted:
        row = rows[key]
        for name in READINESS_REQUIRED_BOOLEANS:
            if row[name] is not True:
                return ReadinessSample(
                    True, True, False, f"readiness_not_up:{key}:{name}", facts
                )
    return ReadinessSample(True, True, True, "", facts)


def assess_https_listener(
    *,
    readiness: Mapping[str, Any],
    marker_page: ProbeReading | None,
    http_positive: RuntimeServiceVerification | None,
    http_off: ProbeReading | None,
    https_positive: RuntimeServiceVerification | None,
    http_negative: RuntimeServiceVerification | None,
    https_off: ProbeReading | None,
    https_negative: RuntimeServiceVerification | None,
    request_urls: Mapping[str, str],
    readiness_after: Mapping[str, Any] | None = None,
) -> Assessment:
    """Judge both same-mode positives and both declared negative controls.

    `readiness` is the bounded gate result the coordinator reached before any
    network attempt. A gate that never became ready leaves every control
    unrun, which is a statement about the measured links and never a verdict
    on the listeners.

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
        "readiness_before": dict(readiness),
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
        facts["readiness_after_failed_positive"] = dict(readiness_after)
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
    if readiness.get("ready") is not True:
        causes.insert(0, f"readiness_not_established:{readiness.get('reason', '')}")
        limitations.append("readiness_result_is_not_a_listener_verdict")
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


# -- Q3 native-default coexistence ---------------------------------------------

#: The two baselines the amended Q3 profile may build on. Anything else --
#: unknown, malformed, incomplete, truncated, enabled, duplicated or merely
#: similar -- refuses before any effect.
BASELINE_EMPTY = "empty_disabled_process"
BASELINE_OBSERVED_NATIVE_DEFAULT = "observed_native_default"
BASELINE_REFUSED = "refused"

_NATIVE_POOL_TYPES: Mapping[str, type] = {
    "name": str,
    "network": str,
    "mask": str,
    "gateway": str,
    "dns": str,
    "start": str,
    "end": str,
    "max": int,
}


@dataclass(frozen=True)
class BaselineAdmission:
    """Whether one observed Q3 server baseline may be built on, and why."""

    admitted: bool
    kind: str
    causes: tuple[str, ...] = ()
    pools: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class DefaultPoolSnapshot:
    """The bounded non-intended pool inventory observed at one moment."""

    label: str
    observed: bool
    cause: str = ""
    pools: tuple[Mapping[str, Any], ...] = ()
    intended_present: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict)


def native_pool_probe_baseline_admitted(
    snapshot: DefaultPoolSnapshot,
    *,
    server: str,
    interface: str,
    expected_row: Mapping[str, object],
) -> bool:
    """Require one exact disabled pool before another diagnostic effect."""
    raw = snapshot.raw
    return bool(
        snapshot.observed
        and not snapshot.intended_present
        and tuple(snapshot.pools) == (dict(expected_row),)
        and raw.get("device") == server
        and raw.get("interface") == interface
        and raw.get("found") is True
        and raw.get("process_found") is True
        and raw.get("enabled_type") == "boolean"
        and raw.get("enabled") is False
        and raw.get("pool_count") == 1
        and raw.get("truncated") is False
        and raw.get("error") == ""
        and raw.get("pools") == [dict(expected_row)]
    )


def assess_native_pool_start_probe(
    *,
    before: DefaultPoolSnapshot,
    probe: ProbeReading,
    after: DefaultPoolSnapshot,
    server: str,
    interface: str,
    requested_start: str,
) -> Assessment:
    """Classify one documented setter from complete physical pool readbacks."""
    before_inventory = (
        [dict(row) for row in before.raw.get("pools", ())] if before.observed else []
    )
    after_inventory = (
        [dict(row) for row in after.raw.get("pools", ())] if after.observed else []
    )
    before_envelope = {
        key: value for key, value in before.raw.items() if key != "pools"
    }
    after_envelope = {key: value for key, value in after.raw.items() if key != "pools"}
    prior = before_inventory[0] if len(before_inventory) == 1 else {}
    current = after_inventory[0] if len(after_inventory) == 1 else {}
    facts = {
        "before": prior,
        "probe": dict(probe.payload) if probe.observed else {},
        "after": current,
        "before_inventory": before_inventory,
        "after_inventory": after_inventory,
        "before_envelope": before_envelope,
        "after_envelope": after_envelope,
        "before_observed": before.observed,
        "after_observed": after.observed,
    }
    if not prior or prior.get("name") != "serverPool" or before.intended_present:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["native_pool_before_unobserved_or_ambiguous"],
        )
    if not probe.observed:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=[f"setter_outcome_unobserved:{probe.cause}"],
            outcome_unknown=True,
        )
    payload = probe.payload
    if (
        payload.get("device") != server
        or payload.get("interface") != interface
        or payload.get("pool") != "serverPool"
        or payload.get("found") is not True
        or payload.get("pre_start") != prior.get("start")
    ):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["setter_subject_or_pre_read_mismatch"],
            outcome_unknown=payload.get("attempted") is True,
        )
    if payload.get("attempted") is not True:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["setter_not_attempted"],
        )
    if payload.get("call_error"):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["setter_reported_error"],
            outcome_unknown=True,
        )
    if not after.observed or not after_inventory:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["native_pool_after_unobserved_or_ambiguous"],
            outcome_unknown=True,
        )
    if before_envelope != after_envelope:
        return Assessment(
            MeasurementConclusion.CONTRADICTED,
            facts=facts,
            causes=["setter_changed_process_or_inventory_envelope"],
        )
    expected = {**prior, "start": requested_start}
    if (
        after_inventory == [expected]
        and not after.intended_present
        and payload.get("post_start") == requested_start
        and prior.get("start") != requested_start
    ):
        return Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE,
            facts=facts,
            limitations=["build_scoped_setter_result_not_pool_service"],
        )
    if after_inventory == [prior] and payload.get("post_start") == prior.get("start"):
        return Assessment(
            MeasurementConclusion.NEGATIVE_OBSERVED,
            facts=facts,
            causes=["setter_returned_without_physical_change"],
        )
    return Assessment(
        MeasurementConclusion.CONTRADICTED,
        facts=facts,
        causes=["setter_changed_unrequested_pool_fields_or_incoherent_readback"],
    )


def assess_native_pool_repeated_start_probe(
    *,
    before: DefaultPoolSnapshot,
    probe: ProbeReading,
    after: DefaultPoolSnapshot,
    server: str,
    interface: str,
    expected_before: Mapping[str, object],
    expected_after: Mapping[str, object],
    evidence_sha256: str,
) -> Assessment:
    """Admit only a repeat of one exact measured coupled setter transition."""
    result = assess_native_pool_start_probe(
        before=before,
        probe=probe,
        after=after,
        server=server,
        interface=interface,
        requested_start=str(expected_after["start"]),
    )
    facts = {**result.facts, "repeat_basis_sha256": evidence_sha256}
    if result.outcome_unknown or result.conclusion in (
        MeasurementConclusion.INCONCLUSIVE,
        MeasurementConclusion.NEGATIVE_OBSERVED,
    ):
        result.facts = facts
        return result
    if (
        facts["before_inventory"] == [dict(expected_before)]
        and facts["after_inventory"] == [dict(expected_after)]
        and facts["before_envelope"] == facts["after_envelope"]
        and probe.observed
        and probe.payload.get("attempted") is True
        and probe.payload.get("call_error") == ""
        and probe.payload.get("post_start") == expected_after["start"]
    ):
        return Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE,
            facts=facts,
            limitations=["repeat_of_one_build_scoped_coupled_result_not_pool_policy"],
        )
    return Assessment(
        MeasurementConclusion.CONTRADICTED,
        facts=facts,
        causes=["episode1_coupled_start_transition_not_reproduced"],
    )


def assess_native_pool_max_probe(
    *,
    before: DefaultPoolSnapshot,
    probe: ProbeReading,
    after: DefaultPoolSnapshot,
    server: str,
    interface: str,
    expected_before: Mapping[str, object],
    requested_max: int,
) -> Assessment:
    """Judge one native capacity call by its complete physical footprint."""
    prior_inventory = (
        [dict(row) for row in before.raw.get("pools", ())] if before.observed else []
    )
    after_inventory = (
        [dict(row) for row in after.raw.get("pools", ())] if after.observed else []
    )
    prior = prior_inventory[0] if len(prior_inventory) == 1 else {}
    current = after_inventory[0] if len(after_inventory) == 1 else {}
    before_envelope = {
        key: value for key, value in before.raw.items() if key != "pools"
    }
    after_envelope = {key: value for key, value in after.raw.items() if key != "pools"}
    facts = {
        "before": prior,
        "after": current,
        "probe": dict(probe.payload) if probe.observed else {},
        "before_inventory": prior_inventory,
        "after_inventory": after_inventory,
        "before_envelope": before_envelope,
        "after_envelope": after_envelope,
    }
    if (
        prior_inventory != [dict(expected_before)]
        or before.intended_present
        or not before.observed
    ):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["native_max_precondition_unobserved_or_changed"],
        )
    if not probe.observed:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=[f"native_max_outcome_unobserved:{probe.cause}"],
            outcome_unknown=True,
        )
    payload = probe.payload
    if (
        payload.get("device") != server
        or payload.get("interface") != interface
        or payload.get("pool") != "serverPool"
        or payload.get("found") is not True
        or payload.get("pre_max") != prior["max"]
    ):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["native_max_subject_or_pre_read_mismatch"],
            outcome_unknown=payload.get("attempted") is True,
        )
    if payload.get("attempted") is not True:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["native_max_not_attempted"],
        )
    if payload.get("call_error"):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["native_max_reported_error"],
            outcome_unknown=True,
        )
    if not after.observed or not after_inventory:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["native_max_after_unobserved"],
            outcome_unknown=True,
        )
    if before_envelope != after_envelope or after.intended_present:
        return Assessment(
            MeasurementConclusion.CONTRADICTED,
            facts=facts,
            causes=["native_max_changed_process_or_inventory_envelope"],
        )
    expected = {**prior, "max": requested_max, "end": prior["start"]}
    if after_inventory == [expected] and payload.get("post_max") == requested_max:
        return Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE,
            facts=facts,
            limitations=["range_and_capacity_only_gateway_dns_exclusions_unqualified"],
        )
    if after_inventory == [prior] and payload.get("post_max") == prior["max"]:
        return Assessment(
            MeasurementConclusion.NEGATIVE_OBSERVED,
            facts=facts,
            causes=["native_max_setter_returned_without_physical_change"],
        )
    return Assessment(
        MeasurementConclusion.CONTRADICTED,
        facts=facts,
        causes=["native_max_changed_unrequested_pool_fields_or_incoherent_readback"],
    )


def _native_policy_exclusions(
    snapshot: DefaultPoolSnapshot,
) -> tuple[tuple[str, str], ...] | None:
    """Return the complete typed exclusion set, or unknown."""
    rows = snapshot.raw.get("exclusions")
    count = snapshot.raw.get("excluded_count")
    if (
        not snapshot.observed
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        or not isinstance(rows, list)
        or len(rows) != count
    ):
        return None
    values: list[tuple[str, str]] = []
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"start", "end"}
            or not isinstance(row["start"], str)
            or not isinstance(row["end"], str)
            or not row["start"]
            or not row["end"]
        ):
            return None
        values.append((row["start"], row["end"]))
    if len(set(values)) != len(values):
        return None
    return tuple(sorted(values))


def native_policy_probe_baseline_admitted(
    snapshot: DefaultPoolSnapshot,
    *,
    server: str,
    interface: str,
    expected_row: Mapping[str, object],
    expected_exclusions: Sequence[Mapping[str, str]],
) -> bool:
    """Require an exact physical pool, disabled process and exclusion set."""
    wanted = tuple(sorted((item["start"], item["end"]) for item in expected_exclusions))
    return (
        native_pool_probe_baseline_admitted(
            snapshot, server=server, interface=interface, expected_row=expected_row
        )
        and _native_policy_exclusions(snapshot) == wanted
    )


def native_policy_snapshot_complete(
    snapshot: DefaultPoolSnapshot, *, server: str, interface: str
) -> bool:
    """Recognize a coherent final disabled pool and complete exclusion list."""
    return bool(
        len(snapshot.pools) == 1
        and native_pool_probe_baseline_admitted(
            snapshot,
            server=server,
            interface=interface,
            expected_row=snapshot.pools[0],
        )
        and _native_policy_exclusions(snapshot) is not None
    )


def _native_policy_facts(
    before: DefaultPoolSnapshot, after: DefaultPoolSnapshot, probe: ProbeReading
) -> dict[str, Any]:
    """Retain both complete physical snapshots around one policy call."""
    prior = before.raw.get("pools") if before.observed else None
    current = after.raw.get("pools") if after.observed else None
    exclusions_before = _native_policy_exclusions(before)
    exclusions_after = _native_policy_exclusions(after)
    return {
        "before": dict(prior[0]) if isinstance(prior, list) and len(prior) == 1 else {},
        "after": (
            dict(current[0]) if isinstance(current, list) and len(current) == 1 else {}
        ),
        "before_inventory": prior,
        "after_inventory": current,
        "before_exclusions": (
            [{"start": a, "end": b} for a, b in exclusions_before]
            if exclusions_before is not None
            else None
        ),
        "after_exclusions": (
            [{"start": a, "end": b} for a, b in exclusions_after]
            if exclusions_after is not None
            else None
        ),
        "probe": dict(probe.payload) if probe.observed else {},
        "before_envelope": {
            key: value
            for key, value in before.raw.items()
            if key not in {"pools", "exclusions", "excluded_count"}
        },
        "after_envelope": {
            key: value
            for key, value in after.raw.items()
            if key not in {"pools", "exclusions", "excluded_count"}
        },
    }


def assess_native_policy_address_probe(
    *,
    before: DefaultPoolSnapshot,
    probe: ProbeReading,
    after: DefaultPoolSnapshot,
    server: str,
    interface: str,
    field: str,
    expected_before: Mapping[str, object],
    expected_after: Mapping[str, object],
    expected_exclusions: Sequence[Mapping[str, str]],
) -> Assessment:
    """Require exactly one gateway or DNS change on a disabled native pool."""
    if field not in {"gateway", "dns"}:
        raise ValueError("native policy address field is not fixed")
    facts = _native_policy_facts(before, after, probe)
    expected_xs = tuple(
        sorted((item["start"], item["end"]) for item in expected_exclusions)
    )
    if (
        not native_pool_probe_baseline_admitted(
            before, server=server, interface=interface, expected_row=expected_before
        )
        or _native_policy_exclusions(before) != expected_xs
    ):
        return Assessment(
            INCONCLUSIVE, facts=facts, causes=["native_policy_precondition_unobserved"]
        )
    if not probe.observed:
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=[f"native_policy_setter_unobserved:{probe.cause}"],
            outcome_unknown=True,
        )
    payload = probe.payload
    if (
        payload.get("device") != server
        or payload.get("interface") != interface
        or payload.get("pool") != "serverPool"
        or payload.get("field") != field
        or payload.get("found") is not True
        or payload.get("pre_value") != expected_before[field]
    ):
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["native_policy_subject_or_pre_read_mismatch"],
            outcome_unknown=payload.get("attempted") is True,
        )
    if payload.get("attempted") is not True:
        return Assessment(
            INCONCLUSIVE, facts=facts, causes=["native_policy_not_attempted"]
        )
    if payload.get("call_error"):
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["native_policy_setter_error"],
            outcome_unknown=True,
        )
    if not after.observed or _native_policy_exclusions(after) is None:
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["native_policy_after_unobserved"],
            outcome_unknown=True,
        )
    if (
        native_pool_probe_baseline_admitted(
            after, server=server, interface=interface, expected_row=expected_after
        )
        and _native_policy_exclusions(after) == expected_xs
        and facts["before_envelope"] == facts["after_envelope"]
        and payload.get("post_value") == expected_after[field]
    ):
        return Assessment(SUPPORTED, facts=facts, limitations=["policy_field_only"])
    if (
        facts["after"] == dict(expected_before)
        and _native_policy_exclusions(after) == expected_xs
        and facts["before_envelope"] == facts["after_envelope"]
        and payload.get("post_value") == expected_before[field]
    ):
        return Assessment(
            NEGATIVE,
            facts=facts,
            causes=["native_policy_setter_returned_without_change"],
        )
    return Assessment(
        CONTRADICTED,
        facts=facts,
        causes=["native_policy_changed_unrequested_field_or_inventory"],
    )


def assess_native_policy_exclusion_probe(
    *,
    before: DefaultPoolSnapshot,
    probe: ProbeReading,
    after: DefaultPoolSnapshot,
    server: str,
    interface: str,
    expected_row: Mapping[str, object],
    expected_before: Sequence[Mapping[str, str]],
    added: Mapping[str, str],
) -> Assessment:
    """Require one exact added exclusion and no other process or pool change."""
    facts = _native_policy_facts(before, after, probe)
    before_xs = tuple(sorted((item["start"], item["end"]) for item in expected_before))
    expected_xs = tuple(sorted((*before_xs, (added["start"], added["end"]))))
    if (
        not native_pool_probe_baseline_admitted(
            before, server=server, interface=interface, expected_row=expected_row
        )
        or _native_policy_exclusions(before) != before_xs
    ):
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["native_exclusion_precondition_unobserved"],
        )
    if not probe.observed:
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=[f"native_exclusion_outcome_unobserved:{probe.cause}"],
            outcome_unknown=True,
        )
    payload = probe.payload
    if (
        payload.get("device") != server
        or payload.get("interface") != interface
        or payload.get("found") is not True
        or payload.get("pre_count") != len(before_xs)
    ):
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["native_exclusion_subject_or_pre_read_mismatch"],
            outcome_unknown=payload.get("attempted") is True,
        )
    if payload.get("attempted") is not True:
        return Assessment(
            INCONCLUSIVE, facts=facts, causes=["native_exclusion_not_attempted"]
        )
    if payload.get("call_error"):
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["native_exclusion_setter_error"],
            outcome_unknown=True,
        )
    if not after.observed or _native_policy_exclusions(after) is None:
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["native_exclusion_after_unobserved"],
            outcome_unknown=True,
        )
    if (
        native_pool_probe_baseline_admitted(
            after, server=server, interface=interface, expected_row=expected_row
        )
        and _native_policy_exclusions(after) == expected_xs
        and facts["before_envelope"] == facts["after_envelope"]
        and payload.get("post_count") == len(expected_xs)
    ):
        return Assessment(
            SUPPORTED, facts=facts, limitations=["exclusion_readback_only"]
        )
    if (
        facts["after"] == dict(expected_row)
        and _native_policy_exclusions(after) == before_xs
        and facts["before_envelope"] == facts["after_envelope"]
        and payload.get("post_count") == len(before_xs)
    ):
        return Assessment(
            NEGATIVE,
            facts=facts,
            causes=["native_exclusion_setter_returned_without_change"],
        )
    return Assessment(
        CONTRADICTED,
        facts=facts,
        causes=["native_exclusion_changed_unrequested_state"],
    )


def _is_observed_native_default(row: Any) -> bool:
    """Return whether one row is the exact observed native pool, field by field."""
    if not isinstance(row, Mapping) or set(row) != set(Q3_OBSERVED_NATIVE_DEFAULT_POOL):
        return False
    for key, expected in Q3_OBSERVED_NATIVE_DEFAULT_POOL.items():
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, _NATIVE_POOL_TYPES[key]):
            return False
        if value != expected:
            return False
    return True


def _bounded_pools(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    rows = payload.get("pools")
    if not isinstance(rows, list):
        return ()
    return tuple(dict(row) for row in rows if isinstance(row, Mapping))


def _is_typed_pool_row(row: Any) -> bool:
    """Whether one bounded inventory row has the complete typed pool shape."""
    if not isinstance(row, Mapping) or set(row) != set(_NATIVE_POOL_TYPES):
        return False
    for key, expected_type in _NATIVE_POOL_TYPES.items():
        value = row[key]
        if isinstance(value, bool) or not isinstance(value, expected_type):
            return False
    return bool(row["name"])


def assess_dhcp_baseline_admission(
    reading: ProbeReading | None,
    *,
    server: str,
    interface: str,
    intended_pool: str,
    observed_build: str,
    qualified_build: str,
    observed_channel: str,
    qualified_channels: Sequence[str],
) -> BaselineAdmission:
    """Decide whether the amended Q3 profile may build on this baseline.

    Two baselines are admissible on the disposable fixture, the exact reviewed
    build and the fixed channel: a coherently observed empty inventory under a
    disabled process, and exactly one complete row equal to the observed native
    default. A matching pool name is not authority; every field is compared by
    value and by type, and a refusal names each reason it found.

    The reviewed build and the permitted channels are supplied by the caller,
    because which backend version this coexistence was measured on is not a
    domain fact. A composition that declares neither refuses, like any other
    unobservable required value.
    """
    causes: list[str] = []
    if not qualified_build or observed_build != qualified_build:
        causes.append(
            f"coexistence_not_qualified_for_build:{observed_build or 'unknown'}"
        )
    if not qualified_channels or observed_channel not in qualified_channels:
        causes.append(
            f"coexistence_not_qualified_for_channel:{observed_channel or 'unknown'}"
        )
    if reading is None:
        causes.append("dhcp_server_baseline_not_read")
        return BaselineAdmission(False, BASELINE_REFUSED, tuple(causes))
    if not reading.observed:
        causes.append(_unobserved(reading))
        return BaselineAdmission(False, BASELINE_REFUSED, tuple(causes))
    payload = reading.payload
    pools = _bounded_pools(payload)
    if payload.get("device") != server:
        causes.append("baseline_subject_not_the_owned_server")
    if payload.get("interface") != interface:
        causes.append("baseline_interface_not_the_bound_port")
    if payload.get("found") is not True:
        causes.append("baseline_device_not_found")
    if payload.get("process_found") is not True:
        causes.append("baseline_dhcp_process_absent")
    if payload.get("enabled_type") != "boolean" or payload.get("enabled") is not False:
        causes.append("baseline_process_not_an_actual_disabled_boolean")
    if payload.get("error"):
        causes.append("baseline_read_error")
    if payload.get("truncated") is not False:
        causes.append("baseline_inventory_truncated")
    count = payload.get("pool_count")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not isinstance(payload.get("pools"), list)
        or count != len(payload["pools"])
        or len(pools) != len(payload["pools"])
    ):
        causes.append("baseline_inventory_incoherent")
        return BaselineAdmission(False, BASELINE_REFUSED, tuple(causes), pools)
    if any(row.get("name") == intended_pool for row in pools):
        causes.append("baseline_already_contains_the_intended_pool")
    kind = BASELINE_REFUSED
    if not pools:
        kind = BASELINE_EMPTY
    elif len(pools) == 1 and _is_observed_native_default(pools[0]):
        kind = BASELINE_OBSERVED_NATIVE_DEFAULT
    elif len(pools) > 1:
        causes.append("baseline_extra_or_duplicate_pool")
    else:
        causes.append("baseline_pool_is_not_the_exact_observed_native_default")
    if causes:
        return BaselineAdmission(False, BASELINE_REFUSED, tuple(causes), pools)
    return BaselineAdmission(True, kind, (), pools)


def default_pool_snapshot(
    label: str,
    reading: ProbeReading | None,
    *,
    intended_pool: str,
    server: str,
    interface: str,
) -> DefaultPoolSnapshot:
    """Validate and retain one bounded post-admission pool observation."""
    if reading is None:
        return DefaultPoolSnapshot(label, False, "default_pool_snapshot_not_read")
    if not reading.observed:
        return DefaultPoolSnapshot(
            label,
            False,
            _unobserved(reading),
            raw=dict(reading.payload),
        )
    payload = reading.payload
    raw = dict(payload)
    cause = ""
    if payload.get("device") != server:
        cause = "default_pool_snapshot_subject_mismatch"
    elif payload.get("interface") != interface:
        cause = "default_pool_snapshot_interface_mismatch"
    elif payload.get("found") is not True:
        cause = "default_pool_snapshot_device_not_found"
    elif payload.get("process_found") is not True:
        cause = "default_pool_snapshot_process_absent"
    elif payload.get("enabled_type") != "boolean" or not isinstance(
        payload.get("enabled"), bool
    ):
        cause = "default_pool_snapshot_process_state_malformed"
    elif payload.get("error"):
        cause = "default_pool_snapshot_read_error"
    elif payload.get("truncated") is not False:
        cause = "default_pool_snapshot_inventory_truncated"
    rows = payload.get("pools")
    count = payload.get("pool_count")
    if not cause and (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        or not isinstance(rows, list)
        or count != len(rows)
    ):
        cause = "default_pool_snapshot_inventory_incoherent"
    if not cause and any(not _is_typed_pool_row(row) for row in rows):
        cause = "default_pool_snapshot_row_malformed"
    if not cause:
        names = [row["name"] for row in rows]
        if len(names) != len(set(names)):
            cause = "default_pool_snapshot_duplicate_pool_name"
    pools = _bounded_pools(payload)
    if cause:
        return DefaultPoolSnapshot(label, False, cause, raw=raw)
    return DefaultPoolSnapshot(
        label,
        True,
        "",
        tuple(row for row in pools if row.get("name") != intended_pool),
        any(row.get("name") == intended_pool for row in pools),
        raw,
    )


def default_pool_differences(
    before: DefaultPoolSnapshot, after: DefaultPoolSnapshot
) -> tuple[str, ...]:
    """Name every way the observed native default moved between two reads."""
    if not before.observed:
        return (f"default_pool_snapshot_unobserved:{before.label}",)
    if not after.observed:
        return (f"default_pool_snapshot_unobserved:{after.label}",)
    first = {str(row.get("name")): row for row in before.pools}
    second = {str(row.get("name")): row for row in after.pools}
    differences = [
        f"default_pool_removed:{name}" for name in sorted(set(first) - set(second))
    ]
    differences += [
        f"default_pool_added:{name}" for name in sorted(set(second) - set(first))
    ]
    for name in sorted(set(first) & set(second)):
        for key in sorted(set(first[name]) | set(second[name])):
            if first[name].get(key) != second[name].get(key):
                differences.append(f"default_pool_changed:{name}.{key}")
    return tuple(differences)


# -- D-WEB and D-DHCP ----------------------------------------------------------

#: Every diagnostic conclusion carries this: what these stages measure is a
#: boundary or a transition, not a product invariant. Observing it confirms no
#: capability and learns no allowlist from it.
DIAGNOSTIC_SCOPE = "diagnostic_observation_confirms_no_product_capability"
#: A ping changes ARP, MAC and timing state. Any later success on the same
#: fixture is therefore not attributable to the boundary under investigation
#: unless a governed comparison changed only that boundary.
ACTIVE_STIMULUS = "ping_is_an_active_stimulus:arp_mac_and_timing_state_changed"


def assess_access_forwarding(
    observation: AccessForwardingObservation,
    *,
    label: str,
    lights: Mapping[str, Any] | None = None,
) -> Assessment:
    """Judge one bounded per-VLAN forwarding sample of the exact interfaces.

    The admission rule decides; this only states what the decision supports.
    An admitted sample supports forwarding for those interfaces, in that VLAN,
    in that sample -- never reachability, never a service, and never a later
    sample. A refused one names its dimension and supports nothing at all.
    """
    admission = access_forwarding_admission(observation)
    facts = {label: access_forwarding_facts(observation, admission)}
    if lights is not None:
        # Kept beside the rows, never merged into them: a green light and a
        # non-forwarding row are contemporaneous and contradictory, and both
        # stay in the record exactly as they were observed.
        facts[f"{label}_port_lights"] = dict(lights)
    limitations = [
        DIAGNOSTIC_SCOPE,
        "forwarding_permission_is_per_vlan_per_interface_per_sample",
        "light_status_and_port_up_are_auxiliary_and_grant_no_forwarding",
    ]
    if not admission.admitted:
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=[f"{admission.dimension}", *admission.causes],
            limitations=limitations,
        )
    return Assessment(SUPPORTED, facts=facts, limitations=limitations)


def assess_forwarding_probe(
    evidence: Mapping[str, Any] | None,
    *,
    forwarding_admitted: bool,
) -> Assessment:
    """Judge one bind-before-ping probe without promoting it past ICMP.

    A verified probe establishes that one attributed ICMP exchange between two
    validated bindings reached its destination. It says nothing about TCP,
    about a listener, or about the HTTP request that follows it. An
    unattributed or drifted probe establishes nothing at all.
    """
    facts = {"probe": dict(evidence or {})}
    limitations = [
        DIAGNOSTIC_SCOPE,
        ACTIVE_STIMULUS,
        "icmp_reachability_is_not_tcp_or_http_service",
    ]
    if not evidence:
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["probe_not_run"],
            limitations=limitations,
        )
    if not forwarding_admitted:
        # The ping may have run; what it cannot do is stand in for the
        # forwarding evidence the stage refused to grant.
        limitations.append("ping_taken_without_admitted_forwarding_evidence")
    status = str(evidence.get("status") or "")
    if not evidence.get("bindings_stable"):
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=[f"probe_not_attributed:{status or 'unknown'}"],
            limitations=limitations,
            outcome_unknown=status == "unobservable",
        )
    if status != "verified":
        return Assessment(
            NEGATIVE if status == "failed" else INCONCLUSIVE,
            facts=facts,
            causes=[f"probe_{status or 'unknown'}"],
            limitations=limitations,
        )
    return Assessment(SUPPORTED, facts=facts, limitations=limitations)


def assess_client_timeline(
    row: RuntimeServiceVerification | None,
    *,
    marker: str,
    schedule: Sequence[float],
) -> Assessment:
    """Judge one instrumented fetch of the real owned background client.

    The conclusion is the reader's own observation fact. What this adds is the
    boundary statement: a retrieved marker supports the whole path for this
    sample, and anything else leaves the listener, request, client and reader
    boundary unresolved rather than blaming one of them.
    """
    limitations = [DIAGNOSTIC_SCOPE, "timeout_is_never_a_negative_listener_claim"]
    if row is None:
        return Assessment(
            INCONCLUSIVE,
            facts={"fetch": {"observed": False}},
            causes=["fetch_not_run"],
            limitations=limitations,
        )
    steps = [item.model_dump(mode="json") for item in row.trace]
    performed = [item for item in steps if item["performed"]]
    late = [item for item in steps if item["label"] == "late_control"]
    facts = {
        "fetch": {
            "outcome": fetch_outcome(row),
            "observation": row.observation.value,
            "cause": row.cause,
            "marker": marker,
            "schedule": [float(item) for item in schedule],
            "inspections": len(
                [item for item in performed if item["label"] == "inspect"]
            ),
            "missed_slots": len([item for item in steps if not item["performed"]]),
            "late_read": late[0] if late else None,
            "timeline": steps,
            "inputs": dict(row.observed),
            "limitations": list(row.limitations),
        }
    }
    if (
        late
        and late[0]["content_changed"]
        and row.observation is not (ObservationFact.OBSERVED)
    ):
        limitations.append("late_content_is_late_evidence_not_success_in_window")
    if row.observation is ObservationFact.OBSERVED:
        return Assessment(SUPPORTED, facts=facts, limitations=limitations)
    if row.observation is ObservationFact.CONTRADICTED:
        return Assessment(
            CONTRADICTED,
            facts=facts,
            causes=[row.cause or "fresh_without_marker"],
            limitations=limitations,
        )
    limitations.append("listener_request_client_and_reader_boundary_unresolved")
    return Assessment(
        INCONCLUSIVE,
        facts=facts,
        causes=[row.cause or row.observation.value],
        limitations=limitations,
    )


def assess_native_default_interval(
    *,
    label: str,
    before: DefaultPoolSnapshot,
    after: DefaultPoolSnapshot,
    intervention: str,
    native_calls: Sequence[str] = (),
    fields_written: Sequence[str] = (),
) -> Assessment:
    """State what one adjacent pair of native readings identifies.

    A transition between two snapshots identifies the INTERVAL between them.
    It does not identify one native call inside that interval, and it says
    nothing about the backend algorithm that produced it. When the interval
    contains an intervention whose own footprint writes more than one field,
    the broader intervention is named here rather than a narrower cause being
    claimed.
    """
    differences = default_pool_differences(before, after)
    facts = {
        label: {
            "before": before.label,
            "after": after.label,
            "intervention": intervention,
            "native_calls": list(native_calls),
            "fields_written": list(fields_written),
            "differences": list(differences),
            "observed": before.observed and after.observed,
        }
    }
    limitations = [
        DIAGNOSTIC_SCOPE,
        f"transition_identifies_the_interval_not_one_call:{intervention}",
    ]
    if len(fields_written) > 1:
        limitations.append(
            "intervention_writes_more_than_one_field:" + ",".join(fields_written)
        )
    if not (before.observed and after.observed):
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=[
                f"native_default_unobserved:{before.label}"
                if not before.observed
                else f"native_default_unobserved:{after.label}"
            ],
            limitations=limitations,
            outcome_unknown=True,
        )
    if differences:
        return Assessment(
            NEGATIVE,
            facts=facts,
            causes=[f"native_default_changed:{item}" for item in differences],
            limitations=limitations,
        )
    return Assessment(SUPPORTED, facts=facts, limitations=limitations)


def assess_native_default_cumulative(
    *,
    label: str,
    baseline: DefaultPoolSnapshot | None,
    final: DefaultPoolSnapshot,
    interventions: Sequence[str] = (),
    declared_native_calls: Sequence[str] = (),
) -> Assessment:
    """State what the run's first and last native readings identify together.

    This pair does not bracket one intervention. It spans every intervention
    the run dispatched, so a difference between them is cumulative and belongs
    to the sequence, never to the last call inside it. Naming one intervention
    here would report a span as a step.

    `declared_native_calls` is the footprint the generators declare for those
    interventions. It is what would be emitted, not a count of what executed:
    an adjacent interval is where a single intervention is attributed, and the
    typed action rows are where execution is observed.
    """
    differences = (
        default_pool_differences(baseline, final) if baseline is not None else ()
    )
    baseline_observed = baseline is not None and baseline.observed
    comparison_available = baseline_observed and final.observed
    facts = {
        label: {
            "before": baseline.label if baseline is not None else None,
            "after": final.label,
            "span": "cumulative_baseline_to_final",
            "interventions": list(interventions),
            "declared_native_calls": list(declared_native_calls),
            "differences": list(differences),
            "observed": comparison_available,
            "baseline_observed": baseline_observed,
            "final_observed": final.observed,
            "comparison_available": comparison_available,
        }
    }
    limitations = [
        DIAGNOSTIC_SCOPE,
        "cumulative_span_identifies_the_sequence_not_one_intervention:"
        + ("+".join(interventions) if interventions else "none"),
        "declared_call_footprint_is_not_an_observed_execution_count",
    ]
    if baseline is None:
        limitations.append("cumulative_comparison_unavailable_without_baseline")
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=["native_default_baseline_missing"],
            limitations=limitations,
            outcome_unknown=True,
        )
    if not comparison_available:
        return Assessment(
            INCONCLUSIVE,
            facts=facts,
            causes=[
                f"native_default_unobserved:{baseline.label}"
                if not baseline.observed
                else f"native_default_unobserved:{final.label}"
            ],
            limitations=limitations,
            outcome_unknown=True,
        )
    if differences:
        return Assessment(
            NEGATIVE,
            facts=facts,
            causes=[
                f"native_default_changed_cumulatively:{item}" for item in differences
            ],
            limitations=limitations,
        )
    return Assessment(SUPPORTED, facts=facts, limitations=limitations)


def assess_baseline_drift(
    first: DefaultPoolSnapshot, second: DefaultPoolSnapshot
) -> Assessment:
    """Distinguish autonomous drift from a transition following an effect.

    Two adjacent readings with no intervention between them. A difference
    here is the workspace moving on its own, which invalidates every later
    attribution in this run rather than being attributed to the first effect.
    """
    assessment = assess_native_default_interval(
        label="baseline_control",
        before=first,
        after=second,
        intervention="none:adjacent_baseline_readings",
    )
    if assessment.conclusion is NEGATIVE:
        return Assessment(
            CONTRADICTED,
            facts=assessment.facts,
            causes=["autonomous_native_default_drift", *assessment.causes],
            limitations=[
                *assessment.limitations,
                "no_later_transition_in_this_run_is_attributable_to_an_effect",
            ],
        )
    return assessment
