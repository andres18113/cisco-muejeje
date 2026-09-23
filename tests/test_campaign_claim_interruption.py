"""An interrupted campaign claim leaves only what its caller can account for.

The claim is two exclusive creations: the campaign lock, then the permanent
attempt marker. An interruption can land after either one. What it may leave
behind is fixed here: a lock whose attempt was not reserved is rolled back; a
reserved attempt keeps its marker and its lock, and the caller that chose the
holder can recover the claim to finish and release it. A marker is never
deleted, and every file that exists holds its complete payload.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    LOCK_NAME,
    CampaignCoordinationError,
    FileCampaignCoordinator,
)

ATTEMPT = "0123456789abcdef0123456789abcdef"
HOLDER = "fedcba9876543210fedcba9876543210"


class _InterruptedAfter(FileCampaignCoordinator):
    """Raise one KeyboardInterrupt right after the named file is created."""

    def __init__(self, scope: Path, name: str) -> None:
        super().__init__(scope)
        self.name = name

    def _create_exclusive(self, path, payload, reason):
        super()._create_exclusive(path, payload, reason)
        if path.name == self.name:
            raise KeyboardInterrupt


def _marker(scope: Path) -> Path:
    return scope / f"attempt-{ATTEMPT}.json"


def test_an_interruption_after_the_lock_rolls_the_lock_back(tmp_path: Path):
    """No attempt was reserved, so nothing of this claim may stay held."""
    scope = tmp_path / "campaign"
    coordinator = _InterruptedAfter(scope, LOCK_NAME)

    with pytest.raises(KeyboardInterrupt):
        coordinator.claim(attempt_id=ATTEMPT, holder=HOLDER)

    assert not (scope / LOCK_NAME).exists()
    assert not _marker(scope).exists()
    assert coordinator.recover(attempt_id=ATTEMPT, holder=HOLDER) is None
    assert FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT).attempt_id == (
        ATTEMPT
    )


def test_an_interruption_after_the_marker_leaves_a_recoverable_claim(
    tmp_path: Path,
):
    """The spent attempt keeps its marker; its holder recovers and releases it."""
    scope = tmp_path / "campaign"
    coordinator = _InterruptedAfter(scope, _marker(scope).name)

    with pytest.raises(KeyboardInterrupt):
        coordinator.claim(attempt_id=ATTEMPT, holder=HOLDER)

    assert coordinator.recover(attempt_id=ATTEMPT, holder="0" * 32) is None
    claim = coordinator.recover(attempt_id=ATTEMPT, holder=HOLDER)
    assert claim is not None
    assert claim.holder == HOLDER
    assert coordinator.verify(claim) == ()
    assert coordinator.release(claim) == ()
    assert not (scope / LOCK_NAME).exists()
    assert json.loads(_marker(scope).read_text(encoding="utf-8"))["holder"] == HOLDER
    with pytest.raises(CampaignCoordinationError, match="already_reserved"):
        FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT)


def test_an_unrecoverable_reservation_does_not_keep_the_campaign_held(
    tmp_path: Path,
):
    """Without a caller-chosen holder nobody could release the lock, so it goes."""
    scope = tmp_path / "campaign"
    coordinator = _InterruptedAfter(scope, _marker(scope).name)

    with pytest.raises(KeyboardInterrupt):
        coordinator.claim(attempt_id=ATTEMPT)

    assert not (scope / LOCK_NAME).exists()
    assert _marker(scope).exists()
    with pytest.raises(CampaignCoordinationError, match="already_reserved"):
        FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT)
    assert FileCampaignCoordinator(scope).claim(attempt_id="f" * 32).holder


def test_an_interruption_while_writing_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A file exists only with its whole payload, so ownership is always readable."""
    from packet_tracer_mcp.infrastructure.persistence import campaign_coordination

    scope = tmp_path / "campaign"
    real_dump = json.dump

    def interrupted_dump(payload, stream):
        # Half the payload reaches the file, then the interruption lands.
        text = json.dumps(payload)
        stream.write(text[: len(text) // 2])
        stream.flush()
        raise KeyboardInterrupt

    monkeypatch.setattr(campaign_coordination.json, "dump", interrupted_dump)
    with pytest.raises(KeyboardInterrupt):
        FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT, holder=HOLDER)
    monkeypatch.setattr(campaign_coordination.json, "dump", real_dump)

    assert sorted(item.name for item in scope.iterdir()) == []
    assert FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT).attempt_id == (
        ATTEMPT
    )


def test_recovery_never_answers_for_an_unreadable_marker(tmp_path: Path):
    """An unreadable marker is an unknown reservation, never an absent one."""
    scope = tmp_path / "campaign"
    scope.mkdir()
    _marker(scope).write_text("{", encoding="utf-8")

    with pytest.raises(CampaignCoordinationError, match="reservation_unreadable"):
        FileCampaignCoordinator(scope).recover(attempt_id=ATTEMPT, holder=HOLDER)

    assert _marker(scope).read_text(encoding="utf-8") == "{"


def test_recovery_answers_none_only_for_an_absent_or_foreign_marker(
    tmp_path: Path,
):
    """None is proof that this holder reserved nothing."""
    scope = tmp_path / "campaign"
    coordinator = FileCampaignCoordinator(scope)

    assert coordinator.recover(attempt_id=ATTEMPT, holder=HOLDER) is None
    coordinator.claim(attempt_id=ATTEMPT, holder="0" * 32)
    assert coordinator.recover(attempt_id=ATTEMPT, holder=HOLDER) is None


def test_abandon_removes_only_this_holders_lock_and_never_a_marker(
    tmp_path: Path,
):
    """A lock that names this holder is this holder's to remove; nothing else."""
    scope = tmp_path / "campaign"
    coordinator = FileCampaignCoordinator(scope)
    coordinator.claim(attempt_id=ATTEMPT, holder=HOLDER)

    assert coordinator.abandon(holder="0" * 32) is False
    assert (scope / LOCK_NAME).exists()
    assert coordinator.abandon(holder=HOLDER) is True
    assert not (scope / LOCK_NAME).exists()
    assert _marker(scope).exists()
    assert coordinator.abandon(holder=HOLDER) is False


@pytest.mark.parametrize("holder", ["", "../x", "a b"])
def test_a_caller_chosen_holder_must_be_a_safe_name(tmp_path: Path, holder: str):
    """The holder reaches a file's payload and its later comparison, never a path."""
    scope = tmp_path / "campaign"

    with pytest.raises(CampaignCoordinationError, match="holder"):
        FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT, holder=holder)

    assert not (scope / LOCK_NAME).exists()
