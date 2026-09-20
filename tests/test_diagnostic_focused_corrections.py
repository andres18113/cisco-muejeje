"""The four focused corrections at `ab668d7`, through the real components.

Each finding is reproduced against the coordinator, the product runtimes, the
record store and the Node engine stub rather than against an isolated model of
them, because a countermodel shows that a defect is possible and only the real
composition shows that it is present.

- GF-R1: a foreign effect is prevented, not reported afterwards.
- GF-R2: an operational precondition is not an experimental conclusion.
- GF-R3: a terminal observation belongs to the run, not to its success.
- GF-R4: a budget is the worst case of the composed path.

Nothing here observes Packet Tracer. These records are `offline_simulation`
and can never qualify a capability.
"""

from __future__ import annotations

import pytest
from service_qualification_engine import (
    FORWARDING_ROWS,
    SIM_PROCESS_ID,
    SIM_PROCESS_INCARNATION,
    SIM_PROCESS_PATH,
    DiagnosticStageRun,
    FakeClock,
    NodeEngine,
    NodeEngineTransport,
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
    D_WEB_FORWARDING_SAMPLE_CALLS,
    D_WEB_PING_INSPECTIONS,
    STAGE_DEFINITIONS,
    DiagnosticLifecycleObservation,
    MeasurementConclusion,
    MeasurementStatus,
    QualificationStage,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    ACCESS_FORWARDING_SAMPLE_CALLS,
    PacketTracerEnterpriseConfigurationRuntime,
)
from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    CampaignClaim,
    CampaignCoordinationError,
    FileCampaignCoordinator,
)

#: `stage` is re-exported here as a pytest fixture, not as a call.
__all__ = ["stage"]

D_DHCP = STAGE_DEFINITIONS[QualificationStage.D_DHCP]
D_WEB = STAGE_DEFINITIONS[QualificationStage.D_WEB]
ATTEMPT_A = "a" * 32
ATTEMPT_B = "b" * 32

#: Which reading of the local pairing a run is at, counted from the preflight:
#: one before the transport, one before each of D-WEB's six procedures, one
#: before owned cleanup and one afterwards.
FIRST_EFFECT = 2
BEFORE_FIRST_REMOVAL = 8


def _paired(**overrides) -> DiagnosticLifecycleObservation:
    """Return the coherent local pairing a simulated authority binds."""
    values = {
        "process_id": SIM_PROCESS_ID,
        "process_path": SIM_PROCESS_PATH,
        "product_version": "9.0.1.0858",
        "process_incarnation": SIM_PROCESS_INCARNATION,
    }
    values.update(overrides)
    return DiagnosticLifecycleObservation(**values)


class _PairingSequence:
    """The pairing a run observes, and what changes when it stops matching.

    `at` is the 1-based reading from which `replacement` answers, so a test
    places the loss exactly where it means to: at the first effect, mid-run,
    or immediately before the first removal. `on_switch` runs once at that
    reading, which is how a test also moves the mailbox to the engine the
    replacement is actually serving.
    """

    def __init__(self, replacement, *, at: int, on_switch=None) -> None:
        """Bind the replacement reading to the moment it starts answering."""
        self.replacement = replacement
        self.at = at
        self.on_switch = on_switch
        self.calls = 0

    def __call__(self) -> DiagnosticLifecycleObservation:
        """Return this reading, switching the instance when the moment comes."""
        self.calls += 1
        if self.calls == self.at and self.on_switch is not None:
            self.on_switch()
        return self.replacement if self.calls >= self.at else _paired()


# -- GF-R1: a foreign effect is prevented ----------------------------------------


def test_a_second_campaign_writer_is_refused_by_the_shared_scope(tmp_path):
    """Two checkouts share the mailbox, never each other's record directory."""
    scope = tmp_path / "scope"
    first = FileCampaignCoordinator(scope)
    held = first.claim(attempt_id=ATTEMPT_A)

    # A different checkout, a different store, a different attempt identity:
    # what it cannot have is the campaign.
    with pytest.raises(CampaignCoordinationError) as refused:
        FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT_B)
    assert "campaign_already_claimed" in str(refused.value)

    # The refusal leaves the holder's claim exactly as it found it.
    assert held.lock_path.exists()
    assert first.verify(held) == ()
    assert first.release(held) == ()
    assert not held.lock_path.exists()


def test_one_attempt_identity_cannot_be_reserved_twice(tmp_path):
    """The reservation is atomic, and an identity stays spent after release."""
    scope = tmp_path / "scope"
    coordinator = FileCampaignCoordinator(scope)
    claim = coordinator.claim(attempt_id=ATTEMPT_A)
    assert coordinator.release(claim) == ()

    # The campaign is free again. The attempt is not: a new SHA, a new
    # process or a new run does not create an attempt identity.
    with pytest.raises(CampaignCoordinationError) as refused:
        FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT_A)
    assert "campaign_attempt_already_reserved" in str(refused.value)
    assert claim.attempt_path.exists()


def test_a_contended_attempt_does_not_leave_the_campaign_held(tmp_path):
    """A writer refused the attempt releases the lock it had just taken."""
    scope = tmp_path / "scope"
    first = FileCampaignCoordinator(scope)
    spent = first.claim(attempt_id=ATTEMPT_A)
    assert first.release(spent) == ()

    with pytest.raises(CampaignCoordinationError):
        FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT_A)

    # The next writer with a fresh identity is admitted, which it could not
    # be if the refused one had left the campaign locked behind it.
    claim = FileCampaignCoordinator(scope).claim(attempt_id=ATTEMPT_B)
    assert claim.lock_path.exists()


def test_a_claim_is_never_reclaimed_by_age_or_guesswork(tmp_path):
    """An owner that is still running looks exactly like one that died."""
    scope = tmp_path / "scope"
    coordinator = FileCampaignCoordinator(scope)
    held = coordinator.claim(attempt_id=ATTEMPT_A)

    # Another writer's view of the same claim: it is not theirs, so their
    # release removes nothing and names what it declined to touch.
    foreign = FileCampaignCoordinator(scope)
    mistaken = CampaignClaim(
        scope=held.scope,
        lock_path=held.lock_path,
        attempt_path=held.attempt_path,
        holder="f" * 32,
        attempt_id=ATTEMPT_A,
    )
    assert foreign.verify(mistaken) == ("campaign_claim:held_by_another_writer",)
    assert foreign.release(mistaken) == (
        "campaign_release_skipped:campaign_claim:held_by_another_writer",
    )
    assert held.lock_path.exists()


def test_a_held_campaign_refuses_the_run_before_any_contact(stage, tmp_path):
    """Exclusion is admission, not a note in the record of what already ran."""
    scope = tmp_path / "shared-scope"
    FileCampaignCoordinator(scope).claim(attempt_id="c" * 32)

    run = stage("D-WEB", campaign_coordinator=FileCampaignCoordinator(scope))

    # A refusal proven to precede every remote effect: no channel was opened,
    # no command was dispatched, and the workspace is untouched.
    assert run.exit_code == 2
    assert run.opened == []
    assert run.transport.calls == []
    assert run.engine.snapshot()["devices"] == []
    assert list((run.directory / "records").rglob("*.json")) == []


class _SwitchableTransport:
    """One mailbox answered by one engine, then by its replacement."""

    def __init__(self, target) -> None:
        """Start on the engine the run was admitted against."""
        self.target = target
        self.calls: list[tuple[str, str]] = []

    def send(self, js_code: str) -> bool:
        """Queue one command on whichever engine answers now."""
        self.calls.append(("send", js_code))
        return self.target.send(js_code)

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        """Dispatch one command on whichever engine answers now."""
        self.calls.append(("send_and_wait", js_code))
        return self.target.send_and_wait(js_code, timeout)

    def dispatch_and_wait(self, js_code: str, timeout: float):
        """Dispatch with typed facts on whichever engine answers now."""
        self.calls.append(("dispatch_and_wait", js_code))
        return self.target.dispatch_and_wait(js_code, timeout)


@pytest.fixture
def replaced_run(tmp_path):
    """Yield a D-WEB run whose Packet Tracer is replaced at one exact reading.

    The replacement polls the same mailbox, so the transport starts answering
    from a second engine at the same instant the pairing stops matching. That
    second workspace already holds objects with this stage's exact fixture
    names and models, which is what makes an unchecked removal destructive
    rather than merely unattributable.
    """
    started: list[tuple[DiagnosticStageRun, NodeEngine]] = []

    def make(*, at: int):
        index = len(started)
        directory = tmp_path / f"replaced{index}"
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
        readings = _PairingSequence(_paired(process_id=SIM_PROCESS_ID + 7), at=at)
        run = DiagnosticStageRun(
            directory,
            "D-WEB",
            {"stp_rows": dict(FORWARDING_ROWS)},
            diagnostic_lifecycle=readings,
        )
        started.append((run, foreign))
        switchable = _SwitchableTransport(run.transport)
        run.transport = switchable
        readings.on_switch = lambda: setattr(
            switchable, "target", NodeEngineTransport(foreign)
        )
        run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        return run, foreign, readings

    yield make
    for run, foreign in started:
        run.close()
        foreign.close()


def test_a_replacement_before_the_first_removal_deletes_nothing(replaced_run):
    """GF-R1: an unproven receiver is not deleted from and then reported on."""
    run, foreign, readings = replaced_run(at=BEFORE_FIRST_REMOVAL)
    record = run.record()

    # The run completed its work, so there was something to remove.
    assert readings.calls >= BEFORE_FIRST_REMOVAL
    # Nothing at all was removed, in either workspace.
    assert foreign.snapshot()["remove_calls"] == []
    assert {item["name"] for item in foreign.snapshot()["devices"]} == set(
        D_WEB.fixture_names
    )
    assert run.engine.snapshot()["remove_calls"] == []
    # And the record names every removal it declined, with its cause.
    assert record.restoration_proven is False
    devices = [item for item in record.releases if item.kind == "device"]
    assert devices and all(item.outcome == "not_attempted" for item in devices)
    assert any(
        item.endswith("removal_refused_unproven_receiver")
        for item in record.engine_residue
    )
    assert "owned_cleanup_not_dispatched_to_an_unproven_receiver" in record.limitations
    assert run.exit_code == 1


def test_a_second_packet_tracer_mid_run_stops_before_the_next_effect(replaced_run):
    """A replacement is a primary failure at the next effect, not a footnote."""
    run, foreign, _readings = replaced_run(at=FIRST_EFFECT)
    record = run.record()

    assert record.primary_failure.startswith("execution_authority_lost")
    # No procedure announced itself, so no effect followed the replacement.
    assert not [item for item in record.operations if item.purpose.startswith("d-web:")]
    assert foreign.snapshot()["remove_calls"] == []
    assert record.restoration_proven is False
    assert run.exit_code == 1


def test_a_reused_pid_at_the_authorized_path_is_not_the_bound_process(stage):
    """A PID names a slot; the creation identity names the process in it."""
    readings = _PairingSequence(
        _paired(process_incarnation="2026-09-20T11:00:00.0000000+00:00"),
        at=FIRST_EFFECT,
    )
    run = stage("D-WEB", diagnostic_lifecycle=readings)
    record = run.record()

    assert "process_instance:changed" in record.engine_residue
    assert record.primary_failure.startswith("execution_authority_lost")
    assert record.restoration_proven is False
    assert run.engine.snapshot()["remove_calls"] == []


def test_an_unobserved_incarnation_is_refused_before_a_transport(stage):
    """Unknown is not a match, so an unbindable process is never bound."""
    run = stage("D-WEB", diagnostic_lifecycle=lambda: _paired(process_incarnation=""))

    assert run.exit_code == 2
    assert run.opened == []
    assert run.transport.calls == []


def test_a_clean_run_still_removes_what_it_owns(stage):
    """The positive control: authority held means cleanup happens as before."""
    run = stage("D-WEB")
    record = run.record()

    assert run.exit_code == 0
    assert sorted(run.engine.snapshot()["remove_calls"]) == sorted(D_WEB.fixture_names)
    assert record.restoration_proven is True
    assert record.engine_residue == []


# -- GF-R2: an operational precondition is not a conclusion ----------------------


def test_a_coherent_change_at_d1_does_not_stop_d2_or_d3(stage):
    """GF-R2: the dependent variable cannot disqualify its own continuation."""
    run = stage("D-DHCP", {"default_pool_drift_reads": 3})
    record = run.record()

    d1 = run.measurement("M-DDHCP-1")
    assert d1.status is MeasurementStatus.RAN
    assert d1.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    # The negative finding is kept negative and is never relabelled.
    assert any(item.startswith("native_default_changed:") for item in d1.causes)
    # And the interventions that depend on the state D1 established still ran.
    for experiment_id in ("M-DDHCP-2", "M-DDHCP-3", "M-DDHCP-4"):
        assert run.measurement(experiment_id).status is MeasurementStatus.RAN
    assert record.primary_failure == ""
    assert run.exit_code == 0


def test_a_coherent_change_at_d2_does_not_stop_the_enable(stage):
    """The pool interval is a finding; the activation still has its state."""
    run = stage("D-DHCP", {"default_pool_drift_reads": 4})

    assert run.measurement("M-DDHCP-2").conclusion is (
        MeasurementConclusion.NEGATIVE_OBSERVED
    )
    assert run.measurement("M-DDHCP-3").status is MeasurementStatus.RAN
    assert run.measurement("M-DDHCP-4").status is MeasurementStatus.RAN
    assert run.engine.snapshot()["dhcp_setter_calls"]["setEnable"] == 1


def test_a_coherent_change_at_the_enable_is_the_finding_itself(stage):
    """D3's interval is what the whole stage exists to observe."""
    run = stage("D-DHCP", {"default_pool_change_on_enable": {"end": "0.0.9.9"}})

    d3 = run.measurement("M-DDHCP-3")
    assert d3.status is MeasurementStatus.RAN
    assert d3.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert run.measurement("M-DDHCP-4").status is MeasurementStatus.RAN


def test_every_adjacent_observation_survives_a_reload(stage):
    """Evidence that is not durable is not evidence a later review can cite."""
    run = stage("D-DHCP", {"default_pool_drift_reads": 3})
    record = run.record()

    assert [item.label for item in record.native_default_pool] == [
        "d0_baseline",
        "d0_control",
        "d1_after_server_address",
        "d2_after_pool",
        "d3_after_enable",
        "d4_before_cleanup",
    ]
    assert all(item.observed for item in record.native_default_pool)


def test_the_stage_touches_no_client_and_no_native_default_setter(stage):
    """A negative finding never buys a wider effect than the stage declares."""
    run = stage("D-DHCP", {"default_pool_drift_reads": 3})
    snapshot = run.engine.snapshot()

    assert snapshot["dhcp_runs"] == []
    assert snapshot["dhcp_setter_calls"]["setDhcpFlag"] == 0
    assert not [
        port
        for device in snapshot["devices"]
        for port in device["ports"]
        if port["dhcp_mode"]
    ]
    # Exactly one pool was added, and the stage named the intended one:
    # the fixtures are gone by now, so the durable evidence is the
    # setter count and the record, not a post-cleanup snapshot.
    assert snapshot["dhcp_setter_calls"]["addPool"] == 1
    pool = run.measurement("M-DDHCP-2").facts["e6_pool"]
    assert pool["expected_enabled"] is False
    assert pool["verification"] is not None


def test_autonomous_drift_still_stops_every_later_effect(stage):
    """An operational rule is not a looser rule: drift still closes the run."""
    run = stage("D-DHCP", {"default_pool_drift_reads": 2})
    record = run.record()

    assert run.measurement("M-DDHCP-0").conclusion is (
        MeasurementConclusion.CONTRADICTED
    )
    assert run.measurement("M-DDHCP-1").status is MeasurementStatus.NOT_RUN
    assert run.engine.snapshot()["dhcp_setter_calls"]["addPool"] == 0
    assert record.primary_failure != ""
    # GF-R3: what the run left behind is still read. The stop is the
    # reason to take the terminal reading, not a reason to skip it.
    assert run.measurement("M-DDHCP-4").status is MeasurementStatus.RAN
    assert [item.label for item in record.native_default_pool][-1] == (
        "d4_before_cleanup"
    )


def test_an_unready_fixture_still_blocks_the_first_intervention(stage):
    """A precondition that was never observed is not a precondition met."""
    run = stage("D-DHCP", {"ports_up": False, "protocol_up": False})
    record = run.record()

    assert run.measurement("M-DDHCP-1").status is MeasurementStatus.NOT_RUN
    assert run.measurement("M-DDHCP-1").reason.startswith(
        ("stopped:", "operational_precondition_unmet:")
    )
    assert run.engine.snapshot()["dhcp_setter_calls"]["addPool"] == 0
    assert record.primary_failure != ""


# -- GF-R3: a terminal observation belongs to the run ----------------------------


def test_an_http_timeout_does_not_suppress_the_after_boundaries(stage):
    """GF-R3: the investigated failure cannot delete its own evidence."""
    run = stage("D-WEB", {"serve_nothing": True, "fetch_failure": "unchanged"})
    record = run.record()

    after = run.measurement("M-DWEB-5")
    assert after.status is MeasurementStatus.RAN
    # The payloads, and their own operation identities, survive the reload.
    assert after.facts["listeners_after"]["observed"] is True
    assert "forwarding_after" in after.facts
    purposes = [item.purpose for item in record.operations if item.seq]
    assert "d-web:listeners:after" in purposes
    assert "d-web:forwarding:after" in purposes
    # The fetch is still what failed, and it is still the primary failure.
    assert run.measurement("M-DWEB-4").conclusion is not (
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )


@pytest.mark.parametrize(
    "engine_config",
    [
        {"go_returns": False},
        {"fetch_content_override": "a page that is not this run's marker"},
        {"delete_client_inert": True},
        {"delete_client_throws": True},
    ],
)
def test_every_unsuccessful_fetch_path_still_reads_its_boundaries(stage, engine_config):
    """A stopped procedure is a reason to observe, not a reason to skip."""
    run = stage("D-WEB", engine_config)

    after = run.measurement("M-DWEB-5")
    assert after.status is MeasurementStatus.RAN
    assert after.facts["listeners_after"]["observed"] is True


def test_an_intermediate_dhcp_failure_still_takes_the_terminal_reading(stage):
    """D4 is what the run left behind, so a failure is why it is taken."""
    run = stage("D-WEB", {"serve_nothing": True})
    assert run.measurement("M-DWEB-5").status is MeasurementStatus.RAN

    stopped = stage("D-DHCP", {"dhcp_default_pool": "arbitrary"})
    record = stopped.record()
    final = stopped.measurement("M-DDHCP-4")
    if record.primary_failure:
        # Whatever stopped the sequence, the terminal reading is either taken
        # or explicitly declared not taken -- never silently missing.
        assert final.status is MeasurementStatus.RAN or final.reason.startswith(
            "not_observed:"
        )


def test_the_terminal_reading_is_cumulative_and_names_its_interventions(stage):
    """A span is not a step, and a declared footprint is not an execution."""
    run = stage("D-DHCP", {"default_pool_drift_reads": 6})
    final = run.measurement("M-DDHCP-4")
    facts = final.facts["d4_cumulative"]

    # The terminal value differs from every earlier snapshot.
    assert facts["differences"]
    assert final.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert all(
        item.startswith("native_default_changed_cumulatively:") for item in final.causes
    )
    # It spans the sequence and says so, instead of naming only the last one.
    assert facts["span"] == "cumulative_baseline_to_final"
    assert facts["interventions"] == [
        "e5:server_static_address:configurePcIp",
        "e6:configure_server_dhcp_pool:process_disabled",
        "e6:enable_server_dhcp",
    ]
    assert any(
        item.startswith("cumulative_span_identifies_the_sequence_not_one_intervention")
        for item in final.limitations
    )
    assert (
        "declared_call_footprint_is_not_an_observed_execution_count"
        in final.limitations
    )
    # The declared footprint is labelled as declared, and carries every
    # intervention's own calls rather than the first one's.
    declared = facts["declared_native_calls"]
    assert "e5:server_static_address:configurePcIp:configurePcIp" in declared
    assert "e6:enable_server_dhcp:setEnable" in declared
    assert any(item.endswith(":addPool") for item in declared)


def test_a_terminal_reading_without_authority_is_declared_not_taken(replaced_run):
    """An unproven receiver answers no question, including the last one."""
    run, _foreign, _readings = replaced_run(at=FIRST_EFFECT)

    after = run.measurement("M-DWEB-5")
    assert after.status is MeasurementStatus.NOT_RUN
    assert after.reason.startswith("not_observed:authority_lost:")


def test_a_failing_store_separates_retained_evidence_from_durable_evidence(
    stage, tmp_path
):
    """Durability and observation are two claims, and the record separates them."""
    from service_qualification_engine import RecordingStore

    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        QualificationRecord,
    )

    # The boundary write of the terminal observation fails; later writes
    # succeed, so the record can still state what it could not make
    # durable at the moment it observed it.
    store = RecordingStore(
        tmp_path / "lossy", fail_at={"experiment:D_DHCP_FINAL:started"}
    )
    run = stage("D-DHCP", record_store=store)
    # The store is the one that failed, so the last durable record is read
    # from where it actually wrote, not from the run's own directory.
    (path,) = list((tmp_path / "lossy").rglob("*.json"))
    record = QualificationRecord.model_validate_json(path.read_text(encoding="utf-8"))

    # The reading was still taken -- a persistence failure is a reason to
    # observe what the run is about to leave behind, not to stop looking --
    # and the record states which of the two claims it can make about it.
    assert any(
        item.startswith("terminal_observation_retained_in_memory_only:")
        for item in record.limitations
    )
    assert record.persist_error
    assert [item.label for item in record.native_default_pool][-1] == (
        "d4_before_cleanup"
    )
    # It was counted outside the cleanup reserve, in its own phase.
    assert [
        item.phase
        for item in record.operations
        if item.purpose.endswith("d4_before_cleanup")
    ] == ["terminal_observation"]
    # The boundary write failing is not a reason to fail the run: nothing
    # followed it, the evidence was made durable by the terminal write,
    # and what could not be persisted at the time is named.
    assert run.exit_code == 0


class _GoesQuietAfter:
    """A channel that stops answering once it has served `calls` commands.

    An engine that becomes unreachable mid-run is not a run that failed to
    take its readings: the readings are dispatched and come back unobserved,
    and each one has to say so.
    """

    def __init__(self, inner, *, calls: int) -> None:
        """Wrap one transport and mute it after that many commands."""
        self.inner = inner
        self.budget = calls
        self.calls: list[tuple[str, str]] = []

    def _spend(self) -> bool:
        if self.budget <= 0:
            return False
        self.budget -= 1
        return True

    def send(self, js_code: str) -> bool:
        """Queue one command, or report that nothing was accepted."""
        self.calls.append(("send", js_code))
        return self.inner.send(js_code) if self._spend() else False

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        """Dispatch one command, or return no answer at all."""
        self.calls.append(("send_and_wait", js_code))
        if not self._spend():
            return None
        return self.inner.send_and_wait(js_code, timeout)

    def dispatch_and_wait(self, js_code: str, timeout: float):
        """Dispatch with typed facts while the engine still answers."""
        self.calls.append(("dispatch_and_wait", js_code))
        return self.inner.dispatch_and_wait(js_code, timeout)


def test_an_engine_that_stops_answering_leaves_an_absence_with_its_cause(
    tmp_path, capsys
):
    """An unobserved terminal reading is an explicit absence, never silence."""
    directory = tmp_path / "quiet"
    directory.mkdir()
    run = DiagnosticStageRun(directory, "D-WEB", {"stp_rows": dict(FORWARDING_ROWS)})
    try:
        # Enough to be admitted and to create the fixtures, then nothing.
        run.transport = _GoesQuietAfter(run.transport, calls=30)
        run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        capsys.readouterr()
        record = run.record()
    finally:
        run.close()

    # Every reading the silent engine could not answer is named rather
    # than dropped, and the run is stopped rather than completed.
    assert record.outcome.value == "stopped"
    assert run.exit_code == 1
    assert record.restoration_proven is False
    # A reading that came back empty is a measurement that ran and names
    # what it could not observe; one that never started names why. Either
    # way it is in the record, with a cause.
    accounted = [
        item
        for item in record.measurements
        if (item.status is MeasurementStatus.RAN and item.causes)
        or (item.status is MeasurementStatus.NOT_RUN and item.reason)
    ]
    assert accounted, "a reading that was not taken must say so"
    assert all(
        item.status is not MeasurementStatus.NOT_RUN or item.reason
        for item in record.measurements
    )


def test_an_unaffordable_terminal_reading_is_named_not_omitted(stage, monkeypatch):
    """Silence is not an observation, and the cleanup reserve is not a fallback."""
    from packet_tracer_mcp.application.use_cases import qualify_server_services as uc

    after = next(item for item in D_WEB.experiments if item.id == "M-DWEB-5")
    original = uc.OperationLedger.can_afford

    def can_afford(self, operations: int) -> bool:
        """Refuse exactly the terminal observation's declared cost."""
        if operations == after.planned_operations:
            return False
        return original(self, operations)

    monkeypatch.setattr(uc.OperationLedger, "can_afford", can_afford)
    run = stage("D-WEB")
    record = run.record()

    reading = run.measurement("M-DWEB-5")
    assert reading.status is MeasurementStatus.NOT_RUN
    assert reading.reason == "not_observed:unaffordable:D_WEB_AFTER"
    # It was declared rather than paid for out of the finalization reserve.
    finalization = [
        item for item in record.operations if item.phase == "finalization" and item.seq
    ]
    assert len(finalization) <= D_WEB.reserve_operations


# -- GF-R4: a budget is the worst case of the composed path ----------------------


def test_a_delayed_ping_costs_its_inspections_and_still_classifies(stage):
    """GF-R4: an instantly answered stub command is not a worst-case oracle."""
    # The terminal withholds its statistics for more reads than the bound
    # allows, so an unbounded poll would spend all of them and a bounded
    # one stops where it said it would.
    run = stage("D-WEB", {"terminal_response_delay_reads": 40})
    record = run.record()

    purposes = [item.purpose for item in record.operations if item.seq]
    ping_calls = purposes.count("d-web:ping")
    # Four endpoint reads, one dispatch, one attribution, and the inspections
    # the slow terminal actually required -- more than the single one the
    # earlier seven-operation figure assumed.
    assert ping_calls > 7
    assert ping_calls == 6 + D_WEB_PING_INSPECTIONS
    # A sample that ended on its own bound says so instead of reporting
    # an unreachable destination it never waited for.
    ping = run.measurement("M-DWEB-3").facts["probe"]["ping"]
    assert ping["failure_reason"] == "ping_inspection_budget_exhausted"
    assert ping["reachable"] is False


@pytest.mark.parametrize("reachable", [True, False])
def test_a_delayed_complete_ping_is_classified_from_its_own_statistics(
    stage, reachable
):
    """The window is spread across the inspections, never shortened."""
    run = stage(
        "D-WEB", {"terminal_response_delay_reads": 4, "ping_reachable": reachable}
    )

    ping = run.measurement("M-DWEB-3").facts["probe"]["ping"]
    assert ping["fresh_output_observed"] is True
    assert ping["reachable"] is reachable


def test_an_output_slower_than_the_sample_budget_is_incomplete_not_forwarding(stage):
    """A sample that was never finished grants nothing and names its bound."""
    run = stage("D-WEB", {"terminal_response_delay_reads": 40})
    record = run.record()

    forwarding = run.measurement("M-DWEB-1").facts["forwarding_before"]
    assert forwarding["sample_budget_exhausted"] is True
    assert forwarding["sample_call_budget"] == D_WEB_FORWARDING_SAMPLE_CALLS
    assert forwarding["failure_reason"] == "sample_call_budget_exhausted"
    assert run.measurement("M-DWEB-1").conclusion is not (
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    # The bound held: the observation never spent more than it declared.
    purposes = [item.purpose for item in record.operations if item.seq]
    assert purposes.count("d-web:forwarding:before") <= (
        2 * D_WEB_FORWARDING_SAMPLE_CALLS + 1
    )


def test_delayed_forwarding_observed_within_the_bound_is_still_admitted(stage):
    """A slow but finishable sample is evidence, not a budget casualty."""
    run = stage("D-WEB", {"terminal_response_delay_reads": 2})

    forwarding = run.measurement("M-DWEB-1").facts["forwarding_before"]
    assert forwarding["sample_budget_exhausted"] is False
    assert run.measurement("M-DWEB-1").conclusion is (
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )


def test_every_ledgered_call_stays_inside_the_calculated_bound(stage):
    """The pinned figure is checked against what the run actually spent."""
    run = stage("D-WEB", {"terminal_response_delay_reads": 3})
    record = run.record()

    assert record.budget.used_operations <= D_WEB.planned_minimum_operations
    assert record.budget.used_operations <= D_WEB.budget.max_operations
    finalization = [
        item for item in record.operations if item.phase == "finalization" and item.seq
    ]
    # Attribution, the after-bindings and cleanup all still fit: the sampling
    # that precedes them did not eat the reserve.
    assert len(finalization) <= D_WEB.reserve_operations
    assert record.restoration_proven is True


class _Composition:
    """One real forwarding observation over one real ledger and one engine."""

    def __init__(self, directory, **config):
        """Compose the production runtime over a counted transport."""
        directory.mkdir(parents=True, exist_ok=True)
        max_operations = config.pop("max_operations", 1000)
        self.engine = NodeEngine(
            directory, terminals=True, stp_rows=dict(FORWARDING_ROWS), **config
        )
        self.clock = FakeClock()
        self.ledger = OperationLedger(
            max_operations=max_operations,
            max_seconds=900,
            clock=self.clock,
        )
        self.bound = LedgeredTransport(
            self.ledger,
            NodeEngineTransport(self.engine),
            self.clock.sleep,
            self.clock,
        )
        self.engine.seed_device("SW", "2960-24TT")
        self.runtime = PacketTracerEnterpriseConfigurationRuntime(
            query_inventory=lambda: [],
            send=self.bound.send,
            send_and_wait=self.bound.send_and_wait,
            clock=self.bound.clock,
            sleeper=self.bound.capped_sleep,
        )

    def close(self):
        """Stop the engine process."""
        self.engine.close()


@pytest.fixture
def composition(tmp_path):
    """Yield real compositions over the stub, closed at the end of the test."""
    started: list[_Composition] = []

    def make(name: str, **config):
        item = _Composition(tmp_path / name, **config)
        started.append(item)
        return item

    yield make
    for item in started:
        item.close()


def test_a_ledger_that_cannot_pay_refuses_the_next_nested_call(composition):
    """Exhaustion is a refusal before dispatch, not an overspend to discover."""
    made = composition("exhausted", terminal_response_delay_reads=40)
    ledger = OperationLedger(max_operations=3, max_seconds=900, clock=made.clock)
    made.ledger = ledger
    bound = LedgeredTransport(
        ledger, NodeEngineTransport(made.engine), made.clock.sleep, made.clock
    )
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        query_inventory=lambda: [],
        send=bound.send,
        send_and_wait=bound.send_and_wait,
        clock=bound.clock,
        sleeper=bound.capped_sleep,
    )

    with pytest.raises(OperationRefused) as refused:
        runtime.observe_access_forwarding("SW", 1, tuple(FORWARDING_ROWS))

    assert refused.value.reason == "operation_budget_exhausted"
    # Every call past the ceiling was refused BEFORE dispatch, so the
    # ledger never records more than it granted, and the refusal is
    # what reaches the caller rather than a quietly short sample.
    assert ledger.used == 3
    assert ledger.refused_calls >= 1
    assert all(item.refused for item in ledger.entries[3:])


def test_the_sample_bound_caps_the_nested_calls_the_deadline_cannot(composition):
    """A deadline read between calls caps none of them; the channel does."""
    made = composition("bounded", terminal_response_delay_reads=40)

    observation = made.runtime.observe_access_forwarding(
        "SW", 1, tuple(FORWARDING_ROWS), max_samples=2
    )

    assert observation.sample_budget_exhausted is True
    assert observation.channel_calls <= 2 * ACCESS_FORWARDING_SAMPLE_CALLS
    assert observation.failure_reason == "sample_call_budget_exhausted"
    # Every counted call is either one of the bounded sample calls or
    # the one simulation-state read taken after the loop.
    assert made.ledger.used == observation.channel_calls + 1


def test_a_crossed_deadline_stops_the_sampling_and_grants_nothing(composition):
    """The wall-clock bound still ends the loop, and late evidence is late."""
    made = composition("deadline")
    made.clock.now = 0.0

    observation = made.runtime.observe_access_forwarding(
        "SW",
        1,
        tuple(FORWARDING_ROWS),
        max_samples=3,
        deadline_seconds=0.0,
    )

    assert observation.samples == 0
    assert observation.deadline_reached is True
    assert observation.channel_calls == 0
    assert made.ledger.used == 0


def test_zero_samples_still_dispatches_nothing_under_the_bound(composition):
    """A hard ceiling of zero is zero calls, budget or no budget."""
    made = composition("zero")

    observation = made.runtime.observe_access_forwarding(
        "SW", 1, tuple(FORWARDING_ROWS), max_samples=0
    )

    assert observation.samples == 0
    assert observation.channel_calls == 0
    assert made.ledger.used == 0
