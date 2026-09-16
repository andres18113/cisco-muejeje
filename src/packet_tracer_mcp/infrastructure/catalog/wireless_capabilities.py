"""Audited wireless capabilities of Packet Tracer, pinned to an exact build.

Three sources feed this module and they are not interchangeable.

* A **measurement** on this exact build makes a capability SUPPORTED. Only a
  measurement can.
* The **vendor reference** shipped with the product makes it DOCUMENTED. The
  reference names a class and a method; it does not say that this build exposes
  it to the script engine, that a given model owns the process, or that the
  call returns anything useful. Its own wording on `Device::getProcess` is
  explicit that "not all names have an interface to interact with".
* Everything else is UNKNOWN.

Nothing here is inferred from a screenshot, from the canvas, or from how close
two icons sit: graphical proximity is not evidence of an association. An API
that nobody has called is UNKNOWN or DOCUMENTED, never UNSUPPORTED.

The reference is the Extensions API help bundled with the Packet Tracer
9.0.1.0858 installation, under `help/default/IpcAPI`. Its own title page reads
"Cisco Packet Tracer Extensions API 8.1.0", so the documentation ships one
version behind the binary it comes with. That gap is exactly why a documented
surface is not a measured one, and it is recorded on every DOCUMENTED record.
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

#: Where a DOCUMENTED record comes from, named once so every record agrees.
EXTENSIONS_API_REFERENCE = (
    "Cisco Packet Tracer Extensions API 8.1.0 reference bundled with the "
    "9.0.1.0858 installation (help/default/IpcAPI)"
)
_DOCUMENTED_NOT_MEASURED = (
    "Documented in the bundled reference, which is labelled 8.1.0 and does not "
    "answer for build 9.0.1.0858, for the models in use, or for what the "
    "script engine exposes. No run has called it."
)


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


def _documented(
    capability: WirelessCapability,
    surface: str,
    *,
    backend_version: str,
    subject: str = "",
    note: str = "",
) -> WirelessCapabilityAssessment:
    return _assessment(
        capability,
        Status.DOCUMENTED,
        backend_version=backend_version,
        subject=subject,
        surface=surface,
        evidence_reference=EXTENSIONS_API_REFERENCE,
        note=(note + " " if note else "") + _DOCUMENTED_NOT_MEASURED,
        resolved_by="vendor reference only; no measurement on this build",
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
                note=(
                    "No module-swap path is registered for any other model, and "
                    "no IoT model has a measured port inventory on this build."
                ),
                resolved_by="absence of a measured surface",
            ),
            _documented(
                WirelessCapability.SERVICE_SET_CONFIGURATION,
                "WirelessCommon.setSsid(string) / getSsid(); "
                "WirelessServerProcess.setAuthenType / setEncryptType / "
                "setSsidBrdCastEnabled, reached via Device.getProcess(\"WirelessServer\")",
                backend_version=version,
                note=(
                    "The maintained note that a custom SSID needs the device "
                    "GUI describes this repository, which drives no such call, "
                    "not the backend."
                ),
            ),
            _documented(
                WirelessCapability.ENDPOINT_SERVICE_SET_SELECTION,
                "WirelessClientProcess.setCurrentProfile(...) / addProfile(...) / "
                "getCurrentProfile(), reached via Device.getProcess(\"WirelessClient\")",
                backend_version=version,
                note=(
                    "A profile carries the service set, the authentication type "
                    "and the addressing mode together."
                ),
            ),
            _documented(
                WirelessCapability.ASSOCIATION_STATE_OBSERVATION,
                "WirelessClientProcess.getCurrentApMac() / getSsid() / "
                "getCurrentProfile(); WirelessCommon.getPort()",
                backend_version=version,
                note=(
                    "The governed CP qualification policy records wireless "
                    "association as unqualified. That is the absence of a "
                    "measurement, and it neither confirms nor refutes these "
                    "surfaces."
                ),
            ),
            _documented(
                WirelessCapability.ASSOCIATED_ACCESS_POINT_IDENTIFICATION,
                "WirelessClientProcess.getCurrentApMac(); "
                "Antenna.getReceiverCount() / getReceiverAt(int) -> Antenna, "
                "each with getPort() and Port.getOwnerDevice()",
                backend_version=version,
                note=(
                    "An Antenna enumerates its receivers, so a pairing is "
                    "reachable in the reference by identity rather than by "
                    "position. Whether this build populates it is unmeasured."
                ),
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
                surface="Device.getPortAt(int).getName(), Port.isWirelessPort()",
                evidence_reference=(
                    "infrastructure/catalog/measured_port_inventories.py"
                ),
                note=(
                    "The measured inventory is exactly ['Port 0', 'Port 1']. "
                    "Which of the two is a radio was never read back, and the "
                    "catalogue declares only Port 0."
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
                    "A configuration read-back only. It says whether the port "
                    "asks for a lease, never that it holds one, and a disabled "
                    "flag is not a static assignment."
                ),
                resolved_by="registered production read path",
            ),
            _documented(
                WirelessCapability.NETWORK_ATTACHMENT_OBSERVATION,
                "WirelessClientProcess.getCurrentProfile() -> WirelessProfile"
                ".isDhcpEnabled / .ipAddress / .subnetMask / .defaultGateway",
                backend_version=version,
                note=(
                    "The profile is the client view of its addressing. It is "
                    "not a lease table, so even once measured it may describe "
                    "what was requested rather than what was granted."
                ),
            ),
            _assessment(
                WirelessCapability.IOT_FUNCTION_OBSERVATION,
                Status.UNKNOWN,
                backend_version=version,
                note=(
                    "Out of scope for this phase by design. Smoke, motion and "
                    "video behaviour is neither attempted nor inferred from any "
                    "association or addressing evidence."
                ),
                resolved_by="deliberately not attempted",
            ),
        ),
    )
