"""SP-1 routed fixtures, composed through the real designer and compilers.

Every plan here is what the product itself compiles from an intent; only the
deployment inventory is derived offline from the E4 topology, exactly as the
single-segment `service_entry_fixture` does. Addresses are never hardcoded in
assertions: tests read the E5 plan and derive their expectations from it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from service_entry_fixture import BACKEND_VERSION, DEPLOYMENT_ID, FINGERPRINT

from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentManifest,
    build_deployment_manifest,
)
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent

#: A run-specific page marker and host name keep one run's evidence from
#: satisfying another; tests may override both.
MARKER = "SP1_ROUTED_4d1c9e2a7b3f"
HOSTNAME = "www.sp1-4d1c9e.lab.example"


def _site(
    name: str,
    kind: str,
    users: int,
    *,
    servers: bool = False,
) -> dict[str, Any]:
    endpoints: list[dict[str, Any]] = [
        {"role": "user_pc", "count": users, "addressing_preference": "static"}
    ]
    if servers:
        endpoints += [
            {
                "role": "dns_server",
                "count": 1,
                "addressing_preference": "static",
                "segment_role": "servers",
            },
            {
                "role": "web_server",
                "count": 1,
                "addressing_preference": "static",
                "segment_role": "servers",
            },
        ]
    return {"name": name, "type": kind, "endpoints": endpoints}


def topology_payload(
    *,
    sites: int = 3,
    users: int = 2,
    hq_users: int | None = None,
    media: str = "ethernet",
    routing: str = "static",
    address_space: str = "10.40.0.0/16",
    chain: bool = True,
) -> dict[str, Any]:
    """Return an intent without services: HQ servers, branch users, WAN links.

    `chain` links HQ-BR1-BR2-...; otherwise every branch hangs off HQ.
    """
    hq = _site("HQ", "hq", users if hq_users is None else hq_users, servers=True)
    branches = [_site(f"BR{index}", "branch", users) for index in range(1, sites)]
    if chain and branches:
        hq["uplinks"] = [{"target_site_id": "br1", "media": media}]
        for index in range(1, len(branches)):
            branches[index - 1]["uplinks"] = [
                {"target_site_id": f"br{index + 1}", "media": media}
            ]
    elif branches:
        hq["uplinks"] = [
            {"target_site_id": f"br{index}", "media": media}
            for index in range(1, sites)
        ]
    payload: dict[str, Any] = {
        "name": "SP1-ROUTED",
        "address_space": address_space,
        "internet_required": True,
        "sites": [hq, *branches],
    }
    if routing:
        payload["routing_preference"] = routing
    return payload


def deployed(payload: dict[str, Any]):
    """Compose to E4 and derive the inventory a deployment would expose."""
    intent = EnterpriseIntent.model_validate_json(json.dumps(payload))
    composed = compose_enterprise_reference(
        intent, packet_tracer_version=BACKEND_VERSION
    )
    assert composed.topology is not None, composed.issues
    inventory = [
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=sorted(
                {
                    port
                    for link in composed.topology.links
                    for endpoint_id, port in (
                        (link.device_a_id, link.port_a),
                        (link.device_b_id, link.port_b),
                    )
                    if endpoint_id == device.id
                }
            ),
        )
        for device in composed.topology.devices
    ]
    return composed.topology, inventory


@dataclass(frozen=True)
class RoutedPlans:
    """One composed routed deployment, as the product would see it."""

    payload: dict[str, Any]
    manifest: DeploymentManifest
    inventory: list[RuntimeConfigurationTarget]
    composition: Any

    @property
    def configuration(self):
        """Return the compiled E5 plan."""
        return self.composition.configuration

    @property
    def services(self):
        """Return the compiled E6 plan."""
        return self.composition.services

    def names(self) -> dict[str, str]:
        """Map semantic device ids to deployed names."""
        return {item.id: item.name for item in self.composition.topology.devices}

    def ids(self) -> dict[str, str]:
        """Map deployed names to semantic device ids."""
        return {name: key for key, name in self.names().items()}

    def endpoint(self, device_name: str):
        """Return the static E5 addressing action of one endpoint."""
        return next(
            action
            for action in self.configuration.actions
            if action.action_type.value == "set_endpoint_static"
            and action.device_name == device_name
        )


def compose(payload: dict[str, Any], *, services: bool = True) -> RoutedPlans:
    """Compose, compile and bind one routed deployment exactly as the product."""
    topology, inventory = deployed(payload)
    manifest = build_deployment_manifest(
        topology,
        inventory,
        fingerprint=FINGERPRINT,
        deployment_id=DEPLOYMENT_ID,
    )
    composition = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(json.dumps(payload)),
        packet_tracer_version=BACKEND_VERSION,
        deployment_manifest=manifest,
        services=services,
    )
    assert composition.configuration is not None, composition.issues
    return RoutedPlans(payload, manifest, inventory, composition)


def with_services(
    payload: dict[str, Any],
    plans: RoutedPlans,
    *,
    clients: list[str] | None = None,
    marker: str = MARKER,
    hostname: str = HOSTNAME,
    dns: bool = True,
) -> dict[str, Any]:
    """Add HQ DNS and HTTP services whose addresses are the E5-assigned ones.

    `clients` are deployed names; the default selects every user PC of every
    site, which is what a routed enterprise workload asks for.
    """
    ids = plans.ids()
    web = plans.endpoint("HQ-DEFAULT-WEB-01").ipv4
    dns_address = plans.endpoint("HQ-DEFAULT-DNS-01").ipv4
    selected = clients or sorted(name for name in ids if "-PC-" in name)
    client_ids = [ids[name] for name in selected]
    services: list[dict[str, Any]] = [
        {
            "name": "sp1-web",
            "service_type": "http",
            "host_device_id": ids["HQ-DEFAULT-WEB-01"],
            "address": web,
            "hostname": hostname if dns else "",
            "http_content": marker,
            "client_device_ids": client_ids,
        }
    ]
    if dns:
        services.insert(
            0,
            {
                "name": "sp1-dns",
                "service_type": "dns",
                "host_device_id": ids["HQ-DEFAULT-DNS-01"],
                "address": dns_address,
                "dns_records": [{"hostname": hostname, "address": web}],
                "client_device_ids": client_ids,
            },
        )
    updated = json.loads(json.dumps(payload))
    updated["sites"][0]["services"] = services
    return updated


def routed_workload(**kwargs: Any) -> tuple[dict[str, Any], RoutedPlans]:
    """Return a DNS+HTTP routed intent and its composed plans."""
    base = topology_payload(**kwargs)
    first = compose(base, services=False)
    payload = with_services(base, first)
    return payload, compose(payload)
