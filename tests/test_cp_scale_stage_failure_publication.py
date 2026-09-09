"""Acquired stage failures survive real execution and evidence publication."""

from __future__ import annotations

from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.application.cp_scale_live.contracts import (
    CPScaleCoreForwardingObservation, CPScaleDiagnosticRecord,
    CPScaleDhcpStatisticsTarget, CPScaleObservationRecord,
    CPScaleRealtimeState, CPScaleSiteForwardingObservation,
)
from src.packet_tracer_mcp.application.cp_scale_live.stage_executor import CPScaleStageExecutor
from src.packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleForwardingAuthority, CPScaleSiteForwardingCheck,
)
from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_stage_evidence import stage_result_evidence
from tests.cp_scale_stage_fixture import stage_fixture
from tests.test_voice_runtime import FakeVoiceRuntime, _compile, _profile


@pytest.mark.parametrize("surface", ["core", "site"])
def test_zero_attempt_forwarding_failure_survives_real_stage_publication(surface):
    fixture = stage_fixture(CPScaleStageExecutor)
    check = CPScaleSiteForwardingCheck(
        "missing-check", "forward", CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW,
        "flow", "", "a", "b", "r", "R", "p", "P", "router", "address", "segment",
        "10.1.0.2", "synthetic-physical", "synthetic-configuration",
    )
    if surface == "core":
        fixture.request = replace(fixture.request, projection=replace(
            fixture.request.projection, forwarding_checks={"R": "10.1.0.2"},
        ))
        fixture.executor.observations.core_forwarding = lambda checks: (
            CPScaleCoreForwardingObservation("R", "10.1.0.2", (), True),
        )
        expected_failure = "Core forwarding regressed at 'routing-core'."
    else:
        fixture.request = replace(fixture.request, site_forwarding_checks=(check,))
        fixture.executor.observations.site_forwarding = lambda checks: (
            CPScaleSiteForwardingObservation(check, (), True),
        )
        expected_failure = "Site forwarding failed at 'routing-core'; first failed check: missing-check."

    result = fixture.executor.execute(fixture.request)
    assert result.failure == expected_failure
    assert result.first_failed_boundary == "forwarding"
    assert result.configuration is fixture.configuration_results[0]
    assert result.control_plane is fixture.control_results[0]
    evidence = stage_result_evidence(result)

    assert result.failure == expected_failure
    assert evidence["configuration"] == result.configuration.model_dump(mode="json")
    assert evidence["control_plane"] == result.control_plane.model_dump(mode="json")
    assert evidence["physical"] == result.deployment.model_dump(mode="json")
    assert evidence[surface + "_forwarding_verified"] is False
    if surface == "core":
        ping = evidence["core_forwarding"]["R"]
    else:
        assert evidence["site_forwarding_first_failure"] == check.id
        assert evidence["site_forwarding"][0]["check"] == asdict(check)
        assert evidence["site_forwarding"][0]["verified"] is False
        ping = evidence["site_forwarding"][0]["result"]
    assert ping["attempts"] == 0
    assert ping["fresh_output_observed"] is False
    assert ping["reachable"] is False
    assert ping["device_identity_provenance"] == "not_observed"
    assert ping["failure_reason"] == "No typed forwarding attempt was acquired."
    assert "workspace_first" not in evidence


def _acquired_voice_failure(*, failing=(), after_state=None, monkeypatch):
    """Real E7 acquires its E4 mismatch; only subsequent I/O is controlled."""
    fixture = stage_fixture(CPScaleStageExecutor)
    fixture.request = replace(
        fixture.request,
        projection=replace(fixture.request.projection, voice=_compile().plan),
        composition=replace(fixture.request.composition, voice_capabilities=_profile()),
        dhcp_statistics_target=CPScaleDhcpStatisticsTarget("R"),
        dhcp_statistics_baseline=CPScaleObservationRecord(
            "dhcp_baseline", fixture.request.projection.stage, "synthetic", "observed", {},
        ),
    )
    runtime = FakeVoiceRuntime()
    fixture.executor.voice.applicator = VoiceApplicator(runtime)
    fixture.executor.voice.runtime = runtime
    states = iter([
        CPScaleRealtimeState(
            observed=True,
            simulation_mode=False,
            present=("observed", "simulation_mode"),
        ),
        after_state if after_state is not None else CPScaleRealtimeState(
            observed=True,
            simulation_mode=False,
            present=("observed", "simulation_mode"),
        ),
    ])
    fixture.executor.observations.voice_window_state = lambda: next(states)
    observed = []

    def observation(operation, result):
        observed.append(operation)
        if operation in failing:
            raise RuntimeError("secondary " + operation + " unavailable")
        return result

    fixture.executor.observations.bindings = lambda projection: observation("bindings", [])
    fixture.executor.observations.dhcp_exchange = lambda *args: observation("statistics", {})
    from src.packet_tracer_mcp.application.cp_scale_live import stage_executor
    correlate = stage_executor.canonical_cp_scale_voice_evidence

    def correlation(**kwargs):
        observation("correlation", None)
        return correlate(**kwargs)

    monkeypatch.setattr(stage_executor, "canonical_cp_scale_voice_evidence", correlation)
    diagnostic_requests = []

    def diagnose(request):
        observed.append("diagnostic")
        diagnostic_requests.append(request)
        return CPScaleDiagnosticRecord(request.projection.stage, {"status": "ATTEMPTED"})

    fixture.executor.diagnostics = SimpleNamespace(diagnose=diagnose)
    return fixture, observed, diagnostic_requests


@pytest.mark.parametrize("failing", [("bindings",), ("statistics",), ("correlation",), ("statistics", "correlation")])
def test_attributable_voice_cause_precedes_secondary_observation_errors(failing, monkeypatch):
    fixture, observed, diagnostics = _acquired_voice_failure(failing=failing, monkeypatch=monkeypatch)
    result = fixture.executor.execute(fixture.request)
    assert result.voice is not None
    assert "VoicePlan source hash does not match deployed E4." in result.voice.preflight_errors
    assert result.report.realtime.verified is True
    assert result.failure == "Voice at 'routing-core' did not close: " + result.report.voice.error
    assert result.first_failed_boundary == "voice"
    assert [(item.operation, item.error) for item in result.secondary_failures] == [
        (operation, "RuntimeError: secondary " + operation + " unavailable") for operation in failing
    ]
    assert len(diagnostics) == 1
    assert len(result.diagnostics) <= fixture.request.diagnostic_attempt_limit
    assert len(result.secondary_failures) <= fixture.request.secondary_failure_limit
    assert len(result.required_observations) <= fixture.request.required_observation_limit
    assert diagnostics[0].voice.result is result.voice
    assert diagnostics[0].realtime_failure_established is True
    assert observed == (["bindings", "diagnostic"] if "bindings" in failing else [
        "bindings", "statistics", "correlation", "diagnostic",
    ])
    assert result.configuration is fixture.configuration_results[0]
    assert result.control_plane is None
    assert result.report.forwarding is None
    assert "control_plane" not in fixture.trace and "forwarding" not in fixture.trace
    evidence = stage_result_evidence(result)
    assert evidence["voice"]["error"] == result.report.voice.error
    assert evidence["secondary_failures"] == [asdict(item) for item in result.secondary_failures]
    assert evidence["configuration"] == result.configuration.model_dump(mode="json")
    if "bindings" in failing:
        assert "dhcp_server_bindings" not in evidence  # No fabricated empty inventory.
        failed_read = next(item for item in result.required_observations if item.kind == "dhcp_server_bindings")
        assert failed_read.status == "failed"
        assert failed_read.error == result.secondary_failures[0].error


@pytest.mark.parametrize("after_state", [
    CPScaleRealtimeState(observed=False, simulation_mode=False,
        present=("observed", "simulation_mode")),
    CPScaleRealtimeState(observed=True, simulation_mode=True,
        present=("observed", "simulation_mode")),
])
def test_unattributable_voice_window_cannot_claim_a_realtime_primary(after_state, monkeypatch):
    fixture, observed, diagnostics = _acquired_voice_failure(
        failing=("bindings",), after_state=after_state, monkeypatch=monkeypatch,
    )
    result = fixture.executor.execute(fixture.request)
    assert result.report.realtime.verified is False
    assert result.failure.startswith("Voice at 'routing-core' is not interpretable:")
    assert diagnostics == []
    assert result.secondary_failures == ()
    assert observed == []
    assert result.control_plane is None and result.report.forwarding is None
