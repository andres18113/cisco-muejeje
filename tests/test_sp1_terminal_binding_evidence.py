"""Static terminal observations require valid fields and attributed answers."""

import pytest

from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    _sp1_terminal_bindings_observed,
)


def _binding():
    return {
        "device": "PC1",
        "found": True,
        "port_found": True,
        "error": "",
        "ipv4": "192.0.2.10",
        "netmask": "255.255.255.0",
        "dns_api": True,
        "dns_error": "",
        "dns_server": "192.0.2.2",
        "gateway_reads": [
            {
                "process": "HostIp",
                "found": False,
                "api": False,
                "error": "invalid string position",
                "value": "",
            },
            {
                "process": "HostIpProcess",
                "found": True,
                "api": True,
                "error": "",
                "value": "192.0.2.1",
            },
        ],
    }


def test_static_terminal_preserves_independent_getter_failure():
    """A clean gateway alias suffices without a DHCP-mode or lease field."""
    assert _sp1_terminal_bindings_observed([_binding()], ["PC1"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("found", False),
        ("port_found", False),
        ("error", "unreadable"),
        ("ipv4", ""),
        ("ipv4", "0.0.0.0"),
        ("ipv4", "bad"),
        ("netmask", "bad"),
        ("netmask", "255.0.255.0"),
        ("netmask", "0.0.0.255"),
        ("netmask", "0.0.0.7"),
        ("dns_api", False),
        ("dns_error", "unreadable"),
        ("dns_server", "0.0.0.0"),
        ("device", []),
        ("device", "foreign"),
        ("gateway_reads", None),
    ],
)
def test_invalid_static_terminal_field_is_not_an_observation(key, value):
    """Malformed or missing fields never count as a successful returned row."""
    row = _binding()
    row[key] = value
    assert not _sp1_terminal_bindings_observed([row], ["PC1"])


def test_conflicting_successful_gateway_answers_remain_unobserved():
    """An observed disagreement cannot be hidden by choosing one process."""
    row = _binding()
    row["gateway_reads"][0].update(found=True, api=True, error="", value="192.0.2.9")
    assert not _sp1_terminal_bindings_observed([row], ["PC1"])
