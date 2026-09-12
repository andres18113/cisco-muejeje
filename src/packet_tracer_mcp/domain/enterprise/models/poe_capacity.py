"""Passive models for a governed PoE capacity qualification plan."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .capabilities import PoEAuthorizedBinding
from .poe2 import PoE2Capture


class PoE3BCapture(PoE2Capture):
    """Closed capture vocabulary for capacity plus its causal PSU boundary."""

    label: Literal[
        "PSU_BEFORE", "PSU_AFTER_NATIVE_FALSE", "PSU_AFTER",
        "AUTO_1", "NEVER", "AUTO_2", "RESTORE",
    ]


class PoEModelQualificationPlan(BaseModel):
    """Exact simultaneous powered bindings to qualify for one switch model."""

    packet_tracer_build: str
    candidate_model: str
    bindings: tuple[PoEAuthorizedBinding, ...]
    simultaneous_active_ports: int


class PoECapacityQualificationPlan(BaseModel):
    """Model-specific qualification scopes derived for one canonical stage."""

    packet_tracer_build: str
    target_stage: str
    models: tuple[PoEModelQualificationPlan, ...]

    def for_model(self, candidate_model: str) -> PoEModelQualificationPlan:
        """Return only an exact governed model scope; absence is not authority."""

        for plan in self.models:
            if plan.candidate_model == candidate_model:
                return plan
        raise ValueError(
            f"No governed PoE capacity qualification plan exists for "
            f"{candidate_model!r}."
        )
