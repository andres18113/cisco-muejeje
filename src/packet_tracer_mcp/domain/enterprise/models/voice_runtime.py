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


class PhoneExecutionMethod(str, Enum):
    """Canal utilizado para iniciar/observar una operación telefónica."""

    STRUCTURED_API = "structured_api"
    PACKET_TRACER_NATIVE_UI = "packet_tracer_native_ui"
    HYBRID = "hybrid"
    UNOBSERVABLE = "unobservable"


class RuntimePhoneRegistration(BaseModel):
    expectation_id: str
    phone_id: str
    extension: str
    status: ActionExecutionStatus
    direct_readback: FieldVerificationStatus = FieldVerificationStatus.UNKNOWN
    evidence_method: str = ""
    fresh_evidence: bool = False
    message: str = ""
    #: What the call control reports the phone registered from, and what the
    #: phone itself reports on its voice SVI. Two independent reads of one
    #: fact, kept apart so that agreeing is evidence and differing is a defect.
    call_control_ipv4: str = ""
    endpoint_ipv4: str = ""
    endpoint_interface: str = ""
    #: Did the phone actually create the SVI the plan expects it to address on?
    #: A phone that never learned its voice VLAN and one that learned it and got
    #: no lease both read as no address, and they are different findings.
    endpoint_interface_present: bool = False
    #: Does that SVI expose an address getter at all? Measured on 9.0.1.0858, an
    #: AccessPoint-PT port comes up powered and exposes none, and the empty
    #: string that comes back is indistinguishable from a port that answered and
    #: holds nothing. On the phone channel that difference is the whole
    #: question: one is "the phone did not acquire", the other is "we did not
    #: look at anything that could answer".
    endpoint_address_channel: bool = False
    #: Was this phone ever asked to acquire? A voice SVI with DHCP off has not
    #: failed to lease -- it never solicited, and the defect is upstream of the
    #: pool entirely. None is the third state and the honest default: the port
    #: exposes no DHCP getter, so nothing was read. Absent is not False.
    endpoint_dhcp_enabled: bool | None = None
    #: The same two questions asked of the phone itself. Packet Tracer does not
    #: put the same getters on a device and on its ports -- the AccessPoint-PT
    #: probe that settled addressability on this build had to ask both -- and a
    #: voice SVI that exposes no DHCP flag does not mean the phone has none.
    #: These never overwrite the interface the plan named; they travel beside it,
    #: because "the phone holds an address its SVI does not report" is a finding
    #: about where to read and not a phone that acquired on Vlan20.
    device_ipv4: str = ""
    device_dhcp_enabled: bool | None = None


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
    execution_method: PhoneExecutionMethod = PhoneExecutionMethod.UNOBSERVABLE
    message: str = ""


class PhoneRegistrationResult(RuntimePhoneRegistration):
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    #: E7's own claim about the phone's address, made only where E5 handed
    #: ownership over. UNKNOWN means E5 still owns it and E7 said nothing.
    addressing_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    addressing_message: str = ""


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
    addressing_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
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
