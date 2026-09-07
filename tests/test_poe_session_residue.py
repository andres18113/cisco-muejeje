"""POE-1: la huella de un fixture desechable incluye lo que PT agrego por el.

Medido en vivo (run `poe1-4d342a1a`): el teardown gobernado borro los dos
dispositivos que habia creado -- `endpoint_deleted=True`, `switch_deleted=True`
-- y aun asi el inventario NO volvio a su fingerprint de apertura. La unica
diferencia era:

    ...|Power Distribution Device/Power Distribution Device0

Packet Tracer coloco ese dispositivo por su cuenta al aparecer el 7960. No lo
creo el runtime, asi que `delete_device` lo rechazo, y hace bien: sólo borra
nombres que registro al crearlos. Pero entonces nadie lo retiraba, y el lienzo
quedaba sucio para la corrida siguiente -- cuya propia precondicion es un
inventario vacio. El residuo bloquea al proximo run.

Retirarlo necesita una autoridad distinta y mas angosta que "borrar cualquier
cosa": lo unico que se puede retirar es lo que NO estaba antes de abrir la
sesion. Un nombre presente en la apertura es del usuario y no se toca, pase lo
que pase.
"""

from __future__ import annotations

import json

from src.packet_tracer_mcp.infrastructure.execution.poe_delivery_runtime import (
    PacketTracerPoEDeliveryFixtureRuntime,
)
from tests.test_poe_delivery_runtime import RecordingTransport


def test_a_device_packet_tracer_added_during_the_session_can_be_retired() -> None:
    """El residuo que dejo el run real: presente ahora, ausente en la apertura."""
    transport = RecordingTransport([
        json.dumps({"devices": ["Power Distribution Device0"]}),
        json.dumps({"removed": True}),
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT 9.0.1.0858")

    retired = runtime.retire_session_residue(frozenset())

    assert retired == ("Power Distribution Device0",)
    scripts = [script for script, _ in transport.calls if "removeDevice" in script]
    assert len(scripts) == 1
    assert json.dumps("Power Distribution Device0") in scripts[0]


def test_a_device_that_predates_the_session_is_never_retired() -> None:
    """Lo que ya estaba es del usuario. No se toca ni para dejar limpio."""
    transport = RecordingTransport([
        json.dumps({"devices": ["USER_DEVICE", "Power Distribution Device0"]}),
        json.dumps({"removed": True}),
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT 9.0.1.0858")

    retired = runtime.retire_session_residue(frozenset({"USER_DEVICE"}))

    assert retired == ("Power Distribution Device0",)
    scripts = [script for script, _ in transport.calls if "removeDevice" in script]
    assert len(scripts) == 1
    assert "USER_DEVICE" not in scripts[0]


def test_an_unchanged_canvas_is_left_completely_alone() -> None:
    """Sin residuo no hay mutacion: ni un `removeDevice` de mas."""
    transport = RecordingTransport([
        json.dumps({"devices": ["USER_DEVICE"]}),
    ])
    runtime = PacketTracerPoEDeliveryFixtureRuntime(transport, "PT 9.0.1.0858")

    assert runtime.retire_session_residue(frozenset({"USER_DEVICE"})) == ()
    assert not [script for script, _ in transport.calls if "removeDevice" in script]
