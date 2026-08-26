"""Contracts for the bounded post-failure Simulation diagnostic.

The canonical LIVE runner imports the production package namespace.  Keep that
namespace in a child process here for the same reason as the neighboring
CP-SCALE failure-evidence suite: importing it in pytest would invalidate the
runner's import-isolation preflight.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

_PROBE = r'''
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, __ROOT__)
sys.path.insert(0, __SRC__)

from tools.cp_scale_canonical_live import (
    _SIMULATION_GLOBAL_EVENT_LIST_CEILING,
    _SIMULATION_HARD_MAX_STEPS,
    _SIMULATION_HARD_WALL_CLOCK_SECONDS,
    _SIMULATION_STALL_BATCH_LIMIT,
    _SIMULATION_STEP_BATCH_SIZE,
    _SIMULATION_TARGET_TIME_SPAN,
    _bounded_simulation_progression,
    _post_failure_simulation_diagnostic,
)


def state(*, observed=True, mode=True, frames=0, sim_time=0, index=0):
    return SimpleNamespace(
        observed=observed,
        simulation_mode=mode,
        frames=frames,
        sim_time=sim_time,
        current_index=index,
        message="state",
    )


def step(*, observed=True, mode=True, before=0, after=1, sim_time=1, index=0):
    return SimpleNamespace(
        observed=observed,
        simulation_mode=mode,
        frames_before=before,
        frames_after=after,
        sim_time=sim_time,
        current_index=index,
        message="step",
    )


class Runtime:
    def __init__(self, states, steps=None):
        self.states = list(states)
        self.steps = list(steps or [])
        self.actions = []

    def read_simulation_state(self):
        self.actions.append(["read"])
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def step(self, action, times=1):
        self.actions.append(["step", action, times])
        if self.steps:
            return self.steps.pop(0)
        return step(after=times, sim_time=times)


class Clock:
    def __init__(self, values):
        self.values = list(values)
        self.last = self.values[-1]

    def __call__(self):
        if self.values:
            self.last = self.values.pop(0)
        return self.last


def run(states, *, steps=None, clock=(0, 1, 2, 3, 4), **limits):
    runtime = Runtime(states, steps)
    result = _bounded_simulation_progression(
        runtime,
        monotonic=Clock(clock),
        **limits,
    )
    return {"result": result, "actions": runtime.actions}


verdict = {
    "constants": {
        "target": _SIMULATION_TARGET_TIME_SPAN,
        "batch": _SIMULATION_STEP_BATCH_SIZE,
        "steps": _SIMULATION_HARD_MAX_STEPS,
        "wall": _SIMULATION_HARD_WALL_CLOCK_SECONDS,
        "events": _SIMULATION_GLOBAL_EVENT_LIST_CEILING,
        "stall": _SIMULATION_STALL_BATCH_LIMIT,
    },
}

verdict["target"] = run(
    [state(sim_time=100, frames=0), state(sim_time=30100, frames=100),
     state(sim_time=60100, frames=200)],
    steps=[step(before=0, after=100, sim_time=30100),
           step(before=100, after=200, sim_time=60100)],
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=100,
    hard_wall_clock_seconds=100, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)
verdict["max_steps"] = run(
    [state(sim_time=0), state(sim_time=1), state(sim_time=2)],
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=20,
    hard_wall_clock_seconds=100, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)
verdict["wall"] = run(
    [state(sim_time=0), state(sim_time=1)], clock=(0, 121),
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=600,
    hard_wall_clock_seconds=120, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)
verdict["events"] = run(
    [state(sim_time=0, frames=0), state(sim_time=1, frames=2500)],
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=600,
    hard_wall_clock_seconds=120, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)
verdict["unobservable"] = run(
    [state(observed=False, sim_time=0, frames=None)],
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=600,
    hard_wall_clock_seconds=120, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)
verdict["sim_time_unobservable"] = run(
    [state(sim_time=None, frames=0)],
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=600,
    hard_wall_clock_seconds=120, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)
verdict["non_monotonic"] = run(
    [state(sim_time=10), state(sim_time=9)],
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=600,
    hard_wall_clock_seconds=120, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)
verdict["stall"] = run(
    [state(sim_time=10), state(sim_time=10), state(sim_time=10),
     state(sim_time=10)],
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=600,
    hard_wall_clock_seconds=120, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)
verdict["step_failure"] = run(
    [state(sim_time=0)], steps=[step(observed=False, sim_time=None)],
    target_sim_time_span=60000, step_batch_size=10, hard_max_steps=600,
    hard_wall_clock_seconds=120, global_event_list_ceiling=2500,
    stall_batch_limit=3,
)


PHONE_NAME = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PHONE-02"
PHONE_ID = "endpoint/large-branch/campus/floor-1/zone-a/ip_phone/002"


def topology():
    phone = SimpleNamespace(id=PHONE_ID, name=PHONE_NAME, model="7960")
    switch = SimpleNamespace(id="switch5", name="Switch5", model="2960")
    return SimpleNamespace(topology=SimpleNamespace(
        devices=[phone, switch],
        links=[SimpleNamespace(
            device_a_id=switch.id, port_a="FastEthernet0/2",
            device_b_id=phone.id, port_b="Switch",
        )],
    ))


def voice():
    return {"staged": True, "error": "voice failed", "result": {
        "registrations": [{
            "phone_id": PHONE_ID, "extension": "3002", "status": "failed",
            "evidence_method": "fresh", "fresh_evidence": True,
            "endpoint_interface": "Vlan20", "endpoint_interface_present": True,
            "endpoint_address_channel": True, "endpoint_dhcp_enabled": True,
            "endpoint_ipv4": "",
        }],
    }}


class Bridge:
    def __init__(
        self, sim_times, *, frame_counts=None, fail_step=False,
        fail_state_once=False,
    ):
        self.mode = False
        self.sim_times = list(sim_times)
        self.frame_counts = list(frame_counts or [0] * len(self.sim_times))
        self.fail_step = fail_step
        self.fail_state_once = fail_state_once
        self.state_failure_emitted = False
        self.forwards = 0

    def point(self):
        index = min(self.forwards, len(self.sim_times) - 1)
        return self.sim_times[index], self.frame_counts[index]

    def __call__(self, script, timeout):
        sim_time, frames = self.point()
        if "getFrameInstanceAt" in script:
            return json.dumps({
                "total": frames, "simulation_mode": self.mode, "frames": [],
            })
        if "setSimulationMode" in script:
            before = self.mode
            self.mode = "setSimulationMode(true)" in script
            return json.dumps({
                "before": before, "after": self.mode,
                "frames": frames, "sim_time": sim_time,
            })
        if "resetSimulation" in script:
            return json.dumps({
                "simulation_mode": self.mode, "frames_before": frames,
                "frames_after": frames, "sim_time": sim_time, "current_index": 0,
            })
        if "__s.forward();" in script:
            if self.fail_step:
                return None
            before = frames
            self.forwards += 1
            sim_time, frames = self.point()
            return json.dumps({
                "simulation_mode": self.mode, "frames_before": before,
                "frames_after": frames, "sim_time": sim_time,
                "current_index": max(0, frames - 1),
            })
        if self.fail_state_once and self.forwards and not self.state_failure_emitted:
            self.state_failure_emitted = True
            return None
        return json.dumps({
            "mode": self.mode, "frames": frames, "sim_time": sim_time,
            "current_index": max(0, frames - 1),
        })


def restored_case(
    sim_times, *, frame_counts=None, fail_step=False, fail_state_once=False,
    clock=(0, 1, 2, 3, 4), **limits,
):
    bridge = Bridge(
        sim_times, frame_counts=frame_counts, fail_step=fail_step,
        fail_state_once=fail_state_once,
    )
    evidence = _post_failure_simulation_diagnostic(
        SimpleNamespace(send_and_wait=bridge), topology(), voice(),
        monotonic=Clock(clock), **limits,
    )
    return {
        "reason": evidence["progression"]["termination_reason"],
        "restoration_verified": evidence["restoration_verified"],
        "final_mode": bridge.mode,
        "captured": evidence["captured"],
        "trace_keys": sorted(
            key for key in evidence if key.endswith("_trace")
        ),
    }


common = {
    "target_sim_time_span": 100,
    "step_batch_size": 10,
    "hard_max_steps": 20,
    "hard_wall_clock_seconds": 120,
    "global_event_list_ceiling": 2500,
    "stall_batch_limit": 3,
}
verdict["restorations"] = {
    "target": restored_case([0, 100], **common),
    "max_steps": restored_case([0, 1, 2], **common),
    "wall": restored_case([0, 1], clock=(0, 121), **common),
    "events": restored_case([0, 1], frame_counts=[0, 2500], **common),
    "state_unobservable": restored_case(
        [0, 1], fail_state_once=True, **common,
    ),
    "sim_time_unobservable": restored_case([0, None], **common),
    "non_monotonic": restored_case([10, 9], **common),
    "stall": restored_case(
        [10, 10, 10, 10], hard_max_steps=60,
        **{key: value for key, value in common.items() if key != "hard_max_steps"},
    ),
    "step_failure": restored_case([0], fail_step=True, **common),
}

print(json.dumps(verdict))
'''


@pytest.fixture(scope="module")
def verdict():
    code = _PROBE.replace("__ROOT__", repr(str(ROOT))).replace(
        "__SRC__", repr(str(ROOT / "src")),
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_production_bounds_are_explicit_and_conservative(verdict):
    assert verdict["constants"] == {
        "target": 60_000,
        "batch": 10,
        "steps": 600,
        "wall": 120,
        "events": 2_500,
        "stall": 3,
    }


def test_target_span_is_measured_from_the_post_reset_pure_state(verdict):
    result = verdict["target"]["result"]

    assert result["termination_reason"] == "TARGET_SIM_TIME_SPAN_REACHED"
    assert result["simulation_time_start"] == 100
    assert result["simulation_time_end"] == 60100
    assert result["simulation_time_span"] == 60000
    assert result["steps_completed"] == 20
    assert result["batches_completed"] == 2


def test_each_batch_is_followed_by_a_pure_state_read(verdict):
    actions = verdict["target"]["actions"]

    assert actions == [
        ["read"],
        ["step", "forward", 10], ["read"],
        ["step", "forward", 10], ["read"],
    ]


def test_progress_retains_each_step_and_state_observation(verdict):
    progress = verdict["target"]["result"]["progress"]

    assert len(progress) == 2
    assert [item["batch"] for item in progress] == [1, 2]
    assert [item["steps_requested"] for item in progress] == [10, 10]
    assert [item["cumulative_steps"] for item in progress] == [10, 20]
    assert all(item["step"]["observed"] for item in progress)
    assert all(item["state"]["observed"] for item in progress)
    assert [item["wall_clock_elapsed_seconds"] for item in progress] == [1, 2]


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("target", "TARGET_SIM_TIME_SPAN_REACHED"),
        ("max_steps", "HARD_MAX_STEPS_REACHED"),
        ("wall", "HARD_WALL_CLOCK_REACHED"),
        ("events", "EVENT_LIST_CEILING"),
        ("unobservable", "SIMULATION_STATE_UNOBSERVABLE"),
        ("sim_time_unobservable", "SIM_TIME_UNOBSERVABLE"),
        ("non_monotonic", "SIM_TIME_NON_MONOTONIC"),
        ("stall", "SIM_TIME_STALLED"),
        ("step_failure", "STEP_FAILED"),
    ],
)
def test_every_terminal_condition_is_named(verdict, case, reason):
    assert verdict[case]["result"]["termination_reason"] == reason


def test_hard_step_ceiling_never_overshoots(verdict):
    result = verdict["max_steps"]["result"]

    assert result["steps_completed"] == 20
    assert result["batches_completed"] == 2
    assert all(item["steps_requested"] == 10 for item in result["progress"])


def test_wall_clock_ceiling_is_independent_of_simulation_progress(verdict):
    result = verdict["wall"]["result"]

    assert result["simulation_time_span"] == 1
    assert result["wall_clock_elapsed_seconds"] == 121
    assert result["steps_completed"] == 10


def test_global_event_ceiling_uses_the_unfiltered_frame_count(verdict):
    result = verdict["events"]["result"]

    assert result["global_frames_end"] == 2500
    assert result["steps_completed"] == 10
    assert result["progress"][-1]["state"]["frames"] == 2500


def test_positive_observations_survive_the_event_ceiling(verdict):
    result = verdict["events"]["result"]

    assert result["progress"][-1]["step"]["observed"] is True
    assert result["progress"][-1]["state"]["observed"] is True
    assert result["simulation_time_end"] == 1


def test_unobservable_start_never_attempts_a_step(verdict):
    assert verdict["unobservable"]["actions"] == [["read"]]
    assert verdict["unobservable"]["result"]["steps_completed"] == 0


def test_non_monotonic_time_retains_both_measured_values(verdict):
    result = verdict["non_monotonic"]["result"]

    assert result["simulation_time_start"] == 10
    assert result["simulation_time_end"] == 9
    assert result["progress"][-1]["state"]["sim_time"] == 9


def test_repeated_stall_is_bounded_by_consecutive_batches(verdict):
    result = verdict["stall"]["result"]

    assert result["stall_batches"] == 3
    assert result["batches_completed"] == 3
    assert result["steps_completed"] == 30


def test_a_refused_step_is_not_counted_as_completed(verdict):
    result = verdict["step_failure"]["result"]

    assert result["steps_completed"] == 0
    assert result["batches_completed"] == 0
    assert result["progress"][-1]["step"]["observed"] is False


def test_no_terminal_path_makes_negative_absence_interpretable(verdict):
    for case in (
        "target", "max_steps", "wall", "events", "unobservable",
        "sim_time_unobservable", "non_monotonic", "stall", "step_failure",
    ):
        result = verdict[case]["result"]
        assert result["negative_absence_interpretable"] is False, case


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("target", "TARGET_SIM_TIME_SPAN_REACHED"),
        ("max_steps", "HARD_MAX_STEPS_REACHED"),
        ("wall", "HARD_WALL_CLOCK_REACHED"),
        ("events", "EVENT_LIST_CEILING"),
        ("state_unobservable", "SIMULATION_STATE_UNOBSERVABLE"),
        ("sim_time_unobservable", "SIM_TIME_UNOBSERVABLE"),
        ("non_monotonic", "SIM_TIME_NON_MONOTONIC"),
        ("stall", "SIM_TIME_STALLED"),
        ("step_failure", "STEP_FAILED"),
    ],
)
def test_every_progression_terminal_path_restores_then_keeps_raw_scopes(
    verdict, case, reason,
):
    outcome = verdict["restorations"][case]

    assert outcome["reason"] == reason
    assert outcome["restoration_verified"] is True
    assert outcome["final_mode"] is False
    assert outcome["captured"] is True
    assert outcome["trace_keys"] == [
        "control_trace", "phone_trace", "router_trace", "switch_trace",
    ]


def test_runner_source_contains_no_dhcp_or_topology_mutator():
    source = (ROOT / "tools" / "cp_scale_canonical_live.py").read_text(
        encoding="utf-8",
    )
    start = source.index("def _post_failure_simulation_diagnostic")
    body = source[start:source.index("\ndef ", start + 10)]

    for forbidden in (
        "setDhcpClientFlag", "configurePcIp", "setIpAddress", "renew",
        "release", "lwAddDevice", "lwAddLink", "removeDevice", "pt_send_raw",
        "debug ip", "VerificationKind", "ConfigurationApplicationResult",
    ):
        assert forbidden not in body


def test_the_obsolete_fixed_step_budget_contract_is_gone():
    source = (ROOT / "tools" / "cp_scale_canonical_live.py").read_text(
        encoding="utf-8",
    )

    assert "_SIMULATION_STEP_BUDGET" not in source
    assert "step_budget" not in source


def test_handoff_names_the_new_bounded_window_and_keeps_live_open():
    handoff = (ROOT / "handoff.md").read_text(encoding="utf-8")

    assert "Simulation-time bounded DHCP diagnostic -- implemented, LIVE observed" in handoff
    assert "CURRENT_PUSHED_HEAD = 540c746711e3076793902d1b42ca160aa5a1d6ed" in handoff
    assert "ACCESS_PORT_VOICE_VLAN = VERIFIED 21/21" in handoff
    assert "data VLAN 10" in handoff and "voice VLAN 20" in handoff
    assert "TARGET_SIM_TIME_SPAN = 60000" in handoff
    assert "POSITIVE_CONTROL_CAPABILITY = UNSAFE_OR_MUTATING" in handoff
    assert "CP_SCALE_STATUS = OPEN / NOT VERIFIED" in handoff
