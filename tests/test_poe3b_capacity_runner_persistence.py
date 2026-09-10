"""PoE-3B safety admission, snapshot staging and authority promotion."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.poe3b_capacity_runner_helpers import (
    empty_file_ledger,
    facts,
    packet_tracer_processes,
    qualification_inputs,
    runner,
)


def test_ephemeral_evidence_carries_acquired_facts_and_explicit_file_ledgers(
    runner,
):
    baseline, restoration, final = facts()
    file_operation_ledger = empty_file_ledger(runner)
    evidence = runner.ephemeral_safety_for(
        baseline,
        restoration,
        final,
        [],
        file_operation_ledger=file_operation_ledger,
    )
    assert runner.validate_live_session_positive_admission(evidence).is_valid
    assert evidence.authorized_file_operations == ()
    assert evidence.attempted_file_operations == ()
    assert evidence.denied_file_operations == ()
    assert evidence.invoked_file_operations == ()
    assert evidence.completed_file_operations == ()
    assert evidence.indeterminate_file_operations == ()
    assert evidence.packet_tracer_pids_before == (42,)
    assert evidence.packet_tracer_pids_after == (42,)
    assert evidence.source_tree_before == "c" * 40
    assert not any(
        "canonical" in key or "disposable" in key
        for key in evidence.model_dump()
    )
    final["processes"] = packet_tracer_processes(main_pid=99, helper_pid=100)
    changed = runner.ephemeral_safety_for(
        baseline,
        restoration,
        final,
        [],
        file_operation_ledger=file_operation_ledger,
    )
    assert changed.packet_tracer_pids_after == (99,)
    assert not runner.validate_live_session_positive_admission(changed).is_valid


def test_ephemeral_continuity_tracks_primary_pid_and_retains_helper_raw(
    runner,
) -> None:
    baseline, restoration, final = facts()
    baseline["processes"] = packet_tracer_processes()
    final["processes"] = packet_tracer_processes()

    evidence = runner.ephemeral_safety_for(
        baseline,
        restoration,
        final,
        [],
        file_operation_ledger=empty_file_ledger(runner),
    )

    assert len(baseline["processes"]) == len(final["processes"]) == 2
    assert evidence.packet_tracer_pids_before == (42,)
    assert evidence.packet_tracer_pids_after == (42,)
    assert evidence.crash_detected is False
    assert runner.validate_live_session_positive_admission(evidence).is_valid


def test_ephemeral_save_attempt_uses_governed_boundary_and_blocks_admission(
    runner,
) -> None:
    baseline, restoration, final = facts()
    session = runner.PacketTracerPoE3BSession(
        "offline-save-attempt",
        switch_ports=("FastEthernet0/1",),
        transport=SimpleNamespace(),
    )
    dispatched: list[str] = []

    with pytest.raises(RuntimeError, match="file operation denied"):
        session.attempt_workspace_file_operation(
            "save",
            lambda: dispatched.append("save reached Packet Tracer"),
        )

    evidence = runner.ephemeral_safety_for(
        baseline,
        restoration,
        final,
        [],
        file_operation_ledger=session.file_operation_ledger(),
    )
    ledger = session.file_operation_ledger()

    assert ledger.authorized_operations == ()
    assert ledger.attempted_operations == ("save",)
    assert ledger.denied_operations == ("save",)
    assert ledger.invoked_operations == ()
    assert ledger.completed_operations == ()
    assert ledger.indeterminate_operations == ()
    assert dispatched == []
    assert evidence.authorized_file_operations == ledger.authorized_operations
    assert evidence.attempted_file_operations == ("save",)
    assert evidence.denied_file_operations == ("save",)
    assert evidence.invoked_file_operations == ()
    assert evidence.completed_file_operations == ()
    assert evidence.indeterminate_file_operations == ()
    assert evidence.positive_claim_allowed is False
    assert not runner.validate_live_session_positive_admission(evidence).is_valid


def test_transport_failure_with_same_pid_is_unhealthy_but_not_a_crash(
    runner,
) -> None:
    baseline, restoration, final = facts()
    final["transport_problems"] = ["synthetic mailbox timeout"]

    evidence = runner.ephemeral_safety_for(
        baseline,
        restoration,
        final,
        [],
        file_operation_ledger=empty_file_ledger(runner),
    )

    assert evidence.runtime_healthy is False
    assert evidence.crash_detected is False
    assert not runner.validate_live_session_positive_admission(evidence).is_valid


@pytest.mark.parametrize(
    "processes_after,expected_crash",
    [
        ([], True),
        (packet_tracer_processes(main_pid=99, helper_pid=100), True),
        (None, None),
    ],
    ids=["pid-disappeared", "pid-changed", "process-evidence-unavailable"],
)
def test_crash_state_comes_only_from_process_continuity(
    runner,
    processes_after,
    expected_crash,
) -> None:
    baseline, restoration, final = facts()
    if processes_after is None:
        final.pop("processes")
    else:
        final["processes"] = processes_after

    evidence = runner.ephemeral_safety_for(
        baseline,
        restoration,
        final,
        [],
        file_operation_ledger=empty_file_ledger(runner),
    )

    assert evidence.runtime_healthy is False
    assert evidence.crash_detected is expected_crash
    assert not runner.validate_live_session_positive_admission(evidence).is_valid


@pytest.mark.parametrize(
    "area,key",
    [
        ("baseline", "environment"),
        ("baseline", "inventory_fingerprint"),
        ("baseline", "processes"),
        ("baseline", "bridge_healthy"),
        ("baseline", "mailbox_entries"),
        ("baseline", "source_branch"),
        ("baseline", "local_head"),
        ("baseline", "source_tree"),
        ("baseline", "worktree_clean"),
        ("restoration", "environment_after"),
        ("restoration", "inventory_fingerprint_after"),
        ("restoration", "inventory_restored"),
        ("restoration", "fixture_removed"),
        ("restoration", "power_inline_auto_proven"),
        ("restoration", "deleted"),
        ("restoration", "created"),
        ("restoration", "attempted"),
        ("safety", "processes"),
        ("safety", "bridge_healthy"),
        ("safety", "mailbox_entries"),
        ("safety", "source_branch"),
        ("safety", "source_head"),
        ("safety", "source_tree"),
        ("safety", "worktree_clean"),
        ("safety", "transport_problems"),
    ],
)
def test_missing_boundary_never_constructs_positive_result(
    runner,
    monkeypatch,
    area,
    key,
):
    inputs = qualification_inputs(runner)
    inputs[area].pop(key)

    def forbidden(*args, **kwargs):
        pytest.fail("Incomplete run crossed the positive result boundary")

    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError):
        runner.build_qualification_snapshot(**inputs)


def test_snapshot_build_requires_the_observed_file_operation_ledger(
    runner,
    monkeypatch,
) -> None:
    inputs = qualification_inputs(runner)
    inputs["file_operation_ledger"] = None

    def forbidden(*args, **kwargs):
        pytest.fail("Missing PT-file ledger crossed the snapshot boundary")

    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError, match="file-operation ledger"):
        runner.build_qualification_snapshot(**inputs)


@pytest.mark.parametrize(
    "failure",
    ["schema", "safety", "problems", "plan", "capture", "cleanup"],
)
def test_rejected_scope_or_safety_never_builds_a_snapshot(
    runner,
    monkeypatch,
    failure,
):
    inputs = qualification_inputs(runner)
    if failure == "schema":
        monkeypatch.setattr(
            runner,
            "decode_poe_pse_multi_port_delivery_scope",
            lambda *args, **kwargs: None,
        )
    elif failure == "safety":
        inputs["safety"]["mailbox_entries"] = ("req_foreign.js",)
    elif failure == "problems":
        inputs["problems"] = ["transport failed"]
    elif failure == "plan":
        inputs["scope"] = replace(
            inputs["scope"],
            simultaneous_active_ports=1,
        )
    elif failure == "capture":
        inputs["scope"] = replace(
            inputs["scope"],
            captures=inputs["scope"].captures[:2],
        )
    else:
        inputs["restoration"]["deleted"] = ["SW"]

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected run crossed the positive snapshot boundary")

    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError):
        runner.build_qualification_snapshot(**inputs)


def test_snapshot_is_built_only_after_both_validators_accept(
    runner,
    monkeypatch,
):
    inputs = qualification_inputs(runner)
    events = []
    validate = runner.validate_live_session_positive_admission
    decode = runner.decode_poe_pse_multi_port_delivery_scope
    result_type = runner.CapabilityProbeResult

    def safety(evidence):
        result = validate(evidence)
        if result.is_valid:
            events.append("safety")
        return result

    def schema(*args, **kwargs):
        result = decode(*args, **kwargs)
        if result is not None:
            events.append("schema")
        return result

    def positive(**kwargs):
        assert "safety" in events and "schema" in events
        events.append("positive")
        return result_type(**kwargs)

    monkeypatch.setattr(runner, "validate_live_session_positive_admission", safety)
    monkeypatch.setattr(
        runner,
        "decode_poe_pse_multi_port_delivery_scope",
        schema,
    )
    monkeypatch.setattr(runner, "CapabilityProbeResult", positive)

    snapshot = runner.build_qualification_snapshot(**inputs)

    assert events == ["safety", "schema", "positive"]
    probe = snapshot.session.results[0]
    assert probe.observed_value == 21
    assert probe.evidence_source is runner.EvidenceSource.CONTROLLED_PROBE
    safety_evidence = probe.context.live_session_safety
    assert safety_evidence.attempted_file_operations == ()
    assert safety_evidence.denied_file_operations == ()
    assert safety_evidence.invoked_file_operations == ()
    assert safety_evidence.completed_file_operations == ()
    assert safety_evidence.indeterminate_file_operations == ()
    assert probe.evidence() is not None


@pytest.mark.parametrize("area", ["baseline", "restoration"])
@pytest.mark.parametrize(
    "key",
    ["devices", "links", "saved_filename", "simulation_mode", "pt_version"],
)
def test_missing_environment_measurement_cannot_build_snapshot(
    runner,
    area,
    key,
):
    inputs = qualification_inputs(runner)
    env_key = "environment" if area == "baseline" else "environment_after"
    inputs[area][env_key].pop(key)

    def forbidden(*args, **kwargs):
        pytest.fail("Incomplete environment crossed snapshot gate")

    with pytest.raises(ValueError):
        runner.build_qualification_snapshot(**inputs)


def test_both_wrong_build_measurements_never_build_snapshot(runner):
    inputs = qualification_inputs(runner)
    inputs["baseline"]["environment"]["pt_version"] = "wrong"
    inputs["restoration"]["environment_after"]["pt_version"] = "wrong"
    with pytest.raises(ValueError):
        runner.build_qualification_snapshot(**inputs)


def test_staged_snapshot_is_not_enumerable_until_atomic_promotion(runner):
    inputs = qualification_inputs(runner)
    snapshot = runner.build_qualification_snapshot(**inputs)
    store = runner.CapabilitySnapshotStore(runner.ROOT / "capabilities")

    staged = store.stage_runtime(snapshot)

    assert store.list_runtime(snapshot.packet_tracer_version) == []
    assert not staged.target.exists()

    promoted = store.promote_runtime(staged)

    assert promoted == staged.target
    assert store.list_runtime(snapshot.packet_tracer_version) == [snapshot]


def test_runtime_promotion_rejects_a_changed_in_memory_stage(runner):
    inputs = qualification_inputs(runner)
    snapshot = runner.build_qualification_snapshot(**inputs)
    store = runner.CapabilitySnapshotStore(runner.ROOT / "capabilities")
    staged = store.stage_runtime(snapshot)
    changed = replace(
        staged,
        payload=staged.payload.replace("offline", "altered", 1),
    )

    with pytest.raises(ValueError, match="identity changed"):
        store.promote_runtime(changed)

    assert store.list_runtime(snapshot.packet_tracer_version) == []


@pytest.mark.parametrize("failure_target", ["raw", "manifest"])
def test_evidence_publication_failure_leaves_no_new_runtime_authority(
    runner,
    monkeypatch,
    failure_target,
) -> None:
    inputs = qualification_inputs(runner)
    snapshot = runner.build_qualification_snapshot(**inputs)
    artifacts = inputs["artifacts"]
    raw_files = {"auto_1.txt": b"measured"}
    if failure_target == "raw":
        raw_files = {"blocked.txt": b"measured"}
        (artifacts.directory / "blocked.txt").mkdir()
    else:
        (artifacts.directory / "evidence.json").mkdir()
    execution = runner.GovernedQualificationExecution(
        fixture_evidence={},
        captures=[],
        pse_captures=list(inputs["scope"].captures),
        problems=[],
        restoration=inputs["restoration"],
        safety=inputs["safety"],
        raw_files=raw_files,
        completed_at_utc="2026-09-10T18:00:00Z",
        file_operation_ledger=inputs["file_operation_ledger"],
        scope=inputs["scope"],
        dimensions=runner.encode_poe_pse_multi_port_dimensions(inputs["scope"]),
        snapshot=snapshot,
    )

    monkeypatch.setattr(
        runner,
        "parse_args",
        lambda: SimpleNamespace(model="3560-24PS", qualification_id="offline"),
    )
    isolation = SimpleNamespace(isolated=True, render=lambda: "ISOLATED")
    monkeypatch.setattr(
        runner,
        "ImportIsolationPreflight",
        lambda _root: SimpleNamespace(ensure_isolated=lambda: isolation),
    )
    monkeypatch.setattr(runner, "governed_plan", lambda _model: inputs["plan"])
    monkeypatch.setattr(
        runner,
        "source_baseline",
        lambda _plan: inputs["baseline"],
    )
    monkeypatch.setattr(runner, "prove_processes", packet_tracer_processes)
    monkeypatch.setattr(runner, "reserve_artifacts", lambda _identity: artifacts)
    session = SimpleNamespace(dispatches=[])
    monkeypatch.setattr(
        runner,
        "PacketTracerPoE3BSession",
        lambda *_args, **_kwargs: session,
    )

    def execute(**kwargs):
        # Old code passed a store here and made it authoritative too early.
        if "store" in kwargs:
            execution.snapshot_path = kwargs["store"].save_runtime(snapshot)
        return execution

    monkeypatch.setattr(runner, "execute_governed_qualification", execute)

    with pytest.raises(OSError):
        runner.main()

    store = runner.CapabilitySnapshotStore(
        runner.resolve_within(runner.ROOT, Path("data") / "capabilities"),
    )
    assert store.list_runtime(inputs["plan"].packet_tracer_build) == []
