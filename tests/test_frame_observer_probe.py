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
                    "index": 267, "in_bounds": True, "frame_found": True,
                    "observed_device": "Switch5",
                    "observed_in_port": "FastEthernet0/10",
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
    index=267, device="Switch5", previous_device="PHONE-02",
    in_port="FastEthernet0/10", sim_time=5786620,
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

def test_every_target_is_selected_by_packet_tracers_own_decision_text(selection):
    targets = {item["role"]: item for item in selection["both"]["targets"]}

    assert set(targets) == {"phone_dhcp", "switch_dhcp", "switch_bpdu"}
    assert "DHCP client constructs a Discover packet" in (
        targets["phone_dhcp"]["identifying_decision"]
    )
    assert "configuration BPDU" in (
        targets["switch_bpdu"]["identifying_decision"]
    )
    assert selection["both"]["_calls"] == 1


def test_the_right_traffic_type_without_the_text_selects_nothing(selection):
    case = selection["unnamed"]

    assert case["targets"] == []
    assert case["attempted"] is False
    assert case["_calls"] == 0


def test_a_bpdu_on_a_port_that_dropped_nothing_is_not_the_comparison(selection):
    roles = {item["role"] for item in selection["no_drop_port"]["targets"]}

    assert "switch_bpdu" not in roles


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
    assert targets["phone_dhcp"]["sim_time"] == 5786620
    assert targets["switch_bpdu"]["sim_time"] == 5782104
    assert targets["phone_dhcp"]["sim_time"] != (
        targets["switch_bpdu"]["sim_time"]
    )
    assert selection["both"]["same_capture"] is True
    assert selection["both"]["same_instant"] is False


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


# --- phase 2: what the two measured child getters actually return ------------
#
# Phase 1 measured getInFrame/getOutFrame as zero-arity get* functions. It did
# NOT observe what they return, and nothing here assumes it. These are the only
# two names this phase is allowed to call, spelled literally; no member
# discovered on whatever comes back is ever invoked.

_CHILD = {
    "index": 100,
    "in_bounds": True,
    "frame_found": True,
    "observed_device": "PHONE-02",
    "observed_sim_time": 8406971,
    "observed_traffic_type": 7,
    "members": ["getInFrame"],
    "observers": [],
    "truncated": False,
    "children": [
        {
            "getter": "getInFrame", "invoked": True, "returned_null": True,
            "type_name": "object", "error": "", "members": [], "observers": [],
            "truncated": False,
        },
        {
            "getter": "getOutFrame", "invoked": True, "returned_null": False,
            "type_name": "object", "error": "",
            "members": ["getVlanId", "getSize"],
            "observers": [
                {"name": "getVlanId", "type_name": "function",
                 "is_callable": True, "arity": 0},
                {"name": "getSize", "type_name": "function",
                 "is_callable": True, "arity": 0},
            ],
            "truncated": False,
        },
    ],
}


def test_only_the_two_measured_child_getters_are_ever_called():
    calls: list[str] = []
    _probe({"observed": True, "simulation_mode": True, "frames": []}, calls)\
        .discover_frame_observers([100])

    script = calls[0]
    assert "getInFrame()" in script
    assert "getOutFrame()" in script
    # Spelled literally, never selected out of a list at runtime.
    assert "__child]()" not in script
    assert "__getter]()" not in script
    for never in ("getVlanId()", "getSize()", "getFrame()", "getPdu()"):
        assert never not in script, never


def test_a_child_getter_returning_null_is_recorded_not_enumerated():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 2341,
        "frames": [_CHILD],
    }).discover_frame_observers([100])

    child = observed.frames[0].children[0]
    assert child.getter == "getInFrame"
    assert child.invoked is True
    assert child.returned_null is True
    assert child.members == ()
    assert child.observers == ()


def test_a_child_object_is_enumerated_by_name_and_shape_only():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 2341,
        "frames": [_CHILD],
    }).discover_frame_observers([100])

    child = observed.frames[0].children[1]
    assert child.getter == "getOutFrame"
    assert child.returned_null is False
    assert child.type_name == "object"
    assert child.members == ("getVlanId", "getSize")
    assert [(item.name, item.is_callable, item.arity) for item in child.observers] == [
        ("getVlanId", True, 0),
        ("getSize", True, 0),
    ]


def test_a_discovered_child_candidate_is_never_invoked_in_this_phase():
    """Finding getVlanId is the result. Calling it is the next patch."""
    calls: list[str] = []
    _probe({
        "observed": True, "simulation_mode": True, "frames": [_CHILD],
    }, calls).discover_frame_observers([100])

    assert "getVlanId" not in calls[0]


def test_child_discovery_is_bounded_per_frame():
    from src.packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (
        CHILD_FRAME_GETTERS,
        MAX_CHILD_OBJECTS_PER_FRAME,
    )

    assert CHILD_FRAME_GETTERS == ("getInFrame", "getOutFrame")
    assert MAX_CHILD_OBJECTS_PER_FRAME == 2
    assert len(CHILD_FRAME_GETTERS) == MAX_CHILD_OBJECTS_PER_FRAME


def test_a_child_getter_that_throws_keeps_its_error_and_stays_unobserved():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 2341,
        "frames": [{
            **_CHILD,
            "children": [{
                "getter": "getInFrame", "invoked": False, "returned_null": False,
                "type_name": "", "error": "TypeError: boom",
                "members": [], "observers": [], "truncated": False,
            }],
        }],
    }).discover_frame_observers([100])

    child = observed.frames[0].children[0]
    assert child.invoked is False
    assert child.error == "TypeError: boom"
    assert child.members == ()


def test_the_child_object_is_never_stringified():
    calls: list[str] = []
    _probe({"observed": True, "simulation_mode": True, "frames": []}, calls)\
        .discover_frame_observers([100])

    script = calls[0]
    for forbidden in ("JSON.stringify(__c)", "String(__c)", "JSON.stringify(__f)"):
        assert forbidden not in script, forbidden


def test_name_matching_is_a_discovery_aid_and_not_an_assertion():
    """A promising name is a lead. It is not evidence of VLAN identity."""
    source = (
        ROOT / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
        / "frame_observer_probe.py"
    ).read_text(encoding="utf-8")

    # The probe may FLAG candidate names, but must never conclude from one.
    for forbidden in (
        "vlan_identified", "vlan_confirmed", "VLAN_VERIFIED", "is_vlan",
    ):
        assert forbidden not in source, forbidden


# --- the three-way, same-device comparison ----------------------------------

_P2_PROBE = r'''
import json
import sys

sys.path.insert(0, __ROOT__)
sys.path.insert(0, __SRC__)

from tools.cp_scale_canonical_live import _frame_observer_discovery

PHONE = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PHONE-02"


class Transport:
    def __init__(self):
        self.calls = []

    def send_and_wait(self, js, timeout=10.0):
        self.calls.append(js)
        return json.dumps({
            "observed": True, "simulation_mode": True, "frame_count": 2341,
            "frames": [
                {"index": 100, "in_bounds": True, "frame_found": True,
                 "observed_device": PHONE, "observed_sim_time": 8406971,
                 "observed_traffic_type": 7, "members": [], "observers": [],
                 "children": [
                     {"getter": "getInFrame", "invoked": True,
                      "returned_null": True, "type_name": "object", "error": "",
                      "members": [], "observers": [], "truncated": False},
                     {"getter": "getOutFrame", "invoked": True,
                      "returned_null": False, "type_name": "object", "error": "",
                      "members": ["getSize"],
                      "observers": [{"name": "getSize", "type_name": "function",
                                     "is_callable": True, "arity": 0}],
                      "truncated": False},
                 ]},
                {"index": 104, "in_bounds": True, "frame_found": True,
                 "observed_device": "Switch5", "observed_in_port": "FastEthernet0/2",
                 "observed_sim_time": 8406971, "observed_traffic_type": 7,
                 "members": [], "observers": [], "children": []},
                {"index": 50, "in_bounds": True, "frame_found": True,
                 "observed_device": "Switch5", "observed_in_port": "GigabitEthernet0/1",
                 "observed_sim_time": 8406324, "observed_traffic_type": 11,
                 "members": [], "observers": [], "children": []},
            ],
        })


def hop(**kw):
    base = {"index": 0, "device": "", "previous_device": "", "in_port": None,
            "out_port": None, "sim_time": 0, "traffic_type_raw": 0,
            "status": "sent", "decisions": []}
    base.update(kw)
    return base


PHONE_DHCP = hop(
    index=100, device=PHONE, out_port="Switch", sim_time=8406971,
    traffic_type_raw=7, status="sent",
    decisions=[{"layer": 7, "inbound": False,
                "description": "The DHCP client constructs a Discover packet and sends it out."}],
)
SWITCH_DHCP = hop(
    index=104, device="Switch5", previous_device=PHONE,
    in_port="FastEthernet0/2", sim_time=8406971, traffic_type_raw=7,
    status="dropped",
    decisions=[
        {"layer": 1, "inbound": True, "description": "FastEthernet0/2 receives the frame."},
        {"layer": 2, "inbound": True,
         "description": "FastEthernet0/2 is blocked by STP. The device drops the frame."},
    ],
)
# Same device and type, but from another phone: not the correlated frame.
SWITCH_DHCP_OTHER = hop(
    index=105, device="Switch5", previous_device="OTHER-PHONE",
    in_port="FastEthernet0/9", sim_time=8406971, traffic_type_raw=7,
    status="dropped",
    decisions=[{"layer": 2, "inbound": True,
                "description": "FastEthernet0/9 is blocked by STP. The device drops the frame."}],
)
BPDU = hop(
    index=50, device="Switch5", in_port="GigabitEthernet0/1",
    out_port="FastEthernet0/2", sim_time=8406324, traffic_type_raw=11,
    status="accepted",
    decisions=[{"layer": 2, "inbound": False,
                "description": "The STP process sends out a configuration BPDU."}],
)
# A BPDU out a port the phone never used.
BPDU_OTHER = hop(
    index=51, device="Switch5", out_port="FastEthernet0/9", sim_time=8406324,
    traffic_type_raw=11, status="accepted",
    decisions=[{"layer": 2, "inbound": False,
                "description": "The STP process sends out a configuration BPDU."}],
)


def run(phone_hops, switch_hops):
    transport = Transport()
    out = _frame_observer_discovery(
        transport, phone_name=PHONE, switch_name="Switch5",
        phone_trace={"hops": phone_hops}, switch_trace={"hops": switch_hops},
    )
    out["_calls"] = len(transport.calls)
    return out


verdict = {
    "three": run([PHONE_DHCP], [SWITCH_DHCP_OTHER, SWITCH_DHCP, BPDU_OTHER, BPDU]),
    "no_correlated_switch_dhcp": run([PHONE_DHCP], [BPDU]),
    "no_bpdu_on_that_port": run([PHONE_DHCP], [SWITCH_DHCP, BPDU_OTHER]),
}
print(json.dumps(verdict))
'''


@pytest.fixture(scope="module")
def phase2():
    import subprocess
    import sys as _sys

    code = _P2_PROBE.replace("__ROOT__", repr(str(ROOT))).replace(
        "__SRC__", repr(str(ROOT / "src")),
    )
    completed = subprocess.run(
        [_sys.executable, "-c", code], cwd=ROOT, check=True,
        capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


def test_all_three_comparison_targets_are_selected(phase2):
    targets = {item["role"]: item for item in phase2["three"]["targets"]}

    assert set(targets) == {"phone_dhcp", "switch_dhcp", "switch_bpdu"}
    assert targets["switch_dhcp"]["index"] == 104
    assert targets["switch_bpdu"]["index"] == 50
    assert phase2["three"]["_calls"] == 1


def test_the_switch_dhcp_frame_is_the_one_this_phone_actually_sent(phase2):
    """previous_device is the path proof; another phone's drop is not it."""
    targets = {item["role"]: item for item in phase2["three"]["targets"]}
    switch_dhcp = targets["switch_dhcp"]

    assert switch_dhcp["previous_device"].endswith("PHONE-02")
    assert switch_dhcp["in_port"] == "FastEthernet0/2"
    assert "blocked by STP" in switch_dhcp["identifying_decision"]


def test_the_bpdu_leaves_the_same_physical_port_the_dhcp_entered(phase2):
    targets = {item["role"]: item for item in phase2["three"]["targets"]}

    assert targets["switch_bpdu"]["out_port"] == targets["switch_dhcp"]["in_port"]


def test_same_capture_is_not_same_instant_and_both_are_recorded(phase2):
    case = phase2["three"]
    targets = {item["role"]: item for item in case["targets"]}

    assert case["same_capture"] is True
    # 8406971 vs 8406324 -- hundreds of sim-time units apart.
    assert case["same_instant"] is False
    assert targets["phone_dhcp"]["sim_time"] == targets["switch_dhcp"]["sim_time"]
    assert targets["switch_bpdu"]["sim_time"] != targets["switch_dhcp"]["sim_time"]


def test_without_a_correlated_switch_frame_the_bpdu_has_no_port_to_match(phase2):
    roles = {item["role"] for item in phase2["no_correlated_switch_dhcp"]["targets"]}

    assert "switch_dhcp" not in roles
    assert "switch_bpdu" not in roles


def test_the_journal_retains_what_each_child_getter_returned(phase2):
    """The whole point of the phase. Collecting it and dropping it is a defect.

    The first Phase-2 run enumerated both children in Packet Tracer and then
    wrote a journal with no `children` key at all, so the question the run
    existed to answer came back unanswered. Shape is pinned here, not just
    parsed.
    """
    frames = phase2["three"]["discovery"]["frames"]

    assert frames, "the discovery must retain the frames it enumerated"
    for frame in frames:
        assert "children" in frame, frame.get("index")
        for child in frame["children"]:
            for key in (
                "getter", "invoked", "returned_null", "type_name", "error",
                "members", "observers", "truncated",
            ):
                assert key in child, key


def test_a_missing_bpdu_target_is_named_rather_than_silently_absent(phase2):
    """A bounded capture may hold no BPDU for that exact port.

    The switch rotates its BPDUs across ports, so a 200-frame window can easily
    miss the one port under test. That is a property of the window, and saying
    so is not the same as saying the port sends none.
    """
    case = phase2["no_bpdu_on_that_port"]
    roles = {item["role"] for item in case["targets"]}

    assert roles == {"phone_dhcp", "switch_dhcp"}
    assert "FastEthernet0/2" in case["switch_bpdu_absent_reason"]
    assert "property of the window" in case["switch_bpdu_absent_reason"]


def test_no_correlated_switch_frame_is_a_different_absence(phase2):
    """Without the switch-side frame there is no port to compare on at all."""
    case = phase2["no_correlated_switch_dhcp"]

    assert {item["role"] for item in case["targets"]} == {"phone_dhcp"}
    assert case["switch_bpdu_absent_reason"] == ""
