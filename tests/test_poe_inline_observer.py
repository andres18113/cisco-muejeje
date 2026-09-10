"""POE-1: la API productiva expone semantica PoE, no CLI.

Por que hace falta ademas de la regla tipada:
`classify_poe_inline_delivery` decide bien, pero deja al llamador cablear a mano
las condiciones que la hacen valida -- frescura, completitud, integridad del
despacho y atribucion al switch exacto. Equivocarse en una sola es silencioso y
apunta siempre en la direccion peligrosa: pasar `capture_complete=True` sobre una
captura truncada convierte un corte de pagina en un NOT_DELIVERING sobre un
puerto que si entrega, y olvidar mirar `device_identity_provenance` atribuye la
tabla de un switch a otro.

`observe_poe_inline_status(exact_switch_identity, exact_expected_ports)` cierra
eso: recibe identidad y puertos, nunca comandos, y cualquier duda sale
UNOBSERVABLE con motivo en vez de convertirse en un negativo.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.infrastructure.execution.command_dispatch import (
    DispatchClassification,
)
from src.packet_tracer_mcp.infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    DeviceIdentityProvenance,
    IosCommandResult,
    IosQualificationQueryId,
    IosSessionState,
    PoEInlineDelivery,
)
from src.packet_tracer_mcp.infrastructure.execution.poe_inline_observer import (
    GovernedPoEInlineObserver,
    PoEInlineObservationStatus,
)
from tests.test_poe_inline_parser import _MEASURED_AUTO, _MEASURED_NEVER

_SWITCH = "Switch0"


class _StubExecutor:
    """Un `ControlledIosExecutor` de mentira que sólo sabe cualificar."""

    def __init__(self, result: IosCommandResult) -> None:
        self._result = result
        self.qualify_calls: list[tuple[str, object]] = []

    def qualify(self, device_name: str, query_id) -> IosCommandResult:
        self.qualify_calls.append((device_name, query_id))
        return self._result

    def execute(self, *args, **kwargs):  # pragma: no cover - nunca debe usarse
        raise AssertionError("El observador no puede usar el registro de producto.")


def _result(
    output: str = _MEASURED_AUTO,
    *,
    executed: bool = True,
    fresh: bool = True,
    complete: bool = True,
    provenance: DeviceIdentityProvenance = DeviceIdentityProvenance.CONFIRMED_UNIQUE,
    observed_name: str = _SWITCH,
    dispatch: DispatchClassification = DispatchClassification.DISPATCHED,
) -> IosCommandResult:
    return IosCommandResult(
        device_name=_SWITCH,
        query_id=IosQualificationQueryId.SHOW_POWER_INLINE,
        executed=executed,
        output=output,
        session_state=IosSessionState.EXEC_PROMPT_READY,
        fresh_output_observed=fresh,
        output_complete=complete,
        dispatch_classification=dispatch.value,
        observed_device_name=observed_name,
        device_identity_provenance=provenance.value,
    )


def _observe(result: IosCommandResult, ports=("FastEthernet0/1",)):
    executor = _StubExecutor(result)
    observation = GovernedPoEInlineObserver(executor).observe_poe_inline_status(
        _SWITCH, ports,
    )
    return executor, observation


# -- el camino que la calibracion midio -------------------------------------

def test_the_calibrated_binding_reads_as_delivering() -> None:
    executor, observation = _observe(_result())

    assert observation.status is PoEInlineObservationStatus.OBSERVED
    assert observation.refusal_reason == ""
    assert len(observation.ports) == 1
    port = observation.ports[0]
    assert port.port == "FastEthernet0/1"
    assert port.delivery is PoEInlineDelivery.DELIVERING
    assert port.row is not None and port.row.device == "IP Phone 7960"
    # Sólo la consulta cerrada, y sólo contra la identidad pedida.
    assert executor.qualify_calls == [
        (_SWITCH, IosQualificationQueryId.SHOW_POWER_INLINE),
    ]


def test_the_never_state_reads_as_not_delivering_from_a_complete_table() -> None:
    _, observation = _observe(_result(_MEASURED_NEVER))

    assert observation.status is PoEInlineObservationStatus.OBSERVED
    assert observation.ports[0].delivery is PoEInlineDelivery.NOT_DELIVERING
    assert observation.ports[0].row is None


def test_only_the_exact_expected_ports_are_reported() -> None:
    """La tabla trae 24 filas; la observacion responde por lo que se pidio."""
    _, observation = _observe(
        _result(), ports=("FastEthernet0/1", "FastEthernet0/7"),
    )

    assert [item.port for item in observation.ports] == [
        "FastEthernet0/1", "FastEthernet0/7",
    ]
    assert observation.ports[0].delivery is PoEInlineDelivery.DELIVERING
    assert observation.ports[1].delivery is PoEInlineDelivery.NOT_DELIVERING


def test_the_summary_is_carried_as_diagnosis_and_decides_nothing() -> None:
    _, powered = _observe(_result())
    _, unpowered = _observe(_result(_MEASURED_NEVER))

    assert powered.summary_used_watts == unpowered.summary_used_watts == 10.0
    assert powered.ports[0].delivery is not unpowered.ports[0].delivery


# -- fail-closed: toda duda es UNOBSERVABLE, nunca un negativo --------------

@pytest.mark.parametrize(
    ("kwargs", "reason_fragment"),
    [
        ({"executed": False}, "not execute"),
        ({"fresh": False}, "fresh"),
        (
            {"dispatch": DispatchClassification.PREFIX_LOSS},
            "corrupted",
        ),
        (
            {"provenance": DeviceIdentityProvenance.NOT_OBSERVED},
            "attribut",
        ),
        ({"observed_name": "Switch9"}, "another device"),
        ({"output": "Invalid input detected at '^' marker."}, "table"),
    ],
)
def test_every_broken_precondition_refuses_instead_of_reporting_a_negative(
    kwargs, reason_fragment,
) -> None:
    _, observation = _observe(_result(**kwargs))

    assert observation.status is PoEInlineObservationStatus.UNOBSERVABLE
    assert reason_fragment in observation.refusal_reason
    assert [item.delivery for item in observation.ports] == [
        PoEInlineDelivery.UNOBSERVABLE,
    ]


def test_a_truncated_capture_still_believes_a_row_it_can_see() -> None:
    """Completitud hace falta para sostener una AUSENCIA, no una fila presente."""
    _, observation = _observe(_result(complete=False))

    assert observation.status is PoEInlineObservationStatus.OBSERVED
    assert observation.capture_complete is False
    assert observation.ports[0].delivery is PoEInlineDelivery.DELIVERING


def test_a_truncated_capture_never_turns_a_missing_row_into_a_negative() -> None:
    """Un corte de pagina y un puerto sin entrega son el mismo texto."""
    _, observation = _observe(_result(_MEASURED_NEVER, complete=False))

    assert observation.ports[0].delivery is PoEInlineDelivery.UNOBSERVABLE


# -- la entrada tampoco puede colar nada ------------------------------------

@pytest.mark.parametrize(
    ("identity", "ports"),
    [
        ("", ("FastEthernet0/1",)),
        ("  ", ("FastEthernet0/1",)),
        (" Switch0", ("FastEthernet0/1",)),
        (_SWITCH, ()),
        (_SWITCH, ("FastEthernet0/1", "FastEthernet0/1")),
        (_SWITCH, ("show power inline",)),
        (_SWITCH, ("FastEthernet0/1 | include on",)),
        (_SWITCH, ("",)),
    ],
)
def test_bad_identity_or_ports_refuse_before_packet_tracer_is_touched(
    identity, ports,
) -> None:
    """Rechazar despues de despachar ya habria tocado PT para nada."""
    executor = _StubExecutor(_result())

    observation = GovernedPoEInlineObserver(executor).observe_poe_inline_status(
        identity, ports,
    )

    assert observation.status is PoEInlineObservationStatus.UNOBSERVABLE
    assert observation.refusal_reason
    assert executor.qualify_calls == []


def test_the_observer_exposes_no_way_to_send_a_command() -> None:
    """La firma es identidad + puertos. No hay parametro por donde entre CLI."""
    import inspect

    signature = inspect.signature(
        GovernedPoEInlineObserver.observe_poe_inline_status,
    )

    assert list(signature.parameters) == [
        "self", "exact_switch_identity", "exact_expected_ports",
    ]


def test_the_observer_drives_the_real_governed_executor() -> None:
    """No es un camino paralelo: usa el ejecutor gobernado de verdad."""
    observer = GovernedPoEInlineObserver(
        ControlledIosExecutor(lambda _js, _timeout: None),
    )

    observation = observer.observe_poe_inline_status(
        _SWITCH, ("FastEthernet0/1",),
    )

    # Sin transporte no hay evidencia, y eso es un rechazo, no un negativo.
    assert observation.status is PoEInlineObservationStatus.UNOBSERVABLE
    assert observation.ports[0].delivery is PoEInlineDelivery.UNOBSERVABLE


# POE-2 needs the exact dispatch consumed by the API, not a parallel capture.
def test_observation_retains_its_own_dispatch_evidence():
    result = _result()
    _, observed = _observe(result)
    assert observed.command_result is result
    assert observed.raw_output == observed.command_result.output


@pytest.mark.parametrize("changes", [
    {"truncated_by_pager": True},
    {"pager_continuation": "failed"},
    {"session_state": IosSessionState.FAILED},
    {"output": _MEASURED_NEVER.replace("Switch#", "Switch>")},
])
def test_contradictory_completeness_cannot_authorize_an_absence(changes):
    from dataclasses import replace
    _, observed = _observe(replace(_result(_MEASURED_NEVER), **changes))
    assert observed.ports[0].delivery is PoEInlineDelivery.UNOBSERVABLE
    assert not observed.capture_complete


@pytest.mark.parametrize("dispatch", ["echo_unobservable", "unrecognized_value"])
def test_unproven_dispatch_is_a_refusal_not_evidence_or_an_exception(dispatch):
    from dataclasses import replace
    _, observed = _observe(replace(_result(), dispatch_classification=dispatch))
    assert observed.status is PoEInlineObservationStatus.UNOBSERVABLE


def test_two_aliases_of_one_requested_interface_are_rejected_before_dispatch():
    executor, observed = _observe(_result(), ("Fa0/1", "FastEthernet0/1"))
    assert executor.qualify_calls == []
    assert observed.status is PoEInlineObservationStatus.UNOBSERVABLE


def test_duplicate_table_rows_cannot_select_one_answer_silently():
    duplicate = next(line for line in _MEASURED_AUTO.splitlines() if line.startswith("Fa0/1 "))
    _, observed = _observe(_result(_MEASURED_AUTO.replace("Switch#", duplicate + "\nSwitch#", 1)))
    assert observed.status is PoEInlineObservationStatus.UNOBSERVABLE


def test_empty_observed_identity_cannot_inherit_requested_identity():
    _, observed = _observe(_result(observed_name=""))
    assert observed.status is PoEInlineObservationStatus.UNOBSERVABLE


def test_incomplete_output_cannot_report_an_off_row_as_a_negative():
    _, observed = _observe(_result(complete=False), ("FastEthernet0/7",))
    assert observed.ports[0].delivery is PoEInlineDelivery.UNOBSERVABLE


def test_malformed_present_target_row_refuses_instead_of_reporting_absence():
    from tests.test_poe_inline_parser import _HEAD
    malformed = "Fa0/1     auto   on         BAD     IP Phone 7960       3     15.4\n"
    output = _MEASURED_NEVER.replace(_HEAD, _HEAD + malformed, 1)
    _, observed = _observe(_result(output))
    assert observed.status is PoEInlineObservationStatus.UNOBSERVABLE
    assert observed.refusal_reason
    assert observed.ports[0].delivery is PoEInlineDelivery.UNOBSERVABLE
