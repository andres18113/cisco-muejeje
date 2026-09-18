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
    assert engine.snapshot()["run_bags"] == {RUN: ["sentinel"]}
    read = probes.read_and_release_bag_sentinel()
    assert engine.snapshot()["run_bags"] == {RUN: []}
    result = assess_bag_persistence(write, read, channel="file")
    assert result.conclusion is SUPPORTED
    assert result.facts["receiver_is_global_at_read"] is True


def test_a_fresh_receiver_per_evaluation_is_an_observed_negative(engine_factory):
    """When `this` is not the engine global, the bag does not survive."""
    engine = engine_factory(receiver="fresh")
    probes, _transport = _probes(engine)
    write = probes.write_bag_sentinel()
    read = probes.read_and_release_bag_sentinel()
    result = assess_bag_persistence(write, read, channel="http")
    assert result.conclusion is NEGATIVE
    assert result.facts["receiver_is_global_at_write"] is False
    assert engine.snapshot()["run_bags"] == {}


# -- ATOM-1 --------------------------------------------------------------------


@pytest.mark.parametrize(("queue", "channel"), [("fifo", "file"), ("coalesce", "http")])
def test_queued_contenders_leave_one_ordered_claim(engine_factory, queue, channel):
    """Sequential or batched evaluations produce one claim and no interleaving."""
    engine = engine_factory(queue=queue)
    probes, _transport = _probes(engine)
    receipts = [probes.queue_atomicity_contender(name) for name in ("A", "B")]
    collect = probes.collect_atomicity()
    result = assess_atomicity(receipts, collect, channel=channel)
    assert result.conclusion is SUPPORTED
    assert engine.snapshot()["run_bags"] == {RUN: []}


def test_a_lost_claim_write_shows_up_as_a_double_claim(engine_factory):
    """A stub that forgets the claim between contenders yields a counterexample."""
    engine = engine_factory(reset_claim_between_queued=True)
    probes, _transport = _probes(engine)
    receipts = [probes.queue_atomicity_contender(name) for name in ("A", "B")]
    result = assess_atomicity(receipts, probes.collect_atomicity(), channel="file")
    assert result.conclusion is CONTRADICTED and result.causes == ["double_claim"]


def test_contenders_that_never_run_are_an_unknown_outcome(engine_factory):
    """Absent execution is not evidence; the record is left for finalization."""
    engine = engine_factory(queue="drop")
    probes, _transport = _probes(engine)
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
    first, second = _unregister(probes)
    assert first.conclusion is SUPPORTED and second.conclusion is SUPPORTED
    snapshot = engine.snapshot()
    assert [call["uuid"] for call in snapshot["unregister_calls"]] == ["{stub-1}"] * 3
    assert [item["active"] for item in snapshot["registrations"]] == [False] * 3
    assert snapshot["devices"][0]["ports"][0]["ip"] == "192.0.2.202"
    assert snapshot["run_bags"] == {RUN: []}


def test_an_unregister_that_does_not_detach_is_a_contradiction(engine_factory):
    """The stub keeps cb1 attached, so the control event reaches it again."""
    engine = engine_factory(unregister_effective=False)
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    first, _second = _unregister(probes)
    assert first.conclusion is CONTRADICTED
    assert all(item["active"] for item in engine.snapshot()["registrations"])


def test_without_the_extension_call_no_release_is_attempted(engine_factory):
    """No `_ScriptModule`: the release is unavailable, never faked."""
    engine = engine_factory(unregister_available=False)
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
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
    first, _second = _unregister(probes)
    assert first.facts["callback_evidence"]["delivered"] is True


def test_a_refused_registration_is_not_an_observer(engine_factory):
    """A throwing registerEvent is reported, and nothing is triggered."""
    engine = engine_factory(register_throws=True)
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
    register = probes.register_observer_and_trigger(PC)
    assert register.observed and register.payload["registered1"] is False
    assert register.payload["register1_error"] == "registration refused"
    assert engine.snapshot()["devices"][0]["ports"] == []


def test_a_failed_trigger_is_a_cause_never_a_negative(engine_factory):
    """A refused setter produces no event; the reading says why."""
    engine = engine_factory(readdress_throws=True)
    engine.seed_device(PC, "PC-PT")
    probes, _transport = _probes(engine)
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
    assert list(engine.snapshot()["run_bags"]) == ["run-theirs"]


# -- Q1 private probes ---------------------------------------------------------


@pytest.mark.parametrize(
    ("config", "model", "identity"),
    [
        ({}, "separate", False),
        ({"page_tables": "shared"}, "shared", False),
        ({"https_identity": "same"}, "shared", True),
    ],
)
def test_cross_reads_decide_the_page_table_model(
    engine_factory, config, model, identity
):
    """The stub's table layout is recovered from reads, not from references."""
    engine = engine_factory(**config)
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)
    write = probes.write_page_markers(SERVER)
    result = assess_page_tables(write, probes.cross_read_page_markers(SERVER))
    assert result.conclusion is SUPPORTED
    assert result.facts["page_table_model"] == model
    assert result.facts["object_identity_equal"] is identity
    pages = engine.snapshot()["servers"][SERVER]
    names = probes.page_marker_names()
    assert names["http_page"] in pages["http_pages"]


def test_listener_toggles_are_read_back_in_the_same_evaluation(engine_factory):
    """HTTP off with HTTPS on, then HTTPS off; the stub state agrees."""
    engine = engine_factory()
    engine.seed_device(SERVER, "Server-PT")
    probes, _transport = _probes(engine)
    prepared = probes.prepare_https_only(SERVER, "MARK-1")
    assert prepared.payload["http_enabled"] is False
    assert prepared.payload["https_enabled"] is True
    assert prepared.payload["index_written"] == {"http": True, "https": True}
    disabled = probes.disable_https(SERVER)
    assert disabled.payload["https_enabled"] is False
    state = engine.snapshot()["servers"][SERVER]
    assert (state["http_enabled"], state["https_enabled"]) == (False, False)


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
