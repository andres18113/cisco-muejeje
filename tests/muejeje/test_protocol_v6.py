"""The Runtime Protocol V6 envelope, whitelist and failure taxonomy.

Structural claims about the source layout, plus executable claims driven
through Node when it is available. Node establishes what *our* JavaScript does;
it establishes nothing about Packet Tracer, whose engine is a different one
(MJ-015). A Node-verified kernel is `V6_KERNEL_RUNTIME = VERIFIED` for our
logic and still `NOT_YET_LIVE_VERIFIED` against `9.0.1.0858`.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje import engine_harness
from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.support import (
    MUEJEJE_TESTS,
    REPO_ROOT,
    SCRIPT_ENGINE,
    engine_sources,
    relative,
    repo_manifest,
)

# The declared evaluation order, written down exactly once. Packet Tracer
# evaluates the Script Engine files in the order the Scripting Interface lists
# them, so this order *is* the dependency direction: core, the protocol
# envelope, the admission that refuses with that envelope, then operations,
# then dispatch, then the lifecycle that may call all of it (MJ-019).
# Operations depend on nothing but core and protocol, so they are ordered
# alphabetically among themselves — a rule, rather than an accident nobody
# could re-derive.
#
# This list is the expectation; the manifest is the source every other reader
# derives from. One written-down copy is what makes a reorder a visible edit
# here instead of a silent drift everywhere.
ENGINE_SCRIPT_ORDER = [
    "muejeje_pts/script-engine/core.js",
    "muejeje_pts/script-engine/protocol_v6.js",
    "muejeje_pts/script-engine/validation_v6.js",
    "muejeje_pts/script-engine/runtime_capabilities.js",
    "muejeje_pts/script-engine/runtime_identity.js",
    "muejeje_pts/script-engine/dispatcher_v6.js",
    "muejeje_pts/script-engine/lifecycle.js",
]

VALID_REQUEST = {
    "v": 6, "operation_rid": "rid-123", "op": "runtime.identify", "args": {},
}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


# ---------------------------------------------------------------------------
# Structural: the layout, and who owns what.
# ---------------------------------------------------------------------------

def test_the_kernel_is_split_into_the_declared_files():
    on_disk = [relative(path) for path in engine_sources()]
    assert sorted(on_disk) == sorted(ENGINE_SCRIPT_ORDER)


def test_engine_script_order_is_the_declared_dependency_order():
    order = repo_manifest()["build_options"]["engine_script_order"]
    assert order == ENGINE_SCRIPT_ORDER, (
        "core and protocol first, then operations, then dispatch, then lifecycle"
    )
    assert set(order) == {relative(path) for path in engine_sources()}


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


def test_mcp_dispatch_v6_is_implemented_exactly_once_by_the_dispatcher():
    pattern = re.compile(r"^function\s+mcpDispatchV6\s*\(", re.MULTILINE)
    owners = [
        relative(path) for path in engine_sources()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert owners == ["muejeje_pts/script-engine/dispatcher_v6.js"], owners


def test_the_dispatcher_holds_no_operation_implementation():
    body = (SCRIPT_ENGINE / "dispatcher_v6.js").read_text(encoding="utf-8")
    for owned_by_the_operation in (
        "extension_name", "extension_version", "supported_features",
    ):
        assert owned_by_the_operation not in body, (
            "the dispatcher whitelists and dispatches; it never implements an "
            f"operation: {owned_by_the_operation}"
        )


def test_the_protocol_module_holds_no_operation_and_no_whitelist():
    body = (SCRIPT_ENGINE / "protocol_v6.js").read_text(encoding="utf-8")
    assert "runtime.identify" not in body, (
        "protocol_v6 shapes envelopes; which operations exist is dispatch"
    )


def test_the_protocol_module_shapes_answers_and_reads_no_request():
    """The envelope and the admission that uses it are two responsibilities.

    `protocol_v6.js` used to hold both, and the bounded admission rules would
    have pushed it past its budget — which is the budget working (MJ-020).
    Reading a request is now `validation_v6.js`, and the split is asserted so
    the two cannot quietly merge back.
    """
    body = (SCRIPT_ENGINE / "protocol_v6.js").read_text(encoding="utf-8")
    for owned_by_admission in ("JSON.parse", "MUEJEJE_V6_LIMITS", "muejejeV6ParseRequest"):
        assert owned_by_admission not in body, owned_by_admission


def test_core_is_constants_and_session_state_only():
    body = (SCRIPT_ENGINE / "core.js").read_text(encoding="utf-8")
    for owned_elsewhere in ("mcpDispatchV6", "JSON.parse", "runtime.identify"):
        assert owned_elsewhere not in body, owned_elsewhere


def test_no_v5_fallback_survives_anywhere_in_the_kernel():
    for path in engine_sources():
        body = path.read_text(encoding="utf-8")
        assert "mcpDispatch(" not in body, relative(path)
        assert '"v": 5' not in body and '"v":5' not in body, relative(path)


# ---------------------------------------------------------------------------
# Executable: the contract itself.
# ---------------------------------------------------------------------------

@requires_node
def test_a_valid_request_returns_a_successful_envelope():
    response = dispatch_v6(json.dumps(VALID_REQUEST))

    assert response["v"] == 6
    assert response["ok"] is True
    assert response["operation_rid"] == "rid-123"
    assert response["op"] == "runtime.identify"
    assert response["error"] is None
    assert isinstance(response["result"], dict)


@requires_node
def test_the_response_envelope_shape_is_the_same_for_success_and_failure():
    ok = dispatch_v6(json.dumps(VALID_REQUEST))
    failed = dispatch_v6(json.dumps({**VALID_REQUEST, "op": "runtime.reboot"}))

    assert set(ok) == set(failed) == {
        "v", "operation_rid", "op", "ok", "result", "error",
    }
    assert failed["ok"] is False
    assert failed["result"] is None


@requires_node
def test_the_operation_rid_is_preserved_and_never_invented():
    response = dispatch_v6(json.dumps({**VALID_REQUEST, "operation_rid": "rid-xyz"}))
    assert response["operation_rid"] == "rid-xyz"

    # A request with no usable rid gets a null one back, not a generated one:
    # correlating a reply to a request nobody made is worse than not correlating.
    orphan = dispatch_v6("{not json")
    assert orphan["operation_rid"] is None


@requires_node
@pytest.mark.parametrize(
    ("request_json", "code"),
    [
        ("{not json", "MALFORMED_REQUEST"),
        ("[]", "MALFORMED_REQUEST"),
        ("null", "MALFORMED_REQUEST"),
        ('"a string"', "MALFORMED_REQUEST"),
        ('{"v":5,"operation_rid":"r","op":"runtime.identify","args":{}}',
         "PROTOCOL_MISMATCH"),
        ('{"v":"6","operation_rid":"r","op":"runtime.identify","args":{}}',
         "PROTOCOL_MISMATCH"),
        ('{"operation_rid":"r","op":"runtime.identify","args":{}}',
         "PROTOCOL_MISMATCH"),
        ('{"v":6,"op":"runtime.identify","args":{}}', "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":"","op":"runtime.identify","args":{}}',
         "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":7,"op":"runtime.identify","args":{}}',
         "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":"r","args":{}}', "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":"r","op":"runtime.identify"}', "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":"r","op":"runtime.identify","args":[]}',
         "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":"r","op":"runtime.identify","args":null}',
         "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":"r","op":"runtime.identify","args":{},"extra":1}',
         "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":"r","op":"runtime.reboot","args":{}}',
         "UNKNOWN_OPERATION"),
        ('{"v":6,"operation_rid":"r","op":"","args":{}}', "INVALID_REQUEST"),
        ('{"v":6,"operation_rid":"r","op":"runtime.identify","args":{"x":1}}',
         "INVALID_ARGS"),
    ],
)
def test_every_rejection_class_has_its_own_code(request_json: str, code: str):
    response = dispatch_v6(request_json)

    assert response["ok"] is False
    assert response["error"]["code"] == code
    assert response["result"] is None
    # A validation failure is never an engine exception: nothing went wrong
    # inside the engine, the request was simply not admissible.
    assert response["error"]["code"] != "ENGINE_EXCEPTION"


@requires_node
def test_an_unknown_operation_fails_closed_and_names_nothing_it_might_have_done():
    response = dispatch_v6(
        json.dumps({**VALID_REQUEST, "op": "device.add"})
    )
    assert response["error"]["code"] == "UNKNOWN_OPERATION"
    assert response["result"] is None
    assert "device.add" not in json.dumps(response["error"])


@requires_node
def test_a_non_string_request_is_rejected_rather_than_coerced():
    for literal in ("undefined", "null", "6", "{}"):
        response = dispatch_v6(literal, raw_argument=True)
        assert response["ok"] is False
        assert response["error"]["code"] in {
            "MALFORMED_REQUEST", "PROTOCOL_MISMATCH", "INVALID_REQUEST",
        }


@requires_node
def test_an_internal_handler_failure_is_the_only_engine_exception():
    """The taxonomy has one slot for "the engine itself broke", and it is used.

    The handler is replaced with one that throws, which is the only way to
    reach `ENGINE_EXCEPTION` — no request can reach it through validation.
    """
    response = dispatch_v6(
        json.dumps(VALID_REQUEST),
        prelude=(
            "muejejeV6OperationTable()['runtime.identify'].handler = "
            "function () { throw new Error('synthetic handler failure'); };"
        ),
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "ENGINE_EXCEPTION"
    assert response["operation_rid"] == "rid-123"


@requires_node
def test_the_dispatcher_returns_a_json_string_not_an_object():
    """`mcpDispatchV6` is called across the Script Engine boundary."""
    kind = dispatch_v6(
        json.dumps(VALID_REQUEST), report="typeof mcpDispatchV6(REQUEST)",
    )
    assert kind == "string"
