"""DF9 to DF11 and DF15: lease scans, calibration and per-client attribution.

Every rule here is decided from typed readings alone. The scans are the shape
the calibration probe returns: an explicit index window per pool, each index
with its return kind, raw row and any exception text.
"""

from __future__ import annotations

import pytest

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    MeasurementConclusion,
)
from packet_tracer_mcp.domain.enterprise.services import dhcp_lease_evidence as ev

INTENDED = "MCP_E6Q_DHCP"
NATIVE = "serverPool"
MAC_1 = "0001.0203.0401"
MAC_2 = "0001.0203.0402"
WINDOW_1 = ev.AddressRange("192.0.2.100", "192.0.2.100")
NATIVE_RANGE = ev.AddressRange("192.0.2.0", "192.0.3.255")
MASK = "255.255.255.0"


def _entry(index, row=None, *, kind=None, error=""):
    if error:
        return {"index": index, "return_kind": "throw", "error": error, "row": None}
    if row is None:
        return {"index": index, "return_kind": kind or "null", "error": "", "row": None}
    return {"index": index, "return_kind": "object", "error": "", "row": row}


def _row(ip, mac, lease=86400):
    return {
        "ipAddress": ip,
        "macAddress": mac,
        "leaseTime": lease,
        "port": "FastEthernet0",
    }


def _pool(name, entries, *, capacity=1, found=True):
    return {
        "requested": name,
        "found": found,
        "name": name if found else "",
        "max": capacity,
        "window": len(entries),
        "entries": entries,
        "error": "",
    }


def _scan(name, entries, capacity=1):
    return ev.classify_lease_scan(
        _pool(name, entries, capacity=capacity), pool_name=name
    )


def _empty(name=INTENDED, capacity=1, window=3):
    return _scan(name, [_entry(i) for i in range(window)], capacity)


def _with(rows, name=INTENDED, capacity=1, window=3):
    entries = [_entry(i, row) for i, row in enumerate(rows)]
    entries += [_entry(i) for i in range(len(rows), window)]
    return _scan(name, entries, capacity)


def _reading(client, mac, ip="0.0.0.0", mode=True):
    return ev.ClientReading(
        client, True, mode, mac, ip, MASK if ip != "0.0.0.0" else "0.0.0.0"
    )


# -- scan termination ----------------------------------------------------------------


def test_a_null_followed_only_by_nulls_is_a_clean_end():
    """The window keeps looking after the first null; nothing follows it."""
    scan = _with([_row("192.0.2.100", MAC_1)])
    assert scan.clean and scan.termination == ev.TERMINATION_NULL
    assert scan.first_null == 1 and [row.index for row in scan.rows] == [0]
    assert len(scan.entries) == 3


@pytest.mark.parametrize(
    ("entries", "termination"),
    [
        (
            [_entry(0), _entry(1, _row("192.0.2.100", MAC_1)), _entry(2)],
            ev.TERMINATION_NON_MONOTONE,
        ),
        (
            [
                _entry(0, _row("192.0.2.100", MAC_1)),
                _entry(1, error="index"),
                _entry(2),
            ],
            ev.TERMINATION_THROW,
        ),
        (
            [
                _entry(0, _row("192.0.2.100", MAC_1)),
                _entry(1, _row("192.0.2.100", MAC_1)),
                _entry(2),
            ],
            ev.TERMINATION_REPEAT,
        ),
        (
            [
                _entry(
                    0,
                    {
                        "ipAddress": "not-an-ip",
                        "macAddress": MAC_1,
                        "leaseTime": 1,
                        "port": "Fa0",
                    },
                )
            ],
            ev.TERMINATION_MALFORMED,
        ),
        (
            [_entry(0, {**_row("192.0.2.100", MAC_1), "leaseTime": True})],
            ev.TERMINATION_MALFORMED,
        ),
        ([_entry(0, _row("192.0.2.100", MAC_1))], ev.TERMINATION_WINDOW),
    ],
    ids=["row-after-null", "throw", "repeat", "bad-ip", "bool-lease", "no-null"],
)
def test_nothing_but_a_trailing_run_of_nulls_is_an_end(entries, termination):
    """A throw, a repeat, a later row or an exhausted window never ends a table."""
    scan = _scan(INTENDED, entries)
    assert scan.observed and not scan.clean
    assert scan.termination == termination


def test_an_absent_or_incoherent_pool_is_not_an_empty_table():
    """A missing pool and a malformed window say nothing about rows."""
    absent = ev.classify_lease_scan(
        _pool(INTENDED, [], found=False), pool_name=INTENDED
    )
    assert absent.termination == ev.TERMINATION_POOL_ABSENT and not absent.clean
    broken = _pool(INTENDED, [_entry(0), _entry(2)])
    assert (
        ev.classify_lease_scan(broken, pool_name=INTENDED).cause
        == "scan_window_incoherent"
    )
    other = ev.classify_lease_scan(_pool(NATIVE, [_entry(0)]), pool_name=INTENDED)
    assert other.cause == "scan_pool_not_answered"


def test_named_pool_lookup_error_is_not_observed_absence():
    """A thrown getPool cannot prove the competing logical pool is absent."""
    row = _pool(INTENDED, [], found=False)
    row["error"] = "getPool threw"
    scan = ev.classify_lease_scan(row, pool_name=INTENDED)
    assert scan.observed is False
    assert scan.cause == "pool_lookup_error"


def test_found_pool_with_different_physical_name_is_not_attributed():
    """A matching lease row from another returned object has unknown identity."""
    row = _pool(NATIVE, [_entry(0, _row("192.0.2.100", MAC_1))])
    row["name"] = "otherPool"
    scan = ev.classify_lease_scan(row, pool_name=NATIVE)
    assert scan.observed is False
    assert scan.cause == "scan_pool_identity_mismatch"


def test_an_undefined_read_is_not_a_null_end():
    """Only an observed null ends rows; undefined is kept distinct and unclean."""
    scan = _scan(INTENDED, [_entry(index, kind="undefined") for index in range(3)])
    assert scan.observed and not scan.clean
    assert scan.termination == ev.TERMINATION_UNDEFINED
    result = ev.assess_lease_calibration(
        [
            ev.CalibrationState("empty", scan),
            ev.CalibrationState("one", _with([_row("192.0.2.100", MAC_1)])),
        ],
        pool=INTENDED,
        capacity=1,
        fixture_macs=[MAC_1, MAC_2],
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert result.null_ends_rows is False


def test_an_exact_row_never_hides_a_same_ip_row_with_another_mac():
    """A same-IP foreign MAC is a contradiction even beside the exact row."""
    scan = _with(
        [_row("192.0.2.100", MAC_1), _row("192.0.2.100", MAC_2)], capacity=2, window=4
    )
    reading = _reading("pc1", MAC_1, "192.0.2.100")
    assert ev.row_status(scan, reading, None) == ev.ROW_WRONG_MAC
    result = _attribute(_reading("pc1", MAC_1), reading, scan, _empty(NATIVE, 512, 4))
    assert result.contradictions == ("intended:" + ev.ROW_WRONG_MAC,)
    assert result.served_by != ev.SERVED_INTENDED


def test_the_throw_text_and_every_raw_entry_are_retained():
    """A getter failure is evidence, kept whole, never a quiet end of table."""
    scan = _scan(INTENDED, [_entry(0, error="Invalid index")])
    assert scan.entries[0]["error"] == "Invalid index"
    assert scan.as_facts()["entries"][0]["return_kind"] == "throw"


# -- calibration ------------------------------------------------------------------------


def _states(*scans):
    return [ev.CalibrationState(f"s{i}", scan) for i, scan in enumerate(scans)]


def test_capacity_one_calibrates_but_cannot_tell_one_row_from_full():
    """Empty and full are observed; the limitation names what is identical."""
    result = ev.assess_lease_calibration(
        _states(_empty(), _with([_row("192.0.2.100", MAC_1)])),
        pool=INTENDED,
        capacity=1,
        fixture_macs=[MAC_1, MAC_2],
    )
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.null_ends_rows is True
    assert result.kinds == (ev.STATE_EMPTY, ev.STATE_FULL)
    assert "one_row_and_full_states_are_identical_at_capacity_one" in result.limitations


def test_capacity_two_discriminates_one_row_from_full():
    """The minimal additional case: a null below capacity ends the rows."""
    result = ev.assess_lease_calibration(
        _states(
            _empty(capacity=2, window=4),
            _with([_row("192.0.2.100", MAC_1)], capacity=2, window=4),
            _with(
                [_row("192.0.2.100", MAC_1), _row("192.0.2.101", MAC_2)],
                capacity=2,
                window=4,
            ),
        ),
        pool=INTENDED,
        capacity=2,
        fixture_macs=[MAC_1, MAC_2],
    )
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.kinds == (ev.STATE_EMPTY, ev.STATE_ONE_ROW, ev.STATE_FULL)
    assert "one_row_and_full_states_discriminated" in result.limitations


@pytest.mark.parametrize(
    ("scans", "cause"),
    [
        ((_with([_row("192.0.2.100", MAC_1)]),), "no_empty_state_observed"),
        ((_empty(),), "no_non_empty_state_observed"),
        (
            (_empty(), _scan(INTENDED, [_entry(0, error="x"), _entry(1), _entry(2)])),
            "s1:scan_not_clean:throw",
        ),
        (
            (_empty(), _with([_row("192.0.2.100", "00aa.bbcc.ddee")])),
            "s1:row_not_from_a_fixture_client",
        ),
    ],
    ids=["no-empty", "no-rows", "throw", "foreign-row"],
)
def test_calibration_without_its_states_stays_inconclusive(scans, cause):
    """No state is assumed, no row is fabricated and a throw is not an end."""
    result = ev.assess_lease_calibration(
        _states(*scans), pool=INTENDED, capacity=1, fixture_macs=[MAC_1, MAC_2]
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert result.null_ends_rows is False
    assert cause in result.causes


def test_more_rows_than_the_capacity_is_a_contradiction():
    """A one-user pool holding two rows contradicts its configuration."""
    result = ev.assess_lease_calibration(
        _states(
            _empty(),
            _with([_row("192.0.2.100", MAC_1), _row("192.0.2.101", MAC_2)], window=4),
        ),
        pool=INTENDED,
        capacity=1,
        fixture_macs=[MAC_1, MAC_2],
    )
    assert result.conclusion is MeasurementConclusion.CONTRADICTED


# -- rows, addressing and attribution --------------------------------------------------------


def _calibrated():
    return ev.assess_lease_calibration(
        _states(_empty(), _with([_row("192.0.2.100", MAC_1)])),
        pool=INTENDED,
        capacity=1,
        fixture_macs=[MAC_1, MAC_2],
    )


@pytest.mark.parametrize(
    ("rows", "reading", "status"),
    [
        (
            [_row("192.0.2.100", MAC_1)],
            _reading("pc1", MAC_1, "192.0.2.100"),
            ev.ROW_EXACT,
        ),
        (
            [_row("192.0.2.100", MAC_2)],
            _reading("pc1", MAC_1, "192.0.2.100"),
            ev.ROW_WRONG_MAC,
        ),
        (
            [_row("192.0.2.100", "00:01:02:03:04:01")],
            _reading("pc1", MAC_1, "192.0.2.100"),
            ev.ROW_REPRESENTATION,
        ),
        (
            [_row("192.0.2.100", MAC_1)],
            _reading("pc1", MAC_1, "192.0.2.7"),
            ev.ROW_MAC_ELSEWHERE,
        ),
        (
            [_row("192.0.2.100", MAC_1)],
            _reading("pc1", MAC_1, "0.0.0.0"),
            ev.ROW_WITHOUT_PORT_ADDRESS,
        ),
        (
            [_row("192.0.2.100", MAC_1)],
            _reading("pc2", MAC_2, "192.0.2.7"),
            ev.ABSENT_CALIBRATED,
        ),
    ],
    ids=[
        "exact",
        "wrong-mac",
        "representation",
        "mac-elsewhere",
        "no-port-address",
        "absent",
    ],
)
def test_a_client_stands_in_a_pool_by_its_exact_text(rows, reading, status):
    """Exact IP and MAC text decide presence; a same-IP other MAC contradicts."""
    assert ev.row_status(_with(rows), reading, _calibrated()) == status


def test_absence_is_calibrated_only_by_the_same_pools_states():
    """Without calibration a clean null end is uncalibrated; unclean is incomplete."""
    scan = _with([_row("192.0.2.100", MAC_1)])
    reading = _reading("pc2", MAC_2, "192.0.2.7")
    assert ev.row_status(scan, reading, None) == ev.ABSENT_UNCALIBRATED
    unclean = _scan(INTENDED, [_entry(0, _row("192.0.2.100", MAC_1))])
    assert ev.row_status(unclean, reading, _calibrated()) == ev.ABSENT_INCOMPLETE


def _attribute(
    before,
    after,
    intended,
    native,
    prior_intended=None,
    prior_native=None,
    request="dispatched",
):
    return ev.attribute_client(
        after.client,
        request=request,
        before=before,
        after=after,
        prior_intended=prior_intended or _empty(),
        prior_native=prior_native or _empty(NATIVE, 512, 4),
        intended=intended,
        native=native,
        intended_range=WINDOW_1,
        native_range=NATIVE_RANGE,
        netmask=MASK,
        intended_calibration=_calibrated(),
        native_calibration=None,
    )


def test_an_intended_row_after_a_request_with_prior_absence_is_causal():
    """Every claim is separate, and each carries its limits."""
    result = _attribute(
        _reading("pc1", MAC_1),
        _reading("pc1", MAC_1, "192.0.2.100"),
        _with([_row("192.0.2.100", MAC_1)]),
        _empty(NATIVE, 512, 4),
    )
    assert result.served_by == ev.SERVED_INTENDED
    assert result.intended_row == ev.ROW_EXACT
    assert result.native_row == ev.ABSENT_UNCALIBRATED
    assert result.causal == "supported_after_request_with_prior_absence_observed"
    assert ev.NO_BACKGROUND_PROOF in result.as_facts()["limitations"]


def test_service_from_the_native_default_is_its_own_result():
    """An address in both ranges is attributed only by the row that holds it."""
    result = _attribute(
        _reading("pc1", MAC_1),
        _reading("pc1", MAC_1, "192.0.2.1"),
        _empty(),
        _with([_row("192.0.2.1", MAC_1)], NATIVE, 512, 4),
    )
    assert result.served_by == ev.SERVED_NATIVE
    assert result.addressing_after == "inside_native_range_only"
    assert result.causal.startswith("supported_")


@pytest.mark.parametrize(
    ("before", "requested", "cause"),
    [
        (
            _reading("pc1", MAC_1, "192.0.2.100"),
            "dispatched",
            "not_established:address_before_request",
        ),
        (
            _reading("pc1", MAC_1),
            "not_dispatched",
            "not_established:request_not_dispatched",
        ),
    ],
)
def test_causality_needs_a_request_and_an_observed_prior_absence(
    before, requested, cause
):
    """An address present before the request, or no request, is not causal."""
    result = _attribute(
        before,
        _reading("pc1", MAC_1, "192.0.2.100"),
        _with([_row("192.0.2.100", MAC_1)]),
        _empty(NATIVE, 512, 4),
        request=requested,
    )
    assert result.causal.startswith(cause)


def test_a_prior_row_for_the_client_blocks_causality():
    """A lease already in a table before the request was not caused by it."""
    prior = _with([_row("192.0.2.100", MAC_1)])
    result = _attribute(
        _reading("pc1", MAC_1),
        _reading("pc1", MAC_1, "192.0.2.100"),
        _with([_row("192.0.2.100", MAC_1)]),
        _empty(NATIVE, 512, 4),
        prior_intended=prior,
    )
    assert result.causal.startswith("not_established:prior_rows_not_observed_absent")


def test_rows_in_both_pools_are_ambiguous_not_a_choice():
    """The observations are reported, never resolved by preference."""
    result = _attribute(
        _reading("pc1", MAC_1),
        _reading("pc1", MAC_1, "192.0.2.100"),
        _with([_row("192.0.2.100", MAC_1)]),
        _with([_row("192.0.2.100", MAC_1)], NATIVE, 512, 4),
    )
    assert result.served_by == ev.SERVED_BOTH
    assert result.causal == "not_established:served_by:" + ev.SERVED_BOTH


# -- the capacity-one negative ------------------------------------------------------------


def _pair(second_after, native_after):
    full = _with([_row("192.0.2.100", MAC_1)])
    first = _attribute(
        _reading("pc1", MAC_1),
        _reading("pc1", MAC_1, "192.0.2.100"),
        full,
        _empty(NATIVE, 512, 4),
    )
    second = _attribute(
        _reading("pc2", MAC_2),
        second_after,
        full,
        native_after,
        prior_intended=full,
    )
    return ev.assess_capacity_one_negative(
        first=first, second=second, intended=full, capacity=1
    )


def test_the_capacity_one_negative_from_completed_negatives():
    """No address, a full pool with the first row and a calibrated absence."""
    result = _pair(_reading("pc2", MAC_2), _empty(NATIVE, 512, 4))
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.result == "lease_not_acquired:no_address_within_settle_window"


def test_native_default_service_is_preserved_beside_the_negative():
    """Being served by `serverPool` is not intended-pool success or exhaustion."""
    result = _pair(
        _reading("pc2", MAC_2, "192.0.2.1"),
        _with([_row("192.0.2.1", MAC_2)], NATIVE, 512, 4),
    )
    assert result.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert result.result == "lease_not_acquired:served_by_native_default"


def test_a_pool_the_first_client_never_filled_decides_nothing():
    """If the first client was served elsewhere, the negative is not reached."""
    empty = _empty()
    first = _attribute(
        _reading("pc1", MAC_1),
        _reading("pc1", MAC_1, "192.0.2.1"),
        empty,
        _with([_row("192.0.2.1", MAC_1)], NATIVE, 512, 4),
    )
    second = _attribute(
        _reading("pc2", MAC_2),
        _reading("pc2", MAC_2, "192.0.2.2"),
        empty,
        _with([_row("192.0.2.1", MAC_1), _row("192.0.2.2", MAC_2)], NATIVE, 512, 4),
    )
    result = ev.assess_capacity_one_negative(
        first=first, second=second, intended=empty, capacity=1
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "intended_pool_not_full_with_the_first_client" in result.causes


def test_an_uncalibrated_absence_is_not_a_negative():
    """A throw after the first row leaves the second client's absence incomplete."""
    unclean = _scan(
        INTENDED,
        [_entry(0, _row("192.0.2.100", MAC_1)), _entry(1, error="index"), _entry(2)],
    )
    full = _with([_row("192.0.2.100", MAC_1)])
    first = _attribute(
        _reading("pc1", MAC_1),
        _reading("pc1", MAC_1, "192.0.2.100"),
        full,
        _empty(NATIVE, 512, 4),
    )
    second = _attribute(
        _reading("pc2", MAC_2),
        _reading("pc2", MAC_2),
        unclean,
        _empty(NATIVE, 512, 4),
        prior_intended=full,
    )
    assert second.intended_row == ev.ABSENT_INCOMPLETE
    result = ev.assess_capacity_one_negative(
        first=first, second=second, intended=unclean, capacity=1
    )
    assert result.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert any(
        item.startswith("second_client_absence_not_calibrated")
        for item in result.causes
    )


def test_a_second_intended_row_on_a_one_user_pool_contradicts():
    """Two clients in a one-user pool is not a negative at all."""
    full = _with([_row("192.0.2.100", MAC_1)])
    first = _attribute(
        _reading("pc1", MAC_1),
        _reading("pc1", MAC_1, "192.0.2.100"),
        full,
        _empty(NATIVE, 512, 4),
    )
    second = _attribute(
        _reading("pc2", MAC_2),
        _reading("pc2", MAC_2, "192.0.2.100"),
        _with([_row("192.0.2.100", MAC_2)]),
        _empty(NATIVE, 512, 4),
        prior_intended=full,
    )
    result = ev.assess_capacity_one_negative(
        first=first, second=second, intended=full, capacity=1
    )
    assert result.conclusion is MeasurementConclusion.CONTRADICTED


# -- DF15: linear work per client -------------------------------------------------------------


@pytest.mark.parametrize("clients", [2, 20, 200, 1000])
def test_attribution_is_linear_in_clients_and_rows(clients, monkeypatch):
    """Each scan is indexed once; each client is lookups, never all pairs."""
    calls = {"count": 0}
    original = ev.normalized_mac

    def counted(value):
        calls["count"] += 1
        return original(value)

    monkeypatch.setattr(ev, "normalized_mac", counted)
    macs = [
        f"0001.{index // 65536:04x}.{index % 65536:04x}" for index in range(clients)
    ]
    addresses = [
        f"10.{index // 65536}.{(index // 256) % 256}.{index % 256}"
        for index in range(clients)
    ]
    rows = [_row(ip, mac) for ip, mac in zip(addresses, macs, strict=True)]
    scan = _with(rows, capacity=clients, window=clients + 2)
    for ip, mac in zip(addresses, macs, strict=True):
        status = ev.row_status(scan, _reading("c", mac, ip), None)
        assert status == ev.ROW_EXACT
    # Index construction touches each row once; each lookup normalizes the
    # client's own MAC and its one same-IP row. All pairs would be clients**2.
    assert calls["count"] <= 4 * clients + 8
