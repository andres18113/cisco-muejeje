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
    """What the two official occupancy surfaces establish about one slot."""

    EMPTY = "empty"
    OCCUPIED = "occupied"
    OCCUPIED_UNKNOWN_IDENTITY = "occupied_unknown_identity"
    UNKNOWN = "unknown"
    CONTRADICTORY = "contradictory"


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
    """A collection-navigation path and physical slot selected by policy."""

    container_navigation_path: tuple[int, ...]
    slot_index: int
    module_type: int


@dataclass(frozen=True)
class FactoryModuleSparseEntry:
    container_navigation_path: tuple[int, ...]
    collection_index: int
    reason: str


@dataclass(frozen=True)
class FactoryModuleSlotObservation:
    container_navigation_path: tuple[int, ...]
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
    fresh_owned: bool = False
    slots: tuple[FactoryModuleSlotObservation, ...] = ()
    sparse_entries: tuple[FactoryModuleSparseEntry, ...] = ()
    candidate_targets: tuple[FactoryModuleTarget, ...] = ()
    installed_targets: tuple[FactoryModuleTarget, ...] = ()
    selected_target: FactoryModuleTarget | None = None
    target_determined: bool = False
    already_prepared: bool = False
    supported_module_verified: bool = False
    supported_modules_raw: Any = None
    supported_diagnostic: str = ""
    device_descriptor_root: FactoryModuleDescriptorEvidence | None = None
    descriptor_evidence_observed: bool = False
    inventory_fingerprint: str = ""
    message: str = ""
    raw_response: str = ""

    @property
    def target(self) -> FactoryModuleTarget | None:
        return self.selected_target

    @property
    def contradictory_slots(self) -> tuple[FactoryModuleSlotObservation, ...]:
        """Every contradiction observed device-wide, whether or not it blocks."""

        return tuple(
            slot
            for slot in self.slots
            if slot.state is FactoryModuleSlotState.CONTRADICTORY
        )

    def container_slots(
        self, navigation_path: tuple[int, ...],
    ) -> tuple[FactoryModuleSlotObservation, ...]:
        return tuple(
            slot
            for slot in self.slots
            if slot.container_navigation_path == navigation_path
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
    prior_rejected_targets: tuple[FactoryModuleTarget, ...] = ()
    prior_rejection_no_effect_verified: bool = False
    power_was_on: bool | None = None
    power_restored: bool | None = None
    expected_guard: str = ""
    observed_guard: str = ""
    message: str = ""
    raw_response: str = ""

    @property
    def refused_before_mutating(self) -> bool:
        """A precondition refusal left Packet Tracer untouched.

        Distinct from an indeterminate result: no ``addModuleAt`` was issued,
        so nothing is ambiguous and the one attempt was never spent on the
        device itself.
        """

        return self.attempted is False and self.native_ack is None


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
    occupancy_effect_verified: bool
    inventory_coherent: bool
    identity_observed: bool
    observed_identity: str | None
    identity_matches: bool | None
    factory_requirement_verified: bool
    message: str = ""

    @property
    def slot_container_effect(self) -> bool:
        """Compatibility spelling for persisted evidence readers."""

        return self.occupancy_effect_verified

    @property
    def installed_identity_observed(self) -> str | None:
        return self.observed_identity

    @property
    def installed_identity_matches(self) -> bool | None:
        return self.identity_matches

    @property
    def verified(self) -> bool:
        return self.factory_requirement_verified


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
    occupancy_effect_verified: bool
    identity_observed: bool
    observed_identity: str | None
    identity_matches: bool | None
    factory_requirement_verified: bool
    power_effect_verified: bool
    available_before_watts: float | None
    used_before_watts: float | None
    remaining_before_watts: float | None
    available_after_watts: float | None
    used_after_watts: float | None
    remaining_after_watts: float | None
    available_delta_watts: float | None
    message: str

    @property
    def slot_container_effect(self) -> bool:
        return self.occupancy_effect_verified

    @property
    def power_effect(self) -> bool:
        return self.power_effect_verified

    @property
    def installed_identity_observed(self) -> str | None:
        return self.observed_identity
