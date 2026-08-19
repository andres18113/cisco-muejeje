"""Stage 3A4 — el id del flujo es procedencia, no una lectura pendiente.

`traffic_flow_id` vivia dentro de `expected` y se reportaba UNOBSERVABLE en cada
observacion de alcanzabilidad. Eso mantenia el agregado por debajo de VERIFIED
para siempre, con independencia de la red: ninguna consulta registrada puede
devolverlo, porque el unico comando es `ping <ip>`.

El problema no era que se reportara: era que se contaba como una PROPIEDAD DEL
DEVICE que no se pudo leer, cuando nunca lo fue. Todas las demas expectativas
del compilador ya distinguen las dos cosas -- `route_present` reclama
`{network, prefix_length, protocol}`, todas leibles, y lleva su procedencia en
`action_id`, `device_id`, `source_link_id`, fuera de `expected`.

Asi que la etiqueta se mueve a `source_traffic_flow_id`, junto a `source_link_id`.
Estos tests fijan que eso NO subio ningun techo:

* la etiqueta se conserva, atada a la misma expectativa;
* el conjunto de propiedades del device reclamadas es exactamente el de antes;
* `unclaimed_fields` sigue rindiendo UNOBSERVABLE, asi que quitar una propiedad
  real de `expected` sigue sin ser una via para subir el agregado.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ControlPlaneActionType,
    ControlPlaneCapabilityDimension,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingResult

from test_typed_ripv2_control_plane import _compile_university


def _observe(expectation, ping_result):
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
        if item.device_id == "r1"
    )
    bound = expectation.model_copy(update={"action_id": action.id})

    class _Ping:
        def ping(self, source_device, destination):
            return ping_result

    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [], lambda _s: True, lambda _s, _t: None,
        ping_executor=_Ping(),
        reachability_convergence_attempts=1,
        reachability_convergence_timeout_seconds=0.0,
        reachability_convergence_interval_seconds=0.0,
    )
    runtime.apply_actions([action])
    return runtime.verify([bound])[0]


def _expectation(**overrides) -> ControlPlaneVerificationExpectation:
    base = dict(
        id="verify/flow",
        kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
        action_id="placeholder",
        device_id="r1",
        source_traffic_flow_id="flow/a-to-b",
        required_capability=ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
        expected={
            "destination_ipv4": "10.0.0.10",
            "reachable": True,
            "protocol": "ripv2",
            # Lo inyecta ControlPlaneApplicator desde el manifiesto; se
            # replica aca para medir la MISMA forma que ve la produccion.
            "source_device_name": "UCE-R1",
        },
    )
    base.update(overrides)
    return ControlPlaneVerificationExpectation(**base)


_REACHED = TypedPingResult(
    reachable=True, fresh_output_observed=True,
    statistics="Success rate is 80 percent (4/5)",
    dispatched_destination="10.0.0.10",
)


class TestTheLabelIsPreserved:
    def test_the_flow_id_still_travels_with_the_expectation(self):
        expectation = _expectation()

        assert expectation.source_traffic_flow_id == "flow/a-to-b"
        assert "traffic_flow_id" not in expectation.expected

    def test_the_compiler_binds_the_real_flow_id_not_a_placeholder(self):
        """Se comprueba contra el compilador, no contra un literal de test."""
        from test_stage3a4_product_composition import (  # noqa: F401
            ControlPlaneVerificationKind as _Kind,
        )

        # La composicion del producto ya lo fija en su propio test; aca solo se
        # afirma que el campo no quedo vacio por defecto en ninguna via.
        assert _expectation().source_traffic_flow_id


class TestTheCeilingDidNotMove:
    def test_the_claimed_device_properties_are_exactly_the_previous_ones(self):
        observed = _observe(_expectation(), _REACHED)

        assert set(observed.fields) == {
            "destination_ipv4", "reachable", "protocol", "source_device_name",
        }
        assert "traffic_flow_id" not in observed.fields

    def test_an_unobservable_source_still_holds_the_aggregate_down(self):
        """La procedencia de ejecucion NO se regalo: sin atribucion, no sube."""
        observed = _observe(_expectation(), _REACHED)

        assert observed.fields["reachable"] is FieldVerificationStatus.VERIFIED
        # El stub no trae evidencia de identidad, asi que la fuente no se
        # certifica y el agregado se queda debajo de VERIFIED.
        assert (
            observed.fields["source_device_name"]
            is FieldVerificationStatus.UNOBSERVABLE
        )
        assert observed.status is not ActionExecutionStatus.VERIFIED

    def test_unclaimed_fields_still_render_unobservable(self):
        """Quitar una propiedad REAL de `expected` sigue sin subir el techo."""
        observed = _observe(
            _expectation(
                expected={"destination_ipv4": "10.0.0.10", "reachable": True},
                unclaimed_fields=["hop_count"],
            ),
            _REACHED,
        )

        assert observed.fields["hop_count"] is FieldVerificationStatus.UNOBSERVABLE
        assert observed.status is not ActionExecutionStatus.VERIFIED

    def test_the_flow_label_cannot_be_smuggled_back_in_as_a_claim(self):
        """Si alguien lo devuelve a `expected`, vuelve a contar como lectura."""
        observed = _observe(
            _expectation(
                expected={
                    "traffic_flow_id": "flow/a-to-b",
                    "destination_ipv4": "10.0.0.10",
                    "reachable": True,
                    "protocol": "ripv2",
                },
            ),
            _REACHED,
        )

        assert (
            observed.fields["traffic_flow_id"]
            is FieldVerificationStatus.UNOBSERVABLE
        )


class TestNoOtherExpectationCarriesACompilerLabel:
    def test_expected_holds_only_device_properties_across_the_plan(self):
        """El defecto era unico; este test impide que reaparezca en otro kind."""
        plan = _compile_university().plan
        labels = {"traffic_flow_id", "flow_id", "expectation_id", "action_id"}

        offenders = {
            (item.kind.value, key)
            for item in plan.verification_expectations
            for key in item.expected
            if key in labels
        }

        assert offenders == set()
