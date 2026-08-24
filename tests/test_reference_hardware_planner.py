"""Exact reference designs resolve through E3 without weakening evidence gates."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.hardware import (
    AccessBlockPlan,
    EndpointPortBinding,
    HierarchyMode,
    HardwarePlanStatus,
    PhysicalDesignDevice,
    PhysicalDesignSpec,
    PhysicalSiteDesign,
)
from src.packet_tracer_mcp.domain.enterprise.models.intent import (
    EnterpriseIntent,
    SiteIntent,
    SiteType,
)
from src.packet_tracer_mcp.domain.enterprise.models.requirements import (
    EndpointRequirement,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.topology import (
    NetworkLayer,
    TopologyPattern,
)
from src.packet_tracer_mcp.domain.enterprise.services.enterprise_designer import (
    EnterpriseDesigner,
)
from src.packet_tracer_mcp.domain.enterprise.services.reference_hardware_planner import (
    ReferenceHardwarePlanner,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)


def _enterprise():
    result = EnterpriseDesigner().design(EnterpriseIntent(
        name="Exact",
        sites=[SiteIntent(
            name="Site",
            type=SiteType.BRANCH,
            endpoints=[EndpointRequirement(role=DeviceRole.USER_PC, count=1)],
        )],
    ))
    assert result.plan is not None and result.validation.is_valid
    return result.plan


def _design() -> PhysicalDesignSpec:
    return PhysicalDesignSpec(
        id="exact",
        sites=[PhysicalSiteDesign(
            site_id="site",
            topology_pattern=TopologyPattern.STAR,
            hierarchy_mode=HierarchyMode.FLAT,
            network_layers=[NetworkLayer.ACCESS],
            devices=[PhysicalDesignDevice(
                id="sw1",
                site_id="site",
                semantic_name="Switch10",
                role=DeviceRole.ACCESS_SWITCH,
                network_layer=NetworkLayer.ACCESS,
                model="2960-24TT",
            )],
            access_blocks=[AccessBlockPlan(
                site_id="site",
                zone_id="site/default",
                block_id="exact",
                switches=["sw1"],
                required_access_ports=1,
                required_poe_ports=0,
                required_uplinks=0,
            )],
            endpoint_bindings=[EndpointPortBinding(
                endpoint_id="endpoint/site/default/user_pc/001",
                device_id="sw1",
                device_port="FastEthernet0/24",
            )],
        )],
    )


def test_exact_build_candidate_resolves_the_reference_hardware_plan():
    candidates = EnterpriseCapabilityAdapter().hardware_candidates(
        "switch", MEASURED_BACKEND_VERSION,
    )

    result = ReferenceHardwarePlanner().plan(_enterprise(), _design(), candidates)

    assert result.status is HardwarePlanStatus.VALID
    device = result.site_hardware[0].devices[0]
    assert device.semantic_name == "Switch10"
    assert device.selected_model == "2960-24TT"
    assert result.site_hardware[0].endpoint_bindings[0].device_port == (
        "FastEthernet0/24"
    )


def test_catalog_only_port_names_do_not_authorize_an_exact_reference_binding():
    candidates = EnterpriseCapabilityAdapter().hardware_candidates("switch")

    result = ReferenceHardwarePlanner().plan(_enterprise(), _design(), candidates)

    assert result.status is HardwarePlanStatus.UNRESOLVED
    assert any("not exact-build evidence" in item for item in result.warnings)
