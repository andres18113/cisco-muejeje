"""R-CAP-01..07: capability is a record about a model, not a default.

The catalog used to be a comprehension over `ServiceType` that started every
family SUPPORTED and then demoted the exceptions, and a client expectation
resolved the SERVER's profile. Both are the same mistake in different places:
evidence about one subject was silently applied to another. These tests hold
the two rules that replaced them - a record exists or the answer is UNKNOWN,
and the model that performs an operation is the model whose record decides.
"""

from __future__ import annotations

import pytest

from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    CapabilityProvenance,
    ClientOperationCapability,
    EnableDnsService,
    ServiceActionType,
    ServiceCapabilityProfile,
    ServiceDefinition,
    ServiceEvidenceKind,
    ServicePhase,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.services.service_capability_resolution import (
    provenance_by_key,
    resolve_action_capability,
    resolve_verification_capability,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    BASELINE_PACKET_TRACER_VERSION,
    ServiceCapabilityCatalogError,
    _validate,
    capability_snapshot_hash,
    packet_tracer_service_capabilities,
)

_SERVICE = ServiceDefinition(
    id="service/hq/lab-dns",
    name="lab-dns",
    service_type=ServiceType.DNS,
    site_id="hq",
    host_device_id="hq/server/1",
    host_device_name="HQ-SERVER-01",
    host_model="Server-PT",
    address="198.18.160.10",
    segment_id="hq/data",
    client_device_ids=["hq/user_pc/1"],
    protocol="udp/tcp",
    ports=[53],
)


def _client_expectation(
    kind: ServiceVerificationKind,
    *,
    client_model: str = "PC-PT",
) -> ServiceVerificationExpectation:
    return ServiceVerificationExpectation(
        id=f"verify/{kind.value}",
        service_id=_SERVICE.id,
        action_id="svc/enable-dns/1",
        kind=kind,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id=_SERVICE.host_device_id,
        host_device_name=_SERVICE.host_device_name,
        client_device_id="hq/user_pc/1",
        client_device_name="HQ-PC-01",
        host_model=_SERVICE.host_model,
        client_model=client_model,
    )


# -- the exact build, and every other one ---------------------------------


def test_only_the_baseline_build_has_any_supported_dimension():
    """R-CAP-01: a build with no evidence supports nothing at all."""
    records = packet_tracer_service_capabilities("9.1.0.0001")

    supported = [
        key
        for key, record in records.items()
        if CapabilityStatus.SUPPORTED
        in {
            getattr(record, "support", None),
            getattr(record, "compile_support", None),
            getattr(record, "application_support", None),
            getattr(record, "direct_readback_support", None),
            getattr(record, "behavioral_verification_support", None),
        }
    ]
    assert supported == []
    for record in records.values():
        assert record.source == "no recorded evidence for 9.1.0.0001"


def test_the_unknown_build_still_answers_for_every_dimension():
    """An absent record could be read as permission; an UNKNOWN one cannot."""
    baseline = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)
    other = packet_tracer_service_capabilities("8.2.0.0000")

    assert set(other) >= set(baseline)


# -- the model that performs the operation decides ------------------------


def test_a_client_kind_resolves_the_client_model_not_the_server_profile():
    """The defect this replaces: a PC-PT credited with Server-PT evidence.

    The server's DNS profile is fully SUPPORTED here, including behavioural
    verification. The client has no record, so the answer is UNKNOWN. If this
    ever returns SUPPORTED again, a client is being verified on evidence that
    was never about it.
    """
    records = {
        "Server-PT:dns": ServiceCapabilityProfile(
            service_type=ServiceType.DNS,
            application_support=CapabilityStatus.SUPPORTED,
            direct_readback_support=CapabilityStatus.SUPPORTED,
            behavioral_verification_support=CapabilityStatus.SUPPORTED,
        ),
    }

    resolution = resolve_verification_capability(
        records,
        _client_expectation(ServiceVerificationKind.DNS_RESOLUTION),
        _SERVICE,
    )

    assert resolution.key == "PC-PT:dns_resolution"
    assert resolution.support is CapabilityStatus.UNKNOWN
    assert not resolution.is_supported


def test_a_client_record_authorizes_only_its_own_model():
    """R-CAP-03: a record about PC-PT says nothing about Laptop-PT."""
    records = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)

    known = resolve_verification_capability(
        records,
        _client_expectation(ServiceVerificationKind.DNS_RESOLUTION),
        _SERVICE,
    )
    foreign = resolve_verification_capability(
        records,
        _client_expectation(
            ServiceVerificationKind.DNS_RESOLUTION, client_model="Laptop-PT"
        ),
        _SERVICE,
    )

    assert known.support is CapabilityStatus.SUPPORTED
    assert foreign.key == "Laptop-PT:dns_resolution"
    assert foreign.support is CapabilityStatus.UNKNOWN


def test_a_host_direct_expectation_still_resolves_the_service_profile():
    """A host read-back is the one case the service profile answers."""
    records = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)
    direct = ServiceVerificationExpectation(
        id="verify/direct",
        service_id=_SERVICE.id,
        action_id="svc/enable-dns/1",
        kind=ServiceVerificationKind.DIRECT_SERVICE_STATE,
        evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
        host_device_id=_SERVICE.host_device_id,
        host_device_name=_SERVICE.host_device_name,
        host_model=_SERVICE.host_model,
    )

    resolution = resolve_verification_capability(records, direct, _SERVICE)

    assert resolution.support is CapabilityStatus.SUPPORTED


def test_the_advisory_client_dns_reader_stays_unknown():
    """R-CAP-06: it is never inferred from another getter on the same client."""
    records = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)

    advisory = resolve_verification_capability(
        records,
        _client_expectation(ServiceVerificationKind.CLIENT_DNS_SERVER),
        _SERVICE,
    )
    sibling = resolve_verification_capability(
        records,
        _client_expectation(ServiceVerificationKind.DNS_RESOLUTION),
        _SERVICE,
    )

    assert sibling.support is CapabilityStatus.SUPPORTED
    assert advisory.support is CapabilityStatus.UNKNOWN


def test_an_action_on_a_model_with_no_record_is_unknown():
    """R-CAP-03: a PC-PT action without an entry is never authorized."""
    action = EnableDnsService(
        id="svc/enable-dns/1",
        phase=ServicePhase.ENABLE,
        service_id=_SERVICE.id,
        service_type=ServiceType.DNS,
        host_device_id="hq/user_pc/1",
        host_device_name="HQ-PC-01",
        host_model="PC-PT",
        site_id="hq",
        required_capability="service_dns_application",
    )
    records = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)

    resolution = resolve_action_capability(records, action)

    assert resolution.key == "PC-PT:enable_dns_service"
    assert resolution.support is CapabilityStatus.UNKNOWN


def test_a_server_action_resolves_through_its_service_profile():
    """The profile IS the explicit record for a server-hosted action."""
    action = EnableDnsService(
        id="svc/enable-dns/1",
        phase=ServicePhase.ENABLE,
        service_id=_SERVICE.id,
        service_type=ServiceType.DNS,
        host_device_id=_SERVICE.host_device_id,
        host_device_name=_SERVICE.host_device_name,
        host_model="Server-PT",
        site_id="hq",
        required_capability="service_dns_application",
    )
    records = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)

    assert resolve_action_capability(records, action).is_supported


def test_tftp_publication_is_still_not_inferred_from_tftp_enable():
    """Enabling a process and publishing through it stay separate channels."""
    records = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)
    profile = records["Server-PT:tftp"]

    assert (
        profile.action_application_support[ServiceActionType.PUBLISH_TFTP_FILE.value]
        is CapabilityStatus.UNKNOWN
    )


# -- provenance and construction-time consistency --------------------------


def test_every_baseline_record_is_documentary_and_says_so():
    """R-CAP-07: nothing in the baseline table claims a recorded run."""
    records = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)

    levels = provenance_by_key(records)
    assert set(levels.values()) == {CapabilityProvenance.DOCUMENTARY_BASELINE.value}
    assert set(levels) == set(records)


def test_a_duplicate_record_fails_closed_before_it_becomes_a_dictionary():
    """Two answers for one key must fail, not silently keep the last one."""
    duplicate = ClientOperationCapability(
        key="PC-PT:http_fetch",
        model="PC-PT",
        operation="http_fetch",
        support=CapabilityStatus.UNKNOWN,
        packet_tracer_version=BASELINE_PACKET_TRACER_VERSION,
    )
    records = [
        *packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION).values(),
        duplicate,
    ]

    with pytest.raises(ServiceCapabilityCatalogError, match="Duplicate"):
        _validate(records, BASELINE_PACKET_TRACER_VERSION)


def test_a_record_from_another_build_fails_closed():
    """R-CAP-04: one snapshot describes exactly one build."""
    foreign = ClientOperationCapability(
        key="PC-PT:ntp_sync",
        model="PC-PT",
        operation="ntp_sync",
        support=CapabilityStatus.SUPPORTED,
        packet_tracer_version="7.3.1.0000",
    )

    with pytest.raises(ServiceCapabilityCatalogError, match="declares version"):
        _validate([foreign], BASELINE_PACKET_TRACER_VERSION)


def test_behavioral_support_without_ready_verification_fails_closed():
    """R-CAP-04: a claim its own readiness contradicts is refused."""
    contradictory = ServiceCapabilityProfile(
        service_type=ServiceType.NTP,
        behavioral_verification_support=CapabilityStatus.SUPPORTED,
        packet_tracer_version=BASELINE_PACKET_TRACER_VERSION,
    )

    with pytest.raises(ServiceCapabilityCatalogError, match="readiness"):
        _validate([contradictory], BASELINE_PACKET_TRACER_VERSION)


def test_a_recorded_run_without_its_attribution_fails_closed():
    """A promotion needs the build, the executed SHA and the run identity."""
    unattributed = ClientOperationCapability(
        key="PC-PT:client_dns_server",
        model="PC-PT",
        operation="client_dns_server",
        support=CapabilityStatus.SUPPORTED,
        provenance=CapabilityProvenance.RECORDED_RUN,
        packet_tracer_version=BASELINE_PACKET_TRACER_VERSION,
    )

    with pytest.raises(ServiceCapabilityCatalogError, match="recorded run"):
        _validate([unattributed], BASELINE_PACKET_TRACER_VERSION)


def test_the_snapshot_hash_changes_with_the_records_it_digests():
    """A run names the exact records it resolved, so the digest must bind them."""
    baseline = packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)
    other = packet_tracer_service_capabilities("9.1.0.0001")

    assert capability_snapshot_hash(baseline) == capability_snapshot_hash(
        packet_tracer_service_capabilities(BASELINE_PACKET_TRACER_VERSION)
    )
    assert capability_snapshot_hash(baseline) != capability_snapshot_hash(other)


def test_the_applicator_never_verifies_a_client_on_the_servers_profile():
    """The same rule, through the real applicator rather than the resolver.

    A runtime that would happily report VERIFIED is injected, and the catalog
    authorizes the SERVER completely while saying nothing about the client.
    The client row must come back UNKNOWN with the client key named, and the
    runtime must never have been asked to observe it. Before S1 this row was
    VERIFIED, on the server's evidence.
    """
    from test_enterprise_services import _fixture
    from test_service_application import FakeServiceRuntime

    from packet_tracer_mcp.application.use_cases.apply_services import (
        ServiceApplicator,
    )
    from packet_tracer_mcp.application.use_cases.compile_services import (
        compile_enterprise_services,
    )

    enterprise, topology, configuration, capabilities = _fixture()
    server_only = {
        key: record
        for key, record in capabilities.items()
        if key.startswith("Server-PT:")
    }
    compiled = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=server_only
    )
    assert compiled.is_valid
    plan = compiled.plan
    runtime = FakeServiceRuntime()

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses={
            item.configuration_action_id: ActionExecutionStatus.VERIFIED
            for item in plan.foundational_requirements
        },
        capabilities=server_only,
    )

    client_rows = [
        item
        for item in result.verification_results
        if any(
            expectation.id == item.expectation_id and expectation.client_device_id
            for expectation in plan.verification_expectations
        )
    ]
    assert client_rows
    refused = [
        row for row in client_rows if row.status is ActionExecutionStatus.UNKNOWN
    ]
    assert refused, "no client row was refused for want of a client record"
    for row in refused:
        assert "PC-PT:" in row.message
    # A composed expectation is blocked by its unverified prerequisites before
    # the capability gate is reached, which is the existing DAG rule.
    for row in client_rows:
        assert row.status in {
            ActionExecutionStatus.UNKNOWN,
            ActionExecutionStatus.DEPENDENCY_BLOCKED,
        }
    client_expectation_ids = {
        expectation.id
        for expectation in plan.verification_expectations
        if expectation.client_device_id
    }
    assert not client_expectation_ids & set(runtime.verify_calls), (
        "an unauthorized client operation reached the runtime"
    )
