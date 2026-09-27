"""SP-1 SP1-04: a routed DNS read waits long enough for a routed ping.

LIVE at 6e5e527 one of six HQ clients left its `ping <host>` window without
the statistics line at the 5 s default, so a resolution that later completed
was reported UNKNOWN. A routed ping sends four echoes; the read now waits for
them by default, and still returns as soon as the window is complete.
"""

from __future__ import annotations

import json

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)

_PARTIAL = (
    "ping www.sp1.lab.example\n"
    "Pinging 10.125.0.11 with 32 bytes of data:\n"
    "Request timed out.\n"
)
_COMPLETE = _PARTIAL + (
    "Reply from 10.125.0.11: bytes=32 time=1ms TTL=126\n"
    "Ping statistics for 10.125.0.11:\n"
    "    Packets: Sent = 4, Received = 3, Lost = 1 (25% loss),\n"
)


def _runtime(windows: list[str]):
    """Each dispatch takes three simulated seconds, as a LIVE inspection does."""
    now = [0.0]
    queue = [json.dumps({"started": True, "blocked": False, "before": ""})] + [
        json.dumps({"found": True, "output": item}) for item in windows
    ]
    calls: list[str] = []

    def send_and_wait(script, timeout):
        calls.append(script)
        now[0] += 3.0
        return queue.pop(0) if queue else None

    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        send_and_wait,
        convergence_interval_seconds=3.0,
        clock=lambda: now[0],
        sleeper=lambda _seconds: None,
    )
    return runtime, calls


def test_a_routed_ping_that_completes_after_nine_seconds_resolves():
    """Three partial windows three seconds apart, then the statistics."""
    runtime, calls = _runtime([_PARTIAL, _PARTIAL, _PARTIAL, _COMPLETE])

    row = runtime.verify(
        ServiceVerificationExpectation(
            id="verify-dns",
            service_id="dns",
            action_id="dns-apply",
            kind=ServiceVerificationKind.DNS_RESOLUTION,
            evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
            host_device_id="dns",
            host_device_name="HQ-DEFAULT-DNS-01",
            client_device_id="pc",
            client_device_name="HQ-DEFAULT-PC-02",
            expected={"hostname": "www.sp1.lab.example", "address": "10.125.0.11"},
        )
    )

    assert row.status is ActionExecutionStatus.VERIFIED, (row.cause, len(calls))
