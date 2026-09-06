"""Coherence rules for reusable Packet Tracer LIVE-session evidence."""

from __future__ import annotations

from pathlib import PurePath, PurePosixPath, PureWindowsPath

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.discovery import (
    LivePathIdentitySemantics,
    LiveSessionSafetyEvidence,
)


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
    semantics = evidence.path_identity_semantics
    if semantics is None:
        errors.append(_error("Persisted .pts path identity semantics are missing."))
    if not _exact_path(evidence.canonical_path, semantics):
        errors.append(_error("Exact canonical .pts identity is missing."))
    if not _exact_path(evidence.disposable_path, semantics):
        errors.append(_error("Exact disposable .pts identity is missing."))
    if _same_path(evidence.canonical_path, evidence.disposable_path, semantics):
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


def _exact_path(
    value: str | None,
    semantics: LivePathIdentitySemantics | None,
) -> bool:
    if not value or value != value.strip() or semantics is None:
        return False
    if any(ord(character) < 32 for character in value):
        return False
    path_type: type[PurePath]
    if semantics is LivePathIdentitySemantics.WINDOWS:
        path_type = PureWindowsPath
    elif semantics is LivePathIdentitySemantics.POSIX:
        path_type = PurePosixPath
    else:
        return False
    try:
        path = path_type(value)
    except (TypeError, ValueError):
        return False
    if str(path) != value or not path.is_absolute() or path.suffix.casefold() != ".pts":
        return False
    if ".." in path.parts:
        return False
    if semantics is LivePathIdentitySemantics.WINDOWS:
        invalid = frozenset('<>:"|?*')
        for part in path.parts[1:]:
            if any(character in invalid for character in part):
                return False
            if part.endswith((" ", ".")):
                return False
    return True


def _same_path(
    first: str | None,
    second: str | None,
    semantics: LivePathIdentitySemantics | None,
) -> bool:
    if not first or not second or semantics is None:
        return False
    path_type = (
        PureWindowsPath
        if semantics is LivePathIdentitySemantics.WINDOWS
        else PurePosixPath
    )
    return path_type(first) == path_type(second)


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
