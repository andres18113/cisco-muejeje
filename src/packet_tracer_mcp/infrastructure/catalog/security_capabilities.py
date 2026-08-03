"""Baseline E8 medido para Packet Tracer 9.0.1.0858."""

from __future__ import annotations

from ...domain.enterprise.models.security_plan import (
    SecurityCapabilityDimension as Dimension,
    SecurityCapabilityProfile,
    SecurityCapabilityStatus as Status,
)


def packet_tracer_security_capabilities(
    packet_tracer_version: str = "9.0.1.0858",
) -> dict[str, SecurityCapabilityProfile]:
    """Return only evidence measured by controlled E8 probes.

    Missing dimensions deliberately resolve to UNKNOWN through the domain
    profile. Generator availability alone is not runtime evidence.
    """
    source = "E8 controlled Packet Tracer runtime probes and fresh IOS read-back"
    return {
        "2911": SecurityCapabilityProfile(
            model="2911",
            packet_tracer_version=packet_tracer_version,
            evidence_source=source,
            dimensions={
                Dimension.ACL_CONFIG: Status.SUPPORTED,
                Dimension.ACL_READBACK: Status.SUPPORTED,
                Dimension.ACL_BEHAVIORAL: Status.SUPPORTED,
                Dimension.NAT_CONFIG: Status.SUPPORTED,
                Dimension.NAT_PAT_CONFIG: Status.SUPPORTED,
                Dimension.NAT_TRANSLATION_READBACK: Status.SUPPORTED,
                Dimension.NAT_BEHAVIORAL: Status.SUPPORTED,
                Dimension.HARDENING_CONFIG: Status.SUPPORTED,
                Dimension.HARDENING_READBACK: Status.SUPPORTED,
            },
        ),
        "2960-24TT": SecurityCapabilityProfile(
            model="2960-24TT",
            packet_tracer_version=packet_tracer_version,
            evidence_source=source,
            dimensions={
                Dimension.PORT_SECURITY_CONFIG: Status.SUPPORTED,
                Dimension.PORT_SECURITY_READBACK: Status.PARTIAL,
                Dimension.PORT_SECURITY_BEHAVIORAL: Status.UNKNOWN,
                Dimension.DHCP_SNOOPING_CONFIG: Status.SUPPORTED,
                Dimension.DHCP_SNOOPING_READBACK: Status.SUPPORTED,
                Dimension.DHCP_SNOOPING_BEHAVIORAL: Status.UNKNOWN,
                Dimension.DAI_CONFIG: Status.SUPPORTED,
                Dimension.DAI_READBACK: Status.PARTIAL,
                Dimension.DAI_BEHAVIORAL: Status.UNKNOWN,
            },
        ),
        "2811": SecurityCapabilityProfile(
            model="2811",
            packet_tracer_version=packet_tracer_version,
            evidence_source="No controlled E8 security probe yet",
        ),
        "3560-24PS": SecurityCapabilityProfile(
            model="3560-24PS",
            packet_tracer_version=packet_tracer_version,
            evidence_source="No controlled E8 security probe yet",
        ),
    }
