"""Stage 3A4 — el seam de diagnostico sobre el event list de simulacion.

MEG-4 run 10 midio `reachable=False` end-to-end sin poder nombrar la causa. El
modo Simulacion de Packet Tracer publica, por frame, el salto y el log de
decisiones por capa OSI, y eso convierte un negativo agregado en un dispositivo
y una razon. Estos tests fijan tres cosas:

* el JS que la fachada MCP publica y el que el runtime gobernado envia son EL
  MISMO -- no hay dos definiciones que puedan divergir;
* la localizacion sale del primer frame fallido en orden de event list, con la
  ultima decision de PT como razon;
* nada de esto promueve un campo a VERIFIED. Es diagnostico.

Los frames de ejemplo son la forma real medida contra PT (ver
`tests/test_packet_trace.py` y el docstring de `domain/services/packet_trace.py`):
un ping genera el ARP broadcast y el ICMP que queda en buffer esperandolo.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from src.packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
    PacketTraceObservation,
    SimulationTraceRuntime,
    packet_trace_js,
    simulation_mode_js,
    simulation_step_js,
)


class _Recorder:
    """Transporte falso: guarda lo enviado y devuelve lo que se le programe."""

    def __init__(self, *responses: str | None) -> None:
        self.responses = list(responses)
        self.sent: list[tuple[str, float]] = []

    def __call__(self, script: str, timeout: float) -> str | None:
        self.sent.append((script, timeout))
        return self.responses.pop(0) if self.responses else None


def _frame(**overrides) -> dict:
    base = {
        "index": 0,
        "device": "SW1",
        "previous_device": "R1",
        "in_port": "GigabitEthernet1/1",
        "out_port": None,
        "source": "10.0.0.17",
        "destination": "10.0.0.10",
        "traffic_type_raw": 0,
        "sent": False,
        "accepted": False,
        "dropped": False,
        "buffered": False,
        "in_transit": False,
        "collided_at_device": False,
        "collided_on_link": False,
        "not_forwarded": False,
        "unexpected": False,
        "decisions": [],
    }
    base.update(overrides)
    return base


def _trace_payload(*frames: dict, simulation_mode: bool = True) -> str:
    return json.dumps({
        "total": len(frames), "simulation_mode": simulation_mode,
        "frames": list(frames),
    })


class TestOneDefinitionOfTheJavaScript:
    """La fachada publica no puede divergir del runtime gobernado."""

    def test_the_mcp_tool_module_imports_the_shared_builders(self):
        from src.packet_tracer_mcp.adapters.mcp import tool_registry

        # Si la fachada volviera a inlinear su propio JS, estos nombres dejarian
        # de estar importados y el drift seria invisible.
        assert tool_registry.simulation_mode_js is simulation_mode_js
        assert tool_registry.simulation_step_js is simulation_step_js
        assert tool_registry.packet_trace_js is packet_trace_js

    def test_the_runtime_sends_exactly_the_shared_script(self):
        send = _Recorder(json.dumps({"before": False, "after": True, "frames": 0}))
        SimulationTraceRuntime(send).set_simulation_mode(True)

        assert send.sent[0][0] == simulation_mode_js(True)

    def test_the_trace_script_carries_the_measured_pt_surface(self):
        js = packet_trace_js(20, "", True)

        # Primitivas reales, no inventadas: si alguna se renombra, este test
        # obliga a re-medirla contra PT en vez de adivinar.
        for primitive in (
            "ipc.simulation()", "getFrameInstanceCount", "getFrameInstanceAt",
            "getPreviousDevice", "getInPort", "getOutPortCount",
            "getFlowChartNodeCount", "getFrameDecsionAt", "isFrameDropped",
            "isFrameNotForwarded",
        ):
            assert primitive in js
        # El typo `Decsion` es de Packet Tracer. Corregirlo rompe la lectura.
        assert "getFrameDecision" not in js

    def test_the_limit_is_clamped_to_the_documented_range(self):
        assert "var __lim = 1;" in packet_trace_js(0, "", True)
        assert "var __lim = 200;" in packet_trace_js(9999, "", True)


class TestLocalization:
    """Lo que este seam entrega: un dispositivo, un puerto y una razon."""

    def test_the_first_failing_frame_in_event_list_order_is_the_localization(self):
        arp = _frame(index=0, device="SW1", sent=True, traffic_type_raw=5)
        dropped = _frame(
            index=1, device="B-DEFAULT-ACCESS-SW-01", dropped=True,
            in_port="GigabitEthernet1/1",
            decisions=[
                {"layer": 2, "inbound": True, "description": "The frame arrives."},
                {"layer": 2, "inbound": False,
                 "description": "The port is not in the same VLAN. The device drops the frame."},
            ],
        )
        later = _frame(index=2, device="PC", not_forwarded=True)
        send = _Recorder(_trace_payload(arp, dropped, later))

        trace = SimulationTraceRuntime(send).read_trace()

        assert trace.observed and trace.simulation_mode
        assert len(trace.failing_hops) == 2
        hop = trace.first_failing_hop
        assert hop is not None
        assert hop.device == "B-DEFAULT-ACCESS-SW-01"
        assert hop.status == "dropped"
        assert hop.in_port == "GigabitEthernet1/1"
        # La razon es la ULTIMA decision, que es la que explica el desenlace.
        assert "not in the same VLAN" in hop.reason
        assert "dropped at B-DEFAULT-ACCESS-SW-01" in trace.localization()

    def test_a_frame_without_decisions_says_so_instead_of_inventing_a_reason(self):
        send = _Recorder(_trace_payload(_frame(dropped=True, decisions=[])))

        trace = SimulationTraceRuntime(send).read_trace()

        assert trace.first_failing_hop is not None
        assert trace.first_failing_hop.reason == ""
        assert "no decision published" in trace.localization()

    def test_a_clean_trace_localizes_nothing_and_claims_nothing(self):
        send = _Recorder(_trace_payload(_frame(accepted=True), _frame(index=1, sent=True)))

        trace = SimulationTraceRuntime(send).read_trace()

        assert trace.failing_hops == ()
        assert trace.first_failing_hop is None
        assert trace.localization() == "no_failing_frame_among_2"

    def test_traffic_types_use_the_measured_labels(self):
        send = _Recorder(_trace_payload(
            _frame(traffic_type_raw=0), _frame(index=1, traffic_type_raw=5),
            _frame(index=2, traffic_type_raw=77),
        ))

        trace = SimulationTraceRuntime(send).read_trace()

        assert [hop.traffic_type for hop in trace.hops] == ["ICMP", "ARP", "type77"]


class TestRefusals:
    """Ausencia de evidencia se nombra; nunca se rellena con un valor comodo."""

    def test_a_silent_bridge_is_not_an_empty_trace(self):
        trace = SimulationTraceRuntime(_Recorder(None)).read_trace()

        assert trace.observed is False
        assert trace.hops == ()
        assert trace.localization().startswith("no_trace_observed")

    @pytest.mark.parametrize("body", ["ERROR: boom", "PT_ERROR: ReferenceError"])
    def test_a_packet_tracer_error_is_not_a_reading(self, body):
        trace = SimulationTraceRuntime(_Recorder(body)).read_trace()

        assert trace.observed is False
        assert body in trace.message

    def test_unparseable_output_is_not_a_reading(self):
        trace = SimulationTraceRuntime(_Recorder("<html>nope</html>")).read_trace()

        assert trace.observed is False
        assert "well-formed JSON" in trace.message

    def test_realtime_mode_is_reported_as_such_and_not_as_no_traffic(self):
        send = _Recorder(_trace_payload(simulation_mode=False))

        trace = SimulationTraceRuntime(send).read_trace()

        assert trace.observed is True and trace.simulation_mode is False
        assert "realtime_mode" in trace.localization()

    def test_simulation_mode_without_frames_is_distinct_from_realtime(self):
        send = _Recorder(_trace_payload(simulation_mode=True))

        trace = SimulationTraceRuntime(send).read_trace()

        assert "simulation_mode_without_frames" in trace.localization()

    def test_an_unsupported_step_action_never_reaches_the_bridge(self):
        send = _Recorder()

        step = SimulationTraceRuntime(send).step("rewind")

        assert step.observed is False
        assert send.sent == []

    def test_stepping_in_realtime_is_observed_and_refused_not_counted(self):
        send = _Recorder(json.dumps({"simulation_mode": False}))

        step = SimulationTraceRuntime(send).step("forward", times=5)

        assert step.observed is True and step.simulation_mode is False
        assert step.frames_before == 0 and step.frames_after == 0

    def test_reset_ignores_times_and_loops_nothing(self):
        assert "for (var __i" not in simulation_step_js("reset", 9)
        assert "for (var __i = 0; __i < 5;" in simulation_step_js("forward", 5)


class TestItStaysDiagnostic:
    """Ningun camino de aca produce una promocion de estado."""

    def test_the_observation_exposes_no_verification_status(self):
        fields = set(PacketTraceObservation.__dataclass_fields__)

        assert fields == {
            "observed", "simulation_mode", "total_in_event_list", "hops", "message",
            "requested_limit", "effective_limit",
        }
        for forbidden in ("verified", "status", "access_port", "gateway"):
            assert forbidden not in fields

    def test_the_module_never_imports_the_configuration_evidence_types(self):
        from pathlib import Path

        source = Path(
            "src/packet_tracer_mcp/infrastructure/execution/simulation_trace_runtime.py",
        ).read_text(encoding="utf-8")

        # Si alguna vez importa esto, dejo de ser diagnostico y paso a ser una
        # via alternativa para certificar campos que nadie leyo directamente.
        for forbidden in (
            "ActionExecutionStatus", "FieldVerificationStatus",
            "RuntimeVerification", "ConfigurationApplicationStatus",
        ):
            assert forbidden not in source


# ======================================================================
# POST_FAILURE_SIMULATION_DIAGNOSTIC — capture hardening.
#
# CP-SCALE needs to discover how THIS build represents DHCP before anything
# may classify it. That makes the raw capture the product: a label, a summary
# or a dropped field is evidence that cannot be re-read later without paying
# for another governed LIVE.
# ======================================================================


class TestPureSimulationStateRead:
    """Leer el estado no puede ser un efecto secundario de cambiarlo."""

    def test_the_pure_state_builder_carries_no_mutator(self):
        from src.packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
            simulation_state_js,
        )

        js = simulation_state_js()

        assert "isSimulationMode" in js
        assert "getFrameInstanceCount" in js
        assert "getCurrentSimTime" in js
        # Una lectura que puede mover el estado no sirve para verificar que el
        # estado volvio: probaria lo que ella misma acaba de hacer.
        for mutator in (
            "setSimulationMode", "forward", "backward", "resetSimulation",
        ):
            assert mutator not in js

    def test_the_pure_read_reports_the_observed_state(self):
        from src.packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
            SimulationTraceRuntime as _R,
        )

        send = _Recorder(json.dumps({
            "mode": True, "frames": 12, "sim_time": 4.5, "current_index": 3,
        }))

        state = _R(send).read_simulation_state()

        assert state.observed is True
        assert state.simulation_mode is True
        assert state.frames == 12
        assert state.sim_time == 4.5
        assert state.current_index == 3

    def test_a_state_without_a_mode_is_not_a_reading(self):
        from src.packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
            SimulationTraceRuntime as _R,
        )

        state = _R(_Recorder(json.dumps({"frames": 3}))).read_simulation_state()

        assert state.observed is False
        assert state.simulation_mode is False

    def test_a_silent_bridge_is_not_a_realtime_reading(self):
        from src.packet_tracer_mcp.infrastructure.execution.simulation_trace_runtime import (
            SimulationTraceRuntime as _R,
        )

        state = _R(_Recorder(None)).read_simulation_state()

        assert state.observed is False
        assert state.frames is None and state.sim_time is None


class TestRawTrafficIdentitySurvives:
    """La etiqueta es conveniencia; el entero es la evidencia."""

    def test_the_raw_traffic_type_is_retained_beside_its_label(self):
        send = _Recorder(_trace_payload(
            _frame(traffic_type_raw=0), _frame(index=1, traffic_type_raw=5),
            _frame(index=2, traffic_type_raw=77),
        ))

        hops = SimulationTraceRuntime(send).read_trace().hops

        assert [hop.traffic_type_raw for hop in hops] == [0, 5, 77]
        # El mapeo medido no cambia, y lo no medido sigue sin nombre.
        assert [hop.traffic_type for hop in hops] == ["ICMP", "ARP", "type77"]

    def test_an_absent_traffic_type_is_not_reported_as_icmp(self):
        frame = _frame()
        frame.pop("traffic_type_raw")
        send = _Recorder(_trace_payload(frame))

        hop = SimulationTraceRuntime(send).read_trace().hops[0]

        assert hop.traffic_type_raw is None
        assert hop.traffic_type == "typeNone"

    def test_no_dhcp_label_exists_yet(self):
        from src.packet_tracer_mcp.domain.services import packet_trace

        assert packet_trace.TRAFFIC_TYPES == {0: "ICMP", 5: "ARP"}
        assert "DHCP" not in set(packet_trace.TRAFFIC_TYPES.values())


class TestFullDecisionEvidenceSurvives:
    """La ultima decision explica el desenlace; las otras explican el camino."""

    def test_every_decision_is_retained_in_order(self):
        send = _Recorder(_trace_payload(_frame(dropped=True, decisions=[
            {"layer": 3, "inbound": True, "description": "The device receives the frame."},
            {"layer": 3, "inbound": False, "description": "The device sets the next-hop."},
            {"layer": 2, "inbound": False, "description": "The device drops the frame."},
        ])))

        hop = SimulationTraceRuntime(send).read_trace().hops[0]

        assert len(hop.decisions) == 3
        assert [item.layer for item in hop.decisions] == [3, 3, 2]
        assert [item.inbound for item in hop.decisions] == [True, False, False]
        assert hop.decisions[0].description.startswith("The device receives")
        # `reason` sigue siendo exactamente lo que era: la ultima descripcion.
        assert hop.reason == "The device drops the frame."

    def test_a_frame_without_decisions_retains_an_empty_tuple(self):
        send = _Recorder(_trace_payload(_frame(dropped=True, decisions=[])))

        hop = SimulationTraceRuntime(send).read_trace().hops[0]

        assert hop.decisions == ()
        assert hop.reason == ""


class TestSimulationTimeIsParsedStrictly:
    """Un cero fabricado y un cero medido no pueden ser el mismo valor."""

    def test_an_integer_simulation_time_is_accepted(self):
        send = _Recorder(_trace_payload(_frame(sim_time=7, transit_time=0)))

        hop = SimulationTraceRuntime(send).read_trace().hops[0]

        assert hop.sim_time == 7
        # Cero medido sigue siendo cero, no ausencia.
        assert hop.transit_time == 0

    def test_a_float_simulation_time_is_accepted(self):
        send = _Recorder(_trace_payload(_frame(sim_time=1.25, transit_time=0.5)))

        hop = SimulationTraceRuntime(send).read_trace().hops[0]

        assert hop.sim_time == 1.25 and hop.transit_time == 0.5

    def test_a_boolean_is_not_a_simulation_time(self):
        send = _Recorder(_trace_payload(_frame(sim_time=True, transit_time=False)))

        hop = SimulationTraceRuntime(send).read_trace().hops[0]

        assert hop.sim_time is None and hop.transit_time is None

    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
    def test_a_non_finite_simulation_time_is_not_evidence(self, literal):
        body = (
            '{"total": 1, "simulation_mode": true, "frames": [{"index": 0,'
            ' "device": "PC", "sim_time": ' + literal + ', "decisions": []}]}'
        )

        hop = SimulationTraceRuntime(_Recorder(body)).read_trace().hops[0]

        assert hop.sim_time is None

    def test_a_missing_simulation_time_stays_absent_instead_of_zero(self):
        frame = _frame()
        frame.pop("sim_time", None)
        frame.pop("transit_time", None)
        send = _Recorder(_trace_payload(frame))

        hop = SimulationTraceRuntime(send).read_trace().hops[0]

        assert hop.sim_time is None and hop.transit_time is None

    def test_the_step_observation_retains_time_and_index(self):
        send = _Recorder(json.dumps({
            "simulation_mode": True, "frames_before": 2, "frames_after": 9,
            "sim_time": 3.5, "current_index": 8,
        }))

        step = SimulationTraceRuntime(send).step("forward", times=4)

        assert step.frames_before == 2 and step.frames_after == 9
        assert step.sim_time == 3.5 and step.current_index == 8


class TestCaptureBoundSemantics:
    """Alcanzar la cota no prueba saturacion; solo prohibe leer una ausencia."""

    def test_the_effective_limit_is_retained_beside_the_requested_one(self):
        send = _Recorder(_trace_payload(_frame()))

        trace = SimulationTraceRuntime(send).read_trace(limit=9999)

        assert trace.requested_limit == 9999
        # La cota dura de 200 no se mueve.
        assert trace.effective_limit == 200
        assert trace.limit_reached is False

    def test_reaching_the_effective_limit_is_reported_conservatively(self):
        frames = [_frame(index=index) for index in range(3)]
        send = _Recorder(_trace_payload(*frames))

        trace = SimulationTraceRuntime(send).read_trace(limit=3)

        assert trace.effective_limit == 3
        assert len(trace.hops) == 3
        assert trace.limit_reached is True

    def test_the_global_event_count_is_not_a_filtered_match_count(self):
        send = _Recorder(json.dumps({
            "total": 4096, "simulation_mode": True, "frames": [_frame()],
        }))

        trace = SimulationTraceRuntime(send).read_trace(limit=20)

        # `total_in_event_list` es global: no dice cuantos frames del device
        # pedido existian, asi que no puede sostener una lectura de ausencia.
        assert trace.total_in_event_list == 4096
        assert len(trace.hops) == 1
        assert trace.limit_reached is False


class TestNoClassifierExistsYet:
    """El primer LIVE es calibracion: descubrir la representacion, no juzgarla."""

    def test_no_integer_is_mapped_to_a_dhcp_label(self):
        """El mapeo es la superficie donde un nombre inventado entraria."""
        from src.packet_tracer_mcp.domain.services.packet_trace import (
            TRAFFIC_TYPES, traffic_type_label,
        )

        assert TRAFFIC_TYPES == {0: "ICMP", 5: "ARP"}
        for raw in range(0, 256):
            label = traffic_type_label(raw)
            assert "DHCP" not in label.upper()
            # O es uno de los dos medidos, o sigue sin nombre.
            assert label in ("ICMP", "ARP") or label == f"type{raw}"

    def test_a_dhcp_shaped_frame_is_still_reported_as_an_unnamed_type(self):
        """La forma clasica de un DISCOVER no alcanza para nombrarlo."""
        send = _Recorder(_trace_payload(_frame(
            source="0.0.0.0", destination="255.255.255.255", traffic_type_raw=7,
            decisions=[{"layer": 2, "inbound": False,
                        "description": "The device sends the broadcast frame."}],
        )))

        hop = SimulationTraceRuntime(send).read_trace().hops[0]

        assert hop.traffic_type_raw == 7 and hop.traffic_type == "type7"
        # Nada en la observacion tipada convierte esa forma en un protocolo.
        assert "DHCP" not in json.dumps(dataclasses.asdict(hop)).upper()

    def test_no_speculative_protocol_rule_is_encoded(self):
        from pathlib import Path

        source = Path(
            "src/packet_tracer_mcp/infrastructure/execution/simulation_trace_runtime.py",
        ).read_text(encoding="utf-8")
        domain = Path(
            "src/packet_tracer_mcp/domain/services/packet_trace.py",
        ).read_text(encoding="utf-8")

        # Las literales que una regla especulativa necesitaria. La prosa puede
        # nombrar DHCP; una REGLA que lo deduzca de una forma no medida, no.
        for forbidden in (
            "0.0.0.0", "255.255.255.255", "DHCPDISCOVER", "DHCPOFFER", "bootp",
        ):
            assert forbidden not in source
            assert forbidden not in domain
