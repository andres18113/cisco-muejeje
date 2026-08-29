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
        "FIRST_COMMON_VOICE_OBSERVABILITY_BOUNDARY": (
            "ENDPOINT_ADDRESS_CONTRADICTED"
        ),
        "DHCP_POOL_EXISTENCE_READBACK": "VERIFIED",
        "DHCP_POOL_RANGE_READBACK": "VERIFIED",
        "DHCP_POOL_AVAILABLE_SPACE_READBACK": "VERIFIED",
        "DHCP_POOL_CONFIGURATION_READBACK": (
            "NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS"
        ),
        "DHCP_POOL_DEFAULT_ROUTER_READBACK": (
            "NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS"
        ),
        "DHCP_POOL_EXCLUSIONS_READBACK": (
            "NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS"
        ),
        "POOL_EXISTENCE_CAUSE": "WEAKENED",
        "POOL_EXHAUSTION_CAUSE": "REFUTED_FOR_THIS_DISPOSABLE",
        "OPTION150_READBACK": "NOT_AVAILABLE_WITH_CURRENT_GOVERNED_READBACKS",
        "PORTFAST_CAUSAL_BRANCH": "CLOSED_FOR_NOW",
        "PORTFAST_AS_VOICE_ROOT_CAUSE": (
            "STRONGLY_WEAKENED_FOR_GOVERNED_DISPATCH"
        ),
        "SERVER_RECEIVES_DISCOVER": "UNOBSERVABLE",
        "DHCP_TRANSACTION_PROGRESS": "UNOBSERVABLE",
        "VOICE_VLAN_REALTIME_DATA_PLANE_FORWARDING": "NOT_ESTABLISHED",
        "ACCESS_VLAN_SHAPE_CONTROLS_STP_MEMBERSHIP": "ESTABLISHED",
        "ACCESS_VLAN_SHAPE_CONTROLS_DHCP": "NOT_YET_ESTABLISHED",
        "VOICE_ENDPOINT_OUTCOME_RUN9": "SAME_FAILURE",
        "CAUSAL_EXPERIMENT_RESULT_RUN9": "PARTIAL_OR_DIVERGENT",
        "INTERVENTION_FWD_OBSERVED_RUN9": "NO",
        "INTERVENTION_NEVER_FWD_DURING_RUN9": "NOT_ESTABLISHED",
        "FRESH_DHCP_TRIGGER": (
            "NOT_ESTABLISHED_RUN11_PRE_FLAGS_ALREADY_YES"
        ),
        "FRESH_7960_DHCP_TRANSACTION": "NOT_INDEPENDENTLY_ESTABLISHED",
        "CURRENT_TYPED_DHCP_FRESH_TRANSACTION": "NOT_ESTABLISHED",
        "PHONE_SVI_DHCP_API": (
            "MEASURED_PRESENT_AND_CISCO_BOOL_SIGNATURE_CONFIRMED"
        ),
        "PHONE_SVI_DHCP_RETRIGGER_EXPERIMENT": "PREPARED_NOT_RUN",
        "NEW_MUTATION_SURFACE": "TYPED_EXACT_PHONE_SVI_ONLY",
        "RAW_ESCAPE_HATCH_ADDED": "NO",
        "PHONE_DHCP_LIFECYCLE_DIAGNOSTIC": "MEASURED",
        "PHONE_DHCP_LIFECYCLE_LIVE_EXECUTED": "YES",
        "PHONE_DHCP_LIFECYCLE_CHANNELS": "SVI_DHCP | DEVICE_DHCP",
        "PHONE_DHCP_LIFECYCLE_DERIVATIONS": "PER_PHONE",
        "PHONE_DHCP_LIFECYCLE_LEDGER_ROLE": (
            "PHONE_DHCP_LIFECYCLE_QUALIFICATION"
        ),
        "FIRST_OBSERVED_SVI_DHCP_ENABLED_MILESTONE": (
            "IMMEDIATELY_BEFORE_STP_FWD_GATE"
        ),
        "FIRST_OBSERVED_DEVICE_DHCP_ENABLED_MILESTONE": "NOT_ESTABLISHED",
        "SVI_DHCP_ENABLED_BEFORE_FWD": "YES",
        "DEVICE_DHCP_ENABLED_BEFORE_FWD": "UNOBSERVABLE",
        "RUN12_EXECUTED": "YES",
        "RUN12_RESULT": "OBSERVATIONAL_LIFECYCLE_QUALIFIED",
        "RUN12_FWD_GATE": "FORWARDING",
        "RUN12_STP_GATE_OBSERVED_STATES": (
            "LIS -> LRN -> UNOBSERVABLE -> LRN -> UNOBSERVABLE -> FORWARDING"
        ),
        "RUN12_STP_AUTHORITY_TRANSITIONS": (
            "LIS(AUTHORITATIVE) -> LRN(AUTHORITATIVE) -> "
            "UNOBSERVABLE(COMPLETENESS) -> LRN(AUTHORITATIVE) -> "
            "UNOBSERVABLE(COMPLETENESS) -> FORWARDING(AUTHORITATIVE)"
        ),
        "RUN12_STP_FAILURE_DIMENSIONS": "COMPLETENESS",
        "RUN12_STP_GATE_DURATION_MS": "31171",
        "RUN12_STP_GATE_SAMPLES": "15",
        "RUN12_AUTHORITATIVE_FWD_OBSERVED": "YES",
        "RUN12_CONTROL_FIRST_SVI_DHCP_ENABLED": (
            "IMMEDIATELY_BEFORE_STP_FWD_GATE"
        ),
        "RUN12_INTERVENTION_FIRST_SVI_DHCP_ENABLED": (
            "IMMEDIATELY_BEFORE_STP_FWD_GATE"
        ),
        "RUN12_CONTROL_FIRST_DEVICE_DHCP_ENABLED": "NOT_ESTABLISHED",
        "RUN12_INTERVENTION_FIRST_DEVICE_DHCP_ENABLED": "NOT_ESTABLISHED",
        "RUN12_CONTROL_SVI_DHCP_BEFORE_FWD": "YES",
        "RUN12_INTERVENTION_SVI_DHCP_BEFORE_FWD": "YES",
        "RUN12_CONTROL_DEVICE_DHCP_BEFORE_FWD": "UNOBSERVABLE",
        "RUN12_INTERVENTION_DEVICE_DHCP_BEFORE_FWD": "UNOBSERVABLE",
        "RUN12_CONTROL_IPV4_OBSERVED": "NO_VALUE_OBSERVED",
        "RUN12_INTERVENTION_IPV4_OBSERVED": "NO_VALUE_OBSERVED",
        "RUN12_OBSERVABLE_DHCP_NO_TO_YES_TRANSITION": "NOT_OBSERVED",
        "RUN10_EXECUTED": "YES",
        "RUN10_RESULT": "STP_PRECONDITION_NOT_ESTABLISHED",
        "RUN10_FWD_GATE": "UNOBSERVABLE",
        "RUN10_STP_GATE_OBSERVED_STATES": "LIS -> LRN -> UNOBSERVABLE",
        "RUN10_STP_GATE_DURATION_MS": "21844",
        "RUN10_STP_GATE_SAMPLES": "11",
        "RUN10_STP_GATE_IDENTITY": "NOT_ESTABLISHED",
        "RUN10_TERMINAL_STP_FAILURE_DIMENSION": "NOT_RETAINED",
        "STP_GATE_DIAGNOSTIC_RETENTION": "READY",
        "STP_GATE_GAP_TOLERANCE": "READY",
        "STP_GATE_SUCCESS_CONTRACT": (
            "EXECUTED + FRESH + COMPLETE + CONFIRMED_UNIQUE + FWD"
        ),
        "STP_GATE_FAILURE_DIMENSIONS": (
            "EXECUTION | FRESHNESS | COMPLETENESS | IDENTITY | PARSING | "
            "QUERY_SESSION"
        ),
        "STP_GATE_QUERY_COUNT_PER_SAMPLE": "ONE",
        "SECOND_STP_QUERY_ADDED": "NO",
        "RUN10_DHCP_FLAG_TRANSITION_CONTRACT": (
            "PRE_NO + ARM_ACCEPTED + POST_YES_REQUIRED"
        ),
        "RUN10_DHCP_FLAG_TRANSITION": "UNOBSERVABLE",
        "RUN10_ACQUISITION_STARTED": "NO",
        "RUN10_ACQUISITION_BOUNDARY": (
            "ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET"
        ),
        "RUN10_TRUNK_VOICE_FORWARDING": "CONTRADICTED",
        "RUN10_TRUNK_ALLOWED_VLANS": "NOT_RETAINED",
        "RUN10_TRUNK_ACTIVE_VLANS": "NOT_RETAINED",
        "RUN10_TRUNK_FORWARDING_VLANS": "NOT_RETAINED",
        "RUN10_TRUNK_VLAN930_ALLOWED": "YES",
        "RUN10_TRUNK_VLAN930_ACTIVE": "YES",
        "RUN10_TRUNK_VLAN930_FORWARDING": "NO",
        "RUN11_EXECUTED": "YES",
        "RUN11_RESULT": "FRESH_DHCP_TRIGGER_UNPROVEN",
        "RUN11_FWD_GATE": "FORWARDING",
        "RUN11_STP_GATE_OBSERVED_STATES": (
            "LIS -> LRN -> UNOBSERVABLE -> LRN -> UNOBSERVABLE -> FORWARDING"
        ),
        "RUN11_STP_AUTHORITY_TRANSITIONS": (
            "LIS(AUTHORITATIVE) -> LRN(AUTHORITATIVE) -> "
            "UNOBSERVABLE(COMPLETENESS) -> LRN(AUTHORITATIVE) -> "
            "UNOBSERVABLE(COMPLETENESS) -> FORWARDING(AUTHORITATIVE)"
        ),
        "RUN11_STP_FAILURE_DIMENSIONS": "COMPLETENESS",
        "RUN11_STP_GATE_DURATION_MS": "30327",
        "RUN11_STP_GATE_SAMPLES": "15",
        "RUN11_AUTHORITATIVE_FWD_OBSERVED": "YES",
        "RUN11_TRUNK_ALLOWED_VLANS": "(930, 931)",
        "RUN11_TRUNK_ACTIVE_VLANS": "(930, 931)",
        "RUN11_TRUNK_FORWARDING_VLANS": "(930, 931)",
        "RUN11_TRUNK_READ_AUTHORITY": "AUTHORITATIVE",
        "RUN11_CONTROL_DHCP_PRE": "YES",
        "RUN11_INTERVENTION_DHCP_PRE": "YES",
        "RUN11_CONTROL_ARM_ACCEPTED": "UNOBSERVABLE",
        "RUN11_INTERVENTION_ARM_ACCEPTED": "UNOBSERVABLE",
        "RUN11_CONTROL_DHCP_POST": "UNOBSERVABLE",
        "RUN11_INTERVENTION_DHCP_POST": "UNOBSERVABLE",
        "RUN11_DHCP_FLAG_TRANSITION_VALID": "UNOBSERVABLE",
        "RUN11_ACQUISITION_STARTED": "NO",
        "RUN11_ACQUISITION_BOUNDARY": (
            "ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN"
        ),
        "TRUNK_FORWARDING_SEMANTIC_AUDIT": (
            "IOS_STP_FORWARDING_AND_NOT_PRUNED_SET_ON_SHARED_TRUNK"
        ),
        "TRUNK_READ_AUTHORITY_RETENTION": "READY",
        "STP_VS_TRUNK_RELATION": "NOT_ESTABLISHED",
        "VOICE_ROOT_CAUSE": "NOT_CONFIRMED",
        "NEXT_ACTIVE_STEP": "RUN_PHONE_SVI_DHCP_RETRIGGER_CAUSAL_LIVE",
        "CP_SCALE_STATUS": "OPEN / NOT VERIFIED",
    }

    actual = parse_handoff_state(handoff)

    assert actual == expected
