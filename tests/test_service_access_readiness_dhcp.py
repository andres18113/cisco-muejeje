"""DF8 and DF15: DHCP acquisition readiness, derived like HTTP's and no wider.

The derivation is the product's own. Only the request kinds differ: a DHCP
acquisition is gated through the lease expectation that follows it, which
names the server as its host and the PC as its client, so the group holds the
client's access port and the server's. HTTP callers keep their default.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import q3_product_contract
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.services.service_access_readiness import (
    DHCP_ACQUISITION_KINDS,
    HTTP_REQUEST_KINDS,
    derive_access_readiness_plan,
)
from packet_tracer_mcp.domain.enterprise.services.service_diagnostic_profiles import (
    q3_fastloop_fixture_placements,
)

RUN_ID = "2026-09-24T00-00-00Z-abcdef12"


def test_the_http_default_derives_nothing_for_dhcp():
    """Existing callers keep exactly the HTTP family."""
    contract = q3_product_contract("9.0.1.0858", RUN_ID)
    plan = derive_access_readiness_plan(
        configuration_actions=contract.configuration_plan.actions,
        verification_expectations=contract.service_plan.verification_expectations,
    )
    assert plan.requirements == () and plan.unplaced == ()
    assert ServiceVerificationKind.DHCP_LEASE not in HTTP_REQUEST_KINDS
    assert DHCP_ACQUISITION_KINDS == frozenset({ServiceVerificationKind.DHCP_LEASE})


def test_the_compiled_q3_plan_derives_one_group_bound_to_the_fixture_vlan():
    """Server and both clients on one switch; only the VLAN is rebound, and said so."""
    contract = q3_product_contract("9.0.1.0858", RUN_ID)
    actions, rewrites = q3_fastloop_fixture_placements(
        contract.configuration_plan, vlan_id=1
    )
    plan = derive_access_readiness_plan(
        configuration_actions=actions,
        verification_expectations=contract.service_plan.verification_expectations,
        request_kinds=DHCP_ACQUISITION_KINDS,
    )

    (group,) = plan.requirements
    assert (group.switch_device_name, group.vlan_id) == ("__MCP_E6Q_SW", 1)
    assert group.interfaces == ("FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3")
    assert [item.kind for item in group.dependents] == [
        ServiceVerificationKind.DHCP_LEASE,
        ServiceVerificationKind.DHCP_LEASE,
    ]
    assert [item.as_text() for item in rewrites] == [
        f"access_vlan_rebound:__MCP_E6Q_SW:FastEthernet0/{index}:10->1:runner_owned_fixture"
        for index in (1, 2, 3)
    ]


@pytest.mark.parametrize("clients", [2, 20, 200, 1000])
def test_one_group_serves_every_client_of_a_switch_and_vlan(clients):
    """The observation cost follows the topology, not the client count."""
    actions = [
        SimpleNamespace(
            action_type="configure_access_port",
            interface=f"FastEthernet0/{index + 1}",
            data_vlan_id=1,
            device_id="switch",
            device_name="SW",
            endpoint_ids=[f"pc-{index}" if index else "server"],
        )
        for index in range(clients + 1)
    ]
    expectations = [
        SimpleNamespace(
            id=f"lease-{index}",
            service_id="dhcp",
            kind=ServiceVerificationKind.DHCP_LEASE,
            host_device_id="server",
            client_device_id=f"pc-{index}",
        )
        for index in range(1, clients + 1)
    ]
    plan = derive_access_readiness_plan(
        configuration_actions=actions,
        verification_expectations=expectations,
        request_kinds=DHCP_ACQUISITION_KINDS,
    )
    (group,) = plan.requirements
    assert len(group.dependents) == clients
    assert len(group.interfaces) == clients + 1
    assert plan.group_count == 1
