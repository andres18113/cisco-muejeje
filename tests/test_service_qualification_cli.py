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
from pathlib import Path

import pytest
from service_qualification_engine import (
    SIM_SHA,
    NodeEngine,
    NodeEngineTransport,
    authorization_args,
    request_args,
    simulated_boundaries,
)

import packet_tracer_mcp
from packet_tracer_mcp.adapters.cli import service_qualification as cli
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
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
        ("Q3", ("not_permitted", "stage")),
        ("Q9", ("malformed", "stage")),
    ],
)
def test_declarative_and_unknown_stages_refuse_before_contact(
    simulation, capsys, stage, expected
):
    """Q2/Q3 have unmet prerequisites; an unknown stage is named."""
    sim = simulation()
    code, summary = sim.main(
        ["--execute", "--stage", stage, "--expected-head", SIM_SHA], capsys
    )
    assert code == 2 and expected in _subjects(summary)
    assert sim.opened == []


def test_q1_is_admitted_at_its_reviewed_ceiling_and_finalizes(simulation, capsys):
    """Q1's 60/600 design ceiling covers its planned worst case of 46 operations.

    The stage used to refuse before contact because its executable definition
    exceeded a 30-operation ceiling. It now runs end to end through the
    operator entry point, spends no more than the planned worst case, refuses
    no call, and leaves the workspace and the engine bag empty.
    """
    sim = simulation()
    code, summary = sim.main(request_args("Q1") + authorization_args("Q1"), capsys)
    assert code == 0
    assert summary["refusals"] == []
    assert sim.opened == ["file"]
    assert summary["operations_used"] <= 46
    (record,) = sim.records()
    assert record.budget.max_operations == 60
    assert record.budget.planned_minimum_operations == 46
    assert record.budget.refused_calls == 0
    assert record.restoration_proven is True
    snapshot = sim.engine.snapshot()
    assert snapshot["devices"] == [] and snapshot["run_bags"] == {}


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
