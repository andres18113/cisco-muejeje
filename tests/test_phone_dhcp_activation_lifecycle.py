"""The phone DHCP trigger is an E5 -> E7 lifecycle foundation.

The activation and the eventual address are deliberately different claims.
Packet Tracer's measured endpoint helper accepts a port that already exists and
then calls ``device.setDhcpFlag(true)``.  A 7960's voice SVI is created later by
the voice-VLAN lifecycle, so E5 must trigger through ``Vlan1`` while reading the
client state back on ``Vlan<voice>``.  E7 still owns the eventual address and
registration.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.application.use_cases.compile_voice import (
    compile_enterprise_voice,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
    VerificationExpectation,
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.configuration_runtime import (
    PacketTracerConfigurationRuntime,
)

from test_enterprise_configuration import _fixture as _e5_fixture
from test_enterprise_voice import _fixture as _e7_fixture
from test_positive_voice_slice import (
    _CallControl,
    _Configuration,
    _Endpoints,
    _run,
)


def _compiled_configuration():
    enterprise, topology, policy = _e5_fixture()
    phone = next(item for item in topology.devices if item.id == "phone-1")
    phone.metadata["addressing_preference"] = "dhcp"
    voice = next(
        segment for site in enterprise.sites for segment in site.segments
        if segment.name == "hq-voice"
    )
    voice.dhcp = True
    result = compile_enterprise_configuration(enterprise, topology, policy)
    assert result.is_valid and result.plan is not None, [
        item.message for item in result.issues
    ]
    return result.plan


def test_voice_phone_keeps_a_typed_e5_dhcp_activation_without_claiming_ip():
    plan = _compiled_configuration()
    actions = [
        item for item in plan.actions
        if item.action_type is ConfigurationActionType.SET_ENDPOINT_DHCP
        and item.device_id == "phone-1"
    ]

    assert len(actions) == 1
    activation = actions[0]
    assert activation.interface == "Vlan1"
    assert getattr(activation, "verification_interface", "") == "Vlan20"
    assert str(getattr(activation, "verification_mode", "")) in {
        "client_enabled", "EndpointDhcpVerificationMode.CLIENT_ENABLED",
    }

    expectation = next(
        item for item in plan.verification_expectations
        if item.action_id == activation.id
    )
    assert expectation.expected == {
        "mode": "dhcp_client_enabled",
        "interface": "Vlan20",
    }
    access = next(
        item for item in plan.actions
        if item.action_type is ConfigurationActionType.CONFIGURE_ACCESS_PORT
        and "phone-1" in item.endpoint_ids
    )
    pool = next(
        item for item in plan.actions
        if item.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
        and item.segment_id == "hq-voice"
    )
    assert set(activation.depends_on) == {access.id, pool.id}


def test_e7_waits_for_activation_but_still_owns_address_acquisition():
    enterprise, topology, configuration, intent, capabilities = _e7_fixture(1)
    for action in configuration.actions:
        if action.action_type is ConfigurationActionType.SET_ENDPOINT_DHCP:
            # Keep this regression fail-first before the typed fields exist.
            # The compiler must inspect the semantic value, not merely the
            # presence of a SetEndpointDhcp instance.
            object.__setattr__(action, "verification_mode", "client_enabled")
            object.__setattr__(action, "verification_interface", "Vlan20")
    result = compile_enterprise_voice(
        intent, enterprise, topology, configuration, capabilities=capabilities,
    )
    assert result.is_valid and result.plan is not None, [
        item.message for item in result.issues
    ]

    assignment = result.plan.phone_assignments[0]
    activation = [
        item for item in result.plan.foundational_requirements
        if item.kind == "phone_dhcp_activation"
    ]

    assert len(activation) == 1
    assert getattr(assignment, "activation_configuration_action_id", "") == (
        activation[0].source_id
    )
    assert assignment.addressing_configuration_action_id == ""
    assert assignment.addressing_interface == "Vlan20"
    assert not [
        item for item in result.plan.foundational_requirements
        if item.kind == "phone_addressing"
    ]


def test_disposable_positive_path_activates_via_vlan1_before_voice():
    timeline: list[str] = []

    class Configuration(_Configuration):
        def apply_actions(self, actions):
            timeline.append("configuration")
            return super().apply_actions(actions)

    class CallControl(_CallControl):
        def apply_actions(self, actions):
            timeline.append("voice")
            return super().apply_actions(actions)

    endpoints = _Endpoints(timeline=timeline)
    _run(
        configuration=Configuration(), call_control=CallControl(),
        endpoints=endpoints,
    )

    first_arm = timeline.index("arm:MCP-VOICEAB-test01_P1")
    assert timeline.index("configuration") < first_arm < timeline.index("voice")
    assert endpoints.armed_interfaces == ["Vlan1", "Vlan1"]


def test_activation_readback_verifies_only_the_voice_svi_client_flag():
    payloads: list[str] = []
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=lambda _payload: True,
        send_and_wait=lambda payload, _timeout: payloads.append(payload) or (
            '{"found":true,"port_found":true,"configuration_channel":true,'
            '"dhcp_channel":true,"dhcp_enabled":true}'
        ),
        endpoint_timeout_seconds=0.2,
        convergence_interval_seconds=0.05,
    )
    expectation = VerificationExpectation(
        id="verify/phone/dhcp-activation",
        action_id="cfg/phone/dhcp-activation",
        kind=VerificationKind.ENDPOINT_ADDRESSING,
        device_id="phone-1",
        device_name="PHONE-1",
        expected={"mode": "dhcp_client_enabled", "interface": "Vlan20"},
    )

    result = runtime.verify([expectation])[0]

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.evidence_method == "structured_endpoint_dhcp_client_getter"
    assert payloads and all("isDhcpClientOn" in item for item in payloads)
    assert all("setDhcpClientFlag" not in item for item in payloads)


def test_activation_acceptance_comes_from_configure_pc_ip_not_enqueueing():
    queued: list[str] = []
    executed: list[str] = []
    runtime = PacketTracerConfigurationRuntime(
        lambda payload: queued.append(payload) or True,
        lambda payload, _timeout: executed.append(payload) or '{"accepted":true}',
    )

    assert runtime.configure_endpoint_dhcp("PHONE-1", "Vlan1") is True
    assert queued == []
    assert len(executed) == 1
    assert 'configurePcIp("PHONE-1",true,null,null,null,null,"Vlan1")' in executed[0]
    assert "reportResult" in executed[0]
