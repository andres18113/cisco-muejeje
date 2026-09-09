"""The authoritative stage Realtime window crosses application as typed facts."""
from __future__ import annotations

import json

import pytest

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


@pytest.mark.parametrize(
    "state",
    [
        None,
        pytest.param(
            {"observed": True, "simulation_mode": None, "present": ("observed", "simulation_mode")},
            id="missing-mode-value",
        ),
        pytest.param(
            {"observed": True, "simulation_mode": 0, "present": ("observed", "simulation_mode")},
            id="integer-mode",
        ),
        pytest.param(
            {"observed": 1, "simulation_mode": False, "present": ("observed", "simulation_mode")},
            id="integer-observed",
        ),
        pytest.param(
            {"observed": True, "simulation_mode": False, "present": ("observed",)},
            id="mode-value-without-presence",
        ),
        pytest.param(
            {"observed": True, "simulation_mode": False, "present": ("simulation_mode",)},
            id="observed-value-without-presence",
        ),
    ],
)
def test_realtime_rule_rejects_absent_mistyped_or_presence_inconsistent_state(
    state,
) -> None:
    from src.packet_tracer_mcp.application.cp_scale_live.contracts import (
        CPScaleRealtimeState,
    )
    from src.packet_tracer_mcp.application.cp_scale_live.voice_stage import (
        realtime_boundary_error,
    )

    value = CPScaleRealtimeState(**state) if isinstance(state, dict) else state

    assert realtime_boundary_error(value, "before")


def test_stage_stops_before_voice_when_realtime_mode_is_not_explicitly_false() -> None:
    from dataclasses import replace

    from src.packet_tracer_mcp.application.cp_scale_live.contracts import (
        CPScaleRealtimeState,
    )
    from src.packet_tracer_mcp.application.cp_scale_live.stage_executor import (
        CPScaleStageExecutor,
    )
    from tests.cp_scale_stage_fixture import stage_fixture
    from tests.test_voice_runtime import _compile

    fixture = stage_fixture(CPScaleStageExecutor)
    fixture.request = replace(
        fixture.request,
        projection=replace(fixture.request.projection, voice=_compile().plan),
    )
    invalid = CPScaleRealtimeState(
        observed=True,
        simulation_mode=None,
        present=("observed", "simulation_mode"),
    )
    calls: list[str] = []
    fixture.executor.observations.voice_window_state = lambda: invalid
    fixture.executor.voice.apply = lambda *args, **kwargs: calls.append("voice")

    result = fixture.executor.execute(fixture.request)

    assert result.outcome == "failed"
    assert result.first_failed_boundary == "voice"
    assert result.report.realtime is not None
    assert result.report.realtime.before.state is invalid
    assert result.report.realtime.before.error
    assert calls == []


@pytest.mark.parametrize(
    "raw",
    [
        {"observed": True},
        {"observed": True, "simulation_mode": None},
        {"observed": True, "simulation_mode": "false"},
    ],
)
def test_cleanup_consumer_fails_closed_for_incoherent_realtime_state(
    monkeypatch,
    raw,
) -> None:
    from src.packet_tracer_mcp.infrastructure.observation import cp_scale_live_run

    monkeypatch.setattr(cp_scale_live_run, "_voice_window_state", lambda runtime: raw)
    observations = cp_scale_live_run.PacketTracerCPScaleRunObservations(
        SimpleTransport(),
        cp_scale_live_run.CPScaleActiveProjection(),
    )

    result = observations.cleanup_realtime()

    assert result.verified is False
    assert result.error
    assert result.state is not None
    assert result.state.observed is True


class SimpleTransport:
    def send_and_wait(self, script, timeout):
        raise AssertionError("The controlled Realtime observation must not contact a transport")
