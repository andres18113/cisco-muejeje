"""Backend-neutral wireless connectivity contracts for IoT endpoints.

The axes here are deliberately orthogonal, in the same spirit as
:mod:`evidence`:

* **Intent** says which endpoints should reach which segment through which
  service set, and which access points are candidates for that. It never names
  a backend and never pins one access point unless the caller asked for it.
* **Association** says whether the radio link between one endpoint and the
  cluster was observed. Configuration that a backend accepted is CONFIGURED,
  never ASSOCIATED: the promotion needs a fresh reading.
* **Network attachment** says whether the endpoint holds an address inside the
  segment it was planned into. An endpoint can be associated without being
  attached, and a reading can be unavailable on either axis independently.
* **IoT function** (smoke, motion, video) is a declaration only. It lives in a
  separate structure precisely so that no association evidence can be read as
  function evidence, or the other way round.

Nothing in this module knows that Packet Tracer exists. The capability
vocabulary is declared here so that any backend can be audited against it; the
concrete audit for a concrete build belongs in infrastructure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from ipaddress import IPv4Address, IPv4Network
from types import MappingProxyType

from .evidence import ObservationStatus, VerificationMethod
from .requirements import AddressingPreference
from .roles import DeviceRole
from .segments import SegmentRole


class WirelessClusterScope(str, Enum):
    """Hierarchy depth one cluster covers.

    A single-zone lab and a multi-site enterprise differ only in which scope the
    caller selects; the cluster contract itself does not change.
    """

    SITE = "site"
    BUILDING = "building"
    FLOOR = "floor"
    ZONE = "zone"


class WirelessSecurityMode(str, Enum):
    UNSPECIFIED = "unspecified"
    OPEN = "open"
    WEP = "wep"
    WPA_PSK = "wpa_psk"
    WPA2_PSK = "wpa2_psk"
    WPA2_ENTERPRISE = "wpa2_enterprise"


class AccessPointOwnership(str, Enum):
    """How one candidate access point relates to the cluster that lists it."""

    CLUSTER_OWNED = "cluster_owned"
    SHARED = "shared"
    EXTERNAL = "external"


class AccessPointSelection(str, Enum):
    """Who decides which access point an endpoint ends up associated with."""

    BACKEND_SELECTED = "backend_selected"
    PINNED = "pinned"


class WirelessAssociationState(str, Enum):
    """Lifecycle of one endpoint association, evidence included.

    ``CONFIGURED`` is not a weaker ``ASSOCIATED``: it says a backend accepted
    configuration and says nothing at all about the radio link.
    """

    PLANNED = "planned"
    CONFIGURED = "configured"
    ASSOCIATED = "associated"
    UNOBSERVABLE = "unobservable"
    FAILED = "failed"
    UNKNOWN = "unknown"


class NetworkAttachmentState(str, Enum):
    """Same lifecycle for the addressing axis; ATTACHED replaces ASSOCIATED."""

    PLANNED = "planned"
    CONFIGURED = "configured"
    ATTACHED = "attached"
    UNOBSERVABLE = "unobservable"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AddressingSource(str, Enum):
    """What an observation actually said about how the address was obtained.

    ``DHCP_CLIENT_DISABLED`` is a fact about one flag, not a static assignment:
    a port can have the client off and hold no address at all. ``STATIC`` is
    reserved for a backend that positively reports a static assignment, and
    nothing derives it from an intent or from the absence of DHCP.
    """

    UNKNOWN = "unknown"
    STATIC = "static"
    DHCP_CLIENT_ENABLED = "dhcp_client_enabled"
    DHCP_CLIENT_DISABLED = "dhcp_client_disabled"


class IoTFunction(str, Enum):
    """What the endpoint is for. Declared, never verified by this phase."""

    NONE = "none"
    VIDEO_CAPTURE = "video_capture"
    SMOKE_DETECTION = "smoke_detection"
    MOTION_DETECTION = "motion_detection"
    ENVIRONMENTAL_SENSING = "environmental_sensing"
    UNCLASSIFIED = "unclassified"


class WirelessCapability(str, Enum):
    """The questions a backend has to answer before any state can be claimed."""

    RADIO_ENABLEMENT = "radio_enablement"
    SERVICE_SET_CONFIGURATION = "service_set_configuration"
    ENDPOINT_SERVICE_SET_SELECTION = "endpoint_service_set_selection"
    ASSOCIATION_STATE_OBSERVATION = "association_state_observation"
    ASSOCIATED_ACCESS_POINT_IDENTIFICATION = "associated_access_point_identification"
    WIRELESS_PORT_CLASSIFICATION = "wireless_port_classification"
    ACCESS_POINT_RADIO_PORT_IDENTITY = "access_point_radio_port_identity"
    ENDPOINT_ADDRESS_OBSERVATION = "endpoint_address_observation"
    DHCP_CLIENT_FLAG_OBSERVATION = "dhcp_client_flag_observation"
    NETWORK_ATTACHMENT_OBSERVATION = "network_attachment_observation"
    IOT_FUNCTION_OBSERVATION = "iot_function_observation"


class WirelessCapabilityStatus(str, Enum):
    """Classification of one capability on one exact backend build.

    ``DOCUMENTED`` is the honest middle: a vendor reference describes the
    surface, and nobody has run it on this build. It licenses writing a probe;
    it licenses no claim about a state, so everything that gates a promotion
    treats it exactly like UNKNOWN. Absence of a record is UNKNOWN, never a no.
    """

    SUPPORTED = "supported"
    DOCUMENTED = "documented"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    UNOBSERVABLE = "unobservable"


#: Statuses that positively establish a capability cannot be observed here.
BLOCKED_CAPABILITY_STATUSES = frozenset({
    WirelessCapabilityStatus.UNSUPPORTED,
    WirelessCapabilityStatus.UNOBSERVABLE,
})

#: Statuses that license driving a surface for evidence. DOCUMENTED is absent
#: on purpose: a reference is not a measurement.
MEASURED_CAPABILITY_STATUSES = frozenset({WirelessCapabilityStatus.SUPPORTED})


class WirelessParticipation(str, Enum):
    """How an endpoint takes part in a wireless cluster.

    Radio capability alone does not make an endpoint a client. A wireless
    bridge, repeater or lightweight access point carries a radio and serves the
    cluster; classifying it by its ``wireless`` flag would quietly turn
    infrastructure into a member.
    """

    CLIENT = "client"
    INFRASTRUCTURE = "infrastructure"
    EXCLUDED = "excluded"


class BackendErrorKind(str, Enum):
    """Why a backend read produced no answer.

    None of these is an absent property, so none of them may become
    UNOBSERVABLE. They say the question could not be asked or the answer could
    not be parsed, which is a probe failure and leaves the state UNKNOWN.
    """

    TRANSPORT_EXCEPTION = "transport_exception"
    TRANSPORT_TIMEOUT = "transport_timeout"
    ENGINE_ERROR = "engine_error"
    PROTOCOL_ERROR = "protocol_error"


class ReadingProvenance(str, Enum):
    """Whether a reading belongs to the subject and build it is used for."""

    MATCHED = "matched"
    FOREIGN_ENDPOINT = "foreign_endpoint"
    FOREIGN_BACKEND = "foreign_backend"
    FOREIGN_BUILD = "foreign_build"


_IOT_FUNCTION_BY_ROLE: Mapping[DeviceRole, IoTFunction] = MappingProxyType({
    DeviceRole.WEBCAM: IoTFunction.VIDEO_CAPTURE,
    DeviceRole.IP_CAMERA: IoTFunction.VIDEO_CAPTURE,
    DeviceRole.SMOKE_DETECTOR: IoTFunction.SMOKE_DETECTION,
    DeviceRole.MOTION_DETECTOR: IoTFunction.MOTION_DETECTION,
    DeviceRole.HUMITURE_MONITOR: IoTFunction.ENVIRONMENTAL_SENSING,
    DeviceRole.TEMPERATURE_MONITOR: IoTFunction.ENVIRONMENTAL_SENSING,
})


def iot_function_for_role(role: DeviceRole) -> IoTFunction:
    """Declared function of a role.

    A wireless endpoint whose role carries no IoT function is not an error: a
    wireless laptop joins the same cluster contract with ``NONE``.
    """
    return _IOT_FUNCTION_BY_ROLE.get(role, IoTFunction.NONE)


#: Roles that serve a cluster rather than join it. Kept deliberately small:
#: the general signal is the ``infrastructure_class`` metadata below, which any
#: new wireless infrastructure model can set without touching this set.
_INFRASTRUCTURE_ROLES = frozenset({DeviceRole.ACCESS_POINT})

#: Metadata keys an endpoint can use to state its own part, in priority order.
PARTICIPATION_METADATA_KEY = "wireless_participation"
INFRASTRUCTURE_METADATA_KEY = "infrastructure_class"


def wireless_participation(
    role: DeviceRole,
    *,
    wireless: bool,
    metadata: Mapping[str, str] | None = None,
) -> WirelessParticipation:
    """Decide how an endpoint takes part, never from the radio flag alone.

    An explicit declaration wins, then an infrastructure class, then the
    infrastructure roles. Only what is left over and carries a radio is a
    client. A wireless bridge or lightweight access point therefore stays
    infrastructure instead of silently joining its own cluster, and a new IoT
    role needs no entry anywhere to be treated as a client.
    """
    declared = dict(metadata or {}).get(PARTICIPATION_METADATA_KEY, "").strip()
    if declared:
        try:
            return WirelessParticipation(declared)
        except ValueError:
            # An unreadable declaration is not an invitation to guess.
            return WirelessParticipation.EXCLUDED
    if dict(metadata or {}).get(INFRASTRUCTURE_METADATA_KEY, "").strip():
        return WirelessParticipation.INFRASTRUCTURE
    if role in _INFRASTRUCTURE_ROLES:
        return WirelessParticipation.INFRASTRUCTURE
    if wireless:
        return WirelessParticipation.CLIENT
    return WirelessParticipation.EXCLUDED


def reading_provenance(
    *,
    endpoint_id: str,
    reading_endpoint_id: str,
    expected: BackendIdentity,
    reading_backend: str,
    reading_backend_version: str,
) -> ReadingProvenance:
    """Whether a reading may be attributed to this endpoint on this build.

    An empty backend on the reading is treated as foreign rather than as a
    match: a reading that cannot say where it came from cannot be credited to
    a build.
    """
    if reading_endpoint_id != endpoint_id:
        return ReadingProvenance.FOREIGN_ENDPOINT
    if reading_backend != expected.backend:
        return ReadingProvenance.FOREIGN_BACKEND
    if reading_backend_version != expected.backend_version:
        return ReadingProvenance.FOREIGN_BUILD
    return ReadingProvenance.MATCHED


def _capability_label(capability: WirelessCapability, subject: str) -> str:
    return capability.value + (f"/{subject}" if subject else "")


def _status_label(status: "WirelessCapabilityStatus | None") -> str:
    return "absent" if status is None else status.value


@dataclass(frozen=True)
class WirelessServiceSetIntent:
    """Requested service set. An empty SSID means the backend default one."""

    ssid: str = ""
    security_mode: WirelessSecurityMode = WirelessSecurityMode.UNSPECIFIED

    @property
    def uses_backend_default(self) -> bool:
        return not self.ssid


@dataclass(frozen=True)
class IntendedNetworkSegment:
    """The segment the cluster members are planned into.

    VLAN id, subnet and gateway stay optional: a plan that has not reached IPAM
    yet is still a complete intent, and no number is assumed here.
    """

    segment_id: str
    role: SegmentRole
    vlan_id: int | None = None
    subnet: str = ""
    gateway: str = ""
    dhcp: bool = False

    def contains(self, ipv4: str) -> bool | None:
        """``None`` when the plan cannot answer, never a silent ``False``."""
        if not self.subnet or not ipv4:
            return None
        try:
            return IPv4Address(ipv4) in IPv4Network(self.subnet, strict=False)
        except ValueError:
            return None


@dataclass(frozen=True)
class AccessPointCandidate:
    """One access point a cluster may associate members through."""

    access_point_id: str
    name: str
    site_id: str
    building_id: str = ""
    floor_id: str = ""
    zone_id: str = ""
    model: str = ""
    uplink_segment_id: str = ""
    ownership: AccessPointOwnership = AccessPointOwnership.CLUSTER_OWNED


@dataclass(frozen=True)
class WirelessEndpointMembership:
    """One endpoint inside one cluster, with its addressing and function."""

    endpoint_id: str
    name: str
    role: DeviceRole
    cluster_id: str
    segment_id: str
    iot_function: IoTFunction = IoTFunction.NONE
    addressing_preference: AddressingPreference = AddressingPreference.UNSPECIFIED
    site_id: str = ""
    building_id: str = ""
    floor_id: str = ""
    zone_id: str = ""
    source_group: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "metadata", MappingProxyType(dict(sorted(self.metadata.items()))),
        )


@dataclass(frozen=True)
class WirelessCluster:
    """A service area: members, candidate access points and one segment."""

    cluster_id: str
    name: str
    scope: WirelessClusterScope
    site_id: str
    segment: IntendedNetworkSegment
    service_set: WirelessServiceSetIntent = WirelessServiceSetIntent()
    building_id: str = ""
    floor_id: str = ""
    zone_id: str = ""
    candidates: tuple[AccessPointCandidate, ...] = ()
    members: tuple[WirelessEndpointMembership, ...] = ()

    @property
    def has_candidate(self) -> bool:
        return bool(self.candidates)

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.access_point_id for item in self.candidates)


@dataclass(frozen=True)
class WirelessAssociationIntent:
    """What the plan asks for, without deciding what the backend will choose.

    ``BACKEND_SELECTED`` keeps every candidate open. A pinned access point is a
    deliberate narrowing and has to name one of the cluster candidates.
    """

    endpoint_id: str
    cluster_id: str
    service_set: WirelessServiceSetIntent = WirelessServiceSetIntent()
    selection: AccessPointSelection = AccessPointSelection.BACKEND_SELECTED
    candidate_access_point_ids: tuple[str, ...] = ()
    pinned_access_point_id: str = ""
    addressing_preference: AddressingPreference = AddressingPreference.UNSPECIFIED


@dataclass(frozen=True)
class IoTFunctionDeclaration:
    """Declared function plus the fact that nothing observed it.

    Kept apart from every association structure on purpose: this phase does not
    attempt smoke, motion or video evidence, and the type makes that visible
    instead of leaving it to a comment.
    """

    endpoint_id: str
    function: IoTFunction
    observation_status: ObservationStatus = ObservationStatus.NOT_ATTEMPTED
    note: str = "Declared role function; no functional observation attempted."


class WirelessConfigurationStatus(str, Enum):
    """What a backend did with one association intent, never what resulted."""

    NOT_ATTEMPTED = "not_attempted"
    APPLIED = "applied"
    REFUSED = "refused"
    FAILED = "failed"


@dataclass(frozen=True)
class WirelessConfigurationOutcome:
    """A backend accepted, refused or failed the configuration. Nothing more.

    ``REFUSED`` is the honest answer when the backend has no surface for the
    request: it is not a failure of the plan and it is not an association.
    """

    endpoint_id: str
    status: WirelessConfigurationStatus = WirelessConfigurationStatus.NOT_ATTEMPTED
    surface: str = ""
    detail: str = ""

    @property
    def applied(self) -> bool:
        return self.status is WirelessConfigurationStatus.APPLIED


@dataclass(frozen=True)
class WirelessAssociationReading:
    """Raw backend answer for one endpoint, before any judgment is applied.

    ``unavailable_reading`` names the exact interface member the read stopped
    at, never a cause: a reading says where it ended, and the classification
    decides what that means.
    """

    endpoint_id: str
    backend: str = ""
    backend_version: str = ""
    attempted: bool = False
    radio_present: bool | None = None
    associated: bool | None = None
    access_point_id: str = ""
    service_set: str = ""
    method: VerificationMethod = VerificationMethod.NONE
    fresh: bool = False
    unavailable_reading: str = ""
    error_kind: BackendErrorKind | None = None
    error_stage: str = ""
    detail: str = ""


@dataclass(frozen=True)
class WirelessAttachmentReading:
    """Raw addressing answer for one endpoint, before any judgment."""

    endpoint_id: str
    backend: str = ""
    backend_version: str = ""
    attempted: bool = False
    interface: str = ""
    ipv4: str = ""
    netmask: str = ""
    dhcp_client_flag: bool | None = None
    method: VerificationMethod = VerificationMethod.NONE
    fresh: bool = False
    unavailable_reading: str = ""
    error_kind: BackendErrorKind | None = None
    error_stage: str = ""
    detail: str = ""


@dataclass(frozen=True)
class WirelessAssociationObservation:
    """Classified association state with the evidence that produced it."""

    endpoint_id: str
    cluster_id: str
    state: WirelessAssociationState
    observed_access_point_id: str = ""
    observed_service_set: str = ""
    method: VerificationMethod = VerificationMethod.NONE
    observation_status: ObservationStatus = ObservationStatus.NOT_ATTEMPTED
    fresh_evidence: bool = False
    backend: str = ""
    backend_version: str = ""
    unavailable_reading: str = ""
    error_kind: BackendErrorKind | None = None
    error_stage: str = ""
    provenance: ReadingProvenance = ReadingProvenance.MATCHED
    detail: str = ""


@dataclass(frozen=True)
class NetworkAttachmentObservation:
    """Classified attachment state with the evidence that produced it."""

    endpoint_id: str
    cluster_id: str
    segment_id: str
    state: NetworkAttachmentState
    interface: str = ""
    ipv4: str = ""
    netmask: str = ""
    addressing_source: AddressingSource = AddressingSource.UNKNOWN
    in_intended_segment: bool | None = None
    method: VerificationMethod = VerificationMethod.NONE
    observation_status: ObservationStatus = ObservationStatus.NOT_ATTEMPTED
    fresh_evidence: bool = False
    backend: str = ""
    backend_version: str = ""
    unavailable_reading: str = ""
    error_kind: BackendErrorKind | None = None
    error_stage: str = ""
    provenance: ReadingProvenance = ReadingProvenance.MATCHED
    detail: str = ""


@dataclass(frozen=True)
class WirelessCapabilityAssessment:
    """One audited backend capability, pinned to an exact backend build."""

    capability: WirelessCapability
    status: WirelessCapabilityStatus
    backend: str
    backend_version: str
    subject: str = ""
    surface: str = ""
    evidence_reference: str = ""
    note: str = ""
    resolved_by: str = ""


@dataclass(frozen=True)
class BackendIdentity:
    """One backend and one exact build. Neither half alone identifies it."""

    backend: str
    backend_version: str

    def __str__(self) -> str:
        return f"{self.backend} {self.backend_version}"


@dataclass(frozen=True)
class WirelessCapabilityAudit:
    """Everything known about one backend build, with UNKNOWN as the default."""

    backend: str
    backend_version: str
    assessments: tuple[WirelessCapabilityAssessment, ...] = ()

    @property
    def identity(self) -> BackendIdentity:
        return BackendIdentity(self.backend, self.backend_version)

    def binding_conflicts(self) -> tuple[str, ...]:
        """Records that do not belong to the build this audit claims to be."""
        return tuple(sorted(
            f"{_capability_label(item.capability, item.subject)} is recorded for "
            f"{item.backend} {item.backend_version}"
            for item in self.assessments
            if item.backend != self.backend
            or item.backend_version != self.backend_version
        ))

    def equivalence_conflicts(
        self, other: "WirelessCapabilityAudit",
    ) -> tuple[str, ...]:
        """Why two audits cannot be treated as the same authority."""
        conflicts: list[str] = []
        if self.identity != other.identity:
            conflicts.append(
                f"backend identity {self.identity} does not equal {other.identity}"
            )
        mine = {
            (item.capability, item.subject): item.status
            for item in self.assessments
        }
        theirs = {
            (item.capability, item.subject): item.status
            for item in other.assessments
        }
        keys = sorted(
            set(mine) | set(theirs), key=lambda item: (item[0].value, item[1]),
        )
        for key in keys:
            if mine.get(key) is not theirs.get(key):
                conflicts.append(
                    f"{_capability_label(key[0], key[1])} is "
                    f"{_status_label(mine.get(key))} here and "
                    f"{_status_label(theirs.get(key))} there"
                )
        return tuple(conflicts)

    def status(
        self, capability: WirelessCapability, subject: str = "",
    ) -> WirelessCapabilityStatus:
        """Most specific record wins; an absent record stays UNKNOWN."""
        exact = next(
            (
                item for item in self.assessments
                if item.capability is capability and item.subject == subject
            ),
            None,
        )
        if exact is not None:
            return exact.status
        if subject:
            generic = next(
                (
                    item for item in self.assessments
                    if item.capability is capability and not item.subject
                ),
                None,
            )
            if generic is not None:
                return generic.status
        return WirelessCapabilityStatus.UNKNOWN

    def assessment(
        self, capability: WirelessCapability, subject: str = "",
    ) -> WirelessCapabilityAssessment | None:
        return next(
            (
                item for item in self.assessments
                if item.capability is capability and item.subject == subject
            ),
            None,
        )


@dataclass(frozen=True)
class WirelessConnectivityPlan:
    """Everything the planner derived, including what it could not place."""

    clusters: tuple[WirelessCluster, ...] = ()
    association_intents: tuple[WirelessAssociationIntent, ...] = ()
    iot_functions: tuple[IoTFunctionDeclaration, ...] = ()
    unclustered_endpoint_ids: tuple[str, ...] = ()
    scope: WirelessClusterScope = WirelessClusterScope.ZONE

    @property
    def member_count(self) -> int:
        return sum(len(cluster.members) for cluster in self.clusters)

    def cluster(self, cluster_id: str) -> WirelessCluster | None:
        return next(
            (item for item in self.clusters if item.cluster_id == cluster_id), None,
        )

    def intent_for(self, endpoint_id: str) -> WirelessAssociationIntent | None:
        return next(
            (
                item for item in self.association_intents
                if item.endpoint_id == endpoint_id
            ),
            None,
        )


@dataclass(frozen=True)
class WirelessEndpointConnectivityResult:
    """One endpoint across all three axes, each keeping its own evidence."""

    endpoint_id: str
    cluster_id: str
    association: WirelessAssociationObservation
    attachment: NetworkAttachmentObservation
    iot_function: IoTFunctionDeclaration

    @property
    def association_state(self) -> WirelessAssociationState:
        return self.association.state

    @property
    def attachment_state(self) -> NetworkAttachmentState:
        return self.attachment.state


def classify_association_state(
    *,
    configured: bool,
    reading: WirelessAssociationReading | None,
    observation_capability: WirelessCapabilityStatus,
    provenance: ReadingProvenance = ReadingProvenance.MATCHED,
) -> WirelessAssociationState:
    """Turn one raw reading into a state without ever inflating it.

    The order matters. A reading belonging to another endpoint or another
    build is a contradiction, and a contradiction is FAILED: reattributing it
    is the one mistake nothing downstream could detect. A transport, engine or
    protocol failure leaves the state UNKNOWN, because the property was never
    asked. Only a named stopping member is UNOBSERVABLE, and configuration
    alone can only reach CONFIGURED.
    """
    if provenance is not ReadingProvenance.MATCHED:
        return WirelessAssociationState.FAILED
    baseline = (
        WirelessAssociationState.CONFIGURED
        if configured else WirelessAssociationState.PLANNED
    )
    if observation_capability in BLOCKED_CAPABILITY_STATUSES:
        return WirelessAssociationState.UNOBSERVABLE
    if reading is None:
        return baseline
    if reading.error_kind is not None:
        # The probe broke, not the property. Claiming UNOBSERVABLE here would
        # hide an exception behind a statement about the backend.
        return WirelessAssociationState.UNKNOWN
    if reading.unavailable_reading:
        # A named stopping member is an answer: the backend was asked and the
        # reading does not exist. That is not the same as never having looked.
        return WirelessAssociationState.UNOBSERVABLE
    if not reading.attempted:
        return baseline
    if reading.method is VerificationMethod.NONE or not reading.fresh:
        return WirelessAssociationState.UNKNOWN
    if reading.associated is True:
        return WirelessAssociationState.ASSOCIATED
    if reading.associated is False:
        return WirelessAssociationState.FAILED
    return WirelessAssociationState.UNKNOWN


def classify_attachment_state(
    *,
    configured: bool,
    reading: WirelessAttachmentReading | None,
    observation_capability: WirelessCapabilityStatus,
    segment: IntendedNetworkSegment,
    provenance: ReadingProvenance = ReadingProvenance.MATCHED,
) -> NetworkAttachmentState:
    """Same rules on the addressing axis.

    An address outside the intended segment is a FAILED attachment, not an
    absent one: the endpoint attached to something the plan did not intend.
    """
    if provenance is not ReadingProvenance.MATCHED:
        return NetworkAttachmentState.FAILED
    baseline = (
        NetworkAttachmentState.CONFIGURED
        if configured else NetworkAttachmentState.PLANNED
    )
    if observation_capability in BLOCKED_CAPABILITY_STATUSES:
        return NetworkAttachmentState.UNOBSERVABLE
    if reading is None:
        return baseline
    if reading.error_kind is not None:
        return NetworkAttachmentState.UNKNOWN
    if reading.unavailable_reading:
        return NetworkAttachmentState.UNOBSERVABLE
    if not reading.attempted:
        return baseline
    if reading.method is VerificationMethod.NONE or not reading.fresh:
        return NetworkAttachmentState.UNKNOWN
    if not reading.ipv4 or reading.ipv4 == "0.0.0.0":
        return NetworkAttachmentState.FAILED
    inside = segment.contains(reading.ipv4)
    if inside is False:
        return NetworkAttachmentState.FAILED
    if inside is None:
        return NetworkAttachmentState.UNKNOWN
    return NetworkAttachmentState.ATTACHED
