"""SP-2: local native and relayed named pools through the product, privately.

The phases are the contract binding to the reviewed plan hashes, the run's
measurement names and client-to-pool bindings, the terminal inventory, the
fresh-build check, the private product application under the ordinary limit,
and the pure acceptance assessment of the product's report.

The acquisition discriminator (`SP2-MIXED-ACQUISITION`) shares every one of
those phases. Its product's expected non-acceptance is its precondition, not
a failure, so it does not run the mixed stop policy: it reads the state the
product left and, only when that is episode 8's link-local state, applies one
typed intervention per arm client and reads one shared window. A genuine
unknown effect, a refused authority or an unreproduced precondition still
stops the run.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from ....domain.enterprise.models.capabilities import CapabilityStatus
from ....domain.enterprise.models.configuration import (
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ....domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ....domain.enterprise.models.deployment import deployment_manifest_semantic_hash
from ....domain.enterprise.models.execution import DispatchFact, ResultFact
from ....domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
    ServiceStageResult,
)
from ....domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServiceActionType,
    ServiceVerificationKind,
)
from ....domain.enterprise.models.service_qualification import (
    SP2_ACQUISITION_ARMS,
    SP2_ACQUISITION_ARMS_OPERATIONS,
    SP2_ACQUISITION_SAMPLES,
    SP2_ACQUISITION_WAIT_SECONDS,
    SP2_CANDIDATE_LABEL,
    SP2_CAPACITY_SITE_CLIENTS,
    SP2_ELIGIBLE_ACQUISITION_ARMS,
    SP2_MIXED_PRODUCT_OPERATIONS,
    SP2_MIXED_SERVER,
    SP2_MIXED_SITE_CLIENTS,
    MeasurementConclusion,
    MeasurementStatus,
    QualificationStage,
    ReleaseRecord,
    sp2_mixed_intent,
    sp2_mixed_run_parameters,
    sp2_mixed_service_candidates,
)
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
from ....domain.enterprise.services.service_compiler import service_plan_semantic_hash
from ....domain.enterprise.services.service_diagnostic_profiles import (
    sp2_acquisition_reassert_plan,
    sp2_acquisition_start_plan,
)
from ....domain.enterprise.services.service_qualification_evidence import Assessment
from ....domain.enterprise.services.sp2_acquisition_discriminator import (
    ARM_EXPLICIT_START,
    ARM_REASSERT,
    INTERVENTION_DISPATCHED,
    AcquisitionSample,
    acquisition_precondition,
    assess_acquisition_arms,
)
from ....domain.enterprise.services.sp2_eligible_acquisition import (
    EligibleCohort,
    assess_eligible_arms,
    eligible_cohort,
)
from ....domain.enterprise.services.topology_identity import compute_topology_hashes
from ...use_cases.apply_configuration import ConfigurationApplicator
from ...use_cases.apply_services import ServiceApplicator
from ..contracts import Q3ProductContract
from ..execution import Execution
from ..fixtures import diagnostic_start
from ..product_support import (
    DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
    acquisition_request_outcome,
    application_rows,
    apply_private_product,
    capability_digest,
    capture_terminal_routers,
    product_runtime_context,
    product_stage_runtimes,
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
    """Name why a composed mixed contract is not this stage's exact run.

    The checks run in order and the first cause wins: the reviewed hashes and
    build, the fixture binding, the private candidates, the canonical intent
    and the relay, pool and client strategy.
    """
    capacity = execution.definition.stage is QualificationStage.SP2_CAPACITY_PRODUCT
    return (
        _mixed_identity_mismatch(execution, contract, capacity)
        or _mixed_fixture_mismatch(execution, contract)
        or _mixed_candidate_mismatch(execution, contract, capacity)
        or _mixed_intent_mismatch(execution, contract, capacity)
        or _mixed_strategy_mismatch(execution, contract)
    )


def _mixed_identity_mismatch(
    execution: Execution, contract: Q3ProductContract, capacity: bool
) -> str:
    """Bind the contract to the reviewed topology, plan and manifest hashes."""
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
        or service_plan_semantic_hash(contract.service_plan)
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
    return ""


def _mixed_fixture_mismatch(execution: Execution, contract: Q3ProductContract) -> str:
    """Bind the contract's devices, links and inventory to the stage fixture."""
    definition = execution.definition
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

    return ""


def _mixed_candidate_mismatch(
    execution: Execution, contract: Q3ProductContract, capacity: bool
) -> str:
    """Bind the private service and relay candidates to their pinned records."""
    definition = execution.definition
    capability_hash = (
        SP2_CAPACITY_SERVICE_CAPABILITIES_SHA256
        if capacity
        else SP2_MIXED_SERVICE_CAPABILITIES_SHA256
    )
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

    return ""


def _mixed_intent_mismatch(
    execution: Execution, contract: Q3ProductContract, capacity: bool
) -> str:
    """Require the intent to be the one canonical form this run derives."""
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

    return ""


def _mixed_strategy_mismatch(execution: Execution, contract: Q3ProductContract) -> str:
    """Require the reviewed relay helpers, pool strategy and client selection."""
    definition = execution.definition
    addresses = {
        item.device_name: item.ipv4
        for item in contract.configuration_plan.actions
        if isinstance(item, SetEndpointStaticAddress)
    }
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


@dataclass(frozen=True)
class _MixedRun:
    """The measurement names and pool bindings of one mixed or capacity run."""

    label: str
    product_id: str
    final_id: str
    product_procedure: str
    final_procedure: str
    clients: tuple[str, ...]
    #: Every physical pool the strategy assigns, sorted.
    pools: tuple[str, ...]
    #: The explicit index window of each pool's final scan.
    windows: dict[str, int]
    #: Each selected client's planned pool action, by client name.
    client_pools: dict[str, ConfigureServerDhcpPool]


def run_sp2_mixed_product(execution: Execution) -> None:
    """Run the mixed DHCP, DNS and HTTP intent through the product, privately."""
    contract = execution.product_contract
    if contract is None:
        execution.stop("sp2_mixed_contract_absent")
        return
    mismatch = _sp2_mixed_contract_mismatch(execution, contract)
    if mismatch:
        execution.stop(mismatch)
        return
    run = _sp2_mixed_run(execution, contract)
    execution.register_terminal(
        (run.final_id,),
        run.final_procedure,
        lambda: _sp2_mixed_final(execution, contract, run),
    )
    if not diagnostic_start(execution):
        return
    ids = (run.product_id,)
    if not execution.selected(f"SP2-{run.label.lower()}") or not execution.begin(
        ids, run.product_procedure
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
        with execution.ledger.purpose_of(f"sp2:{run.label.lower()}:build"):
            build = execution.run.boundaries.build_reader(
                execution.bound.send_and_wait
            ).read()
        observed_build = execution.record.environment.observed_build
        if not build.available or build.version != observed_build:
            execution.conclude(
                run.product_id,
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={"fresh_build": build.version if build.available else ""},
                    causes=["sp2_mixed_build_unobserved_or_mismatched"],
                ),
            )
            execution.finish(run.product_procedure)
            execution.stop("sp2_mixed_build_unobserved_or_mismatched")
            return
        if not execution.run.transition(f"experiment:{run.product_procedure}:started"):
            execution.stop("persistence:sp2_mixed_product_not_announced")
            return
        product_runtimes = product_stage_runtimes(execution, contract, routed=True)
        with execution.ledger.effect_of(
            f"sp2:{run.label.lower()}:apply-enterprise-services"
        ):
            product = apply_private_product(
                execution,
                contract,
                product_runtimes,
                run_label=f"{SP2_CANDIDATE_LABEL} {execution.definition.stage.value}",
                bind_device_catalog=True,
            )
        assessment = _sp2_mixed_product_assessment(
            execution, contract, run, product, build.version
        )
        accepted = assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
        execution.conclude(run.product_id, assessment)
    execution.finish(run.product_procedure)
    if not accepted:
        execution.stop("sp2_mixed_product_not_verified")


def _sp2_mixed_run(execution: Execution, contract: Q3ProductContract) -> _MixedRun:
    """Name this run's measurements and bind each client to its planned pool."""
    capacity = execution.definition.stage is QualificationStage.SP2_CAPACITY_PRODUCT
    label = "CAPACITY" if capacity else "MIXED"
    pool_actions = {
        item.segment_id: item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    return _MixedRun(
        label=label,
        product_id=f"M-SP2-{label}-PRODUCT",
        final_id=f"M-SP2-{label}-FINAL",
        product_procedure=f"SP2_{label}_PRODUCT",
        final_procedure=f"SP2_{label}_FINAL",
        clients=execution.definition.selected_clients,
        pools=tuple(sorted(set(SP2_MIXED_PHYSICAL_POOLS.values()))),
        windows={
            item.effective_pool_name: item.max_users + 2
            for item in pool_actions.values()
        },
        client_pools={
            name: pool_actions[segment]
            for name, segment in _sp2_mixed_segments(contract).items()
            if segment in pool_actions
        },
    )


def _sp2_mixed_final(
    execution: Execution,
    contract: Q3ProductContract,
    run: _MixedRun,
    *,
    acceptance: bool = True,
) -> None:
    """Take the terminal router, binding, client, server and lease inventory.

    With `acceptance` the inventory supports the sample only when every
    client is usable in its pool. Without it (the acquisition discriminator,
    whose controls are meant to stay unserved) it supports only that every
    router, binding, client, server and pool was observed; the usability
    facts are kept either way.
    """
    ids = (run.final_id,)
    if not execution.begin_terminal(ids, run.final_procedure):
        return
    label = run.label.lower()
    clients = run.clients
    pools = run.pools
    client_pools = run.client_pools
    with execution.procedure(ids):
        routers, capture_available = capture_terminal_routers(
            execution, contract, SP2_MIXED_ROUTERS, f"sp2:{label}:final:routers"
        )
        with execution.ledger.purpose_of(f"sp2:{label}:final:clients"):
            binding_read = execution.probes.read_client_bindings(clients)
        bindings = (
            binding_read.payload.get("clients")
            if binding_read.observed and isinstance(binding_read.payload, dict)
            else None
        )
        with execution.ledger.purpose_of(f"sp2:{label}:final:client-macs"):
            client_read = execution.probes.read_dhcp_clients(
                tuple((name, "FastEthernet0") for name in clients)
            )
        readings = (
            client_readings(client_read.payload, clients)
            if client_read.observed and isinstance(client_read.payload, Mapping)
            else {}
        )
        with execution.ledger.purpose_of(f"sp2:{label}:final:server"):
            server_read = execution.probes.read_dhcp_server_baseline(
                SP2_MIXED_SERVER, "FastEthernet0"
            )
        with execution.ledger.purpose_of(f"sp2:{label}:final:leases"):
            lease_read = execution.probes.read_dhcp_lease_calibration(
                SP2_MIXED_SERVER,
                "FastEthernet0",
                tuple((name, run.windows.get(name, 1)) for name in pools),
            )
        scans = (
            scans_by_pool(lease_read.payload, pools)
            if lease_read.observed and isinstance(lease_read.payload, Mapping)
            else unobserved_scans(pools, lease_read.cause)
        )
        server = server_read.payload if server_read.observed else None
        usable = (
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
        complete = (
            usable
            if acceptance
            else _sp2_terminal_observed(
                routers, bindings, readings, server, scans, clients, pools
            )
        )
        execution.conclude(
            run.final_id,
            Assessment(
                MeasurementConclusion.SUPPORTED_IN_SAMPLE
                if complete
                else MeasurementConclusion.INCONCLUSIVE,
                facts={
                    "routers": routers,
                    "router_capture_available": capture_available,
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
                    "scans": {name: item.as_facts() for name, item in scans.items()},
                    "complete": complete,
                    **({} if acceptance else {"usable": usable}),
                },
                causes=[]
                if complete
                else [
                    "sp2_mixed_final_inventory_incomplete"
                    if acceptance
                    else "sp2_acquisition_final_inventory_unobserved"
                ],
                limitations=[
                    "terminal_inventory_is_not_product_acceptance",
                    "positive_row_does_not_establish_table_end",
                ],
            ),
        )
    execution.finish(run.final_procedure)


def _sp2_terminal_observed(
    routers, bindings, readings, server, scans, clients, pools
) -> bool:
    """Whether every terminal reading was observed, usable or not.

    Only the acquisition discriminator asks this; the mixed and capacity
    terminals keep their acceptance predicate. A binding row must name its
    client as text; any malformed row leaves the inventory unobserved.
    """
    devices = (
        [row.get("device") for row in bindings if isinstance(row, Mapping)]
        if isinstance(bindings, list)
        else None
    )
    return bool(
        terminal_router_rows_complete(routers, SP2_MIXED_ROUTERS)
        and devices is not None
        and len(devices) == len(bindings)
        and all(isinstance(device, str) for device in devices)
        and sorted(devices) == sorted(clients)
        and set(readings) == set(clients)
        and all(item.observed for item in readings.values())
        and isinstance(server, Mapping)
        and set(scans) == set(pools)
        and all(item.observed for item in scans.values())
    )


def _sp2_mixed_product_assessment(
    execution: Execution,
    contract: Q3ProductContract,
    run: _MixedRun,
    product: ServiceStageResult,
    fresh_build: str,
) -> Assessment:
    """Accept only a verified product whose every client and routed pair verified."""
    capacity = execution.definition.stage is QualificationStage.SP2_CAPACITY_PRODUCT
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
        and set(client_facts) == set(run.clients)
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
    return Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if accepted
        else MeasurementConclusion.INCONCLUSIVE,
        facts={
            "product_summary": product.compact_summary(),
            "product_record_path": product.record_path,
            "entry_surface": "private_candidate",
            "fresh_build": fresh_build,
            "selected_clients": list(run.clients),
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
                {str(row.get("status")) for row in product.operational_readiness}
            ),
            "service_candidate_keys": sorted(
                sp2_mixed_service_candidates(SP2_MIXED_BUILD, capacity=capacity)
            ),
            "service_capabilities_sha256": capability_digest(
                contract.service_capabilities
            ),
            "device_candidate_evidence": list(contract.device_capability_evidence),
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
    )


# -- SP-2 acquisition discriminator --------------------------------------------

ARMS_ID = "M-SP2-ACQUISITION-ARMS"
ARMS_PROCEDURE = "SP2_ACQUISITION_ARMS"
#: Ordinary seconds the product leaves for the arms window and the terminal:
#: thirteen samples of three reads each plus twelve waits, and the mixed
#: terminal's own 240 seconds.
_ARMS_SECONDS = 600.0
#: The private acquisition record the explicit-start arm alone is admitted
#: with; the composed catalog keeps it UNKNOWN for the product.
_ACQUIRE_KEY = f"PC-PT:{ServiceActionType.ACQUIRE_DHCP_LEASE.value}"


@dataclass
class _Held:
    """What the product phase hands to the arms phase, and nothing else."""

    runtimes: Any = None
    product: ServiceStageResult | None = None
    readings: dict[str, Any] = field(default_factory=dict)
    cohort: EligibleCohort | None = None


def run_sp2_mixed_acquisition(execution: Execution) -> None:
    """Reproduce the mixed product's end state, then run the arms once."""
    contract = execution.product_contract
    if contract is None:
        execution.stop("sp2_acquisition_contract_absent")
        return
    mismatch = _sp2_mixed_contract_mismatch(execution, contract)
    if mismatch:
        execution.stop(mismatch)
        return
    run = replace(
        _sp2_mixed_run(execution, contract),
        label="ACQUISITION",
        product_id="M-SP2-ACQUISITION-PRODUCT",
        final_id="M-SP2-ACQUISITION-FINAL",
        product_procedure="SP2_ACQUISITION_PRODUCT",
        final_procedure="SP2_ACQUISITION_FINAL",
    )
    execution.register_terminal(
        (run.final_id,),
        run.final_procedure,
        lambda: _sp2_mixed_final(execution, contract, run, acceptance=False),
    )
    if not diagnostic_start(execution):
        return
    held = _Held()
    if not _product_phase(execution, contract, run, held):
        # The arms record still says why it holds no intervention.
        execution.not_run(
            (ARMS_ID,),
            "not_reached:"
            + (execution.record.primary_failure or "product_phase_incomplete"),
        )
        return
    _arms_phase(execution, contract, run, held)


def _product_phase(
    execution: Execution, contract: Q3ProductContract, run: _MixedRun, held: _Held
) -> bool:
    """Run the unchanged product and decide whether the precondition holds."""
    ids = (run.product_id,)
    if not execution.selected("SP2-acquisition") or not execution.begin(
        ids, run.product_procedure
    ):
        return False
    reproduced = False
    with (
        execution.ledger.ordinary_limit(
            operations=SP2_MIXED_PRODUCT_OPERATIONS, leave_seconds=_ARMS_SECONDS
        ),
        execution.procedure(ids),
    ):
        with execution.ledger.purpose_of("sp2:acquisition:build"):
            build = execution.run.boundaries.build_reader(
                execution.bound.send_and_wait
            ).read()
        observed_build = execution.record.environment.observed_build
        if not build.available or build.version != observed_build:
            execution.conclude(
                run.product_id,
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={"fresh_build": build.version if build.available else ""},
                    causes=["sp2_acquisition_build_unobserved_or_mismatched"],
                ),
            )
            execution.finish(run.product_procedure)
            execution.stop("sp2_acquisition_build_unobserved_or_mismatched")
            return False
        if not execution.run.transition(f"experiment:{run.product_procedure}:started"):
            execution.stop("persistence:sp2_acquisition_product_not_announced")
            return False
        held.runtimes = product_stage_runtimes(execution, contract, routed=True)
        with execution.ledger.effect_of("sp2:acquisition:apply-enterprise-services"):
            held.product = apply_private_product(
                execution,
                contract,
                held.runtimes,
                run_label=f"{SP2_CANDIDATE_LABEL} {execution.definition.stage.value}",
                bind_device_catalog=True,
            )
        mixed = _sp2_mixed_product_assessment(
            execution, contract, run, held.product, build.version
        )
        assessment = _precondition_assessment(execution, run, held, mixed)
        reproduced = assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
        execution.conclude(run.product_id, assessment)
    execution.finish(run.product_procedure)
    if not reproduced and not execution.stopped:
        execution.stop("sp2_acquisition_precondition_not_reproduced")
    return reproduced and not execution.stopped


def _product_effects_known(product: ServiceStageResult) -> str:
    """Name why the product's effects are not all known, or return ""."""
    if product.e5_effect_uncertain:
        return "product_e5_effect_uncertain"
    for label, result in (
        ("configuration", product.configuration_result),
        ("service", product.service_result),
    ):
        if result is None:
            return f"product_{label}_result_absent"
        if result.execution_journal.transport_unknown:
            return f"product_{label}_transport_unknown"
        for row in result.action_results:
            if (
                row.status is ActionExecutionStatus.UNKNOWN
                or row.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
                or row.result is ResultFact.NOT_OBSERVED
                or (
                    row.received_mutation is not None
                    and bool(row.received_mutation.call_error)
                )
            ):
                return f"product_{label}_effect_unknown:{row.action_id}"
    return ""


def _precondition_assessment(
    execution: Execution, run: _MixedRun, held: _Held, mixed: Assessment
) -> Assessment:
    """Read every client, the server and every pool, then decide the state."""
    if _eligible_profile(execution):
        return _eligible_precondition_assessment(execution, run, held, mixed)
    product = held.product
    assert product is not None
    clients = run.clients
    with execution.ledger.purpose_of("sp2:acquisition:precondition:clients"):
        client_read = execution.probes.read_dhcp_clients(
            tuple((name, "FastEthernet0") for name in clients)
        )
    with execution.ledger.purpose_of("sp2:acquisition:precondition:server"):
        server_read = execution.probes.read_dhcp_server_baseline(
            SP2_MIXED_SERVER, "FastEthernet0"
        )
    with execution.ledger.purpose_of("sp2:acquisition:precondition:leases"):
        lease_read = execution.probes.read_dhcp_lease_calibration(
            SP2_MIXED_SERVER,
            "FastEthernet0",
            tuple((name, run.windows.get(name, 1)) for name in run.pools),
        )
    readings = (
        client_readings(client_read.payload, clients)
        if client_read.observed and isinstance(client_read.payload, Mapping)
        else {}
    )
    held.readings = dict(readings)
    scans = (
        scans_by_pool(lease_read.payload, run.pools)
        if lease_read.observed and isinstance(lease_read.payload, Mapping)
        else unobserved_scans(run.pools, lease_read.cause)
    )
    server = server_read.payload if server_read.observed else None
    precondition = acquisition_precondition(clients, readings, server, scans, run.pools)
    effects = _product_effects_known(product)
    accepted = mixed.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    causes = list(precondition.causes)
    if effects:
        causes.append(effects)
    if accepted:
        causes.append("sp2_acquisition_product_served_every_client")
    if product.refused or not product.record_path or product.persist_error:
        causes.append("sp2_acquisition_product_not_run_or_not_persisted")
    facts = {
        **mixed.facts,
        "product_accepted": accepted,
        "product_assessment_causes": list(mixed.causes),
        "precondition": {
            "holds": not causes,
            "clients": dict(precondition.clients),
            "client_read": "observed" if client_read.observed else client_read.cause,
            "server_read": "observed" if server_read.observed else server_read.cause,
            "server": dict(server) if isinstance(server, Mapping) else {},
            "scans": {name: item.as_facts() for name, item in scans.items()},
            "client_readings": {
                name: {
                    key: value
                    for key, value in item.__dict__.items()
                    if key != "raw_rows"
                }
                for name, item in readings.items()
            },
        },
    }
    if accepted:
        conclusion = MeasurementConclusion.NEGATIVE_OBSERVED
    elif causes:
        conclusion = MeasurementConclusion.INCONCLUSIVE
    else:
        conclusion = MeasurementConclusion.SUPPORTED_IN_SAMPLE
    return Assessment(
        conclusion,
        facts=facts,
        causes=causes,
        limitations=[
            "precondition_reproduction_not_product_acceptance",
            "link_local_onset_time_not_observed",
            *mixed.limitations,
        ],
        outcome_unknown=bool(effects),
    )


def _explicit_start_capabilities(
    records: Mapping[str, Any], *, profile_id: str = "SP2-MIXED-ACQUISITION"
) -> dict[str, Any]:
    """Admit the explicit start privately, for this arm only.

    The composed records are copied; only the acquisition record changes,
    from its recorded state to SUPPORTED, and the source names why. The
    product's catalog and the contract are untouched.
    """
    copied = dict(records)
    record = copied.get(_ACQUIRE_KEY)
    if record is None:
        raise ValueError("explicit start has no acquisition capability record")
    copied[_ACQUIRE_KEY] = record.model_copy(
        update={
            "support": CapabilityStatus.SUPPORTED,
            "source": (
                "Private " + profile_id + " candidate: one documented "
                "DhcpClientProcess.dhcpRun per arm client; unqualified"
            ),
        }
    )
    return copied


def _reassert_outcomes(result, plan) -> dict[str, str]:
    """Classify each reassertion from its row and its mode read-back.

    The ordinary endpoint batch reports legacy rows without dispatch facts,
    so a failure there may still have run: only a known non-submission or
    rejection is `not_dispatched`. Any other failure, and every row of an
    application whose transport outcome is unknown, is `outcome_unknown`.
    """
    rows = {item.action_id: item for item in result.action_results}
    transport_unknown = bool(
        getattr(getattr(result, "execution_journal", None), "transport_unknown", False)
    )
    verified = {
        item.action_id: item.status
        for item in result.verification_results
        if getattr(item, "action_id", "")
    }
    outcomes: dict[str, str] = {}
    for action in plan.actions:
        assert isinstance(action, SetEndpointDhcp)
        row = rows.get(action.id)
        if row is None:
            outcomes[action.device_name] = "outcome_unknown:row_absent"
        elif transport_unknown:
            outcomes[action.device_name] = "outcome_unknown:transport_unknown"
        elif (
            row.status is ActionExecutionStatus.UNKNOWN
            or row.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
            or row.result is ResultFact.NOT_OBSERVED
        ):
            outcomes[action.device_name] = f"outcome_unknown:{row.status.value}"
        elif row.status not in (
            ActionExecutionStatus.APPLIED,
            ActionExecutionStatus.VERIFIED,
        ):
            known_not_sent = row.dispatch in (
                DispatchFact.NOT_SUBMITTED,
                DispatchFact.REJECTED,
            )
            outcomes[action.device_name] = (
                "not_dispatched:" if known_not_sent else "outcome_unknown:"
            ) + row.status.value
        elif verified.get(action.id) is not ActionExecutionStatus.VERIFIED:
            outcomes[action.device_name] = "mode_readback_not_verified"
        else:
            outcomes[action.device_name] = INTERVENTION_DISPATCHED
    return outcomes


def _arms_phase(
    execution: Execution, contract: Q3ProductContract, run: _MixedRun, held: _Held
) -> None:
    """Apply one typed intervention per arm client, then read one window.

    Once the first effect is dispatched the arms record is always concluded,
    whatever ends the phase: a persistence failure, a refused operation or
    an unknown outcome keeps every client's outcome and every partial result,
    and an effect cut short in flight is recorded as unknown.
    """
    ids = (ARMS_ID,)
    if not execution.begin(ids, ARMS_PROCEDURE):
        return
    arms = (
        {name: SP2_ELIGIBLE_ACQUISITION_ARMS[name] for name in held.cohort.eligible}
        if held.cohort is not None
        else dict(SP2_ACQUISITION_ARMS)
    )
    reassert = sorted(name for name, arm in arms.items() if arm == ARM_REASSERT)
    start = sorted(name for name, arm in arms.items() if arm == ARM_EXPLICIT_START)
    # Every arm client has an outcome from the start: controls are untouched,
    # and an intervention never reached says so rather than being absent.
    interventions: dict[str, str] = {
        name: "none"
        if name not in (*reassert, *start)
        else "not_dispatched:not_reached"
        for name in arms
    }
    facts: dict[str, Any] = (
        {"cohort": _cohort_facts(held.cohort)} if held.cohort is not None else {}
    )
    progress: dict[str, Any] = {"begun": False, "in_flight": ()}
    with (
        execution.ledger.ordinary_limit(
            operations=SP2_ACQUISITION_ARMS_OPERATIONS, leave_seconds=240
        ),
        execution.procedure(ids),
    ):
        try:
            _arms_effects_and_window(
                execution,
                contract,
                run,
                held,
                (arms, reassert, start),
                interventions,
                facts,
                progress,
            )
        finally:
            if (
                progress["begun"]
                and execution.measurement(ARMS_ID).status is MeasurementStatus.NOT_RUN
            ):
                for name in progress["in_flight"]:
                    interventions[name] = "outcome_unknown:interrupted_in_flight"
                execution.conclude(
                    ARMS_ID,
                    Assessment(
                        MeasurementConclusion.INCONCLUSIVE,
                        facts={
                            **facts,
                            "interventions": dict(interventions),
                            "window": list(progress.get("window", ())),
                        },
                        causes=[
                            "sp2_acquisition_arms_cut_short:"
                            + (execution.record.primary_failure or "unconcluded")
                        ],
                        outcome_unknown=any(
                            value.startswith("outcome_unknown")
                            for value in interventions.values()
                        ),
                    ),
                )
    execution.finish(ARMS_PROCEDURE)


def _arms_effects_and_window(
    execution: Execution,
    contract: Q3ProductContract,
    run: _MixedRun,
    held: _Held,
    selection: tuple[dict[str, str], list[str], list[str]],
    interventions: dict[str, str],
    facts: dict[str, Any],
    progress: dict[str, Any],
) -> None:
    """Dispatch the reassertions, then one explicit start at a time, then read.

    `progress` names whether any effect was dispatched and which clients'
    effect is in flight, so the caller can conclude truthfully on any exit.
    """
    arms, reassert, start = selection
    product = held.product
    assert product is not None and product.service_result is not None
    context = product_runtime_context(contract)
    progress["begun"] = True
    if reassert:
        if not execution.run.transition(f"experiment:{ARMS_PROCEDURE}:reassert"):
            execution.stop("persistence:sp2_acquisition_reassert_not_announced")
            return
        reassert_plan = sp2_acquisition_reassert_plan(
            contract.configuration_plan, device_names=reassert
        )
        progress.update(begun=True, in_flight=tuple(reassert))
        with execution.ledger.effect_of("sp2:acquisition:reassert"):
            reassert_result = ConfigurationApplicator(
                held.runtimes.configuration
            ).apply(
                reassert_plan,
                actual_source_topology_hash=contract.manifest.physical_topology_hash,
                capabilities=contract.device_capabilities,
                runtime_context=context,
                deployment_manifest=contract.manifest,
            )
        interventions.update(_reassert_outcomes(reassert_result, reassert_plan))
        progress["in_flight"] = ()
        facts["reassert"] = {
            "plan_id": reassert_plan.id,
            **application_rows(reassert_result),
        }
        if any(value.startswith("outcome_unknown") for value in interventions.values()):
            execution.conclude(
                ARMS_ID,
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={**facts, "interventions": dict(interventions)},
                    causes=["sp2_acquisition_reassert_outcome_unknown"],
                    outcome_unknown=True,
                ),
            )
            return
    facts["explicit_start"] = {}
    capabilities = _explicit_start_capabilities(
        contract.service_capabilities, profile_id=execution.definition.profile_id
    )
    unknown_seen = False
    for index, name in enumerate(start, start=1):
        # One client per application, so an unknown outcome is decided
        # before the next start is even built; nothing after it runs.
        if unknown_seen:
            interventions[name] = "not_dispatched:stopped_after_unknown_outcome"
            continue
        if execution.stopped:
            interventions[name] = (
                "not_dispatched:stopped:" + execution.record.primary_failure
            )
            continue
        if not execution.run.transition(
            f"experiment:{ARMS_PROCEDURE}:explicit-start:{name}"
        ):
            execution.stop("persistence:sp2_acquisition_start_not_announced")
            return
        if held.cohort is not None and not _eligible_before_effect(
            execution, run, held, name, arms, interventions, facts
        ):
            if execution.stopped:
                return
            continue
        start_plan = sp2_acquisition_start_plan(
            contract.service_plan,
            contract.configuration_plan,
            device_names=[name],
            nonce=f"{execution.nonce}:sp2-acquisition:{index}",
            required_address_state="link_local"
            if held.cohort is not None
            else "dhcp_mode",
        )
        server_ids = {
            item.id
            for item in start_plan.actions
            if isinstance(item, ConfigureServerDhcpPool | EnableServerDhcp)
        }
        retained = [
            item
            for item in product.service_result.action_results
            if item.action_id in server_ids
        ]
        effect_started = execution.ledger.elapsed()
        progress["in_flight"] = (name,)
        with execution.ledger.effect_of(f"sp2:acquisition:explicit-start:{name}"):
            start_result = ServiceApplicator(held.runtimes.services).apply(
                start_plan,
                actual_source_topology_hash=contract.manifest.physical_topology_hash,
                actual_source_configuration_hash=(
                    contract.service_plan.source_configuration_hash
                ),
                foundational_statuses=dict(product.foundational_statuses),
                capabilities=capabilities,
                runtime_context=context,
                deployment_manifest=contract.manifest,
                operational_readiness=DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
                retained_action_results=retained,
            )
        facts["explicit_start"][name] = {
            "plan_id": start_plan.id,
            "started_seconds": effect_started,
            "finished_seconds": execution.ledger.elapsed(),
            **application_rows(start_result),
        }
        action_id = next(
            item.id
            for item in start_plan.actions
            if item.action_type is ServiceActionType.ACQUIRE_DHCP_LEASE
        )
        interventions[name] = acquisition_request_outcome(start_result, action_id)
        progress["in_flight"] = ()
        if (
            held.cohort is not None
            and interventions[name].startswith("not_dispatched:")
            and "dhcp_client_not_link_local" in interventions[name]
        ):
            _eligible_before_effect(
                execution, run, held, name, arms, interventions, facts
            )
        if interventions[name] == INTERVENTION_DISPATCHED:
            execution.record.releases.append(
                ReleaseRecord(
                    resource=f"claim:{name}:FastEthernet0",
                    kind="claim",
                    outcome="retained_until_process_retirement",
                    detail="product claims are never reset or deleted",
                )
            )
            execution.record.engine_residue.append(f"claim:{name}:retained")
        unknown_seen = interventions[name].startswith("outcome_unknown")
    unknown = sorted(
        name
        for name, value in interventions.items()
        if value.startswith("outcome_unknown")
    )
    if unknown:
        # Never retried: no later effect of this run is admitted.
        execution.conclude(
            ARMS_ID,
            Assessment(
                MeasurementConclusion.INCONCLUSIVE,
                facts={**facts, "interventions": dict(interventions)},
                causes=[
                    f"sp2_acquisition_start_outcome_unknown:{name}" for name in unknown
                ],
                outcome_unknown=True,
            ),
        )
        return
    samples = _window(execution, run, progress)
    assessment = (
        assess_eligible_arms(
            arms,
            run.client_pools,
            interventions,
            samples,
            progress.get("servers", ()),
            expected_samples=SP2_ACQUISITION_SAMPLES,
        )
        if held.cohort is not None
        else assess_acquisition_arms(
            arms,
            {name: run.client_pools[name] for name in arms},
            interventions,
            samples,
        )
    )
    execution.conclude(
        ARMS_ID,
        replace(
            assessment,
            facts={
                **assessment.facts,
                **facts,
                "interventions": dict(interventions),
                "window": list(progress.get("window", ())),
                "window_samples_planned": SP2_ACQUISITION_SAMPLES,
                "window_wait_seconds": SP2_ACQUISITION_WAIT_SECONDS,
            },
            limitations=[
                *assessment.limitations,
                *(
                    ["reassertion_setter_errors_are_not_observable_in_ordinary_batch"]
                    if held.cohort is None
                    else ["activation_age_not_fully_observed"]
                ),
            ],
        ),
    )


def _read_facts(reading: Any) -> dict[str, Any]:
    """Return one probe reading as retained raw evidence."""
    return {
        "observed": reading.observed,
        "cause": reading.cause,
        "payload": reading.payload if reading.observed else None,
    }


def _window(
    execution: Execution, run: _MixedRun, progress: dict[str, Any]
) -> list[AcquisitionSample]:
    """Read every client, binding and pool once per sample, at a fixed cadence.

    Each read's raw answer is retained in `progress["window"]` as soon as it
    returns, so a refusal midway through the window keeps every completed
    sample and every completed read of the interrupted one.
    """
    if _eligible_profile(execution):
        return _eligible_window(execution, run, progress)
    clients = run.clients
    sleep = execution.run.boundaries.sleep
    samples: list[AcquisitionSample] = []
    retained: list[dict[str, Any]] = progress.setdefault("window", [])
    for index in range(1, SP2_ACQUISITION_SAMPLES + 1):
        waited = 0.0
        if index > 1:
            waited = execution.ledger.wait(SP2_ACQUISITION_WAIT_SECONDS, sleep)
        label = f"sp2:acquisition:window:{index}"
        reads: dict[str, Any] = {}
        retained.append({"index": index, "wait_seconds": waited, "reads": reads})
        with execution.ledger.purpose_of(label + ":clients"):
            client_read = execution.probes.read_dhcp_clients(
                tuple((name, "FastEthernet0") for name in clients)
            )
        reads["clients"] = _read_facts(client_read)
        with execution.ledger.purpose_of(label + ":bindings"):
            binding_read = execution.probes.read_client_bindings(clients)
        reads["bindings"] = _read_facts(binding_read)
        with execution.ledger.purpose_of(label + ":leases"):
            lease_read = execution.probes.read_dhcp_lease_calibration(
                SP2_MIXED_SERVER,
                "FastEthernet0",
                tuple((name, run.windows.get(name, 1)) for name in run.pools),
            )
        reads["leases"] = _read_facts(lease_read)
        causes = tuple(
            f"{name}:{reading.cause}"
            for name, reading in (
                ("clients", client_read),
                ("bindings", binding_read),
                ("leases", lease_read),
            )
            if not reading.observed
        )
        samples.append(
            AcquisitionSample(
                index=index,
                readings=(
                    client_readings(client_read.payload, clients)
                    if client_read.observed and isinstance(client_read.payload, Mapping)
                    else {}
                ),
                bindings=(
                    binding_read.payload.get("clients")
                    if binding_read.observed
                    and isinstance(binding_read.payload, Mapping)
                    else None
                ),
                scans=(
                    scans_by_pool(lease_read.payload, run.pools)
                    if lease_read.observed and isinstance(lease_read.payload, Mapping)
                    else unobserved_scans(run.pools, lease_read.cause)
                ),
                read_causes=causes,
                wait_seconds=waited,
            )
        )
        if execution.stopped or (index > 1 and waited < SP2_ACQUISITION_WAIT_SECONDS):
            # A truncated wait means the allowance is spent; the window is
            # recorded as it stands and its shortness is visible.
            break
    return samples


def _eligible_profile(execution: Execution) -> bool:
    return execution.definition.stage is QualificationStage.SP2_ELIGIBLE_ACQUISITION


def _cohort_facts(cohort: EligibleCohort) -> dict[str, Any]:
    return {
        "eligible": list(cohort.eligible),
        "observations": dict(cohort.observations),
        "causes": list(cohort.causes),
        "assignment": dict(SP2_ELIGIBLE_ACQUISITION_ARMS),
    }


def _eligible_census(
    execution: Execution, run: _MixedRun, index: int, frames: list[dict[str, Any]]
) -> tuple[AcquisitionSample, object]:
    """Read each shared dependency once and retain real read clock boundaries."""
    frame: dict[str, Any] = {
        "index": index,
        "started_seconds": execution.ledger.elapsed(),
        "reads": {},
    }
    frames.append(frame)
    calls = (
        (
            "clients",
            lambda: execution.probes.read_dhcp_clients(
                tuple((name, "FastEthernet0") for name in run.clients)
            ),
        ),
        ("bindings", lambda: execution.probes.read_client_bindings(run.clients)),
        (
            "server",
            lambda: execution.probes.read_dhcp_server_policy(
                SP2_MIXED_SERVER, "FastEthernet0"
            ),
        ),
        (
            "leases",
            lambda: execution.probes.read_dhcp_lease_calibration(
                SP2_MIXED_SERVER,
                "FastEthernet0",
                tuple((name, run.windows.get(name, 1)) for name in run.pools),
            ),
        ),
    )
    readings = {}
    try:
        for name, read in calls:
            entry = {
                "started_seconds": execution.ledger.elapsed(),
                "cause": "interrupted",
            }
            frame["reads"][name] = entry
            try:
                with execution.ledger.purpose_of(f"sp2:eligible:census:{index}:{name}"):
                    reading = read()
                readings[name] = reading
                entry.update(_read_facts(reading))
            finally:
                entry["finished_seconds"] = execution.ledger.elapsed()
    finally:
        frame["finished_seconds"] = execution.ledger.elapsed()
    clients, bindings, server, leases = (
        readings[name] for name in ("clients", "bindings", "server", "leases")
    )
    return AcquisitionSample(
        index=index,
        readings=client_readings(clients.payload, run.clients)
        if clients.observed and isinstance(clients.payload, Mapping)
        else {},
        bindings=bindings.payload.get("clients")
        if bindings.observed and isinstance(bindings.payload, Mapping)
        else None,
        scans=scans_by_pool(leases.payload, run.pools)
        if leases.observed and isinstance(leases.payload, Mapping)
        else unobserved_scans(run.pools, leases.cause),
        read_causes=tuple(
            f"{name}:{reading.cause}"
            for name, reading in readings.items()
            if not reading.observed
        ),
    ), server.payload if server.observed else None


def _eligible_precondition_assessment(
    execution: Execution, run: _MixedRun, held: _Held, mixed: Assessment
) -> Assessment:
    """Keep the product aggregate separate from prospective cohort admission."""
    assert held.product is not None
    frames: list[dict[str, Any]] = []
    sample, server = _eligible_census(execution, run, 0, frames)
    held.readings = dict(sample.readings)
    held.cohort = eligible_cohort(
        SP2_ELIGIBLE_ACQUISITION_ARMS, run.client_pools, sample, server
    )
    causes = list(held.cohort.causes)
    effects = _product_effects_known(held.product)
    if effects:
        causes.append(effects)
    if (
        held.product.refused
        or not held.product.record_path
        or held.product.persist_error
    ):
        causes.append("sp2_acquisition_product_not_run_or_not_persisted")
    return Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if held.cohort.holds and not causes
        else MeasurementConclusion.INCONCLUSIVE,
        facts={
            **mixed.facts,
            "product_accepted": mixed.conclusion
            is MeasurementConclusion.SUPPORTED_IN_SAMPLE,
            "product_assessment_causes": list(mixed.causes),
            "cohort": _cohort_facts(held.cohort),
            "eligibility_census": frames,
        },
        causes=causes,
        limitations=[
            "eligibility_not_product_acceptance",
            "activation_age_not_fully_observed",
            *mixed.limitations,
        ],
        outcome_unknown=bool(effects),
    )


def _eligible_before_effect(
    execution: Execution,
    run: _MixedRun,
    held: _Held,
    name: str,
    arms: Mapping[str, str],
    interventions: dict[str, str],
    facts: dict[str, Any],
) -> bool:
    """Remove eligibility after passive acquisition; never alter the fixed arms."""
    frames = facts.setdefault("pre_effect_censuses", [])
    sample, server = _eligible_census(execution, run, len(frames) + 1, frames)
    cohort = eligible_cohort(
        SP2_ELIGIBLE_ACQUISITION_ARMS,
        run.client_pools,
        sample,
        server,
        require_comparisons=False,
    )
    frames[-1]["target"] = name
    frames[-1]["cohort"] = _cohort_facts(cohort)
    if cohort.causes:
        execution.stop("sp2_eligible_shared_precondition_changed")
        return False
    if name not in cohort.eligible:
        interventions[name] = (
            "observed_before_intervention"
            if cohort.observations[name] == "assigned_observer"
            else "not_dispatched:eligibility_lost"
        )
        return False
    pool = run.client_pools[name].effective_pool_name
    controls = [
        client
        for client, arm in arms.items()
        if arm == "control" and run.client_pools[client].effective_pool_name == pool
    ]
    if not controls or any(client not in cohort.eligible for client in controls):
        interventions[name] = "not_dispatched:control_eligibility_lost"
        return False
    return True


def _eligible_window(
    execution: Execution, run: _MixedRun, progress: dict[str, Any]
) -> list[AcquisitionSample]:
    """Observe all subjects, server policy and pools for the declared exposure."""
    samples = []
    frames = progress.setdefault("window", [])
    servers = progress.setdefault("servers", [])
    for index in range(1, SP2_ACQUISITION_SAMPLES + 1):
        waited = (
            execution.ledger.wait(
                SP2_ACQUISITION_WAIT_SECONDS, execution.run.boundaries.sleep
            )
            if index > 1
            else 0.0
        )
        sample, server = _eligible_census(execution, run, index, frames)
        frames[-1]["wait_seconds"] = waited
        samples.append(replace(sample, wait_seconds=waited))
        servers.append(server)
        if execution.stopped or (index > 1 and waited < SP2_ACQUISITION_WAIT_SECONDS):
            break
    return samples
