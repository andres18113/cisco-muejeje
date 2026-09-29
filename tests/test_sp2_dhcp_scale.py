"""SP-2 SP2-06: native local plus relayed named DHCP at about 2 to 1000 clients.

Real: the planner and compilers, admission, the E5 endpoint runtime, the E6
runtime with its grouped lease verifier, the applicator and the durable
record store, all over the Node engine. Substituted, explicitly: router E5
effects are recorded as applied and routed readiness is rendered from the
compiled plan. `dhcp_client_pools` tells the engine which pool answers each
client, so nothing here is native selection, relay or lease capacity. The
measurements are offline orchestration costs only.
"""

from __future__ import annotations

import json
import tracemalloc
from pathlib import Path
from time import perf_counter

import pytest
from native_dhcp_product_flow import run_native_product
from sp2_mixed_fixture import compose_mixed, mixed_dhcp_payload, mixed_records
from test_sp1_routed_scale import _PlanRouters, _ScaleConfigurationRuntime

from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServiceVerificationKind,
)
from packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    candidate_capability_adapter,
)
from tests.service_qualification_engine import (
    FORWARDING_ROWS,
    NodeEngine,
    NodeEngineTransport,
    require_node,
)

#: (sites, users per branch): one native HQ client plus relayed branches,
#: giving about 2, 20, 200 and 1000 constructed clients.
SIZES = {2: (2, 1), 20: (5, 5), 200: (5, 50), 1000: (5, 249)}
STATE_SAMPLES = 3


class _CountingTransport(NodeEngineTransport):
    """Count every dispatched script and the grouped lease scans among them."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self.dispatches = 0
        self.group_scans = 0

    def dispatch_and_wait(self, js_code, timeout):
        self.dispatches += 1
        if "var group=" in js_code:
            self.group_scans += 1
        return super().dispatch_and_wait(js_code, timeout)

    def send_and_wait(self, js_code, timeout):
        self.dispatches += 1
        return super().send_and_wait(js_code, timeout)


@pytest.mark.parametrize("target", sorted(SIZES))
def test_mixed_dhcp_scale_is_grouped_and_complete(tmp_path: Path, target):
    """One group scan per service and sample; every client kept and verified."""
    require_node()
    sites, users = SIZES[target]
    payload, _ids = mixed_dhcp_payload(sites=sites, users=users, hq_users=1)
    plans = compose_mixed(payload, mixed_records())
    assert plans.services is not None, plans.composition.issues
    physical = {
        item.segment_id: item.effective_pool_name
        for item in plans.services.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    leases = [
        item
        for item in plans.services.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    ]
    services = {item.service_id for item in leases}
    segment_of = {item.id: item.segment_id for item in plans.services.services}
    clients = len(leases)
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled_candidate",
        dhcp_native_max_behavior="resize_candidate",
        dhcp_mode_acquires=True,
        dhcp_retry_on_server_enable=True,
        stp_rows=FORWARDING_ROWS,
        terminals=True,
    )
    try:
        # Too large for the engine's command line at scale.
        engine.configure(
            dhcp_client_pools={
                item.client_device_name: physical[segment_of[item.service_id]]
                for item in leases
            }
        )
        for device in plans.composition.topology.devices:
            engine.seed_device(device.name, device.model)
        transport = _CountingTransport(engine)
        routed = _ScaleConfigurationRuntime(targets=plans.inventory)
        routed.routers = _PlanRouters(plans.configuration)
        tracemalloc.start()
        started = perf_counter()
        result = run_native_product(
            tmp_path,
            plans,
            EnterpriseIntent.model_validate(payload),
            transport,
            run_id=f"sp2-scale-{target}",
            capability_catalog=lambda _version: mixed_records(),
            state_samples=STATE_SAMPLES,
            readiness=routed,
            device_capability_catalog=candidate_capability_adapter(
                "9.0.1.0858",
                {"1941": ["supports_dhcp_relay"], "2911": ["supports_dhcp_relay"]},
                label="SP2-SCALE-TEST",
            ),
        )
        elapsed = perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        engine.close()

    assert result.service_result is not None, (
        result.refusal_code,
        result.blocked_reason,
    )
    rows = {
        item.expectation_id: item for item in result.service_result.verification_results
    }
    assert all(rows[item.id].status.value == "verified" for item in leases), sorted(
        {rows[item.id].cause for item in leases}
    )
    # Scan cost follows services and samples, never clients.
    assert transport.group_scans <= len(services) * STATE_SAMPLES
    assert len(result.clients) == clients
    response_bytes = len(json.dumps(result.compact_summary()))
    record_bytes = Path(result.record_path).stat().st_size
    print(
        f"\nSP2-SCALE clients={clients} services={len(services)} "
        f"group_scans={transport.group_scans} dispatches={transport.dispatches} "
        f"dispatches_per_client={transport.dispatches / clients:.1f} "
        f"response_bytes={response_bytes} record_bytes={record_bytes} "
        f"seconds={elapsed:.2f} peak_mib={peak / 2**20:.1f}"
    )
    if clients >= 20:
        assert transport.dispatches / clients < 20
        assert response_bytes / clients < 12_000
        assert record_bytes / clients < 40_000
