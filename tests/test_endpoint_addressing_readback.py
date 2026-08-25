"""E5 endpoint addressing is read back on the interface the plan configured.

The CP-SCALE Floor-1 live run contradicted exactly 43 endpoint expectations and
verified exactly 25. The split was not random and it was not PoE: every endpoint
whose addressing action targeted `FastEthernet0` verified (23 PC-PT, 2
Printer-PT) and every endpoint whose action targeted anything else contradicted
(21 x 7960 on `Vlan1`, 3 x AccessPoint-PT on `Port 0`, 19 wireless IoT devices
on the empty string).

That is the signature of a read-back that never learned which interface was
addressed: it walked `getPortAt(i)` and accepted the first port exposing
`getIpAddress`. On a single-port endpoint the addressed port and the first port
are the same object, so the defect stayed invisible for years of PC-only
topologies. On a phone -- `Switch`, `PC`, plus a logical `Vlan1` -- they are not,
and the runtime reported a contradiction about a port nobody configured.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationIssueCode,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.segments import (
    NetworkSegment,
    SegmentRole,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)

from test_enterprise_configuration import _allocation, _fixture


def _plan():
    enterprise, topology, policy = _fixture()
    result = compile_enterprise_configuration(enterprise, topology, policy)
    assert result.is_valid and result.plan is not None, [
        item.message for item in result.issues
    ]
    return result.plan


def _addressing(plan):
    actions = {
        item.id: item
        for item in plan.actions
        if item.action_type in {
            ConfigurationActionType.SET_ENDPOINT_DHCP,
            ConfigurationActionType.SET_ENDPOINT_STATIC,
        }
    }
    return [
        (item, actions[item.action_id])
        for item in plan.verification_expectations
        if item.kind is VerificationKind.ENDPOINT_ADDRESSING
    ]


def test_every_endpoint_expectation_carries_the_interface_it_addressed():
    """An expectation that omits the interface cannot be read back honestly."""
    pairs = _addressing(_plan())

    assert pairs
    for expectation, action in pairs:
        assert expectation.expected.get("interface") == action.interface, (
            f"{expectation.id} lost the {action.interface!r} it configured"
        )


def test_no_expectation_is_raised_against_a_phone_at_all():
    """The read-back fix was necessary but not sufficient for the 7960.

    Reading the addressed interface stopped the runtime inventing observations
    about ports nobody configured. It could not make `Vlan1` hold an address:
    measured on build 9.0.1.0858, a phone whose access port signals a voice VLAN
    brings up `Vlan<voice>` and takes `Vlan1` down. E5 now claims nothing here,
    so there is no expectation to read back at all.
    """
    pairs = _addressing(_plan())

    assert pairs
    assert "__MCP_E5_PHONE" not in {
        expectation.device_name for expectation, _ in pairs
    }


def _readback_payloads(expectation) -> list[str]:
    payloads: list[str] = []
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda payload, _timeout: payloads.append(payload) or (
            '{"found":true,"port_found":true,"configuration_channel":true,'
            '"ipv4":"198.18.151.20","netmask":"255.255.255.0",'
            '"gateway":null,"dns":null}'
        ),
        endpoint_timeout_seconds=0.2,
        convergence_interval_seconds=0.05,
    )
    runtime.verify([expectation])
    return payloads


def test_endpoint_readback_is_parameterised_by_the_addressed_interface():
    """One endpoint, one named interface, and the read asks about that one.

    Positional selection cannot produce this: it emits the same port walk for
    every endpoint regardless of what was configured. Only a read-back that
    carries the addressed interface can name it in the payload it sends.
    """
    pairs = _addressing(_plan())
    pc = next(item for item, _ in pairs if item.device_name == "__MCP_E5_PC")
    static_pc = next(
        item for item, _ in pairs if item.device_name == "__MCP_E5_STATIC_PC"
    )

    pc_payloads = _readback_payloads(pc)
    static_payloads = _readback_payloads(static_pc)

    assert pc_payloads and static_payloads
    for payloads, name in (
        (pc_payloads, "__MCP_E5_PC"), (static_payloads, "__MCP_E5_STATIC_PC"),
    ):
        assert all("FastEthernet0" in payload for payload in payloads)
        assert all(name in payload for payload in payloads)
    assert not any("__MCP_E5_STATIC_PC" in payload for payload in pc_payloads)


def test_an_unexposed_addressed_interface_is_unobservable_not_contradicted():
    """Not having read the right port is not evidence that the plan is wrong."""
    endpoint = next(
        item for item, _ in _addressing(_plan())
        if item.device_name == "__MCP_E5_PC"
    )
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda _payload, _timeout: (
            '{"found":true,"port_found":false,"configuration_channel":false,'
            '"ipv4":"","netmask":"","gateway":null,"dns":null}'
        ),
        endpoint_timeout_seconds=0.2,
        convergence_interval_seconds=0.05,
    )

    result = runtime.verify([endpoint])[0]

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert not result.fresh_evidence
    assert set(result.fields.values()) == {FieldVerificationStatus.UNOBSERVABLE}


def _fixture_with_wireless_sensor():
    """The same E5 fixture plus one addressable-by-intent wireless IoT device.

    Its CCTV segment and allocation exist, so nothing else can be blamed: the
    only thing missing is a network port to put the address on.
    """
    enterprise, topology, policy = _fixture()
    enterprise.sites[0].segments.append(NetworkSegment(
        name="hq-cctv",
        role=SegmentRole.CCTV,
        site="hq",
        host_requirement=1,
        dhcp=True,
        vlan_id=30,
    ))
    enterprise.addressing.allocations.append(
        _allocation("hq-cctv", "198.18.152.0", "198.18.152.1"),
    )
    topology.devices.append(DevicePlan(
        id="sensor-1",
        name="__MCP_E5_SENSOR",
        model="Motion Detector",
        category="iot",
        enterprise_role="motion_detector",
        site_id="hq",
        wireless=True,
        metadata={"addressing_preference": "dhcp"},
    ))
    return enterprise, topology, policy


def test_a_wireless_endpoint_with_no_interface_is_not_claimed_as_addressed():
    """The 19 wireless IoT contradictions, at their root.

    `Motion Detector`, `Smoke Detector` and `Webcam` expose an empty port
    inventory, so the compiler emitted `interface=""`; the applicator's target
    check skips empty interfaces, so a `critical=True` action reached a live
    device aimed at nothing and was then read back as a contradiction.

    Nothing about that device was ever claimed: CP-SCALE carries these devices
    with `wireless_association=unqualified`, and addressing rides on
    association. So the topology stays valid and its VLAN stays structural --
    what stops is the pretence that an address was configured.
    """
    enterprise, topology, policy = _fixture_with_wireless_sensor()

    result = compile_enterprise_configuration(enterprise, topology, policy)

    assert result.is_valid, [item.message for item in result.issues]
    assert any(
        item.subject == "sensor-1"
        and item.code is ConfigurationIssueCode.ENDPOINT_INTERFACE_MISSING
        for item in result.issues
    )
    assert result.plan is not None
    assert not any(
        item.action_type in {
            ConfigurationActionType.SET_ENDPOINT_DHCP,
            ConfigurationActionType.SET_ENDPOINT_STATIC,
        }
        and item.device_id == "sensor-1"
        for item in result.plan.actions
    )


def test_a_wired_endpoint_with_no_interface_fails_closed():
    """Something holding a cable should own an interface; if not, stop."""
    enterprise, topology, policy = _fixture_with_wireless_sensor()
    sensor = next(item for item in topology.devices if item.id == "sensor-1")
    sensor.wireless = False

    result = compile_enterprise_configuration(enterprise, topology, policy)

    assert not result.is_valid
    assert any(
        item.subject == "sensor-1"
        and item.code is ConfigurationIssueCode.ENDPOINT_INTERFACE_MISSING
        for item in result.issues
    )


def test_no_endpoint_addressing_action_is_ever_emitted_without_an_interface():
    """The invariant, stated once: an addressing action names its interface."""
    plan = _plan()

    for _expectation, action in _addressing(plan):
        assert action.interface, f"{action.id} addressed no interface"
