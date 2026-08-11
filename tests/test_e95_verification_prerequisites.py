import pytest

from src.packet_tracer_mcp.domain.enterprise.models.verification import (
    PrerequisiteKind,
    VerificationDependencyError,
    VerificationPrerequisite,
    order_verification_expectations,
    prerequisites_satisfied,
)


class _Expectation:
    def __init__(self, identifier: str, prerequisites: list[VerificationPrerequisite]):
        self.id = identifier
        self.verification_prerequisites = prerequisites


def test_verification_dag_is_independent_of_input_order():
    direct = _Expectation("dns/direct", [])
    composed = _Expectation("http/by-hostname", [VerificationPrerequisite(
        kind=PrerequisiteKind.VERIFICATION_VERIFIED,
        reference_id="dns/direct",
    )])

    ordered = order_verification_expectations([composed, direct])

    assert [item.id for item in ordered] == ["dns/direct", "http/by-hostname"]


def test_missing_or_cyclic_verification_prerequisites_are_rejected():
    missing = _Expectation("a", [VerificationPrerequisite(
        kind=PrerequisiteKind.VERIFICATION_VERIFIED, reference_id="missing",
    )])
    with pytest.raises(VerificationDependencyError, match="unknown"):
        order_verification_expectations([missing])

    first = _Expectation("a", [VerificationPrerequisite(
        kind=PrerequisiteKind.VERIFICATION_VERIFIED, reference_id="b",
    )])
    second = _Expectation("b", [VerificationPrerequisite(
        kind=PrerequisiteKind.VERIFICATION_VERIFIED, reference_id="a",
    )])
    with pytest.raises(VerificationDependencyError, match="cycle"):
        order_verification_expectations([first, second])


def test_unsatisfied_prerequisite_is_blocked_not_failed():
    prerequisites = [VerificationPrerequisite(
        kind=PrerequisiteKind.ACTION_APPLIED, reference_id="cfg/r2/interface",
    )]

    satisfied, blocked = prerequisites_satisfied(
        prerequisites,
        action_statuses={"cfg/r2/interface": "failed"},
        verification_statuses={},
        resource_statuses={},
    )

    assert satisfied is False
    assert blocked == ["action_applied:cfg/r2/interface"]

