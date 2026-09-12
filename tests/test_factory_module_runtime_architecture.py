"""Maintainability ratchet for the former factory-module runtime hotspot.

The transport adapter used to own wire parsing, inventory authority, post-
mutation verification, and JavaScript generation in one 1006-line file. The
authority correction made that coupling more expensive, so inventory parsing
and verification now have focused owners. This ceiling applies only to the
former hotspot; it is not a project-wide LOC policy.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_HOTSPOT = (
    ROOT
    / "src"
    / "packet_tracer_mcp"
    / "infrastructure"
    / "execution"
    / "factory_module_runtime.py"
)
RUNTIME_HOTSPOT_LINE_CEILING = 382


def test_factory_module_runtime_does_not_regain_monolithic_responsibilities() -> None:
    """New authority belongs in focused modules, not back in the adapter."""

    measured = len(RUNTIME_HOTSPOT.read_text(encoding="utf-8").splitlines())

    assert measured <= RUNTIME_HOTSPOT_LINE_CEILING, (
        "%s grew to %d lines against a ceiling of %d; keep occupancy authority "
        "and verification in their focused modules"
        % (RUNTIME_HOTSPOT.name, measured, RUNTIME_HOTSPOT_LINE_CEILING)
    )
