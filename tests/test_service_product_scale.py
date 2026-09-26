"""Deterministic offline scale controls for Server-PT result assembly.

These are reporting-shape measurements, not physical topology qualification.
They hold the indexed implementation to one pass over expectations, one pass
over service membership, and one lookup per emitted check at the admitted
2/20/200/1000-client sizes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import (
    _native_candidate_capabilities,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    MAX_CLIENT_CHECK_ROWS,
    MAX_REPORTING_CLIENTS,
    ClientRowAssemblyMetrics,
    _client_rows,
    _reporting_budget_exceeded,
)
from packet_tracer_mcp.application.use_cases.apply_services import ServiceApplicator
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import ServiceRunStatus
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceDefinition,
    ServiceEvidenceKind,
    ServicePlan,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
    ServiceApplicationResult,
    ServiceVerificationResult,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
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


@pytest.mark.parametrize("client_count", [2, 20, 200, MAX_REPORTING_CLIENTS])
def test_group_assembly_evaluation_and_persistence_scale_with_fake_backend(
    tmp_path, client_count
):
    """Exercise the actual E6 group derivation and durable product rows offline."""
    clients, service, plan, _unused = _dhcp_reporting_fixture(client_count)
    plan.verification_expectations = [
        item.model_copy(
            update={
                "action_id": "action/dhcp",
                "expected": {
                    "state_only": True,
                    "interface": "FastEthernet0",
                    "effective_pool_name": "serverPool",
                },
            }
        )
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    ]

    class FakeBackend:
        calls = 0
        group_json = None

        def verify(self, expectation):
            self.calls += 1
            group = expectation.expected["native_selected_clients_json"]
            if self.group_json is None:
                self.group_json = group
                selected = json.loads(group)
                assert len(selected) == client_count
                assert (
                    len({item["expectation_id"] for item in selected}) == client_count
                )
            else:
                assert group is self.group_json
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.VERIFIED,
                evidence_kind=expectation.evidence_kind,
                fresh_evidence=True,
                observation=ObservationFact.OBSERVED,
            )

    backend = FakeBackend()
    applicator = ServiceApplicator(backend)
    verify_started = perf_counter()
    verified, limitations = applicator._verify(
        plan,
        {
            "action/dhcp": ActionApplicationResult(
                action_id="action/dhcp", status=ActionExecutionStatus.VERIFIED
            )
        },
        _native_candidate_capabilities("9.0.1.0858"),
        {"server-1": "SERVER-1", **{item: item.upper() for item in clients}},
        {},
    )
    verify_ms = round((perf_counter() - verify_started) * 1000, 3)
    assert limitations == []
    assert len(verified) == backend.calls == client_count
    result = ServiceApplicationResult(
        service_plan_id=plan.id,
        service_semantic_hash="offline-scale",
        source_topology_hash=plan.source_topology_hash,
        source_configuration_hash=plan.source_configuration_hash,
        status=ConfigurationApplicationStatus.VERIFIED,
        verification_results=verified,
    )
    metrics = ClientRowAssemblyMetrics()
    rows = _client_rows(
        plan,
        result,
        [service],
        {item: item.upper() for item in clients},
        {item: "PC-PT" for item in clients},
        metrics=metrics,
    )
    record = ServiceRunRecord(
        run_id=f"offline-scale-{client_count}",
        created_at=datetime.now(UTC),
        deployment_id="offline-scale",
        status=ServiceRunStatus.VERIFIED,
        service_result=result,
        clients=rows,
        selected_clients=clients,
    )
    store = ServiceRunRecordStore(tmp_path)
    persist_started = perf_counter()
    store.complete(record)
    loaded = store.load("offline-scale", record.run_id)
    persist_ms = round((perf_counter() - persist_started) * 1000, 3)
    assert len(loaded.clients) == client_count
    assert all(len(row.results[service.id].checks) == 1 for row in loaded.clients)
    assert metrics.expectations_indexed == client_count
    assert metrics.check_lookups == client_count
    print(
        json.dumps(
            {
                "clients": client_count,
                "group_assemblies": 1,
                "verification_calls": backend.calls,
                "check_lookups": metrics.check_lookups,
                "group_json_bytes": len(backend.group_json.encode("utf-8")),
                "record_bytes": store.path_for("offline-scale", record.run_id)
                .stat()
                .st_size,
                "verify_ms": verify_ms,
                "persist_round_trip_ms": persist_ms,
            },
            sort_keys=True,
        )
    )
