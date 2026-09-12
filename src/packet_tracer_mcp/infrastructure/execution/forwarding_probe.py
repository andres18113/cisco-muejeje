"""Shared bind-before-ping execution for E9 and CP-LIVE forwarding."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from ...domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ...domain.enterprise.models.forwarding import (
    ForwardingAddressObservation,
    ForwardingEndpointBinding,
    ForwardingRuntimeEndpoint,
)
from ...domain.enterprise.services.forwarding_target import (
    bind_forwarding_address,
    coobserved_binding_conflict,
    forwarding_binding_stability,
)
from ...domain.models.typed_ping import TypedPingResult


class EndpointAddressObserver(Protocol):
    def observe(
        self,
        runtime_device_name: str,
        interface: str,
    ) -> ForwardingAddressObservation: ...


class PingExecutor(Protocol):
    def ping(self, source_device: str, destination: str) -> TypedPingResult: ...


@dataclass(frozen=True)
class ForwardingProbeResult:
    status: ActionExecutionStatus
    source_binding: ForwardingEndpointBinding | None = None
    destination_binding: ForwardingEndpointBinding | None = None
    ping: TypedPingResult | None = None
    before: tuple[ForwardingAddressObservation, ...] = ()
    after: tuple[ForwardingAddressObservation, ...] = ()
    communication_observed: bool = False
    message: str = ""
    bindings_stable: bool = False

    @property
    def verified(self) -> bool:
        return self.status is ActionExecutionStatus.VERIFIED

    @property
    def retryable_reachability_mismatch(self) -> bool:
        return bool(
            self.status is ActionExecutionStatus.FAILED
            and self.communication_observed
            and self.ping is not None
            and self.ping.reachable is False
        )


class ForwardingProbeExecutor:
    """Validate selected endpoints before and after one typed ping."""

    def __init__(
        self,
        addresses: EndpointAddressObserver,
        ping: PingExecutor,
    ) -> None:
        self._addresses = addresses
        self._ping = ping

    def probe_once(
        self,
        *,
        source_device_name: str,
        destination_endpoint: ForwardingRuntimeEndpoint,
        source_endpoint: ForwardingRuntimeEndpoint | None = None,
        expected_reachable: bool = True,
    ) -> ForwardingProbeResult:
        targets = tuple(
            item
            for item in (source_endpoint, destination_endpoint)
            if item is not None
        )
        before = tuple(self._observe(item) for item in targets)
        decisions = tuple(
            bind_forwarding_address(target, observation)
            for target, observation in zip(targets, before, strict=True)
        )
        first_unbound = next((item for item in decisions if not item.verified), None)
        if first_unbound is not None:
            return ForwardingProbeResult(
                first_unbound.status,
                before=before,
                message=first_unbound.message,
            )
        bindings = tuple(
            item.binding for item in decisions if item.binding is not None
        )
        conflict = coobserved_binding_conflict(bindings)
        if conflict:
            return ForwardingProbeResult(
                ActionExecutionStatus.FAILED,
                source_binding=(bindings[0] if source_endpoint is not None else None),
                destination_binding=bindings[-1],
                before=before,
                message=conflict,
            )
        source_binding = bindings[0] if source_endpoint is not None else None
        destination_binding = bindings[-1]
        try:
            ping = self._ping.ping(source_device_name, destination_binding.ipv4)
        except Exception as exc:
            return ForwardingProbeResult(
                ActionExecutionStatus.UNOBSERVABLE,
                source_binding,
                destination_binding,
                before=before,
                message=f"Typed ping raised {type(exc).__name__}: {exc}",
            )
        after = tuple(self._observe(item) for item in targets)
        stable = tuple(
            forwarding_binding_stability(binding, observation)
            for binding, observation in zip(bindings, after, strict=True)
        )
        first_drift = next((item for item in stable if not item.verified), None)
        if first_drift is not None:
            return ForwardingProbeResult(
                first_drift.status,
                source_binding,
                destination_binding,
                ping,
                before,
                after,
                False,
                first_drift.message,
            )
        attributed = bool(
            ping.fresh_output_observed
            and ping.dispatched_destination == destination_binding.ipv4
            and ping.observed_device_name == source_device_name
            and ping.device_identity_provenance == "confirmed_unique"
        )
        if not attributed:
            return ForwardingProbeResult(
                ActionExecutionStatus.UNOBSERVABLE,
                source_binding,
                destination_binding,
                ping,
                before,
                after,
                False,
                ping.failure_reason or "Typed ping source/destination attribution is incomplete.",
                True,
            )
        matched = ping.reachable is expected_reachable
        return ForwardingProbeResult(
            ActionExecutionStatus.VERIFIED if matched else ActionExecutionStatus.FAILED,
            source_binding,
            destination_binding,
            ping,
            before,
            after,
            True,
            (
                f"Fresh attributed typed ping matched reachable={expected_reachable}."
                if matched
                else f"Fresh attributed typed ping differed from reachable={expected_reachable}."
            ),
            True,
        )

    def _observe(
        self,
        target: ForwardingRuntimeEndpoint,
    ) -> ForwardingAddressObservation:
        return self._addresses.observe(
            target.runtime_device_name,
            target.selection.endpoint_interface,
        )


def forwarding_probe_evidence(result: object) -> dict[str, object]:
    """Serialize every acquired boundary without inventing a missing ping."""

    if not isinstance(result, ForwardingProbeResult):
        return {
            "status": ActionExecutionStatus.UNOBSERVABLE.value,
            "source_binding": None,
            "destination_binding": None,
            "ping": None,
            "before": [],
            "after": [],
            "communication_observed": False,
            "message": "Forwarding adapter returned an incomplete probe object.",
            "bindings_stable": False,
        }
    return {
        "status": result.status.value,
        "source_binding": (
            asdict(result.source_binding) if result.source_binding else None
        ),
        "destination_binding": (
            asdict(result.destination_binding) if result.destination_binding else None
        ),
        "ping": asdict(result.ping) if result.ping else None,
        "before": [asdict(item) for item in result.before],
        "after": [asdict(item) for item in result.after],
        "communication_observed": result.communication_observed,
        "message": result.message,
        "bindings_stable": result.bindings_stable,
    }
