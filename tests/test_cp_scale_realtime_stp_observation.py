"""Contracts for the phone-edge STP observation inside the Realtime window.

Simulation showed Switch5 dropping every phone DHCP Discover on a blocked
FastEthernet, but a Simulation trace is taken after `resetSimulation()` and
cannot say what the port was doing during the authoritative Realtime voice
window.  These are the contracts for measuring that directly, before anything
about the port is changed.

The observation is READ-ONLY and fail-closed: the only two states it is allowed
to name are the two the decision turns on, every other real state is retained as
itself, and anything that weakens the evidence -- a stale read, a pager, an
ambiguous device -- collapses to UNOBSERVABLE rather than to absence.

The canonical LIVE runner imports the production package namespace.  Keep that
namespace in a child process here for the same reason as the neighboring
CP-SCALE diagnostic suites: importing it in pytest would invalidate the runner's
import-isolation preflight.
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

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureAccessPort,
    ConfigureTrunk,
)
from packet_tracer_mcp.domain.enterprise.models.voice_plan import PhoneAssignment
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    OperationalQueryId,
)
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_stage,
)
from packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from tools.cp_scale_canonical_live import (
    _phone_edge_ports,
    _stp_realtime_evidence,
)


def access(action_id, interface, *, device="Switch5", voice=20):
    return ConfigureAccessPort(
        id=action_id,
        phase=ConfigurationPhase.L2_INTERFACES,
        device_id="sw-5",
        device_name=device,
        site_id="large-branch",
        interface=interface,
        data_vlan_id=10,
        voice_vlan_id=voice,
    )


def trunk(action_id, interface, *, device="Switch5"):
    return ConfigureTrunk(
        id=action_id,
        phase=ConfigurationPhase.L2_INTERFACES,
        device_id="sw-5",
        device_name=device,
        site_id="large-branch",
        interface=interface,
        allowed_vlans=[10, 20, 30],
    )


def phone(index, action_id, *, device="Switch5", vlan=20):
    return PhoneAssignment(
        phone_id="phone-%d" % index,
        physical_device_name="PHONE-%02d" % index,
        model="7960",
        site_id="large-branch",
        extension="10%02d" % index,
        call_control_id="cme/router4",
        voice_vlan_id=vlan,
        voice_segment_id="large-branch/voice",
        access_configuration_action_id=action_id,
        addressing_configuration_action_id="",
        binding_action_id="bind-%d" % index,
    )


class Projection:
    def __init__(self, actions, assignments):
        self.stage = type("S", (), {"value": "floor1"})()
        self.configuration = type("C", (), {"actions": actions})()
        self.voice = type("V", (), {"phone_assignments": assignments})()


def stp_output(rows, *, vlan=20, trailer="Switch>"):
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
    body.append(trailer)
    return "\n".join(body)


class Result:
    def __init__(self, output, **overrides):
        self.device_name = overrides.get("device_name", "Switch5")
        self.query_id = OperationalQueryId.SHOW_SPANNING_TREE
        self.executed = overrides.get("executed", True)
        self.output = output
        self.failure_reason = overrides.get("failure_reason", "")
        self.fresh_output_observed = overrides.get("fresh_output_observed", True)
        self.output_complete = overrides.get("output_complete", True)
        self.truncated_by_pager = overrides.get("truncated_by_pager", False)
        self.pager_pages_captured = overrides.get("pager_pages_captured", 1)
        self.pager_continuation = overrides.get(
            "pager_continuation", "not_encountered",
        )
        self.observed_device_name = overrides.get(
            "observed_device_name", "Switch5",
        )
        self.device_identity_provenance = overrides.get(
            "device_identity_provenance", "confirmed_unique",
        )
        self.device_identity_evidence = overrides.get(
            "device_identity_evidence", "prompt",
        )


class Ios:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def execute(self, device_name, query_id, **kwargs):
        self.calls.append((device_name, query_id.value, kwargs))
        return self._result


def observe(result, *, actions=None, assignments=None, edge="before"):
    actions = actions if actions is not None else [access("acc-1", "FastEthernet0/1")]
    assignments = (
        assignments if assignments is not None else [phone(1, "acc-1")]
    )
    ios = Ios(result)
    evidence = _stp_realtime_evidence(
        ios, Projection(actions, assignments), edge=edge,
    )
    evidence["_calls"] = ios.calls
    return evidence


FORWARDING = stp_output(["Fa0/1            Desg FWD 19        128.1    P2p"])
BLOCKING = stp_output(["Fa0/1            Altn BLK 19        128.1    P2p"])
LEARNING = stp_output(["Fa0/1            Desg LRN 19        128.1    P2p"])
OTHER_VLAN = stp_output(
    ["Fa0/1            Desg FWD 19        128.1    P2p"], vlan=10,
)
NO_ROW = stp_output(["Gi0/1            Root FWD 4         128.25   P2p"])

verdict = {}

verdict["forwarding"] = observe(Result(FORWARDING))
verdict["blocking"] = observe(Result(BLOCKING))
verdict["learning"] = observe(Result(LEARNING))
verdict["missing_vlan"] = observe(Result(OTHER_VLAN))
verdict["missing_row"] = observe(Result(NO_ROW))
verdict["stale"] = observe(Result(FORWARDING, fresh_output_observed=False))
verdict["incomplete"] = observe(Result(FORWARDING, output_complete=False))
verdict["pager"] = observe(
    Result(
        FORWARDING,
        output_complete=False,
        truncated_by_pager=True,
        pager_pages_captured=1,
        pager_continuation="not_qualified",
    ),
)
verdict["ambiguous_device"] = observe(
    Result(FORWARDING, device_identity_provenance="observed_not_unique"),
)
verdict["wrong_device"] = observe(
    Result(FORWARDING, observed_device_name="Switch4"),
)
verdict["not_executed"] = observe(
    Result("", executed=False, failure_reason="prompt_not_ready"),
)
verdict["after_edge"] = observe(Result(BLOCKING), edge="after")

# A phone whose access action is a trunk is not an edge port and must never be
# read as one, nor silently vanish.
verdict["trunk_identity"] = observe(
    Result(FORWARDING),
    actions=[trunk("acc-1", "GigabitEthernet0/1")],
    assignments=[phone(1, "acc-1")],
)
verdict["trunk_ports"] = _phone_edge_ports(
    Projection([trunk("acc-1", "GigabitEthernet0/1")], [phone(1, "acc-1")]),
)
verdict["derived_ports"] = _phone_edge_ports(
    Projection(
        [
            access("acc-1", "FastEthernet0/1"),
            access("acc-2", "FastEthernet0/2"),
            trunk("trunk-1", "GigabitEthernet0/1"),
        ],
        [phone(1, "acc-1"), phone(2, "acc-2")],
    ),
)
verdict["no_voice_plan"] = _phone_edge_ports(Projection([], []))
verdict["untyped_assignment"] = observe(
    Result(FORWARDING), actions=[], assignments=[1, 2],
)

# The real canonical Floor 1, not a fixture: the derivation has to land on the
# exact ports the failing stage owns without ever being told their names.
composition = compose_cp_scale_canonical(
    packet_tracer_version=MEASURED_BACKEND_VERSION,
)
floor1 = project_cp_scale_canonical_stage(
    composition, CPScaleCanonicalStage.FLOOR1,
)
verdict["floor1_ports"] = _phone_edge_ports(floor1)
verdict["floor1_trunks"] = sorted(
    {
        (action.device_name, action.interface)
        for action in floor1.configuration.actions
        if isinstance(action, ConfigureTrunk)
    }
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


def _states(case):
    return [item["classification"] for item in case["ports"]]


# 1 -- the phone-facing port set is DERIVED, never named.

def test_phone_ports_are_derived_from_the_typed_voice_to_access_binding(verdict):
    assert verdict["derived_ports"] == [
        {
            "device_name": "Switch5",
            "interface": "FastEthernet0/1",
            "vlan_id": 20,
            "access_configuration_action_id": "acc-1",
        },
        {
            "device_name": "Switch5",
            "interface": "FastEthernet0/2",
            "vlan_id": 20,
            "access_configuration_action_id": "acc-2",
        },
    ]


def test_a_stage_with_no_phone_derives_no_edge_port(verdict):
    assert verdict["no_voice_plan"] == []


def test_collecting_this_evidence_can_never_be_what_fails_a_stage(verdict):
    """An untyped plan yields no port and no query -- it does not raise."""
    case = verdict["untyped_assignment"]

    assert case["ports"] == []
    assert case["_calls"] == []
    assert case["excluded"] == [
        {"access_configuration_action_id": "", "reason": "NOT_A_TYPED_PHONE_ASSIGNMENT"},
        {"access_configuration_action_id": "", "reason": "NOT_A_TYPED_PHONE_ASSIGNMENT"},
    ]


def test_the_derivation_lands_on_the_exact_failing_floor1_edge_set(verdict):
    """Switch5 Fa0/1-21 on VLAN 20 -- reached semantically, never named."""
    ports = verdict["floor1_ports"]

    assert {item["device_name"] for item in ports} == {"Switch5"}
    assert {item["vlan_id"] for item in ports} == {20}
    assert [item["interface"] for item in ports] == [
        "FastEthernet0/%d" % index for index in sorted(range(1, 22), key=str)
    ]
    assert len(ports) == 21


# 2 -- a trunk is never an edge port, and never silently disappears.

def test_a_trunk_backed_phone_action_is_excluded_from_the_edge_set(verdict):
    assert verdict["trunk_ports"] == []


def test_no_floor1_trunk_is_ever_derived_as_a_phone_edge_port(verdict):
    derived = {
        (item["device_name"], item["interface"])
        for item in verdict["floor1_ports"]
    }
    trunks = {tuple(item) for item in verdict["floor1_trunks"]}

    assert trunks, "Floor 1 must carry trunks for this exclusion to mean anything."
    assert derived & trunks == set()


def test_an_excluded_trunk_is_recorded_rather_than_dropped(verdict):
    case = verdict["trunk_identity"]

    assert case["ports"] == []
    assert case["excluded"] == [{
        "access_configuration_action_id": "acc-1",
        "reason": "NOT_A_TYPED_ACCESS_PORT",
    }]
    assert case["_calls"] == []


# 3, 4 -- both boundaries are retained, and each names which edge it is.

def test_each_observation_names_its_boundary(verdict):
    assert verdict["forwarding"]["edge"] == "before"
    assert verdict["after_edge"]["edge"] == "after"


# 7, 8, 9 -- the three observable outcomes stay distinct.

def test_complete_fresh_attributable_forwarding_is_forwarding(verdict):
    case = verdict["forwarding"]

    assert _states(case) == ["FORWARDING"]
    assert case["counts"] == {
        "FORWARDING": 1, "BLOCKING": 0, "OTHER_OBSERVED": 0, "UNOBSERVABLE": 0,
    }
    port = case["ports"][0]
    assert port["role"] == "Desg"
    assert port["state"] == "FWD"
    assert port["cost"] == 19
    assert port["priority_number"] == "128.1"
    assert port["link_type"] == "P2p"
    assert port["vlan_id"] == 20


def test_complete_fresh_attributable_blocking_is_blocking(verdict):
    case = verdict["blocking"]

    assert _states(case) == ["BLOCKING"]
    assert case["ports"][0]["role"] == "Altn"
    assert case["ports"][0]["state"] == "BLK"


def test_a_real_transitional_state_is_neither_forwarding_nor_blocking(verdict):
    case = verdict["learning"]

    assert _states(case) == ["OTHER_OBSERVED"]
    assert case["ports"][0]["state"] == "LRN"


# 10 -- 15: every evidence weakness is UNOBSERVABLE, never absence.

@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("missing_vlan", "VLAN_INSTANCE_ABSENT"),
        ("missing_row", "INTERFACE_ROW_ABSENT"),
        ("stale", "OUTPUT_NOT_FRESH"),
        ("incomplete", "OUTPUT_INCOMPLETE"),
        ("pager", "PAGER_TRUNCATED"),
        ("ambiguous_device", "DEVICE_IDENTITY_NOT_CONFIRMED"),
        ("wrong_device", "DEVICE_IDENTITY_NOT_CONFIRMED"),
        ("not_executed", "QUERY_NOT_EXECUTED"),
    ],
)
def test_every_weak_evidence_path_is_unobservable_not_absence(
    verdict, case, reason,
):
    observed = verdict[case]

    assert _states(observed) == ["UNOBSERVABLE"], case
    assert observed["ports"][0]["failure_reason"] == reason
    assert observed["counts"]["BLOCKING"] == 0, case
    assert observed["counts"]["FORWARDING"] == 0, case


def test_a_pager_truncation_is_retained_with_its_own_marks(verdict):
    device = verdict["pager"]["devices"][0]

    assert device["truncated_by_pager"] is True
    assert device["pager_pages_captured"] == 1
    assert device["pager_continuation"] == "not_qualified"
    assert device["output_complete"] is False


def test_device_attribution_is_retained_on_every_read(verdict):
    device = verdict["forwarding"]["devices"][0]

    assert device["observed_device_name"] == "Switch5"
    assert device["device_identity_provenance"] == "confirmed_unique"
    assert device["device_identity_confirmed"] is True
    assert device["query_id"] == "show_spanning_tree"


def test_the_registered_spanning_tree_query_is_the_only_one_dispatched(verdict):
    assert verdict["forwarding"]["_calls"] == [
        ["Switch5", "show_spanning_tree", {}],
    ]


# --- source-level contracts -------------------------------------------------


def _runner_source():
    return (ROOT / "tools" / "cp_scale_canonical_live.py").read_text(
        encoding="utf-8",
    )


# 5 -- the reads sit inside the two proven Realtime boundaries.

def test_both_reads_sit_inside_the_proven_realtime_window():
    source = _runner_source()
    start = source.index("def _execute_stage")
    body = source[start:]

    before_boundary = body.index('"before": _voice_window_state(simulation)')
    before_gate = body.index('_realtime_boundary_error(continuity["before"]')
    before_read = body.index('evidence["stp_realtime_before_voice"]')
    voice = body.index("voice_evidence = _stage_voice(")
    after_read = body.index('evidence["stp_realtime_after_voice"]')
    after_boundary = body.index('continuity["after"] = _voice_window_state')

    assert before_boundary < before_gate < before_read < voice
    assert voice < after_read < after_boundary


# 6 -- Simulation can never be the source of a Realtime STP claim.

def test_the_simulation_diagnostic_runs_only_after_the_after_read():
    source = _runner_source()
    start = source.index("def _execute_stage")
    body = source[start:]

    assert body.index('evidence["stp_realtime_after_voice"]') < body.index(
        "_post_failure_simulation_diagnostic(",
    )


def test_realtime_stp_evidence_reads_no_simulation_surface():
    source = _runner_source()
    start = source.index("def _stp_realtime_evidence")
    body = source[start:source.index("\ndef ", start + 10)]

    for forbidden in (
        "SimulationTraceRuntime", "resetSimulation", "simulation", "trace",
        "enterSimulation", "_bounded_simulation_progression",
    ):
        assert forbidden not in body, forbidden


# 16, 17 -- this patch observes; it changes no DHCP and adds no classifier.

def test_the_observation_mutates_nothing_and_adds_no_traffic_type():
    source = _runner_source()
    start = source.index("def _stp_realtime_evidence")
    body = source[start:source.index("\ndef ", start + 10)]

    for forbidden in (
        "setDhcpClientFlag", "configurePcIp", "setIpAddress", "renew",
        "release", "lwAddDevice", "lwAddLink", "removeDevice", "pt_send_raw",
        "TRAFFIC_TYPES", "type7", "traffic_type", "portfast", "spanning-tree ",
    ):
        assert forbidden not in body, forbidden


def test_no_type7_classifier_is_introduced_anywhere_in_the_runner():
    source = _runner_source()

    assert "TRAFFIC_TYPES" not in source
    assert "type7" not in source


# 18 -- the existing pager qualification set is untouched by this patch.

def test_show_spanning_tree_remains_pagination_unqualified():
    terminal = (
        ROOT / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
        / "ios_terminal.py"
    ).read_text(encoding="utf-8")
    start = terminal.index("_PAGINATION_QUALIFIED_QUERIES = frozenset({")
    block = terminal[start:terminal.index("})", start)]

    assert "SHOW_SPANNING_TREE" not in block
    for qualified in (
        "SHOW_CONTROLLERS_SERIAL", "SHOW_IP_DHCP_BINDING",
        "SHOW_IP_DHCP_SERVER_STATISTICS_INTERFACE", "SHOW_INTERFACES_TRUNK",
        "SHOW_IP_PROTOCOLS", "SHOW_EPHONE",
    ):
        assert qualified in block, qualified


def test_the_runner_reuses_the_registered_query_and_parser():
    source = _runner_source()

    assert "OperationalQueryId.SHOW_SPANNING_TREE" in source
    assert "parse_show_spanning_tree" in source
    assert "show spanning-tree" not in source


def test_handoff_states_the_confirmed_defect_without_claiming_the_cause():
    handoff = (ROOT / "handoff.md").read_text(encoding="utf-8")

    assert "SOURCE_DEFECT_FOUND = YES" in handoff
    assert "SOURCE_DEFECT = EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING" in handoff
    # The defect is proven at the compilation layer; the CAUSE is not.
    assert "VOICE_ROOT_CAUSE = NOT_YET_CONFIRMED" in handoff
    assert "STP_BLOCKING_IN_SIMULATION = OBSERVED" in handoff
    assert "STP_BLOCKING_IN_REALTIME = NOT_YET_OBSERVED" in handoff
    assert "CP_SCALE_STATUS = OPEN / NOT VERIFIED" in handoff


def test_handoff_keeps_the_corrected_dhcp_identity_semantics():
    handoff = (ROOT / "handoff.md").read_text(encoding="utf-8")

    assert "DHCP_FRAME_IDENTITY_THIS_RUN = OBSERVED_BY_PT" in handoff
    assert "DHCP_EVENT_LIST_VISIBILITY = OBSERVED" in handoff
    assert "PERMANENT_TYPE7_MAPPING = NOT_IMPLEMENTED" in handoff


def test_handoff_names_the_realtime_observation_and_keeps_the_fix_out():
    handoff = (ROOT / "handoff.md").read_text(encoding="utf-8")

    assert "## Phone-edge STP in Realtime -- observation implemented, LIVE pending" in handoff
    assert "PHONE_EDGE_PORTFAST_COMPILED = NO at FLOOR1" in handoff
    assert "SHOW_SPANNING_TREE_PAGER = NOT_QUALIFIED" in handoff
