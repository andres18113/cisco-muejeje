"""Pure forwarding selection and binding rules shared by E9 and CP-LIVE."""

from __future__ import annotations

import ipaddress

from ...models.plans import TopologyPlan
from ..models.configuration import (
    ConfigureRoutedInterface,
    ConfigureSubinterface,
    ConfigureSvi,
    ConfigurationPlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ..models.configuration_runtime import ActionExecutionStatus
from ..models.deployment import DeploymentIdentityError, DeploymentManifest
from ..models.forwarding import (
    ForwardingAddressMode,
    ForwardingAddressObservation,
    ForwardingBindingDecision,
    ForwardingEndpointBinding,
    ForwardingEndpointSelection,
    ForwardingKnownAddress,
    ForwardingRuntimeEndpoint,
    ForwardingWorkloadPolicy,
)
from .configuration_compiler import configuration_plan_semantic_hash
from .topology_identity import compute_topology_hashes


_L3_ACTIONS = (ConfigureRoutedInterface, ConfigureSubinterface, ConfigureSvi)
_ENDPOINT_ACTIONS = (SetEndpointDhcp, SetEndpointStaticAddress)


class ForwardingSelectionError(ValueError):
    """The plan cannot identify one target without guessing."""


def select_forwarding_workload(
    topology: TopologyPlan,
    configuration: ConfigurationPlan,
    *,
    policy: ForwardingWorkloadPolicy,
    site_id: str,
    routing_device_id: str,
) -> ForwardingEndpointSelection:
    """Select one eligible wired data workload by semantic identity."""

    _validate_plan_provenance(topology, configuration)
    devices = {item.id: item for item in topology.devices}
    router = devices.get(routing_device_id)
    if router is None or router.site_id != site_id:
        raise ForwardingSelectionError(
            f"Forwarding site {site_id!r} has no matching projected routing device."
        )
    allowed_segments = set(policy.segment_ids_for(site_id))
    if not allowed_segments:
        raise ForwardingSelectionError(
            f"Forwarding policy {policy.id!r} declares no data segment for {site_id!r}."
        )
    routed_segments = {
        item.segment_id
        for item in configuration.actions
        if isinstance(item, _L3_ACTIONS) and item.device_id == routing_device_id
    }
    allowed_segments &= routed_segments
    if not allowed_segments:
        raise ForwardingSelectionError(
            f"Forwarding policy {policy.id!r} has no E5 segment routed by {routing_device_id!r}."
        )

    endpoint_actions: dict[str, list[SetEndpointDhcp | SetEndpointStaticAddress]] = {}
    for action in configuration.actions:
        if isinstance(action, _ENDPOINT_ACTIONS):
            endpoint_actions.setdefault(action.device_id, []).append(action)
    candidates = [
        item
        for item in topology.devices
        if item.site_id == site_id
        and item.enterprise_role in policy.eligible_endpoint_roles
        and item.metadata.get(policy.workload_metadata_key)
        == policy.workload_metadata_value
        and (not policy.require_wired or item.wireless is False)
    ]
    resolved: list[tuple[object, SetEndpointDhcp | SetEndpointStaticAddress, object]] = []
    for device in sorted(candidates, key=lambda item: item.id):
        actions = endpoint_actions.get(device.id, [])
        if len(actions) != 1:
            raise ForwardingSelectionError(
                f"Eligible workload {device.id!r} has {len(actions)} E5 addressing actions; exactly one is required."
            )
        action = actions[0]
        if action.site_id != site_id or action.device_name != device.name:
            raise ForwardingSelectionError(
                f"Eligible workload {device.id!r} has ambiguous E4/E5 identity."
            )
        if action.segment_id not in allowed_segments:
            continue
        links = [
            link
            for link in topology.links
            if (
                link.device_a_id == device.id
                and link.port_a == action.interface
                and link.device_b_id in devices
            )
            or (
                link.device_b_id == device.id
                and link.port_b == action.interface
                and link.device_a_id in devices
            )
        ]
        if len(links) != 1:
            raise ForwardingSelectionError(
                f"Eligible workload {device.id!r} has {len(links)} exact projected links on {action.interface!r}; exactly one is required."
            )
        resolved.append((device, action, links[0]))
    if not resolved:
        raise ForwardingSelectionError(
            f"No eligible wired data workload is projected for {site_id!r}; router and infrastructure fallbacks are forbidden."
        )
    device, action, link = min(
        resolved,
        key=lambda item: (item[0].id, item[1].id, item[2].id),
    )
    if link.device_a_id == device.id:
        peer_device_id, peer_interface = link.device_b_id, link.port_b
    else:
        peer_device_id, peer_interface = link.device_a_id, link.port_a

    if isinstance(action, SetEndpointStaticAddress):
        try:
            network = ipaddress.ip_network(
                f"{action.ipv4}/{action.netmask}", strict=False,
            )
        except ValueError as exc:
            raise ForwardingSelectionError(
                f"Static E5 action {action.id!r} has invalid IPv4/netmask."
            ) from exc
        mode = ForwardingAddressMode.STATIC
        planned_ipv4: str | None = action.ipv4
    else:
        try:
            network = ipaddress.ip_network(
                f"{action.network}/{action.prefix}", strict=True,
            )
        except ValueError as exc:
            raise ForwardingSelectionError(
                f"DHCP E5 action {action.id!r} has invalid network/prefix."
            ) from exc
        if str(network.netmask) != action.netmask:
            raise ForwardingSelectionError(
                f"DHCP E5 action {action.id!r} netmask does not match its prefix."
            )
        mode = ForwardingAddressMode.DHCP
        planned_ipv4 = None

    return ForwardingEndpointSelection(
        policy_id=policy.id,
        policy_version=policy.version,
        source_topology_id=topology.id,
        source_topology_hash=topology.physical_identity_hash,
        source_configuration_id=configuration.id,
        source_configuration_hash=configuration.semantic_hash,
        site_id=site_id,
        routing_device_id=routing_device_id,
        endpoint_device_id=device.id,
        endpoint_device_name=device.name,
        endpoint_model=device.model,
        endpoint_role=device.enterprise_role,
        link_id=link.id,
        endpoint_interface=action.interface,
        peer_device_id=peer_device_id,
        peer_interface=peer_interface,
        segment_id=action.segment_id,
        address_mode=mode,
        configuration_action_id=action.id,
        planned_ipv4=planned_ipv4,
        network=str(network.network_address),
        prefix_length=network.prefixlen,
        netmask=str(network.netmask),
        known_plan_addresses=_known_plan_addresses(configuration),
    )


def resolve_forwarding_runtime_endpoint(
    selection: ForwardingEndpointSelection,
    manifest: DeploymentManifest,
) -> ForwardingRuntimeEndpoint:
    """Bind semantic endpoint/link identity to one manifest target."""

    if manifest.physical_topology_hash != selection.source_topology_hash:
        raise DeploymentIdentityError(
            "Forwarding selection topology hash does not match DeploymentManifest."
        )
    binding = manifest.binding_for(selection.endpoint_device_id)
    if binding.model != selection.endpoint_model:
        raise DeploymentIdentityError(
            "Forwarding endpoint model differs from its manifest binding."
        )
    if selection.endpoint_interface not in binding.ports:
        raise DeploymentIdentityError(
            "Forwarding endpoint interface is absent from its manifest binding."
        )
    link = manifest.link_binding_for(selection.link_id)
    endpoint = link.endpoint_for(selection.endpoint_device_id)
    peer = link.endpoint_for(selection.peer_device_id)
    if (
        endpoint.interface != selection.endpoint_interface
        or peer.interface != selection.peer_interface
    ):
        raise DeploymentIdentityError(
            "Forwarding link interfaces differ from the selected E4 link."
        )
    return ForwardingRuntimeEndpoint(
        selection=selection,
        runtime_device_name=binding.deployed_name,
        identity_method=binding.identity_method.value,
        deployment_id=manifest.deployment_id,
        deployment_manifest_hash=manifest.semantic_hash,
        runtime_link_identifier=link.runtime_link_identifier,
        runtime_link_identity_observed=link.runtime_link_identity_observed,
    )


def bind_forwarding_address(
    target: ForwardingRuntimeEndpoint,
    observation: ForwardingAddressObservation,
) -> ForwardingBindingDecision:
    """Validate a fresh observed IP/mask against the selected E5 action."""

    selection = target.selection
    if not observation.fresh_evidence:
        return ForwardingBindingDecision(
            ActionExecutionStatus.UNOBSERVABLE,
            message=observation.failure_reason or "No fresh endpoint address read was observed.",
        )
    if (
        observation.runtime_device_name != target.runtime_device_name
        or observation.interface != selection.endpoint_interface
    ):
        return ForwardingBindingDecision(
            ActionExecutionStatus.FAILED,
            message="Endpoint address evidence is attributed to a different runtime identity or interface.",
        )
    if not observation.device_found or not observation.port_found:
        return ForwardingBindingDecision(
            ActionExecutionStatus.FAILED,
            message="The manifest-bound endpoint or exact interface is absent at runtime.",
        )
    if not observation.address_channel:
        return ForwardingBindingDecision(
            ActionExecutionStatus.UNOBSERVABLE,
            message="The exact endpoint interface exposes no IP/mask getter channel.",
        )
    try:
        address = ipaddress.ip_address(observation.ipv4)
        network = ipaddress.ip_network(
            f"{selection.network}/{selection.prefix_length}", strict=True,
        )
    except ValueError:
        return ForwardingBindingDecision(
            ActionExecutionStatus.FAILED,
            message="The observed endpoint IPv4 or selected E5 network is invalid.",
        )
    if observation.netmask != selection.netmask:
        return ForwardingBindingDecision(
            ActionExecutionStatus.FAILED,
            message="The observed endpoint mask contradicts the selected E5 action.",
        )
    if selection.address_mode is ForwardingAddressMode.STATIC:
        address_matches = observation.ipv4 == selection.planned_ipv4
    else:
        address_matches = (
            address in network
            and address not in {network.network_address, network.broadcast_address}
        )
    if not address_matches:
        return ForwardingBindingDecision(
            ActionExecutionStatus.FAILED,
            message="The observed endpoint address contradicts the selected E5 action.",
        )
    conflict = next(
        (
            item
            for item in selection.known_plan_addresses
            if item.ipv4 == observation.ipv4
            and item.action_id != selection.configuration_action_id
        ),
        None,
    )
    if conflict is not None:
        return ForwardingBindingDecision(
            ActionExecutionStatus.FAILED,
            message=(
                f"Observed address conflicts with known E5 action {conflict.action_id!r}; "
                "no universal duplicate-address claim is made."
            ),
        )
    return ForwardingBindingDecision(
        ActionExecutionStatus.VERIFIED,
        ForwardingEndpointBinding(
            target=target,
            ipv4=observation.ipv4,
            netmask=observation.netmask,
            evidence_method=observation.evidence_method,
            fresh_evidence=True,
        ),
    )


def forwarding_binding_stability(
    binding: ForwardingEndpointBinding,
    observation: ForwardingAddressObservation,
) -> ForwardingBindingDecision:
    """Re-read one exact endpoint and reject any identity/address drift."""

    decision = bind_forwarding_address(binding.target, observation)
    if not decision.verified:
        return decision
    current = decision.binding
    if current is None or (current.ipv4, current.netmask) != (
        binding.ipv4,
        binding.netmask,
    ):
        return ForwardingBindingDecision(
            ActionExecutionStatus.FAILED,
            message="Endpoint address changed during the forwarding probe.",
        )
    return decision


def coobserved_binding_conflict(
    bindings: tuple[ForwardingEndpointBinding, ...],
) -> str:
    """Detect duplicates only within this observed representative cohort."""

    by_address: dict[str, list[str]] = {}
    for binding in bindings:
        by_address.setdefault(binding.ipv4, []).append(
            binding.target.selection.endpoint_device_id,
        )
    duplicate = next(
        ((address, ids) for address, ids in sorted(by_address.items()) if len(ids) > 1),
        None,
    )
    if duplicate is None:
        return ""
    address, identifiers = duplicate
    return (
        f"Observed address {address} is shared by selected endpoints "
        + ", ".join(sorted(identifiers))
        + "; this check covers only the co-observed representative cohort."
    )


def _validate_plan_provenance(
    topology: TopologyPlan,
    configuration: ConfigurationPlan,
) -> None:
    if (
        compute_topology_hashes(topology).physical_topology_hash
        != topology.physical_identity_hash
    ):
        raise ForwardingSelectionError("Forwarding E4 physical provenance is stale.")
    if configuration.source_topology_hash != topology.physical_identity_hash:
        raise ForwardingSelectionError("Forwarding E5 source does not match E4.")
    if configuration_plan_semantic_hash(configuration) != configuration.semantic_hash:
        raise ForwardingSelectionError("Forwarding E5 semantic provenance is stale.")


def _known_plan_addresses(
    configuration: ConfigurationPlan,
) -> tuple[ForwardingKnownAddress, ...]:
    known: list[ForwardingKnownAddress] = []
    for action in configuration.actions:
        value = getattr(action, "ipv4", "")
        if not value:
            continue
        try:
            normalized = str(ipaddress.ip_address(value))
        except ValueError:
            continue
        known.append(ForwardingKnownAddress(
            ipv4=normalized,
            action_id=action.id,
            device_id=action.device_id,
        ))
    return tuple(sorted(known, key=lambda item: (item.ipv4, item.action_id)))
