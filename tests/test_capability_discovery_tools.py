"""Guardas estructurales de las dos tools delgadas de E3.5."""

from pathlib import Path


SOURCE = Path("src/packet_tracer_mcp/adapters/mcp/tool_registry.py").read_text(encoding="utf-8")


def test_capability_discovery_tools_delegate_to_application_service():
    assert "def pt_probe_capabilities(" in SOURCE
    assert "def pt_capability_report(" in SOURCE
    assert "service = _capability_discovery()" in SOURCE
    assert "snapshot, cached = service.run(ProbeRequest(" in SOURCE


def test_capability_probe_tool_does_not_accept_raw_javascript_or_ios_commands():
    start = SOURCE.index("def pt_probe_capabilities(")
    end = SOURCE.index("def pt_capability_report(", start)
    signature_and_body = SOURCE[start:end]
    assert "js_code" not in signature_and_body
    assert "ios_commands" not in signature_and_body
