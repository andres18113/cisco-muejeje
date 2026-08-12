"""RIPv2 tipado: dominio, compilador, renderer, readback y verificación.

El estado semántico de referencia proviene de la calificación en vivo R2-0
(PT 9.0.1.0858, 2911). Este módulo es OFFLINE: no toca Packet Tracer.
"""

from __future__ import annotations

import pathlib

import pytest

from src.packet_tracer_mcp.application.use_cases.compile_control_plane import (
    compile_enterprise_control_plane,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureRoutedInterface,
    ConfigurationIssueCode,
    ConfigurationPhase,
    ConfigurationPlan,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneActionType,
    ControlPlaneCapabilityDimension,
    ControlPlaneCapabilityProfile,
    ControlPlaneIntent,
    ControlPlanePhase,
    ControlPlaneVerificationKind,
    DynamicRoutingIntent,
    DynamicRoutingProtocol,
    RipNetwork,
)
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from src.packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosCommandResult,
    IosSessionState,
    OperationalQueryId,
    parse_show_ip_protocols_rip,
    parse_show_ip_route_rip,
)
from src.packet_tracer_mcp.infrastructure.generator.control_plane_renderer import (
    PacketTracerControlPlaneRenderer,
)


# Capturado en vivo durante R2-0. Packet Tracer indenta las entradas de red y
# de interfaz pasiva con TAB, no con espacios: el fixture conserva el TAB
# literal porque esa es la propiedad que el parser tiene que soportar.
_PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP = (
    "show ip protocols\n"
    'Routing Protocol is "rip"\n'
    "Sending updates every 30 seconds, next due in 21 seconds\n"
    "Invalid after 180 seconds, hold down 180, flushed after 240\n"
    "Outgoing update filter list for all interfaces is not set\n"
    "Incoming update filter list for all interfaces is not set\n"
    "Redistributing: rip\n"
    "Default version control: send version 2, receive 2\n"
    "  Interface             Send  Recv  Triggered RIP  Key-chain\n"
    "Automatic network summarization is not in effect\n"
    "Maximum path: 4\n"
    "Routing for Networks:\n"
    "\t150.1.0.0\n"
    "Passive Interface(s):\n"
    "\tGigabitEthernet0/0\n"
    "Routing Information Sources:\n"
    "\tGateway         Distance      Last Update\n"
    "Distance: (default is 120)\n"
    "Router>"
)


# Capturado EN VIVO durante R2-B fase 3 sobre PT 9.0.1.0858, recorriendo el
# pager para reconstruir la salida completa. Dos bloques reales: EIGRP primero
# --con SUS PROPIAS `Routing for Networks:` y `Passive Interface(s):`, que son
# justo las trampas de fuga-- y RIP despues. Conserva las dos indentaciones
# reales: EIGRP con espacios, RIP con TAB.
_PT_9_0_1_0858_SHOW_IP_PROTOCOLS_EIGRP_THEN_RIP = (
    "show ip protocols\n"
    'Routing Protocol is "eigrp  100 " \n'
    "  Outgoing update filter list for all interfaces is not set \n"
    "  Incoming update filter list for all interfaces is not set \n"
    "  Default networks flagged in outgoing updates  \n"
    "  Default networks accepted from incoming updates \n"
    "  Redistributing: eigrp 100\n"
    "  EIGRP-IPv4 Protocol for AS(100)\n"
    "    Metric weight K1=1, K2=0, K3=1, K4=0, K5=0\n"
    "    NSF-aware route hold timer is 240\n"
    "    Router-ID: 10.0.0.1\n"
    "    Topology : 0 (base)\n"
    "      Active Timer: 3 min\n"
    "      Distance: internal 90 external 170\n"
    "      Maximum path: 4\n"
    "      Maximum hopcount 100\n"
    "      Maximum metric variance 1\n"
    "  Automatic Summarization: disabled\n"
    "  Automatic address summarization: \n"
    "  Maximum path: 4\n"
    "  Routing for Networks:  \n"
    "     10.0.0.0\n"
    "  Passive Interface(s): \n"
    "    GigabitEthernet0/1\n"
    "  Routing Information Sources:  \n"
    "    Gateway         Distance      Last Update \n"
    "  Distance: internal 90 external 170\n"
    'Routing Protocol is "rip"\n'
    "Sending updates every 30 seconds, next due in 10 seconds\n"
    "Invalid after 180 seconds, hold down 180, flushed after 240\n"
    "Outgoing update filter list for all interfaces is not set\n"
    "Incoming update filter list for all interfaces is not set\n"
    "Redistributing: rip\n"
    "Default version control: send version 2, receive 2\n"
    "  Interface             Send  Recv  Triggered RIP  Key-chain\n"
    "Automatic network summarization is not in effect\n"
    "Maximum path: 4\n"
    "Routing for Networks:\n"
    "\t150.1.0.0\n"
    "Passive Interface(s):\n"
    "\tGigabitEthernet0/0\n"
    "Routing Information Sources:\n"
    "\tGateway         Distance      Last Update\n"
    "Distance: (default is 120)\n"
    "Router>"
)


# Capturado EN VIVO en R2-B fase 4 sobre PT 9.0.1.0858, sobre la rebanada
# PCA -- R1 == serial == R2 -- PCC. La ruta aprendida llega por una Serial,
# no por Gigabit: por eso el parser no ancla la familia de interfaz.
_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1 = (
    "show ip route rip\n"
    "     150.1.0.0/16 is variably subnetted, 5 subnets, 4 masks\n"
    "R       150.1.1.0/27 [120/1] via 150.1.1.86, 00:00:26, Serial0/0/0\n"
    "\n"
    "Router>"
)

_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R2 = (
    "show ip route rip\n"
    "     150.1.0.0/16 is variably subnetted, 5 subnets, 4 masks\n"
    "R       150.1.1.64/28 [120/1] via 150.1.1.85, 00:00:07, Serial0/0/0\n"
    "\n"
    "Router>"
)


def _rip_output(
    *,
    send: int = 2,
    recv: int = 2,
    summarization: str = "not in effect",
    networks: tuple[str, ...] = ("150.1.0.0",),
    passive: tuple[str, ...] = ("GigabitEthernet0/0",),
) -> str:
    text = _PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP
    text = text.replace(
        "send version 2, receive 2", f"send version {send}, receive {recv}",
    )
    text = text.replace(
        "Automatic network summarization is not in effect",
        f"Automatic network summarization is {summarization}",
    )
    text = text.replace(
        "Routing for Networks:\n\t150.1.0.0\n",
        "Routing for Networks:\n" + "".join(f"\t{item}\n" for item in networks),
    )
    passive_block = (
        "Passive Interface(s):\n" + "".join(f"\t{item}\n" for item in passive)
        if passive else ""
    )
    return text.replace(
        "Passive Interface(s):\n\tGigabitEthernet0/0\n", passive_block,
    )


def _action(**updates) -> ConfigureRipv2:
    values = {
        "id": "cp/ripv2/reference",
        "phase": ControlPlanePhase.DYNAMIC_ROUTING,
        "device_id": "r1",
        "device_name": "R1",
        "model": "2911",
        "site_id": "hq",
        "required_capability": ControlPlaneCapabilityDimension.RIPV2_CONFIG,
        "networks": [RipNetwork(
            network="150.1.0.0",
            source_segment_ids=["hq-lan"],
            source_configuration_action_ids=["cfg/l3/r1/hq-lan"],
        )],
        "passive_interfaces": ["GigabitEthernet0/0"],
    }
    values.update(updates)
    return ConfigureRipv2(**values)


# --------------------------------------------------------------------------
# Fixture universitaria a nivel de protocolo: tres routers en 150.1.0.0.
# NO construye la topología de 41 dispositivos ni ejecuta Packet Tracer.
# --------------------------------------------------------------------------

_UNIVERSITY_L3 = [
    ("r1", "GigabitEthernet0/0", "150.1.100.1", 30, "transit-r1-r2"),
    ("r2", "GigabitEthernet0/0", "150.1.100.2", 30, "transit-r1-r2"),
    ("r2", "GigabitEthernet0/1", "150.1.200.1", 30, "transit-r2-r3"),
    ("r3", "GigabitEthernet0/1", "150.1.200.2", 30, "transit-r2-r3"),
    ("r1", "GigabitEthernet0/2", "150.1.1.1", 24, "lan-r1"),
    ("r2", "GigabitEthernet0/2", "150.1.2.1", 24, "lan-r2"),
    ("r3", "GigabitEthernet0/2", "150.1.3.1", 24, "lan-r3"),
]


def _university_fixture(l3_values=None):
    routers = {
        key: DevicePlan(
            id=key, name=f"UCE-{key.upper()}", model="2911",
            category="router", site_id="campus", network_layer="core",
        )
        for key in ("r1", "r2", "r3")
    }
    links = [
        LinkPlan(
            id="transit-r1-r2", device_a="UCE-R1", device_a_id="r1",
            port_a="GigabitEthernet0/0", device_b="UCE-R2", device_b_id="r2",
            port_b="GigabitEthernet0/0", cable="cross", link_role="core_link",
        ),
        LinkPlan(
            id="transit-r2-r3", device_a="UCE-R2", device_a_id="r2",
            port_a="GigabitEthernet0/1", device_b="UCE-R3", device_b_id="r3",
            port_b="GigabitEthernet0/1", cable="cross", link_role="core_link",
        ),
    ]
    topology = TopologyPlan(
        id="uce-campus", semantic_hash="uce-campus-hash",
        devices=list(routers.values()), links=links,
    )
    configuration = ConfigurationPlan(
        id="uce-campus-l3",
        source_topology_id=topology.id,
        source_topology_hash=topology.semantic_hash,
        semantic_hash="uce-campus-l3-hash",
        actions=[
            ConfigureRoutedInterface(
                id=f"cfg/l3/{device}/{segment}",
                phase=ConfigurationPhase.L3_INTERFACES,
                device_id=device,
                device_name=routers[device].name,
                site_id="campus",
                interface=interface,
                ipv4=address,
                prefix=prefix,
                netmask="255.255.255.252" if prefix == 30 else "255.255.255.0",
                segment_id=segment,
                required_capability="layer3",
            )
            for device, interface, address, prefix, segment
            in (l3_values if l3_values is not None else _UNIVERSITY_L3)
        ],
    )
    intent = ControlPlaneIntent(
        id="uce-rip",
        routing_domains=[DynamicRoutingIntent(
            id="routing/campus",
            site_id="campus",
            protocol=DynamicRoutingProtocol.RIPV2,
            device_ids=["r1", "r2", "r3"],
            transit_link_ids=["transit-r1-r2", "transit-r2-r3"],
        )],
    )
    capabilities = {"2911": ControlPlaneCapabilityProfile.supported("2911")}
    return intent, topology, configuration, capabilities


def _compile_university(l3_values=None):
    return compile_enterprise_control_plane(
        *_university_fixture(l3_values)[:3],
        capabilities=_university_fixture(l3_values)[3],
    )


# ===================== A. validación de dominio ============================


def test_ripv2_action_cannot_declare_any_version_but_two():
    with pytest.raises(ValueError):
        _action(version=1)


def test_rip_network_carries_no_wildcard_or_area():
    fields = set(RipNetwork.model_fields)

    assert "wildcard" not in fields
    assert "area" not in fields
    assert fields == {
        "network", "source_segment_ids", "source_configuration_action_ids",
    }


def test_renderer_rejects_a_network_that_is_not_classful():
    action = _action(networks=[RipNetwork(network="150.1.1.0")])

    with pytest.raises(ValueError, match="not a classful network address"):
        PacketTracerControlPlaneRenderer().render_action(action)


def test_renderer_rejects_an_unroutable_network_class():
    action = _action(networks=[RipNetwork(network="224.0.0.0")])

    with pytest.raises(ValueError, match="no routable class"):
        PacketTracerControlPlaneRenderer().render_action(action)


def test_renderer_rejects_rip_without_any_network_statement():
    with pytest.raises(ValueError, match="unique compiled classful networks"):
        PacketTracerControlPlaneRenderer().render_action(_action(networks=[]))


def test_renderer_rejects_duplicate_networks_and_passive_interfaces():
    duplicate_networks = _action(networks=[
        RipNetwork(network="150.1.0.0"), RipNetwork(network="150.1.0.0"),
    ])
    duplicate_passive = _action(passive_interfaces=[
        "GigabitEthernet0/0", "gigabitethernet0/0",
    ])

    with pytest.raises(ValueError, match="unique compiled classful networks"):
        PacketTracerControlPlaneRenderer().render_action(duplicate_networks)
    with pytest.raises(ValueError, match="passive interfaces contain duplicates"):
        PacketTracerControlPlaneRenderer().render_action(duplicate_passive)


# ===================== B/C. compilador y acción tipada =====================


def test_compiler_emits_a_typed_ripv2_action_per_router():
    result = _compile_university()

    assert result.is_valid, result.issues
    actions = result.plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
    assert len(actions) == 3
    assert all(isinstance(item, ConfigureRipv2) for item in actions)
    assert all(item.version == 2 for item in actions)
    assert all(item.no_auto_summary for item in actions)
    assert all(
        item.required_capability is ControlPlaneCapabilityDimension.RIPV2_CONFIG
        for item in actions
    )
    assert not result.plan.actions_of_type(
        ControlPlaneActionType.CONFIGURE_OSPFV2,
    )
    assert not result.plan.actions_of_type(
        ControlPlaneActionType.CONFIGURE_EIGRP_IPV4,
    )


def test_compiler_collapses_every_subnet_into_one_classful_statement():
    result = _compile_university()
    by_device = {
        item.device_id: item
        for item in result.plan.actions_of_type(
            ControlPlaneActionType.CONFIGURE_RIPV2,
        )
    }

    # r2 tiene dos tránsitos y una LAN, todos dentro de 150.1.0.0/16.
    assert [item.network for item in by_device["r2"].networks] == ["150.1.0.0"]
    assert by_device["r2"].networks[0].source_segment_ids == [
        "lan-r2", "transit-r1-r2", "transit-r2-r3",
    ]
    assert by_device["r2"].networks[0].source_configuration_action_ids == [
        "cfg/l3/r2/lan-r2",
        "cfg/l3/r2/transit-r1-r2",
        "cfg/l3/r2/transit-r2-r3",
    ]


def test_compiler_output_is_deterministic_and_orders_every_list():
    first = _compile_university()
    second = _compile_university()
    reversed_inputs = _compile_university(list(reversed(_UNIVERSITY_L3)))

    assert first.plan.model_dump(mode="json") == second.plan.model_dump(mode="json")
    assert first.semantic_hash == reversed_inputs.semantic_hash
    for action in first.plan.actions_of_type(
        ControlPlaneActionType.CONFIGURE_RIPV2,
    ):
        networks = [item.network for item in action.networks]
        assert networks == sorted(set(networks))
        assert action.passive_interfaces == sorted(set(action.passive_interfaces))


def test_compiler_marks_only_non_transit_interfaces_passive():
    by_device = {
        item.device_id: item
        for item in _compile_university().plan.actions_of_type(
            ControlPlaneActionType.CONFIGURE_RIPV2,
        )
    }

    assert by_device["r1"].passive_interfaces == ["GigabitEthernet0/2"]
    assert by_device["r2"].passive_interfaces == ["GigabitEthernet0/2"]
    assert by_device["r3"].passive_interfaces == ["GigabitEthernet0/2"]


def test_compiler_rejects_a_router_with_no_classful_rip_network():
    result = _compile_university([
        ("r1", "GigabitEthernet0/0", "150.1.100.1", 30, "transit-r1-r2"),
        ("r2", "GigabitEthernet0/0", "150.1.100.2", 30, "transit-r1-r2"),
        ("r2", "GigabitEthernet0/1", "150.1.200.1", 30, "transit-r2-r3"),
        ("r3", "GigabitEthernet0/1", "150.1.200.2", 30, "transit-r2-r3"),
        ("r3", "GigabitEthernet0/2", "224.0.1.1", 24, "lan-r3"),
    ])

    assert not result.is_valid
    assert any(
        item.code is ConfigurationIssueCode.CONTROL_PLANE_ROUTING_FOUNDATION_MISSING
        for item in result.issues
    )


def test_unknown_capability_never_becomes_unsupported():
    intent, topology, configuration, _ = _university_fixture()
    result = compile_enterprise_control_plane(
        intent, topology, configuration,
        capabilities={"2911": ControlPlaneCapabilityProfile(model="2911")},
    )

    assert result.is_valid, result.issues
    assert result.plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)


# ===================== D/E. renderer =======================================


def test_renderer_emits_the_exact_qualified_ripv2_semantics():
    rendered = PacketTracerControlPlaneRenderer().render_action(_action())

    assert rendered.ios_payload == "\n".join([
        "enable",
        "configure terminal",
        "router rip",
        " version 2",
        " no auto-summary",
        " network 150.1.0.0",
        " passive-interface GigabitEthernet0/0",
        " exit",
        "end",
        "write memory",
    ])
    assert rendered.cleanup_payload.splitlines()[2] == "no router rip"


def test_renderer_never_emits_a_mask_wildcard_or_prefix_for_rip():
    payload = PacketTracerControlPlaneRenderer().render_action(_action()).ios_payload
    network_line = next(
        line for line in payload.splitlines() if line.strip().startswith("network ")
    )

    assert network_line.strip() == "network 150.1.0.0"
    assert "0.0.255.255" not in payload
    assert "255.255.0.0" not in payload
    assert "/16" not in payload


def test_rip_body_contains_no_write_memory():
    payload = PacketTracerControlPlaneRenderer().render_action(_action()).ios_payload
    body = payload.split("configure terminal\n", 1)[1].rsplit("\nend\n", 1)[0]

    assert "write memory" not in body
    assert "copy running-config" not in body
    # La persistencia es el sobre compartido por TODA acción de control plane,
    # no semántica de RIP: aparece una sola vez y después de `end`.
    assert payload.count("write memory") == 1
    assert payload.splitlines()[-1] == "write memory"


def test_renderer_omits_no_auto_summary_when_the_intent_does_not_ask_for_it():
    payload = PacketTracerControlPlaneRenderer().render_action(
        _action(no_auto_summary=False),
    ).ios_payload

    assert "no auto-summary" not in payload
    assert " version 2" in payload


def test_renderer_rejects_a_rip_action_carrying_the_wrong_capability():
    action = _action(
        required_capability=ControlPlaneCapabilityDimension.OSPFV2_CONFIG,
    )

    with pytest.raises(ValueError, match="ripv2_config"):
        PacketTracerControlPlaneRenderer().render_action(action)


# ===================== F. parser (incluye indentación TAB) =================


def test_parser_reads_the_live_r2_0_output_including_tab_indentation():
    assert "\n\t150.1.0.0\n" in _PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP

    observed = parse_show_ip_protocols_rip(_PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP)

    assert observed is not None
    assert observed.version_send == 2
    assert observed.version_recv == 2
    assert observed.auto_summary is False
    assert observed.networks == ("150.1.0.0",)
    assert observed.passive_interfaces == ("GigabitEthernet0/0",)


def test_parser_ignores_volatile_timers():
    early = _PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP
    late = early.replace("next due in 21 seconds", "next due in 3 seconds")

    assert parse_show_ip_protocols_rip(early) == parse_show_ip_protocols_rip(late)


def test_parser_does_not_swallow_the_routing_information_sources_table():
    observed = parse_show_ip_protocols_rip(_PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP)

    assert "Gateway" not in observed.passive_interfaces
    assert observed.passive_interfaces == ("GigabitEthernet0/0",)


def test_parser_reports_absence_rather_than_guessing():
    assert parse_show_ip_protocols_rip("show ip protocols\nRouter>") is None
    assert parse_show_ip_protocols_rip(
        'show ip protocols\nRouting Protocol is "ospf 1"\nRouter>',
    ) is None


def test_parser_reads_only_rip_from_the_live_two_protocol_capture():
    """Cualificacion viva de TD-RUNTIME-003, forma 1.

    El bloque EIGRP trae sus propias `Routing for Networks: 10.0.0.0` y
    `Passive Interface(s): GigabitEthernet0/1`, y se imprime ANTES que RIP.
    Si el acotado de bloque fallara, apareceria aqui.
    """
    text = _PT_9_0_1_0858_SHOW_IP_PROTOCOLS_EIGRP_THEN_RIP
    assert text.count("Routing Protocol is") == 2
    assert text.index('"eigrp') < text.index('"rip"')

    observed = parse_show_ip_protocols_rip(text)

    assert observed is not None
    assert observed.version_send == 2
    assert observed.version_recv == 2
    assert observed.auto_summary is False
    assert observed.networks == ("150.1.0.0",)
    assert observed.passive_interfaces == ("GigabitEthernet0/0",)
    # Lo del vecino no entra.
    assert "10.0.0.0" not in observed.networks
    assert "GigabitEthernet0/1" not in observed.passive_interfaces


def test_the_live_capture_carries_both_real_indentation_styles():
    """EIGRP indenta con espacios y RIP con TAB en la MISMA salida."""
    text = _PT_9_0_1_0858_SHOW_IP_PROTOCOLS_EIGRP_THEN_RIP

    assert "\n     10.0.0.0\n" in text
    assert "\n\t150.1.0.0\n" in text


def test_parser_never_reads_another_protocol_block_as_rip_state():
    # `show ip protocols` lista un bloque por protocolo. Sin acotar el bloque,
    # el `Automatic network summarization` de EIGRP pisa el de RIP y las
    # interfaces pasivas de EIGRP se leen como si fueran de RIP.
    text = (
        "show ip protocols\n"
        'Routing Protocol is "rip"\n'
        "Default version control: send version 2, receive 2\n"
        "Automatic network summarization is not in effect\n"
        "Routing for Networks:\n"
        "\t150.1.0.0\n"
        'Routing Protocol is "eigrp 100"\n'
        "Automatic network summarization is in effect\n"
        "Routing for Networks:\n"
        "\t10.0.0.0\n"
        "Passive Interface(s):\n"
        "\tGigabitEthernet0/9\n"
        "Router>"
    )

    observed = parse_show_ip_protocols_rip(text)

    assert observed.networks == ("150.1.0.0",)
    assert observed.auto_summary is False
    assert observed.passive_interfaces == ()


def test_parser_accepts_the_receive_version_spelling_and_multiple_entries():
    text = _rip_output(networks=("150.1.0.0", "10.0.0.0"), passive=()).replace(
        "receive 2", "receive version 2",
    )

    observed = parse_show_ip_protocols_rip(text)

    assert observed.version_recv == 2
    assert observed.networks == ("150.1.0.0", "10.0.0.0")
    assert observed.passive_interfaces == ()


def test_parser_reads_auto_summary_in_effect():
    observed = parse_show_ip_protocols_rip(_rip_output(summarization="in effect"))

    assert observed.auto_summary is True


# ===================== rutas aprendidas por RIP ============================


def test_the_live_rip_route_is_recognised_on_r1():
    rows = parse_show_ip_route_rip(_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1)

    assert len(rows) == 1
    route = rows[0]
    assert route.code == "R"
    assert route.prefix == "150.1.1.0"
    assert route.prefix_length == 27
    assert route.administrative_distance == 120
    assert route.metric == 1
    assert route.next_hop == "150.1.1.86"
    assert route.interface == "Serial0/0/0"


def test_the_live_rip_route_is_recognised_on_r2():
    rows = parse_show_ip_route_rip(_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R2)

    assert [(item.prefix, item.prefix_length) for item in rows] == [
        ("150.1.1.64", 28),
    ]
    assert rows[0].next_hop == "150.1.1.85"
    assert rows[0].interface == "Serial0/0/0"


def test_a_serial_learned_route_is_not_lost_to_an_interface_family_anchor():
    """El parser de OSPF ancla `GigabitEthernet` y por eso no sirve aqui."""
    from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
        parse_show_ip_route_ospf,
    )

    assert parse_show_ip_route_ospf(_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1) == []
    assert parse_show_ip_route_rip(_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1)


@pytest.mark.parametrize(
    "text",
    [
        # Otro protocolo: la letra de codigo no es `R`.
        "show ip route\nO       150.1.1.0/27 [110/65] via 150.1.1.86, 00:00:26, Serial0/0/0\nRouter>",
        "show ip route\nD       150.1.1.0/27 [90/2172416] via 150.1.1.86, 00:00:26, Serial0/0/0\nRouter>",
        # Conectada / estatica.
        "show ip route\nC       150.1.1.84/30 is directly connected, Serial0/0/0\nRouter>",
        "show ip route\nS       150.1.1.0/27 [1/0] via 150.1.1.86\nRouter>",
    ],
    ids=["ospf", "eigrp", "connected", "static"],
)
def test_a_non_rip_route_never_satisfies_the_rip_expectation(text):
    assert parse_show_ip_route_rip(text) == []


@pytest.mark.parametrize(
    "text",
    [
        # Cortada por el pager justo en la fila.
        "show ip route rip\nR       150.1.1.0/27 [120/1] via 150.1.1.8\n --More-- ",
        # Sin siguiente salto.
        "show ip route rip\nR       150.1.1.0/27 [120/1]\nRouter>",
        # Sin metrica ni distancia.
        "show ip route rip\nR       150.1.1.0/27 via 150.1.1.86, 00:00:26, Serial0/0/0\nRouter>",
        # Sin interfaz de salida.
        "show ip route rip\nR       150.1.1.0/27 [120/1] via 150.1.1.86, 00:00:26,\nRouter>",
        # Vacia.
        "show ip route rip\nRouter>",
    ],
    ids=["pager-cut", "no-next-hop", "no-metric", "no-interface", "empty"],
)
def test_incomplete_route_evidence_never_verifies(text):
    """Fail-closed: una fila incompleta no se completa con supuestos."""
    assert parse_show_ip_route_rip(text) == []


def test_route_evidence_is_distinct_from_configuration_evidence():
    """Una cosa es que RIP este configurado y otra que haya aprendido algo."""
    configured = parse_show_ip_protocols_rip(
        _PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP,
    )
    learned = parse_show_ip_route_rip(_PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP)

    assert configured is not None
    assert learned == []


def test_the_rip_route_query_is_registered_and_unprivileged():
    from src.packet_tracer_mcp.infrastructure.execution import ios_terminal

    assert ios_terminal._COMMANDS[
        OperationalQueryId.SHOW_IP_ROUTE_RIP
    ] == "show ip route rip"
    assert OperationalQueryId.SHOW_IP_ROUTE_RIP not in ios_terminal._PRIVILEGED_QUERIES


# ===================== G/H. verificación ===================================


class _FakeIos:
    def __init__(self, results) -> None:
        self.results = results
        self.calls: list[tuple[str, OperationalQueryId]] = []

    def execute(self, device_name, query_id, *, interface=""):
        assert not interface
        self.calls.append((device_name, query_id))
        value = self.results[(device_name, query_id)]
        if isinstance(value, IosCommandResult):
            return value
        return IosCommandResult(
            device_name=device_name,
            query_id=query_id,
            executed=True,
            output=value,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True,
            window_strategy="prefix_delta",
        )


def _verify(output, *, apply_first: bool = True):
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(
            ControlPlaneActionType.CONFIGURE_RIPV2,
        ) if item.device_id == "r1"
    )
    expectation = next(
        item for item in plan.verification_expectations
        if item.action_id == action.id
        and item.kind is ControlPlaneVerificationKind.ROUTING_PROCESS
    )
    ios = _FakeIos({
        (action.device_name, OperationalQueryId.SHOW_IP_PROTOCOLS): output,
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda _script: True,
        lambda _script, _timeout: None,
        ios_executor=ios,
    )
    if apply_first:
        runtime.apply_actions([action])
    return runtime.verify([expectation])[0], action, expectation, ios


def _expected_rip_output(action) -> str:
    return _rip_output(
        networks=tuple(item.network for item in action.networks),
        passive=tuple(action.passive_interfaces),
    )


def test_matching_rip_state_verifies_every_compared_field():
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(
            ControlPlaneActionType.CONFIGURE_RIPV2,
        ) if item.device_id == "r1"
    )

    result, _, expectation, ios = _verify(_expected_rip_output(action))

    assert result.status is ActionExecutionStatus.VERIFIED
    assert result.evidence_method == "fresh_show_ip_protocols"
    assert result.fresh_evidence
    assert set(result.fields) == set(expectation.expected)
    assert set(result.fields.values()) == {FieldVerificationStatus.VERIFIED}
    assert ios.calls == [("UCE-R1", OperationalQueryId.SHOW_IP_PROTOCOLS)]


@pytest.mark.parametrize(
    ("mutation", "failed_field"),
    [
        ({"send": 1, "recv": 1}, "version_send"),
        ({"summarization": "in effect"}, "auto_summary"),
        ({"networks": ()}, "networks"),
        ({"passive": ()}, "passive_interfaces"),
    ],
    ids=["wrong-version", "auto-summary", "missing-network", "missing-passive"],
)
def test_a_divergent_rip_state_never_verifies(mutation, failed_field):
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(
            ControlPlaneActionType.CONFIGURE_RIPV2,
        ) if item.device_id == "r1"
    )
    baseline = {
        "networks": tuple(item.network for item in action.networks),
        "passive": tuple(action.passive_interfaces),
    }

    result, _, _, _ = _verify(_rip_output(**{**baseline, **mutation}))

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields[failed_field] is FieldVerificationStatus.FAILED


def test_absent_rip_process_fails_instead_of_reporting_unobservable():
    result, _, _, _ = _verify("show ip protocols\nUCE-R1>")

    assert result.status is ActionExecutionStatus.FAILED
    assert set(result.fields.values()) == {FieldVerificationStatus.FAILED}
    assert "no RIP routing process" in result.message


def test_a_pager_truncated_readback_is_unobservable_not_failed():
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(
            ControlPlaneActionType.CONFIGURE_RIPV2,
        ) if item.device_id == "r1"
    )
    truncated = IosCommandResult(
        device_name=action.device_name,
        query_id=OperationalQueryId.SHOW_IP_PROTOCOLS,
        executed=True,
        output=_expected_rip_output(action).split("Routing for Networks:")[0],
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=True,
        truncated_by_pager=True,
    )

    result, _, _, _ = _verify(truncated)

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.evidence_method == "rip_readback_truncated"
    assert not result.fresh_evidence


def test_applied_alone_never_satisfies_the_ripv2_claim():
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(
            ControlPlaneActionType.CONFIGURE_RIPV2,
        ) if item.device_id == "r1"
    )
    expectation = next(
        item for item in plan.verification_expectations
        if item.action_id == action.id
    )
    ios = _FakeIos({
        (action.device_name, OperationalQueryId.SHOW_IP_PROTOCOLS): IosCommandResult(
            device_name=action.device_name,
            query_id=OperationalQueryId.SHOW_IP_PROTOCOLS,
            executed=False,
            failure_reason="prompt_not_ready",
        ),
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda _script: True,
        lambda _script, _timeout: None,
        ios_executor=ios,
    )

    mutation = runtime.apply_actions([action])[0]
    verification = runtime.verify([expectation])[0]

    assert mutation.applied
    assert verification.status is ActionExecutionStatus.UNOBSERVABLE
    assert verification.status is not ActionExecutionStatus.VERIFIED


def test_verification_requires_the_action_to_have_been_applied():
    result, _, _, ios = _verify(
        _PT_9_0_1_0858_SHOW_IP_PROTOCOLS_RIP, apply_first=False,
    )

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert not ios.calls


# ===================== expectativa tipada de ruta (TD-RUNTIME-005) =========


def _route_expectations(plan):
    return [
        item for item in plan.verification_expectations
        if item.kind is ControlPlaneVerificationKind.ROUTE_PRESENT
    ]


def test_route_expectations_name_only_remote_prefixes():
    """El prefijo sale de las identidades L3, no de la sentencia classful."""
    plan = _compile_university().plan
    by_device: dict[str, set] = {}
    for item in _route_expectations(plan):
        by_device.setdefault(item.device_id, set()).add(
            (item.expected["network"], item.expected["prefix_length"]),
        )

    # r1 espera las LAN de r2 y r3 y el transito r2-r3; su propia LAN
    # (150.1.1.0/24) y su propio transito (150.1.100.0/30) quedan fuera.
    assert by_device["r1"] == {
        ("150.1.2.0", 24), ("150.1.3.0", 24), ("150.1.200.0", 30),
    }
    assert ("150.1.2.0", 24) not in by_device["r2"]
    assert ("150.1.3.0", 24) not in by_device["r3"]
    # Nunca la sentencia classful de RIP.
    assert all(
        network != "150.1.0.0"
        for networks in by_device.values() for network, _ in networks
    )


def test_every_compiled_expectation_has_a_unique_id():
    """Con 3+ routers un prefijo llega por varios vecinos.

    Emitir una expectativa por PAREJA producia dos con la misma id, porque la
    id no incluye al vecino. Lo encontro la aceptacion universitaria; los
    tests anteriores lo tapaban al comparar conjuntos.
    """
    plan = _compile_university().plan
    identifiers = [item.id for item in plan.verification_expectations]

    assert len(identifiers) == len(set(identifiers))


def test_a_prefix_reachable_through_two_peers_is_expected_once():
    plan = _compile_university().plan
    routes = _route_expectations(plan)
    keys = [
        (item.device_id, item.expected["network"], item.expected["prefix_length"])
        for item in routes
    ]

    assert len(keys) == len(set(keys))
    # r1 alcanza el transito r2-r3 por r2 y por r3, y aun asi se espera una vez.
    assert keys.count(("r1", "150.1.200.0", 30)) == 1


def test_a_connected_prefix_never_becomes_a_remote_route_expectation():
    plan = _compile_university().plan
    connected = {
        "r1": ("150.1.1.0", 24), "r2": ("150.1.2.0", 24), "r3": ("150.1.3.0", 24),
    }

    for item in _route_expectations(plan):
        key = (item.expected["network"], item.expected["prefix_length"])
        assert key != connected[item.device_id], (
            f"{item.device_id} no puede esperar aprender su propia {key}"
        )


def test_route_expectations_require_prefix_and_rip_but_not_topology_details():
    plan = _compile_university().plan

    for item in _route_expectations(plan):
        assert item.expected["protocol"] == "ripv2"
        assert set(item.expected) == {"network", "prefix_length", "protocol"}
        # Ni siguiente salto ni interfaz: ataria la aceptacion a una serial.
        assert "next_hop" not in item.expected
        assert "outgoing_interface" not in item.expected
        assert item.required_capability is (
            ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE
        )


def _route_case(output, *, network="150.1.1.0", prefix_length=27, truncated=False):
    """Verifica UNA expectativa de ruta contra una salida dada."""
    from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
        ControlPlaneVerificationExpectation,
    )

    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
        if item.device_id == "r1"
    )
    expectation = ControlPlaneVerificationExpectation(
        id="verify/route", kind=ControlPlaneVerificationKind.ROUTE_PRESENT,
        action_id=action.id, device_id="r1",
        required_capability=ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
        expected={"network": network, "prefix_length": prefix_length,
                  "protocol": "ripv2"},
    )
    result = IosCommandResult(
        device_name=action.device_name,
        query_id=OperationalQueryId.SHOW_IP_ROUTE_RIP,
        executed=True, output=output,
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=True, truncated_by_pager=truncated,
    )
    ios = _FakeIos({(action.device_name, OperationalQueryId.SHOW_IP_ROUTE_RIP): result})
    # Un solo intento: estos casos son sobre la COMPARACION, no sobre la
    # ventana de convergencia, que tiene sus propios tests con reloj inyectado.
    # Sin esto heredarian el presupuesto real y dormirian 45 s cada uno.
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _s: True, lambda _s, _t: None, ios_executor=ios,
        route_convergence_attempts=1,
        route_convergence_timeout_seconds=0.0,
        route_convergence_interval_seconds=0.0,
    )
    runtime.apply_actions([action])
    return runtime.verify([expectation])[0]


def test_a_learned_route_verifies():
    observed = _route_case(_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1)

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert observed.evidence_method == "fresh_show_ip_route_rip"
    assert observed.fresh_evidence


def test_a_wrong_prefix_does_not_verify():
    observed = _route_case(
        _PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1, network="10.9.9.0", prefix_length=24,
    )

    assert observed.status is ActionExecutionStatus.FAILED


def test_a_wrong_prefix_length_does_not_verify():
    observed = _route_case(
        _PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1, prefix_length=28,
    )

    assert observed.status is ActionExecutionStatus.FAILED


@pytest.mark.parametrize(
    "output",
    [
        "show ip route rip\nO       150.1.1.0/27 [110/65] via 150.1.1.86, 00:00:26, Serial0/0/0\nRouter>",
        "show ip route rip\nD       150.1.1.0/27 [90/2172416] via 150.1.1.86, 00:00:26, Serial0/0/0\nRouter>",
        "show ip route rip\nC       150.1.1.0/27 is directly connected, Serial0/0/0\nRouter>",
    ],
    ids=["ospf", "eigrp", "connected"],
)
def test_a_route_from_another_protocol_does_not_verify(output):
    observed = _route_case(output)

    assert observed.status is ActionExecutionStatus.FAILED


def test_a_pager_truncated_route_table_is_unobservable_not_failed():
    observed = _route_case(
        "show ip route rip\nR       150.1.1.0/2\n --More-- ", truncated=True,
    )

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert observed.evidence_method == "rip_route_readback_truncated"
    assert not observed.fresh_evidence


def test_stale_evidence_never_verifies_a_route():
    """Sin ventana fresca no hay evidencia, y sin evidencia no hay ruta."""
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
        if item.device_id == "r1"
    )
    expectation = next(
        item for item in _route_expectations(plan) if item.device_id == "r1"
    )
    ios = _FakeIos({
        (action.device_name, OperationalQueryId.SHOW_IP_ROUTE_RIP): IosCommandResult(
            device_name=action.device_name,
            query_id=OperationalQueryId.SHOW_IP_ROUTE_RIP,
            executed=True, output=_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1,
            session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=False,
        ),
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _s: True, lambda _s, _t: None, ios_executor=ios)
    runtime.apply_actions([action])

    observed = runtime.verify([expectation])[0]

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE


def test_applied_configuration_never_proves_a_learned_route():
    """APPLIED es despacho; una ruta aprendida es otra cosa."""
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
        if item.device_id == "r1"
    )
    expectation = next(
        item for item in _route_expectations(plan) if item.device_id == "r1"
    )
    ios = _FakeIos({
        (action.device_name, OperationalQueryId.SHOW_IP_ROUTE_RIP): IosCommandResult(
            device_name=action.device_name,
            query_id=OperationalQueryId.SHOW_IP_ROUTE_RIP,
            executed=False, failure_reason="prompt_not_ready",
        ),
    })
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _s: True, lambda _s, _t: None, ios_executor=ios)

    mutation = runtime.apply_actions([action])[0]
    observed = runtime.verify([expectation])[0]

    assert mutation.applied
    assert observed.status is not ActionExecutionStatus.VERIFIED


def test_route_verification_is_separate_from_forwarding_verification():
    plan = _compile_university().plan
    kinds = {item.kind for item in plan.verification_expectations}

    assert ControlPlaneVerificationKind.ROUTE_PRESENT in kinds
    assert ControlPlaneVerificationKind.END_TO_END_REACHABILITY not in kinds


# ===================== convergencia acotada de rutas (TD-RUNTIME-007) ======


class _SequenceIos:
    """Devuelve una lectura distinta por intento, y cuenta los intentos."""

    def __init__(self, device_name, outputs):
        self._device_name = device_name
        self._outputs = list(outputs)
        self.calls: list[OperationalQueryId] = []

    def execute(self, device_name, query_id, *, interface=""):
        assert not interface
        self.calls.append(query_id)
        index = min(len(self.calls) - 1, len(self._outputs) - 1)
        value = self._outputs[index]
        if isinstance(value, IosCommandResult):
            return value
        return IosCommandResult(
            device_name=device_name, query_id=query_id, executed=True,
            output=value, session_state=IosSessionState.EXEC_PROMPT_READY,
            fresh_output_observed=True, window_strategy="prefix_delta",
        )


_EMPTY_ROUTE_TABLE = "show ip route rip\nRouter>"


def _converging_case(outputs, *, attempts=4, network="150.1.1.0", prefix_length=27):
    """Verifica una expectativa de ruta con reloj y sleeper deterministas."""
    from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
        ControlPlaneVerificationExpectation,
    )

    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
        if item.device_id == "r1"
    )
    expectation = ControlPlaneVerificationExpectation(
        id="verify/route", kind=ControlPlaneVerificationKind.ROUTE_PRESENT,
        action_id=action.id, device_id="r1",
        required_capability=ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
        expected={"network": network, "prefix_length": prefix_length,
                  "protocol": "ripv2"},
    )
    ios = _SequenceIos(action.device_name, outputs)
    ticks = {"now": 0.0}
    slept: list[float] = []

    def clock():
        return ticks["now"]

    def sleeper(seconds):
        slept.append(seconds)
        ticks["now"] += seconds

    dispatched: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda script: dispatched.append(script) or True,
        lambda _s, _t: None,
        ios_executor=ios,
        route_convergence_timeout_seconds=100.0,
        route_convergence_interval_seconds=5.0,
        route_convergence_attempts=attempts,
        clock=clock, sleeper=sleeper,
    )
    runtime.apply_actions([action])
    dispatched.clear()  # el despacho de configuracion ya ocurrio, antes de verificar
    observed = runtime.verify([expectation])[0]
    return observed, ios, dispatched, slept


def test_a_route_that_appears_later_still_verifies():
    """Primera lectura vacia, la ruta llega despues: converge."""
    observed, ios, _, slept = _converging_case([
        _EMPTY_ROUTE_TABLE,
        _EMPTY_ROUTE_TABLE,
        _PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1,
    ])

    assert observed.status is ActionExecutionStatus.VERIFIED
    assert len(ios.calls) == 3
    assert observed.convergence is not None
    assert observed.convergence.attempts == 3
    assert slept == [5.0, 5.0]


def test_a_route_that_never_appears_fails_after_the_budget():
    observed, ios, _, _ = _converging_case([_EMPTY_ROUTE_TABLE], attempts=4)

    assert observed.status is ActionExecutionStatus.FAILED
    assert len(ios.calls) == 4
    assert observed.convergence.attempts == 4
    assert observed.convergence.last_observable_state == "route_absent"
    assert "did not appear" in observed.message


def test_stale_evidence_aborts_convergence_as_unobservable():
    """Rancio no mejora esperando, y no debe disfrazarse de fallo."""
    stale = IosCommandResult(
        device_name="UCE-R1", query_id=OperationalQueryId.SHOW_IP_ROUTE_RIP,
        executed=True, output=_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1,
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=False,
    )
    observed, ios, _, slept = _converging_case([stale], attempts=4)

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert len(ios.calls) == 1
    assert slept == []


def test_a_truncated_read_aborts_convergence_as_unobservable():
    truncated = IosCommandResult(
        device_name="UCE-R1", query_id=OperationalQueryId.SHOW_IP_ROUTE_RIP,
        executed=True, output="show ip route rip\nR  150.1.1.0/2\n --More-- ",
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=True, truncated_by_pager=True,
    )
    observed, ios, _, slept = _converging_case([truncated], attempts=4)

    assert observed.status is ActionExecutionStatus.UNOBSERVABLE
    assert observed.evidence_method == "rip_route_readback_truncated"
    assert len(ios.calls) == 1
    assert slept == []


def test_convergence_never_redispatches_configuration():
    """Lo unico que se reintenta es la lectura."""
    observed, ios, dispatched, _ = _converging_case(
        [_EMPTY_ROUTE_TABLE], attempts=5,
    )

    assert observed.status is ActionExecutionStatus.FAILED
    assert len(ios.calls) == 5
    assert dispatched == []
    assert all(item is OperationalQueryId.SHOW_IP_ROUTE_RIP for item in ios.calls)


@pytest.mark.parametrize(
    ("network", "prefix_length"),
    [("150.1.1.0", 24), ("150.1.9.0", 27), ("150.1.1.64", 27)],
    ids=["wrong-length", "wrong-network", "wrong-pair"],
)
def test_every_sample_still_requires_the_exact_prefix(network, prefix_length):
    """Converger no relaja la comparacion: la ruta correcta nunca satisface otra."""
    observed, ios, _, _ = _converging_case(
        [_PT_9_0_1_0858_SHOW_IP_ROUTE_RIP_R1], attempts=3,
        network=network, prefix_length=prefix_length,
    )

    assert observed.status is ActionExecutionStatus.FAILED
    # Se agoto el presupuesto releyendo, no acepto una coincidencia parcial.
    assert len(ios.calls) == 3


def test_a_non_rip_row_never_satisfies_a_sample_during_convergence():
    observed, _, _, _ = _converging_case([
        "show ip route rip\nO       150.1.1.0/27 [110/65] via 150.1.1.86, 00:00:26, Serial0/0/0\nRouter>",
    ], attempts=2)

    assert observed.status is ActionExecutionStatus.FAILED


def test_the_convergence_budget_is_validated():
    for kwargs in (
        {"route_convergence_attempts": 0},
        {"route_convergence_attempts": True},
        {"route_convergence_timeout_seconds": -1.0},
        {"route_convergence_interval_seconds": -1.0},
    ):
        with pytest.raises(ValueError):
            PacketTracerEnterpriseControlPlaneRuntime(
                lambda: [], lambda _s: True, lambda _s, _t: None, **kwargs,
            )


# ===================== I. ruta de aplicación del producto ==================


def test_the_product_runtime_dispatches_the_typed_renderer_payload():
    plan = _compile_university().plan
    actions = plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
    sent: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda script: sent.append(script) or True,
        lambda _script, _timeout: None,
    )

    results = runtime.apply_actions(actions)

    assert len(sent) == len(actions) == 3
    assert all(item.applied for item in results)
    assert all("configureIosDevice" in script for script in sent)
    assert all("router rip" in script for script in sent)
    assert all("passive-interface GigabitEthernet0/2" in script for script in sent)
    assert not any("pt_send_raw" in script for script in sent)


def test_a_rip_action_the_renderer_rejects_is_never_dispatched():
    sent: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda script: sent.append(script) or True,
        lambda _script, _timeout: None,
    )

    results = runtime.apply_actions([_action(networks=[])])

    assert sent == []
    assert not results[0].applied
    assert "Typed E9 rendering failed" in results[0].message


def test_rip_compiles_configuration_and_route_expectations_but_no_adjacency():
    """R2-A dejo fuera las rutas a proposito; TD-RUNTIME-005 las incorpora.

    Lo que sigue fuera es la vecindad: RIP no tiene maquina de estados de
    vecino y no se inventa una.
    """
    plan = _compile_university().plan
    kinds = {
        item.kind for item in plan.verification_expectations
        if item.action_id.startswith("cp/ripv2/")
    }

    assert kinds == {
        ControlPlaneVerificationKind.ROUTING_PROCESS,
        ControlPlaneVerificationKind.ROUTE_PRESENT,
    }
    assert ControlPlaneVerificationKind.ROUTING_NEIGHBOR not in kinds
    assert ControlPlaneVerificationKind.END_TO_END_REACHABILITY not in kinds


# ===================== J. aislamiento del generador legacy =================


def test_the_typed_path_never_calls_the_legacy_rip_generator(monkeypatch):
    import src.packet_tracer_mcp.infrastructure.generator.cli_config_generator as legacy

    def explode(*args, **kwargs):
        raise AssertionError("the typed RIPv2 path used the legacy CLI generator")

    # `_router_config` es el que escribe `router rip` en la ruta legacy, y
    # `generate_all_configs` es su unico punto de entrada.
    monkeypatch.setattr(legacy, "generate_all_configs", explode)
    monkeypatch.setattr(legacy, "_router_config", explode)
    plan = _compile_university().plan
    sent: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda script: sent.append(script) or True,
        lambda _script, _timeout: None,
    )

    runtime.apply_actions(
        plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2),
    )

    assert len(sent) == 3
    assert all("router rip" in script for script in sent)


def test_the_typed_renderer_module_does_not_import_the_legacy_generator():
    from src.packet_tracer_mcp.infrastructure.generator import control_plane_renderer

    source = pathlib.Path(control_plane_renderer.__file__).read_text(encoding="utf-8")

    assert "cli_config_generator" not in source
    assert not hasattr(control_plane_renderer, "generate_all_configs")


def test_the_legacy_rip_generator_still_exists_and_is_untouched():
    from src.packet_tracer_mcp.infrastructure.generator import cli_config_generator

    source = pathlib.Path(cli_config_generator.__file__).read_text(encoding="utf-8")

    assert "router rip" in source
    assert hasattr(cli_config_generator, "generate_all_configs")


# ===================== K. compilación de referencia universitaria ==========


def test_three_routers_compile_the_university_routing_intent():
    result = _compile_university()
    actions = {
        item.device_id: item
        for item in result.plan.actions_of_type(
            ControlPlaneActionType.CONFIGURE_RIPV2,
        )
    }
    renderer = PacketTracerControlPlaneRenderer()

    assert result.is_valid, result.issues
    assert set(actions) == {"r1", "r2", "r3"}
    for device_id, action in sorted(actions.items()):
        assert [item.network for item in action.networks] == ["150.1.0.0"]
        payload = renderer.render_action(action).ios_payload
        assert " network 150.1.0.0" in payload
        assert " version 2" in payload
        assert " no auto-summary" in payload
        assert " passive-interface GigabitEthernet0/2" in payload
        assert action.device_name == f"UCE-{device_id.upper()}"
