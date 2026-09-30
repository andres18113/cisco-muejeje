"""The SP-2 mixed DHCP, DNS and HTTP qualification contract, composed privately.

Translation and composition only. Every plan in the contract is what the
product's own designer and compilers produce from the canonical mixed intent.
This module chooses the run's marker and host name and the private candidate
evidence the run is composed with: relay support for the branch routers, a
relayed named-pool binding and a native scope for this fixture's local pool.
The default catalogs are never modified; the stage coordinator decides whether
the composed contract is its exact fixture and candidate set.
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
from ...domain.enterprise.models.service_plan import ServiceCapabilityRecords
from ...domain.enterprise.models.service_qualification import (
    SP2_CANDIDATE_LABEL,
    SP2_CAPACITY_SITE_CLIENTS,
    SP2_MIXED_SERVER,
    SP2_MIXED_SITE_CLIENTS,
    sp2_mixed_intent,
    sp2_mixed_run_parameters,
    sp2_mixed_service_candidates,
    sp2_mixed_topology_intent,
)
from ...infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
    candidate_capability_adapter,
)
from ...infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)

#: The router models the mixed fixture composes and the one capability the
#: relay plan needs from them that the default catalog does not record.
SP2_ROUTER_MODELS = ("1941", "2911")
SP2_RELAY_CAPABILITY = "supports_dhcp_relay"


def sp2_mixed_device_candidates(build: str) -> dict[str, list[str]]:
    """Return, per router model, the relay capability the default lacks."""
    default = capability_catalog_for(build)
    missing = [
        model
        for model in SP2_ROUTER_MODELS
        if (capabilities := default.capabilities_for(model, build)) is None
        or getattr(capabilities, SP2_RELAY_CAPABILITY) is not CapabilityStatus.SUPPORTED
    ]
    return {model: [SP2_RELAY_CAPABILITY] for model in missing}


def sp2_mixed_device_catalog(build: str) -> EnterpriseCapabilityAdapter | None:
    """Return candidate relay evidence, or None when the default suffices."""
    candidates = sp2_mixed_device_candidates(build)
    if not candidates:
        return None
    return candidate_capability_adapter(build, candidates, label=SP2_CANDIDATE_LABEL)


def sp2_mixed_device_evidence(build: str) -> tuple[dict[str, Any], ...]:
    """Return the exact entries `sp2_mixed_device_catalog` injects."""
    return tuple(
        {
            "build": build,
            "model": model,
            "capability": capability,
            "status": "supported",
            "source": "static_override",
            "source_detail": f"candidate:{SP2_CANDIDATE_LABEL}",
            "confidence": "candidate",
            "verified": False,
        }
        for model, capabilities in sorted(sp2_mixed_device_candidates(build).items())
        for capability in capabilities
    )


def sp2_mixed_service_capabilities(
    build: str, *, capacity: bool = False
) -> ServiceCapabilityRecords:
    """Return a private copy of the default records plus the two candidates."""
    records = dict(packet_tracer_service_capabilities(build))
    records.update(sp2_mixed_service_candidates(build, capacity=capacity))
    return records


def _composed(intent: dict[str, Any], build: str, catalog, **kwargs: Any):
    composition = compose_enterprise_reference(
        EnterpriseIntent.model_validate(intent),
        packet_tracer_version=build,
        capability_catalog=catalog,
        **kwargs,
    )
    if composition.issues or composition.topology is None:
        raise ValueError(
            "SP-2 mixed composition failed: " + "; ".join(composition.issues)
        )
    return composition


def sp2_mixed_product_contract(
    build: str, run_id: str, *, capacity: bool = False
) -> Q3ProductContract:
    """Compose the mixed product plans for one run, with private candidates."""
    if not run_id:
        raise ValueError("SP-2 mixed needs a run id.")
    catalog = sp2_mixed_device_catalog(build) or capability_catalog_for(build)
    base = sp2_mixed_topology_intent(capacity=capacity)
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
        raise ValueError("SP-2 mixed composition produced no configuration plan.")
    addresses = {
        item.device_name: item.ipv4
        for item in addressed.configuration.actions
        if isinstance(item, SetEndpointStaticAddress)
    }
    ids = {item.name: item.id for item in topology.devices}
    clients = SP2_CAPACITY_SITE_CLIENTS if capacity else SP2_MIXED_SITE_CLIENTS
    wanted = [name for names in clients.values() for name in names]
    if any(name not in ids for name in wanted) or SP2_MIXED_SERVER not in addresses:
        raise ValueError("SP-2 mixed clients or server are not in the composition.")
    parameters = sp2_mixed_run_parameters(run_id, capacity=capacity)
    intent = sp2_mixed_intent(
        parameters.hostname,
        parameters.marker,
        server_id=ids[SP2_MIXED_SERVER],
        server_address=addresses[SP2_MIXED_SERVER],
        client_ids={
            site: [ids[name] for name in names] for site, names in clients.items()
        },
        capacity=capacity,
    )
    service_capabilities = sp2_mixed_service_capabilities(build, capacity=capacity)
    final = _composed(
        intent,
        build,
        catalog,
        deployment_manifest=manifest,
        services=True,
        service_capabilities=service_capabilities,
    )
    if (
        final.configuration is None
        or final.services is None
        or final.topology.model_dump(mode="json") != topology.model_dump(mode="json")
    ):
        raise ValueError("SP-2 mixed service composition changed or lost the topology.")
    device_catalog = sp2_mixed_device_catalog(build)
    return Q3ProductContract(
        topology=final.topology,
        manifest=manifest,
        inventory=inventory,
        configuration_plan=final.configuration,
        service_plan=final.services,
        device_capabilities=final.capabilities,
        service_capabilities=final.service_capabilities,
        intent_json=json.dumps(intent, sort_keys=True),
        device_capability_catalog=device_catalog,
        device_capability_evidence=(
            sp2_mixed_device_evidence(build) if device_catalog is not None else ()
        ),
    )


def sp2_capacity_product_contract(build: str, run_id: str) -> Q3ProductContract:
    """Compose the separately scoped 36-local plus 13/5-remote hypothesis."""
    return sp2_mixed_product_contract(build, run_id, capacity=True)
