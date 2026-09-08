"""Red causal reproductions for the CP-LIVE finalization baseline defect.

These tests intentionally state the safety invariant, not the behavior of the
defective baseline.  They must remain failing until a separately authorized
baseline fix makes final evidence persistence and transport closure independent
and preserves the primary failure.
"""

from __future__ import annotations

from tests.cp_live_m0_harness import RUN_DOUBLES, run_product_probe


def test_final_evidence_write_failure_must_not_prevent_transport_close(
    tmp_path,
):
    verdict = run_product_probe(
        RUN_DOUBLES + r'''
def fail_stage(projection, **kwargs):
    record("execute_stage", stage=projection.stage.value)
    raise live.CanonicalLiveFailure(
        "PRIMARY_STAGE_FAILURE",
        stage_evidence={
            "stage": projection.stage.value,
            "first_failed_boundary": "configuration",
        },
    )


live._execute_stage = fail_stage


def fail_final_write(evidence):
    record("evidence.write", failure=bool(evidence.get("failure")))
    if evidence.get("failure"):
        raise OSError("FINAL_EVIDENCE_WRITE_FAILED")


live._write_evidence = fail_final_write
try:
    returned = live.run(
        "9.0.1.0858",
        expected_head=HEAD,
        retain_on_full_verification=False,
        target_stage="router0-branch",
    )
    raised = ""
except Exception as exc:
    returned = None
    raised = type(exc).__name__ + ": " + str(exc)
print(json.dumps({
    "returned": returned,
    "raised": raised,
    "events": calls,
    "transport_stop_attempted": any(
        item["event"] == "transport.stop" for item in calls
    ),
}))
''',
        tmp_path / "write-failure",
    )

    violations = []
    if not verdict["transport_stop_attempted"]:
        violations.append("transport.stop was not attempted")
    if "PRIMARY_STAGE_FAILURE" not in verdict["raised"]:
        violations.append("the primary stage failure was replaced")

    assert not violations, {"violations": violations, **verdict}


def test_transport_close_failure_must_not_replace_the_primary_failure(tmp_path):
    verdict = run_product_probe(
        RUN_DOUBLES + r'''
def fail_stage(projection, **kwargs):
    record("execute_stage", stage=projection.stage.value)
    raise live.CanonicalLiveFailure("PRIMARY_STAGE_FAILURE")


def fail_stop(self):
    record("transport.stop")
    raise OSError("TRANSPORT_STOP_FAILED")


live._execute_stage = fail_stage
Transport.stop = fail_stop
try:
    returned = live.run(
        "9.0.1.0858",
        expected_head=HEAD,
        retain_on_full_verification=False,
        target_stage="router0-branch",
    )
    raised = ""
except Exception as exc:
    returned = None
    raised = type(exc).__name__ + ": " + str(exc)
print(json.dumps({
    "returned": returned,
    "raised": raised,
    "events": calls,
}))
''',
        tmp_path / "stop-failure",
    )

    assert "PRIMARY_STAGE_FAILURE" in verdict["raised"], verdict
    assert "TRANSPORT_STOP_FAILED" in verdict["raised"], verdict
