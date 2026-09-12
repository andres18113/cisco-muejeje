"""Parse module inventories and apply model/build-scoped occupancy authority."""

from __future__ import annotations

from dataclasses import dataclass
import json

from ..catalog.factory_modules import (
    FactoryModuleRequirement,
    uses_exact_indexed_factory_authority,
)
from .factory_module_contracts import (
    FactoryModuleDescriptorEvidence,
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
        slots, sparse, fingerprint = _flatten_slots(
            root,
            requirement,
            fresh_owned=fresh_owned,
        )
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
        "supported_diagnostic": (
            payload["supported_diagnostic"]
            if type(payload.get("supported_diagnostic")) is str
            else ""
        ),
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
    exact_indexed = uses_exact_indexed_factory_authority(requirement)
    if exact_indexed and not fresh_owned:
        return FactoryModuleObservation(
            **common,
            message=(
                "Exact-build initial occupancy authority requires a fresh-owned device."
            ),
        )
    if not exact_indexed and any(
        slot.state is FactoryModuleSlotState.CONTRADICTORY for slot in compatible
    ):
        return FactoryModuleObservation(
            **common,
            message="Compatible runtime and PhysicalView occupancy are contradictory.",
        )
    if any(slot.state is FactoryModuleSlotState.UNKNOWN for slot in compatible):
        return FactoryModuleObservation(
            **common,
            message="A compatible runtime occupancy is unknown.",
        )
    # A container is the blast radius of addModuleAt. If any slot of a
    # container that holds a compatible bay is undecidable, that container's
    # occupancy surface is unreliable and its compatible bays cannot be
    # trusted either, whatever the bay's own module type says.
    host_containers = {slot.container_navigation_path for slot in compatible}
    if not exact_indexed and any(
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
    requirement: FactoryModuleRequirement,
    *,
    fresh_owned: bool,
) -> tuple[tuple[FactoryModuleSlotObservation, ...],
           tuple[FactoryModuleSparseEntry, ...],
           str]:
    """Derive occupancy under the policy selected for one exact requirement.

    ``getModuleAt`` indexes a *module collection*. Measured on build
    9.0.1.0858 the 3650 root answers ``getModuleCount`` with 3 over 3 slots
    while exposing **four** ``ModulePhysicalView`` entries, two of which report
    the same ``getSlotNum``. So the physical-view collection is parallel to
    neither the slot inventory nor the module collection, and reading
    ``physical_views[collection_index]`` to place a child in a slot is the same
    unproven inference as treating ``getModuleAt(i)`` as slot ``i``.

    The legacy path below therefore treats a retrievable module as occupancy
    somewhere in its container and uses a keyed PhysicalView to place it.

    ``getModuleAdded() === false`` means no module was *added* to that slot, not
    that the slot is physically empty: the same LIVE run shows container ``(1,)``
    holding ``C3650-BUILTIN`` and ``C3650-SFP-BUILTIN`` across two slots whose
    views both report ``false``. Built-in modules are consequently never treated
    as contradicting a not-added view. What does contradict it is an occupant
    that could be sitting in the very bay policy wants to fill: a retrievable
    module of the required identity that no added slot accounts for. Then the
    not-added bays of that container are CONTRADICTORY and the run fails closed,
    because installing would risk a second supply.

    POE-3H superseded that rule only for the closed 3650/build/factory
    requirement. In that one fresh-owned mutation contract, the indexed
    collection is the authority and PhysicalView is retained only as diagnostic
    evidence. A null indexed entry is initially empty by governed model
    semantics; after the one mutation, the target entry must expose the exact
    module identity. No such inference is made for a non-fresh device.
    """

    slots: list[FactoryModuleSlotObservation] = []
    sparse: list[FactoryModuleSparseEntry] = []
    fingerprint: list[object] = []

    exact_indexed = uses_exact_indexed_factory_authority(requirement)

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
                and child.descriptor.model == requirement.module_model
        )
        accounted = (
            1
            if (
                identified is not None
                and identified.descriptor.model == requirement.module_model
            )
            else 0
        )
        unplaceable_required = required_children > accounted

        node_slots: list[object] = []
        for index, module_type in enumerate(module.slot_types):
            views = view_by_slot.get(index, [])
            if exact_indexed:
                entry = module.entries[index] if index < len(module.entries) else None
                if not fresh_owned or entry is None or entry.index != index:
                    state = FactoryModuleSlotState.UNKNOWN
                    child = None
                elif entry.state == "unknown":
                    state = (
                        FactoryModuleSlotState.EMPTY
                        if entry.reason == "null"
                        else FactoryModuleSlotState.UNKNOWN
                    )
                    child = None
                else:
                    child = entry.module
                    state = (
                        FactoryModuleSlotState.OCCUPIED
                        if child is not None
                        and child.descriptor.model_observed
                        and child.descriptor.model
                        else FactoryModuleSlotState.OCCUPIED_UNKNOWN_IDENTITY
                    )
            elif physical_mapping_invalid or len(views) != 1:
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
            (
                []
                if exact_indexed
                else [
                    [view.index, view.slot_num, view.module_added, bool(view.error)]
                    for view in descriptor.physical_views
                ]
            ),
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
