"""FASTLOOP retirement by window observation, and the historical exit import.

Addendum 02 replaces the main-window-title guard of `--retire` with a bounded,
process-bound window census and one revalidated close, and authorizes one
append-only import of episode 1's exit. Every test drives the production rule,
helper, CLI or store that decides it, and every failure asserts that no close
was posted and no process terminated.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from importlib import import_module
from pathlib import Path

import pytest

from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign import (
    FASTLOOP_CAMPAIGN,
)
from packet_tracer_mcp.application.use_cases.server_pt_historical_exit import (
    FASTLOOP_EPISODE_1_EXIT_IMPORT,
    HistoricalExitImportAuthority,
    historical_exit_import_findings,
)
from packet_tracer_mcp.application.use_cases.server_pt_phase_grant import (
    derive_server_pt_phase_grant,
)
from packet_tracer_mcp.application.use_cases.server_pt_process_evidence import (
    EXTENSION_LOG_WINDOW_TITLE,
    exit_evidence_findings,
    force_window_findings,
    select_document_window,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
    SourceAncestry,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_process_control import (
    WINDOW_CENSUS_LIMIT,
    OwnedProcessObservation,
    OwnedWindow,
    OwnedWindowCensus,
    PowerShellOwnedProcessControl,
    WindowCloseResult,
    window_identity_digest,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)

ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
OTHER = "1f1e2d3c4b5a69788796a5b4c3d2e1f0"
HEAD = "a" * 40
TREE = "b" * 40
PID = 123
FOREIGN_PID = 999
PATH = "C:\\Program Files\\Cisco Packet Tracer 9.0.1\\bin\\PacketTracer.exe"
INCARNATION = "2026-09-24T07:00:00-05:00"
COMMAND_LINE = f'"{PATH}" '
QT_CLASS = "Qt663QWindowIcon"


def _window(
    handle: int,
    title: str,
    *,
    pid: int = PID,
    visible: bool = True,
    enabled: bool = True,
    owner: int = 0,
    class_name: str = QT_CLASS,
) -> OwnedWindow:
    return OwnedWindow(
        handle=handle,
        owner_pid=pid,
        class_name=class_name,
        title=title,
        visible=visible,
        enabled=enabled,
        owner_handle=owner,
        identity_digest=window_identity_digest(class_name, title),
    )


DOCUMENT = _window(4242, "Cisco Packet Tracer")
LOG = _window(4343, EXTENSION_LOG_WINDOW_TITLE)
HIDDEN = _window(4444, "QTrayIconMessageWindow", visible=False)


def _census(*windows: OwnedWindow, pid: int = PID, complete: bool = True):
    return OwnedWindowCensus(pid, windows=windows, complete=complete)


# -- selection and force rules --------------------------------------------------------


@pytest.mark.parametrize(
    "windows",
    [
        (DOCUMENT, LOG),
        (LOG, DOCUMENT),
        (DOCUMENT,),
        (HIDDEN, LOG, DOCUMENT),
    ],
    ids=["document-first", "log-first", "log-gone", "hidden-ignored"],
)
def test_order_focus_and_the_log_window_select_the_same_document(windows):
    """Enumeration order and the log window's presence change nothing."""
    selected, found = select_document_window(PID, _census(*windows))

    assert found == ()
    assert selected == DOCUMENT


@pytest.mark.parametrize(
    ("census", "finding"),
    [
        (
            OwnedWindowCensus(PID, error="window_census_unobservable:TimeoutExpired"),
            "window_census_unobservable",
        ),
        (_census(DOCUMENT, LOG, complete=False), "window_census_incomplete"),
        (_census(DOCUMENT, pid=FOREIGN_PID), "window_attribution_mismatch"),
        (
            _census(replace(DOCUMENT, owner_pid=FOREIGN_PID), LOG),
            "window_attribution_mismatch",
        ),
        (
            _census(
                replace(DOCUMENT, enabled=False),
                _window(5555, "Cisco Packet Tracer", owner=4242),
                LOG,
            ),
            "modal_or_owned_window_visible",
        ),
        (_census(replace(DOCUMENT, enabled=False), LOG), "document_window_disabled"),
        (
            _census(DOCUMENT, _window(4545, "Cisco Packet Tracer"), LOG),
            "document_window_ambiguous",
        ),
        (_census(LOG), "document_window_absent"),
        (
            _census(_window(4242, "Cisco Packet Tracer - C:\\coursework.pkt"), LOG),
            "document_window_names_file_or_nothing",
        ),
        (_census(_window(4242, ""), LOG), "document_window_names_file_or_nothing"),
        (
            _census(DOCUMENT, LOG, _window(4646, EXTENSION_LOG_WINDOW_TITLE)),
            "extension_window_ambiguous",
        ),
    ],
)
def test_any_doubt_about_the_windows_selects_nothing(census, finding):
    """Incomplete, foreign, modal, changed or ambiguous: no close target."""
    selected, found = select_document_window(PID, census)

    assert selected is None
    assert finding in found


def test_a_foreign_process_with_identical_titles_is_never_selected():
    """Titles equal to the owned ones prove nothing about another PID."""
    foreign = _census(
        _window(9001, "Cisco Packet Tracer", pid=FOREIGN_PID),
        _window(9002, EXTENSION_LOG_WINDOW_TITLE, pid=FOREIGN_PID),
        pid=FOREIGN_PID,
    )

    assert select_document_window(PID, foreign) == (
        None,
        ("window_attribution_mismatch",),
    )
    assert select_document_window(PID, _census(LOG))[1] == ("document_window_absent",)


@pytest.mark.parametrize(
    ("after", "finding"),
    [
        (_census(LOG, DOCUMENT), None),
        (_census(LOG), "document_window_closed_process_alive"),
        (_census(_window(7777, "Cisco Packet Tracer"), LOG), "document_window_changed"),
        (
            _census(_window(4242, "Cisco Packet Tracer - C:\\saved.pkt"), LOG),
            "document_window_names_file_or_nothing",
        ),
        (
            _census(
                replace(DOCUMENT, enabled=False), _window(5555, "Save?", owner=4242)
            ),
            "modal_or_owned_window_visible",
        ),
        (_census(DOCUMENT, complete=False), "window_census_incomplete"),
    ],
)
def test_a_force_needs_the_same_document_window_and_nothing_modal(after, finding):
    """After a failed close only the unchanged target may be forced."""
    found = force_window_findings(PID, DOCUMENT, after)

    assert (found == ()) if finding is None else (finding in found)


def _launch() -> dict[str, object]:
    return {
        "pid": PID,
        "process_path": PATH,
        "process_incarnation": INCARNATION,
        "observed_command_line": COMMAND_LINE,
        "observed_main_window_title": "Cisco Packet Tracer",
    }


def _target(window: OwnedWindow = DOCUMENT) -> dict[str, object]:
    return {
        "handle": window.handle,
        "owner_pid": window.owner_pid,
        "class_name": window.class_name,
        "title": window.title,
        "identity_digest": window.identity_digest,
    }


@pytest.mark.parametrize(
    "target",
    [
        None,
        _target(LOG),
        _target(_window(4242, "Cisco Packet Tracer - C:\\x.pkt")),
        {**_target(), "owner_pid": FOREIGN_PID},
        {**_target(), "handle": True},
    ],
    ids=["missing", "log-window", "named-file", "foreign", "bool-handle"],
)
def test_a_targeted_close_must_name_one_owned_unnamed_document(target):
    """A WM_CLOSE record without its proven target is not a graceful request."""
    close = {
        **_launch(),
        "method": "WM_CLOSE",
        "close_target": target,
        "requested": True,
        "actual_exit_observed": True,
    }

    assert "graceful_close_identity_unproven" in exit_evidence_findings(
        _launch(), close, process_count=0
    )
    assert (
        exit_evidence_findings(
            _launch(), {**close, "close_target": _target()}, process_count=0
        )
        == ()
    )


# -- the native helper's boundary -----------------------------------------------------


class _Runner:
    """Capture helper invocations and answer with a fixed stdout."""

    def __init__(self, stdout: str = "", error: Exception | None = None):
        self.stdout = stdout
        self.error = error
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        assert kwargs["timeout"] > 0
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(argv, 0, stdout=self.stdout, stderr="")

    def script(self) -> str:
        argv = self.calls[-1]
        assert argv[:4] == [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
        ]
        return base64.b64decode(argv[4]).decode("utf-16-le")


def _row(window: OwnedWindow) -> dict[str, object]:
    return {
        "handle": window.handle,
        "owner_pid": window.owner_pid,
        "class_name": window.class_name,
        "title": window.title,
        "visible": window.visible,
        "enabled": window.enabled,
        "owner_handle": window.owner_handle,
        "identity_digest": window.identity_digest,
    }


def test_the_census_command_names_only_the_validated_pid():
    """No external text reaches the helper; its answer becomes typed windows."""
    runner = _Runner(
        json.dumps({"complete": True, "windows": [_row(DOCUMENT), _row(LOG)]})
    )
    control = PowerShellOwnedProcessControl(run_command=runner)

    census = control.windows(PID)

    assert census == _census(DOCUMENT, LOG)
    assert runner.script().splitlines()[-1] == (
        f"[PtMcpOwnedWindows]::Census({PID}, {WINDOW_CENSUS_LIMIT})"
    )
    with pytest.raises(ValueError):
        control.windows(True)


def test_the_close_command_names_only_validated_integers_and_a_digest():
    """The handle and digest are checked before any helper runs."""
    runner = _Runner(json.dumps({"sent": True, "refusal": ""}))
    control = PowerShellOwnedProcessControl(run_command=runner)

    result = control.close_window(PID, DOCUMENT.handle, DOCUMENT.identity_digest)

    assert result == WindowCloseResult(PID, DOCUMENT.handle, sent=True)
    assert runner.script().splitlines()[-1] == (
        f"[PtMcpOwnedWindows]::Close({PID}, {DOCUMENT.handle}, "
        f"'{DOCUMENT.identity_digest}')"
    )
    for handle, digest in [
        (True, DOCUMENT.identity_digest),
        (0, DOCUMENT.identity_digest),
        (DOCUMENT.handle, "Cisco Packet Tracer"),
        (DOCUMENT.handle, "'); Stop-Process -Id 1; ('" + "0" * 40),
    ]:
        with pytest.raises(ValueError):
            control.close_window(PID, handle, digest)
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    ("stdout", "error"),
    [
        ("not json", "window_census_malformed"),
        (json.dumps({"complete": True}), "window_census_malformed"),
        (
            json.dumps({"complete": True, "windows": [_row(DOCUMENT), _row(DOCUMENT)]}),
            "window_census_malformed",
        ),
        (
            json.dumps(
                {"complete": True, "windows": [{**_row(DOCUMENT), "title": "changed"}]}
            ),
            "window_census_malformed",
        ),
        (
            json.dumps(
                {"complete": True, "windows": [{**_row(DOCUMENT), "visible": 1}]}
            ),
            "window_census_malformed",
        ),
        (
            json.dumps(
                {
                    "complete": True,
                    "windows": [_row(replace(LOG, owner_pid=FOREIGN_PID))],
                }
            ),
            "window_attribution_mismatch",
        ),
        (
            json.dumps(
                {
                    "complete": True,
                    "windows": [
                        _row(_window(index + 1, f"w{index}"))
                        for index in range(WINDOW_CENSUS_LIMIT + 1)
                    ],
                }
            ),
            "window_census_malformed",
        ),
    ],
    ids=[
        "not-json",
        "no-windows",
        "duplicate-handle",
        "altered-title",
        "non-bool-flag",
        "foreign-row",
        "over-limit",
    ],
)
def test_a_doubtful_census_answer_is_an_error_not_an_empty_set(stdout, error):
    """Malformed, foreign-attributed or altered rows never become windows."""
    census = PowerShellOwnedProcessControl(run_command=_Runner(stdout)).windows(PID)

    assert census.error == error
    assert census.windows == ()


def test_a_census_or_close_that_times_out_is_unobservable():
    """A timed-out helper is an error; its close outcome is not known."""
    timeout = subprocess.TimeoutExpired("powershell.exe", 15)
    control = PowerShellOwnedProcessControl(run_command=_Runner(error=timeout))

    assert control.windows(PID).error == "window_census_unobservable:TimeoutExpired"
    result = control.close_window(PID, DOCUMENT.handle, DOCUMENT.identity_digest)
    assert result.sent is False
    assert result.error == "window_close_unobservable:TimeoutExpired"


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "nope",
        json.dumps({"sent": True, "refusal": "window_absent"}),
        json.dumps({"sent": False, "refusal": ""}),
    ],
    ids=["empty", "not-json", "sent-with-refusal", "unsent-without-refusal"],
)
def test_a_doubtful_close_answer_is_not_a_sent_close(stdout):
    """Only an explicit, consistent answer reports what the helper did."""
    result = PowerShellOwnedProcessControl(run_command=_Runner(stdout)).close_window(
        PID, DOCUMENT.handle, DOCUMENT.identity_digest
    )

    assert result.sent is False
    assert result.error == "window_close_malformed"


# -- `--retire` through the CLI -------------------------------------------------------


class _FakeOS:
    """The OS as retirement sees it: the owned process, windows and effects."""

    def __init__(self):
        self.present = True
        self.incarnation = INCARNATION
        self.main_title = "Cisco Packet Tracer"
        self.windows_of: dict[int, list[OwnedWindow]] = {PID: [DOCUMENT, LOG]}
        self.census_complete = True
        self.census_error = ""
        self.on_close = "exit"
        self.close_refusal = ""
        self.close_error = ""
        self.calls: list[str] = []
        self.posted: list[int] = []

    def __call__(self):
        return self

    def observe(self, pid):
        self.calls.append("observe")
        if not self.present:
            return OwnedProcessObservation(pid, present=False)
        return OwnedProcessObservation(
            pid,
            present=True,
            process_path=PATH,
            process_incarnation=self.incarnation,
            command_line=COMMAND_LINE,
            main_window_title=self.main_title,
        )

    def windows(self, pid):
        self.calls.append("windows")
        if self.census_error:
            return OwnedWindowCensus(pid, error=self.census_error)
        windows = tuple(self.windows_of.get(pid, ())) if self.present else ()
        return OwnedWindowCensus(pid, windows=windows, complete=self.census_complete)

    def close_window(self, pid, handle, digest):
        # The helper's own revalidation: the handle must still be that window.
        self.calls.append("close_helper")
        if self.close_error:
            self.posted.append(handle)
            return WindowCloseResult(pid, handle, error=self.close_error)
        if self.close_refusal:
            return WindowCloseResult(pid, handle, refusal=self.close_refusal)
        owned = {window.handle: window for window in self.windows_of.get(pid, ())}
        if handle not in owned or owned[handle].identity_digest != digest:
            return WindowCloseResult(pid, handle, refusal="window_identity_changed")
        self.posted.append(handle)
        current = self.windows_of[pid]
        if self.on_close == "exit":
            self.present = False
        elif self.on_close == "modal":
            self.windows_of[pid] = [
                replace(window, enabled=False) if window.handle == handle else window
                for window in current
            ] + [_window(5555, "Cisco Packet Tracer", owner=handle)]
        elif self.on_close == "vanish":
            self.windows_of[pid] = [w for w in current if w.handle != handle]
        return WindowCloseResult(pid, handle, sent=True)

    def terminate(self, pid):
        self.calls.append("terminate")
        self.present = False
        return True

    def census(self):
        return 0 if not self.present else 1


def _checkpoint() -> RepositoryIdentity:
    return RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head=HEAD,
        tree=TREE,
        clean=True,
        upstream_head="c" * 40,
    )


def _process() -> DiagnosticLifecycleObservation:
    return DiagnosticLifecycleObservation(
        process_id=PID,
        process_path=PATH,
        process_incarnation=INCARNATION,
        product_version="9.0.1.0858",
    )


def _run(cli, argv, env, capsys):
    code = cli.main(argv, environ=env)
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture
def fastloop_cli(tmp_path: Path, monkeypatch):
    """Bind a test charter to the experimental campaign; forbid other reads."""
    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "work-order.md"
    charter.write_text("experimental work order", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "FASTLOOP_CHARTER_SHA256",
        hashlib.sha256(charter.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(cli, "repository_identity", lambda _root: _checkpoint())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("no process may be read by this refusal")

    monkeypatch.setattr(cli, "phase_preflight", forbidden)
    return cli, charter, {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}


@pytest.fixture
def launched(fastloop_cli, tmp_path: Path, capsys, monkeypatch):
    """Record one experimental launch whose capture matches the OS reading."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import PhasePreflight

    cli, charter, env = fastloop_cli
    monkeypatch.setattr(
        cli,
        "phase_preflight",
        lambda *_args, **_kwargs: PhasePreflight(
            _checkpoint(), None, _process(), campaign=FASTLOOP_CAMPAIGN
        ),
    )
    monkeypatch.setattr(cli, "RETIREMENT_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(cli, "RETIREMENT_EXIT_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(cli, "_retirement_sleep", lambda _seconds: time.sleep(0.002))
    system = _FakeOS()
    # At launch the extension log window was the one .NET called "main".
    system.main_title = EXTENSION_LOG_WINDOW_TITLE
    system.windows_of[PID] = [LOG, DOCUMENT]
    monkeypatch.setattr(cli, "_PROCESS_CONTROL", system)
    capture = tmp_path / "launch.json"
    capture.write_text(
        json.dumps(
            {
                "pid": PID,
                "process_path": PATH,
                "process_incarnation": INCARNATION,
                "main_window_title": EXTENSION_LOG_WINDOW_TITLE,
                "command_line": COMMAND_LINE,
                "created_by_campaign": True,
                "workspace_kind": "disposable_declared",
                "launch_method": "Start-Process",
            }
        ),
        encoding="utf-8",
    )
    base = ["--campaign", "fastloop", "--attempt", ATTEMPT, "--charter", str(charter)]
    code, owned = _run(
        cli, ["--record-launch", *base, "--launch-evidence", str(capture)], env, capsys
    )
    assert code == 0, owned
    assert owned["blank_document_proven"] is True
    system.calls.clear()
    return cli, env, base, system


def _store(tmp_path: Path) -> ServerPtCommissioningStore:
    return ServerPtCommissioningStore(tmp_path, FASTLOOP_CAMPAIGN.campaign_id)


def _attempts(tmp_path: Path) -> list[dict[str, object]]:
    directory = tmp_path / "data" / "commissioning" / FASTLOOP_CAMPAIGN.campaign_id
    return [
        json.loads(path.read_bytes())
        for path in sorted((directory / ATTEMPT).glob("retirement-attempt-*.json"))
    ]


def test_the_launch_keeps_its_window_census_as_auxiliary_evidence(
    launched, tmp_path: Path
):
    """Both windows are retained with handle, owner, class, title and flags."""
    record = _store(tmp_path).load_process_launch(ATTEMPT)

    census = record["observed_window_census"]
    assert census["complete"] is True and census["error"] == ""
    assert [item["title"] for item in census["windows"]] == [
        EXTENSION_LOG_WINDOW_TITLE,
        "Cisco Packet Tracer",
    ]
    assert {"handle", "owner_pid", "class_name", "visible", "owner_handle"} <= set(
        census["windows"][0]
    )


@pytest.mark.parametrize(
    ("order", "main_title"),
    [
        ([DOCUMENT, LOG], "Cisco Packet Tracer"),
        ([LOG, DOCUMENT], EXTENSION_LOG_WINDOW_TITLE),
        ([DOCUMENT], "Cisco Packet Tracer"),
        ([HIDDEN, DOCUMENT, LOG], "PacketTracer"),
    ],
    ids=["document-first", "log-focused", "log-closed", "startup-title"],
)
def test_changing_focus_order_and_log_window_still_retire_gracefully(
    launched, capsys, tmp_path: Path, order, main_title
):
    """Episode 1's refusal is gone: one targeted close, no force."""
    cli, env, base, system = launched
    system.windows_of[PID] = list(order)
    system.main_title = main_title

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    assert retired["outcome"] == "exited_before_setup"
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls
    record = _store(tmp_path).load_process_exit(ATTEMPT)
    assert record["method"] == "WM_CLOSE"
    assert record["close_target"]["handle"] == DOCUMENT.handle
    assert "forced_termination" not in record
    assert _store(tmp_path).verify_index() == ()


def _refused_without_effect(cli, env, base, system, capsys, tmp_path, finding):
    code, refused = _run(cli, ["--retire", *base], env, capsys)
    assert code == 2, refused
    assert system.posted == []
    assert "terminate" not in system.calls
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()
    attempts = _attempts(tmp_path)
    assert attempts and any(finding in str(item.get("refusal")) for item in attempts)
    return refused


def test_a_foreign_process_with_identical_titles_is_not_closed(
    launched, capsys, tmp_path: Path
):
    """The owned PID shows only its log; a foreign PID's document is not ours."""
    cli, env, base, system = launched
    system.windows_of = {
        PID: [LOG],
        FOREIGN_PID: [
            _window(9001, "Cisco Packet Tracer", pid=FOREIGN_PID),
            _window(9002, EXTENSION_LOG_WINDOW_TITLE, pid=FOREIGN_PID),
        ],
    }

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "document_window_absent"
    )


def test_a_row_attributed_to_another_process_sends_nothing(
    launched, capsys, tmp_path: Path
):
    """A census that mixes in another PID's window is not a census of ours."""
    cli, env, base, system = launched
    system.windows_of[PID] = [
        _window(9001, "Cisco Packet Tracer", pid=FOREIGN_PID),
        LOG,
    ]

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "window_attribution_mismatch"
    )


def test_a_reused_pid_is_neither_enumerated_nor_closed(launched, capsys, tmp_path):
    """Another creation time under the same PID stops before the census."""
    cli, env, base, system = launched
    system.incarnation = "2026-09-24T09:00:00-05:00"

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "process_identity_changed"
    )
    assert "windows" not in system.calls


def test_a_handle_reused_before_the_close_is_refused_by_the_helper(
    launched, capsys, tmp_path: Path
):
    """The helper's same-call recheck refuses; nothing is posted or forced."""
    cli, env, base, system = launched
    system.close_refusal = "window_owner_changed"

    _refused_without_effect(
        cli, env, base, system, capsys, tmp_path, "close_not_sent:window_owner_changed"
    )
    assert system.present is True


@pytest.mark.parametrize(
    ("complete", "error", "finding"),
    [
        (False, "", "window_census_incomplete"),
        (
            True,
            "window_census_unobservable:TimeoutExpired",
            "window_census_unobservable",
        ),
    ],
)
def test_an_incomplete_enumeration_withholds_every_effect(
    launched, capsys, tmp_path: Path, complete, error, finding
):
    """No close is sent on a census that did not finish or answer."""
    cli, env, base, system = launched
    system.census_complete = complete
    system.census_error = error

    _refused_without_effect(cli, env, base, system, capsys, tmp_path, finding)


@pytest.mark.parametrize(
    ("windows", "finding"),
    [
        (
            [_window(4242, "Cisco Packet Tracer - C:\\coursework.pkt"), LOG],
            "document_window_names_file_or_nothing",
        ),
        (
            [DOCUMENT, _window(4545, "Cisco Packet Tracer"), LOG],
            "document_window_ambiguous",
        ),
        (
            [replace(DOCUMENT, enabled=False), _window(5555, "Save?", owner=4242)],
            "modal_or_owned_window_visible",
        ),
    ],
    ids=["changed-document", "ambiguous-document", "modal-before-close"],
)
def test_a_changed_ambiguous_or_modal_document_withholds_every_effect(
    launched, capsys, tmp_path: Path, windows, finding
):
    """Unknown document state is not permission to close or kill."""
    cli, env, base, system = launched
    system.windows_of[PID] = windows

    refused = _refused_without_effect(cli, env, base, system, capsys, tmp_path, finding)
    assert refused["window_census_before"]["windows"]


def test_a_modal_prompt_after_the_close_is_observed_not_answered(
    launched, capsys, tmp_path: Path
):
    """One close was posted; the prompt is recorded, never answered or forced."""
    cli, env, base, system = launched
    system.on_close = "modal"

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls
    assert "modal_or_owned_window_visible" in refused["refusal"]
    after = refused["window_census_after"]["windows"]
    assert any(item["owner_handle"] == DOCUMENT.handle for item in after)
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()


def test_a_close_that_does_not_exit_is_forced_only_on_the_same_document(
    launched, capsys, tmp_path: Path
):
    """Bounded close, identical process and window, exact PID, observed exit."""
    cli, env, base, system = launched
    system.on_close = "stay"

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    assert retired["outcome"] == "exited_before_setup_forced"
    assert system.posted == [DOCUMENT.handle]
    assert system.calls.index("close_helper") < system.calls.index("terminate")
    store = _store(tmp_path)
    forced = store.load_process_exit(ATTEMPT)["forced_termination"]
    assert forced["rechecked_document_window"]["handle"] == DOCUMENT.handle
    assert forced["modal_windows_visible"] is False
    assert forced["ownership_basis"] == "blank_launch_without_phase"
    assert store.verify_index() == ()


def test_a_document_that_closes_while_the_process_stays_is_not_forced(
    launched, capsys, tmp_path: Path
):
    """The fact is recorded; no kill follows an unexplained live process."""
    cli, env, base, system = launched
    system.on_close = "vanish"

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls
    assert "document_window_closed_process_alive" in refused["refusal"]


def test_an_already_absent_process_is_neither_closed_nor_killed(
    launched, capsys, tmp_path: Path
):
    """Absence before any request is recorded; nothing is sent."""
    cli, env, base, system = launched
    system.present = False

    _refused_without_effect(cli, env, base, system, capsys, tmp_path, "process_absent")
    assert system.calls == ["observe"]


@pytest.mark.parametrize("exits", [False, True])
def test_an_unknown_close_outcome_never_authorizes_a_force(
    launched, capsys, tmp_path: Path, exits
):
    """A helper that did not answer may have posted; nothing is forced."""
    cli, env, base, system = launched
    system.close_error = "window_close_unobservable:TimeoutExpired"
    system.present = True
    if exits:
        system.on_close = "exit"
        original = system.close_window

        def close_then_exit(pid, handle, digest):
            result = original(pid, handle, digest)
            system.present = False
            return result

        system.close_window = close_then_exit

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert "terminate" not in system.calls
    assert refused["requested"] is False
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()
    if not exits:
        assert "close_outcome_unknown" in refused["refusal"]


def test_a_launch_capture_that_disagrees_with_the_os_is_refused(
    fastloop_cli, tmp_path: Path, capsys, monkeypatch
):
    """The retirement evidence is observed at launch, never taken as claimed."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import PhasePreflight

    cli, charter, env = fastloop_cli
    monkeypatch.setattr(
        cli,
        "phase_preflight",
        lambda *_args, **_kwargs: PhasePreflight(
            _checkpoint(), None, _process(), campaign=FASTLOOP_CAMPAIGN
        ),
    )
    system = _FakeOS()
    system.main_title = "Cisco Packet Tracer - C:\\coursework.pkt"
    monkeypatch.setattr(cli, "_PROCESS_CONTROL", system)
    capture = tmp_path / "launch.json"
    capture.write_text(
        json.dumps(
            {
                "pid": PID,
                "process_path": PATH,
                "process_incarnation": INCARNATION,
                "main_window_title": "Cisco Packet Tracer",
                "command_line": COMMAND_LINE,
                "created_by_campaign": True,
                "workspace_kind": "disposable_declared",
                "launch_method": "Start-Process",
            }
        ),
        encoding="utf-8",
    )
    base = ["--campaign", "fastloop", "--attempt", ATTEMPT, "--charter", str(charter)]

    code, refused = _run(
        cli, ["--record-launch", *base, "--launch-evidence", str(capture)], env, capsys
    )

    assert code == 2
    assert refused["reason"] == "launch_evidence:ValueError"


def test_unestablished_workspace_ownership_prevents_any_retirement_effect(
    launched, capsys, tmp_path: Path
):
    """A setup grant without its empty baseline: no census, close or force."""
    cli, env, base, system = launched
    bundle = prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT)
    store = _store(tmp_path)
    store.save_phase_grant(
        ATTEMPT,
        derive_server_pt_phase_grant(
            "setup",
            ATTEMPT,
            _checkpoint(),
            _process(),
            None,
            bundle_sha256="c" * 64,
            prequalification_sha256="d" * 64,
            bundle=bundle,
            campaign=FASTLOOP_CAMPAIGN,
        ),
    )
    store.refresh_index()

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2
    assert refused["reason"].startswith("retirement_unestablished:")
    assert system.calls == []


def test_record_exit_never_admits_a_forced_capture(
    launched, capsys, tmp_path: Path, monkeypatch
):
    """A capture cannot carry a force; only the observed retirement can."""
    cli, env, base, _system = launched

    class _Census:
        def __init__(self, **_kwargs):
            pass

        def read(self):
            return type("Observed", (), {"error": "", "processes": ()})()

    monkeypatch.setattr(cli, "PowerShellPacketTracerProcessReader", _Census)
    close = tmp_path / "close.json"
    close.write_text(
        json.dumps(
            {
                **_launch(),
                "method": "WM_CLOSE",
                "close_target": _target(),
                "requested": True,
                "actual_exit_observed": True,
                "graceful_wait_seconds": 30.0,
                "forced_termination": {"method": "Stop-Process", "pid": PID},
            }
        ),
        encoding="utf-8",
    )

    code, refused = _run(
        cli, ["--record-exit", *base, "--close-evidence", str(close)], env, capsys
    )

    assert code == 2
    assert refused["reason"] == "process_exit:ValueError"


# -- the historical exit import --------------------------------------------------------

LAUNCHED_AT = "2026-09-24T03:43:18.7893781Z"
CLEANUP_AT = "2026-09-24T03:48:43.413036+00:00"
REQUESTED_AT = "2026-09-24T03:49:53.0758496Z"
PRESENCE_AT = "2026-09-24T03:50:13.930Z"
ABSENCE_AT = "2026-09-24T03:50:25.443Z"
CENSUS_AT = "2026-09-24T03:50:40.2114457Z"
REFUSAL = '{"outcome": "refused", "reasons": ["process_document_title_changed"]}'


def _transcript_lines() -> list[bytes]:
    """Return a small session transcript; 1-based lines 3-10 hold the exit."""

    def line(value: object) -> bytes:
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    def use(command: str) -> bytes:
        return line(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "input": {"command": command}}]
                },
            }
        )

    def answer(text: str, stamp: str) -> bytes:
        return line(
            {
                "type": "user",
                "timestamp": stamp,
                "message": {"content": [{"type": "tool_result", "content": text}]},
            }
        )

    return [
        line({"type": "note", "text": "earlier work"}),
        line({"type": "note", "text": "setup"}),
        use("python -m server_pt_commissioning --retire ..."),
        answer(f"Exit code 2\n{REFUSAL}\n2", "2026-09-24T03:48:55.333Z"),
        use("$p.CloseMainWindow(); poll 40 x 0.5 s"),
        answer("requested=True\nexited=False", PRESENCE_AT),
        use("if (Get-Process -Id 123) { windows } else { 'process 123 exited' }"),
        answer("process 123 exited", ABSENCE_AT),
        use("census; mailbox; write close-capture.json"),
        answer(
            "packet_tracer_processes=0\nmailbox_pending=0", "2026-09-24T03:50:40.506Z"
        ),
        line({"type": "note", "text": "later"}),
    ]


def _capture() -> dict[str, object]:
    return {
        "pid": PID,
        "process_path": PATH,
        "process_incarnation": INCARNATION,
        "method": "CloseMainWindow",
        "requested": True,
        "requested_at_utc": REQUESTED_AT,
        "actual_exit_observed": True,
        "observed_at_utc": CENSUS_AT,
        "process_count": 0,
        "completion_method": "graceful_close_request_only",
        "note": "lead narrative",
    }


def _provenance() -> dict[str, str]:
    return {
        "pid": "transcribed",
        "process_path": "transcribed",
        "process_incarnation": "transcribed",
        "method": "transcribed",
        "requested": "transcribed",
        "requested_at_utc": "transcribed",
        "actual_exit_observed": "observed",
        "observed_at_utc": "observed",
        "process_count": "observed",
        "completion_method": "lead_assertion",
        "note": "lead_assertion",
    }


class _ImportLab:
    """A temporary FASTLOOP archive with one restored attempt and its originals."""

    def __init__(self, root: Path):
        self.root = root
        self.lab = root / "lab"
        self.lab.mkdir()
        self.transcript = self.lab / "session.jsonl"
        self.transcript.write_bytes(b"\n".join(_transcript_lines()) + b"\n")
        self.files = {
            "close_capture": self.lab / "close-capture.json",
            "close_request_output": self.lab / "close-request.txt",
            "prelaunch_census": self.lab / "prelaunch-census.json",
            "transcript_excerpt": self.lab / "excerpt.jsonl",
            "event_log_query": self.lab / "event-log.txt",
        }
        self.write_capture(_capture())
        self.files["close_request_output"].write_bytes(
            f"requested=True requested_at_utc={REQUESTED_AT} "
            "exited_within_20s=False\r\n".encode("ascii")
        )
        self.files["prelaunch_census"].write_bytes(
            json.dumps(
                {
                    "attempt_id": ATTEMPT,
                    "source_sha": HEAD,
                    "observed_at_utc": "2026-09-24T03:43:18.7561037Z",
                    "process_count": 0,
                }
            ).encode()
        )
        self.lines = list(range(3, 11))
        self.write_excerpt()
        self.files["event_log_query"].write_bytes(b"matching_events=0\r\n")
        self.manifest = {
            "kind": "historical_exit_import",
            "attempt_id": ATTEMPT,
            "episode": 1,
            "artifacts": {
                role: {"path": str(path), "origin": "lead_command_output_file"}
                for role, path in self.files.items()
            },
            "capture_field_provenance": _provenance(),
            "time_bounds": {
                "close_requested_at_utc": {
                    "value": REQUESTED_AT,
                    "clock": "os",
                    "artifact": "close_request_output",
                },
                "presence_last_reported_by_utc": {
                    "value": PRESENCE_AT,
                    "clock": "session_transcript",
                    "artifact": "transcript_excerpt",
                    "line": 6,
                },
                "absence_first_reported_by_utc": {
                    "value": ABSENCE_AT,
                    "clock": "session_transcript",
                    "artifact": "transcript_excerpt",
                    "line": 8,
                },
                "zero_census_observed_at_utc": {
                    "value": CENSUS_AT,
                    "clock": "os",
                    "artifact": "close_capture",
                },
            },
            "retire_refusal": {"output": REFUSAL, "line": 4, "source_sha": HEAD},
            "retained_command_range": {"first_line": 5, "last_line": 10},
            "lead_report": "The lead requested one graceful close.",
        }
        self.manifest["artifacts"]["transcript_excerpt"].update(
            {"source_path": str(self.transcript), "source_lines": self.lines}
        )

    def write_capture(self, capture: dict[str, object]) -> None:
        self.files["close_capture"].write_bytes(
            b"\xef\xbb\xbf"
            + json.dumps(capture, separators=(",", ":")).encode()
            + b"\r\n"
        )

    def write_excerpt(self) -> None:
        source = self.transcript.read_bytes().split(b"\n")
        self.files["transcript_excerpt"].write_bytes(
            b"".join(source[number - 1] + b"\n" for number in self.lines)
        )

    def launch(self) -> dict[str, object]:
        return {
            "pid": PID,
            "process_path": PATH,
            "process_incarnation": INCARNATION,
            "launched_at_utc": LAUNCHED_AT,
            "prelaunch_census_path": str(self.files["prelaunch_census"]),
            "source_sha": HEAD,
            "source_tree": TREE,
            "campaign_id": FASTLOOP_CAMPAIGN.campaign_id,
            "execution_purpose": "experimental",
            "observed_command_line": COMMAND_LINE,
            "observed_main_window_title": EXTENSION_LOG_WINDOW_TITLE,
        }

    def artifacts(self) -> dict[str, bytes]:
        return {role: path.read_bytes() for role, path in self.files.items()}

    def manifest_file(self) -> Path:
        path = self.lab / "manifest.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return path


def _authority(addendum: bytes) -> HistoricalExitImportAuthority:
    return HistoricalExitImportAuthority(
        addendum_sha256=hashlib.sha256(addendum).hexdigest(),
        campaign_id=FASTLOOP_CAMPAIGN.campaign_id,
        attempt_id=ATTEMPT,
        episode=1,
        episode_source_sha=HEAD,
        episode_source_tree=TREE,
    )


def _findings(lab: _ImportLab, **changes) -> tuple[str, ...]:
    return historical_exit_import_findings(
        authority=_authority(b"addendum"),
        manifest=changes.get("manifest", lab.manifest),
        launch=changes.get("launch", lab.launch()),
        cleanup_recorded_at_utc=changes.get("cleanup", CLEANUP_AT),
        artifacts=changes.get("artifacts", lab.artifacts()),
        archive_at_utc=changes.get("archive", "2026-09-24T12:00:00+00:00"),
    )


def test_the_retained_originals_support_the_import(tmp_path: Path):
    """The positive control of every rule below."""
    assert _findings(_ImportLab(tmp_path)) == ()


def _mutate(lab: _ImportLab, path: str, value: object) -> dict[str, object]:
    manifest = json.loads(json.dumps(lab.manifest))
    target = manifest
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    return manifest


@pytest.mark.parametrize(
    ("path", "value", "finding"),
    [
        ("attempt_id", OTHER, "import_manifest_not_this_authority"),
        ("episode", 2, "import_manifest_not_this_authority"),
        (
            "capture_field_provenance.observed_at_utc",
            "lead_assertion",
            "exit_claim_not_supported_by_observation",
        ),
        (
            "capture_field_provenance.process_count",
            "transcribed",
            "exit_claim_not_supported_by_observation",
        ),
        (
            "capture_field_provenance.pid",
            "lead_assertion",
            "exit_claim_not_supported_by_observation",
        ),
        (
            "capture_field_provenance.note",
            "observed?",
            "capture_field_provenance_incomplete",
        ),
        (
            "time_bounds.presence_last_reported_by_utc.value",
            ABSENCE_AT,
            "time_bounds_out_of_order",
        ),
        (
            "time_bounds.close_requested_at_utc.value",
            "2026-09-24T03:49:54Z",
            "time_bounds_disagree_with_capture",
        ),
        (
            "time_bounds.absence_first_reported_by_utc.line",
            99,
            "time_bound_citation_invalid",
        ),
        (
            "time_bounds.zero_census_observed_at_utc.clock",
            "session_transcript",
            "time_bound_citation_invalid",
        ),
        ("retire_refusal.line", 6, "retire_refusal_not_retained"),
        ("retire_refusal.source_sha", "d" * 40, "retire_refusal_not_retained"),
        ("retained_command_range.last_line", 12, "retained_command_range_incomplete"),
        (
            "artifacts.prelaunch_census.path",
            "C:\\elsewhere.json",
            "prelaunch_census_does_not_bind_the_launch",
        ),
        (
            "artifacts.transcript_excerpt.source_lines",
            [3, 4],
            "transcript_excerpt_lines_malformed",
        ),
    ],
)
def test_each_manifest_claim_must_be_supported(tmp_path: Path, path, value, finding):
    """A citation, order, origin or binding that does not hold is refused."""
    lab = _ImportLab(tmp_path)

    assert finding in _findings(lab, manifest=_mutate(lab, path, value))


@pytest.mark.parametrize(
    ("change", "finding"),
    [
        ({"pid": 124}, "close_capture_does_not_bind_the_launch"),
        ({"process_count": 1}, "close_capture_does_not_bind_the_launch"),
        ({"actual_exit_observed": False}, "close_capture_does_not_bind_the_launch"),
        ({"process_incarnation": "other"}, "close_capture_does_not_bind_the_launch"),
        (
            {"forced_termination": {"method": "Stop-Process"}},
            "close_capture_does_not_bind_the_launch",
        ),
        (
            {"requested_at_utc": "2026-09-24T03:49:54Z"},
            "close_request_output_disagrees",
        ),
    ],
)
def test_a_capture_that_does_not_bind_the_launch_is_refused(
    tmp_path: Path, change, finding
):
    """The capture passes the existing exit rules against the launch, or not."""
    lab = _ImportLab(tmp_path)
    capture = {**_capture(), **change}
    lab.write_capture(capture)
    manifest = json.loads(json.dumps(lab.manifest))
    manifest["capture_field_provenance"] = {
        key: _provenance().get(key, "lead_assertion") for key in capture
    }

    assert finding in _findings(lab, manifest=manifest)


def test_a_retained_range_that_names_a_termination_is_refused(tmp_path: Path):
    """The claim that the lead issued no termination must hold in the record."""
    lab = _ImportLab(tmp_path)
    lines = _transcript_lines()
    lines[6] = lines[6].replace(b"windows", b"Stop-Process -Id 123 -Force")
    lab.transcript.write_bytes(b"\n".join(lines) + b"\n")
    lab.write_excerpt()

    assert "retained_record_names_a_termination" in _findings(lab)


def test_the_launch_must_be_the_authorized_episode_source(tmp_path: Path):
    """An episode source other than the addendum's is not importable."""
    lab = _ImportLab(tmp_path)

    found = _findings(lab, launch={**lab.launch(), "source_tree": "f" * 40})

    assert "launch_not_the_authorized_episode_source" in found


def test_the_cleanup_and_archive_bound_the_request(tmp_path: Path):
    """A request before the restored cleanup, or an archive before it, is refused."""
    lab = _ImportLab(tmp_path)

    assert "time_bounds_out_of_order" in _findings(
        lab, cleanup="2026-09-24T03:50:00+00:00"
    )
    assert "time_bounds_out_of_order" in _findings(
        lab, archive="2026-09-24T03:50:30+00:00"
    )


class _NoPacketTracer:
    processes: tuple = ()
    error = ""

    def __init__(self, **_kwargs):
        pass

    def read(self):
        return self


@pytest.fixture
def import_lab(fastloop_cli, tmp_path: Path, monkeypatch):
    """One restored attempt, its originals, and every non-local read faked."""
    cli, charter, env = fastloop_cli
    lab = _ImportLab(tmp_path)
    addendum = tmp_path / "addendum-02.md"
    addendum.write_bytes(b"# Addendum 02\r\n")
    monkeypatch.setattr(
        cli, "_EXIT_IMPORT_AUTHORITY", _authority(addendum.read_bytes())
    )
    recorder = replace(_checkpoint(), head="d" * 40, tree="e" * 40)
    monkeypatch.setattr(cli, "repository_identity", lambda _root: recorder)
    monkeypatch.setattr(
        cli,
        "_SOURCE_ANCESTRY",
        lambda _root, ancestor, descendant: SourceAncestry(
            ancestor, descendant, TREE, is_ancestor=True
        ),
    )
    monkeypatch.setattr(cli, "PowerShellPacketTracerProcessReader", _NoPacketTracer)
    mailbox = tmp_path / "mailbox"
    mailbox.mkdir()
    monkeypatch.setattr(cli, "_MAILBOX_DIR", lambda: mailbox)

    def no_effect():
        raise AssertionError("an import never observes, closes or terminates")

    monkeypatch.setattr(cli, "_PROCESS_CONTROL", no_effect)
    store = _store(tmp_path)
    store.save_process_launch(ATTEMPT, lab.launch())
    status = {"attempt_id": ATTEMPT, "outcome": "restored", "phase": "cleanup"}
    store.save_phase_status(ATTEMPT, "cleanup", status)
    store.save_archive_admission(ATTEMPT, "cleanup")
    store.save_ledger_record(
        f"episode-0001-{ATTEMPT}-cleanup-result",
        {"kind": "phase_result", "recorded_at_utc": CLEANUP_AT, "outcome": "restored"},
    )
    store.update_current_status(status)
    store.refresh_index()
    base = [
        "--import-exit",
        "--campaign",
        "fastloop",
        "--attempt",
        ATTEMPT,
        "--charter",
        str(charter),
        "--addendum",
        str(addendum),
    ]
    return cli, env, base, lab, addendum


def _archive_bytes(root: Path) -> dict[str, bytes]:
    directory = root / "data" / "commissioning"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_the_import_is_additive_and_claims_no_more_than_absence(
    import_lab, capsys, tmp_path: Path
):
    """Byte-exact originals, a preserved index, no process-exit, no credit."""
    cli, env, base, lab, addendum = import_lab
    before = _archive_bytes(tmp_path)
    index_before = before[
        f"data/commissioning/{FASTLOOP_CAMPAIGN.campaign_id}/index.json"
    ]

    code, imported = _run(
        cli, [*base, "--import-manifest", str(lab.manifest_file())], env, capsys
    )

    assert code == 0, imported
    assert imported["outcome"] == "absence_observed_after_graceful_request"
    assert imported["retire_credited"] is False
    after = _archive_bytes(tmp_path)
    campaign = f"data/commissioning/{FASTLOOP_CAMPAIGN.campaign_id}"
    for name, raw in before.items():
        if name != f"{campaign}/index.json":
            assert after[name] == raw, name
    digest = hashlib.sha256(index_before).hexdigest()
    assert after[f"{campaign}/index-history/index-{digest}.json"] == index_before
    index = json.loads(after[f"{campaign}/index.json"])
    assert index["predecessor"]["sha256"] == digest
    assert after[f"{campaign}/authority/addendum-02.md"] == addendum.read_bytes()
    for role, path in lab.files.items():
        suffix = path.suffix
        stored = f"{campaign}/{ATTEMPT}/exit-import-{role.replace('_', '-')}{suffix}"
        assert after[stored] == path.read_bytes(), role
    store = _store(tmp_path)
    assert not store.record_path_for(ATTEMPT, "process-exit").exists()
    assert store.verify_index() == ()
    record = store.load_exit_import(ATTEMPT)
    assert record["exit_method"] == "unproven"
    assert record["retire_credited"] is False
    assert record["recorder_source"]["sha"] == "d" * 40
    assert record["episode_source"] == {
        "sha": HEAD,
        "tree": TREE,
        "ancestor_of_recorder": True,
    }
    assert record["lead_assertions_not_evidence"] == ["completion_method", "note"]
    assert record["fresh_state"]["packet_tracer_contacted"] is False
    assert record["fresh_state"]["owned_pid_present"] is False
    assert record["archived_at_utc"] > CENSUS_AT.replace("Z", "+00:00")
    assert record["transcript_source"]["lines_verified"] == lab.lines

    code, again = _run(
        cli, [*base, "--import-manifest", str(lab.manifest_file())], env, capsys
    )
    assert code == 2
    assert again["reason"] == "import_exit:ValueError"


def _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path: Path):
    before = _archive_bytes(tmp_path)
    code, refused = _run(cli, argv, env, capsys)
    assert code == 2, refused
    assert _archive_bytes(tmp_path) == before
    return refused


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("other-attempt", "import_not_authorized:"),
        ("wrong-addendum", "import_not_authorized:"),
        ("not-descendant", "import_exit:ValueError"),
        ("other-episode-tree", "import_exit:ValueError"),
        ("dirty-recorder", "import_exit:ValueError"),
        ("excerpt-not-source", "import_exit:ValueError"),
        ("owned-pid-present", "import_exit:ValueError"),
        ("census-unreadable", "import_exit:ValueError"),
    ],
)
def test_an_unauthorized_or_unsupported_import_writes_nothing(
    import_lab, capsys, tmp_path: Path, monkeypatch, change, reason
):
    """Every refusal happens before the first write."""
    cli, env, base, lab, addendum = import_lab
    argv = [*base, "--import-manifest", str(lab.manifest_file())]
    if change == "other-attempt":
        argv[argv.index(ATTEMPT)] = OTHER
    elif change == "wrong-addendum":
        addendum.write_bytes(b"# Another addendum\r\n")
    elif change in {"not-descendant", "other-episode-tree"}:
        ancestor = change == "other-episode-tree"
        tree = "f" * 40 if ancestor else TREE
        monkeypatch.setattr(
            cli,
            "_SOURCE_ANCESTRY",
            lambda _r, a, d: SourceAncestry(a, d, tree, is_ancestor=ancestor),
        )
    elif change == "dirty-recorder":
        monkeypatch.setattr(
            cli,
            "repository_identity",
            lambda _root: replace(_checkpoint(), clean=False),
        )
    elif change == "excerpt-not-source":
        lines = _transcript_lines()
        lines[5] = lines[5].replace(b"exited=False", b"exited=True")
        lab.transcript.write_bytes(b"\n".join(lines) + b"\n")
    elif change in {"owned-pid-present", "census-unreadable"}:

        class _Census(_NoPacketTracer):
            error = "unreadable" if change == "census-unreadable" else ""
            processes = (type("Row", (), {"pid": PID})(),)

        monkeypatch.setattr(cli, "PowerShellPacketTracerProcessReader", _Census)

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused["reason"].startswith(reason)


def test_an_unsupported_manifest_is_refused_with_its_findings(
    import_lab, capsys, tmp_path: Path
):
    """The pure rule's findings reach the operator; nothing is written."""
    cli, env, base, lab, _addendum = import_lab
    lab.manifest["capture_field_provenance"]["observed_at_utc"] = "lead_assertion"
    argv = [*base, "--import-manifest", str(lab.manifest_file())]

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused["reasons"] == ["exit_claim_not_supported_by_observation"]


@pytest.mark.parametrize(
    ("argv_change", "reason"),
    [
        (["--campaign", "c31"], "import_exit_is_experimental_only"),
        (["--ci-run", "42"], "experimental_ci_claim_refused"),
    ],
)
def test_a_delivery_campaign_or_a_ci_claim_cannot_import(
    import_lab, capsys, tmp_path: Path, argv_change, reason
):
    """The exception is experimental and local; it borrows no delivery label."""
    cli, env, base, lab, _addendum = import_lab
    argv = [*base, "--import-manifest", str(lab.manifest_file())]
    if argv_change[0] == "--campaign":
        argv[argv.index("fastloop")] = "c31"
    else:
        argv += argv_change

    refused = _refuses_and_writes_nothing(cli, env, argv, capsys, tmp_path)

    assert refused == {"outcome": "refused", "reason": reason}


def test_a_new_index_names_only_a_preserved_predecessor(tmp_path: Path):
    """The prior index is kept byte for byte; a made-up predecessor is refused."""
    store = _store(tmp_path)
    store.save_ledger_record("episode-0001-opening", {"kind": "episode_opening"})
    store.refresh_index()
    prior = store.index_bytes()

    with pytest.raises(ValueError):
        store.refresh_index(
            predecessor={"path": "data/elsewhere.json", "sha256": "0" * 64}
        )
    predecessor = store.preserve_index()
    assert store.preserve_index() == predecessor
    store.refresh_index(predecessor=predecessor)

    assert json.loads(store.index_bytes())["predecessor"] == predecessor
    assert (tmp_path / str(predecessor["path"])).read_bytes() == prior
    assert predecessor["sha256"] == hashlib.sha256(prior).hexdigest()
    assert store.verify_index() == ()
    (tmp_path / str(predecessor["path"])).write_bytes(prior + b" ")
    assert store.verify_index() == ("archive_bytes_changed",)


def test_the_pinned_authority_is_the_operator_addendum():
    """The one importable exit is episode 1's PID 3248 under Addendum 02."""
    assert FASTLOOP_EPISODE_1_EXIT_IMPORT == HistoricalExitImportAuthority(
        addendum_sha256="684636f6436934029709d83e7bd651194aa6d3a7cd9e56da55d592b8660ea288",
        campaign_id="SERVER-PT-IOS-FASTLOOP-01",
        attempt_id="b118c84808bb06f3a8ede6cf124323b2",
        episode=1,
        episode_source_sha="1d086aad5ec473a29ddb3c631d6615ee8344d29d",
        episode_source_tree="1e709da5744ad8861239765bff9fa0a0e1c6a09f",
    )


# -- the real helper, against a window this test creates ------------------------------

_NATIVE = os.environ.get("PT_MCP_NATIVE_WINDOW_TESTS") == "1"
_FORMS = r"""
Add-Type -AssemblyName System.Windows.Forms
function New-ProbeForm([string]$title) {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    # Shown in the taskbar, a form has no owner window, like Packet Tracer's.
    $form.Opacity = 0
    $form.StartPosition = 'Manual'
    $form.Location = New-Object System.Drawing.Point(-32000, -32000)
    return $form
}
$log = New-ProbeForm 'Logs - MCP BUILDER'
$document = New-ProbeForm 'fastloop window probe'
$log.Show()
[System.Windows.Forms.Application]::Run($document)
"""


@pytest.mark.skipif(
    sys.platform != "win32" or not _NATIVE,
    reason="opt-in: set PT_MCP_NATIVE_WINDOW_TESTS=1 on Windows",
)
def test_the_native_helper_enumerates_selects_and_closes_one_window():
    """Real user32 calls: attribution, selection, a refused and a sent close."""
    encoded = base64.b64encode(_FORMS.encode("utf-16-le")).decode("ascii")
    probe = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    )
    try:
        control = PowerShellOwnedProcessControl()
        deadline = time.monotonic() + 30
        while True:
            census = control.windows(probe.pid)
            visible = [window for window in census.windows if window.visible]
            if len(visible) >= 2 or time.monotonic() > deadline:
                break
            time.sleep(0.5)
        assert census.complete is True and census.error == ""
        assert all(window.owner_pid == probe.pid for window in census.windows)
        target, found = select_document_window(probe.pid, census)
        assert found == ()
        assert target.title == "fastloop window probe"
        refused = control.close_window(probe.pid, target.handle, "0" * 64)
        assert refused.sent is False
        assert refused.refusal == "window_identity_changed"
        foreign = control.close_window(
            os.getpid(), target.handle, target.identity_digest
        )
        assert foreign.sent is False
        assert foreign.refusal == "window_owner_changed"
        sent = control.close_window(probe.pid, target.handle, target.identity_digest)
        assert sent.sent is True
        assert probe.wait(timeout=30) == 0
    finally:
        if probe.poll() is None:
            probe.kill()
