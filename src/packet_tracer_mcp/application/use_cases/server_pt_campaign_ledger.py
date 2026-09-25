"""Cumulative, protected consumption of an experimental Server-PT campaign.

The FASTLOOP charter grants 50,000 bridge operations and 21,600 seconds of
active lab time in total, and protects the last 1,000 operations and 600
seconds for final observation, cleanup and retirement. Those are ceilings for
the whole campaign, across processes and resumptions, so the ledger is a set
of write-once records from which every total is recomputed:

- an episode OPENING declares, before any contact, its question, the frozen
  source, the tests actually run, its attempts, targets, permitted effects, a
  finite operation and time allocation and its stop rule (zero operations
  declares a lifecycle-only episode, which admits no bridge phase);
- a phase ADMISSION records a phase grant against that allocation, before
  the phase binds a mailbox;
- a phase RESULT records the operations and seconds the phase really used;
- a CLOSING records when the episode ended and in what lab state.

Charging is conservative and never subtracts. A closed episode charges what
its phases used and its active seconds; a lifecycle-only episode, which has no
phase to charge, at least its whole time allocation. An open one charges at
least its whole allocation, and time keeps running while it is open. An
admitted phase without a result charges its grant maximum. Nothing here
resets on restart.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_RECORD_NAME = re.compile(
    r"episode-(\d{4})-(?:(opening|closing)|([0-9a-f]{32})-"
    r"(prequalification|setup|acceptance|cleanup|qualification)-(admission|result))\Z"
)
_RECORD_KINDS = {
    "opening": "episode_opening",
    "closing": "episode_closing",
    "admission": "phase_admission",
    "result": "phase_result",
}
_ATTEMPT = re.compile(r"[0-9a-f]{32}\Z")
#: Phases that may draw the protected reserve. Retirement costs no bridge
#: operation; its time is charged to the open episode like any other.
FINAL_ELIGIBLE_PHASES = frozenset({"cleanup"})
#: `qualification` is one governed Q-stage run (the DHCP campaign's Q3-FL
#: profiles). Its own finalization reserve is inside its grant, so it is an
#: ordinary phase and never draws the campaign's protected tail.
LEDGER_PHASES = frozenset(
    {"prequalification", "setup", "acceptance", "cleanup", "qualification"}
)


@dataclass(frozen=True)
class CampaignAllowance:
    """The charter's campaign-wide ceilings and their protected tail."""

    total_operations: int
    total_seconds: int
    protected_operations: int
    protected_seconds: int


FASTLOOP_ALLOWANCE = CampaignAllowance(
    total_operations=50_000,
    total_seconds=6 * 60 * 60,
    protected_operations=1_000,
    protected_seconds=600,
)
#: The DHCP campaign's charter states the same ceilings in its own words:
#: 50,000 bridge operations and 21,600 s in total, 1,000 and 600 protected
#: for eligible finalization. It is a separate object so that one charter's
#: numbers can never silently become the other's.
DHCP_FASTLOOP_ALLOWANCE = CampaignAllowance(
    total_operations=50_000,
    total_seconds=21_600,
    protected_operations=1_000,
    protected_seconds=600,
)
_ALLOWANCES = {
    "SERVER-PT-IOS-FASTLOOP-01": FASTLOOP_ALLOWANCE,
    "SERVER-PT-DHCP-FASTLOOP-01": DHCP_FASTLOOP_ALLOWANCE,
}


def allowance_for(campaign_id: str) -> CampaignAllowance:
    """Return the ledger ceilings one experimental campaign's charter grants.

    A campaign without a ledger allowance has no experimental ledger at all,
    so asking for one is an error rather than a default.
    """
    try:
        return _ALLOWANCES[campaign_id]
    except KeyError:
        raise ValueError(f"campaign {campaign_id!r} has no ledger allowance") from None


@dataclass(frozen=True)
class LedgerTotals:
    """What the campaign has committed, and what ordinary work may still use."""

    committed_operations: int
    committed_seconds: float
    ordinary_operations_left: int
    ordinary_seconds_left: float
    open_episode: int | None


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("ledger time is missing")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("ledger time has no zone")
    return parsed


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("ledger count is not a non-negative int")
    return value


def _seconds(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("ledger seconds are not finite and non-negative")
    return float(value)


def episode_name(episode: int) -> str:
    """Return the zero-padded stem shared by one episode's records."""
    return f"episode-{episode:04d}"


def phase_record_name(episode: int, attempt_id: str, phase: str, kind: str) -> str:
    """Return the record name of one phase admission or result."""
    return f"{episode_name(episode)}-{attempt_id}-{phase}-{kind}"


def ledger_record_findings(
    name: str,
    record: Mapping[str, object],
    records: Mapping[str, Mapping[str, object]],
) -> tuple[str, ...]:
    """Name why one record is not a complete ledger record of this ledger.

    Used before a record a hard stop left unindexed may be adopted: its name
    must be a ledger name, its content must be the record that name implies,
    its numbers must parse, and it must hang from records already present.
    """
    match = _RECORD_NAME.fullmatch(name)
    if match is None:
        return ("ledger_record_name_unknown",)
    episode = int(match.group(1))
    suffix = match.group(2) or match.group(5)
    try:
        if (
            record.get("kind") != _RECORD_KINDS[suffix]
            or _count(record.get("episode")) != episode
        ):
            return ("ledger_record_identity_mismatch",)
        if match.group(3) and (
            record.get("attempt_id") != match.group(3)
            or record.get("phase") != match.group(4)
        ):
            return ("ledger_record_identity_mismatch",)
        if suffix == "opening":
            _count(record.get("allocated_operations"))
            _seconds(record.get("allocated_seconds"))
            _time(record.get("opened_at_utc"))
            return ()
        if f"{episode_name(episode)}-opening" not in records:
            return ("ledger_record_without_opening",)
        if suffix == "closing":
            _time(record.get("closed_at_utc"))
        elif suffix == "admission":
            _count(record.get("granted_operations"))
            _seconds(record.get("granted_seconds"))
            _time(record.get("admitted_at_utc"))
        else:
            _count(record.get("used_operations"))
            _seconds(record.get("active_seconds"))
            admission = phase_record_name(
                episode, match.group(3), match.group(4), "admission"
            )
            if admission not in records:
                return ("ledger_result_without_admission",)
    except ValueError:
        return ("ledger_record_malformed",)
    return ()


def _by_kind(records: Mapping[str, Mapping[str, object]], kind: str):
    return {name: value for name, value in records.items() if value.get("kind") == kind}


def _episode_phases(
    records: Mapping[str, Mapping[str, object]], episode: int
) -> tuple[int, list[tuple[str, str, int, bool]]]:
    """Return one episode's phase charge and its admitted phases."""
    admissions = [
        value
        for value in _by_kind(records, "phase_admission").values()
        if value.get("episode") == episode
    ]
    results = {
        (value.get("attempt_id"), value.get("phase")): value
        for value in _by_kind(records, "phase_result").values()
        if value.get("episode") == episode
    }
    charge = 0
    phases: list[tuple[str, str, int, bool]] = []
    for admission in admissions:
        key = (admission.get("attempt_id"), admission.get("phase"))
        result = results.get(key)
        used = (
            _count(result.get("used_operations"))
            if result is not None
            else _count(admission.get("granted_operations"))
        )
        charge += used
        phases.append((str(key[0]), str(key[1]), used, result is not None))
    return charge, phases


def ledger_totals(
    records: Mapping[str, Mapping[str, object]],
    allowance: CampaignAllowance,
    now: datetime,
) -> LedgerTotals:
    """Recompute the committed totals from every write-once record."""
    openings = _by_kind(records, "episode_opening")
    closings = {
        value.get("episode"): value
        for value in _by_kind(records, "episode_closing").values()
    }
    operations = 0
    seconds = 0.0
    open_episode = None
    for opening in openings.values():
        episode = _count(opening.get("episode"))
        opened = _time(opening.get("opened_at_utc"))
        charge, _ = _episode_phases(records, episode)
        closing = closings.get(episode)
        if closing is not None:
            operations += charge
            elapsed = max(
                0.0, (_time(closing.get("closed_at_utc")) - opened).total_seconds()
            )
            if _count(opening.get("allocated_operations")) == 0:
                # No phase records its time, so a wall-clock step during the
                # episode must not shrink the charge below what it was given.
                elapsed = max(elapsed, _seconds(opening.get("allocated_seconds")))
            seconds += elapsed
            continue
        open_episode = episode
        operations += max(charge, _count(opening.get("allocated_operations")))
        seconds += max(
            _seconds(opening.get("allocated_seconds")),
            max(0.0, (now - opened).total_seconds()),
        )
    return LedgerTotals(
        committed_operations=operations,
        committed_seconds=seconds,
        ordinary_operations_left=(
            allowance.total_operations - allowance.protected_operations - operations
        ),
        ordinary_seconds_left=(
            allowance.total_seconds - allowance.protected_seconds - seconds
        ),
        open_episode=open_episode,
    )


def opening_findings(
    records: Mapping[str, Mapping[str, object]],
    opening: Mapping[str, object],
    allowance: CampaignAllowance,
    now: datetime,
) -> tuple[str, ...]:
    """Name what keeps one declared episode from opening now."""
    found: list[str] = []
    openings = _by_kind(records, "episode_opening")
    try:
        episode = _count(opening.get("episode"))
        operations = _count(opening.get("allocated_operations"))
        seconds = _seconds(opening.get("allocated_seconds"))
        _time(opening.get("opened_at_utc"))
    except ValueError:
        return ("episode_opening_malformed",)
    if opening.get("kind") != "episode_opening":
        found.append("episode_opening_malformed")
    if episode != len(openings) + 1:
        found.append("episode_not_next_in_sequence")
    for field in ("question", "stop_rule"):
        value = opening.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            found.append(f"episode_{field}_missing")
    for field in ("source_sha", "source_tree"):
        if not _SHA40.fullmatch(str(opening.get(field) or "")):
            found.append(f"episode_{field}_unobserved")
    attempts = opening.get("attempt_ids")
    if (
        not isinstance(attempts, list)
        or not attempts
        or any(not _ATTEMPT.fullmatch(str(item)) for item in attempts)
    ):
        found.append("episode_attempts_invalid")
    for field in ("tests_run", "targets", "permitted_effects"):
        value = opening.get(field)
        if not isinstance(value, list) or not value:
            found.append(f"episode_{field}_missing")
    # Zero operations is a lifecycle-only episode: it admits no bridge phase
    # (`phase_admission_findings`), but its time is charged like any other.
    if seconds <= 0:
        found.append("episode_allocation_not_finite_positive")
    totals = ledger_totals(records, allowance, now)
    if totals.open_episode is not None:
        found.append("another_episode_is_open")
    if operations > totals.ordinary_operations_left:
        found.append("allocation_exceeds_ordinary_operations")
    if seconds > totals.ordinary_seconds_left:
        found.append("allocation_exceeds_ordinary_seconds")
    return tuple(found)


def phase_admission_findings(
    records: Mapping[str, Mapping[str, object]],
    *,
    episode: int,
    attempt_id: str,
    phase: str,
    granted_operations: int,
    granted_seconds: float,
    allowance: CampaignAllowance,
    now: datetime,
    source_sha: str,
    source_tree: str,
) -> tuple[tuple[str, ...], bool]:
    """Decide whether one phase grant fits its open episode, and how.

    Returns the findings and whether the phase draws the protected reserve.
    The phase must execute the exact checkpoint its episode declared: an
    episode opened for one commit never admits effects from another. An
    ordinary phase must fit what its episode has left. Only cleanup may
    exceed that, and only by as much as the whole campaign has left.
    """
    if phase not in LEDGER_PHASES:
        return ("ledger_phase_unknown",), False
    openings = {
        value.get("episode"): value
        for value in _by_kind(records, "episode_opening").values()
    }
    opening = openings.get(episode)
    if opening is None:
        return ("episode_not_opened",), False
    if any(
        value.get("episode") == episode
        for value in _by_kind(records, "episode_closing").values()
    ):
        return ("episode_already_closed",), False
    if attempt_id not in (opening.get("attempt_ids") or []):
        return ("attempt_not_declared_by_episode",), False
    if _count(opening.get("allocated_operations")) == 0:
        # A lifecycle-only episode: not even cleanup draws the reserve.
        return ("episode_allocates_no_bridge_operation",), False
    if (
        not source_sha
        or not source_tree
        or (source_sha, source_tree)
        != (opening.get("source_sha"), opening.get("source_tree"))
    ):
        return ("phase_source_differs_from_episode",), False
    charge, phases = _episode_phases(records, episode)
    if any(item[:2] == (attempt_id, phase) for item in phases):
        return ("phase_already_admitted",), False
    # A phase whose result never arrived (a hard stop between admission and
    # result) is charged at its grant maximum above. It must not block the
    # cleanup that the lost phase may have made necessary.
    elapsed = max(0.0, (now - _time(opening.get("opened_at_utc"))).total_seconds())
    ordinary_fit = charge + granted_operations <= _count(
        opening.get("allocated_operations")
    ) and elapsed + granted_seconds <= _seconds(opening.get("allocated_seconds"))
    if ordinary_fit:
        return (), False
    if phase not in FINAL_ELIGIBLE_PHASES:
        return ("phase_exceeds_episode_allocation",), False
    totals = ledger_totals(records, allowance, now)
    others_operations = totals.committed_operations - max(
        charge, _count(opening.get("allocated_operations"))
    )
    others_seconds = totals.committed_seconds - max(
        _seconds(opening.get("allocated_seconds")), elapsed
    )
    if (
        others_operations + charge + granted_operations > allowance.total_operations
        or others_seconds + elapsed + granted_seconds > allowance.total_seconds
    ):
        return ("campaign_allowance_exhausted",), False
    return (), True


def episode_allowance_left(
    records: Mapping[str, Mapping[str, object]],
    episode: int,
    now: datetime,
) -> tuple[int, float]:
    """Return what one opened episode still admits for an ordinary phase."""
    for opening in _by_kind(records, "episode_opening").values():
        if opening.get("episode") != episode:
            continue
        charge, _ = _episode_phases(records, episode)
        elapsed = max(0.0, (now - _time(opening.get("opened_at_utc"))).total_seconds())
        return (
            _count(opening.get("allocated_operations")) - charge,
            _seconds(opening.get("allocated_seconds")) - elapsed,
        )
    raise ValueError("episode is not opened")


def closing_findings(
    records: Mapping[str, Mapping[str, object]], episode: int, now: datetime
) -> tuple[str, ...]:
    """Require an episode that is open now; closing never forgives a charge.

    A closing earlier than its own opening is refused rather than charged as
    zero seconds.
    """
    openings = {
        value.get("episode"): value
        for value in _by_kind(records, "episode_opening").values()
    }
    if episode not in openings:
        return ("episode_not_opened",)
    if any(
        value.get("episode") == episode
        for value in _by_kind(records, "episode_closing").values()
    ):
        return ("episode_already_closed",)
    if now < _time(openings[episode].get("opened_at_utc")):
        return ("episode_closing_precedes_opening",)
    return ()


def unsettled_phases(
    records: Mapping[str, Mapping[str, object]], episode: int
) -> tuple[str, ...]:
    """Name admitted phases without a result; each stays charged at its grant."""
    _, phases = _episode_phases(records, episode)
    return tuple(
        f"{attempt}:{phase}" for attempt, phase, _used, settled in phases if not settled
    )


def qualification_admitted(
    records: Mapping[str, Mapping[str, object]], attempt_id: str
) -> bool:
    """Whether any episode admitted a qualification phase for this attempt."""
    return any(
        value.get("kind") == "phase_admission"
        and value.get("phase") == "qualification"
        and value.get("attempt_id") == attempt_id
        for value in records.values()
    )


def episode_attempts(
    records: Mapping[str, Mapping[str, object]], episode: int
) -> Sequence[str]:
    """Return the attempts one opened episode declared."""
    for value in _by_kind(records, "episode_opening").values():
        if value.get("episode") == episode:
            return tuple(str(item) for item in value.get("attempt_ids") or ())
    return ()
