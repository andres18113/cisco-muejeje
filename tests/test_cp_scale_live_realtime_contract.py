"""The authoritative stage Realtime window crosses application as typed facts."""
from __future__ import annotations

import json

from tests.cp_scale_stage_fixture import voice_window_trace


def test_stage_window_retains_typed_required_observations_and_compatible_evidence() -> None:
    from src.packet_tracer_mcp.application.cp_scale_live import contracts
    from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_stage_evidence import (
        stage_result_evidence,
    )

    assert hasattr(contracts, "CPScaleRealtimeObservation")
    result, trace = voice_window_trace()
    window = result.report.realtime

    assert trace[:4] == ["before", "stp_before", "voice", "stp_after"]
    assert isinstance(window.before, contracts.CPScaleRealtimeObservation)
    assert isinstance(window.before.state, contracts.CPScaleRealtimeState)
    assert window.before.authority == "REQUIRED_STAGE_OBSERVATION"
    assert window.before.provenance == "required_stage_observation"
    assert window.before.error == ""
    assert window.after is not None
    assert isinstance(window.after, contracts.CPScaleRealtimeObservation)
    assert result.required_observations.count(window.before) == 1
    assert result.required_observations.count(window.after) == 1
    evidence = stage_result_evidence(result)["voice_realtime_continuity"]
    assert evidence["before"] == {"observed": True, "simulation_mode": False}
    assert evidence["after"] == {"observed": True, "simulation_mode": False}
    assert evidence["verified"] is True


def test_failed_after_boundary_preserves_typed_absence_error_and_authority() -> None:
    from src.packet_tracer_mcp.application.cp_scale_live import contracts

    result, _ = voice_window_trace(after_simulating=True)
    window = result.report.realtime

    assert isinstance(window.after, contracts.CPScaleRealtimeObservation)
    assert window.after.state.simulation_mode is True
    assert window.after.error == window.failure_reason
    assert "Simulation mode after" in window.failure_reason
    assert window.after.authority == "REQUIRED_STAGE_OBSERVATION"
    assert result.first_failed_boundary == "voice"


def test_packet_tracer_observation_adapter_converts_runtime_state_field_by_field() -> None:
    from src.packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleRealtimeState
    from src.packet_tracer_mcp.infrastructure.observation.cp_scale_live import (
        PacketTracerCPScaleObservations,
    )

    class Transport:
        def send_and_wait(self, script, timeout):
            return json.dumps({
                "mode": False,
                "frames": 7,
                "sim_time": 0,
                "current_index": 0,
            })

    state = PacketTracerCPScaleObservations(Transport(), object()).voice_window_state()

    assert isinstance(state, CPScaleRealtimeState)
    assert state.observed is True
    assert state.simulation_mode is False
    assert state.frames == 7
    assert state.sim_time == 0
    assert state.current_index == 0
    assert state.message == "simulation_state_readback"
    assert state.present == (
        "observed", "simulation_mode", "frames", "sim_time", "current_index", "message",
    )
