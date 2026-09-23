"""LIVE source and receiver identity are read before any transport exists."""

from __future__ import annotations

from pathlib import Path

import pytest

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)


class _Isolation:
    isolated = True


def _source():
    return RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head="a" * 40,
        tree="b" * 40,
        clean=True,
        upstream_head="a" * 40,
    )


def test_ci_mismatch_stops_before_process_or_mailbox_read(tmp_path: Path):
    """A foreign green run cannot advance to receiver binding."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import (
        phase_preflight,
    )

    def forbidden(_deadline):
        raise AssertionError("lifecycle must not be read after CI refusal")

    result = phase_preflight(
        tmp_path,
        ci_run_id=42,
        isolation_reader=lambda _root: _Isolation(),
        source_reader=lambda _root: _source(),
        ci_reader=lambda _run, _sha, _root: (None, ("ci_head_mismatch",)),
        lifecycle_reader=forbidden,
    )

    assert result.findings == ("ci_head_mismatch",)
    assert result.process is None


def test_preflight_refuses_foreign_process_build(tmp_path: Path):
    """A complete but wrong-build lifecycle reading is not an admission."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import (
        phase_preflight,
    )
    from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
        ExactCiEvidence,
    )

    process = DiagnosticLifecycleObservation(
        process_id=123,
        process_path="C:\\PacketTracer.exe",
        process_incarnation="2026-09-23T00:00:00Z",
        product_version="8.0.0",
    )
    result = phase_preflight(
        tmp_path,
        ci_run_id=42,
        isolation_reader=lambda _root: _Isolation(),
        source_reader=lambda _root: _source(),
        ci_reader=lambda _run, _sha, _root: (
            ExactCiEvidence(42, "a" * 40, "https://example.test/42", ("six",)),
            (),
        ),
        lifecycle_reader=lambda _deadline: process,
    )

    assert "packet_tracer_build_mismatch" in result.findings


def test_phase_binding_reserves_once_and_checks_receiver_before_each_dispatch(
    tmp_path: Path,
):
    """The temporary channel cannot outlive its exact campaign claim."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import (
        PhasePreflight,
        bind_live_phase,
    )
    from packet_tracer_mcp.application.use_cases.server_pt_phase_grant import (
        derive_server_pt_phase_grant,
    )
    from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
        ExactCiEvidence,
    )
    from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
        FileCampaignCoordinator,
    )
    from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
        ServerPtCommissioningStore,
    )

    source = _source()
    process = DiagnosticLifecycleObservation(
        process_id=123,
        process_path="C:\\PacketTracer.exe",
        process_incarnation="2026-09-23T00:00:00Z",
        product_version="9.0.1.0858",
    )
    ci = ExactCiEvidence(42, "a" * 40, "https://example.test/42", ("six",))
    attempt = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
    grant = derive_server_pt_phase_grant(
        "prequalification", attempt, source, process, ci
    )
    preflight = PhasePreflight(source=source, ci=ci, process=process)
    store = ServerPtCommissioningStore(tmp_path)
    coordinator = FileCampaignCoordinator(tmp_path / "campaign")

    class Receiver:
        mode = "handle_bound"

        def __init__(self):
            self.reads = 0

        def observe(self, _deadline):
            self.reads += 1
            return process

        def close(self):
            pass

    class Bridge:
        def __init__(self):
            self.calls = 0

        def pt_alive(self):
            return True

        def send(self, _script):
            self.calls += 1
            return True

    receiver = Receiver()
    bridge = Bridge()
    with bind_live_phase(
        preflight,
        grant,
        store=store,
        coordinator=coordinator,
        receiver_binder=lambda _process, _deadline: receiver,
        bridge_factory=lambda: bridge,
    ) as bound:
        assert store.load_phase_grant(attempt, "prequalification") == grant
        assert bound.channel.send("one guarded effect") is True
        assert receiver.reads == 1
        assert bridge.calls == 1
    assert bound.release_findings == ()
    assert not (tmp_path / "campaign" / "campaign.lock").exists()

    from packet_tracer_mcp.infrastructure.execution.server_pt_phase_channel import (
        PhaseAllowanceExhausted,
    )

    now = [0.0]

    def slow_bind(_process, _deadline):
        now[0] = 301.0
        return Receiver()

    slow_root = tmp_path / "slow"
    slow_root.mkdir()
    with pytest.raises(PhaseAllowanceExhausted, match="binding"):
        bind_live_phase(
            preflight,
            grant,
            store=ServerPtCommissioningStore(slow_root),
            coordinator=FileCampaignCoordinator(slow_root / "campaign"),
            receiver_binder=slow_bind,
            bridge_factory=lambda: bridge,
            clock=lambda: now[0],
        )
    assert bridge.calls == 1
