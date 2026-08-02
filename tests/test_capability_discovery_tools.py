"""Guardas estructurales de las dos tools delgadas de E3.5."""

from pathlib import Path


SOURCE = Path("src/packet_tracer_mcp/adapters/mcp/tool_registry.py").read_text(encoding="utf-8")


def test_capability_discovery_tools_delegate_to_application_service():
    assert "def pt_probe_capabilities(" in SOURCE
    assert "def pt_capability_report(" in SOURCE
    assert "service = _capability_discovery()" in SOURCE
    assert "lambda: service.run(request)" in SOURCE
    assert "def _capability_preflight()" in SOURCE
    assert "_capability_preflight().execute_if_ready(" in SOURCE


def test_capability_probe_tool_does_not_accept_raw_javascript_or_ios_commands():
    start = SOURCE.index("def pt_probe_capabilities(")
    end = SOURCE.index("def pt_capability_report(", start)
    signature_and_body = SOURCE[start:end]
    assert "js_code" not in signature_and_body
    assert "ios_commands" not in signature_and_body


def test_capability_probe_cannot_run_before_the_e36_preflight():
    start = SOURCE.index("def pt_probe_capabilities(")
    end = SOURCE.index("def pt_capability_report(", start)
    body = SOURCE[start:end]
    assert body.index("_capability_preflight().execute_if_ready(") < body.index("service.run(request)")
