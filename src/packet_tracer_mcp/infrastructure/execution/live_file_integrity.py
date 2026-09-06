"""Fail-closed file integrity for governed Packet Tracer LIVE sessions.

The guard prepares a disposable copy for Packet Tracer and treats the original
``.pts`` file as canonical, read-only input.  It records exact SHA-256 identity
before and after the run, restores unexpected changes from a private pre-run
copy, and never releases a positive claim after a crash or unverifiable health.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypeVar

from ...domain.enterprise.models.discovery import LiveSessionSafetyEvidence
from ...shared.utils import resolve_within, safe_name_component


_T = TypeVar("_T")


@dataclass(frozen=True)
class PacketTracerLiveFileIdentity:
    canonical_path: str
    canonical_sha256: str
    disposable_path: str
    disposable_sha256: str


@dataclass(frozen=True)
class PacketTracerLiveSessionIntegrity:
    identity: PacketTracerLiveFileIdentity
    observed_post_run_sha256: str | None
    observed_disposable_post_run_sha256: str | None
    verified_canonical_sha256: str | None
    unexpected_modification: bool | None
    disposable_modified: bool | None
    restoration_attempted: bool
    restoration_verified: bool | None
    runtime_healthy: bool | None
    crash_detected: bool | None
    integrity_verified: bool
    session_reusable: bool
    positive_claim_allowed: bool
    failure_reasons: tuple[str, ...]

    def release_positive_claim(self, claim: _T) -> _T | None:
        """Expose a positive claim only after every outer-session gate passed."""

        return claim if self.positive_claim_allowed else None


class PacketTracerLiveFileGuard:
    """Protect one exact canonical ``.pts`` file around one LIVE session."""

    def __init__(
        self,
        *,
        canonical_path: Path,
        disposable_root: Path,
        run_identity: str,
    ) -> None:
        self._canonical_path = Path(canonical_path)
        self._disposable_root = Path(disposable_root)
        self._run_identity = run_identity
        self._identity: PacketTracerLiveFileIdentity | None = None
        self._backup_path: Path | None = None
        self._finalized = False

    def prepare(self) -> PacketTracerLiveFileIdentity:
        """Pin the canonical identity and create the only file PT should open."""

        if self._identity is not None:
            raise RuntimeError("Packet Tracer LIVE file guard was already prepared.")
        canonical = self._canonical_path.resolve()
        if canonical.suffix.casefold() != ".pts":
            raise ValueError("The canonical Packet Tracer file must have a .pts suffix.")
        if not canonical.is_file():
            raise FileNotFoundError(
                f"Canonical Packet Tracer file does not exist: {canonical}"
            )

        root = self._disposable_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        run_component = safe_name_component(self._run_identity, fallback="live-run")
        session_directory = resolve_within(root, run_component)
        session_directory.mkdir(parents=False, exist_ok=False)
        # The session directory already carries the sanitized run identity.
        # Fixed role names cannot collide after component truncation, and the
        # recovery copy deliberately is not a .pts file Packet Tracer may open.
        disposable_name = "packet-tracer-live.pts"
        backup_name = "canonical.pre-run.backup"
        disposable = resolve_within(session_directory, disposable_name)
        backup = resolve_within(session_directory, backup_name)
        if disposable == backup or disposable.suffix.casefold() != ".pts":
            raise RuntimeError("Disposable and recovery file identities are unsafe.")

        canonical_sha256 = _sha256(canonical)
        shutil.copy2(canonical, backup)
        shutil.copy2(canonical, disposable)
        backup_sha256 = _sha256(backup)
        disposable_sha256 = _sha256(disposable)
        if not (
            backup_sha256 == canonical_sha256 == disposable_sha256
        ):
            raise OSError("Disposable Packet Tracer file preparation changed bytes.")

        self._canonical_path = canonical
        self._backup_path = backup
        self._identity = PacketTracerLiveFileIdentity(
            canonical_path=str(canonical),
            canonical_sha256=canonical_sha256,
            disposable_path=str(disposable),
            disposable_sha256=disposable_sha256,
        )
        return self._identity

    def finalize(
        self,
        *,
        runtime_healthy: bool | None,
        crash_detected: bool,
    ) -> PacketTracerLiveSessionIntegrity:
        """Verify/restore the canonical file and close reuse/claim gates."""

        if self._identity is None or self._backup_path is None:
            raise RuntimeError("Packet Tracer LIVE file guard was not prepared.")
        if self._finalized:
            raise RuntimeError("Packet Tracer LIVE file guard was already finalized.")
        self._finalized = True
        reasons: list[str] = []

        post_hash: str | None
        try:
            post_hash = _sha256(self._canonical_path)
        except ValueError:
            post_hash = None
            unexpected_modification = (
                True if not self._canonical_path.exists() else None
            )
        except OSError:
            post_hash = None
            unexpected_modification = None
        else:
            unexpected_modification = (
                post_hash != self._identity.canonical_sha256
            )
        disposable_path = Path(self._identity.disposable_path)
        try:
            disposable_post_hash = _sha256(disposable_path)
        except ValueError:
            disposable_post_hash = None
            disposable_modified = True if not disposable_path.exists() else None
        except OSError:
            disposable_post_hash = None
            disposable_modified = None
        else:
            disposable_modified = (
                disposable_post_hash != self._identity.disposable_sha256
            )
        restoration_attempted = unexpected_modification is not False
        restoration_verified: bool | None = None
        if restoration_attempted:
            reasons.append(
                "Canonical .pts integrity changed or could not be verified after LIVE."
            )
            self._attempt_restoration(reasons)

        verified_hash: str | None
        try:
            verified_hash = _sha256(self._canonical_path)
        except (OSError, ValueError):
            verified_hash = None
        if (
            not restoration_attempted
            and verified_hash != self._identity.canonical_sha256
        ):
            # Detect a modification racing the first post-run hash.  Recovery
            # is attempted, but the session remains permanently non-reusable.
            restoration_attempted = True
            unexpected_modification = (
                True if verified_hash is not None else None
            )
            reasons.append(
                "Canonical .pts changed or became unobservable during final verification."
            )
            self._attempt_restoration(reasons)
            try:
                verified_hash = _sha256(self._canonical_path)
            except (OSError, ValueError):
                verified_hash = None
        if restoration_attempted:
            restoration_verified = (
                verified_hash == self._identity.canonical_sha256
            )
            if not restoration_verified:
                reasons.append("Canonical .pts restoration could not be verified.")

        canonical_integrity_verified = (
            verified_hash == self._identity.canonical_sha256
        )
        if disposable_modified is not False:
            reasons.append(
                "Disposable .pts integrity changed or could not be verified after LIVE."
            )
        integrity_verified = (
            canonical_integrity_verified and disposable_modified is False
        )
        if crash_detected:
            reasons.append("Packet Tracer crash detected during the governed LIVE session.")
        if runtime_healthy is None:
            reasons.append("Packet Tracer runtime health is unobservable after LIVE.")
        elif runtime_healthy is False and not crash_detected:
            reasons.append("Packet Tracer runtime health check failed after LIVE.")

        session_reusable = (
            runtime_healthy is True
            and not crash_detected
            and integrity_verified
            and unexpected_modification is False
        )
        return PacketTracerLiveSessionIntegrity(
            identity=self._identity,
            observed_post_run_sha256=post_hash,
            observed_disposable_post_run_sha256=disposable_post_hash,
            verified_canonical_sha256=verified_hash,
            unexpected_modification=unexpected_modification,
            disposable_modified=disposable_modified,
            restoration_attempted=restoration_attempted,
            restoration_verified=restoration_verified,
            runtime_healthy=runtime_healthy,
            crash_detected=crash_detected,
            integrity_verified=integrity_verified,
            session_reusable=session_reusable,
            positive_claim_allowed=session_reusable,
            failure_reasons=tuple(reasons),
        )

    def _attempt_restoration(self, reasons: list[str]) -> None:
        try:
            self._restore_canonical()
        except (OSError, ValueError) as exc:
            reasons.append(f"Canonical .pts restoration failed: {exc}")

    def _restore_canonical(self) -> None:
        assert self._identity is not None
        assert self._backup_path is not None
        restore_prefix = safe_name_component(
            f".{self._canonical_path.stem}.{self._run_identity}.",
            fallback="packet-tracer-module.",
        )
        restore_fd, restore_name = tempfile.mkstemp(
            dir=self._canonical_path.parent,
            prefix=restore_prefix,
            suffix=".restore",
        )
        restore_path = Path(restore_name)
        try:
            target = os.fdopen(restore_fd, "wb")
            restore_fd = -1
            with self._backup_path.open("rb") as source, target:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            if _sha256(restore_path) != self._identity.canonical_sha256:
                raise OSError("staged canonical .pts restoration hash mismatch")
            os.replace(restore_path, self._canonical_path)
        finally:
            if restore_fd >= 0:
                os.close(restore_fd)
            if restore_path != self._canonical_path and restore_path.exists():
                restore_path.unlink()


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PacketTracerLiveSessionSafety:
    """Bind file integrity and runtime/crash probes to the application port."""

    def __init__(
        self,
        *,
        file_guard: PacketTracerLiveFileGuard,
        runtime_health: Callable[[], bool | None],
        crash_detector: Callable[[], bool | None],
    ) -> None:
        self._file_guard = file_guard
        self._runtime_health = runtime_health
        self._crash_detector = crash_detector
        self.integrity: PacketTracerLiveSessionIntegrity | None = None

    def prepare(self) -> PacketTracerLiveFileIdentity:
        return self._file_guard.prepare()

    def finalize(self) -> LiveSessionSafetyEvidence:
        pre_health, pre_crash, pre_reasons = self._sample_runtime_state(
            phase="pre-integrity"
        )
        self.integrity = self._file_guard.finalize(
            runtime_healthy=(pre_health if pre_crash is not None else None),
            crash_detected=pre_crash is True,
        )
        post_health, post_crash, post_reasons = self._sample_runtime_state(
            phase="post-integrity"
        )
        crash_state = self._combine_crash_samples(pre_crash, post_crash)
        runtime_healthy = self._combine_health_samples(pre_health, post_health)
        if crash_state is None:
            runtime_healthy = None

        reasons = list(self.integrity.failure_reasons)
        reasons.extend(pre_reasons)
        reasons.extend(post_reasons)
        if crash_state is True and self.integrity.crash_detected is not True:
            reasons.append(
                "Packet Tracer crash detected by the post-integrity sample."
            )
        if runtime_healthy is False and self.integrity.runtime_healthy is not False:
            reasons.append(
                "Packet Tracer runtime health failed in the post-integrity sample."
            )
        if crash_state is None:
            reasons.append(
                "Packet Tracer crash status is not observable across both "
                "integrity boundary samples."
            )
        if runtime_healthy is None:
            reasons.append(
                "Packet Tracer runtime health is not observable across both "
                "integrity boundary samples."
            )

        session_reusable = (
            runtime_healthy is True
            and crash_state is False
            and self.integrity.integrity_verified
            and self.integrity.unexpected_modification is False
        )
        self.integrity = replace(
            self.integrity,
            runtime_healthy=runtime_healthy,
            crash_detected=crash_state,
            session_reusable=session_reusable,
            positive_claim_allowed=session_reusable,
            failure_reasons=tuple(reasons),
        )
        identity = self.integrity.identity
        return LiveSessionSafetyEvidence(
            canonical_path=identity.canonical_path,
            canonical_pre_run_sha256=identity.canonical_sha256,
            canonical_observed_post_run_sha256=(
                self.integrity.observed_post_run_sha256
            ),
            canonical_verified_sha256=self.integrity.verified_canonical_sha256,
            disposable_path=identity.disposable_path,
            disposable_pre_run_sha256=identity.disposable_sha256,
            disposable_post_run_sha256=(
                self.integrity.observed_disposable_post_run_sha256
            ),
            unexpected_canonical_modification=(
                self.integrity.unexpected_modification
            ),
            disposable_modified=self.integrity.disposable_modified,
            restoration_attempted=self.integrity.restoration_attempted,
            restoration_verified=self.integrity.restoration_verified,
            runtime_healthy=self.integrity.runtime_healthy,
            session_reusable=self.integrity.session_reusable,
            positive_claim_allowed=self.integrity.positive_claim_allowed,
            integrity_verified=self.integrity.integrity_verified,
            crash_detected=self.integrity.crash_detected,
            failure_reasons=reasons,
        )

    def _sample_runtime_state(
        self,
        *,
        phase: str,
    ) -> tuple[bool | None, bool | None, list[str]]:
        reasons: list[str] = []
        try:
            crash_state = self._crash_detector()
        except Exception as exc:
            crash_state = None
            reasons.append(
                f"Packet Tracer crash status is unobservable at {phase}: {exc}"
            )
        try:
            runtime_healthy = self._runtime_health()
        except Exception as exc:
            runtime_healthy = None
            reasons.append(
                f"Packet Tracer runtime health check failed at {phase}: {exc}"
            )
        return runtime_healthy, crash_state, reasons

    @staticmethod
    def _combine_crash_samples(
        before: bool | None,
        after: bool | None,
    ) -> bool | None:
        if before is True or after is True:
            return True
        if before is False and after is False:
            return False
        return None

    @staticmethod
    def _combine_health_samples(
        before: bool | None,
        after: bool | None,
    ) -> bool | None:
        if before is False or after is False:
            return False
        if before is True and after is True:
            return True
        return None
