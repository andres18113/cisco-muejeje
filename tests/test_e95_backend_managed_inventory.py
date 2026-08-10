"""Inventario semántico frente a objetos que Packet Tracer gestiona solo.

Reproducido en vivo contra PT 9.0.1.0858 por el file-bridge: desde un workspace
vacío, una sesión creó tres switches temporales, los borró los tres sin fallo de
cleanup, y el workspace terminó con un dispositivo -- un `Power Distribution
Device0` que PT materializa por su cuenta y conserva. La huella lo contaba, la
sesión quedaba NOT_RESTORED y ninguna sesión live podía completarse.

Excluirlo sin más tenía un fallo peor: borrar un Power Distribution Device
preexistente del usuario se volvía invisible. La huella guarda por eso dos
mitades -- semántica y backend-managed -- y exige cosas distintas de cada una:
la semántica debe coincidir exactamente, la backend-managed sólo puede crecer.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    decode_inventory_observation,
    inventory_restoration_matches,
)
from src.packet_tracer_mcp.infrastructure.execution.probe_runtime import (
    PacketTracerBridgeProbeRuntime,
)


def _runtime(payload: str) -> PacketTracerBridgeProbeRuntime:
    return PacketTracerBridgeProbeRuntime(lambda _js, _timeout: payload)


def _fingerprint(payload: str) -> str:
    return _runtime(payload).inventory_fingerprint()


_EMPTY = '{"items":[],"links":[]}'
_PDD = (
    '{"items":[{"kind":"device","name":"Power Distribution Device0",'
    '"model":"Power Distribution Device","ports":[]}],"links":[]}'
)
_USER_PDD = (
    '{"items":[{"kind":"device","name":"PDD-del-usuario",'
    '"model":"Power Distribution Device","ports":[]}],"links":[]}'
)
_ROUTER = (
    '{"items":[{"kind":"device","name":"R1","model":"2911",'
    '"ports":["GigabitEthernet0/0"]}],"links":[]}'
)


class TestBackendManagedHalf:
    def test_appearing_backend_object_still_counts_as_restored(self):
        """El caso live exacto: vacío antes, PDD después."""
        assert inventory_restoration_matches(_fingerprint(_EMPTY), _fingerprint(_PDD))

    def test_a_preexisting_backend_object_may_not_disappear(self):
        """El fallo que este diseño corrige: el borrado ya no es invisible."""
        assert not inventory_restoration_matches(
            _fingerprint(_USER_PDD), _fingerprint(_EMPTY),
        )

    def test_a_preexisting_backend_object_may_not_be_replaced(self):
        """Cambiar su identidad tampoco pasa desapercibido."""
        assert not inventory_restoration_matches(
            _fingerprint(_USER_PDD), _fingerprint(_PDD),
        )

    def test_a_preexisting_backend_object_survives_a_new_one(self):
        both = (
            '{"items":[{"kind":"device","name":"PDD-del-usuario",'
            '"model":"Power Distribution Device","ports":[]},'
            '{"kind":"device","name":"Power Distribution Device0",'
            '"model":"Power Distribution Device","ports":[]}],"links":[]}'
        )

        assert inventory_restoration_matches(_fingerprint(_USER_PDD), _fingerprint(both))

    def test_backend_identity_is_recorded_not_collapsed_to_a_count(self):
        _, managed = decode_inventory_observation(_fingerprint(_USER_PDD))

        assert managed == frozenset({"Power Distribution Device/PDD-del-usuario"})


class TestSemanticHalf:
    def test_a_leaked_probe_device_breaks_restoration(self):
        leaked = (
            '{"items":[{"kind":"device","name":"__MCP_PROBE_x_01","model":"2911",'
            '"ports":["GigabitEthernet0/0"]}],"links":[]}'
        )

        assert not inventory_restoration_matches(_fingerprint(_EMPTY), _fingerprint(leaked))

    def test_a_user_device_that_disappears_breaks_restoration(self):
        assert not inventory_restoration_matches(_fingerprint(_ROUTER), _fingerprint(_EMPTY))

    def test_a_power_distribution_device_with_ports_stays_semantic(self):
        """La mitad backend-managed sólo admite el objeto sin puertos."""
        with_ports = (
            '{"items":[{"kind":"device","name":"PDD1",'
            '"model":"Power Distribution Device","ports":["Power0"]}],"links":[]}'
        )
        semantic, managed = decode_inventory_observation(_fingerprint(with_ports))

        assert managed == frozenset()
        assert semantic != decode_inventory_observation(_fingerprint(_EMPTY))[0]

    def test_a_link_is_never_backend_managed(self):
        payload = (
            '{"items":[],"links":[{"kind":"link","model":"Power Distribution Device",'
            '"a_device":"R1","a_port":"Gig0/0","b_device":"SW1","b_port":"Gig0/1"}]}'
        )
        _, managed = decode_inventory_observation(_fingerprint(payload))

        assert managed == frozenset()
        assert not inventory_restoration_matches(_fingerprint(_EMPTY), _fingerprint(payload))

    def test_user_topology_keeps_its_identity_when_a_backend_object_appears(self):
        router_and_pdd = (
            '{"items":[{"kind":"device","name":"R1","model":"2911","ports":["Gig0/0"]},'
            '{"kind":"device","name":"Power Distribution Device0",'
            '"model":"Power Distribution Device","ports":[]}],"links":[]}'
        )
        only_router = (
            '{"items":[{"kind":"device","name":"R1","model":"2911",'
            '"ports":["Gig0/0"]}],"links":[]}'
        )

        assert inventory_restoration_matches(
            _fingerprint(only_router), _fingerprint(router_and_pdd),
        )


class TestLegacyEncoding:
    def test_a_legacy_fingerprint_without_the_managed_half_still_compares(self):
        """Un valor persistido antes de este cambio no se reinterpreta."""
        semantic, managed = decode_inventory_observation("abc123")

        assert semantic == "abc123"
        assert managed == frozenset()
        assert inventory_restoration_matches("abc123", "abc123")
        assert not inventory_restoration_matches("abc123", "def456")
