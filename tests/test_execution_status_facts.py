"""The observation facts, the canonical decision, and the journal rule.

The decision-table test asserts SAFETY PREDICATES, not equality with a copy of
the table. A copy would pass by construction and would prove only that two
transcriptions agree. What has to hold is that no tuple can reach a stronger
claim than its weakest fact supports.
"""

from __future__ import annotations

import itertools
import json

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConvergenceOutcome,
    FieldVerificationStatus,
    MutationResidue,
    RuntimeActionMutation,
    decide_mutation,
    mutation_execution_status,
    sanitized_mutation_snapshot,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    ApplicationExecutionJournal,
    CompensationStatus,
    DirtyState,
    DispatchFact,
    ExecutionJournalEntry,
    FootprintFact,
    MutationDisposition,
    OperationSemantics,
    PostconditionFact,
    ResultFact,
    TransitionFact,
    journal_from_action_results,
    satisfies_apply_dependency,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceActionType,
    ServiceEvidenceKind,
    ServiceType,
    ServiceVerificationKind,
)
from packet_tracer_mcp.infrastructure.execution.file_bridge import RequestDisposition

# -- 1. presentation equivalence of the StrEnum conversion ---------------

_CONVERTED_ENUMS = (
    OperationSemantics,
    MutationDisposition,
    DirtyState,
    CompensationStatus,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    FieldVerificationStatus,
    ConvergenceOutcome,
    RequestDisposition,
    # Converted in S1, because S1 touches the two modules and therefore owns
    # their Ruff state. Each one is public vocabulary that is interpolated
    # into messages and persisted records, so each is asserted here.
    ConfigurationActionType,
    ConfigurationIssueSeverity,
    ConfigurationIssueCode,
    VerificationKind,
    ServiceType,
    ServiceActionType,
    ServiceEvidenceKind,
    ServiceVerificationKind,
)


@pytest.mark.parametrize("enum", _CONVERTED_ENUMS, ids=lambda item: item.__name__)
def test_the_strenum_form_presents_exactly_as_the_mixin_form_did(enum):
    """`StrEnum` plus `__str__ = Enum.__str__` must be indistinguishable.

    A plain `StrEnum` changes `str()` and `format()` from `Class.MEMBER` to the
    raw value, which would silently rewrite every log line, message and
    persisted string that interpolated a member. The precedent
    (`ImportIsolationState`) restores the mixin presentation, and this asserts
    it per enum rather than trusting one example.
    """
    for member in enum:
        assert str(member) == f"{enum.__name__}.{member.name}"
        assert format(member) == f"{enum.__name__}.{member.name}"
        assert f"{member}" == f"{enum.__name__}.{member.name}"
        assert json.dumps(member) == json.dumps(member.value)
        assert member == member.value
        assert {member: 1}[member.value] == 1
        assert enum(member.value) is member
        assert "prefix:" + member == "prefix:" + member.value


def test_a_converted_enum_round_trips_through_pydantic_unchanged():
    """`model_dump(mode="json")` must still produce the bare values."""
    mutation = RuntimeActionMutation(
        action_id="a",
        applied=True,
        operation=OperationSemantics.ENSURE_PRESENT,
        disposition=MutationDisposition.REASSERTED,
        failure_code=ConfigurationFailureCode.OUTCOME_UNKNOWN,
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.UNCHANGED,
        footprint=FootprintFact.COVERED,
        attempted=True,
    )
    dumped = mutation.model_dump(mode="json")

    assert dumped["operation"] == "ensure_present"
    assert dumped["disposition"] == "reasserted"
    assert dumped["failure_code"] == "outcome_unknown"
    assert dumped["dispatch"] == "accepted"
    assert dumped["footprint"] == "covered"
    assert RuntimeActionMutation.model_validate(dumped) == mutation


# -- 2. the decision table: safety predicates ----------------------------

_LEGACY_TUPLE = (
    DispatchFact.UNSPECIFIED,
    ResultFact.NOT_APPLICABLE,
    PostconditionFact.NOT_APPLICABLE,
    TransitionFact.NOT_APPLICABLE,
    FootprintFact.NOT_APPLICABLE,
    None,
)


def _mutation(facts, applied, *, disposition=MutationDisposition.UNKNOWN, cause=""):
    dispatch, result, postcondition, transition, footprint, attempted = facts
    return RuntimeActionMutation(
        action_id="a",
        applied=applied,
        disposition=disposition,
        dispatch=dispatch,
        result=result,
        postcondition=postcondition,
        transition=transition,
        footprint=footprint,
        attempted=attempted,
        cause=cause,
    )


def _every_tuple():
    """Every combination of the seven decision inputs."""
    return itertools.product(
        DispatchFact,
        ResultFact,
        PostconditionFact,
        TransitionFact,
        FootprintFact,
        (True, False, None),
        (True, False),
    )


def test_the_full_product_of_facts_is_decided_without_raising():
    """Every one of the seven-input combinations reaches a decision."""
    count = 0
    for *facts, applied in _every_tuple():
        decision = decide_mutation(_mutation(tuple(facts), applied))
        assert isinstance(decision.row, str) and decision.row
        count += 1

    assert count == (
        len(DispatchFact)
        * len(ResultFact)
        * len(PostconditionFact)
        * len(TransitionFact)
        * len(FootprintFact)
        * 3
        * 2
    )


def test_the_frontier_opens_only_on_a_validated_satisfied_postcondition():
    """Nothing but a validated SATISFIED row, or a legacy row, may proceed.

    This is the predicate that makes the frontier safe. An UNOBSERVED or
    UNSATISFIED postcondition, and any tuple the table refuses, must not let a
    dependent action run on the assumption that the state is in place.
    """
    for *facts, applied in _every_tuple():
        facts = tuple(facts)
        decision = decide_mutation(_mutation(facts, applied))
        if not decision.frontier:
            continue
        if facts == _LEGACY_TUPLE:
            assert decision.row == "16"
            assert decision.frontier is satisfies_apply_dependency(decision.status)
            continue
        assert facts[2] is PostconditionFact.SATISFIED, (facts, applied)
        assert decision.row != "inconsistent"


def test_every_unlisted_tuple_is_unknown_closed_and_sticky():
    """An inadmissible tuple claims nothing and keeps the doubt.

    Including the ones the table names explicitly: `applied` disagreeing with
    `dispatch is ACCEPTED`, SATISFIED under a dispatch that was never
    accepted, and CORRELATED without acceptance.
    """
    for *facts, applied in _every_tuple():
        decision = decide_mutation(_mutation(tuple(facts), applied))
        if decision.row != "inconsistent":
            continue
        assert decision.status is ActionExecutionStatus.UNKNOWN
        assert decision.disposition is MutationDisposition.UNKNOWN
        assert decision.failure_code is ConfigurationFailureCode.OUTCOME_UNKNOWN
        assert decision.residue is MutationResidue.UNKNOWN
        assert decision.frontier is False
        assert decision.sticky is True
        assert decision.cause == "inconsistent_facts"


@pytest.mark.parametrize(
    "facts",
    [
        # `applied` disagrees with an ACCEPTED dispatch.
        (
            DispatchFact.ACCEPTED,
            ResultFact.CORRELATED,
            PostconditionFact.SATISFIED,
            TransitionFact.CHANGED,
            FootprintFact.COVERED,
            True,
        ),
    ],
)
def test_a_satisfied_postcondition_with_applied_false_stays_inconsistent(facts):
    """TD-12.1's counterexample must not become row 12.

    The tuple is contradictory: the channel is said to have accepted the
    dispatch, yet the producer also reports that the payload was not applied.
    Trusting the optimistic half would promote it to a changed, satisfied
    mutation with an open frontier.
    """
    decision = decide_mutation(_mutation(facts, applied=False))

    assert decision.row == "inconsistent"
    assert decision.status is ActionExecutionStatus.UNKNOWN
    assert decision.frontier is False
    assert decision.sticky is True
    # The received value is still on the mutation as a diagnostic, and it
    # granted nothing.
    assert _mutation(facts, applied=False).postcondition is PostconditionFact.SATISFIED


@pytest.mark.parametrize(
    ("facts", "applied", "expected"),
    [
        (
            (
                DispatchFact.NOT_SUBMITTED,
                ResultFact.CORRELATED,
                PostconditionFact.SATISFIED,
                TransitionFact.CHANGED,
                FootprintFact.COVERED,
                True,
            ),
            True,
            "inconsistent",
        ),
        (
            (
                DispatchFact.ACCEPTED,
                ResultFact.ENGINE_ERROR,
                PostconditionFact.SATISFIED,
                TransitionFact.UNCHANGED,
                FootprintFact.COVERED,
                True,
            ),
            True,
            "inconsistent",
        ),
    ],
)
def test_the_named_countermodels_are_refused(facts, applied, expected):
    """The three tuples the plan names as contradictions stay contradictions."""
    assert decide_mutation(_mutation(facts, applied)).row == expected


def test_row_15_is_unknown_with_session_failed():
    """A runtime that raised has no dispatch fact, and FAILED would lie."""
    decision = decide_mutation(
        _mutation(
            (
                DispatchFact.UNSPECIFIED,
                ResultFact.NOT_APPLICABLE,
                PostconditionFact.UNOBSERVED,
                TransitionFact.UNOBSERVED,
                FootprintFact.NOT_APPLICABLE,
                None,
            ),
            applied=False,
            cause="exception:RuntimeError",
        )
    )

    assert decision.row == "15"
    assert decision.status is ActionExecutionStatus.UNKNOWN
    assert decision.failure_code is ConfigurationFailureCode.SESSION_FAILED
    assert decision.cause == "exception:RuntimeError"
    assert decision.sticky is True
    assert decision.frontier is False


def test_the_sticky_rows_are_exactly_the_ones_the_table_names():
    """Rows 3 to 8, 10, 15, 19 and every inconsistent tuple, and no others."""
    sticky_rows = set()
    for *facts, applied in _every_tuple():
        decision = decide_mutation(_mutation(tuple(facts), applied))
        if decision.sticky:
            sticky_rows.add(decision.row)

    assert sticky_rows == {
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "10",
        "15",
        "19",
        "inconsistent",
    }


def test_a_single_entry_journal_is_clean_only_without_residue_or_stickiness():
    """CLEAN must require both: nothing unobserved and nothing in doubt.

    Built through the real journal builder, so the disposition fallback and
    the dirty-state rule participate exactly as they do in production.
    """
    for *facts, applied in _every_tuple():
        facts = tuple(facts)
        decision = decide_mutation(_mutation(facts, applied))
        journal = journal_from_action_results(
            plan_id="p",
            deployment_id="d",
            actions=[_FakeAction("a")],
            results=[
                ActionApplicationResult(
                    action_id="a",
                    status=decision.status,
                    failure_code=decision.failure_code,
                    disposition=decision.disposition,
                    residual_change=decision.residue is MutationResidue.CHANGED,
                    cause=decision.cause,
                    dispatch=facts[0],
                    result=facts[1],
                    postcondition=facts[2],
                    transition=facts[3],
                    footprint=facts[4],
                    attempted=facts[5],
                )
            ],
        )
        if journal.dirty_state is not DirtyState.CLEAN:
            continue
        assert decision.residue is MutationResidue.NONE, (facts, applied)
        assert decision.sticky is False, (facts, applied)


def test_the_unknown_disposition_of_the_residue_rows_survives_the_builder():
    """Rows 9, 10, 18 and 19 must stay UNKNOWN through the real builder.

    The builder falls back to `disposition_from_status` for an UNKNOWN
    disposition. APPLIED and PARTIAL are deliberately absent from that map, so
    the fallback cannot turn an unobserved residue into a named mutation -- and
    that is what keeps `dirty_state` UNKNOWN for these rows.
    """
    seen = set()
    for *facts, applied in _every_tuple():
        facts = tuple(facts)
        decision = decide_mutation(_mutation(facts, applied))
        if decision.row not in {"9", "10", "18", "19"}:
            continue
        seen.add(decision.row)
        journal = journal_from_action_results(
            plan_id="p",
            deployment_id="d",
            actions=[_FakeAction("a")],
            results=[
                ActionApplicationResult(
                    action_id="a",
                    status=decision.status,
                    disposition=decision.disposition,
                    cause=decision.cause,
                )
            ],
        )

        assert decision.disposition is MutationDisposition.UNKNOWN
        assert journal.entries[0].disposition is MutationDisposition.UNKNOWN
        assert journal.dirty_state is DirtyState.UNKNOWN

    assert seen == {"9", "10", "18", "19"}


class _FakeAction:
    """The minimal action shape the journal builder reads."""

    def __init__(self, identifier: str) -> None:
        """Name one action with no inverse."""
        self.id = identifier
        self.operation = OperationSemantics.SET_VALUE
        self.inverse_action_id = ""
        self.compensation_available = False


# -- 3. the legacy row reproduces the baseline mapping -------------------


def _baseline_mutation_execution_status(mutation):
    """Reproduce the baseline rule verbatim, as the oracle for legacy rows.

    Copied from `configuration_runtime.py` at `6263344`. It is the oracle for
    rows whose every new fact is at its default, and for nothing else: for a
    fact-bearing row there IS no baseline answer to compare against.
    """
    if not mutation.applied:
        return ActionExecutionStatus.FAILED
    if mutation.disposition is MutationDisposition.NO_OP:
        return ActionExecutionStatus.NO_OP
    if mutation.disposition is MutationDisposition.REASSERTED:
        return ActionExecutionStatus.REASSERTED
    return ActionExecutionStatus.APPLIED


@pytest.mark.parametrize("disposition", list(MutationDisposition))
@pytest.mark.parametrize("applied", [True, False])
def test_a_legacy_row_maps_exactly_as_the_baseline(disposition, applied):
    """Every legacy row keeps the baseline status, disposition and frontier."""
    mutation = RuntimeActionMutation(
        action_id="a", applied=applied, disposition=disposition
    )
    decision = decide_mutation(mutation)
    expected = _baseline_mutation_execution_status(mutation)

    assert decision.row == "16"
    assert decision.status is expected
    assert mutation_execution_status(mutation) is expected
    assert decision.disposition is disposition
    assert decision.residue is MutationResidue.NONE
    assert decision.sticky is False
    assert decision.frontier is satisfies_apply_dependency(expected)


def test_a_legacy_row_keeps_a_runtime_supplied_failure_code():
    """Only NONE is replaced; a stated code is never discarded."""
    stated = decide_mutation(
        RuntimeActionMutation(
            action_id="a",
            applied=False,
            failure_code=ConfigurationFailureCode.TARGET_NOT_FOUND,
        )
    )
    unstated_failure = decide_mutation(
        RuntimeActionMutation(action_id="a", applied=False)
    )
    unstated_success = decide_mutation(
        RuntimeActionMutation(action_id="a", applied=True)
    )

    assert stated.failure_code is ConfigurationFailureCode.TARGET_NOT_FOUND
    assert unstated_failure.failure_code is ConfigurationFailureCode.APPLICATION_FAILED
    assert unstated_success.failure_code is ConfigurationFailureCode.NONE


# -- 4. the journal dirty-state table ------------------------------------


def _baseline_derive_dirty_state(entries):
    """Reproduce the baseline dirty-state rule, as the oracle for one half.

    Copied from `execution.py` at `6263344`. It is the oracle ONLY for
    `residual_change=False`, because that is the half of the input space the
    baseline could express. For `residual_change=True` there is no baseline
    answer, and the assertions below state the new rule directly.
    """
    if not entries:
        return DirtyState.CLEAN
    if any(item.disposition is MutationDisposition.UNKNOWN for item in entries):
        return DirtyState.UNKNOWN
    failed = any(item.disposition is MutationDisposition.FAILED for item in entries)
    mutations = [
        item
        for item in entries
        if item.disposition
        in {MutationDisposition.CHANGED, MutationDisposition.REASSERTED}
    ]
    if not failed or not mutations:
        return DirtyState.CLEAN
    if all(item.inverse_available for item in mutations):
        return DirtyState.DIRTY_RECOVERABLE
    return DirtyState.DIRTY_UNRECOVERABLE


def _journal_of(disposition, *, inverse, residual):
    journal = ApplicationExecutionJournal(plan_id="p")
    journal.append(
        ExecutionJournalEntry(
            ordinal=1,
            action_id="a",
            operation=OperationSemantics.SET_VALUE,
            disposition=disposition,
            inverse_available=inverse,
            residual_change=residual,
        )
    )
    return journal


@pytest.mark.parametrize("disposition", list(MutationDisposition))
@pytest.mark.parametrize("inverse", [True, False])
def test_without_an_observed_residue_the_dirty_state_is_the_baseline(
    disposition, inverse
):
    """`residual_change=False` must reproduce the baseline exactly."""
    journal = _journal_of(disposition, inverse=inverse, residual=False)

    assert journal.dirty_state is _baseline_derive_dirty_state(journal.entries)


@pytest.mark.parametrize("disposition", list(MutationDisposition))
@pytest.mark.parametrize("inverse", [True, False])
def test_a_failed_entry_with_an_observed_residue_counts_as_a_mutation(
    disposition, inverse
):
    """The one added rule, and it changes nothing for any other disposition."""
    journal = _journal_of(disposition, inverse=inverse, residual=True)
    baseline = _baseline_derive_dirty_state(journal.entries)

    if disposition is MutationDisposition.FAILED:
        assert journal.dirty_state is (
            DirtyState.DIRTY_RECOVERABLE if inverse else DirtyState.DIRTY_UNRECOVERABLE
        )
        assert baseline is DirtyState.CLEAN
    else:
        assert journal.dirty_state is baseline


def test_an_unknown_entry_stays_unknown_whatever_the_residual_flag_says():
    """Unknown residue is carried by the disposition, not by the flag.

    `residual_change=False` is the ABSENCE of an observation. If it could turn
    an UNKNOWN entry clean, "we did not look" would become "nothing changed".
    """
    for residual in (True, False):
        journal = _journal_of(
            MutationDisposition.UNKNOWN, inverse=True, residual=residual
        )

        assert journal.dirty_state is DirtyState.UNKNOWN


def test_transport_uncertainty_cannot_be_cleared_by_a_later_cleanup():
    """A sticky flag survives a successful compensation."""
    journal = _journal_of(MutationDisposition.CHANGED, inverse=True, residual=False)
    journal.mark_transport_unknown("transport_unknown: a")
    journal.mark_cleanup(CompensationStatus.SUCCEEDED)

    assert journal.transport_unknown is True
    assert journal.dirty_state is DirtyState.UNKNOWN


# -- 5. JSON compatibility ------------------------------------------------


def test_a_baseline_shaped_result_still_validates_to_the_new_defaults():
    """Input JSON written before the facts existed must keep validating.

    This is the shape `cp_scale_stage_evidence.py` persists: the model dumped
    to JSON. A stored record from the baseline has none of the new keys, and it
    must stay a legacy record rather than fail or acquire invented facts.
    """
    baseline_shaped = {
        "action_id": "a",
        "status": "applied",
        "failure_code": "none",
        "message": "applied",
        "batch_id": "HQ:20",
        "operation": "set_value",
        "disposition": "unknown",
    }

    result = ActionApplicationResult.model_validate(baseline_shaped)

    assert result.dispatch is DispatchFact.UNSPECIFIED
    assert result.result is ResultFact.NOT_APPLICABLE
    assert result.postcondition is PostconditionFact.NOT_APPLICABLE
    assert result.transition is TransitionFact.NOT_APPLICABLE
    assert result.footprint is FootprintFact.NOT_APPLICABLE
    assert result.attempted is None
    assert result.residual_change is False
    assert result.cause == ""
    # TD-12.1: no snapshot, so no fact-bearing authority. Nothing reconstructs
    # `applied` for it, and it is not even a field on this model.
    assert result.received_mutation is None
    assert not hasattr(result, "applied")


def test_a_baseline_shaped_journal_entry_still_validates_to_the_new_defaults():
    """The same for the journal entry the evidence writer persists."""
    entry = ExecutionJournalEntry.model_validate(
        {
            "ordinal": 1,
            "action_id": "a",
            "operation": "set_value",
            "disposition": "changed",
            "batch_id": "",
            "inverse_action_id": "",
            "inverse_available": False,
            "compensation_status": "not_available",
            "message": "",
        }
    )

    assert entry.dispatch is DispatchFact.UNSPECIFIED
    assert entry.result is ResultFact.NOT_APPLICABLE
    assert entry.residual_change is False
    assert entry.cause == ""


def test_the_journal_compact_summary_is_byte_identical_for_a_legacy_row():
    """The compact summary shape is frozen; new facts live in the full JSON.

    A consumer reading the compact summary was written against these exact
    keys. Adding to it would be a silent contract change, so the facts are
    reachable through `model_dump` and the summary is unchanged.
    """
    journal = _journal_of(MutationDisposition.CHANGED, inverse=True, residual=False)

    assert json.dumps(journal.compact_summary(), sort_keys=True) == json.dumps(
        {
            "plan_id": "p",
            "deployment_id": "",
            "attempted": 1,
            "counts": {"changed": 1},
            "dirty_state": "clean",
            "cleanup_status": "not_attempted",
            "preflight_errors": [],
        },
        sort_keys=True,
    )
    assert "dispatch" in journal.entries[0].model_dump(mode="json")


# -- 6. TD-12.1, at DTO level --------------------------------------------


def test_the_snapshot_is_the_input_and_re_deciding_it_gives_the_same_answer():
    """The retained snapshot must re-decide identically, field for field."""
    mutation = RuntimeActionMutation(
        action_id="a",
        applied=True,
        disposition=MutationDisposition.UNKNOWN,
        failure_code=ConfigurationFailureCode.NONE,
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.CHANGED,
        footprint=FootprintFact.PARTIAL,
        attempted=True,
        cause="footprint_partial:dns_a_record_table",
    )
    decision = decide_mutation(mutation)
    snapshot = sanitized_mutation_snapshot(mutation)

    assert snapshot.applied is True
    assert snapshot.disposition is mutation.disposition
    assert snapshot.failure_code is mutation.failure_code
    assert snapshot.cause == mutation.cause
    assert snapshot.dispatch is mutation.dispatch
    assert snapshot.result is mutation.result
    assert snapshot.postcondition is mutation.postcondition
    assert snapshot.transition is mutation.transition
    assert snapshot.footprint is mutation.footprint
    assert snapshot.attempted is mutation.attempted
    assert decide_mutation(snapshot) == decision


def test_mutating_the_original_after_application_cannot_change_the_snapshot():
    """Keep the classified input safe from a later edit of the original.

    The copy is defensive precisely so that a producer mutating its own object
    after application cannot rewrite what the decision was given.
    """
    mutation = RuntimeActionMutation(
        action_id="a",
        applied=False,
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.CHANGED,
        footprint=FootprintFact.COVERED,
        attempted=True,
    )
    snapshot = sanitized_mutation_snapshot(mutation)
    mutation.applied = True
    mutation.postcondition = PostconditionFact.UNSATISFIED

    assert snapshot.applied is False
    assert snapshot.postcondition is PostconditionFact.SATISFIED
    assert decide_mutation(snapshot).row == "inconsistent"


def test_the_snapshot_bounds_free_text_without_dropping_a_field():
    """A long message is bounded; no field is removed or renamed."""
    mutation = RuntimeActionMutation(
        action_id="a",
        applied=True,
        message="x" * 5000,
        cause="y" * 5000,
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.CHANGED,
        footprint=FootprintFact.COVERED,
        attempted=True,
    )
    snapshot = sanitized_mutation_snapshot(mutation)

    assert len(snapshot.message) < 5000
    assert len(snapshot.cause) < 5000
    assert set(snapshot.model_dump()) == set(mutation.model_dump())


def test_the_inconsistent_cause_is_never_the_producers_error_string():
    """TD-12.1: an incidental message must not hide `inconsistent_facts`."""
    mutation = RuntimeActionMutation(
        action_id="a",
        applied=False,
        cause="exception:ValueError",
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.CHANGED,
        footprint=FootprintFact.COVERED,
        attempted=True,
    )
    decision = decide_mutation(mutation)

    assert decision.cause == "inconsistent_facts"
    assert sanitized_mutation_snapshot(mutation).cause == "exception:ValueError"


def test_a_row_cause_composes_the_canonical_token_with_the_producer_detail():
    """`rejected:<code>` and `post_read_failed` (+ call_error), composed once."""
    rejected = decide_mutation(
        _mutation(
            (
                DispatchFact.REJECTED,
                ResultFact.NOT_APPLICABLE,
                PostconditionFact.NOT_APPLICABLE,
                TransitionFact.NOT_APPLICABLE,
                FootprintFact.NOT_APPLICABLE,
                None,
            ),
            applied=False,
            cause="409",
        )
    )
    already_detailed = decide_mutation(
        _mutation(
            (
                DispatchFact.REJECTED,
                ResultFact.NOT_APPLICABLE,
                PostconditionFact.NOT_APPLICABLE,
                TransitionFact.NOT_APPLICABLE,
                FootprintFact.NOT_APPLICABLE,
                None,
            ),
            applied=False,
            cause="rejected:409",
        )
    )
    post_read = decide_mutation(
        _mutation(
            (
                DispatchFact.ACCEPTED,
                ResultFact.CORRELATED,
                PostconditionFact.UNOBSERVED,
                TransitionFact.UNOBSERVED,
                FootprintFact.COVERED,
                True,
            ),
            applied=True,
            cause="TypeError: not a function",
        )
    )

    assert rejected.cause == "rejected:409"
    assert already_detailed.cause == "rejected:409"
    assert post_read.row == "8"
    assert post_read.cause == "post_read_failed:TypeError: not a function"


def test_the_snapshot_retains_the_setter_error_beside_the_canonical_cause():
    """Two different meanings, both preserved, neither standing for the other.

    A row can have a canonical reason of its own -- `pre_read_failed`,
    `footprint_partial:<scope>` -- and a setter diagnostic at the same time.
    The adapter had to choose, so it dropped the diagnostic, and the snapshot
    could not recover what the adapter had already removed (R5).
    """
    mutation = RuntimeActionMutation(
        action_id="a",
        applied=True,
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.UNOBSERVED,
        footprint=FootprintFact.COVERED,
        attempted=True,
        call_error="TypeError: setEnable is not a function",
    )
    decision = decide_mutation(mutation)
    snapshot = sanitized_mutation_snapshot(mutation)

    assert decision.cause == "pre_read_failed"
    assert snapshot.call_error == "TypeError: setEnable is not a function"
    assert decide_mutation(snapshot) == decision


def test_the_setter_error_never_classifies_and_never_authorizes():
    """A producer diagnostic must not reach the decision at all."""
    facts = dict(
        action_id="a",
        applied=False,
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.CHANGED,
        footprint=FootprintFact.COVERED,
        attempted=True,
    )
    silent = decide_mutation(RuntimeActionMutation(**facts))
    noisy = decide_mutation(
        RuntimeActionMutation(**facts, call_error="stub failure: setEnable")
    )

    assert silent == noisy
    assert noisy.cause == "inconsistent_facts"
    assert noisy.frontier is False


def test_the_snapshot_bounds_the_setter_error_too():
    """Every free-text field that reaches a stored record is bounded."""
    mutation = RuntimeActionMutation(
        action_id="a",
        applied=True,
        call_error="z" * 5000,
        dispatch=DispatchFact.ACCEPTED,
        result=ResultFact.CORRELATED,
        postcondition=PostconditionFact.SATISFIED,
        transition=TransitionFact.CHANGED,
        footprint=FootprintFact.COVERED,
        attempted=True,
    )
    snapshot = sanitized_mutation_snapshot(mutation)

    assert len(snapshot.call_error) < 5000
    assert set(snapshot.model_dump()) == set(mutation.model_dump())


def test_a_mutation_that_states_only_a_setter_error_is_still_legacy():
    """The legacy fact tuple decides row 16; a new field does not disturb it."""
    decision = decide_mutation(
        RuntimeActionMutation(
            action_id="a",
            applied=True,
            call_error="stub failure: setEnable",
        )
    )

    assert decision.row == "16"
