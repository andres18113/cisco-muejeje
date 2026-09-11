"""Where the V6 kernel lives, and who owns what inside it.

Structural claims over the real tree: which files the artifact is split into,
the order they are evaluated in, that exactly one of them declares
`mcpDispatchV6`, and that no file has quietly taken on a neighbour's
responsibility — the dispatcher implementing an operation, the protocol module
reading a request, core growing behaviour (MJ-007, MJ-019).

What the protocol *answers* is `test_protocol_v6`, split from here when this
module crossed its own line budget: the layout of the kernel and the contract it
serves are two claims (MJ-018, MJ-020).

None of this runs anything, so none of it establishes behaviour — and nothing
here is a claim about Packet Tracer (MJ-015).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from tests.muejeje import engine_harness
from tests.muejeje.measure import engine_sources, relative
from tests.muejeje.support import MUEJEJE_TESTS, REPO_ROOT, SCRIPT_ENGINE, repo_manifest

# The declared evaluation order, written down exactly once. Packet Tracer
# evaluates the Script Engine files in the order the Scripting Interface lists
# them, so this order *is* the dependency direction: core, the protocol
# envelope, the admission that refuses with that envelope, what a platform
# reading is, the call boundary, the adapters that read through it, then
# operations, then dispatch, then the lifecycle that may call all of it
# (MJ-019).
# The Scripting Interface lists them by file name, so each name carries its
# place: a three-digit prefix, in steps of ten so a file can be inserted without
# renaming the kernel.
# Operations depend on nothing but core and protocol, so they are ordered
# alphabetically among themselves — a rule, rather than an accident nobody
# could re-derive.
#
# This list is the expectation; the manifest is the source every other reader
# derives from. One written-down copy is what makes a reorder a visible edit
# here instead of a silent drift everywhere.
ENGINE_SCRIPT_ORDER = [
    "muejeje_pts/script-engine/010_core.js",
    "muejeje_pts/script-engine/020_protocol_v6.js",
    "muejeje_pts/script-engine/030_validation_v6.js",
    "muejeje_pts/script-engine/040_arguments_v6.js",
    "muejeje_pts/script-engine/050_platform_reading.js",
    "muejeje_pts/script-engine/060_platform_adapter.js",
    "muejeje_pts/script-engine/070_network_adapter.js",
    "muejeje_pts/script-engine/080_network_identity_adapter.js",
    "muejeje_pts/script-engine/090_network_ports_adapter.js",
    "muejeje_pts/script-engine/100_platform_device_adapter.js",
    "muejeje_pts/script-engine/110_platform_module_adapter.js",
    "muejeje_pts/script-engine/120_platform_support_adapter.js",
    "muejeje_pts/script-engine/130_network_identity.js",
    "muejeje_pts/script-engine/140_network_inventory.js",
    "muejeje_pts/script-engine/150_network_ports.js",
    "muejeje_pts/script-engine/160_platform_discovery.js",
    "muejeje_pts/script-engine/170_platform_modules.js",
    "muejeje_pts/script-engine/180_platform_support.js",
    "muejeje_pts/script-engine/190_runtime_capabilities.js",
    "muejeje_pts/script-engine/200_runtime_identity.js",
    "muejeje_pts/script-engine/210_dispatcher_v6.js",
    "muejeje_pts/script-engine/220_lifecycle.js",
]


def inventory():
    from src.packet_tracer_mcp.infrastructure.pts import inventory
    return inventory


def test_the_kernel_is_split_into_the_declared_files():
    on_disk = [relative(path) for path in engine_sources()]
    assert sorted(on_disk) == sorted(ENGINE_SCRIPT_ORDER)


def test_engine_script_order_is_the_declared_dependency_order():
    order = repo_manifest()["build_options"]["engine_script_order"]
    assert order == ENGINE_SCRIPT_ORDER, (
        "core and protocol first, then operations, then dispatch, then lifecycle"
    )
    assert set(order) == {relative(path) for path in engine_sources()}


def test_the_file_names_list_in_the_declared_order():
    """The order a module can be packaged in is the order its names spell.

    Cisco documents that every engine file is evaluated "in the same order as
    listed in the Scripting Interface", and on `9.0.1.0858` that list is ordered
    by file name whatever order the files were imported in, with no control to
    reorder it. A declared order the names did not spell would have Node
    evaluating the manifest's order while Packet Tracer evaluated the
    alphabet's, and every offline claim would be about a module nobody can
    package (MJ-019, MJ-025).
    """
    declared = repo_manifest()["build_options"]["engine_script_order"]

    assert [path.name for path in engine_sources()] == [
        PurePosixPath(logical).name for logical in declared
    ]
    assert inventory().engine_listing_error(declared) is None


def test_the_node_harness_derives_its_evaluation_order_from_the_manifest():
    """The order is declared once. A second copy is one that will disagree.

    The harness used to list the engine files itself, so a manifest reorder
    would leave every offline run evaluating a different module from the one
    the recipe describes — and every gate in this module would still pass,
    because they all read the manifest. Naming no file is what makes the
    duplication impossible rather than merely absent today.
    """
    declared = repo_manifest()["build_options"]["engine_script_order"]
    assert engine_harness.engine_order() == [REPO_ROOT / item for item in declared]

    harness = (MUEJEJE_TESTS / "engine_harness.py").read_text(encoding="utf-8")
    named = [path.name for path in engine_harness.engine_order() if path.name in harness]
    assert named == [], f"the harness names an engine file itself: {named}"


def test_the_harness_follows_the_manifest_where_no_file_name_agrees(monkeypatch):
    """Deriving the order is a different claim from coinciding with it.

    The file names now spell the declared order, so a harness that listed the
    directory would pass every gate above while ignoring the manifest. The
    declaration is reversed here, where no name agrees with it, and the harness
    has to follow the declaration.
    """
    manifest = repo_manifest()
    reversed_order = list(reversed(manifest["build_options"]["engine_script_order"]))
    manifest["build_options"]["engine_script_order"] = reversed_order
    monkeypatch.setattr(engine_harness, "repo_manifest", lambda: manifest)

    assert engine_harness.engine_order() == [REPO_ROOT / item for item in reversed_order]


def test_mcp_dispatch_v6_is_implemented_exactly_once_by_the_dispatcher():
    pattern = re.compile(r"^function\s+mcpDispatchV6\s*\(", re.MULTILINE)
    owners = [
        relative(path) for path in engine_sources()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert owners == ["muejeje_pts/script-engine/210_dispatcher_v6.js"], owners


def test_the_dispatcher_holds_no_operation_implementation():
    body = (SCRIPT_ENGINE / "210_dispatcher_v6.js").read_text(encoding="utf-8")
    for owned_by_the_operation in (
        "extension_name", "extension_version", "supported_features",
    ):
        assert owned_by_the_operation not in body, (
            "the dispatcher whitelists and dispatches; it never implements an "
            f"operation: {owned_by_the_operation}"
        )


def test_the_protocol_module_holds_no_operation_and_no_whitelist():
    body = (SCRIPT_ENGINE / "020_protocol_v6.js").read_text(encoding="utf-8")
    assert "runtime.identify" not in body, (
        "protocol_v6 shapes envelopes; which operations exist is dispatch"
    )


def test_the_protocol_module_shapes_answers_and_reads_no_request():
    """The envelope and the admission that uses it are two responsibilities.

    `020_protocol_v6.js` used to hold both, and the bounded admission rules would
    have pushed it past its budget — which is the budget working (MJ-020).
    Reading a request is now `030_validation_v6.js`, and the split is asserted so
    the two cannot quietly merge back.
    """
    body = (SCRIPT_ENGINE / "020_protocol_v6.js").read_text(encoding="utf-8")
    for owned_by_admission in ("JSON.parse", "MUEJEJE_V6_LIMITS", "muejejeV6ParseRequest"):
        assert owned_by_admission not in body, owned_by_admission


def test_core_is_constants_and_session_state_only():
    body = (SCRIPT_ENGINE / "010_core.js").read_text(encoding="utf-8")
    for owned_elsewhere in ("mcpDispatchV6", "JSON.parse", "runtime.identify"):
        assert owned_elsewhere not in body, owned_elsewhere


def test_no_v5_fallback_survives_anywhere_in_the_kernel():
    for path in engine_sources():
        body = path.read_text(encoding="utf-8")
        assert "mcpDispatch(" not in body, relative(path)
        assert '"v": 5' not in body and '"v":5' not in body, relative(path)
