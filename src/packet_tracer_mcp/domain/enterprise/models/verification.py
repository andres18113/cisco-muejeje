"""Verification-only dependency graph, separate from application ordering."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import Enum, StrEnum
from heapq import heappop, heappush
from typing import Any, Protocol

from pydantic import BaseModel


class PrerequisiteKind(StrEnum):
    """What one verification prerequisite requires of its reference."""

    __str__ = Enum.__str__

    ACTION_APPLIED = "action_applied"
    ACTION_VERIFIED = "action_verified"
    VERIFICATION_VERIFIED = "verification_verified"
    PHYSICAL_LINK_PRESENT = "physical_link_present"
    PEER_INTERFACE_ENABLED = "peer_interface_enabled"
    SERVICE_USABLE = "service_usable"
    PHONE_REGISTERED = "phone_registered"
    RESOURCE_READY = "resource_ready"


class VerificationPrerequisite(BaseModel):
    """One typed prerequisite of a verification expectation."""

    kind: PrerequisiteKind
    reference_id: str
    description: str = ""


class VerificationDependencyError(ValueError):
    """The verification graph has an unknown reference, a cycle or a bad rank."""


class VerificationExpectationLike(Protocol):
    """The fields ordering needs from any verification expectation."""

    id: str
    verification_prerequisites: list[VerificationPrerequisite]


def order_verification_expectations(
    expectations: Sequence[VerificationExpectationLike],
    *,
    rank: Callable[[VerificationExpectationLike], int] | None = None,
) -> list[VerificationExpectationLike]:
    """Order expectations topologically, ties broken by rank, then by id.

    Without `rank` every expectation ranks equally, which is the historical
    order. With it, ready expectations of a lower rank always run before any
    of a higher rank, so a rank is a barrier: every rank-0 expectation runs
    before the first rank-1 one. That holds only when no expectation depends
    on one of a higher rank, which is refused here rather than half-honored.
    """
    rank_of = rank or (lambda _item: 0)
    by_id = {item.id: item for item in expectations}
    if len(by_id) != len(expectations):
        raise VerificationDependencyError("Duplicate verification expectation id.")
    internal: dict[str, set[str]] = {}
    for item in expectations:
        references = {
            prerequisite.reference_id
            for prerequisite in item.verification_prerequisites
            if prerequisite.kind is PrerequisiteKind.VERIFICATION_VERIFIED
        }
        unknown = sorted(references - by_id.keys())
        if unknown:
            raise VerificationDependencyError(
                f"Verification {item.id!r} references unknown verification(s): "
                + ", ".join(unknown)
            )
        internal[item.id] = references
    for item in expectations:
        for reference in internal[item.id]:
            if rank_of(by_id[reference]) > rank_of(item):
                raise VerificationDependencyError(
                    f"Verification {item.id!r} would run before its dependency "
                    f"{reference!r}, which has a later rank."
                )
    indegree = {
        identifier: len(dependencies) for identifier, dependencies in internal.items()
    }
    downstream: dict[str, set[str]] = {identifier: set() for identifier in by_id}
    for identifier, dependencies in internal.items():
        for dependency in dependencies:
            downstream[dependency].add(identifier)
    frontier: list[tuple[int, str]] = []
    for identifier, degree in indegree.items():
        if degree == 0:
            heappush(frontier, (rank_of(by_id[identifier]), identifier))
    ordered: list[VerificationExpectationLike] = []
    while frontier:
        _, identifier = heappop(frontier)
        ordered.append(by_id[identifier])
        for child in sorted(downstream[identifier]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heappush(frontier, (rank_of(by_id[child]), child))
    if len(ordered) != len(expectations):
        unresolved = sorted(
            identifier for identifier, degree in indegree.items() if degree
        )
        raise VerificationDependencyError(
            "Verification dependency cycle: " + ", ".join(unresolved)
        )
    return ordered


def prerequisites_satisfied(
    prerequisites: Sequence[VerificationPrerequisite],
    *,
    action_statuses: dict[str, Any],
    verification_statuses: dict[str, Any],
    resource_statuses: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Return whether every prerequisite holds, and the ones that do not."""
    blocked: list[str] = []
    for prerequisite in prerequisites:
        if prerequisite.kind in {
            PrerequisiteKind.ACTION_APPLIED,
            PrerequisiteKind.ACTION_VERIFIED,
        }:
            status = action_statuses.get(prerequisite.reference_id, "")
            accepted = (
                _value(status) in {"applied", "no_op", "reasserted", "verified"}
                if prerequisite.kind is PrerequisiteKind.ACTION_APPLIED
                else _value(status) == "verified"
            )
        elif prerequisite.kind is PrerequisiteKind.VERIFICATION_VERIFIED:
            accepted = (
                _value(verification_statuses.get(prerequisite.reference_id, ""))
                == "verified"
            )
        else:
            accepted = _value(resource_statuses.get(prerequisite.reference_id, "")) in {
                "present",
                "ready",
                "enabled",
                "usable",
                "registered",
                "verified",
            }
        if not accepted:
            blocked.append(f"{prerequisite.kind.value}:{prerequisite.reference_id}")
    return not blocked, sorted(blocked)


def legacy_action_prerequisites(
    action_ids: Sequence[str],
) -> list[VerificationPrerequisite]:
    """Return one ACTION_APPLIED prerequisite per distinct action id."""
    return [
        VerificationPrerequisite(
            kind=PrerequisiteKind.ACTION_APPLIED,
            reference_id=identifier,
        )
        for identifier in sorted(set(action_ids))
    ]


def _value(status: Any) -> str:
    return status.value if isinstance(status, Enum) else str(status)
