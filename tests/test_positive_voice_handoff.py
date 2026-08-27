"""Exact contracts for the small canonical CP-SCALE handoff state block."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.handoff_state import HandoffStateError, parse_handoff_state


BEGIN = "<!-- CP_SCALE_STATE_BEGIN -->"
END = "<!-- CP_SCALE_STATE_END -->"


def _block(*lines: str) -> str:
    return "\n".join((BEGIN, *lines, END))


def test_an_exact_canonical_value_passes():
    state = parse_handoff_state(_block("POOL = NOT_AVAILABLE"))

    assert state == {"POOL": "NOT_AVAILABLE"}


def test_a_prefix_only_expectation_does_not_match_an_expanded_value():
    text = _block(
        "DHCP_POOL_CONFIGURATION_READBACK = "
        "NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS",
    )
    # This is the old false positive and the reason this parser exists.
    assert "DHCP_POOL_CONFIGURATION_READBACK = NOT_AVAILABLE" in text

    actual = parse_handoff_state(text)

    assert actual["DHCP_POOL_CONFIGURATION_READBACK"] != "NOT_AVAILABLE"


def test_a_suffix_expanded_value_does_not_match_the_shorter_expected_value():
    actual = parse_handoff_state(_block("STATUS = MEASURED_UNSUPPORTED_ON_PT"))

    assert actual["STATUS"] != "MEASURED_UNSUPPORTED"


def test_spacing_around_the_separator_is_irrelevant():
    actual = parse_handoff_state(_block("  STATUS   =   OPEN / NOT VERIFIED  "))

    assert actual == {"STATUS": "OPEN / NOT VERIFIED"}


def test_duplicate_canonical_key_is_rejected():
    with pytest.raises(HandoffStateError, match="duplicate key"):
        parse_handoff_state(_block("STATUS = OPEN", "STATUS = CLOSED"))


def test_duplicate_state_block_is_rejected():
    text = f"{_block('STATUS = OPEN')}\n{_block('STATUS = CLOSED')}"

    with pytest.raises(HandoffStateError, match="exactly one.*BEGIN"):
        parse_handoff_state(text)


def test_malformed_canonical_line_is_rejected():
    with pytest.raises(HandoffStateError, match="malformed canonical line"):
        parse_handoff_state(_block("STATUS OPEN"))


def test_historical_key_value_text_outside_the_block_is_ignored():
    text = "STATUS = HISTORICAL\n" + _block("STATUS = CURRENT")

    assert parse_handoff_state(text) == {"STATUS": "CURRENT"}


def test_multiline_canonical_value_is_rejected():
    text = _block("STATUS = FIRST LINE", "    SECOND LINE")

    with pytest.raises(HandoffStateError, match="malformed canonical line"):
        parse_handoff_state(text)


@pytest.mark.parametrize("text", ["STATUS = OPEN", f"{BEGIN}\nSTATUS = OPEN"])
def test_a_missing_required_marker_is_rejected(text: str):
    with pytest.raises(HandoffStateError, match="exactly one"):
        parse_handoff_state(text)


def test_current_cp_scale_voice_state_uses_exact_values():
    handoff = Path("handoff.md").read_text(encoding="utf-8")
    expected = {
        "DHCP_DORA_QUERY_STATUS": "MEASURED_UNSUPPORTED",
        "DORA_EXISTING_SURFACE_USABLE": "NO",
        "DORA_QUERY_READBACK": "UNOBSERVABLE",
        "FIRST_DHCP_RUNTIME_BOUNDARY": "NOT_ESTABLISHED",
        "DHCP_POOL_CONFIGURATION_READBACK": (
            "NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS"
        ),
        "OPTION150_READBACK": "NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS",
        "PORTFAST_CAUSAL_BRANCH": "CLOSED_FOR_NOW",
        "PORTFAST_AS_VOICE_ROOT_CAUSE": (
            "STRONGLY_WEAKENED_FOR_GOVERNED_DISPATCH"
        ),
        "VOICE_ROOT_CAUSE": "NOT_YET_CONFIRMED",
        "NEXT_ACTIVE_STEP": "DHCP_POOL_OBSERVER_ARCHITECTURE_DECISION",
        "CP_SCALE_STATUS": "OPEN / NOT VERIFIED",
    }

    actual = parse_handoff_state(handoff)

    assert actual == expected
