"""Contratos backend-neutral de E6 para servicios empresariales."""

from __future__ import annotations

from collections import Counter
from enum import Enum, IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .capabilities import CapabilityStatus
from .configuration import ConfigurationIssue
from .evidence import CapabilityReadiness
from .execution import OperationSemantics
from .verification import VerificationPrerequisite


class ServiceType(StrEnum):
    """Service family one Server-PT process can host."""

    __str__ = Enum.__str__

    DNS = "dns"
    HTTP = "http"
    HTTPS = "https"
    NTP = "ntp"
    TFTP = "tftp"


class ServicePhase(IntEnum):
    """Order in which compiled E6 actions reach their host."""

    ENABLE = 20
    CONTENT = 30


class ServiceActionType(StrEnum):
    """Typed E6 action applied to a service host."""

    __str__ = Enum.__str__

    ENABLE_DNS = "enable_dns_service"
    ADD_DNS_RECORD = "add_dns_record"
    ENABLE_HTTP = "enable_http_service"
    SET_HTTP_CONTENT = "set_http_content"
    ENABLE_HTTPS = "enable_https_service"
    CONFIGURE_NTP = "configure_ntp_service"
    ENABLE_TFTP = "enable_tftp_service"
    PUBLISH_TFTP_FILE = "publish_tftp_file"


class ServiceEvidenceKind(StrEnum):
    """How one verification row obtained what it claims."""

    __str__ = Enum.__str__

    DIRECT_STATE = "direct_state"
    BEHAVIORAL = "behavioral"
    COMPOSED_BEHAVIORAL = "composed_behavioral"


class ServiceVerificationKind(StrEnum):
    """What a single verification expectation observes."""

    __str__ = Enum.__str__

    DIRECT_SERVICE_STATE = "direct_service_state"
    DNS_RESOLUTION = "dns_resolution"
    DNS_NEGATIVE_CONTROL = "dns_negative_control"
    HTTP_FETCH = "http_fetch"
    HTTPS_FETCH = "https_fetch"
    HTTP_BY_HOSTNAME = "http_by_hostname"
    CLIENT_DNS_SERVER = "client_dns_server"
    NTP_SYNC = "ntp_sync"
    TFTP_RETRIEVE = "tftp_retrieve"


class DnsRecordRequirement(BaseModel):
    """One requested A record, stated before a host is chosen."""

    hostname: str
    address: str
    record_type: Literal["A"] = "A"
    target_device_id: str = ""


class TftpFileRequirement(BaseModel):
    """One file a TFTP service is required to publish."""

    filename: str
    content: str


class CapabilityProvenance(StrEnum):
    """Where a capability record's authority comes from.

    `documentary_baseline` is a claim read from Cisco's reference and from the
    controlled process probes that preceded this project's evidence rules. It
    is usable, and it is never upgraded by later refactoring: a golden-script
    identity test proves a reader's call surface did not change, which is a
    different statement from having observed the capability.

    `recorded_run` is the only level that may be produced by a measurement, and
    it requires the build, the executed tree SHA, the transport, the target
    model and the run identity to be carried with it.
    """

    __str__ = Enum.__str__

    DOCUMENTARY_BASELINE = "documentary_baseline"
    RECORDED_RUN = "recorded_run"


class ServiceCapabilityProfile(BaseModel):
    """Matriz por servicio; no colapsa aplicación y observabilidad."""

    service_type: ServiceType
    compile_support: CapabilityStatus = CapabilityStatus.SUPPORTED
    application_support: CapabilityStatus = CapabilityStatus.UNKNOWN
    action_application_support: dict[str, CapabilityStatus] = Field(
        default_factory=dict
    )
    direct_readback_support: CapabilityStatus = CapabilityStatus.UNKNOWN
    behavioral_verification_support: CapabilityStatus = CapabilityStatus.UNKNOWN
    source: str = ""
    packet_tracer_version: str | None = None
    capability_readiness: dict[str, CapabilityReadiness] = Field(default_factory=dict)
    provenance: CapabilityProvenance = CapabilityProvenance.DOCUMENTARY_BASELINE


class ClientOperationCapability(BaseModel):
    """One operation authorized on one target model, with its provenance.

    The profile above answers "what can this service family do on its server".
    This answers the question the profile cannot: whether a given operation is
    authorized on the model that actually performs it. A server whose DNS
    service is behaviourally supported says nothing about whether a PC-PT can
    be driven to resolve a name, and reading the server's profile for a client
    expectation is exactly how a client got credit for the server's evidence.

    `build`, `executed_sha`, `transport` and `run_id` stay empty for a
    documentary record and are required for a recorded one.
    """

    key: str
    model: str
    operation: str
    support: CapabilityStatus = CapabilityStatus.UNKNOWN
    provenance: CapabilityProvenance = CapabilityProvenance.DOCUMENTARY_BASELINE
    source: str = ""
    packet_tracer_version: str = ""
    build: str = ""
    executed_sha: str = ""
    transport: str = ""
    run_id: str = ""


#: One resolution for compilation, admission and execution. Profiles are keyed
#: `"<model>:<service_type>"` and operations `"<model>:<action_type|kind>"`.
ServiceCapabilityRecord = ServiceCapabilityProfile | ClientOperationCapability
ServiceCapabilityRecords = dict[str, ServiceCapabilityRecord]


class BaseServiceAction(BaseModel):
    """Fields every typed E6 action carries, whatever its family."""

    id: str
    action_type: ServiceActionType
    phase: ServicePhase
    service_id: str
    service_type: ServiceType
    host_device_id: str
    host_device_name: str
    host_model: str
    site_id: str
    depends_on: list[str] = Field(default_factory=list)
    apply_dependencies: list[str] = Field(default_factory=list)
    required_capability: str
    critical: bool = True
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    compensation_available: bool = False
    inverse_action_id: str = ""


class EnableDnsService(BaseServiceAction):
    """Turn the DNS process on for its host."""

    action_type: Literal[ServiceActionType.ENABLE_DNS] = ServiceActionType.ENABLE_DNS


class AddDnsRecord(BaseServiceAction):
    """Ensure one A record exists on the DNS host."""

    action_type: Literal[ServiceActionType.ADD_DNS_RECORD] = (
        ServiceActionType.ADD_DNS_RECORD
    )
    operation: Literal[OperationSemantics.ENSURE_PRESENT] = (
        OperationSemantics.ENSURE_PRESENT
    )
    hostname: str
    address: str
    record_type: Literal["A"] = "A"


class EnableHttpService(BaseServiceAction):
    """Turn the HTTP process on for its host."""

    action_type: Literal[ServiceActionType.ENABLE_HTTP] = ServiceActionType.ENABLE_HTTP


class SetHttpContent(BaseServiceAction):
    """Set the served index page and record its digest."""

    action_type: Literal[ServiceActionType.SET_HTTP_CONTENT] = (
        ServiceActionType.SET_HTTP_CONTENT
    )
    path: Literal["index.html"] = "index.html"
    content: str
    content_sha256: str


class EnableHttpsService(BaseServiceAction):
    """Turn the HTTPS process on for its host."""

    action_type: Literal[ServiceActionType.ENABLE_HTTPS] = (
        ServiceActionType.ENABLE_HTTPS
    )


class ConfigureNtpService(BaseServiceAction):
    """Configure the NTP service on its host."""

    action_type: Literal[ServiceActionType.CONFIGURE_NTP] = (
        ServiceActionType.CONFIGURE_NTP
    )
    authoritative: bool = True


class EnableTftpService(BaseServiceAction):
    """Turn the TFTP process on for its host."""

    action_type: Literal[ServiceActionType.ENABLE_TFTP] = ServiceActionType.ENABLE_TFTP


class PublishTftpFile(BaseServiceAction):
    """Ensure one file is published by the TFTP host."""

    action_type: Literal[ServiceActionType.PUBLISH_TFTP_FILE] = (
        ServiceActionType.PUBLISH_TFTP_FILE
    )
    operation: Literal[OperationSemantics.ENSURE_PRESENT] = (
        OperationSemantics.ENSURE_PRESENT
    )
    filename: str
    content: str
    content_sha256: str


ServiceAction = Annotated[
    EnableDnsService
    | AddDnsRecord
    | EnableHttpService
    | SetHttpContent
    | EnableHttpsService
    | ConfigureNtpService
    | EnableTftpService
    | PublishTftpFile,
    Field(discriminator="action_type"),
]


class ServiceDefinition(BaseModel):
    """One compiled service with its host and its selected clients."""

    id: str
    name: str
    service_type: ServiceType
    site_id: str
    host_device_id: str
    host_device_name: str
    host_model: str
    address: str
    segment_id: str
    client_device_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    verification_expectation_ids: list[str] = Field(default_factory=list)
    protocol: str
    ports: list[int] = Field(default_factory=list)
    #: Whether an ineligible version of this service refuses the whole run
    #: or is excluded from it. Carried from the requirement so admission
    #: does not have to re-derive which intent line produced the service.
    required: bool = True
    #: Whether this service's expectations gate it.
    verification_required: bool = True


class FoundationalServiceRequirement(BaseModel):
    """The E5 action this service needs verified before it may apply."""

    id: str
    device_id: str
    device_name: str
    model: str
    ipv4: str
    segment_id: str
    configuration_action_id: str
    #: Which E5 family the referenced action belongs to. Only an
    #: `endpoint_address` foundation may be satisfied by the attributable
    #: IPv4/netmask core of a PARTIAL row; every other kind copies its
    #: verification status, because no core predicate exists for it.
    kind: Literal["endpoint_address", "l3_interface"] = "endpoint_address"


class ServiceVerificationExpectation(BaseModel):
    """One observation the plan expects once its action has applied."""

    id: str
    service_id: str
    action_id: str
    kind: ServiceVerificationKind
    evidence_kind: ServiceEvidenceKind
    host_device_id: str
    host_device_name: str
    client_device_id: str = ""
    client_device_name: str = ""
    depends_on: list[str] = Field(default_factory=list)
    verification_prerequisites: list[VerificationPrerequisite] = Field(
        default_factory=list
    )
    expected: dict[str, str | int | bool] = Field(default_factory=dict)
    #: Whether this expectation gates its service. An advisory reader, and any
    #: expectation of a service whose `verification_required` is False, is
    #: compiled optional: it is still observed and still reported, but it can
    #: neither block eligibility nor report VERIFIED for a capability it lacks.
    required: bool = True
    #: The models the expectation is resolved against. Verification capability
    #: is resolved on the model that performs the operation, which for a client
    #: expectation is the client and never the server profile.
    host_model: str = ""
    client_model: str = ""

    @property
    def target_model(self) -> str:
        """The model that performs this observation."""
        return self.client_model if self.client_device_id else self.host_model


class ServicePlan(BaseModel):
    """The compiled E6 plan for one topology and one configuration."""

    id: str
    source_topology_id: str
    source_topology_hash: str
    source_topology_hash_schema: str = "legacy-full-v1"
    source_configuration_id: str
    source_configuration_hash: str
    semantic_hash: str = ""
    services: list[ServiceDefinition] = Field(default_factory=list)
    actions: list[ServiceAction] = Field(default_factory=list)
    foundational_requirements: list[FoundationalServiceRequirement] = Field(
        default_factory=list
    )
    verification_expectations: list[ServiceVerificationExpectation] = Field(
        default_factory=list
    )

    def actions_of_type(self, action_type: ServiceActionType) -> list[ServiceAction]:
        """Return every action of one type, in plan order."""
        return [item for item in self.actions if item.action_type is action_type]

    def services_on_host(self, device_id: str) -> list[ServiceDefinition]:
        """Return every service compiled onto one device."""
        return [item for item in self.services if item.host_device_id == device_id]


class ServiceCompileSummary(BaseModel):
    """Counts of one compilation, for reports that must not hold plans."""

    service_plan_id: str = ""
    semantic_hash: str = ""
    source_topology_hash: str = ""
    source_topology_hash_schema: str = ""
    source_configuration_hash: str = ""
    service_count: int = 0
    action_count: int = 0
    actions_by_type: dict[str, int] = Field(default_factory=dict)
    dependencies: int = 0
    verification_expectations: int = 0
    warnings: int = 0
    errors: int = 0


class ServiceCompileResult(BaseModel):
    """A compiled plan, or the issues that prevented one."""

    plan: ServicePlan | None = None
    semantic_hash: str = ""
    summary: ServiceCompileSummary = Field(default_factory=ServiceCompileSummary)
    issues: list[ConfigurationIssue] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Whether a plan exists and no issue is an error."""
        from .configuration import ConfigurationIssueSeverity

        return self.plan is not None and not any(
            item.severity is ConfigurationIssueSeverity.ERROR for item in self.issues
        )

    def compact_summary(self) -> dict[str, object]:
        """Return the stable report shape; consumers depend on these keys."""
        return {
            **self.summary.model_dump(mode="json"),
            "issues": [item.model_dump(mode="json") for item in self.issues],
        }


def service_action_type_counts(actions: list[ServiceAction]) -> dict[str, int]:
    """Count actions by type, sorted by the type value."""
    counts = Counter(item.action_type.value for item in actions)
    return dict(sorted(counts.items()))
