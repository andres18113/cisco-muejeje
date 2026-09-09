"""PoE delivery claim boundaries shared by discovery and evidence reuse."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ..models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
    PoEAuthorizedBinding,
)
from ..models.discovery import RuntimePortDescriptor
from .poe_pse_claims import decode_poe_pse_delivery_scope
from .poe_pse_multiport_claims import decode_poe_pse_multi_port_delivery_scope


POE_ACCESS_PORT_COUNT = "poe_access_port_count"
POE_CONTROL_SUPPORTED_PORTS = "poe_control_supported_ports"
POE_DELIVERY_TESTED_PORTS = "poe_delivery_tested_ports"
POE_DELIVERY_ACTIVE_PORTS = "poe_delivery_active_ports"
POE_ACCESS_PORTS = "poe_access_ports"
POE_DELIVERY_TESTED_BINDINGS = "poe_delivery_tested_bindings"
POE_DELIVERY_ACTIVE_BINDINGS = "poe_delivery_active_bindings"
POE_DELIVERY_SIMULTANEOUS_ACTIVE_PORTS = (
    "poe_delivery_simultaneous_active_ports"
)
POE_DELIVERY_COMPARISON_MODEL = "poe_delivery_comparison_model"
POE_DELIVERY_COMPARISON_STATES = "poe_delivery_comparison_states"
POE_DELIVERY_OBSERVATION_METHOD = "poe_delivery_observation_method"
POE_DELIVERY_OBSERVER_ID = "poe_delivery_observer_id"
POE_DELIVERY_CANDIDATE_MODEL = "poe_delivery_candidate_model"
POE_DELIVERY_PACKET_TRACER_BUILD = "poe_delivery_packet_tracer_build"
POE_DELIVERY_CLEANUP_STATUS = "poe_delivery_cleanup_status"
POE_DELIVERY_INVENTORY_RESTORATION = "poe_delivery_inventory_restoration"
POE_DELIVERY_OBSERVED_AT = "poe_delivery_observed_at"

_NEGATIVE_COMPARISON_STATE = "not_powered"
_CLEAN_QUALIFICATION = "clean"
_RESTORED_INVENTORY = "restored"
_AUTHORIZED_OBSERVATION_METHODS = frozenset({"manual_visible_power_state"})

_POE_DELIVERY_EVIDENCE_SOURCES = frozenset({
    EvidenceSource.STATIC_OVERRIDE,
    EvidenceSource.MANUAL_VERIFICATION,
})


@dataclass(frozen=True, order=True)
class PoEDeliveryTestedBinding:
    """Candidate binding paired with its exact differential-control outcome."""

    switch_port: str
    comparison_port: str
    endpoint_model: str
    endpoint_port: str
    candidate_state: str
    comparison_state: str
    candidate_indicator: str
    comparison_indicator: str
    candidate_ready: bool
    comparison_ready: bool

    @property
    def authorized_binding(self) -> PoEAuthorizedBinding:
        return PoEAuthorizedBinding(
            switch_port=self.switch_port,
            endpoint_model=self.endpoint_model,
            endpoint_port=self.endpoint_port,
        )


@dataclass(frozen=True)
class PoEDeliveryClaimScope:
    """Canonical exact scope carried by one reusable PoE delivery claim."""

    candidate_model: str
    packet_tracer_build: str
    access_ports: tuple[str, ...]
    tested_bindings: tuple[PoEDeliveryTestedBinding, ...]
    active_bindings: tuple[PoEAuthorizedBinding, ...]
    simultaneous_active_ports: int
    comparison_model: str
    observation_method: str
    observer_id: str
    observed_at: str
    cleanup_status: str
    inventory_restoration: str

    @property
    def comparison_states(self) -> tuple[str, ...]:
        return tuple(binding.comparison_state for binding in self.tested_bindings)


@dataclass(frozen=True)
class PoEDeliveryAssessment:
    """What one simultaneous access-port observation can actually authorize."""

    access_port_count: int
    control_supported_ports: int
    delivery_tested_ports: int
    delivery_active_ports: int

    @property
    def status(self) -> CapabilityStatus:
        if self.delivery_active_ports:
            return CapabilityStatus.SUPPORTED
        if (
            self.access_port_count
            and self.delivery_tested_ports == self.access_port_count
        ):
            return CapabilityStatus.UNSUPPORTED
        return CapabilityStatus.UNKNOWN

    @property
    def observed_value(self) -> int | None:
        if self.status is CapabilityStatus.SUPPORTED:
            return self.delivery_active_ports
        return None

    @property
    def dimensions(self) -> dict[str, str]:
        return {
            POE_ACCESS_PORT_COUNT: str(self.access_port_count),
            POE_CONTROL_SUPPORTED_PORTS: str(self.control_supported_ports),
            POE_DELIVERY_TESTED_PORTS: str(self.delivery_tested_ports),
            POE_DELIVERY_ACTIVE_PORTS: str(self.delivery_active_ports),
        }


def assess_poe_delivery(
    access_ports: Iterable[RuntimePortDescriptor],
) -> PoEDeliveryAssessment:
    """Separate controllable power state from observed endpoint delivery."""

    ports = tuple(access_ports)
    return PoEDeliveryAssessment(
        access_port_count=len(ports),
        control_supported_ports=sum(
            port.poe_status is CapabilityStatus.SUPPORTED for port in ports
        ),
        delivery_tested_ports=sum(
            port.power_delivery_active is not None for port in ports
        ),
        delivery_active_ports=sum(
            port.power_delivery_active is True for port in ports
        ),
    )


class PoEClaim(Protocol):
    capability: str
    status: CapabilityStatus
    verified: bool
    observed_value: int | None
    dimensions: Mapping[str, str]


def encode_poe_delivery_dimensions(
    scope: PoEDeliveryClaimScope,
) -> dict[str, str]:
    """Encode one exact delivery scope without accepting ambiguous input."""

    canonical_scope = _canonical_scope(scope)
    if canonical_scope is None:
        raise ValueError("PoE delivery scope is incomplete or incoherent")
    return {
        POE_ACCESS_PORT_COUNT: str(len(canonical_scope.access_ports)),
        POE_DELIVERY_TESTED_PORTS: str(len(canonical_scope.tested_bindings)),
        POE_DELIVERY_ACTIVE_PORTS: str(len(canonical_scope.active_bindings)),
        POE_ACCESS_PORTS: _canonical_json(list(canonical_scope.access_ports)),
        POE_DELIVERY_TESTED_BINDINGS: _canonical_json([
            _tested_binding_payload(binding)
            for binding in canonical_scope.tested_bindings
        ]),
        POE_DELIVERY_ACTIVE_BINDINGS: _canonical_json([
            _authorized_binding_payload(binding)
            for binding in canonical_scope.active_bindings
        ]),
        POE_DELIVERY_SIMULTANEOUS_ACTIVE_PORTS: str(
            canonical_scope.simultaneous_active_ports
        ),
        POE_DELIVERY_COMPARISON_MODEL: canonical_scope.comparison_model,
        POE_DELIVERY_COMPARISON_STATES: _canonical_json(
            list(canonical_scope.comparison_states)
        ),
        POE_DELIVERY_OBSERVATION_METHOD: canonical_scope.observation_method,
        POE_DELIVERY_OBSERVER_ID: canonical_scope.observer_id,
        POE_DELIVERY_OBSERVED_AT: canonical_scope.observed_at,
        POE_DELIVERY_CANDIDATE_MODEL: canonical_scope.candidate_model,
        POE_DELIVERY_PACKET_TRACER_BUILD: canonical_scope.packet_tracer_build,
        POE_DELIVERY_CLEANUP_STATUS: canonical_scope.cleanup_status,
        POE_DELIVERY_INVENTORY_RESTORATION: (
            canonical_scope.inventory_restoration
        ),
    }


def decode_poe_delivery_scope(
    result: PoEClaim,
    *,
    expected_model: str | None = None,
    expected_packet_tracer_version: str | None = None,
) -> PoEDeliveryClaimScope | None:
    """Decode a reusable exact scope, rejecting incomplete legacy claims."""

    if result.capability != "supports_poe":
        return None
    if result.status not in {
        CapabilityStatus.SUPPORTED,
        CapabilityStatus.UNSUPPORTED,
    }:
        return None
    if not result.verified:
        return None
    if _claim_source(result) not in _POE_DELIVERY_EVIDENCE_SOURCES:
        return None
    evidence_version = getattr(result, "packet_tracer_version", None)
    if not _exact_identity(evidence_version):
        return None

    dimensions = result.dimensions
    access_ports = _decode_access_ports(dimensions.get(POE_ACCESS_PORTS))
    tested_bindings = _decode_tested_bindings(
        dimensions.get(POE_DELIVERY_TESTED_BINDINGS)
    )
    active_bindings = _decode_active_bindings(
        dimensions.get(POE_DELIVERY_ACTIVE_BINDINGS)
    )
    comparison_states = _decode_string_array(
        dimensions.get(POE_DELIVERY_COMPARISON_STATES)
    )
    simultaneous = _non_negative_int(
        dimensions, POE_DELIVERY_SIMULTANEOUS_ACTIVE_PORTS,
    )
    comparison_model = dimensions.get(POE_DELIVERY_COMPARISON_MODEL)
    observation_method = dimensions.get(POE_DELIVERY_OBSERVATION_METHOD)
    observer_id = dimensions.get(POE_DELIVERY_OBSERVER_ID)
    observed_at = dimensions.get(POE_DELIVERY_OBSERVED_AT)
    candidate_model = dimensions.get(POE_DELIVERY_CANDIDATE_MODEL)
    packet_tracer_build = dimensions.get(POE_DELIVERY_PACKET_TRACER_BUILD)
    cleanup_status = dimensions.get(POE_DELIVERY_CLEANUP_STATUS)
    inventory_restoration = dimensions.get(
        POE_DELIVERY_INVENTORY_RESTORATION
    )
    if (
        access_ports is None
        or tested_bindings is None
        or active_bindings is None
        or comparison_states is None
        or simultaneous is None
        or not _exact_identity(comparison_model)
        or not _exact_identity(observation_method)
        or not _exact_identity(observer_id)
        or not _canonical_utc_timestamp(observed_at)
        or not _exact_identity(candidate_model)
        or not _exact_identity(packet_tracer_build)
        or packet_tracer_build != evidence_version
        or cleanup_status != _CLEAN_QUALIFICATION
        or inventory_restoration != _RESTORED_INVENTORY
        or observation_method not in _AUTHORIZED_OBSERVATION_METHODS
        or (
            expected_model is not None
            and candidate_model != expected_model
        )
        or (
            expected_packet_tracer_version is not None
            and packet_tracer_build != expected_packet_tracer_version
        )
    ):
        return None

    scope = _canonical_scope(PoEDeliveryClaimScope(
        candidate_model=candidate_model,
        packet_tracer_build=packet_tracer_build,
        access_ports=access_ports,
        tested_bindings=tested_bindings,
        active_bindings=active_bindings,
        simultaneous_active_ports=simultaneous,
        comparison_model=comparison_model,
        observation_method=observation_method,
        observer_id=observer_id,
        observed_at=observed_at,
        cleanup_status=cleanup_status,
        inventory_restoration=inventory_restoration,
    ))
    if scope is None:
        return None
    if comparison_states != scope.comparison_states:
        return None

    encoded = encode_poe_delivery_dimensions(scope)
    if any(dimensions.get(key) != value for key, value in encoded.items()):
        return None
    if result.observed_value != scope.simultaneous_active_ports:
        return None
    if result.status is CapabilityStatus.SUPPORTED:
        return scope if scope.active_bindings else None

    tested_ports = {binding.switch_port for binding in scope.tested_bindings}
    if scope.active_bindings or tested_ports != set(scope.access_ports):
        return None
    return scope


@dataclass(frozen=True)
class PoEAuthorizedClaim:
    """What one validated PoE claim authorizes, whatever proved it.

    This is the only PoE vocabulary the resolver and the providers see. Manual
    receipts and PSE readings are validated by their own contracts, against
    their own rules, and meet here -- so a consumer can never tell, or depend
    on, which mechanism established a binding.
    """

    active_bindings: tuple[PoEAuthorizedBinding, ...]
    simultaneous_active_ports: int


def decode_poe_authorized_claim(
    result: PoEClaim,
    *,
    expected_model: str | None = None,
    expected_packet_tracer_version: str | None = None,
) -> PoEAuthorizedClaim | None:
    """Decode one claim through whichever independent basis it belongs to.

    The bases are tried, never merged: a manual receipt is validated only by
    the manual contract and a PSE reading only by the PSE contract. Neither
    can lend the other a field it did not prove.
    """

    manual = decode_poe_delivery_scope(
        result,
        expected_model=expected_model,
        expected_packet_tracer_version=expected_packet_tracer_version,
    )
    if manual is not None:
        return PoEAuthorizedClaim(
            active_bindings=manual.active_bindings,
            simultaneous_active_ports=manual.simultaneous_active_ports,
        )
    pse = decode_poe_pse_delivery_scope(
        result,
        expected_model=expected_model,
        expected_packet_tracer_version=expected_packet_tracer_version,
    )
    if pse is not None:
        return PoEAuthorizedClaim(
            active_bindings=pse.active_bindings,
            simultaneous_active_ports=pse.simultaneous_active_ports,
        )
    multi_port_pse = decode_poe_pse_multi_port_delivery_scope(
        result,
        expected_model=expected_model,
        expected_packet_tracer_version=expected_packet_tracer_version,
    )
    if multi_port_pse is not None:
        return PoEAuthorizedClaim(
            active_bindings=multi_port_pse.active_bindings,
            simultaneous_active_ports=multi_port_pse.simultaneous_active_ports,
        )
    return None


def poe_claim_has_delivery_basis(result: PoEClaim) -> bool:
    """Accept decided PoE claims only when an exact scope decodes."""

    if result.capability != "supports_poe":
        return True
    if result.status is CapabilityStatus.UNKNOWN:
        return True
    if hasattr(result, "context"):
        context = getattr(result, "context", None)
        if context is None or context.live_session_safety is None:
            return False
        from ..rules.live_session_safety import (
            validate_live_session_positive_admission,
        )

        if not validate_live_session_positive_admission(
            context.live_session_safety,
        ).is_valid:
            return False
    return decode_poe_authorized_claim(result) is not None


def _claim_source(result: PoEClaim) -> EvidenceSource | None:
    source = getattr(result, "source", None)
    if source is None:
        source = getattr(result, "evidence_source", None)
    return source if isinstance(source, EvidenceSource) else None


def _non_negative_int(dimensions: Mapping[str, str], key: str) -> int | None:
    raw = dimensions.get(key)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 and str(value) == raw else None


def _canonical_scope(scope: PoEDeliveryClaimScope) -> PoEDeliveryClaimScope | None:
    access_ports = tuple(scope.access_ports)
    tested_bindings = tuple(scope.tested_bindings)
    active_bindings = tuple(scope.active_bindings)
    if (
        not access_ports
        or any(not _exact_identity(port) for port in access_ports)
        or len(set(access_ports)) != len(access_ports)
        or not tested_bindings
        or len(set(tested_bindings)) != len(tested_bindings)
        or len({item.authorized_binding for item in tested_bindings})
        != len(tested_bindings)
        or len({item.switch_port for item in tested_bindings})
        != len(tested_bindings)
        or len({item.comparison_port for item in tested_bindings})
        != len(tested_bindings)
        or len(set(active_bindings)) != len(active_bindings)
        or len({item.switch_port for item in active_bindings})
        != len(active_bindings)
        or not _exact_identity(scope.candidate_model)
        or not _exact_identity(scope.packet_tracer_build)
        or not _exact_identity(scope.comparison_model)
        or scope.observation_method not in _AUTHORIZED_OBSERVATION_METHODS
        or not _exact_identity(scope.observer_id)
        or not _canonical_utc_timestamp(scope.observed_at)
        or scope.cleanup_status != _CLEAN_QUALIFICATION
        or scope.inventory_restoration != _RESTORED_INVENTORY
        or scope.simultaneous_active_ports != len(active_bindings)
    ):
        return None
    if any(
        not _exact_identity(value)
        for binding in tested_bindings
        for value in (
            binding.switch_port,
            binding.comparison_port,
            binding.endpoint_model,
            binding.endpoint_port,
        )
    ):
        return None
    if any(
        binding.candidate_state not in {"powered", "not_powered"}
        or binding.comparison_state != _NEGATIVE_COMPARISON_STATE
        or not _exact_identity(binding.candidate_indicator)
        or not _exact_identity(binding.comparison_indicator)
        or binding.candidate_ready is not True
        or binding.comparison_ready is not True
        for binding in tested_bindings
    ):
        return None
    if any(
        not _exact_identity(value)
        for binding in active_bindings
        for value in (
            binding.switch_port,
            binding.endpoint_model,
            binding.endpoint_port,
        )
    ):
        return None

    access_set = set(access_ports)
    tested_authorized = {
        binding.authorized_binding for binding in tested_bindings
    }
    visibly_active = {
        binding.authorized_binding
        for binding in tested_bindings
        if binding.candidate_state == "powered"
    }
    if (
        any(binding.switch_port not in access_set for binding in tested_bindings)
        or not set(active_bindings) <= tested_authorized
        or set(active_bindings) != visibly_active
    ):
        return None
    return PoEDeliveryClaimScope(
        candidate_model=scope.candidate_model,
        packet_tracer_build=scope.packet_tracer_build,
        access_ports=tuple(sorted(access_ports)),
        tested_bindings=tuple(sorted(tested_bindings)),
        active_bindings=tuple(sorted(active_bindings)),
        simultaneous_active_ports=scope.simultaneous_active_ports,
        comparison_model=scope.comparison_model,
        observation_method=scope.observation_method,
        observer_id=scope.observer_id,
        observed_at=scope.observed_at,
        cleanup_status=scope.cleanup_status,
        inventory_restoration=scope.inventory_restoration,
    )


def _decode_access_ports(raw: str | None) -> tuple[str, ...] | None:
    parsed = _load_json_array(raw)
    if parsed is None or any(not _exact_identity(item) for item in parsed):
        return None
    ports = tuple(parsed)
    if len(set(ports)) != len(ports):
        return None
    canonical = tuple(sorted(ports))
    return canonical if raw == _canonical_json(list(canonical)) else None


def _decode_tested_bindings(
    raw: str | None,
) -> tuple[PoEDeliveryTestedBinding, ...] | None:
    parsed = _load_json_array(raw)
    if parsed is None:
        return None
    expected_keys = {
        "switch_port", "comparison_port", "endpoint_model", "endpoint_port",
        "candidate_state", "comparison_state", "candidate_indicator",
        "comparison_indicator", "candidate_ready", "comparison_ready",
    }
    bindings: list[PoEDeliveryTestedBinding] = []
    for item in parsed:
        if not isinstance(item, dict) or set(item) != expected_keys:
            return None
        identity_keys = expected_keys - {"candidate_ready", "comparison_ready"}
        values = tuple(item[key] for key in sorted(identity_keys))
        if (
            any(not _exact_identity(value) for value in values)
            or not isinstance(item["candidate_ready"], bool)
            or not isinstance(item["comparison_ready"], bool)
        ):
            return None
        bindings.append(PoEDeliveryTestedBinding(**item))
    if (
        len(set(bindings)) != len(bindings)
        or len({binding.authorized_binding for binding in bindings}) != len(bindings)
    ):
        return None
    canonical = tuple(sorted(bindings))
    payload = [_tested_binding_payload(binding) for binding in canonical]
    return canonical if raw == _canonical_json(payload) else None


def _decode_active_bindings(
    raw: str | None,
) -> tuple[PoEAuthorizedBinding, ...] | None:
    parsed = _load_json_array(raw)
    if parsed is None:
        return None
    expected_keys = {"switch_port", "endpoint_model", "endpoint_port"}
    bindings: list[PoEAuthorizedBinding] = []
    for item in parsed:
        if not isinstance(item, dict) or set(item) != expected_keys:
            return None
        values = tuple(item[key] for key in sorted(expected_keys))
        if any(not _exact_identity(value) for value in values):
            return None
        bindings.append(PoEAuthorizedBinding(**item))
    if len(set(bindings)) != len(bindings):
        return None
    canonical = tuple(sorted(bindings))
    payload = [_authorized_binding_payload(binding) for binding in canonical]
    return canonical if raw == _canonical_json(payload) else None


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


def _authorized_binding_payload(binding: PoEAuthorizedBinding) -> dict[str, str]:
    return {
        "switch_port": binding.switch_port,
        "endpoint_model": binding.endpoint_model,
        "endpoint_port": binding.endpoint_port,
    }


def _tested_binding_payload(
    binding: PoEDeliveryTestedBinding,
) -> dict[str, str | bool]:
    return {
        "switch_port": binding.switch_port,
        "comparison_port": binding.comparison_port,
        "endpoint_model": binding.endpoint_model,
        "endpoint_port": binding.endpoint_port,
        "candidate_state": binding.candidate_state,
        "comparison_state": binding.comparison_state,
        "candidate_indicator": binding.candidate_indicator,
        "comparison_indicator": binding.comparison_indicator,
        "candidate_ready": binding.candidate_ready,
        "comparison_ready": binding.comparison_ready,
    }


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
