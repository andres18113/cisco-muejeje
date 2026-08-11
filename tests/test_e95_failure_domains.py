"""E9.5 regression tests for backend-neutral failure-domain semantics."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.failure_domain import (
    FailureDomain,
    FailureDomainProvenance,
    FailureDomainType,
    FailurePath,
    FailureScenario,
    FailureScenarioScope,
    IndependenceStatus,
)
from src.packet_tracer_mcp.domain.enterprise.services.failure_domain_analyzer import (
    FailureDomainAnalyzer,
    build_failure_domain_catalog,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan


def _topology() -> TopologyPlan:
    return TopologyPlan(
        id="topology/redundant",
        physical_topology_hash="physical-v2",
        devices=[
            DevicePlan(id="SRC", name="SRC", model="2911", category="router", site_id="HQ"),
            DevicePlan(id="R1", name="R1", model="2911", category="router", site_id="HQ"),
            DevicePlan(id="R2", name="R2", model="2911", category="router", site_id="HQ"),
            DevicePlan(id="DST", name="DST", model="2911", category="router", site_id="HQ"),
        ],
        links=[
            LinkPlan(id="L1", device_a="SRC", port_a="g0/0", device_b="R1", port_b="g0/0", device_a_id="SRC", device_b_id="R1"),
            LinkPlan(id="L2", device_a="R1", port_a="g0/1", device_b="DST", port_b="g0/0", device_a_id="R1", device_b_id="DST"),
            LinkPlan(id="L3", device_a="SRC", port_a="g0/1", device_b="R2", port_b="g0/0", device_a_id="SRC", device_b_id="R2"),
            LinkPlan(id="L4", device_a="R2", port_a="g0/1", device_b="DST", port_b="g0/1", device_a_id="R2", device_b_id="DST"),
        ],
    )


def _paths() -> tuple[FailurePath, FailurePath]:
    return (
        FailurePath(
            id="primary",
            device_ids=["SRC", "R1", "DST"],
            link_ids=["L1", "L2"],
            endpoint_device_ids=["SRC", "DST"],
        ),
        FailurePath(
            id="surviving",
            device_ids=["SRC", "R2", "DST"],
            link_ids=["L3", "L4"],
            endpoint_device_ids=["SRC", "DST"],
        ),
    )


def test_catalog_derives_only_facts_present_in_topology() -> None:
    first = build_failure_domain_catalog(_topology())
    second = build_failure_domain_catalog(_topology().model_copy(deep=True))

    assert first.semantic_hash == second.semantic_hash
    assert {item.domain_type for item in first.domains} == {
        FailureDomainType.DEVICE,
        FailureDomainType.LINK,
        FailureDomainType.SITE,
    }
    assert all(
        item.provenance is FailureDomainProvenance.DERIVED
        for item in first.domains
    )
    assert not first.domains_of_type(FailureDomainType.CHASSIS)
    assert not first.domains_of_type(FailureDomainType.POWER)
    assert not first.domains_of_type(FailureDomainType.UPLINK_PROVIDER)
    assert not first.domains_of_type(FailureDomainType.SHARED_RISK)


def test_link_fault_paths_can_ignore_only_their_common_endpoints() -> None:
    primary, surviving = _paths()
    result = FailureDomainAnalyzer().analyze(
        FailureScenario(
            id="fail/l1",
            scope=FailureScenarioScope.LINK_FAULT,
            primary_path=primary,
            surviving_path=surviving,
        ),
        build_failure_domain_catalog(_topology()),
    )

    assert result.status is IndependenceStatus.INDEPENDENT
    assert result.ignored_common_endpoint_device_ids == ["DST", "SRC"]
    assert result.blocking_domain_ids == []
    assert result.missing_coverage == []


def test_link_fault_detects_shared_transit_device_and_shared_risk_group() -> None:
    topology = _topology()
    primary, surviving = _paths()
    surviving.device_ids = ["SRC", "R1", "R2", "DST"]
    catalog = build_failure_domain_catalog(
        topology,
        explicit_domains=[
            FailureDomain(
                id="srg/conduit-a",
                domain_type=FailureDomainType.SHARED_RISK,
                provenance=FailureDomainProvenance.EXPLICIT,
                link_ids=["L1", "L3"],
                evidence_reference="site-survey-42",
            ),
        ],
    )

    result = FailureDomainAnalyzer().analyze(
        FailureScenario(
            id="fail/conduit-a",
            scope=FailureScenarioScope.LINK_FAULT,
            primary_path=primary,
            surviving_path=surviving,
        ),
        catalog,
    )

    assert result.status is IndependenceStatus.NOT_INDEPENDENT
    assert "derived/device/R1" in result.blocking_domain_ids
    assert "srg/conduit-a" in result.blocking_domain_ids


def test_power_scope_never_ignores_common_path_endpoints() -> None:
    primary, surviving = _paths()
    explicit = [
        FailureDomain(
            id=f"power/{device_id.lower()}",
            domain_type=FailureDomainType.POWER,
            provenance=FailureDomainProvenance.EXPLICIT,
            device_ids=[device_id],
            evidence_reference="rack-power-map",
        )
        for device_id in ("SRC", "R1", "R2", "DST")
    ]
    result = FailureDomainAnalyzer().analyze(
        FailureScenario(
            id="fail/power",
            scope=FailureScenarioScope.POWER_FAULT,
            primary_path=primary,
            surviving_path=surviving,
        ),
        build_failure_domain_catalog(_topology(), explicit_domains=explicit),
    )

    assert result.status is IndependenceStatus.NOT_INDEPENDENT
    assert result.ignored_common_endpoint_device_ids == []
    assert result.blocking_domain_ids == ["power/dst", "power/src"]


def test_missing_power_evidence_is_unknown_instead_of_fabricated() -> None:
    primary, surviving = _paths()
    result = FailureDomainAnalyzer().analyze(
        FailureScenario(
            id="fail/power-unknown",
            scope=FailureScenarioScope.POWER_FAULT,
            primary_path=primary,
            surviving_path=surviving,
        ),
        build_failure_domain_catalog(_topology()),
    )

    assert result.status is IndependenceStatus.UNKNOWN
    assert result.blocking_domain_ids == []
    assert {gap.domain_type for gap in result.missing_coverage} == {
        FailureDomainType.POWER,
    }
    assert set(result.missing_coverage[0].primary_device_ids) == {"SRC", "R1", "DST"}
    assert set(result.missing_coverage[0].surviving_device_ids) == {"SRC", "R2", "DST"}


def test_uplink_provider_independence_requires_complete_declared_link_coverage() -> None:
    primary, surviving = _paths()
    partial = [
        FailureDomain(
            id="provider/a",
            domain_type=FailureDomainType.UPLINK_PROVIDER,
            provenance=FailureDomainProvenance.EXPLICIT,
            link_ids=["L1", "L2"],
            evidence_reference="carrier-contract-a",
        ),
    ]
    scenario = FailureScenario(
        id="fail/provider",
        scope=FailureScenarioScope.UPLINK_PROVIDER_FAULT,
        primary_path=primary,
        surviving_path=surviving,
    )

    incomplete = FailureDomainAnalyzer().analyze(
        scenario,
        build_failure_domain_catalog(_topology(), explicit_domains=partial),
    )
    assert incomplete.status is IndependenceStatus.UNKNOWN

    complete = FailureDomainAnalyzer().analyze(
        scenario,
        build_failure_domain_catalog(
            _topology(),
            explicit_domains=[
                *partial,
                FailureDomain(
                    id="provider/b",
                    domain_type=FailureDomainType.UPLINK_PROVIDER,
                    provenance=FailureDomainProvenance.EXPLICIT,
                    link_ids=["L3", "L4"],
                    evidence_reference="carrier-contract-b",
                ),
            ],
        ),
    )
    assert complete.status is IndependenceStatus.INDEPENDENT


def test_duplicate_domain_ids_are_rejected_without_silent_merging() -> None:
    duplicate = FailureDomain(
        id="domain/duplicate",
        domain_type=FailureDomainType.POWER,
        provenance=FailureDomainProvenance.EXPLICIT,
        device_ids=["R1"],
    )

    try:
        build_failure_domain_catalog(
            _topology(),
            explicit_domains=[duplicate, duplicate.model_copy(deep=True)],
        )
    except ValueError as exc:
        assert "domain/duplicate" in str(exc)
    else:
        raise AssertionError("duplicate failure-domain IDs must fail closed")
