from datetime import datetime, timezone

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from src.packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentBinding,
    DeploymentManifest,
    DeploymentIdentityError,
    EnvironmentFingerprint,
    IdentityMethod,
    build_deployment_manifest,
)
from src.packet_tracer_mcp.domain.enterprise.services.topology_identity import stamp_topology_hashes
from src.packet_tracer_mcp.domain.models.plans import DevicePlan, TopologyPlan


def _topology() -> TopologyPlan:
    topology = TopologyPlan(
        id="e4/reference",
        devices=[
            DevicePlan(id="r1", name="HQ-R1", model="2911", category="router"),
            DevicePlan(id="sw1", name="HQ-SW1", model="2960-24TT", category="switch"),
        ],
    )
    stamp_topology_hashes(topology)
    return topology


def _inventory() -> list[RuntimeConfigurationTarget]:
    return [
        RuntimeConfigurationTarget(
            device_name="HQ-R1", model="2911",
            interfaces=["GigabitEthernet0/0"], runtime_identifier="runtime-r1",
            runtime_identifier_stable=True,
        ),
        RuntimeConfigurationTarget(
            device_name="HQ-SW1", model="2960-24TT",
            interfaces=["FastEthernet0/1"], runtime_identifier="runtime-sw1",
            runtime_identifier_stable=True,
        ),
    ]


def test_manifest_binds_semantic_devices_to_observed_runtime_identity():
    topology = _topology()
    fingerprint = EnvironmentFingerprint(
        backend="packet_tracer", backend_version="9.0.1.0858",
        bridge_transport="http", extension_version="5",
        capability_snapshot_version="e9.5",
    )

    manifest = build_deployment_manifest(topology, _inventory(), fingerprint=fingerprint)

    assert manifest.physical_topology_hash == topology.physical_topology_hash
    assert len(manifest.bindings) == 2
    assert manifest.binding_for("r1").identity_method is IdentityMethod.RUNTIME_ID
    assert manifest.resolve_target("r1", _inventory()).device_name == "HQ-R1"


def test_manifest_refuses_matching_name_with_wrong_model():
    manifest = build_deployment_manifest(
        _topology(), _inventory(), fingerprint=EnvironmentFingerprint(),
    )
    wrong = [
        RuntimeConfigurationTarget(
            device_name="HQ-R1", model="1841", runtime_identifier="runtime-r1",
            runtime_identifier_stable=True,
        ),
    ]

    with pytest.raises(DeploymentIdentityError, match="model"):
        manifest.resolve_target("r1", wrong)


def test_manifest_refuses_missing_binding_instead_of_falling_back_to_name():
    manifest = build_deployment_manifest(
        _topology(), _inventory(), fingerprint=EnvironmentFingerprint(),
    )

    with pytest.raises(DeploymentIdentityError, match="binding"):
        manifest.resolve_target("missing", _inventory())


def test_manifest_refuses_to_downgrade_stable_runtime_id_to_name_lookup():
    manifest = build_deployment_manifest(
        _topology(), _inventory(), fingerprint=EnvironmentFingerprint(),
    )
    same_name_without_runtime_id = [
        RuntimeConfigurationTarget(device_name="HQ-R1", model="2911"),
    ]

    with pytest.raises(DeploymentIdentityError, match="runtime identifier"):
        manifest.resolve_target("r1", same_name_without_runtime_id)


def test_manifest_requires_recorded_composite_fingerprint_during_resolution():
    inventory = _inventory()
    for target in inventory:
        target.runtime_identifier = ""
        target.runtime_identifier_stable = False
        target.runtime_fingerprint = "fingerprint/" + target.device_name
    manifest = build_deployment_manifest(
        _topology(), inventory, fingerprint=EnvironmentFingerprint(),
    )
    same_name_without_fingerprint = [
        RuntimeConfigurationTarget(device_name="HQ-R1", model="2911"),
    ]

    with pytest.raises(DeploymentIdentityError, match="fingerprint"):
        manifest.resolve_target("r1", same_name_without_fingerprint)


def test_manifest_semantic_hash_excludes_created_at_metadata():
    topology = _topology()
    first = build_deployment_manifest(
        topology, _inventory(), fingerprint=EnvironmentFingerprint(),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    second = build_deployment_manifest(
        topology, _inventory(), fingerprint=EnvironmentFingerprint(),
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    assert first.semantic_hash == second.semantic_hash


def test_manifest_semantic_hash_excludes_deployment_and_stable_runtime_session_ids():
    topology = _topology()
    first_inventory = _inventory()
    second_inventory = _inventory()
    for target in second_inventory:
        target.runtime_identifier = "next-session/" + target.runtime_identifier

    first = build_deployment_manifest(
        topology,
        first_inventory,
        fingerprint=EnvironmentFingerprint(
            backend="packet_tracer", backend_version="9.0.1.0858",
        ),
        deployment_id="deployment/session-one",
    )
    second = build_deployment_manifest(
        topology,
        second_inventory,
        fingerprint=EnvironmentFingerprint(
            backend="packet_tracer", backend_version="9.0.1.0858",
        ),
        deployment_id="deployment/session-two",
    )

    assert first.binding_for("r1").runtime_identifier != second.binding_for("r1").runtime_identifier
    assert first.semantic_hash == second.semantic_hash


def test_unstable_packet_tracer_identifier_is_not_promoted_to_runtime_identity():
    inventory = _inventory()
    for target in inventory:
        target.runtime_identifier_stable = False

    manifest = build_deployment_manifest(
        _topology(), inventory, fingerprint=EnvironmentFingerprint(),
    )

    assert all(
        binding.identity_method is IdentityMethod.SEMANTIC_BINDING
        for binding in manifest.bindings
    )
    assert all(not binding.runtime_identifier for binding in manifest.bindings)


@pytest.mark.parametrize(
    ("identity_method", "missing_field"),
    [
        (IdentityMethod.RUNTIME_ID, "runtime identifier"),
        (IdentityMethod.COMPOSITE_FINGERPRINT, "fingerprint"),
    ],
)
def test_deserialized_manifest_cannot_downgrade_a_strong_identity_method(
    identity_method: IdentityMethod,
    missing_field: str,
):
    manifest = DeploymentManifest(
        deployment_id="deployment/tampered",
        physical_topology_hash=_topology().physical_topology_hash,
        bindings=[
            DeploymentBinding(
                semantic_device_id="r1",
                deployed_name="HQ-R1",
                model="2911",
                identity_method=identity_method,
            ),
        ],
    )

    with pytest.raises(DeploymentIdentityError, match=missing_field):
        manifest.resolve_target("r1", _inventory())
