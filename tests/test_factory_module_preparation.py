"""Factory-module policy, index-native discovery, mutation and wiring."""

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
REAL_NULL_ABORT = '{"found":false,"error":"Error: missing module"}'


def _descriptor(
    model: str,
    slots: tuple[int, ...],
    *,
    model_observed: bool = True,
    physical_views: tuple[tuple[int, bool], ...] = (),
) -> dict:
    return {
        "model": model,
        "model_observed": model_observed,
        "slot_count": len(slots),
        "slots": [
            {"index": index, "module_type": module_type}
            for index, module_type in enumerate(slots)
        ],
        "physical_views": [
            {"index": index, "slot_num": slot_num, "module_added": added}
            for index, (slot_num, added) in enumerate(physical_views)
        ],
    }


def _module(
    slots: tuple[int, ...] = (),
    entries: tuple[dict, ...] = (),
    *,
    model: str = "",
    model_observed: bool = True,
    physical_views: tuple[tuple[int, bool], ...] = (),
) -> dict:
    return {
        "descriptor": _descriptor(
            model,
            slots,
            model_observed=model_observed,
            physical_views=physical_views,
        ),
        "slot_count": len(slots),
        "slots": [
            {"index": index, "module_type": module_type}
            for index, module_type in enumerate(slots)
        ],
        "module_count": len(entries),
        "module_entries": list(entries),
    }


def _present(index: int, module: dict) -> dict:
    return {"index": index, "state": "present", "module": module}


def _unknown(index: int, reason: str = "null") -> dict:
    return {"index": index, "state": "unknown", "reason": reason}


def _runtime_observation(
    *,
    installed: bool = False,
    multiple: bool = False,
    sparse_noncompatible: bool = False,
    occupied: bool = False,
    unknown_compatible: bool = False,
    installed_identity_observed: bool = True,
) -> str:
    if multiple:
        slots = (4, 4)
        entries: tuple[dict, ...] = ()
    elif installed:
        slots = (18, 4)
        entries = (
            _present(0, _module(model="BUILTIN")),
            _present(1, _module(
                model="AC-POWER-SUPPLY",
                model_observed=installed_identity_observed,
            )),
        )
    elif occupied or unknown_compatible:
        slots = (4,)
        if unknown_compatible:
            entries = (_unknown(0),)
        else:
            entries = (_present(0, _module(model="OTHER-MODULE")),)
    else:
        slots = (18, 4)
        entries = (
            _unknown(0)
            if sparse_noncompatible
            else _present(0, _module(model="BUILTIN")),
        )
    root = _module(
        slots,
        entries,
        model="CHASSIS",
        physical_views=tuple((index, False) for index in range(len(slots))),
    )
    return json.dumps({
        "found": True,
        "name": "SW",
        "model": "3650-24PS",
        "supported_modules_raw": ["AC-POWER-SUPPLY"],
        "device_descriptor_root": _descriptor("CHASSIS", slots),
        "root": root,
    })


def _installation_response(*, native_ack: bool | None = True) -> str:
    return json.dumps({
        "attempted": True,
        "requested_identity": "AC-POWER-SUPPLY",
        "native_ack": native_ack,
        "power_was_on": True,
        "power_restored": True,
        "target": {
            "container_ordinal": 0,
            "index": 1,
            "module_type": 4,
        },
        "error": "",
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
    assert requirement.expected_available_watts_before == 0.0
    assert requirement.expected_available_watts == 390.0
    assert factory_module_requirement_for("3560-24PS", BUILD) is None

    with pytest.raises(FactoryModulePolicyError, match="exact Packet Tracer build"):
        factory_module_requirement_for("3650-24PS", "9.0.1.9999")


def test_resolver_selects_one_compatible_index_without_any_slot_path() -> None:
    transport = _Replies(_runtime_observation())
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.observed
    assert observation.target_determined
    assert observation.target_container_ordinal == 0
    assert observation.target_index == 1
    assert len(observation.candidate_targets) == 1
    assert observation.candidate_targets[0].index == 1
    assert not observation.already_prepared
    assert observation.supported_modules_raw == ["AC-POWER-SUPPLY"]
    assert observation.descriptor_evidence_observed
    assert all(not hasattr(slot, "slot_path") for slot in observation.slots)
    assert "getSlotPath" not in transport.scripts[0]
    assert "getModuleNumber" not in transport.scripts[0]


def test_sparse_null_module_entry_is_unknown_and_does_not_abort_other_slots() -> None:
    transport = _Replies(_runtime_observation(sparse_noncompatible=True))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.observed
    assert observation.target_determined
    assert observation.target_index == 1
    assert len(observation.sparse_entries) == 1
    assert observation.sparse_entries[0].container_ordinal == 0
    assert observation.sparse_entries[0].module_index == 0
    assert observation.slots[0].state.value == "unknown"
    assert observation.slots[1].state.value == "empty"


def test_physical_view_flags_are_recorded_but_do_not_select_authority() -> None:
    payload = json.loads(_runtime_observation())
    payload["root"]["descriptor"]["physical_views"][1]["module_added"] = True
    transport = _Replies(json.dumps(payload))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.target_determined
    assert observation.target_index == 1
    assert observation.slots[1].state.value == "empty"
    diagnostic = observation.slots[1].container_descriptor
    assert diagnostic is not None
    assert diagnostic.physical_views[1].slot_num == 1
    assert diagnostic.physical_views[1].module_added is True


def test_real_null_abort_regression_is_retained_as_raw_negative_evidence() -> None:
    transport = _Replies(REAL_NULL_ABORT)
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert not observation.observed
    assert not observation.target_determined
    assert observation.raw_response == REAL_NULL_ABORT
    assert "exact device" in observation.message


@pytest.mark.parametrize(
    "raw,reason",
    [
        (_runtime_observation(multiple=True), "indistinguishable"),
        (_runtime_observation(occupied=True), "occupied"),
        (_runtime_observation(unknown_compatible=True), "unknown"),
        ("{not-json", "malformed"),
    ],
)
def test_non_unique_occupied_unknown_or_malformed_compatible_slots_refuse_mutation(
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
    assert all(".addModuleAt(" not in script for script in transport.scripts)


def _dual_bay(entries: tuple[dict, ...]) -> str:
    """Two compatible PSU-type bays, the real dual-supply 3650 shape."""

    root = _module((4, 4), entries, model="CHASSIS")
    return json.dumps({
        "found": True,
        "name": "SW",
        "model": "3650-24PS",
        "supported_modules_raw": ["AC-POWER-SUPPLY"],
        "device_descriptor_root": _descriptor("CHASSIS", (4, 4)),
        "root": root,
    })


def test_dual_bay_with_one_empty_index_still_resolves_one_target() -> None:
    """A second compatible bay does not make the single empty index ambiguous."""

    transport = _Replies(_dual_bay((_present(0, _module(model="COVER-PLATE")),)))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.observed
    assert observation.target_determined
    assert not observation.already_prepared
    assert observation.target_container_ordinal == 0
    assert observation.target_index == 1
    assert len(observation.candidate_targets) == 1


def test_dual_bay_already_holding_the_required_module_is_already_prepared() -> None:
    transport = _Replies(_dual_bay((
        _present(0, _module(model="AC-POWER-SUPPLY")),
    )))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.already_prepared
    assert observation.target_determined
    assert observation.target_index == 0
    assert len(observation.installed_targets) == 1
    with pytest.raises(RuntimeError, match="already present"):
        preparer.install_required_module(observation)
    assert len(transport.scripts) == 1


def test_dual_bay_with_two_empty_indexes_refuses_as_indistinguishable() -> None:
    transport = _Replies(_dual_bay(()))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.observed
    assert not observation.target_determined
    assert "indistinguishable" in observation.message
    with pytest.raises(RuntimeError):
        preparer.install_required_module(observation)


def test_dual_bay_with_an_unreadable_compatible_index_refuses() -> None:
    """An unknown bay could already hold the required module; never insert."""

    for entries in (
        (_unknown(0),),
        (_present(0, _module(model="", model_observed=False)),),
    ):
        transport = _Replies(_dual_bay(entries))
        preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

        observation = preparer.observe_required_module("SW", "3650-24PS")

        assert observation.observed
        assert not observation.target_determined
        assert not observation.already_prepared
        assert "unknown" in observation.message
        with pytest.raises(RuntimeError):
            preparer.install_required_module(observation)
        assert all(".addModuleAt(" not in s for s in transport.scripts)


def test_malformed_module_and_slot_types_fail_closed() -> None:
    payload = json.loads(_runtime_observation())
    payload["root"]["slots"][1]["module_type"] = "4"
    transport = _Replies(json.dumps(payload))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert not observation.target_determined
    assert "wrongly typed" in observation.message


@pytest.mark.parametrize("absent", ["null", "missing"])
def test_unobservable_device_descriptor_root_is_diagnostic_absence_only(
    absent: str,
) -> None:
    """PT may not expose the descriptor root; that never aborts the tree."""

    payload = json.loads(_runtime_observation())
    if absent == "null":
        payload["device_descriptor_root"] = None
    else:
        payload.pop("device_descriptor_root")
    transport = _Replies(json.dumps(payload))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.observed
    assert observation.target_determined
    assert observation.target_container_ordinal == 0
    assert observation.target_index == 1
    assert observation.device_descriptor_root is None
    assert not observation.descriptor_evidence_observed


def test_present_but_malformed_device_descriptor_root_still_fails_closed() -> None:
    payload = json.loads(_runtime_observation())
    payload["device_descriptor_root"]["slots"][0]["module_type"] = "18"
    transport = _Replies(json.dumps(payload))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert not observation.observed
    assert not observation.target_determined
    assert "wrongly typed" in observation.message


def test_installation_is_one_shot_and_native_true_requires_readback() -> None:
    transport = _Replies(
        _runtime_observation(),
        _installation_response(),
        _runtime_observation(installed=True),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS")

    installation = preparer.install_required_module(before)

    assert installation.requested_identity == "AC-POWER-SUPPLY"
    assert installation.native_ack is True
    assert not hasattr(installation, "verified")
    verification = preparer.verify_required_module(before, installation)
    assert verification.slot_container_effect
    assert verification.inventory_coherent
    assert verification.installed_identity_observed == "AC-POWER-SUPPLY"
    assert verification.installed_identity_matches is True
    assert verification.verified
    assert sum(".addModuleAt(" in script for script in transport.scripts) == 1
    assert all(".addModule(" not in script for script in transport.scripts)

    with pytest.raises(RuntimeError, match="already attempted"):
        preparer.install_required_module(before)
    assert sum(".addModuleAt(" in script for script in transport.scripts) == 1


@pytest.mark.parametrize(
    "raw,native_ack",
    [
        (_installation_response(native_ack=False), False),
        (None, None),
        ("{malformed", None),
    ],
    ids=["native-false", "timeout", "malformed"],
)
def test_non_acceptance_is_never_replayed_but_readback_is_preserved(
    raw: str | None,
    native_ack: bool | None,
) -> None:
    transport = _Replies(
        _runtime_observation(),
        raw,
        _runtime_observation(installed=True),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS")

    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert installation.native_ack is native_ack
    assert verification.slot_container_effect
    assert verification.installed_identity_matches is True
    assert sum(".addModuleAt(" in script for script in transport.scripts) == 1


def test_native_true_without_slot_container_effect_is_not_verified() -> None:
    transport = _Replies(
        _runtime_observation(),
        _installation_response(),
        _runtime_observation(),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS")

    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert installation.native_ack is True
    assert not verification.slot_container_effect
    assert not verification.verified
    assert sum(".addModuleAt(" in script for script in transport.scripts) == 1


def test_unobservable_post_install_identity_is_explicit_not_invented() -> None:
    transport = _Replies(
        _runtime_observation(),
        _installation_response(),
        _runtime_observation(
            installed=True,
            installed_identity_observed=False,
        ),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS")

    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert verification.slot_container_effect
    assert verification.inventory_coherent
    assert verification.installed_identity_observed is None
    assert verification.installed_identity_matches is None
    assert not verification.verified


def test_3560_preparation_is_an_exact_noop_without_transport_access() -> None:
    transport = _Replies()
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    result = preparer.prepare_required_modules("SW", "3560-24PS")

    assert result.ready
    assert not result.required
    assert result.observation is None
    assert transport.scripts == []
    assert preparer.operations == ()


def test_power_hypothesis_requires_inventory_effect_and_exact_delta() -> None:
    transport = _Replies(
        _runtime_observation(),
        _installation_response(),
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

    assert result.power_effect
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


def _node_descriptor_factory() -> str:
    return (
        "function makeDescriptor(model,slots,views){return {"
        "getModel:function(){return model;},"
        "getSlotCount:function(){return slots.length;},"
        "getSlotTypeAt:function(i){return slots[i];},"
        "getModulePhysicalViewCount:function(){return views.length;},"
        "getModulePhysicalViewAt:function(i){return views[i];}};}"
        "function makeView(slot,added){return {"
        "getSlotNum:function(){return slot;},"
        "getModuleAdded:function(){return added;}};}"
    )


def _node_module_factory() -> str:
    return (
        "function makeModule(slots,entries,model){return {"
        "getDescriptor:function(){return makeDescriptor(model,slots,"
        "slots.map(function(_,i){return makeView(i,false);}));},"
        "getSlotCount:function(){return slots.length;},"
        "getSlotTypeAt:function(i){return slots[i];},"
        "getModuleCount:function(){return entries.length;},"
        "getModuleAt:function(i){return entries[i];},"
        "addModuleAt:function(model,index){return false;}};}"
    )


def test_observation_javascript_uses_official_indexed_api_and_tolerates_null() -> None:
    name = 'SW";global.injected=true;//'
    script = factory_module_runtime._observe_module_slots_js(name)
    source = (
        "const assert=require('assert');let reported='';global.injected=false;"
        + _node_descriptor_factory()
        + _node_module_factory()
        + "const root=makeModule([18,4],[null],'CHASSIS');"
        "const deviceDescriptor={getRootModule:function(){return "
        "makeDescriptor('CHASSIS',[18,4],[]);}};"
        "const device={getName:function(){return " + json.dumps(name) + ";},"
        "getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},"
        "getDescriptor:function(){return deviceDescriptor;},"
        "getSupportedModule:function(){return ['AC-POWER-SUPPLY'];}};"
        "global.ipc={network:function(){return {getDevice:function(value){"
        "assert.equal(value," + json.dumps(name) + ");return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "assert.equal(global.injected,false);console.log(reported);"
    )

    payload = json.loads(_run_node(source))

    assert payload["found"] is True
    assert payload["root"]["module_entries"][0]["state"] == "unknown"
    assert payload["root"]["module_entries"][0]["reason"] == "null"
    assert payload["supported_modules_raw"] == ["AC-POWER-SUPPLY"]
    assert payload["device_descriptor_root"]["slots"][1]["module_type"] == 4
    for method in (
        "getSlotCount", "getSlotTypeAt", "getModuleCount", "getModuleAt",
        "getDescriptor", "getRootModule", "getSupportedModule",
        "getModulePhysicalViewCount", "getModulePhysicalViewAt",
        "getSlotNum", "getModuleAdded",
    ):
        assert method in script
    assert "getSlotPath" not in script
    assert "getModuleNumber" not in script
    assert ".addModuleAt(" not in script


def test_install_javascript_rediscovers_target_and_calls_add_module_at_once() -> None:
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
        + _node_descriptor_factory()
        + _node_module_factory()
        + "const entries=[makeModule([],[],'BUILTIN')];"
        "const root=makeModule([18,4],entries,'CHASSIS');"
        "root.addModuleAt=function(model,index){calls++;"
        "assert.equal(model,'AC-POWER-SUPPLY');assert.equal(index,1);"
        "entries.push(makeModule([],[],'AC-POWER-SUPPLY'));return true;};"
        "const device={getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},getPower:function(){return power;},"
        "setPower:function(value){power=value;powers.push(value);},skipBoot:function(){}};"
        "global.ipc={network:function(){return {getDevice:function(value){"
        "assert.equal(value,'SW');return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "assert.equal(calls,1);assert.deepEqual(powers,[false,true]);"
        "console.log(reported);"
    )

    payload = json.loads(_run_node(source))

    assert payload == {
        "attempted": True,
        "requested_identity": "AC-POWER-SUPPLY",
        "native_ack": True,
        "power_was_on": True,
        "power_restored": True,
        "target": {"container_ordinal": 0, "index": 1, "module_type": 4},
        "error": "",
    }
    assert script.count(".addModuleAt(") == 1
    assert ".addModule(" not in script
    assert "var __index=1" not in script


def test_install_javascript_rederives_the_same_dual_bay_target_in_node() -> None:
    """The JS revalidation must agree with Python on the dual-bay rule."""

    transport = _Replies(_dual_bay((_present(0, _module(model="COVER-PLATE")),)))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    observation = preparer.observe_required_module("SW", "3650-24PS")
    assert observation.target_determined and observation.target_index == 1
    requirement = factory_module_requirement_for("3650-24PS", BUILD)
    script = factory_module_runtime._install_factory_module_js(
        observation,
        requirement,
    )
    source = (
        "const assert=require('assert');let reported='',calls=0,power=true,powers=[];"
        + _node_descriptor_factory()
        + _node_module_factory()
        + "const entries=[makeModule([],[],'COVER-PLATE')];"
        "const root=makeModule([4,4],entries,'CHASSIS');"
        "root.addModuleAt=function(model,index){calls++;"
        "assert.equal(model,'AC-POWER-SUPPLY');assert.equal(index,1);"
        "entries.push(makeModule([],[],'AC-POWER-SUPPLY'));return true;};"
        "const device={getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},getPower:function(){return power;},"
        "setPower:function(value){power=value;powers.push(value);},skipBoot:function(){}};"
        "global.ipc={network:function(){return {getDevice:function(){return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "assert.equal(calls,1);assert.deepEqual(powers,[false,true]);"
        "console.log(reported);"
    )

    payload = json.loads(_run_node(source))

    assert payload["attempted"] is True
    assert payload["native_ack"] is True
    assert payload["target"] == {
        "container_ordinal": 0, "index": 1, "module_type": 4,
    }
    assert script.count(".addModuleAt(") == 1


def test_install_javascript_refuses_a_second_bay_that_became_unreadable() -> None:
    """If the sibling bay turns unknown before mutating, never insert."""

    transport = _Replies(_dual_bay((_present(0, _module(model="COVER-PLATE")),)))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    observation = preparer.observe_required_module("SW", "3650-24PS")
    requirement = factory_module_requirement_for("3650-24PS", BUILD)
    script = factory_module_runtime._install_factory_module_js(
        observation,
        requirement,
    )
    source = (
        "let reported='',calls=0,power=true;"
        + _node_descriptor_factory()
        + _node_module_factory()
        # getModuleAt(0) now returns null: unknown occupancy, not empty.
        + "const entries=[null];"
        "const root=makeModule([4,4],entries,'CHASSIS');"
        "root.addModuleAt=function(){calls++;return true;};"
        "const device={getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},getPower:function(){return power;},"
        "setPower:function(value){power=value;},skipBoot:function(){}};"
        "global.ipc={network:function(){return {getDevice:function(){return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "console.log(JSON.stringify({calls:calls,result:JSON.parse(reported)}));"
    )

    payload = json.loads(_run_node(source))

    assert payload["calls"] == 0
    assert payload["result"]["attempted"] is False
    assert payload["result"]["error"] == "installation precondition changed"


def test_install_javascript_refuses_when_the_observed_inventory_changed() -> None:
    before_transport = _Replies(_runtime_observation())
    preparer = PacketTracerFactoryModulePreparer(before_transport, BUILD)
    observation = preparer.observe_required_module("SW", "3650-24PS")
    requirement = factory_module_requirement_for("3650-24PS", BUILD)
    script = factory_module_runtime._install_factory_module_js(
        observation,
        requirement,
    )
    source = (
        "let reported='',calls=0,power=true;"
        + _node_descriptor_factory()
        + _node_module_factory()
        + "const entries=[makeModule([],[],'CHANGED')];"
        "const root=makeModule([18,4],entries,'CHASSIS');"
        "root.addModuleAt=function(){calls++;return true;};"
        "const device={getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},getPower:function(){return power;},"
        "setPower:function(value){power=value;},skipBoot:function(){}};"
        "global.ipc={network:function(){return {getDevice:function(){return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "console.log(JSON.stringify({calls:calls,result:JSON.parse(reported)}));"
    )

    payload = json.loads(_run_node(source))

    assert payload["calls"] == 0
    assert payload["result"]["attempted"] is False
    assert payload["result"]["native_ack"] is None
    assert payload["result"]["error"] == "installation precondition changed"
