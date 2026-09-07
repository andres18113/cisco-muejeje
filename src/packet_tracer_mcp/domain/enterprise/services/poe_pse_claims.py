"""PSE-side PoE delivery evidence: an independent basis, not a manual receipt.

The manual contract in `poe_claims` decides delivery by looking at the powered
device: someone sees a phone light up beside a dark control. This contract
decides it from the delivering end instead, by reading what the PSE reports it
is putting on one exact port across a causal sequence.

The two are deliberately separate all the way down. This module never touches
`_AUTHORIZED_OBSERVATION_METHODS`, never reuses the differential scope, and
never widens anything by making a manual field optional. It produces its own
typed scope, and the only place the two meet is the canonical authorized claim
that `poe_claims` hands the resolver.

What may never cross this boundary: raw CLI. The observer, the parser, the raw
captures and the calibrations are producers and validators of evidence. A table
of text is not a claim, and nothing downstream of here ever sees one.

Scope ceiling, deliberately narrow: one exact binding, proven delivering, on
one exact build. This contract carries no authority over another port, another
endpoint, another switch, another model, another build, or a larger
simultaneous count than the single port it watched.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ..models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
    PoEAuthorizedBinding,
)


PSE_EVIDENCE_KIND = "pse_inline_delivery"
PSE_SCHEMA_VERSION = 1

POE_PSE_EVIDENCE_KIND = "poe_pse_evidence_kind"
POE_PSE_SCHEMA_VERSION = "poe_pse_schema_version"
POE_PSE_SWITCH_MODEL = "poe_pse_switch_model"
POE_PSE_SWITCH_PORT = "poe_pse_switch_port"
POE_PSE_ENDPOINT_MODEL = "poe_pse_endpoint_model"
POE_PSE_ENDPOINT_PORT = "poe_pse_endpoint_port"
POE_PSE_PACKET_TRACER_BUILD = "poe_pse_packet_tracer_build"
POE_PSE_OBSERVER_ID = "poe_pse_observer_id"
POE_PSE_EXPERIMENT_ID = "poe_pse_experiment_id"
POE_PSE_OBSERVED_AT = "poe_pse_observed_at"
POE_PSE_CAPTURES = "poe_pse_captures"
POE_PSE_GATES = "poe_pse_gates"
POE_PSE_SIMULTANEOUS_ACTIVE_PORTS = "poe_pse_simultaneous_active_ports"
POE_PSE_CLEANUP_STATUS = "poe_pse_cleanup_status"
POE_PSE_INVENTORY_RESTORATION = "poe_pse_inventory_restoration"
POE_PSE_LIVE_SAFETY = "poe_pse_live_safety"

# The causal shape a positive PSE reading has to have. Delivery present, then
# removed by the only administrative change made, then restored. A single
# reading of "on" proves nothing: the port could have been lit by anything.
_CAUSAL_SEQUENCE = ("AUTO_1", "NEVER", "AUTO_2")
_ADMIN_BY_LABEL = {"AUTO_1": "auto", "NEVER": "never", "AUTO_2": "auto"}
_DELIVERING_BY_LABEL = {"AUTO_1": True, "NEVER": False, "AUTO_2": True}

# Every gate the observer has to have proven for a capture to be readable as
# evidence at all. An absent row under an incomplete pager is not an absence.
_REQUIRED_GATES = (
    "all_pagers_traversed",
    "attributable",
    "dispatch_integrity_valid",
    "expected_privileged_prompt_reached",
    "fresh",
    "no_pending_continuation",
    "observer_complete",
    "stable",
)

_CLEAN_QUALIFICATION = "clean"
_RESTORED_INVENTORY = "restored"
_ADMITTED_LIVE_SAFETY = "admitted"

# One governed producer, one source. A PSE reading is a controlled probe: a
# registered qualification query dispatched by the governed executor and read
# by the governed observer. It is not a manual receipt and not a bare runtime
# inventory read, so neither of those sources may carry it.
_PSE_EVIDENCE_SOURCES = frozenset({EvidenceSource.CONTROLLED_PROBE})


class PoEClaim(Protocol):
    capability: str
    status: CapabilityStatus
    verified: bool
    observed_value: int | None
    dimensions: Mapping[str, str]


@dataclass(frozen=True, order=True)
class PoEPseCapture:
    """One governed observation of the measured port in one administrative mode."""

    label: str
    admin_mode: str
    oper_state: str
    power_watts: float
    row_present: bool
    delivering: bool


@dataclass(frozen=True)
class PoEPseDeliveryScope:
    """Exactly what one governed PSE run proved, and nothing adjacent to it."""

    schema_version: int
    switch_model: str
    switch_port: str
    endpoint_model: str
    endpoint_port: str
    packet_tracer_build: str
    observer_id: str
    experiment_id: str
    observed_at: str
    captures: tuple[PoEPseCapture, ...]
    gates: tuple[str, ...]
    simultaneous_active_ports: int
    cleanup_status: str
    inventory_restoration: str
    live_safety: str

    @property
    def authorized_binding(self) -> PoEAuthorizedBinding:
        return PoEAuthorizedBinding(
            switch_port=self.switch_port,
            endpoint_model=self.endpoint_model,
            endpoint_port=self.endpoint_port,
        )

    @property
    def active_bindings(self) -> tuple[PoEAuthorizedBinding, ...]:
        return (self.authorized_binding,)


def declares_pse_evidence(result: PoEClaim) -> bool:
    """Whether this record presents itself as PSE evidence at all.

    A record that says it is PSE and then fails validation is an unusable
    claim of a known kind, not an unreadable fact of an unknown one. It
    authorizes nothing on its own, and it is not evidence that some other,
    independently valid claim is wrong.
    """
    dimensions = getattr(result, "dimensions", None) or {}
    return dimensions.get(POE_PSE_EVIDENCE_KIND) == PSE_EVIDENCE_KIND


def encode_poe_pse_dimensions(scope: PoEPseDeliveryScope) -> dict[str, str]:
    """Encode one exact PSE scope, refusing anything incoherent."""

    canonical = _canonical_scope(scope)
    if canonical is None:
        raise ValueError("PSE delivery scope is incomplete or incoherent")
    return {
        POE_PSE_EVIDENCE_KIND: PSE_EVIDENCE_KIND,
        POE_PSE_SCHEMA_VERSION: str(canonical.schema_version),
        POE_PSE_SWITCH_MODEL: canonical.switch_model,
        POE_PSE_SWITCH_PORT: canonical.switch_port,
        POE_PSE_ENDPOINT_MODEL: canonical.endpoint_model,
        POE_PSE_ENDPOINT_PORT: canonical.endpoint_port,
        POE_PSE_PACKET_TRACER_BUILD: canonical.packet_tracer_build,
        POE_PSE_OBSERVER_ID: canonical.observer_id,
        POE_PSE_EXPERIMENT_ID: canonical.experiment_id,
        POE_PSE_OBSERVED_AT: canonical.observed_at,
        POE_PSE_CAPTURES: _canonical_json(
            [_capture_payload(item) for item in canonical.captures]
        ),
        POE_PSE_GATES: _canonical_json(list(canonical.gates)),
        POE_PSE_SIMULTANEOUS_ACTIVE_PORTS: str(canonical.simultaneous_active_ports),
        POE_PSE_CLEANUP_STATUS: canonical.cleanup_status,
        POE_PSE_INVENTORY_RESTORATION: canonical.inventory_restoration,
        POE_PSE_LIVE_SAFETY: canonical.live_safety,
    }


def decode_poe_pse_delivery_scope(
    result: PoEClaim,
    *,
    expected_model: str | None = None,
    expected_packet_tracer_version: str | None = None,
) -> PoEPseDeliveryScope | None:
    """Decode a positive PSE claim, or refuse it entirely.

    POE-3A productivises positive PSE evidence only. A PSE reading that says
    "not delivering" is a measured fact about one binding on one build; it is
    not a statement that the switch has no PoE, so it is never decoded into a
    claim here and cannot become UNSUPPORTED by this route.
    """

    if result.capability != "supports_poe":
        return None
    if not declares_pse_evidence(result):
        return None
    # Positive only. Nothing here ever authorises a negative.
    if result.status is not CapabilityStatus.SUPPORTED:
        return None
    if not result.verified:
        return None
    if _claim_source(result) not in _PSE_EVIDENCE_SOURCES:
        return None
    evidence_version = getattr(result, "packet_tracer_version", None)
    if not _exact_identity(evidence_version):
        return None

    dimensions = result.dimensions
    if dimensions.get(POE_PSE_SCHEMA_VERSION) != str(PSE_SCHEMA_VERSION):
        return None
    captures = _decode_captures(dimensions.get(POE_PSE_CAPTURES))
    gates = _decode_string_array(dimensions.get(POE_PSE_GATES))
    simultaneous = _non_negative_int(dimensions, POE_PSE_SIMULTANEOUS_ACTIVE_PORTS)
    build = dimensions.get(POE_PSE_PACKET_TRACER_BUILD)
    if (
        captures is None
        or gates is None
        or simultaneous is None
        or build != evidence_version
        or (
            expected_packet_tracer_version is not None
            and build != expected_packet_tracer_version
        )
        or (
            expected_model is not None
            and dimensions.get(POE_PSE_SWITCH_MODEL) != expected_model
        )
    ):
        return None

    scope = _canonical_scope(PoEPseDeliveryScope(
        schema_version=PSE_SCHEMA_VERSION,
        switch_model=dimensions.get(POE_PSE_SWITCH_MODEL),
        switch_port=dimensions.get(POE_PSE_SWITCH_PORT),
        endpoint_model=dimensions.get(POE_PSE_ENDPOINT_MODEL),
        endpoint_port=dimensions.get(POE_PSE_ENDPOINT_PORT),
        packet_tracer_build=build,
        observer_id=dimensions.get(POE_PSE_OBSERVER_ID),
        experiment_id=dimensions.get(POE_PSE_EXPERIMENT_ID),
        observed_at=dimensions.get(POE_PSE_OBSERVED_AT),
        captures=captures,
        gates=gates,
        simultaneous_active_ports=simultaneous,
        cleanup_status=dimensions.get(POE_PSE_CLEANUP_STATUS),
        inventory_restoration=dimensions.get(POE_PSE_INVENTORY_RESTORATION),
        live_safety=dimensions.get(POE_PSE_LIVE_SAFETY),
    ))
    if scope is None:
        return None

    # Re-encoding has to reproduce the record exactly. A dimension the decoder
    # ignored but the producer wrote would otherwise ride along unchecked.
    encoded = encode_poe_pse_dimensions(scope)
    if any(dimensions.get(key) != value for key, value in encoded.items()):
        return None
    if result.observed_value != scope.simultaneous_active_ports:
        return None
    return scope


def _canonical_scope(scope: PoEPseDeliveryScope) -> PoEPseDeliveryScope | None:
    captures = tuple(scope.captures)
    gates = tuple(scope.gates)
    if scope.schema_version != PSE_SCHEMA_VERSION:
        return None
    if any(not _exact_identity(value) for value in (
        scope.switch_model, scope.switch_port, scope.endpoint_model,
        scope.endpoint_port, scope.packet_tracer_build, scope.observer_id,
        scope.experiment_id,
    )):
        return None
    if not _canonical_utc_timestamp(scope.observed_at):
        return None
    if scope.cleanup_status != _CLEAN_QUALIFICATION:
        return None
    if scope.inventory_restoration != _RESTORED_INVENTORY:
        return None
    if scope.live_safety != _ADMITTED_LIVE_SAFETY:
        return None
    # Every gate, on the whole run. A partial capture cannot be read at all,
    # so it certainly cannot establish that power was or was not delivered.
    if tuple(sorted(set(gates))) != _REQUIRED_GATES or len(gates) != len(set(gates)):
        return None
    # One port watched, one port proven. This contract cannot speak to
    # simultaneity it never exercised.
    if scope.simultaneous_active_ports != 1:
        return None
    if tuple(item.label for item in captures) != _CAUSAL_SEQUENCE:
        return None
    for capture in captures:
        expected_delivering = _DELIVERING_BY_LABEL[capture.label]
        if (
            capture.admin_mode != _ADMIN_BY_LABEL[capture.label]
            or capture.delivering is not expected_delivering
            or not isinstance(capture.power_watts, float)
            or not isinstance(capture.row_present, bool)
        ):
            return None
        if expected_delivering:
            # Delivering means the PSE says so: the row is there, the
            # operational state is on, and the wattage is real.
            if (
                not capture.row_present
                or capture.oper_state != "on"
                or capture.power_watts <= 0
            ):
                return None
        else:
            # Not delivering under `never`: either the row is gone, or it is
            # present and explicitly off at zero. Nothing in between.
            if capture.power_watts != 0 or capture.oper_state not in {"off", "absent"}:
                return None
            if capture.row_present and capture.oper_state != "off":
                return None
            if not capture.row_present and capture.oper_state != "absent":
                return None
    return PoEPseDeliveryScope(
        schema_version=PSE_SCHEMA_VERSION,
        switch_model=scope.switch_model,
        switch_port=scope.switch_port,
        endpoint_model=scope.endpoint_model,
        endpoint_port=scope.endpoint_port,
        packet_tracer_build=scope.packet_tracer_build,
        observer_id=scope.observer_id,
        experiment_id=scope.experiment_id,
        observed_at=scope.observed_at,
        captures=captures,
        gates=tuple(sorted(gates)),
        simultaneous_active_ports=scope.simultaneous_active_ports,
        cleanup_status=scope.cleanup_status,
        inventory_restoration=scope.inventory_restoration,
        live_safety=scope.live_safety,
    )


def _capture_payload(capture: PoEPseCapture) -> dict[str, object]:
    return {
        "label": capture.label,
        "admin_mode": capture.admin_mode,
        "oper_state": capture.oper_state,
        "power_watts": capture.power_watts,
        "row_present": capture.row_present,
        "delivering": capture.delivering,
    }


def _decode_captures(raw: str | None) -> tuple[PoEPseCapture, ...] | None:
    parsed = _load_json_array(raw)
    if parsed is None:
        return None
    expected_keys = {
        "label", "admin_mode", "oper_state", "power_watts",
        "row_present", "delivering",
    }
    captures: list[PoEPseCapture] = []
    for item in parsed:
        if not isinstance(item, dict) or set(item) != expected_keys:
            return None
        if (
            not _exact_identity(item["label"])
            or not _exact_identity(item["admin_mode"])
            or not _exact_identity(item["oper_state"])
            or not isinstance(item["row_present"], bool)
            or not isinstance(item["delivering"], bool)
            or isinstance(item["power_watts"], bool)
            or not isinstance(item["power_watts"], (int, float))
        ):
            return None
        captures.append(PoEPseCapture(
            label=item["label"],
            admin_mode=item["admin_mode"],
            oper_state=item["oper_state"],
            power_watts=float(item["power_watts"]),
            row_present=item["row_present"],
            delivering=item["delivering"],
        ))
    result = tuple(captures)
    payload = [_capture_payload(item) for item in result]
    return result if raw == _canonical_json(payload) else None


def _decode_string_array(raw: str | None) -> tuple[str, ...] | None:
    parsed = _load_json_array(raw)
    if parsed is None or any(not _exact_identity(item) for item in parsed):
        return None
    values = tuple(parsed)
    return values if raw == _canonical_json(list(values)) else None


def _load_json_array(raw: str | None) -> list[object] | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, list) else None


def _non_negative_int(dimensions: Mapping[str, str], key: str) -> int | None:
    raw = dimensions.get(key)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 and str(value) == raw else None


def _claim_source(result: PoEClaim) -> EvidenceSource | None:
    source = getattr(result, "source", None)
    if source is None:
        source = getattr(result, "evidence_source", None)
    return source if isinstance(source, EvidenceSource) else None


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def _exact_identity(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _canonical_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return (
        parsed.utcoffset() == timezone.utc.utcoffset(parsed)
        and parsed.isoformat().replace("+00:00", "Z") == value
    )
