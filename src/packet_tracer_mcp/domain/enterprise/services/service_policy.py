"""Derive the E5 configuration policy that the requested services imply.

One decision lives here, and it has to be taken BEFORE E5 compiles: which DNS
server address every static client endpoint is configured with. `E5` already
knows how to place `ConfigurationPolicy.dns_server` on
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

from ..models.configuration import (
    ConfigurationIssue,
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigurationPolicy,
)
from ..models.intent import EnterpriseIntent
from ..models.requirements import ServiceRequirement
from ..models.service_plan import ServiceType


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


def derive_service_policy(
    intent: EnterpriseIntent,
    *,
    base_policy: ConfigurationPolicy | None = None,
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

    for site_id, requirement in _requested_services(intent):
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

    return ServicePolicyDerivation(policy=policy, issues=issues)
