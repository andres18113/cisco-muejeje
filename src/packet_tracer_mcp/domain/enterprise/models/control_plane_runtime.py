"""Resultados E9 que separan configuración, evidencia y failover."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    ConvergenceReport,
    FieldVerificationStatus,
    RuntimeActionMutation,
)
from .control_plane import ControlPlaneVerificationKind
from .evidence import EvidenceRecord
from .execution import ApplicationExecutionJournal, DirtyState


class ControlPlaneExecutionStage(str, Enum):
    CONFIGURED = "configured"
    APPLIED = "applied"
    OBSERVED = "observed"
    BEHAVIOR = "behavior"
    FAILOVER = "failover"
    RESTORE = "restore"


class FailureTransitionPhase(str, Enum):
    """Observable milestones in one bounded fault/restore execution."""

    BASELINE_OBSERVED = "baseline_observed"
    FAULT_INJECTED = "fault_injected"
    FAILOVER_OBSERVED = "failover_observed"
    RESTORE_DISPATCHED = "restore_dispatched"
    RECOVERY_OBSERVED = "recovery_observed"


class FailureScenarioTransition(BaseModel):
    sequence: int
    phase: FailureTransitionPhase
    elapsed_ms: int
    status: ActionExecutionStatus
    evidence_method: str = ""
    message: str = ""


class RuntimeControlPlaneVerification(BaseModel):
    expectation_id: str
    stage: ControlPlaneExecutionStage
    status: ActionExecutionStatus
    evidence_method: str = ""
    fresh_evidence: bool = False
    fields: dict[str, FieldVerificationStatus] = Field(default_factory=dict)
    message: str = ""
    convergence: ConvergenceReport | None = None


class ControlPlaneVerificationResult(BaseModel):
    expectation_id: str
    action_id: str
    kind: ControlPlaneVerificationKind
    stage: ControlPlaneExecutionStage
    status: ActionExecutionStatus
    evidence_method: str = ""
    fresh_evidence: bool = False
    fields: dict[str, FieldVerificationStatus] = Field(default_factory=dict)
    message: str = ""
    convergence: ConvergenceReport | None = None


class RuntimeFailureScenarioResult(BaseModel):
    scenario_id: str
    before: RuntimeControlPlaneVerification | None = None
    injection: RuntimeActionMutation | None = None
    during: RuntimeControlPlaneVerification | None = None
    restore_attempted: bool = False
    restore: RuntimeActionMutation | None = None
    after: RuntimeControlPlaneVerification | None = None
    transitions: list[FailureScenarioTransition] = Field(default_factory=list)
    message: str = ""


class FailureScenarioResult(BaseModel):
    scenario_id: str
    status: ActionExecutionStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    baseline_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    injection_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    failover_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    restore_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    recovery_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    restore_attempted: bool = False
    before: RuntimeControlPlaneVerification | None = None
    during: RuntimeControlPlaneVerification | None = None
    after: RuntimeControlPlaneVerification | None = None
    transitions: list[FailureScenarioTransition] = Field(default_factory=list)
    message: str = ""


class ControlPlaneApplicationResult(BaseModel):
    control_plane_plan_id: str
    control_plane_semantic_hash: str
    source_topology_hash: str
    source_configuration_hash: str
    source_security_hash: str = ""
    runtime_context: ConfigurationRuntimeContext = Field(
        default_factory=ConfigurationRuntimeContext,
    )
    status: ConfigurationApplicationStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    configured_status: ActionExecutionStatus = ActionExecutionStatus.COMPILED
    applied_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    observed_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    behavior_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    failover_status: ActionExecutionStatus = ActionExecutionStatus.SKIPPED
    action_results: list[ActionApplicationResult] = Field(default_factory=list)
    mutation_action_ids: list[str] = Field(default_factory=list)
    retained_action_ids: list[str] = Field(default_factory=list)
    observed_results: list[ControlPlaneVerificationResult] = Field(default_factory=list)
    behavior_results: list[ControlPlaneVerificationResult] = Field(default_factory=list)
    failover_results: list[ControlPlaneVerificationResult] = Field(default_factory=list)
    scenario_results: list[FailureScenarioResult] = Field(default_factory=list)
    preflight_errors: list[str] = Field(default_factory=list)
    deployment_id: str = ""
    execution_journal: ApplicationExecutionJournal | None = None
    dirty_state: DirtyState = DirtyState.CLEAN
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    duration_ms: int = 0

    def compact_summary(self) -> dict[str, object]:
        return {
            "control_plane_plan_id": self.control_plane_plan_id,
            "control_plane_semantic_hash": self.control_plane_semantic_hash,
            "source_topology_hash": self.source_topology_hash,
            "source_configuration_hash": self.source_configuration_hash,
            "source_security_hash": self.source_security_hash,
            "runtime_context": self.runtime_context.model_dump(mode="json"),
            "status": self.status.value,
            "failure_code": self.failure_code.value,
            "stages": {
                "configured": self.configured_status.value,
                "applied": self.applied_status.value,
                "observed": self.observed_status.value,
                "behavior": self.behavior_status.value,
                "failover": self.failover_status.value,
            },
            "actions": len(self.action_results),
            "mutation_action_ids": self.mutation_action_ids,
            "retained_action_ids": self.retained_action_ids,
            "observations": len(self.observed_results),
            "behavior_checks": len(self.behavior_results),
            "unbound_failover_checks": len(self.failover_results),
            "failure_scenarios": len(self.scenario_results),
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
