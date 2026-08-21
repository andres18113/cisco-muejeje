"""Offline guards for the bounded EIGRP live-qualification harness."""

from __future__ import annotations

from src.packet_tracer_mcp.shared.utils import (
    serialize_typed_ping_evidence,
    typed_ping_behavior_transition_verified,
)
from src.packet_tracer_mcp.infrastructure.execution.typed_ping import (
    TypedPingResult,
)


def test_ping_evidence_serializes_only_current_typed_result_fields():
    result = TypedPingResult(
        reachable=True,
        fresh_output_observed=True,
        window_strategy="prefix_delta",
        statistics="Success rate is 100 percent (5/5)",
        dispatched_destination="198.18.211.10",
        observed_device_name="MCP-PROBE-EIGRP-CP3-PCA",
        device_identity_provenance="confirmed_unique",
        device_identity_evidence="session_transcript_continuity",
    )

    assert serialize_typed_ping_evidence(result) == {
        "reachable": True,
        "fresh_output_observed": True,
        "window_strategy": "prefix_delta",
        "failure_reason": "",
        "attempts": 1,
        "statistics": "Success rate is 100 percent (5/5)",
        "dispatched_destination": "198.18.211.10",
        "observed_device_name": "MCP-PROBE-EIGRP-CP3-PCA",
        "device_identity_provenance": "confirmed_unique",
        "device_identity_evidence": "session_transcript_continuity",
    }


def test_behavior_transition_requires_fresh_negative_and_positive_controls():
    before = TypedPingResult(
        reachable=False,
        fresh_output_observed=True,
        window_strategy="prefix_delta",
    )
    after = TypedPingResult(
        reachable=True,
        fresh_output_observed=True,
        window_strategy="prefix_delta",
    )

    assert typed_ping_behavior_transition_verified([before], [after])
    assert not typed_ping_behavior_transition_verified([after], [after])
    stale_after = TypedPingResult(
        reachable=True, fresh_output_observed=False,
    )
    assert not typed_ping_behavior_transition_verified(
        [before], [stale_after],
    )
