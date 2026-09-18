"""Fail-closed admission for the bounded S1 static service path."""

from __future__ import annotations

import json

import pytest
from service_entry_fixture import (
    BACKEND_VERSION,
    deployment_manifest,
    intent_payload,
)

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    _e5_closure,
    _unsupported_paths,
)
from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureAccessPort,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.services.service_policy import (
    derive_service_policy,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)


def _composition():
    intent = EnterpriseIntent.model_validate_json(json.dumps(intent_payload()))
    manifest, _inventory = deployment_manifest()
    composition = compose_enterprise_reference(
        intent,
        packet_tracer_version=BACKEND_VERSION,
        deployment_manifest=manifest,
        configuration_policy=derive_service_policy(intent).policy,
        services=True,
        service_capabilities=packet_tracer_service_capabilities(BACKEND_VERSION),
    )
    assert composition.services is not None
    return composition


def test_the_real_fixture_is_one_static_supported_path():
    """The maintained acceptance fixture remains inside the bounded path."""
    composition = _composition()

    assert (
        _unsupported_paths(
            composition.configuration,
            composition.services,
            composition.services.services,
        )
        == []
    )


def test_a_dhcp_foundation_is_explicitly_outside_s1():
    """A typed DHCP foundation is refused even when the rest is coherent."""
    composition = _composition()
    static = next(
        item
        for item in composition.configuration.actions
        if isinstance(item, SetEndpointStaticAddress) and "user_pc" in item.device_id
    )
    values = static.model_dump(exclude={"action_type", "ipv4"})
    dhcp = SetEndpointDhcp(
        **values,
        network="198.18.160.0",
        prefix=29,
    )
    configuration = composition.configuration.model_copy(
        update={
            "actions": [
                dhcp if item.id == static.id else item
                for item in composition.configuration.actions
            ]
        }
    )

    unsupported = _unsupported_paths(
        configuration,
        composition.services,
        composition.services.services,
    )

    assert any(item.endswith(":dhcp") for item in unsupported)


def test_a_multi_switch_path_without_governed_trunks_is_refused():
    """Same segment does not prove an ungoverned inter-switch path."""
    composition = _composition()
    client = next(
        item
        for item in composition.configuration.actions
        if isinstance(item, SetEndpointStaticAddress) and "user_pc" in item.device_id
    )
    access_id = client.depends_on[0]
    configuration = composition.configuration.model_copy(
        update={
            "actions": [
                item.model_copy(
                    update={
                        "device_id": "other-switch",
                        "device_name": "SW-OTHER",
                    }
                )
                if item.id == access_id and isinstance(item, ConfigureAccessPort)
                else item
                for item in composition.configuration.actions
            ]
        }
    )

    unsupported = _unsupported_paths(
        configuration,
        composition.services,
        composition.services.services,
    )

    assert any(item.endswith(":inter_switch") for item in unsupported)


def test_a_missing_selected_dependency_does_not_disappear_from_the_closure():
    """Every selected dependency must remain present in the typed plan."""
    composition = _composition()
    selected = composition.services.services
    seed = next(
        item
        for item in composition.configuration.actions
        if isinstance(item, SetEndpointStaticAddress)
    )
    missing = seed.depends_on[0]
    configuration = composition.configuration.model_copy(
        update={
            "actions": [
                item for item in composition.configuration.actions if item.id != missing
            ]
        }
    )

    with pytest.raises(ValueError, match="dependency"):
        _e5_closure(configuration, composition.services, selected)


def test_a_non_pc_selected_client_is_outside_the_s1_contract():
    """Static addressing alone does not turn another endpoint model into PC-PT."""
    composition = _composition()
    client = next(
        item
        for item in composition.services.foundational_requirements
        if "user_pc" in item.device_id
    )
    services = composition.services.model_copy(
        update={
            "foundational_requirements": [
                item.model_copy(update={"model": "Laptop-PT"})
                if item.id == client.id
                else item
                for item in composition.services.foundational_requirements
            ]
        }
    )

    unsupported = _unsupported_paths(
        composition.configuration,
        services,
        services.services,
    )

    assert any(":model_Laptop-PT" in item for item in unsupported)


def test_a_static_endpoint_without_one_access_switch_is_refused():
    """Same segment does not replace the required switching prerequisite."""
    composition = _composition()
    client = next(
        item
        for item in composition.configuration.actions
        if isinstance(item, SetEndpointStaticAddress) and "user_pc" in item.device_id
    )
    configuration = composition.configuration.model_copy(
        update={
            "actions": [
                item.model_copy(update={"depends_on": [], "apply_dependencies": []})
                if item.id == client.id
                else item
                for item in composition.configuration.actions
            ]
        }
    )

    unsupported = _unsupported_paths(
        configuration,
        composition.services,
        composition.services.services,
    )

    assert any(item.endswith(":switching_prerequisite") for item in unsupported)
