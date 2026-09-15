"""Adaptadores cerrados para controlar teléfonos de Packet Tracer."""

from __future__ import annotations

from collections.abc import Callable

from ...domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ...domain.enterprise.models.voice_plan import CallExpectation, VoicePlan
from ...domain.enterprise.models.voice_runtime import (
    PhoneExecutionMethod,
    RuntimeCallObservation,
)


CallDriver = Callable[[CallExpectation, str, int], RuntimeCallObservation]


class UnavailablePhoneControl:
    """Representa la ausencia conocida de una API documentada de llamadas."""

    execution_method = PhoneExecutionMethod.UNOBSERVABLE

    def bind_plan(self, plan: VoicePlan) -> None:
        return None

    def execute_call(
        self,
        expectation: CallExpectation,
        call_attempt_id: str,
        started_ns: int,
    ) -> RuntimeCallObservation:
        return RuntimeCallObservation(
            call_expectation_id=expectation.id,
            call_attempt_id=call_attempt_id,
            source_phone_id=expectation.source_phone_id,
            destination_phone_id=expectation.expected_target_phone_id,
            dialed_extension=expectation.dialed_extension,
            status=ActionExecutionStatus.UNOBSERVABLE,
            connected=False,
            teardown_verified=False,
            observed_after_ns=started_ns,
            fresh_evidence=False,
            evidence_method="pt_documented_phone_control_api_unavailable",
            execution_method=self.execution_method,
            message=(
                "Packet Tracer phone control is unavailable: no documented structured "
                "API can dial, answer and hang up, so no call was attempted."
            ),
        )


class PacketTracerNativeUiPhoneControlAdapter:
    """Encapsula una automatización UI controlada detrás del puerto E7."""

    execution_method = PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI

    def __init__(self, driver: CallDriver) -> None:
        self._driver = driver

    def bind_plan(self, plan: VoicePlan) -> None:
        binder = getattr(self._driver, "bind_plan", None)
        if callable(binder):
            binder(plan)

    def execute_call(
        self,
        expectation: CallExpectation,
        call_attempt_id: str,
        started_ns: int,
    ) -> RuntimeCallObservation:
        observed = self._driver(expectation, call_attempt_id, started_ns)
        identity_matches = bool(
            observed.call_expectation_id == expectation.id
            and observed.call_attempt_id == call_attempt_id
            and observed.source_phone_id == expectation.source_phone_id
            and observed.destination_phone_id == expectation.expected_target_phone_id
            and observed.dialed_extension == expectation.dialed_extension
            and observed.observed_after_ns >= started_ns
        )
        if not identity_matches:
            observed = RuntimeCallObservation(
                call_expectation_id=expectation.id,
                call_attempt_id=call_attempt_id,
                source_phone_id=expectation.source_phone_id,
                destination_phone_id=expectation.expected_target_phone_id,
                dialed_extension=expectation.dialed_extension,
                status=ActionExecutionStatus.UNOBSERVABLE,
                observed_after_ns=started_ns,
                fresh_evidence=False,
                evidence_method="native_ui_driver_observation_identity_invalid",
                message=(
                    "The native-UI driver returned a foreign or stale call "
                    "observation; no call behavior is claimed."
                ),
            )
        return observed.model_copy(update={"execution_method": self.execution_method})


class StructuredPhoneControlAdapter:
    """Reserva tipada para un backend que sí ofrezca control estructurado."""

    execution_method = PhoneExecutionMethod.STRUCTURED_API

    def __init__(self, driver: CallDriver) -> None:
        self._driver = driver

    def bind_plan(self, plan: VoicePlan) -> None:
        binder = getattr(self._driver, "bind_plan", None)
        if callable(binder):
            binder(plan)

    def execute_call(
        self,
        expectation: CallExpectation,
        call_attempt_id: str,
        started_ns: int,
    ) -> RuntimeCallObservation:
        observed = self._driver(expectation, call_attempt_id, started_ns)
        return observed.model_copy(update={"execution_method": self.execution_method})
