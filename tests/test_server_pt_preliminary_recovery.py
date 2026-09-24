"""The operator's one no-contact C31 preliminary recovery stays narrow."""

from __future__ import annotations

import hashlib
import json
import time
from contextlib import nullcontext
from importlib import import_module
from pathlib import Path

import pytest

from packet_tracer_mcp.adapters.cli.server_pt_commissioning import (
    _prequalification_recovery_findings,
)
from packet_tracer_mcp.application.use_cases.server_pt_phase_grant import (
    derive_server_pt_phase_grant,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
    ExactCiEvidence,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)

FIRST = "979b4636d50290d199e8ea0f95eddab3"
SECOND = "5b09a9c35fd572f00945bdb18040d2fb"
THIRD = "b" * 32
OLD_PROCESS = "2026-09-23T18:55:33.5209275-05:00"
NEW_PROCESS = "2026-09-24T08:00:00.0000000-05:00"


def _seed_first(root: Path, *, operations: int = 0):
    store = ServerPtCommissioningStore(root)
    source = RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head="a" * 40,
        tree="b" * 40,
        clean=True,
        upstream_head="a" * 40,
    )
    process = DiagnosticLifecycleObservation(
        process_id=17620,
        process_path="C:\\PacketTracer.exe",
        process_incarnation=OLD_PROCESS,
        product_version="9.0.1.0858",
    )
    ci = ExactCiEvidence(42, source.head, "https://example.test/42", ("six",))
    store.save_phase_grant(
        FIRST,
        derive_server_pt_phase_grant("prequalification", FIRST, source, process, ci),
    )
    status = {
        "attempt_id": FIRST,
        "phase": "prequalification",
        "outcome": "stopped",
        "reason": "prequalification_boundary:ValueError",
        "operations_used": operations,
    }
    path = store.save_phase_status(FIRST, "prequalification", status)
    store.refresh_index()
    store.save_archive_admission(FIRST, "prequalification")
    store.refresh_index()
    return store, hashlib.sha256(path.read_bytes()).hexdigest()


def test_one_indexed_zero_contact_preliminary_can_recover(tmp_path: Path):
    """An indexed first grant with no dispatched work allows the fixed second ID."""
    store, digest = _seed_first(tmp_path)

    assert (
        _prequalification_recovery_findings(
            store,
            SECOND,
            first_attempt_id=FIRST,
            first_status_sha256=digest,
            new_process_incarnation=NEW_PROCESS,
        )
        == ()
    )
    assert store.prequalification_attempt_ids() == (FIRST,)
    assert store.setup_attempt_ids() == ()


@pytest.mark.parametrize(
    ("operations", "new_process", "wrong_digest"),
    [
        (1, NEW_PROCESS, False),
        (0, OLD_PROCESS, False),
        (0, NEW_PROCESS, True),
    ],
)
def test_recovery_refuses_contact_reuse_or_changed_authority(
    tmp_path: Path, operations: int, new_process: str, wrong_digest: bool
):
    """Prior contact, an old process or altered source bytes refuse recovery."""
    store, digest = _seed_first(tmp_path, operations=operations)

    assert _prequalification_recovery_findings(
        store,
        SECOND,
        first_attempt_id=FIRST,
        first_status_sha256="0" * 64 if wrong_digest else digest,
        new_process_incarnation=new_process,
    )


def test_recovery_refuses_replay_and_third_preliminary(tmp_path: Path):
    """The first ID cannot replay and no third reservation is admissible."""
    store, digest = _seed_first(tmp_path)
    assert _prequalification_recovery_findings(
        store,
        FIRST,
        first_attempt_id=FIRST,
        first_status_sha256=digest,
        new_process_incarnation=NEW_PROCESS,
    )
    assert _prequalification_recovery_findings(
        store,
        THIRD,
        first_attempt_id=FIRST,
        first_status_sha256=digest,
        new_process_incarnation=NEW_PROCESS,
    )

    store.save_phase_status(
        SECOND,
        "prequalification",
        {"attempt_id": SECOND, "phase": "prequalification", "outcome": "stopped"},
    )
    store.refresh_index()
    assert _prequalification_recovery_findings(
        store,
        THIRD,
        first_attempt_id=FIRST,
        first_status_sha256=digest,
        new_process_incarnation=NEW_PROCESS,
    )


def test_recovery_refuses_missing_archive_or_raw_journal(tmp_path: Path):
    """Missing or contradictory original answers fail closed."""
    store, digest = _seed_first(tmp_path)
    store.journal_path_for(FIRST, "prequalification").write_text(
        '{"request": 1}\n', encoding="utf-8"
    )
    store.refresh_index()
    assert _prequalification_recovery_findings(
        store,
        SECOND,
        first_attempt_id=FIRST,
        first_status_sha256=digest,
        new_process_incarnation=NEW_PROCESS,
    )

    missing_store = ServerPtCommissioningStore(tmp_path / "missing")
    assert _prequalification_recovery_findings(
        missing_store,
        SECOND,
        first_attempt_id=FIRST,
        first_status_sha256=digest,
        new_process_incarnation=NEW_PROCESS,
    )


def test_cli_recovery_reaches_only_the_new_preliminary_grant(
    tmp_path: Path, monkeypatch, capsys
):
    """The real CLI/store path admits the fixed fresh ID before a fake PT seam."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import PhasePreflight
    from packet_tracer_mcp.application.use_cases.prequalify_server_pt import (
        ServerPtPrequalificationResult,
    )

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    store, digest = _seed_first(tmp_path)
    monkeypatch.setattr(cli, "_RECOVERY_FIRST_STATUS_SHA256", digest)
    charter = tmp_path / "charter.md"
    charter.write_text("operator charter", encoding="utf-8")
    monkeypatch.setattr(
        cli, "CHARTER_SHA256", hashlib.sha256(charter.read_bytes()).hexdigest()
    )
    source = RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head="a" * 40,
        tree="b" * 40,
        clean=True,
        upstream_head="a" * 40,
    )
    process = DiagnosticLifecycleObservation(
        process_id=20000,
        process_path="C:\\PacketTracer.exe",
        process_incarnation=NEW_PROCESS,
        product_version="9.0.1.0858",
    )
    ci = ExactCiEvidence(42, source.head, "https://example.test/42", ("six",))
    store.save_process_launch(
        SECOND,
        {
            "pid": process.process_id,
            "process_path": process.process_path,
            "process_incarnation": process.process_incarnation,
            "created_by_campaign": True,
            "workspace_kind": "disposable_declared",
            "launch_method": "Start-Process",
            "source_sha": source.head,
            "source_tree": source.tree,
        },
    )
    store.refresh_index()
    monkeypatch.setattr(
        cli,
        "phase_preflight",
        lambda *_args, **_kwargs: PhasePreflight(source, ci, process),
    )
    entered = []

    class FakeChannel:
        started = time.monotonic()
        max_seconds = 300
        used_operations = 0
        cleanup_scope = staticmethod(nullcontext)
        authority = staticmethod(lambda: ())

    class FakeBound:
        channel = FakeChannel()
        release_findings = ()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def bind(_preflight, grant, *, store):
        store.save_phase_grant(SECOND, grant)
        entered.append(grant)
        return FakeBound()

    monkeypatch.setattr(cli, "bind_live_phase", bind)
    monkeypatch.setattr(
        cli,
        "prequalify_server_pt",
        lambda *_args, **_kwargs: ServerPtPrequalificationResult(
            errors=["fake_external_boundary"]
        ),
    )
    assert (
        cli.main(
            [
                "--qualify",
                "--attempt",
                SECOND,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["outcome"] == "stopped"
    assert len(entered) == 1
    assert "zero_contact_prequalification_recovery" in entered[0].operator_extensions
    assert store.verify_index() == ()


def test_cli_recovery_id_refuses_without_original_archive(
    tmp_path: Path, monkeypatch, capsys
):
    """The fixed replacement ID cannot act as an ordinary first qualifier."""
    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "charter.md"
    charter.write_text("operator charter", encoding="utf-8")
    monkeypatch.setattr(
        cli, "CHARTER_SHA256", hashlib.sha256(charter.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(
        cli,
        "phase_preflight",
        lambda *_args, **_kwargs: pytest.fail("preflight must not run"),
    )

    assert (
        cli.main(
            [
                "--qualify",
                "--attempt",
                SECOND,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["reason"] == (
        "prequalification_recovery_unverified"
    )
    assert not (tmp_path / "data").exists()
