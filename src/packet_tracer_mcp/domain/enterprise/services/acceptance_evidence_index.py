"""Indexes an acceptance judgement reads from, each built once.

Judging a thousand clients by scanning the whole ledger and every record row
per client is quadratic in the evidence. These indexes are built in one pass
each -- ledger entries by purpose, record verification rows by expectation,
readiness episodes by group and ordinal -- so a client's judgement costs
lookups in its own evidence, and the whole assembly is linear in the
retained evidence plus the selected relationships.

They hold references to the evidence, never copies or reinterpretations, and a
lookup that finds nothing returns nothing rather than a default fact.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models.service_qualification import OperationEntry
from ..models.service_run_record import ServiceRunRecord

E6_VERIFY_PREFIX = "e6_verify:"
OWNED_RELEASE_PREFIX = "owned_release:"
#: A scalable readiness dispatch is `readiness:<group key>#<episode ordinal>`.
READINESS_PREFIX = "readiness:"


@dataclass
class LedgerIndex:
    """Ledger positions by purpose, for dispatched and refused entries."""

    dispatched: dict[str, list[int]] = field(default_factory=dict)
    refused: dict[str, list[int]] = field(default_factory=dict)
    entries: Sequence[OperationEntry] = ()

    @classmethod
    def build(cls, entries: Sequence[OperationEntry]) -> LedgerIndex:
        """Index every entry by its purpose, in ledger order."""
        index = cls(entries=entries)
        for position, item in enumerate(entries):
            bucket = index.dispatched if item.seq > 0 else index.refused
            if item.seq > 0 or item.refused:
                bucket.setdefault(item.purpose, []).append(position)
        return index

    def positions(self, purpose: str) -> list[int]:
        """Return the ledger positions of every dispatch with this purpose."""
        return self.dispatched.get(purpose, [])

    def dispatches(self, purpose: str) -> list[OperationEntry]:
        """Return the dispatched entries of one purpose."""
        return [self.entries[item] for item in self.positions(purpose)]

    def refusals(self, purpose: str) -> list[OperationEntry]:
        """Return the refused entries of one purpose."""
        return [self.entries[item] for item in self.refused.get(purpose, [])]

    def purposes(self) -> list[str]:
        """Return every purpose that dispatched at least once."""
        return list(self.dispatched)


def verification_rows(record: ServiceRunRecord | None) -> dict[str, Any]:
    """Index the record's E6 verification rows by expectation id, once."""
    if record is None or record.service_result is None:
        return {}
    rows: dict[str, Any] = {}
    for item in record.service_result.verification_results:
        rows.setdefault(item.expectation_id, item)
    return rows


def readiness_episode_spans(
    ledger: LedgerIndex,
) -> dict[str, dict[int, tuple[int, int]]]:
    """Return, per group key and episode ordinal, its first and last dispatch.

    One pass over the ledger's purposes. A readiness purpose without a valid
    `#<ordinal>` suffix names no episode and is not an episode of any group.
    """
    spans: dict[str, dict[int, tuple[int, int]]] = {}
    for purpose in ledger.purposes():
        if not purpose.startswith(READINESS_PREFIX):
            continue
        key, marker, ordinal = purpose[len(READINESS_PREFIX) :].rpartition("#")
        if not marker or not key or not ordinal.isdigit():
            continue
        positions = ledger.positions(purpose)
        spans.setdefault(key, {})[int(ordinal)] = (positions[0], positions[-1])
    return spans
