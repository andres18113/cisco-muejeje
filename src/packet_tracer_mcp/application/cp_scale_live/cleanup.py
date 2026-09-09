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
        mutations = tuple(physical.remove_device(device) for device in reversed(topology.devices) if device.id in owned)
        first = physical.observe_workspace()
        second = physical.observe_workspace()
        error = canonical_cleanup_restoration_error(baseline, first, second)
        return CPScaleCleanupResult(not error, error, mutations, first, second)
