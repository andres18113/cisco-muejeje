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
from src.packet_tracer_mcp.infrastructure.execution.factory_module_contracts import (
    FactoryModuleSlotState,
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
        # One added bay and one retrievable module: the only shape in which
        # Packet Tracer's two surfaces pin an identity to a slot. A second
        # retrievable child would leave the occupant of the added bay a guess,
        # which is what the measured build actually reports.
        slots = (18, 4)
        entries = (
            _present(0, _module(
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
    physical_views = tuple((index, False) for index in range(len(slots)))
    if installed or occupied:
        compatible_index = slots.index(4)
        physical_views = tuple(
            (index, index == compatible_index) for index in range(len(slots))
        )
    elif unknown_compatible:
        physical_views = ()
    root = _module(
        slots,
        entries,
        model="CHASSIS",
        physical_views=physical_views,
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
            "container_navigation_path": [],
            "slot_index": 1,
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
    assert observation.target is not None
    assert observation.target.container_navigation_path == ()
    assert observation.target.slot_index == 1
    assert len(observation.candidate_targets) == 1
    assert observation.candidate_targets[0].slot_index == 1
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
    assert observation.target is not None
    assert observation.target.slot_index == 1
    assert len(observation.sparse_entries) == 1
    assert observation.sparse_entries[0].container_navigation_path == ()
    assert observation.sparse_entries[0].collection_index == 0
    assert observation.slots[0].state.value == "empty"
    assert observation.slots[1].state.value == "empty"


def test_physical_view_true_is_authoritative_even_without_observed_identity() -> None:
    # No module is retrievable, so nothing but the physical view can speak for
    # the bay. It still counts as occupied, and the identity stays unobserved.
    payload = json.loads(_runtime_observation(sparse_noncompatible=True))
    payload["root"]["descriptor"]["physical_views"][1]["module_added"] = True
    transport = _Replies(json.dumps(payload))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert not observation.target_determined
    assert observation.slots[1].state.value == "occupied_unknown_identity"
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
        (_runtime_observation(multiple=True), "preexisting"),
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

    root = _module(
        (4, 4),
        entries,
        model="CHASSIS",
        physical_views=((0, bool(entries)), (1, False)),
    )
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
    assert observation.target is not None
    assert observation.target.container_navigation_path == ()
    assert observation.target.slot_index == 1
    assert len(observation.candidate_targets) == 1


def test_dual_bay_already_holding_the_required_module_is_already_prepared() -> None:
    transport = _Replies(_dual_bay((
        _present(0, _module(model="AC-POWER-SUPPLY")),
    )))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module("SW", "3650-24PS")

    assert observation.already_prepared
    assert observation.target_determined
    assert observation.target is not None
    assert observation.target.slot_index == 0
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
    assert "preexisting" in observation.message.casefold()
    with pytest.raises(RuntimeError):
        preparer.install_required_module(observation)


def test_dual_bay_with_an_unreadable_compatible_index_refuses() -> None:
    """An unknown bay could already hold the required module; never insert."""

    for entries in (
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
    assert observation.target is not None
    assert observation.target.container_navigation_path == ()
    assert observation.target.slot_index == 1
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
    before = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

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
    assert not verification.factory_requirement_verified
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
    before = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert verification.slot_container_effect
    assert verification.inventory_coherent
    assert verification.installed_identity_observed is None
    assert verification.installed_identity_matches is None
    assert verification.occupancy_effect_verified
    assert not verification.identity_observed
    assert verification.identity_matches is None
    assert verification.factory_requirement_verified


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

    def prepare_required_modules(
        self, device_name: str, device_model: str, *, fresh_owned: bool = False,
    ):
        assert fresh_owned
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
        "function makeModule(slots,entries,model,views){return {"
        "getDescriptor:function(){return makeDescriptor(model,slots,"
        "views||slots.map(function(_,i){return makeView(i,false);}));},"
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
    assert "Boolean(__view.getModuleAdded())" not in script
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
        "getSupportedModule:function(){return ['AC-POWER-SUPPLY'];},"
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
        "target": {
            "container_navigation_path": [], "slot_index": 1, "module_type": 4,
        },
        "error": "",
        "observed_guard": observation.inventory_fingerprint,
    }
    assert script.count(".addModuleAt(") == 1
    assert ".addModule(" not in script
    assert "var __index=1" not in script


def test_install_javascript_rederives_the_same_dual_bay_target_in_node() -> None:
    """The JS revalidation must agree with Python on the dual-bay rule."""

    transport = _Replies(_dual_bay((_present(0, _module(model="COVER-PLATE")),)))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    observation = preparer.observe_required_module("SW", "3650-24PS")
    assert observation.target_determined
    assert observation.target is not None and observation.target.slot_index == 1
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
        "const root=makeModule([4,4],entries,'CHASSIS',"
        "[makeView(0,true),makeView(1,false)]);"
        "root.addModuleAt=function(model,index){calls++;"
        "assert.equal(model,'AC-POWER-SUPPLY');assert.equal(index,1);"
        "entries.push(makeModule([],[],'AC-POWER-SUPPLY'));return true;};"
        "const device={getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},getPower:function(){return power;},"
        "getSupportedModule:function(){return ['AC-POWER-SUPPLY'];},"
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
        "container_navigation_path": [], "slot_index": 1, "module_type": 4,
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
        "getSupportedModule:function(){return ['AC-POWER-SUPPLY'];},"
        "setPower:function(value){power=value;},skipBoot:function(){}};"
        "global.ipc={network:function(){return {getDevice:function(){return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "console.log(JSON.stringify({calls:calls,result:JSON.parse(reported)}));"
    )

    payload = json.loads(_run_node(source))

    assert payload["calls"] == 0
    assert payload["result"]["attempted"] is False
    # The sibling bay turning unknown moves the evidence, not the target bay,
    # so the fingerprint is what refuses here.
    assert payload["result"]["error"] == (
        "installation precondition changed: inventory or PhysicalView "
        "evidence changed since observation (stable across two reads)"
    )
    assert payload["result"]["observed_guard"] != observation.inventory_fingerprint


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
        "getSupportedModule:function(){return ['AC-POWER-SUPPLY'];},"
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
    assert payload["result"]["error"] == (
        "installation precondition changed: inventory or PhysicalView "
        "evidence changed since observation (stable across two reads)"
    )
    assert payload["result"]["observed_guard"]
    assert payload["result"]["observed_guard"] != observation.inventory_fingerprint


def _physical_authority_observation(
    *,
    slots: tuple[int, ...],
    views: tuple[tuple[int, object], ...],
    entries: tuple[dict, ...],
) -> str:
    root = _module(slots, entries, model="CHASSIS")
    root["descriptor"]["physical_views"] = [
        {
            "index": index,
            "slot_num": slot_num,
            "module_added": module_added,
            "error": "",
        }
        for index, (slot_num, module_added) in enumerate(views)
    ]
    return json.dumps({
        "found": True,
        "name": "SW",
        "model": "3650-24PS",
        "supported_modules_raw": [
            "AC-POWER-SUPPLY:../art/PhysicalView/3650Power.pngAC Power Supply",
        ],
        "device_descriptor_root": None,
        "root": root,
    })


def test_collection_index_is_not_treated_as_the_physical_slot_index() -> None:
    raw = _physical_authority_observation(
        slots=(18, 18, 18, 18, 4),
        views=((4, True), (0, False), (1, False), (2, False), (3, False)),
        entries=(_present(0, _module(model="AC-POWER-SUPPLY")),),
    )
    preparer = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)

    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    compatible = next(slot for slot in observation.slots if slot.index == 4)
    assert compatible.container_navigation_path == ()
    assert compatible.state is FactoryModuleSlotState.OCCUPIED
    assert compatible.descriptor_model == "AC-POWER-SUPPLY"
    assert observation.already_prepared
    assert observation.target is not None
    assert observation.target.container_navigation_path == ()
    assert observation.target.slot_index == 4


def test_live_687ba57_false_physical_views_make_runtime_unknown_bays_empty() -> None:
    power_container = _module(
        (30, 30, 30, 30, 4, 4),
        tuple(_unknown(index) for index in range(6)),
        physical_views=tuple((index, False) for index in range(6)),
    )
    root = _module(
        (18, 18, 18),
        (
            _present(0, _module()),
            _present(1, _module((32, 32))),
            _present(2, power_container),
        ),
        physical_views=((0, False), (1, False), (2, False)),
    )
    raw = json.dumps({
        "found": True,
        "name": "SW",
        "model": "3650-24PS",
        "supported_modules_raw": ["AC-POWER-SUPPLY:measured-live-687ba57"],
        "device_descriptor_root": None,
        "root": root,
    })
    preparer = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)

    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    compatible = [slot for slot in observation.slots if slot.module_type == 4]
    assert [slot.index for slot in compatible] == [4, 5]
    assert all(slot.state is FactoryModuleSlotState.EMPTY for slot in compatible)
    assert observation.target is not None
    assert observation.target.container_navigation_path == (2,)
    assert observation.target.slot_index == 4


def test_physical_view_true_is_never_selected_as_empty() -> None:
    raw = _physical_authority_observation(
        slots=(4,), views=((0, True),), entries=(_unknown(0),),
    )
    preparer = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)

    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    assert observation.slots[0].state is FactoryModuleSlotState.OCCUPIED_UNKNOWN_IDENTITY
    assert not observation.target_determined


@pytest.mark.parametrize(
    "malformation",
    ["missing", "duplicate", "wrong-type", "out-of-range", "error"],
)
def test_duplicate_or_malformed_physical_view_is_unknown(malformation: str) -> None:
    raw = json.loads(_physical_authority_observation(
        slots=(4,), views=((0, False),), entries=(_unknown(0),),
    ))
    if malformation == "missing":
        raw["root"]["descriptor"].pop("physical_views")
    elif malformation == "duplicate":
        raw["root"]["descriptor"]["physical_views"].append({
            "index": 1, "slot_num": 0, "module_added": False, "error": "",
        })
    elif malformation == "wrong-type":
        raw["root"]["descriptor"]["physical_views"][0]["module_added"] = 0
    elif malformation == "out-of-range":
        raw["root"]["descriptor"]["physical_views"][0]["slot_num"] = 9
    else:
        raw["root"]["descriptor"]["physical_views"][0]["error"] = "IPC failure"
    preparer = PacketTracerFactoryModulePreparer(_Replies(json.dumps(raw)), BUILD)

    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    assert observation.observed
    assert observation.slots[0].state is FactoryModuleSlotState.UNKNOWN
    assert not observation.target_determined


def test_two_empty_type_four_bays_choose_the_minimum_observed_slot() -> None:
    raw = _physical_authority_observation(
        slots=(4, 4),
        views=((0, False), (1, False)),
        entries=(_unknown(0), _unknown(1)),
    )
    preparer = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)

    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    assert [target.slot_index for target in observation.candidate_targets] == [0, 1]
    assert observation.target is not None
    assert observation.target.slot_index == 0


def test_contradictory_runtime_and_physical_view_refuses_mutation() -> None:
    raw = _physical_authority_observation(
        slots=(18, 18, 18, 18, 4),
        views=((4, False), (0, False), (1, False), (2, False), (3, False)),
        entries=(_present(0, _module(model="AC-POWER-SUPPLY")),),
    )
    transport = _Replies(raw)
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    compatible = next(slot for slot in observation.slots if slot.index == 4)
    assert compatible.state is FactoryModuleSlotState.CONTRADICTORY
    assert not observation.target_determined
    with pytest.raises(RuntimeError):
        preparer.install_required_module(observation)
    assert all(".addModuleAt(" not in script for script in transport.scripts)


def test_navigation_identity_survives_unrelated_traversal_growth() -> None:
    empty_power = _module(
        (4,), (_unknown(0),), physical_views=((0, False),),
    )
    occupied_power = _module(
        (4,), (_present(0, _module(model="", model_observed=False)),),
        physical_views=((0, True),),
    )
    before_root = _module(
        (18, 18, 18),
        (_present(0, _module()), _present(1, _module()), _present(2, empty_power)),
        physical_views=((0, False), (1, False), (2, False)),
    )
    grown_sibling = _module(
        (18,), (_present(0, _module()),), physical_views=((0, True),),
    )
    after_root = _module(
        (18, 18, 18),
        (_present(0, _module()), _present(1, grown_sibling), _present(2, occupied_power)),
        physical_views=((0, False), (1, False), (2, False)),
    )
    envelope = lambda root: json.dumps({
        "found": True,
        "name": "SW",
        "model": "3650-24PS",
        "supported_modules_raw": ["AC-POWER-SUPPLY"],
        "device_descriptor_root": None,
        "root": root,
    })
    transport = _Replies(
        envelope(before_root),
        json.dumps({
            "attempted": True,
            "requested_identity": "AC-POWER-SUPPLY",
            "native_ack": True,
            "power_was_on": True,
            "power_restored": True,
            "target": {
                "container_navigation_path": [2],
                "slot_index": 0,
                "module_type": 4,
            },
            "error": "",
        }),
        envelope(after_root),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS", fresh_owned=True)

    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert before.target is not None
    assert before.target.container_navigation_path == (2,)
    after_target = next(
        slot for slot in verification.after.slots
        if slot.container_navigation_path == (2,) and slot.index == 0
    )
    assert after_target.state is FactoryModuleSlotState.OCCUPIED_UNKNOWN_IDENTITY
    assert verification.occupancy_effect_verified
    assert verification.factory_requirement_verified


def test_fresh_owned_policy_does_not_weaken_preexisting_authority() -> None:
    raw = _physical_authority_observation(
        slots=(4, 4),
        views=((0, False), (1, False)),
        entries=(_unknown(0), _unknown(1)),
    )
    fresh = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)
    existing = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)

    fresh_observation = fresh.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )
    existing_observation = existing.observe_required_module(
        "SW", "3650-24PS", fresh_owned=False,
    )

    assert fresh_observation.target_determined
    assert fresh_observation.target is not None
    assert fresh_observation.target.slot_index == 0
    assert not existing_observation.target_determined
    assert "preexisting" in existing_observation.message.casefold()


def test_native_false_allows_one_bounded_preobserved_fallback_only_after_no_effect() -> None:
    before_raw = _physical_authority_observation(
        slots=(4, 4),
        views=((0, False), (1, False)),
        entries=(_unknown(0), _unknown(1)),
    )
    transport = _Replies(
        before_raw,
        json.dumps({
            "attempted": True,
            "requested_identity": "AC-POWER-SUPPLY",
            "native_ack": False,
            "power_was_on": True,
            "power_restored": True,
            "target": {
                "container_navigation_path": [],
                "slot_index": 0,
                "module_type": 4,
            },
            "error": "",
        }),
        before_raw,
        json.dumps({
            "attempted": True,
            "requested_identity": "AC-POWER-SUPPLY",
            "native_ack": True,
            "power_was_on": True,
            "power_restored": True,
            "target": {
                "container_navigation_path": [],
                "slot_index": 1,
                "module_type": 4,
            },
            "error": "",
        }),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS", fresh_owned=True)
    rejected = preparer.install_required_module(before)

    fallback = preparer.install_fallback_after_false(
        before,
        rejected,
        observed_available_watts=0.0,
    )

    assert rejected.native_ack is False
    assert fallback.native_ack is True
    assert fallback.target is not None
    assert fallback.target.slot_index == 1
    assert fallback.prior_rejected_targets == (rejected.target,)
    assert fallback.prior_rejection_no_effect_verified
    assert sum(script.count(".addModuleAt(") for script in transport.scripts) == 2
    with pytest.raises(RuntimeError, match="fallback"):
        preparer.install_fallback_after_false(
            before,
            rejected,
            observed_available_watts=0.0,
        )


@pytest.mark.parametrize("available", [None, 1.0])
def test_native_false_fallback_requires_fresh_zero_available_power(
    available: float | None,
) -> None:
    raw = _physical_authority_observation(
        slots=(4, 4),
        views=((0, False), (1, False)),
        entries=(_unknown(0), _unknown(1)),
    )
    transport = _Replies(
        raw,
        json.dumps({
            "attempted": True,
            "requested_identity": "AC-POWER-SUPPLY",
            "native_ack": False,
            "power_was_on": True,
            "power_restored": True,
            "target": {
                "container_navigation_path": [],
                "slot_index": 0,
                "module_type": 4,
            },
            "error": "",
        }),
    )
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS", fresh_owned=True)
    rejected = preparer.install_required_module(before)

    with pytest.raises(RuntimeError, match="Available"):
        preparer.install_fallback_after_false(
            before,
            rejected,
            observed_available_watts=available,
        )

    assert sum(script.count(".addModuleAt(") for script in transport.scripts) == 1


@pytest.mark.parametrize("native_result", ["undefined", "null", "'false'", "0"])
def test_nonboolean_add_module_result_stays_ambiguous(
    native_result: str,
) -> None:
    preparer = PacketTracerFactoryModulePreparer(
        _Replies(_runtime_observation()), BUILD,
    )
    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )
    requirement = factory_module_requirement_for("3650-24PS", BUILD)
    script = factory_module_runtime._install_factory_module_js(
        observation, requirement,
    )
    source = (
        "let reported='',power=true;"
        + _node_descriptor_factory()
        + _node_module_factory()
        + "const entries=[makeModule([],[],'BUILTIN')];"
        "const root=makeModule([18,4],entries,'CHASSIS');"
        "root.addModuleAt=function(){return " + native_result + ";};"
        "const device={getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},getPower:function(){return power;},"
        "getSupportedModule:function(){return ['AC-POWER-SUPPLY'];},"
        "setPower:function(value){power=value;},skipBoot:function(){}};"
        "global.ipc={network:function(){return {getDevice:function(){return device;}};}};"
        "global.reportResult=function(value){reported=value;};"
        + script
        + "console.log(reported);"
    )

    payload = json.loads(_run_node(source))

    assert payload["native_ack"] is None


def test_known_required_module_plus_unknown_compatible_identity_is_not_ready() -> None:
    raw = _physical_authority_observation(
        slots=(4, 4),
        views=((0, True), (1, True)),
        entries=(
            _present(0, _module(model="AC-POWER-SUPPLY")),
            _unknown(1),
        ),
    )
    preparer = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)

    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    assert not observation.already_prepared
    assert not observation.target_determined
    assert "unknown" in observation.message.casefold()


def test_post_inventory_rejects_a_new_compatible_slot_outside_the_target() -> None:
    before_raw = _physical_authority_observation(
        slots=(4,), views=((0, False),), entries=(_unknown(0),),
    )
    after_raw = _physical_authority_observation(
        slots=(4, 4),
        views=((0, True), (1, False)),
        entries=(
            _present(0, _module(model="AC-POWER-SUPPLY")),
            _unknown(1),
        ),
    )
    installation_raw = json.dumps({
        "attempted": True,
        "requested_identity": "AC-POWER-SUPPLY",
        "native_ack": True,
        "power_was_on": True,
        "power_restored": True,
        "target": {
            "container_navigation_path": [],
            "slot_index": 0,
            "module_type": 4,
        },
        "error": "",
    })
    preparer = PacketTracerFactoryModulePreparer(
        _Replies(before_raw, installation_raw, after_raw), BUILD,
    )
    before = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    installation = preparer.install_required_module(before)
    verification = preparer.verify_required_module(before, installation)

    assert verification.occupancy_effect_verified
    assert not verification.inventory_coherent
    assert not verification.factory_requirement_verified


LIVE_687BA57_EVIDENCE = Path(
    "docs/reference/cp-scale/canonical-live-evidence"
    "/poe3b-router0-b-3650-11-psu-indexed-20260911T225755Z-6453007a/evidence.json"
)


def _live_687ba57_raw_observation() -> tuple[str, str]:
    """The exact bytes Packet Tracer returned for the 3650 during LIVE B."""

    evidence = json.loads(LIVE_687BA57_EVIDENCE.read_text(encoding="utf-8"))
    before = evidence["factory_preparation"]["before"]
    return before["device_name"], before["raw_response"]


def test_live_687ba57_resolves_the_measured_chassis_to_one_power_bay() -> None:
    """The refusal recorded at 687ba57 was the collection-index model, not PT."""

    device_name, raw = _live_687ba57_raw_observation()
    preparer = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)

    observation = preparer.observe_required_module(
        device_name, "3650-24PS", fresh_owned=True,
    )

    assert observation.observed
    assert observation.supported_module_verified
    compatible = [slot for slot in observation.slots if slot.module_type == 4]
    assert [
        (slot.container_navigation_path, slot.index, slot.state)
        for slot in compatible
    ] == [
        ((2,), 4, FactoryModuleSlotState.EMPTY),
        ((2,), 5, FactoryModuleSlotState.EMPTY),
    ]
    assert observation.target is not None
    assert observation.target.container_navigation_path == (2,)
    assert observation.target.slot_index == 4
    assert observation.target.module_type == 4
    # All six entries of the power container answered getModuleAt with null.
    # They stay unknown collection navigation, never empty slots.
    assert len(observation.sparse_entries) == 6
    assert all(
        entry.container_navigation_path == (2,) and entry.reason == "null"
        for entry in observation.sparse_entries
    )


def test_live_687ba57_builtins_under_not_added_views_are_not_contradictions() -> None:
    """getModuleAdded false means "not added", so built-ins never contradict it.

    Container (1,) of the measured chassis holds C3650-BUILTIN and
    C3650-SFP-BUILTIN across two slots whose physical views both report
    module_added=false. Calling that a contradiction would condemn every
    ordinary chassis, so only an unplaceable module of the required identity
    may do so.
    """

    device_name, raw = _live_687ba57_raw_observation()
    preparer = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)

    observation = preparer.observe_required_module(
        device_name, "3650-24PS", fresh_owned=True,
    )

    builtin_bays = observation.container_slots((1,))
    assert [slot.module_type for slot in builtin_bays] == [32, 32]
    assert all(
        slot.state is FactoryModuleSlotState.EMPTY for slot in builtin_bays
    )
    assert observation.contradictory_slots == ()
    assert observation.target_determined


def test_live_687ba57_javascript_rederives_the_measured_target_in_node() -> None:
    """Python and the emitted JavaScript agree on the real chassis, byte for byte.

    The measured root exposes four ModulePhysicalView entries over three slots
    and three modules, two of them reporting the same getSlotNum. Any parallel
    collection assumption diverges here, so the guard is re-derived through the
    official API under Node and must still authorise the one mutation.
    """

    device_name, raw = _live_687ba57_raw_observation()
    payload = json.loads(raw)
    preparer = PacketTracerFactoryModulePreparer(_Replies(raw), BUILD)
    observation = preparer.observe_required_module(
        device_name, "3650-24PS", fresh_owned=True,
    )
    requirement = factory_module_requirement_for("3650-24PS", BUILD)

    def as_js(node: dict) -> str:
        descriptor = node["descriptor"]
        views = ",".join(
            "makeView(" + json.dumps(view["slot_num"]) + ","
            + json.dumps(view["module_added"]) + ")"
            for view in descriptor.get("physical_views") or []
        )
        children = ",".join(
            as_js(entry["module"]) if entry["state"] == "present" else "null"
            for entry in node["module_entries"]
        )
        return (
            "makeModule("
            + json.dumps([slot["module_type"] for slot in node["slots"]])
            + ",[" + children + "],"
            + json.dumps(descriptor["model"] if descriptor["model_observed"] else "")
            + ",[" + views + "])"
        )

    source = (
        "let calls=[],powers=[],reported='';"
        + _node_descriptor_factory()
        + "function makeModule(slots,entries,model,views){return {"
        "getDescriptor:function(){return makeDescriptor(model,slots,views);},"
        "getSlotCount:function(){return slots.length;},"
        "getSlotTypeAt:function(i){return slots[i];},"
        "getModuleCount:function(){return entries.length;},"
        "getModuleAt:function(i){return entries[i];},"
        "addModuleAt:function(m,i){calls.push([m,i]);return true;}};}"
        "const root=" + as_js(payload["root"]) + ";"
        "const device={getName:function(){return " + json.dumps(device_name) + ";},"
        "getModel:function(){return " + json.dumps("3650-24PS") + ";},"
        "getRootModule:function(){return root;},"
        "getSupportedModule:function(){return "
        + json.dumps(payload["supported_modules_raw"]) + ";},"
        "getDescriptor:function(){return null;},"
        "getPower:function(){return true;},"
        "setPower:function(v){powers.push(v);},skipBoot:function(){}};"
        "global.ipc={network:function(){return {getDevice:function(){"
        "return device;}};}};global.reportResult=function(r){reported=r;};"
        + factory_module_runtime._install_factory_module_js(observation, requirement)
        + "console.log(JSON.stringify({reported:JSON.parse(reported),"
        "calls:calls,powers:powers}));"
    )

    result = json.loads(_run_node(source))

    assert result["calls"] == [["AC-POWER-SUPPLY", 4]]
    assert result["powers"] == [False, True]
    assert result["reported"]["native_ack"] is True
    assert result["reported"]["error"] == ""
    assert result["reported"]["target"] == {
        "container_navigation_path": [2],
        "slot_index": 4,
        "module_type": 4,
    }


@pytest.mark.parametrize("truthy", ["no", 1, [0]])
def test_fresh_owned_authority_refuses_truthiness(truthy: object) -> None:
    """Fresh-owned relaxes multi-bay authority, so it must be an exact bool."""

    transport = _Replies(_runtime_observation(multiple=True))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    with pytest.raises(TypeError):
        preparer.observe_required_module("SW", "3650-24PS", fresh_owned=truthy)
    with pytest.raises(TypeError):
        preparer.prepare_required_modules("SW", "3650-24PS", fresh_owned=truthy)
    assert transport.scripts == []


def test_undecidable_neighbour_bay_blocks_its_whole_container() -> None:
    """A container is the blast radius of addModuleAt, not one bay of it."""

    raw = json.loads(_physical_authority_observation(
        slots=(30, 4), views=((0, False), (1, False)), entries=(),
    ))
    # Slot 0 loses its physical view, so the container's occupancy surface is
    # incomplete and the compatible bay beside it cannot be trusted either.
    raw["root"]["descriptor"]["physical_views"] = [
        {"index": 0, "slot_num": 1, "module_added": False, "error": ""},
    ]
    transport = _Replies(json.dumps(raw))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)

    observation = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )

    assert observation.observed
    assert observation.slots[0].state is FactoryModuleSlotState.UNKNOWN
    assert observation.slots[1].state is FactoryModuleSlotState.EMPTY
    assert not observation.target_determined
    assert "undecidable" in observation.message
    with pytest.raises(RuntimeError):
        preparer.install_required_module(observation)
    assert all(".addModuleAt(" not in script for script in transport.scripts)


def test_fallback_guard_compares_the_module_collection_not_only_occupancy() -> None:
    """Derived occupancy alone let the module collection move unnoticed."""

    def payload(entries: tuple[dict, ...]) -> str:
        root = _module(
            (4, 4), entries, model="CHASSIS",
            physical_views=((0, False), (1, False)),
        )
        return json.dumps({
            "found": True,
            "name": "SW",
            "model": "3650-24PS",
            "supported_modules_raw": ["AC-POWER-SUPPLY"],
            "device_descriptor_root": None,
            "root": root,
        })

    before_raw = payload((_unknown(0), _unknown(1)))
    # The same two empty bays, but Packet Tracer now enumerates one module
    # fewer and explains the survivor differently. Occupancy is untouched.
    moved_raw = payload((_unknown(0, "Error: missing module"),))
    rejection_raw = json.dumps({
        "attempted": True,
        "requested_identity": "AC-POWER-SUPPLY",
        "native_ack": False,
        "power_was_on": True,
        "power_restored": True,
        "target": {
            "container_navigation_path": [],
            "slot_index": 0,
            "module_type": 4,
        },
        "error": "",
    })
    transport = _Replies(before_raw, rejection_raw, moved_raw)
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module(
        "SW", "3650-24PS", fresh_owned=True,
    )
    rejected = preparer.install_required_module(before)
    assert rejected.native_ack is False

    moved = factory_module_runtime._parse_observation(
        moved_raw,
        "SW",
        factory_module_requirement_for("3650-24PS", BUILD),
        fresh_owned=True,
    )
    assert [slot.state for slot in moved.slots] == [
        slot.state for slot in before.slots
    ]
    with pytest.raises(RuntimeError, match="inventory changed"):
        preparer.install_fallback_after_false(
            before, rejected, observed_available_watts=0.0,
        )
    assert sum(".addModuleAt(" in script for script in transport.scripts) == 1



def test_install_javascript_names_the_target_bay_that_stopped_being_empty() -> None:
    """A refusal must say which precondition moved, not just that one did.

    The occupancy of the target bay is checked before the whole-inventory
    fingerprint, so the most specific cause is the one reported. Without it a
    live refusal is indistinguishable from any other drift.
    """

    transport = _Replies(_dual_bay((_present(0, _module(model="COVER-PLATE")),)))
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    observation = preparer.observe_required_module("SW", "3650-24PS")
    requirement = factory_module_requirement_for("3650-24PS", BUILD)
    script = factory_module_runtime._install_factory_module_js(
        observation, requirement,
    )
    source = (
        "let reported='',calls=0,power=true;"
        + _node_descriptor_factory()
        + _node_module_factory()
        # Both bays now report an added module, so the target bay is occupied
        # and its occupant cannot be identified.
        + "const views=[makeView(0,true),makeView(1,true)];"
        "const child=makeModule([],[],'COVER-PLATE',[]);"
        "const root=makeModule([4,4],[child],'CHASSIS',views);"
        "root.addModuleAt=function(){calls++;return true;};"
        "const device={getModel:function(){return '3650-24PS';},"
        "getRootModule:function(){return root;},getPower:function(){return power;},"
        "getSupportedModule:function(){return ['AC-POWER-SUPPLY'];},"
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
    assert payload["result"]["error"] == (
        "installation precondition changed: target slot is no longer empty: "
        "occupied_unknown_identity"
    )


def test_a_precondition_refusal_is_not_an_indeterminate_mutation() -> None:
    """attempted=False means addModuleAt never ran, so nothing is ambiguous.

    The live runner stops either way, but only an indeterminate result forbids
    a later rerun; conflating the two turned a clean refusal into a dead end.
    """

    refusal = json.dumps({
        "attempted": False,
        "requested_identity": "AC-POWER-SUPPLY",
        "native_ack": None,
        "power_was_on": None,
        "power_restored": None,
        "target": None,
        "error": "installation precondition changed: target slot is no longer empty",
        "observed_guard": "[[[],\"\",false,[4],0,[],[],[]]]",
    })
    transport = _Replies(_runtime_observation(), refusal)
    preparer = PacketTracerFactoryModulePreparer(transport, BUILD)
    before = preparer.observe_required_module("SW", "3650-24PS", fresh_owned=True)

    installation = preparer.install_required_module(before)

    assert installation.attempted is False
    assert installation.native_ack is None
    assert installation.refused_before_mutating
    assert installation.power_was_on is None
    assert "no longer empty" in installation.message
    # Both sides of the comparison are retained so the drift is auditable.
    assert installation.expected_guard == before.inventory_fingerprint
    assert installation.observed_guard == "[[[],\"\",false,[4],0,[],[],[]]]"

    # A timeout stays indeterminate: the mutation may have reached PT.
    timeout_transport = _Replies(_runtime_observation(), None)
    timeout_preparer = PacketTracerFactoryModulePreparer(timeout_transport, BUILD)
    timed = timeout_preparer.install_required_module(
        timeout_preparer.observe_required_module(
            "SW", "3650-24PS", fresh_owned=True,
        ),
    )
    assert timed.attempted is True
    assert timed.native_ack is None
    assert not timed.refused_before_mutating
