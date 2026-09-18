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


def assess_page_tables(write: ProbeReading, read: ProbeReading | None) -> Assessment:
    """Distinguish one shared page table from two separate ones.

    Reference equality between the two process handles is recorded as a fact
    and deliberately decides nothing: equal references still need the
    cross-read to say whose pages are visible, and unequal ones can still share
    a table.
    """
    limitations = ["reference_equality_is_not_page_ownership"]
    if not write.observed:
        return Assessment(
            INCONCLUSIVE, {}, [_unobserved(write)], limitations, outcome_unknown=True
        )
    facts: dict[str, Any] = {
        "http_process_found": write.payload["http_found"],
        "https_process_found": write.payload["https_found"],
        "object_identity_equal": write.payload["reference_equal"],
    }
    errors = [
        str(write.payload[key])
        for key in ("http_write_error", "https_write_error")
        if write.payload[key]
    ]
    if not write.payload["http_found"] or not write.payload["https_found"]:
        return Assessment(INCONCLUSIVE, facts, ["process_absent"], limitations)
    if errors:
        return Assessment(
            INCONCLUSIVE, facts, ["marker_write_failed", *errors], limitations
        )
    if read is None or not read.observed:
        cause = _unobserved(read) if read else "cross_read_not_run"
        return Assessment(INCONCLUSIVE, facts, [cause], limitations)
    cross = {key: read.payload[key] for key in ("hh", "hs", "sh", "ss")}
    facts["visibility"] = cross
    facts["cross_read_errors"] = read.payload["read_errors"]
    causes = [
        f"cross_read_failed:{key}:{str(value)[:120]}"
        for key, value in sorted(read.payload["errors"].items())
    ]
    # A cell nobody could read is unobserved, never an observed absence. Two
    # such cells would otherwise be indistinguishable from two separate page
    # tables, and one would manufacture an asymmetry that nobody measured.
    unobserved = sorted(key for key, value in cross.items() if value is None)
    if len(unobserved) != read.payload["read_errors"]:
        return Assessment(
            INCONCLUSIVE,
            facts,
            ["cross_read_count_contradicts_cells", *causes],
            limitations,
        )
    if unobserved:
        return Assessment(
            INCONCLUSIVE,
            facts,
            ["cross_read_unobserved:" + ",".join(unobserved), *causes],
            limitations,
        )
    if not (cross["hh"] and cross["ss"]):
        return Assessment(INCONCLUSIVE, facts, ["own_marker_not_readable"], limitations)
    if cross["hs"] and cross["sh"]:
        facts["page_table_model"] = "shared"
        return Assessment(SUPPORTED, facts, [], limitations)
    if not cross["hs"] and not cross["sh"]:
        facts["page_table_model"] = "separate"
        return Assessment(SUPPORTED, facts, [], limitations)
    return Assessment(CONTRADICTED, facts, ["asymmetric_page_visibility"], limitations)


# -- M-HTTPS-2 -----------------------------------------------------------------


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


def _positive_control(
    outcome: str, *, setup_established: bool
) -> tuple[MeasurementConclusion, list[str]]:
    """Classify the declared positive condition of the listener model."""
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
    `NO_QUALIFIED_NEGATIVE_OBSERVABLE`. The same-mode positive control is
    recorded because a negative in one mode is not qualified by a positive in
    another.
    """
    if not disabled_confirmed:
        return INCONCLUSIVE, ["listener_state_not_read_back"]
    if outcome == "marker_retrieved":
        return CONTRADICTED, ["listener_served_while_read_back_as_disabled"]
    causes = [f"observed:{outcome}", NO_QUALIFIED_NEGATIVE_OBSERVABLE]
    if not same_mode_positive:
        causes.insert(0, "no_same_mode_positive_control")
    return INCONCLUSIVE, causes


def assess_https_listener(
    positive_setup: ProbeReading | None,
    positive: RuntimeServiceVerification | None,
    http_negative: RuntimeServiceVerification | None,
    https_setup: ProbeReading | None,
    https_negative: RuntimeServiceVerification | None,
) -> Assessment:
    """Judge the positive condition and both declared negative controls.

    The model claims that a listener *fails* when it is disabled, and this
    reader has no observation that establishes a refusal, so a supported
    conclusion is unreachable here by construction. The measurement records
    every descriptive observation, contradicts the model when a listener that
    was read back as disabled still served the marker or when the marked
    positive page returned other content, and is otherwise INCONCLUSIVE.
    """
    p_setup = listener_toggle_established(positive_setup, http=False, https=True)
    n1_setup = listener_toggle_established(https_setup, http=False, https=False)
    p_outcome = fetch_outcome(positive)
    n2_outcome = fetch_outcome(http_negative)
    n1_outcome = fetch_outcome(https_negative)
    positive_conclusion, p_causes = _positive_control(
        p_outcome, setup_established=p_setup
    )
    positive_ok = positive_conclusion is SUPPORTED
    # The HTTP-mode negative has no HTTP-mode positive control in this stage:
    # the positive condition is measured in HTTPS mode only.
    n2, n2_causes = _negative_control(
        n2_outcome, disabled_confirmed=p_setup, same_mode_positive=False
    )
    n1, n1_causes = _negative_control(
        n1_outcome, disabled_confirmed=n1_setup, same_mode_positive=positive_ok
    )
    facts: dict[str, Any] = {
        "positive_https_only": {
            "setup_established": p_setup,
            "fetch": p_outcome,
            "conclusion": positive_conclusion.value,
        },
        "negative_http_mode_http_disabled": {
            "same_mode_positive_control": False,
            "fetch": n2_outcome,
            "conclusion": n2.value,
        },
        "negative_https_mode_https_disabled": {
            "setup_established": n1_setup,
            "same_mode_positive_control": positive_ok,
            "fetch": n1_outcome,
            "conclusion": n1.value,
        },
    }
    limitations = [
        "no_http_mode_positive_control_in_run",
        "fresh_content_not_retained",
        NO_QUALIFIED_NEGATIVE_OBSERVABLE,
    ]
    causes = (
        [f"positive:{item}" for item in p_causes]
        + [f"negative_http:{item}" for item in n2_causes]
        + [f"negative_https:{item}" for item in n1_causes]
    )
    # A setup toggle that was dispatched and never read back is an effect with
    # an unknown outcome, which the coordinator must treat as a stop signal.
    unknown_setup = [
        name
        for name, reading in (
            ("positive_setup", positive_setup),
            ("https_negative_setup", https_setup),
        )
        if reading is not None and not reading.observed
    ]
    causes += [f"setup_unobserved:{name}" for name in unknown_setup]
    conclusion = (
        CONTRADICTED if CONTRADICTED in (positive_conclusion, n1, n2) else INCONCLUSIVE
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
