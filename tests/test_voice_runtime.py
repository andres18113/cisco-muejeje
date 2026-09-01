"""E7 runtime: APPLY, REGISTER and CALL remain independent."""

from __future__ import annotations

from copy import deepcopy

from src.packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    BindPhoneToExtension,
    CallExpectationResult,
    EnableCallControl,
    VoiceCapabilityDimension,
    VoiceCapabilityProfile,
    VoiceCapabilityStatus,
    VoicePhase,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    CallState,
    RuntimeCallObservation,
    RuntimePhoneRegistration,
)
from src.packet_tracer_mcp.infrastructure.generator.voice_renderer import (
    PacketTracerVoiceRenderer,
)
from tests.test_enterprise_voice import _compile


def _profile(overrides=None):
    dimensions = {
        VoiceCapabilityDimension.CALL_CONTROL_CONFIG: VoiceCapabilityStatus.SUPPORTED,
        VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG: VoiceCapabilityStatus.SUPPORTED,
        VoiceCapabilityDimension.PHONE_REGISTRATION: VoiceCapabilityStatus.SUPPORTED,
        VoiceCapabilityDimension.CALL_INITIATION: VoiceCapabilityStatus.SUPPORTED,
        VoiceCapabilityDimension.CALL_STATE_READBACK: VoiceCapabilityStatus.SUPPORTED,
        VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP: VoiceCapabilityStatus.SUPPORTED,
        VoiceCapabilityDimension.VOICE_DHCP_OPTIONS: VoiceCapabilityStatus.SUPPORTED,
    }
    dimensions.update(overrides or {})
    return {"2911": VoiceCapabilityProfile(model="2911", dimensions=dimensions)}


class FakeVoiceRuntime:
    def __init__(self):
        self.applied = []
        self.registration = {}
        self.calls = {}
        self.call_requests = []
        self.timeline: list[str] = []

    def inventory(self):
        return [
            RuntimeConfigurationTarget(device_name="HQ-R1", model="2911"),
            RuntimeConfigurationTarget(device_name="HQ-PHONE-01", model="7960"),
            RuntimeConfigurationTarget(device_name="HQ-PHONE-02", model="7960"),
        ]

    def apply_actions(self, actions):
        self.timeline.append("bootstrap")
        self.applied.extend(item.id for item in actions)
        return [RuntimeActionMutation(action_id=item.id, applied=True) for item in actions]

    def observe_registration(self, expectation):
        self.timeline.append("registration")
        return self.registration.get(expectation.phone_id, RuntimePhoneRegistration(
            expectation_id=expectation.id,
            phone_id=expectation.phone_id,
            extension=expectation.extension,
            status=ActionExecutionStatus.VERIFIED,
            direct_readback=FieldVerificationStatus.VERIFIED,
            evidence_method="fake_registration_table",
            fresh_evidence=True,
        ))

    def verify_call(self, expectation, attempt_id, started_ns):
        self.call_requests.append((expectation.id, attempt_id, started_ns))
        observed = deepcopy(self.calls.get(expectation.id, RuntimeCallObservation(
            call_expectation_id=expectation.id,
            call_attempt_id=attempt_id,
            source_phone_id=expectation.source_phone_id,
            dialed_extension=expectation.dialed_extension,
            status=ActionExecutionStatus.VERIFIED,
            states=(
                [CallState.IDLE, CallState.DIALING, CallState.FAILED, CallState.IDLE]
                if expectation.expected_result is CallExpectationResult.NOT_CONNECTED
                else [
                    CallState.IDLE, CallState.DIALING, CallState.RINGING,
                    CallState.CONNECTED, CallState.DISCONNECTED, CallState.IDLE,
                ]
            ),
            connected=(expectation.expected_result is CallExpectationResult.ESTABLISHED),
            teardown_verified=True,
            observed_after_ns=started_ns + 1,
            fresh_evidence=True,
            evidence_method="fake_current_call",
        )))
        if not observed.call_attempt_id:
            observed.call_attempt_id = attempt_id
        if not observed.observed_after_ns:
            observed.observed_after_ns = started_ns + 1
        return observed


def _apply(
    runtime=None, *, capabilities=None, foundations=None,
    complete_voice_signal=None, lifecycle_observer=None,
):
    plan = _compile().plan
    runtime = runtime or FakeVoiceRuntime()
    statuses = {
        item.source_id: ActionExecutionStatus.VERIFIED
        for item in plan.foundational_requirements
    }
    if foundations is not None:
        statuses = foundations
    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=statuses,
        capabilities=_profile() if capabilities is None else capabilities,
        runtime_context=ConfigurationRuntimeContext(
            backend="fake", backend_version="9.0.1.0858",
        ),
        complete_voice_signal=complete_voice_signal,
        lifecycle_observer=lifecycle_observer,
    )
    return plan, runtime, result


def test_runtime_keeps_applied_registered_and_call_verified_separate():
    plan, runtime, result = _apply()

    assert result.application_status is ActionExecutionStatus.APPLIED
    assert all(item.status is ActionExecutionStatus.APPLIED for item in result.action_results)
    assert all(item.status is ActionExecutionStatus.VERIFIED for item in result.registrations)
    assert all(item.status is ActionExecutionStatus.VERIFIED for item in result.calls)
    assert result.status is ActionExecutionStatus.VERIFIED
    assert len(runtime.call_requests) == len(plan.call_expectations)


def test_hash_or_foundation_preflight_failure_performs_no_mutation():
    plan = _compile().plan
    runtime = FakeVoiceRuntime()
    mismatch = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash="wrong",
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses={}, capabilities=_profile(),
    )
    assert mismatch.status is ActionExecutionStatus.FAILED
    assert runtime.applied == []


def test_deferred_voice_signal_runs_after_bootstrap_and_before_registration():
    plan = _compile().plan
    runtime = FakeVoiceRuntime()
    statuses = {
        item.source_id: (
            ActionExecutionStatus.PARTIAL
            if item.kind == "voice_vlan"
            else ActionExecutionStatus.VERIFIED
        )
        for item in plan.foundational_requirements
    }

    def complete_signal():
        runtime.timeline.append("voice_signal")
        return {
            item.source_id: ActionExecutionStatus.VERIFIED
            for item in plan.foundational_requirements
        }

    _, _, result = _apply(
        runtime,
        foundations=statuses,
        complete_voice_signal=complete_signal,
    )

    assert runtime.timeline.index("bootstrap") < runtime.timeline.index(
        "voice_signal"
    ) < runtime.timeline.index("registration")
    assert result.status is ActionExecutionStatus.VERIFIED


def test_deferred_voice_lifecycle_is_retained_in_causal_order():
    plan = _compile().plan
    runtime = FakeVoiceRuntime()
    statuses = {
        item.source_id: (
            ActionExecutionStatus.PARTIAL
            if item.kind == "voice_vlan"
            else ActionExecutionStatus.VERIFIED
        )
        for item in plan.foundational_requirements
    }
    events: list[str] = []

    _, _, result = _apply(
        runtime,
        foundations=statuses,
        complete_voice_signal=lambda: {
            item.source_id: ActionExecutionStatus.VERIFIED
            for item in plan.foundational_requirements
        },
        lifecycle_observer=events.append,
    )

    assert result.status is ActionExecutionStatus.VERIFIED
    assert events == [
        "VOICE_BOOTSTRAP_STARTED",
        "VOICE_BOOTSTRAP_APPLIED",
        "DEFERRED_VOICE_COMPLETION_STARTED",
        "DEFERRED_VOICE_COMPLETION_VERIFIED",
        "REGISTRATION_STARTED",
        "REGISTRATION_COMPLETED",
    ]


def test_unverified_deferred_signal_blocks_registration_after_bootstrap():
    plan = _compile().plan
    runtime = FakeVoiceRuntime()
    statuses = {
        item.source_id: (
            ActionExecutionStatus.PARTIAL
            if item.kind == "voice_vlan"
            else ActionExecutionStatus.VERIFIED
        )
        for item in plan.foundational_requirements
    }

    _, _, result = _apply(
        runtime,
        foundations=statuses,
        complete_voice_signal=lambda: statuses,
    )

    assert result.status is ActionExecutionStatus.FAILED
    assert result.failure_code is (
        ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    )
    assert "registration" not in runtime.timeline

    _, runtime, missing = _apply(FakeVoiceRuntime(), foundations={})
    assert missing.status is ActionExecutionStatus.FAILED
    assert runtime.applied == []


def test_unknown_capability_is_never_attempted_blindly():
    plan, runtime, result = _apply(capabilities={})

    assert runtime.applied == []
    assert all(item.status is ActionExecutionStatus.SKIPPED for item in result.action_results)
    assert result.status is ActionExecutionStatus.PARTIAL


def test_unknown_tftp_bootstrap_is_skipped_and_blocks_only_its_dependents():
    plan, runtime, result = _apply(capabilities=_profile({
        VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP: VoiceCapabilityStatus.UNKNOWN,
    }))
    bootstrap = next(
        item for item in plan.actions
        if item.required_capability is VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP
    )
    observed = next(
        item for item in result.action_results if item.action_id == bootstrap.id
    )

    assert observed.status is ActionExecutionStatus.SKIPPED
    assert bootstrap.id not in runtime.applied
    assert result.application_status is ActionExecutionStatus.PARTIAL


def test_call_control_application_failure_blocks_registration_and_calls():
    class FailingRuntime(FakeVoiceRuntime):
        def apply_actions(self, actions):
            self.applied.extend(item.id for item in actions)
            return [RuntimeActionMutation(
                action_id=item.id, applied=False,
            ) for item in actions]

    _, runtime, result = _apply(FailingRuntime())

    assert runtime.applied
    assert result.application_status is ActionExecutionStatus.FAILED
    assert all(item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
               for item in result.registrations)
    assert all(item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
               for item in result.calls)


def test_dependency_cycle_stops_voice_runtime_before_mutation():
    plan = _compile().plan
    runtime = FakeVoiceRuntime()
    plan.actions[0].depends_on = [plan.actions[-1].id]
    foundations = {
        item.source_id: ActionExecutionStatus.VERIFIED
        for item in plan.foundational_requirements
    }

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=foundations,
        capabilities=_profile(),
    )

    assert result.status is ActionExecutionStatus.FAILED
    assert runtime.applied == []


def test_unobservable_registration_can_still_prove_phone_usability_by_fresh_call():
    runtime = FakeVoiceRuntime()
    for phone_id in ("phone-1", "phone-2"):
        runtime.registration[phone_id] = RuntimePhoneRegistration(
            expectation_id=f"registration/{phone_id}", phone_id=phone_id,
            extension="", status=ActionExecutionStatus.PARTIAL,
            direct_readback=FieldVerificationStatus.UNOBSERVABLE,
            evidence_method="pt_api_has_no_registration_getter", fresh_evidence=False,
        )
    _, _, result = _apply(runtime, capabilities=_profile({
        VoiceCapabilityDimension.PHONE_REGISTRATION: VoiceCapabilityStatus.UNOBSERVABLE,
    }))

    assert all(item.direct_readback is FieldVerificationStatus.UNOBSERVABLE
               for item in result.registrations)
    assert any(item.usability_status is ActionExecutionStatus.VERIFIED
               for item in result.phones)
    assert all(item.status is ActionExecutionStatus.VERIFIED for item in result.calls)


def test_registration_timeout_blocks_calls_without_mislabeling_call_control():
    runtime = FakeVoiceRuntime()
    runtime.registration["phone-2"] = RuntimePhoneRegistration(
        expectation_id="registration/phone-2", phone_id="phone-2", extension="3102",
        status=ActionExecutionStatus.FAILED,
        direct_readback=FieldVerificationStatus.FAILED,
        evidence_method="bounded_registration_wait", fresh_evidence=True,
        message="registration timeout",
    )
    _, _, result = _apply(runtime)

    positive = [item for item in result.calls if item.expected_result is CallExpectationResult.ESTABLISHED]
    assert all(item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED for item in positive)
    assert runtime.call_requests == [
        item for item in runtime.call_requests
        if next(call for call in result.calls if call.call_expectation_id == item[0]).expected_result
        is CallExpectationResult.NOT_CONNECTED
    ]


def test_stale_previous_call_cannot_verify_current_attempt():
    plan = _compile().plan
    runtime = FakeVoiceRuntime()
    call = next(item for item in plan.call_expectations
                if item.expected_result is CallExpectationResult.ESTABLISHED)
    runtime.calls[call.id] = RuntimeCallObservation(
        call_expectation_id=call.id, call_attempt_id="previous-attempt",
        source_phone_id=call.source_phone_id, dialed_extension=call.dialed_extension,
        status=ActionExecutionStatus.VERIFIED,
        states=[CallState.CONNECTED], connected=True, teardown_verified=True,
        observed_after_ns=1, fresh_evidence=True,
    )
    _, _, result = _apply(runtime)
    observed = next(item for item in result.calls if item.call_expectation_id == call.id)

    assert observed.status is ActionExecutionStatus.FAILED
    assert not observed.fresh_evidence


def test_ring_without_connect_and_hangup_failure_are_distinct_failures():
    plan = _compile().plan
    calls = [item for item in plan.call_expectations
             if item.expected_result is CallExpectationResult.ESTABLISHED]
    runtime = FakeVoiceRuntime()
    runtime.calls[calls[0].id] = RuntimeCallObservation(
        call_expectation_id=calls[0].id, call_attempt_id="",
        source_phone_id=calls[0].source_phone_id, dialed_extension=calls[0].dialed_extension,
        states=[CallState.IDLE, CallState.DIALING, CallState.RINGING], connected=False,
        teardown_verified=True, status=ActionExecutionStatus.FAILED,
        fresh_evidence=True,
    )
    runtime.calls[calls[1].id] = RuntimeCallObservation(
        call_expectation_id=calls[1].id, call_attempt_id="",
        source_phone_id=calls[1].source_phone_id, dialed_extension=calls[1].dialed_extension,
        states=[CallState.IDLE, CallState.DIALING, CallState.CONNECTED], connected=True,
        teardown_verified=False, status=ActionExecutionStatus.PARTIAL,
        fresh_evidence=True,
    )
    _, _, result = _apply(runtime)
    observed = {item.call_expectation_id: item for item in result.calls}

    assert observed[calls[0].id].status is ActionExecutionStatus.FAILED
    assert observed[calls[1].id].status is ActionExecutionStatus.PARTIAL
    assert not observed[calls[1].id].teardown_verified


def test_connect_timeout_is_not_misreported_as_a_verified_call():
    plan = _compile().plan
    call = next(
        item for item in plan.call_expectations
        if item.expected_result is CallExpectationResult.ESTABLISHED
    )
    runtime = FakeVoiceRuntime()
    runtime.calls[call.id] = RuntimeCallObservation(
        call_expectation_id=call.id, call_attempt_id="",
        source_phone_id=call.source_phone_id,
        dialed_extension=call.dialed_extension,
        states=[CallState.IDLE, CallState.DIALING], connected=False,
        teardown_verified=True, status=ActionExecutionStatus.FAILED,
        fresh_evidence=True, message="bounded connect timeout",
    )

    _, _, result = _apply(runtime)
    observed = next(
        item for item in result.calls if item.call_expectation_id == call.id
    )

    assert observed.status is ActionExecutionStatus.FAILED
    assert observed.failure_code.value == "call_setup_failed"
    assert CallState.CONNECTED not in observed.states


def test_unavailable_phone_control_is_unobservable_not_failed_call_setup():
    plan = _compile().plan
    call = next(
        item for item in plan.call_expectations
        if item.expected_result is CallExpectationResult.ESTABLISHED
    )
    runtime = FakeVoiceRuntime()
    runtime.calls[call.id] = RuntimeCallObservation(
        call_expectation_id=call.id,
        call_attempt_id="",
        source_phone_id=call.source_phone_id,
        dialed_extension=call.dialed_extension,
        status=ActionExecutionStatus.UNOBSERVABLE,
        observed_after_ns=0,
        fresh_evidence=False,
        evidence_method="documented_phone_control_api_unavailable",
    )

    _, _, result = _apply(runtime)
    observed = next(
        item for item in result.calls if item.call_expectation_id == call.id
    )

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert observed.failure_code.value == "observability_limitation"
    assert result.status is ActionExecutionStatus.PARTIAL


def test_each_direction_receives_a_distinct_current_attempt_id():
    plan, runtime, result = _apply()
    positives = [item for item in result.calls
                 if item.expected_result is CallExpectationResult.ESTABLISHED]

    assert len(positives) == 2
    assert len({item.call_attempt_id for item in positives}) == 2
    assert all(item.fresh_evidence for item in positives)


def test_unassigned_extension_is_a_fresh_negative_control():
    _, runtime, result = _apply()
    negative = next(
        item for item in result.calls
        if item.expected_result is CallExpectationResult.NOT_CONNECTED
    )

    assert negative.dialed_extension == "3200"
    assert negative.status is ActionExecutionStatus.VERIFIED
    assert negative.fresh_evidence
    assert not negative.connected
    assert any(item[0] == negative.call_expectation_id for item in runtime.call_requests)


def test_trusted_renderer_translates_only_typed_actions_and_runtime_mac():
    plan = _compile().plan
    renderer = PacketTracerVoiceRenderer()
    batches = renderer.render_device_batches(
        "HQ-R1", "2911", plan.actions,
        phone_macs={"phone-1": "00:11:22:33:44:55", "phone-2": "0060.5c12.3456"},
    )
    payload = "\n".join(item.ios_payload for item in batches)

    assert "telephony-service" in payload
    assert "ip source-address 198.18.170.1 port 2000" in payload
    assert "ephone-dn 1" in payload
    assert "number 3101" in payload
    assert "mac-address 0011.2233.4455" in payload
    assert "button 1:1" in payload
    assert "option 150 ip 198.18.170.1" in payload
    assert "create cnf-files" in payload
    assert "configureIosDevice" in batches[0].js_call
    bindings = [
        item for item in plan.actions
        if isinstance(item, BindPhoneToExtension)
    ]
    binding_batches = [
        item for item in batches
        if item.phase is VoicePhase.PHONE_BINDINGS
    ]
    assert len(binding_batches) == len(bindings)
    assert all(len(item.action_ids) == 1 for item in binding_batches)
    assert all(
        sum(
            line.startswith("ephone ")
            for line in item.ios_payload.splitlines()
        ) == 1
        for item in binding_batches
    )


def test_applied_binding_with_failed_readback_fails_voice_application():
    result = ActionApplicationResult(
        action_id="voice/binding/1",
        status=ActionExecutionStatus.APPLIED,
        failure_code=ConfigurationFailureCode.VERIFICATION_FAILED,
        message="Binding was dispatched but absent from readback.",
    )

    assert VoiceApplicator._application_status([result]) is (
        ActionExecutionStatus.FAILED
    )


def test_renderer_preserves_qualified_site_capacity_above_historical_42():
    action = EnableCallControl(
        id="voice/enable/large",
        phase=VoicePhase.CALL_CONTROL,
        call_control_id="call-control/large",
        host_device_id="r-large",
        host_device_name="LARGE-RTR",
        host_model="2911",
        site_id="large-branch",
        required_capability=VoiceCapabilityDimension.CALL_CONTROL_CONFIG,
        max_phones=51,
        max_extensions=51,
    )

    batches = PacketTracerVoiceRenderer().render_device_batches(
        "LARGE-RTR", "2911", [action],
    )

    assert "max-ephones 51" in batches[0].ios_payload
    assert "max-dn 51" in batches[0].ios_payload


def test_renderer_rejects_missing_or_malformed_phone_identity():
    plan = _compile().plan
    renderer = PacketTracerVoiceRenderer()
    bindings = [item for item in plan.actions if isinstance(item, BindPhoneToExtension)]

    for phone_macs in ({}, {"phone-1": "bad;reload", "phone-2": "0011.2233.4455"}):
        try:
            renderer.render_device_batches("HQ-R1", "2911", bindings, phone_macs=phone_macs)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe or absent phone MAC must be rejected")


def test_compact_runtime_summary_omits_call_history_details():
    _, _, result = _apply()
    summary = result.compact_summary()

    assert summary["calls"]["verified"] == 3
    assert "states" not in summary
    assert "action_results" not in summary


def _foundations(plan, **overrides):
    statuses = {
        item.source_id: ActionExecutionStatus.VERIFIED
        for item in plan.foundational_requirements
    }
    for kind, status in overrides.items():
        for item in plan.foundational_requirements:
            if item.kind == kind:
                statuses[item.source_id] = status
    return statuses


def test_an_unobservable_dhcp_pool_foundation_does_not_block_voice():
    """Packet Tracer exposes no DHCP-pool getter, and never will on this build.

    `VerificationKind.DHCP_POOL` is answered UNOBSERVABLE unconditionally --
    a measured limit of the observer, already accepted as a governed ceiling by
    the canonical stage gate. Requiring VERIFIED for the pool a phone leases
    from is therefore not fail-closed but fail-impossible: it asks for evidence
    the backend cannot produce, and voice could never be staged at all.

    The pool is not taken on trust. Its action must have applied for a
    verification result to exist for it, and on the stage where this matters its
    effect is independently evidenced by every other endpoint that leased from
    it and read its address back.
    """
    plan = _compile().plan
    runtime = FakeVoiceRuntime()

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundations(
            plan, voice_dhcp_pool=ActionExecutionStatus.UNOBSERVABLE,
        ),
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


def test_an_unobservable_voice_vlan_foundation_still_blocks_voice():
    """The ceiling is per kind. A switch port has a read-back and must use it."""
    plan = _compile().plan
    runtime = FakeVoiceRuntime()

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundations(
            plan, voice_vlan=ActionExecutionStatus.UNOBSERVABLE,
        ),
        capabilities=_profile(),
        runtime_context=ConfigurationRuntimeContext(
            backend="fake", backend_version="9.0.1.0858",
        ),
    )

    assert (
        result.failure_code
        is ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    )
    assert runtime.applied == []


def test_a_failed_dhcp_pool_foundation_still_blocks_voice():
    """Unobservable is not a licence to ignore an observed failure."""
    plan = _compile().plan
    runtime = FakeVoiceRuntime()

    result = VoiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundations(
            plan, voice_dhcp_pool=ActionExecutionStatus.FAILED,
        ),
        capabilities=_profile(),
        runtime_context=ConfigurationRuntimeContext(
            backend="fake", backend_version="9.0.1.0858",
        ),
    )

    assert (
        result.failure_code
        is ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    )
    assert runtime.applied == []
