"""Exclusive campaign access and atomic attempt reservation across checkouts.

A qualification record store is per checkout, so two worktrees running the same
campaign never see each other's records: scanning them decides nothing about
concurrency. What the two do share is the fixed file mailbox under
`%LOCALAPPDATA%`, because that is the channel a Packet Tracer instance polls.
Exclusion is therefore taken there, beside the resource it protects.

The claim is one exclusive file creation. It is never reclaimed by age, never
inspected for staleness and never removed on another holder's behalf: an
existing claim refuses admission and is left exactly as it was found, because a
claim whose owner is still running is indistinguishable from one whose owner
died, and guessing wrong is the failure this control exists to prevent.

Scope of what a claim proves: one cooperating Python campaign writer. It says
nothing about which Packet Tracer instance answers the mailbox, which the
lifecycle pairing decides, and nothing about a program that mutates the same
workspace by other means.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ...shared.utils import resolve_within, safe_name_component
from ..execution.file_bridge import bridge_dir

#: The coordination scope lives beside the mailbox, not inside it, so a claim
#: file can never be mistaken for a pending command by the bridge or by the
#: lifecycle reader's `req_*`/`res_*` inspection.
CAMPAIGN_SUBDIR = "campaign"
LOCK_NAME = "campaign.lock"


class CampaignCoordinationError(RuntimeError):
    """A campaign claim could not be taken in the shared coordination scope."""


@dataclass(frozen=True)
class CampaignClaim:
    """What one admitted writer holds from admission through finalization."""

    scope: Path
    lock_path: Path
    attempt_path: Path
    #: Unique per claim. It is what distinguishes this holder from another
    #: process that happens to share a PID after a restart.
    holder: str
    attempt_id: str

    def compact_summary(self) -> dict[str, object]:
        """Return what the record stores about this claim."""
        return {
            "scope": str(self.scope),
            "holder": self.holder,
            "attempt_id": self.attempt_id,
        }


class FileCampaignCoordinator:
    """Take, verify and release one campaign claim in the shared mailbox scope."""

    def __init__(self, scope_dir: Path | None = None) -> None:
        """Bind the coordinator to its scope without touching the filesystem."""
        self._scope = (
            Path(scope_dir) if scope_dir is not None else bridge_dir() / CAMPAIGN_SUBDIR
        )

    @property
    def scope(self) -> Path:
        """Return the coordination directory this coordinator uses."""
        return self._scope

    def claim(self, *, attempt_id: str) -> CampaignClaim:
        """Hold the campaign exclusively and reserve this attempt, atomically.

        The two exclusive creations happen in one order and are not separable:
        the campaign lock first, so only one writer is ever inside the attempt
        reservation, and the attempt marker second, so an identity that has
        already been used cannot be reserved a second time by anyone.

        Raises `CampaignCoordinationError` when either is already held. The
        caller refuses; nothing existing is deleted on the way out.
        """
        safe_attempt = safe_name_component(attempt_id, "")
        if not attempt_id or safe_attempt != attempt_id:
            raise CampaignCoordinationError(
                "campaign_attempt_identity_is_not_a_safe_name"
            )
        try:
            self._scope.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock_path = resolve_within(self._scope, LOCK_NAME)
            attempt_path = resolve_within(self._scope, f"attempt-{safe_attempt}.json")
        except OSError as exc:
            raise CampaignCoordinationError(
                f"campaign_scope_unavailable:{type(exc).__name__}"
            ) from exc
        except ValueError as exc:
            raise CampaignCoordinationError(
                f"campaign_scope_escaped:{type(exc).__name__}"
            ) from exc
        holder = uuid4().hex
        payload = {
            "holder": holder,
            "attempt_id": attempt_id,
            "pid": os.getpid(),
            "claimed_at": datetime.now(UTC).isoformat(),
        }
        self._create_exclusive(lock_path, payload, "campaign_already_claimed")
        try:
            self._create_exclusive(
                attempt_path, payload, "campaign_attempt_already_reserved"
            )
        except CampaignCoordinationError:
            # The attempt is not ours, so neither is the campaign. The lock we
            # just created is ours and only ours, so removing it here is not a
            # reclaim of somebody else's file.
            self._remove_own(lock_path, holder)
            raise
        return CampaignClaim(
            scope=self._scope,
            lock_path=lock_path,
            attempt_path=attempt_path,
            holder=holder,
            attempt_id=attempt_id,
        )

    def verify(self, claim: CampaignClaim) -> tuple[str, ...]:
        """Name what the shared scope now says about this claim, if anything.

        An empty tuple means the campaign is still held by this holder. Every
        other answer is a reason the exclusion no longer covers what follows:
        the lock is gone, it is unreadable, or it names a different holder.
        """
        try:
            stored = json.loads(claim.lock_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ("campaign_claim:released_by_someone_else",)
        except OSError as exc:
            return (f"campaign_claim:unreadable:{type(exc).__name__}",)
        except ValueError:
            return ("campaign_claim:malformed",)
        if not isinstance(stored, dict):
            return ("campaign_claim:malformed",)
        holder = stored.get("holder")
        attempt_id = stored.get("attempt_id")
        if (
            not isinstance(holder, str)
            or not holder
            or not isinstance(attempt_id, str)
            or not attempt_id
        ):
            return ("campaign_claim:malformed",)
        if holder != claim.holder:
            return ("campaign_claim:held_by_another_writer",)
        if attempt_id != claim.attempt_id:
            return ("campaign_claim:malformed",)
        return ()

    def release(self, claim: CampaignClaim) -> tuple[str, ...]:
        """Release this holder's campaign lock and name whatever it could not.

        The attempt marker is deliberately not removed: an attempt identity is
        spent once and stays spent, and that permanence is the reservation.
        """
        reasons = self.verify(claim)
        if reasons:
            return tuple(f"campaign_release_skipped:{item}" for item in reasons)
        removed = self._remove_own(claim.lock_path, claim.holder)
        return () if removed else ("campaign_claim:release_unverified",)

    def _create_exclusive(
        self, path: Path, payload: dict[str, object], reason: str
    ) -> None:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise CampaignCoordinationError(reason) from exc
        except OSError as exc:
            raise CampaignCoordinationError(
                f"campaign_claim_failed:{type(exc).__name__}"
            ) from exc
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
        except OSError as exc:
            # The file is ours -- nothing else could have created it -- so
            # clearing a half-written claim of our own is not a reclaim.
            self._remove_own(path, str(payload["holder"]))
            raise CampaignCoordinationError(
                f"campaign_claim_unwritable:{type(exc).__name__}"
            ) from exc

    @staticmethod
    def _remove_own(path: Path, holder: str) -> bool:
        """Delete `path` only while it still names `holder`; never otherwise."""
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(stored, dict) or stored.get("holder") != holder:
            return False
        try:
            path.unlink()
        except OSError:
            return False
        return True
