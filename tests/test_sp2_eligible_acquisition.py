"""Prospective cohort rules preserve assigned observers and shared contradictions."""

from dataclasses import replace

import pytest

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    SP2_ACQUISITION_ARMS,
    MeasurementConclusion,
)
from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import LeaseRow
from tests.test_sp2_acquisition_discriminator import (
    CLIENT_POOLS,
    LEASES,
    MACS,
    _sample,
    _scan,
)
from tests.test_sp2_acquisition_discriminator import (
    SERVER as BASE_SERVER,
)

ARMS = {
    name: "explicit_start" if arm == "explicit_start" else "control"
    for name, arm in SP2_ACQUISITION_ARMS.items()
}
STARTS = {name for name, arm in ARMS.items() if arm == "explicit_start"}
OBSERVER = "BR1-DEFAULT-PC-02"
SERVER = {
    **BASE_SERVER,
    "pools": [
        {
            "name": "serverPool",
            "network": "10.80.1.0",
            "mask": "255.255.255.0",
            "gateway": "10.80.1.1",
            "dns": "10.80.1.10",
            "start": "10.80.1.100",
            "end": "10.80.1.104",
            "max": 5,
        },
        {
            "name": "BR1_DATA",
            "network": "10.80.16.0",
            "mask": "255.255.255.240",
            "gateway": "10.80.16.1",
            "dns": "10.80.1.10",
            "start": "10.80.16.2",
            "end": "10.80.16.4",
            "max": 3,
        },
        {
            "name": "BR2_DATA",
            "network": "10.80.33.64",
            "mask": "255.255.255.224",
            "gateway": "10.80.33.65",
            "dns": "10.80.1.10",
            "start": "10.80.33.75",
            "end": "10.80.33.77",
            "max": 3,
        },
    ],
    "excluded_count": 4,
    "exclusions": [
        {"start": address, "end": address}
        for address in ("10.80.1.1", "10.80.1.10", "10.80.16.1", "10.80.33.65")
    ],
}


def _rules():
    from packet_tracer_mcp.domain.enterprise.services import sp2_eligible_acquisition

    return sp2_eligible_acquisition


def test_e9_assigned_subject_is_observed_without_blocking_eligible_comparisons():
    """E9 assigned subject is observed without blocking eligible comparisons."""
    cohort = _rules().eligible_cohort(
        ARMS, CLIENT_POOLS, _sample(1, {OBSERVER}), SERVER
    )
    assert cohort.holds, cohort.causes
    assert len(cohort.eligible) == 10
    assert OBSERVER not in cohort.eligible
    assert cohort.observations[OBSERVER] == "assigned_observer"


def test_an_unobserved_competing_pool_authorizes_no_cohort():
    """An unobserved competing pool authorizes no cohort."""
    sample = _sample(1, {OBSERVER}, unobserved_pools={"BR2_DATA"})
    cohort = _rules().eligible_cohort(ARMS, CLIENT_POOLS, sample, SERVER)
    assert not cohort.holds
    assert any("pool_unscanned:BR2_DATA" in cause for cause in cohort.causes)


def test_an_excluded_observers_duplicate_mac_is_still_a_shared_contradiction():
    """An excluded observers duplicate mac is still a shared contradiction."""
    sample = _sample(1, {OBSERVER})
    readings = dict(sample.readings)
    target = "HQ-DEFAULT-PC-02"
    readings[OBSERVER] = replace(readings[OBSERVER], mac=MACS[target])
    cohort = _rules().eligible_cohort(
        ARMS, CLIENT_POOLS, replace(sample, readings=readings), SERVER
    )
    assert not cohort.holds
    assert any("duplicate_mac" in cause for cause in cohort.causes)


def test_an_unknown_client_is_not_eligible_or_an_assigned_observer():
    """An unknown client is not eligible or an assigned observer."""
    sample = _sample(1, {OBSERVER})
    name = "HQ-DEFAULT-PC-01"
    readings = dict(sample.readings)
    readings[name] = replace(readings[name], observed=False)
    cohort = _rules().eligible_cohort(
        ARMS, CLIENT_POOLS, replace(sample, readings=readings), SERVER
    )
    assert name not in cohort.eligible
    assert cohort.observations[name] == "unobserved"


def test_missing_control_in_the_intended_pool_refuses_causal_assignment():
    """Missing control in the intended pool refuses causal assignment."""
    sample = _sample(1, {"BR1-DEFAULT-PC-02", "BR1-DEFAULT-PC-03"})
    cohort = _rules().eligible_cohort(ARMS, CLIENT_POOLS, sample, SERVER)
    assert not cohort.holds
    assert "comparison_absent:BR1_DATA:control" in cohort.causes


@pytest.mark.parametrize("late_kind", ["server", "pool", "binding"])
def test_a_later_shared_or_required_contradiction_revokes_causal_success(late_kind):
    """A later shared or required contradiction revokes causal success."""
    samples = [_sample(index, STARTS | {OBSERVER}) for index in range(1, 4)]
    servers = [SERVER, SERVER, SERVER]
    if late_kind == "server":
        servers[-1] = {**SERVER, "enabled": False}
    elif late_kind == "pool":
        samples[-1] = _sample(3, STARTS | {OBSERVER}, unobserved_pools={"BR2_DATA"})
    else:
        samples[-1] = replace(samples[-1], bindings=None)
    eligible = {name: arm for name, arm in ARMS.items() if name != OBSERVER}
    assessment = _rules().assess_eligible_arms(
        eligible,
        CLIENT_POOLS,
        {name: "dispatched" if name in STARTS else "none" for name in eligible},
        samples,
        servers,
    )
    assert assessment.conclusion is MeasurementConclusion.INCONCLUSIVE


def test_stable_explicit_acquisitions_with_unchanged_controls_are_supported_in_sample():
    """Stable explicit acquisitions with unchanged controls are supported in sample."""
    samples = [_sample(index, STARTS | {OBSERVER}) for index in range(1, 4)]
    eligible = {name: arm for name, arm in ARMS.items() if name != OBSERVER}
    assessment = _rules().assess_eligible_arms(
        eligible,
        CLIENT_POOLS,
        {name: "dispatched" if name in STARTS else "none" for name in eligible},
        samples,
        [SERVER] * 3,
    )
    assert assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert assessment.facts["pattern"] == "explicit_start_only"
    observer = assessment.facts["all_subjects"][OBSERVER]
    assert observer["acquired"] is False
    assert observer["observed_stable_lease"] is True
    assert observer["arm"] == "observer"


def test_an_acquisition_before_intervention_cannot_be_counted_as_effect_success():
    """An acquisition before intervention cannot be counted as effect success."""
    samples = [_sample(index, STARTS | {OBSERVER}) for index in range(1, 4)]
    eligible = {name: arm for name, arm in ARMS.items() if name != OBSERVER}
    interventions = {
        name: "dispatched" if name in STARTS else "none" for name in eligible
    }
    interventions["BR1-DEFAULT-PC-01"] = "observed_before_intervention"
    assessment = _rules().assess_eligible_arms(
        eligible, CLIENT_POOLS, interventions, samples, [SERVER] * 3
    )
    assert assessment.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "comparison_absent:BR1_DATA:explicit_start" in assessment.causes


@pytest.mark.parametrize("drift", ["dns", "max", "exclusions"])
def test_changed_or_unreadable_shared_policy_is_not_eligibility(drift):
    """Changed or unreadable shared policy is not eligibility."""
    server = {**SERVER, "pools": [dict(row) for row in SERVER["pools"]]}
    if drift == "exclusions":
        server["exclusions"] = []
    else:
        server["pools"][0][drift] = "unobservable"
    cohort = _rules().eligible_cohort(ARMS, CLIENT_POOLS, _sample(1, set()), server)
    assert not cohort.holds


def test_repeated_rows_for_an_assigned_observer_refuse_shared_causal_credit():
    """An excluded observer still participates in repeated identity detection."""
    sample = _sample(
        1,
        {OBSERVER},
        extra_rows=[
            (
                "BR1_DATA",
                LeaseRow(1, LEASES[OBSERVER], MACS[OBSERVER], 3600.0, "FastEthernet0"),
            )
        ],
    )
    cohort = _rules().eligible_cohort(ARMS, CLIENT_POOLS, sample, SERVER)
    assert not cohort.holds


def test_a_new_matching_identity_after_acquisition_revokes_the_causal_result():
    """A later matching row cannot conceal changed acquired client identity."""
    target = "BR2-DEFAULT-PC-01"
    samples = [_sample(index, STARTS | {OBSERVER}) for index in range(1, 4)]
    readings = dict(samples[-1].readings)
    readings[target] = replace(readings[target], mac="0001.0000.FFFF")
    scans = dict(samples[-1].scans)
    scans["BR2_DATA"] = _scan(
        "BR2_DATA",
        LeaseRow(0, LEASES[target], "0001.0000.FFFF", 3600.0, "FastEthernet0"),
    )
    samples[-1] = replace(samples[-1], readings=readings, scans=scans)
    eligible = {name: arm for name, arm in ARMS.items() if name != OBSERVER}
    assessment = _rules().assess_eligible_arms(
        eligible,
        CLIENT_POOLS,
        {name: "dispatched" if name in STARTS else "none" for name in eligible},
        samples,
        [SERVER] * 3,
    )
    assert assessment.conclusion is MeasurementConclusion.INCONCLUSIVE


def test_an_excluded_observers_wrong_mac_row_refuses_every_causal_result():
    """Excluding a subject cannot hide a wrong identity in its intended pool."""
    sample = _sample(1, {OBSERVER})
    scans = dict(sample.scans)
    scans["BR1_DATA"] = _scan(
        "BR1_DATA",
        LeaseRow(0, LEASES[OBSERVER], "0001.0000.FFFF", 3600.0, "FastEthernet0"),
    )
    sample = replace(sample, scans=scans)
    cohort = _rules().eligible_cohort(ARMS, CLIENT_POOLS, sample, SERVER)
    assert not cohort.holds
    samples = []
    for index in range(1, 4):
        observed = _sample(index, STARTS | {OBSERVER})
        own = observed.scans["BR1_DATA"]
        scans = dict(observed.scans)
        scans["BR1_DATA"] = _scan(
            "BR1_DATA",
            *(
                replace(row, mac="0001.0000.FFFF")
                if row.ip == LEASES[OBSERVER]
                else row
                for row in own.rows
            ),
        )
        samples.append(replace(observed, scans=scans))
    eligible = {name: arm for name, arm in ARMS.items() if name != OBSERVER}
    assessment = _rules().assess_eligible_arms(
        eligible,
        CLIENT_POOLS,
        {name: "dispatched" if name in STARTS else "none" for name in eligible},
        samples,
        [SERVER] * 3,
    )
    assert assessment.conclusion is MeasurementConclusion.INCONCLUSIVE
