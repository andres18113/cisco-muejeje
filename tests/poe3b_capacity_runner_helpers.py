"""Small shared fixtures for the offline PoE-3B runner test slices."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[1] / "tools")
    )
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


def packet_tracer_processes(*, main_pid=42, helper_pid=43):
    executable = (
        r"C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe"
    )
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


def facts():
    env = dict(
        devices=0,
        links=0,
        saved_filename="",
        simulation_mode=False,
        pt_version="9.0.1.0858",
    )
    head = "b" * 40
    baseline = dict(
        environment=env,
        inventory_fingerprint="a" * 64 + "|",
        source_branch="feature/runtime-ripv2",
        local_head=head,
        source_tree="c" * 40,
        upstream="cisco/feature/runtime-ripv2",
        upstream_head=head,
        worktree_clean=True,
        processes=packet_tracer_processes(),
        bridge_healthy=True,
        mailbox_entries=(),
    )
    restoration = dict(
        environment_after=deepcopy(env),
        inventory_fingerprint_after="a" * 64 + "|",
        inventory_restored=True,
        fixture_removed=True,
        power_inline_auto_proven=True,
        attempted=["SW", "PH"],
        created=["SW", "PH"],
        deleted=["PH", "SW"],
    )
    final = dict(
        source_branch="feature/runtime-ripv2",
        source_head=head,
        source_tree="c" * 40,
        upstream="cisco/feature/runtime-ripv2",
        upstream_head=head,
        worktree_clean=True,
        processes=packet_tracer_processes(),
        bridge_healthy=True,
        mailbox_entries=(),
        transport_problems=[],
    )
    return baseline, restoration, final


def typed_captures(runner, plan):
    return tuple(
        runner.PoEPseMultiPortCapture(
            label,
            mode,
            tuple(
                runner.PoEPseBindingCapture(
                    binding.switch_port,
                    binding.endpoint_model,
                    binding.endpoint_port,
                    "on" if mode == "auto" else "absent",
                    10.0 if mode == "auto" else 0.0,
                    mode == "auto",
                    mode == "auto",
                )
                for binding in plan.bindings
            ),
        )
        for label, mode in (
            ("AUTO_1", "auto"),
            ("NEVER", "never"),
            ("AUTO_2", "auto"),
        )
    )


def qualification_inputs(runner):
    plan = runner.governed_plan("3560-24PS")
    baseline, restoration, final = facts()
    names = ["SW"] + ["PH" + str(index) for index in range(21)]
    restoration.update(
        attempted=names,
        created=names,
        deleted=list(reversed(names)),
    )
    artifacts = runner.reserve_artifacts("offline")
    scope = runner.pse_scope_for(
        plan=plan,
        run_id=artifacts.run_id,
        observed_at="2026-09-09T18:00:00Z",
        captures=typed_captures(runner, plan),
        gates=tuple(sorted(runner.COMPLETENESS_KEYS)),
    )
    return dict(
        plan=plan,
        scope=scope,
        artifacts=artifacts,
        baseline=baseline,
        restoration=restoration,
        safety=final,
        problems=[],
        file_operation_ledger=empty_file_ledger(runner),
    )


def measured_capture(runner, plan, label="AUTO_1"):
    mode = "never" if label == "NEVER" else "auto"
    rows = []
    text_rows = []
    for binding in plan.bindings:
        interface = binding.switch_port.replace("FastEthernet", "Fa")
        row = None
        if mode != "never":
            row = dict(
                interface=interface,
                admin="auto",
                oper="on",
                power_watts=10.0,
                device="IP Phone 7960",
                power_class="3",
                max_watts=15.4,
            )
        rows.append(
            dict(
                port=binding.switch_port,
                row=row,
                delivery=(
                    "not_delivering" if mode == "never" else "delivering"
                ),
            )
        )
        if row is not None:
            text_rows.append(
                f"{interface:<9} {'auto':<6} {'on':<10} {'10.0':<7} "
                f"{'IP Phone 7960':<19} {'3':<5} 15.4"
            )
    text_rows.append(
        f"{'Fa0/24':<9} {'auto':<6} {'off':<10} {'0.0':<7} "
        f"{'n/a':<19} {'n/a':<5} 15.4"
    )
    raw = (
        "Interface Admin Oper Power Device Class Max\n"
        "--------- ------ ---------- ------- ------------------- ----- ----\n"
        + "\n".join(text_rows)
        + "\nSW#"
    )
    dispatch = dict(
        output=raw,
        pager_continuation="not_encountered",
        pager_pages_captured=1,
        expected_prompt="SW#",
        session_state="exec_prompt_ready",
        truncated_by_pager=False,
        observed_device_name="SW",
        device_identity_provenance="confirmed_unique",
        dispatch_classification="dispatched",
        echo_observed="show power inline",
        query_id="qualification_show_power_inline",
        executed=True,
        fresh_output_observed=True,
    )
    observation = dict(
        ports=rows,
        raw_output=raw,
        command_result=dispatch,
        capture_complete=True,
        device_identity_provenance="confirmed_unique",
        observed_device_name="SW",
        switch_identity="SW",
        fresh_output_observed=True,
        status="observed",
        refusal_reason="",
    )

    class Capture(SimpleNamespace):
        def model_dump(self, **kwargs):
            return dict(vars(self))

    return Capture(
        observation=observation,
        repeat_observation=deepcopy(observation),
        expected_prompt="SW#",
        stable=True,
        raw_file=label.lower() + ".txt",
        raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        table_completeness={key: True for key in runner.COMPLETENESS_KEYS},
    )
