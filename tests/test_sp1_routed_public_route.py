"""SP-1 system tests: the registered MCP tool over a SIMULATED routed campus.

The tool, its session composition, the use case, both runtimes, the readiness
gate, the routed rule and the record store are production code; only what
lies beyond the bridge is simulated (`routed_product_simulation`), and the
device catalog is the production candidate adapter naming exactly the one
unmeasured capability SP-1 needs (`supports_static_routes`). The oracle is the
simulator's own forwarding at request time, never the product's verdict.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from routed_product_simulation import routed_campus_plans, run_public_routed
from sp1_routed_fixture import HOSTNAME, compose, topology_payload, with_services

CANDIDATES = {"1941": ["supports_static_routes"], "2911": ["supports_static_routes"]}


@pytest.fixture(scope="module")
def workload():
    """Return the routed intent, its simulator plans and its addresses."""
    base = topology_payload()
    first = compose(base, services=False)
    payload = with_services(base, first)
    plans = routed_campus_plans(payload)
    return {
        "plans": plans,
        "web": first.endpoint("HQ-DEFAULT-WEB-01").ipv4,
        "dns": first.endpoint("HQ-DEFAULT-DNS-01").ipv4,
        "first": first,
    }


def _run(tmp_path, monkeypatch, workload, configure=None):
    if configure is not None:
        # A refusing routed group waits out its whole window on the real
        # clock. Faults are about WHICH dependents refuse, not how long the
        # window is, so fault runs use a short window.
        from packet_tracer_mcp.application.use_cases import (
            service_access_readiness_gate as gate,
        )

        monkeypatch.setattr(gate, "ROUTED_GROUP_DEADLINE_SECONDS", 8.0)
    return run_public_routed(
        tmp_path,
        monkeypatch,
        workload["plans"],
        dns_server=workload["dns"],
        records={HOSTNAME: workload["web"]},
        configure=configure,
        device_candidates=CANDIDATES,
    )


def _checks(public) -> dict[tuple[str, str], dict]:
    rows = {}
    for client in public["clients"]:
        for result in client["results"].values():
            for check in result["checks"]:
                rows[(client["deployed_name"], check["kind"])] = check
    return rows


def test_every_client_is_served_across_vlans_and_sites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """Inter-VLAN, one-hop and two-hop clients: by IP, DNS and by name."""
    public, terminal = _run(tmp_path, monkeypatch, workload)

    assert public["status"] == "verified", public["blocked_reason"]
    checks = _checks(public)
    clients = {name for name, _ in checks}
    assert len(clients) == 6
    for name in clients:
        for kind in (
            "http_fetch",
            "dns_resolution",
            "dns_negative_control",
            "http_by_hostname",
        ):
            assert checks[(name, kind)]["status"] == "verified", (name, kind)
    # The oracle: every delivered request really crossed the simulated routers.
    assert all(
        delivered
        for _time, _kind, _client, target, delivered in terminal.requests
        if not target.startswith("missing-")
    )
    assert not terminal.unhandled


def test_every_first_request_is_http_by_address_before_any_dns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """Cold order at the network: all by-IP fetches precede the first DNS query."""
    _public, terminal = _run(tmp_path, monkeypatch, workload)

    kinds = [(kind, target) for _time, kind, _client, target, _ok in terminal.requests]
    by_ip = [
        index
        for index, (kind, target) in enumerate(kinds)
        if kind == "http" and target[0].isdigit()
    ]
    later = [
        index
        for index, (kind, target) in enumerate(kinds)
        if kind == "dns" or (kind == "http" and not target[0].isdigit())
    ]
    assert len(by_ip) == 6 and later
    assert max(by_ip) < min(later)
    first_per_client: dict[str, str] = {}
    for _time, kind, client, target, _ok in terminal.requests:
        first_per_client.setdefault(client, f"{kind}:{target}")
    assert all(item == f"http:{workload['web']}" for item in first_per_client.values())


def test_a_missing_return_route_blocks_exactly_the_clients_behind_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """HQ loses its route back to BR2: BR2 is refused, never requested."""
    import ipaddress

    br2 = workload["first"].endpoint("BR2-DEFAULT-PC-01")
    network = ipaddress.ip_interface(f"{br2.ipv4}/{br2.netmask}").network

    def configure(terminal):
        terminal.withheld_routes.add(("HQ-EDGE-RTR-01", str(network.network_address)))

    public, terminal = _run(tmp_path, monkeypatch, workload, configure)

    checks = _checks(public)
    for name in ("BR2-DEFAULT-PC-01", "BR2-DEFAULT-PC-02"):
        row = checks[(name, "http_fetch")]
        assert row["status"] == "dependency_blocked"
        assert "return_route_missing:HQ-EDGE-RTR-01" in row["cause"]
    for name in ("HQ-DEFAULT-PC-01", "BR1-DEFAULT-PC-01"):
        assert checks[(name, "http_fetch")]["status"] == "verified"
    requested = {client for _t, kind, client, *_ in terminal.requests if kind == "http"}
    assert not requested & {"BR2-DEFAULT-PC-01", "BR2-DEFAULT-PC-02"}


def test_a_wrong_next_hop_is_refused_before_the_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """BR1 points HQ-bound traffic back at BR2: readiness names the hop."""
    import ipaddress

    web = workload["first"].endpoint("HQ-DEFAULT-WEB-01")
    hq_servers = ipaddress.ip_interface(f"{web.ipv4}/{web.netmask}").network
    br2_facing = next(
        item.ipv4
        for item in workload["plans"].configuration_plan.actions
        if item.action_type.value == "configure_routed_interface"
        and item.device_name == "BR2-EDGE-RTR-01"
        and item.segment_id.startswith("transit/")
    )

    def configure(terminal):
        terminal.wrong_next_hops[
            ("BR1-EDGE-RTR-01", str(hq_servers.network_address))
        ] = br2_facing

    public, _terminal = _run(tmp_path, monkeypatch, workload, configure)

    checks = _checks(public)
    for name in ("BR1-DEFAULT-PC-01", "BR2-DEFAULT-PC-01"):
        row = checks[(name, "http_fetch")]
        assert row["status"] == "dependency_blocked"
        assert "route_next_hop:BR1-EDGE-RTR-01" in row["cause"]
    assert checks[("HQ-DEFAULT-PC-01", "http_fetch")]["status"] == "verified"


@pytest.mark.parametrize(
    ("router_name", "target_name", "fault", "cause"),
    [
        (
            "BR1-EDGE-RTR-01",
            "HQ-DEFAULT-WEB-01",
            "printed_egress",
            "route_output_interface:BR1-EDGE-RTR-01",
        ),
        (
            "HQ-EDGE-RTR-01",
            "BR1-DEFAULT-PC-01",
            "next_hop_shadow",
            "return_next_hop_egress:HQ-EDGE-RTR-01",
        ),
    ],
)
def test_effective_egress_fault_refuses_product_request_and_survives_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workload,
    router_name,
    target_name,
    fault,
    cause,
):
    """Parsed IOS egress contradictions stop E6 traffic and remain in the record."""
    import ipaddress

    from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
        ServiceRunRecordStore,
    )

    endpoint = workload["first"].endpoint(target_name)
    network = ipaddress.ip_interface(f"{endpoint.ipv4}/{endpoint.netmask}").network
    route = next(
        item
        for item in workload["plans"].configuration_plan.actions
        if item.action_type.value == "configure_static_route"
        and item.device_name == router_name
        and item.network == str(network.network_address)
        and item.prefix == network.prefixlen
    )

    def configure(terminal):
        original = terminal._route_table

        def route_table(router):
            text = original(router)
            if router.name != router_name or not terminal._faults_on():
                return text
            printed = f"S       {network} [1/0] via {route.next_hop}"
            assert printed in text
            if fault == "printed_egress":
                return text.replace(printed, printed + ", GigabitEthernet0/9", 1)
            return text + (
                f"\nC       {route.next_hop}/32 is directly connected, "
                "GigabitEthernet0/9"
            )

        terminal._route_table = route_table

    public, terminal = _run(tmp_path, monkeypatch, workload, configure)

    row = _checks(public)[("BR1-DEFAULT-PC-01", "http_fetch")]
    assert row["status"] == "dependency_blocked"
    assert cause in row["cause"]
    assert not [item for item in terminal.requests if item[2] == "BR1-DEFAULT-PC-01"]
    assert _checks(public)[("HQ-DEFAULT-PC-01", "http_fetch")]["status"] == ("verified")
    record = ServiceRunRecordStore(tmp_path / "services").load(
        public["deployment_id"], public["run_id"]
    )
    assert any(
        cause in str(row.get("causes", ()))
        for row in record.operational_readiness
        if row.get("kind") == "routed_forwarding"
    )
    router_id = next(
        device_id
        for device_id, name in workload["plans"].deployed_names.items()
        if name == router_name
    )
    facts = [
        row["sample"]["devices"][router_id]
        for row in record.operational_readiness
        if row.get("kind") == "routed_forwarding"
        and router_id in row["sample"]["devices"]
    ]
    assert facts
    if fault == "printed_egress":
        assert any(
            item["interface"] == "GigabitEthernet0/9"
            for fact in facts
            for item in fact["routes"].get(endpoint.ipv4, ())
        )
    else:
        assert any(
            item["prefix"] == f"{route.next_hop}/32"
            and item["interface"] == "GigabitEthernet0/9"
            for fact in facts
            for item in fact["routes"].get(route.next_hop, ())
        )


def test_a_down_transit_link_is_refused_by_its_interface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """The BR1-BR2 link is down: BR2 clients are refused naming the interface."""

    def configure(terminal):
        terminal.down_interfaces.add(("BR2-EDGE-RTR-01", "GigabitEthernet0/0"))

    public, _terminal = _run(tmp_path, monkeypatch, workload, configure)

    row = _checks(public)[("BR2-DEFAULT-PC-01", "http_fetch")]
    assert row["status"] == "dependency_blocked"
    assert "BR2-EDGE-RTR-01" in row["cause"]


def test_routes_that_install_within_the_window_are_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """Late installation inside the routed window is convergence, not failure."""

    def configure(terminal):
        terminal.routes_install_after = 3.0

    public, _terminal = _run(tmp_path, monkeypatch, workload, configure)

    assert _checks(public)[("BR2-DEFAULT-PC-01", "http_fetch")]["status"] == "verified"


def test_recovered_route_round_still_blocks_pending_product_dns_and_reloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """A transient authoritative route loss revokes a prior group's pending DNS."""
    import ipaddress

    from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
        ServiceRunRecordStore,
    )

    web = workload["first"].endpoint("HQ-DEFAULT-WEB-01")
    network = ipaddress.ip_interface(f"{web.ipv4}/{web.netmask}").network
    state = {"bad_read": False}

    def configure(terminal):
        original = terminal._route_table

        def route_table(router):
            text = original(router)
            if (
                router.name != "BR1-EDGE-RTR-01"
                or not terminal._faults_on()
                or state["bad_read"]
                or not any(
                    kind == "http" and client == "BR1-DEFAULT-PC-01"
                    for _time, kind, client, _target, _ok in terminal.requests
                )
            ):
                return text
            line = next(
                item
                for item in text.splitlines()
                if item.startswith(f"S       {network} ")
            )
            state["bad_read"] = True
            return text.replace(line, "", 1)

        terminal._route_table = route_table

    public, terminal = _run(tmp_path, monkeypatch, workload, configure)

    assert state["bad_read"]
    checks = _checks(public)
    assert checks[("BR1-DEFAULT-PC-01", "http_fetch")]["status"] == "verified"
    assert checks[("BR1-DEFAULT-PC-01", "dns_resolution")]["status"] == (
        "dependency_blocked"
    )
    assert (
        "ROUTE_DRIFT_AFTER_ADMISSION"
        in checks[("BR1-DEFAULT-PC-01", "dns_resolution")]["cause"]
    )
    assert not [
        item
        for item in terminal.requests
        if item[1] == "dns" and item[2] == "BR1-DEFAULT-PC-01"
    ]
    assert any(
        item[1] == "http" and item[2] == "BR2-DEFAULT-PC-01"
        for item in terminal.requests
    )
    record = ServiceRunRecordStore(tmp_path / "services").load(
        public["deployment_id"], public["run_id"]
    )
    [revocations] = [
        row
        for row in record.operational_readiness
        if row.get("kind") == "routed_revocations"
    ]
    affected = next(
        item
        for item in revocations["revoked"]
        if item["admitted_group"] == ["routed_forwarding", "br1-data", "hq-servers"]
        and item["cause"] == (f"route_missing:BR1-EDGE-RTR-01:{web.ipv4}")
    )
    assert affected["router"] == "BR1-EDGE-RTR-01"
    assert affected["round"] == 0
    assert affected["order"] >= 1
    assert affected["source_group"] == ["routed_forwarding", "br2-data", "hq-servers"]
    evidence = revocations["evidence"][affected["evidence_ref"]]
    assert evidence["episode"]["ordinal"] == 1
    assert evidence["source_group"] == affected["source_group"]
    assert evidence["round"] == affected["round"]
    router_id = next(
        device_id
        for device_id, name in workload["plans"].deployed_names.items()
        if name == "BR1-EDGE-RTR-01"
    )
    assert evidence["devices"][router_id]["routes"][web.ipv4] == []
    assert evidence["devices"][router_id]["interfaces"]
    [later] = [
        row
        for row in record.operational_readiness
        if row.get("kind") == "routed_forwarding"
        and row["client_segment_id"] == "br2-data"
    ]
    assert later["status"] == "admitted"
    assert later["sample"]["rounds"] >= 2
    assert later["sample"]["deciding_round"] >= 1


def test_a_wrong_resolver_fails_dns_but_keeps_the_by_ip_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """The fresh resolver read fails first; no DNS query is sent; by IP stands.

    Named delta (SP1-04): the resolver read now gates the client's queries,
    so the wrong binding is caught by the read rather than by a timeout.
    """

    def configure(terminal):
        original = terminal.send

        def send(script):
            accepted = original(script)
            binding = terminal.bindings.get("BR1-DEFAULT-PC-01")
            if binding is not None:
                binding["dns"] = workload["web"]
            return accepted

        terminal.send = send

    public, terminal = _run(tmp_path, monkeypatch, workload, configure)

    checks = _checks(public)
    assert checks[("BR1-DEFAULT-PC-01", "http_fetch")]["status"] == "verified"
    assert checks[("BR1-DEFAULT-PC-01", "client_dns_server")]["status"] == "failed"
    assert checks[("BR1-DEFAULT-PC-01", "dns_resolution")]["status"] == (
        "dependency_blocked"
    )
    dns_sent = {client for _t, kind, client, *_ in terminal.requests if kind == "dns"}
    assert "BR1-DEFAULT-PC-01" not in dns_sent
    assert checks[("BR1-DEFAULT-PC-01", "dns_negative_control")]["status"] == (
        "dependency_blocked"
    )
    assert checks[("BR1-DEFAULT-PC-01", "http_by_hostname")]["status"] == (
        "dependency_blocked"
    )
    assert checks[("BR1-DEFAULT-PC-02", "dns_resolution")]["status"] == "verified"


def test_a_fault_present_at_configuration_time_stops_before_e6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """E5 read-back sees the missing route and no E6 effect is dispatched."""

    def configure(terminal):
        terminal.faults_after_service_apply = False
        terminal.down_interfaces.add(("BR2-EDGE-RTR-01", "GigabitEthernet0/0"))

    public, terminal = _run(tmp_path, monkeypatch, workload, configure)

    assert public["refusal_code"] == "e5_contradiction"
    assert "service_apply" not in terminal.events
    assert terminal.requests == []


def test_the_durable_record_agrees_with_the_public_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """The stored record reloads with the same routed readiness and results."""
    from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
        ServiceRunRecordStore,
    )

    public, _terminal = _run(tmp_path, monkeypatch, workload)

    store = ServiceRunRecordStore(tmp_path / "services")
    record = store.load(public["deployment_id"], public["run_id"])
    assert record.status.value == public["status"]
    assert [row.get("kind") for row in record.operational_readiness] == [
        row.get("kind") for row in public["operational_readiness"]
    ]
    routed = [
        row
        for row in record.operational_readiness
        if row.get("kind") == "routed_forwarding"
    ]
    assert len(routed) == 3 and {row["status"] for row in routed} == {"admitted"}


def test_a_failed_gateway_read_sends_no_traffic_for_that_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workload
):
    """SP1-03 (review finding): no DNS may precede a skipped HTTP-by-address.

    The client's gateway read contradicts the plan, so its HTTP-by-address
    fetch is blocked; its DNS rows share that prerequisite and are blocked
    too, so nothing warms its path. Other clients are unaffected.
    """

    def configure(terminal):
        original = terminal.send

        def send(script):
            accepted = original(script)
            binding = terminal.bindings.get("BR1-DEFAULT-PC-02")
            if binding is not None:
                binding["gateway"] = "10.255.255.254"
            return accepted

        terminal.send = send

    public, terminal = _run(tmp_path, monkeypatch, workload, configure)

    checks = _checks(public)
    assert checks[("BR1-DEFAULT-PC-02", "client_gateway")]["status"] == "failed"
    for kind in ("http_fetch", "dns_resolution", "http_by_hostname"):
        assert checks[("BR1-DEFAULT-PC-02", kind)]["status"] == "dependency_blocked"
    assert not [item for item in terminal.requests if item[2] == "BR1-DEFAULT-PC-02"]
    assert checks[("BR1-DEFAULT-PC-01", "dns_resolution")]["status"] == "verified"
