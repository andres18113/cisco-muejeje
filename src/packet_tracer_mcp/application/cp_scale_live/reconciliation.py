"""Terminal cumulative workspace readback, never another physical deployment.

The outer coordinator already assembled the cumulative deployment manifest.
This collaborator observes that same accumulated topology exactly twice after
forwarding. It neither owns devices nor changes the physical runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..use_cases.qualify_cp_scale_live import canonical_stage_workspace_error
from ...domain.enterprise.models.physical_deployment import PhysicalWorkspaceObservation
from ...domain.models.plans import TopologyPlan
from .observation import CPScaleRequiredObservations


@dataclass(frozen=True)
class CPScaleReconciliationResult:
    first: PhysicalWorkspaceObservation | None
    second: PhysicalWorkspaceObservation | None
    errors: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return self.first is not None and self.second is not None and not any(self.errors)


class CPScaleReconciliation:
    def __init__(self, observations: CPScaleRequiredObservations) -> None:
        self.observations = observations

    def execute(self, topology: TopologyPlan) -> CPScaleReconciliationResult:
        first = None
        second = None
        try:
            first = self.observations.workspace()
            second = self.observations.workspace()
            errors = (
                canonical_stage_workspace_error(first, topology),
                canonical_stage_workspace_error(second, topology),
            )
        except Exception as exc:
            errors = (f"{type(exc).__name__}: {exc}",)
        return CPScaleReconciliationResult(first, second, errors)
