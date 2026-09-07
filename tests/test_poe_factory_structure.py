"""Factory metadata diagnoses supply isolation; it is never PoE evidence."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from src.packet_tracer_mcp.infrastructure.execution.poe_delivery_runtime import (
    PacketTracerPoEDeliveryFixtureRuntime,
)


def _factory_transport(*, adapter: object = False, null_child: bool = False):
    # Execute the generated artifact against the documented *descriptor* API.
    # No network, device mutation, or administrative power API is exposed.
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute the generated descriptor query")

    def send(script: str, timeout: float) -> str:
        fixture = """
const assert = require('node:assert/strict');
const child = {
  getModel: () => 'PT-HOST-NM-1CFE', getType: () => 6,
  isHotSwappable: () => false, getSlotCount: () => 0,
  getModuleCount: () => 0
};
const root = {
  getModel: () => 'AccessPoint-PT', getType: () => 18,
  isHotSwappable: () => false, getSlotCount: () => 1,
  getSlotTypeAt: i => { assert.equal(i, 0); return 6; },
  getModuleCount: () => 1,
  getModuleAt: i => { assert.equal(i, 0); return NULL_CHILD ? null : child; }
};
const ipc = { hardwareFactory: () => ({ devices: () => ({
  getDescriptor: (type, model) => {
    assert.equal(type, 7); assert.equal(model, 'AccessPoint-PT');
    return {
      getModel: () => 'AccessPoint-PT', getType: () => 7,
      isModuleTypeSupported: type => { assert.equal(type, 31); return ADAPTER; },
      getRootModule: () => root
    };
  }
}) }) };
const reportResult = value => process.stdout.write(value);
"""
        fixture = fixture.replace("NULL_CHILD", json.dumps(null_child)).replace(
            "ADAPTER", json.dumps(adapter),
        )
        result = subprocess.run(
            [node, "-e", fixture + script], capture_output=True, text=True,
            timeout=timeout, check=True,
        )
        return result.stdout

    return send


def test_exact_factory_structure_reads_descriptors_without_creating_a_fixture():
    runtime = PacketTracerPoEDeliveryFixtureRuntime(_factory_transport())

    result = runtime.observe_factory_structure("AccessPoint-PT", module_type=31)

    assert result == {
        "evidence_role": "FACTORY_STRUCTURE_ONLY_NOT_POWER_DELIVERY",
        "model": "AccessPoint-PT", "device_type": 7,
        "queried_module_type": 31, "module_type_supported": False,
        "max_depth": 12, "truncated": False,
        "root": {
            "model": "AccessPoint-PT", "module_type": 18,
            "hot_swappable": False, "slot_types": [6], "truncated": False,
            "modules": [{
                "model": "PT-HOST-NM-1CFE", "module_type": 6,
                "hot_swappable": False, "slot_types": [], "modules": [],
                "truncated": False,
            }],
        },
    }


@pytest.mark.parametrize("adapter,null_child", [(None, False), ("false", False), (False, True)])
def test_incomplete_factory_reads_are_not_negative_module_support(adapter, null_child):
    runtime = PacketTracerPoEDeliveryFixtureRuntime(
        _factory_transport(adapter=adapter, null_child=null_child),
    )
    with pytest.raises(RuntimeError):
        runtime.observe_factory_structure("AccessPoint-PT", module_type=31)


@pytest.mark.parametrize("model,module_type", [
    ('AP\";throw new Error("injected")//', 31),
    ("ap", 31),  # Catalog aliases are not exact Cisco factory model identities.
    ("AccessPoint-PT", True), ("AccessPoint-PT", -1),
])
def test_unknown_factory_identity_cannot_use_a_default_device_type(model, module_type):
    def no_dispatch(script, timeout):
        pytest.fail("invalid factory request must not reach Packet Tracer")

    runtime = PacketTracerPoEDeliveryFixtureRuntime(no_dispatch)
    with pytest.raises(ValueError):
        runtime.observe_factory_structure(model, module_type=module_type)


@pytest.mark.parametrize("payload", [
    None, "[]", "{}", '{"observed":false}',
    '{"observed":true,"model":"different","device_type":7}',
])
def test_unattributable_factory_response_is_not_a_structural_observation(payload):
    runtime = PacketTracerPoEDeliveryFixtureRuntime(lambda script, timeout: payload)
    with pytest.raises((RuntimeError, TimeoutError)):
        runtime.observe_factory_structure("AccessPoint-PT", module_type=31)


# Captured verbatim from Packet Tracer 9.0.1.0858 while reading the exact
# AccessPoint-PT descriptor: the chassis root and one nested module report an
# empty model. Attribution is carried by the top-level identity, not by a
# per-node model string, so an empty one is real metadata and not corruption.
PT_9_0_1_ACCESS_POINT_DESCRIPTOR = (
    '{"observed":true,"model":"AccessPoint-PT","device_type":7,'
    '"queried_module_type":31,"module_type_supported":false,'
    '"root":{"model":"","module_type":18,"hot_swappable":false,'
    '"slot_types":[6,18],"truncated":false,"modules":['
    '{"model":"PT-REPEATER-NM-1CFE","module_type":6,"hot_swappable":false,'
    '"slot_types":[],"modules":[],"truncated":false},'
    '{"model":"","module_type":18,"hot_swappable":false,'
    '"slot_types":[],"modules":[],"truncated":false}]}}'
)


def test_real_chassis_descriptor_with_empty_module_models_is_observed():
    runtime = PacketTracerPoEDeliveryFixtureRuntime(
        lambda script, timeout: PT_9_0_1_ACCESS_POINT_DESCRIPTOR,
    )

    result = runtime.observe_factory_structure("AccessPoint-PT", module_type=31)

    assert result["evidence_role"] == "FACTORY_STRUCTURE_ONLY_NOT_POWER_DELIVERY"
    assert result["module_type_supported"] is False
    assert result["root"]["model"] == ""
    assert result["root"]["slot_types"] == [6, 18]
    assert [item["model"] for item in result["root"]["modules"]] == [
        "PT-REPEATER-NM-1CFE", "",
    ]


@pytest.mark.parametrize("node_model", ["null", "5", "[]", "{}"])
def test_module_model_that_is_not_a_string_is_still_malformed(node_model):
    payload = PT_9_0_1_ACCESS_POINT_DESCRIPTOR.replace('"model":""', f'"model":{node_model}', 1)
    runtime = PacketTracerPoEDeliveryFixtureRuntime(lambda script, timeout: payload)

    with pytest.raises(RuntimeError):
        runtime.observe_factory_structure("AccessPoint-PT", module_type=31)


def _descriptor_payload(children: int, *, device_type: int = 7, echo: int | None = None):
    leaf = {"model": "", "module_type": 18, "hot_swappable": False,
            "slot_types": [], "modules": [], "truncated": False}
    return json.dumps({
        "observed": True, "model": "AccessPoint-PT",
        "device_type": device_type if echo is None else echo,
        "queried_module_type": 31, "module_type_supported": False,
        "root": {"model": "", "module_type": 18, "hot_swappable": False,
                 "slot_types": [], "truncated": False,
                 "modules": [dict(leaf) for _ in range(children)]},
    })


def test_descriptor_tree_larger_than_a_toy_bound_is_still_observed():
    # A real chassis has more than the 64 nodes the first bound allowed, so
    # that ceiling rejected genuine hardware as oversized.
    runtime = PacketTracerPoEDeliveryFixtureRuntime(
        lambda script, timeout: _descriptor_payload(200),
    )

    result = runtime.observe_factory_structure("AccessPoint-PT", module_type=31)

    assert len(result["root"]["modules"]) == 200


def test_descriptor_tree_beyond_the_bound_is_rejected():
    runtime = PacketTracerPoEDeliveryFixtureRuntime(
        lambda script, timeout: _descriptor_payload(4096),
    )

    with pytest.raises(RuntimeError):
        runtime.observe_factory_structure("AccessPoint-PT", module_type=31)


@pytest.mark.parametrize("device_type", [999, -1, 7.0, True, "16"])
def test_undocumented_device_type_never_reaches_packet_tracer(device_type):
    def no_dispatch(script, timeout):
        pytest.fail("an undocumented device type must not reach Packet Tracer")

    runtime = PacketTracerPoEDeliveryFixtureRuntime(no_dispatch)
    with pytest.raises(ValueError):
        runtime.observe_factory_structure(
            "3560-24PS", module_type=4, device_type=device_type,
        )


def test_documented_device_type_override_is_dispatched_and_echo_checked():
    sent: list[str] = []

    def send(script: str, timeout: float) -> str:
        sent.append(script)
        return json.dumps({
            "observed": True, "model": "3560-24PS", "device_type": 16,
            "queried_module_type": 4, "module_type_supported": True,
            "root": {"model": "", "module_type": 18, "hot_swappable": False,
                     "slot_types": [], "modules": [], "truncated": False},
        })

    runtime = PacketTracerPoEDeliveryFixtureRuntime(send)
    result = runtime.observe_factory_structure(
        "3560-24PS", module_type=4, device_type=16,
    )

    assert result["device_type"] == 16
    assert result["module_type_supported"] is True
    assert "16" in sent[0]


def test_device_type_override_still_requires_an_exact_echo():
    runtime = PacketTracerPoEDeliveryFixtureRuntime(
        lambda script, timeout: _descriptor_payload(1, echo=1),
    )

    with pytest.raises(RuntimeError):
        runtime.observe_factory_structure(
            "AccessPoint-PT", module_type=31, device_type=16,
        )


def _nested_payload(depth: int, *, truncated_at: int | None = None):
    node = {"model": "leaf", "module_type": 6, "hot_swappable": False,
            "slot_types": [], "modules": [], "truncated": False}
    for level in range(depth):
        node = {"model": f"n{level}", "module_type": 18, "hot_swappable": False,
                "slot_types": [6], "modules": [node],
                "truncated": truncated_at == level}
    return json.dumps({
        "observed": True, "model": "AccessPoint-PT", "device_type": 7,
        "queried_module_type": 31, "module_type_supported": False, "root": node,
    })


@pytest.mark.parametrize("max_depth", [-1, 13, 1.0, True, "2"])
def test_out_of_range_depth_never_reaches_packet_tracer(max_depth):
    def no_dispatch(script, timeout):
        pytest.fail("an out-of-range depth must not reach Packet Tracer")

    runtime = PacketTracerPoEDeliveryFixtureRuntime(no_dispatch)
    with pytest.raises(ValueError):
        runtime.observe_factory_structure(
            "AccessPoint-PT", module_type=31, max_depth=max_depth,
        )


def test_bounded_depth_reads_the_root_of_a_tree_too_large_to_walk_whole():
    # A 24-port switch descriptor overflows any walk of the entire tree, but
    # the root slot inventory is still readable and is what a supply question
    # actually needs.
    sent: list[str] = []

    def send(script: str, timeout: float) -> str:
        sent.append(script)
        return _nested_payload(1, truncated_at=0)

    runtime = PacketTracerPoEDeliveryFixtureRuntime(send)
    result = runtime.observe_factory_structure(
        "AccessPoint-PT", module_type=31, max_depth=1,
    )

    assert result["max_depth"] == 1
    assert result["truncated"] is True
    assert result["root"]["slot_types"] == [6]
    assert "1" in sent[0]


def test_a_complete_bounded_read_is_not_marked_truncated():
    runtime = PacketTracerPoEDeliveryFixtureRuntime(
        lambda script, timeout: _nested_payload(2),
    )

    result = runtime.observe_factory_structure(
        "AccessPoint-PT", module_type=31, max_depth=4,
    )

    assert result["truncated"] is False


def test_missing_truncation_marking_is_malformed():
    payload = json.loads(_nested_payload(1))
    del payload["root"]["truncated"]
    runtime = PacketTracerPoEDeliveryFixtureRuntime(
        lambda script, timeout: json.dumps(payload),
    )

    with pytest.raises(RuntimeError):
        runtime.observe_factory_structure("AccessPoint-PT", module_type=31)
