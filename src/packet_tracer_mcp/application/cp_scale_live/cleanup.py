"""CP-SCALE cleanup by attempted ownership, followed by two fresh reads."""
from __future__ import annotations

from .run_contracts import CPScaleCleanupResult
from ..use_cases.deploy_enterprise_topology import PhysicalTopologyRuntime
from ..use_cases.qualify_cp_scale_live import canonical_cleanup_restoration_error
from ...domain.models.plans import TopologyPlan
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentResult, PhysicalWorkspaceObservation,
    PhysicalObjectKind, PhysicalDeploymentItemStatus,
)


def attempted_device_ids(deployment: PhysicalDeploymentResult) -> frozenset[str]:
    return frozenset(item.target_id for item in deployment.item_results
                     if item.target_kind is PhysicalObjectKind.DEVICE
                     and item.status is not PhysicalDeploymentItemStatus.NOT_ATTEMPTED)


class CPScaleCleanup:
    def restore(self, physical: PhysicalTopologyRuntime, topology: TopologyPlan,
                owned: frozenset[str], baseline: PhysicalWorkspaceObservation) -> CPScaleCleanupResult:
        mutations: list[PhysicalMutationResult] = []
        first: PhysicalWorkspaceObservation | None = None
        second: PhysicalWorkspaceObservation | None = None
        try:
            for device in reversed(topology.devices):
                if device.id in owned:
                    mutations.append(physical.remove_device(device))
            first = physical.observe_workspace()
            second = physical.observe_workspace()
            restoration_error = canonical_cleanup_restoration_error(
                baseline,
                first,
                second,
            )
        except Exception as exc:
            return CPScaleCleanupResult(
                False,
                mutations=tuple(mutations),
                first=first,
                second=second,
                error=f"{type(exc).__name__}: {exc}",
            )
        return CPScaleCleanupResult(
            not restoration_error,
            restoration_error,
            tuple(mutations),
            first,
            second,
        )
