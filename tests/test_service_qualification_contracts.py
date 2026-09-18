"""S4a module contracts: stage rules, ledger, reader, parser and assessments.

Expected values come from the requirements in section 12 of the maintained
brief, not from the implementation. The planned-minimum numbers are the
design's own accounting at the transport boundary. The system tests prove
separately that a simulated Q0 run spends exactly that many operations.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from unittest import mock

import pytest

from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    LedgerPhase,
    OperationLedger,
    OperationRefused,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    STAGE_CEILINGS,
    STAGE_DEFINITIONS,
    BudgetRecord,
    EnvironmentIdentity,
    ExecutionMode,
    MeasurementConclusion,
    QualificationAuthorization,
    QualificationOutcome,
    QualificationRecord,
    QualificationRequest,
    QualificationStage,
    RefusalKind,
    RefusalSubject,
    RepositoryIdentity,
    SourceIdentity,
    TransportIdentity,
    promotion_evidence_refusal,
    repository_refusals,
    request_refusals,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
)
from packet_tracer_mcp.domain.enterprise.services.service_qualification_evidence import (
    NO_QUALIFIED_NEGATIVE_OBSERVABLE,
    ProbeReading,
    QueueReceipt,
    assess_atomicity,
    assess_bag_persistence,
    assess_client_resolver,
    assess_https_listener,
    assess_observer_release,
    assess_page_tables,
)
from packet_tracer_mcp.infrastructure.execution.service_environment import (
    observe_service_environment,
    parse_service_environment,
)
from packet_tracer_mcp.infrastructure.execution.service_qualification_probes import (
    parse_probe_reading,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

SHA = "c" * 40
BUILD = "9.0.1.0858"
SUPPORTED = MeasurementConclusion.SUPPORTED_IN_SAMPLE
NEGATIVE = MeasurementConclusion.NEGATIVE_OBSERVED
CONTRADICTED = MeasurementConclusion.CONTRADICTED
INCONCLUSIVE = MeasurementConclusion.INCONCLUSIVE


def _request(base: str = "Q0", **changes) -> QualificationRequest:
    """Build a complete request for `base`, then apply field changes."""
    stage = base
    definition = STAGE_DEFINITIONS[QualificationStage(stage)]
    ceiling = STAGE_CEILINGS[QualificationStage(stage)]
    authorization = QualificationAuthorization(
        authorization_id="TD-Q0-1",
        stage=stage,
        sha=SHA,
        targets=definition.fixture_names,
        channel="file",
        build=BUILD,
        max_operations=ceiling[0],
        max_seconds=ceiling[1],
    )
    auth_changes = changes.pop("authorization_changes", {})
    request = QualificationRequest(
        execute=True,
        stage=stage,
        expected_head=SHA,
        targets=definition.fixture_names,
        channel="file",
        packet_tracer_build=BUILD,
        authorization=replace(authorization, **auth_changes),
    )
    return replace(request, **changes)


def _pairs(refusals) -> set[tuple[RefusalKind, RefusalSubject]]:
    return {(item.kind, item.subject) for item in refusals}


# -- stage definitions ---------------------------------------------------------


def test_hard_ceilings_are_the_plan_values():
    """Plan 5.8 ceilings, with Q1's reviewed design ceiling of 60 / 10 min."""
    assert STAGE_CEILINGS[QualificationStage.Q0] == (20, 300)
    assert STAGE_CEILINGS[QualificationStage.Q1] == (60, 600)
    assert STAGE_CEILINGS[QualificationStage.Q2] == (60, 900)
    assert STAGE_CEILINGS[QualificationStage.Q3] == (60, 1200)
    for stage, definition in STAGE_DEFINITIONS.items():
        assert (
            definition.budget.max_operations,
            definition.budget.max_seconds,
        ) == STAGE_CEILINGS[stage]


def test_q0_fits_its_ceiling_with_the_reserve_counted():
    """Q0: 5 setup + 9 required experiment + 5 reserve operations = 19 <= 20."""
    q0 = STAGE_DEFINITIONS[QualificationStage.Q0]
    assert (q0.setup_operations, q0.required_experiment_operations) == (5, 9)
    assert q0.reserve_operations == 5
    assert q0.planned_minimum_operations == 19
    assert q0.fixture_names == ("__MCP_E6Q_PC1",)


def test_q1_fits_its_reviewed_ceiling_on_its_bounded_worst_case():
    """19 setup + 17 required + 10 reserve = 46 worst-case operations <= 60.

    Every planned figure is its step's worst case, including three production
    fetches at four operations each. The luckiest trace is cheaper; the stage
    is admitted on the expensive one, and the reserve is not part of the slack.
    """
    q1 = STAGE_DEFINITIONS[QualificationStage.Q1]
    assert q1.fixture_names == (
        "__MCP_E6Q_SRV",
        "__MCP_E6Q_PC1",
        "__MCP_E6Q_PC2",
        "__MCP_E6Q_SW",
    )
    assert q1.experiment("M-HTTPS-2").planned_operations == 14
    assert (q1.setup_operations, q1.required_experiment_operations) == (19, 17)
    assert q1.reserve_operations == 10
    assert q1.planned_minimum_operations == 46
    assert q1.planned_minimum_operations <= q1.budget.max_operations == 60
    assert request_refusals(_request("Q1")) == ()


def test_a_stage_whose_worst_case_exceeds_its_ceiling_is_refused_before_contact():
    """The infeasibility gate survives the raised ceiling, with its arithmetic."""
    q1 = STAGE_DEFINITIONS[QualificationStage.Q1]
    narrow = replace(q1, budget=replace(q1.budget, max_operations=45))
    with mock.patch.dict(
        STAGE_DEFINITIONS, {QualificationStage.Q1: narrow}, clear=False
    ):
        refusals = request_refusals(_request("Q1"))
    assert _pairs(refusals) == {(RefusalKind.INFEASIBLE, RefusalSubject.BUDGET)}
    assert "46" in refusals[0].detail and "45" in refusals[0].detail


@pytest.mark.parametrize("stage", ["Q2", "Q3"])
def test_declarative_stages_refuse_before_any_reader(stage):
    """Q2/Q3 carry metadata and unmet prerequisites only."""
    refusals = request_refusals(_request(stage=stage))
    assert _pairs(refusals) == {(RefusalKind.NOT_PERMITTED, RefusalSubject.STAGE)}
    assert "not implemented" in refusals[0].detail


def test_optional_measurements_carry_their_omission_reason():
    """M-HTTP-1 and M-DNS-1/2 are omitted with a reason, never silently."""
    q0 = STAGE_DEFINITIONS[QualificationStage.Q0]
    q1 = STAGE_DEFINITIONS[QualificationStage.Q1]
    assert q0.experiment("M-HTTP-1").omission_reason.startswith("prerequisite_absent")
    for identifier in ("M-DNS-1", "M-DNS-2"):
        assert q1.experiment(identifier).omission_reason.startswith(
            "not_admitted_by_budget"
        )
    assert "M-HTTP-1" not in {
        item.id for item in q0.experiments if item.planned_operations
    }


# -- request admission ---------------------------------------------------------


def test_a_complete_matching_q0_request_is_admissible():
    """The positive control: nothing to refuse."""
    assert request_refusals(_request()) == ()


def test_no_execution_flag_refuses_alone_and_first():
    """Nothing runs by default, whatever else the request carries."""
    refusals = request_refusals(_request(execute=False, stage="Q9"))
    assert _pairs(refusals) == {(RefusalKind.MISSING, RefusalSubject.EXECUTION)}


def test_unknown_stage_is_malformed():
    """A stage outside the matrix is named, not guessed."""
    assert _pairs(request_refusals(_request(stage="Q9"))) == {
        (RefusalKind.MALFORMED, RefusalSubject.STAGE)
    }


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"expected_head": ""}, (RefusalKind.MISSING, RefusalSubject.EXPECTED_HEAD)),
        (
            {"expected_head": "ABC"},
            (RefusalKind.MALFORMED, RefusalSubject.EXPECTED_HEAD),
        ),
        ({"targets": ()}, (RefusalKind.MISSING, RefusalSubject.TARGETS)),
        (
            {"targets": ("__MCP_E6Q_PC1", "__MCP_E6Q_PC1")},
            (RefusalKind.MALFORMED, RefusalSubject.TARGETS),
        ),
        (
            {"targets": ("__MCP_E6Q_PC2",)},
            (RefusalKind.MISMATCH, RefusalSubject.TARGETS),
        ),
        ({"channel": ""}, (RefusalKind.MISSING, RefusalSubject.CHANNEL)),
        ({"channel": "udp"}, (RefusalKind.MALFORMED, RefusalSubject.CHANNEL)),
        ({"packet_tracer_build": ""}, (RefusalKind.MISSING, RefusalSubject.BUILD)),
        (
            {"packet_tracer_build": "9.0.1"},
            (RefusalKind.MALFORMED, RefusalSubject.BUILD),
        ),
        (
            {"packet_tracer_build": "9.0.1.0858b"},
            (RefusalKind.MALFORMED, RefusalSubject.BUILD),
        ),
        (
            {"authorization": None},
            (RefusalKind.MISSING, RefusalSubject.AUTHORIZATION),
        ),
    ],
)
def test_request_values_are_refused_by_kind_and_subject(changes, expected):
    """Every request field has a typed missing/malformed/mismatch refusal."""
    assert expected in _pairs(request_refusals(_request(**changes)))


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        (
            {"authorization_id": ""},
            (RefusalKind.MISSING, RefusalSubject.AUTHORIZATION_ID),
        ),
        (
            {"authorization_id": "x\n"},
            (RefusalKind.MALFORMED, RefusalSubject.AUTHORIZATION_ID),
        ),
        ({"stage": ""}, (RefusalKind.MISSING, RefusalSubject.AUTHORIZED_STAGE)),
        ({"stage": "Q7"}, (RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_STAGE)),
        ({"stage": "Q1"}, (RefusalKind.MISMATCH, RefusalSubject.AUTHORIZED_STAGE)),
        ({"sha": ""}, (RefusalKind.MISSING, RefusalSubject.AUTHORIZED_SHA)),
        ({"sha": "c" * 39}, (RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_SHA)),
        ({"sha": "d" * 40}, (RefusalKind.MISMATCH, RefusalSubject.AUTHORIZED_SHA)),
        (
            {"targets": ("__MCP_E6Q_SRV",)},
            (RefusalKind.MISMATCH, RefusalSubject.AUTHORIZED_TARGETS),
        ),
        ({"channel": ""}, (RefusalKind.MISSING, RefusalSubject.AUTHORIZED_CHANNEL)),
        (
            {"channel": "http"},
            (RefusalKind.MISMATCH, RefusalSubject.AUTHORIZED_CHANNEL),
        ),
        ({"build": ""}, (RefusalKind.MISSING, RefusalSubject.AUTHORIZED_BUILD)),
        (
            {"build": "9.0.1.0859"},
            (RefusalKind.MISMATCH, RefusalSubject.AUTHORIZED_BUILD),
        ),
        ({"max_operations": None}, (RefusalKind.MISSING, RefusalSubject.BUDGET)),
        ({"max_seconds": "300s"}, (RefusalKind.MALFORMED, RefusalSubject.BUDGET)),
        ({"max_operations": True}, (RefusalKind.MALFORMED, RefusalSubject.BUDGET)),
        ({"max_operations": 21}, (RefusalKind.MISMATCH, RefusalSubject.BUDGET)),
        ({"max_seconds": 299}, (RefusalKind.MISMATCH, RefusalSubject.BUDGET)),
    ],
)
def test_authorization_scope_is_compared_exactly(changes, expected):
    """Stage, SHA, targets, channel, build and budget must each match exactly."""
    assert expected in _pairs(request_refusals(_request(authorization_changes=changes)))


def test_repository_identity_must_be_complete_clean_and_published():
    """Missing, stale, dirty and unpublished checkouts refuse with typed reasons."""
    good = RepositoryIdentity(
        branch="b", head=SHA, tree="t" * 40, clean=True, upstream="u", upstream_head=SHA
    )
    assert repository_refusals(good, SHA) == ()
    cases = [
        (replace(good, head="", error="git failed"), RefusalSubject.REPOSITORY_HEAD),
        (
            replace(good, head="e" * 40, upstream_head="e" * 40),
            RefusalSubject.REPOSITORY_HEAD,
        ),
        (replace(good, tree=""), RefusalSubject.REPOSITORY_TREE),
        (replace(good, clean=None), RefusalSubject.REPOSITORY_CLEAN),
        (replace(good, clean=False), RefusalSubject.REPOSITORY_CLEAN),
        (replace(good, upstream_head=""), RefusalSubject.REPOSITORY_UPSTREAM),
        (replace(good, upstream_head="e" * 40), RefusalSubject.REPOSITORY_UPSTREAM),
    ]
    for observed, subject in cases:
        assert subject in {item.subject for item in repository_refusals(observed, SHA)}
    stale = repository_refusals(replace(good, head="e" * 40), SHA)
    assert (RefusalKind.MISMATCH, RefusalSubject.REPOSITORY_HEAD) in _pairs(stale)
    unobservable = repository_refusals(replace(good, clean=None), SHA)
    assert (RefusalKind.UNOBSERVABLE, RefusalSubject.REPOSITORY_CLEAN) in _pairs(
        unobservable
    )


# -- ledger --------------------------------------------------------------------


class _Clock:
    """A settable monotonic clock."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current time."""
        return self.now


def test_ledger_admits_exactly_up_to_the_reserve_then_refuses_before_dispatch():
    """The reserve is untouchable outside finalization; a refusal is not counted."""
    clock = _Clock()
    ledger = OperationLedger(max_operations=5, max_seconds=100, clock=clock)
    ledger.reserve(2, 10)
    ledger.enter(LedgerPhase.EXPERIMENT)
    for _ in range(3):
        ledger.admit("dispatch_and_wait", 5.0)
    assert ledger.used == 3
    assert not ledger.can_afford(1)
    with pytest.raises(OperationRefused) as refused:
        ledger.admit("dispatch_and_wait", 5.0)
    assert refused.value.reason == "operation_budget_exhausted"
    assert ledger.used == 3 and ledger.refused_calls == 1
    ledger.enter(LedgerPhase.FINALIZATION)
    ledger.admit("send_and_wait", 5.0)
    ledger.admit("send_and_wait", 5.0)
    assert ledger.used == 5
    with pytest.raises(OperationRefused):
        ledger.admit("send_and_wait", 5.0)


def test_ledger_caps_each_timeout_and_wait_by_the_remaining_phase_time():
    """A call's timeout and a wait never reach into the reserved seconds."""
    clock = _Clock()
    ledger = OperationLedger(max_operations=10, max_seconds=60, clock=clock)
    ledger.reserve(1, 20)
    ledger.enter(LedgerPhase.EXPERIMENT)
    clock.now = 35.0
    _index, timeout = ledger.admit("send_and_wait", 12.0)
    assert timeout == pytest.approx(5.0)
    slept: list[float] = []
    assert ledger.wait(30.0, slept.append) == pytest.approx(5.0)
    clock.now = 40.0
    with pytest.raises(OperationRefused) as refused:
        ledger.admit("send_and_wait", 12.0)
    assert refused.value.reason == "time_budget_exhausted"
    ledger.enter(LedgerPhase.FINALIZATION)
    _index, timeout = ledger.admit("send_and_wait", 12.0)
    assert timeout == pytest.approx(12.0)


def test_closed_effect_gate_admits_only_finalization():
    """After a write-ahead failure no new effect may be dispatched."""
    ledger = OperationLedger(max_operations=10, max_seconds=60, clock=_Clock())
    ledger.reserve(2, 10)
    ledger.enter(LedgerPhase.EXPERIMENT)
    ledger.close_effects("record_not_advanced_past:admitted")
    with pytest.raises(OperationRefused) as refused:
        ledger.admit("dispatch_and_wait", 5.0)
    assert refused.value.reason.startswith("effects_halted:")
    ledger.enter(LedgerPhase.FINALIZATION)
    ledger.admit("send_and_wait", 5.0)
    with pytest.raises(RuntimeError):
        ledger.reserve(1, 1)


# -- reader and parser -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "no_correlated_response"),
        ("PT_ERROR: boom", "engine_error"),
        ("{", "malformed_response"),
        ("[]", "malformed_response"),
        (
            json.dumps({"found": False, "reason": "application_version_unavailable"}),
            "not_found:application_version_unavailable",
        ),
        (json.dumps({"found": True, "backend_version": ""}), "version_absent"),
        (
            json.dumps({"found": True, "backend_version": "9.0.1"}),
            "version_not_exact_build",
        ),
        (
            json.dumps({"found": True, "backend_version": "9" * 70 + ".1.1.1"}),
            "version_not_exact_build",
        ),
    ],
)
def test_build_reader_keeps_every_unavailable_reason_and_no_fallback(raw, reason):
    """Unavailable is typed; the product parser still yields no fingerprint."""
    assert observe_service_environment(raw) == ("", reason)
    assert parse_service_environment(raw, channel="file").backend_version == ""


def test_build_reader_accepts_only_one_exact_build():
    """The positive control of the shared reader."""
    raw = json.dumps({"found": True, "backend_version": BUILD})
    assert observe_service_environment(raw) == (BUILD, "")
    assert parse_service_environment(raw, channel="http").bridge_transport == "http"


def _outcome(body: str | None, result=ResultFact.CORRELATED) -> BridgeDispatchOutcome:
    return BridgeDispatchOutcome(
        dispatch=DispatchFact.ACCEPTED, result=result, body=body
    )


def test_probe_parser_requires_every_promised_key_with_its_exact_type():
    """A missing key or an int posing as a bool is unobserved, never a value."""
    good = {
        "receiver_is_global": True,
        "run_bag_preexisting": False,
        "written": True,
        "owned": True,
    }
    assert parse_probe_reading("eng_write", _outcome(json.dumps(good))).observed
    missing = dict(good)
    del missing["written"]
    reading = parse_probe_reading("eng_write", _outcome(json.dumps(missing)))
    assert not reading.observed and reading.cause == "shape:missing:written"
    wrong = dict(good, written=1)
    assert parse_probe_reading("eng_write", _outcome(json.dumps(wrong))).cause == (
        "shape:type:written"
    )
    counter = {
        "found": True,
        "event": "ipChanged",
        "registered1": True,
        "register1_error": "",
        "trigger_x": True,
        "trigger_error": "",
        "cb1_calls": 0,
    }
    assert (
        parse_probe_reading("unreg_register", _outcome(json.dumps(counter))).cause
        == "shape:type:trigger_x"
    )


def test_probe_parser_separates_transport_engine_and_script_failures():
    """Lost, engine error and caught probe error are distinct unobserved causes."""
    lost = parse_probe_reading("eng_read", _outcome(None, ResultFact.NOT_OBSERVED))
    assert (lost.observed, lost.result) == (False, ResultFact.NOT_OBSERVED)
    engine = parse_probe_reading("eng_read", _outcome("PT_ERROR: x"))
    assert engine.result is ResultFact.ENGINE_ERROR
    caught = parse_probe_reading(
        "eng_read", _outcome(json.dumps({"probe_error": "TypeError"}))
    )
    assert caught.cause.startswith("probe_error:") and not caught.observed
    assert parse_probe_reading("eng_read", _outcome("[1]")).cause == "not_an_object"


# -- assessments ---------------------------------------------------------------


def _reading(step: str, payload=None, *, observed: bool = True) -> ProbeReading:
    return ProbeReading(
        step,
        DispatchFact.ACCEPTED,
        ResultFact.CORRELATED if observed else ResultFact.NOT_OBSERVED,
        observed,
        payload or {},
        "" if observed else "lost",
    )


def _write(preexisting: bool = False) -> ProbeReading:
    return _reading(
        "eng_write",
        {
            "receiver_is_global": True,
            "run_bag_preexisting": preexisting,
            "written": not preexisting,
            "owned": not preexisting,
        },
    )


def _read(found: bool, matches: bool, owned: bool = True) -> ProbeReading:
    return _reading(
        "eng_read",
        {
            "receiver_is_global": True,
            "owned": owned,
            "found": found,
            "nonce_matches": matches,
            "released": found and matches and owned,
        },
    )


def test_bag_persistence_distinguishes_supported_negative_and_contradicted():
    """Found+matching supports; a completed absence is negative; foreign contradicts."""
    assert (
        assess_bag_persistence(_write(), _read(True, True), channel="file").conclusion
        is SUPPORTED
    )
    assert (
        assess_bag_persistence(_write(), _read(False, False), channel="file").conclusion
        is NEGATIVE
    )
    foreign = assess_bag_persistence(_write(), _read(True, False), channel="file")
    assert foreign.conclusion is CONTRADICTED and foreign.outcome_unknown
    collision = assess_bag_persistence(_write(True), None, channel="file")
    assert collision.conclusion is CONTRADICTED
    # The claim proved it wrote nothing, so the outcome is known, not unknown.
    assert collision.outcome_unknown is False
    assert collision.facts["run_key_written"] is False
    assert "nothing was written" in collision.causes[0]


def test_bag_persistence_never_reads_a_lost_answer_as_absence():
    """An unobserved read, or absence after an unobserved write, is inconclusive."""
    lost = assess_bag_persistence(
        _write(), _reading("eng_read", observed=False), channel="file"
    )
    assert lost.conclusion is INCONCLUSIVE
    unwritten = assess_bag_persistence(
        _reading("eng_write", observed=False), _read(False, False), channel="http"
    )
    assert unwritten.conclusion is INCONCLUSIVE and unwritten.outcome_unknown


def _receipts(accepted: bool = True) -> list[QueueReceipt]:
    return [
        QueueReceipt("contender_A", accepted, DispatchFact.ACCEPTED),
        QueueReceipt("contender_B", True, DispatchFact.ACCEPTED),
    ]


def _collect(log, *, present: bool = True, released: bool = True) -> ProbeReading:
    return _reading(
        "atom_collect",
        {
            "present": present,
            "log": log,
            "claim": "A",
            "terminal_steps": 2,
            "released": released,
        },
    )


_SERIAL = [
    {"c": "A", "s": "check", "n": 1},
    {"c": "A", "s": "claimed", "n": 2},
    {"c": "B", "s": "check", "n": 3},
    {"c": "B", "s": "refused", "n": 4},
]


def test_atomicity_http_sample_is_inconclusive_without_observed_separation():
    """An ordered HTTP log does not prove it came from separate evaluations."""
    result = assess_atomicity(_receipts(), _collect(_SERIAL), channel="http")
    assert result.conclusion is INCONCLUSIVE
    assert result.causes == ["separate_evaluations_not_observed"]
    assert result.facts["evaluation_scope"] == "unknown"
    assert result.facts["log"] == _SERIAL
    assert "not_universal_atomicity" in result.limitations
    assert "http_channel_may_join_queued_commands_into_one_batch" in result.limitations


def test_atomicity_file_sample_supports_only_its_observed_separate_pair():
    """A file-channel pair can be scoped support while remaining finite."""
    result = assess_atomicity(_receipts(), _collect(_SERIAL), channel="file")
    assert result.conclusion is SUPPORTED
    assert result.facts["evaluation_scope"] == "separate_evaluations"
    assert "not_universal_atomicity" in result.limitations


def test_atomicity_counterexamples_contradict_the_candidate_invariant():
    """A double claim or an interleaved step is a contradiction."""
    double = [
        {"c": "A", "s": "check", "n": 1},
        {"c": "A", "s": "claimed", "n": 2},
        {"c": "B", "s": "check", "n": 3},
        {"c": "B", "s": "claimed", "n": 4},
    ]
    interleaved = [
        {"c": "A", "s": "check", "n": 1},
        {"c": "B", "s": "check", "n": 2},
        {"c": "A", "s": "claimed", "n": 3},
        {"c": "B", "s": "refused", "n": 4},
    ]
    assert assess_atomicity(_receipts(), _collect(double), channel="file").causes == [
        "double_claim"
    ]
    result = assess_atomicity(_receipts(), _collect(interleaved), channel="file")
    assert result.conclusion is CONTRADICTED
    assert result.causes == ["interleaving_within_contender_A"]


def test_atomicity_unknown_execution_is_inconclusive_and_outcome_unknown():
    """A pending, unaccepted or malformed contender never supports anything."""
    for receipts, collect in (
        (_receipts(False), _collect(_SERIAL)),
        (_receipts(), _collect(_SERIAL[:3], released=False)),
        (_receipts(), _collect([], present=False, released=False)),
        (_receipts(), _collect([{"c": "A", "s": "check", "n": "1"}])),
        (_receipts(), _reading("atom_collect", observed=False)),
    ):
        result = assess_atomicity(receipts, collect, channel="file")
        assert result.conclusion is INCONCLUSIVE and result.outcome_unknown


def _unreg_steps(**overrides):
    register = _reading(
        "unreg_register",
        {
            "found": True,
            "event": "ipChanged",
            "registered1": True,
            "register1_error": "",
            "trigger_x": 1,
            "trigger_error": "",
            "cb1_calls": 0,
        },
    )
    evidence = _reading(
        "unreg_evidence",
        {
            "cb1_calls": 1,
            "cb1_events": [
                {
                    "seq": 2,
                    "className": "HostPort",
                    "uuid": "{u}",
                    "eventName": "ipChanged",
                    "arg_keys": ["inputCommand"],
                }
            ],
            "registered2": True,
            "register2_error": "",
            "cb2_calls": 0,
        },
    )
    release = {
        "release1": {
            "attempted": True,
            "available": True,
            "threw": "",
            "return_type": "undefined",
        },
        "cb2_calls_before_inert": 0,
        "cb2_inert": True,
        "registered3": True,
        "register3_error": "",
        "cb1_calls_before_y": 1,
        "cb2_calls_before_y": 0,
        "cb3_calls_before_y": 0,
        "trigger_y": 3,
        "trigger_error": "",
    }
    after = {
        "cb1_calls": 1,
        "cb1_events_after_y": 0,
        "cb2_calls": 1,
        "cb2_events_after_inert": 0,
        "cb3_calls": 1,
        "cb3_events_after_y": 1,
        "release2": {"attempted": True, "threw": "", "return_type": "undefined"},
        "release3": {"attempted": True, "threw": "", "return_type": "undefined"},
        "dropped": True,
    }
    release.update(overrides.pop("release", {}))
    after.update(overrides.pop("after", {}))
    return (
        register,
        evidence,
        _reading("unreg_release", release),
        _reading("unreg_after", after),
    )


def test_observer_release_supported_needs_delivery_release_and_a_control_event():
    """cb1 silent after Y while the never-released control fired supports release."""
    first, second = assess_observer_release(*_unreg_steps())
    assert first.conclusion is SUPPORTED and second.conclusion is SUPPORTED
    assert second.facts["safe_zero_event_release_established"] is False
    assert first.facts["release_call_label"].startswith("undocumented_existing_usage")


def test_released_callback_invoked_again_contradicts_release():
    """An unregister that did not detach is a contradiction, not a failure."""
    first, _second = assess_observer_release(*_unreg_steps(after={"cb1_calls": 2}))
    assert first.conclusion is CONTRADICTED
    assert "released_callback_invoked_again" in first.causes


def test_without_a_control_event_absence_proves_nothing():
    """No control invocation after Y leaves both measurements inconclusive."""
    first, second = assess_observer_release(
        *_unreg_steps(after={"cb3_calls": 0, "cb2_calls": 0})
    )
    assert first.conclusion is INCONCLUSIVE and second.conclusion is INCONCLUSIVE


def test_zero_event_measurement_requires_its_precondition_and_bounds():
    """A pre-release event, an unexplained detachment or inert recording decide."""
    _first, violated = assess_observer_release(
        *_unreg_steps(release={"cb2_calls_before_inert": 1})
    )
    assert violated.causes == ["zero_event_precondition_violated"]
    _first, detached = assess_observer_release(*_unreg_steps(after={"cb2_calls": 0}))
    assert detached.conclusion is CONTRADICTED
    _first, leaky = assess_observer_release(
        *_unreg_steps(after={"cb2_events_after_inert": 1})
    )
    assert leaky.conclusion is CONTRADICTED


def test_no_delivered_event_means_no_identity_and_no_release_attempt():
    """Without an event there is no uuid to release by; nothing is invented."""
    register, evidence, release, after = _unreg_steps(
        release={
            "release1": {
                "attempted": False,
                "available": True,
                "threw": "",
                "return_type": "",
            }
        }
    )
    evidence = replace(evidence, payload={**evidence.payload, "cb1_events": []})
    first, _second = assess_observer_release(register, evidence, release, after)
    assert first.conclusion is INCONCLUSIVE
    assert "release_not_attempted:identity_unobserved" in first.causes


def _pages(**cross) -> tuple[ProbeReading, ProbeReading]:
    write = _reading(
        "page_write",
        {
            "http_found": True,
            "https_found": True,
            "reference_equal": False,
            "http_write_error": "",
            "https_write_error": "",
        },
    )
    values = {
        "hh": True,
        "hs": False,
        "sh": False,
        "ss": True,
        "read_errors": 0,
        "errors": {},
    }
    values.update(cross)
    return write, _reading("page_read", values)


def test_page_tables_are_decided_by_cross_reads_not_reference_equality():
    """Symmetric cross-visibility is shared, symmetric absence separate."""
    separate = assess_page_tables(*_pages())
    assert separate.facts["page_table_model"] == "separate"
    shared = assess_page_tables(*_pages(hs=True, sh=True))
    assert shared.facts["page_table_model"] == "shared"
    assert "reference_equality_is_not_page_ownership" in shared.limitations
    assert assess_page_tables(*_pages(hs=True)).conclusion is CONTRADICTED
    assert assess_page_tables(*_pages(ss=False)).conclusion is INCONCLUSIVE


def test_an_unreadable_cross_cell_decides_nothing_in_either_direction():
    """A cell nobody could read is unobserved: not an absence, not an asymmetry."""
    both = assess_page_tables(
        *_pages(
            hs=None,
            sh=None,
            read_errors=2,
            errors={"hs": "page read refused", "sh": "page read refused"},
        )
    )
    assert both.conclusion is INCONCLUSIVE
    assert "page_table_model" not in both.facts
    assert "cross_read_unobserved:hs,sh" in both.causes
    assert "cross_read_failed:hs:page read refused" in both.causes
    one = assess_page_tables(
        *_pages(hs=None, sh=True, read_errors=1, errors={"hs": "refused"})
    )
    assert one.conclusion is INCONCLUSIVE
    assert "cross_read_unobserved:hs" in one.causes
    own = assess_page_tables(*_pages(hh=None, read_errors=1, errors={"hh": "refused"}))
    assert own.conclusion is INCONCLUSIVE


def test_a_cross_read_that_contradicts_its_own_error_count_decides_nothing():
    """`read_errors` and the unobserved cells must agree, or the reading is unusable."""
    inflated = assess_page_tables(*_pages(read_errors=2))
    assert inflated.conclusion is INCONCLUSIVE
    assert "cross_read_count_contradicts_cells" in inflated.causes
    silent = assess_page_tables(*_pages(hs=None, read_errors=0))
    assert silent.conclusion is INCONCLUSIVE
    assert "cross_read_count_contradicts_cells" in silent.causes


def _row(observation: ObservationFact, cause: str = "") -> RuntimeServiceVerification:
    return RuntimeServiceVerification(
        expectation_id="q1",
        status=ActionExecutionStatus.UNKNOWN,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        evidence_method="https_client_fresh_content",
        fresh_evidence=True,
        observation=observation,
        cause=cause,
    )


def _toggle(http: bool | None, https: bool | None, error: str = "") -> ProbeReading:
    return _reading(
        "https_only",
        {
            "error": error,
            "index_written": {"http": True, "https": True},
            "http_enabled": http,
            "https_enabled": https,
            "https_process_enabled": True,
        },
    )


def test_a_coherent_positive_with_fresh_negatives_still_cannot_support_the_model():
    """The reader has no refusal observable, so the isolation model stays open.

    Fresh content without the marker proves a marker mismatch. It is not an
    observation that a disabled listener refused the request, and this reader
    reports an actual refusal as a deadline, so no run of this shape can
    establish the negative half of the model.
    """
    result = assess_https_listener(
        _toggle(False, True),
        _row(ObservationFact.OBSERVED),
        _row(ObservationFact.CONTRADICTED),
        _toggle(False, False),
        _row(ObservationFact.CONTRADICTED),
    )
    assert result.conclusion is INCONCLUSIVE
    assert result.outcome_unknown is False
    positive = result.facts["positive_https_only"]
    assert positive["conclusion"] == "supported_in_sample"
    for key in (
        "negative_http_mode_http_disabled",
        "negative_https_mode_https_disabled",
    ):
        assert result.facts[key]["conclusion"] == "inconclusive"
        assert result.facts[key]["fetch"] == "fresh_without_marker"
    assert NO_QUALIFIED_NEGATIVE_OBSERVABLE in result.limitations
    assert f"negative_https:{NO_QUALIFIED_NEGATIVE_OBSERVABLE}" in result.causes
    # The HTTP-mode negative has no HTTP-mode positive; the HTTPS one does.
    assert "negative_http:no_same_mode_positive_control" in result.causes
    assert "negative_https:no_same_mode_positive_control" not in result.causes
    assert (
        result.facts["negative_http_mode_http_disabled"]["same_mode_positive_control"]
        is False
    )


def test_wrong_content_on_the_marked_positive_page_contradicts_the_expectation():
    """A completed read of this run's marked page that returns other content."""
    result = assess_https_listener(
        _toggle(False, True),
        _row(ObservationFact.CONTRADICTED),
        None,
        None,
        None,
    )
    assert result.conclusion is CONTRADICTED
    assert "positive:marked_page_returned_other_content" in result.causes


def test_an_unread_listener_toggle_is_an_unknown_outcome_not_a_negative():
    """A setup that was dispatched and never read back stops the procedure."""
    lost = _reading("https_only", observed=False)
    result = assess_https_listener(lost, None, None, None, None)
    assert result.conclusion is INCONCLUSIVE
    assert result.outcome_unknown is True
    assert "setup_unobserved:positive_setup" in result.causes
    assert result.facts["positive_https_only"]["setup_established"] is False
    not_dispatched = assess_https_listener(_toggle(False, True), None, None, None, None)
    assert not_dispatched.outcome_unknown is False


def test_https_retrieval_with_https_disabled_contradicts_the_model():
    """The plan's stop condition: a marker fetched in HTTPS mode with HTTPS off."""
    result = assess_https_listener(
        _toggle(False, True),
        _row(ObservationFact.OBSERVED),
        _row(ObservationFact.CONTRADICTED),
        _toggle(False, False),
        _row(ObservationFact.OBSERVED),
    )
    assert result.conclusion is CONTRADICTED
    assert "negative_https:listener_served_while_read_back_as_disabled" in result.causes


def test_timeouts_and_unconfirmed_states_are_never_negatives():
    """A deadline, an unconfirmed mode or an unconfirmed toggle is inconclusive."""
    timeout = _row(ObservationFact.INCONCLUSIVE, "no_response_within_deadline")
    mode = _row(ObservationFact.CONTRADICTED, "https_mode_not_confirmed")
    result = assess_https_listener(
        _toggle(False, True),
        _row(ObservationFact.OBSERVED),
        timeout,
        _toggle(False, False),
        mode,
    )
    assert result.conclusion is INCONCLUSIVE
    controls = result.facts
    assert controls["negative_http_mode_http_disabled"]["conclusion"] == "inconclusive"
    assert (
        controls["negative_https_mode_https_disabled"]["conclusion"] == "inconclusive"
    )
    unconfirmed = assess_https_listener(
        _toggle(False, True),
        _row(ObservationFact.OBSERVED),
        _row(ObservationFact.CONTRADICTED),
        _toggle(False, True),
        _row(ObservationFact.OBSERVED),
    )
    assert unconfirmed.conclusion is INCONCLUSIVE


def test_negatives_without_a_positive_control_have_no_discriminating_power():
    """If the positive never retrieved the marker, fresh failures prove nothing."""
    result = assess_https_listener(
        _toggle(False, True),
        _row(ObservationFact.CONTRADICTED),
        _row(ObservationFact.CONTRADICTED),
        _toggle(False, False),
        _row(ObservationFact.CONTRADICTED),
    )
    assert result.conclusion is CONTRADICTED
    assert "positive:marked_page_returned_other_content" in result.causes


def _resolvers(value, unset="0.0.0.0") -> ProbeReading:
    return _reading(
        "client_resolvers",
        {
            "clients": {
                "PC1": {"found": True, "value": value, "error": ""},
                "PC2": {"found": True, "value": unset, "error": ""},
            }
        },
    )


def test_client_resolver_compares_with_its_e5_intent_under_attribution():
    """Equal supports; a different value after an accepted dispatch contradicts."""
    kwargs = {
        "configured_client": "PC1",
        "unset_client": "PC2",
        "intended": "192.0.2.10",
    }
    ok = assess_client_resolver(
        _resolvers("192.0.2.10"), e5_dispatch_accepted=True, **kwargs
    )
    assert ok.conclusion is SUPPORTED
    assert ok.facts["unset_client_representation"]["value"] == "0.0.0.0"
    other = assess_client_resolver(
        _resolvers("10.0.0.1"), e5_dispatch_accepted=True, **kwargs
    )
    assert other.conclusion is CONTRADICTED
    unattributed = assess_client_resolver(
        _resolvers("10.0.0.1"), e5_dispatch_accepted=False, **kwargs
    )
    assert unattributed.conclusion is INCONCLUSIVE
    lost = assess_client_resolver(
        _reading("client_resolvers", observed=False),
        e5_dispatch_accepted=True,
        **kwargs,
    )
    assert lost.conclusion is INCONCLUSIVE


# -- promotion evidence ----------------------------------------------------------


def _record(**changes) -> QualificationRecord:
    record = QualificationRecord(
        run_id="r1",
        stage=QualificationStage.Q0,
        execution_mode=ExecutionMode.LIVE,
        created_at=datetime(2026, 9, 18, tzinfo=UTC),
        source=SourceIdentity(executed_sha=SHA, clean=True),
        environment=EnvironmentIdentity(observed_build=BUILD),
        transport=TransportIdentity(channel="file"),
        budget=BudgetRecord(
            max_operations=20,
            max_seconds=300,
            reserve_operations=5,
            reserve_seconds=60,
            planned_minimum_operations=19,
        ),
        restoration_proven=True,
        outcome=QualificationOutcome.COMPLETED,
    )
    return record.model_copy(update=changes)


def test_only_a_completed_live_record_at_the_exact_sha_can_be_evidence():
    """Offline, other-SHA, other-build, other-channel or unrestored records refuse."""
    arguments = {
        "stage": QualificationStage.Q0,
        "executed_sha": SHA,
        "build": BUILD,
        "channel": "file",
    }
    assert promotion_evidence_refusal(_record(), **arguments) == ""
    refusing = [
        _record(execution_mode=ExecutionMode.OFFLINE_SIMULATION),
        _record(outcome=QualificationOutcome.STOPPED),
        _record(stage=QualificationStage.Q1),
        _record(source=SourceIdentity(executed_sha="d" * 40, clean=True)),
        _record(source=SourceIdentity(executed_sha=SHA, clean=False)),
        _record(environment=EnvironmentIdentity(observed_build="9.0.1.0859")),
        _record(transport=TransportIdentity(channel="http")),
        _record(restoration_proven=False),
    ]
    for record in refusing:
        assert promotion_evidence_refusal(record, **arguments)
    later_sha = dict(arguments, executed_sha="e" * 40)
    assert "never relabeled" in promotion_evidence_refusal(_record(), **later_sha)
