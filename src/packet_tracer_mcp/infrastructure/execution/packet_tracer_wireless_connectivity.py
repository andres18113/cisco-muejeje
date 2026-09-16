"""Packet Tracer side of the wireless connectivity port.

The adapter is deliberately narrow. It drives exactly the surfaces the audit in
`catalog/wireless_capabilities.py` classifies as SUPPORTED and refuses to
invent the rest: a capability that is UNKNOWN or UNOBSERVABLE produces a
reading that says where it stopped, never a verdict.

Reuse over invention: addressing goes through `endpoint_address_read_js`, the
named-interface getter path already qualified for endpoint evidence, instead of
a second script that would have to be qualified all over again.

None of this has been exercised against a running Packet Tracer. It is the seam
a first bounded live probe plugs into, and every method is written so that an
absent answer stays absent.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ...domain.enterprise.models.evidence import VerificationMethod
from ...domain.enterprise.models.wireless_connectivity import (
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
        """Never reports APPLIED for something this backend cannot configure.

        A plan that stays on the backend default service set has nothing to
        apply, which is NOT_ATTEMPTED and not a quiet success. A plan that names
        its own service set is REFUSED, because the audit records the setting as
        unreachable from the script engine.
        """
        binding = self._bindings.get(intent.endpoint_id)
        subject = binding.model if binding else ""
        service_set_capability = self._audit.status(
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
        if service_set_capability is not WirelessCapabilityStatus.SUPPORTED:
            return WirelessConfigurationOutcome(
                endpoint_id=intent.endpoint_id,
                status=WirelessConfigurationStatus.REFUSED,
                detail=(
                    "Service set configuration is "
                    f"{service_set_capability.value} on {self.backend} "
                    f"{self.backend_version}."
                ),
            )
        return WirelessConfigurationOutcome(
            endpoint_id=intent.endpoint_id,
            status=WirelessConfigurationStatus.NOT_ATTEMPTED,
            detail="No configuration primitive is registered for this intent.",
        )

    def observe_association(
        self, intent: WirelessAssociationIntent,
    ) -> WirelessAssociationReading:
        """Report the radio classification only, and never a pairing.

        The association state itself has no registered reading on this build, so
        the reading stops at the member that would have answered it. The access
        point is left empty on purpose: the link surface names one radio owner,
        and reading a pairing out of it would be an inference.
        """
        binding = self._bindings.get(intent.endpoint_id)
        if binding is None:
            return WirelessAssociationReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=False,
                unavailable_reading="Network.getDevice",
                detail="No runtime binding is known for this endpoint.",
            )
        subject = binding.model
        state_capability = self._audit.status(
            WirelessCapability.ASSOCIATION_STATE_OBSERVATION, subject,
        )
        radio_present = self._read_wireless_port(binding)
        if state_capability is not WirelessCapabilityStatus.SUPPORTED:
            return WirelessAssociationReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=False,
                radio_present=radio_present,
                method=VerificationMethod.NONE,
                fresh=False,
                unavailable_reading="Port.isAssociated",
                detail=(
                    "Association state observation is "
                    f"{state_capability.value} on {self.backend} "
                    f"{self.backend_version}."
                ),
            )
        return WirelessAssociationReading(
            endpoint_id=intent.endpoint_id,
            backend=self.backend,
            backend_version=self.backend_version,
            attempted=False,
            radio_present=radio_present,
            unavailable_reading="Port.isAssociated",
            detail="No association primitive is registered for this build.",
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
                unavailable_reading="Network.getDevice",
                detail="No runtime binding is known for this endpoint.",
            )
        address_capability = self._audit.status(
            WirelessCapability.ENDPOINT_ADDRESS_OBSERVATION, binding.model,
        )
        if address_capability is not WirelessCapabilityStatus.SUPPORTED:
            return WirelessAttachmentReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=False,
                interface=binding.interface,
                unavailable_reading="Port.getIpAddress",
                detail=(
                    "Endpoint address observation is "
                    f"{address_capability.value} for {binding.model!r} on "
                    f"{self.backend} {self.backend_version}."
                ),
            )
        if not binding.interface:
            return WirelessAttachmentReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=False,
                unavailable_reading="Port.getName",
                detail="No measured interface name is known for this model.",
            )
        value = self._call(
            endpoint_address_read_js(binding.runtime_device_name, binding.interface),
        )
        if value is None:
            return WirelessAttachmentReading(
                endpoint_id=intent.endpoint_id,
                backend=self.backend,
                backend_version=self.backend_version,
                attempted=True,
                interface=binding.interface,
                unavailable_reading="Port.getIpAddress",
                detail="The endpoint getter path did not return a reading.",
            )
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

    def _read_wireless_port(self, binding: WirelessRuntimeEndpoint) -> bool | None:
        """`None` whenever the classification did not come back as a boolean."""
        if self._audit.status(
            WirelessCapability.WIRELESS_PORT_CLASSIFICATION, binding.model,
        ) is not WirelessCapabilityStatus.SUPPORTED:
            return None
        if not binding.interface:
            return None
        value = self._call(
            _wireless_port_read_js(binding.runtime_device_name, binding.interface),
        )
        if value is None:
            return None
        wireless = value.get("wireless")
        return wireless if isinstance(wireless, bool) else None

    def _call(self, script: str) -> dict | None:
        try:
            raw = self._send_and_wait(script, self._timeout)
        except Exception:
            return None
        if not isinstance(raw, str) or raw.startswith(("ERROR:", "PT_ERROR:")):
            return None
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return value if isinstance(value, dict) else None


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
