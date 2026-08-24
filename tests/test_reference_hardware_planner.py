"""Exact reference designs resolve through E3 without weakening evidence gates."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    DeviceCandidateStatus,
)
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
    packet_tracer_enterprise_capability_adapter,
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


def _poe_enterprise(phones: int = 1):
    result = EnterpriseDesigner().design(EnterpriseIntent(
        name="Exact",
        sites=[SiteIntent(
            name="Site",
            type=SiteType.BRANCH,
            endpoints=[EndpointRequirement(
                role=DeviceRole.IP_PHONE, count=phones, requires_poe=True,
            )],
        )],
    ))
    assert result.plan is not None and result.validation.is_valid
    return result.plan


def _poe_design(
    *,
    model: str = "2960-24TT",
    phones: int = 1,
    declared_poe: int | None = None,
    first_port: int = 1,
) -> PhysicalDesignSpec:
    """One exact switch powering `phones` explicitly bound IP phones."""
    return PhysicalDesignSpec(
        id="exact-poe",
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
                model=model,
            )],
            access_blocks=[AccessBlockPlan(
                site_id="site",
                zone_id="site/default",
                block_id="exact-poe",
                switches=["sw1"],
                required_access_ports=phones,
                required_poe_ports=phones if declared_poe is None else declared_poe,
                required_uplinks=0,
            )],
            endpoint_bindings=[
                EndpointPortBinding(
                    endpoint_id=f"endpoint/site/default/ip_phone/{index:03d}",
                    device_id="sw1",
                    device_port=f"FastEthernet0/{first_port + index - 1}",
                    endpoint_port="Switch",
                )
                for index in range(1, phones + 1)
            ],
        )],
    )


def _switch_candidates():
    """The productive exact-version root, so PoE evidence is the real one."""
    return packet_tracer_enterprise_capability_adapter(
        MEASURED_BACKEND_VERSION,
    ).hardware_candidates("switch", MEASURED_BACKEND_VERSION)


def _rebudget(candidates, model: str, poe_ports: int):
    """Same exact-build ports, a deliberately smaller admitted power budget."""
    return [
        item.model_copy(update={
            "capabilities": item.capabilities.model_copy(
                update={"poe_ports": poe_ports},
            ),
        })
        if item.model == model else item
        for item in candidates
    ]


def test_unknown_poe_evidence_never_admits_a_powered_endpoint_binding():
    """A 2960-24TT reports no PoE evidence, so it may not power a phone.

    The exact-reference path used to hand this design to E5 as VALID with
    `poe_capacity=None`: a powered-port requirement admitted with no capability
    evidence at all. UNKNOWN is not permission.
    """
    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(), _poe_design(model="2960-24TT"), _switch_candidates(),
    )

    assert result.status is HardwarePlanStatus.PARTIALLY_RESOLVED
    device = result.site_hardware[0].devices[0]
    assert device.selection_status is DeviceCandidateStatus.NEEDS_VERIFICATION
    assert device.poe_capacity is None
    assert any(
        "2960-24TT" in item and "unknown" in item.casefold()
        for item in result.warnings
    )


def test_supported_poe_evidence_within_capacity_stays_valid():
    """3560-24PS carries exact-build evidence for 24 powered access ports."""
    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(phones=24),
        _poe_design(model="3560-24PS", phones=24),
        _switch_candidates(),
    )

    assert result.status is HardwarePlanStatus.VALID, result.warnings
    device = result.site_hardware[0].devices[0]
    assert device.selection_status is DeviceCandidateStatus.COMPATIBLE
    assert device.poe_capacity == 24


def test_poe_demand_beyond_the_exact_admitted_capacity_is_unresolved():
    """Three powered endpoints do not fit a budget evidenced as two."""
    candidates = _rebudget(_switch_candidates(), "3560-24PS", 2)

    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(phones=3), _poe_design(model="3560-24PS", phones=3), candidates,
    )

    assert result.status is HardwarePlanStatus.UNRESOLVED
    assert any(
        "sw1" in item and "3" in item and "2" in item for item in result.warnings
    )


def test_powered_endpoints_may_not_be_bound_to_unpowered_uplink_ports():
    """The 3560 evidence covers its 24 access ports, not its Gigabit uplinks."""
    design = _poe_design(model="3560-24PS", phones=1)
    design.sites[0].endpoint_bindings[0].device_port = "GigabitEthernet0/1"

    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(), design, _switch_candidates(),
    )

    assert result.status is HardwarePlanStatus.UNRESOLVED
    assert any("GigabitEthernet0/1" in item for item in result.warnings)


def test_block_poe_aggregate_must_reconcile_with_the_exact_bindings():
    """A block that under-declares its powered demand is a governance defect."""
    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(phones=2),
        _poe_design(model="3560-24PS", phones=2, declared_poe=1),
        _switch_candidates(),
    )

    assert result.status is HardwarePlanStatus.UNRESOLVED
    assert any(
        "exact-poe" in item and "required_poe_ports" in item
        for item in result.warnings
    )
