"""One address, one claimant; one earlier activation foundation.

The CP-SCALE Floor-1 live run reported 21 x 7960 contradicting the plan on
`Vlan1`. The number came from a single mistaken premise -- that a phone is an
endpoint E5 addresses -- and that premise fails on measured Packet Tracer
behaviour in two independent ways.

Measured on build 9.0.1.0858. A 7960 enumerates exactly `PC`, `Switch` and
`Vlan1`. Once its access port signals a voice VLAN, the phone itself brings up
`Vlan<voice>` -- powered, up, protocol up -- and takes `Vlan1` down. So `Vlan1`
is the one interface guaranteed to hold no address, and `Vlan<voice>` does not
exist yet when E5 is preflighted against the live inventory. Neither is an
interface E5 could honestly name.

What the historical positive lifecycle also supplied was a device-level DHCP
activation before E7.  E5 now retains that typed event through an interface
that exists at preflight, and verifies only the resulting voice-SVI client
state. E7 still owns the address claim and verifies it two ways -- what the
call control says the phone registered from, and what the phone reports on the
SVI it created.
"""

from __future__ import annotations

from copy import deepcopy

from src.packet_tracer_mcp.application.use_cases.apply_voice import (
    VoiceApplicator,
    _addressing_claim,
)
from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.application.use_cases.compile_voice import (
    compile_enterprise_voice,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigureAccessPort,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    RuntimePhoneRegistration,
)

from test_enterprise_configuration import _fixture as _e5_fixture
from test_enterprise_voice import _fixture as _e7_fixture
from test_voice_runtime import FakeVoiceRuntime, _profile


def _e5_plan():
    enterprise, topology, policy = _e5_fixture()
    result = compile_enterprise_configuration(enterprise, topology, policy)
    assert result.is_valid and result.plan is not None, [
        item.message for item in result.issues
    ]
    return result.plan


def _addressing_actions(plan, device_id: str):
    return [
        item for item in plan.actions
        if item.action_type in {
            ConfigurationActionType.SET_ENDPOINT_DHCP,
            ConfigurationActionType.SET_ENDPOINT_STATIC,
        }
        and item.device_id == device_id
    ]


def test_configuration_does_not_address_a_phone_on_a_voice_vlan():
    """Not an omission: there is no interface here E5 could name honestly."""
    plan = _e5_plan()

    assert _addressing_actions(plan, "phone-1") == []
    assert _addressing_actions(plan, "pc-1")


def test_the_phone_still_gets_its_whole_network_from_configuration():
    """What is withdrawn is the claim, not the VLAN, the port or the pool.

    Withdrawing the pool as well would quietly delete a designed router service
    because its only client stopped being one this plan configures -- and that
    pool is exactly what the phone leases from.
    """
    enterprise, topology, policy = _e5_fixture()
    phone = next(item for item in topology.devices if item.id == "phone-1")
    phone.metadata["addressing_preference"] = "dhcp"
    for site in enterprise.sites:
        for segment in site.segments:
            if segment.name == "hq-voice":
                segment.dhcp = True
    plan = compile_enterprise_configuration(enterprise, topology, policy).plan

    access = next(
        item for item in plan.actions
        if isinstance(item, ConfigureAccessPort)
        and "phone-1" in item.endpoint_ids
    )
    pools = [
        item for item in plan.actions
        if item.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
    ]

    assert access.voice_vlan_id == 20
    assert access.data_vlan_id == 10
    activation = _addressing_actions(plan, "phone-1")
    assert len(activation) == 1
    assert activation[0].claims_address_acquisition is False
    assert activation[0].interface == "Vlan1"
    assert activation[0].verification_interface == "Vlan20"
    assert any(item.segment_id == "hq-voice" for item in pools)


def test_configuration_claims_no_addressing_it_cannot_read_back():
    plan = _e5_plan()

    claimed = [
        item for item in plan.verification_expectations
        if item.kind is VerificationKind.ENDPOINT_ADDRESSING
    ]

    assert {item.device_name for item in claimed} == {
        "__MCP_E5_PC", "__MCP_E5_STATIC_PC",
    }


def test_a_phone_with_no_voice_vlan_is_still_addressed_on_vlan1():
    """`Vlan1` stays up when nothing displaces it, so E5 can still own it."""
    enterprise, topology, policy = _e5_fixture()
    # Unpair the phone: with no paired PC and no data segment behind it, the
    # access port carries the phone's VLAN untagged and signals no voice VLAN.
    phone = next(item for item in topology.devices if item.id == "phone-1")
    pc = next(item for item in topology.devices if item.id == "pc-1")
    phone.metadata["pair_id"] = ""
    pc.metadata["pair_id"] = ""
    topology.links = [
        item for item in topology.links if item.id != "phone-pc"
    ]
    for site in enterprise.sites:
        site.segments = [item for item in site.segments if item.name != "hq-data"]

    result = compile_enterprise_configuration(enterprise, topology, policy)
    plan = result.plan
    access = next(
        item for item in plan.actions
        if isinstance(item, ConfigureAccessPort) and "phone-1" in item.endpoint_ids
    )
    addressing = _addressing_actions(plan, "phone-1")

    assert access.voice_vlan_id is None
    assert [item.interface for item in addressing] == ["Vlan1"]


def _voice_plan(*, e5_addresses_the_phone: bool):
    enterprise, topology, configuration, intent, capabilities = _e7_fixture()
    if not e5_addresses_the_phone:
        configuration.actions = [
            item for item in configuration.actions
            if item.action_type is not ConfigurationActionType.SET_ENDPOINT_DHCP
        ]
    result = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )
    assert result.is_valid and result.plan is not None, [
        item.message for item in result.issues
    ]
    return result.plan


def test_voice_resolves_the_phone_segment_from_what_its_port_signals():
    """With no E5 addressing action there is still exactly one voice segment."""
    plan = _voice_plan(e5_addresses_the_phone=False)

    assignment = plan.phone_assignments[0]

    assert assignment.addressing_configuration_action_id == ""
    assert assignment.voice_vlan_id == 20
    assert assignment.voice_segment_id == "hq-voice"
    assert assignment.addressing_interface == "Vlan20"
    # The range it can lease from is the pool that serves that segment.
    assert assignment.voice_network == "198.18.170.0"
    assert assignment.voice_prefix == 24


def test_voice_does_not_require_the_acquisition_it_is_about_to_produce():
    """The cycle, stated as a test: E7 used to wait for its own output."""
    unaddressed = _voice_plan(e5_addresses_the_phone=False)
    addressed = _voice_plan(e5_addresses_the_phone=True)

    def addressing_foundations(plan):
        return [
            item for item in plan.foundational_requirements
            if item.kind == "phone_addressing"
        ]

    assert addressing_foundations(unaddressed) == []
    assert addressing_foundations(addressed)
    # The voice VLAN really is a precondition, and stays one either way.
    assert [
        item for item in unaddressed.foundational_requirements
        if item.kind == "voice_vlan"
    ]


def test_voice_applies_when_only_the_voice_vlan_foundation_is_verified():
    """Before the fix this returned FOUNDATIONAL_CONFIGURATION_MISSING."""
    plan = _voice_plan(e5_addresses_the_phone=False)
    runtime = FakeVoiceRuntime()

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses={
            item.source_id: ActionExecutionStatus.VERIFIED
            for item in plan.foundational_requirements
        },
        capabilities=_profile(),
        runtime_context=ConfigurationRuntimeContext(
            backend="fake", backend_version="9.0.1.0858",
        ),
    )

    assert (
        result.failure_code
        is not ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    )
    assert runtime.applied
    assert result.application_status is ActionExecutionStatus.APPLIED


def test_the_registration_expectation_names_the_phone_and_its_svi():
    plan = _voice_plan(e5_addresses_the_phone=False)

    assignment = plan.phone_assignments[0]
    expectation = next(
        item for item in plan.verification_expectations
        if item.phone_id == assignment.phone_id
        and item.kind.value == "phone_registration"
    )

    assert expectation.endpoint_device_name == assignment.physical_device_name
    assert expectation.endpoint_interface == "Vlan20"


def _observed(control: str = "", endpoint: str = ""):
    return RuntimePhoneRegistration(
        expectation_id="e", phone_id="phone-1", extension="3101",
        status=ActionExecutionStatus.VERIFIED,
        call_control_ipv4=control, endpoint_ipv4=endpoint,
        endpoint_interface="Vlan20",
    )


def _assignment(*, e5_addressed: bool = False):
    assignment = deepcopy(
        _voice_plan(e5_addresses_the_phone=False).phone_assignments[0]
    )
    if e5_addressed:
        assignment.addressing_configuration_action_id = "cfg/dhcp/phone-1"
    return assignment


def test_two_agreeing_reads_of_one_address_are_the_evidence():
    status, message = _addressing_claim(
        _assignment(), _observed("198.18.170.5", "198.18.170.5"),
    )

    assert status is ActionExecutionStatus.VERIFIED
    assert message == ""


def test_two_reads_that_disagree_are_a_defect_not_a_preference():
    status, message = _addressing_claim(
        _assignment(), _observed("198.18.170.5", "198.18.170.9"),
    )

    assert status is ActionExecutionStatus.FAILED
    assert "cannot hold two addresses" in message


def test_an_address_outside_the_voice_segment_fails():
    status, _ = _addressing_claim(
        _assignment(), _observed("198.18.150.5", "198.18.150.5"),
    )

    assert status is ActionExecutionStatus.FAILED


def test_a_single_silent_channel_is_partial_not_verified():
    status, message = _addressing_claim(
        _assignment(), _observed("198.18.170.5", ""),
    )

    assert status is ActionExecutionStatus.PARTIAL
    assert "one channel only" in message


def test_no_address_anywhere_is_unobservable_not_failed():
    """Fail-closed: nothing was seen, so nothing is claimed either way."""
    status, _ = _addressing_claim(_assignment(), _observed())

    assert status is ActionExecutionStatus.UNOBSERVABLE


def test_voice_says_nothing_about_a_phone_configuration_addressed_itself():
    status, message = _addressing_claim(
        _assignment(e5_addressed=True), _observed("198.18.170.5", "198.18.170.5"),
    )

    assert status is ActionExecutionStatus.UNKNOWN
    assert message == ""
