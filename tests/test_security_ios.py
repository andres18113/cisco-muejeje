"""E8 parsers use captured Packet Tracer 9.0.1 security output."""

from pathlib import Path

from src.packet_tracer_mcp.infrastructure.execution.security_ios import (
    parse_show_access_lists,
    parse_show_ip_arp_inspection,
    parse_show_ip_dhcp_snooping,
    parse_show_ip_interface_security,
    parse_show_ip_nat_statistics,
    parse_show_ip_nat_translations,
    parse_show_port_security_interface,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_acl_and_interface_attachment_parse_real_pt_output():
    rows = parse_show_access_lists(_fixture(
        "packet_tracer_9_0_1_0858_show_access_lists.txt",
    ))
    attachment = parse_show_ip_interface_security(_fixture(
        "packet_tracer_9_0_1_0858_show_ip_interface_acl.txt",
    ))

    assert [(item.sequence, item.decision, item.protocol) for item in rows] == [
        (10, "deny", "icmp"), (20, "permit", "ip"),
    ]
    assert attachment is not None
    assert attachment.interface == "GigabitEthernet0/0"
    assert attachment.inbound_acl == "101"
    assert attachment.outbound_acl == ""


def test_nat_empty_translation_table_and_statistics_are_distinct_evidence():
    translations = parse_show_ip_nat_translations(_fixture(
        "packet_tracer_9_0_1_0858_show_ip_nat_translations_empty.txt",
    ))
    statistics = parse_show_ip_nat_statistics(_fixture(
        "packet_tracer_9_0_1_0858_show_ip_nat_statistics.txt",
    ))

    assert translations == []
    assert statistics is not None
    assert statistics.total_translations == 0
    assert statistics.inside_interfaces == ["GigabitEthernet0/0"]
    assert statistics.outside_interfaces == ["GigabitEthernet0/1"]


def test_port_security_parser_reads_exact_pt_field_names():
    state = parse_show_port_security_interface(_fixture(
        "packet_tracer_9_0_1_0858_show_port_security_interface.txt",
    ))

    assert state is not None and state.enabled
    assert state.interface == "FastEthernet0/1"
    assert state.violation_mode == "restrict"
    assert state.maximum_macs == 1
    assert state.violation_count == 0


def test_snooping_and_dai_parsers_preserve_observable_scope():
    snooping = parse_show_ip_dhcp_snooping(_fixture(
        "packet_tracer_9_0_1_0858_show_ip_dhcp_snooping.txt",
    ))
    dai = parse_show_ip_arp_inspection(_fixture(
        "packet_tracer_9_0_1_0858_show_ip_arp_inspection.txt",
    ))

    assert snooping is not None and snooping.enabled
    assert snooping.vlan_ids == [10]
    assert snooping.trusted_interfaces == ["GigabitEthernet0/1"]
    assert dai is not None
    assert dai.enabled_vlans == [10]
    assert dai.active_vlans == [10]


def test_a_standard_list_is_parsed_and_never_attributed_to_the_previous_list():
    """Captura real: un router con una ACL de filtrado y la ACL NAT a la vez.

    El parser sólo reconocía cabeceras `Extended IP access list`. Ante una
    `Standard IP access list` no cambiaba `acl_name`, así que la ACE estándar
    quedaba atribuida a la ACL EXTENDIDA anterior, con su primer octeto leído
    como protocolo. `_observe_acl` filtra por `acl_name`, de modo que una ACL de
    filtrado cuyas reglas hubieran desaparecido podía seguir verificando desde
    una ACE que pertenece a la ACL de traducción NAT.

    Capturado en vivo sobre PT `9.0.1.0858` / `1941` durante la reproducción de
    replay de TD-SECURITY-001.
    """
    rows = parse_show_access_lists(_fixture(
        "packet_tracer_9_0_1_0858_show_access_lists_mixed.txt",
    ))

    assert [
        (item.acl_name, item.sequence, item.decision, item.protocol, item.expression)
        for item in rows
    ] == [
        ("181", 10, "permit", "ip", "198.18.160.0 0.0.0.255 198.18.161.0 0.0.0.255"),
        ("82", 10, "permit", "", "198.18.160.0 0.0.0.255"),
    ]


def test_an_unrecognised_header_never_leaks_the_previous_list_name():
    rows = parse_show_access_lists(
        "Extended IP access list 181\n"
        "    10 permit ip any any\n"
        "IPv6 access list SOMETHING\n"
        "    20 permit 198.18.160.0 0.0.0.255\n"
    )

    assert [item.acl_name for item in rows] == ["181"]
