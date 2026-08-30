"""Contracts for the positive disposable Voice slice (the A side of the A/B)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (
    ABSENT,
    ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN,
    ACQUISITION_NOT_STARTED_PRE_RETRIGGER_ADDRESS_BASELINE_UNPROVEN,
    ACQUISITION_NOT_STARTED_SVI_DHCP_TRANSITION_UNPROVEN,
    ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET,
    APPLICATION,
    APPLIED,
    BLOCKING,
    CONTRADICTED,
    DATA_VLAN_ID,
    EXPERIMENT_PAIRED_ACCESS_VLAN,
    EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED,
    EXPERIMENT_PHONE_DHCP_LIFECYCLE,
    EXPERIMENT_PHONE_SVI_DHCP_RETRIGGER,
    EXPERIMENT_UNIFORM_BASELINE,
    EXTENSIONS,
    FORWARDING,
    GATE_TIMEOUT,
    NO,
    NOT_AVAILABLE,
    NOT_REGISTERED,
    ROUTER_UPLINK_INTERFACE,
    ROUTER_VOICE_SUBINTERFACE,
    SWITCH_UPLINK_INTERFACE,
    OBSERVATION,
    PHONE_ADDRESSING_INTERFACE,
    PHONE_DHCP_LIFECYCLE_MILESTONES,
    PHONE_LINK_PORT,
    POSITIVE_VOICE_PREFIX,
    REGISTERED,
    UNOBSERVABLE,
    VERIFIED,
    VOICE_VLAN_ID,
    YES,
    LifecycleMilestone,
    PhoneDhcpLifecycleEvidence,
    PhonePreRetriggerEndpointState,
    PhoneSviDhcpTransitionEvidence,
    PositiveVoicePhoneOutcome,
    PositiveVoiceSliceQualifier,
    PositiveVoiceSliceResult,
    StpForwardingGate,
    StpReadObservation,
    await_stp_forwarding,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeActionMutation,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalMutationResult,
    PhysicalObjectKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    VoiceVerificationExpectation,
    VoiceVerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.services.configuration_compiler import (
    _phone_addressing_interface,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    DhcpPoolReadbackObservation,
)


def _device_result(applied: bool = True, message: str = ""):
    """What a backend really answers for one typed ensure operation."""
    return PhysicalMutationResult(
        target_id="voiceab", target_kind=PhysicalObjectKind.DEVICE,
        applied=applied, message=message,
    )


def _link_result(applied: bool = True, message: str = ""):
    return PhysicalMutationResult(
        target_id="voiceab", target_kind=PhysicalObjectKind.LINK,
        applied=applied, message=message,
    )


def _mutation(action_id: str = "", applied: bool = True, message: str = ""):
    return RuntimeActionMutation(
        action_id=action_id, applied=applied, message=message,
    )


@dataclass
class _LegacySuccess:
    """A result that still carries the OLD flag while the real one says no.

    Nothing in production returns this shape.  It exists so that a fail-open
    `.success` default cannot come back unnoticed: a qualifier that consults it
    would read this object as a mutation that happened.
    """

    applied: bool = False
    success: bool = True
    message: str = "the backend refused"
    action_id: str = ""


@dataclass
class _Mode:
    simulation_mode: bool = False
    observed: bool = True


@dataclass
class _Port:
    data_vlan_id: int | None
    voice_vlan_id: int | None


@dataclass
class _Binding:
    ip_address: str


@dataclass
class _StpRow:
    interface: str
    role: str = "Desg"
    state: str = "FWD"
    #: The Type column, which is where an edge port announces itself.
    link_type: str = "P2p"


@dataclass
class _StpInstance:
    vlan_id: int
    interfaces: tuple


@dataclass
class _Registration:
    status: str = "ActionExecutionStatus.VERIFIED"
    direct_readback: str = "FieldVerificationStatus.VERIFIED"
    endpoint_ipv4: str = "10.93.0.10"
    endpoint_dhcp_enabled: bool = True
    # The three facts the production surface keeps apart behind one empty
    # string: did the SVI exist, could it be asked, and what did the phone
    # itself report beside it.
    endpoint_interface_present: bool = True
    endpoint_address_channel: bool = True
    device_ipv4: str = ""


class _Physical:
    def __init__(self, baseline, fail_on: str = ""):
        self.baseline = baseline
        self.fail_on = fail_on
        self.created: list[str] = []
        self.removed: list[str] = []
        self.links: list[str] = []
        self.final = baseline

    def observe_workspace(self):
        return self.final if self.removed else self.baseline

    def ensure_device(self, device):
        self.created.append(device.name)
        if self.fail_on and self.fail_on in device.name:
            return _device_result(applied=False, message="refused")
        return _device_result()

    def observe_device(self, device):
        return _device_result()

    def remove_device(self, device):
        self.removed.append(device.name)
        return _device_result()

    def ensure_link(self, link):
        self.links.append(f"{link.device_a}:{link.port_a}")
        return _link_result()


class _Configuration:
    def __init__(
        self, port=None, stp=None, bindings=None, mutations=None,
        stp_sequence=None, timeline=None,
    ):
        self.applied: list = []
        self.port = port if port is not None else _Port(DATA_VLAN_ID, VOICE_VLAN_ID)
        self.stp = stp
        #: Scripted answers for consecutive `read_spanning_tree` calls.  The
        #: FWD gate polls the SAME qualified read the before/after snapshots
        #: use, so a gated test needs one script covering all of them; after
        #: exhaustion the last answer repeats, which is how a port that stays
        #: LIS forever is expressed.
        self.stp_sequence = list(stp_sequence) if stp_sequence is not None else None
        self.bindings = bindings if bindings is not None else [_Binding("10.93.0.10")]
        self.mutations = mutations
        #: Shared cross-fake event order, so ordering contracts -- the gate
        #: reads before the first arm, the arm before the window -- are proven
        #: from one record instead of inferred from separate lists.
        self.timeline = timeline
        #: Every access-port readback request, exactly as the qualifier asked
        #: it: (interface, expected access VLAN).  The paired A/B turns on the
        #: expectation each port is judged against, so the fake must retain it.
        self.access_reads: list[tuple[str, int]] = []

    def apply_actions(self, actions):
        self.applied.extend(actions)
        if self.mutations is not None:
            return [self.mutations(getattr(a, "id", "")) for a in actions]
        return [_mutation(action_id=getattr(a, "id", "")) for a in actions]

    def read_access_port(self, device_name, interface, expected_access_vlan):
        self.access_reads.append((interface, expected_access_vlan))
        # A dict maps each interface to its own readback, so one fake can hand
        # the two halves of the paired A/B different answers.
        if isinstance(self.port, dict):
            return self.port.get(interface)
        return self.port

    def read_spanning_tree(self, device_name):
        if self.timeline is not None:
            self.timeline.append("stp_read")
        if self.stp_sequence is not None:
            if len(self.stp_sequence) > 1:
                return self.stp_sequence.pop(0)
            return self.stp_sequence[0] if self.stp_sequence else None
        return self.stp

    def read_spanning_tree_observation(self, device_name):
        instances = self.read_spanning_tree(device_name)
        if instances is None:
            return StpReadObservation(
                failure_reason="scripted unreadable STP result",
                failure_dimensions=("QUERY_SESSION",),
            )
        return StpReadObservation(
            instances=instances,
            executed=True,
            fresh=True,
            complete=True,
            identity_provenance="confirmed_unique",
        )

    def read_dhcp_bindings(self, device_name):
        return self.bindings


_DEFAULT = object()


class _CallControl:
    def __init__(self, registration=_DEFAULT, mutations=None):
        self.applied: list = []
        # A sentinel, not None: passing None must mean "observed nothing", which
        # is the case this fake exists to reproduce.
        self.registration = _Registration() if registration is _DEFAULT else registration
        self.mutations = mutations
        self.expectations: list = []

    def apply_actions(self, actions):
        self.applied.extend(actions)
        if self.mutations is not None:
            return [self.mutations(getattr(a, "id", "")) for a in actions]
        return [_mutation(action_id=getattr(a, "id", "")) for a in actions]

    def observe_registrations(self, expectations):
        """Answer per phone the way the production runtime does.

        `PacketTracerEnterpriseVoiceRuntime` reads the phone off
        `endpoint_device_name` to interrogate that phone's own SVI.  This spy
        reads the same field, so an expectation that does not carry it cannot
        be answered here either -- which is the whole point: a private
        stand-in silently produced "no address" for every phone.
        """
        self.expectations.extend(expectations)
        if self.registration is None:
            return []
        return [self._for(item.endpoint_device_name) for item in expectations]

    def _for(self, endpoint_device_name: str):
        if not endpoint_device_name:
            raise AssertionError(
                "a registration expectation reached the runtime without the "
                "phone it is about"
            )
        return self.registration


class _Endpoints:
    def __init__(self, observation=None, observation_after_arm=None, timeline=None):
        self.armed: list[str] = []
        self.armed_interfaces: list[str] = []
        self.read_interfaces: list[str] = []
        #: What `read_endpoint_address` answers BEFORE any phone was armed, and
        #: what it answers afterwards.  Two values, because the pre-arm/post-arm
        #: pair is exactly the OFF-to-ON evidence the fresh-DHCP gate turns on.
        self.observation = observation
        self.observation_after_arm = observation_after_arm
        self.timeline = timeline

    def configure_endpoint_dhcp(self, device_name, interface):
        # The typed runtime answers with a bool, and that is what is judged.
        if self.timeline is not None:
            self.timeline.append(f"arm:{device_name}")
        self.armed.append(device_name)
        self.armed_interfaces.append(interface)
        return True

    def read_endpoint_address(self, device_name, interface):
        if self.timeline is not None:
            self.timeline.append(f"endpoint_read:{device_name}")
        self.read_interfaces.append(interface)
        if self.armed and self.observation_after_arm is not None:
            return self.observation_after_arm
        return self.observation


class _ModeRuntime:
    def __init__(self, state=None):
        self.state = state if state is not None else _Mode()
        self.set_calls: list[bool] = []

    def read_simulation_state(self):
        return self.state

    def set_simulation_mode(self, on):
        self.set_calls.append(bool(on))


def _empty_workspace():
    return PhysicalWorkspaceObservation(observed=True, devices=[], links=[])


def _busy_workspace():
    return PhysicalWorkspaceObservation(
        observed=True,
        devices=[
            PhysicalWorkspaceDeviceObservation(
                name="Router4", model="2811", backend_managed=False,
            )
        ],
        links=[],
    )


def _qualifier(
    physical, configuration, call_control, endpoints, mode,
    control_plane=None, edge_portfast=False, phone_access_vlans=None,
    **gate_kwargs,
):
    return PositiveVoiceSliceQualifier(
        physical, configuration, call_control, endpoints, mode, token="test01",
        control_plane=control_plane, edge_portfast=edge_portfast,
        phone_access_vlans=phone_access_vlans,
        **gate_kwargs,
    )


def _run(
    *, physical=None, configuration=None, call_control=None,
    endpoints=None, mode=None, baseline=None, control_plane=None,
    edge_portfast=False, phone_access_vlans=None, **gate_kwargs,
):
    baseline = baseline if baseline is not None else _empty_workspace()
    physical = physical if physical is not None else _Physical(baseline)
    configuration = configuration if configuration is not None else _Configuration()
    call_control = call_control if call_control is not None else _CallControl()
    endpoints = endpoints if endpoints is not None else _Endpoints()
    mode = mode if mode is not None else _ModeRuntime()
    qualifier = _qualifier(
        physical, configuration, call_control, endpoints, mode,
        control_plane, edge_portfast, phone_access_vlans, **gate_kwargs,
    )
    result = qualifier.qualify("2811", "3560-24PS", "7960")
    return (
        result, physical, configuration, call_control, endpoints, mode,
        control_plane,
    )


def test_a_workspace_that_is_not_empty_is_never_mutated():
    physical = _Physical(_busy_workspace())
    result, *_ = _run(physical=physical, baseline=_busy_workspace())

    assert physical.created == []
    assert physical.links == []
    assert result.outcome == UNOBSERVABLE
    assert any("refuses to mutate" in item for item in result.errors)


def test_the_positive_slice_applies_no_edge_stp_policy():
    result, _, configuration, call_control, *_ = _run()

    # PortFast is emitted by the control-plane stage.  A slice that quietly
    # added one would be engineering the success it is supposed to test.
    emitted = [
        type(action).__name__ for action in configuration.applied + call_control.applied
    ]
    assert not any("Stp" in name or "PortFast" in name for name in emitted)
    assert result.portfast == "NOT_APPLIED"


def test_a_successful_slice_needs_every_dimension_and_a_server_binding():
    result, *_ = _run()

    assert result.outcome == "SUCCESS"
    assert [item.voice_vlan_readback for item in result.phones] == [VERIFIED, VERIFIED]
    assert [item.dhcp_enabled for item in result.phones] == [YES, YES]
    assert all(item.ipv4_observed for item in result.phones)
    assert [item.registration for item in result.phones] == [REGISTERED, REGISTERED]
    assert result.voice_binding_count == 1
    assert result.voice_binding_ipv4s == ("10.93.0.10",)
    assert result.voice_bindings_observed == YES


def test_a_phone_address_without_a_server_binding_is_not_a_success():
    # The phone claiming a lease while the server shows none is a disagreement,
    # and averaging it into SUCCESS is how a half-observation gets promoted.
    result, *_ = _run(configuration=_Configuration(bindings=[]))

    assert result.voice_binding_count == 0
    assert result.outcome == "DIFFERENT_FAILURE"


def test_the_cp_scale_signature_is_reported_as_the_same_failure():
    registration = _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="0.0.0.0", endpoint_dhcp_enabled=True,
    )
    result, *_ = _run(
        configuration=_Configuration(bindings=[]),
        call_control=_CallControl(registration=registration),
    )

    assert [item.dhcp_enabled for item in result.phones] == [YES, YES]
    assert [item.addressed for item in result.phones] == [NO, NO]
    assert [item.registration for item in result.phones] == [
        NOT_REGISTERED, NOT_REGISTERED,
    ]
    assert result.outcome == "SAME_FAILURE"


def test_an_unread_binding_table_is_not_zero_bindings():
    class _NoBindings(_Configuration):
        def read_dhcp_bindings(self, device_name):
            raise RuntimeError("terminal unavailable")

    result, *_ = _run(configuration=_NoBindings())

    assert result.voice_binding_count is None
    assert result.voice_bindings_observed == UNOBSERVABLE
    # Unread is not zero, so it is neither a success nor a demonstrated failure.
    assert result.outcome == UNOBSERVABLE


def test_missing_registration_evidence_stays_unobservable():
    result, *_ = _run(call_control=_CallControl(registration=None))

    assert [item.registration for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]
    assert [item.dhcp_enabled for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]
    assert result.outcome == UNOBSERVABLE


def test_an_absent_voice_stp_row_is_never_reported_as_blocking():
    # This is the exact CP-SCALE representation: the VLAN was read, and it has
    # no row for the phone port.  ABSENT and BLOCKING are different facts.
    stp = [_StpInstance(vlan_id=VOICE_VLAN_ID, interfaces=())]
    result, *_ = _run(configuration=_Configuration(stp=stp))

    assert [item.stp_row_after for item in result.phones] == [ABSENT, ABSENT]
    assert result.stp_phone_row_after == ABSENT
    assert BLOCKING not in {item.stp_row_after for item in result.phones}


def test_an_unread_stp_table_is_unobservable_not_absent():
    result, *_ = _run(configuration=_Configuration(stp=None))

    assert [item.stp_row_after for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]


def test_a_forwarding_voice_row_is_classified_from_the_read_state():
    stp = [
        _StpInstance(
            vlan_id=VOICE_VLAN_ID,
            interfaces=(_StpRow("FastEthernet0/1"), _StpRow("FastEthernet0/2")),
        )
    ]
    result, *_ = _run(configuration=_Configuration(stp=stp))

    assert [item.stp_row_after for item in result.phones] == [FORWARDING, FORWARDING]
    assert result.stp_phone_row_after == FORWARDING


def test_addressing_judged_outside_realtime_is_not_judged():
    result, *_ = _run(mode=_ModeRuntime(_Mode(simulation_mode=True)))

    assert result.realtime_before is False
    assert result.outcome == UNOBSERVABLE


def test_the_lifecycle_journal_is_ordered_and_names_the_unobservable():
    result, *_ = _run()

    names = [item.name for item in result.lifecycle]
    assert [item.sequence for item in result.lifecycle] == list(
        range(1, len(result.lifecycle) + 1)
    )
    for milestone in (
        "DEVICE_CREATE_ORDER", "WHEN_PHONE_EXISTS", "WHEN_PHONE_IS_LINKED",
        "WHEN_ACCESS_VLAN_APPLIED", "WHEN_VOICE_VLAN_APPLIED",
        "WHEN_DHCP_POOL_EXISTS", "WHEN_OPTION150_APPLIED", "WHEN_CME_ENABLED",
        "WHEN_PHONE_BINDING_EXISTS", "WHEN_CNF_FILES_GENERATED",
    ):
        assert milestone in names
    # Phone boot state has no measured surface on this build, so it is written
    # UNOBSERVABLE instead of inferred from the device existing.
    powered = next(i for i in result.lifecycle if i.name == "WHEN_PHONE_IS_POWERED")
    assert powered.observed is False
    assert powered.status == UNOBSERVABLE
    assert names.index("WHEN_PHONE_EXISTS") < names.index("WHEN_PHONE_IS_LINKED")
    assert names.index("WHEN_VOICE_VLAN_APPLIED") < names.index("WHEN_CME_ENABLED")


def test_every_created_device_is_removed_even_when_the_pass_fails():
    physical = _Physical(_empty_workspace(), fail_on="_SW")
    result, physical, *_ = _run(physical=physical)

    # The switch failed to create, but it was still owned and still removed.
    assert physical.created == [
        f"{POSITIVE_VOICE_PREFIX}test01_R", f"{POSITIVE_VOICE_PREFIX}test01_SW",
    ]
    assert sorted(physical.removed) == sorted(physical.created)
    assert result.workspace_restored is True


def test_realtime_is_restored_from_the_mode_observed_before_the_run():
    mode = _ModeRuntime(_Mode(simulation_mode=False))
    result, _, _, _, _, mode, _ = _run(mode=mode)

    assert mode.set_calls == [False]
    assert result.realtime_restored is True


def test_the_slice_never_saves_the_workspace():
    source = Path(
        "src/packet_tracer_mcp/application/use_cases/qualify_positive_voice_slice.py"
    ).read_text(encoding="utf-8")

    assert ".pkt" not in source
    assert "save" not in source.lower().replace("save_", "")


def test_the_plan_uses_the_documented_models_and_voice_vlan():
    result, _, configuration, call_control, *_ = _run()

    assert (result.router_model, result.switch_model, result.phone_model) == (
        "2811", "3560-24PS", "7960",
    )
    assert result.voice_vlan_id == VOICE_VLAN_ID == 930
    assert EXTENSIONS[:2] == ("3101", "3102")
    voice_vlans = {
        getattr(action, "voice_vlan_id", None) for action in configuration.applied
    }
    assert VOICE_VLAN_ID in voice_vlans
    tftp = {getattr(action, "tftp_address", None) for action in call_control.applied}
    assert "10.93.0.1" in tftp


def test_a_contradicted_voice_vlan_readback_is_not_a_success():
    port = _Port(data_vlan_id=DATA_VLAN_ID, voice_vlan_id=1)
    result, *_ = _run(configuration=_Configuration(port=port))

    assert [item.voice_vlan_readback for item in result.phones] == [
        "CONTRADICTED", "CONTRADICTED",
    ]
    assert result.outcome != "SUCCESS"


def test_link_ownership_is_recorded_for_every_link_created():
    result, physical, *_ = _run()

    assert len(result.owned_links) == 3
    assert len(physical.links) == 3


def test_a_phone_outcome_reports_dimensions_independently():
    # Dimensions must not imply one another: a registered phone with no address
    # is still not addressed.
    outcome = PositiveVoicePhoneOutcome(
        voice_vlan_readback=VERIFIED, dhcp_enabled=YES, ipv4="",
        registration=REGISTERED,
    )

    assert outcome.addressed == UNOBSERVABLE
    assert outcome.ipv4_observed is False
    assert outcome.succeeded is False


def test_an_apipa_address_is_not_a_dhcp_lease():
    outcome = PositiveVoicePhoneOutcome(
        voice_vlan_readback=VERIFIED, dhcp_enabled=YES, ipv4="169.254.10.5",
        registration=REGISTERED,
    )

    assert outcome.ipv4_observed is False
    assert outcome.addressed == NO
    assert outcome.succeeded is False


def test_a_result_without_phones_is_unobservable_not_a_failure():
    assert PositiveVoiceSliceResult().outcome == UNOBSERVABLE


# --- the production result contracts ----------------------------------------
# `.applied` is the field the real objects publish.  Every one of these cases
# used to read as a successful mutation through a fail-open `.success` default.

def test_a_physical_result_that_was_not_applied_is_not_a_created_device():
    physical = _Physical(_empty_workspace(), fail_on="_SW")
    result, physical, *_ = _run(physical=physical)

    assert any("device_not_created" in item for item in result.errors)
    # Not created is not "created and then judged": nothing downstream ran.
    assert physical.links == []
    assert result.outcome == UNOBSERVABLE


def test_a_link_result_that_was_not_applied_fails_closed():
    class _RefusedLink(_Physical):
        def ensure_link(self, link):
            self.links.append(f"{link.device_a}:{link.port_a}")
            return _link_result(applied=False, message="port occupied")

    result, *_ = _run(physical=_RefusedLink(_empty_workspace()))

    assert any("link_failed" in item for item in result.errors)
    assert result.outcome == UNOBSERVABLE


def test_a_configuration_mutation_that_was_not_applied_fails_its_milestones():
    configuration = _Configuration(
        mutations=lambda action_id: _mutation(
            action_id=action_id, applied=False, message="IOS never reached ready",
        ),
    )
    result, *_ = _run(configuration=configuration)

    for name in (
        "WHEN_ACCESS_VLAN_APPLIED", "WHEN_VOICE_VLAN_APPLIED",
        "WHEN_DHCP_POOL_EXISTS", "CONFIGURATION_APPLY_ORDER",
    ):
        milestone = next(item for item in result.lifecycle if item.name == name)
        assert milestone.observed is False
        assert milestone.status == UNOBSERVABLE
    assert any("action_failed" in item for item in result.errors)


def test_a_voice_mutation_that_was_not_applied_fails_the_call_control_milestones():
    call_control = _CallControl(
        mutations=lambda action_id: _mutation(
            action_id=action_id, applied=False, message="batch refused",
        ),
    )
    result, *_ = _run(call_control=call_control)

    for name in (
        "WHEN_OPTION150_APPLIED", "WHEN_CME_ENABLED",
        "WHEN_PHONE_BINDING_EXISTS", "WHEN_CNF_FILES_GENERATED",
    ):
        milestone = next(item for item in result.lifecycle if item.name == name)
        assert milestone.observed is False


def test_no_legacy_success_flag_can_rescue_a_result_that_was_not_applied():
    class _LegacyPhysical(_Physical):
        def ensure_device(self, device):
            self.created.append(device.name)
            return _LegacySuccess()

    result, *_ = _run(physical=_LegacyPhysical(_empty_workspace()))
    assert any("device_not_created" in item for item in result.errors)

    result, *_ = _run(
        configuration=_Configuration(
            mutations=lambda action_id: _LegacySuccess(action_id=action_id),
        ),
    )
    applied = next(
        item for item in result.lifecycle if item.name == "WHEN_VOICE_VLAN_APPLIED"
    )
    assert applied.observed is False


def test_a_batch_that_answers_for_fewer_actions_than_it_was_given_is_not_applied():
    # An action with no mutation was never judged.  Reading the batch as
    # applied would be judging it by omission.
    class _Silent(_Configuration):
        def apply_actions(self, actions):
            self.applied.extend(actions)
            return []

    result, *_ = _run(configuration=_Silent())

    applied = next(
        item for item in result.lifecycle if item.name == "WHEN_DHCP_POOL_EXISTS"
    )
    assert applied.observed is False
    assert any("apply_incomplete" in item for item in result.errors)


# --- ownership before an ambiguous mutation ---------------------------------

def test_device_ownership_survives_a_create_that_raises():
    class _RaisingPhysical(_Physical):
        def ensure_device(self, device):
            if "_SW" in device.name:
                # The call was made; whatever the backend did with it is now
                # unknown, and that is exactly when ownership has to exist.
                raise RuntimeError("the backend went away mid-create")
            return super().ensure_device(device)

    result, physical, *_ = _run(physical=_RaisingPhysical(_empty_workspace()))

    assert f"{POSITIVE_VOICE_PREFIX}test01_SW" in result.removed
    assert f"{POSITIVE_VOICE_PREFIX}test01_R" in result.removed
    assert any("device_create_raised" in item for item in result.errors)


def test_link_ownership_survives_a_link_that_raises():
    class _RaisingLinks(_Physical):
        def ensure_link(self, link):
            raise RuntimeError("the backend went away mid-link")

    result, *_ = _run(physical=_RaisingLinks(_empty_workspace()))

    assert len(result.owned_links) == 1
    assert result.owned_links[0].startswith(f"{POSITIVE_VOICE_PREFIX}test01_R:")
    assert any("link_raised" in item for item in result.errors)


def test_cleanup_removes_only_the_devices_this_slice_owns():
    result, physical, *_ = _run()

    assert set(result.removed) == set(physical.created)
    assert all(item.startswith(POSITIVE_VOICE_PREFIX) for item in result.removed)


# --- the production registration expectation --------------------------------

def test_registration_expectations_carry_the_production_voice_contract():
    result, _, _, call_control, *_ = _run()

    assert len(call_control.expectations) == 2
    for index, expectation in enumerate(call_control.expectations, start=1):
        assert isinstance(expectation, VoiceVerificationExpectation)
        assert expectation.kind is VoiceVerificationKind.PHONE_REGISTRATION
        # The runtime reads the phone off THIS field to interrogate its SVI.
        assert expectation.endpoint_device_name == (
            f"{POSITIVE_VOICE_PREFIX}test01_P{index}"
        )
        assert expectation.endpoint_interface == PHONE_ADDRESSING_INTERFACE
        assert expectation.phone_id == f"voiceab/p{index}"
        assert expectation.extension == EXTENSIONS[index - 1]
        assert expectation.call_control_id
        # The action id names the binding that was actually applied.
        assert expectation.action_id in {
            getattr(action, "id", "") for action in call_control.applied
        }
    assert result.outcome == "SUCCESS"


def test_a_registration_the_runtime_could_not_attribute_is_unobservable():
    class _Unattributable(_CallControl):
        def observe_registrations(self, expectations):
            raise AssertionError("the expectation carried no phone")

    result, *_ = _run(call_control=_Unattributable())

    assert [item.registration for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]
    assert result.outcome == UNOBSERVABLE


# --- endpoint DHCP arming ---------------------------------------------------

def test_endpoint_dhcp_arming_that_was_refused_is_not_a_verified_milestone():
    class _Refused(_Endpoints):
        def configure_endpoint_dhcp(self, device_name, interface):
            self.armed.append(device_name)
            return False

    result, *_ = _run(endpoints=_Refused())

    armed = next(
        item for item in result.lifecycle if item.name == "WHEN_ENDPOINT_DHCP_ARMED"
    )
    assert armed.observed is False
    assert armed.status == UNOBSERVABLE
    assert any("endpoint_dhcp_not_accepted" in item for item in result.errors)


def test_one_unarmed_phone_is_enough_to_withhold_the_arming_milestone():
    class _HalfArmed(_Endpoints):
        def configure_endpoint_dhcp(self, device_name, interface):
            self.armed.append(device_name)
            return not device_name.endswith("P2")

    result, *_ = _run(endpoints=_HalfArmed())

    armed = next(
        item for item in result.lifecycle if item.name == "WHEN_ENDPOINT_DHCP_ARMED"
    )
    assert armed.observed is False


def test_endpoint_dhcp_arming_that_raises_is_not_a_verified_milestone():
    class _Raising(_Endpoints):
        def configure_endpoint_dhcp(self, device_name, interface):
            raise RuntimeError("no channel to the phone")

    result, *_ = _run(endpoints=_Raising())

    armed = next(
        item for item in result.lifecycle if item.name == "WHEN_ENDPOINT_DHCP_ARMED"
    )
    assert armed.observed is False


# --- STP row identity -------------------------------------------------------

def test_an_abbreviated_stp_row_is_the_same_port_as_the_typed_plan():
    # IOS prints `Fa0/1`; the plan says `FastEthernet0/1`.  Comparing raw made
    # every read row ABSENT, which is one of the two facts this A/B turns on.
    stp = [
        _StpInstance(
            vlan_id=VOICE_VLAN_ID,
            interfaces=(_StpRow("Fa0/1"), _StpRow("Fa0/2", state="BLK")),
        )
    ]
    result, *_ = _run(configuration=_Configuration(stp=stp))

    assert [item.stp_row_after for item in result.phones] == [FORWARDING, BLOCKING]
    assert result.stp_phone_row_after == "MIXED"


def test_a_truncated_binding_table_can_never_become_the_same_failure():
    # The CP-SCALE signature on every phone, and a binding table nobody read.
    # SAME_FAILURE needs a measured zero, not an unread one.
    signature = PositiveVoicePhoneOutcome(
        voice_vlan_readback=VERIFIED, dhcp_enabled=YES, ipv4="0.0.0.0",
        registration=NOT_REGISTERED,
    )
    unread = PositiveVoiceSliceResult(
        phones=(signature, signature), voice_binding_count=None,
        realtime_before=True, realtime_after=True,
    )
    measured = PositiveVoiceSliceResult(
        phones=(signature, signature), voice_binding_count=0,
        realtime_before=True, realtime_after=True,
    )

    assert unread.voice_bindings_observed == UNOBSERVABLE
    assert unread.outcome == UNOBSERVABLE
    assert measured.outcome == "SAME_FAILURE"


# --- where a phone holds an address -----------------------------------------
# The first LIVE armed and read the physical port the cable lands on.  It is a
# real port, so nothing failed; it simply has no DHCP client and no address to
# give, and every phone came back UNOBSERVABLE on the two dimensions the A/B
# turns on.

def test_the_phone_addressing_interface_is_the_one_production_derives():
    # Pinned to the compiler's own derivation: two copies of this rule would be
    # two sets of mistakes, and the drift would be invisible until a LIVE.
    assert PHONE_ADDRESSING_INTERFACE == _phone_addressing_interface(
        str(VOICE_VLAN_ID)
    )
    assert PHONE_ADDRESSING_INTERFACE == "Vlan930"
    assert PHONE_LINK_PORT != PHONE_ADDRESSING_INTERFACE


def test_dhcp_is_armed_on_the_svi_the_phone_addresses_on():
    result, _, _, _, endpoints, _, _ = _run()

    assert endpoints.armed_interfaces == [
        PHONE_ADDRESSING_INTERFACE, PHONE_ADDRESSING_INTERFACE,
    ]
    armed = next(
        item for item in result.lifecycle if item.name == "WHEN_ENDPOINT_DHCP_ARMED"
    )
    assert armed.observed is True


def test_production_pipeline_does_not_add_the_disposable_endpoint_arm():
    class _ProductionConfiguration(_Configuration):
        production_pipeline = True

    result, _, _, _, endpoints, _, _ = _run(
        configuration=_ProductionConfiguration(),
    )

    assert endpoints.armed == []
    names = [item.name for item in result.lifecycle]
    assert "WHEN_ENDPOINT_DHCP_ARMED" not in names
    assert "WHEN_ENDPOINT_DHCP_ACTIVATION_NOT_APPLICABLE" in names


def test_the_registration_expectation_reads_the_addressing_svi_not_the_cable():
    _, _, _, call_control, *_ = _run()

    assert [item.endpoint_interface for item in call_control.expectations] == [
        PHONE_ADDRESSING_INTERFACE, PHONE_ADDRESSING_INTERFACE,
    ]


def test_the_independent_endpoint_read_asks_the_same_interface():
    # Reached only when the registration surface carried no address, which is
    # exactly when the fallback has to ask the right port.
    result, _, _, _, endpoints, _, _ = _run(
        call_control=_CallControl(registration=_Registration(endpoint_ipv4="")),
    )

    assert endpoints.read_interfaces == [
        PHONE_ADDRESSING_INTERFACE, PHONE_ADDRESSING_INTERFACE,
    ]
    # The registration surface answered none on a channel that exists, so the
    # fallback read changes where the question was asked, not the answer.
    assert [item.addressed for item in result.phones] == [NO, NO]


def test_the_phone_link_still_lands_on_the_physical_port():
    # The cable attaches to `Switch`; only the ADDRESS moved to the SVI.
    _, physical, *_ = _run()

    assert PHONE_LINK_PORT == "Switch"
    assert len(physical.links) == 3


# --- an empty address is three different findings ---------------------------

def test_an_svi_that_answered_none_is_a_phone_that_did_not_acquire():
    # The channel was there and it reported no address.  That IS the finding.
    registration = _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="", endpoint_dhcp_enabled=True,
        endpoint_interface_present=True, endpoint_address_channel=True,
    )
    result, *_ = _run(
        configuration=_Configuration(bindings=[]),
        call_control=_CallControl(registration=registration),
    )

    assert [item.addressed for item in result.phones] == [NO, NO]
    assert [item.dhcp_enabled for item in result.phones] == [YES, YES]
    # Enabled, unaddressed, unregistered, zero bindings: the CP-SCALE shape.
    assert result.outcome == "SAME_FAILURE"


def test_an_svi_with_no_address_channel_is_not_a_phone_that_did_not_acquire():
    # Same empty string, nothing asked.  Calling this NO would invent the
    # finding the previous test earns.
    registration = _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="", endpoint_dhcp_enabled=True,
        endpoint_interface_present=True, endpoint_address_channel=False,
    )
    result, *_ = _run(
        configuration=_Configuration(bindings=[]),
        call_control=_CallControl(registration=registration),
    )

    assert [item.addressed for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]
    assert [item.address_channel for item in result.phones] == [False, False]
    assert result.outcome == UNOBSERVABLE


def test_a_phone_that_never_created_the_voice_svi_is_retained_as_such():
    registration = _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="", endpoint_dhcp_enabled=None,
        endpoint_interface_present=False, endpoint_address_channel=False,
    )
    result, *_ = _run(call_control=_CallControl(registration=registration))

    assert [item.voice_svi_present for item in result.phones] == [False, False]
    assert [item.addressed for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]
    assert [item.dhcp_enabled for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]


def test_an_address_the_voice_svi_does_not_report_is_never_promoted():
    # PT does not put the same getters on a device and on its ports.  An
    # address the phone reports elsewhere is a finding about WHERE to read, not
    # a phone that acquired on the voice VLAN.
    registration = _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="", endpoint_dhcp_enabled=True,
        endpoint_interface_present=True, endpoint_address_channel=True,
        device_ipv4="10.93.0.10",
    )
    result, *_ = _run(call_control=_CallControl(registration=registration))

    assert [item.ipv4 for item in result.phones] == ["", ""]
    assert [item.device_ipv4 for item in result.phones] == [
        "10.93.0.10", "10.93.0.10",
    ]
    assert [item.ipv4_observed for item in result.phones] == [False, False]
    assert all(not item.succeeded for item in result.phones)


def test_a_real_lease_on_the_voice_svi_still_reads_as_addressed():
    result, *_ = _run()

    assert [item.addressed for item in result.phones] == [YES, YES]
    assert [item.address_channel for item in result.phones] == [True, True]
    assert result.outcome == "SUCCESS"


def test_handoff_records_the_measured_positive_voice_ab_result():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert "POSITIVE_VOICE_AB_IMPLEMENTED = YES" in handoff
    assert "POSITIVE_VOICE_AB_LIVE = RUN at c9d6ead" in handoff
    assert "POSITIVE_VOICE_AB_RESULT = SAME_FAILURE" in handoff
    # An unrun experiment is never a negative result, so the blocker that
    # stood while it was unrun must not survive the run that replaced it.
    assert "POSITIVE_VOICE_AB_LIVE = NOT_RUN" not in handoff
    assert "POSITIVE_VOICE_AB_LIVE_BLOCKER" not in handoff

    # The five dimensions, each recorded as it was measured.
    assert "POSITIVE_SLICE_VOICE_VLAN_READBACK = VERIFIED 2/2" in handoff
    assert "POSITIVE_SLICE_PHONE_DHCP_ENABLED = YES 2/2" in handoff
    assert "POSITIVE_SLICE_PHONE_IPV4 = NONE 2/2" in handoff
    assert "POSITIVE_SLICE_VOICE_DHCP_BINDINGS = 0" in handoff
    assert "POSITIVE_SLICE_SCCP_REGISTRATION = NOT_REGISTERED 2/2" in handoff
    assert "POSITIVE_SLICE_STP_VOICE_PHONE_ROW = ABSENT" in handoff

    # The slice engineered nothing to reach this result.
    assert "POSITIVE_SLICE_PORTFAST = NOT_APPLIED" in handoff

    # What the result does and does not license.
    assert "SCALE_SPECIFIC_VOICE_FAILURE = NOT_ESTABLISHED / WEAKENED" in handoff
    # Weakened at the SYMPTOM level.  Four devices reproduce the endpoint
    # signature; that is not the same as the two failures sharing a cause.
    assert (
        "SCALE_SPECIFIC_VOICE_FAILURE_LEVEL = WEAKENED_AT_SYMPTOM_LEVEL" in handoff
    )
    # The positive control carried no PortFast either, so it separates nothing
    # and the causal verdicts stay exactly where they were.
    assert "PORTFAST_AS_VOICE_ROOT_CAUSE = NOT_CONFIRMED" in handoff
    assert (
        "VOICE_VLAN_STP_ROW_ABSENCE_CAUSAL_STATUS = NOT_ESTABLISHED_AS_CAUSE"
        in handoff
    )
    assert "SOURCE_DEFECT = EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING" in handoff


def test_handoff_keeps_the_router_side_readback_boundary_explicit():
    # WHEN_DHCP_POOL_EXISTS is APPLIED, which on this architecture means
    # DISPATCHED.  Reading it as "the pool existed and served nothing" would be
    # the promotion the whole evidence discipline exists to stop.
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert "NOT established -- only \"the pool action applied" in handoff
    assert "`WHEN_PHONE_IS_POWERED` is UNOBSERVABLE" in handoff


# --- APPLIED is not VERIFIED ------------------------------------------------
#
# A typed mutation coming back `applied=True` states that the runtime channel
# accepted the dispatch.  It states nothing about what the backend now holds.
# Collapsing the two turned eight router-side milestones -- the DHCP pool, the
# subinterfaces, option 150, CME -- into VERIFIED in the run 3 evidence, and
# that is the exact promotion this qualification exists to refuse.


def test_a_milestone_derived_from_an_applied_mutation_never_reads_verified():
    result, *_ = _run()

    for name in (
        "DEVICE_CREATE_ORDER", "WHEN_PHONE_EXISTS",
        "LINK_CREATE_ORDER", "WHEN_PHONE_IS_LINKED",
        "WHEN_ACCESS_VLAN_APPLIED", "WHEN_VOICE_VLAN_APPLIED",
        "WHEN_DHCP_POOL_EXISTS", "CONFIGURATION_APPLY_ORDER",
        "WHEN_OPTION150_APPLIED", "WHEN_CME_ENABLED",
        "WHEN_PHONE_BINDING_EXISTS", "WHEN_CNF_FILES_GENERATED",
        "WHEN_ENDPOINT_DHCP_ARMED",
    ):
        milestone = next(item for item in result.lifecycle if item.name == name)
        assert milestone.observed is True, name
        assert milestone.evidence == APPLICATION, name
        assert milestone.status == APPLIED, name
        assert milestone.status != VERIFIED, name


def test_verified_requires_an_independent_observation():
    result, *_ = _run()

    verified = [item for item in result.lifecycle if item.status == VERIFIED]
    assert verified, "an observed lifecycle has to be able to reach VERIFIED"
    for milestone in verified:
        assert milestone.evidence == OBSERVATION, milestone.name
    names = {item.name for item in verified}
    assert {"REALTIME_VERIFIED_BEFORE_WINDOW", "REALTIME_VERIFIED_AFTER_WINDOW"} <= names


def test_a_milestone_that_does_not_state_its_evidence_can_only_claim_application():
    # Fail closed: the weaker claim is the default, so a milestone added later
    # without saying what it rests on cannot silently reach VERIFIED.
    milestone = LifecycleMilestone(sequence=1, name="WHEN_SOMETHING", observed=True)

    assert milestone.evidence == APPLICATION
    assert milestone.status == APPLIED


def test_unobservable_stays_distinct_from_applied_and_verified():
    result, *_ = _run()

    powered = next(
        item for item in result.lifecycle if item.name == "WHEN_PHONE_IS_POWERED"
    )
    assert powered.observed is False
    assert powered.status == UNOBSERVABLE
    assert powered.status not in {APPLIED, VERIFIED}
    # An observation surface that answered nothing is not an applied mutation.
    assert powered.evidence == OBSERVATION
    assert len({APPLIED, VERIFIED, UNOBSERVABLE}) == 3


def test_a_mutation_that_was_refused_reaches_neither_applied_nor_verified():
    configuration = _Configuration(
        mutations=lambda action_id: _mutation(
            action_id=action_id, applied=False, message="IOS never reached ready",
        ),
    )
    result, *_ = _run(configuration=configuration)

    milestone = next(
        item for item in result.lifecycle if item.name == "WHEN_DHCP_POOL_EXISTS"
    )
    assert milestone.status == UNOBSERVABLE
    assert milestone.status not in {APPLIED, VERIFIED}


def test_serialized_evidence_keeps_application_and_verification_apart():
    # The retained JSON is the artefact the investigation is read from months
    # later.  If the distinction only lives in memory, the evidence file still
    # publishes eight router-side milestones as VERIFIED.
    result, *_ = _run()

    serialized = [item.as_evidence() for item in result.lifecycle]
    by_name = {item["name"]: item for item in serialized}

    assert by_name["WHEN_DHCP_POOL_EXISTS"]["status"] == APPLIED
    assert by_name["WHEN_DHCP_POOL_EXISTS"]["evidence"] == APPLICATION
    assert by_name["REALTIME_VERIFIED_AFTER_WINDOW"]["status"] == VERIFIED
    assert by_name["REALTIME_VERIFIED_AFTER_WINDOW"]["evidence"] == OBSERVATION
    assert by_name["WHEN_PHONE_IS_POWERED"]["status"] == UNOBSERVABLE
    assert VERIFIED not in {
        item["status"] for item in serialized if item["evidence"] == APPLICATION
    }


def test_the_live_serializer_publishes_the_evidence_kind_it_was_given():
    # Read as source, not imported: the LIVE runner resolves the production
    # namespace and pytest resolves `src.`, and loading both gives every typed
    # model two identities.
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(encoding="utf-8")

    assert "item.as_evidence()" in source
    # Nothing may rebuild the milestone dict beside the one the model publishes.
    assert '"status": item.status' not in source


# --- the shared Voice foundation, read back rather than assumed -------------
#
# The A/B reproduced the CP-SCALE endpoint signature at four devices, which
# makes SAME_FAILURE a fact about the OUTCOME and nothing yet about the cause.
# Both sides share a foundation -- the uplink trunk, the router's voice
# subinterface, the DHCP pool, the call control -- and not one of those had ever
# been read.  These reads add no configuration and turn no knob; they establish
# where the first common boundary actually is.


@dataclass
class _Trunk:
    """What the existing `read_trunk` readback publishes, shape for shape."""

    status: str = "trunking"
    native_vlan: int | None = 1
    allowed_vlans: tuple | None = (DATA_VLAN_ID, VOICE_VLAN_ID)
    active_vlans: tuple | None = (DATA_VLAN_ID, VOICE_VLAN_ID)
    forwarding_vlans: tuple | None = (DATA_VLAN_ID, VOICE_VLAN_ID)
    executed: bool = True
    fresh_output_observed: bool = True
    fresh_evidence: bool = True
    output_complete: bool = True
    device_identity_provenance: str = "confirmed_unique"
    interface: str = "GigabitEthernet0/1"


@dataclass
class _InterfaceRow:
    interface: str
    ip_address: str
    status: str = "up"
    protocol: str = "up"


def _router_rows(ipv4: str = "10.93.0.1", status: str = "up", protocol: str = "up"):
    return [
        _InterfaceRow("FastEthernet0/0", "unassigned", status, protocol),
        _InterfaceRow("FastEthernet0/0.931", "10.94.0.1", status, protocol),
        _InterfaceRow(f"FastEthernet0/0.{VOICE_VLAN_ID}", ipv4, status, protocol),
    ]


_UNSET = object()


class _FoundationConfiguration(_Configuration):
    """The configuration runtime WITH the two read-only foundation surfaces."""

    def __init__(
        self, *, trunk=_UNSET, interfaces=_UNSET, pool=_UNSET, **kwargs,
    ):
        super().__init__(**kwargs)
        self.trunk = _Trunk() if trunk is _UNSET else trunk
        self.interfaces = _router_rows() if interfaces is _UNSET else interfaces
        self.pool = DhcpPoolReadbackObservation(
            device_name="R",
            requested_pool_name="VOICEAB_VOICE",
            requested_range_start="10.93.0.10",
            requested_range_end="10.93.0.254",
            pool_present=True,
            requested_range_covered=True,
            range_start="10.93.0.1",
            range_end="10.93.0.254",
            subnet_ranges=(("10.93.0.1", "10.93.0.254"),),
            total_addresses=254,
            leased_addresses=0,
            excluded_addresses=9,
            available_addresses=245,
            fresh_evidence=True,
            output_complete=True,
            identity_confirmed=True,
        ) if pool is _UNSET else pool
        self.trunk_reads: list[tuple[str, str]] = []
        self.interface_reads: list[str] = []
        self.pool_reads: list[tuple[str, str, str, str]] = []

    def read_trunk(self, device_name, interface):
        self.trunk_reads.append((device_name, interface))
        return self.trunk

    def read_interface_addresses(self, device_name):
        self.interface_reads.append(device_name)
        return self.interfaces

    def read_dhcp_pool(self, device_name, pool_name, lease_start, lease_end):
        self.pool_reads.append((device_name, pool_name, lease_start, lease_end))
        return self.pool


class _FoundationCallControl(_CallControl):
    def __init__(self, *, table=_UNSET, **kwargs):
        super().__init__(**kwargs)
        self.table = {
            "executed": True, "fresh_output_observed": True,
            "output_complete": True, "ephones": [{"index": 1}, {"index": 2}],
        } if table is _UNSET else table
        self.inspected: list[str] = []

    def inspect_call_control(self, device_name):
        self.inspected.append(device_name)
        return self.table


def _run_foundation(*, configuration=None, call_control=None, **kwargs):
    return _run(
        configuration=(
            configuration if configuration is not None else _FoundationConfiguration()
        ),
        call_control=(
            call_control if call_control is not None else _FoundationCallControl()
        ),
        **kwargs,
    )


def test_the_trunk_dimensions_stay_four_independent_answers():
    # Allowed, active and forwarding are three separate IOS sections and the
    # native VLAN comes from a fourth.  Collapsing them would let a permitted
    # VLAN stand in for a forwarded one, which is the difference between a
    # trunk that is configured and a trunk that carries voice.
    configuration = _FoundationConfiguration(
        trunk=_Trunk(
            allowed_vlans=(DATA_VLAN_ID, VOICE_VLAN_ID),
            active_vlans=(DATA_VLAN_ID, VOICE_VLAN_ID),
            forwarding_vlans=(DATA_VLAN_ID,),
            native_vlan=1,
        ),
    )
    result, *_ = _run_foundation(configuration=configuration)
    foundation = result.foundation

    assert foundation.trunk_operational == VERIFIED
    assert foundation.trunk_allowed_voice == VERIFIED
    assert foundation.trunk_active_voice == VERIFIED
    assert foundation.trunk_forwarding_voice == CONTRADICTED
    assert foundation.trunk_native == VERIFIED
    assert foundation.trunk_native_vlan == 1
    assert foundation.trunk_status == "trunking"
    assert foundation.trunk_allowed_vlans == (DATA_VLAN_ID, VOICE_VLAN_ID)
    assert foundation.trunk_active_vlans == (DATA_VLAN_ID, VOICE_VLAN_ID)
    assert foundation.trunk_forwarding_vlans == (DATA_VLAN_ID,)


def test_voice_vlan_membership_in_the_exact_forwarding_set_verifies_that_dimension():
    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(
            trunk=_Trunk(
                allowed_vlans=(DATA_VLAN_ID, VOICE_VLAN_ID),
                active_vlans=(DATA_VLAN_ID, VOICE_VLAN_ID),
                forwarding_vlans=(VOICE_VLAN_ID,),
            ),
        ),
    )

    assert result.foundation.trunk_forwarding_vlans == (VOICE_VLAN_ID,)
    assert result.foundation.trunk_forwarding_voice == VERIFIED


def test_a_trunk_section_that_never_printed_is_unread_and_never_pruned():
    # `None` is the section being absent from the capture.  An empty tuple is
    # IOS printing the section and listing no VLAN.  Only the second is a
    # finding about the network.
    unread = _FoundationConfiguration(
        trunk=_Trunk(forwarding_vlans=None, active_vlans=None),
    )
    result, *_ = _run_foundation(configuration=unread)
    assert result.foundation.trunk_forwarding_voice == UNOBSERVABLE
    assert result.foundation.trunk_active_voice == UNOBSERVABLE

    printed_empty = _FoundationConfiguration(
        trunk=_Trunk(forwarding_vlans=(), active_vlans=()),
    )
    result, *_ = _run_foundation(configuration=printed_empty)
    assert result.foundation.trunk_forwarding_voice == CONTRADICTED
    assert result.foundation.trunk_active_voice == CONTRADICTED


def test_a_trunk_read_that_was_stale_or_incomplete_claims_nothing():
    for trunk in (
        _Trunk(fresh_output_observed=False, fresh_evidence=False),
        _Trunk(output_complete=False),
    ):
        result, *_ = _run_foundation(
            configuration=_FoundationConfiguration(trunk=trunk),
        )
        foundation = result.foundation
        assert foundation.trunk_operational == UNOBSERVABLE
        assert foundation.trunk_allowed_voice == UNOBSERVABLE
        assert foundation.trunk_active_voice == UNOBSERVABLE
        assert foundation.trunk_forwarding_voice == UNOBSERVABLE
        assert foundation.trunk_native == UNOBSERVABLE


def test_an_unattributed_trunk_keeps_its_sets_but_authorizes_no_verdict():
    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(
            trunk=_Trunk(device_identity_provenance="ambiguous"),
        ),
    )
    foundation = result.foundation

    assert foundation.trunk_read_authority == UNOBSERVABLE
    assert foundation.trunk_identity_provenance == "ambiguous"
    assert foundation.trunk_allowed_vlans == (DATA_VLAN_ID, VOICE_VLAN_ID)
    assert foundation.trunk_active_vlans == (DATA_VLAN_ID, VOICE_VLAN_ID)
    assert foundation.trunk_forwarding_vlans == (DATA_VLAN_ID, VOICE_VLAN_ID)
    assert foundation.trunk_allowed_voice == UNOBSERVABLE
    assert foundation.trunk_active_voice == UNOBSERVABLE
    assert foundation.trunk_forwarding_voice == UNOBSERVABLE


def test_a_runtime_that_publishes_no_trunk_readback_is_unobservable():
    # The plain configuration runtime has no `read_trunk`.  Nothing failed, so
    # nothing is recorded as an error -- the surface simply is not published.
    result, *_ = _run(configuration=_Configuration())

    assert result.foundation.trunk_operational == UNOBSERVABLE
    assert not any("trunk" in item for item in result.errors)


def test_the_router_voice_subinterface_is_read_back_on_three_dimensions():
    result, *_ = _run_foundation()
    foundation = result.foundation

    assert foundation.router_subinterface_present == VERIFIED
    assert foundation.router_subinterface_ipv4 == VERIFIED
    assert foundation.router_subinterface_state == VERIFIED
    assert foundation.router_subinterface_state_detail == "up/up"


def test_a_router_subinterface_that_is_down_is_not_a_missing_one():
    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(
            interfaces=_router_rows(status="administratively down", protocol="down"),
        ),
    )
    foundation = result.foundation

    assert foundation.router_subinterface_present == VERIFIED
    assert foundation.router_subinterface_ipv4 == VERIFIED
    assert foundation.router_subinterface_state == CONTRADICTED
    assert "administratively down" in foundation.router_subinterface_state_detail


def test_a_missing_router_foundation_readback_cannot_become_a_contradiction():
    # An unread table is not an absent subinterface.  Reading it as one would
    # manufacture the router-side finding this whole investigation is after.
    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(interfaces=None),
    )
    foundation = result.foundation

    assert foundation.router_subinterface_present == UNOBSERVABLE
    assert foundation.router_subinterface_ipv4 == UNOBSERVABLE
    assert foundation.router_subinterface_state == UNOBSERVABLE
    assert CONTRADICTED not in {
        foundation.router_subinterface_present,
        foundation.router_subinterface_ipv4,
        foundation.router_subinterface_state,
    }


def test_a_complete_router_table_without_the_subinterface_is_a_contradiction():
    # The distinction the previous test protects: this table WAS read, and the
    # subinterface was not in it.  That is a finding, not an absence of one.
    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(
            interfaces=[_InterfaceRow("FastEthernet0/0", "unassigned")],
        ),
    )

    assert result.foundation.router_subinterface_present == CONTRADICTED
    assert result.foundation.router_subinterface_ipv4 == UNOBSERVABLE


def test_a_subinterface_carrying_another_address_contradicts_the_expected_one():
    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(
            interfaces=_router_rows(ipv4="unassigned"),
        ),
    )

    assert result.foundation.router_subinterface_present == VERIFIED
    assert result.foundation.router_subinterface_ipv4 == CONTRADICTED


def test_the_measured_pool_surface_verifies_only_the_dimensions_it_exposes():
    result, *_ = _run_foundation()
    foundation = result.foundation

    assert foundation.dhcp_pool_existence == VERIFIED
    assert foundation.dhcp_pool_range == VERIFIED
    assert foundation.dhcp_pool_available_space == VERIFIED
    assert foundation.dhcp_pool_table_readback == VERIFIED
    assert foundation.dhcp_pool_name == "VOICEAB_VOICE"
    assert foundation.dhcp_pool_range_start == "10.93.0.1"
    assert foundation.dhcp_pool_range_end == "10.93.0.254"
    assert foundation.dhcp_pool_available_addresses == 245
    assert foundation.dhcp_pool_default_router == NOT_AVAILABLE
    assert foundation.dhcp_pool_exclusions == NOT_AVAILABLE
    assert foundation.option150 == NOT_AVAILABLE
    assert foundation.option150 != CONTRADICTED
    ladder = dict(result.foundation_ladder)
    assert ladder["DHCP_POOL_TABLE_READBACK"] == VERIFIED


def test_pool_absence_is_a_contradiction_but_does_not_invent_other_fields():
    absent = DhcpPoolReadbackObservation(
        device_name="R",
        requested_pool_name="VOICEAB_VOICE",
        requested_range_start="10.93.0.10",
        requested_range_end="10.93.0.254",
        pool_present=False,
        fresh_evidence=True,
        output_complete=True,
        identity_confirmed=True,
    )

    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(pool=absent),
    )

    assert result.foundation.dhcp_pool_existence == CONTRADICTED
    assert result.foundation.dhcp_pool_range == UNOBSERVABLE
    assert result.foundation.dhcp_pool_available_space == UNOBSERVABLE
    assert result.foundation.dhcp_pool_table_readback == CONTRADICTED


def test_pool_range_and_available_space_can_contradict_independently():
    wrong = DhcpPoolReadbackObservation(
        device_name="R",
        requested_pool_name="VOICEAB_VOICE",
        requested_range_start="10.93.0.10",
        requested_range_end="10.93.0.254",
        pool_present=True,
        requested_range_covered=False,
        range_start="10.93.0.1",
        range_end="10.93.0.20",
        total_addresses=20,
        leased_addresses=11,
        excluded_addresses=9,
        available_addresses=0,
        fresh_evidence=True,
        output_complete=True,
        identity_confirmed=True,
    )

    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(pool=wrong),
    )

    assert result.foundation.dhcp_pool_existence == VERIFIED
    assert result.foundation.dhcp_pool_range == CONTRADICTED
    assert result.foundation.dhcp_pool_available_space == CONTRADICTED
    assert result.foundation.dhcp_pool_table_readback == CONTRADICTED


def test_missing_pool_evidence_does_not_change_the_voice_outcome():
    registration = _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="0.0.0.0", endpoint_dhcp_enabled=True,
    )
    common = {
        "bindings": [],
    }
    unread, *_ = _run(
        configuration=_Configuration(**common),
        call_control=_CallControl(registration=registration),
    )
    observed, *_ = _run_foundation(
        configuration=_FoundationConfiguration(**common),
        call_control=_FoundationCallControl(registration=registration),
    )

    assert unread.outcome == "SAME_FAILURE"
    assert observed.outcome == "SAME_FAILURE"
    assert unread.foundation.dhcp_pool_table_readback == UNOBSERVABLE
    assert observed.foundation.dhcp_pool_table_readback == VERIFIED


def test_the_pool_ladder_stage_never_claims_the_whole_pool_configuration():
    # `show ip dhcp pool` exposes existence, the range and the free count. It
    # does NOT expose default-router, the excluded RANGES, or option 150, so a
    # stage called DHCP_POOL_DEFINITION reading VERIFIED would tell the next
    # session the pool is configured correctly -- a claim this evidence cannot
    # support. The stage is named for the table it actually read.
    from src.packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (  # noqa: E501
        FOUNDATION_STAGES,
    )

    assert "DHCP_POOL_TABLE_READBACK" in FOUNDATION_STAGES
    assert "DHCP_POOL_DEFINITION" not in FOUNDATION_STAGES

    result, *_ = _run_foundation()
    ladder = dict(result.foundation_ladder)

    assert ladder["DHCP_POOL_TABLE_READBACK"] == VERIFIED
    assert result.foundation.dhcp_pool_default_router == NOT_AVAILABLE
    assert result.foundation.dhcp_pool_exclusions == NOT_AVAILABLE
    assert result.foundation.option150 == NOT_AVAILABLE


def test_the_pool_read_asks_for_exactly_the_pool_the_slice_configures():
    # The observation is only about the intent if it names the same pool and
    # the same lease window. Two independent literals drift apart silently,
    # and the failure that drift produces is `pool_present=False` -- a WRONG
    # strong causal claim, not a visible error.
    from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
        ConfigureDhcpPool,
    )

    result, _physical, configuration, *_ = _run_foundation()

    pool = next(
        item for item in configuration.applied
        if isinstance(item, ConfigureDhcpPool)
    )
    assert configuration.pool_reads == [(
        pool.device_name, pool.pool_name, pool.lease_start, pool.lease_end,
    )]
    assert result.foundation.dhcp_pool_name == pool.pool_name


def test_the_call_control_table_is_read_as_a_foundation_of_its_own():
    result, _, _, call_control, *_ = _run_foundation()

    assert result.foundation.call_control_table == VERIFIED
    assert result.foundation.call_control_ephone_rows == 2
    assert call_control.inspected == [result.router_name]


def test_a_call_control_table_that_paged_claims_no_ephone_count():
    result, *_ = _run_foundation(
        call_control=_FoundationCallControl(table={
            "executed": True, "fresh_output_observed": True,
            "output_complete": False, "ephones": [],
        }),
    )

    assert result.foundation.call_control_table == UNOBSERVABLE
    assert result.foundation.call_control_ephone_rows is None


def test_the_foundation_reads_add_no_configuration_and_turn_no_knob():
    # The next LIVE has to run the SAME failing topology.  A read that changed
    # what gets applied would make it a different experiment.
    plain, _, plain_configuration, plain_call_control, *_ = _run()
    observed, _, configuration, call_control, *_ = _run_foundation()

    def emitted(runtime):
        return [
            (type(action).__name__, getattr(action, "id", ""))
            for action in runtime.applied
        ]

    assert emitted(configuration) == emitted(plain_configuration)
    assert emitted(call_control) == emitted(plain_call_control)
    assert observed.portfast == plain.portfast == "NOT_APPLIED"
    names = [
        type(action).__name__
        for action in configuration.applied + call_control.applied
    ]
    assert not any("Stp" in name or "PortFast" in name for name in names)


def test_a_contradicted_foundation_does_not_move_the_endpoint_outcome():
    # SAME_FAILURE is a statement about the endpoint and server surfaces.  New
    # foundation evidence localises it; it does not reclassify it.
    registration = _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="", endpoint_dhcp_enabled=True,
        endpoint_interface_present=True, endpoint_address_channel=True,
    )
    verified = _run_foundation(
        configuration=_FoundationConfiguration(bindings=[]),
        call_control=_FoundationCallControl(registration=registration),
    )[0]
    contradicted = _run_foundation(
        configuration=_FoundationConfiguration(
            bindings=[], trunk=_Trunk(forwarding_vlans=()),
            interfaces=[_InterfaceRow("FastEthernet0/0", "unassigned")],
        ),
        call_control=_FoundationCallControl(registration=registration),
    )[0]

    assert verified.outcome == "SAME_FAILURE"
    assert contradicted.outcome == "SAME_FAILURE"
    assert verified.first_boundary_stage != contradicted.first_boundary_stage


def test_the_first_common_boundary_is_reported_without_skipping_ahead():
    registration = _Registration(
        status="ActionExecutionStatus.FAILED", direct_readback="",
        endpoint_ipv4="", endpoint_dhcp_enabled=True,
        endpoint_interface_present=True, endpoint_address_channel=True,
    )
    result, *_ = _run_foundation(
        configuration=_FoundationConfiguration(
            bindings=[], trunk=_Trunk(forwarding_vlans=(DATA_VLAN_ID,)),
        ),
        call_control=_FoundationCallControl(registration=registration),
    )

    ladder = result.foundation_ladder
    assert [stage for stage, _ in ladder] == [
        "PHONE_ACCESS_AND_VOICE_VLAN", "SWITCH_TRUNK",
        "ROUTER_VOICE_SUBINTERFACE", "DHCP_POOL_TABLE_READBACK",
        "CALL_CONTROL_FOUNDATION", "ENDPOINT_DHCP", "ENDPOINT_ADDRESS",
        "VOICE_DHCP_BINDING", "SCCP_REGISTRATION",
    ]
    # The trunk contradiction comes before every endpoint symptom, and the
    # boundary names it rather than the symptom furthest downstream.
    assert result.first_boundary_stage == "SWITCH_TRUNK"
    assert result.first_boundary_status == CONTRADICTED


def test_an_unread_foundation_stops_the_walk_before_the_stages_behind_it():
    result, *_ = _run(configuration=_Configuration(), call_control=_CallControl())

    assert result.first_boundary_stage == "SWITCH_TRUNK"
    assert result.first_boundary_status == UNOBSERVABLE


def test_the_foundation_observations_are_journalled_as_observations():
    result, *_ = _run_foundation()

    for name in (
        "SWITCH_TRUNK_OBSERVED", "ROUTER_VOICE_SUBINTERFACE_OBSERVED",
        "CALL_CONTROL_TABLE_OBSERVED",
    ):
        milestone = next(item for item in result.lifecycle if item.name == name)
        assert milestone.evidence == OBSERVATION
        assert milestone.status == VERIFIED
    assert [item.sequence for item in result.lifecycle] == list(
        range(1, len(result.lifecycle) + 1)
    )


def test_handoff_records_the_foundation_the_slice_finally_read():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    # Every shared foundation dimension a governed read can reach, measured at
    # four devices, in the same failing topology as run 3.
    assert "POSITIVE_SLICE_TRUNK_ALLOWED_930 = VERIFIED" in handoff
    assert "POSITIVE_SLICE_TRUNK_ACTIVE_930 = VERIFIED" in handoff
    assert "POSITIVE_SLICE_TRUNK_FORWARDING_930 = VERIFIED" in handoff
    assert "POSITIVE_SLICE_TRUNK_NATIVE = VERIFIED" in handoff
    assert "POSITIVE_SLICE_ROUTER_VOICE_SUBINTERFACE = VERIFIED" in handoff
    assert "POSITIVE_SLICE_ROUTER_VOICE_IPV4 = VERIFIED" in handoff
    assert "POSITIVE_SLICE_ROUTER_VOICE_STATE = VERIFIED" in handoff
    # The ephone table is what was read.  "CME foundation" is broader than the
    # evidence: telephony-service and option 150 stay unobservable.
    assert "CALL_CONTROL_EPHONE_TABLE = VERIFIED" in handoff
    assert "CME_FOUNDATION_READBACK" not in handoff


def test_handoff_keeps_the_observer_ceiling_apart_from_a_finding():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    # It is a boundary of the OBSERVER, and the label has to say so: calling
    # it a failure boundary invites the next reader to hear a finding.
    assert (
        "FIRST_COMMON_VOICE_OBSERVABILITY_BOUNDARY = "
        "DHCP_POOL_DEFINITION / UNOBSERVABLE" in handoff
    )
    assert "FIRST_COMMON_VOICE_FAILURE_BOUNDARY" not in handoff
    assert "FIRST_CONTRADICTED_VOICE_STAGE = ENDPOINT_ADDRESS" in handoff
    # The ceiling is a property of the observer.  A handoff that shortened it
    # to "the pool is absent" would hand the next session a root cause nobody
    # measured, which is exactly what this run was built to avoid.
    assert "DHCP_POOL_CONFIGURATION_READBACK = ABSENT" not in handoff
    assert "DHCP_POOL_ABSENT" not in handoff


def test_handoff_refuses_to_promote_the_same_failure_into_a_same_cause():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert "SAME_ROOT_CAUSE = NOT_ESTABLISHED" in handoff
    assert "SAME_ROOT_CAUSE = ESTABLISHED" not in handoff
    assert "PORTFAST_AS_VOICE_ROOT_CAUSE = NOT_CONFIRMED" in handoff


def test_handoff_records_the_applied_verified_lifecycle_separation():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert "LIFECYCLE_APPLIED_VERIFIED_BOUNDARY = SEPARATED at 241e64b" in handoff
    assert "RAW_VOICE_AB_RUNS_PINNED = 11" in handoff


# --- PortFast as ONE changed variable ---------------------------------------
#
# Run 4 read every foundation dimension a governed query can reach and found
# them all VERIFIED, so the remaining causal candidate on the switch side is
# the edge policy the canonical pipeline never emits at Floor 1.  This
# intervention changes exactly that and nothing else: same devices, same links,
# same VLANs, same subinterfaces, same pool, same CME, same extensions, same
# window.  BPDU Guard stays OFF on purpose -- two variables would answer
# neither question.


class _ControlPlane:
    """The typed control-plane runtime, in the shape the slice consumes."""

    def __init__(self, mutations=None):
        self.applied: list = []
        self.mutations = mutations

    def apply_actions(self, actions):
        self.applied.extend(actions)
        if self.mutations is not None:
            return [self.mutations(getattr(a, "id", "")) for a in actions]
        return [_mutation(action_id=getattr(a, "id", "")) for a in actions]


def _edge_run(**kwargs):
    """Run the intervention with the foundation surfaces run 4 established."""
    kwargs.setdefault("configuration", _FoundationConfiguration())
    kwargs.setdefault("call_control", _FoundationCallControl())
    kwargs.setdefault("control_plane", _ControlPlane())
    kwargs.setdefault("edge_portfast", True)
    return _run(**kwargs)


def _edge_actions(control_plane):
    return [
        item for item in control_plane.applied
        if type(item).__name__ == "ConfigureStpEdgePort"
    ]


def test_the_intervention_emits_one_edge_action_per_phone_facing_port():
    result, _, _, _, _, _, control_plane = _edge_run()

    actions = _edge_actions(control_plane)
    assert len(actions) == 2
    assert [item.interface for item in actions] == [
        "FastEthernet0/1", "FastEthernet0/2",
    ]
    assert len(control_plane.applied) == 2
    assert [item.device_name for item in actions] == [result.switch_name] * 2


def test_portfast_is_on_and_bpdu_guard_is_deliberately_off():
    # `ConfigureStpEdgePort.bpduguard` defaults to True.  Taking the default
    # would change two variables in a one-variable experiment.
    _, _, _, _, _, _, control_plane = _edge_run()

    for action in _edge_actions(control_plane):
        assert action.portfast is True
        assert action.bpduguard is False


def test_no_edge_policy_reaches_the_uplink_the_trunk_or_the_router():
    _, _, _, _, _, _, control_plane = _edge_run()

    interfaces = {item.interface for item in _edge_actions(control_plane)}
    assert SWITCH_UPLINK_INTERFACE not in interfaces
    assert ROUTER_UPLINK_INTERFACE not in interfaces
    assert ROUTER_VOICE_SUBINTERFACE not in interfaces
    assert not any(item.startswith("Vlan") for item in interfaces)


def test_the_edge_actions_are_recognisably_this_disposable_slice_and_no_other():
    # Nothing here may be mistaken for a canonical CP-SCALE action later: the
    # device carries the disposable prefix and the site is this slice's own.
    result, _, _, _, _, _, control_plane = _edge_run()

    for action in _edge_actions(control_plane):
        assert action.device_name.startswith(POSITIVE_VOICE_PREFIX)
        assert action.site_id == "voiceab"
        assert action.id.startswith("voiceab/")
    assert result.switch_name.startswith(POSITIVE_VOICE_PREFIX)


def test_the_baseline_still_emits_no_edge_policy_at_all():
    # Run 4's behaviour is the control.  If the default moved, the comparison
    # would be against an experiment nobody ran.
    result, _, configuration, call_control, _, _, control_plane = _run(
        configuration=_FoundationConfiguration(),
        call_control=_FoundationCallControl(),
        control_plane=_ControlPlane(),
    )

    assert control_plane.applied == []
    assert result.portfast == "NOT_APPLIED"
    emitted = [
        type(item).__name__ for item in configuration.applied + call_control.applied
    ]
    assert not any("Stp" in name or "PortFast" in name for name in emitted)


def test_the_intervention_differs_from_the_baseline_by_the_edge_actions_alone():
    def shape(result, configuration, call_control):
        return {
            "configuration": [
                (type(a).__name__, a.id, a.model_dump(mode="json"))
                for a in configuration.applied
            ],
            "voice": [
                (type(a).__name__, a.id, a.model_dump(mode="json"))
                for a in call_control.applied
            ],
            "router": result.router_name,
            "switch": result.switch_name,
            "voice_vlan": result.voice_vlan_id,
            "links": tuple(result.owned_links),
            "phones": [
                (p.phone_name, p.extension, p.switch_interface) for p in result.phones
            ],
        }

    baseline = _run(
        configuration=_FoundationConfiguration(),
        call_control=_FoundationCallControl(),
        control_plane=_ControlPlane(),
    )
    intervention = _edge_run()

    assert shape(baseline[0], baseline[2], baseline[3]) == shape(
        intervention[0], intervention[2], intervention[3],
    )
    assert baseline[6].applied == []
    assert len(_edge_actions(intervention[6])) == 2


def test_the_intervention_changes_no_device_link_or_addressing_intent():
    baseline_physical = _Physical(_empty_workspace())
    intervention_physical = _Physical(_empty_workspace())
    baseline = _run(
        physical=baseline_physical, configuration=_FoundationConfiguration(),
        call_control=_FoundationCallControl(), control_plane=_ControlPlane(),
    )
    intervention = _edge_run(physical=intervention_physical)

    assert baseline_physical.created == intervention_physical.created
    assert baseline_physical.links == intervention_physical.links
    assert baseline[0].owned_links == intervention[0].owned_links
    # The phones are armed on the same interface, in the same order.
    assert baseline[4].armed == intervention[4].armed
    assert baseline[4].armed_interfaces == intervention[4].armed_interfaces


def test_an_applied_edge_mutation_is_not_a_verified_one():
    result, *_ = _edge_run()

    milestone = next(
        item for item in result.lifecycle if item.name == "WHEN_EDGE_PORTFAST_APPLIED"
    )
    assert milestone.evidence == APPLICATION
    assert milestone.status == APPLIED
    assert milestone.status != VERIFIED
    assert result.portfast == "APPLIED"
    assert result.portfast != VERIFIED


def test_a_refused_edge_mutation_never_reads_as_applied():
    control_plane = _ControlPlane(
        mutations=lambda action_id: _mutation(
            action_id=action_id, applied=False, message="the switch refused",
        ),
    )
    result, *_ = _edge_run(control_plane=control_plane)

    milestone = next(
        item for item in result.lifecycle if item.name == "WHEN_EDGE_PORTFAST_APPLIED"
    )
    assert milestone.status == UNOBSERVABLE
    assert result.portfast == "NOT_APPLIED"


def test_asking_for_the_intervention_without_a_control_plane_runtime_is_refused():
    # Silently running the baseline while the report says PortFast was on is
    # the one failure mode that would poison the comparison.
    result, *_ = _run(
        configuration=_FoundationConfiguration(),
        call_control=_FoundationCallControl(),
        edge_portfast=True,
    )

    assert result.portfast == "NOT_APPLIED"
    assert any("edge_portfast" in item for item in result.errors)


# --- reading PortFast back --------------------------------------------------

def test_an_edge_marker_in_the_stp_type_column_verifies_portfast():
    stp = [
        _StpInstance(VOICE_VLAN_ID, (
            _StpRow("FastEthernet0/1", link_type="P2p Edge"),
            _StpRow("FastEthernet0/2", link_type="P2p Edge"),
        )),
    ]
    result, *_ = _edge_run(
        configuration=_FoundationConfiguration(stp=stp),
    )

    assert [item.portfast_readback for item in result.phones] == [VERIFIED, VERIFIED]
    assert [item.stp_link_types for item in result.phones] == [
        ("P2p Edge",), ("P2p Edge",),
    ]
    assert result.portfast_readback == VERIFIED


def test_a_type_column_without_an_edge_marker_claims_nothing_either_way():
    # This build has never been measured printing an edge marker at all, so a
    # column without one cannot separate "PortFast is off" from "this IOS does
    # not print it".  UNOBSERVABLE is the only honest answer.
    stp = [
        _StpInstance(VOICE_VLAN_ID, (
            _StpRow("FastEthernet0/1", link_type="P2p"),
            _StpRow("FastEthernet0/2", link_type="P2p"),
        )),
    ]
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=stp))

    assert [item.portfast_readback for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]
    assert CONTRADICTED not in {item.portfast_readback for item in result.phones}
    assert result.portfast_readback == UNOBSERVABLE


def test_an_unread_stp_table_leaves_portfast_unobservable():
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=None))

    assert result.portfast_readback == UNOBSERVABLE
    assert [item.stp_link_types for item in result.phones] == [(), ()]


def test_an_absent_row_is_not_a_port_without_portfast():
    stp = [_StpInstance(VOICE_VLAN_ID, (_StpRow("GigabitEthernet0/1"),))]
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=stp))

    assert result.portfast_readback == UNOBSERVABLE
    assert [item.stp_row_after for item in result.phones] == [ABSENT, ABSENT]


def test_applied_portfast_and_verified_portfast_are_different_answers():
    # The mutation was accepted and the table says nothing.  Those are two
    # facts and the artefact keeps both.
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=None))

    assert result.portfast == "APPLIED"
    assert result.portfast_readback == UNOBSERVABLE
    assert result.portfast != result.portfast_readback


def test_the_intervention_publishes_no_causal_verdict_of_its_own():
    # The qualifier reports what it measured.  Whether PortFast explains
    # CP-SCALE is a comparison against a topology this run does not touch.
    result, *_ = _edge_run()

    evidence = result.foundation.as_evidence()
    for field in evidence:
        assert "root_cause" not in field
    assert not hasattr(result, "root_cause")
    assert not hasattr(result, "portfast_sufficiency")


def test_handoff_keeps_the_two_calibration_lineages_apart():
    # One head calibrated the frame/trunk VLAN field; another ran the Voice
    # A/B. They moved independently, and a single name for both let the second
    # overwrite the first's record of the calibration lineage.
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert (
        "LATEST_FRAME_VLAN_CALIBRATION_LIVE_HEAD = "
        "d15a5b71dff8b95b56404e550540ca0f3aef018d" in handoff
    )
    assert (
        "LATEST_VOICE_AB_LIVE_HEAD = 8ecee845c0553ae25e4e82d965671e98cf135bf3"
        in handoff
    )
    assert "LATEST_CALIBRATION_LIVE_HEAD" not in handoff


def test_the_disposable_names_render_through_the_trusted_control_plane_renderer():
    """TD-RUNTIME-004, met from the other side.

    The typed control-plane renderer's allowlist requires an alphanumeric first
    character, and the resolution on record for that conflict is a COMPATIBLE
    NAMESPACE, never a relaxed validator -- `test_the_discovery_prefix_is_still_
    refused_by_the_trusted_renderer` exists to keep it that way.  This slice now
    renders edge ports through that renderer, so it belongs in the compatible
    namespace as well.  Cleanup never depended on the prefix; it tracks the
    objects it created.

    The first LIVE of the intervention is what taught this: both edge mutations
    came back `Invalid compiled device name`, PortFast read NOT_APPLIED, and the
    run was a baseline wearing an experiment's name.  This contract is the
    offline version of that lesson.
    """
    from src.packet_tracer_mcp.infrastructure.generator.control_plane_renderer import (
        PacketTracerControlPlaneRenderer,
    )

    assert POSITIVE_VOICE_PREFIX[:1].isalnum(), POSITIVE_VOICE_PREFIX

    result, _, _, _, _, _, control_plane = _edge_run()
    renderer = PacketTracerControlPlaneRenderer()
    for action in _edge_actions(control_plane):
        rendered = renderer.render_action(action)
        assert rendered.device_name == result.switch_name
        lines = rendered.ios_payload.splitlines()
        assert " spanning-tree portfast" in lines
        assert " no spanning-tree bpduguard enable" in lines
        assert " spanning-tree bpduguard enable" not in lines


def test_a_rendering_refusal_is_reported_and_never_silently_downgraded():
    # What the first intervention LIVE actually did: the mutations were
    # refused, `portfast` stayed NOT_APPLIED and the reason reached the
    # evidence.  A run that had reported APPLIED anyway would have produced a
    # baseline wearing an experiment's name.
    control_plane = _ControlPlane(
        mutations=lambda action_id: _mutation(
            action_id=action_id, applied=False,
            message="Typed E9 rendering failed: Invalid compiled device name",
        ),
    )
    result, *_ = _edge_run(control_plane=control_plane)

    assert result.portfast == "NOT_APPLIED"
    assert any("Invalid compiled device name" in item for item in result.errors)


def test_handoff_records_the_portfast_only_control_as_the_no_effect_it_was():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert "PORTFAST_INTERVENTION_RESULT = NO_EFFECT" in handoff
    assert "PAIRED_BASELINE_MATCH = YES" in handoff
    assert "FIRST_STAGE_CHANGED_BETWEEN_PAIRED_RUNS = NONE" in handoff
    assert "PORTFAST_EXPERIMENT_BPDU_GUARD = OFF" in handoff
    # APPLIED is the mutation being accepted.  Nothing saw the switch holding
    # it, and the conclusion is bounded by that rather than rounded up.
    assert "POSITIVE_SLICE_PORTFAST = APPLIED" in handoff
    assert "PORTFAST_READBACK = UNOBSERVABLE" in handoff
    assert "PORTFAST_READBACK = VERIFIED" not in handoff
    assert "PORTFAST_SUFFICIENCY_IN_DISPOSABLE_VOICE = NOT_ESTABLISHED" in handoff


def test_handoff_promotes_only_the_ordering_root_after_causal_controls():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert "SAME_ROOT_CAUSE = NOT_ESTABLISHED" in handoff
    assert (
        "VOICE_ROOT_CAUSE_CONFIRMED = "
        "REGISTRATION_STARTS_BEFORE_AUTHORITATIVE_PHONE_ACCESS_FORWARDING_"
        "AFTER_LATE_VOICE_SIGNAL"
    ) in handoff
    assert (
        "UNOBSERVED_INTERNAL_MECHANISM = "
        "PHONE_BOOT_DHCP_ATTEMPT_AND_RETRY_TIMING"
    ) in handoff
    assert "SERVER_RECEIVES_DISCOVER = YES" not in handoff
    # The architectural defect is real and stays real; what weakened is its
    # standing as the explanation for THIS failure.
    assert "SOURCE_DEFECT = EDGE_STP_POLICY_STAGE_GATING_AND_ORDERING" in handoff
    assert "SOURCE_DEFECT_FOUND = YES" in handoff
    assert (
        "VOICE_VLAN_STP_ROW_ABSENCE_CAUSAL_STATUS = NOT_ESTABLISHED_AS_CAUSE"
        in handoff
    )


# --- the edge marker lives in whichever instance prints it ------------------
#
# Being an edge port is a property of the PORT, and `show spanning-tree` prints
# one row per VLAN instance.  The classifier's docstring said it searched every
# instance while the code returned on the first matching row, so a capture whose
# data-VLAN row printed `P2p` answered for a voice-VLAN row that said `P2p Edge`
# and never got read.  Run 6 happened not to expose it -- its voice-VLAN rows
# were ABSENT, leaving one row to find -- which is exactly the kind of luck a
# causal experiment must not depend on.


def _instances(*rows_by_vlan):
    return [_StpInstance(vlan, rows) for vlan, rows in rows_by_vlan]


def test_an_edge_marker_in_a_later_instance_still_verifies_the_port():
    stp = _instances(
        (DATA_VLAN_ID, (_StpRow("FastEthernet0/1", link_type="P2p"),
                        _StpRow("FastEthernet0/2", link_type="P2p"))),
        (VOICE_VLAN_ID, (_StpRow("FastEthernet0/1", link_type="P2p Edge"),
                         _StpRow("FastEthernet0/2", link_type="P2p Edge"))),
    )
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=stp))

    assert [item.portfast_readback for item in result.phones] == [VERIFIED, VERIFIED]
    assert result.portfast_readback == VERIFIED


def test_every_instance_that_printed_the_port_keeps_its_type_value():
    # The evidence is every column that named this port, not the first one.
    stp = _instances(
        (DATA_VLAN_ID, (_StpRow("FastEthernet0/1", link_type="P2p"),)),
        (VOICE_VLAN_ID, (_StpRow("FastEthernet0/1", link_type="P2p Edge"),)),
    )
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=stp))

    assert result.phones[0].stp_link_types == ("P2p", "P2p Edge")
    # The second phone was never printed at all, and says so with an empty tuple.
    assert result.phones[1].stp_link_types == ()
    assert result.phones[1].portfast_readback == UNOBSERVABLE


def test_rows_that_all_lack_the_marker_claim_nothing_either_way():
    stp = _instances(
        (DATA_VLAN_ID, (_StpRow("FastEthernet0/1", link_type="P2p"),)),
        (VOICE_VLAN_ID, (_StpRow("FastEthernet0/1", link_type="P2p"),)),
    )
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=stp))

    assert result.phones[0].stp_link_types == ("P2p", "P2p")
    assert result.phones[0].portfast_readback == UNOBSERVABLE
    assert result.phones[0].portfast_readback != CONTRADICTED


def test_a_baseline_without_portfast_never_becomes_a_contradiction():
    # The paired baseline reads exactly these columns.  If a missing `Edge`
    # counted as a finding, the baseline would manufacture the difference the
    # comparison exists to look for.
    stp = _instances(
        (DATA_VLAN_ID, (_StpRow("FastEthernet0/1", link_type="P2p"),
                        _StpRow("FastEthernet0/2", link_type="P2p"))),
    )
    result, *_ = _run(
        configuration=_FoundationConfiguration(stp=stp),
        call_control=_FoundationCallControl(),
    )

    assert result.portfast == "NOT_APPLIED"
    assert result.portfast_readback == UNOBSERVABLE
    assert CONTRADICTED not in {item.portfast_readback for item in result.phones}


def test_an_edge_marker_on_another_port_verifies_nothing_here():
    stp = _instances(
        (VOICE_VLAN_ID, (
            _StpRow("GigabitEthernet0/1", link_type="P2p Edge"),
            _StpRow("FastEthernet0/1", link_type="P2p"),
        )),
    )
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=stp))

    assert result.phones[0].portfast_readback == UNOBSERVABLE
    assert result.phones[0].stp_link_types == ("P2p",)
    assert "Edge" not in " ".join(result.phones[0].stp_link_types)


def test_a_port_no_instance_printed_has_no_types_and_no_verdict():
    stp = _instances((VOICE_VLAN_ID, (_StpRow("GigabitEthernet0/1"),)))
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=stp))

    assert [item.stp_link_types for item in result.phones] == [(), ()]
    assert result.portfast_readback == UNOBSERVABLE


def test_the_marker_is_a_word_and_not_any_substring():
    # `edge` has to be the Type column saying edge, not a longer token that
    # happens to contain those four letters.
    stp = _instances(
        (VOICE_VLAN_ID, (_StpRow("FastEthernet0/1", link_type="P2p Edgeless"),)),
    )
    result, *_ = _edge_run(configuration=_FoundationConfiguration(stp=stp))

    assert result.phones[0].portfast_readback == UNOBSERVABLE
    assert result.phones[0].stp_link_types == ("P2p Edgeless",)


def test_handoff_does_not_claim_run6_was_a_strict_one_variable_comparison():
    """Run 4 and run 6 differ by TWO things, and only one was the experiment.

    TD-RUNTIME-004 forced the disposable namespace to move between them.  There
    is no evidence a device name changes Voice behaviour, and there is also no
    measurement saying it does not -- which is exactly the assumption a causal
    A/B is not allowed to make silently about its own second variable.
    """
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert (
        "RUN4_VS_RUN6_SINGLE_VARIABLE = NOT_STRICTLY_ESTABLISHED" in handoff
    )
    assert "RUN4_VS_RUN6_SECOND_VARIABLE = DISPOSABLE_NAMESPACE_CHANGED" in handoff
    assert "RUN6 = VALID_ISOLATED_PORTFAST_INTERVENTION_ATTEMPT" in handoff
    assert "run 4 with exactly one variable moved" not in handoff
    # The governed network experiment stayed paired even though an observer-only
    # correction means the two LIVE processes did not run the same revision.
    assert "RUN6_VS_RUN7_SAME_CODE_REVISION = NO" in handoff
    assert "RUN6_VS_RUN7_SAME_NETWORK_MUTATION_PATH = YES" in handoff
    assert "RUN6_VS_RUN7_SAME_VOICE_CONFIGURATION = YES" in handoff
    assert (
        "RUN6_VS_RUN7_OBSERVER_DIFFERENCE = EDGE_MARKER_CLASSIFIER_FIX_ONLY"
        in handoff
    )
    assert "PAIRED_NETWORK_OUTCOME_MATCH = YES" in handoff
    assert "RUN6_VS_RUN7_SINGLE_VARIABLE = ESTABLISHED" not in handoff
    assert "RUN6_VS_RUN7_SAME_CODE_REVISION = YES" not in handoff
    assert "is run 6's other half: same code revision" not in handoff
    assert "DISPOSABLE_NAMESPACE_EFFECT = NONE_OBSERVED" in handoff


def test_handoff_separates_the_isolated_component_from_the_canonical_repair():
    # The canonical compiler couples an edge action to the global STP action
    # and takes both policy flags.  Run 6 deliberately emitted neither of those
    # couplings, which is correct isolation and NOT the eventual repair.
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert "ISOLATED_PORTFAST_COMPONENT_TESTED = YES" in handoff
    assert "EXACT_CANONICAL_STP_REPAIR_TESTED = NO" in handoff
    assert "GOVERNED_EDGE_PORTFAST_MUTATION = APPLIED_NO_OBSERVED_EFFECT" in handoff
    assert "PORTFAST_RUNTIME_STATE = UNOBSERVABLE" in handoff
    # The claim that the repair IS this dispatch was the overclaim.
    assert "is exactly this dispatch" not in handoff


def test_handoff_closes_the_portfast_branch_without_refuting_portfast():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert (
        "GOVERNED_EDGE_PORTFAST_DISPATCH_EFFECT = NO_OBSERVED_EFFECT" in handoff
    )
    # The dispatch had no observable effect.  That is not the same as PortFast
    # being refuted, and it is not the same as knowing the switch ran it.
    assert "PORTFAST_RUNTIME_STATE = UNOBSERVABLE" in handoff
    assert "PORTFAST_SUFFICIENCY_IN_DISPOSABLE_VOICE = NOT_ESTABLISHED" in handoff
    assert "PORTFAST_REFUTED" not in handoff
    assert "PORTFAST_RUNTIME_STATE_VERIFIED" not in handoff


# --- the paired access-VLAN causal control (run 9) ---------------------------
#
# The strongest surviving root-cause candidate is a Packet Tracer behaviour of
# the phone-facing ACCESS PORT SHAPE itself: with `access 931` + `voice 930`
# the complete realtime STP table lists the port only under the data VLAN, and
# the one simulation capture that ever saw a phone Discover saw the switch drop
# it at that port.  The experiment that can move that hypothesis is a same-run
# two-phone A/B whose ONLY network-policy difference is the intervention
# phone's access VLAN being the voice VLAN.  These contracts pin that the
# mapping changes exactly that one field, and nothing else.


def _access_actions(configuration):
    return sorted(
        (
            action for action in configuration.applied
            if type(action).__name__ == "ConfigureAccessPort"
        ),
        key=lambda action: action.interface,
    )


_PAIRED = (DATA_VLAN_ID, VOICE_VLAN_ID)


def test_the_default_slice_still_puts_every_phone_port_on_the_data_vlan():
    _, _, configuration, *_ = _run()

    access = _access_actions(configuration)
    assert [action.interface for action in access] == [
        "FastEthernet0/1", "FastEthernet0/2",
    ]
    assert [action.data_vlan_id for action in access] == [
        DATA_VLAN_ID, DATA_VLAN_ID,
    ]
    assert [action.voice_vlan_id for action in access] == [
        VOICE_VLAN_ID, VOICE_VLAN_ID,
    ]


def test_the_paired_mapping_moves_exactly_the_intervention_ports_access_vlan():
    _, _, configuration, *_ = _run(phone_access_vlans=_PAIRED)

    access = _access_actions(configuration)
    assert [
        (action.interface, action.data_vlan_id, action.voice_vlan_id)
        for action in access
    ] == [
        ("FastEthernet0/1", DATA_VLAN_ID, VOICE_VLAN_ID),
        ("FastEthernet0/2", VOICE_VLAN_ID, VOICE_VLAN_ID),
    ]


def test_the_paired_mapping_changes_no_other_intent_at_all():
    def shape(result, configuration, call_control):
        return {
            "configuration": [
                (type(a).__name__, a.id, a.model_dump(mode="json"))
                for a in configuration.applied
                if type(a).__name__ != "ConfigureAccessPort"
            ],
            "voice": [
                (type(a).__name__, a.id, a.model_dump(mode="json"))
                for a in call_control.applied
            ],
            "links": tuple(result.owned_links),
            "phones": [
                (p.phone_name, p.extension, p.switch_interface)
                for p in result.phones
            ],
        }

    baseline_physical = _Physical(_empty_workspace())
    paired_physical = _Physical(_empty_workspace())
    baseline = _run(physical=baseline_physical)
    paired = _run(physical=paired_physical, phone_access_vlans=_PAIRED)

    assert shape(baseline[0], baseline[2], baseline[3]) == shape(
        paired[0], paired[2], paired[3],
    )
    assert baseline_physical.created == paired_physical.created
    assert baseline_physical.links == paired_physical.links
    # The phones are armed on the same SVI, in the same order, on both sides.
    assert baseline[4].armed == paired[4].armed
    assert baseline[4].armed_interfaces == paired[4].armed_interfaces
    # And the two access-port actions differ in the one experimental field.
    baseline_access = _access_actions(baseline[2])
    paired_access = _access_actions(paired[2])
    assert [
        (b.model_dump(mode="json"), p.model_dump(mode="json"))
        for b, p in zip(baseline_access, paired_access)
    ][0][0] == [
        (b.model_dump(mode="json"), p.model_dump(mode="json"))
        for b, p in zip(baseline_access, paired_access)
    ][0][1]
    changed = [
        (b.model_dump(mode="json"), p.model_dump(mode="json"))
        for b, p in zip(baseline_access, paired_access)
    ][1]
    assert changed[0] != changed[1]
    changed[0].pop("data_vlan_id"), changed[1].pop("data_vlan_id")
    assert changed[0] == changed[1]


def test_the_paired_mapping_applies_no_edge_policy():
    result, _, configuration, *_ = _run(phone_access_vlans=_PAIRED)

    assert [
        action for action in configuration.applied
        if type(action).__name__ == "ConfigureStpEdgePort"
    ] == []
    assert result.portfast == "NOT_APPLIED"


def test_a_paired_mapping_must_name_every_phone_port_once():
    with pytest.raises(ValueError, match="one access VLAN per phone"):
        _qualifier(
            _Physical(_empty_workspace()), _Configuration(), _CallControl(),
            _Endpoints(), _ModeRuntime(),
            phone_access_vlans=(DATA_VLAN_ID,),
        )


def test_a_paired_mapping_may_only_use_the_slices_own_vlans():
    with pytest.raises(ValueError, match="does not exist in this slice"):
        _qualifier(
            _Physical(_empty_workspace()), _Configuration(), _CallControl(),
            _Endpoints(), _ModeRuntime(),
            phone_access_vlans=(DATA_VLAN_ID, 999),
        )


def test_each_access_port_readback_is_judged_against_its_own_expected_vlan():
    configuration = _Configuration(port={
        "FastEthernet0/1": _Port(DATA_VLAN_ID, VOICE_VLAN_ID),
        "FastEthernet0/2": _Port(VOICE_VLAN_ID, VOICE_VLAN_ID),
    })
    result, _, configuration, *_ = _run(
        configuration=configuration, phone_access_vlans=_PAIRED,
    )

    assert configuration.access_reads == [
        ("FastEthernet0/1", DATA_VLAN_ID),
        ("FastEthernet0/2", VOICE_VLAN_ID),
    ]
    assert [item.access_vlan_expected for item in result.phones] == [
        DATA_VLAN_ID, VOICE_VLAN_ID,
    ]
    assert [item.data_vlan_readback for item in result.phones] == [
        VERIFIED, VERIFIED,
    ]
    assert [item.voice_vlan_readback for item in result.phones] == [
        VERIFIED, VERIFIED,
    ]


def test_an_intervention_port_left_on_the_data_vlan_reads_contradicted():
    # The readback compares against the EXPERIMENT's intent, not the default:
    # a switch that kept Fa0/2 on 931 after being asked for 930 is a
    # contradiction of the paired mapping and must surface as one.
    configuration = _Configuration(port=_Port(DATA_VLAN_ID, VOICE_VLAN_ID))
    result, *_ = _run(
        configuration=configuration, phone_access_vlans=_PAIRED,
    )

    assert [item.data_vlan_readback for item in result.phones] == [
        VERIFIED, CONTRADICTED,
    ]


def test_the_default_readback_expectation_is_unchanged():
    result, _, configuration, *_ = _run()

    assert configuration.access_reads == [
        ("FastEthernet0/1", DATA_VLAN_ID),
        ("FastEthernet0/2", DATA_VLAN_ID),
    ]
    assert [item.access_vlan_expected for item in result.phones] == [
        DATA_VLAN_ID, DATA_VLAN_ID,
    ]


def test_the_live_serializer_publishes_each_phones_access_vlan_half():
    # Read as source for the same namespace reason as the serializer test
    # above: importing the runner would load the production package beside
    # `src.` and split every typed model into two identities.
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(encoding="utf-8")

    assert '"access_vlan_expected": item.access_vlan_expected' in source
    assert "--paired-access-vlan" in source


# --- run 10: the FWD-gated fresh-DHCP paired control -------------------------
#
# Run 9 established that the access-VLAN shape controls voice-VLAN spanning-tree
# MEMBERSHIP, and could not test DHCP because the intervention port was read
# LIS immediately before the window and LRN immediately after it: forwarding
# was never OBSERVED, and the phones were judged on a port that was never seen
# past convergence.  Run 10 exists to close exactly that: DHCP is armed only
# AFTER a fresh+complete qualified STP read establishes FWD on the intervention
# port, and only when the pre-arm readback proves the arming call is a real
# OFF-to-ON transition.  Anything less fails closed with a named boundary
# instead of another ambiguous SAME_FAILURE.


@dataclass
class _EndpointObservation:
    """What the governed per-phone SVI read publishes, shape for shape."""

    present: bool | None = None
    ipv4: str = ""
    address_channel: bool = True
    dhcp_enabled: bool | None = None
    device_ipv4: str = ""
    device_dhcp_enabled: bool | None = None


class _Clock:
    """Deterministic monotonic time: sleeping IS how time advances here."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _stp(state, interface="FastEthernet0/2"):
    return [_StpInstance(vlan_id=VOICE_VLAN_ID, interfaces=(
        _StpRow(interface=interface, state=state),
    ))]


def _stp_both(control_state, intervention_state):
    return [_StpInstance(vlan_id=VOICE_VLAN_ID, interfaces=(
        _StpRow(interface="FastEthernet0/1", state=control_state),
        _StpRow(interface="FastEthernet0/2", state=intervention_state),
    ))]


_NO_ROW = [_StpInstance(vlan_id=VOICE_VLAN_ID, interfaces=())]

_PAIRED_GATED = dict(
    phone_access_vlans=_PAIRED, fwd_gated_fresh_dhcp=True,
)


class _ContractEndpoints(_Endpoints):
    """Per-phone PRE/ARM/POST answers for the Run-10 causal contract."""

    def __init__(
        self, *, pre=(False, False), accepted=(True, True),
        post=(True, True), timeline=None,
    ):
        super().__init__(timeline=timeline)
        self._pre = pre
        self._accepted = accepted
        self._post = post

    @staticmethod
    def _phone_index(device_name):
        return 0 if device_name.endswith("P1") else 1

    def configure_endpoint_dhcp(self, device_name, interface):
        if self.timeline is not None:
            self.timeline.append(f"arm:{device_name}")
        self.armed.append(device_name)
        self.armed_interfaces.append(interface)
        return self._accepted[self._phone_index(device_name)]

    def read_endpoint_address(self, device_name, interface):
        if self.timeline is not None:
            self.timeline.append(f"endpoint_read:{device_name}")
        self.read_interfaces.append(interface)
        flags = self._post if self.armed else self._pre
        return _EndpointObservation(
            dhcp_enabled=flags[self._phone_index(device_name)],
        )


def _gate(sequence, *, timeout=60.0, interval=2.0):
    clock = _Clock()
    configuration = _Configuration(stp_sequence=sequence)
    result = await_stp_forwarding(
        configuration, "SW", VOICE_VLAN_ID, "FastEthernet0/2",
        timeout_seconds=timeout, interval_seconds=interval,
        clock=clock, sleeper=clock.sleep,
    )
    return result, clock


class _DiagnosticConfiguration:
    """Publishes one already-captured STP table with its same-read metadata."""

    def __init__(self, observations):
        self.observations = list(observations)
        self.calls = 0

    def read_spanning_tree_observation(self, device_name):
        self.calls += 1
        if len(self.observations) > 1:
            return self.observations.pop(0)
        return self.observations[0]


class _LegacyOnlyConfiguration:
    """The pre-diagnostic parsed-table contract, with no authority metadata."""

    def __init__(self, instances):
        self.instances = instances
        self.calls = 0

    def read_spanning_tree(self, device_name):
        self.calls += 1
        return self.instances


def _stp_read(
    instances,
    *,
    executed=True,
    fresh=True,
    complete=True,
    identity="confirmed_unique",
    failure_reason="",
    failure_dimensions=(),
):
    return StpReadObservation(
        instances=instances,
        executed=executed,
        fresh=fresh,
        complete=complete,
        identity_provenance=identity,
        failure_reason=failure_reason,
        duration_ms=17,
        failure_dimensions=tuple(failure_dimensions),
    )


def _diagnostic_gate(observations, *, timeout=60.0, interval=2.0):
    clock = _Clock()
    configuration = _DiagnosticConfiguration(observations)
    result = await_stp_forwarding(
        configuration, "SW", VOICE_VLAN_ID, "FastEthernet0/2",
        timeout_seconds=timeout, interval_seconds=interval,
        clock=clock, sleeper=clock.sleep,
    )
    return result, configuration


def test_a_forwarding_row_satisfies_the_gate_at_the_first_qualified_read():
    result, clock = _gate([_stp("FWD")])

    assert result.status == FORWARDING
    assert result.forwarding_observed is True
    assert result.observed_states == (FORWARDING,)
    assert result.samples == 1
    assert clock.sleeps == []


def test_an_authoritative_forwarding_observation_has_no_failure_dimensions():
    result, configuration = _diagnostic_gate([_stp_read(_stp("FWD"))])

    assert result.status == FORWARDING
    assert result.terminal_read_authority == "AUTHORITATIVE"
    assert result.terminal_failure_dimensions == ()
    assert result.terminal_executed == YES
    assert result.terminal_fresh == YES
    assert result.terminal_complete == YES
    assert result.terminal_identity_provenance == "confirmed_unique"
    assert configuration.calls == 1


def test_listening_does_not_satisfy_the_gate():
    result, _ = _gate([_stp("LIS")], timeout=4.0, interval=2.0)

    assert result.status == GATE_TIMEOUT
    assert result.forwarding_observed is False
    assert result.observed_states == ("LIS",)


def test_learning_does_not_satisfy_the_gate():
    result, _ = _gate([_stp("LRN")], timeout=4.0, interval=2.0)

    assert result.status == GATE_TIMEOUT
    assert result.observed_states == ("LRN",)


def test_an_absent_row_does_not_satisfy_the_gate():
    result, _ = _gate([_NO_ROW], timeout=4.0, interval=2.0)

    assert result.status == GATE_TIMEOUT
    assert result.observed_states == (ABSENT,)


def test_a_blocking_row_is_not_success_but_may_still_converge():
    result, _ = _gate([_stp("BLK"), _stp("FWD")])

    assert result.status == FORWARDING
    assert result.observed_states == (BLOCKING, FORWARDING)


def test_the_convergence_sequence_is_retained_compactly():
    result, clock = _gate([
        _NO_ROW, _stp("LIS"), _stp("LIS"), _stp("LRN"), _stp("FWD"),
    ])

    assert result.status == FORWARDING
    # Adjacent repeats collapse; the transitions survive.
    assert result.observed_states == (ABSENT, "LIS", "LRN", FORWARDING)
    assert result.samples == 5
    assert result.duration_ms == int(sum(clock.sleeps) * 1000)


def test_a_timeout_while_converging_reads_timeout_not_never():
    result, _ = _gate([_stp("LIS"), _stp("LRN")], timeout=6.0, interval=2.0)

    assert result.status == GATE_TIMEOUT
    assert result.observed_states == ("LIS", "LRN")
    assert result.forwarding_observed is False


def test_an_unreadable_table_keeps_polling_but_fails_closed_at_the_bound():
    result, _ = _gate([None], timeout=4.0, interval=2.0)

    assert result.status == GATE_TIMEOUT
    assert result.observed_states == (UNOBSERVABLE,)
    assert result.forwarding_observed is False


def test_a_transient_unobservable_gap_can_recover_to_new_authoritative_fwd():
    result, configuration = _diagnostic_gate([
        _stp_read(_stp("LIS")),
        _stp_read(_stp("LRN")),
        _stp_read(
            None,
            fresh=False,
            failure_reason="No fresh current-command output window was observed.",
            failure_dimensions=("FRESHNESS",),
        ),
        _stp_read(_stp("LRN")),
        _stp_read(_stp("FWD")),
    ])

    assert result.status == FORWARDING
    assert result.forwarding_observed is True
    assert result.observed_states == (
        "LIS", "LRN", UNOBSERVABLE, "LRN", FORWARDING,
    )
    assert result.samples == 5
    assert result.terminal_read_authority == "AUTHORITATIVE"
    assert result.terminal_failure_dimensions == ()
    assert configuration.calls == 5


def test_the_unobservable_gap_is_retained_in_transition_evidence_after_recovery():
    result, _ = _diagnostic_gate([
        _stp_read(_stp("LIS")),
        _stp_read(
            None,
            complete=False,
            failure_reason="The STP table was incomplete.",
            failure_dimensions=("COMPLETENESS",),
        ),
        _stp_read(_stp("FWD")),
    ])

    assert result.as_evidence()["transitions"] == [
        {
            "state": "LIS",
            "read_authority": "AUTHORITATIVE",
            "failure_dimensions": [],
        },
        {
            "state": UNOBSERVABLE,
            "read_authority": UNOBSERVABLE,
            "failure_dimensions": ["COMPLETENESS"],
        },
        {
            "state": FORWARDING,
            "read_authority": "AUTHORITATIVE",
            "failure_dimensions": [],
        },
    ]


def test_repeated_unobservable_samples_without_authoritative_fwd_time_out():
    gap = _stp_read(
        None,
        identity="ambiguous",
        failure_reason="The STP table was not uniquely attributed.",
        failure_dimensions=("IDENTITY",),
    )
    result, configuration = _diagnostic_gate(
        [gap], timeout=4.0, interval=2.0,
    )

    assert result.status == GATE_TIMEOUT
    assert result.forwarding_observed is False
    assert result.observed_states == (UNOBSERVABLE,)
    assert result.samples == 3
    assert result.terminal_failure_dimensions == ("IDENTITY",)
    assert configuration.calls == 3


def test_authority_transitions_retain_the_terminal_failure_without_every_sample():
    result, configuration = _diagnostic_gate([
        _stp_read(_stp("LIS")),
        _stp_read(_stp("LIS")),
        _stp_read(_stp("LRN")),
        _stp_read(
            None,
            fresh=False,
            failure_reason="No fresh current-command output window was observed.",
            failure_dimensions=("FRESHNESS",),
        ),
    ], timeout=6.0, interval=2.0)

    assert result.status == GATE_TIMEOUT
    assert result.observed_states == ("LIS", "LRN", UNOBSERVABLE)
    assert result.samples == 4
    assert result.terminal_read_authority == UNOBSERVABLE
    assert result.terminal_failure_dimensions == ("FRESHNESS",)
    assert result.terminal_fresh == NO
    assert result.as_evidence()["transitions"] == [
        {
            "state": "LIS",
            "read_authority": "AUTHORITATIVE",
            "failure_dimensions": [],
        },
        {
            "state": "LRN",
            "read_authority": "AUTHORITATIVE",
            "failure_dimensions": [],
        },
        {
            "state": UNOBSERVABLE,
            "read_authority": UNOBSERVABLE,
            "failure_dimensions": ["FRESHNESS"],
        },
    ]
    assert configuration.calls == 4


def test_a_terminal_invalid_read_cannot_reuse_an_earlier_forwarding_fact():
    gate = StpForwardingGate(
        status=UNOBSERVABLE,
        observed_states=(FORWARDING, UNOBSERVABLE),
        terminal_read_authority=UNOBSERVABLE,
        terminal_failure_dimensions=("IDENTITY",),
    )

    assert gate.forwarding_observed is False


def test_identity_is_required_even_when_a_fwd_observation_claims_no_failures():
    forged = _stp_read(
        _stp("FWD"), identity="ambiguous", failure_dimensions=(),
    )

    assert forged.authoritative is False


def test_a_non_authoritative_fwd_sample_never_authorizes_dhcp_mutation():
    class _GapConfiguration(_Configuration):
        def __init__(self):
            super().__init__(stp=_stp("LIS"))
            self.gate_calls = 0

        def read_spanning_tree_observation(self, device_name):
            self.gate_calls += 1
            return _stp_read(
                _stp("FWD"), identity="ambiguous", failure_dimensions=(),
            )

    clock = _Clock()
    configuration = _GapConfiguration()
    endpoints = _Endpoints()
    result, *_ = _run(
        configuration=configuration,
        endpoints=endpoints,
        gate_clock=clock,
        gate_sleeper=clock.sleep,
        gate_timeout_seconds=4.0,
        gate_interval_seconds=2.0,
        **_PAIRED_GATED,
    )

    assert result.stp_gate.status == GATE_TIMEOUT
    assert result.stp_gate.forwarding_observed is False
    assert configuration.gate_calls == 3
    assert endpoints.armed == []


def test_a_legacy_parsed_fwd_sample_has_no_authority_and_times_out():
    clock = _Clock()
    configuration = _LegacyOnlyConfiguration(_stp("FWD"))
    result = await_stp_forwarding(
        configuration, "SW", VOICE_VLAN_ID, "FastEthernet0/2",
        timeout_seconds=4.0, interval_seconds=2.0,
        clock=clock, sleeper=clock.sleep,
    )

    assert result.status == GATE_TIMEOUT
    assert result.forwarding_observed is False
    assert result.observed_states == (UNOBSERVABLE,)
    assert result.terminal_failure_dimensions == ("IDENTITY",)
    assert configuration.calls == 3


def test_forwarding_is_observed_at_a_read_never_inferred_from_time():
    # Time may run out entirely while every read still says LIS; elapsed time
    # alone never becomes FWD.
    result, clock = _gate([_stp("LIS")], timeout=60.0, interval=2.0)

    assert clock.now >= 60.0
    assert result.status == GATE_TIMEOUT


def test_the_gated_mode_requires_the_paired_mapping():
    with pytest.raises(ValueError, match="paired"):
        _qualifier(
            _Physical(_empty_workspace()), _Configuration(), _CallControl(),
            _Endpoints(), _ModeRuntime(), fwd_gated_fresh_dhcp=True,
        )


def test_the_gated_mode_refuses_portfast_as_a_second_variable():
    with pytest.raises(ValueError, match="one causal variable"):
        _qualifier(
            _Physical(_empty_workspace()), _Configuration(), _CallControl(),
            _Endpoints(), _ModeRuntime(), control_plane=_ControlPlane(),
            edge_portfast=True, phone_access_vlans=_PAIRED,
            fwd_gated_fresh_dhcp=True,
        )


def _gated_run(*, stp_sequence, endpoints=None, timeline=None, **kwargs):
    clock = _Clock()
    configuration = _Configuration(stp_sequence=stp_sequence, timeline=timeline)
    endpoints = endpoints if endpoints is not None else _Endpoints(
        observation=_EndpointObservation(dhcp_enabled=False),
        observation_after_arm=_EndpointObservation(dhcp_enabled=True),
        timeline=timeline,
    )
    outcome = _run(
        configuration=configuration, endpoints=endpoints,
        gate_clock=clock, gate_sleeper=clock.sleep,
        **_PAIRED_GATED, **kwargs,
    )
    return outcome, clock


def test_dhcp_is_armed_only_after_forwarding_was_observed():
    timeline: list[str] = []
    (result, _, configuration, call_control, endpoints, *_), _ = _gated_run(
        stp_sequence=[
            _stp("LIS"),   # the BEFORE snapshot
            _stp("LIS"), _stp("LRN"), _stp("FWD"),  # the gate's samples
            _stp("FWD"),   # the AFTER snapshot
        ],
        timeline=timeline,
    )

    first_arm = timeline.index("arm:MCP-VOICEAB-test01_P1")
    gate_reads = [i for i, item in enumerate(timeline) if item == "stp_read"]
    # The before snapshot and every gate sample precede the first arm; only
    # the AFTER snapshot follows it.
    assert [i for i in gate_reads if i < first_arm][3] == gate_reads[3]
    assert len([i for i in gate_reads if i < first_arm]) == 4
    # Pre-arm reads precede the arm; the post-arm reads follow it.
    pre_reads = [i for i, item in enumerate(timeline)
                 if item.startswith("endpoint_read:")]
    assert len([i for i in pre_reads if i < first_arm]) == 2
    assert result.acquisition_started is True
    assert result.acquisition_boundary == ""
    assert result.stp_gate is not None
    assert result.stp_gate.status == FORWARDING
    assert result.stp_gate.observed_states == ("LIS", "LRN", FORWARDING)
    assert endpoints.armed == [
        "MCP-VOICEAB-test01_P1", "MCP-VOICEAB-test01_P2",
    ]
    assert [item.dhcp_enabled_pre_arm for item in result.phones] == [NO, NO]
    assert [item.dhcp_enabled_post_arm for item in result.phones] == [YES, YES]
    assert [item.arm_call_accepted for item in result.phones] == [YES, YES]
    assert result.all_endpoint_arms_accepted == YES
    assert result.dhcp_flag_transition == "OBSERVED_OFF_TO_ON"
    assert result.dhcp_flag_transition_valid_for_experiment == YES
    assert result.fresh_7960_dhcp_transaction == (
        "NOT_INDEPENDENTLY_ESTABLISHED"
    )
    assert result.experiment == EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED


def test_a_gate_timeout_never_arms_and_names_the_boundary():
    (result, _, configuration, call_control, endpoints, *_), clock = _gated_run(
        stp_sequence=[_stp("LIS")],
    )

    assert endpoints.armed == []
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET
    )
    assert result.stp_gate.status == GATE_TIMEOUT
    assert result.causal_experiment_result == "STP_PRECONDITION_NOT_ESTABLISHED"
    assert result.outcome == UNOBSERVABLE


def test_a_phone_already_on_before_arming_fails_the_fresh_trigger_closed():
    endpoints = _Endpoints(
        observation=_EndpointObservation(dhcp_enabled=True),
    )
    (result, _, configuration, call_control, endpoints, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD")],
        endpoints=endpoints,
    )

    assert endpoints.armed == []
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
    )
    assert result.causal_experiment_result == "FRESH_DHCP_TRIGGER_UNPROVEN"
    assert [item.dhcp_enabled_pre_arm for item in result.phones] == [YES, YES]
    assert result.outcome == UNOBSERVABLE


def test_an_unreadable_pre_arm_flag_also_fails_the_trigger_closed():
    endpoints = _Endpoints(observation=None)
    (result, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD")],
        endpoints=endpoints,
    )

    assert endpoints.armed == []
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
    )
    assert [item.dhcp_enabled_pre_arm for item in result.phones] == [
        UNOBSERVABLE, UNOBSERVABLE,
    ]


def test_a_false_arm_aggregate_never_opens_the_acquisition_window():
    endpoints = _ContractEndpoints(accepted=(False, False))
    (result, _, _, call_control, endpoints, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
        endpoints=endpoints,
    )

    assert endpoints.armed == [
        "MCP-VOICEAB-test01_P1", "MCP-VOICEAB-test01_P2",
    ]
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
    )
    assert result.causal_experiment_result == "FRESH_DHCP_TRIGGER_UNPROVEN"
    assert result.all_endpoint_arms_accepted == NO


def test_one_rejected_arm_is_enough_to_withhold_acquisition():
    endpoints = _ContractEndpoints(accepted=(True, False))
    (result, _, _, call_control, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
        endpoints=endpoints,
    )

    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
    )
    assert [item.arm_call_accepted for item in result.phones] == [YES, NO]
    assert result.all_endpoint_arms_accepted == NO


def test_an_arm_exception_is_not_retried_and_never_opens_acquisition():
    class _SecondArmRaises(_ContractEndpoints):
        def configure_endpoint_dhcp(self, device_name, interface):
            if device_name.endswith("P2"):
                raise RuntimeError("typed endpoint channel unavailable")
            return super().configure_endpoint_dhcp(device_name, interface)

    endpoints = _SecondArmRaises()
    (result, _, _, call_control, endpoints, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
        endpoints=endpoints,
    )

    assert endpoints.armed == ["MCP-VOICEAB-test01_P1"]
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
    )
    assert [item.arm_call_accepted for item in result.phones] == [YES, NO]


def test_post_arm_yes_no_is_not_a_valid_dhcp_flag_transition():
    endpoints = _ContractEndpoints(post=(True, False))
    (result, _, _, call_control, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
        endpoints=endpoints,
    )

    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
    )
    assert [item.dhcp_enabled_post_arm for item in result.phones] == [YES, NO]
    assert result.dhcp_flag_transition == "NOT_OBSERVED"


def test_post_arm_yes_unobservable_is_not_a_valid_dhcp_flag_transition():
    endpoints = _ContractEndpoints(post=(True, None))
    (result, _, _, call_control, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
        endpoints=endpoints,
    )

    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
    )
    assert [item.dhcp_enabled_post_arm for item in result.phones] == [
        YES, UNOBSERVABLE,
    ]
    assert result.dhcp_flag_transition == UNOBSERVABLE


def test_identity_invalid_gate_cannot_reuse_prior_fwd_or_arm_dhcp():
    endpoints = _ContractEndpoints()
    (result, _, _, call_control, endpoints, *_), _ = _gated_run(
        # The BEFORE snapshot is valid and FWD, but every decision read is
        # non-authoritative through the bound.  The prior state cannot leak
        # across the gate and authorize acquisition.
        stp_sequence=[_stp("FWD"), None],
        endpoints=endpoints,
        gate_timeout_seconds=4.0,
        gate_interval_seconds=2.0,
    )

    assert result.stp_gate.status == GATE_TIMEOUT
    assert result.stp_gate.observed_states == (UNOBSERVABLE,)
    assert result.acquisition_started is False
    assert endpoints.armed == []
    assert call_control.expectations == []


def test_the_gated_mode_still_applies_no_edge_policy():
    (result, _, configuration, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
    )

    assert [
        action for action in configuration.applied
        if type(action).__name__ == "ConfigureStpEdgePort"
    ] == []
    assert result.portfast == "NOT_APPLIED"


def test_ungated_runs_keep_their_shape_and_carry_no_gate():
    result, _, configuration, _, endpoints, *_ = _run()
    paired, *_ = _run(phone_access_vlans=_PAIRED)

    assert result.stp_gate is None
    assert result.acquisition_started is True
    assert result.acquisition_boundary == ""
    assert result.experiment == EXPERIMENT_UNIFORM_BASELINE
    assert result.causal_experiment_result == "NOT_FWD_GATED"
    assert paired.experiment == EXPERIMENT_PAIRED_ACCESS_VLAN
    assert paired.causal_experiment_result == "NOT_FWD_GATED"
    # The default arming order is untouched: armed before the window, without
    # any pre-arm read.
    assert endpoints.armed == [
        "MCP-VOICEAB-test01_P1", "MCP-VOICEAB-test01_P2",
    ]


def _gated_result(control_addressed, intervention_addressed):
    def phone(vlan, ipv4):
        return PositiveVoicePhoneOutcome(
            access_vlan_expected=vlan,
            dhcp_enabled_pre_arm=NO,
            arm_call_accepted=YES,
            dhcp_enabled_post_arm=YES,
            ipv4=ipv4,
            address_channel=True,
        )

    return PositiveVoiceSliceResult(
        experiment=EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED,
        stp_gate=StpForwardingGate(status=FORWARDING),
        acquisition_started=True,
        phones=(
            phone(DATA_VLAN_ID, "10.93.0.10" if control_addressed else ""),
            phone(VOICE_VLAN_ID, "10.93.0.11" if intervention_addressed else ""),
        ),
    )


def test_the_causal_matrix_requires_the_validated_run10_preconditions():
    result = PositiveVoiceSliceResult(
        experiment=EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED,
        acquisition_started=True,
        phones=_gated_result(False, True).phones,
    )

    assert result.causal_experiment_result == (
        "STP_PRECONDITION_NOT_ESTABLISHED"
    )


def test_the_causal_matrix_requires_valid_arm_and_flag_evidence():
    result = PositiveVoiceSliceResult(
        experiment=EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED,
        stp_gate=StpForwardingGate(status=FORWARDING),
        acquisition_started=True,
        phones=(
            PositiveVoicePhoneOutcome(
                access_vlan_expected=DATA_VLAN_ID,
                ipv4="",
                address_channel=True,
            ),
            PositiveVoicePhoneOutcome(
                access_vlan_expected=VOICE_VLAN_ID,
                ipv4="10.93.0.11",
                address_channel=True,
            ),
        ),
    )

    assert result.causal_experiment_result == "FRESH_DHCP_TRIGGER_UNPROVEN"


def test_an_intervention_address_retains_the_strong_causal_classification():
    assert _gated_result(False, True).causal_experiment_result == (
        "ACCESS_VLAN_DHCP_CAUSAL_EFFECT_OBSERVED"
    )


def test_no_addresses_after_the_gate_does_not_claim_no_dhcp_effect():
    assert _gated_result(False, False).causal_experiment_result == (
        "NO_ADDRESS_AFTER_FWD_AND_DHCP_FLAG_TRANSITION"
    )


def test_both_addresses_stop_on_run9_repeatability():
    assert _gated_result(True, True).causal_experiment_result == (
        "RUN9_FAILURE_NOT_REPRODUCED"
    )


def test_the_reversed_half_keeps_the_transaction_observability_caveat():
    assert _gated_result(True, False).causal_experiment_result == (
        "OBSERVED_REVERSED_ADDRESS_OUTCOME"
    )


def test_an_unreadable_half_is_divergent_not_a_case():
    unread = PositiveVoiceSliceResult(
        experiment=EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED,
        stp_gate=StpForwardingGate(status=FORWARDING),
        acquisition_started=True,
        phones=(
            PositiveVoicePhoneOutcome(
                access_vlan_expected=DATA_VLAN_ID,
                dhcp_enabled_pre_arm=NO,
                arm_call_accepted=YES,
                dhcp_enabled_post_arm=YES,
                ipv4="",
                address_channel=True,
            ),
            PositiveVoicePhoneOutcome(
                access_vlan_expected=VOICE_VLAN_ID,
                dhcp_enabled_pre_arm=NO,
                arm_call_accepted=YES,
                dhcp_enabled_post_arm=YES,
                ipv4="",
                address_channel=False,
            ),
        ),
    )

    assert unread.causal_experiment_result == "PARTIAL_OR_DIVERGENT"


def test_the_endpoint_outcome_and_the_causal_result_stay_distinct():
    # Run 9's exact split: the ENDPOINT outcome may read SAME_FAILURE while the
    # CAUSAL result of a gated run is a boundary.  One field never answers for
    # the other.
    boundary = PositiveVoiceSliceResult(
        experiment=EXPERIMENT_PAIRED_ACCESS_VLAN_FWD_GATED,
        acquisition_started=False,
        acquisition_boundary=ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET,
    )

    assert boundary.outcome == UNOBSERVABLE
    assert boundary.causal_experiment_result == (
        "STP_PRECONDITION_NOT_ESTABLISHED"
    )


def test_the_paired_journal_names_each_ports_access_vlan():
    result, *_ = _run(phone_access_vlans=_PAIRED)

    milestone = next(
        item for item in result.lifecycle
        if item.name == "WHEN_ACCESS_VLAN_APPLIED"
    )
    assert milestone.detail == "FastEthernet0/1:931, FastEthernet0/2:930"


def test_the_default_journal_still_names_the_uniform_mapping():
    result, *_ = _run()

    milestone = next(
        item for item in result.lifecycle
        if item.name == "WHEN_ACCESS_VLAN_APPLIED"
    )
    assert milestone.detail == "FastEthernet0/1:931, FastEthernet0/2:931"


def test_the_live_serializer_publishes_the_gate_and_the_two_result_concepts():
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(encoding="utf-8")

    assert '"experiment": result.experiment' in source
    assert '"causal_experiment_result": result.causal_experiment_result' in source
    assert '"acquisition_started": result.acquisition_started' in source
    assert '"acquisition_boundary": result.acquisition_boundary' in source
    assert '"all_endpoint_arms_accepted": result.all_endpoint_arms_accepted' in source
    assert '"dhcp_flag_transition": result.dhcp_flag_transition' in source
    assert 'result.dhcp_flag_transition_valid_for_experiment' in source
    assert '"fresh_7960_dhcp_transaction": result.fresh_7960_dhcp_transaction' in source
    assert '"dhcp_enabled_pre_arm": item.dhcp_enabled_pre_arm' in source
    assert '"arm_call_accepted": item.arm_call_accepted' in source
    assert '"dhcp_enabled_post_arm": item.dhcp_enabled_post_arm' in source
    assert "--paired-access-vlan-fwd-gated" in source


# --- next causal experiment: exact phone-SVI DHCP client retrigger ----------


@dataclass(frozen=True)
class _SviDhcpMutation:
    requested_enabled: bool
    accepted: bool
    before_enabled: bool | None
    after_enabled: bool | None


class _SviTransitionEndpoints(_Endpoints):
    def __init__(
        self, *, initial=(True, True), disable_accepted=True,
        enable_accepted=True, control_after_intervention=None, timeline=None,
        pre_addresses=("", ""), pre_svi_present=(True, True),
        pre_address_channels=(True, True),
    ):
        super().__init__(timeline=timeline)
        self.state = {
            "MCP-VOICEAB-test01_P1": initial[0],
            "MCP-VOICEAB-test01_P2": initial[1],
        }
        self.disable_accepted = disable_accepted
        self.enable_accepted = enable_accepted
        self.control_after_intervention = control_after_intervention
        self.pre_addresses = pre_addresses
        self.pre_svi_present = pre_svi_present
        self.pre_address_channels = pre_address_channels
        self.state_calls: list[tuple[str, str, bool]] = []

    @staticmethod
    def _phone_index(device_name):
        return 0 if device_name.endswith("P1") else 1

    def read_endpoint_address(self, device_name, interface):
        if self.timeline is not None:
            self.timeline.append(f"endpoint_read:{device_name}")
        self.read_interfaces.append(interface)
        index = self._phone_index(device_name)
        return _EndpointObservation(
            present=self.pre_svi_present[index],
            ipv4=self.pre_addresses[index],
            address_channel=self.pre_address_channels[index],
            dhcp_enabled=self.state[device_name],
        )

    def set_endpoint_dhcp_client_state(self, device_name, interface, enabled):
        if self.timeline is not None:
            self.timeline.append(f"svi_dhcp:{device_name}:{enabled}")
        self.state_calls.append((device_name, interface, enabled))
        before = self.state[device_name]
        accepted = self.enable_accepted if enabled else self.disable_accepted
        if accepted:
            self.state[device_name] = enabled
            if (
                device_name.endswith("P2") and enabled
                and self.control_after_intervention is not None
            ):
                self.state["MCP-VOICEAB-test01_P1"] = (
                    self.control_after_intervention
                )
        return _SviDhcpMutation(
            requested_enabled=enabled,
            accepted=accepted,
            before_enabled=before,
            after_enabled=self.state[device_name],
        )


_SVI_RETRIGGER = dict(
    phone_access_vlans=(VOICE_VLAN_ID, VOICE_VLAN_ID),
    phone_svi_dhcp_retrigger=True,
)

_RETRIGGER_SUCCESS_STP = (
    _stp_both("LIS", "LIS"),  # before snapshot
    _stp_both("FWD", "FWD"),  # fresh control gate read
    _stp_both("FWD", "FWD"),  # fresh intervention gate read
    _stp_both("FWD", "FWD"),  # after snapshot
)


def _svi_retrigger_run(*, stp_sequence, endpoints=None, timeline=None, **kwargs):
    clock = _Clock()
    endpoints = endpoints or _SviTransitionEndpoints(timeline=timeline)
    outcome = _run(
        configuration=_Configuration(
            stp_sequence=stp_sequence, timeline=timeline,
        ),
        endpoints=endpoints,
        gate_clock=clock,
        gate_sleeper=clock.sleep,
        **_SVI_RETRIGGER,
        **kwargs,
    )
    return outcome, clock


def test_phone_svi_retrigger_is_an_exclusive_gated_mode():
    with pytest.raises(ValueError, match="separate modes"):
        _qualifier(
            _Physical(_empty_workspace()), _Configuration(), _CallControl(),
            _SviTransitionEndpoints(), _ModeRuntime(),
            phone_access_vlans=(VOICE_VLAN_ID, VOICE_VLAN_ID),
            phone_dhcp_lifecycle=True,
            phone_svi_dhcp_retrigger=True,
        )


def test_phone_svi_retrigger_refuses_the_historical_asymmetric_shape():
    with pytest.raises(ValueError, match="symmetric"):
        _qualifier(
            _Physical(_empty_workspace()), _Configuration(), _CallControl(),
            _SviTransitionEndpoints(), _ModeRuntime(),
            phone_access_vlans=_PAIRED,
            phone_svi_dhcp_retrigger=True,
        )


def test_phone_svi_retrigger_cannot_mutate_before_authoritative_fwd():
    endpoints = _SviTransitionEndpoints()
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=[_stp_both("LIS", "FWD")], endpoints=endpoints,
        gate_timeout_seconds=4.0, gate_interval_seconds=2.0,
    )

    assert endpoints.state_calls == []
    assert endpoints.armed == []
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_STP_PRECONDITION_UNMET
    )


def test_phone_svi_retrigger_changes_only_intervention_yes_no_yes_after_fwd():
    timeline: list[str] = []
    endpoints = _SviTransitionEndpoints(timeline=timeline)
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP),
        endpoints=endpoints,
        timeline=timeline,
    )

    assert endpoints.state_calls == [
        ("MCP-VOICEAB-test01_P2", PHONE_ADDRESSING_INTERFACE, False),
        ("MCP-VOICEAB-test01_P2", PHONE_ADDRESSING_INTERFACE, True),
    ]
    assert endpoints.armed == []
    first_mutation = timeline.index(
        "svi_dhcp:MCP-VOICEAB-test01_P2:False"
    )
    assert len([
        item for item in timeline[:first_mutation] if item == "stp_read"
    ]) == 3
    assert call_control.expectations
    assert result.acquisition_started is True
    assert result.acquisition_boundary == ""
    assert result.experiment == EXPERIMENT_PHONE_SVI_DHCP_RETRIGGER
    assert result.control_stp_gate.forwarding_observed is True
    assert result.intervention_stp_gate.forwarding_observed is True
    for gate in (result.control_stp_gate, result.intervention_stp_gate):
        assert gate.terminal_executed == YES
        assert gate.terminal_fresh == YES
        assert gate.terminal_complete == YES
        assert gate.terminal_identity_provenance == "confirmed_unique"
    assert result.phone_svi_dhcp_transition_valid_for_experiment == YES
    assert result.voice_binding_ipv4s == ("10.93.0.10",)
    assert result.matching_intervention_binding == YES
    assert result.phone_svi_dhcp_transitions == (
        PhoneSviDhcpTransitionEvidence(
            phone="MCP-VOICEAB-test01_P2",
            control_phone="MCP-VOICEAB-test01_P1",
            control_pre_enabled=YES,
            control_post_enabled=YES,
            pre_enabled=YES,
            disable_before=YES,
            disable_accepted=YES,
            disabled_readback=NO,
            enable_before=NO,
            enable_accepted=YES,
            reenabled_readback=YES,
        ),
    )


def test_phone_svi_retrigger_retains_one_complete_pre_observation_per_phone():
    timeline: list[str] = []
    endpoints = _SviTransitionEndpoints(
        timeline=timeline,
        pre_addresses=("unassigned", "0.0.0.0"),
    )
    (result, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP),
        endpoints=endpoints,
        timeline=timeline,
    )

    first_mutation = timeline.index(
        "svi_dhcp:MCP-VOICEAB-test01_P2:False"
    )
    assert [
        item for item in timeline[:first_mutation]
        if item.startswith("endpoint_read:")
    ] == [
        "endpoint_read:MCP-VOICEAB-test01_P1",
        "endpoint_read:MCP-VOICEAB-test01_P2",
    ]
    assert [item.as_evidence() for item in result.pre_retrigger_endpoint_states] == [
        {
            "phone": "MCP-VOICEAB-test01_P1",
            "svi_present": YES,
            "address_channel": YES,
            "dhcp_enabled": YES,
            "ipv4": "unassigned",
            "addressed": NO,
        },
        {
            "phone": "MCP-VOICEAB-test01_P2",
            "svi_present": YES,
            "address_channel": YES,
            "dhcp_enabled": YES,
            "ipv4": "0.0.0.0",
            "addressed": NO,
        },
    ]
    assert result.pre_retrigger_address_baseline_valid == YES


@pytest.mark.parametrize(
    "pre_addresses",
    [
        ("10.93.0.10", ""),
        ("", "10.93.0.11"),
    ],
)
def test_pre_retrigger_address_already_present_blocks_p2_mutation(pre_addresses):
    endpoints = _SviTransitionEndpoints(pre_addresses=pre_addresses)
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP), endpoints=endpoints,
    )

    assert endpoints.state_calls == []
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        "ACQUISITION_NOT_STARTED_PRE_RETRIGGER_ADDRESS_BASELINE_UNPROVEN"
    )
    assert result.pre_retrigger_address_baseline_valid == NO
    assert result.causal_experiment_result == (
        "PRE_RETRIGGER_ACQUISITION_ALREADY_OCCURRED"
    )


@pytest.mark.parametrize(
    "pre_address_channels",
    [
        (False, True),
        (True, False),
        (None, True),
    ],
)
def test_unreadable_pre_retrigger_address_channel_blocks_p2_mutation(
    pre_address_channels,
):
    endpoints = _SviTransitionEndpoints(
        pre_address_channels=pre_address_channels,
    )
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP), endpoints=endpoints,
    )

    assert endpoints.state_calls == []
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        "ACQUISITION_NOT_STARTED_PRE_RETRIGGER_ADDRESS_BASELINE_UNPROVEN"
    )
    assert result.pre_retrigger_address_baseline_valid != YES


def test_unreadable_pre_retrigger_endpoint_observation_blocks_p2_mutation():
    class _UnreadableP2(_SviTransitionEndpoints):
        def read_endpoint_address(self, device_name, interface):
            if device_name.endswith("P2"):
                raise RuntimeError("endpoint channel unavailable")
            return super().read_endpoint_address(device_name, interface)

    endpoints = _UnreadableP2()
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP), endpoints=endpoints,
    )

    assert endpoints.state_calls == []
    assert call_control.expectations == []
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_PRE_RETRIGGER_ADDRESS_BASELINE_UNPROVEN
    )
    p2, = (
        item for item in result.pre_retrigger_endpoint_states
        if item.phone.endswith("P2")
    )
    assert p2.address_channel == UNOBSERVABLE
    assert p2.dhcp_enabled == UNOBSERVABLE
    assert result.pre_retrigger_address_baseline_valid == UNOBSERVABLE


@pytest.mark.parametrize(
    "pre_svi_present",
    [
        (False, True),
        (True, False),
        (None, True),
    ],
)
def test_unproven_pre_retrigger_svi_presence_blocks_p2_mutation(
    pre_svi_present,
):
    endpoints = _SviTransitionEndpoints(pre_svi_present=pre_svi_present)
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP), endpoints=endpoints,
    )

    assert endpoints.state_calls == []
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_PRE_RETRIGGER_ADDRESS_BASELINE_UNPROVEN
    )
    assert result.pre_retrigger_address_baseline_valid != YES


def test_dhcp_yes_and_observed_no_address_authorizes_only_p2_transition():
    timeline: list[str] = []
    endpoints = _SviTransitionEndpoints(timeline=timeline)
    (result, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP),
        endpoints=endpoints,
        timeline=timeline,
    )

    first_mutation = timeline.index(
        "svi_dhcp:MCP-VOICEAB-test01_P2:False"
    )
    assert timeline[:first_mutation][-2:] == [
        "endpoint_read:MCP-VOICEAB-test01_P1",
        "endpoint_read:MCP-VOICEAB-test01_P2",
    ]
    assert result.pre_retrigger_address_baseline_valid == YES
    assert result.acquisition_started is True
    assert all(not call[0].endswith("P1") for call in endpoints.state_calls)


def test_phone_svi_retrigger_uses_identical_access_and_voice_vlan_shape():
    (result, _, configuration, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP),
    )

    access = [
        item for item in configuration.applied
        if type(item).__name__ == "ConfigureAccessPort"
    ]
    assert [
        (item.interface, item.data_vlan_id, item.voice_vlan_id)
        for item in access
    ] == [
        ("FastEthernet0/1", VOICE_VLAN_ID, VOICE_VLAN_ID),
        ("FastEthernet0/2", VOICE_VLAN_ID, VOICE_VLAN_ID),
    ]
    assert [item.access_vlan_expected for item in result.phones] == [
        VOICE_VLAN_ID, VOICE_VLAN_ID,
    ]


def test_run11_keeps_the_historical_asymmetric_network_shape():
    (result, _, configuration, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
    )

    access = [
        item for item in configuration.applied
        if type(item).__name__ == "ConfigureAccessPort"
    ]
    assert [item.data_vlan_id for item in access] == [
        DATA_VLAN_ID, VOICE_VLAN_ID,
    ]
    assert result.control_stp_gate is None
    assert result.intervention_stp_gate is None


def test_intervention_gate_failure_after_control_fwd_prevents_mutation():
    endpoints = _SviTransitionEndpoints()
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=[
            _stp_both("LIS", "LIS"),
            _stp_both("FWD", "LIS"),
            _stp_both("FWD", "LIS"),
        ],
        endpoints=endpoints,
        gate_timeout_seconds=4.0,
        gate_interval_seconds=2.0,
    )

    assert result.control_stp_gate.forwarding_observed is True
    assert result.intervention_stp_gate.forwarding_observed is False
    assert endpoints.state_calls == []
    assert call_control.expectations == []
    assert result.acquisition_started is False


def test_control_gate_failure_never_reuses_intervention_fwd_or_mutates():
    endpoints = _SviTransitionEndpoints()
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=[_stp_both("LIS", "FWD")],
        endpoints=endpoints,
        gate_timeout_seconds=4.0,
        gate_interval_seconds=2.0,
    )

    assert result.control_stp_gate.forwarding_observed is False
    assert result.intervention_stp_gate is None
    assert endpoints.state_calls == []
    assert call_control.expectations == []


@pytest.mark.parametrize("initial", [(False, True), (True, False), (None, True)])
def test_phone_svi_retrigger_requires_both_phones_already_enabled(initial):
    endpoints = _SviTransitionEndpoints(initial=initial)
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP), endpoints=endpoints,
    )

    assert endpoints.state_calls == []
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_PRE_RETRIGGER_ADDRESS_BASELINE_UNPROVEN
    )


def test_failed_disable_is_not_followed_by_enable_or_an_acquisition_window():
    endpoints = _SviTransitionEndpoints(disable_accepted=False)
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP), endpoints=endpoints,
    )

    assert [call[2] for call in endpoints.state_calls] == [False]
    assert call_control.expectations == []
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_SVI_DHCP_TRANSITION_UNPROVEN
    )
    assert result.phone_svi_dhcp_transition_valid_for_experiment == NO


def test_failed_reenable_never_opens_the_acquisition_window():
    endpoints = _SviTransitionEndpoints(enable_accepted=False)
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP), endpoints=endpoints,
    )

    assert [call[2] for call in endpoints.state_calls] == [False, True]
    assert call_control.expectations == []
    assert result.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_SVI_DHCP_TRANSITION_UNPROVEN
    )
    assert result.phone_svi_dhcp_transition_valid_for_experiment == NO


def test_unexpected_control_dhcp_change_blocks_isolated_interpretation():
    endpoints = _SviTransitionEndpoints(control_after_intervention=False)
    (result, _, _, call_control, *_), _ = _svi_retrigger_run(
        stp_sequence=list(_RETRIGGER_SUCCESS_STP), endpoints=endpoints,
    )

    transition, = result.phone_svi_dhcp_transitions
    assert transition.control_pre_enabled == YES
    assert transition.control_post_enabled == NO
    assert all(not call[0].endswith("P1") for call in endpoints.state_calls)
    assert call_control.expectations == []
    assert result.acquisition_started is False
    assert result.acquisition_boundary == (
        "ACQUISITION_NOT_STARTED_CONTROL_DHCP_INVARIANT_UNPROVEN"
    )
    assert result.causal_experiment_result == (
        "CONTROL_DHCP_INVARIANT_UNPROVEN"
    )


def test_default_and_run11_modes_have_no_phone_svi_transition_evidence():
    default, *_ = _run()
    (run11, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD")],
    )

    assert default.phone_svi_dhcp_transitions == ()
    assert run11.phone_svi_dhcp_transitions == ()
    assert default.pre_retrigger_endpoint_states == ()
    assert run11.pre_retrigger_endpoint_states == ()
    assert default.control_stp_gate is default.intervention_stp_gate is None
    assert run11.control_stp_gate is run11.intervention_stp_gate is None


def test_phone_svi_retrigger_causal_matrix_keeps_control_and_intervention_apart():
    transition = PhoneSviDhcpTransitionEvidence(
        phone="P2", control_phone="P1", control_pre_enabled=YES,
        control_post_enabled=YES, pre_enabled=YES, disable_before=YES,
        disable_accepted=YES, disabled_readback=NO, enable_before=NO,
        enable_accepted=YES, reenabled_readback=YES,
    )

    def result(control, intervention):
        return PositiveVoiceSliceResult(
            experiment=EXPERIMENT_PHONE_SVI_DHCP_RETRIGGER,
            stp_gate=StpForwardingGate(status=FORWARDING),
            control_stp_gate=StpForwardingGate(status=FORWARDING),
            intervention_stp_gate=StpForwardingGate(status=FORWARDING),
            acquisition_started=True,
            pre_retrigger_endpoint_states=(
                PhonePreRetriggerEndpointState(
                    phone="P1", svi_present=YES, address_channel=YES,
                    dhcp_enabled=YES,
                ),
                PhonePreRetriggerEndpointState(
                    phone="P2", svi_present=YES, address_channel=YES,
                    dhcp_enabled=YES,
                ),
            ),
            phone_svi_dhcp_transitions=(transition,),
            phones=(
                PositiveVoicePhoneOutcome(
                    phone_name="P1",
                    access_vlan_expected=VOICE_VLAN_ID,
                    ipv4="10.93.0.10" if control else "",
                    address_channel=True,
                ),
                PositiveVoicePhoneOutcome(
                    phone_name="P2",
                    access_vlan_expected=VOICE_VLAN_ID,
                    ipv4="10.93.0.11" if intervention else "",
                    address_channel=True,
                ),
            ),
        )

    assert result(False, True).causal_experiment_result == (
        "PHONE_SVI_DHCP_RETRIGGER_EFFECT_OBSERVED"
    )
    assert result(False, False).causal_experiment_result == (
        "NO_ADDRESS_AFTER_PHONE_SVI_DHCP_RETRIGGER"
    )
    assert result(True, True).causal_experiment_result == (
        "SHARED_LATE_ACQUISITION_NOT_ISOLATED"
    )
    assert result(True, False).causal_experiment_result == (
        "CONTROL_ONLY_ADDRESS_OBSERVED"
    )


def test_runner_exposes_only_the_typed_svi_retrigger_mode():
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )

    assert "--phone-svi-dhcp-retrigger" in source
    assert "set_endpoint_dhcp_client_state" in source
    assert '"phone_svi_dhcp_transitions"' in source
    assert '"pre_retrigger_endpoint_states"' in source
    assert '"pre_retrigger_address_baseline_valid"' in source
    assert '"voice_binding_ipv4s"' in source
    assert '"matching_intervention_binding"' in source
    assert '"control_stp_gate"' in source
    assert '"intervention_stp_gate"' in source
    assert "setDhcpClientFlag" not in source


def test_positive_voice_live_enforces_governed_preflight_in_mutating_process():
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )

    assert "ImportIsolationPreflight(GOVERNED_ROOT).ensure_isolated()" in source
    assert "read_git_repository_state(GOVERNED_ROOT)" in source
    assert '["git", "status", "--porcelain"]' in source
    assert '_git_output("rev-parse", "@{upstream}")' in source
    assert "packet_tracer_process_error(" in source
    assert "baseline = physical.observe_workspace()" in source
    assert "baseline.safe_for_disposable_mutation" in source
    assert "preflight_mode = mode_runtime.read_simulation_state()" in source
    assert "independent_final = physical.observe_workspace()" in source
    assert "independent_mode = mode_runtime.read_simulation_state()" in source
    assert "physical_workspace_restoration_matches(" in source


# --- phone DHCP lifecycle qualification preparation -------------------------


class _LifecycleEndpoints(_Endpoints):
    """One existing endpoint/SVI read per phone at each lifecycle milestone."""

    def __init__(
        self, flags, addresses=None, device_flags=None,
        device_addresses=None, svi_present=None,
    ):
        super().__init__()
        self._flags = tuple(flags)
        self._addresses = tuple(addresses or (None,) * len(self._flags))
        self._device_flags = tuple(
            device_flags or (None,) * len(self._flags)
        )
        self._device_addresses = tuple(
            device_addresses or (None,) * len(self._flags)
        )
        self._svi_present = tuple(
            svi_present or (None,) * len(self._flags)
        )

    def configure_endpoint_dhcp(self, device_name, interface):
        raise AssertionError("the observational lifecycle must never arm DHCP")

    def read_endpoint_address(self, device_name, interface):
        self.read_interfaces.append(interface)
        index = len(self.read_interfaces) - 1
        flag = self._flags[index]
        address = self._addresses[index]
        device_flag = self._device_flags[index]
        device_address = self._device_addresses[index]
        present = self._svi_present[index]
        if (
            flag is None and address is None and device_flag is None
            and device_address is None and present is None
        ):
            return None
        return _EndpointObservation(
            present=present,
            ipv4=address or "",
            address_channel=address is not None,
            dhcp_enabled=flag,
            device_ipv4=device_address or "",
            device_dhcp_enabled=device_flag,
        )


def _milestone_flags(values):
    """Expand one value per milestone into the two phone reads at that point."""
    return tuple(value for value in values for _ in range(2))


def _lifecycle_run(
    values, *, addresses=None, device_values=None, device_addresses=None,
    svi_present=None,
):
    endpoints = _LifecycleEndpoints(
        _milestone_flags(values),
        _milestone_flags(addresses) if addresses is not None else None,
        _milestone_flags(device_values) if device_values is not None else None,
        _milestone_flags(device_addresses)
        if device_addresses is not None else None,
        _milestone_flags(svi_present) if svi_present is not None else None,
    )
    outcome = _run(
        configuration=_Configuration(
            stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
        ),
        endpoints=endpoints,
        phone_access_vlans=_PAIRED,
        phone_dhcp_lifecycle=True,
    )
    return outcome, endpoints


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        (
            (True, True, True, True, True, True, True),
            "AFTER_PHONE_CREATION",
        ),
        (
            (False, True, True, True, True, True, True),
            "AFTER_PHYSICAL_LINK_CREATION",
        ),
        (
            (False, False, True, True, True, True, True),
            "AFTER_NETWORK_CONFIGURATION_BATCH",
        ),
        (
            (False, False, False, True, True, True, True),
            "AFTER_VOICE_CME_CONFIGURATION",
        ),
        (
            (False, False, False, False, False, False, True),
            "IMMEDIATELY_AFTER_AUTHORITATIVE_FWD",
        ),
        (
            (False, False, False, False, False, False, False),
            "NOT_ESTABLISHED",
        ),
    ),
)
def test_dhcp_lifecycle_derives_the_first_observed_yes(values, expected):
    (result, *_), _ = _lifecycle_run(values)

    assert result.first_observed_svi_dhcp_enabled_milestone == expected


def test_run12_lifecycle_keeps_its_historical_shape_and_single_gate():
    (result, _, configuration, *_), _ = _lifecycle_run((True,) * 7)

    access = [
        item for item in configuration.applied
        if type(item).__name__ == "ConfigureAccessPort"
    ]
    assert [item.data_vlan_id for item in access] == [
        DATA_VLAN_ID, VOICE_VLAN_ID,
    ]
    assert result.stp_gate.forwarding_observed is True
    assert result.control_stp_gate is None
    assert result.intervention_stp_gate is None


def test_dhcp_lifecycle_ignores_unobservable_rows_before_a_later_yes():
    (result, *_), _ = _lifecycle_run(
        (None, None, None, True, True, True, True),
    )

    assert result.first_observed_svi_dhcp_enabled_milestone == (
        "AFTER_VOICE_CME_CONFIGURATION"
    )
    assert result.svi_dhcp_enabled_before_fwd == YES
    early = result.phone_dhcp_lifecycle[:6]
    assert {item.svi_dhcp_enabled for item in early} == {UNOBSERVABLE}
    assert {item.svi_ipv4 for item in early} == {UNOBSERVABLE}


def test_first_enabled_derivation_uses_milestone_order_and_only_observed_yes():
    result = PositiveVoiceSliceResult(phone_dhcp_lifecycle=(
        PhoneDhcpLifecycleEvidence(
            milestone="IMMEDIATELY_BEFORE_STP_FWD_GATE",
            phone="P1", svi_dhcp_enabled=YES,
        ),
        PhoneDhcpLifecycleEvidence(
            milestone="AFTER_PHONE_CREATION",
            phone="P1", svi_dhcp_enabled=UNOBSERVABLE,
        ),
        PhoneDhcpLifecycleEvidence(
            milestone="AFTER_PHYSICAL_LINK_CREATION",
            phone="P1", svi_dhcp_enabled=YES,
        ),
    ))

    assert result.first_observed_svi_dhcp_enabled_milestone == (
        "AFTER_PHYSICAL_LINK_CREATION"
    )


def test_dhcp_enabled_before_fwd_is_yes_when_any_earlier_read_says_yes():
    (result, *_), _ = _lifecycle_run(
        (False, False, False, True, True, True, True),
    )

    assert result.svi_dhcp_enabled_before_fwd == YES


def test_dhcp_enabled_before_fwd_is_no_when_all_prior_reads_stay_no():
    (result, *_), _ = _lifecycle_run(
        (False, False, False, False, False, False, True),
    )

    assert result.svi_dhcp_enabled_before_fwd == NO


def test_dhcp_enabled_before_fwd_fails_closed_across_an_unobservable_gap():
    (result, *_), _ = _lifecycle_run(
        (None, False, False, False, False, False, True),
    )

    assert result.svi_dhcp_enabled_before_fwd == UNOBSERVABLE


def test_same_read_retains_device_dhcp_independently_from_svi_dhcp():
    (result, *_), endpoints = _lifecycle_run(
        (False,) * 7,
        device_values=(True,) * 7,
        addresses=("",) * 7,
        device_addresses=("10.93.0.50",) * 7,
        svi_present=(True,) * 7,
    )

    first = result.phone_dhcp_lifecycle[0]
    assert first.svi_present == YES
    assert first.svi_dhcp_enabled == NO
    assert first.device_dhcp_enabled == YES
    assert first.svi_ipv4 == "NONE"
    assert first.device_ipv4 == "10.93.0.50"
    assert first.as_evidence() == {
        "milestone": "AFTER_PHONE_CREATION",
        "phone": "MCP-VOICEAB-test01_P1",
        "svi_present": YES,
        "svi_dhcp_enabled": NO,
        "device_dhcp_enabled": YES,
        "svi_ipv4": "NONE",
        "device_ipv4": "10.93.0.50",
        "evidence_authority": UNOBSERVABLE,
    }
    assert len(endpoints.read_interfaces) == 14


def test_svi_unobservable_and_device_yes_remain_separate_facts():
    (result, *_), _ = _lifecycle_run(
        (None,) * 7,
        device_values=(True,) * 7,
    )

    first = result.phone_dhcp_lifecycle[0]
    assert first.svi_dhcp_enabled == UNOBSERVABLE
    assert first.device_dhcp_enabled == YES
    assert result.first_observed_svi_dhcp_enabled_milestone_by_phone == {
        "MCP-VOICEAB-test01_P1": "NOT_ESTABLISHED",
        "MCP-VOICEAB-test01_P2": "NOT_ESTABLISHED",
    }
    assert result.first_observed_device_dhcp_enabled_milestone_by_phone == {
        "MCP-VOICEAB-test01_P1": "AFTER_PHONE_CREATION",
        "MCP-VOICEAB-test01_P2": "AFTER_PHONE_CREATION",
    }


def test_control_and_intervention_keep_different_first_enabled_milestones():
    svi = tuple(
        value
        for pair in zip(
            (True, True, True, True, True, True, True),
            (False, False, True, True, True, True, True),
        )
        for value in pair
    )
    device = tuple(
        value
        for pair in zip(
            (False, False, False, True, True, True, True),
            (False, False, False, False, True, True, True),
        )
        for value in pair
    )
    endpoints = _LifecycleEndpoints(svi, device_flags=device)
    result, *_ = _run(
        configuration=_Configuration(
            stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
        ),
        endpoints=endpoints,
        phone_access_vlans=_PAIRED,
        phone_dhcp_lifecycle=True,
    )

    assert result.first_observed_svi_dhcp_enabled_milestone_by_phone == {
        "MCP-VOICEAB-test01_P1": "AFTER_PHONE_CREATION",
        "MCP-VOICEAB-test01_P2": "AFTER_NETWORK_CONFIGURATION_BATCH",
    }
    assert result.first_observed_device_dhcp_enabled_milestone_by_phone == {
        "MCP-VOICEAB-test01_P1": "AFTER_VOICE_CME_CONFIGURATION",
        "MCP-VOICEAB-test01_P2": "AFTER_REALTIME_VERIFICATION",
    }
    assert result.first_observed_svi_dhcp_enabled_milestone == "MIXED"
    assert result.first_observed_device_dhcp_enabled_milestone == "MIXED"


def test_per_phone_before_fwd_derivations_fail_closed_only_for_the_gapped_phone():
    svi = tuple(
        value
        for pair in zip(
            (None, False, False, False, False, False, True),
            (False, False, False, False, False, False, True),
        )
        for value in pair
    )
    device = tuple(
        value
        for pair in zip(
            (False, False, False, False, False, False, True),
            (None, False, False, False, False, False, True),
        )
        for value in pair
    )
    endpoints = _LifecycleEndpoints(svi, device_flags=device)
    result, *_ = _run(
        configuration=_Configuration(
            stp_sequence=[_stp("LIS"), _stp("FWD"), _stp("FWD")],
        ),
        endpoints=endpoints,
        phone_access_vlans=_PAIRED,
        phone_dhcp_lifecycle=True,
    )

    assert result.svi_dhcp_enabled_before_fwd_by_phone == {
        "MCP-VOICEAB-test01_P1": UNOBSERVABLE,
        "MCP-VOICEAB-test01_P2": NO,
    }
    assert result.device_dhcp_enabled_before_fwd_by_phone == {
        "MCP-VOICEAB-test01_P1": NO,
        "MCP-VOICEAB-test01_P2": UNOBSERVABLE,
    }
    assert result.svi_dhcp_enabled_before_fwd == "MIXED"
    assert result.device_dhcp_enabled_before_fwd == "MIXED"


def test_network_configuration_milestone_names_the_whole_existing_batch():
    (result, *_), _ = _lifecycle_run((False,) * 7)

    assert "AFTER_NETWORK_CONFIGURATION_BATCH" in (
        item.milestone for item in result.phone_dhcp_lifecycle
    )
    assert "AFTER_ACCESS_VOICE_VLAN_CONFIGURATION" not in (
        item.milestone for item in result.phone_dhcp_lifecycle
    )
    source = Path(
        "src/packet_tracer_mcp/application/use_cases/qualify_positive_voice_slice.py"
    ).read_text(encoding="utf-8")
    handoff = Path("handoff.md").read_text(encoding="utf-8")
    assert "AFTER_ACCESS_VOICE_VLAN_CONFIGURATION" not in source
    assert "AFTER_ACCESS_VOICE_VLAN_CONFIGURATION" not in handoff
    assert "full network configuration batch" in handoff


def test_lifecycle_diagnostic_is_read_only_bounded_and_retains_address_shape():
    addresses = (None, "", "0.0.0.0", "10.93.0.10", "", "", "")
    (result, _, _, call_control, *_), endpoints = _lifecycle_run(
        (None, False, False, True, True, True, True),
        addresses=addresses,
    )

    assert result.experiment == EXPERIMENT_PHONE_DHCP_LIFECYCLE
    assert result.causal_experiment_result == (
        "NOT_APPLICABLE_OBSERVATIONAL_DIAGNOSTIC"
    )
    assert result.acquisition_started is False
    assert call_control.expectations == []
    assert endpoints.armed == []
    assert endpoints.read_interfaces == [
        PHONE_ADDRESSING_INTERFACE
    ] * (len(PHONE_DHCP_LIFECYCLE_MILESTONES) * 2)
    assert [
        item.milestone for item in result.phone_dhcp_lifecycle[::2]
    ] == list(PHONE_DHCP_LIFECYCLE_MILESTONES)
    assert [
        item.svi_ipv4 for item in result.phone_dhcp_lifecycle[::2]
    ] == [
        UNOBSERVABLE, "NONE", "0.0.0.0", "10.93.0.10",
        "NONE", "NONE", "NONE",
    ]
    assert {
        item.evidence_authority for item in result.phone_dhcp_lifecycle
    } == {UNOBSERVABLE}
    assert result.fresh_7960_dhcp_transaction == (
        "NOT_INDEPENDENTLY_ESTABLISHED"
    )


def test_lifecycle_retains_unobservable_post_fwd_rows_when_gate_is_not_met():
    clock = _Clock()
    endpoints = _LifecycleEndpoints(_milestone_flags((False,) * 7))
    result, *_ = _run(
        configuration=_Configuration(stp_sequence=[_stp("LIS")]),
        endpoints=endpoints,
        phone_access_vlans=_PAIRED,
        phone_dhcp_lifecycle=True,
        gate_clock=clock,
        gate_sleeper=clock.sleep,
        gate_timeout_seconds=0.0,
    )

    post_fwd = [
        item for item in result.phone_dhcp_lifecycle
        if item.milestone == "IMMEDIATELY_AFTER_AUTHORITATIVE_FWD"
    ]
    assert len(post_fwd) == 2
    assert {item.svi_dhcp_enabled for item in post_fwd} == {UNOBSERVABLE}
    assert len(endpoints.read_interfaces) == 12
    assert result.svi_dhcp_enabled_before_fwd == UNOBSERVABLE


def test_default_and_run11_modes_do_not_collect_lifecycle_or_change_arming():
    default_endpoints = _Endpoints()
    default, *_ = _run(endpoints=default_endpoints)
    gated_endpoints = _Endpoints(
        observation=_EndpointObservation(dhcp_enabled=True),
    )
    (gated, *_), _ = _gated_run(
        stp_sequence=[_stp("LIS"), _stp("FWD")],
        endpoints=gated_endpoints,
    )

    assert default.phone_dhcp_lifecycle == ()
    assert default_endpoints.armed == [
        "MCP-VOICEAB-test01_P1", "MCP-VOICEAB-test01_P2",
    ]
    assert gated.phone_dhcp_lifecycle == ()
    assert gated.acquisition_boundary == (
        ACQUISITION_NOT_STARTED_FRESH_DHCP_TRIGGER_UNPROVEN
    )
    assert gated_endpoints.armed == []


def test_lifecycle_helper_adds_no_query_observer_or_mutation_surface():
    source = Path(
        "src/packet_tracer_mcp/application/use_cases/qualify_positive_voice_slice.py"
    ).read_text(encoding="utf-8")
    helper = source.split("def _retain_phone_dhcp_lifecycle", 1)[1].split(
        "\n    def ", 1,
    )[0]

    assert "self._endpoints.read_endpoint_address" in helper
    assert "configure_endpoint_dhcp" not in helper
    assert "self._configuration." not in helper
    assert "self._call_control." not in helper
    live_source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )
    assert set(re.findall(r"OperationalQueryId\.[A-Z0-9_]+", live_source)) == {
        "OperationalQueryId.SHOW_IP_DHCP_BINDING",
        "OperationalQueryId.SHOW_IP_DHCP_POOL",
        "OperationalQueryId.SHOW_IP_INTERFACE",
        "OperationalQueryId.SHOW_IP_INTERFACE_BRIEF",
        "OperationalQueryId.SHOW_SPANNING_TREE",
    }


def test_live_entrypoint_publishes_the_lifecycle_without_changing_old_modes():
    source = Path("tools/cp_scale_positive_voice_ab_live.py").read_text(
        encoding="utf-8",
    )

    assert "--phone-dhcp-lifecycle" in source
    assert '"phone_dhcp_lifecycle"' in source
    assert '"first_observed_svi_dhcp_enabled_milestone"' in source
    assert '"first_observed_device_dhcp_enabled_milestone"' in source
    assert '"svi_dhcp_enabled_before_fwd"' in source
    assert '"device_dhcp_enabled_before_fwd"' in source
    assert '"first_observed_svi_dhcp_enabled_milestone_by_phone"' in source
    assert '"first_observed_device_dhcp_enabled_milestone_by_phone"' in source
    assert '"svi_dhcp_enabled_before_fwd_by_phone"' in source
    assert '"device_dhcp_enabled_before_fwd_by_phone"' in source
    assert '"timing_intrusion_assessment"' in source
    assert '"server_receives_discover": "UNOBSERVABLE"' in source
    assert '"dhcp_transaction_progress": "UNOBSERVABLE"' in source
