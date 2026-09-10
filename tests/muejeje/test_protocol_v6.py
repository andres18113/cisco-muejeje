"""The Runtime Protocol V6 envelope, whitelist and failure taxonomy.

Executable claims, driven through Node when it is available: what a valid
request answers with, what each rejection class is called, that the entry point
answers even when the engine itself breaks, and that `ENGINE_EXCEPTION` means
only that.

Where the kernel lives and who owns what is `test_kernel_layout`. Node
establishes what *our* JavaScript does; it establishes nothing about Packet
Tracer, whose engine is a different one (MJ-015). A Node-verified kernel is
`V6_KERNEL_RUNTIME = VERIFIED` for our logic and still
`NOT_YET_LIVE_VERIFIED` against `9.0.1.0858`.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.muejeje import engine_harness
from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import (
    engine_sources,
    relative,
)
from tests.muejeje.support import (
    MUEJEJE_TESTS,
    REPO_ROOT,
    SCRIPT_ENGINE,
    repo_manifest,
)

VALID_REQUEST = {
    "v": 6, "operation_rid": "rid-123", "op": "runtime.identify", "args": {},
}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


@pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)
@pytest.mark.parametrize("broken", [
    "muejejeV6ParseRequest", "muejejeV6OperationTable", "muejejeV6ArgsError",
    "muejejeV6Encode",
])
def test_the_entry_point_answers_even_when_the_engine_itself_breaks(broken: str):
    """Never throwing is enforced here, not assumed of everything called.

    Admission, the whitelist lookup, the argument rules and the encoder are
    ordinary code and can fail the way ordinary code does. An uncaught error
    inside a Script Engine call is not something a consumer can correlate,
    diagnose or retry, so each of those is broken in turn and the entry point
    still has to answer with an envelope — `ENGINE_EXCEPTION`, which is what
    "the engine itself broke" means, and never a code that would send a
    consumer looking at its own request (MJ-022).
    """
    response = dispatch_v6(
        json.dumps(VALID_REQUEST),
        prelude=f"{broken} = function () {{ throw new Error('engine defect'); }};",
        report="JSON.parse(mcpDispatchV6(REQUEST))",
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "ENGINE_EXCEPTION"
    assert response["result"] is None
    assert "engine defect" not in json.dumps(response)


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
def test_the_last_resort_envelope_is_the_one_the_kernel_would_have_shaped():
    """The single hard-coded envelope in this artifact, held to the contract.

    It exists so the engine can still answer when the *encoder* is what broke,
    which means it cannot be built by the encoder. That makes it a second copy
    of the envelope shape, and a second copy is only safe while something
    compares it with the first — so this parses the literal and asserts it is
    exactly what `muejejeV6Fail` produces for the same failure, field for field.
    """
    observed = dispatch_v6(
        json.dumps(VALID_REQUEST),
        report=(
            "{literal: JSON.parse(MUEJEJE_V6_ENGINE_FAILURE),"
            " shaped: muejejeV6Fail(null, null,"
            "   MUEJEJE_V6_ERRORS.ENGINE_EXCEPTION, MUEJEJE_V6_ENGINE_MESSAGE)}"
        ),
    )

    assert observed["literal"] == observed["shaped"]


def test_the_dispatcher_returns_a_json_string_not_an_object():
    """`mcpDispatchV6` is called across the Script Engine boundary."""
    kind = dispatch_v6(
        json.dumps(VALID_REQUEST), report="typeof mcpDispatchV6(REQUEST)",
    )
    assert kind == "string"
