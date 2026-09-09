"""Suite-wide isolation from machine state.

`CapabilitySnapshotStore()` defaults to `data/capabilities`, relative to the
working directory. That directory is gitignored: it is machine state, not
repository state. On one developer's box it holds 72 runtime snapshots — 344
capability results across 9 models — and in CI it does not exist at all, so a
test that reads it composes different evidence from the same source SHA.

The productive composition root builds that default store itself
(`packet_tracer_enterprise_capability_adapter`), so a test cannot avoid it by
being careful; it has to be redirected. The early pytest hooks below redirect
it before test-module collection and keep a byte/metadata sentinel until pytest
is fully unconfigured. Tests that want snapshots inject their own store.
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

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
_ISOLATION_ATTRIBUTE = "_cp_live_early_isolation"


def pytest_configure(config) -> None:
    """Capture and redirect state before pytest imports any test module."""
    if hasattr(config, _ISOLATION_ATTRIBUTE):
        return
    extra = os.environ.get("PT_MCP_TEST_EXTRA_PROTECTED_PATH", "").strip()
    protected_paths = [*cp_live_workspace_protected_paths(ROOT), token_path()]
    if extra:
        protected_paths.append(Path(extra))
    protected = capture_protected_paths(tuple(protected_paths))
    temporary = TemporaryDirectory(prefix="cp-live-pytest-")
    isolated = Path(temporary.name)
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
    setattr(config, _ISOLATION_ATTRIBUTE, (protected, patcher, temporary))


def pytest_unconfigure(config) -> None:
    state = getattr(config, _ISOLATION_ATTRIBUTE, None)
    if state is None:
        return
    protected, patcher, temporary = state
    try:
        assert_protected_paths_unchanged(protected)
    finally:
        try:
            patcher.undo()
        finally:
            temporary.cleanup()
