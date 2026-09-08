"""Causal coverage for CP-LIVE finalization.

Finalization owes three things at once: persist what happened, close what the
session acquired, and never let either of those failures replace the cause that
ended the session.  The baseline ran the last two as a single statement, so a
failed final write skipped ``transport.stop()`` and a failed stop replaced the
primary cause with its own ``OSError``.

These probes drive the real ``run()`` in a child process with the pre-existing
Router0 doubles.  ``run()`` keeps returning ``int`` and keeps the published
codes, so the invariant is stated over the returned code, the attempted close,
and the finalization report -- not over an exception the API never promised.
"""

from __future__ import annotations

import pytest

from tests.cp_live_m0_harness import RUN_DOUBLES, run_product_probe


FINALIZATION_EVENT = "CP_SCALE_FINALIZATION_INCOMPLETE"


_FINALIZATION_DOUBLES = r'''
import contextlib
import io

writes = []
finalizing = []
summary_double = live._write_checkpoint_summary


def summary_marker(stage, evidence, **kwargs):
    # The terminal checkpoint summary is the last step a successful run takes
    # before returning, so any evidence write after it belongs to finalization.
    # The frozen oracle pins exactly that order for this scenario:
    # archive -> cleanup -> archive -> write -> summary -> write -> stop.
    finalizing.append(stage)
    return summary_double(stage, evidence, **kwargs)


live._write_checkpoint_summary = summary_marker


def record_write(evidence):
    writes.append({
        "closure": str(evidence.get("closure") or ""),
        "primary_failure": str(evidence.get("failure") or ""),
        "after_terminal_summary": bool(finalizing),
    })
    record("evidence.write", after_terminal_summary=bool(finalizing))


def is_final_write(evidence):
    # Both discriminators name the same write: the one the ``finally`` block
    # performs.  A failed run reaches it with the primary cause recorded; a
    # successful one reaches it after the terminal summary.
    return bool(evidence.get("failure")) or bool(finalizing)


def write_evidence(evidence):
    record_write(evidence)
    if not is_final_write(evidence):
        return
    if CANCEL_AT_FINAL_WRITE:
        raise KeyboardInterrupt("OPERATOR_CANCELLED_DURING_FINALIZATION")
    if WRITE_FAILS:
        raise OSError("FINAL_EVIDENCE_WRITE_FAILED")


def stop(self):
    record("transport.stop")
    if STOP_FAILS:
        raise OSError("TRANSPORT_STOP_FAILED")


def failing_stage(projection, **kwargs):
    record("execute_stage", stage=projection.stage.value)
    raise live.CanonicalLiveFailure(
        "PRIMARY_STAGE_FAILURE",
        stage_evidence={
            "stage": projection.stage.value,
            "first_failed_boundary": "configuration",
        },
    )


def cancelled_stage(projection, **kwargs):
    record("execute_stage", stage=projection.stage.value)
    raise KeyboardInterrupt("OPERATOR_CANCELLED_DURING_STAGE")


live._write_evidence = write_evidence
Transport.stop = stop
if PRIMARY_FAILS:
    live._execute_stage = failing_stage
if CANCEL_AT_STAGE:
    live._execute_stage = cancelled_stage

stream = io.StringIO()
returned = None
raised = ""
try:
    with contextlib.redirect_stdout(stream):
        returned = live.run(
            "9.0.1.0858",
            expected_head=HEAD,
            retain_on_full_verification=False,
            target_stage="router0-branch",
        )
except BaseException as exc:  # a cancellation must stay observable, not vanish
    raised = type(exc).__name__ + ": " + str(exc)
reports = []
for line in stream.getvalue().splitlines():
    if line.startswith("{"):
        reports.append(json.loads(line))
print(json.dumps({
    "returned": returned,
    "raised": raised,
    "events": calls,
    "writes": writes,
    "reports": reports,
}))
'''


def _probe_source(
    *,
    primary_fails: bool = False,
    write_fails: bool = False,
    stop_fails: bool = False,
    cancel_at_stage: bool = False,
    cancel_at_final_write: bool = False,
) -> str:
    """Compose a child source from booleans only; never interpolate input."""

    flags = "".join(
        f"{name} = {bool(value)!r}\n"
        for name, value in (
            ("PRIMARY_FAILS", primary_fails),
            ("WRITE_FAILS", write_fails),
            ("STOP_FAILS", stop_fails),
            ("CANCEL_AT_STAGE", cancel_at_stage),
            ("CANCEL_AT_FINAL_WRITE", cancel_at_final_write),
        )
    )
    return RUN_DOUBLES + flags + _FINALIZATION_DOUBLES


def _finalization_report(verdict: dict) -> dict:
    reports = [
        item for item in verdict["reports"]
        if item.get("event") == FINALIZATION_EVENT
    ]
    assert len(reports) == 1, verdict
    return reports[0]


@pytest.mark.parametrize(
    ("primary_fails", "write_fails", "stop_fails"),
    [
        (True, True, False),
        (True, False, True),
        (True, True, True),
        (False, True, False),
        (False, False, True),
        (False, True, True),
    ],
)
def test_finalization_closes_and_never_replaces_the_cause(
    primary_fails,
    write_fails,
    stop_fails,
    tmp_path,
):
    verdict = run_product_probe(
        _probe_source(
            primary_fails=primary_fails,
            write_fails=write_fails,
            stop_fails=stop_fails,
        ),
        tmp_path / f"{int(primary_fails)}{int(write_fails)}{int(stop_fails)}",
    )

    # The API is unchanged: run() settles on a published code and raises
    # nothing, whichever half of finalization failed.
    assert verdict["raised"] == "", verdict
    assert verdict["returned"] == 1, verdict
    # Acquired, therefore closed: the failed write did not skip the close.
    assert any(item["event"] == "transport.stop" for item in verdict["events"]), (
        verdict
    )

    report = _finalization_report(verdict)
    expected_secondaries = [
        prefix for prefix, failed in (
            ("final_evidence_write:", write_fails),
            ("transport_stop:", stop_fails),
        ) if failed
    ]
    assert [
        item.split(" ")[0] for item in report["finalization_errors"]
    ] == expected_secondaries, verdict
    if write_fails:
        assert "FINAL_EVIDENCE_WRITE_FAILED" in report["finalization_errors"][0]
    if stop_fails:
        assert "TRANSPORT_STOP_FAILED" in report["finalization_errors"][-1]

    if primary_fails:
        # The primary cause survives its own secondaries and stays the reason.
        assert "PRIMARY_STAGE_FAILURE" in report["primary_failure"], verdict
    else:
        # No primary cause, so an unfinished finalization is the failure and
        # the successful run may not report success.
        assert report["primary_failure"] == "", verdict
        assert any(
            item.get("event") == "ROUTER0_BRANCH_VERIFIED_AND_CLEANED"
            for item in verdict["reports"]
        ), verdict

    # An attempted close is not a restoration claim: the report says only what
    # finalization could not complete.
    assert set(report) == {
        "event",
        "run_identity",
        "primary_failure",
        "hard_stop",
        "finalization_errors",
    }, report


@pytest.mark.parametrize("stop_fails", [False, True])
def test_the_failing_write_is_the_finalization_write(stop_fails, tmp_path):
    verdict = run_product_probe(
        _probe_source(write_fails=True, stop_fails=stop_fails),
        tmp_path / f"final-write-{int(stop_fails)}",
    )

    # The premise of the "no previous failure" cases: the session itself
    # succeeded, reached its terminal closure, and only finalization failed.
    final_write = verdict["writes"][-1]
    assert final_write["after_terminal_summary"] is True, verdict
    assert final_write["primary_failure"] == "", verdict
    assert final_write["closure"] == "ROUTER0_BRANCH_VERIFIED_AND_CLEANED", verdict
    assert verdict["returned"] == 1, verdict


def test_a_healthy_finalization_still_succeeds_and_reports_nothing(tmp_path):
    verdict = run_product_probe(_probe_source(), tmp_path / "healthy")

    assert verdict["returned"] == 0, verdict
    assert verdict["raised"] == ""
    assert [
        item for item in verdict["reports"]
        if item.get("event") == FINALIZATION_EVENT
    ] == []
    assert any(item["event"] == "transport.stop" for item in verdict["events"])


@pytest.mark.parametrize("stop_fails", [False, True])
def test_a_cancelled_stage_still_closes_and_never_becomes_an_exit_code(
    stop_fails,
    tmp_path,
):
    verdict = run_product_probe(
        _probe_source(cancel_at_stage=True, stop_fails=stop_fails),
        tmp_path / f"cancel-stage-{int(stop_fails)}",
    )

    assert verdict["returned"] is None, verdict
    assert verdict["raised"].startswith("KeyboardInterrupt"), verdict
    assert "OPERATOR_CANCELLED_DURING_STAGE" in verdict["raised"], verdict
    assert any(item["event"] == "transport.stop" for item in verdict["events"])


def test_a_cancellation_inside_the_final_write_still_closes_and_travels(tmp_path):
    verdict = run_product_probe(
        _probe_source(cancel_at_final_write=True, stop_fails=True),
        tmp_path / "cancel-final-write",
    )

    assert verdict["returned"] is None, verdict
    assert "OPERATOR_CANCELLED_DURING_FINALIZATION" in verdict["raised"], verdict
    # The close was attempted anyway, its own failure did not replace the
    # cancellation, and no code was manufactured from either.
    assert any(item["event"] == "transport.stop" for item in verdict["events"])
    assert "TRANSPORT_STOP_FAILED" not in verdict["raised"], verdict
    assert [
        item for item in verdict["reports"]
        if item.get("event") == FINALIZATION_EVENT
    ] == []
