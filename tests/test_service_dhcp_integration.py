"""S3 product integration through composition, E5/E6 and the run store."""

from __future__ import annotations

import copy

from service_entry_fixture import RecordingConfigurationRuntime, intent_payload
from test_apply_enterprise_services import _harness
from test_service_dhcp_scheduler import (
    CLIENT_IDS,
    SERVER_ID,
    _candidate_catalog,
)

from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration import VerificationKind
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConvergenceReport,
    FieldVerificationStatus,
    VerificationResult,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceStage,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceActionType,
    ServiceType,
    ServiceVerificationKind,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)


def _payload(*, required: bool = True):
    payload = copy.deepcopy(intent_payload())
    payload["sites"][0]["endpoints"][0]["addressing_preference"] = "dhcp"
    payload["sites"][0]["endpoints"][1]["segment_role"] = "data"
    payload["sites"][0]["services"].append(
        {
            "name": "lab-dhcp",
            "service_type": "dhcp",
            "required": required,
            "host_device_id": SERVER_ID,
            "segment_id": "hq-data",
            "client_device_ids": CLIENT_IDS,
            "dhcp_pool": {},
        }
    )
    return payload


def _optional_with_independent_static_service():
    payload = _payload(required=False)
    payload["sites"][0]["services"] = [
        payload["sites"][0]["services"][-1],
        {
            "name": "independent-pop3",
            "service_type": "pop3",
            "host_device_id": SERVER_ID,
        },
    ]
    return payload


def _pop3_only_candidate(version):
    records = packet_tracer_service_capabilities(version)
    key = f"Server-PT:{ServiceType.POP3.value}"
    records[key] = records[key].model_copy(
        update={
            "application_support": CapabilityStatus.SUPPORTED,
            "direct_readback_support": CapabilityStatus.SUPPORTED,
            "action_application_support": {
                ServiceActionType.ENABLE_POP3.value: CapabilityStatus.SUPPORTED
            },
        }
    )
    return records


class _ModeConfigurationRuntime(RecordingConfigurationRuntime):
    """External E5 seam that returns the exact candidate mode observation."""

    def verify(self, expectations):
        rows = super().verify(expectations)
        return [
            VerificationResult(
                expectation_id=item.id,
                action_id=item.action_id,
                status=ActionExecutionStatus.VERIFIED,
                evidence_method="structured_endpoint_dhcp_mode",
                fresh_evidence=True,
                fields={"dhcp_mode": FieldVerificationStatus.VERIFIED},
                convergence=ConvergenceReport(
                    attempts=1,
                    final_status=ActionExecutionStatus.VERIFIED,
                    details={
                        "kind": "endpoint_dhcp_mode",
                        "device_name": item.device_name,
                        "interface": item.expected["interface"],
                        "last_observation": {
                            "device_found": True,
                            "port_found": True,
                            "mode_channel": True,
                            "interface": item.expected["interface"],
                            "dhcp_mode": True,
                            "fresh_evidence": True,
                            "failure_reason": "",
                        },
                    },
                ),
            )
            if item.kind is VerificationKind.ENDPOINT_DHCP_MODE
            else row
            for item, row in zip(expectations, rows, strict=True)
        ]


def _candidate_harness(tmp_path):
    harness = _harness(tmp_path, _payload())
    harness.configuration = _ModeConfigurationRuntime(
        targets=harness.configuration.targets
    )
    return harness


def test_default_catalog_refuses_required_dhcp_before_the_first_e5_effect(tmp_path):
    """Keep documented but unqualified DHCP unavailable in the product."""
    harness = _harness(tmp_path, _payload())

    result = harness.run()

    assert result.refusal_code is ServiceEntryRefusal.SERVICE_INELIGIBLE
    assert harness.mutating_calls == []


def test_candidate_path_persists_separate_mode_configuration_and_lease_rows(tmp_path):
    """Exercise the real product path with only external seams synthesized."""
    harness = _candidate_harness(tmp_path)

    result = harness.run(capability_catalog=lambda _version: _candidate_catalog())

    assert result.refusal_code is ServiceEntryRefusal.NONE
    configured = {item.action_type.value for item in harness.configuration.rendered}
    assert "set_endpoint_dhcp" in configured
    service_actions = {
        identifier for batch in harness.services.applied for identifier in batch
    }
    assert any("acquire-dhcp" in identifier for identifier in service_actions)
    kinds = {
        check.kind
        for client in result.clients
        for outcome in client.results.values()
        for check in outcome.checks
    }
    assert ServiceVerificationKind.DHCP_LEASE in kinds
    assert ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED in kinds
    stored = ServiceRunRecordStore(tmp_path).load(result.deployment_id, result.run_id)
    assert stored.service_result is not None
    [authority] = stored.dhcp_authorities
    assert authority.service_id == "service/hq/lab-dhcp"
    assert authority.server_device_id == SERVER_ID
    assert authority.segment_id == "hq-data"
    assert authority.interface == "FastEthernet0"
    assert authority.pool_name == "HQ_DATA"
    assert authority.client_device_ids == CLIENT_IDS
    assert authority.action_ids
    assert authority.expectation_ids
    assert any(
        item.kind is ServiceVerificationKind.DHCP_LEASE
        for item in result.clients[0].results["service/hq/lab-dhcp"].checks
    )


def test_unqualified_mode_reader_refuses_before_e5_even_with_other_dhcp_support(
    tmp_path,
):
    """Require M-DHCP-5 separately from every server/acquisition operation."""
    harness = _candidate_harness(tmp_path)
    records = _candidate_catalog()
    key = "PC-PT:endpoint_dhcp_mode"
    records[key] = records[key].model_copy(update={"support": CapabilityStatus.UNKNOWN})

    result = harness.run(capability_catalog=lambda _version: records)

    assert result.refusal_code is ServiceEntryRefusal.SERVICE_INELIGIBLE
    assert harness.mutating_calls == []


def test_optional_unknown_dhcp_is_excluded_without_reactivating_ios_or_clients(
    tmp_path,
):
    """Exclude optional DHCP while preserving an independent static service."""
    payload = _optional_with_independent_static_service()
    harness = _harness(tmp_path, payload)

    result = harness.run(capability_catalog=_pop3_only_candidate)

    assert result.refusal_code is ServiceEntryRefusal.NONE
    rendered_types = {item.action_type.value for item in harness.configuration.rendered}
    assert "configure_dhcp_pool" not in rendered_types
    assert "set_endpoint_dhcp" not in rendered_types
    assert "set_endpoint_static" in rendered_types
    by_client = {item.client_device_id: item for item in result.clients}
    for client_id in CLIENT_IDS:
        outcome = by_client[client_id].results["service/hq/lab-dhcp"]
        assert outcome.status is ActionExecutionStatus.SKIPPED
        assert outcome.checks


def test_persistence_loss_after_mode_bootstrap_blocks_acquisition(tmp_path):
    """Close the mutation gate before acquisition when the record is lost."""

    class FailAtFoundation(ServiceRunRecordStore):
        def advance(self, record):
            if record.persisted_stage is ServiceStage.FOUNDATIONAL_EVIDENCE:
                raise RunRecordPersistenceError("volume went read-only")
            return super().advance(record)

    harness = _candidate_harness(tmp_path)
    harness.record_store = FailAtFoundation(tmp_path)

    result = harness.run(capability_catalog=lambda _version: _candidate_catalog())

    assert result.refusal_code is ServiceEntryRefusal.EFFECT_HALTED
    assert any(
        item.action_type.value == "set_endpoint_dhcp"
        for item in harness.configuration.rendered
    )
    assert not any(
        "acquire-dhcp" in identifier
        for batch in harness.services.applied
        for identifier in batch
    )
