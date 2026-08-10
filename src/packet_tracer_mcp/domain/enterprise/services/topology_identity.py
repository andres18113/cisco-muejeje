"""Canonical E4 physical, layout and complete-artifact identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

from ...models.plans import TopologyPlan
from ..models.compilation import LayoutProfile, LayoutRegion


class TopologyHashes(BaseModel):
    schema_version: str = "2"
    physical_topology_hash: str
    layout_hash: str
    artifact_hash: str


_VISUAL_METADATA_PREFIXES = ("layout_", "visual_", "display_")


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _network_metadata(metadata: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value for key, value in sorted(metadata.items())
        if not key.casefold().startswith(_VISUAL_METADATA_PREFIXES)
    }


def _physical_payload(topology: TopologyPlan) -> dict[str, object]:
    devices = []
    name_to_id: dict[str, str] = {}
    for device in sorted(topology.devices, key=lambda item: (item.id or item.name, item.model)):
        semantic_id = device.id or device.name
        name_to_id[device.name] = semantic_id
        devices.append({
            "id": semantic_id,
            "model": device.model,
            "category": device.category,
            "role": device.role.value,
            "enterprise_role": device.enterprise_role,
            "site_id": device.site_id,
            "building_id": device.building_id,
            "floor_id": device.floor_id,
            "zone_id": device.zone_id,
            "network_layer": device.network_layer,
            "requires_poe": device.requires_poe,
            "wireless": device.wireless,
            "metadata": _network_metadata(device.metadata),
        })
    links = []
    for link in topology.links:
        endpoint_a = (
            link.device_a_id or name_to_id.get(link.device_a, link.device_a),
            link.port_a,
        )
        endpoint_b = (
            link.device_b_id or name_to_id.get(link.device_b, link.device_b),
            link.port_b,
        )
        first, second = sorted((endpoint_a, endpoint_b))
        links.append({
            "id": link.id,
            "device_a_id": first[0],
            "port_a": first[1],
            "device_b_id": second[0],
            "port_b": second[1],
            "cable": link.cable,
            "link_role": link.link_role,
            "network_layer": link.network_layer,
            "redundancy_group": link.redundancy_group,
            "metadata": _network_metadata(link.metadata),
        })
    links.sort(key=lambda item: (
        str(item["id"]), str(item["device_a_id"]), str(item["port_a"]),
        str(item["device_b_id"]), str(item["port_b"]),
    ))
    modules = [
        {
            "device_id": name_to_id.get(module.device, module.device),
            "slot": module.slot,
            "module": module.module,
        }
        for module in topology.modules
    ]
    modules.sort(key=lambda item: (
        str(item["device_id"]), str(item["slot"]), str(item["module"]),
    ))
    return {
        "schema": "physical-topology-v2",
        "devices": devices,
        "modules": modules,
        "links": links,
        "dual_stack": topology.dual_stack,
    }


def _serializable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    return value


def _layout_payload(
    topology: TopologyPlan,
    layout_regions: Iterable[LayoutRegion | Mapping[str, object]],
    layout_profile: LayoutProfile | Mapping[str, object] | None,
) -> dict[str, object]:
    regions = sorted(
        (_serializable(item) for item in layout_regions),
        key=lambda item: (str(item.get("kind", "")), str(item.get("id", ""))),
    )
    coordinates = [(item.x, item.y) for item in topology.devices]
    left = [x for x, _ in coordinates] + [int(item.get("x", 0)) for item in regions]
    top = [y for _, y in coordinates] + [int(item.get("y", 0)) for item in regions]
    right = [x for x, _ in coordinates] + [
        int(item.get("x", 0)) + int(item.get("width", 0)) for item in regions
    ]
    bottom = [y for _, y in coordinates] + [
        int(item.get("y", 0)) + int(item.get("height", 0)) for item in regions
    ]
    return {
        "schema": "layout-v2",
        "topology_name": topology.name,
        "devices": [
            {"id": item.id or item.name, "name": item.name, "x": item.x, "y": item.y}
            for item in sorted(topology.devices, key=lambda device: device.id or device.name)
        ],
        "regions": regions,
        "bounds": {
            "left": min(left, default=0),
            "top": min(top, default=0),
            "right": max(right, default=0),
            "bottom": max(bottom, default=0),
        },
        "profile": _serializable(layout_profile) if layout_profile is not None else {},
    }


def compute_topology_hashes(
    topology: TopologyPlan,
    *,
    layout_regions: Iterable[LayoutRegion | Mapping[str, object]] = (),
    layout_profile: LayoutProfile | Mapping[str, object] | None = None,
) -> TopologyHashes:
    physical_payload = _physical_payload(topology)
    layout_payload = _layout_payload(topology, layout_regions, layout_profile)
    physical_hash = _digest(physical_payload)
    layout_hash = _digest(layout_payload)
    return TopologyHashes(
        physical_topology_hash=physical_hash,
        layout_hash=layout_hash,
        artifact_hash=_digest({
            "schema": "topology-artifact-v2",
            "physical_topology_hash": physical_hash,
            "layout_hash": layout_hash,
            "warnings": sorted(topology.warnings),
            "errors": sorted(topology.errors),
        }),
    )


def stamp_topology_hashes(
    topology: TopologyPlan,
    *,
    layout_regions: Iterable[LayoutRegion | Mapping[str, object]] = (),
    layout_profile: LayoutProfile | Mapping[str, object] | None = None,
) -> TopologyHashes:
    hashes = compute_topology_hashes(
        topology, layout_regions=layout_regions, layout_profile=layout_profile,
    )
    topology.hash_schema_version = hashes.schema_version
    topology.physical_topology_hash = hashes.physical_topology_hash
    topology.layout_hash = hashes.layout_hash
    topology.artifact_hash = hashes.artifact_hash
    # Controlled compatibility: semantic_hash retains the complete-artifact
    # meaning it had in v1. New downstream plans bind to the physical hash.
    topology.semantic_hash = hashes.artifact_hash
    return hashes
