"""SP-2 Step 2: native local and named remote pools on one Server-PT."""

from __future__ import annotations

import pytest
from sp2_mixed_fixture import (
    RELAY_BINDING_KEY,
    compose_mixed,
    mixed_dhcp_payload,
    mixed_records,
)

from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    _plan_for,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    AddressRange,
    ConfigureDhcpRelay,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServicePhase,
    ServiceType,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.services.service_capability_resolution import (
    resolve_action_capability,
    resolve_verification_capability,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    packet_tracer_service_capabilities,
)


def _dhcp(plans):
    actions = plans.services.actions
    pools = {
        item.segment_id: item
        for item in actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    enables = {
        item.service_id: item for item in actions if isinstance(item, EnableServerDhcp)
    }
    return actions, pools, enables


def _segment_of(plans, service_id):
    return next(
        item.segment_id for item in plans.services.services if item.id == service_id
    )


def _prerequisites(actions, action_id):
    by_id = {item.id: item for item in actions}
    found: set[str] = set()
    pending = list(by_id[action_id].depends_on)
    while pending:
        identifier = pending.pop()
        if identifier not in found:
            found.add(identifier)
            pending.extend(by_id[identifier].depends_on)
    return found


def test_one_server_compiles_native_local_and_named_remote_pools():
    """Placement selects the physical pool; remote pools keep one helper."""
    payload, _ids = mixed_dhcp_payload()
    plans = compose_mixed(payload, mixed_records())

    assert plans.services is not None, plans.composition.issues
    _actions, pools, _enables = _dhcp(plans)
    assert set(pools) == {"hq-data", "br1-data", "br2-data"}
    assert pools["hq-data"].effective_pool_name == "serverPool"
    for segment in ("br1-data", "br2-data"):
        pool = pools[segment]
        assert pool.effective_pool_name == pool.pool_name != "serverPool"
        relays = [
            item
            for item in plans.configuration.actions
            if isinstance(item, ConfigureDhcpRelay) and item.segment_id == segment
        ]
        assert len(relays) == 1
    leases = {
        item.client_device_name: item
        for item in plans.services.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    }
    assert {
        name: (item.expected["state_only"], item.expected["effective_pool_name"])
        for name, item in leases.items()
    } == {
        **{f"HQ-DEFAULT-PC-0{n}": (True, "serverPool") for n in (1, 2)},
        **{
            f"BR{s}-DEFAULT-PC-0{n}": (True, pools[f"br{s}-data"].pool_name)
            for s in (1, 2)
            for n in (1, 2)
        },
    }


def test_named_relay_binding_resolves_only_its_own_named_pool_actions():
    """The relay record authorizes named pools, never the native or a generic one."""
    payload, _ids = mixed_dhcp_payload()
    records = mixed_records()
    plans = compose_mixed(payload, records)
    assert plans.services is not None, plans.composition.issues
    _actions, pools, enables = _dhcp(plans)
    services = {item.id: item for item in plans.services.services}
    for action in [*pools.values(), *enables.values()]:
        assert resolve_action_capability(records, action).is_supported
    for expectation in plans.services.verification_expectations:
        service = services[expectation.service_id]
        if service.service_type is ServiceType.DHCP and expectation.kind in {
            ServiceVerificationKind.DHCP_LEASE,
            ServiceVerificationKind.DHCP_SERVER_STATE,
        }:
            assert resolve_verification_capability(
                records, expectation, service
            ).is_supported, expectation.id
    generic = pools["br1-data"].model_copy(update={"effective_pool_name": ""})
    assert not resolve_action_capability(records, generic).is_supported
    unrelated = {k: v for k, v in records.items() if k != RELAY_BINDING_KEY}
    assert not resolve_action_capability(unrelated, pools["br1-data"]).is_supported


def test_default_catalog_refuses_remote_state_only_before_effects():
    """Without the relay record, remote state-only DHCP never compiles."""
    payload, _ids = mixed_dhcp_payload()
    default = packet_tracer_service_capabilities("9.0.1.0858")
    assert RELAY_BINDING_KEY not in default or (
        default[RELAY_BINDING_KEY].support is not CapabilityStatus.SUPPORTED
    )
    plans = compose_mixed(payload, mixed_records(relay=False))

    assert plans.services is None
    assert any("relay" in issue.casefold() for issue in plans.composition.issues)


@pytest.mark.parametrize(
    "names",
    [
        {"br1-data": "SAME", "br2-data": "SAME"},
        {"br1-data": "serverPool"},
    ],
)
def test_colliding_or_native_physical_names_refuse_the_host(names):
    """Two services cannot share one physical pool, nor claim serverPool."""
    payload, _ids = mixed_dhcp_payload(pool_names=names)

    plans = compose_mixed(payload, mixed_records())

    assert plans.services is None
    assert plans.composition.issues


def _pool(name, network, prefix, *, start, end, exclusions=(), host="srv"):
    netmask = {24: "255.255.255.0", 29: "255.255.255.248"}[prefix]
    return ConfigureServerDhcpPool(
        id=f"pool/{name}",
        service_id=f"svc/{name}",
        service_type=ServiceType.DHCP,
        host_device_id=host,
        host_device_name=host,
        host_model="Server-PT",
        site_id="hq",
        required_capability="service_dhcp_application",
        phase=ServicePhase.CONTENT,
        interface="FastEthernet0",
        pool_name=name,
        effective_pool_name=name,
        segment_id=name.lower(),
        network=network,
        prefix=prefix,
        netmask=netmask,
        gateway=exclusions[0][0] if exclusions else start,
        lease_start=start,
        lease_end=end,
        max_users=1,
        excluded_ranges=[AddressRange(start=a, end=b) for a, b in exclusions],
    )


def test_host_pool_conflicts_find_overlap_and_cross_pool_exclusions():
    """Process-wide exclusions and overlapping networks are host conflicts."""
    from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
        dhcp_host_pool_conflicts,
    )

    a = _pool(
        "A",
        "10.1.0.0",
        24,
        start="10.1.0.100",
        end="10.1.0.100",
        exclusions=[("10.1.0.1", "10.1.0.1")],
    )
    overlapping = _pool("B", "10.1.0.0", 29, start="10.1.0.2", end="10.1.0.2")
    excluding = _pool(
        "C",
        "10.2.0.0",
        29,
        start="10.2.0.2",
        end="10.2.0.2",
        exclusions=[("10.1.0.100", "10.1.0.100")],
    )
    disjoint = _pool(
        "D",
        "10.3.0.0",
        29,
        start="10.3.0.2",
        end="10.3.0.2",
        exclusions=[("10.3.0.1", "10.3.0.1")],
    )
    elsewhere = _pool(
        "E", "10.1.0.0", 29, start="10.1.0.2", end="10.1.0.2", host="other"
    )

    assert dhcp_host_pool_conflicts([a, disjoint, elsewhere]) == []
    assert dhcp_host_pool_conflicts([a, overlapping])
    assert dhcp_host_pool_conflicts([a, excluding])
    assert dhcp_host_pool_conflicts(
        [a, _pool("A", "10.4.0.0", 29, start="10.4.0.2", end="10.4.0.2")]
    )


def test_native_pool_runs_first_and_named_enables_wait_for_native_enable():
    """The pristine native transition precedes every other write on its host."""
    payload, _ids = mixed_dhcp_payload()
    plans = compose_mixed(payload, mixed_records())
    assert plans.services is not None, plans.composition.issues
    actions, pools, enables = _dhcp(plans)
    native_pool = pools["hq-data"]
    native_enable = next(
        item for item in enables.values() if item.effective_pool_name == "serverPool"
    )
    named = [pools["br1-data"], pools["br2-data"]]
    assert native_pool.depends_on == []
    for pool in named:
        assert native_pool.id in _prerequisites(actions, pool.id)
    for enable in enables.values():
        assert {item.id for item in pools.values()} <= _prerequisites(
            actions, enable.id
        )
        if enable is not native_enable:
            assert native_enable.id in enable.depends_on
            assert native_enable.id in enable.apply_dependencies
    assert all(actions.index(native_pool) < actions.index(item) for item in named)


@pytest.mark.parametrize("omitted", ["hq-data", "br1-data"])
def test_a9_narrowing_keeps_native_first_and_strips_omitted_edges(omitted):
    """Dropping an optional service leaves no dangling pool or enable edge."""
    payload, _ids = mixed_dhcp_payload(optional={omitted})
    plans = compose_mixed(payload, mixed_records())
    assert plans.services is not None, plans.composition.issues
    admitted = [item for item in plans.services.services if item.segment_id != omitted]

    selected = _plan_for(plans.services, admitted, {})

    ids = {item.id for item in selected.actions}
    assert all(set(item.depends_on) <= ids for item in selected.actions)
    assert all(set(item.apply_dependencies) <= ids for item in selected.actions)
    _actions, pools, enables = _dhcp(type("P", (), {"services": selected})())
    assert omitted not in pools
    if omitted != "hq-data":
        native_enable = next(
            item
            for item in enables.values()
            if item.effective_pool_name == "serverPool"
        )
        for enable in enables.values():
            if enable is not native_enable:
                assert native_enable.id in enable.depends_on
        assert pools["hq-data"].id in _prerequisites(
            selected.actions, pools["br2-data"].id
        )


def test_only_local_clients_carry_the_native_mode_guard():
    """Remote clients keep the ordinary E5 mode path, not native admission."""
    from packet_tracer_mcp.domain.enterprise.models.configuration import (
        SetEndpointDhcp,
    )

    payload, _ids = mixed_dhcp_payload()
    plans = compose_mixed(payload, mixed_records())

    modes = {
        item.device_name: item.native_effective_pool_name
        for item in plans.configuration.actions
        if isinstance(item, SetEndpointDhcp)
    }
    assert modes == {
        "HQ-DEFAULT-PC-01": "serverPool",
        "HQ-DEFAULT-PC-02": "serverPool",
        "BR1-DEFAULT-PC-01": "",
        "BR1-DEFAULT-PC-02": "",
        "BR2-DEFAULT-PC-01": "",
        "BR2-DEFAULT-PC-02": "",
    }


@pytest.mark.parametrize("omitted", [None, "br1-data"])
def test_native_enable_names_exactly_its_surviving_companion_pools(omitted):
    """The native enable expects the named pools and exclusions A9 kept."""
    payload, _ids = mixed_dhcp_payload(optional={omitted} if omitted else set())
    plans = compose_mixed(payload, mixed_records())
    assert plans.services is not None, plans.composition.issues
    plan = plans.services
    if omitted:
        plan = _plan_for(
            plan,
            [item for item in plan.services if item.segment_id != omitted],
            {},
        )
    pools = {
        item.segment_id: item
        for item in plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    }
    native = next(
        item
        for item in plan.actions
        if isinstance(item, EnableServerDhcp) and item.native_policy is not None
    )
    companions = {
        item.effective_pool_name: [(r.start, r.end) for r in item.excluded_ranges]
        for segment, item in pools.items()
        if segment != "hq-data"
    }
    assert {
        item.pool_name: [(r.start, r.end) for r in item.excluded_ranges]
        for item in native.native_policy.companion_pools
    } == companions
    assert len(companions) == (1 if omitted else 2)


def test_host_lease_scan_budget_refuses_an_oversized_process():
    """Every sample may scan every pool of the host, so the host is bounded."""
    from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
        MAX_HOST_DHCP_LEASE_ROWS,
        dhcp_host_pool_conflicts,
    )

    pools = [
        _pool(
            f"P{index}",
            f"10.{index + 1}.0.0",
            24,
            start=f"10.{index + 1}.0.2",
            end=f"10.{index + 1}.0.2",
        )
        for index in range(5)
    ]
    for pool in pools:
        pool.max_users = MAX_HOST_DHCP_LEASE_ROWS // 5 + 1

    assert any(
        item.endswith(":scan_budget") for item in dhcp_host_pool_conflicts(pools)
    )
    for pool in pools:
        pool.max_users = MAX_HOST_DHCP_LEASE_ROWS // 5
    assert dhcp_host_pool_conflicts(pools) == []


def _native_server_expectation(pool_names):
    import json

    payload, _ids = mixed_dhcp_payload()
    plans = compose_mixed(payload, mixed_records())
    pools = [
        item
        for item in plans.services.actions
        if isinstance(item, ConfigureServerDhcpPool)
    ]
    expectation = next(
        item
        for item in plans.services.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_SERVER_STATE
        and item.expected.get("effective_pool_name") == "serverPool"
    )
    host_pools = sorted(
        (
            {
                "pool_name": item.effective_pool_name,
                "excluded_ranges": [
                    r.model_dump(mode="json") for r in item.excluded_ranges
                ],
            }
            for item in pools
        ),
        key=lambda item: item["pool_name"],
    )
    expected = {
        **expectation.expected,
        "host_pools_json": json.dumps(
            host_pools, sort_keys=True, separators=(",", ":")
        ),
    }
    union = sorted(
        {(r["start"], r["end"]) for item in host_pools for r in item["excluded_ranges"]}
    )
    answer = {
        "found": True,
        "process_found": True,
        "pool_found": True,
        "interface": expected["interface"],
        "pool_name": "serverPool",
        "pool_count": len(host_pools),
        "pool_names": pool_names(host_pools),
        "logical_pool_present": False,
        "enabled": True,
        "enabled_valid": True,
        "network": expected["network"],
        "mask": expected["netmask"],
        "gateway": expected["gateway"],
        "dns": expected["dns_server"],
        "start": expected["lease_start"],
        "end": expected["lease_end"],
        "max": expected["max_users"],
        "exclusions": [{"start": s, "end": e} for s, e in union],
        "error": "",
    }
    return expectation.model_copy(update={"expected": expected}), answer


@pytest.mark.parametrize(
    ("names", "verified"),
    [
        (lambda pools: [item["pool_name"] for item in pools], True),
        (
            lambda pools: [
                "ROGUE" if item["pool_name"] != "serverPool" else "serverPool"
                for item in pools
            ][: len(pools)],
            False,
        ),
    ],
)
def test_native_readback_checks_companion_names_not_only_their_count(names, verified):
    """A same-count process holding an unplanned pool is not the planned one."""
    import json

    from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
        PacketTracerEnterpriseServiceRuntime,
    )

    expectation, answer = _native_server_expectation(names)
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda _script, _timeout: json.dumps(answer)
    )

    result = runtime._verify_dhcp_server_state(expectation)

    assert (result.status.value == "verified") is verified, result.cause


@pytest.mark.parametrize(
    ("companion_label", "present", "verified"),
    [
        (False, False, True),
        (False, True, False),
        (True, True, True),
        (True, False, False),
    ],
)
def test_native_logical_label_is_present_only_as_a_planned_companion(
    companion_label, present, verified
):
    """A pool named like the native label is stale unless it is planned."""
    import json

    from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
        PacketTracerEnterpriseServiceRuntime,
    )

    expectation, answer = _native_server_expectation(
        lambda pools: [item["pool_name"] for item in pools]
    )
    label = expectation.expected["pool_name"]
    if companion_label:
        pools = json.loads(expectation.expected["host_pools_json"])
        renamed = next(item for item in pools if item["pool_name"] != "serverPool")
        renamed["pool_name"] = label
        pools.sort(key=lambda item: item["pool_name"])
        expectation = expectation.model_copy(
            update={
                "expected": {
                    **expectation.expected,
                    "host_pools_json": json.dumps(
                        pools, sort_keys=True, separators=(",", ":")
                    ),
                }
            }
        )
        answer["pool_names"] = sorted(item["pool_name"] for item in pools)
    answer["logical_pool_present"] = present
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [], lambda _script, _timeout: json.dumps(answer)
    )

    result = runtime._verify_dhcp_server_state(expectation)

    assert (result.status.value == "verified") is verified, result.cause


def test_named_pool_size_stays_within_the_verifiable_scan():
    """A named pool must fit the lease scan with room for its terminating null."""
    from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
        MAX_NAMED_POOL_LEASES,
        dhcp_host_pool_conflicts,
    )
    from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
        DHCP_LEASE_SCAN_LIMIT,
    )

    assert MAX_NAMED_POOL_LEASES == DHCP_LEASE_SCAN_LIMIT - 1
    pool = _pool("A", "10.1.0.0", 24, start="10.1.0.2", end="10.1.0.2")
    pool.max_users = MAX_NAMED_POOL_LEASES
    assert dhcp_host_pool_conflicts([pool]) == []
    pool.max_users = MAX_NAMED_POOL_LEASES + 1
    assert any(item.endswith(":pool_size") for item in dhcp_host_pool_conflicts([pool]))


def test_pool_budget_counts_the_stock_default_pool():
    """Named pools join serverPool on the process, so it takes one slot."""
    from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
        MAX_HOST_DHCP_POOLS,
        dhcp_host_pool_conflicts,
    )

    def pools(count):
        return [
            _pool(
                f"P{i}",
                f"10.{i // 250}.{i % 250}.0",
                29,
                start=f"10.{i // 250}.{i % 250}.2",
                end=f"10.{i // 250}.{i % 250}.2",
            )
            for i in range(count)
        ]

    def budget(items):
        return [
            c for c in dhcp_host_pool_conflicts(items) if c.endswith(":pool_budget")
        ]

    assert budget(pools(MAX_HOST_DHCP_POOLS - 1)) == []
    assert budget(pools(MAX_HOST_DHCP_POOLS))
    native = pools(MAX_HOST_DHCP_POOLS)
    native[0].effective_pool_name = "serverPool"
    assert budget(native) == []


def test_named_pool_smaller_than_its_clients_refuses_before_effects():
    """Capacity below the selected clients could never verify, so it never compiles."""
    payload, _ids = mixed_dhcp_payload()
    payload["sites"][1]["services"][0]["dhcp_pool"]["max_users"] = 1

    plans = compose_mixed(payload, mixed_records())

    assert plans.services is None
    assert any("capacity" in issue.casefold() for issue in plans.composition.issues)
