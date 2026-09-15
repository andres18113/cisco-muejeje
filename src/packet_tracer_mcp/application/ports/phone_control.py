"""Frontera tipada entre E7 y cualquier mecanismo real de control telefónico."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...domain.enterprise.models.voice_plan import CallExpectation, VoicePlan
from ...domain.enterprise.models.voice_runtime import (
    PhoneExecutionMethod,
    RuntimeCallObservation,
)


@runtime_checkable
class PhoneControlPort(Protocol):
    """Ejecuta una llamada planificada sin exponer UI, clics ni coordenadas."""

    @property
    def execution_method(self) -> PhoneExecutionMethod: ...

    def bind_plan(self, plan: VoicePlan) -> None: ...

    def execute_call(
        self,
        expectation: CallExpectation,
        call_attempt_id: str,
        started_ns: int,
    ) -> RuntimeCallObservation: ...
