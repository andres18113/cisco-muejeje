"""Derive the E5 configuration policy that the requested services imply.

One decision lives here, and it has to be taken BEFORE E5 compiles: which DNS
server address every static client endpoint is configured with and which
canonical segments delegate DHCP to Server-PT. `E5` already knows how to place
`ConfigurationPolicy.dns_server` on
`SetEndpointStaticAddress`, and the runtime already carries it into
`configurePcIp`. What never existed was the step that reads the requested DNS
service and fills the policy, so a product invocation that asked for DNS left
every client with no resolver configured and then verified resolution against
a client that could not resolve anything.

The derivation is deliberately narrow:

- it reads only the intent, so it is pure and can run before anything is
  composed, let alone applied;
- it never invents an address. A DNS service without an explicit `address` is
  `DNS_SERVER_ADDRESS_REQUIRED`, not a guess and not a silent skip. Deriving
  the address from whatever E5 later assigns to the host is a two-pass
  allocator, which is deferred work, not a shortcut to take here;
- two requested DNS services that disagree about the authority are
  `DNS_AUTHORITY_CONFLICT`. Choosing one of them arbitrarily would configure
  every client against a server the operator did not pick.

The caller's policy object is never mutated: the derivation returns a copy, so
a caller that passes its own base policy still owns the object it passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...models.plans import DevicePlan, TopologyPlan
from ..models.configuration import (
    ConfigurationIssue,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigurationPolicy,
)
from ..models.enterprise_plan import EnterprisePlan
from ..models.intent import EnterpriseIntent
from ..models.requirements import EndpointRequirement, ServiceRequirement
from ..models.roles import DeviceRole
from ..models.segments import SegmentRole
from ..models.service_plan import ServiceType
from .segment_assignment import SegmentAssignmentPolicy


@dataclass(frozen=True)
class ServicePolicyDerivation:
    """The derived policy, or the issues that stop it being derived."""

    policy: ConfigurationPolicy
    issues: list[ConfigurationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Whether no derived issue is an error."""
        return not any(
            item.severity is ConfigurationIssueSeverity.ERROR for item in self.issues
        )


def _requested_services(
    intent: EnterpriseIntent,
) -> list[tuple[str, ServiceRequirement]]:
    """Return every requested service with the site that asked for it.

    The intent names sites; the site identifier only exists once the designer
    has produced a plan, which has not happened yet at derivation time.
    """
    return [
        (site.name, requirement)
        for site in intent.sites
        for requirement in site.services
    ]


def _is_dns(requirement: ServiceRequirement) -> bool:
    """Whether this requirement asks for DNS, by type or by its own name."""
    if requirement.service_type is not None:
        return requirement.service_type is ServiceType.DNS
    return requirement.name.strip().casefold() == ServiceType.DNS.value


def _is_dhcp(requirement: ServiceRequirement) -> bool:
    """Whether this requirement explicitly asks for Server-PT DHCP."""
    if requirement.service_type is not None:
        return requirement.service_type is ServiceType.DHCP
    return requirement.name.strip().casefold() == ServiceType.DHCP.value


def _canonical_services(
    enterprise: EnterprisePlan,
) -> list[tuple[str, ServiceRequirement]]:
    """Return services with canonical site ids produced by the designer."""
    values = [
        (site.site_id, requirement)
        for site in enterprise.sites
        for requirement in site.services
    ]
    values.extend(
        (requirement.metadata.get("site_id", ""), requirement)
        for requirement in enterprise.services
    )
    return values


def _device_segment(
    device: DevicePlan,
    enterprise: EnterprisePlan,
) -> str:
    """Resolve one canonical device to exactly one canonical segment."""
    explicit = device.metadata.get("segment_role", "").strip()
    try:
        role = (
            SegmentRole(explicit)
            if explicit
            else SegmentAssignmentPolicy().segment_for(
                EndpointRequirement(
                    role=DeviceRole(device.enterprise_role),
                    count=1,
                    wired=not device.wireless,
                    wireless=device.wireless,
                )
            )
        )
    except (ValueError, TypeError):
        return ""
    matches = [
        segment.name
        for site in enterprise.sites
        if site.site_id == device.site_id
        for segment in site.segments
        if segment.role is role
    ]
    return matches[0] if len(matches) == 1 else ""


def derive_service_policy(
    intent: EnterpriseIntent,
    *,
    base_policy: ConfigurationPolicy | None = None,
    enterprise: EnterprisePlan | None = None,
    topology: TopologyPlan | None = None,
) -> ServicePolicyDerivation:
    """Derive the configuration policy the requested services require.

    Returns a copy of `base_policy` (or a default policy) with `dns_server`
    set from the single explicit DNS service address the intent requests. An
    intent that requests no DNS service derives no DNS server and reports no
    issue: there is nothing to configure and nothing to complain about.
    """
    policy = (base_policy or ConfigurationPolicy()).model_copy(deep=True)
    issues: list[ConfigurationIssue] = []
    addresses: dict[str, list[str]] = {}

    services = (
        _canonical_services(enterprise)
        if enterprise is not None
        else _requested_services(intent)
    )
    for site_id, requirement in services:
        if not _is_dns(requirement):
            continue
        subject = f"service/{site_id or 'global'}/{requirement.name}"
        address = requirement.address.strip()
        if not address:
            issues.append(
                ConfigurationIssue(
                    severity=ConfigurationIssueSeverity.ERROR,
                    code=ConfigurationIssueCode.DNS_SERVER_ADDRESS_REQUIRED,
                    message=(
                        f"DNS service {requirement.name!r} has no explicit address, "
                        "so no client DNS server can be derived for it."
                    ),
                    subject=subject,
                )
            )
            continue
        addresses.setdefault(address, []).append(subject)

    if len(addresses) > 1:
        issues.append(
            ConfigurationIssue(
                severity=ConfigurationIssueSeverity.ERROR,
                code=ConfigurationIssueCode.DNS_AUTHORITY_CONFLICT,
                message=(
                    "Requested DNS services declare incompatible authorities: "
                    + ", ".join(sorted(addresses))
                ),
                subject=",".join(
                    sorted(subject for group in addresses.values() for subject in group)
                ),
            )
        )
        return ServicePolicyDerivation(policy=policy, issues=issues)

    if len(addresses) == 1:
        policy.dns_server = next(iter(addresses))

    dhcp = [item for item in services if _is_dhcp(item[1])]
    if not dhcp:
        return ServicePolicyDerivation(policy=policy, issues=issues)
    if enterprise is None or topology is None:
        issues.append(
            ConfigurationIssue(
                severity=ConfigurationIssueSeverity.ERROR,
                code=ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT,
                message=(
                    "Server-PT DHCP authority requires canonical enterprise and "
                    "topology identities before E5 compilation."
                ),
                subject="dhcp",
            )
        )
        return ServicePolicyDerivation(policy=policy, issues=issues)

    devices = {item.id or item.name: item for item in topology.devices}
    segments = {
        segment.name: (site.site_id, segment)
        for site in enterprise.sites
        for segment in site.segments
    }
    delegated: dict[str, str] = {}
    for site_id, requirement in sorted(
        dhcp, key=lambda item: (item[0], item[1].name.casefold())
    ):
        subject = f"service/{site_id or 'global'}/{requirement.name}"
        segment_id = requirement.segment_id.strip()
        segment_entry = segments.get(segment_id)
        host = devices.get(requirement.host_device_id)
        if (
            not segment_id
            or segment_entry is None
            or segment_entry[0] != site_id
            or host is None
            or host.site_id != site_id
            or host.model.casefold() != "server-pt"
        ):
            issues.append(
                ConfigurationIssue(
                    severity=ConfigurationIssueSeverity.ERROR,
                    code=ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT,
                    message=(
                        f"DHCP service {requirement.name!r} does not identify one "
                        "canonical Server-PT and segment in its site."
                    ),
                    subject=subject,
                )
            )
            continue
        host_segment = _device_segment(host, enterprise)
        if host_segment != segment_id:
            observed_segment = host_segment or "an unresolved segment"
            issues.append(
                ConfigurationIssue(
                    severity=ConfigurationIssueSeverity.ERROR,
                    code=ConfigurationIssueCode.DHCP_RELAY_REQUIRED,
                    message=(
                        f"DHCP server {host.id!r} is on {observed_segment}, not "
                        f"delegated segment {segment_id!r}."
                    ),
                    subject=subject,
                )
            )
            continue
        foreign_clients = sorted(
            client_id
            for client_id in requirement.client_device_ids
            if (client := devices.get(client_id)) is None
            or _device_segment(client, enterprise) != segment_id
        )
        if foreign_clients:
            issues.append(
                ConfigurationIssue(
                    severity=ConfigurationIssueSeverity.ERROR,
                    code=ConfigurationIssueCode.DHCP_RELAY_REQUIRED,
                    message=(
                        "Delegated DHCP clients are missing or outside the server "
                        "segment: " + ", ".join(foreign_clients)
                    ),
                    subject=subject,
                )
            )
            continue
        if segment_id in delegated:
            issues.append(
                ConfigurationIssue(
                    severity=ConfigurationIssueSeverity.ERROR,
                    code=ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT,
                    message=(
                        f"Segment {segment_id!r} is delegated to both "
                        f"{delegated[segment_id]!r} and {requirement.host_device_id!r}."
                    ),
                    subject=subject,
                )
            )
            continue
        if site_id in policy.dhcp_server_device_ids:
            issues.append(
                ConfigurationIssue(
                    severity=ConfigurationIssueSeverity.ERROR,
                    code=ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT,
                    message=(
                        f"Segment {segment_id!r} has both an explicit IOS DHCP "
                        "authority and an explicit Server-PT authority."
                    ),
                    subject=subject,
                )
            )
            continue
        delegated[segment_id] = requirement.host_device_id

    policy.delegated_dhcp_segment_ids = sorted(delegated)
    policy.delegated_dhcp_server_device_ids = dict(sorted(delegated.items()))

    return ServicePolicyDerivation(policy=policy, issues=issues)
