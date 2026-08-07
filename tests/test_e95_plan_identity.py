from copy import deepcopy

from packet_tracer_mcp.domain.enterprise.models.compilation import LayoutProfile, LayoutRegion
from packet_tracer_mcp.domain.enterprise.services.topology_identity import (
    compute_topology_hashes,
    stamp_topology_hashes,
)
from packet_tracer_mcp.domain.models.plans import DevicePlan, LinkPlan, TopologyPlan


def _topology() -> TopologyPlan:
    return TopologyPlan(
        id="e4/reference",
        name="Reference",
        devices=[
            DevicePlan(
                id="r1", name="HQ-R1", model="2911", category="router",
                enterprise_role="edge_router", site_id="hq", network_layer="edge",
                x=100, y=100,
            ),
            DevicePlan(
                id="sw1", name="HQ-SW1", model="2960-24TT", category="switch",
                enterprise_role="access_switch", site_id="hq", network_layer="access",
                x=100, y=300,
            ),
        ],
        links=[
            LinkPlan(
                id="link/r1-sw1", device_a="HQ-R1", port_a="GigabitEthernet0/0",
                device_b="HQ-SW1", port_b="GigabitEthernet0/1",
                device_a_id="r1", device_b_id="sw1", link_role="access_uplink",
                redundancy_group="uplink-a",
            ),
        ],
    )


def test_layout_only_change_does_not_change_physical_identity():
    original = _topology()
    moved = deepcopy(original)
    moved.devices[0].x += 700
    moved.devices[1].y += 400

    first = compute_topology_hashes(
        original,
        layout_regions=[LayoutRegion(id="hq", kind="site", x=0, y=0, width=500, height=500)],
        layout_profile=LayoutProfile(origin_x=100),
    )
    second = compute_topology_hashes(
        moved,
        layout_regions=[LayoutRegion(id="hq", kind="site", x=0, y=0, width=900, height=900)],
        layout_profile=LayoutProfile(origin_x=200),
    )

    assert first.physical_topology_hash == second.physical_topology_hash
    assert first.layout_hash != second.layout_hash
    assert first.artifact_hash != second.artifact_hash


def test_display_rename_does_not_redefine_physical_topology():
    original = _topology()
    renamed = deepcopy(original)
    renamed.devices[0].name = "DISPLAY-ONLY-R1"
    renamed.links[0].device_a = "DISPLAY-ONLY-R1"

    assert (
        compute_topology_hashes(original).physical_topology_hash
        == compute_topology_hashes(renamed).physical_topology_hash
    )


def test_hash_stamp_preserves_legacy_semantic_hash_as_artifact_identity():
    topology = _topology()
    hashes = stamp_topology_hashes(topology)

    assert topology.hash_schema_version == "2"
    assert topology.physical_topology_hash == hashes.physical_topology_hash
    assert topology.layout_hash == hashes.layout_hash
    assert topology.artifact_hash == hashes.artifact_hash
    assert topology.semantic_hash == topology.artifact_hash
    assert topology.physical_identity_hash == topology.physical_topology_hash


def test_legacy_topology_uses_explicit_compatibility_fallback():
    legacy = TopologyPlan(semantic_hash="legacy-e4-hash")

    assert legacy.hash_schema_version == "1"
    assert legacy.physical_identity_hash == "legacy-e4-hash"


def test_network_mutations_change_physical_identity_but_warnings_do_not():
    original = _topology()
    base = compute_topology_hashes(original)

    changed_model = deepcopy(original)
    changed_model.devices[0].model = "1941"
    changed_port = deepcopy(original)
    changed_port.links[0].port_a = "GigabitEthernet0/1"
    changed_redundancy = deepcopy(original)
    changed_redundancy.links[0].redundancy_group = "uplink-b"
    warning_only = deepcopy(original)
    warning_only.warnings.append("layout exceeds viewport")

    assert compute_topology_hashes(changed_model).physical_topology_hash != base.physical_topology_hash
    assert compute_topology_hashes(changed_port).physical_topology_hash != base.physical_topology_hash
    assert compute_topology_hashes(changed_redundancy).physical_topology_hash != base.physical_topology_hash
    warning_hashes = compute_topology_hashes(warning_only)
    assert warning_hashes.physical_topology_hash == base.physical_topology_hash
    assert warning_hashes.layout_hash == base.layout_hash
    assert warning_hashes.artifact_hash != base.artifact_hash


def test_all_topology_hashes_are_deterministic_ten_times():
    observed = {
        tuple(compute_topology_hashes(_topology()).model_dump().values())
        for _ in range(10)
    }

    assert len(observed) == 1
