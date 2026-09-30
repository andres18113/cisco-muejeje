"""The public route over one Server-PT with native local and named remote pools.

The real A1-E6 use case, E6 runtime and record store run over the Node engine.
`dhcp_client_pools` tells the engine which physical pool answers each client;
that is a scenario setting, so these tests prove composition and evidence
handling, never native selection or relay support.
"""

from __future__ import annotations

import json

import pytest
from native_dhcp_product_flow import run_native_product
from sp2_mixed_fixture import (
    RELAY_BINDING_KEY,
    compose_mixed,
    mixed_dhcp_payload,
    mixed_records,
)
from test_sp1_routed_scale import _PlanRouters, _ScaleConfigurationRuntime

from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    ServiceVerificationKind,
)
from packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    candidate_capability_adapter,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)
from tests.service_qualification_engine import (
    FORWARDING_ROWS,
    NodeEngine,
    NodeEngineTransport,
    require_node,
)

_LEASE = ServiceVerificationKind.DHCP_LEASE


def _relay_candidates():
    # Test candidate: router relay stays UNKNOWN in the default catalog.
    return candidate_capability_adapter(
        "9.0.1.0858",
        {"1941": ["supports_dhcp_relay"], "2911": ["supports_dhcp_relay"]},
        label="SP2-MIXED-TEST",
    )


def _run(
    tmp_path,
    run_id,
    *,
    pools=None,
    transport_factory=None,
    payload=None,
    **engine_config,
):
    require_node()
    if payload is None:
        payload, _ids = mixed_dhcp_payload()
    plans = compose_mixed(payload, mixed_records())
    assert plans.services is not None, plans.composition.issues
    physical = {
        item.segment_id: item.effective_pool_name
        for item in plans.services.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    clients = pools or {
        f"{site}-DEFAULT-PC-0{n}": physical[f"{site.lower()}-data"]
        for site in ("HQ", "BR1", "BR2")
        for n in (1, 2)
    }
    engine = NodeEngine(
        tmp_path,
        dhcp_default_pool="native",
        default_pool_realigns_on_address=True,
        dhcp_native_start_behavior="coupled_candidate",
        dhcp_native_max_behavior="resize_candidate",
        dhcp_mode_acquires=True,
        dhcp_retry_on_server_enable=True,
        dhcp_client_pools=clients,
        stp_rows=FORWARDING_ROWS,
        terminals=True,
        **engine_config,
    )
    try:
        for device in plans.composition.topology.devices:
            engine.seed_device(device.name, device.model)
        transport = (transport_factory or NodeEngineTransport)(engine)
        routed = _ScaleConfigurationRuntime(targets=plans.inventory)
        routed.routers = _PlanRouters(plans.configuration)
        result = run_native_product(
            tmp_path,
            plans,
            EnterpriseIntent.model_validate(payload),
            transport,
            run_id=run_id,
            capability_catalog=lambda _version: mixed_records(),
            # Test candidate: router relay stays UNKNOWN in the default catalog.
            readiness=routed,
            device_capability_catalog=candidate_capability_adapter(
                "9.0.1.0858",
                {"1941": ["supports_dhcp_relay"], "2911": ["supports_dhcp_relay"]},
                label="SP2-MIXED-TEST",
            ),
        )
        snapshot = engine.snapshot()
    finally:
        engine.close()
    return plans, physical, result, (transport if transport_factory else snapshot)


def _leases(plans, rows):
    names = {
        item.id: item.client_device_name
        for item in plans.services.verification_expectations
        if item.kind is _LEASE
    }
    return {
        names[row.expectation_id]: row for row in rows if row.expectation_id in names
    }


def test_mixed_strategies_verify_every_client_in_its_own_physical_pool(tmp_path):
    """Local clients join serverPool, relayed ones their segment's named pool."""
    plans, physical, result, snapshot = _run(tmp_path, "sp2-mixed-positive")

    assert result.service_result is not None, (
        result.refusal_code,
        result.blocked_reason,
    )
    typed = _leases(plans, result.service_result.verification_results)
    assert set(typed) == {
        f"{site}-DEFAULT-PC-0{n}" for site in ("HQ", "BR1", "BR2") for n in (1, 2)
    }
    for name, row in typed.items():
        assert row.status.value == "verified", (name, row.cause)
        assert row.claim_level == "attributed_to_effective_server_pool"
        site = name.split("-")[0].lower()
        assert row.observed["effective_pool_name"] == physical[f"{site}-data"]
    stored = ServiceRunRecordStore(tmp_path).load(result.deployment_id, result.run_id)
    assert {
        name: row.status.value
        for name, row in _leases(
            plans, stored.service_result.verification_results
        ).items()
    } == {name: "verified" for name in typed}
    assert snapshot["dhcp_runs"] == []


def test_a_companion_named_like_the_native_logical_pool_still_verifies(tmp_path):
    """The native logical name is free for a planned companion's physical pool.

    The native service's requested name is only a label; `serverPool` serves
    it. A relayed pool explicitly given that label is a distinct planned
    physical pool, and the pinned process inventory already refuses any
    other pool of that name.
    """
    plans = compose_mixed(mixed_dhcp_payload()[0], mixed_records())
    [native] = [
        item
        for item in plans.services.actions
        if isinstance(item, ConfigureServerDhcpPool)
        and item.effective_pool_name == "serverPool"
    ]
    payload, _ids = mixed_dhcp_payload(pool_names={"br1-data": native.pool_name})

    plans, physical, result, _snapshot = _run(
        tmp_path, "sp2-mixed-logical-name", payload=payload
    )

    assert physical["br1-data"] == native.pool_name
    assert result.service_result is not None, (
        result.refusal_code,
        result.blocked_reason,
    )
    rows = result.service_result.verification_results
    typed = _leases(plans, rows)
    assert {name: row.status.value for name, row in typed.items()} == {
        f"{site}-DEFAULT-PC-0{n}": "verified"
        for site in ("HQ", "BR1", "BR2")
        for n in (1, 2)
    }
    server_state = [
        row
        for row in rows
        if row.expectation_id
        in {
            item.id
            for item in plans.services.verification_expectations
            if item.kind is ServiceVerificationKind.DHCP_SERVER_STATE
        }
    ]
    assert server_state and all(
        row.status.value == "verified" for row in server_state
    ), [(row.expectation_id, row.cause) for row in server_state]


@pytest.mark.parametrize("wrong", ["serverPool", "other_named"])
def test_a_relayed_client_answered_from_a_competing_pool_is_not_verified(
    tmp_path, wrong
):
    """A lease from the wrong physical pool never becomes intended-pool evidence."""
    payload, _ids = mixed_dhcp_payload()
    plans = compose_mixed(payload, mixed_records())
    physical = {
        item.segment_id: item.effective_pool_name
        for item in plans.services.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    clients = {
        f"{site}-DEFAULT-PC-0{n}": physical[f"{site.lower()}-data"]
        for site in ("HQ", "BR1", "BR2")
        for n in (1, 2)
    }
    clients["BR1-DEFAULT-PC-01"] = (
        "serverPool" if wrong == "serverPool" else physical["br2-data"]
    )

    plans, physical, result, _snapshot = _run(
        tmp_path, f"sp2-mixed-wrong-{wrong}", pools=clients
    )

    assert result.service_result is not None
    typed = _leases(plans, result.service_result.verification_results)
    assert typed["BR1-DEFAULT-PC-01"].status.value != "verified"
    assert typed["BR1-DEFAULT-PC-02"].status.value == "verified"
    assert typed["HQ-DEFAULT-PC-01"].status.value == "verified"


class _CompetingRowTransport(NodeEngineTransport):
    """Add one competing-pool row for a chosen client to a group scan answer."""

    def __init__(self, engine, *, client, pool, same_address=False) -> None:
        super().__init__(engine)
        self.client, self.pool, self.same_address = client, pool, same_address
        self.planted = 0

    def dispatch_and_wait(self, js_code, timeout):
        outcome = super().dispatch_and_wait(js_code, timeout)
        if "var group=" not in js_code or not outcome.body:
            return outcome
        payload = json.loads(outcome.body)
        client = next(
            (
                item
                for item in payload.get("clients", ())
                if item.get("device_name") == self.client
            ),
            None,
        )
        competing = payload.get("competing")
        if client is None or not client.get("mac") or not isinstance(competing, list):
            return outcome
        for scan in competing:
            if scan.get("pool_name") == self.pool:
                row = {
                    "ipAddress": client["ipv4"] if self.same_address else "10.99.0.9",
                    "macAddress": client["mac"],
                    "leaseTime": 3600,
                    "port": client["interface"],
                }
                row.update(
                    {
                        key + "_type": "number" if key == "leaseTime" else "string"
                        for key in list(row)
                    }
                )
                # Replace an existing row so this wrong-pool control retains
                # its declared capacity and both observed confirmation indexes.
                entry = next(
                    (
                        item
                        for item in scan["entries"]
                        if item["return_kind"] == "object"
                    ),
                    scan["entries"][0],
                )
                entry.update(return_kind="object", error="", row=row)
                self.planted += 1
        return BridgeDispatchOutcome(
            dispatch=outcome.dispatch,
            result=outcome.result,
            body=json.dumps(payload),
        )


@pytest.mark.parametrize("pool", ["serverPool", "br2"])
def test_a_competing_pool_row_for_a_relayed_client_contradicts_it(tmp_path, pool):
    """The intended row alone is not enough when another pool holds the MAC."""
    payload, _ids = mixed_dhcp_payload()
    plans = compose_mixed(payload, mixed_records())
    physical = {
        item.segment_id: item.effective_pool_name
        for item in plans.services.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    target = physical["br2-data"] if pool == "br2" else pool

    plans, _physical, result, transport = _run(
        tmp_path,
        f"sp2-mixed-competing-{pool}",
        transport_factory=lambda engine: _CompetingRowTransport(
            engine, client="BR1-DEFAULT-PC-01", pool=target
        ),
    )

    assert transport.planted
    typed = _leases(plans, result.service_result.verification_results)
    row = typed["BR1-DEFAULT-PC-01"]
    assert row.status.value != "verified"
    assert row.observed["local_failure_cause"] == "competing_pool_row"
    assert typed["BR1-DEFAULT-PC-02"].status.value == "verified"


#: The stock pool realigns to 512 addresses from the server's network, which in
#: this fixture covers the branch exclusions. Tests that are about another pool
#: first narrow it to a disjoint window, as an operator-set default would be.
_NARROW_STOCK_POOL = (
    "var sq=p.getPool('serverPool');"
    "sq.setStartIp('10.40.1.100');sq.setEndIp('10.40.1.150');"
)


def _seed_before_e6(transport, seed):
    """Run `seed` on the engine just before the first E6 DHCP server script.

    E5 addressing realigns every non-intended pool in this engine scenario, so
    a pool seeded earlier would not survive to the E6 writer.
    """
    dispatch = transport.dispatch_and_wait
    pending = [seed]

    def guarded(js_code, timeout):
        if pending and "DhcpServerMain" in js_code:
            transport.engine.evaluate(pending.pop())
        return dispatch(js_code, timeout)

    transport.dispatch_and_wait = guarded
    return transport


def _named_only_payload():
    payload, _ids = mixed_dhcp_payload()
    payload["sites"][0]["services"] = []
    return payload


def test_named_only_plan_refuses_an_unrecorded_transport_before_effects(tmp_path):
    """The relay binding is recorded on the file channel; http is refused at A9."""
    require_node()
    payload = _named_only_payload()
    plans = compose_mixed(payload, mixed_records())
    assert plans.services is not None, plans.composition.issues
    engine = NodeEngine(tmp_path, dhcp_default_pool="native", terminals=True)
    try:
        for device in plans.composition.topology.devices:
            engine.seed_device(device.name, device.model)
        transport = _CountingTransport(engine)
        result = run_native_product(
            tmp_path,
            plans,
            EnterpriseIntent.model_validate(payload),
            transport,
            run_id="sp2-named-http",
            capability_catalog=lambda _version: mixed_records(),
            channel="http",
            device_capability_catalog=_relay_candidates(),
        )
    finally:
        engine.close()

    assert result.service_result is None
    assert result.refusal_code.value == "service_path_unsupported"
    assert transport.dispatches == 0


class _CountingTransport(NodeEngineTransport):
    def __init__(self, engine) -> None:
        super().__init__(engine)
        self.dispatches = 0

    def dispatch_and_wait(self, js_code, timeout):
        self.dispatches += 1
        return super().dispatch_and_wait(js_code, timeout)

    def send_and_wait(self, js_code, timeout):
        self.dispatches += 1
        return super().send_and_wait(js_code, timeout)


def test_an_unplanned_pool_row_is_scanned_as_competition(tmp_path):
    """A pool the plan never names still holds competing rows for the client."""
    payload = _named_only_payload()
    plans = compose_mixed(payload, mixed_records())
    physical = {
        item.segment_id: item.effective_pool_name
        for item in plans.services.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    clients = {
        f"{site}-DEFAULT-PC-0{n}": physical[f"{site.lower()}-data"]
        for site in ("BR1", "BR2")
        for n in (1, 2)
    }

    def seeded(engine):
        seed = (
            "var p=ipc.network().getDevice('HQ-DEFAULT-DNS-01')"
            ".getProcess('DhcpServerMain')"
            ".getDhcpServerProcessByPortName('FastEthernet0');"
            + _NARROW_STOCK_POOL
            + "p.addPool('ROGUE');"
            "var q=p.getPool('ROGUE');q.setNetworkMask('10.201.0.0','255.255.255.0');"
            "q.setStartIp('10.201.0.2');q.setEndIp('10.201.0.2');q.setMaxUsers(1);"
            "reportResult('ok');"
        )
        return _seed_before_e6(
            _CompetingRowTransport(engine, client="BR1-DEFAULT-PC-01", pool="ROGUE"),
            seed,
        )

    plans, _physical, result, transport = _run(
        tmp_path,
        "sp2-unplanned-pool",
        pools=clients,
        payload=payload,
        transport_factory=seeded,
    )

    assert transport.planted
    typed = _leases(plans, result.service_result.verification_results)
    assert typed["BR1-DEFAULT-PC-01"].observed["local_failure_cause"] == (
        "competing_pool_row"
    )
    assert typed["BR1-DEFAULT-PC-02"].status.value == "verified"


class _LatePoolTransport(NodeEngineTransport):
    """Add an unplanned pool between the last server readback and snapshot."""

    def __init__(self, engine) -> None:
        super().__init__(engine)
        self.added = False
        self.snapshots = 0

    def dispatch_and_wait(self, js_code, timeout):
        if "var group=" in js_code and "HQ-DEFAULT-PC" in js_code:
            self.snapshots += 1
        if not self.added and self.snapshots == 2:
            self.added = True
            self.engine.evaluate(
                "ipc.network().getDevice('HQ-DEFAULT-DNS-01')"
                ".getProcess('DhcpServerMain')"
                ".getDhcpServerProcessByPortName('FastEthernet0').addPool('LATE');"
                "reportResult('ok');"
            )
        return super().dispatch_and_wait(js_code, timeout)


def test_mixed_native_snapshot_reads_its_own_inventory(tmp_path):
    """A pool added after the server readback still stops native attribution."""
    plans, _physical, result, transport = _run(
        tmp_path, "sp2-late-pool", transport_factory=_LatePoolTransport
    )

    assert transport.added
    typed = _leases(plans, result.service_result.verification_results)
    for name in ("HQ-DEFAULT-PC-01", "HQ-DEFAULT-PC-02"):
        assert typed[name].status.value != "verified", name


def test_single_pool_native_snapshot_reads_its_own_inventory(tmp_path):
    """The legacy single-pool snapshot also sees a pool added before it."""
    payload, _ids = mixed_dhcp_payload()
    for site in payload["sites"][1:]:
        site["services"] = []

    plans, _physical, result, transport = _run(
        tmp_path,
        "sp2-late-pool-single",
        payload=payload,
        pools={"HQ-DEFAULT-PC-01": "serverPool", "HQ-DEFAULT-PC-02": "serverPool"},
        transport_factory=_LatePoolTransport,
    )

    assert transport.added
    typed = _leases(plans, result.service_result.verification_results)
    for name in ("HQ-DEFAULT-PC-01", "HQ-DEFAULT-PC-02"):
        assert typed[name].status.value != "verified", name


@pytest.mark.parametrize(
    "overlap",
    ["network", "exclusion", "process_exclusion", "full_inventory", "lease_window"],
)
def test_named_pool_refuses_an_existing_conflicting_pool_before_writing(
    tmp_path, overlap
):
    """An unplanned pool overlapping the new one stops the write, not the reader."""
    payload = _named_only_payload()
    plans = compose_mixed(payload, mixed_records())
    br1 = next(
        item
        for item in plans.services.actions
        if isinstance(item, ConfigureServerDhcpPool) and item.segment_id == "br1-data"
    )
    if overlap == "network":
        network, mask, start, end = (
            br1.network,
            br1.netmask,
            br1.lease_start,
            br1.lease_end,
        )
    elif overlap == "lease_window":
        # A different declared network whose stored lease range still covers
        # the new pool's leases.
        network, mask = "10.200.0.0", "255.255.255.0"
        start, end = br1.lease_start, br1.lease_end
    elif overlap == "exclusion":
        excluded = br1.excluded_ranges[0]
        network, mask = "10.200.0.0", "255.255.255.0"
        start, end = excluded.start, excluded.end
    else:
        network, mask, start, end = (
            "10.200.0.0",
            "255.255.255.0",
            "10.200.0.2",
            "10.200.0.2",
        )
    # An existing process-wide exclusion inside the new lease window, or an
    # inventory already at the 64-pool read limit, with ROGUE itself disjoint.
    extra = {
        "process_exclusion": (
            f"p.addExcludedAddress('{br1.lease_start}','{br1.lease_start}');"
        ),
        "full_inventory": (
            "for(var i=0;i<62;i++){p.addPool('FILL'+i);var f=p.getPool('FILL'+i);"
            "f.setNetworkMask('10.210.'+i+'.0','255.255.255.0');"
            "f.setStartIp('10.210.'+i+'.2');f.setEndIp('10.210.'+i+'.2');}"
        ),
    }.get(overlap, "")

    def seeded(engine):
        seed = (
            "var p=ipc.network().getDevice('HQ-DEFAULT-DNS-01')"
            ".getProcess('DhcpServerMain')"
            ".getDhcpServerProcessByPortName('FastEthernet0');"
            + _NARROW_STOCK_POOL
            + "p.addPool('ROGUE');"
            f"var q=p.getPool('ROGUE');q.setNetworkMask('{network}','{mask}');"
            f"q.setStartIp('{start}');q.setEndIp('{end}');"
            + extra
            + "reportResult('ok');"
        )
        return _seed_before_e6(_CountingTransport(engine), seed)

    plans, _physical, result, _transport = _run(
        tmp_path,
        f"sp2-existing-{overlap}",
        payload=payload,
        pools={
            f"BR{s}-DEFAULT-PC-0{n}": "BR1_DATA" if s == 1 else "BR2_DATA"
            for s in (1, 2)
            for n in (1, 2)
        },
        transport_factory=seeded,
    )

    rows = {item.action_id: item for item in result.service_result.action_results}
    assert rows[br1.id].status.value != "applied", rows[br1.id].cause


def test_a_relay_record_from_another_build_refuses_before_effects(tmp_path):
    """A self-consistent record for a different build admits nothing here."""
    require_node()
    payload = _named_only_payload()
    plans = compose_mixed(payload, mixed_records())
    foreign = dict(mixed_records())
    foreign[RELAY_BINDING_KEY] = foreign[RELAY_BINDING_KEY].model_copy(
        update={"build": "9.0.0.0810", "packet_tracer_version": "9.0.0.0810"}
    )
    engine = NodeEngine(tmp_path, dhcp_default_pool="native", terminals=True)
    try:
        for device in plans.composition.topology.devices:
            engine.seed_device(device.name, device.model)
        transport = _CountingTransport(engine)
        result = run_native_product(
            tmp_path,
            plans,
            EnterpriseIntent.model_validate(payload),
            transport,
            run_id="sp2-foreign-build",
            capability_catalog=lambda _version: foreign,
            device_capability_catalog=_relay_candidates(),
        )
    finally:
        engine.close()

    assert result.service_result is None
    assert result.refusal_code.value == "capability_unknown"
    assert transport.dispatches == 0


def test_the_measured_out_of_range_throw_ends_every_table(tmp_path):
    """PT 9.0.1.0858 throws past a pool's last row; it never returned null.

    Every SP-2 episode (e1-e6) read `invalid vector subscript` at the index
    equal to the row count. With that native end, the relayed and local
    clients still verify, each naming how its tables ended.
    """
    plans, _physical, result, _snapshot = _run(
        tmp_path, "sp2-native-table-end", dhcp_table_end="native"
    )

    assert result.service_result is not None, (
        result.refusal_code,
        result.blocked_reason,
    )
    typed = _leases(plans, result.service_result.verification_results)
    assert {name: row.status.value for name, row in typed.items()} == {
        f"{site}-DEFAULT-PC-0{n}": "verified"
        for site in ("HQ", "BR1", "BR2")
        for n in (1, 2)
    }
    for row in typed.values():
        assert "lease_table_end_by_out_of_range_throw" in row.limitations, row


def test_a_row_field_failure_is_never_a_table_end(tmp_path):
    """A row whose MAC getter throws the end text leaves its table unread.

    Otherwise a competing pool would read as empty while it holds a row, and
    every client scanned against it would verify over an unread lease.
    """
    plans, _physical, result, _snapshot = _run(
        tmp_path,
        "sp2-row-field-failure",
        dhcp_table_end="native",
        dhcp_lease_field_throws="BR2_DATA",
    )

    typed = _leases(plans, result.service_result.verification_results)
    assert typed and all(row.status.value != "verified" for row in typed.values()), {
        name: row.status.value for name, row in typed.items()
    }


def test_an_unexplained_throw_is_not_a_table_end(tmp_path):
    """Any other error past the rows leaves the tables unread."""
    plans, _physical, result, _snapshot = _run(
        tmp_path, "sp2-unexplained-throw", dhcp_table_end="throw"
    )

    typed = _leases(plans, result.service_result.verification_results)
    assert typed and all(row.status.value != "verified" for row in typed.values())


class _TruncatedScanTransport(NodeEngineTransport):
    """Report the BR1 intended-pool scan as cut short by a read error."""

    def dispatch_and_wait(self, js_code, timeout):
        outcome = super().dispatch_and_wait(js_code, timeout)
        if "var group=" not in js_code or "BR1_DATA" not in js_code:
            return outcome
        payload = json.loads(outcome.body)
        if payload.get("pool_name") != "BR1_DATA":
            return outcome
        payload["termination"] = "error"
        payload["scan_error"] = "lease read failed"
        return BridgeDispatchOutcome(
            dispatch=outcome.dispatch, result=outcome.result, body=json.dumps(payload)
        )


def test_a_truncated_named_pool_scan_never_verifies(tmp_path):
    """A named pool needs its whole table read, not only a matching first row."""
    plans, _physical, result, _transport = _run(
        tmp_path, "sp2-truncated-scan", transport_factory=_TruncatedScanTransport
    )

    typed = _leases(plans, result.service_result.verification_results)
    for name in ("BR1-DEFAULT-PC-01", "BR1-DEFAULT-PC-02"):
        assert typed[name].status.value != "verified", name
    assert typed["BR2-DEFAULT-PC-01"].status.value == "verified"
