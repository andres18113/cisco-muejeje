"""Governed Packet Tracer capability observations pinned to an exact build.

This is the capability counterpart of :mod:`measured_port_inventories`.  The
generic device catalogue remains backend-agnostic, while mutable discovery
snapshots remain under ``data/capabilities`` for new observations.  Facts that
an exposed product plan already relies on need a third, deliberately curated
surface: a small Git-tracked projection of the governed observations.

Every record below names the stable hash of the source snapshot, the producer
and its verification method.  Projecting a record uses ``STATIC_OVERRIDE`` so
fresh runtime/probe evidence retains its higher resolver priority.  Records are
exact-build only; an absent model, capability, or build is still UNKNOWN.

The observations were produced before this module existed.  Several canonical
snapshot hashes are also retained in ``docs/reference/cp-scale``; the earlier
MEG-4/MEG-5 qualifications are described in
``docs/architecture/technical-debt.md`` and
``docs/architecture/ripv2-runtime-qualification.md``.  This module records
their conclusions without broadening their claim ceilings.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.enterprise.models.capabilities import (
    CapabilityEvidence,
    CapabilityStatus,
    EvidenceSource,
)
from .measured_port_inventories import MEASURED_BACKEND_VERSION


@dataclass(frozen=True)
class MeasuredCapabilityRecord:
    """One reviewed projection of a reusable governed snapshot result."""

    model: str
    capability: str
    status: CapabilityStatus
    snapshot_hash: str
    producer: str
    original_source: EvidenceSource
    verification_method: str
    summary: str
    observed_value: int | None = None

    def as_evidence(self) -> CapabilityEvidence:
        """Return resolver evidence without pretending the snapshot is live."""
        return CapabilityEvidence(
            capability=self.capability,
            status=self.status,
            source=EvidenceSource.STATIC_OVERRIDE,
            source_detail=(
                f"governed {self.original_source.value}/{self.producer}; "
                f"snapshot={self.snapshot_hash}; method={self.verification_method}"
            ),
            packet_tracer_version=MEASURED_BACKEND_VERSION,
            confidence="live_qualified",
            verified=True,
            observed_value=self.observed_value,
            notes=self.summary,
        )


def _supported(
    model: str,
    capability: str,
    snapshot_hash: str,
    producer: str,
    verification_method: str,
    summary: str,
    *,
    original_source: EvidenceSource = EvidenceSource.CONTROLLED_PROBE,
    observed_value: int | None = None,
) -> MeasuredCapabilityRecord:
    return MeasuredCapabilityRecord(
        model=model,
        capability=capability,
        status=CapabilityStatus.SUPPORTED,
        snapshot_hash=snapshot_hash,
        producer=producer,
        original_source=original_source,
        verification_method=verification_method,
        summary=summary,
        observed_value=observed_value,
    )


def _unknown(
    model: str,
    capability: str,
    snapshot_hash: str,
    producer: str,
    verification_method: str,
    summary: str,
    *,
    original_source: EvidenceSource,
) -> MeasuredCapabilityRecord:
    """Retain an exact observation without widening it into authorization."""

    return MeasuredCapabilityRecord(
        model=model,
        capability=capability,
        status=CapabilityStatus.UNKNOWN,
        snapshot_hash=snapshot_hash,
        producer=producer,
        original_source=original_source,
        verification_method=verification_method,
        summary=summary,
    )


_LAYER2 = "VlanManager was present on the freshly created exact-model device."
_VLAN = (
    "VLAN 999 was configured through the typed IOS channel, read back through "
    "VlanManager, and removed successfully."
)
_TRUNK = (
    "Trunk administrative mode was configured through the typed IOS channel, "
    "read back from the typed SwitchPort object, and restored to access mode."
)
_LAYER3 = (
    "An IPv4 interface was configured through the typed IOS channel, read back "
    "through a registered IOS query, and cleared successfully."
)
_POE_CONTROL_ONLY = (
    "24 fresh access ports exposed complete administrative/runtime power-on "
    "state; powered-device delivery was not observed, so delivery capability "
    "and capacity remain unknown."
)

_IE_2000 = "a90573080383dec861b75c72875d2db1d8c75ed5008eaa6e6f866354e765423a"
_PT_2911 = "1a6af1dd1aa28b7c3a34e20c3b91e152a50cbf2b4ee31bbae19d7f5fb806e2fc"
_PT_2950T = "fa5506899b5fb6b4f519656d65f712f0f6e71855274b5c35878f3931c05e8238"
_PT_1941 = "12c2c6bec52123b6df3a3d2f8f5233f92f760e4414f9a7b221c745894f35fc75"
_PT_2811 = "3d77ebfc5645156bd0acc3d35a45fcc086d894e35a92f3f1e205925b65d684d3"
_PT_2960_LOGICAL = "018f99a6815d4b647e39aab0890b7103c855a692c6c1055eb69bc21c147aa11a"
_PT_2960_POE = "aa178f7f2484b7094d7051dc5820b828371059122a77251ed326d224f636102c"
_PT_3560_LOGICAL = "1579ab1ca80ebcfe623534a3fdbf1e9bfb4298bfaa594ac62c21931cee0b32c0"
_PT_3560_LAYER3 = "273d226532753d68480069c9b61b16ef91c6eea6f5b9ab7d264bb7e5519512a6"
_PT_3560_POE = "ae52cee8f8e23d032141aaa025c6ea466aa82b90bc5cc156660f67f625b9156e"
_PT_3650_LOGICAL = "4153e5f90b641336a9745666cc92bd459debdb01f5ab21ebb7fc041c9d337db8"
_PT_3650_POE = "e446646eb7c836beb0346b1b87236e0605dec185c67ea36aaa005d064315de94"


MEASURED_CAPABILITY_RECORDS: tuple[MeasuredCapabilityRecord, ...] = (
    _supported("IE-2000", "layer2", _IE_2000, "layer2-probe", "object_state", _LAYER2),
    _supported(
        "IE-2000", "supports_vlan", _IE_2000, "vlan-probe",
        "cli_plus_readback", _VLAN, observed_value=999,
    ),
    _supported("2911", "layer3", _PT_2911, "layer3-probe", "cli_plus_readback", _LAYER3),
    _supported("2950T-24", "layer2", _PT_2950T, "layer2-probe", "object_state", _LAYER2),
    _supported(
        "2950T-24", "supports_vlan", _PT_2950T, "vlan-probe",
        "cli_plus_readback", _VLAN, observed_value=999,
    ),
    _supported("1941", "layer3", _PT_1941, "layer3-probe", "cli_plus_readback", _LAYER3),
    _supported("2811", "layer3", _PT_2811, "layer3-probe", "cli_plus_readback", _LAYER3),
    _supported(
        "2811", "supports_cme", _PT_2811, "cme-call-control",
        "cli_plus_readback",
        "A controlled telephony-service instance was accepted and its ephone-1 "
        "row read back as UNREGISTERED; registration read-back exists.",
    ),
    _supported(
        "2811", "supports_dhcp_server", _PT_2811, "dhcp-server-behavior",
        "simulation_trace",
        "A disposable client obtained fresh IPv4/mask state from the controlled "
        "DHCP pool and was removed successfully.",
    ),
    _supported(
        "2960-24TT", "layer2", _PT_2960_LOGICAL, "layer2-probe",
        "object_state", _LAYER2,
    ),
    _supported(
        "2960-24TT", "supports_vlan", _PT_2960_LOGICAL, "vlan-probe",
        "cli_plus_readback", _VLAN, observed_value=999,
    ),
    _supported(
        "2960-24TT", "supports_trunk", _PT_2960_LOGICAL, "trunk-probe",
        "cli_plus_readback", _TRUNK,
    ),
    _unknown(
        "2960-24TT", "supports_poe", _PT_2960_POE, "supports-poe",
        "object_state",
        (
            "24 fresh access ports exposed complete administrative/runtime "
            "power-off state; powered-device delivery was not observed, so "
            "delivery capability remains unknown."
        ),
        original_source=EvidenceSource.PACKET_TRACER_RUNTIME,
    ),
    _supported(
        "3560-24PS", "layer2", _PT_3560_LOGICAL, "layer2-probe",
        "object_state", _LAYER2,
    ),
    _supported(
        "3560-24PS", "supports_vlan", _PT_3560_LOGICAL, "vlan-probe",
        "cli_plus_readback", _VLAN, observed_value=999,
    ),
    _supported(
        "3560-24PS", "supports_trunk", _PT_3560_LOGICAL, "trunk-probe",
        "cli_plus_readback", _TRUNK,
    ),
    _supported(
        "3560-24PS", "multilayer_intervlan", _PT_3560_LAYER3,
        "multilayer-intervlan-probe", "simulation_trace",
        "Both endpoint-to-SVI paths and inter-VLAN forwarding converged; SVI "
        "configuration, addresses, and up/up state were read back.",
    ),
    _unknown(
        "3560-24PS", "supports_poe", _PT_3560_POE, "supports-poe",
        "object_state", _POE_CONTROL_ONLY,
        original_source=EvidenceSource.PACKET_TRACER_RUNTIME,
    ),
    _supported(
        "3650-24PS", "layer2", _PT_3650_LOGICAL, "layer2-probe",
        "object_state", _LAYER2,
    ),
    _supported(
        "3650-24PS", "supports_vlan", _PT_3650_LOGICAL, "vlan-probe",
        "cli_plus_readback", _VLAN, observed_value=999,
    ),
    _supported(
        "3650-24PS", "supports_trunk", _PT_3650_LOGICAL, "trunk-probe",
        "cli_plus_readback", _TRUNK,
    ),
    _unknown(
        "3650-24PS", "supports_poe", _PT_3650_POE, "supports-poe",
        "object_state", _POE_CONTROL_ONLY,
        original_source=EvidenceSource.PACKET_TRACER_RUNTIME,
    ),
)


def measured_capability_evidence() -> dict[str, list[CapabilityEvidence]]:
    """Build a fresh provider map from the immutable reviewed records."""
    by_model: dict[str, list[CapabilityEvidence]] = {}
    for record in MEASURED_CAPABILITY_RECORDS:
        by_model.setdefault(record.model, []).append(record.as_evidence())
    return by_model
