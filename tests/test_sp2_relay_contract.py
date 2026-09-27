"""SP-2 remote relay discriminator composes an exact private fixture."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from packet_tracer_mcp.adapters.cli import service_qualification
from packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
    capability_catalog_for,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.service_plan import AcquireDhcpLease

BUILD = "9.0.1.0858"


def _contract():
    compose = getattr(service_qualification, "sp2_remote_relay_contract", None)
    assert callable(compose)
    return compose(BUILD, "sp2-e3-offline-contract")


def test_remote_relay_contract_binds_the_composed_fixture_and_pool():
    """The private contract uses real E4/E5/E6 plans and one selected PC."""
    contract = _contract()
    assert len(contract.topology.devices) == 6
    assert len(contract.topology.links) == 5
    assert len(contract.configuration_plan.actions) == 19
    assert contract.manifest.physical_topology_hash == (
        contract.topology.physical_topology_hash
    )
    assert {item.name for item in contract.topology.devices} == {
        "HQ-DEFAULT-DNS-01",
        "HQ-DEFAULT-ACCESS-SW-01",
        "HQ-EDGE-RTR-01",
        "BR1-DEFAULT-PC-01",
        "BR1-DEFAULT-ACCESS-SW-01",
        "BR1-EDGE-RTR-01",
    }
    intent = json.loads(contract.intent_json)
    [dhcp] = intent["sites"][1]["services"]
    assert dhcp["verification_mode"] == "configure_only"
    assert dhcp["dhcp_pool"]["pool_name"] == "BR1_DATA"
    assert not any(
        isinstance(item, AcquireDhcpLease) for item in contract.service_plan.actions
    )
    [pool] = [
        item
        for item in contract.service_plan.actions
        if item.action_type.value == "configure_server_dhcp_pool"
    ]
    assert (pool.lease_start, pool.lease_end, pool.gateway, pool.dns_server) == (
        "10.72.32.2",
        "10.72.32.3",
        "10.72.32.1",
        "10.72.0.2",
    )
    [relay] = [
        item
        for item in contract.configuration_plan.actions
        if item.action_type.value == "configure_dhcp_relay"
    ]
    assert (relay.device_name, relay.interface, relay.server_address) == (
        "BR1-EDGE-RTR-01",
        "GigabitEthernet0/1",
        "10.72.0.2",
    )
    routes = {
        (item.device_name, item.network, item.next_hop)
        for item in contract.configuration_plan.actions
        if item.action_type.value == "configure_static_route"
    }
    assert routes == {
        ("BR1-EDGE-RTR-01", "10.72.0.0", "10.72.64.2"),
        ("HQ-EDGE-RTR-01", "10.72.32.0", "10.72.64.1"),
    }


def test_relay_candidate_does_not_promote_the_default_catalog():
    """The experiment's device override never changes public support."""
    contract = _contract()
    assert contract.device_capabilities["1941"].supports_dhcp_relay is (
        CapabilityStatus.SUPPORTED
    )
    assert contract.device_capability_catalog is not None
    assert contract.device_capability_evidence == (
        {
            "build": BUILD,
            "model": "1941",
            "capability": "supports_dhcp_relay",
            "status": "supported",
            "source": "static_override",
            "source_detail": "candidate:SERVER-PT-SP2-GENERALIZED-DHCP-RELAY-01",
            "confidence": "candidate",
            "verified": False,
        },
    )
    assert (
        capability_catalog_for(BUILD)
        .capabilities_for("1941", BUILD)
        .supports_dhcp_relay
        is CapabilityStatus.UNKNOWN
    )


def test_relay_contract_refuses_an_unmeasured_build():
    """A private candidate is bound to the exact initial PT build."""
    compose = getattr(service_qualification, "sp2_remote_relay_contract", None)
    assert callable(compose)
    with pytest.raises(ValueError, match="exact build"):
        compose("9.0.1.other", "sp2-e3-offline-contract")


def test_relay_contract_refuses_a_changed_default_relay_record(monkeypatch):
    """Candidate attribution is invalid if the default catalog has changed."""
    catalog = SimpleNamespace(
        capabilities_for=lambda _model, _build: SimpleNamespace(
            supports_dhcp_relay=CapabilityStatus.SUPPORTED
        )
    )
    monkeypatch.setattr(
        service_qualification, "capability_catalog_for", lambda _: catalog
    )

    with pytest.raises(ValueError, match="default catalog"):
        service_qualification.sp2_remote_relay_contract(BUILD, "sp2-e3-offline")


@pytest.mark.parametrize(
    "change", ["model", "port", "interface", "client_mode", "helper", "route", "pool"]
)
def test_relay_contract_rejects_a_changed_fixture_or_policy(change):
    """The reviewed topology and effects are checked beyond their hash chain."""
    contract = _contract()
    validate = getattr(
        service_qualification, "_validate_sp2_remote_relay_contract", None
    )
    assert callable(validate)
    if change in {"model", "port"}:
        topology = contract.topology.model_copy(deep=True)
        if change == "model":
            router = next(
                item for item in topology.devices if item.name == "HQ-EDGE-RTR-01"
            )
            router.model = "2911"
        else:
            link = next(
                item for item in topology.links if item.device_b == "BR1-DEFAULT-PC-01"
            )
            link.port_a = "FastEthernet1/2"
        changed = replace(contract, topology=topology)
    elif change in {"interface", "client_mode", "helper", "route"}:
        configuration = contract.configuration_plan.model_copy(deep=True)
        kind = {
            "interface": "configure_routed_interface",
            "client_mode": "set_endpoint_dhcp",
            "helper": "configure_dhcp_relay",
            "route": "configure_static_route",
        }[change]
        action = next(
            item for item in configuration.actions if item.action_type.value == kind
        )
        if change == "interface":
            action.ipv4 = "10.72.32.3"
        elif change == "client_mode":
            action.interface = "FastEthernet1"
        elif change == "helper":
            action.server_address = "10.72.0.3"
        else:
            action.next_hop = "10.72.64.3"
        changed = replace(contract, configuration_plan=configuration)
    else:
        services = contract.service_plan.model_copy(deep=True)
        pool = next(
            item
            for item in services.actions
            if item.action_type.value == "configure_server_dhcp_pool"
        )
        pool.pool_name = "OTHER_POOL"
        changed = replace(contract, service_plan=services)

    with pytest.raises(ValueError, match="SP-2 relay contract"):
        validate(changed)


@pytest.mark.parametrize(
    "change", ["effective_pool", "duplicate_device", "duplicate_link"]
)
def test_relay_contract_refuses_pool_strategy_and_duplicate_fixture_rows(change):
    """Physical selection and fixture cardinality are exact stage inputs."""
    contract = _contract()
    validate = getattr(
        service_qualification, "_validate_sp2_remote_relay_contract", None
    )
    assert callable(validate)
    if change == "effective_pool":
        services = contract.service_plan.model_copy(deep=True)
        pool = next(
            item
            for item in services.actions
            if item.action_type.value == "configure_server_dhcp_pool"
        )
        pool.effective_pool_name = "serverPool"
        changed = replace(contract, service_plan=services)
    else:
        topology = contract.topology.model_copy(deep=True)
        if change == "duplicate_device":
            topology.devices.append(topology.devices[0].model_copy(deep=True))
        else:
            topology.links.append(topology.links[0].model_copy(deep=True))
        changed = replace(contract, topology=topology)

    with pytest.raises(ValueError, match="SP-2 relay contract"):
        validate(changed)
