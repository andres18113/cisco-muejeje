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
    """A VLAN value comes from a frame's own tag read, never from a port.

    Phase 3 does read VLAN values, so "no VLAN anywhere" is no longer the
    invariant.  This one is: these frames share a physical port and returned no
    child object, so every VLAN verdict here stays UNOBSERVABLE and the
    selection metadata carries no VLAN of its own.
    """
    case = selection["both"]
    link = case["link_tag_comparison"]

    assert link["vlan_value_match"] == "UNOBSERVABLE"
    assert link["tag_fields_match"] == "UNOBSERVABLE"
    assert case["frame_vlan_field_semantics"] == (
        "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"
    )
    for target in case["targets"]:
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


# --- phase 3: the four measured tag fields, read as values -------------------
#
# Phase 2 measured the child object of getInFrame/getOutFrame: `vlanId`,
# `tpid`, `cfi` and `userPriority` came back as non-callable, number-typed data
# properties, so no invocation signature is involved in reading them.  This
# phase reads those four and nothing else.
#
# Four literal names are not a property reader.  The same child also exposes a
# payload member, and a loop over discovered names would walk into it and turn
# a bounded reading into a dump.

_TAG_OK = [
    {"name": "vlanId", "observed": True, "type_name": "number",
     "numeric_value": 20, "error": ""},
    {"name": "tpid", "observed": True, "type_name": "number",
     "numeric_value": 33024, "error": ""},
    {"name": "cfi", "observed": True, "type_name": "number",
     "numeric_value": 0, "error": ""},
    {"name": "userPriority", "observed": True, "type_name": "number",
     "numeric_value": 5, "error": ""},
]

_TAG_FRAME = {
    "index": 100,
    "in_bounds": True,
    "frame_found": True,
    "observed_device": "PHONE-02",
    "observed_sim_time": 12433083,
    "observed_traffic_type": 7,
    "members": [], "observers": [], "truncated": False,
    "children": [
        {"getter": "getInFrame", "invoked": True, "returned_null": True,
         "type_name": "object", "error": "", "members": [], "observers": [],
         "truncated": False, "tag": []},
        {"getter": "getOutFrame", "invoked": True, "returned_null": False,
         "type_name": "object", "error": "", "members": [], "observers": [],
         "truncated": False, "tag": _TAG_OK},
    ],
}


def _tag_script() -> str:
    calls: list[str] = []
    _probe({"observed": True, "simulation_mode": True, "frames": []}, calls)\
        .discover_frame_observers([100])
    return calls[0]


def _one_tag(rows):
    """One frame whose single child carries exactly the given tag rows."""
    return {
        "observed": True, "simulation_mode": True, "frame_count": 2341,
        "frames": [{**_TAG_FRAME, "children": [{
            "getter": "getOutFrame", "invoked": True, "returned_null": False,
            "type_name": "object", "error": "", "members": [], "observers": [],
            "truncated": False, "tag": rows,
        }]}],
    }


# 1 -- exactly four names, and they are the measured ones.

def test_exactly_the_four_measured_tag_fields_are_read():
    from src.packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (
        CHILD_TAG_FIELDS,
    )

    assert CHILD_TAG_FIELDS == ("vlanId", "tpid", "cfi", "userPriority")
    script = _tag_script()
    for name in CHILD_TAG_FIELDS:
        assert f"__c.{name}" in script, name


# 2 -- the payload is never traversed.

def test_the_frame_payload_is_never_traversed():
    script = _tag_script()
    source = (
        ROOT / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
        / "frame_observer_probe.py"
    ).read_text(encoding="utf-8")

    assert "payload" not in script
    # The name appears nowhere in the module, so nothing can dispatch on it.
    assert "payload" not in source


# 3 -- no dynamic reader: a retained value only comes from a literal name.

def test_no_tag_value_is_read_through_a_name_chosen_at_runtime():
    script = _tag_script()

    assert "__c[" not in script
    assert "[__name]()" not in script
    # The one dynamic read in the script belongs to the Phase-2 enumerator and
    # keeps only `typeof`; there is no second lookup that retains a value.
    assert script.count("__o[__name]") == 1


# 4, 5 -- zero is a reading; anything that is not a finite number is not.

def test_a_zero_tag_value_is_a_value_and_never_an_absence():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 2341,
        "frames": [_TAG_FRAME],
    }).discover_frame_observers([100])

    fields = observed.frames[0].children[1].tag_by_name
    assert fields["cfi"].observed is True
    assert fields["cfi"].numeric_value == 0
    assert fields["vlanId"].numeric_value == 20
    assert fields["tpid"].numeric_value == 33024
    assert fields["userPriority"].numeric_value == 5


def test_a_non_numeric_tag_value_fails_closed_without_coercion():
    observed = _probe(_one_tag([
        {"name": "vlanId", "observed": True, "type_name": "string",
         "numeric_value": "20", "error": ""},
    ])).discover_frame_observers([100])

    field = observed.frames[0].children[0].tag_by_name["vlanId"]
    assert field.observed is False
    assert field.type_name == "string"
    assert field.numeric_value is None


def test_a_boolean_is_not_a_number_and_never_becomes_one():
    observed = _probe(_one_tag([
        {"name": "cfi", "observed": True, "type_name": "boolean",
         "numeric_value": True, "error": ""},
    ])).discover_frame_observers([100])

    field = observed.frames[0].children[0].tag_by_name["cfi"]
    assert field.observed is False
    assert field.numeric_value is None


def test_a_non_finite_value_never_becomes_a_reading():
    observed = _probe(_one_tag([
        {"name": "vlanId", "observed": True, "type_name": "number",
         "numeric_value": float("inf"), "error": ""},
    ])).discover_frame_observers([100])

    field = observed.frames[0].children[0].tag_by_name["vlanId"]
    assert field.observed is False
    assert field.numeric_value is None


def test_the_script_itself_requires_a_finite_number_before_observing():
    script = _tag_script()

    assert "isFinite" in script
    assert "numeric_value:null" in script


# 6 -- a field that threw keeps its error, and a null child carries no tag.

def test_a_tag_field_that_threw_keeps_its_error_and_stays_unobserved():
    observed = _probe(_one_tag([
        {"name": "tpid", "observed": False, "type_name": "",
         "numeric_value": None, "error": "TypeError: boom"},
    ])).discover_frame_observers([100])

    field = observed.frames[0].children[0].tag_by_name["tpid"]
    assert field.observed is False
    assert field.error == "TypeError: boom"
    assert field.numeric_value is None


def test_a_null_child_carries_no_tag_at_all():
    observed = _probe({
        "observed": True, "simulation_mode": True, "frame_count": 2341,
        "frames": [_TAG_FRAME],
    }).discover_frame_observers([100])

    child = observed.frames[0].children[0]
    assert child.returned_null is True
    assert child.tag == ()
    assert child.tag_by_name == {}


def test_an_asserted_observation_without_a_finite_number_does_not_survive():
    """`observed` is re-decided here; the script's word alone never carries it."""
    observed = _probe(_one_tag([
        {"name": "vlanId", "observed": True, "type_name": "undefined",
         "numeric_value": None, "error": ""},
    ])).discover_frame_observers([100])

    assert observed.frames[0].children[0].tag_by_name["vlanId"].observed is False


def test_the_target_bound_admits_the_comparison_and_the_two_controls():
    from src.packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (
        MAX_VLAN_CONTROL_TARGETS,
    )

    # Three comparison frames plus at most two independently known controls.
    assert MAX_VLAN_CONTROL_TARGETS == 2
    assert MAX_FRAME_TARGETS == 3 + MAX_VLAN_CONTROL_TARGETS


# --- phase 3, runner slice: the link comparison and its calibration ----------

_P3_PROBE = r'''
import json
import sys

sys.path.insert(0, __ROOT__)
sys.path.insert(0, __SRC__)

from tools.cp_scale_canonical_live import (
    _frame_observer_discovery,
    _single_vlan_access_ports,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureAccessPort,
)

PHONE = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PHONE-02"
SWITCH = "Switch5"
T = 12433083


def tag(vlan=None, tpid=None, cfi=None, up=None):
    rows = []
    for name, value in (("vlanId", vlan), ("tpid", tpid), ("cfi", cfi),
                        ("userPriority", up)):
        if value is None:
            continue
        rows.append({"name": name, "observed": True, "type_name": "number",
                     "numeric_value": value, "error": ""})
    return rows


def child(getter, rows=None, null=False):
    return {"getter": getter, "invoked": True, "returned_null": null,
            "type_name": "object", "error": "", "members": [], "observers": [],
            "truncated": False, "tag": rows or []}


def frame(index, device, in_port="", sim_time=T, ttype=7, children=None):
    return {"index": index, "in_bounds": True, "frame_found": True,
            "observed_device": device, "observed_in_port": in_port,
            "observed_sim_time": sim_time, "observed_traffic_type": ttype,
            "members": [], "observers": [], "truncated": False,
            "children": children or []}


def hop(**kw):
    base = {"index": 0, "device": "", "previous_device": "", "in_port": None,
            "out_port": None, "sim_time": T, "traffic_type_raw": 7,
            "status": "sent", "decisions": []}
    base.update(kw)
    return base


PHONE_DHCP = hop(
    index=100, device=PHONE, out_port="Switch", status="sent",
    decisions=[{"layer": 7, "inbound": False,
                "description": "The DHCP client constructs a Discover packet and sends it out."}],
)
SWITCH_DHCP = hop(
    index=104, device=SWITCH, previous_device=PHONE, in_port="FastEthernet0/2",
    status="dropped",
    decisions=[{"layer": 2, "inbound": True,
                "description": "FastEthernet0/2 is blocked by STP. The device drops the frame."}],
)
BPDU = hop(
    index=50, device=SWITCH, in_port="GigabitEthernet0/1",
    out_port="FastEthernet0/2", sim_time=T - 700, traffic_type_raw=11,
    status="accepted",
    decisions=[{"layer": 2, "inbound": False,
                "description": "The STP process sends out a configuration BPDU."}],
)
CCTV_IN = hop(index=70, device=SWITCH, in_port="FastEthernet0/24",
              sim_time=T - 40, traffic_type_raw=3, status="sent")
IOT_IN = hop(index=71, device=SWITCH, in_port="FastEthernet0/23",
             sim_time=T - 60, traffic_type_raw=3, status="sent")


class Transport:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def send_and_wait(self, js, timeout=10.0):
        self.calls.append(js)
        return json.dumps({
            "observed": True, "simulation_mode": True, "frame_count": 2341,
            "frames": self.frames,
        })


def run(phone_hops, switch_hops, frames, ports=None):
    transport = Transport(frames)
    out = _frame_observer_discovery(
        transport, phone_name=PHONE, switch_name=SWITCH,
        phone_trace={"hops": phone_hops}, switch_trace={"hops": switch_hops},
        single_vlan_ports=ports,
    )
    out["_calls"] = len(transport.calls)
    return out


FULL = tag(vlan=20, tpid=33024, cfi=0, up=5)
PHONE_F = frame(100, PHONE, children=[child("getInFrame", null=True),
                                      child("getOutFrame", FULL)])


def switch_frame(rows, in_port="FastEthernet0/2", device=SWITCH, null=False):
    return frame(104, device, in_port=in_port,
                 children=[child("getInFrame", rows, null=null),
                           child("getOutFrame", null=True)])


BPDU_F = frame(50, SWITCH, in_port="GigabitEthernet0/1", sim_time=T - 700,
               ttype=11, children=[child("getInFrame", null=True),
                                   child("getOutFrame", null=True)])


def access(name, interface, data_vlan, voice_vlan=None):
    return ConfigureAccessPort(
        id=name, phase=ConfigurationPhase.L2_INTERFACES, device_id="d",
        device_name=SWITCH, site_id="s", interface=interface,
        data_vlan_id=data_vlan, voice_vlan_id=voice_vlan,
    )


class Projection:
    class configuration:
        actions = [
            access("a1", "FastEthernet0/24", 40),
            access("a2", "FastEthernet0/23", 30),
            access("a3", "FastEthernet0/2", 10, voice_vlan=20),
        ]


verdict = {
    "preserved": run([PHONE_DHCP], [SWITCH_DHCP, BPDU],
                     [PHONE_F, switch_frame(FULL), BPDU_F]),
    "contradiction": run(
        [PHONE_DHCP], [SWITCH_DHCP],
        [PHONE_F, switch_frame(tag(vlan=10, tpid=33024, cfi=0, up=5))]),
    "switch_child_null": run([PHONE_DHCP], [SWITCH_DHCP],
                             [PHONE_F, switch_frame(None, null=True)]),
    "identity_mismatch": run(
        [PHONE_DHCP], [SWITCH_DHCP],
        [PHONE_F, switch_frame(FULL, device="Switch9")]),
    "port_mismatch": run(
        [PHONE_DHCP], [SWITCH_DHCP],
        [PHONE_F, switch_frame(FULL, in_port="FastEthernet0/9")]),
    "partial": run(
        [PHONE_DHCP], [SWITCH_DHCP],
        [PHONE_F, switch_frame(tag(vlan=20, tpid=33024))]),
    "no_bpdu": run([PHONE_DHCP], [SWITCH_DHCP],
                   [PHONE_F, switch_frame(FULL)]),
    "no_control": run([PHONE_DHCP], [SWITCH_DHCP],
                      [PHONE_F, switch_frame(FULL)], ports={}),
    "one_control": run(
        [PHONE_DHCP], [SWITCH_DHCP, CCTV_IN],
        [PHONE_F, switch_frame(FULL),
         frame(70, SWITCH, in_port="FastEthernet0/24", sim_time=T - 40, ttype=3,
               children=[child("getInFrame", tag(vlan=40, tpid=33024)),
                         child("getOutFrame", null=True)])],
        ports={"FastEthernet0/24": 40, "FastEthernet0/23": 30}),
    "two_controls": run(
        [PHONE_DHCP], [SWITCH_DHCP, CCTV_IN, IOT_IN],
        [PHONE_F, switch_frame(FULL),
         frame(70, SWITCH, in_port="FastEthernet0/24", sim_time=T - 40, ttype=3,
               children=[child("getInFrame", tag(vlan=40))]),
         frame(71, SWITCH, in_port="FastEthernet0/23", sim_time=T - 60, ttype=3,
               children=[child("getInFrame", tag(vlan=30))])],
        ports={"FastEthernet0/24": 40, "FastEthernet0/23": 30}),
    "control_contradicted": run(
        [PHONE_DHCP], [SWITCH_DHCP, CCTV_IN],
        [PHONE_F, switch_frame(FULL),
         frame(70, SWITCH, in_port="FastEthernet0/24", sim_time=T - 40, ttype=3,
               children=[child("getInFrame", tag(vlan=99))])],
        ports={"FastEthernet0/24": 40}),
}
verdict["_ports"] = _single_vlan_access_ports(Projection, SWITCH)
verdict["_ports_other_device"] = _single_vlan_access_ports(Projection, "Switch7")
print(json.dumps(verdict))
'''


@pytest.fixture(scope="module")
def phase3():
    import subprocess
    import sys as _sys

    code = _P3_PROBE.replace("__ROOT__", repr(str(ROOT))).replace(
        "__SRC__", repr(str(ROOT / "src")),
    )
    completed = subprocess.run(
        [_sys.executable, "-c", code], cwd=ROOT, check=True,
        capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


# 7 -- egress is read on getOutFrame and ingress on getInFrame, never crossed.

def test_each_side_is_read_on_its_own_getter(phase3):
    link = phase3["preserved"]["link_tag_comparison"]

    assert link["phone_dhcp_out_tag"]["getter"] == "getOutFrame"
    assert link["switch_dhcp_in_tag"]["getter"] == "getInFrame"
    assert link["phone_dhcp_out_tag"]["frame_index"] == 100
    assert link["switch_dhcp_in_tag"]["frame_index"] == 104
    assert phase3["preserved"]["_calls"] == 1


def test_the_four_measured_fields_travel_with_each_side(phase3):
    link = phase3["preserved"]["link_tag_comparison"]

    for side in ("phone_dhcp_out_tag", "switch_dhcp_in_tag"):
        fields = link[side]["fields"]
        assert set(fields) == {"vlanId", "tpid", "cfi", "userPriority"}
        for name, row in fields.items():
            for key in ("observed", "type_name", "numeric_value", "error"):
                assert key in row, (side, name, key)
    assert link["phone_dhcp_out_tag"]["fields"]["cfi"]["numeric_value"] == 0
    assert link["phone_dhcp_out_tag"]["fields"]["cfi"]["observed"] is True


# 11, 12 -- equality is computed only from two fresh readings.

def test_two_equal_readings_are_a_match_and_the_values_survive(phase3):
    link = phase3["preserved"]["link_tag_comparison"]

    assert link["vlan_value_match"] == "YES"
    assert link["tpid_match"] == "YES"
    assert link["tag_fields_match"] == "YES"
    assert link["phone_dhcp_out_tag"]["fields"]["vlanId"]["numeric_value"] == 20
    assert link["switch_dhcp_in_tag"]["fields"]["vlanId"]["numeric_value"] == 20
    assert link["phone_dhcp_out_tag"]["fields"]["tpid"]["numeric_value"] == 33024
    assert link["tpid_hex"] == "0x8100"


def test_a_different_vlan_is_kept_as_a_contradiction_not_smoothed(phase3):
    link = phase3["contradiction"]["link_tag_comparison"]

    assert link["vlan_value_match"] == "NO"
    assert link["phone_dhcp_out_tag"]["fields"]["vlanId"]["numeric_value"] == 20
    assert link["switch_dhcp_in_tag"]["fields"]["vlanId"]["numeric_value"] == 10
    assert link["tpid_match"] == "YES"
    assert link["tag_fields_match"] == "NO"


def test_incomplete_coverage_that_agrees_is_partial_and_not_a_match(phase3):
    link = phase3["partial"]["link_tag_comparison"]

    assert link["vlan_value_match"] == "YES"
    assert link["tag_fields_match"] == "PARTIAL"
    assert link["switch_dhcp_in_tag"]["fields"]["cfi"]["observed"] is False


# 6, 11 -- one side unreadable can never produce an equality.

def test_a_missing_child_makes_the_comparison_unobservable(phase3):
    case = phase3["switch_child_null"]
    link = case["link_tag_comparison"]

    assert link["vlan_value_match"] == "UNOBSERVABLE"
    assert link["tpid_match"] == "UNOBSERVABLE"
    assert link["tag_fields_match"] == "UNOBSERVABLE"
    assert link["switch_dhcp_in_tag"]["child_returned"] is False
    assert link["switch_dhcp_in_tag"]["fields"] == {}
    # The side that WAS read keeps its values; absence deletes nothing.
    assert link["phone_dhcp_out_tag"]["fields"]["vlanId"]["numeric_value"] == 20


# 8, 9 -- attribution first; a value is never claimed for the wrong frame.

def test_a_frame_that_is_not_the_selected_one_yields_no_value(phase3):
    link = phase3["identity_mismatch"]["link_tag_comparison"]

    assert link["switch_dhcp_in_tag"]["identity_reconfirmed"] is False
    assert link["switch_dhcp_in_tag"]["fields"] == {}
    assert link["vlan_value_match"] == "UNOBSERVABLE"
    assert "attribut" in link["switch_dhcp_in_tag"]["failure_reason"].casefold()


def test_the_ingress_port_is_part_of_the_reconfirmed_identity(phase3):
    """The event list is live; the same index may name another frame."""
    link = phase3["port_mismatch"]["link_tag_comparison"]

    assert link["switch_dhcp_in_tag"]["identity_reconfirmed"] is False
    assert link["switch_dhcp_in_tag"]["fields"] == {}
    assert link["vlan_value_match"] == "UNOBSERVABLE"


# 10 -- the exact observed instant travels with the comparison.

def test_the_same_observed_start_sim_time_is_retained(phase3):
    link = phase3["preserved"]["link_tag_comparison"]

    assert link["phone_dhcp_out_tag"]["observed_sim_time"] == 12433083
    assert link["switch_dhcp_in_tag"]["observed_sim_time"] == 12433083
    assert link["same_observed_start_sim_time"] == "YES"


# 15 -- the primary comparison never depends on a BPDU.

def test_the_link_comparison_stands_without_any_bpdu(phase3):
    case = phase3["no_bpdu"]

    assert {item["role"] for item in case["targets"]} == {
        "phone_dhcp", "switch_dhcp",
    }
    assert case["switch_bpdu_absent_reason"]
    assert case["link_tag_comparison"]["vlan_value_match"] == "YES"
    assert case["vlan_scoped_stp_interpretation"] == "STILL_INFERENCE"


# 13, 14 -- the calibration control is optional and cannot contaminate.

def test_a_matching_single_vlan_control_qualifies_the_field(phase3):
    case = phase3["one_control"]
    control = case["vlan_controls"][0]

    assert case["frame_vlan_field_semantics"] == "SUPPORTED_BY_CONTROL"
    assert control["port"] == "FastEthernet0/24"
    assert control["port_side"] == "in"
    assert control["expected_vlan"] == 40
    assert control["observed_vlan"] == 40
    assert control["vlan_match"] is True


def test_two_distinct_matching_controls_qualify_it_more_strongly(phase3):
    case = phase3["two_controls"]

    assert case["frame_vlan_field_semantics"] == (
        "STRONGLY_SUPPORTED_BY_MULTIVLAN_CONTROL"
    )
    assert sorted(item["expected_vlan"] for item in case["vlan_controls"]) == [30, 40]


def test_a_control_that_disagrees_is_named_and_never_averaged_away(phase3):
    case = phase3["control_contradicted"]
    link = case["link_tag_comparison"]

    assert case["frame_vlan_field_semantics"] == "CONTRADICTED_BY_CONTROL"
    assert case["vlan_controls"][0]["vlan_match"] is False
    # The DHCP evidence is untouched by what the control did.
    assert link["vlan_value_match"] == "YES"
    assert link["phone_dhcp_out_tag"]["fields"]["vlanId"]["numeric_value"] == 20


def test_no_control_leaves_the_field_unqualified_and_the_values_intact(phase3):
    case = phase3["no_control"]

    assert case["frame_vlan_field_semantics"] == (
        "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"
    )
    assert case["vlan_controls"] == []
    assert case["vlan_control_absent_reason"]
    assert case["link_tag_comparison"]["vlan_value_match"] == "YES"


def test_a_control_never_enters_the_dhcp_target_set_or_its_instant(phase3):
    """Its own sim_time must not make the DHCP pair look non-simultaneous."""
    case = phase3["one_control"]

    assert {item["role"] for item in case["targets"]} == {
        "phone_dhcp", "switch_dhcp",
    }
    assert case["same_instant"] is True
    assert case["link_tag_comparison"]["same_observed_start_sim_time"] == "YES"


# The control set comes from the typed plan, never from a port name.

def test_only_a_port_the_plan_gives_one_vlan_can_calibrate(phase3):
    ports = phase3["_ports"]

    # The phone port carries data 10 AND voice 20: either reading would look
    # right, so it can calibrate nothing.
    assert "FastEthernet0/2" not in ports
    assert ports == {"FastEthernet0/24": 40, "FastEthernet0/23": 30}
    assert phase3["_ports_other_device"] == {}


# 16, 17, 18 -- this phase still adds no MAC work, no lifecycle, no classifier.

def test_the_phase_three_slice_adds_no_mac_lifecycle_or_classifier():
    source = (ROOT / "tools" / "cp_scale_canonical_live.py").read_text(
        encoding="utf-8",
    )
    start = source.index("def _tag_field_observation")
    body = source[start:source.index("\ndef _post_failure_simulation_diagnostic")]

    for forbidden in (
        "mac address-table", "mac_address_table", "SHOW_MAC", "portfast",
        "bpduguard", "setPower", "setDhcpClientFlag", "configurePcIp",
        "TRAFFIC_TYPES", "type7 =", "show vlan",
    ):
        assert forbidden not in body, forbidden
