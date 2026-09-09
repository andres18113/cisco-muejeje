"""Bounded post-failure Simulation and frame diagnostics; no acceptance authority."""

from __future__ import annotations
import math
import time
from ...domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationPhase,
    ConfigureAccessPort,
    VerificationKind,
)
from ...infrastructure.execution.frame_observer_probe import (
    CHILD_TAG_FIELDS,
    MAX_FRAME_TARGETS,
    MAX_VLAN_CONTROL_TARGETS,
    PacketTracerFrameObserverProbe,
)
from ...infrastructure.execution.simulation_trace_runtime import (
    TRACE_LIMIT_MAX,
    SimulationTraceRuntime,
)


from ..observation.cp_scale_live import (
    _simulation_state_dict, _simulation_mode_dict, _simulation_step_dict,
)
from ...application.cp_scale_live.contracts import CPScaleDiagnosticRecord, CPScaleDiagnosticRequest
from ...domain.enterprise.models.voice_runtime import VoiceApplicationResult
from ..execution.live_bridge import PacketTracerHttpTransport


class PacketTracerCPScaleDiagnostics:
    def __init__(self, transport: PacketTracerHttpTransport) -> None:
        self.transport = transport

    def diagnose(self, request: CPScaleDiagnosticRequest) -> CPScaleDiagnosticRecord:
        evidence = _post_failure_simulation_diagnostic(
            self.transport, request.projection, request.voice.result,
            realtime_failure_established=request.realtime_failure_established,
        )
        original = evidence.get("original_state", {})
        final = evidence.get("restoration", {}).get("verification", {})
        def mode(state: dict[str, object]) -> str:
            if not state.get("observed"):
                return "unobservable"
            return "simulation" if state.get("simulation_mode") else "realtime"
        return CPScaleDiagnosticRecord(
            stage=request.projection.stage, evidence=evidence,
            initial_mode=mode(original),
            final_mode=mode(final),
            attempted_mutations=tuple(
                key for key in ("mode_request", "reset", "progression", "restoration")
                if key in evidence and (key != "restoration" or evidence[key].get("changed"))
            ),
            restoration_verified=bool(evidence.get("restoration_verified")),
            error=str(evidence.get("failure_reason") or ""),
        )


_SIMULATION_TARGET_TIME_SPAN = 60_000
_SIMULATION_STEP_BATCH_SIZE = 10
_SIMULATION_HARD_MAX_STEPS = 600
_SIMULATION_HARD_WALL_CLOCK_SECONDS = 120
_SIMULATION_GLOBAL_EVENT_LIST_CEILING = 2_500
_SIMULATION_STALL_BATCH_LIMIT = 3
_REPRESENTATIVE_PHONE_NAME = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PHONE-02"
_REPRESENTATIVE_SWITCH_NAME = "Switch5"
_CONTROL_ENDPOINT_NAME = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PC-01"
_VOICE_GATEWAY_NAME = "Router4"
#: Re-checked against THIS run before any capture is attributed to the phone.
_PHONE_PREREQUISITES = (
    ("endpoint_interface", "Vlan20"),
    ("endpoint_interface_present", True),
    ("endpoint_address_channel", True),
    ("endpoint_dhcp_enabled", True),
    ("endpoint_ipv4", ""),
)


def _endpoint_attachment(projection, device_name: str) -> dict[str, str] | None:
    """The one planned device with this name and the one link that attaches it."""
    devices = [
        item for item in projection.topology.devices if item.name == device_name
    ]
    if len(devices) != 1:
        return None
    device = devices[0]
    links = [
        item for item in projection.topology.links
        if device.id in (item.device_a_id, item.device_b_id)
    ]
    if len(links) != 1:
        return None
    link = links[0]
    near_is_a = link.device_a_id == device.id
    peer_id = link.device_b_id if near_is_a else link.device_a_id
    peers = [item for item in projection.topology.devices if item.id == peer_id]
    return {
        "device_name": device.name,
        "device_id": device.id,
        "model": getattr(device, "model", ""),
        "endpoint_port": link.port_a if near_is_a else link.port_b,
        "peer_id": peer_id,
        "peer_name": peers[0].name if len(peers) == 1 else "",
        "peer_port": link.port_b if near_is_a else link.port_a,
    }


def _representative_phone_evidence(
    projection, voice_result: VoiceApplicationResult | None, device_name: str,
) -> dict[str, object]:
    """Re-establish the representative's prerequisites from THIS run.

    A phone that already holds an address, or whose channel could not be read,
    cannot carry a solicitation this window would be about. Failing any of them
    yields no trace at all -- never a quiet substitution of a different phone.
    """
    evidence: dict[str, object] = {
        "device_name": device_name,
        "attachment": None,
        "registration": None,
        "prerequisites_met": False,
        "failure_reason": "",
    }
    attachment = _endpoint_attachment(projection, device_name)
    evidence["attachment"] = attachment
    if attachment is None:
        evidence["failure_reason"] = (
            f"The representative endpoint {device_name!r} was not uniquely "
            "attributable to one planned device and one link."
        )
        return evidence
    rows = [
        item for item in (voice_result.registrations if voice_result is not None else ())
        if item.phone_id == attachment["device_id"]
    ]
    if len(rows) != 1:
        evidence["failure_reason"] = (
            f"This run carried {len(rows)} registration row(s) for "
            f"{device_name!r}; exactly one is required to attribute a capture."
        )
        return evidence
    row = rows[0]
    evidence["registration"] = {
        field: getattr(row, field) for field in (
            "phone_id", "extension", "status", "evidence_method", "fresh_evidence",
            "endpoint_interface", "endpoint_interface_present",
            "endpoint_address_channel", "endpoint_dhcp_enabled", "endpoint_ipv4",
        )
    }
    evidence["registration"]["status"] = row.status.value
    unmet = [
        field for field, expected in _PHONE_PREREQUISITES
        if getattr(row, field) != expected
    ]
    if unmet:
        evidence["failure_reason"] = (
            f"{device_name!r} did not hold the representative prerequisites in "
            "this run: " + ", ".join(unmet)
        )
        return evidence
    evidence["prerequisites_met"] = True
    return evidence


def _progression_evidence(
    *,
    target_sim_time_span: int | float,
    step_batch_size: int,
    hard_max_steps: int,
    hard_wall_clock_seconds: int | float,
    global_event_list_ceiling: int,
    stall_batch_limit: int,
) -> dict[str, object]:
    """One conservative evidence shape for every bounded terminal path."""
    return {
        "limits": {
            "target_sim_time_span": target_sim_time_span,
            "step_batch_size": step_batch_size,
            "hard_max_steps": hard_max_steps,
            "hard_wall_clock_seconds": hard_wall_clock_seconds,
            "global_event_list_ceiling": global_event_list_ceiling,
            "stall_batch_limit": stall_batch_limit,
        },
        "monotonicity_policy": (
            "Each post-batch pure simulation-time read must be greater than or "
            "equal to the preceding read; a decrease terminates the window."
        ),
        "stall_policy": (
            f"Terminate after {stall_batch_limit} consecutive completed batches "
            "whose pure simulation-time read does not advance."
        ),
        "termination_reason": "",
        "start_state": None,
        "end_state": None,
        "simulation_time_start": None,
        "simulation_time_end": None,
        "simulation_time_span": None,
        "global_frames_start": None,
        "global_frames_end": None,
        "steps_completed": 0,
        "batches_completed": 0,
        "stall_batches": 0,
        "wall_clock_elapsed_seconds": 0.0,
        "progress": [],
        # Every terminal reason is a capture boundary, never evidence of absence.
        "negative_absence_interpretable": False,
    }


def _usable_simulation_progress_state(state) -> bool:
    return bool(
        state.observed
        and state.simulation_mode
        and type(state.frames) is int
        and state.frames >= 0
    )


def _usable_simulation_time(value) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _bounded_simulation_progression(
    runtime,
    *,
    target_sim_time_span: int | float = _SIMULATION_TARGET_TIME_SPAN,
    step_batch_size: int = _SIMULATION_STEP_BATCH_SIZE,
    hard_max_steps: int = _SIMULATION_HARD_MAX_STEPS,
    hard_wall_clock_seconds: int | float = _SIMULATION_HARD_WALL_CLOCK_SECONDS,
    global_event_list_ceiling: int = _SIMULATION_GLOBAL_EVENT_LIST_CEILING,
    stall_batch_limit: int = _SIMULATION_STALL_BATCH_LIMIT,
    monotonic=time.monotonic,
) -> dict[str, object]:
    """Advance in fixed batches until simulation time or one hard ceiling wins.

    Each successful batch is followed by a PURE state read.  The complete step
    and state observations are retained even when that read fires a ceiling.
    No terminal reason makes a missing packet interpretable as a negative.
    """
    evidence = _progression_evidence(
        target_sim_time_span=target_sim_time_span,
        step_batch_size=step_batch_size,
        hard_max_steps=hard_max_steps,
        hard_wall_clock_seconds=hard_wall_clock_seconds,
        global_event_list_ceiling=global_event_list_ceiling,
        stall_batch_limit=stall_batch_limit,
    )
    started = monotonic()
    initial = runtime.read_simulation_state()
    initial_dict = _simulation_state_dict(initial)
    evidence["start_state"] = initial_dict
    evidence["end_state"] = initial_dict
    if not _usable_simulation_progress_state(initial):
        evidence["termination_reason"] = "SIMULATION_STATE_UNOBSERVABLE"
        evidence["wall_clock_elapsed_seconds"] = max(0.0, monotonic() - started)
        return evidence
    if not _usable_simulation_time(initial.sim_time):
        evidence["termination_reason"] = "SIM_TIME_UNOBSERVABLE"
        evidence["wall_clock_elapsed_seconds"] = max(0.0, monotonic() - started)
        return evidence

    start_sim_time = initial.sim_time
    previous_sim_time = initial.sim_time
    evidence.update({
        "simulation_time_start": start_sim_time,
        "simulation_time_end": start_sim_time,
        "simulation_time_span": 0,
        "global_frames_start": initial.frames,
        "global_frames_end": initial.frames,
    })
    if initial.frames >= global_event_list_ceiling:
        evidence["termination_reason"] = "EVENT_LIST_CEILING"
        evidence["wall_clock_elapsed_seconds"] = max(0.0, monotonic() - started)
        return evidence

    elapsed = 0.0
    while not evidence["termination_reason"]:
        completed = int(evidence["steps_completed"])
        if completed >= hard_max_steps:
            evidence["termination_reason"] = "HARD_MAX_STEPS_REACHED"
            break
        if elapsed >= hard_wall_clock_seconds:
            evidence["termination_reason"] = "HARD_WALL_CLOCK_REACHED"
            break

        requested = min(step_batch_size, hard_max_steps - completed)
        step = runtime.step("forward", times=requested)
        entry: dict[str, object] = {
            "batch": int(evidence["batches_completed"]) + 1,
            "steps_requested": requested,
            "cumulative_steps": completed,
            "step": _simulation_step_dict(step),
            "state": None,
        }
        progress = evidence["progress"]
        assert isinstance(progress, list)
        progress.append(entry)
        if not (step.observed and step.simulation_mode):
            evidence["termination_reason"] = "STEP_FAILED"
            elapsed = max(0.0, monotonic() - started)
            evidence["wall_clock_elapsed_seconds"] = elapsed
            entry["wall_clock_elapsed_seconds"] = elapsed
            break

        completed += requested
        evidence["steps_completed"] = completed
        evidence["batches_completed"] = int(evidence["batches_completed"]) + 1
        entry["cumulative_steps"] = completed

        state = runtime.read_simulation_state()
        state_dict = _simulation_state_dict(state)
        entry["state"] = state_dict
        evidence["end_state"] = state_dict
        elapsed = max(0.0, monotonic() - started)
        evidence["wall_clock_elapsed_seconds"] = elapsed
        entry["wall_clock_elapsed_seconds"] = elapsed
        if not _usable_simulation_progress_state(state):
            evidence["termination_reason"] = "SIMULATION_STATE_UNOBSERVABLE"
            break
        if not _usable_simulation_time(state.sim_time):
            evidence["termination_reason"] = "SIM_TIME_UNOBSERVABLE"
            break

        current_sim_time = state.sim_time
        evidence["simulation_time_end"] = current_sim_time
        evidence["simulation_time_span"] = current_sim_time - start_sim_time
        evidence["global_frames_end"] = state.frames
        entry["simulation_time_span"] = evidence["simulation_time_span"]

        if current_sim_time < previous_sim_time:
            evidence["termination_reason"] = "SIM_TIME_NON_MONOTONIC"
            break
        if current_sim_time == previous_sim_time:
            evidence["stall_batches"] = int(evidence["stall_batches"]) + 1
        else:
            evidence["stall_batches"] = 0
        entry["stall_batches"] = evidence["stall_batches"]
        previous_sim_time = current_sim_time

        if state.frames >= global_event_list_ceiling:
            evidence["termination_reason"] = "EVENT_LIST_CEILING"
        elif current_sim_time - start_sim_time >= target_sim_time_span:
            evidence["termination_reason"] = "TARGET_SIM_TIME_SPAN_REACHED"
        elif completed >= hard_max_steps:
            evidence["termination_reason"] = "HARD_MAX_STEPS_REACHED"
        elif elapsed >= hard_wall_clock_seconds:
            evidence["termination_reason"] = "HARD_WALL_CLOCK_REACHED"
        elif int(evidence["stall_batches"]) >= stall_batch_limit:
            evidence["termination_reason"] = "SIM_TIME_STALLED"

    return evidence


def _traced_hop_dict(hop) -> dict[str, object]:
    """Every measured field. A summary here would be evidence nobody can re-read."""
    return {
        "index": hop.index,
        "device": hop.device,
        "previous_device": hop.previous_device,
        "in_port": hop.in_port,
        "out_port": hop.out_port,
        "source": hop.source,
        "destination": hop.destination,
        "traffic_type_raw": hop.traffic_type_raw,
        "traffic_type": hop.traffic_type,
        "sim_time": hop.sim_time,
        "transit_time": hop.transit_time,
        "status": hop.status,
        "decisions": [
            {
                "layer": item.layer,
                "inbound": item.inbound,
                "description": item.description,
            }
            for item in hop.decisions
        ],
    }


def _packet_trace_dict(trace) -> dict[str, object]:
    return {
        "observed": trace.observed,
        "simulation_mode": trace.simulation_mode,
        # Global, never a filtered match count: it cannot support an absence.
        "total_in_event_list": trace.total_in_event_list,
        "requested_limit": trace.requested_limit,
        "effective_limit": trace.effective_limit,
        "limit_reached": trace.limit_reached,
        "hops_captured": len(trace.hops),
        "message": trace.message,
        "hops": [_traced_hop_dict(hop) for hop in trace.hops],
    }


# ----------------------------------------------------------------------
# VOICE_REALTIME_CONTINUITY
#
# The two windows are not interchangeable and must never be confused:
#
#   NORMAL_WINDOW  -- Realtime only. The authoritative voice acquisition and
#                     its verification. This is what 0/21 is a statement about.
#   POST_FAILURE_SIMULATION_DIAGNOSTIC -- Simulation, bounded stepping,
#                     diagnostic only, never configuration verification.
#
# In Simulation mode packets do not progress autonomously, so a 180-second
# convergence window that elapsed while it was active did not measure what the
# same wall clock measures in Realtime. Proving both edges of the authoritative
# window were Realtime is what makes its result attributable at all.
# ----------------------------------------------------------------------


_DHCP_DISCOVER_DECISION = "dhcp client constructs a discover packet"
_BPDU_DECISION = "stp process sends out a configuration bpdu"
_STP_DROP_DECISION = "is blocked by stp"
#: Ayuda de descubrimiento, no una afirmacion. Que un nombre case con `vlan` no
#: hace que su getter devuelva una VLAN; sirve para no tener que releer 47
#: nombres a mano en el journal.
_FRAME_VLAN_CANDIDATE_NEEDLES = (
    "vlan", "tag", "dot1q", "802", "encapsulation", "header", "ethernet",
)


def _decision_match(hop: dict, needle: str) -> str:
    """La decision literal que identifica este frame, o cadena vacia."""
    for decision in hop.get("decisions") or ():
        description = str(decision.get("description") or "")
        if needle in description.casefold():
            return description
    return ""


def _frame_target(hop: dict, decision: str, role: str) -> dict[str, object]:
    """Lo que hay que conservar de un frame elegido, antes de enumerarlo."""
    return {
        "role": role,
        "index": hop.get("index"),
        "device": hop.get("device"),
        "previous_device": hop.get("previous_device"),
        "in_port": hop.get("in_port"),
        "out_port": hop.get("out_port"),
        "sim_time": hop.get("sim_time"),
        "traffic_type_raw": hop.get("traffic_type_raw"),
        "status": hop.get("status"),
        "identifying_decision": decision,
    }


#: Qué getter hijo pertenece a cada lado del salto. Un frame de EGRESO se lee
#: en `getOutFrame` y uno de INGRESO en `getInFrame`; cruzarlos compararía dos
#: lados distintos del mismo salto y llamaría preservación a esa confusión.
_ROLE_TAG_GETTER = {"phone_dhcp": "getOutFrame", "switch_dhcp": "getInFrame"}
#: De dónde sale la VLAN que un control da por conocida. No es una lectura de
#: Packet Tracer: es lo que el plan tipado configuró en ese puerto.
_CONTROL_VLAN_SOURCE = "TYPED_ACCESS_PORT_PLAN_SINGLE_VLAN"
#: Un control se lee SIEMPRE en el lado de entrada, y por eso el getter es una
#: constante y no una rama: si el codigo pudiera elegir el otro lado, podria
#: emparejar la VLAN conocida de un puerto con el tag del lado contrario, que es
#: justo la suposicion que una calibracion no puede permitirse.
_CONTROL_TAG_GETTER = "getInFrame"


def _tag_field_observation(target, frame, getter: str) -> dict[str, object]:
    """Los cuatro campos medidos de UN lado, o por qué no hay ninguno.

    La atribución decide primero y sola. Si el frame enumerado no vuelve a ser
    el que se eligió, no hay valores que reportar: leer el tag de otro frame y
    ponerle este nombre sería exactamente la sustitución silenciosa que el
    contrato de identidad existe para impedir, y un valor mal atribuido es peor
    que ninguno porque parece una respuesta.
    """
    observation: dict[str, object] = {
        "role": target.get("role"),
        "getter": getter,
        "frame_index": target.get("index"),
        "device": target.get("device"),
        "previous_device": target.get("previous_device"),
        "in_port": target.get("in_port"),
        "out_port": target.get("out_port"),
        "traffic_type_raw": target.get("traffic_type_raw"),
        "sim_time": target.get("sim_time"),
        "identifying_decision": target.get("identifying_decision"),
        "identity_reconfirmed": bool(target.get("identity_reconfirmed")),
        "observed_sim_time": None,
        "child_returned": False,
        "fields": {},
        "failure_reason": "",
    }
    if frame is None or not observation["identity_reconfirmed"]:
        observation["failure_reason"] = (
            "The enumerated frame could not be re-attributed to this target, "
            "so no tag field may be read as belonging to it."
        )
        return observation
    observation["observed_sim_time"] = frame.observed_sim_time
    child = next(
        (item for item in frame.children if item.getter == getter), None,
    )
    if child is None:
        observation["failure_reason"] = (
            f"{getter} left nothing this enumeration retained."
        )
        return observation
    if child.returned_null:
        observation["failure_reason"] = (
            f"{getter} returned no object, so there is no tag to read. That is "
            "an absent reading, never a zero."
        )
        return observation
    observation["child_returned"] = True
    by_name = child.tag_by_name
    # Los CUATRO campos viajan siempre, decidido cada uno por su cuenta: un
    # campo que no vino se queda sin observar en vez de desaparecer, porque una
    # clave ausente se lee como si nadie la hubiera preguntado.
    observation["fields"] = {
        name: {
            "observed": bool(by_name[name].observed) if name in by_name else False,
            "type_name": by_name[name].type_name if name in by_name else "",
            "numeric_value": (
                by_name[name].numeric_value if name in by_name else None
            ),
            "error": by_name[name].error if name in by_name else "",
        }
        for name in CHILD_TAG_FIELDS
    }
    return observation


def _tag_value(side, name: str):
    """El número de ESE campo, o None si ese lado no lo observó."""
    row = (side or {}).get("fields", {}).get(name) or {}
    return row.get("numeric_value") if row.get("observed") else None


def _tag_link_comparison(phone_tag, switch_tag) -> dict[str, object]:
    """El frame que SALE del teléfono contra el que ENTRA al switch.

    Cada igualdad se calcula sólo con dos lecturas frescas del mismo campo. Una
    ausencia de un lado no vale como acuerdo ni como desacuerdo: se queda
    UNOBSERVABLE, y una diferencia medida sigue siendo una diferencia aunque el
    resto de los campos coincida.
    """
    comparison: dict[str, object] = {
        "observes": (
            "The four measured tag fields on the phone's DHCP egress frame and "
            "on the switch's ingress copy of that same frame. The member set is "
            "strongly consistent with an Ethernet frame carrying 802.1Q-shaped "
            "tag metadata; what is retained here is what those four properties "
            "returned, not a proven header contract."
        ),
        "phone_dhcp_out_tag": phone_tag,
        "switch_dhcp_in_tag": switch_tag,
        "field_matches": {name: "UNOBSERVABLE" for name in CHILD_TAG_FIELDS},
        "vlan_value_match": "UNOBSERVABLE",
        "tpid_match": "UNOBSERVABLE",
        "tpid_hex": "",
        "tpid_hex_withheld_reason": "",
        "tag_fields_match": "UNOBSERVABLE",
        "same_observed_start_sim_time": "UNOBSERVABLE",
        "failure_reason": "",
    }
    if phone_tag is None or switch_tag is None:
        comparison["failure_reason"] = (
            "Both sides of the link are required and one of them was never "
            "selected in this window."
        )
        return comparison

    matches: dict[str, str] = {}
    for name in CHILD_TAG_FIELDS:
        near = _tag_value(phone_tag, name)
        far = _tag_value(switch_tag, name)
        if near is None or far is None:
            matches[name] = "UNOBSERVABLE"
        else:
            matches[name] = "YES" if near == far else "NO"
    comparison["field_matches"] = matches
    comparison["vlan_value_match"] = matches["vlanId"]
    comparison["tpid_match"] = matches["tpid"]
    if "NO" in matches.values():
        # Un desacuerdo medido decide solo. El acuerdo del resto de los campos
        # no lo diluye ni lo convierte en parcial.
        comparison["tag_fields_match"] = "NO"
    elif all(verdict == "YES" for verdict in matches.values()):
        comparison["tag_fields_match"] = "YES"
    elif any(verdict == "YES" for verdict in matches.values()):
        comparison["tag_fields_match"] = "PARTIAL"

    # Base 16 del MISMO número leído, y sólo cuando ese número no es negativo.
    # 33024 se reporta 0x8100 porque eso es lo que 33024 vale. Un negativo, en
    # cambio, necesita una anchura de campo para significar algo en hexadecimal,
    # y este repositorio no ha medido con cuántos bits PT guarda `tpid`:
    # renderizarlo igual invitaría a leer como cabecera un valor que nadie
    # observó. Se dice que se retiene, en vez de desaparecer.
    for side in (phone_tag, switch_tag):
        tpid = _tag_value(side, "tpid")
        if not isinstance(tpid, int) or isinstance(tpid, bool):
            continue
        if tpid < 0:
            comparison["tpid_hex_withheld_reason"] = (
                f"The measured tpid {tpid} is negative. A hexadecimal rendering "
                "would imply a field width this repository has not measured, so "
                "only the exact decimal reading is reported."
            )
        else:
            comparison["tpid_hex"] = hex(tpid)
        break

    near_time = phone_tag.get("observed_sim_time")
    far_time = switch_tag.get("observed_sim_time")
    if near_time is not None and far_time is not None:
        comparison["same_observed_start_sim_time"] = (
            "YES" if near_time == far_time else "NO"
        )
    return comparison


def _single_vlan_access_ports(projection, switch_name: str) -> dict[str, int]:
    """Los puertos de ESTE switch cuya VLAN el plan tipado da sin ambigüedad.

    Un puerto de teléfono lleva datos Y voz, así que un frame suyo no puede
    calibrar el significado de un campo: cualquiera de los dos valores
    parecería correcto. Un puerto con VLAN de datos y SIN VLAN de voz tiene una
    sola respuesta, y esa respuesta sale del plan -- escribir un nombre de
    interfaz acá convertiría el control en su propia hipótesis.
    """
    configuration = getattr(projection, "configuration", None)
    ports: dict[str, int] = {}
    for action in getattr(configuration, "actions", []) or ():
        if not isinstance(action, ConfigureAccessPort):
            continue
        if getattr(action, "device_name", "") != switch_name:
            continue
        if action.voice_vlan_id is not None:
            continue
        vlan = action.data_vlan_id
        if isinstance(vlan, bool) or not isinstance(vlan, int):
            continue
        interface = str(action.interface or "")
        if interface:
            ports[interface] = vlan
    return ports


def _vlan_control_candidates(switch_hops, switch_name: str, ports, taken):
    """Frames YA capturados que ENTRARON por un puerto de VLAN única conocida.

    Sólo el lado de entrada califica. La VLAN esperada sale del puerto por el
    que el frame entró y el valor observado se lee en el hijo de ESE mismo lado,
    así que no hace falta ninguna suposición sobre lo que el switch hace entre
    una boca y la otra.

    Un frame que sólo SALE por un puerto conocido no es un control aunque su
    copia de entrada traiga un tag que cuadre: emparejar la VLAN del puerto de
    salida con el tag del lado de entrada asumiría que el switch preserva la
    VLAN a través de ese reenvío -- comportamiento L2 corriente que este
    repositorio no ha medido --, y una calibración que se apoya en una
    suposición no medida no califica nada. Se cuentan y se nombran en vez de
    colarse como controles con veredicto nulo.

    No se genera tráfico para tener un control ni se amplía la ventana: si esta
    captura no trajo ninguno, no hay control y se dice cuál de las dos ausencias
    es.
    """
    candidates: list[dict[str, object]] = []
    seen_ports: set[str] = set()
    egress_only = 0
    for hop in switch_hops:
        if hop.get("device") != switch_name:
            continue
        index = hop.get("index")
        if not isinstance(index, int) or index in taken:
            continue
        in_name = str(hop.get("in_port") or "")
        expected = ports.get(in_name)
        if expected is None:
            if ports.get(str(hop.get("out_port") or "")) is not None:
                egress_only += 1
            continue
        if in_name in seen_ports:
            continue
        seen_ports.add(in_name)
        candidates.append({
            "index": index,
            "device": hop.get("device"),
            "port": in_name,
            "port_side": "in",
            "in_port": hop.get("in_port"),
            "out_port": hop.get("out_port"),
            "sim_time": hop.get("sim_time"),
            "traffic_type_raw": hop.get("traffic_type_raw"),
            "status": hop.get("status"),
            "expected_vlan": expected,
            "expected_vlan_source": _CONTROL_VLAN_SOURCE,
        })
    return candidates, egress_only

def _frame_vlan_field_semantics(controls) -> str:
    """Hasta dónde queda cualificado `vlanId`, y nunca más allá."""
    judged = [item for item in controls if item.get("vlan_match") is not None]
    if any(item["vlan_match"] is False for item in judged):
        # Un control que no cuadra es información, no ruido: se nombra y no se
        # promedia contra los que sí cuadraron.
        return "CONTRADICTED_BY_CONTROL"
    matched = [item for item in judged if item["vlan_match"] is True]
    if len(matched) >= 2 and len({item["expected_vlan"] for item in matched}) >= 2:
        return "STRONGLY_SUPPORTED_BY_MULTIVLAN_CONTROL"
    if matched:
        return "SUPPORTED_BY_CONTROL"
    return "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"


def _frame_observer_discovery(
    transport,
    *,
    phone_name: str,
    switch_name: str,
    phone_trace,
    switch_trace,
    single_vlan_ports: dict[str, int] | None = None,
) -> dict[str, object]:
    """Enumera los miembros de los dos frames que la pregunta compara.

    Uno es el DHCP Discover del telefono; el otro es una BPDU que el switch
    emite por un puerto de telefono. Mismo puerto fisico NO implica misma VLAN,
    y misma captura NO implica mismo instante: por eso cada objetivo conserva su
    propio `sim_time` y su propia decision identificadora, y nada aqui deriva
    una VLAN del tipo de trafico.
    """
    observation: dict[str, object] = {
        "diagnostic": "FRAME_OBSERVER_DISCOVERY",
        "observes": (
            "Which members a Simulation frameInstance exposes on this build, "
            "and -- on the child object the two measured getters return -- the "
            "four measured tag fields, read as values. Every OTHER discovered "
            "member is still only a name: evidence that something exists, "
            "never evidence of what it means."
        ),
        "targets": [],
        "attempted": False,
        "switch_bpdu_absent_reason": "",
        # La calibración es opcional por diseño y va aparte de la comparación
        # DHCP: un control ausente, o uno que contradice, no puede tocar los
        # valores que los dos frames del enlace devolvieron.
        "vlan_controls": [],
        "vlan_control_absent_reason": "",
        "vlan_control_dropped": 0,
        "vlan_control_egress_only_hops": 0,
        "frame_vlan_field_semantics": "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED",
        # Ningún BPDU de esta fase cualifica una lectura de STP por VLAN, y su
        # ausencia acotada tampoco la refuta.
        "vlan_scoped_stp_interpretation": "STILL_INFERENCE",
        "link_tag_comparison": _tag_link_comparison(None, None),
        "failure_reason": "",
    }
    phone_hops = (phone_trace or {}).get("hops") or []
    switch_hops = (switch_trace or {}).get("hops") or []

    targets: list[dict[str, object]] = []
    phone_hop = next(
        (
            hop for hop in phone_hops
            if hop.get("device") == phone_name
            and _decision_match(hop, _DHCP_DISCOVER_DECISION)
        ),
        None,
    )
    if phone_hop is not None:
        targets.append(_frame_target(
            phone_hop,
            _decision_match(phone_hop, _DHCP_DISCOVER_DECISION),
            "phone_dhcp",
        ))
        # El MISMO frame en el switch, probado por el camino y no por el reloj:
        # `previous_device` dice que vino de ESTE telefono. La caida de OTRO
        # telefono en el mismo instante no es este frame.
        switch_hop = next(
            (
                hop for hop in switch_hops
                if hop.get("device") == switch_name
                and hop.get("previous_device") == phone_name
                and hop.get("traffic_type_raw") == phone_hop.get("traffic_type_raw")
                and hop.get("sim_time") == phone_hop.get("sim_time")
            ),
            None,
        )
        if switch_hop is not None:
            drop_decision = _decision_match(switch_hop, _STP_DROP_DECISION)
            targets.append(_frame_target(
                switch_hop,
                drop_decision or "",
                "switch_dhcp",
            ))
            # La comparacion mas fuerte es en el MISMO device y el MISMO puerto
            # fisico: la BPDU tiene que salir por donde entro el DHCP.
            edge_port = switch_hop.get("in_port")
            bpdu_hop = next(
                (
                    hop for hop in switch_hops
                    if hop.get("device") == switch_name
                    and hop.get("out_port") == edge_port
                    and _decision_match(hop, _BPDU_DECISION)
                ),
                None,
            )
            if bpdu_hop is not None:
                targets.append(_frame_target(
                    bpdu_hop,
                    _decision_match(bpdu_hop, _BPDU_DECISION),
                    "switch_bpdu",
                ))
            else:
                # El switch rota sus BPDU entre puertos y la captura esta
                # acotada: que esta ventana no traiga una para ESTE puerto no
                # dice nada sobre el puerto. Se nombra en vez de faltar.
                observation["switch_bpdu_absent_reason"] = (
                    "This bounded capture held no configuration BPDU leaving "
                    f"{edge_port!r}; absence here is a property of the window, "
                    "not of the port."
                )

    times = {
        item.get("sim_time") for item in targets
        if item.get("sim_time") is not None
    }
    # Misma captura NO es mismo instante. Sin igualdad exacta de `sim_time` no
    # se afirma simultaneidad de ninguna forma.
    observation["same_capture"] = bool(targets)
    observation["same_instant"] = bool(targets) and len(times) == 1
    observation["targets"] = targets
    indices = [
        int(item["index"]) for item in targets
        if isinstance(item.get("index"), int)
    ]
    if not indices:
        observation["failure_reason"] = (
            "No frame carried the exact identifying decision text, so there was "
            "nothing whose members could be attributed."
        )
        return observation

    # El control de calibración viaja en la MISMA llamada y en su propia lista.
    # Meterlo entre los objetivos le daría su `sim_time` a la comparación DHCP
    # y haría que el par dejara de verse simultáneo por un frame que no es suyo.
    ports = dict(single_vlan_ports or {})
    controls, egress_only = _vlan_control_candidates(
        switch_hops, switch_name, ports, set(indices),
    )
    observation["vlan_control_egress_only_hops"] = egress_only
    budget = max(0, min(MAX_VLAN_CONTROL_TARGETS, MAX_FRAME_TARGETS - len(indices)))
    observation["vlan_control_dropped"] = max(0, len(controls) - budget)
    controls = controls[:budget]
    for position, control in enumerate(controls, start=1):
        control["role"] = f"vlan_control_{position}"
    if not controls and not ports:
        observation["vlan_control_absent_reason"] = (
            "The typed plan configures no single-VLAN access port on "
            f"{switch_name!r}, so nothing in this window has an independently "
            "known VLAN."
        )
    elif not controls:
        # Las dos ausencias no son la misma y confundirlas perdería justo el
        # hecho que decide si otra ventana podría traer un control.
        observation["vlan_control_absent_reason"] = (
            "No frame ENTERED a single-VLAN access port of "
            f"{switch_name!r} in this bounded capture"
            + (
                f"; {egress_only} frame(s) only LEFT one, and an access-port "
                "egress copy carries no tag to read."
                if egress_only else
                "; absence here is a property of the window, not of those ports."
            )
        )
    elif observation["vlan_control_dropped"]:
        observation["vlan_control_absent_reason"] = (
            f"{observation['vlan_control_dropped']} further single-VLAN "
            "control frame(s) were left out by the enumeration bound of "
            f"{MAX_FRAME_TARGETS} targets."
        )
    indices.extend(int(item["index"]) for item in controls)

    observation["attempted"] = True
    discovery = PacketTracerFrameObserverProbe(
        transport.send_and_wait,
    ).discover_frame_observers(indices)
    observation["discovery"] = {
        "observed": discovery.observed,
        "simulation_mode": discovery.simulation_mode,
        "frame_count": discovery.frame_count,
        "failure_reason": discovery.failure_reason,
        "frames": [
            {
                "index": frame.index,
                "in_bounds": frame.in_bounds,
                "frame_found": frame.frame_found,
                "observed_device": frame.observed_device,
                "observed_in_port": frame.observed_in_port,
                "observed_sim_time": frame.observed_sim_time,
                "observed_traffic_type": frame.observed_traffic_type,
                "truncated": frame.truncated,
                "members": list(frame.members),
                "observers": [
                    {
                        "name": item.name,
                        "type_name": item.type_name,
                        "is_callable": item.is_callable,
                        "arity": item.arity,
                        "read_only_name": item.read_only_name,
                    }
                    for item in frame.observers
                ],
                # Lo que devolvio cada uno de los dos getters medidos. Es la
                # pregunta entera de esta fase: recogerlo y no escribirlo
                # devolveria un LIVE gobernado sin la respuesta que lo motivo.
                "children": [
                    {
                        "getter": child.getter,
                        "invoked": child.invoked,
                        "returned_null": child.returned_null,
                        "type_name": child.type_name,
                        "error": child.error,
                        "truncated": child.truncated,
                        "members": list(child.members),
                        "observers": [
                            {
                                "name": item.name,
                                "type_name": item.type_name,
                                "is_callable": item.is_callable,
                                "arity": item.arity,
                                "read_only_name": item.read_only_name,
                            }
                            for item in child.observers
                        ],
                        "candidates": list(child.candidates(
                            _FRAME_VLAN_CANDIDATE_NEEDLES,
                        )),
                        # Los cuatro campos medidos, con lo que trajo cada uno.
                        "tag": [
                            {
                                "name": item.name,
                                "observed": item.observed,
                                "type_name": item.type_name,
                                "numeric_value": item.numeric_value,
                                "error": item.error,
                            }
                            for item in child.tag
                        ],
                    }
                    for child in frame.children
                ],
            }
            for frame in discovery.frames
        ],
    }
    # La identidad del frame se vuelve a probar contra el objetivo elegido: un
    # indice sigue nombrando un frame solo mientras ese event list siga en pie.
    by_index = {frame.index: frame for frame in discovery.frames}
    for target in targets:
        frame = by_index.get(target.get("index"))
        target["identity_reconfirmed"] = bool(
            frame is not None
            and frame.matches(
                device=str(target.get("device") or ""),
                sim_time=target.get("sim_time"),
                traffic_type=target.get("traffic_type_raw"),
                in_port=str(target.get("in_port") or ""),
            )
        )

    # Sólo AHORA, con la atribución hecha, se leen los cuatro campos de cada
    # lado. Cada rol lee su propio getter: el egreso del teléfono en
    # `getOutFrame` y el ingreso del switch en `getInFrame`.
    by_role = {str(item.get("role")): item for item in targets}
    sides: dict[str, dict[str, object] | None] = {}
    for role, getter in _ROLE_TAG_GETTER.items():
        target = by_role.get(role)
        sides[role] = None if target is None else _tag_field_observation(
            target, by_index.get(target.get("index")), getter,
        )
    observation["link_tag_comparison"] = _tag_link_comparison(
        sides["phone_dhcp"], sides["switch_dhcp"],
    )

    qualified: list[dict[str, object]] = []
    for control in controls:
        frame = by_index.get(control.get("index"))
        control["identity_reconfirmed"] = bool(
            frame is not None
            and frame.matches(
                device=str(control.get("device") or ""),
                sim_time=control.get("sim_time"),
                traffic_type=control.get("traffic_type_raw"),
                # El puerto de ENTRADA es el que da la VLAN esperada, así que
                # es parte de la identidad que hay que reconfirmar.
                in_port=str(control.get("in_port") or ""),
            )
        )
        row = _tag_field_observation(control, frame, _CONTROL_TAG_GETTER)
        row.update({
            # Un control se elige por su puerto, no por un texto de decisión.
            "identifying_decision": "",
            "port": control.get("port"),
            "port_side": control.get("port_side"),
            "status": control.get("status"),
            "expected_vlan": control.get("expected_vlan"),
            "expected_vlan_source": control.get("expected_vlan_source"),
        })
        observed_vlan = _tag_value(row, "vlanId")
        row["observed_vlan"] = observed_vlan
        row["vlan_match"] = (
            None if observed_vlan is None
            else observed_vlan == control.get("expected_vlan")
        )
        qualified.append(row)
    observation["vlan_controls"] = qualified
    observation["frame_vlan_field_semantics"] = _frame_vlan_field_semantics(
        qualified,
    )
    return observation


def _post_failure_simulation_diagnostic(
    transport,
    projection,
    voice_result: VoiceApplicationResult | None,
    *,
    realtime_failure_established: bool = True,
    phone_name: str = _REPRESENTATIVE_PHONE_NAME,
    control_name: str = _CONTROL_ENDPOINT_NAME,
    target_sim_time_span: int | float = _SIMULATION_TARGET_TIME_SPAN,
    step_batch_size: int = _SIMULATION_STEP_BATCH_SIZE,
    hard_max_steps: int = _SIMULATION_HARD_MAX_STEPS,
    hard_wall_clock_seconds: int | float = _SIMULATION_HARD_WALL_CLOCK_SECONDS,
    global_event_list_ceiling: int = _SIMULATION_GLOBAL_EVENT_LIST_CEILING,
    stall_batch_limit: int = _SIMULATION_STALL_BATCH_LIMIT,
    monotonic=time.monotonic,
) -> dict[str, object]:
    """Bounded raw capture after the voice failure. Never raises, always restores.

    Owns one explicit window: read the original mode purely, enter Simulation
    only if it was not already there, reset, advance in fixed batches until the
    simulation-time target or one independent hard ceiling, capture four raw
    device scopes, and give the mode back verifying with ANOTHER pure read. A
    restoration that cannot be verified is recorded on its own key -- it never
    becomes, hides or overwrites the Floor-1 failure this stage already carries.
    """
    evidence: dict[str, object] = {
        "diagnostic": "POST_FAILURE_SIMULATION_DIAGNOSTIC",
        "observes": (
            "Events generated or processed AFTER entering Simulation mode, "
            "following the already-established Floor-1 voice failure. Simulation "
            "mode changes execution semantics -- packets do not progress "
            "autonomously and must be stepped -- so this is NOT the original "
            "realtime voice acquisition window and may not be described as it."
        ),
        # This slice discovers a representation; it does not judge one. Both stay
        # UNOBSERVABLE until a live capture shows how this build renders DHCP.
        "dhcp_trace_identity": "UNOBSERVABLE",
        "control_dhcp_visibility": "UNOBSERVABLE",
        "positive_control_capability": "UNSAFE_OR_MUTATING",
        "positive_control_implemented": False,
        "dhcp_positive_control_observed": "UNOBSERVABLE",
        "control_semantics": (
            "Passive same-window visibility observation only. No acquisition is "
            "forced: the repository's governed DHCP acquisition paths mutate an "
            "endpoint or disposable probe topology/configuration. An empty PC-01 "
            "trace does not establish event-list eligibility and says nothing "
            "about the representative phone's own switching path."
        ),
        "phone": None,
        "control_name": control_name,
        "status": "ATTEMPTED",
        "captured": False,
        "restoration_verified": False,
        "failure_reason": "",
        "post_failure_simulation_state": {
            "phone_address_readback": "DEFERRED",
            "router4_voice_binding_readback": "DEFERRED",
            "reason": (
                "No cheap typed read-only post-restoration path is available in "
                "SimulationTraceRuntime; adding voice or IOS orchestration is deferred."
            ),
        },
    }
    if not realtime_failure_established:
        # There is no valid normal failure to diagnose. Opening a Simulation
        # window here would produce evidence about nothing, at the cost of a
        # real application-state transition.
        evidence["status"] = "NOT_APPLICABLE"
        evidence["failure_reason"] = (
            "No authoritative REALTIME voice failure was established, so there "
            "is nothing for this diagnostic to be about."
        )
        return evidence
    phone = _representative_phone_evidence(projection, voice_result, phone_name)
    evidence["phone"] = phone
    if not phone["prerequisites_met"]:
        evidence["failure_reason"] = str(phone["failure_reason"])
        return evidence
    attachment = phone["attachment"]
    assert isinstance(attachment, dict)
    switch_name = str(attachment["peer_name"])
    if switch_name != _REPRESENTATIVE_SWITCH_NAME:
        evidence["failure_reason"] = (
            f"The representative phone was attached to {switch_name!r}, not the "
            f"required attributable access scope {_REPRESENTATIVE_SWITCH_NAME!r}."
        )
        return evidence
    evidence["capture_scopes"] = {
        "phone": phone_name,
        "switch": switch_name,
        "router": _VOICE_GATEWAY_NAME,
        "control": control_name,
    }

    runtime = SimulationTraceRuntime(transport.send_and_wait)
    original = runtime.read_simulation_state()
    evidence["original_state"] = _simulation_state_dict(original)
    if not original.observed:
        # Nothing has been touched, and nothing may be: without an attributable
        # original there is no state to give back.
        evidence["failure_reason"] = (
            "The original simulation state was not attributable, so the mode was "
            "left untouched."
        )
        return evidence

    changed = False
    try:
        if not original.simulation_mode:
            evidence["mode_request"] = _simulation_mode_dict(
                runtime.set_simulation_mode(True),
            )
            changed = True
            entered = runtime.read_simulation_state()
            evidence["entered_state"] = _simulation_state_dict(entered)
            if not (entered.observed and entered.simulation_mode):
                evidence["failure_reason"] = (
                    "Simulation mode was requested and could not be verified."
                )
                return evidence
        evidence["window_before"] = _simulation_state_dict(
            runtime.read_simulation_state(),
        )
        reset = runtime.step("reset")
        evidence["reset"] = _simulation_step_dict(reset)
        if reset.observed and reset.simulation_mode:
            progression = _bounded_simulation_progression(
                runtime,
                target_sim_time_span=target_sim_time_span,
                step_batch_size=step_batch_size,
                hard_max_steps=hard_max_steps,
                hard_wall_clock_seconds=hard_wall_clock_seconds,
                global_event_list_ceiling=global_event_list_ceiling,
                stall_batch_limit=stall_batch_limit,
                monotonic=monotonic,
            )
        else:
            reset_state = runtime.read_simulation_state()
            progression = _progression_evidence(
                target_sim_time_span=target_sim_time_span,
                step_batch_size=step_batch_size,
                hard_max_steps=hard_max_steps,
                hard_wall_clock_seconds=hard_wall_clock_seconds,
                global_event_list_ceiling=global_event_list_ceiling,
                stall_batch_limit=stall_batch_limit,
            )
            reset_state_dict = _simulation_state_dict(reset_state)
            progression.update({
                "termination_reason": "STEP_FAILED",
                "start_state": reset_state_dict,
                "end_state": reset_state_dict,
                "progress": [{
                    "batch": 0,
                    "steps_requested": 0,
                    "cumulative_steps": 0,
                    "step": _simulation_step_dict(reset),
                    "state": reset_state_dict,
                }],
            })
        evidence["progression"] = progression
        evidence["reset_verification"] = progression["start_state"]
        evidence["window_after"] = _simulation_state_dict(
            runtime.read_simulation_state(),
        )
        traces = {
            "phone": runtime.read_trace(limit=TRACE_LIMIT_MAX, device=phone_name),
            "switch": runtime.read_trace(limit=TRACE_LIMIT_MAX, device=switch_name),
            "router": runtime.read_trace(
                limit=TRACE_LIMIT_MAX, device=_VOICE_GATEWAY_NAME,
            ),
            "control": runtime.read_trace(limit=TRACE_LIMIT_MAX, device=control_name),
        }
        for scope, trace in traces.items():
            evidence[f"{scope}_trace"] = _packet_trace_dict(trace)
        evidence["captured"] = all(trace.observed for trace in traces.values())
        if not evidence["captured"]:
            evidence["failure_reason"] = (
                "The bounded capture did not complete; what was observed is "
                "retained and no absence may be read from it."
            )
        # Still inside Simulation, on the SAME event list the traces came from:
        # a frame index only names a frame while that list stands. Nothing is
        # invoked here beyond the getters this repository already measured --
        # the question is which members exist, not what they return.
        evidence["frame_observer_discovery"] = _frame_observer_discovery(
            transport,
            phone_name=phone_name,
            switch_name=switch_name,
            phone_trace=evidence.get("phone_trace"),
            switch_trace=evidence.get("switch_trace"),
            single_vlan_ports=_single_vlan_access_ports(projection, switch_name),
        )
    except Exception as exc:
        # The diagnostic may never be the reason a governed stage stops running
        # its own failure and cleanup.
        evidence["failure_reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        restoration: dict[str, object] = {"changed": changed}
        try:
            if changed:
                restoration["request"] = _simulation_mode_dict(
                    runtime.set_simulation_mode(original.simulation_mode),
                )
            verified = runtime.read_simulation_state()
            restoration["verification"] = _simulation_state_dict(verified)
            evidence["restoration_verified"] = bool(
                verified.observed
                and verified.simulation_mode == original.simulation_mode
            )
        except Exception as exc:
            restoration["error"] = f"{type(exc).__name__}: {exc}"
            evidence["restoration_verified"] = False
        if not evidence["restoration_verified"] and "error" not in restoration:
            restoration["error"] = (
                "Packet Tracer simulation mode could not be verified back to the "
                "observed original state."
            )
        evidence["restoration"] = restoration
    return evidence
