"""Named required reads. Implementations own concrete IOS/bridge mechanics."""

from __future__ import annotations

from typing import Protocol

from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStageProjection, CPScaleSiteForwardingCheck
from ..use_cases.observe_serial_orientation import SerialOrientationResult
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.physical_deployment import PhysicalWorkspaceObservation
from ...domain.models.plans import TopologyPlan
from .contracts import (
    CPScaleDiagnosticRecord, CPScaleDiagnosticRequest, CPScaleDhcpStatisticsTarget,
    CPScaleObservationRecord, CPScaleCoreForwardingObservation, CPScaleSiteForwardingObservation,
)


class CPScaleRequiredObservations(Protocol):
    def network_state(self, projection: CPScaleCanonicalStageProjection, *, boundary: str) -> dict[str, object]: ...
    def serial_orientation(
        self, projection: CPScaleCanonicalStageProjection, manifest: DeploymentManifest,
        verified_topology: TopologyPlan | None, verified_manifest: DeploymentManifest | None,
    ) -> SerialOrientationResult: ...
    def serial_interfaces(self, projection: CPScaleCanonicalStageProjection) -> tuple[bool, list[dict[str, object]]]: ...
    def voice_window_state(self) -> dict[str, object]: ...
    def stp(self, projection: CPScaleCanonicalStageProjection, *, edge: str) -> dict[str, object]: ...
    def bindings(self, projection: CPScaleCanonicalStageProjection) -> list[dict[str, object]]: ...
    def dhcp_exchange(
        self, bindings: list[dict[str, object]], target: CPScaleDhcpStatisticsTarget,
        baseline: CPScaleObservationRecord,
    ) -> dict[str, object]: ...
    def core_forwarding(self, checks: dict[str, str]) -> tuple[CPScaleCoreForwardingObservation, ...]: ...
    def site_forwarding(self, checks: tuple[CPScaleSiteForwardingCheck, ...]) -> tuple[CPScaleSiteForwardingObservation, ...]: ...
    def workspace(self) -> PhysicalWorkspaceObservation: ...


class CPScaleDiagnosticPort(Protocol):
    def diagnose(self, request: CPScaleDiagnosticRequest) -> CPScaleDiagnosticRecord: ...
