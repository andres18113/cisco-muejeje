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

import pytest

from src.packet_tracer_mcp.infrastructure.persistence import capability_snapshot_store


@pytest.fixture(scope="session", autouse=True)
def _isolate_default_capability_store(tmp_path_factory):
    patcher = pytest.MonkeyPatch()
    patcher.setattr(
        capability_snapshot_store,
        "DEFAULT_BASE_DIR",
        tmp_path_factory.mktemp("default-capability-store"),
    )
    yield
    patcher.undo()
