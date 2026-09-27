"""SP-2 address policy keeps native pool windows contiguous and conflict free."""

from __future__ import annotations

from ipaddress import ip_network

from packet_tracer_mcp.domain.enterprise.models.configuration import AddressRange
from packet_tracer_mcp.domain.enterprise.services.service_compiler import (
    ServiceCompiler,
)


def test_pool_window_moves_past_an_exclusion_instead_of_spanning_it():
    """A native start/end interval must never allocate an excluded address."""
    window = ServiceCompiler._lease_window(
        ip_network("198.19.7.0/26"),
        [AddressRange(start="198.19.7.10", end="198.19.7.10")],
        start_offset=0,
        max_users=36,
    )
    assert window == ("198.19.7.11", "198.19.7.46")


def test_pool_window_refuses_when_no_contiguous_capacity_remains():
    """Disjoint small holes do not add up to a usable native pool."""
    window = ServiceCompiler._lease_window(
        ip_network("198.19.8.0/28"),
        [AddressRange(start="198.19.8.7", end="198.19.8.8")],
        start_offset=0,
        max_users=7,
    )
    assert window is None
