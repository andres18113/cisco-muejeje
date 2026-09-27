"""Relay readback must settle before E5 can trigger remote DHCP traffic."""

from __future__ import annotations

from service_entry_fixture import FINGERPRINT
from sp1_routed_fixture import compose
from test_configuration_application import FakeConfigurationRuntime
from test_sp2_relay_composition import _remote_dhcp_payload

from packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import VerificationKind
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationRuntimeContext,
)
from packet_tracer_mcp.domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)


def _apply(
    relay_readback,
    *,
    refused_segment="",
    reader_raises=False,
    route_refused_segment="",
):
    payload, _ids = _remote_dhcp_payload()
    plans = compose(payload, services=False)
    plan = plans.configuration.model_copy(deep=True)
    # This test isolates phase ordering after capability admission. Product
    # admission still requires a separately recorded router relay capability.
    for action in plan.actions:
        action.required_capability = ""
    plan.semantic_hash = configuration_plan_semantic_hash(plan)
    runtime = FakeConfigurationRuntime(plans.composition.topology)
    runtime.verification_by_kind[VerificationKind.DHCP_RELAY] = relay_readback
    if reader_raises:
        original_verify = runtime.verify

        def interrupted_verify(expectations):
            if any(item.kind is VerificationKind.DHCP_RELAY for item in expectations):
                raise RuntimeError("relay reader disappeared")
            return original_verify(expectations)

        runtime.verify = interrupted_verify
    if refused_segment:
        original_verify = runtime.verify
        relay_by_expectation = {
            item.id: next(
                action.segment_id
                for action in plan.actions
                if action.id == item.action_id
            )
            for item in plan.verification_expectations
            if item.kind is VerificationKind.DHCP_RELAY
        }

        def verify_by_segment(expectations):
            rows = original_verify(expectations)
            for row in rows:
                if relay_by_expectation.get(row.expectation_id) == refused_segment:
                    row.status = ActionExecutionStatus.UNOBSERVABLE
            return rows

        runtime.verify = verify_by_segment

    def pre_dhcp_readiness(actions):
        runtime.events.append(("pre_dhcp_readiness", [item.id for item in actions]))
        return {item.id: item.segment_id != route_refused_segment for item in actions}

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities={},
        deployment_manifest=plans.manifest,
        runtime_context=ConfigurationRuntimeContext(
            environment_fingerprint=FINGERPRINT
        ),
        pre_dhcp_readiness=pre_dhcp_readiness,
    )
    return plan, runtime, result


def test_unreadable_helper_blocks_dhcp_mode_before_any_client_mutation():
    """A configured but unverified helper cannot authorize DHCP acquisition."""
    plan, runtime, result = _apply(ActionExecutionStatus.UNOBSERVABLE)
    dhcp_ids = {
        action.id
        for action in plan.actions
        if action.action_type.value == "set_endpoint_dhcp"
    }
    attempted = {identifier for batch in runtime.apply_calls for identifier in batch}
    assert dhcp_ids.isdisjoint(attempted)
    assert all(
        row.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for row in result.action_results
        if row.action_id in dhcp_ids
    )
    assert any(
        row.status is ActionExecutionStatus.UNOBSERVABLE
        for row in result.verification_results
        if row.action_id
        in {
            action.id
            for action in plan.actions
            if action.action_type.value == "configure_dhcp_relay"
        }
    )


def test_relay_reader_exception_is_unobserved_and_blocks_dhcp_mode():
    """A raised read cannot become evidence of an observed wrong helper."""
    plan, runtime, result = _apply(ActionExecutionStatus.VERIFIED, reader_raises=True)
    relay_ids = {
        action.id
        for action in plan.actions
        if action.action_type.value == "configure_dhcp_relay"
    }
    assert all(
        row.status is ActionExecutionStatus.UNOBSERVABLE
        for row in result.verification_results
        if row.action_id in relay_ids
    )
    dhcp_ids = {
        action.id
        for action in plan.actions
        if action.action_type.value == "set_endpoint_dhcp"
    }
    assert dhcp_ids.isdisjoint(
        {identifier for batch in runtime.apply_calls for identifier in batch}
    )


def test_verified_helper_is_read_before_the_dhcp_mode_effect():
    """The same exact helper proof permits the dependent phase to proceed."""
    plan, runtime, _result = _apply(ActionExecutionStatus.VERIFIED)
    dhcp_ids = {
        action.id
        for action in plan.actions
        if action.action_type.value == "set_endpoint_dhcp"
    }
    relay_expectations = {
        item.id
        for item in plan.verification_expectations
        if item.kind is VerificationKind.DHCP_RELAY
    }
    first_relay_read = next(
        index
        for index, (kind, ids) in enumerate(runtime.events)
        if kind == "verify" and relay_expectations.intersection(ids)
    )
    first_client_effect = next(
        index
        for index, (kind, ids) in enumerate(runtime.events)
        if kind == "apply" and dhcp_ids.intersection(ids)
    )
    assert first_relay_read < first_client_effect


def test_unreadable_branch_relay_does_not_block_independent_hq_clients():
    """A shared branch failure stays with the branch DHCP dependency group."""
    plan, runtime, result = _apply(
        ActionExecutionStatus.VERIFIED, refused_segment="br1-data"
    )
    segment_by_id = {
        action.id: action.segment_id
        for action in plan.actions
        if action.action_type.value == "set_endpoint_dhcp"
    }
    attempted = {identifier for batch in runtime.apply_calls for identifier in batch}
    assert {
        segment_by_id[identifier] for identifier in attempted & segment_by_id.keys()
    } == {"hq-data"}
    statuses = {
        segment_by_id[row.action_id]: row.status
        for row in result.action_results
        if row.action_id in segment_by_id
    }
    assert statuses == {
        "hq-data": ActionExecutionStatus.APPLIED,
        "br1-data": ActionExecutionStatus.DEPENDENCY_BLOCKED,
    }


def test_correct_helper_with_refused_return_path_blocks_branch_dhcp_mode():
    """A helper setter alone cannot authorize a remote DHCP acquisition."""
    plan, runtime, result = _apply(
        ActionExecutionStatus.VERIFIED,
        route_refused_segment="br1-data",
    )
    dhcp = {
        action.id: action.segment_id
        for action in plan.actions
        if action.action_type.value == "set_endpoint_dhcp"
    }
    attempted = {identifier for batch in runtime.apply_calls for identifier in batch}
    assert {dhcp[item] for item in attempted & dhcp.keys()} == {"hq-data"}
    assert any(kind == "pre_dhcp_readiness" for kind, _ids in runtime.events)
    assert all(
        row.status is ActionExecutionStatus.DEPENDENCY_BLOCKED
        for row in result.action_results
        if row.action_id in dhcp and dhcp[row.action_id] == "br1-data"
    )


def test_relay_effect_requires_an_explicit_model_capability_before_mutation():
    """A router's general routing capability never grants DHCP relay by proxy."""
    payload, _ids = _remote_dhcp_payload()
    plans = compose(payload, services=False)
    plan = plans.configuration.model_copy(deep=True)
    for action in plan.actions:
        if action.action_type.value != "configure_dhcp_relay":
            action.required_capability = ""
    plan.semantic_hash = configuration_plan_semantic_hash(plan)
    runtime = FakeConfigurationRuntime(plans.composition.topology)
    kwargs = {
        "actual_source_topology_hash": plan.source_topology_hash,
        "deployment_manifest": plans.manifest,
        "runtime_context": ConfigurationRuntimeContext(
            environment_fingerprint=FINGERPRINT
        ),
    }
    unknown = ConfigurationApplicator(runtime).apply(plan, capabilities={}, **kwargs)
    assert unknown.preflight_errors
    assert runtime.apply_calls == []

    router_model = next(
        device.model
        for device in plans.composition.topology.devices
        if device.category == "router"
    )
    admitted = DeviceCapabilities(model=router_model, category="router")
    admitted.supports_dhcp_relay = CapabilityStatus.SUPPORTED
    supported = ConfigurationApplicator(runtime).apply(
        plan, capabilities={router_model: admitted}, **kwargs
    )
    assert supported.preflight_errors == []
    assert any(runtime.apply_calls)
