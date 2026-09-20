"""Typed forwarding target identity, runtime address evidence and binding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

from .configuration_runtime import ActionExecutionStatus


class ForwardingAddressMode(StrEnum):
    """How the selected endpoint gets the address the plan names."""

    # Keep the qualified repr the `(str, Enum)` form produced, so no
    # existing message or record changes wording with the base class.
    __str__ = Enum.__str__

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
        """Return the eligible segments of one site, or nothing."""
        matches = [
            segments
            for site, segments in self.eligible_segment_ids_by_site
            if site == site_id
        ]
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
        """Return the four values that identify this selection."""
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
    """Whether one observation bound its selection, and why not."""

    status: ActionExecutionStatus
    binding: ForwardingEndpointBinding | None = None
    message: str = ""

    @property
    def verified(self) -> bool:
        """Whether this decision produced a usable binding."""
        return (
            self.status is ActionExecutionStatus.VERIFIED and self.binding is not None
        )


@dataclass(frozen=True)
class PortLightReading:
    """One `Port::getLightStatus()` value, strictly typed, and its meaning.

    `raw` holds the value only when the engine returned an actual integer;
    `raw_type` keeps what `typeof` reported, so a missing reader, a
    non-numeric return and an actual `0` stay three different observations.
    `interpretation` is the documented enum name, or `unknown`, and it is
    never derived from anything but `raw`.
    """

    device_name: str
    interface: str
    raw: int | None = None
    raw_type: str = "absent"
    interpretation: str = "unknown"
    failure_reason: str = ""


@dataclass(frozen=True)
class AccessForwardingRow:
    """One switch-side interface as one spanning-tree instance reported it."""

    interface: str
    #: How many rows of the instance matched this requested interface. Zero is
    #: a missing row and more than one is an ambiguous one; neither is a state.
    matches: int = 0
    state: str = ""
    role: str = ""


@dataclass(frozen=True)
class AccessForwardingObservation:
    """One bounded switch/VLAN forwarding sample, with nothing inferred.

    The observation carries the dimensions the registered IOS reader already
    separates -- execution, freshness, completeness and identity -- beside the
    per-interface rows, so the admission rule can refuse on each of them
    independently instead of collapsing them into one boolean.
    """

    switch_name: str
    vlan_id: int
    requested_interfaces: tuple[str, ...]
    rows: tuple[AccessForwardingRow, ...] = ()
    executed: bool = False
    fresh_output_observed: bool = False
    output_complete: bool = False
    observed_device_name: str = ""
    device_identity_provenance: str = ""
    vlan_present: bool = False
    samples: int = 0
    max_samples: int = 0
    deadline_seconds: float = 0.0
    elapsed_ms: int = 0
    deadline_reached: bool = False
    #: Every channel call one sample was allowed, and how many the whole
    #: observation actually made. A registered query is not one call:
    #: session preparation, the dispatch, output convergence, attribution
    #: and pager handling are nested calls a caller's own deadline cannot
    #: cap from outside, so they are bounded here and counted here.
    sample_call_budget: int = 0
    channel_calls: int = 0
    #: True when a sample ended on that budget rather than on its own
    #: completion. Such a sample is incomplete by construction: it is
    #: reported as exactly that and grants no forwarding permission.
    sample_budget_exhausted: bool = False
    #: What the simulation-time reader reported, when the composition supplied
    #: one. `absent` means no such reader was composed, which is a statement
    #: about this run and never a claim that simulation time did not move.
    simulation_time: str = "absent"
    failure_reason: str = ""
    lights: tuple[PortLightReading, ...] = ()


@dataclass(frozen=True)
class AccessForwardingAdmission:
    """Whether one sample grants forwarding permission, and why not."""

    admitted: bool
    dimension: str
    forwarding_interfaces: tuple[str, ...] = ()
    causes: tuple[str, ...] = ()
