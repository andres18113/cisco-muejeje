"""R-NET-02: the client DNS server is derived, never guessed.

Before S1 nothing filled `ConfigurationPolicy.dns_server`, so a product run
that asked for DNS configured every client with no resolver and then verified
resolution against a client that could not resolve anything. The derivation
closes that, and these tests pin the three answers it is allowed to give:
one explicit address, a typed refusal when there is none, and a typed refusal
when two requested services disagree.
"""

from __future__ import annotations

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigurationPolicy,
)
from packet_tracer_mcp.domain.enterprise.models.intent import (
    EnterpriseIntent,
    SiteIntent,
)
from packet_tracer_mcp.domain.enterprise.models.requirements import ServiceRequirement
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    DnsRecordRequirement,
    ServiceType,
)
from packet_tracer_mcp.domain.enterprise.services.service_policy import (
    derive_service_policy,
)


def _intent(*services: ServiceRequirement) -> EnterpriseIntent:
    return EnterpriseIntent(
        name="SAMPLE-LAB",
        sites=[SiteIntent(name="HQ", type="hq", services=list(services))],
    )


def _dns(name: str = "lab-dns", address: str = "198.18.160.10") -> ServiceRequirement:
    return ServiceRequirement(
        name=name,
        service_type=ServiceType.DNS,
        host_device_id="hq/server/1",
        address=address,
        client_device_ids=["hq/user_pc/1", "hq/user_pc/2"],
        dns_records=[
            DnsRecordRequirement(hostname="www.lab.example", address="198.18.160.10")
        ],
    )


def test_the_explicit_dns_address_becomes_the_client_dns_server():
    """R-NET-02: the requested address reaches the configuration policy."""
    derived = derive_service_policy(_intent(_dns()))

    assert derived.is_valid
    assert derived.policy.dns_server == "198.18.160.10"
    assert derived.issues == []


def test_a_dns_service_without_an_explicit_address_is_refused():
    """No address is a refusal, not a guess and not a silent skip.

    Deriving it from whatever E5 later assigns to the host is the deferred
    two-pass allocator. Guessing here would configure every client against an
    address nobody chose.
    """
    derived = derive_service_policy(_intent(_dns(address="")))

    assert not derived.is_valid
    assert [item.code for item in derived.issues] == [
        ConfigurationIssueCode.DNS_SERVER_ADDRESS_REQUIRED
    ]
    assert derived.issues[0].severity is ConfigurationIssueSeverity.ERROR
    assert derived.policy.dns_server is None


def test_two_disagreeing_dns_authorities_refuse_instead_of_one_winning():
    """R-NET-02: an arbitrary choice would configure every client wrongly."""
    derived = derive_service_policy(
        _intent(
            _dns(name="lab-dns"),
            _dns(name="other-dns", address="198.18.160.11"),
        )
    )

    assert not derived.is_valid
    assert [item.code for item in derived.issues] == [
        ConfigurationIssueCode.DNS_AUTHORITY_CONFLICT
    ]
    assert derived.policy.dns_server is None
    assert "198.18.160.10" in derived.issues[0].message
    assert "198.18.160.11" in derived.issues[0].message


def test_two_services_agreeing_on_one_address_are_not_a_conflict():
    """One authority stated twice is still one authority."""
    derived = derive_service_policy(
        _intent(_dns(name="lab-dns"), _dns(name="lab-dns-secondary"))
    )

    assert derived.is_valid
    assert derived.policy.dns_server == "198.18.160.10"


def test_an_intent_without_dns_derives_nothing_and_complains_about_nothing():
    """No DNS requested is not an error: there is nothing to configure."""
    http = ServiceRequirement(
        name="lab-web",
        service_type=ServiceType.HTTP,
        host_device_id="hq/server/1",
        hostname="www.lab.example",
        http_content="SAMPLE_WEB_PAGE",
    )
    derived = derive_service_policy(_intent(http))

    assert derived.is_valid
    assert derived.policy.dns_server is None
    assert derived.issues == []


def test_the_caller_policy_is_copied_rather_than_mutated():
    """User input is preserved without hidden mutation."""
    """The caller still owns the object it passed in."""
    base = ConfigurationPolicy(native_vlan_id=99)

    derived = derive_service_policy(_intent(_dns()), base_policy=base)

    assert derived.policy is not base
    assert base.dns_server is None
    assert derived.policy.dns_server == "198.18.160.10"
    assert derived.policy.native_vlan_id == 99


def test_a_service_named_dns_without_a_type_is_still_a_dns_authority():
    """The compiler resolves the type from the name, so the policy must too."""
    named = ServiceRequirement(
        name="dns",
        host_device_id="hq/server/1",
        address="198.18.160.10",
    )
    derived = derive_service_policy(_intent(named))

    assert derived.policy.dns_server == "198.18.160.10"
