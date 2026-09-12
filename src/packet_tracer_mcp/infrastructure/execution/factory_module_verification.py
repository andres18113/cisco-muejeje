"""Verify factory-module inventory deltas independently of PT transport."""

from __future__ import annotations

from ..catalog.factory_modules import (
    FactoryModuleRequirement,
    uses_exact_indexed_factory_authority,
)
from .factory_module_contracts import (
    FactoryModuleInstallation,
    FactoryModuleObservation,
    FactoryModuleSlotObservation,
    FactoryModuleSlotState,
)


def _inventory_effect(
    before: FactoryModuleObservation,
    installation: FactoryModuleInstallation,
    after: FactoryModuleObservation,
    requirement: FactoryModuleRequirement,
) -> dict[str, object]:
    if uses_exact_indexed_factory_authority(requirement):
        return _exact_indexed_inventory_effect(
            before,
            installation,
            after,
            requirement,
        )

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
        diagnostic_inconsistent_with_runtime=False,
        message=message,
    )


def _exact_indexed_inventory_effect(
    before: FactoryModuleObservation,
    installation: FactoryModuleInstallation,
    after: FactoryModuleObservation,
    requirement: FactoryModuleRequirement,
) -> dict[str, object]:
    """Verify the one indexed delta measured by the exact 3650 factory policy."""

    target = before.target
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
    structure_unchanged = (
        before_by_key.keys() == after_by_key.keys()
        and all(
            after_by_key[key].module_type == slot.module_type
            for key, slot in before_by_key.items()
        )
    )
    non_target_unchanged = structure_unchanged and all(
        _slot_authority_fact(after_by_key[key]) == _slot_authority_fact(slot)
        for key, slot in before_by_key.items()
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
        and before.fresh_owned
        and before.target_determined
        and not before.already_prepared
        and target is not None
        and installation.requested_identity == requirement.module_model
        and installation.attempted is True
        and installation.native_ack is True
        and installation.target == target
        and after.observed
        and slot_effect
        and structure_unchanged
        and non_target_unchanged
    )
    factory_verified = coherent and identity_matches is True
    diagnostic_inconsistent = any(
        _physical_view_disagrees_with_runtime(slot) for slot in after.slots
    )
    if not coherent:
        if not structure_unchanged:
            message = "Post-inventory container navigation or slot structure changed."
        elif not non_target_unchanged:
            message = "Post-inventory contains a competing non-target collection change."
        elif installation.native_ack is not True or installation.target != target:
            message = "Post-inventory lacks the exact acknowledged mutation target."
        else:
            message = "Post-inventory did not prove the exact target collection delta."
    elif identity_matches is None:
        message = "Exact post-install identity is not observable on the measured build."
    elif identity_matches is False:
        message = "Exact post-install identity differs from AC-POWER-SUPPLY."
    elif diagnostic_inconsistent:
        message = (
            "Exact indexed factory delta verified; PhysicalView is diagnostic_"
            "inconsistent_with_runtime."
        )
    else:
        message = "Post-inventory verified the exact indexed factory-module delta."
    return dict(
        occupancy_effect_verified=slot_effect,
        inventory_coherent=coherent,
        identity_observed=identity is not None,
        observed_identity=identity,
        identity_matches=identity_matches,
        factory_requirement_verified=factory_verified,
        diagnostic_inconsistent_with_runtime=diagnostic_inconsistent,
        message=message,
    )


def _physical_view_disagrees_with_runtime(
    slot: FactoryModuleSlotObservation,
) -> bool:
    descriptor = slot.container_descriptor
    if descriptor is None:
        return False
    matches = tuple(
        view
        for view in descriptor.physical_views
        if not view.error
        and view.slot_num == slot.index
        and view.module_added is not None
    )
    if len(matches) != 1:
        return False
    runtime_occupied = slot.state in {
        FactoryModuleSlotState.OCCUPIED,
        FactoryModuleSlotState.OCCUPIED_UNKNOWN_IDENTITY,
    }
    return matches[0].module_added is not runtime_occupied


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
