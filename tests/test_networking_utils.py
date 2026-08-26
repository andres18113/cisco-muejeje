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
    """El ping no debe deserializar una string y volverla un literal JS crudo.

    El despacho dejó de vivir en el tool: pasa por TypedPingExecutor, que es la
    frontera que además verifica el eco y se niega a tipear sobre un pager
    activo. La propiedad que este test cuida se mudó con él, así que se verifica
    donde ahora ocurre en vez de darla por perdida.
    """
    registry = Path("src/packet_tracer_mcp/adapters/mcp/tool_registry.py").read_text(
        encoding="utf-8"
    )
    executor = Path(
        "src/packet_tracer_mcp/infrastructure/execution/typed_ping.py"
    ).read_text(encoding="utf-8")

    assert "target_ip = normalize_ip(to_ip)" in registry
    # Si vuelve un despacho crudo al tool, vuelve el bypass de la frontera.
    assert "cp.enterCommand(" not in registry
    assert "TypedPingExecutor(" in registry
    assert "target = str(ipaddress.ip_address(destination))" in executor
    assert 'command = "ping " + target' in executor
    assert "json.dumps(command)" in executor
    assert "json.loads(target)" not in registry


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        # `show spanning-tree` abbreviates every interface it prints, and the
        # typed plan never does. Both spellings name one physical port.
        ("Fa0/1", "FastEthernet0/1"),
        ("FastEthernet0/1", "Fa0/1"),
        ("Gi0/1", "GigabitEthernet0/1"),
        ("Te1/1", "TenGigabitEthernet1/1"),
        ("Se0/0/0", "Serial0/0/0"),
        ("fa0/1", "FastEthernet0/1"),
        ("Gi1/0/2", "GigabitEthernet1/0/2"),
    ],
)
def test_same_interface_name_reconciles_both_ios_spellings(observed, expected):
    from src.packet_tracer_mcp.shared.utils import same_interface_name

    assert same_interface_name(observed, expected)


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        ("Fa0/1", "FastEthernet0/2"),
        ("Fa0/1", "GigabitEthernet0/1"),
        ("Gi0/1", "Gi0/10"),
        ("Fa0/1", ""),
        # Deliberate, and a change from the runtime-private predecessor: two
        # ABSENT names are not one interface. A verification that "matched"
        # nothing against nothing was passing on the absence of evidence.
        ("", ""),
    ],
)
def test_same_interface_name_never_conflates_distinct_ports(observed, expected):
    from src.packet_tracer_mcp.shared.utils import same_interface_name

    assert not same_interface_name(observed, expected)


def test_the_configuration_runtime_reuses_the_shared_interface_reconciler():
    """One alias table, not two. A second copy is a second set of bugs."""
    runtime = Path(
        "src/packet_tracer_mcp/infrastructure/execution/"
        "enterprise_configuration_runtime.py"
    ).read_text(encoding="utf-8")

    assert "same_interface_name" in runtime
    assert '("fastethernet", "fa")' not in runtime
