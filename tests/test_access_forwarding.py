"""Per-VLAN forwarding admission and the documented light enum (unit level).

Every dimension refuses on its own, and each one is exercised against an
observation that is otherwise admissible: a rule that only refuses when
several things are wrong at once is not a rule about any of them.
"""

from __future__ import annotations

import pytest

from packet_tracer_mcp.domain.enterprise.models.forwarding import (
    AccessForwardingObservation,
    AccessForwardingRow,
)
from packet_tracer_mcp.domain.enterprise.services.access_forwarding import (
    CONFIRMED_UNIQUE,
    DIMENSION_AMBIGUOUS_INTERFACE,
    DIMENSION_COMPLETENESS,
    DIMENSION_DEADLINE,
    DIMENSION_EXECUTION,
    DIMENSION_FRESHNESS,
    DIMENSION_IDENTITY,
    DIMENSION_MISSING_INTERFACE,
    DIMENSION_NON_FORWARDING,
    DIMENSION_NONE,
    DIMENSION_NOT_ATTEMPTED,
    DIMENSION_REQUEST,
    DIMENSION_VLAN_INSTANCE,
    PORT_LIGHT_STATUS,
    access_forwarding_admission,
    access_forwarding_facts,
    interpret_port_light,
    port_light_reading,
)
from packet_tracer_mcp.domain.enterprise.services.service_qualification_evidence import (
    INCONCLUSIVE,
    SUPPORTED,
    assess_access_forwarding,
)

REQUESTED = ("FastEthernet0/1", "FastEthernet0/2")


def _observation(**overrides) -> AccessForwardingObservation:
    """Return an admissible sample, with the one field a test changes."""
    values = {
        "switch_name": "SW",
        "vlan_id": 1,
        "requested_interfaces": REQUESTED,
        "rows": tuple(
            AccessForwardingRow(item, 1, "FWD", "Desg") for item in REQUESTED
        ),
        "executed": True,
        "fresh_output_observed": True,
        "output_complete": True,
        "observed_device_name": "SW",
        "device_identity_provenance": CONFIRMED_UNIQUE,
        "vlan_present": True,
        "samples": 1,
    }
    values.update(overrides)
    return AccessForwardingObservation(**values)


def test_a_complete_attributed_sample_admits_exactly_its_interfaces():
    """The one positive control every negative below is measured against."""
    admission = access_forwarding_admission(_observation())
    assert (admission.admitted, admission.dimension) == (True, DIMENSION_NONE)
    assert admission.forwarding_interfaces == REQUESTED
    assert admission.causes == ()


def test_an_exhausted_complete_forwarding_sample_refuses_in_the_shared_rule():
    """The observation model's exhausted flag is non-authorizing by itself."""
    exhausted = access_forwarding_admission(_observation(sample_budget_exhausted=True))
    complete = access_forwarding_admission(_observation(sample_budget_exhausted=False))
    assert exhausted.admitted is False
    assert exhausted.causes == ("sample_call_budget_exhausted",)
    assert complete.admitted is True


def test_diagnostic_projection_refuses_exhaustion_and_retains_the_raw_flag():
    """A diagnostic row keeps FWD bytes without promoting an exhausted read."""
    refused = assess_access_forwarding(
        _observation(sample_budget_exhausted=True), label="forwarding"
    )
    admitted = assess_access_forwarding(
        _observation(sample_budget_exhausted=False), label="forwarding"
    )
    assert refused.conclusion is INCONCLUSIVE
    assert refused.facts["forwarding"]["sample_budget_exhausted"] is True
    assert refused.facts["forwarding"]["admitted"] is False
    assert admitted.conclusion is SUPPORTED


@pytest.mark.parametrize(
    ("overrides", "dimension"),
    [
        ({"requested_interfaces": ()}, DIMENSION_REQUEST),
        ({"samples": 0}, DIMENSION_NOT_ATTEMPTED),
        ({"executed": False}, DIMENSION_EXECUTION),
        ({"fresh_output_observed": False}, DIMENSION_FRESHNESS),
        ({"output_complete": False}, DIMENSION_COMPLETENESS),
        ({"observed_device_name": "OTHER"}, DIMENSION_IDENTITY),
        ({"device_identity_provenance": "ambiguous"}, DIMENSION_IDENTITY),
        ({"deadline_reached": True}, DIMENSION_DEADLINE),
        ({"vlan_present": False}, DIMENSION_VLAN_INSTANCE),
    ],
)
def test_each_dimension_refuses_on_its_own(overrides, dimension):
    """One wrong dimension is enough, whatever the rows say."""
    admission = access_forwarding_admission(_observation(**overrides))
    assert (admission.admitted, admission.dimension) == (False, dimension)


@pytest.mark.parametrize("state", ["LRN", "LIS", "BLK", "DIS", "", "forwarding-ish"])
def test_only_a_forwarding_state_forwards(state):
    """Learning, listening and blocking are states, not near-misses."""
    rows = (
        AccessForwardingRow(REQUESTED[0], 1, "FWD", "Desg"),
        AccessForwardingRow(REQUESTED[1], 1, state, "Desg"),
    )
    admission = access_forwarding_admission(_observation(rows=rows))
    assert (admission.admitted, admission.dimension) == (
        False,
        DIMENSION_NON_FORWARDING,
    )
    assert admission.causes == (f"{REQUESTED[1]}={state or 'unobservable'}",)


def test_a_missing_row_is_not_a_non_forwarding_row():
    """An interface the instance never named was not observed at all."""
    rows = (
        AccessForwardingRow(REQUESTED[0], 1, "FWD", "Desg"),
        AccessForwardingRow(REQUESTED[1], 0, "", ""),
    )
    admission = access_forwarding_admission(_observation(rows=rows))
    assert admission.dimension == DIMENSION_MISSING_INTERFACE
    assert admission.causes == (f"interface_absent:{REQUESTED[1]}",)


def test_two_rows_for_one_interface_are_ambiguous_not_forwarding():
    """Collapsing duplicates would turn two contradictory rows into one state."""
    rows = (
        AccessForwardingRow(REQUESTED[0], 2, "FWD", "Desg"),
        AccessForwardingRow(REQUESTED[1], 1, "FWD", "Desg"),
    )
    admission = access_forwarding_admission(_observation(rows=rows))
    assert admission.dimension == DIMENSION_AMBIGUOUS_INTERFACE
    assert admission.causes == (f"interface_rows:{REQUESTED[0]}=2",)


def test_the_facts_never_promote_the_auxiliary_light_evidence():
    """A green light beside a non-forwarding row stays exactly that."""
    observation = _observation(
        rows=(
            AccessForwardingRow(REQUESTED[0], 1, "FWD", "Desg"),
            AccessForwardingRow(REQUESTED[1], 1, "LRN", "Desg"),
        ),
        lights=(port_light_reading("SW", REQUESTED[1], raw=2, raw_type="number"),),
    )
    admission = access_forwarding_admission(observation)
    facts = access_forwarding_facts(observation, admission)
    assert facts["admitted"] is False
    assert facts["light_status_is_auxiliary"] is True
    assert facts["lights"][0]["interpretation"] == "green"
    assert facts["forwarding_interfaces"] == []


@pytest.mark.parametrize(
    ("raw", "raw_type", "name"),
    [
        (0, "number", "off"),
        (1, "number", "amber"),
        (2, "number", "green"),
        (3, "number", "blink"),
        (4, "number", "unknown"),
        (-1, "number", "unknown"),
        (True, "boolean", "unknown"),
        (1, "boolean", "unknown"),
        ("2", "string", "unknown"),
        (None, "absent", "unknown"),
        (None, "threw", "unknown"),
    ],
)
def test_the_light_enum_is_the_documented_one_and_nothing_else(raw, raw_type, name):
    """`eOffLight = 0, eAmberLight = 1, eGreenLight = 2, eBlink = 3`."""
    assert interpret_port_light(raw, raw_type) == name


def test_a_light_reading_keeps_its_raw_value_only_when_it_is_a_number():
    """A missing reader, a refused one and an actual `0` stay three answers."""
    off = port_light_reading("SW", "Fa0/1", raw=0, raw_type="number")
    assert (off.raw, off.interpretation, off.raw_type) == (0, "off", "number")
    threw = port_light_reading("SW", "Fa0/1", raw_type="threw", failure_reason="boom")
    assert (threw.raw, threw.interpretation, threw.failure_reason) == (
        None,
        "unknown",
        "boom",
    )
    absent = port_light_reading("SW", "Fa0/1")
    assert (absent.raw, absent.raw_type) == (None, "absent")
    assert set(PORT_LIGHT_STATUS) == {0, 1, 2, 3}
