"""CLI composition and filesystem contracts, without a LIVE backend."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from tests.subprocess_harness import run_isolated_command, subprocess_failure


ROOT = Path(__file__).resolve().parents[1]


def test_cli_refuses_without_execute_in_a_subprocess():
    result = run_isolated_command(
        [sys.executable, "tools/cp_scale_canonical_live.py",
         "--packet-tracer-version", "9.0.1.0858", "--expected-head", "a" * 40],
        cwd=ROOT,
    )
    assert result.returncode == 2, subprocess_failure(result)
    assert json.loads(result.stdout) == {
        "hard_stop": "--execute is required; no Packet Tracer mutation occurred."
    }


def test_persistence_uses_the_composed_root_and_hashes_the_actual_progress(tmp_path):
    spec = importlib.util.find_spec(
        "src.packet_tracer_mcp.infrastructure.persistence.cp_scale_live"
    )
    assert spec is not None, "Persistence is still tied to the tool module path"
    from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_live import (
        CPScaleLivePersistence,
    )

    persistence = CPScaleLivePersistence(tmp_path)
    evidence = {"schema": "cp-scale-canonical-voice-live-v1", "stages": [],
                "packet_tracer_version": "9.0.1.0858", "live_devices": 3}
    persistence.write_evidence(evidence)
    persistence.write_checkpoint_summary("routing-core", evidence)
    progress = tmp_path / "data/cp-scale/live-canonical-progress.json"
    checkpoint = tmp_path / "data/cp-scale/live-canonical-checkpoint.json"
    summary = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert summary["schema"] == "cp-scale-live-checkpoint-v1"
    assert summary["raw_evidence_sha256"] == hashlib.sha256(progress.read_bytes()).hexdigest()
    assert summary["live_devices"] == 3
    assert not list(tmp_path.rglob("*.tmp"))
    receipt = persistence.archive("precleanup", evidence, run_identity="offline-test")
    assert receipt.path == tmp_path / "docs/reference/cp-scale/canonical-live-evidence/offline-test-precleanup.json"
    assert receipt.sha256 == hashlib.sha256(receipt.path.read_bytes()).hexdigest()


def test_real_offline_assembly_uses_explicit_root_and_closes_partial_start(tmp_path):
    from tests.test_cp_scale_router0_live_runner import RUN_DOUBLES, _probe
    # Use the real CLI composition and coordinator. Only local preflight and
    # the external transport are controlled; persistence is the actual writer.
    verdict = _probe(RUN_DOUBLES + r'''
from pathlib import Path
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
root = Path(__ROOT__)
class RefusingTransport(Transport):
    def start(self, **kwargs):
        record("offline.start")
        raise RuntimeError("OFFLINE_START_FAILURE")
live.build_local_preflight = lambda governed_root: LocalPreflight()
live.PacketTracerHttpTransport = RefusingTransport
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False)
coordinator = PRODUCT_SYMBOLS["build_coordinator"](request, governed_root=root)
result = coordinator.run(request)
payload = json.loads((root / "data/cp-scale/live-canonical-progress.json").read_text(encoding="utf-8"))
print(json.dumps({"outcome": result.outcome.value, "calls": calls, "schema": payload["schema"],
    "failure": payload["failure"], "capabilities_exist": (root / "data/capabilities").exists(),
    "coordinator": type(coordinator).__module__, "stages": payload["stages"]}))
'''.replace("__ROOT__", repr(str(tmp_path))))
    assert verdict == {"outcome": "failed", "calls": [{"event": "offline.start"}, {"event": "transport.stop"}],
        "schema": "cp-scale-canonical-voice-live-v1", "failure": "RuntimeError: OFFLINE_START_FAILURE",
        "capabilities_exist": False, "coordinator": "packet_tracer_mcp.application.cp_scale_live.coordinator", "stages": []}
