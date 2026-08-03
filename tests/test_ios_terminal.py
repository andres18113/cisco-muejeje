from pathlib import Path

from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor, OperationalQueryId, TrunkQueryClassification, classify_show_interfaces_trunk,
    extract_terminal_command_window, normalize_terminal_output, parse_show_interfaces_trunk, parse_show_ip_interface_brief,
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
