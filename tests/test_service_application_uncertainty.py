"""E6 application under uncertainty: the decision, the snapshot, the frontier.

Everything here runs through the real `ServiceApplicator`, the real journal
builder, the real evidence adapter and a real Pydantic round-trip. The runtime
is a stub, but the stub reports ROWS OF FACTS and the applicator's own code
decides what they mean -- the test never supplies a status or a disposition.
"""

from __future__ import annotations

import pytest
from test_enterprise_services import _fixture
from test_service_application import FakeServiceRuntime

from packet_tracer_mcp.application.use_cases.apply_services import (
    VERIFICATION_EFFECT_CLASSES,
    ServiceApplicator,
)
from packet_tracer_mcp.application.use_cases.compile_services import (
    compile_enterprise_services,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    MutationResidue,
    RuntimeActionMutation,
    decide_mutation,
)
from packet_tracer_mcp.domain.enterprise.models.evidence import (
    ObservationStatus,
    VerificationStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DirtyState,
    DispatchFact,
    FootprintFact,
    MutationDisposition,
    PostconditionFact,
    ResultFact,
    TransitionFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
    ServiceApplicationResult,
)


def _compiled():
    enterprise, topology, configuration, capabilities = _fixture()
    result = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities
    )
    assert result.is_valid
    return result.plan, capabilities


def _foundation(plan):
    return {
        requirement.configuration_action_id: ActionExecutionStatus.VERIFIED
        for requirement in plan.foundational_requirements
    }


class _FactRuntime(FakeServiceRuntime):
    """A runtime that reports observation facts instead of a verdict."""

    def __init__(self, facts, *, raises=None, omit=()):
        """Bind one fact template, an optional exception, and ids to omit."""
        super().__init__()
        self._facts = facts
        self._raises = raises
        self._omit = set(omit)
        self.sent: list[RuntimeActionMutation] = []

    def apply_actions(self, actions):
        """Report the bound facts for every action except the omitted ones."""
        self.apply_calls.append([item.id for item in actions])
        if self._raises is not None:
            raise self._raises
        mutations = []
        for item in actions:
            if item.id in self._omit:
                continue
            mutation = RuntimeActionMutation(
                action_id=item.id,
                operation=item.operation,
                batch_id=f"{item.host_device_name}:{int(item.phase)}",
                **self._facts,
            )
            mutations.append(mutation)
        self.sent.extend(mutations)
        return mutations


_ACCEPTED_SATISFIED_CHANGED = {
    "applied": True,
    "dispatch": DispatchFact.ACCEPTED,
    "result": ResultFact.CORRELATED,
    "postcondition": PostconditionFact.SATISFIED,
    "transition": TransitionFact.CHANGED,
    "footprint": FootprintFact.COVERED,
    "attempted": True,
}

_ACCEPTED_ENGINE_ERROR = {
    "applied": True,
    "dispatch": DispatchFact.ACCEPTED,
    "result": ResultFact.ENGINE_ERROR,
    "postcondition": PostconditionFact.UNOBSERVED,
    "transition": TransitionFact.UNOBSERVED,
    "footprint": FootprintFact.NOT_APPLICABLE,
    "attempted": None,
    "cause": "engine_error",
}

_PARTIAL_FOOTPRINT_SATISFIED = {
    "applied": True,
    "dispatch": DispatchFact.ACCEPTED,
    "result": ResultFact.CORRELATED,
    "postcondition": PostconditionFact.SATISFIED,
    "transition": TransitionFact.CHANGED,
    "footprint": FootprintFact.PARTIAL,
    "attempted": True,
    "cause": "footprint_partial:dns_a_record_table",
}

_PRE_READ_FAILED_UNSATISFIED = {
    "applied": True,
    "dispatch": DispatchFact.ACCEPTED,
    "result": ResultFact.CORRELATED,
    "postcondition": PostconditionFact.UNSATISFIED,
    "transition": TransitionFact.UNOBSERVED,
    "footprint": FootprintFact.COVERED,
    "attempted": True,
}

_INCONSISTENT = {
    "applied": False,
    "dispatch": DispatchFact.ACCEPTED,
    "result": ResultFact.CORRELATED,
    "postcondition": PostconditionFact.SATISFIED,
    "transition": TransitionFact.CHANGED,
    "footprint": FootprintFact.COVERED,
    "attempted": True,
    "cause": "exception:SomeIncidentalError",
}


def _apply(runtime, *, direct_readback=None):
    plan, capabilities = _compiled()
    if direct_readback is not None:
        for profile in capabilities.values():
            if hasattr(profile, "direct_readback_support"):
                profile.direct_readback_support = direct_readback
    return (
        ServiceApplicator(runtime).apply(
            plan,
            actual_source_topology_hash=plan.source_topology_hash,
            actual_source_configuration_hash=plan.source_configuration_hash,
            foundational_statuses=_foundation(plan),
            capabilities=capabilities,
        ),
        plan,
    )


# -- 1. one decision per row, and the row carries what it received -------


def test_a_satisfied_covered_row_is_applied_changed_and_clean():
    """The happy path: a read-back postcondition and an observed change."""
    result, _ = _apply(_FactRuntime(_ACCEPTED_SATISFIED_CHANGED))

    assert all(
        item.status is ActionExecutionStatus.APPLIED for item in result.action_results
    )
    assert all(
        item.disposition is MutationDisposition.CHANGED
        for item in result.action_results
    )
    assert all(item.residual_change is False for item in result.action_results)
    assert result.dirty_state is DirtyState.CLEAN
    assert result.limitations == []
    assert result.execution_journal is not None
    assert result.execution_journal.transport_unknown is False


def test_an_engine_error_is_applied_unknown_and_sticky_and_blocks_dependents():
    """Accepted plus engine error: the dispatch is proven, the effect is not."""
    result, plan = _apply(_FactRuntime(_ACCEPTED_ENGINE_ERROR))
    by_id = {item.action_id: item for item in result.action_results}
    dependent_ids = [item.id for item in plan.actions if item.depends_on]

    assert dependent_ids
    first = next(item for item in plan.actions if not item.depends_on)
    assert by_id[first.id].status is ActionExecutionStatus.APPLIED
    assert by_id[first.id].disposition is MutationDisposition.UNKNOWN
    assert by_id[first.id].failure_code is ConfigurationFailureCode.OUTCOME_UNKNOWN
    for identifier in dependent_ids:
        assert by_id[identifier].status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        assert "prerequisite_outcome_unknown:" in by_id[identifier].message
    assert result.execution_journal is not None
    assert result.execution_journal.transport_unknown is True
    assert result.status is not ConfigurationApplicationStatus.VERIFIED
    assert result.dirty_state is DirtyState.UNKNOWN


def test_a_runtime_exception_is_unknown_with_session_failed_never_failed():
    """Row 15. FAILED would claim the payload never left the process."""
    result, _ = _apply(_FactRuntime({}, raises=RuntimeError("synthetic")))
    attempted = [
        item
        for item in result.action_results
        if item.status is not ActionExecutionStatus.DEPENDENCY_BLOCKED
    ]

    assert attempted
    for item in attempted:
        assert item.status is ActionExecutionStatus.UNKNOWN
        assert item.failure_code is ConfigurationFailureCode.SESSION_FAILED
        assert item.cause == "exception:RuntimeError"
        assert item.postcondition is PostconditionFact.UNOBSERVED
    assert result.execution_journal is not None
    assert result.execution_journal.transport_unknown is True


def test_a_missing_row_at_this_port_is_row_fifteen_not_row_seven():
    """TD-12.2. This port holds no acceptance evidence for the missing item.

    Row 7 asserts a proven ACCEPTED, CORRELATED envelope. The applicator never
    saw one for an item the runtime simply did not return, so concluding row 7
    would manufacture channel acceptance out of an absence.
    """
    plan, _ = _compiled()
    first = next(item for item in plan.actions if not item.depends_on)
    runtime = _FactRuntime(_ACCEPTED_SATISFIED_CHANGED, omit=[first.id])

    result, _ = _apply(runtime)
    row = next(item for item in result.action_results if item.action_id == first.id)

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.failure_code is ConfigurationFailureCode.SESSION_FAILED
    assert row.cause == "exception:MissingRuntimeMutationResult"
    assert row.dispatch is DispatchFact.UNSPECIFIED
    assert row.postcondition is PostconditionFact.UNOBSERVED
    assert result.execution_journal is not None
    assert result.execution_journal.transport_unknown is True


def test_an_empty_result_list_is_never_read_as_proof_of_dispatch():
    """A runtime that returned nothing at all makes no acceptance claim."""

    class _SilentRuntime(FakeServiceRuntime):
        def apply_actions(self, actions):
            """Dispatch nothing and report nothing."""
            self.apply_calls.append([item.id for item in actions])
            return []

    result, _ = _apply(_SilentRuntime())
    attempted = [
        item
        for item in result.action_results
        if item.status is not ActionExecutionStatus.DEPENDENCY_BLOCKED
    ]

    assert attempted
    for item in attempted:
        assert item.status is ActionExecutionStatus.UNKNOWN
        assert item.cause == "exception:MissingRuntimeMutationResult"
        assert item.dispatch is not DispatchFact.ACCEPTED
    assert result.status is not ConfigurationApplicationStatus.VERIFIED


def test_an_inconsistent_tuple_is_unknown_and_the_received_value_grants_nothing():
    """A contradiction closes the frontier and keeps its diagnostics apart."""
    result, plan = _apply(_FactRuntime(_INCONSISTENT))
    first = next(item for item in plan.actions if not item.depends_on)
    row = next(item for item in result.action_results if item.action_id == first.id)

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.failure_code is ConfigurationFailureCode.OUTCOME_UNKNOWN
    # TD-12.1: the decision's canonical reason on the result, the producer's
    # own incidental string preserved in the snapshot.
    assert row.cause == "inconsistent_facts"
    assert row.received_mutation is not None
    assert row.received_mutation.cause == "exception:SomeIncidentalError"
    # The received SATISFIED is still visible as a diagnostic and granted
    # nothing: every dependent is blocked.
    assert row.postcondition is PostconditionFact.SATISFIED
    dependents = [item for item in plan.actions if first.id in item.depends_on]
    by_id = {item.action_id: item for item in result.action_results}
    for item in dependents:
        assert by_id[item.id].status is ActionExecutionStatus.DEPENDENCY_BLOCKED


# -- 2. residue and the frontier -----------------------------------------


def test_a_satisfied_partial_footprint_keeps_the_frontier_open_and_names_residue():
    """Rows 9 and 18: the postcondition holds, the residue is unobserved.

    These two claims are independent, so the run may still be VERIFIED while
    reporting an UNKNOWN `dirty_state` and naming the action.
    """
    result, _ = _apply(_FactRuntime(_PARTIAL_FOOTPRINT_SATISFIED))
    by_id = {item.action_id: item for item in result.action_results}

    assert all(
        item.status is ActionExecutionStatus.APPLIED for item in result.action_results
    )
    assert all(
        item.disposition is MutationDisposition.UNKNOWN
        for item in result.action_results
    )
    # The frontier stayed open, so nothing was blocked.
    assert not any(
        item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for item in result.action_results
    )
    assert result.dirty_state is DirtyState.UNKNOWN
    assert result.limitations
    for identifier in by_id:
        assert (
            f"residue_unknown:{identifier}:footprint_partial:dns_a_record_table"
            in result.limitations
        )
    assert result.execution_journal is not None
    assert result.execution_journal.transport_unknown is False


def test_an_unsatisfied_row_closes_the_frontier_and_names_the_reason():
    """Row 10: PARTIAL, sticky, and dependents blocked as unsatisfied."""
    result, plan = _apply(_FactRuntime(_PRE_READ_FAILED_UNSATISFIED))
    first = next(item for item in plan.actions if not item.depends_on)
    by_id = {item.action_id: item for item in result.action_results}

    assert by_id[first.id].status is ActionExecutionStatus.PARTIAL
    assert (
        by_id[first.id].failure_code
        is ConfigurationFailureCode.POSTCONDITION_UNSATISFIED
    )
    assert by_id[first.id].disposition is MutationDisposition.UNKNOWN
    dependents = [item for item in plan.actions if first.id in item.depends_on]
    assert dependents
    for item in dependents:
        assert by_id[item.id].status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        assert f"prerequisite_unsatisfied:{first.id}" in by_id[item.id].message
    assert result.dirty_state is DirtyState.UNKNOWN
    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.POSTCONDITION_UNSATISFIED


def test_an_observed_wrong_value_is_a_recoverable_or_unrecoverable_residue():
    """Row 14: the setter stored something, and it is not what was asked."""
    facts = dict(_ACCEPTED_SATISFIED_CHANGED)
    facts["postcondition"] = PostconditionFact.UNSATISFIED
    result, plan = _apply(_FactRuntime(facts))
    first = next(item for item in plan.actions if not item.depends_on)
    row = next(item for item in result.action_results if item.action_id == first.id)

    assert row.status is ActionExecutionStatus.PARTIAL
    assert row.disposition is MutationDisposition.FAILED
    assert row.residual_change is True
    assert result.dirty_state in {
        DirtyState.DIRTY_RECOVERABLE,
        DirtyState.DIRTY_UNRECOVERABLE,
    }


def test_a_no_op_row_keeps_the_frontier_open_and_the_journal_clean():
    """Row 17: no call was made, so there is nothing to be dirty about."""
    facts = {
        "applied": True,
        "dispatch": DispatchFact.ACCEPTED,
        "result": ResultFact.CORRELATED,
        "postcondition": PostconditionFact.SATISFIED,
        "transition": TransitionFact.UNCHANGED,
        "footprint": FootprintFact.COVERED,
        "attempted": False,
    }
    result, _ = _apply(_FactRuntime(facts))

    assert all(
        item.status is ActionExecutionStatus.NO_OP for item in result.action_results
    )
    assert all(
        item.disposition is MutationDisposition.NO_OP for item in result.action_results
    )
    assert result.dirty_state is DirtyState.CLEAN
    assert result.limitations == []


# -- 3. TD-12.1: the retained classifier input ---------------------------


def test_every_fact_bearing_row_retains_the_exact_tuple_that_was_classified():
    """The snapshot must re-decide to the same decision, from itself."""
    result, _ = _apply(_FactRuntime(_PARTIAL_FOOTPRINT_SATISFIED))

    for row in result.action_results:
        assert row.received_mutation is not None
        snapshot = row.received_mutation
        decision = decide_mutation(snapshot)

        assert decision.status is row.status
        assert decision.disposition is row.disposition
        assert decision.failure_code is row.failure_code
        assert decision.cause == row.cause
        assert (decision.residue is MutationResidue.CHANGED) is row.residual_change


def test_the_snapshot_holds_applied_which_the_public_result_does_not():
    """Without it, `applied` could only be reconstructed -- and must not be."""
    result, _ = _apply(_FactRuntime(_INCONSISTENT))
    row = result.action_results[0]

    assert not hasattr(row, "applied")
    assert row.received_mutation is not None
    assert row.received_mutation.applied is False
    # The reconstruction TD-12.1 forbids: `applied` from `dispatch is ACCEPTED`
    # turns the contradiction into row 12.
    reconstructed = row.received_mutation.model_copy(update={"applied": True})
    assert decide_mutation(reconstructed).row == "12"
    assert decide_mutation(row.received_mutation).row == "inconsistent"


def test_mutating_the_runtimes_object_afterwards_cannot_change_the_snapshot():
    """The applicator's copy is defensive at the boundary it crosses."""
    runtime = _FactRuntime(_ACCEPTED_SATISFIED_CHANGED)
    result, _ = _apply(runtime)
    before = [row.received_mutation.model_dump() for row in result.action_results]

    for mutation in runtime.sent:
        mutation.applied = False
        mutation.postcondition = PostconditionFact.UNSATISFIED
        mutation.cause = "rewritten after the fact"

    after = [row.received_mutation.model_dump() for row in result.action_results]

    assert before == after


def test_a_legacy_row_carries_a_snapshot_whose_re_decision_is_still_legacy():
    """A legacy producer's row keeps its baseline mapping through the snapshot."""
    result, _ = _apply(FakeServiceRuntime())

    for row in result.action_results:
        assert row.received_mutation is not None
        assert decide_mutation(row.received_mutation).row == "16"
        assert row.status is ActionExecutionStatus.APPLIED


def test_a_stored_result_without_a_snapshot_stays_a_legacy_record():
    """No inference gives an old record new fact-bearing authority."""
    result, _ = _apply(_FactRuntime(_ACCEPTED_SATISFIED_CHANGED))
    dumped = result.model_dump(mode="json")
    for row in dumped["action_results"]:
        del row["received_mutation"]

    revalidated = ServiceApplicationResult.model_validate(dumped)

    for row in revalidated.action_results:
        assert row.received_mutation is None
        # The received facts are still there as diagnostics, and nothing
        # fabricates `applied` for the record.
        assert row.dispatch is DispatchFact.ACCEPTED
        assert not hasattr(row, "applied")


# -- 4. the full round-trip through the real serializer ------------------


@pytest.mark.parametrize(
    ("name", "facts", "raises", "omit"),
    [
        ("valid", _ACCEPTED_SATISFIED_CHANGED, None, ()),
        ("residue_unknown", _PARTIAL_FOOTPRINT_SATISFIED, None, ()),
        ("unsatisfied", _PRE_READ_FAILED_UNSATISFIED, None, ()),
        ("inconsistent", _INCONSISTENT, None, ()),
        ("engine_error", _ACCEPTED_ENGINE_ERROR, None, ()),
        ("exception", {}, RuntimeError("synthetic"), ()),
    ],
)
def test_the_whole_result_round_trips_with_every_fact_still_accessible(
    name, facts, raises, omit
):
    """Serialize with the real serializer, validate back, re-decide.

    Status agreement is asserted by BEHAVIOR, not by vocabulary identity: an
    UNKNOWN action row with a PROBE_FAILED evidence record is consistent,
    because the two describe different dimensions.
    """
    runtime = _FactRuntime(facts, raises=raises, omit=omit)
    result, _ = _apply(runtime)

    revalidated = ServiceApplicationResult.model_validate_json(result.model_dump_json())

    assert len(revalidated.action_results) == len(result.action_results)
    for before, after in zip(
        result.action_results, revalidated.action_results, strict=True
    ):
        assert after.dispatch is before.dispatch
        assert after.result is before.result
        assert after.postcondition is before.postcondition
        assert after.transition is before.transition
        assert after.footprint is before.footprint
        assert after.attempted == before.attempted
        assert after.residual_change == before.residual_change
        assert after.cause == before.cause
        assert after.status is before.status
        if before.received_mutation is None:
            assert after.received_mutation is None
            continue
        assert after.received_mutation == before.received_mutation
        assert decide_mutation(after.received_mutation) == decide_mutation(
            before.received_mutation
        )

    assert revalidated.limitations == result.limitations
    assert revalidated.execution_journal is not None
    assert result.execution_journal is not None
    for before, after in zip(
        result.execution_journal.entries,
        revalidated.execution_journal.entries,
        strict=True,
    ):
        assert after.dispatch is before.dispatch
        assert after.result is before.result
        assert after.residual_change == before.residual_change
        assert after.cause == before.cause
        assert after.disposition is before.disposition
    assert (
        revalidated.execution_journal.transport_unknown
        is result.execution_journal.transport_unknown
    )
    assert revalidated.dirty_state is result.dirty_state
    for before, after in zip(
        result.verification_results, revalidated.verification_results, strict=True
    ):
        assert after.observation is before.observation
        assert after.cause == before.cause
        assert after.limitations == before.limitations
    for before, after in zip(
        result.evidence_records, revalidated.evidence_records, strict=True
    ):
        assert after.observation_status is before.observation_status
        assert after.limitations == before.limitations


def test_the_inconsistent_tuple_is_still_inconsistent_after_the_round_trip():
    """TD-12.1's acceptance case, stated on its own."""
    result, _ = _apply(_FactRuntime(_INCONSISTENT))

    revalidated = ServiceApplicationResult.model_validate_json(result.model_dump_json())
    row = revalidated.action_results[0]

    assert row.received_mutation is not None
    assert row.received_mutation.applied is False
    assert decide_mutation(row.received_mutation).row == "inconsistent"
    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.cause == "inconsistent_facts"


# -- 5. evidence -----------------------------------------------------------


def test_a_verified_fresh_read_classifies_as_verified_evidence():
    """R-EVD-01, the positive case."""
    result, _ = _apply(_FactRuntime(_ACCEPTED_SATISFIED_CHANGED))

    assert result.evidence_records
    verified = [
        item for item in result.evidence_records if item.classification == "verified"
    ]
    assert verified


def test_an_undelivered_read_classifies_as_probe_failed_and_names_the_transport():
    """R-EVD-01: UNKNOWN NOT_OBSERVED becomes `probe_failed` plus the fact."""

    class _LostReadRuntime(_FactRuntime):
        def verify(self, expectation):
            """Report a read the transport never delivered."""
            self.verify_calls.append(expectation.id)
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.UNKNOWN,
                evidence_kind=expectation.evidence_kind,
                evidence_method="structured_service_getters",
                fresh_evidence=False,
                observation=ObservationFact.NOT_OBSERVED,
                cause="timed_out",
            )

    result, _ = _apply(_LostReadRuntime(_ACCEPTED_SATISFIED_CHANGED))
    stated = {
        item.expectation_id
        for item in result.verification_results
        if item.observation is ObservationFact.NOT_OBSERVED
    }
    records = [
        item
        for item in result.evidence_records
        if item.id.removeprefix("evidence/") in stated
    ]

    assert records
    for record in records:
        assert record.classification == "probe_failed"
        assert record.observation_status is ObservationStatus.PROBE_FAILED
        assert "transport:not_observed" in record.limitations


def test_a_contradicted_read_is_observed_evidence_of_a_failure():
    """A fresh contradiction is evidence, and it is negative."""

    class _ContradictingRuntime(_FactRuntime):
        def verify(self, expectation):
            """Report a completed read that contradicts the expectation."""
            self.verify_calls.append(expectation.id)
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.FAILED,
                evidence_kind=expectation.evidence_kind,
                evidence_method="structured_service_getters",
                fresh_evidence=True,
                observation=ObservationFact.CONTRADICTED,
            )

    result, _ = _apply(
        _ContradictingRuntime(_ACCEPTED_SATISFIED_CHANGED),
        direct_readback=CapabilityStatus.SUPPORTED,
    )
    stated = {
        item.expectation_id
        for item in result.verification_results
        if item.observation is ObservationFact.CONTRADICTED
    }
    records = [
        item
        for item in result.evidence_records
        if item.id.removeprefix("evidence/") in stated
    ]

    assert records
    for record in records:
        assert record.observation_status is ObservationStatus.OBSERVED
        assert record.verification_status is VerificationStatus.FAILED


def test_a_legacy_verification_row_produces_the_baseline_adapter_output():
    """Observation UNSPECIFIED delegates verbatim to the legacy adapter.

    `FakeServiceRuntime` states no observation fact, so its records must be
    byte-identical to what the baseline adapter produced for the same row.
    """
    from packet_tracer_mcp.domain.enterprise.models.evidence import (
        evidence_from_legacy_result,
    )

    result, plan = _apply(FakeServiceRuntime())
    expectations = {item.id: item for item in plan.verification_expectations}

    for record, row in zip(
        result.evidence_records, result.verification_results, strict=True
    ):
        expected = evidence_from_legacy_result(
            identifier=f"evidence/{row.expectation_id}",
            subject=row.service_id,
            claim=expectations[row.expectation_id].kind.value,
            status=row.status,
            evidence_method=row.evidence_method,
            fresh_evidence=row.fresh_evidence,
            observed_value=row.observed,
            limitations=[row.message] if row.message else [],
        )

        assert row.observation is ObservationFact.UNSPECIFIED
        assert record.observation_status is expected.observation_status
        assert record.verification_status is expected.verification_status
        assert record.classification == expected.classification
        assert record.limitations == expected.limitations


# -- 6. recovery reads -----------------------------------------------------


def test_every_s0_verification_kind_has_a_declared_effect_class():
    """An unclassified kind must not silently become a recovery read."""
    for kind in ServiceVerificationKind:
        assert kind in VERIFICATION_EFFECT_CLASSES, kind
        assert VERIFICATION_EFFECT_CLASSES[kind] in {"read_only", "owned_temporary"}


def test_a_read_only_probe_still_runs_after_an_unresolved_action():
    """A fresh read is exactly what an unresolved action needs.

    The row carries the limitation, the action row is untouched, and the
    sticky flag is not cleared by it.
    """
    result, _ = _apply(
        _FactRuntime(_ACCEPTED_ENGINE_ERROR),
        direct_readback=CapabilityStatus.SUPPORTED,
    )
    recovery = [
        item
        for item in result.verification_results
        if any(
            note.startswith("recovery_read_after_unresolved_action:")
            for note in item.limitations
        )
    ]

    assert recovery
    assert any(
        item.evidence_kind is ServiceEvidenceKind.DIRECT_STATE for item in recovery
    )
    assert any(
        note.startswith("recovery_read_after_unresolved_action:")
        for note in result.limitations
    )
    # The recovery read changed no action row and cleared no doubt.
    assert result.execution_journal is not None
    assert result.execution_journal.transport_unknown is True
    assert result.status is not ConfigurationApplicationStatus.VERIFIED


def test_a_recovery_read_never_lifts_the_bundle_to_verified():
    """Reading state back does not resolve whether the mutation happened."""

    class _AlwaysVerifiedRuntime(_FactRuntime):
        def verify(self, expectation):
            """Report a fresh successful read for every expectation."""
            self.verify_calls.append(expectation.id)
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.VERIFIED,
                evidence_kind=expectation.evidence_kind,
                evidence_method="structured_service_getters",
                fresh_evidence=True,
                observation=ObservationFact.OBSERVED,
            )

    result, _ = _apply(
        _AlwaysVerifiedRuntime(_ACCEPTED_ENGINE_ERROR),
        direct_readback=CapabilityStatus.SUPPORTED,
    )

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert result.failure_code is ConfigurationFailureCode.OUTCOME_UNKNOWN
    assert any(item.startswith("transport_unknown:") for item in result.limitations)


# -- 7. aggregation --------------------------------------------------------


def test_a_direct_contradiction_caps_usability_even_when_behavior_verified():
    """Two readings disagree, and the optimistic one does not win."""

    class _SplitRuntime(_FactRuntime):
        def verify(self, expectation):
            """Contradict the direct read and verify the behavioral one."""
            self.verify_calls.append(expectation.id)
            direct = expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=(
                    ActionExecutionStatus.FAILED
                    if direct
                    else ActionExecutionStatus.VERIFIED
                ),
                evidence_kind=expectation.evidence_kind,
                evidence_method="structured_service_getters",
                fresh_evidence=True,
                observation=(
                    ObservationFact.CONTRADICTED if direct else ObservationFact.OBSERVED
                ),
            )

    result, _ = _apply(
        _SplitRuntime(_ACCEPTED_SATISFIED_CHANGED),
        direct_readback=CapabilityStatus.SUPPORTED,
    )

    assert result.services
    assert all(
        item.usability_status is not ActionExecutionStatus.VERIFIED
        for item in result.services
    )
    assert result.status is not ConfigurationApplicationStatus.VERIFIED


def test_the_verification_failure_code_is_derived_from_the_status():
    """Each status maps to one code, split only by direct versus behavioral."""
    for status, direct_code, behavioral_code in (
        (
            ActionExecutionStatus.VERIFIED,
            ConfigurationFailureCode.NONE,
            ConfigurationFailureCode.NONE,
        ),
        (
            ActionExecutionStatus.FAILED,
            ConfigurationFailureCode.VERIFICATION_FAILED,
            ConfigurationFailureCode.BEHAVIORAL_VERIFICATION_FAILED,
        ),
        (
            ActionExecutionStatus.UNKNOWN,
            ConfigurationFailureCode.OUTCOME_UNKNOWN,
            ConfigurationFailureCode.OUTCOME_UNKNOWN,
        ),
        (
            ActionExecutionStatus.UNOBSERVABLE,
            ConfigurationFailureCode.DIRECT_READBACK_UNOBSERVABLE,
            ConfigurationFailureCode.OBSERVABILITY_LIMITATION,
        ),
        (
            ActionExecutionStatus.PARTIAL,
            ConfigurationFailureCode.OBSERVABILITY_LIMITATION,
            ConfigurationFailureCode.OBSERVABILITY_LIMITATION,
        ),
    ):
        assert (
            ServiceApplicator._verification_failure_code(status, direct=True)
            is direct_code
        )
        assert (
            ServiceApplicator._verification_failure_code(status, direct=False)
            is behavioral_code
        )
