"""`runtime.identify`: the first V6 operation, and what it may claim.

It is read-only, makes no Cisco IPC call, and reports only facts this artifact
can establish about itself. The interesting assertions here are the negative
ones: what it must *not* invent (MJ-010, MJ-017).
"""

from __future__ import annotations

import json

import pytest

from tests.muejeje.engine_harness import dispatch_v6, node_available
from tests.muejeje.support import FEATURE_EVIDENCE, SCRIPT_ENGINE, repo_manifest

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
    assert result["operations"] == [
        "platform.device_descriptors", "runtime.capabilities", "runtime.identify",
    ]
    assert result["supported_features"] == [
        "platform.descriptor_discovery", "protocol.v6",
        "runtime.operation_catalog", "runtime.session_id",
    ]


@requires_node
def test_every_declared_feature_is_backed_by_kernel_source():
    """A feature list is a promise. Each entry names something that exists."""
    for feature in _result()["supported_features"]:
        assert feature in FEATURE_EVIDENCE, f"{feature} names nothing in this artifact"
        name, symbol = FEATURE_EVIDENCE[feature]
        assert symbol in (SCRIPT_ENGINE / name).read_text(encoding="utf-8")


@requires_node
def test_provenance_is_reported_unbound_rather_than_invented():
    provenance = _result()["provenance"]

    assert provenance == {
        "state": "UNBOUND", "source_sha": None, "build_recipe_id": None,
    }, "nothing binds a source SHA or recipe id into the runtime yet"


# ---------------------------------------------------------------------------
# runtime_session_id: one token per engine evaluation, and nothing wider.
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
def test_calling_the_lifecycle_twice_rebinds_no_token_and_is_only_bookkeeping():
    """What our own `main()`/`cleanUp()` record, and nothing more than that.

    This calls the two functions directly, in one Node evaluation. It
    establishes that the token is bound at evaluation time rather than at
    startup, and that the lifecycle counter counts the calls it saw. It
    establishes **nothing** about Packet Tracer's stop/start semantics: an
    earlier revision read exactly this run as evidence that "restarting the
    module is not re-evaluating it", which is a claim about PT that Cisco's
    own reference contradicts — every script file is evaluated when the module
    starts, so a restart is a new evaluation and a new token (MJ-015, MJ-023).

    Whether PT ever calls `main()` twice inside one evaluation is not
    documented and is not claimed here; the counter exists so a reader can
    tell one call from two, not to predict how many PT will make.
    """
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


def test_the_session_token_is_generated_exactly_once_per_evaluation():
    """The scope of the token is the evaluation, and it is set there once.

    An earlier test asserted that two evaluations produce *different* tokens.
    Nothing in the kernel guarantees that — the token is a clock reading and a
    random draw — so the assertion was probabilistic, and a gate that can fail
    without anything being wrong teaches people to re-run it. What the kernel
    does guarantee is asserted instead: one generation site, one assignment,
    at evaluation time (MJ-023).
    """
    body = (SCRIPT_ENGINE / "core.js").read_text(encoding="utf-8")

    assert body.count("MUEJEJE_CORE.session.id = ") == 1
    assert body.count("function muejejeCoreNewSessionId(") == 1
    for source in sorted(SCRIPT_ENGINE.glob("*.js")):
        if source.name == "core.js":
            continue
        other = source.read_text(encoding="utf-8")
        assert "muejejeCoreNewSessionId" not in other, (
            f"{source.name} may not mint a second token for one evaluation"
        )


@requires_node
def test_regenerating_the_token_does_not_change_the_session():
    """Calling the generator again mints a value; it never rebinds the session."""
    observed = dispatch_v6(
        IDENTIFY,
        prelude=(
            "var before = MUEJEJE_CORE.session.id;"
            " var minted = muejejeCoreNewSessionId();"
        ),
        report=(
            "{before: before, after: MUEJEJE_CORE.session.id,"
            " minted_type: typeof minted,"
            " reported: JSON.parse(mcpDispatchV6(REQUEST)).result.runtime_session_id}"
        ),
    )
    assert observed["minted_type"] == "string"
    assert observed["after"] == observed["before"]
    assert observed["reported"] == observed["before"]


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
