"""Fail-closed acceptance for direct typed-runtime qualification batches."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Protocol

from ...domain.enterprise.models.configuration_runtime import ActionExecutionStatus


class _MutationResult(Protocol):
    action_id: str
    applied: bool


class _ObservationResult(Protocol):
    expectation_id: str
    status: ActionExecutionStatus
    fresh_evidence: bool


def qualification_evidence_value(value: Any) -> Any:
    """Convert typed runtime evidence, including dataclasses, to JSON values."""
    if hasattr(value, "model_dump"):
        return qualification_evidence_value(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return qualification_evidence_value(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): qualification_evidence_value(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray),
    ):
        return [qualification_evidence_value(item) for item in value]
    return value


def _identity_errors(
    expected_ids: Sequence[str],
    actual_ids: Sequence[str],
    *,
    label: str,
) -> list[str]:
    errors: list[str] = []
    expected_counts = Counter(expected_ids)
    actual_counts = Counter(actual_ids)
    duplicate_expected = sorted(
        item for item, count in expected_counts.items() if count != 1
    )
    duplicate_actual = sorted(
        item for item, count in actual_counts.items() if count != 1
    )
    missing = sorted(set(expected_counts) - set(actual_counts))
    unexpected = sorted(set(actual_counts) - set(expected_counts))
    if duplicate_expected:
        errors.append(
            f"duplicate expected {label} IDs: {', '.join(duplicate_expected)}"
        )
    if duplicate_actual:
        errors.append(f"duplicate {label} results: {', '.join(duplicate_actual)}")
    if missing:
        errors.append(f"missing {label} results: {', '.join(missing)}")
    if unexpected:
        errors.append(f"unexpected {label} results: {', '.join(unexpected)}")
    return errors


def typed_runtime_batch_errors(
    *,
    action_ids: Sequence[str],
    expectation_ids: Sequence[str],
    mutations: Sequence[_MutationResult],
    observations: Sequence[_ObservationResult],
) -> tuple[str, ...]:
    """Return every reason a direct typed qualification batch is not VERIFIED.

    A transport acceptance only establishes ``applied``.  Qualification also
    requires a one-to-one fresh runtime observation for every declared
    expectation; neither side may silently omit or add an identity.
    """
    errors = _identity_errors(
        action_ids,
        [item.action_id for item in mutations],
        label="action",
    )
    errors.extend(_identity_errors(
        expectation_ids,
        [item.expectation_id for item in observations],
        label="expectation",
    ))
    for item in mutations:
        if not item.applied:
            errors.append(f"{item.action_id}: mutation was not accepted")
    for item in observations:
        if item.status is not ActionExecutionStatus.VERIFIED:
            errors.append(f"{item.expectation_id}: status is {item.status.value}")
        if not item.fresh_evidence:
            errors.append(f"{item.expectation_id}: evidence is not fresh")
    return tuple(errors)
