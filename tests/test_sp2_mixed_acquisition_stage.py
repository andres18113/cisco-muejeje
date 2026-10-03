"""The private SP-2 acquisition discriminator over a hybrid simulation.

Production code: the qualification coordinator, the mixed contract composer,
the product use case and both product runtimes, the acquisition projections,
the configuration and service applicators and the record stores. Simulated:
the Node engine answers every endpoint script and the routed campus every
router and switch. Each scenario's DHCP behaviour (no retry on server
enable, inert or acquiring reassertion, throwing `dhcpRun`) is a stub
setting, so these tests prove the stage's precondition, typed effects,
evidence and stop rules, never which behaviour Packet Tracer has.
"""

from __future__ import annotations

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    SP2_ACQUISITION_ARMS,
    SP2_ACQUISITION_SAMPLES,
    MeasurementConclusion,
    MeasurementStatus,
)
from tests.service_qualification_engine import RecordingStore
from tests.test_sp2_mixed_product_stage import POOLS, _run

STAGE = "SP2-MIXED-ACQUISITION"
RUN_ID = "sp2-acquisition-stage-offline"
#: Episode 8 as a scenario: a client put in DHCP mode reads pending at
#: first and falls back to a link-local address a little later when no
#: server answered, and enabling the server afterwards retries nobody.
E8_STATE = {
    "dhcp_retry_on_server_enable": False,
    "dhcp_failure_address": "169.254.10.10",
    "dhcp_mode_acquire_after_evals": 2,
}


def _arm(arm: str) -> set[str]:
    return {name for name, value in SP2_ACQUISITION_ARMS.items() if value == arm}


def _acquisition(tmp_path, boundary_overrides=None, **engine):
    return _run(
        tmp_path,
        stage=STAGE,
        run_id=RUN_ID,
        engine_config={**E8_STATE, **engine},
        boundary_overrides=boundary_overrides,
    )


def test_explicit_start_recovers_where_reassertion_and_controls_do_not(tmp_path):
    """Only the typed explicit start acquires when reassertion is inert."""
    run = _acquisition(tmp_path, dhcp_mode_reassert_acquires=False)

    product = run.measurement("M-SP2-ACQUISITION-PRODUCT")
    assert product.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, (
        product.causes,
        run.record.primary_failure,
    )
    assert product.facts["product_accepted"] is False
    assert set(product.facts["precondition"]["clients"].values()) == {"link_local"}
    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, (
        arms.causes,
        arms.facts.get("interventions"),
    )
    assert arms.facts["pattern"] == "explicit_start_only"
    clients = arms.facts["clients"]
    acquired = {name for name, item in clients.items() if item["acquired"]}
    assert acquired == _arm("explicit_start")
    for name in acquired:
        site = name.split("-")[0]
        assert clients[name]["stable_identity"][0].startswith(
            {"HQ": "10.80.1.", "BR1": "10.80.16.", "BR2": "10.80.33."}[site]
        ), (name, clients[name], POOLS[site])
    assert {item["device"] for item in run.snapshot["dhcp_runs"]} == _arm(
        "explicit_start"
    )
    assert len(run.snapshot["dhcp_runs"]) == len(_arm("explicit_start"))
    interventions = arms.facts["interventions"]
    assert set(interventions) == set(SP2_ACQUISITION_ARMS)
    assert {interventions[name] for name in _arm("reassert")} == {"dispatched"}
    assert {interventions[name] for name in _arm("explicit_start")} == {"dispatched"}
    assert {interventions[name] for name in _arm("control")} == {"none"}
    assert len(arms.facts["samples"]) == SP2_ACQUISITION_SAMPLES
    final = run.measurement("M-SP2-ACQUISITION-FINAL")
    assert final.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, final.causes
    assert final.facts["usable"] is False
    assert run.record.restoration_proven
    claims = {
        item.resource
        for item in run.record.releases
        if item.kind == "claim" and item.resource.startswith("claim:")
    }
    assert claims == {f"claim:{name}:FastEthernet0" for name in _arm("explicit_start")}
    assert run.record.budget.used_operations <= run.record.budget.max_operations


def test_a_reassertion_that_acquires_is_reported_beside_the_explicit_start(
    tmp_path,
):
    """When reassertion also acquires, the pattern names both arms."""
    run = _acquisition(tmp_path, dhcp_mode_reassert_acquires=True)

    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE, arms.causes
    assert arms.facts["pattern"] == "explicit_start_and_reassertion"
    acquired = {
        name for name, item in arms.facts["clients"].items() if item["acquired"]
    }
    assert acquired == _arm("explicit_start") | _arm("reassert")


def test_a_product_that_serves_every_client_runs_no_arm(tmp_path):
    """No episode-8 state, no intervention: the product's success is reported."""
    run = _run(tmp_path, stage=STAGE, run_id=RUN_ID)

    product = run.measurement("M-SP2-ACQUISITION-PRODUCT")
    assert product.conclusion is MeasurementConclusion.NEGATIVE_OBSERVED
    assert "sp2_acquisition_product_served_every_client" in product.causes
    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.status is MeasurementStatus.NOT_RUN
    assert arms.reason, "an arms record that did not run must say why"
    assert run.record.primary_failure == "sp2_acquisition_precondition_not_reproduced"
    assert run.snapshot["dhcp_runs"] == []
    assert run.record.restoration_proven


def test_a_throwing_explicit_start_is_never_retried_or_counted(tmp_path):
    """An explicit start whose call failed stops every later effect."""
    run = _acquisition(
        tmp_path, dhcp_mode_reassert_acquires=False, dhcp_acquire_throws=True
    )

    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert arms.outcome_unknown is True
    assert run.record.primary_failure.startswith("outcome_unknown:")
    assert "samples" not in arms.facts
    # The first explicit start's unknown outcome admits no later effect: it
    # is the only start ever applied, and nothing was retried. (The stub logs
    # only calls that returned, so a throwing one leaves no run behind.)
    assert run.snapshot["dhcp_runs"] == []
    assert len(arms.facts["explicit_start"]) == 1
    interventions = arms.facts["interventions"]
    assert set(interventions) == set(SP2_ACQUISITION_ARMS)
    unknown = [
        name for name, value in interventions.items() if value.startswith("outcome")
    ]
    assert unknown == list(arms.facts["explicit_start"])
    assert {
        interventions[name] for name in _arm("explicit_start") if name not in unknown
    } == {"not_dispatched:stopped_after_unknown_outcome"}
    final = run.measurement("M-SP2-ACQUISITION-FINAL")
    assert final.status is MeasurementStatus.RAN
    assert run.record.restoration_proven


def test_a_persistence_loss_after_one_start_keeps_every_outcome(tmp_path):
    """Executed interventions are never recorded as an arms run that never ran.

    The second explicit start's announcement cannot be written: the first
    start already ran, so the arms record must be concluded with every
    client's outcome and the partial results, and nothing later dispatched.
    """
    starts = sorted(_arm("explicit_start"))
    store = RecordingStore(
        tmp_path / "records",
        fail_at={f"experiment:SP2_ACQUISITION_ARMS:explicit-start:{starts[1]}"},
    )
    run = _acquisition(
        tmp_path,
        boundary_overrides={"record_store": store},
        dhcp_mode_reassert_acquires=False,
    )

    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.status is MeasurementStatus.RAN, (arms.status, arms.reason)
    assert arms.conclusion is MeasurementConclusion.INCONCLUSIVE
    assert any(
        cause.startswith("sp2_acquisition_arms_cut_short") for cause in arms.causes
    )
    interventions = arms.facts["interventions"]
    assert set(interventions) == set(SP2_ACQUISITION_ARMS)
    assert interventions[starts[0]] == "dispatched"
    assert {interventions[name] for name in starts[1:]} == {
        "not_dispatched:not_reached"
    }
    assert {interventions[name] for name in _arm("reassert")} == {"dispatched"}
    assert list(arms.facts["explicit_start"]) == [starts[0]]
    assert [item["device"] for item in run.snapshot["dhcp_runs"]] == [starts[0]]
    assert "samples" not in arms.facts
    assert run.record.restoration_proven


def _reassertion(statuses):
    """Classify synthetic reassertion rows over the real projected plan."""
    from types import SimpleNamespace

    from packet_tracer_mcp.adapters.cli.sp2_mixed_qualification import (
        sp2_mixed_product_contract,
    )
    from packet_tracer_mcp.application.server_service_qualification.workflows import (
        sp2_mixed_product,
    )
    from packet_tracer_mcp.domain.enterprise.services.service_diagnostic_profiles import (
        sp2_acquisition_reassert_plan,
    )

    contract = sp2_mixed_product_contract("9.0.1.0858", "reassert-unit")
    plan = sp2_acquisition_reassert_plan(
        contract.configuration_plan, device_names=sorted(_arm("reassert"))
    )
    rows, checks = [], []
    for action, (status, dispatch, _transport) in zip(
        plan.actions, statuses, strict=True
    ):
        rows.append(
            SimpleNamespace(
                action_id=action.id,
                status=status,
                dispatch=dispatch,
                result=ResultFact.NOT_APPLICABLE,
            )
        )
        checks.append(
            SimpleNamespace(action_id=action.id, status=ActionExecutionStatus.VERIFIED)
        )
    result = SimpleNamespace(
        action_results=rows,
        verification_results=checks,
        execution_journal=SimpleNamespace(
            transport_unknown=any(item[2] for item in statuses)
        ),
    )
    return sp2_mixed_product._reassert_outcomes(result, plan)


def test_a_failed_reassertion_without_known_non_submission_is_unknown():
    """A legacy failed row may have run: it is unknown, never not-dispatched."""
    outcomes = _reassertion(
        [
            (ActionExecutionStatus.FAILED, DispatchFact.UNSPECIFIED, False),
            (ActionExecutionStatus.FAILED, DispatchFact.NOT_SUBMITTED, False),
        ]
    )
    values = sorted(outcomes.values())
    assert values[0].startswith("not_dispatched:")
    assert values[1].startswith("outcome_unknown:")


def test_a_reassertion_over_an_unknown_transport_is_unknown():
    """A lost acknowledgement makes even an applied row's dispatch unknown."""
    outcomes = _reassertion(
        [
            (ActionExecutionStatus.APPLIED, DispatchFact.UNSPECIFIED, True),
            (ActionExecutionStatus.APPLIED, DispatchFact.UNSPECIFIED, True),
        ]
    )
    assert all(value.startswith("outcome_unknown:") for value in outcomes.values())


def test_a_verified_reassertion_is_dispatched():
    """Positive control: an applied, verified ordinary assertion was dispatched."""
    outcomes = _reassertion(
        [
            (ActionExecutionStatus.APPLIED, DispatchFact.UNSPECIFIED, False),
            (ActionExecutionStatus.VERIFIED, DispatchFact.UNSPECIFIED, False),
        ]
    )
    assert set(outcomes.values()) == {"dispatched"}


class _RefusingProbes:
    """The production probes, refusing the Nth lease read as the ledger would."""

    def __init__(self, inner, refuse_at):
        self.inner = inner
        self.refuse_at = refuse_at
        self.lease_reads = 0

    def read_dhcp_lease_calibration(self, *args, **kwargs):
        from packet_tracer_mcp.application.server_service_qualification.operation_budget import (
            OperationRefused,
        )

        self.lease_reads += 1
        if self.lease_reads == self.refuse_at:
            raise OperationRefused("injected_allowance_exhausted")
        return self.inner.read_dhcp_lease_calibration(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_an_interrupted_window_keeps_every_completed_read(tmp_path):
    """Sample 1 and the reads sample 2 completed survive a refusal midway."""
    from packet_tracer_mcp.adapters.cli import service_qualification

    default = service_qualification.production_boundaries(tmp_path).probes
    # Lease reads: the precondition, window sample 1, then sample 2 refused.
    probes = lambda bound, run_id, nonce: _RefusingProbes(  # noqa: E731
        default(bound, run_id, nonce), refuse_at=3
    )
    run = _acquisition(
        tmp_path,
        boundary_overrides={"probes": probes},
        dhcp_mode_reassert_acquires=False,
    )

    arms = run.measurement("M-SP2-ACQUISITION-ARMS")
    assert arms.status is MeasurementStatus.RAN, (arms.status, arms.reason)
    assert arms.conclusion is MeasurementConclusion.INCONCLUSIVE
    window = arms.facts["window"]
    assert [item["index"] for item in window] == [1, 2]
    assert set(window[0]["reads"]) == {"clients", "bindings", "leases"}
    assert set(window[1]["reads"]) == {"clients", "bindings"}
    assert all(read["observed"] for read in window[0]["reads"].values())
    assert set(arms.facts["interventions"]) == set(SP2_ACQUISITION_ARMS)
