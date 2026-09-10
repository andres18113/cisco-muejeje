"""What may change in V6 without breaking a consumer, and what may not.

V6 is the contract Muejeje owns and publishes (MJ-005), so "we changed the
runtime" and "we broke our consumers" have to be different events. The rule is
one sentence, and this module is that sentence as a gate (MJ-030):

    A result may gain a field. Nothing may lose one, be renamed, or keep its
    name while meaning something else.

That is why the two kinds of set below are asserted differently. The envelope
and the error taxonomy are asserted **equal** to what the kernel declares: a
consumer's parser is total over those, so adding to them breaks an exhaustive
reader exactly as removing from them breaks a field access. Each operation's
required result fields are asserted as a **subset** of what it answers: a new
field is invisible to a consumer that does not read it.

None of this is a claim about Packet Tracer. It is a claim about the contract
we publish, checked against the kernel that implements it under Node (MJ-015).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.support import REPO_ROOT, SCRIPT_ENGINE

# The frozen V6 surface. Every entry here is a promise already made, so an
# edit to this file is the visible moment a consumer-facing contract changes.
REQUEST_FIELDS = {"v", "operation_rid", "op", "args"}
RESPONSE_FIELDS = {"v", "operation_rid", "op", "ok", "result", "error"}
ERROR_FIELDS = {"code", "message"}
ERROR_CODES = {
    "MALFORMED_REQUEST", "PROTOCOL_MISMATCH", "INVALID_REQUEST",
    "UNKNOWN_OPERATION", "INVALID_ARGS", "ENGINE_EXCEPTION",
}

# Per operation, the result fields a consumer may already be reading. An
# operation may answer with more; it may never answer with fewer.
REQUIRED_RESULT_FIELDS = {
    "platform.device_descriptors": {
        "resolution", "unavailable_reason", "available_count", "offset",
        "limit", "descriptors", "window_truncated",
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

# An operation published as read-only may never become mutating under the same
# name. A consumer decides whether it may call something from this flag, so
# changing it is changing what the name means, not extending it. A mutating
# operation is a new name (MJ-008).
READ_ONLY_OPERATIONS = {
    "platform.device_descriptors", "runtime.capabilities", "runtime.identify",
}

REQUIREMENTS = "docs/architecture/muejeje-pts-requirements.md"

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def missing_fields(frozen: set[str], observed: set[str]) -> set[str]:
    """The frozen fields `observed` no longer carries. Empty means compatible.

    This is the whole compatibility test for a result: a field that appeared is
    not in `frozen`, so it cannot show up here, while a field that was removed
    or renamed leaves its old name behind and does.
    """
    return frozen - observed


def _request(op: str) -> str:
    return json.dumps({
        "v": 6, "operation_rid": f"rid-compat-{op}", "op": op, "args": {},
    })


# ---------------------------------------------------------------------------
# The gate can tell an addition from a removal.
# ---------------------------------------------------------------------------

def test_the_compatibility_measure_admits_additions_and_catches_the_rest():
    """Asserted on synthetic field sets, in every direction that matters.

    A gate that reported "different" would fail on a compatible change and
    teach the next reader to edit the frozen set to make it pass, which is
    exactly how a breaking change gets waved through.
    """
    frozen = {"model", "device_type"}

    assert missing_fields(frozen, {"model", "device_type"}) == set()
    assert missing_fields(frozen, {"model", "device_type", "slot_types"}) == set()
    assert missing_fields(frozen, {"model"}) == {"device_type"}
    assert missing_fields(frozen, {"model", "deviceType"}) == {"device_type"}


# ---------------------------------------------------------------------------
# The envelope and the taxonomy are closed sets.
# ---------------------------------------------------------------------------

def test_the_request_envelope_carries_exactly_the_published_fields():
    """Adding a required request field would refuse every existing caller."""
    body = (SCRIPT_ENGINE / "validation_v6.js").read_text(encoding="utf-8")
    declared = body.split("MUEJEJE_V6_ENVELOPE_FIELDS = ")[1].split(";")[0]

    assert set(json.loads(declared)) == REQUEST_FIELDS


@requires_node
def test_the_response_envelope_carries_exactly_the_published_fields():
    for op in sorted(REQUIRED_RESULT_FIELDS):
        assert set(dispatch_v6(_request(op))) == RESPONSE_FIELDS


@requires_node
def test_the_failure_taxonomy_is_closed():
    """A seventh code breaks every consumer that switches on the six.

    Which is why a bound refuses with one of the existing codes rather than
    introducing one of its own (MJ-029).
    """
    codes = dispatch_v6(_request("runtime.identify"), report="MUEJEJE_V6_ERRORS")

    assert set(codes) == ERROR_CODES
    assert set(codes.values()) == ERROR_CODES, "a code's own value is its name"


@requires_node
def test_an_error_carries_exactly_a_code_and_a_message():
    failed = dispatch_v6(json.dumps({
        "v": 6, "operation_rid": "rid-compat", "op": "runtime.reboot", "args": {},
    }))

    assert set(failed["error"]) == ERROR_FIELDS
    assert failed["error"]["code"] in ERROR_CODES


# ---------------------------------------------------------------------------
# A result may grow. It may not shrink, rename, or change meaning.
# ---------------------------------------------------------------------------

@requires_node
@pytest.mark.parametrize("op", sorted(REQUIRED_RESULT_FIELDS))
def test_a_result_still_carries_every_field_already_published(op: str):
    observed = set(dispatch_v6(_request(op))["result"])

    assert missing_fields(REQUIRED_RESULT_FIELDS[op], observed) == set(), (
        f"{op} dropped or renamed a published field; that needs a new protocol "
        "version, not a new field list"
    )


def test_every_admitted_operation_publishes_a_frozen_result_shape():
    """An operation with no frozen shape is one nothing is holding still.

    Adding an operation therefore means declaring what its result promises, in
    the same commit — not later, once a consumer has started reading it.
    """
    from tests.muejeje.test_capability_claims import admitted_operations

    assert set(REQUIRED_RESULT_FIELDS) == admitted_operations()


@requires_node
def test_an_operation_published_as_read_only_stays_read_only():
    """Read-only is a meaning, not a field. Changing it renames nothing."""
    catalog = dispatch_v6(
        _request("runtime.capabilities"), report="muejejeV6OperationCatalog()",
    )
    read_only = {entry["op"] for entry in catalog if entry["read_only"] is True}

    assert READ_ONLY_OPERATIONS <= read_only, (
        "an operation that stops being read-only has changed what its name "
        f"means: {sorted(READ_ONLY_OPERATIONS - read_only)}"
    )


# ---------------------------------------------------------------------------
# The semantics that carry no field of their own.
# ---------------------------------------------------------------------------

@requires_node
def test_success_and_failure_stay_mutually_exclusive():
    ok = dispatch_v6(_request("runtime.identify"))
    failed = dispatch_v6(json.dumps({
        "v": 6, "operation_rid": "rid-compat", "op": "runtime.reboot", "args": {},
    }))

    assert ok["ok"] is True and ok["error"] is None
    assert isinstance(ok["result"], dict)
    assert failed["ok"] is False and failed["result"] is None
    assert isinstance(failed["error"], dict)


@requires_node
def test_the_entry_point_keeps_taking_and_returning_a_json_string():
    """The one signature a consumer cannot adapt to a change in."""
    kind = dispatch_v6(
        _request("runtime.identify"),
        report="typeof mcpDispatchV6(REQUEST)",
    )
    assert kind == "string"


@requires_node
def test_the_declared_protocol_version_does_not_move_under_a_consumer():
    """A V6 answer says 6. A different number is a different contract."""
    response = dispatch_v6(_request("runtime.identify"))

    assert response["v"] == 6
    assert response["result"]["protocol_versions"] == [6]


# ---------------------------------------------------------------------------
# The rule is written down where a consumer can read it.
# ---------------------------------------------------------------------------

def test_the_evolution_rule_is_stated_in_the_requirements_baseline():
    """A gate with no stated rule behind it is a habit nobody agreed to.

    Both halves have to be written down, because either half alone is a
    different rule: "additive fields are allowed" without "a removal is
    breaking" reads as permission to reshape a result freely.
    """
    body = (REPO_ROOT / REQUIREMENTS).read_text(encoding="utf-8")
    heading = "### MJ-030"

    assert heading in body, "the compatibility rule has no requirement id"
    rule = body.split(heading)[1].split("\n### ")[0]
    for half in ("additive", "breaking"):
        assert half in rule.lower(), half
