"""Common-session DHCP readers obey the caller's enclosing allowance."""

import json
from types import SimpleNamespace

import pytest

from packet_tracer_mcp.adapters.service_session import SessionControls
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ActionExecutionStatus,
)
from tests.test_cold_http_acceptance_boundaries import _Callables, _compose
from tests.test_service_dhcp_script_harness import (
    _native_state_expectation,
    _prime_native_usable,
)
from tests.test_service_dhcp_script_harness import (
    engine as _engine_fixture,
)


@pytest.fixture
def engine(tmp_path):
    """Use the persistent Node engine with bounded owned teardown."""
    yield from _engine_fixture.__wrapped__(tmp_path)


def test_common_session_passes_the_enclosing_allowance_to_e6(tmp_path):
    """The shared E6 runtime cannot invent a longer acquisition allowance."""

    def allowance():
        return 0.25

    binding = _compose(
        _Callables(), tmp_path, SessionControls(wait_allowance=allowance)
    )()
    assert binding.runtimes.services._dhcp_state_wait_allowance is allowance
    window = binding.runtimes.services._dhcp_sampling_window([5.0, 8.0])
    assert window["wall_limit_seconds"] == 0.25


def test_real_generated_reader_work_spends_the_common_session_allowance(
    engine, tmp_path
):
    """A retained positive lease cannot verify after the enclosing allowance."""
    item = engine()
    _prime_native_usable(item)
    clock = SimpleNamespace(value=0.0)
    calls = _Callables()
    original = item.dispatch_and_wait

    def dispatch(script, timeout, channel):
        answer = original(script, timeout)
        clock.value += 0.2
        return answer

    calls.dispatch_and_wait = dispatch
    runtime = _compose(
        calls,
        tmp_path,
        SessionControls(
            clock=lambda: clock.value,
            sleeper=lambda seconds: setattr(clock, "value", clock.value + seconds),
            wait_allowance=lambda: max(0.0, 0.25 - clock.value),
        ),
    )().runtimes.services
    result = runtime.verify(_native_state_expectation())
    assert result.status is not ActionExecutionStatus.VERIFIED
    window = json.loads(result.observed["sampling_window_json"])
    assert window["wall_limit_seconds"] <= 0.25
    assert result.observed["samples"] == 1
