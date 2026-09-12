"""File-specific growth ratchet for the legacy configuration runtime tests."""

from __future__ import annotations

from pathlib import Path


HOTSPOT = Path(__file__).with_name("test_configuration_runtime.py")
HOTSPOT_LINE_CEILING = 2069


def test_configuration_runtime_legacy_hotspot_does_not_grow() -> None:
    """New runtime behavior belongs in a focal module, not the 2k-line suite."""

    measured = len(HOTSPOT.read_text(encoding="utf-8").splitlines())

    assert measured <= HOTSPOT_LINE_CEILING, (
        "%s grew to %d lines against a ceiling of %d; add a focal test module"
        % (HOTSPOT.name, measured, HOTSPOT_LINE_CEILING)
    )
