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
