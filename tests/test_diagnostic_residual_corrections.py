"""The residual corrections at `5db6916`, through the real components.

- R1: authority is decided at the dispatch that carries the effect, not once
  per finalization. The receiver is replaced at a TRANSPORT milestone here --
  after the first `removeDevice`, after a fixture creation, between a cleanup
  pre-readback and the delete that follows it -- and never at a count of
  authority callbacks, because counting those would place the injection
  inside the control under test.
- R3: the terminal read-only observation is part of guaranteed pre-cleanup
  finalization, so an ordinary Python exception raised out of the middle of
  the sequence cannot delete the fixtures without it.
- C1: a campaign claim this run could not release reaches the record before
  the record is completed, and the local authority reader waits a bounded
  time.

Nothing here observes Packet Tracer. These records are `offline_simulation`
and can never qualify a capability.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

import pytest
from service_qualification_engine import (
    FORWARDING_ROWS,
    SIM_BUILD,
    SIM_PROCESS_ID,
    SIM_PROCESS_INCARNATION,
    SIM_PROCESS_PATH,
    DiagnosticStageRun,
    FakeClock,
    MilestoneTransport,
    NodeEngine,
    NodeEngineTransport,
    RecordingStore,
    SwitchableLifecycle,
    authorization_args,
    request_args,
    stage,
)

from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    LedgeredTransport,
    OperationLedger,
    OperationRefused,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    LOCAL_OBSERVATION_TIMEOUT_SECONDS,
    STAGE_DEFINITIONS,
    BudgetRecord,
    DiagnosticLifecycleObservation,
    EnvironmentIdentity,
    ExecutionMode,
    MeasurementStatus,
    QualificationOutcome,
    QualificationRecord,
    QualificationStage,
    SourceIdentity,
    TransportIdentity,
    diagnostic_lifecycle_continuity,
    promotion_evidence_refusal,
)
from packet_tracer_mcp.infrastructure.execution.cp_scale_live_preflight import (
    PowerShellPacketTracerProcessReader,
)
from packet_tracer_mcp.infrastructure.execution.service_qualification_lifecycle import (
    PacketTracerDiagnosticLifecycleReader,
    PowerShellProcessIncarnationReader,
)
from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    CAMPAIGN_SUBDIR,
    LOCK_NAME,
    FileCampaignCoordinator,
)

#: `stage` is re-exported here as a pytest fixture, not as a call.
__all__ = ["stage"]

D_DHCP = STAGE_DEFINITIONS[QualificationStage.D_DHCP]
D_WEB = STAGE_DEFINITIONS[QualificationStage.D_WEB]
SWITCH = "__MCP_E6Q_SW"
SERVER = "__MCP_E6Q_SRV"

#: One coherent local pairing, in the shape a record stores it.
PAIRING = {
    "process_id": SIM_PROCESS_ID,
    "process_path": SIM_PROCESS_PATH,
    "product_version": SIM_BUILD,
    "file_version": "",
    "process_incarnation": SIM_PROCESS_INCARNATION,
    "mailbox_entries": [],
    "error": "",
}


def _paired(**overrides) -> DiagnosticLifecycleObservation:
    """Return the coherent local pairing a simulated authority binds."""
    values = {
        "process_id": SIM_PROCESS_ID,
        "process_path": SIM_PROCESS_PATH,
        "product_version": SIM_BUILD,
        "process_incarnation": SIM_PROCESS_INCARNATION,
    }
    values.update(overrides)
    return DiagnosticLifecycleObservation(**values)


def _stored(directory: Path) -> QualificationRecord:
    """Return the record exactly as the store last wrote it."""
    (path,) = list(directory.rglob("*.json"))
    return QualificationRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _sequence(record: QualificationRecord, needle: str) -> list[int]:
    """Return the counted operation numbers whose purpose contains `needle`."""
    return [
        item.seq for item in record.operations if item.seq and needle in item.purpose
    ]


class _RecordingChannel:
    """A channel that records what reached it, and reaches nothing else."""

    def __init__(self) -> None:
        """Start with nothing dispatched."""
        self.sent: list[str] = []

    def send(self, js_code: str) -> bool:
        """Record one fire-and-forget command."""
        self.sent.append(js_code)
        return True

    def send_and_wait(self, js_code: str, _timeout: float) -> str:
        """Record one correlated command."""
        self.sent.append(js_code)
        return "{}"

    def dispatch_and_wait(self, js_code: str, _timeout: float) -> None:
        """Record one typed dispatch."""
        self.sent.append(js_code)


# -- transport milestones ---------------------------------------------------------


def creates(name: str):
    """Match the script that creates one exact fixture."""
    return lambda script: f'lwAddDevice("{name}"' in script


def removes(name: str):
    """Match the destructive script that deletes one exact fixture."""
    marker = f'__cleanupName="{name}"'
    return lambda script: marker in script and "removeDevice" in script


def reads_back(name: str, *, occurrence: int):
    """Match the Nth plain identity read of one device.

    One run reads a device's identity exactly twice: once before it creates
    it, and once as the cleanup pre-readback, immediately before the delete.
    The inventory sweep and the spanning-tree query are different scripts and
    are excluded by shape, so `occurrence=2` is the pre-readback and nothing
    else.
    """
    seen: list[str] = []

    def matches(script: str) -> bool:
        if f'getDevice("{name}")' not in script or "getPortCount" not in script:
            return False
        if "getDeviceCount" in script or "spanning-tree" in script:
            return False
        seen.append(script)
        return len(seen) == occurrence

    return matches


# -- R1: the receiver is decided at each effect dispatch --------------------------


@pytest.fixture
def replaced_at(tmp_path):
    """Yield a D-WEB run whose Packet Tracer is replaced at a transport milestone.

    The replacement polls the same mailbox and already holds objects with this
    stage's exact fixture names and models, which is what makes an unchecked
    dispatch destructive rather than merely unattributable. Both the channel
    and the local pairing change at the same instant, because that is what one
    process being replaced by another looks like from here.
    """
    started: list[tuple[DiagnosticStageRun, NodeEngine]] = []
    snapshots: list[dict] = []

    def make(*, when, **overrides):
        index = len(started)
        directory = tmp_path / f"bound{index}"
        directory.mkdir()
        foreign_directory = tmp_path / f"foreign{index}"
        foreign_directory.mkdir()
        foreign = NodeEngine(
            foreign_directory,
            terminals=True,
            ping_reachable=True,
            stp_rows=dict(FORWARDING_ROWS),
        )
        for fixture in D_WEB.fixtures:
            foreign.seed_device(fixture.name, fixture.model)
        readings = SwitchableLifecycle(
            _paired(), _paired(process_id=SIM_PROCESS_ID + 7)
        )
        holder: dict = {}

        def replace() -> None:
            readings.switch()
            holder["transport"].target = NodeEngineTransport(foreign)

        def wrap(inner):
            holder["transport"] = MilestoneTransport(inner, when=when, after=replace)
            return holder["transport"]

        run = DiagnosticStageRun(
            directory,
            "D-WEB",
            {"stp_rows": dict(FORWARDING_ROWS)},
            diagnostic_lifecycle=readings,
            wrap_transport=wrap,
            **overrides,
        )
        started.append((run, foreign))
        run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        snapshots.append(
            {"bound": run.engine.snapshot(), "foreign": foreign.snapshot()}
        )
        return run, snapshots[-1], holder["transport"]

    yield make
    for run, foreign in started:
        run.close()
        foreign.close()


def _foreign_is_untouched(snapshot: dict) -> None:
    """Assert the replacement's workspace was neither deleted from nor mutated."""
    foreign = snapshot["foreign"]
    assert foreign["remove_calls"] == []
    assert {item["name"] for item in foreign["devices"]} == set(D_WEB.fixture_names)


def test_a_receiver_replaced_between_two_removals_deletes_nothing_further(replaced_at):
    """R1: the finalizer decides per removal, not once for all of them."""
    run, snapshot, _transport = replaced_at(when=removes(SWITCH))
    record = run.record()

    # The first removal was authorized and landed on the bound instance. It is
    # the only deletion that happened anywhere.
    assert snapshot["bound"]["remove_calls"] == [SWITCH]
    _foreign_is_untouched(snapshot)

    # The other three are named refusals with their cause, not silence.
    declined = {
        item.resource: item
        for item in record.releases
        if item.kind == "device" and item.outcome == "not_attempted"
    }
    assert set(declined) == {
        f"device:{name}" for name in D_WEB.fixture_names if name != SWITCH
    }
    assert all("execution_authority_lost" in item.detail for item in declined.values())
    refused = [item.refused for item in record.operations if item.refused]
    assert refused and all(
        item.startswith("execution_authority_lost:") for item in refused
    )
    assert record.restoration_proven is False
    assert "owned_cleanup_not_dispatched_to_an_unproven_receiver" in record.limitations
    assert run.exit_code == 1


def test_a_receiver_replaced_between_the_cleanup_read_and_the_delete_refuses(
    replaced_at,
):
    """R1: a pre-readback is not a licence for the dispatch that follows it."""
    run, snapshot, _transport = replaced_at(when=reads_back(SWITCH, occurrence=2))
    record = run.record()

    # The pre-readback was answered by the bound instance and the delete that
    # would have followed it never left this process.
    assert snapshot["bound"]["remove_calls"] == []
    _foreign_is_untouched(snapshot)
    assert [item.outcome for item in record.releases if item.kind == "device"] == [
        "not_attempted"
    ] * len(D_WEB.fixture_names)
    assert record.restoration_proven is False
    assert any(item.endswith("removal_not_attempted") for item in record.engine_residue)


def test_a_receiver_replaced_during_setup_stops_before_the_next_fixture(replaced_at):
    """R1: setup is effects too, and it happens before the first `begin`."""
    run, snapshot, _transport = replaced_at(when=creates(SERVER))
    record = run.record()

    # Exactly one fixture reached the bound workspace; nothing reached the
    # replacement, and nothing was deleted from either.
    assert {item["name"] for item in snapshot["bound"]["devices"]} == {SERVER}
    assert snapshot["bound"]["remove_calls"] == []
    _foreign_is_untouched(snapshot)
    assert record.primary_failure.startswith("execution_authority_lost")
    # No measurement ran, because setup never completed.
    assert all(item.status is not MeasurementStatus.RAN for item in record.measurements)
    assert run.exit_code == 1


def test_the_same_fixture_names_in_the_foreign_workspace_are_not_adopted(replaced_at):
    """R1: equal names and models are a collision, never permission."""
    run, snapshot, _transport = replaced_at(when=removes(SWITCH))

    # The replacement holds objects this run would recognise by name and
    # model. The gate refused before anything could act on that resemblance.
    devices = {item["name"]: item["model"] for item in snapshot["foreign"]["devices"]}
    assert devices == {item.name: item.model for item in D_WEB.fixtures}
    assert snapshot["foreign"]["remove_calls"] == []
    assert run.record().restoration_proven is False


def test_a_lost_campaign_claim_refuses_the_next_effect(tmp_path):
    """R1: the campaign claim is the other half, and it is read per dispatch."""
    directory = tmp_path / "unclaimed"
    directory.mkdir()
    lock = directory / CAMPAIGN_SUBDIR / LOCK_NAME
    run = DiagnosticStageRun(
        directory,
        "D-WEB",
        {"stp_rows": dict(FORWARDING_ROWS)},
        wrap_transport=lambda inner: MilestoneTransport(
            inner, when=removes(SWITCH), after=lock.unlink
        ),
    )
    try:
        run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        record = run.record()
        removed = run.engine.snapshot()["remove_calls"]
    finally:
        run.close()

    # One removal was authorized; the claim vanished behind it and the rest
    # were refused before dispatch.
    assert removed == [SWITCH]
    assert any(
        "campaign_claim:released_by_someone_else" in (item.refused or "")
        for item in record.operations
    )
    assert record.restoration_proven is False


def test_an_effect_scope_without_a_bound_guard_refuses_before_dispatch():
    """R1: a control that is absent cannot be satisfied, so nothing dispatches."""
    clock = FakeClock()
    ledger = OperationLedger(max_operations=10, max_seconds=100, clock=clock)
    channel = _RecordingChannel()
    bound = LedgeredTransport(ledger, channel, clock.sleep, clock)

    # A read outside any effect scope needs no guard and still works.
    assert bound.send_and_wait("read();", 1.0) == "{}"

    with pytest.raises(OperationRefused) as refused, ledger.effect_of("create:X"):
        bound.send_and_wait("mutate();", 1.0)

    assert refused.value.reason == "effect_guard_not_bound"
    assert channel.sent == ["read();"]
    assert [item.refused for item in ledger.entries if item.refused] == [
        "effect_guard_not_bound"
    ]


def test_a_clean_run_still_removes_what_it_owns(stage):
    """The positive control: authority held means cleanup happens as before."""
    run = stage("D-WEB")
    record = run.record()

    assert run.exit_code == 0
    assert sorted(run.engine.snapshot()["remove_calls"]) == sorted(D_WEB.fixture_names)
    assert record.restoration_proven is True
    assert record.engine_residue == []
    assert record.coordination_residue == []
    # The gate is declared for what it is, and never as an in-band fence.
    assert (
        "effect_gate_is_local_and_not_an_in_band_receiver_fence" in record.limitations
    )


# -- R3: the terminal observation is part of finalization -------------------------


class _StoreThatBreaks:
    """The real record store, with one ordinary exception at one boundary.

    A store is a real collaborator, and `_Run.transition` only ever expected a
    typed persistence error from it. Anything else escapes the stage sequence
    exactly the way a defect would, which is the path this correction had to
    make survivable. The engine stays perfectly readable throughout.
    """

    def __init__(self, inner, *, at: str) -> None:
        """Raise once, the first time `at` is the step being written."""
        self.inner = inner
        self.at = at
        self.raised = False

    def begin(self, record):
        """Delegate the opening write."""
        return self.inner.begin(record)

    def complete(self, record):
        """Delegate the terminal write."""
        return self.inner.complete(record)

    def attempt_exists(self, attempt_id: str) -> bool:
        """Delegate the attempt scan."""
        return self.inner.attempt_exists(attempt_id)

    def advance(self, record):
        """Break once at the named boundary, then behave normally."""
        if not self.raised and record.persisted_step == self.at:
            self.raised = True
            raise RuntimeError("injected_after_intervention")
        return self.inner.advance(record)


class _RaisesAfterVerifying:
    """A diagnostic web runtime whose fetch completes and then raises."""

    def __init__(self, inner) -> None:
        """Wrap the composed diagnostic service runtime."""
        self.inner = inner
        self.raised = False

    def inventory(self):
        """Delegate the inventory read."""
        return self.inner.inventory()

    def apply_actions(self, actions):
        """Delegate the application."""
        return self.inner.apply_actions(actions)

    def verify(self, expectation):
        """Run the whole owned client lifecycle, then fail the caller."""
        self.inner.verify(expectation)
        self.raised = True
        raise RuntimeError("injected_before_w5")


def test_an_exception_after_an_intermediate_dhcp_intervention_still_reads_d4(
    stage, tmp_path
):
    """R3: D4 is not the bottom of the sequence any more; it is finalization."""
    # The boundary write that follows the enable, which really was dispatched.
    store = _StoreThatBreaks(
        RecordingStore(tmp_path / "records"), at="experiment:D_DHCP_ENABLE:concluded"
    )
    run = stage("D-DHCP", record_store=store)
    engine = run.engine.snapshot()
    record = _stored(tmp_path / "records")

    # The fault actually fired, and it fired AFTER a real intervention: the
    # enable reached the engine before the exception left Python.
    assert store.raised is True
    assert engine["dhcp_setter_calls"]["setEnable"] == 1
    # The original error survives as the primary failure.
    assert record.primary_failure.startswith("exception:RuntimeError")
    assert "injected_after_intervention" in record.primary_failure
    enable = next(
        item for item in record.measurements if item.experiment_id == ("M-DDHCP-3")
    )
    assert enable.status is MeasurementStatus.RAN

    # The terminal reading was taken, exactly once, before any deletion.
    final = next(
        item for item in record.measurements if item.experiment_id == "M-DDHCP-4"
    )
    assert final.status is MeasurementStatus.RAN
    labels = [item.label for item in record.native_default_pool]
    assert labels.count("d4_before_cleanup") == 1
    terminal = _sequence(record, "d4_before_cleanup")
    removals = _sequence(record, "remove:")
    assert len(terminal) == 1
    assert removals and max(terminal) < min(removals)
    # It is still the cumulative summary, over the state the sequence had
    # reached when it raised.
    assert final.facts["d4_cumulative"]["span"] == "cumulative_baseline_to_final"
    assert run.exit_code == 1


def test_the_terminal_payload_is_its_own_and_survives_a_reload(stage, tmp_path):
    """R3: a reading taken from finalization is durable, not in-memory only."""
    store = _StoreThatBreaks(
        RecordingStore(tmp_path / "records"), at="experiment:D_DHCP_ENABLE:concluded"
    )
    # The sixth native reading is the terminal one on this path, and the stub
    # moves every non-intended pool exactly there, so the payload D4 stores
    # cannot be confused with any earlier snapshot.
    stage("D-DHCP", {"default_pool_drift_reads": 6}, record_store=store)
    record = _stored(tmp_path / "records")

    assert store.raised is True
    stored = record.native_default_pool
    assert [item.label for item in stored][-1] == "d4_before_cleanup"
    assert stored[-1].pools != stored[0].pools
    assert stored[-1].differences
    # The reading, its own operation identity and its difference list all came
    # back from the store, not from the object the run held in memory.
    assert stored[-1].operation_seq
    assert not [
        item for item in record.limitations if item.startswith("terminal_observation_")
    ]


def test_an_exception_before_w5_still_reads_the_after_boundaries(stage, tmp_path):
    """R3: the same hole in D-WEB, with the engine perfectly readable."""
    from packet_tracer_mcp.adapters.cli.service_qualification import (
        production_boundaries,
    )

    base = production_boundaries(tmp_path / "unused")
    proxies: list[_RaisesAfterVerifying] = []

    def diagnostic_service_runtime(bound, allowance):
        assert base.diagnostic_service_runtime is not None
        proxy = _RaisesAfterVerifying(base.diagnostic_service_runtime(bound, allowance))
        proxies.append(proxy)
        return proxy

    run = stage("D-WEB", diagnostic_service_runtime=diagnostic_service_runtime)
    removed = sorted(run.engine.snapshot()["remove_calls"])
    record = run.record()
    (proxy,) = proxies

    assert proxy.raised is True
    assert record.primary_failure.startswith("exception:RuntimeError")
    assert "injected_before_w5" in record.primary_failure

    after = run.measurement("M-DWEB-5")
    assert after.status is MeasurementStatus.RAN
    assert after.facts["listeners_after"]["observed"] is True
    assert "forwarding_after" in after.facts
    # Taken once, and before the first deletion.
    listeners = _sequence(record, "d-web:listeners:after")
    removals = _sequence(record, "remove:")
    assert len(listeners) == 1
    assert removals and max(listeners) < min(removals)
    started = [
        item.step
        for item in record.transitions
        if item.step == "experiment:D_WEB_AFTER:started"
    ]
    assert len(started) == 1
    # Cleanup still happened: a terminal reading is not a reason to leave
    # fixtures behind.
    assert removed == sorted(D_WEB.fixture_names)


def test_a_failing_terminal_reader_keeps_the_error_and_still_cleans_up(
    stage, monkeypatch
):
    """R3: a defect in the last reading is secondary to what stopped the run."""
    from packet_tracer_mcp.application.use_cases import qualify_server_services as uc

    def explode(_execution, _state):
        raise RuntimeError("terminal_reader_defect")

    monkeypatch.setattr(uc, "_d_web_after", explode)
    # An owned client whose release refuses leaves an unresolved effect, so
    # the run already has a primary failure of its own.
    run = stage("D-WEB", {"delete_client_throws": True})
    removed = sorted(run.engine.snapshot()["remove_calls"])
    record = run.record()

    assert record.primary_failure.startswith("outcome_unknown:fetch_client")
    assert "terminal_reader_defect" not in record.primary_failure
    assert (
        "terminal_observation:D_WEB_AFTER:exception:RuntimeError"
        in record.secondary_failures
    )
    after = run.measurement("M-DWEB-5")
    assert after.status is MeasurementStatus.NOT_RUN
    assert after.reason == "not_observed:exception:RuntimeError"
    # Owned cleanup is not the terminal reader's dependant.
    assert removed == sorted(D_WEB.fixture_names)


def test_a_cancelled_run_declares_its_terminal_reading_not_taken(
    tmp_path, capsys, monkeypatch
):
    """R3: cancellation stops work; it does not restart or re-dispatch any."""
    from packet_tracer_mcp.application.use_cases import qualify_server_services as uc

    def interrupt(_execution, _state):
        raise KeyboardInterrupt

    monkeypatch.setattr(uc, "_d_web_fetch", interrupt)
    directory = tmp_path / "cancelled"
    directory.mkdir()
    run = DiagnosticStageRun(directory, "D-WEB", {"stp_rows": dict(FORWARDING_ROWS)})
    try:
        exit_code = run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        capsys.readouterr()
        record = run.record()
        removed = sorted(run.engine.snapshot()["remove_calls"])
    finally:
        run.close()

    # The adapter reports the cancellation as such and invents no outcome.
    assert exit_code == 130
    assert record.primary_failure == "cancelled"
    after = run.measurement("M-DWEB-5")
    assert after.status is MeasurementStatus.NOT_RUN
    assert after.reason == "not_observed:cancelled"
    # Nothing was restarted: the fetch never spent an operation, and the
    # terminal reading was declared rather than dispatched.
    assert not _sequence(record, "d-web:fetch:http")
    assert not _sequence(record, "d-web:listeners:after")
    assert run.measurement("M-DWEB-4").status is not MeasurementStatus.RAN
    # Owned cleanup still ran, which is the only thing a cancelled run owes.
    assert removed == sorted(D_WEB.fixture_names)


def test_an_intermediate_dhcp_failure_states_which_path_it_took(stage):
    """The conditional guard this test used to carry proved nothing."""
    stopped = stage("D-DHCP", {"dhcp_default_pool": "arbitrary"})
    record = stopped.record()

    # The intended failing path is asserted, not assumed: an unreviewed native
    # default is not an admissible baseline, so the sequence stops at D0.
    assert record.primary_failure == (
        "d_dhcp_baseline_not_established:initial_dhcp_server_state_not_admissible"
    )
    assert stopped.measurement("M-DDHCP-0").conclusion.value == "inconclusive"
    assert [
        stopped.measurement(item).status
        for item in ("M-DDHCP-1", "M-DDHCP-2", "M-DDHCP-3")
    ] == [MeasurementStatus.NOT_RUN] * 3
    # And the terminal reading is still taken, which is the whole point.
    assert stopped.measurement("M-DDHCP-4").status is MeasurementStatus.RAN
    assert [item.label for item in record.native_default_pool][-1] == (
        "d4_before_cleanup"
    )


# -- C1: local finalization results, and bounded local readers --------------------


class _CoordinatorThatCannotRelease:
    """The real coordinator, with its release refused or broken on purpose."""

    def __init__(self, inner, *, reasons=(), raises=False) -> None:
        """Wrap one real coordinator and script only its release."""
        self.inner = inner
        self.reasons = tuple(reasons)
        self.raises = raises
        self.releases = 0

    @property
    def scope(self):
        """Delegate the coordination directory."""
        return self.inner.scope

    def claim(self, *, attempt_id):
        """Take the real claim."""
        return self.inner.claim(attempt_id=attempt_id)

    def verify(self, claim):
        """Answer the real verification."""
        return self.inner.verify(claim)

    def release(self, claim):
        """Fail to release, either by reason or by raising."""
        self.releases += 1
        if self.raises:
            raise OSError("release_exploded")
        return self.reasons


def _coordinator(directory: Path, **kwargs) -> _CoordinatorThatCannotRelease:
    """Return the production coordinator for this run, with a broken release."""
    return _CoordinatorThatCannotRelease(
        FileCampaignCoordinator(directory / "campaign"), **kwargs
    )


def test_a_failed_campaign_release_is_a_visible_durable_finalization_failure(
    tmp_path, capsys
):
    """C1: a lock the next campaign will hit cannot be a silent discard."""
    directory = tmp_path / "held"
    directory.mkdir()
    coordinator = _coordinator(
        directory, reasons=("campaign_claim:release_unverified",)
    )
    run = DiagnosticStageRun(
        directory,
        "D-WEB",
        {"stp_rows": dict(FORWARDING_ROWS)},
        campaign_coordinator=coordinator,
    )
    try:
        exit_code = run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        record = run.record()
    finally:
        run.close()

    # The claim was released exactly once, inside the run, and it failed.
    assert coordinator.releases == 1
    assert (directory / CAMPAIGN_SUBDIR / LOCK_NAME).exists()
    # It is durable, visible in the record and in the operator's summary.
    assert record.coordination_residue == ["campaign_claim:release_unverified"]
    assert "campaign_release:campaign_claim:release_unverified" in (
        record.secondary_failures
    )
    assert [item.resource for item in record.releases if item.kind == "claim"] == [
        "campaign:lock"
    ]
    assert summary["coordination_residue"] == ["campaign_claim:release_unverified"]
    # And it keeps the run from claiming a complete, clean handoff.
    assert record.outcome is QualificationOutcome.STOPPED
    assert exit_code == 1
    # Engine restoration stays its own fact: the workspace WAS restored.
    assert record.restoration_proven is True
    assert record.engine_residue == []


def test_a_raising_release_is_recorded_rather_than_lost(tmp_path, capsys):
    """C1: the finalization path still never raises, and still never forgets."""
    directory = tmp_path / "exploded"
    directory.mkdir()
    coordinator = _coordinator(directory, raises=True)
    run = DiagnosticStageRun(
        directory,
        "D-WEB",
        {"stp_rows": dict(FORWARDING_ROWS)},
        campaign_coordinator=coordinator,
    )
    try:
        exit_code = run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        capsys.readouterr()
        record = run.record()
    finally:
        run.close()

    assert record.coordination_residue == ["campaign_release_failed:OSError"]
    assert record.restoration_proven is True
    assert exit_code == 1


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('{"holder": "someone-else", "attempt_id": "x"}', "held_by_another_writer"),
        ("{not json at all", "malformed"),
    ],
)
def test_a_claim_that_is_no_longer_ours_is_reported_and_never_deleted(
    tmp_path, capsys, payload, expected
):
    """C1: another holder's file is evidence, not something to clean up."""
    directory = tmp_path / "foreign"
    directory.mkdir()
    lock = directory / CAMPAIGN_SUBDIR / LOCK_NAME

    def overwrite() -> None:
        lock.write_text(payload, encoding="utf-8")

    run = DiagnosticStageRun(
        directory,
        "D-WEB",
        {"stp_rows": dict(FORWARDING_ROWS)},
        # The last owned removal has already been dispatched, so what this
        # changes is the release and nothing the engine evidence rests on.
        wrap_transport=lambda inner: MilestoneTransport(
            inner, when=removes(SERVER), after=overwrite
        ),
    )
    try:
        run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        capsys.readouterr()
        record = run.record()
        removed = sorted(run.engine.snapshot()["remove_calls"])
    finally:
        run.close()

    # The file is exactly as it was found, and the attempt marker is intact.
    assert lock.read_text(encoding="utf-8") == payload
    markers = sorted(
        item.name for item in (directory / CAMPAIGN_SUBDIR).glob("attempt-*.json")
    )
    assert len(markers) == 1
    # The run says what it could not finalize, and it did restore the engine.
    assert any(expected in item for item in record.coordination_residue)
    assert record.restoration_proven is True
    assert removed == sorted(D_WEB.fixture_names)


def test_coordination_residue_blocks_promotion_on_its_own():
    """C1: a retained lock is not a complete-clean handoff to the next run."""
    record = QualificationRecord(
        run_id="r",
        stage=QualificationStage.D_WEB,
        execution_mode=ExecutionMode.LIVE,
        created_at=datetime.datetime(2026, 9, 20, tzinfo=datetime.UTC),
        source=SourceIdentity(executed_sha="a" * 40, clean=True),
        environment=EnvironmentIdentity(observed_build=SIM_BUILD),
        transport=TransportIdentity(channel="file"),
        diagnostic_lifecycle=dict(PAIRING),
        diagnostic_lifecycle_postflight=dict(PAIRING),
        budget=BudgetRecord(
            max_operations=80,
            max_seconds=1800,
            reserve_operations=10,
            reserve_seconds=300,
            planned_minimum_operations=74,
        ),
        outcome=QualificationOutcome.COMPLETED,
        restoration_proven=True,
    )
    promotable = {
        "stage": QualificationStage.D_WEB,
        "executed_sha": "a" * 40,
        "build": SIM_BUILD,
        "channel": "file",
    }

    # The control first: without the residue this record is promotable.
    assert promotion_evidence_refusal(record, **promotable) == ""

    record.coordination_residue = ["campaign_claim:release_unverified"]
    assert "coordination scope" in promotion_evidence_refusal(record, **promotable)


# -- C1: the local reader waits a bounded time ------------------------------------


def test_the_incarnation_reader_bounds_its_local_observation():
    """C1: zero bridge operations is not a bound on wall-clock time."""
    seen: list[dict] = []

    def run_command(argv, **kwargs):
        seen.append(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="2026-09-20T09:15:00\n")

    reader = PowerShellProcessIncarnationReader(run_command=run_command)
    assert reader.read(4242) == "2026-09-20T09:15:00"
    assert seen[0]["timeout"] == LOCAL_OBSERVATION_TIMEOUT_SECONDS

    PowerShellProcessIncarnationReader(
        run_command=run_command, timeout_seconds=1.5
    ).read(4242)
    assert seen[1]["timeout"] == 1.5


def test_an_incarnation_timeout_is_unobservable_authority(tmp_path):
    """C1: an expired wait is a loss, never a quiet unknown that passes."""
    from packet_tracer_mcp.application.cp_scale_live.admission import (
        CPScaleProcessObservation,
    )
    from packet_tracer_mcp.application.cp_scale_live.contracts import (
        CPScaleProcessRecord,
    )

    def run_command(argv, **_kwargs):
        raise subprocess.TimeoutExpired(argv, LOCAL_OBSERVATION_TIMEOUT_SECONDS)

    reader = PowerShellProcessIncarnationReader(run_command=run_command)
    with pytest.raises(subprocess.TimeoutExpired):
        reader.read(4242)

    class _OneProcess:
        """A process reader that answers with the authorized instance."""

        def read(self):
            """Return one Packet Tracer process."""
            return CPScaleProcessObservation(
                processes=(
                    CPScaleProcessRecord(
                        pid=SIM_PROCESS_ID,
                        name="PacketTracer",
                        main_window_handle=1,
                        product_version=SIM_BUILD,
                        file_version=SIM_BUILD,
                        executable_path=SIM_PROCESS_PATH,
                    ),
                ),
            )

    observed = PacketTracerDiagnosticLifecycleReader(
        process_reader=_OneProcess(),
        mailbox_dir=tmp_path / "mailbox",
        incarnation_reader=reader,
    ).read()

    assert observed.error == "process_incarnation_unreadable:TimeoutExpired"
    assert diagnostic_lifecycle_continuity(_paired(), observed) == (
        "process_instance:unobservable:process_incarnation_unreadable:TimeoutExpired",
    )


def test_an_unreadable_incarnation_is_still_an_empty_unknown():
    """C1: only the timeout changed; every other failure keeps its semantics."""

    def run_command(_argv, **_kwargs):
        raise OSError("powershell is missing")

    assert PowerShellProcessIncarnationReader(run_command=run_command).read(4242) == ""


def test_the_process_reader_bound_is_opt_in_for_every_other_caller():
    """C1: the shared CP-scale reader keeps the wait it has always had."""
    seen: list[dict] = []

    def run_command(argv, **kwargs):
        seen.append(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="")

    PowerShellPacketTracerProcessReader(run_command=run_command).read()
    assert "timeout" not in seen[0]

    PowerShellPacketTracerProcessReader(
        run_command=run_command, timeout_seconds=LOCAL_OBSERVATION_TIMEOUT_SECONDS
    ).read()
    assert seen[1]["timeout"] == LOCAL_OBSERVATION_TIMEOUT_SECONDS


def test_the_record_reports_what_the_local_observations_cost(stage):
    """C1: the phase is charged for the time its authority readings spend."""
    clock = FakeClock()

    def lifecycle():
        # Every local reading costs the phase real time, whatever it costs
        # the operation ledger, which is nothing.
        clock.now += 0.5
        return _paired()

    run = stage("D-WEB", diagnostic_lifecycle=lifecycle, clock=clock)
    record = run.record()

    assert record.budget.local_observation_seconds > 0
    assert record.budget.local_observation_seconds <= record.budget.elapsed_seconds
    assert any(
        item.startswith("local_process_observation_bounded_seconds:")
        for item in record.limitations
    )
