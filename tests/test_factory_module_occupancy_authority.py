"""Exact-build occupancy authority established by the POE-3H live delta.

The committed bundle is the regression fixture.  These tests deliberately do
not restate its module tree or mutation response: they replay the exact wire
captures and alter only the one fact whose rejection is under test.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from src.packet_tracer_mcp.infrastructure.catalog.factory_modules import (
    factory_module_requirement_for,
)
from src.packet_tracer_mcp.infrastructure.execution.factory_module_contracts import (
    FactoryModuleSlotState,
)
from src.packet_tracer_mcp.infrastructure.execution.factory_module_preparation import (
    PacketTracerFactoryModulePreparer,
)
from src.packet_tracer_mcp.infrastructure.execution.factory_module_runtime import (
    _install_factory_module_js,
    _observation_guard,
)
from tests.support.factory_module_cases import (
    BUILD,
    DEVICE_MODEL,
    installation_response,
    module,
    present,
    target_payload,
)


ROOT = Path(__file__).resolve().parents[1]
LIVE_POE3H = (
    ROOT
    / "docs"
    / "reference"
    / "cp-scale"
    / "canonical-live-evidence"
    / "poe3b-router0-b-3650-11-psu-host-inventory-20260912T045537Z-766e4a93"
    / "evidence.json"
)
REQUIRED_IDENTITY = "AC-POWER-SUPPLY"


class _Replies:
    def __init__(self, *replies: str | None) -> None:
        self.replies = list(replies)
        self.scripts: list[str] = []

    def queue(self, *replies: str | None) -> None:
        self.replies.extend(replies)

    def __call__(self, script: str, _timeout: float) -> str | None:
        self.scripts.append(script)
        if not self.replies:
            raise AssertionError("Unexpected Packet Tracer dispatch")
        return self.replies.pop(0)


def _live_factory_wire() -> tuple[str, str, str, str]:
    bundle = json.loads(LIVE_POE3H.read_text(encoding="utf-8"))
    factory = bundle["factory_preparation"]
    return (
        factory["before"]["device_name"],
        factory["before"]["raw_response"],
        factory["installation"]["raw_response"],
        factory["verification"]["after"]["raw_response"],
    )


def _power_entries(raw: str) -> tuple[dict, list[dict]]:
    payload = json.loads(raw)
    power_container = payload["root"]["module_entries"][2]["module"]
    return payload, power_container["module_entries"]


def _run_node(source: str) -> str:
    completed = subprocess.run(
        ["node", "-e", source],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _module_tree_as_js(node: dict) -> str:
    descriptor = node["descriptor"]
    views = ",".join(
        "makeView(" + json.dumps(view["slot_num"]) + ","
        + json.dumps(view["module_added"]) + ")"
        for view in descriptor["physical_views"]
    )
    entries = ",".join(
        _module_tree_as_js(entry["module"])
        if entry["state"] == "present"
        else "null"
        for entry in node["module_entries"]
    )
    model = descriptor["model"] if descriptor["model_observed"] else ""
    return (
        "makeModule("
        + json.dumps([slot["module_type"] for slot in node["slots"]])
        + ",[" + entries + "],"
        + json.dumps(model)
        + ",[" + views + "])"
    )


def _prepare_live_delta(
    after_raw: str,
):
    device_name, before_raw, _live_installation, _live_after = _live_factory_wire()
    transport = _Replies(before_raw)
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module(
        device_name,
        DEVICE_MODEL,
        fresh_owned=True,
    )
    transport.queue(installation_response(before), after_raw)
    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)
    return before, installation, verification


def test_live_poe3h_false_physical_view_does_not_contradict_exact_psu_delta() -> None:
    """Reintroducing PhysicalView authority would recreate the LIVE false negative."""

    device_name, before_raw, installation_raw, after_raw = _live_factory_wire()
    transport = _Replies(before_raw, installation_raw, after_raw)
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    before = preparer.observe_required_module(
        device_name,
        DEVICE_MODEL,
        fresh_owned=True,
    )
    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert before.target is not None
    assert before.target.container_navigation_path == (2,)
    assert before.target.slot_index == 4
    assert before.target.module_type == 4
    assert installation.native_ack is True
    assert installation.target == before.target
    assert verification.occupancy_effect_verified
    assert verification.inventory_coherent
    assert verification.identity_observed
    assert verification.observed_identity == REQUIRED_IDENTITY
    assert verification.identity_matches is True
    assert verification.factory_requirement_verified
    assert verification.diagnostic_inconsistent_with_runtime
    after_target = next(
        slot
        for slot in verification.after.slots
        if slot.container_navigation_path == (2,) and slot.index == 4
    )
    assert after_target.state is FactoryModuleSlotState.OCCUPIED
    assert after_target.container_descriptor is not None
    assert after_target.container_descriptor.physical_views[4].module_added is False


def test_live_poe3h_initial_state_is_not_factory_authority_when_not_fresh_owned() -> None:
    """Applying the fresh semantic assumption to a preexisting device is a bug."""

    device_name, before_raw, _installation_raw, _after_raw = _live_factory_wire()
    preparer = PacketTracerFactoryModulePreparer(_Replies(before_raw), BUILD)

    observation = preparer.observe_required_module(
        device_name,
        DEVICE_MODEL,
        fresh_owned=False,
    )

    compatible = tuple(slot for slot in observation.slots if slot.module_type == 4)
    assert compatible
    assert all(slot.state is FactoryModuleSlotState.UNKNOWN for slot in compatible)
    assert not observation.target_determined
    assert observation.target is None
    assert "fresh-owned" in observation.message
    assert compatible[0].container_descriptor is not None
    assert compatible[0].container_descriptor.physical_views[4].module_added is False


def test_post_identity_different_from_the_exact_psu_is_a_hard_failure() -> None:
    """Accepting any observed target identity would admit the wrong module."""

    _device_name, _before_raw, _installation_raw, after_raw = _live_factory_wire()
    payload, entries = _power_entries(after_raw)
    entries[4]["module"]["descriptor"]["model"] = "POWER-COVER-PLATE"
    verification = _prepare_live_delta(json.dumps(payload))[2]

    assert verification.occupancy_effect_verified
    assert verification.inventory_coherent
    assert verification.identity_observed
    assert verification.observed_identity == "POWER-COVER-PLATE"
    assert verification.identity_matches is False
    assert not verification.factory_requirement_verified


def test_post_identity_unobservable_is_not_a_factory_pass_on_this_build() -> None:
    """The live build proved identity observable, so losing it must fail closed."""

    _device_name, _before_raw, _installation_raw, after_raw = _live_factory_wire()
    payload, entries = _power_entries(after_raw)
    entries[4]["module"]["descriptor"]["model_observed"] = False
    verification = _prepare_live_delta(json.dumps(payload))[2]

    assert verification.occupancy_effect_verified
    assert verification.inventory_coherent
    assert not verification.identity_observed
    assert verification.observed_identity is None
    assert verification.identity_matches is None
    assert not verification.factory_requirement_verified
    assert "not observable" in verification.message


def test_non_target_collection_drift_rejects_the_otherwise_exact_delta() -> None:
    """Ignoring entry 5 would permit a competing mutation beside the target."""

    _device_name, _before_raw, _installation_raw, after_raw = _live_factory_wire()
    payload, entries = _power_entries(after_raw)
    entries[5] = present(5, module(model="POWER-COVER-PLATE"))
    verification = _prepare_live_delta(json.dumps(payload))[2]

    assert verification.occupancy_effect_verified
    assert verification.identity_matches is True
    assert not verification.inventory_coherent
    assert not verification.factory_requirement_verified
    assert "non-target" in verification.message


def test_physical_view_changes_only_diagnostics_not_the_exact_guard() -> None:
    """Putting PhysicalView back in the guard would let diagnostics veto mutation."""

    device_name, before_raw, _installation_raw, _after_raw = _live_factory_wire()
    changed = json.loads(before_raw)
    views = changed["root"]["module_entries"][2]["module"]["descriptor"][
        "physical_views"
    ]
    for view in views:
        view["module_added"] = True
    preparer = PacketTracerFactoryModulePreparer(
        _Replies(before_raw, json.dumps(changed)),
        BUILD,
    )

    first = preparer.observe_required_module(
        device_name,
        DEVICE_MODEL,
        fresh_owned=True,
    )
    second = preparer.observe_required_module(
        device_name,
        DEVICE_MODEL,
        fresh_owned=True,
    )

    assert _observation_guard(first) == _observation_guard(second)
    assert [slot.state for slot in first.slots] == [slot.state for slot in second.slots]
    first_power = next(
        slot for slot in first.slots
        if slot.container_navigation_path == (2,) and slot.index == 4
    )
    second_power = next(
        slot for slot in second.slots
        if slot.container_navigation_path == (2,) and slot.index == 4
    )
    assert first_power.container_descriptor is not None
    assert second_power.container_descriptor is not None
    assert first_power.container_descriptor.physical_views != (
        second_power.container_descriptor.physical_views
    )


def test_physical_view_drift_cannot_veto_the_exact_javascript_mutation() -> None:
    """The emitted precondition guard must enforce the same authority as Python."""

    device_name, before_raw, _installation_raw, _after_raw = _live_factory_wire()
    payload = json.loads(before_raw)
    preparer = PacketTracerFactoryModulePreparer(_Replies(before_raw), BUILD)
    observation = preparer.observe_required_module(
        device_name,
        DEVICE_MODEL,
        fresh_owned=True,
    )
    for view in payload["root"]["module_entries"][2]["module"]["descriptor"][
        "physical_views"
    ]:
        view["module_added"] = True
    requirement = factory_module_requirement_for(DEVICE_MODEL, BUILD)
    assert requirement is not None
    script = _install_factory_module_js(observation, requirement)
    source = (
        "let calls=[],reported='',power=true;"
        "function makeView(slot,added){return {getSlotNum:function(){return slot;},"
        "getModuleAdded:function(){return added;}};}"
        "function makeDescriptor(model,slots,views){return {getModel:function(){"
        "return model;},getSlotCount:function(){return slots.length;},"
        "getSlotTypeAt:function(i){return slots[i];},"
        "getModulePhysicalViewCount:function(){return views.length;},"
        "getModulePhysicalViewAt:function(i){return views[i];}};}"
        "function makeModule(slots,entries,model,views){return {getDescriptor:function(){"
        "return makeDescriptor(model,slots,views);},getSlotCount:function(){"
        "return slots.length;},getSlotTypeAt:function(i){return slots[i];},"
        "getModuleCount:function(){return entries.length;},getModuleAt:function(i){"
        "return entries[i];},addModuleAt:function(m,i){calls.push([m,i]);return true;}};}"
        "const root=" + _module_tree_as_js(payload["root"]) + ";"
        "const device={getModel:function(){return " + json.dumps(DEVICE_MODEL) + ";},"
        "getRootModule:function(){return root;},getSupportedModule:function(){return "
        + json.dumps(payload["supported_modules_raw"])
        + ";},getPower:function(){return power;},setPower:function(v){power=v;},"
        "skipBoot:function(){}};"
        "global.ipc={network:function(){return {getDevice:function(){return device;}};}};"
        "global.reportResult=function(v){reported=v;};"
        + script
        + "console.log(JSON.stringify({calls:calls,result:JSON.parse(reported)}));"
    )

    result = json.loads(_run_node(source))

    assert result["calls"] == [[REQUIRED_IDENTITY, 4]]
    assert result["result"]["native_ack"] is True
    assert result["result"]["target"] == target_payload(observation.target)
