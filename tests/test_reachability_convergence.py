"""Stage 3A4 — la medida de reenvio tiene ventana de convergencia acotada.

Por que existe, con la evidencia que lo probo:
MEG-4 run 11 leyo el event list de simulacion de Packet Tracer sobre el mismo
flujo que el producto acababa de medir como `reachable=False`. El trace mostro
el camino ENTERO funcionando -- el primer eco cae en `B-EDGE-RTR-01` por ARP
("The next-hop IP address is not in the ARP table..."), el ARP resuelve, y el
eco siguiente cruza router -> switch -> PC y vuelve como
"The Ping process received an Echo Reply message.". Nada estaba mal cableado ni
mal configurado: la primera medida llego antes de que el plano de reenvio
convergiera.

Toda otra observacion de este runtime que depende de un plano que converge ya
tenia su ventana acotada de RELECTURA -- `_observe_rip_route` reintenta hasta
45 s porque RIP anuncia cada 30 s. La medida de reenvio, que depende de la
convergencia MAS larga de todas (RIP, mas ARP en la LAN destino, mas un switch
de acceso recien creado), se tomaba exactamente una vez.

Lo que estos tests fijan es que la ventana es de convergencia y no de
conveniencia:

* corta en cuanto la medida COINCIDE con lo esperado, no en cuanto es
  favorable: si el plan espera `reachable=False`, el primer False corta y un
  True sigue midiendo;
* no reaplica ni redespacha nada: lo unico que se repite es la medida;
* una ventana no fresca aborta de inmediato como UNOBSERVABLE, porque esperar
  no la vuelve atribuible;
* el numero real de medidas se reporta en `convergence.attempts`.
"""

from __future__ import annotations

import pytest

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


class _ScriptedPing:
    """Una medida distinta por intento, y cuenta cuantas hubo."""

    def __init__(self, results) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str]] = []

    def ping(self, source_device: str, destination: str) -> TypedPingResult:
        self.calls.append((source_device, destination))
        index = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[index]


def _measured(reachable: bool) -> TypedPingResult:
    """Una ventana fresca y atribuida: el executor SI midio."""
    return TypedPingResult(
        reachable=reachable,
        fresh_output_observed=True,
        statistics=(
            "Success rate is 80 percent (4/5)" if reachable
            else "Success rate is 0 percent (0/5)"
        ),
        dispatched_destination="10.0.0.10",
    )


_UNATTRIBUTABLE = TypedPingResult(
    reachable=False, fresh_output_observed=False,
    failure_reason="current_ping_echo_not_observed",
)


def _run(results, *, expected_reachable: bool = True, attempts: int = 6):
    plan = _compile_university().plan
    action = next(
        item for item in plan.actions_of_type(ControlPlaneActionType.CONFIGURE_RIPV2)
        if item.device_id == "r1"
    )
    expectation = ControlPlaneVerificationExpectation(
        id="verify/flow", kind=ControlPlaneVerificationKind.END_TO_END_REACHABILITY,
        action_id=action.id, device_id="r1",
        required_capability=ControlPlaneCapabilityDimension.ROUTING_BEHAVIOR,
        expected={
            "traffic_flow_id": "flow/x",
            "destination_ipv4": "10.0.0.10",
            "reachable": expected_reachable,
            "protocol": "ripv2",
        },
    )
    ping = _ScriptedPing(results)
    ticks = {"now": 0.0}
    slept: list[float] = []

    def clock():
        return ticks["now"]

    def sleeper(seconds):
        slept.append(seconds)
        ticks["now"] += seconds

    dispatched: list[str] = []
    runtime = PacketTracerEnterpriseControlPlaneRuntime(
        lambda: [],
        lambda script: dispatched.append(script) or True,
        lambda _s, _t: None,
        ping_executor=ping,
        reachability_convergence_timeout_seconds=100.0,
        reachability_convergence_interval_seconds=5.0,
        reachability_convergence_attempts=attempts,
        clock=clock, sleeper=sleeper,
    )
    runtime.apply_actions([action])
    dispatched.clear()  # el despacho de configuracion ya ocurrio, antes de medir
    observed = runtime.verify([expectation])[0]
    return observed, ping, dispatched, slept


class TestItConverges:
    def test_forwarding_that_comes_up_later_is_measured_not_condemned(self):
        """Exactamente run 11: el camino funciona, la primera medida es prematura."""
        observed, ping, dispatched, slept = _run([
            _measured(False), _measured(False), _measured(True),
        ])

        # El AGREGADO no es lo que se mide aca: `traffic_flow_id` es
        # inobservable por contrato y lo arrastra. Lo que cambio es el campo.
        assert observed.fields["reachable"] is FieldVerificationStatus.VERIFIED
        assert len(ping.calls) == 3
        assert observed.convergence.attempts == 3
        assert observed.convergence.last_observable_state == "reachable=True"
        assert slept == [5.0, 5.0]
        # Lo unico que se repitio fue la MEDIDA.
        assert dispatched == []

    def test_a_first_measurement_that_already_matches_stops_immediately(self):
        observed, ping, _, slept = _run([_measured(True)])

        assert observed.fields["reachable"] is FieldVerificationStatus.VERIFIED
        assert len(ping.calls) == 1
        assert observed.convergence.attempts == 1
        assert slept == []

    def test_the_reported_attempt_count_is_the_real_one(self):
        observed, ping, _, _ = _run([_measured(False)], attempts=4)

        assert len(ping.calls) == 4
        assert observed.convergence.attempts == 4
        assert "4 bounded measurement(s)" in observed.message


class TestItIsNotFishingForAFavourableResult:
    def test_it_stops_on_agreement_not_on_reachability(self):
        """Si el plan espera False, el primer False corta y un True no lo salva."""
        observed, ping, _, slept = _run(
            [_measured(False), _measured(True)], expected_reachable=False,
        )

        assert observed.fields["reachable"] is FieldVerificationStatus.VERIFIED
        assert len(ping.calls) == 1
        assert slept == []

    def test_a_true_that_contradicts_an_expected_false_keeps_being_measured(self):
        observed, ping, _, _ = _run(
            [_measured(True)], expected_reachable=False, attempts=3,
        )

        assert observed.fields["reachable"] is FieldVerificationStatus.FAILED
        assert observed.status is ActionExecutionStatus.FAILED
        assert len(ping.calls) == 3
        assert observed.convergence.last_observable_state == "reachable=True"

    def test_forwarding_that_never_comes_up_still_fails(self):
        observed, ping, dispatched, _ = _run([_measured(False)], attempts=3)

        assert observed.fields["reachable"] is FieldVerificationStatus.FAILED
        assert observed.status is ActionExecutionStatus.FAILED
        assert len(ping.calls) == 3
        assert observed.convergence.last_observable_state == "reachable=False"
        assert "nothing was redispatched" in observed.message
        assert dispatched == []


class TestItNeverWaitsOutMissingEvidence:
    def test_an_unattributable_window_aborts_at_once_as_unobservable(self):
        """Rancio no mejora esperando, y agotar el presupuesto lo disfrazaria."""
        observed, ping, _, slept = _run([_UNATTRIBUTABLE, _measured(True)])

        assert observed.status is ActionExecutionStatus.UNOBSERVABLE
        assert len(ping.calls) == 1
        assert slept == []
        assert "current_ping_echo_not_observed" in observed.message

    def test_an_unattributable_window_after_a_real_one_also_aborts(self):
        observed, ping, _, _ = _run([_measured(False), _UNATTRIBUTABLE])

        assert observed.status is ActionExecutionStatus.UNOBSERVABLE
        assert len(ping.calls) == 2


class TestTheBudgetIsValidated:
    @pytest.mark.parametrize("override", [
        {"reachability_convergence_attempts": 0},
        {"reachability_convergence_attempts": True},
        {"reachability_convergence_timeout_seconds": -1.0},
        {"reachability_convergence_interval_seconds": -1.0},
    ])
    def test_a_nonsense_budget_is_refused_at_construction(self, override):
        with pytest.raises(ValueError):
            PacketTracerEnterpriseControlPlaneRuntime(
                lambda: [], lambda _s: True, lambda _s, _t: None, **override,
            )

    def test_the_production_default_covers_more_than_one_measurement(self):
        """Un default de 1 reintroduce exactamente el defecto de run 10."""
        import inspect

        signature = inspect.signature(PacketTracerEnterpriseControlPlaneRuntime)
        assert signature.parameters["reachability_convergence_attempts"].default > 1
        assert (
            signature.parameters["reachability_convergence_timeout_seconds"].default
            >= 60.0
        )
