"""Offline guards for the exact-model PVST live qualifier.

The live tool imports the production package namespace. Exercise it in one
child process so pytest itself keeps only the governed ``src.`` namespace.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

_PROBE = r'''
import json
import sys
from dataclasses import replace

sys.path.insert(0, __ROOT__)
sys.path.insert(0, __SRC__)

from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    StpInstanceStatus,
)
from tools.stp_pvst_runtime_qualification import (
    EDGE_INTERFACE,
    PRIMARY_MODEL,
    SECONDARY_MODEL,
    TRUNK_INTERFACE,
    VLAN_ID,
    foundation_actions,
    qualification_topology,
    stp_actions,
    stp_convergence_errors,
    stp_expectations,
)


def instance(
    *,
    base_priority,
    bridge_address,
    root_address,
    root_is_local,
    root_port,
):
    return StpInstanceStatus(
        vlan_id=VLAN_ID,
        protocol="ieee",
        root_priority=24576 + VLAN_ID,
        root_address=root_address,
        root_is_local=root_is_local,
        root_cost=None if root_is_local else 4,
        root_port=root_port,
        bridge_priority=base_priority + VLAN_ID,
        bridge_base_priority=base_priority,
        bridge_address=bridge_address,
        interfaces=(),
    )


topology = qualification_topology()
foundation = foundation_actions(topology)
actions = stp_actions(topology)
expectations = stp_expectations(topology)
primary = instance(
    base_priority=24576,
    bridge_address="0011.2233.4455",
    root_address="0011.2233.4455",
    root_is_local=True,
    root_port="",
)
secondary = instance(
    base_priority=28672,
    bridge_address="0066.7788.99aa",
    root_address=primary.bridge_address,
    root_is_local=False,
    root_port="Gi0/1",
)

print(json.dumps({
    "constants": {
        "primary_model": PRIMARY_MODEL,
        "secondary_model": SECONDARY_MODEL,
        "trunk_interface": TRUNK_INTERFACE,
        "edge_interface": EDGE_INTERFACE,
        "vlan_id": VLAN_ID,
    },
    "topology": {
        "devices": [(item.id, item.model) for item in topology.devices],
        "links": [
            {
                "device_ids": sorted([item.device_a_id, item.device_b_id]),
                "ports": [item.port_a, item.port_b],
            }
            for item in topology.links
        ],
    },
    "foundation": [
        {
            "type": type(item).__name__,
            "vlan_id": getattr(item, "vlan_id", None),
            "interface": getattr(item, "interface", None),
            "allowed_vlans": getattr(item, "allowed_vlans", None),
            "data_vlan_id": getattr(item, "data_vlan_id", None),
        }
        for item in foundation
    ],
    "actions": [
        {
            "type": type(item).__name__,
            "id": item.id,
            "model": item.model,
            "capability": item.required_capability.value,
            "mode": getattr(getattr(item, "mode", None), "value", None),
            "root_primary_vlans": getattr(item, "root_primary_vlans", None),
            "root_secondary_vlans": getattr(item, "root_secondary_vlans", None),
            "interface": getattr(item, "interface", None),
            "portfast": getattr(item, "portfast", None),
            "bpduguard": getattr(item, "bpduguard", None),
        }
        for item in actions
    ],
    "expectations": [
        {
            "action_id": item.action_id,
            "capability": item.required_capability.value,
            "source_device_name": item.expected["source_device_name"],
        }
        for item in expectations
    ],
    "convergence": {
        "valid": stp_convergence_errors({
            PRIMARY_MODEL: [primary],
            SECONDARY_MODEL: [secondary],
        }),
        "secondary_local": stp_convergence_errors({
            PRIMARY_MODEL: [primary],
            SECONDARY_MODEL: [replace(secondary, root_is_local=True)],
        }),
        "wrong_port": stp_convergence_errors({
            PRIMARY_MODEL: [primary],
            SECONDARY_MODEL: [replace(
                secondary, root_port="FastEthernet0/1",
            )],
        }),
        "wrong_root": stp_convergence_errors({
            PRIMARY_MODEL: [primary],
            SECONDARY_MODEL: [replace(
                secondary, root_address="00ff.ffff.ffff",
            )],
        }),
        "missing_secondary": stp_convergence_errors({
            PRIMARY_MODEL: [primary],
        }),
    },
}))
'''


@pytest.fixture(scope="module")
def verdict() -> dict:
    code = _PROBE.replace("__ROOT__", repr(str(ROOT))).replace(
        "__SRC__", repr(str(ROOT / "src")),
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_qualifier_uses_only_the_two_exact_blocking_models_and_one_trunk(
    verdict: dict,
):
    constants = verdict["constants"]
    assert verdict["topology"]["devices"] == [
        ["pvst-primary", constants["primary_model"]],
        ["pvst-secondary", constants["secondary_model"]],
    ]
    assert verdict["topology"]["links"] == [{
        "device_ids": ["pvst-primary", "pvst-secondary"],
        "ports": [constants["trunk_interface"], constants["trunk_interface"]],
    }]


def test_qualifier_foundation_is_typed_vlan_trunk_and_one_access_port(
    verdict: dict,
):
    foundation = verdict["foundation"]
    assert sum(item["type"] == "CreateVlan" for item in foundation) == 2
    assert sum(item["type"] == "ConfigureTrunk" for item in foundation) == 2
    assert sum(item["type"] == "ConfigureAccessPort" for item in foundation) == 1
    assert all(
        item["vlan_id"] == verdict["constants"]["vlan_id"]
        for item in foundation if item["type"] == "CreateVlan"
    )
    trunks = [item for item in foundation if item["type"] == "ConfigureTrunk"]
    assert all(
        item["interface"] == verdict["constants"]["trunk_interface"]
        and item["allowed_vlans"] == [verdict["constants"]["vlan_id"]]
        for item in trunks
    )
    edge = next(
        item for item in foundation if item["type"] == "ConfigureAccessPort"
    )
    assert edge["interface"] == verdict["constants"]["edge_interface"]
    assert edge["data_vlan_id"] == verdict["constants"]["vlan_id"]


def test_qualifier_exercises_global_pvst_on_both_models_and_edge_on_3560(
    verdict: dict,
):
    actions = verdict["actions"]
    global_actions = [
        item for item in actions if item["type"] == "ConfigureSpanningTree"
    ]
    edge = next(
        item for item in actions if item["type"] == "ConfigureStpEdgePort"
    )
    assert len(global_actions) == 2
    assert {item["model"] for item in global_actions} == {
        verdict["constants"]["primary_model"],
        verdict["constants"]["secondary_model"],
    }
    assert all(item["mode"] == "pvst" for item in global_actions)
    assert all(item["capability"] == "stp_pvst_config" for item in actions)
    assert next(
        item for item in global_actions
        if item["model"] == verdict["constants"]["primary_model"]
    )["root_primary_vlans"] == [verdict["constants"]["vlan_id"]]
    assert next(
        item for item in global_actions
        if item["model"] == verdict["constants"]["secondary_model"]
    )["root_secondary_vlans"] == [verdict["constants"]["vlan_id"]]
    assert edge["model"] == verdict["constants"]["primary_model"]
    assert edge["interface"] == verdict["constants"]["edge_interface"]
    assert edge["portfast"] is True
    assert edge["bpduguard"] is True


def test_qualifier_declares_fresh_state_expectations_for_both_global_actions(
    verdict: dict,
):
    expectations = verdict["expectations"]
    assert {item["action_id"] for item in expectations} == {
        "pvst/stp/primary", "pvst/stp/secondary",
    }
    assert all(item["capability"] == "stp_state" for item in expectations)
    assert {item["source_device_name"] for item in expectations} == {
        "MCP-PROBE-PVST-3560", "MCP-PROBE-PVST-2960",
    }


def test_convergence_requires_primary_root_secondary_priority_and_exact_root_path(
    verdict: dict,
):
    convergence = verdict["convergence"]
    assert convergence["valid"] == []
    assert convergence["secondary_local"]
    assert convergence["wrong_port"]
    assert convergence["wrong_root"]
    assert convergence["missing_secondary"]
