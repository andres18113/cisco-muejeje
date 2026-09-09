"""Characterize the runner's local preflight before extracting that boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _probe(scenario: str) -> dict:
    source = _PROBE_SOURCE.replace("__SCENARIO__", json.dumps(scenario))
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout.strip().splitlines()[-1])


_PROBE_SOURCE = r'''
import json

import packet_tracer_mcp.adapters.cli.cp_scale_live as live
from packet_tracer_mcp.application.cp_scale_live import (
    CPScaleImportIsolationObservation,
    CPScaleProcessObservation,
    CPScaleProcessRecord,
    CPScaleRepositoryObservation,
    CPScaleRuntimeEvidence,
)


SCENARIO = __SCENARIO__
HEAD = "a" * 40
events = []
writes = []


class RuntimeReader:
    def read(self):
        events.append("runtime")
        return CPScaleRuntimeEvidence(
            python_executable=live.sys.executable,
            package_file=live.packet_tracer_mcp.__file__,
            loaded_namespaces=("packet_tracer_mcp",),
        )


class IsolationReader:
    def read(self, root):
        events.append("imports")
        rejected = SCENARIO == "imports-rejected"
        return CPScaleImportIsolationObservation(
            isolated=not rejected,
            isolation_state="DUAL_IDENTITY" if rejected else "ISOLATED",
            detail="two namespaces" if rejected else "package.py",
            error="DUAL_IDENTITY: rejected" if rejected else "",
        )


class RepositoryReader:
    def read(self, root):
        events.extend(("repository", "dirty", "upstream-head", "source-tree"))
        rejected = SCENARIO == "repository-rejected"
        return CPScaleRepositoryObservation(
            branch="wrong-branch" if rejected else live.EXPECTED_BRANCH,
            upstream="wrong/upstream" if rejected else live.EXPECTED_UPSTREAM,
            head=HEAD,
            upstream_head="b" * 40 if rejected else HEAD,
            source_tree="c" * 40,
            dirty=rejected,
            error="REPOSITORY_READ_ERROR" if rejected else "",
        )


class ProcessReader:
    def read(self):
        events.append("processes")
        if SCENARIO == "process-rejected":
            return CPScaleProcessObservation()
        return CPScaleProcessObservation(processes=(CPScaleProcessRecord(
            pid=101,
            name="PacketTracer",
            main_window_handle=0,
            product_version="9.0.1.0858",
            file_version="9.0.1.0858",
            executable_path=(
                r"C:\\Program Files\\Cisco Packet Tracer\\bin\\PacketTracer.exe"
            ),
        ),))


class BackendReached(RuntimeError):
    pass


def transport():
    events.append("backend")
    raise BackendReached("local preflight passed")


def write(evidence):
    events.append("write")
    writes.append(evidence)


live.PythonRuntimeEvidenceReader = RuntimeReader
live.PacketTracerImportIsolationReader = IsolationReader
live.GitCPScaleRepositoryReader = RepositoryReader
live.PowerShellPacketTracerProcessReader = ProcessReader
live.PacketTracerHttpTransport = transport
from packet_tracer_mcp.infrastructure.persistence.cp_scale_run_evidence import run_evidence
original_factory = live._build_coordinator
def build_coordinator(request, **kwargs):
    coordinator = original_factory(request, **kwargs)
    coordinator.persistence.write_progress = lambda report: write(run_evidence(report))
    # This sentinel marks entry into the factory, before any session acquisition.
    coordinator.session_factory = transport
    return coordinator
live._build_coordinator = build_coordinator

try:
    code = live.run(
        "9.0.1.0858",
        expected_head=HEAD,
        retain_on_full_verification=(SCENARIO == "request-rejected"),
        target_stage=(
            "router0-branch"
            if SCENARIO == "request-rejected"
            else "full-qualification"
        ),
    )
    escaped = ""
except Exception as exc:
    code = None
    escaped = f"{type(exc).__name__}: {exc}"

last = writes[-1] if writes else {}
print(json.dumps({
    "code": code,
    "escaped": escaped,
    "events": events,
    "write_count": len(writes),
    "hard_stop": last.get("hard_stop", ""),
    "import_isolation": last.get("import_isolation"),
    "repository": last.get("repository"),
    "processes": last.get("packet_tracer_processes"),
}))
'''


def test_request_rejection_stops_before_import_inspection():
    verdict = _probe("request-rejected")

    assert verdict == {
        "code": 2,
        "escaped": "",
        "events": ["runtime", "write"],
        "write_count": 1,
        "hard_stop": (
            "Router0 target cannot be combined with full-scale retention."
        ),
        "import_isolation": None,
        "repository": None,
        "processes": None,
    }


def test_import_rejection_does_not_read_git_or_enumerate_processes():
    verdict = _probe("imports-rejected")

    assert verdict["code"] == 2
    assert verdict["events"] == ["runtime", "imports", "write"]
    assert verdict["hard_stop"] == "DUAL_IDENTITY: rejected"
    assert verdict["import_isolation"] == {
        "state": "DUAL_IDENTITY",
        "detail": "two namespaces",
    }
    assert verdict["repository"] is None
    assert verdict["processes"] is None


def test_repository_rejection_preserves_issue_order_and_skips_processes():
    verdict = _probe("repository-rejected")

    assert verdict["code"] == 2
    assert verdict["events"] == [
        "runtime", "imports", "repository", "dirty", "upstream-head",
        "source-tree", "write",
    ]
    assert verdict["hard_stop"] == " ".join((
        "Expected branch 'feature/runtime-ripv2'; observed 'wrong-branch'.",
        "Expected upstream 'cisco/feature/runtime-ripv2'; observed 'wrong/upstream'.",
        "REPOSITORY_READ_ERROR",
        "Live session requires a clean initial worktree.",
        "Live session requires its exact initial HEAD pushed to upstream.",
    ))
    assert verdict["repository"] == {
        "branch": "wrong-branch",
        "upstream": "wrong/upstream",
        "head": "a" * 40,
        "error": "REPOSITORY_READ_ERROR",
    }
    assert verdict["processes"] is None


def test_process_rejection_stops_before_the_backend_boundary():
    verdict = _probe("process-rejected")

    assert verdict["code"] == 2
    assert verdict["events"] == [
        "runtime", "imports", "repository", "dirty", "upstream-head",
        "source-tree", "processes", "write",
    ]
    assert verdict["hard_stop"] == "No running Packet Tracer process was observed."
    assert verdict["processes"] == []


def test_success_crosses_every_local_boundary_once_and_only_then_reaches_backend():
    verdict = _probe("success")

    assert verdict["code"] is None
    assert verdict["escaped"] == "BackendReached: local preflight passed"
    assert verdict["events"] == [
        "runtime", "imports", "repository", "dirty", "upstream-head",
        "source-tree", "processes", "backend",
    ]
    assert verdict["write_count"] == 0
    assert verdict["hard_stop"] == ""


@pytest.mark.parametrize(
    "scenario",
    [
        "request-rejected",
        "imports-rejected",
        "repository-rejected",
        "process-rejected",
        "success",
    ],
)
def test_local_preflight_never_reaches_packet_tracer(scenario):
    verdict = _probe(scenario)

    assert "transport.start" not in verdict["events"]
