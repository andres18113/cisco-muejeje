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
    _snapshot_facts,
    qualify_server_services,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DirtyState,
    DispatchFact,
    PostconditionFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import AcquireDhcpLease
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
from packet_tracer_mcp.domain.enterprise.services.service_qualification_evidence import (
    ProbeReading,
)
from packet_tracer_mcp.infrastructure.catalog.service_capabilities import (
    capability_snapshot_hash,
    packet_tracer_service_capabilities,
)
from packet_tracer_mcp.infrastructure.execution.service_environment import (
    ServiceEnvironmentReader,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

Q0 = STAGE_DEFINITIONS[QualificationStage.Q0]
Q1 = STAGE_DEFINITIONS[QualificationStage.Q1]
Q3 = STAGE_DEFINITIONS[QualificationStage.Q3]
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


FIXED_RUN = "2026-09-18T00-00-00Z-fixedrun"


def _fixed_run_id(_moment) -> str:
    return FIXED_RUN


def _plant_foreign_run_key(harness, run: str = FIXED_RUN) -> dict:
    """Place a run key another invocation owns, and return its exact content."""
    planted = {
        "owner": "another-invocations-nonce",
        "sentinel": {"nonce": "another-invocations-nonce"},
        "unrelated": ["keep", "me"],
    }
    harness.engine.evaluate(
        "var q=this.__mcpE6Q=this.__mcpE6Q||{};"
        f"q[{json.dumps(run)}]={json.dumps(planted)};reportResult('planted');"
    )
    return planted


def _engine_bag(harness) -> dict:
    """Read the whole run-bag container straight out of the stub engine."""
    return json.loads(
        harness.engine.evaluate("reportResult(JSON.stringify(this.__mcpE6Q||{}));")
    )


def _q3_request():
    return replace(
        _request(),
        stage="Q3",
        targets=Q3.fixture_names,
        authorization=replace(
            _request().authorization,
            stage="Q3",
            targets=Q3.fixture_names,
            max_operations=Q3.budget.max_operations,
            max_seconds=Q3.budget.max_seconds,
        ),
    )


def _q1_request():
    return replace(
        _request(),
        stage="Q1",
        targets=Q1.fixture_names,
        authorization=replace(
            _request().authorization,
            stage="Q1",
            targets=Q1.fixture_names,
            max_operations=Q1.budget.max_operations,
            max_seconds=Q1.budget.max_seconds,
        ),
    )


class _Wrapped:
    """A boundary object with one method replaced, and the rest untouched."""

    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)


class _LateReadinessTransport(_Wrapped):
    """Advance the injected clock after one correlated readiness response."""

    def __init__(self, inner, clock, *, late_read: int, elapsed: float):
        super().__init__(inner)
        self.clock = clock
        self.late_read = late_read
        self.elapsed = elapsed
        self.reads = 0
        self.timeouts: list[float] = []

    def dispatch_and_wait(self, js_code: str, timeout: float):
        if 'step:"readiness"' in js_code or 'step:"port_readiness"' in js_code:
            self.reads += 1
            self.timeouts.append(timeout)
            outcome = self.inner.dispatch_and_wait(js_code, timeout)
            if self.reads == self.late_read:
                self.clock.now += self.elapsed
            return outcome
        return self.inner.dispatch_and_wait(js_code, timeout)


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


def test_a_foreign_run_key_stops_the_run_and_is_neither_written_nor_deleted(
    harness,
):
    """A collision is a refusal with nothing to undo, and nothing to clean up."""
    h = harness()
    planted = _plant_foreign_run_key(h)
    result = h.run(new_run_id=_fixed_run_id)
    record = result.record
    assert _status(record)["M-ENG-1"] == ("ran", "contradicted")
    assert record.primary_failure == "contradiction:M-ENG-1"
    # No claim, so no release: the finalizer never dispatches over a foreign key.
    assert h.scripts("bag_release") == []
    assert "bag:run_key_not_exclusively_owned" in record.engine_residue
    bag = next(item for item in record.releases if item.kind == "bag")
    assert bag.outcome == "not_attempted"
    assert _engine_bag(h) == {FIXED_RUN: planted}


def test_a_lost_claim_over_a_foreign_key_finalizes_without_deleting_it(harness):
    """Call 3 is the claim. Its answer is lost, so ownership is undecided here.

    The finalizer must still look, because the claim may have executed. The
    engine-side proof -- this invocation's nonce, not the key's name -- is what
    refuses the delete, and the record reports the key as residue.
    """
    h = harness(lose={3})
    planted = _plant_foreign_run_key(h)
    record = h.run(new_run_id=_fixed_run_id).record
    assert len(h.scripts("bag_release")) == 1
    bag = next(item for item in record.releases if item.kind == "bag")
    assert bag.outcome == "not_attempted"
    assert "bag:run_key_not_owned" in record.engine_residue
    assert "bag:sentinel:release_unverified" in record.engine_residue
    assert _engine_bag(h) == {FIXED_RUN: planted}


def test_an_uncertain_first_contender_never_queues_the_second(harness):
    """Call 5 is contender A. An unknown dispatch admits no second contender."""
    h = harness(not_submitted={5})
    record = h.run().record
    assert len(h.scripts('c:"A"')) == 1
    assert h.scripts('c:"B"') == []
    atom = next(item for item in record.measurements if item.experiment_id == "ATOM-1")
    assert atom.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "contender_acceptance_unknown" in atom.causes
    assert atom.outcome_unknown is True


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


def _q1_executor(h: _Harness, max_operations: int = 60, **overrides):
    """Drive the Q1 executor directly, with an explicit test ceiling.

    The stage is admitted at its real gate now; this helper exists to put the
    ledger at a chosen ceiling, so a test can stand exactly on the budget
    boundary instead of inside the production slack.
    """
    boundaries = h.boundaries(**overrides)
    devices, links = fixture_plans(Q1)
    request = _q1_request()
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


def test_q1_measures_both_experiments_inside_its_planned_worst_case(harness):
    """The nominal trace is cheaper than the plan, because the plan is the worst case.

    M-HTTPS-2 runs both same-mode positives and both negatives and concludes
    INCONCLUSIVE against a stub that behaves exactly as the model predicts:
    the reader has no observation that establishes a refusal, so the negative
    half of the model stays open however well the engine behaves. That is the
    measurement, not a defect.
    """
    h = harness()
    record, ledger = _q1_executor(h)
    statuses = _status(record)
    assert statuses["M-HTTPS-1"] == ("ran", "supported_in_sample")
    assert statuses["M-HTTPS-2"] == ("ran", "inconclusive")
    # Q1R-5.1: declared omitted with its reason, and never dispatched.
    assert statuses["M-DNS-3"][0] == "omitted"
    assert h.scripts("getServerIp()") == []
    tables = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-1"
    )
    assert tables.facts["page_table_model"] == "separate"
    listener = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    )
    for key in ("positive_http_mode_both_enabled", "positive_https_only"):
        assert listener.facts[key]["conclusion"] == "supported_in_sample"
    gate = listener.facts["readiness_before"]
    assert (gate["ready"], gate["reads"], gate["max_reads"]) == (True, 1, 4)
    assert gate["last"]["observed"] is True
    assert json.dumps(listener.facts).count("negative_observed") == 0
    assert ledger.used == 51 < Q1.planned_minimum_operations == 56
    assert ledger.refused_calls == 0
    clients = [item for item in record.releases if item.kind == "client"]
    assert [item.outcome for item in clients] == ["released"] * 4
    snapshot = h.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["live_clients"] == 0
    assert record.restoration_proven is True and record.dirty_state is DirtyState.CLEAN


@pytest.mark.parametrize(
    ("label", "transform"),
    [
        ("empty", lambda rows: []),
        ("short", lambda rows: rows[:-1]),
        (
            "unknown",
            lambda rows: [item.model_copy(update={"applied": False}) for item in rows],
        ),
    ],
)
def test_an_unaccepted_e5_batch_dispatches_no_e6_enable(harness, label, transform):
    """E5 is classified before the E6 batch is built, so a refusal prevents it."""
    h = harness()
    base = h.boundaries()

    class _Truncated(_Wrapped):
        def apply_actions(self, actions):
            return transform(self.inner.apply_actions(actions))

    record, _ledger = _q1_executor(
        h,
        configuration_runtime=lambda bound: _Truncated(
            base.configuration_runtime(bound)
        ),
    )
    assert record.primary_failure.startswith("outcome_unknown:e5_endpoints")
    assert h.scripts("setEnable(true)") == []
    assert h.scripts("createClient") == []
    limitation = next(
        item for item in record.limitations if item.startswith("e5_endpoint_dispatch:")
    )
    assert limitation != "e5_endpoint_dispatch:accepted"
    if label == "short":
        assert "incomplete_result_set:2_of_3" in limitation
    assert h.engine.snapshot()["devices"] == []


def test_an_unread_listener_toggle_admits_no_fetch_and_no_second_toggle(harness):
    """The toggle's effect may have happened; nobody read it back, so it stops there."""
    h = harness()
    base = h.boundaries()

    class _LostToggle(_Wrapped):
        def prepare_marker_page(self, server, marker):
            # The effect still reaches the engine; only the answer is lost.
            self.inner.prepare_marker_page(server, marker)
            return ProbeReading(
                "marker_page",
                DispatchFact.ACCEPTED,
                ResultFact.NOT_OBSERVED,
                False,
                cause="stub_response_lost",
            )

    record, _ledger = _q1_executor(
        h,
        probes=lambda bound, run_id, nonce: _LostToggle(
            base.probes(bound, run_id, nonce)
        ),
    )
    listener = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    )
    assert listener.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert listener.outcome_unknown is True
    assert "setup_unobserved:marker_page" in listener.causes
    assert h.scripts("createClient") == []
    assert h.scripts("setEnable(false)") == []
    assert h.scripts("setHttpsEnable(false)") == []
    assert record.primary_failure == "outcome_unknown:M-HTTPS-2"
    assert h.engine.snapshot()["devices"] == []


def test_wrong_positive_page_is_classified_before_any_negative_effect(harness):
    """A released positive contradiction stops at its own channel boundary."""
    h = harness({"fetch_content_override": "WRONG-FRESH-PAGE"})

    record, _ledger = _q1_executor(h)

    listener = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    )
    assert listener.conclusion is MeasurementConclusion.CONTRADICTED
    positive = listener.facts["positive_http_mode_both_enabled"]
    assert positive["fetch"] == "fresh_without_marker"
    assert listener.facts["positive_https_only"]["fetch"] == "not_run"
    assert listener.facts["negative_http_mode_http_disabled"]["fetch"] == "not_run"
    assert listener.facts["negative_https_mode_https_disabled"]["fetch"] == "not_run"
    assert len(h.scripts("createClient()")) == 1
    assert h.scripts("setEnable(false)") == []
    assert h.scripts("setHttpsEnable(false)") == []
    assert h.scripts("getServerIp()") == []
    assert [item.resource for item in record.releases if item.kind == "client"] == [
        "client:http-positive"
    ]
    dns = next(item for item in record.measurements if item.experiment_id == "M-DNS-3")
    assert dns.status is MeasurementStatus.OMITTED
    assert dns.reason.startswith("already_measured")
    assert record.primary_failure == "contradiction:M-HTTPS-2"
    assert [item.step for item in record.transitions][-2:] == [
        "finalization:started",
        "finalization:completed",
    ]
    durable = h.durable()
    durable_listener = next(
        item for item in durable.measurements if item.experiment_id == "M-HTTPS-2"
    )
    assert durable_listener.conclusion is MeasurementConclusion.CONTRADICTED
    assert durable.primary_failure == "contradiction:M-HTTPS-2"
    snapshot = h.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["live_clients"] == 0


def test_q1_https_success_with_https_disabled_stops_the_stage(harness):
    """The declared contradiction stops the stage at its own boundary."""
    h = harness({"serve_https_when_disabled": True})
    record, _ledger = _q1_executor(h)
    assert _status(record)["M-HTTPS-2"] == ("ran", "contradicted")
    assert record.primary_failure == "contradiction:M-HTTPS-2"
    assert h.engine.snapshot()["devices"] == []


def test_q1_timeouts_are_never_negative_controls(harness):
    """A positive that times out leaves every negative unrun and uninterpreted.

    No wait or timeout is added to force it: the procedure spends one readiness
    read instead, so the record says what the fixture looked like when the
    positive failed, and it creates no second client and toggles nothing.
    """
    h = harness({"fetch_failure": "unchanged", "serve_nothing": True})
    record, _ledger = _q1_executor(h)
    https2 = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    )
    assert https2.conclusion is MeasurementConclusion.INCONCLUSIVE
    controls = https2.facts
    assert controls["positive_http_mode_both_enabled"]["fetch"].startswith(
        "unestablished:inconclusive:no_response_within_deadline"
    )
    assert controls["negative_http_mode_http_disabled"]["fetch"] == "not_run"
    assert "negative_http:no_same_mode_positive_control" in https2.causes
    assert controls["readiness_after_failed_positive"]["observed"] is True
    assert json.dumps(controls).count("negative_observed") == 0
    assert len(h.scripts("createClient()")) == 1
    assert h.scripts("setEnable(false)") == []


def test_an_unresolved_page_effect_admits_no_further_experimental_effect(harness):
    """Q1R-7: the setter changed the page and threw, so the stage stops there.

    The probe reports `written=false` because it sets that flag only after
    `setPageContents` returns. The page moved anyway, and no read followed it,
    so the effect is unresolved: no second page setter, no listener toggle, no
    fetch and no unrelated measurement may run. Only the owned finalization
    continues, and it completes in full.
    """
    h = harness({"setpage_throws_after_http": ["index"]})

    record, _ledger = _q1_executor(h)

    tables = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-1"
    )
    assert tables.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert tables.causes[0] == "marker_write_failed:http"
    assert tables.facts["page_effect"] == "unresolved"
    assert tables.outcome_unknown is True
    assert record.primary_failure == "outcome_unknown:M-HTTPS-1"
    assert len(h.scripts("setPageContents(")) == 1
    assert h.scripts("setEnable(false)") == []
    assert h.scripts("setHttpsEnable(false)") == []
    assert h.scripts("createClient") == []
    assert h.scripts("getServerIp()") == []
    listener = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    )
    assert listener.status is MeasurementStatus.NOT_RUN
    assert listener.reason == "stopped:outcome_unknown:M-HTTPS-1"
    assert record.restoration_proven is True
    assert h.engine.snapshot()["devices"] == []
    assert [item.step for item in record.transitions][-2:] == [
        "finalization:started",
        "finalization:completed",
    ]


def test_a_baseline_read_failure_attributes_no_unresolved_effect(harness):
    """Q1R-7: the guard stopped before the setter, so nothing is unknown.

    The page procedure decides nothing about the table model, which is a
    conclusion about its subject and not a loose effect. The stage therefore
    goes on to the listener procedure instead of being stopped by an unknown
    outcome that never happened.
    """
    h = harness({"getpage_throws_https": ["index"]})

    record, _ledger = _q1_executor(h)

    tables = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-1"
    )
    assert tables.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert tables.facts["page_effect"] == "not_attempted"
    assert tables.outcome_unknown is False
    # The procedure stopped after its first step, and the stop was the
    # measurement, not this stage.
    assert len(h.scripts('step:"page_write"')) == 1
    assert "M-HTTPS-1" not in record.primary_failure
    assert _status(record)["M-HTTPS-2"][0] == "ran"
    assert record.restoration_proven is True


def test_the_page_procedure_never_names_a_new_page(harness):
    """Q1R-1: every page write targets the existing index page."""
    h = harness()
    _q1_executor(h)
    assert h.scripts("mcpq-") == []
    writes = h.scripts("setPageContents(")
    assert writes and all('setPageContents("index.html"' in item for item in writes)


def test_a_retained_backend_device_is_named_and_not_hidden(harness):
    """Q1R-6: CLEAN in its semantic scope, with the raw difference stated."""
    h = harness()
    h.transport.before[50] = lambda: h.engine.seed_device(
        "Power Distribution Device0", "Power Distribution Device"
    )
    record, ledger = _q1_executor(h)
    assert ledger.used == 51
    assert record.restoration_proven is True
    assert "restoration_scope:semantic_devices_and_links" in record.limitations
    assert "backend_managed_devices_changed:0->1" in record.limitations
    assert [item["backend_managed_device_count"] for item in record.restoration] == [
        1,
        1,
    ]


def test_q1_passes_the_real_stage_gate_and_finalizes_inside_its_ceiling(harness):
    """Through the whole coordinator, at the reviewed ceiling, with cleanup proven."""
    h = harness()
    result = h.run(_q1_request(), capabilities=frozenset(Q1.experimental_capabilities))
    record = result.record
    assert result.refusals == []
    assert h.opened == ["file"]
    assert record.budget.max_operations == 60
    assert record.budget.planned_minimum_operations == 56
    assert record.budget.used_operations <= Q1.planned_minimum_operations
    assert record.budget.refused_calls == 0
    assert record.restoration_proven is True
    snapshot = h.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["live_clients"] == 0
    assert snapshot["run_bags"] == {}


def test_a_budget_below_the_worst_case_refuses_before_any_channel(harness):
    """An authorization that does not reach the planned worst case never contacts."""
    h = harness()
    request = replace(
        _q1_request(),
        authorization=replace(_q1_request().authorization, max_operations=52),
    )
    result = h.run(request, capabilities=frozenset(Q1.experimental_capabilities))
    assert [(item.kind, item.subject) for item in result.refusals] == [
        (RefusalKind.MISMATCH, RefusalSubject.BUDGET)
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


def test_q1_executor_at_exactly_its_planned_worst_case_completes(harness):
    """A ceiling equal to the planned 56 admits the stage and is never exceeded."""
    h = harness()
    record, ledger = _q1_executor(h, max_operations=56)
    assert ledger.used <= 56 and ledger.refused_calls == 0
    assert record.primary_failure == ""
    assert record.restoration_proven is True


def test_q1_executor_one_below_its_worst_case_creates_nothing(harness):
    """The pre-check refuses the stage work; finalization still reads twice."""
    h = harness()
    record, ledger = _q1_executor(h, max_operations=55)
    assert record.primary_failure == "budget:Q1"
    assert h.scripts("lwAddDevice") == []
    assert [item.purpose for item in ledger.entries][-2:] == [
        "read:restoration:1",
        "read:restoration:2",
    ]


def test_a_lost_inspection_is_exactly_what_the_worst_case_budget_pays_for(harness):
    """The complete worst case: a slow fixture and both positives losing one poll.

    The fixture needs all four readiness reads before every link is up, and
    the two positives each lose their first inspection, which costs that fetch
    its fourth operation. Both are exactly what the plan budgets, so the trace
    lands on the planned worst case: nothing is refused, every owned client is
    still released, and the finalization reserve is untouched.
    """
    h = harness({"ports_down_calls": 18}, lose={30, 35})
    record, ledger = _q1_executor(h, max_operations=56)
    assert record.primary_failure == ""
    assert ledger.used == 56 == Q1.planned_minimum_operations
    assert ledger.refused_calls == 0
    gate = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    ).facts["readiness_before"]
    assert (gate["ready"], gate["reads"]) == (True, 4)
    assert gate["first"]["ports"]["__MCP_E6Q_SRV/FastEthernet0"]["port_up"] is False
    assert gate["last"]["ports"]["__MCP_E6Q_SRV/FastEthernet0"]["port_up"] is True
    clients = [item for item in record.releases if item.kind == "client"]
    assert [item.outcome for item in clients] == ["released"] * 4
    assert record.restoration_proven is True
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


# -- amendment 01: the bounded readiness gate ------------------------------------


def _q3_executor(h: _Harness, max_operations: int = 60, **overrides):
    """Drive the Q3 executor directly, at a chosen ceiling."""
    boundaries = h.boundaries(**overrides)
    devices, links = fixture_plans(Q3)
    request = _q3_request()
    record = coordinator._initial_record(
        request,
        Q3,
        boundaries,
        IsolationObservation(True, "ISOLATED"),
        RepositoryIdentity(
            head=SIM_SHA, tree="f" * 40, clean=True, upstream_head=SIM_SHA
        ),
        frozenset(Q3.experimental_capabilities),
    )
    record.environment.observed_build = SIM_BUILD
    run = coordinator._Run(record, boundaries, boundaries.record_store.begin(record))
    ledger = coordinator.OperationLedger(
        max_operations=max_operations, max_seconds=1200, clock=boundaries.clock
    )
    run.ledger = ledger
    bound = coordinator.LedgeredTransport(
        ledger, h.transport, boundaries.sleep, boundaries.clock
    )
    assert ServiceEnvironmentReader(bound.send_and_wait).read().version == SIM_BUILD
    physical = boundaries.physical_runtime(bound.send_and_wait)
    baseline = physical.observe_workspace()
    ledger.reserve(Q3.reserve_operations, Q3.budget.reserve_seconds)
    execution = coordinator._Execution(
        run=run,
        nonce="7" * 32,
        definition=Q3,
        devices=devices,
        links=links,
        bound=bound,
        physical=physical,
        baseline=baseline,
        channel="file",
        capabilities=frozenset(Q3.experimental_capabilities),
        probes=boundaries.probes(bound, record.run_id, "7" * 32),
        product_contract=boundaries.q3_product_contract(SIM_BUILD, "file"),
    )
    coordinator._run_q3(execution)
    coordinator._finalize(execution)
    return record, ledger


def _gate_of(record, experiment_id: str, key: str = "readiness") -> dict:
    facts = next(
        item for item in record.measurements if item.experiment_id == experiment_id
    ).facts
    return facts[key if key in facts else "readiness_before"]


def test_a_fixture_that_is_already_up_costs_exactly_one_readiness_read(harness):
    """The gate stops at the first complete ready sample."""
    h = harness()
    record, _ledger = _q1_executor(h)
    gate = _gate_of(record, "M-HTTPS-2", "readiness_before")
    assert (gate["ready"], gate["reads"]) == (True, 1)
    assert gate["deadline_seconds"] == 30.0
    assert gate["first"] == gate["last"]


def test_a_fixture_that_comes_up_late_is_admitted_on_the_fresh_sample(harness):
    """F3: the first two reads are down, the third is complete and ready."""
    h = harness({"ports_down_calls": 12})
    record, _ledger = _q1_executor(h)
    gate = _gate_of(record, "M-HTTPS-2", "readiness_before")
    assert (gate["ready"], gate["reads"]) == (True, 3)
    assert gate["first"]["ports"]["__MCP_E6Q_SRV/FastEthernet0"]["port_up"] is False
    assert gate["last"]["ports"]["__MCP_E6Q_SRV/FastEthernet0"]["port_up"] is True
    listener = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    )
    assert listener.facts["positive_http_mode_both_enabled"]["fetch"] == (
        "marker_retrieved"
    )


def test_a_fixture_that_never_comes_up_starts_no_fetch_and_no_client(harness):
    """F3: no marked page, no created client, and no listener verdict."""
    h = harness({"ports_up": False})
    record, ledger = _q1_executor(h)
    listener = next(
        item for item in record.measurements if item.experiment_id == "M-HTTPS-2"
    )
    gate = listener.facts["readiness_before"]
    assert (gate["ready"], gate["reads"]) == (False, 4)
    assert gate["reason"].startswith("readiness_not_up:")
    assert listener.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "readiness_not_established:readiness_not_up" in " ".join(listener.causes)
    assert "readiness_result_is_not_a_listener_verdict" in listener.limitations
    assert h.scripts("createClient") == []
    # The marked page belongs to the gated procedure, so it was never written.
    assert h.scripts("-INDEX") == []
    assert listener.facts["marker_page"] == {"established": False}
    assert ledger.refused_calls == 0
    assert record.restoration_proven is True
    assert h.engine.snapshot()["devices"] == []


def test_a_non_boolean_readiness_reader_is_never_read_as_down_or_up(harness):
    """F3: an invalid native value is incomplete, which is not `false`."""
    h = harness({"protocol_up_return": "string"})
    record, _ledger = _q1_executor(h)
    gate = _gate_of(record, "M-HTTPS-2", "readiness_before")
    assert gate["ready"] is False
    assert gate["reason"].endswith(":protocol_up")
    assert "readiness_non_boolean" in gate["reason"]
    row = gate["last"]["ports"]["__MCP_E6Q_SRV/FastEthernet0"]
    assert row["protocol_up"] is None and row["protocol_up_type"] == "string"
    assert h.scripts("createClient") == []


def test_the_readiness_gate_stops_at_its_monotonic_deadline(harness):
    """F3: the gate is a 30-second precondition, not an open-ended wait."""
    h = harness({"ports_up": False})
    record, ledger = _q1_executor(h, settle_seconds=20.0)
    gate = _gate_of(record, "M-HTTPS-2", "readiness_before")
    assert gate["ready"] is False
    assert gate["reads"] < 4 and gate["reason"] == "readiness_deadline_reached"
    assert gate["elapsed_seconds"] >= 30.0
    assert h.scripts("createClient") == []
    assert ledger.refused_calls == 0
    assert [item.purpose for item in ledger.entries][-2:] == [
        "read:restoration:1",
        "read:restoration:2",
    ]
    assert record.restoration_proven is True


def test_a_ready_sample_returned_after_the_deadline_grants_no_permission(harness):
    """F2-close: a late correlated body is evidence, never authorization."""
    h = harness({"ports_down_calls": 12})
    clock = FakeClock()
    delayed = _LateReadinessTransport(h.transport, clock, late_read=3, elapsed=3.0)
    h.transport = delayed

    record, ledger = _q1_executor(h, clock=clock, settle_seconds=14.0)

    gate = _gate_of(record, "M-HTTPS-2", "readiness_before")
    assert gate["ready"] is False
    assert gate["reads"] == 3
    assert gate["reason"] == "readiness_deadline_reached_after_read"
    assert gate["last"]["ports"]["__MCP_E6Q_SRV/FastEthernet0"]["port_up"] is True
    assert delayed.timeouts[-1] == pytest.approx(2.0)
    assert h.scripts("createClient") == []
    assert ledger.refused_calls == 0
    assert record.restoration_proven is True


def test_a_record_that_cannot_advance_admits_no_readiness_read_or_effect(harness):
    """The persistence gate closes effects before the gate reads anything."""
    h = harness()
    store = RecordingStore(
        h.directory / "records", fail_from="experiment:HTTPS2:started"
    )
    record, ledger = _q1_executor(h, record_store=store)
    assert record.primary_failure == "persistence:record_not_advanced"
    assert [
        item.purpose for item in ledger.entries if "readiness" in item.purpose
    ] == []
    assert h.scripts("createClient") == []
    assert h.engine.snapshot()["devices"] == []


# -- amendment 01: Q3 classifies E5 before it mutates the server ----------------


def test_q3_dispatches_no_server_mutation_when_e5_is_not_complete(harness):
    """F5: an E5 batch whose rows are missing founds nothing for E6."""
    h = harness()
    base = h.boundaries()

    class _Truncated(_Wrapped):
        def apply_actions(self, actions):
            return self.inner.apply_actions(actions)[:-1]

    record, _ledger = _q3_executor(
        h,
        configuration_runtime=lambda bound: _Truncated(
            base.configuration_runtime(bound)
        ),
    )
    assert record.primary_failure == "q3_foundations_not_established"
    assert h.scripts("addPool") == []
    assert h.scripts("dhcpRun") == []
    setup = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-1"
    )
    # The applicator blocked the dependent endpoint instead of reporting it,
    # so the foundations are incomplete and nothing may be built on them.
    assert "dependency_blocked" in setup.facts["foundation_statuses"].values()
    assert setup.facts["server_mutations"] == []
    assert setup.facts["server_readback"] == {}
    assert record.restoration_proven is True


def test_q3_dispatches_no_server_mutation_when_a_foundation_is_not_verified(harness):
    """F5: foundations are derived and judged before the E6 batch is built."""
    h = harness()
    base = h.boundaries()

    class _Unverified(_Wrapped):
        def verify(self, expectations):
            rows = self.inner.verify(expectations)
            return [
                item.model_copy(update={"status": ActionExecutionStatus.UNKNOWN})
                for item in rows
            ]

    record, _ledger = _q3_executor(
        h,
        configuration_runtime=lambda bound: _Unverified(
            base.configuration_runtime(bound)
        ),
    )
    assert record.primary_failure == "q3_foundations_not_established"
    assert h.scripts("addPool") == []
    assert h.scripts("dhcpRun") == []
    assert record.restoration_proven is True


def test_q3_readiness_precedes_the_first_dhcp_client_activation(harness):
    """F2-close: an unready fixture admits no SetEndpointDhcp or dhcpRun."""
    h = harness({"ports_up": False, "dhcp_default_pool": "native"})

    record, ledger = _q3_executor(h)

    snapshot = h.engine.snapshot()
    assert snapshot["dhcp_setter_calls"]["configurePcIpDhcp"] == 0
    assert snapshot["dhcp_setter_calls"]["setEnable"] == 0
    assert snapshot["dhcp_setter_calls"]["addPool"] == 0
    assert snapshot["dhcp_runs"] == []
    assert h.scripts("createClient") == []
    assert record.restoration_proven is True
    assert ledger.refused_calls == 0


def test_q3_reuses_exact_setup_rows_without_rescheduling_server_actions(harness):
    """F4-close: setup setters are scheduled once and their rows are retained."""
    h = harness({"dhcp_default_pool": "native"})

    record, _ledger = _q3_executor(h)

    assert record.primary_failure == "outcome_unknown:q3_product_service"
    snapshot = h.engine.snapshot()
    calls = snapshot["dhcp_setter_calls"]
    assert calls["configurePcIpDhcp"] == 2
    assert calls["setEnable"] == 1
    assert calls["addPool"] == 1
    assert calls["setNetworkMask"] == 1
    assert calls["setStartIp"] == 1
    assert calls["setEndIp"] == 1
    assert calls["setMaxUsers"] == 1
    assert len(h.scripts("setEnable(true)")) == 1
    assert len(h.scripts("addPool(")) == 1


def test_q3_lost_action_acknowledgement_blocks_the_guard_and_later_effects(harness):
    """F4-close: attempted=None with an unknown envelope is never permission."""
    h = harness({"dhcp_default_pool": "native"})
    base = h.boundaries()

    class _LostAcknowledgement(_Wrapped):
        def apply_actions(self, actions):
            rows = self.inner.apply_actions(actions)
            first = next(
                (item.id for item in actions if isinstance(item, AcquireDhcpLease)),
                "",
            )
            return [
                row.model_copy(
                    update={
                        "applied": False,
                        "dispatch": DispatchFact.ACCEPTANCE_UNKNOWN,
                        "result": ResultFact.NOT_OBSERVED,
                        "postcondition": PostconditionFact.UNOBSERVED,
                        "attempted": None,
                        "cause": "synthetic_acknowledgement_lost",
                    }
                )
                if row.action_id == first
                else row
                for row in rows
            ]

    record, ledger = _q3_executor(
        h,
        service_runtime=lambda bound: _LostAcknowledgement(base.service_runtime(bound)),
    )

    assert record.primary_failure == "outcome_unknown:q3_product_service"
    assert not any(
        item.purpose == "q3:guard:acquisition_replay" for item in ledger.entries
    )
    assert record.restoration_proven is True


# -- A02-E1: the record is the one sink for every native default reading -------

SRV = "__MCP_E6Q_SRV"
#: The exact LIVE transition: enabling the process moved the native default.
NATIVE_DEFAULT_MOVES = {
    "dhcp_default_pool": "native",
    "default_pool_change_on_enable": {
        "network": "192.0.2.0",
        "mask": "255.255.255.0",
        "start": "192.0.2.0",
        "end": "192.0.3.255",
    },
}
LATE_END = "203.0.113.255"
MOVED_ON_ENABLE = [
    "default_pool_changed:serverPool.end",
    "default_pool_changed:serverPool.mask",
    "default_pool_changed:serverPool.network",
    "default_pool_changed:serverPool.start",
]
DEFAULT_LABELS = ["before_e5", "after_setup", "before_cleanup"]
DEFAULT_PURPOSES = [f"q3:native_default:{item}" for item in DEFAULT_LABELS]


def _move_native_default(engine, end_ip: str) -> None:
    """Move the native default once, through the engine's own pool object."""
    engine.evaluate(
        f"var d=ipc.network().getDevice({json.dumps(SRV)});"
        "var m=d&&d.getProcess('DhcpServerMain');"
        "var p=m&&m.getDhcpServerProcessByPortName('FastEthernet0');"
        "var q=p&&p.getPool('serverPool');"
        f"if(q){{q.setEndIp({json.dumps(end_ip)});}}"
        "reportResult(JSON.stringify({moved:!!q}));"
    )


class _NativeDefaultWatcher(_Wrapped):
    """Watch every native default read and disturb exactly one of them.

    `pools` keeps what the stub engine itself held at each read, so the oracle
    for a persisted reading is the engine's own state at that moment rather
    than a second copy of the projection. `hook` runs right after the numbered
    read returns; `lose` and `corrupt` replace one read's answer without
    changing any other call.
    """

    def __init__(
        self,
        inner,
        engine,
        *,
        hook_after: int = 0,
        hook=None,
        lose: int = 0,
        corrupt: int = 0,
    ):
        super().__init__(inner)
        self.engine = engine
        self.hook_after = hook_after
        self.hook = hook
        self.lose = lose
        self.corrupt = corrupt
        self.reads = 0
        self.pools: list[dict] = []

    def _native_end(self, index: int) -> str:
        return self.pools[index]["pools"]["serverPool"]["end"]

    def dispatch_and_wait(self, js_code: str, timeout: float):
        if 'step:"dhcp_server_baseline"' not in js_code:
            return self.inner.dispatch_and_wait(js_code, timeout)
        self.reads += 1
        outcome = self.inner.dispatch_and_wait(js_code, timeout)
        # Taken after the read, because the stub materializes the stock
        # default pool on the first access, exactly as the read observes it.
        self.pools.append(self.engine.snapshot()["dhcp_servers"].get(SRV, {}))
        if self.reads == self.lose:
            outcome = BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                result=ResultFact.NOT_OBSERVED,
                detail="stub_response_lost",
            )
        elif self.reads == self.corrupt:
            body = json.loads(outcome.body)
            body["pool_count"] = len(body["pools"]) + 1
            outcome = replace(outcome, body=json.dumps(body))
        if self.reads == self.hook_after and self.hook is not None:
            self.hook()
        return outcome


def _watch(h: _Harness, **options) -> _NativeDefaultWatcher:
    """Put a watcher in front of the harness channel and return it."""
    watcher = _NativeDefaultWatcher(h.transport, h.engine, **options)
    h.transport = watcher
    return watcher


def _q3_stage(h: _Harness, **overrides):
    """Run the whole Q3 stage through the coordinator at its own ceiling."""
    return h.run(
        _q3_request(),
        capabilities=frozenset(Q3.experimental_capabilities),
        **overrides,
    )


def test_every_native_default_reading_reaches_the_terminal_record(harness):
    """A02-E1: the reading taken after the stop is durable, and it is its own.

    Enabling the process moves the native default, so Q3 stops and takes its
    last reading after the final conclusion and after `Q3_SETUP` finished. The
    engine then moves the default once more, so a record that reproduced
    `after_setup` instead of persisting what it read would contradict the
    stub's own state at that moment.
    """
    h = harness(NATIVE_DEFAULT_MOVES)
    watcher = _watch(
        h, hook_after=2, hook=lambda: _move_native_default(h.engine, LATE_END)
    )

    result = _q3_stage(h)

    assert result.record.primary_failure == (
        "q3_native_default_changed:default_pool_changed:serverPool.end"
    )
    durable = h.durable()
    entries = durable.native_default_pool
    assert [item.label for item in entries] == DEFAULT_LABELS
    assert [item.purpose for item in entries] == DEFAULT_PURPOSES
    assert [item.observed for item in entries] == [True, True, True]
    counted = {item.seq: item.purpose for item in durable.operations if item.seq}
    assert [counted[item.operation_seq] for item in entries] == DEFAULT_PURPOSES
    assert watcher.reads == 3
    assert [item.pools[0]["end"] for item in entries] == [
        watcher._native_end(0),
        watcher._native_end(1),
        LATE_END,
    ]
    assert entries[2].pools[0]["end"] != entries[1].pools[0]["end"]
    assert [item.differences for item in entries] == [
        [],
        MOVED_ON_ENABLE,
        MOVED_ON_ENABLE,
    ]
    assert durable.budget.used_operations <= Q3.planned_minimum_operations
    assert h.scripts("dhcpRun") == [] and h.engine.snapshot()["dhcp_runs"] == []
    assert durable.restoration_proven is True


def test_the_terminal_record_carries_the_readings_when_completion_fails(harness):
    """A02-E1: each reading is durable when it is taken, not only at the end."""
    h = harness(NATIVE_DEFAULT_MOVES)
    _watch(h, hook_after=2, hook=lambda: _move_native_default(h.engine, LATE_END))
    store = RecordingStore(h.directory / "records", fail_at={"complete"})

    result = _q3_stage(h, record_store=store)

    record = result.record
    assert "record_completion_failed" in record.secondary_failures
    assert record.persist_error
    assert record.primary_failure == (
        "q3_native_default_changed:default_pool_changed:serverPool.end"
    )
    # The last successful write already carried all three readings.
    assert [item.label for item in h.durable().native_default_pool] == DEFAULT_LABELS
    assert h.durable().native_default_pool[2].pools[0]["end"] == LATE_END


def test_a_failed_reading_write_keeps_the_primary_cause_and_finalizes(harness):
    """A02-E1: a store failure at the last reading is evidence, not a new cause."""
    h = harness(NATIVE_DEFAULT_MOVES)
    watcher = _watch(h)
    store = RecordingStore(
        h.directory / "records", fail_at={"native_default:before_cleanup"}
    )

    result = _q3_stage(h, record_store=store)

    record = result.record
    assert record.primary_failure == (
        "q3_native_default_changed:default_pool_changed:serverPool.end"
    )
    assert "persist_error:native_default:before_cleanup" in record.limitations
    assert record.persist_error
    assert watcher.reads == 3
    assert [item.label for item in record.native_default_pool] == DEFAULT_LABELS
    assert record.restoration_proven is True
    assert h.engine.snapshot()["devices"] == []


@pytest.mark.parametrize(
    ("options", "cause"),
    [
        ({"lose": 3}, "dhcp_server_baseline_unobserved:stub_response_lost"),
        ({"corrupt": 3}, "default_pool_snapshot_inventory_incoherent"),
    ],
    ids=["lost_answer", "incoherent_inventory"],
)
def test_an_unusable_final_reading_is_recorded_as_not_observed(harness, options, cause):
    """A02-E1: the record says what the last reading could not establish."""
    h = harness(NATIVE_DEFAULT_MOVES)
    _watch(h, **options)

    result = _q3_stage(h)

    record = result.record
    last = record.native_default_pool[-1]
    assert (last.label, last.observed, last.cause) == ("before_cleanup", False, cause)
    assert last.purpose == "q3:native_default:before_cleanup"
    assert record.primary_failure == (
        "q3_native_default_changed:default_pool_changed:serverPool.end"
    )
    assert f"native_default:before_cleanup:{cause}" in record.secondary_failures
    assert record.restoration_proven is True


def test_an_unaffordable_final_reading_is_stated_and_never_dispatched(harness):
    """A02-E1: no operation is added to the stage to repair the record."""
    clock = FakeClock()
    h = harness(NATIVE_DEFAULT_MOVES)
    watcher = _watch(
        h, hook_after=2, hook=lambda: setattr(clock, "now", clock.now + 1100.0)
    )

    result = _q3_stage(h, clock=clock)

    record = result.record
    assert watcher.reads == 2
    last = record.native_default_pool[-1]
    assert [item.label for item in record.native_default_pool] == DEFAULT_LABELS
    assert (last.observed, last.cause) == (
        False,
        "default_pool_snapshot_not_affordable",
    )
    assert (last.operation_seq, last.pools, last.raw) == (0, [], {})
    assert [
        item.purpose
        for item in record.operations
        if item.purpose == "q3:native_default:before_cleanup"
    ] == []
    assert record.primary_failure == (
        "q3_native_default_changed:default_pool_changed:serverPool.end"
    )
    assert record.restoration_proven is True


def test_q3_records_the_native_default_before_and_after_its_own_setup(harness):
    """F2: the snapshots bracket the setup and the intended pool is separate."""
    h = harness({"dhcp_default_pool": "native"})
    record, ledger = _q3_executor(h)
    assert record.primary_failure == "outcome_unknown:q3_product_service"
    assert ledger.used <= Q3.planned_minimum_operations == 59
    timing = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-6"
    )
    snapshots = timing.facts["native_default"]["snapshots"]
    assert [item["label"] for item in snapshots] == [
        "before_e5",
        "after_setup",
        "before_cleanup",
    ]
    assert {item["intended_pool_present"] for item in snapshots} == {False, True}
    assert timing.facts["native_default"]["differences"] == []
    # The projection is a view of the record's sink, not a second store.
    assert snapshots == [_snapshot_facts(item) for item in record.native_default_pool]
    assert [item.purpose for item in record.native_default_pool] == DEFAULT_PURPOSES
    assert all(item.operation_seq for item in record.native_default_pool)
    assert h.scripts("addPool") != []
    # The intended pool was created; the observed default was never touched.
    assert "serverPool" not in "".join(h.scripts("addPool"))
