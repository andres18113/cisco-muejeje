"""Configured cyclic trunks and current component forwarding are distinct claims."""

import json
from dataclasses import replace

import pytest
from test_configuration_runtime import _authoritative_trunk_result, _SequenceIos

from packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_configuration_runtime import (
    PacketTracerEnterpriseConfigurationRuntime,
)


def _table(*, allowed="10", active="10", forwarding="none"):
    return f"""SW#show interfaces trunk
Port Mode Encapsulation Status Native vlan
Gig0/1 on 802.1q trunking 1

Port Vlans allowed on trunk
Gig0/1 {allowed}

Port Vlans allowed and active in management domain
Gig0/1 {active}

Port Vlans in spanning tree forwarding state and not pruned
Gig0/1 {forwarding}
SW#"""


def _read(*, configured=True, allowed="10", active="10", fault="", scoped=True):
    kind = (
        getattr(VerificationKind, "TRUNK_CONFIGURATION", None)
        if configured
        else VerificationKind.TRUNK
    )
    assert kind is not None, (
        "A configured trunk has no distinct typed verification claim."
    )
    expected = {"interface": "GigabitEthernet0/1", "allowed_vlans": [10]}
    if configured and scoped:
        expected.update(component_vlans=[10], source_link_id="selected-component-link")
    expectation = VerificationExpectation(
        id="trunk-check",
        action_id="trunk-action",
        kind=kind,
        device_id="switch",
        device_name="SW",
        expected=expected,
        required_query="show_interfaces_trunk",
    )
    show = _authoritative_trunk_result(
        expectation, _table(allowed=allowed, active=active)
    )
    if fault == "foreign":
        show = replace(show, observed_device_name="OTHER")
    elif fault == "stale":
        show = replace(show, fresh_output_observed=False)
    elif fault == "incomplete":
        show = replace(show, output_complete=False)
    runtime = PacketTracerEnterpriseConfigurationRuntime(
        lambda: [],
        lambda _script: True,
        lambda _script, _timeout: None,
        trunk_timeout_seconds=0.0,
        convergence_interval_seconds=0.0,
    )
    runtime._ios = _SequenceIos([show])
    rows = runtime.verify([expectation])
    assert len(rows) == 1, "The declared kind must retain one typed observation."
    return rows[0]


def test_configured_trunk_retains_blocked_forwarding_without_claiming_it():
    """Only configured fields verify; the raw blocked forwarding set survives."""
    result = _read()

    assert result.status is ActionExecutionStatus.VERIFIED
    assert set(result.fields.values()) == {FieldVerificationStatus.VERIFIED}
    assert "forwarding_vlans" not in result.fields
    raw = json.loads(result.convergence.last_observable_state)
    assert raw["forwarding_vlans"] == []
    assert raw["verification_scope"] == "configured_trunk"
    assert raw["component_vlans"] == [10]
    assert raw["source_link_id"] == "selected-component-link"
    assert result.evidence_method == "fresh_show_interfaces_trunk_configuration"


def test_legacy_trunk_still_requires_its_vlan_to_forward():
    """The historical per-port forwarding contract stays strict."""
    result = _read(configured=False)

    assert result.status is ActionExecutionStatus.FAILED
    assert result.fields["forwarding_vlans"] is FieldVerificationStatus.FAILED
    assert result.evidence_method == "fresh_show_interfaces_trunk"


@pytest.mark.parametrize(
    "change",
    [
        {"allowed": "none"},
        {"active": "none"},
        {"fault": "foreign"},
        {"fault": "stale"},
        {"fault": "incomplete"},
    ],
)
def test_configured_trunk_unknown_or_wrong_configuration_does_not_verify(change):
    """Missing configuration or authority remains non-authorizing."""
    assert _read(**change).status is not ActionExecutionStatus.VERIFIED


def test_unscoped_configured_trunk_kind_cannot_inherit_a_component_claim():
    """A new kind needs its explicit component/VLAN/link scope."""
    assert _read(scoped=False).status is not ActionExecutionStatus.VERIFIED


def test_frozen_v1_service_composition_keeps_its_exact_strict_configuration():
    """Exact legacy manifest recognition preserves C31 verification semantics."""
    from test_hardware_planning_profiles import _frozen_bundle_manifest

    from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
        compose_enterprise_reference,
    )
    from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent

    bundle, manifest = _frozen_bundle_manifest()
    result = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(bundle.intent_json),
        packet_tracer_version=bundle.build,
        deployment_manifest=manifest,
        services=True,
    )

    assert result.configuration is not None, result.issues
    assert result.configuration.semantic_hash == bundle.configuration_semantic_hash
    trunks = [
        item
        for item in result.configuration.verification_expectations
        if item.required_query == "show_interfaces_trunk"
    ]
    assert len(trunks) == 10
    assert {item.kind for item in trunks} == {VerificationKind.TRUNK}
    assert result.configuration_policy.trunk_verification_mode == "per_port_forwarding"


def test_exact_v1_manifest_keeps_legacy_semantics_when_v2_selects_the_same_models():
    """Later scoped hardware evidence cannot change a frozen configuration contract."""
    from test_hardware_planning_profiles import _frozen_bundle_manifest
    from test_server_pt_commissioning import _qualified_trunk_catalog

    from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
        compose_enterprise_reference,
    )
    from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent

    bundle, manifest = _frozen_bundle_manifest()
    result = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(bundle.intent_json),
        packet_tracer_version=bundle.build,
        capability_catalog=_qualified_trunk_catalog(),
        deployment_manifest=manifest,
        services=True,
    )

    assert result.topology.physical_identity_hash == bundle.physical_topology_hash
    assert result.configuration.semantic_hash == bundle.configuration_semantic_hash
    assert result.configuration_policy.trunk_verification_mode == "per_port_forwarding"


def test_static_http_keeps_strict_trunks_and_its_existing_effect_scope():
    """DHCP's new component effects cannot enter an established static HTTP scope."""
    from campus_product_simulation import campus_payload, compose_campus

    from packet_tracer_mcp.application.use_cases.apply_enterprise_services import (
        _e5_closure,
    )

    plans = compose_campus(campus_payload(30))
    trunks = [
        item
        for item in plans.configuration_plan.verification_expectations
        if item.required_query == "show_interfaces_trunk"
    ]
    assert trunks
    assert {item.kind for item in trunks} == {VerificationKind.TRUNK}
    scope = _e5_closure(
        plans.configuration_plan, plans.service_plan, plans.service_plan.services
    )
    assert not any(
        item.action_type.value == "configure_trunk"
        for item in plans.configuration_plan.actions
        if item.id in scope
    )


def test_routed_index_legacy_default_does_not_add_cyclic_trunk_effects():
    """Component forwarding alone never enlarges a legacy routed effect grant."""
    from packet_tracer_mcp.adapters.cli.sp2_mixed_qualification import (
        sp2_capacity_product_contract,
    )
    from packet_tracer_mcp.application.use_cases.service_path_admission import (
        path_admission,
    )
    from packet_tracer_mcp.domain.enterprise.services.routed_service_path import (
        RoutedPlanIndex,
    )

    contract = sp2_capacity_product_contract("9.0.1.0858", "legacy-routed-scope")
    unsupported, paths = path_admission(
        contract.configuration_plan,
        contract.service_plan,
        contract.service_plan.services,
        links=contract.topology.links,
    )
    assert unsupported == []
    leg = next(path.host_leg for path in paths.values() if path.host_leg.cyclic)
    legacy_index = RoutedPlanIndex(
        contract.configuration_plan.actions, contract.topology.links
    )
    actual = legacy_index.leg(leg.endpoint_id, leg.attachment)
    assert actual.cyclic
    assert actual.trunk_action_ids == ()
