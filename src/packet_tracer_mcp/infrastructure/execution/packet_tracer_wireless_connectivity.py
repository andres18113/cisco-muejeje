"""Packet Tracer side of the wireless connectivity port.

The adapter is deliberately narrow. It drives exactly the surfaces the audit in
`catalog/wireless_capabilities.py` classifies as SUPPORTED, and refuses to
treat a DOCUMENTED one as if it had been measured: a reference manual licenses
writing a probe, not making a claim.

Failures are typed. A transport exception, a timeout, a script-engine error and
a malformed payload are four different things, and none of them is the absence
of a property, so none of them may surface as UNOBSERVABLE. Each reading keeps
the kind and the stage it failed at, which is what a diagnosis needs.

Reuse over invention: addressing goes through `endpoint_address_read_js`, the
named-interface getter path already qualified for endpoint evidence, instead of
a second script that would have to be qualified all over again.

None of this has been exercised against a running Packet Tracer.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ...domain.enterprise.models.evidence import VerificationMethod
from ...domain.enterprise.models.wireless_connectivity import (
    BackendErrorKind,
    IntendedNetworkSegment,
    WirelessAssociationIntent,
    WirelessAssociationReading,
    WirelessAttachmentReading,
    WirelessCapability,
    WirelessCapabilityAudit,
    WirelessCapabilityStatus,
    WirelessConfigurationOutcome,
    WirelessConfigurationStatus,
)
from ..catalog.measured_port_inventories import MEASURED_BACKEND_VERSION
from ..catalog.wireless_capabilities import packet_tracer_wireless_capability_audit
from .endpoint_address_observer import endpoint_address_read_js


@dataclass(frozen=True)
class WirelessRuntimeEndpoint:
    """What the backend needs to find one planned endpoint in a live workspace."""

    endpoint_id: str
    runtime_device_name: str
    model: str = ""
    interface: str = ""


@dataclass(frozen=True)
class BackendCallOutcome:
    """One backend call: either a payload, or the exact way it failed."""

    stage: str
    value: dict | None = None
    error_kind: BackendErrorKind | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.error_kind is None and self.value is not None


class PacketTracerWirelessConnectivityAdapter:
    """Implements the wireless connectivity port for one Packet Tracer build."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        bindings: Mapping[str, WirelessRuntimeEndpoint],
        *,
        packet_tracer_version: str = MEASURED_BACKEND_VERSION,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._send_and_wait = send_and_wait
        self._bindings = dict(bindings)
        self._version = packet_tracer_version
        self._timeout = timeout_seconds
        self._audit = packet_tracer_wireless_capability_audit(packet_tracer_version)

    @property
    def backend(self) -> str:
        return self._audit.backend

    @property
    def backend_version(self) -> str:
        return self._audit.backend_version

    def capability_audit(self) -> WirelessCapabilityAudit:
        return self._audit

    def configure_association(
        self, intent: WirelessAssociationIntent,
    ) -> WirelessConfigurationOutcome:
        """Never reports APPLIED for something this build has not been measured to do.

        A plan that stays on the backend default service set has nothing to
        apply, which is NOT_ATTEMPTED and not a quiet success. A plan that names
        its own service set is REFUSED while the configuring surface is only
        documented: this phase performs no mutation.
        """
        binding = self._bindings.get(intent.endpoint_id)
        subject = binding.model if binding else ""
        capability = self._audit.status(
            WirelessCapability.SERVICE_SET_CONFIGURATION, subject,
        )
        if intent.service_set.uses_backend_default:
            return WirelessConfigurationOutcome(
                endpoint_id=intent.endpoint_id,
                status=WirelessConfigurationStatus.NOT_ATTEMPTED,
                detail=(
                    "The intent keeps the backend default service set; nothing "
                    "is configured and nothing is claimed."
                ),
            )
        return WirelessConfigurationOutcome(
            endpoint_id=intent.endpoint_id,
            status=WirelessConfigurationStatus.REFUSED,
            detail=(
                f"Service set configuration is {capability.value} on "
                f"{self._audit.identity}; this phase performs no wireless "
                "mutation."
            ),
        )

    def observe_association(
        self, intent: WirelessAssociationIntent,
    ) -> WirelessAssociationReading:
        """Report the radio classification only, and never a pairing.

        The association surfaces are documented and unmeasured on this build,
        so the adapter does not drive them and does not pretend the state is
        absent either. ``unavailable_reading`` is reserved for a member that
        was actually asked for and was not there; an unmeasured capability is
        not an absent property. The access point is left empty on purpose:
        identity has to come from a measured surface, never from proximity.
        """
        binding = self._bindings.get(intent.endpoint_id)
        if binding is None:
            return self._unbound_association(intent)
        subject = binding.model
        state_capability = self._audit.status(
            WirelessCapability.ASSOCIATION_STATE_OBSERVATION, subject,
        )
        radio = self._read_wireless_port(binding)
        base = {
            "endpoint_id": intent.endpoint_id,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "radio_present": radio.value,
        }
        if radio.error_kind is not None:
            return WirelessAssociationReading(
                **base,
                attempted=True,
                error_kind=radio.error_kind,
                error_stage=radio.stage,
                detail=radio.detail,
            )
        if state_capability is WirelessCapabilityStatus.SUPPORTED:
            # Reserved for the build where a measurement has admitted the
            # surface; nothing reaches it today.
            return WirelessAssociationReading(
                **base,
                attempted=False,
                unavailable_reading="WirelessClientProcess.getCurrentApMac",
                detail="No measured association read path is wired yet.",
            )
        return WirelessAssociationReading(
            **base,
            attempted=False,
            detail=(
                "Association state observation is "
                f"{state_capability.value} on {self._audit.identity}; the "
                "documented surface is left to a bounded probe."
            ),
        )

    def observe_attachment(
        self,
        intent: WirelessAssociationIntent,
        segment: IntendedNetworkSegment,
    ) -> WirelessAttachmentReading:
        """Read the address through the already qualified getter path."""
        binding = self._bindings.get(intent.endpoint_id)
        if binding is None:
            return WirelessAttachmentReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=False,
                detail="No runtime binding is known for this endpoint.",
            )
        address_capability = self._audit.status(
            WirelessCapability.ENDPOINT_ADDRESS_OBSERVATION, binding.model,
        )
        if address_capability is not WirelessCapabilityStatus.SUPPORTED:
            # Unmeasured is not unobservable. Nothing was asked here, so the
            # state stays at its planned baseline rather than becoming a
            # statement about what the backend cannot do.
            return WirelessAttachmentReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=False,
                interface=binding.interface,
                detail=(
                    "Endpoint address observation is "
                    f"{address_capability.value} for {binding.model!r} on "
                    f"{self._audit.identity}."
                ),
            )
        if not binding.interface:
            return WirelessAttachmentReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=False,
                detail="No measured interface name is known for this model.",
            )
        outcome = self._call(
            endpoint_address_read_js(binding.runtime_device_name, binding.interface),
            stage="Port.getIpAddress",
        )
        if not outcome.ok:
            return WirelessAttachmentReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=True,
                interface=binding.interface,
                error_kind=outcome.error_kind,
                error_stage=outcome.stage,
                detail=outcome.detail,
            )
        value = outcome.value or {}
        if not value.get("address_channel"):
            return WirelessAttachmentReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=True,
                interface=binding.interface,
                unavailable_reading=(
                    "Network.getDevice" if not value.get("found")
                    else "Device.getPortAt" if not value.get("port_found")
                    else "Port.getIpAddress"
                ),
                detail="The endpoint getter path was not available.",
            )
        return WirelessAttachmentReading(
            endpoint_id=intent.endpoint_id,
            backend=self.backend,
            backend_version=self.backend_version,
            attempted=True,
            interface=str(value.get("interface") or binding.interface),
            ipv4=str(value.get("ipv4") or ""),
            netmask=str(value.get("netmask") or ""),
            method=VerificationMethod.STRUCTURED_API,
            fresh=True,
            detail=f"Read against the intended segment {segment.segment_id}.",
        )

    def _unbound_association(
        self, intent: WirelessAssociationIntent,
    ) -> WirelessAssociationReading:
        return WirelessAssociationReading(
            endpoint_id=intent.endpoint_id,
            backend=self.backend,
            backend_version=self.backend_version,
            attempted=False,
            detail="No runtime binding is known for this endpoint.",
        )

    def _read_wireless_port(
        self, binding: WirelessRuntimeEndpoint,
    ) -> "_RadioReading":
        """Classify one named port, keeping a failure distinct from a False."""
        if self._audit.status(
            WirelessCapability.WIRELESS_PORT_CLASSIFICATION, binding.model,
        ) is not WirelessCapabilityStatus.SUPPORTED:
            return _RadioReading(stage="Port.isWirelessPort")
        if not binding.interface:
            return _RadioReading(stage="Port.getName")
        outcome = self._call(
            _wireless_port_read_js(binding.runtime_device_name, binding.interface),
            stage="Port.isWirelessPort",
        )
        if not outcome.ok:
            return _RadioReading(
                stage=outcome.stage,
                error_kind=outcome.error_kind,
                detail=outcome.detail,
            )
        wireless = (outcome.value or {}).get("wireless")
        return _RadioReading(
            stage=outcome.stage,
            value=wireless if isinstance(wireless, bool) else None,
        )

    def _call(self, script: str, *, stage: str) -> BackendCallOutcome:
        """One backend round trip, with every failure mode kept apart.

        A bare ``except`` here used to turn a broken transport, a script-engine
        error and a truncated payload into the same silent ``None``, and the
        caller then had to guess. Each of these is a probe failure with its own
        remedy, and none of them says anything about the property being read.
        """
        try:
            raw = self._send_and_wait(script, self._timeout)
        except Exception as exc:
            return BackendCallOutcome(
                stage=stage,
                error_kind=BackendErrorKind.TRANSPORT_EXCEPTION,
                detail=f"{type(exc).__name__}: {exc}",
            )
        if raw is None:
            return BackendCallOutcome(
                stage=stage,
                error_kind=BackendErrorKind.TRANSPORT_TIMEOUT,
                detail=f"No answer within {self._timeout}s.",
            )
        if not isinstance(raw, str):
            return BackendCallOutcome(
                stage=stage,
                error_kind=BackendErrorKind.PROTOCOL_ERROR,
                detail=f"The transport returned {type(raw).__name__}, not text.",
            )
        if raw.startswith(("ERROR:", "PT_ERROR:")):
            return BackendCallOutcome(
                stage=stage,
                error_kind=BackendErrorKind.ENGINE_ERROR,
                detail=raw,
            )
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            return BackendCallOutcome(
                stage=stage,
                error_kind=BackendErrorKind.PROTOCOL_ERROR,
                detail=f"Malformed payload: {type(exc).__name__}: {exc}",
            )
        if not isinstance(value, dict):
            return BackendCallOutcome(
                stage=stage,
                error_kind=BackendErrorKind.PROTOCOL_ERROR,
                detail=f"Payload is {type(value).__name__}, not an object.",
            )
        return BackendCallOutcome(stage=stage, value=value)


@dataclass(frozen=True)
class _RadioReading:
    """Radio classification, or the exact reason there is none."""

    stage: str
    value: bool | None = None
    error_kind: BackendErrorKind | None = None
    detail: str = ""


def _wireless_port_read_js(device_name: str, interface: str) -> str:
    """One optional-guarded `isWirelessPort()` read on a named interface.

    Every field is serialized with `json.dumps`: Packet Tracer runs this through
    `new Function()`, so an unescaped device name would be executable code.
    """
    name = json.dumps(device_name)
    wanted = json.dumps(interface)
    return "".join((
        "try{var d=ipc.network().getDevice(", name, ");",
        "var want=", wanted, ";var p=null;",
        "if(d){for(var i=0;i<d.getPortCount();i++){var c=d.getPortAt(i);",
        "if(c&&typeof c.getName==='function'&&String(c.getName())===want){p=c;break;}}}",
        "var able=!!p&&typeof p.isWirelessPort==='function';",
        "reportResult(JSON.stringify({found:!!d,port_found:!!p,interface:want,",
        "classification_channel:able,wireless:able?!!p.isWirelessPort():null}));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))
