"""Exact reference designs resolve through E3 without weakening evidence gates."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCandidateStatus,
    PoEAuthorizedBinding,
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
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
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
                endpoint_model="PC-PT",
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
                    endpoint_model="7960",
                    endpoint_port="Switch",
                )
                for index in range(1, phones + 1)
            ],
        )],
    )


def _switch_candidates(store=None):
    """The productive exact-version root, so PoE evidence is the real one.

    ``store`` pins the evidence explicitly.  The default reads the host's own
    snapshot store, so a governed qualification performed on this machine
    changes what these candidates carry.
    """
    return packet_tracer_enterprise_capability_adapter(
        MEASURED_BACKEND_VERSION, store=store,
    ).hardware_candidates("switch", MEASURED_BACKEND_VERSION)


def _rebudget(candidates, model: str, poe_ports: int):
    """Same exact-build ports, a deliberately smaller admitted power budget."""
    return [
        item.model_copy(update={
            "capabilities": item.capabilities.model_copy(
                update={
                    "supports_poe": CapabilityStatus.SUPPORTED,
                    "poe_ports": poe_ports,
                    "poe_authorized_bindings": [
                        PoEAuthorizedBinding(
                            f"FastEthernet0/{index}", "7960", "Switch",
                        )
                        for index in range(1, poe_ports + 1)
                    ],
                },
            ),
        })
        if item.model == model else item
        for item in candidates
    ]


def _unmeasured(candidates, model: str):
    """The same build, with its PoE question deliberately unanswered."""
    return [
        item.model_copy(update={
            "capabilities": item.capabilities.model_copy(update={
                "supports_poe": CapabilityStatus.UNKNOWN,
                "poe_ports": None,
            }),
        })
        if item.model == model else item
        for item in candidates
    ]


def test_unknown_poe_evidence_allows_execution_without_a_delivery_claim():
    """Physical execution is admissible; UNKNOWN still supplies no PoE claim."""
    candidates = _unmeasured(_switch_candidates(), "2960-24TT")

    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(), _poe_design(model="2960-24TT"), candidates,
    )

    assert result.status is HardwarePlanStatus.EXECUTABLE_WITH_UNVERIFIED_POE
    device = result.site_hardware[0].devices[0]
    assert device.selection_status is DeviceCandidateStatus.COMPATIBLE
    assert device.poe_capacity is None
    assert device.poe_authorized_bindings == []
    assert device.poe_uncertainty is not None
    assert any(
        "2960-24TT" in item and "unknown" in item.casefold()
        for item in result.warnings
    )


def test_control_off_without_a_delivery_test_remains_unverified():
    """2960-24TT has a measured control state, not a delivery refusal.

    Every one of its 24 access ports reported complete administrative and
    runtime power-OFF state on 9.0.1.0858. Without an attached powered device,
    that does not decide delivery capability.
    """
    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(), _poe_design(model="2960-24TT"), _switch_candidates(),
    )

    assert result.status is HardwarePlanStatus.EXECUTABLE_WITH_UNVERIFIED_POE
    device = result.site_hardware[0].devices[0]
    assert device.selection_status is DeviceCandidateStatus.COMPATIBLE
    assert any(
        "2960-24TT" in item and "unknown" in item for item in result.warnings
    )


def test_control_only_poe_baseline_preserves_unverified_execution_demand(
    tmp_path,
):
    """The exact-build 3560 control observation does not prove delivery."""
    # Pinned to an empty store: this measures the control-only baseline, so it
    # must not read whatever delivery evidence the host happens to hold.
    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(phones=24),
        _poe_design(model="3560-24PS", phones=24),
        _switch_candidates(CapabilitySnapshotStore(tmp_path / "capabilities")),
    )

    assert result.status is HardwarePlanStatus.EXECUTABLE_WITH_UNVERIFIED_POE, result.warnings
    device = result.site_hardware[0].devices[0]
    assert device.selection_status is DeviceCandidateStatus.COMPATIBLE
    assert device.poe_capacity is None
    assert device.poe_authorized_bindings == []
    assert device.poe_uncertainty is not None


def test_poe_demand_beyond_evidenced_capacity_is_executable_with_unknown_scope():
    """A two-port claim cannot prove three simultaneous deliveries or forbid measuring them."""
    candidates = _rebudget(_switch_candidates(), "3560-24PS", 2)

    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(phones=3), _poe_design(model="3560-24PS", phones=3), candidates,
    )

    assert result.status is HardwarePlanStatus.EXECUTABLE_WITH_UNVERIFIED_POE
    device = result.site_hardware[0].devices[0]
    assert device.poe_capacity == 2
    assert device.poe_uncertainty is not None
    assert device.poe_uncertainty.required_simultaneous_ports == 3
    assert device.poe_uncertainty.unverified_bindings == [
        PoEAuthorizedBinding("FastEthernet0/3", "7960", "Switch"),
    ]
    assert any(
        "sw1" in item and "3" in item and "2" in item for item in result.warnings
    )


def test_exact_delivery_binding_authorizes_only_its_measured_switch_port():
    candidates = _rebudget(_switch_candidates(), "3560-24PS", 1)

    exact = ReferenceHardwarePlanner().plan(
        _poe_enterprise(), _poe_design(model="3560-24PS"), candidates,
    )
    adjacent = ReferenceHardwarePlanner().plan(
        _poe_enterprise(),
        _poe_design(model="3560-24PS", first_port=2),
        candidates,
    )

    assert exact.status is HardwarePlanStatus.VALID
    assert exact.site_hardware[0].devices[0].poe_uncertainty is None
    assert adjacent.site_hardware[0].devices[0].poe_capacity == 1
    assert adjacent.site_hardware[0].devices[0].poe_uncertainty.unverified_bindings == [
        PoEAuthorizedBinding("FastEthernet0/2", "7960", "Switch"),
    ]
    assert adjacent.status is HardwarePlanStatus.EXECUTABLE_WITH_UNVERIFIED_POE
    assert adjacent.site_hardware[0].devices[0].selection_status is (
        DeviceCandidateStatus.COMPATIBLE
    )


def test_exact_delivery_binding_does_not_authorize_another_endpoint_identity():
    candidates = _rebudget(_switch_candidates(), "3560-24PS", 1)
    wrong_model = _poe_design(model="3560-24PS")
    wrong_model.sites[0].endpoint_bindings[0].endpoint_model = "AccessPoint-PT"
    wrong_port = _poe_design(model="3560-24PS")
    wrong_port.sites[0].endpoint_bindings[0].endpoint_port = "Port 0"

    model_result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(), wrong_model, candidates,
    )
    port_result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(), wrong_port, candidates,
    )

    assert model_result.status is HardwarePlanStatus.EXECUTABLE_WITH_UNVERIFIED_POE
    assert port_result.status is HardwarePlanStatus.EXECUTABLE_WITH_UNVERIFIED_POE


def test_two_simultaneous_exact_bindings_authorize_only_that_complete_group():
    candidates = _rebudget(_switch_candidates(), "3560-24PS", 2)

    exact = ReferenceHardwarePlanner().plan(
        _poe_enterprise(phones=2),
        _poe_design(model="3560-24PS", phones=2),
        candidates,
    )
    outside = ReferenceHardwarePlanner().plan(
        _poe_enterprise(phones=2),
        _poe_design(model="3560-24PS", phones=2, first_port=2),
        candidates,
    )

    assert exact.status is HardwarePlanStatus.VALID
    assert outside.status is HardwarePlanStatus.EXECUTABLE_WITH_UNVERIFIED_POE


def test_powered_endpoints_may_not_be_bound_to_unpowered_uplink_ports():
    """The 3560 evidence covers its 24 access ports, not its Gigabit uplinks."""
    design = _poe_design(model="3560-24PS", phones=1)
    design.sites[0].endpoint_bindings[0].device_port = "GigabitEthernet0/1"

    result = ReferenceHardwarePlanner().plan(
        _poe_enterprise(), design, _rebudget(_switch_candidates(), "3560-24PS", 24),
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
