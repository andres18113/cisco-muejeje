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
    navigation_path: tuple[int, ...]
    descriptor: FactoryModuleDescriptorEvidence
    slot_types: tuple[int, ...]
    entries: tuple[_RuntimeModuleEntry, ...]


def _parse_observation(
    raw: str | None,
    device_name: str,
    requirement: FactoryModuleRequirement,
    *,
    fresh_owned: bool = False,
) -> FactoryModuleObservation:
    # `fresh_owned` relaxes multi-bay authority, so it must be a real boolean.
    # A truthy non-boolean (a "no" string, a stray 1) would silently buy the
    # weaker rule for a device that never earned it.
    if type(fresh_owned) is not bool:
        raise TypeError("fresh_owned authority requires an exact boolean")
    base = dict(
        operation=FactoryModuleOperation.OBSERVE_MODULE_SLOTS,
        device_name=device_name,
        device_model=requirement.device_model,
        packet_tracer_build=requirement.packet_tracer_build,
        required_module_model=requirement.module_model,
        required_module_type=requirement.module_type,
        observed=False,
        fresh_owned=fresh_owned,
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
        root = _runtime_module(payload["root"], ())
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
        slots, sparse, fingerprint = _flatten_slots(root, requirement.module_model)
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
        "inventory_fingerprint": fingerprint,
        "supported_modules_raw": payload.get("supported_modules_raw"),
        "supported_module_verified": _supports_required_module(
            payload.get("supported_modules_raw"), requirement.module_model,
        ),
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
    if not common["supported_module_verified"]:
        return FactoryModuleObservation(
            **common,
            message="The exact supported-module inventory did not contain the requirement.",
        )
    if any(slot.state is FactoryModuleSlotState.CONTRADICTORY for slot in compatible):
        return FactoryModuleObservation(
            **common,
            message="Compatible runtime and PhysicalView occupancy are contradictory.",
        )
    if any(slot.state is FactoryModuleSlotState.UNKNOWN for slot in compatible):
        return FactoryModuleObservation(
            **common,
            message="A compatible PhysicalView occupancy is unknown.",
        )
    # A container is the blast radius of addModuleAt. If any slot of a
    # container that holds a compatible bay is undecidable, that container's
    # occupancy surface is unreliable and its compatible bays cannot be
    # trusted either, whatever the bay's own module type says.
    host_containers = {slot.container_navigation_path for slot in compatible}
    if any(
        slot.state in {
            FactoryModuleSlotState.CONTRADICTORY,
            FactoryModuleSlotState.UNKNOWN,
        }
        for slot in slots
        if slot.container_navigation_path in host_containers
    ):
        return FactoryModuleObservation(
            **common,
            message=(
                "A container holding a compatible bay has undecidable occupancy."
            ),
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
    if any(
        slot.state is FactoryModuleSlotState.OCCUPIED_UNKNOWN_IDENTITY
        for slot in compatible
    ):
        return FactoryModuleObservation(
            **common,
            installed_targets=installed,
            message="A compatible occupied slot has unknown module identity.",
        )
    if len(installed) == requirement.required_count:
        return FactoryModuleObservation(
            **common,
            installed_targets=installed,
            selected_target=installed[0],
            target_determined=True,
            already_prepared=True,
            message="The exact required factory module is installed.",
        )
    candidates = tuple(
        _target_for(slot)
        for slot in compatible
        if slot.state is FactoryModuleSlotState.EMPTY
    )
    if not candidates:
        if any(
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
    if not fresh_owned and len(candidates) != 1:
        return FactoryModuleObservation(
            **common,
            installed_targets=installed,
            candidate_targets=candidates,
            message=(
                "Preexisting-device authority refuses multiple compatible empty slots."
            ),
        )
    target = min(
        candidates,
        key=lambda item: (item.slot_index, item.container_navigation_path),
    )
    return FactoryModuleObservation(
        **common,
        candidate_targets=candidates,
        selected_target=target,
        target_determined=True,
        message=(
            "Fresh-owned policy selected the minimum compatible empty slot index."
            if fresh_owned
            else "One compatible empty index was deterministically observed."
        ),
    )


def _supports_required_module(value: object, required_model: str) -> bool:
    if not isinstance(value, list) or not all(type(item) is str for item in value):
        return False
    return any(
        item == required_model or item.startswith(required_model + ":")
        for item in value
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
    ):
        raise ValueError("descriptor fields are incomplete or wrongly typed")
    if not isinstance(views, list):
        views = []
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
        if not isinstance(view, dict):
            physical_views.append(FactoryModulePhysicalViewEvidence(
                index=index,
                slot_num=None,
                module_added=None,
                error="physical view is not an object",
            ))
            continue
        errors: list[str] = []
        if type(view.get("index")) is not int or view["index"] != index:
            errors.append("invalid physical view collection index")
        slot_num = view.get("slot_num")
        if type(slot_num) is not int:
            errors.append("invalid physical slot number")
            slot_num = None
        module_added = view.get("module_added")
        if type(module_added) is not bool:
            errors.append("invalid module-added type")
            module_added = None
        error = view.get("error", "")
        if type(error) is not str:
            errors.append("invalid physical view error")
        elif error:
            errors.append(error)
        physical_views.append(FactoryModulePhysicalViewEvidence(
            index=index,
            slot_num=slot_num,
            module_added=module_added,
            error=" | ".join(errors),
        ))
    return FactoryModuleDescriptorEvidence(
        model=(model if model_observed else ""),
        model_observed=model_observed,
        slot_types=tuple(slot_types),
        physical_views=tuple(physical_views),
    )


def _runtime_module(
    value: object,
    navigation_path: tuple[int, ...],
) -> _RuntimeModule:
    if not isinstance(value, dict):
        raise TypeError("module is not an object")
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
                _runtime_module(entry.get("module"), navigation_path + (index,)),
            ))
    return _RuntimeModule(
        navigation_path=navigation_path,
        descriptor=descriptor,
        slot_types=tuple(slot_types),
        entries=tuple(parsed_entries),
    )


def _flatten_slots(
    root: _RuntimeModule,
    required_model: str,
) -> tuple[tuple[FactoryModuleSlotObservation, ...],
           tuple[FactoryModuleSparseEntry, ...],
           str]:
    """Derive occupancy from the two official surfaces without inventing a map.

    ``getModuleAt`` indexes a *module collection*. Measured on build
    9.0.1.0858 the 3650 root answers ``getModuleCount`` with 3 over 3 slots
    while exposing **four** ``ModulePhysicalView`` entries, two of which report
    the same ``getSlotNum``. So the physical-view collection is parallel to
    neither the slot inventory nor the module collection, and reading
    ``physical_views[collection_index]`` to place a child in a slot is the same
    unproven inference as treating ``getModuleAt(i)`` as slot ``i``.

    A retrievable module therefore proves occupancy *somewhere in its
    container*, never at a named index. Occupancy per slot comes from the
    exact ``getSlotNum``-keyed physical view.

    ``getModuleAdded() === false`` means no module was *added* to that slot, not
    that the slot is physically empty: the same LIVE run shows container ``(1,)``
    holding ``C3650-BUILTIN`` and ``C3650-SFP-BUILTIN`` across two slots whose
    views both report ``false``. Built-in modules are consequently never treated
    as contradicting a not-added view. What does contradict it is an occupant
    that could be sitting in the very bay policy wants to fill: a retrievable
    module of the required identity that no added slot accounts for. Then the
    not-added bays of that container are CONTRADICTORY and the run fails closed,
    because installing would risk a second supply.
    """

    slots: list[FactoryModuleSlotObservation] = []
    sparse: list[FactoryModuleSparseEntry] = []
    fingerprint: list[object] = []

    def visit(module: _RuntimeModule) -> None:
        descriptor = module.descriptor
        view_by_slot: dict[int, list[FactoryModulePhysicalViewEvidence]] = {}
        physical_mapping_invalid = False
        for view in descriptor.physical_views:
            if (
                view.error
                or view.slot_num is None
                or view.module_added is None
                or view.slot_num < 0
                or view.slot_num >= len(module.slot_types)
            ):
                physical_mapping_invalid = True
                continue
            view_by_slot.setdefault(view.slot_num, []).append(view)
        if any(len(matches) != 1 for matches in view_by_slot.values()):
            physical_mapping_invalid = True

        children: list[_RuntimeModule] = []
        for entry in module.entries:
            if entry.state == "unknown":
                sparse.append(FactoryModuleSparseEntry(
                    container_navigation_path=module.navigation_path,
                    collection_index=entry.index,
                    reason=entry.reason,
                ))
            elif entry.module is not None:
                children.append(entry.module)

        added_slots = [
            index
            for index, matches in view_by_slot.items()
            if len(matches) == 1 and matches[0].module_added is True
        ]
        # An identity can only be pinned to a slot when the container leaves no
        # choice: exactly one added slot, exactly one retrievable module, and
        # no unreadable slot the module could be sitting in instead.
        undecidable = any(
            physical_mapping_invalid or len(view_by_slot.get(index, [])) != 1
            for index in range(len(module.slot_types))
        )
        sole_child = (
            children[0]
            if len(added_slots) == 1 and len(children) == 1 and not undecidable
            else None
        )
        identified = (
            sole_child
            if sole_child is not None
            and sole_child.descriptor.model_observed
            and sole_child.descriptor.model
            else None
        )
        # More retrievable modules than the container has slots is impossible
        # under either reading of the two surfaces.
        impossible = len(children) > len(module.slot_types)
        # A retrievable module of the required identity that no added slot
        # accounts for could be sitting in any not-added bay of this container.
        required_children = sum(
            1
            for child in children
            if child.descriptor.model_observed
            and child.descriptor.model == required_model
        )
        accounted = (
            1
            if identified is not None and identified.descriptor.model == required_model
            else 0
        )
        unplaceable_required = required_children > accounted

        node_slots: list[object] = []
        for index, module_type in enumerate(module.slot_types):
            views = view_by_slot.get(index, [])
            if physical_mapping_invalid or len(views) != 1:
                state = FactoryModuleSlotState.UNKNOWN
                child = None
            elif impossible:
                state = FactoryModuleSlotState.CONTRADICTORY
                child = None
            elif views[0].module_added is False:
                state = (
                    FactoryModuleSlotState.CONTRADICTORY
                    if unplaceable_required
                    else FactoryModuleSlotState.EMPTY
                )
                child = None
            else:
                child = identified
                state = (
                    FactoryModuleSlotState.OCCUPIED
                    if child is not None
                    else FactoryModuleSlotState.OCCUPIED_UNKNOWN_IDENTITY
                )
            observation = FactoryModuleSlotObservation(
                container_navigation_path=module.navigation_path,
                index=index,
                module_type=module_type,
                state=state,
                container_descriptor=module.descriptor,
                descriptor_model=(child.descriptor.model if child else ""),
                descriptor_model_observed=(
                    child.descriptor.model_observed if child else False
                ),
                descriptor=(child.descriptor if child else None),
            )
            slots.append(observation)
            node_slots.append([
                index,
                module_type,
                state.value,
                observation.descriptor_model_observed,
                observation.descriptor_model,
            ])

        fingerprint.append([
            list(module.navigation_path),
            descriptor.model,
            descriptor.model_observed,
            list(module.slot_types),
            len(module.entries),
            [
                [entry.index, entry.state, entry.reason]
                for entry in module.entries
            ],
            [
                [view.index, view.slot_num, view.module_added, bool(view.error)]
                for view in descriptor.physical_views
            ],
            node_slots,
        ])
        for entry in module.entries:
            if entry.module is not None:
                visit(entry.module)

    visit(root)
    return (
        tuple(slots),
        tuple(sparse),
        json.dumps(fingerprint, ensure_ascii=False, separators=(",", ":")),
    )


def _target_for(slot: FactoryModuleSlotObservation) -> FactoryModuleTarget:
    return FactoryModuleTarget(
        container_navigation_path=slot.container_navigation_path,
        slot_index=slot.index,
        module_type=slot.module_type,
    )


def _observation_guard(observation: FactoryModuleObservation) -> str:
    """The complete inventory and PhysicalView evidence, not just occupancy.

    Both the pre-mutation re-derivation in JavaScript and the Python fallback
    guard compare this string. Derived occupancy alone was too narrow: the
    module collection could lose or re-explain an entry, or the physical-view
    collection could change shape, while every derived slot state held still.
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
    target = installation.target or before.target
    before_by_key = {
        (slot.container_navigation_path, slot.index): slot for slot in before.slots
    }
    after_by_key = {
        (slot.container_navigation_path, slot.index): slot for slot in after.slots
    }
    target_key = (
        (target.container_navigation_path, target.slot_index)
        if target is not None
        else None
    )
    before_slot = before_by_key.get(target_key) if target_key is not None else None
    after_slot = after_by_key.get(target_key) if target_key is not None else None
    before_relevant = {
        key: slot
        for key, slot in before_by_key.items()
        if slot.module_type == requirement.module_type
    }
    after_relevant = {
        key: slot
        for key, slot in after_by_key.items()
        if slot.module_type == requirement.module_type
    }
    relevant_keys_unchanged = before_relevant.keys() == after_relevant.keys()
    unaffected_relevant = all(
        after_by_key.get(key) is not None
        and _slot_authority_fact(after_by_key[key]) == _slot_authority_fact(slot)
        for key, slot in before_relevant.items()
        if key != target_key
    )
    slot_effect = (
        before_slot is not None
        and before_slot.state is FactoryModuleSlotState.EMPTY
        and after_slot is not None
        and after_slot.state in {
            FactoryModuleSlotState.OCCUPIED,
            FactoryModuleSlotState.OCCUPIED_UNKNOWN_IDENTITY,
        }
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
        and relevant_keys_unchanged
        and unaffected_relevant
    )
    factory_verified = (
        coherent
        and installation.native_ack is True
        and (
            identity_matches is True
            or (before.fresh_owned and identity_matches is None)
        )
    )
    if not coherent:
        message = "Post-inventory did not prove the unique container/index effect."
    elif identity_matches is None:
        message = "Container/index effect is coherent; installed identity is not observable."
    elif not identity_matches:
        message = "Container/index effect is coherent but installed identity differs."
    else:
        message = "Post-inventory verified the exact installed factory module."
    return dict(
        occupancy_effect_verified=slot_effect,
        inventory_coherent=coherent,
        identity_observed=identity is not None,
        observed_identity=identity,
        identity_matches=identity_matches,
        factory_requirement_verified=factory_verified,
        message=message,
    )


def _slot_authority_fact(slot: FactoryModuleSlotObservation) -> tuple[object, ...]:
    """Exclude diagnostic physical-view metadata from authority comparison."""

    return (
        slot.container_navigation_path,
        slot.index,
        slot.module_type,
        slot.state,
        slot.descriptor_model_observed,
        slot.descriptor_model,
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
        "function __facts(__root,__required){var __all=[];"
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
        "__slotTypes.push(__slot.module_type);if(!__decidable(__key)){__state='unknown';}"
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
        "__en.reason||'']);}var __viewsOut=[];for(var __v2=0;__v2<__views.length;__v2++){"
        "var __vw=__views[__v2];__viewsOut.push([__vw.index,__vw.slot_num,"
        "__vw.module_added,__vw.error?true:false]);}"
        "__all.push([__node.navigation_path,__node.descriptor.model,"
        "__node.descriptor.model_observed,__slotTypes,__node.module_count,__entriesOut,"
        "__viewsOut,__slotStates]);for(var __j=0;__j<__node.module_entries.length;"
        "__j++){var __childEntry=__node.module_entries[__j];if(__childEntry.state==='present'){"
        "__walk(__childEntry.module);}}}__walk(__root);return __all;}"
        "function __hasSupportedModule(__raw,__model){if(!Array.isArray(__raw)){return false;}"
        "for(var __s=0;__s<__raw.length;__s++){if(typeof __raw[__s]!=='string'){"
        "return false;}if(__raw[__s]===__model||__raw[__s].indexOf(__model+':')===0){"
        "return true;}}return false;}"
    )


def _observe_module_slots_js(device_name: str) -> str:
    name = json.dumps(device_name, ensure_ascii=False)
    helpers = _module_observation_js_helpers()
    return (
        "try{var __d=ipc.network().getDevice(" + name + ");"
        "if(!__d){reportResult(JSON.stringify({found:false}));}else{" + helpers
        + "var __state={containers:{}};var __root=__module(__d.getRootModule(),[],__state);"
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
    expected_path = json.dumps(list(target.container_navigation_path))
    expected_index = json.dumps(target.slot_index)
    expected_guard = json.dumps(
        _observation_guard(observation),
        ensure_ascii=False,
    )
    module_type = json.dumps(requirement.module_type)
    module_model = json.dumps(requirement.module_model, ensure_ascii=False)
    helpers = _module_observation_js_helpers()
    return (
        "try{var __d=ipc.network().getDevice(" + name + "),__model=" + module_model
        + ",__type=" + module_type + ",__path=" + expected_path + ";"
        "function __result(__attempted,__ack,__powerWasOn,__powerRestored,__target,__error){"
        "reportResult(JSON.stringify({attempted:__attempted,requested_identity:__model,"
        "native_ack:__ack,power_was_on:__powerWasOn,power_restored:__powerRestored,"
        "target:__target,error:__error}));}if(!__d){__result(false,null,null,null,null,"
        "'device missing');}else if(String(__d.getModel())!==" + device_model + "){"
        "__result(false,null,null,null,null,'device model changed');}else{" + helpers
        + "var __supportedRaw=null;try{__supportedRaw=__d.getSupportedModule();}catch(__se){}"
        "var __state={containers:{}},__root=__module(__d.getRootModule(),[],__state),"
        "__currentFacts=__facts(__root,__model),__pathKey=JSON.stringify(__path),"
        "__targetContainer=__state.containers[__pathKey],__targetFact=null;"
        "for(var __f=0;__f<__currentFacts.length;__f++){var __oneNode="
        "__currentFacts[__f];if(JSON.stringify(__oneNode[0])!==__pathKey){continue;}"
        "var __nodeSlots=__oneNode[7];for(var __g=0;__g<__nodeSlots.length;__g++){"
        "if(__nodeSlots[__g][0]===" + expected_index + "){__targetFact=__nodeSlots[__g];"
        "break;}}break;}"
        "if(!__targetContainer||!__targetFact||JSON.stringify(__currentFacts)!=="
        + expected_guard + "||__targetFact[1]!==__type||__targetFact[2]!=='empty'||"
        "!__hasSupportedModule(__supportedRaw,__model)){"
        "__result(false,null,null,null,null,'installation precondition changed');}else{"
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
        "__result(__attempted,__ack,__powerWasOn,__powerRestored,__target,__error);}}}"
        "catch(__e){reportResult(JSON.stringify({attempted:false,requested_identity:"
        + module_model + ",native_ack:null,power_was_on:null,power_restored:null,"
        "target:null,error:String(__e)}));}"
    )
