"""The V6 result shapes this repository has published, frozen as declared data.

Split out of `support` when the link readings pushed that module past its line
budget (MJ-018, MJ-020): the synthetic repository and the frozen contract grow
for different reasons. They are declared data rather than claims — what they
*mean* is asserted in `test_v6_result_shapes` (MJ-030) — and they live in one
module because two copies of a frozen shape could disagree.
"""

from __future__ import annotations

# Per operation, the result fields a consumer may already be reading. An
# operation may answer with more; it may never answer with fewer.
# `descriptors[].factory_index` is frozen for the reason it was added: it is a
# reading's *reusable input*, and relay closure turns on it being reported
# rather than derived (`test_relay_closure`).
# `unavailable_member` and `unavailable_argument` are frozen for the reason they
# were added: an unavailable reading that cannot say which `Interface.member` it
# stopped at leaves a target run unable to locate what it observed
# (`test_platform_stage`).
STAGE = {"resolution", "unavailable_reason", "unavailable_member", "unavailable_argument"}
REQUIRED_RESULT_FIELDS = {
    "network.device_identity": STAGE | {
        "workspace_index", "available_count", "device_present",
        "name", "model", "device_type", "object_uuid",
    },
    "network.device_inventory": STAGE | {
        "available_count", "workspace_offset",
        "limit", "devices", "window_truncated",
    },
    "network.device_ports": STAGE | {
        "workspace_index", "available_count", "device_present",
        "name", "model", "object_uuid", "port_offset", "limit", "port_count",
        "ports", "window_truncated",
    },
    "network.link_endpoints": STAGE | {
        "workspace_link_index", "available_count", "link_present",
        "object_uuid", "port1", "port2",
    },
    "network.link_inventory": STAGE | {
        "available_count", "workspace_link_offset",
        "limit", "links", "window_truncated",
    },
    "platform.device_descriptors": STAGE | {
        "available_count", "factory_offset",
        "limit", "descriptors", "window_truncated",
    },
    "platform.module_descriptors": STAGE | {
        "factory_index", "available_count",
        "descriptor_present", "model", "device_type", "root_present", "nodes",
        "nodes_truncated", "depth_truncated", "module_positions_truncated",
    },
    "platform.module_type_support": STAGE | {
        "factory_index", "module_type",
        "available_count", "descriptor_present", "model", "device_type",
        "module_type_supported",
    },
    "runtime.identify": {
        "extension_name", "extension_version", "protocol_versions",
        "operations", "supported_features", "runtime_session_id",
        "provenance", "lifecycle",
    },
    "runtime.capabilities": {
        "runtime_session_id", "protocol_versions", "operations",
        "supported_features",
    },
}

# The nested objects inside those results, by the path that reaches them, with
# the type each published field carries. `descriptors[]` means "every object in
# that list"; a tuple of types means the field may be any of them, which is how
# a nullable one is written down.
#
# Fields and types, not just names, because "keeps its name while meaning
# something else" is the half of MJ-030 a name-only reader cannot see. Paths
# are a *floor*: a result may publish a nested object nobody froze — that is
# additive, and a consumer not reading it cannot see it — but it may never stop
# publishing one that is frozen here.
LINK_END = {"name": str, "object_uuid": str, "owner_device_object_uuid": str}
REQUIRED_NESTED_FIELDS = {
    # No nested object of its own: one device, read flat. Frozen as empty on
    # purpose — a nested object added later is additive.
    "network.device_identity": {},
    "network.device_inventory": {
        "devices[]": {"workspace_index": int, "name": str, "object_uuid": str},
    },
    "network.device_ports": {
        "ports[]": {"port_index": int, "name": str, "object_uuid": str},
    },
    # The two ends are named for the members that hand them over, and each is
    # attributable to a port and a device only through the UUIDs it carries.
    "network.link_endpoints": {"port1": LINK_END, "port2": LINK_END},
    "network.link_inventory": {
        "links[]": {
            "workspace_link_index": int, "connection_type": int, "object_uuid": str,
        },
    },
    "platform.device_descriptors": {
        "descriptors[]": {
            "factory_index": int, "model": str, "device_type": int,
            "model_supported": bool, "supported_module_types": list,
            "module_types_truncated": bool,
        },
    },
    "platform.module_descriptors": {
        "nodes[]": {
            "index": int, "parent_index": (int, type(None)), "depth": int,
            "module_index": (int, type(None)), "model": str,
            "module_type": int, "hot_swappable": bool, "slot_types": list,
            "slot_types_truncated": bool, "module_count": int,
            "null_module_positions": list, "children_truncated": bool,
        },
    },
    # No nested object of its own: one flag, and the identity that attributes
    # it. Frozen as empty on purpose — a nested object added later is additive.
    "platform.module_type_support": {},
    "runtime.identify": {
        "provenance": {
            "state": str, "source_sha": type(None),
            "build_recipe_id": type(None),
        },
        "lifecycle": {
            "started": bool, "started_at": (int, type(None)),
            "stopped_at": (int, type(None)), "start_count": int,
        },
    },
    "runtime.capabilities": {
        "operations[]": {"op": str, "read_only": bool},
    },
}
