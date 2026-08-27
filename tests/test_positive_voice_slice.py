"""Contracts for the positive disposable Voice slice (the A side of the A/B)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.packet_tracer_mcp.application.use_cases.qualify_positive_voice_slice import (
    ABSENT,
    BLOCKING,
    DATA_VLAN_ID,
    EXTENSIONS,
    FORWARDING,
    NO,
    NOT_REGISTERED,
    POSITIVE_VOICE_PREFIX,
    REGISTERED,
    UNOBSERVABLE,
    VERIFIED,
    VOICE_VLAN_ID,
    YES,
    PositiveVoicePhoneOutcome,
    PositiveVoiceSliceQualifier,
    PositiveVoiceSliceResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)


@dataclass
class _Outcome:
    success: bool = True
    message: str = ""
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
        if self.fail_on and self.fail_on in device.name:
            self.created.append(device.name)
            return _Outcome(success=False, message="refused")
        self.created.append(device.name)
        return _Outcome()

    def observe_device(self, device):
        return _Outcome()

    def remove_device(self, device):
        self.removed.append(device.name)
        return _Outcome()

    def ensure_link(self, link):
        self.links.append(f"{link.device_a}:{link.port_a}")
        return _Outcome()


class _Configuration:
    def __init__(self, port=None, stp=None, bindings=None):
        self.applied: list = []
        self.port = port if port is not None else _Port(DATA_VLAN_ID, VOICE_VLAN_ID)
        self.stp = stp
        self.bindings = bindings if bindings is not None else [_Binding("10.93.0.10")]

    def apply_actions(self, actions):
        self.applied.extend(actions)
        return [_Outcome(action_id=getattr(a, "id", "")) for a in actions]

    def read_access_port(self, device_name, interface):
        return self.port

    def read_spanning_tree(self, device_name):
        return self.stp

    def read_dhcp_bindings(self, device_name):
        return self.bindings


_DEFAULT = object()


class _CallControl:
    def __init__(self, registration=_DEFAULT):
        self.applied: list = []
        # A sentinel, not None: passing None must mean "observed nothing", which
        # is the case this fake exists to reproduce.
        self.registration = _Registration() if registration is _DEFAULT else registration

    def apply_actions(self, actions):
        self.applied.extend(actions)
        return [_Outcome(action_id=getattr(a, "id", "")) for a in actions]

    def observe_registrations(self, expectations):
        if self.registration is None:
            return []
        return [self.registration for _ in expectations]


class _Endpoints:
    def __init__(self):
        self.armed: list[str] = []

    def configure_endpoint_dhcp(self, device_name, interface):
        self.armed.append(device_name)
        return _Outcome()

    def read_endpoint_address(self, device_name, interface):
        return None


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


def _qualifier(physical, configuration, call_control, endpoints, mode):
    return PositiveVoiceSliceQualifier(
        physical, configuration, call_control, endpoints, mode, token="test01",
    )


def _run(
    *, physical=None, configuration=None, call_control=None,
    endpoints=None, mode=None, baseline=None,
):
    baseline = baseline if baseline is not None else _empty_workspace()
    physical = physical if physical is not None else _Physical(baseline)
    configuration = configuration if configuration is not None else _Configuration()
    call_control = call_control if call_control is not None else _CallControl()
    endpoints = endpoints if endpoints is not None else _Endpoints()
    mode = mode if mode is not None else _ModeRuntime()
    qualifier = _qualifier(physical, configuration, call_control, endpoints, mode)
    result = qualifier.qualify("2811", "3560-24PS", "7960")
    return result, physical, configuration, call_control, endpoints, mode


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
    result, _, _, _, _, mode = _run(mode=mode)

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


def test_handoff_records_the_positive_voice_slice_and_its_live_boundary():
    handoff = Path("handoff.md").read_text(encoding="utf-8")

    assert "POSITIVE_VOICE_AB_IMPLEMENTED = YES" in handoff
    assert "POSITIVE_VOICE_AB_LIVE = NOT_RUN" in handoff
    # The blocker is named exactly.  "Voice A/B failed" would be false: it was
    # never run, and the reason is a bridge that would not connect.
    assert "POSITIVE_VOICE_AB_LIVE_BLOCKER = BRIDGE_DID_NOT_CONNECT" in handoff
    assert "PACKET_TRACER_PROCESS_PRESENT = YES" in handoff
    assert "POSITIVE_VOICE_AB_RESULT = NOT_ESTABLISHED" in handoff
    assert "POSITIVE_SLICE_PORTFAST = NOT_APPLIED" in handoff
    assert "NEXT_ACTIVE_STEP = POSITIVE_DISPOSABLE_VOICE_AB_LIVE" in handoff
    # Nothing about the failure side may drift while the A side is unrun.
    assert "PORTFAST_AS_VOICE_ROOT_CAUSE = NOT_CONFIRMED" in handoff
    assert "VOICE_ROOT_CAUSE = NOT_YET_CONFIRMED" in handoff
    assert "CP_SCALE_STATUS = OPEN / NOT VERIFIED" in handoff
