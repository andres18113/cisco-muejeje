"""System tests: the real CLI entry point, composition and coordinator.

Each test enters through `service_qualification.main`, the operator's entry
point. The simulated runs replace only the external boundaries (channel,
isolation, repository identity, clock and record directory) on top of the
production composition. The last group uses the production composition
itself and proves that under pytest it refuses as `TEST_PROCESS` before any
channel, repository reader or record exists.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest
from service_qualification_engine import (
    SIM_SHA,
    NodeEngine,
    NodeEngineTransport,
    RecordingStore,
    authorization_args,
    request_args,
    simulated_boundaries,
)

import packet_tracer_mcp
from packet_tracer_mcp.adapters.cli import service_qualification as cli
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    STAGE_CEILINGS,
    STAGE_DEFINITIONS,
    ExecutionMode,
    QualificationRecord,
    QualificationStage,
    promotion_evidence_refusal,
)

GOVERNED_ROOT = Path(packet_tracer_mcp.__file__).resolve().parents[2]


class _Simulation:
    """One stub engine and the boundary factory the CLI will call."""

    def __init__(self, directory: Path, **config) -> None:
        """Start the engine; nothing is composed until the CLI asks."""
        self.directory = directory
        self.engine = NodeEngine(directory, **config)
        self.transport = NodeEngineTransport(self.engine)
        self.factory_calls: list[Path] = []
        self.opened: list[str] = []
        self.overrides: dict = {}

    def factory(self, governed_root: Path):
        """Return simulated boundaries and remember that composition happened."""
        from packet_tracer_mcp.application.ports.service_qualification import (
            OpenedTransport,
        )

        self.factory_calls.append(governed_root)

        def open_transport(channel: str):
            self.opened.append(channel)
            return OpenedTransport(channel, self.transport, True, "stub_engine")

        values = {"open_transport": open_transport, **self.overrides}
        return simulated_boundaries(self.directory, self.transport, **values)

    def main(self, argv: list[str], capsys) -> tuple[int, dict]:
        """Run the entry point and parse its one JSON line."""
        code = cli.main(
            argv,
            environ={"PT_MCP_GOVERNED_ROOT": str(self.directory)},
            boundaries_factory=self.factory,
        )
        return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    def records(self) -> list[QualificationRecord]:
        """Return every record the store wrote."""
        return [
            QualificationRecord.model_validate_json(path.read_text(encoding="utf-8"))
            for path in (self.directory / "records").rglob("*.json")
        ]


@pytest.fixture
def simulation(tmp_path):
    """Yield a simulation factory and stop its engines afterwards."""
    started: list[_Simulation] = []

    def make(**config) -> _Simulation:
        directory = tmp_path / f"sim{len(started)}"
        directory.mkdir()
        item = _Simulation(directory, **config)
        started.append(item)
        return item

    yield make
    for item in started:
        item.engine.close()


def _subjects(summary: dict) -> set[tuple[str, str]]:
    return {(item["kind"], item["subject"]) for item in summary["refusals"]}


# -- nothing by default ------------------------------------------------------------


def test_the_default_invocation_refuses_before_composing_anything(simulation, capsys):
    """No `--execute`: no reader, no boundary, no channel."""
    sim = simulation()
    code, summary = sim.main(["--stage", "Q0"], capsys)
    assert code == 2
    assert _subjects(summary) == {("missing", "execution")}
    assert sim.factory_calls == [] and sim.transport.calls == []


def test_an_undeclared_governed_root_refuses_before_composition(capsys):
    """The governed checkout is declared by the operator, never derived."""

    def forbidden(_root):
        raise AssertionError("composition must not happen")

    code = cli.main(
        request_args() + authorization_args(),
        environ={},
        boundaries_factory=forbidden,
    )
    assert code == 2
    summary = json.loads(capsys.readouterr().out)
    assert _subjects(summary) == {("missing", "governed_root")}


def test_an_unauthorized_request_never_opens_a_channel(simulation, capsys):
    """Execution alone is not authorization."""
    sim = simulation()
    code, summary = sim.main(request_args(), capsys)
    assert code == 2
    assert _subjects(summary) == {("missing", "authorization")}
    assert sim.opened == [] and sim.transport.calls == []


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("Q2", ("not_permitted", "stage")),
        ("Q9", ("malformed", "stage")),
    ],
)
def test_declarative_and_unknown_stages_refuse_before_contact(
    simulation, capsys, stage, expected
):
    """Q2 has unmet prerequisites; an unknown stage is named."""
    sim = simulation()
    code, summary = sim.main(
        ["--execute", "--stage", stage, "--expected-head", SIM_SHA], capsys
    )
    assert code == 2 and expected in _subjects(summary)
    assert sim.opened == []


def test_q1_is_admitted_at_its_reviewed_ceiling_and_finalizes(simulation, capsys):
    """Q1's 60/600 design ceiling covers its planned worst case of 56 operations.

    The stage used to refuse before contact because its executable definition
    exceeded a 30-operation ceiling. It now runs end to end through the
    operator entry point, spends no more than the planned worst case -- which
    includes the readiness gate -- refuses no call, and leaves the workspace
    and the engine bag empty.
    """
    sim = simulation()
    code, summary = sim.main(request_args("Q1") + authorization_args("Q1"), capsys)
    assert code == 0
    assert summary["refusals"] == []
    assert sim.opened == ["file"]
    assert summary["operations_used"] <= 56
    (record,) = sim.records()
    assert record.budget.max_operations == 60
    assert record.budget.planned_minimum_operations == 56
    assert record.budget.refused_calls == 0
    assert record.restoration_proven is True
    snapshot = sim.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["run_bags"] == {}


def test_q3_runs_the_real_bounded_dhcp_stage_and_round_trips_its_record(
    simulation, capsys
):
    """Drive Q3 through the operator CLI, real coordinator and generated scripts."""
    sim = simulation()

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    assert summary["primary_failure"] == "outcome_unknown:q3_product_service"
    assert summary["refusals"] == []
    assert summary["operations_used"] <= 60
    assert {item["id"] for item in summary["measurements"]} == {
        "M-DHCP-1",
        "M-DHCP-2",
        "M-DHCP-3",
        "M-DHCP-4",
        "M-DHCP-5",
        "M-DHCP-6",
    }
    assert {item["id"]: item["status"] for item in summary["measurements"]} == {
        "M-DHCP-1": "ran",
        "M-DHCP-2": "ran",
        # Declared OMITTED in the amended profile, with its reason, rather
        # than silently dropped or reported as supported.
        "M-DHCP-3": "omitted",
        "M-DHCP-4": "ran",
        "M-DHCP-5": "ran",
        "M-DHCP-6": "ran",
    }
    assert {item["id"]: item["conclusion"] for item in summary["measurements"]} == {
        "M-DHCP-1": "supported_in_sample",
        "M-DHCP-2": "supported_in_sample",
        "M-DHCP-3": "not_evaluated",
        "M-DHCP-4": "supported_in_sample",
        "M-DHCP-5": "supported_in_sample",
        "M-DHCP-6": "inconclusive",
    }
    (record,) = sim.records()
    assert record.stage is QualificationStage.Q3
    assert record.budget.planned_minimum_operations == 59
    assert record.restoration_proven is True
    assert record.source.executed_sha == SIM_SHA
    assert record.budget.refused_calls == 0
    assert record.dirty_state.value == "unknown"
    assert {item.kind for item in record.releases} >= {"claim", "device"}
    assert not [item for item in record.releases if item.kind == "observer"]
    assert "engine.dhcp_event_delivery" not in record.experimental_capabilities
    timing = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-6"
    )
    assert timing.causes == ["product_dhcp_effect_outcome_unknown"]
    assert "no_guard_or_later_mutation_authorized" in timing.limitations
    snapshot = sim.engine.snapshot()
    assert snapshot["devices"] == []
    assert snapshot["run_bags"] == {}
    assert snapshot["registrations"] == []
    assert snapshot["dhcp_runs"] == [
        {"device": "__MCP_E6Q_PC1", "port": "FastEthernet0"},
        {"device": "__MCP_E6Q_PC2", "port": "FastEthernet0"},
    ]
    assert snapshot["production_globals"] == ["__mcpE6Claims"]


def test_the_amended_q3_profile_registers_no_dhcp_observer(simulation, capsys):
    """F4: no event registration or unregistration executes in this profile."""
    sim = simulation()

    code, _summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    dispatched = "".join(script for _kind, script in sim.transport.calls)
    assert "registerEvent" not in dispatched
    assert "unregisterIpcEventByID" not in dispatched
    assert "dhcpSucceed" not in dispatched
    snapshot = sim.engine.snapshot()
    assert snapshot["registrations"] == [] and snapshot["unregister_calls"] == []
    (record,) = sim.records()
    omitted = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-3"
    )
    assert omitted.status.value == "omitted"
    assert omitted.reason.startswith(
        "qualification_event_source_and_release_not_qualified"
    )
    assert record.engine_residue == [
        "claim:__MCP_E6Q_PC1:retained",
        "claim:__MCP_E6Q_PC2:retained",
    ]


def test_q3_unreviewed_build_refuses_before_opening_the_file_channel(
    simulation, capsys
):
    """Apply the backend-specific Q3 build policy at the application boundary."""
    sim = simulation()

    code, summary = sim.main(
        request_args("Q3", build="9.0.1.9999")
        + authorization_args("Q3", build="9.0.1.9999"),
        capsys,
    )

    assert code == 2
    assert _subjects(summary) == {("not_permitted", "build")}
    assert sim.opened == []


def test_q3_missing_build_policy_refuses_before_contact(simulation, capsys):
    """Do not infer a backend contract when composition omitted its build policy."""
    sim = simulation()
    sim.overrides["q3_required_build"] = ""

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 2
    assert _subjects(summary) == {("not_permitted", "build")}
    assert sim.opened == []


def test_q3_persistence_loss_before_acquisition_halts_effects_and_cleans_fixtures(
    simulation, capsys
):
    """Close the product effect gate when the acquisition boundary is not durable."""
    sim = simulation()
    sim.overrides["record_store"] = RecordingStore(
        sim.directory / "records",
        fail_from="experiment:Q3_DHCP:product_started",
    )

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    assert summary["primary_failure"] == "persistence:q3_product_not_announced"
    snapshot = sim.engine.snapshot()
    assert snapshot["dhcp_runs"] == []
    assert snapshot["devices"] == []
    assert snapshot["run_bags"] == {}


def test_q3_preserves_a_product_address_contradiction_and_still_finalizes(
    simulation, capsys
):
    """Do not relabel a same-subnet address outside the one-address pool as success.

    F5: the contradicted read-back is classified before the intentional
    same-claim guard control, so the guard is never dispatched on top of an
    effect the product already contradicted.
    """
    sim = simulation(dhcp_client_address_override="192.0.2.101")

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    assert summary["primary_failure"] == "contradiction:q3_product_readback"
    conclusions = {item["id"]: item["conclusion"] for item in summary["measurements"]}
    assert conclusions["M-DHCP-6"] == "contradicted"
    (record,) = sim.records()
    timing = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-6"
    )
    assert timing.facts["guard"] == {}
    assert [item.purpose for item in record.operations if "guard" in item.purpose] == []
    snapshot = sim.engine.snapshot()
    assert snapshot["devices"] == []
    assert snapshot["run_bags"] == {}


def test_q3_unknown_acquisition_stops_guard_mutation_but_keeps_bounded_cleanup(
    simulation, capsys
):
    """Do not retry or run the duplicate control after an effect throws unknown."""
    sim = simulation(dhcp_acquire_throws=True)

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    assert summary["primary_failure"] == "outcome_unknown:q3_product_service"
    snapshot = sim.engine.snapshot()
    assert snapshot["dhcp_runs"] == []
    assert snapshot["devices"] == []
    assert snapshot["run_bags"] == {}


def test_q3_never_activates_a_client_from_an_unready_fixture(simulation, capsys):
    """F3: a gate that never becomes ready requests no acquisition at all.

    The stage still reads what it can and finalizes; what it records is a
    readiness result about the measured links, never a verdict on DHCP.
    """
    sim = simulation(ports_up=False)

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    conclusions = {item["id"]: item["conclusion"] for item in summary["measurements"]}
    assert conclusions["M-DHCP-1"] == "inconclusive"
    assert conclusions["M-DHCP-6"] == "not_evaluated"
    assert sim.engine.snapshot()["dhcp_runs"] == []
    (record,) = sim.records()
    setup = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-1"
    )
    gate = setup.facts["readiness"]
    assert (gate["ready"], gate["reads"], gate["max_reads"]) == (False, 4, 4)
    assert gate["reason"].startswith("readiness_not_up:")
    assert any(item.startswith("readiness_not_established") for item in setup.causes)
    assert "no_serving_claim" in setup.limitations
    assert [
        item.purpose for item in record.operations if "service_apply" in item.purpose
    ] == []
    assert record.restoration_proven is True


def test_q3_runtime_budget_refusal_stops_experiments_and_preserves_finalization(
    simulation, capsys
):
    """Exercise the Q3 ledger stop independently of its reviewed 60-op arithmetic."""
    q3 = STAGE_DEFINITIONS[QualificationStage.Q3]
    experiments = tuple(
        replace(item, planned_operations=1)
        if item.id == "M-DHCP-1"
        else replace(item, planned_operations=0)
        if item.id == "M-DHCP-2"
        else item
        for item in q3.experiments
    )
    narrow = replace(
        q3,
        experiments=experiments,
        budget=replace(q3.budget, max_operations=29),
    )
    sim = simulation()

    with (
        mock.patch.dict(
            STAGE_DEFINITIONS, {QualificationStage.Q3: narrow}, clear=False
        ),
        mock.patch.dict(
            STAGE_CEILINGS, {QualificationStage.Q3: (29, 1200)}, clear=False
        ),
    ):
        code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    assert "operation_budget_exhausted" in summary["primary_failure"]
    assert summary["operations_used"] == 28
    snapshot = sim.engine.snapshot()
    assert snapshot["devices"] == []
    assert snapshot["run_bags"] == {}


def test_q3_records_an_initial_default_pool_and_stops_before_product_setters(
    simulation, capsys
):
    """Never remove or silently coexist with an unreviewed native default pool."""
    sim = simulation(dhcp_default_pool="arbitrary")

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    assert summary["primary_failure"] == "q3_initial_server_state_not_admissible"
    conclusions = {item["id"]: item["conclusion"] for item in summary["measurements"]}
    assert conclusions["M-DHCP-1"] == "inconclusive"
    (record,) = sim.records()
    admission = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-1"
    ).facts["baseline_admission"]
    assert admission["admitted"] is False
    assert (
        "baseline_pool_is_not_the_exact_observed_native_default" in admission["causes"]
    )
    snapshot = sim.engine.snapshot()
    assert snapshot["dhcp_runs"] == []
    assert snapshot["devices"] == []


def test_q3_coexists_with_the_exact_observed_native_default(simulation, capsys):
    """F1/F2: the measured `serverPool` is admitted, preserved and never touched."""
    sim = simulation(dhcp_default_pool="native")

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    assert summary["primary_failure"] == "outcome_unknown:q3_product_service"
    assert summary["operations_used"] <= 60
    conclusions = {item["id"]: item["conclusion"] for item in summary["measurements"]}
    assert conclusions["M-DHCP-1"] == "supported_in_sample"
    (record,) = sim.records()
    setup = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-1"
    )
    assert setup.facts["baseline_admission"] == {
        "admitted": True,
        "kind": "observed_native_default",
        "causes": [],
    }
    assert "native_default_pool_coexists_and_is_never_modified" in setup.limitations
    assert "process_enable_is_process_wide_not_pool_scoped" in setup.limitations
    labels = [item["label"] for item in setup.facts["native_default"]["snapshots"]]
    assert labels == ["before_e5", "after_setup"]
    timing = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-6"
    )
    assert [item["label"] for item in timing.facts["native_default"]["snapshots"]] == [
        "before_e5",
        "after_setup",
        "before_cleanup",
    ]
    assert timing.facts["native_default"]["differences"] == []
    # The last read before cleanup still shows exactly the pool the first one
    # did: the run never removed it, renamed it or rewrote one of its options.
    for item in timing.facts["native_default"]["snapshots"]:
        assert item["pools"] == [
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
    assert timing.facts["native_default"]["snapshots"][-1]["intended_pool_present"]


def test_q3_stops_when_the_observed_native_default_moves(simulation, capsys):
    """F2: a default that changed under the run stops the effects that follow."""
    sim = simulation(
        dhcp_default_pool="native",
        default_pool_change_on_enable={"gateway": "10.9.9.9"},
    )

    code, summary = sim.main(request_args("Q3") + authorization_args("Q3"), capsys)

    assert code == 1
    assert summary["primary_failure"] == (
        "q3_native_default_changed:default_pool_changed:serverPool.gateway"
    )
    (record,) = sim.records()
    setup = next(
        item for item in record.measurements if item.experiment_id == "M-DHCP-1"
    )
    assert setup.facts["native_default"]["differences"] == [
        "default_pool_changed:serverPool.gateway"
    ]
    before, after = setup.facts["native_default"]["snapshots"]
    assert before["pools"][0]["gateway"] == "0.0.0.0"
    assert after["pools"][0]["gateway"] == "10.9.9.9"
    assert sim.engine.snapshot()["dhcp_runs"] == []
    assert record.restoration_proven is True


def test_a_budget_below_the_planned_worst_case_never_reaches_a_channel(
    simulation, capsys
):
    """An authorization under the stage ceiling is a mismatch, refused before contact."""
    sim = simulation()
    code, summary = sim.main(
        request_args("Q1") + authorization_args("Q1", operations="45"), capsys
    )
    assert code == 2
    assert _subjects(summary) == {("mismatch", "budget")}
    assert sim.opened == []


def test_a_malformed_budget_argument_is_named_not_crashed(simulation, capsys):
    """A non-integer budget reaches the domain rule as a malformed value."""
    sim = simulation()
    code, summary = sim.main(
        request_args() + authorization_args(operations="twenty"), capsys
    )
    assert code == 2 and ("malformed", "budget") in _subjects(summary)


# -- mismatches ----------------------------------------------------------------------


def test_target_mismatch_refuses_before_contact(simulation, capsys):
    """The authorization must name the stage fixtures exactly."""
    sim = simulation()
    code, summary = sim.main(
        request_args() + authorization_args(targets=("__MCP_E6Q_SRV",)), capsys
    )
    assert code == 2 and ("mismatch", "authorized_targets") in _subjects(summary)
    assert sim.opened == []


def test_sha_mismatch_refuses_before_contact(simulation, capsys):
    """The authorized SHA must be the expected head."""
    sim = simulation()
    code, summary = sim.main(request_args() + authorization_args(sha="d" * 40), capsys)
    assert code == 2 and ("mismatch", "authorized_sha") in _subjects(summary)
    assert sim.opened == []


def test_channel_mismatch_refuses_before_contact(simulation, capsys):
    """One channel per authorization; no switching."""
    sim = simulation()
    code, summary = sim.main(
        request_args(channel="file") + authorization_args(channel="http"), capsys
    )
    assert code == 2 and ("mismatch", "authorized_channel") in _subjects(summary)
    assert sim.opened == []


def test_repository_head_mismatch_refuses_before_contact(simulation, capsys):
    """The executing checkout must be the authorized SHA."""
    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        RepositoryIdentity,
    )

    sim = simulation()
    sim.overrides["repository"] = lambda: RepositoryIdentity(
        head="e" * 40, tree="f" * 40, clean=True, upstream_head="e" * 40
    )
    code, summary = sim.main(request_args() + authorization_args(), capsys)
    assert code == 2 and ("mismatch", "repository_head") in _subjects(summary)
    assert sim.opened == []


def test_build_mismatch_refuses_after_one_read_and_leaves_no_effect(simulation, capsys):
    """The running application differs from the authorized build."""
    sim = simulation(version="9.0.1.9999")
    code, summary = sim.main(request_args() + authorization_args(), capsys)
    assert code == 2 and ("mismatch", "executable_build") in _subjects(summary)
    assert len(sim.transport.calls) == 1
    assert sim.engine.snapshot()["devices"] == []
    (record,) = sim.records()
    assert record.outcome.value == "refused"


# -- nominal simulated runs --------------------------------------------------------------


@pytest.mark.parametrize(("channel", "queue"), [("file", "fifo"), ("http", "coalesce")])
def test_nominal_q0_simulation_completes_and_restores(
    simulation, capsys, channel, queue
):
    """The whole entry point, one channel, 19 operations, two restoration reads."""
    sim = simulation(queue=queue)
    code, summary = sim.main(
        request_args(channel=channel) + authorization_args(channel=channel), capsys
    )
    assert code == 0
    assert summary["outcome"] == "completed"
    assert summary["execution_mode"] == "offline_simulation"
    assert summary["channel"] == channel and sim.opened == [channel]
    assert summary["operations_used"] == 19
    assert summary["restoration_proven"] is True
    assert summary["dirty_state"] == "unknown"
    snapshot = sim.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["run_bags"] == {}
    (record,) = sim.records()
    assert record.completed_at is not None
    assert record.authorization["stage"] == "Q0"
    assert record.authorization["targets"] == ["__MCP_E6Q_PC1"]
    atom = next(item for item in record.measurements if item.experiment_id == "ATOM-1")
    if channel == "http":
        assert (
            "http_channel_may_join_queued_commands_into_one_batch" in atom.limitations
        )


def test_a_simulated_record_can_never_serve_as_promotion_evidence(simulation, capsys):
    """Offline simulations are marked as such and refused by the gate."""
    sim = simulation()
    code, _summary = sim.main(request_args() + authorization_args(), capsys)
    assert code == 0
    (record,) = sim.records()
    assert record.execution_mode is ExecutionMode.OFFLINE_SIMULATION
    reason = promotion_evidence_refusal(
        record,
        stage=QualificationStage.Q0,
        executed_sha=SIM_SHA,
        build="9.0.1.0858",
        channel="file",
    )
    assert reason == "An offline simulation record can never qualify a capability."


# -- the production wiring -------------------------------------------------------------


def test_production_boundaries_are_live_and_inert_until_used(tmp_path):
    """Composing the LIVE boundaries performs no I/O."""
    boundaries = cli.production_boundaries(tmp_path)
    assert boundaries.execution_mode is ExecutionMode.LIVE
    assert list(tmp_path.iterdir()) == []


def test_production_wiring_refuses_as_test_process_before_any_contact(
    monkeypatch, capsys
):
    """The real preflight under pytest is a refusal, never a bypass."""

    class Forbidden:
        def __init__(self, *args, **kwargs):
            raise AssertionError("no channel or repository reader may be built")

    monkeypatch.setattr(cli, "PacketTracerHttpTransport", Forbidden)
    monkeypatch.setattr(cli, "FileBridge", Forbidden)
    monkeypatch.setattr(cli, "GitSourceReader", Forbidden)
    records = GOVERNED_ROOT.joinpath(*cli.RECORD_DIRECTORY)
    existed = records.exists()
    code = cli.main(
        request_args(channel="http") + authorization_args(channel="http"),
        environ={"PT_MCP_GOVERNED_ROOT": str(GOVERNED_ROOT)},
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 2
    assert _subjects(summary) == {("not_permitted", "process_isolation")}
    assert summary["refusals"][0]["detail"].startswith("TEST_PROCESS")
    assert records.exists() is existed
