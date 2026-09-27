"""SP-1 A-3: E5 reads a static route back from a fresh routing table.

The IOS executor is the replaced boundary; the runtime's own convergence,
parsing and decision run unchanged. A route is VERIFIED only when a fresh,
complete table carries exactly the planned static next hop for the exact
prefix; an absent or contradicting row is FAILED, and an unreadable table is
UNOBSERVABLE, never a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)

_HEADER = "Gateway of last resort is not set\n\n"


@dataclass
class _Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(seconds, 0.25)


@dataclass
class _Ios:
    outputs: list[IosCommandResult]
    asked: list[tuple[str, OperationalQueryId]] = field(default_factory=list)

    def execute(self, device_name, query_id, *args, **kwargs):
        self.asked.append((device_name, query_id))
        return self.outputs[min(len(self.asked), len(self.outputs)) - 1]


def _result(output: str, *, complete: bool = True, fresh: bool = True):
    return IosCommandResult(
        device_name="BR2",
        query_id=OperationalQueryId.SHOW_IP_ROUTE,
        executed=True,
        output=output,
        fresh_output_observed=fresh,
        output_complete=complete,
    )


def _expectation() -> VerificationExpectation:
    return VerificationExpectation(
        id="verify-route",
        action_id="route",
        kind=VerificationKind.STATIC_ROUTE,
        device_id="r-br2",
        device_name="BR2",
        expected={"network": "10.40.0.8", "prefix": 29, "next_hop": "10.40.0.33"},
        required_query="show_ip_route",
    )


def _verify(*outputs: IosCommandResult):
    clock = _Clock()
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        l3_timeout_seconds=1.0,
        clock=clock,
        sleeper=clock.sleep,
        wait_allowance=lambda: 100.0,
    )
    ios = _Ios(list(outputs))
    runtime._ios = ios
    [row] = runtime.verify([_expectation()])
    return row, ios


def test_the_planned_static_route_is_verified():
    """The exact prefix via the planned next hop, in a fresh complete table."""
    row, ios = _verify(_result(_HEADER + "S       10.40.0.8/29 [1/0] via 10.40.0.33\n"))

    assert row.status is ActionExecutionStatus.VERIFIED
    assert row.fresh_evidence and row.evidence_method == "fresh_show_ip_route"
    assert ios.asked == [("BR2", OperationalQueryId.SHOW_IP_ROUTE)]


def test_a_route_installed_late_is_verified_within_the_window():
    """Installation after the egress link comes up is convergence, not failure."""
    row, ios = _verify(
        _result(_HEADER),
        _result(_HEADER + "S       10.40.0.8/29 [1/0] via 10.40.0.33\n"),
    )

    assert row.status is ActionExecutionStatus.VERIFIED
    assert len(ios.asked) == 2


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ("", "static_route_absent"),
        (
            "S       10.40.0.8/29 [1/0] via 10.40.0.37\n",
            "static_route_next_hop_differs:10.40.0.37",
        ),
        (
            "S       10.40.0.8/29 [1/0] via 10.40.0.33\n"
            "                [1/0] via 10.40.0.37\n",
            "static_route_next_hop_differs:10.40.0.33,10.40.0.37",
        ),
    ],
)
def test_an_absent_or_contradicting_route_is_failed(rows, reason):
    """A fresh complete table that lacks or contradicts the route."""
    row, _ios = _verify(_result(_HEADER + rows))

    assert row.status is ActionExecutionStatus.FAILED
    assert row.message == reason


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (
            _result(
                _HEADER + "S       10.40.0.8/29 [1/0] via 10.40.0.33\n", complete=False
            ),
            "route_table_incomplete",
        ),
        (
            _result(
                _HEADER + "S       10.40.0.8/29 [1/0] via 10.40.0.33\n", fresh=False
            ),
            "route_table_not_fresh",
        ),
        (
            _result("S       10.40.0.8/29 [1/0] via 10.40.0.33\n"),
            "route_table_unparsed",
        ),
        (_result("Default gateway is not set\n"), "ipv4_routing_disabled"),
    ],
)
def test_an_unreadable_table_is_unobservable_not_failed(result, reason):
    """A paged, stale, headerless or routing-off answer proves nothing."""
    row, _ios = _verify(result)

    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.message == reason
