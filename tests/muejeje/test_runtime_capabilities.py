"""`runtime.capabilities`: what this kernel admits, and only what it admits.

The operation exists so a consumer can discover the contract instead of
assuming it. That only works if the answer is measured from the kernel rather
than written down beside it, so the assertions here compare the reported
capabilities against the dispatcher and the core that produce them — and
against `runtime.identify`, which must never disagree (MJ-008, MJ-025).

The negative claims carry as much weight as the positive ones: nothing here
may promise a transport, a platform call or an operation that does not exist,
and nothing here may certify its own verification (MJ-011).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.measure import (
    engine_sources,
    relative,
)
from tests.muejeje.support import (
    FEATURE_EVIDENCE,
    SCRIPT_ENGINE,
)

CAPABILITIES = json.dumps({
    "v": 6, "operation_rid": "rid-capabilities", "op": "runtime.capabilities",
    "args": {},
})
IDENTIFY = json.dumps({
    "v": 6, "operation_rid": "rid-identify", "op": "runtime.identify", "args": {},
})

RESULT_FIELDS = {
    "runtime_session_id", "protocol_versions", "operations", "supported_features",
}
ADMITTED = [
    "network.device_identity", "network.device_inventory",
    "platform.device_descriptors",
    "platform.module_descriptors", "platform.module_type_support",
    "runtime.capabilities", "runtime.identify",
]
FEATURES = 8

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _result() -> dict:
    return dispatch_v6(CAPABILITIES)["result"]


# ---------------------------------------------------------------------------
# Structural: read-only, IPC-free, and no reach into the dispatcher.
# ---------------------------------------------------------------------------

def test_the_operation_has_its_own_file_and_does_not_grow_the_dispatcher():
    """A second operation is a second file, not a longer dispatcher (MJ-018)."""
    body = (SCRIPT_ENGINE / "runtime_capabilities.js").read_text(encoding="utf-8")
    assert "function muejejeRuntimeCapabilities(" in body
    dispatcher = (SCRIPT_ENGINE / "dispatcher_v6.js").read_text(encoding="utf-8")
    assert "supported_features" not in dispatcher
    assert "protocol_versions" not in dispatcher


def test_the_operation_makes_no_platform_call_and_mutates_nothing():
    body = (SCRIPT_ENGINE / "runtime_capabilities.js").read_text(encoding="utf-8")
    assert "ipc." not in body, "runtime.capabilities is read-only and needs no privilege"
    assert "MUEJEJE_CORE.session." not in body
    assert "muejejeCoreMark" not in body


def test_the_operation_does_not_reach_into_the_dispatcher():
    """The whitelist has one owner; the operation is handed the catalogue."""
    body = (SCRIPT_ENGINE / "runtime_capabilities.js").read_text(encoding="utf-8")
    assert "muejejeV6OperationTable" not in body
    assert "MUEJEJE_V6_DISPATCH" not in body


def test_the_operation_catalogue_is_derived_where_the_whitelist_lives():
    owners = [
        relative(path) for path in engine_sources()
        if "function muejejeV6OperationCatalog(" in path.read_text(encoding="utf-8")
    ]
    assert owners == ["muejeje_pts/script-engine/dispatcher_v6.js"], owners


# ---------------------------------------------------------------------------
# Executable: the reported capabilities.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_carries_exactly_the_declared_fields():
    assert set(_result()) == RESULT_FIELDS


@requires_node
def test_the_whitelist_admits_exactly_these_read_only_operations():
    operations = _result()["operations"]

    assert [entry["op"] for entry in operations] == ADMITTED
    assert all(entry["read_only"] is True for entry in operations)
    assert all(set(entry) == {"op", "read_only"} for entry in operations)


@requires_node
def test_the_reported_protocol_is_the_only_one_the_kernel_speaks():
    assert _result()["protocol_versions"] == [6]


@requires_node
def test_the_two_read_only_operations_report_the_same_whitelist():
    """One whitelist, two views of it. A disagreement is a second whitelist.

    Both are asked inside a single evaluation, because that is the scope the
    session token is defined over: two Node processes are two evaluations and
    would differ there legitimately (MJ-023).
    """
    both = dispatch_v6(
        CAPABILITIES,
        prelude=f"var IDENTIFY = {json.dumps(IDENTIFY)};",
        report=(
            "{capabilities: JSON.parse(mcpDispatchV6(REQUEST)).result,"
            " identity: JSON.parse(mcpDispatchV6(IDENTIFY)).result}"
        ),
    )
    capabilities, identity = both["capabilities"], both["identity"]

    assert [entry["op"] for entry in capabilities["operations"]] == identity["operations"]
    assert capabilities["supported_features"] == identity["supported_features"]
    assert capabilities["runtime_session_id"] == identity["runtime_session_id"]


@requires_node
def test_every_reported_feature_names_something_in_this_artifact():
    """A capability report is a promise. Each entry names existing code.

    The map is the point: a feature added to the list without code behind it
    fails here, which is what stops the report from drifting into a roadmap.
    It is single-sourced in `support`, because two copies of it could disagree
    and a feature backed by only one would be a claim nobody was checking.
    """
    for feature in _result()["supported_features"]:
        assert feature in FEATURE_EVIDENCE, f"{feature} names nothing in this artifact"
        name, symbol = FEATURE_EVIDENCE[feature]
        assert symbol in (SCRIPT_ENGINE / name).read_text(encoding="utf-8")


@requires_node
def test_the_report_names_no_roadmap_and_no_layer_the_kernel_does_not_have():
    """A capability that does not exist is absent, never listed as pending.

    An earlier revision also forbade the words "device", "platform" and "ipc",
    which was the same rule as "there is no platform adapter" — true then, and
    it would have had to be deleted the moment one arrived. What must stay
    forbidden is the vocabulary of things this kernel genuinely does not have,
    and of things nothing can have: a roadmap entry a consumer cannot act on
    (MJ-028).
    """
    reported = json.dumps(_result()).lower()
    for absent in (
        "http", "bridge", "mailbox", "polling", "transport", "batch",
        "topology", "write", "mutate", "planned", "roadmap", "pending",
        "future", "coming",
    ):
        assert absent not in reported, f"the report mentions {absent}"


@requires_node
def test_the_report_makes_no_platform_call_and_carries_no_observation():
    """It answers what the kernel admits, not what the platform said.

    A platform capability now exists, and this operation still does not use
    it: whether Packet Tracer answers is what `platform.device_descriptors`
    reports, when a consumer asks. Folding a reading into the capability
    report would make discovery depend on a platform call and turn one
    unavailable platform into "this runtime has no capabilities" (MJ-028).
    """
    body = (SCRIPT_ENGINE / "runtime_capabilities.js").read_text(encoding="utf-8")
    assert "muejejeAdapter" not in body
    assert "MUEJEJE_PLATFORM" not in body

    reported = json.dumps(_result())
    for observation in ("resolution", "available_count", "unavailable_reason"):
        assert observation not in reported, observation


@requires_node
def test_the_runtime_certifies_no_verification_of_its_own():
    reported = json.dumps(_result())
    for verdict in ("VERIFIED", "QUALIFIED", "ATTESTED", "PASS"):
        assert verdict not in reported, (
            f"Python owns verification; the runtime observes: {verdict}"
        )


@requires_node
def test_the_answer_carries_copies_of_the_kernel_state_it_reports():
    """Mutating a reply must not reach the constants it was built from.

    Asserted *in-engine*, on the handler's own return value, because across
    the Script Engine boundary the reply is JSON and copying is implicit — a
    test that mutated the parsed envelope would pass no matter what the
    handler did. The reachable target is `MUEJEJE_CORE`: a handler that
    returned its arrays instead of `slice(0)` copies would let one caller's
    reply permanently extend the kernel's feature list.
    """
    observed = dispatch_v6(
        CAPABILITIES,
        prelude=(
            "var context = {operations: muejejeV6OperationNames(),"
            " operation_catalog: muejejeV6OperationCatalog()};"
            " var direct = muejejeRuntimeCapabilities({}, context);"
            " direct.supported_features.push('transport.http');"
            " direct.protocol_versions.push(5);"
            " direct.operations.push({op: 'device.add', read_only: false});"
            " var identity = muejejeRuntimeIdentify({}, context);"
            " identity.supported_features.push('transport.http');"
            " identity.protocol_versions.push(5);"
        ),
        report=(
            "{features: MUEJEJE_CORE.SUPPORTED_FEATURES.length,"
            " protocols: MUEJEJE_CORE.PROTOCOL_VERSIONS.length,"
            " admitted: muejejeV6OperationNames().length,"
            " reported: JSON.parse(mcpDispatchV6(REQUEST)).result}"
        ),
    )

    assert observed["features"] == FEATURES
    assert observed["protocols"] == 1
    assert observed["admitted"] == len(ADMITTED)
    assert [entry["op"] for entry in observed["reported"]["operations"]] == ADMITTED
    assert observed["reported"]["protocol_versions"] == [6]


@requires_node
def test_the_operation_takes_no_arguments():
    response = dispatch_v6(json.dumps({
        "v": 6, "operation_rid": "rid-args", "op": "runtime.capabilities",
        "args": {"verbose": True},
    }))
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_ARGS"
