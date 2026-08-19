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


def test_the_catalogue_leaves_forwarding_behaviour_unknown_until_it_is_measured():
    """UNKNOWN no se hereda ni se deduce de las dimensiones vecinas."""
    profiles = packet_tracer_control_plane_capabilities("9.0.1.0858")
    profile = profiles["2911"]

    assert profile.status(
        ControlPlaneCapabilityDimension.RIPV2_CONFIG,
    ) is SecurityCapabilityStatus.SUPPORTED
    assert profile.status(
        ControlPlaneCapabilityDimension.ROUTING_ROUTE_STATE,
    ) is SecurityCapabilityStatus.SUPPORTED
    # Saber leer el proceso y la ruta NO afirma nada sobre reenviar.
    assert profile.status(
        ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
    ) is SecurityCapabilityStatus.UNKNOWN


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
    """Un modelo ausente del catálogo no obtiene perfil ni estado por omisión."""
    profiles = packet_tracer_control_plane_capabilities("9.0.1.0858")

    assert "1941" not in profiles
    profile = profiles["2960-24TT"]
    assert all(
        profile.status(dimension) is SecurityCapabilityStatus.UNKNOWN
        for dimension in ControlPlaneCapabilityDimension
    )


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
    """Un eco ICMP no observa qué protocolo instaló la ruta que usó.

    El prerequisito de ruta ORDENA la evidencia; no la sustituye. Por eso
    `protocol` se reporta UNOBSERVABLE en lugar de heredarse de la ruta ya
    verificada, y el agregado de reenvío se queda abajo con él.
    """
    expectation = _reachability_expectation(source="A-EDGE-RTR-01")
    result = _verify(expectation, _ping(reachable=True, source="A-EDGE-RTR-01"))

    assert result.fields["protocol"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.fields["traffic_flow_id"] is FieldVerificationStatus.UNOBSERVABLE
    assert result.status is ActionExecutionStatus.UNOBSERVABLE
    assert result.evidence_method == "typed_ping_current_command_window"


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
    provenance: DeviceIdentityProvenance = (
        DeviceIdentityProvenance.CONFIRMED_UNIQUE
    ),
) -> TypedPingResult:
    return TypedPingResult(
        reachable=reachable,
        fresh_output_observed=True,
        window_strategy="prefix_delta",
        statistics="Success rate is 100 percent (5/5)",
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
