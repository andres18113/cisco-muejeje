"""Grouped native DHCP evidence over controlled bridge observations.

Each test drives the real `PacketTracerEnterpriseServiceRuntime` group
evaluator. Only the bridge answers are controlled: the grouped lease scan and
the inactive-client reader receive scripted payloads per sample, and the server
policy reader, a separate observation with its own tests, reports VERIFIED.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import (
    native_dhcp_http_product_contract,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ActionExecutionStatus,
    ObservationFact,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    BridgeObservation,
    BridgeObservationKind,
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
    DispatchFact,
    ResultFact,
)

INTERFACE = "FastEthernet0"
MAC = {"PC1": "0001.0001.0001", "PC2": "0002.0002.0002", "PC3": "0003.0003.0003"}
FOREIGN_MAC = "00AA.00BB.00CC"
UNREADABLE = object()


def _leases(selected_count: int, start_offset: int = 124):
    contract = native_dhcp_http_product_contract(
        "9.0.1.0858",
        "group-evidence",
        selected_count=selected_count,
        start_offset=start_offset,
    )
    return [
        item
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    ]


def _group_expectations(
    selected_count: int = 2, *, reverse: bool = False, capacity: int | None = None
):
    """Return the runtime expectations the applicator would pass, by name.

    `capacity` widens the evaluator's own row bound past the selected count;
    the public product policy never does, so only table-shape tests use it.
    """
    leases = _leases(selected_count)
    group = [
        {
            "expectation_id": item.id,
            "device_name": item.client_device_name,
            "interface": item.expected["interface"],
        }
        for item in leases
    ]
    if reverse:
        group.reverse()
    expected = {
        **leases[0].expected,
        "native_selected_clients_json": json.dumps(group),
    }
    if capacity is not None:
        expected["max_users"] = capacity
        expected["lease_end"] = _address(capacity - 1)
    return {
        f"PC{index + 1}": item.model_copy(update={"expected": expected})
        for index, item in enumerate(leases)
    }, group


def _address(offset: int) -> str:
    return f"192.0.2.{125 + offset}"


def _client(item, reading):
    """Answer one selected port as the grouped scan script would."""
    if reading is UNREADABLE:
        return {
            **item,
            "found": True,
            "port_found": True,
            "mode": None,
            "mode_type": "error",
            "ipv4": "",
            "netmask": "",
            "mac": "",
            "error": "Error: client MAC getter failed",
        }
    ipv4, mac, mode = reading
    return {
        **item,
        "found": True,
        "port_found": True,
        "mode": mode,
        "mode_type": "boolean",
        "ipv4": ipv4,
        "netmask": "255.255.255.0" if ipv4 else "",
        "mac": mac,
        "error": "",
    }


def _row(ipv4: str, mac: str, port: str = INTERFACE) -> dict:
    return {"ipAddress": ipv4, "macAddress": mac, "leaseTime": 3600, "port": port}


def _short(device_name: str) -> str:
    """Map `Q3-DEFAULT-PC-02` to the `PC2` key the plans use."""
    return "PC" + str(int(device_name.rsplit("-", 1)[1]))


def _scan(group, readings: dict, rows: list[dict]) -> dict:
    """Build one grouped scan payload; readings are keyed by short name."""
    entries = [
        {
            "index": index,
            "return_kind": "object",
            "error": "",
            "row": {
                **row,
                **{
                    key + "_type": "number"
                    if type(value) in (int, float)
                    else "string"
                    if isinstance(value, str)
                    else "undefined"
                    for key, value in row.items()
                },
            },
        }
        for index, row in enumerate(rows)
    ]
    entries += [
        {"index": index, "return_kind": "null", "error": "", "row": None}
        for index in range(len(rows), len(rows) + 2)
    ]
    return {
        "entries": entries,
        "window": len(entries),
        "server_found": True,
        "process_found": True,
        "pool_found": True,
        "pool_name": "serverPool",
        "scan_error": "",
        "termination": "null",
        "error": "",
        # The snapshot reads its own pool inventory in the same dispatch.
        "inventory": ["serverPool"],
        "inventory_error": "",
        "competing": [],
        "clients": [
            _client(item, readings[_short(item["device_name"])]) for item in group
        ],
        "rows": rows,
    }


def _assigned(name: str, offset: int, *, mac: str | None = None, mode=True):
    return (_address(offset), mac or MAC[name], mode)


def _device(name: str) -> str:
    return f"Q3-DEFAULT-{name[:2]}-{int(name[2:]):02d}"


class _ScriptedBridge:
    """Answer the grouped scan and inactive reader from per-sample plans.

    A scan plan entry is a payload dict. An inactive plan entry is either a
    payload dict or None, which models a result that never arrived.
    """

    def __init__(self, scans, inactive=()):
        self.scans = list(scans)
        self.inactive = list(inactive)
        self.scripts: list[str] = []

    def dispatch_and_wait(self, js_code, _timeout):
        self.scripts.append(js_code)
        if "var group=" in js_code:
            body = self.scans.pop(0)
        elif "{device:name,interface:want" in js_code:
            body = self.inactive.pop(0)
        else:
            raise AssertionError("unexpected bridge read")
        if body is None:
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                result=ResultFact.NOT_OBSERVED,
                detail="scripted_result_lost",
            )
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=json.dumps(body),
        )


def _runtime(monkeypatch, bridge, samples: int = 3):
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda *_: None,
        dispatch_and_wait=bridge.dispatch_and_wait,
        sleeper=lambda _seconds: None,
    )
    runtime._dhcp_state_max_samples = samples
    runtime._dhcp_state_interval = 0.0
    monkeypatch.setattr(
        runtime,
        "_verify_dhcp_server_state",
        lambda _: SimpleNamespace(
            status=ActionExecutionStatus.VERIFIED,
            observed={"native_policy_json": "{}"},
        ),
    )
    return runtime


def _verify_group(runtime, expectations, trigger: str = "PC1"):
    """Verify the triggering client first, then its peers from the cache."""
    rows = {trigger: runtime.verify(expectations[trigger])}
    for name, expectation in expectations.items():
        if name != trigger:
            rows[name] = runtime.verify(expectation)
    return rows


def _readings(row) -> list[dict]:
    return json.loads(row.observed["client_readings_json"])


# -- R1: a local failure never hides a later global conflict -------------------


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("failing", ["PC2", "PC1"])
def test_prior_unreadable_client_still_enters_later_duplicate_census(
    monkeypatch, failing, reverse
):
    """The review counterexample, with either client failing and either order."""
    expectations, group = _group_expectations(reverse=reverse)
    positive = "PC1" if failing == "PC2" else "PC2"
    held = _assigned(positive, 0)
    rows = [_row(held[0], MAC[positive])]
    bridge = _ScriptedBridge(
        [
            _scan(group, {positive: held, failing: UNREADABLE}, rows),
            _scan(
                group,
                {positive: held, failing: (held[0], MAC[failing], True)},
                rows,
            ),
        ]
    )
    runtime = _runtime(monkeypatch, bridge)

    rows_by_name = _verify_group(runtime, expectations, trigger=positive)

    for name in ("PC1", "PC2"):
        row = rows_by_name[name]
        assert row.status is ActionExecutionStatus.FAILED, (name, row.cause)
        assert row.observation is ObservationFact.CONTRADICTED
        assert row.cause == "native_selected_identity_duplicate"
        assert row.observed["global_failure_sample"] == 2
    failed = rows_by_name[failing]
    assert failed.observed["local_failure_cause"] == (
        "native_client_identity_unobserved"
    )
    assert failed.observed["local_failure_sample"] == 1
    assert [item["reading"] for item in _readings(failed)] == [
        "unreadable",
        "assigned",
    ]
    assert _readings(failed)[1]["ipv4"] == held[0]
    assert rows_by_name[positive].observed["local_failure_cause"] == ""
    assert len(bridge.scans) == 0


def test_same_sample_mode_disabled_address_still_enters_the_census(monkeypatch):
    """A statically addressed disabled client is a local failure and a duplicate."""
    expectations, group = _group_expectations()
    held = _assigned("PC1", 0)
    scan = _scan(
        group,
        {"PC1": held, "PC2": (held[0], MAC["PC2"], False)},
        [_row(held[0], MAC["PC1"])],
    )
    bridge = _ScriptedBridge([scan, scan])

    rows = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert {row.cause for row in rows.values()} == {
        "native_selected_identity_duplicate"
    }
    assert rows["PC2"].observed["local_failure_cause"] == "native_client_mode_disabled"
    assert rows["PC1"].status is ActionExecutionStatus.FAILED


@pytest.mark.parametrize("delayed", [False, True])
def test_observed_duplicate_without_local_failure_blocks_every_client(
    monkeypatch, delayed
):
    """Immediate and delayed duplicates both stay global controls."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    pc2 = _assigned("PC2", 1)
    rows = [_row(pc1[0], MAC["PC1"]), _row(pc2[0], MAC["PC2"])]
    duplicate = _scan(group, {"PC1": pc1, "PC2": (pc1[0], MAC["PC2"], True)}, rows)
    scans = [_scan(group, {"PC1": pc1, "PC2": pc2}, rows), duplicate]
    bridge = _ScriptedBridge(scans if delayed else [duplicate])

    rows_by_name = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert {row.cause for row in rows_by_name.values()} == {
        "native_selected_identity_duplicate"
    }
    assert {row.observed["global_failure_sample"] for row in rows_by_name.values()} == {
        2 if delayed else 1
    }


@pytest.mark.parametrize("prior_failure", [False, True])
def test_unassigned_client_reporting_a_peer_mac_is_a_global_duplicate(
    monkeypatch, prior_failure
):
    """A second owner of PC1's MAC makes PC1's exact row ambiguous."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    rows = [_row(pc1[0], MAC["PC1"])]
    twin = ("0.0.0.0", MAC["PC1"], True)
    bridge = _ScriptedBridge(
        [
            _scan(
                group, {"PC1": pc1, "PC2": UNREADABLE if prior_failure else twin}, rows
            ),
            _scan(group, {"PC1": pc1, "PC2": twin}, rows),
            _scan(group, {"PC1": pc1, "PC2": twin}, rows),
        ]
    )

    rows_by_name = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert {row.cause for row in rows_by_name.values()} == {
        "native_selected_identity_duplicate"
    }
    assert {row.status for row in rows_by_name.values()} == {
        ActionExecutionStatus.FAILED
    }
    assert rows_by_name["PC1"].observed["global_failure_sample"] == (
        2 if prior_failure else 1
    )


@pytest.mark.parametrize(
    ("owner_mac", "twin_mac"),
    [
        ("0001.0001.0001", "00:01:00:01:00:01"),
        ("0001.0001.0001", "00-01-00-01-00-01"),
        ("00AA.00BB.00CC", "00aa.00bb.00cc"),
    ],
)
def test_equivalent_mac_spellings_are_one_identity(monkeypatch, owner_mac, twin_mac):
    """The parser accepts several spellings; the census compares the value."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0, mac=owner_mac)
    scan = _scan(
        group,
        {"PC1": pc1, "PC2": ("0.0.0.0", twin_mac, True)},
        [_row(pc1[0], owner_mac)],
    )
    bridge = _ScriptedBridge([scan, scan, scan])

    rows = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert {row.cause for row in rows.values()} == {
        "native_selected_identity_duplicate"
    }


def test_row_spelling_a_peer_mac_differently_is_still_a_selected_conflict(
    monkeypatch,
):
    """A row naming PC1's MAC in colon form on PC2's address is shared evidence."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    pc2 = _assigned("PC2", 1)
    scan = _scan(
        group,
        {"PC1": pc1, "PC2": pc2},
        [_row(pc1[0], MAC["PC1"]), _row(pc2[0], "00:01:00:01:00:01")],
    )
    bridge = _ScriptedBridge([scan, scan, scan])

    rows = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert {row.cause for row in rows.values()} == {"native_selected_lease_conflict"}


def test_exact_join_still_requires_the_same_mac_spelling(monkeypatch):
    """Canonical identity widens conflicts only; it never creates an exact row."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    pc2 = _assigned("PC2", 1)
    scan = _scan(
        group,
        {"PC1": pc1, "PC2": pc2},
        [_row(pc1[0], MAC["PC1"]), _row(pc2[0], "00:02:00:02:00:02")],
    )
    bridge = _ScriptedBridge([scan, scan, scan])

    rows = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert rows["PC1"].status is ActionExecutionStatus.VERIFIED
    assert rows["PC2"].status is ActionExecutionStatus.FAILED
    assert rows["PC2"].cause == "foreign_lease_row"


def test_unset_macs_of_addressed_clients_stay_local_failures(monkeypatch):
    """Two addressed clients with unset MACs name nobody, so PC0 stays positive."""
    expectations, group = _wide_group(3)
    scan = _scan(
        group,
        {
            "PC0": (_address(0), MAC["PC1"], True),
            "PC1": (_address(1), "", True),
            "PC2": (_address(2), "", True),
        },
        [_row(_address(0), MAC["PC1"])],
    )
    bridge = _ScriptedBridge([scan, scan, scan])
    runtime = _runtime(monkeypatch, bridge)

    rows = [runtime.verify(item) for item in expectations]

    assert rows[0].status is ActionExecutionStatus.VERIFIED, rows[0].cause
    assert [row.cause for row in rows[1:]] == ["native_client_outside_policy"] * 2
    assert {row.observed["global_failure_sample"] for row in rows} == {0}


def test_unparseable_addresses_name_no_shared_address(monkeypatch):
    """Two degraded address readings are local failures, not one address."""
    expectations, group = _wide_group(3)
    scan = _scan(
        group,
        {
            "PC0": (_address(0), MAC["PC1"], True),
            "PC1": ("undefined", MAC["PC2"], True),
            "PC2": ("undefined", MAC["PC3"], True),
        },
        [_row(_address(0), MAC["PC1"])],
    )
    bridge = _ScriptedBridge([scan, scan, scan])
    runtime = _runtime(monkeypatch, bridge)

    rows = [runtime.verify(item) for item in expectations]

    assert rows[0].status is ActionExecutionStatus.VERIFIED, rows[0].cause
    assert [row.cause for row in rows[1:]] == ["native_client_outside_policy"] * 2


def test_row_at_an_unparseable_address_is_not_a_selected_conflict(monkeypatch):
    """A degraded row address held by a degraded reading proves no ownership."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    scan = _scan(
        group,
        {"PC1": pc1, "PC2": ("undefined", MAC["PC2"], True)},
        [_row(pc1[0], MAC["PC1"]), _row("undefined", MAC["PC1"])],
    )
    bridge = _ScriptedBridge([scan, scan, scan])

    rows = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert all(row.status is ActionExecutionStatus.UNKNOWN for row in rows.values())
    assert rows["PC1"].cause == "native_pool_scan_incomplete"
    assert rows["PC2"].observed["local_failure_cause"] == "native_client_outside_policy"


def test_unset_macs_of_unassigned_clients_are_not_a_duplicate(monkeypatch):
    """Control: two empty MAC readings before acquisition name no identity."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    pc2 = _assigned("PC2", 1)
    rows = [_row(pc1[0], MAC["PC1"]), _row(pc2[0], MAC["PC2"])]
    unset = ("0.0.0.0", "", True)
    bridge = _ScriptedBridge(
        [
            _scan(group, {"PC1": unset, "PC2": unset}, []),
            _scan(group, {"PC1": pc1, "PC2": pc2}, rows),
            _scan(group, {"PC1": pc1, "PC2": pc2}, rows),
        ]
    )

    rows_by_name = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert {row.status for row in rows_by_name.values()} == {
        ActionExecutionStatus.VERIFIED
    }


@pytest.mark.parametrize("prior_failure", [False, True])
def test_row_naming_another_selected_client_is_a_global_conflict(
    monkeypatch, prior_failure
):
    """The pool recording one selected MAC on a peer's address is shared evidence."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    pc2 = _assigned("PC2", 1)
    first = _scan(
        group,
        {"PC1": pc1, "PC2": UNREADABLE if prior_failure else pc2},
        [_row(pc1[0], MAC["PC1"]), _row(pc2[0], MAC["PC2"])],
    )
    conflict = _scan(
        group,
        {"PC1": pc1, "PC2": pc2},
        [_row(pc1[0], MAC["PC1"]), _row(pc2[0], MAC["PC1"])],
    )
    bridge = _ScriptedBridge([first, conflict])

    rows = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert {row.cause for row in rows.values()} == {"native_selected_lease_conflict"}
    assert {row.status for row in rows.values()} == {ActionExecutionStatus.FAILED}
    assert _readings(rows["PC2"])[-1]["join"] == "selected_conflict"


def test_both_clients_positive_remain_verified(monkeypatch):
    """Positive control: two stable exact joins verify both clients."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    pc2 = _assigned("PC2", 1)
    rows = [_row(pc1[0], MAC["PC1"]), _row(pc2[0], MAC["PC2"])]
    scan = _scan(group, {"PC1": pc1, "PC2": pc2}, rows)
    bridge = _ScriptedBridge([scan, scan])

    rows_by_name = _verify_group(_runtime(monkeypatch, bridge), expectations)

    for name, row in rows_by_name.items():
        assert row.status is ActionExecutionStatus.VERIFIED, (name, row.cause)
        assert row.observed["stable_samples"] == 2
        assert row.observed["local_failure_cause"] == ""
        assert row.observed["global_failure_sample"] == 0
        assert [item["join"] for item in _readings(row)] == ["exact", "exact"]
    assert sum(bool(row.observed["group_trace_json"]) for row in rows_by_name.values())


@pytest.mark.parametrize(
    "later",
    ["unreadable", "distinct_exact", "foreign_party_row"],
)
def test_local_unreadable_client_does_not_invalidate_a_positive_peer(
    monkeypatch, later
):
    """Without a global reason, PC2's local failure stays PC2's alone."""
    expectations, group = _group_expectations()
    pc1 = _assigned("PC1", 0)
    pc2 = _assigned("PC2", 1)
    rows = [_row(pc1[0], MAC["PC1"])]
    if later == "distinct_exact":
        rows.append(_row(pc2[0], MAC["PC2"]))
    if later == "foreign_party_row":
        rows.append(_row(pc2[0], FOREIGN_MAC))
    second = UNREADABLE if later == "unreadable" else pc2
    bridge = _ScriptedBridge(
        [
            _scan(group, {"PC1": pc1, "PC2": UNREADABLE}, rows),
            _scan(group, {"PC1": pc1, "PC2": second}, rows),
        ]
    )

    rows_by_name = _verify_group(_runtime(monkeypatch, bridge), expectations)

    assert rows_by_name["PC1"].status is ActionExecutionStatus.VERIFIED
    assert rows_by_name["PC1"].observed["global_failure_sample"] == 0
    local = rows_by_name["PC2"]
    assert local.status is ActionExecutionStatus.UNKNOWN
    assert local.cause == "native_client_identity_unobserved"
    assert local.observed["local_failure_sample"] == 1
    assert _readings(local)[0]["reading"] == "unreadable"
    assert _readings(local)[1]["reading"] == (
        "unreadable" if later == "unreadable" else "assigned"
    )
    if later == "foreign_party_row":
        assert _readings(local)[1]["join"] == "foreign"


EPISODE_11_RECORD = (
    Path(__file__).resolve().parents[1]
    / "docs/reference/server-pt/evidence/dhcp-autonomy-02/e11/record"
    / "2026-09-26T14-07-49Z-9c285d5a.json"
)


def test_episode_11_results_stay_immutable_without_requalifying_old_scans(monkeypatch):
    """Preserve accepted results while refusing missing prospective index evidence.

    The immutable archive is read only; no missing observations are recreated.
    """
    record = json.loads(EPISODE_11_RECORD.read_text(encoding="utf-8"))
    archived = {
        row["expectation_id"]: row
        for row in record["service_result"]["verification_results"]
        if row.get("observed", {}).get("group_trace_ref")
    }
    [leader] = [row for row in archived.values() if row["observed"]["group_trace_json"]]
    trace = json.loads(leader["observed"]["group_trace_json"])
    group = [
        {key: item[key] for key in ("expectation_id", "device_name", "interface")}
        for item in trace[0]["lease_snapshot"]["clients"]
    ]
    expectations, _unused = _group_expectations()
    assert {item.id for item in expectations.values()} == set(archived)
    expected = {
        **expectations["PC1"].expected,
        "native_selected_clients_json": json.dumps(group),
    }
    # Explicit delta: the recorded snapshots predate the same-dispatch pool
    # inventory, so the current reader leaves them inconclusive as recorded.
    legacy = _runtime(
        monkeypatch, _ScriptedBridge([sample["lease_snapshot"] for sample in trace])
    )
    legacy_row = legacy.verify(
        expectations["PC1"].model_copy(update={"expected": expected})
    )
    assert legacy_row.status.value == "unknown"
    assert legacy_row.cause == "competing_pool_unobserved"
    # With the single-pool inventory the process actually had, every other
    # decision and value replays unchanged.
    bridge = _ScriptedBridge(
        [
            {
                **sample["lease_snapshot"],
                "inventory": ["serverPool"],
                "inventory_error": "",
                "competing": [],
            }
            for sample in trace
        ]
    )
    runtime = _runtime(monkeypatch, bridge)

    rows = {
        identifier: runtime.verify(
            next(
                item for item in expectations.values() if item.id == identifier
            ).model_copy(update={"expected": expected})
        )
        for identifier in sorted(
            archived, key=lambda item: item != leader["expectation_id"]
        )
    }

    # New prospective index evidence is absent in the original producer.
    # The modern reader refuses it, while immutable original conclusions and
    # client fields retain their original accepted meaning.
    assert bridge.scans
    assert all(row.status is ActionExecutionStatus.UNKNOWN for row in rows.values())
    assert {row.cause for row in rows.values()} == {"native_pool_scan_incomplete"}
    for stored in archived.values():
        assert stored["status"] == "verified"
        assert stored["cause"] == ""
        assert stored["observed"]["client_ipv4"]
        assert stored["observed"]["client_mac"]
        assert stored["observed"]["stable_samples"] == 2


# -- R2: one shared index per fresh scan -------------------------------------


class _CountingRow(dict):
    """A lease row that counts every field read the evaluator makes."""

    reads: dict[str, int]

    def __getitem__(self, key):
        self.reads[key] = self.reads.get(key, 0) + 1
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.reads[key] = self.reads.get(key, 0) + 1
        return super().get(key, default)


def _wide_group(client_count: int):
    """Build N selected expectations inside the evaluator's own 16-client bound.

    The public product admits at most two clients; a wider group exercises the
    evaluator's envelope only and claims no native capacity. Devices are named
    `PC-00` onwards, so scan readings are keyed `PC0` onwards.
    """
    [base] = _leases(1)
    group = [
        {
            "expectation_id": f"{base.id}/{index}",
            "device_name": f"PC-{index:02d}",
            "interface": INTERFACE,
        }
        for index in range(client_count)
    ]
    expected = {
        **base.expected,
        "lease_start": _address(0),
        "lease_end": _address(client_count - 1),
        "max_users": client_count,
        "native_selected_clients_json": json.dumps(group),
        "native_inactive_clients_json": "[]",
    }
    return [
        base.model_copy(update={"id": item["expectation_id"], "expected": expected})
        for item in group
    ], group


def _counted_group_run(monkeypatch, client_count: int) -> tuple[dict, list]:
    """Verify N positive clients over N rows for two samples; count row reads."""
    expectations, group = _wide_group(client_count)
    reads: dict[str, int] = {}

    def snapshot(*_args):
        rows = []
        for index in range(client_count):
            row = _CountingRow(_row(_address(index), f"0000.0000.{index:04d}"))
            row.reads = reads
            rows.append(row)
        return BridgeObservation(
            kind=BridgeObservationKind.PAYLOAD,
            payload={
                **_scan([], {}, []),
                "clients": [
                    _client(item, (_address(index), f"0000.0000.{index:04d}", True))
                    for index, item in enumerate(group)
                ],
                "rows": rows,
            },
            message="",
            outcome=BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTED, result=ResultFact.CORRELATED
            ),
        )

    runtime = _runtime(monkeypatch, _ScriptedBridge([]))
    monkeypatch.setattr(runtime, "_native_group_snapshot", snapshot)
    return reads, [runtime.verify(item) for item in expectations]


@pytest.mark.parametrize("client_count", [2, 4, 8, 16])
def test_group_join_reads_each_row_address_a_bounded_number_of_times(
    monkeypatch, client_count
):
    """Two samples of N clients over N rows read row addresses O(N), not O(N^2)."""
    reads, results = _counted_group_run(monkeypatch, client_count)

    assert {row.status for row in results} == {ActionExecutionStatus.VERIFIED}
    samples = 2
    # The reviewed method read 2*N*N addresses in its join alone.
    assert reads["ipAddress"] <= 2 * samples * client_count


def test_group_row_reads_grow_linearly_with_clients_and_rows(monkeypatch):
    """Total row field reads per client stay constant from 2 to 16 clients."""
    totals = {}
    for client_count in (2, 4, 8, 16):
        reads, _results = _counted_group_run(monkeypatch, client_count)
        totals[client_count] = sum(reads.values())

    per_client = {count: total / count for count, total in totals.items()}
    assert len(set(per_client.values())) == 1, totals


@pytest.mark.parametrize(
    ("extra", "status", "cause"),
    [
        ("duplicate_exact", ActionExecutionStatus.UNKNOWN, "native_lease_attribution"),
        ("foreign_mac", ActionExecutionStatus.FAILED, "foreign_lease_row"),
        ("foreign_port", ActionExecutionStatus.FAILED, "foreign_lease_row"),
    ],
)
def test_index_preserves_row_multiplicity_and_conflicting_evidence(
    monkeypatch, extra, status, cause
):
    """A last-wins index would hide the second row for the same address."""
    expectations, group = _group_expectations(capacity=3)
    pc1 = _assigned("PC1", 0)
    pc2 = _assigned("PC2", 1)
    second = {
        "duplicate_exact": _row(pc2[0], MAC["PC2"]),
        "foreign_mac": _row(pc2[0], FOREIGN_MAC),
        "foreign_port": _row(pc2[0], MAC["PC2"], "FastEthernet1"),
    }[extra]
    # The extra row comes last in one order and first in the other, so
    # neither a last-wins nor a first-wins map reaches both outcomes.
    for rows in (
        [_row(pc1[0], MAC["PC1"]), _row(pc2[0], MAC["PC2"]), second],
        [second, _row(pc1[0], MAC["PC1"]), _row(pc2[0], MAC["PC2"])],
    ):
        scan = _scan(group, {"PC1": pc1, "PC2": pc2}, rows)
        bridge = _ScriptedBridge([scan, scan, scan])

        rows_by_name = _verify_group(_runtime(monkeypatch, bridge), expectations)

        assert all(
            row.status is ActionExecutionStatus.UNKNOWN for row in rows_by_name.values()
        )
        assert rows_by_name["PC1"].cause == "native_pool_scan_incomplete"
        if extra != "duplicate_exact":
            assert rows_by_name["PC2"].observed["local_failure_cause"].startswith(cause)
        trace = json.loads(rows_by_name["PC1"].observed["group_trace_json"])
        snapshot = trace[0]["lease_snapshot"]
        assert len(snapshot["row_indices"]) == 3
        assert (
            len(
                [
                    entry
                    for entry in snapshot["entries"]
                    if entry["return_kind"] == "object"
                ]
            )
            == 3
        )


# -- R3: unreadable is not observed changed ----------------------------------


def _inactive_payload(*, mode=False, ipv4="", netmask=None, mac=MAC["PC2"], error=""):
    """Answer the inactive reader as its script would, including its catch."""
    return {
        "device": _device("PC2"),
        "interface": INTERFACE,
        "found": True,
        "port_found": True,
        "mode": mode,
        "mode_type": "error" if error else "boolean",
        "ipv4": ipv4,
        "netmask": netmask if netmask is not None else "255.255.255.0" if ipv4 else "",
        "mac": mac,
        "error": error,
    }


def _one_client_run(monkeypatch, second_inactive):
    """Sample 1 reads PC2 clear; sample 2 answers with `second_inactive`."""
    [lease] = _leases(1)
    group = [
        {
            "expectation_id": lease.id,
            "device_name": lease.client_device_name,
            "interface": lease.expected["interface"],
        }
    ]
    expectation = lease.model_copy(
        update={
            "expected": {
                **lease.expected,
                "native_selected_clients_json": json.dumps(group),
            }
        }
    )
    assert json.loads(expectation.expected["native_inactive_clients_json"]) == [
        {"device_name": _device("PC2"), "interface": INTERFACE}
    ]
    pc1 = (_address(0), MAC["PC1"], True)
    scan = _scan(
        group,
        {"PC1": pc1},
        [_row(pc1[0], MAC["PC1"])],
    )
    bridge = _ScriptedBridge(
        [scan, scan], inactive=[_inactive_payload(), second_inactive]
    )
    return _runtime(monkeypatch, bridge).verify(expectation)


@pytest.mark.parametrize(
    ("second", "detail"),
    [
        (_inactive_payload(mode=None, mac="", error="read_error"), "read_error"),
        (None, "unobserved:acceptance_unknown"),
        (_inactive_payload(mac="not-a-mac"), "reading_invalid"),
        (_inactive_payload(ipv4="undefined", netmask=""), "reading_invalid"),
        (_inactive_payload(netmask="undefined"), "reading_invalid"),
    ],
)
def test_valid_clear_then_unreadable_inactive_client_is_unobserved(
    monkeypatch, second, detail
):
    """A stored earlier MAC does not turn a later unknown into a change."""
    row = _one_client_run(monkeypatch, second)

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "native_inactive_client_unobserved"
    assert row.observed["global_failure_sample"] == 2
    assert row.observed["global_failure_detail"].startswith(
        f"{_device('PC2')}:{detail}"
    )


@pytest.mark.parametrize(
    ("second", "detail"),
    [
        (_inactive_payload(mode=True), "dhcp_mode_on"),
        (_inactive_payload(ipv4=_address(1)), "address_present"),
        (_inactive_payload(mac=MAC["PC3"]), "mac_changed"),
    ],
)
def test_genuine_inactive_client_change_is_contradicted(monkeypatch, second, detail):
    """Fresh mode, address or MAC readings stay contradictions."""
    row = _one_client_run(monkeypatch, second)

    assert row.status is ActionExecutionStatus.FAILED
    assert row.observation is ObservationFact.CONTRADICTED
    assert row.cause == "native_inactive_client_changed"
    assert row.observed["global_failure_detail"] == f"{_device('PC2')}:{detail}"


def test_inactive_mac_respelled_is_not_a_change(monkeypatch):
    """The same 48-bit MAC in another accepted spelling is still clear."""
    row = _one_client_run(monkeypatch, _inactive_payload(mac="00:02:00:02:00:02"))

    assert row.status is ActionExecutionStatus.VERIFIED, row.cause
    assert row.observed["global_failure_sample"] == 0


def test_two_inactive_ports_of_one_device_are_refused_not_changed(monkeypatch):
    """Per-device MAC history cannot hold two ports; both readers refuse early."""
    [lease] = _leases(1)
    group = [
        {
            "expectation_id": lease.id,
            "device_name": lease.client_device_name,
            "interface": lease.expected["interface"],
        }
    ]
    inactive = [
        {"device_name": _device("PC2"), "interface": INTERFACE},
        {"device_name": _device("PC2"), "interface": "FastEthernet1"},
    ]
    expectation = lease.model_copy(
        update={
            "expected": {
                **lease.expected,
                "native_selected_clients_json": json.dumps(group),
                "native_inactive_clients_json": json.dumps(inactive),
            }
        }
    )
    second_port = {**_inactive_payload(mac=MAC["PC3"]), "interface": "FastEthernet1"}
    single = expectation.model_copy(
        update={
            "expected": {
                key: value
                for key, value in expectation.expected.items()
                if key != "native_selected_clients_json"
            }
        }
    )

    for candidate, cause in (
        (expectation, "native_group_contract_invalid"),
        (single, "native_state_contract_invalid"),
    ):
        bridge = _ScriptedBridge([], inactive=[_inactive_payload(), second_port])

        row = _runtime(monkeypatch, bridge).verify(candidate)

        assert row.observation is ObservationFact.MALFORMED
        assert row.cause == cause
        assert bridge.scripts == []


@pytest.mark.parametrize(
    ("second_mac", "status"),
    [
        ("00:02:00:02:00:02", ActionExecutionStatus.VERIFIED),
        (MAC["PC3"], ActionExecutionStatus.FAILED),
    ],
)
def test_single_client_reader_compares_inactive_mac_values(
    monkeypatch, second_mac, status
):
    """The single-client reader applies the same value comparison as the group."""
    [lease] = _leases(1)
    expectation = lease.model_copy(
        update={
            "expected": {
                key: value
                for key, value in lease.expected.items()
                if key != "native_selected_clients_json"
            }
        }
    )
    reading = {
        "ipv4": _address(0),
        "netmask": "255.255.255.0",
        "mac": MAC["PC1"],
    }
    bridge = _ScriptedBridge(
        [], inactive=[_inactive_payload(), _inactive_payload(mac=second_mac)]
    )
    runtime = _runtime(monkeypatch, bridge, samples=2)
    entry = runtime._verify_dhcp_lease

    def client_reading(candidate):
        # The same method dispatches state-only leases to the reader under
        # test; only its inner client readback is substituted.
        if candidate.expected.get("state_only") is True:
            return entry(candidate)
        return SimpleNamespace(
            observation=ObservationFact.INCONCLUSIVE,
            claim_level="fresh_address_within_intended_allocation",
            observed={**reading, "dhcp_mode": True},
            cause="acquisition_unattributed",
        )

    monkeypatch.setattr(runtime, "_verify_dhcp_lease", client_reading)
    monkeypatch.setattr(
        runtime,
        "_verify_dhcp_lease_attributed",
        lambda _: SimpleNamespace(
            observation=ObservationFact.OBSERVED,
            status=ActionExecutionStatus.VERIFIED,
            observed={**reading, "matching_row_observed": True},
            cause="",
        ),
    )

    row = runtime.verify(expectation)

    assert row.status is status, row.cause
    assert bridge.inactive == []
