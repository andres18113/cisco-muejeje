"""PoE-3B capture stability, completeness and schema translation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.poe3b_capacity_runner_helpers import (
    measured_capture,
    qualification_inputs,
    runner,
)


def test_experiment_applies_ordered_ports_and_observes_whole_tuple_twice(
    runner,
):
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
        "offline",
        switch_ports=ports,
        transport=transport,
    )
    session.apply_inline_mode(runner.PoEInlineMode.NEVER)
    assert configured == [
        (session.switch_name, ports, runner.PoEInlineMode.NEVER),
    ]
    with pytest.raises(Done):
        session.capture_inline_status("NEVER")
        session.capture_inline_status("NEVER")
    assert observed == [ports, ports]


@pytest.mark.parametrize(
    "ports",
    [
        (),
        ("FastEthernet0/1", "FastEthernet0/1"),
        ("FastEthernet0/1\nwrite memory",),
    ],
)
def test_experiment_rejects_empty_or_duplicate_ports(runner, ports):
    with pytest.raises(ValueError):
        runner.PacketTracerPoE3BSession(
            "offline",
            switch_ports=ports,
            transport=SimpleNamespace(),
        )


@pytest.mark.parametrize("label", ["AUTO_1", "NEVER", "AUTO_2"])
def test_measured_capture_translates_every_port_in_plan_order(runner, label):
    plan = runner.governed_plan("3560-24PS")
    capture = measured_capture(runner, plan, label)
    typed = runner.pse_capture(plan, label, capture, "SW")
    assert len(typed.binding_captures) == 21
    assert tuple(item.switch_port for item in typed.binding_captures) == tuple(
        binding.switch_port for binding in plan.bindings
    )
    assert all(
        item.delivering is (label != "NEVER")
        for item in typed.binding_captures
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "order",
        "repeat_incomplete",
        "repeat_rows",
        "admin",
        "raw_mismatch",
        "refused",
        "raw_hash",
        "stable",
    ],
)
def test_capture_rejects_incomplete_or_inconsistent_measurements(
    runner,
    mutation,
):
    plan = runner.governed_plan("3560-24PS")
    capture = measured_capture(runner, plan)
    if mutation == "missing":
        capture.observation["ports"].pop()
    elif mutation == "duplicate":
        capture.observation["ports"][1] = capture.observation["ports"][0]
    elif mutation == "order":
        capture.observation["ports"].reverse()
    elif mutation == "repeat_incomplete":
        capture.repeat_observation["command_result"][
            "truncated_by_pager"
        ] = True
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


@pytest.mark.parametrize("malformed", [False, True])
def test_real_observer_malformed_never_row_cannot_cross_persistence(
    runner,
    malformed,
):
    # The sole fake is the external IOS transport result. Both observer reads,
    # session capture, typed translation, validators and snapshot builder run.
    ios = importlib.import_module(runner.parse_show_power_inline.__module__)
    observer_module = importlib.import_module(
        "packet_tracer_mcp.infrastructure.execution.poe_inline_observer"
    )
    session_module = importlib.import_module(
        "packet_tracer_mcp.infrastructure.execution.poe3b_session"
    )
    inputs = qualification_inputs(runner)
    plan = inputs["plan"]
    transport = session_module.PacketTracerPoE3BLiveTransport(
        bridge=SimpleNamespace(
            send=lambda script: True,
            send_and_wait=lambda script, timeout: None,
        ),
        sleeper=lambda seconds: None,
    )
    captures, problems = [], []
    for label in ("AUTO_1", "NEVER", "AUTO_2"):
        raw = measured_capture(runner, plan, label).observation["raw_output"]
        if malformed and label == "NEVER":
            bad = (
                "Fa0/1     auto   on         BAD     IP Phone 7960       "
                "3     15.4\n"
            )
            raw = raw.replace("Fa0/24", bad + "Fa0/24", 1)
        dispatch = ios.IosCommandResult(
            device_name="SW",
            query_id=ios.IosQualificationQueryId.SHOW_POWER_INLINE,
            executed=True,
            output=raw,
            output_complete=True,
            session_state=ios.IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            device_identity_provenance="confirmed_unique",
            observed_device_name="SW",
            dispatch_classification="dispatched",
            echo_observed="show power inline",
            expected_prompt="SW#",
            pager_continuation="not_encountered",
            pager_pages_captured=1,
            truncated_by_pager=False,
        )
        transport._observer = observer_module.GovernedPoEInlineObserver(
            SimpleNamespace(qualify=lambda *args, dispatch=dispatch: dispatch)
        )
        acquired = transport.capture_inline_status(
            "SW",
            tuple(binding.switch_port for binding in plan.bindings),
            label,
        )
        try:
            captures.append(runner.pse_capture(plan, label, acquired, "SW"))
        except ValueError as exc:
            problems.append(str(exc))
    inputs["scope"] = replace(inputs["scope"], captures=tuple(captures))
    inputs["problems"] = problems
    if malformed:
        with pytest.raises(ValueError):
            runner.build_qualification_snapshot(**inputs)
    else:
        snapshot = runner.build_qualification_snapshot(**inputs)
        assert snapshot.session.results[0].verified is True


@pytest.mark.parametrize("label", ["PSU_BEFORE", "PSU_AFTER"])
def test_live_transport_accepts_the_closed_factory_power_capture_labels(
    runner,
    label,
) -> None:
    """Removing either PoE-3B label must fail at the real capture boundary."""

    ios = importlib.import_module(runner.parse_show_power_inline.__module__)
    observer_module = importlib.import_module(
        "packet_tracer_mcp.infrastructure.execution.poe_inline_observer"
    )
    session_module = importlib.import_module(
        "packet_tracer_mcp.infrastructure.execution.poe3b_session"
    )
    plan = runner.governed_plan("3650-24PS")
    raw = (
        Path(__file__).resolve().parents[1]
        / "docs/reference/cp-scale/canonical-live-evidence"
        / "poe3b-router0-b-3650-11-20260910T234609Z-8c86e3b4"
        / "auto_1.txt"
    ).read_text(encoding="utf-8")
    dispatch = ios.IosCommandResult(
        device_name="SW",
        query_id=ios.IosQualificationQueryId.SHOW_POWER_INLINE,
        executed=True,
        output=raw,
        output_complete=True,
        session_state=ios.IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=True,
        device_identity_provenance="confirmed_unique",
        observed_device_name="SW",
        dispatch_classification="dispatched",
        echo_observed="show power inline",
        expected_prompt="Switch#",
        pager_continuation="continued",
        pager_pages_captured=2,
        truncated_by_pager=False,
    )
    transport = session_module.PacketTracerPoE3BLiveTransport(
        bridge=SimpleNamespace(
            send=lambda script: True,
            send_and_wait=lambda script, timeout: None,
        ),
        sleeper=lambda seconds: None,
    )
    transport._observer = observer_module.GovernedPoEInlineObserver(
        SimpleNamespace(qualify=lambda *args: dispatch)
    )

    acquired = transport.capture_inline_status(
        "SW",
        tuple(binding.switch_port for binding in plan.bindings),
        label,
    )

    assert acquired.label == label
    assert acquired.raw_file == label.lower() + ".txt"
    assert acquired.stable is True
