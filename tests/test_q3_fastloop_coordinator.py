"""DF6 to DF14: the Q3-FL coordinator over the real generated scripts.

Every run goes through the production use case, the real E5/E6 runtimes, the
product readiness gate, the real probes and the persistent Node stub engine.
The stub's own state -- its DHCP runs, pool rows and setter counts -- is the
oracle, never the row the runner reports. Nothing here observes Packet
Tracer: which of these scenarios the real engine behaves like is what the
LIVE episodes measure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from packet_tracer_mcp.adapters.cli.service_qualification import _request
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    qualify_server_services,
)
from packet_tracer_mcp.application.use_cases.service_access_readiness_gate import (
    READINESS_EPISODE_CALLS,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    Q3_FL_FORWARDING_OPERATIONS,
    REQUESTED_RENEWAL_CONTRACT_ABSENT,
    MeasurementConclusion,
    MeasurementStatus,
    QualificationOutcome,
    stage_definition,
)
from tests.service_qualification_engine import (
    FORWARDING_ROWS,
    NodeEngine,
    NodeEngineTransport,
    authorization_args,
    request_args,
    require_node,
    simulated_boundaries,
)

SERVER = "__MCP_E6Q_SRV"
PC1 = "__MCP_E6Q_PC1"
PC2 = "__MCP_E6Q_PC2"
BASE = {
    "terminals": True,
    "stp_rows": dict(FORWARDING_ROWS),
    "dhcp_default_pool": "native",
    "default_pool_realigns_on_address": True,
    "dhcp_pool_selection": "intended_then_default",
}


@dataclass
class Run:
    """One completed Q3-FL invocation and the engine state it left."""

    result: Any
    snapshot: dict[str, Any]
    transport: Any

    @property
    def record(self):
        """Return the record the run completed."""
        return self.result.record

    def measurement(self, experiment_id: str):
        """Return one measurement of the record."""
        return next(
            item
            for item in self.record.measurements
            if item.experiment_id == experiment_id
        )

    def scripts(self, needle: str) -> list[str]:
        """Return every dispatched script containing `needle`."""
        return [script for _kind, script in self.transport.calls if needle in script]


@pytest.fixture
def run_stage(tmp_path):
    """Run one Q3-FL stage through the use case against a fresh stub engine."""
    require_node()
    engines: list[NodeEngine] = []

    def make(stage: str = "Q3-FL-C1", config: dict | None = None, **overrides) -> Run:
        directory = tmp_path / f"run{len(engines)}"
        directory.mkdir()
        engine = NodeEngine(directory, **{**BASE, **(config or {})})
        engines.append(engine)
        transport = NodeEngineTransport(engine)
        boundaries = simulated_boundaries(directory, transport, **overrides)
        steps = overrides.pop("steps", None)
        request = _request(request_args(stage) + authorization_args(stage, steps=steps))
        definition = stage_definition(stage)
        result = qualify_server_services(
            request,
            boundaries,
            experimental_capabilities=frozenset(definition.experimental_capabilities),
        )
        return Run(result, engine.snapshot(), transport)

    yield make
    for engine in engines:
        engine.close()


def _attribution(run: Run, client: str) -> dict[str, Any]:
    facts = run.measurement("M-DHCP-6").facts["clients"][client]
    return facts["attribution"]


def test_the_forwarding_worst_case_is_the_gates_own_cap():
    """Two capped episodes of the product gate, pinned to its constant."""
    assert Q3_FL_FORWARDING_OPERATIONS == 2 * READINESS_EPISODE_CALLS


def test_c1_keeps_every_claim_separate_from_intended_to_native_default(run_stage):
    """PC1 is served by the intended pool, PC2 by `serverPool`, both recorded."""
    run = run_stage()

    assert run.result.outcome is QualificationOutcome.COMPLETED, (
        run.record.primary_failure
    )
    status = {item.experiment_id: item.conclusion for item in run.record.measurements}
    assert status["M-DHCP-1"] is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert status["M-DHCP-2"] is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert status["M-DHCP-6"] is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert status["M-DHCP-6-CAP"] is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert status["M-DHCP-6-REPEAT"] is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert status["M-DHCP-6-TIME"] is MeasurementConclusion.INCONCLUSIVE
    first = _attribution(run, PC1)
    second = _attribution(run, PC2)
    assert (first["served_by"], first["intended_row"]) == (
        "intended_pool",
        "exact_ip_mac_row",
    )
    assert first["causal_acquisition"].startswith("supported_")
    assert second["served_by"] == "native_default"
    assert second["intended_row"] == "absent_after_calibrated_scan"
    cap = run.measurement("M-DHCP-6-CAP")
    assert cap.facts["result"] == "lease_not_acquired:served_by_native_default"
    # The oracle: exactly one dhcpRun per client, none from the repeat.
    assert [item["device"] for item in run.snapshot["dhcp_runs"]] == [PC1, PC2]
    # Cleanup removed the server, so the realignment is read from the record.
    realigned = next(
        item
        for item in run.record.native_default_pool
        if item.label == "after_server_address"
    )
    assert (realigned.pools[0]["network"], realigned.pools[0]["end"]) == (
        "192.0.2.0",
        "192.0.3.255",
    )
    assert run.record.budget.used_operations <= 440


def test_the_policy_admits_the_realignment_then_requires_stability(run_stage):
    """Every interval after the reviewed one is unchanged, and each is recorded."""
    run = run_stage()
    intervals = run.measurement("M-DHCP-1").facts["native_default_sequence"][
        "intervals"
    ]

    assert [item["classification"] for item in intervals] == [
        "admitted_realignment",
        "unchanged",
        "unchanged",
    ]
    final = run.measurement("M-DHCP-1-FINAL")
    assert final.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    labels = [item.label for item in run.record.native_default_pool]
    assert labels == [
        "before_e5",
        "after_server_address",
        "after_client_mode",
        "after_server_setup",
        "before_cleanup",
    ]


def test_c2_discriminates_one_row_from_full(run_stage):
    """The minimal additional case: a null below capacity ends the rows."""
    run = run_stage("Q3-FL-C2", {"dhcp_pool_selection": "intended"})

    calibration = run.measurement("M-DHCP-2")
    assert calibration.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    assert calibration.facts["intended"]["kinds"][:3] == [
        "empty",
        "one_row_not_full",
        "full",
    ]
    assert "one_row_and_full_states_discriminated" in calibration.limitations
    cap = run.measurement("M-DHCP-6-CAP")
    assert cap.status is MeasurementStatus.OMITTED
    assert cap.reason.startswith("capacity_one_negative_needs_a_one_user_pool")


def test_declared_omissions_keep_their_own_reasons(run_stage):
    """M-DHCP-3 and requested renewal are omitted, never `not_selected`."""
    run = run_stage()

    events = run.measurement("M-DHCP-3")
    renewal = run.measurement("M-DHCP-6-RENEW")
    assert events.status is MeasurementStatus.OMITTED
    assert events.reason.startswith("qualification_event_source_and_release")
    assert renewal.status is MeasurementStatus.OMITTED
    assert renewal.reason == REQUESTED_RENEWAL_CONTRACT_ABSENT
    assert not run.scripts("registerEvent")


def test_an_unreviewed_default_movement_stops_before_any_client_request(run_stage):
    """Drift at the enable is contradiction; no dhcpRun follows it."""
    run = run_stage(config={"default_pool_change_on_enable": {"gateway": "192.0.2.1"}})

    assert run.record.primary_failure.startswith("q3fl_native_default_policy:")
    assert run.measurement("M-DHCP-1").conclusion is MeasurementConclusion.CONTRADICTED
    assert run.snapshot["dhcp_runs"] == []
    assert run.measurement("M-DHCP-6").status is MeasurementStatus.NOT_RUN
    assert run.measurement("M-DHCP-1-FINAL").status is MeasurementStatus.RAN
    assert run.record.restoration_proven is True


def test_an_unchanged_default_is_permitted_too(run_stage):
    """Unchanged is the other admissible reviewed-interval outcome."""
    run = run_stage(config={"default_pool_realigns_on_address": False})

    first = run.measurement("M-DHCP-1").facts["native_default_sequence"]["intervals"][0]
    assert first["classification"] == "unchanged"
    assert run.result.outcome is QualificationOutcome.COMPLETED, (
        run.record.primary_failure
    )


def test_a_refused_forwarding_group_blocks_exactly_its_dependent(run_stage):
    """PC1's port never forwards: PC1 is never activated nor requested."""
    rows = {**FORWARDING_ROWS, "FastEthernet0/2": "LIS"}
    run = run_stage(config={"stp_rows": rows})

    snapshot_ports = {
        item["name"]: [
            port for port in item["ports"] if port["name"] == "FastEthernet0"
        ]
        for item in run.snapshot["devices"]
    }
    assert [item["device"] for item in run.snapshot["dhcp_runs"]] == [PC2]
    assert not any(port["dhcp_mode"] for port in snapshot_ports.get(PC1, []))
    mode = run.measurement("M-DHCP-5")
    assert mode.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert f"forwarding_not_admitted:{PC1}" in mode.causes
    assert (
        run.measurement("M-DHCP-6")
        .facts["not_requested"][PC1]["request"]
        .startswith("not_dispatched:")
    )
    # The worst case is the gate's own: its cap, not a longer wait.
    assert run.record.budget.used_operations <= 440


def test_mode_activation_before_the_enable_leaves_nothing_to_acquire(run_stage):
    """A background discover at mode time finds no server; causality holds."""
    run = run_stage(
        config={"dhcp_mode_acquires": True, "dhcp_failure_address": "169.254.10.10"}
    )

    assert len(run.snapshot["background_acquisitions"]) == 2
    first = _attribution(run, PC1)
    assert first["addressing_before"] == "link_local"
    assert first["causal_acquisition"].startswith("supported_")


def test_an_unknown_acquisition_outcome_stops_every_later_effect(run_stage):
    """A call error is never retried, and no other client is requested."""
    run = run_stage(config={"dhcp_acquire_throws": True})

    assert run.record.primary_failure.startswith("outcome_unknown:q3fl_acquisition:")
    clients = run.measurement("M-DHCP-6").facts["not_requested"]
    assert clients[PC2]["request"].startswith("not_dispatched:stopped:")
    acquisition_scripts = run.scripts("dhcpRun(")
    assert len(acquisition_scripts) == 1
    repeat = run.measurement("M-DHCP-6-REPEAT")
    assert repeat.status is MeasurementStatus.NOT_RUN
    assert repeat.reason.startswith("repeat_not_reached:outcome_unknown:")


def test_a_repeat_that_dispatches_again_is_a_contradiction(run_stage):
    """With the claim gone, the replay sends a second dhcpRun and says so."""
    run = run_stage(config={"drop_product_claims_after_eval": True})

    repeat = run.measurement("M-DHCP-6-REPEAT")
    assert repeat.conclusion is MeasurementConclusion.CONTRADICTED
    assert [item["device"] for item in run.snapshot["dhcp_runs"]][:2] == [PC1, PC1]
    assert run.record.primary_failure == (
        "contradiction:q3fl_same_action_repeat_not_refused"
    )


def test_a_pool_the_first_client_never_filled_decides_no_negative(run_stage):
    """Both clients served by the native default: the negative is not reached."""
    run = run_stage(config={"dhcp_pool_selection": "default"})

    cap = run.measurement("M-DHCP-6-CAP")
    assert cap.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert "intended_pool_not_full_with_the_first_client" in cap.causes
    assert _attribution(run, PC1)["served_by"] == "native_default"


def test_every_client_reading_is_retained_with_its_label(run_stage):
    """Background, settle, timed and repeat readings stay in the record."""
    run = run_stage()

    series = run.measurement("M-DHCP-6").facts["client_readings"]
    labels = [item["label"] for item in series]
    assert labels[:4] == [
        "baseline",
        "after_client_mode",
        "background_1",
        "background_2",
    ]
    assert {"timed_1", "timed_2", "horizon_3"} <= set(labels)
    assert any(label.startswith("settle:") for label in labels)
    first = next(item for item in series if item["label"] == "background_1")
    assert set(first["clients"]) == {PC1, PC2}


def test_the_native_default_is_never_written(run_stage):
    """Only the intended pool is ever configured; `serverPool` moves only by address."""
    run = run_stage()

    calls = run.snapshot["dhcp_setter_calls"]
    assert calls["addPool"] == 1
    assert calls["setMaxUsers"] == 1
    assert calls["setEnable"] == 1
    assert not run.scripts("removePool")
    assert not run.scripts("dhcpRelease")
    assert not run.scripts("resetDhcpConfOn")
