"""Pure failure-domain inventory and resiliency independence analysis."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable

from ...models.plans import TopologyPlan
from ..models.failure_domain import (
    FailureDomain,
    FailureDomainCatalog,
    FailureDomainCoverageGap,
    FailureDomainIndependenceResult,
    FailureDomainProvenance,
    FailureDomainType,
    FailurePath,
    FailureScenario,
    FailureScenarioScope,
    IndependenceStatus,
)


_REQUIRED_TYPES: dict[FailureScenarioScope, tuple[FailureDomainType, ...]] = {
    FailureScenarioScope.LINK_FAULT: (
        FailureDomainType.LINK,
        FailureDomainType.DEVICE,
    ),
    FailureScenarioScope.DEVICE_FAULT: (FailureDomainType.DEVICE,),
    FailureScenarioScope.CHASSIS_FAULT: (FailureDomainType.CHASSIS,),
    FailureScenarioScope.POWER_FAULT: (FailureDomainType.POWER,),
    FailureScenarioScope.SITE_FAULT: (FailureDomainType.SITE,),
    FailureScenarioScope.UPLINK_PROVIDER_FAULT: (
        FailureDomainType.UPLINK_PROVIDER,
    ),
    FailureScenarioScope.SHARED_RISK_FAULT: (FailureDomainType.SHARED_RISK,),
}

# A link-independent path must not silently reuse a transit device or a declared
# shared-risk group.  Chassis evidence is checked when present, but lack of
# chassis metadata does not poison a link-only claim.  Other scopes require the
# exact physical fact named by the scenario and also honor declared SRGs.
_OPTIONAL_RELEVANT_TYPES: dict[
    FailureScenarioScope, tuple[FailureDomainType, ...]
] = {
    FailureScenarioScope.LINK_FAULT: (
        FailureDomainType.CHASSIS,
        FailureDomainType.SHARED_RISK,
    ),
    FailureScenarioScope.DEVICE_FAULT: (
        FailureDomainType.CHASSIS,
        FailureDomainType.SHARED_RISK,
    ),
    FailureScenarioScope.CHASSIS_FAULT: (FailureDomainType.SHARED_RISK,),
    FailureScenarioScope.POWER_FAULT: (FailureDomainType.SHARED_RISK,),
    FailureScenarioScope.SITE_FAULT: (FailureDomainType.SHARED_RISK,),
    FailureScenarioScope.UPLINK_PROVIDER_FAULT: (
        FailureDomainType.SHARED_RISK,
    ),
    FailureScenarioScope.SHARED_RISK_FAULT: (),
}


def build_failure_domain_catalog(
    topology: TopologyPlan,
    *,
    explicit_domains: Iterable[FailureDomain] = (),
) -> FailureDomainCatalog:
    """Build deterministic domains without inventing unavailable facilities.

    Device and link identity are concrete E4 facts.  Site membership is derived
    only when ``site_id`` is present.  Chassis, power, carrier and shared-risk
    domains must be supplied explicitly by an authoritative caller.
    """

    domains: list[FailureDomain] = []
    seen_ids: set[str] = set()

    def add(domain: FailureDomain) -> None:
        normalized = domain.model_copy(
            update={
                "device_ids": sorted(set(domain.device_ids)),
                "link_ids": sorted(set(domain.link_ids)),
            },
            deep=True,
        )
        if normalized.id in seen_ids:
            raise ValueError(f"duplicate failure-domain id: {normalized.id}")
        seen_ids.add(normalized.id)
        domains.append(normalized)

    for device in sorted(topology.devices, key=lambda item: item.id):
        if not device.id:
            continue
        add(
            FailureDomain(
                id=f"derived/device/{device.id}",
                domain_type=FailureDomainType.DEVICE,
                provenance=FailureDomainProvenance.DERIVED,
                device_ids=[device.id],
                evidence_reference=f"{topology.id}:devices/{device.id}",
            ),
        )

    for link in sorted(topology.links, key=lambda item: item.id):
        if not link.id:
            continue
        add(
            FailureDomain(
                id=f"derived/link/{link.id}",
                domain_type=FailureDomainType.LINK,
                provenance=FailureDomainProvenance.DERIVED,
                link_ids=[link.id],
                evidence_reference=f"{topology.id}:links/{link.id}",
            ),
        )

    site_members: dict[str, list[str]] = defaultdict(list)
    for device in topology.devices:
        if device.id and device.site_id:
            site_members[device.site_id].append(device.id)
    for site_id in sorted(site_members):
        add(
            FailureDomain(
                id=f"derived/site/{site_id}",
                domain_type=FailureDomainType.SITE,
                provenance=FailureDomainProvenance.DERIVED,
                device_ids=site_members[site_id],
                evidence_reference=f"{topology.id}:site/{site_id}",
            ),
        )

    for domain in sorted(explicit_domains, key=lambda item: item.id):
        add(domain)

    ordered = sorted(domains, key=_domain_sort_key)
    payload = {
        "source_topology_id": topology.id,
        "source_topology_hash": topology.physical_identity_hash,
        "domains": [
            {
                "id": item.id,
                "domain_type": item.domain_type.value,
                "provenance": item.provenance.value,
                "device_ids": item.device_ids,
                "link_ids": item.link_ids,
                "blocking": item.blocking,
            }
            for item in ordered
        ],
    }
    return FailureDomainCatalog(
        source_topology_id=topology.id,
        source_topology_hash=topology.physical_identity_hash,
        semantic_hash=_digest(payload),
        domains=ordered,
    )


class FailureDomainAnalyzer:
    """Compare primary and surviving paths under an explicit fault scope."""

    def analyze(
        self,
        scenario: FailureScenario,
        catalog: FailureDomainCatalog,
    ) -> FailureDomainIndependenceResult:
        required_types = set(_REQUIRED_TYPES[scenario.scope])
        required_types.update(scenario.additional_relevant_domain_types)
        relevant_types = required_types | set(_OPTIONAL_RELEVANT_TYPES[scenario.scope])

        common_endpoints: set[str] = set()
        if scenario.scope is FailureScenarioScope.LINK_FAULT:
            common_endpoints = (
                set(scenario.primary_path.effective_endpoint_device_ids)
                & set(scenario.surviving_path.effective_endpoint_device_ids)
            )

        domains = [
            item for item in catalog.domains if item.domain_type in relevant_types
        ]
        blocking_ids: list[str] = []
        ignored_domain_ids: list[str] = []
        for domain in domains:
            primary_raw = _domain_intersects(domain, scenario.primary_path)
            surviving_raw = _domain_intersects(domain, scenario.surviving_path)
            if not (primary_raw and surviving_raw):
                continue

            primary_effective = _domain_intersects(
                domain,
                scenario.primary_path,
                ignored_device_ids=common_endpoints,
            )
            surviving_effective = _domain_intersects(
                domain,
                scenario.surviving_path,
                ignored_device_ids=common_endpoints,
            )
            if not (primary_effective and surviving_effective):
                ignored_domain_ids.append(domain.id)
                continue
            if domain.blocking:
                blocking_ids.append(domain.id)

        gaps = [
            gap
            for domain_type in sorted(required_types, key=lambda item: item.value)
            if (
                gap := _coverage_gap(
                    domain_type,
                    scenario.primary_path,
                    scenario.surviving_path,
                    domains,
                    ignored_device_ids=(
                        common_endpoints
                        if scenario.scope is FailureScenarioScope.LINK_FAULT
                        else set()
                    ),
                )
            )
            is not None
        ]

        blocking_ids = sorted(set(blocking_ids))
        ignored_domain_ids = sorted(set(ignored_domain_ids))
        reasons: list[str] = []
        if blocking_ids:
            status = IndependenceStatus.NOT_INDEPENDENT
            reasons.append(
                "primary and surviving paths share declared blocking failure domains",
            )
        elif gaps:
            status = IndependenceStatus.UNKNOWN
            reasons.append(
                "required failure-domain coverage is incomplete; independence cannot be claimed",
            )
        elif not scenario.primary_path.link_ids or not scenario.surviving_path.link_ids:
            status = IndependenceStatus.UNKNOWN
            reasons.append("both paths require explicit physical link membership")
        else:
            status = IndependenceStatus.INDEPENDENT
            reasons.append("no relevant declared blocking failure domain is shared")

        if common_endpoints:
            reasons.append(
                "common endpoints were ignored only because this is a link-fault scenario",
            )

        return FailureDomainIndependenceResult(
            scenario_id=scenario.id,
            scope=scenario.scope,
            status=status,
            relevant_domain_types=sorted(relevant_types, key=lambda item: item.value),
            blocking_domain_ids=blocking_ids,
            ignored_common_endpoint_device_ids=sorted(common_endpoints),
            ignored_domain_ids=ignored_domain_ids,
            missing_coverage=gaps,
            reasons=reasons,
        )


def _coverage_gap(
    domain_type: FailureDomainType,
    primary: FailurePath,
    surviving: FailurePath,
    domains: list[FailureDomain],
    *,
    ignored_device_ids: set[str],
) -> FailureDomainCoverageGap | None:
    typed = [item for item in domains if item.domain_type is domain_type]
    mapped_devices = {device_id for item in typed for device_id in item.device_ids}
    mapped_links = {link_id for item in typed for link_id in item.link_ids}

    use_links = domain_type in {
        FailureDomainType.LINK,
        FailureDomainType.UPLINK_PROVIDER,
    }
    if domain_type is FailureDomainType.SHARED_RISK:
        use_links = bool(primary.link_ids or surviving.link_ids)

    if use_links:
        primary_missing_links = sorted(set(primary.link_ids) - mapped_links)
        surviving_missing_links = sorted(set(surviving.link_ids) - mapped_links)
        if not primary_missing_links and not surviving_missing_links:
            return None
        return FailureDomainCoverageGap(
            domain_type=domain_type,
            primary_link_ids=primary_missing_links,
            surviving_link_ids=surviving_missing_links,
            reason=f"{domain_type.value} coverage is missing for path links",
        )

    primary_devices = set(primary.device_ids) - ignored_device_ids
    surviving_devices = set(surviving.device_ids) - ignored_device_ids
    primary_missing_devices = sorted(primary_devices - mapped_devices)
    surviving_missing_devices = sorted(surviving_devices - mapped_devices)
    if not primary_missing_devices and not surviving_missing_devices:
        return None
    return FailureDomainCoverageGap(
        domain_type=domain_type,
        primary_device_ids=primary_missing_devices,
        surviving_device_ids=surviving_missing_devices,
        reason=f"{domain_type.value} coverage is missing for path devices",
    )


def _domain_intersects(
    domain: FailureDomain,
    path: FailurePath,
    *,
    ignored_device_ids: set[str] | None = None,
) -> bool:
    ignored = ignored_device_ids or set()
    device_intersection = (set(domain.device_ids) - ignored) & (
        set(path.device_ids) - ignored
    )
    link_intersection = set(domain.link_ids) & set(path.link_ids)
    return bool(device_intersection or link_intersection)


def _domain_sort_key(item: FailureDomain) -> tuple[str, str]:
    return item.domain_type.value, item.id


def _digest(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
