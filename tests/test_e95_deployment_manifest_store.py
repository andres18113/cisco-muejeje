from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentManifest,
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from packet_tracer_mcp.domain.enterprise.services.topology_identity import (
    stamp_topology_hashes,
)
from packet_tracer_mcp.domain.models.plans import DevicePlan, TopologyPlan
from packet_tracer_mcp.infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
    ManifestPersistenceError,
)
from packet_tracer_mcp.infrastructure.persistence import deployment_manifest_store


def _manifest(
    *,
    deployment_id: str = "deployment/reference",
    runtime_identifier: str = "runtime-r1",
    created_at: datetime | None = None,
) -> DeploymentManifest:
    topology = TopologyPlan(
        id="e4/reference",
        devices=[
            DevicePlan(
                id="r1",
                name="HQ-R1",
                model="2911",
                category="router",
            ),
        ],
    )
    stamp_topology_hashes(topology)
    return build_deployment_manifest(
        topology,
        [
            RuntimeConfigurationTarget(
                device_name="HQ-R1",
                model="2911",
                interfaces=["GigabitEthernet0/0"],
                runtime_identifier=runtime_identifier,
                runtime_identifier_stable=True,
            ),
        ],
        fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version="9.0.1.0858",
            bridge_transport="file",
            extension_version="5",
            runtime_mode="logical-workspace",
        ),
        deployment_id=deployment_id,
        created_at=created_at,
    )


def test_verified_manifest_roundtrips_and_is_queryable_by_both_identities(tmp_path: Path):
    base_dir = tmp_path / "deployment-manifests"
    store = DeploymentManifestStore(base_dir)
    manifest = _manifest()

    saved_path = store.save_verified(manifest)

    assert saved_path.resolve().is_relative_to(base_dir.resolve())
    assert DeploymentManifest.model_validate_json(
        saved_path.read_text(encoding="utf-8")
    ) == manifest
    assert store.latest_by_deployment_id(manifest.deployment_id) == manifest
    assert store.find_by_semantic_hash(manifest.semantic_hash) == [manifest]


def test_manifest_store_confines_untrusted_deployment_id_to_base_directory(tmp_path: Path):
    base_dir = tmp_path / "deployment-manifests"
    store = DeploymentManifestStore(base_dir)
    manifest = _manifest(deployment_id="../../outside\\CON")

    saved_path = store.save_verified(manifest)

    assert saved_path.resolve().is_relative_to(base_dir.resolve())
    assert not (tmp_path / "outside").exists()
    assert store.latest_by_deployment_id(manifest.deployment_id) == manifest
    # Sanitized path aliases must never become manifest identity aliases.
    assert store.latest_by_deployment_id("outside_CON") is None


def test_same_semantics_from_new_runtime_session_is_append_only(tmp_path: Path):
    store = DeploymentManifestStore(tmp_path / "deployment-manifests")
    first = _manifest(
        runtime_identifier="runtime-session-one",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    second = _manifest(
        runtime_identifier="runtime-session-two",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    assert first.semantic_hash == second.semantic_hash

    first_path = store.save_verified(first)
    first_payload = first_path.read_text(encoding="utf-8")
    second_path = store.save_verified(second)

    assert first_path != second_path
    assert first_path.read_text(encoding="utf-8") == first_payload
    assert store.latest_by_deployment_id(first.deployment_id) == second
    assert store.find_by_semantic_hash(first.semantic_hash) == [first, second]
    assert store.save_verified(second) == second_path
    assert len(list((tmp_path / "deployment-manifests").rglob("*.json"))) == 2


def test_existing_content_addressed_record_is_never_silently_overwritten(tmp_path: Path):
    store = DeploymentManifestStore(tmp_path / "deployment-manifests")
    manifest = _manifest()
    path = store.save_verified(manifest)
    path.write_text("corrupted-but-preserved", encoding="utf-8")

    with pytest.raises(ManifestPersistenceError, match="existing manifest record"):
        store.save_verified(manifest)

    assert path.read_text(encoding="utf-8") == "corrupted-but-preserved"


def test_atomic_replace_failure_leaves_no_partial_record_or_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base_dir = tmp_path / "deployment-manifests"
    store = DeploymentManifestStore(base_dir)

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("controlled atomic replace failure")

    monkeypatch.setattr(deployment_manifest_store.os, "replace", fail_replace)

    with pytest.raises(ManifestPersistenceError, match="atomic replace failure"):
        store.save_verified(_manifest())

    assert list(base_dir.rglob("*.json")) == []
    assert list(base_dir.rglob("*.tmp")) == []


def test_live_enterprise_deploy_persists_only_after_verified_manifest_exists():
    source = Path(
        "src/packet_tracer_mcp/adapters/mcp/tool_registry.py"
    ).read_text(encoding="utf-8")
    live_deploy = source[source.index("    def pt_live_deploy("):]
    enterprise_path = live_deploy[:live_deploy.index(
        "        # Compatibility path for pre-E9.5 plans."
    )]

    missing_guard = enterprise_path.index("if physical_result.manifest is None:")
    missing_return = enterprise_path.index("return (", missing_guard)
    persist = enterprise_path.index(
        "DeploymentManifestStore().save_verified(",
        missing_return,
    )

    assert missing_guard < missing_return < persist
    assert "except ManifestPersistenceError as exc:" in enterprise_path
    assert "Manifest path: {manifest_path}" in enterprise_path
