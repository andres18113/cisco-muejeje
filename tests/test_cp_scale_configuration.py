"""CP-SCALE existing-scope configuration, PVST, RIPv2, and voice."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from tests.test_cp_scale_layout import _compile
from tests.test_stage3a4_product_composition import _oriented_manifest


def test_wireless_iot_vlan_is_carried_structurally_without_claiming_association():
    enterprise, _, compiled = _compile()
    topology = compiled.plan
    configuration = compile_enterprise_configuration(
        enterprise,
        topology,
        deployment_manifest=_oriented_manifest(topology),
        packet_tracer_version="9.0.1.0858",
    )

    assert configuration.is_valid and configuration.plan is not None
    created = {
        (item.site_id, item.vlan_id)
        for item in configuration.plan.actions
        if item.action_type is ConfigurationActionType.CREATE_VLAN
    }
    assert {
        vlan for site, vlan in created if site == "large-branch"
    } == {10, 20, 30, 40, 99}
    assert {
        vlan for site, vlan in created if site == "multilayer-branch"
    } == {10, 20, 30, 99}
    assert {
        vlan for site, vlan in created if site == "small-branch"
    } == {10, 20, 30, 99}
    trunks = configuration.plan.actions_of_type(ConfigurationActionType.CONFIGURE_TRUNK)
    assert trunks and all(30 in item.allowed_vlans for item in trunks)
    assert all(
        item.metadata.get("requirement.wireless_association") == "unqualified"
        for item in topology.devices
        if item.model == "Thing"
    )

