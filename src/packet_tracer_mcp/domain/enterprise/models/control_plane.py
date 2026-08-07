"""Contratos backend-neutral de E9 para el control plane empresarial."""

from __future__ import annotations

from collections import Counter
from enum import Enum, IntEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .configuration import ConfigurationIssue
from .execution import OperationSemantics
from .evidence import CapabilityReadiness
from .security_plan import SecurityCapabilityStatus
from .verification import VerificationPrerequisite


class StpMode(str, Enum):
    PVST = "pvst"
    RAPID_PVST = "rapid-pvst"
    MST = "mst"


class EtherChannelProtocol(str, Enum):
    LACP = "lacp"
    PAGP = "pagp"
    STATIC = "static"


class DynamicRoutingProtocol(str, Enum):
    OSPFV2 = "ospfv2"
    EIGRP = "eigrp"


class ControlPlaneCapabilityDimension(str, Enum):
    STP_PVST_CONFIG = "stp_pvst_config"
    STP_RAPID_PVST_CONFIG = "stp_rapid_pvst_config"
    STP_MST_CONFIG = "stp_mst_config"
    ETHERCHANNEL_LACP_CONFIG = "etherchannel_lacp_config"
    ETHERCHANNEL_PAGP_CONFIG = "etherchannel_pagp_config"
    ETHERCHANNEL_STATIC_CONFIG = "etherchannel_static_config"
    HSRP_CONFIG = "hsrp_config"
    OSPFV2_CONFIG = "ospfv2_config"
    EIGRP_IPV4_CONFIG = "eigrp_ipv4_config"
    STP_READBACK = "stp_readback"
    ETHERCHANNEL_READBACK = "etherchannel_readback"
    HSRP_READBACK = "hsrp_readback"
    ROUTING_PROCESS_READBACK = "routing_process_readback"
    ROUTING_NEIGHBOR_READBACK = "routing_neighbor_readback"
    ROUTE_READBACK = "route_readback"
    BEHAVIORAL_REACHABILITY = "behavioral_reachability"
    LINK_FAILURE_CONTROL = "link_failure_control"
    STP_STATE = "stp_state"
    STP_BEHAVIOR = "stp_behavior"
    STP_FAILOVER = "stp_failover"
    ETHERCHANNEL_STATE = "etherchannel_state"
    ETHERCHANNEL_BEHAVIOR = "etherchannel_behavior"
    ETHERCHANNEL_FAILOVER = "etherchannel_failover"
    HSRP_STATE = "hsrp_state"
    HSRP_BEHAVIOR = "hsrp_behavior"
    HSRP_FAILOVER = "hsrp_failover"
    ROUTING_PROCESS_STATE = "routing_process_state"
    ROUTING_NEIGHBOR_STATE = "routing_neighbor_state"
    ROUTING_ROUTE_STATE = "routing_route_state"
    ROUTING_BEHAVIOR = "routing_behavior"
    ROUTING_FAILOVER = "routing_failover"


class ControlPlaneCapabilityProfile(BaseModel):
    model: str
    dimensions: dict[
        ControlPlaneCapabilityDimension, SecurityCapabilityStatus
    ] = Field(default_factory=dict)
    evidence_source: str = ""
    packet_tracer_version: str | None = None
    capability_readiness: dict[str, CapabilityReadiness] = Field(default_factory=dict)

    def status(
        self, dimension: ControlPlaneCapabilityDimension,
    ) -> SecurityCapabilityStatus:
        return self.dimensions.get(dimension, SecurityCapabilityStatus.UNKNOWN)

    @classmethod
    def supported(cls, model: str) -> "ControlPlaneCapabilityProfile":
        return cls(
            model=model,
            dimensions={
                dimension: SecurityCapabilityStatus.SUPPORTED
                for dimension in ControlPlaneCapabilityDimension
            },
            evidence_source="test fixture",
        )


class StpIntent(BaseModel):
    id: str = "stp/default"
    site_id: str = ""
    mode: StpMode = StpMode.RAPID_PVST
    vlan_ids: list[int] = Field(default_factory=list)
    root_primary_by_vlan: dict[int, str] = Field(default_factory=dict)
    root_secondary_by_vlan: dict[int, str] = Field(default_factory=dict)
    mst_instances: dict[int, list[int]] = Field(default_factory=dict)
    portfast_access_ports: bool = True
    bpduguard_access_ports: bool = True


class EtherChannelIntent(BaseModel):
    id: str
    member_link_ids: list[str]
    protocol: EtherChannelProtocol = EtherChannelProtocol.LACP
    channel_group: int | None = None


class FirstHopRedundancyIntent(BaseModel):
    id: str
    segment_id: str
    device_ids: list[str]
    virtual_ipv4: str = ""
    group_number: int | None = None
    priority_by_device: dict[str, int] = Field(default_factory=dict)
    preempt: bool = True


class DynamicRoutingIntent(BaseModel):
    id: str = "routing/default"
    site_id: str = ""
    protocol: DynamicRoutingProtocol
    device_ids: list[str] = Field(default_factory=list)
    transit_link_ids: list[str] = Field(default_factory=list)
    process_id: int = 1
    eigrp_as_number: int = 100
    area_by_segment: dict[str, int] = Field(default_factory=dict)
    router_ids: dict[str, str] = Field(default_factory=dict)
    passive_segment_ids: list[str] = Field(default_factory=list)


class LinkFailureScenarioIntent(BaseModel):
    id: str
    link_id: str
    probe_source_device_id: str
    probe_destination_device_id: str
    expected_surviving_link_ids: list[str] = Field(default_factory=list)
    restore_required: bool = True


class ControlPlaneIntent(BaseModel):
    id: str
    stp_domains: list[StpIntent] = Field(default_factory=list)
    stp: StpIntent | None = None
    etherchannels: list[EtherChannelIntent] = Field(default_factory=list)
    first_hop_redundancy: list[FirstHopRedundancyIntent] = Field(default_factory=list)
    routing_domains: list[DynamicRoutingIntent] = Field(default_factory=list)
    routing: DynamicRoutingIntent | None = None
    failure_scenarios: list[LinkFailureScenarioIntent] = Field(default_factory=list)
    security_policy_ids: list[str] = Field(default_factory=list)


class ControlPlanePhase(IntEnum):
    L2_FOUNDATION = 20
    L2_RESILIENCY = 30
    L3_RESILIENCY = 40
    DYNAMIC_ROUTING = 50


class ControlPlaneActionType(str, Enum):
    CONFIGURE_STP = "configure_stp"
    CONFIGURE_STP_EDGE_PORT = "configure_stp_edge_port"
    CONFIGURE_ETHERCHANNEL = "configure_etherchannel"
    CONFIGURE_HSRP = "configure_hsrp"
    CONFIGURE_OSPFV2 = "configure_ospfv2"
    CONFIGURE_EIGRP_IPV4 = "configure_eigrp_ipv4"


class BaseControlPlaneAction(BaseModel):
    id: str
    action_type: ControlPlaneActionType
    phase: ControlPlanePhase
    device_id: str
    device_name: str
    model: str
    site_id: str
    depends_on: list[str] = Field(default_factory=list)
    apply_dependencies: list[str] = Field(default_factory=list)
    required_capability: ControlPlaneCapabilityDimension
    critical: bool = True
    operation: OperationSemantics = OperationSemantics.SET_VALUE
    compensation_available: bool = False
    inverse_action_id: str = ""


class ConfigureSpanningTree(BaseControlPlaneAction):
    action_type: Literal[
        ControlPlaneActionType.CONFIGURE_STP
    ] = ControlPlaneActionType.CONFIGURE_STP
    mode: StpMode
    vlan_ids: list[int] = Field(default_factory=list)
    root_primary_vlans: list[int] = Field(default_factory=list)
    root_secondary_vlans: list[int] = Field(default_factory=list)
    priorities: dict[int, int] = Field(default_factory=dict)
    mst_instances: dict[int, list[int]] = Field(default_factory=dict)
    source_vlan_action_ids: list[str] = Field(default_factory=list)


class ConfigureStpEdgePort(BaseControlPlaneAction):
    action_type: Literal[
        ControlPlaneActionType.CONFIGURE_STP_EDGE_PORT
    ] = ControlPlaneActionType.CONFIGURE_STP_EDGE_PORT
    interface: str
    portfast: bool = True
    bpduguard: bool = True
    source_access_action_id: str


class ConfigureEtherChannel(BaseControlPlaneAction):
    action_type: Literal[
        ControlPlaneActionType.CONFIGURE_ETHERCHANNEL
    ] = ControlPlaneActionType.CONFIGURE_ETHERCHANNEL
    etherchannel_id: str
    peer_device_id: str
    protocol: EtherChannelProtocol
    channel_group: int
    port_channel_interface: str
    member_interfaces: list[str]
    allowed_vlans: list[int] = Field(default_factory=list)
    native_vlan_id: int | None = None
    source_link_ids: list[str] = Field(default_factory=list)
    source_trunk_action_ids: list[str] = Field(default_factory=list)


class ConfigureHsrp(BaseControlPlaneAction):
    action_type: Literal[
        ControlPlaneActionType.CONFIGURE_HSRP
    ] = ControlPlaneActionType.CONFIGURE_HSRP
    redundancy_id: str
    interface: str
    segment_id: str
    group_number: int
    virtual_ipv4: str
    physical_ipv4: str
    priority: int = 100
    preempt: bool = True
    source_configuration_action_id: str


class RoutingNetwork(BaseModel):
    network: str
    wildcard: str
    segment_id: str
    interface: str
    source_configuration_action_id: str
    area: int | None = None


class ConfigureOspfv2(BaseControlPlaneAction):
    action_type: Literal[
        ControlPlaneActionType.CONFIGURE_OSPFV2
    ] = ControlPlaneActionType.CONFIGURE_OSPFV2
    process_id: int
    router_id: str
    networks: list[RoutingNetwork] = Field(default_factory=list)
    passive_interfaces: list[str] = Field(default_factory=list)


class ConfigureEigrpIpv4(BaseControlPlaneAction):
    action_type: Literal[
        ControlPlaneActionType.CONFIGURE_EIGRP_IPV4
    ] = ControlPlaneActionType.CONFIGURE_EIGRP_IPV4
    as_number: int
    router_id: str
    networks: list[RoutingNetwork] = Field(default_factory=list)
    passive_interfaces: list[str] = Field(default_factory=list)
    no_auto_summary: bool = True


ControlPlaneAction = Annotated[
    ConfigureSpanningTree
    | ConfigureStpEdgePort
    | ConfigureEtherChannel
    | ConfigureHsrp
    | ConfigureOspfv2
    | ConfigureEigrpIpv4,
    Field(discriminator="action_type"),
]


class ControlPlaneFoundationRequirement(BaseModel):
    id: str
    kind: Literal[
        "l3_interface", "endpoint_address", "vlan", "access_port", "trunk",
        "link", "security",
    ]
    source_id: str
    source_hash: str = ""


class ControlPlaneVerificationKind(str, Enum):
    STP_STATE = "stp_state"
    ETHERCHANNEL_STATE = "etherchannel_state"
    HSRP_STATE = "hsrp_state"
    ROUTING_PROCESS = "routing_process"
    ROUTING_NEIGHBOR = "routing_neighbor"
    ROUTE_PRESENT = "route_present"
    END_TO_END_REACHABILITY = "end_to_end_reachability"
    LINK_FAILURE_CONVERGENCE = "link_failure_convergence"
    RESTORE_RECOVERY = "restore_recovery"


class ControlPlaneVerificationExpectation(BaseModel):
    id: str
    kind: ControlPlaneVerificationKind
    action_id: str
    device_id: str
    peer_device_id: str = ""
    source_link_id: str = ""
    required_capability: ControlPlaneCapabilityDimension
    expected: dict[str, str | int | bool | list[str] | list[int]] = Field(
        default_factory=dict,
    )
    depends_on: list[str] = Field(default_factory=list)
    verification_prerequisites: list[VerificationPrerequisite] = Field(default_factory=list)


class LinkFailureScenario(BaseModel):
    id: str
    link_id: str
    device_a_id: str
    device_b_id: str
    target_device_id: str
    target_device_name: str
    target_interface: str
    peer_device_id: str
    peer_device_name: str
    peer_interface: str
    cable: str
    probe_source_device_id: str
    probe_source_device_name: str
    probe_destination_device_id: str
    probe_destination_device_name: str
    probe_destination_ipv4: str
    expected_surviving_link_ids: list[str] = Field(default_factory=list)
    restore_required: bool = True
    verification_expectation_ids: list[str] = Field(default_factory=list)


class ControlPlanePlan(BaseModel):
    id: str
    source_topology_id: str
    source_topology_hash: str
    source_topology_hash_schema: str = "legacy-full-v1"
    source_configuration_id: str
    source_configuration_hash: str
    source_security_id: str = ""
    source_security_hash: str = ""
    security_policy_ids: list[str] = Field(default_factory=list)
    semantic_hash: str = ""
    actions: list[ControlPlaneAction] = Field(default_factory=list)
    foundational_requirements: list[ControlPlaneFoundationRequirement] = Field(
        default_factory=list,
    )
    verification_expectations: list[ControlPlaneVerificationExpectation] = Field(
        default_factory=list,
    )
    failure_scenarios: list[LinkFailureScenario] = Field(default_factory=list)

    def actions_of_type(
        self, action_type: ControlPlaneActionType,
    ) -> list[ControlPlaneAction]:
        return [item for item in self.actions if item.action_type is action_type]


class ControlPlaneCompileSummary(BaseModel):
    control_plane_plan_id: str = ""
    semantic_hash: str = ""
    source_topology_hash: str = ""
    source_topology_hash_schema: str = ""
    source_configuration_hash: str = ""
    source_security_hash: str = ""
    action_count: int = 0
    actions_by_type: dict[str, int] = Field(default_factory=dict)
    dependencies: int = 0
    verification_count: int = 0
    failure_scenario_count: int = 0
    warnings: int = 0
    errors: int = 0


class ControlPlaneCompileResult(BaseModel):
    plan: ControlPlanePlan | None = None
    semantic_hash: str = ""
    summary: ControlPlaneCompileSummary = Field(
        default_factory=ControlPlaneCompileSummary,
    )
    issues: list[ConfigurationIssue] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        from .configuration import ConfigurationIssueSeverity

        return self.plan is not None and not any(
            item.severity is ConfigurationIssueSeverity.ERROR for item in self.issues
        )

    def compact_summary(self) -> dict[str, object]:
        return {
            **self.summary.model_dump(mode="json"),
            "issues": [item.model_dump(mode="json") for item in self.issues],
        }


def control_plane_action_type_counts(
    actions: list[ControlPlaneAction],
) -> dict[str, int]:
    counts = Counter(item.action_type.value for item in actions)
    return dict(sorted(counts.items()))
