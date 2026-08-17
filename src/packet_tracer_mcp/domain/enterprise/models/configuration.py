"""Contratos backend-neutral de E5 para configuración compilada."""

from __future__ import annotations

from collections import Counter
from enum import IntEnum, Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .execution import OperationSemantics
from .segments import SegmentRole
from .verification import VerificationPrerequisite


class ConfigurationPhase(IntEnum):
    L2_DEFINITIONS = 20
    L2_INTERFACES = 30
    L3_INTERFACES = 40
    SERVICES = 50
    ENDPOINT_ADDRESSING = 60
    VERIFICATION = 70


class ConfigurationActionType(str, Enum):
    CREATE_VLAN = "create_vlan"
    CONFIGURE_ACCESS_PORT = "configure_access_port"
    CONFIGURE_TRUNK = "configure_trunk"
    CONFIGURE_ROUTED_INTERFACE = "configure_routed_interface"
    CONFIGURE_SVI = "configure_svi"
    CONFIGURE_SUBINTERFACE = "configure_subinterface"
    CONFIGURE_DHCP_POOL = "configure_dhcp_pool"
    SET_ENDPOINT_STATIC = "set_endpoint_static"
    SET_ENDPOINT_DHCP = "set_endpoint_dhcp"
    CONFIGURE_SERIAL_CLOCK = "configure_serial_clock"
    CONFIGURE_INTERFACE_BANDWIDTH = "configure_interface_bandwidth"
    CONFIGURE_ETHERNET_LINK_MODE = "configure_ethernet_link_mode"


class ConfigurationIssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ConfigurationIssueCode(str, Enum):
    SOURCE_TOPOLOGY_HASH_MISSING = "SOURCE_TOPOLOGY_HASH_MISSING"
    SITE_TOPOLOGY_MISSING = "SITE_TOPOLOGY_MISSING"
    SEGMENT_ALLOCATION_MISSING = "SEGMENT_ALLOCATION_MISSING"
    TRANSIT_ALLOCATION_MISSING = "TRANSIT_ALLOCATION_MISSING"
    SEGMENT_MAPPING_MISSING = "SEGMENT_MAPPING_MISSING"
    VLAN_INVALID_ID = "VLAN_INVALID_ID"
    VLAN_ID_CONFLICT = "VLAN_ID_CONFLICT"
    ACCESS_LINK_INVALID = "ACCESS_LINK_INVALID"
    ACCESS_TRUNK_CONFLICT = "ACCESS_TRUNK_CONFLICT"
    GATEWAY_DEVICE_MISSING = "GATEWAY_DEVICE_MISSING"
    GATEWAY_INVALID = "GATEWAY_INVALID"
    GATEWAY_INTERFACE_MISSING = "GATEWAY_INTERFACE_MISSING"
    DHCP_SERVER_MISSING = "DHCP_SERVER_MISSING"
    ADDRESS_SPACE_EXHAUSTED = "ADDRESS_SPACE_EXHAUSTED"
    DUPLICATE_IPV4 = "DUPLICATE_IPV4"
    DHCP_STATIC_COLLISION = "DHCP_STATIC_COLLISION"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"
    CAPABILITY_UNVERIFIED = "CAPABILITY_UNVERIFIED"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    SOURCE_CONFIGURATION_HASH_MISSING = "SOURCE_CONFIGURATION_HASH_MISSING"
    SOURCE_CONFIGURATION_TOPOLOGY_MISMATCH = "SOURCE_CONFIGURATION_TOPOLOGY_MISMATCH"
    SERVICE_TYPE_INVALID = "SERVICE_TYPE_INVALID"
    SERVICE_HOST_MISSING = "SERVICE_HOST_MISSING"
    FOUNDATIONAL_CONFIGURATION_MISSING = "FOUNDATIONAL_CONFIGURATION_MISSING"
    FOUNDATIONAL_CONFIGURATION_MISMATCH = "FOUNDATIONAL_CONFIGURATION_MISMATCH"
    SERVICE_ADDRESS_INVALID = "SERVICE_ADDRESS_INVALID"
    SERVICE_ADDRESS_MISMATCH = "SERVICE_ADDRESS_MISMATCH"
    SERVICE_SEGMENT_MISMATCH = "SERVICE_SEGMENT_MISMATCH"
    SERVICE_CLIENT_MISSING = "SERVICE_CLIENT_MISSING"
    DNS_HOSTNAME_INVALID = "DNS_HOSTNAME_INVALID"
    DNS_RECORD_CONFLICT = "DNS_RECORD_CONFLICT"
    HTTP_CONTENT_UNSAFE = "HTTP_CONTENT_UNSAFE"
    TFTP_FILENAME_UNSAFE = "TFTP_FILENAME_UNSAFE"
    VOICE_SOURCE_SERVICE_MISMATCH = "VOICE_SOURCE_SERVICE_MISMATCH"
    VOICE_SERVICE_DEPENDENCY_MISSING = "VOICE_SERVICE_DEPENDENCY_MISSING"
    CALL_CONTROL_HOST_MISSING = "CALL_CONTROL_HOST_MISSING"
    CALL_CONTROL_ADDRESS_MISSING = "CALL_CONTROL_ADDRESS_MISSING"
    FOUNDATIONAL_VOICE_VLAN_MISSING = "FOUNDATIONAL_VOICE_VLAN_MISSING"
    PHONE_ADDRESSING_MISSING = "PHONE_ADDRESSING_MISSING"
    PHONE_ENDPOINT_MISSING = "PHONE_ENDPOINT_MISSING"
    EXTENSION_INVALID = "EXTENSION_INVALID"
    EXTENSION_COLLISION = "EXTENSION_COLLISION"
    EXTENSION_RANGE_INVALID = "EXTENSION_RANGE_INVALID"
    EXTENSION_RANGE_EXHAUSTED = "EXTENSION_RANGE_EXHAUSTED"
    VOICE_CAPABILITY_UNKNOWN = "VOICE_CAPABILITY_UNKNOWN"
    VOICE_CAPABILITY_UNSUPPORTED = "VOICE_CAPABILITY_UNSUPPORTED"
    SECURITY_SOURCE_HASH_MISSING = "SECURITY_SOURCE_HASH_MISSING"
    SECURITY_SOURCE_MISMATCH = "SECURITY_SOURCE_MISMATCH"
    SECURITY_SERVICE_MISSING = "SECURITY_SERVICE_MISSING"
    SECURITY_VOICE_DEPENDENCY_MISSING = "SECURITY_VOICE_DEPENDENCY_MISSING"
    SECURITY_SCOPE_MISSING = "SECURITY_SCOPE_MISSING"
    SECURITY_PLACEMENT_FAILED = "SECURITY_PLACEMENT_FAILED"
    SECURITY_POLICY_CONFLICT = "SECURITY_POLICY_CONFLICT"
    SECURITY_POLICY_SHADOWED = "SECURITY_POLICY_SHADOWED"
    SECURITY_CAPABILITY_UNKNOWN = "SECURITY_CAPABILITY_UNKNOWN"
    SECURITY_CAPABILITY_PARTIAL = "SECURITY_CAPABILITY_PARTIAL"
    SECURITY_CAPABILITY_UNOBSERVABLE = "SECURITY_CAPABILITY_UNOBSERVABLE"
    SECURITY_CAPABILITY_UNSUPPORTED = "SECURITY_CAPABILITY_UNSUPPORTED"
    SECURITY_NAT_INVALID = "SECURITY_NAT_INVALID"
    SECURITY_PORT_BINDING_MISSING = "SECURITY_PORT_BINDING_MISSING"
    SECURITY_VLAN_MISSING = "SECURITY_VLAN_MISSING"
    SECURITY_INTENT_INVALID = "SECURITY_INTENT_INVALID"
    CONTROL_PLANE_SOURCE_HASH_MISSING = "CONTROL_PLANE_SOURCE_HASH_MISSING"
    CONTROL_PLANE_SOURCE_MISMATCH = "CONTROL_PLANE_SOURCE_MISMATCH"
    CONTROL_PLANE_SECURITY_MISSING = "CONTROL_PLANE_SECURITY_MISSING"
    CONTROL_PLANE_SECURITY_POLICY_MISSING = "CONTROL_PLANE_SECURITY_POLICY_MISSING"
    CONTROL_PLANE_INTENT_INVALID = "CONTROL_PLANE_INTENT_INVALID"
    CONTROL_PLANE_CAPABILITY_UNKNOWN = "CONTROL_PLANE_CAPABILITY_UNKNOWN"
    CONTROL_PLANE_CAPABILITY_UNSUPPORTED = "CONTROL_PLANE_CAPABILITY_UNSUPPORTED"
    CONTROL_PLANE_STP_VLAN_MISSING = "CONTROL_PLANE_STP_VLAN_MISSING"
    CONTROL_PLANE_STP_ROOT_INVALID = "CONTROL_PLANE_STP_ROOT_INVALID"
    CONTROL_PLANE_MST_MAPPING_INVALID = "CONTROL_PLANE_MST_MAPPING_INVALID"
    CONTROL_PLANE_PORTFAST_TRUNK_CONFLICT = "CONTROL_PLANE_PORTFAST_TRUNK_CONFLICT"
    CONTROL_PLANE_LINK_MISSING = "CONTROL_PLANE_LINK_MISSING"
    CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID = "CONTROL_PLANE_ETHERCHANNEL_MEMBER_INVALID"
    CONTROL_PLANE_ETHERCHANNEL_TRUNK_MISSING = "CONTROL_PLANE_ETHERCHANNEL_TRUNK_MISSING"
    CONTROL_PLANE_ETHERCHANNEL_CONFLICT = "CONTROL_PLANE_ETHERCHANNEL_CONFLICT"
    CONTROL_PLANE_HSRP_FOUNDATION_MISSING = "CONTROL_PLANE_HSRP_FOUNDATION_MISSING"
    CONTROL_PLANE_HSRP_VIP_COLLISION = "CONTROL_PLANE_HSRP_VIP_COLLISION"
    CONTROL_PLANE_HSRP_VIP_INVALID = "CONTROL_PLANE_HSRP_VIP_INVALID"
    CONTROL_PLANE_ROUTING_FOUNDATION_MISSING = "CONTROL_PLANE_ROUTING_FOUNDATION_MISSING"
    CONTROL_PLANE_TRANSIT_L3_MISSING = "CONTROL_PLANE_TRANSIT_L3_MISSING"
    CONTROL_PLANE_TRANSIT_SUBNET_MISMATCH = "CONTROL_PLANE_TRANSIT_SUBNET_MISMATCH"
    CONTROL_PLANE_ROUTER_ID_COLLISION = "CONTROL_PLANE_ROUTER_ID_COLLISION"
    CONTROL_PLANE_FAILURE_RESTORE_REQUIRED = "CONTROL_PLANE_FAILURE_RESTORE_REQUIRED"
    CONTROL_PLANE_FAILURE_PROBE_MISSING = "CONTROL_PLANE_FAILURE_PROBE_MISSING"
    CONTROL_PLANE_FAILURE_DOMAIN_NOT_INDEPENDENT = "CONTROL_PLANE_FAILURE_DOMAIN_NOT_INDEPENDENT"
    CONTROL_PLANE_FAILURE_DOMAIN_UNKNOWN = "CONTROL_PLANE_FAILURE_DOMAIN_UNKNOWN"


class ConfigurationIssue(BaseModel):
    severity: ConfigurationIssueSeverity
    code: ConfigurationIssueCode
    message: str
    subject: str = ""
    details: dict[str, str | int | bool] = Field(default_factory=dict)


class ConfigurationPolicy(BaseModel):
    """Política explícita; completa intención sin depender de Packet Tracer."""

    vlan_ids_by_role: dict[SegmentRole, int] = Field(default_factory=lambda: {
        SegmentRole.DATA: 10,
        SegmentRole.VOICE: 20,
        SegmentRole.CCTV: 30,
        SegmentRole.PRINTERS: 40,
        SegmentRole.SERVERS: 50,
        SegmentRole.GUEST: 60,
        SegmentRole.WIRELESS_CORPORATE: 70,
        SegmentRole.MANAGEMENT: 99,
    })
    gateway_device_ids: dict[str, str] = Field(default_factory=dict)
    dhcp_server_device_ids: dict[str, str] = Field(default_factory=dict)
    native_vlan_id: int | None = None
    dns_server: str | None = None

    # Alinear el `bandwidth` logico de routing con la capacidad del enlace es
    # una decision de metricas, no un efecto secundario de tener un enlace.
    # Apagado por defecto: nadie lo pidio hasta que alguien lo pide.
    sync_routing_bandwidth: bool = False


class BaseConfigurationAction(BaseModel):
    id: str
    action_type: ConfigurationActionType
    phase: ConfigurationPhase
    device_id: str
    device_name: str
    site_id: str
    depends_on: list[str] = Field(default_factory=list)
    apply_dependencies: list[str] = Field(default_factory=list)
    required_capability: str = ""
    critical: bool = True
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    compensation_available: bool = False
    inverse_action_id: str = ""


class CreateVlan(BaseConfigurationAction):
    action_type: Literal[ConfigurationActionType.CREATE_VLAN] = ConfigurationActionType.CREATE_VLAN
    operation: Literal[
        OperationSemantics.ENSURE_PRESENT
    ] = OperationSemantics.ENSURE_PRESENT
    vlan_id: int
    name: str = ""
    segment_id: str = ""


class ConfigureAccessPort(BaseConfigurationAction):
    action_type: Literal[
        ConfigurationActionType.CONFIGURE_ACCESS_PORT
    ] = ConfigurationActionType.CONFIGURE_ACCESS_PORT
    interface: str
    data_vlan_id: int
    voice_vlan_id: int | None = None
    endpoint_ids: list[str] = Field(default_factory=list)


class ConfigureTrunk(BaseConfigurationAction):
    action_type: Literal[
        ConfigurationActionType.CONFIGURE_TRUNK
    ] = ConfigurationActionType.CONFIGURE_TRUNK
    interface: str
    allowed_vlans: list[int] = Field(default_factory=list)
    native_vlan_id: int | None = None
    peer_device_id: str = ""
    source_link_id: str = ""


class ConfigureRoutedInterface(BaseConfigurationAction):
    action_type: Literal[
        ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE
    ] = ConfigurationActionType.CONFIGURE_ROUTED_INTERFACE
    interface: str
    ipv4: str
    prefix: int
    netmask: str
    segment_id: str
    administrative_up: bool = True


class ConfigureSvi(BaseConfigurationAction):
    action_type: Literal[
        ConfigurationActionType.CONFIGURE_SVI
    ] = ConfigurationActionType.CONFIGURE_SVI
    vlan_id: int
    ipv4: str
    prefix: int
    netmask: str
    segment_id: str
    administrative_up: bool = True


class ConfigureSubinterface(BaseConfigurationAction):
    action_type: Literal[
        ConfigurationActionType.CONFIGURE_SUBINTERFACE
    ] = ConfigurationActionType.CONFIGURE_SUBINTERFACE
    parent_interface: str
    vlan_id: int
    ipv4: str
    prefix: int
    netmask: str
    segment_id: str
    encapsulation: str = "dot1Q"


class AddressRange(BaseModel):
    start: str
    end: str


class ConfigureDhcpPool(BaseConfigurationAction):
    action_type: Literal[
        ConfigurationActionType.CONFIGURE_DHCP_POOL
    ] = ConfigurationActionType.CONFIGURE_DHCP_POOL
    pool_name: str
    segment_id: str
    network: str
    prefix: int
    netmask: str
    gateway: str
    dns_server: str | None = None
    excluded_ranges: list[AddressRange] = Field(default_factory=list)
    lease_start: str
    lease_end: str


class SetEndpointStaticAddress(BaseConfigurationAction):
    action_type: Literal[
        ConfigurationActionType.SET_ENDPOINT_STATIC
    ] = ConfigurationActionType.SET_ENDPOINT_STATIC
    interface: str
    ipv4: str
    netmask: str
    gateway: str
    dns_server: str | None = None
    segment_id: str


class SetEndpointDhcp(BaseConfigurationAction):
    action_type: Literal[
        ConfigurationActionType.SET_ENDPOINT_DHCP
    ] = ConfigurationActionType.SET_ENDPOINT_DHCP
    interface: str
    segment_id: str
    network: str
    prefix: int
    netmask: str
    gateway: str
    dns_server: str | None = None


class ConfigureSerialClock(BaseConfigurationAction):
    """Reloj fisico del extremo DCE. Nunca se emite en ambos extremos."""

    action_type: Literal[
        ConfigurationActionType.CONFIGURE_SERIAL_CLOCK
    ] = ConfigurationActionType.CONFIGURE_SERIAL_CLOCK
    interface: str
    clock_rate_bps: int
    serial_endpoint_role: Literal["dce"] = "dce"
    source_link_id: str = ""


class ConfigureInterfaceBandwidth(BaseConfigurationAction):
    """Ancho de banda logico para metricas de routing, no el reloj del enlace."""

    action_type: Literal[
        ConfigurationActionType.CONFIGURE_INTERFACE_BANDWIDTH
    ] = ConfigurationActionType.CONFIGURE_INTERFACE_BANDWIDTH
    interface: str
    bandwidth_kbps: int


class ConfigureEthernetLinkMode(BaseConfigurationAction):
    """Velocidad y duplex explicitos; AUTO deja negociar al enlace."""

    action_type: Literal[
        ConfigurationActionType.CONFIGURE_ETHERNET_LINK_MODE
    ] = ConfigurationActionType.CONFIGURE_ETHERNET_LINK_MODE
    interface: str
    speed: str = "auto"
    duplex: str = "auto"


ConfigurationAction = Annotated[
    CreateVlan
    | ConfigureAccessPort
    | ConfigureTrunk
    | ConfigureRoutedInterface
    | ConfigureSvi
    | ConfigureSubinterface
    | ConfigureDhcpPool
    | SetEndpointStaticAddress
    | SetEndpointDhcp
    | ConfigureSerialClock
    | ConfigureInterfaceBandwidth
    | ConfigureEthernetLinkMode,
    Field(discriminator="action_type"),
]


class VerificationKind(str, Enum):
    VLAN = "vlan"
    ACCESS_PORT = "access_port"
    TRUNK = "trunk"
    L3_INTERFACE = "l3_interface"
    DHCP_POOL = "dhcp_pool"
    ENDPOINT_ADDRESSING = "endpoint_addressing"
    SERIAL_CONTROLLER = "serial_controller"


class VerificationExpectation(BaseModel):
    id: str
    action_id: str
    kind: VerificationKind
    device_id: str
    device_name: str
    expected: dict[str, str | int | bool | list[int]] = Field(default_factory=dict)
    required_query: str = ""
    verification_prerequisites: list[VerificationPrerequisite] = Field(default_factory=list)


class DeviceConfigurationPlan(BaseModel):
    device_id: str
    device_name: str
    model: str
    site_id: str
    action_ids: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)


class ConfigurationPlan(BaseModel):
    id: str
    source_topology_id: str
    source_topology_hash: str
    source_topology_hash_schema: str = "legacy-full-v1"
    semantic_hash: str = ""
    actions: list[ConfigurationAction] = Field(default_factory=list)
    devices: list[DeviceConfigurationPlan] = Field(default_factory=list)
    verification_expectations: list[VerificationExpectation] = Field(default_factory=list)

    def actions_for_device(self, device_id: str) -> list[ConfigurationAction]:
        return [action for action in self.actions if action.device_id == device_id]

    def actions_of_type(
        self, action_type: ConfigurationActionType,
    ) -> list[ConfigurationAction]:
        return [action for action in self.actions if action.action_type is action_type]


class ConfigurationCompileSummary(BaseModel):
    config_plan_id: str = ""
    semantic_hash: str = ""
    source_topology_hash: str = ""
    source_topology_hash_schema: str = ""
    devices: int = 0
    endpoint_devices: int = 0
    action_count: int = 0
    actions_by_type: dict[str, int] = Field(default_factory=dict)
    verification_expectations: int = 0
    warnings: int = 0
    errors: int = 0


class ConfigurationCompileResult(BaseModel):
    plan: ConfigurationPlan | None = None
    semantic_hash: str = ""
    summary: ConfigurationCompileSummary = Field(default_factory=ConfigurationCompileSummary)
    issues: list[ConfigurationIssue] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.plan is not None and not any(
            issue.severity is ConfigurationIssueSeverity.ERROR for issue in self.issues
        )

    def compact_summary(self) -> dict[str, str | int | dict[str, int] | list[dict]]:
        return {
            **self.summary.model_dump(mode="json"),
            "issues": [issue.model_dump(mode="json") for issue in self.issues],
        }


def action_type_counts(actions: list[ConfigurationAction]) -> dict[str, int]:
    counts = Counter(action.action_type.value for action in actions)
    return dict(sorted(counts.items()))
