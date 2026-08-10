"""Adapter from immutable E7 call expectations to the closed phone-control port."""

from __future__ import annotations

from collections.abc import Callable
from time import time_ns
from uuid import uuid4

from ...application.ports.phone_control import PhoneControlPort
from ...domain.enterprise.models.voice_plan import VoicePlan
from ...domain.enterprise.models.voice_runtime import RuntimeCallObservation


class VoicePlanCallOperationAdapter:
    """Resolve only plan-owned IDs, leaving API/UI choice inside ``PhoneControl``."""

    def __init__(
        self,
        plan: VoicePlan,
        phone_control: PhoneControlPort,
        *,
        clock_ns: Callable[[], int] = time_ns,
        attempt_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._expectations = {item.id: item for item in plan.call_expectations}
        self._phone_control = phone_control
        self._clock_ns = clock_ns
        self._attempt_id_factory = attempt_id_factory or (
            lambda: f"call-{uuid4().hex}"
        )

    def execute_planned_call(
        self,
        call_expectation_id: str,
    ) -> RuntimeCallObservation:
        try:
            expectation = self._expectations[call_expectation_id]
        except KeyError as exc:
            raise ValueError(
                f"E7 call expectation {call_expectation_id!r} is not in the bound VoicePlan."
            ) from exc
        attempt_id = self._attempt_id_factory()
        started_ns = self._clock_ns()
        return self._phone_control.execute_call(
            expectation,
            attempt_id,
            started_ns,
        )
