"""Fresh DHCP evidence must arrive inside finite read and acquisition bounds."""

import json
from types import SimpleNamespace

import pytest
from test_native_dhcp_group_evidence import (
    MAC,
    _address,
    _assigned,
    _group_expectations,
    _row,
    _runtime,
    _scan,
    _ScriptedBridge,
    _verify_group,
)
from test_service_dhcp_script_harness import (
    _native_state_expectation,
    _prime_native_usable,
)
from test_service_dhcp_script_harness import (
    _runtime as _single_runtime,
)
from test_service_dhcp_script_harness import (
    engine as _engine_fixture,
)

from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ActionExecutionStatus,
)


@pytest.fixture
def engine(tmp_path):
    """Reuse the actual persistent engine fixture and its bounded teardown."""
    yield from _engine_fixture.__wrapped__(tmp_path)


def _timed_group(monkeypatch, *, server_seconds, snapshot_seconds, allowance=None):
    expectations, group = _group_expectations()
    scan = _scan(
        group,
        {"PC1": _assigned("PC1", 0), "PC2": _assigned("PC2", 1)},
        [_row(_address(0), MAC["PC1"]), _row(_address(1), MAC["PC2"])],
    )
    clock = SimpleNamespace(value=0.0)
    bridge = _ScriptedBridge([scan, scan, scan])
    original = bridge.dispatch_and_wait

    def dispatch(script, timeout):
        result = original(script, timeout)
        clock.value += snapshot_seconds
        return result

    bridge.dispatch_and_wait = dispatch
    runtime = _runtime(monkeypatch, bridge)
    runtime._clock = lambda: clock.value
    runtime._dhcp_state_interval = 10.0
    runtime._dhcp_state_wait_allowance = (
        (lambda: allowance) if allowance is not None else None
    )

    def server(_expectation):
        clock.value += server_seconds
        return SimpleNamespace(
            status=ActionExecutionStatus.VERIFIED,
            observed={"native_policy_json": "{}"},
        )

    def sleep(seconds):
        clock.value += seconds

    monkeypatch.setattr(runtime, "_verify_dhcp_server_state", server)
    runtime._sleep = sleep
    return _verify_group(runtime, expectations), bridge, clock


def test_group_sampling_records_actual_work_and_keeps_the_existing_wait_cadence(
    monkeypatch,
):
    """Reader time is additional work; twelve waits never define a wall deadline."""
    results, bridge, clock = _timed_group(
        monkeypatch, server_seconds=1.0, snapshot_seconds=1.0
    )

    assert {row.status for row in results.values()} == {ActionExecutionStatus.VERIFIED}
    assert clock.value == 14.0
    window = json.loads(results["PC1"].observed["group_window_json"])
    assert window["wall_limit_seconds"] == 59.0
    assert window["max_samples"] == 3
    assert window["interval_seconds"] == 10.0
    assert [row["started_seconds"] for row in window["samples"]] == [0.0, 12.0]
    assert [row["server_seconds"] for row in window["samples"]] == [1.0, 1.0]
    assert [row["snapshot_seconds"] for row in window["samples"]] == [1.0, 1.0]
    assert len(bridge.scans) == 1
    assert "group_window_json" not in results["PC2"].observed


@pytest.mark.parametrize(
    ("server_seconds", "snapshot_seconds"), [(9.0, 0.0), (0.0, 9.0)]
)
def test_a_late_positive_read_cannot_verify_the_group(
    monkeypatch, server_seconds, snapshot_seconds
):
    """A correlated positive returned after its own read bound is late evidence."""
    results, _bridge, _clock = _timed_group(
        monkeypatch,
        server_seconds=server_seconds,
        snapshot_seconds=snapshot_seconds,
    )

    assert {row.status for row in results.values()} == {ActionExecutionStatus.UNKNOWN}
    assert {row.cause for row in results.values()} == {"native_group_read_late"}
    window = json.loads(results["PC1"].observed["group_window_json"])
    assert len(window["samples"]) == 1


def test_current_phase_allowance_caps_acquisition_work_and_rejects_a_late_answer(
    monkeypatch,
):
    """The work-derived window cannot spend time protected by the caller's ledger."""
    results, _bridge, clock = _timed_group(
        monkeypatch, server_seconds=4.0, snapshot_seconds=7.0, allowance=10.0
    )

    assert clock.value == 11.0
    assert {row.status for row in results.values()} == {ActionExecutionStatus.UNKNOWN}
    assert {row.cause for row in results.values()} == {"native_group_window_elapsed"}
    window = json.loads(results["PC1"].observed["group_window_json"])
    assert window["wall_limit_seconds"] == 10.0
    assert window["work_limit_seconds"] == 59.0
    trace = json.loads(results["PC1"].observed["group_trace_json"])
    assert trace[0]["lease_snapshot"]["clients"][0]["ipv4"] == _address(0)


def test_single_client_window_records_actual_reader_work(engine):
    """A single client includes its inactive, client and attribution reads."""
    item = engine()
    _prime_native_usable(item)
    clock = SimpleNamespace(value=0.0)
    original = item.dispatch_and_wait

    def dispatch(script, timeout):
        outcome = original(script, timeout)
        clock.value += 1.0
        return outcome

    item.dispatch_and_wait = dispatch
    runtime = _single_runtime(item)
    runtime._clock = lambda: clock.value
    runtime._sleep = lambda seconds: setattr(clock, "value", clock.value + seconds)
    runtime._dhcp_state_max_samples = 3

    result = runtime.verify(_native_state_expectation())

    assert result.status is ActionExecutionStatus.VERIFIED
    window = json.loads(result.observed["sampling_window_json"])
    assert window["work_limit_seconds"] == 89.0
    assert clock.value == 18.0
    assert len(window["samples"]) == 2


def test_a_single_client_late_positive_pool_row_cannot_open_services(engine):
    """The actual generated attribution read is refused after its five-second bound."""
    item = engine()
    _prime_native_usable(item)
    clock = SimpleNamespace(value=0.0)
    original = item.dispatch_and_wait

    def dispatch(script, timeout):
        outcome = original(script, timeout)
        if "getLeaseAt" in script:
            clock.value += 6.0
        return outcome

    item.dispatch_and_wait = dispatch
    runtime = _single_runtime(item)
    runtime._clock = lambda: clock.value
    runtime._sleep = lambda seconds: setattr(clock, "value", clock.value + seconds)
    runtime._dhcp_state_max_samples = 3

    result = runtime.verify(_native_state_expectation())

    assert result.status is ActionExecutionStatus.UNKNOWN
    assert result.cause == "native_state_read_late"
    assert result.observed["samples"] == 1
    window = json.loads(result.observed["sampling_window_json"])
    assert window["samples"][0]["attribution_seconds"] == 6.0
