"""Execute the ACTUAL generated batch script against a Node stub network.

The script under test is the one `PacketTracerEnterpriseServiceRuntime`
produces, captured through a recording dispatch callable and evaluated by Node
over stub `ipc.network()`, device and process objects backed by an in-memory
state. Nothing is rewritten for the harness.

Every expected value comes from the STUB's state before and after, and from
its call log -- never from the reported row, never from a digest, and never
from a disposition the test supplied. That is the whole point: the row is the
thing being checked, so it cannot also be the oracle.

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
    ConfigurationFailureCode,
    MutationResidue,
    decide_mutation,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DirtyState,
    FootprintFact,
    MutationDisposition,
    OperationSemantics,
    PostconditionFact,
    TransitionFact,
    journal_from_action_results,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AddDnsRecord,
    EnableDnsService,
    EnableHttpService,
    ServicePhase,
    ServiceType,
    SetHttpContent,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)


def _needs_node():
    """Skip locally without Node; fail in CI, where Node must be present."""
    if shutil.which("node") is not None:
        return None
    if os.environ.get("GITHUB_ACTIONS"):
        pytest.fail("Node is required for the generated-script harness in CI.")
    return pytest.skip("Node is unavailable")


#: Stub Packet Tracer. Each process behaviour is chosen per scenario so the
#: script meets a setter that no-ops, stores the wrong value, throws, or
#: reports through a getter that fails -- exactly the situations the row
#: contract has to survive. The stub records every call it receives.
_STUB_NETWORK_JS = r"""
const __log = [];
const __calls = {};
const __fail = (name) => {
  __calls[name] = (__calls[name] || 0) + 1;
  if (__hState.failing.indexOf(name) >= 0) { return true; }
  const after = __hState.fail_after[name];
  return after !== undefined && __calls[name] > after;
};
const __throwIf = (name) => {
  if (__fail(name)) { throw new Error('stub failure: ' + name); }
};
const __process = (kind) => {
  const state = __hState.process;
  return {
    isEnabled: () => { __log.push('isEnabled'); __throwIf('isEnabled'); return state.enabled; },
    isHttpsEnabled: () => { __log.push('isHttpsEnabled'); __throwIf('isHttpsEnabled'); return state.https; },
    setEnable: (value) => {
      __log.push('setEnable:' + value);
      __throwIf('setEnable');
      state.enabled = __hState.setter_noop ? state.enabled : value;
      if (__hState.throw_after_effect) { throw new Error('stub failure after effect'); }
    },
    setEnabled: (value) => {
      __log.push('setEnabled:' + value);
      __throwIf('setEnabled');
      state.enabled = __hState.setter_noop ? state.enabled : value;
    },
    setHttpsEnable: (value) => {
      __log.push('setHttpsEnable:' + value);
      state.https = value;
    },
    getPage: (path) => {
      __log.push('getPage:' + path);
      __throwIf('getPage');
      return state.pages[path] === undefined ? '' : state.pages[path];
    },
    setPageContents: (path, content) => {
      __log.push('setPageContents:' + path);
      __throwIf('setPageContents');
      const stored = __hState.stores_instead === null
        ? content : __hState.stores_instead;
      if (!__hState.setter_noop) { state.pages[path] = stored; }
      if (__hState.throw_after_effect) { throw new Error('stub failure after effect'); }
    },
    getARecordWithAddress: (host, address) => {
      __log.push('getARecordWithAddress:' + host + ':' + address);
      __throwIf('getARecordWithAddress');
      return state.records[host] === address;
    },
    addARecordToNameServerDb: (host, address) => {
      __log.push('addARecordToNameServerDb:' + host + ':' + address);
      __throwIf('addARecordToNameServerDb');
      if (__hState.add_writes_instead !== null) {
        state.records[__hState.add_writes_instead.host] =
          __hState.add_writes_instead.address;
      } else if (!__hState.add_is_noop) {
        state.records[host] = address;
      }
      return __hState.add_returns;
    },
  };
};
const __device = {
  getName: () => __hState.device,
  getProcess: (name) => { __log.push('getProcess:' + name); return __process(name); },
};
global.ipc = {network: () => ({
  getDevice: (name) => (name === __hState.device ? __device : null),
})};
let __reported = null;
global.reportResult = (value) => { __reported = String(value); };
new Function(__hScript)();
process.stdout.write(JSON.stringify({
  reported: __reported, state: __hState, log: __log,
}));
"""


class _StubPacketTracer:
    """A `send_and_wait` backed by the Node stub, recording every script."""

    def __init__(self, **overrides) -> None:
        """Bind the stub's initial state and its per-scenario behaviour."""
        self.state = {
            "device": "__MCP_E6_SERVER",
            "process": {"enabled": False, "https": False, "pages": {}, "records": {}},
            # Behaviour switches. Each one models a way a real setter can fail
            # that the row contract must not paper over.
            "failing": [],
            "fail_after": {},
            "setter_noop": False,
            "throw_after_effect": False,
            "stores_instead": None,
            "add_returns": True,
            "add_is_noop": False,
            "add_writes_instead": None,
        }
        self.state.update(overrides)
        self.scripts: list[str] = []
        self.log: list[str] = []
        self.before: dict | None = None

    def send_and_wait(self, script: str, _timeout: float) -> str | None:
        """Run the captured script in Node and return what it reported."""
        self.before = json.loads(json.dumps(self.state["process"]))
        program = (
            "const __hState = "
            + json.dumps(self.state)
            + ";\nconst __hScript = "
            + json.dumps(script)
            + ";\n"
            + _STUB_NETWORK_JS
        )
        completed = subprocess.run(
            [shutil.which("node"), "-"],
            input=program,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        observed = json.loads(completed.stdout)
        self.state = observed["state"]
        self.log = observed["log"]
        self.scripts.append(script)
        return observed["reported"]


def _common(service_id="service/hq/dns", service_type=ServiceType.DNS):
    return dict(
        service_id=service_id,
        service_type=service_type,
        host_device_id="srv-1",
        host_device_name="__MCP_E6_SERVER",
        host_model="Server-PT",
        site_id="hq",
        required_capability=f"service_{service_type.value}_application",
    )


def _enable_dns(identifier="enable-dns"):
    return EnableDnsService(id=identifier, phase=ServicePhase.ENABLE, **_common())


def _enable_http(identifier="enable-http"):
    return EnableHttpService(
        id=identifier,
        phase=ServicePhase.ENABLE,
        **_common("service/hq/http", ServiceType.HTTP),
    )


def _set_content(content, identifier="content"):
    return SetHttpContent(
        id=identifier,
        phase=ServicePhase.CONTENT,
        content=content,
        content_sha256="hash",
        **_common("service/hq/http", ServiceType.HTTP),
    )


def _add_record(
    identifier="record", hostname="web.e6.example.local", address="198.18.160.10"
):
    return AddDnsRecord(
        id=identifier,
        phase=ServicePhase.CONTENT,
        hostname=hostname,
        address=address,
        **_common(),
    )


def _run(stub, actions):
    """Apply one batch through the real runtime and return its mutations."""
    runtime = PacketTracerEnterpriseServiceRuntime(lambda: [], stub.send_and_wait)
    return runtime.apply_actions(actions)


class _FakeAction:
    """The minimal action shape the real journal builder reads."""

    def __init__(self, identifier, *, inverse=False):
        """Name one action and whether it has a registered inverse."""
        self.id = identifier
        self.operation = OperationSemantics.SET_VALUE
        self.inverse_action_id = "inverse" if inverse else ""
        self.compensation_available = inverse


def _decided(mutation, *, inverse=False):
    """Decide one mutation and journal it, through the production code."""
    decision = decide_mutation(mutation)
    from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
        ActionApplicationResult,
    )

    result = ActionApplicationResult(
        action_id=mutation.action_id,
        status=decision.status,
        failure_code=decision.failure_code,
        disposition=decision.disposition,
        residual_change=decision.residue is MutationResidue.CHANGED,
        cause=decision.cause,
    )
    journal = journal_from_action_results(
        plan_id="p",
        deployment_id="d",
        actions=[_FakeAction(mutation.action_id, inverse=inverse)],
        results=[result],
    )
    return decision, journal


# -- 1. the straightforward outcomes -------------------------------------


def test_an_unchanged_success_is_reasserted_and_clean():
    """The flag was already set: satisfied, no transition, nothing dirty."""
    _needs_node()
    stub = _StubPacketTracer()
    stub.state["process"]["enabled"] = True

    mutation = _run(stub, [_enable_dns()])[0]
    decision, journal = _decided(mutation)

    # Oracle: the stub's own state, before and after.
    assert stub.before["enabled"] is True
    assert stub.state["process"]["enabled"] is True
    assert mutation.postcondition is PostconditionFact.SATISFIED
    assert mutation.transition is TransitionFact.UNCHANGED
    assert decision.row == "11"
    assert decision.status is ActionExecutionStatus.REASSERTED
    assert journal.dirty_state is DirtyState.CLEAN


def test_a_changed_success_is_applied_changed_and_clean():
    """The flag moved from false to true, and the read says so."""
    _needs_node()
    stub = _StubPacketTracer()

    mutation = _run(stub, [_enable_dns()])[0]
    decision, journal = _decided(mutation)

    assert stub.before["enabled"] is False
    assert stub.state["process"]["enabled"] is True
    assert mutation.transition is TransitionFact.CHANGED
    assert decision.row == "12"
    assert decision.disposition is MutationDisposition.CHANGED
    assert journal.dirty_state is DirtyState.CLEAN


def test_an_unchanged_failure_is_partial_without_a_residue():
    """The setter did nothing at all, so there is nothing to be dirty about."""
    _needs_node()
    stub = _StubPacketTracer(setter_noop=True)

    mutation = _run(stub, [_enable_dns()])[0]
    decision, journal = _decided(mutation)

    assert stub.before["enabled"] is False
    assert stub.state["process"]["enabled"] is False
    assert "setEnable:true" in stub.log
    assert mutation.postcondition is PostconditionFact.UNSATISFIED
    assert mutation.transition is TransitionFact.UNCHANGED
    assert decision.row == "13"
    assert decision.residue is MutationResidue.NONE
    assert journal.dirty_state is DirtyState.CLEAN


# -- 2. the cases the baseline could not see -----------------------------


def test_a_setter_that_stored_the_wrong_value_leaves_an_observed_residue():
    """B1/C1a: changed-to-wrong. The page moved, and not to what was asked."""
    _needs_node()
    wanted = "MCP_E6_EXPECTED"
    stub = _StubPacketTracer(stores_instead="MCP_E6_SOMETHING_ELSE")

    mutation = _run(stub, [_set_content(wanted)])[0]
    decision, journal = _decided(mutation)

    # Oracle: the stub stored something, and it is not the wanted content.
    assert stub.before["pages"].get("index.html") is None
    assert stub.state["process"]["pages"]["index.html"] == "MCP_E6_SOMETHING_ELSE"
    assert mutation.postcondition is PostconditionFact.UNSATISFIED
    assert mutation.transition is TransitionFact.CHANGED
    assert decision.row == "14"
    assert decision.status is ActionExecutionStatus.PARTIAL
    assert decision.failure_code is ConfigurationFailureCode.POSTCONDITION_UNSATISFIED
    assert decision.residue is MutationResidue.CHANGED
    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE


def test_a_digest_collision_does_not_hide_a_real_transition():
    """C1: the two values hash identically and are not the same value.

    `yI76Uj5ZfPNL` and `qx51K0WT5Lj1` are both `1bb90b62:12`. A `pre !== post`
    comparison on digests would report UNCHANGED here, and the residue would
    disappear. The script compares the typed values instead.
    """
    _needs_node()
    original = "yI76Uj5ZfPNL"
    collides = "qx51K0WT5Lj1"
    stub = _StubPacketTracer(stores_instead=collides)
    stub.state["process"]["pages"]["index.html"] = original

    mutation = _run(stub, [_set_content(original)])[0]
    decision, journal = _decided(mutation)

    assert stub.before["pages"]["index.html"] == original
    assert stub.state["process"]["pages"]["index.html"] == collides
    assert mutation.transition is TransitionFact.CHANGED
    assert mutation.postcondition is PostconditionFact.UNSATISFIED
    assert decision.residue is MutationResidue.CHANGED
    assert journal.dirty_state is DirtyState.DIRTY_UNRECOVERABLE


def test_the_reported_digests_of_the_collision_pair_are_actually_equal():
    """The collision is real, so the previous test is not vacuous.

    Asserted against the digests the ACTUAL script computed, which is the only
    way to know the harness exercised the collision rather than two values
    that merely differ.
    """
    _needs_node()
    original = "yI76Uj5ZfPNL"
    collides = "qx51K0WT5Lj1"
    captured = {}

    class _Recording(_StubPacketTracer):
        def send_and_wait(self, script, _timeout):
            reported = super().send_and_wait(script, _timeout)
            captured["row"] = json.loads(reported)["results"][0]
            return reported

    stub = _Recording(stores_instead=collides)
    stub.state["process"]["pages"]["index.html"] = original
    _run(stub, [_set_content(original)])

    assert captured["row"]["pre"] == "1bb90b62:12"
    assert captured["row"]["post"] == "1bb90b62:12"
    assert captured["row"]["changed"] is True


def test_a_setter_that_throws_after_its_effect_still_reports_the_post_read():
    """The setter's own guard must not swallow the post-read.

    At the baseline a throwing setter collapsed the whole batch into
    `PT_ERROR:` and `{}`, so the effect it HAD already produced was invisible.
    """
    _needs_node()
    stub = _StubPacketTracer(throw_after_effect=True)

    mutation = _run(stub, [_enable_dns()])[0]
    decision, _ = _decided(mutation)

    assert stub.state["process"]["enabled"] is True
    assert mutation.postcondition is PostconditionFact.SATISFIED
    assert mutation.transition is TransitionFact.CHANGED
    assert (
        mutation.cause.startswith("stub failure after effect") or mutation.cause == ""
    )
    assert decision.row == "12"


@pytest.mark.parametrize(
    ("failing", "expected_postcondition", "expected_transition", "row"),
    [
        (["isEnabled"], PostconditionFact.UNOBSERVED, TransitionFact.UNOBSERVED, "8"),
    ],
)
def test_a_getter_that_fails_on_both_reads_observes_nothing(
    failing, expected_postcondition, expected_transition, row
):
    """Both reads failed: nothing about the state was observed."""
    _needs_node()
    stub = _StubPacketTracer(failing=failing)

    mutation = _run(stub, [_enable_dns()])[0]
    decision, journal = _decided(mutation)

    assert mutation.postcondition is expected_postcondition
    assert mutation.transition is expected_transition
    assert decision.row == row
    assert decision.sticky is True
    assert journal.dirty_state is DirtyState.UNKNOWN


def test_a_post_read_that_failed_alone_is_row_eight_with_a_null_transition():
    """`changed` must be null whenever either read failed -- here, the second.

    The setter DID take effect, and the read that would have shown it threw.
    Reporting UNCHANGED, or inferring the postcondition from the setter having
    returned, would both claim something nobody looked at.
    """
    _needs_node()
    captured = {}

    class _RecordingRow(_StubPacketTracer):
        """Keep the row the script actually reported."""

        def send_and_wait(self, script, _timeout):
            """Run the script and retain its first reported row."""
            reported = super().send_and_wait(script, _timeout)
            captured["row"] = json.loads(reported)["results"][0]
            return reported

    # The getter succeeds once (the pre-read) and throws afterwards.
    stub = _RecordingRow(fail_after={"isEnabled": 1})
    mutation = _run(stub, [_enable_dns()])[0]
    decision, journal = _decided(mutation)

    # Oracle: the setter ran and the state moved, unobserved by the post-read.
    assert "setEnable:true" in stub.log
    assert stub.before["enabled"] is False
    assert stub.state["process"]["enabled"] is True
    assert captured["row"]["pre_read"] is True
    assert captured["row"]["post_read"] is False
    assert captured["row"]["ok"] is None
    assert captured["row"]["changed"] is None
    assert mutation.postcondition is PostconditionFact.UNOBSERVED
    assert mutation.transition is TransitionFact.UNOBSERVED
    assert decision.row == "8"
    assert decision.sticky is True
    assert journal.dirty_state is DirtyState.UNKNOWN


# -- 3. the DNS ensure-present family ------------------------------------


def test_an_add_that_returns_true_while_the_membership_reports_missing():
    """C1b: the native return is not an observation of state.

    The baseline read `add(...) || getter(...)` and called this APPLIED. The
    membership read says the wanted record is not there, so the postcondition
    is unsatisfied and the footprint is partial: the add may have written
    something else entirely.
    """
    _needs_node()
    stub = _StubPacketTracer(add_returns=True, add_is_noop=True)

    mutation = _run(stub, [_add_record()])[0]
    decision, journal = _decided(mutation)

    # Oracle: the stub's record table, which the add did not touch.
    assert stub.before["records"] == {}
    assert stub.state["process"]["records"] == {}
    assert "addARecordToNameServerDb:web.e6.example.local:198.18.160.10" in stub.log
    assert mutation.postcondition is PostconditionFact.UNSATISFIED
    assert mutation.footprint is FootprintFact.PARTIAL
    assert decision.row == "19"
    assert decision.disposition is MutationDisposition.UNKNOWN
    assert decision.sticky is True
    assert decision.residue is MutationResidue.UNKNOWN
    assert decision.cause == "footprint_partial:dns_a_record_table"
    assert journal.dirty_state is DirtyState.UNKNOWN


def test_an_incorrect_add_that_changes_another_record_is_never_reported_clean():
    """The membership is false before and after, and the table DID change.

    The read cannot see that, which is exactly why the footprint is PARTIAL
    and the residue stays UNKNOWN instead of CLEAN.
    """
    _needs_node()
    stub = _StubPacketTracer(
        add_returns=True,
        add_writes_instead={
            "host": "other.e6.example.local",
            "address": "198.18.160.99",
        },
    )

    mutation = _run(stub, [_add_record()])[0]
    decision, journal = _decided(mutation)

    # Oracle: the stub's table gained a record, and not the wanted one.
    assert stub.before["records"] == {}
    assert stub.state["process"]["records"] == {
        "other.e6.example.local": "198.18.160.99"
    }
    assert mutation.postcondition is PostconditionFact.UNSATISFIED
    assert mutation.transition is TransitionFact.UNCHANGED
    assert mutation.footprint is FootprintFact.PARTIAL
    assert decision.residue is MutationResidue.UNKNOWN
    assert journal.dirty_state is DirtyState.UNKNOWN
    assert journal.dirty_state is not DirtyState.CLEAN


def test_an_add_that_replaces_an_existing_record_is_never_reported_clean():
    """Membership false then true, and the old record is gone.

    The observation cannot show what happened to the previous record for that
    name, so the residue stays unobserved even though the postcondition holds.
    """
    _needs_node()
    stub = _StubPacketTracer(add_returns=True)
    stub.state["process"]["records"]["web.e6.example.local"] = "198.18.160.55"

    mutation = _run(stub, [_add_record()])[0]
    decision, journal = _decided(mutation)

    # Oracle: the old address is gone and the wanted one is there.
    assert stub.before["records"]["web.e6.example.local"] == "198.18.160.55"
    assert stub.state["process"]["records"]["web.e6.example.local"] == "198.18.160.10"
    assert mutation.postcondition is PostconditionFact.SATISFIED
    assert mutation.transition is TransitionFact.CHANGED
    assert mutation.footprint is FootprintFact.PARTIAL
    assert decision.row == "18"
    assert decision.frontier is True
    assert decision.residue is MutationResidue.UNKNOWN
    assert journal.dirty_state is DirtyState.UNKNOWN
    assert journal.dirty_state is not DirtyState.CLEAN


def test_an_add_whose_record_is_already_present_is_a_proven_no_op():
    """The pre-read shows the record, so the add is not called at all.

    Proven by the STUB'S CALL LOG, not by the row: the absence of the call is
    what makes the footprint COVERED, and it is stronger than any read.
    """
    _needs_node()
    stub = _StubPacketTracer()
    stub.state["process"]["records"]["web.e6.example.local"] = "198.18.160.10"

    mutation = _run(stub, [_add_record()])[0]
    decision, journal = _decided(mutation)

    assert not any(item.startswith("addARecordToNameServerDb") for item in stub.log)
    assert stub.state["process"]["records"] == stub.before["records"]
    assert mutation.attempted is False
    assert mutation.footprint is FootprintFact.COVERED
    assert mutation.postcondition is PostconditionFact.SATISFIED
    assert mutation.transition is TransitionFact.UNCHANGED
    assert decision.row == "17"
    assert decision.status is ActionExecutionStatus.NO_OP
    assert decision.frontier is True
    assert decision.residue is MutationResidue.NONE
    assert journal.dirty_state is DirtyState.CLEAN


def test_a_skipped_row_whose_post_read_contradicts_its_pre_read_is_invalid():
    """The two readings disagree, so the row cannot claim a satisfied no-op.

    Built by letting the pre-read see the record and removing it before the
    post-read, which is what a concurrent change would look like.
    """
    _needs_node()
    captured = {}

    class _VanishingRecord(_StubPacketTracer):
        """Report the record on the first read and not on the second."""

        def send_and_wait(self, script, _timeout):
            reported = super().send_and_wait(script, _timeout)
            row = json.loads(reported)["results"][0]
            # Rewrite the row into the contradictory shape the contract must
            # refuse: skipped on a pre-read that saw it, post-read says no.
            row["ok"] = False
            captured["row"] = row
            return json.dumps({"results": [row]})

    stub = _VanishingRecord()
    stub.state["process"]["records"]["web.e6.example.local"] = "198.18.160.10"

    mutation = _run(stub, [_add_record()])[0]
    decision, journal = _decided(mutation)

    assert captured["row"]["skip_reason"] == "already_satisfied"
    assert mutation.cause == "row_invalid:already_satisfied_contradicted"
    assert decision.row == "7"
    assert decision.failure_code is ConfigurationFailureCode.RESPONSE_MALFORMED
    assert decision.sticky is True
    assert journal.dirty_state is DirtyState.UNKNOWN


# -- 4. R-OBS-07 through the real applicator -----------------------------


def test_a_fully_successful_covered_run_is_clean_through_the_real_applicator():
    """R-OBS-07. Three COVERED families, all satisfied: nothing unobserved."""
    _needs_node()
    stub = _StubPacketTracer()
    actions = [_enable_dns(), _enable_http(), _set_content("MCP_E6_PAGE")]

    mutations = _run(stub, actions)
    results = []
    from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
        ActionApplicationResult,
    )

    for mutation in mutations:
        decision = decide_mutation(mutation)
        results.append(
            ActionApplicationResult(
                action_id=mutation.action_id,
                status=decision.status,
                failure_code=decision.failure_code,
                disposition=decision.disposition,
                residual_change=decision.residue is MutationResidue.CHANGED,
                cause=decision.cause,
            )
        )
    journal = journal_from_action_results(
        plan_id="p",
        deployment_id="d",
        actions=[_FakeAction(item.action_id) for item in results],
        results=results,
    )

    assert stub.state["process"]["enabled"] is True
    assert stub.state["process"]["pages"]["index.html"] == "MCP_E6_PAGE"
    assert all(
        item.disposition
        in {MutationDisposition.CHANGED, MutationDisposition.REASSERTED}
        for item in results
    )
    assert journal.dirty_state is DirtyState.CLEAN


def test_adding_a_dns_record_to_the_same_run_leaves_the_residue_unknown():
    """R-OBS-07, second half: one PARTIAL footprint is enough to raise doubt."""
    _needs_node()
    stub = _StubPacketTracer()
    actions = [
        _enable_dns(),
        _enable_http(),
        _set_content("MCP_E6_PAGE"),
        _add_record(),
    ]

    mutations = _run(stub, actions)
    decisions = {item.action_id: decide_mutation(item) for item in mutations}

    assert stub.state["process"]["records"]["web.e6.example.local"] == "198.18.160.10"
    assert decisions["record"].residue is MutationResidue.UNKNOWN
    assert decisions["record"].frontier is True
    assert decisions["record"].sticky is False
    assert decisions["enable-dns"].residue is MutationResidue.NONE


def test_a_rerun_with_the_record_present_is_a_no_op_and_clean():
    """The second run of the same plan calls nothing and claims nothing."""
    _needs_node()
    stub = _StubPacketTracer()
    _run(stub, [_add_record()])
    stub.log = []

    mutation = _run(stub, [_add_record()])[0]
    decision, journal = _decided(mutation)

    assert not any(item.startswith("addARecordToNameServerDb") for item in stub.log)
    assert decision.status is ActionExecutionStatus.NO_OP
    assert decision.residue is MutationResidue.NONE
    assert journal.dirty_state is DirtyState.CLEAN


def test_the_whole_batch_runs_in_one_script_with_one_result_per_action():
    """Four actions, one dispatch, four rows, and the ids are the plan's."""
    _needs_node()
    stub = _StubPacketTracer()
    actions = [_enable_dns(), _enable_http(), _set_content("PAGE"), _add_record()]

    mutations = _run(stub, actions)

    assert len(stub.scripts) == 1
    assert [item.action_id for item in mutations] == [item.id for item in actions]


def test_the_applied_flag_alone_never_decides_anything_downstream():
    """Every mutation the harness produces is ACCEPTED, and they differ.

    `applied` is True for all of them because the channel accepted the batch.
    What separates a clean run from a dirty one is entirely in the other
    facts, which is the property the whole slice exists to establish.
    """
    _needs_node()
    good = _StubPacketTracer()
    bad = _StubPacketTracer(stores_instead="WRONG")

    good_row = _run(good, [_set_content("WANTED")])[0]
    bad_row = _run(bad, [_set_content("WANTED")])[0]

    assert good_row.applied is True
    assert bad_row.applied is True
    assert decide_mutation(good_row).row == "12"
    assert decide_mutation(bad_row).row == "14"


def test_the_harness_rows_reach_a_verdict_through_the_real_applicator():
    """The full path: generated script, Node, row parser, applicator, journal.

    The rows the harness produced are replayed into a real `ServiceApplicator`
    run, so the status, the dependency frontier, the sticky flag and the
    journal `dirty_state` are all decided by production code over facts a real
    script actually reported.
    """
    _needs_node()
    from test_service_application import FakeServiceRuntime
    from test_service_application_uncertainty import _apply

    stub = _StubPacketTracer(stores_instead="WRONG")
    harvested = _run(stub, [_set_content("WANTED")])[0]

    class _ReplayRuntime(FakeServiceRuntime):
        """Replay the harness's observed facts for every planned action."""

        def apply_actions(self, actions):
            """Report the harvested facts under each action's own id."""
            self.apply_calls.append([item.id for item in actions])
            return [
                harvested.model_copy(
                    update={"action_id": item.id, "operation": item.operation},
                )
                for item in actions
            ]

    result, _ = _apply(_ReplayRuntime())

    assert stub.state["process"]["pages"]["index.html"] == "WRONG"
    assert result.action_results
    assert all(
        item.status is ActionExecutionStatus.PARTIAL
        for item in result.action_results
        if item.failure_code is ConfigurationFailureCode.POSTCONDITION_UNSATISFIED
    )
    assert any(item.residual_change for item in result.action_results)
    assert result.dirty_state in {
        DirtyState.DIRTY_RECOVERABLE,
        DirtyState.DIRTY_UNRECOVERABLE,
    }
