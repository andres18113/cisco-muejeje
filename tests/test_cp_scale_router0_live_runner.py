"""Isolated behavioral tests for the production-namespace LIVE runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _probe(source: str) -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_runner_dispatches_both_typed_branch_directions_and_fails_each_closed():
    verdict = _probe(r'''
import json

import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleSiteForwardingCheck,
)
from packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingResult

checks = tuple(
    CPScaleSiteForwardingCheck(
        id=f"check-{index}",
        direction=direction,
        traffic_flow_id="flow/large-to-multilayer",
        source_site_id=source_site,
        destination_site_id=destination_site,
        source_device_id=source_id,
        source_device_name=source_name,
        destination_device_id=destination_id,
        destination_device_name=destination_name,
        destination_router_id=destination_router_id,
        destination_action_id=f"cfg/static-{index}",
        destination_segment_id=f"segment-{index}",
        destination_ipv4=destination_ipv4,
        source_topology_hash="e4-hash",
        source_configuration_hash="e5-hash",
    )
    for index, (
        direction, source_site, destination_site, source_id, source_name,
        destination_id, destination_name, destination_router_id,
        destination_ipv4,
    ) in enumerate((
        (
            "large-branch-to-multilayer-branch",
            "large-branch", "multilayer-branch", "router-large", "Router4",
            "endpoint-multilayer", "MLS-AP", "router-multilayer", "192.0.2.20",
        ),
        (
            "multilayer-branch-to-large-branch",
            "multilayer-branch", "large-branch", "router-multilayer", "Router0",
            "endpoint-large", "LARGE-AP", "router-large", "192.0.2.10",
        ),
    ))
)

class Ping:
    def __init__(self, failed=None, stale=False):
        self.failed = failed
        self.stale = stale
        self.calls = []

    def ping(self, source, destination):
        self.calls.append((source, destination))
        index = len(self.calls) - 1
        return TypedPingResult(
            reachable=index != self.failed,
            fresh_output_observed=not self.stale,
            dispatched_destination=destination,
            observed_device_name=source,
            device_identity_provenance="confirmed_unique",
            device_identity_evidence="terminal_object_identity",
        )

success_ping = Ping()
success, evidence, first = live._wait_for_site_forwarding(
    success_ping, checks, attempts=1, interval_seconds=0,
)
failures = []
for failed in (0, 1):
    ping = Ping(failed=failed)
    verified, failed_evidence, first_failure = live._wait_for_site_forwarding(
        ping, checks, attempts=1, interval_seconds=0,
    )
    failures.append({
        "verified": verified,
        "first": first_failure,
        "evidence": failed_evidence,
    })
stale, _, stale_first = live._wait_for_site_forwarding(
    Ping(stale=True), checks, attempts=1, interval_seconds=0,
)
print(json.dumps({
    "success": success,
    "first": first,
    "calls": success_ping.calls,
    "evidence": evidence,
    "failures": failures,
    "stale": stale,
    "stale_first": stale_first,
}))
''')

    assert verdict["success"] is True
    assert verdict["first"] == ""
    assert verdict["calls"] == [
        ["Router4", "192.0.2.20"],
        ["Router0", "192.0.2.10"],
    ]
    assert all(item["verified"] for item in verdict["evidence"])
    assert [item["first"] for item in verdict["failures"]] == [
        "check-0", "check-1",
    ]
    assert not any(item["verified"] for item in verdict["failures"])
    assert verdict["stale"] is False
    assert verdict["stale_first"] == "check-0"


def test_runner_router0_terminal_sequence_is_successful_and_stops_at_target():
    verdict = _probe(r'''
import json
import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)

contract = canonical_cp_scale_target_contract(CPScaleCanonicalTarget.ROUTER0_BRANCH)
events = []
live._write_evidence = lambda evidence: events.append("write")
live._write_checkpoint_summary = lambda stage, evidence: events.append(
    "summary:" + stage
)
live._cleanup_owned = lambda *args, **kwargs: (
    events.append("cleanup")
    or {"verified": True, "first": {}, "second": {}, "restoration_error": ""}
)

def observe_realtime():
    events.append("realtime")
    return {"verified": True, "error": ""}

def archive(phase, payload):
    events.append("archive:" + phase)
    return {"phase": phase, "path": phase + ".json"}

evidence = {
    "stages": [{
        "stage": "router0-branch",
        "verified": True,
        "site_forwarding_verified": True,
        "plan": {"branch_forwarding_checks": [{"id": "forward-1"}]},
        "site_forwarding": [{"check": {"id": "forward-1"}, "verified": True}],
        "workspace_verified_twice": True,
    }],
    "live_devices": 290,
    "live_links": 202,
}
result = live._complete_router0_target(
    evidence=evidence,
    target_contract=contract,
    physical=object(),
    full_topology=object(),
    owned_device_ids=set(),
    baseline=object(),
    observe_cleanup_realtime=observe_realtime,
    archive=archive,
    run_identity="run-id",
    session_source_head="a" * 40,
)
print(json.dumps({
    "events": events,
    "closure": evidence["closure"],
    "scope": evidence["closure_scope"],
    "result": result,
    "build_stages": [item.value for item in contract.build_stages],
    "remaining": contract.run_remaining_reconciliation,
    "full": contract.run_full_qualification,
}))
''')

    assert verdict["events"] == [
        "write",
        "archive:precleanup",
        "cleanup",
        "realtime",
        "archive:cleanup",
        "write",
        "summary:router0-branch",
    ]
    assert verdict["closure"] == "ROUTER0_BRANCH_VERIFIED_AND_CLEANED"
    assert verdict["scope"] == "router0-branch"
    assert verdict["build_stages"][-1] == "router0-branch"
    assert "router3-branch" not in verdict["build_stages"]
    assert verdict["remaining"] is False
    assert verdict["full"] is False


@pytest.mark.parametrize(
    ("failure", "expected_events"),
    [
        ("precleanup", ["write", "archive:precleanup"]),
        (
            "first-restoration",
            ["write", "archive:precleanup", "cleanup", "realtime"],
        ),
        (
            "second-restoration",
            ["write", "archive:precleanup", "cleanup", "realtime"],
        ),
        (
            "realtime",
            ["write", "archive:precleanup", "cleanup", "realtime"],
        ),
        (
            "cleanup-archive",
            [
                "write", "archive:precleanup", "cleanup", "realtime",
                "archive:cleanup",
            ],
        ),
    ],
)
def test_runner_never_publishes_router0_success_before_every_terminal_gate(
    failure,
    expected_events,
):
    verdict = _probe(rf'''
import json
import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)

failure = {failure!r}
contract = canonical_cp_scale_target_contract(CPScaleCanonicalTarget.ROUTER0_BRANCH)
events = []
live._write_evidence = lambda evidence: events.append("write")
live._write_checkpoint_summary = lambda stage, evidence: events.append("summary")

def cleanup(*args, **kwargs):
    events.append("cleanup")
    restoration = failure if "restoration" in failure else ""
    return {{
        "verified": not restoration,
        "restoration_error": restoration,
        "first": {{}},
        "second": {{}},
    }}

live._cleanup_owned = cleanup

def realtime():
    events.append("realtime")
    return {{
        "verified": failure != "realtime",
        "error": "realtime" if failure == "realtime" else "",
    }}

def archive(phase, payload):
    events.append("archive:" + phase)
    if failure == phase or (failure == "cleanup-archive" and phase == "cleanup"):
        raise RuntimeError("archive failed: " + phase)
    return {{"phase": phase}}

evidence = {{
    "stages": [{{
        "stage": "router0-branch",
        "verified": True,
        "site_forwarding_verified": True,
        "plan": {{"branch_forwarding_checks": [{{"id": "forward-1"}}]}},
        "site_forwarding": [{{
            "check": {{"id": "forward-1"}}, "verified": True,
        }}],
        "workspace_verified_twice": True,
    }}],
}}
try:
    live._complete_router0_target(
        evidence=evidence,
        target_contract=contract,
        physical=object(),
        full_topology=object(),
        owned_device_ids=set(),
        baseline=object(),
        observe_cleanup_realtime=realtime,
        archive=archive,
        run_identity="run-id",
        session_source_head="a" * 40,
    )
    error = ""
except Exception as exc:
    error = type(exc).__name__ + ": " + str(exc)
print(json.dumps({{
    "events": events,
    "error": error,
    "closure": evidence.get("closure", ""),
}}))
''')

    assert verdict["events"] == expected_events
    assert verdict["error"]
    assert verdict["closure"] != "ROUTER0_BRANCH_VERIFIED_AND_CLEANED"


def test_api_rejects_invalid_or_retained_router0_target_before_pt_contact():
    verdict = _probe(r'''
import inspect
import json
import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)

contacted = False
def contact():
    global contacted
    contacted = True
    raise AssertionError("Packet Tracer contact was attempted")

live._packet_tracer_processes = contact
live._write_evidence = lambda evidence: None
try:
    live.run(
        "9.0.1.0858",
        expected_head="a" * 40,
        retain_on_full_verification=False,
        target_stage="unknown",
    )
    invalid = ""
except ValueError as exc:
    invalid = str(exc)

retained = live.run(
    "9.0.1.0858",
    expected_head="a" * 40,
    retain_on_full_verification=True,
    target_stage="router0-branch",
)
default_target = inspect.signature(live.run).parameters["target_stage"].default
full_contract = canonical_cp_scale_target_contract(default_target)
print(json.dumps({
    "invalid": invalid,
    "retained": retained,
    "contacted": contacted,
    "default_target": default_target.value,
    "default_stages": [item.value for item in full_contract.build_stages],
    "legacy_stages": [item.value for item in live._BUILD_STAGES],
    "remaining": full_contract.run_remaining_reconciliation,
    "full": full_contract.run_full_qualification,
}))
''')

    assert verdict["invalid"]
    assert verdict["retained"] == 2
    assert verdict["contacted"] is False
    assert verdict["default_target"] == "full-qualification"
    assert verdict["default_stages"] == verdict["legacy_stages"]
    assert verdict["remaining"] is True
    assert verdict["full"] is True
