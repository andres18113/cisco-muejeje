"""Lectura tipada del event list de simulacion de Packet Tracer. DIAGNOSTICO.

Por que existe:
MEG-4 run 10 midio `reachable=False` de punta a punta y no pudo nombrar la
causa. Los dos saltos que este stage no observa -- pertenencia de puerto de
acceso a VLAN y default gateway del endpoint -- son exactamente los que quedan
en el camino, y ninguno se puede confirmar ni descartar con una medida
agregada. Un ping que falla dice QUE no llego; no dice DONDE ni POR QUE.

El modo Simulacion de Packet Tracer si lo dice. Por frame publica el salto
(dispositivo, puerto de entrada, puerto de salida) y el log de decisiones por
capa OSI -- el mismo texto del panel "PDU Details" de su GUI:

    L3 :: The destination IP address is in the same subnet...
    L2 :: The next-hop IP address is not in the ARP table...

Esto es un ADAPTADOR de esas primitivas, no una fuente de verdad nueva. La
logica pura (estado por frame, agregacion, etiquetas de trafico) ya vive en
`domain/services/packet_trace.py` y NO se duplica aca: este modulo aporta el
JS, el transporte y el tipado.

## Lo que este modulo NO hace, a proposito

Es DIAGNOSTICO. Localiza; no certifica. En particular:

* un frame `dropped` en un switch NO establece `ACCESS_PORT`, ni verificado ni
  contradicho: el trace observa el desenlace del paquete, no la pertenencia del
  puerto a una VLAN;
* un frame que muere en el endpoint NO establece el default gateway;
* un trace limpio NO promueve nada a VERIFIED.

Nada de aca entra en `ConfigurationApplicationResult` ni en el plano de
control. Para eso hace falta una relectura DIRECTA del campo reclamado, que es
otro trabajo gobernado (`TD-ACCESSPORT-READBACK-001`).

Contrato de campos, tomado de la superficie real de PT y no de prosa:
`ipc.simulation()` -> `isSimulationMode`, `setSimulationMode`,
`getFrameInstanceCount`, `getFrameInstanceAt`, `getCurrentSimTime`,
`getCurrentFrameInstanceIndex`, `forward`, `backward`, `resetSimulation`;
`frameInstance` -> `getDevice`, `getPreviousDevice`, `getInPort`,
`getOutPortCount`, `getOutPort`, `getSourceString`, `getDestinationString`,
`getUserTrafficType`, `getStartSimTime`, `getTransitTime`, `isFrameSent`,
`isFrameAccepted`, `isFrameDropped`, `isFrameBuffered`, `isFrameOnTransit`,
`isFrameCollidedAtDevice`, `isFrameCollidedOnLink`, `isFrameNotForwarded`,
`isFrameUnexpected`, `getFlowChartNodeCount`, `getFrameDecsionAt` (el typo es
de Packet Tracer); `frameDecision` -> `osiLayer`, `osiIn`, `description`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from ...domain.services.packet_trace import (
    FAILURE_STATUSES,
    frame_status,
    summarize_trace,
    traffic_type_label,
)

SendAndWait = Callable[[str, float], str | None]

#: Acciones de paso admitidas por `ipc.simulation()`, medidas en la superficie.
_STEP_CALLS = {
    "forward": "__s.forward();",
    "back": "__s.backward();",
    "reset": "__s.resetSimulation();",
}


# ----------------------------------------------------------------------
# Constructores de JS. Viven aca, debajo de la fachada MCP, para que el
# adaptador publico y el runtime gobernado compartan UNA sola definicion.
# ----------------------------------------------------------------------

def simulation_mode_js(on: bool) -> str:
    """JS que conmuta Realtime/Simulacion y reporta el antes y el despues."""
    want = "true" if on else "false"
    return (
        "try {"
        "  var __s = ipc.simulation();"
        "  var __before = !!__s.isSimulationMode();"
        f"  __s.setSimulationMode({want});"
        "  reportResult(JSON.stringify({"
        "    before: __before, after: !!__s.isSimulationMode(),"
        "    frames: __s.getFrameInstanceCount(), sim_time: __s.getCurrentSimTime()"
        "  }));"
        "} catch (__e) { reportResult('ERROR:' + __e); }"
    )


def simulation_step_js(action: str, times: int) -> str:
    """JS que avanza, retrocede o reinicia. `action` ya debe estar validada."""
    call = _STEP_CALLS[action]
    loop = (
        call if action == "reset"
        else f"for (var __i = 0; __i < {int(times)}; __i++) {{ {call} }}"
    )
    return (
        "try {"
        "  var __s = ipc.simulation();"
        "  if (!__s.isSimulationMode()) {"
        "    reportResult(JSON.stringify({ simulation_mode: false }));"
        "  } else {"
        "    var __b = __s.getFrameInstanceCount();"
        f"   {loop}"
        "    reportResult(JSON.stringify({"
        "      simulation_mode: true, frames_before: __b,"
        "      frames_after: __s.getFrameInstanceCount(),"
        "      sim_time: __s.getCurrentSimTime(),"
        "      current_index: __s.getCurrentFrameInstanceIndex()"
        "    }));"
        "  }"
        "} catch (__e) { reportResult('ERROR:' + __e); }"
    )


def packet_trace_js(limit: int, device: str, include_decisions: bool) -> str:
    """JS que lee el event list frame por frame con su log de decisiones."""
    lim = max(1, min(int(limit), 200))
    want = json.dumps(device.strip())
    dec = "true" if include_decisions else "false"
    return (
        "try {"
        "  var __s = ipc.simulation();"
        f"  var __lim = {lim}; var __want = {want}; var __wd = {dec};"
        "  var __n = __s.getFrameInstanceCount();"
        "  var __out = [];"
        "  for (var __i = 0; __i < __n && __out.length < __lim; __i++) {"
        "    try {"
        "      var __f = __s.getFrameInstanceAt(__i);"
        "      if (!__f) continue;"
        "      var __dev = __f.getDevice();"
        "      var __dn = __dev ? __dev.getName() : '';"
        "      if (__want && __dn !== __want) continue;"
        "      var __prev = __f.getPreviousDevice();"
        "      var __ip = __f.getInPort();"
        "      var __op = null;"
        # getOutPort(0) lanza cuando getOutPortCount() es 0 (frame en buffer,
        # todavia sin puerto de salida elegido).
        "      try {"
        "        if (__f.getOutPortCount() > 0) {"
        "          var __o = __f.getOutPort(0); __op = __o ? __o.getName() : null;"
        "        }"
        "      } catch (__oe) {}"
        "      var __dl = [];"
        "      if (__wd) {"
        # No hay getDecisionCount(); el conteo de nodos del flowchart coincide
        # con el de decisiones (verificado: 6/6 y 3/3 en un ping real).
        "        var __dc = __f.getFlowChartNodeCount();"
        "        for (var __j = 0; __j < __dc; __j++) {"
        "          try {"
        # getFrameDecsionAt: el typo es de PT, no nuestro.
        "            var __d = __f.getFrameDecsionAt(__j);"
        "            if (!__d) continue;"
        "            __dl.push({ layer: __d.osiLayer, inbound: !!__d.osiIn,"
        "                        description: __d.description });"
        "          } catch (__de) {}"
        "        }"
        "      }"
        "      __out.push({"
        "        index: __i, device: __dn,"
        "        previous_device: __prev ? __prev.getName() : null,"
        "        in_port: __ip ? __ip.getName() : null, out_port: __op,"
        "        source: __f.getSourceString(), destination: __f.getDestinationString(),"
        "        traffic_type_raw: __f.getUserTrafficType(),"
        "        sim_time: __f.getStartSimTime(), transit_time: __f.getTransitTime(),"
        "        sent: !!__f.isFrameSent(), accepted: !!__f.isFrameAccepted(),"
        "        dropped: !!__f.isFrameDropped(), buffered: !!__f.isFrameBuffered(),"
        "        in_transit: !!__f.isFrameOnTransit(),"
        "        collided_at_device: !!__f.isFrameCollidedAtDevice(),"
        "        collided_on_link: !!__f.isFrameCollidedOnLink(),"
        "        not_forwarded: !!__f.isFrameNotForwarded(),"
        "        unexpected: !!__f.isFrameUnexpected(),"
        "        decisions: __dl"
        "      });"
        "    } catch (__pe) {}"
        "  }"
        "  reportResult(JSON.stringify({"
        "    total: __n, simulation_mode: !!__s.isSimulationMode(), frames: __out"
        "  }));"
        "} catch (__e) { reportResult('ERROR:' + __e); }"
    )


# ----------------------------------------------------------------------
# Observaciones tipadas. Frozen y sin defaults optimistas: la ausencia de
# evidencia se nombra, no se rellena.
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class SimulationModeObservation:
    """Estado del modo de simulacion, antes y despues de pedir el cambio."""

    observed: bool
    before: bool = False
    after: bool = False
    frames: int = 0
    message: str = ""


@dataclass(frozen=True)
class SimulationStepObservation:
    """Efecto medido de avanzar/retroceder/reiniciar el event list."""

    observed: bool
    simulation_mode: bool = False
    frames_before: int = 0
    frames_after: int = 0
    message: str = ""


@dataclass(frozen=True)
class TracedHop:
    """Un frame del event list, ya con su estado derivado y su causa.

    `reason` es la ULTIMA decision que PT registro para el frame: es la que
    explica el desenlace. Cadena vacia significa que PT no publico ninguna,
    no que no haya habido causa.
    """

    index: int
    device: str
    previous_device: str
    in_port: str
    out_port: str
    source: str
    destination: str
    traffic_type: str
    status: str
    reason: str

    @property
    def failed(self) -> bool:
        return self.status in FAILURE_STATUSES


@dataclass(frozen=True)
class PacketTraceObservation:
    """Event list leido. DIAGNOSTICO: no promueve ningun campo a VERIFIED."""

    observed: bool
    simulation_mode: bool = False
    total_in_event_list: int = 0
    hops: tuple[TracedHop, ...] = ()
    message: str = ""

    @property
    def failing_hops(self) -> tuple[TracedHop, ...]:
        return tuple(hop for hop in self.hops if hop.failed)

    @property
    def first_failing_hop(self) -> TracedHop | None:
        """El primer salto que no prospero, en orden de event list.

        Es la localizacion que este modulo entrega: un dispositivo, un puerto y
        el texto con el que PT explico el descarte. No es un veredicto sobre
        ninguna configuracion.
        """
        failing = self.failing_hops
        return failing[0] if failing else None

    def localization(self) -> str:
        """Una linea legible con el primer fallo, o por que no hay ninguno."""
        if not self.observed:
            return (
                f"no_trace_observed: {self.message}" if self.message
                else "no_trace_observed"
            )
        if not self.simulation_mode:
            return "realtime_mode: the event list retains no frames"
        if not self.hops:
            return "simulation_mode_without_frames: no traffic was captured"
        hop = self.first_failing_hop
        if hop is None:
            return f"no_failing_frame_among_{len(self.hops)}"
        where = hop.device or "?"
        if hop.in_port:
            where += f" in={hop.in_port}"
        if hop.out_port:
            where += f" out={hop.out_port}"
        return f"{hop.status} at {where}: {hop.reason or 'no decision published'}"


class SimulationTraceRuntime:
    """Adaptador tipado del modo Simulacion. Solo lee; el paso es reversible.

    `setSimulationMode` y `forward` cambian el estado de la aplicacion, no la
    topologia: no crean, borran ni reconfiguran ningun dispositivo, y el modo
    se devuelve a Realtime con la misma llamada. Por eso este runtime no
    participa del contrato de restauracion del workspace.
    """

    def __init__(
        self,
        send_and_wait: SendAndWait,
        *,
        mode_timeout_seconds: float = 10.0,
        step_timeout_seconds: float = 15.0,
        trace_timeout_seconds: float = 20.0,
    ) -> None:
        self._send_and_wait = send_and_wait
        self._mode_timeout_seconds = mode_timeout_seconds
        self._step_timeout_seconds = step_timeout_seconds
        self._trace_timeout_seconds = trace_timeout_seconds

    # -- modo ----------------------------------------------------------
    def set_simulation_mode(self, on: bool) -> SimulationModeObservation:
        payload, error = self._payload(
            simulation_mode_js(on), self._mode_timeout_seconds,
        )
        if payload is None:
            return SimulationModeObservation(observed=False, message=error)
        return SimulationModeObservation(
            observed=True,
            before=bool(payload.get("before")),
            after=bool(payload.get("after")),
            frames=_int(payload.get("frames")),
            message="simulation_mode_readback",
        )

    # -- paso ----------------------------------------------------------
    def step(self, action: str = "forward", times: int = 1) -> SimulationStepObservation:
        normalized = action.strip().casefold()
        if normalized not in _STEP_CALLS:
            return SimulationStepObservation(
                observed=False,
                message=f"unsupported_step_action: {action!r}",
            )
        steps = 1 if normalized == "reset" else max(1, min(int(times), 100))
        payload, error = self._payload(
            simulation_step_js(normalized, steps), self._step_timeout_seconds,
        )
        if payload is None:
            return SimulationStepObservation(observed=False, message=error)
        if payload.get("simulation_mode") is not True:
            return SimulationStepObservation(
                observed=True,
                simulation_mode=False,
                message="realtime_mode: there is nothing to advance",
            )
        return SimulationStepObservation(
            observed=True,
            simulation_mode=True,
            frames_before=_int(payload.get("frames_before")),
            frames_after=_int(payload.get("frames_after")),
            message="simulation_step_readback",
        )

    # -- trace ---------------------------------------------------------
    def read_trace(
        self, *, limit: int = 20, device: str = "", include_decisions: bool = True,
    ) -> PacketTraceObservation:
        payload, error = self._payload(
            packet_trace_js(limit, device, include_decisions),
            self._trace_timeout_seconds,
        )
        if payload is None:
            return PacketTraceObservation(observed=False, message=error)
        raw_frames = payload.get("frames")
        frames = (
            [item for item in raw_frames if isinstance(item, dict)]
            if isinstance(raw_frames, list) else []
        )
        for frame in frames:
            frame["traffic_type"] = traffic_type_label(frame.pop("traffic_type_raw", None))
        # `summarize_trace` escribe `status` en cada frame: es la MISMA
        # derivacion que usa la fachada publica, no una segunda copia.
        summarize_trace(frames)
        return PacketTraceObservation(
            observed=True,
            simulation_mode=bool(payload.get("simulation_mode")),
            total_in_event_list=_int(payload.get("total")),
            hops=tuple(_hop(frame) for frame in frames),
            message="packet_trace_readback",
        )

    # -- transporte ----------------------------------------------------
    def _payload(self, script: str, timeout: float) -> tuple[dict | None, str]:
        raw = self._send_and_wait(script, timeout)
        if raw is None:
            return None, "the bridge returned no response within the budget"
        text = raw.strip()
        if text.startswith("ERROR:") or text.startswith("PT_ERROR:"):
            return None, text
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return None, "the bridge response was not well-formed JSON"
        if not isinstance(parsed, dict):
            return None, "the bridge response was not a JSON object"
        return parsed, ""


def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _hop(frame: dict) -> TracedHop:
    decisions = frame.get("decisions")
    last = decisions[-1] if isinstance(decisions, list) and decisions else {}
    return TracedHop(
        index=_int(frame.get("index")),
        device=_text(frame.get("device")),
        previous_device=_text(frame.get("previous_device")),
        in_port=_text(frame.get("in_port")),
        out_port=_text(frame.get("out_port")),
        source=_text(frame.get("source")),
        destination=_text(frame.get("destination")),
        traffic_type=_text(frame.get("traffic_type")),
        status=_text(frame.get("status")) or frame_status(frame),
        reason=_text(last.get("description")) if isinstance(last, dict) else "",
    )
