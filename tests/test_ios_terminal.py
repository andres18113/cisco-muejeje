from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor, OperationalQueryId, extract_terminal_command_window, normalize_terminal_output, parse_show_ip_interface_brief,
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
