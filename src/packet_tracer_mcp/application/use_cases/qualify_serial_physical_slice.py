"""Disposable Stage 3A4 Slice 2A physical-product qualification.

This harness only orchestrates production runtime and deployment seams.  It
renders no Packet Tracer mutation itself, inventories before deployment, and
finally removes only exact device names whose product ensure was attempted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import time
from typing import Protocol
import re

from pydantic import BaseModel, Field

from .deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
    PhysicalTopologyRuntime,
)
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.execution import MutationDisposition
from ...domain.enterprise.models.execution import CompensationStatus
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentFailureCode,
    PhysicalDeploymentResult,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.models.plans import DevicePlan, TopologyPlan


_DISPOSABLE_DEVICE_NAME = re.compile(r"^MCP-PROBE-[A-Za-z0-9_.-]{1,53}$")


class DisposablePhysicalTopologyRuntime(PhysicalTopologyRuntime, Protocol):
    def remove_device(self, device: DevicePlan) -> PhysicalMutationResult: ...


class SerialPhysicalSliceQualificationStatus(str, Enum):
    VERIFIED_CLEAN = "verified_clean"
    FAILED_CLEAN = "failed_clean"
    UNKNOWN_CLEAN = "unknown_clean"
    HARD_STOP = "hard_stop"
    DIRTY_UNKNOWN = "dirty_unknown"


class SerialPhysicalSliceQualificationResult(BaseModel):
    status: SerialPhysicalSliceQualificationStatus
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    inventory_restored: bool | None = None
    deployment: PhysicalDeploymentResult
    cleanup_results: list[PhysicalMutationResult] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime
    errors: list[str] = Field(default_factory=list)

    def compact_summary(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "baseline_inventory": (
                self.baseline_inventory.compact_summary()
                if self.baseline_inventory else None
            ),
            "deployment": self.deployment.compact_summary(),
            "cleanup": [item.model_dump(mode="json") for item in self.cleanup_results],
            "final_inventory": (
                self.final_inventory.compact_summary() if self.final_inventory else None
            ),
            "inventory_restored": self.inventory_restored,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "errors": list(self.errors),
        }


class _TrackingRuntime:
    """Delegate product calls while recording only attempted device creation."""

    def __init__(self, runtime: DisposablePhysicalTopologyRuntime) -> None:
        self._runtime = runtime
        self.baseline_inventory: PhysicalWorkspaceObservation | None = None
        self.attempted_devices: list[DevicePlan] = []
        self.device_ensure_started = False

    def observe_workspace(self) -> PhysicalWorkspaceObservation:
        observation = self._runtime.observe_workspace()
        if self.baseline_inventory is None:
            self.baseline_inventory = observation.model_copy(deep=True)
        return observation

    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult:
        self.device_ensure_started = True
        if all(item.name != device.name for item in self.attempted_devices):
            self.attempted_devices.append(device.model_copy(deep=True))
        try:
            result = self._runtime.ensure_device(device)
        except Exception as exc:
            # The call crossed the mutation boundary but returned no receipt.
            # The exact name was absent in the baseline, so existing probe
            # precedent permits one finally-protected exact cleanup attempt.
            return PhysicalMutationResult(
                target_id=device.id or device.name,
                target_kind=PhysicalObjectKind.DEVICE,
                disposition=MutationDisposition.UNKNOWN,
                message=f"Device creation raised without a receipt: {exc}",
            )
        if result.disposition not in {
            MutationDisposition.CHANGED,
            MutationDisposition.UNKNOWN,
        }:
            self.attempted_devices = [
                item for item in self.attempted_devices if item.name != device.name
            ]
        if result.disposition in {
            MutationDisposition.NO_OP,
            MutationDisposition.REASSERTED,
        }:
            return result.model_copy(update={
                "disposition": MutationDisposition.FAILED,
                "applied": False,
                "message": (
                    "Disposable workspace changed after the empty inventory: "
                    f"device {device.name!r} unexpectedly already existed."
                ),
            })
        return result

    def __getattr__(self, name: str):
        return getattr(self._runtime, name)


def qualify_serial_physical_slice(
    runtime: DisposablePhysicalTopologyRuntime,
    topology: TopologyPlan,
    *,
    environment_fingerprint: EnvironmentFingerprint,
    deployment_id: str = "",
    restoration_timeout_seconds: float = 5.0,
) -> SerialPhysicalSliceQualificationResult:
    """Run and clean one bounded 2x2911/module/serial-link qualification."""

    started_at = datetime.now(timezone.utc)
    _validate_slice_shape(topology)
    tracker = _TrackingRuntime(runtime)
    cleanup_results: list[PhysicalMutationResult] = []
    final_inventory: PhysicalWorkspaceObservation | None = None
    inventory_restored: bool | None = None
    errors: list[str] = []
    deployment: PhysicalDeploymentResult | None = None
    unexpected: Exception | None = None

    try:
        deployment = EnterprisePhysicalTopologyDeployer(tracker).deploy(
            topology,
            environment_fingerprint=environment_fingerprint,
            deployment_id=deployment_id,
            require_empty_workspace=True,
        )
    except Exception as exc:  # finally still owns exact attempted-name cleanup
        unexpected = exc
    finally:
        for device in reversed(tracker.attempted_devices):
            try:
                cleanup_results.append(runtime.remove_device(device))
            except Exception as exc:
                errors.append(f"Cleanup failed for {device.name!r}: {exc}")

        baseline = tracker.baseline_inventory
        if tracker.device_ensure_started and baseline is not None:
            deadline = time.monotonic() + max(0.0, restoration_timeout_seconds)
            while True:
                try:
                    final_inventory = runtime.observe_workspace()
                except Exception as exc:
                    errors.append(f"Final workspace inventory failed: {exc}")
                    final_inventory = None
                if final_inventory is not None and physical_workspace_restoration_matches(
                    baseline,
                    final_inventory,
                ):
                    inventory_restored = True
                    break
                if time.monotonic() >= deadline:
                    inventory_restored = (
                        False
                        if final_inventory is not None and final_inventory.observed
                        else None
                    )
                    break
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        elif (
            not tracker.attempted_devices
            and baseline is not None
            and baseline.observed
        ):
            final_inventory = baseline.model_copy(deep=True)
            inventory_restored = True

    if unexpected is not None:
        cleanup_note = (
            "cleanup/restoration succeeded"
            if inventory_restored is True else "cleanup/restoration is unknown"
        )
        raise RuntimeError(
            f"Unexpected Slice 2A deployment failure; {cleanup_note}: {unexpected}"
        ) from unexpected
    assert deployment is not None

    unknown_history = any(
        item.disposition is MutationDisposition.UNKNOWN
        for item in deployment.item_results
    )

    if tracker.device_ensure_started:
        if inventory_restored is True and cleanup_results and all(
            item.disposition in {MutationDisposition.CHANGED, MutationDisposition.NO_OP}
            for item in cleanup_results
        ):
            deployment.execution_journal.mark_cleanup(CompensationStatus.SUCCEEDED)
        elif inventory_restored is None or any(
            item.disposition is MutationDisposition.UNKNOWN
            for item in cleanup_results
        ):
            deployment.execution_journal.mark_cleanup(CompensationStatus.UNKNOWN)
        else:
            deployment.execution_journal.mark_cleanup(CompensationStatus.FAILED)
        deployment.dirty_state = deployment.execution_journal.dirty_state

    if deployment.failure_code in {
        PhysicalDeploymentFailureCode.WORKSPACE_NOT_EMPTY,
        PhysicalDeploymentFailureCode.WORKSPACE_OBSERVATION_FAILED,
    }:
        status = SerialPhysicalSliceQualificationStatus.HARD_STOP
    elif not tracker.device_ensure_started:
        status = SerialPhysicalSliceQualificationStatus.FAILED_CLEAN
    else:
        cleanup_known = len(cleanup_results) == len(tracker.attempted_devices) and all(
            item.target_kind is PhysicalObjectKind.DEVICE
            and item.target_id == (device.id or device.name)
            and item.disposition in {
                MutationDisposition.CHANGED,
                MutationDisposition.NO_OP,
            }
            and (
                item.disposition is MutationDisposition.NO_OP or item.applied
            )
            for item, device in zip(
                cleanup_results,
                reversed(tracker.attempted_devices),
                strict=True,
            )
        )
        clean = cleanup_known and inventory_restored is True and not errors
        if not clean:
            status = SerialPhysicalSliceQualificationStatus.DIRTY_UNKNOWN
        elif unknown_history:
            status = SerialPhysicalSliceQualificationStatus.UNKNOWN_CLEAN
        elif deployment.manifest is not None:
            status = SerialPhysicalSliceQualificationStatus.VERIFIED_CLEAN
        else:
            status = SerialPhysicalSliceQualificationStatus.FAILED_CLEAN

    return SerialPhysicalSliceQualificationResult(
        status=status,
        baseline_inventory=tracker.baseline_inventory,
        final_inventory=final_inventory,
        inventory_restored=inventory_restored,
        deployment=deployment,
        cleanup_results=cleanup_results,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        errors=[*deployment.errors, *errors],
    )


def _validate_slice_shape(topology: TopologyPlan) -> None:
    if len(topology.devices) != 2 or any(
        device.model != "2911" for device in topology.devices
    ):
        raise ValueError("Slice 2A qualification requires exactly two 2911 routers.")
    if any(_DISPOSABLE_DEVICE_NAME.fullmatch(device.name) is None for device in topology.devices):
        raise ValueError("Slice 2A requires exact disposable MCP-PROBE-* names.")
    if len(topology.modules) != 2 or {
        (module.device, module.slot, module.module) for module in topology.modules
    } != {
        (device.name, "0/0", "HWIC-2T") for device in topology.devices
    }:
        raise ValueError("Slice 2A requires one requested HWIC-2T in slot 0/0 per router.")
    if len(topology.links) != 1:
        raise ValueError("Slice 2A qualification requires exactly one physical link.")
    link = topology.links[0]
    device_names = {device.name for device in topology.devices}
    if (
        {link.device_a, link.device_b} != device_names
        or not link.port_a.startswith("Serial")
        or not link.port_b.startswith("Serial")
        or link.cable.casefold() != "serial"
    ):
        raise ValueError("Slice 2A link must be one serial WAN between the two routers.")
