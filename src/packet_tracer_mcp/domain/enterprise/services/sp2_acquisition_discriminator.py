"""SP-2 acquisition discriminator: pure precondition and per-arm decisions.

Episode 8 left every selected client in DHCP mode on a link-local address
after the server was enabled. The private `SP2-MIXED-ACQUISITION` stage
reproduces that state and then intervenes once per arm client: an ordinary
DHCP-mode reassertion, one typed explicit start (`dhcpRun`), or nothing.
These functions decide, from observations only, whether the precondition was
reproduced and what each arm's clients did in one shared window.

A client acquired only when two consecutive samples show it in DHCP mode
with the same usable address inside its intended pool's lease window, the
pool's mask, gateway and resolver, an exact (or normalization-equal) row in
its intended physical pool and no positive or conflicting row in any other
pool. An address in range alone, a single sample, or a row without a usable
port reading is not an acquisition. The outcome is a discriminator for the
next product design, never product acceptance, default support, capacity,
renewal or `dhcpRun` causality beyond the arms measured here.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models.service_plan import ConfigureServerDhcpPool
from ..models.service_qualification import MeasurementConclusion
from .dhcp_lease_evidence import (
    ROW_EXACT,
    ROW_MAC_ELSEWHERE,
    ROW_REPEATED,
    ROW_REPRESENTATION,
    ROW_UNOBSERVED,
    ROW_WITHOUT_PORT_ADDRESS,
    ROW_WRONG_MAC,
    TERMINATION_NULL,
    TERMINATION_THROW,
    AddressRange,
    ClientReading,
    LeaseScan,
    addressing_of,
    normalized_mac,
    row_status,
)
from .qualification_terminal_evidence import (
    sp2_mixed_bindings_usable,
    sp2_mixed_server_complete,
)
from .service_qualification_evidence import Assessment

ARM_REASSERT = "reassert"
ARM_EXPLICIT_START = "explicit_start"
ARM_CONTROL = "control"
ARMS = (ARM_REASSERT, ARM_EXPLICIT_START, ARM_CONTROL)
#: The only intervention outcome that lets an intervened client count: the
#: typed effect is known to have been dispatched (a void call or a setter
#: whose read-back verified). Anything else leaves that client undecided.
INTERVENTION_DISPATCHED = "dispatched"
LINK_LOCAL_MASK = "255.255.0.0"
_LINK_LOCAL = ipaddress.ip_network("169.254.0.0/16")
_POSITIVE_ROWS = (ROW_EXACT, ROW_REPRESENTATION)
#: Rows in a pool that is not the client's own which contradict an
#: attribution to its intended pool: the same identity, the same address for
#: another MAC, or the client's MAC on any other address.
_COMPETING_ROWS = (
    ROW_EXACT,
    ROW_REPRESENTATION,
    ROW_REPEATED,
    ROW_WRONG_MAC,
    ROW_MAC_ELSEWHERE,
    ROW_WITHOUT_PORT_ADDRESS,
)


#: The reader's semantics for this build's observed out-of-range index throw.
_NATIVE_INDEX_END = "observed_native_index_end"


def _scanned(scan: LeaseScan | None) -> bool:
    """Whether one pool was read to an observed end, so absence is shown.

    The scan must be observed without a scan error, its rows contiguous from
    index 0, and at least two later indices each a null or this build's
    observed index-end throw under its reader provenance. A pool the server
    does not hold (`pool_absent`), a row after an end (`non_monotone`), an
    unexplained throw, a repeated, malformed or exhausted window all leave
    rows possibly unseen, so they prove nothing about absence.
    """
    if (
        scan is None
        or not scan.observed
        or scan.termination not in (TERMINATION_NULL, TERMINATION_THROW)
        or scan.end_observation.get("scan_error")
    ):
        return False
    count = len(scan.rows)
    tail = list(scan.entries)[count:]
    return (
        [row.index for row in scan.rows] == list(range(count))
        and len(tail) >= 2
        and all(
            item.get("return_kind") == "null"
            or (
                item.get("return_kind") == "throw"
                and item.get("end_semantics") == _NATIVE_INDEX_END
                and bool(scan.reader_provenance)
            )
            for item in tail
        )
    )


def _link_local(value: str) -> bool:
    """Whether one address text parses as an IPv4 address in 169.254/16."""
    try:
        return ipaddress.IPv4Address(value) in _LINK_LOCAL
    except ValueError:
        return False


@dataclass(frozen=True)
class AcquisitionPrecondition:
    """Whether the product left the state the arms are designed for."""

    holds: bool
    causes: tuple[str, ...]
    clients: Mapping[str, str]


def acquisition_precondition(
    clients: Sequence[str],
    readings: Mapping[str, ClientReading],
    server: object,
    scans: Mapping[str, LeaseScan],
    pools: Sequence[str],
) -> AcquisitionPrecondition:
    """Decide whether every client is a link-local DHCP client of a ready server.

    Each client must be read in DHCP mode with a 169.254/16 address and mask;
    the server must be read enabled with exactly the planned physical pools;
    every pool must be scanned and hold no row for any client's MAC. A client
    that already holds a lease, an unread client or pool, or a server in any
    other state does not reproduce episode 8, so no arm may run.
    """
    causes: list[str] = []
    states: dict[str, str] = {}
    for name in clients:
        reading = readings.get(name)
        if reading is None or not reading.observed:
            states[name] = "unobserved"
        elif reading.mode is not True:
            states[name] = "dhcp_mode_not_on"
        elif not _link_local(reading.ipv4) or reading.netmask != LINK_LOCAL_MASK:
            states[name] = (
                "no_address" if reading.ipv4 in ("", "0.0.0.0") else "not_link_local"
            )
        elif not normalized_mac(reading.mac):
            states[name] = "mac_unusable"
        else:
            states[name] = "link_local"
        if states[name] != "link_local":
            causes.append(f"client_not_link_local:{name}:{states[name]}")
    if not sp2_mixed_server_complete(server, pools):
        causes.append("server_not_enabled_on_planned_pools")
    for pool in pools:
        scan = scans.get(pool)
        if not _scanned(scan):
            causes.append(
                f"pool_unscanned:{pool}:{scan.cause if scan is not None else 'absent'}"
            )
            continue
        for name in clients:
            reading = readings.get(name)
            mac = reading.mac if reading is not None else ""
            if normalized_mac(mac) and (
                scan.rows_with_mac(mac) or scan.rows_with_normalized_mac(mac)
            ):
                causes.append(f"client_row_present:{name}:{pool}")
    return AcquisitionPrecondition(not causes, tuple(causes), states)


@dataclass(frozen=True)
class AcquisitionSample:
    """One shared window sample: every client, every binding, every pool."""

    index: int
    readings: Mapping[str, ClientReading]
    bindings: object
    scans: Mapping[str, LeaseScan]
    read_causes: tuple[str, ...] = ()
    wait_seconds: float = 0.0


@dataclass(frozen=True)
class _ClientSample:
    addressing: str
    intended_row: str
    competing: tuple[str, ...]
    binding_usable: bool
    identity: tuple[str, str] | None
    complete: bool

    @property
    def usable(self) -> bool:
        return (
            self.complete
            and self.identity is not None
            and self.addressing.startswith("inside_intended_window")
            and self.intended_row in _POSITIVE_ROWS
            and not self.competing
            and self.binding_usable
        )

    def as_facts(self) -> dict[str, Any]:
        return {
            "addressing": self.addressing,
            "intended_row": self.intended_row,
            "competing": list(self.competing),
            "binding_usable": self.binding_usable,
            "usable": self.usable,
        }


def _binding_row(bindings: object, client: str) -> Mapping[str, Any] | None:
    rows = [
        row
        for row in (bindings if isinstance(bindings, list) else ())
        if isinstance(row, Mapping) and row.get("device") == client
    ]
    return rows[0] if len(rows) == 1 else None


def _binding_observed(row: Mapping[str, Any] | None) -> bool:
    """Whether one binding row is a reading rather than a failed lookup.

    The probe emits a row per requested client even when its lookup failed,
    so the row's presence proves nothing. It observed the client only when
    the device and port were found without error, at least one gateway
    reader answered, and the resolver reader answered.
    """
    if row is None:
        return False
    gateways = row.get("gateway_reads")
    return bool(
        row.get("found") is True
        and row.get("port_found") is True
        and row.get("error") == ""
        and isinstance(gateways, list)
        and any(
            isinstance(item, Mapping)
            and item.get("api") is True
            and item.get("error") == ""
            for item in gateways
        )
        and row.get("dns_api") is True
        and row.get("dns_error") == ""
    )


def _client_sample(
    client: str,
    pool: ConfigureServerDhcpPool,
    sample: AcquisitionSample,
    planned_pools: frozenset[str],
) -> _ClientSample:
    """Classify one client in one sample, against every planned pool.

    A sample counts only when it is complete: the client reading, an
    observed binding for the same address and mask, and every planned
    physical pool scanned. An unread pool cannot show that no competing
    lease exists.
    """
    reading = sample.readings.get(client) or ClientReading(client, False)
    addressing = (
        addressing_of(
            reading,
            intended=AddressRange(pool.lease_start, pool.lease_end),
            native=None,
            netmask=pool.netmask,
        )
        if reading.mode is True or not reading.observed
        else "dhcp_mode_off"
    )
    intended = sample.scans.get(pool.effective_pool_name)
    intended_row = (
        row_status(intended, reading, None) if intended is not None else ROW_UNOBSERVED
    )
    competing = tuple(
        sorted(
            f"{name}:{status}"
            for name, scan in sample.scans.items()
            if name != pool.effective_pool_name
            and (status := row_status(scan, reading, None)) in _COMPETING_ROWS
        )
    )
    row = _binding_row(sample.bindings, client)
    agrees = (
        row is not None
        and reading.observed
        and row.get("ipv4") == reading.ipv4
        and row.get("netmask") == reading.netmask
    )
    binding_usable = agrees and sp2_mixed_bindings_usable([row], {client: pool})
    mac = normalized_mac(reading.mac)
    identity = (reading.ipv4, mac) if reading.observed and mac else None
    # Complete means every reader observed the same client: its identity,
    # a binding for the same address and mask, and every planned pool.
    complete = (
        identity is not None
        and agrees
        and _scanned(intended)
        and planned_pools <= set(sample.scans)
        and all(_scanned(scan) for scan in sample.scans.values())
        and _binding_observed(row)
    )
    return _ClientSample(
        addressing, intended_row, competing, binding_usable, identity, complete
    )


@dataclass(frozen=True)
class ClientOutcome:
    """What one arm client did in the shared window."""

    client: str
    arm: str
    intervention: str
    acquired: bool
    first_usable_sample: int | None
    stable_identity: tuple[str, str] | None
    complete: bool
    samples: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    @property
    def decided(self) -> bool:
        """Whether the client's result may count for its arm."""
        intervened = self.arm == ARM_CONTROL or (
            self.intervention == INTERVENTION_DISPATCHED
        )
        return intervened and (self.acquired or self.complete)

    def as_facts(self) -> dict[str, Any]:
        """Return the outcome as record facts."""
        return {
            "arm": self.arm,
            "intervention": self.intervention,
            "acquired": self.acquired,
            "first_usable_sample": self.first_usable_sample,
            "stable_identity": list(self.stable_identity)
            if self.stable_identity
            else None,
            "observation_complete": self.complete,
            "samples": [dict(item) for item in self.samples],
        }


def client_outcome(
    client: str,
    arm: str,
    intervention: str,
    pool: ConfigureServerDhcpPool,
    samples: Sequence[AcquisitionSample],
    planned_pools: frozenset[str] = frozenset(),
) -> ClientOutcome:
    """Return whether one client held a stable attributed lease in the window.

    Acquisition needs two consecutive usable samples with one identity; a
    later contradiction does not erase an earlier stable pair but is kept in
    the per-sample facts. A client with any incomplete sample before it
    acquired is undecided, not a negative.
    """
    planned = planned_pools or frozenset({pool.effective_pool_name})
    states = [_client_sample(client, pool, item, planned) for item in samples]
    first: int | None = None
    stable: tuple[str, str] | None = None
    for position, state in enumerate(states):
        if state.usable and first is None:
            first = samples[position].index
        if (
            position
            and state.usable
            and states[position - 1].usable
            and state.identity == states[position - 1].identity
        ):
            stable = state.identity
            break
    complete = bool(states) and all(item.complete for item in states)
    return ClientOutcome(
        client=client,
        arm=arm,
        intervention=intervention,
        acquired=stable is not None,
        first_usable_sample=first,
        stable_identity=stable,
        complete=complete,
        samples=tuple(item.as_facts() for item in states),
    )


def _all(outcomes: Sequence[ClientOutcome]) -> bool:
    return bool(outcomes) and all(item.acquired for item in outcomes)


def _none(outcomes: Sequence[ClientOutcome]) -> bool:
    return all(not item.acquired for item in outcomes)


def assess_acquisition_arms(
    arms: Mapping[str, str],
    pools: Mapping[str, ConfigureServerDhcpPool],
    interventions: Mapping[str, str],
    samples: Sequence[AcquisitionSample],
) -> Assessment:
    """Classify the window into one discriminator pattern.

    SUPPORTED_IN_SAMPLE requires every explicit-start client, or every
    reassertion client, to acquire while no control does. NEGATIVE_OBSERVED
    requires a complete window in which no intervened client and no control
    acquired. A control that acquires confounds every attribution; an
    undecided client (unknown intervention or incomplete observation) or a
    partly acquiring arm stays INCONCLUSIVE. The pattern names what was seen.
    """
    if set(arms) != set(pools) or not set(arms.values()) <= set(ARMS):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            causes=["sp2_acquisition_arm_binding_invalid"],
        )
    planned = frozenset(item.effective_pool_name for item in pools.values())
    outcomes = {
        name: client_outcome(
            name,
            arm,
            interventions.get(name, "not_dispatched"),
            pools[name],
            samples,
            planned,
        )
        for name, arm in sorted(arms.items())
    }
    by_arm = {
        arm: [item for item in outcomes.values() if item.arm == arm] for arm in ARMS
    }
    controls = by_arm[ARM_CONTROL]
    reassert = by_arm[ARM_REASSERT]
    start = by_arm[ARM_EXPLICIT_START]
    causes: list[str] = []
    undecided = sorted(name for name, item in outcomes.items() if not item.decided)
    if any(item.acquired for item in controls):
        pattern = "control_acquired"
        causes.append("sp2_acquisition_control_acquired_confounds_arms")
    elif undecided:
        pattern = "undecided"
        causes.extend(f"sp2_acquisition_client_undecided:{name}" for name in undecided)
    elif _all(start) and _all(reassert):
        pattern = "explicit_start_and_reassertion"
    elif _all(start) and _none(reassert):
        pattern = "explicit_start_only"
    elif _all(reassert) and _none(start):
        pattern = "reassertion_only"
    elif _none(start) and _none(reassert):
        pattern = "no_intervention_acquired"
    else:
        pattern = "partial"
        causes.append("sp2_acquisition_arm_partly_acquired")
    conclusion = (
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if pattern
        in {"explicit_start_and_reassertion", "explicit_start_only", "reassertion_only"}
        else MeasurementConclusion.NEGATIVE_OBSERVED
        if pattern == "no_intervention_acquired"
        else MeasurementConclusion.INCONCLUSIVE
    )
    return Assessment(
        conclusion,
        facts={
            "pattern": pattern,
            "arms": {
                arm: {
                    "clients": [item.client for item in items],
                    "acquired": [item.client for item in items if item.acquired],
                }
                for arm, items in by_arm.items()
            },
            "clients": {name: item.as_facts() for name, item in outcomes.items()},
            "samples": [
                {
                    "index": item.index,
                    "wait_seconds": item.wait_seconds,
                    "read_causes": list(item.read_causes),
                }
                for item in samples
            ],
        },
        causes=causes,
        limitations=[
            "discriminator_not_product_acceptance",
            "explicit_start_is_one_void_dhcpRun_per_client",
            "no_renewal_or_table_end_claim",
            "relay_giaddr_not_observed",
        ],
    )
