"""Whether a moved Server-PT native default pool is the reviewed realignment.

The problem this answers is narrow and the answer is deliberately narrower. A
Server-PT ships one native default DHCP pool, and D-DHCP attempt 2 measured
that addressing the server through the whole `configurePcIp` call moves four of
its fields. A product that refuses every moved default would also refuse that
one measured transition; a product that accepts any moved default would accept
drift nobody measured. Neither is acceptable, so this module decides between
them and does nothing else.

Two properties make the decision safe.

It compares, it never computes. An admitted transition is a reviewed record of
exact before and after field values. Nothing here derives a network from a
mask, an end address from a start and a size, or any other arithmetic, so a
network nobody measured cannot be admitted by a formula that happened to hold
in the one case that was. That is a structural guarantee, not a policy the next
change could quietly relax.

It authorizes nothing. Every assessment carries `authorizes_allocation=False`,
and no code path sets it otherwise. Deciding that a default moved the way the
reviewed measurement says is a statement about one observation; it is not
permission to allocate, not a capability, and not evidence that any pool would
answer a client.

The backend build belongs to the caller. This module names no Packet Tracer
version: the reviewed records arrive through composition, so a second build
needs its own measurement rather than an edit here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

#: The fields one native pool row carries, and the type each one must have.
#: A row missing a field, carrying an extra one, or carrying the right name
#: with the wrong type is not a pool row this module will compare.
NATIVE_POOL_FIELDS: Mapping[str, type] = {
    "name": str,
    "network": str,
    "mask": str,
    "gateway": str,
    "dns": str,
    "start": str,
    "end": str,
    "max": int,
}

#: What one before/after pair was decided to be.
NOT_ASSESSED = "not_assessed"
UNCHANGED = "unchanged"
ADMITTED_REALIGNMENT = "admitted_realignment"
UNEXPLAINED_DRIFT = "unexplained_drift"

#: Standing limitations every assessment carries. They are part of the answer,
#: not commentary on it.
COEXISTENCE_IS_NOT_SERVICE = (
    "stored_pool_coexistence_is_not_proof_the_intended_pool_serves_a_client"
)
TRANSITION_IS_NOT_ALLOCATION = (
    "an_admitted_native_default_transition_authorizes_no_allocation"
)
MEASURED_VALUES_ONLY = "admission_compares_measured_values_and_extrapolates_nothing"


@dataclass(frozen=True)
class NativeDefaultContext:
    """The exact situation one measurement belongs to.

    Every field participates in the match. A reviewed transition of one model
    on one build through one interface says nothing about another model,
    another build, another interface or another intervention, and this is
    where that is enforced rather than remembered.
    """

    model: str
    backend_version: str
    interface: str
    #: The whole backend call the measurement brackets, never one internal
    #: setter inside it. The interval is what was observed.
    intervention: str


@dataclass(frozen=True)
class AdmittedNativeDefaultTransition:
    """One reviewed measurement: this default moved exactly this way, here."""

    context: NativeDefaultContext
    pool_name: str
    before: Mapping[str, object]
    after: Mapping[str, object]
    changed_fields: tuple[str, ...]
    #: Where the values came from, carried into the assessment so a reader can
    #: reach the record rather than trust the table.
    evidence: str = ""


@dataclass(frozen=True)
class NativeDefaultTransitionAssessment:
    """What one observed pair is, and what it still does not permit."""

    classification: str
    changed_fields: tuple[str, ...] = ()
    causes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    matched_evidence: str = ""

    @property
    def authorizes_allocation(self) -> bool:
        """Always False. Deciding what a default did permits handing out nothing.

        A read-only property rather than a field, because a field with a
        `False` default is still a field a caller can pass `True` to, and the
        one thing this type must never be able to say is yes.
        """
        return False

    @property
    def admitted(self) -> bool:
        """Whether this pair is the reviewed realignment and nothing more."""
        return self.classification == ADMITTED_REALIGNMENT


@dataclass(frozen=True)
class IntendedPoolCoexistence:
    """How an intended pool sits beside the native default it shares a wire with."""

    native_pool_name: str
    intended_pool_name: str
    shares_subnet: bool
    ranges_overlap: bool
    overlapping_addresses: tuple[str, ...] = ()
    causes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = field(
        default_factory=lambda: (COEXISTENCE_IS_NOT_SERVICE,)
    )


def _typed_row(row: object) -> dict[str, object] | None:
    """Return one pool row only when every field is present and typed."""
    if not isinstance(row, Mapping) or set(row) != set(NATIVE_POOL_FIELDS):
        return None
    for name, expected in NATIVE_POOL_FIELDS.items():
        value = row[name]
        if isinstance(value, bool) or not isinstance(value, expected):
            return None
    return dict(row)


def _by_name(rows: Sequence[object]) -> dict[str, dict[str, object]] | None:
    """Index typed pool rows by name, refusing a malformed or duplicated set."""
    indexed: dict[str, dict[str, object]] = {}
    for row in rows:
        typed = _typed_row(row)
        if typed is None:
            return None
        name = str(typed["name"])
        if name in indexed:
            return None
        indexed[name] = typed
    return indexed


def _changed_fields(
    before: Mapping[str, object], after: Mapping[str, object]
) -> tuple[str, ...]:
    """Name every field whose value differs between two typed rows."""
    return tuple(
        name
        for name in sorted(NATIVE_POOL_FIELDS)
        if before.get(name) != after.get(name)
    )


def _same_values(
    observed: Mapping[str, object], recorded: Mapping[str, object]
) -> bool:
    """Whether two typed rows agree on every field, with no field left out."""
    return all(observed.get(name) == recorded.get(name) for name in NATIVE_POOL_FIELDS)


def assess_native_default_transition(
    *,
    before: Sequence[object],
    after: Sequence[object],
    context: NativeDefaultContext,
    admitted: Sequence[AdmittedNativeDefaultTransition],
    before_observed: bool = True,
    after_observed: bool = True,
) -> NativeDefaultTransitionAssessment:
    """Decide what one adjacent pair of native default readings is.

    Ordered and fail-closed. An unobserved reading decides nothing, a set that
    gained, lost or renamed a pool is drift whatever its fields say, an
    identical pair is unchanged, and a moved pair is admitted only when some
    reviewed record matches the whole observation: its context, its pool, every
    before field, every after field and exactly the same changed set.
    """
    limitations = (MEASURED_VALUES_ONLY, TRANSITION_IS_NOT_ALLOCATION)
    if not before_observed or not after_observed:
        return NativeDefaultTransitionAssessment(
            NOT_ASSESSED,
            causes=(
                "native_default_unobserved:before"
                if not before_observed
                else "native_default_unobserved:after",
            ),
            limitations=limitations,
        )
    first = _by_name(before)
    second = _by_name(after)
    if first is None or second is None:
        return NativeDefaultTransitionAssessment(
            NOT_ASSESSED,
            causes=(
                "native_default_inventory_malformed:"
                + ("before" if first is None else "after"),
            ),
            limitations=limitations,
        )
    removed = sorted(set(first) - set(second))
    gained = sorted(set(second) - set(first))
    if removed or gained:
        # A default that disappeared, was renamed or was joined by a second
        # one is not this transition. Admitting it here is exactly how a
        # deleted or hidden `serverPool` would become invisible.
        return NativeDefaultTransitionAssessment(
            UNEXPLAINED_DRIFT,
            causes=tuple(
                [f"native_default_removed:{name}" for name in removed]
                + [f"native_default_added:{name}" for name in gained]
            ),
            limitations=limitations,
        )
    moved = {
        name: _changed_fields(first[name], second[name])
        for name in sorted(first)
        if _changed_fields(first[name], second[name])
    }
    if not moved:
        return NativeDefaultTransitionAssessment(UNCHANGED, limitations=limitations)
    if len(moved) > 1:
        return NativeDefaultTransitionAssessment(
            UNEXPLAINED_DRIFT,
            changed_fields=tuple(
                f"{name}.{item}" for name, items in moved.items() for item in items
            ),
            causes=("more_than_one_native_default_moved:" + ",".join(sorted(moved)),),
            limitations=limitations,
        )
    pool_name, changed = next(iter(moved.items()))
    qualified = tuple(f"{pool_name}.{item}" for item in changed)
    context_mismatch: list[str] = []
    # The reviewed measurement describes a stock server carrying ONE native
    # default. An inventory holding a second, unreviewed pool is a different
    # situation, even when that pool sits unchanged across both readings and
    # only the reviewed one moved. No record can match such an observation.
    unreviewed = sorted((set(first) | set(second)) - {pool_name})
    candidates: Sequence[AdmittedNativeDefaultTransition] = (
        () if unreviewed else admitted
    )
    for record in candidates:
        if record.context != context:
            # Name which fields of the reviewed situation differ, so a reader
            # can tell "no record for this build" from "a record for this build
            # that describes another interface or another call".
            context_mismatch.extend(
                f"context_differs:{name}"
                for name in ("model", "backend_version", "interface", "intervention")
                if getattr(record.context, name) != getattr(context, name)
            )
            continue
        if record.pool_name != pool_name:
            continue
        if record.changed_fields != changed:
            continue
        if not _same_values(first[pool_name], record.before):
            continue
        if not _same_values(second[pool_name], record.after):
            continue
        return NativeDefaultTransitionAssessment(
            ADMITTED_REALIGNMENT,
            changed_fields=qualified,
            limitations=limitations,
            matched_evidence=record.evidence,
        )
    return NativeDefaultTransitionAssessment(
        UNEXPLAINED_DRIFT,
        changed_fields=qualified,
        causes=(
            "no_reviewed_transition_matches_this_observation",
            *(
                (f"unreviewed_pool_present:{','.join(unreviewed)}",)
                if unreviewed
                else ()
            ),
            *sorted(set(context_mismatch)),
        ),
        limitations=limitations,
    )


def _octets(value: str) -> tuple[int, ...] | None:
    """Parse one dotted-quad into its four octets, or refuse it."""
    parts = value.split(".")
    if len(parts) != 4:
        return None
    octets: list[int] = []
    for part in parts:
        if not part.isdigit() or (len(part) > 1 and part[0] == "0"):
            return None
        number = int(part)
        if number > 255:
            return None
        octets.append(number)
    return tuple(octets)


def _as_int(value: str) -> int | None:
    """Return one IPv4 address as an integer, or nothing when it is not one."""
    octets = _octets(value)
    if octets is None:
        return None
    return (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]


def _network_of(address: str, mask: str) -> int | None:
    """Return the network number of one address under one mask."""
    numeric = _as_int(address)
    bits = _as_int(mask)
    if numeric is None or bits is None:
        return None
    return numeric & bits


def assess_intended_pool_coexistence(
    *,
    native: Mapping[str, object],
    intended: Mapping[str, object],
) -> IntendedPoolCoexistence:
    """State how an intended pool sits beside the native default, as fact only.

    Sharing a subnet and overlapping a range are observations about two stored
    configurations. They are reported because they are what makes a later
    matching address ambiguous, and they are reported with the limitation that
    says so, because neither of them is evidence that either pool would answer
    a request.
    """
    native_row = _typed_row(native)
    intended_row = _typed_row(intended)
    if native_row is None or intended_row is None:
        return IntendedPoolCoexistence(
            native_pool_name=str(native.get("name", "")),
            intended_pool_name=str(intended.get("name", "")),
            shares_subnet=False,
            ranges_overlap=False,
            causes=(
                "pool_row_malformed:"
                + ("native" if native_row is None else "intended"),
            ),
        )
    native_network = _network_of(str(native_row["network"]), str(native_row["mask"]))
    intended_network = _network_of(
        str(intended_row["network"]), str(intended_row["mask"])
    )
    shares_subnet = (
        native_network is not None
        and intended_network is not None
        and native_row["mask"] == intended_row["mask"]
        and native_network == intended_network
    )
    bounds = [
        _as_int(str(native_row["start"])),
        _as_int(str(native_row["end"])),
        _as_int(str(intended_row["start"])),
        _as_int(str(intended_row["end"])),
    ]
    causes: list[str] = []
    overlapping: tuple[str, ...] = ()
    ranges_overlap = False
    if any(item is None for item in bounds):
        causes.append("pool_range_unparsable")
    else:
        native_start, native_end, intended_start, intended_end = bounds  # type: ignore[misc]
        ranges_overlap = native_start <= intended_end and intended_start <= native_end
        if ranges_overlap:
            overlapping = (
                _dotted(max(native_start, intended_start)),
                _dotted(min(native_end, intended_end)),
            )
            if native_start <= intended_start and intended_end <= native_end:
                causes.append("intended_range_is_inside_the_native_default")
            elif intended_start <= native_start and native_end <= intended_end:
                causes.append("native_default_is_inside_the_intended_range")
            else:
                causes.append("intended_and_native_ranges_overlap_partially")
    return IntendedPoolCoexistence(
        native_pool_name=str(native_row["name"]),
        intended_pool_name=str(intended_row["name"]),
        shares_subnet=shares_subnet,
        ranges_overlap=ranges_overlap,
        overlapping_addresses=overlapping,
        causes=tuple(causes),
    )


def _dotted(value: int) -> str:
    """Render one IPv4 integer back as a dotted quad."""
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))
