"""Execute the ACTUAL generated web-verification scripts against Node stubs.

The scripts under test are the ones `PacketTracerEnterpriseServiceRuntime`
produces for an HTTP or HTTPS expectation, evaluated by one LONG-LIVED Node
process over a stub `HttpBackgroundClientManager`. The process outlives the
individual evaluations on purpose: `this.__mcpE6HttpClients` is the ownership
bag, it lives on the global object between `new Function()` calls in Packet
Tracer, and a harness that restarted the engine between scripts would lose
exactly the state this module is about.

Every expectation comes from the STUB: how many clients it created and has not
been asked to delete, and the call log it recorded. The reported row is the
thing under test, so it is never also the oracle -- a row claiming
`released:true` while the stub still holds a live client is the defect this
module exists to catch.

Nothing here observes Packet Tracer. The stub answers the documented call
surface; whether a real `HttpBackgroundClient` behaves this way is gate
M-HTTPS-2 and stays unqualified.

Skipped only when Node is missing locally. Under `GITHUB_ACTIONS` it fails
instead, so CI is the oracle rather than a silent skip.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

#: The stub network, driven one script per stdin line. `new Function(...)()` is
#: called with no receiver, so `this` inside the evaluated script is the global
#: object -- the same place Packet Tracer's `executeCode` puts it, which is why
#: the ownership bag survives from one script to the next.
_DRIVER_JS = r"""
const readline = require('readline');

const state = JSON.parse(process.argv[2]);
const log = [];
const live = {};
const seen = {};
let sequence = 0;

const guard = (name, detail) => {
  log.push(detail === undefined ? name : name + ':' + detail);
  seen[name] = (seen[name] || 0) + 1;
  const after = state.throw_after[name];
  if (state.throw_on.indexOf(name) >= 0) {
    throw new Error('stub failure: ' + name);
  }
  if (after !== undefined && seen[name] > after) {
    throw new Error('stub failure after ' + after + ': ' + name);
  }
};

const makeClient = () => {
  sequence += 1;
  const id = 'client-' + sequence;
  live[id] = true;
  return {
    id: id,
    getLastPageContent: () => { guard('getLastPageContent'); return state.page; },
    setHttps: (value) => { guard('setHttps', value); state.https_mode = !!value; },
    isHttps: () => {
      guard('isHttps');
      return state.https_reports === null ? state.https_mode : state.https_reports;
    },
    go: (url) => {
      guard('go', url);
      if (state.go_sets_page !== null) { state.page = state.go_sets_page; }
      return state.go_returns;
    },
  };
};

const manager = {
  createClient: () => {
    guard('createClient');
    return state.create_returns_null ? null : makeClient();
  },
  deleteClient: (client) => {
    guard('deleteClient', client && client.id ? client.id : String(client));
    if (client && client.id) { delete live[client.id]; }
  },
};

const device = {
  getName: () => state.device,
  getProcess: (name) => {
    log.push('getProcess:' + name);
    if (name !== 'HttpBackgroundClientManager') { return null; }
    return state.manager_missing ? null : manager;
  },
};

global.ipc = {network: () => ({
  getDevice: (name) => (name === state.device ? device : null),
})};

let reported = null;
global.reportResult = (value) => { reported = String(value); };

readline.createInterface({input: process.stdin}).on('line', (line) => {
  const message = JSON.parse(line);
  if (message.kind === 'state') {
    Object.assign(state, message.state);
    process.stdout.write(JSON.stringify({ok: true}) + '\n');
    return;
  }
  reported = null;
  let failure = '';
  try {
    new Function(message.script)();
  } catch (error) {
    failure = String(error && error.message ? error.message : error);
  }
  const bag = global.__mcpE6HttpClients || {};
  process.stdout.write(JSON.stringify({
    reported: reported,
    failure: failure,
    live: Object.keys(live).length,
    tracked: Object.keys(bag).length,
    log: log.splice(0, log.length),
  }) + '\n');
});
"""


def _needs_node():
    """Skip locally without Node; fail in CI, where Node must be present."""
    if shutil.which("node") is not None:
        return None
    if os.environ.get("GITHUB_ACTIONS"):
        pytest.fail("Node is required for the client-ownership harness in CI.")
    return pytest.skip("Node is unavailable")


class _ClientStub:
    """A typed command channel backed by one long-lived Node stub network.

    `transport` injects a controlled channel boundary per phase: `sent_lost`
    and `sent_malformed` still EXECUTE the script, so the stub's real side
    effects happen while Python observes nothing usable, and `not_submitted`
    does not execute it at all. That is how a start whose response was lost is
    distinguished from a start that never reached the engine.

    `payload` replaces the reported body of one phase AFTER its script has run,
    so the stub's real state stands while the reader is handed a payload the
    generated script could not have produced. That is the only way to ask what
    the reader concludes from a self-contradictory stage answer without
    rewriting the script under test.
    """

    def __init__(self, tmp_path, **overrides) -> None:
        """Start the stub with its initial state and behaviour switches."""
        self.state = {
            "device": "__MCP_E6_PC",
            "page": "",
            "go_returns": True,
            "go_sets_page": "MCP_E6_PAGE_MARKER",
            "https_mode": False,
            "https_reports": None,
            "create_returns_null": False,
            "manager_missing": False,
            "throw_on": [],
            "throw_after": {},
        }
        self.state.update(overrides)
        self.transport: dict[str, str] = {}
        self.payload: dict[str, str] = {}
        self.phases: list[str] = []
        self.log: list[str] = []
        self.live = 0
        self.tracked = 0
        driver = tmp_path / "client_driver.js"
        driver.write_text(_DRIVER_JS, encoding="utf-8")
        self._process = subprocess.Popen(
            [shutil.which("node"), str(driver), json.dumps(self.state)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

    def close(self) -> None:
        """Stop the stub engine."""
        if self._process.stdin is not None:
            self._process.stdin.close()
        self._process.wait(timeout=10)

    @staticmethod
    def _phase(script: str) -> str:
        """Name which of the three generated scripts this is."""
        if "createClient()" in script:
            return "start"
        if "deleteClient" in script:
            return "release"
        return "inspect"

    def set_state(self, **overrides) -> None:
        """Change a behaviour switch between scripts."""
        self._exchange({"kind": "state", "state": overrides})

    def _exchange(self, message: dict) -> dict:
        """Send one line to the stub engine and read its answer."""
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()
        line = self._process.stdout.readline()
        if not line:
            raise AssertionError("The Node stub engine closed unexpectedly.")
        return json.loads(line)

    def _run(self, script: str) -> dict:
        """Evaluate one script and absorb the stub's own observations."""
        reply = self._exchange({"kind": "script", "script": script})
        self.live = reply["live"]
        self.tracked = reply["tracked"]
        self.log.extend(reply["log"])
        return reply

    def dispatch_and_wait(self, script: str, _timeout: float):
        """Run one command through the injected boundary for its phase."""
        phase = self._phase(script)
        self.phases.append(phase)
        override = self.transport.get(phase, "")
        if override == "not_submitted":
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.NOT_SUBMITTED,
                result=ResultFact.NOT_APPLICABLE,
                detail="stub_never_left_the_process",
            )
        if override == "raises":
            raise RuntimeError("stub channel failure")
        reply = self._run(script)
        if override == "sent_lost":
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.NOT_OBSERVED,
                detail="stub_deadline",
            )
        if override == "sent_malformed":
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.CORRELATED,
                body="<html>not json</html>",
            )
        body = (
            "PT_ERROR: " + reply["failure"] if reply["failure"] else reply["reported"]
        )
        if phase in self.payload:
            body = self.payload[phase]
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=body,
        )

    def deletions(self) -> list[str]:
        """Every `deleteClient` the stub actually received, in order."""
        return [item for item in self.log if item.startswith("deleteClient:")]

    def creations(self) -> int:
        """How many clients the stub was asked to create."""
        return len([item for item in self.log if item == "createClient"])


@pytest.fixture
def stub(tmp_path):
    """One stub engine per test, stopped whatever the test does."""
    _needs_node()
    made: list[_ClientStub] = []

    def factory(**overrides):
        instance = _ClientStub(tmp_path, **overrides)
        made.append(instance)
        return instance

    yield factory
    for instance in made:
        instance.close()


def _runtime(stub_instance):
    """Bind the real runtime to the stub's typed channel, polling once."""
    return PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda js, timeout: None,
        dispatch_and_wait=stub_instance.dispatch_and_wait,
        http_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )


def _expectation(
    kind=ServiceVerificationKind.HTTP_FETCH,
    *,
    marker="MCP_E6_PAGE_MARKER",
    scheme="http",
    identifier="verify-web",
):
    return ServiceVerificationExpectation(
        id=identifier,
        service_id="service/hq/http",
        action_id="content",
        kind=kind,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        client_device_id="pc-1",
        client_device_name="__MCP_E6_PC",
        expected={"address": "198.18.160.10", "marker": marker, "scheme": scheme},
    )


def _unresolved(row) -> list[str]:
    """Return the ownership limitations the row carries, if any."""
    return [
        item
        for item in row.limitations
        if item.startswith("client_ownership_unresolved:")
    ]


# -- 1. the happy path still releases exactly its own resource ------------


def test_a_successful_fetch_releases_exactly_the_client_it_created(stub):
    """One client created, one deleted, and the stub holds nothing after."""
    engine = stub()

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert len(engine.deletions()) == 1
    assert engine.live == 0
    assert engine.tracked == 0
    assert row.status is ActionExecutionStatus.VERIFIED
    assert row.observation is ObservationFact.OBSERVED
    assert row.observed["released"] == "released"
    assert _unresolved(row) == []


def test_the_finalization_is_dispatched_exactly_once(stub):
    """Cleanup is bounded: one release command, never a retry loop."""
    engine = stub()

    _runtime(engine).verify(_expectation())

    assert engine.phases.count("release") == 1


# -- 2. a throw between creation and tracking -----------------------------


def test_a_throwing_initial_page_getter_still_releases_the_client(stub):
    """`getLastPageContent()` raised after the client existed."""
    engine = stub(throw_on=["getLastPageContent"])

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert engine.live == 0
    assert row.observation is ObservationFact.ENGINE_ERROR
    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.observed["released"] == "released"


def test_a_throwing_go_still_releases_the_client(stub):
    """`go()` raised, so the request state is unknown and the client is not."""
    engine = stub(throw_on=["go"])

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert engine.live == 0
    assert row.observation is ObservationFact.ENGINE_ERROR
    assert row.observed["released"] == "released"


@pytest.mark.parametrize("member", ["setHttps", "isHttps"])
def test_a_throwing_https_mode_call_still_releases_the_client(stub, member):
    """Both mode calls sit between creation and the old tracking point."""
    engine = stub(throw_on=[member])

    row = _runtime(engine).verify(
        _expectation(
            ServiceVerificationKind.HTTPS_FETCH,
            scheme="https",
            identifier="verify-https",
        )
    )

    assert engine.creations() == 1
    assert engine.live == 0
    assert row.observation is ObservationFact.ENGINE_ERROR
    assert row.observed["released"] == "released"


def test_a_client_that_did_not_start_is_released_rather_than_forgotten(stub):
    """`go()` false is an answer, and the client it answered about is owned."""
    engine = stub(go_returns=False)

    row = _runtime(engine).verify(_expectation())

    assert engine.live == 0
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "client_go_false"
    assert row.observed["released"] == "released"


# -- 3. a start whose outcome Python never observed -----------------------


def test_a_start_whose_response_was_lost_releases_the_client_it_finds(stub):
    """The script ran and tracked a client; the release finds and deletes it."""
    engine = stub()
    engine.transport["start"] = "sent_lost"

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert engine.live == 0
    assert row.observation is ObservationFact.NOT_OBSERVED
    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observed["released"] == "released"


def test_a_non_json_start_reply_still_releases_the_created_client(stub):
    """A malformed answer decides nothing about the client that exists."""
    engine = stub()
    engine.transport["start"] = "sent_malformed"

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert engine.live == 0
    assert row.observation is ObservationFact.MALFORMED
    assert row.observed["released"] == "released"


def test_a_start_that_never_reached_the_engine_leaves_ownership_unknown(stub):
    """An absent slot after an unobserved start is not proof of release."""
    engine = stub()
    engine.transport["start"] = "not_submitted"

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 0
    assert engine.live == 0
    assert row.observation is ObservationFact.NOT_SUBMITTED
    assert row.observed["released"] == "ownership_unknown"
    assert _unresolved(row) == [
        "client_ownership_unresolved:ownership_unknown:start_outcome_unobserved"
    ]


def test_a_channel_that_raises_on_the_start_still_finalizes(stub):
    """An exception in the reader does not skip the finalization."""
    engine = stub()
    engine.transport["start"] = "raises"

    row = _runtime(engine).verify(_expectation())

    assert engine.phases.count("release") == 1
    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "exception:RuntimeError"
    assert row.observed["released"] == "ownership_unknown"


# -- 4. failures after the request started --------------------------------


def test_an_inspection_that_throws_still_releases_the_client(stub):
    """The start read the page once; the inspection's read raises."""
    engine = stub(throw_after={"getLastPageContent": 1})

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert engine.live == 0
    assert row.observation is ObservationFact.ENGINE_ERROR
    assert row.observed["released"] == "released"


def test_a_channel_that_raises_during_polling_still_finalizes(stub):
    """The exception path is the one that used to escape to `verify`."""
    engine = stub()
    engine.transport["inspect"] = "raises"

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert engine.live == 0
    assert engine.phases.count("release") == 1
    assert row.cause == "exception:RuntimeError"
    assert row.observed["released"] == "released"


def test_a_deadline_with_no_response_releases_and_stays_inconclusive(stub):
    """No content change is not a negative observation, and the client goes."""
    engine = stub(go_sets_page=None)

    row = _runtime(engine).verify(_expectation())

    assert engine.live == 0
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "no_response_within_deadline"
    assert row.observed["released"] == "released"


# -- 5. the cleanup itself fails ------------------------------------------


def test_a_successful_read_with_a_failing_delete_keeps_both_facts(stub):
    """The observation stands; the leak is reported, not hidden."""
    engine = stub(throw_after={"deleteClient": 0})

    row = _runtime(engine).verify(_expectation())

    # Oracle: the stub was asked to delete and still holds the client.
    assert len(engine.deletions()) == 1
    assert engine.live == 1
    assert row.status is ActionExecutionStatus.VERIFIED
    assert row.observation is ObservationFact.OBSERVED
    assert row.observed["released"] == "release_unverified"
    assert _unresolved(row) == [
        "client_ownership_unresolved:release_unverified:stub failure after 0: "
        "deleteClient"
    ]


def test_a_release_whose_reply_was_lost_is_not_a_release(stub):
    """The delete may have run; nothing came back, so nothing is claimed."""
    engine = stub()
    engine.transport["release"] = "sent_lost"

    row = _runtime(engine).verify(_expectation())

    assert row.status is ActionExecutionStatus.VERIFIED
    assert row.observed["released"] == "release_failed"
    assert _unresolved(row) == [
        "client_ownership_unresolved:release_failed:stub_deadline"
    ]


def test_a_release_that_never_reached_the_engine_is_not_a_release(stub):
    """A cleanup that never left the process left the client where it was."""
    engine = stub()
    engine.transport["release"] = "not_submitted"

    row = _runtime(engine).verify(_expectation())

    assert engine.live == 1
    assert row.observed["released"] == "release_failed"


# -- 6. no client to own --------------------------------------------------


def test_a_device_without_a_client_manager_is_a_missing_subject(stub):
    """No manager, no client: the subject was not observed, and nothing leaks."""
    engine = stub(manager_missing=True)

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 0
    assert engine.live == 0
    assert engine.phases.count("release") == 0
    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.observation is ObservationFact.SUBJECT_NOT_FOUND
    assert row.cause == "client_not_created"
    assert row.observed["released"] == "nothing_owned"
    assert _unresolved(row) == []


def test_a_manager_that_returns_no_client_is_a_missing_subject(stub):
    """`createClient()` answered null, which is not a client that failed."""
    engine = stub(create_returns_null=True)

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert engine.live == 0
    assert engine.phases.count("release") == 0
    assert row.observation is ObservationFact.SUBJECT_NOT_FOUND
    assert row.observed["released"] == "nothing_owned"


# -- 7. a previous client is retired, once -------------------------------


def test_a_second_read_retires_the_first_read_own_client(stub):
    """Two reads of the same expectation never leave two live clients."""
    engine = stub()
    runtime = _runtime(engine)

    runtime.verify(_expectation())
    engine.transport["release"] = "not_submitted"
    second = runtime.verify(_expectation())
    assert engine.live == 1
    engine.transport.pop("release")
    third = runtime.verify(_expectation())

    # The second read's release never left the process, so its client stayed
    # live and tracked; the third read retired it before creating its own.
    assert second.observed["released"] == "release_failed"
    assert engine.creations() == 3
    assert engine.live == 0
    assert third.observed["released"] == "released"


# -- 8. a stage answer that contradicts itself ----------------------------


def test_a_start_denying_a_client_it_started_does_not_prove_absence(stub):
    """`owned:false` with `started:true` cannot have come from the builder.

    `started` is `!!(p&&p.go(url))`, so it cannot be true without a client.
    Reading `owned` alone and returning at once granted ABSENT from a tuple
    that contradicts itself, and the finalization then reported
    `nothing_owned` without looking -- while the stub still held the client
    the script really did create.
    """
    engine = stub()
    engine.payload["start"] = json.dumps(
        {"owned": False, "started": True, "content_before": ""}
    )

    row = _runtime(engine).verify(_expectation())

    # Oracle: the script ran, so a client exists whatever the payload says.
    assert engine.creations() == 1
    # One start, one finalization, no re-dispatch and no channel fallback.
    assert engine.phases == ["start", "release"]
    assert engine.live == 0
    assert row.observed["released"] != "nothing_owned"
    assert row.observed["released"] == "released"
    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == "start_inconsistent:started_without_client"


def test_a_start_denying_a_client_whose_page_it_read_does_not_prove_absence(stub):
    """`content_before` is `p?String(...):''`, so text implies a client."""
    engine = stub()
    engine.payload["start"] = json.dumps(
        {"owned": False, "started": False, "content_before": "PAGE"}
    )

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 1
    assert engine.live == 0
    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == "start_inconsistent:content_without_client"
    assert row.observed["released"] == "released"


def test_a_coherent_no_client_start_still_avoids_unnecessary_cleanup(stub):
    """The positive control: a real no-client answer releases nothing."""
    engine = stub(manager_missing=True)

    row = _runtime(engine).verify(_expectation())

    assert engine.creations() == 0
    assert engine.phases.count("release") == 0
    assert row.observation is ObservationFact.SUBJECT_NOT_FOUND
    assert row.cause == "client_not_created"
    assert row.observed["released"] == "nothing_owned"
    assert _unresolved(row) == []


@pytest.mark.parametrize(
    ("payload", "cause"),
    [
        (
            {"found": False, "deleted": True, "present": False, "error": ""},
            "release_inconsistent:deleted_without_slot",
        ),
        (
            {"found": True, "deleted": True, "present": True, "error": ""},
            "release_inconsistent:deleted_but_present",
        ),
        (
            {"found": True, "deleted": True, "present": False, "error": "boom"},
            "release_inconsistent:deleted_with_error",
        ),
        (
            {"found": True, "deleted": False, "present": False, "error": "boom"},
            "release_inconsistent:not_deleted_but_absent",
        ),
        (
            {"found": True, "deleted": True, "present": False},
            "release_shape:missing:error",
        ),
        (
            {"found": True, "deleted": True, "present": False, "error": 7},
            "release_shape:not_a_string:error",
        ),
        (
            {"found": True, "deleted": 1, "present": False, "error": ""},
            "release_shape:not_a_boolean:deleted",
        ),
    ],
)
def test_a_release_that_contradicts_itself_is_never_a_release(stub, payload, cause):
    """Individually well-typed flags can still describe nothing coherent.

    Each tuple here is one the release script cannot produce: `deleted` is
    only ever set inside `if(found)`, after the call returned and before the
    `catch` that fills `error`, and the slot is dropped in the same
    evaluation. What the script CAN produce is not listed, however odd it
    looks -- see the malformed-slot case below.
    """
    engine = stub()
    engine.payload["release"] = json.dumps(payload)

    row = _runtime(engine).verify(_expectation())

    assert row.status is ActionExecutionStatus.VERIFIED
    assert row.observation is ObservationFact.OBSERVED
    assert row.observed["released"] == "release_unverified"
    assert _unresolved(row) == [
        "client_ownership_unresolved:release_unverified:" + cause
    ]


def test_an_unresolved_release_survives_serialization(stub):
    """An ownership residue must still be visible in a stored record."""
    engine = stub()
    engine.payload["release"] = json.dumps(
        {"found": False, "deleted": True, "present": False, "error": ""}
    )

    row = _runtime(engine).verify(_expectation())
    restored = RuntimeServiceVerification.model_validate_json(row.model_dump_json())

    assert restored.observed["released"] == "release_unverified"
    assert "deleted_without_slot" in " ".join(restored.limitations)


def test_a_coherent_release_still_closes_normally(stub):
    """The positive control: the real release payload is still a release."""
    engine = stub()

    row = _runtime(engine).verify(_expectation())

    assert engine.live == 0
    assert row.observed["released"] == "released"
    assert _unresolved(row) == []


def test_a_slot_without_a_client_is_unresolved_rather_than_contradictory(stub):
    """`found:false` with `present:true` is reachable, so it is not a lie.

    `found` is `!!(slot&&slot.manager&&slot.client)`, so a slot object
    missing either member reports exactly this. There is something owned
    here that the release could not act on, which is unresolved ownership --
    not an impossible answer and not a release.
    """
    engine = stub()
    engine.payload["release"] = json.dumps(
        {"found": False, "deleted": False, "present": True, "error": ""}
    )

    row = _runtime(engine).verify(_expectation())

    assert row.observed["released"] == "release_unverified"
    assert _unresolved(row) == [
        "client_ownership_unresolved:release_unverified:slot_not_usable"
    ]
