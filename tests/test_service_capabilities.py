"""Catálogo E6 medido para Packet Tracer 9.0.1.0858."""

from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceActionType,
    ServiceCapabilityProfile,
    ServiceType,
)
from packet_tracer_mcp.infrastructure.catalog import (
    packet_tracer_service_capabilities,
)
from packet_tracer_mcp.domain.enterprise.models.evidence import ReadinessStatus


def test_packet_tracer_service_matrix_keeps_four_capability_dimensions():
    """Every server family is still a four-dimension profile of one build.

    S1 added client operation records to the SAME mapping, because a client
    expectation must resolve its own model rather than the server's profile.
    The assertion therefore names the server profiles instead of claiming the
    mapping holds nothing else; what it protects is unchanged.
    """
    records = packet_tracer_service_capabilities("9.0.1.0858")

    profiles = {
        key: record
        for key, record in records.items()
        if isinstance(record, ServiceCapabilityProfile)
    }
    assert set(profiles) == {f"Server-PT:{service.value}" for service in ServiceType}
    for profile in profiles.values():
        assert profile.compile_support is CapabilityStatus.SUPPORTED
        assert profile.packet_tracer_version == "9.0.1.0858"
        assert profile.source
    assert set(records) > set(profiles)


def test_tftp_file_publication_is_not_inferred_from_tftp_enable_support():
    profile = packet_tracer_service_capabilities("9.0.1.0858")["Server-PT:tftp"]

    assert profile.application_support is CapabilityStatus.SUPPORTED
    assert (
        profile.action_application_support[ServiceActionType.ENABLE_TFTP.value]
        is CapabilityStatus.SUPPORTED
    )
    assert (
        profile.action_application_support[ServiceActionType.PUBLISH_TFTP_FILE.value]
        is CapabilityStatus.UNKNOWN
    )


def test_only_live_behaviorally_proven_services_are_promoted():
    profiles = packet_tracer_service_capabilities("9.0.1.0858")

    assert (
        profiles["Server-PT:dns"].behavioral_verification_support
        is CapabilityStatus.SUPPORTED
    )
    assert (
        profiles["Server-PT:http"].behavioral_verification_support
        is CapabilityStatus.SUPPORTED
    )
    for service_type in (ServiceType.HTTPS, ServiceType.NTP, ServiceType.TFTP):
        assert (
            profiles[f"Server-PT:{service_type.value}"].behavioral_verification_support
            is CapabilityStatus.UNKNOWN
        )
    assert (
        profiles["Server-PT:https"].capability_readiness["behavioral_verification"].verify
        is ReadinessStatus.UNKNOWN
    )
    for service_type in (ServiceType.NTP, ServiceType.TFTP):
        assert (
            profiles[f"Server-PT:{service_type.value}"]
            .capability_readiness["behavioral_verification"].verify
            is ReadinessStatus.UNOBSERVABLE
        )
