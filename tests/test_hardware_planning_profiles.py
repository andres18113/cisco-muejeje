"""Versioned planning preserves exact deployed shapes and admits new trunks."""

from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.application.use_cases.plan_enterprise_hardware import (
    capability_catalog_for,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import CapabilityStatus
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent


def test_new_single_segment_hierarchy_selects_trunk_evidenced_hardware():
    """Thirty-six selected users require two access switches with actual trunks."""
    intent = EnterpriseIntent.model_validate(
        {
            "name": "NEW-HIERARCHY",
            "address_space": "10.40.0.0/16",
            "sites": [
                {
                    "name": "BR1",
                    "type": "branch",
                    "endpoints": [
                        {
                            "role": "user_pc",
                            "count": 36,
                            "addressing_preference": "static",
                        }
                    ],
                }
            ],
        }
    )
    result = compose_enterprise_reference(intent, packet_tracer_version="9.0.1.0858")
    assert result.topology is not None, result.issues
    access = [d for d in result.topology.devices if "-ACCESS-SW-" in d.name]
    assert len(access) == 2
    catalog = capability_catalog_for("9.0.1.0858")
    assert all(
        catalog.capabilities_for(d.model, "9.0.1.0858").supports_trunk
        is CapabilityStatus.SUPPORTED
        for d in access
    )


def _frozen_bundle_manifest():
    """Reconstruct the reviewed bundle without depending on ignored archives."""
    from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
        prepare_server_pt_commissioning,
    )
    from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
        RuntimeConfigurationTarget,
    )
    from packet_tracer_mcp.domain.enterprise.models.deployment import (
        EnvironmentFingerprint,
        build_deployment_manifest,
    )
    from packet_tracer_mcp.domain.models.plans import TopologyPlan

    bundle = prepare_server_pt_commissioning(
        30, "COLD_HTTP_5b09a9c35fd572f00945bdb18040d2fb"
    )
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    inventory = [
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=sorted(
                {
                    port
                    for link in topology.links
                    for device_id, port in (
                        (link.device_a_id, link.port_a),
                        (link.device_b_id, link.port_b),
                    )
                    if device_id == device.id
                }
            ),
        )
        for device in topology.devices
    ]
    manifest = build_deployment_manifest(
        topology,
        inventory,
        fingerprint=EnvironmentFingerprint(
            backend="packet_tracer", backend_version="9.0.1.0858"
        ),
    )
    return bundle, manifest


def test_frozen_commissioning_hashes_and_manifest_reconstruction_are_exact():
    """The rejected planner commit cannot silently change reviewed C31 inputs."""
    bundle, manifest = _frozen_bundle_manifest()
    assert (
        bundle.intent_sha256
        == "9d353bfc35030c313a97a74ca95f830de919a936c7068755420ed7f4e186abef"
    )
    assert (
        bundle.topology_sha256
        == "fcff5b9d54dcb8acafb487e150e1db9eebecb32b8734e3d1e8270a5ad6742ffd"
    )
    assert (
        bundle.physical_topology_hash
        == "753cf2ecee52ae13681ef57fd4b93c39c4540a1c970f44dd5e435becfef87d44"
    )
    assert (
        bundle.configuration_semantic_hash
        == "35618f4d709d9142cacf9dd6cc9913ccb2c1001765fa148dc6dee1a8c8dcab3a"
    )
    composed = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(bundle.intent_json),
        packet_tracer_version=bundle.build,
        deployment_manifest=manifest,
    )
    assert composed.topology.physical_identity_hash == bundle.physical_topology_hash


def test_unmatched_manifest_does_not_select_previous_profile():
    """A foreign physical hash cannot request legacy hardware by omission."""
    bundle, manifest = _frozen_bundle_manifest()
    manifest.physical_topology_hash = "f" * 64
    composed = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(bundle.intent_json),
        packet_tracer_version=bundle.build,
        deployment_manifest=manifest,
    )
    assert composed.topology.physical_identity_hash not in {
        manifest.physical_topology_hash,
        bundle.physical_topology_hash,
    }


def test_explicit_current_policy_never_falls_back_to_a_frozen_manifest():
    """An explicit policy is authoritative even when a previous plan survives."""
    from packet_tracer_mcp.domain.enterprise.services.hardware_planner import (
        HardwarePlanningPolicy,
    )

    bundle, manifest = _frozen_bundle_manifest()
    composed = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(bundle.intent_json),
        packet_tracer_version=bundle.build,
        deployment_manifest=manifest,
        policy=HardwarePlanningPolicy(),
    )
    assert composed.topology.physical_identity_hash != manifest.physical_topology_hash


def test_public_route_refuses_an_unmatched_physical_identity_before_effects(tmp_path):
    """Compatibility recognition never weakens public target identity admission."""
    from test_apply_enterprise_services import _harness

    from packet_tracer_mcp.domain.enterprise.models.service_entry import (
        ServiceEntryRefusal,
    )

    harness = _harness(tmp_path)
    harness.manifest_store.manifest.physical_topology_hash = "f" * 64
    result = harness.run()
    assert result.refusal_code is ServiceEntryRefusal.TARGET_IDENTITY_MISMATCH
    assert harness.mutating_calls == []
