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
import subprocess as stdlib_subprocess
from types import SimpleNamespace

import tools.cp_scale_canonical_live as live


SCENARIO = __SCENARIO__
HEAD = "a" * 40
events = []
writes = []


class Isolation:
    def ensure_isolated(self):
        events.append("imports")
        rejected = SCENARIO == "imports-rejected"
        return SimpleNamespace(
            state=SimpleNamespace(
                value="DUAL_IDENTITY" if rejected else "ISOLATED",
            ),
            detail="two namespaces" if rejected else "package.py",
            isolated=not rejected,
            render=lambda: "DUAL_IDENTITY: rejected",
        )


def repository(_root):
    events.append("repository")
    rejected = SCENARIO == "repository-rejected"
    values = {
        "branch": "wrong-branch" if rejected else live.EXPECTED_BRANCH,
        "upstream": "wrong/upstream" if rejected else live.EXPECTED_UPSTREAM,
        "head": HEAD,
        "error": "REPOSITORY_READ_ERROR" if rejected else "",
    }
    return SimpleNamespace(
        **values,
        model_dump=lambda mode="json": dict(values),
    )


def git_status(*args, **kwargs):
    events.append("dirty")
    return SimpleNamespace(
        stdout=" M governed.py" if SCENARIO == "repository-rejected" else "",
        returncode=0,
    )


def upstream_head(*arguments):
    events.append("upstream-head")
    return "b" * 40 if SCENARIO == "repository-rejected" else HEAD


def processes():
    events.append("processes")
    if SCENARIO == "process-rejected":
        return []
    return [{
        "ProcessName": "PacketTracer",
        "Id": 101,
        "MainWindowHandle": 0,
        "ProductVersion": "9.0.1.0858",
        "FileVersion": "9.0.1.0858",
        "Path": r"C:\\Program Files\\Cisco Packet Tracer\\bin\\PacketTracer.exe",
    }]


class BackendReached(RuntimeError):
    pass


def transport():
    events.append("backend")
    raise BackendReached("local preflight passed")


def write(evidence):
    events.append("write")
    writes.append(evidence)


live.ImportIsolationPreflight = lambda root: Isolation()
live.read_git_repository_state = repository
live.subprocess = SimpleNamespace(
    run=git_status,
    CalledProcessError=stdlib_subprocess.CalledProcessError,
)
live._git_output = upstream_head
live._packet_tracer_processes = processes
live.PacketTracerHttpTransport = transport
live._write_evidence = write

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
        "events": ["write"],
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
    assert verdict["events"] == ["imports", "write"]
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
        "imports", "repository", "dirty", "upstream-head", "write",
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
        "imports", "repository", "dirty", "upstream-head", "processes", "write",
    ]
    assert verdict["hard_stop"] == "No running Packet Tracer process was observed."
    assert verdict["processes"] == []


def test_success_crosses_every_local_boundary_once_and_only_then_reaches_backend():
    verdict = _probe("success")

    assert verdict["code"] is None
    assert verdict["escaped"] == "BackendReached: local preflight passed"
    assert verdict["events"] == [
        "imports", "repository", "dirty", "upstream-head", "processes", "backend",
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
