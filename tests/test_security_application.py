"""E8 offline: security application preserves every evidence stage."""

from __future__ import annotations

from collections.abc import Sequence

from src.packet_tracer_mcp.application.use_cases.apply_security import (
    SecurityApplicator,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    SecurityAction,
    SecurityCapabilityDimension,
    SecurityCapabilityProfile,
    SecurityCapabilityStatus,
    SecurityVerificationExpectation,
    SecurityVerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_runtime import (
    RuntimeSecurityVerification,
    SecurityVerificationStage,
)
from tests.test_enterprise_security import _compile


class FakeSecurityRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.baseline_status = ActionExecutionStatus.VERIFIED
        self.direct_status = ActionExecutionStatus.VERIFIED
        self.enforcement_status = ActionExecutionStatus.VERIFIED
        self.cleanup_status = ActionExecutionStatus.VERIFIED
        self.failed_action_id = ""

    def inventory(self):
        self.calls.append(("inventory", []))
        return [
            RuntimeConfigurationTarget(
                device_name="HQ-R1", model="2911",
                interfaces=["GigabitEthernet0/0", "GigabitEthernet0/1"],
            ),
            RuntimeConfigurationTarget(
                device_name="HQ-SW1", model="2960-24TT",
                interfaces=["FastEthernet0/1", "GigabitEthernet0/1"],
            ),
        ]

    def apply_actions(self, actions: Sequence[SecurityAction]):
        self.calls.append(("apply", [item.id for item in actions]))
        return [RuntimeActionMutation(
            action_id=item.id,
            applied=item.id != self.failed_action_id,
            failure_code=(
                ConfigurationFailureCode.NONE
                if item.id != self.failed_action_id
                else ConfigurationFailureCode.SECURITY_APPLICATION_FAILED
            ),
        ) for item in actions]

    def observe(self, expectations: Sequence[SecurityVerificationExpectation]):
        self.calls.append(("observe", [item.id for item in expectations]))
        return [RuntimeSecurityVerification(
            expectation_id=item.id,
            stage=SecurityVerificationStage.DIRECT_STATE,
            status=self.direct_status,
            evidence_method="fake_direct",
            fresh_evidence=self.direct_status is ActionExecutionStatus.VERIFIED,
            fields={"state": (
                FieldVerificationStatus.VERIFIED
                if self.direct_status is ActionExecutionStatus.VERIFIED
                else FieldVerificationStatus.UNOBSERVABLE
            )},
        ) for item in expectations]

    def verify_behavior(
        self,
        expectations: Sequence[SecurityVerificationExpectation],
        stage: SecurityVerificationStage,
    ):
        self.calls.append((stage.value, [item.id for item in expectations]))
        status = {
            SecurityVerificationStage.BASELINE: self.baseline_status,
            SecurityVerificationStage.ENFORCEMENT_BEHAVIOR: self.enforcement_status,
            SecurityVerificationStage.CLEANUP_RECOVERY: self.cleanup_status,
        }[stage]
        return [RuntimeSecurityVerification(
            expectation_id=item.id,
            stage=stage,
            status=status,
            evidence_method="fake_" + stage.value,
            fresh_evidence=status is ActionExecutionStatus.VERIFIED,
        ) for item in expectations]

    def cleanup_actions(self, actions: Sequence[SecurityAction]):
        self.calls.append(("cleanup", [item.id for item in actions]))
        return [RuntimeActionMutation(action_id=item.id, applied=True) for item in actions]


def _foundations(plan):
    return {
        item.source_id: ActionExecutionStatus.VERIFIED
        for item in plan.foundational_requirements
    }


def _capabilities():
    return {
        "2911": SecurityCapabilityProfile.supported("2911"),
        "2960-24TT": SecurityCapabilityProfile.supported("2960-24TT"),
    }


def _apply(runtime, *, cleanup_control=False, **overrides):
    plan = _compile().plan
    kwargs = {
        "actual_source_topology_hash": plan.source_topology_hash,
        "actual_source_configuration_hash": plan.source_configuration_hash,
        "actual_source_service_hash": plan.source_service_hash,
        "foundational_statuses": _foundations(plan),
        "capabilities": _capabilities(),
        "cleanup_control": cleanup_control,
    }
    kwargs.update(overrides)
    return SecurityApplicator(runtime).apply(plan, **kwargs)


def test_source_hash_mismatch_stops_before_inventory_or_mutation():
    runtime = FakeSecurityRuntime()
    result = _apply(runtime, actual_source_configuration_hash="stale")

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.SOURCE_CONFIGURATION_MISMATCH
    assert runtime.calls == []


def test_unverified_foundation_stops_before_inventory_or_mutation():
    runtime = FakeSecurityRuntime()
    result = _apply(runtime, foundational_statuses={})

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    assert runtime.calls == []


def test_failed_deny_baseline_prevents_all_security_mutations():
    runtime = FakeSecurityRuntime()
    runtime.baseline_status = ActionExecutionStatus.FAILED
    result = _apply(runtime)

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.SECURITY_BASELINE_FAILED
    assert [item[0] for item in runtime.calls] == ["inventory", "baseline"]


def test_verified_security_keeps_compiled_applied_direct_and_behavior_distinct():
    runtime = FakeSecurityRuntime()
    result = _apply(runtime)

    assert result.status is ConfigurationApplicationStatus.VERIFIED
    assert all(item.status is ActionExecutionStatus.APPLIED for item in result.action_results)
    deny = next(
        item for item in result.verification_results
        if item.policy_id == "deny-guest-http"
    )
    assert deny.baseline_status is ActionExecutionStatus.VERIFIED
    assert deny.enforcement_status is ActionExecutionStatus.VERIFIED
    assert deny.cleanup_status is ActionExecutionStatus.SKIPPED
    assert "fake_baseline" in deny.evidence_methods
    assert "fake_enforcement_behavior" in deny.evidence_methods


def test_disposable_cleanup_control_proves_allow_deny_allow_sequence():
    runtime = FakeSecurityRuntime()
    result = _apply(runtime, cleanup_control=True)

    assert result.status is ConfigurationApplicationStatus.VERIFIED
    assert [item[0] for item in runtime.calls].index("baseline") < [
        item[0] for item in runtime.calls
    ].index("apply")
    assert [item[0] for item in runtime.calls].index("cleanup") < [
        item[0] for item in runtime.calls
    ].index("cleanup_recovery")
    deny = next(
        item for item in result.verification_results
        if item.policy_id == "deny-guest-http"
    )
    assert deny.cleanup_status is ActionExecutionStatus.VERIFIED
    assert len(result.cleanup_results) == len(result.action_results)


def test_unobservable_direct_state_is_partial_even_when_behavior_is_verified():
    runtime = FakeSecurityRuntime()
    runtime.direct_status = ActionExecutionStatus.UNOBSERVABLE
    result = _apply(runtime)

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert result.failure_code is ConfigurationFailureCode.DIRECT_READBACK_UNOBSERVABLE
    assert any(
        item.direct_status is ActionExecutionStatus.UNOBSERVABLE
        for item in result.verification_results
    )


def test_failed_enforcement_is_not_mistaken_for_applied_security():
    runtime = FakeSecurityRuntime()
    runtime.enforcement_status = ActionExecutionStatus.FAILED
    result = _apply(runtime)

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.SECURITY_ENFORCEMENT_FAILED


def test_unknown_runtime_capability_skips_actions_without_calling_them_applied():
    runtime = FakeSecurityRuntime()
    capabilities = {
        model: SecurityCapabilityProfile(
            model=model,
            dimensions={
                SecurityCapabilityDimension.ACL_BEHAVIORAL:
                    SecurityCapabilityStatus.SUPPORTED,
            },
        )
        for model in ("2911", "2960-24TT")
    }
    result = _apply(runtime, capabilities=capabilities)

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert any(item.status is ActionExecutionStatus.SKIPPED for item in result.action_results)
    submitted = {action_id for kind, ids in runtime.calls if kind == "apply" for action_id in ids}
    skipped = {
        item.action_id for item in result.action_results
        if item.status is ActionExecutionStatus.SKIPPED
    }
    assert submitted.isdisjoint(skipped)


def test_unknown_acl_behavior_blocks_deny_baseline_before_any_mutation():
    runtime = FakeSecurityRuntime()

    result = _apply(runtime, capabilities={})

    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.SECURITY_BASELINE_FAILED
    assert [kind for kind, _ids in runtime.calls] == ["inventory"]


def test_unobservable_security_behavior_is_partial_not_falsely_failed_or_verified():
    runtime = FakeSecurityRuntime()
    runtime.enforcement_status = ActionExecutionStatus.UNOBSERVABLE

    result = _apply(runtime)

    assert result.status is ConfigurationApplicationStatus.PARTIAL
    assert result.failure_code is ConfigurationFailureCode.SECURITY_BEHAVIOR_UNOBSERVABLE


def test_unknown_readback_capability_is_not_queried_or_promoted_to_verified():
    runtime = FakeSecurityRuntime()
    capabilities = _capabilities()
    capabilities["2911"].dimensions[
        SecurityCapabilityDimension.ACL_READBACK
    ] = SecurityCapabilityStatus.UNKNOWN
    plan = _compile().plan

    result = _apply(runtime, capabilities=capabilities)

    acl_ids = {
        item.id for item in plan.verification_expectations
        if item.kind is SecurityVerificationKind.ACL_DIRECT_STATE
    }
    observed_ids = {
        item_id for kind, ids in runtime.calls if kind == "observe" for item_id in ids
    }
    acl_results = [
        item for item in result.verification_results if item.expectation_id in acl_ids
    ]
    assert observed_ids.isdisjoint(acl_ids)
    assert acl_results
    assert all(
        item.direct_status is ActionExecutionStatus.UNOBSERVABLE
        and "security_capability_gate" in item.evidence_methods
        for item in acl_results
    )
