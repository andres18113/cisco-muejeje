"""The qualification's caller budget reaches its nested configuration waits."""

from packet_tracer_mcp.adapters.cli.service_qualification import _configuration_runtime
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    LedgeredTransport,
    OperationLedger,
)
from packet_tracer_mcp.infrastructure.execution.device_lifecycle import (
    DeviceReadinessWaiter,
)


class _Clock:
    value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def test_exhausted_caller_budget_stops_nested_configuration_wait():
    """A wait cannot spend real time after its owned allowance is exhausted."""
    clock = _Clock()
    ledger = OperationLedger(max_operations=2, max_seconds=1, clock=clock)
    bound = LedgeredTransport(ledger, object(), clock.sleep, clock)
    runtime = _configuration_runtime(bound)
    clock.value = 1.0
    observations = []

    def inspect():
        observations.append(True)
        return {"found": True, "configuration_channel": False}

    result = DeviceReadinessWaiter(
        inspect,
        timeout_seconds=0.1,
        interval_seconds=0.01,
        **runtime._wait_controls(),
    ).wait()
    assert result.attempts == 1
    assert observations == [True]
    assert ledger.used == 0


def test_hostname_wait_stops_at_phase_deadline_and_keeps_cleanup_reserve():
    """A final failed read spends no additional calls or protected cleanup time."""
    import json

    from packet_tracer_mcp.application.use_cases.qualify_server_services import (
        LedgerPhase,
    )
    from packet_tracer_mcp.domain.enterprise.models.configuration import (
        VerificationExpectation,
        VerificationKind,
    )
    from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
        ActionExecutionStatus,
    )

    clock = _Clock()
    calls, sleeps = [], []
    ledger = OperationLedger(max_operations=10, max_seconds=10, clock=clock)
    ledger.reserve(2, 3)
    ledger.enter(LedgerPhase.EXPERIMENT)

    class Transport:
        def send_and_wait(self, _script, _timeout):
            calls.append(True)
            clock.value += 7
            return json.dumps({"found": True, "hostname": "wrong"})

    def sleep(seconds):
        sleeps.append(seconds)
        clock.sleep(seconds)

    bound = LedgeredTransport(ledger, Transport(), sleep, clock)
    runtime = _configuration_runtime(bound)
    expectation = VerificationExpectation(
        id="hostname",
        action_id="set-hostname",
        kind=VerificationKind.HOSTNAME,
        device_id="router",
        device_name="Router",
        expected={"hostname": "Router"},
    )
    result = runtime._verify_hostname(expectation)
    assert result.status is ActionExecutionStatus.FAILED
    assert calls == [True]
    assert sleeps == []
    assert ledger.allowance()[1] == 0
    ledger.enter(LedgerPhase.FINALIZATION)
    assert ledger.allowance() == (9, 3.0)
