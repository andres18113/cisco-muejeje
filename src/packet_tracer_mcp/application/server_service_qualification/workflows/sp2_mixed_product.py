"""SP-2: local native and relayed named pools through the product, privately."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from ....domain.enterprise.models.configuration import (
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ....domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ....domain.enterprise.models.deployment import deployment_manifest_semantic_hash
from ....domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
)
from ....domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServiceVerificationKind,
)
from ....domain.enterprise.models.service_qualification import (
    SP2_CANDIDATE_LABEL,
    SP2_CAPACITY_SITE_CLIENTS,
    SP2_MIXED_SERVER,
    SP2_MIXED_SITE_CLIENTS,
    MeasurementConclusion,
    QualificationStage,
    sp2_mixed_intent,
    sp2_mixed_run_parameters,
    sp2_mixed_service_candidates,
)
from ....domain.enterprise.models.service_run_record import SourceTreeIdentity
from ....domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)
from ....domain.enterprise.services.dhcp_lease_evidence import (
    client_readings,
    normalized_mac,
    scans_by_pool,
    unobserved_scans,
)
from ....domain.enterprise.services.qualification_terminal_evidence import (
    sp2_mixed_bindings_usable,
    sp2_mixed_scan_complete,
    sp2_mixed_server_complete,
    terminal_router_rows_complete,
)
from ....domain.enterprise.services.service_compiler import ServiceCompiler
from ....domain.enterprise.services.service_qualification_evidence import Assessment
from ....domain.enterprise.services.topology_identity import compute_topology_hashes
from ...use_cases.apply_enterprise_services import (
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from ..contracts import Q3ProductContract
from ..execution import Execution
from ..fixtures import diagnostic_start
from ..product_support import (
    SP1_CAPTURE_DEADLINE_SECONDS,
    SP1_CAPTURE_SAMPLE_CALLS,
    ExactInventoryServiceRuntime,
    RoutedInventoryConfigurationRuntime,
    capability_digest,
)

SP2_MIXED_TOPOLOGY_SHA256 = (
    "2aa800ab75dbdb4a614f30bb3a8cb4afbdf50bbb73c74e47bd636cb024d7134b"
)
SP2_MIXED_CONFIGURATION_SHA256 = (
    "2e2ef33e9e7d4305b5de2c45b0f71de1c6f8389c90fa2f3df8b62468ee175180"
)
SP2_MIXED_MANIFEST_SHA256 = (
    "569ad187ae834e982c3d76a94ed469708fc277a923f03a2dedfca97a9d492c2d"
)
SP2_MIXED_SERVICE_CAPABILITIES_SHA256 = (
    "d358fda37317120011783b2b78dc8c7ac332d18d4e67e1c1650775a05b255b12"
)
SP2_MIXED_BUILD = "9.0.1.0858"
SP2_MIXED_NORMALIZED_SERVICES_SHA256 = (
    "6e978c7eecaee52becfddcaf94a3f90ee5eeed7193cd176e91198c181e916d7a"
)
SP2_CAPACITY_TOPOLOGY_SHA256 = (
    "ef36487fe87642d286c8d11ba4beb35536c2c1edd8438f1b61368bf4bac69b34"
)
SP2_CAPACITY_CONFIGURATION_SHA256 = (
    "7ccda09a418d755c49f2d14f29c54f660b74f051a7c4b8b3a2715d6223b88b96"
)
SP2_CAPACITY_MANIFEST_SHA256 = (
    "e35d69a9e846c0a37908f50114d0208f58f9e8da7b66cdbbb89d28c8fcb37143"
)
SP2_CAPACITY_SERVICE_CAPABILITIES_SHA256 = (
    "71e1945a5f0fe63428429e31e84a4047ef363af950db15e4bf07d6cbc7dca7cd"
)
SP2_CAPACITY_NORMALIZED_SERVICES_SHA256 = (
    "09feeeb4d926ba06155297ec243dcdd73b1f5ae21b0d34dc772f8f79ae17fbeb"
)
_SP2_SERVICE_ID = re.compile(r"svc/[a-z0-9-]+/[0-9a-f]{16}")
SP2_MIXED_ROUTERS = ("HQ-EDGE-RTR-01", "BR1-EDGE-RTR-01", "BR2-EDGE-RTR-01")
#: Each site's segment and the physical pool the strategy assigns to it: the
#: native pool where the server sits, the segment's named pool elsewhere.
SP2_MIXED_PHYSICAL_POOLS = {
    "hq-data": "serverPool",
    "br1-data": "BR1_DATA",
    "br2-data": "BR2_DATA",
}
#: Every relayed segment's helper: the branch gateway interface the product
#: designed, pointed at the Server-PT.
SP2_MIXED_HELPERS = {
    ("BR1-EDGE-RTR-01", "GigabitEthernet0/2", "br1-data"),
    ("BR2-EDGE-RTR-01", "GigabitEthernet0/1", "br2-data"),
}
#: The client checks every selected client must verify.
SP2_MIXED_CLIENT_KINDS = (
    ServiceVerificationKind.DHCP_LEASE,
    ServiceVerificationKind.CLIENT_GATEWAY,
    ServiceVerificationKind.CLIENT_DNS_SERVER,
    ServiceVerificationKind.HTTP_FETCH,
    ServiceVerificationKind.DNS_RESOLUTION,
    ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
    ServiceVerificationKind.HTTP_BY_HOSTNAME,
)
#: The routed pairs every product phase must admit: each branch segment to
#: the server's segment, before the lease and again for the services.
SP2_MIXED_ROUTED_PAIRS = {("br1-data", "hq-data"), ("br2-data", "hq-data")}


def sp2_mixed_normalized_services_hash(
    contract: Q3ProductContract, run_id: str, *, capacity: bool = False
) -> str:
    """Hash the E6 plan with only its run-derived values abstracted.

    The run's page marker, its digest and host name become placeholders and
    every derived action identity its order of first appearance, so every
    other action and expectation value is bound to the reviewed plan.
    """
    parameters = sp2_mixed_run_parameters(run_id, capacity=capacity)
    plan = contract.service_plan.model_dump(mode="json")
    plan.pop("semantic_hash", None)
    text = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    text = text.replace(
        hashlib.sha256(parameters.marker.encode("utf-8")).hexdigest(), "@MARKER_SHA@"
    )
    text = text.replace(parameters.marker, "@MARKER@").replace(
        parameters.hostname, "@HOSTNAME@"
    )
    order: dict[str, str] = {}
    for match in _SP2_SERVICE_ID.findall(text):
        order.setdefault(match, f"@ID{len(order)}@")
    text = _SP2_SERVICE_ID.sub(lambda item: order[item.group(0)], text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sp2_mixed_device_evidence() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "build": SP2_MIXED_BUILD,
            "model": model,
            "capability": "supports_dhcp_relay",
            "status": "supported",
            "source": "static_override",
            "source_detail": f"candidate:{SP2_CANDIDATE_LABEL}",
            "confidence": "candidate",
            "verified": False,
        }
        for model in ("1941", "2911")
    )


def _sp2_mixed_contract_mismatch(
    execution: Execution, contract: Q3ProductContract
) -> str:
    """Name why a composed mixed contract is not this stage's exact run."""
    definition = execution.definition
    capacity = definition.stage is QualificationStage.SP2_CAPACITY_PRODUCT
    topology_hash = (
        SP2_CAPACITY_TOPOLOGY_SHA256 if capacity else SP2_MIXED_TOPOLOGY_SHA256
    )
    manifest_hash = (
        SP2_CAPACITY_MANIFEST_SHA256 if capacity else SP2_MIXED_MANIFEST_SHA256
    )
    configuration_hash = (
        SP2_CAPACITY_CONFIGURATION_SHA256
        if capacity
        else SP2_MIXED_CONFIGURATION_SHA256
    )
    service_hash = (
        SP2_CAPACITY_NORMALIZED_SERVICES_SHA256
        if capacity
        else SP2_MIXED_NORMALIZED_SERVICES_SHA256
    )
    capability_hash = (
        SP2_CAPACITY_SERVICE_CAPABILITIES_SHA256
        if capacity
        else SP2_MIXED_SERVICE_CAPABILITIES_SHA256
    )
    if (
        contract.topology.physical_topology_hash != topology_hash
        or compute_topology_hashes(contract.topology).physical_topology_hash
        != topology_hash
        or contract.manifest.physical_topology_hash != topology_hash
    ):
        return "sp2_mixed_topology_hash_changed"
    if (
        contract.manifest.semantic_hash != manifest_hash
        or deployment_manifest_semantic_hash(contract.manifest) != manifest_hash
    ):
        return "sp2_mixed_manifest_hash_changed"
    if (
        contract.configuration_plan.semantic_hash != configuration_hash
        or configuration_plan_semantic_hash(contract.configuration_plan)
        != configuration_hash
        or contract.configuration_plan.source_topology_hash != topology_hash
        or contract.service_plan.source_configuration_hash != configuration_hash
        or ServiceCompiler._semantic_hash(contract.service_plan)
        != contract.service_plan.semantic_hash
    ):
        return "sp2_mixed_plan_hash_changed"
    if (
        sp2_mixed_normalized_services_hash(
            contract, execution.record.run_id, capacity=capacity
        )
        != service_hash
    ):
        return "sp2_mixed_service_plan_changed"
    if contract.manifest.deployment_id != f"qualification/{execution.record.run_id}":
        return "sp2_mixed_deployment_id_changed"
    if (
        contract.manifest.backend != "packet_tracer"
        or contract.manifest.backend_version != SP2_MIXED_BUILD
        or contract.manifest.environment_fingerprint.backend != "packet_tracer"
        or contract.manifest.environment_fingerprint.backend_version != SP2_MIXED_BUILD
    ):
        return "sp2_mixed_build_or_backend_changed"
    if {(item.name, item.model) for item in contract.topology.devices} != {
        (item.name, item.model) for item in definition.fixtures
    }:
        return "sp2_mixed_device_fixture_changed"
    if {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in contract.topology.links
    } != {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in definition.links
    }:
        return "sp2_mixed_link_fixture_changed"
    ports: dict[str, set[str]] = {
        item.name: set() for item in contract.topology.devices
    }
    for link in contract.topology.links:
        ports[link.device_a].add(link.port_a)
        ports[link.device_b].add(link.port_b)
    if {
        (item.device_name, item.model, tuple(item.interfaces))
        for item in contract.inventory
    } != {
        (item.name, item.model, tuple(sorted(ports[item.name])))
        for item in definition.fixtures
    }:
        return "sp2_mixed_inventory_changed"

    # The candidates: exactly the two private service records over one
    # pinned catalog, and relay evidence for exactly the branch routers.
    try:
        candidates = sp2_mixed_service_candidates(SP2_MIXED_BUILD, capacity=capacity)
        if (
            any(
                contract.service_capabilities.get(key) != value
                for key, value in candidates.items()
            )
            or capability_digest(contract.service_capabilities) != capability_hash
        ):
            return "sp2_mixed_service_candidates_changed"
        catalog = contract.device_capability_catalog
        if (
            catalog is None
            or contract.device_capability_evidence != _sp2_mixed_device_evidence()
            or set(contract.device_capabilities)
            != {item.model for item in definition.fixtures}
            or any(
                catalog.capabilities_for(model, SP2_MIXED_BUILD)
                != contract.device_capabilities[model]
                for model in contract.device_capabilities
            )
        ):
            return "sp2_mixed_device_candidates_changed"
        for model in ("1941", "2911"):
            capability = contract.device_capabilities[model]
            if capability.supports_dhcp_relay.value != "supported" or not any(
                row.capability == "supports_dhcp_relay"
                and row.status.value == "supported"
                and row.source_detail == f"candidate:{SP2_CANDIDATE_LABEL}"
                and row.packet_tracer_version == SP2_MIXED_BUILD
                and row.verified is False
                and row.confidence == "candidate"
                for row in capability.evidence
            ):
                return "sp2_mixed_device_candidates_changed"
    except (AttributeError, KeyError, TypeError, ValueError):
        return "sp2_mixed_capability_snapshot_unreadable"

    # The intent is what the product recomposes from, so it must be the one
    # canonical form this run derives, byte for byte after normalization.
    ids = {item.name: item.id for item in contract.topology.devices}
    addresses = {
        item.device_name: item.ipv4
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointStaticAddress)
    }
    parameters = sp2_mixed_run_parameters(execution.record.run_id, capacity=capacity)
    try:
        canonical = sp2_mixed_intent(
            parameters.hostname,
            parameters.marker,
            server_id=ids[SP2_MIXED_SERVER],
            server_address=addresses[SP2_MIXED_SERVER],
            client_ids={
                site: [ids[name] for name in names]
                for site, names in (
                    SP2_CAPACITY_SITE_CLIENTS if capacity else SP2_MIXED_SITE_CLIENTS
                ).items()
            },
            capacity=capacity,
        )
        if json.loads(contract.intent_json) != canonical:
            return "sp2_mixed_intent_values_differ_from_run"
    except (KeyError, TypeError, ValueError):
        return "sp2_mixed_intent_unreadable"

    relays = {
        (item.device_name, item.interface, item.segment_id)
        for item in contract.configuration_plan.actions
        if item.action_type.value == "configure_dhcp_relay"
        and item.server_address == addresses[SP2_MIXED_SERVER]
    }
    relay_count = sum(
        item.action_type.value == "configure_dhcp_relay"
        for item in contract.configuration_plan.actions
    )
    if relays != SP2_MIXED_HELPERS or relay_count != len(SP2_MIXED_HELPERS):
        return "sp2_mixed_helpers_changed"
    pools = {
        item.segment_id: item.effective_pool_name
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    pool_count = sum(
        isinstance(item, ConfigureServerDhcpPool)
        for item in contract.service_plan.actions
    )
    if pools != SP2_MIXED_PHYSICAL_POOLS or pool_count != len(pools):
        return "sp2_mixed_pool_strategy_changed"
    clients = set(definition.selected_clients)
    required = sorted(
        (item.client_device_name, item.kind.value)
        for item in contract.service_plan.verification_expectations
        if item.kind in SP2_MIXED_CLIENT_KINDS
    )
    if {pair for pair in required} != {
        (name, kind.value) for name in clients for kind in SP2_MIXED_CLIENT_KINDS
    } or any(
        item.client_device_name and item.client_device_name not in clients
        for item in contract.service_plan.verification_expectations
    ):
        return "sp2_mixed_selected_clients_differ_from_stage"
    return ""


def _sp2_mixed_segments(contract: Q3ProductContract) -> dict[str, str]:
    """Return each selected client's planned segment from its E5 mode action."""
    return {
        item.device_name: item.segment_id
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointDhcp)
    }


def _sp2_mixed_client_facts(
    contract: Q3ProductContract, by_id: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Return every selected client's check outcomes and lease attribution."""
    segments = _sp2_mixed_segments(contract)
    facts: dict[str, dict[str, Any]] = {}
    for item in contract.service_plan.verification_expectations:
        if item.kind not in SP2_MIXED_CLIENT_KINDS or not item.client_device_name:
            continue
        observed = by_id.get(item.id)
        entry = facts.setdefault(
            item.client_device_name,
            {
                "segment": segments.get(item.client_device_name, ""),
                "intended_pool": SP2_MIXED_PHYSICAL_POOLS.get(
                    segments.get(item.client_device_name, ""), ""
                ),
                "checks": {},
            },
        )
        status = observed.status.value if observed is not None else "absent"
        checks = entry["checks"]
        # A kind planned twice must verify twice; the worst outcome is kept.
        if checks.get(item.kind.value, "verified") == "verified":
            checks[item.kind.value] = status
        if item.kind is ServiceVerificationKind.DHCP_LEASE and observed is not None:
            values = observed.observed or {}
            entry["lease"] = {
                "claim_level": observed.claim_level,
                "effective_pool_name": values.get("effective_pool_name", ""),
                "client_ipv4": values.get("client_ipv4", ""),
                "client_netmask": values.get("client_netmask", ""),
                "client_mac": values.get("client_mac", ""),
                "cause": observed.cause,
            }
    return facts


def _sp2_mixed_client_accepted(entry: Mapping[str, Any]) -> bool:
    lease = entry.get("lease") or {}
    return (
        all(
            entry["checks"].get(kind.value) == ActionExecutionStatus.VERIFIED.value
            for kind in SP2_MIXED_CLIENT_KINDS
        )
        and lease.get("claim_level") == "attributed_to_effective_server_pool"
        and bool(entry.get("intended_pool"))
        and lease.get("effective_pool_name") == entry["intended_pool"]
    )


def run_sp2_mixed_product(execution: Execution) -> None:
    """Run the mixed DHCP, DNS and HTTP intent through the product, privately."""
    contract = execution.product_contract
    boundaries = execution.run.boundaries
    definition = execution.definition
    capacity = definition.stage is QualificationStage.SP2_CAPACITY_PRODUCT
    label = "CAPACITY" if capacity else "MIXED"
    product_id = f"M-SP2-{label}-PRODUCT"
    final_id = f"M-SP2-{label}-FINAL"
    product_procedure = f"SP2_{label}_PRODUCT"
    final_procedure = f"SP2_{label}_FINAL"
    if contract is None:
        execution.stop("sp2_mixed_contract_absent")
        return
    mismatch = _sp2_mixed_contract_mismatch(execution, contract)
    if mismatch:
        execution.stop(mismatch)
        return
    clients = definition.selected_clients
    pools = tuple(sorted(set(SP2_MIXED_PHYSICAL_POOLS.values())))
    pool_actions = {
        item.segment_id: item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    windows = {
        item.effective_pool_name: item.max_users + 2 for item in pool_actions.values()
    }
    client_pools = {
        name: pool_actions[segment]
        for name, segment in _sp2_mixed_segments(contract).items()
        if segment in pool_actions
    }

    def terminal() -> None:
        ids = (final_id,)
        if not execution.begin_terminal(ids, final_procedure):
            return
        with execution.procedure(ids):
            reader = boundaries.native_product_runtimes(
                execution.bound, contract.inventory
            ).configuration
            capture = getattr(reader, "capture_routed_text", None)
            with execution.ledger.purpose_of(f"sp2:{label.lower()}:final:routers"):
                routers = (
                    list(
                        capture(
                            SP2_MIXED_ROUTERS,
                            sample_calls=SP1_CAPTURE_SAMPLE_CALLS,
                            deadline_seconds=SP1_CAPTURE_DEADLINE_SECONDS,
                        )
                    )
                    if callable(capture)
                    else []
                )
            with execution.ledger.purpose_of(f"sp2:{label.lower()}:final:clients"):
                binding_read = execution.probes.read_client_bindings(clients)
            bindings = (
                binding_read.payload.get("clients")
                if binding_read.observed and isinstance(binding_read.payload, dict)
                else None
            )
            with execution.ledger.purpose_of(f"sp2:{label.lower()}:final:client-macs"):
                client_read = execution.probes.read_dhcp_clients(
                    tuple((name, "FastEthernet0") for name in clients)
                )
            readings = (
                client_readings(client_read.payload, clients)
                if client_read.observed and isinstance(client_read.payload, Mapping)
                else {}
            )
            with execution.ledger.purpose_of(f"sp2:{label.lower()}:final:server"):
                server_read = execution.probes.read_dhcp_server_baseline(
                    SP2_MIXED_SERVER, "FastEthernet0"
                )
            with execution.ledger.purpose_of(f"sp2:{label.lower()}:final:leases"):
                lease_read = execution.probes.read_dhcp_lease_calibration(
                    SP2_MIXED_SERVER,
                    "FastEthernet0",
                    tuple((name, windows.get(name, 1)) for name in pools),
                )
            scans = (
                scans_by_pool(lease_read.payload, pools)
                if lease_read.observed and isinstance(lease_read.payload, Mapping)
                else unobserved_scans(pools, lease_read.cause)
            )
            server = server_read.payload if server_read.observed else None
            complete = (
                terminal_router_rows_complete(routers, SP2_MIXED_ROUTERS)
                and set(client_pools) == set(clients)
                and sp2_mixed_bindings_usable(bindings, client_pools)
                and set(readings) == set(clients)
                and all(
                    readings[str(row.get("device"))].observed
                    and readings[str(row.get("device"))].mode is True
                    and readings[str(row.get("device"))].ipv4 == row.get("ipv4")
                    for row in bindings
                )
                and sp2_mixed_server_complete(server, pools)
                and set(scans) == set(pools)
                and all(
                    sp2_mixed_scan_complete(
                        scans[name],
                        [
                            (
                                readings[client].ipv4,
                                normalized_mac(readings[client].mac),
                            )
                            for client, pool in client_pools.items()
                            if pool.effective_pool_name == name
                        ],
                    )
                    for name in pools
                )
            )
            execution.conclude(
                final_id,
                Assessment(
                    MeasurementConclusion.SUPPORTED_IN_SAMPLE
                    if complete
                    else MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "routers": routers,
                        "router_capture_available": callable(capture),
                        "client_bindings": bindings,
                        "client_binding_read": binding_read.cause
                        if not binding_read.observed
                        else "observed",
                        "client_readings": {
                            name: {
                                key: value
                                for key, value in item.__dict__.items()
                                if key != "raw_rows"
                            }
                            for name, item in readings.items()
                        },
                        "server": dict(server) if isinstance(server, Mapping) else {},
                        "server_read": server_read.cause
                        if not server_read.observed
                        else "observed",
                        "scans": {
                            name: item.as_facts() for name, item in scans.items()
                        },
                        "complete": complete,
                    },
                    causes=[] if complete else ["sp2_mixed_final_inventory_incomplete"],
                    limitations=[
                        "terminal_inventory_is_not_product_acceptance",
                        "positive_row_does_not_establish_table_end",
                    ],
                ),
            )
        execution.finish(final_procedure)

    execution.register_terminal((final_id,), final_procedure, terminal)
    if not diagnostic_start(execution):
        return
    ids = (product_id,)
    if not execution.selected(f"SP2-{label.lower()}") or not execution.begin(
        ids, product_procedure
    ):
        return
    accepted = False
    product_operations = execution.definition.experiment(ids[0]).planned_operations
    with (
        execution.ledger.ordinary_limit(
            operations=product_operations, leave_seconds=240
        ),
        execution.procedure(ids),
    ):
        with execution.ledger.purpose_of(f"sp2:{label.lower()}:build"):
            build = boundaries.build_reader(execution.bound.send_and_wait).read()
        observed_build = execution.record.environment.observed_build
        if not build.available or build.version != observed_build:
            execution.conclude(
                product_id,
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={"fresh_build": build.version if build.available else ""},
                    causes=["sp2_mixed_build_unobserved_or_mismatched"],
                ),
            )
            execution.finish(product_procedure)
            execution.stop("sp2_mixed_build_unobserved_or_mismatched")
            return
        if not execution.run.transition(f"experiment:{product_procedure}:started"):
            execution.stop("persistence:sp2_mixed_product_not_announced")
            return

        class ExactManifest:
            def latest_by_deployment_id(self, identifier: str):
                return (
                    contract.manifest
                    if identifier == contract.manifest.deployment_id
                    else None
                )

        inner = boundaries.native_product_runtimes(execution.bound, contract.inventory)
        product_runtimes = ServiceStageRuntimes(
            configuration=RoutedInventoryConfigurationRuntime(
                inner.configuration, contract.inventory
            ),
            services=ExactInventoryServiceRuntime(inner.services, contract.inventory),
        )
        with execution.ledger.effect_of(
            f"sp2:{label.lower()}:apply-enterprise-services"
        ):
            product = apply_enterprise_services(
                contract.intent_json,
                deployment_id=contract.manifest.deployment_id,
                packet_tracer_version=observed_build,
                import_preflight=boundaries.native_product_import_preflight(),
                manifest_store=ExactManifest(),
                runtimes=product_runtimes,
                record_store=boundaries.native_product_record_store_factory(),
                environment_fingerprint=contract.manifest.environment_fingerprint,
                transport_selection=TransportSelection(
                    channel=execution.channel, fixed_at=boundaries.now()
                ),
                endpoint_observer=boundaries.native_product_endpoint_observer(
                    execution.bound
                ),
                capability_catalog=lambda version: (
                    contract.service_capabilities if version == observed_build else {}
                ),
                device_capability_catalog=contract.device_capability_catalog,
                source_tree=SourceTreeIdentity(
                    sha=execution.record.source.executed_sha,
                    tree=execution.record.source.executed_tree,
                    dirty=execution.record.source.clean is not True,
                ),
                run_label=f"{SP2_CANDIDATE_LABEL} {definition.stage.value}",
                run_id=execution.record.run_id + "-product",
            )
        by_id = (
            {
                item.expectation_id: item
                for item in product.service_result.verification_results
            }
            if product.service_result is not None
            else {}
        )
        client_facts = _sp2_mixed_client_facts(contract, by_id)
        server_ids = [
            item.id
            for item in contract.service_plan.verification_expectations
            if item.kind is ServiceVerificationKind.DHCP_SERVER_STATE
        ]
        server_states = {
            identifier: (
                by_id[identifier].status.value if identifier in by_id else "absent"
            )
            for identifier in server_ids
        }
        routed = [
            row
            for row in product.operational_readiness
            if row.get("kind") == "routed_forwarding"
        ]
        prelease = [
            (row.get("client_segment_id"), row.get("host_segment_id"))
            for row in routed
            if row.get("phase") == "dhcp_prelease"
        ]
        services = [
            (row.get("client_segment_id"), row.get("host_segment_id"))
            for row in routed
            if row.get("phase") != "dhcp_prelease"
        ]
        injected = "device_capability_catalog:injected" in product.limitations
        accepted = (
            product.refusal_code is ServiceEntryRefusal.NONE
            and product.status is ServiceRunStatus.VERIFIED
            and product.stage is ServiceStage.COMPLETED
            and product.persisted_stage is ServiceStage.COMPLETED
            and bool(product.record_path)
            and not product.persist_error
            and injected
            and set(client_facts) == set(clients)
            and all(_sp2_mixed_client_accepted(item) for item in client_facts.values())
            and len(server_ids) == len(SP2_MIXED_PHYSICAL_POOLS)
            and all(value == "verified" for value in server_states.values())
            and len(prelease) == len(set(prelease))
            and set(prelease) == SP2_MIXED_ROUTED_PAIRS
            and len(services) == len(set(services))
            and set(services) == SP2_MIXED_ROUTED_PAIRS
            and all(row.get("status") == "admitted" for row in routed)
            and not any(
                row.get("kind") == "routed_revocations"
                for row in product.operational_readiness
            )
        )
        execution.conclude(
            product_id,
            Assessment(
                MeasurementConclusion.SUPPORTED_IN_SAMPLE
                if accepted
                else MeasurementConclusion.INCONCLUSIVE,
                facts={
                    "product_summary": product.compact_summary(),
                    "product_record_path": product.record_path,
                    "entry_surface": "private_candidate",
                    "fresh_build": build.version,
                    "selected_clients": list(clients),
                    "clients": client_facts,
                    "server_states": server_states,
                    "routed_groups": [
                        {
                            "phase": row.get("phase", ""),
                            "client_segment_id": row.get("client_segment_id"),
                            "host_segment_id": row.get("host_segment_id"),
                            "status": row.get("status"),
                            "device_ids": row.get("device_ids"),
                        }
                        for row in routed
                    ],
                    "readiness_statuses": sorted(
                        {
                            str(row.get("status"))
                            for row in product.operational_readiness
                        }
                    ),
                    "service_candidate_keys": sorted(
                        sp2_mixed_service_candidates(SP2_MIXED_BUILD, capacity=capacity)
                    ),
                    "service_capabilities_sha256": capability_digest(
                        contract.service_capabilities
                    ),
                    "device_candidate_evidence": list(
                        contract.device_capability_evidence
                    ),
                    "product_device_catalog_injected": injected,
                },
                causes=[]
                if accepted
                else [f"sp2_mixed_product_not_verified:{product.refusal_code.value}"],
                limitations=[
                    "private_candidate_capabilities_not_global_product_promotion",
                    "relay_packet_giaddr_not_observed",
                    "positive_row_does_not_establish_table_end",
                ],
            ),
        )
    execution.finish(product_procedure)
    if not accepted:
        execution.stop("sp2_mixed_product_not_verified")
