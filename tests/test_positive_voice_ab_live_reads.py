"""Contracts for the two registered reads the positive Voice A/B decides on.

Both reads answer a question whose NEGATIVE form is a causal discriminant.  An
STP table with no phone row says ABSENT, which is the exact CP-SCALE VLAN20
shape; a binding table with no voice row says zero bindings, which is the exact
CP-SCALE server shape.  Reaching either of those from a read that was stale or
stopped at a pager would manufacture the evidence the A/B is meant to weigh.

The STP gate is four dimensions: EXECUTED is the terminal answering, FRESH is
this capture being of this moment, COMPLETE is it being the whole logical read,
and CONFIRMED_UNIQUE attributes that answer to the requested switch.  Anything
short of all four is UNOBSERVABLE for the mutation-authorizing STP decision.
UNOBSERVABLE is never ABSENT and never zero.

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
    DATA_VLAN_ID,
    VOICE_VLAN_ID,
    _classify_stp_row,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    DeviceIdentityProvenance,
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


class QueryIos:
    """One answer per registered query, so a two-stage read can be observed."""

    def __init__(self, answers):
        self._answers = answers
        self.calls = []

    def execute(self, device_name, query_id, **kwargs):
        self.calls.append((device_name, query_id.value, kwargs.get("interface", "")))
        return self._answers[query_id]


def result(query, output, **overrides):
    fields = {
        "executed": True,
        "fresh_output_observed": True,
        "output_complete": True,
        "device_identity_provenance": (
            DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
        ),
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


def stp_observation(rows=FORWARDING_ROW, *, output=None, **overrides):
    """The parsed state and authority metadata from one registered result."""
    show = result(
        OperationalQueryId.SHOW_SPANNING_TREE,
        stp_table(rows) if output is None else output,
        **overrides,
    )
    ios = Ios(show)
    observation = _ConfigurationAdapter(None, ios).read_spanning_tree_observation(
        SWITCH
    )
    state = (
        _classify_stp_row(observation.instances, VOICE_VLAN_ID, PHONE_PORT)
        if observation.authoritative else "UNOBSERVABLE"
    )
    return {
        "state": state,
        "authoritative": observation.authoritative,
        "failure_dimensions": list(observation.failure_dimensions),
        "executed": observation.executed,
        "fresh": observation.fresh,
        "complete": observation.complete,
        "identity_provenance": observation.identity_provenance,
        "failure_reason": observation.failure_reason,
        "duration_ms": observation.duration_ms,
        "queries": [item[1] for item in ios.calls],
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


SUBINTERFACE = "FastEthernet0/0.%d" % VOICE_VLAN_ID


def brief_table(*rows):
    body = [
        "show ip interface brief",
        "Interface              IP-Address      OK? Method Status                Protocol",
        "FastEthernet0/0        unassigned      YES manual up                    up",
    ]
    body.extend(rows)
    return "\n".join(body)


VOICE_BRIEF_ROW = (
    "FastEthernet0/0.930    10.93.0.1       YES manual up                    up"
)
DOWN_BRIEF_ROW = (
    "FastEthernet0/0.930    10.93.0.1       YES manual administratively down  down"
)
SCOPED_OUTPUT = "\n".join((
    "show ip interface FastEthernet0/0.930",
    "FastEthernet0/0.930 is up, line protocol is up",
    "  Internet address is 10.93.0.1/24",
))


def router_interfaces(brief_output, *, brief=None, scoped=None, scoped_output=""):
    """What the runner's registered router read publishes, end to end."""
    answers = {
        OperationalQueryId.SHOW_IP_INTERFACE_BRIEF: result(
            OperationalQueryId.SHOW_IP_INTERFACE_BRIEF, brief_output,
            **(brief or {}),
        ),
        OperationalQueryId.SHOW_IP_INTERFACE: result(
            OperationalQueryId.SHOW_IP_INTERFACE, scoped_output, **(scoped or {}),
        ),
    }
    ios = QueryIos(answers)
    rows = _ConfigurationAdapter(None, ios).read_interface_addresses(ROUTER)
    return {
        "read": rows is not None,
        "interfaces": None if rows is None else [item.interface for item in rows],
        "voice": None if rows is None else [
            [item.interface, item.ip_address, item.status, item.protocol]
            for item in rows
            if item.interface.casefold().endswith(".930")
        ],
        "queries": [item[1] for item in ios.calls],
        "scoped_interface": [item[2] for item in ios.calls if item[2]],
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
verdict["stp_identity_not_observed"] = stp_row(
    device_identity_provenance=DeviceIdentityProvenance.NOT_OBSERVED.value,
)
verdict["stp_identity_ambiguous"] = stp_row(
    device_identity_provenance=DeviceIdentityProvenance.AMBIGUOUS.value,
)
verdict["stp_identity_mismatched"] = stp_row(
    device_identity_provenance=DeviceIdentityProvenance.MISMATCHED.value,
)
verdict["stp_observation_forwarding"] = stp_observation(duration_ms=23)
verdict["stp_observation_execution"] = stp_observation(
    executed=False, failure_reason="IOS command submission timed out.",
)
verdict["stp_observation_freshness"] = stp_observation(
    fresh_output_observed=False,
)
verdict["stp_observation_completeness"] = stp_observation(
    output_complete=False, truncated_by_pager=True,
    pager_continuation="failed", pager_pages_captured=4,
)
for provenance in (
    DeviceIdentityProvenance.NOT_OBSERVED,
    DeviceIdentityProvenance.AMBIGUOUS,
    DeviceIdentityProvenance.MISMATCHED,
):
    verdict["stp_observation_identity_" + provenance.value] = stp_observation(
        device_identity_provenance=provenance.value,
    )
verdict["stp_observation_parse"] = stp_observation(
    output="show spanning-tree\nSwitch#",
)
verdict["stp_observation_query"] = stp_observation(
    output="show spanning-tree\n% Invalid input detected at '^' marker.\nSwitch#",
)
verdict["stp_observation_multiple"] = stp_observation(
    fresh_output_observed=False,
    output_complete=False,
    device_identity_provenance=DeviceIdentityProvenance.AMBIGUOUS.value,
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

# --- the router foundation read, which must never invent an absence --------

verdict["router_brief_has_subinterface"] = router_interfaces(
    brief_table(VOICE_BRIEF_ROW),
)
verdict["router_brief_shows_it_down"] = router_interfaces(
    brief_table(DOWN_BRIEF_ROW),
)
verdict["router_brief_unreadable"] = router_interfaces(
    brief_table(VOICE_BRIEF_ROW), brief={"output_complete": False},
)
verdict["router_brief_stale"] = router_interfaces(
    brief_table(VOICE_BRIEF_ROW), brief={"fresh_output_observed": False},
)
# The brief table did not list it.  Before that may stand as an absence, the
# bounded per-interface read has to answer -- and if IT is unreadable, nothing
# is claimed at all.
verdict["router_falls_back_and_finds_it"] = router_interfaces(
    brief_table(), scoped_output=SCOPED_OUTPUT,
)
verdict["router_fallback_unreadable"] = router_interfaces(
    brief_table(), scoped_output=SCOPED_OUTPUT,
    scoped={"output_complete": False},
)
verdict["router_fallback_not_executed"] = router_interfaces(
    brief_table(), scoped={"executed": False},
)
verdict["router_two_readable_reads_find_nothing"] = router_interfaces(
    brief_table(), scoped_output="% Invalid input detected at '^' marker.",
)

# --- the pool read: one production call, and the boundary kept if unread ----


class _Enterprise:
    """Stands in for the production readback the adapter delegates to."""

    def __init__(self, observation):
        self._observation = observation
        self.calls = []

    def read_dhcp_pool(self, device_name, pool_name, lease_start, lease_end):
        self.calls.append([device_name, pool_name, lease_start, lease_end])
        return self._observation


class _Observed:
    def __init__(self, pool_present, failure_reason=""):
        self.pool_present = pool_present
        self.failure_reason = failure_reason


EMPTY_POOL_PROMPT = "\n".join(("show ip dhcp pool", "Router#"))


def pool(pool_present, **overrides):
    show = result(
        OperationalQueryId.SHOW_IP_DHCP_POOL, EMPTY_POOL_PROMPT, **overrides,
    )
    enterprise = _Enterprise(_Observed(pool_present, "incomplete"))
    ios = Ios(show)
    adapter = _ConfigurationAdapter(enterprise, ios)
    observed = adapter.read_dhcp_pool(ROUTER, "P", "10.93.0.10", "10.93.0.254")
    return {
        "pool_present": observed.pool_present,
        "production_calls": enterprise.calls,
        "extra_reads": [item[1] for item in ios.calls],
        "captures": adapter.pool_boundary_captures,
    }


verdict["pool_readable"] = pool(True)
# An absence measured in a fresh, complete, uniquely attributed table is a
# FINDING.  Capturing it as a boundary would blur it into a failure to see.
verdict["pool_absent"] = pool(False)
# Nothing established: nothing may be inferred, and the text that defeated the
# parser is kept, because re-measuring it costs another LIVE.
verdict["pool_unreadable"] = pool(None, output_complete=False)

# --- the access-port readback: judged against each port's own intent --------


class _VerifyEnterprise:
    """Records the expectation the adapter builds and verifies it as asked."""

    def __init__(self):
        self.expectations = []

    def verify(self, expectations):
        self.expectations.extend(expectations)

        class _Result:
            fields = {"vlan_id": "VERIFIED", "voice_vlan_id": "VERIFIED"}

        return [_Result()]


def access_read(expected_access_vlan):
    enterprise = _VerifyEnterprise()
    adapter = _ConfigurationAdapter(enterprise, None)
    port = adapter.read_access_port(SWITCH, PHONE_PORT, expected_access_vlan)
    expectation = enterprise.expectations[0]
    return {
        "expected_vlan": expectation.expected.get("vlan_id"),
        "expected_voice": expectation.expected.get("voice_vlan_id"),
        "readback_data_vlan": port.data_vlan_id,
        "readback_voice_vlan": port.voice_vlan_id,
    }


verdict["access_control_half"] = access_read(DATA_VLAN_ID)
verdict["access_intervention_half"] = access_read(VOICE_VLAN_ID)

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

def test_a_fresh_complete_uniquely_attributed_fwd_row_reads_forwarding(verdict):
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


@pytest.mark.parametrize(
    "key",
    [
        "stp_identity_not_observed",
        "stp_identity_ambiguous",
        "stp_identity_mismatched",
    ],
)
def test_non_authoritative_stp_identity_is_unobservable(verdict, key):
    assert verdict[key] == {
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


def test_the_same_authoritative_result_carries_forwarding_and_no_failures(verdict):
    observed = verdict["stp_observation_forwarding"]

    assert observed["state"] == "FORWARDING"
    assert observed["authoritative"] is True
    assert observed["failure_dimensions"] == []
    assert observed["duration_ms"] == 23


@pytest.mark.parametrize(
    ("key", "dimension"),
    [
        ("stp_observation_execution", "EXECUTION"),
        ("stp_observation_freshness", "FRESHNESS"),
        ("stp_observation_completeness", "COMPLETENESS"),
        ("stp_observation_identity_not_observed", "IDENTITY"),
        ("stp_observation_identity_ambiguous", "IDENTITY"),
        ("stp_observation_identity_mismatched", "IDENTITY"),
        ("stp_observation_parse", "PARSING"),
        ("stp_observation_query", "QUERY_SESSION"),
    ],
)
def test_each_stp_authority_boundary_retains_its_exact_dimension(
    verdict, key, dimension,
):
    observed = verdict[key]

    assert observed["state"] == "UNOBSERVABLE"
    assert observed["authoritative"] is False
    assert dimension in observed["failure_dimensions"]


def test_multiple_stp_authority_failures_are_retained_together(verdict):
    observed = verdict["stp_observation_multiple"]

    assert observed["failure_dimensions"] == [
        "FRESHNESS", "COMPLETENESS", "IDENTITY",
    ]


def test_stp_diagnostics_do_not_dispatch_a_second_registered_query(verdict):
    for key, observed in verdict.items():
        if not key.startswith("stp_observation_"):
            continue
        assert observed["queries"] == ["show_spanning_tree"], key


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


# --- the router voice subinterface -----------------------------------------
#
# This read is the one that could most easily manufacture a root cause.  A
# build that does not print subinterfaces in the brief table would look exactly
# like a router that never got one, and "the voice subinterface is missing" is
# precisely the conclusion this investigation would love to reach and must not
# reach by accident.


def test_a_readable_brief_table_answers_with_its_own_rows(verdict):
    observed = verdict["router_brief_has_subinterface"]

    assert observed["read"] is True
    assert observed["voice"] == [
        ["FastEthernet0/0.930", "10.93.0.1", "up", "up"]
    ]
    # One query.  The bounded fallback is for a table that did NOT list it.
    assert observed["queries"] == ["show_ip_interface_brief"]


def test_a_subinterface_that_is_down_is_still_a_subinterface_that_exists(verdict):
    observed = verdict["router_brief_shows_it_down"]

    assert observed["voice"] == [
        ["FastEthernet0/0.930", "10.93.0.1", "administratively down", "down"]
    ]


def test_an_unreadable_brief_table_claims_nothing_about_the_router(verdict):
    for key in ("router_brief_unreadable", "router_brief_stale"):
        assert verdict[key]["read"] is False, key
        assert verdict[key]["interfaces"] is None, key


def test_a_brief_table_without_the_row_asks_the_bounded_read_before_concluding(verdict):
    observed = verdict["router_falls_back_and_finds_it"]

    assert observed["queries"] == ["show_ip_interface_brief", "show_ip_interface"]
    assert observed["scoped_interface"] == ["FastEthernet0/0.930"]
    assert observed["voice"] == [
        ["FastEthernet0/0.930", "10.93.0.1", "up", "up"]
    ]


def test_an_unreadable_bounded_read_leaves_the_router_unobserved(verdict):
    # Two ways for the second read to say nothing, and neither may be allowed
    # to harden the first read's silence into an absent subinterface.
    for key in ("router_fallback_unreadable", "router_fallback_not_executed"):
        assert verdict[key]["read"] is False, key
        assert verdict[key]["interfaces"] is None, key


def test_two_readable_reads_that_find_nothing_are_a_finding(verdict):
    # The distinction the previous test protects.  Both reads answered, whole
    # and fresh, and neither carried the subinterface.
    observed = verdict["router_two_readable_reads_find_nothing"]

    assert observed["read"] is True
    assert observed["voice"] == []
    assert observed["queries"] == ["show_ip_interface_brief", "show_ip_interface"]


def test_the_runner_reads_the_trunk_through_the_existing_typed_readback():
    # No new IOS: the trunk dimensions come from the readback the enterprise
    # runtime already owns, which is also what publishes their freshness.
    source = (ROOT / "tools" / "cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )

    assert "return self._enterprise.read_trunk(device_name, interface)" in source
    assert "show interfaces trunk" not in source
    assert "pt_send_raw" not in source


# --- the DHCP pool read -----------------------------------------------------

def test_a_readable_pool_costs_exactly_one_production_read(verdict):
    answer = verdict["pool_readable"]

    assert answer["pool_present"] is True
    assert answer["production_calls"] == [
        ["__MCP_VOICEAB_probe_R", "P", "10.93.0.10", "10.93.0.254"],
    ]
    assert answer["extra_reads"] == []
    assert answer["captures"] == []


def test_a_measured_pool_absence_is_a_finding_and_not_a_boundary(verdict):
    answer = verdict["pool_absent"]

    assert answer["pool_present"] is False
    assert answer["extra_reads"] == []
    assert answer["captures"] == []


def test_an_unreadable_pool_keeps_the_exact_text_that_defeated_it(verdict):
    answer = verdict["pool_unreadable"]

    assert answer["pool_present"] is None
    assert answer["extra_reads"] == ["show_ip_dhcp_pool"]
    captured, = answer["captures"]
    assert captured["requested_pool_name"] == "P"
    assert captured["failure_reason"] == "incomplete"
    assert captured["output_complete"] is False
    assert captured["output"].splitlines() == ["show ip dhcp pool", "Router#"]


# --- the access-port readback ------------------------------------------------


def test_each_access_port_expectation_carries_its_own_intent(verdict):
    # The paired A/B turns on this: the control half is verified against the
    # data VLAN and the intervention half against the voice VLAN.  One shared
    # constant here would contradict a switch that did exactly what it was
    # asked to do.
    assert verdict["access_control_half"]["expected_vlan"] == 931
    assert verdict["access_intervention_half"]["expected_vlan"] == 930
    assert verdict["access_control_half"]["expected_voice"] == 930
    assert verdict["access_intervention_half"]["expected_voice"] == 930


def test_a_verified_access_readback_answers_with_the_intent_it_verified(verdict):
    assert verdict["access_control_half"]["readback_data_vlan"] == 931
    assert verdict["access_intervention_half"]["readback_data_vlan"] == 930
    assert verdict["access_control_half"]["readback_voice_vlan"] == 930
    assert verdict["access_intervention_half"]["readback_voice_vlan"] == 930
