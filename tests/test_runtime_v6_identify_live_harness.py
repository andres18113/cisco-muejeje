"""Phase 1B-LIVE-A prep: the operator harness, exercised entirely offline.

No Packet Tracer is opened, no HTTP server is started, and no file mailbox is
touched. Every transport below is a fake written in this file. What is being
validated is the harness's *orchestration*: which transport it builds for a
declared channel, that it starts and always stops the one it owns, that it
refuses to dispatch without preflight evidence, that it runs the accepted
`RuntimeProtocolClient` rather than reimplementing it, and that its JSON and
exit code say only what the run actually established.

Why child processes
-------------------
`tools/runtime_v6_identify_live.py` imports the PRODUCTION `packet_tracer_mcp`
namespace, as every operator LIVE runner in `tools/` does. Importing it here
would load that namespace into the pytest process, which three existing tests
assert must not happen (`test_cp_scale_live_failure_evidence.py:187`,
`test_cp_scale_voice_staging.py:321`, `test_import_isolation_preflight.py:148`)
-- and it would create the second module identity that
`ImportIsolationPreflight` exists to prevent. So the harness is driven in a
child process and only its observations cross back, the same shape
`test_cp_scale_live_failure_evidence.py` already uses.

The structural checks read the source instead, which needs no import at all.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Imported from the sweep that owns it, so a new mutating API starts being
# enforced here on the same commit.
from tests.test_transport_mutation_containment import _MUTATING_PT_APIS

REPO = Path(__file__).resolve().parents[1]
HARNESS = REPO / "tools" / "runtime_v6_identify_live.py"

RAW_TOKEN = "RAWTOKENd41d8cd98f00b204e9800998ecf8427e"
TOKEN_ID = "fingerprint01234"


# ------------------------------------------------------------- the probe ---
#
# Runs in a child process. Reads (repo_root, scenario, timeout) from argv so
# nothing has to be interpolated into this source, and prints one JSON
# observation to stdout.

_PROBE = r'''
import json, re, sys

root, scenario, timeout_text = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)

import tools.runtime_v6_identify_live as harness

RAW_TOKEN = "RAWTOKENd41d8cd98f00b204e9800998ecf8427e"
TOKEN_ID = "fingerprint01234"
OTHER_RID = "0123456789abcdef0123456789abcdef"
OTHER_OP = "some.other.operation"

events = []


class SeamFailure(RuntimeError):
    pass


def embedded(payload, pattern):
    found = re.search(pattern, payload)
    assert found is not None, payload[:80]
    return found.group(1)


def conforming(payload, rid=None, op=None, status="ok", version=6):
    document = {
        "v": version,
        "operation_rid": rid or embedded(payload, r'operation_rid:"([0-9a-f]{32})"'),
        "op": op or embedded(payload, r'op:"([a-z.]+)"'),
        "status": status,
        "runtime": {
            "session_id": "ses_live_fake",
            "session_storage": "script_engine_global",
            "session_minted_by": "mcp_server",
            "extension_version": None,
            "protocol_version": 6,
        },
        "observed": {} if status == "error" else {
            "pt_file_version": "9.0.1.0858", "device_count": 0,
        },
        "error": None if status == "ok" else {
            "code": "ENGINE_EXCEPTION", "detail": "TypeError: x",
        },
    }
    return json.dumps(document)


def respond(payload):
    if scenario.endswith("_no_response"):
        return None
    if scenario.endswith("_raises"):
        raise SeamFailure("the channel dropped mid-operation " + RAW_TOKEN)
    if scenario.endswith("_not_v6"):
        return "PT_ERROR: TypeError: undefined is not a function"
    if scenario.endswith("_protocol_mismatch"):
        return conforming(payload, version=7)
    if scenario.endswith("_invalid_v6"):
        return json.dumps({"v": 6})
    if scenario.endswith("_correlation_rid"):
        return conforming(payload, rid=OTHER_RID)
    if scenario.endswith("_correlation_op"):
        return conforming(payload, op=OTHER_OP)
    if scenario.endswith("_engine_error"):
        return conforming(payload, status="error")
    return conforming(payload)
'''

_PROBE += r'''

class FakeHttpTransport:
    bridge_transport = "http"

    def __init__(self, *args, **kwargs):
        events.append("http.construct")
        self.token = RAW_TOKEN
        self.port = 65123
        self.base_url = ""
        self.sends = []
        harness_probe["http"] = self

    def start(self, **kwargs):
        events.append("http.start")
        return not scenario.endswith("_not_connected")

    def stop(self):
        events.append("http.stop")

    def status_dict(self):
        return {
            "connected": not scenario.endswith("_not_connected"),
            "last_poll_ago": 0.4,
            "unauth_recent": False,
            "unauth_count": 0,
            "unauth_paths": [],
            "client_headers": {"User-Agent": "PacketTracer/9.0.1"},
            "token_id": TOKEN_ID,
            "token": RAW_TOKEN,
        }

    def send_and_wait(self, js_code, timeout=12.0):
        events.append("http.send")
        self.sends.append([js_code, timeout])
        return respond(js_code)


class FakeFileBridge:
    def __init__(self, *args, **kwargs):
        events.append("file.construct")
        self.dir = "/fake/mailbox"
        self.sends = []
        harness_probe["file"] = self

    def pt_alive(self):
        events.append("file.pt_alive")
        return not scenario.endswith("_not_alive")

    def send_and_wait(self, js_code, timeout=12.0):
        events.append("file.send")
        self.sends.append([js_code, timeout])
        return respond(js_code)


class RefusedIsolation:
    def __init__(self, *args, **kwargs):
        pass

    def ensure_isolated(self):
        class Result:
            isolated = False
            detail = "two namespaces loaded"

            class state:
                value = "DUAL_IDENTITY"

            def render(self):
                return "import isolation refused"

        return Result()


harness_probe = {}
real_client = harness.RuntimeProtocolClient
client_seen = {}


class SpyClient(real_client):
    def __init__(self, send_and_wait, **kwargs):
        events.append("client.construct")
        client_seen["seam_owner"] = getattr(
            getattr(send_and_wait, "__self__", None), "__class__", type(None),
        ).__name__
        client_seen["timeout"] = kwargs.get("timeout_seconds")
        super().__init__(send_and_wait, **kwargs)

    def identify(self):
        events.append("client.identify")
        return super().identify()


harness.PacketTracerHttpTransport = FakeHttpTransport
harness.FileBridge = FakeFileBridge
harness.RuntimeProtocolClient = SpyClient
if scenario.endswith("_isolation_refused"):
    harness.ImportIsolationPreflight = RefusedIsolation

channel = "file" if scenario.startswith("file") else "http"
result, code, raised = None, None, None
try:
    result, code = harness.run(
        channel=channel, timeout_seconds=float(timeout_text),
    )
except Exception as exc:
    raised = type(exc).__name__

owner = harness_probe.get(channel)
print(json.dumps({
    "events": events,
    "exit_code": code,
    "result": result,
    "raised": raised,
    "sends": getattr(owner, "sends", None),
    "client_seen": client_seen,
}))
'''


_OBSERVED: dict = {}


def probe(scenario: str, *, timeout: str = "7.5") -> dict:
    """Drive the harness once in a child process and cache what it did."""
    key = (scenario, timeout)
    if key not in _OBSERVED:
        completed = subprocess.run(
            [sys.executable, "-c", _PROBE, str(REPO), scenario, timeout],
            capture_output=True, text=True, timeout=180, cwd=str(REPO),
        )
        assert completed.returncode == 0, completed.stderr
        _OBSERVED[key] = json.loads(completed.stdout)
    return _OBSERVED[key]


def cli(*argv: str) -> subprocess.CompletedProcess:
    """Invoke the harness's own CLI. Argument parsing only -- these calls must
    fail before anything constructs a transport."""
    return subprocess.run(
        [sys.executable, str(HARNESS), *argv],
        capture_output=True, text=True, timeout=180, cwd=str(REPO),
    )


def harness_tree() -> ast.AST:
    return ast.parse(HARNESS.read_text(encoding="utf-8"))


# ------------------------------------------------- 1/2/3. the CLI contract ---


def test_the_channel_is_required():
    """No default channel: evidence has to stay attributable to one transport."""
    completed = cli("--timeout-seconds", "7.5")

    assert completed.returncode != 0
    assert "--channel" in completed.stderr
    assert completed.stdout.strip() == ""


@pytest.mark.parametrize("channel", ["auto", "https", "filebridge", ""])
def test_only_http_and_file_are_accepted_channels(channel):
    completed = cli("--channel", channel, "--timeout-seconds", "7.5")

    assert completed.returncode != 0
    assert completed.stdout.strip() == ""


def test_the_timeout_is_required():
    """No default: no measurement backs a number for this operation yet."""
    completed = cli("--channel", "http")

    assert completed.returncode != 0
    assert "--timeout-seconds" in completed.stderr
    assert completed.stdout.strip() == ""


def test_the_cli_declares_both_channels_and_nothing_else():
    completed = cli("--help")

    assert completed.returncode == 0
    assert "http" in completed.stdout and "file" in completed.stdout
    assert "runtime.identify" in completed.stdout


# ------------------------------------ 4/5/6/7/8/9/10. transport ownership ---


def test_the_http_channel_builds_the_http_transport_and_nothing_else():
    events = probe("http_ok")["events"]

    assert "http.construct" in events
    assert "file.construct" not in events


def test_the_file_channel_builds_the_file_bridge_and_nothing_else():
    events = probe("file_ok")["events"]

    assert "file.construct" in events
    assert "http.construct" not in events


def test_http_starts_before_it_identifies():
    events = probe("http_ok")["events"]

    assert events.index("http.start") < events.index("client.identify")


@pytest.mark.parametrize(
    "scenario",
    [
        "http_ok",
        "http_engine_error",
        "http_not_v6",
        "http_protocol_mismatch",
        "http_invalid_v6",
        "http_correlation_rid",
        "http_correlation_op",
        "http_no_response",
        "http_raises",
        "http_not_connected",
    ],
)
def test_http_always_stops_the_transport_it_started(scenario):
    """Success, protocol failure, integration exception, refused preflight --
    the harness owns the server it starts and never leaves one running."""
    events = probe(scenario)["events"]

    assert events.count("http.start") == 1
    assert events.count("http.stop") == 1
    assert events.index("http.stop") == len(events) - 1


def test_http_stops_even_when_the_budget_is_refused_after_start():
    """A non-finite budget is refused by the client, after the server is up.

    The `finally` is what makes that safe, so it is asserted rather than
    assumed -- and the seam is never reached.
    """
    observed = probe("http_ok", timeout="nan")

    assert observed["raised"] == "ValueError"
    assert observed["events"].count("http.stop") == 1
    assert "http.send" not in observed["events"]


def test_a_refused_import_isolation_builds_no_transport_at_all():
    """The gate every sibling operator runner passes through, before anything."""
    observed = probe("http_isolation_refused")

    assert observed["events"] == []
    assert observed["result"]["transport"]["preflight_ok"] is False
    assert observed["exit_code"] != 0


# --------------------------------------------- 11/12. the file preflight ---


def test_file_checks_the_heartbeat_before_it_identifies():
    events = probe("file_ok")["events"]

    assert events.index("file.pt_alive") < events.index("client.identify")


def test_a_stale_heartbeat_costs_zero_sends():
    observed = probe("file_not_alive")

    assert observed["events"] == ["file.construct", "file.pt_alive"]
    assert observed["result"]["transport"]["pt_alive"] is False
    assert observed["result"]["transport"]["preflight_ok"] is False
    assert observed["exit_code"] != 0


def test_a_stale_heartbeat_is_not_reported_as_a_protocol_fact():
    """It proves the Script Engine did not touch its heartbeat recently. It does
    not prove a timeout, an unsupported protocol, or a Packet Tracer failure."""
    result = probe("file_not_alive")["result"]

    assert result["response"]["document_received"] is False
    assert result["response"]["parse_state"] is None
    assert result["runtime"]["protocol_version"] is None
    # Scoped to the blocks that make the claim. The document echoes the
    # declared `timeout_seconds` for the record, which is the budget the
    # operator chose and not a diagnosis of anything.
    claimed = json.dumps({
        "response": result["response"],
        "preflight": result["transport"]["preflight_detail"],
        "pt_alive": result["transport"]["pt_alive"],
    }).lower()
    assert "timeout" not in claimed
    assert "unsupported" not in claimed
    assert "heartbeat" in claimed


# ------------------------------------- 13/14/30/31/32. one channel, one send ---


@pytest.mark.parametrize(
    "scenario",
    ["http_no_response", "http_not_v6", "http_invalid_v6", "http_correlation_rid"],
)
def test_a_failed_http_attempt_never_falls_back_to_the_file_bridge(scenario):
    events = probe(scenario)["events"]

    assert "file.construct" not in events
    assert "file.send" not in events


@pytest.mark.parametrize("scenario", ["file_not_alive", "file_no_response"])
def test_a_failed_file_attempt_never_falls_back_to_http(scenario):
    events = probe(scenario)["events"]

    assert "http.construct" not in events
    assert "http.start" not in events


@pytest.mark.parametrize(
    "scenario",
    [
        "http_ok",
        "http_engine_error",
        "http_not_v6",
        "http_protocol_mismatch",
        "http_invalid_v6",
        "http_correlation_rid",
        "http_correlation_op",
        "http_no_response",
    ],
)
def test_every_outcome_costs_exactly_one_send(scenario):
    """Whatever the responder said, the harness asks once and stops."""
    observed = probe(scenario)

    assert observed["events"].count("client.identify") == 1
    assert observed["events"].count("http.send") == 1
    assert len(observed["sends"]) == 1


def test_the_harness_identifies_from_exactly_one_place_in_its_source():
    """A second call site is a retry or a fallback, whatever it is named."""
    call_sites = [
        node for node in ast.walk(harness_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "identify"
    ]

    assert len(call_sites) == 1


def test_the_harness_has_no_loop_to_retry_or_fall_back_from():
    loops = [
        node for node in ast.walk(harness_tree())
        if isinstance(node, (ast.For, ast.While, ast.AsyncFor))
    ]

    assert loops == []


# ------------------------------------ 15/16/27. the client is the authority ---


def test_the_accepted_runtime_protocol_client_is_the_thing_that_runs():
    observed = probe("http_ok")

    assert "client.construct" in observed["events"]
    assert "client.identify" in observed["events"]


@pytest.mark.parametrize(
    ("scenario", "owner"),
    [("http_ok", "FakeHttpTransport"), ("file_ok", "FakeFileBridge")],
)
def test_the_seam_is_the_bound_method_of_the_selected_transport(scenario, owner):
    """Not a wrapper the harness wrote: the client gets the real object's own
    `send_and_wait`, so the channel that answered is the channel that was
    declared."""
    seen = probe(scenario)["client_seen"]

    assert seen["seam_owner"] == owner


def test_the_declared_budget_reaches_the_client_unaltered():
    seen = probe("http_ok", timeout="3.25")["client_seen"]

    assert seen["timeout"] == 3.25


def test_the_harness_never_encodes_or_parses_behind_the_client():
    """The harness exists to validate the 1B-OFFLINE orchestration, so it must
    not reimplement it. Calling the encoder or the parser directly would mean
    the LIVE run proved something other than what ships."""
    called = {
        node.func.id
        for node in ast.walk(harness_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "encode_runtime_identify" not in called
    assert "parse_runtime_result" not in called


def test_the_reported_identity_comes_from_the_attempt_not_from_the_document():
    """The rid the harness reports is the one it sent, recovered from the
    payload that actually went out -- not a value read back out of the reply."""
    observed = probe("http_ok")

    sent_payload = observed["sends"][0][0]
    reported = observed["result"]["operation"]
    assert reported["op"] == "runtime.identify"
    assert reported["operation_rid"] in sent_payload
    assert len(reported["operation_rid"]) == 32


# ----------------------------------------- 17-24. the exit-code contract ---
#
# Three codes, and the partition is structural rather than a taste:
#   0  the operation succeeded            (VALID_V6 and status ok)
#   1  a document was classified, but it was not that
#   2  no classified document exists at all

EXIT_CASES = [
    ("http_ok", "VALID_V6", 0),
    ("http_engine_error", "VALID_V6", 1),
    ("http_not_v6", "NOT_V6", 1),
    ("http_protocol_mismatch", "PROTOCOL_MISMATCH", 1),
    ("http_invalid_v6", "INVALID_V6", 1),
    ("http_correlation_rid", "CORRELATION_MISMATCH", 1),
    ("http_correlation_op", "CORRELATION_MISMATCH", 1),
    ("http_no_response", None, 2),
    ("http_raises", None, 2),
    ("http_not_connected", None, 2),
    ("http_isolation_refused", None, 2),
    ("file_ok", "VALID_V6", 0),
    ("file_not_alive", None, 2),
]


@pytest.mark.parametrize(("scenario", "parse_state", "code"), EXIT_CASES)
def test_the_exit_code_follows_the_classified_outcome(scenario, parse_state, code):
    observed = probe(scenario)

    assert observed["result"]["response"]["parse_state"] == parse_state
    assert observed["exit_code"] == code


def test_a_protocol_valid_engine_failure_is_still_a_failed_validation():
    """This is a validation harness, not a generic protocol decoder. The
    envelope parsed perfectly and the operation did not succeed, so the process
    must not report success -- while the JSON keeps both facts separately."""
    result = probe("http_engine_error")["result"]

    assert result["response"]["parse_state"] == "VALID_V6"
    assert result["response"]["status"] == "error"
    assert result["error"] == {"code": "ENGINE_EXCEPTION", "detail": "TypeError: x"}
    assert probe("http_engine_error")["exit_code"] == 1


def test_no_response_is_never_called_a_timeout():
    """`RuntimeProtocolAttempt.no_response_document` carries no provenance, and
    neither transport hands one over separately."""
    result = probe("http_no_response")["result"]

    assert result["response"]["document_received"] is False
    assert result["response"]["parse_state"] is None
    assert result["response"]["detail"] == "NO_RESPONSE_DOCUMENT"
    assert "timeout" not in json.dumps(result["response"]).lower()


# ------------------------------------ 24. an integration exception -----------


def test_an_integration_exception_is_structured_and_not_an_engine_error():
    """ENGINE_EXCEPTION means the Script Engine ran the operation and reported a
    failure envelope. A Python callable that raised did no such thing."""
    result = probe("http_raises")["result"]

    assert result["integration_error"]["type"] == "SeamFailure"
    assert "the channel dropped mid-operation" in result["integration_error"]["message"]
    assert result["error"] is None
    assert result["response"]["parse_state"] is None
    assert "ENGINE_EXCEPTION" not in json.dumps(result)


def test_an_integration_exception_is_not_swallowed():
    observed = probe("http_raises")

    assert observed["exit_code"] == 2
    assert observed["result"]["integration_error"] is not None


# ------------------------------------------------- 25. the bridge token -----


@pytest.mark.parametrize("scenario", [s for s, _, _ in EXIT_CASES])
def test_the_raw_bridge_token_never_reaches_the_output(scenario):
    """The token rides in the query string of every signed request, so a urllib
    exception can carry it verbatim -- which is why the fake puts it inside the
    exception message and inside `status_dict()`."""
    rendered = json.dumps(probe(scenario)["result"])

    assert RAW_TOKEN not in rendered


def test_the_token_fingerprint_is_reported_where_it_exists():
    """Identifying the bridge is useful; leaking it is not. The fingerprint is
    already the transport's own non-invertible id."""
    bridge = probe("http_ok")["result"]["transport"]["bridge"]

    assert bridge["token_id"] == TOKEN_ID
    assert "token" not in bridge


# --------------------------- 26. the runtime block is envelope-only ---------


def test_a_valid_envelope_is_the_only_source_of_the_runtime_block():
    runtime = probe("http_ok")["result"]["runtime"]

    assert runtime == {
        "session_id": "ses_live_fake",
        "session_storage": "script_engine_global",
        "session_minted_by": "mcp_server",
        "extension_version": None,
        "protocol_version": 6,
    }


@pytest.mark.parametrize(
    "scenario",
    [
        "http_not_v6",
        "http_protocol_mismatch",
        "http_invalid_v6",
        "http_correlation_rid",
        "http_no_response",
        "http_raises",
        "http_not_connected",
        "file_not_alive",
    ],
)
def test_no_envelope_means_no_runtime_fields_are_invented(scenario):
    result = probe(scenario)["result"]

    assert result["runtime"] == {
        "session_id": None,
        "session_storage": None,
        "session_minted_by": None,
        "extension_version": None,
        "protocol_version": None,
    }
    assert result["observed"] == {}


def test_a_correlation_mismatch_still_reports_the_identity_that_was_sent():
    """The reply belonged to another operation, so nothing of it is adopted --
    but what we asked for is still on the record."""
    observed = probe("http_correlation_rid")

    reported = observed["result"]["operation"]["operation_rid"]
    assert reported in observed["sends"][0][0]
    assert observed["result"]["runtime"]["session_id"] is None


# ----------------------------- 28/29. no mutation surface whatsoever --------


def test_the_harness_names_no_mutating_packet_tracer_api():
    source = HARNESS.read_text(encoding="utf-8")

    named = sorted(name for name in _MUTATING_PT_APIS if name in source)

    assert named == [], f"a read-only harness names mutating APIs: {named}"


def test_the_harness_cannot_save_or_create_a_packet_tracer_file():
    source = HARNESS.read_text(encoding="utf-8")

    for forbidden in ("saveFile", "saveAs", ".pkt", "newFile", "setPageContents"):
        assert forbidden not in source, forbidden


def test_the_harness_builds_no_javascript_and_sends_no_raw_command():
    """Every byte on the wire comes from the accepted encoder, through the
    client. A payload assembled here would be one nobody escaped."""
    source = HARNESS.read_text(encoding="utf-8")

    for forbidden in ("reportResult", "JSON.stringify", "ipc.", "runCode"):
        assert forbidden not in source, forbidden


def test_the_harness_uses_only_the_send_and_wait_seam():
    """`send` is the fire-and-forget mutation path on both transports. A
    read-only harness has no business calling it."""
    called = {
        node.func.attr
        for node in ast.walk(harness_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "send" not in called
    assert "configure_ios" not in called
    assert "collect_completed" not in called


def test_the_harness_declares_only_runtime_identify():
    """One operation. Adding a second here would put an unreviewed payload in
    front of a real Packet Tracer."""
    source = HARNESS.read_text(encoding="utf-8")
    calls = {
        node.func.attr
        for node in ast.walk(harness_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "runtime.identify" in source
    assert {name for name in calls if name.startswith("encode_")} == set()


# ------------------------------------- 33. the JSON is the evidence ---------


REQUIRED_KEYS = {
    "phase", "channel", "timeout_seconds", "operation", "transport",
    "response", "runtime", "observed", "error", "integration_error",
    "verdict", "exit_code", "non_claims",
}


@pytest.mark.parametrize("scenario", [s for s, _, _ in EXIT_CASES])
def test_every_run_emits_the_same_top_level_shape(scenario):
    """A later evidence capture has to diff runs against each other, so the
    shape cannot depend on how well the run went."""
    result = probe(scenario)["result"]

    assert set(result) == REQUIRED_KEYS
    assert result["phase"] == "1B-LIVE-A"
    assert result["channel"] in ("http", "file")
    assert set(result["operation"]) == {"operation_rid", "op"}
    assert set(result["response"]) == {
        "document_received", "parse_state", "status", "detail",
    }


@pytest.mark.parametrize("scenario", [s for s, _, _ in EXIT_CASES])
def test_the_emitted_result_survives_a_json_round_trip(scenario):
    observed = probe(scenario)
    result = observed["result"]

    assert json.loads(json.dumps(result)) == result
    assert result["exit_code"] == observed["exit_code"]


def test_the_declared_channel_and_budget_are_echoed_for_the_record():
    result = probe("http_ok", timeout="3.25")["result"]

    assert result["channel"] == "http"
    assert result["timeout_seconds"] == 3.25


def test_the_result_states_what_the_run_did_not_establish():
    """A successful `runtime.identify` is one observation from one channel. The
    persistence claims need a second run, a reopen, or a restart, and none of
    them is inferable from this one."""
    result = probe("http_ok")["result"]

    assert set(result["non_claims"]) >= {
        "SCRIPT_ENGINE_SESSION_PERSISTENCE",
        "WEBVIEW_REOPEN_PERSISTENCE",
        "PT_RESTART_SESSION_CHANGE",
        "CROSS_CHANNEL_SESSION_AGREEMENT",
    }


def test_a_successful_http_run_claims_nothing_about_the_file_channel():
    result = probe("http_ok")["result"]

    assert result["channel"] == "http"
    assert "FILE_V6" in result["non_claims"]


def test_a_successful_file_run_claims_nothing_about_http():
    result = probe("file_ok")["result"]

    assert result["channel"] == "file"
    assert "HTTP_V6" in result["non_claims"]


def test_the_verdict_is_a_closed_vocabulary():
    verdicts = {probe(scenario)["result"]["verdict"] for scenario, _, _ in EXIT_CASES}

    assert verdicts <= {
        "VALID_V6_OK",
        "CLASSIFIED_NOT_VALID_V6_OK",
        "NO_CLASSIFIED_DOCUMENT",
    }
    assert probe("http_ok")["result"]["verdict"] == "VALID_V6_OK"


# ------------------------------------- the harness is not an MCP surface ----


def test_the_harness_is_not_registered_as_an_mcp_tool():
    """Operator-only. It must not appear on the product surface, and it must
    not reach into the adapter layer to get there."""
    source = HARNESS.read_text(encoding="utf-8")

    assert "tool_registry" not in source
    assert "register_tools" not in source
    assert "mcp.tool" not in source


def test_the_tool_registry_does_not_know_this_harness_exists():
    registry = (
        REPO / "src" / "packet_tracer_mcp" / "adapters" / "mcp" / "tool_registry.py"
    ).read_text(encoding="utf-8")

    assert "runtime_v6_identify_live" not in registry
    assert "RuntimeProtocolClient" not in registry
