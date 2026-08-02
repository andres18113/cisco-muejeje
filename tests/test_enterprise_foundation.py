"""Pruebas offline de E1: dominio Enterprise y adaptación del catálogo vigente."""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
    DeviceRequirement,
    DeviceSelectionStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.enterprise_plan import EnterprisePlan
from src.packet_tracer_mcp.domain.enterprise.models.intent import (
    EnterpriseIntent,
    SiteIntent,
    SiteType,
)
from src.packet_tracer_mcp.domain.enterprise.models.requirements import EndpointRequirement
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.segments import SegmentRole
from src.packet_tracer_mcp.domain.enterprise.services.capability_resolver import (
    CapabilityResolver,
    CatalogDeviceFacts,
)
from src.packet_tracer_mcp.domain.enterprise.services.device_selector import DeviceSelector
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from src.packet_tracer_mcp.domain.enterprise.services.requirements_validator import (
    validate_enterprise_intent,
)
from src.packet_tracer_mcp.infrastructure.catalog.devices import ALL_MODELS
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)


@pytest.mark.parametrize("site_type", list(SiteType))
def test_enterprise_intent_accepts_every_initial_site_type(site_type: SiteType):
    intent = EnterpriseIntent(
        name="Artefacta",
        sites=[SiteIntent(name="Quito", type=site_type)],
    )

    assert validate_enterprise_intent(intent).is_valid


@pytest.mark.parametrize("count", [0, -1])
def test_endpoint_count_is_validated_by_enterprise_rules_not_the_model(count: int):
    intent = EnterpriseIntent(
        name="Artefacta",
        sites=[SiteIntent(
            name="Quito",
            type=SiteType.HQ,
            endpoints=[EndpointRequirement(role=DeviceRole.USER_PC, count=count)],
        )],
    )

    result = validate_enterprise_intent(intent)
    assert not result.is_valid
    assert result.errors[0].code.value == "ENTERPRISE_INVALID_ENDPOINT_COUNT"


def test_endpoint_and_segment_roles_are_serialized_as_stable_values():
    endpoint = EndpointRequirement(role=DeviceRole.IP_PHONE, count=1)

    assert endpoint.model_dump(mode="json")["role"] == "ip_phone"
    assert SegmentRole.CCTV.value == "cctv"


@pytest.mark.parametrize("growth", [-1, 101])
def test_growth_percent_outside_0_to_100_is_rejected(growth: float):
    intent = EnterpriseIntent(
        name="Artefacta",
        default_growth_percent=growth,
        sites=[SiteIntent(name="Quito", type=SiteType.HQ)],
    )

    assert not validate_enterprise_intent(intent).is_valid


def test_designer_creates_semantic_segments_without_vlan_or_subnet():
    intent = EnterpriseIntent(
        name="Artefacta",
        default_growth_percent=25,
        sites=[SiteIntent(
            name="Matriz Quito",
            type=SiteType.HQ,
            endpoints=[
                EndpointRequirement(role=DeviceRole.USER_PC, count=30),
                EndpointRequirement(role=DeviceRole.IP_PHONE, count=30, requires_poe=True),
                EndpointRequirement(role=DeviceRole.IP_CAMERA, count=12, requires_poe=True),
            ],
        )],
    )

    designed = EnterpriseDesigner().design(intent)

    assert designed.validation.is_valid
    assert designed.plan is not None
    segments = {segment.role: segment for segment in designed.plan.sites[0].segments}
    assert segments[SegmentRole.DATA].host_requirement == 30
    assert segments[SegmentRole.VOICE].host_requirement == 30
    assert segments[SegmentRole.CCTV].host_requirement == 12
    assert all(segment.vlan_id is None and segment.subnet is None for segment in segments.values())


def test_enterprise_plan_pydantic_round_trip_is_consistent():
    plan = EnterpriseDesigner().design(EnterpriseIntent(
        name="Artefacta",
        sites=[SiteIntent(name="Quito", type=SiteType.HQ)],
    )).plan
    assert plan is not None

    assert EnterprisePlan.model_validate_json(plan.model_dump_json()) == plan


def test_capability_resolver_keeps_unverified_features_unknown():
    capabilities = CapabilityResolver().resolve(CatalogDeviceFacts(
        model="Example",
        category="switch",
        port_speeds=("FastEthernet", "GigabitEthernet"),
    ))

    assert capabilities.fastethernet_ports == 1
    assert capabilities.gigabit_ports == 1
    assert capabilities.layer3 is CapabilityStatus.UNKNOWN
    assert capabilities.supports_poe is CapabilityStatus.UNKNOWN
    assert capabilities.supports_modules is CapabilityStatus.UNKNOWN


def _switch(model: str, *, ports: int, uplinks: int, poe: CapabilityStatus = CapabilityStatus.UNKNOWN,
            poe_ports: int | None = None, layer3: CapabilityStatus = CapabilityStatus.UNKNOWN) -> DeviceCapabilities:
    return DeviceCapabilities(
        model=model,
        category="switch",
        fastethernet_ports=ports - uplinks,
        gigabit_ports=uplinks,
        port_count=ports,
        supports_poe=poe,
        poe_ports=poe_ports,
        layer3=layer3,
    )


def test_device_selector_selects_compatible_candidate_and_alternatives():
    result = DeviceSelector().select(
        DeviceRequirement(role=DeviceRole.ACCESS_SWITCH, min_access_ports=24, min_uplinks=2),
        [_switch("Small", ports=10, uplinks=2), _switch("Large", ports=26, uplinks=2), _switch("Larger", ports=30, uplinks=4)],
    )

    assert result.status is DeviceSelectionStatus.SUPPORTED
    assert result.selected_model == "Large"
    assert result.alternatives == ["Larger"]


def test_device_selector_rejects_unverified_poe_instead_of_inventing_support():
    result = DeviceSelector().select(
        DeviceRequirement(role=DeviceRole.ACCESS_SWITCH, min_access_ports=24, poe_ports=20),
        [_switch("Unknown-PoE", ports=26, uplinks=2)],
    )

    assert result.status is DeviceSelectionStatus.PARTIALLY_SUPPORTED
    assert result.selected_model is None
    assert result.candidates[0].missing_evidence == ["supports_poe"]


def test_device_selector_is_deterministic_and_handles_preferred_model_rejection():
    requirement = DeviceRequirement(
        role=DeviceRole.ACCESS_SWITCH,
        min_access_ports=24,
        preferred_model="TooSmall",
    )
    candidates = [_switch("Zulu", ports=26, uplinks=2), _switch("Alpha", ports=26, uplinks=2), _switch("TooSmall", ports=8, uplinks=2)]

    forward = DeviceSelector().select(requirement, candidates)
    backward = DeviceSelector().select(requirement, reversed(candidates))

    assert forward.selected_model == backward.selected_model == "Alpha"
    assert forward.alternatives == backward.alternatives == ["Zulu"]
    assert forward.warnings == backward.warnings
    assert "TooSmall rechazado" in forward.warnings[0]


def test_model_aliases_normalize_to_the_existing_canonical_catalog_name():
    adapter = EnterpriseCapabilityAdapter()

    assert adapter.normalize_model_name("ISR4331") == "ISR4331"
    assert adapter.normalize_model_name("4331") == "ISR4331"
    assert adapter.normalize_model_name("Cisco 4331") == "ISR4331"


def test_every_catalog_router_and_switch_is_representable_once():
    adapter = EnterpriseCapabilityAdapter()
    models = [model for model in ALL_MODELS.values() if model.category in {"router", "switch"}]
    capabilities = [adapter.capabilities_for(model.pt_type) for model in models]

    assert all(adapter.can_represent(model.pt_type) for model in models)
    assert all(capability is not None for capability in capabilities)
    assert {capability.model for capability in capabilities if capability} == {model.pt_type for model in models}
    assert {capability.model for capability in adapter.all_capabilities("router")} == {
        model.pt_type for model in models if model.category == "router"
    }
    assert {capability.model for capability in adapter.all_capabilities("switch")} == {
        model.pt_type for model in models if model.category == "switch"
    }


def test_pt_empty_keeps_logical_capabilities_unknown():
    capabilities = EnterpriseCapabilityAdapter().capabilities_for("Router-PT-Empty")
    assert capabilities is not None

    assert capabilities.port_count == 0
    assert capabilities.layer2 is CapabilityStatus.UNKNOWN
    assert capabilities.layer3 is CapabilityStatus.UNKNOWN
    assert capabilities.supports_poe is CapabilityStatus.UNKNOWN
    assert capabilities.supports_modules in {CapabilityStatus.SUPPORTED, CapabilityStatus.UNKNOWN}
