"""Enumerar un slot y nombrar lo que contiene son observaciones distintas.

Medido en vivo contra PT 9.0.1.0858 por el file-bridge. `getRootModule()`
responde y expone `getSlotCount`, `getModuleCount`, `getModuleNumber`,
`getSlotTypeAt` y `getPortCount`: 3 slots en un 3650-24PS y 1 en un 2911.

`getModuleNameAsString()` es de aridad cero y se llama sobre el módulo, no
sobre el padre -- llamarla con un argumento lanza "Invalid arguments", que fue
lo que en su momento pareció ausencia de getter. Con la firma correcta responde
y devuelve la cadena "None", también para el módulo del 2911 que expone 3
puertos y por tanto existe. La identidad no es observable en esta superficie;
no es una cuestión de aridad pendiente.
"""

from __future__ import annotations

from src.packet_tracer_mcp.infrastructure.execution.probe_runtime import (
    PacketTracerBridgeProbeRuntime,
)


def _modules(*entries: dict):
    """Parsea la mitad de módulos de la respuesta de creación.

    Se ejercita el parser y no `create_temporary_device`, porque esa ruta
    espera además la readiness del IOS y aquí no se prueba el arranque.
    """
    parse = PacketTracerBridgeProbeRuntime._module_descriptor
    return [parse(entry) for entry in entries]


_EMPTY_SLOT = {"name": "None", "slot_type_code": "18", "port_count": 0}


_SLOT_WITH_PORTS = {"name": "None", "slot_type_code": "18", "port_count": 3}


class TestSlotEnumeration:
    def test_slots_are_enumerated_with_their_type_code(self):
        modules = _modules(
            {**_EMPTY_SLOT, "slot": "0"},
            {**_EMPTY_SLOT, "slot": "1"},
            {**_EMPTY_SLOT, "slot": "2"},
        )

        assert [item.slot for item in modules] == ["0", "1", "2"]
        assert {item.slot_type_code for item in modules} == {"18"}
        assert all(item.installed for item in modules)

    def test_port_count_per_module_is_preserved(self):
        assert _modules({**_SLOT_WITH_PORTS, "slot": "0"})[0].port_count == 3

    def test_a_missing_port_count_is_not_guessed(self):
        assert _modules({"name": "None", "slot": "0"})[0].port_count == 0

    def test_an_absent_slot_number_stays_absent(self):
        assert _modules({"name": "None"})[0].slot is None


class TestInstalledIdentity:
    def test_the_literal_none_string_is_not_taken_as_a_name(self):
        module = _modules({**_EMPTY_SLOT, "slot": "0"})[0]

        assert not module.identity_observable
        assert module.name == ""

    def test_identity_stays_unobservable_even_when_the_module_has_ports(self):
        """El control positivo del 2911: el modulo existe y sigue sin nombre."""
        module = _modules({**_SLOT_WITH_PORTS, "slot": "0"})[0]

        assert module.port_count == 3
        assert not module.identity_observable

    def test_a_real_name_is_recorded_when_the_runtime_supplies_one(self):
        """El gate es estrecho: un nombre de verdad si cuenta."""
        module = _modules({
            "name": "HWIC-2T", "slot": "0", "slot_type_code": "18", "port_count": 2,
        })[0]

        assert module.identity_observable
        assert module.name == "HWIC-2T"

    def test_an_empty_or_null_name_is_also_not_an_identity(self):
        for raw in ("", "  ", "null", "NONE"):
            assert not _modules({"name": raw, "slot": "0"})[0].identity_observable
