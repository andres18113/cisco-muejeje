"""One readiness sample must be able to finish the table the build prints.

The second C31 attempt (`e0a7dfe16198cb14809fd78dcbb8003a`) dispatched no HTTP
request: both access groups ended with every sample exhausted at six nested
calls. Its own journal holds the answers, and they are replayed here byte for
byte through the real `ControlledIosExecutor` and the runtime's bounded
forwarding channel. A 2950T-24 with VLAN 1 and VLAN 10 prints `show
spanning-tree` as two pages; a clean read of two pages costs seven calls, so
the continuation key was always the last call a sample could make.

Nothing here assigns a row, a state or an admission. The only inputs are the
original terminal bytes and the native way the build rewrote them on the
continuation and cancel keys, both taken from the same journal.
"""

from __future__ import annotations

import json
from pathlib import Path

from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    READINESS_EPISODE_CALLS,
    READINESS_GROUP_DEADLINE_SECONDS,
    READINESS_GROUP_INTERVAL_SECONDS,
    READINESS_GROUP_MAX_SAMPLES,
    READINESS_SAMPLE_CALLS,
)
from packet_tracer_mcp.domain.enterprise.services.access_forwarding import (
    access_forwarding_admission,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)

_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "packet_tracer_9_0_1_0858_c31_spanning_tree_pages.json"
)
_NATIVE = json.loads(_FIXTURE.read_text(encoding="utf-8"))
_RULES = _NATIVE["native_rules"]
_SW01 = "HQ-DEFAULT-ACCESS-SW-01"
_SW02 = "HQ-DEFAULT-ACCESS-SW-02"
#: The requested access interfaces of the original groups, from the product
#: record's reasons: 24 on SW-01 and 7 on SW-02.
_SW01_PORTS = tuple(f"FastEthernet0/{index}" for index in range(1, 25))
_SW02_PORTS = (
    "FastEthernet0/1",
    *(f"FastEthernet0/{index}" for index in range(10, 16)),
)
_ORIGINAL_SAMPLE_CALLS = 6


class _NativeTerminal:
    """One device's TerminalLine, answering with the journal's own bytes."""

    def __init__(self, device_name: str, *, pages: tuple[str, ...] | None = None):
        switch = _NATIVE["switches"][device_name]
        self.device_name = device_name
        self.prompt = switch["prompt"]
        self.output = switch["baseline"]
        self.pages = pages or (switch["first_page"], switch["continuation"])
        self.index = -1
        self.calls: list[str] = []

    def _pager_active(self) -> bool:
        return self.output.endswith(_RULES["marker_removed_by_cancel_key"])

    def leave_first_page_active(self) -> None:
        """Reproduce what an exhausted sample leaves: its first page, unread."""
        self.output += self.pages[0]
        self.index = 0

    def __call__(self, js: str, _timeout: float) -> str:
        self.calls.append(js)
        if "String.fromCharCode(32)" in js:
            marker = _RULES["marker_removed_by_continuation_key"]
            if self._pager_active() and self.index + 1 < len(self.pages):
                self.index += 1
                self.output = self.output[: -len(marker)] + self.pages[self.index]
            return '{"ok":true}'
        if "String.fromCharCode(3)" in js:
            if self._pager_active():
                marker = _RULES["marker_removed_by_cancel_key"]
                self.output = self.output[: -len(marker)]
            self.output += _RULES["text_appended_by_cancel_key"]
            self.index = -1
            return '{"ok":true}'
        if "terminal_kind:'ios_command_line'" in js:
            return json.dumps(
                {
                    "found": True,
                    "booting": False,
                    "terminal": True,
                    "terminal_available": True,
                    "terminal_kind": "ios_command_line",
                    "prompt": self.prompt,
                    "output": self.output,
                }
            )
        if 'enterCommand("show spanning-tree")' in js:
            if self._pager_active():
                return json.dumps(
                    {"ok": False, "reason": "prompt_not_ready:pager_active"}
                )
            before = self.output
            self.output += self.pages[0]
            self.index = 0
            return json.dumps(
                {"ok": True, "before": before, "expected_prompt": self.prompt}
            )
        if "owner_candidate_names" in js:
            return json.dumps(
                {
                    "found": True,
                    "configuration_channel": True,
                    "output": self.output,
                    "owner_name": self.device_name,
                    "owner_evidence": "session_transcript_continuity",
                    "owner_candidates": 1,
                    "owner_candidate_evidence": "session_transcript_continuity",
                    "owner_candidate_names": [self.device_name],
                    "device_count": 36,
                }
            )
        if "configuration_channel" in js:
            return json.dumps(
                {"found": True, "configuration_channel": True, "output": self.output}
            )
        raise AssertionError(f"unexpected terminal interaction: {js[:120]}")


class _Clock:
    """Each answer costs the measured ~0.22 s; sleeps advance the same clock."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


class _Unobserved:
    observed = False


def _observe(
    terminal: _NativeTerminal,
    ports,
    *,
    sample_calls: int,
    samples: int = 1,
    episode_calls: int | None = READINESS_EPISODE_CALLS,
):
    clock = _Clock()

    def answered(js: str, timeout: float) -> str:
        clock.now += 0.22
        return terminal(js, timeout)

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=answered,
        clock=clock,
        sleeper=clock.sleep,
        simulation_time_observer=lambda: _Unobserved(),
    )
    return runtime.observe_access_forwarding(
        terminal.device_name,
        10,
        list(ports),
        remaining_seconds=READINESS_GROUP_DEADLINE_SECONDS,
        max_samples=samples,
        deadline_seconds=READINESS_GROUP_DEADLINE_SECONDS,
        interval_seconds=READINESS_GROUP_INTERVAL_SECONDS,
        sample_calls=sample_calls,
        episode_calls=episode_calls,
    )


def test_six_calls_reproduce_the_original_refusal_of_a_forwarding_switch():
    """The first SW-01 sample of the journal, with its original six calls."""
    terminal = _NativeTerminal(_SW01)

    observation = _observe(
        terminal, _SW01_PORTS, sample_calls=_ORIGINAL_SAMPLE_CALLS, episode_calls=None
    )

    assert observation.sample_budget_exhausted is True
    assert observation.failure_reason == "sample_call_budget_exhausted"
    assert observation.rows == ()
    assert access_forwarding_admission(observation).admitted is False
    # The sixth call was the continuation key, exactly as in sequence 174;
    # the table it completed was never read by this sample.
    assert "String.fromCharCode(32)" in terminal.calls[5]
    assert terminal.output.endswith("Switch>\nSwitch>")


def test_the_gate_sample_finishes_the_native_two_page_table_and_admits():
    """The same bytes at the gate's ceiling: all 24 rows read, all FWD."""
    terminal = _NativeTerminal(_SW01)

    observation = _observe(terminal, _SW01_PORTS, sample_calls=READINESS_SAMPLE_CALLS)

    assert observation.sample_budget_exhausted is False
    assert observation.output_complete is True
    assert observation.fresh_output_observed is True
    assert [row.state for row in observation.rows] == ["FWD"] * 24
    assert observation.episode_end_reason == (
        "all_requested_interfaces_observed_forwarding"
    )
    assert access_forwarding_admission(observation).admitted is True
    assert observation.sample_history[0].channel_calls == 7


def test_a_pager_left_by_an_exhausted_sample_is_isolated_inside_one_sample():
    """The steady state of the original loop no longer starves every sample."""
    terminal = _NativeTerminal(_SW01)
    terminal.leave_first_page_active()

    observation = _observe(terminal, _SW01_PORTS, sample_calls=READINESS_SAMPLE_CALLS)

    assert any("String.fromCharCode(3)" in call for call in terminal.calls)
    assert observation.sample_budget_exhausted is False
    assert access_forwarding_admission(observation).admitted is True
    assert observation.sample_history[0].channel_calls == 10


def test_a_learning_switch_stays_a_refusal_after_a_complete_read():
    """SW-02 at 30.6 s was LRN; reading it completely does not admit it."""
    terminal = _NativeTerminal(_SW02)

    observation = _observe(terminal, _SW02_PORTS, sample_calls=READINESS_SAMPLE_CALLS)
    admission = access_forwarding_admission(observation)

    assert observation.output_complete is True
    assert {row.state for row in observation.rows} == {"LRN"}
    assert admission.admitted is False
    assert admission.forwarding_interfaces == ()


def test_a_table_longer_than_the_ceiling_still_fails_closed():
    """More pages than one sample can pay for is an unobserved sample."""
    switch = _NATIVE["switches"][_SW01]
    marker = _RULES["marker_removed_by_cancel_key"]
    middle = tuple(
        "".join(f"page {page} line {line}\n" for line in range(20)) + marker
        for page in range(12)
    )
    pages = (switch["first_page"], *middle, switch["continuation"])
    terminal = _NativeTerminal(_SW01, pages=pages)

    observation = _observe(terminal, _SW01_PORTS, sample_calls=READINESS_SAMPLE_CALLS)

    assert observation.sample_budget_exhausted is True
    assert observation.rows == ()
    assert access_forwarding_admission(observation).admitted is False


def test_the_gate_ceiling_is_the_named_composition_of_one_registered_read():
    """The constant is derived from the executor's calls, not chosen."""
    from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
        READINESS_PAGE_ALLOWANCE,
    )
    from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
        registered_read_call_ceiling,
    )

    assert registered_read_call_ceiling(1) == 9
    assert registered_read_call_ceiling(2) == 13
    assert registered_read_call_ceiling(3) == 16
    assert READINESS_SAMPLE_CALLS == registered_read_call_ceiling(
        READINESS_PAGE_ALLOWANCE
    )


def test_the_episode_allowance_bounds_every_sample_together():
    """A switch that never forwards cannot spend more than the episode allows.

    Each sample may borrow up to sixteen calls to finish its table, but all
    of them together stop at the episode allowance, and the sample that finds
    less than a whole read left ends exhausted rather than admitted.
    """
    terminal = _NativeTerminal(_SW02)

    observation = _observe(
        terminal,
        _SW02_PORTS,
        sample_calls=READINESS_SAMPLE_CALLS,
        samples=READINESS_GROUP_MAX_SAMPLES,
        episode_calls=20,
    )

    assert observation.channel_calls == 20
    assert len(terminal.calls) == 20
    assert observation.episode_end_reason == "episode_call_budget_exhausted"
    assert observation.episode_budget_exhausted is True
    assert observation.simulation_time == "not_sampled_call_budget"
    assert [item.channel_calls for item in observation.sample_history] == [7, 7, 6]
    assert observation.sample_history[-1].sample_budget_exhausted is True
    assert access_forwarding_admission(observation).admitted is False


def test_the_gate_passes_the_per_sample_ceiling_and_the_episode_allowance():
    """The product gate hands both bounds to its observer, every group."""
    from service_entry_fixture import ForwardingBackend

    from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
        ServiceAccessReadinessGate,
    )
    from tests.test_service_access_readiness import SWITCH, SWITCH_NAME, _plan

    backend = ForwardingBackend(forwards_at=0.0)
    gate = ServiceAccessReadinessGate(
        _plan(), backend, clock=backend.clock, device_names={SWITCH: SWITCH_NAME}
    )

    gate.decide("http-1")

    assert backend.limits[0]["sample_calls"] == READINESS_SAMPLE_CALLS
    assert backend.limits[0]["episode_calls"] == READINESS_EPISODE_CALLS
