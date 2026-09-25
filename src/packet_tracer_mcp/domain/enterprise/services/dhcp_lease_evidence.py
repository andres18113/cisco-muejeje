"""What a bounded Server-PT lease-table reading establishes, and what it does not.

Cisco documents `DhcpPool.getLeaseAt(int)` and nothing else about the table:
no count, no end condition, no statement about what an index past the last
lease returns. A capacity (`getMaxUsers`) is configuration, not a count. So
this module never assumes an end of table. It classifies what one explicit
index window returned, derives a calibration verdict only from states the same
run observed, and keeps each client claim separate:

- native client addressing (what the port reports);
- an exact IP/MAC row in the intended pool, or in the native default;
- a same-IP row with another MAC, which is a contradiction;
- absence, which is *calibrated* only when the same pool's scans in this run
  showed that a null ends the rows, and is otherwise incomplete;
- causal acquisition, which needs a dispatched request, observed prior
  absence and an observed result, and still does not prove DORA internals or
  that no background traffic occurred.

Everything is pure and linear: each scan is indexed by MAC and by address
once, and each client is a lookup, never a comparison against every other
client.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models.service_qualification import MeasurementConclusion

_IPV4 = re.compile(
    r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}"
)
#: The dotted MAC text Packet Tracer's port getter returns.
_MAC_TEXT = re.compile(r"[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}")
_HEX = re.compile(r"[^0-9a-f]")

#: How one scan ended.
TERMINATION_NULL = "null"
#: `undefined` is not `null`. The probe keeps them apart and so does the
#: classification: only an observed null can end the rows.
TERMINATION_UNDEFINED = "undefined"
TERMINATION_WINDOW = "window_exhausted"
TERMINATION_THROW = "throw"
TERMINATION_NON_MONOTONE = "non_monotone"
TERMINATION_REPEAT = "repeat"
TERMINATION_MALFORMED = "malformed"
TERMINATION_POOL_ABSENT = "pool_absent"
TERMINATION_UNOBSERVED = "unobserved"
_CLEAN = frozenset({TERMINATION_NULL})

#: What one clean state of a pool was, by its observed rows and capacity.
STATE_EMPTY = "empty"
STATE_ONE_ROW = "one_row_not_full"
STATE_PARTIAL = "partial"
STATE_FULL = "full"
STATE_OVER_CAPACITY = "over_capacity"

#: How one client stands in one pool.
ROW_EXACT = "exact_ip_mac_row"
ROW_WRONG_MAC = "same_ip_other_mac"
ROW_MAC_ELSEWHERE = "mac_on_another_address"
ROW_WITHOUT_PORT_ADDRESS = "mac_row_while_port_reports_no_address"
ROW_REPRESENTATION = "mac_matches_only_after_normalization"
ABSENT_CALIBRATED = "absent_after_calibrated_scan"
ABSENT_UNCALIBRATED = "absent_null_terminated_uncalibrated"
ABSENT_INCOMPLETE = "absent_scan_incomplete"
ROW_UNOBSERVED = "scan_unobserved"

#: Which pool the observations attribute one client's address to.
SERVED_INTENDED = "intended_pool"
SERVED_NATIVE = "native_default"
SERVED_BOTH = "ambiguous_rows_in_both_pools"
SERVED_NONE = "no_address_observed"
SERVED_UNKNOWN = "address_without_attributing_row"

CALIBRATION_IS_LOCAL = (
    "calibration_holds_for_this_run_pool_and_build_only:"
    "getLeaseAt_documents_no_end_condition"
)
NO_BACKGROUND_PROOF = "no_explicit_request_is_not_proof_of_absent_background_traffic"
NOT_DORA = "a_matching_row_proves_presence_not_dora_internals_or_exclusivity"


@dataclass(frozen=True)
class LeaseRow:
    """One non-null `getLeaseAt` answer with usable identity."""

    index: int
    ip: str
    mac: str
    lease_time: float
    port: str


@dataclass(frozen=True)
class LeaseScan:
    """One pool's explicit index window, as read and as classified."""

    pool: str
    observed: bool
    cause: str = ""
    capacity: int | None = None
    window: int = 0
    rows: tuple[LeaseRow, ...] = ()
    termination: str = TERMINATION_UNOBSERVED
    first_null: int | None = None
    entries: tuple[Mapping[str, Any], ...] = ()
    _by_ip: Mapping[str, tuple[LeaseRow, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _by_mac: Mapping[str, tuple[LeaseRow, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _by_normalized_mac: Mapping[str, tuple[LeaseRow, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )

    @property
    def clean(self) -> bool:
        """Whether the scan ended at a null with nothing after it in the window."""
        return self.observed and self.termination in _CLEAN

    def rows_with_ip(self, ip: str) -> tuple[LeaseRow, ...]:
        """Return every row carrying one address."""
        return self._by_ip.get(ip, ())

    def rows_with_mac(self, mac: str) -> tuple[LeaseRow, ...]:
        """Return every row carrying one MAC text, exactly."""
        return self._by_mac.get(mac, ())

    def rows_with_normalized_mac(self, mac: str) -> tuple[LeaseRow, ...]:
        """Return every row whose MAC has the same hex digits."""
        return self._by_normalized_mac.get(normalized_mac(mac), ())

    def as_facts(self) -> dict[str, Any]:
        """Return the JSON-ready facts the record keeps for this scan."""
        return {
            "pool": self.pool,
            "observed": self.observed,
            "cause": self.cause,
            "capacity": self.capacity,
            "window": self.window,
            "termination": self.termination,
            "first_null": self.first_null,
            "rows": [
                {
                    "index": row.index,
                    "ip": row.ip,
                    "mac": row.mac,
                    "lease_time": row.lease_time,
                    "port": row.port,
                }
                for row in self.rows
            ],
            "entries": [dict(item) for item in self.entries],
        }


def is_dotted_mac(value: object) -> bool:
    """Whether one value is the dotted-hex MAC text a Packet Tracer port reports."""
    return isinstance(value, str) and bool(_MAC_TEXT.fullmatch(value))


def normalized_mac(value: str) -> str:
    """Return a MAC's hex digits only, lower case, for a representation check."""
    return _HEX.sub("", str(value).lower())


def _group(rows: Iterable[LeaseRow], key) -> dict[str, tuple[LeaseRow, ...]]:
    grouped: dict[str, list[LeaseRow]] = {}
    for row in rows:
        grouped.setdefault(key(row), []).append(row)
    return {name: tuple(items) for name, items in grouped.items()}


def _indexed(scan: LeaseScan) -> LeaseScan:
    """Attach the three lookups one scan is asked about, built once."""
    object.__setattr__(scan, "_by_ip", _group(scan.rows, lambda row: row.ip))
    object.__setattr__(scan, "_by_mac", _group(scan.rows, lambda row: row.mac))
    object.__setattr__(
        scan,
        "_by_normalized_mac",
        _group(scan.rows, lambda row: normalized_mac(row.mac)),
    )
    return scan


def _row(index: int, value: Any) -> LeaseRow | None:
    """Return one typed lease row, or None when any identity field is unusable."""
    if not isinstance(value, Mapping):
        return None
    ip = value.get("ipAddress")
    mac = value.get("macAddress")
    port = value.get("port")
    lease = value.get("leaseTime")
    if not isinstance(ip, str) or not _IPV4.fullmatch(ip):
        return None
    if not isinstance(mac, str) or not mac:
        return None
    if not isinstance(port, str) or not port:
        return None
    if (
        isinstance(lease, bool)
        or not isinstance(lease, (int, float))
        or not math.isfinite(float(lease))
    ):
        return None
    return LeaseRow(index, ip, mac, float(lease), port)


def classify_lease_scan(entry: object, *, pool_name: str) -> LeaseScan:
    """Classify one pool's explicit index window without assuming an end.

    A null is a clean end only when every later index in the window is null
    too; a row after a null makes the null non-terminal. A throw is recorded
    at its index and ends nothing: it is not end of table. A repeated row, an
    unusable identity or an incoherent window leaves the scan unclean. The
    raw entries are always kept, whatever the classification.
    """
    if not isinstance(entry, Mapping) or entry.get("requested") != pool_name:
        return LeaseScan(pool_name, False, "scan_pool_not_answered")
    raw_entries = entry.get("entries")
    capacity_value = entry.get("max")
    capacity = (
        capacity_value
        if isinstance(capacity_value, int)
        and not isinstance(capacity_value, bool)
        and capacity_value >= 0
        else None
    )
    if entry.get("found") is not True:
        return LeaseScan(
            pool_name,
            True,
            "pool_absent",
            capacity,
            termination=TERMINATION_POOL_ABSENT,
        )
    window = entry.get("window")
    if (
        isinstance(window, bool)
        or not isinstance(window, int)
        or window <= 0
        or not isinstance(raw_entries, list)
        or len(raw_entries) != window
        or any(
            not isinstance(item, Mapping) or item.get("index") != position
            for position, item in enumerate(raw_entries)
        )
    ):
        return LeaseScan(
            pool_name,
            False,
            "scan_window_incoherent",
            capacity,
            entries=tuple(
                dict(item) for item in raw_entries or () if isinstance(item, Mapping)
            ),
        )
    entries = tuple(dict(item) for item in raw_entries)
    rows: list[LeaseRow] = []
    first_null: int | None = None
    termination = ""
    seen: set[tuple[str, str]] = set()
    for item in entries:
        index = int(item["index"])
        kind = item.get("return_kind")
        if item.get("error"):
            termination = termination or TERMINATION_THROW
            continue
        if kind == "undefined":
            termination = termination or TERMINATION_UNDEFINED
            continue
        if kind == "null":
            if first_null is None:
                first_null = index
            continue
        if first_null is not None:
            termination = termination or TERMINATION_NON_MONOTONE
            continue
        row = _row(index, item.get("row"))
        if row is None:
            termination = termination or TERMINATION_MALFORMED
            continue
        if (row.ip, row.mac) in seen:
            termination = termination or TERMINATION_REPEAT
            continue
        seen.add((row.ip, row.mac))
        rows.append(row)
    if not termination:
        termination = TERMINATION_NULL if first_null is not None else TERMINATION_WINDOW
    return _indexed(
        LeaseScan(
            pool=pool_name,
            observed=True,
            capacity=capacity,
            window=window,
            rows=tuple(rows),
            termination=termination,
            first_null=first_null,
            entries=entries,
        )
    )


def scans_by_pool(payload: object, pools: Sequence[str]) -> dict[str, LeaseScan]:
    """Classify every requested pool of one calibration reading."""
    entries = payload.get("pools") if isinstance(payload, Mapping) else None
    found: dict[str, Mapping[str, Any]] = {}
    for item in entries if isinstance(entries, list) else ():
        if isinstance(item, Mapping) and isinstance(item.get("requested"), str):
            found.setdefault(str(item["requested"]), item)
    return {
        name: classify_lease_scan(found.get(name), pool_name=name) for name in pools
    }


def unobserved_scans(pools: Sequence[str], cause: str) -> dict[str, LeaseScan]:
    """Return one explicit unobserved scan per pool, carrying why."""
    return {name: LeaseScan(name, False, cause) for name in pools}


# -- calibration ------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationState:
    """One scan of one pool, labelled with the moment it was taken."""

    label: str
    scan: LeaseScan


@dataclass(frozen=True)
class LeaseCalibration:
    """What this run's scans of one pool establish about its end condition."""

    pool: str
    capacity: int | None
    conclusion: MeasurementConclusion
    null_ends_rows: bool
    kinds: tuple[str, ...] = ()
    causes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    states: tuple[dict[str, Any], ...] = ()

    def as_facts(self) -> dict[str, Any]:
        """Return the JSON-ready calibration facts."""
        return {
            "pool": self.pool,
            "capacity": self.capacity,
            "conclusion": self.conclusion.value,
            "null_ends_rows": self.null_ends_rows,
            "kinds": list(self.kinds),
            "causes": list(self.causes),
            "limitations": list(self.limitations),
            "states": [dict(item) for item in self.states],
        }


def _state_kind(rows: int, capacity: int | None) -> str:
    if rows == 0:
        return STATE_EMPTY
    if capacity is not None and rows > capacity:
        return STATE_OVER_CAPACITY
    if capacity is not None and rows == capacity:
        return STATE_FULL
    return STATE_ONE_ROW if rows == 1 else STATE_PARTIAL


def assess_lease_calibration(
    states: Sequence[CalibrationState],
    *,
    pool: str,
    capacity: int | None,
    fixture_macs: Iterable[str],
) -> LeaseCalibration:
    """Decide what one pool's observed states establish about its end condition.

    A null is taken to end the rows only when every observed state of this
    pool in this run is clean, ends exactly at its own row count, and at least
    one empty and one non-empty state were observed. A state whose capacity
    equals its row count cannot tell "end of rows" from "end of capacity";
    only a non-empty state below capacity, or an empty one, can. Rows the
    fixture's clients do not account for are never fabricated into a state,
    and more rows than the configured capacity is a contradiction.
    """
    macs = {normalized_mac(item) for item in fixture_macs}
    facts: list[dict[str, Any]] = []
    kinds: list[str] = []
    causes: list[str] = []
    contradiction = False
    unclean = False
    for state in states:
        scan = state.scan
        row = {
            "label": state.label,
            "termination": scan.termination,
            "first_null": scan.first_null,
            "rows": len(scan.rows),
            "window": scan.window,
            "observed": scan.observed,
        }
        if not scan.clean:
            unclean = True
            causes.append(
                f"{state.label}:scan_not_clean:{scan.termination or scan.cause}"
            )
            facts.append(row)
            continue
        kind = _state_kind(len(scan.rows), capacity)
        row["kind"] = kind
        facts.append(row)
        foreign = [item for item in scan.rows if normalized_mac(item.mac) not in macs]
        if foreign:
            unclean = True
            causes.append(f"{state.label}:row_not_from_a_fixture_client")
        if kind == STATE_OVER_CAPACITY:
            contradiction = True
            causes.append(f"{state.label}:rows_exceed_configured_capacity")
        if scan.first_null != len(scan.rows):
            unclean = True
            causes.append(f"{state.label}:null_not_at_row_count")
        if kind not in kinds:
            kinds.append(kind)
    if capacity is None:
        causes.append("capacity_unreadable")
    observed_empty = STATE_EMPTY in kinds
    observed_rows = any(kind != STATE_EMPTY for kind in kinds)
    null_ends_rows = (
        not unclean and not contradiction and observed_empty and observed_rows
    )
    if not observed_empty:
        causes.append("no_empty_state_observed")
    if not observed_rows:
        causes.append("no_non_empty_state_observed")
    limitations = [CALIBRATION_IS_LOCAL, "a_capacity_is_not_a_lease_count"]
    if STATE_FULL in kinds and STATE_ONE_ROW not in kinds and capacity == 1:
        limitations.append("one_row_and_full_states_are_identical_at_capacity_one")
    if STATE_FULL in kinds and STATE_ONE_ROW in kinds:
        limitations.append("one_row_and_full_states_discriminated")
    if contradiction:
        conclusion = MeasurementConclusion.CONTRADICTED
    elif null_ends_rows:
        conclusion = MeasurementConclusion.SUPPORTED_IN_SAMPLE
    else:
        conclusion = MeasurementConclusion.INCONCLUSIVE
    return LeaseCalibration(
        pool=pool,
        capacity=capacity,
        conclusion=conclusion,
        null_ends_rows=null_ends_rows,
        kinds=tuple(kinds),
        causes=tuple(causes),
        limitations=tuple(limitations),
        states=tuple(facts),
    )


# -- per-client attribution --------------------------------------------------------


@dataclass(frozen=True)
class ClientReading:
    """One typed reading of one client port, or why there is none."""

    client: str
    observed: bool
    mode: bool | None = None
    mac: str = ""
    ipv4: str = ""
    netmask: str = ""
    lease_time: str = ""
    cause: str = ""


def client_readings(
    payload: object, clients: Sequence[str]
) -> dict[str, ClientReading]:
    """Index one `dhcp_clients` reading by client, typing every field."""
    rows = payload.get("clients") if isinstance(payload, Mapping) else None
    found: dict[str, Mapping[str, Any]] = {}
    for item in rows if isinstance(rows, list) else ():
        if isinstance(item, Mapping) and isinstance(item.get("device"), str):
            found.setdefault(str(item["device"]), item)
    result: dict[str, ClientReading] = {}
    for name in clients:
        item = found.get(name)
        if item is None:
            result[name] = ClientReading(name, False, cause="client_row_absent")
            continue
        if item.get("error"):
            result[name] = ClientReading(name, False, cause="client_read_error")
            continue
        if item.get("found") is not True or item.get("port_found") is not True:
            result[name] = ClientReading(name, False, cause="client_subject_not_found")
            continue
        mode = item.get("mode")
        texts = [item.get(key) for key in ("mac", "ipv4", "netmask", "lease_time")]
        if (
            item.get("mode_type") != "boolean"
            or not isinstance(mode, bool)
            or any(not isinstance(value, str) for value in texts)
        ):
            result[name] = ClientReading(name, False, cause="client_reading_malformed")
            continue
        result[name] = ClientReading(name, True, mode, *texts)  # type: ignore[arg-type]
    return result


def _as_int(address: str) -> int | None:
    if not _IPV4.fullmatch(address):
        return None
    value = 0
    for part in address.split("."):
        value = (value << 8) | int(part)
    return value


@dataclass(frozen=True)
class AddressRange:
    """One inclusive IPv4 range, compared as integers."""

    start: str
    end: str

    def contains(self, address: str) -> bool:
        """Whether one dotted address lies inside this range."""
        low, high, value = _as_int(self.start), _as_int(self.end), _as_int(address)
        return None not in (low, high, value) and low <= value <= high  # type: ignore[operator]


def addressing_of(
    reading: ClientReading,
    *,
    intended: AddressRange,
    native: AddressRange | None,
    netmask: str,
) -> str:
    """Name what one client's own address says, and nothing about who served it."""
    if not reading.observed:
        return "unobserved"
    if reading.ipv4 in ("", "0.0.0.0"):
        return "no_address"
    if reading.ipv4.startswith("169.254."):
        return "link_local"
    if _as_int(reading.ipv4) is None:
        return "malformed"
    in_intended = intended.contains(reading.ipv4) and reading.netmask == netmask
    in_native = native is not None and native.contains(reading.ipv4)
    if in_intended and in_native:
        return "inside_intended_window_and_native_range"
    if in_intended:
        return "inside_intended_window"
    if in_native:
        return "inside_native_range_only"
    return "outside_both_ranges"


def row_status(
    scan: LeaseScan, reading: ClientReading, calibration: LeaseCalibration | None
) -> str:
    """Name how one client stands in one pool, by exact text first."""
    if not scan.observed:
        return ROW_UNOBSERVED
    if not reading.observed or not reading.mac:
        return ROW_UNOBSERVED
    same_ip = scan.rows_with_ip(reading.ipv4) if reading.ipv4 else ()
    # A same-IP row for another MAC contradicts the claim, and it takes
    # precedence even when an exact row is also present.
    own = normalized_mac(reading.mac)
    if any(normalized_mac(row.mac) != own for row in same_ip):
        return ROW_WRONG_MAC
    if any(row.mac == reading.mac for row in same_ip):
        return ROW_EXACT
    if same_ip:
        return ROW_REPRESENTATION
    if scan.rows_with_mac(reading.mac) or scan.rows_with_normalized_mac(reading.mac):
        # A row for this MAC while the port still reports no address is an
        # inconsistency between two readers at two instants, not a lease on
        # another address; only a real other address contradicts.
        if reading.ipv4 in ("", "0.0.0.0") or reading.ipv4.startswith("169.254."):
            return ROW_WITHOUT_PORT_ADDRESS
        return ROW_MAC_ELSEWHERE
    if not scan.clean:
        return ABSENT_INCOMPLETE
    if calibration is not None and calibration.null_ends_rows:
        return ABSENT_CALIBRATED
    return ABSENT_UNCALIBRATED


def serving_pool(intended_row: str, native_row: str, addressing: str) -> str:
    """Attribute an address only to the pool that holds its exact row."""
    intended = intended_row == ROW_EXACT
    native = native_row == ROW_EXACT
    if intended and native:
        return SERVED_BOTH
    if intended:
        return SERVED_INTENDED
    if native:
        return SERVED_NATIVE
    if addressing in ("no_address", "link_local"):
        return SERVED_NONE
    return SERVED_UNKNOWN


@dataclass(frozen=True)
class ClientAttribution:
    """Every separate claim about one client's acquisition."""

    client: str
    request: str
    addressing_before: str
    addressing_after: str
    intended_row: str
    native_row: str
    served_by: str
    causal: str
    contradictions: tuple[str, ...] = ()
    facts: Mapping[str, Any] = field(default_factory=dict)

    def as_facts(self) -> dict[str, Any]:
        """Return the JSON-ready claims, one field per claim."""
        return {
            "client": self.client,
            "request": self.request,
            "addressing_before": self.addressing_before,
            "addressing_after": self.addressing_after,
            "intended_row": self.intended_row,
            "native_row": self.native_row,
            "served_by": self.served_by,
            "causal_acquisition": self.causal,
            "contradictions": list(self.contradictions),
            **dict(self.facts),
        }


_ABSENT = frozenset({ABSENT_CALIBRATED, ABSENT_UNCALIBRATED, ABSENT_INCOMPLETE})


def attribute_client(
    client: str,
    *,
    request: str,
    before: ClientReading,
    after: ClientReading,
    prior_intended: LeaseScan,
    prior_native: LeaseScan,
    intended: LeaseScan,
    native: LeaseScan,
    intended_range: AddressRange,
    native_range: AddressRange | None,
    netmask: str,
    intended_calibration: LeaseCalibration | None,
    native_calibration: LeaseCalibration | None,
) -> ClientAttribution:
    """Keep native addressing, row presence, absence and causality apart.

    `request` is `dispatched` only for an acquisition whose script reported
    `attempted=true` with no call error and a known transport outcome. Causal
    acquisition is supported only when that request was preceded by an
    observed state with no subnet address and no row for this MAC in either
    pool, and followed by an exact row in exactly one pool whose address the
    port also reports. Even then it proves presence after a request, not DORA
    internals, exclusivity or the absence of background traffic.
    """
    addressing_before = addressing_of(
        before, intended=intended_range, native=native_range, netmask=netmask
    )
    addressing_after = addressing_of(
        after, intended=intended_range, native=native_range, netmask=netmask
    )
    intended_row = row_status(intended, after, intended_calibration)
    native_row = row_status(native, after, native_calibration)
    served = serving_pool(intended_row, native_row, addressing_after)
    contradictions = [
        f"{name}:{status}"
        for name, status in (("intended", intended_row), ("native", native_row))
        if status in (ROW_WRONG_MAC, ROW_MAC_ELSEWHERE)
    ]
    prior_rows = [
        status
        for status in (
            row_status(prior_intended, before, None)
            if before.observed
            else ROW_UNOBSERVED,
            row_status(prior_native, before, None)
            if before.observed
            else ROW_UNOBSERVED,
        )
    ]
    prior_absent = all(status in _ABSENT for status in prior_rows)
    causal = "supported_after_request_with_prior_absence_observed"
    if request != "dispatched":
        causal = f"not_established:request_{request}"
    elif addressing_before not in ("no_address", "link_local"):
        causal = f"not_established:address_before_request:{addressing_before}"
    elif not prior_absent:
        causal = "not_established:prior_rows_not_observed_absent:" + ",".join(
            prior_rows
        )
    elif served not in (SERVED_INTENDED, SERVED_NATIVE):
        causal = f"not_established:served_by:{served}"
    elif contradictions:
        causal = "not_established:contradiction_observed"
    return ClientAttribution(
        client=client,
        request=request,
        addressing_before=addressing_before,
        addressing_after=addressing_after,
        intended_row=intended_row,
        native_row=native_row,
        served_by=served,
        causal=causal,
        contradictions=tuple(contradictions),
        facts={
            "before": _reading_facts(before),
            "after": _reading_facts(after),
            "prior_rows": prior_rows,
            "limitations": [NO_BACKGROUND_PROOF, NOT_DORA],
        },
    )


def _reading_facts(reading: ClientReading) -> dict[str, Any]:
    return {
        "observed": reading.observed,
        "mode": reading.mode,
        "mac": reading.mac,
        "ipv4": reading.ipv4,
        "netmask": reading.netmask,
        "lease_time": reading.lease_time,
        "cause": reading.cause,
    }


@dataclass(frozen=True)
class CapacityNegative:
    """What the second client on a full one-user pool establishes."""

    conclusion: MeasurementConclusion
    result: str
    causes: tuple[str, ...] = ()
    facts: Mapping[str, Any] = field(default_factory=dict)


def assess_capacity_one_negative(
    *,
    first: ClientAttribution,
    second: ClientAttribution,
    intended: LeaseScan,
    capacity: int,
) -> CapacityNegative:
    """Decide `lease_not_acquired` only from completed negative observations.

    It needs a dispatched second request, a one-user pool that is full with
    the first client's exact row, a calibrated absence of the second client
    and no intended-window address for it. Service from the native default is
    recorded as its own result. A timeout without an address is neither
    exhaustion nor a failure of the intended pool.
    """
    facts = {
        "capacity": capacity,
        "first": first.as_facts(),
        "second": second.as_facts(),
        "intended_scan": intended.as_facts(),
    }
    if capacity != 1:
        return CapacityNegative(
            MeasurementConclusion.INCONCLUSIVE,
            "not_applicable",
            ("capacity_is_not_one",),
            facts,
        )
    if second.contradictions:
        return CapacityNegative(
            MeasurementConclusion.CONTRADICTED,
            "contradicted",
            tuple(second.contradictions),
            facts,
        )
    if second.intended_row == ROW_EXACT:
        return CapacityNegative(
            MeasurementConclusion.CONTRADICTED,
            "second_client_holds_an_intended_row",
            ("one_user_pool_served_a_second_client",),
            facts,
        )
    causes: list[str] = []
    if second.request != "dispatched":
        causes.append(f"second_request_{second.request}")
    if first.intended_row != ROW_EXACT or len(intended.rows) != capacity:
        causes.append("intended_pool_not_full_with_the_first_client")
    if second.intended_row != ABSENT_CALIBRATED:
        causes.append(f"second_client_absence_not_calibrated:{second.intended_row}")
    if (
        second.addressing_after
        in (
            "inside_intended_window",
            "inside_intended_window_and_native_range",
        )
        and second.served_by != SERVED_NATIVE
    ):
        causes.append("second_client_reports_an_intended_window_address")
    if causes:
        return CapacityNegative(
            MeasurementConclusion.INCONCLUSIVE, "not_established", tuple(causes), facts
        )
    result = "lease_not_acquired"
    if second.served_by == SERVED_NATIVE:
        result = "lease_not_acquired:served_by_native_default"
    elif second.served_by == SERVED_NONE:
        result = "lease_not_acquired:no_address_within_settle_window"
    return CapacityNegative(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE, result, (), facts
    )
