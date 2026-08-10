"""Capacidades E6 observadas en los procesos de Server-PT.

La matriz describe canales independientes. En particular, que TftpServer pueda
habilitarse no demuestra que la Extensions API permita publicar un archivo.
"""

from __future__ import annotations

from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.service_plan import (
    ServiceActionType,
    ServiceCapabilityProfile,
    ServiceType,
)
from ...domain.enterprise.models.evidence import CapabilityReadiness, ReadinessStatus


def packet_tracer_service_capabilities(
    packet_tracer_version: str = "9.0.1.0858",
) -> dict[str, ServiceCapabilityProfile]:
    """Devuelve evidencia conservadora para el runtime local medido."""

    source = "PT 9.0.1 local IpcAPI reference and controlled process probes"
    profiles = {
        service_type: ServiceCapabilityProfile(
            service_type=service_type,
            compile_support=CapabilityStatus.SUPPORTED,
            application_support=CapabilityStatus.SUPPORTED,
            direct_readback_support=CapabilityStatus.SUPPORTED,
            behavioral_verification_support=CapabilityStatus.UNKNOWN,
            source=source,
            packet_tracer_version=packet_tracer_version,
        )
        for service_type in ServiceType
    }
    profiles[ServiceType.TFTP].action_application_support = {
        ServiceActionType.ENABLE_TFTP.value: CapabilityStatus.SUPPORTED,
        ServiceActionType.PUBLISH_TFTP_FILE.value: CapabilityStatus.UNKNOWN,
    }
    profiles[ServiceType.DNS].behavioral_verification_support = CapabilityStatus.SUPPORTED
    profiles[ServiceType.HTTP].behavioral_verification_support = CapabilityStatus.SUPPORTED
    profiles[ServiceType.DNS].capability_readiness["behavioral_verification"] = (
        CapabilityReadiness(
            capability="dns_behavioral_verification",
            compile=ReadinessStatus.READY,
            apply=ReadinessStatus.READY,
            verify=ReadinessStatus.READY,
        )
    )
    profiles[ServiceType.HTTP].capability_readiness["behavioral_verification"] = (
        CapabilityReadiness(
            capability="http_behavioral_verification",
            compile=ReadinessStatus.READY,
            apply=ReadinessStatus.READY,
            verify=ReadinessStatus.READY,
        )
    )
    profiles[ServiceType.HTTPS].capability_readiness["behavioral_verification"] = (
        CapabilityReadiness(
            capability="https_behavioral_verification",
            compile=ReadinessStatus.READY,
            apply=ReadinessStatus.PARTIAL,
            verify=ReadinessStatus.UNKNOWN,
            reasons={
                "verify": [
                    "A typed HTTPS URL is compiled, but PT 9.0.1 client behavior has not been live verified."
                ],
            },
        )
    )
    for service_type, reason in (
        (ServiceType.NTP, "Packet Tracer exposes activation but no independent registered synchronization observation."),
        (ServiceType.TFTP, "Packet Tracer exposes service activation but no safe registered publication/retrieval observation."),
    ):
        profiles[service_type].capability_readiness["behavioral_verification"] = (
            CapabilityReadiness(
                capability=f"{service_type.value}_behavioral_verification",
                compile=ReadinessStatus.READY,
                apply=ReadinessStatus.PARTIAL,
                verify=ReadinessStatus.UNOBSERVABLE,
                reasons={"verify": [reason]},
            )
        )
    return {
        f"Server-PT:{service_type.value}": profiles[service_type]
        for service_type in ServiceType
    }
