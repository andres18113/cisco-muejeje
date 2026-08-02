from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor, OperationalQueryId, normalize_terminal_output, parse_show_ip_interface_brief,
)


def test_ios_executor_only_emits_registered_query():
    sent = []
    responses = iter((
        '{"ok":true,"before":0}',
        '{"found":true,"configuration_channel":true,"output":"Interface IP-Address"}',
        '{"found":true,"configuration_channel":true,"output":"Interface IP-Address"}',
    ))
    result = ControlledIosExecutor(lambda js, _timeout: sent.append(js) or next(responses)).execute("R1", OperationalQueryId.SHOW_IP_INTERFACE_BRIEF)
    assert result.executed
    assert 'show ip interface brief' in sent[0]
    assert 'getCommandLine' in sent[0]


def test_parse_show_ip_interface_brief_handles_packet_tracer_spacing():
    rows = parse_show_ip_interface_brief("Interface              IP-Address      OK? Method Status                Protocol\r\nGigabitEthernet0/0     198.18.40.1    YES manual up                    up\nGigabitEthernet0/1     unassigned      YES unset  administratively down down")
    assert [(row.interface, row.ip_address, row.status, row.protocol) for row in rows] == [
        ("GigabitEthernet0/0", "198.18.40.1", "up", "up"),
        ("GigabitEthernet0/1", "unassigned", "administratively down", "down"),
    ]


def test_normalize_terminal_output_strips_ansi_only():
    assert normalize_terminal_output("\x1b[31mRouter#\x1b[0m\r\n") == "Router#\n"
