import json
from pathlib import Path

import pytest

from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor, EigrpQueryClassification,
    EtherChannelQueryClassification, OperationalQueryId, OspfQueryClassification,
    StpQueryClassification,
    TrunkQueryClassification, classify_show_interfaces_trunk,
    classify_show_etherchannel_summary, classify_show_ip_eigrp_neighbors,
    classify_show_ip_ospf_neighbor, classify_show_ip_route_eigrp,
    classify_show_ip_route_ospf, classify_show_spanning_tree,
    extract_terminal_command_window, normalize_terminal_output, parse_show_ephone,
    parse_show_etherchannel_summary, parse_show_interfaces_trunk,
    parse_show_ip_eigrp_neighbors, parse_show_ip_interface_brief,
    parse_show_ip_protocols_eigrp,
    parse_show_ip_ospf_neighbor, parse_show_ip_route_eigrp,
    parse_show_ip_route_ospf, parse_show_spanning_tree,
)


_PT_9_0_1_0858_STP_ROOT = """show spanning-tree
VLAN0001
  Spanning tree enabled protocol rstp
  Root ID    Priority    24577
             Address     0060.5C2C.521E
             This bridge is the root
             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec

  Bridge ID  Priority    24577  (priority 24576 sys-id-ext 1)
             Address     0060.5C2C.521E
             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec
             Aging Time  20

Interface        Role Sts Cost      Prio.Nbr Type
---------------- ---- --- --------- -------- --------------------------------
Fa0/1            Desg FWD 19        128.1    P2p

Switch>"""

_PT_9_0_1_0858_STP_NON_ROOT = """show spanning-tree
VLAN0001
  Spanning tree enabled protocol rstp
  Root ID    Priority    24577
             Address     0060.5C2C.521E
             Cost        19
             Port        1(FastEthernet0/1)
             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec

  Bridge ID  Priority    28673  (priority 28672 sys-id-ext 1)
             Address     0001.9663.8714
             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec
             Aging Time  20

Interface        Role Sts Cost      Prio.Nbr Type
---------------- ---- --- --------- -------- --------------------------------
Fa0/1            Root FWD 19        128.1    P2p

Switch>"""

_PT_9_0_1_0858_STP_EMPTY = """show spanning-tree

No spanning tree instance exists.

Switch>"""

_PT_9_0_1_0858_ETHERCHANNEL_SUMMARY = (
    """show etherchannel summary
Flags:  D - down        P - in port-channel
        I - stand-alone s - suspended
        H - Hot-standby (LACP only)
        R - Layer3      S - Layer2
        U - in use      f - failed to allocate aggregator
        u - unsuitable for bundling
        w - waiting to be aggregated
        d - default port


Number of channel-groups in use: 1
Number of aggregators:           1

Group  Port-channel  Protocol    Ports
------+-------------+-----------+----------------------------------------------

"""
    "1      Po1(SU)           LACP   Fa0/1(P) Fa0/2(P) \n"
    "Switch>"
)

_PT_9_0_1_0858_ETHERCHANNEL_MEMBER_DOWN = (
    _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY.replace("Fa0/2(P)", "Fa0/2(D)")
)

_PT_9_0_1_0858_OSPF_NEIGHBOR_R1 = """show ip ospf neighbor


Neighbor ID     Pri   State           Dead Time   Address         Interface
2.2.2.2           1   FULL/DR         00:00:37    198.18.100.2    GigabitEthernet0/0
Router>"""

_PT_9_0_1_0858_OSPF_NEIGHBOR_R2 = """show ip ospf neighbor


Neighbor ID     Pri   State           Dead Time   Address         Interface
1.1.1.1           1   FULL/BDR        00:00:35    198.18.100.1    GigabitEthernet0/0
Router>"""

_PT_9_0_1_0858_OSPF_ROUTE_R1 = """show ip route ospf
O    198.18.102.0 [110/2] via 198.18.100.2, 00:00:13, GigabitEthernet0/0

Router>"""

_PT_9_0_1_0858_OSPF_ROUTE_R2 = """show ip route ospf
O    198.18.101.0 [110/2] via 198.18.100.1, 00:00:16, GigabitEthernet0/0

Router>"""

_PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY = """show ip eigrp neighbors
IP-EIGRP neighbors for process 90

Router>"""

_PT_9_0_1_0858_EIGRP_ROUTES_EMPTY = """show ip route eigrp


Router>"""

# Captured by the governed CP3-HARD disposable 2x1941 qualification on
# Packet Tracer 9.0.1.0858. These are complete current-command windows.
_PT_9_0_1_0858_EIGRP_NEIGHBORS_R1 = """show ip eigrp neighbors
IP-EIGRP neighbors for process 100
H   Address         Interface      Hold Uptime    SRTT   RTO   Q   Seq
                                   (sec)          (ms)        Cnt  Num
0   198.18.212.2    Gig0/1         13   00:00:01  40     1000  0   3

Router>"""

_PT_9_0_1_0858_EIGRP_ROUTE_R1 = """show ip route eigrp
     198.18.210.0/24 is variably subnetted, 2 subnets, 2 masks
D    198.18.211.0/24 [90/28416] via 198.18.212.2, 00:00:03, GigabitEthernet0/1

Router>"""

_PT_9_0_1_0858_EIGRP_PROTOCOL_R1 = """show ip protocols

Routing Protocol is "eigrp  100 "
  Redistributing: eigrp 100
  EIGRP-IPv4 Protocol for AS(100)
    Metric weight K1=1, K2=0, K3=1, K4=0, K5=0
    Router-ID: 198.18.210.1
  Routing for Networks:
 --More-- """


def test_ios_executor_only_emits_registered_query():
    sent = []
    responses = iter((
        '{"found":true,"booting":false,"terminal":true,"prompt":"Router>","output":""}',
        '{"ok":true,"before":""}',
        '{"found":true,"configuration_channel":true,"output":"Interface IP-Address"}',
        '{"found":true,"configuration_channel":true,"output":"Interface IP-Address"}',
    ))
    result = ControlledIosExecutor(lambda js, _timeout: sent.append(js) or next(responses)).execute("R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF)
    assert result.executed
    assert any('show ip interface brief' in item for item in sent)
    assert 'getCommandLine' in sent[0]


def test_ios_executor_reuses_boot_waiter_before_configuration():
    responses = iter((
        '{"found":true,"booting":true,"terminal":true,"terminal_available":true,"prompt":"","output":"boot"}',
        '{"found":true,"booting":false,"terminal":true,"terminal_available":true,"prompt":"Router>","output":"Router>"}',
    ))
    executor = ControlledIosExecutor(lambda _js, _timeout: next(responses))

    result = executor.wait_until_ready(
        "R1", timeout_seconds=1.0, interval_seconds=0,
    )

    assert result.state.value == "operational_ready"
    assert result.attempts == 2


def test_parse_show_ip_interface_brief_handles_packet_tracer_spacing():
    rows = parse_show_ip_interface_brief("Interface              IP-Address      OK? Method Status                Protocol\r\nGigabitEthernet0/0     198.18.40.1    YES manual up                    up\nGigabitEthernet0/1     unassigned      YES unset  administratively down down")
    assert [(row.interface, row.ip_address, row.status, row.protocol) for row in rows] == [
        ("GigabitEthernet0/0", "198.18.40.1", "up", "up"),
        ("GigabitEthernet0/1", "unassigned", "administratively down", "down"),
    ]


def test_normalize_terminal_output_strips_ansi_only():
    assert normalize_terminal_output("\x1b[31mRouter#\x1b[0m\r\n") == "Router#\n"


def test_exec_prompt_uses_current_prompt_not_setup_text_retained_in_history():
    state = {"prompt": "Router>", "output": "Would you like to enter the initial configuration dialog?\nPress RETURN to get started!\nRouter>"}

    assert ControlledIosExecutor._is_exec_prompt(state)


def test_current_command_window_uses_only_appended_ios_output():
    window = extract_terminal_command_window("Router>\n", "Router>\nshow ip interface brief\nInterface IP-Address\nRouter>", "show ip interface brief")

    assert window.fresh and window.strategy == "prefix_delta"
    assert window.output.startswith("show ip interface brief")


def test_current_command_window_rejects_unchanged_history():
    window = extract_terminal_command_window("Router>show ip interface brief", "Router>show ip interface brief", "show ip interface brief")

    assert not window.fresh


def test_packet_tracer_trunk_empty_fixture_is_a_supported_empty_query():
    fixture = Path(__file__).parent / "fixtures" / "packet_tracer_9_0_1_0858_show_interfaces_trunk_empty.txt"

    output = fixture.read_text(encoding="utf-8")

    assert parse_show_interfaces_trunk(output) == []
    assert classify_show_interfaces_trunk(output) is TrunkQueryClassification.SUPPORTED_EMPTY


def test_packet_tracer_trunk_parser_reads_configured_rows_from_current_window_only():
    current = "show interfaces trunk\nGi0/1 on 802.1q trunking 999\nSwitch>"
    stale = "Gi0/2 on 802.1q trunking 1\nSwitch>"
    window = extract_terminal_command_window(stale, stale + current, "show interfaces trunk")

    rows = parse_show_interfaces_trunk(window.output)

    assert window.fresh and window.strategy == "prefix_delta"
    assert [(row.interface, row.status) for row in rows] == [("Gi0/1", "trunking")]
    assert classify_show_interfaces_trunk(window.output) is TrunkQueryClassification.SUPPORTED_WITH_ROWS


def test_trunk_parser_keeps_allowed_active_and_forwarding_vlan_observations_distinct():
    output = """show interfaces trunk
Port        Mode         Encapsulation  Status        Native vlan
Gig0/1      on           802.1q         trunking      1
Gig0/2      on           802.1q         trunking      1

Port        Vlans allowed on trunk
Gig0/1      10,20,30
Gig0/2      10,30

Port        Vlans allowed and active in management domain
Gig0/1      10,20,30
Gig0/2      10,30

Port        Vlans in spanning tree forwarding state and not pruned
Gig0/1      10,20,30
Gig0/2      10,30
Switch#"""

    rows = {row.interface: row for row in parse_show_interfaces_trunk(output)}

    assert rows["Gig0/1"].allowed_vlans == (10, 20, 30)
    assert rows["Gig0/1"].active_vlans == (10, 20, 30)
    assert rows["Gig0/1"].forwarding_vlans == (10, 20, 30)
    assert rows["Gig0/2"].allowed_vlans == (10, 30)
    assert rows["Gig0/2"].active_vlans == (10, 30)
    assert rows["Gig0/2"].forwarding_vlans == (10, 30)


def test_trunk_parser_does_not_turn_absent_vlan_sections_into_empty_sets():
    rows = parse_show_interfaces_trunk(
        "show interfaces trunk\nGi0/1 on 802.1q trunking 1\nSwitch#"
    )

    assert len(rows) == 1
    assert rows[0].allowed_vlans is None
    assert rows[0].active_vlans is None
    assert rows[0].forwarding_vlans is None


def test_trunk_parser_preserves_an_explicit_none_as_an_observed_empty_set():
    output = """show interfaces trunk
Port Mode Encapsulation Status Native vlan
Gi0/1 on 802.1q trunking 1
Port Vlans allowed on trunk
Gi0/1 none
Port Vlans allowed and active in management domain
Gi0/1 none
Port Vlans in spanning tree forwarding state and not pruned
Gi0/1 none
Switch#"""

    row = parse_show_interfaces_trunk(output)[0]

    assert row.allowed_vlans == ()
    assert row.active_vlans == ()
    assert row.forwarding_vlans == ()


def test_packet_tracer_rpvst_root_output_parses_exact_live_state():
    instances = parse_show_spanning_tree(_PT_9_0_1_0858_STP_ROOT)

    assert classify_show_spanning_tree(
        _PT_9_0_1_0858_STP_ROOT,
    ) is StpQueryClassification.SUPPORTED_WITH_INSTANCES
    assert len(instances) == 1
    instance = instances[0]
    assert (
        instance.vlan_id,
        instance.protocol,
        instance.root_priority,
        instance.root_address,
        instance.root_is_local,
        instance.root_cost,
        instance.root_port,
    ) == (1, "rstp", 24577, "0060.5C2C.521E", True, None, "")
    assert (
        instance.bridge_priority,
        instance.bridge_base_priority,
        instance.bridge_address,
    ) == (24577, 24576, "0060.5C2C.521E")
    assert [
        (
            row.interface,
            row.role,
            row.state,
            row.cost,
            row.priority_number,
            row.link_type,
        )
        for row in instance.interfaces
    ] == [("Fa0/1", "Desg", "FWD", 19, "128.1", "P2p")]


def test_packet_tracer_rpvst_non_root_output_parses_exact_live_state():
    instances = parse_show_spanning_tree(_PT_9_0_1_0858_STP_NON_ROOT)

    assert classify_show_spanning_tree(
        _PT_9_0_1_0858_STP_NON_ROOT,
    ) is StpQueryClassification.SUPPORTED_WITH_INSTANCES
    assert len(instances) == 1
    instance = instances[0]
    assert (
        instance.vlan_id,
        instance.protocol,
        instance.root_priority,
        instance.root_address,
        instance.root_is_local,
        instance.root_cost,
        instance.root_port,
    ) == (
        1,
        "rstp",
        24577,
        "0060.5C2C.521E",
        False,
        19,
        "FastEthernet0/1",
    )
    assert (
        instance.bridge_priority,
        instance.bridge_base_priority,
        instance.bridge_address,
    ) == (28673, 28672, "0001.9663.8714")
    assert [
        (
            row.interface,
            row.role,
            row.state,
            row.cost,
            row.priority_number,
            row.link_type,
        )
        for row in instance.interfaces
    ] == [("Fa0/1", "Root", "FWD", 19, "128.1", "P2p")]


def test_packet_tracer_spanning_tree_empty_output_is_supported_empty():
    assert parse_show_spanning_tree(_PT_9_0_1_0858_STP_EMPTY) == []
    assert classify_show_spanning_tree(
        _PT_9_0_1_0858_STP_EMPTY,
    ) is StpQueryClassification.SUPPORTED_EMPTY


def test_show_spanning_tree_is_a_registered_fresh_query():
    sent = []
    before = "Switch>"
    after = before + "\n" + _PT_9_0_1_0858_STP_ROOT
    responses = iter((
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Switch>",
            "output": before,
        }),
        json.dumps({"ok": True, "before": before}),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
    ))

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or next(responses),
    ).execute("SW1", OperationalQueryId.SHOW_SPANNING_TREE)

    assert result.executed and result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert classify_show_spanning_tree(
        result.output,
    ) is StpQueryClassification.SUPPORTED_WITH_INSTANCES
    assert any('enterCommand("show spanning-tree")' in item for item in sent)


def test_packet_tracer_etherchannel_summary_parses_exact_live_bundle():
    groups = parse_show_etherchannel_summary(
        _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY,
    )

    assert classify_show_etherchannel_summary(
        _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY,
    ) is EtherChannelQueryClassification.SUPPORTED_WITH_GROUPS
    assert len(groups) == 1
    group = groups[0]
    assert (
        group.group_number,
        group.port_channel,
        group.port_channel_flags,
        group.protocol,
    ) == (1, "Po1", "SU", "LACP")
    assert [
        (member.interface, member.flag)
        for member in group.members
    ] == [("Fa0/1", "P"), ("Fa0/2", "P")]


def test_packet_tracer_etherchannel_summary_preserves_member_failure_flag():
    groups = parse_show_etherchannel_summary(
        _PT_9_0_1_0858_ETHERCHANNEL_MEMBER_DOWN,
    )

    assert classify_show_etherchannel_summary(
        _PT_9_0_1_0858_ETHERCHANNEL_MEMBER_DOWN,
    ) is EtherChannelQueryClassification.SUPPORTED_WITH_GROUPS
    assert len(groups) == 1
    assert [
        (member.interface, member.flag)
        for member in groups[0].members
    ] == [("Fa0/1", "P"), ("Fa0/2", "D")]


def test_show_etherchannel_summary_is_a_registered_fresh_query():
    sent = []
    before = "Switch>"
    after = before + "\n" + _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY
    responses = iter((
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Switch>",
            "output": before,
        }),
        json.dumps({"ok": True, "before": before}),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
    ))

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or next(responses),
    ).execute("SW1", OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY)

    assert result.executed and result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert classify_show_etherchannel_summary(
        result.output,
    ) is EtherChannelQueryClassification.SUPPORTED_WITH_GROUPS
    assert any(
        'enterCommand("show etherchannel summary")' in item
        for item in sent
    )


def test_packet_tracer_ospf_neighbor_parses_both_exact_live_rows():
    r1 = parse_show_ip_ospf_neighbor(_PT_9_0_1_0858_OSPF_NEIGHBOR_R1)
    r2 = parse_show_ip_ospf_neighbor(_PT_9_0_1_0858_OSPF_NEIGHBOR_R2)

    assert classify_show_ip_ospf_neighbor(
        _PT_9_0_1_0858_OSPF_NEIGHBOR_R1,
    ) is OspfQueryClassification.SUPPORTED_WITH_ROWS
    assert [
        (
            row.neighbor_id,
            row.priority,
            row.state,
            row.role,
            row.dead_time,
            row.address,
            row.interface,
        )
        for row in r1 + r2
    ] == [
        (
            "2.2.2.2", 1, "FULL", "DR", "00:00:37",
            "198.18.100.2", "GigabitEthernet0/0",
        ),
        (
            "1.1.1.1", 1, "FULL", "BDR", "00:00:35",
            "198.18.100.1", "GigabitEthernet0/0",
        ),
    ]


def test_packet_tracer_ospf_routes_parse_both_exact_live_rows():
    r1 = parse_show_ip_route_ospf(_PT_9_0_1_0858_OSPF_ROUTE_R1)
    r2 = parse_show_ip_route_ospf(_PT_9_0_1_0858_OSPF_ROUTE_R2)

    assert classify_show_ip_route_ospf(
        _PT_9_0_1_0858_OSPF_ROUTE_R1,
    ) is OspfQueryClassification.SUPPORTED_WITH_ROWS
    assert [
        (
            row.code,
            row.prefix,
            row.administrative_distance,
            row.metric,
            row.next_hop,
            row.age,
            row.interface,
        )
        for row in r1 + r2
    ] == [
        (
            "O", "198.18.102.0", 110, 2, "198.18.100.2",
            "00:00:13", "GigabitEthernet0/0",
        ),
        (
            "O", "198.18.101.0", 110, 2, "198.18.100.1",
            "00:00:16", "GigabitEthernet0/0",
        ),
    ]


def test_ospf_route_parser_preserves_an_explicit_prefix_length_when_present():
    output = _PT_9_0_1_0858_OSPF_ROUTE_R1.replace(
        "198.18.102.0", "198.18.102.0/24",
    )

    rows = parse_show_ip_route_ospf(output)

    assert len(rows) == 1
    assert rows[0].prefix == "198.18.102.0"
    assert rows[0].prefix_length == 24
    assert parse_show_ip_route_ospf(
        _PT_9_0_1_0858_OSPF_ROUTE_R1,
    )[0].prefix_length is None


def test_show_ip_ospf_neighbor_is_a_registered_fresh_query():
    sent = []
    before = "Router>"
    after = before + "\n" + _PT_9_0_1_0858_OSPF_NEIGHBOR_R1
    responses = iter((
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Router>",
            "output": before,
        }),
        json.dumps({"ok": True, "before": before}),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
    ))

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or next(responses),
    ).execute("R1", OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR)

    assert result.executed and result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert [row.neighbor_id for row in parse_show_ip_ospf_neighbor(result.output)] == [
        "2.2.2.2",
    ]
    assert any(
        'enterCommand("show ip ospf neighbor")' in item for item in sent
    )


def test_show_ip_route_ospf_is_a_registered_fresh_query():
    sent = []
    before = "Router>"
    after = before + "\n" + _PT_9_0_1_0858_OSPF_ROUTE_R1
    responses = iter((
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Router>",
            "output": before,
        }),
        json.dumps({"ok": True, "before": before}),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
    ))

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or next(responses),
    ).execute("R1", OperationalQueryId.SHOW_IP_ROUTE_OSPF)

    assert result.executed and result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert [row.prefix for row in parse_show_ip_route_ospf(result.output)] == [
        "198.18.102.0",
    ]
    assert any('enterCommand("show ip route ospf")' in item for item in sent)


def test_ospf_neighbor_parser_excludes_stale_previous_query_window():
    before = _PT_9_0_1_0858_OSPF_NEIGHBOR_R1
    after = before + "\n" + _PT_9_0_1_0858_OSPF_NEIGHBOR_R2

    window = extract_terminal_command_window(
        before, after, "show ip ospf neighbor",
    )

    assert window.fresh and window.strategy == "prefix_delta"
    assert [
        row.neighbor_id for row in parse_show_ip_ospf_neighbor(window.output)
    ] == ["1.1.1.1"]


def test_packet_tracer_eigrp_live_outputs_are_supported_empty():
    assert parse_show_ip_eigrp_neighbors(
        _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY,
    ) == []
    assert classify_show_ip_eigrp_neighbors(
        _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY,
    ) is EigrpQueryClassification.SUPPORTED_EMPTY


def test_packet_tracer_eigrp_live_rows_are_parsed_semantically():
    neighbors = parse_show_ip_eigrp_neighbors(
        _PT_9_0_1_0858_EIGRP_NEIGHBORS_R1,
    )
    routes = parse_show_ip_route_eigrp(_PT_9_0_1_0858_EIGRP_ROUTE_R1)
    process = parse_show_ip_protocols_eigrp(_PT_9_0_1_0858_EIGRP_PROTOCOL_R1)

    assert len(neighbors) == 1
    assert neighbors[0].address == "198.18.212.2"
    assert neighbors[0].interface == "Gig0/1"
    assert neighbors[0].queue_count == 0
    assert classify_show_ip_eigrp_neighbors(
        _PT_9_0_1_0858_EIGRP_NEIGHBORS_R1,
        expected_as_number=100,
    ) is EigrpQueryClassification.SUPPORTED_WITH_ROWS

    assert len(routes) == 1
    assert routes[0].code == "D"
    assert routes[0].prefix == "198.18.211.0"
    assert routes[0].prefix_length == 24
    assert routes[0].next_hop == "198.18.212.2"
    assert classify_show_ip_route_eigrp(
        _PT_9_0_1_0858_EIGRP_ROUTE_R1,
    ) is EigrpQueryClassification.SUPPORTED_WITH_ROWS

    assert process is not None
    assert process.as_number == 100
    assert process.router_id == "198.18.210.1"
    assert parse_show_ip_route_eigrp(
        _PT_9_0_1_0858_EIGRP_ROUTES_EMPTY,
    ) == []
    assert classify_show_ip_route_eigrp(
        _PT_9_0_1_0858_EIGRP_ROUTES_EMPTY,
    ) is EigrpQueryClassification.SUPPORTED_EMPTY


def test_eigrp_empty_neighbor_header_is_bound_to_the_expected_process_as():
    assert classify_show_ip_eigrp_neighbors(
        _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY,
        expected_as_number=90,
    ) is EigrpQueryClassification.SUPPORTED_EMPTY
    assert classify_show_ip_eigrp_neighbors(
        _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY,
        expected_as_number=100,
    ) is EigrpQueryClassification.PROCESS_MISMATCH


def test_eigrp_empty_classifiers_accept_real_device_prompts_not_only_router():
    neighbors = _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY.replace(
        "Router>", "HQ-R1#",
    )
    routes = _PT_9_0_1_0858_EIGRP_ROUTES_EMPTY.replace(
        "Router>", "HQ-R1#",
    )

    assert classify_show_ip_eigrp_neighbors(
        neighbors, expected_as_number=90,
    ) is EigrpQueryClassification.SUPPORTED_EMPTY
    assert classify_show_ip_route_eigrp(
        routes,
    ) is EigrpQueryClassification.SUPPORTED_EMPTY


@pytest.mark.parametrize("protocol", ("PAgP", "STATIC", "-"))
def test_unobserved_etherchannel_protocol_rows_are_not_parser_backed(protocol):
    output = _PT_9_0_1_0858_ETHERCHANNEL_SUMMARY.replace("LACP", protocol)

    assert parse_show_etherchannel_summary(output) == []
    assert classify_show_etherchannel_summary(
        output,
    ) is EtherChannelQueryClassification.PARSER_UNAVAILABLE


def test_show_ip_eigrp_neighbors_is_a_registered_fresh_query():
    sent = []
    before = "Router>"
    after = before + "\n" + _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY
    responses = iter((
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Router>",
            "output": before,
        }),
        json.dumps({"ok": True, "before": before}),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
    ))

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or next(responses),
    ).execute("R1", OperationalQueryId.SHOW_IP_EIGRP_NEIGHBORS)

    assert result.executed and result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert classify_show_ip_eigrp_neighbors(
        result.output,
    ) is EigrpQueryClassification.SUPPORTED_EMPTY
    assert any(
        'enterCommand("show ip eigrp neighbors")' in item for item in sent
    )


def test_show_ip_route_eigrp_is_a_registered_fresh_query():
    sent = []
    before = "Router>"
    after = before + "\n" + _PT_9_0_1_0858_EIGRP_ROUTES_EMPTY
    responses = iter((
        json.dumps({
            "found": True,
            "booting": False,
            "terminal": True,
            "prompt": "Router>",
            "output": before,
        }),
        json.dumps({"ok": True, "before": before}),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
        json.dumps({
            "found": True,
            "configuration_channel": True,
            "output": after,
        }),
    ))

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or next(responses),
    ).execute("R1", OperationalQueryId.SHOW_IP_ROUTE_EIGRP)

    assert result.executed and result.fresh_output_observed
    assert result.window_strategy == "prefix_delta"
    assert classify_show_ip_route_eigrp(
        result.output,
    ) is EigrpQueryClassification.SUPPORTED_EMPTY
    assert any('enterCommand("show ip route eigrp")' in item for item in sent)


def test_eigrp_empty_classifier_excludes_stale_previous_query_window():
    before = _PT_9_0_1_0858_EIGRP_NEIGHBORS_EMPTY
    after = before + "\n" + _PT_9_0_1_0858_EIGRP_ROUTES_EMPTY

    window = extract_terminal_command_window(
        before, after, "show ip route eigrp",
    )

    assert window.fresh and window.strategy == "prefix_delta"
    assert classify_show_ip_route_eigrp(
        window.output,
    ) is EigrpQueryClassification.SUPPORTED_EMPTY
    assert classify_show_ip_eigrp_neighbors(
        window.output,
    ) is EigrpQueryClassification.PARSER_UNAVAILABLE


def test_parse_show_ephone_reads_registration_identity_and_idle_state():
    output = """show ephone

ephone-1 Mac:00D0.9709.202C TCP socket:[1] activeLine:0 REGISTERED in SCCP ver 12 and Server in ver 8
mediaActive:0 offhook:0 ringing:0
IP:198.18.170.3 1025 7960 keepalive 43 max_line 2
 button 1: dn 1 number 3101 CH1 IDLE

ephone-2 Mac:000D.BD9E.153C TCP socket:[1] activeLine:1 UNREGISTERED
IP:0.0.0.0 0 7960 keepalive 43 max_line 2
 button 1: dn 2 number 3102 CH1 DOWN
Router#"""

    rows = parse_show_ephone(output)

    assert [row.extension for row in rows] == ["3101", "3102"]
    assert rows[0].registered and rows[0].ip_address == "198.18.170.3"
    assert rows[0].line_state == "IDLE"
    assert not rows[1].registered and rows[1].line_state == "DOWN"


def test_privileged_ephone_query_enters_enable_and_restores_user_exec():
    sent = []
    output = (
        "Router#show ephone\n"
        "ephone-1 Mac:0011.2233.4455 REGISTERED in SCCP ver 12\n"
        "IP:198.18.170.2 1025 7960\n"
        " button 1: dn 1 number 3101 CH1 IDLE\nRouter#"
    )
    responses = iter((
        '{"found":true,"booting":false,"terminal":true,"prompt":"Router>","output":"Router>"}',
        '{"found":true,"booting":false,"terminal":true,"prompt":"Router>","output":"Router>"}',
        '{"ok":true}',
        '{"found":true,"booting":false,"terminal":true,"prompt":"Router#","output":"Router#"}',
        '{"ok":true,"before":"Router#"}',
        '{"found":true,"configuration_channel":true,"output":' + repr(output).replace("'", '"') + '}',
        '{"found":true,"configuration_channel":true,"output":' + repr(output).replace("'", '"') + '}',
        '{"ok":true}',
    ))

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or next(responses),
    ).execute("R1", OperationalQueryId.SHOW_EPHONE)

    assert result.executed and result.fresh_output_observed
    assert any('enterCommand("enable")' in item for item in sent)
    assert any('enterCommand("show ephone")' in item for item in sent)
    assert any('enterCommand("disable")' in item for item in sent)


def test_typed_interface_query_rejects_cli_injection_before_bridge_call():
    sent = []

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or None,
    ).execute(
        "R1",
        OperationalQueryId.SHOW_IP_INTERFACE,
        interface="GigabitEthernet0/0\nconfigure terminal",
    )

    assert not result.executed
    assert "valid interface name" in result.failure_reason
    assert sent == []


def test_paginated_registered_query_captures_first_page_and_cancels_pager():
    sent = []
    before = "Router#"
    output = (
        before
        + "show ip interface GigabitEthernet0/0\n"
        + "GigabitEthernet0/0 is up, line protocol is down\n"
        + "  Inbound  access list is 101\n--More--"
    )
    responses = iter((
        json.dumps({"found": True, "booting": False, "terminal": True,
                    "prompt": "Router#", "output": before}),
        json.dumps({"found": True, "booting": False, "terminal": True,
                    "prompt": "Router#", "output": before}),
        json.dumps({"ok": True, "before": before}),
        json.dumps({"found": True, "configuration_channel": True,
                    "output": output}),
        json.dumps({"found": True, "configuration_channel": True,
                    "output": output}),
        '{"ok":true}',
        json.dumps({"found": True, "booting": False, "terminal": True,
                    "prompt": "Router#", "output": output + "\n^C\nRouter#"}),
    ))

    result = ControlledIosExecutor(
        lambda js, _timeout: sent.append(js) or next(responses),
    ).execute(
        "R1", OperationalQueryId.SHOW_IP_INTERFACE,
        interface="GigabitEthernet0/0",
    )

    assert result.executed and result.truncated_by_pager
    assert result.window_strategy == "prefix_delta"
    assert any("String.fromCharCode(3)" in item for item in sent)
    assert any(
        'enterCommand("show ip interface GigabitEthernet0/0")' in item
        for item in sent
    )


def test_paginated_query_is_isolated_before_the_next_registered_query():
    class AsynchronousPagerTerminal:
        def __init__(self):
            self.output = "Router#"
            self.cancel_pending = False
            self.cancel_polls = 0
            self.contaminated = False
            self.sent = []

        def __call__(self, js, _timeout):
            self.sent.append(js)
            if "String.fromCharCode(3)" in js:
                self.cancel_pending = True
                return '{"ok":true}'
            if "terminal_kind:'ios_command_line'" in js:
                current = self.output
                if self.cancel_pending:
                    self.cancel_polls += 1
                    if self.cancel_polls >= 2:
                        self.output += "\n^C\nRouter#"
                        self.cancel_pending = False
                return json.dumps({
                    "found": True,
                    "booting": False,
                    "terminal": True,
                    "prompt": "Router#",
                    "output": current,
                })
            if "var before=String(t.getOutput())" in js:
                before = self.output
                if self.output.rstrip().endswith("--More--"):
                    self.contaminated = True
                    self.output += "\n[pager consumed registered query]"
                elif 'enterCommand("show ip interface brief")' in js:
                    self.output += (
                        "show ip interface brief\n"
                        "Interface IP-Address OK? Method Status Protocol\n"
                        "GigabitEthernet0/0 192.0.2.1 YES manual up up\n"
                        "--More--"
                    )
                else:
                    assert 'enterCommand("show interfaces trunk")' in js
                    self.output += (
                        "show interfaces trunk\n"
                        "Gi0/1 on 802.1q trunking 1\nRouter#"
                    )
                return json.dumps({"ok": True, "before": before})
            if "configuration_channel" in js:
                return json.dumps({
                    "found": True,
                    "configuration_channel": True,
                    "output": self.output,
                })
            raise AssertionError(f"Unexpected terminal interaction: {js}")

    terminal = AsynchronousPagerTerminal()
    executor = ControlledIosExecutor(terminal)

    first = executor.execute(
        "R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
    )
    second = executor.execute(
        "R1", OperationalQueryId.SHOW_INTERFACES_TRUNK,
    )

    assert first.executed and first.truncated_by_pager
    assert second.executed and second.fresh_output_observed
    assert "show interfaces trunk" in second.output
    assert not terminal.contaminated
    assert not any("terminal length 0" in item for item in terminal.sent)


def test_unconfirmed_pager_cancellation_fails_closed_and_keeps_truncation():
    before = "Router#"
    output = before + "show ip interface brief\nGi0/0 192.0.2.1\n--More--"
    responses = iter((
        json.dumps({"found": True, "booting": False, "terminal": True,
                    "prompt": "Router#", "output": before}),
        json.dumps({"ok": True, "before": before}),
        json.dumps({"found": True, "configuration_channel": True,
                    "output": output}),
        json.dumps({"found": True, "configuration_channel": True,
                    "output": output}),
        '{"ok":true}',
    ))
    executor = ControlledIosExecutor(lambda _js, _timeout: next(responses))
    executor._wait_for = lambda _name, _predicate: False

    result = executor.execute(
        "R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
    )

    assert not result.executed
    assert result.truncated_by_pager
    assert "pager cancellation" in result.failure_reason.casefold()
