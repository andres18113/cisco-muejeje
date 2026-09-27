"""The SP-1 routed DNS/HTTP qualification contract, composed by the product.

Translation and composition only. Every plan in the contract is what the
product's own designer and compilers produce from the SP-1 intent; this module
chooses the intent, the run's address space, page marker and host name, and
the device evidence the run is composed with. The stage coordinator decides
whether the composed topology is its exact fixture.

Each run derives its address space, marker and host name from its run id, so
one run's evidence can never satisfy another's. The device catalog is the
default one for the build whenever that catalog already supports static routes
on every SP-1 router model; otherwise the run is composed with named,
unverified candidate evidence for exactly that one capability and the product
record says so.
"""

from __future__ import annotations

import json
from typing import Any

from ...application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from ...application.use_cases.plan_enterprise_hardware import capability_catalog_for
from ...application.use_cases.qualify_server_services import Q3ProductContract
from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.configuration import SetEndpointStaticAddress
from ...domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from ...domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.service_qualification import (
    SP1_DNS_SERVER,
    SP1_WEB_SERVER,
    Sp1RunParameters,
    sp1_run_parameters,
)

__all__ = ["Sp1RunParameters", "sp1_run_parameters"]
from ...infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
    candidate_capability_adapter,
)

#: The router models the SP-1 fixture composes, and the one capability the
#: routed plan needs from them that the catalog may not yet support.
SP1_ROUTER_MODELS = ("1941", "2911")
SP1_STATIC_ROUTE_CAPABILITY = "supports_static_routes"
SP1_CANDIDATE_LABEL = "SERVER-PT-SP1-ROUTED-01"


def sp1_topology_intent(address_space: str) -> dict[str, Any]:
    """Return the SP-1 intent without services: three chained sites.

    HQ holds two users and separate DNS and web servers in a servers VLAN;
    each branch holds two users. `internet_required` makes the product
    LAN-attach every site router, and static routing is requested explicitly.
    """

    def users(count: int) -> dict[str, Any]:
        return {"role": "user_pc", "count": count, "addressing_preference": "static"}

    def server(role: str) -> dict[str, Any]:
        return {
            "role": role,
            "count": 1,
            "addressing_preference": "static",
            "segment_role": "servers",
        }

    return {
        "name": "SP1-ROUTED",
        "address_space": address_space,
        "internet_required": True,
        "routing_preference": "static",
        "sites": [
            {
                "name": "HQ",
                "type": "hq",
                "endpoints": [users(2), server("dns_server"), server("web_server")],
                "uplinks": [{"target_site_id": "br1", "media": "ethernet"}],
            },
            {
                "name": "BR1",
                "type": "branch",
                "endpoints": [users(2)],
                "uplinks": [{"target_site_id": "br2", "media": "ethernet"}],
            },
            {"name": "BR2", "type": "branch", "endpoints": [users(2)]},
        ],
    }


def sp1_device_candidates(build: str) -> dict[str, list[str]]:
    """Return, per SP-1 router model, the capability the default catalog lacks.

    Empty means the default catalog of `build` already supports static routes
    on every SP-1 router model.
    """
    default = capability_catalog_for(build)
    missing = [
        model
        for model in SP1_ROUTER_MODELS
        if (capabilities := default.capabilities_for(model, build)) is None
        or getattr(capabilities, SP1_STATIC_ROUTE_CAPABILITY)
        is not CapabilityStatus.SUPPORTED
    ]
    return {model: [SP1_STATIC_ROUTE_CAPABILITY] for model in missing}


def sp1_device_catalog(build: str) -> EnterpriseCapabilityAdapter | None:
    """Return candidate device evidence, or None when the default suffices.

    None means the run uses exactly what the registered tool uses. Otherwise
    the candidate names only the missing capability, unverified.
    """
    candidates = sp1_device_candidates(build)
    if not candidates:
        return None
    return candidate_capability_adapter(build, candidates, label=SP1_CANDIDATE_LABEL)


def sp1_candidate_evidence(build: str) -> tuple[dict[str, Any], ...]:
    """Return the exact entries `sp1_device_catalog` injects, for the record."""
    return tuple(
        {
            "build": build,
            "model": model,
            "capability": capability,
            "status": "supported",
            "source": "static_override",
            "source_detail": f"candidate:{SP1_CANDIDATE_LABEL}",
            "confidence": "candidate",
            "verified": False,
        }
        for model, capabilities in sorted(sp1_device_candidates(build).items())
        for capability in capabilities
    )


def _composed(intent: dict[str, Any], build: str, catalog, **kwargs: Any):
    composition = compose_enterprise_reference(
        EnterpriseIntent.model_validate(intent),
        packet_tracer_version=build,
        capability_catalog=catalog,
        **kwargs,
    )
    if composition.issues or composition.topology is None:
        raise ValueError("SP-1 composition failed: " + "; ".join(composition.issues))
    return composition


def sp1_routed_product_contract(
    build: str, run_id: str, clients: tuple[str, ...]
) -> Q3ProductContract:
    """Compose the SP-1 routed product plans for the selected client names."""
    if not clients or len(set(clients)) != len(clients):
        raise ValueError("SP-1 needs distinct selected clients.")
    candidate = sp1_device_catalog(build)
    catalog = candidate or capability_catalog_for(build)
    parameters = sp1_run_parameters(run_id)
    base = sp1_topology_intent(parameters.address_space)
    topology = _composed(base, build, catalog).topology
    ports: dict[str, set[str]] = {item.id: set() for item in topology.devices}
    for link in topology.links:
        ports[link.device_a_id].add(link.port_a)
        ports[link.device_b_id].add(link.port_b)
    inventory = tuple(
        RuntimeConfigurationTarget(
            device_name=item.name,
            model=item.model,
            interfaces=sorted(ports[item.id]),
        )
        for item in topology.devices
    )
    manifest = build_deployment_manifest(
        topology,
        list(inventory),
        fingerprint=EnvironmentFingerprint(
            backend="packet_tracer", backend_version=build
        ),
        deployment_id=f"qualification/{run_id}",
    )
    addressed = _composed(base, build, catalog, deployment_manifest=manifest)
    if addressed.configuration is None:
        raise ValueError("SP-1 composition produced no configuration plan.")
    addresses = {
        item.device_name: item.ipv4
        for item in addressed.configuration.actions
        if isinstance(item, SetEndpointStaticAddress)
    }
    ids = {item.name: item.id for item in topology.devices}
    unknown = [name for name in clients if name not in ids or "-PC-" not in name]
    if unknown or SP1_DNS_SERVER not in addresses or SP1_WEB_SERVER not in addresses:
        raise ValueError("SP-1 clients or servers are not in the composition.")
    client_ids = [ids[name] for name in clients]
    web = addresses[SP1_WEB_SERVER]
    intent = json.loads(json.dumps(base))
    intent["sites"][0]["services"] = [
        {
            "name": "sp1-dns",
            "service_type": "dns",
            "host_device_id": ids[SP1_DNS_SERVER],
            "address": addresses[SP1_DNS_SERVER],
            "dns_records": [{"hostname": parameters.hostname, "address": web}],
            "client_device_ids": client_ids,
        },
        {
            "name": "sp1-web",
            "service_type": "http",
            "host_device_id": ids[SP1_WEB_SERVER],
            "address": web,
            "hostname": parameters.hostname,
            "http_content": parameters.marker,
            "client_device_ids": client_ids,
        },
    ]
    final = _composed(
        intent, build, catalog, deployment_manifest=manifest, services=True
    )
    if (
        final.configuration is None
        or final.services is None
        or final.topology.model_dump(mode="json") != topology.model_dump(mode="json")
    ):
        raise ValueError("SP-1 service composition changed or lost the topology.")
    return Q3ProductContract(
        topology=final.topology,
        manifest=manifest,
        inventory=inventory,
        configuration_plan=final.configuration,
        service_plan=final.services,
        device_capabilities=final.capabilities,
        service_capabilities=final.service_capabilities,
        intent_json=json.dumps(intent, sort_keys=True),
        device_capability_catalog=candidate,
        device_capability_evidence=sp1_candidate_evidence(build) if candidate else (),
    )
