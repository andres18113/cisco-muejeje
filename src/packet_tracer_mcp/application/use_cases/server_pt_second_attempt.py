"""Fail-closed second-attempt admission for the bounded C31 campaign."""

from __future__ import annotations

import re
from collections.abc import Mapping

_ATTEMPT = re.compile(r"[0-9a-f]{32}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_CLASSIFICATIONS = frozenset({"setup", "observer", "transport", "product"})


def second_attempt_findings(
    *,
    first_attempt_id: str,
    first_process_incarnation: str,
    first_result_outcome: str,
    first_retirement_outcome: str,
    first_result_sha256: str,
    first_retirement_sha256: str,
    new_source_sha: str,
    new_process_incarnation: str,
    correction: Mapping[str, object] | None,
) -> tuple[str, ...]:
    """Require first evidence, a bounded causal delta and a fresh process."""
    found: list[str] = []
    if _ATTEMPT.fullmatch(first_attempt_id) is None or first_result_outcome not in {
        "stopped",
        "refused",
    }:
        found.append("first_result_not_preserved_as_failure")
    if first_retirement_outcome not in {"restored", "exited_dirty"}:
        found.append("first_retirement_not_safe")
    if (
        not first_process_incarnation
        or not new_process_incarnation
        or first_process_incarnation == new_process_incarnation
    ):
        found.append("process_not_fresh")
    if (
        _SHA64.fullmatch(first_result_sha256) is None
        or _SHA64.fullmatch(first_retirement_sha256) is None
        or _SHA40.fullmatch(new_source_sha) is None
    ):
        found.append("first_evidence_or_source_unobservable")
    if correction is None:
        found.append("causal_correction_missing")
    else:
        explanation = correction.get("causal_explanation")
        action = correction.get("corrective_action")
        if (
            correction.get("first_attempt_id") != first_attempt_id
            or correction.get("first_result_sha256") != first_result_sha256
            or correction.get("first_retirement_sha256") != first_retirement_sha256
            or correction.get("corrected_source_sha") != new_source_sha
            or correction.get("classification") not in _CLASSIFICATIONS
            or not isinstance(explanation, str)
            or not explanation.strip()
            or len(explanation) > 2048
            or not isinstance(action, str)
            or not action.strip()
            or len(action) > 2048
        ):
            found.append("causal_correction_mismatch")
    return tuple(found)
