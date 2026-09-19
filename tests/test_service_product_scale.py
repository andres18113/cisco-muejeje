"""Deterministic offline scale controls for Server-PT result assembly.

These are reporting-shape measurements, not physical topology qualification.
They hold the indexed implementation to one pass over expectations, one pass
over service membership, and one lookup per emitted check at the admitted
2/20/200/1000-client sizes.
"""

from __future__ import annotations

import pytest

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    MAX_CLIENT_CHECK_ROWS,
    MAX_REPORTING_CLIENTS,
    ClientRowAssemblyMetrics,
    _client_rows,
    _reporting_budget_exceeded,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceDefinition,
    ServiceEvidenceKind,
    ServicePlan,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    ServiceApplicationResult,
    ServiceVerificationResult,
)

_CHECKS_PER_CLIENT = 5


def _reporting_fixture(client_count: int):
    clients = [f"client-{index:04d}" for index in range(client_count)]
    service = ServiceDefinition(
        id="service/hq/dns",
        name="dns",
        service_type=ServiceType.DNS,
        site_id="hq",
        host_device_id="server-1",
        host_device_name="SERVER-1",
        host_model="Server-PT",
        address="198.18.0.2",
        segment_id="hq-data",
        client_device_ids=clients,
        protocol="udp",
        ports=[53],
    )
    expectations = [
        ServiceVerificationExpectation(
            id=f"expectation/{client_id}/{check_index}",
            service_id=service.id,
            action_id="action/dns",
            kind=ServiceVerificationKind.DNS_RESOLUTION,
            evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
            host_device_id="server-1",
            host_device_name="SERVER-1",
            client_device_id=client_id,
            client_device_name=client_id.upper(),
            client_model="PC-PT",
        )
        for client_id in clients
        for check_index in range(_CHECKS_PER_CLIENT)
    ]
    plan = ServicePlan(
        id="service-plan",
        source_topology_id="topology",
        source_topology_hash="topology-hash",
        source_configuration_id="configuration",
        source_configuration_hash="configuration-hash",
        services=[service],
        verification_expectations=expectations,
    )
    result = ServiceApplicationResult(
        service_plan_id=plan.id,
        service_semantic_hash="service-hash",
        source_topology_hash=plan.source_topology_hash,
        source_configuration_hash=plan.source_configuration_hash,
        status=ConfigurationApplicationStatus.VERIFIED,
        verification_results=[
            ServiceVerificationResult(
                expectation_id=item.id,
                service_id=service.id,
                status=ActionExecutionStatus.VERIFIED,
                evidence_kind=item.evidence_kind,
                fresh_evidence=True,
                observation=ObservationFact.OBSERVED,
            )
            for item in expectations
        ],
    )
    return clients, service, plan, result


@pytest.mark.parametrize("client_count", [2, 20, 200, MAX_REPORTING_CLIENTS])
def test_reporting_assembly_is_linear_and_complete(client_count: int):
    """Every admitted size performs exactly one operation per input row."""
    clients, service, plan, result = _reporting_fixture(client_count)
    metrics = ClientRowAssemblyMetrics()

    rows = _client_rows(
        plan,
        result,
        [service],
        {client_id: client_id.upper() for client_id in clients},
        {client_id: "PC-PT" for client_id in clients},
        metrics=metrics,
    )

    assert len(rows) == client_count
    assert all(set(item.results) == {service.id} for item in rows)
    assert all(
        len(item.results[service.id].checks) == _CHECKS_PER_CLIENT for item in rows
    )
    assert metrics.expectations_indexed == client_count * _CHECKS_PER_CLIENT
    assert metrics.memberships_indexed == client_count
    assert metrics.pairs_assembled == client_count
    assert metrics.check_lookups == client_count * _CHECKS_PER_CLIENT


def test_reporting_budget_is_the_measured_1000_by_5_boundary():
    """The offline response budget is explicit and fail-closed above its edge."""
    _clients, _service, admitted, _result = _reporting_fixture(MAX_REPORTING_CLIENTS)
    _clients, _service, too_many_clients, _result = _reporting_fixture(
        MAX_REPORTING_CLIENTS + 1
    )
    assert MAX_CLIENT_CHECK_ROWS == MAX_REPORTING_CLIENTS * _CHECKS_PER_CLIENT
    assert not _reporting_budget_exceeded(admitted)
    assert _reporting_budget_exceeded(too_many_clients)


def _dhcp_reporting_fixture(client_count: int):
    """Build the two distinct DHCP claims retained for every selected client."""
    clients = [f"dhcp-client-{index:04d}" for index in range(client_count)]
    service = ServiceDefinition(
        id="service/hq/dhcp",
        name="dhcp",
        service_type=ServiceType.DHCP,
        site_id="hq",
        host_device_id="server-1",
        host_device_name="SERVER-1",
        host_model="Server-PT",
        address="198.18.0.2",
        segment_id="hq-data",
        client_device_ids=clients,
        protocol="udp",
        ports=[67, 68],
    )
    expectations = [
        ServiceVerificationExpectation(
            id=f"expectation/{kind.value}/{client_id}",
            service_id=service.id,
            action_id="action/dhcp",
            kind=kind,
            evidence_kind=(
                ServiceEvidenceKind.BEHAVIORAL
                if kind is ServiceVerificationKind.DHCP_LEASE
                else ServiceEvidenceKind.DIRECT_STATE
            ),
            host_device_id="server-1",
            host_device_name="SERVER-1",
            host_model="Server-PT",
            client_device_id=client_id,
            client_device_name=client_id.upper(),
            client_model="PC-PT",
        )
        for client_id in clients
        for kind in (
            ServiceVerificationKind.DHCP_LEASE,
            ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED,
        )
    ]
    plan = ServicePlan(
        id="dhcp-plan",
        source_topology_id="topology",
        source_topology_hash="topology-hash",
        source_configuration_id="configuration",
        source_configuration_hash="configuration-hash",
        services=[service],
        verification_expectations=expectations,
    )
    result = ServiceApplicationResult(
        service_plan_id=plan.id,
        service_semantic_hash="service-hash",
        source_topology_hash=plan.source_topology_hash,
        source_configuration_hash=plan.source_configuration_hash,
        status=ConfigurationApplicationStatus.PARTIAL,
        verification_results=[
            ServiceVerificationResult(
                expectation_id=item.id,
                service_id=service.id,
                status=ActionExecutionStatus.UNKNOWN,
                evidence_kind=item.evidence_kind,
                observation=ObservationFact.INCONCLUSIVE,
                cause="offline_scale_fixture",
            )
            for item in expectations
        ],
    )
    return clients, service, plan, result


@pytest.mark.parametrize("client_count", [2, 20, 200, MAX_REPORTING_CLIENTS])
def test_dhcp_reporting_retains_both_claims_at_every_admitted_scale(client_count):
    """Keep acquisition and attribution rows complete through 1000 clients."""
    clients, service, plan, result = _dhcp_reporting_fixture(client_count)
    metrics = ClientRowAssemblyMetrics()

    rows = _client_rows(
        plan,
        result,
        [service],
        {client_id: client_id.upper() for client_id in clients},
        {client_id: "PC-PT" for client_id in clients},
        metrics=metrics,
    )

    assert not _reporting_budget_exceeded(plan)
    assert len(rows) == client_count
    assert all(len(item.results[service.id].checks) == 2 for item in rows)
    assert metrics.expectations_indexed == client_count * 2
    assert metrics.check_lookups == client_count * 2


def test_combined_seven_row_workload_is_explicitly_refused_at_1000_clients():
    """Do not raise the five-row budget or silently drop DHCP rows."""
    clients, dns, baseline, _result = _reporting_fixture(MAX_REPORTING_CLIENTS)
    _clients, dhcp, dhcp_plan, _dhcp_result = _dhcp_reporting_fixture(
        MAX_REPORTING_CLIENTS
    )
    combined = baseline.model_copy(
        update={
            "services": [dns, dhcp],
            "verification_expectations": [
                *baseline.verification_expectations,
                *dhcp_plan.verification_expectations,
            ],
        }
    )

    assert len(clients) == MAX_REPORTING_CLIENTS
    assert len(combined.verification_expectations) == MAX_REPORTING_CLIENTS * 7
    assert _reporting_budget_exceeded(combined)
