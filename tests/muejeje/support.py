"""Shared paths, declared data and fixtures for the Muejeje test area.

Small on purpose. This module holds where things are, what this repository
declares about itself, and the synthetic repository the build audit runs
against. It holds no assertions, so a behaviour claim always lives in the test
module whose responsibility it is (MJ-020).

The frozen V6 result shapes are here for the same reason `FEATURE_EVIDENCE`
is: they are what this repository declares about its own contract, they grow
with every operation, and two copies of them could disagree. What they *mean*
is asserted in `test_v6_result_shapes` (MJ-030).

Measuring the real tree is `measure`, which was split out of here when this
module crossed its own line budget. Building a fixture and measuring a file are
two responsibilities, and the budget is what made the split happen rather than
be argued about (MJ-018, MJ-020).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_MODULE = REPO_ROOT / "src/packet_tracer_mcp/infrastructure/pts/build.py"
PTS_PACKAGE = REPO_ROOT / "src/packet_tracer_mcp/infrastructure/pts"
CLI = REPO_ROOT / "tools/build_muejeje_pts.py"
SOURCE_ROOT = REPO_ROOT / "muejeje_pts"
SCRIPT_ENGINE = SOURCE_ROOT / "script-engine"
REPO_MANIFEST = SOURCE_ROOT / "manifest/muejeje-build-manifest.json"
MUEJEJE_TESTS = Path(__file__).resolve().parent
REFERENCE_PATH = "local-references/api-reference.txt"

INSTALLED_BUILDER = Path(
    "C:/Program Files/Cisco Packet Tracer 9.0.1/bin/PacketTracer.exe"
)
# Cisco's own installed documentation. Read, never copied: it is somebody
# else's bytes, and the pages this repository relies on are hash-pinned in the
# v2 preflight inventory. Nothing here ships in the artifact.
INSTALLED_HELP = Path("C:/Program Files/Cisco Packet Tracer 9.0.1/help/default")

TOOLING_INPUTS = [
    "src/packet_tracer_mcp/infrastructure/pts/__init__.py",
    "src/packet_tracer_mcp/infrastructure/pts/build.py",
    "src/packet_tracer_mcp/infrastructure/pts/build_state.py",
    "src/packet_tracer_mcp/infrastructure/pts/inventory.py",
    "src/packet_tracer_mcp/infrastructure/pts/manifest.py",
    "src/packet_tracer_mcp/infrastructure/pts/provenance.py",
    "src/packet_tracer_mcp/infrastructure/pts/references.py",
    "tools/build_muejeje_pts.py",
]

# Every kernel feature `MUEJEJE_CORE.SUPPORTED_FEATURES` may name, and the
# symbol in the artifact that backs it. Data, not a claim: the modules that
# assert against it are `test_runtime_identify` and `test_runtime_capabilities`
# for the reported list, and `test_capability_claims` for what a document may
# call a capability. It lives here because two copies of this map could
# disagree, and a feature backed by one of them would be a capability claim
# nobody was checking (MJ-028).
FEATURE_EVIDENCE = {
    "network.device_reading": (
        "network_adapter.js", "muejejeAdapterDeviceInventory",
    ),
    "network.identity_reading": (
        "network_identity_adapter.js", "muejejeAdapterDeviceIdentity",
    ),
    "network.port_reading": (
        "network_ports_adapter.js", "muejejeAdapterDevicePorts",
    ),
    "platform.descriptor_discovery": (
        "platform_device_adapter.js", "muejejeAdapterDeviceDescriptors",
    ),
    "platform.module_discovery": (
        "platform_module_adapter.js", "muejejeAdapterModuleDescriptors",
    ),
    "platform.support_lookup": (
        "platform_support_adapter.js", "muejejeAdapterModuleTypeSupport",
    ),
    "protocol.v6": ("validation_v6.js", "muejejeV6ParseRequest"),
    "runtime.operation_catalog": ("dispatcher_v6.js", "muejejeV6OperationCatalog"),
    "runtime.session_id": ("core.js", "muejejeCoreNewSessionId"),
}


# Per operation, the result fields a consumer may already be reading. An
# operation may answer with more; it may never answer with fewer.
# `descriptors[].factory_index` is frozen for the reason it was added: it is a
# reading's *reusable input*, and relay closure turns on it being reported
# rather than derived (`test_relay_closure`).
REQUIRED_RESULT_FIELDS = {
    "network.device_identity": {
        "resolution", "unavailable_reason", "workspace_index", "available_count",
        "device_present", "name", "model", "device_type",
    },
    "network.device_inventory": {
        "resolution", "unavailable_reason", "available_count", "workspace_offset",
        "limit", "devices", "window_truncated",
    },
    "network.device_ports": {
        "resolution", "unavailable_reason", "workspace_index", "available_count",
        "device_present", "name", "model", "port_offset", "limit", "port_count",
        "ports", "window_truncated",
    },
    "platform.device_descriptors": {
        "resolution", "unavailable_reason", "available_count", "factory_offset",
        "limit", "descriptors", "window_truncated",
    },
    "platform.module_descriptors": {
        "resolution", "unavailable_reason", "factory_index", "available_count",
        "descriptor_present", "model", "device_type", "root_present", "nodes",
        "nodes_truncated", "depth_truncated",
    },
    "platform.module_type_support": {
        "resolution", "unavailable_reason", "factory_index", "module_type",
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
REQUIRED_NESTED_FIELDS = {
    # No nested object of its own: one device, read flat. Frozen as empty on
    # purpose — a nested object added later is additive.
    "network.device_identity": {},
    "network.device_inventory": {
        "devices[]": {"workspace_index": int, "name": str},
    },
    "network.device_ports": {
        "ports[]": {"port_index": int, "name": str},
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
            "children_truncated": bool,
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


def resolved_options() -> dict[str, Any]:
    """The baselined packaging recipe (MJ-025), read from the real manifest.

    The synthetic repository declares this repository's own artifact inputs,
    so its build options have to be this repository's own too: a fixture
    carrying its own copy of the engine order would keep the synthetic audit
    green after a reorder that no artifact reflects. `test_protocol_v6` is
    where the expected order is written down and asserted; here it is read.
    """
    return dict(repo_manifest()["build_options"])


def build_api():
    from src.packet_tracer_mcp.infrastructure.pts import build
    return build


def repo_manifest() -> dict[str, Any]:
    """The real manifest this repository ships."""
    return json.loads(REPO_MANIFEST.read_text(encoding="utf-8"))


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True,
    )


def manifest_document() -> dict[str, Any]:
    """The manifest the synthetic repository declares.

    It mirrors the real schema-2 document but names synthetic file contents, so
    a test can perturb one field without touching the repository.
    """
    return {
        "schema_version": 2,
        "extension": {"name": "muejeje", "version": "0.1.0"},
        "output": {"artifact": "muejeje.pts", "report": "muejeje.build.json"},
        "artifact_inputs": list(repo_manifest()["artifact_inputs"]),
        "tooling_inputs": list(TOOLING_INPUTS),
        "reference_inputs": [],
        "builder": {
            "name": "Cisco Packet Tracer", "version": "9.0.1.0858",
            "kind": "packet-tracer-scripting-interface",
            "sha256": "843579cc806a41d57a4ca524d6805b97ee1f91e0ddd02ac09be8461db04b94a1",
        },
        "build_options": {
            "engine_script_order": None, "custom_interface_order": None,
            "module_id": None, "startup": None, "privileges": None,
        },
        "packaging": {
            "status": "unresolved", "compiler_command": None,
            "content_validation": None,
        },
    }


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A committed synthetic checkout whose declared inputs all exist."""
    root = tmp_path / "source"
    document = manifest_document()
    manifest_path = root / "muejeje_pts/manifest/muejeje-build-manifest.json"
    declared = document["artifact_inputs"] + document["tooling_inputs"]
    for logical in declared:
        path = root / logical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"own:{logical}\n", encoding="utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    (root / ".gitignore").write_text("dist/\nlocal-references/\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Muejeje test")
    git(root, "add", ".")
    git(root, "commit", "-qm", "fixture")
    return root, manifest_path


def commit_manifest(root: Path, manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    git(root, "add", str(manifest_path.relative_to(root)))
    git(root, "commit", "-qm", "update manifest")


def reference_entry(root: Path) -> dict[str, str]:
    path = root / REFERENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = b"synthetic API reference\n"
    path.write_bytes(contents)
    return {"path": REFERENCE_PATH, "sha256": hashlib.sha256(contents).hexdigest()}
