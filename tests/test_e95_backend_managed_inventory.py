"""La huella de inventario ignora el objeto que Packet Tracer se crea solo.

Reproducido en vivo contra PT 9.0.1.0858 por el file-bridge: tras crear tres
dispositivos temporales y borrarlos todos sin fallo de cleanup, el workspace
pasó de 0 dispositivos a 1 -- un `Power Distribution Device0` que PT materializó
por su cuenta. La huella final no coincidía con la inicial, la sesión quedaba
`NOT_RESTORED` y todos los resultados se degradaban a UNKNOWN, de modo que
ninguna sesión live podía completarse.

El probe no puede borrarlo: sólo posee los objetos `__MCP_PROBE_*`.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    semantic_inventory_fingerprint,
)
from src.packet_tracer_mcp.infrastructure.execution.probe_runtime import (
    PacketTracerBridgeProbeRuntime,
)


def _runtime(payload: str) -> PacketTracerBridgeProbeRuntime:
    return PacketTracerBridgeProbeRuntime(lambda _js, _timeout: payload)


_EMPTY = '{"items":[],"links":[]}'
_ONLY_POWER_DISTRIBUTION = (
    '{"items":[{"kind":"device","name":"Power Distribution Device0",'
    '"model":"Power Distribution Device","ports":[]}],"links":[]}'
)


def test_power_distribution_device_does_not_change_the_fingerprint():
    """El caso live exacto: vacío antes, PDD después, misma huella."""
    before = _runtime(_EMPTY).inventory_fingerprint()
    after = _runtime(_ONLY_POWER_DISTRIBUTION).inventory_fingerprint()

    assert before == after
    assert before == semantic_inventory_fingerprint([])


def test_a_real_device_still_changes_the_fingerprint():
    """La exclusión es estrecha: un dispositivo real sigue contando."""
    payload = (
        '{"items":[{"kind":"device","name":"__MCP_PROBE_x_01","model":"2911",'
        '"ports":["GigabitEthernet0/0"]}],"links":[]}'
    )

    assert _runtime(payload).inventory_fingerprint() != _runtime(
        _EMPTY,
    ).inventory_fingerprint()


def test_a_power_distribution_device_with_ports_is_not_excluded():
    """Sólo se ignora el objeto sin puertos que PT gestiona por su cuenta."""
    payload = (
        '{"items":[{"kind":"device","name":"PDD1",'
        '"model":"Power Distribution Device","ports":["Power0"]}],"links":[]}'
    )

    assert _runtime(payload).inventory_fingerprint() != _runtime(
        _EMPTY,
    ).inventory_fingerprint()


def test_a_link_is_never_treated_as_backend_managed():
    """La exclusión mira `kind`; un link nunca cae en ella."""
    payload = (
        '{"items":[],"links":[{"kind":"link","model":"Power Distribution Device",'
        '"a_device":"R1","a_port":"Gig0/0","b_device":"SW1","b_port":"Gig0/1"}]}'
    )

    assert _runtime(payload).inventory_fingerprint() != _runtime(
        _EMPTY,
    ).inventory_fingerprint()


def test_user_devices_are_preserved_alongside_the_excluded_object():
    """Un workspace con topología real conserva su identidad exacta."""
    with_pdd = (
        '{"items":[{"kind":"device","name":"R1","model":"2911","ports":["Gig0/0"]},'
        '{"kind":"device","name":"Power Distribution Device0",'
        '"model":"Power Distribution Device","ports":[]}],"links":[]}'
    )
    without_pdd = (
        '{"items":[{"kind":"device","name":"R1","model":"2911",'
        '"ports":["Gig0/0"]}],"links":[]}'
    )

    assert _runtime(with_pdd).inventory_fingerprint() == _runtime(
        without_pdd,
    ).inventory_fingerprint()
