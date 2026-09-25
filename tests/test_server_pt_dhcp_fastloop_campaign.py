"""Campaign SERVER-PT-DHCP-FASTLOOP-01: identity, ledger and retirement.

DF1, DF2 and DF5 of the DHCP fast-loop brief. The campaign is selected by its
identity and charter digest; a governed qualification run is one ledger
phase that never draws the protected tail; and retirement of a qualification
laboratory derives its ownership basis from the archived qualification,
without ever forcing, because the charter does not authorize a force.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packet_tracer_mcp.adapters.cli.server_pt_campaign_archive import (
    archive_or_stop,
)
from packet_tracer_mcp.adapters.cli.server_pt_live_phase import PhasePreflight
from packet_tracer_mcp.application.use_cases.server_pt_campaign import (
    DHCP_FASTLOOP_CAMPAIGN,
    FASTLOOP_CAMPAIGN,
    ExecutionPurpose,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign_ledger import (
    DHCP_FASTLOOP_ALLOWANCE,
    FASTLOOP_ALLOWANCE,
    allowance_for,
    episode_name,
    ledger_record_findings,
    ledger_totals,
    opening_findings,
    phase_admission_findings,
    phase_record_name,
    qualification_admitted,
    unsettled_phases,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from tests.test_server_pt_fastloop_retirement import (
    ATTEMPT,
    COMMAND_LINE,
    DOCUMENT,
    EXTENSION_LOG_WINDOW_TITLE,
    HEAD,
    INCARNATION,
    LOG,
    PATH,
    PID,
    TREE,
    _checkpoint,
    _FakeOS,
    _Isolated,
    _process,
    _run,
)

ROOT = Path(__file__).resolve().parents[1]
WORK_ORDER = (
    ROOT
    / "docs"
    / "reference"
    / "server-pt"
    / "assignments"
    / "Next_Work_S3_Q3_FASTLOOP_PROPOSAL.md"
)
OPENED = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)


# -- DF1: identity and charter ---------------------------------------------------


def test_the_dhcp_campaign_is_selected_by_identity_and_its_own_charter():
    """The digest is the archived work order's, not FASTLOOP's."""
    assert DHCP_FASTLOOP_CAMPAIGN.campaign_id == "SERVER-PT-DHCP-FASTLOOP-01"
    assert DHCP_FASTLOOP_CAMPAIGN.purpose is ExecutionPurpose.EXPERIMENTAL
    assert DHCP_FASTLOOP_CAMPAIGN.complete_attempt_limit is None
    assert DHCP_FASTLOOP_CAMPAIGN.acceptance_cost_pin is None
    assert (
        DHCP_FASTLOOP_CAMPAIGN.charter_sha256
        == hashlib.sha256(WORK_ORDER.read_bytes()).hexdigest()
    )
    assert DHCP_FASTLOOP_CAMPAIGN.charter_sha256 != FASTLOOP_CAMPAIGN.charter_sha256


def test_only_the_charter_that_authorized_a_force_permits_one():
    """The work order says it does not newly authorize force termination."""
    assert DHCP_FASTLOOP_CAMPAIGN.forced_retirement_authorized is False
    assert FASTLOOP_CAMPAIGN.forced_retirement_authorized is True


def test_each_experimental_charter_has_its_own_ledger_ceilings():
    """50,000 / 21,600 s with 1,000 / 600 protected, as the work order states."""
    assert allowance_for(DHCP_FASTLOOP_CAMPAIGN.campaign_id) is DHCP_FASTLOOP_ALLOWANCE
    assert allowance_for(FASTLOOP_CAMPAIGN.campaign_id) is FASTLOOP_ALLOWANCE
    assert (
        DHCP_FASTLOOP_ALLOWANCE.total_operations,
        DHCP_FASTLOOP_ALLOWANCE.total_seconds,
        DHCP_FASTLOOP_ALLOWANCE.protected_operations,
        DHCP_FASTLOOP_ALLOWANCE.protected_seconds,
    ) == (50_000, 21_600, 1_000, 600)
    with pytest.raises(ValueError, match="no ledger allowance"):
        allowance_for("SERVER-PT-C31-COMMISSION-01")


# -- DF2: the qualification phase ------------------------------------------------


def _opening(**overrides) -> dict[str, object]:
    base = {
        "kind": "episode_opening",
        "episode": 1,
        "question": "Which pool serves a Server-PT client on 9.0.1.0858?",
        "stop_rule": "stop on any unresolved effect or native-default drift",
        "source_sha": HEAD,
        "source_tree": TREE,
        "attempt_ids": [ATTEMPT],
        "tests_run": ["tests/test_server_pt_dhcp_fastloop_campaign.py"],
        "targets": ["__MCP_E6Q_SRV"],
        "permitted_effects": ["qualification:Q3-FL-C1"],
        "allocated_operations": 440,
        "allocated_seconds": 2400.0,
        "opened_at_utc": OPENED.isoformat(),
    }
    return {**base, **overrides}


def _admit(records, *, operations=440, seconds=1500.0, now=None, phase="qualification"):
    return phase_admission_findings(
        records,
        episode=1,
        attempt_id=ATTEMPT,
        phase=phase,
        granted_operations=operations,
        granted_seconds=seconds,
        allowance=DHCP_FASTLOOP_ALLOWANCE,
        now=now or OPENED + timedelta(seconds=5),
        source_sha=HEAD,
        source_tree=TREE,
    )


def test_a_qualification_phase_is_admitted_against_its_episode_at_its_checkpoint():
    """The grant must fit the episode and name the episode's exact source."""
    records = {episode_name(1) + "-opening": _opening()}
    assert opening_findings({}, _opening(), DHCP_FASTLOOP_ALLOWANCE, OPENED) == ()
    assert _admit(records) == ((), False)
    assert _admit(records, operations=441) == (
        ("phase_exceeds_episode_allocation",),
        False,
    )
    other = phase_admission_findings(
        records,
        episode=1,
        attempt_id=ATTEMPT,
        phase="qualification",
        granted_operations=10,
        granted_seconds=10.0,
        allowance=DHCP_FASTLOOP_ALLOWANCE,
        now=OPENED,
        source_sha="d" * 40,
        source_tree=TREE,
    )
    assert other == (("phase_source_differs_from_episode",), False)


def test_qualification_never_draws_the_protected_tail():
    """Only cleanup may exceed its episode; a qualification run may not."""
    records = {episode_name(1) + "-opening": _opening(allocated_operations=10)}
    findings, protected = _admit(records, operations=11, seconds=10.0)
    assert findings == ("phase_exceeds_episode_allocation",)
    assert protected is False


def test_an_unsettled_qualification_is_charged_at_its_grant_and_a_result_at_its_use():
    """A hard stop between admission and result never shrinks the charge."""
    admission = phase_record_name(1, ATTEMPT, "qualification", "admission")
    result = phase_record_name(1, ATTEMPT, "qualification", "result")
    records = {
        episode_name(1) + "-opening": _opening(),
        admission: {
            "kind": "phase_admission",
            "episode": 1,
            "attempt_id": ATTEMPT,
            "phase": "qualification",
            "granted_operations": 440,
            "granted_seconds": 1500.0,
            "admitted_at_utc": (OPENED + timedelta(seconds=5)).isoformat(),
        },
        episode_name(1) + "-closing": {
            "kind": "episode_closing",
            "episode": 1,
            "closed_at_utc": (OPENED + timedelta(seconds=600)).isoformat(),
        },
    }
    for name, value in records.items():
        assert ledger_record_findings(name, value, records) == ()
    later = OPENED + timedelta(days=1)
    assert unsettled_phases(records, 1) == (f"{ATTEMPT}:qualification",)
    assert (
        ledger_totals(records, DHCP_FASTLOOP_ALLOWANCE, later).committed_operations
        == 440
    )
    records[result] = {
        "kind": "phase_result",
        "episode": 1,
        "attempt_id": ATTEMPT,
        "phase": "qualification",
        "used_operations": 57,
        "active_seconds": 212.5,
    }
    assert ledger_record_findings(result, records[result], records) == ()
    assert (
        ledger_totals(records, DHCP_FASTLOOP_ALLOWANCE, later).committed_operations
        == 57
    )


def test_qualification_admitted_names_only_its_own_attempt():
    """Another attempt's admission establishes nothing about this one."""
    records = {
        "x": {
            "kind": "phase_admission",
            "phase": "qualification",
            "attempt_id": "1" * 32,
        },
        "y": {"kind": "phase_admission", "phase": "setup", "attempt_id": ATTEMPT},
    }
    assert qualification_admitted(records, ATTEMPT) is False
    assert qualification_admitted(records, "1" * 32) is True


# -- CLI: what the DHCP campaign may do here ------------------------------------------


@pytest.fixture
def dhcp_cli(tmp_path: Path, monkeypatch):
    """Bind a test charter to the DHCP campaign; forbid every other read."""
    from importlib import import_module

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "work-order.md"
    charter.write_text("dhcp work order", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "DHCP_FASTLOOP_CHARTER_SHA256",
        hashlib.sha256(charter.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(cli, "repository_identity", lambda _root: _checkpoint())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("no process may be read by this refusal")

    monkeypatch.setattr(cli, "phase_preflight", forbidden)
    monkeypatch.setattr(cli, "_RETIREMENT_ISOLATION", _Isolated)
    return cli, charter, {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}


@pytest.mark.parametrize(
    "mode",
    [
        "--prepare",
        "--inspect",
        "--qualify",
        "--setup",
        "--accept",
        "--cleanup",
        "--record-exit",
        "--import-exit",
        "--record-correction",
    ],
)
def test_every_http_commissioning_mode_refuses_for_the_dhcp_campaign(
    dhcp_cli, capsys, tmp_path: Path, mode
):
    """Its bridge work is a qualification stage, never a commissioning phase."""
    cli, charter, env = dhcp_cli
    code, refused = _run(
        cli,
        [
            mode,
            "--campaign",
            "dhcp-fastloop",
            "--attempt",
            ATTEMPT,
            "--charter",
            str(charter),
        ],
        env,
        capsys,
    )
    assert code == 2
    assert refused == {
        "outcome": "refused",
        "reason": "mode_not_part_of_the_dhcp_campaign",
    }
    assert not (tmp_path / "data").exists()


def test_the_dhcp_ledger_refuses_another_campaigns_charter(dhcp_cli, capsys, tmp_path):
    """FASTLOOP's work order does not open a DHCP episode."""
    cli, _charter, env = dhcp_cli
    other = tmp_path / "fastloop.md"
    other.write_text("experimental work order", encoding="utf-8")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(_opening()), encoding="utf-8")
    code, refused = _run(
        cli,
        [
            "--open-episode",
            "--campaign",
            "dhcp-fastloop",
            "--charter",
            str(other),
            "--episode-plan",
            str(plan),
        ],
        env,
        capsys,
    )
    assert code == 2
    assert refused["reason"] == "charter_digest_mismatch"


def test_the_dhcp_ledger_opens_an_episode_under_its_own_campaign(
    dhcp_cli, capsys, tmp_path: Path
):
    """The opening names this campaign, charter and the observed checkpoint."""
    cli, charter, env = dhcp_cli
    plan = tmp_path / "plan.json"
    fields = {
        key: value
        for key, value in _opening().items()
        if key not in {"kind", "episode", "source_sha", "source_tree", "opened_at_utc"}
    }
    plan.write_text(json.dumps(fields), encoding="utf-8")
    code, opened = _run(
        cli,
        [
            "--open-episode",
            "--campaign",
            "dhcp-fastloop",
            "--charter",
            str(charter),
            "--episode-plan",
            str(plan),
        ],
        env,
        capsys,
    )
    assert code == 0, opened
    record = json.loads(Path(opened["record_path"]).read_bytes())
    assert record["campaign_id"] == DHCP_FASTLOOP_CAMPAIGN.campaign_id
    assert record["execution_purpose"] == "experimental"
    assert (record["source_sha"], record["source_tree"]) == (HEAD, TREE)
    assert opened["ledger"]["committed_operations"] == 440
    assert opened["ledger"]["ordinary_operations_left"] == 50_000 - 1_000 - 440


# -- DF5: retirement of a qualification laboratory -----------------------------------


@pytest.fixture
def launched(dhcp_cli, tmp_path: Path, capsys, monkeypatch):
    """Record one DHCP campaign launch whose capture matches the OS reading."""
    import time

    cli, charter, env = dhcp_cli
    monkeypatch.setattr(
        cli,
        "phase_preflight",
        lambda *_args, **_kwargs: PhasePreflight(
            _checkpoint(), None, _process(), campaign=DHCP_FASTLOOP_CAMPAIGN
        ),
    )
    monkeypatch.setattr(cli, "RETIREMENT_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(cli, "RETIREMENT_EXIT_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(cli, "RETIREMENT_HELPER_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(cli, "_retirement_sleep", lambda _seconds: time.sleep(0.002))
    system = _FakeOS()
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
    base = [
        "--campaign",
        "dhcp-fastloop",
        "--attempt",
        ATTEMPT,
        "--charter",
        str(charter),
    ]
    code, owned = _run(
        cli, ["--record-launch", *base, "--launch-evidence", str(capture)], env, capsys
    )
    assert code == 0, owned
    assert owned["blank_document_proven"] is True
    system.calls.clear()
    system.censuses = 0
    return cli, env, base, system


def _store(tmp_path: Path) -> ServerPtCommissioningStore:
    return ServerPtCommissioningStore(tmp_path, DHCP_FASTLOOP_CAMPAIGN.campaign_id)


def _archive_qualification(tmp_path: Path, **status) -> None:
    store = _store(tmp_path)
    document = {"phase": "qualification", "attempt_id": ATTEMPT, **status}
    store.save_phase_status(ATTEMPT, "qualification", document)
    archive_or_stop(store, dict(document))
    assert store.verify_index() == ()


@pytest.mark.parametrize(
    ("status", "disposition", "basis"),
    [
        (
            {
                "outcome": "completed",
                "effects_dispatched": True,
                "workspace_baseline_empty": True,
                "restoration_proven": True,
            },
            "exited",
            "owned_qualification_restored",
        ),
        (
            {
                "outcome": "stopped",
                "effects_dispatched": True,
                "workspace_baseline_empty": True,
                "restoration_proven": False,
            },
            "exited_dirty",
            "empty_baseline_then_qualification_effects",
        ),
        (
            {
                "outcome": "refused",
                "effects_dispatched": False,
                "workspace_baseline_observed": False,
                "workspace_baseline_empty": False,
                "restoration_proven": False,
            },
            "exited_before_setup",
            "blank_launch_without_qualification_effects",
        ),
    ],
    ids=["restored", "dirty", "refused-before-effects"],
)
def test_an_archived_qualification_decides_the_retirement_basis(
    launched, capsys, tmp_path: Path, status, disposition, basis
):
    """The ownership basis comes from the indexed qualification status."""
    cli, env, base, system = launched
    _archive_qualification(tmp_path, **status)

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    assert (retired["outcome"], retired["ownership_basis"]) == (disposition, basis)
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls


def test_an_admitted_qualification_without_a_status_is_an_interrupted_basis(
    launched, capsys, tmp_path: Path
):
    """Effects of unknown state still rest on the blank launch, named as such."""
    cli, env, base, _system = launched
    store = _store(tmp_path)
    store.save_ledger_record(episode_name(1) + "-opening", _opening())
    store.save_ledger_record(
        phase_record_name(1, ATTEMPT, "qualification", "admission"),
        {
            "kind": "phase_admission",
            "episode": 1,
            "attempt_id": ATTEMPT,
            "phase": "qualification",
            "granted_operations": 440,
            "granted_seconds": 1500.0,
            "admitted_at_utc": (OPENED + timedelta(seconds=5)).isoformat(),
        },
    )
    store.refresh_index()

    code, retired = _run(cli, ["--retire", *base], env, capsys)

    assert code == 0, retired
    assert retired["outcome"] == "exited_interrupted"
    assert retired["ownership_basis"] == "blank_launch_then_interrupted_qualification"


def test_a_qualification_whose_baseline_was_not_empty_establishes_no_basis(
    launched, capsys, tmp_path: Path
):
    """Effects on a workspace not proven disposable authorize no close at all."""
    cli, env, base, system = launched
    _archive_qualification(
        tmp_path,
        outcome="stopped",
        effects_dispatched=True,
        workspace_baseline_empty=False,
        restoration_proven=False,
    )
    code, refused = _run(cli, ["--retire", *base], env, capsys)
    assert code == 2
    assert refused["reason"].startswith("retirement_unestablished")
    assert system.posted == []


def test_a_refusal_after_a_foreign_baseline_establishes_no_basis(
    launched, capsys, tmp_path: Path
):
    """A blank launch that later showed foreign devices is not ours to close."""
    cli, env, base, system = launched
    _archive_qualification(
        tmp_path,
        outcome="refused",
        effects_dispatched=False,
        workspace_baseline_observed=True,
        workspace_baseline_empty=False,
        restoration_proven=False,
    )
    code, refused = _run(cli, ["--retire", *base], env, capsys)
    assert code == 2
    assert refused["reason"].startswith("retirement_unestablished")
    assert system.posted == []


def test_the_dhcp_campaign_never_forces_a_laboratory_that_does_not_exit(
    launched, capsys, tmp_path: Path
):
    """A close that is not followed by an exit stays unresolved, never killed."""
    cli, env, base, system = launched
    _archive_qualification(
        tmp_path,
        outcome="completed",
        effects_dispatched=True,
        workspace_baseline_empty=True,
        restoration_proven=True,
    )
    system.on_close = "stay"

    code, refused = _run(cli, ["--retire", *base], env, capsys)

    assert code == 2, refused
    assert system.posted == [DOCUMENT.handle]
    assert "terminate" not in system.calls
    assert "terminate_helper" not in system.calls
    assert not _store(tmp_path).record_path_for(ATTEMPT, "process-exit").exists()
    directory = tmp_path / "data" / "commissioning" / DHCP_FASTLOOP_CAMPAIGN.campaign_id
    attempts = [
        json.loads(path.read_bytes())
        for path in sorted((directory / ATTEMPT).glob("retirement-attempt-*.json"))
    ]
    assert any(
        "forced_retirement_not_authorized_by_campaign" in item.get("refusal", [])
        for item in attempts
    )
