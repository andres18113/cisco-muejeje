"""Packet Tracer JavaScript adapter and factory-mutation response parser."""

from __future__ import annotations

import json

from ..catalog.factory_modules import (
    FactoryModuleRequirement,
    uses_exact_indexed_factory_authority,
)
from .factory_module_contracts import (
    FactoryModuleInstallation,
    FactoryModuleObservation,
    FactoryModuleOperation,
    FactoryModuleTarget,
)


def _observation_guard(observation: FactoryModuleObservation) -> str:
    """The policy-scoped authority fingerprint used before mutation.

    The exact 3650 policy excludes diagnostic-only PhysicalView facts. Other
    policies may retain them; the occupancy parser is the single owner of that
    distinction. JavaScript and the Python fallback compare the same string.
    """

    return observation.inventory_fingerprint


def _parse_target(value: object) -> FactoryModuleTarget | None:
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("container_navigation_path"), list)
        or not all(
            type(index) is int and index >= 0
            for index in value["container_navigation_path"]
        )
        or type(value.get("slot_index")) is not int
        or value["slot_index"] < 0
        or type(value.get("module_type")) is not int
    ):
        raise ValueError("mutation target is malformed")
    return FactoryModuleTarget(
        tuple(value["container_navigation_path"]),
        value["slot_index"],
        value["module_type"],
    )


def _parse_installation(
    raw: str | None,
    observation: FactoryModuleObservation,
    requirement: FactoryModuleRequirement,
    *,
    prior_rejected_targets: tuple[FactoryModuleTarget, ...] = (),
    prior_rejection_no_effect_verified: bool = False,
) -> FactoryModuleInstallation:
    base = dict(
        operation=FactoryModuleOperation.INSTALL_FACTORY_MODULE,
        device_name=observation.device_name,
        device_model=observation.device_model,
        packet_tracer_build=observation.packet_tracer_build,
        requested_identity=requirement.module_model,
        target=None,
        prior_rejected_targets=prior_rejected_targets,
        prior_rejection_no_effect_verified=prior_rejection_no_effect_verified,
        expected_guard=_observation_guard(observation),
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
    attempted = payload.get("attempted")
    target_malformed = False
    try:
        target = _parse_target(payload.get("target"))
    except ValueError:
        target = None
        target_malformed = True
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
        and not target_malformed
        and (
            (attempted is False and target is None)
            or (attempted is True and target == observation.target)
        )
    )
    if not valid:
        return FactoryModuleInstallation(
            **base,
            attempted=True,
            acknowledged=None,
            native_ack=None,
            message="Factory module result was malformed; mutation will not replay.",
        )
    observed_guard = payload.get("observed_guard")
    return FactoryModuleInstallation(
        **{**base, "target": target},
        attempted=attempted,
        acknowledged=True,
        native_ack=native_ack,
        power_was_on=power_was_on,
        power_restored=power_restored,
        observed_guard=(observed_guard if type(observed_guard) is str else ""),
        message=str(payload.get("error") or "Factory module mutation returned."),
    )


def _module_observation_js_helpers() -> str:
    """Return one-line helpers built only from observed official APIs."""

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
        "__viewError='';try{var __view=__md.getModulePhysicalViewAt(__j);if(!__view){"
        "throw new Error('null physical view');}var __rawSlot=__view.getSlotNum();"
        "if(typeof __rawSlot==='number'&&isFinite(__rawSlot)&&"
        "Math.floor(__rawSlot)===__rawSlot){__slotNum=__rawSlot;}else{"
        "__viewError='invalid physical slot number';}var __rawAdded=__view.getModuleAdded();"
        "if(typeof __rawAdded==='boolean'){__moduleAdded=__rawAdded;}else{"
        "__viewError+=(__viewError?' | ':'')+'invalid module-added type';}}"
        "catch(__oneViewError){"
        "__viewError=String(__oneViewError);}__views.push({index:__j,slot_num:__slotNum,"
        "module_added:__moduleAdded,error:__viewError});}}catch(__ve){__views=[];}}"
        "return {model:__model,model_observed:__modelObserved,slot_count:__slotCount,"
        "slots:__slots,physical_views:__views};}"
        "function __module(__m,__path,__state){__state.containers[JSON.stringify(__path)]=__m;"
        "var __descriptorValue=__descriptor(__m.getDescriptor());"
        "var __slotCount=__integer(__m.getSlotCount(),'module slot count'),__slots=[];"
        "for(var __i=0;__i<__slotCount;__i++){var __type=Number(__m.getSlotTypeAt(__i));"
        "if(!isFinite(__type)||Math.floor(__type)!==__type){"
        "throw new Error('invalid module slot type');}__slots.push({index:__i,"
        "module_type:__type});}var __moduleCount="
        "__integer(__m.getModuleCount(),'module count');"
        "var __entries=[];for(var __j=0;__j<__moduleCount;__j++){var __child=null;"
        "try{__child=__m.getModuleAt(__j);}catch(__ce){__entries.push({index:__j,"
        "state:'unknown',reason:String(__ce)});continue;}if(!__child){"
        "__entries.push({index:__j,state:'unknown',reason:'null'});continue;}"
        "__entries.push({index:__j,state:'present',reason:'',module:__module(__child,"
        "__path.concat([__j]),__state)});}"
        "return {navigation_path:__path,descriptor:__descriptorValue,slot_count:__slotCount,"
        "slots:__slots,module_count:__moduleCount,module_entries:__entries};}"
        "function __facts(__root,__required,__exactFresh){var __all=[];"
        "function __walk(__node){var __invalid=false,"
        "__viewBySlot={},__viewDupe={},__views=__node.descriptor.physical_views;"
        "for(var __v=0;__v<__views.length;__v++){var __view=__views[__v];"
        "if(__view.error||__view.slot_num===null||"
        "typeof __view.module_added!=='boolean'||__view.slot_num<0||"
        "__view.slot_num>=__node.slots.length){__invalid=true;continue;}var __vk="
        "String(__view.slot_num);if(__viewBySlot.hasOwnProperty(__vk)){__invalid=true;"
        "__viewDupe[__vk]=true;}else{__viewBySlot[__vk]=__view;}}"
        "var __children=[];for(var __e=0;__e<__node.module_entries.length;__e++){"
        "var __entry=__node.module_entries[__e];if(__entry.state==='present'){"
        "__children.push(__entry.module);}}"
        "function __decidable(__k){return !__invalid&&__viewBySlot.hasOwnProperty(__k)"
        "&&!__viewDupe[__k];}var __added=0;for(var __ak in __viewBySlot){"
        "if(__viewBySlot.hasOwnProperty(__ak)&&!__viewDupe[__ak]&&"
        "__viewBySlot[__ak].module_added===true){__added++;}}"
        "var __undecidable=false;for(var __ui=0;__ui<__node.slots.length;__ui++){"
        "if(!__decidable(String(__ui))){__undecidable=true;}}"
        "var __sole=(__added===1&&__children.length===1&&!__undecidable)?"
        "__children[0]:null;"
        "var __identified=(__sole&&__sole.descriptor.model_observed&&"
        "__sole.descriptor.model)?__sole:null;"
        "var __impossible=__children.length>__node.slots.length;"
        "var __requiredChildren=0;for(var __c=0;__c<__children.length;__c++){"
        "if(__children[__c].descriptor.model_observed&&"
        "__children[__c].descriptor.model===__required){__requiredChildren++;}}"
        "var __accounted=(__identified&&__identified.descriptor.model===__required)?1:0;"
        "var __unplaceable=__requiredChildren>__accounted;"
        "var __slotStates=[],__slotTypes=[];"
        "for(var __i=0;__i<__node.slots.length;__i++){var __slot=__node.slots[__i],"
        "__key=String(__i),__state='unknown',__identity='',__identityObserved=false;"
        "__slotTypes.push(__slot.module_type);if(__exactFresh){var __indexed="
        "(__i<__node.module_entries.length&&__node.module_entries[__i].index===__i)"
        "?__node.module_entries[__i]:null;if(!__indexed){__state='unknown';}"
        "else if(__indexed.state==='unknown'){__state=__indexed.reason==='null'"
        "?'empty':'unknown';}else if(__indexed.module.descriptor.model_observed&&"
        "__indexed.module.descriptor.model){__state='occupied';"
        "__identity=__indexed.module.descriptor.model;__identityObserved=true;}"
        "else{__state='occupied_unknown_identity';}}"
        "else if(!__decidable(__key)){__state='unknown';}"
        "else if(__impossible){__state='contradictory';}"
        "else if(__viewBySlot[__key].module_added===false){"
        "__state=__unplaceable?'contradictory':'empty';}"
        "else if(__identified){__state='occupied';"
        "__identity=__identified.descriptor.model;__identityObserved=true;}"
        "else{__state='occupied_unknown_identity';}"
        "__slotStates.push([__i,__slot.module_type,__state,__identityObserved,"
        "__identity]);}var __entriesOut=[];"
        "for(var __e2=0;__e2<__node.module_entries.length;__e2++){var __en="
        "__node.module_entries[__e2];__entriesOut.push([__en.index,__en.state,"
        "__en.reason||'']);}var __viewsOut=[];if(!__exactFresh){"
        "for(var __v2=0;__v2<__views.length;__v2++){"
        "var __vw=__views[__v2];__viewsOut.push([__vw.index,__vw.slot_num,"
        "__vw.module_added,__vw.error?true:false]);}}"
        "__all.push([__node.navigation_path,__node.descriptor.model,"
        "__node.descriptor.model_observed,__slotTypes,__node.module_count,__entriesOut,"
        "__viewsOut,__slotStates]);for(var __j=0;__j<__node.module_entries.length;"
        "__j++){var __childEntry=__node.module_entries[__j];if(__childEntry.state==='present'){"
        "__walk(__childEntry.module);}}}__walk(__root);return __all;}"
        # The supported inventory crosses the IPC boundary. Python only ever
        # sees its JSON round-trip, which is an array of strings; the raw value
        # handed to JavaScript may be a host list proxy, for which
        # Array.isArray is false and elements are not native strings. Requiring
        # a native Array here made the mutation refuse an identity the very
        # same device had just offered the observation. Accept any indexable
        # value with an integer length, coerce each element, and still require
        # the exact identity - the fact Python establishes, established here.
        "function __supportedList(__raw){if(__raw===null||typeof __raw==='undefined'){"
        "return null;}var __len=__raw.length;if(typeof __len!=='number'||!isFinite(__len)"
        "||__len<0||Math.floor(__len)!==__len){return null;}var __out=[];"
        "for(var __i=0;__i<__len;__i++){var __item=__raw[__i];"
        "if(__item===null||typeof __item==='undefined'){return null;}"
        "__out.push(String(__item));}return __out;}"
        "function __hasSupportedModule(__raw,__model){var __list=__supportedList(__raw);"
        "if(__list===null){return false;}for(var __s=0;__s<__list.length;__s++){"
        "if(__list[__s]===__model||__list[__s].indexOf(__model+':')===0){"
        "return true;}}return false;}"
        "function __supportedDiagnostic(__raw,__model){var __list=__supportedList(__raw);"
        "return 'typeof='+(typeof __raw)+' isArray='+Array.isArray(__raw)"
        "+' indexable='+(__list!==null)+' length='+(__list===null?'n/a':__list.length)"
        "+' matches='+__hasSupportedModule(__raw,__model);}"
    )


def _observe_module_slots_js(device_name: str, required_model: str = "") -> str:
    name = json.dumps(device_name, ensure_ascii=False)
    model = json.dumps(required_model, ensure_ascii=False)
    helpers = _module_observation_js_helpers()
    return (
        "try{var __d=ipc.network().getDevice(" + name + ");"
        "if(!__d){reportResult(JSON.stringify({found:false}));}else{" + helpers
        + "var __state={containers:{}};var __root=__module(__d.getRootModule(),[],__state);"
        # The JavaScript view of the supported inventory is recorded alongside
        # its JSON round-trip, because only the round-trip reaches Python and
        # the two disagreed on a live device.
        "var __supported=null,__supportedDiag='unavailable';"
        "try{__supported=__d.getSupportedModule();"
        "__supportedDiag=__supportedDiagnostic(__supported," + model + ");}"
        "catch(__se){__supportedDiag='threw: '+String(__se);}"
        "var __deviceDescriptorRoot=null;try{var __dd=__d.getDescriptor();"
        "if(__dd&&typeof __dd.getRootModule==='function'){"
        "__deviceDescriptorRoot=__descriptor(__dd.getRootModule());}}catch(__dde){}"
        "reportResult(JSON.stringify({found:true,name:String(__d.getName()),"
        "model:String(__d.getModel()),supported_modules_raw:__supported,"
        "supported_diagnostic:__supportedDiag,"
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
    expected_path = json.dumps(list(target.container_navigation_path))
    expected_index = json.dumps(target.slot_index)
    expected_guard = json.dumps(
        _observation_guard(observation),
        ensure_ascii=False,
    )
    module_type = json.dumps(requirement.module_type)
    module_model = json.dumps(requirement.module_model, ensure_ascii=False)
    uses_exact_fresh = (
        observation.fresh_owned
        and uses_exact_indexed_factory_authority(requirement)
    )
    exact_fresh = json.dumps(uses_exact_fresh)
    changed_evidence = json.dumps(
        "authoritative inventory changed since observation"
        if uses_exact_fresh
        else "inventory or PhysicalView evidence changed since observation"
    )
    helpers = _module_observation_js_helpers()
    return (
        "try{var __d=ipc.network().getDevice(" + name + "),__model=" + module_model
        + ",__type=" + module_type + ",__path=" + expected_path + ";"
        "function __result(__attempted,__ack,__powerWasOn,__powerRestored,__target,__error,"
        "__observedGuard){"
        "reportResult(JSON.stringify({attempted:__attempted,requested_identity:__model,"
        "native_ack:__ack,power_was_on:__powerWasOn,power_restored:__powerRestored,"
        "target:__target,error:__error,observed_guard:(__observedGuard||'')}));}"
        "if(!__d){__result(false,null,null,null,null,"
        "'device missing','');}else if(String(__d.getModel())!==" + device_model + "){"
        "__result(false,null,null,null,null,'device model changed','');}else{" + helpers
        # getSupportedModule is read after the module tree, exactly as the
        # observation reads it. Measured on build 9.0.1.0858 the order is not
        # cosmetic: asking first returned an inventory without the identity the
        # same device had just offered, and the pre-mutation check refused a
        # target whose tree evidence was byte-identical to the observation.
        + "var __state={containers:{}},__root=__module(__d.getRootModule(),[],__state),"
        "__supportedRaw=null;try{__supportedRaw=__d.getSupportedModule();}catch(__se){}"
        "var __currentFacts=__facts(__root,__model," + exact_fresh
        + "),__pathKey=JSON.stringify(__path),"
        "__targetContainer=__state.containers[__pathKey],__targetFact=null;"
        "for(var __f=0;__f<__currentFacts.length;__f++){var __oneNode="
        "__currentFacts[__f];if(JSON.stringify(__oneNode[0])!==__pathKey){continue;}"
        "var __nodeSlots=__oneNode[7];for(var __g=0;__g<__nodeSlots.length;__g++){"
        "if(__nodeSlots[__g][0]===" + expected_index + "){__targetFact=__nodeSlots[__g];"
        "break;}}break;}"
        "var __observedGuard=JSON.stringify(__currentFacts),__why='';"
        "if(!__targetContainer){__why='container navigation path is unreachable';}"
        "else if(!__targetFact){__why='target slot index is absent';}"
        "else if(__targetFact[1]!==__type){__why='target slot module type changed';}"
        "else if(__targetFact[2]!=='empty'){__why='target slot is no longer empty: '"
        "+__targetFact[2];}"
        "else if(!__hasSupportedModule(__supportedRaw,__model)){"
        "__why='supported module inventory no longer offers the identity ['"
        "+__supportedDiagnostic(__supportedRaw,__model)+']';}"
        "else if(__observedGuard!==" + expected_guard + "){"
        "__why=" + changed_evidence + ";"
        # Read the surface a second time. Equal reads mean it changed once and
        # settled; unequal reads mean the surface itself is not stable, which
        # is a different defect and must not be mistaken for a real change.
        "var __repeatState={containers:{}};try{var __repeat=__facts("
        "__module(__d.getRootModule(),[],__repeatState),__model," + exact_fresh + ");"
        "__why+=(JSON.stringify(__repeat)===__observedGuard"
        "?' (stable across two reads)':' (unstable across two reads)');}"
        "catch(__re){__why+=' (repeat read failed: '+String(__re)+')';}}"
        "if(__why){__result(false,null,null,null,null,"
        "'installation precondition changed: '+__why,__observedGuard);}else{"
        "var __target={container_navigation_path:__path,slot_index:"
        + expected_index + ",module_type:__type};var __hasPower="
        "typeof __d.getPower==='function'&&typeof __d.setPower==='function';"
        "var __powerWasOn=null,__powerRestored=null,__ack=null,__error='',__attempted=false;"
        "try{if(!__hasPower){throw new Error('device power state is unavailable');}"
        "__powerWasOn=Boolean(__d.getPower());if(!__powerWasOn){"
        "throw new Error('device is not powered before installation');}__d.setPower(false);"
        "__attempted=true;var __nativeResult=__targetContainer.addModuleAt("
        "__model,__target.slot_index);if(typeof __nativeResult==='boolean'){"
        "__ack=__nativeResult;}else{__ack=null;__error='malformed addModuleAt result';}}"
        "catch(__nativeError){__error=String(__nativeError);}finally{"
        "if(__hasPower&&__powerWasOn===true){try{__d.setPower(true);"
        "if(typeof __d.skipBoot==='function'){__d.skipBoot();}__powerRestored=true;}"
        "catch(__powerError){__powerRestored=false;__error+=(__error?' | ':'')"
        "+String(__powerError);}}else if(__hasPower){__powerRestored=true;}}"
        "__result(__attempted,__ack,__powerWasOn,__powerRestored,__target,__error,"
        "__observedGuard);}}}"
        "catch(__e){reportResult(JSON.stringify({attempted:false,requested_identity:"
        + module_model + ",native_ack:null,power_was_on:null,power_restored:null,"
        "target:null,error:String(__e),observed_guard:''}));}"
    )
