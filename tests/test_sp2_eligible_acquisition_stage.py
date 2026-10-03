"""Eligible recovery uses the maintained runtimes and durable qualification record."""

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    MeasurementConclusion,
    QualificationRecord,
    stage_definition,
)
from tests.service_qualification_engine import RecordingStore
from tests.test_sp2_mixed_acquisition_stage import E8_STATE
from tests.test_sp2_mixed_product_stage import _run

STAGE = "SP2-ELIGIBLE-ACQUISITION"


def test_one_assigned_observer_does_not_prevent_owned_explicit_interventions(tmp_path):
    """One assigned observer does not prevent owned explicit interventions."""
    assert stage_definition(STAGE) is not None, "Prospective profile is not admitted"
    run = _run(
        tmp_path,
        stage=STAGE,
        run_id="eligible-acquisition-offline",
        engine_config={
            **E8_STATE,
            "dhcp_retry_on_server_enable_clients": ["BR1-DEFAULT-PC-02"],
        },
    )
    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, (
        arms.causes,
        run.record.primary_failure,
    )
    assert (
        arms.facts["cohort"]["observations"]["BR1-DEFAULT-PC-02"] == "assigned_observer"
    )
    assert "BR1-DEFAULT-PC-02" not in arms.facts["interventions"]
    assert len(run.snapshot["dhcp_runs"]) == 4
    assert run.record.restoration_proven
    record_paths = list((tmp_path / "records").rglob("*.json"))
    assert len(record_paths) == 1
    reloaded = QualificationRecord.model_validate_json(record_paths[0].read_text())
    measured = next(
        item
        for item in reloaded.measurements
        if item.experiment_id == arms.experiment_id
    )
    assert measured.facts["cohort"] == arms.facts["cohort"]
    assert (
        measured.facts["window"][-1]["finished_seconds"]
        >= measured.facts["window"][0]["started_seconds"]
    )


def test_the_historical_all_apipa_profile_still_withholds_every_arm(tmp_path):
    """The historical all apipa profile still withholds every arm."""
    run = _run(
        tmp_path,
        stage="SP2-MIXED-ACQUISITION",
        run_id="historical-one-assigned",
        engine_config={
            **E8_STATE,
            "dhcp_retry_on_server_enable_clients": ["BR1-DEFAULT-PC-02"],
        },
    )
    assert run.record.primary_failure == "sp2_acquisition_precondition_not_reproduced"
    assert run.snapshot["dhcp_runs"] == []


def test_unknown_explicit_dispatch_stops_every_later_start(tmp_path):
    """Unknown effects retain every outcome and are never replayed."""
    run = _run(
        tmp_path,
        stage=STAGE,
        run_id="eligible-unknown",
        engine_config={**E8_STATE, "dhcp_acquire_throws": True},
    )
    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert arms.outcome_unknown
    assert len(arms.facts["explicit_start"]) == 1
    assert run.snapshot["dhcp_runs"] == []
    assert run.record.restoration_proven


def test_lost_next_announcement_preserves_the_first_effect_and_cohort(tmp_path):
    """Persistence loss after one start cannot admit the second effect."""
    store = RecordingStore(
        tmp_path / "records",
        fail_at={"experiment:SP2_ACQUISITION_ARMS:explicit-start:BR2-DEFAULT-PC-01"},
    )
    run = _run(
        tmp_path,
        stage=STAGE,
        run_id="eligible-persistence",
        engine_config=E8_STATE,
        boundary_overrides={"record_store": store},
    )
    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert [row["device"] for row in run.snapshot["dhcp_runs"]] == ["BR1-DEFAULT-PC-01"]
    assert len(arms.facts["explicit_start"]) == 1
    assert "cohort" in arms.facts
    assert run.record.restoration_proven


def test_shared_server_loss_after_an_effect_refuses_the_next_intervention(tmp_path):
    """Fresh policy loss remains visible even beside an allocated lease."""
    run = _run(
        tmp_path,
        stage=STAGE,
        run_id="eligible-shared-loss",
        engine_config={**E8_STATE, "dhcp_disable_server_after_acquire": True},
    )
    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert run.record.primary_failure == "sp2_eligible_shared_precondition_changed"
    assert [row["device"] for row in run.snapshot["dhcp_runs"]] == ["BR1-DEFAULT-PC-01"]
    assert run.record.restoration_proven
