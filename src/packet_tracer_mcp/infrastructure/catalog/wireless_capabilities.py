"""Audited wireless capabilities of Packet Tracer, pinned to an exact build.

Every record below names the surface it was read from, inside this repository
or inside the maintained documentation. Nothing here was inferred from a
screenshot, from the canvas, or from how close two icons sit: graphical
proximity is not evidence of an association, and an API that nobody has called
is UNKNOWN, not UNSUPPORTED.

The four classes are not interchangeable:

* SUPPORTED    a named surface exists and this repository already drives it.
* UNSUPPORTED  the backend does not offer it at all through this channel.
* UNOBSERVABLE the state exists but no registered reading exposes it.
* UNKNOWN      never measured on this build. The default for anything absent.

An absent (capability, subject) pair therefore resolves UNKNOWN, and a model
this module does not name inherits the backend-wide record when there is one.
"""

from __future__ import annotations

from ...domain.enterprise.models.discovery import CapabilityBackend
from ...domain.enterprise.models.wireless_connectivity import (
    WirelessCapability,
    WirelessCapabilityAssessment,
    WirelessCapabilityAudit,
    WirelessCapabilityStatus as Status,
)
from .measured_port_inventories import MEASURED_BACKEND_VERSION


_BACKEND = CapabilityBackend.PACKET_TRACER.value
_DECLARED_BUILDS = frozenset({MEASURED_BACKEND_VERSION})


def _assessment(
    capability: WirelessCapability,
    status: Status,
    *,
    backend_version: str,
    subject: str = "",
    surface: str = "",
    evidence_reference: str = "",
    note: str = "",
    resolved_by: str = "",
) -> WirelessCapabilityAssessment:
    return WirelessCapabilityAssessment(
        capability=capability,
        status=status,
        backend=_BACKEND,
        backend_version=backend_version,
        subject=subject,
        surface=surface,
        evidence_reference=evidence_reference,
        note=note,
        resolved_by=resolved_by,
    )


def packet_tracer_wireless_capability_audit(
    packet_tracer_version: str,
) -> WirelessCapabilityAudit:
    """Return the declared wireless audit for one exact Packet Tracer build.

    A build without a declaration has no audit. Returning an empty one would
    read as "everything UNKNOWN" and silently admit work on an unmeasured
    backend, so this refuses instead.
    """
    if packet_tracer_version not in _DECLARED_BUILDS:
        raise ValueError(
            "No wireless capability audit is declared for Packet Tracer "
            f"{packet_tracer_version!r}."
        )
    version = packet_tracer_version
    return WirelessCapabilityAudit(
        backend=_BACKEND,
        backend_version=version,
        assessments=(
            _assessment(
                WirelessCapability.RADIO_ENABLEMENT,
                Status.SUPPORTED,
                backend_version=version,
                subject="Laptop-PT",
                surface="Device.addModule(slot, PT-LAPTOP-NM-1W)",
                evidence_reference=(
                    "EXTENSION/script-engine/main.js swapLaptopToWireless; "
                    "infrastructure/generator/ptbuilder_generator.py"
                ),
                note=(
                    "Replacing the wired NIC yields a Wireless0 port that the "
                    "production generator then addresses."
                ),
                resolved_by="production generator path exercised offline",
            ),
            _assessment(
                WirelessCapability.RADIO_ENABLEMENT,
                Status.UNKNOWN,
                backend_version=version,
                surface="",
                note=(
                    "No module-swap path is registered for any other model, and "
                    "no IoT model has a measured port inventory on this build."
                ),
                resolved_by="absence of a measured surface",
            ),
            _assessment(
                WirelessCapability.SERVICE_SET_CONFIGURATION,
                Status.UNSUPPORTED,
                backend_version=version,
                surface="none (access point GUI only)",
                evidence_reference="docs/advanced-features.md",
                note=(
                    "SSID and WPA2 settings of an access point are not exposed "
                    "through the Script Engine; they are set in the device GUI. "
                    "Plans therefore run on the backend default service set."
                ),
                resolved_by="maintained documentation of the backend limit",
            ),
            _assessment(
                WirelessCapability.ENDPOINT_SERVICE_SET_SELECTION,
                Status.UNKNOWN,
                backend_version=version,
                surface="",
                note=(
                    "The only described client path is radio auto-association "
                    "to the default service set. No primitive that selects a "
                    "service set from an endpoint has been confirmed."
                ),
                resolved_by="absence of a confirmed primitive",
            ),
            _assessment(
                WirelessCapability.ASSOCIATION_STATE_OBSERVATION,
                Status.UNKNOWN,
                backend_version=version,
                surface="",
                evidence_reference=(
                    "infrastructure/catalog/cp_scale_qualification_policy.py"
                ),
                note=(
                    "The governed backend policy records wireless association "
                    "as unqualified: no governed run has established that an "
                    "association, or the lease that depends on it, is readable "
                    "on this build. Unmeasured, not refuted."
                ),
                resolved_by="governed qualification policy",
            ),
            _assessment(
                WirelessCapability.ASSOCIATED_ACCESS_POINT_IDENTIFICATION,
                Status.UNOBSERVABLE,
                backend_version=version,
                surface="Link.getClassName() == 'Antenna', Link.getPort()",
                evidence_reference="adapters/mcp/tool_registry.py topology export",
                note=(
                    "A wireless link is enumerated through a single getPort(), "
                    "which names one radio owner. No registered reading returns "
                    "both ends, so endpoint-to-access-point pairing cannot be "
                    "read from the link surface."
                ),
                resolved_by="shape of the registered link surface",
            ),
            _assessment(
                WirelessCapability.WIRELESS_PORT_CLASSIFICATION,
                Status.SUPPORTED,
                backend_version=version,
                surface="Port.isWirelessPort()",
                evidence_reference="adapters/mcp/tool_registry.py port inventory",
                note=(
                    "A typed per-port getter, already read through the "
                    "optional-guarded inventory path."
                ),
                resolved_by="registered production read path",
            ),
            _assessment(
                WirelessCapability.ACCESS_POINT_RADIO_PORT_IDENTITY,
                Status.UNKNOWN,
                backend_version=version,
                subject="AccessPoint-PT",
                surface="Device.getPortAt(i).getName()",
                evidence_reference=(
                    "infrastructure/catalog/measured_port_inventories.py"
                ),
                note=(
                    "The measured inventory is exactly ['Port 0', 'Port 1']. "
                    "Which of the two is a radio was never read back with "
                    "isWirelessPort(), and the catalogue declares only Port 0."
                ),
                resolved_by="measured inventory without a radio classification",
            ),
            _assessment(
                WirelessCapability.ENDPOINT_ADDRESS_OBSERVATION,
                Status.SUPPORTED,
                backend_version=version,
                subject="Laptop-PT",
                surface="Port.getIpAddress(), Port.getSubnetMask()",
                evidence_reference=(
                    "infrastructure/execution/endpoint_address_observer.py"
                ),
                note=(
                    "The qualified named-interface getter path. It needs the "
                    "exact interface name, which Laptop-PT has as Wireless0."
                ),
                resolved_by="qualified endpoint getter path",
            ),
            _assessment(
                WirelessCapability.ENDPOINT_ADDRESS_OBSERVATION,
                Status.UNKNOWN,
                backend_version=version,
                surface="Port.getIpAddress(), Port.getSubnetMask()",
                note=(
                    "The getter path is generic, but it resolves a port by name "
                    "and no IoT model has a measured port inventory on this "
                    "build, so no interface name can be supplied."
                ),
                resolved_by="absence of a measured interface name",
            ),
            _assessment(
                WirelessCapability.DHCP_CLIENT_FLAG_OBSERVATION,
                Status.SUPPORTED,
                backend_version=version,
                surface="Port.isDhcpClientOn()",
                evidence_reference="adapters/mcp/tool_registry.py port inventory",
                note=(
                    "A configuration read-back only. It says the port asks for "
                    "a lease, never that it holds one."
                ),
                resolved_by="registered production read path",
            ),
            _assessment(
                WirelessCapability.NETWORK_ATTACHMENT_OBSERVATION,
                Status.UNKNOWN,
                backend_version=version,
                surface="",
                note=(
                    "No registered primitive returns lease state. An address on "
                    "a DHCP-flagged port is indirect evidence and has never "
                    "been qualified for a wireless endpoint on this build."
                ),
                resolved_by="absence of a lease surface",
            ),
            _assessment(
                WirelessCapability.IOT_FUNCTION_OBSERVATION,
                Status.UNKNOWN,
                backend_version=version,
                surface="",
                note=(
                    "Out of scope for this phase by design. Smoke, motion and "
                    "video behaviour is neither attempted nor inferred from any "
                    "association or addressing evidence."
                ),
                resolved_by="deliberately not attempted",
            ),
        ),
    )
