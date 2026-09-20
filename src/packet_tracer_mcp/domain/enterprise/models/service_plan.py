"""Contratos backend-neutral de E6 para servicios empresariales."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from enum import Enum, IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .capabilities import CapabilityStatus
from .configuration import AddressRange, ConfigurationIssue
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
    SMTP = "smtp"
    POP3 = "pop3"
    DHCP = "dhcp"


class ServicePhase(IntEnum):
    """Order in which compiled E6 actions reach their host."""

    ENABLE = 20
    CONTENT = 30
    #: Configuration applied on a selected client, after its server content.
    CLIENT = 40
    #: Execute-once user-state effects, after every client is configured.
    MESSAGE = 50
    #: Explicit client acquisition after server configuration, before client effects.
    ACQUISITION = 35


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
    ENABLE_SMTP = "enable_smtp_service"
    ENABLE_POP3 = "enable_pop3_service"
    ENSURE_EMAIL_ACCOUNT = "ensure_email_account"
    CONFIGURE_EMAIL_CLIENT = "configure_email_client"
    SEND_MAIL_MESSAGE = "send_mail_message"
    ENABLE_SERVER_DHCP = "enable_server_dhcp"
    CONFIGURE_SERVER_DHCP_POOL = "configure_server_dhcp_pool"
    ACQUIRE_DHCP_LEASE = "acquire_dhcp_lease"


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
    #: A client's own mail configuration, read back field by field.
    EMAIL_CLIENT_STATE = "email_client_state"
    #: The sender's `mailSent` event. Gated: no observer is admitted.
    SMTP_SEND = "smtp_send"
    #: Presence of the pair's message in the recipient's server mailbox.
    SMTP_DELIVERED = "smtp_delivered"
    #: The recipient's `mailReceived` event. Gated: no retrieval is admitted.
    POP3_RETRIEVE = "pop3_retrieve"
    #: Send and retrieval of one message, composed. Gated with its parts.
    EMAIL_END_TO_END = "email_end_to_end"
    #: E5 mode-only evidence; catalogued here for one capability vocabulary.
    ENDPOINT_DHCP_MODE = "endpoint_dhcp_mode"
    DHCP_SERVER_STATE = "dhcp_server_state"
    DHCP_LEASE = "dhcp_lease"
    DHCP_LEASE_ATTRIBUTED = "dhcp_lease_attributed"


#: Kinds that run on the service host even when they are reported on a client:
#: mailbox presence is read from the server's own account table.
HOST_PERFORMED_KINDS = frozenset(
    {
        ServiceVerificationKind.SMTP_DELIVERED,
        ServiceVerificationKind.DHCP_SERVER_STATE,
        ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED,
    }
)


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


class ServerDhcpPoolRequirement(BaseModel):
    """Operator choices for one Server-PT pool; zero/empty values derive later."""

    interface: str = ""
    pool_name: str = ""
    start_offset: int = 0
    max_users: int = 0


class EmailAccountRequirement(BaseModel):
    """One server mail account; its credential is an opaque reference."""

    username: str
    secret_ref: str
    display_name: str = ""


class EmailClientRequirement(BaseModel):
    """Which account one selected client uses."""

    client_device_id: str
    username: str


class EmailPairRequirement(BaseModel):
    """One explicit message: a sender client and a recipient client."""

    sender_device_id: str
    recipient_device_id: str


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
    #: Verification rows that must be VERIFIED before this effect is eligible.
    verification_dependencies: list[str] = Field(default_factory=list)
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
    """Set the served index page and record its digest.

    One page store, one action. The Q1 ordinal-1 record measured distinct
    `HttpServer` and `HttpsServer` process objects over a single page table on
    Server-PT: a write through either protocol is visible through both. So
    when one host serves both protocols, one action carries the payload,
    `service_type` names the process it is written through, and
    `shared_service_ids` names every service the page belongs to. The payload
    is never duplicated into a second action to represent the second protocol.

    `content_source_record` names the qualification record that measured the
    shared store. It is provenance, not permission: it promotes no capability
    and sets no readiness.
    """

    action_type: Literal[ServiceActionType.SET_HTTP_CONTENT] = (
        ServiceActionType.SET_HTTP_CONTENT
    )
    path: Literal["index.html"] = "index.html"
    content: str
    content_sha256: str
    #: Every service id this one page satisfies, sorted. A single-service
    #: action carries its own id, so the field is never empty and a reader
    #: never has to guess whether an empty list means "none" or "unknown".
    shared_service_ids: list[str] = Field(default_factory=list)
    content_source_record: str = ""


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


class EnableSmtpService(BaseServiceAction):
    """Set the SMTP domain and turn the SMTP process on for its host."""

    action_type: Literal[ServiceActionType.ENABLE_SMTP] = ServiceActionType.ENABLE_SMTP
    domain_name: str


class EnablePop3Service(BaseServiceAction):
    """Turn the POP3 process on for its host."""

    action_type: Literal[ServiceActionType.ENABLE_POP3] = ServiceActionType.ENABLE_POP3


class EnsureEmailAccount(BaseServiceAction):
    """Ensure one server mail account exists; never change an existing one.

    `secret_ref` names the credential. The value is resolved by the runtime
    for the one script that adds a missing account and is never stored here.
    """

    action_type: Literal[ServiceActionType.ENSURE_EMAIL_ACCOUNT] = (
        ServiceActionType.ENSURE_EMAIL_ACCOUNT
    )
    operation: Literal[OperationSemantics.ENSURE_PRESENT] = (
        OperationSemantics.ENSURE_PRESENT
    )
    username: str
    secret_ref: str


class ConfigureEmailClient(BaseServiceAction):
    """Configure one selected client's mail user; its host is the client."""

    action_type: Literal[ServiceActionType.CONFIGURE_EMAIL_CLIENT] = (
        ServiceActionType.CONFIGURE_EMAIL_CLIENT
    )
    username: str
    mail_id: str
    display_name: str
    smtp_server: str
    pop3_server: str
    secret_ref: str


class SendMailMessage(BaseServiceAction):
    """Send one pair's message once, from the sender client.

    `message_ref` is the compiled identity of the pair's message. `nonce` is
    empty in a compiled plan and bound per run, so the plan's hash never
    depends on it and an earlier run's message can never satisfy a later one.
    """

    action_type: Literal[ServiceActionType.SEND_MAIL_MESSAGE] = (
        ServiceActionType.SEND_MAIL_MESSAGE
    )
    operation: Literal[OperationSemantics.EXECUTE_ONCE] = (
        OperationSemantics.EXECUTE_ONCE
    )
    message_ref: str
    sender_mail_id: str
    recipient_mail_id: str
    recipient_username: str
    smtp_server: str
    secret_ref: str
    nonce: str = ""


class EnableServerDhcp(BaseServiceAction):
    """Enable DHCP on the exact addressed Server-PT interface."""

    action_type: Literal[ServiceActionType.ENABLE_SERVER_DHCP] = (
        ServiceActionType.ENABLE_SERVER_DHCP
    )
    interface: str


class ConfigureServerDhcpPool(BaseServiceAction):
    """Ensure one non-destructive Server-PT DHCP pool is configured."""

    action_type: Literal[ServiceActionType.CONFIGURE_SERVER_DHCP_POOL] = (
        ServiceActionType.CONFIGURE_SERVER_DHCP_POOL
    )
    operation: Literal[OperationSemantics.ENSURE_PRESENT] = (
        OperationSemantics.ENSURE_PRESENT
    )
    interface: str
    pool_name: str
    segment_id: str
    network: str
    prefix: int
    netmask: str
    gateway: str
    dns_server: str = ""
    lease_start: str
    lease_end: str
    max_users: int
    excluded_ranges: list[AddressRange] = Field(default_factory=list)


class AcquireDhcpLease(BaseServiceAction):
    """Start DHCP once on one exact client/interface under a durable claim."""

    action_type: Literal[ServiceActionType.ACQUIRE_DHCP_LEASE] = (
        ServiceActionType.ACQUIRE_DHCP_LEASE
    )
    operation: Literal[OperationSemantics.EXECUTE_ONCE] = (
        OperationSemantics.EXECUTE_ONCE
    )
    interface: str
    segment_id: str
    server_device_id: str
    server_device_name: str
    pool_name: str
    network: str
    prefix: int
    netmask: str
    claim_ref: str
    nonce: str = ""


ServiceAction = Annotated[
    EnableDnsService
    | AddDnsRecord
    | EnableHttpService
    | SetHttpContent
    | EnableHttpsService
    | ConfigureNtpService
    | EnableTftpService
    | PublishTftpFile
    | EnableSmtpService
    | EnablePop3Service
    | EnsureEmailAccount
    | ConfigureEmailClient
    | SendMailMessage
    | EnableServerDhcp
    | ConfigureServerDhcpPool
    | AcquireDhcpLease,
    Field(discriminator="action_type"),
]

#: The families whose script carries a credential. A plan containing any of
#: them is admitted only on the authenticated HTTP channel (R-SEC-01).
SECRET_BEARING_ACTIONS = (EnsureEmailAccount, ConfigureEmailClient, SendMailMessage)


def secret_refs(actions: Sequence[object]) -> list[str]:
    """Return the sorted distinct credential references some actions need."""
    return sorted(
        {
            item.secret_ref
            for item in actions
            if isinstance(item, SECRET_BEARING_ACTIONS) and item.secret_ref
        }
    )


def mail_message_text(nonce: str) -> str:
    """Return the one subject and body a pair's message carries."""
    return f"MCP-E6-MAIL-{nonce}"


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
    kind: Literal["endpoint_address", "endpoint_dhcp_mode", "l3_interface"] = (
        "endpoint_address"
    )


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
        if self.kind in HOST_PERFORMED_KINDS:
            return self.host_model
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

    def message_refs(self) -> list[str]:
        """Return the message identities this plan would send, in plan order."""
        return [
            item.message_ref
            for item in self.actions
            if isinstance(item, SendMailMessage)
        ]

    def operation_nonce_refs(self) -> list[str]:
        """Return every execute-once reference that needs a per-run nonce."""
        return sorted(
            {
                *self.message_refs(),
                *(
                    item.claim_ref
                    for item in self.actions
                    if isinstance(item, AcquireDhcpLease)
                ),
            }
        )

    def with_message_nonces(self, nonces: Mapping[str, str]) -> ServicePlan:
        """Return a copy whose messages and message rows carry this run's nonces.

        The compiled plan, its identity and its semantic hash are unchanged:
        a nonce belongs to one run, and the hash describes the plan.
        """
        bound = self.model_copy(deep=True)
        for action in bound.actions:
            if isinstance(action, SendMailMessage):
                action.nonce = nonces.get(action.message_ref, "")
        for expectation in bound.verification_expectations:
            reference = expectation.expected.get("message_ref")
            if isinstance(reference, str) and reference in nonces:
                expectation.expected["nonce"] = nonces[reference]
        return bound

    def with_operation_nonces(self, nonces: Mapping[str, str]) -> ServicePlan:
        """Bind mail and DHCP claim nonces without changing plan identity."""
        bound = self.with_message_nonces(nonces)
        for action in bound.actions:
            if isinstance(action, AcquireDhcpLease):
                action.nonce = nonces.get(action.claim_ref, "")
        return bound


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
