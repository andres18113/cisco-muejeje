"""Resultados E6 reutilizando los estados de ejecución establecidos en E5."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
)
from .service_plan import ServiceEvidenceKind, ServiceType


class RuntimeServiceVerification(BaseModel):
    expectation_id: str
    status: ActionExecutionStatus
    evidence_kind: ServiceEvidenceKind
    evidence_method: str = ""
    fresh_evidence: bool = False
    observed: dict[str, str | int | bool] = Field(default_factory=dict)
    message: str = ""


class ServiceVerificationResult(RuntimeServiceVerification):
    service_id: str
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE


class ServiceOutcome(BaseModel):
    service_id: str
    service_type: ServiceType
    application_status: ActionExecutionStatus
    direct_readback_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    behavioral_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    usability_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN


class ServiceApplicationResult(BaseModel):
    service_plan_id: str
    service_semantic_hash: str
    source_topology_hash: str
    source_configuration_hash: str
    runtime_context: ConfigurationRuntimeContext = Field(default_factory=ConfigurationRuntimeContext)
    status: ConfigurationApplicationStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    action_results: list[ActionApplicationResult] = Field(default_factory=list)
    verification_results: list[ServiceVerificationResult] = Field(default_factory=list)
    services: list[ServiceOutcome] = Field(default_factory=list)
    preflight_errors: list[str] = Field(default_factory=list)
    duration_ms: int = 0

    def compact_summary(self) -> dict[str, object]:
        action_counts: dict[str, int] = {}
        for item in self.action_results:
            action_counts[item.status.value] = action_counts.get(item.status.value, 0) + 1
        verification_counts: dict[str, int] = {}
        for item in self.verification_results:
            verification_counts[item.status.value] = verification_counts.get(item.status.value, 0) + 1
        return {
            "service_plan_id": self.service_plan_id,
            "service_semantic_hash": self.service_semantic_hash,
            "source_topology_hash": self.source_topology_hash,
            "source_configuration_hash": self.source_configuration_hash,
            "runtime_context": self.runtime_context.model_dump(mode="json"),
            "status": self.status.value,
            "failure_code": self.failure_code.value,
            "actions": dict(sorted(action_counts.items())),
            "verification": dict(sorted(verification_counts.items())),
            "services": [item.model_dump(mode="json") for item in self.services],
            "preflight_errors": self.preflight_errors,
            "duration_ms": self.duration_ms,
        }
