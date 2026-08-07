"""Resultados E7: aplicar, registrar y llamar son estados independientes."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
)
from .evidence import EvidenceRecord
from .execution import ApplicationExecutionJournal, DirtyState
from .voice_plan import CallExpectationResult


class CallState(str, Enum):
    IDLE = "idle"
    DIALING = "dialing"
    RINGING = "ringing"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    UNKNOWN = "unknown"


class RuntimePhoneRegistration(BaseModel):
    expectation_id: str
    phone_id: str
    extension: str
    status: ActionExecutionStatus
    direct_readback: FieldVerificationStatus = FieldVerificationStatus.UNKNOWN
    evidence_method: str = ""
    fresh_evidence: bool = False
    message: str = ""


class RuntimeCallObservation(BaseModel):
    call_expectation_id: str
    call_attempt_id: str
    source_phone_id: str
    dialed_extension: str
    status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    states: list[CallState] = Field(default_factory=list)
    connected: bool = False
    teardown_verified: bool = False
    observed_after_ns: int = 0
    fresh_evidence: bool = False
    evidence_method: str = ""
    message: str = ""


class PhoneRegistrationResult(RuntimePhoneRegistration):
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE


class CallVerificationResult(RuntimeCallObservation):
    expected_result: CallExpectationResult
    expected_target_phone_id: str = ""
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE


class PhoneVoiceOutcome(BaseModel):
    phone_id: str
    extension: str
    application_status: ActionExecutionStatus
    registration_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    direct_registration_readback: FieldVerificationStatus = FieldVerificationStatus.UNKNOWN
    call_behavior_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    usability_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN


class VoiceApplicationResult(BaseModel):
    voice_plan_id: str
    voice_semantic_hash: str
    source_topology_hash: str
    source_configuration_hash: str
    source_service_hash: str = ""
    runtime_context: ConfigurationRuntimeContext = Field(default_factory=ConfigurationRuntimeContext)
    status: ActionExecutionStatus
    application_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    action_results: list[ActionApplicationResult] = Field(default_factory=list)
    registrations: list[PhoneRegistrationResult] = Field(default_factory=list)
    calls: list[CallVerificationResult] = Field(default_factory=list)
    phones: list[PhoneVoiceOutcome] = Field(default_factory=list)
    audio_observability: FieldVerificationStatus = FieldVerificationStatus.UNOBSERVABLE
    preflight_errors: list[str] = Field(default_factory=list)
    deployment_id: str = ""
    execution_journal: ApplicationExecutionJournal | None = None
    dirty_state: DirtyState = DirtyState.CLEAN
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    duration_ms: int = 0

    def compact_summary(self) -> dict[str, object]:
        def counts(items):
            result: dict[str, int] = {}
            for item in items:
                result[item.status.value] = result.get(item.status.value, 0) + 1
            return dict(sorted(result.items()))

        return {
            "voice_plan_id": self.voice_plan_id,
            "voice_semantic_hash": self.voice_semantic_hash,
            "source_topology_hash": self.source_topology_hash,
            "source_configuration_hash": self.source_configuration_hash,
            "source_service_hash": self.source_service_hash,
            "runtime_context": self.runtime_context.model_dump(mode="json"),
            "status": self.status.value,
            "application_status": self.application_status.value,
            "failure_code": self.failure_code.value,
            "actions": counts(self.action_results),
            "registrations": counts(self.registrations),
            "calls": counts(self.calls),
            "phones": [item.model_dump(mode="json") for item in self.phones],
            "audio_observability": self.audio_observability.value,
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
