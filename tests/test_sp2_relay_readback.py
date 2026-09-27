"""Exact, attributable IOS helper readback for an SP-2 relay interface."""

from __future__ import annotations

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
    DeviceIdentityProvenance,
    IosCommandResult,
    OperationalQueryId,
    parse_show_ip_interface_helpers,
)


def _output(*helpers: str) -> str:
    return "\n".join(
        [
            "R1#show ip interface FastEthernet0/0.10",
            "FastEthernet0/0.10 is up, line protocol is up",
            "  Internet address is 198.18.160.1/29",
            *[f"  Helper address is {item}" for item in helpers],
            "R1#",
        ]
    )


def test_helper_parser_retains_every_complete_helper_on_the_interface():
    """Repeated helper lines remain visible for exact-set comparison."""
    row = parse_show_ip_interface_helpers(_output("192.0.2.10", "192.0.2.11"))
    assert row is not None
    assert row.interface == "FastEthernet0/0.10"
    assert row.addresses == ("192.0.2.10", "192.0.2.11")


def test_helper_parser_distinguishes_none_from_unreadable():
    """An explicit empty set differs from a missing or malformed field."""
    absent = parse_show_ip_interface_helpers(_output("not set"))
    assert absent is not None and absent.addresses == ()
    assert parse_show_ip_interface_helpers(_output()) is None
    assert parse_show_ip_interface_helpers(_output("192.0.2.10;evil")) is None


class _Ios:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append((device_name, query_id, interface))
        return self.result


def _readback(*helpers, fresh=True, complete=True, device="R1"):
    return IosCommandResult(
        device_name="R1",
        query_id=OperationalQueryId.SHOW_IP_INTERFACE,
        executed=True,
        output=_output(*helpers),
        fresh_output_observed=fresh,
        output_complete=complete,
        observed_device_name=device,
        device_identity_provenance=DeviceIdentityProvenance.CONFIRMED_UNIQUE.value,
    )


def _verify(result):
    runtime = object.__new__(PacketTracerEnterpriseConfigurationRuntime)
    runtime._ios = _Ios(result)
    expectation = VerificationExpectation(
        id="relay-readback",
        action_id="relay-action",
        kind=VerificationKind.DHCP_RELAY,
        device_id="router-1",
        device_name="R1",
        expected={"interface": "FastEthernet0/0.10", "server_address": "192.0.2.10"},
    )
    row = runtime._verify_dhcp_relay(expectation)
    assert runtime._ios.calls == [
        ("R1", OperationalQueryId.SHOW_IP_INTERFACE, "FastEthernet0/0.10")
    ]
    return row


def test_exact_fresh_complete_helper_is_verified():
    """Only an exact attributed helper line verifies the relay action."""
    assert _verify(_readback("192.0.2.10")).status is ActionExecutionStatus.VERIFIED


@pytest.mark.parametrize(
    "helpers", [(), ("not set",), ("192.0.2.11",), ("192.0.2.10", "192.0.2.11")]
)
def test_missing_wrong_or_extra_helper_never_verifies(helpers):
    """A wrong or competing helper cannot satisfy the plan."""
    status = _verify(_readback(*helpers)).status
    assert status is not ActionExecutionStatus.VERIFIED


@pytest.mark.parametrize(
    "attributes",
    [
        {"fresh": False},
        {"complete": False},
        {"device": "OtherRouter"},
    ],
)
def test_stale_incomplete_or_foreign_helper_is_unobservable(attributes):
    """Only the current complete response from the selected router counts."""
    assert _verify(_readback("192.0.2.10", **attributes)).status is (
        ActionExecutionStatus.UNOBSERVABLE
    )
