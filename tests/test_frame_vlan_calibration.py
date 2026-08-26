"""Contracts for calibrating `child.vlanId` without a cross-side assumption.

Two governed LIVEs read `vlanId = 20` on both sides of PHONE-02's DHCP link, and
neither could say what that 20 MEANS: no frame in either window entered a port
whose VLAN was independently known, so the field stayed
DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED.

The calibration this covers is the smallest thing that can close that: a
disposable switch whose access port VLAN is proven by DIRECT readback, an
endpoint attached to that port, and the `getInFrame()` of a frame that ENTERED
by it.  Expected and observed both come from the ingress side, so nothing is
assumed about what the switch does between one boca and the other.

The tempting shortcut -- pairing an egress port's known VLAN with the tagged
ingress copy -- is refused in `test_frame_observer_probe.py` and must stay
refused here: a calibration resting on an unmeasured assumption qualifies
nothing.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.qualify_frame_vlan_calibration import (
    CALIBRATION_PREFIX,
    CONTROL_VLAN_IDS,
    FrameVlanCalibrationResult,
    VlanCalibrationControl,
)


def control(**kw) -> VlanCalibrationControl:
    base = {
        "vlan_id": 742,
        "switch_interface": "FastEthernet0/1",
        "endpoint_name": "__MCP_VLANCAL_abc_PC0",
        "access_vlan_verified": True,
        "voice_vlan_claimed": False,
        "frame_index": 12,
        "frame_observed_in_port": "FastEthernet0/1",
        "frame_previous_device": "__MCP_VLANCAL_abc_PC0",
        "identity_reconfirmed": True,
        "child_returned": True,
        "observed_vlan": 742,
    }
    base.update(kw)
    return VlanCalibrationControl(**base)


def result(*controls) -> FrameVlanCalibrationResult:
    return FrameVlanCalibrationResult(controls=tuple(controls))


# 1 -- the two VLANs are distinct, reserved-prefixed and not the default.

def test_the_two_control_vlans_are_distinct_and_not_the_default():
    assert len(CONTROL_VLAN_IDS) == 2
    assert len(set(CONTROL_VLAN_IDS)) == 2
    assert 1 not in CONTROL_VLAN_IDS
    # Outside PT's reserved 1002-1005 range, so "it matched" and "it was read"
    # can never be confused with a default the backend invented.
    for vlan in CONTROL_VLAN_IDS:
        assert 1 < vlan < 1002 or vlan > 1005
    assert CALIBRATION_PREFIX.startswith("__MCP_")


# 2 -- the expected VLAN is only ever the DIRECT readback, never the intent.

def test_an_applied_but_unverified_port_can_never_qualify():
    """APPLIED is not VERIFIED. A port nobody read back proves no VLAN."""
    item = control(access_vlan_verified=False)

    assert item.expected_vlan_qualified is False
    assert item.match == "UNOBSERVABLE"


def test_a_port_claiming_a_voice_vlan_is_refused_as_ambiguous():
    """Data AND voice on one port means either value would look right."""
    item = control(voice_vlan_claimed=True)

    assert item.expected_vlan_qualified is False
    assert item.match == "UNOBSERVABLE"


# 3 -- the frame must be the one that ENTERED that exact port.

def test_a_frame_whose_identity_was_not_reconfirmed_yields_no_match():
    assert control(identity_reconfirmed=False).match == "UNOBSERVABLE"


def test_a_child_that_returned_no_vlan_yields_no_match():
    assert control(observed_vlan=None, child_returned=False).match == "UNOBSERVABLE"


# 4 -- equality, contradiction, and the two qualification strengths.

def test_one_matching_control_supports_the_field():
    assert result(control()).semantics == "SUPPORTED_BY_CONTROL"


def test_two_matching_controls_on_distinct_vlans_support_it_strongly():
    outcome = result(control(), control(vlan_id=743, observed_vlan=743))

    assert outcome.semantics == "STRONGLY_SUPPORTED_BY_MULTIVLAN_CONTROL"


def test_two_matching_controls_on_the_SAME_vlan_are_not_multivlan():
    """Two readings of one VLAN are one calibration observed twice."""
    outcome = result(control(), control(switch_interface="FastEthernet0/2"))

    assert outcome.semantics == "SUPPORTED_BY_CONTROL"


def test_a_contradiction_is_never_averaged_against_a_match():
    outcome = result(control(), control(vlan_id=743, observed_vlan=742))

    assert outcome.controls[1].match == "NO"
    assert outcome.semantics == "CONTRADICTED_BY_CONTROL"


def test_no_usable_control_leaves_the_field_exactly_where_it_was():
    outcome = result(control(access_vlan_verified=False))

    assert outcome.semantics == "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"
    assert result().semantics == "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"


# 5 -- zero is a value here too, and nothing is coerced.

def test_a_zero_vlan_reading_is_a_reading_and_contradicts_a_known_port():
    item = control(observed_vlan=0)

    assert item.match == "NO"


def test_a_non_numeric_reading_never_becomes_a_match():
    assert control(observed_vlan="742").match == "UNOBSERVABLE"
    assert control(observed_vlan=True).match == "UNOBSERVABLE"


# --- the pass itself, driven entirely by fakes -------------------------------
#
# The orchestration is what decides which frame is allowed to calibrate, so it
# is proven offline before any Packet Tracer run pays for it.

from src.packet_tracer_mcp.application.use_cases.qualify_frame_vlan_calibration import (  # noqa: E402
    CONTROL_VLAN_IDS as VLANS,
    FrameVlanCalibrationQualifier,
    MAX_ENUMERATED,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (  # noqa: E402
    MutationDisposition,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (  # noqa: E402
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (  # noqa: E402
    FrameChildDiscovery,
    FrameInstanceDiscovery,
    FrameObserverDiscovery,
    FrameTagField,
)


class Mutation:
    def __init__(self, applied=True, disposition=MutationDisposition.CHANGED, message=""):
        self.applied = applied
        self.disposition = disposition
        self.message = message


class Ports:
    def __init__(self, names):
        self.interfaces = [type("P", (), {"name": n})() for n in names]


class FakePhysical:
    def __init__(self, ports=None, empty=True):
        self.created, self.removed, self.links = [], [], []
        self._ports = ports or ["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3"]
        self._empty = empty

    def observe_workspace(self):
        occupied = [] if self._empty else [PhysicalWorkspaceDeviceObservation(
            name="OPERATOR-ROUTER", model="2911",
        )]
        return PhysicalWorkspaceObservation(
            observed=True, devices=occupied, links=[],
        )

    def ensure_device(self, device):
        self.created.append(device.name)
        return Mutation()

    def observe_device(self, device):
        return Ports(self._ports)

    def remove_device(self, device):
        self.removed.append(device.name)
        return Mutation()

    def ensure_link(self, link):
        self.links.append((link.device_a, link.port_b))
        return Mutation()


class FakeConfiguration:
    def __init__(self, verified=True):
        self.actions, self.expectations = [], []
        self._verified = verified

    def inventory(self):
        return []

    def apply_actions(self, actions):
        self.actions.extend(actions)
        return []

    def verify(self, expectations):
        self.expectations.extend(expectations)
        return [
            type("V", (), {
                "expectation_id": item.id,
                "fresh_evidence": self._verified,
                "fields": {"vlan_id": "verified" if self._verified else "unobservable"},
            })()
            for item in expectations
        ]


class FakeEndpoints:
    def __init__(self, ok=True):
        self.armed, self._ok = [], ok

    def configure_endpoint_dhcp(self, device, interface="FastEthernet0"):
        self.armed.append(device)
        return self._ok


class Hop:
    def __init__(self, index, in_port, previous_device, sim_time=10, ttype=7):
        self.index, self.in_port = index, in_port
        self.previous_device = previous_device
        self.sim_time, self.traffic_type_raw = sim_time, ttype


class FakeSimulation:
    def __init__(self, hops, original=False):
        self.hops, self.steps, self.modes = hops, [], []
        self._mode = original
        self._original = original

    def read_simulation_state(self):
        return type("S", (), {"observed": True, "simulation_mode": self._mode})()

    def set_simulation_mode(self, on):
        self._mode = on
        self.modes.append(on)
        return type("M", (), {"observed": True})()

    def step(self, action="forward", times=1):
        self.steps.append((action, times))
        return type("R", (), {"observed": True})()

    def read_trace(self, limit=200, device=""):
        return type("T", (), {"observed": True, "hops": self.hops})()


class FakeProbe:
    def __init__(self, tags):
        """tags: {frame_index: vlan value or None}."""
        self.calls, self._tags = [], tags

    def discover_frame_observers(self, indices, *, timeout=10.0):
        self.calls.append(list(indices))
        frames = []
        for index in indices:
            value = self._tags.get(index)
            tag = ()
            if value is not None:
                tag = (FrameTagField(
                    name="vlanId", observed=True, type_name="number",
                    numeric_value=value,
                ),)
            frames.append(FrameInstanceDiscovery(
                index=index, in_bounds=True, frame_found=True,
                observed_device="__MCP_VLANCAL_tok_SW",
                observed_in_port=SLOTS[index], observed_sim_time=10,
                observed_traffic_type=7,
                children=(FrameChildDiscovery(
                    getter="getInFrame", invoked=True, returned_null=value is None,
                    type_name="object", tag=tag,
                ),),
            ))
        return FrameObserverDiscovery(
            observed=True, simulation_mode=True, frame_count=99,
            frames=tuple(frames),
        )


SLOTS = {}


def run_pass(hops, tags, *, verified=True, empty=True, armed=True, ports=None):
    SLOTS.clear()
    SLOTS.update({hop.index: hop.in_port for hop in hops})
    physical = FakePhysical(ports=ports, empty=empty)
    configuration = FakeConfiguration(verified=verified)
    endpoints = FakeEndpoints(ok=armed)
    simulation = FakeSimulation(hops)
    probe = FakeProbe(tags)
    outcome = FrameVlanCalibrationQualifier(
        physical, configuration, endpoints, simulation, probe, name_token="tok",
    ).qualify("2960", "PC")
    return outcome, physical, configuration, endpoints, simulation, probe


PC0, PC1 = "__MCP_VLANCAL_tok_PC0", "__MCP_VLANCAL_tok_PC1"
GOOD = [Hop(11, "FastEthernet0/1", PC0), Hop(12, "FastEthernet0/2", PC1)]


def test_two_ingress_controls_on_distinct_vlans_qualify_strongly():
    outcome, physical, _c, endpoints, sim, probe = run_pass(
        GOOD, {11: VLANS[0], 12: VLANS[1]},
    )

    assert outcome.errors == ()
    assert outcome.semantics == "STRONGLY_SUPPORTED_BY_MULTIVLAN_CONTROL"
    assert [c.match for c in outcome.controls] == ["YES", "YES"]
    assert [c.vlan_id for c in outcome.controls] == list(VLANS)
    assert endpoints.armed == [PC0, PC1]
    assert probe.calls == [[11, 12]]
    # Simulation was entered, reset first, and given back.
    assert sim.steps[0] == ("reset", 1)
    assert sim.modes[0] is True and sim.modes[-1] is False


def test_a_non_empty_workspace_is_refused_before_any_mutation():
    outcome, physical, _c, endpoints, sim, _p = run_pass(GOOD, {}, empty=False)

    assert physical.created == [] and physical.links == []
    assert endpoints.armed == [] and sim.modes == []
    assert "refuses to mutate" in outcome.errors[0]


def test_every_created_device_is_removed_in_reverse_order():
    outcome, physical, *_ = run_pass(GOOD, {11: VLANS[0], 12: VLANS[1]})

    assert physical.created == ["__MCP_VLANCAL_tok_SW", PC0, PC1]
    assert physical.removed == list(reversed(physical.created))
    assert outcome.removed == tuple(physical.removed)
    assert outcome.restored is True
    assert outcome.realtime_restored is True


def test_a_frame_entering_the_right_port_from_another_device_is_not_a_control():
    """The endpoint on that port is what makes the VLAN attributable."""
    hops = [Hop(11, "FastEthernet0/1", "SOMEONE-ELSE"), Hop(12, "FastEthernet0/2", PC1)]
    outcome, *_rest = run_pass(hops, {11: VLANS[0], 12: VLANS[1]})

    first, second = outcome.controls
    assert first.match == "UNOBSERVABLE"
    assert first.frame_index is None
    assert second.match == "YES"
    assert outcome.semantics == "SUPPORTED_BY_CONTROL"


def test_an_applied_but_unread_access_vlan_qualifies_nothing():
    outcome, *_rest = run_pass(
        GOOD, {11: VLANS[0], 12: VLANS[1]}, verified=False,
    )

    assert [c.access_vlan_verified for c in outcome.controls] == [False, False]
    assert outcome.semantics == "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"


def test_a_disagreeing_reading_is_a_contradiction_not_an_absence():
    outcome, *_rest = run_pass(GOOD, {11: VLANS[0], 12: VLANS[0]})

    assert outcome.controls[1].match == "NO"
    assert outcome.semantics == "CONTRADICTED_BY_CONTROL"


def test_a_child_with_no_readable_vlan_stays_unobservable():
    outcome, *_rest = run_pass(GOOD, {11: VLANS[0], 12: None})

    assert outcome.controls[1].match == "UNOBSERVABLE"
    assert outcome.controls[1].child_returned is False
    assert "no object" in outcome.controls[1].failure_reason


def test_an_empty_window_is_named_and_never_read_as_a_contradiction():
    outcome, _p, _c, _e, _s, probe = run_pass([], {})

    assert probe.calls == []
    assert all(c.match == "UNOBSERVABLE" for c in outcome.controls)
    assert any("property of the window" in item for item in outcome.errors)
    assert outcome.semantics == "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"


def test_a_switch_without_enough_access_ports_mutates_nothing_further():
    outcome, physical, *_ = run_pass(
        GOOD, {}, ports=["FastEthernet0/1"],
    )

    assert physical.created == ["__MCP_VLANCAL_tok_SW"]
    assert physical.removed == ["__MCP_VLANCAL_tok_SW"]
    assert any("are required" in item for item in outcome.errors)


def test_the_enumeration_stays_bounded():
    assert MAX_ENUMERATED == len(VLANS)
