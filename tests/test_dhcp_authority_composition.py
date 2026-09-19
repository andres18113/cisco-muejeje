"""S3-01/S3-02: canonical DHCP authority reaches E5 and E6 once."""

from __future__ import annotations

import copy
import json

from service_entry_fixture import (
    BACKEND_VERSION,
    deployment_manifest,
    intent_payload,
)

from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureDhcpPool,
    ConfigurationIssueCode,
    ConfigurationPolicy,
    ConfigurationPhase,
    SetEndpointDhcp,
)
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AcquireDhcpLease,
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServiceType,
)
from packet_tracer_mcp.application.use_cases.compile_services import (
    compile_enterprise_services,
)


SERVER_ID = "endpoint/hq/default/server/001"
CLIENT_IDS = [
    "endpoint/hq/default/user_pc/001",
    "endpoint/hq/default/user_pc/002",
]
SEGMENT_ID = "hq-data"


def _dhcp_payload(*, duplicate: bool = False, server_segment: str = "data"):
    payload = copy.deepcopy(intent_payload())
    endpoints = payload["sites"][0]["endpoints"]
    endpoints[0]["addressing_preference"] = "dhcp"
    endpoints[1]["segment_role"] = server_segment
    service = {
        "name": "lab-dhcp",
        "service_type": "dhcp",
        "host_device_id": SERVER_ID,
        "segment_id": SEGMENT_ID,
        "client_device_ids": CLIENT_IDS,
        "dhcp_pool": {},
    }
    payload["sites"][0]["services"].append(service)
    if duplicate:
        payload["sites"][0]["services"].append(
            {**service, "name": "other-dhcp"}
        )
    return payload


def _compose(payload, *, policy: ConfigurationPolicy | None = None):
    intent = EnterpriseIntent.model_validate_json(json.dumps(payload))
    manifest, _inventory = deployment_manifest(payload)
    return compose_enterprise_reference(
        intent,
        packet_tracer_version=BACKEND_VERSION,
        deployment_manifest=manifest,
        configuration_policy=policy,
        services=True,
    )


def test_real_composition_delegates_one_segment_and_keeps_its_dhcp_clients():
    """The intent, not a hand-built policy, drives the E5/E6 authority split."""
    composition = _compose(_dhcp_payload())

    assert composition.issues == []
    assert composition.configuration_policy is not None
    assert composition.configuration_policy.delegated_dhcp_segment_ids == [
        SEGMENT_ID
    ]
    assert not any(
        isinstance(action, ConfigureDhcpPool)
        and action.segment_id == SEGMENT_ID
        for action in composition.configuration.actions
    )
    clients = [
        action
        for action in composition.configuration.actions
        if isinstance(action, SetEndpointDhcp)
    ]
    assert [action.device_id for action in clients] == CLIENT_IDS
    assert all(len(action.depends_on) == 1 for action in clients)
    assert all(
        expectation.kind.value == "endpoint_dhcp_mode"
        for expectation in composition.configuration.verification_expectations
        if expectation.action_id in {action.id for action in clients}
    )

    assert composition.services is not None
    dhcp_service = next(
        item
        for item in composition.services.services
        if item.service_type is ServiceType.DHCP
    )
    assert dhcp_service.segment_id == SEGMENT_ID
    assert dhcp_service.host_device_id == SERVER_ID
    assert dhcp_service.client_device_ids == CLIENT_IDS
    enable = next(
        item
        for item in composition.services.actions
        if isinstance(item, EnableServerDhcp)
    )
    pool = next(
        item
        for item in composition.services.actions
        if isinstance(item, ConfigureServerDhcpPool)
    )
    assert enable.interface == "FastEthernet0"
    assert pool.interface == "FastEthernet0"
    assert pool.network == "198.18.160.0"
    assert pool.netmask == "255.255.255.248"
    assert pool.gateway == "198.18.160.1"
    assert pool.dns_server == "198.18.160.2"
    assert pool.lease_start == "198.18.160.3"
    assert pool.lease_end == "198.18.160.4"
    assert pool.max_users == 2
    assert [item.model_dump() for item in pool.excluded_ranges] == [
        {"start": "198.18.160.1", "end": "198.18.160.2"}
    ]


def test_two_server_authorities_for_one_segment_are_a_typed_refusal():
    composition = _compose(_dhcp_payload(duplicate=True))

    assert composition.services is None
    assert [item.code for item in composition.service_policy_issues] == [
        ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT
    ]


def test_an_explicit_ios_authority_conflicts_with_service_delegation():
    policy = ConfigurationPolicy(dhcp_server_device_ids={"hq": "router/hq/1"})

    composition = _compose(_dhcp_payload(), policy=policy)

    assert composition.services is None
    assert [item.code for item in composition.service_policy_issues] == [
        ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT
    ]


def test_a_server_on_another_segment_is_not_silently_used_as_a_relay():
    composition = _compose(_dhcp_payload(server_segment="servers"))

    assert composition.services is None
    assert [item.code for item in composition.service_policy_issues] == [
        ConfigurationIssueCode.DHCP_RELAY_REQUIRED
    ]


def test_a_wrong_explicit_server_interface_is_refused():
    payload = _dhcp_payload()
    payload["sites"][0]["services"][-1]["dhcp_pool"]["interface"] = (
        "FastEthernet9"
    )

    composition = _compose(payload)

    assert composition.services is None
    assert any("FastEthernet9" in issue for issue in composition.issues)


def test_configure_only_keeps_acquisition_rows_but_compiles_no_effect():
    payload = _dhcp_payload()
    payload["sites"][0]["services"][-1]["verification_mode"] = "configure_only"

    composition = _compose(payload)

    assert composition.services is not None, composition.issues
    assert not any(
        isinstance(item, AcquireDhcpLease) for item in composition.services.actions
    )
    lease_rows = [
        item
        for item in composition.services.verification_expectations
        if item.kind.value == "dhcp_lease"
    ]
    assert len(lease_rows) == 2
    assert all(item.expected["configure_only"] is True for item in lease_rows)


def test_invalid_offsets_capacity_and_pool_name_are_domain_issues():
    cases = [
        {"start_offset": -1},
        {"start_offset": 99},
        {"max_users": 99},
        {"pool_name": "bad pool name"},
    ]

    for pool_values in cases:
        payload = _dhcp_payload()
        payload["sites"][0]["services"][-1]["dhcp_pool"] = pool_values
        composition = _compose(payload)

        assert composition.services is None
        assert any("DHCP" in message for message in composition.issues)


def test_e6_rejects_a_delegated_segment_that_still_contains_an_ios_pool():
    composition = _compose(_dhcp_payload())
    configuration = composition.configuration.model_copy(deep=True)
    configuration.actions.append(
        ConfigureDhcpPool(
            id="cfg/dhcp/conflict",
            phase=ConfigurationPhase.SERVICES,
            device_id="router-1",
            device_name="R1",
            site_id="hq",
            pool_name="IOS_CONFLICT",
            segment_id=SEGMENT_ID,
            network="198.18.160.0",
            prefix=29,
            netmask="255.255.255.248",
            gateway="198.18.160.1",
            lease_start="198.18.160.3",
            lease_end="198.18.160.4",
        )
    )

    result = compile_enterprise_services(
        composition.enterprise,
        composition.topology,
        configuration,
    )

    assert result.plan is None
    assert ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT in {
        item.code for item in result.issues
    }


def test_existing_static_dns_http_composition_keeps_its_ids_and_hashes():
    """The additive S3 contract does not perturb callers with no delegation."""
    composition = _compose(intent_payload())

    assert composition.configuration_policy.delegated_dhcp_segment_ids == []
    assert composition.configuration.semantic_hash == (
        "4a14fe52bba9d4e53dc1bfa8ba329055556eea6896262a518c442aea2d72e921"
    )
    assert composition.services.semantic_hash == (
        "844b7665041c93a0c57cd67f7d97551941e68d1ad76da6b2123e0bc55cfb66e8"
    )
