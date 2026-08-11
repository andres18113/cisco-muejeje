from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    CallExpectation,
    CallExpectationResult,
    VoicePlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    PhoneExecutionMethod,
    RuntimeCallObservation,
)
from src.packet_tracer_mcp.infrastructure.execution.voice_call_operation import (
    VoicePlanCallOperationAdapter,
)


class FakePhoneControl:
    execution_method = PhoneExecutionMethod.STRUCTURED_API

    def __init__(self) -> None:
        self.calls = []

    def execute_call(self, expectation, call_attempt_id, started_ns):
        self.calls.append((expectation.id, call_attempt_id, started_ns))
        return RuntimeCallObservation(
            call_expectation_id=expectation.id,
            call_attempt_id=call_attempt_id,
            source_phone_id=expectation.source_phone_id,
            dialed_extension=expectation.dialed_extension,
            status=ActionExecutionStatus.VERIFIED,
            connected=True,
            teardown_verified=True,
            observed_after_ns=started_ns,
            fresh_evidence=True,
            evidence_method="fake_structured_phone_control",
            execution_method=self.execution_method,
        )


def _plan() -> VoicePlan:
    return VoicePlan(
        id="voice/reference",
        source_topology_id="e4/reference",
        source_topology_hash="physical-hash",
        source_configuration_id="e5/reference",
        source_configuration_hash="configuration-hash",
        call_expectations=[
            CallExpectation(
                id="call/local-1",
                source_phone_id="phone-1",
                source_extension="1001",
                dialed_extension="1002",
                expected_target_phone_id="phone-2",
                expected_result=CallExpectationResult.ESTABLISHED,
                site_id="hq",
            ),
        ],
    )


def test_voice_call_operation_resolves_only_immutable_e7_plan_ids():
    phone_control = FakePhoneControl()
    adapter = VoicePlanCallOperationAdapter(
        _plan(),
        phone_control,
        clock_ns=lambda: 123,
        attempt_id_factory=lambda: "attempt-1",
    )

    observed = adapter.execute_planned_call("call/local-1")

    assert observed.connected
    assert phone_control.calls == [("call/local-1", "attempt-1", 123)]


def test_voice_call_operation_rejects_ids_outside_bound_e7_plan():
    adapter = VoicePlanCallOperationAdapter(_plan(), FakePhoneControl())

    try:
        adapter.execute_planned_call("call/not-in-plan")
    except ValueError as exc:
        assert "not in the bound VoicePlan" in str(exc)
    else:
        raise AssertionError("Unknown E7 call ID must not reach PhoneControl.")
