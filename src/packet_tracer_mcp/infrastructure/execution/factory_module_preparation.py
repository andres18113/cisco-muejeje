"""Fail-closed factory-module preparation for disposable Packet Tracer devices.

Only this infrastructure adapter knows module models, ModuleType values, slot
paths, or JavaScript.  A caller identifies the already-created device and asks
for its exact-build policy to be satisfied.  Discovery, the one permitted
mutation, and independent verification remain three distinct typed operations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import TYPE_CHECKING

from ..catalog.factory_modules import (
    FactoryModuleRequirement,
    factory_module_requirement_for,
)

if TYPE_CHECKING:
    from .ios_terminal import PoEInlineTable


SendAndWait = Callable[[str, float], str | None]
_SLOT_PATH = re.compile(r"^[0-9]+(?:/[0-9]+)*$")


class FactoryModuleOperation(str, Enum):
    """The complete public operation vocabulary of this boundary."""

    OBSERVE_MODULE_SLOTS = "observe_module_slots"
    INSTALL_FACTORY_MODULE = "install_factory_module"
    VERIFY_FACTORY_MODULE = "verify_factory_module"


@dataclass(frozen=True)
class FactoryModuleSlotObservation:
    container_path: str
    index: int
    slot_path: str
    slot_path_determined: bool
    module_type: int
    occupied: bool
    installed_module_number: int | None = None
    installed_module_type: int | None = None
    descriptor_model: str = ""
    descriptor_model_observed: bool = False


@dataclass(frozen=True)
class FactoryModuleObservation:
    operation: FactoryModuleOperation
    device_name: str
    device_model: str
    packet_tracer_build: str
    required_module_model: str
    required_module_type: int
    observed: bool
    slots: tuple[FactoryModuleSlotObservation, ...] = ()
    candidate_slots: tuple[str, ...] = ()
    installed_slots: tuple[str, ...] = ()
    target_slot: str | None = None
    target_parent_path: str | None = None
    target_index: int | None = None
    target_determined: bool = False
    already_prepared: bool = False
    message: str = ""
    raw_response: str = ""


@dataclass(frozen=True)
class FactoryModuleInstallation:
    operation: FactoryModuleOperation
    device_name: str
    device_model: str
    packet_tracer_build: str
    target_slot: str
    attempted: bool
    acknowledged: bool | None
    native_accepted: bool | None
    power_was_on: bool | None = None
    power_restored: bool | None = None
    message: str = ""
    raw_response: str = ""


@dataclass(frozen=True)
class FactoryModuleVerification:
    operation: FactoryModuleOperation
    device_name: str
    device_model: str
    packet_tracer_build: str
    required_module_model: str
    required_module_type: int
    expected_available_watts_before: float
    expected_available_watts: float
    before: FactoryModuleObservation
    installation: FactoryModuleInstallation
    after: FactoryModuleObservation
    caused_effect: bool
    verified: bool
    message: str = ""


@dataclass(frozen=True)
class FactoryModulePreparationResult:
    device_name: str
    device_model: str
    packet_tracer_build: str
    required: bool
    ready: bool
    observation: FactoryModuleObservation | None = None
    installation: FactoryModuleInstallation | None = None
    verification: FactoryModuleVerification | None = None
    message: str = ""


@dataclass(frozen=True)
class FactoryPowerHypothesisResult:
    confirmed: bool
    available_before_watts: float | None
    used_before_watts: float | None
    remaining_before_watts: float | None
    available_after_watts: float | None
    used_after_watts: float | None
    remaining_after_watts: float | None
    available_delta_watts: float | None
    message: str


@dataclass(frozen=True)
class _RuntimeModule:
    slot_path: str
    module_number: int
    module_type: int
    descriptor_model: str
    descriptor_model_observed: bool
    slot_types: tuple[int, ...]
    children: tuple["_RuntimeModule", ...]


class PacketTracerFactoryModulePreparer:
    """Prepare one policy-owned factory module without accepting raw choices."""

    def __init__(
        self,
        send_and_wait: SendAndWait,
        packet_tracer_build: str,
        *,
        observation_timeout_seconds: float = 12.0,
        mutation_timeout_seconds: float = 30.0,
    ) -> None:
        if not callable(send_and_wait):
            raise TypeError("Factory preparation requires a send-and-wait transport")
        if type(packet_tracer_build) is not str or not packet_tracer_build:
            raise ValueError("Factory preparation requires an exact Packet Tracer build")
        self._send_and_wait = send_and_wait
        self.packet_tracer_build = packet_tracer_build
        self._observation_timeout_seconds = max(0.1, observation_timeout_seconds)
        self._mutation_timeout_seconds = max(0.1, mutation_timeout_seconds)
        self._operations: list[FactoryModuleOperation] = []
        self._observations: dict[str, FactoryModuleObservation] = {}
        self._attempted: set[str] = set()
        self._installations: dict[str, FactoryModuleInstallation] = {}

    @property
    def operations(self) -> tuple[FactoryModuleOperation, ...]:
        return tuple(self._operations)

    def observe_required_module(
        self,
        device_name: str,
        device_model: str,
    ) -> FactoryModuleObservation:
        requirement = self._require_policy(device_name, device_model)
        self._operations.append(FactoryModuleOperation.OBSERVE_MODULE_SLOTS)
        observation = self._read_observation(device_name, requirement)
        self._observations[device_name] = observation
        return observation

    def install_required_module(
        self,
        observation: FactoryModuleObservation,
    ) -> FactoryModuleInstallation:
        if not isinstance(observation, FactoryModuleObservation):
            raise TypeError("Installation requires the typed slot observation")
        known = self._observations.get(observation.device_name)
        if known != observation:
            raise RuntimeError("Installation observation is stale or foreign")
        if observation.device_name in self._attempted:
            raise RuntimeError("Factory module installation was already attempted")
        if observation.already_prepared:
            raise RuntimeError("Required factory module is already present")
        if (
            not observation.observed
            or not observation.target_determined
            or observation.target_slot is None
            or observation.target_parent_path is None
            or observation.target_index is None
        ):
            raise RuntimeError("Factory module target was not deterministically observed")

        requirement = self._require_policy(
            observation.device_name,
            observation.device_model,
        )
        self._attempted.add(observation.device_name)
        self._operations.append(FactoryModuleOperation.INSTALL_FACTORY_MODULE)
        raw = self._send_and_wait(
            _install_factory_module_js(observation, requirement),
            self._mutation_timeout_seconds,
        )
        installation = _parse_installation(raw, observation)
        self._installations[observation.device_name] = installation
        return installation

    def verify_required_module(
        self,
        before: FactoryModuleObservation,
        installation: FactoryModuleInstallation,
    ) -> FactoryModuleVerification:
        if not isinstance(before, FactoryModuleObservation):
            raise TypeError("Verification requires the typed before observation")
        if not isinstance(installation, FactoryModuleInstallation):
            raise TypeError("Verification requires the typed installation result")
        if (
            self._observations.get(before.device_name) != before
            or self._installations.get(before.device_name) != installation
            or installation.device_name != before.device_name
        ):
            raise RuntimeError("Factory verification inputs are stale or foreign")

        requirement = self._require_policy(before.device_name, before.device_model)
        self._operations.append(FactoryModuleOperation.VERIFY_FACTORY_MODULE)
        after = self._read_observation(before.device_name, requirement)
        caused, reason = _verified_caused_effect(before, installation, after)
        return FactoryModuleVerification(
            operation=FactoryModuleOperation.VERIFY_FACTORY_MODULE,
            device_name=before.device_name,
            device_model=before.device_model,
            packet_tracer_build=self.packet_tracer_build,
            required_module_model=requirement.module_model,
            required_module_type=requirement.module_type,
            expected_available_watts_before=(
                requirement.expected_available_watts_before
            ),
            expected_available_watts=requirement.expected_available_watts,
            before=before,
            installation=installation,
            after=after,
            caused_effect=caused,
            verified=caused,
            message=reason,
        )

    def prepare_required_modules(
        self,
        device_name: str,
        device_model: str,
    ) -> FactoryModulePreparationResult:
        """Satisfy the exact policy or return a closed refusal; never retry."""

        _validate_device_identity(device_name, device_model)
        requirement = factory_module_requirement_for(
            device_model,
            self.packet_tracer_build,
        )
        if requirement is None:
            return FactoryModulePreparationResult(
                device_name=device_name,
                device_model=device_model,
                packet_tracer_build=self.packet_tracer_build,
                required=False,
                ready=True,
                message="No factory module is required by the exact policy.",
            )

        observation = self.observe_required_module(device_name, device_model)
        if observation.already_prepared:
            return FactoryModulePreparationResult(
                device_name=device_name,
                device_model=device_model,
                packet_tracer_build=self.packet_tracer_build,
                required=True,
                ready=True,
                observation=observation,
                message="The exact required factory module was already observed.",
            )
        if not observation.target_determined:
            return FactoryModulePreparationResult(
                device_name=device_name,
                device_model=device_model,
                packet_tracer_build=self.packet_tracer_build,
                required=True,
                ready=False,
                observation=observation,
                message=observation.message,
            )
        installation = self.install_required_module(observation)
        verification = self.verify_required_module(observation, installation)
        return FactoryModulePreparationResult(
            device_name=device_name,
            device_model=device_model,
            packet_tracer_build=self.packet_tracer_build,
            required=True,
            ready=verification.verified,
            observation=observation,
            installation=installation,
            verification=verification,
            message=verification.message,
        )

    def _require_policy(
        self,
        device_name: str,
        device_model: str,
    ) -> FactoryModuleRequirement:
        _validate_device_identity(device_name, device_model)
        requirement = factory_module_requirement_for(
            device_model,
            self.packet_tracer_build,
        )
        if requirement is None:
            raise ValueError(
                "The exact model has no required factory-module operation"
            )
        return requirement

    def _read_observation(
        self,
        device_name: str,
        requirement: FactoryModuleRequirement,
    ) -> FactoryModuleObservation:
        raw = self._send_and_wait(
            _observe_module_slots_js(device_name),
            self._observation_timeout_seconds,
        )
        return _parse_observation(raw, device_name, requirement)


def classify_factory_power_hypothesis(
    verification: FactoryModuleVerification,
    *,
    before: PoEInlineTable,
    after: PoEInlineTable,
) -> FactoryPowerHypothesisResult:
    """Confirm only the exact no-load budget delta owned by the verified module."""

    values = (
        before.summary_available_watts,
        before.summary_used_watts,
        before.summary_remaining_watts,
        after.summary_available_watts,
        after.summary_used_watts,
        after.summary_remaining_watts,
    )
    delta = (
        values[3] - values[0]
        if values[0] is not None and values[3] is not None
        else None
    )
    confirmed = (
        isinstance(verification, FactoryModuleVerification)
        and verification.verified
        and verification.caused_effect
        and all(value is not None for value in values)
        and values[0] == verification.expected_available_watts_before
        and values[1] == 0.0
        and values[2] == verification.expected_available_watts_before
        and values[3] == verification.expected_available_watts
        and values[4] == values[1]
        and values[5] == values[3] - values[4]
        and delta == (
            verification.expected_available_watts
            - verification.expected_available_watts_before
        )
    )
    return FactoryPowerHypothesisResult(
        confirmed=confirmed,
        available_before_watts=values[0],
        used_before_watts=values[1],
        remaining_before_watts=values[2],
        available_after_watts=values[3],
        used_after_watts=values[4],
        remaining_after_watts=values[5],
        available_delta_watts=delta,
        message=(
            "Verified factory-module insertion caused the exact governed power budget delta."
            if confirmed
            else "Factory-module power hypothesis was not established."
        ),
    )


def _validate_device_identity(device_name: str, device_model: str) -> None:
    if (
        type(device_name) is not str
        or not device_name
        or device_name != device_name.strip()
        or type(device_model) is not str
        or not device_model
        or device_model != device_model.strip()
    ):
        raise ValueError("Factory preparation requires exact device identity")


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
        root = _runtime_module(payload["root"], root=True)
        slots = _flatten_slots(root)
    except (TypeError, ValueError) as exc:
        return FactoryModuleObservation(
            **base,
            message="Malformed factory module tree: " + str(exc),
        )
    if len({slot.slot_path for slot in slots}) != len(slots):
        return FactoryModuleObservation(
            **base,
            message="Malformed factory module tree: duplicate slot path.",
        )

    compatible = tuple(
        slot for slot in slots
        if slot.module_type == requirement.module_type
    )
    if not compatible:
        return FactoryModuleObservation(
            **base,
            slots=slots,
            message="No runtime slot is compatible with the required module type.",
        )
    unknown = tuple(
        slot for slot in compatible
        if slot.occupied and (
            not slot.descriptor_model_observed or not slot.descriptor_model
        )
    )
    if unknown:
        return FactoryModuleObservation(
            **base,
            slots=slots,
            message="An occupied compatible bay has no observable descriptor model.",
        )
    installed = tuple(
        slot.slot_path for slot in compatible
        if slot.occupied and slot.descriptor_model == requirement.module_model
    )
    if len(installed) > requirement.required_count:
        return FactoryModuleObservation(
            **base,
            slots=slots,
            installed_slots=installed,
            message="More required factory modules are installed than policy permits.",
        )
    observed_base = {**base, "observed": True}
    if len(installed) == requirement.required_count:
        target = next(slot for slot in compatible if slot.slot_path == installed[0])
        return FactoryModuleObservation(
            **observed_base,
            slots=slots,
            installed_slots=installed,
            target_slot=target.slot_path,
            target_parent_path=target.container_path,
            target_index=target.index,
            target_determined=True,
            already_prepared=True,
            message="The exact required factory module is installed.",
        )

    candidates = tuple(
        slot.slot_path for slot in compatible
        if not slot.occupied and slot.slot_path_determined
    )
    if len(candidates) != 1:
        return FactoryModuleObservation(
            **observed_base,
            slots=slots,
            candidate_slots=candidates,
            message=(
                "Two or more compatible targets are indistinguishable."
                if len(candidates) > 1
                else "No empty compatible target with an observed slot-path mapping was found."
            ),
        )
    target = next(slot for slot in compatible if slot.slot_path == candidates[0])
    return FactoryModuleObservation(
        **observed_base,
        slots=slots,
        candidate_slots=candidates,
        target_slot=target.slot_path,
        target_parent_path=target.container_path,
        target_index=target.index,
        target_determined=True,
        message="One empty compatible target was deterministically observed.",
    )


def _runtime_module(value: object, *, root: bool = False) -> _RuntimeModule:
    if not isinstance(value, dict):
        raise TypeError("module is not an object")
    path = value.get("slot_path")
    number = value.get("module_number")
    module_type = value.get("module_type")
    descriptor_model = value.get("descriptor_model")
    descriptor_observed = value.get("descriptor_model_observed")
    slots = value.get("slots")
    children = value.get("children")
    if (
        type(path) is not str
        or (not root and _SLOT_PATH.fullmatch(path) is None)
        or type(number) is not int
        or (not root and number < 0)
        or type(module_type) is not int
        or type(descriptor_model) is not str
        or type(descriptor_observed) is not bool
        or not isinstance(slots, list)
        or not isinstance(children, list)
    ):
        raise ValueError("module fields are incomplete or wrongly typed")
    slot_types: list[int] = []
    for expected_index, slot in enumerate(slots):
        if (
            not isinstance(slot, dict)
            or type(slot.get("index")) is not int
            or slot["index"] != expected_index
            or type(slot.get("module_type")) is not int
        ):
            raise ValueError("slot inventory is not complete and ordered")
        slot_types.append(slot["module_type"])
    parsed_children = tuple(_runtime_module(child) for child in children)
    numbers = tuple(child.module_number for child in parsed_children)
    if len(set(numbers)) != len(numbers):
        raise ValueError("two installed modules claim the same slot")
    if any(number >= len(slot_types) for number in numbers):
        raise ValueError("installed module number is outside its parent slots")
    for child in parsed_children:
        expected_path = _child_slot_path(path, child.module_number)
        if child.slot_path != expected_path:
            raise ValueError("slot path and module number disagree")
        if child.module_type != slot_types[child.module_number]:
            raise ValueError("installed module type contradicts its slot type")
    return _RuntimeModule(
        slot_path=path,
        module_number=number,
        module_type=module_type,
        descriptor_model=descriptor_model,
        descriptor_model_observed=descriptor_observed,
        slot_types=tuple(slot_types),
        children=parsed_children,
    )


def _child_slot_path(parent_path: str, index: int) -> str:
    return (parent_path + "/" if parent_path else "") + str(index)


def _flatten_slots(root: _RuntimeModule) -> tuple[FactoryModuleSlotObservation, ...]:
    result: list[FactoryModuleSlotObservation] = []

    def visit(module: _RuntimeModule) -> None:
        by_number = {child.module_number: child for child in module.children}
        for index, slot_type in enumerate(module.slot_types):
            child = by_number.get(index)
            result.append(FactoryModuleSlotObservation(
                container_path=module.slot_path,
                index=index,
                slot_path=_child_slot_path(module.slot_path, index),
                slot_path_determined=(child is not None or bool(module.children)),
                module_type=slot_type,
                occupied=child is not None,
                installed_module_number=(child.module_number if child else None),
                installed_module_type=(child.module_type if child else None),
                descriptor_model=(child.descriptor_model if child else ""),
                descriptor_model_observed=(
                    child.descriptor_model_observed if child else False
                ),
            ))
        for child in module.children:
            visit(child)

    visit(root)
    return tuple(result)


def _parse_installation(
    raw: str | None,
    observation: FactoryModuleObservation,
) -> FactoryModuleInstallation:
    base = dict(
        operation=FactoryModuleOperation.INSTALL_FACTORY_MODULE,
        device_name=observation.device_name,
        device_model=observation.device_model,
        packet_tracer_build=observation.packet_tracer_build,
        target_slot=observation.target_slot or "",
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
            native_accepted=None,
            message="Factory module result was missing or malformed; mutation will not replay.",
        )
    attempted = payload.get("attempted")
    accepted = payload.get("native_accepted")
    power_was_on = payload.get("power_was_on")
    power_restored = payload.get("power_restored")
    if (
        type(attempted) is not bool
        or (accepted is not None and type(accepted) is not bool)
        or (power_was_on is not None and type(power_was_on) is not bool)
        or (power_restored is not None and type(power_restored) is not bool)
    ):
        return FactoryModuleInstallation(
            **base,
            attempted=True,
            acknowledged=None,
            native_accepted=None,
            message="Factory module result was malformed; mutation will not replay.",
        )
    return FactoryModuleInstallation(
        **base,
        attempted=attempted,
        acknowledged=True,
        native_accepted=accepted,
        power_was_on=power_was_on,
        power_restored=power_restored,
        message=str(payload.get("error") or "Factory module mutation returned."),
    )


def _verified_caused_effect(
    before: FactoryModuleObservation,
    installation: FactoryModuleInstallation,
    after: FactoryModuleObservation,
) -> tuple[bool, str]:
    target = before.target_slot
    before_other = tuple(slot for slot in before.slots if slot.slot_path != target)
    after_other = tuple(slot for slot in after.slots if slot.slot_path != target)
    caused = (
        before.observed
        and before.target_determined
        and not before.already_prepared
        and target is not None
        and installation.target_slot == target
        and installation.attempted
        and after.observed
        and after.already_prepared
        and after.installed_slots == (target,)
        and before_other == after_other
    )
    return (
        caused,
        "Independent read-back verified the exact newly installed factory module."
        if caused
        else "Independent read-back did not prove the exact caused factory-module effect.",
    )


def _observe_module_slots_js(device_name: str) -> str:
    # Signatures are from the installed 9.0.1 IpcAPI class_device.html and
    # class_module.html reference.  The root has no parent slot, so only its
    # number/path may normalize to the explicit root sentinels; every child is
    # still required to expose both values exactly.
    name = json.dumps(device_name, ensure_ascii=False)
    return (
        "try{var __d=ipc.network().getDevice(" + name + ");"
        "if(!__d){reportResult(JSON.stringify({found:false}));}else{"
        "var __seen=0;function __module(__m,__root){if(!__m){throw new Error('missing module');}"
        "__seen++;if(__seen>128){throw new Error('module tree exceeds bound');}"
        "var __path='',__number=-1;try{__path=String(__m.getSlotPath());}"
        "catch(__pe){if(!__root){throw __pe;}}"
        "if(__path==='undefined'||__path==='null'){if(!__root){"
        "throw new Error('child slot path unavailable');}__path='';}"
        "try{var __mn=Number(__m.getModuleNumber());if(isFinite(__mn)"
        "&&Math.floor(__mn)===__mn){__number=__mn;}else if(!__root){"
        "throw new Error('child module number unavailable');}}"
        "catch(__ne){if(!__root){throw __ne;}}"
        "var __type=Number(__m.getModuleType()),__descriptor='',__descriptorObserved=false;"
        "try{var __md=__m.getDescriptor();if(__md&&typeof __md.getModel==='function'){"
        "__descriptor=String(__md.getModel());__descriptorObserved=true;}}catch(__de){}"
        "var __slotCount=Number(__m.getSlotCount()),__moduleCount=Number(__m.getModuleCount());"
        "if(!isFinite(__slotCount)||__slotCount<0||Math.floor(__slotCount)!==__slotCount"
        "||!isFinite(__moduleCount)||__moduleCount<0||Math.floor(__moduleCount)!==__moduleCount){"
        "throw new Error('invalid module counts');}var __slots=[],__children=[];"
        "for(var __i=0;__i<__slotCount;__i++){__slots.push({index:__i,"
        "module_type:Number(__m.getSlotTypeAt(__i))});}"
        "for(var __j=0;__j<__moduleCount;__j++){__children.push(__module(__m.getModuleAt(__j),false));}"
        "return {slot_path:__path,module_number:__number,module_type:__type,"
        "descriptor_model:__descriptor,descriptor_model_observed:__descriptorObserved,"
        "slots:__slots,children:__children};}var __root=__d.getRootModule();"
        "reportResult(JSON.stringify({found:true,name:String(__d.getName()),"
        "model:String(__d.getModel()),root:__module(__root,true)}));}}"
        "catch(__e){reportResult(JSON.stringify({found:false,error:String(__e)}));}"
    )


def _install_factory_module_js(
    observation: FactoryModuleObservation,
    requirement: FactoryModuleRequirement,
) -> str:
    name = json.dumps(observation.device_name, ensure_ascii=False)
    device_model = json.dumps(observation.device_model, ensure_ascii=False)
    target = json.dumps(observation.target_slot, ensure_ascii=False)
    parent = json.dumps(observation.target_parent_path, ensure_ascii=False)
    index = json.dumps(observation.target_index)
    module_type = json.dumps(requirement.module_type)
    module_model = json.dumps(requirement.module_model, ensure_ascii=False)
    return (
        "try{var __d=ipc.network().getDevice(" + name + ");"
        "if(!__d){reportResult(JSON.stringify({attempted:false,native_accepted:null,"
        "power_was_on:null,power_restored:null,error:'device missing'}));}"
        "else if(String(__d.getModel())!==" + device_model + "){"
        "reportResult(JSON.stringify({attempted:false,native_accepted:null,"
        "power_was_on:null,power_restored:null,error:'device model changed'}));}else{"
        "var __target=" + target + ",__parent=" + parent + ",__index=" + index
        + ",__type=" + module_type + ",__model=" + module_model + ";"
        "var __container=null,__containers=0,__occupied=false,__required=0,__unknown=0;"
        "function __walk(__m){if(!__m){throw new Error('missing module');}"
        "var __path=String(__m.getSlotPath());if(__path===__parent){"
        "__container=__m;__containers++;}if(__path===__target){__occupied=true;}"
        "if(Number(__m.getModuleType())===__type){try{var __md=__m.getDescriptor();"
        "if(!__md||typeof __md.getModel!=='function'||String(__md.getModel())===''){__unknown++;}"
        "else if(String(__md.getModel())===__model){__required++;}}catch(__de){__unknown++;}}"
        "var __count=Number(__m.getModuleCount());for(var __i=0;__i<__count;__i++){"
        "__walk(__m.getModuleAt(__i));}}__walk(__d.getRootModule());"
        "if(__containers!==1||!__container||__index<0"
        "||__index>=Number(__container.getSlotCount())"
        "||Number(__container.getSlotTypeAt(__index))!==__type||__occupied"
        "||__required!==0||__unknown!==0){"
        "reportResult(JSON.stringify({attempted:false,native_accepted:null,"
        "power_was_on:null,power_restored:null,error:'installation precondition changed'}));}else{"
        "var __hasPower=typeof __d.getPower==='function'&&typeof __d.setPower==='function';"
        "var __powerWasOn=null,__powerRestored=null,__accepted=null,__error='';"
        "try{if(!__hasPower){throw new Error('device power state is unavailable');}"
        "__powerWasOn=Boolean(__d.getPower());"
        "if(!__powerWasOn){throw new Error('device is not powered before installation');}"
        "__d.setPower(false);"
        "__accepted=__d.addModule(__target,__type,__model)===true;}"
        "catch(__nativeError){__error=String(__nativeError);}finally{"
        "if(__hasPower&&__powerWasOn===true){try{__d.setPower(true);"
        "if(typeof __d.skipBoot==='function'){__d.skipBoot();}__powerRestored=true;}"
        "catch(__powerError){__powerRestored=false;__error+=(__error?' | ':'')+String(__powerError);}}"
        "else if(__hasPower){__powerRestored=true;}}"
        "reportResult(JSON.stringify({attempted:true,native_accepted:__accepted,"
        "power_was_on:__powerWasOn,power_restored:__powerRestored,error:__error}));}}}"
        "catch(__e){reportResult(JSON.stringify({attempted:false,native_accepted:null,"
        "power_was_on:null,power_restored:null,error:String(__e)}));}"
    )
