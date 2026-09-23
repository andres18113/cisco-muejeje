"""Indexes an acceptance judgement reads from, each built once.

Judging a thousand clients by scanning the whole ledger and every record row
per client is quadratic in the evidence. These indexes are built in one pass
each -- ledger entries by purpose, record verification rows by expectation,
readiness rows by group identity -- so a client's judgement costs lookups in
its own evidence, and the whole assembly is linear in the retained evidence
plus the selected relationships.

They hold references to the evidence, never copies or reinterpretations, and a
lookup that finds nothing returns nothing rather than a default fact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models.service_qualification import OperationEntry
from ..models.service_run_record import ServiceRunRecord

E6_VERIFY_PREFIX = "e6_verify:"
OWNED_RELEASE_PREFIX = "owned_release:"


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


@dataclass
class ReadinessIndex:
    """Readiness rows by group identity, with each row's dependents indexed."""

    access: dict[tuple[str, int], list[Mapping[str, Any]]] = field(default_factory=dict)
    continuity: dict[tuple[int, frozenset[str]], list[Mapping[str, Any]]] = field(
        default_factory=dict
    )
    dependents: dict[int, dict[str, Mapping[str, Any]]] = field(default_factory=dict)

    @classmethod
    def build(cls, rows: Sequence[object]) -> ReadinessIndex:
        """Index each row once; a malformed row is skipped, never repaired."""
        index = cls()
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            dependents = {
                str(item.get("expectation_id")): item
                for item in (row.get("dependents") or [])
                if isinstance(item, Mapping)
            }
            index.dependents[id(row)] = dependents
            vlan = row.get("vlan_id")
            if not isinstance(vlan, int):
                continue
            if row.get("kind") == "trunk_continuity":
                names = row.get("switch_device_names")
                if isinstance(names, list):
                    key = (vlan, frozenset(str(item) for item in names))
                    index.continuity.setdefault(key, []).append(row)
            elif "kind" not in row:
                name = row.get("switch_device_name")
                if isinstance(name, str):
                    index.access.setdefault((name, vlan), []).append(row)
        return index

    def dependent(
        self, row: Mapping[str, Any], expectation_id: str
    ) -> Mapping[str, Any] | None:
        """Return one row's dependent entry for one expectation."""
        return self.dependents.get(id(row), {}).get(expectation_id)

    def admitting_row(
        self, rows: Sequence[Mapping[str, Any]], expectation_id: str
    ) -> Mapping[str, Any] | None:
        """Return the last row of a group that admitted this expectation."""
        chosen = None
        for row in rows:
            dependent = self.dependent(row, expectation_id)
            if dependent is not None and dependent.get("admitted") is True:
                chosen = row
        return chosen
