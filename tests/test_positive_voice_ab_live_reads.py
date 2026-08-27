"""Contracts for the two registered reads the positive Voice A/B decides on.

Both reads answer a question whose NEGATIVE form is a causal discriminant.  An
STP table with no phone row says ABSENT, which is the exact CP-SCALE VLAN20
shape; a binding table with no voice row says zero bindings, which is the exact
CP-SCALE server shape.  Reaching either of those from a read that was stale or
stopped at a pager would manufacture the evidence the A/B is meant to weigh.

So the gate is three dimensions, not one: EXECUTED is the terminal answering,
FRESH is this capture being of this moment, COMPLETE is it being the whole
logical read.  Anything short of all three is UNOBSERVABLE, and UNOBSERVABLE is
never ABSENT and never zero.

The LIVE runner imports the production package namespace.  Keep it in a child
process here for the same reason as the neighbouring CP-SCALE suites: importing
it inside pytest would give the qualifier two identities for every typed model.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

_PROBE = r'''
import json
import sys

sys.path.insert(0, __ROOT__)
sys.path.insert(0, __SRC__)

from packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (
    VOICE_VLAN_ID,
    _classify_stp_row,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)
from tools.cp_scale_positive_voice_ab_live import _ConfigurationAdapter

SWITCH = "__MCP_VOICEAB_probe_SW"
ROUTER = "__MCP_VOICEAB_probe_R"
PHONE_PORT = "FastEthernet0/1"


def stp_table(rows, *, vlan=VOICE_VLAN_ID):
    """The exact multi-instance layout PT 9.0.1.0858 prints."""
    body = [
        "show spanning-tree",
        "VLAN%04d" % vlan,
        "  Spanning tree enabled protocol ieee",
        "  Root ID    Priority    24586",
        "             Address     0060.5C2C.521E",
        "             Cost        19",
        "             Port        25(GigabitEthernet0/1)",
        "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
        "",
        "  Bridge ID  Priority    32788  (priority 32768 sys-id-ext 20)",
        "             Address     0001.9663.8714",
        "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
        "             Aging Time  20",
        "",
        "Interface        Role Sts Cost      Prio.Nbr Type",
        "---------------- ---- --- --------- -------- ------------------------",
    ]
    body.extend(rows)
    body.append("")
    body.append("Switch>")
    return "\n".join(body)


FORWARDING_ROW = ["Fa0/1            Desg FWD 19        128.1    P2p"]
BLOCKING_ROW = ["Fa0/1            Altn BLK 19        128.1    P2p"]
UPLINK_ONLY = ["Gi0/1            Root FWD 4         128.25   P2p"]

BINDING_TABLE = "\n".join((
    "show ip dhcp binding",
    "IP address       Client-ID/              Lease expiration        Type",
    "                 Hardware address",
    "10.93.0.10       0100.0BE0.1234          --                      Automatic",
    "10.93.0.11       0100.0BE0.5678          --                      Automatic",
    "",
    "Router>",
))
TRUNCATED_TABLE = "\n".join((
    "show ip dhcp binding",
    "IP address       Client-ID/              Lease expiration        Type",
    "                 Hardware address",
    "10.93.0.10       0100.0BE0.1234          --                      Automatic",
    " --More--",
))


class Ios:
    """One registered query, one answer, recorded."""

    def __init__(self, result):
        self._result = result
        self.calls = []

    def execute(self, device_name, query_id, **kwargs):
        self.calls.append((device_name, query_id.value))
        return self._result


def result(query, output, **overrides):
    fields = {
        "executed": True,
        "fresh_output_observed": True,
        "output_complete": True,
    }
    fields.update(overrides)
    return IosCommandResult(
        device_name=SWITCH, query_id=query, output=output, **fields,
    )


def stp_row(rows=FORWARDING_ROW, **overrides):
    """What the qualifier ends up calling this phone's voice-VLAN row."""
    show = result(
        OperationalQueryId.SHOW_SPANNING_TREE, stp_table(rows), **overrides,
    )
    adapter = _ConfigurationAdapter(None, Ios(show))
    instances = adapter.read_spanning_tree(SWITCH)
    return {
        "parsed": instances is not None,
        "classification": _classify_stp_row(
            instances, VOICE_VLAN_ID, PHONE_PORT,
        ),
    }


def bindings(output=BINDING_TABLE, **overrides):
    show = result(
        OperationalQueryId.SHOW_IP_DHCP_BINDING, output, **overrides,
    )
    adapter = _ConfigurationAdapter(None, Ios(show))
    rows = adapter.read_dhcp_bindings(ROUTER)
    return {
        "read": rows is not None,
        "addresses": (
            None if rows is None else [item.ip_address for item in rows]
        ),
    }


verdict = {}

# A fresh, complete table is the only thing that may classify anything.
verdict["stp_forwarding"] = stp_row()
verdict["stp_blocking"] = stp_row(BLOCKING_ROW)
verdict["stp_absent"] = stp_row(UPLINK_ONLY)
verdict["stp_incomplete"] = stp_row(output_complete=False)
verdict["stp_unfresh"] = stp_row(fresh_output_observed=False)
verdict["stp_not_executed"] = stp_row(executed=False)
verdict["stp_pager"] = stp_row(
    output_complete=False, truncated_by_pager=True, pager_continuation="failed",
)

verdict["dhcp_complete"] = bindings()
verdict["dhcp_incomplete"] = bindings(TRUNCATED_TABLE, output_complete=False)
verdict["dhcp_unfresh"] = bindings(fresh_output_observed=False)
verdict["dhcp_not_executed"] = bindings("", executed=False)
# The shape that matters most: a table that STOPPED at a pager after printing
# no voice row.  Parsed, it would read as a measured zero.
verdict["dhcp_pager_before_any_row"] = bindings(
    "\n".join((
        "show ip dhcp binding",
        "IP address       Client-ID/              Lease expiration        Type",
        " --More--",
    )),
    output_complete=False,
    truncated_by_pager=True,
)

print(json.dumps(verdict))
'''


@pytest.fixture(scope="module")
def verdict():
    code = _PROBE.replace("__ROOT__", repr(str(ROOT))).replace(
        "__SRC__", repr(str(ROOT / "src")),
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


# --- STP --------------------------------------------------------------------

def test_a_fresh_complete_table_with_a_forwarding_row_reads_forwarding(verdict):
    assert verdict["stp_forwarding"] == {
        "parsed": True, "classification": "FORWARDING",
    }


def test_a_fresh_complete_table_with_a_blocking_row_reads_blocking(verdict):
    assert verdict["stp_blocking"] == {
        "parsed": True, "classification": "BLOCKING",
    }


def test_a_fresh_complete_table_without_the_phone_row_reads_absent(verdict):
    # This is the CP-SCALE VLAN20 shape, and it is a MEASURED absence: the
    # instance was printed in full and simply has no row for this port.
    assert verdict["stp_absent"] == {"parsed": True, "classification": "ABSENT"}


def test_an_incomplete_stp_read_is_unobservable_and_never_absent(verdict):
    assert verdict["stp_incomplete"] == {
        "parsed": False, "classification": "UNOBSERVABLE",
    }


def test_a_stale_stp_read_is_unobservable_and_never_absent(verdict):
    assert verdict["stp_unfresh"] == {
        "parsed": False, "classification": "UNOBSERVABLE",
    }


def test_an_unexecuted_stp_read_is_unobservable(verdict):
    assert verdict["stp_not_executed"]["classification"] == "UNOBSERVABLE"


def test_a_paged_stp_read_never_becomes_a_missing_row(verdict):
    # `executed` alone was the old gate, and this result satisfies it.
    assert verdict["stp_pager"] == {
        "parsed": False, "classification": "UNOBSERVABLE",
    }


def test_absent_and_unobservable_never_collapse_into_each_other(verdict):
    absent = verdict["stp_absent"]["classification"]
    unread = {
        verdict[key]["classification"]
        for key in ("stp_incomplete", "stp_unfresh", "stp_pager")
    }
    assert absent == "ABSENT"
    assert unread == {"UNOBSERVABLE"}


# --- DHCP bindings ----------------------------------------------------------

def test_a_fresh_complete_binding_table_yields_its_rows(verdict):
    assert verdict["dhcp_complete"] == {
        "read": True, "addresses": ["10.93.0.10", "10.93.0.11"],
    }


def test_an_incomplete_binding_table_is_unread_not_zero(verdict):
    assert verdict["dhcp_incomplete"] == {"read": False, "addresses": None}


def test_a_stale_binding_table_is_unread_not_zero(verdict):
    assert verdict["dhcp_unfresh"] == {"read": False, "addresses": None}


def test_an_unexecuted_binding_read_is_unread(verdict):
    assert verdict["dhcp_not_executed"]["read"] is False


def test_a_binding_table_paged_before_any_row_never_reads_as_zero(verdict):
    # Parsed, this output has no voice address in it at all, and the qualifier
    # would count zero voice bindings -- the CP-SCALE server signature, made up
    # out of a pager.
    assert verdict["dhcp_pager_before_any_row"] == {
        "read": False, "addresses": None,
    }
