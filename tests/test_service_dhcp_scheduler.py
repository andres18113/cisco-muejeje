"""S3-06: lease verification gates actual dependent E6 effects in-flow."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from service_entry_fixture import (
    BACKEND_VERSION,
    FINGERPRINT,
    deployment_manifest,
    intent_payload,
)

from packet_tracer_mcp.application.use_cases.apply_services import ServiceApplicator
from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationRuntimeContext,
    RuntimeActionMutation,
)
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ClientOperationCapability,
    ConfigureEmailClient,
    ServiceActionType,
    ServiceType,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)


SERVER_ID = "endpoint/hq/default/server/001"
CLIENT_IDS = [
    "endpoint/hq/default/user_pc/001",
    "endpoint/hq/default/user_pc/002",
]


def _payload():
    payload = copy.deepcopy(intent_payload())
    payload["sites"][0]["endpoints"][0]["addressing_preference"] = "dhcp"
    payload["sites"][0]["endpoints"][1]["segment_role"] = "data"
    payload["sites"][0]["services"].extend(
        [
            {
                "name": "lab-dhcp",
                "service_type": "dhcp",
                "host_device_id": SERVER_ID,
                "segment_id": "hq-data",
                "client_device_ids": CLIENT_IDS,
                "dhcp_pool": {},
            },
            {
                "name": "lab-mail",
                "service_type": "smtp",
                "domain_name": "lab.example",
                "email_accounts": [
                    {"username": "user1", "secret_ref": "mail.user1"},
                    {"username": "user2", "secret_ref": "mail.user2"},
                ],
                "email_clients": [
                    {"client_device_id": CLIENT_IDS[0], "username": "user1"},
                    {"client_device_id": CLIENT_IDS[1], "username": "user2"},
                ],
                "verification_mode": "configure_only",
            },
        ]
    )
    return payload


def _supported_operation(records, model: str, operation: str) -> None:
    key = f"{model}:{operation}"
    current = records.get(key)
    if isinstance(current, ClientOperationCapability):
        records[key] = current.model_copy(
            update={"support": CapabilityStatus.SUPPORTED}
        )
    else:
        records[key] = ClientOperationCapability(
            key=key,
            model=model,
            operation=operation,
            support=CapabilityStatus.SUPPORTED,
            source="test-bound synthetic prerequisite",
            packet_tracer_version=BACKEND_VERSION,
        )


def _candidate_catalog():
    records = dict(packet_tracer_service_capabilities(BACKEND_VERSION))
    for service_type, actions in (
        (
            ServiceType.DHCP,
            (
                ServiceActionType.ENABLE_SERVER_DHCP,
                ServiceActionType.CONFIGURE_SERVER_DHCP_POOL,
            ),
        ),
        (
            ServiceType.SMTP,
            (
                ServiceActionType.ENABLE_SMTP,
                ServiceActionType.ENSURE_EMAIL_ACCOUNT,
            ),
        ),
    ):
        key = f"Server-PT:{service_type.value}"
        records[key] = records[key].model_copy(
            update={
                "application_support": CapabilityStatus.SUPPORTED,
                "direct_readback_support": CapabilityStatus.SUPPORTED,
                "behavioral_verification_support": CapabilityStatus.SUPPORTED,
                "action_application_support": {
                    item.value: CapabilityStatus.SUPPORTED for item in actions
                },
            }
        )
    for model, operation in (
        ("PC-PT", ServiceActionType.ACQUIRE_DHCP_LEASE.value),
        ("PC-PT", ServiceVerificationKind.ENDPOINT_DHCP_MODE.value),
        ("PC-PT", ServiceVerificationKind.DHCP_LEASE.value),
        ("Server-PT", ServiceVerificationKind.DHCP_SERVER_STATE.value),
        ("Server-PT", ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED.value),
        ("PC-PT", ServiceActionType.CONFIGURE_EMAIL_CLIENT.value),
        ("PC-PT", ServiceVerificationKind.EMAIL_CLIENT_STATE.value),
        ("Server-PT", ServiceVerificationKind.SMTP_DELIVERED.value),
    ):
        _supported_operation(records, model, operation)
    return records


def _composition():
    payload = _payload()
    manifest, inventory = deployment_manifest(payload)
    capabilities = _candidate_catalog()
    composition = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(json.dumps(payload)),
        packet_tracer_version=BACKEND_VERSION,
        deployment_manifest=manifest,
        services=True,
        service_capabilities=capabilities,
    )
    assert composition.services is not None, composition.issues
    return composition, manifest, inventory, capabilities


@dataclass
class _Runtime:
    inventory_rows: list
    lease_status: ActionExecutionStatus
    applied: list[list[str]] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)

    def inventory(self):
        return list(self.inventory_rows)

    def apply_actions(self, actions):
        self.applied.append([item.id for item in actions])
        return [
            RuntimeActionMutation(
                action_id=item.id,
                applied=True,
            )
            for item in actions
        ]

    def verify(self, expectation):
        self.verified.append(expectation.id)
        status = (
            self.lease_status
            if expectation.kind is ServiceVerificationKind.DHCP_LEASE
            else ActionExecutionStatus.VERIFIED
        )
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_kind=expectation.evidence_kind,
            fresh_evidence=status is ActionExecutionStatus.VERIFIED,
            observation=(
                ObservationFact.OBSERVED
                if status is ActionExecutionStatus.VERIFIED
                else ObservationFact.INCONCLUSIVE
            ),
            cause=""
            if status is ActionExecutionStatus.VERIFIED
            else "synthetic_unknown",
        )


def _apply(lease_status: ActionExecutionStatus):
    composition, manifest, inventory, capabilities = _composition()
    runtime = _Runtime(inventory, lease_status)
    result = ServiceApplicator(runtime).apply(
        composition.services,
        actual_source_topology_hash=manifest.physical_topology_hash,
        actual_source_configuration_hash=composition.services.source_configuration_hash,
        foundational_statuses={
            item.configuration_action_id: ActionExecutionStatus.VERIFIED
            for item in composition.services.foundational_requirements
        },
        capabilities=capabilities,
        runtime_context=ConfigurationRuntimeContext(
            backend=FINGERPRINT.backend,
            backend_version=FINGERPRINT.backend_version,
            environment_fingerprint=FINGERPRINT,
        ),
        deployment_manifest=manifest,
    )
    return composition.services, runtime, result


def test_unknown_lease_blocks_the_actual_mail_client_call_but_not_static_work():
    plan, runtime, result = _apply(ActionExecutionStatus.UNKNOWN)
    called = {identifier for batch in runtime.applied for identifier in batch}
    mail_clients = {
        item.id for item in plan.actions if isinstance(item, ConfigureEmailClient)
    }
    independent = {
        item.id
        for item in plan.actions
        if item.service_type in {ServiceType.DNS, ServiceType.HTTP}
    }

    assert called.isdisjoint(mail_clients)
    assert independent <= called
    by_id = {item.action_id: item for item in result.action_results}
    assert all(
        by_id[identifier].status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for identifier in mail_clients
    )
    lease_ids = {
        item.id
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    }
    assert lease_ids <= set(runtime.verified)
    assert all(runtime.verified.count(identifier) == 1 for identifier in lease_ids)
    dependent_checks = {
        item.id
        for item in plan.verification_expectations
        if item.client_device_id in CLIENT_IDS
        and item.kind
        not in {
            ServiceVerificationKind.DHCP_LEASE,
            ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED,
        }
    }
    assert set(runtime.verified).isdisjoint(dependent_checks)
    by_expectation = {item.expectation_id: item for item in result.verification_results}
    assert all(
        by_expectation[identifier].status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for identifier in dependent_checks
    )


def test_synthetic_verified_lease_admits_each_dependent_call_once():
    plan, runtime, _result = _apply(ActionExecutionStatus.VERIFIED)
    called = [identifier for batch in runtime.applied for identifier in batch]
    mail_clients = [
        item.id for item in plan.actions if isinstance(item, ConfigureEmailClient)
    ]

    assert mail_clients
    assert all(called.count(identifier) == 1 for identifier in mail_clients)


def test_action_verification_cycle_makes_no_dependent_call():
    composition, manifest, inventory, capabilities = _composition()
    plan = composition.services.model_copy(deep=True)
    client_action = next(
        item for item in plan.actions if isinstance(item, ConfigureEmailClient)
    )
    own_read = next(
        item
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.EMAIL_CLIENT_STATE
        and item.client_device_id == client_action.host_device_id
    )
    client_action.verification_dependencies = [own_read.id]
    runtime = _Runtime(inventory, ActionExecutionStatus.VERIFIED)

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=manifest.physical_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses={
            item.configuration_action_id: ActionExecutionStatus.VERIFIED
            for item in plan.foundational_requirements
        },
        capabilities=capabilities,
        runtime_context=ConfigurationRuntimeContext(
            backend=FINGERPRINT.backend,
            backend_version=FINGERPRINT.backend_version,
            environment_fingerprint=FINGERPRINT,
        ),
        deployment_manifest=manifest,
    )

    called = {identifier for batch in runtime.applied for identifier in batch}
    by_id = {item.action_id: item for item in result.action_results}
    assert client_action.id not in called
    assert by_id[client_action.id].status is ActionExecutionStatus.DEPENDENCY_BLOCKED
