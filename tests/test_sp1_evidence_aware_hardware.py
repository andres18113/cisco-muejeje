"""SP-1 A-1: the planner prefers models whose required E5 evidence exists.

The expected results follow from the requirement, not from a model list: a
site router that E5 will configure as a layer-3 gateway, and an access switch
that will carry trunks, are chosen among models whose exact-build evidence
says SUPPORTED whenever one fits. An unmeasured model still wins when nothing
measured fits, and the designs that never needed the evidence are unchanged.
"""

from __future__ import annotations

import json

import pytest

from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
    capability_catalog_for,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from packet_tracer_mcp.domain.enterprise.models.hardware import (
    HardwareCandidate,
    PortClass,
    PortDescriptor,
)
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
    SwitchCountPlanner,
)

BUILD = "9.0.1.0858"


def _site(name: str, kind: str, users: int, *, servers: int = 0) -> dict:
    endpoints = [{"role": "user_pc", "count": users, "addressing_preference": "static"}]
    if servers:
        endpoints.append(
            {
                "role": "server",
                "count": servers,
                "addressing_preference": "static",
                "segment_role": "servers",
            }
        )
    return {"name": name, "type": kind, "endpoints": endpoints}


def _intent(media: str, *, hq_servers: int = 1) -> EnterpriseIntent:
    hq = _site("HQ", "hq", 2, servers=hq_servers)
    hq["uplinks"] = [
        {"target_site_id": "br1", "media": media},
        {"target_site_id": "br2", "media": media},
    ]
    payload = {
        "name": "SP1-EVIDENCE",
        "address_space": "10.40.0.0/16",
        "internet_required": True,
        "sites": [hq, _site("BR1", "branch", 2), _site("BR2", "branch", 2)],
    }
    return EnterpriseIntent.model_validate_json(json.dumps(payload))


def _models(intent: EnterpriseIntent) -> dict[str, str]:
    composed = compose_enterprise_reference(intent, packet_tracer_version=BUILD)
    assert composed.topology is not None, composed.issues
    return {device.name: device.model for device in composed.topology.devices}


def _status(model: str, capability: str) -> CapabilityStatus:
    profile = capability_catalog_for(BUILD).capabilities_for(model, BUILD)
    assert profile is not None
    return getattr(profile, capability)


def test_ethernet_site_routers_are_layer3_evidenced():
    """Every site router of an Ethernet WAN design has measured layer 3."""
    models = _models(_intent("ethernet"))
    routers = {name: model for name, model in models.items() if "RTR" in name}

    assert len(routers) == 3
    assert {_status(model, "layer3") for model in routers.values()} == {
        CapabilityStatus.SUPPORTED
    }


def test_a_serial_design_keeps_the_module_free_measured_router():
    """Module count still ranks before evidence: CP-SCALE's 819 is kept."""
    models = _models(_intent("serial"))

    assert models["BR1-EDGE-RTR-01"] == "819HG-4G-IOX"
    assert models["BR2-EDGE-RTR-01"] == "819HG-4G-IOX"


def test_a_multi_segment_site_uses_a_trunk_evidenced_access_switch():
    """HQ has users and servers, so its access switch will carry trunks."""
    models = _models(_intent("ethernet"))

    assert _status(models["HQ-DEFAULT-ACCESS-SW-01"], "supports_trunk") is (
        CapabilityStatus.SUPPORTED
    )


def test_a_single_segment_site_keeps_its_previous_access_switch():
    """Branches have one segment and no trunk; nothing changes for them."""
    models = _models(_intent("ethernet"))

    assert models["BR1-DEFAULT-ACCESS-SW-01"] == "IE-2000"
    assert models["BR2-DEFAULT-ACCESS-SW-01"] == "IE-2000"


def _switch(model: str, trunk: CapabilityStatus, access: int) -> HardwareCandidate:
    ports = [
        PortDescriptor(name=f"Fa0/{index}", classes=[PortClass.ACCESS_CAPABLE])
        for index in range(1, access + 1)
    ] + [PortDescriptor(name="Gi0/1", classes=[PortClass.UPLINK_CAPABLE])]
    return HardwareCandidate(
        model=model,
        capabilities=DeviceCapabilities(
            model=model, category="switch", supports_trunk=trunk
        ),
        ports=ports,
    )


@pytest.mark.parametrize("requires_trunk", [False, True])
def test_trunk_evidence_only_reorders_when_trunks_are_required(requires_trunk):
    """Without a trunk need the tighter unmeasured model still wins."""
    small = _switch("SMALL", CapabilityStatus.UNKNOWN, 8)
    large = _switch("LARGE", CapabilityStatus.SUPPORTED, 24)

    choice = SwitchCountPlanner().choose(
        3, 0, 1, [small, large], requires_trunk=requires_trunk
    )

    assert choice is not None
    assert choice.candidate.model == ("LARGE" if requires_trunk else "SMALL")


def test_an_unmeasured_switch_still_wins_when_nothing_measured_fits():
    """Evidence reorders viable candidates; it never removes the only one."""
    only = _switch("ONLY", CapabilityStatus.UNKNOWN, 8)

    choice = SwitchCountPlanner().choose(3, 0, 1, [only], requires_trunk=True)

    assert choice is not None and choice.candidate.model == "ONLY"


def _single_segment_branch(users: int) -> EnterpriseIntent:
    hq = _site("HQ", "hq", 2, servers=1)
    hq["uplinks"] = [{"target_site_id": "br1", "media": "ethernet"}]
    payload = {
        "name": "SP2-CAPACITY",
        "address_space": "10.40.0.0/16",
        "internet_required": True,
        "sites": [hq, _site("BR1", "branch", users)],
    }
    return EnterpriseIntent.model_validate_json(json.dumps(payload))


def test_a_single_segment_site_past_one_switch_uses_trunk_evidenced_switches():
    """SP-2: 36 users need two access switches, which uplink over trunks.

    One segment alone never asked for trunk evidence, yet a site past one
    access switch is hierarchical and its access uplinks are trunks. E5
    refuses a trunk on a model whose trunk support is unknown, so the
    designer must choose measured trunk support whenever one fits.
    """
    models = _models(_single_segment_branch(36))
    access = {
        name: model
        for name, model in models.items()
        if name.startswith("BR1-") and "-ACCESS-SW-" in name
    }

    assert len(access) == 2
    assert {_status(model, "supports_trunk") for model in access.values()} == {
        CapabilityStatus.SUPPORTED
    }


def test_a_single_segment_site_within_one_switch_is_unchanged():
    """Eight users still fit one untrunked switch: nothing new is required."""
    models = _models(_single_segment_branch(3))

    assert models["BR1-DEFAULT-ACCESS-SW-01"] == "IE-2000"
