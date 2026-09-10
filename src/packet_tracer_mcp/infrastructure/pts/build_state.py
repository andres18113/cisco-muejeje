"""The Muejeje build-state model: five facts, one dominant state.

This module owns the vocabulary and the precedence. It knows nothing about
Git, JSON or the filesystem, which is what keeps the state machine testable on
its own (MJ-016).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Five states, five different facts. The earlier model collapsed the last three
# into BUILD_TOOLCHAIN_BLOCKED, so "a human can package this in the Scripting
# Interface", "nobody has demonstrated an automated packager" and "we have not
# decided the module id yet" all read as the same failure.
BUILD_SOURCE_INVALID = "BUILD_SOURCE_INVALID"
BUILD_INPUT_INVALID = "BUILD_INPUT_INVALID"
BUILD_TOOLCHAIN_BLOCKED = "BUILD_TOOLCHAIN_BLOCKED"
BUILD_AUTOMATION_UNPROVEN = "BUILD_AUTOMATION_UNPROVEN"
PACKAGING_MANUAL_AVAILABLE = "PACKAGING_MANUAL_AVAILABLE"
PACKAGING_MANUAL_UNAVAILABLE = "PACKAGING_MANUAL_UNAVAILABLE"

BUILD_STATES = (
    BUILD_SOURCE_INVALID,
    BUILD_INPUT_INVALID,
    BUILD_TOOLCHAIN_BLOCKED,
    BUILD_AUTOMATION_UNPROVEN,
    PACKAGING_MANUAL_AVAILABLE,
)

# Substrings that mark a blocker as "the declared inputs violate the contract"
# rather than "the source is unreadable" or "we cannot build right now".
_INPUT_INVALID_MARKERS = (
    "invalid", "unsafe", "noncanonical", "tracked owned source",
    "must be untracked", "must be tracked", "not tracked",
    "mismatch", "omitted",
    "artifact_inputs must", "tooling_inputs must", "reference_inputs must",
    "must be ignored", "must live under the owned source root",
)
_SOURCE_DIRTY_MARKERS = ("dirty", "differ from head")


@dataclass
class Findings:
    """Accumulated blockers, split by who they stop.

    `blockers` stops the audit from certifying anything. `manual_blockers` is
    the strict subset that also stops a *human* from packaging in the Scripting
    Interface: no usable Packet Tracer, or a declared input that is not on disk.
    Tracked explicitly rather than recovered from blocker prose.
    """

    blockers: list[str] = field(default_factory=list)
    manual_blockers: list[str] = field(default_factory=list)

    def block(self, message: str) -> None:
        self.blockers.append(message)

    def block_manual(self, message: str) -> None:
        """A blocker that also stops manual packaging."""
        self.blockers.append(message)
        self.manual_blockers.append(message)

    def extend(self, messages: list[str]) -> None:
        self.blockers.extend(messages)

    @property
    def input_invalid(self) -> bool:
        return _any_marker(self.blockers, _INPUT_INVALID_MARKERS)

    @property
    def source_dirty(self) -> bool:
        return _any_marker(self.blockers, _SOURCE_DIRTY_MARKERS)

    @property
    def toolchain_unusable(self) -> bool:
        return bool(self.manual_blockers)


def _any_marker(blockers: list[str], markers: tuple[str, ...]) -> bool:
    return any(
        marker in blocker.lower() for blocker in blockers for marker in markers
    )


def classify_build_state(
    *,
    source_unidentifiable: bool,
    input_invalid: bool,
    source_dirty: bool,
    toolchain_unusable: bool,
    recipe_complete: bool,
) -> str:
    """Reduce the five independent axes to one dominant state.

    Precedence runs from the fact that invalidates every downstream claim to the
    fact that invalidates none of them. Note that a *malformed manifest* outranks
    a *dirty tree*: a manifest we cannot read tells us nothing, while a dirty
    tree we can still describe precisely. That ordering predates this function
    and is preserved deliberately.

    ``BUILD_SOURCE_INVALID`` (``source_unidentifiable``)
        Git could not identify the source at all, so no recipe describes
        anything.
    ``BUILD_INPUT_INVALID``
        The manifest or an input violates the contract.
    ``BUILD_SOURCE_INVALID`` (``source_dirty``)
        The source is readable but not pinned: uncommitted or differing from
        HEAD, so a recipe built from it would not identify what it hashed.
    ``BUILD_TOOLCHAIN_BLOCKED``
        A genuine inability to build: no usable Packet Tracer, or a declared
        input that is not there. **Not** the mere absence of automation.
    ``BUILD_AUTOMATION_UNPROVEN``
        Nothing is broken; the recipe is not fully specified yet, and no
        automated packaging path has been demonstrated.
    ``PACKAGING_MANUAL_AVAILABLE``
        A human can package this recipe in the Scripting Interface right now.
        Automation is still unproven; ``packaging_state`` says so separately.
    """
    if source_unidentifiable:
        return BUILD_SOURCE_INVALID
    if input_invalid:
        return BUILD_INPUT_INVALID
    if source_dirty:
        return BUILD_SOURCE_INVALID
    if toolchain_unusable:
        return BUILD_TOOLCHAIN_BLOCKED
    if not recipe_complete:
        return BUILD_AUTOMATION_UNPROVEN
    return PACKAGING_MANUAL_AVAILABLE


def packaging_state(
    *,
    manual: str,
    manual_blockers: list[str],
    recipe_complete: bool,
    unresolved_build_options: list[str],
    unresolved_automation_prerequisites: list[str],
) -> dict[str, Any]:
    return {
        "manual": manual,
        "manual_blockers": manual_blockers,
        # No automated packaging path has been demonstrated for the Scripting
        # Interface. This stays UNPROVEN until evidence says otherwise; it is
        # never inferred from a clean report.
        "automation": BUILD_AUTOMATION_UNPROVEN,
        "automation_evidence": None,
        "recipe_complete": recipe_complete,
        "unresolved_build_options": unresolved_build_options,
        "unresolved_automation_prerequisites": unresolved_automation_prerequisites,
    }


def base_report(
    status: str,
    blockers: list[str],
    *,
    unresolved_build_options: list[str],
    unresolved_automation_prerequisites: list[str],
) -> dict[str, Any]:
    """The report shape every run returns, including the earliest failures."""
    return {
        "status": status,
        "blockers": blockers,
        "source": {"commit": None, "tree": None, "clean": False},
        "inputs": {"artifact": [], "tooling": [], "reference": []},
        "builder": None,
        "packaging_state": packaging_state(
            manual=PACKAGING_MANUAL_UNAVAILABLE,
            manual_blockers=[],
            recipe_complete=False,
            unresolved_build_options=unresolved_build_options,
            unresolved_automation_prerequisites=unresolved_automation_prerequisites,
        ),
        "recipe": None,
        "build_recipe_id": None,
        "artifact_sha256": None,
    }
