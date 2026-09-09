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
        observation = CPScaleCleanupRealtime(verified, "" if verified else "restoration unavailable",
            cleanup_realtime_state({"observed": True, "simulation_mode": False}))
        acquired.append(observation)
        return observation
    value.cleanup_realtime = realtime
    return value
coordinator.observations_factory = observations
result = coordinator.run(request)
assert hasattr(result, "cleanup_realtime"), "Frozen result drops acquired Realtime authority"
print(json.dumps({"same": result.cleanup_realtime is acquired[-1],
    "verified": result.cleanup_realtime.verified, "state": result.cleanup_realtime.state.simulation_mode}))
''')
    assert verdict == {"same": True, "verified": verified, "state": False}


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
live._build_coordinator = lambda request, **kwargs: coordinator
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


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("broken_report", [False, True])
def test_owned_secondaries_report_once_after_close_even_during_cancellation(cancel, broken_report):
    verdict = _probe(RUN_DOUBLES + "\ncancel = " + repr(cancel)
        + "\nbroken_report = " + repr(broken_report) + r'''
from dataclasses import replace
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest, CPScaleStageSecondaryFailure
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
coordinator = offline_coordinator(request)
def stage(projection, **kwargs):
    value = execute_stage(projection, **kwargs)
    return replace(value, outcome="failed", failure="FIRST", secondary_failures=(
        CPScaleStageSecondaryFailure("bindings", "repeated"), CPScaleStageSecondaryFailure("bindings", "repeated")))
seams._execute_stage = stage
coordinator.completion.cleanup.restore = lambda *args: CPScaleCleanupResult(False, "restore failed")
original_write = coordinator.persistence.write_progress
def write(value):
    if cancel and value.failure:
        raise KeyboardInterrupt("ORIGINAL_CANCELLATION")
    return original_write(value)
coordinator.persistence.write_progress = write
reports = []
def report(value):
    reports.append(list(value.finalization_errors))
    record("report")
    if broken_report:
        raise OSError("broken report")
coordinator.presentation.finalization_incomplete = report
raised = ""
result = None
try:
    result = coordinator.run(request)
except BaseException as exc:
    raised = type(exc).__name__ + ": " + str(exc)
print(json.dumps({"raised": raised, "reports": reports,
    "secondary": list(result.secondary_failures) if result else None,
    "calls": [item["event"] for item in calls if item["event"] in ("transport.stop", "report")]}))
''')
    errors = ["stage:routing-core:bindings: repeated", "stage:routing-core:bindings: repeated",
        "cleanup_restoration: restore failed"]
    assert verdict == {"raised": "KeyboardInterrupt: ORIGINAL_CANCELLATION" if cancel else "",
        "reports": [errors], "secondary": None if cancel else errors + (["finalization_report: OSError: broken report"] if broken_report else []),
        "calls": ["transport.stop", "report"]}


def test_publication_snapshots_cannot_mutate_the_run_or_change_after_acquisition():
    verdict = _probe(RUN_DOUBLES + r'''
from dataclasses import FrozenInstanceError
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
coordinator = offline_coordinator(request)
snapshots = []
mutations_blocked = []
def write(value):
    snapshots.append(value)
    try:
        value.failure = "EXTERNAL_PUBLICATION_MUTATION"
    except FrozenInstanceError:
        mutations_blocked.append(True)
coordinator.persistence.write_progress = write
result = coordinator.run(request)
print(json.dumps({"outcome": result.outcome.value, "primary": result.primary_failure,
    "blocked": len(mutations_blocked) == len(snapshots),
    "first_stages": len(snapshots[0].stages), "first_closure": snapshots[0].closure,
    "last_stages": len(snapshots[-1].stages), "same_snapshot": snapshots[0] is snapshots[-1]}))
''')
    assert verdict == {"outcome": "completed", "primary": None, "blocked": True,
        "first_stages": 0, "first_closure": "", "last_stages": 6, "same_snapshot": False}


def test_real_coordinator_uses_the_typed_stage_sequence_mechanism():
    verdict = _probe(RUN_DOUBLES + r'''
import packet_tracer_mcp.application.cp_scale_live.coordinator as coordinator_module
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
assert hasattr(coordinator_module, "execute_stage_sequence"), "Coordinator has no reusable sequence mechanism"
original = coordinator_module.execute_stage_sequence
sequences = []
def observe_sequence(stages, initial, step):
    result = original(stages, initial, step)
    sequences.append(result)
    return result
coordinator_module.execute_stage_sequence = observe_sequence
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
result = offline_coordinator(request).run(request)
sequence = sequences[0]
assert all(step.value is stage for step, stage in zip(sequence.steps, result.progress.completed_stages))
print(json.dumps({"count": len(sequences), "steps": len(sequence.steps), "succeeded": sequence.succeeded,
    "secondary": sequence.secondary_failures}))
''')
    assert verdict == {"count": 1, "steps": 6, "succeeded": True, "secondary": []}


def test_cleanup_realtime_payload_is_not_a_mutable_dictionary():
    from dataclasses import is_dataclass
    from src.packet_tracer_mcp.infrastructure.observation.cp_scale_live_run import PacketTracerCPScaleRunObservations
    from src.packet_tracer_mcp.infrastructure.observation import cp_scale_live_run as module
    from unittest.mock import patch

    raw = {"observed": True, "simulation_mode": False}
    with patch.object(module, "_voice_window_state", return_value=raw):
        observation = PacketTracerCPScaleRunObservations(type("Transport", (), {"send_and_wait": None})(), None).cleanup_realtime()
    assert is_dataclass(observation.state), "Cleanup observation still exposes a mutable arbitrary dictionary"
    raw["simulation_mode"] = True
    assert observation.state.simulation_mode is False


@pytest.mark.parametrize("failure", ["", "prepare_write", "resume_cancel"])
def test_real_checkpoint_assembly_publishes_owned_snapshots_in_order(tmp_path, failure):
    verdict = _probe(RUN_DOUBLES + "\nfailure = " + repr(failure) + "\nroot = " + repr(str(tmp_path)) + r'''
from pathlib import Path
import hashlib
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
from packet_tracer_mcp.application.cp_scale_live.checkpoint import CPScaleCheckpoint, CPScaleCheckpointRepository
from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import CPScaleRepositoryState
from packet_tracer_mcp.infrastructure.persistence.cp_scale_live import CPScaleLivePersistence
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
coordinator = offline_coordinator(request)
repository = CPScaleRepositoryState(branch=live.EXPECTED_BRANCH, upstream=live.EXPECTED_UPSTREAM, head=HEAD)
resumption = CPScaleCheckpointRepository(repository, HEAD, False, False)
events = []
class Repository:
    def read(self):
        events.append("prepare")
        return repository
    def resumed(self, source_head):
        assert source_head == HEAD
        events.append("resume")
        return resumption
class Console:
    def decide(self, prompt):
        raw = persistence.evidence_path.read_bytes()
        summary = json.loads(persistence.checkpoint_path.read_text(encoding="utf-8"))
        payload = json.loads(raw)
        assert payload["checkpoint"] == prompt.stage == summary["checkpoint"]
        assert summary["raw_evidence_sha256"] == hashlib.sha256(raw).hexdigest()
        events.append("prompt")
        return CPScaleCheckpointDecision.CONTINUE
persistence = CPScaleLivePersistence(Path(root))
original_write = persistence.write_progress
snapshots = []
injected = []
def write(value):
    snapshots.append(value)
    if failure and value.checkpoint == "routing-core" and not injected:
        if failure == "prepare_write" or value.checkpoint_resume_repository is not None:
            injected.append(True)
            if failure == "resume_cancel":
                raise KeyboardInterrupt("checkpoint resumed publication cancelled")
            raise OSError("checkpoint prepared publication failed")
    return original_write(value)
persistence.write_progress = write
coordinator.persistence = persistence
coordinator.checkpoint = CPScaleCheckpoint(repository=Repository(), console=Console(), persistence=persistence)
result = None
raised = ""
try:
    result = coordinator.run(request)
except BaseException as exc:
    raised = type(exc).__name__ + ": " + str(exc)
latest = snapshots[-1]
print(json.dumps({"outcome": result.outcome.value if result else None, "raised": raised,
    "events": events, "checkpoint": latest.checkpoint,
    "prepared_identity": latest.checkpoint_repository is repository,
    "resumed_identity": latest.checkpoint_resume_repository is resumption,
    "closed": len([item for item in calls if item["event"] == "transport.stop"])}))
''')
    assert verdict == {
        "outcome": None if failure == "resume_cancel" else "failed" if failure else "completed",
        "raised": "KeyboardInterrupt: checkpoint resumed publication cancelled" if failure == "resume_cancel" else "",
        "events": ["prepare"] if failure == "prepare_write" else ["prepare", "prompt", "resume"] * (1 if failure else 5),
        "checkpoint": "routing-core" if failure else "floor3", "prepared_identity": True,
        "resumed_identity": failure != "prepare_write", "closed": 1,
    }


@pytest.mark.parametrize("restoration_error,realtime_error", [
    ("first restoration failed", ""), ("second restoration failed", ""),
    ("", "Realtime unavailable"), ("restoration failed", "later Realtime failure"),
])
def test_completion_cleanup_policy_keeps_the_exact_first_cause(restoration_error, realtime_error):
    from src.packet_tracer_mcp.application.cp_scale_live.completion import CPScaleCompletion
    from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import CPScaleCleanupResult, CPScaleCleanupRealtime

    policy = CPScaleCompletion(cleanup=None)
    result = policy.review_cleanup(CPScaleCleanupResult(not restoration_error, restoration_error),
        CPScaleCleanupRealtime(not realtime_error, realtime_error), router0=True)
    assert result.error == "Router0 verification completed, but cleanup/restoration did not verify: " + (restoration_error or realtime_error)
    assert result.secondary_failures == (("cleanup_realtime: " + realtime_error,) if restoration_error and realtime_error else ())
