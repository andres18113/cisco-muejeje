"""Phase 1A: the pure V6 protocol model, offline.

These tests describe the protocol contract and nothing else. No transport is
imported, nothing is dispatched, and no claim is made about the Script Engine.
The runtime-session *behaviour* (first-writer-wins persistence, stability across
a webview reopen, change across a PT restart) is UNVERIFIED_UNTIL_PHASE_1B by
construction: Phase 1A sends nothing, so it can only pin schema, encoding and
parse behaviour.

The documents fed to the parser are handwritten JSON, deliberately. Serialising
our own envelope object and parsing it back would only prove the model agrees
with itself; the parser's job is to classify text that some *other* process
produced.
"""

from __future__ import annotations

import json
import typing

import pytest

from src.packet_tracer_mcp.infrastructure.execution.runtime_protocol import (
    PROTOCOL_VERSION,
    READ_ONLY_OPERATIONS,
    ProtocolParseState,
    ResultStatus,
    RuntimeErrorCode,
    SessionMintedBy,
    SessionStorage,
    is_valid_operation_name,
    is_valid_operation_rid,
    new_operation_rid,
    new_session_candidate,
    parse_runtime_result,
)


# --------------------------------------------------------------- helpers ---

#: The one operation Phase 1A encodes, and so the expected `op` for every
#: document below that is not deliberately answering something else.
IDENTIFY = "runtime.identify"

#: An operation this build does not encode. Well-formed as a name -- the parser
#: keeps no registry -- and therefore never a schema fault, only a correlation
#: one.
OTHER_OP = "some.other.operation"


def envelope_document(
    *,
    operation_rid: str,
    op: str = IDENTIFY,
    status: str = "ok",
    session_id: str | None = "ses_abc",
    observed: dict | None = None,
    error: dict | None = None,
    version: object = 6,
    runtime_overrides: dict | None = None,
    extra: dict | None = None,
) -> str:
    """Build the raw JSON text a conforming responder would return."""
    runtime = {
        "session_id": session_id,
        "session_storage": "script_engine_global",
        "session_minted_by": "mcp_server",
        "extension_version": None,
        "protocol_version": 6,
    }
    runtime.update(runtime_overrides or {})
    document: dict = {
        "v": version,
        "operation_rid": operation_rid,
        "op": op,
        "status": status,
        "runtime": runtime,
        "observed": {"pt_file_version": "9.0.1", "device_count": 3}
        if observed is None
        else observed,
        "error": error,
    }
    document.update(extra or {})
    return json.dumps(document)


# --------------------------------------------------- 1. operation identity ---


def test_generated_operation_rids_are_unique_and_self_validating():
    rids = {new_operation_rid() for _ in range(64)}

    assert len(rids) == 64
    assert all(is_valid_operation_rid(rid) for rid in rids)


@pytest.mark.parametrize(
    "candidate",
    [
        "",
        "abc",
        "0" * 31,
        "0" * 33,
        "0" * 31 + "g",          # not hex
        "0" * 31 + "A",          # uppercase is not the accepted shape
        " " + "0" * 32,
        "0" * 32 + " ",
        None,
        6,
        b"0" * 32,
        ["0" * 32],
    ],
)
def test_malformed_operation_rids_are_rejected(candidate):
    assert is_valid_operation_rid(candidate) is False


@pytest.mark.parametrize("name", [IDENTIFY, OTHER_OP, "x", "runtime.identify.v2"])
def test_any_non_empty_string_is_a_well_formed_operation_name(name):
    """Shape only, by design.

    The parser holds no registry of known operations. A name this build has
    never encoded is still a name it can correlate *against*, which is what
    keeps the contract generic as typed operations are added: only the caller's
    expectation changes, never this layer's schema.
    """
    assert is_valid_operation_name(name) is True


@pytest.mark.parametrize(
    "name", ["", None, 6, True, b"runtime.identify", ["runtime.identify"], {}],
)
def test_a_malformed_operation_name_is_rejected(name):
    assert is_valid_operation_name(name) is False


def test_session_candidates_are_unique_and_distinguishable_from_rids():
    """A session id must never be mistakable for an operation_rid in a log."""
    candidates = {new_session_candidate() for _ in range(32)}

    assert len(candidates) == 32
    assert not any(is_valid_operation_rid(item) for item in candidates)


# ------------------------------------------------------- 2. VALID_V6 ------


def test_a_conforming_document_parses_as_valid_v6():
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.VALID_V6
    assert outcome.envelope is not None
    assert outcome.envelope.operation_rid == rid
    assert outcome.envelope.op == "runtime.identify"
    assert outcome.envelope.status is ResultStatus.OK
    assert outcome.envelope.observed == {"pt_file_version": "9.0.1", "device_count": 3}
    assert outcome.envelope.error is None
    assert outcome.envelope.runtime.session_id == "ses_abc"
    assert outcome.envelope.runtime.session_storage is SessionStorage.SCRIPT_ENGINE_GLOBAL
    assert outcome.envelope.runtime.session_minted_by is SessionMintedBy.MCP_SERVER
    assert outcome.envelope.runtime.extension_version is None
    assert outcome.envelope.runtime.protocol_version == PROTOCOL_VERSION


def test_a_structured_engine_error_is_a_valid_v6_document():
    """An engine failure is a *successful parse* of a failed operation."""
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(
            operation_rid=rid,
            status="error",
            observed={},
            error={"code": "ENGINE_EXCEPTION", "detail": "TypeError: x"},
        ),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.VALID_V6
    assert outcome.envelope.status is ResultStatus.ERROR
    assert outcome.envelope.error.code is RuntimeErrorCode.ENGINE_EXCEPTION
    assert outcome.envelope.error.detail == "TypeError: x"


# --------------------------------------------- 3. CORRELATION_MISMATCH ----
#
# Operation identity is the pair (operation_rid, op). Correlating on the rid
# alone left a hole exactly one document wide: schema-valid V6, our own rid,
# somebody else's operation. No other check in the parser compares `op` against
# what was asked for, so no other check could have caught it.


def test_a_schema_valid_document_answering_another_op_is_not_valid_v6():
    """The regression: everything conforms except the operation being answered.

    The rid is the one that was requested and the envelope is schema-valid down
    to the last field. Only `op` differs -- the responder answered some other
    operation under our rid.
    """
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid, op=OTHER_OP),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.CORRELATION_MISMATCH
    assert outcome.envelope is None
    assert outcome.legacy_text is None
    assert outcome.routes_to_legacy_v5 is False
    assert outcome.fails_closed is True


#: Every way to miss a correct operation identity, and which half is wrong.
NEAR_MISSES = [
    pytest.param(True, False, ["op"], id="right-rid-wrong-op"),
    pytest.param(False, True, ["operation_rid"], id="wrong-rid-right-op"),
    pytest.param(False, False, ["operation_rid", "op"], id="wrong-rid-wrong-op"),
]


def near_miss_document(rid_matches: bool, op_matches: bool, expected_rid: str) -> str:
    return envelope_document(
        operation_rid=expected_rid if rid_matches else new_operation_rid(),
        op=IDENTIFY if op_matches else OTHER_OP,
    )


@pytest.mark.parametrize(
    ("rid_matches", "op_matches", "mismatched"), NEAR_MISSES,
)
def test_every_mismatched_operation_identity_fails_closed(
    rid_matches, op_matches, mismatched,
):
    """One correct half is not a correlation. Both halves, or nothing."""
    expected_rid = new_operation_rid()

    outcome = parse_runtime_result(
        near_miss_document(rid_matches, op_matches, expected_rid),
        expected_operation_rid=expected_rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.CORRELATION_MISMATCH
    assert outcome.envelope is None
    # The decisive property: it must not be offered to the legacy path.
    assert outcome.legacy_text is None
    assert outcome.routes_to_legacy_v5 is False
    assert outcome.fails_closed is True


@pytest.mark.parametrize(
    ("rid_matches", "op_matches", "mismatched"), NEAR_MISSES,
)
def test_the_detail_names_which_half_of_the_identity_mismatched(
    rid_matches, op_matches, mismatched,
):
    """A stale answer and a wrong answer are different faults to chase."""
    expected_rid = new_operation_rid()

    outcome = parse_runtime_result(
        near_miss_document(rid_matches, op_matches, expected_rid),
        expected_operation_rid=expected_rid,
        expected_op=IDENTIFY,
    )

    # Read the names out of the trailing list rather than searching the whole
    # detail for them: "operation_rid" contains "op", so a substring test would
    # report an op mismatch on every rid mismatch.
    listed = outcome.detail.rsplit(": ", 1)[-1].rstrip(")")

    assert listed.split(", ") == mismatched


def test_the_correlation_detail_never_carries_the_document():
    """Fail closed means the document does not escape -- in prose either.

    `legacy_text` is the routing gate, but a detail string that quoted the
    responder's own `op` back would put responder-controlled text into a caller
    that has just been told this document answers nothing it asked for.
    """
    rid = new_operation_rid()
    document = envelope_document(operation_rid=rid, op=OTHER_OP)

    outcome = parse_runtime_result(
        document, expected_operation_rid=rid, expected_op=IDENTIFY,
    )

    assert OTHER_OP not in outcome.detail
    assert rid not in outcome.detail
    assert document not in outcome.detail


def test_a_malformed_op_is_a_schema_fault_not_a_correlation_result():
    """Order of validation, stated once: schema first, identity second.

    This document misses on *both* halves of the identity and breaks the schema
    as well. The schema fault is the one to report -- correlating against a
    document whose shape was never established is not a correlation at all.
    """
    document = json.loads(envelope_document(operation_rid=new_operation_rid()))
    document["op"] = ""

    outcome = parse_runtime_result(
        json.dumps(document),
        expected_operation_rid=new_operation_rid(),
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.INVALID_V6
    assert outcome.envelope is None
    assert outcome.legacy_text is None


# ------------------------------------------------- 6. PROTOCOL_MISMATCH ---


@pytest.mark.parametrize("version", [1, 5, 7, 60, "6", True, None, 6.0])
def test_a_foreign_protocol_version_fails_closed(version):
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid, version=version),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.PROTOCOL_MISMATCH
    assert outcome.envelope is None
    assert outcome.legacy_text is None
    assert outcome.fails_closed is True


# ------------------------------------------------------ 7. INVALID_V6 ----


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda d: d.pop("op"), "op missing"),
        (lambda d: d.update(op=""), "op empty"),
        (lambda d: d.update(op=6), "op not a string"),
        (lambda d: d.pop("status"), "status missing"),
        (lambda d: d.update(status="OK"), "status not in the finite set"),
        (lambda d: d.update(status="pending"), "status invented"),
        (lambda d: d.pop("runtime"), "runtime missing"),
        (lambda d: d.update(runtime=[]), "runtime not an object"),
        (lambda d: d.pop("observed"), "observed missing"),
        (lambda d: d.update(observed="none"), "observed not an object"),
        (lambda d: d.pop("operation_rid"), "operation_rid missing"),
        (lambda d: d.update(operation_rid="zz"), "operation_rid malformed"),
        (lambda d: d.pop("error"), "error key missing"),
        (lambda d: d.update(error={"detail": "x"}), "error without a code"),
        (lambda d: d.update(error={"code": "NOPE", "detail": "x"}), "unknown code"),
        (lambda d: d.update(error={"code": "ENGINE_EXCEPTION"}), "error without detail"),
    ],
)
def test_a_malformed_v6_envelope_fails_closed(mutate, why):
    rid = new_operation_rid()
    document = json.loads(envelope_document(operation_rid=rid))
    mutate(document)

    outcome = parse_runtime_result(
        json.dumps(document), expected_operation_rid=rid, expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.INVALID_V6, why
    assert outcome.envelope is None
    assert outcome.legacy_text is None, "a broken V6 responder is not a V5 responder"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("ok", {"code": "ENGINE_EXCEPTION", "detail": "boom"}),
        ("error", None),
    ],
)
def test_status_and_error_must_agree(status, error):
    """`ok` with an error, or `error` without one, is an incoherent envelope."""
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid, status=status, error=error),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.INVALID_V6


@pytest.mark.parametrize(
    "overrides",
    [
        {"session_storage": "webview"},
        {"session_storage": None},
        {"session_minted_by": "somewhere"},
        {"protocol_version": 5},
        {"session_id": 6},
        {"extension_version": 5},
    ],
)
def test_a_malformed_runtime_block_fails_closed(overrides):
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid, runtime_overrides=overrides),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.INVALID_V6


def test_a_read_only_operation_may_not_carry_mutation_evidence():
    """APPLIED stays distinct from VERIFIED, enforced at the protocol layer."""
    rid = new_operation_rid()
    assert "runtime.identify" in READ_ONLY_OPERATIONS

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid, extra={"mutated": {"devices": 1}}),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.INVALID_V6
    assert outcome.envelope is None


def test_a_read_only_operation_may_not_carry_a_null_mutated_key_either():
    """Absent, not null. A null default would still read as 'nothing mutated'."""
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid, extra={"mutated": None}),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.INVALID_V6


# ------------------------------------- 8. the parser never sees a failure --


def test_the_parser_accepts_only_a_string_by_annotation():
    """A transport non-response must be unable to reach the protocol layer."""
    hints = typing.get_type_hints(parse_runtime_result)

    assert hints["document"] is str


@pytest.mark.parametrize("document", [None, 6, b"{}", ["{}"], {"v": 6}])
def test_the_parser_refuses_a_non_string_document(document):
    rid = new_operation_rid()

    with pytest.raises(TypeError):
        parse_runtime_result(
            document, expected_operation_rid=rid, expected_op=IDENTIFY,
        )


def test_the_parser_refuses_an_invalid_expected_rid():
    """Asking the parser to correlate against nonsense is a caller bug."""
    with pytest.raises(ValueError):
        parse_runtime_result(
            "{}", expected_operation_rid="not-a-rid", expected_op=IDENTIFY,
        )


def test_the_parser_requires_an_expected_op():
    """Half an operation identity is not an operation identity.

    `expected_op` has no default, so no caller can quietly fall back to
    correlating on the rid alone -- and it is not inferrable either: the rid
    is opaque, and this layer keeps no registry of operations in flight to
    look one up in.
    """
    rid = new_operation_rid()

    with pytest.raises(TypeError):
        parse_runtime_result(
            envelope_document(operation_rid=rid), expected_operation_rid=rid,
        )


@pytest.mark.parametrize("expected_op", ["", None, 6, True, b"runtime.identify"])
def test_the_parser_refuses_an_invalid_expected_op(expected_op):
    """Correlating against a nonsense op is a caller bug, as a bad rid is."""
    rid = new_operation_rid()

    with pytest.raises(ValueError):
        parse_runtime_result(
            envelope_document(operation_rid=rid),
            expected_operation_rid=rid,
            expected_op=expected_op,
        )


# --------------------------------------------------- 9. session_id null ---


def test_a_null_session_id_is_valid_v6():
    """Degradation must stay expressible: null beats a fabricated identity."""
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid, session_id=None),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.state is ProtocolParseState.VALID_V6
    assert outcome.envelope.runtime.session_id is None


# ------------------------------------------- 10. extension_version null ---


def test_extension_version_is_null_on_the_phase_1a_wire():
    rid = new_operation_rid()

    outcome = parse_runtime_result(
        envelope_document(operation_rid=rid),
        expected_operation_rid=rid,
        expected_op=IDENTIFY,
    )

    assert outcome.envelope.runtime.extension_version is None


def test_the_schema_reserves_an_extension_minted_session_without_producing_it():
    """The later phase has a name; Phase 1A must not be able to emit it."""
    assert SessionMintedBy.EXTENSION.value == "extension"
    assert SessionMintedBy.MCP_SERVER.value == "mcp_server"


# --------------------------------- 14. reserved codes are not fabricated ---


def test_the_parser_never_invents_an_error_code():
    """Every code in an outcome came from the document, or there is no code."""
    rid = new_operation_rid()
    documents = [
        "PT_ERROR: boom",
        "ERROR:boom",
        "OK",
        "{}",
        json.dumps({"found": True}),
        envelope_document(operation_rid=rid),
        envelope_document(operation_rid=rid, version=7),
        json.dumps({"v": 6, "op": "runtime.identify"}),
        envelope_document(
            operation_rid=rid,
            status="error",
            observed={},
            error={"code": "TARGET_NOT_FOUND", "detail": "R1"},
        ),
    ]
    carried_a_code = False

    for document in documents:
        outcome = parse_runtime_result(
            document, expected_operation_rid=rid, expected_op=IDENTIFY,
        )
        if outcome.envelope is None or outcome.envelope.error is None:
            continue
        carried_a_code = True
        assert outcome.envelope.error.code.value in document

    assert carried_a_code, "the assertion above must actually fire"


def test_every_reserved_engine_code_is_declared_exactly_once():
    values = [item.value for item in RuntimeErrorCode]

    assert sorted(values) == sorted(set(values))
    assert set(values) == {
        "UNKNOWN_OPERATION",
        "INVALID_ARGUMENTS",
        "TARGET_NOT_FOUND",
        "ENGINE_EXCEPTION",
    }


def test_the_status_vocabulary_is_finite():
    """`status` is a closed set, not an arbitrary string."""
    assert {item.value for item in ResultStatus} == {"ok", "error"}


# ------------------------------------------------- parse-state totality ---


def test_every_parse_state_is_either_legacy_routing_or_fail_closed():
    """No state may be neither, and none may be both."""
    for state in ProtocolParseState:
        legacy = state is ProtocolParseState.NOT_V6
        valid = state is ProtocolParseState.VALID_V6
        closed = state in {
            ProtocolParseState.PROTOCOL_MISMATCH,
            ProtocolParseState.INVALID_V6,
            ProtocolParseState.CORRELATION_MISMATCH,
        }
        assert [legacy, valid, closed].count(True) == 1, state


def test_only_not_v6_carries_legacy_text():
    """Structural, not merely conventional: the field is the routing gate."""
    rid = new_operation_rid()
    cases = {
        "PT_ERROR: boom": ProtocolParseState.NOT_V6,
        envelope_document(operation_rid=rid): ProtocolParseState.VALID_V6,
        envelope_document(operation_rid=rid, version=7): (
            ProtocolParseState.PROTOCOL_MISMATCH
        ),
        json.dumps({"v": 6}): ProtocolParseState.INVALID_V6,
        envelope_document(operation_rid=new_operation_rid()): (
            ProtocolParseState.CORRELATION_MISMATCH
        ),
        envelope_document(operation_rid=rid, op=OTHER_OP): (
            ProtocolParseState.CORRELATION_MISMATCH
        ),
    }

    for document, expected_state in cases.items():
        outcome = parse_runtime_result(
            document, expected_operation_rid=rid, expected_op=IDENTIFY,
        )
        assert outcome.state is expected_state
        assert (outcome.legacy_text is not None) == (
            expected_state is ProtocolParseState.NOT_V6
        )
