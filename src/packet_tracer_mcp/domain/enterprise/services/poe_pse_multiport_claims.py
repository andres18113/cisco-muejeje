"""Closed multi-port PSE delivery evidence contract (schema 3).

Schema 2 remains the historical single-port contract in ``poe_pse_claims``.
This sibling contract names every authorized binding and observes that exact,
ordered set through one simultaneous AUTO -> NEVER -> AUTO qualification.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ..models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
    PoEAuthorizedBinding,
)
from .poe_pse_claims import (
    PSE_EVIDENCE_KIND,
    POE_PSE_CAPTURES,
    POE_PSE_CLEANUP_STATUS,
    POE_PSE_EVIDENCE_KIND,
    POE_PSE_EXPERIMENT_ID,
    POE_PSE_GATES,
    POE_PSE_INVENTORY_RESTORATION,
    POE_PSE_OBSERVED_AT,
    POE_PSE_OBSERVER_ID,
    POE_PSE_PACKET_TRACER_BUILD,
    POE_PSE_SCHEMA_VERSION,
    POE_PSE_SIMULTANEOUS_ACTIVE_PORTS,
    POE_PSE_SWITCH_MODEL,
    _REQUIRED_GATES,
)


PSE_MULTI_PORT_SCHEMA_VERSION = 3
POE_PSE_BINDINGS = "poe_pse_bindings"

_CAUSAL_SEQUENCE = ("AUTO_1", "NEVER", "AUTO_2")
_ADMIN_BY_LABEL = {"AUTO_1": "auto", "NEVER": "never", "AUTO_2": "auto"}
_DELIVERING_BY_LABEL = {"AUTO_1": True, "NEVER": False, "AUTO_2": True}
_CLEAN_QUALIFICATION = "clean"
_RESTORED_INVENTORY = "restored"
_PSE_EVIDENCE_SOURCES = frozenset({EvidenceSource.CONTROLLED_PROBE})

PSE_SCHEMA_3_DIMENSIONS = frozenset({
    POE_PSE_EVIDENCE_KIND,
    POE_PSE_SCHEMA_VERSION,
    POE_PSE_SWITCH_MODEL,
    POE_PSE_PACKET_TRACER_BUILD,
    POE_PSE_OBSERVER_ID,
    POE_PSE_EXPERIMENT_ID,
    POE_PSE_OBSERVED_AT,
    POE_PSE_BINDINGS,
    POE_PSE_CAPTURES,
    POE_PSE_GATES,
    POE_PSE_SIMULTANEOUS_ACTIVE_PORTS,
    POE_PSE_CLEANUP_STATUS,
    POE_PSE_INVENTORY_RESTORATION,
})


class PoEClaim(Protocol):
    capability: str
    status: CapabilityStatus
    verified: bool
    observed_value: int | None
    dimensions: Mapping[str, str]


@dataclass(frozen=True, order=True)
class PoEPseBindingCapture:
    """One binding's PSE state in one simultaneous capture."""

    switch_port: str
    endpoint_model: str
    endpoint_port: str
    oper_state: str
    power_watts: float
    row_present: bool
    delivering: bool

    @property
    def authorized_binding(self) -> PoEAuthorizedBinding:
        return PoEAuthorizedBinding(
            switch_port=self.switch_port,
            endpoint_model=self.endpoint_model,
            endpoint_port=self.endpoint_port,
        )


@dataclass(frozen=True)
class PoEPseMultiPortCapture:
    """All governed bindings observed together in one administrative mode."""

    label: str
    admin_mode: str
    binding_captures: tuple[PoEPseBindingCapture, ...]


@dataclass(frozen=True)
class PoEPseMultiPortDeliveryScope:
    """The exact ordered binding set proven by one schema-3 qualification."""

    schema_version: int
    switch_model: str
    packet_tracer_build: str
    bindings: tuple[PoEAuthorizedBinding, ...]
    observer_id: str
    experiment_id: str
    observed_at: str
    captures: tuple[PoEPseMultiPortCapture, ...]
    gates: tuple[str, ...]
    simultaneous_active_ports: int
    cleanup_status: str
    inventory_restoration: str

    @property
    def active_bindings(self) -> tuple[PoEAuthorizedBinding, ...]:
        return self.bindings


def encode_poe_pse_multi_port_dimensions(
    scope: PoEPseMultiPortDeliveryScope,
) -> dict[str, str]:
    """Encode one exact multi-port scope, refusing incoherent input."""

    canonical = _canonical_scope(scope)
    if canonical is None:
        raise ValueError("multi-port PSE delivery scope is incomplete or incoherent")
    return {
        POE_PSE_EVIDENCE_KIND: PSE_EVIDENCE_KIND,
        POE_PSE_SCHEMA_VERSION: str(canonical.schema_version),
        POE_PSE_SWITCH_MODEL: canonical.switch_model,
        POE_PSE_PACKET_TRACER_BUILD: canonical.packet_tracer_build,
        POE_PSE_OBSERVER_ID: canonical.observer_id,
        POE_PSE_EXPERIMENT_ID: canonical.experiment_id,
        POE_PSE_OBSERVED_AT: canonical.observed_at,
        POE_PSE_BINDINGS: _canonical_json([
            _binding_payload(binding) for binding in canonical.bindings
        ]),
        POE_PSE_CAPTURES: _canonical_json([
            _capture_payload(capture) for capture in canonical.captures
        ]),
        POE_PSE_GATES: _canonical_json(list(canonical.gates)),
        POE_PSE_SIMULTANEOUS_ACTIVE_PORTS: str(
            canonical.simultaneous_active_ports
        ),
        POE_PSE_CLEANUP_STATUS: canonical.cleanup_status,
        POE_PSE_INVENTORY_RESTORATION: canonical.inventory_restoration,
    }


def decode_poe_pse_multi_port_delivery_scope(
    result: PoEClaim,
    *,
    expected_model: str | None = None,
    expected_packet_tracer_version: str | None = None,
) -> PoEPseMultiPortDeliveryScope | None:
    """Decode only a complete, positive and byte-canonical schema-3 claim."""

    if result.capability != "supports_poe":
        return None
    dimensions = getattr(result, "dimensions", None)
    if not isinstance(dimensions, Mapping):
        return None
    if dimensions.get(POE_PSE_EVIDENCE_KIND) != PSE_EVIDENCE_KIND:
        return None
    if result.status is not CapabilityStatus.SUPPORTED:
        return None
    if result.verified is not True:
        return None
    if _claim_source(result) not in _PSE_EVIDENCE_SOURCES:
        return None
    evidence_version = getattr(result, "packet_tracer_version", None)
    if not _exact_identity(evidence_version):
        return None
    if dimensions.get(POE_PSE_SCHEMA_VERSION) != str(
        PSE_MULTI_PORT_SCHEMA_VERSION
    ):
        return None

    bindings = _decode_bindings(dimensions.get(POE_PSE_BINDINGS))
    captures = _decode_captures(dimensions.get(POE_PSE_CAPTURES))
    gates = _decode_string_array(dimensions.get(POE_PSE_GATES))
    simultaneous = _non_negative_int(
        dimensions, POE_PSE_SIMULTANEOUS_ACTIVE_PORTS,
    )
    build = dimensions.get(POE_PSE_PACKET_TRACER_BUILD)
    if (
        bindings is None
        or captures is None
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

    scope = _canonical_scope(PoEPseMultiPortDeliveryScope(
        schema_version=PSE_MULTI_PORT_SCHEMA_VERSION,
        switch_model=dimensions.get(POE_PSE_SWITCH_MODEL),
        packet_tracer_build=build,
        bindings=bindings,
        observer_id=dimensions.get(POE_PSE_OBSERVER_ID),
        experiment_id=dimensions.get(POE_PSE_EXPERIMENT_ID),
        observed_at=dimensions.get(POE_PSE_OBSERVED_AT),
        captures=captures,
        gates=gates,
        simultaneous_active_ports=simultaneous,
        cleanup_status=dimensions.get(POE_PSE_CLEANUP_STATUS),
        inventory_restoration=dimensions.get(POE_PSE_INVENTORY_RESTORATION),
    ))
    if scope is None:
        return None

    encoded = encode_poe_pse_multi_port_dimensions(scope)
    if set(dimensions) != set(encoded):
        return None
    if any(dimensions.get(key) != value for key, value in encoded.items()):
        return None
    if type(result.observed_value) is not int:
        return None
    if result.observed_value != len(scope.bindings):
        return None
    return scope


def _canonical_scope(
    scope: PoEPseMultiPortDeliveryScope,
) -> PoEPseMultiPortDeliveryScope | None:
    try:
        bindings = tuple(scope.bindings)
        captures = tuple(scope.captures)
        gates = tuple(scope.gates)
    except TypeError:
        return None
    if type(scope.schema_version) is not int:
        return None
    if scope.schema_version != PSE_MULTI_PORT_SCHEMA_VERSION:
        return None
    if any(not _exact_identity(value) for value in (
        scope.switch_model,
        scope.packet_tracer_build,
        scope.observer_id,
        scope.experiment_id,
    )):
        return None
    if not _canonical_utc_timestamp(scope.observed_at):
        return None
    if scope.cleanup_status != _CLEAN_QUALIFICATION:
        return None
    if scope.inventory_restoration != _RESTORED_INVENTORY:
        return None
    if not bindings or any(not _valid_binding(binding) for binding in bindings):
        return None
    if len(bindings) != len(set(bindings)):
        return None
    if tuple(sorted(set(gates))) != _REQUIRED_GATES:
        return None
    if len(gates) != len(set(gates)):
        return None
    if type(scope.simultaneous_active_ports) is not int:
        return None
    if scope.simultaneous_active_ports != len(bindings):
        return None
    if tuple(capture.label for capture in captures) != _CAUSAL_SEQUENCE:
        return None

    for capture in captures:
        if not isinstance(capture, PoEPseMultiPortCapture):
            return None
        if capture.admin_mode != _ADMIN_BY_LABEL[capture.label]:
            return None
        rows = tuple(capture.binding_captures)
        if tuple(row.authorized_binding for row in rows) != bindings:
            return None
        expected_delivering = _DELIVERING_BY_LABEL[capture.label]
        for row in rows:
            if not _valid_binding_capture(row):
                return None
            if row.delivering is not expected_delivering:
                return None
            if expected_delivering:
                if (
                    not row.row_present
                    or row.oper_state != "on"
                    or row.power_watts <= 0
                ):
                    return None
            else:
                if row.power_watts != 0.0:
                    return None
                if row.row_present and row.oper_state != "off":
                    return None
                if not row.row_present and row.oper_state != "absent":
                    return None

    return PoEPseMultiPortDeliveryScope(
        schema_version=PSE_MULTI_PORT_SCHEMA_VERSION,
        switch_model=scope.switch_model,
        packet_tracer_build=scope.packet_tracer_build,
        bindings=bindings,
        observer_id=scope.observer_id,
        experiment_id=scope.experiment_id,
        observed_at=scope.observed_at,
        captures=captures,
        gates=tuple(sorted(gates)),
        simultaneous_active_ports=scope.simultaneous_active_ports,
        cleanup_status=scope.cleanup_status,
        inventory_restoration=scope.inventory_restoration,
    )


def _valid_binding(binding: object) -> bool:
    return (
        isinstance(binding, PoEAuthorizedBinding)
        and _exact_identity(binding.switch_port)
        and _exact_identity(binding.endpoint_model)
        and _exact_identity(binding.endpoint_port)
    )


def _valid_binding_capture(capture: object) -> bool:
    return (
        isinstance(capture, PoEPseBindingCapture)
        and _valid_binding(capture.authorized_binding)
        and _exact_identity(capture.oper_state)
        and isinstance(capture.power_watts, float)
        and math.isfinite(capture.power_watts)
        and isinstance(capture.row_present, bool)
        and isinstance(capture.delivering, bool)
    )


def _binding_payload(binding: PoEAuthorizedBinding) -> dict[str, str]:
    return {
        "switch_port": binding.switch_port,
        "endpoint_model": binding.endpoint_model,
        "endpoint_port": binding.endpoint_port,
    }


def _binding_capture_payload(capture: PoEPseBindingCapture) -> dict[str, object]:
    return {
        **_binding_payload(capture.authorized_binding),
        "oper_state": capture.oper_state,
        "power_watts": capture.power_watts,
        "row_present": capture.row_present,
        "delivering": capture.delivering,
    }


def _capture_payload(capture: PoEPseMultiPortCapture) -> dict[str, object]:
    return {
        "label": capture.label,
        "admin_mode": capture.admin_mode,
        "binding_captures": [
            _binding_capture_payload(item) for item in capture.binding_captures
        ],
    }


def _decode_bindings(raw: object) -> tuple[PoEAuthorizedBinding, ...] | None:
    parsed = _load_json_array(raw)
    if parsed is None:
        return None
    expected_keys = {"switch_port", "endpoint_model", "endpoint_port"}
    bindings: list[PoEAuthorizedBinding] = []
    for item in parsed:
        if not isinstance(item, dict) or set(item) != expected_keys:
            return None
        if any(not _exact_identity(item[key]) for key in expected_keys):
            return None
        bindings.append(PoEAuthorizedBinding(**item))
    result = tuple(bindings)
    payload = [_binding_payload(binding) for binding in result]
    return result if raw == _canonical_json(payload) else None


def _decode_captures(raw: object) -> tuple[PoEPseMultiPortCapture, ...] | None:
    parsed = _load_json_array(raw)
    if parsed is None:
        return None
    captures: list[PoEPseMultiPortCapture] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        if set(item) != {"label", "admin_mode", "binding_captures"}:
            return None
        if not _exact_identity(item["label"]):
            return None
        if not _exact_identity(item["admin_mode"]):
            return None
        rows = _decode_binding_captures(item["binding_captures"])
        if rows is None:
            return None
        captures.append(PoEPseMultiPortCapture(
            label=item["label"],
            admin_mode=item["admin_mode"],
            binding_captures=rows,
        ))
    result = tuple(captures)
    payload = [_capture_payload(capture) for capture in result]
    return result if raw == _canonical_json(payload) else None


def _decode_binding_captures(
    parsed: object,
) -> tuple[PoEPseBindingCapture, ...] | None:
    if not isinstance(parsed, list):
        return None
    expected_keys = {
        "switch_port",
        "endpoint_model",
        "endpoint_port",
        "oper_state",
        "power_watts",
        "row_present",
        "delivering",
    }
    rows: list[PoEPseBindingCapture] = []
    for item in parsed:
        if not isinstance(item, dict) or set(item) != expected_keys:
            return None
        if any(not _exact_identity(item[key]) for key in (
            "switch_port", "endpoint_model", "endpoint_port", "oper_state",
        )):
            return None
        if not isinstance(item["row_present"], bool):
            return None
        if not isinstance(item["delivering"], bool):
            return None
        if isinstance(item["power_watts"], bool):
            return None
        if not isinstance(item["power_watts"], (int, float)):
            return None
        power_watts = float(item["power_watts"])
        if not math.isfinite(power_watts):
            return None
        rows.append(PoEPseBindingCapture(
            switch_port=item["switch_port"],
            endpoint_model=item["endpoint_model"],
            endpoint_port=item["endpoint_port"],
            oper_state=item["oper_state"],
            power_watts=power_watts,
            row_present=item["row_present"],
            delivering=item["delivering"],
        ))
    return tuple(rows)


def _decode_string_array(raw: object) -> tuple[str, ...] | None:
    parsed = _load_json_array(raw)
    if parsed is None or any(not _exact_identity(item) for item in parsed):
        return None
    values = tuple(parsed)
    return values if raw == _canonical_json(list(values)) else None


def _load_json_array(raw: object) -> list[object] | None:
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, list) else None


def _non_negative_int(dimensions: Mapping[str, str], key: str) -> int | None:
    raw = dimensions.get(key)
    if not isinstance(raw, str):
        return None
    try:
        value = int(raw)
    except ValueError:
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
