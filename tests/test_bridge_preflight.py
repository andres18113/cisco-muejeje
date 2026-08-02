"""Preflight E3.6: bootstrap oficial antes de cualquier probe mutante."""

from src.packet_tracer_mcp.infrastructure.execution.bridge_preflight import (
    BridgePreflightState,
    BridgeReadinessPreflight,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeBridge:
    def __init__(
        self,
        *,
        active: bool = False,
        bootstrap_result: bool = True,
        activate_on_bootstrap: bool = True,
        token_ready: bool = True,
    ) -> None:
        self.active = active
        self.bootstrap_result = bootstrap_result
        self.activate_on_bootstrap = activate_on_bootstrap
        self.token_ready = token_ready
        self.bootstrap_calls = 0

    def bootstrap(self) -> bool:
        self.bootstrap_calls += 1
        if self.bootstrap_result and self.activate_on_bootstrap:
            self.active = True
        return self.bootstrap_result


def _preflight(bridge: FakeBridge, clock: FakeClock | None = None) -> BridgeReadinessPreflight:
    clock = clock or FakeClock()
    return BridgeReadinessPreflight(
        mcp_server_ready=lambda: True,
        bridge_ready=lambda: bridge.active,
        bootstrap_bridge=bridge.bootstrap,
        token_ready=lambda: bridge.token_ready,
        timeout_s=0.5,
        poll_interval_s=0.1,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def test_preflight_accepts_an_already_active_bridge_without_bootstrap():
    bridge = FakeBridge(active=True)

    result = _preflight(bridge).ensure_ready()

    assert result.state is BridgePreflightState.READY
    assert bridge.bootstrap_calls == 0


def test_preflight_bootstraps_an_inactive_bridge_and_rechecks_readiness():
    bridge = FakeBridge()

    result = _preflight(bridge).ensure_ready()

    assert result.state is BridgePreflightState.READY
    assert bridge.bootstrap_calls == 1
    assert result.attempts == 1


def test_preflight_reports_failed_official_bootstrap():
    bridge = FakeBridge(bootstrap_result=False)

    result = _preflight(bridge).ensure_ready()

    assert result.state is BridgePreflightState.BRIDGE_START_FAILED
    assert bridge.bootstrap_calls == 1


def test_preflight_times_out_when_bridge_does_not_become_ready():
    bridge = FakeBridge(activate_on_bootstrap=False)
    clock = FakeClock()

    result = _preflight(bridge, clock).ensure_ready()

    assert result.state is BridgePreflightState.BRIDGE_START_TIMEOUT
    assert bridge.bootstrap_calls == 1
    assert clock.now == 0.5


def test_preflight_rejects_missing_token_after_successful_bootstrap():
    bridge = FakeBridge(token_ready=False)

    result = _preflight(bridge).ensure_ready()

    assert result.state is BridgePreflightState.BRIDGE_TOKEN_MISSING
    assert bridge.bootstrap_calls == 1


def test_preflight_never_runs_probes_when_bridge_is_not_ready():
    bridge = FakeBridge(bootstrap_result=False)
    probes: list[str] = []

    result, value = _preflight(bridge).execute_if_ready(lambda: probes.append("probe"))

    assert result.state is BridgePreflightState.BRIDGE_START_FAILED
    assert value is None
    assert probes == []
