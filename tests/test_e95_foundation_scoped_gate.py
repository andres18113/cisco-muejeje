"""Stage 3A4 — the E5→E9 gate is scoped to the foundations the plan declares.

MEG-4 run 5 applied all seventeen configuration actions and verified every
foundation the bounded RIPv2 `ControlPlanePlan` declares. It stopped anyway,
because the product gated on the **aggregate** `ConfigurationApplicationResult`
status, which falls to PARTIAL the moment any single read-back is UNOBSERVABLE —
even for an action nothing downstream depends on.

`TD-ACCEPTANCE-001` row 4 asks for something narrower: *statuses and hashes
produced by `apply_configuration` from real readback, so `ControlPlaneApplicator`'s
gate decides on evidence instead of on an assertion*. That gate already exists
and is already strict: `_foundation_errors` refuses unless every declared
foundation is VERIFIED, before it touches the runtime.

So this is claim **scoping**, not claim reduction, and these tests pin both
halves of it:

* evidence that is not a prerequisite keeps its truthful state — UNOBSERVABLE
  stays UNOBSERVABLE, PARTIAL stays PARTIAL, and the aggregate is never
  rewritten — and does not block;
* every declared foundation must still be VERIFIED, and anything less blocks
  E9 with zero mutation.

Nothing here promotes a status. Nothing here hardcodes the bounded topology's
ids or counts: the required set is read from the typed plan.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    EnterpriseExecutionStage,
    EnterpriseExecutionStatus,
    EnterpriseRuntimes,
    execute_enterprise_reference,
)
from src.packet_tracer_mcp.application.use_cases.foundational_evidence import (
    derive_foundational_statuses,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    VerificationKind,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import VoiceIntent

from test_e95_e5_capability_evidence import (
    BOUNDED_REQUIREMENTS,
    MEASURED_VERSION,
    _probe,
    _store,
)
from test_enterprise_reference_execution import _isolated_preflight
from test_stage3a4_offline_adversarial_matrix import (
    FINGERPRINT,
    _bounded_intent,
    _control_plane_intent,
    _GenericOrientationRuntime,
    _GenericPhysicalRuntime,
    _QUALIFIED,
)

#: La forma de verificacion medida en MEG-4 run 5, por tipo de expectativa.
RUN5_SHAPE = {
    VerificationKind.VLAN: ActionExecutionStatus.VERIFIED,
    VerificationKind.SERIAL_CONTROLLER: ActionExecutionStatus.VERIFIED,
    VerificationKind.L3_INTERFACE: ActionExecutionStatus.VERIFIED,
    VerificationKind.ACCESS_PORT: ActionExecutionStatus.UNOBSERVABLE,
    VerificationKind.ENDPOINT_ADDRESSING: ActionExecutionStatus.PARTIAL,
}


class _ShapedConfigurationRuntime:
    """Aplica todo y devuelve la verificacion medida, por tipo de expectativa.

    El inventario se sintetiza con la MISMA identidad que el runtime fisico
    falso publica en el manifiesto, porque de otro modo la resolucion de
    objetivos falla antes de llegar a lo que estos tests miden.
    """

    def __init__(self, physical, topology, shape=None) -> None:
        self._physical = physical
        self._topology = topology
        self._shape = dict(RUN5_SHAPE if shape is None else shape)
        self.apply_calls: list[list[str]] = []
        self.verify_calls: list[list[str]] = []

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        return [
            RuntimeConfigurationTarget(
                device_name=device.name,
                model=device.model,
                interfaces=sorted(self._physical._interfaces_for(device.name)),
                runtime_identifier=f"runtime-{device.id}",
                runtime_identifier_stable=True,
                runtime_fingerprint=f"fp-{device.id}",
            )
            for device in self._topology.devices
        ]

    def apply_actions(self, actions):
        self.apply_calls.append([action.id for action in actions])
        return [
            RuntimeActionMutation(action_id=action.id, applied=True, message="applied")
            for action in actions
        ]

    def verify(self, expectations):
        self.verify_calls.append([item.id for item in expectations])
        results = []
        for item in expectations:
            status = self._shape.get(item.kind, ActionExecutionStatus.UNOBSERVABLE)
            field = {
                ActionExecutionStatus.VERIFIED: FieldVerificationStatus.VERIFIED,
                ActionExecutionStatus.FAILED: FieldVerificationStatus.FAILED,
            }.get(status, FieldVerificationStatus.UNOBSERVABLE)
            results.append(RuntimeVerification(
                expectation_id=item.id,
                status=status,
                evidence_method="shaped_fake",
                fresh_evidence=status is ActionExecutionStatus.VERIFIED,
                fields={name: field for name in item.expected},
            ))
        return results


class _RecordingControlPlaneRuntime:
    """Registra si E9 llego siquiera a pedir inventario."""

    def __init__(self) -> None:
        self.inventory_calls = 0
        self.mutations = 0

    def inventory(self):
        self.inventory_calls += 1
        return []

    def __getattr__(self, name):
        def _record(*_args, **_kwargs):
            self.mutations += 1
            raise AssertionError(f"control_plane.{name} was reached")
        return _record


class _EmptyVoiceRuntime:
    """Exercises the governed voice stage without fabricating phone behavior."""

    def inventory(self):
        return []

    def apply_actions(self, actions):
        assert actions == []
        return []

    def observe_registration(self, expectation):
        raise AssertionError("an empty voice plan has no registration expectations")

    def verify_call(self, expectation, call_attempt_id, started_ns):
        raise AssertionError("an empty voice plan has no call expectations")


@pytest.fixture
def measured_store(tmp_path):
    return _store(tmp_path, "measured", [
        _probe(model, capability) for model, capability in BOUNDED_REQUIREMENTS
    ])


def _compose(store):
    intent = _bounded_intent()
    topology = compose_enterprise_reference(
        intent, policy=_QUALIFIED, packet_tracer_version=MEASURED_VERSION,
        capability_store=store,
    ).topology
    return intent, topology, _control_plane_intent(topology)


def _run(store, *, shape=None, preexisting=None):
    intent, topology, control_plane_intent = _compose(store)
    physical = _GenericPhysicalRuntime(preexisting=preexisting or [])
    physical.bind(topology)
    configuration = _ShapedConfigurationRuntime(physical, topology, shape)
    control_plane = _RecordingControlPlaneRuntime()
    result = execute_enterprise_reference(
        intent,
        EnterpriseRuntimes(
            physical=physical,
            serial_orientation=_GenericOrientationRuntime(),
            configuration=configuration,
            control_plane=control_plane,
        ),
        control_plane_intent,
        environment_fingerprint=FINGERPRINT,
        import_preflight=_isolated_preflight(),
        packet_tracer_version=MEASURED_VERSION,
        capability_store=store,
        policy=_QUALIFIED,
    )
    return result, physical, configuration, control_plane


def _required_kinds(result):
    return sorted({
        requirement.kind
        for requirement in result.composition.control_plane.foundational_requirements
    })


# --------------------------------------------------------------------------
# what the typed plan actually requires
# --------------------------------------------------------------------------


def test_the_required_foundation_set_comes_from_the_typed_plan(measured_store):
    """Derivado del plan compilado, no de una lista escrita a mano."""
    result, _physical, _configuration, _control_plane = _run(measured_store)
    requirements = result.composition.control_plane.foundational_requirements

    assert requirements
    assert set(_required_kinds(result)) == {"l3_interface", "link"}
    assert "access_port" not in _required_kinds(result)
    assert "endpoint_address" not in _required_kinds(result)


def test_every_required_foundation_resolves_to_an_executed_status(measured_store):
    """Una fundacion sin entrada seria ausencia, y la ausencia bloquea."""
    result, _physical, _configuration, _control_plane = _run(measured_store)
    required = {
        item.source_id
        for item in result.composition.control_plane.foundational_requirements
    }

    assert required <= set(result.foundational_statuses)
    assert all(
        result.foundational_statuses[item] is ActionExecutionStatus.VERIFIED
        for item in required
    )


# --------------------------------------------------------------------------
# scoped, not reduced
# --------------------------------------------------------------------------


def test_a_not_fully_verified_configuration_still_reaches_the_control_plane(measured_store):
    """El caso exacto de run 5, que el gate agregado detenia."""
    result, _physical, _configuration, control_plane = _run(measured_store)

    assert result.configuration_result.status is ConfigurationApplicationStatus.PARTIAL
    assert control_plane.inventory_calls == 1
    assert result.control_plane_result is not None
    assert (
        result.control_plane_result.failure_code
        is not ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    )


def test_bounded_voice_observation_runs_before_control_plane_without_promotion(
    measured_store,
):
    intent, topology, control_plane_intent = _compose(measured_store)
    physical = _GenericPhysicalRuntime().bind(topology)
    configuration = _ShapedConfigurationRuntime(physical, topology)
    control_plane = _RecordingControlPlaneRuntime()

    result = execute_enterprise_reference(
        intent,
        EnterpriseRuntimes(
            physical=physical,
            serial_orientation=_GenericOrientationRuntime(),
            configuration=configuration,
            control_plane=control_plane,
            voice=_EmptyVoiceRuntime(),
        ),
        control_plane_intent,
        environment_fingerprint=FINGERPRINT,
        import_preflight=_isolated_preflight(),
        packet_tracer_version=MEASURED_VERSION,
        capability_store=measured_store,
        policy=_QUALIFIED,
        voice_intent=VoiceIntent(id="voice/bounded-observation"),
    )

    assert result.voice_result is not None
    assert result.voice_result.status is ActionExecutionStatus.PARTIAL
    stages = [item.stage for item in result.stage_metrics]
    assert stages.index(EnterpriseExecutionStage.VOICE_APPLY) < stages.index(
        EnterpriseExecutionStage.CONTROL_PLANE_APPLY,
    )
    assert control_plane.inventory_calls == 1


def test_the_aggregate_configuration_status_is_never_rewritten(measured_store):
    """Seguir no reescribe la evidencia: el agregado sigue diciendo la verdad."""
    result, _physical, _configuration, _control_plane = _run(measured_store)
    statuses = {
        item.status for item in result.configuration_result.verification_results
    }

    assert result.configuration_result.status is ConfigurationApplicationStatus.PARTIAL
    assert ActionExecutionStatus.UNOBSERVABLE in statuses
    assert ActionExecutionStatus.PARTIAL in statuses


def test_access_port_stays_unobservable_and_does_not_block(measured_store):
    result, _physical, _configuration, control_plane = _run(measured_store)
    access = [
        item for item in result.configuration_result.verification_results
        if item.status is ActionExecutionStatus.UNOBSERVABLE
    ]

    assert access
    assert all(
        value is FieldVerificationStatus.UNOBSERVABLE
        for item in access for value in item.fields.values()
    )
    assert control_plane.inventory_calls == 1


def test_endpoint_addressing_stays_partial_and_does_not_block(measured_store):
    result, _physical, _configuration, control_plane = _run(measured_store)
    endpoints = [
        item for item in result.configuration_result.verification_results
        if item.status is ActionExecutionStatus.PARTIAL
    ]

    assert endpoints
    assert control_plane.inventory_calls == 1


# --------------------------------------------------------------------------
# every declared foundation still has to be VERIFIED
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [
    ActionExecutionStatus.UNOBSERVABLE,
    ActionExecutionStatus.PARTIAL,
    ActionExecutionStatus.FAILED,
])
def test_a_required_l3_foundation_short_of_verified_blocks_e9(measured_store, status):
    shape = {**RUN5_SHAPE, VerificationKind.L3_INTERFACE: status}

    result, _physical, _configuration, control_plane = _run(measured_store, shape=shape)

    assert result.status is EnterpriseExecutionStatus.FAILED
    assert control_plane.inventory_calls == 0
    assert control_plane.mutations == 0


def test_a_verified_but_unrelated_action_cannot_substitute_for_a_foundation(measured_store):
    """VLAN y reloj serial siguen VERIFIED; no cubren la fundacion faltante."""
    shape = {
        **RUN5_SHAPE,
        VerificationKind.L3_INTERFACE: ActionExecutionStatus.UNOBSERVABLE,
    }

    result, _physical, _configuration, control_plane = _run(measured_store, shape=shape)
    verified = [
        item for item in result.configuration_result.verification_results
        if item.status is ActionExecutionStatus.VERIFIED
    ]

    assert verified, "the fixture must still contain verified, non-foundational rows"
    assert result.status is EnterpriseExecutionStatus.FAILED
    assert control_plane.inventory_calls == 0


def test_a_required_link_foundation_that_was_not_observed_blocks_e9(measured_store):
    """La fundacion de enlace viene del despliegue fisico, no de E5."""
    intent, topology, control_plane_intent = _compose(measured_store)
    physical = _GenericPhysicalRuntime()
    physical.bind(topology)
    configuration = _ShapedConfigurationRuntime(physical, topology)
    control_plane = _RecordingControlPlaneRuntime()
    statuses = derive_foundational_statuses(physical_result=None, configuration_result=None)

    assert statuses == {}

    original = physical.observe_link

    def unobserved_link(link):
        observation = original(link)
        return observation.model_copy(update={"observed": False})

    physical.observe_link = unobserved_link
    result = execute_enterprise_reference(
        intent,
        EnterpriseRuntimes(
            physical=physical, serial_orientation=_GenericOrientationRuntime(),
            configuration=configuration, control_plane=control_plane,
        ),
        control_plane_intent,
        environment_fingerprint=FINGERPRINT,
        import_preflight=_isolated_preflight(),
        packet_tracer_version=MEASURED_VERSION,
        capability_store=measured_store,
        policy=_QUALIFIED,
    )

    assert result.status is EnterpriseExecutionStatus.FAILED
    assert control_plane.inventory_calls == 0
    assert control_plane.mutations == 0


def test_no_foundational_status_is_ever_supplied_rather_than_derived():
    """`derive_foundational_statuses` no tiene por donde recibir un estado."""
    import inspect

    signature = inspect.signature(derive_foundational_statuses)

    assert set(signature.parameters) == {"configuration_result", "physical_result"}
    assert derive_foundational_statuses() == {}


# --------------------------------------------------------------------------
# a contradiction is not an absence
# --------------------------------------------------------------------------


def test_a_failed_configuration_verification_still_stops_before_the_control_plane(
    measured_store,
):
    """UNOBSERVABLE es no haber mirado; FAILED es haber visto lo contrario."""
    shape = {**RUN5_SHAPE, VerificationKind.VLAN: ActionExecutionStatus.FAILED}

    result, _physical, _configuration, control_plane = _run(measured_store, shape=shape)

    assert result.stopped_at is EnterpriseExecutionStage.CONFIGURATION_APPLY
    assert result.status is EnterpriseExecutionStatus.FAILED
    assert control_plane.inventory_calls == 0
    assert any("contradict" in message.casefold() for message in result.errors)


# --------------------------------------------------------------------------
# what a foundation refusal may not touch
# --------------------------------------------------------------------------


def test_a_foundation_refusal_preserves_the_e4_identity_and_cleans_up(measured_store):
    shape = {**RUN5_SHAPE, VerificationKind.L3_INTERFACE: ActionExecutionStatus.FAILED}

    result, physical, _configuration, _control_plane = _run(measured_store, shape=shape)

    assert result.e4_identity_preserved is True
    assert result.cleanup_results
    assert result.final_inventory is not None
    assert physical.calls.count("observe_workspace") >= 2


def test_a_foundation_refusal_never_removes_foreign_objects(measured_store):
    shape = {**RUN5_SHAPE, VerificationKind.L3_INTERFACE: ActionExecutionStatus.FAILED}

    result, physical, _configuration, _control_plane = _run(measured_store, shape=shape)
    planned = {item.name for item in result.composition.topology.devices}

    assert set(physical.removed) <= planned
    assert "Power Distribution Device0" not in physical.removed


def test_a_refused_control_plane_is_never_reported_as_a_completed_run(measured_store):
    """El hueco que el gate agregado tapaba.

    `ControlPlaneApplicator` se negaba en preflight con
    FOUNDATIONAL_CONFIGURATION_MISSING y `execute_enterprise_reference` devolvia
    COMPLETED igual, porque nadie miraba el resultado de E9. No se veia mientras
    el gate de E5 impedia llegar hasta aca con fundaciones malas.
    """
    shape = {**RUN5_SHAPE, VerificationKind.L3_INTERFACE: ActionExecutionStatus.UNOBSERVABLE}

    result, _physical, _configuration, control_plane = _run(measured_store, shape=shape)

    assert result.control_plane_result is not None
    assert (
        result.control_plane_result.failure_code
        is ConfigurationFailureCode.FOUNDATIONAL_CONFIGURATION_MISSING
    )
    assert result.status is EnterpriseExecutionStatus.FAILED
    assert result.stopped_at is EnterpriseExecutionStage.CONTROL_PLANE_APPLY
    assert result.errors
    assert control_plane.inventory_calls == 0


def test_forwarding_evidence_can_never_substitute_for_a_missing_foundation(measured_store):
    """E9 no llega a mirar comportamiento si una fundacion no esta VERIFIED.

    El runtime de plano de control revienta ante cualquier metodo que no sea
    `inventory`, asi que si el gate dejara pasar, la corrida moriria ahi. Muere
    antes, y sin haber pedido inventario siquiera.
    """
    for status in (
        ActionExecutionStatus.FAILED, ActionExecutionStatus.UNOBSERVABLE,
    ):
        shape = {**RUN5_SHAPE, VerificationKind.L3_INTERFACE: status}

        result, _physical, _configuration, control_plane = _run(
            measured_store, shape=shape,
        )

        assert control_plane.inventory_calls == 0
        assert control_plane.mutations == 0
        assert result.status is EnterpriseExecutionStatus.FAILED
        # Ninguna afirmacion de comportamiento llega a existir: o E9 no se
        # construye (contradiccion en E5) o se niega en su propio preflight.
        observed = result.control_plane_result
        assert observed is None or (
            observed.observed_status is not ActionExecutionStatus.VERIFIED
            and observed.behavior_status is not ActionExecutionStatus.VERIFIED
        )


def test_a_completed_run_never_implies_a_fully_verified_configuration(measured_store):
    """Defensa contra la lectura de mas: COMPLETED no es "todo releido".

    Con el gate acotado, una corrida puede completar cada etapa y cada fundacion
    declarada mientras seis puertos de acceso siguen sin getter. El resultado
    tiene que decirlo por si mismo, no dejarlo deducir del enum.
    """
    result, _physical, _configuration, _control_plane = _run(measured_store)

    assert result.configuration_fully_verified is False
    assert result.compact_summary()["configuration_fully_verified"] is False
    assert result.compact_summary()["configuration_status"] == "partial"
