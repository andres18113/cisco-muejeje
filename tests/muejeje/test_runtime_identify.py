"""`runtime.identify`: the first V6 operation, and what it may claim.

It is read-only, makes no Cisco IPC call, and reports only facts this artifact
can establish about itself. The interesting assertions here are the negative
ones: what it must *not* invent (MJ-010, MJ-017).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.support import SCRIPT_ENGINE, repo_manifest

IDENTIFY = json.dumps({
    "v": 6, "operation_rid": "rid-identify", "op": "runtime.identify", "args": {},
})

RESULT_FIELDS = {
    "extension_name", "extension_version", "protocol_versions", "operations",
    "supported_features", "runtime_session_id", "provenance", "lifecycle",
}

requires_node = pytest.mark.skipif(
    not node_available(), reason="Node is unavailable; structural gates still run",
)


def _result() -> dict:
    return dispatch_v6(IDENTIFY)["result"]


# ---------------------------------------------------------------------------
# Structural: read-only, and no platform dependency.
# ---------------------------------------------------------------------------

def test_the_operation_makes_no_platform_call_and_mutates_nothing():
    body = (SCRIPT_ENGINE / "runtime_identity.js").read_text(encoding="utf-8")
    assert "ipc." not in body, "runtime.identify is read-only and needs no privilege"
    # It reads core; it never writes to it.
    assert "MUEJEJE_CORE.session." not in body
    assert "muejejeCoreMark" not in body


def test_the_operation_does_not_reach_into_the_dispatcher():
    """The whitelist has one owner; the operation is handed the list."""
    body = (SCRIPT_ENGINE / "runtime_identity.js").read_text(encoding="utf-8")
    assert "muejejeV6OperationTable" not in body
    assert "MUEJEJE_V6_DISPATCH" not in body


def test_the_artifact_never_embeds_its_own_hash():
    """A self-embedded artifact hash cannot be checked (MJ-017)."""
    for path in sorted(SCRIPT_ENGINE.glob("*.js")):
        body = path.read_text(encoding="utf-8")
        assert "ARTIFACT_SHA256" not in body, path.name


# ---------------------------------------------------------------------------
# Executable: the result shape.
# ---------------------------------------------------------------------------

@requires_node
def test_the_result_carries_exactly_the_declared_fields():
    assert set(_result()) == RESULT_FIELDS


@requires_node
def test_the_reported_identity_matches_the_manifest():
    extension = repo_manifest()["extension"]
    result = _result()

    assert result["extension_name"] == extension["name"]
    assert result["extension_version"] == extension["version"]


@requires_node
def test_the_reported_protocol_and_operations_are_what_the_kernel_admits():
    result = _result()

    assert result["protocol_versions"] == [6]
    assert result["operations"] == ["runtime.identify"]
    assert result["supported_features"] == ["protocol.v6", "runtime.session_id"]


@requires_node
def test_every_declared_feature_is_backed_by_kernel_source():
    """A feature list is a promise. Each entry names something that exists."""
    evidence = {
        "protocol.v6": ("protocol_v6.js", "muejejeV6ParseRequest"),
        "runtime.session_id": ("core.js", "muejejeCoreNewSessionId"),
    }
    for feature in _result()["supported_features"]:
        assert feature in evidence, f"{feature} names nothing in this artifact"
        name, symbol = evidence[feature]
        assert symbol in (SCRIPT_ENGINE / name).read_text(encoding="utf-8")


@requires_node
def test_provenance_is_reported_unbound_rather_than_invented():
    provenance = _result()["provenance"]

    assert provenance == {
        "state": "UNBOUND", "source_sha": None, "build_recipe_id": None,
    }, "nothing binds a source SHA or recipe id into the runtime yet"


# ---------------------------------------------------------------------------
# runtime_session_id: stable within a session, different between sessions.
# ---------------------------------------------------------------------------

@requires_node
def test_the_session_id_is_stable_across_calls_within_one_session():
    both = dispatch_v6(
        IDENTIFY,
        report=(
            "[JSON.parse(mcpDispatchV6(REQUEST)).result.runtime_session_id,"
            " JSON.parse(mcpDispatchV6(REQUEST)).result.runtime_session_id]"
        ),
    )
    assert both[0] == both[1]
    assert both[0]


@requires_node
def test_the_session_id_survives_a_restart_within_the_same_session():
    """`main()` may run more than once; the session is the evaluation, not the run."""
    observed = dispatch_v6(
        IDENTIFY,
        prelude="main(); cleanUp(); main();",
        report=(
            "{first: MUEJEJE_CORE.session.id,"
            " reported: JSON.parse(mcpDispatchV6(REQUEST)).result}"
        ),
    )
    assert observed["reported"]["runtime_session_id"] == observed["first"]
    assert observed["reported"]["lifecycle"]["start_count"] == 2
    assert observed["reported"]["lifecycle"]["started"] is True


@requires_node
def test_the_session_id_differs_between_sessions():
    """Two Node processes are two evaluations, which are two sessions."""
    first = _result()["runtime_session_id"]
    second = _result()["runtime_session_id"]
    assert first != second


@requires_node
def test_the_session_id_is_a_plain_correlation_token():
    session_id = _result()["runtime_session_id"]

    assert isinstance(session_id, str)
    assert session_id.startswith("mjs-")
    # Non-secret by construction: short, printable, and derived from nothing a
    # caller could not have generated. It is correlation evidence, never
    # authentication, and the kernel never checks it against anything.
    assert 8 <= len(session_id) <= 64
    assert "muejejeV6ParseRequest" not in json.dumps(_result())
    for source in sorted(SCRIPT_ENGINE.glob("*.js")):
        body = source.read_text(encoding="utf-8")
        assert "session.id ===" not in body, (
            f"{source.name} compares the session id; it authenticates nothing"
        )


@requires_node
def test_the_lifecycle_block_reports_a_module_that_has_not_started():
    lifecycle = _result()["lifecycle"]

    assert lifecycle == {
        "started": False, "started_at": None, "stopped_at": None,
        "start_count": 0,
    }


@requires_node
def test_the_lifecycle_block_reflects_a_started_module():
    result = dispatch_v6(IDENTIFY, prelude="main();")["result"]

    assert result["lifecycle"]["started"] is True
    assert result["lifecycle"]["start_count"] == 1
    assert isinstance(result["lifecycle"]["started_at"], int)
    assert result["lifecycle"]["stopped_at"] is None
