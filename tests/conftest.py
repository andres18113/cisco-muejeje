"""Suite-wide isolation from machine state.

`CapabilitySnapshotStore()` defaults to `data/capabilities`, relative to the
working directory. That directory is gitignored: it is machine state, not
repository state. On one developer's box it holds 72 runtime snapshots — 344
capability results across 9 models — and in CI it does not exist at all, so a
test that reads it composes different evidence from the same source SHA.

The productive composition root builds that default store itself
(`packet_tracer_enterprise_capability_adapter`), so a test cannot avoid it by
being careful; it has to be redirected. This fixture points the default at an
empty per-session temporary directory. Tests that want snapshots inject their
own store, as they already do.

Session-scoped on purpose: module- and session-scoped fixtures elsewhere build
capability stores during their own setup, which runs before any function-scoped
fixture could patch anything.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.cp_live_data_integrity import (
    assert_protected_paths_unchanged,
    capture_protected_paths,
    cp_live_workspace_protected_paths,
    isolated_subprocess_environment,
)
from src.packet_tracer_mcp.infrastructure.execution.bridge_token import token_path
from src.packet_tracer_mcp.infrastructure.persistence import capability_snapshot_store


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _isolate_machine_and_repository_state(tmp_path_factory):
    protected = capture_protected_paths((*cp_live_workspace_protected_paths(ROOT), token_path()))
    isolated = tmp_path_factory.mktemp("cp-live-session-state")
    environment = isolated_subprocess_environment(isolated)
    patcher = pytest.MonkeyPatch()
    for name in (
        "LOCALAPPDATA", "APPDATA", "XDG_STATE_HOME", "TEMP", "TMP", "TMPDIR",
        "PT_MCP_BRIDGE_TOKEN", "PYTHONNOUSERSITE",
    ):
        patcher.setenv(name, environment[name])
    patcher.delenv("PT_MCP_GOVERNED_ROOT", raising=False)
    patcher.setenv("PT_MCP_TEST_STATE_ROOT", str(isolated))
    patcher.setattr(
        capability_snapshot_store,
        "DEFAULT_BASE_DIR",
        isolated / "capability-store",
    )
    try:
        yield
    finally:
        try:
            assert_protected_paths_unchanged(protected)
        finally:
            patcher.undo()
