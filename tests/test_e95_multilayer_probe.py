"""Estrategia L3 declarativa, lectura de SVI y clasificación inter-VLAN.

Medido en vivo contra PT 9.0.1.0858 por el file-bridge, sobre 3650-24PS y
3560-24PS desechables: ambos alcanzaron SVI configurada, con dirección leída,
admin up, line protocol up, y forwarding entre VLAN 10 y VLAN 20 demostrado en
ambos sentidos.

Dos defectos propios salieron de esa corrida y quedan fijados aquí:

`show ip interface brief` pagina en un switch de 24+ puertos y PT 9.0.1 rechaza
`terminal length 0`, así que las interfaces Vlan caían fuera de la primera
página y su ausencia se leía como "la SVI no existe". La lectura por interfaz
entrega estado y dirección dentro de esa primera página.

El primer `ping` de un endpoint recién creado devuelve un resultado sin ventana
fresca. Tomado como medida, un camino que funciona se clasifica inalcanzable:
en la reproducción, `A->SVI10` daba `no_fresh_ping_result` mientras `A->PCB`
por la misma ruta respondía.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    Layer3ProbeStrategy,
    MultilayerDimension,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    parse_show_ip_interface,
)
from src.packet_tracer_mcp.infrastructure.execution.probe_runtime import (
    layer3_strategy_for,
)


class TestLayer3Strategy:
    def test_multilayer_switches_declare_the_svi_strategy(self):
        assert layer3_strategy_for("3650-24PS") is Layer3ProbeStrategy.SVI
        assert layer3_strategy_for("3560-24PS") is Layer3ProbeStrategy.SVI

    def test_a_router_declares_a_routed_physical_interface(self):
        assert layer3_strategy_for("2911") is (
            Layer3ProbeStrategy.ROUTED_PHYSICAL_INTERFACE
        )

    def test_a_layer2_switch_declares_no_strategy(self):
        """Soportar VLANs no implica poder enrutar entre ellas."""
        assert layer3_strategy_for("2960-24TT") is Layer3ProbeStrategy.NONE

    def test_an_unknown_model_never_guesses_a_strategy(self):
        assert layer3_strategy_for("no-such-model") is Layer3ProbeStrategy.NONE

    def test_a_catalog_alias_resolves_to_the_declared_strategy(self):
        """El alias pasa por el catálogo; antes se comparaba por subcadena."""
        assert layer3_strategy_for("3560") is Layer3ProbeStrategy.SVI

    def test_an_endpoint_never_declares_a_layer3_strategy(self):
        assert layer3_strategy_for("PC-PT") is Layer3ProbeStrategy.NONE


class TestShowIpInterfaceParser:
    _UP_DOWN = (
        "show ip interface Vlan10\n"
        "Vlan10 is up, line protocol is down\n"
        "  Internet address is 198.18.140.1/24\n"
        "  Broadcast address is 255.255.255.255\n"
    )

    def test_admin_and_line_protocol_are_read_separately(self):
        row = parse_show_ip_interface(self._UP_DOWN)

        assert row is not None
        assert row.interface == "Vlan10"
        assert row.status == "up"
        assert row.protocol == "down"

    def test_the_address_is_read_without_its_prefix(self):
        assert parse_show_ip_interface(self._UP_DOWN).ip_address == "198.18.140.1"

    def test_an_administratively_down_svi_is_distinguishable(self):
        row = parse_show_ip_interface(
            "Vlan20 is administratively down, line protocol is down\n"
            "  Internet address is 198.18.141.1/24\n",
        )

        assert "administratively down" in row.status
        assert row.protocol == "down"

    def test_an_svi_without_an_address_is_not_invented(self):
        row = parse_show_ip_interface("Vlan30 is up, line protocol is up\n")

        assert row.ip_address == "unassigned"

    def test_output_without_an_interface_line_returns_nothing(self):
        assert parse_show_ip_interface("% Invalid input detected") is None

    def test_a_truncated_brief_listing_is_not_parsed_as_an_svi(self):
        """El caso live: la paginación cortaba antes de las interfaces Vlan."""
        truncated = (
            "show ip interface brief\n"
            "Interface              IP-Address      OK? Method Status    Protocol\n"
            "GigabitEthernet1/0/1   unassigned      YES unset  down      down\n"
        )
        row = parse_show_ip_interface(truncated)

        assert row is None or row.interface != "Vlan10"


class TestMultilayerDimensions:
    def test_every_dimension_the_closure_must_distinguish_exists(self):
        assert {item.value for item in MultilayerDimension} == {
            "svi_configuration", "svi_address_readback", "svi_admin_state",
            "svi_operational_state", "ip_routing", "endpoint_gateway",
            "intervlan_forwarding",
        }

    def test_forwarding_and_routing_are_separate_dimensions(self):
        """`ip routing` se prueba por el forwarding, pero no es lo mismo."""
        assert (
            MultilayerDimension.IP_ROUTING
            is not MultilayerDimension.INTERVLAN_FORWARDING
        )


class TestTheLayer3StrategyComesFromTheCatalogueNotAHandList:
    """MEG-5: `1941` se saltaba con `layer3` UNKNOWN por no estar en el mapa.

    Medido en la cualificacion MEG-5 contra PT 9.0.1.0858: el probe respondio
    "No model-specific IPv4 probe target is available for this device" para el
    router que la referencia de 41 dispositivos selecciona, con `2911` ya
    cualificado por el mismo mecanismo. Enrutar sobre una interfaz fisica es lo
    que hace router a un router; enumerarlos a mano garantizaba que cada router
    nuevo entrara UNKNOWN.
    """

    def test_a_router_the_map_never_named_still_routes_on_a_physical_interface(self):
        assert layer3_strategy_for("1941") is (
            Layer3ProbeStrategy.ROUTED_PHYSICAL_INTERFACE
        )

    def test_every_router_in_the_catalogue_resolves_a_strategy(self):
        from src.packet_tracer_mcp.infrastructure.catalog.devices import ALL_MODELS

        routers = [
            model.pt_type for model in ALL_MODELS.values()
            if model.category == "router"
        ]

        assert routers
        assert all(
            layer3_strategy_for(item) is Layer3ProbeStrategy.ROUTED_PHYSICAL_INTERFACE
            for item in routers
        )

    def test_switch_category_alone_never_grants_layer3(self):
        """`switch` cubre L2 y multilayer; solo el segundo alcanza una IPv4."""
        assert layer3_strategy_for("2950T-24") is Layer3ProbeStrategy.NONE
        assert layer3_strategy_for("IE-2000") is Layer3ProbeStrategy.NONE
        assert layer3_strategy_for("3560-24PS") is Layer3ProbeStrategy.SVI

    def test_the_declared_map_holds_only_what_the_category_cannot_decide(self):
        from src.packet_tracer_mcp.infrastructure.execution.probe_runtime import (
            _LAYER3_STRATEGY_BY_MODEL,
        )
        from src.packet_tracer_mcp.infrastructure.catalog.devices import resolve_model

        # Un router en el mapa seria una entrada que la categoria ya deriva, y
        # es exactamente la clase de duplicado que dejo a 1941 fuera.
        assert not [
            model for model in _LAYER3_STRATEGY_BY_MODEL
            if (resolve_model(model) or None) and resolve_model(model).category == "router"
        ]
