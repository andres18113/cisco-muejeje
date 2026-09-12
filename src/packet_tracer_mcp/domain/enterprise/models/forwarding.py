"""Typed forwarding target identity, runtime address evidence and binding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .configuration_runtime import ActionExecutionStatus


class ForwardingAddressMode(str, Enum):
    STATIC = "static"
    DHCP = "dhcp"


@dataclass(frozen=True)
class ForwardingKnownAddress:
    """One fixed IPv4 identity visible in E5, not a universal lease view."""

    ipv4: str
    action_id: str
    device_id: str


@dataclass(frozen=True)
class ForwardingWorkloadPolicy:
    """Explicit opt-in policy; generic E9 compilation does not assume it."""

    id: str
    version: str
    eligible_endpoint_roles: tuple[str, ...]
    eligible_segment_ids_by_site: tuple[tuple[str, tuple[str, ...]], ...]
    workload_metadata_key: str = "requirement.workload_endpoint"
    workload_metadata_value: str = "true"
    require_wired: bool = True

    def segment_ids_for(self, site_id: str) -> tuple[str, ...]:
        matches = [segments for site, segments in self.eligible_segment_ids_by_site if site == site_id]
        if len(matches) != 1:
            return ()
        return matches[0]


@dataclass(frozen=True)
class ForwardingEndpointSelection:
    """Plan-only target identity. A LIVE address never enters this object."""

    policy_id: str
    policy_version: str
    source_topology_id: str
    source_topology_hash: str
    source_configuration_id: str
    source_configuration_hash: str
    site_id: str
    routing_device_id: str
    endpoint_device_id: str
    endpoint_device_name: str
    endpoint_model: str
    endpoint_role: str
    link_id: str
    endpoint_interface: str
    peer_device_id: str
    peer_interface: str
    segment_id: str
    address_mode: ForwardingAddressMode
    configuration_action_id: str
    planned_ipv4: str | None
    network: str
    prefix_length: int
    netmask: str
    known_plan_addresses: tuple[ForwardingKnownAddress, ...] = ()

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (
            self.endpoint_device_id,
            self.endpoint_interface,
            self.segment_id,
            self.configuration_action_id,
        )


@dataclass(frozen=True)
class ForwardingRuntimeEndpoint:
    """Execution-only correspondence between a selection and the manifest."""

    selection: ForwardingEndpointSelection
    runtime_device_name: str
    identity_method: str
    deployment_id: str
    deployment_manifest_hash: str
    runtime_link_identifier: str = ""
    runtime_link_identity_observed: bool = False


@dataclass(frozen=True)
class ForwardingAddressObservation:
    """Only the endpoint IP/mask getters qualified on Packet Tracer."""

    runtime_device_name: str
    interface: str
    device_found: bool
    port_found: bool
    address_channel: bool
    ipv4: str = ""
    netmask: str = ""
    fresh_evidence: bool = False
    evidence_method: str = "structured_endpoint_getters"
    failure_reason: str = ""


@dataclass(frozen=True)
class ForwardingEndpointBinding:
    """Fresh execution evidence; deliberately absent from all plan hashes."""

    target: ForwardingRuntimeEndpoint
    ipv4: str
    netmask: str
    evidence_method: str
    fresh_evidence: bool
    conflict_validation_scope: str = (
        "selected E5 fixed addresses and co-observed forwarding bindings"
    )


@dataclass(frozen=True)
class ForwardingBindingDecision:
    status: ActionExecutionStatus
    binding: ForwardingEndpointBinding | None = None
    message: str = ""

    @property
    def verified(self) -> bool:
        return self.status is ActionExecutionStatus.VERIFIED and self.binding is not None
