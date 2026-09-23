"""The typed vocabulary of one enterprise-services product invocation.

This is what the product entry point returns and what its record persists. It
is deliberately separate from the E5 and E6 execution vocabularies, which keep
travelling untouched inside `configuration_result` and `service_result`: an
admission refusal and an action failure are different kinds of fact, and
collapsing them into one enum is how "the run was never authorized" and "the
mutation failed" would become indistinguishable.

Three things the response keeps apart, because this project has confused them
before:

- the behavioural claim: did the service work for this client (`status`,
  `claim_level`);
- effect uncertainty: is it known whether a mutation this run dispatched
  actually happened (`e5_effect_uncertain`, run-level UNKNOWN);
- residue uncertainty: is it known what else changed (`dirty_state`, the
  `residue_unknown:` limitations).

A run can be VERIFIED and still leave `dirty_state` UNKNOWN, because an
attempted partial-footprint DNS add is observed only within the record it
wanted. Saying so is the requirement, not an omission to tidy up.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationFailureCode,
)
from .execution import DirtyState
from .service_plan import ServiceType, ServiceVerificationKind
from .service_runtime import ObservationFact, ServiceApplicationResult


class ServiceStage(StrEnum):
    """How far one invocation got before it stopped."""

    __str__ = Enum.__str__

    ADMISSION = "admission"
    CONFIGURATION_APPLY = "configuration_apply"
    FOUNDATIONAL_EVIDENCE = "foundational_evidence"
    SERVICE_APPLY = "service_apply"
    RELEASE = "release"
    PERSIST = "persist"
    COMPLETED = "completed"


class ServiceRunStatus(StrEnum):
    """The one-word answer, never stronger than the weakest fact supports."""

    __str__ = Enum.__str__

    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    UNKNOWN = "unknown"
    REFUSED = "refused"


class ServiceEntryRefusal(StrEnum):
    """Why admission or a governed continuation gate stopped the run.

    Most values are pre-effect admission refusals. E5 effect uncertainty and
    contradiction are post-E5 continuation refusals: they preserve the typed
    E5 result and prevent any E6 effect. `NONE` is the absence of either kind,
    not a silent pass; the E5 and E6 results still decide the run outcome.
    """

    __str__ = Enum.__str__

    NONE = "none"
    INTENT_INVALID = "intent_invalid"
    DEPLOYMENT_MANIFEST_MISSING = "deployment_manifest_missing"
    DEPLOYMENT_MANIFEST_UNREADABLE = "deployment_manifest_unreadable"
    VERSION_MISMATCH = "version_mismatch"
    IMPORT_ISOLATION_REFUSED = "import_isolation_refused"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    SOURCE_TREE_UNAVAILABLE = "source_tree_unavailable"
    RUNTIME_PROVENANCE_UNAVAILABLE = "runtime_provenance_unavailable"
    RECORD_STORE_UNWRITABLE = "record_store_unwritable"
    COMPOSITION_FAILED = "composition_failed"
    DNS_SERVER_ADDRESS_REQUIRED = "dns_server_address_required"
    DNS_AUTHORITY_CONFLICT = "dns_authority_conflict"
    DHCP_AUTHORITY_CONFLICT = "dhcp_authority_conflict"
    DHCP_RELAY_REQUIRED = "dhcp_relay_required"
    TARGET_IDENTITY_MISMATCH = "target_identity_mismatch"
    ENVIRONMENT_FINGERPRINT_MISMATCH = "environment_fingerprint_mismatch"
    SERVICE_PATH_UNSUPPORTED = "service_path_unsupported"
    SERVICE_INELIGIBLE = "service_ineligible"
    CAPABILITY_UNKNOWN = "capability_unknown"
    EXISTING_CONFIGURATION_CONFLICT = "existing_configuration_conflict"
    DRIFT_UNREADABLE = "drift_unreadable"
    RETAINED_RESULT_INVALID = "retained_result_invalid"
    E5_EFFECT_UNCERTAIN = "e5_effect_uncertain"
    E5_CONTRADICTION = "e5_contradiction"
    FOUNDATIONAL_CONFIGURATION_MISSING = "foundational_configuration_missing"
    EFFECT_HALTED = "effect_halted"
    SECRET_TRANSPORT_UNAVAILABLE = "secret_transport_unavailable"
    SECRET_UNRESOLVED = "secret_unresolved"
    #: Only a governing caller that binds an effect admission can produce this:
    #: the compiled closure was not the one it authorized, so no effect ran.
    EFFECT_SCOPE_NOT_ADMITTED = "effect_scope_not_admitted"


class AdmissionRead(BaseModel):
    """One directed read admission performed, named so the order is auditable."""

    step: str
    subject: str
    outcome: str = ""


class AdmissionRefusal(BaseModel):
    """One typed reason admission stopped."""

    step: str
    code: ServiceEntryRefusal
    detail: str = ""


class AdmissionTrace(BaseModel):
    """What admission read and what it refused, in the order it happened."""

    reads: list[AdmissionRead] = Field(default_factory=list)
    refusals: list[AdmissionRefusal] = Field(default_factory=list)


class E5EffectScope(BaseModel):
    """The disclosed partition of the E5 plan for this invocation."""

    mutated: list[str] = Field(default_factory=list)
    retained: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    #: Kinds applied as registered declarative setters, with no typed pre-read
    #: of their own. Disclosed rather than presented as equivalent to the
    #: endpoint drift observation.
    declarative_only: list[str] = Field(default_factory=list)


class EffectClosureAction(BaseModel):
    """One compiled action an admitted run is about to dispatch, on its target.

    `device_name` is the deployed runtime name the manifest resolved, never a
    plan display label. Typed E5 fields are named; a service action keeps its
    primitive parameters as compiled.
    """

    action_id: str
    action_type: str
    device_name: str
    model: str = ""
    interface: str = ""
    vlan_id: int | None = None
    ipv4: str = ""
    netmask: str = ""
    gateway: str = ""
    parameters: dict[str, str | int | bool] = Field(default_factory=dict)


class EffectClosureCheck(BaseModel):
    """One verification an admitted run will perform, on deployed names."""

    expectation_id: str
    kind: str
    evidence_kind: str
    host_device_name: str
    client_device_name: str = ""
    expected: dict[str, str | int | bool] = Field(default_factory=dict)


class EffectClosureReadinessGroup(BaseModel):
    """One readiness group the invocation may observe, on deployed names.

    `key` is the group's complete identity as text. An access group names its
    switch, VLAN and access interfaces; a continuity group names its VLAN,
    every switch of the compiled component and every trunk end, each as
    `switch:interface`.
    """

    key: str
    kind: str
    vlan_id: int
    switches: list[str] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)


class EffectClosurePath(BaseModel):
    """One selected client-to-server request and every group it waits on."""

    expectation_id: str
    client_device_name: str
    host_device_name: str
    kind: str
    vlan_id: int | None = None
    client_switch: str = ""
    client_port: str = ""
    host_switch: str = ""
    host_port: str = ""
    groups: list[str] = Field(default_factory=list)


class ServiceEffectClosure(BaseModel):
    """Everything one invocation will do, fixed after A10 and before E1.

    The product derives it from its own compiled plans and the manifest it
    admitted; a governing caller may compare it with what it authorized. It is
    a description of what is about to happen and grants nothing by itself.
    """

    deployment_id: str
    manifest_hash: str
    physical_topology_hash: str
    configuration_semantic_hash: str
    service_semantic_hash: str
    environment_fingerprint_hash: str
    observed_build: str
    transport: str
    source_sha: str
    source_tree: str
    source_dirty: bool
    mutated: list[str] = Field(default_factory=list)
    retained: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    e5_actions: list[EffectClosureAction] = Field(default_factory=list)
    excluded_actions: list[EffectClosureAction] = Field(default_factory=list)
    service_actions: list[EffectClosureAction] = Field(default_factory=list)
    checks: list[EffectClosureCheck] = Field(default_factory=list)
    selected_service_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    #: The per-request dependency closure and the readiness groups it names,
    #: derived from the same compiled plans the run will execute.
    paths: list[EffectClosurePath] = Field(default_factory=list)
    readiness_groups: list[EffectClosureReadinessGroup] = Field(default_factory=list)


class OwnedResourceRelease(BaseModel):
    """One resource this run created and what happened when it let it go."""

    resource: str
    outcome: str
    detail: str = ""

    @property
    def resolved(self) -> bool:
        """Whether the release is known to have completed."""
        return self.outcome == "released"


class StageTransition(BaseModel):
    """One durable stage boundary, written before the next effect begins."""

    stage: ServiceStage
    started_at: datetime
    ended_at: datetime | None = None
    outcome: str = ""
    blocked_reason: str = ""


class ClientCheckRow(BaseModel):
    """One expectation observed for one client, with what the read established."""

    expectation_id: str
    kind: ServiceVerificationKind
    required: bool = True
    status: ActionExecutionStatus
    observation: ObservationFact = ObservationFact.UNSPECIFIED
    cause: str = ""
    claim_level: str = ""
    fresh_evidence: bool = False
    failure_code: ConfigurationFailureCode = ConfigurationFailureCode.NONE
    limitations: list[str] = Field(default_factory=list)


class ClientCheckOutcome(BaseModel):
    """Everything one client's rows say about one service."""

    service_id: str
    service_type: ServiceType
    status: ActionExecutionStatus
    required: bool = True
    checks: list[ClientCheckRow] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ClientServiceOutcome(BaseModel):
    """One selected client, and every service it was selected for."""

    client_device_id: str
    deployed_name: str = ""
    model: str = ""
    results: dict[str, ClientCheckOutcome] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class ServiceEntryOutcome(BaseModel):
    """One service as the product reports it, with the clients it selected."""

    service_id: str
    service_type: ServiceType
    usability_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    application_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    direct_readback_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    behavioral_status: ActionExecutionStatus = ActionExecutionStatus.UNKNOWN
    required: bool = True
    selected_clients: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CapabilitySnapshotSummary(BaseModel):
    """Exactly which capability records this invocation resolved."""

    packet_tracer_version: str = ""
    catalog_hash: str = ""
    provenance_by_key: dict[str, str] = Field(default_factory=dict)


class ServiceStageResult(BaseModel):
    """The full typed outcome of one `pt_apply_enterprise_services` call."""

    run_id: str
    run_label: str = ""
    deployment_id: str = ""
    stage: ServiceStage = ServiceStage.ADMISSION
    status: ServiceRunStatus = ServiceRunStatus.REFUSED
    refusal_code: ServiceEntryRefusal = ServiceEntryRefusal.NONE
    blocked_reason: str = ""
    transport: str = ""
    packet_tracer_version: str = ""
    admission: AdmissionTrace = Field(default_factory=AdmissionTrace)
    e5_effect_scope: E5EffectScope = Field(default_factory=E5EffectScope)
    e5_effect_uncertain: bool = False
    configuration_result: ConfigurationApplicationResult | None = None
    foundational_statuses: dict[str, ActionExecutionStatus] = Field(
        default_factory=dict
    )
    service_result: ServiceApplicationResult | None = None
    services: list[ServiceEntryOutcome] = Field(default_factory=list)
    clients: list[ClientServiceOutcome] = Field(default_factory=list)
    releases: list[OwnedResourceRelease] = Field(default_factory=list)
    #: One row per switch/VLAN group whose access ports a client request
    #: depended on, carrying the rendered forwarding sample, the verdict and
    #: the per-client coverage. Operational readiness is reported separately
    #: from configuration application, eligibility and behavioural
    #: verification, because it answers a different question from all three.
    operational_readiness: list[dict[str, Any]] = Field(default_factory=list)
    capability_snapshot: CapabilitySnapshotSummary = Field(
        default_factory=CapabilitySnapshotSummary
    )
    dirty_state: DirtyState = DirtyState.CLEAN
    persisted_stage: ServiceStage | None = None
    record_path: str = ""
    persist_error: str = ""
    limitations: list[str] = Field(default_factory=list)
    duration_ms: int = 0

    @property
    def refused(self) -> bool:
        """Whether admission stopped the run before any effect."""
        return self.refusal_code is not ServiceEntryRefusal.NONE

    def compact_summary(self) -> dict[str, object]:
        """Return the stable report shape; consumers depend on these keys."""
        return {
            "run_id": self.run_id,
            "run_label": self.run_label,
            "deployment_id": self.deployment_id,
            "stage": self.stage.value,
            "status": self.status.value,
            "refusal_code": self.refusal_code.value,
            "blocked_reason": self.blocked_reason,
            "transport": self.transport,
            "packet_tracer_version": self.packet_tracer_version,
            "provenance": dict(self.capability_snapshot.provenance_by_key),
            "e5_effect_scope": self.e5_effect_scope.model_dump(mode="json"),
            "e5_effect_uncertain": self.e5_effect_uncertain,
            "services": [item.model_dump(mode="json") for item in self.services],
            "clients": [item.model_dump(mode="json") for item in self.clients],
            "operational_readiness": [
                dict(item) for item in self.operational_readiness
            ],
            "releases": [item.model_dump(mode="json") for item in self.releases],
            "dirty_state": self.dirty_state.value,
            "persisted_stage": (
                self.persisted_stage.value if self.persisted_stage else None
            ),
            "record_path": self.record_path,
            "persist_error": self.persist_error,
            "limitations": list(self.limitations),
            "duration_ms": self.duration_ms,
        }
