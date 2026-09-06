from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.packet_tracer_mcp.infrastructure.execution import live_file_integrity
from src.packet_tracer_mcp.infrastructure.execution.active_workspace_observer import (
    ActiveWorkspaceIdentitySample,
)
from src.packet_tracer_mcp.infrastructure.execution.live_file_integrity import (
    PacketTracerLiveFileGuard,
    PacketTracerLiveSessionSafety,
)


CANONICAL = b"canonical packet tracer script module\n"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _guard(tmp_path: Path):
    canonical = tmp_path / "V5.pts"
    canonical.write_bytes(CANONICAL)
    guard = PacketTracerLiveFileGuard(
        canonical_path=canonical,
        disposable_root=tmp_path / "live-sessions",
        run_identity="poe-run/with unsafe separators",
    )
    return canonical, guard


def _workspace_sample(path: str, *, instance_id: str = "instance-1"):
    return ActiveWorkspaceIdentitySample(
        path=path,
        instance_id=instance_id,
        module_id="pt-mcp-module",
        module_name="Packet Tracer MCP",
    )


def _bound_safety(
    tmp_path: Path,
    *,
    workspace_path=None,
    runtime_health=lambda: True,
    crash_detector=lambda: False,
):
    _canonical, guard = _guard(tmp_path)
    observed_path = {"value": workspace_path}

    def observe_workspace():
        path = observed_path["value"]
        return None if path is None else _workspace_sample(path)

    safety = PacketTracerLiveSessionSafety(
        file_guard=guard,
        runtime_health=runtime_health,
        crash_detector=crash_detector,
        active_workspace_observer=observe_workspace,
    )
    identity = safety.prepare()
    if workspace_path == "prepared-disposable":
        observed_path["value"] = identity.disposable_path
    return safety, identity, observed_path


def test_guard_prepares_an_exact_hash_pinned_disposable_pts_copy(tmp_path: Path):
    canonical, guard = _guard(tmp_path)

    prepared = guard.prepare()

    assert prepared.canonical_path == str(canonical.resolve())
    assert prepared.canonical_sha256 == _sha256(CANONICAL)
    assert prepared.disposable_path != prepared.canonical_path
    disposable = Path(prepared.disposable_path)
    assert disposable.suffix.casefold() == ".pts"
    assert disposable.read_bytes() == CANONICAL
    assert prepared.disposable_sha256 == prepared.canonical_sha256
    assert disposable.resolve().is_relative_to((tmp_path / "live-sessions").resolve())


def test_long_canonical_name_cannot_alias_disposable_and_recovery_files(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / (("x" * 120) + ".pts")
    canonical.write_bytes(CANONICAL)
    guard = PacketTracerLiveFileGuard(
        canonical_path=canonical,
        disposable_root=tmp_path / "live-sessions",
        run_identity="long-name-run",
    )

    identity = guard.prepare()
    assert guard._backup_path is not None
    assert Path(identity.disposable_path).suffix.casefold() == ".pts"
    assert Path(identity.disposable_path) != guard._backup_path
    Path(identity.disposable_path).write_bytes(b"changed disposable")
    canonical.write_bytes(b"changed canonical")

    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert canonical.read_bytes() == CANONICAL
    assert integrity.restoration_verified is True
    assert integrity.disposable_modified is True
    assert integrity.session_reusable is False


def test_changes_to_disposable_pts_never_change_the_canonical_file(tmp_path: Path):
    canonical, guard = _guard(tmp_path)
    prepared = guard.prepare()

    Path(prepared.disposable_path).write_bytes(b"Packet Tracer changed its copy")
    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert canonical.read_bytes() == CANONICAL
    assert integrity.unexpected_modification is False
    assert integrity.disposable_modified is True
    assert integrity.integrity_verified is False
    assert integrity.session_reusable is False
    assert integrity.release_positive_claim("SUPPORTED") is None


def test_file_guard_alone_cannot_release_a_positive_live_claim(tmp_path: Path):
    _canonical, guard = _guard(tmp_path)
    guard.prepare()

    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert integrity.integrity_verified is True
    assert integrity.unexpected_modification is False
    assert integrity.session_reusable is False
    assert integrity.workspace_binding_verified is None
    assert integrity.positive_claim_allowed is False
    assert integrity.release_positive_claim("SUPPORTED") is None


def test_crash_makes_session_non_reusable_even_when_canonical_pts_is_unchanged(tmp_path: Path):
    _canonical, guard = _guard(tmp_path)
    guard.prepare()

    integrity = guard.finalize(runtime_healthy=False, crash_detected=True)

    assert integrity.integrity_verified is True
    assert integrity.session_reusable is False
    assert integrity.positive_claim_allowed is False
    assert integrity.release_positive_claim("SUPPORTED") is None
    assert any("crash" in reason.casefold() for reason in integrity.failure_reasons)


def test_common_session_safety_adapter_closes_claim_before_persistence_on_crash(tmp_path: Path):
    _canonical, guard = _guard(tmp_path)
    safety = PacketTracerLiveSessionSafety(
        file_guard=guard,
        runtime_health=lambda: False,
        crash_detector=lambda: True,
        active_workspace_observer=lambda: None,
    )
    safety.prepare()

    result = safety.finalize()

    assert result.crash_detected is True
    assert result.integrity_verified is True
    assert result.session_reusable is False
    assert result.positive_claim_allowed is False
    assert safety.integrity is not None
    assert safety.integrity.observed_disposable_post_run_sha256 == _sha256(CANONICAL)


def test_exact_disposable_workspace_binding_admits_a_healthy_session(
    tmp_path: Path,
) -> None:
    safety, identity, _observed_path = _bound_safety(
        tmp_path,
        workspace_path="prepared-disposable",
    )

    pre_sample = safety.bind_active_workspace()
    result = safety.finalize()

    assert pre_sample.path == identity.disposable_path
    assert result.active_workspace_binding is not None
    assert (
        result.active_workspace_binding.pre_qualification_path
        == identity.disposable_path
    )
    assert result.active_workspace_binding.post_integrity_path == (
        identity.disposable_path
    )
    assert result.session_reusable is True
    assert result.positive_claim_allowed is True


@pytest.mark.parametrize("workspace_kind", ["canonical", "other-disposable", None])
def test_missing_or_mismatched_active_workspace_cannot_release_a_positive_claim(
    tmp_path: Path,
    workspace_kind: str | None,
) -> None:
    safety, identity, observed_path = _bound_safety(tmp_path)
    if workspace_kind == "canonical":
        observed_path["value"] = identity.canonical_path
    elif workspace_kind == "other-disposable":
        observed_path["value"] = str(
            (tmp_path / "other-session" / "packet-tracer-live.pts").resolve()
        )

    if workspace_kind is not None:
        assert safety.bind_active_workspace() is None
    result = safety.finalize()

    assert result.session_reusable is False
    assert result.positive_claim_allowed is False
    assert safety.integrity is not None
    assert safety.integrity.release_positive_claim("SUPPORTED") is None
    assert any("workspace" in reason.casefold() for reason in result.failure_reasons)


def test_crash_still_dominates_a_verified_workspace_binding(tmp_path: Path) -> None:
    safety, _identity, _observed_path = _bound_safety(
        tmp_path,
        workspace_path="prepared-disposable",
        runtime_health=lambda: False,
        crash_detector=lambda: True,
    )
    safety.bind_active_workspace()

    result = safety.finalize()

    assert result.crash_detected is True
    assert result.session_reusable is False
    assert result.positive_claim_allowed is False


def test_disposable_integrity_failure_still_dominates_verified_workspace_binding(
    tmp_path: Path,
) -> None:
    safety, identity, _observed_path = _bound_safety(
        tmp_path,
        workspace_path="prepared-disposable",
    )
    safety.bind_active_workspace()
    Path(identity.disposable_path).write_bytes(b"changed during live")

    result = safety.finalize()

    assert result.disposable_modified is True
    assert result.integrity_verified is False
    assert result.positive_claim_allowed is False


def test_post_integrity_workspace_drift_cannot_release_a_positive_claim(
    tmp_path: Path,
) -> None:
    _canonical, guard = _guard(tmp_path)
    paths: list[str] = []

    def observe_workspace() -> ActiveWorkspaceIdentitySample:
        return _workspace_sample(paths.pop(0))

    safety = PacketTracerLiveSessionSafety(
        file_guard=guard,
        runtime_health=lambda: True,
        crash_detector=lambda: False,
        active_workspace_observer=observe_workspace,
    )
    identity = safety.prepare()
    paths.extend([
        identity.disposable_path,
        str((tmp_path / "other" / "packet-tracer-live.pts").resolve()),
    ])
    safety.bind_active_workspace()

    result = safety.finalize()

    assert result.active_workspace_binding is not None
    assert result.active_workspace_binding.pre_qualification_path == (
        identity.disposable_path
    )
    assert result.active_workspace_binding.post_integrity_path != (
        identity.disposable_path
    )
    assert result.session_reusable is False
    assert result.positive_claim_allowed is False


def test_crash_during_final_file_verification_cannot_release_a_positive_claim(
    tmp_path: Path,
) -> None:
    _canonical, guard = _guard(tmp_path)
    crash_samples = iter((False, True))
    health_samples = iter((True, False))
    safety = PacketTracerLiveSessionSafety(
        file_guard=guard,
        runtime_health=lambda: next(health_samples),
        crash_detector=lambda: next(crash_samples),
        active_workspace_observer=lambda: None,
    )
    safety.prepare()

    result = safety.finalize()

    assert result.crash_detected is True
    assert result.runtime_healthy is False
    assert result.integrity_verified is True
    assert result.session_reusable is False
    assert result.positive_claim_allowed is False
    assert safety.integrity is not None
    assert safety.integrity.release_positive_claim("SUPPORTED") is None
    assert any("post-integrity" in reason for reason in result.failure_reasons)


def test_unobservable_crash_status_is_preserved_and_fails_closed(tmp_path: Path):
    _canonical, guard = _guard(tmp_path)
    safety = PacketTracerLiveSessionSafety(
        file_guard=guard,
        runtime_health=lambda: True,
        crash_detector=lambda: None,
        active_workspace_observer=lambda: None,
    )
    safety.prepare()

    result = safety.finalize()

    assert result.crash_detected is None
    assert result.runtime_healthy is None
    assert result.session_reusable is False
    assert result.positive_claim_allowed is False
    assert any("unobservable" in reason.casefold() for reason in result.failure_reasons)


def test_silent_canonical_modification_is_detected_restored_and_still_invalidates_session(tmp_path: Path):
    canonical, guard = _guard(tmp_path)
    guard.prepare()
    canonical.write_bytes(b"corrupt despite semantic cleanup being green")

    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert integrity.observed_post_run_sha256 != integrity.identity.canonical_sha256
    assert integrity.unexpected_modification is True
    assert integrity.restoration_attempted is True
    assert integrity.restoration_verified is True
    assert integrity.verified_canonical_sha256 == _sha256(CANONICAL)
    assert canonical.read_bytes() == CANONICAL
    assert integrity.session_reusable is False
    assert integrity.release_positive_claim("SUPPORTED") is None


def test_canonical_change_racing_final_hash_is_restored_and_session_invalidated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical, guard = _guard(tmp_path)
    guard.prepare()
    original_sha256 = live_file_integrity._sha256
    canonical_calls = 0

    def race_sha256(path: Path) -> str:
        nonlocal canonical_calls
        if path.resolve() == canonical.resolve():
            canonical_calls += 1
            if canonical_calls == 2:
                canonical.write_bytes(b"late corruption")
        return original_sha256(path)

    monkeypatch.setattr(live_file_integrity, "_sha256", race_sha256)

    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert canonical.read_bytes() == CANONICAL
    assert integrity.unexpected_modification is True
    assert integrity.restoration_attempted is True
    assert integrity.restoration_verified is True
    assert integrity.session_reusable is False
    assert integrity.positive_claim_allowed is False


def test_preexisting_deterministic_restore_path_is_never_reused_or_deleted(
    tmp_path: Path,
) -> None:
    canonical, guard = _guard(tmp_path)
    guard.prepare()
    old_deterministic_stage = (
        tmp_path / ".V5.pts.poe-run_with_unsafe_separators.restore"
    )
    old_deterministic_stage.write_bytes(b"unrelated sentinel")
    canonical.write_bytes(b"corrupt canonical")

    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert canonical.read_bytes() == CANONICAL
    assert old_deterministic_stage.read_bytes() == b"unrelated sentinel"
    assert integrity.restoration_verified is True
    assert integrity.session_reusable is False


def test_deleted_canonical_pts_is_restored_but_the_session_remains_invalid(tmp_path: Path):
    canonical, guard = _guard(tmp_path)
    guard.prepare()
    canonical.unlink()

    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert integrity.observed_post_run_sha256 is None
    assert integrity.unexpected_modification is True
    assert integrity.restoration_verified is True
    assert canonical.read_bytes() == CANONICAL
    assert integrity.session_reusable is False


def test_unverifiable_runtime_health_blocks_reuse_and_positive_claim(tmp_path: Path):
    _canonical, guard = _guard(tmp_path)
    guard.prepare()

    integrity = guard.finalize(runtime_healthy=None, crash_detected=False)

    assert integrity.integrity_verified is True
    assert integrity.session_reusable is False
    assert integrity.positive_claim_allowed is False
    assert integrity.release_positive_claim("SUPPORTED") is None
    assert any("health" in reason.casefold() for reason in integrity.failure_reasons)


def test_failed_restoration_is_fail_closed_and_never_reports_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    canonical, guard = _guard(tmp_path)
    guard.prepare()
    canonical.write_bytes(b"corrupt")
    monkeypatch.setattr(guard, "_restore_canonical", lambda: (_ for _ in ()).throw(
        OSError("synthetic restore failure")
    ))

    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert integrity.unexpected_modification is True
    assert integrity.restoration_attempted is True
    assert integrity.restoration_verified is False
    assert integrity.integrity_verified is False
    assert integrity.session_reusable is False
    assert integrity.release_positive_claim("SUPPORTED") is None
    assert canonical.read_bytes() == b"corrupt"


def test_corrupted_recovery_copy_cannot_produce_false_restoration(tmp_path: Path):
    canonical, guard = _guard(tmp_path)
    guard.prepare()
    canonical.write_bytes(b"corrupt canonical")
    assert guard._backup_path is not None
    guard._backup_path.write_bytes(b"corrupt recovery copy")

    integrity = guard.finalize(runtime_healthy=True, crash_detected=False)

    assert integrity.restoration_attempted is True
    assert integrity.restoration_verified is False
    assert integrity.integrity_verified is False
    assert integrity.session_reusable is False
    assert integrity.release_positive_claim("SUPPORTED") is None


@pytest.mark.parametrize("name", ["module.pkt", "module", "module.pts.txt"])
def test_guard_rejects_a_non_pts_canonical_identity(tmp_path: Path, name: str):
    canonical = tmp_path / name
    canonical.write_bytes(CANONICAL)
    guard = PacketTracerLiveFileGuard(
        canonical_path=canonical,
        disposable_root=tmp_path / "sessions",
        run_identity="run-1",
    )

    with pytest.raises(ValueError, match=".pts"):
        guard.prepare()
