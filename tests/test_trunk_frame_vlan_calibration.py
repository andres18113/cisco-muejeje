"""Contracts for a non-circular tagged trunk-ingress VLAN calibration."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.qualify_trunk_frame_vlan_calibration import (
    CONTROL_VLAN_IDS,
    TRUNK_CALIBRATION_PREFIX,
    TrunkFrameVlanCalibrationQualifier,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    MutationDisposition,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    TrunkReadbackObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.frame_observer_probe import (
    FrameChildDiscovery,
    FrameInstanceDiscovery,
    FrameObserverDiscovery,
    FrameTagField,
)


class Mutation:
    def __init__(
        self,
        applied: bool = True,
        disposition: MutationDisposition = MutationDisposition.CHANGED,
        message: str = "",
    ) -> None:
        self.applied = applied
        self.disposition = disposition
        self.message = message


class Ports:
    def __init__(self, names: list[str]) -> None:
        self.interfaces = [type("P", (), {"name": name})() for name in names]


class FakePhysical:
    def __init__(self, *, empty: bool = True) -> None:
        self.created: list[str] = []
        self.removed: list[str] = []
        self.links: list[tuple[str, str, str, str]] = []
        self._empty = empty
        self._ports = [
            "FastEthernet0/1",
            "FastEthernet0/2",
            "FastEthernet0/3",
            "FastEthernet0/4",
        ]

    def observe_workspace(self):
        devices = [] if self._empty else [PhysicalWorkspaceDeviceObservation(
            name="OPERATOR-SWITCH", model="3560-24PS",
        )]
        return PhysicalWorkspaceObservation(observed=True, devices=devices, links=[])

    def ensure_device(self, device):
        self.created.append(device.name)
        return Mutation()

    def observe_device(self, _device):
        return Ports(self._ports)

    def remove_device(self, device):
        self.removed.append(device.name)
        return Mutation()

    def ensure_link(self, link):
        self.links.append((link.device_a, link.port_a, link.device_b, link.port_b))
        return Mutation()


class FakeConfiguration:
    def __init__(
        self,
        overrides: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.actions: list[object] = []
        self.expectations: list[object] = []
        self.reads: list[tuple[str, str]] = []
        self._overrides = overrides or {}

    def inventory(self):
        return []

    def apply_actions(self, actions):
        self.actions.extend(actions)
        return []

    def verify(self, expectations):
        self.expectations.extend(expectations)
        return [type("V", (), {
            "expectation_id": item.id,
            "status": "verified",
            "fresh_evidence": True,
            "fields": {
                "interface": "verified",
                "status": "verified",
                "allowed_vlans": "verified",
                "active_vlans": "verified",
                "forwarding_vlans": "verified",
            },
        })() for item in expectations]

    def read_trunk(self, device_name: str, interface: str):
        self.reads.append((device_name, interface))
        vlan = CONTROL_VLAN_IDS[int(interface.rsplit("/", 1)[1]) - 1]
        values: dict[str, object] = {
            "device_name": device_name,
            "requested_interface": interface,
            "interface": interface,
            "status": "trunking",
            "native_vlan": 1,
            "allowed_vlans": (vlan,),
            "active_vlans": (vlan,),
            "forwarding_vlans": (vlan,),
            "fresh_evidence": True,
            "output_complete": True,
        }
        values.update(self._overrides.get(interface, {}))
        return TrunkReadbackObservation(**values)


class FakeEndpoints:
    def __init__(self, ok: bool = True) -> None:
        self.armed: list[str] = []
        self._ok = ok

    def configure_endpoint_dhcp(self, device, interface="FastEthernet0"):
        self.armed.append(device)
        return self._ok


class Hop:
    def __init__(self, index: int, in_port: str, previous_device: str) -> None:
        self.index = index
        self.in_port = in_port
        self.previous_device = previous_device
        self.sim_time = 10
        self.traffic_type_raw = 7


class FakeSimulation:
    def __init__(self, hops: list[Hop]) -> None:
        self.hops = hops
        self.steps: list[tuple[str, int]] = []
        self.modes: list[bool] = []
        self._mode = False

    def read_simulation_state(self):
        return type("S", (), {"observed": True, "simulation_mode": self._mode})()

    def set_simulation_mode(self, on: bool):
        self._mode = on
        self.modes.append(on)
        return type("M", (), {"observed": True})()

    def step(self, action="forward", times=1):
        self.steps.append((action, times))
        return type("R", (), {"observed": True})()

    def read_trace(self, limit=200, device=""):
        return type("T", (), {"observed": True, "hops": self.hops})()


class FakeProbe:
    def __init__(self, values: dict[int, object]) -> None:
        self.calls: list[list[int]] = []
        self._values = values

    def discover_frame_observers(self, indices, *, timeout=10.0):
        self.calls.append(list(indices))
        frames = []
        for index in indices:
            value = self._values[index]
            frames.append(FrameInstanceDiscovery(
                index=index,
                in_bounds=True,
                frame_found=True,
                observed_device=f"{TRUNK_CALIBRATION_PREFIX}tok_RX",
                observed_in_port=f"FastEthernet0/{index - 10}",
                observed_sim_time=10,
                observed_traffic_type=7,
                children=(FrameChildDiscovery(
                    getter="getInFrame",
                    invoked=True,
                    returned_null=False,
                    type_name="object",
                    members=("vlanId", "tpid", "cfi", "userPriority"),
                    tag=(FrameTagField(
                        name="vlanId",
                        observed=True,
                        type_name="number",
                        numeric_value=value,
                    ),),
                ),),
            ))
        return FrameObserverDiscovery(
            observed=True,
            simulation_mode=True,
            frame_count=50,
            frames=tuple(frames),
        )


TX = f"{TRUNK_CALIBRATION_PREFIX}tok_TX"
RX = f"{TRUNK_CALIBRATION_PREFIX}tok_RX"
PC0 = f"{TRUNK_CALIBRATION_PREFIX}tok_PC0"
PC1 = f"{TRUNK_CALIBRATION_PREFIX}tok_PC1"
GOOD_HOPS = [
    Hop(11, "FastEthernet0/1", TX),
    Hop(12, "FastEthernet0/2", TX),
]


def run_pass(
    *,
    overrides: dict[str, dict[str, object]] | None = None,
    values: dict[int, object] | None = None,
    hops: list[Hop] | None = None,
    empty: bool = True,
    armed: bool = True,
):
    physical = FakePhysical(empty=empty)
    configuration = FakeConfiguration(overrides)
    endpoints = FakeEndpoints(armed)
    simulation = FakeSimulation(GOOD_HOPS if hops is None else hops)
    probe = FakeProbe(values or {11: CONTROL_VLAN_IDS[0], 12: CONTROL_VLAN_IDS[1]})
    outcome = TrunkFrameVlanCalibrationQualifier(
        physical,
        configuration,
        endpoints,
        simulation,
        probe,
        name_token="tok",
    ).qualify("3560-24PS", "PC-PT")
    return outcome, physical, configuration, endpoints, simulation, probe


def test_two_exact_non_native_trunk_ingress_controls_qualify_strongly():
    outcome, physical, configuration, endpoints, simulation, probe = run_pass()

    assert outcome.errors == ()
    assert outcome.semantics == "STRONGLY_SUPPORTED_BY_MULTIVLAN_CONTROL"
    assert [item.expected_vlan for item in outcome.controls] == list(CONTROL_VLAN_IDS)
    assert [item.match for item in outcome.controls] == ["YES", "YES"]
    assert [item.native_vlan for item in outcome.controls] == [1, 1]
    assert configuration.reads == [
        (RX, "FastEthernet0/1"),
        (RX, "FastEthernet0/2"),
    ]
    assert endpoints.armed == [PC0, PC1]
    assert probe.calls == [[11, 12]]
    assert simulation.steps[0] == ("reset", 1)
    assert simulation.modes == [True, False]
    assert len(physical.links) == 4
    assert outcome.owned_links == (
        "trunkcal/access-link/0",
        "trunkcal/access-link/1",
        "trunkcal/trunk-link/0",
        "trunkcal/trunk-link/1",
    )


def test_a_native_target_vlan_cannot_be_a_control():
    outcome, *_ = run_pass(overrides={
        "FastEthernet0/1": {"native_vlan": CONTROL_VLAN_IDS[0]},
    })

    assert outcome.controls[0].expected_vlan is None
    assert outcome.controls[0].match == "UNOBSERVABLE"
    assert outcome.controls[1].match == "YES"
    assert outcome.semantics == "SUPPORTED_BY_CONTROL"


def test_an_allowed_superset_does_not_prove_a_single_allowed_vlan():
    outcome, *_ = run_pass(overrides={
        "FastEthernet0/1": {"allowed_vlans": (CONTROL_VLAN_IDS[0], 999)},
    })

    assert outcome.controls[0].expected_vlan is None
    assert "exactly one allowed VLAN" in outcome.controls[0].failure_reason


def test_active_and_forwarding_are_independent_required_observations():
    outcome, *_ = run_pass(overrides={
        "FastEthernet0/1": {"active_vlans": None},
        "FastEthernet0/2": {"forwarding_vlans": ()},
    })

    assert [item.match for item in outcome.controls] == [
        "UNOBSERVABLE",
        "UNOBSERVABLE",
    ]
    assert outcome.semantics == "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"


def test_a_tagged_contradiction_is_never_averaged_away():
    outcome, *_ = run_pass(values={
        11: CONTROL_VLAN_IDS[0],
        12: CONTROL_VLAN_IDS[0],
    })

    assert outcome.controls[1].match == "NO"
    assert outcome.semantics == "CONTRADICTED_BY_CONTROL"


def test_a_frame_without_the_governed_dhcp_trigger_never_matches():
    outcome, *_ = run_pass(armed=False)

    assert [item.endpoint_armed for item in outcome.controls] == [False, False]
    assert [item.match for item in outcome.controls] == [
        "UNOBSERVABLE",
        "UNOBSERVABLE",
    ]


def test_physical_arrival_on_a_qualified_trunk_is_not_target_vlan_admission():
    outcome, *_ = run_pass(values={11: None, 12: CONTROL_VLAN_IDS[1]})

    first = outcome.controls[0]
    assert first.expected_vlan == CONTROL_VLAN_IDS[0]
    assert first.identity_reconfirmed is True
    assert first.frame_entered_policy_qualified_trunk is True
    assert first.match == "UNOBSERVABLE"
    assert first.frame_admitted_for_target_vlan is False


def test_the_frame_must_enter_the_exact_read_back_trunk_from_the_source_switch():
    outcome, *_ = run_pass(hops=[
        Hop(11, "FastEthernet0/1", "SOMEONE-ELSE"),
        GOOD_HOPS[1],
    ])

    assert outcome.controls[0].frame_index is None
    assert outcome.controls[0].match == "UNOBSERVABLE"
    assert outcome.controls[1].match == "YES"


def test_cleanup_is_owned_reversed_and_the_original_mode_is_verified():
    outcome, physical, *_ = run_pass()

    assert physical.created == [TX, RX, PC0, PC1]
    assert physical.removed == list(reversed(physical.created))
    assert outcome.removed == tuple(physical.removed)
    assert outcome.workspace_restored is True
    assert outcome.realtime_restored is True


def test_a_nonempty_workspace_is_refused_before_any_mutation():
    outcome, physical, configuration, endpoints, simulation, probe = run_pass(
        empty=False,
    )

    assert physical.created == []
    assert configuration.actions == []
    assert endpoints.armed == []
    assert simulation.steps == []
    assert probe.calls == []
    assert "refuses to mutate" in outcome.errors[0]
