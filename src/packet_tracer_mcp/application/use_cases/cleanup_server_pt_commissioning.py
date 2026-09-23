"""Remove only proven C31 E4 devices and observe restoration twice."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...domain.enterprise.models.execution import MutationDisposition
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentResult,
    PhysicalMutationResult,
    PhysicalWorkspaceObservation,
    ServerPtCleanupResult,
    physical_workspace_restoration_matches,
)
from ...domain.models.plans import DevicePlan, TopologyPlan
from ...infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from .deploy_enterprise_topology import disposable_workspace_error


class CleanupPhysicalRuntime(Protocol):
    """The existing physical runtime with verified E4 ownership adoption."""

    def adopt_verified_deployment_for_cleanup(
        self, topology: TopologyPlan, deployment: PhysicalDeploymentResult
    ) -> frozenset[str]:
        """Return only the names proved owned by a complete E4 result."""
        ...

    def observe_workspace(self) -> PhysicalWorkspaceObservation:
        """Read the complete current workspace without mutation."""
        ...

    def remove_device(self, device: DevicePlan) -> PhysicalMutationResult:
        """Remove an exactly owned device or report an unknown result."""
        ...


def _workspace_matches_plan(
    topology: TopologyPlan, workspace: PhysicalWorkspaceObservation
) -> bool:
    """Require every semantic device and link, with no foreign additions."""
    if not workspace.observed:
        return False
    if any(
        item.model.strip().casefold() != "power distribution device" or item.ports
        for item in workspace.backend_managed_devices
    ):
        return False
    expected_devices = {(item.name, item.model) for item in topology.devices}
    found_devices = {(item.name, item.model) for item in workspace.semantic_devices}
    if (
        len(workspace.semantic_devices) != len(expected_devices)
        or found_devices != expected_devices
    ):
        return False

    def endpoints(a: str, pa: str, b: str, pb: str):
        return frozenset(((a, pa), (b, pb)))

    expected_links = {
        endpoints(item.device_a, item.port_a, item.device_b, item.port_b)
        for item in topology.links
    }
    found_links = {
        endpoints(item.device_a, item.port_a, item.device_b, item.port_b)
        for item in workspace.links
    }
    return len(workspace.links) == len(expected_links) and found_links == expected_links


def run_server_pt_cleanup(
    attempt_id: str,
    *,
    store: ServerPtCommissioningStore,
    physical_runtime: CleanupPhysicalRuntime,
    admission: Callable[[], tuple[str, ...]],
) -> ServerPtCleanupResult:
    """Keep each removal and two restoration reads; never replay unknowns."""
    result = ServerPtCleanupResult(attempt_id=attempt_id)

    def finish() -> ServerPtCleanupResult:
        try:
            store.save_cleanup(attempt_id, result)
        except (OSError, ValueError) as exc:
            result.restored = False
            result.errors.append(f"cleanup_persistence_failed:{type(exc).__name__}")
        return result

    if store.record_path_for(attempt_id, "precleanup").exists():
        result.errors.append("cleanup_attempt_already_started")
        return result
    try:
        bundle = store.load_bundle(attempt_id)
        baseline = store.load_baseline(attempt_id)
        deployment = store.load_e4(attempt_id)
        topology = TopologyPlan.model_validate_json(bundle.topology_json)
    except (OSError, ValueError) as exc:
        result.errors.append(f"cleanup_input_unavailable:{type(exc).__name__}")
        return finish()
    result.deployment_id = deployment.deployment_id
    if disposable_workspace_error(baseline):
        result.errors.append("cleanup_baseline_not_empty")
        return finish()
    reasons = admission()
    if reasons:
        result.errors.append("cleanup_admission:" + ",".join(reasons))
        return finish()
    try:
        owned = physical_runtime.adopt_verified_deployment_for_cleanup(
            topology, deployment
        )
    except ValueError as exc:
        result.errors.append(f"cleanup_ownership_unverified:{exc}")
        return finish()
    if owned != frozenset(device.name for device in topology.devices):
        result.errors.append("cleanup_owned_targets_mismatch")
        return finish()
    try:
        result.precleanup = physical_runtime.observe_workspace()
        store.save_precleanup(attempt_id, result.precleanup)
    except (OSError, ValueError) as exc:
        result.errors.append(f"precleanup_unavailable:{type(exc).__name__}")
        return finish()
    if not _workspace_matches_plan(topology, result.precleanup):
        result.errors.append("precleanup_workspace_drift")
        return finish()

    for index, device in enumerate(reversed(topology.devices)):
        reasons = admission()
        if reasons:
            result.errors.append("cleanup_admission:" + ",".join(reasons))
            break
        try:
            removal = physical_runtime.remove_device(device)
            result.removals.append(removal)
            store.save_cleanup_item(attempt_id, index, removal)
        except Exception as exc:
            result.errors.append(f"cleanup_device_unobservable:{type(exc).__name__}")
            break
        if not (removal.applied and removal.disposition is MutationDisposition.CHANGED):
            result.errors.append(f"cleanup_device_not_removed:{device.name}")
            break

    if not result.errors:
        try:
            result.first_restoration = physical_runtime.observe_workspace()
            result.second_restoration = physical_runtime.observe_workspace()
        except Exception as exc:
            result.errors.append(
                f"cleanup_restoration_unobservable:{type(exc).__name__}"
            )
    result.restored = bool(
        not result.errors
        and result.first_restoration is not None
        and result.second_restoration is not None
        and physical_workspace_restoration_matches(baseline, result.first_restoration)
        and physical_workspace_restoration_matches(baseline, result.second_restoration)
    )
    if not result.restored and not result.errors:
        result.errors.append("cleanup_restoration_mismatch")
    return finish()
