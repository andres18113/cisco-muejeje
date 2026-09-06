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
        "root": {
            "model": "AccessPoint-PT", "module_type": 18,
            "hot_swappable": False, "slot_types": [6],
            "modules": [{
                "model": "PT-HOST-NM-1CFE", "module_type": 6,
                "hot_swappable": False, "slot_types": [], "modules": [],
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
