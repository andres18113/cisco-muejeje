"""Coordinate one policy-owned, index-native factory-module preparation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
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
    _observation_guard,
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
        self._fallback_consumed: set[str] = set()
        self._installations: dict[str, FactoryModuleInstallation] = {}

    @property
    def operations(self) -> tuple[FactoryModuleOperation, ...]:
        return tuple(self._operations)

    def observe_required_module(
        self,
        device_name: str,
        device_model: str,
        *,
        fresh_owned: bool = False,
    ) -> FactoryModuleObservation:
        _validate_fresh_owned(fresh_owned)
        requirement = self._require_policy(device_name, device_model)
        self._operations.append(FactoryModuleOperation.OBSERVE_MODULE_SLOTS)
        observation = self._read_observation(
            device_name,
            requirement,
            fresh_owned=fresh_owned,
        )
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

    def install_fallback_after_false(
        self,
        before: FactoryModuleObservation,
        rejected: FactoryModuleInstallation,
        *,
        observed_available_watts: float | None,
    ) -> FactoryModuleInstallation:
        """Try the next preobserved empty bay after a proven no-effect ``false``."""

        if (
            not isinstance(before, FactoryModuleObservation)
            or not isinstance(rejected, FactoryModuleInstallation)
            or self._observations.get(before.device_name) != before
            or self._installations.get(before.device_name) != rejected
        ):
            raise RuntimeError("Factory fallback inputs are stale or foreign")
        if before.device_name in self._fallback_consumed:
            raise RuntimeError("Factory module fallback was already consumed")
        if (
            not before.fresh_owned
            or rejected.native_ack is not False
            or not rejected.attempted
            or rejected.power_was_on is not True
            or rejected.power_restored is not True
            or rejected.target != before.target
        ):
            raise RuntimeError("Factory fallback requires one exact native false")
        requirement = self._require_policy(before.device_name, before.device_model)
        if (
            type(observed_available_watts) not in {int, float}
            or observed_available_watts != requirement.expected_available_watts_before
        ):
            raise RuntimeError("Factory fallback requires fresh Available 0 W evidence")

        self._fallback_consumed.add(before.device_name)
        current = self._read_observation(
            before.device_name,
            requirement,
            fresh_owned=True,
        )
        if (
            not current.observed
            or not current.supported_module_verified
            or _observation_guard(current) != _observation_guard(before)
        ):
            raise RuntimeError(
                "Factory fallback refused because inventory changed after native false"
            )
        ordered = sorted(
            before.candidate_targets,
            key=lambda item: (item.slot_index, item.container_navigation_path),
        )
        try:
            rejected_index = ordered.index(rejected.target)
        except ValueError as exc:
            raise RuntimeError("Factory fallback target was not preobserved") from exc
        if rejected_index + 1 >= len(ordered):
            raise RuntimeError("Factory fallback has no next preobserved empty slot")
        fallback_target = ordered[rejected_index + 1]
        current_slots = {
            (slot.container_navigation_path, slot.index): slot
            for slot in current.slots
        }
        fallback_slot = current_slots.get((
            fallback_target.container_navigation_path,
            fallback_target.slot_index,
        ))
        if (
            fallback_slot is None
            or fallback_slot.state is not FactoryModuleSlotState.EMPTY
        ):
            raise RuntimeError("Factory fallback target is no longer EMPTY")

        fallback_observation = replace(
            current,
            selected_target=fallback_target,
            target_determined=True,
        )
        self._operations.append(FactoryModuleOperation.INSTALL_FACTORY_MODULE)
        raw = self._send_and_wait(
            _install_factory_module_js(fallback_observation, requirement),
            self._mutation_timeout_seconds,
        )
        installation = _parse_installation(
            raw,
            fallback_observation,
            requirement,
            prior_rejected_targets=(rejected.target,),
            prior_rejection_no_effect_verified=True,
        )
        self._installations[before.device_name] = installation
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
        after = self._read_observation(
            before.device_name,
            requirement,
            fresh_owned=before.fresh_owned,
        )
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
        *,
        fresh_owned: bool = False,
    ) -> FactoryModulePreparationResult:
        """Satisfy the exact policy or return a closed refusal; never retry."""

        _validate_device_identity(device_name, device_model)
        _validate_fresh_owned(fresh_owned)
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

        observation = self.observe_required_module(
            device_name,
            device_model,
            fresh_owned=fresh_owned,
        )
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
        *,
        fresh_owned: bool,
    ) -> FactoryModuleObservation:
        raw = self._send_and_wait(
            _observe_module_slots_js(device_name),
            self._observation_timeout_seconds,
        )
        return _parse_observation(
            raw,
            device_name,
            requirement,
            fresh_owned=fresh_owned,
        )


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
    power_effect_verified = (
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
        and verification.installation.native_ack is True
        and verification.occupancy_effect_verified
        and verification.inventory_coherent
        and verification.identity_matches is not False
        and verification.factory_requirement_verified
        and power_effect_verified
    )
    return FactoryPowerHypothesisResult(
        confirmed=confirmed,
        requested_identity=verification.installation.requested_identity,
        native_ack=verification.installation.native_ack,
        occupancy_effect_verified=verification.occupancy_effect_verified,
        identity_observed=verification.identity_observed,
        observed_identity=verification.observed_identity,
        identity_matches=verification.identity_matches,
        factory_requirement_verified=verification.factory_requirement_verified,
        power_effect_verified=power_effect_verified,
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


def _validate_fresh_owned(fresh_owned: object) -> None:
    """Refuse truthiness where an authority decision is being made.

    Fresh-owned authority is what permits selecting one of several empty
    compatible bays. Accepting any truthy value would let a stray ``1`` or a
    ``"no"`` string buy that relaxation for a device that never earned it.
    """

    if type(fresh_owned) is not bool:
        raise TypeError("fresh_owned authority requires an exact boolean")


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
