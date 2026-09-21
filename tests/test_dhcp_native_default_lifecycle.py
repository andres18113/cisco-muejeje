"""The native default lifecycle decision, against the values that were measured.

The oracle here is the immutable D-DHCP attempt 2 record, transcribed once at
the top of this file rather than recomputed: a test that derived the expected
values with the same arithmetic the decision must NOT use would prove the
arithmetic, not the decision. Every refusal case is built by changing exactly
one thing about a pair that would otherwise be admitted, so each test names one
reason.
"""

from __future__ import annotations

from typing import Any

import pytest

from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.service_plan import ServiceType
from packet_tracer_mcp.domain.enterprise.services.dhcp_native_default_lifecycle import (
    ADMITTED_REALIGNMENT,
    COEXISTENCE_IS_NOT_SERVICE,
    MEASURED_VALUES_ONLY,
    NOT_ASSESSED,
    TRANSITION_IS_NOT_ALLOCATION,
    UNCHANGED,
    UNEXPLAINED_DRIFT,
    AdmittedNativeDefaultTransition,
    NativeDefaultContext,
    assess_intended_pool_coexistence,
    assess_native_default_transition,
)
from packet_tracer_mcp.infrastructure.catalog.dhcp_native_default_transitions import (
    WHOLE_CONFIGURE_PC_IP,
    admitted_native_default_transitions,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)

BUILD = "9.0.1.0858"

#: `d0_baseline` and `d0_control` of `d-dhcp-2026-09-21T20-01-43Z-dffd6c3b`.
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
#: `d1_after_server_address`, and unchanged through `d2`, `d3` and `d4`.
REALIGNED = {
    "name": "serverPool",
    "network": "192.0.2.0",
    "mask": "255.255.255.0",
    "gateway": "0.0.0.0",
    "dns": "0.0.0.0",
    "start": "192.0.2.0",
    "end": "192.0.3.255",
    "max": 512,
}
#: The intended pool the same run wrote while the process was still disabled.
INTENDED = {
    "name": "MCP_E6Q_DHCP",
    "network": "192.0.2.0",
    "mask": "255.255.255.0",
    "gateway": "192.0.2.1",
    "dns": "192.0.2.10",
    "start": "192.0.2.100",
    "end": "192.0.2.100",
    "max": 1,
}

CONTEXT = NativeDefaultContext(
    model="Server-PT",
    backend_version=BUILD,
    interface="FastEthernet0",
    intervention=WHOLE_CONFIGURE_PC_IP,
)


def _assess(before: Any, after: Any, *, context: Any = None, **kwargs: Any):
    """Assess one pair against the catalog record of the measured build."""
    return assess_native_default_transition(
        before=before,
        after=after,
        context=context or CONTEXT,
        admitted=admitted_native_default_transitions(BUILD),
        **kwargs,
    )


# -- C1, C2: the measured transition, and the two states kept apart ------------


def test_the_exact_measured_transition_is_admitted():
    """The whole `configurePcIp` interval moved four fields, and only those."""
    assessment = _assess([STOCK], [REALIGNED])

    assert assessment.classification == ADMITTED_REALIGNMENT
    assert assessment.admitted is True
    assert assessment.changed_fields == (
        "serverPool.end",
        "serverPool.mask",
        "serverPool.network",
        "serverPool.start",
    )
    assert assessment.causes == ()
    assert assessment.matched_evidence.endswith("d-dhcp-2026-09-21T20-01-43Z-dffd6c3b")
    assert MEASURED_VALUES_ONLY in assessment.limitations


def test_the_post_e5_state_is_never_treated_as_a_baseline():
    """`d1` to `d2` and `d2` to `d3` moved nothing, and that is its own answer."""
    later = _assess([REALIGNED], [REALIGNED])

    assert later.classification == UNCHANGED
    assert later.changed_fields == ()
    # And the reverse pair is not the admitted transition read backwards.
    reversed_pair = _assess([REALIGNED], [STOCK])
    assert reversed_pair.classification == UNEXPLAINED_DRIFT


def test_an_unobserved_reading_decides_nothing():
    """A snapshot that was not read is not a comparison."""
    for flags, expected in (
        ({"before_observed": False}, "native_default_unobserved:before"),
        ({"after_observed": False}, "native_default_unobserved:after"),
    ):
        assessment = _assess([STOCK], [REALIGNED], **flags)
        assert assessment.classification == NOT_ASSESSED
        assert assessment.causes == (expected,)


# -- C3, C4, C5: every unrelated difference refuses ----------------------------


@pytest.mark.parametrize(
    "field",
    ["gateway", "dns", "max"],
)
def test_a_field_outside_the_measured_set_refuses(field: str):
    """A fifth moved field is drift, even beside the four that were measured."""
    after = {**REALIGNED, field: ("10.0.0.1" if field != "max" else 1024)}

    assessment = _assess([STOCK], [after])

    assert assessment.classification == UNEXPLAINED_DRIFT
    assert "no_reviewed_transition_matches_this_observation" in assessment.causes


def test_a_measured_field_landing_on_an_unmeasured_value_refuses():
    """The changed set can match while the values do not, and that is drift."""
    after = {**REALIGNED, "end": "192.0.7.255"}

    assessment = _assess([STOCK], [after])

    assert assessment.classification == UNEXPLAINED_DRIFT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "Server-PT-2"),
        ("backend_version", "9.0.2.0000"),
        ("interface", "FastEthernet1"),
        ("intervention", "set_ip_address_only"),
    ],
)
def test_a_different_context_refuses(field: str, value: str):
    """One reviewed situation says nothing about another one."""
    assessment = _assess(
        [STOCK],
        [REALIGNED],
        context=NativeDefaultContext(
            **{
                "model": CONTEXT.model,
                "backend_version": CONTEXT.backend_version,
                "interface": CONTEXT.interface,
                "intervention": CONTEXT.intervention,
                field: value,
            }
        ),
    )

    assert assessment.classification == UNEXPLAINED_DRIFT
    # The cause names which part of the reviewed situation differed, so "no
    # record for this build" stays distinguishable from "a record for this
    # build that describes another interface or another call".
    assert f"context_differs:{field}" in assessment.causes


def test_an_unmeasured_network_refuses_under_the_same_relationship():
    """The arithmetic that held once is not the reason the once was admitted.

    `198.51.100.0/24` with a `.10` server follows exactly the relationship the
    measured case follows: the network is the masked address, the start is the
    network, and the end is the start plus `max` minus one. It is refused
    because nobody measured it, which is the whole point of comparing values
    instead of computing them.
    """
    unmeasured_after = {
        "name": "serverPool",
        "network": "198.51.100.0",
        "mask": "255.255.255.0",
        "gateway": "0.0.0.0",
        "dns": "0.0.0.0",
        "start": "198.51.100.0",
        "end": "198.51.101.255",
        "max": 512,
    }

    assessment = _assess([STOCK], [unmeasured_after])

    assert assessment.classification == UNEXPLAINED_DRIFT
    assert assessment.changed_fields == (
        "serverPool.end",
        "serverPool.mask",
        "serverPool.network",
        "serverPool.start",
    )


def test_a_build_with_no_reviewed_measurement_refuses():
    """An empty record set is a refusal, not a fallback to the measured build."""
    assessment = assess_native_default_transition(
        before=[STOCK],
        after=[REALIGNED],
        context=CONTEXT,
        admitted=admitted_native_default_transitions("9.0.2.0000"),
    )

    assert assessment.classification == UNEXPLAINED_DRIFT


def test_further_change_after_the_admitted_transition_still_refuses():
    """An admitted transition does not make the next one admissible."""
    drifted = {**REALIGNED, "start": "192.0.2.50"}

    assessment = _assess([REALIGNED], [drifted])

    assert assessment.classification == UNEXPLAINED_DRIFT


# -- C6: serverPool cannot be removed, renamed or hidden ----------------------


def test_a_removed_default_is_drift_not_an_admission():
    """A pool that disappeared is the case this decision exists to catch."""
    assessment = _assess([STOCK], [])

    assert assessment.classification == UNEXPLAINED_DRIFT
    assert assessment.causes == ("native_default_removed:serverPool",)


def test_a_renamed_default_is_drift():
    """A rename is a removal and an addition, and neither is the transition."""
    assessment = _assess([STOCK], [{**REALIGNED, "name": "serverPoolRenamed"}])

    assert assessment.classification == UNEXPLAINED_DRIFT
    assert set(assessment.causes) == {
        "native_default_removed:serverPool",
        "native_default_added:serverPoolRenamed",
    }


def test_a_second_default_appearing_is_drift():
    """A new pool beside the default is not a field change of the default."""
    assessment = _assess([STOCK], [REALIGNED, {**INTENDED, "name": "extraPool"}])

    assert assessment.classification == UNEXPLAINED_DRIFT
    assert assessment.causes == ("native_default_added:extraPool",)


def test_two_defaults_moving_at_once_is_drift():
    """No single reviewed record describes two pools moving together."""
    other_before = {**STOCK, "name": "otherPool"}
    other_after = {**STOCK, "name": "otherPool", "start": "10.0.0.1"}

    assessment = _assess([STOCK, other_before], [REALIGNED, other_after])

    assert assessment.classification == UNEXPLAINED_DRIFT
    assert assessment.causes == (
        "more_than_one_native_default_moved:otherPool,serverPool",
    )


@pytest.mark.parametrize(
    "row",
    [
        {"name": "serverPool"},
        {**STOCK, "unexpected": "field"},
        {**STOCK, "max": "512"},
        {**STOCK, "max": True},
        "not-a-mapping",
    ],
)
def test_a_malformed_inventory_decides_nothing(row: Any):
    """A row this module cannot type is not a row it will compare."""
    assessment = _assess([row], [REALIGNED])

    assert assessment.classification == NOT_ASSESSED
    assert assessment.causes == ("native_default_inventory_malformed:before",)


def test_a_duplicated_pool_name_decides_nothing():
    """Two rows claiming one name are not one pool."""
    assessment = _assess([STOCK, STOCK], [REALIGNED])

    assert assessment.classification == NOT_ASSESSED


# -- C7: coexistence is stated and authorizes nothing -------------------------


def test_the_measured_pools_share_a_subnet_and_overlap():
    """The intended single address sits inside the realigned native range."""
    coexistence = assess_intended_pool_coexistence(native=REALIGNED, intended=INTENDED)

    assert coexistence.native_pool_name == "serverPool"
    assert coexistence.intended_pool_name == "MCP_E6Q_DHCP"
    assert coexistence.shares_subnet is True
    assert coexistence.ranges_overlap is True
    assert coexistence.overlapping_addresses == ("192.0.2.100", "192.0.2.100")
    assert "intended_range_is_inside_the_native_default" in coexistence.causes
    assert COEXISTENCE_IS_NOT_SERVICE in coexistence.limitations


def test_a_disjoint_intended_pool_reports_no_overlap():
    """Overlap is measured, not assumed from sharing a device."""
    coexistence = assess_intended_pool_coexistence(
        native=STOCK,
        intended={**INTENDED, "start": "203.0.113.50", "end": "203.0.113.60"},
    )

    assert coexistence.ranges_overlap is False
    assert coexistence.overlapping_addresses == ()
    assert COEXISTENCE_IS_NOT_SERVICE in coexistence.limitations


def test_a_malformed_pool_row_states_no_coexistence():
    """An unreadable row produces a named refusal, not a default answer."""
    coexistence = assess_intended_pool_coexistence(
        native={"name": "serverPool"}, intended=INTENDED
    )

    assert coexistence.shares_subnet is False
    assert coexistence.ranges_overlap is False
    assert coexistence.causes == ("pool_row_malformed:native",)


# -- C8, C9: nothing is authorized and nothing is hardcoded -------------------


@pytest.mark.parametrize(
    ("before", "after", "kwargs"),
    [
        ([STOCK], [REALIGNED], {}),
        ([REALIGNED], [REALIGNED], {}),
        ([STOCK], [], {}),
        ([STOCK], [REALIGNED], {"before_observed": False}),
    ],
)
def test_no_classification_authorizes_allocation(before: Any, after: Any, kwargs: Any):
    """Every answer, including the admitted one, permits nothing."""
    assessment = _assess(before, after, **kwargs)

    assert assessment.authorizes_allocation is False
    assert TRANSITION_IS_NOT_ALLOCATION in assessment.limitations


def test_product_dhcp_capabilities_remain_unknown():
    """This block promotes nothing: the public catalog is untouched."""
    records = packet_tracer_service_capabilities(BUILD)
    profile = records[f"Server-PT:{ServiceType.DHCP.value}"]

    assert profile.application_support is CapabilityStatus.UNKNOWN
    assert profile.direct_readback_support is CapabilityStatus.UNKNOWN
    assert profile.behavioral_verification_support is CapabilityStatus.UNKNOWN


def test_the_domain_module_names_no_backend_version():
    """Backend policy is bound by composition, not written into the decision."""
    from packet_tracer_mcp.domain.enterprise.services import (
        dhcp_native_default_lifecycle as module,
    )

    source = __import__("pathlib").Path(module.__file__).read_text(encoding="utf-8")

    assert BUILD not in source
    assert "Server-PT" not in source.split('"""', 2)[2]


def test_a_caller_supplied_record_never_reaches_the_catalog():
    """A test record is admitted for that call only and mutates nothing public."""
    local = AdmittedNativeDefaultTransition(
        context=CONTEXT,
        pool_name="serverPool",
        before=STOCK,
        after={**REALIGNED, "gateway": "192.0.2.1"},
        changed_fields=("end", "gateway", "mask", "network", "start"),
        evidence="test-only",
    )

    admitted = assess_native_default_transition(
        before=[STOCK],
        after=[{**REALIGNED, "gateway": "192.0.2.1"}],
        context=CONTEXT,
        admitted=(local,),
    )
    assert admitted.classification == ADMITTED_REALIGNMENT
    assert admitted.matched_evidence == "test-only"

    # The public catalog still holds exactly the one reviewed record.
    catalog = admitted_native_default_transitions(BUILD)
    assert len(catalog) == 1
    assert catalog[0].evidence != "test-only"
    assert _assess([STOCK], [{**REALIGNED, "gateway": "192.0.2.1"}]).classification == (
        UNEXPLAINED_DRIFT
    )
