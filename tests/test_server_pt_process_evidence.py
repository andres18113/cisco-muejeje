"""Only an owned launch and observed graceful exit close the C31 archive."""

from __future__ import annotations

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
)


def test_launch_and_exit_evidence_bind_the_same_owned_process():
    """A close request without observed exit cannot finish the campaign."""
    from packet_tracer_mcp.application.use_cases.server_pt_process_evidence import (
        exit_evidence_findings,
        launch_evidence_findings,
    )

    process = DiagnosticLifecycleObservation(
        process_id=123,
        process_path="C:\\Program Files\\Cisco Packet Tracer\\PacketTracer.exe",
        process_incarnation="2026-09-23T00:00:00Z",
        product_version="9.0.1.0858",
    )
    launch = {
        "pid": 123,
        "process_path": process.process_path,
        "process_incarnation": process.process_incarnation,
        "created_by_campaign": True,
        "workspace_kind": "disposable_declared",
        "launch_method": "Start-Process",
    }
    close = {
        "pid": 123,
        "process_path": process.process_path,
        "process_incarnation": process.process_incarnation,
        "method": "CloseMainWindow",
        "requested": True,
        "actual_exit_observed": True,
    }

    assert launch_evidence_findings(launch, process) == ()
    assert exit_evidence_findings(launch, close, process_count=0) == ()
    assert "process_exit_unobserved" in exit_evidence_findings(
        launch, {**close, "actual_exit_observed": False}, process_count=1
    )
    assert "foreign_launch_identity" in launch_evidence_findings(
        {**launch, "pid": 999}, process
    )
