"""DF7: the versioned native-default policy over a whole run's readings.

The policy wires the existing exact-value classifier into a sequence: the one
interval that carries the reviewed intervention may be the admitted
realignment or unchanged, and every other interval must be unchanged. The
positive control replays the six readings D-DHCP attempt 2 recorded; every
negative control changes one thing about it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    Q3_FL_NATIVE_DEFAULT_POLICY,
)
from packet_tracer_mcp.domain.enterprise.services.dhcp_native_default_lifecycle import (
    ADMITTED_REALIGNMENT,
    INTERVAL_PERMITTED,
    INTERVAL_REFUSED,
    NOT_ASSESSED,
    UNCHANGED,
    UNEXPLAINED_DRIFT,
    NativeDefaultReading,
    assess_native_default_sequence,
)
from packet_tracer_mcp.infrastructure.catalog.dhcp_native_default_transitions import (
    WHOLE_CONFIGURE_PC_IP,
    admitted_native_default_transitions,
)

BUILD = "9.0.1.0858"
STOCK = {
    "name": "serverPool",
    "network": "0.0.0.0",
    "mask": "0.0.0.0",
    "gateway": "0.0.0.0",
    "dns": "0.0.0.0",
    "start": "0.0.0.0",
    "end": "0.0.2.0",
    "max": 512,
}
REALIGNED = {
    **STOCK,
    "network": "192.0.2.0",
    "mask": "255.255.255.0",
    "start": "192.0.2.0",
    "end": "192.0.3.255",
}
RECORD = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "services"
    / "qualification"
    / "d-dhcp"
    / "d-dhcp-2026-09-21T20-01-43Z-dffd6c3b.json"
)


def _reading(label: str, row, intervention: str = "", observed: bool = True):
    return NativeDefaultReading(
        label=label,
        observed=observed,
        rows=(dict(row),) if row is not None else (),
        intervention=intervention,
    )


def _assess(
    readings, *, backend_version: str = BUILD, interface: str = "FastEthernet0"
):
    return assess_native_default_sequence(
        readings,
        policy=Q3_FL_NATIVE_DEFAULT_POLICY,
        model="Server-PT",
        backend_version=backend_version,
        interface=interface,
        reviewed_intervention=WHOLE_CONFIGURE_PC_IP,
        admitted=admitted_native_default_transitions(backend_version),
    )


def _q3fl_sequence(after_mode=REALIGNED, after_setup=REALIGNED):
    return [
        _reading("before_e5", STOCK),
        _reading("after_server_address", REALIGNED, WHOLE_CONFIGURE_PC_IP),
        _reading("after_client_mode", after_mode, "e5:client_dhcp_mode"),
        _reading("after_server_setup", after_setup, "e6:pool_and_enable"),
    ]


def test_the_reviewed_realignment_followed_by_stability_is_permitted():
    """The one measured transition in its context, then nothing moves."""
    result = _assess(_q3fl_sequence())

    assert result.permits_continuation is True
    assert [item.assessment.classification for item in result.intervals] == [
        ADMITTED_REALIGNMENT,
        UNCHANGED,
        UNCHANGED,
    ]
    assert {item.decision for item in result.intervals} == {INTERVAL_PERMITTED}
    assert result.policy == Q3_FL_NATIVE_DEFAULT_POLICY
    assert result.authorizes_allocation is False


@pytest.mark.skipif(not RECORD.exists(), reason="the D-DHCP record is machine-local")
def test_the_six_recorded_d_dhcp_readings_are_permitted_in_their_order():
    """Replay the immutable record: baseline, control, address, pool, enable, final."""
    record = json.loads(RECORD.read_bytes())
    interventions = {
        "d0_control": "control:no_intervention",
        "d1_after_server_address": WHOLE_CONFIGURE_PC_IP,
        "d2_after_pool": "e6:configure_server_dhcp_pool:process_disabled",
        "d3_after_enable": "e6:enable_server_dhcp",
        "d4_before_cleanup": "terminal:no_intervention",
    }
    readings = [
        NativeDefaultReading(
            label=entry["label"],
            observed=entry["observed"],
            rows=tuple(entry["pools"]),
            intervention=interventions.get(entry["label"], ""),
        )
        for entry in record["native_default_pool"]
    ]

    result = _assess(readings)

    assert [item.after_label for item in result.intervals] == list(interventions)
    assert result.permits_continuation is True
    assert result.intervals[1].assessment.classification == ADMITTED_REALIGNMENT


def test_a_movement_after_the_realignment_is_a_stability_failure():
    """A later interval moving the default is drift even to plausible values."""
    moved = {**REALIGNED, "gateway": "192.0.2.1"}
    result = _assess(_q3fl_sequence(after_mode=moved, after_setup=moved))

    assert result.permits_continuation is False
    refused = result.intervals[1]
    assert refused.decision == INTERVAL_REFUSED
    assert refused.assessment.classification == UNEXPLAINED_DRIFT
    assert refused.cause.startswith("stability_required:")
    assert result.causes[0].startswith("after_client_mode:stability_required:")


def test_the_realignment_inside_another_interval_is_not_admitted():
    """The same values reached through another call are not the reviewed context."""
    readings = [
        _reading("before_e5", STOCK),
        _reading("after_server_address", STOCK, WHOLE_CONFIGURE_PC_IP),
        _reading("after_client_mode", REALIGNED, "e5:client_dhcp_mode"),
    ]
    result = _assess(readings)

    assert result.intervals[0].assessment.classification == UNCHANGED
    assert result.intervals[1].decision == INTERVAL_REFUSED
    assert result.permits_continuation is False


def test_the_reviewed_intervention_is_admitted_once():
    """A second interval claiming the reviewed call is refused, not re-admitted."""
    readings = [
        _reading("before_e5", STOCK),
        _reading("after_server_address", REALIGNED, WHOLE_CONFIGURE_PC_IP),
        _reading("after_second_address", REALIGNED, WHOLE_CONFIGURE_PC_IP),
    ]
    result = _assess(readings)

    assert result.intervals[1].cause == "reviewed_intervention_repeated"
    assert result.permits_continuation is False


def test_an_unobserved_reading_permits_nothing():
    """Unknown is not unchanged."""
    readings = _q3fl_sequence()
    readings[2] = _reading("after_client_mode", None, "e5:client_dhcp_mode", False)
    result = _assess(readings)

    assert result.intervals[1].assessment.classification == NOT_ASSESSED
    assert result.intervals[1].decision == INTERVAL_REFUSED
    assert not result.intervals[1].cause.startswith("stability_required:")
    assert result.permits_continuation is False


@pytest.mark.parametrize(
    ("override", "cause"),
    [
        (
            {"backend_version": "9.0.0.0810"},
            "no_reviewed_transition_matches_this_observation",
        ),
        (
            {"interface": "FastEthernet1"},
            "no_reviewed_transition_matches_this_observation",
        ),
    ],
)
def test_another_build_or_interface_never_admits_the_realignment(override, cause):
    """Unknown builds and interfaces stay non-authorizing."""
    result = _assess(_q3fl_sequence(), **override)

    assert result.intervals[0].assessment.classification == UNEXPLAINED_DRIFT
    assert result.intervals[0].cause == cause
    assert result.permits_continuation is False


def test_an_unmeasured_realignment_on_the_reviewed_call_is_refused():
    """Another network through the same call is not the measured transition."""
    other = {
        **STOCK,
        "network": "198.51.100.0",
        "mask": "255.255.255.0",
        "start": "198.51.100.0",
        "end": "198.51.101.255",
    }
    readings = [
        _reading("before_e5", STOCK),
        _reading("after_server_address", other, WHOLE_CONFIGURE_PC_IP),
    ]
    result = _assess(readings)

    assert result.intervals[0].assessment.classification == UNEXPLAINED_DRIFT
    assert result.permits_continuation is False
