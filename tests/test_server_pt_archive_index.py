"""One campaign hash index checks every immutable source byte."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)

ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def test_index_catches_changed_full_plan_bytes(tmp_path: Path):
    """A matching typed bundle alone cannot conceal a changed source file."""
    store = ServerPtCommissioningStore(tmp_path)
    store.save_bundle(
        ATTEMPT,
        prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT),
    )

    index_path = store.refresh_index()
    assert index_path.is_file()
    assert store.verify_index() == ()
    topology = store.topology_path_for(ATTEMPT)
    topology.write_bytes(topology.read_bytes() + b" ")
    assert "archive_bytes_changed" in store.verify_index()
    with pytest.raises(ValueError, match="prior archive bytes changed"):
        store.refresh_index()


def test_index_checks_external_product_source_bytes(tmp_path: Path):
    """A service or envelope source cannot be silently rebaselined by a new phase."""
    store = ServerPtCommissioningStore(tmp_path)
    store.save_bundle(
        ATTEMPT, prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT)
    )
    external = tmp_path / "data" / "acceptance" / "cold-http" / "terminal.json"
    external.parent.mkdir(parents=True)
    external.write_bytes(b'{"terminal":"original"}')
    store.register_external_source(ATTEMPT, "terminal", external)
    store.refresh_index()
    assert store.verify_index() == ()

    external.write_bytes(b'{"terminal":"changed"}')
    assert "archive_bytes_changed" in store.verify_index()


def test_stopped_current_projection_cannot_become_a_ready_phase(tmp_path: Path):
    """A stored ready row cannot bypass a later archive validation stop."""
    store = ServerPtCommissioningStore(tmp_path)
    store.save_bundle(
        ATTEMPT,
        prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT),
    )
    store.save_phase_status(ATTEMPT, "setup", {"outcome": "ready"})
    store.update_current_status(
        {"phase": "setup", "outcome": "stopped", "attempt_id": ATTEMPT}
    )
    store.refresh_index()

    with pytest.raises(ValueError, match="archived phase is not ready"):
        store.require_archived_phase(ATTEMPT, "setup", "ready")


def test_resealed_bundle_cannot_replace_the_exact_setup_input(tmp_path: Path):
    """A coherent new sidecar hash cannot rewrite what E4 consumed."""
    store = ServerPtCommissioningStore(tmp_path)
    store.save_bundle(
        ATTEMPT, prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT)
    )
    path = store.bundle_path_for(ATTEMPT)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    data = json.loads(path.read_bytes())
    data["configuration_semantic_hash"] = "f" * 64
    changed = (json.dumps(data) + "\n").encode()
    path.write_bytes(changed)
    path.with_name("bundle.sha256").write_text(
        hashlib.sha256(changed).hexdigest() + "\n", encoding="ascii"
    )

    with pytest.raises(ValueError, match="setup bundle changed"):
        store.require_bundle_sha256(ATTEMPT, expected)


def test_cleanup_start_blocks_later_acceptance(tmp_path: Path):
    """A precleanup record is a permanent phase boundary, even if partial."""
    store = ServerPtCommissioningStore(tmp_path)
    store.save_precleanup(ATTEMPT, PhysicalWorkspaceObservation())

    assert store.cleanup_started(ATTEMPT) is True
