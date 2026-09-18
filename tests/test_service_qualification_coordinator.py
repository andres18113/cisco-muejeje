"""The qualification coordinator over controlled boundaries (integration level).

The coordinator runs with the production runtimes, probes, build reader and
record store. Only the external boundaries are replaced: the channel is the
Node stub engine, the clock is fake, and isolation and repository identity are
declared by the simulation. Every expectation about Packet Tracer state comes
from the stub's snapshot; every expectation about call order comes from the
channel's own call log.

The nominal Q0 call sequence is deterministic, which lets a test aim a hook or
a lost response at one exact call:
1 build, 2 workspace, 3-4 M-ENG-1, 5-6 queued contenders, 7 collect,
8-9 PC create (pre-read, PTBuilder), 10 fixture identity, 11-14 M-UNREG,
15 run-bag release, 16-17 PC removal, 18-19 restoration reads.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest
from service_qualification_engine import (
    SIM_BUILD,
    SIM_SHA,
    FakeClock,
    NodeEngine,
    NodeEngineTransport,
    RecordingStore,
    simulated_boundaries,
)

from packet_tracer_mcp.adapters.cli.service_qualification import fixture_plans
from packet_tracer_mcp.application.use_cases import (
    qualify_server_services as coordinator,
)
from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
    apply_enterprise_services,
)
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    IsolationObservation,
    qualify_server_services,
)
from packet_tracer_mcp.domain.enterprise.models.execution import DirtyState
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    STAGE_DEFINITIONS,
    MeasurementConclusion,
    MeasurementStatus,
    QualificationAuthorization,
    QualificationOutcome,
    QualificationRecord,
    QualificationRequest,
    QualificationStage,
    RefusalKind,
    RefusalSubject,
    RepositoryIdentity,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    capability_snapshot_hash,
    packet_tracer_service_capabilities,
)
from packet_tracer_mcp.infrastructure.execution.service_environment import (
    ServiceEnvironmentReader,
)

Q0 = STAGE_DEFINITIONS[QualificationStage.Q0]
Q1 = STAGE_DEFINITIONS[QualificationStage.Q1]
PC = "__MCP_E6Q_PC1"
CAPABILITIES = frozenset(Q0.experimental_capabilities)


def _request(channel: str = "file") -> QualificationRequest:
    return QualificationRequest(
        execute=True,
        stage="Q0",
        expected_head=SIM_SHA,
        targets=Q0.fixture_names,
        channel=channel,
        packet_tracer_build=SIM_BUILD,
        authorization=QualificationAuthorization(
            authorization_id="TD-Q0-sim",
            stage="Q0",
            sha=SIM_SHA,
            targets=Q0.fixture_names,
            channel=channel,
            build=SIM_BUILD,
            max_operations=20,
            max_seconds=300,
        ),
    )


class _Harness:
    """One stub engine, one channel, the simulated boundaries and a run."""

    def __init__(self, directory: Path, engine_config=None, **transport_options):
        """Start the engine and bind the simulated boundaries to it."""
        self.directory = directory
        self.engine = NodeEngine(directory, **(engine_config or {}))
        self.transport = NodeEngineTransport(self.engine, **transport_options)
        self.opened: list[str] = []

    def boundaries(self, **overrides):
        """Return simulated boundaries that record every channel opening."""
        from packet_tracer_mcp.application.ports.service_qualification import (
            OpenedTransport,
        )

        def open_transport(channel: str):
            self.opened.append(channel)
            return OpenedTransport(channel, self.transport, True, "stub_engine")

        values = {"open_transport": open_transport}
        values.update(overrides)
        return simulated_boundaries(self.directory, self.transport, **values)

    def run(self, request=None, *, capabilities=CAPABILITIES, **overrides):
        """Run one invocation and return its result."""
        return qualify_server_services(
            request or _request(),
            self.boundaries(**overrides),
            experimental_capabilities=capabilities,
        )

    def durable(self) -> QualificationRecord:
        """Return the record exactly as the store wrote it last."""
        (path,) = list((self.directory / "records").rglob("*.json"))
        return QualificationRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def scripts(self, needle: str) -> list[str]:
        """Return every dispatched script that contains `needle`."""
        return [script for _kind, script in self.transport.calls if needle in script]


@pytest.fixture
def harness(tmp_path):
    """Yield a harness factory and stop every engine afterwards."""
    started: list[_Harness] = []

    def make(engine_config=None, **transport_options) -> _Harness:
        directory = tmp_path / f"run{len(started)}"
        directory.mkdir()
        item = _Harness(directory, engine_config, **transport_options)
        started.append(item)
        return item

    yield make
    for item in started:
        item.engine.close()


def _status(record: QualificationRecord) -> dict[str, tuple[str, str]]:
    return {
        item.experiment_id: (item.status.value, item.conclusion.value)
        for item in record.measurements
    }


# -- local admission: nothing is contacted ---------------------------------------


def test_isolation_refusal_happens_before_any_record_or_channel(harness):
    """A process that is not the live one never opens a channel or a record."""
    h = harness()
    result = h.run(
        isolation=lambda: IsolationObservation(False, "TEST_PROCESS", "pytest")
    )
    assert result.outcome is QualificationOutcome.REFUSED
    assert result.refusals[0].subject is RefusalSubject.PROCESS_ISOLATION
    assert "TEST_PROCESS" in result.refusals[0].detail
    assert h.opened == [] and h.transport.calls == []
    assert not (h.directory / "records").exists()


def test_a_stale_checkout_refuses_before_any_channel(harness):
    """Observed HEAD differs from the authorized SHA: nothing is contacted."""
    h = harness()
    result = h.run(
        repository=lambda: RepositoryIdentity(
            head="e" * 40, tree="f" * 40, clean=True, upstream_head="e" * 40
        )
    )
    assert (RefusalKind.MISMATCH, RefusalSubject.REPOSITORY_HEAD) in {
        (item.kind, item.subject) for item in result.refusals
    }
    assert h.opened == [] and h.transport.calls == []


def test_an_unwritable_record_refuses_before_any_channel(harness):
    """No write-ahead record, no contact."""
    h = harness()
    store = RecordingStore(h.directory / "records", fail_at={"begin"})
    result = h.run(record_store=store)
    assert result.refusals[0].subject is RefusalSubject.RECORD
    assert h.opened == [] and h.transport.calls == []


# -- contact before effects ------------------------------------------------------


def test_a_build_mismatch_refuses_after_one_read_and_no_effect(harness):
    """The executable is read first; a different build stops everything."""
    h = harness({"version": "9.0.1.9999"})
    result = h.run()
    assert result.outcome is QualificationOutcome.REFUSED
    assert (RefusalKind.MISMATCH, RefusalSubject.EXECUTABLE_BUILD) in {
        (item.kind, item.subject) for item in result.refusals
    }
    assert len(h.transport.calls) == 1
    snapshot = h.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["run_bags"] == {}
    durable = h.durable()
    assert durable.outcome is QualificationOutcome.REFUSED
    assert durable.environment.observed_build == "9.0.1.9999"
    assert durable.environment.build_reader_id == "AppWindow.getVersion"


def test_an_unobservable_build_is_unobservable_not_assumed(harness):
    """A missing application getter is never replaced by the saved-file version."""
    h = harness({"version_getter": False})
    result = h.run()
    assert (RefusalKind.UNOBSERVABLE, RefusalSubject.EXECUTABLE_BUILD) in {
        (item.kind, item.subject) for item in result.refusals
    }
    assert h.durable().environment.observed_build == ""


def test_a_foreign_workspace_refuses_before_creation_and_is_untouched(harness):
    """An operator's device is never cleared to satisfy admission."""
    h = harness()
    h.engine.seed_device("Operator-PC", "PC-PT")
    result = h.run()
    assert (RefusalKind.NOT_PERMITTED, RefusalSubject.WORKSPACE) in {
        (item.kind, item.subject) for item in result.refusals
    }
    assert len(h.transport.calls) == 2
    assert [item["name"] for item in h.engine.snapshot()["devices"]] == ["Operator-PC"]


def test_an_engine_managed_object_is_reported_and_retained(harness):
    """A zero-port power distribution device is excluded explicitly, not silently."""
    h = harness()
    h.engine.seed_device("Power Distribution Device0", "Power Distribution Device")
    result = h.run()
    assert result.outcome is QualificationOutcome.COMPLETED
    record = result.record
    assert any(
        item.startswith("engine_managed_objects_in_baseline:")
        for item in record.limitations
    )
    assert record.restoration_proven is True
    assert [item["name"] for item in h.engine.snapshot()["devices"]] == [
        "Power Distribution Device0"
    ]


# -- the nominal run -------------------------------------------------------------


def test_nominal_q0_uses_one_channel_and_exactly_the_planned_operations(harness):
    """Every call goes through the one transport; the count is the planned 19."""
    h = harness()
    result = h.run()
    record = result.record
    assert result.outcome is QualificationOutcome.COMPLETED
    assert h.opened == ["file"]
    assert record.budget.used_operations == len(h.transport.calls) == 19
    assert record.budget.used_operations == Q0.planned_minimum_operations
    assert h.transport.calls[0][1].startswith("try{var app=ipc.appWindow()")
    purposes = [item.purpose for item in record.operations]
    assert purposes[:2] == ["read:executable_build", "read:workspace_baseline"]
    assert purposes[-2:] == ["read:restoration:1", "read:restoration:2"]
    assert _status(record) == {
        "M-ENG-1": ("ran", "supported_in_sample"),
        "ATOM-1": ("ran", "supported_in_sample"),
        "M-UNREG-1": ("ran", "supported_in_sample"),
        "M-UNREG-2": ("ran", "supported_in_sample"),
        "M-HTTP-1": ("omitted", "not_evaluated"),
    }
    assert record.execution_mode.value == "offline_simulation"
    assert record.source.executed_sha == SIM_SHA
    snapshot = h.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["run_bags"] == {}


def test_observer_residue_keeps_the_state_unknown_despite_an_empty_workspace(harness):
    """Two empty reads are necessary, not sufficient."""
    h = harness()
    record = h.run().record
    assert record.restoration_proven is True
    assert {"observer:cb2", "observer:cb3"} <= set(record.engine_residue)
    assert record.dirty_state is DirtyState.UNKNOWN


def test_write_ahead_steps_precede_their_work_and_survive_reload(harness):
    """The durable record carries every boundary in order."""
    h = harness()
    h.run()
    steps = [item.step for item in h.durable().transitions]
    assert steps == [
        "admitted",
        "experiment:ENG:started",
        "experiment:ENG:concluded",
        "experiment:ATOM:started",
        "experiment:ATOM:concluded",
        "fixtures:started",
        "fixtures:ready",
        "experiment:UNREG:started",
        "experiment:UNREG:concluded",
        "finalization:started",
        "finalization:completed",
    ]
    assert h.durable().completed_at is not None


def test_no_claim_reset_and_no_production_global_is_ever_written(harness):
    """The runner owns only its run bag; the product claim map is never touched."""
    h = harness()
    h.run()
    assert h.engine.snapshot()["production_globals"] == []
    assert h.scripts("__mcpE6Claims") == [] and h.scripts("__mcpE6Inert") == []


def test_the_capability_scope_is_enforced_before_the_fixture_exists(harness):
    """A procedure outside the injected scope does not run or create anything."""
    h = harness()
    scope = CAPABILITIES - {"engine.event_unregister_by_id"}
    record = h.run(capabilities=scope).record
    unreg = next(
        item for item in record.measurements if item.experiment_id == "M-UNREG-1"
    )
    assert unreg.status is MeasurementStatus.NOT_RUN
    assert unreg.reason.startswith("capability_not_in_scope")
    assert h.scripts("lwAddDevice") == []


def test_the_runner_mutates_no_catalog_and_the_product_has_no_override():
    """R-QUAL-02/R-QUAL-14: experimental scope is runner-only."""
    before = capability_snapshot_hash(packet_tracer_service_capabilities(SIM_BUILD))
    assert "experimental" not in " ".join(
        inspect.signature(apply_enterprise_services).parameters
    )
    assert (
        "experimental_capabilities"
        in inspect.signature(qualify_server_services).parameters
    )
    after = capability_snapshot_hash(packet_tracer_service_capabilities(SIM_BUILD))
    assert before == after


# -- stop rules and finalization -------------------------------------------------


def test_a_contradiction_stops_later_experiments_before_their_fixture(harness):
    """ATOM-1 counterexample: M-UNREG does not run and PC1 is never created."""
    h = harness({"reset_claim_between_queued": True})
    record = h.run().record
    assert _status(record)["ATOM-1"] == ("ran", "contradicted")
    unreg = next(
        item for item in record.measurements if item.experiment_id == "M-UNREG-1"
    )
    assert unreg.reason == "stopped:contradiction:ATOM-1"
    assert record.primary_failure == "contradiction:ATOM-1"
    assert h.scripts("lwAddDevice") == []
    assert record.outcome is QualificationOutcome.STOPPED


def test_persistence_loss_before_the_first_effect_is_a_refusal(harness):
    """If `admitted` cannot be written, nothing is effected."""
    h = harness()
    store = RecordingStore(h.directory / "records", fail_at={"admitted"})
    result = h.run(record_store=store)
    assert result.outcome is QualificationOutcome.REFUSED
    assert len(h.transport.calls) == 2
    assert h.engine.snapshot()["run_bags"] == {}


def test_persistence_loss_after_an_effect_halts_effects_but_finalizes(harness):
    """No new experiment; owned engine state is still released and read back."""
    h = harness()
    store = RecordingStore(h.directory / "records", fail_from="experiment:ATOM:started")
    result = h.run(record_store=store)
    record = result.record
    assert _status(record)["M-ENG-1"] == ("ran", "supported_in_sample")
    assert _status(record)["ATOM-1"] == ("not_run", "not_evaluated")
    assert (
        record.persist_error and "record_completion_failed" in record.secondary_failures
    )
    assert [kind for kind, _script in h.transport.calls if kind == "send"] == []
    assert h.engine.snapshot()["run_bags"] == {}
    durable = h.durable()
    assert durable.persisted_step == "experiment:ENG:concluded"
    assert durable.completed_at is None
    assert result.outcome is QualificationOutcome.STOPPED


def test_the_time_budget_stops_work_but_keeps_the_finalization_reserve(harness):
    """A long settle exhausts the non-reserve time; finalization still runs."""
    h = harness()
    clock = FakeClock()
    result = h.run(clock=clock, settle_seconds=10_000.0)
    record = result.record
    atom = next(item for item in record.measurements if item.experiment_id == "ATOM-1")
    assert atom.status is MeasurementStatus.INTERRUPTED
    assert record.primary_failure.startswith("operation_refused:time_budget_exhausted")
    refused = [item for item in record.operations if item.refused]
    assert refused and refused[0].phase == "experiment"
    finals = [
        item.purpose for item in record.operations if item.phase == "finalization"
    ]
    assert finals == ["release:run_bag", "read:restoration:1", "read:restoration:2"]
    assert "bag:atom:contender_may_still_run" in record.engine_residue
    assert record.dirty_state is DirtyState.UNKNOWN


def test_an_exception_in_a_probe_still_finalizes_owned_state(harness):
    """The primary error survives, and the PC is removed anyway."""
    h = harness()
    base = h.boundaries()

    class Exploding:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def register_observer_and_trigger(self, device):
            raise RuntimeError("probe exploded")

    result = h.run(
        probes=lambda bound, run_id, nonce: Exploding(base.probes(bound, run_id, nonce))
    )
    record = result.record
    unreg = next(
        item for item in record.measurements if item.experiment_id == "M-UNREG-1"
    )
    assert unreg.status is MeasurementStatus.INTERRUPTED
    assert record.primary_failure.startswith("exception:RuntimeError")
    assert h.engine.snapshot()["devices"] == []
    assert record.restoration_proven is True


def test_cancellation_finalizes_and_then_propagates(harness):
    """KeyboardInterrupt is not swallowed, and finalization still completes."""
    h = harness()
    base = h.boundaries()

    class Cancelling:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def collect_atomicity(self):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        h.run(
            probes=lambda bound, run_id, nonce: Cancelling(
                base.probes(bound, run_id, nonce)
            )
        )
    durable = h.durable()
    assert durable.primary_failure == "cancelled"
    assert durable.completed_at is not None
    assert [item.step for item in durable.transitions][-1] == "finalization:completed"


def test_a_same_name_device_appearing_mid_run_is_a_collision_not_adopted(harness):
    """The pre-read finds it: no creation, no removal, restoration not proven."""
    h = harness()
    h.transport.before[8] = lambda: h.engine.seed_device(PC, "PC-PT")
    record = h.run().record
    assert record.primary_failure == f"fixture_collision:{PC}"
    assert h.scripts("lwAddDevice") == [] and h.scripts("removeDevice") == []
    assert [item["name"] for item in h.engine.snapshot()["devices"]] == [PC]
    assert record.restoration_proven is False
    assert record.dirty_state is DirtyState.UNKNOWN


def test_an_unknown_creation_is_never_replayed(harness):
    """A lost PTBuilder acknowledgement stops the run; cleanup is guarded."""
    h = harness(lose={9})
    record = h.run().record
    assert record.primary_failure == f"outcome_unknown:create:{PC}"
    assert len(h.scripts("lwAddDevice")) == 1
    assert h.engine.snapshot()["devices"] == []
    release = next(item for item in record.releases if item.kind == "device")
    assert release.outcome == "removed"


def test_a_failing_cleanup_is_reported_and_not_repeated(harness):
    """A refused removal leaves known owned residue: dirty, recoverable."""
    h = harness({"remove_throws": True})
    record = h.run().record
    assert len(h.scripts("removeDevice")) == 1
    release = next(item for item in record.releases if item.kind == "device")
    assert release.outcome == "failed"
    assert record.restoration_proven is False
    assert f"device:{PC}:removal_failed" in record.engine_residue


def test_a_foreign_device_appearing_mid_run_is_neither_removed_nor_ignored(harness):
    """Foreign state stops the run and stays; restoration reports it."""
    h = harness()
    h.transport.before[10] = lambda: h.engine.seed_device("Operator-PC", "PC-PT")
    record = h.run().record
    assert record.primary_failure == "foreign_device_observed:Operator-PC"
    names = [item["name"] for item in h.engine.snapshot()["devices"]]
    assert names == ["Operator-PC"]
    assert record.restoration_proven is False
    assert record.dirty_state is DirtyState.UNKNOWN


# -- Q1 below its stage gate -------------------------------------------------------


def _q1_below_the_gate(h: _Harness, max_operations: int = 60):
    """Drive the Q1 executor directly: the stage itself is refused as infeasible.

    The ledger is deliberately built with a test ceiling. The production stage
    ceiling stays 30 and the stage refuses before contact; this exercises the
    executable definition that a reviewed budget decision would unlock.
    """
    boundaries = h.boundaries()
    devices, links = fixture_plans(Q1)
    request = replace(
        _request(),
        stage="Q1",
        targets=Q1.fixture_names,
        authorization=replace(
            _request().authorization,
            stage="Q1",
            targets=Q1.fixture_names,
            max_operations=30,
            max_seconds=600,
        ),
    )
    record = coordinator._initial_record(
        request,
        Q1,
        boundaries,
        IsolationObservation(True, "ISOLATED"),
        RepositoryIdentity(
            head=SIM_SHA, tree="f" * 40, clean=True, upstream_head=SIM_SHA
        ),
        frozenset(Q1.experimental_capabilities),
    )
    run = coordinator._Run(record, boundaries, boundaries.record_store.begin(record))
    ledger = coordinator.OperationLedger(
        max_operations=max_operations, max_seconds=600, clock=boundaries.clock
    )
    run.ledger = ledger
    bound = coordinator.LedgeredTransport(
        ledger, h.transport, boundaries.sleep, boundaries.clock
    )
    assert ServiceEnvironmentReader(bound.send_and_wait).read().version == SIM_BUILD
    physical = boundaries.physical_runtime(bound.send_and_wait)
    baseline = physical.observe_workspace()
    ledger.reserve(Q1.reserve_operations, Q1.budget.reserve_seconds)
    execution = coordinator._Execution(
        run=run,
        nonce="5" * 32,
        definition=Q1,
        devices=devices,
        links=links,
        bound=bound,
        physical=physical,
        baseline=baseline,
        channel="file",
        capabilities=frozenset(Q1.experimental_capabilities),
        probes=boundaries.probes(bound, record.run_id, "5" * 32),
    )
    coordinator._run_q1(execution)
    coordinator._finalize(execution)
    return record, ledger


def test_q1_executor_measures_all_three_and_spends_exactly_its_planned_minimum(harness):
    """The executable Q1 definition costs 45 operations, which is why it refuses."""
    h = harness()
    record, ledger = _q1_below_the_gate(h)
    statuses = _status(record)
    for identifier in ("M-HTTPS-1", "M-HTTPS-2", "M-DNS-3"):
        assert statuses[identifier] == ("ran", "supported_in_sample")
    assert ledger.used == Q1.planned_minimum_operations == 45
    clients = [item for item in record.releases if item.kind == "client"]
    assert [item.outcome for item in clients] == ["released"] * 3
    snapshot = h.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["live_clients"] == 0
    assert record.restoration_proven is True and record.dirty_state is DirtyState.CLEAN


def test_q1_https_success_with_https_disabled_stops_the_stage(harness):
    """The declared contradiction: M-DNS-3 does not run afterwards."""
    h = harness({"serve_https_when_disabled": True})
    record, _ledger = _q1_below_the_gate(h)
    assert _status(record)["M-HTTPS-2"] == ("ran", "contradicted")
    dns = next(item for item in record.measurements if item.experiment_id == "M-DNS-3")
    assert dns.reason == "stopped:contradiction:M-HTTPS-2"
    assert h.engine.snapshot()["devices"] == []


def test_q1_timeouts_are_never_negative_controls(harness):
    """A refused fetch that leaves the page unchanged is inconclusive."""
    h = harness({"fetch_failure": "unchanged"})
    record, _ledger = _q1_below_the_gate(h)
    https2 = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    )
    assert https2.conclusion is MeasurementConclusion.INCONCLUSIVE
    controls = https2.facts
    assert controls["negative_http_mode_http_disabled"]["conclusion"] == "inconclusive"
    assert json.dumps(controls).count("negative_observed") == 0


def test_q1_is_refused_at_the_real_stage_gate(harness):
    """Through the coordinator, Q1 never reaches a channel."""
    h = harness()
    request = replace(
        _request(),
        stage="Q1",
        targets=Q1.fixture_names,
        authorization=replace(
            _request().authorization,
            stage="Q1",
            targets=Q1.fixture_names,
            max_operations=30,
            max_seconds=600,
        ),
    )
    result = h.run(request, capabilities=frozenset(Q1.experimental_capabilities))
    assert [(item.kind, item.subject) for item in result.refusals] == [
        (RefusalKind.INFEASIBLE, RefusalSubject.BUDGET)
    ]
    assert h.opened == [] and h.transport.calls == []


def test_a_secondary_cleanup_failure_never_replaces_the_primary(harness):
    """A probe exception stays primary when the removal also fails."""
    h = harness({"remove_throws": True})
    base = h.boundaries()

    class Exploding:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def read_post_release_and_drop(self):
            raise RuntimeError("probe exploded late")

    record = h.run(
        probes=lambda bound, run_id, nonce: Exploding(base.probes(bound, run_id, nonce))
    ).record
    assert record.primary_failure.startswith("exception:RuntimeError")
    assert f"remove:{PC}:failed" in record.secondary_failures
    assert record.outcome is QualificationOutcome.STOPPED
    assert h.durable().primary_failure == record.primary_failure


def test_q1_executor_at_exactly_its_planned_minimum_completes(harness):
    """With a ceiling equal to 45 the executable definition fits exactly."""
    h = harness()
    record, ledger = _q1_below_the_gate(h, max_operations=45)
    assert ledger.used == 45 and ledger.refused_calls == 0
    assert record.primary_failure == ""


def test_q1_executor_one_below_its_minimum_creates_nothing(harness):
    """The pre-check refuses the stage work; finalization still reads twice."""
    h = harness()
    record, ledger = _q1_below_the_gate(h, max_operations=44)
    assert record.primary_failure == "budget:Q1"
    assert h.scripts("lwAddDevice") == []
    assert [item.purpose for item in ledger.entries][-2:] == [
        "read:restoration:1",
        "read:restoration:2",
    ]


def test_a_lost_inspection_spends_slack_and_stops_before_a_release_is_refused(
    harness,
):
    """The positive fetch polls twice, so M-DNS-3 no longer fits the budget.

    Call 24 is the positive fetch's first inspection. Losing it costs one more
    inspection. The listener measurement still completes, and the budget stop
    lands before M-DNS-3 rather than inside a fetch, so no owned client
    release is ever the call that the budget refuses.
    """
    h = harness(lose={24})
    record, ledger = _q1_below_the_gate(h, max_operations=45)
    assert record.primary_failure == "budget:DNS3"
    statuses = _status(record)
    assert statuses["M-HTTPS-2"] == ("ran", "supported_in_sample")
    dns = next(item for item in record.measurements if item.experiment_id == "M-DNS-3")
    assert dns.reason == "budget_insufficient_for:DNS3"
    clients = [item for item in record.releases if item.kind == "client"]
    assert [item.outcome for item in clients] == ["released"] * 3
    assert ledger.refused_calls == 0 and ledger.used == 45
    snapshot = h.engine.snapshot()
    assert snapshot["live_clients"] == 0 and snapshot["devices"] == []


def test_a_failing_run_bag_release_is_secondary_and_the_record_completes(harness):
    """An exception while releasing engine state never skips completion."""
    h = harness()
    base = h.boundaries()

    class FailingRelease:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def release_run_bag(self):
            raise RuntimeError("release exploded")

    record = h.run(
        probes=lambda bound, run_id, nonce: FailingRelease(
            base.probes(bound, run_id, nonce)
        )
    ).record
    assert "release:run_bag:exception:RuntimeError" in record.secondary_failures
    assert any(item.startswith("bag:") for item in record.engine_residue)
    assert record.dirty_state is DirtyState.UNKNOWN
    durable = h.durable()
    assert durable.completed_at is not None
    assert h.engine.snapshot()["devices"] == []
