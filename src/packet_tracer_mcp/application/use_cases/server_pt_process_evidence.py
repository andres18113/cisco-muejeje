"""Pure ownership and graceful process-exit evidence rules for C31."""

from __future__ import annotations

from collections.abc import Mapping

from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
)
from .prepare_server_pt_commissioning import SERVER_PT_BUILD


def launch_evidence_findings(
    launch: Mapping[str, object], process: DiagnosticLifecycleObservation
) -> tuple[str, ...]:
    """Bind the campaign's owned launch to the fresh OS process reading."""
    found: list[str] = []
    if (
        process.error
        or not process.process_id
        or not process.process_path
        or not process.process_incarnation
        or launch.get("pid") != process.process_id
        or launch.get("process_path") != process.process_path
        or launch.get("process_incarnation") != process.process_incarnation
    ):
        found.append("foreign_launch_identity")
    if (
        launch.get("created_by_campaign") is not True
        or launch.get("workspace_kind") != "disposable_declared"
        or launch.get("launch_method") != "Start-Process"
    ):
        found.append("campaign_creation_unproven")
    if SERVER_PT_BUILD not in (process.product_version, process.file_version):
        found.append("process_build_mismatch")
    return tuple(found)


def exit_evidence_findings(
    launch: Mapping[str, object],
    close: Mapping[str, object],
    *,
    process_count: int | None,
) -> tuple[str, ...]:
    """Require graceful request and actual exit of exactly the owned process."""
    found: list[str] = []
    if (
        close.get("pid") != launch.get("pid")
        or close.get("process_path") != launch.get("process_path")
        or close.get("process_incarnation") != launch.get("process_incarnation")
        or close.get("method") != "CloseMainWindow"
        or close.get("requested") is not True
    ):
        found.append("graceful_close_identity_unproven")
    if (
        isinstance(process_count, bool)
        or process_count != 0
        or close.get("actual_exit_observed") is not True
    ):
        found.append("process_exit_unobserved")
    return tuple(found)
