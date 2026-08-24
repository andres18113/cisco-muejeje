from __future__ import annotations

import json
from dataclasses import dataclass

from src.packet_tracer_mcp.application.use_cases.qualify_typed_runtime import (
    qualification_evidence_value,
    typed_runtime_batch_errors,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    RuntimeActionMutation,
    RuntimeVerification,
)


def test_typed_runtime_batch_requires_exact_fresh_verified_evidence() -> None:
    assert typed_runtime_batch_errors(
        action_ids=["action/a"],
        expectation_ids=["expectation/a"],
        mutations=[RuntimeActionMutation(action_id="action/a", applied=True)],
        observations=[RuntimeVerification(
            expectation_id="expectation/a",
            status=ActionExecutionStatus.VERIFIED,
            fresh_evidence=True,
        )],
    ) == ()


def test_typed_runtime_batch_rejects_missing_or_non_fresh_results() -> None:
    errors = typed_runtime_batch_errors(
        action_ids=["action/a", "action/b"],
        expectation_ids=["expectation/a", "expectation/b"],
        mutations=[
            RuntimeActionMutation(action_id="action/a", applied=True),
            RuntimeActionMutation(action_id="unexpected", applied=True),
        ],
        observations=[
            RuntimeVerification(
                expectation_id="expectation/a",
                status=ActionExecutionStatus.VERIFIED,
                fresh_evidence=False,
            ),
            RuntimeVerification(
                expectation_id="expectation/b",
                status=ActionExecutionStatus.UNKNOWN,
                fresh_evidence=True,
            ),
        ],
    )

    assert any("missing action results: action/b" in item for item in errors)
    assert any("unexpected action results: unexpected" in item for item in errors)
    assert any("expectation/a: evidence is not fresh" in item for item in errors)
    assert any("expectation/b: status is unknown" in item for item in errors)


def test_qualification_evidence_serializes_nested_dataclass_results() -> None:
    @dataclass(frozen=True)
    class Diagnostic:
        query: str
        status: ActionExecutionStatus

    value = qualification_evidence_value({
        "result": Diagnostic("show ip protocols", ActionExecutionStatus.VERIFIED),
    })

    assert json.loads(json.dumps(value)) == {
        "result": {"query": "show ip protocols", "status": "verified"},
    }
