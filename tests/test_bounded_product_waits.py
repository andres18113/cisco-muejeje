"""Nested waits and the owned release under a caller-owned allowance.

The cold-HTTP envelope bounds one product invocation with one operation ledger.
A channel wrapper alone does not bound it: several product waiters catch a
refused call as "no answer" and keep polling on their own clock. These tests
pin the three optional controls that close that gap and prove that each one is
inert when it is not composed, so the ordinary MCP route keeps its behavior.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    LedgerPhase,
    OperationLedger,
    OperationRefused,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    CreateVlan,
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.discovery import (
    DeviceInitializationState,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)


class _Clock:
    """A monotonic clock that only a sleeper or a slow call advances."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += max(0.0, seconds)


class _RefusingChannel:
    """A channel whose owner stopped granting calls after `granted` of them."""

    def __init__(self, granted: int, answer: str) -> None:
        self.granted = granted
        self.answer = answer
        self.calls = 0
        self.refused = 0

    def __call__(self, script: str, timeout: float) -> str | None:
        del script, timeout
        if self.calls >= self.granted:
            self.refused += 1
            raise OperationRefused("operation_budget_exhausted")
        self.calls += 1
        return self.answer


_NOT_READY = json.dumps(
    {"found": True, "booting": True, "terminal": False, "terminal_available": False}
)
_VLAN_ABSENT = json.dumps(
    {"found": True, "configuration_channel": False, "present": False}
)


def _vlan_expectation() -> VerificationExpectation:
    return VerificationExpectation(
        id="verify/vlan/10",
        action_id="cfg/vlan/sw/10",
        kind=VerificationKind.VLAN,
        device_id="sw",
        device_name="SW",
        expected={"vlan_id": 10},
    )


def _vlan_action() -> CreateVlan:
    return CreateVlan(
        id="cfg/vlan/sw/10",
        phase=ConfigurationPhase.L2_DEFINITIONS,
        device_id="sw",
        device_name="SW",
        site_id="hq",
        vlan_id=10,
    )


def _inventory() -> list[dict]:
    return [{"name": "SW", "model": "IE-2000", "ports": [{"name": "Vlan1"}]}]


# -- E5 waits -----------------------------------------------------------------


def test_e5_readback_waits_end_when_the_callers_allowance_ends():
    """A refused read ends the wait at once; it is never polled until timeout."""
    clock = _Clock()
    channel = _RefusingChannel(granted=2, answer=_VLAN_ABSENT)
    allowance = {"seconds": 100.0}

    def remaining() -> float:
        return allowance["seconds"] if channel.refused == 0 else 0.0

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        _inventory,
        lambda script: True,
        channel,
        clock=clock,
        sleeper=clock.sleep,
        wait_allowance=remaining,
    )

    [row] = runtime.verify([_vlan_expectation()])

    assert channel.calls == 2
    assert channel.refused == 1
    # Two granted reads, one interval between them, and nothing after the
    # refusal: no sleep follows a spent allowance and no read is re-asked.
    assert clock.sleeps == [0.25, 0.25]
    assert row.convergence.attempts == 3
    assert clock.now == pytest.approx(0.5)


def test_e5_waits_keep_their_own_clock_when_no_control_is_composed():
    """Without the control, a composed clock stays the forwarding observer's."""
    clock = _Clock()
    present = json.dumps(
        {"found": True, "configuration_channel": True, "present": True}
    )
    answers = iter([_VLAN_ABSENT, present])
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        _inventory,
        lambda script: True,
        lambda script, timeout: next(answers),
        clock=clock,
        sleeper=clock.sleep,
    )

    [row] = runtime.verify([_vlan_expectation()])

    # The legacy waiter kept the module clock and sleeper, not the composed
    # ones, so an ordinary composition waits exactly as it did before.
    assert clock.sleeps == []
    assert row.convergence.attempts == 2


def test_ios_boot_wait_ends_with_the_callers_allowance_before_any_batch():
    """The 90-second boot wait is bounded by the control, not by its own clock."""
    clock = _Clock()
    channel = _RefusingChannel(granted=3, answer=_NOT_READY)
    sends: list[str] = []

    runtime = PacketTracerEnterpriseConfigurationRuntime(
        _inventory,
        sends.append,
        channel,
        clock=clock,
        sleeper=clock.sleep,
        wait_allowance=lambda: 0.0 if channel.refused else 300.0,
    )

    [mutation] = runtime.apply_actions([_vlan_action()])

    assert channel.calls == 3
    assert channel.refused == 1
    assert clock.sleeps == [0.25, 0.25, 0.25]
    assert mutation.applied is False
    assert sends == []


def test_wait_until_ready_accepts_optional_controls_and_keeps_its_defaults():
    """The executor passes controls through only when a caller supplies them."""
    clock = _Clock()
    reads: list[str] = []

    def not_ready(script: str, timeout: float) -> str:
        reads.append(script)
        return _NOT_READY

    executor = ControlledIosExecutor(not_ready)
    result = executor.wait_until_ready(
        "SW",
        timeout_seconds=1.0,
        interval_seconds=0.5,
        clock=clock,
        sleeper=clock.sleep,
        remaining_seconds=lambda: 0.0 if len(reads) >= 2 else 10.0,
    )

    assert result.state is DeviceInitializationState.TIMEOUT
    assert len(reads) == 2
    assert clock.sleeps == [0.5]


# -- owned release ------------------------------------------------------------


def _http_expectation() -> ServiceVerificationExpectation:
    return ServiceVerificationExpectation(
        id="verify/http/pc1",
        service_id="svc/http",
        action_id="svc/http/content",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="server",
        host_device_name="SERVER",
        client_device_id="pc1",
        client_device_name="PC1",
        expected={"scheme": "http", "address": "198.18.160.2", "marker": "M"},
    )


def _Outcome(body: str) -> BridgeDispatchOutcome:
    return BridgeDispatchOutcome(
        dispatch=DispatchFact.ACCEPTED, result=ResultFact.CORRELATED, body=body
    )


def test_the_owned_release_scope_encloses_exactly_the_release_dispatch():
    """Only the release runs inside the scope; start and inspection do not."""
    clock = _Clock()
    events: list[str] = []
    inside = {"depth": 0}

    @contextmanager
    def owned_release(expectation_id: str):
        events.append(f"enter:{expectation_id}")
        inside["depth"] += 1
        try:
            yield
        finally:
            inside["depth"] -= 1
            events.append(f"exit:{expectation_id}")

    def dispatch(script: str, timeout: float) -> BridgeDispatchOutcome:
        del timeout
        if "content_before:before" in script:
            events.append(f"start:{inside['depth']}")
            return _Outcome(
                json.dumps(
                    {
                        "started": True,
                        "go_result": True,
                        "go_result_type": "boolean",
                        "content_before": "",
                        "https_mode": False,
                        "https_mode_type": "boolean",
                        "owner_device": "PC1",
                        "owner_read": True,
                        "owned": True,
                    }
                )
            )
        if "var found=!!(slot&&slot.manager&&slot.client)" in script:
            events.append(f"release:{inside['depth']}")
            return _Outcome(
                json.dumps(
                    {"found": True, "deleted": True, "present": False, "error": ""}
                )
            )
        events.append(f"inspect:{inside['depth']}")
        return _Outcome(json.dumps({"found": True, "content": "page M"}))

    runtime = PacketTracerEnterpriseServiceRuntime(
        _inventory,
        lambda script, timeout: None,
        dispatch_and_wait=dispatch,
        clock=clock,
        sleeper=clock.sleep,
        owned_release=owned_release,
    )

    row = runtime.verify(_http_expectation())

    assert row.observed["released"] == "released"
    assert events == [
        "start:0",
        "inspect:0",
        "enter:verify/http/pc1",
        "release:1",
        "exit:verify/http/pc1",
    ]


def test_a_refused_owned_release_is_reported_as_unresolved_not_released():
    """A scope that declines the release leaves ownership explicitly unresolved."""

    @contextmanager
    def declined(expectation_id: str):
        del expectation_id
        raise OperationRefused("execution_authority_lost:campaign_claim")
        yield  # pragma: no cover - the scope refuses before yielding

    def dispatch(script: str, timeout: float) -> BridgeDispatchOutcome:
        del timeout
        if "content_before:before" in script:
            return _Outcome(
                json.dumps(
                    {
                        "started": True,
                        "go_result": True,
                        "go_result_type": "boolean",
                        "content_before": "",
                        "https_mode": False,
                        "https_mode_type": "boolean",
                        "owner_device": "PC1",
                        "owner_read": True,
                        "owned": True,
                    }
                )
            )
        return _Outcome(json.dumps({"found": True, "content": "page M"}))

    clock = _Clock()
    runtime = PacketTracerEnterpriseServiceRuntime(
        _inventory,
        lambda script, timeout: None,
        dispatch_and_wait=dispatch,
        clock=clock,
        sleeper=clock.sleep,
        owned_release=declined,
    )

    row = runtime.verify(_http_expectation())

    assert row.observed["released"] == "release_failed"
    assert (
        "client_ownership_unresolved:release_failed:exception:OperationRefused"
        in row.limitations
    )


# -- ledger protected release -------------------------------------------------


def _ledger(clock: _Clock, *, operations: int = 10, seconds: float = 100.0):
    ledger = OperationLedger(
        max_operations=operations, max_seconds=seconds, clock=clock
    )
    ledger.reserve(2, 40.0)
    ledger.enter(LedgerPhase.EXPERIMENT)
    return ledger


def test_a_protected_release_is_charged_to_the_reserve_not_the_ordinary_pool():
    """PC1's early release leaves every ordinary call PC2 needs."""
    clock = _Clock()
    ledger = _ledger(clock)
    for _ in range(3):
        ledger.admit("send_and_wait", 1.0)
    with ledger.protected_release():
        ledger.admit("dispatch_and_wait", 3.0)

    operations, seconds = ledger.allowance()

    assert ledger.used == 4
    assert ledger.reserve_used == 1
    # 10 - 2 reserved - 3 ordinary; the release did not come out of these.
    assert operations == 5
    assert seconds == pytest.approx(60.0)
    assert ledger.entries[-1].phase == "protected_release"
    # The scope ended with its dispatch: the next call is ordinary again.
    ledger.admit("send_and_wait", 1.0)
    assert ledger.entries[-1].phase == LedgerPhase.EXPERIMENT.value


def test_after_ordinary_exhaustion_only_protected_releases_are_admitted():
    """The reserve is reachable by owned releases and by nothing else."""
    clock = _Clock()
    ledger = _ledger(clock, operations=5)
    for _ in range(3):
        ledger.admit("send_and_wait", 1.0)
    with pytest.raises(OperationRefused, match="operation_budget_exhausted"):
        ledger.admit("send_and_wait", 1.0)
    with ledger.protected_release():
        ledger.admit("dispatch_and_wait", 3.0)
    with ledger.protected_release():
        ledger.admit("dispatch_and_wait", 3.0)
    with pytest.raises(OperationRefused, match="protected_reserve_exhausted"):
        with ledger.protected_release():
            ledger.admit("dispatch_and_wait", 3.0)

    assert ledger.used == 5
    assert ledger.reserve_used == 2
    assert ledger.refused_calls == 2


def test_a_protected_release_uses_the_reserved_seconds_capped_by_the_deadline():
    """Past the ordinary deadline a release still has the absolute one."""
    clock = _Clock()
    ledger = _ledger(clock)
    clock.now = 61.0
    with pytest.raises(OperationRefused, match="time_budget_exhausted"):
        ledger.admit("send_and_wait", 1.0)
    with ledger.protected_release():
        index, timeout = ledger.admit("dispatch_and_wait", 3.0)
    assert timeout == pytest.approx(3.0)
    assert ledger.entries[index].timeout_seconds == pytest.approx(3.0)
    clock.now = 99.0
    with ledger.protected_release():
        _index, timeout = ledger.admit("dispatch_and_wait", 3.0)
    assert timeout == pytest.approx(1.0)


def test_a_protected_release_still_asks_the_effect_guard():
    """Remaining reserve never authorizes a dispatch after authority is lost."""
    clock = _Clock()
    ledger = _ledger(clock)
    ledger.bind_effect_guard(lambda purpose, deadline: "campaign_claim:lost")
    with ledger.effect_of("product"):
        with pytest.raises(OperationRefused, match="execution_authority_lost"):
            with ledger.protected_release():
                ledger.admit("dispatch_and_wait", 3.0)
    assert ledger.reserve_used == 0


def test_without_protected_releases_the_ledger_arithmetic_is_unchanged():
    """The qualification stages never enter the scope and see the old ledger."""
    clock = _Clock()
    ledger = _ledger(clock)
    for _ in range(8):
        ledger.admit("send_and_wait", 1.0)
    with pytest.raises(OperationRefused, match="operation_budget_exhausted"):
        ledger.admit("send_and_wait", 1.0)
    ledger.enter(LedgerPhase.FINALIZATION)
    assert ledger.allowance()[0] == 2
    ledger.admit("send_and_wait", 1.0)
    ledger.admit("send_and_wait", 1.0)
    assert ledger.reserve_used == 0
    assert ledger.allowance()[0] == 0
