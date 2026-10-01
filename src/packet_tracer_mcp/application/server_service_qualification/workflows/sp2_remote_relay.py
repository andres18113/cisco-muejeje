"""SP-2: the private routed named-pool discriminator through one relay."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from ....domain.enterprise.models.configuration import (
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ....domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ....domain.enterprise.models.deployment import deployment_manifest_semantic_hash
from ....domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServiceType,
    ServiceVerificationKind,
)
from ....domain.enterprise.models.service_qualification import (
    Q3_FL_SETTLE_INTERVAL_SECONDS,
    SP2_REMOTE_ACQUISITION_MAX_POLLS,
    SP2_REMOTE_ACQUISITION_POLL_SECONDS,
    MeasurementConclusion,
)
from ....domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)
from ....domain.enterprise.services.dhcp_lease_evidence import (
    TERMINATION_POOL_ABSENT,
    AddressRange,
    ClientReading,
    LeaseScan,
    client_readings,
    normalized_mac,
    scans_by_pool,
    unobserved_scans,
)
from ....domain.enterprise.services.qualification_product_evidence import (
    e5_foundation_cause,
    readback_not_observed_cause,
    service_result_cause,
)
from ....domain.enterprise.services.qualification_terminal_evidence import (
    terminal_router_rows_complete,
)
from ....domain.enterprise.services.service_access_readiness import (
    DHCP_ACQUISITION_KINDS,
    derive_access_readiness_plan,
)
from ....domain.enterprise.services.service_compiler import ServiceCompiler
from ....domain.enterprise.services.service_diagnostic_profiles import (
    d_dhcp_enable_only_plan,
    d_dhcp_pool_only_plan,
    q3_fastloop_client_mode_plan,
    sp2_preclient_configuration_plan,
)
from ....domain.enterprise.services.service_qualification_evidence import Assessment
from ....domain.enterprise.services.sp2_pool_diagnostic import assess_sp2_remote_samples
from ....domain.enterprise.services.topology_identity import compute_topology_hashes
from ...use_cases.apply_configuration import ConfigurationApplicator
from ...use_cases.apply_enterprise_services import _dhcp_prelease_paths, _path_admission
from ...use_cases.apply_services import ServiceApplicator
from ...use_cases.service_access_readiness_gate import ServiceAccessReadinessGate
from ..contracts import Q3ProductContract
from ..dhcp_observations import read_client_binding
from ..execution import Execution
from ..fixtures import diagnostic_start
from ..operation_budget import LedgerPhase, OperationRefused
from ..product_support import (
    DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
    SP1_CAPTURE_DEADLINE_SECONDS,
    SP1_CAPTURE_SAMPLE_CALLS,
    ExactInventoryServiceRuntime,
    RoutedInventoryConfigurationRuntime,
    application_rows,
    capability_digest,
    product_runtime_context,
    projection_foundations,
)

SP2_REMOTE_INTENT_SHA256 = (
    "f3bde2722df87fc64ca19caa58a1b7cdecd5f69547323d12cc585619d6d7c34b"
)
SP2_REMOTE_TOPOLOGY_SHA256 = (
    "9d8db364a8260407282796baccb85a56d5d314d241e84179ed2e364b5dee915f"
)
SP2_REMOTE_CONFIGURATION_SHA256 = (
    "a58405ecbf3a60f47ead76c5e1b7cb52da1320458c969cf51677a6e672d9491f"
)
SP2_REMOTE_SERVICES_SHA256 = (
    "77c12f340f9263eb9d537d3cf034436a5dbd50d831dfd98ab226aeeb4fca0282"
)
SP2_REMOTE_SERVICE_CAPABILITIES_SHA256 = (
    "153c17b5226d04e8d474229e5309e6c604347b103a239d135852e84d82e8b0f3"
)
SP2_REMOTE_BUILD = "9.0.1.0858"
SP2_REMOTE_MANIFEST_SHA256 = (
    "8d755b89559134139c60aa01b0be6eb0b0541ca8e6d6e38443215e0ed635038e"
)
SP2_REMOTE_REQUIRED_DEVICE_EVIDENCE = (
    (
        "1941",
        "layer3",
        "governed controlled_probe/layer3-probe; snapshot=12c2c6bec52123b6df3a3d2f8f5233f92f760e4414f9a7b221c745894f35fc75; method=cli_plus_readback",
        True,
        "live_qualified",
    ),
    (
        "1941",
        "supports_static_routes",
        "governed packet_tracer_runtime/sp1-routed-w2; snapshot=aa2d0f77d75d260f27399b21a4f1738df749e4114609fb9d42ecb4198536b90b; method=cli_plus_readback",
        True,
        "live_qualified",
    ),
    (
        "1941",
        "supports_dhcp_relay",
        "candidate:SERVER-PT-SP2-GENERALIZED-DHCP-RELAY-01",
        False,
        "candidate",
    ),
    (
        "IE-2000",
        "supports_vlan",
        "governed controlled_probe/vlan-probe; snapshot=a90573080383dec861b75c72875d2db1d8c75ed5008eaa6e6f866354e765423a; method=cli_plus_readback",
        True,
        "live_qualified",
    ),
)


def _sp2_remote_contract_mismatch(
    execution: Execution, contract: Q3ProductContract
) -> str:
    """Bind a private candidate to this exact stage and composed plan."""
    definition = execution.definition
    if (
        not contract.intent_json
        or hashlib.sha256(contract.intent_json.encode()).hexdigest()
        != SP2_REMOTE_INTENT_SHA256
    ):
        return "sp2_remote_intent_changed"
    if (
        contract.topology.physical_topology_hash != SP2_REMOTE_TOPOLOGY_SHA256
        or compute_topology_hashes(contract.topology).physical_topology_hash
        != SP2_REMOTE_TOPOLOGY_SHA256
        or contract.manifest.physical_topology_hash != SP2_REMOTE_TOPOLOGY_SHA256
    ):
        return "sp2_remote_topology_hash_changed"
    if (
        contract.manifest.semantic_hash != SP2_REMOTE_MANIFEST_SHA256
        or deployment_manifest_semantic_hash(contract.manifest)
        != SP2_REMOTE_MANIFEST_SHA256
    ):
        return "sp2_remote_manifest_hash_changed"
    if (
        contract.configuration_plan.semantic_hash != SP2_REMOTE_CONFIGURATION_SHA256
        or configuration_plan_semantic_hash(contract.configuration_plan)
        != SP2_REMOTE_CONFIGURATION_SHA256
        or contract.service_plan.semantic_hash != SP2_REMOTE_SERVICES_SHA256
        or ServiceCompiler._semantic_hash(contract.service_plan)
        != SP2_REMOTE_SERVICES_SHA256
        or contract.configuration_plan.source_topology_hash
        != SP2_REMOTE_TOPOLOGY_SHA256
        or contract.service_plan.source_configuration_hash
        != SP2_REMOTE_CONFIGURATION_SHA256
    ):
        return "sp2_remote_plan_hash_changed"
    if contract.manifest.deployment_id != f"qualification/{execution.record.run_id}":
        return "sp2_remote_deployment_id_changed"
    if (
        contract.manifest.backend != "packet_tracer"
        or contract.manifest.backend_version != SP2_REMOTE_BUILD
        or contract.manifest.environment_fingerprint.backend != "packet_tracer"
        or contract.manifest.environment_fingerprint.backend_version != SP2_REMOTE_BUILD
    ):
        return "sp2_remote_build_or_backend_changed"

    models = {"1941", "IE-2000", "PC-PT", "Server-PT"}
    if set(contract.device_capabilities) != models:
        return "sp2_remote_capability_snapshot_changed"
    try:
        if (
            capability_digest(contract.service_capabilities)
            != SP2_REMOTE_SERVICE_CAPABILITIES_SHA256
        ):
            return "sp2_remote_capability_snapshot_changed"
        catalog = contract.device_capability_catalog
        if catalog is None or any(
            catalog.capabilities_for(model, SP2_REMOTE_BUILD)
            != contract.device_capabilities[model]
            for model in models
        ):
            return "sp2_remote_candidate_catalog_changed"
        if any(
            capability.packet_tracer_version != SP2_REMOTE_BUILD
            for capability in contract.device_capabilities.values()
        ):
            return "sp2_remote_required_capability_evidence_changed"
        for (
            model,
            name,
            source_detail,
            verified,
            confidence,
        ) in SP2_REMOTE_REQUIRED_DEVICE_EVIDENCE:
            capability = contract.device_capabilities[model]
            if getattr(capability, name).value != "supported" or not any(
                row.capability == name
                and row.status.value == "supported"
                and row.source.value == "static_override"
                and row.source_detail == source_detail
                and row.packet_tracer_version == SP2_REMOTE_BUILD
                and row.verified is verified
                and row.confidence == confidence
                for row in capability.evidence
            ):
                return "sp2_remote_required_capability_evidence_changed"
    except (AttributeError, KeyError, TypeError, ValueError):
        return "sp2_remote_capability_snapshot_unreadable"
    if {(item.name, item.model) for item in contract.topology.devices} != {
        (item.name, item.model) for item in definition.fixtures
    }:
        return "sp2_remote_device_fixture_changed"
    if {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in contract.topology.links
    } != {
        (item.device_a, item.port_a, item.device_b, item.port_b, item.cable)
        for item in definition.links
    }:
        return "sp2_remote_link_fixture_changed"
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
        return "sp2_remote_inventory_changed"
    if len(contract.service_plan.services) != 1:
        return "sp2_remote_service_count_changed"
    [service] = contract.service_plan.services
    selected = definition.selected_clients
    ids = {item.name: item.id for item in contract.topology.devices}
    if (
        service.service_type is not ServiceType.DHCP
        or service.segment_id != "br1-data"
        or service.host_device_id != ids.get("HQ-DEFAULT-DNS-01")
        or service.client_device_ids != [ids[selected[0]]]
    ):
        return "sp2_remote_selected_service_changed"
    if contract.device_capability_evidence != (
        {
            "build": SP2_REMOTE_BUILD,
            "model": "1941",
            "capability": "supports_dhcp_relay",
            "status": "supported",
            "source": "static_override",
            "source_detail": "candidate:SERVER-PT-SP2-GENERALIZED-DHCP-RELAY-01",
            "confidence": "candidate",
            "verified": False,
        },
    ):
        return "sp2_remote_candidate_provenance_changed"
    return ""


SP2_REMOTE_SERVER = "HQ-DEFAULT-DNS-01"
SP2_REMOTE_CLIENT = "BR1-DEFAULT-PC-01"
SP2_REMOTE_POOL = "BR1_DATA"
SP2_REMOTE_ROUTERS = ("BR1-EDGE-RTR-01", "HQ-EDGE-RTR-01")


def _sp2_remote_snapshot(execution: Execution, label: str) -> dict[str, Any]:
    """Read the exact Server-PT process and every physical pool before effects."""
    try:
        with execution.ledger.purpose_of(f"sp2:remote:server:{label}"):
            reading = execution.probes.read_dhcp_server_baseline(
                SP2_REMOTE_SERVER, "FastEthernet0"
            )
    except OperationRefused as exc:
        return {"observed": False, "cause": f"snapshot_refused:{exc.reason}"}
    raw = reading.payload if reading.observed else None
    valid = (
        isinstance(raw, Mapping)
        and raw.get("device") == SP2_REMOTE_SERVER
        and raw.get("interface") == "FastEthernet0"
        and raw.get("found") is True
        and raw.get("process_found") is True
        and raw.get("error") == ""
        and raw.get("truncated") is False
        and isinstance(raw.get("pools"), list)
        and raw.get("pool_count") == len(raw["pools"])
        and raw.get("enabled_type") == "boolean"
        and type(raw.get("enabled")) is bool
    )
    return {
        "observed": bool(valid),
        "cause": "" if valid else (reading.cause or "server_snapshot_unattributed"),
        "raw": dict(raw) if isinstance(raw, Mapping) else {},
    }


def _sp2_remote_physical_policy(
    snapshot: Mapping[str, Any], pool: ConfigureServerDhcpPool, enabled: bool
) -> str:
    """Require the intended stored policy and a disjoint competing default."""
    raw = snapshot.get("raw", {})
    if not snapshot.get("observed") or raw.get("enabled") is not enabled:
        return "sp2_remote_process_state_unverified"
    rows = raw.get("pools", [])
    if (
        not isinstance(rows, list)
        or len(rows) != 2
        or not all(isinstance(row, Mapping) for row in rows)
    ):
        return "sp2_remote_physical_pool_set_unverified"
    by_name = {row.get("name"): row for row in rows}
    if set(by_name) != {SP2_REMOTE_POOL, "serverPool"}:
        return "sp2_remote_physical_pool_set_unverified"
    named = by_name[SP2_REMOTE_POOL]
    if (
        named.get("network") != pool.network
        or named.get("mask") != pool.netmask
        or named.get("gateway") != pool.gateway
        or named.get("dns") != pool.dns_server
        or named.get("start") != pool.lease_start
        or named.get("end") != pool.lease_end
        or named.get("max") != pool.max_users
    ):
        return "sp2_remote_named_policy_unverified"
    try:
        from ipaddress import IPv4Address

        default_low = IPv4Address(by_name["serverPool"]["start"])
        default_high = IPv4Address(by_name["serverPool"]["end"])
        named_low = IPv4Address(pool.lease_start)
        named_high = IPv4Address(pool.lease_end)
    except (KeyError, ValueError, TypeError):
        return "sp2_remote_default_range_unreadable"
    if default_low > default_high or not (
        default_high < named_low or named_high < default_low
    ):
        return "sp2_remote_default_competes_with_named_range"
    return ""


def _sp2_remote_scan(execution: Execution, label: str) -> dict[str, LeaseScan]:
    """Index one shared named/default sample without fabricating table ends."""
    names = (SP2_REMOTE_POOL, "serverPool")
    try:
        with execution.ledger.purpose_of(f"sp2:remote:leases:{label}"):
            reading = execution.probes.read_dhcp_lease_calibration(
                SP2_REMOTE_SERVER,
                "FastEthernet0",
                ((SP2_REMOTE_POOL, 4), ("serverPool", 16)),
            )
    except OperationRefused as exc:
        return unobserved_scans(names, f"scan_refused:{exc.reason}")
    payload = reading.payload if reading.observed else None
    if not (
        isinstance(payload, Mapping)
        and payload.get("device") == SP2_REMOTE_SERVER
        and payload.get("interface") == "FastEthernet0"
        and payload.get("found") is True
        and payload.get("process_found") is True
        and payload.get("error") == ""
    ):
        return unobserved_scans(names, reading.cause or "scan_subject_invalid")
    return scans_by_pool(payload, names)


def _sp2_remote_server_gateway_cause(
    binding: Mapping[str, object], planned: SetEndpointStaticAddress | None
) -> str:
    """Require the server's planned address and return hop, read not assumed.

    A relayed reply leaves the server toward the relay agent through its
    default gateway. Only getters that answered without error count, and
    every one of them must name the planned gateway.
    """
    gateways = binding.get("gateway_reads")
    observed = (
        [
            item.get("value")
            for item in gateways
            if isinstance(item, Mapping)
            and item.get("api") is True
            and item.get("error") == ""
        ]
        if isinstance(gateways, list)
        else []
    )
    if (
        planned is None
        or binding.get("device") != SP2_REMOTE_SERVER
        or binding.get("found") is not True
        or binding.get("port_found") is not True
        or binding.get("error") != ""
        or binding.get("ipv4") != planned.ipv4
        or binding.get("netmask") != planned.netmask
        or not observed
        or any(value != planned.gateway for value in observed)
    ):
        return "sp2_remote_server_gateway_unverified"
    return ""


def _sp2_remote_client(execution: Execution, label: str) -> ClientReading:
    """Read one selected PC through the typed client observer."""
    try:
        with execution.ledger.purpose_of(f"sp2:remote:client:{label}"):
            reading = execution.probes.read_dhcp_clients(
                ((SP2_REMOTE_CLIENT, "FastEthernet0"),)
            )
    except OperationRefused as exc:
        return ClientReading(
            SP2_REMOTE_CLIENT, False, cause=f"client_refused:{exc.reason}"
        )
    if not reading.observed:
        return ClientReading(SP2_REMOTE_CLIENT, False, cause=reading.cause)
    rows = (
        reading.payload.get("clients") if isinstance(reading.payload, Mapping) else None
    )
    if (
        not isinstance(rows, list)
        or len(rows) != 1
        or not isinstance(rows[0], Mapping)
        or rows[0].get("device") != SP2_REMOTE_CLIENT
    ):
        return ClientReading(
            SP2_REMOTE_CLIENT,
            False,
            cause="client_rows_ambiguous",
            raw_rows=tuple(dict(row) for row in rows if isinstance(row, Mapping))
            if isinstance(rows, list)
            else (),
        )
    if rows[0].get("interface") != "FastEthernet0":
        return ClientReading(
            SP2_REMOTE_CLIENT,
            False,
            cause="client_interface_mismatch",
            raw_rows=(dict(rows[0]),),
        )
    return client_readings(reading.payload, (SP2_REMOTE_CLIENT,)).get(
        SP2_REMOTE_CLIENT,
        ClientReading(SP2_REMOTE_CLIENT, False, cause="client_absent"),
    )


def _sp2_remote_product(
    execution: Execution, contract: Q3ProductContract
) -> Assessment:
    """Apply the composed E5/E6 path and sample physical relay-associated leases."""
    facts: dict[str, Any] = {
        "intent_sha256": SP2_REMOTE_INTENT_SHA256,
        "topology_sha256": contract.topology.physical_topology_hash,
        "configuration_sha256": contract.configuration_plan.semantic_hash,
        "services_sha256": contract.service_plan.semantic_hash,
        "candidate_device_evidence": list(contract.device_capability_evidence),
        "device_capabilities_sha256": capability_digest(contract.device_capabilities),
        "service_capabilities_sha256": capability_digest(contract.service_capabilities),
        "samples": [],
    }

    def budget_cause() -> str:
        denied = next(
            (
                row.refused
                for row in execution.ledger.entries
                if row.phase == LedgerPhase.EXPERIMENT.value
                and row.refused
                in {"operation_budget_exhausted", "time_budget_exhausted"}
            ),
            "",
        )
        return f"budget:sp2_remote_product:{denied}" if denied else ""

    def stopped(reason: str) -> Assessment:
        budget = budget_cause()
        if budget and reason != budget:
            facts["downstream_stop_cause"] = reason
        effective = budget or reason
        execution.stop(effective)
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=[effective] if effective == reason else [effective, reason],
            limitations=[
                "private_candidate_not_public_support",
                "packet_giaddr_not_observed",
            ],
        )

    boundaries = execution.run.boundaries
    inner = boundaries.native_product_runtimes(execution.bound, contract.inventory)
    configuration_runtime = RoutedInventoryConfigurationRuntime(
        inner.configuration, contract.inventory
    )
    service_runtime = ExactInventoryServiceRuntime(inner.services, contract.inventory)
    context = product_runtime_context(contract)
    pool_actions = [
        item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    ]
    lease_expectations = [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
        and item.client_device_name == SP2_REMOTE_CLIENT
    ]
    if len(pool_actions) != 1 or len(lease_expectations) != 1:
        return stopped("sp2_remote_pool_or_lease_selection_not_exact")
    [pool] = pool_actions
    [lease_expectation] = lease_expectations
    preclient, rewrites = sp2_preclient_configuration_plan(contract.configuration_plan)
    facts["preclient_projection"] = {
        "id": preclient.id,
        "semantic_hash": preclient.semantic_hash,
        "rewrites": [item.as_text() for item in rewrites],
    }
    if len(preclient.actions) != 18 or any(
        isinstance(item, SetEndpointDhcp) for item in preclient.actions
    ):
        return stopped("sp2_remote_preclient_projection_not_exact")
    if not execution.run.transition("experiment:SP2_REMOTE:e5_preclient"):
        return stopped("persistence:sp2_remote_e5_not_announced")
    with execution.ledger.effect_of("sp2:remote:product:e5_preclient"):
        e5 = ConfigurationApplicator(configuration_runtime).apply(
            preclient,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
        )
    facts["e5_preclient"] = application_rows(e5)
    foundations = projection_foundations(contract, preclient, e5)
    cause = e5_foundation_cause(
        e5, foundations, {item.id for item in preclient.actions}
    )
    if cause:
        return stopped(cause)
    helper = [
        item
        for item in preclient.actions
        if item.action_type.value == "configure_dhcp_relay"
    ]
    if len(helper) != 1 or not any(
        item.action_id == helper[0].id and item.status is ActionExecutionStatus.VERIFIED
        for item in e5.verification_results
    ):
        return stopped("sp2_remote_helper_readback_unverified")
    facts["foundations"] = {key: value.value for key, value in foundations.items()}
    baseline = _sp2_remote_snapshot(execution, "after_e5")
    facts["after_e5"] = baseline
    if not baseline["observed"] or baseline["raw"].get("enabled") is not False:
        return stopped("sp2_remote_process_not_proven_disabled")
    if baseline["raw"].get("pool_count") != 1 or [
        row.get("name") for row in baseline["raw"].get("pools", [])
    ] != ["serverPool"]:
        return stopped("sp2_remote_initial_pool_set_not_exact")
    before = _sp2_remote_client(execution, "before_pool")
    facts["before_client"] = before.__dict__
    if (
        not before.observed
        or before.mode is not False
        or before.ipv4 not in ("", "0.0.0.0")
    ):
        return stopped("sp2_remote_client_not_unbound")

    unsupported, paths = _path_admission(
        contract.configuration_plan,
        contract.service_plan,
        contract.service_plan.services,
        links=contract.topology.links,
    )
    facts["path_refusals"] = unsupported
    if unsupported or len(paths) != 1:
        return stopped("sp2_remote_path_not_admitted")
    readiness = derive_access_readiness_plan(
        configuration_actions=contract.configuration_plan.actions,
        verification_expectations=contract.service_plan.verification_expectations,
        request_kinds=DHCP_ACQUISITION_KINDS,
        routed_paths=_dhcp_prelease_paths(paths, contract.service_plan.services),
    )
    gate = ServiceAccessReadinessGate(
        readiness,
        configuration_runtime,
        clock=execution.bound.clock,
        device_names={item.id: item.name for item in contract.topology.devices},
        continuity_observer=configuration_runtime,
        routed_observer=configuration_runtime,
    )
    gate.begin_invocation()
    with execution.ledger.purpose_of("sp2:remote:prelease_readiness"):
        verdict = gate.decide(lease_expectation.id)
    facts["readiness"] = {
        "verdict": verdict.as_row() if verdict is not None else None,
        "groups": gate.rows(),
        "unplaced": [item.expectation_id for item in readiness.unplaced],
    }
    if verdict is None or not verdict.admitted or readiness.unplaced:
        return stopped("sp2_remote_access_or_routed_readiness_refused")

    def apply_e6() -> str:
        """Write and read the named pool, then enable and read the process."""
        for name, projection, enabled in (
            ("pool", d_dhcp_pool_only_plan, False),
            ("enable", d_dhcp_enable_only_plan, True),
        ):
            plan, changes = projection(
                contract.service_plan,
                executed_configuration_action_ids=frozenset(foundations),
            )
            facts[f"e6_{name}_projection"] = {
                "id": plan.id,
                "semantic_hash": plan.semantic_hash,
                "rewrites": [item.as_text() for item in changes],
            }
            if len(plan.actions) != 1 or len(plan.verification_expectations) != 1:
                return f"sp2_remote_{name}_projection_not_exact"
            if not execution.run.transition(f"experiment:SP2_REMOTE:e6_{name}"):
                return f"persistence:sp2_remote_e6_{name}_not_announced"
            with execution.ledger.effect_of(f"sp2:remote:product:e6_{name}"):
                e6 = ServiceApplicator(service_runtime).apply(
                    plan,
                    actual_source_topology_hash=contract.manifest.physical_topology_hash,
                    actual_source_configuration_hash=contract.service_plan.source_configuration_hash,
                    foundational_statuses=foundations,
                    capabilities=contract.service_capabilities,
                    runtime_context=context,
                    deployment_manifest=contract.manifest,
                    operational_readiness=DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
                )
            facts[f"e6_{name}"] = application_rows(e6)
            cause = service_result_cause(
                e6,
                {item.id for item in plan.actions},
                expected_verification_ids={
                    item.id for item in plan.verification_expectations
                },
            ) or readback_not_observed_cause(e6)
            if cause:
                return cause
            snapshot = _sp2_remote_snapshot(execution, f"after_{name}")
            facts[f"after_{name}"] = snapshot
            cause = _sp2_remote_physical_policy(snapshot, pool, enabled)
            if cause:
                return cause
            scan = _sp2_remote_scan(execution, f"after_{name}")
            facts[f"after_{name}_scan"] = {
                key: value.as_facts() for key, value in scan.items()
            }
        return ""

    # Profile v3 (after e5): the product order. The selected PC enters DHCP
    # mode while the process is still disabled and the named pool absent;
    # the pool is then written and the process enabled. Only serverPool can
    # be read before the pool exists.
    before_mode = _sp2_remote_client(execution, "before_mode")
    facts["before_mode"] = before_mode.__dict__
    if (
        not before_mode.observed
        or before_mode.mode is not False
        or before_mode.ipv4 not in ("", "0.0.0.0")
    ):
        return stopped("sp2_remote_client_prebound_before_mode")
    prelease = _sp2_remote_scan(execution, "before_mode")
    facts["before_mode_scan"] = {
        key: value.as_facts() for key, value in prelease.items()
    }
    default_before = prelease.get("serverPool")
    named_before = prelease.get(SP2_REMOTE_POOL)
    if (
        default_before is None
        or not default_before.observed
        or named_before is None
        or not named_before.observed
    ):
        return stopped("sp2_remote_pre_mode_pool_unobserved")
    # The named pool must be read absent: mode-first is an observed state.
    if named_before.termination != TERMINATION_POOL_ABSENT or named_before.rows:
        return stopped("sp2_remote_named_pool_present_before_mode")
    if any(
        scan.rows_with_normalized_mac(before_mode.mac)
        for scan in prelease.values()
        if scan.observed
    ):
        return stopped("sp2_remote_preexisting_client_lease")
    planned_server = next(
        (
            item
            for item in contract.configuration_plan.actions
            if isinstance(item, SetEndpointStaticAddress)
            and item.device_name == SP2_REMOTE_SERVER
        ),
        None,
    )
    server_binding = read_client_binding(
        execution, SP2_REMOTE_SERVER, "server_before_mode"
    )
    facts["server_binding"] = dict(server_binding)
    cause = _sp2_remote_server_gateway_cause(server_binding, planned_server)
    if cause:
        return stopped(cause)
    mode_plan = q3_fastloop_client_mode_plan(
        contract.configuration_plan, device_names=(SP2_REMOTE_CLIENT,)
    )
    if len(mode_plan.actions) != 1 or not isinstance(
        mode_plan.actions[0], SetEndpointDhcp
    ):
        return stopped("sp2_remote_mode_projection_not_exact")
    facts["mode_projection"] = {
        "id": mode_plan.id,
        "semantic_hash": mode_plan.semantic_hash,
    }
    if not execution.run.transition("experiment:SP2_REMOTE:e5_client_mode"):
        return stopped("persistence:sp2_remote_mode_not_announced")
    with execution.ledger.effect_of("sp2:remote:product:e5_client_mode"):
        mode_result = ConfigurationApplicator(configuration_runtime).apply(
            mode_plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
        )
    facts["e5_client_mode"] = application_rows(mode_result)
    mode_foundations = projection_foundations(contract, mode_plan, mode_result)
    cause = e5_foundation_cause(
        mode_result, mode_foundations, {item.id for item in mode_plan.actions}
    )
    if cause:
        return stopped(cause)
    # Before the pool write, re-read both sides: the client in DHCP mode and
    # unbound, the process still disabled with only its stock pool.
    after_mode = _sp2_remote_client(execution, "after_mode_before_pool")
    facts["after_mode_before_pool"] = after_mode.__dict__
    if (
        not after_mode.observed
        or after_mode.mode is not True
        or after_mode.ipv4 not in ("", "0.0.0.0")
    ):
        return stopped("sp2_remote_client_state_changed_before_pool")
    server_before_pool = _sp2_remote_snapshot(execution, "after_mode_before_pool")
    facts["server_after_mode_before_pool"] = server_before_pool
    if (
        not server_before_pool["observed"]
        or server_before_pool["raw"].get("enabled") is not False
        or [row.get("name") for row in server_before_pool["raw"].get("pools", [])]
        != ["serverPool"]
    ):
        return stopped("sp2_remote_server_state_changed_before_pool")
    # E6 runs with the verified mode foundation, ID and status together.
    foundations = {**foundations, **mode_foundations}
    cause = apply_e6()
    if cause:
        return stopped(cause)
    # Passive, bounded wait for the relayed acquisition: client reads only,
    # no request, ping or dhcpRun. The two separated samples follow either
    # way, so an address that never appears stays a retained finding.
    polls: list[dict[str, object]] = []
    acquired = False
    for ordinal in range(1, SP2_REMOTE_ACQUISITION_MAX_POLLS + 1):
        waited = execution.ledger.wait(
            SP2_REMOTE_ACQUISITION_POLL_SECONDS, boundaries.sleep
        )
        if waited < SP2_REMOTE_ACQUISITION_POLL_SECONDS:
            facts["acquisition"] = {
                "polls": polls,
                "acquired": False,
                "max_polls": SP2_REMOTE_ACQUISITION_MAX_POLLS,
                "poll_seconds": SP2_REMOTE_ACQUISITION_POLL_SECONDS,
            }
            return stopped("sp2_remote_acquisition_interval_unavailable")
        polled = _sp2_remote_client(execution, f"acquire_{ordinal}")
        polls.append(
            {
                "observed": polled.observed,
                "mode": polled.mode,
                "ipv4": polled.ipv4,
                "netmask": polled.netmask,
                "cause": polled.cause,
            }
        )
        # A link-local fallback is a failed acquisition, not an address.
        if (
            polled.observed
            and polled.ipv4 not in ("", "0.0.0.0")
            and not polled.ipv4.startswith("169.254.")
        ):
            acquired = True
            break
    facts["acquisition"] = {
        "polls": polls,
        "acquired": acquired,
        "max_polls": SP2_REMOTE_ACQUISITION_MAX_POLLS,
        "poll_seconds": SP2_REMOTE_ACQUISITION_POLL_SECONDS,
    }
    readings: list[ClientReading] = []
    bindings: list[Mapping[str, object]] = []
    named_scans: list[LeaseScan] = []
    default_scans: list[LeaseScan] = []
    for ordinal in (1, 2):
        waited = execution.ledger.wait(Q3_FL_SETTLE_INTERVAL_SECONDS, boundaries.sleep)
        if waited < Q3_FL_SETTLE_INTERVAL_SECONDS:
            return stopped("sp2_remote_sample_interval_unavailable")
        label = f"sample_{ordinal}"
        reading = _sp2_remote_client(execution, label)
        binding = read_client_binding(execution, SP2_REMOTE_CLIENT, label)
        scans = _sp2_remote_scan(execution, label)
        named = scans.get(SP2_REMOTE_POOL, LeaseScan(SP2_REMOTE_POOL, False, "absent"))
        default = scans.get("serverPool", LeaseScan("serverPool", False, "absent"))
        readings.append(reading)
        bindings.append(binding)
        named_scans.append(named)
        default_scans.append(default)
        facts["samples"].append(
            {
                "label": label,
                "client": reading.__dict__,
                "binding": dict(binding),
                "named": named.as_facts(),
                "default": default.as_facts(),
            }
        )
    if denied := budget_cause():
        return stopped(denied)
    assessment = assess_sp2_remote_samples(
        readings,
        bindings,
        named_scans,
        default_scans,
        named_range=AddressRange(pool.lease_start, pool.lease_end),
        expected_mask=pool.netmask,
        expected_gateway=pool.gateway,
        expected_dns=pool.dns_server,
        expected_capacity=pool.max_users,
    )
    assessment.facts.update(facts)
    assessment.limitations.append("private_candidate_not_public_support")
    return assessment


def _sp2_remote_terminal_state_complete(
    server: Mapping[str, Any],
    client: ClientReading,
    binding: Mapping[str, object],
    pool: ConfigureServerDhcpPool,
) -> bool:
    """Require the final physical pool, DHCP mode and usable client binding."""
    gateways = binding.get("gateway_reads")
    observed_gateways = (
        [
            item.get("value")
            for item in gateways
            if isinstance(item, Mapping)
            and item.get("api") is True
            and item.get("error") == ""
        ]
        if isinstance(gateways, list)
        else []
    )
    return bool(
        not _sp2_remote_physical_policy(server, pool, True)
        and client.observed
        and client.mode is True
        and normalized_mac(client.mac)
        and AddressRange(pool.lease_start, pool.lease_end).contains(client.ipv4)
        and client.netmask == pool.netmask
        and binding.get("device") == client.client
        and binding.get("found") is True
        and binding.get("port_found") is True
        and binding.get("error") == ""
        and binding.get("ipv4") == client.ipv4
        and binding.get("netmask") == client.netmask
        and observed_gateways
        and all(value == pool.gateway for value in observed_gateways)
        and binding.get("dns_api") is True
        and binding.get("dns_error") == ""
        and binding.get("dns_server") == pool.dns_server
    )


def run_sp2_remote_relay(execution: Execution) -> None:
    """Run e3 under the existing campaign ledger, terminal and owned cleanup."""
    contract = execution.product_contract
    boundaries = execution.run.boundaries
    if contract is None or boundaries.native_product_runtimes is None:
        execution.stop("sp2_remote_contract_or_runtime_absent")
        return
    mismatch = _sp2_remote_contract_mismatch(execution, contract)
    if mismatch:
        execution.stop(mismatch)
        return

    def terminal() -> None:
        ids = ("M-SP2-REMOTE-FINAL",)
        if not execution.begin_terminal(ids, "SP2_REMOTE_FINAL"):
            return
        with execution.procedure(ids):
            runtime = boundaries.native_product_runtimes(
                execution.bound, contract.inventory
            ).configuration
            capture = getattr(runtime, "capture_routed_text", None)
            with execution.ledger.purpose_of("sp2:remote:final:routers"):
                routers = (
                    list(
                        capture(
                            SP2_REMOTE_ROUTERS,
                            sample_calls=SP1_CAPTURE_SAMPLE_CALLS,
                            deadline_seconds=SP1_CAPTURE_DEADLINE_SECONDS,
                        )
                    )
                    if callable(capture)
                    else []
                )
            server = _sp2_remote_snapshot(execution, "terminal")
            client = _sp2_remote_client(execution, "terminal")
            binding = read_client_binding(execution, SP2_REMOTE_CLIENT, "terminal")
            [pool] = [
                action
                for action in contract.service_plan.actions
                if isinstance(action, ConfigureServerDhcpPool)
            ]
            state_complete = _sp2_remote_terminal_state_complete(
                server, client, binding, pool
            )
            complete = (
                terminal_router_rows_complete(routers, SP2_REMOTE_ROUTERS)
                and state_complete
            )
            execution.conclude(
                ids[0],
                Assessment(
                    MeasurementConclusion.SUPPORTED_IN_SAMPLE
                    if complete
                    else MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "routers": routers,
                        "server": server,
                        "client": client.__dict__,
                        "binding": dict(binding),
                        "state_complete": state_complete,
                        "complete": complete,
                    },
                    causes=[] if complete else ["sp2_remote_terminal_incomplete"],
                    limitations=["terminal_inventory_is_not_product_acceptance"],
                ),
            )
        execution.finish("SP2_REMOTE_FINAL")

    execution.register_terminal(("M-SP2-REMOTE-FINAL",), "SP2_REMOTE_FINAL", terminal)
    if not diagnostic_start(execution):
        return
    ids = ("M-SP2-REMOTE-POOL",)
    if not execution.selected("SP2-remote") or not execution.begin(
        ids, "SP2_REMOTE_PRODUCT"
    ):
        return
    product_operations = execution.definition.experiment(ids[0]).planned_operations
    with execution.ledger.ordinary_limit(
        operations=product_operations, leave_seconds=180
    ):
        with execution.procedure(ids):
            assessment = _sp2_remote_product(execution, contract)
            execution.conclude(ids[0], assessment)
    execution.finish("SP2_REMOTE_PRODUCT")
