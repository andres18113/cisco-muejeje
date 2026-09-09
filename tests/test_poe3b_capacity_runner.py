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
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    module = importlib.import_module("poe3a_pse_live")
    experiment = importlib.import_module("poe2_ap_live")
    # The actual constructor opens the machine mailbox. Replace before constructing.
    monkeypatch.setattr(experiment, "FileBridge", lambda: SimpleNamespace(send=None))
    monkeypatch.setattr(experiment.time, "sleep", lambda seconds: None)
    return module


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
    exp = runner.Experiment("offline", switch_ports=ports)
    assert exp.switch_port == ports[0]
    configured, observed = [], []
    exp.config = SimpleNamespace(configure_ios=lambda device, payload: configured.append(payload) or True)
    exp.bridge = SimpleNamespace(collect_completed=lambda: None, _pending={})
    class Done(Exception):
        pass
    def observe(device, requested):
        observed.append(requested)
        if len(observed) == 2:
            raise Done
        return SimpleNamespace(command_result=None)
    exp.observer = SimpleNamespace(observe_poe_inline_status=observe)
    exp.apply(runner.PoEInlineMode.NEVER)
    assert [p.split("interface ")[1].splitlines()[0] for p in configured] == list(ports)
    with pytest.raises(Done):
        exp.capture("NEVER")
    assert observed == [ports, ports]


@pytest.mark.parametrize("ports", [(), ("FastEthernet0/1", "FastEthernet0/1")])
def test_experiment_rejects_empty_or_duplicate_ports(runner, ports):
    with pytest.raises(ValueError):
        runner.Experiment("offline", switch_ports=ports)


@pytest.mark.parametrize("model,count", [("3560-24PS", 21), ("3650-24PS", 11)])
def test_fixture_has_one_phone_and_link_per_governed_binding(runner, model, count):
    plan = runner.governed_plan(model)
    made, links, attempted = [], [], []
    class Device(SimpleNamespace):
        def model_dump(self, **kwargs):
            return vars(self)
    def create(model, name, ports, **kwargs):
        made.append((model, name, ports))
        return Device(model=model, name=name)
    def link(switch, port, phone, endpoint_port):
        links.append((port, endpoint_port))
        return Device(port=port)
    exp = SimpleNamespace(switch="SW", endpoint="PH", fixture=SimpleNamespace(
        create_device=create, create_link=link))
    created = []
    runner.create_fixture(exp, plan, attempted, created)
    assert len(made) == count + 1 and len(links) == count
    assert made[0] == (model, "SW", tuple(b.switch_port for b in plan.bindings))
    assert all(m[0] == "7960" and m[2] == ("Switch",) for m in made[1:])
    assert attempted == [m[1] for m in made]
    assert created == attempted
    assert len(set(attempted)) == count + 1
    assert links == [(b.switch_port, "Switch") for b in plan.bindings]


def facts():
    env = dict(devices=0, links=0, saved_filename="", simulation_mode=False,
               pt_version="9.0.1.0858")
    baseline = dict(environment=env, inventory_fingerprint="a" * 64 + "|",
        source_branch="feature/runtime-ripv2", local_head="b" * 40,
        source_tree="c" * 40, worktree_clean=True,
        processes=[dict(Name="PacketTracer.exe", ProcessId=42)],
        bridge_healthy=True, mailbox_entries=(),
        authorized_file_operations=(), executed_file_operations=())
    restoration = dict(environment_after=deepcopy(env),
        inventory_fingerprint_after="a" * 64 + "|", inventory_restored=True,
        fixture_removed=True, power_inline_auto_proven=True,
        attempted=["SW", "PH"], created=["SW", "PH"], deleted=["PH", "SW"])
    final = dict(source_branch="feature/runtime-ripv2", source_head="b" * 40,
        source_tree="c" * 40, worktree_clean=True,
        processes=[dict(Name="PacketTracer.exe", ProcessId=42)],
        bridge_healthy=True, mailbox_entries=(), transport_problems=[],
        authorized_file_operations=(), executed_file_operations=())
    return baseline, restoration, final


def test_ephemeral_evidence_carries_acquired_facts_and_explicit_file_ledgers(runner):
    baseline, restoration, final = facts()
    evidence = runner.ephemeral_safety_for(baseline, restoration, final, [])
    assert runner.validate_live_session_positive_admission(evidence).is_valid
    assert evidence.authorized_file_operations == evidence.executed_file_operations == ()
    assert evidence.packet_tracer_pids_before == evidence.packet_tracer_pids_after == (42,)
    assert evidence.source_tree_before == "c" * 40
    assert not any("canonical" in key or "disposable" in key for key in evidence.model_dump())
    final["processes"] = [dict(Name="PacketTracer.exe", ProcessId=99)]
    changed = runner.ephemeral_safety_for(baseline, restoration, final, [])
    assert changed.packet_tracer_pids_after == (99,)
    assert not runner.validate_live_session_positive_admission(changed).is_valid


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
    scope = runner.pse_scope_for(plan=plan, run_id="offline", observed_at="2026-09-09T18:00:00Z",
        captures=typed_captures(runner, plan), gates=tuple(sorted(runner.COMPLETENESS_KEYS)))
    return dict(plan=plan, scope=scope, baseline=baseline, restoration=restoration,
                safety=final, problems=[])


@pytest.mark.parametrize("area,key", [
    ("baseline", "environment"), ("baseline", "inventory_fingerprint"),
    ("baseline", "processes"), ("baseline", "bridge_healthy"),
    ("baseline", "mailbox_entries"), ("baseline", "source_branch"),
    ("baseline", "local_head"), ("baseline", "source_tree"),
    ("baseline", "worktree_clean"), ("baseline", "authorized_file_operations"),
    ("baseline", "executed_file_operations"),
    ("restoration", "environment_after"), ("restoration", "inventory_fingerprint_after"),
    ("restoration", "inventory_restored"), ("restoration", "fixture_removed"),
    ("restoration", "power_inline_auto_proven"), ("restoration", "deleted"),
    ("restoration", "created"), ("restoration", "attempted"),
    ("safety", "processes"), ("safety", "bridge_healthy"), ("safety", "mailbox_entries"),
    ("safety", "source_branch"), ("safety", "source_head"), ("safety", "source_tree"),
    ("safety", "worktree_clean"), ("safety", "transport_problems"),
    ("safety", "authorized_file_operations"), ("safety", "executed_file_operations"),
])
def test_missing_boundary_never_constructs_positive_result_or_saves(runner, monkeypatch, area, key):
    inputs = persist_inputs(runner)
    inputs[area].pop(key)
    def forbidden(*args, **kwargs):
        pytest.fail("Incomplete run crossed the positive result/persistence boundary")
    monkeypatch.setattr(runner, "CapabilityProbeResult", forbidden)
    with pytest.raises(ValueError):
        runner.persist_qualification(**inputs, store=SimpleNamespace(save_runtime=forbidden))


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
    assert probe.context.live_session_safety.executed_file_operations == ()
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
    return SimpleNamespace(observation=observation, repeat_observation=deepcopy(observation),
        expected_prompt="SW#", stable=True, raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
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
    attempted = ["SW", "PH1", "PH2", "PH3"]
    calls, problems = [], []
    def delete(name):
        calls.append(name)
        if name == "PH2":
            raise RuntimeError("controlled failure")
        return name != "PH1"
    exp = SimpleNamespace(fixture=SimpleNamespace(delete_device=delete))
    deleted = runner.cleanup_fixture(exp, attempted, problems)
    assert calls == ["PH3", "PH2", "PH1", "SW"]
    assert deleted == ["PH3", "SW"] and len(problems) == 2


def test_both_wrong_build_measurements_never_save(runner):
    inputs = persist_inputs(runner)
    inputs["baseline"]["environment"]["pt_version"] = "wrong"
    inputs["restoration"]["environment_after"]["pt_version"] = "wrong"
    def forbidden(*args, **kwargs):
        pytest.fail("Wrong PT build crossed persistence gate")
    with pytest.raises(ValueError):
        runner.persist_qualification(**inputs, store=SimpleNamespace(save_runtime=forbidden))


def test_partial_fixture_tracks_created_identity_before_link_failure(runner):
    attempted, created = [], []
    plan = runner.governed_plan("3560-24PS")
    def link(*args):
        raise RuntimeError("link failure")
    exp = SimpleNamespace(switch="SW", endpoint="PH", fixture=SimpleNamespace(
        create_device=lambda model, *args, **kwargs: SimpleNamespace(model=model),
        create_link=link))
    with pytest.raises(RuntimeError, match="link failure"):
        runner.create_fixture(exp, plan, attempted, created)
    assert attempted == created == ["SW", "PH-1"]
