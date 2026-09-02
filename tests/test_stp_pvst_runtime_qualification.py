"""Offline guards for the exact-model PVST live qualifier.

The live tool imports the production package namespace. Exercise it in one
child process so pytest itself keeps only the governed ``src.`` namespace.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIRST_LIVE_EVIDENCE = (
    ROOT / "docs" / "reference" / "cp-scale" / "canonical-live-evidence"
    / "stp-pvst-capability-20260901T143133904065Z-7aead990dccc.json"
)
SECOND_LIVE_EVIDENCE = (
    ROOT / "docs" / "reference" / "cp-scale" / "canonical-live-evidence"
    / "stp-pvst-capability-20260901T143608724809Z-71fae1c74878.json"
)
THIRD_LIVE_EVIDENCE = (
    ROOT / "docs" / "reference" / "cp-scale" / "canonical-live-evidence"
    / "stp-pvst-capability-20260901T150150452540Z-29afd03bdd21.json"
)
FOURTH_LIVE_EVIDENCE = (
    ROOT / "docs" / "reference" / "cp-scale" / "canonical-live-evidence"
    / "stp-pvst-capability-20260901T151056013414Z-c61ee6626d65.json"
)
FIFTH_LIVE_EVIDENCE = (
    ROOT / "docs" / "reference" / "cp-scale" / "canonical-live-evidence"
    / "stp-pvst-capability-20260902T002049264918Z-ed386bcd37f5.json"
)

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
    TERTIARY_EDGE_INTERFACE,
    TERTIARY_MODEL,
    TERTIARY_TRUNK_INTERFACE,
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
tertiary = instance(
    base_priority=28672,
    bridge_address="00bb.ccdd.eeff",
    root_address=primary.bridge_address,
    root_is_local=False,
    root_port=TERTIARY_TRUNK_INTERFACE,
)

print(json.dumps({
    "constants": {
        "primary_model": PRIMARY_MODEL,
        "secondary_model": SECONDARY_MODEL,
        "tertiary_model": TERTIARY_MODEL,
        "trunk_interface": TRUNK_INTERFACE,
        "edge_interface": EDGE_INTERFACE,
        "tertiary_trunk_interface": TERTIARY_TRUNK_INTERFACE,
        "tertiary_edge_interface": TERTIARY_EDGE_INTERFACE,
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
            "hostname": getattr(item, "hostname", None),
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
            TERTIARY_MODEL: [tertiary],
        }),
        "secondary_local": stp_convergence_errors({
            PRIMARY_MODEL: [primary],
            SECONDARY_MODEL: [replace(secondary, root_is_local=True)],
            TERTIARY_MODEL: [tertiary],
        }),
        "wrong_port": stp_convergence_errors({
            PRIMARY_MODEL: [primary],
            SECONDARY_MODEL: [replace(
                secondary, root_port="FastEthernet0/1",
            )],
            TERTIARY_MODEL: [tertiary],
        }),
        "wrong_root": stp_convergence_errors({
            PRIMARY_MODEL: [primary],
            SECONDARY_MODEL: [replace(
                secondary, root_address="00ff.ffff.ffff",
            )],
            TERTIARY_MODEL: [tertiary],
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


def test_qualifier_uses_the_three_exact_models_and_two_trunks(
    verdict: dict,
):
    constants = verdict["constants"]
    assert verdict["topology"]["devices"] == [
        ["pvst-primary", constants["primary_model"]],
        ["pvst-secondary", constants["secondary_model"]],
        ["pvst-tertiary", constants["tertiary_model"]],
    ]
    assert verdict["topology"]["links"] == [
        {
            "device_ids": ["pvst-primary", "pvst-secondary"],
            "ports": [
                constants["trunk_interface"], constants["trunk_interface"],
            ],
        },
        {
            "device_ids": ["pvst-primary", "pvst-tertiary"],
            "ports": [
                "GigabitEthernet0/2",
                constants["tertiary_trunk_interface"],
            ],
        },
    ]


def test_qualifier_foundation_is_typed_vlan_trunks_and_two_access_ports(
    verdict: dict,
):
    foundation = verdict["foundation"]
    assert sum(item["type"] == "ConfigureHostname" for item in foundation) == 3
    assert sum(item["type"] == "CreateVlan" for item in foundation) == 3
    assert sum(item["type"] == "ConfigureTrunk" for item in foundation) == 4
    assert sum(item["type"] == "ConfigureAccessPort" for item in foundation) == 2
    assert {
        item["hostname"]
        for item in foundation if item["type"] == "ConfigureHostname"
    } == {
        "MCP-PROBE-PVST-3560",
        "MCP-PROBE-PVST-2960",
        "MCP-PROBE-PVST-3650",
    }
    assert all(
        item["vlan_id"] == verdict["constants"]["vlan_id"]
        for item in foundation if item["type"] == "CreateVlan"
    )
    trunks = [item for item in foundation if item["type"] == "ConfigureTrunk"]
    assert {item["interface"] for item in trunks} == {
        verdict["constants"]["trunk_interface"],
        "GigabitEthernet0/2",
        verdict["constants"]["tertiary_trunk_interface"],
    }
    assert all(
        item["allowed_vlans"] == [verdict["constants"]["vlan_id"]]
        for item in trunks
    )
    edges = [
        item for item in foundation if item["type"] == "ConfigureAccessPort"
    ]
    assert {item["interface"] for item in edges} == {
        verdict["constants"]["edge_interface"],
        verdict["constants"]["tertiary_edge_interface"],
    }
    assert all(
        item["data_vlan_id"] == verdict["constants"]["vlan_id"]
        for item in edges
    )


def test_qualifier_exercises_global_pvst_and_only_measured_edge_models(
    verdict: dict,
):
    actions = verdict["actions"]
    global_actions = [
        item for item in actions if item["type"] == "ConfigureSpanningTree"
    ]
    edges = [
        item for item in actions if item["type"] == "ConfigureStpEdgePort"
    ]
    assert len(global_actions) == 3
    assert {item["model"] for item in global_actions} == {
        verdict["constants"]["primary_model"],
        verdict["constants"]["secondary_model"],
        verdict["constants"]["tertiary_model"],
    }
    assert all(item["mode"] == "pvst" for item in global_actions)
    assert {
        item["capability"] for item in global_actions
    } == {"stp_pvst_config"}
    assert {
        item["capability"] for item in edges
    } == {"stp_edge_config"}
    assert next(
        item for item in global_actions
        if item["model"] == verdict["constants"]["primary_model"]
    )["root_primary_vlans"] == [verdict["constants"]["vlan_id"]]
    assert next(
        item for item in global_actions
        if item["model"] == verdict["constants"]["secondary_model"]
    )["root_secondary_vlans"] == [verdict["constants"]["vlan_id"]]
    assert next(
        item for item in global_actions
        if item["model"] == verdict["constants"]["tertiary_model"]
    )["root_secondary_vlans"] == [verdict["constants"]["vlan_id"]]
    assert {(item["model"], item["interface"]) for item in edges} == {
        (
            verdict["constants"]["primary_model"],
            verdict["constants"]["edge_interface"],
        ),
        (
            verdict["constants"]["tertiary_model"],
            verdict["constants"]["tertiary_edge_interface"],
        ),
    }
    assert all(item["portfast"] is True for item in edges)
    assert all(item["bpduguard"] is True for item in edges)


def test_qualifier_declares_fresh_expectations_for_all_global_actions(
    verdict: dict,
):
    expectations = verdict["expectations"]
    assert {item["action_id"] for item in expectations} == {
        "pvst/stp/primary", "pvst/stp/secondary", "pvst/stp/tertiary",
    }
    assert [
        item["capability"] for item in expectations
    ] == [
        "stp_state", "stp_state", "stp_state",
        "stp_behavior", "stp_behavior", "stp_behavior",
    ]
    assert {item["source_device_name"] for item in expectations} == {
        "MCP-PROBE-PVST-3560",
        "MCP-PROBE-PVST-2960",
        "MCP-PROBE-PVST-3650",
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


def test_first_live_negative_proves_trunk_convergence_but_not_unique_identity():
    assert hashlib.sha256(FIRST_LIVE_EVIDENCE.read_bytes()).hexdigest() == (
        "5da968302f54bd03e5c8a961182d10dd74d40fa251356b07dcc5b3ddb2f44a51"
    )
    evidence = json.loads(FIRST_LIVE_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["repository"]["head"] == (
        "7aead990dcccb104e35278223507df9ec1a63211"
    )
    assert evidence["foundation_trunk_convergence"]["verified"] is False
    attempts = evidence["foundation_trunk_convergence"]["attempts"]
    assert any(
        20 in (
            item["devices"]["3560-24PS"]["rows"][0]["forwarding_vlans"] or []
        )
        and item["devices"]["3560-24PS"]["device_identity_provenance"]
        == "confirmed_unique"
        for item in attempts
    )
    assert any(
        20 in (
            item["devices"]["2960-24TT"]["rows"][0]["forwarding_vlans"] or []
        )
        for item in attempts
    )
    assert not any(
        20 in (
            item["devices"]["2960-24TT"]["rows"][0]["forwarding_vlans"] or []
        )
        and item["devices"]["2960-24TT"]["device_identity_provenance"]
        == "confirmed_unique"
        for item in attempts
    )
    assert "stp_application" not in evidence
    assert evidence["cleanup"]["verified"] is True
    assert evidence["cleanup"]["first"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["second"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["realtime"]["verified_realtime"] is True


def test_second_live_verifies_exact_model_pvst_configuration_and_state():
    assert hashlib.sha256(SECOND_LIVE_EVIDENCE.read_bytes()).hexdigest() == (
        "b7096988c199092e3ff187a0b047e6fb5e285e9607aa9999f8d57c47366df5ee"
    )
    evidence = json.loads(SECOND_LIVE_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["repository"]["head"] == (
        "71fae1c74878eee2d9fd8ac9330c11c781e0f155"
    )
    assert evidence["verified"] is True
    assert evidence["qualification_errors"] == []
    assert {
        item["action_id"]: item["applied"]
        for item in evidence["stp_application"]
    } == {
        "pvst/stp/primary": True,
        "pvst/stp/secondary": True,
        "pvst/stp/edge": True,
    }
    assert {
        item["expectation_id"]: item["status"]
        for item in evidence["stp_verification"]
    } == {
        "pvst/verify/primary": "verified",
        "pvst/verify/secondary": "verified",
    }
    assert all(
        item["fresh_evidence"]
        and all(value == "verified" for value in item["fields"].values())
        for item in evidence["stp_verification"]
    )
    terminal = evidence["stp_convergence"]["attempts"][-1]["devices"]
    primary = next(
        item for item in terminal["3560-24PS"]["instances"]
        if item["vlan_id"] == 20
    )
    secondary = next(
        item for item in terminal["2960-24TT"]["instances"]
        if item["vlan_id"] == 20
    )
    assert primary["root_is_local"] is True
    assert primary["bridge_base_priority"] == 24576
    assert secondary["root_is_local"] is False
    assert secondary["bridge_base_priority"] == 28672
    assert secondary["root_address"] == primary["bridge_address"]
    assert secondary["root_port"] == "GigabitEthernet0/1"
    assert evidence["edge_policy_qualification"]["mutation_status"] is True
    assert evidence["cleanup"]["verified"] is True
    assert evidence["cleanup"]["first"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["second"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["realtime"]["verified_realtime"] is True


def test_third_live_verifies_floor3_model_state_and_behavior_observers():
    assert hashlib.sha256(THIRD_LIVE_EVIDENCE.read_bytes()).hexdigest() == (
        "1de1d5d8b3b3da2dfa7264689daf42af52b8b6b3493111165b5345136a19165b"
    )
    evidence = json.loads(THIRD_LIVE_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["repository"]["head"] == (
        "29afd03bdd215d16b5d2e7c9eef5ea53e4a521c1"
    )
    assert evidence["verified"] is True
    assert evidence["qualification_errors"] == []
    assert evidence["qualified_models"] == {
        "3560-24PS": {
            "stp_pvst_config": "supported",
            "stp_state": "supported",
            "stp_behavior": "supported",
        },
        "2960-24TT": {
            "stp_pvst_config": "supported",
            "stp_state": "supported",
            "stp_behavior": "supported",
        },
    }
    observations = {
        item["expectation_id"]: item
        for item in evidence["stp_verification"]
    }
    assert set(observations) == {
        "pvst/verify/primary",
        "pvst/verify/secondary",
        "pvst/verify/primary-behavior",
        "pvst/verify/secondary-behavior",
    }
    for item in observations.values():
        assert item["status"] == "verified"
        assert item["fresh_evidence"] is True
        assert all(value == "verified" for value in item["fields"].values())
    for identifier in (
        "pvst/verify/primary-behavior",
        "pvst/verify/secondary-behavior",
    ):
        assert observations[identifier]["stage"] == "behavior"
        assert observations[identifier]["evidence_method"] == (
            "fresh_show_spanning_tree_stable_roles"
        )
    assert evidence["cleanup"]["verified"] is True
    assert evidence["cleanup"]["first"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["second"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["realtime"]["verified_realtime"] is True


def test_fourth_live_reaches_3650_but_expires_at_primary_behavior_boundary():
    assert hashlib.sha256(FOURTH_LIVE_EVIDENCE.read_bytes()).hexdigest() == (
        "e1eac60ca0b304fa6b26a9fb233de4b9e540ab5f8371279a5b86d1db8ac5832c"
    )
    evidence = json.loads(FOURTH_LIVE_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["repository"]["head"] == (
        "c61ee6626d6536be49b986bbd2fae72c78c29cf2"
    )
    assert evidence["verified"] is False
    assert all(item["applied"] for item in evidence["stp_application"])
    assert len(evidence["stp_application"]) == 5
    observations = {
        item["expectation_id"]: item
        for item in evidence["stp_verification"]
    }
    assert all(
        observations[identifier]["status"] == "verified"
        for identifier in (
            "pvst/verify/primary",
            "pvst/verify/secondary",
            "pvst/verify/tertiary",
            "pvst/verify/secondary-behavior",
            "pvst/verify/tertiary-behavior",
        )
    )
    primary_behavior = observations["pvst/verify/primary-behavior"]
    assert primary_behavior["status"] == "failed"
    assert primary_behavior["convergence"]["attempts"] == 4
    assert evidence["qualification_errors"] == [
        "pvst/verify/primary-behavior: status is failed",
    ]
    assert evidence["cleanup"]["verified"] is True
    assert evidence["cleanup"]["first"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["second"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["realtime"]["verified_realtime"] is True


def test_fifth_live_verifies_the_exact_three_model_typed_boundary():
    assert hashlib.sha256(FIFTH_LIVE_EVIDENCE.read_bytes()).hexdigest() == (
        "3e1b9e4fc2a4eab5e26622250eec4a724a3e5dd029406f510730d485a1550edd"
    )
    evidence = json.loads(FIFTH_LIVE_EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["schema"] == "stp-pvst-exact-model-qualification-v3"
    assert evidence["repository"] == {
        "branch": "feature/runtime-ripv2",
        "upstream": "personal/feature/runtime-ripv2",
        "head": "ed386bcd37f52854e0b966cb1a1da248337fbb00",
        "error": "",
    }
    assert evidence["loaded_namespaces"] == ["packet_tracer_mcp"]
    assert evidence["import_isolation"]["state"] == "ISOLATED"
    assert evidence["verified"] is True
    assert evidence["qualification_errors"] == []

    actions = evidence["plan"]["stp_actions"]
    global_actions = [
        item for item in actions if item["action_type"] == "configure_stp"
    ]
    edge_actions = [
        item for item in actions
        if item["action_type"] == "configure_stp_edge_port"
    ]
    assert {
        (item["model"], item["required_capability"])
        for item in global_actions
    } == {
        ("3560-24PS", "stp_pvst_config"),
        ("2960-24TT", "stp_pvst_config"),
        ("3650-24PS", "stp_pvst_config"),
    }
    assert {
        (item["model"], item["required_capability"])
        for item in edge_actions
    } == {
        ("3560-24PS", "stp_edge_config"),
        ("3650-24PS", "stp_edge_config"),
    }
    assert len(evidence["stp_application"]) == 5
    assert all(item["applied"] for item in evidence["stp_application"])

    assert evidence["qualified_models"] == {
        "3560-24PS": {
            "stp_pvst_config": "supported",
            "stp_edge_config": "supported",
            "stp_state": "supported",
            "stp_behavior": "supported",
        },
        "2960-24TT": {
            "stp_pvst_config": "supported",
            "stp_edge_config": "unknown",
            "stp_state": "supported",
            "stp_behavior": "supported",
        },
        "3650-24PS": {
            "stp_pvst_config": "supported",
            "stp_edge_config": "supported",
            "stp_state": "supported",
            "stp_behavior": "supported",
        },
    }
    observations = {
        item["expectation_id"]: item
        for item in evidence["stp_verification"]
    }
    assert len(observations) == 6
    assert all(
        item["status"] == "verified"
        and item["fresh_evidence"] is True
        and all(value == "verified" for value in item["fields"].values())
        for item in observations.values()
    )
    for identifier in (
        "pvst/verify/primary-behavior",
        "pvst/verify/secondary-behavior",
        "pvst/verify/tertiary-behavior",
    ):
        convergence = observations[identifier]["convergence"]
        assert convergence["attempts"] == 2
        assert convergence["details"]["stable_samples_required"] == 2
        assert convergence["details"]["stable_samples_observed"] == 2
        assert convergence["details"]["transitions"]

    assert evidence["cleanup"]["verified"] is True
    assert evidence["cleanup"]["first"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["first"]["link_count"] == 0
    assert evidence["cleanup"]["second"]["semantic_device_count"] == 0
    assert evidence["cleanup"]["second"]["link_count"] == 0
    assert evidence["cleanup"]["realtime"]["verified_realtime"] is True
