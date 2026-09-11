"""Official indexed Packet Tracer module API adapter and response parser."""

from __future__ import annotations

from dataclasses import dataclass
import json

from ..catalog.factory_modules import FactoryModuleRequirement
from .factory_module_contracts import (
    FactoryModuleDescriptorEvidence,
    FactoryModuleInstallation,
    FactoryModuleObservation,
    FactoryModuleOperation,
    FactoryModulePhysicalViewEvidence,
    FactoryModuleSlotObservation,
    FactoryModuleSlotState,
    FactoryModuleSparseEntry,
    FactoryModuleTarget,
)


@dataclass(frozen=True)
class _RuntimeModuleEntry:
    index: int
    state: str
    module: _RuntimeModule | None
    reason: str = ""


@dataclass(frozen=True)
class _RuntimeModule:
    ordinal: int
    descriptor: FactoryModuleDescriptorEvidence
    slot_types: tuple[int, ...]
    entries: tuple[_RuntimeModuleEntry, ...]


def _parse_observation(
    raw: str | None,
    device_name: str,
    requirement: FactoryModuleRequirement,
) -> FactoryModuleObservation:
    base = dict(
        operation=FactoryModuleOperation.OBSERVE_MODULE_SLOTS,
        device_name=device_name,
        device_model=requirement.device_model,
        packet_tracer_build=requirement.packet_tracer_build,
        required_module_model=requirement.module_model,
        required_module_type=requirement.module_type,
        observed=False,
        raw_response=raw or "",
    )
    try:
        payload = json.loads(raw) if isinstance(raw, str) else None
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        return FactoryModuleObservation(
            **base,
            message="Malformed or missing factory module observation.",
        )
    if (
        payload.get("found") is not True
        or payload.get("name") != device_name
        or payload.get("model") != requirement.device_model
        or not isinstance(payload.get("root"), dict)
    ):
        return FactoryModuleObservation(
            **base,
            message="Factory module observation did not prove the exact device.",
        )

    try:
        ordinal = [0]
        root = _runtime_module(payload["root"], ordinal)
        # The device descriptor root only corroborates the runtime tree. Packet
        # Tracer does not always expose it, and the emitter reports that absence
        # as null. Absence lowers `descriptor_evidence_observed`; it never
        # invalidates the indexed runtime observation that carries authority.
        raw_device_descriptor = payload.get("device_descriptor_root")
        device_descriptor = (
            _descriptor_evidence(raw_device_descriptor)
            if raw_device_descriptor is not None
            else None
        )
        slots, sparse = _flatten_slots(root)
    except (TypeError, ValueError) as exc:
        return FactoryModuleObservation(
            **base,
            message="Malformed factory module tree: " + str(exc),
        )

    common = {
        **base,
        "observed": True,
        "slots": slots,
        "sparse_entries": sparse,
        "supported_modules_raw": payload.get("supported_modules_raw"),
        "device_descriptor_root": device_descriptor,
        "descriptor_evidence_observed": (
            device_descriptor is not None
            and device_descriptor.slot_types == root.slot_types
        ),
    }
    compatible = tuple(
        slot for slot in slots if slot.module_type == requirement.module_type
    )
    if not compatible:
        return FactoryModuleObservation(
            **common,
            message="No runtime index is compatible with the required module type.",
        )
    # A compatible index whose occupancy or identity cannot be read makes both
    # already-prepared detection and insertion unsafe: it could already hold the
    # required module. `null` is unknown, never empty, so this refuses.
    if any(_is_unreadable(slot) for slot in compatible):
        return FactoryModuleObservation(
            **common,
            message="A compatible index has unknown occupancy or identity.",
        )
    installed = tuple(
        _target_for(slot)
        for slot in compatible
        if slot.state is FactoryModuleSlotState.OCCUPIED
        and slot.descriptor_model == requirement.module_model
    )
    if len(installed) > requirement.required_count:
        return FactoryModuleObservation(
            **common,
            installed_targets=installed,
            message="More required factory modules are installed than policy permits.",
        )
    if len(installed) == requirement.required_count:
        return FactoryModuleObservation(
            **common,
            installed_targets=installed,
            target_container_ordinal=installed[0].container_ordinal,
            target_index=installed[0].index,
            target_determined=True,
            already_prepared=True,
            message="The exact required factory module is installed.",
        )
    candidates = tuple(
        _target_for(slot)
        for slot in compatible
        if slot.state is FactoryModuleSlotState.EMPTY
    )
    if len(candidates) != 1:
        if len(candidates) > 1:
            message = "Two or more compatible indexes are indistinguishable."
        elif any(
            slot.state is FactoryModuleSlotState.OCCUPIED for slot in compatible
        ):
            message = "Every compatible index is occupied by another module."
        else:
            message = "No empty compatible index was observed."
        return FactoryModuleObservation(
            **common,
            installed_targets=installed,
            candidate_targets=candidates,
            message=message,
        )
    target = candidates[0]
    return FactoryModuleObservation(
        **common,
        candidate_targets=candidates,
        target_container_ordinal=target.container_ordinal,
        target_index=target.index,
        target_determined=True,
        message="One compatible empty index was deterministically observed.",
    )


def _is_unreadable(slot: FactoryModuleSlotObservation) -> bool:
    """An index is unreadable when occupancy or installed identity is unknown."""

    if slot.state is FactoryModuleSlotState.UNKNOWN:
        return True
    return slot.state is FactoryModuleSlotState.OCCUPIED and not (
        slot.descriptor_model_observed and slot.descriptor_model
    )


def _descriptor_evidence(value: object) -> FactoryModuleDescriptorEvidence:
    if not isinstance(value, dict):
        raise TypeError("descriptor is not an object")
    model = value.get("model")
    model_observed = value.get("model_observed")
    slots = value.get("slots")
    views = value.get("physical_views")
    if (
        type(model) is not str
        or type(model_observed) is not bool
        or type(value.get("slot_count")) is not int
        or not isinstance(slots, list)
        or value["slot_count"] != len(slots)
        or not isinstance(views, list)
    ):
        raise ValueError("descriptor fields are incomplete or wrongly typed")
    slot_types: list[int] = []
    for index, slot in enumerate(slots):
        if (
            not isinstance(slot, dict)
            or type(slot.get("index")) is not int
            or slot["index"] != index
            or type(slot.get("module_type")) is not int
        ):
            raise ValueError("descriptor slot inventory is wrongly typed")
        slot_types.append(slot["module_type"])
    physical_views: list[FactoryModulePhysicalViewEvidence] = []
    for index, view in enumerate(views):
        if (
            not isinstance(view, dict)
            or type(view.get("index")) is not int
            or view["index"] != index
            or (view.get("slot_num") is not None
                and type(view.get("slot_num")) is not int)
            or (view.get("module_added") is not None
                and type(view.get("module_added")) is not bool)
            or type(view.get("error", "")) is not str
        ):
            raise ValueError("descriptor physical view is wrongly typed")
        physical_views.append(FactoryModulePhysicalViewEvidence(
            index=index,
            slot_num=view["slot_num"],
            module_added=view["module_added"],
            error=view.get("error", ""),
        ))
    return FactoryModuleDescriptorEvidence(
        model=(model if model_observed else ""),
        model_observed=model_observed,
        slot_types=tuple(slot_types),
        physical_views=tuple(physical_views),
    )


def _runtime_module(value: object, next_ordinal: list[int]) -> _RuntimeModule:
    if not isinstance(value, dict):
        raise TypeError("module is not an object")
    ordinal = next_ordinal[0]
    next_ordinal[0] += 1
    descriptor = _descriptor_evidence(value.get("descriptor"))
    slots = value.get("slots")
    entries = value.get("module_entries")
    if (
        type(value.get("slot_count")) is not int
        or not isinstance(slots, list)
        or value["slot_count"] != len(slots)
        or type(value.get("module_count")) is not int
        or not isinstance(entries, list)
        or value["module_count"] != len(entries)
        or len(entries) > len(slots)
    ):
        raise ValueError("module fields are incomplete or wrongly typed")
    slot_types: list[int] = []
    for index, slot in enumerate(slots):
        if (
            not isinstance(slot, dict)
            or type(slot.get("index")) is not int
            or slot["index"] != index
            or type(slot.get("module_type")) is not int
        ):
            raise ValueError("slot inventory is incomplete or wrongly typed")
        slot_types.append(slot["module_type"])
    if descriptor.slot_types and descriptor.slot_types != tuple(slot_types):
        raise ValueError("runtime and descriptor slot types disagree")
    parsed_entries: list[_RuntimeModuleEntry] = []
    for index, entry in enumerate(entries):
        if (
            not isinstance(entry, dict)
            or type(entry.get("index")) is not int
            or entry["index"] != index
            or entry.get("state") not in {"present", "unknown"}
        ):
            raise ValueError("module entry inventory is incomplete or wrongly typed")
        if entry["state"] == "unknown":
            reason = entry.get("reason")
            if type(reason) is not str or not reason:
                raise ValueError("unknown module entry lacks a reason")
            parsed_entries.append(_RuntimeModuleEntry(index, "unknown", None, reason))
        else:
            parsed_entries.append(_RuntimeModuleEntry(
                index,
                "present",
                _runtime_module(entry.get("module"), next_ordinal),
            ))
    return _RuntimeModule(
        ordinal=ordinal,
        descriptor=descriptor,
        slot_types=tuple(slot_types),
        entries=tuple(parsed_entries),
    )


def _flatten_slots(
    root: _RuntimeModule,
) -> tuple[tuple[FactoryModuleSlotObservation, ...],
           tuple[FactoryModuleSparseEntry, ...]]:
    slots: list[FactoryModuleSlotObservation] = []
    sparse: list[FactoryModuleSparseEntry] = []

    def visit(module: _RuntimeModule) -> None:
        entries = {entry.index: entry for entry in module.entries}
        for index, module_type in enumerate(module.slot_types):
            entry = entries.get(index)
            if entry is None:
                state = FactoryModuleSlotState.EMPTY
                child = None
            elif entry.state == "unknown":
                state = FactoryModuleSlotState.UNKNOWN
                child = None
                sparse.append(FactoryModuleSparseEntry(
                    container_ordinal=module.ordinal,
                    module_index=index,
                    reason=entry.reason,
                ))
            else:
                state = FactoryModuleSlotState.OCCUPIED
                child = entry.module
            slots.append(FactoryModuleSlotObservation(
                container_ordinal=module.ordinal,
                index=index,
                module_type=module_type,
                state=state,
                container_descriptor=module.descriptor,
                descriptor_model=(child.descriptor.model if child else ""),
                descriptor_model_observed=(
                    child.descriptor.model_observed if child else False
                ),
                descriptor=(child.descriptor if child else None),
            ))
        for entry in module.entries:
            if entry.module is not None:
                visit(entry.module)

    visit(root)
    return tuple(slots), tuple(sparse)


def _target_for(slot: FactoryModuleSlotObservation) -> FactoryModuleTarget:
    return FactoryModuleTarget(
        container_ordinal=slot.container_ordinal,
        index=slot.index,
        module_type=slot.module_type,
    )


def _observation_guard(observation: FactoryModuleObservation) -> str:
    facts = [
        [
            slot.container_ordinal,
            slot.index,
            slot.module_type,
            slot.state.value,
            slot.descriptor_model_observed,
            slot.descriptor_model,
        ]
        for slot in observation.slots
    ]
    return json.dumps(facts, ensure_ascii=False, separators=(",", ":"))


def _parse_target(value: object) -> FactoryModuleTarget | None:
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or type(value.get("container_ordinal")) is not int
        or value["container_ordinal"] < 0
        or type(value.get("index")) is not int
        or value["index"] < 0
        or type(value.get("module_type")) is not int
    ):
        raise ValueError("mutation target is malformed")
    return FactoryModuleTarget(
        value["container_ordinal"],
        value["index"],
        value["module_type"],
    )


def _parse_installation(
    raw: str | None,
    observation: FactoryModuleObservation,
    requirement: FactoryModuleRequirement,
) -> FactoryModuleInstallation:
    base = dict(
        operation=FactoryModuleOperation.INSTALL_FACTORY_MODULE,
        device_name=observation.device_name,
        device_model=observation.device_model,
        packet_tracer_build=observation.packet_tracer_build,
        requested_identity=requirement.module_model,
        target=None,
        raw_response=raw or "",
    )
    try:
        payload = json.loads(raw) if isinstance(raw, str) else None
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        return FactoryModuleInstallation(
            **base,
            attempted=True,
            acknowledged=None,
            native_ack=None,
            message="Factory module result was missing or malformed; mutation will not replay.",
        )
    try:
        target = _parse_target(payload.get("target"))
    except ValueError:
        target = None
    attempted = payload.get("attempted")
    requested = payload.get("requested_identity")
    native_ack = payload.get("native_ack")
    power_was_on = payload.get("power_was_on")
    power_restored = payload.get("power_restored")
    valid = (
        type(attempted) is bool
        and requested == requirement.module_model
        and (native_ack is None or type(native_ack) is bool)
        and (power_was_on is None or type(power_was_on) is bool)
        and (power_restored is None or type(power_restored) is bool)
        and (target is None or target == observation.target)
    )
    if not valid:
        return FactoryModuleInstallation(
            **base,
            attempted=True,
            acknowledged=None,
            native_ack=None,
            message="Factory module result was malformed; mutation will not replay.",
        )
    return FactoryModuleInstallation(
        **{**base, "target": target},
        attempted=attempted,
        acknowledged=True,
        native_ack=native_ack,
        power_was_on=power_was_on,
        power_restored=power_restored,
        message=str(payload.get("error") or "Factory module mutation returned."),
    )


def _inventory_effect(
    before: FactoryModuleObservation,
    installation: FactoryModuleInstallation,
    after: FactoryModuleObservation,
    requirement: FactoryModuleRequirement,
) -> dict[str, object]:
    target = before.target
    before_by_key = {
        (slot.container_ordinal, slot.index): slot for slot in before.slots
    }
    after_by_key = {
        (slot.container_ordinal, slot.index): slot for slot in after.slots
    }
    target_key = (
        (target.container_ordinal, target.index) if target is not None else None
    )
    before_slot = before_by_key.get(target_key) if target_key is not None else None
    after_slot = after_by_key.get(target_key) if target_key is not None else None
    unaffected = all(
        after_by_key.get(key) is not None
        and _slot_authority_fact(after_by_key[key]) == _slot_authority_fact(slot)
        for key, slot in before_by_key.items()
        if key != target_key
    )
    slot_effect = (
        before_slot is not None
        and before_slot.state is FactoryModuleSlotState.EMPTY
        and after_slot is not None
        and after_slot.state is FactoryModuleSlotState.OCCUPIED
    )
    identity = (
        after_slot.descriptor_model
        if after_slot is not None
        and after_slot.descriptor_model_observed
        and after_slot.descriptor_model
        else None
    )
    identity_matches = identity == requirement.module_model if identity else None
    coherent = (
        before.observed
        and before.target_determined
        and not before.already_prepared
        and target is not None
        and installation.requested_identity == requirement.module_model
        and installation.attempted
        and (installation.target is None or installation.target == target)
        and after.observed
        # Coherence rests on the observed container/index transition below, not
        # on re-running pre-mutation target selection against the after-tree:
        # once installed, that index is no longer an insertion candidate, and
        # an unobservable installed identity must stay reportable, not fatal.
        and slot_effect
        and unaffected
    )
    verified = coherent and identity_matches is True
    if not coherent:
        message = "Post-inventory did not prove the unique container/index effect."
    elif identity_matches is None:
        message = "Container/index effect is coherent; installed identity is not observable."
    elif not identity_matches:
        message = "Container/index effect is coherent but installed identity differs."
    else:
        message = "Post-inventory verified the exact installed factory module."
    return dict(
        slot_container_effect=slot_effect,
        inventory_coherent=coherent,
        installed_identity_observed=identity,
        installed_identity_matches=identity_matches,
        verified=verified,
        message=message,
    )


def _slot_authority_fact(slot: FactoryModuleSlotObservation) -> tuple[object, ...]:
    """Exclude diagnostic physical-view metadata from authority comparison."""

    return (
        slot.container_ordinal,
        slot.index,
        slot.module_type,
        slot.state,
        slot.descriptor_model_observed,
        slot.descriptor_model,
    )


def _module_observation_js_helpers() -> str:
    """Return one-line helpers built only from documented indexed APIs."""

    return (
        "function __integer(__v,__label){var __n=Number(__v);"
        "if(!isFinite(__n)||__n<0||Math.floor(__n)!==__n){"
        "throw new Error('invalid '+__label);}return __n;}"
        "function __descriptor(__md){var __model='',__modelObserved=false;"
        "if(!__md){return {model:'',model_observed:false,slot_count:0,slots:[],"
        "physical_views:[]};}try{if(typeof __md.getModel==='function'){var __rawModel="
        "__md.getModel();if(__rawModel!==null&&typeof __rawModel!=='undefined'){"
        "__model=String(__rawModel);__modelObserved=__model!=='';}}}catch(__me){}"
        "var __slotCount=__integer(__md.getSlotCount(),'descriptor slot count'),"
        "__slots=[];for(var __i=0;__i<__slotCount;__i++){var __type="
        "Number(__md.getSlotTypeAt(__i));if(!isFinite(__type)||Math.floor(__type)!==__type){"
        "throw new Error('invalid descriptor slot type');}__slots.push({index:__i,"
        "module_type:__type});}var __views=[];"
        "if(typeof __md.getModulePhysicalViewCount==='function'&&"
        "typeof __md.getModulePhysicalViewAt==='function'){try{var __viewCount="
        "__integer(__md.getModulePhysicalViewCount(),'physical view count');"
        "for(var __j=0;__j<__viewCount;__j++){var __slotNum=null,__moduleAdded=null,"
        "__viewError='';try{var __view=__md.getModulePhysicalViewAt(__j);if(__view){"
        "var __rawSlot=Number(__view.getSlotNum());if(isFinite(__rawSlot)&&"
        "Math.floor(__rawSlot)===__rawSlot){__slotNum=__rawSlot;}"
        "__moduleAdded=Boolean(__view.getModuleAdded());}}catch(__oneViewError){"
        "__viewError=String(__oneViewError);}__views.push({index:__j,slot_num:__slotNum,"
        "module_added:__moduleAdded,error:__viewError});}}catch(__ve){__views=[];}}"
        "return {model:__model,model_observed:__modelObserved,slot_count:__slotCount,"
        "slots:__slots,physical_views:__views};}"
        "function __module(__m,__state){var __ordinal=__state.seen++;"
        "__state.containers.push(__m);var __descriptorValue=__descriptor(__m.getDescriptor());"
        "var __slotCount=__integer(__m.getSlotCount(),'module slot count'),__slots=[];"
        "for(var __i=0;__i<__slotCount;__i++){var __type=Number(__m.getSlotTypeAt(__i));"
        "if(!isFinite(__type)||Math.floor(__type)!==__type){"
        "throw new Error('invalid module slot type');}__slots.push({index:__i,"
        "module_type:__type});}var __moduleCount="
        "__integer(__m.getModuleCount(),'module count');"
        "if(__moduleCount>__slotCount){throw new Error('module count exceeds slot count');}"
        "var __entries=[];for(var __j=0;__j<__moduleCount;__j++){var __child=null;"
        "try{__child=__m.getModuleAt(__j);}catch(__ce){__entries.push({index:__j,"
        "state:'unknown',reason:String(__ce)});continue;}if(!__child){"
        "__entries.push({index:__j,state:'unknown',reason:'null'});continue;}"
        "__entries.push({index:__j,state:'present',module:__module(__child,__state)});}"
        "return {ordinal:__ordinal,descriptor:__descriptorValue,slot_count:__slotCount,"
        "slots:__slots,module_count:__moduleCount,module_entries:__entries};}"
        "function __select(__root,__state,__type,__model){var __compatible=[],"
        "__installed=[],__facts=[];"
        "function __walk(__node){var __entries={};for(var __e=0;"
        "__e<__node.module_entries.length;__e++){var __entry=__node.module_entries[__e];"
        "__entries[__entry.index]=__entry;}for(var __i=0;__i<__node.slots.length;__i++){"
        "var __slot=__node.slots[__i],__entryAt=__entries[__i],__slotState='empty',"
        "__identity='',__identityObserved=false;if(__entryAt){if(__entryAt.state==='unknown'){"
        "__slotState='unknown';}else{__slotState='occupied';var __childDescriptor="
        "__entryAt.module.descriptor;__identity=__childDescriptor.model;"
        "__identityObserved=__childDescriptor.model_observed;}}if(__slot.module_type===__type){"
        "var __candidate={container:__state.containers[__node.ordinal],"
        "container_ordinal:__node.ordinal,index:__i,module_type:__slot.module_type,"
        "state:__slotState,identity:__identity,identity_observed:__identityObserved};"
        "__compatible.push(__candidate);if(__slotState==='occupied'&&"
        "__identityObserved&&__identity===__model){__installed.push(__candidate);}}"
        "__facts.push([__node.ordinal,__i,__slot.module_type,__slotState,"
        "__identityObserved,__identity]);}"
        "for(var __j=0;__j<__node.module_entries.length;__j++){var __childEntry="
        "__node.module_entries[__j];if(__childEntry.state==='present'){"
        "__walk(__childEntry.module);}}}__walk(__root);var __target=null,"
        "__unreadable=false,__empty=[];for(var __c=0;__c<__compatible.length;__c++){"
        "var __one=__compatible[__c];if(__one.state==='unknown'||(__one.state==='occupied'"
        "&&!(__one.identity_observed&&__one.identity))){__unreadable=true;}"
        "if(__one.state==='empty'){__empty.push(__one);}}"
        "if(!__unreadable&&__installed.length===0&&__empty.length===1){"
        "__target=__empty[0];}return {compatible:__compatible,installed:__installed,"
        "target:__target,guard:JSON.stringify(__facts)};}"
    )


def _observe_module_slots_js(device_name: str) -> str:
    name = json.dumps(device_name, ensure_ascii=False)
    helpers = _module_observation_js_helpers()
    return (
        "try{var __d=ipc.network().getDevice(" + name + ");"
        "if(!__d){reportResult(JSON.stringify({found:false}));}else{" + helpers
        + "var __state={seen:0,containers:[]};var __root=__module(__d.getRootModule(),__state);"
        "var __supported=null;try{__supported=__d.getSupportedModule();}catch(__se){}"
        "var __deviceDescriptorRoot=null;try{var __dd=__d.getDescriptor();"
        "if(__dd&&typeof __dd.getRootModule==='function'){"
        "__deviceDescriptorRoot=__descriptor(__dd.getRootModule());}}catch(__dde){}"
        "reportResult(JSON.stringify({found:true,name:String(__d.getName()),"
        "model:String(__d.getModel()),supported_modules_raw:__supported,"
        "device_descriptor_root:__deviceDescriptorRoot,root:__root}));}}"
        "catch(__e){reportResult(JSON.stringify({found:false,error:String(__e)}));}"
    )


def _install_factory_module_js(
    observation: FactoryModuleObservation,
    requirement: FactoryModuleRequirement,
) -> str:
    target = observation.target
    if target is None:
        raise ValueError("Index-native installation requires an observed target")
    name = json.dumps(observation.device_name, ensure_ascii=False)
    device_model = json.dumps(observation.device_model, ensure_ascii=False)
    expected_ordinal = json.dumps(target.container_ordinal)
    expected_index = json.dumps(target.index)
    expected_guard = json.dumps(
        _observation_guard(observation),
        ensure_ascii=False,
    )
    module_type = json.dumps(requirement.module_type)
    module_model = json.dumps(requirement.module_model, ensure_ascii=False)
    helpers = _module_observation_js_helpers()
    return (
        "try{var __d=ipc.network().getDevice(" + name + "),__model=" + module_model
        + ",__type=" + module_type + ";"
        "function __result(__attempted,__ack,__powerWasOn,__powerRestored,__target,__error){"
        "reportResult(JSON.stringify({attempted:__attempted,requested_identity:__model,"
        "native_ack:__ack,power_was_on:__powerWasOn,power_restored:__powerRestored,"
        "target:__target,error:__error}));}if(!__d){__result(false,null,null,null,null,"
        "'device missing');}else if(String(__d.getModel())!==" + device_model + "){"
        "__result(false,null,null,null,null,'device model changed');}else{" + helpers
        + "var __state={seen:0,containers:[]};var __root=__module(__d.getRootModule(),__state);"
        "var __selected=__select(__root,__state,__type,__model),__target=__selected.target;"
        "if(!__target||__selected.guard!==" + expected_guard
        + "||__target.container_ordinal!==" + expected_ordinal
        + "||__target.index!==" + expected_index + "){"
        "__result(false,null,null,null,null,'installation precondition changed');}else{"
        "var __targetFact={container_ordinal:__target.container_ordinal,index:__target.index,"
        "module_type:__target.module_type};var __hasPower="
        "typeof __d.getPower==='function'&&typeof __d.setPower==='function';"
        "var __powerWasOn=null,__powerRestored=null,__ack=null,__error='',__attempted=false;"
        "try{if(!__hasPower){throw new Error('device power state is unavailable');}"
        "__powerWasOn=Boolean(__d.getPower());if(!__powerWasOn){"
        "throw new Error('device is not powered before installation');}__d.setPower(false);"
        "__attempted=true;__ack=__target.container.addModuleAt(__model,__target.index)===true;}"
        "catch(__nativeError){__error=String(__nativeError);}finally{"
        "if(__hasPower&&__powerWasOn===true){try{__d.setPower(true);"
        "if(typeof __d.skipBoot==='function'){__d.skipBoot();}__powerRestored=true;}"
        "catch(__powerError){__powerRestored=false;__error+=(__error?' | ':'')"
        "+String(__powerError);}}else if(__hasPower){__powerRestored=true;}}"
        "__result(__attempted,__ack,__powerWasOn,__powerRestored,__targetFact,__error);}}}"
        "catch(__e){reportResult(JSON.stringify({attempted:false,requested_identity:"
        + module_model + ",native_ack:null,power_was_on:null,power_restored:null,"
        "target:null,error:String(__e)}));}"
    )
