"""Settle selected DHCP identity readings before any cold application request."""

from __future__ import annotations

from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.verification import (
    order_verification_expectations,
)
from packet_tracer_mcp.domain.enterprise.services.service_request_order import (
    request_phases,
)


def _expectation(identifier, kind):
    return ServiceVerificationExpectation(
        id=identifier,
        service_id="service/group",
        action_id="action/group",
        kind=kind,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="server",
        host_device_name="S",
        client_device_id=identifier,
        client_device_name=identifier,
    )


def test_all_lease_readings_settle_before_the_first_cold_http_by_ip():
    """A peer's later lease cannot force another router scan per client."""
    expectations = [
        _expectation("a-http", ServiceVerificationKind.HTTP_FETCH),
        _expectation("z-lease-1", ServiceVerificationKind.DHCP_LEASE),
        _expectation("z-lease-2", ServiceVerificationKind.DHCP_LEASE),
    ]
    phases = request_phases(expectations)
    ordered = order_verification_expectations(
        expectations, rank=lambda item: phases[item.id]
    )
    assert [item.id for item in ordered] == [
        "z-lease-1",
        "z-lease-2",
        "a-http",
    ]
