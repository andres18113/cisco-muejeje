"""Resultados E8: aplicación, observación y conducta permanecen separadas."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
)
from .evidence import EvidenceRecord
from .execution import ApplicationExecutionJournal, DirtyState


class SecurityVerificationStage(str, Enum):
    BASELINE = "baseline"
    DIRECT_STATE = "direct_state"
    ENFORCEMENT_BEHAVIOR = "enforcement_behavior"
    CLEANUP_RECOVERY = "cleanup_recovery"


class RuntimeSecurityVerification(BaseModel):
    expectation_id: str
    stage: SecurityVerificationStage
    status: ActionExecutionStatus
    evidence_method: str = ""
    fresh_evidence: bool = False
    fields: dict[str, FieldVerificationStatus] = Field(default_factory=dict)
    message: str = ""


class SecurityVerificationResult(BaseModel):
    expectation_id: str
    action_id: str
    policy_id: str
    baseline_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    direct_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    enforcement_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    cleanup_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    evidence_methods: list[str] = Field(default_factory=list)
    fresh_evidence: bool = False
    fields: dict[str, FieldVerificationStatus] = Field(default_factory=dict)
    message: str = ""


class SecurityApplicationResult(BaseModel):
    security_plan_id: str
    security_semantic_hash: str
    source_topology_hash: str
    source_configuration_hash: str
    source_service_hash: str = ""
    source_voice_hash: str = ""
    runtime_context: ConfigurationRuntimeContext = Field(
        default_factory=ConfigurationRuntimeContext,
    )
    status: ConfigurationApplicationStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    action_results: list[ActionApplicationResult] = Field(default_factory=list)
    verification_results: list[SecurityVerificationResult] = Field(default_factory=list)
    cleanup_results: list[ActionApplicationResult] = Field(default_factory=list)
    preflight_errors: list[str] = Field(default_factory=list)
    deployment_id: str = ""
    execution_journal: ApplicationExecutionJournal | None = None
    dirty_state: DirtyState = DirtyState.CLEAN
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    duration_ms: int = 0

    def compact_summary(self) -> dict[str, object]:
        action_counts: dict[str, int] = {}
        for item in self.action_results:
            action_counts[item.status.value] = action_counts.get(item.status.value, 0) + 1
        verification_counts: dict[str, int] = {}
        for item in self.verification_results:
            statuses = (
                item.baseline_status,
                item.direct_status,
                item.enforcement_status,
                item.cleanup_status,
            )
            for status in statuses:
                if status is ActionExecutionStatus.SKIPPED:
                    continue
                verification_counts[status.value] = (
                    verification_counts.get(status.value, 0) + 1
                )
        return {
            "security_plan_id": self.security_plan_id,
            "security_semantic_hash": self.security_semantic_hash,
            "source_topology_hash": self.source_topology_hash,
            "source_configuration_hash": self.source_configuration_hash,
            "source_service_hash": self.source_service_hash,
            "source_voice_hash": self.source_voice_hash,
            "runtime_context": self.runtime_context.model_dump(mode="json"),
            "status": self.status.value,
            "failure_code": self.failure_code.value,
            "actions": dict(sorted(action_counts.items())),
            "verification": dict(sorted(verification_counts.items())),
            "cleanup_actions": len(self.cleanup_results),
            "preflight_errors": self.preflight_errors,
            "deployment_id": self.deployment_id,
            "dirty_state": self.dirty_state.value,
            "execution_journal": (
                self.execution_journal.compact_summary()
                if self.execution_journal else None
            ),
            "evidence_records": [item.compact_summary() for item in self.evidence_records],
            "duration_ms": self.duration_ms,
        }
