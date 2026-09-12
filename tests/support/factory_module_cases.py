"""Wire-format construction for factory-module tests, written in one place.

Production decides the target of a factory-module installation. A test that
also writes that target by hand states the same identity twice, and the two
drift: a fixture that resolved to slot 0 was paired with a hand-written
response naming slot 1, production correctly refused the mismatch, and a large
JSON block had to be edited to repair a test whose behaviour had not changed.

So the target has exactly one spelling here, and a normal installation
response derives it from the observation under test rather than restating it.
A test that needs the two to disagree asks for that explicitly -
``foreign_target``, ``target_override``, ``malformed_target`` - so the
discrepancy reads as the point of the test instead of an accident of
transcription.

Only the factory-module wire format lives here: module observations, their
PhysicalViews, the target payload, installation responses, and the malformed
shapes used adversarially. Test doubles, assertions and JavaScript fakes stay
with the tests that own them.
"""

from __future__ import annotations

import json
from typing import Any

from src.packet_tracer_mcp.infrastructure.execution.factory_module_contracts import (
    FactoryModuleObservation,
    FactoryModuleTarget,
)

BUILD = "9.0.1.0858"
DEVICE_NAME = "SW"
DEVICE_MODEL = "3650-24PS"
REQUIRED_IDENTITY = "AC-POWER-SUPPLY"
REQUIRED_MODULE_TYPE = 4
SUPPORTED_INVENTORY = (REQUIRED_IDENTITY,)

# The exact bytes Packet Tracer returned when getModuleAt aborted the whole
# tree, retained as raw negative evidence rather than paraphrased.
REAL_NULL_ABORT = '{"found":false,"error":"Error: missing module"}'

_UNSET = object()


# --------------------------------------------------------------------------
# Module tree
# --------------------------------------------------------------------------

def descriptor(
    model: str,
    slots: tuple[int, ...],
    *,
    model_observed: bool = True,
    physical_views: tuple[tuple[int, bool], ...] = (),
) -> dict:
    """One descriptor, including its PhysicalView collection.

    ``physical_views`` is a sequence of ``(slot_num, module_added)`` pairs. It
    is deliberately independent of ``slots``: on the measured build the view
    collection is parallel to neither the slots nor the modules.
    """

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


def module(
    slots: tuple[int, ...] = (),
    entries: tuple[dict, ...] = (),
    *,
    model: str = "",
    model_observed: bool = True,
    physical_views: tuple[tuple[int, bool], ...] = (),
) -> dict:
    """One container of the runtime module tree."""

    return {
        "descriptor": descriptor(
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


def present(index: int, child: dict) -> dict:
    """A module collection entry that getModuleAt answered with a module."""

    return {"index": index, "state": "present", "module": child}


def unknown(index: int, reason: str = "null") -> dict:
    """A module collection entry getModuleAt could not answer."""

    return {"index": index, "state": "unknown", "reason": reason}


def observation_envelope(
    root: dict,
    *,
    name: str = DEVICE_NAME,
    model: str = DEVICE_MODEL,
    supported: Any = SUPPORTED_INVENTORY,
    device_descriptor_root: dict | None = None,
    found: bool = True,
) -> str:
    """The observation reply Packet Tracer reports for one device."""

    return json.dumps({
        "found": found,
        "name": name,
        "model": model,
        "supported_modules_raw": (
            list(supported) if isinstance(supported, tuple) else supported
        ),
        "device_descriptor_root": device_descriptor_root,
        "root": root,
    })


# --------------------------------------------------------------------------
# Named chassis shapes
# --------------------------------------------------------------------------

def runtime_observation(
    *,
    installed: bool = False,
    multiple: bool = False,
    sparse_noncompatible: bool = False,
    occupied: bool = False,
    unknown_compatible: bool = False,
    installed_identity_observed: bool = True,
) -> str:
    """The single-container shapes most behaviours are characterised against."""

    if multiple:
        slots = (4, 4)
        entries: tuple[dict, ...] = ()
    elif installed:
        # One added bay and one retrievable module: the only shape in which
        # Packet Tracer's two surfaces pin an identity to a slot. A second
        # retrievable child would leave the occupant of the added bay a guess.
        slots = (18, 4)
        entries = (
            present(0, module(
                model=REQUIRED_IDENTITY,
                model_observed=installed_identity_observed,
            )),
        )
    elif occupied or unknown_compatible:
        slots = (4,)
        entries = (
            (unknown(0),)
            if unknown_compatible
            else (present(0, module(model="OTHER-MODULE")),)
        )
    else:
        slots = (18, 4)
        entries = (
            unknown(0)
            if sparse_noncompatible
            else present(0, module(model="BUILTIN")),
        )
    physical_views = tuple((index, False) for index in range(len(slots)))
    if installed or occupied:
        compatible_index = slots.index(REQUIRED_MODULE_TYPE)
        physical_views = tuple(
            (index, index == compatible_index) for index in range(len(slots))
        )
    elif unknown_compatible:
        physical_views = ()
    return observation_envelope(
        module(slots, entries, model="CHASSIS", physical_views=physical_views),
        device_descriptor_root=descriptor("CHASSIS", slots),
    )


def physical_authority_observation(
    *,
    slots: tuple[int, ...],
    views: tuple[tuple[int, Any], ...],
    entries: tuple[dict, ...],
) -> str:
    """A chassis whose PhysicalViews are stated independently of its slots."""

    root = module(slots, entries, model="CHASSIS")
    root["descriptor"]["physical_views"] = [
        {
            "index": index,
            "slot_num": slot_num,
            "module_added": module_added,
            "error": "",
        }
        for index, (slot_num, module_added) in enumerate(views)
    ]
    return observation_envelope(
        root,
        supported=(
            REQUIRED_IDENTITY + ":../art/PhysicalView/3650Power.pngAC Power Supply",
        ),
    )


def dual_bay(entries: tuple[dict, ...]) -> str:
    """Two compatible PSU-type bays, the real dual-supply 3650 shape."""

    return observation_envelope(
        module(
            (REQUIRED_MODULE_TYPE, REQUIRED_MODULE_TYPE),
            entries,
            model="CHASSIS",
            physical_views=((0, bool(entries)), (1, False)),
        ),
        device_descriptor_root=descriptor(
            "CHASSIS", (REQUIRED_MODULE_TYPE, REQUIRED_MODULE_TYPE),
        ),
    )


# --------------------------------------------------------------------------
# Target and installation result
# --------------------------------------------------------------------------

def target_payload(target: FactoryModuleTarget) -> dict:
    """The wire spelling of one target. The only place it is written."""

    if not isinstance(target, FactoryModuleTarget):
        raise TypeError("target payload requires the typed target")
    return {
        "container_navigation_path": list(target.container_navigation_path),
        "slot_index": target.slot_index,
        "module_type": target.module_type,
    }


def resolve_target(
    source: FactoryModuleObservation | FactoryModuleTarget,
) -> FactoryModuleTarget:
    """The target production actually selected for this observation."""

    if isinstance(source, FactoryModuleTarget):
        return source
    if not isinstance(source, FactoryModuleObservation):
        raise TypeError("an installation response needs an observation or target")
    if source.target is None:
        raise AssertionError(
            "the observation resolved no target, so no installation response "
            "can be derived from it",
        )
    return source.target


def foreign_target(
    source: FactoryModuleObservation | FactoryModuleTarget,
    *,
    container_navigation_path: tuple[int, ...] | None = None,
    slot_index: int | None = None,
    module_type: int | None = None,
) -> FactoryModuleTarget:
    """A target deliberately unequal to the one production selected.

    Every field defaults to the resolved target's, so a test states only the
    dimension it means to corrupt, and the result is asserted to differ.
    """

    resolved = resolve_target(source)
    candidate = FactoryModuleTarget(
        container_navigation_path=(
            resolved.container_navigation_path
            if container_navigation_path is None
            else container_navigation_path
        ),
        slot_index=(
            resolved.slot_index if slot_index is None else slot_index
        ),
        module_type=(
            resolved.module_type if module_type is None else module_type
        ),
    )
    if candidate == resolved:
        raise AssertionError(
            "foreign_target was asked for a target equal to the resolved one",
        )
    return candidate


def installation_response(
    source: FactoryModuleObservation | FactoryModuleTarget | None = None,
    *,
    native_ack: bool | None = True,
    attempted: bool = True,
    power_was_on: bool | None = True,
    power_restored: bool | None = True,
    requested_identity: str = REQUIRED_IDENTITY,
    error: str = "",
    observed_guard: str | None = None,
    target_override: Any = _UNSET,
    malformed_target: Any = _UNSET,
) -> str:
    """The reply the mutation script reports for one installation attempt.

    The target is derived from ``source`` so it cannot drift from the one
    production selected. ``target_override`` states a different typed target,
    ``malformed_target`` states a payload that is not a target at all; both
    make the disagreement explicit and are only for tests about disagreement.
    """

    if target_override is not _UNSET and malformed_target is not _UNSET:
        raise TypeError("choose either target_override or malformed_target")

    if malformed_target is not _UNSET:
        target: Any = malformed_target
    elif target_override is not _UNSET:
        target = (
            None
            if target_override is None
            else target_payload(target_override)
        )
    else:
        if source is None:
            raise TypeError(
                "an installation response needs a source, an override or a "
                "malformed target",
            )
        target = target_payload(resolve_target(source))

    payload: dict[str, Any] = {
        "attempted": attempted,
        "requested_identity": requested_identity,
        "native_ack": native_ack,
        "power_was_on": power_was_on,
        "power_restored": power_restored,
        "target": target,
        "error": error,
    }
    if observed_guard is not None:
        payload["observed_guard"] = observed_guard
    return json.dumps(payload)

def refusal_response(
    reason: str,
    *,
    observed_guard: str = "",
    requested_identity: str = REQUIRED_IDENTITY,
) -> str:
    """The reply the mutation reports when it refuses before mutating.

    ``attempted`` is false and there is no target, which is what separates
    a refusal from an indeterminate result.
    """

    return installation_response(
        attempted=False,
        native_ack=None,
        power_was_on=None,
        power_restored=None,
        requested_identity=requested_identity,
        error="installation precondition changed: " + reason,
        observed_guard=observed_guard,
        target_override=None,
    )
