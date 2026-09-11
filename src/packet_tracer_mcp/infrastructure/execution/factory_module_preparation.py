"""Coordinate one policy-owned, index-native factory-module preparation."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..catalog.factory_modules import (
    FactoryModuleRequirement,
    factory_module_requirement_for,
)
from .factory_module_contracts import (
    FactoryModuleDescriptorEvidence,
    FactoryModuleInstallation,
    FactoryModuleObservation,
    FactoryModuleOperation,
    FactoryModulePhysicalViewEvidence,
    FactoryModulePreparationResult,
    FactoryModuleSlotObservation,
    FactoryModuleSlotState,
    FactoryModuleSparseEntry,
    FactoryModuleTarget,
    FactoryModuleVerification,
    FactoryPowerHypothesisResult,
)
from .factory_module_runtime import (
    _install_factory_module_js,
    _inventory_effect,
    _observe_module_slots_js,
    _parse_installation,
    _parse_observation,
)

if TYPE_CHECKING:
    from .ios_terminal import PoEInlineTable


SendAndWait = Callable[[str, float], str | None]


class PacketTracerFactoryModulePreparer:
    """Prepare one required module without raw caller choices or replay."""

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
            raise TypeError("Installation requires the typed index observation")
        if self._observations.get(observation.device_name) != observation:
            raise RuntimeError("Installation observation is stale or foreign")
        if observation.device_name in self._attempted:
            raise RuntimeError("Factory module installation was already attempted")
        if observation.already_prepared:
            raise RuntimeError("Required factory module is already present")
        if not observation.observed or not observation.target_determined:
            raise RuntimeError("Factory module target was not deterministically observed")
        if observation.target is None:
            raise RuntimeError("Factory module target index is unavailable")

        requirement = self._require_policy(
            observation.device_name,
            observation.device_model,
        )
        # Consume the sole attempt before crossing the transport. A timeout,
        # malformed result, false acknowledgement, or exception never replays.
        self._attempted.add(observation.device_name)
        self._operations.append(FactoryModuleOperation.INSTALL_FACTORY_MODULE)
        raw = self._send_and_wait(
            _install_factory_module_js(observation, requirement),
            self._mutation_timeout_seconds,
        )
        installation = _parse_installation(raw, observation, requirement)
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
        effect = _inventory_effect(before, installation, after, requirement)
        return FactoryModuleVerification(
            operation=FactoryModuleOperation.VERIFY_FACTORY_MODULE,
            device_name=before.device_name,
            device_model=before.device_model,
            packet_tracer_build=self.packet_tracer_build,
            required_module_model=requirement.module_model,
            required_module_type=requirement.module_type,
            expected_available_watts_before=requirement.expected_available_watts_before,
            expected_available_watts=requirement.expected_available_watts,
            before=before,
            installation=installation,
            after=after,
            **effect,
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
            raise ValueError("The exact model has no required factory-module operation")
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
    """Classify the exact causal no-load power effect without inventing identity."""

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
    power_effect = (
        all(value is not None for value in values)
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
    confirmed = (
        isinstance(verification, FactoryModuleVerification)
        and verification.installation.requested_identity
        == verification.required_module_model
        and verification.installation.attempted
        and verification.installation.native_ack is not False
        and verification.slot_container_effect
        and verification.inventory_coherent
        and verification.installed_identity_matches is not False
        and power_effect
    )
    return FactoryPowerHypothesisResult(
        confirmed=confirmed,
        requested_identity=verification.installation.requested_identity,
        native_ack=verification.installation.native_ack,
        slot_container_effect=verification.slot_container_effect,
        installed_identity_observed=verification.installed_identity_observed,
        power_effect=power_effect,
        available_before_watts=values[0],
        used_before_watts=values[1],
        remaining_before_watts=values[2],
        available_after_watts=values[3],
        used_after_watts=values[4],
        remaining_after_watts=values[5],
        available_delta_watts=delta,
        message=(
            "The one requested module mutation caused the exact governed power effect."
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
