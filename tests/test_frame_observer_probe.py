"""Contracts for enumerating what a Simulation frameInstance actually exposes.

CP-SCALE Floor 1 needs one thing this repository cannot currently read: whether
PHONE-02's DHCP Discover and the STP configuration BPDU that leaves the SAME
physical phone-facing port carry different VLAN identities.  Packet Tracer's own
decision text never names a VLAN, so the object has to be asked.

`AGENTS.md` rule 6 forbids writing code over a PT signature this repository has
not confirmed, so this is discovery, not use: it enumerates member NAMES and
their shape, and it invokes nothing whose signature is not already measured.
A name that exists is not a capability -- what a getter means is decided later,
by a positive/negative control, not by its spelling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (
    MAX_FRAME_TARGETS,
    MAX_MEMBER_NAMES,
    MAX_MEMBER_NAME_LENGTH,
    PacketTracerFrameObserverProbe,
)


ROOT = Path(__file__).resolve().parents[1]


def _probe(payload, calls=None):
    def send_and_wait(js: str, _timeout: float = 10.0):
        if calls is not None:
            calls.append(js)
        return json.dumps(payload) if isinstance(payload, dict) else payload

    return PacketTracerFrameObserverProbe(send_and_wait)


_FRAME = {
    "index": 263,
    "in_bounds": True,
    "frame_found": True,
    "observed_device": "PHONE-02",
    "observed_in_port": "",
    "observed_sim_time": 5786620,
    "observed_traffic_type": 7,
    "members": ["getDevice", "getUserTrafficType", "getVlanId"],
    "observers": [
        {"name": "getDevice", "type_name": "function", "is_callable": True, "arity": 0},
        {
            "name": "getUserTrafficType", "type_name": "function",
            "is_callable": True, "arity": 0,
        },
        {"name": "getVlanId", "type_name": "function", "is_callable": True, "arity": 0},
    ],
    "truncated": False,
}


# 1 -- an index is only usable when the event list actually holds it.

def test_an_out_of_bounds_index_is_reported_not_read():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 10,
        "frames": [{"index": 99, "in_bounds": False, "frame_found": False}],
    }).discover_frame_observers([99])

    frame = observed.frames[0]
    assert frame.in_bounds is False
    assert frame.frame_found is False
    assert frame.members == ()
    assert frame.observers == ()


def test_a_negative_index_is_refused_before_any_dispatch():
    calls: list[str] = []
    observed = _probe({"observed": True}, calls).discover_frame_observers([-1])

    assert calls == []
    assert observed.observed is False
    assert "index" in observed.failure_reason.casefold()


def test_more_targets_than_the_bound_are_refused_before_any_dispatch():
    calls: list[str] = []
    observed = _probe({"observed": True}, calls).discover_frame_observers(
        list(range(MAX_FRAME_TARGETS + 1)),
    )

    assert calls == []
    assert observed.observed is False


# 2 -- outside Simulation there is no event list to enumerate.

def test_the_probe_refuses_outside_simulation_mode():
    observed = _probe({
        "observed": True, "simulation_mode": False, "frame_count": 0, "frames": [],
    }).discover_frame_observers([263])

    assert observed.simulation_mode is False
    assert observed.frames == ()


def test_the_dispatched_script_requires_simulation_mode_itself():
    calls: list[str] = []
    _probe({"observed": True, "simulation_mode": True, "frames": []}, calls)\
        .discover_frame_observers([263])

    assert "isSimulationMode" in calls[0]


# 3 -- discovery may never be able to change anything.

def test_no_mutation_primitive_appears_in_the_dispatched_script():
    calls: list[str] = []
    _probe({"observed": True, "simulation_mode": True, "frames": []}, calls)\
        .discover_frame_observers([263])

    for forbidden in (
        "setSimulationMode", "resetSimulation", "forward", "backward",
        "enterCommand", "lwAddDevice", "lwAddLink", "removeDevice",
        "configurePcIp", "setDhcpClientFlag", "setPower", "setAccessVlan",
        "setVoipVlanId", "set", "add", "remove", "delete",
    ):
        assert forbidden not in calls[0], forbidden


def test_the_source_carries_no_mutation_or_mac_or_portfast_work():
    source = (
        ROOT / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
        / "frame_observer_probe.py"
    ).read_text(encoding="utf-8")

    # 13, 14 -- the MAC fallback and the PortFast defect are explicitly out of
    # this slice.
    for forbidden in (
        "mac address-table", "mac_address_table", "SHOW_MAC",
        "portfast", "PortFast", "bpduguard",
        "TRAFFIC_TYPES", "type7",
    ):
        assert forbidden not in source, forbidden


# 4, 5 -- names and shape only; nothing unknown is called.

def test_only_member_names_and_shape_are_enumerated():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 2000,
        "frames": [_FRAME],
    }).discover_frame_observers([263])

    frame = observed.frames[0]
    assert frame.members == ("getDevice", "getUserTrafficType", "getVlanId")
    assert [(item.name, item.type_name, item.is_callable, item.arity)
            for item in frame.observers] == [
        ("getDevice", "function", True, 0),
        ("getUserTrafficType", "function", True, 0),
        ("getVlanId", "function", True, 0),
    ]


def test_no_enumerated_member_is_invoked_in_this_pass():
    """A discovered name is evidence. Calling it is a separate, later decision."""
    calls: list[str] = []
    _probe({"observed": True, "simulation_mode": True, "frames": []}, calls)\
        .discover_frame_observers([263])

    script = calls[0]
    # The only calls in the script are the measured identity getters, spelled
    # out literally. There is no generic `obj[name]()` invocation anywhere.
    assert "__k]()" not in script
    assert "__n]()" not in script
    assert "[__name]()" not in script
    assert "apply(" not in script
    assert "call(" not in script
    assert "eval" not in script
    assert "Function(" not in script


def test_only_already_measured_getters_are_ever_called():
    calls: list[str] = []
    _probe({"observed": True, "simulation_mode": True, "frames": []}, calls)\
        .discover_frame_observers([263])

    script = calls[0]
    for measured in (
        "getFrameInstanceCount", "getFrameInstanceAt", "getDevice",
        "getStartSimTime", "getUserTrafficType", "getInPort",
    ):
        assert measured in script, measured
    # Never a getter this repository has not measured on frameInstance.
    for unmeasured in ("getClassName", "getVlan", "getPdu", "getTag", "toString"):
        assert unmeasured not in script, unmeasured


# 6 -- the object is never dumped, and the enumeration is hard-bounded.

def test_the_frame_object_is_never_stringified_or_dumped():
    calls: list[str] = []
    _probe({"observed": True, "simulation_mode": True, "frames": []}, calls)\
        .discover_frame_observers([263])

    script = calls[0]
    assert "JSON.stringify(__f)" not in script
    assert "String(__f)" not in script
    assert str(MAX_MEMBER_NAMES) in script
    assert str(MAX_MEMBER_NAME_LENGTH) in script


def test_an_over_long_member_list_is_marked_truncated_not_silently_cut():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 2000,
        "frames": [{**_FRAME, "truncated": True}],
    }).discover_frame_observers([263])

    assert observed.frames[0].truncated is True


# 9 -- identity is proven per frame, and time is its own field.

def test_each_frame_retains_its_own_identity_and_sim_time():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 2000,
        "frames": [_FRAME],
    }).discover_frame_observers([263])

    frame = observed.frames[0]
    assert frame.index == 263
    assert frame.observed_device == "PHONE-02"
    assert frame.observed_sim_time == 5786620
    assert frame.observed_traffic_type == 7


# 15 -- discovery is diagnostic and can never promote anything.

def test_discovery_cannot_promote_cp_scale_verification():
    source = (
        ROOT / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
        / "frame_observer_probe.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "VerificationKind", "ConfigurationApplicationResult", "VERIFIED",
        "CapabilityStatus", "ConfigurationApplicationStatus",
    ):
        assert forbidden not in source, forbidden


def test_a_transport_error_stays_unobserved_rather_than_becoming_absence():
    observed = _probe("ERROR:boom").discover_frame_observers([263])

    assert observed.observed is False
    assert observed.frames == ()
    assert "boom" in observed.failure_reason


def test_malformed_json_is_unobserved_not_an_empty_enumeration():
    observed = _probe("{not json").discover_frame_observers([263])

    assert observed.observed is False
    assert observed.frames == ()


# --- runner-side target selection -------------------------------------------
#
# A frame is chosen by what Packet Tracer SAID about it, never by its raw
# traffic type: `type7` is not "DHCP" in this repository and `type11` is not
# "BPDU". Both targets keep their own sim_time and their own identifying
# decision, because the same physical port does not imply the same VLAN and the
# same capture does not imply the same instant.

_SEL_PROBE = r'''
import json
import sys

sys.path.insert(0, __ROOT__)
sys.path.insert(0, __SRC__)

from tools.cp_scale_canonical_live import _frame_observer_discovery


class Transport:
    def __init__(self):
        self.calls = []

    def send_and_wait(self, js, timeout=10.0):
        self.calls.append(js)
        return json.dumps({
            "observed": True, "simulation_mode": True, "frame_count": 2000,
            "frames": [
                {
                    "index": 263, "in_bounds": True, "frame_found": True,
                    "observed_device": "PHONE-02", "observed_in_port": "",
                    "observed_sim_time": 5786620, "observed_traffic_type": 7,
                    "members": ["getDevice"], "observers": [], "truncated": False,
                },
                {
                    "index": 29, "in_bounds": True, "frame_found": True,
                    "observed_device": "Switch5", "observed_in_port": "",
                    "observed_sim_time": 5782104, "observed_traffic_type": 11,
                    "members": ["getDevice"], "observers": [], "truncated": False,
                },
            ],
        })


def hop(**kw):
    base = {
        "index": 0, "device": "", "in_port": None, "out_port": None,
        "sim_time": 0, "traffic_type_raw": 0, "status": "sent", "decisions": [],
    }
    base.update(kw)
    return base


DHCP = hop(
    index=263, device="PHONE-02", out_port="Switch", sim_time=5786620,
    traffic_type_raw=7, status="sent",
    decisions=[
        {"layer": 7, "inbound": False,
         "description": "The DHCP client constructs a Discover packet and sends it out."},
        {"layer": 2, "inbound": False,
         "description": "The IP Phone uses the active VLAN interface as the outgoing VLAN number."},
    ],
)
DROP = hop(
    index=267, device="Switch5", in_port="FastEthernet0/10", sim_time=5786620,
    traffic_type_raw=7, status="dropped",
    decisions=[
        {"layer": 1, "inbound": True, "description": "FastEthernet0/10 receives the frame."},
        {"layer": 2, "inbound": True,
         "description": "FastEthernet0/10 is blocked by STP. The device drops the frame."},
    ],
)
BPDU = hop(
    index=29, device="Switch5", out_port="FastEthernet0/10", sim_time=5782104,
    traffic_type_raw=11, status="sent",
    decisions=[
        {"layer": 2, "inbound": False,
         "description": "The STP process sends out a configuration BPDU."},
    ],
)
# type11 on a port nothing dropped on: not the comparison this asks for.
BPDU_ELSEWHERE = hop(
    index=31, device="Switch5", out_port="FastEthernet0/23", sim_time=5782104,
    traffic_type_raw=11, status="sent",
    decisions=[
        {"layer": 2, "inbound": False,
         "description": "The STP process sends out a configuration BPDU."},
    ],
)
# Right traffic type, no identifying decision text at all.
UNNAMED7 = hop(index=900, device="PHONE-02", sim_time=1, traffic_type_raw=7,
               decisions=[{"layer": 2, "inbound": False, "description": "Frame sent."}])
UNNAMED11 = hop(index=901, device="Switch5", out_port="FastEthernet0/10",
                sim_time=2, traffic_type_raw=11,
                decisions=[{"layer": 2, "inbound": False, "description": "Frame sent."}])


def run(phone_hops, switch_hops):
    transport = Transport()
    result = _frame_observer_discovery(
        transport,
        phone_name="PHONE-02",
        switch_name="Switch5",
        phone_trace={"hops": phone_hops},
        switch_trace={"hops": switch_hops},
    )
    result["_calls"] = len(transport.calls)
    return result


verdict = {
    "both": run([DHCP], [DROP, BPDU, BPDU_ELSEWHERE]),
    "unnamed": run([UNNAMED7], [DROP, UNNAMED11]),
    "no_drop_port": run([DHCP], [BPDU_ELSEWHERE]),
    "empty": run([], []),
}
print(json.dumps(verdict))
'''


@pytest.fixture(scope="module")
def selection():
    import subprocess
    import sys as _sys

    code = _SEL_PROBE.replace("__ROOT__", repr(str(ROOT))).replace(
        "__SRC__", repr(str(ROOT / "src")),
    )
    completed = subprocess.run(
        [_sys.executable, "-c", code], cwd=ROOT, check=True,
        capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


# 7, 8 -- each target is admitted only by PT's own identifying text.

def test_both_targets_are_selected_by_packet_tracers_own_decision_text(selection):
    targets = {item["role"]: item for item in selection["both"]["targets"]}

    assert set(targets) == {"dhcp_discover", "configuration_bpdu"}
    assert "DHCP client constructs a Discover packet" in (
        targets["dhcp_discover"]["identifying_decision"]
    )
    assert "configuration BPDU" in (
        targets["configuration_bpdu"]["identifying_decision"]
    )
    assert selection["both"]["_calls"] == 1


def test_the_right_traffic_type_without_the_text_selects_nothing(selection):
    case = selection["unnamed"]

    assert case["targets"] == []
    assert case["attempted"] is False
    assert case["_calls"] == 0


def test_a_bpdu_on_a_port_that_dropped_nothing_is_not_the_comparison(selection):
    roles = {item["role"] for item in selection["no_drop_port"]["targets"]}

    assert "configuration_bpdu" not in roles


def test_an_empty_capture_attempts_no_enumeration(selection):
    case = selection["empty"]

    assert case["targets"] == []
    assert case["attempted"] is False
    assert case["_calls"] == 0


# 10, 11 -- the two facts that must never be collapsed.

def test_same_physical_port_never_implies_same_vlan(selection):
    """Nothing in the evidence asserts a VLAN. That is the open question."""
    blob = json.dumps(selection["both"]).casefold()

    assert "vlan_id" not in blob
    assert "same_vlan" not in blob
    for target in selection["both"]["targets"]:
        assert "vlan" not in json.dumps(target).casefold()


def test_same_capture_never_implies_same_instant(selection):
    targets = {item["role"]: item for item in selection["both"]["targets"]}

    # Both keep their own time, and here they genuinely differ.
    assert targets["dhcp_discover"]["sim_time"] == 5786620
    assert targets["configuration_bpdu"]["sim_time"] == 5782104
    assert targets["dhcp_discover"]["sim_time"] != (
        targets["configuration_bpdu"]["sim_time"]
    )


def test_each_target_identity_is_reconfirmed_against_the_enumerated_frame(selection):
    for target in selection["both"]["targets"]:
        assert target["identity_reconfirmed"] is True


# 12, 13, 14 -- this slice adds no classifier, no MAC work, no PortFast.

def test_the_runner_slice_adds_no_classifier_mac_or_portfast():
    source = (ROOT / "tools" / "cp_scale_canonical_live.py").read_text(
        encoding="utf-8",
    )
    start = source.index("def _frame_observer_discovery")
    body = source[start:source.index("\ndef ", start + 10)]

    for forbidden in (
        "TRAFFIC_TYPES", "type7 =", "mac address-table", "SHOW_MAC",
        "portfast", "bpduguard", "setDhcpClientFlag", "configurePcIp",
    ):
        assert forbidden not in body, forbidden
    # Traffic type may be RETAINED as evidence, never used to decide identity.
    assert "_DHCP_DISCOVER_DECISION" in source
    assert "_BPDU_DECISION" in source
