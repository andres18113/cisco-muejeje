"""E6 application: preflight, capability gates y evidencia independiente."""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.apply_services import ServiceApplicator
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceCapabilityProfile,
    ServiceActionType,
    ServiceEvidenceKind,
    ServiceType,
)
from src.packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    RuntimeServiceVerification,
)

from test_enterprise_services import _fixture
from src.packet_tracer_mcp.application.use_cases.compile_services import (
    compile_enterprise_services,
)


class FakeServiceRuntime:
    def __init__(self):
        self.apply_calls: list[list[str]] = []
        self.verify_calls: list[str] = []
        self.behavior_status = ActionExecutionStatus.VERIFIED
        self.direct_status = ActionExecutionStatus.PARTIAL

    def inventory(self):
        return [
            RuntimeConfigurationTarget(device_name="HQ-SERVER-01", model="Server-PT"),
            RuntimeConfigurationTarget(device_name="HQ-PC-01", model="PC-PT"),
        ]

    def apply_actions(self, actions):
        self.apply_calls.append([item.id for item in actions])
        return [RuntimeActionMutation(action_id=item.id, applied=True) for item in actions]

    def verify(self, expectation):
        self.verify_calls.append(expectation.id)
        status = (
            self.direct_status
            if expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
            else self.behavior_status
        )
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_kind=expectation.evidence_kind,
            evidence_method="fake_fresh_service_observation",
            fresh_evidence=True,
        )


def _compiled():
    enterprise, topology, configuration, capabilities = _fixture()
    result = compile_enterprise_services(
        enterprise, topology, configuration, capabilities=capabilities,
    )
    assert result.is_valid
    return result.plan, capabilities


def _foundation(plan):
    return {
        requirement.configuration_action_id: ActionExecutionStatus.VERIFIED
        for requirement in plan.foundational_requirements
    }


def test_stale_topology_or_configuration_stops_before_runtime_mutation():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash="stale",
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.SOURCE_TOPOLOGY_MISMATCH
    assert not runtime.apply_calls


def test_foundation_must_be_verified_and_e6_never_runs_e5_implicitly():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()
    foundation = _foundation(plan)
    foundation[next(iter(foundation))] = ActionExecutionStatus.APPLIED

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=foundation,
        capabilities=capabilities,
    )

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    assert not runtime.apply_calls


def test_unknown_application_capability_is_skipped_not_attempted():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()
    capabilities["Server-PT:dns"].application_support = CapabilityStatus.UNKNOWN

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
    )
    dns_ids = {
        action.id for action in plan.actions if action.service_type is ServiceType.DNS
    }
    attempted = {action_id for call in runtime.apply_calls for action_id in call}

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert not dns_ids.intersection(attempted)


def test_unsupported_application_capability_is_skipped_with_distinct_reason():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()
    capabilities["Server-PT:dns"].application_support = CapabilityStatus.UNSUPPORTED

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
    )
    dns_results = [
        item for item in result.action_results
        if next(action for action in plan.actions if action.id == item.action_id).service_type
        is ServiceType.DNS
    ]

    assert dns_results
    assert all(item.status is ActionExecutionStatus.SKIPPED for item in dns_results)
    assert all(
        item.failure_code is ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
        for item in dns_results
    )


def test_action_capability_override_gates_only_the_unverified_action():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()
    http = capabilities["Server-PT:http"]
    http.application_support = CapabilityStatus.SUPPORTED
    http.action_application_support = {
        ServiceActionType.SET_HTTP_CONTENT.value: CapabilityStatus.UNKNOWN,
    }

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
    )
    http_actions = [
        item for item in result.action_results
        if next(action for action in plan.actions if action.id == item.action_id).service_type
        is ServiceType.HTTP
    ]
    by_type = {
        next(action for action in plan.actions if action.id == item.action_id).action_type: item
        for item in http_actions
    }

    assert by_type[ServiceActionType.ENABLE_HTTP].status is ActionExecutionStatus.APPLIED
    assert by_type[ServiceActionType.SET_HTTP_CONTENT].status is ActionExecutionStatus.SKIPPED
    assert (
        by_type[ServiceActionType.SET_HTTP_CONTENT].failure_code
        is ConfigurationFailureCode.CAPABILITY_UNKNOWN
    )


def test_behavioral_success_can_prove_usability_when_direct_getter_is_unobservable():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
    )

    assert result.status is ConfigurationApplicationStatus.VERIFIED
    assert all(item.usability_status is ActionExecutionStatus.VERIFIED for item in result.services)
    assert all(item.direct_readback_status is ActionExecutionStatus.PARTIAL for item in result.services)


def test_applied_service_is_not_verified_when_behavior_fails():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()
    runtime.behavior_status = ActionExecutionStatus.FAILED

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
    )

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert any(item.usability_status is ActionExecutionStatus.FAILED for item in result.services)


def test_http_hostname_is_dependency_blocked_when_dns_resolution_fails():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()

    original_verify = runtime.verify

    def verify(expectation):
        if expectation.kind.value == "dns_resolution":
            return RuntimeServiceVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.FAILED,
                evidence_kind=expectation.evidence_kind,
                evidence_method="fake_dns_failure",
                fresh_evidence=True,
            )
        return original_verify(expectation)

    runtime.verify = verify
    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
    )
    composed = next(
        item for item in result.verification_results
        if item.evidence_kind is ServiceEvidenceKind.COMPOSED_BEHAVIORAL
    )

    assert composed.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
    assert composed.failure_code is ConfigurationFailureCode.DEPENDENCY_BLOCKED


def test_runtime_target_model_mismatch_stops_without_partial_application():
    plan, capabilities = _compiled()
    runtime = FakeServiceRuntime()
    runtime.inventory = lambda: [
        RuntimeConfigurationTarget(device_name="HQ-SERVER-01", model="Other-Server"),
        RuntimeConfigurationTarget(device_name="HQ-PC-01", model="PC-PT"),
    ]

    result = ServiceApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        actual_source_configuration_hash=plan.source_configuration_hash,
        foundational_statuses=_foundation(plan),
        capabilities=capabilities,
    )

    assert result.failure_code is ConfigurationFailureCode.TARGET_IDENTITY_MISMATCH
    assert not runtime.apply_calls
