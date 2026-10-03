"""SP-2 acquisition discriminator: pure decisions and typed projections.

Production code: the discriminator's precondition and per-arm assessment,
and the two diagnostic projections, over the real composed mixed contract.
Observations are hand-built readings and scans, so these cases pin the
input/output/error contracts; they say nothing about Packet Tracer.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from packet_tracer_mcp.adapters.cli.sp2_mixed_qualification import (
    sp2_mixed_product_contract,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import SetEndpointDhcp
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AcquireDhcpLease,
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    SP2_ACQUISITION_ARMS,
    MeasurementConclusion,
)
from packet_tracer_mcp.domain.enterprise.services.dhcp_lease_evidence import (
    ClientReading,
    LeaseRow,
    classify_lease_scan,
)
from packet_tracer_mcp.domain.enterprise.services.service_diagnostic_profiles import (
    sp2_acquisition_reassert_plan,
    sp2_acquisition_start_plan,
)
from packet_tracer_mcp.domain.enterprise.services.sp2_acquisition_discriminator import (
    AcquisitionSample,
    acquisition_precondition,
    assess_acquisition_arms,
)

CONTRACT = sp2_mixed_product_contract("9.0.1.0858", "discriminator-unit")
_POOLS = {
    item.segment_id: item
    for item in CONTRACT.service_plan.actions
    if isinstance(item, ConfigureServerDhcpPool)
}
CLIENT_POOLS = {
    item.device_name: _POOLS[item.segment_id]
    for item in CONTRACT.configuration_plan.actions
    if isinstance(item, SetEndpointDhcp)
}
POOL_NAMES = tuple(sorted({item.effective_pool_name for item in _POOLS.values()}))
CLIENTS = tuple(sorted(SP2_ACQUISITION_ARMS))
MACS = {name: f"0001.0000.{index:04X}" for index, name in enumerate(CLIENTS, start=1)}


def _leases() -> dict[str, str]:
    """Give each client the next address of its own pool's lease window."""
    used: dict[str, int] = {}
    leases = {}
    for name in CLIENTS:
        pool = CLIENT_POOLS[name]
        offset = used.get(pool.effective_pool_name, 0)
        used[pool.effective_pool_name] = offset + 1
        prefix, last = pool.lease_start.rsplit(".", 1)
        leases[name] = f"{prefix}.{int(last) + offset}"
    return leases


LEASES = _leases()
SERVER = {
    "device": "HQ-DEFAULT-DNS-01",
    "interface": "FastEthernet0",
    "found": True,
    "process_found": True,
    "error": "",
    "truncated": False,
    "enabled": True,
    "pool_count": len(POOL_NAMES),
    "pools": [{"name": name} for name in POOL_NAMES],
}


def _scan(pool: str, *rows: LeaseRow, observed: bool = True):
    entries = [
        {
            "index": index,
            "return_kind": "object",
            "error": "",
            "row": {
                "ipAddress": row.ip,
                "macAddress": row.mac,
                "leaseTime": row.lease_time,
                "port": row.port,
            },
        }
        for index, row in enumerate(rows)
    ]
    entries.extend(
        {"index": index, "return_kind": "null", "error": "", "row": None}
        for index in range(len(entries), len(entries) + 2)
    )
    return classify_lease_scan(
        {
            "requested": pool,
            "found": observed,
            "name": pool,
            "max": 8,
            "window": len(entries),
            "entries": entries if observed else [],
            "error": "" if observed else "pool_absent",
        },
        pool_name=pool,
    )


def _reading(name: str, *, leased: bool) -> ClientReading:
    return ClientReading(
        name,
        True,
        mode=True,
        mac=MACS[name],
        ipv4=LEASES[name] if leased else "169.254.7.7",
        netmask=CLIENT_POOLS[name].netmask if leased else "255.255.0.0",
    )


def _binding(name: str, *, leased: bool) -> dict:
    pool = CLIENT_POOLS[name]
    return {
        "device": name,
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": LEASES[name] if leased else "169.254.7.7",
        "netmask": pool.netmask if leased else "255.255.0.0",
        "gateway_reads": [
            {"api": True, "error": "", "value": pool.gateway if leased else "0.0.0.0"}
        ],
        "dns_api": True,
        "dns_error": "",
        "dns_server": pool.dns_server if leased else "0.0.0.0",
    }


def _failed_binding(name: str, failure: str) -> dict:
    """Return a binding row the probe emitted although the lookup failed."""
    row = {**_binding(name, leased=False)}
    if failure == "error":
        row["error"] = "binding_read_failed"
    else:
        row["gateway_reads"] = [{"api": False, "error": "gateway_api_missing"}]
        row["dns_api"] = False
        row["dns_error"] = "dns_api_missing"
    return row


def _sample(
    index: int,
    leased: set[str],
    *,
    extra_rows=None,
    unread=(),
    failed_bindings=None,
    unobserved_pools=(),
    binding_overrides=None,
) -> AcquisitionSample:
    rows: dict[str, list[LeaseRow]] = {name: [] for name in POOL_NAMES}
    for name in sorted(leased):
        rows[CLIENT_POOLS[name].effective_pool_name].append(
            LeaseRow(0, LEASES[name], MACS[name], 3600.0, "FastEthernet0")
        )
    for pool, row in extra_rows or ():
        rows[pool].append(row)
    return AcquisitionSample(
        index=index,
        readings={
            name: _reading(name, leased=name in leased)
            for name in CLIENTS
            if name not in unread
        },
        bindings=[
            _failed_binding(name, failed_bindings[name])
            if failed_bindings and name in failed_bindings
            else {
                **_binding(name, leased=name in leased),
                **((binding_overrides or {}).get(name, {})),
            }
            for name in CLIENTS
        ],
        scans={
            name: _scan(name, *value, observed=name not in unobserved_pools)
            for name, value in rows.items()
        },
    )


def _arm(arm: str) -> set[str]:
    return {name for name, value in SP2_ACQUISITION_ARMS.items() if value == arm}


INTERVENED = {
    name: ("none" if arm == "control" else "dispatched")
    for name, arm in SP2_ACQUISITION_ARMS.items()
}


def _assess(*leased_per_sample: set[str], interventions=None, **kwargs):
    samples = [
        _sample(index, leased, **kwargs)
        for index, leased in enumerate(leased_per_sample, start=1)
    ]
    return assess_acquisition_arms(
        SP2_ACQUISITION_ARMS,
        {name: CLIENT_POOLS[name] for name in CLIENTS},
        interventions or INTERVENED,
        samples,
    )


# -- the window decision -----------------------------------------------------------


def test_explicit_start_alone_acquiring_is_its_own_pattern():
    """Two stable usable samples for every explicit start, nothing else."""
    start = _arm("explicit_start")
    result = _assess(set(), start, start)
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.facts["pattern"] == "explicit_start_only"
    assert set(result.facts["arms"]["explicit_start"]["acquired"]) == start


def test_one_usable_sample_is_not_an_acquisition():
    """A single usable reading is not a stable lease."""
    start = _arm("explicit_start")
    result = _assess(set(), set(), start)
    assert result.facts["pattern"] == "no_intervention_acquired"
    assert result.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED


def test_no_arm_acquiring_in_a_complete_window_is_negative():
    """Nobody acquiring across a fully read window is a negative observation."""
    result = _assess(set(), set(), set())
    assert result.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert result.facts["pattern"] == "no_intervention_acquired"


def test_a_control_that_acquires_confounds_every_arm():
    """A passive recovery makes no intervention attributable."""
    acquired = _arm("explicit_start") | {sorted(_arm("control"))[0]}
    result = _assess(set(), acquired, acquired)
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert result.facts["pattern"] == "control_acquired"


def test_a_partly_acquiring_arm_is_inconclusive():
    """One explicit start failing while another acquires decides nothing."""
    acquired = set(sorted(_arm("explicit_start"))[1:])
    result = _assess(set(), acquired, acquired)
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert result.facts["pattern"] == "partial"


def test_reassertion_and_explicit_start_together_are_named():
    """Both intervened arms acquiring is one pattern, not explicit-start-only."""
    acquired = _arm("explicit_start") | _arm("reassert")
    result = _assess(set(), acquired, acquired)
    assert result.facts["pattern"] == "explicit_start_and_reassertion"


def test_an_unknown_intervention_leaves_its_client_undecided():
    """Only a known dispatch lets an intervened client count."""
    unknown = sorted(_arm("explicit_start"))[0]
    interventions = {**INTERVENED, unknown: "outcome_unknown:acquisition_row_absent"}
    result = _assess(set(), set(), set(), interventions=interventions)
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert result.facts["pattern"] == "undecided"
    assert f"sp2_acquisition_client_undecided:{unknown}" in result.causes


def test_an_unread_client_without_acquisition_is_undecided_not_negative():
    """A missing reading is unknown, never an observed absence."""
    unread = sorted(_arm("control"))[0]
    result = _assess(set(), set(), set(), unread=(unread,))
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert f"sp2_acquisition_client_undecided:{unread}" in result.causes


@pytest.mark.parametrize("failure", ["error", "resolver_api"])
def test_a_failed_binding_read_without_acquisition_is_undecided(failure):
    """A binding row emitted for a failed lookup is no observation of absence."""
    control = sorted(_arm("control"))[0]
    result = _assess(set(), set(), set(), failed_bindings={control: failure})
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert result.facts["pattern"] == "undecided"
    assert f"sp2_acquisition_client_undecided:{control}" in result.causes


def test_a_row_in_a_competing_pool_withholds_the_acquisition():
    """An exact row in another pool contradicts attribution to the intended one."""
    start = _arm("explicit_start")
    hq = next(name for name in sorted(start) if name.startswith("HQ"))
    other = next(
        name for name in POOL_NAMES if name != CLIENT_POOLS[hq].effective_pool_name
    )
    competing = [(other, LeaseRow(0, LEASES[hq], MACS[hq], 3600.0, "FastEthernet0"))]
    result = _assess(set(), start, start, extra_rows=competing)
    assert result.facts["clients"][hq]["acquired"] is False
    assert any(entry["competing"] for entry in result.facts["clients"][hq]["samples"])
    assert result.facts["pattern"] == "partial"


def _hq_start() -> str:
    return next(
        name for name in sorted(_arm("explicit_start")) if name.startswith("HQ")
    )


def test_the_same_mac_elsewhere_in_another_pool_withholds_the_acquisition():
    """A competing row for the client's MAC at another address contradicts it."""
    start = _arm("explicit_start")
    hq = _hq_start()
    other = next(
        name for name in POOL_NAMES if name != CLIENT_POOLS[hq].effective_pool_name
    )
    elsewhere = [(other, LeaseRow(0, "10.99.99.99", MACS[hq], 3600.0, "Fa0"))]
    result = _assess(set(), start, start, extra_rows=elsewhere)
    assert result.facts["clients"][hq]["acquired"] is False
    assert result.facts["pattern"] != "explicit_start_only"


def test_an_unread_competing_pool_withholds_the_acquisition():
    """Absence of a competing lease is not shown while a pool is unread."""
    start = _arm("explicit_start")
    hq = _hq_start()
    other = next(
        name for name in POOL_NAMES if name != CLIENT_POOLS[hq].effective_pool_name
    )
    result = _assess(set(), start, start, unobserved_pools=(other,))
    assert result.facts["clients"][hq]["acquired"] is False
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE


def test_a_binding_for_another_address_withholds_the_acquisition():
    """The binding must describe the same address the lease row joins."""
    start = _arm("explicit_start")
    hq = _hq_start()
    pool = CLIENT_POOLS[hq]
    prefix, last = pool.lease_end.rsplit(".", 1)
    other_address = f"{prefix}.{last}"
    assert other_address != LEASES[hq]
    overrides = {hq: {"ipv4": other_address}}
    result = _assess(set(), start, start, binding_overrides=overrides)
    assert result.facts["clients"][hq]["acquired"] is False


def test_an_invalid_arm_binding_is_refused():
    """Arms and pools must name the same clients."""
    result = assess_acquisition_arms(
        SP2_ACQUISITION_ARMS, {}, INTERVENED, [_sample(1, set())]
    )
    assert result.causes == ["sp2_acquisition_arm_binding_invalid"]


# -- the precondition ----------------------------------------------------------------


def _precondition(readings=None, server=SERVER, scans=None):
    sample = _sample(1, set())
    return acquisition_precondition(
        CLIENTS,
        sample.readings if readings is None else readings,
        server,
        sample.scans if scans is None else scans,
        POOL_NAMES,
    )


def test_every_link_local_client_of_an_enabled_server_reproduces_episode_8():
    """The designed state: DHCP mode, 169.254/16, enabled planned pools, no rows."""
    result = _precondition()
    assert result.holds and result.causes == ()


def test_a_leased_or_unread_client_does_not_reproduce_episode_8():
    """Any client off the link-local state stops the arms."""
    sample = _sample(1, set())
    leased = sorted(CLIENTS)[0]
    readings = {
        **sample.readings,
        leased: _reading(leased, leased=True),
    }
    readings.pop(sorted(CLIENTS)[1])
    result = _precondition(readings=readings)
    assert not result.holds
    assert result.clients[leased] == "not_link_local"
    assert result.clients[sorted(CLIENTS)[1]] == "unobserved"


def test_a_disabled_server_or_unread_pool_does_not_reproduce_episode_8():
    """The server must be read enabled on exactly its planned pools."""
    assert (
        "server_not_enabled_on_planned_pools"
        in _precondition(server={**SERVER, "enabled": False}).causes
    )
    scans = dict(_sample(1, set()).scans)
    scans[POOL_NAMES[0]] = _scan(POOL_NAMES[0], observed=False)
    assert any(
        cause.startswith(f"pool_unscanned:{POOL_NAMES[0]}:")
        for cause in _precondition(scans=scans).causes
    )


def _absent(pool: str):
    """Return the reader's answer for a pool the server does not hold."""
    return classify_lease_scan(
        {"requested": pool, "found": False, "name": "", "error": ""}, pool_name=pool
    )


def test_an_absent_pool_does_not_reproduce_episode_8():
    """A pool the server does not hold was not scanned, whatever its flag says."""
    scans = dict(_sample(1, set()).scans)
    scans[POOL_NAMES[0]] = _absent(POOL_NAMES[0])
    result = _precondition(scans=scans)
    assert not result.holds
    assert any(POOL_NAMES[0] in cause for cause in result.causes)


@pytest.mark.parametrize("address", ["169.254.not-an-ip", "169.254.1", "169.2540.1.1"])
def test_a_malformed_link_local_address_does_not_reproduce_episode_8(address):
    """Only a parsed 169.254/16 address is link-local."""
    name = sorted(CLIENTS)[0]
    readings = dict(_sample(1, set()).readings)
    readings[name] = ClientReading(
        name, True, mode=True, mac=MACS[name], ipv4=address, netmask="255.255.0.0"
    )
    result = _precondition(readings=readings)
    assert not result.holds
    assert result.clients[name] != "link_local"


def test_an_absent_competing_pool_withholds_the_acquisition():
    """A competing pool the server does not hold proves no absence of rows."""
    start = _arm("explicit_start")
    hq = _hq_start()
    other = next(
        name for name in POOL_NAMES if name != CLIENT_POOLS[hq].effective_pool_name
    )
    samples = []
    for index in (1, 2, 3):
        sample = _sample(index, set() if index == 1 else start)
        scans = dict(sample.scans)
        scans[other] = _absent(other)
        samples.append(replace(sample, scans=scans))
    result = assess_acquisition_arms(
        SP2_ACQUISITION_ARMS,
        {name: CLIENT_POOLS[name] for name in CLIENTS},
        INTERVENED,
        samples,
    )
    assert result.facts["clients"][hq]["acquired"] is False


def test_a_pool_row_for_a_link_local_client_does_not_reproduce_episode_8():
    """A row for the client's MAC means the state is not plain link-local."""
    name = sorted(CLIENTS)[0]
    pool = CLIENT_POOLS[name].effective_pool_name
    scans = dict(_sample(1, set()).scans)
    scans[pool] = _scan(pool, LeaseRow(0, LEASES[name], MACS[name], 3600.0, "Fa0"))
    assert f"client_row_present:{name}:{pool}" in _precondition(scans=scans).causes


# -- the projections -------------------------------------------------------------------


def test_reassertion_projection_takes_the_ordinary_mode_path():
    """Native guard fields are cleared; mode and its read-back are kept."""
    names = sorted(_arm("reassert"))
    plan = sp2_acquisition_reassert_plan(
        CONTRACT.configuration_plan, device_names=names
    )
    assert sorted(item.device_name for item in plan.actions) == names
    for action in plan.actions:
        assert isinstance(action, SetEndpointDhcp)
        assert action.native_effective_pool_name == ""
        assert action.native_server_device_name == ""
        assert action.depends_on == []
    assert {item.action_id for item in plan.verification_expectations} == {
        item.id for item in plan.actions
    }
    with pytest.raises(ValueError):
        sp2_acquisition_reassert_plan(
            CONTRACT.configuration_plan, device_names=["NOT-A-CLIENT"]
        )


def test_explicit_start_projection_derives_one_acquisition_per_client():
    """Each start names its own segment's pool and waits on its server state."""
    names = sorted(_arm("explicit_start"))
    plan = sp2_acquisition_start_plan(
        CONTRACT.service_plan,
        CONTRACT.configuration_plan,
        device_names=names,
        nonce="run:sp2-acquisition",
    )
    starts = [item for item in plan.actions if isinstance(item, AcquireDhcpLease)]
    assert sorted(item.host_device_name for item in starts) == names
    states = {
        item.service_id: item.id
        for item in plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_SERVER_STATE
    }
    for item in starts:
        pool = CLIENT_POOLS[item.host_device_name]
        assert item.pool_name == pool.effective_pool_name
        assert item.depends_on == [pool.id]
        assert item.verification_dependencies == [states[pool.service_id]]
        assert item.nonce == "run:sp2-acquisition"
    source_server = [
        item
        for item in CONTRACT.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool | EnableServerDhcp)
    ]
    assert plan.actions[: len(source_server)] == source_server
    assert (
        plan.semantic_hash and plan.semantic_hash != CONTRACT.service_plan.semantic_hash
    )
    with pytest.raises(ValueError):
        sp2_acquisition_start_plan(
            CONTRACT.service_plan,
            CONTRACT.configuration_plan,
            device_names=names,
            nonce="",
        )


def test_projections_leave_the_composed_contract_unchanged():
    """The mixed contract's plans keep their hashes and their state-only shape."""
    before = (
        CONTRACT.configuration_plan.semantic_hash,
        CONTRACT.service_plan.semantic_hash,
        CONTRACT.configuration_plan.model_dump_json(),
        CONTRACT.service_plan.model_dump_json(),
    )
    sp2_acquisition_reassert_plan(
        CONTRACT.configuration_plan, device_names=sorted(_arm("reassert"))
    )
    sp2_acquisition_start_plan(
        CONTRACT.service_plan,
        CONTRACT.configuration_plan,
        device_names=sorted(_arm("explicit_start")),
        nonce="n",
    )
    assert before == (
        CONTRACT.configuration_plan.semantic_hash,
        CONTRACT.service_plan.semantic_hash,
        CONTRACT.configuration_plan.model_dump_json(),
        CONTRACT.service_plan.model_dump_json(),
    )
    assert not any(
        isinstance(item, AcquireDhcpLease) for item in CONTRACT.service_plan.actions
    )


def test_every_pool_has_an_explicit_start_and_a_control():
    """The fixed arm allocation exercises every physical pool."""
    by_pool: dict[str, set[str]] = {}
    for name, arm in SP2_ACQUISITION_ARMS.items():
        by_pool.setdefault(CLIENT_POOLS[name].effective_pool_name, set()).add(arm)
    assert set(by_pool) == set(POOL_NAMES)
    assert all({"explicit_start", "control"} <= arms for arms in by_pool.values())


def _raw_scan(pool: str, entries: list[dict], provenance=None):
    """Classify an explicit raw entry list exactly as the reader returns it."""
    return classify_lease_scan(
        {
            "requested": pool,
            "found": True,
            "name": pool,
            "max": 8,
            "window": len(entries),
            "entries": entries,
            "error": "",
            "reader_provenance": provenance or {},
        },
        pool_name=pool,
    )


def _null(index: int) -> dict:
    return {"index": index, "return_kind": "null", "error": "", "row": None}


def _native_end(index: int) -> dict:
    return {
        "index": index,
        "return_kind": "throw",
        "error": "invalid vector subscript",
        "end_semantics": "observed_native_index_end",
        "row": None,
    }


def _object(index: int, ip: str, mac: str) -> dict:
    return {
        "index": index,
        "return_kind": "object",
        "error": "",
        "row": {
            "ipAddress": ip,
            "macAddress": mac,
            "leaseTime": 3600.0,
            "port": "FastEthernet0",
        },
    }


def test_a_row_after_the_end_is_not_a_scanned_absence():
    """A null followed by a row is incoherent: absence is not shown."""
    name = sorted(CLIENTS)[0]
    pool = CLIENT_POOLS[name].effective_pool_name
    scans = dict(_sample(1, set()).scans)
    scans[pool] = _raw_scan(
        pool, [_null(0), _object(1, LEASES[name], MACS[name]), _null(2)]
    )
    assert scans[pool].observed
    assert not _precondition(scans=scans).holds


def test_a_hidden_competing_row_withholds_the_acquisition():
    """A competing pool whose rows run past its end cannot prove no conflict."""
    start = _arm("explicit_start")
    hq = _hq_start()
    other = next(
        name for name in POOL_NAMES if name != CLIENT_POOLS[hq].effective_pool_name
    )
    samples = []
    for index in (1, 2, 3):
        sample = _sample(index, set() if index == 1 else start)
        scans = dict(sample.scans)
        scans[other] = _raw_scan(
            other, [_null(0), _object(1, "10.99.0.1", MACS[hq]), _null(2)]
        )
        samples.append(replace(sample, scans=scans))
    result = assess_acquisition_arms(
        SP2_ACQUISITION_ARMS,
        {name: CLIENT_POOLS[name] for name in CLIENTS},
        INTERVENED,
        samples,
    )
    assert result.facts["clients"][hq]["acquired"] is False


def test_the_native_end_throw_is_a_scanned_end():
    """Positive control: this build's observed index-end throw ends a scan."""
    scans = {
        pool: _raw_scan(
            pool,
            [_native_end(0), _native_end(1)],
            provenance={"reader": "dhcp_lease_reader", "build": "9.0.1.0858"},
        )
        for pool in POOL_NAMES
    }
    assert _precondition(scans=scans).holds


def test_an_unexplained_throw_is_not_a_scanned_end():
    """A throw without the observed native end semantics proves nothing."""
    scans = dict(_sample(1, set()).scans)
    pool = POOL_NAMES[0]
    scans[pool] = _raw_scan(
        pool,
        [
            {"index": 0, "return_kind": "throw", "error": "boom", "row": None},
            {"index": 1, "return_kind": "throw", "error": "boom", "row": None},
        ],
        provenance={"reader": "dhcp_lease_reader"},
    )
    assert not _precondition(scans=scans).holds


def test_a_reading_without_a_usable_mac_is_undecided_not_negative():
    """A missing client identity is an incomplete observation."""
    control = sorted(_arm("control"))[0]
    samples = []
    for index in (1, 2, 3):
        sample = _sample(index, set())
        readings = dict(sample.readings)
        readings[control] = replace(readings[control], mac="")
        samples.append(replace(sample, readings=readings))
    result = assess_acquisition_arms(
        SP2_ACQUISITION_ARMS,
        {name: CLIENT_POOLS[name] for name in CLIENTS},
        INTERVENED,
        samples,
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert f"sp2_acquisition_client_undecided:{control}" in result.causes


def test_a_binding_for_another_address_is_undecided_not_negative():
    """Two readers disagreeing about the client's address observed nothing."""
    control = sorted(_arm("control"))[0]
    result = _assess(
        set(),
        set(),
        set(),
        binding_overrides={control: {"ipv4": "169.254.99.99"}},
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert f"sp2_acquisition_client_undecided:{control}" in result.causes
