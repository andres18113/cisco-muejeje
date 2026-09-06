"""Coherence rules for reusable Packet Tracer LIVE-session evidence."""

from __future__ import annotations

import os
from pathlib import Path

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.discovery import LiveSessionSafetyEvidence


def validate_live_session_positive_admission(
    evidence: LiveSessionSafetyEvidence,
) -> ValidationResult:
    """Accept only complete, internally coherent evidence for a positive claim."""

    errors: list[PlanError] = []
    expected_true = (
        ("positive claim admission", evidence.positive_claim_allowed),
        ("session reuse", evidence.session_reusable),
        ("file integrity", evidence.integrity_verified),
        ("runtime health", evidence.runtime_healthy),
    )
    for label, value in expected_true:
        if value is not True:
            errors.append(_error(f"LIVE {label} was not verified true."))
    if evidence.crash_detected is not False:
        errors.append(_error("Packet Tracer crash absence was not verified."))
    if evidence.unexpected_canonical_modification is not False:
        errors.append(_error("Canonical .pts immutability was not verified."))
    if evidence.disposable_modified is not False:
        errors.append(_error("Disposable .pts immutability was not verified."))
    if evidence.restoration_attempted:
        errors.append(_error(
            "A session that required canonical .pts restoration cannot release a claim."
        ))
    if evidence.restoration_verified is not None:
        errors.append(_error(
            "Restoration verification is inconsistent when no restoration was allowed."
        ))
    if not _exact_path(evidence.canonical_path):
        errors.append(_error("Exact canonical .pts identity is missing."))
    if not _exact_path(evidence.disposable_path):
        errors.append(_error("Exact disposable .pts identity is missing."))
    if _same_path(evidence.canonical_path, evidence.disposable_path):
        errors.append(_error("Canonical and disposable .pts identities must differ."))

    canonical_hashes = (
        evidence.canonical_pre_run_sha256,
        evidence.canonical_observed_post_run_sha256,
        evidence.canonical_verified_sha256,
    )
    disposable_hashes = (
        evidence.disposable_pre_run_sha256,
        evidence.disposable_post_run_sha256,
    )
    if not all(_is_sha256(value) for value in (*canonical_hashes, *disposable_hashes)):
        errors.append(_error("Complete SHA-256 file identity is missing or malformed."))
    elif len(set(canonical_hashes)) != 1:
        errors.append(_error("Canonical .pts SHA-256 changed during the LIVE session."))
    elif len(set(disposable_hashes)) != 1:
        errors.append(_error("Disposable .pts SHA-256 changed during the LIVE session."))
    elif canonical_hashes[0] != disposable_hashes[0]:
        errors.append(_error(
            "Disposable .pts did not retain the canonical pre-run byte identity."
        ))
    if evidence.failure_reasons:
        errors.append(_error("LIVE session safety reported one or more failures."))
    return ValidationResult(errors=errors)


def _exact_path(value: str | None) -> bool:
    return bool(
        value
        and value == value.strip()
        and Path(value).is_absolute()
        and Path(value).suffix.casefold() == ".pts"
    )


def _same_path(first: str | None, second: str | None) -> bool:
    if not first or not second:
        return False
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(
        os.path.abspath(second)
    )


def _is_sha256(value: str | None) -> bool:
    return bool(
        value
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.casefold())
    )


def _error(message: str) -> PlanError:
    return PlanError(
        code=ErrorCode.CAPABILITY_SNAPSHOT_INVALID,
        message=message,
        suggestion="Keep the claim UNKNOWN and require a fresh governed LIVE session.",
    )
