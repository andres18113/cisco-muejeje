"""The two executable diagnostics, end to end (integration and acceptance).

Both stages run through the real command line, the real request rule, the real
coordinator, the real product runtimes and the real record store. Only the
external boundaries are replaced: the channel is the Node engine stub, whose
terminal executes the actual generated IOS, ping and spanning-tree scripts,
and the clock is fake. Every expectation about engine state comes from the
stub's own snapshot, and every expectation about cost comes from the ledger.

Nothing here observes Packet Tracer. These records are `offline_simulation`
and can never qualify a capability.
"""

from __future__ import annotations

import json

import pytest
from service_qualification_engine import (
    FORWARDING_ROWS,
    SIM_BUILD,
    SIM_PROCESS_ID,
    SIM_PROCESS_INCARNATION,
    SIM_PROCESS_PATH,
    SIM_SHA,
    SIM_TREE,
    DiagnosticStageRun,
    MilestoneTransport,
    RecordingStore,
    authorization_args,
    request_args,
    stage,
)

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    STAGE_DEFINITIONS,
    DiagnosticLifecycleObservation,
    MeasurementConclusion,
    MeasurementStatus,
    QualificationRecord,
    QualificationStage,
)

#: `stage` is re-exported here as a pytest fixture, not as a call.
__all__ = ["stage"]

D_DHCP = STAGE_DEFINITIONS[QualificationStage.D_DHCP]
D_WEB = STAGE_DEFINITIONS[QualificationStage.D_WEB]

# -- D-DHCP ----------------------------------------------------------------------


def test_d_dhcp_runs_the_server_only_sequence_and_activates_no_client(stage):
    """G5.3: the full projection, with zero client activation anywhere."""
    run = stage("D-DHCP")
    record = run.record()

    assert run.exit_code == 0 and record.outcome.value == "completed"
    assert [item.status for item in record.measurements] == [
        MeasurementStatus.RAN
    ] * len(record.measurements)
    setters = run.engine.snapshot()["dhcp_setter_calls"]
    # No client is put into DHCP mode and no lease is acquired.
    assert setters["setDhcpFlag"] == 0 and setters["configurePcIpDhcp"] == 0
    assert run.scripts("dhcpRun") == [] and run.scripts("AcquireDhcpLease") == []
    # The intended pool is written once; the observed native default is never
    # a setter's target.
    assert setters["addPool"] == 1 and setters["setEnable"] == 1
    assert "serverPool" not in "".join(run.scripts("addPool"))
    # The clients keep the flags the fixture created them with.
    devices = {item["name"]: item for item in run.engine.snapshot()["devices"]}
    assert devices == {} or all(
        not port.get("dhcp_mode")
        for device in devices.values()
        for port in device["ports"]
    )


def test_d_dhcp_verifies_the_disabled_pool_before_the_single_enable(stage):
    """G5.3: `enabled=False` is verified, then exactly one transition to true."""
    run = stage("D-DHCP")
    pool = run.measurement("M-DDHCP-2").facts["e6_pool"]
    enable = run.measurement("M-DDHCP-3").facts["e6_enable"]

    assert pool["expected_enabled"] is False
    assert pool["verification"]["observation"] == "observed"
    assert pool["verification"]["observed"]["observed_enabled"] is False
    assert enable["expected_enabled"] is True
    assert enable["verification"]["observation"] == "observed"
    assert enable["verification"]["observed"]["observed_enabled"] is True
    # Every rewrite the projection made is named, in both stages.
    kinds = {item.split(":")[0] for item in pool["rewrites"]}
    assert {"dependency_removed", "foundation_removed", "expectation_field"} <= kinds
    assert any(item.startswith("expectation_rebound") for item in enable["rewrites"])


def test_d_dhcp_attributes_an_interval_to_its_whole_intervention(stage):
    """G-I7: the static address is one call that also writes gateway and DNS."""
    run = stage("D-DHCP")
    facts = run.measurement("M-DDHCP-1").facts

    assert facts["d1_interval"]["native_calls"] == ["configurePcIp"]
    assert facts["d1_interval"]["fields_written"] == [
        "ipv4",
        "netmask",
        "gateway",
        "dns_server",
    ]
    assert facts["e5"]["gateway"] and facts["e5"]["dns_server"]
    limitations = run.measurement("M-DDHCP-1").limitations
    assert any("transition_identifies_the_interval" in item for item in limitations)
    assert any(
        "intervention_writes_more_than_one_field" in item for item in limitations
    )


def test_d_dhcp_persists_each_interventions_typed_action_evidence(stage):
    """G3: adjacent snapshots keep the native dispatch/result facts between them."""
    run = stage("D-DHCP")
    static = run.measurement("M-DDHCP-1").facts["e5"]
    pool_measurement = run.measurement("M-DDHCP-2")
    pool = pool_measurement.facts["e6_pool"]
    enable = run.measurement("M-DDHCP-3").facts["e6_enable"]

    (static_action,) = static["action_results"]
    # E5's maintained endpoint batch exposes acceptance at the batch boundary,
    # not one correlated native return per action. The typed absence is kept.
    assert static_action["status"] == "applied"
    assert static_action["dispatch"] == "unspecified"
    assert static_action["result"] == "not_applicable"
    assert static_action["attempted"] is None
    assert static_action["received_mutation"] is None
    for action in pool["action_results"] + enable["action_results"]:
        assert action["dispatch"] == "accepted"
        assert action["result"] == "correlated"
        assert action["attempted"] is True
        assert action["received_mutation"] is not None
    assert set(pool_measurement.facts["d2_interval"]["native_calls"]) == {
        "addPool",
        "addExcludedAddress",
        "setNetworkMask",
        "setDefaultRouter",
        "setDnsServerIp",
        "setStartIp",
        "setEndIp",
        "setMaxUsers",
    }
    assert run.measurement("M-DDHCP-3").facts["d3_interval"]["native_calls"] == [
        "setEnable"
    ]


def test_d_dhcp_preserves_every_native_reading_on_every_exit(stage):
    """G5.3: the snapshots reach the terminal record, stopped or not."""
    run = stage("D-DHCP")
    record = run.record()
    labels = [item.label for item in record.native_default_pool]

    assert labels == [
        "d0_baseline",
        "d0_control",
        "d1_after_server_address",
        "d2_after_pool",
        "d3_after_enable",
        "d4_before_cleanup",
    ]
    assert all(
        item.purpose.startswith("d-dhcp:native_default:")
        for item in record.native_default_pool
    )
    assert all(item.operation_seq for item in record.native_default_pool)
    counted = {item.seq: item.purpose for item in record.operations if item.seq}
    assert [counted[item.operation_seq] for item in record.native_default_pool] == [
        item.purpose for item in record.native_default_pool
    ]


def test_d_dhcp_reports_a_native_default_transition_as_the_interval_it_is(stage):
    """A stub that moves the default on enable is a scenario, not a cause."""
    run = stage(
        "D-DHCP",
        {"default_pool_change_on_enable": {"end": "0.0.9.9"}},
    )
    enable = run.measurement("M-DDHCP-3")

    assert enable.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert any("default_pool_changed" in item for item in enable.causes)
    assert enable.facts["d3_interval"]["intervention"] == "e6:enable_server_dhcp"
    assert any(
        item.startswith("transition_identifies_the_interval_not_one_call")
        for item in enable.limitations
    )
    # The earlier intervals stay clean, so the change is bracketed.
    assert run.measurement("M-DDHCP-2").facts["d2_interval"]["differences"] == []


def test_d_dhcp_stops_when_the_baseline_drifts_on_its_own(stage):
    """G-I7: autonomous drift invalidates attribution instead of becoming one.

    The two baseline readings have no intervention between them, so a
    difference there is the workspace moving by itself. Continuing would let
    every later transition be attributed to an effect that did not cause it.
    """
    run = stage("D-DHCP", {"default_pool_drift_reads": 2})
    baseline = run.measurement("M-DDHCP-0")

    assert baseline.conclusion is MeasurementConclusion.CONTRADICTED
    assert "autonomous_native_default_drift" in baseline.causes
    assert baseline.facts["baseline_control"]["intervention"] == (
        "none:adjacent_baseline_readings"
    )
    assert (
        "no_later_transition_in_this_run_is_attributable_to_an_effect"
        in baseline.limitations
    )
    record = run.record()
    # A contradiction is the stop rule the coordinator already had, and it
    # keeps the first reason rather than the stage's later restatement.
    assert record.primary_failure == "contradiction:M-DDHCP-0"
    assert run.measurement("M-DDHCP-1").status is MeasurementStatus.NOT_RUN
    # The authority selected every step, the activation included, and the run
    # still did not reach it: a selection is permission to attempt a step, not
    # permission to bypass the state the same run failed to establish.
    assert "D3-enable" in D_DHCP.step_ids
    assert run.measurement("M-DDHCP-3").reason != "not_selected_by_authorization"
    assert run.engine.snapshot()["dhcp_setter_calls"]["addPool"] == 0
    assert run.engine.snapshot()["dhcp_setter_calls"]["setEnable"] == 0


# -- D-WEB -----------------------------------------------------------------------


def test_d_web_uses_the_real_binding_ping_and_client_components(stage):
    """G5.2: one attributed ping and one instrumented fetch, both counted."""
    run = stage("D-WEB")
    record = run.record()

    assert run.exit_code == 0 and record.outcome.value == "completed"
    typed = run.engine.snapshot()["terminal_commands"]
    assert [item["command"] for item in typed] == [
        "show spanning-tree",
        "ping 192.0.2.10",
        "show spanning-tree",
    ]
    # Every nested terminal call is ledgered under its own purpose.
    purposes = [item.purpose for item in record.operations if item.seq]
    assert purposes.count("d-web:ping") == 7
    assert purposes.count("d-web:forwarding:before") == 5
    assert purposes.count("d-web:forwarding:after") == 5
    forwarding_before = run.measurement("M-DWEB-1").facts["forwarding_before"]
    assert forwarding_before["simulation_time"] == "sim_time:0;frames:0"
    assert record.diagnostic_lifecycle == {
        "process_id": SIM_PROCESS_ID,
        "process_path": SIM_PROCESS_PATH,
        "product_version": SIM_BUILD,
        "file_version": "",
        "process_incarnation": SIM_PROCESS_INCARNATION,
        "mailbox_entries": [],
        "error": "",
    }
    probe = run.measurement("M-DWEB-3").facts["probe"]
    assert probe["status"] == "verified" and probe["bindings_stable"] is True
    assert probe["before"] and probe["after"]
    assert any(
        item.startswith("ping_is_an_active_stimulus")
        for item in run.measurement("M-DWEB-3").limitations
    )
    assert any(
        "icmp_reachability_is_not_tcp_or_http_service" in item
        for item in run.measurement("M-DWEB-3").limitations
    )


def test_the_ping_bindings_name_the_e5_action_this_run_applied(stage):
    """Provenance is real: the binding cites an action the stage dispatched."""
    run = stage("D-WEB")
    probe = run.measurement("M-DWEB-3").facts["probe"]

    source = probe["source_binding"]["target"]["selection"]
    destination = probe["destination_binding"]["target"]["selection"]
    assert source["configuration_action_id"] == "d-web-e5-__MCP_E6Q_PC1"
    assert destination["configuration_action_id"] == "d-web-e5-__MCP_E6Q_SRV"
    # The addresses of the other fixtures are co-observed, so a duplicate
    # address would conflict instead of binding.
    known = {item["ipv4"] for item in source["known_plan_addresses"]}
    assert {"192.0.2.10", "192.0.2.11", "192.0.2.12"} <= known
    dispatched = "".join(run.scripts("configurePcIp"))
    assert "192.0.2.11" in dispatched and "192.0.2.10" in dispatched


def test_d_web_preserves_the_whole_client_timeline_through_a_reload(stage):
    """G5.2/I5: owner, mode, native go result, every slot, the late read."""
    run = stage("D-WEB")
    fetch = run.measurement("M-DWEB-4").facts["fetch"]

    assert fetch["inputs"]["owner_device"] == "__MCP_E6Q_PC1"
    assert fetch["inputs"]["owner_read"] is True
    assert fetch["inputs"]["client_mode"] == "http"
    assert fetch["inputs"]["client_mode_type"] == "boolean"
    assert fetch["inputs"]["go_result_type"] == "boolean"
    assert fetch["inputs"]["go_result"] is True
    assert fetch["inputs"]["selected_url"] == "http://192.0.2.10/"
    assert fetch["inputs"]["selected_url_is_input"] is True
    assert fetch["inputs"]["released"] == "released"
    assert fetch["schedule"] == [1.0, 3.0, 6.0]
    labels = [item["label"] for item in fetch["timeline"]]
    assert labels[0] == "start" and labels[-1] == "late_control"
    assert all(item["budget_observed"] for item in fetch["timeline"])
    assert fetch["late_read"]["offset_seconds"] == 10.0
    # One request, ever: the late read starts nothing.
    assert len(run.scripts("p.go(")) == 1


def test_d_web_refuses_forwarding_permission_without_an_attributable_row(stage):
    """G5.1: UP and green grant nothing when the VLAN row is not forwarding."""
    run = stage(
        "D-WEB", {"stp_rows": dict(FORWARDING_ROWS, **{"FastEthernet0/2": "LRN"})}
    )
    forwarding = run.measurement("M-DWEB-1")
    facts = forwarding.facts["forwarding_before"]

    assert forwarding.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert facts["admitted"] is False and facts["dimension"] == "NON_FORWARDING"
    assert facts["light_status_is_auxiliary"] is True
    # The auxiliary light was read and is green; it grants nothing.
    lights = forwarding.facts["forwarding_before_port_lights"]
    assert any(item["light_status_name"] == "green" for item in lights.values())
    assert any(
        item.startswith("forwarding_not_admitted:") for item in run.record().limitations
    )


def test_d_web_refuses_a_row_from_another_vlan(stage):
    """G5.1: forwarding in VLAN 9 is not forwarding in the fixture's VLAN."""
    run = stage("D-WEB", {"stp_vlan": 9})
    facts = run.measurement("M-DWEB-1").facts["forwarding_before"]

    assert facts["admitted"] is False
    assert facts["dimension"] == "VLAN_INSTANCE"
    assert facts["causes"] == ["vlan_instance_absent:1"]


def test_d_web_refuses_an_ambiguous_row_for_one_interface(stage):
    """G5.1: two rows naming one port are an ambiguity, not a state."""
    run = stage(
        "D-WEB",
        {"stp_extra_rows": [["FastEthernet0/2", "BLK"]]},
    )
    facts = run.measurement("M-DWEB-1").facts["forwarding_before"]

    assert facts["admitted"] is False
    assert facts["dimension"] == "AMBIGUOUS_INTERFACE"


def test_d_web_keeps_a_valid_unreachable_control_distinguishable(stage):
    """G5.2: an unreachable ping is a measured negative, not a lost reading."""
    run = stage("D-WEB", {"ping_reachable": False})
    probe = run.measurement("M-DWEB-3")

    assert probe.facts["probe"]["bindings_stable"] is True
    assert probe.facts["probe"]["ping"]["reachable"] is False
    assert probe.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert probe.causes == ["probe_failed"]


def test_d_web_leaves_the_boundary_unresolved_when_nothing_is_retrieved(stage):
    """A timeout is never a negative listener claim."""
    run = stage("D-WEB", {"serve_nothing": True, "fetch_failure": "unchanged"})
    fetch = run.measurement("M-DWEB-4")

    assert fetch.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert fetch.causes == ["no_response_within_deadline"]
    assert "timeout_is_never_a_negative_listener_claim" in fetch.limitations
    assert "listener_request_client_and_reader_boundary_unresolved" in fetch.limitations
    assert fetch.facts["fetch"]["inputs"]["released"] == "released"


# -- authority and failure boundaries --------------------------------------------


@pytest.mark.parametrize(
    ("replace_flag", "value", "subject"),
    [
        ("--authorized-tree", "c" * 40, "repository_tree"),
        ("--authorized-profile-version", "99", "authorized_profile"),
        ("--authorized-reserve-operations", "1", "authorized_reserve"),
        ("--attempt-id", "zz", "attempt_identity"),
    ],
)
def test_a_wrong_authority_refuses_before_any_contact(
    stage, replace_flag, value, subject
):
    """G5.4: nothing is opened and nothing is dispatched."""
    argv = request_args("D-DHCP") + authorization_args("D-DHCP")
    index = argv.index(replace_flag)
    argv[index + 1] = value
    run = stage("D-DHCP", argv=argv)

    assert run.exit_code == 2
    assert run.summary["outcome"] == "refused"
    assert subject in {item["subject"] for item in run.summary["refusals"]}
    assert run.opened == [] and run.transport.calls == []


@pytest.mark.parametrize(
    ("observation", "subject"),
    [
        (
            DiagnosticLifecycleObservation(error="multiple_processes:2"),
            "process_instance",
        ),
        (
            DiagnosticLifecycleObservation(
                process_id=SIM_PROCESS_ID + 1,
                process_path=SIM_PROCESS_PATH,
                product_version=SIM_BUILD,
                process_incarnation=SIM_PROCESS_INCARNATION,
            ),
            "process_instance",
        ),
        (
            DiagnosticLifecycleObservation(
                process_id=SIM_PROCESS_ID,
                process_path=SIM_PROCESS_PATH,
                product_version=SIM_BUILD,
                process_incarnation=SIM_PROCESS_INCARNATION,
                mailbox_entries=("res_stale.txt",),
            ),
            "mailbox",
        ),
    ],
)
def test_lifecycle_preflight_refuses_before_transport(stage, observation, subject):
    """Actual process pairing and an empty mailbox precede any channel open."""
    run = stage("D-WEB", diagnostic_lifecycle=lambda: observation)

    assert run.exit_code == 2
    assert subject in {item["subject"] for item in run.summary["refusals"]}
    assert run.opened == [] and run.transport.calls == []


def test_a_repeated_attempt_identity_refuses_before_any_contact(stage, tmp_path):
    """G5.4: a new SHA or process does not create an attempt."""
    first = stage("D-DHCP")
    assert first.exit_code == 0

    directory = tmp_path / "second"
    directory.mkdir()
    second = DiagnosticStageRun(directory, "D-DHCP", None)
    try:
        # Point the second run at the first run's record directory, so the
        # store sees the attempt identity that already ran.
        second.boundaries = second._boundaries(
            record_store=RecordingStore(first.directory / "records")
        )
        code = second.run(request_args("D-DHCP") + authorization_args("D-DHCP"))
        assert code == 2
        assert second.opened == [] and second.transport.calls == []
    finally:
        second.close()


def test_a_store_that_cannot_answer_uniqueness_refuses(stage, tmp_path):
    """G5.4: an unobservable control is not a pass."""
    directory = tmp_path / "blind"
    directory.mkdir()
    run = DiagnosticStageRun(directory, "D-DHCP", None)
    try:

        class _Blind:
            def __init__(self, inner):
                self.inner = inner

            def begin(self, record):
                return self.inner.begin(record)

            def advance(self, record):
                return self.inner.advance(record)

            def complete(self, record):
                return self.inner.complete(record)

        run.boundaries = run._boundaries(
            record_store=_Blind(RecordingStore(directory / "records"))
        )
        code = run.run(request_args("D-DHCP") + authorization_args("D-DHCP"))
        assert code == 2
        assert run.opened == [] and run.transport.calls == []
    finally:
        run.close()


def test_a_missing_diagnostic_boundary_refuses_the_stage(stage, tmp_path):
    """A stage whose executor was not composed never runs a narrower one."""
    directory = tmp_path / "uncomposed"
    directory.mkdir()
    run = DiagnosticStageRun(directory, "D-WEB", None)
    try:
        run.boundaries = run._boundaries(forwarding_probe=None)
        code = run.run(request_args("D-WEB") + authorization_args("D-WEB"))
        assert code == 2
        assert run.opened == [] and run.transport.calls == []
    finally:
        run.close()


def test_an_unselected_step_is_omitted_rather_than_failed(stage):
    """A partial but coherent selection completes what it authorized."""
    steps = tuple(item.id for item in D_DHCP.steps if not item.separately_authorized)
    run = stage(
        "D-DHCP",
        argv=request_args("D-DHCP") + authorization_args("D-DHCP", steps=steps),
    )
    record = run.record()

    assert run.exit_code == 0 and record.outcome.value == "completed"
    enable = run.measurement("M-DDHCP-3")
    assert enable.status is MeasurementStatus.OMITTED
    assert enable.reason == "not_selected_by_authorization"
    # The process was never enabled, so the stage really did stop short of it.
    assert run.engine.snapshot()["dhcp_setter_calls"]["setEnable"] == 0


def test_budget_exhaustion_never_borrows_the_cleanup_reserve(stage):
    """G5.4: the reserve pays for finalization, never for one more effect."""
    argv = request_args("D-DHCP") + authorization_args("D-DHCP")
    # The ceiling the authorization names must be the stage ceiling, so the
    # squeeze comes from the ledger the coordinator builds for it.
    run = stage("D-DHCP", {"dhcp_default_pool": "native"}, argv=argv)
    record = run.record()

    reserve = D_DHCP.reserve_operations
    finalization = [
        item for item in record.operations if item.phase == "finalization" and item.seq
    ]
    experiments = [
        item for item in record.operations if item.phase == "experiment" and item.seq
    ]
    assert len(finalization) <= reserve
    assert record.budget.used_operations <= D_DHCP.budget.max_operations
    assert len(experiments) + len(finalization) <= D_DHCP.budget.max_operations
    assert record.restoration_proven is True


def test_a_persistence_failure_keeps_the_primary_error_and_still_finalizes(
    stage, tmp_path, capsys
):
    """G5.4: a lost write closes new effects; it never replaces the outcome."""

    def capsys_text() -> dict:
        printed = capsys.readouterr().out.strip().splitlines()
        return json.loads(printed[-1])

    directory = tmp_path / "lossy"
    directory.mkdir()
    run = DiagnosticStageRun(directory, "D-DHCP", None)
    try:
        run.boundaries = run._boundaries(
            record_store=RecordingStore(
                directory / "records", fail_from="experiment:D_DHCP_POOL:started"
            )
        )
        code = run.run(request_args("D-DHCP") + authorization_args("D-DHCP"))
        printed = capsys_text()
        assert code == 1
        # The terminal write failed too, so the in-memory summary is where the
        # run reports what it could not persist. The stored record is the last
        # boundary that did reach the disk, and it is still coherent.
        assert printed["persist_error"]
        assert printed["primary_failure"].startswith("persistence:")
        assert printed["restoration_proven"] is True
        record = run.record()
        assert record.persisted_step == "experiment:D_DHCP_E5:concluded"
        assert [item.label for item in record.native_default_pool][:3] == [
            "d0_baseline",
            "d0_control",
            "d1_after_server_address",
        ]
        # New effects stopped: nothing was configured after the lost write.
        assert run.engine.snapshot()["dhcp_setter_calls"]["addPool"] == 0
    finally:
        run.close()


def test_the_offline_record_can_never_qualify_a_capability(stage):
    """Simulations are labelled, and the label is what the gate reads."""
    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        promotion_evidence_refusal,
    )

    run = stage("D-WEB")
    record = run.record()
    assert record.execution_mode.value == "offline_simulation"
    assert promotion_evidence_refusal(
        record,
        stage=QualificationStage.D_WEB,
        executed_sha=SIM_SHA,
        build="9.0.1.0858",
        channel="file",
    )
    assert record.source.executed_tree == SIM_TREE


def test_a_schema_one_record_without_lifecycle_fields_still_loads(stage):
    """The new admission evidence does not reinterpret historical records."""
    payload = stage("D-WEB").record().model_dump(mode="json")
    payload.pop("diagnostic_lifecycle")
    payload.pop("diagnostic_lifecycle_postflight")
    payload["authorization"].pop("process_id")
    payload["authorization"].pop("process_path")

    historical = QualificationRecord.model_validate(payload)

    assert historical.schema_version == 1
    assert historical.diagnostic_lifecycle == {}
    assert historical.diagnostic_lifecycle_postflight == {}


#: The structural schedule of one D-WEB run's local pairing readings: one
#: before a transport exists, one before each of its six procedures, one
#: before the terminal observation, one before owned cleanup and one after
#: finalization, plus one before every dispatch inside an effect scope. The
#: last group is bounded by the stage's own operation ceiling rather than
#: fixed, so the control below pins the bound and the structure instead of a
#: constant that moves whenever the gate asks one more question.
D_WEB_STRUCTURAL_PAIRING_READS = 10


def _pairing_read_ceiling(definition) -> int:
    """Return the most local pairing readings one stage may take.

    A reading happens for each call admitted or refused inside an effect
    scope, and a call inside an effect scope is still a counted call, so the
    operation ceiling bounds them. Everything else is the structural schedule
    above.
    """
    return definition.budget.max_operations + len(definition.experiments) + 4


class _LocalReadings:
    """The local pairing one run observes, reading by reading.

    The replacement arrives because the run reached a milestone, never because
    it asked a particular number of questions: counting the authority
    callbacks would put the injection inside the control under test. Tests
    that need a replacement at an exact point drive `switch()` from a
    transport milestone; `switch_immediately` is the degenerate case of a
    pairing that never matched from the first reading on.
    """

    def __init__(
        self,
        first: DiagnosticLifecycleObservation,
        later: DiagnosticLifecycleObservation | None = None,
        *,
        switch_immediately: bool = True,
    ):
        self.first = first
        self.later = later
        self.switched = bool(later is not None and switch_immediately)
        self.calls = 0

    def switch(self) -> None:
        """Answer as the replacement from the next reading on."""
        self.switched = True

    def __call__(self) -> DiagnosticLifecycleObservation:
        """Return this reading and keep the count the run made."""
        self.calls += 1
        if self.later is not None and self.switched:
            return self.later
        return self.first


def _after_last_removal(readings: _LocalReadings) -> dict:
    """Switch the pairing once the last owned removal has been dispatched.

    The milestone is the removal of the first fixture the stage created, which
    the finalizer deletes last. Everything before it -- including both
    restoration reads -- is answered by the instance the run bound, so what
    this places at the postflight is a change that happened after the owned
    work, not one that invalidates it halfway through.
    """
    last = D_WEB.fixture_names[0]

    return {
        "wrap_transport": lambda inner: MilestoneTransport(
            inner,
            when=lambda script: "removeDevice" in script and last in script,
            after=readings.switch,
        )
    }


def _paired(**overrides) -> DiagnosticLifecycleObservation:
    """Return the coherent local pairing the simulated authority binds."""
    values = {
        "process_id": SIM_PROCESS_ID,
        "process_path": SIM_PROCESS_PATH,
        "product_version": SIM_BUILD,
        "process_incarnation": SIM_PROCESS_INCARNATION,
    }
    values.update(overrides)
    return DiagnosticLifecycleObservation(**values)


def test_the_local_pairing_is_read_again_after_finalization(stage):
    """A clean run proves the same process and a drained mailbox on exit."""
    readings = _LocalReadings(_paired())
    run = stage("D-WEB", diagnostic_lifecycle=readings)
    record = run.record()

    # Read before the transport, before each procedure, before the
    # terminal observation, before owned cleanup, once more afterwards,
    # and once before every dispatch that carries an effect. The last
    # group is what the effect gate added, and it is bounded by the
    # stage ceiling rather than fixed.
    assert readings.calls >= D_WEB_STRUCTURAL_PAIRING_READS
    assert readings.calls <= _pairing_read_ceiling(D_WEB)
    # Every effect this run dispatched was decided against the pairing,
    # so there are at least as many readings as effect operations.
    effects = [
        item
        for item in record.operations
        if item.seq and (item.purpose.startswith(("create:", "remove:", "apply:")))
    ]
    assert readings.calls >= len(effects) + D_WEB_STRUCTURAL_PAIRING_READS
    assert record.diagnostic_lifecycle["process_id"] == SIM_PROCESS_ID
    assert record.diagnostic_lifecycle_postflight["process_id"] == SIM_PROCESS_ID
    assert record.diagnostic_lifecycle_postflight["mailbox_entries"] == []
    # The positive control still completes: reading twice refuses nothing.
    assert run.exit_code == 0 and record.outcome.value == "completed"
    assert record.restoration_proven is True
    assert not [item for item in record.engine_residue if "process" in item]


def test_a_replaced_packet_tracer_invalidates_the_run_it_did_not_serve(stage):
    """GF-R1: a replacement stops the run at the next effect, not at the end.

    Packet Tracer can be restarted mid-run, and the replacement polls the same
    mailbox. Every reading taken afterwards describes a process this authority
    never bound, so the run stops at the first effect that asks again rather
    than continuing and being invalidated in its final report.
    """
    readings = _LocalReadings(
        _paired(), _paired(process_id=SIM_PROCESS_ID + 7), switch_immediately=False
    )
    # The replacement arrives when the run reaches its channel: the
    # preflight bound one process, and from the first command on the
    # mailbox is answered by another one.
    run = stage(
        "D-WEB",
        diagnostic_lifecycle=readings,
        wrap_transport=lambda inner: MilestoneTransport(
            inner, when=lambda _script: True, before=readings.switch
        ),
    )
    record = run.record()

    assert record.diagnostic_lifecycle_postflight["process_id"] == SIM_PROCESS_ID + 7
    assert "process_instance:changed" in record.engine_residue
    assert record.restoration_proven is False
    assert run.exit_code == 1 and record.outcome.value == "stopped"
    # The replacement itself is the primary failure now: it is what stopped
    # the run, and naming anything else would misattribute the cause.
    assert record.primary_failure.startswith(
        "execution_authority_lost:process_instance:changed"
    )


def test_an_undrained_mailbox_is_named_at_the_end_and_deleted_by_nobody(stage):
    """Containment reports what a later instance could still re-execute."""
    readings = _LocalReadings(
        _paired(),
        _paired(mailbox_entries=("req_orphan.js", "res_orphan.txt")),
        switch_immediately=False,
    )
    run = stage("D-WEB", diagnostic_lifecycle=readings, **_after_last_removal(readings))
    record = run.record()

    assert "mailbox:not_drained:req_orphan.js,res_orphan.txt" in record.engine_residue
    assert record.restoration_proven is False
    assert run.exit_code == 1


def test_an_unreadable_second_reading_is_unknown_not_a_clean_exit(stage):
    """Zero or multiple processes at the end cannot confirm the first one."""
    readings = _LocalReadings(
        _paired(),
        DiagnosticLifecycleObservation(error="packet_tracer_process_count:2"),
        switch_immediately=False,
    )
    run = stage("D-WEB", diagnostic_lifecycle=readings, **_after_last_removal(readings))
    record = run.record()

    assert (
        "process_instance:unobservable:packet_tracer_process_count:2"
        in record.engine_residue
    )
    assert record.restoration_proven is False
    assert record.dirty_state.value == "unknown"


def test_a_failing_second_reading_is_secondary_and_never_raises(stage):
    """A defect in local finalization evidence cannot lose the record."""

    def readings() -> DiagnosticLifecycleObservation:
        if not calls:
            calls.append(1)
            return _paired()
        raise OSError("process table unreadable")

    calls: list[int] = []
    run = stage("D-WEB", diagnostic_lifecycle=readings)
    record = run.record()

    assert record.diagnostic_lifecycle_postflight["error"].startswith(
        "diagnostic_lifecycle_failed:OSError"
    )
    assert record.restoration_proven is False
    assert record.outcome.value == "stopped"
