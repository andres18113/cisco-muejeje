"""DF2 to DF5: the qualification CLI under campaign SERVER-PT-DHCP-FASTLOOP-01.

The composition validates every campaign fact before the use case runs, admits
one `qualification` ledger phase, waives exactly the publication rule for
exactly the attempt it names, binds the launched process's incarnation, and
archives a status whose fields the retirement basis reads. These tests drive
the real CLI, the real commissioning store and ledger, and the Node stub.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path

import pytest

from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    CampaignQualificationAuthority,
    qualify_server_services,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign import (
    DHCP_FASTLOOP_CAMPAIGN,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign_ledger import (
    episode_name,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RefusalSubject,
    RepositoryIdentity,
    stage_definition,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_qualification_store import (
    QualificationRecordStore,
)
from tests.service_qualification_engine import (
    FORWARDING_ROWS,
    SIM_PROCESS_ID,
    SIM_PROCESS_INCARNATION,
    SIM_PROCESS_PATH,
    SIM_SHA,
    SIM_TREE,
    NodeEngine,
    NodeEngineTransport,
    authorization_args,
    request_args,
    require_node,
    simulated_boundaries,
)

STAGE = "Q3-FL-C1"
ATTEMPT = "c" * 32
UNPUBLISHED = RepositoryIdentity(
    branch="feature/server-pt-goal-foundations",
    head=SIM_SHA,
    tree=SIM_TREE,
    clean=True,
    upstream="cisco/feature/server-pt-goal-foundations",
    upstream_head="b" * 40,
)
ENGINE = {
    "terminals": True,
    "stp_rows": dict(FORWARDING_ROWS),
    "dhcp_default_pool": "native",
    "default_pool_realigns_on_address": True,
    "dhcp_pool_selection": "intended_then_default",
}


def _store(root: Path) -> ServerPtCommissioningStore:
    return ServerPtCommissioningStore(root, DHCP_FASTLOOP_CAMPAIGN.campaign_id)


def _open_episode(root: Path, *, attempt: str = ATTEMPT, sha: str = SIM_SHA) -> None:
    store = _store(root)
    store.save_ledger_record(
        episode_name(1) + "-opening",
        {
            "kind": "episode_opening",
            "episode": 1,
            "question": "Which pool serves a Server-PT client?",
            "stop_rule": "stop on an unresolved effect or native-default drift",
            "source_sha": sha,
            "source_tree": SIM_TREE,
            "attempt_ids": [attempt],
            "tests_run": ["tests/test_q3_fastloop_campaign_cli.py"],
            "targets": ["__MCP_E6Q_SRV"],
            "permitted_effects": ["qualification:Q3-FL-C1"],
            "allocated_operations": 440,
            "allocated_seconds": 2400.0,
            "opened_at_utc": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
        },
    )
    store.refresh_index()


def _launch(root: Path, **overrides) -> None:
    store = _store(root)
    store.save_process_launch(
        ATTEMPT,
        {
            "pid": SIM_PROCESS_ID,
            "process_path": SIM_PROCESS_PATH,
            "process_incarnation": SIM_PROCESS_INCARNATION,
            "campaign_id": DHCP_FASTLOOP_CAMPAIGN.campaign_id,
            "execution_purpose": "experimental",
            "source_sha": SIM_SHA,
            "source_tree": SIM_TREE,
            **overrides,
        },
    )
    store.refresh_index()


@pytest.fixture
def campaign(tmp_path: Path, monkeypatch):
    """Build a governed root with a charter, an open episode and a launch."""
    require_node()
    cli = import_module("packet_tracer_mcp.adapters.cli.service_qualification")
    charter = tmp_path / "work-order.md"
    charter.write_text("dhcp work order", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "DHCP_FASTLOOP_CHARTER_SHA256",
        hashlib.sha256(charter.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(cli, "repository_identity", lambda _root: UNPUBLISHED)
    engines: list[NodeEngine] = []

    def factory_for(root: Path):
        def factory(_governed_root):
            engine = NodeEngine(root, **ENGINE)
            engines.append(engine)
            return simulated_boundaries(
                root,
                NodeEngineTransport(engine),
                repository=lambda: UNPUBLISHED,
                record_store=QualificationRecordStore(
                    root / "data" / "services" / "qualification"
                ),
            )

        return factory

    def run(argv_extra=(), *, stage: str = STAGE, attempt: str = ATTEMPT, capsys=None):
        argv = (
            request_args(stage)
            + authorization_args(stage, attempt_id=attempt)
            + [
                "--campaign",
                "dhcp-fastloop",
                "--charter",
                str(charter),
                "--episode",
                "1",
            ]
            + list(argv_extra)
        )
        code = cli.main(
            argv,
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
            boundaries_factory=factory_for(tmp_path),
        )
        return code

    yield cli, run, charter
    for engine in engines:
        engine.close()


def _printed(capsys) -> dict:
    lines = capsys.readouterr().out.strip().splitlines()
    return json.loads(lines[-1])


def test_a_campaign_run_admits_settles_and_archives_its_phase(
    campaign, tmp_path, capsys
):
    """The unpublished checkpoint runs, and every campaign fact is recorded."""
    _cli, run, _charter = campaign
    _open_episode(tmp_path)
    _launch(tmp_path)

    code = run()
    summary = _printed(capsys)

    assert code == 0, summary
    assert summary["campaign"]["publication_waived_for_this_attempt_only"] is True
    store = _store(tmp_path)
    records = store.ledger_records()
    admission = records[f"episode-0001-{ATTEMPT}-qualification-admission"]
    result = records[f"episode-0001-{ATTEMPT}-qualification-result"]
    assert admission["granted_operations"] == 440
    assert result["used_operations"] == summary["operations_used"]
    status = store.load_phase_status(ATTEMPT, "qualification")
    assert status["effects_dispatched"] is True
    assert status["workspace_baseline_empty"] is True
    assert status["restoration_proven"] is True
    assert store.external_source_registered(ATTEMPT, "qualification-record")
    assert store.verify_index() == ()
    commissioning = import_module(
        "packet_tracer_mcp.adapters.cli.server_pt_commissioning"
    )
    assert commissioning._qualification_basis(store, ATTEMPT) == (
        "exited",
        "owned_qualification_restored",
    )


@pytest.mark.parametrize(
    ("setup", "argv", "reason"),
    [
        ("launch", ["--charter", "missing.md"], "charter_unreadable"),
        ("launch", [], None),
        ("none", [], "campaign_launch_unestablished"),
        ("pid", [], "authorization_differs_from_the_campaign_launch"),
        ("source", [], "source_differs_from_the_launch_checkpoint"),
        ("episode", [], "episode_not_opened"),
    ],
    ids=["charter", "control", "no-launch", "pid", "source", "no-episode"],
)
def test_every_campaign_fact_refuses_before_contact(
    campaign, tmp_path, capsys, setup, argv, reason
):
    """A missing or foreign campaign fact contacts nothing and admits nothing."""
    _cli, run, _charter = campaign
    if setup != "episode":
        _open_episode(tmp_path)
    if setup in ("launch", "episode"):
        _launch(tmp_path)
    elif setup == "pid":
        _launch(tmp_path, pid=SIM_PROCESS_ID + 1)
    elif setup == "source":
        _launch(tmp_path, source_sha="d" * 40)

    code = run(argv)
    printed = _printed(capsys)

    if reason is None:
        assert code == 0, printed
        return
    assert code == 2, printed
    assert reason in (printed.get("reason"), *printed.get("reasons", []))
    records = _store(tmp_path).ledger_records()
    assert not any("qualification-admission" in name for name in records)
    assert not (tmp_path / "data" / "services" / "qualification").exists()


def test_a_non_campaign_stage_is_refused_by_the_campaign(campaign, tmp_path, capsys):
    """The campaign runs its Q3-FL profiles only, never the historical Q3."""
    _cli, run, _charter = campaign
    _open_episode(tmp_path)
    _launch(tmp_path)
    code = run(stage="Q3")
    assert code == 2
    assert _printed(capsys)["reason"] == "stage_not_part_of_the_dhcp_campaign"


def test_a_q3fl_stage_without_its_campaign_is_refused(tmp_path, capsys):
    """A Q3-FL profile exists only under its campaign's authority."""
    cli = import_module("packet_tracer_mcp.adapters.cli.service_qualification")
    code = cli.main(
        request_args(STAGE) + authorization_args(STAGE),
        environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        boundaries_factory=lambda _root: pytest.fail("no boundary may be built"),
    )
    assert code == 2
    assert _printed(capsys)["reason"] == "stage_requires_its_campaign"


# -- the use case: the waiver and the incarnation binding --------------------------------


def _use_case(tmp_path, authority, *, lifecycle=None):
    require_node()
    cli = import_module("packet_tracer_mcp.adapters.cli.service_qualification")
    engine = NodeEngine(tmp_path, **ENGINE)
    try:
        overrides = {"repository": lambda: UNPUBLISHED}
        if lifecycle is not None:
            overrides["diagnostic_lifecycle"] = lifecycle
        boundaries = dataclasses.replace(
            simulated_boundaries(tmp_path, NodeEngineTransport(engine), **overrides),
            campaign_source_authority=authority,
        )
        request = cli._request(
            request_args(STAGE) + authorization_args(STAGE, attempt_id=ATTEMPT)
        )
        return qualify_server_services(
            request,
            boundaries,
            experimental_capabilities=frozenset(
                stage_definition(STAGE).experimental_capabilities
            ),
        ), engine.snapshot()
    finally:
        engine.close()


def _authority(**overrides) -> CampaignQualificationAuthority:
    values = {
        "campaign_id": DHCP_FASTLOOP_CAMPAIGN.campaign_id,
        "episode": 1,
        "attempt_id": ATTEMPT,
        "authorization_id": f"TD-{STAGE}-simulated",
        "sha": SIM_SHA,
        "tree": SIM_TREE,
        "process_incarnation": SIM_PROCESS_INCARNATION,
    }
    values.update(overrides)
    return CampaignQualificationAuthority(**values)


def test_without_campaign_authority_an_unpublished_head_is_refused(tmp_path):
    """Publication stays required wherever no validated authority exists."""
    result, snapshot = _use_case(tmp_path, None)
    subjects = {item.subject for item in result.refusals}
    assert RefusalSubject.REPOSITORY_UPSTREAM in subjects
    assert snapshot["devices"] == []


@pytest.mark.parametrize(
    "override",
    [
        {"attempt_id": "e" * 32},
        {"authorization_id": "another"},
        {"sha": "d" * 40},
        {"tree": "d" * 40},
        {"episode": 0},
    ],
    ids=["attempt", "authorization", "sha", "tree", "episode"],
)
def test_an_authority_for_anything_else_waives_nothing(tmp_path, override):
    """It names exactly one attempt, authorization, HEAD and tree, or refuses."""
    result, snapshot = _use_case(tmp_path, _authority(**override))
    assert [item.subject for item in result.refusals] == [RefusalSubject.AUTHORIZATION]
    assert snapshot["devices"] == []


def test_another_incarnation_at_the_launched_pid_is_refused(tmp_path):
    """The launch record pinned one process; a reused PID is not it."""
    other = lambda _deadline=None: DiagnosticLifecycleObservation(  # noqa: E731
        process_id=SIM_PROCESS_ID,
        process_path=SIM_PROCESS_PATH,
        product_version="9.0.1.0858",
        process_incarnation="2026-09-24T00:00:00.0000000+00:00",
    )
    result, snapshot = _use_case(tmp_path, _authority(), lifecycle=other)
    assert RefusalSubject.PROCESS_INSTANCE in {item.subject for item in result.refusals}
    assert snapshot["devices"] == []
