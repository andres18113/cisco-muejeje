"""Passive models for a governed PoE capacity qualification plan."""

from __future__ import annotations

from pydantic import BaseModel

from .capabilities import PoEAuthorizedBinding


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
