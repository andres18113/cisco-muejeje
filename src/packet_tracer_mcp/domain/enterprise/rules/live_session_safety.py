"""Coherence rules for reusable Packet Tracer LIVE-session evidence."""

from __future__ import annotations

from pathlib import PurePath, PurePosixPath, PureWindowsPath

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.discovery import (
    EphemeralUntitledWorkspaceSafetyEvidence,
    LivePathIdentitySemantics,
    LiveSessionSafetyAdmissionEvidence,
    LiveSessionSafetyEvidence,
    LiveSessionSafetyMode,
    decode_inventory_observation,
    encode_inventory_observation,
)


def validate_live_session_positive_admission(
    evidence: LiveSessionSafetyAdmissionEvidence,
) -> ValidationResult:
    """Accept only complete, internally coherent evidence for a positive claim."""

    if isinstance(evidence, EphemeralUntitledWorkspaceSafetyEvidence):
        return _validate_ephemeral_untitled_workspace(evidence)
    return _validate_guarded_pts_copy(evidence)


def _validate_guarded_pts_copy(
    evidence: LiveSessionSafetyEvidence,
) -> ValidationResult:
    """Preserve the historical guarded-copy admission contract unchanged."""

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


def _validate_ephemeral_untitled_workspace(
    evidence: EphemeralUntitledWorkspaceSafetyEvidence,
) -> ValidationResult:
    errors: list[PlanError] = []
    if evidence.mode is not LiveSessionSafetyMode.EPHEMERAL_UNTITLED_WORKSPACE:
        errors.append(_error("Ephemeral LIVE session safety mode is contradictory."))

    workspace_counts = (
        ("initial device count", evidence.initial_device_count),
        ("final device count", evidence.final_device_count),
        ("initial link count", evidence.initial_link_count),
        ("final link count", evidence.final_link_count),
    )
    for label, value in workspace_counts:
        if type(value) is not int or value != 0:
            errors.append(_error(f"Ephemeral LIVE {label} was not exactly zero."))

    saved_filenames = (
        ("initial saved filename", evidence.initial_saved_filename),
        ("final saved filename", evidence.final_saved_filename),
    )
    for label, value in saved_filenames:
        if type(value) is not str or value != "":
            errors.append(_error(f"Ephemeral LIVE {label} was not exactly empty."))

    file_ledgers = (
        ("authorized file-operation ledger", evidence.authorized_file_operations),
        ("executed file-operation ledger", evidence.executed_file_operations),
    )
    for label, value in file_ledgers:
        if not _is_explicitly_empty_tuple(value):
            errors.append(_error(f"Ephemeral LIVE {label} was not explicitly empty."))

    initial_inventory = evidence.initial_inventory_fingerprint
    final_inventory = evidence.final_inventory_fingerprint
    if not _is_canonical_inventory_identity(initial_inventory):
        errors.append(_error(
            "Ephemeral LIVE initial inventory identity is missing or malformed."
        ))
    if not _is_canonical_inventory_identity(final_inventory):
        errors.append(_error(
            "Ephemeral LIVE final inventory identity is missing or malformed."
        ))
    if initial_inventory != final_inventory:
        errors.append(_error("Ephemeral LIVE inventory identity changed."))

    expected_true = (
        ("fixture removal", evidence.fixture_removed),
        ("initial Realtime mode", evidence.initial_realtime),
        ("final Realtime mode", evidence.final_realtime),
        ("initial bridge health", evidence.bridge_healthy_before),
        ("final bridge health", evidence.bridge_healthy_after),
        ("initial worktree cleanliness", evidence.worktree_clean_before),
        ("final worktree cleanliness", evidence.worktree_clean_after),
        ("runtime health", evidence.runtime_healthy),
        ("file integrity", evidence.integrity_verified),
        ("session reuse", evidence.session_reusable),
        ("positive claim admission", evidence.positive_claim_allowed),
    )
    for label, value in expected_true:
        if value is not True:
            errors.append(_error(f"Ephemeral LIVE {label} was not verified true."))
    if evidence.crash_detected is not False:
        errors.append(_error("Ephemeral LIVE crash absence was not verified."))

    before_pids = evidence.packet_tracer_pids_before
    after_pids = evidence.packet_tracer_pids_after
    if not _is_single_positive_pid(before_pids):
        errors.append(_error("Exactly one positive Packet Tracer PID is required before."))
    if not _is_single_positive_pid(after_pids):
        errors.append(_error("Exactly one positive Packet Tracer PID is required after."))
    if before_pids != after_pids:
        errors.append(_error("Packet Tracer PID identity changed during the LIVE session."))

    mailboxes = (
        ("initial mailbox", evidence.mailbox_entries_before),
        ("final mailbox", evidence.mailbox_entries_after),
    )
    for label, value in mailboxes:
        if not _is_explicitly_empty_tuple(value):
            errors.append(_error(f"Ephemeral LIVE {label} was not explicitly empty."))

    source_identities = (
        (
            "source branch",
            evidence.source_branch_before,
            evidence.source_branch_after,
            _is_exact_identity,
        ),
        (
            "source HEAD",
            evidence.source_head_before,
            evidence.source_head_after,
            _is_git_object_id,
        ),
        (
            "source tree",
            evidence.source_tree_before,
            evidence.source_tree_after,
            _is_git_object_id,
        ),
    )
    for label, before, after, identity_is_valid in source_identities:
        if not identity_is_valid(before) or not identity_is_valid(after):
            errors.append(_error(f"Ephemeral LIVE {label} identity is missing or malformed."))
        if before != after:
            errors.append(_error(f"Ephemeral LIVE {label} identity changed."))

    if evidence.failure_reasons:
        errors.append(_error("Ephemeral LIVE session safety reported failures."))
    return ValidationResult(errors=errors)


def _is_explicitly_empty_tuple(value: tuple[object, ...] | None) -> bool:
    return type(value) is tuple and not value


def _is_nonblank_identity(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _is_canonical_inventory_identity(value: object) -> bool:
    if type(value) is not str:
        return False
    semantic, backend_managed = decode_inventory_observation(value)
    return (
        _is_lower_hex_identity(semantic, length=64)
        and encode_inventory_observation(
            semantic, list(backend_managed),
        ) == value
    )


def _is_exact_identity(value: object) -> bool:
    return _is_nonblank_identity(value) and value == value.strip()


def _is_git_object_id(value: object) -> bool:
    return _is_lower_hex_identity(value, length=40)


def _is_lower_hex_identity(value: object, *, length: int) -> bool:
    return (
        type(value) is str
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_single_positive_pid(value: tuple[int, ...] | None) -> bool:
    return (
        type(value) is tuple
        and len(value) == 1
        and type(value[0]) is int
        and value[0] > 0
    )


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
