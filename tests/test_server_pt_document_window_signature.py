"""FASTLOOP Addendum 03: a document window is identified positively, per build.

`--retire` used to select the only visible, enabled, unowned window that was
not the extension log and named no file. A native dialog or an unknown window
left beside the log was therefore closed as if it were the document. Every
test here drives the production CLI, rule or ledger, and every refusal
asserts that no close was posted and no process terminated.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packet_tracer_mcp.application.use_cases import (
    server_pt_process_evidence as evidence,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign_ledger import (
    FASTLOOP_ALLOWANCE,
    closing_findings,
    ledger_record_findings,
    ledger_totals,
    opening_findings,
    phase_admission_findings,
)
from packet_tracer_mcp.application.use_cases.server_pt_process_evidence import (
    EXTENSION_LOG_WINDOW_TITLE,
    exit_evidence_findings,
    packet_tracer_process_role,
    select_document_window,
    window_signature_for_launch,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_process_control import (
    OwnedWindowCensus,
    PacketTracerProcessCensus,
    PowerShellOwnedProcessControl,
    parse_packet_tracer_processes,
)
from tests import test_server_pt_fastloop_retirement as retirement
from tests.test_server_pt_fastloop_retirement import (
    ATTEMPT,
    COMMAND_LINE,
    DOCUMENT,
    HELPER_PID,
    HELPER_ROW,
    HIDDEN,
    LOG,
    OWNED_ROW,
    PATH,
    PID,
    SIGNATURE,
    START_TICKS,
    _appear,
    _attempts,
    _census,
    _process_row,
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
                "visible": target.visible,
                "enabled": target.enabled,
                "owner_handle": target.owner_handle,
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


# -- review delta: evidence the record may not overstate -------------------------------


@pytest.mark.parametrize(
    "change",
    [{"owner_handle": 4242}, {"visible": False}, {"enabled": False}],
    ids=["owned", "hidden", "disabled"],
)
def test_a_targeted_close_needs_a_visible_enabled_unowned_target(change):
    """A modal, hidden or disabled window is not a document close target."""
    launch = {
        "pid": PID,
        "process_path": "C:\\PacketTracer.exe",
        "process_incarnation": "2026-09-24T07:00:00-05:00",
        "observed_command_line": '"C:\\PacketTracer.exe" ',
        "observed_main_window_title": "Cisco Packet Tracer",
        "observed_product_version": "9.0.1.0858",
    }
    target = {
        "handle": DOCUMENT.handle,
        "owner_pid": PID,
        "class_name": DOCUMENT.class_name,
        "title": DOCUMENT.title,
        "visible": True,
        "enabled": True,
        "owner_handle": 0,
        "identity_digest": DOCUMENT.identity_digest,
    }
    close = {
        **launch,
        "method": "WM_CLOSE",
        "requested": True,
        "actual_exit_observed": True,
    }

    assert (
        exit_evidence_findings(
            launch, {**close, "close_target": target}, process_count=0
        )
        == ()
    )
    assert "graceful_close_identity_unproven" in exit_evidence_findings(
        launch, {**close, "close_target": {**target, **change}}, process_count=0
    )


def test_record_exit_never_admits_a_targeted_close_capture(
    launched, capsys, tmp_path: Path, monkeypatch
):
    """Only --retire posts WM_CLOSE, so only --retire may record one."""
    cli, env, base, _system = launched

    class _NoProcess:
        def __init__(self, **_kwargs):
            pass

        def read(self):
            return type("Observed", (), {"error": "", "processes": ()})()

    monkeypatch.setattr(cli, "PowerShellPacketTracerProcessReader", _NoProcess)
    launch = _store(tmp_path).load_process_launch(ATTEMPT)
    capture = tmp_path / "close.json"
    capture.write_text(
        json.dumps(
            {
                "pid": PID,
                "process_path": launch["process_path"],
                "process_incarnation": launch["process_incarnation"],
                "method": "WM_CLOSE",
                "close_target": {
                    "handle": DOCUMENT.handle,
                    "owner_pid": PID,
                    "class_name": DOCUMENT.class_name,
                    "title": DOCUMENT.title,
                    "visible": True,
                    "enabled": True,
                    "owner_handle": 0,
                    "identity_digest": DOCUMENT.identity_digest,
                },
                "requested": True,
                "actual_exit_observed": True,
            }
        ),
        encoding="utf-8",
    )

    code, refused = _run(
        cli, ["--record-exit", *base, "--close-evidence", str(capture)], env, capsys
    )

    assert code == 2, refused
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()


class _SteppedClock(datetime):
    """Wall time that steps back 100 s once `stepped` is set."""

    stepped = False

    @classmethod
    def now(cls, tz=None):
        value = datetime.now(tz)
        return value - timedelta(seconds=100) if cls.stepped else value


def test_a_wall_clock_step_withholds_the_exit_bounds(
    launched, capsys, tmp_path: Path, monkeypatch
):
    """The exit is still observed; its bounds are not claimed across a step."""
    cli, env, base, system = launched
    _SteppedClock.stepped = False
    monkeypatch.setattr(cli, "datetime", _SteppedClock)
    close = system.close_window

    def close_then_step(pid, handle, digest, **bound):
        result = close(pid, handle, digest, **bound)
        _SteppedClock.stepped = True
        return result

    system.close_window = close_then_step

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    record = _store(tmp_path).load_process_exit(ATTEMPT)
    assert record["actual_exit_observed"] is True
    assert record["exit_bounds"] == {"unavailable": "wall_clock_discontinuous"}


def test_a_closed_lifecycle_episode_is_charged_at_least_its_allocation():
    """With no phase to charge, a clock step cannot shrink its time."""
    records = {
        **_closed_first_episode(),
        "episode-0002-opening": _lifecycle_opening(),
        "episode-0002-closing": {
            "kind": "episode_closing",
            "episode": 2,
            "closed_at_utc": (OPENED + timedelta(seconds=50)).isoformat(),
        },
    }

    totals = ledger_totals(records, FASTLOOP_ALLOWANCE, OPENED + timedelta(hours=1))

    assert totals.committed_seconds >= 1800 + 300
    assert totals.open_episode is None


def test_an_episode_cannot_close_before_it_opened():
    """A closing earlier than its opening is refused, not charged as zero."""
    records = {**_closed_first_episode(), "episode-0002-opening": _lifecycle_opening()}

    assert closing_findings(records, 2, OPENED - timedelta(seconds=1)) == (
        "episode_closing_precedes_opening",
    )
    assert closing_findings(records, 2, OPENED + timedelta(seconds=1)) == ()


# -- lifecycle attempt 1: the owned helper outlives the owned process ------------------


def _helper_lingers(system, censuses: int) -> None:
    """Keep the owned helper counted for `censuses` calls after the exit."""
    system.rows_after_exit = [(HELPER_ROW,)] * censuses


def test_the_exit_waits_for_the_owned_helper_before_its_census(
    launched, capsys, tmp_path: Path
):
    """Episode 2 counted the exiting --progress-bar-server helper and refused."""
    cli, env, base, system = launched
    _helper_lingers(system, censuses=3)

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    record = _store(tmp_path).load_process_exit(ATTEMPT)
    assert record["process_count"] == 0
    counts = [item["count"] for item in record["process_census_readings"]]
    assert counts == [1, 1, 1, 0]
    assert all(
        item["started_at_utc"] <= item["answered_at_utc"]
        for item in record["process_census_readings"]
    )
    assert (
        record["process_census_readings"][0]["started_at_utc"]
        >= (record["exit_bounds"]["before_utc"])
    )


def test_a_helper_that_never_exits_leaves_the_exit_unarchived(
    launched, capsys, tmp_path: Path
):
    """The bounded wait ends; the refusal keeps every census, and nothing is forced."""
    cli, env, base, system = launched
    _helper_lingers(system, censuses=10_000)

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2, refused
    assert "process_exit_unobserved" in refused["findings"]
    assert "terminate_helper" not in system.calls
    assert refused["process_census_readings"]
    assert all(item["count"] == 1 for item in refused["process_census_readings"])
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()


@pytest.mark.parametrize(
    "stranger",
    [
        _process_row(777, 4, START_TICKS + 1, COMMAND_LINE),
        _process_row(777, PID, START_TICKS + 1, "PacketTracer.exe C:\\coursework.pkt"),
        _process_row(
            HELPER_PID, PID, START_TICKS - 50_000_000, HELPER_ROW.command_line
        ),
        _process_row(
            HELPER_PID, PID, START_TICKS + 1, HELPER_ROW.command_line, "C:\\x.exe"
        ),
    ],
    ids=["unrelated", "child-not-helper", "created-before-launch", "other-image"],
)
def test_a_packet_tracer_the_campaign_did_not_start_withholds_the_exit(
    launched, capsys, tmp_path: Path, stranger
):
    """A foreign process seen after the exit is not waited out; it refuses."""
    cli, env, base, system = launched
    system.rows_after_exit = [(stranger,), (stranger,)]

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2, refused
    assert "foreign_packet_tracer_process" in refused["refusal"]
    assert "terminate_helper" not in system.calls
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()
    first = refused["process_census_readings"][0]
    assert first["processes"][0]["process_id"] == stranger.process_id
    assert len(refused["process_census_readings"]) == 1


def test_a_nonfinite_time_allocation_is_malformed():
    """NaN or infinity would defeat every time comparison and charge."""
    records = _closed_first_episode()
    for value in (float("nan"), float("inf")):
        opening = {**_lifecycle_opening(), "allocated_seconds": value}
        assert opening_findings(records, opening, FASTLOOP_ALLOWANCE, OPENED) == (
            "episode_opening_malformed",
        )
        assert ledger_record_findings("episode-0002-opening", opening, records) == (
            "ledger_record_malformed",
        )


# -- the identity census and its ownership rule -----------------------------------------


def _launch_record() -> dict[str, object]:
    return {"pid": PID, "process_path": PATH}


@pytest.mark.parametrize(
    ("row", "role"),
    [
        (OWNED_ROW, "owned"),
        (_process_row(PID, 4, START_TICKS + 9, COMMAND_LINE), "owned"),
        (_process_row(PID, 4, START_TICKS + 10, COMMAND_LINE), "foreign"),
        (HELPER_ROW, "owned_helper"),
        (
            _process_row(HELPER_PID, PID, START_TICKS, HELPER_ROW.command_line, ""),
            "owned_helper",
        ),
        (
            _process_row(HELPER_PID, 999, START_TICKS + 1, HELPER_ROW.command_line),
            "foreign",
        ),
        (_process_row(HELPER_PID, PID, START_TICKS + 1, COMMAND_LINE), "foreign"),
        (
            _process_row(
                HELPER_PID, PID, START_TICKS + 1, '"C:\\y.exe" --progress-bar-server'
            ),
            "foreign",
        ),
    ],
    ids=[
        "owned",
        "owned-at-census-resolution",
        "same-pid-other-instant",
        "helper",
        "helper-without-image",
        "helper-of-another-parent",
        "child-without-helper-argument",
        "helper-of-another-image",
    ],
)
def test_each_listed_process_is_owned_its_helper_or_foreign(row, role):
    """Parent, creation, image and argument prove a helper; nothing else does."""
    assert packet_tracer_process_role(_launch_record(), START_TICKS, row) == role


def test_the_identity_census_names_no_external_text_and_fails_closed():
    """The command is constant; every doubtful answer is an error, not 'none'."""
    runner = retirement._Runner(
        stdout='[{"pid":124,"parent":123,"ticks":5,"path":"","command_line":"x"}]'
    )
    census = PowerShellOwnedProcessControl(run_command=runner).packet_tracer_processes()

    assert census.error == ""
    assert census.processes[0].parent_process_id == PID
    argv = runner.calls[-1]
    assert argv[:3] == ["powershell.exe", "-NoProfile", "-Command"]
    assert "PacketTracer*" in argv[3] and str(PID) not in argv[3]
    for stdout in (
        "",
        "{}",
        "[1]",
        '[{"pid":1,"parent":2,"ticks":0,"path":"","command_line":""}]',
        '[{"pid":1,"parent":2,"ticks":true,"path":"","command_line":""}]',
        '[{"pid":1,"parent":2,"ticks":3,"path":null,"command_line":""}]',
        '[{"pid":1,"parent":2,"ticks":3,"path":"","command_line":""},'
        '{"pid":1,"parent":2,"ticks":3,"path":"","command_line":""}]',
    ):
        assert parse_packet_tracer_processes(stdout).error == "process_census_malformed"
    assert parse_packet_tracer_processes("[]").processes == ()
    failing = retirement._Runner(error=subprocess.TimeoutExpired("powershell", 15))
    assert (
        PowerShellOwnedProcessControl(run_command=failing)
        .packet_tracer_processes()
        .error.startswith("process_census_unobservable")
    )


# -- final review: a failed enumeration is unknown, never empty -------------------------


class _AnsweringRunner:
    """Answer the census command with fixed stdout, stderr and exit code."""

    def __init__(self, stdout: str, stderr: str = "", code: int = 0):
        self.stdout, self.stderr, self.code = stdout, stderr, code
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if kwargs.get("check") and self.code:
            raise subprocess.CalledProcessError(
                self.code, argv, self.stdout, self.stderr
            )
        return subprocess.CompletedProcess(argv, self.code, self.stdout, self.stderr)


def test_a_census_that_reports_an_error_is_not_an_empty_census():
    """Access denied on stderr with `[]` and exit 0 is unknown, not 'none'."""
    denied = _AnsweringRunner("[]", "Get-CimInstance : Access denied")
    census = PowerShellOwnedProcessControl(run_command=denied).packet_tracer_processes()

    assert census.processes == ()
    assert census.error.startswith("process_census_unobservable")
    command = denied.calls[-1][3]
    assert command.startswith("$ErrorActionPreference = 'Stop'; ")
    assert "Get-CimInstance Win32_Process -ErrorAction Stop" in command
    failed = _AnsweringRunner("[]", "terminating error", code=1)
    assert (
        PowerShellOwnedProcessControl(run_command=failed)
        .packet_tracer_processes()
        .error.startswith("process_census_unobservable")
    )
    clean = _AnsweringRunner("[]")
    assert (
        PowerShellOwnedProcessControl(run_command=clean).packet_tracer_processes()
        == PacketTracerProcessCensus()
    )


def test_an_unknown_census_after_the_exit_never_archives_it(
    launched, capsys, tmp_path: Path
):
    """The owned process is gone, but no census can say that nothing remains."""
    cli, env, base, system = launched

    def unknown():
        if system.present:
            return retirement.SimpleNamespace(
                processes=(retirement.OWNED_ROW,), error=""
            )
        return retirement.SimpleNamespace(
            processes=(), error="process_census_unobservable:ValueError"
        )

    system.packet_tracer_processes = unknown

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2, refused
    assert refused["process_count"] is None
    assert "process_exit_unobserved" in refused["findings"]
    assert all(item["count"] is None for item in refused["process_census_readings"])
    assert "terminate_helper" not in system.calls
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()
