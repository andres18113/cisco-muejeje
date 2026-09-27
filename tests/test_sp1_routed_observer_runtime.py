"""SP-1 A-5: the E5 runtime's routed-forwarding observer.

The IOS executor is replaced (it is the boundary to Packet Tracer); the
runtime's own round loop, window, attribution merge and parsing run. Two
registered reads per router per round, nothing else dispatched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packet_tracer_mcp.domain.enterprise.models.routed_forwarding import (
    CONFIRMED_UNIQUE_IDENTITY,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)

_BRIEF = (
    "Interface              IP-Address      OK? Method Status                Protocol\n"
    "GigabitEthernet0/0     10.12.0.1       YES manual up                    up\n"
    "GigabitEthernet0/1     10.1.0.1        YES manual up                    up\n"
)
_ROUTES = (
    "Gateway of last resort is not set\n\n"
    "     10.0.0.0/8 is variably subnetted, 3 subnets, 2 masks\n"
    "C       10.1.0.0/24 is directly connected, GigabitEthernet0/1\n"
    "C       10.12.0.0/30 is directly connected, GigabitEthernet0/0\n"
    "S       10.3.0.0/24 [1/0] via 10.12.0.2\n"
)


@dataclass
class _Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class _Ios:
    clock: _Clock
    answers: dict[tuple[str, OperationalQueryId], IosCommandResult]
    asked: list[tuple[str, OperationalQueryId]] = field(default_factory=list)

    def execute(self, device_name, query_id, *args, **kwargs):
        self.asked.append((device_name, query_id))
        self.clock.now += 0.1
        return self.answers[(device_name, query_id)]


def _result(device, query, output, *, observed=None, complete=True):
    return IosCommandResult(
        device_name=device,
        query_id=query,
        executed=True,
        output=output,
        fresh_output_observed=True,
        output_complete=complete,
        observed_device_name=device if observed is None else observed,
        device_identity_provenance=CONFIRMED_UNIQUE_IDENTITY,
    )


def _runtime(answers):
    clock = _Clock()
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: None,
        clock=clock,
        sleeper=clock.sleep,
    )
    ios = _Ios(clock, answers)
    runtime._forwarding_ios = ios
    return runtime, ios, clock


def _observe(runtime, settled):
    return runtime.observe_routed_forwarding(
        ["R1"],
        settled=settled,
        remaining_seconds=30.0,
        max_rounds=5,
        deadline_seconds=30.0,
        interval_seconds=1.0,
        sample_calls=16,
        episode_calls=5 * 12,
    )


def _answers(overrides=None):
    answers = {
        ("R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF): _result(
            "R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF, _BRIEF
        ),
        ("R1", OperationalQueryId.SHOW_IP_ROUTE): _result(
            "R1", OperationalQueryId.SHOW_IP_ROUTE, _ROUTES
        ),
    }
    answers.update(overrides or {})
    return answers


def test_one_round_reads_interfaces_then_routes_and_settles():
    """Two registered reads, merged into one authoritative reading."""
    runtime, ios, _clock = _runtime(_answers())

    observation = _observe(runtime, lambda round_: round_.readings[0].authoritative)

    assert ios.asked == [
        ("R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF),
        ("R1", OperationalQueryId.SHOW_IP_ROUTE),
    ]
    assert observation.episode_end_reason == "required_paths_forwarding"
    [reading] = observation.rounds[0].readings
    assert reading.authoritative
    assert reading.route_table.exact("10.3.0.0", 24)[0].next_hop == "10.12.0.2"
    assert [item.name for item in reading.interfaces] == [
        "GigabitEthernet0/0",
        "GigabitEthernet0/1",
    ]


def test_reads_attributed_to_different_devices_are_not_authoritative():
    """The two halves of a reading must come from the one device asked."""
    answers = _answers(
        {
            ("R1", OperationalQueryId.SHOW_IP_ROUTE): _result(
                "R1", OperationalQueryId.SHOW_IP_ROUTE, _ROUTES, observed="R2"
            )
        }
    )
    runtime, _ios, _clock = _runtime(answers)

    observation = _observe(runtime, lambda round_: round_.readings[0].authoritative)

    assert observation.episode_end_reason == "max_rounds_reached"
    assert not observation.rounds[0].readings[0].authoritative
    assert observation.rounds[0].readings[0].observed_device_name == ""


def test_a_paged_route_table_is_kept_but_never_parsed_into_evidence():
    """Without the pager walked to the prompt the table is absent."""
    answers = _answers(
        {
            ("R1", OperationalQueryId.SHOW_IP_ROUTE): _result(
                "R1", OperationalQueryId.SHOW_IP_ROUTE, _ROUTES, complete=False
            )
        }
    )
    runtime, _ios, _clock = _runtime(answers)

    reading = _observe(runtime, lambda _round: False).rounds[0].readings[0]

    assert reading.route_table is None and not reading.authoritative


def test_the_episode_stops_at_its_round_ceiling():
    """An unsettled episode is bounded by its rounds and window."""
    runtime, ios, _clock = _runtime(_answers())

    observation = _observe(runtime, lambda _round: False)

    assert len(observation.rounds) == 5
    assert len(ios.asked) == 10
    assert observation.device_names == ("R1",)
