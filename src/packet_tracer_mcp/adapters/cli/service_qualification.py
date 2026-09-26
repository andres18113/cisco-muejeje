"""Operator entry point for one governed Server-PT qualification stage.

Translation and composition only. The adapter turns arguments into one
`QualificationRequest`, composes the production boundaries and prints the
coordinator's summary as JSON. It decides nothing: every refusal comes from the
domain rule or from the coordinator, through the same path the offline tests
drive.

Nothing runs by default. Without `--execute` the adapter refuses before it
reads anything. Without `PT_MCP_GOVERNED_ROOT` it refuses before it composes
anything. Building the production boundaries performs no I/O: the bridge is
started only when the coordinator opens the authorized channel, after local
admission. Under pytest the real import-isolation preflight answers
`TEST_PROCESS`, so the production wiring refuses before any channel exists.

The authorization values come from a reviewer's separate, stage- and
SHA-specific LIVE authorization. This adapter never invents one, and
`docs/qa/server-services-qualification.md` holds the template. No raw
JavaScript, IOS or bridge command is accepted from the operator.

Budget note: the production service runtime polls with an interval equal to
its HTTP timeout, so one fetch performs at most two inspections. The
coordinator therefore admits a fetch only when four operations remain outside
the reserve, which keeps the owned client's release inside the budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...application.ports.service_qualification import OpenedTransport
from ...application.use_cases.apply_enterprise_services import ServiceStageRuntimes
from ...application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from ...application.use_cases.compile_services import compile_enterprise_services
from ...application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from ...application.use_cases.plan_enterprise_hardware import capability_catalog_for
from ...application.use_cases.qualify_server_services import (
    CampaignQualificationAuthority,
    IsolationObservation,
    LedgeredTransport,
    Q3ProductContract,
    QualificationBoundaries,
    QualificationCancelled,
    QualificationResult,
    RuntimeIdentity,
    qualify_server_services,
)
from ...application.use_cases.server_pt_campaign import (
    DHCP_AUTONOMY_CAMPAIGN,
    DHCP_FASTLOOP_CAMPAIGN,
    source_authority_findings,
)
from ...application.use_cases.server_pt_campaign_ledger import (
    ledger_record_findings,
    phase_record_name,
)
from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.configuration import ConfigurationPolicy
from ...domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from ...domain.enterprise.models.deployment import (
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.service_plan import (
    CapabilityProvenance,
    ClientOperationCapability,
    NativeDhcpPolicyScope,
    ServiceActionType,
    ServiceCapabilityRecords,
    ServiceType,
    ServiceVerificationKind,
)
from ...domain.enterprise.models.service_qualification import (
    D_WEB_INSPECTION_SCHEDULE,
    D_WEB_LATE_READ_OFFSET,
    D_WEB_PING_INSPECTIONS,
    Q3_DNS_IPV4,
    Q3_FL_STAGES,
    Q3_GATEWAY_IPV4,
    Q3_NATIVE_STAGES,
    Q3_PC1,
    Q3_PC2,
    Q3_POOL,
    Q3_SERVER,
    Q3_SERVER_IPV4,
    Q3_SWITCH,
    ExecutionMode,
    QualificationAuthorization,
    QualificationRecord,
    QualificationRequest,
    QualificationStage,
    RefusalKind,
    RefusalSubject,
    RepositoryIdentity,
    StageDefinition,
    refusal,
    stage_definition,
)
from ...domain.enterprise.models.service_run_record import generate_run_id
from ...domain.enterprise.services.service_policy import derive_service_policy
from ...domain.enterprise.services.topology_identity import stamp_topology_hashes
from ...domain.models.plans import DevicePlan, LinkPlan
from ...infrastructure.catalog.devices import ALL_MODELS
from ...infrastructure.catalog.dhcp_native_default_transitions import (
    WHOLE_CONFIGURE_PC_IP,
    admitted_native_default_transitions,
)
from ...infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from ...infrastructure.catalog.measured_port_inventories import (
    backend_verified_port_inventory,
)
from ...infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)
from ...infrastructure.execution.endpoint_address_observer import (
    PacketTracerEndpointAddressObserver,
)
from ...infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)
from ...infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from ...infrastructure.execution.file_bridge import FileBridge
from ...infrastructure.execution.forwarding_probe import (
    ForwardingProbeExecutor,
    forwarding_probe_evidence,
)
from ...infrastructure.execution.import_isolation_preflight import (
    PRODUCTION_NAMESPACE,
    ImportIsolationPreflight,
    governed_root_from_env,
)
from ...infrastructure.execution.live_bridge import PacketTracerHttpTransport
from ...infrastructure.execution.packet_tracer_physical_runtime import (
    PacketTracerPhysicalTopologyRuntime,
)
from ...infrastructure.execution.service_environment import ServiceEnvironmentReader
from ...infrastructure.execution.service_qualification_lifecycle import (
    PacketTracerDiagnosticLifecycleReader,
)
from ...infrastructure.execution.service_qualification_probes import (
    PacketTracerQualificationProbes,
)
from ...infrastructure.execution.source_preflight import GitSourceReader
from ...infrastructure.execution.typed_ping import TypedPingExecutor
from ...infrastructure.persistence.campaign_coordination import (
    FileCampaignCoordinator,
)
from ...infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from ...infrastructure.persistence.service_qualification_store import (
    QualificationRecordStore,
)
from ...infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)
from .server_pt_campaign_archive import archive_or_stop, ledger_admit, ledger_result

#: Service runtime timings for a qualification fetch; see the module docstring.
HTTP_TIMEOUT_SECONDS = 8.0
#: Physical runtime timeouts. The finalization time reserve covers them.
MUTATION_TIMEOUT_SECONDS = 15.0
OBSERVATION_TIMEOUT_SECONDS = 10.0
RECORD_DIRECTORY = ("data", "services", "qualification")
Q3_PACKET_TRACER_BUILD = "9.0.1.0858"

_Q3_SERVER_ID = "endpoint/q3/default/server/001"
_Q3_PC1_ID = "endpoint/q3/default/user_pc/001"
_Q3_PC2_ID = "endpoint/q3/default/user_pc/002"
_Q3_SWITCH_ID = "sw-acc-q3-default-01"
_Q3_RUNTIME_NAMES = {
    _Q3_SERVER_ID: Q3_SERVER,
    _Q3_PC1_ID: Q3_PC1,
    _Q3_PC2_ID: Q3_PC2,
    _Q3_SWITCH_ID: Q3_SWITCH,
}
_Q3_SWITCH_PORTS = {
    _Q3_SERVER_ID: "FastEthernet0/1",
    _Q3_PC1_ID: "FastEthernet0/2",
    _Q3_PC2_ID: "FastEthernet0/3",
}


class _Q3HardwareCatalog(EnterpriseCapabilityAdapter):
    """Keep real catalog evidence while selecting the work-order's 2960 fixture."""

    def hardware_candidates(self, category, packet_tracer_version=None):
        candidates = super().hardware_candidates(category, packet_tracer_version)
        if category != "switch":
            return candidates
        return [item for item in candidates if item.model == "2960-24TT"]


def _q3_intent(max_users: int = 1) -> EnterpriseIntent:
    """Return the exact one-segment product intent the Q3 fixture measures.

    `max_users` is the intended pool's capacity. Q3 and Q3-FL-C1 compose one
    user; Q3-FL-C2 composes two so one row and a full table differ.
    """
    return EnterpriseIntent.model_validate(
        {
            "name": "MCP-E6Q",
            "address_space": "192.0.2.0/24",
            "sites": [
                {
                    "name": "Q3",
                    "type": "hq",
                    "address_block": "192.0.2.0/24",
                    "segments": [
                        {
                            "role": "data",
                            "hosts": 4,
                            "dhcp": True,
                            "subnet": "192.0.2.0/24",
                            "gateway": Q3_GATEWAY_IPV4,
                        }
                    ],
                    "endpoints": [
                        {
                            "role": "user_pc",
                            "count": 2,
                            "addressing_preference": "dhcp",
                            "segment_role": "data",
                        },
                        {
                            "role": "server",
                            "count": 1,
                            "addressing_preference": "static",
                            "segment_role": "data",
                            "metadata": {"ipv4": Q3_SERVER_IPV4},
                        },
                    ],
                    "services": [
                        {
                            "name": "q3-dhcp",
                            "service_type": "dhcp",
                            "host_device_id": _Q3_SERVER_ID,
                            "segment_id": "q3-data",
                            "client_device_ids": [_Q3_PC1_ID, _Q3_PC2_ID],
                            "dhcp_pool": {
                                "interface": "FastEthernet0",
                                "pool_name": Q3_POOL,
                                "start_offset": 99,
                                "max_users": max_users,
                            },
                        }
                    ],
                }
            ],
        }
    )


def _q3_service_capabilities(build: str):
    """Return a private candidate copy; never mutate the product catalog."""
    records = dict(packet_tracer_service_capabilities(build))
    server_key = f"Server-PT:{ServiceType.DHCP.value}"
    profile = records[server_key]
    records[server_key] = profile.model_copy(
        update={
            "application_support": CapabilityStatus.SUPPORTED,
            "direct_readback_support": CapabilityStatus.SUPPORTED,
            "behavioral_verification_support": CapabilityStatus.SUPPORTED,
            "action_application_support": {
                ServiceActionType.ENABLE_SERVER_DHCP.value: CapabilityStatus.SUPPORTED,
                ServiceActionType.CONFIGURE_SERVER_DHCP_POOL.value: (
                    CapabilityStatus.SUPPORTED
                ),
            },
        }
    )
    for model, operation in (
        ("PC-PT", ServiceActionType.ACQUIRE_DHCP_LEASE.value),
        ("PC-PT", ServiceVerificationKind.ENDPOINT_DHCP_MODE.value),
        ("PC-PT", ServiceVerificationKind.DHCP_LEASE.value),
        ("Server-PT", ServiceVerificationKind.DHCP_SERVER_STATE.value),
        ("Server-PT", ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED.value),
    ):
        key = f"{model}:{operation}"
        records[key] = records[key].model_copy(
            update={"support": CapabilityStatus.SUPPORTED}
        )
    return records


def _native_candidate_capabilities(build: str):
    """Private exact-build product hypothesis; explicit acquisition stays UNKNOWN."""
    if build != Q3_PACKET_TRACER_BUILD:
        raise ValueError("native DHCP candidate is not bound to this build")
    records = dict(packet_tracer_service_capabilities(build))
    native_key = "Server-PT:dhcp_native_default_binding"
    records[native_key] = ClientOperationCapability(
        key=native_key,
        model="Server-PT",
        operation="dhcp_native_default_binding",
        support=CapabilityStatus.SUPPORTED,
        provenance=CapabilityProvenance.RECORDED_RUN,
        source=(
            "Experimental candidate extrapolated from "
            "SERVER-PT-DHCP-AUTONOMOUS-02/e5 physical serverPool attribution; "
            "capacity and shifted policies unmeasured"
        ),
        packet_tracer_version=build,
        build=build,
        executed_sha="04f5337eef67f0c850e057537ce80757e3aa73b1",
        transport="file",
        run_id="2026-09-26T00-30-30Z-f961bd3d",
        native_policy_scope=NativeDhcpPolicyScope(
            network="192.0.2.0",
            netmask="255.255.255.0",
            gateway="192.0.2.1",
            dns_server="192.0.2.10",
            first_lease="192.0.2.2",
            last_lease="192.0.2.254",
            max_users=16,
            max_exclusion_ranges=16,
        ),
    )
    key = f"Server-PT:{ServiceType.DHCP.value}"
    profile = records[key]
    records[key] = profile.model_copy(
        update={
            "application_support": CapabilityStatus.SUPPORTED,
            "direct_readback_support": CapabilityStatus.SUPPORTED,
            "behavioral_verification_support": CapabilityStatus.SUPPORTED,
            "action_application_support": {
                ServiceActionType.ENABLE_SERVER_DHCP.value: CapabilityStatus.SUPPORTED,
                ServiceActionType.CONFIGURE_SERVER_DHCP_POOL.value: (
                    CapabilityStatus.SUPPORTED
                ),
            },
            "source": "experimental candidate from dhcp-autonomy-02/e1-e5; product unqualified",
        }
    )
    for model, operation in (
        ("PC-PT", ServiceVerificationKind.ENDPOINT_DHCP_MODE.value),
        ("PC-PT", ServiceVerificationKind.DHCP_LEASE.value),
        ("Server-PT", ServiceVerificationKind.DHCP_SERVER_STATE.value),
        ("Server-PT", ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED.value),
    ):
        operation_key = f"{model}:{operation}"
        records[operation_key] = records[operation_key].model_copy(
            update={
                "support": CapabilityStatus.SUPPORTED,
                "source": "experimental state reader candidate; not product LIVE evidence",
            }
        )
    return records


def q3_product_contract(build: str, run_id: str) -> Q3ProductContract:
    """Compose real E4/E5/E6 plans and bind them to the exact Q3 names/ports."""
    return dhcp_product_contract(build, run_id, 1)


def _native_dhcp_http_intent(
    selected_count: int = 1, start_offset: int = 99
) -> EnterpriseIntent:
    """Select owned clients and a native binding without a named request."""
    if selected_count not in {1, 2}:
        raise ValueError("The native product fixture has one or two clients.")
    payload = _q3_intent(1).model_dump(mode="json")
    services = payload["sites"][0]["services"]
    dhcp = services[0]
    selected = [_Q3_PC1_ID, _Q3_PC2_ID][:selected_count]
    dhcp["client_device_ids"] = selected
    dhcp["verification_mode"] = "state_only"
    dhcp["dhcp_pool"].pop("pool_name")
    dhcp["dhcp_pool"]["dns_server"] = Q3_DNS_IPV4
    dhcp["dhcp_pool"]["max_users"] = selected_count
    dhcp["dhcp_pool"]["start_offset"] = start_offset
    services.append(
        {
            "name": "q3-native-http",
            "service_type": "http",
            "host_device_id": _Q3_SERVER_ID,
            "client_device_ids": selected,
            "http_content": "MCP-Q3-NATIVE-HTTP-READY",
        }
    )
    return EnterpriseIntent.model_validate(payload)


def native_dhcp_http_product_contract(
    build: str,
    run_id: str,
    *,
    selected_count: int = 1,
    start_offset: int = 99,
) -> Q3ProductContract:
    """Compose the bounded native DHCP plus HTTP candidate fixture."""
    return dhcp_product_contract(
        build,
        run_id,
        selected_count,
        intent_override=_native_dhcp_http_intent(selected_count, start_offset),
        capabilities_override=_native_candidate_capabilities(build),
        preserve_reference_topology=True,
    )


def dhcp_product_contract(
    build: str,
    run_id: str,
    max_users: int,
    *,
    intent_override: EnterpriseIntent | None = None,
    capabilities_override: ServiceCapabilityRecords | None = None,
    preserve_reference_topology: bool = False,
) -> Q3ProductContract:
    """Compose the real plans for the Q3 fixture with a pool of `max_users`."""
    if build != Q3_PACKET_TRACER_BUILD:
        raise ValueError("Q3 has no reviewed native contract for this build.")
    if isinstance(max_users, bool) or not isinstance(max_users, int) or max_users < 1:
        raise ValueError("The intended pool capacity must be a positive integer.")
    intent = intent_override or _q3_intent(max_users)
    catalog = (
        capability_catalog_for(build)
        if preserve_reference_topology
        else _Q3HardwareCatalog()
    )
    base = compose_enterprise_reference(
        intent,
        packet_tracer_version=build,
        capability_catalog=catalog,
    )
    if (
        base.issues
        or base.enterprise is None
        or base.topology is None
        or base.traffic is None
    ):
        raise ValueError("Q3 base composition failed: " + "; ".join(base.issues))
    topology = base.topology.model_copy(deep=True)
    devices = {item.id or item.name: item for item in topology.devices}
    if set(devices) != set(_Q3_RUNTIME_NAMES):
        raise ValueError("Q3 composition did not produce the exact semantic fixtures.")
    if not preserve_reference_topology:
        for identifier, runtime_name in _Q3_RUNTIME_NAMES.items():
            devices[identifier].name = runtime_name
        for link in topology.links:
            a_id = link.device_a_id or link.device_a
            b_id = link.device_b_id or link.device_b
            if _Q3_SWITCH_ID not in {a_id, b_id}:
                raise ValueError("Q3 composition produced a non-access fixture link.")
            endpoint_id = b_id if a_id == _Q3_SWITCH_ID else a_id
            if endpoint_id not in _Q3_SWITCH_PORTS:
                raise ValueError("Q3 composition produced an unexpected endpoint link.")
            if a_id == _Q3_SWITCH_ID:
                link.port_a = _Q3_SWITCH_PORTS[endpoint_id]
                link.port_b = "FastEthernet0"
            else:
                link.port_a = "FastEthernet0"
                link.port_b = _Q3_SWITCH_PORTS[endpoint_id]
            link.device_a = _Q3_RUNTIME_NAMES[a_id]
            link.device_b = _Q3_RUNTIME_NAMES[b_id]
    stamp_topology_hashes(topology)

    ports: dict[str, set[str]] = {identifier: set() for identifier in devices}
    for link in topology.links:
        ports[link.device_a_id].add(link.port_a)
        ports[link.device_b_id].add(link.port_b)
    inventory = tuple(
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=sorted(ports[identifier]),
        )
        for identifier, device in devices.items()
    )
    fingerprint = EnvironmentFingerprint(backend="packet_tracer", backend_version=build)
    manifest = build_deployment_manifest(
        topology,
        list(inventory),
        fingerprint=fingerprint,
        deployment_id=f"qualification/{run_id}",
    )
    derived = derive_service_policy(
        intent,
        base_policy=(
            ConfigurationPolicy()
            if preserve_reference_topology
            else ConfigurationPolicy(dns_server=Q3_DNS_IPV4)
        ),
        enterprise=base.enterprise,
        topology=topology,
    )
    if not derived.is_valid:
        raise ValueError(
            "Q3 service policy failed: "
            + "; ".join(item.message for item in derived.issues)
        )
    device_capabilities = {
        model: catalog.capabilities_for(model, build)
        for model in sorted({item.model for item in topology.devices})
    }
    if any(value is None for value in device_capabilities.values()):
        raise ValueError("Q3 device capability resolution was incomplete.")
    typed_device_capabilities = {
        model: value
        for model, value in device_capabilities.items()
        if value is not None
    }
    configured = compile_enterprise_configuration(
        base.enterprise,
        topology,
        derived.policy,
        typed_device_capabilities,
        deployment_manifest=manifest,
        traffic_by_link=base.traffic.contributions_by_link,
        packet_tracer_version=build,
    )
    if not configured.is_valid or configured.plan is None:
        raise ValueError(
            "Q3 configuration composition failed: "
            + "; ".join(item.message for item in configured.issues)
        )
    service_capabilities = capabilities_override or _q3_service_capabilities(build)
    services = compile_enterprise_services(
        base.enterprise,
        topology,
        configured.plan,
        capabilities=service_capabilities,
    )
    if not services.is_valid or services.plan is None:
        raise ValueError(
            "Q3 service composition failed: "
            + "; ".join(item.message for item in services.issues)
        )
    return Q3ProductContract(
        topology=topology,
        manifest=manifest,
        inventory=inventory,
        configuration_plan=configured.plan,
        service_plan=services.plan,
        device_capabilities=typed_device_capabilities,
        service_capabilities=service_capabilities,
        intent_json=intent.model_dump_json(),
    )


def fixture_plans(
    definition: StageDefinition,
) -> tuple[tuple[DevicePlan, ...], tuple[LinkPlan, ...]]:
    """Resolve a stage's fixtures through the device catalog, never by guessing.

    The PTBuilder device type comes from the catalog category, and every link
    port must be a catalogued port of its model. An unknown model or port
    raises `ValueError`, which the coordinator turns into a refusal before any
    contact.
    """
    devices: list[DevicePlan] = []
    ports: dict[str, set[str]] = {}
    for index, fixture in enumerate(definition.fixtures):
        model = ALL_MODELS.get(fixture.model)
        if model is None:
            raise ValueError(f"Fixture model {fixture.model!r} is not catalogued.")
        ports[fixture.name] = {port.full_name for port in model.ports}
        if (
            definition.stage is QualificationStage.Q3_NATIVE_PRODUCT
            and fixture.model == "IE-2000"
        ):
            observed = backend_verified_port_inventory(
                fixture.model, backend_version=Q3_PACKET_TRACER_BUILD
            )
            if not observed.backend_verified:
                raise ValueError(
                    "Native product switch ports lack exact-build evidence."
                )
            ports[fixture.name] = set(observed.bindable_ports)
        devices.append(
            DevicePlan(
                id=fixture.name,
                name=fixture.name,
                model=model.pt_type,
                category=model.category,
                x=120 + 160 * index,
                y=120,
            )
        )
    links: list[LinkPlan] = []
    for index, link in enumerate(definition.links, start=1):
        for device, port in (
            (link.device_a, link.port_a),
            (link.device_b, link.port_b),
        ):
            if port not in ports.get(device, set()):
                raise ValueError(f"Port {port!r} is not catalogued for {device!r}.")
        links.append(
            LinkPlan(
                id=f"q-link-{index}",
                device_a=link.device_a,
                port_a=link.port_a,
                device_b=link.device_b,
                port_b=link.port_b,
                cable="straight",
            )
        )
    return tuple(devices), tuple(links)


def repository_identity(governed_root: Path) -> RepositoryIdentity:
    """Observe the executing checkout once, naming every read that failed."""
    observed = GitSourceReader().read(governed_root)
    errors = "; ".join(
        item
        for item in (
            observed.error,
            observed.dirty_error,
            observed.upstream_head_error,
            observed.source_tree_error,
        )
        if item
    )
    return RepositoryIdentity(
        branch=observed.branch,
        head=observed.head,
        tree=observed.source_tree,
        clean=None if observed.dirty is None else not observed.dirty,
        upstream=observed.upstream,
        upstream_head=observed.upstream_head,
        error=errors,
    )


def _isolation(governed_root: Path) -> IsolationObservation:
    result = ImportIsolationPreflight(governed_root).ensure_isolated()
    return IsolationObservation(result.isolated, result.state.value, result.detail)


def runtime_identity() -> RuntimeIdentity:
    """Report the interpreter and the loaded package origin of this process."""
    # Read the loaded package; importing it here would create what we audit.
    package = sys.modules.get(PRODUCTION_NAMESPACE)
    return RuntimeIdentity(
        python_executable=sys.executable,
        package_file=str(getattr(package, "__file__", "") or ""),
    )


def _open_transport(channel: str) -> OpenedTransport:
    if channel == "http":
        transport = PacketTracerHttpTransport()
        live = transport.start(wait_for_connection=True, timeout_seconds=8.0)
        return OpenedTransport(
            channel,
            transport,
            live,
            "webview_polling" if live else "webview_not_polling",
        )
    bridge = FileBridge()
    live = bridge.pt_alive()
    return OpenedTransport(
        channel, bridge, live, "heartbeat_fresh" if live else "heartbeat_stale"
    )


def _close_transport(opened: OpenedTransport) -> None:
    stop = getattr(opened.transport, "stop", None)
    if callable(stop):
        stop()


def _no_inventory() -> list[dict]:
    raise RuntimeError("A qualification runtime never enumerates the workspace.")


def _configuration_runtime(
    bound: LedgeredTransport,
    *,
    inventory_rows: tuple[RuntimeConfigurationTarget, ...] | None = None,
) -> PacketTracerEnterpriseConfigurationRuntime:
    return PacketTracerEnterpriseConfigurationRuntime(
        _no_inventory
        if inventory_rows is None
        else lambda: [item.model_dump(mode="json") for item in inventory_rows],
        bound.send,
        bound.send_and_wait,
        # The neutral access-forwarding observer is the only path that reads
        # these; every other waiter keeps the lifecycle helper it had. The
        # sleeper is the ledger's, so a bounded sample can never outlive the
        # phase's remaining time.
        clock=bound.clock,
        sleeper=bound.capped_sleep,
    )


def _service_runtime(
    bound: LedgeredTransport,
    *,
    inventory_rows: tuple[RuntimeConfigurationTarget, ...] | None = None,
) -> PacketTracerEnterpriseServiceRuntime:
    return PacketTracerEnterpriseServiceRuntime(
        _no_inventory
        if inventory_rows is None
        else lambda: [item.model_dump(mode="json") for item in inventory_rows],
        bound.send_and_wait,
        dispatch_and_wait=bound.dispatch_and_wait,
        http_timeout_seconds=HTTP_TIMEOUT_SECONDS,
        convergence_interval_seconds=HTTP_TIMEOUT_SECONDS,
        clock=bound.clock,
        sleeper=bound.capped_sleep,
    )


def _native_product_runtimes(
    bound: LedgeredTransport,
    inventory_rows: tuple[RuntimeConfigurationTarget, ...],
) -> ServiceStageRuntimes:
    """Bind both inner product runtimes to the exact owned fixture inventory."""
    if not inventory_rows:
        raise ValueError("Native product requires a nonempty fixture inventory.")
    return ServiceStageRuntimes(
        configuration=_configuration_runtime(bound, inventory_rows=inventory_rows),
        services=_service_runtime(bound, inventory_rows=inventory_rows),
    )


def _native_product_record_path(record: QualificationRecord | None) -> str:
    """Return the product record a native product measurement names, or "".

    The path is read from the qualification record itself, so the campaign
    seals exactly the file that record cites.
    """
    if record is None:
        return ""
    for item in record.measurements:
        if item.experiment_id == "M-NATIVE-PRODUCT":
            path = item.facts.get("product_record_path")
            return path if isinstance(path, str) else ""
    return ""


def _stop_status(status: dict[str, object], finding: str, exc: Exception) -> None:
    """Stop one phase status and append why, keeping earlier findings."""
    findings = status.get("archive_findings")
    status["outcome"] = "stopped"
    status["archive_findings"] = [
        *(findings if isinstance(findings, list) else []),
        f"{finding}:{type(exc).__name__}",
    ]


def _qualification_sealed(
    store: ServerPtCommissioningStore, attempt: str, sources: Mapping[str, str]
) -> bool:
    """Whether the phase status reloads and every cited record is sealed."""
    try:
        store.load_phase_status(attempt, "qualification")
        sealed = all(
            store.external_source_registered(attempt, label)
            for label, source in sources.items()
            if source
        )
        return sealed and not store.verify_index()
    except (OSError, ValueError):
        return False


def _diagnostic_service_runtime(
    bound: LedgeredTransport, allowance
) -> PacketTracerEnterpriseServiceRuntime:
    """Compose the product web reader with the diagnostic's inspection cadence.

    The public timeout defaults are untouched: only the finite inspection
    schedule, the one bounded late read and the budget reader are added, and
    all three are observation rather than policy.
    """
    return PacketTracerEnterpriseServiceRuntime(
        _no_inventory,
        bound.send_and_wait,
        dispatch_and_wait=bound.dispatch_and_wait,
        http_timeout_seconds=HTTP_TIMEOUT_SECONDS,
        convergence_interval_seconds=HTTP_TIMEOUT_SECONDS,
        clock=bound.clock,
        sleeper=bound.capped_sleep,
        web_inspection_schedule=D_WEB_INSPECTION_SCHEDULE,
        web_late_read_offset=D_WEB_LATE_READ_OFFSET,
        budget_reader=allowance,
    )


class _SerializedForwardingProbe:
    """Run the existing bind-before-ping probe and hand back typed evidence."""

    def __init__(self, executor: ForwardingProbeExecutor) -> None:
        """Wrap one composed executor for this invocation."""
        self._executor = executor

    def probe_once(self, **kwargs) -> Mapping[str, Any]:
        """Probe once and serialize every boundary the executor acquired."""
        return forwarding_probe_evidence(self._executor.probe_once(**kwargs))


def _forwarding_probe(bound: LedgeredTransport) -> _SerializedForwardingProbe:
    """Compose the real probe: documented endpoint getters plus one typed ping.

    `measurement_attempts` is one, because a diagnostic measures once. The
    safe ping timeout stays the executor's own contract and is not
    shortened: what is bounded is how many inspections the poll may spend
    inside that window, because every one of them is a counted operation
    and the stage has to account for all of them in advance. The window is
    spread across them, so a destination that publishes its statistics
    late is still classified from its own output.
    """
    return _SerializedForwardingProbe(
        ForwardingProbeExecutor(
            PacketTracerEndpointAddressObserver(bound.send_and_wait),
            TypedPingExecutor(
                bound.send_and_wait,
                measurement_attempts=1,
                max_inspections=D_WEB_PING_INSPECTIONS,
                clock=bound.clock,
                sleeper=bound.capped_sleep,
            ),
        )
    )


def production_boundaries(governed_root: Path) -> QualificationBoundaries:
    """Compose the LIVE boundaries; constructing them performs no I/O."""
    return QualificationBoundaries(
        execution_mode=ExecutionMode.LIVE,
        isolation=lambda: _isolation(governed_root),
        runtime_identity=runtime_identity,
        repository=lambda: repository_identity(governed_root),
        record_store=QualificationRecordStore(
            governed_root.joinpath(*RECORD_DIRECTORY)
        ),
        open_transport=_open_transport,
        close_transport=_close_transport,
        fixture_plans=fixture_plans,
        build_reader=lambda send_and_wait: ServiceEnvironmentReader(send_and_wait),
        physical_runtime=lambda send_and_wait: PacketTracerPhysicalTopologyRuntime(
            send_and_wait,
            mutation_timeout_seconds=MUTATION_TIMEOUT_SECONDS,
            observation_timeout_seconds=OBSERVATION_TIMEOUT_SECONDS,
        ),
        probes=lambda bound, run_id, nonce: PacketTracerQualificationProbes(
            run_id=run_id,
            nonce=nonce,
            dispatch_and_wait=bound.dispatch_and_wait,
            send=bound.send,
        ),
        configuration_runtime=_configuration_runtime,
        service_runtime=_service_runtime,
        clock=time.monotonic,
        sleep=time.sleep,
        now=lambda: datetime.now(UTC),
        new_run_id=generate_run_id,
        new_nonce=lambda: uuid4().hex,
        q3_product_contract=q3_product_contract,
        q3_required_build=Q3_PACKET_TRACER_BUILD,
        dhcp_product_contract=dhcp_product_contract,
        native_product_contract=lambda build, run_id: native_dhcp_http_product_contract(
            build, run_id, selected_count=2
        ),
        native_product_runtimes=_native_product_runtimes,
        native_product_import_preflight=lambda: ImportIsolationPreflight(governed_root),
        native_product_record_store_factory=lambda: ServiceRunRecordStore(
            governed_root / "data/services/product-qualification"
        ),
        native_product_endpoint_observer=lambda bound: (
            PacketTracerEndpointAddressObserver(bound.send_and_wait)
        ),
        native_default_transitions=admitted_native_default_transitions,
        reviewed_native_default_intervention=WHOLE_CONFIGURE_PC_IP,
        forwarding_probe=_forwarding_probe,
        diagnostic_service_runtime=_diagnostic_service_runtime,
        diagnostic_lifecycle=PacketTracerDiagnosticLifecycleReader().read,
        # Exclusion is taken beside the mailbox, which is what two
        # checkouts share, and never in this checkout's record directory,
        # which neither of them can see from the other.
        campaign_coordinator=FileCampaignCoordinator(),
    )


def _integer(value: str | None) -> Any:
    """Keep a malformed number raw so the domain rule can name it."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stage", default="")
    parser.add_argument("--expected-head", default="")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--channel", default="")
    parser.add_argument("--packet-tracer-build", default="")
    parser.add_argument("--authorization-id")
    parser.add_argument("--authorized-stage")
    parser.add_argument("--authorized-sha")
    parser.add_argument("--authorized-target", action="append")
    parser.add_argument("--authorized-channel")
    parser.add_argument("--authorized-build")
    parser.add_argument("--authorized-max-operations")
    parser.add_argument("--authorized-max-seconds")
    # The diagnostic half of the authority. Every one of these is compared
    # against a value the stage definition or the observed checkout already
    # fixes; none of them is prose and none of them widens anything.
    parser.add_argument("--authorized-profile")
    parser.add_argument("--authorized-profile-version")
    parser.add_argument("--authorized-tree")
    parser.add_argument("--authorized-model", action="append")
    parser.add_argument("--authorized-link", action="append")
    parser.add_argument("--authorized-step", action="append")
    parser.add_argument("--authorized-reserve-operations")
    parser.add_argument("--authorized-process-id")
    parser.add_argument("--authorized-process-path")
    parser.add_argument("--instance-token")
    parser.add_argument("--attempt-id")
    # Each fixed experimental DHCP stage needs its own campaign authority.
    parser.add_argument(
        "--campaign", choices=("dhcp-fastloop", "dhcp-autonomy"), default=""
    )
    parser.add_argument("--charter", default="")
    parser.add_argument("--episode", type=int, default=0)
    return parser


def _request(argv: Sequence[str] | None) -> QualificationRequest:
    return _request_from(_parser().parse_args(argv))


def _request_from(args: argparse.Namespace) -> QualificationRequest:
    named = (
        args.authorization_id,
        args.authorized_stage,
        args.authorized_sha,
        args.authorized_target,
        args.authorized_channel,
        args.authorized_build,
        args.authorized_max_operations,
        args.authorized_max_seconds,
        args.authorized_profile,
        args.authorized_profile_version,
        args.authorized_tree,
        args.authorized_model,
        args.authorized_link,
        args.authorized_step,
        args.authorized_reserve_operations,
        args.authorized_process_id,
        args.authorized_process_path,
        args.instance_token,
        args.attempt_id,
    )
    authorization = None
    if any(item is not None for item in named):
        authorization = QualificationAuthorization(
            authorization_id=args.authorization_id or "",
            stage=args.authorized_stage or "",
            sha=args.authorized_sha or "",
            targets=tuple(args.authorized_target or ()),
            channel=args.authorized_channel or "",
            build=args.authorized_build or "",
            max_operations=_integer(args.authorized_max_operations),
            max_seconds=_integer(args.authorized_max_seconds),
            profile_id=args.authorized_profile or "",
            profile_version=args.authorized_profile_version or "",
            tree=args.authorized_tree or "",
            models=tuple(args.authorized_model or ()),
            links=tuple(args.authorized_link or ()),
            step_ids=tuple(args.authorized_step or ()),
            reserve_operations=_integer(args.authorized_reserve_operations),
            process_id=_integer(args.authorized_process_id),
            process_path=args.authorized_process_path or "",
            instance_token=args.instance_token or "",
            attempt_id=args.attempt_id or "",
        )
    return QualificationRequest(
        execute=bool(args.execute),
        stage=args.stage,
        expected_head=args.expected_head,
        targets=tuple(args.target),
        channel=args.channel,
        packet_tracer_build=args.packet_tracer_build,
        authorization=authorization,
    )


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    boundaries_factory=production_boundaries,
) -> int:
    """Run one stage and return 0 completed, 1 stopped or 2 refused."""
    args = _parser().parse_args(argv)
    request = _request_from(args)
    if not request.execute:
        _print(
            {
                "outcome": "refused",
                "refusals": [
                    refusal(
                        RefusalKind.MISSING,
                        RefusalSubject.EXECUTION,
                        "--execute is required; nothing was read or contacted.",
                    ).model_dump(mode="json")
                ],
            }
        )
        return 2
    governed_root = governed_root_from_env(environ)
    if governed_root is None:
        _print(
            {
                "outcome": "refused",
                "refusals": [
                    refusal(
                        RefusalKind.MISSING,
                        RefusalSubject.GOVERNED_ROOT,
                        "PT_MCP_GOVERNED_ROOT must declare the governed checkout.",
                    ).model_dump(mode="json")
                ],
            }
        )
        return 2
    definition = stage_definition(request.stage)
    capabilities = (
        frozenset(definition.experimental_capabilities)
        if definition is not None
        else frozenset()
    )
    try:
        if args.campaign:
            return _campaign_main(
                request, args, governed_root, boundaries_factory, capabilities
            )
        if definition is not None and definition.stage in (
            *Q3_FL_STAGES,
            *Q3_NATIVE_STAGES,
        ):
            # Experimental DHCP profiles exist only under campaign authority.
            _print({"outcome": "refused", "reason": "stage_requires_its_campaign"})
            return 2
        result = qualify_server_services(
            request,
            boundaries_factory(governed_root),
            experimental_capabilities=capabilities,
        )
    except QualificationCancelled as exc:
        summary: dict[str, Any] = {
            "outcome": "stopped",
            "primary_failure": "cancelled",
        }
        if exc.claim_release is not None:
            summary["claim_release"] = exc.claim_release.model_dump(mode="json")
        _print(summary)
        return 130
    except KeyboardInterrupt:
        _print({"outcome": "stopped", "primary_failure": "cancelled"})
        return 130
    _print(result.compact_summary())
    return result.exit_code


#: The charter digest the DHCP campaign's qualification runs require. A module
#: seam, read at call time, so a test binds its own charter without touching
#: the campaign identity.
DHCP_FASTLOOP_CHARTER_SHA256 = DHCP_FASTLOOP_CAMPAIGN.charter_sha256
DHCP_AUTONOMY_CHARTER_SHA256 = DHCP_AUTONOMY_CAMPAIGN.charter_sha256
_CHARTER_LIMIT = 1024 * 1024
_ATTEMPT_ID = re.compile(r"[0-9a-f]{32}\Z")


def _campaign_refused(reason: str) -> int:
    _print({"outcome": "refused", "reason": reason})
    return 2


def _campaign_status(
    result: QualificationResult | None, *, active_seconds: float, ledger_result: str
) -> dict[str, Any]:
    """Return the qualification status the campaign archive retains.

    Without a result the run was interrupted inside the use case, after it
    may have dispatched effects. Nothing here then claims what happened:
    effects and the workspace baseline are unknown (`None`), which the
    retirement basis reads as an interrupted qualification.
    """
    if result is None:
        return {
            "outcome": "interrupted",
            "stage": "",
            "run_id": "",
            "record_path": "",
            "refusals": [],
            "operations_used": None,
            "active_seconds": round(active_seconds, 3),
            "effects_dispatched": None,
            "workspace_baseline_observed": None,
            "workspace_baseline_empty": None,
            "restoration_proven": False,
            "dirty_state": "",
            "primary_failure": "interrupted",
            "ledger_result": ledger_result,
        }
    record = result.record
    operations = list(record.operations) if record is not None else []
    baseline = dict(record.workspace_baseline) if record is not None else {}
    return {
        "outcome": result.outcome.value if result is not None else "refused",
        "stage": record.stage.value if record is not None else "",
        "run_id": record.run_id if record is not None else "",
        "record_path": result.record_path if result is not None else "",
        "refusals": (
            [item.model_dump(mode="json") for item in result.refusals]
            if result is not None
            else []
        ),
        "operations_used": record.budget.used_operations if record is not None else 0,
        "active_seconds": round(active_seconds, 3),
        # The first effect of any stage is a fixture creation, so a run with
        # no counted creation dispatched nothing into the workspace.
        "effects_dispatched": any(
            item.seq and item.purpose.startswith("create:") for item in operations
        ),
        "workspace_baseline_observed": baseline.get("observed") is True,
        "workspace_baseline_empty": (
            baseline.get("observed") is True
            and baseline.get("semantic_device_count") == 0
            and baseline.get("link_count") == 0
        ),
        "restoration_proven": bool(record.restoration_proven) if record else False,
        "dirty_state": record.dirty_state.value if record is not None else "",
        "primary_failure": record.primary_failure if record is not None else "",
        "ledger_result": ledger_result or "recorded",
    }


def _campaign_main(
    request: QualificationRequest,
    args: argparse.Namespace,
    governed_root: Path,
    boundaries_factory,
    capabilities: frozenset[str],
) -> int:
    """Run one fixed DHCP stage under its exact experimental campaign.

    Every campaign fact is validated before the use case sees anything: the
    charter digest, the stage, the attempt's launch record and process, the
    exact clean checkpoint the episode declared, and the ledger admission of
    this qualification phase. Only then is the one-rule publication waiver
    composed, and only for this attempt. The result, used operations and
    active seconds are recorded whatever the stage concluded, and the full
    record is pinned in the campaign archive by digest.
    """
    if args.campaign == "dhcp-autonomy":
        campaign = DHCP_AUTONOMY_CAMPAIGN
        stages = Q3_NATIVE_STAGES
        charter_sha256 = DHCP_AUTONOMY_CHARTER_SHA256
    else:
        campaign = DHCP_FASTLOOP_CAMPAIGN
        stages = Q3_FL_STAGES
        charter_sha256 = DHCP_FASTLOOP_CHARTER_SHA256
    try:
        charter = Path(args.charter).read_bytes() if args.charter else b""
    except OSError:
        return _campaign_refused("charter_unreadable")
    if (
        not charter
        or len(charter) > _CHARTER_LIMIT
        or hashlib.sha256(charter).hexdigest() != charter_sha256
    ):
        return _campaign_refused("charter_digest_mismatch")
    definition = stage_definition(request.stage)
    if definition is None or definition.stage not in stages:
        return _campaign_refused("stage_not_part_of_the_dhcp_campaign")
    authorization = request.authorization
    if (
        authorization is None
        or not _ATTEMPT_ID.fullmatch(authorization.attempt_id or "")
        or args.episode < 1
    ):
        return _campaign_refused("campaign_attempt_or_episode_invalid")
    attempt = authorization.attempt_id
    store = ServerPtCommissioningStore(governed_root, campaign.campaign_id)
    source = repository_identity(governed_root)
    try:
        if store.index_exists() and store.adopt_ledger_residue(ledger_record_findings):
            raise ValueError("ledger residue unverified")
        if store.verify_index():
            raise ValueError("campaign archive unverified")
        launch = store.load_process_launch(attempt)
    except (OSError, ValueError):
        return _campaign_refused("campaign_launch_unestablished")
    if (
        launch.get("campaign_id") != campaign.campaign_id
        or launch.get("execution_purpose") != campaign.purpose.value
        or launch.get("pid") != authorization.process_id
        or launch.get("process_path") != authorization.process_path
        or not launch.get("process_incarnation")
    ):
        return _campaign_refused("authorization_differs_from_the_campaign_launch")
    if (
        source_authority_findings(campaign, source, None)
        or (source.head, source.tree) != (request.expected_head, authorization.tree)
        or (source.head, source.tree)
        != (launch.get("source_sha"), launch.get("source_tree"))
    ):
        return _campaign_refused("source_differs_from_the_launch_checkpoint")
    findings = ledger_admit(
        store,
        campaign,
        args.episode,
        attempt,
        "qualification",
        definition.budget.max_operations,
        float(definition.budget.max_seconds),
        source=source,
    )
    if findings:
        _print({"outcome": "refused", "reasons": list(findings)})
        return 2
    authority = CampaignQualificationAuthority(
        campaign_id=campaign.campaign_id,
        episode=args.episode,
        admission_record=phase_record_name(
            args.episode, attempt, "qualification", "admission"
        ),
        attempt_id=attempt,
        authorization_id=authorization.authorization_id,
        sha=source.head,
        tree=source.tree,
        process_incarnation=str(launch["process_incarnation"]),
    )
    boundaries = replace(
        boundaries_factory(governed_root), campaign_source_authority=authority
    )
    started = time.monotonic()
    result: QualificationResult | None = None
    try:
        result = qualify_server_services(
            request, boundaries, experimental_capabilities=capabilities
        )
    finally:
        active = time.monotonic() - started
        record = result.record if result is not None else None
        if result is None:
            # No trustworthy count exists: the use case was interrupted after
            # it may have dispatched. The admission stays unsettled, so the
            # ledger keeps charging this phase its whole grant.
            recorded = "unsettled:charged_at_grant"
        else:
            recorded = ledger_result(
                store,
                campaign,
                args.episode,
                attempt,
                "qualification",
                record.budget.used_operations if record is not None else 0,
                active,
                result.outcome.value,
            )
        status = {
            "phase": "qualification",
            "attempt_id": attempt,
            "episode": args.episode,
            "campaign_id": campaign.campaign_id,
            **_campaign_status(result, active_seconds=active, ledger_result=recorded),
        }
        # Seal both records before the status is written, so a sealing
        # failure is part of that status; the product record is the decisive
        # E5/E6 evidence. Every persistence failure stops the phase.
        sources = {
            "product-record": _native_product_record_path(record),
            "qualification-record": result.record_path if result is not None else "",
        }
        for label, source in sources.items():
            if not source:
                continue
            try:
                store.register_external_source(attempt, label, Path(source))
            except (OSError, ValueError) as exc:
                _stop_status(status, f"{label.replace('-', '_')}_unsealed", exc)
        try:
            store.save_phase_status(attempt, "qualification", status)
        except (OSError, ValueError) as exc:
            _stop_status(status, "status_unrecorded", exc)
        archive_or_stop(store, status)
    summary = result.compact_summary()
    summary["campaign"] = {
        "campaign_id": campaign.campaign_id,
        "episode": args.episode,
        "attempt_id": attempt,
        "ledger_result": status.get("ledger_result"),
        "archive_findings": status.get("archive_findings", []),
        "publication_waived_for_this_attempt_only": True,
    }
    _print(summary)
    if result.exit_code == 0 and (
        status.get("outcome") == "stopped"
        or not _qualification_sealed(store, attempt, sources)
    ):
        # An unsealed, unreloadable or unverified archive never reports
        # phase success.
        return 1
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
