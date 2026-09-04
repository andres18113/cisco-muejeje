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
from pathlib import Path

import pytest

from tests.subprocess_harness import run_isolated_python, subprocess_failure


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
    _STP_MAX_LOGICAL_ATTEMPTS,
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
        self.dispatch_classification = overrides.get(
            "dispatch_classification", "dispatched",
        )


class Ios:
    def __init__(self, result):
        self._results = result if isinstance(result, list) else [result]
        self.calls = []

    def execute(self, device_name, query_id, **kwargs):
        self.calls.append((device_name, query_id.value, kwargs))
        index = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[index]


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


def pager_failed(output=FORWARDING, **overrides):
    """The exact shape the Floor-1 AFTER read returned at 540c746.

    `executed` True is the discriminator: reaching it after an incomplete
    qualified capture requires the executor's own `_cancel_pager` to have been
    confirmed, so the terminal is back at a prompt and not quarantined.
    """
    fields = {
        "output_complete": False,
        "truncated_by_pager": True,
        "pager_pages_captured": 1,
        "pager_continuation": "failed",
        "failure_reason": (
            "IOS pager continuation window could not be attributed to this "
            "capture (rolled_unattributable)."
        ),
    }
    fields.update(overrides)
    return Result(output, **fields)


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

# --- bounded retry -----------------------------------------------------------
verdict["max_attempts"] = _STP_MAX_LOGICAL_ATTEMPTS
# 1: a complete first read is the whole observation.
verdict["retry_not_needed"] = observe(Result(FORWARDING))
# 2, 3: retry-safe pager failure, then a complete second read.
verdict["retry_then_complete"] = observe([pager_failed(), Result(BLOCKING)])
# 4, 5: both incomplete -- final UNOBSERVABLE and no third execution.
verdict["retry_then_incomplete"] = observe([pager_failed(), pager_failed()])
# 6: the executor could not confirm it cancelled the pager.
verdict["retry_unsafe_terminal"] = observe([
    pager_failed(
        "",
        executed=False,
        failure_reason=(
            "IOS pager cancellation could not be confirmed; the terminal "
            "session remains isolated from new queries."
        ),
    ),
    Result(FORWARDING),
])
# 7: IOS provably received a different command.
verdict["retry_dispatch_corrupted"] = observe([
    pager_failed(dispatch_classification="prefix_loss"), Result(FORWARDING),
])
# 8: the executing session belongs to another device.
verdict["retry_ambiguous_device"] = observe([
    pager_failed(device_identity_provenance="ambiguous"), Result(FORWARDING),
])
# A pager on an UNQUALIFIED query is a policy state, not a transient failure.
verdict["retry_not_qualified"] = observe([
    pager_failed(pager_continuation="not_qualified"), Result(FORWARDING),
])
# 15: the measured Floor-1 shape -- complete VLAN 20 carrying only the uplink.
verdict["complete_without_phone_rows"] = observe([
    pager_failed(), Result(NO_ROW),
])
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
    completed = run_isolated_python(code, cwd=ROOT)
    assert completed.returncode == 0, subprocess_failure(completed)
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


# 18 -- qualification is per-query, and every prior one keeps its own.

def test_spanning_tree_qualification_did_not_relax_the_others():
    """It was UNQUALIFIED until the Floor-1 run measured the truncation.

    The first governed run of this observation read Switch5 and came back
    `truncated_by_pager` with `vlan_instances == [1]`: page one ended mid
    `VLAN0010` header and VLAN 20 was never in the capture. That measurement --
    not a line-count derivation -- is what admits this one query.
    """
    terminal = (
        ROOT / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
        / "ios_terminal.py"
    ).read_text(encoding="utf-8")
    start = terminal.index("_PAGINATION_QUALIFIED_QUERIES = frozenset({")
    block = terminal[start:terminal.index("})", start)]

    assert "SHOW_SPANNING_TREE" in block
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
    assert "STP_BLOCKING_IN_SIMULATION = OBSERVED" in handoff
    # Realtime STP remains unclaimed either way; its current value is pinned by
    # test_handoff_records_the_run_that_measured_the_pager_without_claiming_state.
    realtime = [
        line for line in handoff.splitlines()
        if line.startswith("STP_BLOCKING_IN_REALTIME = ")
    ]
    assert len(realtime) == 1
    assert realtime[0].split(" = ", 1)[1].split()[0] != "OBSERVED"


def test_handoff_keeps_the_corrected_dhcp_identity_semantics():
    handoff = (ROOT / "handoff.md").read_text(encoding="utf-8")

    assert "DHCP_FRAME_IDENTITY_THIS_RUN = OBSERVED_BY_PT" in handoff
    assert "DHCP_EVENT_LIST_VISIBILITY = OBSERVED" in handoff
    assert "PERMANENT_TYPE7_MAPPING = NOT_IMPLEMENTED" in handoff


def test_handoff_names_the_realtime_observation_and_keeps_the_fix_out():
    handoff = (ROOT / "handoff.md").read_text(encoding="utf-8")

    assert "## Phone-edge STP in Realtime -- CASE D, bounded retry pending LIVE" in handoff
    assert "PHONE_EDGE_PORTFAST_COMPILED = NO at FLOOR1" in handoff
    assert "SHOW_SPANNING_TREE_PAGER = QUALIFIED by fresh 2f2055c measurement" in handoff
    assert "STP_REALTIME_LOGICAL_ATTEMPTS = 2" in handoff


def test_handoff_records_case_d_without_claiming_a_port_state():
    """A complete VLAN 20 carrying only the uplink proves representation."""
    handoff = (ROOT / "handoff.md").read_text(encoding="utf-8")

    assert "VLAN20  Gi0/1 ONLY" in handoff
    assert "VLAN20_PHONE_PORT_ROWS = ABSENT in a COMPLETE capture at 540c746" in handoff
    assert "VLAN10_PHONE_PORTS_BEFORE_VOICE = 21/21 Desg FWD at 540c746" in handoff
    assert "CASE_D_REALTIME_STP_REPRESENTATION_UNRESOLVED" in handoff
    # Absent rows are never promoted to BLOCKING in the narrative either.
    assert "Absent rows are not BLOCKING." in handoff
    assert "STP_BLOCKING_IN_REALTIME = UNOBSERVABLE (CASE D at 540c746)" in handoff


# --- bounded retry contract -------------------------------------------------
#
# The Floor-1 rerun at 540c746 lost the AFTER observation to a qualified pager
# continuation that did not close. That read still came back executed=True with
# confirmed_unique attribution, which is exactly what proves the executor had
# already cancelled the pager and left the terminal at a prompt. One fresh
# registered execution is therefore safe -- and only then.


def _device(case):
    return case["devices"][0]


def test_the_retry_is_bounded_to_two_logical_attempts(verdict):
    assert verdict["max_attempts"] == 2


def test_a_complete_first_read_is_never_retried(verdict):
    case = verdict["retry_not_needed"]
    device = _device(case)

    assert len(case["_calls"]) == 1
    assert len(device["attempts"]) == 1
    assert device["selected_attempt"] == 1
    assert device["retry_eligible"] is False
    assert device["retry_reason"] == ""
    assert [item["classification"] for item in case["ports"]] == ["FORWARDING"]


def test_a_retry_safe_pager_failure_buys_exactly_one_more_execution(verdict):
    case = verdict["retry_then_complete"]
    device = _device(case)

    assert len(case["_calls"]) == 2
    assert len(device["attempts"]) == 2
    assert device["retry_eligible"] is True
    assert device["retry_reason"] == "QUALIFIED_PAGER_CONTINUATION_FAILED"
    assert device["selected_attempt"] == 2
    # The second read is what is claimed, and nothing from the first survives
    # into the parsed state.
    assert [item["classification"] for item in case["ports"]] == ["BLOCKING"]
    assert case["ports"][0]["state"] == "BLK"


def test_both_attempts_are_retained_independently_and_never_merged(verdict):
    case = verdict["retry_then_complete"]
    attempts = _device(case)["attempts"]

    assert [item["attempt"] for item in attempts] == [1, 2]
    assert attempts[0]["output_complete"] is False
    assert attempts[0]["truncated_by_pager"] is True
    assert attempts[0]["pager_continuation"] == "failed"
    assert attempts[0]["source_error"] == "PAGER_TRUNCATED"
    assert attempts[1]["output_complete"] is True
    assert attempts[1]["source_error"] == ""
    # Two executions are two observations. The failed page is kept as its own
    # evidence and its output is not spliced into the selected one.
    assert attempts[0]["output"] != attempts[1]["output"]
    assert attempts[1]["output"] not in attempts[0]["output"]
    assert _device(case)["output"] == attempts[1]["output"]


def test_every_attempt_retains_its_own_raw_quality_metadata(verdict):
    for attempt in _device(verdict["retry_then_complete"])["attempts"]:
        for field in (
            "executed", "fresh_output_observed", "output_complete",
            "truncated_by_pager", "pager_pages_captured", "pager_continuation",
            "dispatch_classification", "failure_reason", "observed_device_name",
            "device_identity_provenance", "vlan_instances",
        ):
            assert field in attempt, field


def test_a_second_incomplete_attempt_ends_unobservable_with_no_third(verdict):
    case = verdict["retry_then_incomplete"]
    device = _device(case)

    assert len(case["_calls"]) == 2
    assert len(device["attempts"]) == 2
    assert device["selected_attempt"] is None
    assert [item["classification"] for item in case["ports"]] == ["UNOBSERVABLE"]
    assert case["ports"][0]["failure_reason"] == "PAGER_TRUNCATED"


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("retry_unsafe_terminal", "TERMINAL_NOT_CONFIRMED_SAFE"),
        ("retry_dispatch_corrupted", "DISPATCH_CORRUPTED"),
        ("retry_ambiguous_device", "DEVICE_IDENTITY_NOT_CONFIRMED"),
        ("retry_not_qualified", "NOT_A_QUALIFIED_PAGER_FAILURE"),
    ],
)
def test_an_unproven_terminal_is_never_retried(verdict, case, reason):
    """Retry only where the prior result PROVES a fresh query is safe."""
    observed = verdict[case]
    device = _device(observed)

    assert len(observed["_calls"]) == 1, case
    assert len(device["attempts"]) == 1, case
    assert device["retry_eligible"] is False, case
    assert device["retry_reason"] == reason, case
    assert device["selected_attempt"] is None, case
    assert [item["classification"] for item in observed["ports"]] == ["UNOBSERVABLE"]


def test_a_complete_vlan20_without_phone_rows_is_unobservable_not_blocking(verdict):
    """The measured Floor-1 shape: VLAN 20 carried only the trunk uplink.

    A complete capture proves the table's REPRESENTATION, not the port state.
    Reading an absent row as BLOCKING would manufacture the very finding this
    observation exists to test.
    """
    case = verdict["complete_without_phone_rows"]
    device = _device(case)

    assert device["selected_attempt"] == 2
    assert device["attempts"][1]["output_complete"] is True
    assert device["attempts"][1]["source_error"] == ""
    assert device["vlan_instances"] == [20]
    assert [item["classification"] for item in case["ports"]] == ["UNOBSERVABLE"]
    assert case["ports"][0]["failure_reason"] == "INTERFACE_ROW_ABSENT"
    assert case["counts"]["BLOCKING"] == 0


# --- the retry belongs to this seam, not to the executor ---------------------


def test_the_generic_executor_gained_no_pagination_retry():
    """ControlledIosExecutor still retries only proven dispatch corruption."""
    terminal = (
        ROOT / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
        / "ios_terminal.py"
    ).read_text(encoding="utf-8")
    start = terminal.index("    def execute(")
    body = terminal[start:terminal.index("    @staticmethod", start)]

    assert "_is_retryable_corruption" in body
    for forbidden in (
        "truncated_by_pager", "pager_continuation", "output_complete",
        "PagerContinuation", "_STP_MAX_LOGICAL_ATTEMPTS",
    ):
        assert forbidden not in body, forbidden


def test_the_retry_lives_in_the_cp_scale_observation_seam():
    source = _runner_source()

    assert "_STP_MAX_LOGICAL_ATTEMPTS = 2" in source
    start = source.index("def _stp_logical_observation")
    body = source[start:source.index("\ndef ", start + 10)]
    # The executor keeps owning pagination mechanics; the seam only re-asks.
    for forbidden in (
        "_PAGER_CONTINUATION_KEY", "enterCommand", "_cancel_pager",
        "String.fromCharCode",
    ):
        assert forbidden not in body, forbidden
    assert "ios.execute(" in body


def test_before_and_after_share_one_logical_observation_helper():
    source = _runner_source()
    start = source.index("def _execute_stage")
    body = source[start:]

    before = body.index('evidence["stp_realtime_before_voice"]')
    after = body.index('evidence["stp_realtime_after_voice"]')
    for index in (before, after):
        assert "_stp_realtime_evidence(" in body[index:index + 220]
    # AFTER is not special-cased with its own retry knob.
    assert body.count("_stp_realtime_evidence(") == 2
    assert "attempts=" not in body[before:after + 220]


def test_the_logical_observation_completes_before_the_realtime_after_boundary():
    source = _runner_source()
    start = source.index("def _execute_stage")
    body = source[start:]

    assert body.index('evidence["stp_realtime_after_voice"]') < body.index(
        'continuity["after"] = _voice_window_state',
    )


def test_this_patch_leaves_the_staging_defect_and_dhcp_untouched():
    """The retry buys evidence. It fixes neither PortFast nor DHCP."""
    compose = (
        ROOT / "src" / "packet_tracer_mcp" / "application" / "use_cases"
        / "compose_cp_scale_canonical.py"
    ).read_text(encoding="utf-8")

    # Leg 1 of the confirmed defect is still exactly as measured: LARGE's STP
    # domain, and therefore every edge action, still waits for FLOOR3.
    marker = compose.index("def _completed_stp_sites")
    body = compose[marker:compose.index("\ndef ", marker + 10)]
    assert "CPScaleCanonicalStage.FLOOR3" in body
    assert "CPScaleCanonicalStage.FLOOR1" not in body

    source = _runner_source()
    assert "TRAFFIC_TYPES" not in source
    assert "type7" not in source
    assert "spanning-tree portfast" not in source
