"""Qué autoriza una medida de reenvío, y qué establece esa medida.

MEG-4 run 8 dejó `2911:routing_behavior is unknown` en el
`control_plane_capability_gate`. Este módulo fija que ese contrato NO es
circular — la dimensión autoriza EJECUTAR la medida, y el resultado vive en los
campos de la expectativa — y que la contabilidad de campos de una observación de
alcance no puede tirar en silencio un `source_device_name` reclamado. Es
OFFLINE: no toca Packet Tracer.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    FieldVerificationStatus,
)
from src.packet_tracer_mcp.domain.enterprise.models.control_plane import (
    ConfigureRipv2,
    ControlPlaneCapabilityDimension,
    ControlPlaneCapabilityProfile,
    ControlPlanePhase,
    ControlPlaneVerificationExpectation,
    ControlPlaneVerificationKind,
    RipNetwork,
)
from src.packet_tracer_mcp.domain.enterprise.models.security_plan import (
    SecurityCapabilityStatus,
)
from src.packet_tracer_mcp.infrastructure.catalog.control_plane_capabilities import (
    packet_tracer_control_plane_capabilities,
)
from src.packet_tracer_mcp.infrastructure.execution.enterprise_control_plane_runtime import (
    PacketTracerEnterpriseControlPlaneRuntime,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    DeviceIdentityEvidence,
    DeviceIdentityProvenance,
)
from src.packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingResult


# ==========================================================================
# A. La dimensión autoriza la medida; no es su resultado
# ==========================================================================

def test_the_behaviour_dimension_gates_the_measurement_and_never_carries_it():
    """El contrato no es circular: capacidad != resultado.

    `routing_behavior` es lo que hace falta para EJECUTAR el ping tipado. Lo
    que la medida establece viaja en `expected`/`fields` como `reachable`. Si
    la dimensión fuese el resultado, exigirla antes de medir sí sería circular;
    esta prueba fija que no lo es, y falla si alguien las mezcla.
    """
    expectation = _reachability_expectation()

    assert expectation.required_capability is (
        ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR
    )
    assert expectation.expected["reachable"] is True
    # El resultado NUNCA se guarda como capacidad, y la capacidad nunca aparece
    # entre los campos reclamados.
    assert "routing_behavior" not in expectation.expected
    assert "reachable" not in {
        item.value for item in ControlPlaneCapabilityDimension
    }


def test_forwarding_behaviour_is_granted_only_where_it_was_measured():
    """R3 midio el canal en 2911/9.0.1.0858; nadie mas lo hereda."""
    profiles = packet_tracer_control_plane_capabilities("9.0.1.0858")
    profile = profiles["2911"]

    assert profile.status(
        ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
    ) is SecurityCapabilityStatus.SUPPORTED
    assert "R3" in profile.evidence_source
    # Cualificar el canal de medida no cualifica nada mas: las dimensiones sin
    # medicion atribuida siguen UNKNOWN en el mismo modelo.
    assert profile.status(
        ControlPlaneCapabilityDimension.ROUTING_FAILOVER,
    ) is SecurityCapabilityStatus.UNKNOWN
    assert profile.status(
        ControlPlaneCapabilityDimension.HSRP_BEHAVIOR,
    ) is SecurityCapabilityStatus.UNKNOWN


def test_another_model_never_inherits_the_measured_behaviour_channel():
    """La evidencia es por modelo: otro modelo no se autoriza con la ajena."""
    profiles = packet_tracer_control_plane_capabilities("9.0.1.0858")

    assert profiles["2960-24TT"].status(
        ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
    ) is SecurityCapabilityStatus.UNKNOWN


def test_a_different_build_carries_its_own_profile_version():
    """La evidencia es por build: el perfil se emite version-scoped."""
    other = packet_tracer_control_plane_capabilities("8.2.2.0400")["2911"]

    assert other.packet_tracer_version == "8.2.2.0400"
    assert "9.0.1.0858" not in (other.packet_tracer_version or "")


def test_authorising_the_measurement_does_not_fabricate_its_success():
    """Con la dimensión SUPPORTED la medida corre; su resultado sigue siendo suyo.

    Autorizar no es aprobar: un ping autorizado que mide `reachable=False`
    tiene que FALLAR, no verificar.
    """
    expectation = _reachability_expectation()
    result = _verify(
        expectation,
        _ping(reachable=False, source="A-EDGE-RTR-01"),
    )

    assert result.fields["reachable"] is FieldVerificationStatus.FAILED
    assert result.status is ActionExecutionStatus.FAILED


def test_a_supported_profile_is_never_built_from_an_absent_model():
    """Un modelo ausente del catálogo no obtiene perfil ni estado por omisión.

    El ejemplar era `1941` hasta que la cualificacion R4 de MEG-5 lo midio --
    la referencia de 41 dispositivos lo selecciona. La fila es sobre AUSENCIA,
    no sobre ese modelo, asi que usa uno que sigue sin perfil.
    """
    profiles = packet_tracer_control_plane_capabilities("9.0.1.0858")

    assert "2901" not in profiles
    assert profiles.get("2901") is None


# ==========================================================================
# B. La contabilidad de campos del observador de alcance
# ==========================================================================

def test_reachability_never_silently_drops_a_claimed_source_device():
    """Todo campo reclamado aparece en el resultado, observado o no."""
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    result = _verify(expectation, _ping(reachable=True, source="A-EDGE-RTR-01"))

    assert set(result.fields) == set(expectation.expected)
    assert "source_device_name" in result.fields


def test_reachability_certifies_the_source_only_from_execution_provenance():
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    result = _verify(expectation, _ping(reachable=True, source="A-EDGE-RTR-01"))

    assert result.fields["source_device_name"] is FieldVerificationStatus.VERIFIED
    assert result.fields["reachable"] is FieldVerificationStatus.VERIFIED


def test_reachability_source_attribution_fails_closed_without_provenance():
    """Sin atribución única el campo NO se rellena con el nombre pedido."""
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    result = _verify(
        expectation,
        _ping(
            reachable=True,
            source="",
            provenance=DeviceIdentityProvenance.NOT_OBSERVED,
        ),
    )

    assert result.fields["source_device_name"] is (
        FieldVerificationStatus.UNOBSERVABLE
    )
    assert result.status is ActionExecutionStatus.UNOBSERVABLE


def test_a_measurement_taken_on_another_device_never_certifies_the_claimed_one():
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    result = _verify(
        expectation, _ping(reachable=True, source="B-EDGE-RTR-01"),
    )

    assert result.fields["source_device_name"] is FieldVerificationStatus.FAILED
    assert result.status is ActionExecutionStatus.FAILED


def test_the_forwarding_result_is_not_satisfied_by_route_evidence():
    """La ruta ORDENA la evidencia de reenvío; no la sustituye.

    `reachable` sale del ping y de nada mas, y `traffic_flow_id` sigue sin ser
    observable por ninguna medida, asi que una ruta verificada no puede llevar
    el agregado de reenvio a VERIFIED por si sola.
    """
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    result = _verify(expectation, _ping(reachable=True, source="A-EDGE-RTR-01"))

    assert result.fields["reachable"] is FieldVerificationStatus.VERIFIED
    assert result.fields["traffic_flow_id"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.evidence_method == "typed_ping_current_command_window"


def test_the_protocol_is_bound_to_the_action_that_was_actually_applied():
    """No basta con reclamarlo: se compara contra lo que se aplico de verdad."""
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    result = _verify(expectation, _ping(reachable=True, source="A-EDGE-RTR-01"))

    assert result.fields["protocol"] is FieldVerificationStatus.VERIFIED


def test_a_protocol_claim_that_contradicts_the_applied_action_fails():
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    expectation = expectation.model_copy(update={
        "expected": {**expectation.expected, "protocol": "ospfv2"},
    })
    result = _verify(expectation, _ping(reachable=True, source="A-EDGE-RTR-01"))

    assert result.fields["protocol"] is FieldVerificationStatus.FAILED
    assert result.status is ActionExecutionStatus.FAILED


def test_the_destination_is_certified_from_the_dispatched_echo_not_the_request():
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")

    echoed = _verify(
        expectation,
        _ping(reachable=True, source="A-EDGE-RTR-01", dispatched="10.0.0.10"),
    )
    crossed = _verify(
        expectation,
        _ping(reachable=True, source="A-EDGE-RTR-01", dispatched="10.0.0.99"),
    )
    unreported = _verify(
        expectation,
        _ping(reachable=True, source="A-EDGE-RTR-01", dispatched=""),
    )

    assert echoed.fields["destination_ipv4"] is FieldVerificationStatus.VERIFIED
    # Un resultado cruzado, de otra medida, no puede certificar esta direccion.
    assert crossed.fields["destination_ipv4"] is FieldVerificationStatus.FAILED
    assert crossed.status is ActionExecutionStatus.FAILED
    # Y sin eco confirmado el ejecutor no la reporta: falla cerrado.
    assert unreported.fields["destination_ipv4"] is (
        FieldVerificationStatus.UNOBSERVABLE
    )


def test_an_unmeasurable_ping_stays_unobservable_rather_than_failing():
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    result = _verify(
        expectation,
        TypedPingResult(
            reachable=False,
            fresh_output_observed=False,
            failure_reason="no_fresh_ping_result",
        ),
    )

    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert set(result.fields.values()) == {FieldVerificationStatus.UNOBSERVABLE}


# ==========================================================================
# helpers
# ==========================================================================

def _action() -> ConfigureRipv2:
    return ConfigureRipv2(
        id="cp/ripv2/forwarding",
        phase=ControlPlanePhase.DYNAMIC_ROUTING,
        device_id="r1",
        device_name="A-EDGE-RTR-01",
        model="2911",
        site_id="a",
        required_capability=ControlPlaneCapabilityDimension.RIPV2_CONFIG,
        networks=[RipNetwork(
            network="10.0.0.0",
            source_segment_ids=["a-lan"],
            source_configuration_action_ids=["cfg/l3/r1/a-lan"],
        )],
        passive_interfaces=["GigabitEthernet0/0"],
    )


def _reachability_expectation(source: str = "") -> ControlPlaneVerificationExpectation:
    expected: dict = {
        "traffic_flow_id": "flow/a-to-b",
        "destination_ipv4": "10.0.0.10",
        "reachable": True,
        "protocol": "ripv2",
    }
    if source:
        expected["source_device_name"] = source
    return ControlPlaneVerificationExpectation(
        id="cp/verify-flow-reachability/forwarding",
        kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
        action_id="cp/ripv2/forwarding",
        device_id="r1",
        peer_device_id="r2",
        required_capability=ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
        expected=expected,
    )


def _ping(
    *,
    reachable: bool,
    source: str,
    dispatched: str = "10.0.0.10",
    provenance: DeviceIdentityProvenance = (
        DeviceIdentityProvenance.CONFIRMED_UNIQUE
    ),
) -> TypedPingResult:
    return TypedPingResult(
        reachable=reachable,
        fresh_output_observed=True,
        window_strategy="prefix_delta",
        statistics="Success rate is 100 percent (5/5)",
        dispatched_destination=dispatched,
        observed_device_name=source,
        device_identity_provenance=(
            provenance.value if source
            else DeviceIdentityProvenance.NOT_OBSERVED.value
        ),
        device_identity_evidence=(
            DeviceIdentityEvidence.SESSION_TRANSCRIPT_CONTINUITY.value if source
            else DeviceIdentityEvidence.NONE.value
        ),
    )


class _FakePing:
    def __init__(self, result: TypedPingResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    def ping(self, source_device: str, destination: str) -> TypedPingResult:
        self.calls.append((source_device, destination))
        return self._result


def _verify(expectation, ping_result: TypedPingResult):
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda _script: True,
        lambda _script, _timeout: None,
        ping_executor=_FakePing(ping_result),
    )
    runtime.apply_actions([_action()])
    return runtime.verify([expectation])[0]


@pytest.mark.parametrize(
    "status",
    [
        SecurityCapabilityStatus.UNKNOWN,
        SecurityCapabilityStatus.UNSUPPORTED,
    ],
    ids=["unknown", "unsupported"],
)
def test_a_non_runnable_capability_never_becomes_runnable(status):
    """El conjunto ejecutable no admite ni desconocido ni no soportado."""
    from src.packet_tracer_mcp.application.use_cases.apply_control_plane import (
        _RUNNABLE_CAPABILITIES,
    )

    assert status not in _RUNNABLE_CAPABILITIES
    assert _RUNNABLE_CAPABILITIES == {
        SecurityCapabilityStatus.SUPPORTED,
        SecurityCapabilityStatus.PARTIAL,
    }


def test_a_profile_may_not_be_upgraded_by_asking_for_a_missing_dimension():
    profile = ControlPlaneCapabilityProfile(model="2911")

    assert profile.status(
        ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
    ) is SecurityCapabilityStatus.UNKNOWN
