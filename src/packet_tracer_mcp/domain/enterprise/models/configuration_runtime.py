"""Resultados E5 que mantienen COMPILED, APPLIED y VERIFIED separados."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .deployment import EnvironmentFingerprint
from .evidence import EvidenceRecord
from .execution import (
    ApplicationExecutionJournal,
    DirtyState,
    MutationDisposition,
    OperationSemantics,
)


class ActionExecutionStatus(str, Enum):
    """Estado de una acción a lo largo de su ciclo de vida.

    Qué evento produce APPLIED
    --------------------------
    Hasta R1-E esto no estaba escrito en ninguna parte. La arquitectura decía
    con qué NO se confunde -- `compiled != applied`, `applied != observed`,
    "a result may be APPLIED and still be UNOBSERVABLE" -- pero ningún source
    nombraba el evento que lo produce, y el enum no tenía documentación.

    Se fija aquí lo único que el transporte puede sustentar:

        APPLIED = el payload fue aceptado por el canal del runtime.

    Ni más ni menos. El canal de configuración es fire-and-forget: entrega el
    payload y no recibe acuse de Packet Tracer. Por eso APPLIED no puede
    significar "el backend confirmó la aplicación" -- no existe en el sistema
    ninguna señal capaz de sostener esa afirmación --, y tampoco "el estado
    quedó aplicado", que es precisamente lo que la verificación va a averiguar.

    Esto DOCUMENTA el comportamiento vigente; no lo cambia. Si la intención
    original era la lectura más fuerte ("el estado intencionado quedó aplicado
    aunque no sea observable"), entonces el transporte actual no puede
    entregarla y eso es una decisión semántica propia, no un ajuste de wording.

    FAILED aquí es una certeza LOCAL: el payload no salió del proceso, así que
    no puede aplicarse más tarde. VERIFIED es lo contrario de APPLIED en cuanto
    a evidencia: sale de releer el estado, nunca del envío.
    """

    INTENDED = "intended"
    COMPILED = "compiled"
    # Aceptado por el canal del runtime. NO implica efecto en el backend.
    APPLIED = "applied"
    # Releído del dispositivo. Es el único que afirma efecto.
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    UNOBSERVABLE = "unobservable"
    NO_OP = "no_op"
    REASSERTED = "reasserted"


class ConfigurationApplicationStatus(str, Enum):
    APPLIED = "applied"
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConfigurationFailureCode(str, Enum):
    NONE = "none"
    SOURCE_TOPOLOGY_MISMATCH = "source_topology_mismatch"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_IDENTITY_MISMATCH = "target_identity_mismatch"
    INTERFACE_NOT_FOUND = "interface_not_found"
    CAPABILITY_UNKNOWN = "capability_unknown"
    CAPABILITY_UNSUPPORTED = "capability_unsupported"
    APPLICATION_FAILED = "application_failed"
    SESSION_FAILED = "session_failed"
    CONVERGENCE_TIMEOUT = "convergence_timeout"
    VERIFICATION_FAILED = "verification_failed"
    OBSERVABILITY_LIMITATION = "observability_limitation"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    SOURCE_CONFIGURATION_MISMATCH = "source_configuration_mismatch"
    FOUNDATIONAL_CONFIGURATION_MISSING = "foundational_configuration_missing"
    SERVICE_COMPILE_ERROR = "service_compile_error"
    SERVICE_HOST_MISSING = "service_host_missing"
    BEHAVIORAL_VERIFICATION_FAILED = "behavioral_verification_failed"
    DIRECT_READBACK_UNOBSERVABLE = "direct_readback_unobservable"
    CLEANUP_FAILED = "cleanup_failed"
    VOICE_COMPILE_ERROR = "voice_compile_error"
    CALL_CONTROL_APPLICATION_FAILED = "call_control_application_failed"
    PHONE_REGISTRATION_TIMEOUT = "phone_registration_timeout"
    PHONE_REGISTRATION_UNOBSERVABLE = "phone_registration_unobservable"
    CALL_SETUP_FAILED = "call_setup_failed"
    CALL_CONNECT_TIMEOUT = "call_connect_timeout"
    CALL_TEARDOWN_FAILED = "call_teardown_failed"
    SECURITY_COMPILE_ERROR = "security_compile_error"
    SECURITY_BASELINE_FAILED = "security_baseline_failed"
    SECURITY_APPLICATION_FAILED = "security_application_failed"
    SECURITY_DIRECT_READBACK_FAILED = "security_direct_readback_failed"
    SECURITY_ENFORCEMENT_FAILED = "security_enforcement_failed"
    SECURITY_BEHAVIOR_UNOBSERVABLE = "security_behavior_unobservable"
    SECURITY_CLEANUP_FAILED = "security_cleanup_failed"
    DEPLOYMENT_MANIFEST_REQUIRED = "deployment_manifest_required"
    ENVIRONMENT_FINGERPRINT_MISMATCH = "environment_fingerprint_mismatch"


class FieldVerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"
    UNOBSERVABLE = "unobservable"


class ConvergenceReport(BaseModel):
    attempts: int = 0
    elapsed_ms: int = 0
    final_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    last_observable_state: str = ""
    #: Optional structured terminal evidence for convergence observers.  The
    #: generic fields above remain the stable summary; observer-specific
    #: details preserve the exact members and authority dimensions needed to
    #: audit a grouped decision without parsing a human message.
    details: dict[str, object] = Field(default_factory=dict)


class RuntimeConfigurationTarget(BaseModel):
    device_name: str
    model: str
    interfaces: list[str] = Field(default_factory=list)
    runtime_identifier: str = ""
    runtime_identifier_stable: bool = False
    runtime_fingerprint: str = ""


class ConfigurationRuntimeContext(BaseModel):
    backend: str = ""
    backend_version: str = ""
    capability_snapshot_hash: str = ""
    environment_fingerprint: EnvironmentFingerprint | None = None

    @property
    def evidence_backend(self) -> str:
        if self.environment_fingerprint is not None:
            return self.environment_fingerprint.backend
        return self.backend

    @property
    def evidence_backend_version(self) -> str:
        if self.environment_fingerprint is not None:
            return self.environment_fingerprint.backend_version
        return self.backend_version

    @property
    def environment_semantic_hash(self) -> str:
        if self.environment_fingerprint is None:
            return ""
        return self.environment_fingerprint.semantic_hash


class RuntimeActionMutation(BaseModel):
    action_id: str
    applied: bool
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    disposition: MutationDisposition = MutationDisposition.UNKNOWN
    message: str = ""
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    batch_id: str = ""


def mutation_execution_status(
    mutation: RuntimeActionMutation,
) -> ActionExecutionStatus:
    """Estado de ejecución de una mutación despachada. Una sola definición.

    Vivía duplicada, idéntica, en cinco applicators.

    `APPLIED` acá significa DESPACHADO POR EL CANAL DEL RUNTIME, no "el backend
    confirmó el efecto". No es una laxitud heredada: es el contrato que la
    arquitectura fija de forma explícita.

        docs/architecture/e95-stabilization.md   compiled != applied
                                                 applied  != observed
        docs/architecture/enterprise-control-plane.md
            "A result may be APPLIED and still be UNOBSERVABLE."

    Por eso el canal de configuración puede ser asíncrono sin mentir: el envío
    sostiene APPLIED y nada más. Quien afirma el efecto es la verificación, que
    relee el estado y produce VERIFIED, y ningún camino promueve lo uno a lo
    otro. Colapsar los dos estados en uno "más conservador" no agregaría
    seguridad -- borraría la distinción que ya los mantiene separados.

    `applied=False` sí es una certeza local: el payload no salió del proceso,
    así que no puede aplicarse más tarde.
    """
    if not mutation.applied:
        return ActionExecutionStatus.FAILED
    if mutation.disposition is MutationDisposition.NO_OP:
        return ActionExecutionStatus.NO_OP
    if mutation.disposition is MutationDisposition.REASSERTED:
        return ActionExecutionStatus.REASSERTED
    return ActionExecutionStatus.APPLIED


class RuntimeVerification(BaseModel):
    expectation_id: str
    status: ActionExecutionStatus
    evidence_method: str = ""
    fresh_evidence: bool = False
    fields: dict[str, FieldVerificationStatus] = Field(default_factory=dict)
    message: str = ""
    convergence: ConvergenceReport | None = None


class ActionApplicationResult(BaseModel):
    action_id: str
    status: ActionExecutionStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    message: str = ""
    batch_id: str = ""
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    disposition: MutationDisposition = MutationDisposition.UNKNOWN


class VerificationResult(BaseModel):
    expectation_id: str
    action_id: str
    status: ActionExecutionStatus
    evidence_method: str = ""
    fresh_evidence: bool = False
    fields: dict[str, FieldVerificationStatus] = Field(default_factory=dict)
    message: str = ""
    convergence: ConvergenceReport | None = None


class VoiceSignalBarrierResult(BaseModel):
    """Typed evidence for data-only preparation and late Voice signalling."""

    required: bool = False
    deferred_action_ids: list[str] = Field(default_factory=list)
    foundation_expectation_ids: list[str] = Field(default_factory=list)
    preparation_results: list[ActionApplicationResult] = Field(
        default_factory=list,
    )
    foundation_verification_results: list[VerificationResult] = Field(
        default_factory=list,
    )
    signal_results: list[ActionApplicationResult] = Field(
        default_factory=list,
    )
    post_signal_convergence_results: list[VerificationResult] = Field(
        default_factory=list,
    )
    foundation_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    signal_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    message: str = ""

    def compact_summary(self) -> dict[str, object]:
        return {
            "required": self.required,
            "deferred_action_ids": self.deferred_action_ids,
            "foundation_expectation_ids": self.foundation_expectation_ids,
            "preparation_statuses": {
                item.action_id: item.status.value
                for item in self.preparation_results
            },
            "foundation_status": self.foundation_status.value,
            "signal_status": self.signal_status.value,
            "message": self.message,
        }


class ConfigurationApplicationResult(BaseModel):
    config_plan_id: str
    config_semantic_hash: str
    source_topology_hash: str
    runtime_context: ConfigurationRuntimeContext = Field(
        default_factory=ConfigurationRuntimeContext,
    )
    status: ConfigurationApplicationStatus
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    action_results: list[ActionApplicationResult] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    preflight_errors: list[str] = Field(default_factory=list)
    deployment_id: str = ""
    execution_journal: ApplicationExecutionJournal | None = None
    dirty_state: DirtyState = DirtyState.CLEAN
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    voice_signal_barrier: VoiceSignalBarrierResult | None = None
    duration_ms: int = 0

    def compact_summary(self) -> dict[str, object]:
        action_counts: dict[str, int] = {}
        for item in self.action_results:
            action_counts[item.status.value] = action_counts.get(item.status.value, 0) + 1
        verification_counts: dict[str, int] = {}
        for item in self.verification_results:
            verification_counts[item.status.value] = verification_counts.get(item.status.value, 0) + 1
        return {
            "config_plan_id": self.config_plan_id,
            "config_semantic_hash": self.config_semantic_hash,
            "source_topology_hash": self.source_topology_hash,
            "runtime_context": self.runtime_context.model_dump(mode="json"),
            "status": self.status.value,
            "failure_code": self.failure_code.value,
            "actions": dict(sorted(action_counts.items())),
            "verification": dict(sorted(verification_counts.items())),
            "preflight_errors": self.preflight_errors,
            "deployment_id": self.deployment_id,
            "dirty_state": self.dirty_state.value,
            "execution_journal": (
                self.execution_journal.compact_summary()
                if self.execution_journal else None
            ),
            "evidence_records": [item.compact_summary() for item in self.evidence_records],
            "voice_signal_barrier": (
                self.voice_signal_barrier.compact_summary()
                if self.voice_signal_barrier is not None else None
            ),
            "duration_ms": self.duration_ms,
        }
