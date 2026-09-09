"""The extracted executor keeps typed authority and ordered stage effects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from importlib.util import find_spec

import pytest


def _api():
    # An assertion, rather than a collection error, records the missing slice.
    assert find_spec(
        "src.packet_tracer_mcp.application.cp_scale_live.stage_executor"
    ) is not None, "M2-A real typed stage executor has not been extracted"
    from src.packet_tracer_mcp.application.cp_scale_live.stage_executor import (
        CPScaleStageExecutor,
    )
    return CPScaleStageExecutor


def test_real_executor_orders_effects_and_preserves_typed_results():
    executor_type = _api()
    from tests.cp_scale_stage_fixture import stage_fixture

    fixture = stage_fixture(executor_type)
    result = fixture.executor.execute(fixture.request)

    assert fixture.trace == [
        "physical_delta", "configuration", "voice", "control_plane",
        "forwarding", "reconciliation", "workspace", "workspace",
    ]
    assert result.outcome == "verified"
    assert result.configuration is fixture.configuration_results[0]
    assert result.control_plane is fixture.control_results[0]
    assert result.configuration.source_topology_hash == "synthetic-physical"
    assert result.configuration.config_semantic_hash == "synthetic-configuration"
    assert result.replay_audit.verified
    assert result.workspace is fixture.workspaces[-1]
    assert result.continuity.previous_configuration is result.configuration
    assert result.continuity.previous_projection is fixture.request.projection
    with pytest.raises(FrozenInstanceError):
        result.continuity.previous_configuration = None


def test_partial_acceptance_is_not_promoted_and_unobservable_blocks_dependants():
    executor_type = _api()
    from tests.cp_scale_stage_fixture import stage_fixture

    fixture = stage_fixture(executor_type, partial=True)
    result = fixture.executor.execute(fixture.request)
    assert result.configuration_accepted
    assert result.configuration.status.value == "partial"
    assert result.configuration is fixture.configuration_results[0]

    blocked = stage_fixture(executor_type, unobservable=True)
    failure = blocked.executor.execute(blocked.request)
    assert failure.outcome == "failed"
    assert failure.first_failed_boundary == "configuration"
    assert failure.configuration is blocked.configuration_results[0]
    assert failure.configuration_attempts == (failure.configuration,)
    assert blocked.trace == ["physical_delta", "configuration"]
    assert failure.voice is None
    assert failure.control_plane is None


def test_reread_is_zero_mutation_and_runtime_journal_controls_replay_authority():
    executor_type = _api()
    from tests.cp_scale_stage_fixture import stage_fixture

    fixture = stage_fixture(executor_type, reread=True)
    result = fixture.executor.execute(fixture.request)
    assert result.outcome == "verified"
    assert fixture.configuration_runtime.apply_calls == [["hostname"]]
    assert len(result.configuration_attempts) == 2
    assert result.configuration_attempts[1].mutation_action_ids == []
    assert result.configuration_attempts[1].retained_action_ids == ["hostname"]
    assert result.replay_audit.verified

    forged = stage_fixture(executor_type, omit_journal=True)
    result = forged.executor.execute(forged.request)
    assert result.replay_audit.verified is False
    assert result.replay_audit.claim != "NO_MUTATION_REPLAY"


def test_continuation_retains_results_and_hashes_without_replaying_actions():
    executor_type = _api()
    from tests.cp_scale_stage_fixture import stage_fixture

    fixture = stage_fixture(executor_type)
    first = fixture.executor.execute(fixture.request)
    second = fixture.executor.execute(replace(
        fixture.request, continuity=first.continuity,
    ))
    assert second.outcome == "verified"
    assert fixture.configuration_runtime.apply_calls == [["hostname"]]
    assert second.configuration.retained_action_ids == ["hostname"]
    assert second.replay_audit.verified


def test_physical_failure_preserves_partial_evidence_before_any_application():
    executor_type = _api()
    from tests.cp_scale_stage_fixture import stage_fixture
    from src.packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
        PhysicalDeploymentStatus,
    )

    fixture = stage_fixture(executor_type)
    request = replace(fixture.request, deployment=fixture.request.deployment.model_copy(
        update={"status": PhysicalDeploymentStatus.FAILED, "errors": ["refused"]},
    ))
    result = fixture.executor.execute(request)
    assert result.outcome == "failed"
    assert result.first_failed_boundary == "physical_delta"
    assert result.configuration is None
    assert result.projection is request.projection
    assert result.deployment is request.deployment
    assert fixture.trace == []


def test_unexpected_read_failure_preserves_the_typed_attempt_and_first_boundary():
    executor_type = _api()
    from tests.cp_scale_stage_fixture import stage_fixture

    fixture = stage_fixture(executor_type)
    def broken_read(projection):
        raise RuntimeError("serial read exploded")
    fixture.executor.configuration.serial_wait = broken_read
    result = fixture.executor.execute(fixture.request)
    assert result.first_failed_boundary == "configuration"
    assert result.configuration is fixture.configuration_results[0]
    assert result.configuration_attempts == (result.configuration,)
    assert "serial read exploded" in result.failure
    assert fixture.trace == ["physical_delta", "configuration"]


def test_ping_result_is_the_same_neutral_value_at_the_legacy_import():
    assert find_spec("src.packet_tracer_mcp.domain.models.typed_ping") is not None
    from src.packet_tracer_mcp.domain.models.typed_ping import TypedPingResult
    from src.packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingResult as LegacyResult
    assert TypedPingResult is LegacyResult
    result = LegacyResult(False, False)
    assert result.device_identity_provenance == "not_observed"
    assert result.device_identity_evidence == "none"


def test_forwarding_retains_each_typed_attempt_with_its_exact_planned_authority():
    from src.packet_tracer_mcp.infrastructure.observation.cp_scale_live import PacketTracerCPScaleObservations
    from src.packet_tracer_mcp.domain.models.typed_ping import TypedPingResult
    from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import CPScaleSiteForwardingCheck, CPScaleForwardingAuthority

    check = CPScaleSiteForwardingCheck(
        id="synthetic-forward", source_device_id="r", source_device_name="R",
        destination_device_id="p", destination_device_name="P", destination_ipv4="10.1.0.2",
        destination_segment_id="lab", authority=CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW,
        direction="forward", declared_traffic_flow_id="flow/lab", reverse_of_traffic_flow_id="",
        source_site_id="source", destination_site_id="lab", destination_router_id="router/lab",
        destination_action_id="address/p", source_topology_hash="physical", source_configuration_hash="configuration",
    )
    replies = [TypedPingResult(False, False), TypedPingResult(
        True, True, dispatched_destination="10.1.0.2", observed_device_name="R",
        device_identity_provenance="confirmed_unique",
    )]
    dispatched = []
    class Ping:
        def ping(self, source, destination):
            dispatched.append((source, destination))
            return replies[len(dispatched) - 1]
    observer = PacketTracerCPScaleObservations.__new__(PacketTracerCPScaleObservations)
    observer.ping = Ping()
    observed = observer.site_forwarding((check,))
    assert len(observed) == 1
    assert observed[0].check is check
    assert observed[0].attempts == tuple(replies)
    assert observed[0].attempts[1] is replies[1]
    assert observed[0].verified
    assert dispatched == [("R", "10.1.0.2"), ("R", "10.1.0.2")]


@pytest.mark.parametrize("drain_raises", [False, True])
def test_real_voice_collaborator_preserves_deferred_signal_and_lifecycle_order(drain_raises):
    from types import SimpleNamespace
    from src.packet_tracer_mcp.application.cp_scale_live.voice_stage import CPScaleVoiceStage
    from src.packet_tracer_mcp.application.use_cases.apply_voice import VoiceApplicator
    from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import ActionExecutionStatus, ConfigurationRuntimeContext
    from tests.test_voice_runtime import FakeVoiceRuntime, _compile, _profile

    plan = _compile().plan
    runtime = FakeVoiceRuntime()
    if drain_raises:
        def broken_diagnostic_drain():
            raise RuntimeError("diagnostic drain unavailable")
        runtime.drain_diagnostic_evidence = broken_diagnostic_drain
    events = []
    statuses = {
        item.source_id: ActionExecutionStatus.PARTIAL if item.kind == "voice_vlan" else ActionExecutionStatus.VERIFIED
        for item in plan.foundational_requirements
    }
    projection = SimpleNamespace(
        voice=plan, stage=SimpleNamespace(value="synthetic-voice"),
        topology=SimpleNamespace(physical_identity_hash=plan.source_topology_hash),
        configuration=SimpleNamespace(semantic_hash=plan.source_configuration_hash),
    )
    result = CPScaleVoiceStage(VoiceApplicator(runtime), runtime).apply(
        projection, composition=SimpleNamespace(voice_capabilities=_profile()),
        configuration=None, statuses=statuses, context=ConfigurationRuntimeContext(), manifest=None,
        complete_voice_signal=lambda: {item.source_id: ActionExecutionStatus.VERIFIED for item in plan.foundational_requirements},
        lifecycle_observer=events.append,
    )
    assert result.result.status is ActionExecutionStatus.VERIFIED
    assert result.error == ""
    if drain_raises:
        assert result.runtime_diagnostics.error == "RuntimeError: diagnostic drain unavailable"
    assert events == [
        "VOICE_BOOTSTRAP_STARTED", "VOICE_BOOTSTRAP_APPLIED",
        "DEFERRED_VOICE_COMPLETION_STARTED", "DEFERRED_VOICE_COMPLETION_VERIFIED",
        "REGISTRATION_STARTED", "REGISTRATION_COMPLETED",
    ]


def test_diagnostic_exception_never_replaces_the_acquired_voice_cause():
    from tests.cp_scale_stage_fixture import voice_window_trace

    result, trace = voice_window_trace(diagnostic_raises=True)
    assert result.first_failed_boundary == "voice"
    assert result.failure == "Voice at 'routing-core' did not close: primary voice contradiction"
    assert result.diagnostics[0].error == "RuntimeError: secondary diagnostic failure"
    assert result.diagnostics[0].authority == "DIAGNOSTIC_ONLY"
    assert trace[-2:] == ["bindings", "diagnostic"]


def test_a_second_synthetic_target_uses_its_own_sequence_and_acceptance_policy():
    executor_type = _api()
    from tests.cp_scale_stage_fixture import stage_fixture
    from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
        CPScaleCanonicalStage, CPScaleCanonicalTarget, canonical_cp_scale_target_contract,
    )

    target = replace(canonical_cp_scale_target_contract(CPScaleCanonicalTarget.ROUTER0_BRANCH),
        build_stages=(CPScaleCanonicalStage.FLOOR3, CPScaleCanonicalStage.ROUTING_CORE))
    fixture = stage_fixture(executor_type, partial=True)
    continuity = fixture.request.continuity
    completed = []
    for stage in target.build_stages:
        result = fixture.executor.execute(replace(
            fixture.request, projection=replace(fixture.request.projection, stage=stage), continuity=continuity,
        ))
        assert result.outcome == "verified"
        assert result.configuration.status.value == "partial"
        assert result.configuration_accepted
        assert fixture.request.configuration_attempt_limit == 2
        assert fixture.request.required_observation_limit == 6
        assert fixture.request.diagnostic_attempt_limit == 0
        assert len(result.configuration_attempts) <= fixture.request.configuration_attempt_limit
        assert len(result.required_observations) <= fixture.request.required_observation_limit
        assert len(result.diagnostics) <= fixture.request.diagnostic_attempt_limit
        completed.append(result.stage.value)
        continuity = result.continuity
    assert completed == ["floor3", "routing-core"]
    assert fixture.configuration_runtime.apply_calls == [["hostname"]]


def test_second_workspace_exception_keeps_the_first_accumulated_readback():
    from tests.cp_scale_stage_fixture import stage_fixture
    fixture = stage_fixture(_api())
    observed = fixture.executor.observations.workspace
    def workspace():
        if fixture.workspaces:
            raise RuntimeError("second workspace unavailable")
        return observed()
    fixture.executor.observations.workspace = workspace
    result = fixture.executor.execute(fixture.request)
    assert result.first_failed_boundary == "reconciliation"
    assert result.report.workspace_first is fixture.workspaces[0]
    assert result.configuration is fixture.configuration_results[0]
    assert result.report.workspace_second is None
    assert "second workspace unavailable" in result.failure


@pytest.mark.parametrize("malformation", ["omitted", "duplicate", "substituted", "equal_copy", "reordered", "no_attempt", "unobservable"])
def test_forwarding_port_cannot_verify_an_omitted_declared_check(malformation):
    from types import SimpleNamespace
    from tests.cp_scale_stage_fixture import stage_fixture
    from src.packet_tracer_mcp.application.cp_scale_live.forwarding_stage import CPScaleForwardingStage
    from src.packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleSiteForwardingObservation
    from src.packet_tracer_mcp.domain.models.typed_ping import TypedPingResult
    from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import CPScaleSiteForwardingCheck, CPScaleForwardingAuthority

    fixture = stage_fixture(_api())
    check = CPScaleSiteForwardingCheck(
        "missing-check", "forward", CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW,
        "flow", "", "a", "b", "r", "R", "p", "P", "router", "address", "segment",
        "10.1.0.2", "synthetic-physical", "synthetic-configuration",
    )
    other = replace(check, id="other-check")
    reply = TypedPingResult(True, True, dispatched_destination=check.destination_ipv4,
        observed_device_name=check.source_device_name, device_identity_provenance="confirmed_unique")
    observed = CPScaleSiteForwardingObservation(check, (reply,), True)
    second = CPScaleSiteForwardingObservation(other, (reply,), True)
    malformed = {
        "omitted": (second,), "duplicate": (observed, observed),
        "substituted": (replace(observed, check=replace(check, declared_traffic_flow_id="forged")), second),
        "equal_copy": (replace(observed, check=replace(check)), second),
        "reordered": (second, observed), "no_attempt": (replace(observed, attempts=()), second),
        "unobservable": (replace(observed, attempts=(TypedPingResult(False, False),)), second),
    }[malformation]
    result = CPScaleForwardingStage(SimpleNamespace(
        core_forwarding=lambda checks: (), site_forwarding=lambda checks: malformed,
    )).execute(replace(fixture.request, site_forwarding_checks=(check, other)))
    assert result.verified is False
    assert result.first_failure == ("other-check" if malformation == "duplicate" else "missing-check")
