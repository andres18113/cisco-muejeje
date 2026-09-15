"""The first FULL qualification LIVE failed with its backend and closes nothing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from functools import cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "reference" / "cp-scale" / "full_qualification_failed_runs.json"
RUN_IDENTITY = "canonical-cp-scale-voice-20260915T181618415152Z-ff117655a973"
EXECUTED_SHA = "ff117655a97301aa05cad6c7696f89dd87ec71fc"


@cache
def _archive(path: str) -> dict:
    return json.loads((ROOT / path).read_bytes())


def _run() -> dict:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    assert index["schema"] == "cp-scale-full-qualification-failed-runs-v1"
    assert index["classification"] == "FAILED"
    assert index["publication_is_success_authority"] is False
    assert index["full_qualification_successful_closure"] is False
    (run,) = index["runs"]
    assert run["run_identity"] == RUN_IDENTITY
    return run


def _artifacts(run: dict) -> dict[str, dict]:
    return {item["phase"]: item for item in run["artifacts"]}


def test_failed_full_run_pins_original_bytes_and_closes_nothing():
    run = _run()
    artifacts = _artifacts(run)
    assert set(artifacts) == {"failure-precleanup", "cleanup"}
    for artifact in artifacts.values():
        raw = (ROOT / artifact["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]

    failure = _archive(artifacts["failure-precleanup"]["path"])
    assert failure["run_identity"] == RUN_IDENTITY
    assert failure["failure"] == run["failure"]
    assert failure["target_stage"] == run["target"] == "full-qualification"
    assert failure["repository"]["head"] == run["executed_sha"] == EXECUTED_SHA
    assert "closure" not in failure
    # FULL died inside floor3; REMAINING, the only terminal authority, never ran.
    assert [stage["stage"] for stage in failure["stages"]] == [
        "routing-core", "router4-switch10", "floor1", "floor2", "floor3",
    ]
    assert failure["stages"][-1]["stage_outcome"] == "failed"
    assert run["failed_stage"] == "floor3"
    assert run["remaining_executed"] is False
    assert run["successful_closure"] is False
    assert {
        "stage": failure["checkpoint"],
        "live_devices": failure["live_devices"],
        "live_links": failure["live_links"],
    } == run["last_checkpoint"]

    cleanup = _archive(artifacts["cleanup"]["path"])
    assert cleanup["run_identity"] == RUN_IDENTITY
    assert cleanup["source_head"] == EXECUTED_SHA
    assert cleanup["failure"] == run["failure"]
    assert cleanup["canonical_evidence_precleanup"]["sha256"] == (
        artifacts["failure-precleanup"]["sha256"]
    )
    observed = cleanup["cleanup"]
    mutations = observed["mutations"]
    assert all(
        item["disposition"] == "no_op" and item["applied"] is False
        for item in mutations
    )
    assert run["cleanup"] == {
        "verified": observed["verified"],
        "owned_devices_removed": 0,
        "owned_devices_already_absent": len(mutations),
        "first_semantic_devices": observed["first"]["semantic_device_count"],
        "first_links": observed["first"]["link_count"],
        "second_semantic_devices": observed["second"]["semantic_device_count"],
        "second_links": observed["second"]["link_count"],
        "realtime_verified": cleanup["cleanup_realtime"]["verified"],
    }
    assert run["cleanup"]["verified"] is True
    assert run["cleanup"]["owned_devices_already_absent"] == 232


def test_backend_crash_belongs_to_the_session_process_and_precedes_the_failure():
    run = _run()
    host = run["host_observations"]
    assert host["authority"] == "HOST_OBSERVATION_OUTSIDE_GOVERNED_ARCHIVE"
    crash = host["backend_process_crash"]
    failure = _archive(_artifacts(run)["failure-precleanup"]["path"])

    # The crashed process is the one preflight bound to this session.
    assert crash["process_id"] in {
        process["Id"] for process in failure["packet_tracer_processes"]
    }
    assert crash["exception_code"] == "0xc0000005"
    assert host["replacement_process"]["process_id"] != crash["process_id"]
    crashed_at = datetime.fromisoformat(crash["observed_at"])

    # floor3's physical manifest closed before the crash; its configuration
    # evidence and the serial read-back that raised the failure came after it.
    floor3 = failure["stages"][-1]
    assert datetime.fromisoformat(floor3["physical"]["manifest"]["created_at"]) < crashed_at
    configured = [
        datetime.fromisoformat(record["timestamp"])
        for attempt in floor3["configuration_attempts"]
        for record in attempt["evidence_records"]
    ]
    assert configured
    assert min(configured) > crashed_at
    assert floor3["serial_interfaces"]
    assert all(
        reading["fresh_output_observed"] is False
        and reading["failure_reason"] == "IOS session state: failed"
        for reading in floor3["serial_interfaces"]
    )

    analysis = run["causal_analysis"]
    assert analysis["cause_classification"] == "BACKEND_PROCESS_CRASH"
    assert analysis["implementation_causation"] == "UNKNOWN"
    assert analysis["recorded_failure_role"] == "OBSERVED_AFTER_BACKEND_CRASH"
    assert analysis["cleanup_runtime_instance"] == "REPLACEMENT_PROCESS"
    assert analysis["runner_recorded_process_replacement"] is False
