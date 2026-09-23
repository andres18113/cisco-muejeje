"""Measure the two additionally authorized C31 setup prerequisites."""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext

from pydantic import BaseModel, Field

from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilityVerificationMethod,
    ProbeExecutionStatus,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.enterprise.models.port_inventory import BackendVerifiedPortInventory
from ...infrastructure.catalog.enterprise_capabilities import (
    packet_tracer_enterprise_capability_adapter,
)
from .capability_discovery import CapabilityProbeRegistry
from .deploy_enterprise_topology import disposable_workspace_error
from .prepare_server_pt_commissioning import SERVER_PT_BUILD
from .qualify_port_inventories import (
    PortInventoryQualificationResult,
    PortInventoryQualifier,
    PortInventoryTarget,
)

_TOKEN = re.compile(r"[0-9a-f]{6,32}\Z")


class ServerPtPrequalificationResult(BaseModel):
    """Complete preliminary measurements; no catalog is changed here."""

    port_qualification: PortInventoryQualificationResult | None = None
    server_port_inventory: BackendVerifiedPortInventory | None = None
    trunk_probe: CapabilityProbeResult | None = None
    trunk_baseline: PhysicalWorkspaceObservation | None = None
    first_restoration: PhysicalWorkspaceObservation | None = None
    second_restoration: PhysicalWorkspaceObservation | None = None
    trunk_name: str = ""
    trunk_cleanup_applied: bool = False
    errors: list[str] = Field(default_factory=list)

    @property
    def ready_for_catalog_review(self) -> bool:
        """Whether both observations and both cleanup reads warrant review."""
        probe = self.trunk_probe
        baseline = self.trunk_baseline
        first = self.first_restoration
        second = self.second_restoration
        return bool(
            not self.errors
            and self.port_qualification is not None
            and self.port_qualification.restored is True
            and self.server_port_inventory is not None
            and probe is not None
            and probe.capability == "supports_trunk"
            and probe.status is CapabilityStatus.SUPPORTED
            and probe.execution_status is ProbeExecutionStatus.VERIFIED
            and probe.verified
            and probe.verification_method
            is CapabilityVerificationMethod.CLI_PLUS_READBACK
            and probe.packet_tracer_version == SERVER_PT_BUILD
            and self.trunk_cleanup_applied
            and baseline is not None
            and first is not None
            and second is not None
            and physical_workspace_restoration_matches(baseline, first)
            and physical_workspace_restoration_matches(baseline, second)
        )


def prequalify_server_pt(
    physical,
    trunk_runtime,
    *,
    attempt_token: str,
    cleanup_scope: Callable[[], AbstractContextManager[None]] | None = None,
) -> ServerPtPrequalificationResult:
    """Use existing qualifiers on one Server-PT and one 2950T-24 in turn."""
    if _TOKEN.fullmatch(attempt_token) is None:
        return ServerPtPrequalificationResult(errors=["invalid_prequalification_token"])
    cleanup_scope = cleanup_scope or nullcontext
    result = ServerPtPrequalificationResult()
    baseline = physical.observe_workspace()
    error = disposable_workspace_error(baseline)
    if error:
        result.errors.append(error)
        return result
    qualified = PortInventoryQualifier(
        physical, name_token=attempt_token, cleanup_scope=cleanup_scope
    ).qualify([PortInventoryTarget("Server-PT")])
    result.port_qualification = qualified
    if qualified.errors or qualified.restored is not True:
        result.errors.append("server_port_qualification_not_restored")
        return result
    if len(qualified.measurements) != 1:
        result.errors.append("server_port_measurement_missing")
        return result
    result.server_port_inventory = qualified.measurements[0].as_evidence(
        backend="packet_tracer",
        backend_version=SERVER_PT_BUILD,
        source=f"server-pt-c31-prequalification/{attempt_token}/observe_device",
    )
    if result.server_port_inventory is None:
        result.errors.append("server_port_inventory_unobservable")
        return result
    catalog = packet_tracer_enterprise_capability_adapter(SERVER_PT_BUILD)
    capabilities = catalog.capabilities_for("2950T-24", SERVER_PT_BUILD)
    if (
        capabilities is None
        or capabilities.supports_vlan is not CapabilityStatus.SUPPORTED
    ):
        result.errors.append("trunk_vlan_prerequisite_not_verified")
        return result
    trunk_baseline = physical.observe_workspace()
    result.trunk_baseline = trunk_baseline
    error = disposable_workspace_error(trunk_baseline)
    if error:
        result.errors.append(error)
        return result
    name = f"__MCP_PROBE_C31_{attempt_token}_TRUNK"
    result.trunk_name = name
    definition = CapabilityProbeRegistry().definitions_for(["supports_trunk"])[-1]
    created_exact = False
    try:
        observation = trunk_runtime.create_temporary_device("2950T-24", name)
        if (
            not observation.found
            or observation.runtime_id != "2950T-24"
            or observation.display_name != name
        ):
            result.errors.append("trunk_device_identity_unobservable")
        else:
            created_exact = True
            result.trunk_probe = trunk_runtime.probe_capability(
                name, "supports_trunk", definition
            ).model_copy(
                update={"model": "2950T-24", "packet_tracer_version": SERVER_PT_BUILD}
            )
    except Exception as exc:
        result.errors.append(f"trunk_probe_error:{type(exc).__name__}")
    finally:
        with cleanup_scope():
            if created_exact:
                try:
                    result.trunk_cleanup_applied = bool(
                        trunk_runtime.delete_temporary_device(name)
                    )
                except Exception as exc:
                    result.errors.append(f"trunk_cleanup_error:{type(exc).__name__}")
                if not result.trunk_cleanup_applied:
                    result.errors.append("trunk_cleanup_unverified")
            else:
                result.errors.append("trunk_creation_unverified_no_cleanup")
            try:
                result.first_restoration = physical.observe_workspace()
                result.second_restoration = physical.observe_workspace()
            except Exception as exc:
                result.errors.append(
                    f"trunk_restoration_unobservable:{type(exc).__name__}"
                )
    if not result.ready_for_catalog_review and not result.errors:
        result.errors.append("trunk_measurement_or_restoration_not_verified")
    return result
