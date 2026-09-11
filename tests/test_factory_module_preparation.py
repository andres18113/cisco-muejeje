"""Factory-module policy, discovery, one-shot mutation and product wiring."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    MutationDisposition,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan
from src.packet_tracer_mcp.infrastructure.catalog.factory_modules import (
    FactoryModulePolicyError,
    factory_module_requirement_for,
)
from src.packet_tracer_mcp.infrastructure.execution.factory_module_preparation import (
    FactoryModuleOperation,
    PacketTracerFactoryModulePreparer,
    classify_factory_power_hypothesis,
)
from src.packet_tracer_mcp.infrastructure.execution import (
    factory_module_preparation as factory_module_runtime,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    PoEInlineTable,
)
from src.packet_tracer_mcp.infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)


BUILD = "9.0.1.0858"


def _node(
    path: str,
    number: int,
    module_type: int,
    *,
    slots: tuple[int, ...] = (),
    children: tuple[dict, ...] = (),
    model: str = "",
    descriptor_observed: bool = True,
) -> dict:
    return {
        "slot_path": path,
        "module_number": number,
        "module_type": module_type,
        "descriptor_model": model,
        "descriptor_model_observed": descriptor_observed,
        "slots": [
            {"index": index, "module_type": value}
            for index, value in enumerate(slots)
        ],
        "children": list(children),
    }


def _runtime_observation(*, installed: bool = False, ambiguous: bool = False,
                         unknown_other_bay: bool = False,
                         blank_other_bay: bool = False) -> str:
    bay_children: list[dict] = [
        _node("2/0", 0, 30, model="GLC-T"),
    ]
    if installed:
        bay_children.append(
            _node("2/4", 4, 4, model="AC-POWER-SUPPLY"),
        )
    if not ambiguous:
        bay_children.append(
            _node(
                "2/5",
                5,
                4,
                model=(
                    "" if unknown_other_bay or blank_other_bay
                    else "POWER-COVER-PLATE"
                ),
                descriptor_observed=not unknown_other_bay,
            ),
        )
    root = _node(
        "",
        -1,
        18,
        slots=(18, 18, 18),
        children=(
            _node("0", 0, 18),
            _node(
                "1",
                1,
                18,
                slots=(32, 32),
                children=(
                    _node("1/0", 0, 32, model="C3650-BUILTIN"),
                    _node("1/1", 1, 32, model="C3650-SFP-BUILTIN"),
                ),
            ),
            _node(
                "2",
                2,
                18,
                slots=(30, 30, 30, 30, 4, 4),
                children=tuple(bay_children),
            ),
        ),
    )
    return json.dumps({
        "found": True,
        "name": "SW",
        "model": "3650-24PS",
        "root": root,
    })


class _Replies:
    def __init__(self, *replies: str | None) -> None:
        self.replies = list(replies)
        self.scripts: list[str] = []

    def __call__(self, script: str, _timeout: float) -> str | None:
        self.scripts.append(script)
        if not self.replies:
            raise AssertionError("Unexpected Packet Tracer dispatch")
        return self.replies.pop(0)


def test_exact_build_model_policy_requires_one_3650_supply_and_leaves_3560() -> None:
    requirement = factory_module_requirement_for("3650-24PS", BUILD)

    assert requirement is not None
    assert requirement.device_model == "3650-24PS"
    assert requirement.packet_tracer_build == BUILD
    assert requirement.module_model == "AC-POWER-SUPPLY"
    assert requirement.module_type == 4
    assert requirement.required_count == 1
    assert requirement.expected_available_watts == 390.0
    assert factory_module_requirement_for("3560-24PS", BUILD) is None

    with pytest.raises(FactoryModulePolicyError, match="exact Packet Tracer build"):
        factory_module_requirement_for("3650-24PS", "9.0.1.9999")


def test_read_only_discovery_uses_the_documented_runtime_surface() -> None:
    transport = _Replies(_runtime_observation())
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.observed
    assert observation.target_determined
    assert observation.target_slot == "2/4"
    assert observation.candidate_slots == ("2/4",)
    assert not observation.already_prepared
    script = transport.scripts[0]
    for method in (
        "getRootModule", "getSlotCount", "getSlotTypeAt", "getModuleAt",
        "getModuleCount", "getModuleNumber", "getSlotPath", "getModuleType",
        "getDescriptor", "getModel",
    ):
        assert method in script
    assert ".addModule(" not in script
    assert preparer.operations == (FactoryModuleOperation.OBSERVE_MODULE_SLOTS,)


@pytest.mark.parametrize(
    "raw,reason",
    [
        (_runtime_observation(ambiguous=True), "indistinguishable"),
        (_runtime_observation(unknown_other_bay=True), "descriptor"),
        (_runtime_observation(blank_other_bay=True), "descriptor"),
        ("{not-json", "malformed"),
    ],
)
def test_ambiguous_or_malformed_slot_discovery_stops_before_mutation(
    raw: str,
    reason: str,
) -> None:
    transport = _Replies(raw)
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert not observation.target_determined
    assert reason in observation.message.casefold()
    with pytest.raises(RuntimeError):
        preparer.install_required_module(observation)
    assert len(transport.scripts) == 1
    assert all(".addModule(" not in script for script in transport.scripts)


def test_one_empty_type_four_slot_without_an_observed_path_scheme_is_refused() -> None:
    payload = json.loads(_runtime_observation(ambiguous=True))
    bays = payload["root"]["children"][2]
    bays["slots"] = [{"index": 0, "module_type": 4}]
    bays["children"] = []
    transport = _Replies(json.dumps(payload))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert not observation.target_determined
    assert "slot-path mapping" in observation.message
    assert ".addModule(" not in transport.scripts[0]


def test_installation_is_one_shot_and_true_requires_independent_verification() -> None:
    transport = _Replies(
        _runtime_observation(),
        json.dumps({
            "attempted": True,
            "native_accepted": True,
            "power_was_on": True,
            "power_restored": True,
        }),
        _runtime_observation(installed=True),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS")

    installation = preparer.install_required_module(before)

    assert installation.attempted
    assert installation.native_accepted is True
    assert not hasattr(installation, "verified")
    verification = preparer.verify_required_module(before, installation)
    assert verification.verified
    assert verification.caused_effect
    assert verification.after.already_prepared
    assert verification.after.installed_slots == ("2/4",)
    assert sum(".addModule(" in script for script in transport.scripts) == 1
    assert preparer.operations == (
        FactoryModuleOperation.OBSERVE_MODULE_SLOTS,
        FactoryModuleOperation.INSTALL_FACTORY_MODULE,
        FactoryModuleOperation.VERIFY_FACTORY_MODULE,
    )

    with pytest.raises(RuntimeError, match="already attempted"):
        preparer.install_required_module(before)
    assert sum(".addModule(" in script for script in transport.scripts) == 1


def test_lost_install_result_is_never_replayed_but_can_be_read_back() -> None:
    transport = _Replies(
        _runtime_observation(),
        None,
        _runtime_observation(installed=True),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS")

    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert installation.acknowledged is None
    assert verification.verified
    assert sum(".addModule(" in script for script in transport.scripts) == 1


def test_native_true_without_the_required_after_state_is_not_verified() -> None:
    transport = _Replies(
        _runtime_observation(),
        json.dumps({
            "attempted": True,
            "native_accepted": True,
            "power_was_on": True,
            "power_restored": True,
        }),
        _runtime_observation(),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS")

    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert installation.native_accepted is True
    assert not verification.verified
    assert not verification.caused_effect
    assert sum(".addModule(" in script for script in transport.scripts) == 1


def test_3560_preparation_is_an_exact_noop_without_transport_access() -> None:
    transport = _Replies()
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    result = preparer.prepare_required_modules("SW", "3560-24PS")

    assert result.ready
    assert not result.required
    assert result.observation is None
    assert transport.scripts == []
    assert preparer.operations == ()


def test_power_hypothesis_requires_the_verified_caused_effect_and_exact_delta() -> None:
    transport = _Replies(
        _runtime_observation(),
        json.dumps({
            "attempted": True,
            "native_accepted": True,
            "power_was_on": True,
            "power_restored": True,
        }),
        _runtime_observation(installed=True),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS")
    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)
    before_power = PoEInlineTable(
        summary_available_watts=0.0,
        summary_used_watts=0.0,
        summary_remaining_watts=0.0,
    )
    after_power = PoEInlineTable(
        summary_available_watts=390.0,
        summary_used_watts=0.0,
        summary_remaining_watts=390.0,
    )

    result = classify_factory_power_hypothesis(
        verification,
        before=before_power,
        after=after_power,
    )

    assert result.confirmed
    assert result.available_delta_watts == 390.0
    assert not classify_factory_power_hypothesis(
        verification,
        before=before_power,
        after=PoEInlineTable(
            summary_available_watts=389.0,
            summary_used_watts=0.0,
            summary_remaining_watts=389.0,
        ),
    ).confirmed


class _PreparationGate:
    def __init__(self, *, ready: bool) -> None:
        self.ready = ready
        self.calls: list[tuple[str, str]] = []

    def prepare_required_modules(self, device_name: str, device_model: str):
        self.calls.append((device_name, device_model))
        return SimpleNamespace(ready=self.ready, message="factory gate refused")


class _DeviceCreationTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, script: str, _timeout: float) -> str:
        self.calls.append(script)
        if "lwAddDevice(" in script:
            return json.dumps({"ack": True})
        return json.dumps({"found": False})


def test_product_device_creation_cannot_cross_a_refused_factory_gate() -> None:
    transport = _DeviceCreationTransport()
    gate = _PreparationGate(ready=False)
    runtime = PacketTracerPhysicalTopologyRuntime(
        transport,
        factory_module_preparer=gate,
    )
    device = DevicePlan(
        id="sw", name="SW", model="3650-24PS", category="switch",
    )

    mutation = runtime.ensure_device(device)

    assert gate.calls == [("SW", "3650-24PS")]
    assert mutation.disposition is MutationDisposition.FAILED
    assert mutation.inverse_available
    assert "factory gate refused" in mutation.message
    assert ".addModule(" not in inspect.getsource(runtime.ensure_module)


def test_poe3b_and_cp_live_compose_the_same_factory_preparer() -> None:
    root = Path(__file__).resolve().parents[1]
    session_source = (
        root / "src/packet_tracer_mcp/infrastructure/execution/poe3b_session.py"
    ).read_text(encoding="utf-8")
    cp_live_source = (
        root / "src/packet_tracer_mcp/adapters/cli/cp_scale_live.py"
    ).read_text(encoding="utf-8")

    assert "PacketTracerFactoryModulePreparer" in session_source
    assert "PacketTracerFactoryModulePreparer" in cp_live_source
    assert "factory_module_preparer=" in cp_live_source
    assert "AC-POWER-SUPPLY" not in session_source
    assert "AC-POWER-SUPPLY" not in cp_live_source


def _run_node(source: str) -> str:
    result = subprocess.run(
        ["node", "-e", source],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _node_module_factory() -> str:
    return (
        "function makeModule(path,number,type,slots,children,model){return {"
        "getSlotPath:function(){return path;},"
        "getModuleNumber:function(){return number;},"
        "getModuleType:function(){return type;},"
        "getDescriptor:function(){return {getModel:function(){return model;}};},"
        "getSlotCount:function(){return slots.length;},"
        "getSlotTypeAt:function(i){return slots[i];},"
        "getModuleCount:function(){return children.length;},"
        "getModuleAt:function(i){return children[i];}};}"
    )


def test_observation_javascript_executes_and_serializes_an_injected_name() -> None:
    name = 'SW";global.injected=true;//'
    script = factory_module_runtime._observe_module_slots_js(name)
    source = (
        "const assert=require('assert');let reported='';global.injected=false;"
        + _node_module_factory()
        + "const cover=makeModule('2/5',5,4,[],[],'POWER-COVER-PLATE');"
        "const bays=makeModule('2',2,18,[30,30,30,30,4,4],[cover],'');"
        "const root=makeModule('',-1,18,[18,18,18],["
        "makeModule('0',0,18,[],[],''),makeModule('1',1,18,[],[],''),bays],'');"
        "const device={getName:function(){return " + json.dumps(name) + ";},"
        "getModel:function(){return '3650-24PS';},getRootModule:function(){return root;}};"
        "global.ipc={network:function(){return {getDevice:function(value){"
        "assert.equal(value," + json.dumps(name) + ");return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "assert.equal(global.injected,false);console.log(reported);"
    )

    payload = json.loads(_run_node(source))

    assert payload["found"] is True
    assert payload["name"] == name
    assert payload["root"]["children"][2]["slots"][4]["module_type"] == 4


def test_install_javascript_power_cycles_and_calls_native_add_once() -> None:
    before_transport = _Replies(_runtime_observation())
    preparer = PacketTracerFactoryModulePreparer(before_transport, BUILD)
    observation = preparer.observe_required_module("SW", "3650-24PS")
    requirement = factory_module_requirement_for("3650-24PS", BUILD)
    script = factory_module_runtime._install_factory_module_js(
        observation,
        requirement,
    )
    source = (
        "const assert=require('assert');let reported='',calls=0,power=true,powers=[];"
        + _node_module_factory()
        + "const cover=makeModule('2/5',5,4,[],[],'POWER-COVER-PLATE');"
        "const children=[cover];const bays=makeModule('2',2,18,[30,30,30,30,4,4],children,'');"
        "const root=makeModule('',-1,18,[18,18,18],["
        "makeModule('0',0,18,[],[],''),makeModule('1',1,18,[],[],''),bays],'');"
        "const device={getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},getPower:function(){return power;},"
        "setPower:function(value){power=value;powers.push(value);},skipBoot:function(){},"
        "addModule:function(slot,type,model){calls++;assert.equal(slot,'2/4');"
        "assert.equal(type,4);assert.equal(model,'AC-POWER-SUPPLY');"
        "children.push(makeModule('2/4',4,4,[],[],'AC-POWER-SUPPLY'));return true;}};"
        "global.ipc={network:function(){return {getDevice:function(value){"
        "assert.equal(value,'SW');return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "assert.equal(calls,1);assert.deepEqual(powers,[false,true]);console.log(reported);"
    )

    payload = json.loads(_run_node(source))

    assert payload == {
        "attempted": True,
        "native_accepted": True,
        "power_was_on": True,
        "power_restored": True,
        "error": "",
    }
