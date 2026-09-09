"""Session observations for stage boundaries and cleanup; no acceptance policy."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ...application.cp_scale_live.contracts import (
    CP_SCALE_REALTIME_FIELDS,
    CPScaleDhcpStatisticsTarget,
    CPScaleObservationRecord,
    CPScaleRealtimeState,
)
from ...application.cp_scale_live.run_contracts import CPScaleCleanupRealtime
from ...application.cp_scale_live.voice_stage import realtime_boundary_error
from ...application.use_cases.compose_cp_scale_canonical import CPScaleCanonicalStage, CPScaleCanonicalStageProjection
from ..execution.ios_terminal import ControlledIosExecutor
from ..execution.simulation_trace_runtime import SimulationTraceRuntime
from .cp_scale_live import (
    _network_state_observation, _voice_dhcp_statistics_target,
    _dhcp_server_statistics_point, _voice_window_state,
    _stp_network_device_evidence,
)


@dataclass
class CPScaleActiveProjection:
    projection: CPScaleCanonicalStageProjection | None = None


def cleanup_realtime_state(value: dict[str, object] | None) -> CPScaleRealtimeState | None:
    if value is None:
        return None
    return CPScaleRealtimeState(value.get("observed"), value.get("simulation_mode"), value.get("frames"),
        value.get("sim_time"), value.get("current_index"), value.get("message"), value.get("mode"),
        tuple(name for name in CP_SCALE_REALTIME_FIELDS if name in value))


class PacketTracerCPScaleRunObservations:
    def __init__(self, transport, active: CPScaleActiveProjection) -> None:
        self.transport = transport
        self.active = active

    def activate(self, projection: CPScaleCanonicalStageProjection) -> None:
        self.active.projection = projection

    def before_delta(self, projection: CPScaleCanonicalStageProjection) -> CPScaleObservationRecord:
        return CPScaleObservationRecord("network_state", projection.stage, "coordinator", "observed",
            _network_state_observation(ControlledIosExecutor(self.transport.send_and_wait), projection, boundary="before_physical_delta"))

    def dhcp_target(self, projection: CPScaleCanonicalStageProjection) -> CPScaleDhcpStatisticsTarget | None:
        target = _voice_dhcp_statistics_target(projection.configuration, projection.voice)
        return CPScaleDhcpStatisticsTarget(**target) if target is not None else None

    def dhcp_baseline(self, target: CPScaleDhcpStatisticsTarget | None) -> CPScaleObservationRecord:
        if target is None:
            evidence = {"voice": None, "control": None, "failure_reason": "A unique Floor-1 voice DHCP statistics target with a control scope was unavailable."}
        else:
            evidence = _dhcp_server_statistics_point(ControlledIosExecutor(self.transport.send_and_wait), asdict(target))
        return CPScaleObservationRecord("dhcp_baseline", CPScaleCanonicalStage.ROUTER4_SWITCH10, "coordinator", "observed", evidence)

    def cleanup_realtime(self) -> CPScaleCleanupRealtime:
        try:
            raw = _voice_window_state(SimulationTraceRuntime(self.transport.send_and_wait))
            state = cleanup_realtime_state(raw)
            error = realtime_boundary_error(state, "after cleanup")
            return CPScaleCleanupRealtime(not error, error, state)
        except Exception as exc:
            return CPScaleCleanupRealtime(False, f"{type(exc).__name__}: {exc}")

    def trunk_transition(self, device_name: str) -> dict[str, object]:
        if self.active.projection is None:
            return {"device_name": device_name, "authoritative": False, "failure_reason": "NO_ACTIVE_CANONICAL_PROJECTION"}
        return _stp_network_device_evidence(ControlledIosExecutor(self.transport.send_and_wait), self.active.projection, device_name)
