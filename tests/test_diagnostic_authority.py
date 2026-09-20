"""The one execution authority an executable diagnostic stage needs (unit level).

Nothing here runs anything. These are the decisions the request rule makes
before a transport exists: what is being run, against which exact tree, on
which exact fixture models and ports, in which order, with which reserve, and
under which single attempt identity.
"""

from __future__ import annotations

import importlib
from dataclasses import replace

import pytest

from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    D_WEB_FORWARDING_SAMPLE_CALLS,
    D_WEB_PING_INSPECTIONS,
    DIAGNOSTIC_PROFILE_VERSION,
    STAGE_DEFINITIONS,
    DiagnosticLifecycleObservation,
    QualificationAuthorization,
    QualificationRequest,
    QualificationStage,
    RefusalKind,
    RefusalSubject,
    RepositoryIdentity,
    diagnostic_lifecycle_continuity,
    diagnostic_lifecycle_refusals,
    repository_refusals,
    request_refusals,
    stage_definition,
    step_selection_refusals,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    ACCESS_FORWARDING_SAMPLE_CALLS,
)
from packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingExecutor

SHA = "a" * 40
TREE = "b" * 40
BUILD = "9.0.1.0858"
PROCESS_ID = 4242
#: The creation identity that distinguishes one incarnation of that PID
#: from the next process the operating system puts in the same slot.
INCARNATION = "2026-09-20T09:15:00.0000000+00:00"
PROCESS_PATH = r"C:\Program Files\Cisco Packet Tracer\bin\PacketTracer.exe"
DIAGNOSTIC_STAGES = (QualificationStage.D_DHCP, QualificationStage.D_WEB)


def _authorization(stage: QualificationStage, **overrides):
    definition = STAGE_DEFINITIONS[stage]
    values = {
        "authorization_id": f"TD-{stage.value}-1",
        "stage": stage.value,
        "sha": SHA,
        "targets": definition.fixture_names,
        "channel": "file",
        "build": BUILD,
        "max_operations": definition.budget.max_operations,
        "max_seconds": definition.budget.max_seconds,
        "profile_id": definition.profile_id,
        "profile_version": definition.profile_version,
        "tree": TREE,
        "models": definition.fixture_models,
        "links": definition.link_bindings,
        "step_ids": definition.step_ids,
        "reserve_operations": definition.reserve_operations,
        "instance_token": "1" * 32,
        "attempt_id": "2" * 32,
        "process_id": PROCESS_ID,
        "process_path": PROCESS_PATH,
    }
    values.update(overrides)
    return QualificationAuthorization(**values)


def _request(stage: QualificationStage, authorization=None):
    definition = STAGE_DEFINITIONS[stage]
    return QualificationRequest(
        execute=True,
        stage=stage.value,
        expected_head=SHA,
        targets=definition.fixture_names,
        channel="file",
        packet_tracer_build=BUILD,
        authorization=authorization or _authorization(stage),
    )


def _subjects(refusals):
    return {item.subject for item in refusals}


@pytest.mark.parametrize("stage", DIAGNOSTIC_STAGES)
def test_a_complete_authority_admits_the_stage(stage):
    """The positive control every refusal below is measured against."""
    assert request_refusals(_request(stage)) == ()


@pytest.mark.parametrize("stage", DIAGNOSTIC_STAGES)
def test_both_diagnostic_stages_fit_their_proposed_ceiling(stage):
    """The planned worst case is the composed path, and it fits."""
    definition = STAGE_DEFINITIONS[stage]
    assert definition.executable and definition.profile_id
    assert definition.profile_version == DIAGNOSTIC_PROFILE_VERSION
    assert definition.planned_minimum_operations <= definition.budget.max_operations
    assert definition.allowed_channels == ("file",)
    # Every step names a measurement the stage declares, and every measurement
    # is reachable from some step.
    declared = {item.id for item in definition.experiments}
    assert {item.experiment_id for item in definition.steps} <= declared


def test_the_composed_worst_cases_are_pinned_not_only_below_the_ceiling():
    """A loose less-than assertion cannot detect a missing nested call.

    GF-R4: the D-WEB figure is recomputed from the bounded compositions
    instead of from their fastest observed path. The ping is one dispatch,
    its bounded inspections and one attribution read; a registered
    spanning-tree sample is capped at its own channel call budget rather than
    at the four calls an instantly answered stub happened to make.
    """
    assert STAGE_DEFINITIONS[QualificationStage.D_DHCP].planned_minimum_operations == 45
    d_web = STAGE_DEFINITIONS[QualificationStage.D_WEB]
    assert d_web.planned_minimum_operations == 74
    per_experiment = {item.id: item.planned_operations for item in d_web.experiments}
    assert per_experiment["M-DWEB-1"] == 2 * D_WEB_FORWARDING_SAMPLE_CALLS + 1 == 13
    assert per_experiment["M-DWEB-3"] == 6 + D_WEB_PING_INSPECTIONS == 12
    assert per_experiment["M-DWEB-5"] == 2 + D_WEB_FORWARDING_SAMPLE_CALLS == 8


def test_the_declared_sample_bound_is_the_one_the_runtime_enforces():
    """A budget figure that the enforcing runtime does not share is a guess."""
    assert D_WEB_FORWARDING_SAMPLE_CALLS == ACCESS_FORWARDING_SAMPLE_CALLS


def test_the_ping_bound_is_the_one_the_production_probe_composes():
    """The stage pays for the inspections the composed executor may take."""
    taken: list[int | None] = []

    class _Recording(TypedPingExecutor):
        def __init__(self, *args, **kwargs):
            taken.append(kwargs.get("max_inspections"))
            super().__init__(*args, **kwargs)

    module = importlib.import_module(
        "packet_tracer_mcp.adapters.cli.service_qualification"
    )
    original = module.TypedPingExecutor
    module.TypedPingExecutor = _Recording
    try:
        module._forwarding_probe(_InertBound())
    finally:
        module.TypedPingExecutor = original
    assert taken == [D_WEB_PING_INSPECTIONS]


class _InertBound:
    """A ledgered transport stand-in; composing a probe dispatches nothing."""

    def send_and_wait(self, _script: str, _timeout: float) -> str | None:
        """Never called: this test only observes how the probe is composed."""
        raise AssertionError("composing a probe must not dispatch")

    @staticmethod
    def clock() -> float:
        """Return a fixed time; nothing here polls."""
        return 0.0

    @staticmethod
    def capped_sleep(_seconds: float) -> None:
        """Never sleep while composing."""


@pytest.mark.parametrize(
    ("overrides", "subject"),
    [
        ({"profile_id": ""}, RefusalSubject.AUTHORIZED_PROFILE),
        ({"profile_version": "0"}, RefusalSubject.AUTHORIZED_PROFILE),
        ({"profile_id": "D-OTHER"}, RefusalSubject.AUTHORIZED_PROFILE),
        ({"tree": ""}, RefusalSubject.AUTHORIZED_TREE),
        ({"tree": "not-a-tree"}, RefusalSubject.AUTHORIZED_TREE),
        ({"models": ()}, RefusalSubject.AUTHORIZED_MODELS),
        ({"links": ()}, RefusalSubject.AUTHORIZED_LINKS),
        ({"reserve_operations": None}, RefusalSubject.AUTHORIZED_RESERVE),
        ({"reserve_operations": 0}, RefusalSubject.AUTHORIZED_RESERVE),
        ({"reserve_operations": True}, RefusalSubject.AUTHORIZED_RESERVE),
        ({"instance_token": ""}, RefusalSubject.INSTANCE_TOKEN),
        ({"instance_token": "XYZ"}, RefusalSubject.INSTANCE_TOKEN),
        ({"attempt_id": ""}, RefusalSubject.ATTEMPT_IDENTITY),
        ({"attempt_id": "1" * 32}, RefusalSubject.ATTEMPT_IDENTITY),
        ({"process_id": None}, RefusalSubject.AUTHORIZED_PROCESS),
        ({"process_id": True}, RefusalSubject.AUTHORIZED_PROCESS),
        ({"process_id": 0}, RefusalSubject.AUTHORIZED_PROCESS),
        ({"process_path": ""}, RefusalSubject.AUTHORIZED_PROCESS),
        ({"step_ids": ()}, RefusalSubject.AUTHORIZED_STEPS),
    ],
)
def test_each_identity_binding_refuses_on_its_own(overrides, subject):
    """A missing or wrong binding is not compensated by the correct ones."""
    stage = QualificationStage.D_DHCP
    refusals = request_refusals(_request(stage, _authorization(stage, **overrides)))
    assert subject in _subjects(refusals)


def test_a_wrong_fixture_model_is_not_the_stage_fixture():
    """Names alone are not identity: the model each name resolves to is."""
    stage = QualificationStage.D_WEB
    definition = STAGE_DEFINITIONS[stage]
    swapped = (
        definition.fixture_models[0].split(":")[0] + ":PC-PT",
        *definition.fixture_models[1:],
    )
    refusals = request_refusals(_request(stage, _authorization(stage, models=swapped)))
    assert RefusalSubject.AUTHORIZED_MODELS in _subjects(refusals)


def test_a_wrong_link_port_is_not_the_stage_link():
    """The exact switch port each fixture lands on is part of the authority."""
    stage = QualificationStage.D_WEB
    definition = STAGE_DEFINITIONS[stage]
    moved = (
        definition.link_bindings[0].replace("/1", "/9"),
        *definition.link_bindings[1:],
    )
    refusals = request_refusals(_request(stage, _authorization(stage, links=moved)))
    assert RefusalSubject.AUTHORIZED_LINKS in _subjects(refusals)


def test_a_q_stage_binds_none_of_the_diagnostic_identity():
    """Scope a stage cannot honour is refused, not ignored."""
    definition = STAGE_DEFINITIONS[QualificationStage.Q3]
    authorization = QualificationAuthorization(
        authorization_id="TD-Q3-1",
        stage="Q3",
        sha=SHA,
        targets=definition.fixture_names,
        channel="file",
        build=BUILD,
        max_operations=definition.budget.max_operations,
        max_seconds=definition.budget.max_seconds,
        profile_id="D-DHCP",
    )
    request = QualificationRequest(
        execute=True,
        stage="Q3",
        expected_head=SHA,
        targets=definition.fixture_names,
        channel="file",
        packet_tracer_build=BUILD,
        authorization=authorization,
    )
    refusals = request_refusals(request)
    assert RefusalSubject.AUTHORIZED_PROFILE in _subjects(refusals)
    assert (
        request_refusals(
            replace(request, authorization=replace(authorization, profile_id=""))
        )
        == ()
    )


@pytest.mark.parametrize("stage", DIAGNOSTIC_STAGES)
def test_the_step_selection_must_be_ordered_complete_and_not_activation_only(stage):
    """Reordered, duplicated, incomplete and activation-only all refuse."""
    definition = STAGE_DEFINITIONS[stage]
    steps = definition.step_ids
    assert step_selection_refusals(definition, steps) == []
    assert step_selection_refusals(definition, ()) != []
    duplicated = step_selection_refusals(definition, (steps[0], steps[0]))
    assert any(item.kind is RefusalKind.MALFORMED for item in duplicated)
    unknown = step_selection_refusals(definition, ("not-a-step",))
    assert any(item.kind is RefusalKind.MALFORMED for item in unknown)
    reordered = step_selection_refusals(definition, (steps[1], steps[0]))
    assert any(item.kind is RefusalKind.MISMATCH for item in reordered)
    incomplete = step_selection_refusals(definition, (steps[0], steps[2]))
    assert any(item.kind is RefusalKind.INFEASIBLE for item in incomplete)
    activation = tuple(
        item.id for item in definition.steps if item.separately_authorized
    )
    assert activation
    refusals = step_selection_refusals(definition, activation)
    assert any(item.kind is RefusalKind.NOT_PERMITTED for item in refusals) or any(
        item.kind is RefusalKind.INFEASIBLE for item in refusals
    )


@pytest.mark.parametrize("stage", DIAGNOSTIC_STAGES)
def test_a_prefix_without_the_activation_is_a_coherent_selection(stage):
    """Leaving the activation out is a decision, not an incomplete authority."""
    definition = STAGE_DEFINITIONS[stage]
    chosen = tuple(
        item.id for item in definition.steps if not item.separately_authorized
    )
    # Only a prefix-closed subset is coherent, so drop anything that requires
    # a step this selection left out.
    selected: list[str] = []
    for item in definition.steps:
        if item.id in chosen and all(value in selected for value in item.requires):
            selected.append(item.id)
    assert step_selection_refusals(definition, tuple(selected)) == []
    assert (
        request_refusals(
            _request(stage, _authorization(stage, step_ids=tuple(selected)))
        )
        == ()
    )


def test_the_authorized_tree_is_compared_against_the_observed_one():
    """A commit names a history; the tree names the bytes that will execute."""
    observed = RepositoryIdentity(
        branch="feature/x", head=SHA, tree=TREE, clean=True, upstream_head=SHA
    )
    assert repository_refusals(observed, SHA, TREE) == ()
    refusals = repository_refusals(observed, SHA, "c" * 40)
    assert {item.subject for item in refusals} == {RefusalSubject.REPOSITORY_TREE}
    # A stage that binds no tree is unaffected by the new comparison.
    assert repository_refusals(observed, SHA) == ()


def test_the_local_lifecycle_must_match_the_exact_process_and_empty_mailbox():
    """A heartbeat is liveness; the local PID/path/build/mailbox bind identity."""
    authorization = _authorization(QualificationStage.D_WEB)
    observed = DiagnosticLifecycleObservation(
        process_id=PROCESS_ID,
        process_path=PROCESS_PATH,
        product_version=BUILD,
        process_incarnation=INCARNATION,
    )
    assert diagnostic_lifecycle_refusals(authorization, observed, BUILD) == ()

    wrong_pid = replace(observed, process_id=PROCESS_ID + 1)
    assert RefusalSubject.PROCESS_INSTANCE in _subjects(
        diagnostic_lifecycle_refusals(authorization, wrong_pid, BUILD)
    )
    wrong_path = replace(observed, process_path=PROCESS_PATH + ".other")
    assert RefusalSubject.PROCESS_INSTANCE in _subjects(
        diagnostic_lifecycle_refusals(authorization, wrong_path, BUILD)
    )
    wrong_build = replace(observed, product_version="9.0.0.0000")
    assert RefusalSubject.PROCESS_INSTANCE in _subjects(
        diagnostic_lifecycle_refusals(authorization, wrong_build, BUILD)
    )
    stale = replace(observed, mailbox_entries=("req_stale.js",))
    assert RefusalSubject.MAILBOX in _subjects(
        diagnostic_lifecycle_refusals(authorization, stale, BUILD)
    )


def test_an_unobservable_or_nonexclusive_process_is_not_a_pairing():
    """Zero, multiple or unreadable processes refuse before transport."""
    authorization = _authorization(QualificationStage.D_DHCP)
    observed = DiagnosticLifecycleObservation(error="multiple_processes:2")
    refusals = diagnostic_lifecycle_refusals(authorization, observed, BUILD)
    assert {(item.kind, item.subject) for item in refusals} == {
        (RefusalKind.UNOBSERVABLE, RefusalSubject.PROCESS_INSTANCE)
    }


def test_stage_definitions_still_answer_for_every_known_stage():
    """Adding stages never leaves `stage_definition` without an answer."""
    for stage in QualificationStage:
        assert stage_definition(stage.value) is not None
    assert stage_definition("D-OTHER") is None


def test_the_same_process_and_a_drained_mailbox_must_survive_finalization():
    """Pairing is preserved across the run, not asserted once before it.

    A Packet Tracer that crashes mid-run is replaced by a new instance that
    polls the same mailbox. Every later reading, cleanup included, would then
    attest a process this authority never bound, so the second reading is what
    decides whether the first one still describes the run that happened.
    """
    preflight = DiagnosticLifecycleObservation(
        process_id=PROCESS_ID,
        process_path=PROCESS_PATH,
        product_version=BUILD,
        process_incarnation=INCARNATION,
    )
    assert diagnostic_lifecycle_continuity(preflight, preflight) == ()

    replaced = replace(preflight, process_id=PROCESS_ID + 1)
    assert diagnostic_lifecycle_continuity(preflight, replaced) == (
        "process_instance:changed",
    )
    moved = replace(preflight, process_path=PROCESS_PATH + ".other")
    assert diagnostic_lifecycle_continuity(preflight, moved) == (
        "process_instance:changed",
    )
    rebuilt = replace(preflight, product_version="9.0.0.0000", file_version="")
    assert diagnostic_lifecycle_continuity(preflight, rebuilt) == (
        "process_instance:changed",
    )


def test_an_unreadable_second_reading_is_unknown_and_never_permission():
    """Zero, multiple or unreadable processes cannot confirm the first one."""
    preflight = DiagnosticLifecycleObservation(
        process_id=PROCESS_ID,
        process_path=PROCESS_PATH,
        product_version=BUILD,
        process_incarnation=INCARNATION,
    )
    lost = DiagnosticLifecycleObservation(error="packet_tracer_process_count:0")
    assert diagnostic_lifecycle_continuity(preflight, lost) == (
        "process_instance:unobservable:packet_tracer_process_count:0",
    )
    # A preflight that was never taken cannot be confirmed by anything.
    assert diagnostic_lifecycle_continuity(None, preflight) == (
        "process_instance:not_paired",
    )


def test_artifacts_left_in_the_mailbox_are_named_and_never_deleted_here():
    """Containment reports what a later instance could still re-execute."""
    preflight = DiagnosticLifecycleObservation(
        process_id=PROCESS_ID,
        process_path=PROCESS_PATH,
        product_version=BUILD,
        process_incarnation=INCARNATION,
    )
    undrained = replace(preflight, mailbox_entries=("req_7.js", "res_7.txt"))
    assert diagnostic_lifecycle_continuity(preflight, undrained) == (
        "mailbox:not_drained:req_7.js,res_7.txt",
    )
