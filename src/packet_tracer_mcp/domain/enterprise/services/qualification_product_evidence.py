"""Pure product-evidence predicates for server-service qualification.

Each one decides from domain application results alone whether the product
path may found a further effect. They dispatch nothing and receive no
application contract.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    MutationResidue,
    decide_mutation,
)
from ..models.execution import DispatchFact, PostconditionFact, ResultFact
from ..models.service_runtime import ObservationFact, ServiceApplicationResult


def e5_foundation_cause(
    configuration: ConfigurationApplicationResult,
    foundations: Mapping[str, ActionExecutionStatus],
    expected_action_ids: set[str],
) -> str:
    """Return why E5 cannot found an E6 mutation, or "" when it can.

    The classification reuses the applicator's own decided facts. A short
    result set, an unknown dispatch, an unobserved result, an unsatisfied
    postcondition, a contradicted read-back or a foundational status that is
    not VERIFIED all mean the same thing here: the next effect has no
    permission, and none of them is a reason to dispatch it and look later.
    """
    reported = [item.action_id for item in configuration.action_results]
    if (
        len(reported) != len(expected_action_ids)
        or set(reported) != expected_action_ids
        or len(reported) != len(set(reported))
    ):
        return "outcome_unknown:q3_e5_incomplete_result_set"
    for item in sorted(configuration.action_results, key=lambda row: row.action_id):
        snapshot = item.received_mutation
        if snapshot is not None:
            decision = decide_mutation(snapshot)
            if not (
                item.status is decision.status
                and item.failure_code is decision.failure_code
                and item.disposition is decision.disposition
                and item.cause == decision.cause
            ):
                return f"outcome_unknown:q3_e5_endpoints:{item.action_id}"
        if (
            item.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
            or item.result is ResultFact.NOT_OBSERVED
            or item.status is ActionExecutionStatus.UNKNOWN
            or (snapshot is not None and bool(snapshot.call_error))
        ):
            return f"outcome_unknown:q3_e5_endpoints:{item.action_id}"
        if item.postcondition is PostconditionFact.UNSATISFIED:
            return f"contradiction:q3_e5_endpoints:{item.action_id}"
    # E5 read-backs carry a lifecycle status, not an observation fact:
    # FAILED is the re-read that did not match what the action intended.
    contradicted = sorted(
        item.expectation_id
        for item in configuration.verification_results
        if item.status is ActionExecutionStatus.FAILED
    )
    if contradicted:
        return f"contradiction:q3_e5_verification:{contradicted[0]}"
    if not foundations or any(
        item is not ActionExecutionStatus.VERIFIED for item in foundations.values()
    ):
        return "q3_foundations_not_established"
    return ""


def service_result_cause(
    result: ServiceApplicationResult,
    expected_action_ids: set[str],
    *,
    expected_verification_ids: set[str] | None = None,
    recovered_action_ids: set[str] | None = None,
) -> str:
    """Return why the product result forbids another mutation, or "".

    The exact row identities and the canonical decision retained on every
    mutation are the authority. A later fresh verification may settle a
    correlated execute-once action, but it cannot repair a lost acknowledgement
    or an incoherent result set.
    """
    action_ids = [item.action_id for item in result.action_results]
    if len(action_ids) != len(expected_action_ids) or set(action_ids) != set(
        expected_action_ids
    ):
        return "outcome_unknown:q3_product_incomplete_result_set"
    if len(action_ids) != len(set(action_ids)):
        return "outcome_unknown:q3_product_incomplete_result_set"
    if expected_verification_ids is not None:
        verification_ids = [item.expectation_id for item in result.verification_results]
        if (
            len(verification_ids) != len(expected_verification_ids)
            or set(verification_ids) != expected_verification_ids
            or len(verification_ids) != len(set(verification_ids))
        ):
            return "outcome_unknown:q3_product_incomplete_verification_set"
    if any(
        item.observation is ObservationFact.CONTRADICTED
        for item in result.verification_results
    ):
        return "contradiction:q3_product_readback"
    if any(
        item.observation is ObservationFact.ENGINE_ERROR
        or item.cause.startswith("exception:")
        for item in result.verification_results
    ):
        return "outcome_unknown:q3_product_verification"
    recovered = recovered_action_ids or set()
    for row in result.action_results:
        snapshot = row.received_mutation
        if snapshot is None or snapshot.action_id != row.action_id:
            return "outcome_unknown:q3_product_service"
        decision = decide_mutation(snapshot)
        if not (
            row.status is decision.status
            and row.failure_code is decision.failure_code
            and row.disposition is decision.disposition
            and row.dispatch is snapshot.dispatch
            and row.result is snapshot.result
            and row.postcondition is snapshot.postcondition
            and row.transition is snapshot.transition
            and row.footprint is snapshot.footprint
            and row.attempted is snapshot.attempted
            and row.residual_change is (decision.residue is MutationResidue.CHANGED)
            and row.cause == decision.cause
        ):
            return "outcome_unknown:q3_product_service"
        if (
            row.dispatch is not DispatchFact.ACCEPTED
            or row.result is ResultFact.NOT_OBSERVED
            or row.attempted is None
            or bool(snapshot.call_error)
            or (not decision.frontier and row.action_id not in recovered)
        ):
            return "outcome_unknown:q3_product_service"
    return ""


def readback_not_observed_cause(result: ServiceApplicationResult) -> str:
    """Return why a projected stage's read-back did not observe, or "".

    A stage whose whole point is the stored configuration cannot treat a
    verification that never ran as a pass. `service_result_cause` refuses
    a contradicted or errored row and a short result set, but a row the
    applicator reported DEPENDENCY_BLOCKED carries `UNSPECIFIED` and slipped
    through: the process was activated and nothing was read back.
    """
    for item in result.verification_results:
        if item.observation is not ObservationFact.OBSERVED:
            return (
                "outcome_unknown:diagnostic_readback_not_observed:"
                f"{item.expectation_id}:{item.observation.value}"
            )
    return ""
