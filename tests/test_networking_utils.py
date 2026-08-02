"""Regresiones de validaciones de red reutilizables."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.packet_tracer_mcp.shared.utils import normalize_ip


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.168.1.1", "192.168.1.1"),
        (" 192.168.1.1 ", "192.168.1.1"),
        ("2001:0db8:0:0:0:0:0:1", "2001:db8::1"),
    ],
)
def test_normalize_ip_accepts_and_canonicalizes_ip_addresses(raw: str, expected: str):
    assert normalize_ip(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "google.com",
        "192.168.1.1'",
        "1.1.1.1\nreload",
        "1.1.1.1'); reportResult('pwned'); //",
    ],
)
def test_normalize_ip_rejects_non_ip_input(raw: str):
    with pytest.raises(ValueError):
        normalize_ip(raw)


def test_connectivity_tool_passes_the_validated_ip_as_json_data():
    """El ping no debe deserializar una string y volverla un literal JS crudo."""
    registry = Path("src/packet_tracer_mcp/adapters/mcp/tool_registry.py").read_text(
        encoding="utf-8"
    )
    assert "target_ip = normalize_ip(to_ip)" in registry
    assert 'ping_command = json.dumps(f"ping {target_ip}")' in registry
    assert "cp.enterCommand({ping_command});" in registry
    assert "json.loads(target)" not in registry
