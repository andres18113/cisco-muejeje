"""FASTLOOP Addendum 03: a document window is identified positively, per build.

`--retire` used to select the only visible, enabled, unowned window that was
not the extension log and named no file. A native dialog or an unknown window
left beside the log was therefore closed as if it were the document. Every
test here drives the production CLI, rule or ledger, and every refusal
asserts that no close was posted and no process terminated.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packet_tracer_mcp.application.use_cases import (
    server_pt_process_evidence as evidence,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign_ledger import (
    FASTLOOP_ALLOWANCE,
    opening_findings,
    phase_admission_findings,
)
from packet_tracer_mcp.application.use_cases.server_pt_process_evidence import (
    EXTENSION_LOG_WINDOW_TITLE,
    exit_evidence_findings,
    select_document_window,
    window_signature_for_launch,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_process_control import (
    OwnedWindowCensus,
)
from tests import test_server_pt_fastloop_retirement as retirement
from tests.test_server_pt_fastloop_retirement import (
    ATTEMPT,
    DOCUMENT,
    HIDDEN,
    LOG,
    PID,
    SIGNATURE,
    _appear,
    _attempts,
    _census,
    _run,
    _store,
    _window,
)

# The shared retirement fixtures: a FASTLOOP CLI and one recorded launch.
fastloop_cli = retirement.fastloop_cli
launched = retirement.launched

DIALOG_CLASS = "#32770"
SAVE_DIALOG = _window(6161, "Save changes", class_name=DIALOG_CLASS)
STARTUP_NOTICE = _window(6262, "Startup notice")
DIALOG_AS_DOCUMENT = _window(6363, "Cisco Packet Tracer", class_name=DIALOG_CLASS)
TOOL_AS_DOCUMENT = _window(
    6464, "Cisco Packet Tracer", class_name="Qt687QWindowToolSaveBits"
)


def _refused_without_effect(launched, capsys, tmp_path: Path, windows, finding):
    cli, env, base, system = launched
    system.windows_of[PID] = list(windows)

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2, refused
    assert system.posted == []
    assert "close_helper" not in system.calls
    assert "terminate" not in system.calls
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()
    attempts = _attempts(tmp_path)
    assert attempts and finding in attempts[-1]["refusal"]
    return refused


@pytest.mark.parametrize(
    ("windows", "finding"),
    [
        ((SAVE_DIALOG, LOG), "dialog_window_visible"),
        ((LOG, SAVE_DIALOG), "dialog_window_visible"),
        ((SAVE_DIALOG,), "dialog_window_visible"),
        ((STARTUP_NOTICE, LOG), "unclassified_window_visible"),
        ((LOG, STARTUP_NOTICE), "unclassified_window_visible"),
        ((DIALOG_AS_DOCUMENT, LOG), "dialog_window_visible"),
        ((TOOL_AS_DOCUMENT, LOG), "unclassified_window_visible"),
    ],
    ids=[
        "save-dialog-then-log",
        "log-then-save-dialog",
        "save-dialog-alone",
        "startup-notice-then-log",
        "log-then-startup-notice",
        "dialog-titled-like-the-document",
        "tool-window-titled-like-the-document",
    ],
)
def test_a_dialog_or_unknown_window_beside_the_log_is_never_closed(
    launched, capsys, tmp_path: Path, windows, finding
):
    """The only non-log window is not thereby the document."""
    _refused_without_effect(launched, capsys, tmp_path, windows, finding)


@pytest.mark.parametrize(
    "extra",
    [SAVE_DIALOG, STARTUP_NOTICE],
    ids=["save-dialog", "startup-notice"],
)
def test_a_dialog_or_unknown_window_beside_the_document_withholds_the_close(
    launched, capsys, tmp_path: Path, extra
):
    """A real document does not make an unclassified neighbour harmless."""
    finding = (
        "dialog_window_visible"
        if extra.class_name == DIALOG_CLASS
        else "unclassified_window_visible"
    )
    _refused_without_effect(launched, capsys, tmp_path, (DOCUMENT, extra, LOG), finding)


def test_the_exit_record_keeps_its_signature_readings_and_mailbox(
    launched, capsys, tmp_path: Path, monkeypatch
):
    """Method and times are those of the raw readings, not of the bounds."""
    cli, env, base, _system = launched
    mailbox = tmp_path / "bridge"
    mailbox.mkdir()
    (mailbox / "alive.txt").write_text("heartbeat", encoding="utf-8")
    monkeypatch.setattr(cli, "_MAILBOX_DIR", lambda: mailbox)

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    record = _store(tmp_path).load_process_exit(ATTEMPT)
    assert record["close_target"]["handle"] == DOCUMENT.handle
    signature = record["window_signature"]
    assert signature["build"] == "9.0.1.0858"
    assert signature["document_title"] == "Cisco Packet Tracer"
    assert signature["basis"]
    readings = record["absence_observations"]
    assert readings and readings[-1]["present"] is False
    assert all(item["started_at_utc"] <= item["answered_at_utc"] for item in readings)
    bounds = record["exit_bounds"]
    assert bounds["after_utc"] >= record["requested_at_utc"]
    assert bounds["before_utc"] == readings[-1]["answered_at_utc"]
    assert record["mailbox_before_close"] == {"pending_count": 0, "error": ""}
    assert record["mailbox_after_exit"] == {"pending_count": 0, "error": ""}
    assert record["process_count"] == 0


def test_a_process_that_is_not_isolated_retires_nothing(
    launched, capsys, tmp_path: Path, monkeypatch
):
    """The real preflight refuses this test process before any observation."""
    cli, env, base, system = launched
    monkeypatch.setattr(cli, "_RETIREMENT_ISOLATION", ImportIsolationPreflight)

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert refused["reason"].startswith("import_isolation_unverified:")
    assert system.calls == []
    assert _attempts(tmp_path) == []


def test_the_launch_names_the_build_the_os_reported(launched, tmp_path: Path):
    """The signature is chosen by an observed build, never by a claim."""
    record = _store(tmp_path).load_process_launch(ATTEMPT)

    assert record["observed_product_version"] == "9.0.1.0858"
    assert window_signature_for_launch(record) is SIGNATURE


def test_a_build_without_a_signature_is_observed_but_never_closed(
    launched, capsys, tmp_path: Path, monkeypatch
):
    """The census is kept; nothing is selected, posted or forced."""
    monkeypatch.setattr(evidence, "PT_WINDOW_SIGNATURES", {})

    refused = _refused_without_effect(
        launched, capsys, tmp_path, (DOCUMENT, LOG), "document_signature_unestablished"
    )

    assert refused["window_signature"] is None
    assert len(refused["window_census_before"]["windows"]) == 2


def test_every_attempt_names_the_signature_it_applied(launched, capsys, tmp_path: Path):
    """A refusal records how the document role would have been identified."""
    refused = _refused_without_effect(
        launched, capsys, tmp_path, (SAVE_DIALOG, LOG), "dialog_window_visible"
    )

    assert refused["window_signature"]["build"] == "9.0.1.0858"
    assert refused["window_signature"]["dialog_classes"] == [DIALOG_CLASS]
    assert refused["mailbox_before_close"]["error"] == ""


def test_a_window_left_after_a_failed_close_must_still_be_classified(
    launched, capsys, tmp_path: Path
):
    """An unknown window after the close withholds the force like a modal."""
    cli, env, base, system = launched
    system.on_close = "stay"
    close = system.close_window

    def close_then_notice(pid, handle, digest, **bound):
        result = close(pid, handle, digest, **bound)
        _appear(STARTUP_NOTICE)(system)
        return result

    system.close_window = close_then_notice

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2, refused
    assert system.posted == [DOCUMENT.handle]
    assert "terminate_helper" not in system.calls
    assert refused["refusal"] == ["unclassified_window_visible"]
    after = refused["window_census_after"]["windows"]
    assert any(item["title"] == "Startup notice" for item in after)


# -- the rule itself ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "windows",
    [(DOCUMENT, LOG), (LOG, DOCUMENT), (DOCUMENT,), (HIDDEN, LOG, DOCUMENT)],
    ids=["document-first", "log-first", "log-absent", "hidden-ignored"],
)
def test_the_signed_document_is_selected_in_any_order(windows):
    """Order, focus and the log window's presence change nothing."""
    assert select_document_window(PID, _census(*windows), signature=SIGNATURE) == (
        DOCUMENT,
        (),
    )


@pytest.mark.parametrize(
    ("windows", "findings"),
    [
        ((SAVE_DIALOG, LOG), ("dialog_window_visible", "document_window_absent")),
        (
            (STARTUP_NOTICE, LOG),
            ("unclassified_window_visible", "document_window_absent"),
        ),
        (
            (DIALOG_AS_DOCUMENT, LOG),
            ("dialog_window_visible", "document_window_absent"),
        ),
        (
            (TOOL_AS_DOCUMENT, LOG),
            ("unclassified_window_visible", "document_window_absent"),
        ),
        ((DOCUMENT, SAVE_DIALOG, LOG), ("dialog_window_visible",)),
        (
            (_window(4242, "Cisco Packet Tracer - C:\\coursework.pkt"), LOG),
            (
                "unclassified_window_visible",
                "document_window_names_file_or_nothing",
                "document_window_absent",
            ),
        ),
        (
            (_window(4343, EXTENSION_LOG_WINDOW_TITLE, class_name=DIALOG_CLASS),),
            ("dialog_window_visible", "document_window_absent"),
        ),
        (
            (replace(DOCUMENT, enabled=False), _window(5555, "Save?", owner=4242)),
            ("modal_or_owned_window_visible", "document_window_disabled"),
        ),
    ],
    ids=[
        "save-dialog",
        "startup-notice",
        "dialog-with-document-title",
        "tool-with-document-title",
        "dialog-beside-document",
        "file-named-document",
        "dialog-with-log-title",
        "owned-modal-first",
    ],
)
def test_only_positively_classified_windows_leave_a_document(windows, findings):
    """Each doubt is named, the owned or dialog cause first; nothing is selected."""
    assert select_document_window(PID, _census(*windows), signature=SIGNATURE) == (
        None,
        findings,
    )


@pytest.mark.parametrize(
    ("census", "finding"),
    [
        (
            OwnedWindowCensus(PID, error="window_census_unobservable:TimeoutExpired"),
            "window_census_unobservable",
        ),
        (_census(SAVE_DIALOG, LOG, complete=False), "window_census_incomplete"),
        (_census(SAVE_DIALOG, LOG, pid=999), "window_attribution_mismatch"),
    ],
)
def test_a_census_doubt_is_the_primary_cause_with_or_without_a_signature(
    census, finding
):
    """Window roles are never judged on a census that is not ours or whole."""
    for signature in (SIGNATURE, None):
        assert select_document_window(PID, census, signature=signature) == (
            None,
            (finding,),
        )
    assert select_document_window(PID, _census(DOCUMENT, LOG), signature=None) == (
        None,
        ("document_signature_unestablished",),
    )


@pytest.mark.parametrize(
    ("launch", "expected"),
    [
        ({"observed_product_version": "9.0.1.0858"}, True),
        ({"observed_file_version": "9.0.1.0858"}, True),
        (
            {
                "observed_product_version": "9.0.1.0858",
                "observed_file_version": "9.0.1.0858",
            },
            True,
        ),
        ({"observed_product_version": "9.0.0.0810"}, False),
        ({"product_version": "9.0.1.0858"}, False),
        ({}, False),
    ],
    ids=["product", "file", "both", "other-build", "claimed-field", "none"],
)
def test_a_signature_needs_an_observed_known_build(launch, expected):
    """Only the OS-observed version of a pinned build yields a signature."""
    assert (window_signature_for_launch(launch) is SIGNATURE) is expected


@pytest.mark.parametrize(
    "window",
    [SAVE_DIALOG, STARTUP_NOTICE, DIALOG_AS_DOCUMENT, TOOL_AS_DOCUMENT, LOG],
    ids=["save-dialog", "startup-notice", "dialog-titled", "tool-titled", "log"],
)
def test_a_targeted_close_record_must_name_the_signed_document(window):
    """An exit record whose target was not the build's document is refused."""
    launch = {
        "pid": PID,
        "process_path": "C:\\PacketTracer.exe",
        "process_incarnation": "2026-09-24T07:00:00-05:00",
        "observed_command_line": '"C:\\PacketTracer.exe" ',
        "observed_main_window_title": "Cisco Packet Tracer",
        "observed_product_version": "9.0.1.0858",
    }

    def close(target):
        return {
            **launch,
            "pid": PID,
            "method": "WM_CLOSE",
            "close_target": {
                "handle": target.handle,
                "owner_pid": target.owner_pid,
                "class_name": target.class_name,
                "title": target.title,
                "identity_digest": target.identity_digest,
            },
            "requested": True,
            "actual_exit_observed": True,
        }

    assert "graceful_close_identity_unproven" in exit_evidence_findings(
        launch, close(window), process_count=0
    )
    assert exit_evidence_findings(launch, close(DOCUMENT), process_count=0) == ()
    unsigned = {**launch, "observed_product_version": ""}
    assert "graceful_close_identity_unproven" in exit_evidence_findings(
        unsigned, {**close(DOCUMENT), **unsigned, "pid": PID}, process_count=0
    )


# -- a lifecycle-only episode ----------------------------------------------------------

OPENED = datetime(2026, 9, 24, 18, 0, tzinfo=UTC)
HEAD = "a" * 40
TREE = "b" * 40


def _lifecycle_opening() -> dict[str, object]:
    return {
        "kind": "episode_opening",
        "episode": 2,
        "question": "Does --retire close the genuine document of a fresh lab?",
        "stop_rule": "one launch, one census, one --retire, then close",
        "source_sha": HEAD,
        "source_tree": TREE,
        "source_upstream_head": "c" * 40,
        "tests_run": ["tests/test_server_pt_document_window_signature.py"],
        "attempt_ids": [ATTEMPT],
        "targets": ["one campaign-launched disposable PacketTracer.exe"],
        "permitted_effects": ["retirement: --retire"],
        "allocated_operations": 0,
        "allocated_seconds": 300,
        "opened_at_utc": OPENED.isoformat(),
    }


def _closed_first_episode() -> dict[str, dict[str, object]]:
    first = {
        **_lifecycle_opening(),
        "episode": 1,
        "allocated_operations": 10,
        "opened_at_utc": (OPENED - timedelta(hours=1)).isoformat(),
    }
    closing = {
        "kind": "episode_closing",
        "episode": 1,
        "closed_at_utc": (OPENED - timedelta(minutes=30)).isoformat(),
    }
    return {"episode-0001-opening": first, "episode-0001-closing": closing}


def test_a_lifecycle_episode_may_allocate_no_operation():
    """Zero bridge operations is a finite allocation, not a missing one."""
    records = _closed_first_episode()

    assert (
        opening_findings(records, _lifecycle_opening(), FASTLOOP_ALLOWANCE, OPENED)
        == ()
    )
    assert "episode_allocation_not_finite_positive" in opening_findings(
        records,
        {**_lifecycle_opening(), "allocated_seconds": 0},
        FASTLOOP_ALLOWANCE,
        OPENED,
    )


@pytest.mark.parametrize(
    "phase", ["prequalification", "setup", "acceptance", "cleanup"]
)
def test_a_lifecycle_episode_admits_no_bridge_phase(phase):
    """Not even cleanup may draw the protected reserve from it."""
    records = {**_closed_first_episode(), "episode-0002-opening": _lifecycle_opening()}

    findings, protected = phase_admission_findings(
        records,
        episode=2,
        attempt_id=ATTEMPT,
        phase=phase,
        granted_operations=1,
        granted_seconds=1.0,
        allowance=FASTLOOP_ALLOWANCE,
        now=OPENED + timedelta(seconds=5),
        source_sha=HEAD,
        source_tree=TREE,
    )

    assert findings == ("episode_allocates_no_bridge_operation",)
    assert protected is False
