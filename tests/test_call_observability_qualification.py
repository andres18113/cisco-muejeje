from __future__ import annotations

from types import SimpleNamespace

from src.packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
from src.packet_tracer_mcp.application.use_cases.qualify_call_observability import (
    CallObservabilityQualification,
    CallObservabilityQualificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.execution import (
    MutationDisposition,
)
from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceObservation,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    CallExpectationResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    CallState,
    PhoneExecutionMethod,
    RuntimeCallObservation,
    RuntimePhoneRegistration,
)


class Physical:
    def __init__(self, *, baseline=None, final_second=None):
        self.created = []
        self.links = []
        self.removed = []
        self.observations = 0
        self.final_second = final_second
        self.baseline = baseline

    def observe_workspace(self):
        self.observations += 1
        if self.observations == 1 and self.baseline is not None:
            return self.baseline
        if self.observations == 3 and self.final_second is not None:
            return self.final_second
        return PhysicalWorkspaceObservation()

    def ensure_device(self, device):
        self.created.append(device)
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def ensure_link(self, link):
        self.links.append(link)
        return PhysicalMutationResult(
            target_id=link.id,
            target_kind=PhysicalObjectKind.LINK,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )

    def remove_device(self, device):
        self.removed.append(device)
        return PhysicalMutationResult(
            target_id=device.id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
        )


class Configuration:
    def __init__(self, timeline=None):
        self.actions = []
        self.timeline = timeline if timeline is not None else []

    def apply_actions(self, actions):
        self.timeline.append(("configuration", tuple(item.id for item in actions)))
        self.actions.extend(actions)
        return [
            RuntimeActionMutation(
                action_id=item.id,
                applied=True,
                disposition=MutationDisposition.CHANGED,
            )
            for item in actions
        ]


class Mode:
    def __init__(self):
        self.set_calls = []
        self.reads = 0

    def read_simulation_state(self):
        self.reads += 1
        return SimpleNamespace(observed=True, simulation_mode=False, message="realtime")

    def set_simulation_mode(self, value):
        self.set_calls.append(value)
        return SimpleNamespace(observed=True, after=value)


class VoiceRuntime:
    def __init__(self, *, unobservable=False, timeline=None):
        self.unobservable = unobservable
        self.bound = None
        self.actions = []
        self.timeline = timeline if timeline is not None else []

    def inventory(self):
        return [
            RuntimeConfigurationTarget(
                device_name="__MCP_CALL_QUAL_TEST_R", model="2811",
            ),
            RuntimeConfigurationTarget(
                device_name="__MCP_CALL_QUAL_TEST_P1", model="7960",
            ),
            RuntimeConfigurationTarget(
                device_name="__MCP_CALL_QUAL_TEST_P2", model="7960",
            ),
        ]

    def apply_actions(self, actions):
        self.timeline.append(("voice", tuple(item.id for item in actions)))
        self.actions.extend(actions)
        return [RuntimeActionMutation(action_id=item.id, applied=True) for item in actions]

    def observe_registration(self, expectation):
        self.timeline.append(("registration", expectation.id))
        return RuntimePhoneRegistration(
            expectation_id=expectation.id,
            phone_id=expectation.phone_id,
            extension=expectation.extension,
            status=ActionExecutionStatus.VERIFIED,
            direct_readback=FieldVerificationStatus.VERIFIED,
            evidence_method="fresh_show_ephone",
            fresh_evidence=True,
        )

    def bind_call_plan(self, plan):
        self.bound = plan

    def verify_call(self, expectation, attempt_id, started_ns):
        self.timeline.append(("call", expectation.id))
        if self.unobservable:
            return RuntimeCallObservation(
                call_expectation_id=expectation.id,
                call_attempt_id=attempt_id,
                source_phone_id=expectation.source_phone_id,
                destination_phone_id=expectation.expected_target_phone_id,
                dialed_extension=expectation.dialed_extension,
                status=ActionExecutionStatus.UNOBSERVABLE,
                observed_after_ns=started_ns,
                evidence_method="native_ui_unobservable",
                execution_method=PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI,
            )
        established = expectation.expected_result is CallExpectationResult.ESTABLISHED
        return RuntimeCallObservation(
            call_expectation_id=expectation.id,
            call_attempt_id=attempt_id,
            source_phone_id=expectation.source_phone_id,
            destination_phone_id=expectation.expected_target_phone_id,
            dialed_extension=expectation.dialed_extension,
            status=ActionExecutionStatus.VERIFIED,
            states=(
                [
                    CallState.IDLE,
                    CallState.DIALING,
                    CallState.RINGING,
                    CallState.CONNECTED,
                    CallState.DISCONNECTED,
                    CallState.IDLE,
                ]
                if established else [
                    CallState.IDLE,
                    CallState.DIALING,
                    CallState.FAILED,
                    CallState.IDLE,
                ]
            ),
            connected=established,
            teardown_verified=True,
            observed_after_ns=started_ns + 1,
            fresh_evidence=True,
            evidence_method="packet_tracer_native_ui_correlated_state_capture_v1",
            evidence_artifact_path=f"captures/{attempt_id}.json",
            evidence_sha256="a" * 64,
            execution_method=PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI,
        )


def _qualification(*, unobservable=False, baseline=None, final_second=None):
    timeline = []
    physical = Physical(baseline=baseline, final_second=final_second)
    configuration = Configuration(timeline)
    mode = Mode()
    voice_runtime = VoiceRuntime(unobservable=unobservable, timeline=timeline)
    qualifier = CallObservabilityQualification(
        physical=physical,
        configuration=configuration,
        voice=VoiceApplicator(voice_runtime),
        mode=mode,
        token="test",
    )
    return qualifier, physical, configuration, mode, voice_runtime


def test_minimum_qualification_uses_cp_scale_models_and_existing_voice_applicator():
    qualifier, physical, configuration, mode, voice_runtime = _qualification()

    result = qualifier.qualify()

    assert result.status is CallObservabilityQualificationStatus.VERIFIED
    assert [item.model for item in physical.created] == [
        "2811", "3560-24PS", "7960", "7960",
    ]
    assert len(physical.links) == 3
    assert [item.name for item in physical.removed] == [
        "__MCP_CALL_QUAL_TEST_P2",
        "__MCP_CALL_QUAL_TEST_P1",
        "__MCP_CALL_QUAL_TEST_SW",
        "__MCP_CALL_QUAL_TEST_R",
    ]
    assert physical.observations == 3
    assert mode.set_calls == [False]
    assert mode.reads == 2
    assert voice_runtime.bound is result.voice_plan
    assert result.voice_result is not None
    assert [item.expected_result for item in result.voice_result.calls] == [
        CallExpectationResult.ESTABLISHED,
        CallExpectationResult.NOT_CONNECTED,
    ]
    assert len({item.call_attempt_id for item in result.voice_result.calls}) == 2
    assert all(item.fresh_evidence for item in result.voice_result.calls)
    assert all(item.teardown_verified for item in result.voice_result.calls)
    assert all(
        item.execution_method is PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI
        for item in result.voice_result.calls
    )
    assert configuration.actions
    initial_access = [
        item for item in configuration.actions
        if item.id in {"callqual/config/access/1", "callqual/config/access/2"}
    ]
    signal_access = [
        item for item in configuration.actions
        if item.id in {
            "callqual/config/access/voice/1",
            "callqual/config/access/voice/2",
        }
    ]
    assert [item.voice_vlan_id for item in initial_access] == [None, None]
    assert [item.voice_vlan_id for item in signal_access] == [930, 930]
    events = [event for event, _detail in configuration.timeline]
    assert events[0] == "configuration"
    assert events[1:5] == ["voice"] * 4
    assert events[5:] == [
        "configuration", "registration", "registration", "call", "call",
    ]


def test_unobservable_call_channel_stays_unobservable_and_still_cleans_twice():
    qualifier, physical, _configuration, mode, _voice_runtime = _qualification(
        unobservable=True,
    )

    result = qualifier.qualify()

    assert result.status is CallObservabilityQualificationStatus.UNOBSERVABLE
    assert result.voice_result is not None
    assert all(
        item.status is ActionExecutionStatus.UNOBSERVABLE
        for item in result.voice_result.calls
    )
    assert physical.observations == 3
    assert len(physical.removed) == 4
    assert mode.set_calls == [False]


def test_second_nonempty_cleanup_observation_blocks_positive_claim():
    foreign = PhysicalWorkspaceObservation(devices=[
        PhysicalWorkspaceDeviceObservation(
            name="foreign",
            model="PC-PT",
        ),
    ])
    qualifier, physical, _configuration, _mode, _voice_runtime = _qualification(
        final_second=foreign,
    )

    result = qualifier.qualify()

    assert result.status is CallObservabilityQualificationStatus.BLOCKED
    assert result.cleanup_verified is False
    assert physical.observations == 3


def test_nonempty_baseline_never_mutates_and_reports_postflight_observations():
    foreign = PhysicalWorkspaceObservation(devices=[
        PhysicalWorkspaceDeviceObservation(name="foreign", model="PC-PT"),
    ])
    qualifier, physical, configuration, mode, voice_runtime = _qualification(
        baseline=foreign,
    )

    result = qualifier.qualify()

    assert result.status is CallObservabilityQualificationStatus.BLOCKED
    assert physical.created == []
    assert physical.links == []
    assert physical.removed == []
    assert configuration.actions == []
    assert voice_runtime.actions == []
    assert result.cleanup_first is not None
    assert result.cleanup_second is not None
    assert mode.set_calls == [False]
