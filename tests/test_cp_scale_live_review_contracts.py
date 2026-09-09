"""Causal contracts from the independent M2-B review."""
from __future__ import annotations

import pytest

from tests.test_cp_scale_router0_live_runner import RUN_DOUBLES, _probe


@pytest.mark.parametrize("verified", [False, True])
def test_final_result_retains_the_original_cleanup_realtime_observation(verified):
    verdict = _probe(RUN_DOUBLES + "\nverified = " + repr(verified) + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
coordinator = offline_coordinator(request)
acquired = []
original = coordinator.observations_factory
def observations(session):
    value = original(session)
    def realtime():
        observation = CPScaleCleanupRealtime(verified, "" if verified else "restoration unavailable", {"mode": "realtime"})
        acquired.append(observation)
        return observation
    value.cleanup_realtime = realtime
    return value
coordinator.observations_factory = observations
result = coordinator.run(request)
assert hasattr(result, "cleanup_realtime"), "Frozen result drops acquired Realtime authority"
print(json.dumps({"same": result.cleanup_realtime is acquired[-1],
    "verified": result.cleanup_realtime.verified, "state": result.cleanup_realtime.state}))
''')
    assert verdict == {"same": True, "verified": verified, "state": {"mode": "realtime"}}


@pytest.mark.parametrize("missing_identity", [False, True])
@pytest.mark.parametrize("broken_report", [False, True])
def test_rejected_preflight_write_failure_keeps_code_two_without_a_session(missing_identity, broken_report):
    verdict = _probe(RUN_DOUBLES + "\nmissing_identity = " + repr(missing_identity)
        + "\nbroken_report = " + repr(broken_report) + r'''
from dataclasses import replace
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest, CPScalePreflightOutcome
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
coordinator = offline_coordinator(request)
original = coordinator.preflight
def inspect(request, **kwargs):
    value = original.inspect(request, **kwargs)
    return SimpleNamespace(**{**vars(value), "identity": None, "outcome": value.outcome}) if missing_identity else replace(value,
        issues=("REJECTED_LOCALLY",))
coordinator.preflight = SimpleNamespace(inspect=inspect)
def write(report):
    record("write")
    raise OSError("rejected publication failed")
def report(value):
    record("report", errors=list(value.finalization_errors))
    if broken_report:
        raise OSError("report unavailable")
coordinator.persistence.write_progress = write
coordinator.presentation.finalization_incomplete = report
result = coordinator.run(request)
live._build_coordinator = lambda request: coordinator
calls.clear()
code = live.run("9.0.1.0858", expected_head=HEAD, retain_on_full_verification=False, target_stage="router0-branch")
print(json.dumps({"outcome": result.outcome.value, "code": code, "secondary": result.secondary_failures,
    "calls": [item["event"] for item in calls], "sessions": len(sessions)}))
''')
    errors = ["preflight_evidence_write: OSError: rejected publication failed"]
    if broken_report:
        errors += ["finalization_report: OSError: report unavailable"]
    assert verdict == {"outcome": "rejected", "code": 2, "secondary": errors,
        "calls": ["write", "report"], "sessions": 0}
