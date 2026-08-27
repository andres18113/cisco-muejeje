"""Parser for the one authoritative CP-SCALE state block in ``handoff.md``."""

from __future__ import annotations

import re


STATE_BEGIN = "<!-- CP_SCALE_STATE_BEGIN -->"
STATE_END = "<!-- CP_SCALE_STATE_END -->"
_KEY = re.compile(r"[A-Z][A-Z0-9_]*")


class HandoffStateError(ValueError):
    """The canonical handoff state block is absent, ambiguous, or malformed."""


def parse_handoff_state(text: str) -> dict[str, str]:
    """Return only the exact key/value pairs inside the canonical state block."""
    lines = text.splitlines()
    begins = [index for index, line in enumerate(lines) if line.strip() == STATE_BEGIN]
    ends = [index for index, line in enumerate(lines) if line.strip() == STATE_END]
    if len(begins) != 1:
        raise HandoffStateError(
            f"expected exactly one CP_SCALE_STATE_BEGIN marker; found {len(begins)}"
        )
    if len(ends) != 1:
        raise HandoffStateError(
            f"expected exactly one CP_SCALE_STATE_END marker; found {len(ends)}"
        )
    begin, end = begins[0], ends[0]
    if end <= begin:
        raise HandoffStateError("CP_SCALE_STATE_END must follow CP_SCALE_STATE_BEGIN")

    state: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines[begin + 1:end], start=begin + 2):
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            raise HandoffStateError(
                f"malformed canonical line {line_number}: expected KEY = VALUE"
            )
        raw_key, raw_value = line.split("=", 1)
        key, value = raw_key.strip(), raw_value.strip()
        if _KEY.fullmatch(key) is None or not value:
            raise HandoffStateError(
                f"malformed canonical line {line_number}: expected KEY = VALUE"
            )
        if key in state:
            raise HandoffStateError(
                f"duplicate key {key!r} in canonical handoff state"
            )
        state[key] = value
    return state
