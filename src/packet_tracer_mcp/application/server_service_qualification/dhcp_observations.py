"""Counted, purpose-labelled DHCP server, client and pool observations.

Every reading is dispatched under its own ledger purpose and persisted to
the record's sink, so a reading taken after a stop or during finalization is
durable evidence rather than a value lost with its procedure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ...domain.enterprise.models.service_plan import (
    AcquireDhcpLease,
    ServiceVerificationKind,
)
from ...domain.enterprise.models.service_qualification import (
    Q3_FL_INTENDED_EXTRA_INDEXES,
    Q3_FL_NATIVE_DEFAULT_POLICY,
    Q3_FL_NATIVE_SCAN_INDEXES,
    Q3_PC1,
    Q3_PC2,
    Q3_POOL,
    Q3_SERVER,
    DefaultPoolObservation,
)
from ...domain.enterprise.services.dhcp_lease_evidence import (
    ClientReading,
    LeaseScan,
    client_readings,
    scans_by_pool,
    unobserved_scans,
)
from ...domain.enterprise.services.dhcp_native_default_lifecycle import (
    NativeDefaultReading,
    NativeDefaultSequenceAssessment,
    assess_native_default_sequence,
)
from ...domain.enterprise.services.service_qualification_evidence import (
    DefaultPoolSnapshot,
    ProbeReading,
    default_pool_differences,
    default_pool_snapshot,
)
from .contracts import Q3ProductContract, bounded
from .execution import Execution
from .operation_budget import OperationRefused, counted_seq

Q3_DEFAULT_PURPOSE = "q3:native_default"
#: The same reading under the D-DHCP diagnostic, so a record can never confuse
#: a Q3 sample with a diagnostic one by its purpose alone.
D_DHCP_DEFAULT_PURPOSE = "d-dhcp:native_default"


def q3_client_rows(reading: ProbeReading | None) -> list[dict[str, Any]] | None:
    """Return the exact two bounded client rows, or None when shape is unusable."""
    if reading is None or not reading.observed:
        return None
    rows = reading.payload.get("clients")
    if not isinstance(rows, list) or len(rows) != 2:
        return None
    expected = {(Q3_PC1, "FastEthernet0"), (Q3_PC2, "FastEthernet0")}
    observed: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        required = {
            "device": str,
            "interface": str,
            "found": bool,
            "port_found": bool,
            "mode_type": str,
            "mac": str,
            "ipv4": str,
            "netmask": str,
            "lease_time": str,
            "error": str,
        }
        if any(
            key not in row or not isinstance(row[key], kind)
            for key, kind in required.items()
        ):
            return None
        if row.get("mode") is not None and not isinstance(row.get("mode"), bool):
            return None
        observed.add((row["device"], row["interface"]))
    return rows if observed == expected else None


def _snapshot_facts(entry: DefaultPoolObservation) -> dict[str, Any]:
    """Return one persisted default reading exactly as it was recorded."""
    return {
        "label": entry.label,
        "purpose": entry.purpose,
        "operation_seq": entry.operation_seq,
        "observed": entry.observed,
        "cause": entry.cause,
        "pools": [dict(item) for item in entry.pools],
        "intended_pool_present": entry.intended_pool_present,
        "raw": dict(entry.raw),
        "differences": list(entry.differences),
    }


def native_default_facts(execution: Execution) -> dict[str, Any]:
    """Return every default reading the record holds and their differences."""
    return {
        "snapshots": [
            _snapshot_facts(item) for item in execution.record.native_default_pool
        ],
        "differences": execution.default_pool_differences,
    }


def q3_default_purpose(label: str, prefix: str = Q3_DEFAULT_PURPOSE) -> str:
    """Return the ledger purpose one default reading is dispatched under."""
    return f"{prefix}:{label}"


def _restore_snapshot(entry: DefaultPoolObservation) -> DefaultPoolSnapshot:
    """Return the domain snapshot one persisted reading stands for."""
    return DefaultPoolSnapshot(
        entry.label,
        entry.observed,
        entry.cause,
        tuple(dict(item) for item in entry.pools),
        entry.intended_pool_present,
        dict(entry.raw),
    )


def _q3_default_persist(
    execution: Execution,
    purpose: str,
    operation_seq: int,
    snapshot: DefaultPoolSnapshot,
) -> DefaultPoolSnapshot:
    """Write one default reading to the record's sink and persist it there.

    The sink is the record itself, so a reading taken after the last
    conclusion, after a stop or during finalization is durable evidence of the
    run rather than a value that disappears with the procedure that took it.
    The write uses the existing step machinery: a failed advance keeps the
    first primary failure, records its own error and closes further effects.
    """
    record = execution.record
    first = record.native_default_pool[0] if record.native_default_pool else None
    differences = (
        default_pool_differences(_restore_snapshot(first), snapshot)
        if first is not None
        else ()
    )
    record.native_default_pool.append(
        DefaultPoolObservation(
            label=snapshot.label,
            purpose=purpose,
            operation_seq=operation_seq,
            observed=snapshot.observed,
            cause=snapshot.cause,
            pools=[dict(item) for item in snapshot.pools],
            intended_pool_present=snapshot.intended_present,
            raw=dict(snapshot.raw),
            differences=list(differences),
        )
    )
    if not snapshot.observed and execution.stopped:
        # The run already has its cause. An unobserved later reading is one
        # more fact about it, never a replacement for it.
        record.secondary_failures.append(
            f"native_default:{snapshot.label}:{snapshot.cause}"
        )
    execution.run.transition(f"native_default:{snapshot.label}")
    return snapshot


def q3_default_observed(
    execution: Execution,
    label: str,
    reading: ProbeReading | None,
    *,
    operation_seq: int,
    prefix: str = Q3_DEFAULT_PURPOSE,
) -> DefaultPoolSnapshot:
    """Classify and persist one default reading this run already performed."""
    return _q3_default_persist(
        execution,
        q3_default_purpose(label, prefix),
        operation_seq,
        default_pool_snapshot(
            label,
            reading,
            intended_pool=Q3_POOL,
            server=Q3_SERVER,
            interface="FastEthernet0",
        ),
    )


def q3_default_read(
    execution: Execution,
    label: str,
    *,
    prefix: str = Q3_DEFAULT_PURPOSE,
    policy: bool = False,
) -> DefaultPoolSnapshot:
    """Dispatch one bounded default reading under its own purpose and persist it.

    The purpose is set before the call, so the counted operation states what it
    was for instead of being identified afterwards from its ordinal. A reading
    the remaining allowance cannot pay for, and one the ledger refuses, are
    explicitly not observed: no operation is added to the stage to repair the
    record, and the budgets are the ones the stage already planned.
    """
    purpose = q3_default_purpose(label, prefix)
    ledger = execution.ledger
    start = len(ledger.entries)
    if not ledger.can_afford(1):
        return _q3_default_persist(
            execution,
            purpose,
            0,
            DefaultPoolSnapshot(label, False, "default_pool_snapshot_not_affordable"),
        )
    try:
        with ledger.purpose_of(purpose):
            if policy:
                reading = execution.probes.read_dhcp_server_policy(
                    Q3_SERVER, "FastEthernet0"
                )
            else:
                reading = execution.probes.read_dhcp_server_baseline(
                    Q3_SERVER, "FastEthernet0"
                )
    except OperationRefused as exc:
        return _q3_default_persist(
            execution,
            purpose,
            0,
            DefaultPoolSnapshot(
                label, False, f"default_pool_snapshot_refused:{exc.reason}"
            ),
        )
    return q3_default_observed(
        execution,
        label,
        reading,
        operation_seq=counted_seq(ledger, start),
        prefix=prefix,
    )


Q3_FL_DEFAULT_PURPOSE = "q3-fl:native_default"


@dataclass(frozen=True)
class DhcpAcquisitionClient:
    """One client of the compiled DHCP service, by its product identities."""

    device_id: str
    name: str
    interface: str
    acquisition_id: str
    lease_expectation_id: str


@dataclass
class DhcpObservationState:
    """The DHCP observations one run took, shared by the workflows that take them.

    The native-default readings and the policy's decision over them, and every
    labelled pool scan and client reading. A workflow that needs more state
    extends it; none of these fields means anything workflow-specific.
    """

    clients: tuple[DhcpAcquisitionClient, ...] = ()
    native_pools: tuple[str, ...] = ()
    readings: list[NativeDefaultReading] = field(default_factory=list)
    snapshots: list[DefaultPoolSnapshot] = field(default_factory=list)
    sequence: NativeDefaultSequenceAssessment | None = None
    scans: list[tuple[str, dict[str, LeaseScan]]] = field(default_factory=list)
    client_reads: list[tuple[str, dict[str, ClientReading]]] = field(
        default_factory=list
    )

    def reading(self, label: str) -> dict[str, ClientReading]:
        """Return one labelled client reading, or an empty mapping."""
        return next((value for name, value in self.client_reads if name == label), {})

    def latest_scans(self) -> dict[str, LeaseScan]:
        """Return the most recent scan set, or none."""
        return self.scans[-1][1] if self.scans else {}


def dhcp_acquisition_clients(
    contract: Q3ProductContract,
) -> tuple[DhcpAcquisitionClient, ...]:
    """Return every compiled acquisition's client, in plan order."""
    leases = {
        item.action_id: item.id
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    }
    return tuple(
        DhcpAcquisitionClient(
            device_id=item.host_device_id,
            name=item.host_device_name,
            interface=item.interface,
            acquisition_id=item.id,
            lease_expectation_id=leases.get(item.id, ""),
        )
        for item in contract.service_plan.actions
        if isinstance(item, AcquireDhcpLease)
    )


def _scan_windows(
    execution: Execution, state: DhcpObservationState
) -> list[tuple[str, int]]:
    """Return the explicit index window of every pool a scan names."""
    capacity = execution.definition.dhcp_pool_capacity
    return [
        (Q3_POOL, capacity + Q3_FL_INTENDED_EXTRA_INDEXES),
        *((name, Q3_FL_NATIVE_SCAN_INDEXES) for name in state.native_pools),
    ]


def scan_dhcp_pools(
    execution: Execution, state: DhcpObservationState, label: str
) -> dict[str, LeaseScan]:
    """Take one calibrated scan of every pool and keep it under its label."""
    pools = _scan_windows(execution, state)
    names = [name for name, _window in pools]
    if not execution.ledger.can_afford(1):
        scans = unobserved_scans(names, "lease_scan_not_affordable")
    else:
        try:
            with execution.ledger.purpose_of(f"q3-fl:lease_scan:{label}"):
                reading = execution.probes.read_dhcp_lease_calibration(
                    Q3_SERVER, "FastEthernet0", pools
                )
        except OperationRefused as exc:
            scans = unobserved_scans(names, f"lease_scan_refused:{exc.reason}")
        else:
            payload = reading.payload if reading.observed else {}
            subject_ok = (
                reading.observed
                and payload.get("device") == Q3_SERVER
                and payload.get("interface") == "FastEthernet0"
                and payload.get("found") is True
                and payload.get("process_found") is True
                and not payload.get("error")
            )
            scans = (
                scans_by_pool(payload, names)
                if subject_ok
                else unobserved_scans(
                    names,
                    reading.cause if not reading.observed else "scan_subject_invalid",
                )
            )
    state.scans.append((label, scans))
    return scans


def read_acquisition_clients(
    execution: Execution, state: DhcpObservationState, label: str
) -> dict[str, ClientReading]:
    """Take one typed reading of every client and keep it under its label."""
    names = [item.name for item in state.clients]
    if not execution.ledger.can_afford(1):
        readings = {
            name: ClientReading(name, False, cause="client_read_not_affordable")
            for name in names
        }
    else:
        try:
            with execution.ledger.purpose_of(f"q3-fl:clients:{label}"):
                reading = execution.probes.read_dhcp_clients(
                    [(item.name, item.interface) for item in state.clients]
                )
        except OperationRefused as exc:
            readings = {
                name: ClientReading(
                    name, False, cause=f"client_read_refused:{exc.reason}"
                )
                for name in names
            }
        else:
            readings = (
                client_readings(reading.payload, names)
                if reading.observed
                else {
                    name: ClientReading(name, False, cause=bounded(reading.cause))
                    for name in names
                }
            )
    state.client_reads.append((label, readings))
    return readings


def _decide_native_default_sequence(
    execution: Execution, state: DhcpObservationState
) -> bool:
    """Re-decide the whole native-default sequence under the versioned policy."""
    boundaries = execution.run.boundaries
    transitions = boundaries.native_default_transitions
    state.sequence = assess_native_default_sequence(
        state.readings,
        policy=Q3_FL_NATIVE_DEFAULT_POLICY,
        model="Server-PT",
        backend_version=execution.record.environment.observed_build,
        interface="FastEthernet0",
        reviewed_intervention=boundaries.reviewed_native_default_intervention,
        admitted=(
            transitions(execution.record.environment.observed_build)
            if callable(transitions)
            else ()
        ),
    )
    return state.sequence.permits_continuation


def native_default_snapshot(
    execution: Execution,
    state: DhcpObservationState,
    label: str,
    intervention: str,
    *,
    policy: bool = False,
) -> bool:
    """Take one native-default reading after `intervention` and re-decide."""
    snapshot = q3_default_read(
        execution, label, prefix=Q3_FL_DEFAULT_PURPOSE, policy=policy
    )
    state.snapshots.append(snapshot)
    state.readings.append(
        NativeDefaultReading(
            label=label,
            observed=snapshot.observed,
            rows=tuple(dict(item) for item in snapshot.pools),
            intervention=intervention,
            cause=snapshot.cause,
        )
    )
    return _decide_native_default_sequence(execution, state)


def read_client_binding(
    execution: Execution, client_name: str, label: str
) -> Mapping[str, object]:
    """Keep exactly one correlated client binding row or its raw refusal."""
    try:
        with execution.ledger.purpose_of(f"sp2:binding:{label}"):
            reading = execution.probes.read_client_bindings((client_name,))
    except OperationRefused as exc:
        rows = None
        cause = f"binding_refused:{exc.reason}"
    else:
        rows = (
            reading.payload.get("clients")
            if reading.observed and isinstance(reading.payload, Mapping)
            else None
        )
        cause = reading.cause
    if (
        isinstance(rows, list)
        and len(rows) == 1
        and isinstance(rows[0], Mapping)
        and rows[0].get("device") == client_name
    ):
        return rows[0]
    return {
        "device": client_name,
        "cause": cause or "binding_rows_ambiguous",
        "raw_rows": rows,
    }
