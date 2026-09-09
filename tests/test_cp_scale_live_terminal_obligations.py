"""Causal terminal-obligation regressions against the real coordinator."""
from __future__ import annotations

import pytest

from tests.test_cp_scale_router0_live_runner import RUN_DOUBLES, _probe


@pytest.mark.parametrize("cancel", [False, True])
def test_report_callback_failure_cannot_mask_obligations_or_cancellation(cancel):
    from src.packet_tracer_mcp.application.cp_scale_live.lifecycle import finalize_session

    calls = []

    class Session:
        def close(self):
            calls.append("close")
            raise OSError("close failed")

    def write():
        calls.append("write")
        if cancel:
            raise KeyboardInterrupt("original cancellation")
        raise OSError("write failed")

    def report(errors):
        calls.append("report")
        raise OSError("report failed")

    def invoke():
        return finalize_session(prepare=lambda: calls.append("prepare"), write=write,
                                session=Session(), report=report)

    if cancel:
        with pytest.raises(KeyboardInterrupt, match="original cancellation"):
            invoke()
    else:
        assert invoke().errors == (
            "final_evidence_write: OSError: write failed",
            "transport_stop: OSError: close failed",
            "finalization_report: OSError: report failed",
        )
    assert calls == ["prepare", "write", "close", "report"]


@pytest.mark.parametrize("secondary_boundary", ["close", "report"])
def test_later_baseexception_never_replaces_the_original_cancellation(
    secondary_boundary,
):
    from src.packet_tracer_mcp.application.cp_scale_live.lifecycle import (
        finalize_session,
    )

    calls = []
    reports = []
    original = KeyboardInterrupt("FIRST")

    class Session:
        def close(self):
            calls.append("close")
            if secondary_boundary == "close":
                raise SystemExit("SECOND")
            raise OSError("ordinary close failure")

    def write():
        calls.append("write")
        raise original

    def report(errors):
        calls.append("report")
        reports.append(errors)
        if secondary_boundary == "report":
            raise SystemExit("SECOND")

    with pytest.raises(KeyboardInterrupt, match="FIRST") as caught:
        finalize_session(
            prepare=lambda: calls.append("prepare"),
            write=write,
            session=Session(),
            report=report,
            defer_report=True,
        )

    assert calls == ["prepare", "write", "close", "report"]
    assert caught.value is original
    expected = (
        ("transport_stop: SystemExit: SECOND",)
        if secondary_boundary == "close"
        else (
            "transport_stop: OSError: ordinary close failure",
            "finalization_report: SystemExit: SECOND",
        )
    )
    assert caught.value.finalization_errors == expected
    assert reports == [expected[:1]]


@pytest.mark.parametrize("cancel_boundary", ["stage", "checkpoint"])
@pytest.mark.parametrize("stop_failure", ["oserror", "systemexit"])
def test_execute_session_cancellation_survives_close_and_is_published(
    cancel_boundary,
    stop_failure,
):
    verdict = _probe(
        RUN_DOUBLES
        + "\ncancel_boundary = "
        + repr(cancel_boundary)
        + "\nstop_failure = "
        + repr(stop_failure)
        + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest

request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
original = KeyboardInterrupt("ORIGINAL_EXECUTE_SESSION_CANCELLATION")

if cancel_boundary == "stage":
    def cancel_stage(*args, **kwargs):
        record("cancel_stage")
        raise original
    seams._execute_stage = cancel_stage
else:
    def cancel_checkpoint(*args, **kwargs):
        record("cancel_checkpoint")
        raise original
    seams._checkpoint = cancel_checkpoint

def stop(self):
    record("transport.stop")
    if stop_failure == "oserror":
        raise OSError("STOP_FAILED_AFTER_EXECUTE_CANCELLATION")
    raise SystemExit("STOP_ABORTED_AFTER_EXECUTE_CANCELLATION")
Transport.stop = stop

coordinator = offline_coordinator(request)
writes = []
reports = []

def write(report):
    after_close = any(item["event"] == "transport.stop" for item in calls)
    writes.append({
        "after_close": after_close,
        "errors": list(report.finalization_errors),
        "archives": [item.model_dump(mode="json")["phase"] for item in report.archives],
    })

def report(report):
    reports.append(list(report.finalization_errors))

coordinator.persistence.write_progress = write
coordinator.presentation.finalization_incomplete = report

caught = None
try:
    coordinator.run(request)
except BaseException as exc:
    caught = exc

print(json.dumps({
    "identity_preserved": caught is original,
    "raised": type(caught).__name__ + ": " + str(caught),
    "finalization_errors": list(getattr(caught, "finalization_errors", ())),
    "cancel_count": sum(item["event"] == "cancel_" + cancel_boundary for item in calls),
    "session_effects_after_cancel": [
        item["event"]
        for item in calls[
            next(index for index, item in enumerate(calls)
                 if item["event"] == "cancel_" + cancel_boundary) + 1:
        ]
        if item["event"] in ("deploy", "execute_stage", "checkpoint", "reconcile")
    ],
    "cleanup_count": sum(item["event"] == "cleanup" for item in calls),
    "stop_count": sum(item["event"] == "transport.stop" for item in calls),
    "post_close_writes": [item for item in writes if item["after_close"]],
    "reports": reports,
}))
'''
    )

    expected_error = (
        "transport_stop: OSError: STOP_FAILED_AFTER_EXECUTE_CANCELLATION"
        if stop_failure == "oserror"
        else "transport_stop: SystemExit: STOP_ABORTED_AFTER_EXECUTE_CANCELLATION"
    )
    assert verdict == {
        "identity_preserved": True,
        "raised": "KeyboardInterrupt: ORIGINAL_EXECUTE_SESSION_CANCELLATION",
        "finalization_errors": [expected_error],
        "cancel_count": 1,
        "session_effects_after_cancel": [],
        "cleanup_count": 1,
        "stop_count": 1,
        "post_close_writes": [{
            "after_close": True,
            "errors": [expected_error],
            "archives": ["failure-precleanup", "cleanup"],
        }],
        "reports": [[expected_error]],
    }


def test_execute_session_cancellation_classifies_post_close_baseexception():
    verdict = _probe(RUN_DOUBLES + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest

request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
original = KeyboardInterrupt("ORIGINAL_EXECUTE_SESSION_CANCELLATION")
seams._execute_stage = lambda *args, **kwargs: (_ for _ in ()).throw(original)

def stop(self):
    record("transport.stop")
    raise OSError("STOP_FAILED_AFTER_EXECUTE_CANCELLATION")
Transport.stop = stop

coordinator = offline_coordinator(request)
publication_attempts = []
reports = []

def write(report):
    if any(item["event"] == "transport.stop" for item in calls):
        publication_attempts.append(list(report.finalization_errors))
        raise SystemExit("POST_CLOSE_PUBLICATION_ABORTED")

coordinator.persistence.write_progress = write
coordinator.presentation.finalization_incomplete = (
    lambda report: reports.append(list(report.finalization_errors))
)

caught = None
try:
    coordinator.run(request)
except BaseException as exc:
    caught = exc

print(json.dumps({
    "identity_preserved": caught is original,
    "finalization_errors": list(getattr(caught, "finalization_errors", ())),
    "cleanup_count": sum(item["event"] == "cleanup" for item in calls),
    "stop_count": sum(item["event"] == "transport.stop" for item in calls),
    "publication_attempts": publication_attempts,
    "reports": reports,
}))
''')

    stop_error = "transport_stop: OSError: STOP_FAILED_AFTER_EXECUTE_CANCELLATION"
    publication_error = (
        "terminal_evidence_write: SystemExit: POST_CLOSE_PUBLICATION_ABORTED"
    )
    assert verdict == {
        "identity_preserved": True,
        "finalization_errors": [stop_error, publication_error],
        "cleanup_count": 1,
        "stop_count": 1,
        "publication_attempts": [[stop_error]],
        "reports": [[stop_error, publication_error]],
    }


def test_execute_session_cancellation_classifies_final_write_baseexception():
    verdict = _probe(RUN_DOUBLES + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest

request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
original = KeyboardInterrupt("ORIGINAL_EXECUTE_SESSION_CANCELLATION")
seams._execute_stage = lambda *args, **kwargs: (_ for _ in ()).throw(original)

def stop(self):
    record("transport.stop")
    raise OSError("STOP_FAILED_AFTER_EXECUTE_CANCELLATION")
Transport.stop = stop

coordinator = offline_coordinator(request)
writes = []
reports = []

def write(report):
    after_close = any(item["event"] == "transport.stop" for item in calls)
    phases = [item.model_dump(mode="json")["phase"] for item in report.archives]
    writes.append({"after_close": after_close, "errors": list(report.finalization_errors)})
    if not after_close and phases == ["failure-precleanup", "cleanup"]:
        raise SystemExit("FINAL_WRITE_ABORTED")

coordinator.persistence.write_progress = write
coordinator.presentation.finalization_incomplete = (
    lambda report: reports.append(list(report.finalization_errors))
)

caught = None
try:
    coordinator.run(request)
except BaseException as exc:
    caught = exc

print(json.dumps({
    "identity_preserved": caught is original,
    "finalization_errors": list(getattr(caught, "finalization_errors", ())),
    "cleanup_count": sum(item["event"] == "cleanup" for item in calls),
    "stop_count": sum(item["event"] == "transport.stop" for item in calls),
    "post_close_writes": [item for item in writes if item["after_close"]],
    "reports": reports,
}))
''')

    write_error = "final_evidence_write: SystemExit: FINAL_WRITE_ABORTED"
    stop_error = "transport_stop: OSError: STOP_FAILED_AFTER_EXECUTE_CANCELLATION"
    assert verdict == {
        "identity_preserved": True,
        "finalization_errors": [write_error, stop_error],
        "cleanup_count": 1,
        "stop_count": 1,
        "post_close_writes": [{
            "after_close": True,
            "errors": [write_error, stop_error],
        }],
        "reports": [[write_error, stop_error]],
    }


def test_execute_session_cancellation_bounds_publication_and_report_failures():
    verdict = _probe(RUN_DOUBLES + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest

request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
original = KeyboardInterrupt("ORIGINAL_EXECUTE_SESSION_CANCELLATION")
seams._execute_stage = lambda *args, **kwargs: (_ for _ in ()).throw(original)

def stop(self):
    record("transport.stop")
    raise OSError("STOP_FAILED_AFTER_EXECUTE_CANCELLATION")
Transport.stop = stop

coordinator = offline_coordinator(request)
publication_attempts = []
report_attempts = []

def write(report):
    if any(item["event"] == "transport.stop" for item in calls):
        publication_attempts.append(list(report.finalization_errors))
        raise OSError("POST_CLOSE_PUBLICATION_FAILED_" + str(len(publication_attempts)))

def report(report):
    report_attempts.append(list(report.finalization_errors))
    raise SystemExit("POST_CLOSE_REPORT_ABORTED")

coordinator.persistence.write_progress = write
coordinator.presentation.finalization_incomplete = report

caught = None
try:
    coordinator.run(request)
except BaseException as exc:
    caught = exc

print(json.dumps({
    "identity_preserved": caught is original,
    "finalization_errors": list(getattr(caught, "finalization_errors", ())),
    "cleanup_count": sum(item["event"] == "cleanup" for item in calls),
    "stop_count": sum(item["event"] == "transport.stop" for item in calls),
    "publication_attempts": publication_attempts,
    "report_attempts": report_attempts,
}))
''')

    stop_error = "transport_stop: OSError: STOP_FAILED_AFTER_EXECUTE_CANCELLATION"
    first_write = "terminal_evidence_write: OSError: POST_CLOSE_PUBLICATION_FAILED_1"
    report_error = "finalization_report: SystemExit: POST_CLOSE_REPORT_ABORTED"
    second_write = "terminal_evidence_write: OSError: POST_CLOSE_PUBLICATION_FAILED_2"
    assert verdict == {
        "identity_preserved": True,
        "finalization_errors": [stop_error, first_write, report_error, second_write],
        "cleanup_count": 1,
        "stop_count": 1,
        "publication_attempts": [
            [stop_error],
            [stop_error, first_write, report_error],
        ],
        "report_attempts": [[stop_error, first_write]],
    }


@pytest.mark.parametrize("cancel_boundary", ["stage", "checkpoint"])
def test_execute_session_cancellation_declares_failed_post_close_publication_limit(
    cancel_boundary,
):
    verdict = _probe(
        RUN_DOUBLES
        + "\ncancel_boundary = "
        + repr(cancel_boundary)
        + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest

request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
original = KeyboardInterrupt("ORIGINAL_EXECUTE_SESSION_CANCELLATION")

if cancel_boundary == "stage":
    def cancel_stage(*args, **kwargs):
        raise original
    seams._execute_stage = cancel_stage
else:
    def cancel_checkpoint(*args, **kwargs):
        raise original
    seams._checkpoint = cancel_checkpoint

def stop(self):
    record("transport.stop")
    raise OSError("STOP_FAILED_AFTER_EXECUTE_CANCELLATION")
Transport.stop = stop

coordinator = offline_coordinator(request)
publication_attempts = []
reports = []

def write(report):
    after_close = any(item["event"] == "transport.stop" for item in calls)
    if after_close:
        publication_attempts.append(list(report.finalization_errors))
        raise OSError("POST_CLOSE_PUBLICATION_FAILED")

def report(report):
    reports.append(list(report.finalization_errors))

coordinator.persistence.write_progress = write
coordinator.presentation.finalization_incomplete = report

caught = None
try:
    coordinator.run(request)
except BaseException as exc:
    caught = exc

print(json.dumps({
    "identity_preserved": caught is original,
    "raised": type(caught).__name__ + ": " + str(caught),
    "finalization_errors": list(getattr(caught, "finalization_errors", ())),
    "cleanup_count": sum(item["event"] == "cleanup" for item in calls),
    "stop_count": sum(item["event"] == "transport.stop" for item in calls),
    "publication_attempts": publication_attempts,
    "reports": reports,
}))
'''
    )

    stop_error = "transport_stop: OSError: STOP_FAILED_AFTER_EXECUTE_CANCELLATION"
    publication_error = (
        "terminal_evidence_write: OSError: POST_CLOSE_PUBLICATION_FAILED"
    )
    assert verdict == {
        "identity_preserved": True,
        "raised": "KeyboardInterrupt: ORIGINAL_EXECUTE_SESSION_CANCELLATION",
        "finalization_errors": [stop_error, publication_error],
        "cleanup_count": 1,
        "stop_count": 1,
        "publication_attempts": [[stop_error]],
        "reports": [[stop_error, publication_error]],
    }


@pytest.mark.parametrize("boundary", ["realtime", "postcleanup_write", "checkpoint"])
def test_router0_acquired_cleanup_is_never_repeated_after_cancellation(boundary):
    verdict = _probe(RUN_DOUBLES + "\nboundary = " + repr(boundary) + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
coordinator = offline_coordinator(request)
captured = []
original_restore = coordinator.completion.cleanup.restore
def restore(*args):
    acquired = original_restore(*args)
    captured.append(acquired)
    return acquired
coordinator.completion.cleanup.restore = restore
original_observations = coordinator.observations_factory
realtime_calls = []
def observations(session):
    result = original_observations(session)
    original = result.cleanup_realtime
    def realtime():
        realtime_calls.append("realtime")
        if boundary == "realtime" and len(realtime_calls) == 1:
            raise KeyboardInterrupt("CANCEL_AFTER_ACQUIRED_CLEANUP")
        return original()
    result.cleanup_realtime = realtime
    return result
coordinator.observations_factory = observations
reports = []
cancelled = []
original_write = coordinator.persistence.write_progress
def write(report):
    reports.append(report)
    if boundary == "postcleanup_write" and report.cleanup_attestation and not cancelled:
        cancelled.append(True)
        raise KeyboardInterrupt("CANCEL_AFTER_ACQUIRED_CLEANUP")
    return original_write(report)
coordinator.persistence.write_progress = write
original_checkpoint = coordinator.persistence.checkpoint
def checkpoint(stage, report, **kwargs):
    if boundary == "checkpoint" and report.cleanup_attestation:
        raise KeyboardInterrupt("CANCEL_AFTER_ACQUIRED_CLEANUP")
    return original_checkpoint(stage, report, **kwargs)
coordinator.persistence.checkpoint = checkpoint
raised = ""
try:
    coordinator.run(request)
except BaseException as exc:
    raised = type(exc).__name__ + ": " + str(exc)
print(json.dumps({"raised": raised, "cleanup_count": len(captured),
    "cleanup_identity": reports[-1].cleanup is captured[0],
    "archives": [item.model_dump()["phase"] for item in reports[-1].archives],
    "terminal_events": [item["event"] for item in calls if item["event"] in ("archive", "cleanup", "transport.stop")],
    "realtime_count": len(realtime_calls)}))
''')
    assert verdict == {
        "raised": "KeyboardInterrupt: CANCEL_AFTER_ACQUIRED_CLEANUP",
        "cleanup_count": 1,
        "cleanup_identity": True,
        "archives": ["precleanup", "cleanup"],
        "terminal_events": ["archive", "cleanup", "archive", "transport.stop"],
        "realtime_count": 2,
    }


@pytest.mark.parametrize("broken", ["", "write", "close", "presentation"])
@pytest.mark.parametrize("target", ["router0-branch", "full-cleanup", "full-retain"])
def test_success_is_published_only_after_final_write_and_close(broken, target):
    verdict = _probe(RUN_DOUBLES + "\nbroken = " + repr(broken) + "\ntarget = " + repr(target) + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, target == "full-retain",
    "router0-branch" if target == "router0-branch" else "full-qualification")
coordinator = offline_coordinator(request)
if target != "router0-branch":
    seams._write_checkpoint_summary = lambda stage, evidence, **kwargs: record("summary", stage=stage)
    coordinator.build.reconcile = lambda topology, physical, **kwargs: Deployment()
    coordinator.build.full_projection = lambda composition: projection_for(composition, CPScaleCanonicalStage.REMAINING)
    coordinator.backend.compose = lambda **kwargs: SimpleNamespace(valid=True, topology=SimpleNamespace(devices=[], links=[]),
        configuration=object(), control_plane=object(), capabilities={}, voice=None)
if target == "full-retain":
    original_decide = seams._checkpoint
    seams._checkpoint = lambda stage, *args, **kwargs: "retain" if stage == "full-qualification" else original_decide(stage, *args, **kwargs)
after_summary = []
original_checkpoint = coordinator.persistence.checkpoint
def checkpoint(*args, **kwargs):
    value = original_checkpoint(*args, **kwargs)
    after_summary.append(True)
    return value
coordinator.persistence.checkpoint = checkpoint
def write(report):
    record("write")
    if after_summary and broken == "write":
        raise OSError("final write failed")
coordinator.persistence.write_progress = write
def stop(self):
    record("transport.stop")
    if broken == "close":
        raise OSError("close failed")
Transport.stop = stop
def terminal(event, report):
    record("terminal")
    if broken == "presentation":
        raise OSError("terminal channel failed")
presentation = SimpleNamespace(terminal=terminal, core_rematerialized=lambda: None,
    finalization_incomplete=lambda report: record("report"))
coordinator.presentation = presentation
result = coordinator.run(request)
names = [item["event"] for item in calls]
last_stage = max(index for index, name in enumerate(names) if name == "execute_stage")
print(json.dumps({"outcome": result.outcome.value, "events": names[last_stage + 1:],
    "primary": result.primary_failure, "secondary": result.secondary_failures}))
''')
    expected = ["write", "archive"]
    if target != "full-retain":
        expected += ["cleanup", "archive"]
    if target == "full-cleanup":
        expected.insert(0, "checkpoint")
    expected += ["write", "summary", "write", "transport.stop"]
    if not broken:
        expected += ["terminal"]
    elif broken == "presentation":
        expected += ["terminal", "write", "report"]
    else:
        expected += ["write", "report"]
    assert verdict["events"] == expected, verdict
    assert verdict["outcome"] == ("failed" if broken else "completed")
    assert verdict["primary"] is None
    assert verdict["secondary"] == {
        "": [],
        "write": [
            "final_evidence_write: OSError: final write failed",
            "terminal_evidence_write: OSError: final write failed",
        ],
        "close": ["transport_stop: OSError: close failed"],
        "presentation": ["terminal_presentation: OSError: terminal channel failed"],
    }[broken]


@pytest.mark.parametrize("cleanup_raises", [False, True])
def test_final_result_preserves_ordered_stage_and_terminal_secondaries(cleanup_raises):
    verdict = _probe(RUN_DOUBLES + "\ncleanup_raises = " + repr(cleanup_raises) + r'''
from dataclasses import replace
from packet_tracer_mcp.application.cp_scale_live.contracts import (
    CPScaleLiveRequest, CPScaleStageSecondaryFailure, CPScaleDiagnosticRecord,
)
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "router0-branch")
coordinator = offline_coordinator(request)
def failed_stage(projection, **kwargs):
    acquired = execute_stage(projection, **kwargs)
    return replace(acquired, outcome="failed", failure="FIRST_CAUSE", first_failed_boundary="voice",
        secondary_failures=(CPScaleStageSecondaryFailure("bindings", "same error"),
                            CPScaleStageSecondaryFailure("statistics", "same error")),
        diagnostics=(CPScaleDiagnosticRecord(projection.stage, {}, error="diagnostic error"),))
seams._execute_stage = failed_stage
def archive(phase, payload, **kwargs):
    raise OSError(phase + " archive error")
coordinator.persistence.archive = archive
def restore(*args):
    if cleanup_raises:
        raise OSError("cleanup exception")
    return CPScaleCleanupResult(False, "restoration error")
coordinator.completion.cleanup.restore = restore
original_observations = coordinator.observations_factory
def observations(session):
    result = original_observations(session)
    result.cleanup_realtime = lambda: CPScaleCleanupRealtime(False, "realtime error")
    return result
coordinator.observations_factory = observations
original_write = coordinator.persistence.write_progress
def write(report):
    if report.failure:
        raise OSError("write error")
    return original_write(report)
coordinator.persistence.write_progress = write
def stop(self):
    record("transport.stop")
    raise OSError("close error")
Transport.stop = stop
result = coordinator.run(request)
print(json.dumps({"outcome": result.outcome.value, "primary": result.primary_failure,
    "secondaries": result.secondary_failures,
    "diagnostic_identity": result.progress.completed_stages[0].diagnostics[0].error,
    "closed": [item["event"] for item in calls if item["event"] == "transport.stop"]}))
''')
    assert verdict == {
        "outcome": "failed", "primary": "CanonicalLiveFailure: FIRST_CAUSE",
        "secondaries": [
            "stage:routing-core:bindings: same error",
            "stage:routing-core:statistics: same error",
            "stage:routing-core:diagnostic: diagnostic error",
            "precleanup_archive: OSError: failure-precleanup archive error",
            "cleanup: OSError: cleanup exception" if cleanup_raises else "cleanup_restoration: restoration error",
            "cleanup_realtime: realtime error",
            "cleanup_archive: OSError: cleanup-incomplete archive error",
            "final_evidence_write: OSError: write error",
            "transport_stop: OSError: close error",
            "terminal_evidence_write: OSError: write error",
        ],
        "diagnostic_identity": "diagnostic error", "closed": ["transport.stop"],
    }


def test_full_qualification_failure_keeps_legacy_stage_slot_and_typed_cause():
    verdict = _probe(RUN_DOUBLES + r'''
from dataclasses import replace
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False)
coordinator = offline_coordinator(request)
coordinator.build.reconcile = lambda topology, physical, **kwargs: Deployment()
coordinator.build.full_projection = lambda composition: projection_for(composition, CPScaleCanonicalStage.REMAINING)
def stage(projection, **kwargs):
    result = execute_stage(projection, **kwargs)
    if projection.stage is CPScaleCanonicalStage.REMAINING:
        return replace(result, outcome="failed", failure="FULL_FAILED", first_failed_boundary="control_plane")
    return result
seams._execute_stage = stage
evidence = []
seams._write_evidence = lambda value: evidence.append(value)
result = coordinator.run(request)
print(json.dumps({"outcome": result.outcome.value, "primary": result.primary_failure,
    "boundary": result.progress.first_failed_boundary,
    "last_stage": evidence[-1]["stages"][-1]["stage"],
    "last_outcome": evidence[-1]["stages"][-1].get("stage_outcome"),
    "full_published": "full_qualification" in evidence[-1],
    "typed_failure": result.progress.completed_stages[-1].failure}))
''')
    assert verdict == {"outcome": "failed", "primary": "CanonicalLiveFailure: FULL_FAILED",
        "boundary": "control_plane", "last_stage": "remaining", "last_outcome": "failed",
        "full_published": False, "typed_failure": "FULL_FAILED"}


def test_late_full_cleanup_observation_failure_prevents_terminal_success():
    verdict = _probe(RUN_DOUBLES + r'''
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False)
coordinator = offline_coordinator(request)
coordinator.build.reconcile = lambda topology, physical, **kwargs: Deployment()
coordinator.build.full_projection = lambda composition: projection_for(composition, CPScaleCanonicalStage.REMAINING)
coordinator.backend.compose = lambda **kwargs: SimpleNamespace(valid=True, topology=SimpleNamespace(devices=[], links=[]),
    configuration=object(), control_plane=object(), capabilities={}, voice=None)
seams._write_checkpoint_summary = lambda stage, evidence, **kwargs: record("summary", stage=stage)
original_observations = coordinator.observations_factory
reads = []
def observations(session):
    result = original_observations(session)
    def realtime():
        reads.append(True)
        return CPScaleCleanupRealtime(len(reads) == 1, "late realtime error" if len(reads) > 1 else "")
    result.cleanup_realtime = realtime
    return result
coordinator.observations_factory = observations
coordinator.presentation = SimpleNamespace(core_rematerialized=lambda: None,
    terminal=lambda *args: record("terminal"), finalization_incomplete=lambda report: record("report"))
result = coordinator.run(request)
print(json.dumps({"outcome": result.outcome.value, "secondary": result.secondary_failures,
    "calls": [item["event"] for item in calls if item["event"] in ("transport.stop", "terminal", "report")]}))
''')
    assert verdict == {"outcome": "failed", "secondary": ["cleanup_realtime: late realtime error"],
        "calls": ["transport.stop", "report"]}
