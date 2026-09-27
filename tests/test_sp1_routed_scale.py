"""SP-1 SP1-06: routed DNS/HTTP at 2, 20, 200 and 1000 clients, measured.

Real: the planner and compilers (clients over several sites, VLANs and
distribution layers), admission and routed derivation, the readiness plan,
the gate with its access, continuity and routed rules, the request order, the
applicator and the durable record store. Substituted, explicitly: the E5 and
E6 runtimes at their ports. Router reads are rendered as IOS text from the
compiled plan and parsed by the production reader, so the routed rule decides
from parsed tables; E5 and E6 read-backs answer VERIFIED because their own
verifiers are tested elsewhere and are not what scales here.

The measurements are offline orchestration costs, never Packet Tracer
capacity or latency.
"""

from __future__ import annotations

import ipaddress
import json
import tracemalloc
from pathlib import Path
from time import perf_counter

import pytest
from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    EndpointObserver,
    IsolationPreflight,
    ManifestStore,
    RecordingConfigurationRuntime,
    RecordingServiceRuntime,
)
from sp1_routed_fixture import compose, topology_payload, with_services

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    MAX_CLIENT_CHECK_ROWS,
    ServiceStageRuntimes,
    TransportSelection,
    apply_enterprise_services,
)
from packet_tracer_mcp.domain.enterprise.models.routed_forwarding import (
    CONFIRMED_UNIQUE_IDENTITY,
    RoutedForwardingObservation,
    RoutedForwardingRound,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
)
from packet_tracer_mcp.domain.enterprise.services.trunk_continuity import (
    TrunkContinuityObservation,
    TrunkContinuityRound,
    TrunkPortReading,
    TrunkSwitchReading,
)
from packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    candidate_capability_adapter,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    _routed_reading,
)
from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    OperationalQueryId,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

CANDIDATES = {"1941": ["supports_static_routes"], "2911": ["supports_static_routes"]}
#: (sites, users per branch) giving about 2, 20, 200 and 1000 clients; HQ
#: keeps one user so the inter-VLAN family is always present.
SIZES = {2: (3, 1), 20: (3, 10), 200: (5, 50), 1000: (5, 249)}


class _PlanRouters:
    """Router state rendered from the compiled plan, read as IOS text."""

    def __init__(self, plan) -> None:
        self.interfaces: dict[str, dict[str, str]] = {}
        self.routes: dict[str, list[tuple[str, str]]] = {}
        for action in plan.actions:
            kind = action.action_type.value
            if kind == "configure_routed_interface":
                self.interfaces.setdefault(action.device_name, {})[action.interface] = (
                    f"{action.ipv4}/{action.prefix}"
                )
            elif kind == "configure_subinterface":
                self.interfaces.setdefault(action.device_name, {})[
                    f"{action.parent_interface}.{action.vlan_id}"
                ] = f"{action.ipv4}/{action.prefix}"
            elif kind == "configure_static_route":
                self.routes.setdefault(action.device_name, []).append(
                    (f"{action.network}/{action.prefix}", action.next_hop)
                )

    def reading(self, name: str):
        brief = ["Interface  IP-Address  OK? Method Status  Protocol"]
        table = ["Gateway of last resort is not set", ""]
        for interface, value in sorted(self.interfaces.get(name, {}).items()):
            address = ipaddress.ip_interface(value)
            brief.append(f"{interface} {address.ip} YES manual up up")
            table.append(
                f"C       {address.network} is directly connected, {interface}"
            )
            table.append(f"L       {address.ip}/32 is directly connected, {interface}")
        for network, hop in self.routes.get(name, ()):
            table.append(f"S       {network} [1/0] via {hop}")

        def result(query, text):
            return IosCommandResult(
                device_name=name,
                query_id=query,
                executed=True,
                output="\n".join(text),
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name=name,
                device_identity_provenance=CONFIRMED_UNIQUE_IDENTITY,
            )

        return _routed_reading(
            name,
            result(OperationalQueryId.SHOW_IP_INTERFACE_BRIEF, brief),
            result(OperationalQueryId.SHOW_IP_ROUTE, table),
            channel_calls=2,
            exhausted=False,
            after_deadline=False,
        )


class _ScaleConfigurationRuntime(RecordingConfigurationRuntime):
    """The recording E5 runtime plus continuity and routed observers."""

    routers: _PlanRouters | None = None
    routed_episodes: int = 0
    router_reads: int = 0
    continuity_episodes: int = 0

    def observe_trunk_continuity(self, switches, vlan_id, *, settled, **bounds):
        self.continuity_episodes += 1
        readings = tuple(
            TrunkSwitchReading(
                switch_name=name,
                executed=True,
                fresh_output_observed=True,
                output_complete=True,
                observed_device_name=name,
                device_identity_provenance=CONFIRMED_UNIQUE_IDENTITY,
                ports=tuple(
                    TrunkPortReading(
                        interface=port,
                        matches=1,
                        status="trunking",
                        allowed_vlans=(vlan_id,),
                        active_vlans=(vlan_id,),
                        forwarding_vlans=(vlan_id,),
                    )
                    for port in ports
                ),
            )
            for name, ports in switches
        )
        round_ = TrunkContinuityRound(
            index=0, elapsed_ms=0, readings=readings, complete=True
        )
        return TrunkContinuityObservation(
            vlan_id=vlan_id,
            switch_names=tuple(name for name, _ in switches),
            rounds=(round_,),
            deadline_seconds=bounds["deadline_seconds"],
            episode_end_reason="required_pairs_joined"
            if settled(round_)
            else "deadline",
        )

    def observe_routed_forwarding(self, devices, *, settled, **bounds):
        self.routed_episodes += 1
        self.router_reads += len(devices)
        round_ = RoutedForwardingRound(
            index=0,
            elapsed_ms=0,
            readings=tuple(self.routers.reading(name) for name in devices),
            complete=True,
        )
        return RoutedForwardingObservation(
            device_names=tuple(devices),
            rounds=(round_,),
            deadline_seconds=bounds["deadline_seconds"],
            episode_end_reason=(
                "required_paths_forwarding" if settled(round_) else "deadline"
            ),
        )


@pytest.fixture(scope="module")
def workloads():
    """Compose every size once; composition is not what is being measured."""
    built = {}
    for target, (sites, users) in SIZES.items():
        base = topology_payload(
            sites=sites, users=users, hq_users=1, address_space="10.0.0.0/14"
        )
        payload = with_services(base, compose(base, services=False))
        built[target] = (payload, compose(payload))
    return built


@pytest.mark.parametrize("target", sorted(SIZES))
def test_routed_scale_is_linear_and_complete(tmp_path: Path, workloads, target):
    """One routed episode per segment pair, one request per client, all kept."""
    payload, plans = workloads[target]
    clients = len(plans.services.services[0].client_device_ids)
    configuration = _ScaleConfigurationRuntime(targets=plans.inventory)
    configuration.routers = _PlanRouters(plans.configuration)
    services = RecordingServiceRuntime(targets=plans.inventory)
    tracemalloc.start()
    started = perf_counter()
    result = apply_enterprise_services(
        json.dumps(payload),
        deployment_id=DEPLOYMENT_ID,
        packet_tracer_version=BACKEND_VERSION,
        runtimes=ServiceStageRuntimes(configuration=configuration, services=services),
        manifest_store=ManifestStore(manifest=plans.manifest),
        record_store=ServiceRunRecordStore(tmp_path),
        import_preflight=IsolationPreflight(),
        environment_fingerprint=FINGERPRINT,
        transport_selection=TransportSelection(channel="file"),
        endpoint_observer=EndpointObserver(address=""),
        source_tree=SourceTreeIdentity(sha="test-source", dirty=True),
        device_capability_catalog=candidate_capability_adapter(
            BACKEND_VERSION, CANDIDATES, label="sp1-scale"
        ),
    )
    elapsed = perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result.status.value == "verified", result.blocked_reason
    rows = result.operational_readiness
    routed = [row for row in rows if row.get("kind") == "routed_forwarding"]
    segments = {(row["client_segment_id"], row["host_segment_id"]) for row in routed}
    # Observation cost follows the topology: one episode per segment pair.
    assert configuration.routed_episodes == len(routed) == len(segments)
    assert configuration.router_reads == sum(len(row["device_ids"]) for row in routed)
    # Every selected client: one row set, one HTTP-by-IP request, all verified.
    assert len(result.clients) == clients
    fetches = [item for item in services.verified if "/verify-http-ip/" in item]
    assert len(fetches) == clients
    rows_per_client = (
        sum(
            len(check_result.checks)
            for client in result.clients
            for check_result in client.results.values()
        )
        / clients
    )
    assert rows_per_client * clients <= MAX_CLIENT_CHECK_ROWS
    response_bytes = len(json.dumps(result.compact_summary()))
    record_bytes = Path(result.record_path).stat().st_size
    print(
        f"\nSP1-SCALE clients={clients} routed_groups={len(routed)} "
        f"router_reads={configuration.router_reads} "
        f"continuity={configuration.continuity_episodes} "
        f"rows_per_client={rows_per_client:.1f} response_bytes={response_bytes} "
        f"record_bytes={record_bytes} seconds={elapsed:.2f} peak_mib={peak / 2**20:.1f}"
    )
    # Bounded, per-client cost: no quadratic evidence growth. Small runs are
    # dominated by the fixed plan evidence, so the per-client bound starts at
    # twenty clients (measured: about 9.8 KB and 31 KB per client at 997).
    if clients >= 20:
        assert response_bytes / clients < 12_000
        assert record_bytes / clients < 40_000
