"""SP-2 e3 regression: the relay helper readback must survive IOS paging.

Episode 3 (`9f93721f`, attempt `37f79929`) applied the BR1 helper and then
stopped with `sp2_remote_helper_readback_unverified`: the fresh
`show ip interface GigabitEthernet0/1` reading was executed and fresh but not
a complete attributed capture. PT 9.0.1 rejects `terminal length 0`, and a
non-qualified paged query keeps only its first page as truncated evidence.

The pages below are SYNTHETIC: no archived capture of this command exists.
They drive the real `ControlledIosExecutor` through the independent paged
terminal stub, so the walk and its bounds come from production code, not from
the test. The shared first-page `SHOW_IP_INTERFACE` query must stay
unqualified for its other readers.
"""

from __future__ import annotations

import json

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.infrastructure.execution import ios_terminal as ios_module
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    OperationalQueryId,
)
from tests.test_e95_serial_orientation_pager_capture import (
    _EndlessTerminal,
    _executor,
    _PagedTerminal,
)

_INTERFACE = "GigabitEthernet0/1"
_COMMAND = f"show ip interface {_INTERFACE}"
_PAGE_1 = (
    f"{_INTERFACE} is up, line protocol is up (connected)\n"
    "  Internet address is 10.72.32.1/29\n"
    "  Broadcast address is 255.255.255.255\n"
    "  Address determined by setup command\n"
    "  MTU is 1500 bytes\n"
    "  Helper address is 10.72.0.2\n"
    "  Directed broadcast forwarding is disabled\n"
    "  Outgoing access list is not set\n"
    "  Inbound  access list is not set\n"
)
_PAGE_2 = (
    "  Proxy ARP is enabled\n"
    "  Security level is default\n"
    "  Split horizon is enabled\n"
    "  ICMP redirects are always sent\n"
    "  IP fast switching is disabled\n"
)


_DEVICE = "BR1-EDGE-RTR-01"


def _owner_answer(terminal, js: str) -> str | None:
    """Answer the ownership enumeration as one owner by session transcript continuity."""
    if "owner_candidate_names" not in js:
        return None
    return json.dumps(
        {
            "found": True,
            "configuration_channel": True,
            "output": terminal.output,
            "owner_name": _DEVICE,
            "owner_evidence": "session_transcript_continuity",
            "owner_candidates": 1,
            "owner_candidate_evidence": "session_transcript_continuity",
            "owner_candidate_names": [_DEVICE],
            "device_count": 6,
        }
    )


class _AttributedPagedTerminal(_PagedTerminal):
    def __call__(self, js: str, timeout: float) -> str:
        return _owner_answer(self, js) or super().__call__(js, timeout)


class _AttributedEndlessTerminal(_EndlessTerminal):
    def __call__(self, js: str, timeout: float) -> str:
        return _owner_answer(self, js) or super().__call__(js, timeout)


def _runtime(terminal) -> PacketTracerEnterpriseConfigurationRuntime:
    runtime = object.__new__(PacketTracerEnterpriseConfigurationRuntime)
    runtime._ios = _executor(terminal)
    return runtime


def _expectation() -> VerificationExpectation:
    return VerificationExpectation(
        id="relay-readback",
        action_id="relay-action",
        kind=VerificationKind.DHCP_RELAY,
        device_id="router-br1",
        device_name=_DEVICE,
        expected={"interface": _INTERFACE, "server_address": "10.72.0.2"},
    )


def _terminal(pages, cls=_AttributedPagedTerminal, **kwargs):
    return cls(pages, prompt=f"{_DEVICE}#", command=_COMMAND, **kwargs)


def test_paged_helper_readback_walks_to_the_prompt_and_verifies():
    """RED at 9f93721f: a paged helper read was truncated and unobservable."""
    terminal = _terminal([_PAGE_1, _PAGE_2])

    row = _runtime(terminal)._verify_dhcp_relay(_expectation())

    assert terminal.advances == 1
    assert row.status is ActionExecutionStatus.VERIFIED, row.message


def test_helper_pager_that_never_closes_stays_unobservable_with_diagnostics():
    """A bounded walk that cannot close is never read as the helper set."""
    terminal = _terminal([_PAGE_1, _PAGE_2], cls=_AttributedEndlessTerminal)

    row = _runtime(terminal)._verify_dhcp_relay(_expectation())

    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.message.startswith("relay_read_not_attributed_complete_fresh")
    assert "complete=False" in row.message
    assert "pager=" in row.message


def test_only_the_helper_query_is_pagination_qualified():
    """First-page readers of `show ip interface` keep their measured behavior."""
    qualified = ios_module._PAGINATION_QUALIFIED_QUERIES
    assert OperationalQueryId.SHOW_IP_INTERFACE_HELPER in qualified
    assert OperationalQueryId.SHOW_IP_INTERFACE not in qualified
    assert (
        ios_module._INTERFACE_COMMANDS[OperationalQueryId.SHOW_IP_INTERFACE_HELPER]
        == ios_module._INTERFACE_COMMANDS[OperationalQueryId.SHOW_IP_INTERFACE]
    )
