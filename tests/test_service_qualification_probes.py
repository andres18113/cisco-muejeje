"""Execute the ACTUAL generated Q0/Q1 probes against the Node stub engine.

Each script is the one `PacketTracerQualificationProbes` produces, evaluated by
one long-lived Node process whose state survives between evaluations like
Packet Tracer's engine global. Expectations come from the stub's snapshot:
which bag keys exist, which registrations are active, which unregister calls
arrived and which production globals exist. The reading under test is never
also its own oracle.

Nothing here observes Packet Tracer. These tests prove the scripts do what the
design says against an engine that behaves in a stated way. Whether the real
engine behaves that way is what Q0/Q1 would measure. The harness is skipped
locally without Node and fails under `GITHUB_ACTIONS`.
"""

from __future__ import annotations

import json

import pytest
from service_qualification_engine import NodeEngine, NodeEngineTransport

from packet_tracer_mcp.adapters.mcp import tool_registry
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    MeasurementConclusion,
)
from packet_tracer_mcp.domain.enterprise.services.service_qualification_evidence import (
    assess_atomicity,
    assess_bag_persistence,
    assess_observer_release,
    assess_page_tables,
    page_read_admits_second_write,
    page_write_established,
)
from packet_tracer_mcp.infrastructure.execution import service_environment
from packet_tracer_mcp.infrastructure.execution.service_environment import (
    READER_ID,
    READER_SHA256,
    SERVICE_ENVIRONMENT_JS,
    ServiceEnvironmentReader,
)
from packet_tracer_mcp.infrastructure.execution.service_qualification_probes import (
    PacketTracerQualificationProbes,
)

SUPPORTED = MeasurementConclusion.SUPPORTED_IN_SAMPLE
NEGATIVE = MeasurementConclusion.NEGATIVE_OBSERVED
CONTRADICTED = MeasurementConclusion.CONTRADICTED
INCONCLUSIVE = MeasurementConclusion.INCONCLUSIVE
RUN = "2026-09-18T10-00-00Z-0123abcd"
PC = "__MCP_E6Q_PC1"
SERVER = "__MCP_E6Q_SRV"


@pytest.fixture
def engine_factory(tmp_path):
    """Start stub engines on demand and stop them after the test."""
    started: list[NodeEngine] = []

    def start(**config) -> NodeEngine:
        directory = tmp_path / f"engine{len(started)}"
        directory.mkdir()
        engine = NodeEngine(directory, **config)
        started.append(engine)
        return engine

    yield start
    for engine in started:
        engine.close()


def _probes(engine: NodeEngine, run: str = RUN, nonce: str = "9" * 32):
    transport = NodeEngineTransport(engine)
    probes = PacketTracerQualificationProbes(
        run_id=run,
        nonce=nonce,
        dispatch_and_wait=transport.dispatch_and_wait,
        send=transport.send,
    )
    return probes, transport


def _claim(probes) -> None:
    """Claim the run key, as M-ENG-1 does before any other Q0 procedure.

    Every Q0 procedure declares M-ENG-1 as its prerequisite, so in a stage the
    run bag is always owned before a contender or an observer touches it. A
    test that drives a probe directly has to establish the same fact, because
    ownership is what the probe now proves before it writes.
    """
    write = probes.write_bag_sentinel()
    assert write.observed
    assert (write.payload["written"], write.payload["owned"]) == (True, True)


def _bag(engine: NodeEngine) -> dict:
    """Read the whole run-bag container straight out of the stub engine."""
    raw = engine.evaluate("reportResult(JSON.stringify(this.__mcpE6Q||{}));")
    return json.loads(raw)


def _plant_foreign_run_key(engine: NodeEngine, run: str = RUN) -> dict:
    """Place a run key this invocation did not write, and return its content."""
    planted = {
        "owner": "another-invocations-nonce",
        "sentinel": {"nonce": "another-invocations-nonce"},
        "unrelated": ["keep", "me"],
    }
    engine.evaluate(
        "var q=this.__mcpE6Q=this.__mcpE6Q||{};"
        f"q[{json.dumps(run)}]={json.dumps(planted)};reportResult('planted');"
    )
    assert _bag(engine)[run] == planted
    return planted


def _unregister(probes, *, device: str = PC):
    register = probes.register_observer_and_trigger(device)
    evidence = probes.read_observer_and_register_zero_event(device)
    release = probes.release_observers_and_trigger(device)
    after = probes.read_post_release_and_drop()
    return assess_observer_release(register, evidence, release, after)


# -- script hygiene --------------------------------------------------------------


def test_every_q0_probe_is_single_line_without_line_comments(engine_factory):
    """Pasted executeCode loses newlines; a `//` would swallow the rest."""
    engine = engine_factory()
    engine.seed_device(PC, "PC-PT")
    probes, transport = _probes(engine)
    probes.write_bag_sentinel()
    probes.read_and_release_bag_sentinel()
    probes.queue_atomicity_contender("A")
    probes.queue_atomicity_contender("B")
    probes.collect_atomicity()
    _unregister(probes)
    probes.release_run_bag()
    assert len(transport.calls) == 10
    for _kind, script in transport.calls:
        assert "\n" not in script and "//" not in script


def test_a_hostile_run_identity_is_data_not_code(engine_factory):
    """Every datum is serialized with json.dumps, so a quote cannot escape."""
    engine = engine_factory()
    hostile = 'r"];globalThis.pwned=1;x=["'
    probes, _transport = _probes(engine, run=hostile)
    write = probes.write_bag_sentinel()
    assert write.observed
    assert list(engine.snapshot()["run_bags"]) == [hostile]
    assert engine.evaluate("reportResult(typeof globalThis.pwned);") == "undefined"


# -- M-ENG-1 -------------------------------------------------------------------


def test_bag_sentinel_persists_on_a_global_receiver_and_is_released(engine_factory):
    """The stub keeps the bag between evaluations; the read releases the nonce."""
    engine = engine_factory()
    probes, _transport = _probes(engine)
    write = probes.write_bag_sentinel()
    assert (write.payload["written"], write.payload["owned"]) == (True, True)
    assert engine.snapshot()["run_bags"] == {RUN: ["owner", "sentinel"]}
    read = probes.read_and_release_bag_sentinel()
    # The owner stamp outlives the sentinel: it is what every later write and
    # the finalizer's delete prove before they touch this key.
    assert engine.snapshot()["run_bags"] == {RUN: ["owner"]}
    result = assess_bag_persistence(write, read, channel="file")
    assert result.conclusion is SUPPORTED
    assert result.facts["receiver_is_global_at_read"] is True
    assert result.facts["owned_at_read"] is True


def test_a_pre_existing_run_key_is_refused_without_a_single_write(engine_factory):
    """The check and the write are one decision, so a collision writes nothing."""
    engine = engine_factory()
    planted = _plant_foreign_run_key(engine)
    probes, _transport = _probes(engine)
    write = probes.write_bag_sentinel()
    assert write.observed
    assert write.payload["run_bag_preexisting"] is True
    assert (write.payload["written"], write.payload["owned"]) == (False, False)
    # Every field of the foreign key, related or not, is exactly as planted.
    assert _bag(engine) == {RUN: planted}
    result = assess_bag_persistence(write, None, channel="file")
    assert result.conclusion is CONTRADICTED and result.outcome_unknown is False


def test_the_finalizer_never_deletes_a_run_key_it_cannot_prove_it_owns(
    engine_factory,
):
    """A lost claim acknowledgement must not let the release adopt a foreign key."""
    engine = engine_factory()
    planted = _plant_foreign_run_key(engine)
    probes, _transport = _probes(engine)
    released = probes.release_run_bag()
    assert released.observed
    assert released.payload["had_run_bag"] is True
    assert released.payload["owned"] is False
    assert released.payload["deleted"] is False
    assert released.payload["present_after"] is True
    assert released.payload["observers_marked_inert"] == 0
    assert _bag(engine) == {RUN: planted}


def test_an_unowned_run_key_takes_no_contender_and_no_observer(engine_factory):
    """Ownership gates every write under the key, not only the claim."""
    engine = engine_factory()
    engine.seed_device(PC, "PC-PT")
    planted = _plant_foreign_run_key(engine)
    probes, _transport = _probes(engine)
    probes.queue_atomicity_contender("A")
    collect = probes.collect_atomicity()
    register = probes.register_observer_and_trigger(PC)
    assert not collect.observed
    assert collect.cause == "probe_error:run_bag_not_owned"
    assert register.observed and register.payload["registered1"] is False
    assert register.payload["register1_error"] == "run_bag_not_owned"
    snapshot = engine.snapshot()
    assert snapshot["registrations"] == []
    assert snapshot["devices"][0]["ports"] == []
    assert _bag(engine) == {RUN: planted}


def test_a_foreign_complete_atom_log_is_neither_evidence_nor_deleted(engine_factory):
    """Collection must prove ownership before reading or releasing a log."""
    engine = engine_factory()
    planted = _plant_foreign_run_key(engine)
    planted["atom"] = {
        "claim": "A",
        "seq": 4,
        "log": [
            {"c": "A", "s": "check", "n": 1},
            {"c": "A", "s": "claimed", "n": 2},
            {"c": "B", "s": "check", "n": 3},
            {"c": "B", "s": "refused", "n": 4},
        ],
    }
    engine.evaluate(
        f"this.__mcpE6Q[{json.dumps(RUN)}]={json.dumps(planted)};"
        "reportResult('planted');"
    )
    before = _bag(engine)
    probes, _transport = _probes(engine)

    collect = probes.collect_atomicity()

    assert not collect.observed
    assert collect.cause == "probe_error:run_bag_not_owned"
    assert _bag(engine) == before


def test_atomicity_collection_rechecks_ownership_after_a_successful_claim(
    engine_factory,
):
    """A prior claim does not survive replacement of its owner field."""
    engine = engine_factory()
    probes, _transport = _probes(engine)
    _claim(probes)
    for contender in ("A", "B"):
        assert probes.queue_atomicity_contender(contender).accepted
    # Evaluating this script first drains both contenders, then replaces the
    # ownership fact before the collection continuation begins.
    engine.evaluate(
        f"this.__mcpE6Q[{json.dumps(RUN)}].owner='replacement-owner';"
        "reportResult('replaced');"
    )
    before = _bag(engine)

    collect = probes.collect_atomicity()

    assert not collect.observed
    assert collect.cause == "probe_error:run_bag_not_owned"
    assert _bag(engine) == before


def test_absent_run_key_stops_every_mutating_continuation(engine_factory):
    """Absence is reported separately and creates no callbacks or bag state."""
    engine = engine_factory()
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    before = engine.snapshot()

    readings = (
        probes.collect_atomicity(),
        probes.read_observer_and_register_zero_event(PC),
        probes.release_observers_and_trigger(PC),
        probes.read_post_release_and_drop(),
    )

    assert all(not item.observed for item in readings)
    assert {item.cause for item in readings} == {"probe_error:run_bag_absent"}
    assert engine.snapshot() == before
    assert _bag(engine) == {}


@pytest.mark.parametrize("continuation", ["evidence", "release", "after"])
def test_foreign_observer_bookkeeping_stops_before_each_continuation_effect(
    engine_factory, continuation
):
    """Usable callbacks owned by another invocation are never adopted."""
    engine = engine_factory()
    engine.seed_device(PC, "PC-PT")
    owner, _transport = _probes(engine, nonce="1" * 32)
    _claim(owner)
    registered = owner.register_observer_and_trigger(PC)
    assert registered.observed and registered.payload["registered1"] is True
    if continuation in ("release", "after"):
        evidence = owner.read_observer_and_register_zero_event(PC)
        assert evidence.observed and evidence.payload["registered2"] is True
    if continuation == "after":
        release = owner.release_observers_and_trigger(PC)
        assert release.observed and release.payload["registered3"] is True

    before_bag = _bag(engine)
    before_state = engine.snapshot()
    foreign, _transport = _probes(engine, nonce="2" * 32)
    if continuation == "evidence":
        reading = foreign.read_observer_and_register_zero_event(PC)
    elif continuation == "release":
        reading = foreign.release_observers_and_trigger(PC)
    else:
        reading = foreign.read_post_release_and_drop()

    assert not reading.observed
    assert reading.cause == "probe_error:run_bag_not_owned"
    assert _bag(engine) == before_bag
    assert engine.snapshot() == before_state


def test_a_fresh_receiver_per_evaluation_is_an_observed_negative(engine_factory):
    """When `this` is not the engine global, the bag does not survive."""
    engine = engine_factory(receiver="fresh")
    probes, _transport = _probes(engine)
    write = probes.write_bag_sentinel()
    read = probes.read_and_release_bag_sentinel()
    result = assess_bag_persistence(write, read, channel="http")
    assert result.conclusion is NEGATIVE
    assert result.facts["run_key_written"] is True
    assert result.facts["receiver_is_global_at_write"] is False
    assert engine.snapshot()["run_bags"] == {}


# -- ATOM-1 --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("queue", "channel", "conclusion", "scope"),
    [
        ("fifo", "file", SUPPORTED, "separate_evaluations"),
        ("coalesce", "http", INCONCLUSIVE, "unknown"),
    ],
)
def test_queued_contenders_keep_the_log_without_overstating_evaluation_scope(
    engine_factory, queue, channel, conclusion, scope
):
    """The ordered log survives even when batching leaves separation unknown."""
    engine = engine_factory(queue=queue)
    probes, _transport = _probes(engine)
    _claim(probes)
    receipts = [probes.queue_atomicity_contender(name) for name in ("A", "B")]
    collect = probes.collect_atomicity()
    result = assess_atomicity(receipts, collect, channel=channel)
    assert result.conclusion is conclusion
    assert result.facts["evaluation_scope"] == scope
    assert result.facts["log"] == [
        {"c": "A", "s": "check", "n": 1},
        {"c": "A", "s": "claimed", "n": 2},
        {"c": "B", "s": "check", "n": 3},
        {"c": "B", "s": "refused", "n": 4},
    ]
    assert engine.snapshot()["run_bags"] == {RUN: ["owner", "sentinel"]}


def test_a_lost_claim_write_shows_up_as_a_double_claim(engine_factory):
    """A stub that forgets the claim between contenders yields a counterexample."""
    engine = engine_factory(reset_claim_between_queued=True)
    probes, _transport = _probes(engine)
    _claim(probes)
    receipts = [probes.queue_atomicity_contender(name) for name in ("A", "B")]
    result = assess_atomicity(receipts, probes.collect_atomicity(), channel="file")
    assert result.conclusion is CONTRADICTED and result.causes == ["double_claim"]


def test_contenders_that_never_run_are_an_unknown_outcome(engine_factory):
    """Absent execution is not evidence; the record is left for finalization."""
    engine = engine_factory(queue="drop")
    probes, _transport = _probes(engine)
    _claim(probes)
    receipts = [probes.queue_atomicity_contender(name) for name in ("A", "B")]
    result = assess_atomicity(receipts, probes.collect_atomicity(), channel="http")
    assert result.conclusion is INCONCLUSIVE and result.outcome_unknown


# -- M-UNREG-1 / M-UNREG-2 -------------------------------------------------------


def test_identity_release_detaches_and_the_inert_observer_stays_bounded(
    engine_factory,
):
    """Against a stub whose unregister works, both measurements are supported."""
    engine = engine_factory()
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    _claim(probes)
    first, second = _unregister(probes)
    assert first.conclusion is SUPPORTED and second.conclusion is SUPPORTED
    snapshot = engine.snapshot()
    assert [call["uuid"] for call in snapshot["unregister_calls"]] == ["{stub-1}"] * 3
    assert [item["active"] for item in snapshot["registrations"]] == [False] * 3
    assert snapshot["devices"][0]["ports"][0]["ip"] == "192.0.2.202"
    assert snapshot["run_bags"] == {RUN: ["owner", "sentinel"]}


def test_an_unregister_that_does_not_detach_is_a_contradiction(engine_factory):
    """The stub keeps cb1 attached, so the control event reaches it again."""
    engine = engine_factory(unregister_effective=False)
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    _claim(probes)
    first, _second = _unregister(probes)
    assert first.conclusion is CONTRADICTED
    assert all(item["active"] for item in engine.snapshot()["registrations"])


def test_without_the_extension_call_no_release_is_attempted(engine_factory):
    """No `_ScriptModule`: the release is unavailable, never faked."""
    engine = engine_factory(unregister_available=False)
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    _claim(probes)
    first, second = _unregister(probes)
    assert first.conclusion is INCONCLUSIVE
    assert "release_not_attempted:unregister_unavailable" in first.causes
    assert second.conclusion is SUPPORTED
    assert engine.snapshot()["unregister_calls"] == []


def test_no_event_means_no_identity_and_no_invented_uuid(engine_factory):
    """Without a delivered event nothing is unregistered and nothing is claimed."""
    engine = engine_factory(deliver_events="never")
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    _claim(probes)
    first, second = _unregister(probes)
    assert first.conclusion is INCONCLUSIVE
    assert "no_event_observed_after_trigger" in first.causes
    assert second.conclusion is INCONCLUSIVE
    assert engine.snapshot()["unregister_calls"] == []


def test_synchronous_delivery_is_still_attributed_after_the_trigger(engine_factory):
    """An event delivered inside enterCommand still carries a later sequence."""
    engine = engine_factory(deliver_events="sync")
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    _claim(probes)
    first, _second = _unregister(probes)
    assert first.facts["callback_evidence"]["delivered"] is True


def test_a_refused_registration_is_not_an_observer(engine_factory):
    """A throwing registerEvent is reported, and nothing is triggered."""
    engine = engine_factory(register_throws=True)
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    _claim(probes)
    register = probes.register_observer_and_trigger(PC)
    assert register.observed and register.payload["registered1"] is False
    assert register.payload["register1_error"] == "registration refused"
    assert engine.snapshot()["devices"][0]["ports"] == []


def test_a_failed_trigger_is_a_cause_never_a_negative(engine_factory):
    """A refused setter produces no event; the reading says why."""
    engine = engine_factory(readdress_throws=True)
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    _claim(probes)
    first, second = _unregister(probes)
    assert first.conclusion is INCONCLUSIVE and second.conclusion is INCONCLUSIVE
    assert "trigger_x_failed:setter refused" in first.causes
    assert "trigger_y_failed:setter refused" in second.causes
    assert engine.snapshot()["unregister_calls"] == []


def test_the_observer_source_is_the_owned_port_not_a_terminal(engine_factory):
    """No probe dispatches a terminal command; the event is the port's."""
    engine = engine_factory()
    engine.seed_device(PC, "PC-PT")
    probes, transport = _probes(engine)
    _claim(probes)
    first, _second = _unregister(probes)
    source = first.facts["callback_evidence"]["source"]
    assert (source["className"], source["eventName"]) == ("HostPort", "ipChanged")
    assert all("enterCommand" not in script for _kind, script in transport.calls)


def test_q0_probes_never_write_production_globals(engine_factory):
    """Claims, inert counters and client bags of the product stay untouched."""
    engine = engine_factory()
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    probes.write_bag_sentinel()
    probes.read_and_release_bag_sentinel()
    probes.queue_atomicity_contender("A")
    probes.queue_atomicity_contender("B")
    probes.collect_atomicity()
    _unregister(probes)
    assert engine.snapshot()["production_globals"] == []


def test_the_finalizer_removes_only_its_own_run_key(engine_factory):
    """Another run's bag entry survives this run's release."""
    engine = engine_factory()
    ours, _transport = _probes(engine, run="run-ours")
    theirs, _other = _probes(engine, run="run-theirs")
    ours.write_bag_sentinel()
    theirs.write_bag_sentinel()
    released = ours.release_run_bag()
    assert released.observed and released.payload["present_after"] is False
    assert (released.payload["owned"], released.payload["deleted"]) == (True, True)
    assert list(engine.snapshot()["run_bags"]) == ["run-theirs"]


# -- Q1 private probes ---------------------------------------------------------


def _index(engine: NodeEngine, handle: str = "HttpServer") -> str:
    """Read the index page straight out of the stub, bypassing the probes."""
    return engine.evaluate(
        f"reportResult(String(ipc.network().getDevice({json.dumps(SERVER)})"
        f".getProcess({json.dumps(handle)}).getPage('index.html')));"
    )


def _page_procedure(probes):
    """Run M-HTTPS-1 exactly as the coordinator admits it, step by step.

    Each step runs only when the previous one was interpreted, so a skipped
    step is reported as `None` here the same way the coordinator reports it.
    """
    texts = probes.page_marker_texts()
    write_http = probes.write_index_marker(SERVER, "http")
    read_http = write_https = read_https = None
    if page_write_established(write_http):
        read_http = probes.read_index_cells(SERVER)
    if page_read_admits_second_write(read_http, texts["http_marker"]):
        write_https = probes.write_index_marker(SERVER, "https")
    if page_write_established(write_https):
        read_https = probes.read_index_cells(SERVER)
    return (
        assess_page_tables(
            write_http,
            read_http,
            write_https,
            read_https,
            http_marker=texts["http_marker"],
            https_marker=texts["https_marker"],
        ),
        (write_http, read_http, write_https, read_https),
    )


def test_the_stub_only_updates_pages_that_exist(engine_factory):
    """The measured semantics: `setPageContents` never creates a page."""
    engine = engine_factory()
    engine.seed_device(SERVER, "Server-PT")
    reported = engine.evaluate(
        f"var p=ipc.network().getDevice({json.dumps(SERVER)}).getProcess('HttpServer');"
        "var out={};try{p.setPageContents('mcpq-new.html','x');out.created=true;}"
        "catch(e){out.error=String(e.message);}"
        "p.setPageContents('index.html','updated');out.index=String(p.getPage('index.html'));"
        "reportResult(JSON.stringify(out));"
    )
    assert json.loads(reported) == {
        "error": "File not exist: mcpq-new.html",
        "index": "updated",
    }


@pytest.mark.parametrize(
    ("config", "model", "identity"),
    [
        ({}, "separate", False),
        ({"page_tables": "shared"}, "shared", False),
        ({"https_identity": "same"}, "shared", True),
    ],
)
def test_the_repaired_procedure_decides_the_table_model(
    engine_factory, config, model, identity
):
    """Q1R-1/2: the table layout is recovered by writing the existing page only."""
    engine = engine_factory(**config)
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)

    result, _readings = _page_procedure(probes)

    assert result.conclusion is SUPPORTED, result.causes
    assert result.facts["page_table_model"] == model
    assert result.facts["object_identity_equal"] is identity
    pages = engine.snapshot()["servers"][SERVER]
    assert (pages["http_pages"], pages["https_pages"]) == (
        ["index.html"],
        ["index.html"],
    )


def test_an_unreadable_baseline_writes_nothing(engine_factory):
    """A failed read is not a separate table, and no mutation follows it."""
    engine = engine_factory(getpage_throws_https=["index"])
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)
    before = _index(engine)

    write = probes.write_index_marker(SERVER, "http")

    assert write.payload["written"] is False
    assert _index(engine) == before
    result = assess_page_tables(
        write,
        None,
        None,
        None,
        http_marker=probes.page_marker_texts()["http_marker"],
        https_marker=probes.page_marker_texts()["https_marker"],
    )
    assert result.conclusion is INCONCLUSIVE
    assert "page_table_model" not in result.facts
    assert any(item.startswith("baseline_unreadable:https:") for item in result.causes)
    # No setter ran, so nothing is attributed to an effect of this step.
    assert result.facts["page_effect"] == "not_attempted"
    assert result.outcome_unknown is False


def test_a_refused_write_to_an_existing_page_is_inconclusive(engine_factory):
    """An exception is a cause, never an observed absence."""
    engine = engine_factory(setpage_throws_http=["index"])
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)

    result, (write_http, *rest) = _page_procedure(probes)

    assert write_http.payload["written"] is False
    assert "page write refused" in write_http.payload["write_error"]
    assert result.conclusion is INCONCLUSIVE
    assert result.causes[0] == "marker_write_failed:http"
    # The setter was reached, so the effect is unresolved and no further step
    # of the procedure may run.
    assert rest == [None, None, None]
    assert result.facts["page_effect"] == "unresolved"
    assert result.outcome_unknown is True


def test_a_setter_that_changed_the_page_and_threw_is_unresolved(engine_factory):
    """Q1R-7: the page moved while the probe reported `written=false`."""
    engine = engine_factory(setpage_throws_after_http=["index"])
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)
    before = _index(engine)

    result, readings = _page_procedure(probes)

    write_http = readings[0]
    assert write_http.payload["written"] is False
    assert "after the change" in write_http.payload["write_error"]
    # The stub's own state, not the reported flag: the page really did change.
    assert _index(engine) != before
    assert probes.page_marker_texts()["http_marker"] in _index(engine)
    assert list(readings[1:]) == [None, None, None]
    assert result.conclusion is INCONCLUSIVE
    assert result.facts["page_effect"] == "unresolved"
    assert result.outcome_unknown is True


def test_one_unreadable_cell_after_a_write_is_not_an_asymmetry(engine_factory):
    """A cell that stops reading between steps decides nothing."""
    engine = engine_factory(page_tables="shared")
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)
    texts = probes.page_marker_texts()
    write_http = probes.write_index_marker(SERVER, "http")
    engine.configure(getpage_throws_https=["index"])
    read_http = probes.read_index_cells(SERVER)

    result = assess_page_tables(
        write_http,
        read_http,
        None,
        None,
        http_marker=texts["http_marker"],
        https_marker=texts["https_marker"],
    )

    assert result.conclusion is INCONCLUSIVE
    assert any(
        item.startswith("read_after_http_write_unreadable:https:")
        for item in result.causes
    )
    assert "page_table_model" not in result.facts


def test_the_marker_page_and_the_toggles_are_read_back_in_their_evaluation(
    engine_factory,
):
    """Both handles serve the marker, then HTTP off, then HTTPS off."""
    engine = engine_factory()
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)

    prepared = probes.prepare_marker_page(SERVER, "MARK-1")

    assert (prepared.payload["http_enabled"], prepared.payload["https_enabled"]) == (
        True,
        True,
    )
    assert prepared.payload["index_written"] == {"http": True, "https": True}
    assert all(
        prepared.payload["readback"][name]["contains_marker"] is True
        for name in ("http", "https")
    )
    http_off = probes.disable_http(SERVER)
    assert (http_off.payload["http_enabled"], http_off.payload["https_enabled"]) == (
        False,
        True,
    )
    disabled = probes.disable_https(SERVER)
    assert disabled.payload["https_enabled"] is False
    state = engine.snapshot()["servers"][SERVER]
    assert (state["http_enabled"], state["https_enabled"]) == (False, False)
    assert state["http_pages"] == ["index.html"]


def test_readiness_reads_documented_port_state_only(engine_factory):
    """Q1R-3: port and link state where a documented reader exists."""
    engine = engine_factory(protocol_up=False)
    engine.seed_device(SERVER, "Server-PT")
    engine.seed_device("__MCP_E6Q_SW", "2960-24TT")
    probes, _transport = _probes(engine)

    reading = probes.read_listener_readiness(
        SERVER,
        [(SERVER, "FastEthernet0"), ("__MCP_E6Q_SW", "FastEthernet0/1"), ("X", "Y")],
    )

    assert reading.observed
    ports = reading.payload["ports"]
    server = ports[f"{SERVER}/FastEthernet0"]
    assert server["found"] is True and server["linked"] is False
    assert server["port_up"] is False and server["ip"] == ""
    switch = ports["__MCP_E6Q_SW/FastEthernet0/1"]
    assert switch["found"] is True and switch["ip"] is None
    assert ports["X/Y"]["found"] is False
    assert reading.payload["listeners"]["http_enabled"] is True


def test_client_resolver_reader_reports_raw_values(engine_factory):
    """The configured and unset values come back as the stub stores them."""
    engine = engine_factory(unset_dns="0.0.0.0")
    engine.seed_device("PC-A", "PC-PT")
    engine.seed_device("PC-B", "PC-PT")
    engine.evaluate(
        'configurePcIp("PC-A",false,"192.0.2.11","255.255.255.0","",'
        '"192.0.2.10","FastEthernet0");'
    )
    probes, _transport = _probes(engine)
    reading = probes.read_client_resolvers(("PC-A", "PC-B", "PC-missing"))
    clients = reading.payload["clients"]
    assert clients["PC-A"]["value"] == "192.0.2.10"
    assert clients["PC-B"]["value"] == "0.0.0.0"
    assert clients["PC-missing"]["found"] is False


# -- the shared build reader -----------------------------------------------------


def test_the_registry_and_the_runner_share_one_reader():
    """The move kept one script object; nothing was copied."""
    assert (
        tool_registry.SERVICE_ENVIRONMENT_JS
        is service_environment.SERVICE_ENVIRONMENT_JS
    )
    assert tool_registry.parse_service_environment is (
        service_environment.parse_service_environment
    )
    assert "_SERVICE_ENVIRONMENT_JS" not in vars(tool_registry)


def test_the_runner_reads_the_application_version_never_the_saved_file(
    engine_factory,
):
    """Application and saved-file versions differ; only the former is read."""
    engine = engine_factory(version="9.0.1.9999", saved_version="9.0.1.0858")
    transport = NodeEngineTransport(engine)
    reading = ServiceEnvironmentReader(transport.send_and_wait).read()
    assert (reading.available, reading.version) == (True, "9.0.1.9999")
    assert (reading.reader_id, reading.reader_sha256) == (READER_ID, READER_SHA256)
    assert transport.calls == [("dispatch", SERVICE_ENVIRONMENT_JS)]
    assert json.loads(reading.excerpt)["backend_version"] == "9.0.1.9999"


@pytest.mark.parametrize(
    ("config", "reason"),
    [
        ({"version_getter": False}, "not_found:application_version_unavailable"),
        ({"active_file": False}, "not_found:active_file_unavailable"),
        ({"version": "9.0.1"}, "version_not_exact_build"),
    ],
)
def test_an_unavailable_build_is_never_recovered(engine_factory, config, reason):
    """Missing getter, missing file or a partial build stay unavailable."""
    engine = engine_factory(**config)
    reading = ServiceEnvironmentReader(NodeEngineTransport(engine).send_and_wait).read()
    assert (reading.available, reading.version, reading.reason) == (False, "", reason)


# -- amendment 01: typed readiness and the echoed baseline subject --------------


def test_port_readiness_reports_actual_booleans_and_their_absence(engine_factory):
    """F3: `!!` is gone, so a non-boolean reader is not an observed `false`."""
    engine = engine_factory(port_up_return="number")
    engine.seed_device(SERVER, "Server-PT")
    engine.seed_device("__MCP_E6Q_SW", "2960-24TT")
    probes, _transport = _probes(engine)

    reading = probes.read_port_readiness(
        [(SERVER, "FastEthernet0"), ("__MCP_E6Q_SW", "FastEthernet0/1"), ("X", "Y")]
    )

    assert reading.observed and "listeners" not in reading.payload
    server = reading.payload["ports"][f"{SERVER}/FastEthernet0"]
    assert (server["device"], server["interface"]) == (SERVER, "FastEthernet0")
    assert server["found"] is True
    # `isPortUp` answered with a number, so there is no boolean to report.
    assert server["port_up"] is None and server["port_up_type"] == "number"
    assert server["protocol_up"] is False and server["protocol_up_type"] == "boolean"
    assert server["linked"] is False and server["link_type"] == "absent"
    missing = reading.payload["ports"]["X/Y"]
    assert missing["found"] is False and missing["port_up_type"] == "absent"


def test_a_linked_fixture_reports_every_readiness_boolean(engine_factory):
    """The positive control: two linked ports answer with actual booleans."""
    engine = engine_factory()
    engine.seed_device(SERVER, "Server-PT")
    engine.seed_device("__MCP_E6Q_SW", "2960-24TT")
    probes, _transport = _probes(engine)
    engine.evaluate(
        f"lwAddLink({json.dumps(SERVER)},'FastEthernet0','__MCP_E6Q_SW',"
        "'FastEthernet0/1','Copper Straight-Through');reportResult('linked');"
    )

    reading = probes.read_port_readiness(
        [(SERVER, "FastEthernet0"), ("__MCP_E6Q_SW", "FastEthernet0/1")]
    )

    for row in reading.payload["ports"].values():
        assert (row["found"], row["linked"], row["port_up"], row["protocol_up"]) == (
            True,
            True,
            True,
            True,
        )
        assert row["link_type"] == "object" and row["error"] == ""


def test_the_dhcp_baseline_echoes_the_subject_it_was_asked_about(engine_factory):
    """F1: the admission rule compares the answer against the device it named."""
    engine = engine_factory(dhcp_default_pool="native")
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)

    reading = probes.read_dhcp_server_baseline(SERVER, "FastEthernet0")

    assert reading.observed
    assert reading.payload["device"] == SERVER
    assert reading.payload["enabled"] is False
    assert reading.payload["pools"] == [
        {
            "name": "serverPool",
            "network": "0.0.0.0",
            "mask": "0.0.0.0",
            "gateway": "0.0.0.0",
            "dns": "0.0.0.0",
            "start": "0.0.0.0",
            "end": "0.0.2.0",
            "max": 512,
        }
    ]
    missing = probes.read_dhcp_server_baseline("__MCP_E6Q_ABSENT", "FastEthernet0")
    assert missing.payload["device"] == "__MCP_E6Q_ABSENT"
    assert missing.payload["found"] is False


def test_native_pool_probe_brackets_a_documented_setter_with_physical_reads(
    engine_factory,
):
    """A returned setter call alone cannot establish an effective pool change."""
    engine = engine_factory(dhcp_default_pool="native")
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)
    assert hasattr(probes, "probe_native_pool_start")
    before = probes.read_dhcp_server_baseline(SERVER, "FastEthernet0")
    changed = probes.probe_native_pool_start(SERVER, "FastEthernet0", "192.0.2.100")
    after = probes.read_dhcp_server_baseline(SERVER, "FastEthernet0")
    assert changed.observed
    assert changed.payload == {
        "device": SERVER,
        "interface": "FastEthernet0",
        "pool": "serverPool",
        "found": True,
        "attempted": True,
        "call_error": "",
        "pre_start": "0.0.0.0",
        "post_start": "192.0.2.100",
    }
    assert before.payload["pools"][0]["start"] == "0.0.0.0"
    assert after.payload["pools"][0]["start"] == "192.0.2.100"
