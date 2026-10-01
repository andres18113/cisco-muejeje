"""Admission of the selected service paths of one compiled service plan.

`path_admission` classifies every selected client-to-server dependency against
the compiled configuration and names each refusal, returning the routed paths
it admitted. `dhcp_prelease_paths` turns admitted DHCP paths into labelled
pre-lease route targets. The product's service entry and the SP-2 remote-relay
qualification both consume these functions, so neither re-derives the rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from ipaddress import ip_network
from typing import Any

from ...domain.enterprise.models.configuration import (
    ConfigureAccessPort,
    ConfigureDhcpRelay,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
    VerificationKind,
)
from ...domain.enterprise.models.service_plan import (
    ServiceDefinition,
    ServicePlan,
    ServiceType,
)
from ...domain.enterprise.services.routed_service_path import (
    RoutedPath,
    RoutedPlanIndex,
    derive_routed_path,
    dhcp_endpoint_networks,
    endpoint_addresses,
)
from ...domain.enterprise.services.service_path_closure import (
    PathKind,
    PathTopology,
    classify_path,
)


def dhcp_prelease_paths(
    paths: Mapping[tuple[str, str], RoutedPath],
    services: Sequence[ServiceDefinition],
) -> dict[tuple[str, str], RoutedPath]:
    """Use a labeled network target only for pre-lease route observation.

    The original path keeps `client_ipv4` empty until an attributed lease
    binds the application gate. A network address here is a route lookup
    target, never a claimed client address or a static endpoint fallback.
    """
    selected = {item.id for item in services if item.service_type is ServiceType.DHCP}
    result: dict[tuple[str, str], RoutedPath] = {}
    for (service_id, _client_id), path in paths.items():
        if service_id not in selected or not path.client_network:
            continue
        target = ip_network(path.client_network, strict=True)
        pair = (path.client_device_id, path.host_device_id)
        candidate = replace(path, client_ipv4=str(target.network_address))
        prior = result.get(pair)
        if prior is not None and prior != candidate:
            raise ValueError("conflicting DHCP pre-lease routed paths")
        result[pair] = candidate
    return result


def path_admission(
    configuration_plan: Any,
    plan: ServicePlan,
    services: Sequence[ServiceDefinition],
    *,
    links: Sequence[Any] = (),
) -> tuple[list[str], dict[tuple[str, str], RoutedPath]]:
    """Classify every selected dependency; name refusals, return routed paths.

    R-NET-01. Each selected client-to-server dependency must be a static (or
    delegated DHCP) endpoint pair of the service's site and segment, each end
    placed by exactly one access switch, joined either on one access switch
    or through compiled trunk links that carry the segment's VLAN between two
    access switches. The trunk path is not assumed from the compilation: the
    readiness gate proves it before any dependent request.

    SP-1 expands the boundary to routed paths. A client in another segment or
    site is admitted when `derive_routed_path` follows both L2 legs, both
    gateways and complete forward and return static-route chains in the
    compiled plans (E4 links included); otherwise the first precise reason
    refuses it. The host must still be static and in the service's own site
    and segment, and routed clients must be static.
    """
    requirements: dict[str, list[Any]] = {}
    for item in plan.foundational_requirements:
        requirements.setdefault(item.device_id, []).append(item)
    actions = {item.id: item for item in configuration_plan.actions}
    topology = PathTopology(configuration_plan.actions)
    component_configuration_action_ids = {
        item.action_id
        for item in configuration_plan.verification_expectations
        if item.kind is VerificationKind.TRUNK_CONFIGURATION
    }
    delegated_claims: dict[str, set[tuple[str, str]]] = {}
    for service in services:
        if service.service_type is not ServiceType.DHCP:
            continue
        for client_id in service.client_device_ids:
            delegated_claims.setdefault(client_id, set()).add(
                (service.segment_id, service.host_device_id)
            )

    def access_switches(action_id: str) -> set[str]:
        switches: set[str] = set()
        pending = [action_id]
        visited: set[str] = set()
        while pending:
            identifier = pending.pop()
            if identifier in visited:
                continue
            visited.add(identifier)
            action = actions.get(identifier)
            if action is None:
                continue
            if isinstance(action, ConfigureAccessPort):
                switches.add(action.device_id)
            if isinstance(action, ConfigureDhcpRelay):
                continue
            pending.extend([*action.depends_on, *action.apply_dependencies])
        return switches

    unsupported: list[str] = []
    routed: dict[tuple[str, str], RoutedPath] = {}
    index: RoutedPlanIndex | None = None
    addresses = endpoint_addresses(configuration_plan.actions)
    dhcp_networks = dhcp_endpoint_networks(configuration_plan.actions)
    relays: dict[str, list[ConfigureDhcpRelay]] = {}
    for action in configuration_plan.actions:
        if isinstance(action, ConfigureDhcpRelay):
            relays.setdefault(action.segment_id, []).append(action)
    for service in services:
        placed: set[str] = set()
        segments: dict[str, str] = {}
        for device_id in [service.host_device_id, *service.client_device_ids]:
            matches = requirements.get(device_id, [])
            if len(matches) != 1:
                unsupported.append(f"{service.id}:{device_id}:foundation_identity")
                continue
            requirement = matches[0]
            segments[device_id] = requirement.segment_id
            expected_model = (
                "Server-PT" if device_id == service.host_device_id else "PC-PT"
            )
            if requirement.model.casefold() != expected_model.casefold():
                unsupported.append(
                    f"{service.id}:{device_id}:model_{requirement.model}"
                )
            action = actions.get(requirement.configuration_action_id)
            if action is None:
                unsupported.append(f"{service.id}:{device_id}:foundation_missing")
                continue
            if isinstance(action, SetEndpointDhcp):
                claims = delegated_claims.get(device_id, set())
                if not claims:
                    unsupported.append(f"{service.id}:{device_id}:dhcp")
                    continue
                if len(claims) != 1 or next(iter(claims))[0] != action.segment_id:
                    unsupported.append(f"{service.id}:{device_id}:dhcp_authority")
                    continue
            elif not isinstance(action, SetEndpointStaticAddress):
                unsupported.append(f"{service.id}:{device_id}:not_static")
                continue
            if (
                service.service_type is not ServiceType.DHCP
                and device_id == service.host_device_id
                and action.site_id != service.site_id
            ):
                unsupported.append(f"{service.id}:{device_id}:foreign_site")
            if (
                service.service_type is not ServiceType.DHCP
                and device_id == service.host_device_id
                and requirement.segment_id != service.segment_id
            ):
                unsupported.append(f"{service.id}:{device_id}:host_segment")
            if len(access_switches(action.id)) != 1:
                unsupported.append(f"{service.id}:{device_id}:switching_prerequisite")
                continue
            placed.add(device_id)
        if service.host_device_id not in placed:
            continue
        for client_id in service.client_device_ids:
            if client_id not in placed:
                continue
            path = classify_path(
                topology,
                client_device_id=client_id,
                host_device_id=service.host_device_id,
                segments=segments,
            )
            if path.kind is PathKind.ROUTED:
                client = addresses.get(client_id) or dhcp_networks.get(client_id)
                host = addresses.get(service.host_device_id)
                if client is None or host is None:
                    unsupported.append(
                        f"{service.id}:{client_id}:routed_endpoint_unresolved"
                    )
                    continue
                relay = None
                if client.network:
                    candidates = relays.get(client.segment_id, [])
                    authority = next(iter(delegated_claims[client_id]))[1]
                    server_address = addresses.get(authority)
                    if (
                        len(candidates) != 1
                        or server_address is None
                        or candidates[0].server_address != server_address.ipv4
                    ):
                        unsupported.append(
                            f"{service.id}:{client_id}:dhcp_relay_unresolved"
                        )
                        continue
                    relay = candidates[0]
                if index is None:
                    index = RoutedPlanIndex(
                        configuration_plan.actions,
                        links,
                        component_configuration_action_ids=(
                            component_configuration_action_ids
                        ),
                    )
                derived = derive_routed_path(index, client=client, host=host)
                if not derived.admitted:
                    unsupported.append(f"{service.id}:{client_id}:{derived.reason}")
                    continue
                if relay is not None:
                    derived = replace(
                        derived, action_ids=derived.action_ids | {relay.id}
                    )
                routed[(service.id, client_id)] = derived
            elif path.kind is PathKind.UNPLACED:
                unsupported.append(f"{service.id}:{client_id}:{path.reason}")
    return sorted(unsupported), routed
