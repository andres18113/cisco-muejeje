"""SP-1 A-8 (SP1-03, SP1-04): cold HTTP by address first, qualified DNS after.

The order is checked through the real product use case: the recording E6
runtime logs every expectation it is asked to observe, in order, and the log
is the oracle. The compiled plans are the product's own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    EndpointObserver,
    IsolationPreflight,
    ManifestStore,
    RecordingConfigurationRuntime,
    RecordingServiceRuntime,
    deployment_manifest,
    intent_payload,
)
from sp1_routed_fixture import routed_workload

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
)
from packet_tracer_mcp.domain.enterprise.models.verification import (
    PrerequisiteKind,
    VerificationDependencyError,
    VerificationPrerequisite,
    order_verification_expectations,
)
from packet_tracer_mcp.domain.enterprise.services.service_request_order import (
    COLD_REQUEST_PHASE,
    LATER_TRAFFIC_PHASE,
    request_phases,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

HTTP = ServiceVerificationKind.HTTP_FETCH
DNS_KINDS = {
    ServiceVerificationKind.DNS_RESOLUTION,
    ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
    ServiceVerificationKind.HTTP_BY_HOSTNAME,
}


def _dag(plan):
    return [
        item.model_copy(
            update={
                "verification_prerequisites": [
                    VerificationPrerequisite(
                        kind=PrerequisiteKind.VERIFICATION_VERIFIED, reference_id=dep
                    )
                    for dep in item.depends_on
                ]
            }
        )
        for item in plan.verification_expectations
    ]


@pytest.fixture(scope="module")
def routed_plan():
    """Return the compiled routed DNS+HTTP service plan for six clients."""
    return routed_workload()[1].services


def test_every_http_by_address_is_in_the_cold_phase(routed_plan):
    """HTTP by IP and traffic-free reads are phase 0; DNS and names phase 1."""
    phases = request_phases(_dag(routed_plan))
    by_kind: dict[ServiceVerificationKind, set[int]] = {}
    for item in routed_plan.verification_expectations:
        by_kind.setdefault(item.kind, set()).add(phases[item.id])

    assert by_kind[HTTP] == {COLD_REQUEST_PHASE}
    assert by_kind[ServiceVerificationKind.CLIENT_GATEWAY] == {COLD_REQUEST_PHASE}
    for kind in DNS_KINDS:
        assert by_kind[kind] == {LATER_TRAFFIC_PHASE}


def test_the_ranked_order_is_a_barrier(routed_plan):
    """No DNS or hostname request precedes any HTTP-by-IP request."""
    dag = _dag(routed_plan)
    phases = request_phases(dag)
    ordered = order_verification_expectations(dag, rank=lambda item: phases[item.id])
    kinds = [item.kind for item in ordered]

    last_http = max(index for index, kind in enumerate(kinds) if kind is HTTP)
    first_dns = min(index for index, kind in enumerate(kinds) if kind in DNS_KINDS)
    assert last_http < first_dns


def test_a_rank_pointing_back_at_a_later_dependency_is_refused(routed_plan):
    """A rank that would break a dependency is an error, never half-honored."""
    dag = _dag(routed_plan)
    named = next(
        item for item in dag if item.kind is ServiceVerificationKind.HTTP_BY_HOSTNAME
    )

    with pytest.raises(VerificationDependencyError, match="later rank"):
        order_verification_expectations(
            dag, rank=lambda item: 0 if item.id == named.id else 1
        )


def test_a_dns_negative_waits_for_the_same_clients_positive(routed_plan):
    """A negative is qualified only by that client's own positive answer."""
    by_id = {item.id: item for item in routed_plan.verification_expectations}
    for item in routed_plan.verification_expectations:
        if item.kind is not ServiceVerificationKind.DNS_NEGATIVE_CONTROL:
            continue
        assert item.depends_on
        for dependency in item.depends_on:
            positive = by_id[dependency]
            assert positive.kind is ServiceVerificationKind.DNS_RESOLUTION
            assert positive.client_device_id == item.client_device_id
            assert positive.service_id == item.service_id


def test_routed_clients_read_their_gateway_and_local_ones_do_not():
    """The gateway row exists for a cross-segment client only.

    Named delta (SP-1 e2): the reader is measured, so the row is required and
    each client's HTTP-by-address fetch waits for its own gateway read.
    """
    routed = routed_workload()[1].services
    gateways = [
        item
        for item in routed.verification_expectations
        if item.kind is ServiceVerificationKind.CLIENT_GATEWAY
    ]

    assert {item.client_device_name for item in gateways} == {
        "HQ-DEFAULT-PC-01",
        "HQ-DEFAULT-PC-02",
        "BR1-DEFAULT-PC-01",
        "BR1-DEFAULT-PC-02",
        "BR2-DEFAULT-PC-01",
        "BR2-DEFAULT-PC-02",
    }
    assert all(item.required for item in gateways)
    by_client = {item.client_device_id: item.id for item in gateways}
    fetches = [
        item
        for item in routed.verification_expectations
        if item.kind is ServiceVerificationKind.HTTP_FETCH
    ]
    assert fetches
    for fetch in fetches:
        assert fetch.depends_on == [by_client[fetch.client_device_id]]
    # The same gateway read gates the client's DNS, so a failed read can
    # never let DNS cross the path before the skipped cold request.
    resolutions = [
        item
        for item in routed.verification_expectations
        if item.kind is ServiceVerificationKind.DNS_RESOLUTION
    ]
    assert resolutions
    for item in resolutions:
        assert by_client[item.client_device_id] in item.depends_on


def test_the_product_asks_every_http_by_ip_before_any_dns(tmp_path: Path):
    """Through the use case: the S1 DNS+HTTP intent now runs HTTP by IP first."""
    manifest, inventory = deployment_manifest()
    services = RecordingServiceRuntime(targets=inventory)
    result = apply_enterprise_services(
        json.dumps(intent_payload()),
        deployment_id=DEPLOYMENT_ID,
        packet_tracer_version=BACKEND_VERSION,
        runtimes=ServiceStageRuntimes(
            configuration=RecordingConfigurationRuntime(targets=inventory),
            services=services,
        ),
        manifest_store=ManifestStore(manifest=manifest),
        record_store=ServiceRunRecordStore(tmp_path),
        import_preflight=IsolationPreflight(),
        environment_fingerprint=FINGERPRINT,
        transport_selection=TransportSelection(channel="http"),
        endpoint_observer=EndpointObserver(address=""),
        source_tree=SourceTreeIdentity(sha="test-source", dirty=True),
    )

    asked = [item.split("/")[1] for item in services.verified]
    assert "verify-http-ip" in asked and "verify-dns" in asked, result.blocked_reason
    last_http = max(i for i, kind in enumerate(asked) if kind == "verify-http-ip")
    first_dns = min(
        i
        for i, kind in enumerate(asked)
        if kind in {"verify-dns", "verify-dns-negative", "verify-http-name"}
    )
    assert last_http < first_dns
