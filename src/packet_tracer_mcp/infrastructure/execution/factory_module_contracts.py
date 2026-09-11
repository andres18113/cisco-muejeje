"""Typed facts exchanged by factory-module preparation components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FactoryModuleOperation(str, Enum):
    """The complete public operation vocabulary of this boundary."""

    OBSERVE_MODULE_SLOTS = "observe_module_slots"
    INSTALL_FACTORY_MODULE = "install_factory_module"
    VERIFY_FACTORY_MODULE = "verify_factory_module"


class FactoryModuleSlotState(str, Enum):
    """What the indexed runtime API established about one slot."""

    EMPTY = "empty"
    OCCUPIED = "occupied"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FactoryModulePhysicalViewEvidence:
    """Diagnostic-only descriptor physical-view evidence."""

    index: int
    slot_num: int | None
    module_added: bool | None
    error: str = ""


@dataclass(frozen=True)
class FactoryModuleDescriptorEvidence:
    model: str
    model_observed: bool
    slot_types: tuple[int, ...]
    physical_views: tuple[FactoryModulePhysicalViewEvidence, ...]


@dataclass(frozen=True)
class FactoryModuleTarget:
    """A container/index selected by observation, never by a caller."""

    container_ordinal: int
    index: int
    module_type: int


@dataclass(frozen=True)
class FactoryModuleSparseEntry:
    container_ordinal: int
    module_index: int
    reason: str


@dataclass(frozen=True)
class FactoryModuleSlotObservation:
    container_ordinal: int
    index: int
    module_type: int
    state: FactoryModuleSlotState
    container_descriptor: FactoryModuleDescriptorEvidence | None = None
    descriptor_model: str = ""
    descriptor_model_observed: bool = False
    descriptor: FactoryModuleDescriptorEvidence | None = None


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
    sparse_entries: tuple[FactoryModuleSparseEntry, ...] = ()
    candidate_targets: tuple[FactoryModuleTarget, ...] = ()
    installed_targets: tuple[FactoryModuleTarget, ...] = ()
    target_container_ordinal: int | None = None
    target_index: int | None = None
    target_determined: bool = False
    already_prepared: bool = False
    supported_modules_raw: Any = None
    device_descriptor_root: FactoryModuleDescriptorEvidence | None = None
    descriptor_evidence_observed: bool = False
    message: str = ""
    raw_response: str = ""

    @property
    def target(self) -> FactoryModuleTarget | None:
        if self.target_container_ordinal is None or self.target_index is None:
            return None
        return FactoryModuleTarget(
            self.target_container_ordinal,
            self.target_index,
            self.required_module_type,
        )


@dataclass(frozen=True)
class FactoryModuleInstallation:
    operation: FactoryModuleOperation
    device_name: str
    device_model: str
    packet_tracer_build: str
    requested_identity: str
    target: FactoryModuleTarget | None
    attempted: bool
    acknowledged: bool | None
    native_ack: bool | None
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
    slot_container_effect: bool
    inventory_coherent: bool
    installed_identity_observed: str | None
    installed_identity_matches: bool | None
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
    requested_identity: str
    native_ack: bool | None
    slot_container_effect: bool
    installed_identity_observed: str | None
    power_effect: bool
    available_before_watts: float | None
    used_before_watts: float | None
    remaining_before_watts: float | None
    available_after_watts: float | None
    used_after_watts: float | None
    remaining_after_watts: float | None
    available_delta_watts: float | None
    message: str
