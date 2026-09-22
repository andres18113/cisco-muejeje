"""The registered IOS enum migration preserves the existing wire behavior."""

from __future__ import annotations

import json

from packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    IosSessionState,
    OperationalQueryId,
)


def test_registered_query_keeps_value_json_and_legacy_str():
    """Formatting cleanup does not change query identity or serialization."""
    member = OperationalQueryId.SHOW_SPANNING_TREE
    assert isinstance(member, str)
    assert member.value == "show_spanning_tree"
    assert str(member) == "OperationalQueryId.SHOW_SPANNING_TREE"
    assert json.dumps(member) == '"show_spanning_tree"'
    assert OperationalQueryId("show_spanning_tree") is member
    assert str(IosSessionState.EXEC_PROMPT_READY) == "IosSessionState.EXEC_PROMPT_READY"
