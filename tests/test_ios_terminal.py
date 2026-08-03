import json
from pathlib import Path

from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor, OperationalQueryId, TrunkQueryClassification, classify_show_interfaces_trunk,
    extract_terminal_command_window, normalize_terminal_output, parse_show_ephone,
    parse_show_interfaces_trunk, parse_show_ip_interface_brief,
)


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
