"""Packet Tracer E7 adapter stays typed and honest about observability."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    BindPhoneToExtension,
    ConfigureDialRule,
    VoiceActionType,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    PhoneExecutionMethod,
    RuntimeCallObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_voice_runtime import (
    PacketTracerEnterpriseVoiceRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.phone_control import (
    PacketTracerNativeUiPhoneControlAdapter,
)
from tests.test_enterprise_voice import _compile


def _runtime(captured):
    def send(source):
        captured.append(source)
        return True

    def send_and_wait(source, _timeout):
        captured.append(source)
        if "getMacAddress" in source:
            return '{"found":true,"mac":"00:11:22:33:44:55"}'
        return "{}"

    return PacketTracerEnterpriseVoiceRuntime(
        lambda: {"devices": [
            {"name": "HQ-R1", "model": "2911", "ports": [{"name": "Gi0/0"}]},
            {"name": "HQ-PHONE-01", "model": "7960", "ports": [{"name": "Switch"}]},
            {"name": "HQ-PHONE-02", "model": "7960", "ports": [{"name": "Switch"}]},
        ]},
        send,
        send_and_wait,
        ios_readiness=lambda _name: True,
    )


def test_adapter_applies_only_typed_voice_actions_and_escapes_device_names():
    captured = []
    runtime = _runtime(captured)
    plan = _compile().plan
    bindings = [item for item in plan.actions if isinstance(item, BindPhoneToExtension)]

    results = runtime.apply_actions(bindings)

    assert all(item.applied for item in results)
    assert any("getMacAddress" in item for item in captured)
    assert any("configureIosDevice" in item for item in captured)
    assert any('"HQ-R1"' in item for item in captured)
    assert any("mac-address 0011.2233.4455" in item for item in captured)


def test_local_dial_rule_is_implicit_and_intersite_rule_is_not_claimed_applied():
    captured = []
    runtime = _runtime(captured)
    plan = _compile().plan
    local = next(item for item in plan.actions if isinstance(item, ConfigureDialRule))
    result = runtime.apply_actions([local])[0]

    assert result.applied
    assert "implicit" in result.message
    assert not any("configureIosDevice" in item for item in captured)

    intersite = local.model_copy(update={
        "id": "voice/dial/intersite", "local": False,
        "destination_site_id": "branch",
    })
    rejected = runtime.apply_actions([intersite])[0]
    assert not rejected.applied


def test_missing_documented_call_driver_returns_unobservable_not_success():
    runtime = _runtime([])
    plan = _compile().plan
    call = plan.call_expectations[0]

    observed = runtime.verify_call(call, "attempt-current", 123)

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert observed.execution_method is PhoneExecutionMethod.UNOBSERVABLE
    assert not observed.fresh_evidence
    assert not observed.connected
    assert not observed.teardown_verified
    assert "unavailable" in observed.message


def test_registration_getter_absence_is_reported_as_unobservable():
    runtime = _runtime([])
    expectation = next(
        item for item in _compile().plan.verification_expectations
        if item.kind.value == "phone_registration"
    )

    observed = runtime.observe_registration(expectation)

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert observed.direct_readback is FieldVerificationStatus.UNOBSERVABLE
    assert not observed.fresh_evidence


def test_registration_uses_fresh_privileged_show_ephone_when_available():
    captured = []
    output = (
        "show ephone\n"
        "ephone-1 Mac:0011.2233.4455 TCP socket:[1] activeLine:0 "
        "REGISTERED in SCCP ver 12 and Server in ver 8\n"
        "IP:198.18.170.2 1025 7960 keepalive 43 max_line 2\n"
        " button 1: dn 1 number 3101 CH1 IDLE\nRouter#"
    )

    def send(source):
        captured.append(source)
        return True

    def send_and_wait(source, _timeout):
        captured.append(source)
        if "getMacAddress" in source:
            return '{"found":true,"mac":"00:11:22:33:44:55"}'
        if "getPrompt" in source and "booting" in source:
            return '{"found":true,"booting":false,"terminal":true,"prompt":"Router#","output":"Router#"}'
        if "enterCommand" in source and "show ephone" in source:
            return '{"ok":true,"before":"Router#"}'
        if "configuration_channel" in source:
            import json
            return json.dumps({
                "found": True, "configuration_channel": True,
                "output": "Router#" + output,
            })
        return "{}"

    runtime = PacketTracerEnterpriseVoiceRuntime(
        lambda: {"devices": [
            {"name": "HQ-R1", "model": "2911"},
            {"name": "HQ-PHONE-01", "model": "7960"},
            {"name": "HQ-PHONE-02", "model": "7960"},
        ]},
        send, send_and_wait, ios_readiness=lambda _name: True,
    )
    plan = _compile().plan
    bindings = [item for item in plan.actions if isinstance(item, BindPhoneToExtension)]
    runtime.apply_actions(bindings)
    expectation = next(
        item for item in plan.verification_expectations
        if item.kind.value == "phone_registration" and item.phone_id == "phone-1"
    )

    observed = runtime.observe_registration(expectation)

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.direct_readback is FieldVerificationStatus.VERIFIED
    assert observed.fresh_evidence
    assert any("show ephone" in item for item in captured)


def test_inventory_preserves_runtime_model_and_interfaces():
    items = _runtime([]).inventory()

    router = next(item for item in items if item.device_name == "HQ-R1")
    assert router.model == "2911"
    assert router.interfaces == ["Gi0/0"]


def test_legacy_ui_driver_is_encapsulated_and_execution_method_is_preserved():
    requests = []

    def driver(expectation, attempt_id, started_ns):
        requests.append((expectation.id, attempt_id, started_ns))
        return RuntimeCallObservation(
            call_expectation_id=expectation.id,
            call_attempt_id=attempt_id,
            source_phone_id=expectation.source_phone_id,
            dialed_extension=expectation.dialed_extension,
            status=ActionExecutionStatus.VERIFIED,
            observed_after_ns=started_ns + 1,
            fresh_evidence=True,
            evidence_method="controlled_native_ui",
        )

    runtime = PacketTracerEnterpriseVoiceRuntime(
        lambda: [], lambda _source: True, lambda _source, _timeout: "{}",
        ios_readiness=lambda _name: True,
        phone_control=PacketTracerNativeUiPhoneControlAdapter(driver),
    )
    call = _compile().plan.call_expectations[0]

    observed = runtime.verify_call(call, "attempt-current", 123)

    assert requests == [(call.id, "attempt-current", 123)]
    assert observed.execution_method is PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI


def test_intersite_runtime_limitation_is_unknown_not_unsupported():
    runtime = _runtime([])
    local = next(
        item for item in _compile().plan.actions
        if isinstance(item, ConfigureDialRule)
    )
    intersite = local.model_copy(update={
        "id": "voice/dial/intersite", "local": False,
        "destination_site_id": "branch",
    })

    observed = runtime.apply_actions([intersite])[0]

    assert observed.failure_code.value == "capability_unknown"
