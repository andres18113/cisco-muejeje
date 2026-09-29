"""One Server-PT serving a local segment natively and remote segments by relay.

The server sits on the HQ data segment, so HQ clients are local and every
branch segment is remote. Capability records built here are test inputs that
shape admission; they are not catalog entries and prove no native support.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from sp1_routed_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    RoutedPlans,
    deployed,
    topology_payload,
)

from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration import AddressRange
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    build_deployment_manifest,
)
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    CapabilityProvenance,
    ClientOperationCapability,
    NativeDhcpPolicyScope,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)

RELAY_BINDING_KEY = "Server-PT:dhcp_relay_named_pool_binding"
NATIVE_BINDING_KEY = "Server-PT:dhcp_native_default_binding"
HQ_SUBNET = "10.40.1.0/24"
HQ_GATEWAY = "10.40.1.1"
HQ_SERVER = "10.40.1.10"


def mixed_topology(
    *, sites: int = 3, users: int = 2, hq_users: int | None = None
) -> dict[str, Any]:
    """Return an intent whose DHCP server shares the HQ client segment."""
    hq_users = users if hq_users is None else hq_users
    payload = topology_payload(sites=sites, users=users, hq_users=hq_users)
    hq = payload["sites"][0]
    hq["address_block"] = "10.40.0.0/23"
    hq["segments"] = [
        {
            "role": "data",
            "hosts": hq_users + 2,
            "dhcp": True,
            "subnet": HQ_SUBNET,
            "gateway": HQ_GATEWAY,
        }
    ]
    hq["endpoints"][1]["segment_role"] = "data"
    hq["endpoints"][1]["metadata"] = {"ipv4": HQ_SERVER}
    for site in payload["sites"]:
        site["endpoints"][0]["addressing_preference"] = "dhcp"
    return payload


def _records_with(*, native: bool, relay: bool):
    records = dict(packet_tracer_service_capabilities(BACKEND_VERSION))
    common = dict(
        model="Server-PT",
        support=CapabilityStatus.SUPPORTED,
        provenance=CapabilityProvenance.RECORDED_RUN,
        source="test input: shapes admission, proves no native support",
        packet_tracer_version=BACKEND_VERSION,
        build=BACKEND_VERSION,
        executed_sha="0" * 40,
        transport="file",
        run_id="test-run",
    )
    if native:
        records[NATIVE_BINDING_KEY] = ClientOperationCapability(
            key=NATIVE_BINDING_KEY,
            operation="dhcp_native_default_binding",
            native_policy_scope=NativeDhcpPolicyScope(
                network="10.40.1.0",
                netmask="255.255.255.0",
                server_address=HQ_SERVER,
                gateway=HQ_GATEWAY,
                dns_server=HQ_SERVER,
                first_lease="10.40.1.100",
                latest_start="10.40.1.100",
                last_lease="10.40.1.101",
                max_users=2,
                max_exclusion_ranges=2,
                excluded_ranges=[
                    AddressRange(start=HQ_GATEWAY, end=HQ_GATEWAY),
                    AddressRange(start=HQ_SERVER, end=HQ_SERVER),
                ],
            ),
            **common,
        )
    if relay:
        records[RELAY_BINDING_KEY] = ClientOperationCapability(
            key=RELAY_BINDING_KEY,
            operation="dhcp_relay_named_pool_binding",
            **common,
        )
    return records


def mixed_records(*, native: bool = True, relay: bool = True):
    """Return default records plus test-only native and relay bindings."""
    return _records_with(native=native, relay=relay)


def compose_mixed(payload: dict[str, Any], records=None) -> RoutedPlans:
    """Compose one deployment with explicit service capability records."""
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
        services=True,
        service_capabilities=records,
    )
    assert composition.configuration is not None, composition.issues
    return RoutedPlans(payload, manifest, inventory, composition)


def mixed_dhcp_payload(
    *,
    sites: int = 3,
    users: int = 2,
    hq_users: int | None = None,
    pool_names: dict[str, str] | None = None,
    optional: set[str] = frozenset(),
) -> tuple[dict[str, Any], dict[str, str]]:
    """Add one state-only DHCP service per site, all on the HQ Server-PT."""
    hq_users = users if hq_users is None else hq_users
    base = mixed_topology(sites=sites, users=users, hq_users=hq_users)
    first = compose_mixed(base, mixed_records())
    ids = first.ids()
    server = "HQ-DEFAULT-DNS-01"
    resolver = first.endpoint(server).ipv4
    payload = copy.deepcopy(base)
    for index, site in enumerate(payload["sites"]):
        prefix = "HQ" if index == 0 else f"BR{index}"
        segment = f"{prefix.lower()}-data"
        pool: dict[str, Any] = {"dns_server": resolver}
        if index == 0:
            pool.update({"interface": "FastEthernet0", "start_offset": 99})
        if pool_names and segment in pool_names:
            pool["pool_name"] = pool_names[segment]
        site["services"] = [
            {
                "name": f"{prefix.lower()}-dhcp",
                "service_type": "dhcp",
                "host_device_id": ids[server],
                "segment_id": segment,
                "client_device_ids": [
                    ids[name]
                    for name in sorted(ids)
                    if name.startswith(f"{prefix}-DEFAULT-PC-")
                ],
                "verification_mode": "state_only",
                "required": segment not in optional,
                "dhcp_pool": pool,
            }
        ]
    return payload, ids
