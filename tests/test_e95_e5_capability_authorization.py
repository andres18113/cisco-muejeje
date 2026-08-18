"""Stage 3A4 — E5 capability authorization: whole-batch preflight and evidence.

TD-CONFIG-CAPABILITY-001. MEG-4 run 4 compiled 17 required actions, resolved
twelve of them UNKNOWN before touching anything, and then **mutated a live
device anyway** with the one action that declares no capability requirement.
The transaction could never complete, and a real router was configured for it.

Two separate things are pinned here, and they must not be conflated:

* the **whole-batch rule**: if any REQUIRED action of a ConfigurationPlan is
  refused by the capability gate, the plan mutates nothing at all;
* the **evidence path**: the exact-version capability composition root reaches
  E5 compile and E5 application, so a capability decision is made from measured
  evidence for the exact build, or stays UNKNOWN.

`ConfigureSerialClock` is deliberately covered here too. It declares no generic
capability, and that is correct rather than a hole -- its authorization is
exact-version serial-clock evidence plus a manifest-bound observed DCE -- but
"authorized" never meant "may mutate while the batch is already lost".
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.apply_configuration import (
    ConfigurationApplicator,
)
from src.packet_tracer_mcp.application.use_cases.compile_configuration import (
    compile_enterprise_configuration,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationActionType,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
)

from test_configuration_application import (
    FakeConfigurationRuntime,
    _compiled,
    _supported_capabilities,
)
from test_enterprise_configuration import _fixture


# --------------------------------------------------------------------------
# whole-batch required preflight
# --------------------------------------------------------------------------


def test_a_required_capability_refusal_mutates_nothing_at_all():
    """El defecto que MEG-4 run 4 midio, en su forma minima."""
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=None,
    )

    assert runtime.apply_calls == []
    assert result.status is ConfigurationApplicationStatus.FAILED
    assert result.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
    assert result.preflight_errors
    assert result.action_results == []


def test_an_ungated_action_never_mutates_while_a_required_action_is_blocked():
    """La forma exacta de run 4: el reloj serial salia primero y mutaba."""
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    capabilities = _supported_capabilities()
    capabilities["2960-24TT"].supports_vlan = CapabilityStatus.UNKNOWN

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=capabilities,
    )
    ungated = [
        action for action in plan.actions
        if not action.required_capability
        or action.required_capability.startswith("endpoint_")
    ]

    assert ungated, "this fixture must contain an action the gate does not evaluate"
    assert runtime.apply_calls == []
    assert result.status is ConfigurationApplicationStatus.FAILED


def test_unsupported_stays_distinct_from_unknown_in_the_refusal():
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    capabilities = _supported_capabilities()
    capabilities["2960-24TT"].supports_vlan = CapabilityStatus.UNSUPPORTED

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=capabilities,
    )

    assert runtime.apply_calls == []
    assert result.failure_code is ConfigurationFailureCode.CAPABILITY_UNSUPPORTED
    assert any("unsupported" in message for message in result.preflight_errors)


def test_an_optional_action_is_skipped_without_stopping_the_batch():
    """`critical` es la distincion tipada que el modelo ya declara.

    Hasta ahora no la leia nadie, asi que REQUERIDA y OPCIONAL eran la misma
    cosa. Una accion declarada NO critica puede saltarse; una critica no.
    """
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    capabilities = _supported_capabilities()
    capabilities["2960-24TT"].supports_svi = CapabilityStatus.UNKNOWN
    svi_ids = {
        action.id
        for action in plan.actions_of_type(ConfigurationActionType.CONFIGURE_SVI)
    }
    optional = plan.model_copy(update={
        "actions": [
            action.model_copy(update={"critical": False})
            if action.id in svi_ids else action
            for action in plan.actions
        ],
    })

    result = ConfigurationApplicator(runtime).apply(
        optional,
        actual_source_topology_hash=optional.source_topology_hash,
        capabilities=capabilities,
    )
    by_id = {item.action_id: item for item in result.action_results}

    assert runtime.apply_calls
    assert all(by_id[item].status is ActionExecutionStatus.SKIPPED for item in svi_ids)
    assert all(
        by_id[item].failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN
        for item in svi_ids
    )
    vlan = plan.actions_of_type(ConfigurationActionType.CREATE_VLAN)
    assert all(by_id[action.id].status is ActionExecutionStatus.APPLIED for action in vlan)


def test_a_fully_authorized_plan_still_applies_and_verifies():
    """La regla de lote entero no puede volverse un rechazo universal."""
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert runtime.apply_calls
    assert result.status is ConfigurationApplicationStatus.VERIFIED
    assert all(
        item.status is ActionExecutionStatus.APPLIED
        for item in result.action_results
    )


def test_capability_authorization_never_fabricates_verification():
    """SUPPORTED autoriza; sigue haciendo falta la relectura para VERIFIED."""
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    runtime.verification_status = ActionExecutionStatus.UNOBSERVABLE

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=_supported_capabilities(),
    )

    assert result.status is not ConfigurationApplicationStatus.VERIFIED
    assert all(
        item.status is ActionExecutionStatus.APPLIED
        for item in result.action_results
    )


# --------------------------------------------------------------------------
# ConfigureSerialClock: its real contract, and what it does not imply
# --------------------------------------------------------------------------


def test_the_serial_clock_declares_no_generic_layer_capability():
    """No es un descuido: su autorizacion es de otra clase, y mas estrecha."""
    enterprise, topology, policy = _fixture()
    plan = compile_enterprise_configuration(enterprise, topology, policy).plan
    clocks = plan.actions_of_type(ConfigurationActionType.CONFIGURE_SERIAL_CLOCK)

    for action in clocks:
        assert action.required_capability == ""
        assert action.critical is True


def test_the_serial_clock_compile_demands_the_exact_measured_build():
    """`PT_2911_HWIC2T_SERIAL_CLOCK` es evidencia de version exacta."""
    enterprise, topology, policy = _fixture()

    with pytest.raises(ValueError, match="9.0.1.0858"):
        compile_enterprise_configuration(
            enterprise, topology, policy, packet_tracer_version="9.0.2.0000",
        )


def test_serial_clock_authorization_implies_no_vlan_or_layer3_permission():
    """Autorizar el reloj no reparte permisos a otras familias de accion."""
    topology, plan = _compiled()
    runtime = FakeConfigurationRuntime(topology)
    capabilities = _supported_capabilities()
    capabilities["2911"].layer3 = CapabilityStatus.UNKNOWN

    result = ConfigurationApplicator(runtime).apply(
        plan,
        actual_source_topology_hash=plan.source_topology_hash,
        capabilities=capabilities,
    )

    assert runtime.apply_calls == []
    assert result.failure_code is ConfigurationFailureCode.CAPABILITY_UNKNOWN


# --------------------------------------------------------------------------
# the evidence path reaches E5
# --------------------------------------------------------------------------


def _bounded_pieces():
    from test_e95_e5_capability_evidence import bounded_composition_inputs

    return bounded_composition_inputs()


def test_the_composition_publishes_the_capability_map_it_compiled_with():
    from test_e95_e5_capability_evidence import composed_with_store

    composed, store = composed_with_store()

    assert composed.capabilities
    assert set(composed.capabilities) == {
        device.model for device in composed.topology.devices
    }
    for model, profile in composed.capabilities.items():
        assert isinstance(profile, DeviceCapabilities)
        assert profile.model == model
