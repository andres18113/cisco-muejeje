"""Governed FULL qualification: offline contract, REMAINING authority, closure.

Nothing here contacts Packet Tracer. Contract, transition and forwarding facts
are derived from the canonical composition, the review runs on typed stage
facts, and the closure runs the real coordinator with the Level A doubles.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.application.cp_scale_live.completion import (
    CPScaleCompletion,
)
from src.packet_tracer_mcp.application.cp_scale_live.contracts import (
    CPScaleMutationScope,
)
from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import (
    CPScaleStageProgress,
)
from src.packet_tracer_mcp.application.cp_scale_live.step_policy import (
    canonical_step_decision,
)
from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    CPScaleCanonicalStageTransition,
    CPScaleCanonicalTarget,
    CPScaleForwardingAuthority,
    canonical_cp_scale_target_contract,
    canonical_stage_transition_contract,
    derive_cp_scale_branch_forwarding_checks,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    CPScaleCanonicalVoiceEvidence,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    CallExpectation,
    CallExpectationResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    CallState,
    CallVerificationResult,
    PhoneExecutionMethod,
    VoiceApplicationResult,
)
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import (
    cp_scale_canonical_voice_intent,
)
from src.packet_tracer_mcp.domain.enterprise.services.control_plane_compiler import (
    control_plane_plan_semantic_hash,
)
from tests.poe_delivery_capabilities import (
    compose_delivery_qualified_cp_scale_canonical,
)
from tests.test_cp_scale_live_local_preflight import _inspect, _request, _service
from tests.test_cp_scale_router0_live_runner import RUN_DOUBLES, _probe


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs" / "reference" / "cp-scale" / "current_state.json"
FULL = canonical_cp_scale_target_contract(CPScaleCanonicalTarget.FULL_QUALIFICATION)
ROUTER3 = CPScaleCanonicalStage.ROUTER3_BRANCH
REMAINING = CPScaleCanonicalStage.REMAINING
PRECLEANUP = "CP_SCALE_FULL_QUALIFICATION_VERIFIED_PRECLEANUP"
CLEANED = "CP_SCALE_FULL_QUALIFICATION_VERIFIED_AND_CLEANED"


@pytest.fixture(scope="module")
def preparation():
    composition = compose_delivery_qualified_cp_scale_canonical(
        packet_tracer_version="9.0.1.0858",
    )
    router3 = project_cp_scale_canonical_stage(composition, ROUTER3)
    remaining = project_cp_scale_canonical_stage(composition, REMAINING)
    return SimpleNamespace(
        composition=composition,
        router0=project_cp_scale_canonical_stage(
            composition, CPScaleCanonicalStage.ROUTER0_BRANCH,
        ),
        router3=router3,
        remaining=remaining,
        transition=canonical_stage_transition_contract(router3, remaining),
    )


def test_full_contract_runs_remaining_last_and_always_cleans_up():
    router3 = canonical_cp_scale_target_contract(CPScaleCanonicalTarget.ROUTER3_BRANCH)

    assert FULL.build_stages == router3.build_stages
    assert FULL.execution_stages == (*router3.build_stages, REMAINING)
    assert FULL.terminal_stage is REMAINING
    assert (
        FULL.run_remaining_reconciliation,
        FULL.run_full_qualification,
        FULL.allow_retention,
        FULL.require_cleanup,
    ) == (True, True, False, True)
    assert (FULL.precleanup_closure, FULL.cleaned_closure) == (PRECLEANUP, CLEANED)
    decisions = {
        stage: canonical_step_decision(FULL, stage)
        for stage in FULL.execution_stages
    }
    # REMAINING alone is terminal: it proves the transition and the derived
    # pairs, and no checkpoint is offered before the closure.
    for field in ("terminal_transition", "site_forwarding"):
        assert {
            stage for stage, decision in decisions.items()
            if getattr(decision, field)
        } == {REMAINING}
    assert {
        stage for stage, decision in decisions.items()
        if not decision.checkpoint_required
    } == {REMAINING}


def test_router3_to_remaining_is_a_zero_delta_exact_partition(preparation):
    router3 = preparation.router3
    remaining = preparation.remaining
    transition = preparation.transition

    assert (transition.previous_stage, transition.current_stage) == (
        ROUTER3, REMAINING,
    )
    assert transition.previous_physical_topology_hash == (
        router3.topology.physical_identity_hash
    )
    assert transition.current_physical_topology_hash == (
        remaining.topology.physical_identity_hash
    )
    assert transition.physical_delta_empty is True
    for previous, current, mutations, retained in (
        (
            router3.configuration.actions, remaining.configuration.actions,
            transition.configuration_mutation_ids,
            transition.configuration_retained_ids,
        ),
        (
            router3.control_plane.actions, remaining.control_plane.actions,
            transition.control_plane_mutation_ids,
            transition.control_plane_retained_ids,
        ),
        (
            router3.voice.actions, remaining.voice.actions,
            transition.voice_mutation_ids, transition.voice_retained_ids,
        ),
    ):
        # Derived, never assumed empty: the final plan is exactly the retained
        # Router3 plan plus a disjoint mutation scope.
        assert set(retained) == {item.id for item in previous}
        assert set(mutations).isdisjoint(retained)
        assert set(mutations) | set(retained) == {item.id for item in current}
    assert transition.mutation_scope_disjoint is True
    assert transition.claim == "MUTATION_SCOPE_DISJOINT"


def test_full_forwarding_is_derived_from_every_applicable_flow(preparation):
    remaining = preparation.remaining
    flows = preparation.composition.enterprise.traffic_flows
    pairs = {
        frozenset((item.source_site_id, item.destination_site_id))
        for item in flows
    }
    site_checks = remaining.branch_forwarding_checks
    user_checks = remaining.branch_user_forwarding_checks
    by_direction = {item.direction: item for item in site_checks}

    # One router-to-workload and one representative PC check per direction
    # of every derived site pair; the count is never an authority of its own.
    assert len(by_direction) == len(site_checks) == 2 * len(pairs)
    assert len(user_checks) == len(site_checks)
    assert {
        frozenset((item.source_site_id, item.destination_site_id))
        for item in user_checks
    } == pairs
    for flow in flows:
        declared = by_direction[
            f"{flow.source_site_id}-to-{flow.destination_site_id}"
        ]
        returned = by_direction[
            f"{flow.destination_site_id}-to-{flow.source_site_id}"
        ]
        assert declared.authority is CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW
        assert declared.declared_traffic_flow_id == flow.id
        assert returned.reverse_of_traffic_flow_id == flow.id
    derived = {item.id for item in site_checks}
    assert {item.id for item in preparation.router0.branch_forwarding_checks} <= derived
    assert {item.id for item in preparation.router3.branch_forwarding_checks} <= derived
    assert all(
        item.source_topology_hash == remaining.topology.physical_identity_hash
        and item.source_configuration_hash == remaining.configuration.semantic_hash
        for item in (*site_checks, *user_checks)
    )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unbacked-flow", "without projected E9 forwarding authority"),
        (
            "duplicate-declared-direction",
            "exactly one matching E4 traffic flow; found 2",
        ),
    ],
)
def test_full_forwarding_fails_closed_on_unbacked_or_ambiguous_flows(
    preparation,
    case,
    message,
):
    composition = preparation.composition
    remaining = preparation.remaining
    enterprise = composition.enterprise.model_copy(deep=True)
    declared = enterprise.traffic_flows[0]
    duplicate = declared.model_copy(update={"id": declared.id + "/duplicate"})
    enterprise.traffic_flows = [*enterprise.traffic_flows, duplicate]
    control = remaining.control_plane.model_copy(deep=True)
    if case == "duplicate-declared-direction":
        # E9 backs the second declaration too, so only the E4 ambiguity remains.
        backing = next(
            item for item in control.verification_expectations
            if item.source_traffic_flow_id == declared.id
        )
        control.verification_expectations.append(backing.model_copy(update={
            "id": backing.id + "/duplicate",
            "source_traffic_flow_id": duplicate.id,
        }))
        control.semantic_hash = control_plane_plan_semantic_hash(control)

    with pytest.raises(ValueError, match=message):
        derive_cp_scale_branch_forwarding_checks(
            replace(composition, enterprise=enterprise),
            replace(remaining, control_plane=control),
            joining_site_id=None,
        )


def test_full_preparation_keeps_the_unqualified_product_scope(preparation):
    remaining = preparation.remaining
    phone_sites = {
        item.phone_id: item.site_id for item in remaining.voice.phone_assignments
    }
    state = json.loads(STATE.read_text(encoding="utf-8"))
    offline = state["operational_state"]["full_qualification"]["offline_preparation"]

    assert preparation.composition.enterprise.metadata["wireless_association"] == (
        "unqualified"
    )
    assert cp_scale_canonical_voice_intent(remaining.topology).intersite_calling is False
    assert remaining.voice.call_expectations
    assert all(
        phone_sites.get(item.source_phone_id) == item.site_id
        and phone_sites.get(item.expected_target_phone_id, item.site_id) == item.site_id
        for item in remaining.voice.call_expectations
    )
    assert offline["product_scope"] == {
        "wireless_association": "unqualified",
        "intersite_calling": False,
    }


def _call_expectations():
    return (
        CallExpectation(
            id="call/established",
            source_phone_id="phone/1",
            source_extension="1001",
            dialed_extension="1002",
            expected_target_phone_id="phone/2",
            expected_result=CallExpectationResult.ESTABLISHED,
            site_id="site/1",
        ),
        CallExpectation(
            id="call/not-connected",
            source_phone_id="phone/1",
            source_extension="1001",
            dialed_extension="1099",
            expected_result=CallExpectationResult.NOT_CONNECTED,
            site_id="site/1",
        ),
    )


def _verified_call(expectation, index):
    established = expectation.expected_result is CallExpectationResult.ESTABLISHED
    states = (
        [
            CallState.IDLE,
            CallState.DIALING,
            CallState.RINGING,
            CallState.CONNECTED,
            CallState.DISCONNECTED,
            CallState.IDLE,
        ]
        if established
        else [CallState.IDLE, CallState.DIALING, CallState.FAILED, CallState.IDLE]
    )
    return CallVerificationResult(
        call_expectation_id=expectation.id,
        call_attempt_id=f"call-attempt/{index}",
        source_phone_id=expectation.source_phone_id,
        dialed_extension=expectation.dialed_extension,
        status=ActionExecutionStatus.VERIFIED,
        states=states,
        connected=established,
        teardown_verified=True,
        observed_after_ns=index,
        fresh_evidence=True,
        evidence_method="typed_call_state_lifecycle",
        execution_method=PhoneExecutionMethod.STRUCTURED_API,
        expected_result=expectation.expected_result,
        expected_target_phone_id=expectation.expected_target_phone_id,
    )


def _projection(stage, physical, configuration_ids, call_expectations=()):
    return SimpleNamespace(
        stage=stage,
        topology=SimpleNamespace(physical_identity_hash=physical),
        configuration=SimpleNamespace(
            actions=[SimpleNamespace(id=item) for item in configuration_ids],
            semantic_hash="e5/" + stage.value,
        ),
        control_plane=SimpleNamespace(actions=[SimpleNamespace(id="cp/retained")]),
        voice=SimpleNamespace(
            actions=[SimpleNamespace(id="voice/retained")],
            phone_assignments=["phone/1"],
            call_expectations=tuple(call_expectations),
        ),
    )


def _verified(projection, report=None, voice=None):
    return SimpleNamespace(
        stage=projection.stage,
        outcome="verified",
        projection=projection,
        configuration_accepted=True,
        control_plane=SimpleNamespace(status=ConfigurationApplicationStatus.VERIFIED),
        voice=voice,
        replay_audit=SimpleNamespace(
            verified=True, claim="NO_MUTATION_REPLAY", surfaces=(),
        ),
        report=report,
    )


def _full_run():
    """Typed facts of a FULL run that REMAINING closes with one real mutation."""

    stages = []
    for stage in FULL.build_stages:
        physical = "e4/final" if stage is ROUTER3 else "e4/" + stage.value
        projection = _projection(stage, physical, ["cfg/retained"])
        stages.append(CPScaleStageProgress(projection, result=_verified(projection)))
    call_expectations = _call_expectations()
    remaining = _projection(
        REMAINING,
        "e4/final",
        ["cfg/retained", "cfg/remaining"],
        call_expectations,
    )
    calls = [
        _verified_call(expectation, index)
        for index, expectation in enumerate(call_expectations, 1)
    ]
    voice_result = VoiceApplicationResult(
        voice_plan_id="voice/remaining",
        voice_semantic_hash="e7/remaining",
        source_topology_hash="e4/final",
        source_configuration_hash="e5/remaining",
        status=ActionExecutionStatus.VERIFIED,
        application_status=ActionExecutionStatus.APPLIED,
        calls=calls,
    )

    def check(identifier):
        return SimpleNamespace(
            id=identifier,
            source_topology_hash="e4/final",
            source_configuration_hash="e5/remaining",
        )

    def observed(checks):
        return tuple(
            SimpleNamespace(check=item, verified=True, attempts=("ping",))
            for item in checks
        )

    remaining.branch_forwarding_checks = (check("site/1"), check("site/2"))
    remaining.branch_user_forwarding_checks = (check("user/1"), check("user/2"))
    report = SimpleNamespace(
        scope=CPScaleMutationScope(
            ("cfg/remaining",), ("cfg/retained",), (), ("cp/retained",),
            (), ("voice/retained",),
        ),
        canonical_voice=CPScaleCanonicalVoiceEvidence(
            complete=True,
            stage=REMAINING.value,
            expected_phone_count=1,
            expected_call_count=len(call_expectations),
            call_verified_count=len(call_expectations),
            call_failed_count=0,
            call_unobservable_count=0,
            call_identity_errors=[],
        ),
        forwarding=SimpleNamespace(
            site=observed(remaining.branch_forwarding_checks),
            site_verified=True,
            user=observed(remaining.branch_user_forwarding_checks),
            user_verified=True,
        ),
        site_forwarding_checks=remaining.branch_forwarding_checks,
        user_forwarding_checks=remaining.branch_user_forwarding_checks,
        workspace_first=object(),
        workspace_second=object(),
        workspace_verified=True,
    )
    transition = CPScaleCanonicalStageTransition(
        previous_stage=ROUTER3,
        current_stage=REMAINING,
        previous_physical_topology_hash="e4/final",
        current_physical_topology_hash="e4/final",
        new_device_ids=(),
        anchor_device_ids=(),
        new_link_ids=(),
        configuration_mutation_ids=("cfg/remaining",),
        configuration_retained_ids=("cfg/retained",),
        control_plane_mutation_ids=(),
        control_plane_retained_ids=("cp/retained",),
        voice_mutation_ids=(),
        voice_retained_ids=("voice/retained",),
        replayed_configuration_ids=(),
        replayed_control_plane_ids=(),
        replayed_voice_ids=(),
    )
    stages.append(CPScaleStageProgress(
        remaining,
        transition=transition,
        result=_verified(remaining, report, voice_result),
    ))
    return stages


def _with_defect(stages, preflight, defect):
    final = stages[-1]
    report = final.result.report
    if defect == "contract":
        preflight = replace(preflight, target=replace(preflight.target, allow_retention=True))
    elif defect == "foreign-authorization":
        preflight = replace(preflight, live_authorization=replace(
            preflight.live_authorization, authorized_target=CPScaleCanonicalTarget.ROUTER3_BRANCH,
        ))
    elif defect == "missing-stage":
        del stages[2]
    elif defect == "remaining-not-verified":
        final.result.outcome = "failed"
    elif defect == "configuration":
        final.result.configuration_accepted = False
    elif defect == "control-plane":
        final.result.control_plane.status = ConfigurationApplicationStatus.PARTIAL
    elif defect == "voice":
        report.canonical_voice.complete = False
    elif defect == "site-forwarding":
        report.forwarding.site = report.forwarding.site[:1]
    elif defect == "user-forwarding":
        report.forwarding.user_verified = None
    elif defect == "workspace":
        report.workspace_second = None
    elif defect == "transition-delta":
        stages[-1] = replace(final, transition=replace(final.transition, new_link_ids=("link/new",)))
    elif defect == "executed-scope":
        report.scope = replace(report.scope, configuration=())
    elif defect == "replay":
        stages[3].result.replay_audit = SimpleNamespace(
            verified=False, claim="MUTATION_REPLAY_DETECTED", surfaces=(),
        )
    return stages, preflight


@pytest.mark.parametrize(
    ("defect", "reason"),
    [
        ("", ""),
        ("contract", "not the exact FULL qualification contract"),
        ("foreign-authorization", "admitted FULL authorization"),
        ("missing-stage", "exact build sequence followed by REMAINING"),
        ("remaining-not-verified", "no VERIFIED result"),
        ("configuration", "configuration was not accepted"),
        ("control-plane", "control plane was not VERIFIED"),
        ("voice", "canonical Voice"),
        ("site-forwarding", "site forwarding"),
        ("user-forwarding", "representative PC forwarding"),
        ("workspace", "two fresh readbacks"),
        ("transition-delta", "zero physical delta"),
        ("executed-scope", "differs from the transition's authorized scope"),
        ("replay", "cannot attest NO_MUTATION_REPLAY"),
    ],
)
def test_full_review_accepts_only_the_complete_remaining_authority(defect, reason):
    stages, preflight = _with_defect(_full_run(), _inspect(_service(), _request()), defect)

    review = CPScaleCompletion(cleanup=None).review_full_qualification(
        preflight, tuple(stages),
    )

    if not defect:
        assert review.error == ""
        assert review.replay.verified is True
        assert review.replay.audited_stages == tuple(
            stage.value for stage in FULL.execution_stages
        )
        return
    assert review.error.startswith("Full qualification closure")
    assert reason in review.error


@pytest.mark.parametrize(
    "status",
    (ActionExecutionStatus.UNOBSERVABLE, ActionExecutionStatus.FAILED),
)
def test_full_refuses_non_verified_calls_without_reclassifying_them(status):
    stages = _full_run()
    final = stages[-1].result
    final.voice.calls[0] = final.voice.calls[0].model_copy(update={"status": status})
    expected = len(final.projection.voice.call_expectations)
    final.report.canonical_voice = final.report.canonical_voice.model_copy(update={
        "call_verified_count": expected - 1,
        "call_failed_count": int(status is ActionExecutionStatus.FAILED),
        "call_unobservable_count": int(status is ActionExecutionStatus.UNOBSERVABLE),
    })

    review = CPScaleCompletion(cleanup=None).review_full_qualification(
        _inspect(_service(), _request()), tuple(stages),
    )

    assert "FULL call acceptance" in review.error
    assert status.value.upper() in review.error
    assert final.voice.calls[0].status is status
    assert final.report.canonical_voice.complete is True


@pytest.mark.parametrize("defect", ("missing", "duplicate", "unexpected"))
def test_full_requires_exactly_one_observation_per_planned_call(defect):
    stages = _full_run()
    calls = stages[-1].result.voice.calls
    if defect == "missing":
        calls.pop(0)
    elif defect == "duplicate":
        calls.append(calls[0].model_copy(update={"call_attempt_id": "duplicate"}))
    else:
        calls[0] = calls[0].model_copy(update={
            "call_expectation_id": "call/unexpected",
            "call_attempt_id": "unexpected",
        })

    review = CPScaleCompletion(cleanup=None).review_full_qualification(
        _inspect(_service(), _request()), tuple(stages),
    )

    assert "exact 1:1" in review.error


@pytest.mark.parametrize(
    ("defect", "reason"),
    (
        ("stale", "fresh evidence"),
        ("missing-attempt", "unique call-attempt identities"),
        ("unobservable-method", "observable execution method"),
        ("missing-evidence-method", "explicit evidence method"),
        ("foreign-identity", "foreign call identity"),
        ("expected-result", "typed expected result"),
        ("established-disconnected", "ESTABLISHED behavior"),
        ("established-lifecycle", "required call lifecycle"),
        ("negative-connected", "NOT_CONNECTED behavior"),
    ),
)
def test_full_audits_each_verified_call_evidence_contract(defect, reason):
    stages = _full_run()
    calls = stages[-1].result.voice.calls
    index = 1 if defect == "negative-connected" else 0
    call = calls[index]
    if defect == "missing-attempt":
        update = {"call_attempt_id": ""}
    elif defect == "stale":
        update = {"fresh_evidence": False}
    elif defect == "unobservable-method":
        update = {"execution_method": PhoneExecutionMethod.UNOBSERVABLE}
    elif defect == "missing-evidence-method":
        update = {"evidence_method": ""}
    elif defect == "foreign-identity":
        update = {"source_phone_id": "phone/foreign"}
    elif defect == "expected-result":
        update = {"expected_result": CallExpectationResult.NOT_CONNECTED}
    elif defect == "established-disconnected":
        update = {"connected": False, "states": [CallState.IDLE]}
    elif defect == "established-lifecycle":
        update = {"teardown_verified": False}
    else:
        update = {"connected": True, "states": [CallState.CONNECTED]}
    calls[index] = call.model_copy(update=update)

    review = CPScaleCompletion(cleanup=None).review_full_qualification(
        _inspect(_service(), _request()), tuple(stages),
    )

    assert reason in review.error


@pytest.mark.parametrize(
    "defect",
    (
        "expected-count",
        "verified-count",
        "failed-count",
        "unobservable-count",
        "identity-errors",
    ),
)
def test_full_requires_exact_canonical_call_aggregates(defect):
    stages = _full_run()
    canonical = stages[-1].result.report.canonical_voice
    expected = len(stages[-1].projection.voice.call_expectations)
    updates = {
        "expected-count": {"expected_call_count": expected + 1},
        "verified-count": {"call_verified_count": expected - 1},
        "failed-count": {"call_failed_count": 1},
        "unobservable-count": {"call_unobservable_count": 1},
        "identity-errors": {"call_identity_errors": ["unexpected:call/foreign"]},
    }
    stages[-1].result.report.canonical_voice = canonical.model_copy(
        update=updates[defect],
    )

    review = CPScaleCompletion(cleanup=None).review_full_qualification(
        _inspect(_service(), _request()), tuple(stages),
    )

    assert "canonical Voice call aggregates" in review.error


@pytest.mark.parametrize(
    "failure", ["", "review", "restoration", "realtime", "cleanup-archive"],
)
def test_full_run_publishes_its_closure_only_after_review_and_attested_cleanup(failure):
    verdict = _probe(RUN_DOUBLES + "\nfailure = " + repr(failure) + r'''
from dataclasses import replace
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleLiveRequest
request = CPScaleLiveRequest("9.0.1.0858", HEAD, False, "full-qualification", authorized("full-qualification"))
coordinator = offline_coordinator(request)
coordinator.build.reconcile = lambda topology, physical, **kwargs: (
    record("reconcile", deployment_id=kwargs.get("deployment_id")) or Deployment()
)
seams._write_checkpoint_summary = lambda stage, evidence, **kwargs: record("summary", stage=stage)
archives = []
original_archive = coordinator.persistence.archive
def archive(phase, payload, **kwargs):
    archives.append(phase)
    if failure == "cleanup-archive" and phase == "cleanup":
        raise OSError("cleanup attestation was not archived")
    return original_archive(phase, payload, **kwargs)
coordinator.persistence.archive = archive
if failure == "review":
    def stage(projection, **kwargs):
        result = execute_stage(projection, **kwargs)
        if projection.stage is CPScaleCanonicalStage.REMAINING:
            result = replace(result, report=replace(result.report, user_forwarding_checks=()))
        return result
    seams._execute_stage = stage
if failure == "restoration":
    coordinator.completion.cleanup.restore = lambda *args: CPScaleCleanupResult(
        False, "Second cleanup observation did not restore the exact baseline.",
    )
original_observations = coordinator.observations_factory
def observations(session):
    value = original_observations(session)
    if failure == "realtime":
        value.cleanup_realtime = lambda: CPScaleCleanupRealtime(False, "Realtime was not restored.")
    return value
coordinator.observations_factory = observations
terminal_events = []
coordinator.presentation.terminal = lambda event, report: terminal_events.append(event.value)
result = coordinator.run(request)
remaining = stage_requests[-1]
print(json.dumps({
    "outcome": result.outcome.value,
    "closure": result.closure,
    "primary": result.primary_failure,
    "stages": [item.stage.value for item in result.progress.completed_stages],
    "checkpoints": [item["stage"] for item in calls if item["event"] == "checkpoint"],
    "transitions": [[item["previous"], item["current"]] for item in calls if item["event"] == "transition"],
    "reconciliations": [
        item["deployment_id"] for item in calls
        if item["event"] == "reconcile" and "remaining" in item["deployment_id"]
    ],
    "remaining_checks": [
        remaining.projection.stage.value,
        len(remaining.site_forwarding_checks),
        len(remaining.user_forwarding_checks),
    ],
    "archives": archives,
    "terminal": terminal_events,
}))
''')

    closed = not failure
    assert verdict["outcome"] == ("completed" if closed else "failed")
    assert verdict["terminal"] == ([CLEANED] if closed else [])
    assert verdict["closure"] == {
        "": CLEANED,
        "review": None,
        "restoration": PRECLEANUP,
        "realtime": PRECLEANUP,
        "cleanup-archive": PRECLEANUP,
    }[failure]
    assert verdict["primary"] == {
        "": None,
        "review": (
            "CanonicalLiveFailure: Full qualification closure refused: REMAINING "
            "representative PC forwarding is not VERIFIED for every derived check."
        ),
        "restoration": (
            "CanonicalLiveFailure: Remaining verification completed, but "
            "cleanup/restoration did not verify: Second cleanup observation did "
            "not restore the exact baseline."
        ),
        "realtime": (
            "CanonicalLiveFailure: Remaining verification completed, but "
            "cleanup/restoration did not verify: Realtime was not restored."
        ),
        "cleanup-archive": "OSError: cleanup attestation was not archived",
    }[failure]
    assert verdict["archives"] == {
        "": ["precleanup", "cleanup"],
        "review": ["failure-precleanup", "cleanup"],
        "restoration": ["precleanup", "cleanup-incomplete"],
        "realtime": ["precleanup", "cleanup-incomplete"],
        "cleanup-archive": ["precleanup", "cleanup", "cleanup"],
    }[failure]
    assert verdict["stages"] == [stage.value for stage in FULL.execution_stages]
    assert verdict["checkpoints"] == [stage.value for stage in FULL.build_stages]
    assert verdict["transitions"] == [["router3-branch", "remaining"]]
    assert verdict["reconciliations"] == ["cp-scale-canonical/remaining/reconciliation"]
    assert verdict["remaining_checks"] == ["remaining", 2, 1]


def test_current_state_pins_the_derived_full_preparation_without_live_authority(
    preparation,
):
    operational = json.loads(STATE.read_text(encoding="utf-8"))["operational_state"]
    full = operational["full_qualification"]
    offline = full["offline_preparation"]
    transition = preparation.transition
    remaining = preparation.remaining
    flows = preparation.composition.enterprise.traffic_flows

    assert operational["next_active_step"] == (
        "READY_FOR_EXPLICIT_FULL_QUALIFICATION_LIVE_AUTHORIZATION"
    )
    assert operational["live_execution_authorized"] is False
    assert {
        key: full[key] for key in (
            "executed", "verification", "live_evidence_acquired",
            "live_execution_authorized", "authorization_required",
        )
    } == {
        "executed": False,
        "verification": "NOT_VERIFIED",
        "live_evidence_acquired": False,
        "live_execution_authorized": False,
        "authorization_required": "EXPLICIT_TARGET_AND_SHA_SCOPED",
    }
    assert "authorized_sha" not in json.dumps(full)
    assert not (ROOT / "docs/reference/cp-scale/full_successful_run.json").exists()
    assert {
        key: offline[key] for key in (
            "target", "execution_stages", "terminal_stage",
            "run_remaining_reconciliation", "run_full_qualification",
            "allow_retention", "require_cleanup", "precleanup_closure",
            "cleaned_closure",
        )
    } == {
        "target": FULL.target.value,
        "execution_stages": [stage.value for stage in FULL.execution_stages],
        "terminal_stage": FULL.terminal_stage.value,
        "run_remaining_reconciliation": FULL.run_remaining_reconciliation,
        "run_full_qualification": FULL.run_full_qualification,
        "allow_retention": FULL.allow_retention,
        "require_cleanup": FULL.require_cleanup,
        "precleanup_closure": FULL.precleanup_closure,
        "cleaned_closure": FULL.cleaned_closure,
    }
    assert offline["transition"] == {
        "previous_stage": transition.previous_stage.value,
        "current_stage": transition.current_stage.value,
        "physical_delta_empty": transition.physical_delta_empty,
        "configuration_mutations": len(transition.configuration_mutation_ids),
        "configuration_retained": len(transition.configuration_retained_ids),
        "control_plane_mutations": len(transition.control_plane_mutation_ids),
        "control_plane_retained": len(transition.control_plane_retained_ids),
        "voice_mutations": len(transition.voice_mutation_ids),
        "voice_retained": len(transition.voice_retained_ids),
        "claim": transition.claim,
        "runtime_replay_claim": "NOT_ACQUIRED",
    }
    assert offline["forwarding"] == {
        "declared_flow_ids": sorted(item.id for item in flows),
        "site_pairs": len({
            frozenset((item.source_site_id, item.destination_site_id))
            for item in flows
        }),
        "router_to_workload_checks": len(remaining.branch_forwarding_checks),
        "representative_pc_checks": len(remaining.branch_user_forwarding_checks),
    }
