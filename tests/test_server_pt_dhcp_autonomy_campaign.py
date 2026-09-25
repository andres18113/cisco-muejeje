"""Prospective DHCP mission authority is separate from the closed campaign."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from packet_tracer_mcp.adapters.cli import server_pt_commissioning
from packet_tracer_mcp.application.use_cases import (
    server_pt_campaign,
    server_pt_process_evidence,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign_ledger import (
    allowance_for,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_process_control import (
    PowerShellOwnedProcessControl,
    SavePromptResponse,
    visible_set_digest,
)
from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    FileCampaignCoordinator,
)
from tests.test_server_pt_fastloop_retirement import (
    ATTEMPT,
    COMMAND_LINE,
    DOCUMENT,
    HEAD,
    INCARNATION,
    LOG,
    PATH,
    PID,
    SIGNATURE,
    START_TICKS,
    TREE,
    _census,
    _checkpoint,
    _FakeOS,
    _Isolated,
    _run,
    _Runner,
    _window,
)

MANDATE = (
    Path(__file__).resolve().parents[1]
    / "docs/reference/server-pt/assignments/ServerPT_DHCP_Delegated_Autonomy_Mandate.md"
)


def test_new_mission_uses_its_own_authority_and_finite_ledger() -> None:
    """The old expired ledger cannot be interpreted as a fresh grant."""
    campaign = getattr(server_pt_campaign, "DHCP_AUTONOMY_CAMPAIGN", None)
    assert campaign is not None
    assert campaign.campaign_id == "SERVER-PT-DHCP-AUTONOMOUS-02"
    assert campaign.charter_sha256 == hashlib.sha256(MANDATE.read_bytes()).hexdigest()
    assert campaign.experimental is True
    assert campaign.forced_retirement_authorized is True
    allowance = allowance_for(campaign.campaign_id)
    assert (
        allowance.total_operations,
        allowance.total_seconds,
        allowance.protected_operations,
        allowance.protected_seconds,
    ) == (10_000, 14_400, 1_000, 600)
    assert campaign.campaign_id != server_pt_campaign.DHCP_FASTLOOP_CAMPAIGN.campaign_id
    assert (
        allowance_for(
            server_pt_campaign.DHCP_FASTLOOP_CAMPAIGN.campaign_id
        ).total_seconds
        == 21_600
    )


def test_new_mission_cli_opens_only_with_the_new_mandate(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Old authority cannot open the prospective mission's own ledger."""
    assert "dhcp-autonomy" in server_pt_commissioning._CAMPAIGNS
    monkeypatch.setattr(
        server_pt_commissioning, "repository_identity", lambda _: _checkpoint()
    )
    plan = tmp_path / "episode.json"
    plan.write_text(
        json.dumps(
            {
                "question": "Does a documented setter change native serverPool?",
                "stop_rule": "stop on unknown effect or incomplete readback",
                "attempt_ids": [ATTEMPT],
                "tests_run": ["tests/test_server_pt_dhcp_autonomy_campaign.py"],
                "targets": ["__MCP_E6Q_SRV"],
                "permitted_effects": ["qualification:Q3-NATIVE-PROBE"],
                "allocated_operations": 120,
                "allocated_seconds": 1800.0,
            }
        ),
        encoding="utf-8",
    )
    args = [
        "--open-episode",
        "--campaign",
        "dhcp-autonomy",
        "--episode-plan",
        str(plan),
        "--charter",
    ]
    env = {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}
    old = MANDATE.parent / "Next_Work_S3_Q3_FASTLOOP_PROPOSAL.md"
    code, refused = _run(server_pt_commissioning, [*args, str(old)], env, capsys)
    assert code == 2
    assert refused == {"outcome": "refused", "reason": "charter_digest_mismatch"}
    code, opened = _run(server_pt_commissioning, [*args, str(MANDATE)], env, capsys)
    assert code == 0, opened
    record = json.loads(Path(opened["record_path"]).read_bytes())
    assert record["campaign_id"] == "SERVER-PT-DHCP-AUTONOMOUS-02"
    assert record["charter_sha256"] == hashlib.sha256(MANDATE.read_bytes()).hexdigest()
    assert (record["source_sha"], record["source_tree"]) == (HEAD, TREE)
    assert opened["ledger"]["ordinary_operations_left"] == 10_000 - 1_000 - 120


def test_retirement_refuses_while_the_qualification_writer_holds_the_mailbox(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """A concurrent retirement cannot close the active writer's lab."""
    coordinator = FileCampaignCoordinator(tmp_path / "shared-campaign")
    active = coordinator.claim(attempt_id="a" * 32)
    try:
        assert hasattr(coordinator, "claim_lifecycle")
        monkeypatch.setattr(
            server_pt_commissioning,
            "_RETIREMENT_COORDINATOR",
            lambda: coordinator,
            raising=False,
        )
        code = server_pt_commissioning._retire(
            tmp_path, "b" * 32, server_pt_campaign.DHCP_AUTONOMY_CAMPAIGN
        )
        output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert code == 2
        assert output["reason"] == "campaign_already_claimed"
        assert coordinator.verify(active) == ()
        assert not (coordinator.scope / f"attempt-{'b' * 32}.json").exists()
    finally:
        assert coordinator.release(active) == ()


def test_interrupted_lifecycle_claim_removes_only_its_own_unreturned_lock(
    tmp_path: Path, monkeypatch
) -> None:
    """An interrupt after exclusive creation cannot strand an unknown holder."""
    coordinator = FileCampaignCoordinator(tmp_path / "shared-campaign")
    create = coordinator._create_exclusive

    def interrupt_after_create(path, payload, reason):
        create(path, payload, reason)
        raise KeyboardInterrupt

    monkeypatch.setattr(coordinator, "_create_exclusive", interrupt_after_create)
    with pytest.raises(KeyboardInterrupt):
        coordinator.claim_lifecycle(attempt_id=ATTEMPT)
    assert not (coordinator.scope / "campaign.lock").exists()
    assert not (coordinator.scope / f"attempt-{ATTEMPT}.json").exists()


def test_save_prompt_selection_requires_the_owned_document_and_exact_dialog():
    """A foreign or ambiguous modal can never be answered by retirement."""
    select = getattr(server_pt_process_evidence, "select_owned_save_prompt", None)
    assert select is not None
    prompt = _window(
        4545,
        "Exit -- Cisco Packet Tracer",
        owner=DOCUMENT.handle,
        class_name="Qt687QWindowIcon",
    )
    selected, findings = select(
        PID,
        _census(DOCUMENT, LOG, prompt),
        document=DOCUMENT,
        signature=SIGNATURE,
        start_ticks=START_TICKS,
    )
    assert selected == prompt
    assert findings == ()
    for bad in (
        _window(4545, prompt.title, owner=9999),
        _window(4545, "Unknown Prompt", owner=DOCUMENT.handle),
    ):
        selected, findings = select(
            PID,
            _census(DOCUMENT, LOG, bad),
            document=DOCUMENT,
            signature=SIGNATURE,
            start_ticks=START_TICKS,
        )
        assert selected is None
        assert findings


def test_retirement_claim_release_failure_is_archived(tmp_path, monkeypatch, capsys):
    """An observed exit cannot hide an unreleased writer claim."""

    class ReleaseReportsFailure(FileCampaignCoordinator):
        def release(self, claim):
            assert super().release(claim) == ()
            return ("campaign_claim:release_unverified",)

    monkeypatch.setattr(
        server_pt_commissioning,
        "_RETIREMENT_COORDINATOR",
        lambda: ReleaseReportsFailure(tmp_path / "scope"),
    )

    def refuse_once(root, attempt, campaign, **_kwargs):
        store = server_pt_commissioning.ServerPtCommissioningStore(
            root, campaign.campaign_id
        )
        return server_pt_commissioning._record_retirement_attempt(
            store,
            attempt,
            campaign,
            {"requested": False, "refusal": ["test_prior_refusal"]},
        )

    monkeypatch.setattr(server_pt_commissioning, "_retire_claimed", refuse_once)
    campaign = server_pt_campaign.DHCP_AUTONOMY_CAMPAIGN
    code = server_pt_commissioning._retire(tmp_path, ATTEMPT, campaign)
    output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 2
    assert output["refusal"] == ["retirement_claim_release_unverified"]
    store = server_pt_commissioning.ServerPtCommissioningStore(
        tmp_path, campaign.campaign_id
    )
    assert len(store.retirement_attempts(ATTEMPT)) == 1
    assert Path(output["claim_release_record"]).exists()
    assert store.verify_index() == ()


def test_interrupted_retirement_releases_and_archives_its_claim(tmp_path, monkeypatch):
    """An interrupted process action leaves explicit coordination evidence."""
    coordinator = FileCampaignCoordinator(tmp_path / "scope")
    monkeypatch.setattr(
        server_pt_commissioning, "_RETIREMENT_COORDINATOR", lambda: coordinator
    )

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(server_pt_commissioning, "_retire_claimed", interrupt)
    campaign = server_pt_campaign.DHCP_AUTONOMY_CAMPAIGN
    with pytest.raises(KeyboardInterrupt):
        server_pt_commissioning._retire(tmp_path, ATTEMPT, campaign)
    assert not (coordinator.scope / "campaign.lock").exists()
    directory = tmp_path / "data/commissioning" / campaign.campaign_id / ATTEMPT
    records = list(directory.glob("retirement-claim-release-*.json"))
    assert len(records) == 1
    saved = json.loads(records[0].read_bytes())
    assert saved["retirement_result_before_release"] == "interrupted:KeyboardInterrupt"


def test_save_prompt_helper_targets_only_the_revalidated_no_button():
    """The helper reports the exact prompt and one No invocation."""
    prompt = _window(
        4545,
        "Exit -- Cisco Packet Tracer",
        owner=DOCUMENT.handle,
        class_name="Qt687QWindowIcon",
    )
    runner = _Runner(
        json.dumps(
            {
                "sent": True,
                "refusal": "",
                "prompt": "Any unsaved changes will be lost. Do you want to save your work?",
                "button": "No",
            }
        )
    )
    control = PowerShellOwnedProcessControl(run_command=runner)
    assert hasattr(control, "answer_owned_save_prompt_no")
    response = control.answer_owned_save_prompt_no(
        PID,
        prompt.handle,
        DOCUMENT.handle,
        prompt.identity_digest,
        set_digest=visible_set_digest((DOCUMENT, LOG, prompt)),
        start_ticks=START_TICKS,
    )
    assert response.sent is True
    assert response.prompt == (
        "Any unsaved changes will be lost. Do you want to save your work?"
    )
    assert response.button == "No"
    assert (
        runner.script()
        .splitlines()[-1]
        .startswith(
            f"[PtMcpOwnedWindows]::AnswerNo({PID}, {prompt.handle}, {DOCUMENT.handle},"
        )
    )


def test_retirement_answer_uses_fresh_owned_prompt_and_process_identity():
    """A prompt tied to the disposable document can receive one exact No."""
    answer = getattr(server_pt_commissioning, "_answer_owned_save_prompt", None)
    assert answer is not None
    system = _FakeOS()
    system.on_close = "modal"
    closed = system.close_window(
        PID,
        DOCUMENT.handle,
        DOCUMENT.identity_digest,
        set_digest=visible_set_digest((DOCUMENT, LOG)),
        start_ticks=START_TICKS,
    )
    assert closed.sent
    prompt = _window(
        5555,
        "Exit -- Cisco Packet Tracer",
        owner=DOCUMENT.handle,
        class_name="Qt687QWindowIcon",
    )
    system.windows_of[PID][-1] = prompt

    def invoke_no(pid, handle, document_handle, digest, *, set_digest, start_ticks):
        assert (pid, handle, document_handle) == (
            PID,
            prompt.handle,
            DOCUMENT.handle,
        )
        assert digest == prompt.identity_digest
        assert not system._changed(pid, set_digest, start_ticks)
        system.present = False
        return SavePromptResponse(
            PID,
            prompt.handle,
            sent=True,
            prompt="Any unsaved changes will be lost. Do you want to save your work?",
            button="No",
        )

    system.answer_owned_save_prompt_no = invoke_no
    result = answer(
        system,
        PID,
        {
            "pid": PID,
            "process_path": PATH,
            "process_incarnation": INCARNATION,
            "observed_command_line": COMMAND_LINE,
            "observed_main_window_title": "Cisco Packet Tracer",
        },
        DOCUMENT,
        SIGNATURE,
        START_TICKS,
    )
    assert result["sent"] is True
    assert result["prompt"] == (
        "Any unsaved changes will be lost. Do you want to save your work?"
    )
    assert system.present is False


@pytest.mark.parametrize(
    ("prompt_title", "expected_code", "preexisting", "prior_uncertain"),
    [
        ("Exit -- Cisco Packet Tracer", 0, False, False),
        ("Unexpected Prompt", 2, False, False),
        ("Exit -- Cisco Packet Tracer", 0, True, False),
        ("Exit -- Cisco Packet Tracer", 2, True, True),
    ],
)
def test_autonomy_retirement_handles_only_the_owned_save_prompt(
    tmp_path: Path,
    monkeypatch,
    capsys,
    prompt_title,
    expected_code,
    preexisting,
    prior_uncertain,
):
    """The campaign does not leave its known disposable save dialog open."""
    campaign = server_pt_campaign.DHCP_AUTONOMY_CAMPAIGN
    store = server_pt_commissioning.ServerPtCommissioningStore(
        tmp_path, campaign.campaign_id
    )
    store.save_process_launch(
        ATTEMPT,
        {
            "pid": PID,
            "process_path": PATH,
            "process_incarnation": INCARNATION,
            "observed_command_line": COMMAND_LINE,
            "observed_main_window_title": "Cisco Packet Tracer",
            "observed_product_version": "9.0.1.0858",
            "observed_file_version": "9.0.1.0858",
            "campaign_id": campaign.campaign_id,
            "execution_purpose": "experimental",
            "source_sha": HEAD,
            "source_tree": TREE,
        },
    )
    store.refresh_index()

    class SavePromptOS(_FakeOS):
        def close_window(self, *args, **kwargs):
            response = super().close_window(*args, **kwargs)
            self.windows_of[PID][-1] = _window(
                5555,
                prompt_title,
                owner=DOCUMENT.handle,
                class_name="Qt687QWindowIcon",
            )
            return response

        def answer_owned_save_prompt_no(
            self, pid, handle, document_handle, digest, *, set_digest, start_ticks
        ):
            self.calls.append("answer_no")
            assert (pid, handle, document_handle) == (PID, 5555, DOCUMENT.handle)
            assert not self._changed(pid, set_digest, start_ticks)
            self.present = False
            return SavePromptResponse(
                PID,
                handle,
                sent=True,
                prompt="Any unsaved changes will be lost. Do you want to save your work?",
                button="No",
            )

    system = SavePromptOS()
    system.on_close = "modal"
    if preexisting:
        prior = system.close_window(
            PID,
            DOCUMENT.handle,
            DOCUMENT.identity_digest,
            set_digest=visible_set_digest((DOCUMENT, LOG)),
            start_ticks=START_TICKS,
        )
        assert prior.sent
        store.save_retirement_attempt(
            ATTEMPT,
            "20260925T200000Z",
            {
                "pid": PID,
                "process_path": PATH,
                "process_incarnation": INCARNATION,
                "method": "WM_CLOSE",
                "requested": True,
                "requested_at_utc": "2026-09-25T20:00:00+00:00",
                "close_target": server_pt_commissioning._window_record(DOCUMENT),
                "actual_exit_observed": False,
                "refusal": ["save_prompt_unanswered_or_unobservable"],
                **(
                    {"save_prompt_response": {"sent": False, "error": "unknown"}}
                    if prior_uncertain
                    else {}
                ),
            },
        )
        store.refresh_index()
    monkeypatch.setattr(server_pt_commissioning, "_PROCESS_CONTROL", system)
    monkeypatch.setattr(server_pt_commissioning, "_RETIREMENT_ISOLATION", _Isolated)
    monkeypatch.setattr(
        server_pt_commissioning, "repository_identity", lambda _: _checkpoint()
    )
    monkeypatch.setattr(
        server_pt_commissioning,
        "_RETIREMENT_COORDINATOR",
        lambda: FileCampaignCoordinator(tmp_path / "claim"),
    )
    monkeypatch.setattr(
        server_pt_commissioning, "_MAILBOX_DIR", lambda: tmp_path / "mailbox"
    )
    monkeypatch.setattr(server_pt_commissioning, "RETIREMENT_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(server_pt_commissioning, "_retirement_sleep", lambda _: None)
    code = server_pt_commissioning._retire(tmp_path, ATTEMPT, campaign)
    output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == expected_code, output
    assert "terminate" not in system.calls
    if expected_code == 0:
        assert "answer_no" in system.calls
        assert len(system.posted) == 1
        assert output["outcome"] == "exited_before_setup"
        exit_record = store.load_process_exit(ATTEMPT)
        assert exit_record["actual_exit_observed"] is True
        assert exit_record["save_prompt_response"]["button"] == "No"
    else:
        assert "answer_no" not in system.calls
        assert (
            "save_prompt_prior_close_unproven"
            if prior_uncertain
            else "save_prompt_unanswered_or_unobservable"
        ) in output["refusal"]
        assert output["quarantine"] == "owned_lab_open_prompt_unresolved"
