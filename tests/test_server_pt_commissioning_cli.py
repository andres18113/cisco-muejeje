"""Maintained prepare and inspect entry points use one declared checkout root."""

from __future__ import annotations

import json
from pathlib import Path

from packet_tracer_mcp.domain.models.plans import TopologyPlan

ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def test_prepare_persists_the_full_e4_input_and_inspects_from_another_cwd(
    tmp_path: Path, monkeypatch, capsys
):
    """The CLI exports exact E4 bytes under the governed root."""
    from packet_tracer_mcp.adapters.cli.server_pt_commissioning import main
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    root = tmp_path / "governed"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    env = {"PT_MCP_GOVERNED_ROOT": str(root)}

    assert main(["--prepare", "--attempt", ATTEMPT], environ=env) == 0
    prepared = json.loads(capsys.readouterr().out)
    bundle = ServerPtCommissioningStore(root).load_bundle(ATTEMPT)
    assert prepared["mode"] == "prepare"
    assert prepared["devices"] == 35
    assert prepared["links"] == 36
    assert prepared["topology_sha256"] == bundle.topology_sha256
    assert len(TopologyPlan.model_validate_json(bundle.topology_json).devices) == 35

    assert main(["--inspect", "--attempt", ATTEMPT], environ=env) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["bundle_sha256"] == prepared["bundle_sha256"]


def test_prepare_refuses_a_non_campaign_client_count_without_writing(
    tmp_path: Path, capsys
):
    """The charter's LIVE producer cannot silently select a different size."""
    from packet_tracer_mcp.adapters.cli.server_pt_commissioning import main

    env = {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}
    assert (
        main(["--prepare", "--attempt", ATTEMPT, "--clients", "20"], environ=env) == 2
    )
    assert json.loads(capsys.readouterr().out)["outcome"] == "refused"
    assert not (tmp_path / "data").exists()


def test_qualify_requires_exact_ci_and_charter_before_contact(tmp_path: Path, capsys):
    """A bare effect request cannot create a phase record or mailbox command."""
    from packet_tracer_mcp.adapters.cli.server_pt_commissioning import main

    env = {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}
    assert main(["--qualify", "--attempt", ATTEMPT], environ=env) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["outcome"] == "refused"
    assert not (tmp_path / "data").exists()


def test_qualify_refuses_a_different_parent_charter_before_contact(
    tmp_path: Path, capsys
):
    """A new file with a new digest is not an expanded operator grant."""
    from packet_tracer_mcp.adapters.cli.server_pt_commissioning import main

    charter = tmp_path / "other.md"
    charter.write_text("different scope", encoding="utf-8")
    env = {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}

    assert (
        main(
            [
                "--qualify",
                "--attempt",
                ATTEMPT,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
            ],
            environ=env,
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["reason"] == "charter_digest_mismatch"
    assert not (tmp_path / "data").exists()


def test_setup_refuses_without_retained_prequalification(
    tmp_path: Path, capsys, monkeypatch
):
    """The campaign cannot dispatch E4 from a bare charter and attempt ID."""
    import hashlib
    from importlib import import_module

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "charter.md"
    charter.write_text("activated test charter", encoding="utf-8")
    monkeypatch.setattr(
        cli, "CHARTER_SHA256", hashlib.sha256(charter.read_bytes()).hexdigest()
    )

    assert (
        cli.main(
            [
                "--setup",
                "--attempt",
                ATTEMPT,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        )
        == 2
    )
    assert (
        json.loads(capsys.readouterr().out)["reason"]
        == "setup_input_missing:ValueError"
    )


def test_cleanup_refuses_without_immutable_setup_ownership(
    tmp_path: Path, capsys, monkeypatch
):
    """A bare attempt ID cannot authorize device removal."""
    import hashlib
    from importlib import import_module

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "charter.md"
    charter.write_text("activated test charter", encoding="utf-8")
    monkeypatch.setattr(
        cli, "CHARTER_SHA256", hashlib.sha256(charter.read_bytes()).hexdigest()
    )

    assert (
        cli.main(
            [
                "--cleanup",
                "--attempt",
                ATTEMPT,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        )
        == 2
    )
    assert (
        json.loads(capsys.readouterr().out)["reason"]
        == "cleanup_input_missing:ValueError"
    )


def test_acceptance_refuses_without_a_completed_setup(
    tmp_path: Path, capsys, monkeypatch
):
    """A charter alone cannot reach the existing product coordinator."""
    import hashlib
    from importlib import import_module

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "charter.md"
    charter.write_text("activated test charter", encoding="utf-8")
    monkeypatch.setattr(
        cli, "CHARTER_SHA256", hashlib.sha256(charter.read_bytes()).hexdigest()
    )

    assert (
        cli.main(
            [
                "--accept",
                "--attempt",
                ATTEMPT,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        )
        == 2
    )
    assert (
        json.loads(capsys.readouterr().out)["reason"]
        == "acceptance_input_missing:ValueError"
    )


def test_new_nonce_cannot_repeat_the_two_preliminary_mutations(
    tmp_path: Path, capsys, monkeypatch
):
    """One sealed preliminary grant spends the campaign's extra qualifier."""
    import hashlib
    from importlib import import_module

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

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "charter.md"
    charter.write_text("activated test charter", encoding="utf-8")
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
        process_id=123,
        process_path="C:\\PacketTracer.exe",
        process_incarnation="2026-09-23T00:00:00Z",
        product_version="9.0.1.0858",
    )
    ci = ExactCiEvidence(42, "a" * 40, "https://example.test/42", ("six",))
    store = ServerPtCommissioningStore(tmp_path)
    store.save_phase_grant(
        ATTEMPT,
        derive_server_pt_phase_grant("prequalification", ATTEMPT, source, process, ci),
    )

    other = ATTEMPT[:12] + "f" * 20
    assert (
        cli.main(
            [
                "--qualify",
                "--attempt",
                other,
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
        "prequalification_already_reserved"
    )


def test_process_evidence_modes_require_original_local_capture(
    tmp_path: Path, capsys, monkeypatch
):
    """A bare nonce cannot claim launch ownership or a graceful process exit."""
    import hashlib
    from importlib import import_module

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "charter.md"
    charter.write_text("activated test charter", encoding="utf-8")
    monkeypatch.setattr(
        cli, "CHARTER_SHA256", hashlib.sha256(charter.read_bytes()).hexdigest()
    )
    env = {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}

    assert (
        cli.main(
            [
                "--record-launch",
                "--attempt",
                ATTEMPT,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
            ],
            environ=env,
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["reason"] == "launch_evidence_required"
    assert (
        cli.main(
            [
                "--record-exit",
                "--attempt",
                ATTEMPT,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
            ],
            environ=env,
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["reason"] == "close_evidence_required"


def test_record_launch_seals_exact_observed_process_without_pt_contact(
    tmp_path: Path, capsys, monkeypatch
):
    """The CLI retains creation provenance and a verified source-byte index."""
    import hashlib
    from importlib import import_module

    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import PhasePreflight
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

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "charter.md"
    charter.write_text("activated test charter", encoding="utf-8")
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
        process_id=123,
        process_path="C:\\PacketTracer.exe",
        process_incarnation="2026-09-23T00:00:00Z",
        product_version="9.0.1.0858",
    )
    ci = ExactCiEvidence(42, "a" * 40, "https://example.test/42", ("six",))
    monkeypatch.setattr(
        cli,
        "phase_preflight",
        lambda *_args, **_kwargs: PhasePreflight(source, ci, process),
    )
    captured = tmp_path / "launch-capture.json"
    captured.write_text(
        json.dumps(
            {
                "pid": 123,
                "process_path": process.process_path,
                "process_incarnation": process.process_incarnation,
                "created_by_campaign": True,
                "workspace_kind": "disposable_declared",
                "launch_method": "Start-Process",
            }
        ),
        encoding="utf-8",
    )

    assert (
        cli.main(
            [
                "--record-launch",
                "--attempt",
                ATTEMPT,
                "--ci-run",
                "42",
                "--charter",
                str(charter),
                "--launch-evidence",
                str(captured),
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(tmp_path)},
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["outcome"] == "owned"
    store = ServerPtCommissioningStore(tmp_path)
    assert store.load_process_launch(ATTEMPT)["pid"] == 123
    assert store.verify_index() == ()


def test_third_attempt_is_refused_before_any_process_read(
    tmp_path: Path, capsys, monkeypatch
):
    """Two prior setup reservations consume the whole C31 campaign ceiling."""
    import hashlib
    from importlib import import_module

    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        CAMPAIGN_ID,
    )

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "charter.md"
    charter.write_text("activated test charter", encoding="utf-8")
    monkeypatch.setattr(
        cli, "CHARTER_SHA256", hashlib.sha256(charter.read_bytes()).hexdigest()
    )
    for name in ("1" * 32, "2" * 32):
        directory = tmp_path / "data" / "commissioning" / CAMPAIGN_ID / name
        directory.mkdir(parents=True)
        (directory / "setup-grant.json").write_text("{}", encoding="utf-8")

    assert (
        cli.main(
            [
                "--setup",
                "--attempt",
                ATTEMPT,
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
        "campaign_attempt_allowance_exhausted"
    )
