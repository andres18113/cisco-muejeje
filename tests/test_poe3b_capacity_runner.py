"""Offline runner boundaries. No execute path, PT, bridge or mailbox access."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    module = importlib.import_module("poe3a_pse_live")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def empty_file_ledger(runner):
    session = runner.PacketTracerPoE3BSession(
        "offline-ledger",
        switch_ports=("FastEthernet0/1",),
        transport=SimpleNamespace(),
    )
    return session.file_operation_ledger()


@pytest.mark.parametrize("argv", [[], ["--execute"], ["--model", "3560-24PS"],
    ["--execute", "--model", "3560-24PS"],
    ["--model", "3560-24PS", "--qualification-id", "offline"],
    ["--execute", "--model", "unknown", "--qualification-id", "offline"],
    ["--execute", "--model", "3560-24PS", "--qualification-id", "../escape"],
    ["--execute", "--model", "3560-24PS", "--qualification-id", "x", "--ios", "show run"],
])
def test_parser_refuses_incomplete_or_ungoverned_requests(runner, argv):
    with pytest.raises((SystemExit, ValueError)):
        runner.parse_args(argv)


@pytest.mark.parametrize("model,count,first,last", [
    ("3560-24PS", 21, "FastEthernet0/1", "FastEthernet0/21"),
    ("3650-24PS", 11, "GigabitEthernet1/0/2", "GigabitEthernet1/0/13"),
])
def test_plan_is_derived_with_exact_count_and_order(runner, model, count, first, last):
    args = runner.parse_args(["--execute", "--model", model, "--qualification-id", "offline"])
    plan = runner.governed_plan(args.model)
    assert plan.simultaneous_active_ports == count == len(plan.bindings)
    assert (plan.bindings[0].switch_port, plan.bindings[-1].switch_port) == (first, last)


def test_experiment_applies_ordered_ports_and_observes_whole_tuple_twice(runner):
    ports = ("FastEthernet0/2", "FastEthernet0/1")
    configured, observed = [], []
    class Done(Exception):
        pass
    def observe(device, requested, label):
        observed.append(requested)
        if len(observed) == 2:
            raise Done
        return SimpleNamespace(command_result=None)
    transport = SimpleNamespace(
        apply_inline_mode=lambda device, requested, mode: configured.append(
            (device, requested, mode)
        ),
        capture_inline_status=observe,
    )
    session = runner.PacketTracerPoE3BSession(
        "offline", switch_ports=ports, transport=transport,
    )
    session.apply_inline_mode(runner.PoEInlineMode.NEVER)
    assert configured == [
        (session.switch_name, ports, runner.PoEInlineMode.NEVER),
    ]
    with pytest.raises(Done):
        session.capture_inline_status("NEVER")
        session.capture_inline_status("NEVER")
    assert observed == [ports, ports]


@pytest.mark.parametrize("ports", [
    (),
    ("FastEthernet0/1", "FastEthernet0/1"),
    ("FastEthernet0/1\nwrite memory",),
])
def test_experiment_rejects_empty_or_duplicate_ports(runner, ports):
    with pytest.raises(ValueError):
        runner.PacketTracerPoE3BSession(
            "offline", switch_ports=ports, transport=SimpleNamespace(),
        )


@pytest.mark.parametrize("model,count", [("3560-24PS", 21), ("3650-24PS", 11)])
def test_fixture_has_one_phone_and_link_per_governed_binding(runner, model, count):
    plan = runner.governed_plan(model)
    made, links = [], []
    class Device(SimpleNamespace):
        def model_dump(self, **kwargs):
            return vars(self)
    def create(model, name, ports, **kwargs):
        made.append((model, name, ports))
        return Device(model=model, name=name)
    def link(switch, port, phone, endpoint_port):
        links.append((port, endpoint_port))
        return Device(port=port)
    transport = SimpleNamespace(create_device=create, create_link=link)
    session = runner.PacketTracerPoE3BSession(
        "offline",
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        endpoint_role="PH",
        transport=transport,
    )
    session.create_fixture(plan.candidate_model, plan.bindings)
    assert len(made) == count + 1 and len(links) == count
    assert made[0] == (
        model, session.switch_name, tuple(b.switch_port for b in plan.bindings),
    )
    assert all(m[0] == "7960" and m[2] == ("Switch",) for m in made[1:])
    assert session.attempted_device_names == tuple(m[1] for m in made)
    assert session.created_device_names == session.attempted_device_names
    assert len(set(session.attempted_device_names)) == count + 1
    assert links == [(b.switch_port, "Switch") for b in plan.bindings]


def facts():
    env = dict(devices=0, links=0, saved_filename="", simulation_mode=False,
               pt_version="9.0.1.0858")
    baseline = dict(environment=env, inventory_fingerprint="a" * 64 + "|",
        source_branch="feature/runtime-ripv2", local_head="b" * 40,
        source_tree="c" * 40, worktree_clean=True,
        processes=packet_tracer_processes(),
        bridge_healthy=True, mailbox_entries=())
    restoration = dict(environment_after=deepcopy(env),
        inventory_fingerprint_after="a" * 64 + "|", inventory_restored=True,
        fixture_removed=True, power_inline_auto_proven=True,
        attempted=["SW", "PH"], created=["SW", "PH"], deleted=["PH", "SW"])
    final = dict(source_branch="feature/runtime-ripv2", source_head="b" * 40,
        source_tree="c" * 40, worktree_clean=True,
        processes=packet_tracer_processes(),
        bridge_healthy=True, mailbox_entries=(), transport_problems=[])
    return baseline, restoration, final


def packet_tracer_processes(*, main_pid=42, helper_pid=43):
    executable = r"C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe"
    return [
        dict(
            Name="PacketTracer.exe",
            ProcessId=main_pid,
            ParentProcessId=1,
            ExecutablePath=executable,
            CommandLine=f'"{executable}" ',
        ),
        dict(
            Name="PacketTracer.exe",
            ProcessId=helper_pid,
            ParentProcessId=main_pid,
            ExecutablePath=executable,
            CommandLine=f'"{executable}" --progress-bar-server',
        ),
    ]


def test_one_primary_packet_tracer_and_its_exact_helper_are_one_runtime_cohort(
    runner,
    monkeypatch,
) -> None:
    observed = packet_tracer_processes()
    monkeypatch.setattr(runner, "processes", lambda: observed)

    acquired = runner.prove_processes()

    assert acquired == observed
    assert runner.packet_tracer_primary_pids(acquired) == (42,)


@pytest.mark.parametrize("mutation", ["second-primary", "wrong-parent", "wrong-executable"])
def test_packet_tracer_process_cohort_rejects_unrelated_same_name_processes(
    runner,
    monkeypatch,
    mutation,
) -> None:
    observed = packet_tracer_processes()
    if mutation == "second-primary":
        observed.append(dict(observed[0], ProcessId=44))
    elif mutation == "wrong-parent":
        observed[1]["ParentProcessId"] = 999
    else:
        observed[1]["ExecutablePath"] = r"C:\Other\PacketTracer.exe"
    monkeypatch.setattr(runner, "processes", lambda: observed)

    with pytest.raises(RuntimeError, match="Packet Tracer process cohort"):
        runner.prove_processes()


def test_ephemeral_evidence_carries_acquired_facts_and_explicit_file_ledgers(runner):
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
    assert evidence.packet_tracer_pids_before == evidence.packet_tracer_pids_after == (42,)
    assert evidence.source_tree_before == "c" * 40
    assert not any("canonical" in key or "disposable" in key for key in evidence.model_dump())
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


def test_transport_failure_with_same_pid_is_unhealthy_but_not_a_crash(runner) -> None:
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
    "processes_after, expected_crash",
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


def typed_captures(runner, plan):
    return tuple(runner.PoEPseMultiPortCapture(label, mode, tuple(
        runner.PoEPseBindingCapture(b.switch_port, b.endpoint_model, b.endpoint_port,
            "on" if mode == "auto" else "absent", 10.0 if mode == "auto" else 0.0,
            mode == "auto", mode == "auto") for b in plan.bindings))
        for label, mode in (("AUTO_1", "auto"), ("NEVER", "never"), ("AUTO_2", "auto")))


def persist_inputs(runner):
    plan = runner.governed_plan("3560-24PS")
    baseline, restoration, final = facts()
    names = ["SW"] + ["PH" + str(i) for i in range(21)]
    restoration.update(attempted=names, created=names, deleted=list(reversed(names)))
    artifacts = runner.reserve_artifacts("offline")
    scope = runner.pse_scope_for(plan=plan, run_id=artifacts.run_id, observed_at="2026-09-09T18:00:00Z",
        captures=typed_captures(runner, plan), gates=tuple(sorted(runner.COMPLETENESS_KEYS)))
    return dict(plan=plan, scope=scope, artifacts=artifacts, baseline=baseline, restoration=restoration,
                safety=final, problems=[],
                file_operation_ledger=empty_file_ledger(runner))


@pytest.mark.parametrize("area,key", [
    ("baseline", "environment"), ("baseline", "inventory_fingerprint"),
    ("baseline", "processes"), ("baseline", "bridge_healthy"),
    ("baseline", "mailbox_entries"), ("baseline", "source_branch"),
    ("baseline", "local_head"), ("baseline", "source_tree"),
    ("baseline", "worktree_clean"),
    ("restoration", "environment_after"), ("restoration", "inventory_fingerprint_after"),
    ("restoration", "inventory_restored"), ("restoration", "fixture_removed"),
    ("restoration", "power_inline_auto_proven"), ("restoration", "deleted"),
    ("restoration", "created"), ("restoration", "attempted"),
    ("safety", "processes"), ("safety", "bridge_healthy"), ("safety", "mailbox_entries"),
    ("safety", "source_branch"), ("safety", "source_head"), ("safety", "source_tree"),
    ("safety", "worktree_clean"), ("safety", "transport_problems"),
])
def test_missing_boundary_never_constructs_positive_result_or_saves(runner, monkeypatch, area, key):
    inputs = persist_inputs(runner)
    inputs[area].pop(key)
    def forbidden(*args, **kwargs):
        pytest.fail("Incomplete run crossed the positive result/persistence boundary")
    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError):
        runner.persist_qualification(**inputs, store=SimpleNamespace(save_runtime=forbidden))


def test_persistence_requires_the_observed_file_operation_ledger(
    runner,
    monkeypatch,
) -> None:
    inputs = persist_inputs(runner)
    inputs["file_operation_ledger"] = None

    def forbidden(*args, **kwargs):
        pytest.fail("Missing PT-file ledger crossed the persistence boundary")

    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError, match="file-operation ledger"):
        runner.persist_qualification(
            **inputs,
            store=SimpleNamespace(save_runtime=forbidden),
        )


@pytest.mark.parametrize("failure", ["schema", "safety", "problems", "plan", "capture", "cleanup"])
def test_rejected_scope_or_safety_never_saves(runner, monkeypatch, failure):
    inputs = persist_inputs(runner)
    if failure == "schema":
        monkeypatch.setattr(runner, "decode_poe_pse_multi_port_delivery_scope", lambda *a, **kw: None)
    elif failure == "safety":
        inputs["safety"]["mailbox_entries"] = ("req_foreign.js",)
    elif failure == "problems":
        inputs["problems"] = ["transport failed"]
    elif failure == "plan":
        inputs["scope"] = replace(inputs["scope"], simultaneous_active_ports=1)
    elif failure == "capture":
        inputs["scope"] = replace(inputs["scope"], captures=inputs["scope"].captures[:2])
    else:
        inputs["restoration"]["deleted"] = ["SW"]
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected run crossed the positive result/persistence boundary")
    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError):
        runner.persist_qualification(**inputs, store=SimpleNamespace(save_runtime=forbidden))


def test_snapshot_saved_only_after_both_validators_accept(runner, monkeypatch):
    inputs = persist_inputs(runner)
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
    saved = []
    def save(snapshot):
        assert events.index("safety") < events.index("positive")
        assert events.index("schema") < events.index("positive")
        saved.append(snapshot)
        return Path("offline-snapshot.json")
    monkeypatch.setattr(runner, "validate_live_session_positive_admission", safety)
    monkeypatch.setattr(runner, "decode_poe_pse_multi_port_delivery_scope", schema)
    monkeypatch.setattr(runner, "CapabilityProbeResult", positive)
    snapshot, path = runner.persist_qualification(**inputs, store=SimpleNamespace(save_runtime=save))
    assert saved == [snapshot] and str(path) == "offline-snapshot.json"
    probe = snapshot.session.results[0]
    assert probe.observed_value == 21
    assert probe.evidence_source is runner.EvidenceSource.CONTROLLED_PROBE
    assert probe.context.live_session_safety.attempted_file_operations == ()
    assert probe.context.live_session_safety.denied_file_operations == ()
    assert probe.context.live_session_safety.invoked_file_operations == ()
    assert probe.context.live_session_safety.completed_file_operations == ()
    assert probe.context.live_session_safety.indeterminate_file_operations == ()
    assert probe.evidence() is not None


def measured_capture(runner, plan, label="AUTO_1"):
    mode = "never" if label == "NEVER" else "auto"
    rows = []
    text_rows = []
    for binding in plan.bindings:
        interface = binding.switch_port.replace("FastEthernet", "Fa")
        row = None if mode == "never" else dict(interface=interface, admin="auto", oper="on",
            power_watts=10.0, device="IP Phone 7960", power_class="3", max_watts=15.4)
        rows.append(dict(port=binding.switch_port, row=row,
            delivery="not_delivering" if mode == "never" else "delivering"))
        if row is not None:
            text_rows.append(f"{interface:<9} {'auto':<6} {'on':<10} {'10.0':<7} {'IP Phone 7960':<19} {'3':<5} 15.4")
    text_rows.append(f"{'Fa0/24':<9} {'auto':<6} {'off':<10} {'0.0':<7} {'n/a':<19} {'n/a':<5} 15.4")
    raw = ("Interface Admin Oper Power Device Class Max\n"
           "--------- ------ ---------- ------- ------------------- ----- ----\n"
           + "\n".join(text_rows) + "\nSW#")
    dispatch = dict(output=raw, pager_continuation="not_encountered", pager_pages_captured=1,
        expected_prompt="SW#", session_state="exec_prompt_ready", truncated_by_pager=False,
        observed_device_name="SW", device_identity_provenance="confirmed_unique",
        dispatch_classification="dispatched", echo_observed="show power inline",
        query_id="qualification_show_power_inline", executed=True, fresh_output_observed=True)
    observation = dict(ports=rows, raw_output=raw, command_result=dispatch,
        capture_complete=True, device_identity_provenance="confirmed_unique",
        observed_device_name="SW", switch_identity="SW", fresh_output_observed=True,
        status="observed", refusal_reason="")
    class Capture(SimpleNamespace):
        def model_dump(self, **kwargs):
            return dict(vars(self))
    return Capture(observation=observation, repeat_observation=deepcopy(observation),
        expected_prompt="SW#", stable=True, raw_file=label.lower() + ".txt",
        raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        table_completeness={key: True for key in runner.COMPLETENESS_KEYS})


@pytest.mark.parametrize("label", ["AUTO_1", "NEVER", "AUTO_2"])
def test_measured_capture_translates_every_port_in_plan_order(runner, label):
    plan = runner.governed_plan("3560-24PS")
    capture = measured_capture(runner, plan, label)
    typed = runner.pse_capture(plan, label, capture, "SW")
    assert len(typed.binding_captures) == 21
    assert tuple(c.switch_port for c in typed.binding_captures) == tuple(b.switch_port for b in plan.bindings)
    assert all(c.delivering is (label != "NEVER") for c in typed.binding_captures)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "order", "repeat_incomplete",
    "repeat_rows", "admin", "raw_mismatch", "refused", "raw_hash", "stable"])
def test_capture_rejects_incomplete_or_inconsistent_measurements(runner, mutation):
    plan = runner.governed_plan("3560-24PS")
    capture = measured_capture(runner, plan)
    if mutation == "missing":
        capture.observation["ports"].pop()
    elif mutation == "duplicate":
        capture.observation["ports"][1] = capture.observation["ports"][0]
    elif mutation == "order":
        capture.observation["ports"].reverse()
    elif mutation == "repeat_incomplete":
        capture.repeat_observation["command_result"]["truncated_by_pager"] = True
    elif mutation == "repeat_rows":
        capture.repeat_observation["ports"][0]["row"]["power_watts"] = 5.0
    elif mutation == "admin":
        capture.observation["ports"][0]["row"]["admin"] = "never"
    elif mutation == "raw_mismatch":
        for reading in (capture.observation, capture.repeat_observation):
            reading["ports"][0]["row"]["power_watts"] = 5.0
    elif mutation == "refused":
        capture.repeat_observation["refusal_reason"] = "unobservable"
    elif mutation == "raw_hash":
        capture.raw_sha256 = "0" * 64
    else:
        capture.stable = False
    with pytest.raises(ValueError):
        runner.pse_capture(plan, "AUTO_1", capture, "SW")


@pytest.mark.parametrize("area", ["baseline", "restoration"])
@pytest.mark.parametrize("key", ["devices", "links", "saved_filename", "simulation_mode", "pt_version"])
def test_missing_environment_measurement_cannot_save(runner, area, key):
    inputs = persist_inputs(runner)
    env_key = "environment" if area == "baseline" else "environment_after"
    inputs[area][env_key].pop(key)
    def forbidden(*args, **kwargs):
        pytest.fail("Incomplete environment crossed persistence gate")
    with pytest.raises(ValueError):
        runner.persist_qualification(**inputs, store=SimpleNamespace(save_runtime=forbidden))


def test_cleanup_attempts_every_identity_even_after_a_deletion_failure(runner):
    plan = runner.governed_plan("3560-24PS")
    bindings = plan.bindings[:3]
    calls = []
    class Device(SimpleNamespace):
        def model_dump(self, **kwargs):
            return dict(vars(self))
    transport = SimpleNamespace(
        create_device=lambda model, name, ports, **kwargs: Device(
            model=model, name=name,
        ),
        create_link=lambda *args: Device(linked=True),
    )
    session = runner.PacketTracerPoE3BSession(
        "offline-cleanup",
        switch_ports=tuple(binding.switch_port for binding in bindings),
        transport=transport,
    )
    session.create_fixture(plan.candidate_model, bindings)
    switch, phone1, phone2, phone3 = session.attempted_device_names
    def delete(name):
        calls.append(name)
        if name == phone2:
            raise RuntimeError("controlled failure")
        return name != phone1
    transport.delete_device = delete

    cleanup = session.cleanup_fixture()

    assert calls == [phone3, phone2, phone1, switch]
    assert cleanup.deleted == (phone3, switch)
    assert len(cleanup.problems) == 2


def test_both_wrong_build_measurements_never_save(runner):
    inputs = persist_inputs(runner)
    inputs["baseline"]["environment"]["pt_version"] = "wrong"
    inputs["restoration"]["environment_after"]["pt_version"] = "wrong"
    def forbidden(*args, **kwargs):
        pytest.fail("Wrong PT build crossed persistence gate")
    with pytest.raises(ValueError):
        runner.persist_qualification(**inputs, store=SimpleNamespace(save_runtime=forbidden))


def test_partial_fixture_tracks_created_identity_before_link_failure(runner):
    plan = runner.governed_plan("3560-24PS")
    class Device(SimpleNamespace):
        def model_dump(self, **kwargs):
            return dict(vars(self))
    def link(*args):
        raise RuntimeError("link failure")
    session = runner.PacketTracerPoE3BSession(
        "offline-partial",
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        transport=SimpleNamespace(
            create_device=lambda model, name, *args, **kwargs: Device(
                model=model, name=name,
            ),
            create_link=link,
        ),
    )
    with pytest.raises(RuntimeError, match="link failure"):
        session.create_fixture(plan.candidate_model, plan.bindings)
    assert session.attempted_device_names == session.created_device_names
    assert session.attempted_device_names == (
        session.switch_name,
        session.endpoint_prefix + "-1",
    )


@pytest.mark.parametrize("malformed", [False, True])
def test_real_observer_malformed_never_row_cannot_cross_persistence(runner, malformed):
    # The sole fake is the external IOS transport result. Both observer reads,
    # session capture, typed translation, validators and snapshot builder run.
    ios = importlib.import_module(runner.parse_show_power_inline.__module__)
    observer_module = importlib.import_module(
        "packet_tracer_mcp.infrastructure.execution.poe_inline_observer")
    session_module = importlib.import_module(
        "packet_tracer_mcp.infrastructure.execution.poe3b_session")
    inputs = persist_inputs(runner)
    plan = inputs["plan"]
    transport = session_module.PacketTracerPoE3BLiveTransport(
        bridge=SimpleNamespace(
            send=lambda script: True,
            send_and_wait=lambda script, timeout: None,
        ),
        sleeper=lambda seconds: None,
    )
    captures, problems, saved = [], [], []
    for label in ("AUTO_1", "NEVER", "AUTO_2"):
        raw = measured_capture(runner, plan, label).observation["raw_output"]
        if malformed and label == "NEVER":
            bad = "Fa0/1     auto   on         BAD     IP Phone 7960       3     15.4\n"
            raw = raw.replace("Fa0/24", bad + "Fa0/24", 1)
        dispatch = ios.IosCommandResult(
            device_name="SW", query_id=ios.IosQualificationQueryId.SHOW_POWER_INLINE,
            executed=True, output=raw, output_complete=True,
            session_state=ios.IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True, device_identity_provenance="confirmed_unique",
            observed_device_name="SW", dispatch_classification="dispatched",
            echo_observed="show power inline", expected_prompt="SW#",
            pager_continuation="not_encountered", pager_pages_captured=1,
            truncated_by_pager=False)
        transport._observer = observer_module.GovernedPoEInlineObserver(
            SimpleNamespace(qualify=lambda *args, dispatch=dispatch: dispatch))
        acquired = transport.capture_inline_status(
            "SW", tuple(binding.switch_port for binding in plan.bindings), label,
        )
        try:
            captures.append(runner.pse_capture(plan, label, acquired, "SW"))
        except ValueError as exc:
            problems.append(str(exc))
    inputs["scope"] = replace(inputs["scope"], captures=tuple(captures))
    inputs["problems"] = problems
    store = SimpleNamespace(save_runtime=lambda snapshot: saved.append(snapshot) or Path("spy.json"))
    if malformed:
        with pytest.raises(ValueError):
            runner.persist_qualification(**inputs, store=store)
        assert saved == []
    else:
        runner.persist_qualification(**inputs, store=store)
        assert len(saved) == 1


@pytest.mark.parametrize("length", [69, 99, 100, 101])
def test_qualification_metadata_cannot_displace_unique_run_suffix(runner, length):
    with pytest.raises(ValueError):
        runner.parse_args(["--execute", "--model", "3560-24PS", "--qualification-id", "x" * length])


def test_boundary_length_run_names_keep_timestamp_nonce_and_final_id_character(runner, monkeypatch):
    monkeypatch.setattr(runner, "token_hex", lambda size: "1234abcd")
    names = []
    for suffix in ("a", "b"):
        identifier = "x" * 67 + suffix
        runner.parse_args(["--execute", "--model", "3560-24PS", "--qualification-id", identifier])
        run_id = runner.qualification_run_id(identifier)
        assert len(run_id) == 100
        assert run_id == runner.safe_name_component(run_id)
        assert run_id.startswith("poe3b-" + identifier + "-")
        assert run_id.endswith("Z-1234abcd")
        names.append(run_id)
    assert names[0] != names[1]
    monkeypatch.setattr(runner, "token_hex", lambda size: "8765dcba")
    retry = runner.qualification_run_id("x" * 67 + "a")
    assert retry != names[0] and retry.endswith("Z-8765dcba")


def test_artifact_destination_is_reserved_exclusively_before_any_fixture_mutation(runner, monkeypatch):
    monkeypatch.setattr(runner, "qualification_run_id", lambda _: "poe3b-fixed-identity")
    first = runner.reserve_artifacts("offline")
    assert first.directory.is_dir()
    assert first.directory.name == first.run_id
    with pytest.raises(FileExistsError):
        runner.reserve_artifacts("offline")
    assert list(first.directory.iterdir()) == []
    # A caller cannot enter the bounded session without an exact reservation.
    plan = runner.governed_plan("3560-24PS")
    def forbidden(*args, **kwargs):
        pytest.fail("Fixture mutation preceded destination safety")
    session = runner.PacketTracerPoE3BSession(
        "offline-unreserved",
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        transport=SimpleNamespace(bridge_healthy=forbidden),
    )
    with pytest.raises(ValueError):
        runner.execute_governed_qualification(
            session=session,
            plan=plan,
            baseline=facts()[0],
            artifacts=None,
            store=SimpleNamespace(save_runtime=forbidden),
            process_probe=forbidden,
            source_state_probe=forbidden,
        )


@pytest.mark.parametrize("failure", ["missing", "removed", "scope_mismatch", "replacement"])
def test_snapshot_persistence_requires_original_exact_artifact_reservation(runner, monkeypatch, failure):
    inputs = persist_inputs(runner)
    artifacts = inputs["artifacts"]
    if failure == "missing":
        inputs["artifacts"] = None
    elif failure == "removed":
        artifacts.directory.rmdir()
    elif failure == "scope_mismatch":
        inputs["scope"] = replace(inputs["scope"], experiment_id="different-run")
    else:
        # Move the original empty directory to preserve its inode and replace it.
        artifacts.directory.rename(artifacts.directory.with_name("previous-reservation"))
        artifacts.directory.mkdir()
    def forbidden(*args, **kwargs):
        pytest.fail("Positive result/persistence preceded destination safety")
    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError):
        runner.persist_qualification(**inputs, store=SimpleNamespace(save_runtime=forbidden))


def test_runner_cycle_uses_only_the_instrumented_bounded_session_transport(
    runner,
) -> None:
    plan = runner.governed_plan("3560-24PS")
    baseline, _restoration, _final = facts()
    artifacts = runner.reserve_artifacts("offline-e2e")
    saved = []

    class Dump(SimpleNamespace):
        def model_dump(self, **kwargs):
            return dict(vars(self))

    class InstrumentedPoE3BTransport:
        def __init__(self):
            self.calls = []

        def record(self, operation):
            self.calls.append(operation)

        def bridge_healthy(self):
            self.record(runner.PoE3BSessionOperation.TRANSPORT_HEALTH)
            return True

        def mailbox_entries(self):
            self.record(runner.PoE3BSessionOperation.MAILBOX_OBSERVATION)
            return ()

        def start_control_bridge(self):
            self.record(runner.PoE3BSessionOperation.CONTROL_BRIDGE_START)
            return dict(
                authenticated_status=200,
                unauthenticated_status=401,
                active_pt_transport="instrumented_session_transport",
            )

        def stop_control_bridge(self):
            self.record(runner.PoE3BSessionOperation.CONTROL_BRIDGE_STOP)

        def environment(self):
            self.record(runner.PoE3BSessionOperation.ENVIRONMENT_OBSERVATION)
            return dict(
                devices=0,
                links=0,
                saved_filename="",
                simulation_mode=False,
                pt_version=plan.packet_tracer_build,
            )

        def inventory_fingerprint(self):
            self.record(runner.PoE3BSessionOperation.INVENTORY_OBSERVATION)
            return "a" * 64 + "|"

        def device_names(self):
            self.record(runner.PoE3BSessionOperation.DEVICE_NAMES_OBSERVATION)
            return frozenset()

        def create_device(self, model, name, required_ports, *, arm):
            self.record(runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE)
            return Dump(name=name, model=model, observed_ports=list(required_ports))

        def create_link(self, switch, switch_port, endpoint, endpoint_port):
            self.record(runner.PoE3BSessionOperation.FIXTURE_LINK_CREATE)
            return Dump(
                first=dict(device_name=switch.name, port=switch_port),
                second=dict(device_name=endpoint.name, port=endpoint_port),
            )

        def wait_until_ready(self, switch_name, *, timeout_seconds):
            self.record(runner.PoE3BSessionOperation.DEVICE_READINESS)
            return Dump(state="operational_ready", attempts=1)

        def apply_inline_mode(self, switch_name, switch_ports, mode):
            self.record(runner.PoE3BSessionOperation.INLINE_MODE_APPLY)

        def capture_inline_status(self, switch_name, switch_ports, label):
            self.record(runner.PoE3BSessionOperation.INLINE_CAPTURE)
            capture = measured_capture(runner, plan, label)
            for observation in (
                capture.observation, capture.repeat_observation,
            ):
                observation["switch_identity"] = switch_name
                observation["observed_device_name"] = switch_name
                observation["command_result"]["observed_device_name"] = switch_name
            capture.table_completeness = runner.completeness(
                capture.observation,
                capture.expected_prompt,
                capture.stable,
                switch_name,
            )
            return capture

        def delete_device(self, name):
            self.record(runner.PoE3BSessionOperation.FIXTURE_DEVICE_DELETE)
            return True

        def retire_session_residue(self, preexisting):
            self.record(runner.PoE3BSessionOperation.RESIDUE_RETIRE)
            return ()

        def wait_for_inventory_fingerprint(self, expected):
            self.record(runner.PoE3BSessionOperation.INVENTORY_RESTORATION)
            return expected

        def collect_completed(self):
            self.record(runner.PoE3BSessionOperation.IPC_DRAIN)

        def transport_problems(self):
            self.record(runner.PoE3BSessionOperation.TRANSPORT_PROBLEMS)
            return ()

    transport = InstrumentedPoE3BTransport()
    session = runner.PacketTracerPoE3BSession(
        artifacts.run_id,
        switch_ports=tuple(binding.switch_port for binding in plan.bindings),
        endpoint_role="PH",
        transport=transport,
    )
    source = dict(
        source_branch="feature/runtime-ripv2",
        source_head="b" * 40,
        source_tree="c" * 40,
        worktree_clean=True,
    )
    execution = runner.execute_governed_qualification(
        session=session,
        plan=plan,
        baseline=baseline,
        artifacts=artifacts,
        store=SimpleNamespace(
            save_runtime=lambda snapshot: saved.append(snapshot)
            or Path("synthetic-snapshot.json"),
        ),
        process_probe=packet_tracer_processes,
        source_state_probe=lambda: dict(source),
    )

    observed = tuple(record.operation for record in session.dispatches)
    assert execution.problems == []
    assert execution.snapshot_path == Path("synthetic-snapshot.json")
    assert saved == [execution.snapshot]
    assert observed == tuple(transport.calls)
    assert runner.PoE3BSessionOperation.WORKSPACE_FILE_OPERATION not in observed
    assert observed.count(runner.PoE3BSessionOperation.FIXTURE_DEVICE_CREATE) == 22
    assert observed.count(runner.PoE3BSessionOperation.FIXTURE_LINK_CREATE) == 21
    assert observed.count(runner.PoE3BSessionOperation.INLINE_MODE_APPLY) == 4
    assert observed.count(runner.PoE3BSessionOperation.INLINE_CAPTURE) == 4
    assert observed.count(runner.PoE3BSessionOperation.FIXTURE_DEVICE_DELETE) == 22
    assert execution.file_operation_ledger.ephemeral_safe
