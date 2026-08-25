"""A failed CP-SCALE stage must keep the evidence it already gathered.

The Floor-1 run died with a 43-identifier failure string and nothing else. The
per-field read-backs that would have named the root cause existed at the moment
of the raise -- `_execute_stage` had already written the full typed
`ConfigurationApplicationResult` into its local journal three lines earlier --
but that dict escapes only through the success return, and the outer loop
appends it only after the call returns. The exception threw away the exact
evidence and kept the summary. Reconstructing what the run had already seen
cost a full offline investigation.

`tools/cp_scale_canonical_live.py` imports the PRODUCTION `packet_tracer_mcp`
namespace, and `ImportIsolationPreflight` exists precisely so that the live
process is the only one holding it. Importing the tool here would load that
namespace into the pytest process and make this suite look like a live one, so
the tool is exercised in a child process instead and only its verdict crosses
back.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

_PROBE = '''
import json, sys
from types import SimpleNamespace

sys.path.insert(0, {root!r})
sys.path.insert(0, {src!r})

from tools.cp_scale_canonical_live import CanonicalLiveFailure, _execute_stage
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentStatus,
)

verdict = {{}}

carried = CanonicalLiveFailure("boom", stage_evidence={{"stage": "floor1"}})
verdict["carries_evidence"] = carried.stage_evidence == {{"stage": "floor1"}}
verdict["message_intact"] = str(carried) == "boom"

bare = CanonicalLiveFailure("boom")
verdict["defaults_to_none"] = bare.stage_evidence is None
verdict["still_runtime_error"] = isinstance(bare, RuntimeError)

projection = SimpleNamespace(
    stage=SimpleNamespace(value="floor1"),
    topology=SimpleNamespace(
        physical_identity_hash="topology-hash", devices=[1, 2, 3], modules=[], links=[1, 2],
    ),
    configuration=SimpleNamespace(semantic_hash="config-hash", actions=[1]),
    control_plane=SimpleNamespace(
        semantic_hash="control-hash", actions=[], verification_expectations=[],
    ),
    voice=None,
)
deployment = SimpleNamespace(
    status=PhysicalDeploymentStatus.FAILED,
    manifest=None,
    errors=["exact physical binding was refused"],
    model_dump=lambda mode="json": {{"status": "failed"}},
)

try:
    _execute_stage(
        projection,
        composition=SimpleNamespace(capabilities={{}}),
        deployment=deployment,
        delta_deployment=None,
        physical=None,
        configuration_runtime=None,
        control_runtime=None,
        voice_runtime=None,
        transport=None,
        fingerprint=None,
        packet_tracer_version="9.0.1.0858",
    )
except CanonicalLiveFailure as exc:
    evidence = exc.stage_evidence
    verdict["raised_with_journal"] = evidence is not None
    verdict["stage"] = (evidence or {{}}).get("stage")
    verdict["configuration_hash"] = (
        (evidence or {{}}).get("plan", {{}}).get("configuration_hash")
    )
    verdict["physical"] = (evidence or {{}}).get("physical")
else:
    verdict["raised_with_journal"] = False

print(json.dumps(verdict))
'''


@pytest.fixture(scope="module")
def verdict() -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE.format(root=str(ROOT), src=str(ROOT / "src"))],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_canonical_live_failure_carries_the_stage_evidence_it_had(verdict):
    assert verdict["carries_evidence"]
    assert verdict["message_intact"]


def test_canonical_live_failure_without_evidence_still_behaves_as_before(verdict):
    assert verdict["defaults_to_none"]
    assert verdict["still_runtime_error"]


def test_a_failed_stage_raises_with_the_journal_it_had_already_written(verdict):
    assert verdict["raised_with_journal"], "the stage journal was thrown away again"
    assert verdict["stage"] == "floor1"
    assert verdict["configuration_hash"] == "config-hash"
    assert verdict["physical"] == {"status": "failed"}


def test_this_suite_never_loaded_the_production_namespace():
    """The isolation invariant this file must not be the one to break."""
    assert "packet_tracer_mcp" not in sys.modules
