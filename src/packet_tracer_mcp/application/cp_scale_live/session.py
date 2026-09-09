"""Named session/observation ports; runtime resources share a single lifecycle."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import CPScaleDhcpStatisticsTarget, CPScaleObservationRecord
from .run_contracts import CPScaleCleanupRealtime, CPScaleBridgeStatus
from ..use_cases.apply_configuration import ConfigurationRuntime
from ..use_cases.apply_control_plane import ControlPlaneRuntime
from ..use_cases.apply_voice import VoiceRuntime
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStageProjection
from ..use_cases.deploy_enterprise_topology import PhysicalTopologyRuntime


class CPScaleRunObservationPort(Protocol):
    def activate(self, projection: CPScaleCanonicalStageProjection) -> None: ...
    def before_delta(self, projection: CPScaleCanonicalStageProjection) -> CPScaleObservationRecord: ...
    def dhcp_target(self, projection: CPScaleCanonicalStageProjection) -> CPScaleDhcpStatisticsTarget | None: ...
    def dhcp_baseline(self, target: CPScaleDhcpStatisticsTarget | None) -> CPScaleObservationRecord: ...
    def cleanup_realtime(self) -> CPScaleCleanupRealtime: ...


@dataclass(frozen=True)
class CPScaleRuntimeResources:
    configuration: ConfigurationRuntime
    control_plane: ControlPlaneRuntime
    voice: VoiceRuntime


class CPScaleSessionPort(Protocol):
    @property
    def physical(self) -> PhysicalTopologyRuntime | None: ...
    @property
    def connected(self) -> bool: ...
    @property
    def channel(self) -> str: ...
    def start(self) -> bool: ...
    def status(self) -> CPScaleBridgeStatus: ...
    def acquire_runtimes(self) -> CPScaleRuntimeResources: ...
    def close(self) -> None: ...
