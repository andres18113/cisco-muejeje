"""Phase 1A: V6 must be additive, and the encoder must stay read-only.

Two things are pinned here. First, that no existing V5 response can be dragged
into the V6 path or altered by it -- the repository already returns JSON from
118 call sites, so "it parses as JSON" is not evidence of V6. Second, that the
`runtime.identify` encoder is what it claims: a read-only operation encoder,
building JS through one escaping function, naming no mutating Packet Tracer API,
and carrying no mutation evidence.

Nothing here reaches Packet Tracer. The last group does execute the generated
text, in Node, under the same `new Function("reportResult", js)` shape the file
bridge uses -- which establishes that the JavaScript is valid and that each
branch builds a conforming envelope, and establishes nothing whatsoever about
Packet Tracer's Script Engine.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from src.packet_tracer_mcp.infrastructure.execution.runtime_operation_encoder import (
    RUNTIME_IDENTIFY,
    encode_runtime_identify,
    js_string_literal,
)
from src.packet_tracer_mcp.infrastructure.execution.runtime_protocol import (
    ProtocolParseState,
    RuntimeErrorCode,
    new_operation_rid,
    parse_runtime_result,
)

# The canonical list of mutating Packet Tracer APIs, imported from the sweep
# that owns it rather than copied. If that sweep learns a new name, this test
# starts enforcing it on the same commit.
from tests.test_transport_mutation_containment import _MUTATING_PT_APIS

REPO = pathlib.Path(__file__).resolve().parents[1]
EXECUTION = REPO / "src" / "packet_tracer_mcp" / "infrastructure" / "execution"
PROTOCOL_MODULE = EXECUTION / "runtime_protocol.py"
ENCODER_MODULE = EXECUTION / "runtime_operation_encoder.py"

LINE_SEPARATOR = " "
PARAGRAPH_SEPARATOR = " "

#: V5 responses in the shapes the deployed product actually produces.
LEGACY_V5_RESPONSES = [
    "PT_ERROR: TypeError: undefined is not a function",
    "ERROR:ReferenceError: ipc is not defined",
    "OK",
    "MISSING",
    "",
    "true",
    "9.0.1.0858",
    # tool_registry's project-metadata read, verbatim in shape.
    json.dumps(
        {
            "found": True,
            "saved_filename": "campus.pkt",
            "pt_version": "9.0.1",
            "description": "",
            "devices": 12,
            "links": 14,
        }
    ),
    # A payload runtime's structured read, which has no protocol version key.
    json.dumps({"started": True, "before": ""}),
    json.dumps({"found": False}),
    json.dumps([1, 2, 3]),
    json.dumps(None),
]


# ------------------------------------- 4/5. legacy responses stay legacy ---


@pytest.mark.parametrize("document", LEGACY_V5_RESPONSES)
def test_a_legacy_v5_response_is_not_v6_and_is_handed_back_untouched(document):
    rid = new_operation_rid()

    outcome = parse_runtime_result(document, expected_operation_rid=rid)

    assert outcome.state is ProtocolParseState.NOT_V6
    assert outcome.envelope is None
    assert outcome.routes_to_legacy_v5 is True
    # Byte-for-byte: the V5 path must receive exactly what arrived.
    assert outcome.legacy_text == document


def test_json_is_not_evidence_of_v6():
    """The existing JSON.stringify sites must not be misread in either direction."""
    rid = new_operation_rid()
    structured_but_legacy = json.dumps(
        {"devices": 3, "links": 2, "status": "ok", "error": None},
    )

    outcome = parse_runtime_result(
        structured_but_legacy, expected_operation_rid=rid,
    )

    assert outcome.state is ProtocolParseState.NOT_V6


def test_a_broken_v6_responder_never_degrades_into_a_v5_responder():
    rid = new_operation_rid()
    broken = json.dumps({"v": 6, "op": "runtime.identify"})

    outcome = parse_runtime_result(broken, expected_operation_rid=rid)

    assert outcome.state is ProtocolParseState.INVALID_V6
    assert outcome.routes_to_legacy_v5 is False
    assert outcome.legacy_text is None


# ------------------------------- 16. no existing V5 path is reached into ---


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(
                (node.module or "") + "." + alias.name for alias in node.names
            )
    return names


@pytest.mark.parametrize("module", [PROTOCOL_MODULE, ENCODER_MODULE])
def test_phase_1a_imports_no_transport_and_no_adapter(module):
    """Phase 1A is pure. It cannot dispatch, because it cannot reach a transport."""
    forbidden = (
        "live_bridge",
        "file_bridge",
        "tool_registry",
        "adapters",
        "bridge_token",
        "transport_health",
        "urllib",
        "http",
        "socket",
        "subprocess",
    )
    imported = _imported_modules(module)

    offenders = sorted(
        name for name in imported if any(bad in name for bad in forbidden)
    )
    assert offenders == [], f"{module.name} reaches outside Phase 1A: {offenders}"


@pytest.mark.parametrize("module", [PROTOCOL_MODULE, ENCODER_MODULE])
def test_phase_1a_never_reads_the_caller_supplied_extension_version(module):
    """`extension_version` must not be back-filled from the MCP tool parameter."""
    tree = ast.parse(module.read_text(encoding="utf-8"))

    accepted = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.arg) and node.arg == "extension_version"
    ]

    assert accepted == [], "Phase 1A accepts no extension_version input"


# --------------------------------------- 11/12/13/15. the encoder itself ---


def test_the_encoder_reports_the_identity_it_embedded():
    encoded = encode_runtime_identify()

    assert encoded.op == RUNTIME_IDENTIFY == "runtime.identify"
    assert js_string_literal(encoded.operation_rid) in encoded.payload
    assert js_string_literal(encoded.session_candidate) in encoded.payload


def test_the_encoded_rid_round_trips_through_the_parser():
    """Encoder and parser agree on the wire, not merely on a shared constant."""
    encoded = encode_runtime_identify()

    # Recover the rid from the generated text, then answer as the engine would.
    embedded = re.search(r'operation_rid:"([0-9a-f]{32})"', encoded.payload)
    assert embedded is not None
    document = json.dumps(
        {
            "v": 6,
            "operation_rid": embedded.group(1),
            "op": "runtime.identify",
            "status": "ok",
            "runtime": {
                "session_id": encoded.session_candidate,
                "session_storage": "script_engine_global",
                "session_minted_by": "mcp_server",
                "extension_version": None,
                "protocol_version": 6,
            },
            "observed": {"pt_file_version": "9.0.1", "device_count": 0},
            "error": None,
        }
    )

    outcome = parse_runtime_result(
        document, expected_operation_rid=encoded.operation_rid,
    )

    assert outcome.state is ProtocolParseState.VALID_V6
    assert outcome.envelope.runtime.session_id == encoded.session_candidate


def test_the_encoder_rejects_an_operation_rid_it_did_not_validate():
    with pytest.raises(ValueError):
        encode_runtime_identify(operation_rid="'; dropTable(); //")


@pytest.mark.parametrize(
    "hostile",
    [
        '"; reportResult("owned"); var x="',
        "</script><script>alert(1)</script>",
        "back\\slash",
        'quote"inside',
        "new\nline",
        "carriage\rreturn",
        "tab\there",
        "line" + LINE_SEPARATOR + "separator",
        "paragraph" + PARAGRAPH_SEPARATOR + "separator",
        "null\x00byte",
    ],
)
def test_dynamic_values_reach_the_payload_only_through_json_encoding(hostile):
    """A hostile session candidate must survive as data, never become code."""
    encoded = encode_runtime_identify(session_candidate=hostile)

    literal = js_string_literal(hostile)
    # The literal is what the payload carries...
    assert literal in encoded.payload
    # ...it decodes back to exactly what went in...
    assert json.loads(literal) == hostile
    # ...and the raw text appears nowhere outside that encoded form.
    assert hostile not in encoded.payload.replace(literal, "")


@pytest.mark.parametrize("terminator", [LINE_SEPARATOR, PARAGRAPH_SEPARATOR])
def test_javascript_line_terminators_never_reach_the_payload_raw(terminator):
    """Legal raw inside JSON, but they end a JavaScript string literal.

    Nothing in the encoder escapes them explicitly: `json.dumps` defaults to
    `ensure_ascii=True`, which already does. That default is the mechanism, so
    it is pinned here -- switching it off would reopen the hole silently.
    """
    hostile = "a" + terminator + "b"
    encoded = encode_runtime_identify(session_candidate=hostile)

    assert terminator not in encoded.payload
    assert terminator not in js_string_literal(hostile)


def test_every_encoded_literal_is_pure_ascii():
    """The mechanism above, stated once as a property of the escaping function."""
    for value in ["a" + LINE_SEPARATOR, "é", "你好", "emoji \U0001f600"]:
        literal = js_string_literal(value)

        assert literal.isascii(), f"non-ASCII survived encoding: {value!r}"
        assert json.loads(literal) == value


def test_the_encoder_builds_javascript_without_f_string_interpolation():
    """AGENTS.md rule 1, asserted on source rather than trusted."""
    tree = ast.parse(ENCODER_MODULE.read_text(encoding="utf-8"))

    joined = [node for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)]

    assert joined == [], "JS is built through js_string_literal, never an f-string"


def test_runtime_identify_names_no_mutating_packet_tracer_api():
    encoded = encode_runtime_identify()

    named = sorted(name for name in _MUTATING_PT_APIS if name in encoded.payload)

    assert named == [], f"a read-only operation names mutating APIs: {named}"


def test_runtime_identify_carries_no_mutation_evidence():
    """Structurally absent, so no read-only result can imply a mutation."""
    encoded = encode_runtime_identify()

    assert "mutated" not in encoded.payload


def test_the_payload_is_a_single_self_contained_statement():
    """HTTP joins up to two hundred commands with newlines into one runCode body."""
    encoded = encode_runtime_identify()

    assert "\n" not in encoded.payload
    assert "\r" not in encoded.payload
    assert "//" not in encoded.payload
    assert encoded.payload.endswith(";")


def test_batching_two_operations_preserves_both_payloads():
    first = encode_runtime_identify()
    second = encode_runtime_identify()

    batch = "\n".join([first.payload, second.payload])

    assert batch.split("\n") == [first.payload, second.payload]
    assert first.operation_rid != second.operation_rid
    assert first.session_candidate != second.session_candidate


def test_the_payload_declares_the_protocol_version_on_the_wire():
    encoded = encode_runtime_identify()

    assert "v:6" in encoded.payload
    assert "protocol_version:6" in encoded.payload


def test_the_payload_observes_only_already_proven_reads():
    """No speculative Packet Tracer API may appear in a Phase 1A operation."""
    encoded = encode_runtime_identify()

    calls = set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)\(", encoded.payload))
    permitted = {
        "appWindow",
        "getActiveFile",
        "getVersion",
        "network",
        "getDeviceCount",
        "stringify",
    }

    assert calls <= permitted, f"unproven API surface: {sorted(calls - permitted)}"


def test_the_payload_degrades_to_a_null_session_rather_than_fabricating_one():
    """An unreachable global must not echo the candidate back as if it were read."""
    encoded = encode_runtime_identify()

    assert "catch(__e0){__sid=null;}" in encoded.payload


# ------------------------------ 14. reserved codes are declared, not used --


def test_the_encoder_emits_only_the_engine_exception_code():
    """The chosen contract: engine faults become V6 envelopes, not PT_ERROR."""
    encoded = encode_runtime_identify()

    present = sorted(
        code.value for code in RuntimeErrorCode if code.value in encoded.payload
    )

    assert present == ["ENGINE_EXCEPTION"]


def test_the_encoder_does_not_fall_back_to_legacy_error_prefixes():
    """A complete V6 error contract cannot lean on V5 semantics underneath."""
    encoded = encode_runtime_identify()

    assert "PT_ERROR" not in encoded.payload
    assert "ERROR:" not in encoded.payload


# ------------------- the generated text is valid, executable JavaScript ----
#
# What follows runs the payload in Node, under the *same* invocation shape the
# file bridge uses -- `(new Function("reportResult", js))(report)` -- with `ipc`
# stubbed.
#
# This is a JavaScript engine. It is NOT Packet Tracer. It establishes that the
# generated text parses, that its branches build a conforming envelope, and that
# its seed is first-writer-wins in a conforming engine. It establishes nothing
# about Packet Tracer's Script Engine: whether `this` is the global there, and
# whether the seed survives real dispatches, stay UNVERIFIED_UNTIL_PHASE_1B.

NODE = shutil.which("node")

_HARNESS = """
const fs = require('fs');
const payload = fs.readFileSync(process.argv[2], 'utf8');
const mode = process.argv[3];
const out = [];
const report = (d) => out.push(String(d));
if (mode === 'ok') {
  globalThis.ipc = {
    appWindow: () => ({ getActiveFile: () => ({ getVersion: () => '9.0.1.0858' }) }),
    network: () => ({ getDeviceCount: () => 12 }),
  };
} else if (mode === 'nofile') {
  globalThis.ipc = {
    appWindow: () => ({ getActiveFile: () => null }),
    network: () => ({ getDeviceCount: () => 0 }),
  };
} else {
  globalThis.ipc = { appWindow: () => { throw new TypeError('ipc unavailable'); } };
}
const fn = new Function('reportResult', payload);
fn(report);
fn(report);
console.log(JSON.stringify(out));
"""


def _run_in_node(tmp_path: pathlib.Path, payload: str, mode: str) -> list[str]:
    harness = tmp_path / "harness.js"
    script = tmp_path / "payload.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    script.write_text(payload, encoding="utf-8")

    completed = subprocess.run(
        [NODE, str(harness), str(script), mode],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(completed.stdout)


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_generated_payload_is_syntactically_valid_javascript(tmp_path):
    script = tmp_path / "payload.js"
    script.write_text(encode_runtime_identify().payload, encoding="utf-8")

    completed = subprocess.run(
        [NODE, "--check", str(script)], capture_output=True, text=True, timeout=30,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize(
    ("mode", "status", "observed"),
    [
        ("ok", "ok", {"pt_file_version": "9.0.1.0858", "device_count": 12}),
        # getActiveFile() returning null is a real state the read must survive.
        ("nofile", "ok", {"pt_file_version": "", "device_count": 0}),
        ("throw", "error", {}),
    ],
)
def test_each_branch_builds_an_envelope_this_parser_accepts(
    tmp_path, mode, status, observed,
):
    encoded = encode_runtime_identify()

    reported = _run_in_node(tmp_path, encoded.payload, mode)

    assert len(reported) == 2
    outcome = parse_runtime_result(
        reported[0], expected_operation_rid=encoded.operation_rid,
    )
    assert outcome.state is ProtocolParseState.VALID_V6
    assert outcome.envelope.status.value == status
    assert outcome.envelope.observed == observed
    assert outcome.envelope.op == RUNTIME_IDENTIFY


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_an_engine_fault_becomes_a_structured_envelope_not_a_thrown_error(tmp_path):
    encoded = encode_runtime_identify()

    reported = _run_in_node(tmp_path, encoded.payload, "throw")

    outcome = parse_runtime_result(
        reported[0], expected_operation_rid=encoded.operation_rid,
    )
    assert outcome.envelope.error.code is RuntimeErrorCode.ENGINE_EXCEPTION
    assert "ipc unavailable" in outcome.envelope.error.detail


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_seed_is_first_writer_wins_within_one_engine(tmp_path):
    """Two dispatches, one global: the second must not re-seed the session."""
    encoded = encode_runtime_identify()

    reported = _run_in_node(tmp_path, encoded.payload, "ok")

    first = json.loads(reported[0])["runtime"]["session_id"]
    second = json.loads(reported[1])["runtime"]["session_id"]
    assert first == second == encoded.session_candidate


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_a_later_operation_does_not_displace_an_established_session(tmp_path):
    """The engine keeps the value it already holds, whoever dispatches next."""
    first_op = encode_runtime_identify()
    second_op = encode_runtime_identify()

    reported = _run_in_node(
        tmp_path, first_op.payload + second_op.payload, "ok",
    )

    # Four envelopes: the harness dispatches the combined batch twice.
    sessions = {json.loads(item)["runtime"]["session_id"] for item in reported}
    assert sessions == {first_op.session_candidate}
    assert second_op.session_candidate not in sessions
