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
