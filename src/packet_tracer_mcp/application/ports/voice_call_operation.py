"""Typed E7 call operation consumable by downstream application layers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...domain.enterprise.models.voice_runtime import RuntimeCallObservation


@runtime_checkable
class VoiceCallOperationPort(Protocol):
    """Execute one call already identified by an immutable E7 ``VoicePlan``."""

    def execute_planned_call(
        self,
        call_expectation_id: str,
    ) -> RuntimeCallObservation: ...
