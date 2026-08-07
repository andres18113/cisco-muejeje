"""Verification-only dependency graph, separate from application ordering."""

from __future__ import annotations

from enum import Enum
from heapq import heappop, heappush
from typing import Any, Protocol, Sequence

from pydantic import BaseModel


class PrerequisiteKind(str, Enum):
    ACTION_APPLIED = "action_applied"
    ACTION_VERIFIED = "action_verified"
    VERIFICATION_VERIFIED = "verification_verified"
    PHYSICAL_LINK_PRESENT = "physical_link_present"
    PEER_INTERFACE_ENABLED = "peer_interface_enabled"
    SERVICE_USABLE = "service_usable"
    PHONE_REGISTERED = "phone_registered"
    RESOURCE_READY = "resource_ready"


class VerificationPrerequisite(BaseModel):
    kind: PrerequisiteKind
    reference_id: str
    description: str = ""


class VerificationDependencyError(ValueError):
    pass


class VerificationExpectationLike(Protocol):
    id: str
    verification_prerequisites: list[VerificationPrerequisite]


def order_verification_expectations(
    expectations: Sequence[VerificationExpectationLike],
) -> list[VerificationExpectationLike]:
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
    indegree = {identifier: len(dependencies) for identifier, dependencies in internal.items()}
    downstream: dict[str, set[str]] = {identifier: set() for identifier in by_id}
    for identifier, dependencies in internal.items():
        for dependency in dependencies:
            downstream[dependency].add(identifier)
    frontier: list[str] = []
    for identifier, degree in indegree.items():
        if degree == 0:
            heappush(frontier, identifier)
    ordered: list[VerificationExpectationLike] = []
    while frontier:
        identifier = heappop(frontier)
        ordered.append(by_id[identifier])
        for child in sorted(downstream[identifier]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heappush(frontier, child)
    if len(ordered) != len(expectations):
        unresolved = sorted(identifier for identifier, degree in indegree.items() if degree)
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
    blocked: list[str] = []
    for prerequisite in prerequisites:
        if prerequisite.kind in {
            PrerequisiteKind.ACTION_APPLIED, PrerequisiteKind.ACTION_VERIFIED,
        }:
            status = action_statuses.get(prerequisite.reference_id, "")
            accepted = (
                _value(status) in {"applied", "no_op", "reasserted", "verified"}
                if prerequisite.kind is PrerequisiteKind.ACTION_APPLIED
                else _value(status) == "verified"
            )
        elif prerequisite.kind is PrerequisiteKind.VERIFICATION_VERIFIED:
            accepted = _value(verification_statuses.get(prerequisite.reference_id, "")) == "verified"
        else:
            accepted = _value(resource_statuses.get(prerequisite.reference_id, "")) in {
                "present", "ready", "enabled", "usable", "registered", "verified",
            }
        if not accepted:
            blocked.append(f"{prerequisite.kind.value}:{prerequisite.reference_id}")
    return not blocked, sorted(blocked)


def legacy_action_prerequisites(action_ids: Sequence[str]) -> list[VerificationPrerequisite]:
    return [
        VerificationPrerequisite(
            kind=PrerequisiteKind.ACTION_APPLIED,
            reference_id=identifier,
        )
        for identifier in sorted(set(action_ids))
    ]


def _value(status: Any) -> str:
    return status.value if isinstance(status, Enum) else str(status)

