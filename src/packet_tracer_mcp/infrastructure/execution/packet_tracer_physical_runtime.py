"""Packet Tracer adapter for verified E4 physical deployment.

The adapter reuses the trusted PTBuilder renderers and requires independent
read-back for devices, ports and both ends of every link.  One instance is
bound to one caller-provided transport callback, so ambiguous mutations are
never replayed on a different bridge channel.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
import json

from ...domain.enterprise.models.deployment import runtime_target_fingerprint
from ...domain.enterprise.models.execution import MutationDisposition
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeviceObservation,
    PhysicalLinkObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
)
from ...domain.models.plans import DevicePlan, LinkPlan
from ..generator.ptbuilder_generator import (
    generate_device_command,
    generate_link_command,
)
from .topology_observation import (
    LinkEndpoint,
    LinkExpectation,
    LinkObservationStatus,
    build_exact_link_readback_js,
    parse_exact_link_readback,
    verify_exact_link_convergence,
)


SendAndWait = Callable[[str, float], str | None]


class _MutationAckStatus(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class PacketTracerPhysicalTopologyRuntime:
    """Production Packet Tracer implementation of ``PhysicalTopologyRuntime``."""

    def __init__(
        self,
        send_and_wait: SendAndWait,
        *,
        mutation_timeout_seconds: float = 5.0,
        observation_timeout_seconds: float = 4.0,
    ) -> None:
        self._send_and_wait = send_and_wait
        self._mutation_timeout_seconds = max(0.1, mutation_timeout_seconds)
        self._observation_timeout_seconds = max(0.1, observation_timeout_seconds)

    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult:
        target_id = _device_id(device)
        observation = self.observe_device(device)
        if observation.observed:
            if observation.model != device.model:
                return _failure(
                    target_id,
                    PhysicalObjectKind.DEVICE,
                    f"Existing device {device.name!r} has model "
                    f"{observation.model!r}, expected {device.model!r}.",
                )
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.DEVICE,
                disposition=MutationDisposition.NO_OP,
                message="Exact device identity already exists.",
            )
        if observation.message != "not_found":
            return _failure(
                target_id,
                PhysicalObjectKind.DEVICE,
                "Device pre-readback was inconclusive: " + observation.message,
            )
        ack_status, ack_message = self._mutation_ack(generate_device_command(device))
        if ack_status is _MutationAckStatus.UNKNOWN:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.DEVICE,
                disposition=MutationDisposition.UNKNOWN,
                message=(
                    f"Device creation outcome for {device.name!r} is ambiguous; "
                    f"the mutation will not be replayed. {ack_message}"
                ).strip(),
            )
        if ack_status is _MutationAckStatus.REJECTED:
            return _failure(
                target_id,
                PhysicalObjectKind.DEVICE,
                f"Packet Tracer rejected creation of {device.name!r}: {ack_message}",
            )
        return PhysicalMutationResult(
            target_id=target_id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            message="Device creation acknowledged; independent read-back required.",
        )

    def observe_device(self, device: DevicePlan) -> PhysicalDeviceObservation:
        target_id = _device_id(device)
        raw = self._send_and_wait(
            _device_observation_js(device.name),
            self._observation_timeout_seconds,
        )
        payload = _json_object(raw)
        if payload is None:
            return PhysicalDeviceObservation(
                target_id=target_id,
                observed=False,
                deployed_name=device.name,
                model="",
                interfaces_observed=False,
                message="timeout_or_malformed_response",
            )
        if payload.get("found") is not True:
            return PhysicalDeviceObservation(
                target_id=target_id,
                observed=False,
                deployed_name=device.name,
                model="",
                interfaces_observed=False,
                message="not_found",
            )
        name = payload.get("name")
        model = payload.get("model")
        ports = payload.get("ports")
        if not isinstance(name, str) or not isinstance(model, str) or not isinstance(ports, list):
            return PhysicalDeviceObservation(
                target_id=target_id,
                observed=False,
                deployed_name=device.name,
                model="",
                interfaces_observed=False,
                message="malformed_device_observation",
            )
        interfaces = sorted({item for item in ports if isinstance(item, str)})
        if len(interfaces) != len(ports):
            return PhysicalDeviceObservation(
                target_id=target_id,
                observed=False,
                deployed_name=name,
                model=model,
                interfaces=interfaces,
                interfaces_observed=False,
                message="malformed_port_inventory",
            )
        return PhysicalDeviceObservation(
            target_id=target_id,
            deployed_name=name,
            model=model,
            interfaces=interfaces,
            interfaces_observed=True,
            runtime_identifier="",
            runtime_identifier_stable=False,
            runtime_fingerprint=runtime_target_fingerprint(name, model, interfaces),
            message="fresh_packet_tracer_readback",
        )

    def supports_module_observation(self) -> bool:
        """Packet Tracer has no verified exact module/slot getter in this backend."""

        return False

    def ensure_link(self, link: LinkPlan) -> PhysicalMutationResult:
        target_id = _link_id(link)
        expectation = _link_expectation(link)
        precheck = parse_exact_link_readback(
            self._send_and_wait(
                build_exact_link_readback_js(expectation),
                self._observation_timeout_seconds,
            )
        )
        if precheck.exact:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.LINK,
                disposition=MutationDisposition.NO_OP,
                message="Exact two-ended link already exists.",
            )
        if precheck.port_a_bound or precheck.port_b_bound:
            return _failure(
                target_id,
                PhysicalObjectKind.LINK,
                "A planned endpoint is already bound to a different or unreadable link.",
            )
        if precheck.status is not LinkObservationStatus.NO_LINK:
            return _failure(
                target_id,
                PhysicalObjectKind.LINK,
                "Link pre-readback is not safe for mutation: " + precheck.status.value,
            )
        ack_status, ack_message = self._mutation_ack(generate_link_command(link))
        if ack_status is _MutationAckStatus.UNKNOWN:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.LINK,
                disposition=MutationDisposition.UNKNOWN,
                message=(
                    f"Link creation outcome for {target_id!r} is ambiguous; "
                    f"the mutation will not be replayed. {ack_message}"
                ).strip(),
            )
        if ack_status is _MutationAckStatus.REJECTED:
            return _failure(
                target_id,
                PhysicalObjectKind.LINK,
                f"Packet Tracer rejected creation of link {target_id!r}: {ack_message}",
            )
        return PhysicalMutationResult(
            target_id=target_id,
            target_kind=PhysicalObjectKind.LINK,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            message="Link creation acknowledged; exact two-ended read-back required.",
        )

    def observe_link(self, link: LinkPlan) -> PhysicalLinkObservation:
        target_id = _link_id(link)
        convergence = verify_exact_link_convergence(
            self._send_and_wait,
            _link_expectation(link),
            timeout_seconds=self._observation_timeout_seconds,
        )
        return PhysicalLinkObservation(
            target_id=target_id,
            observed=convergence.verified,
            device_a=link.device_a,
            port_a=link.port_a,
            device_b=link.device_b,
            port_b=link.port_b,
            cable="",
            cable_observed=False,
            message=(
                "fresh_exact_two_ended_readback"
                if convergence.verified
                else "link_readback_" + convergence.observation.status.value.casefold()
            ),
        )

    def _mutation_ack(
        self,
        trusted_command: str,
    ) -> tuple[_MutationAckStatus, str]:
        script = (
            "try{" + trusted_command
            + "reportResult(JSON.stringify({ack:true}));}"
            + "catch(__e){reportResult(JSON.stringify({ack:false,error:String(__e)}));}"
        )
        raw = self._send_and_wait(script, self._mutation_timeout_seconds)
        payload = _json_object(raw)
        if payload is None:
            return (
                _MutationAckStatus.UNKNOWN,
                "The bridge returned no well-formed mutation acknowledgement.",
            )
        if payload.get("ack") is True:
            return _MutationAckStatus.ACKNOWLEDGED, ""
        if payload.get("ack") is False:
            error = payload.get("error")
            return (
                _MutationAckStatus.REJECTED,
                error if isinstance(error, str) and error else "explicit negative acknowledgement",
            )
        return (
            _MutationAckStatus.UNKNOWN,
            "The bridge response did not contain an explicit acknowledgement.",
        )


def _device_observation_js(device_name: str) -> str:
    name = json.dumps(device_name, ensure_ascii=False)
    return (
        "try{var __d=ipc.network().getDevice(" + name + ");"
        "if(!__d){reportResult(JSON.stringify({found:false}));}else{"
        "var __ports=[];for(var __i=0;__i<__d.getPortCount();__i++){"
        "var __p=__d.getPortAt(__i);if(__p){__ports.push(String(__p.getName()));}}"
        "reportResult(JSON.stringify({found:true,name:String(__d.getName()),"
        "model:(typeof __d.getModel==='function'?String(__d.getModel()):''),"
        "ports:__ports}));}}catch(__e){"
        "reportResult(JSON.stringify({found:false,error:String(__e)}));}"
    )


def _json_object(raw: str | None) -> dict[str, object] | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _link_expectation(link: LinkPlan) -> LinkExpectation:
    return LinkExpectation(
        endpoint_a=LinkEndpoint(link.device_a, link.port_a),
        endpoint_b=LinkEndpoint(link.device_b, link.port_b),
    )


def _device_id(device: DevicePlan) -> str:
    return device.id or device.name


def _link_id(link: LinkPlan) -> str:
    return link.id or (
        f"{link.device_a}:{link.port_a}<->{link.device_b}:{link.port_b}"
    )


def _failure(
    target_id: str,
    kind: PhysicalObjectKind,
    message: str,
) -> PhysicalMutationResult:
    return PhysicalMutationResult(
        target_id=target_id,
        target_kind=kind,
        disposition=MutationDisposition.FAILED,
        message=message,
    )
