"""Required CP-SCALE IOS, ping, DHCP, STP and Realtime observations."""

from __future__ import annotations
import collections
import ipaddress
import time
from dataclasses import asdict
from datetime import datetime, timezone
from ...domain.enterprise.models.configuration import (
    ConfigurationActionType,
    ConfigurationPhase,
    ConfigureAccessPort,
    VerificationKind,
)
from ...infrastructure.execution.command_dispatch import (
    DispatchClassification,
    is_command_corrupted,
)
from ...infrastructure.execution.ios_terminal import (
    ControlledIosExecutor,
    OperationalQueryId,
    PagerContinuation,
    classify_show_spanning_tree,
    ios_rejection_reason,
    parse_show_ip_dhcp_binding,
    parse_show_ip_dhcp_server_statistics,
    parse_show_ip_interface_brief,
    parse_show_interfaces_trunk,
    parse_show_spanning_tree,
)
from ...infrastructure.execution.typed_ping import (
    TypedPingExecutor,
)
from ...shared.utils import (
    same_interface_name,
    serialize_typed_ping_evidence,
)
from ...application.use_cases.observe_serial_orientation import (
    SerialOrientationObserver, inherit_verified_serial_orientation,
)
from ...application.cp_scale_live.contracts import CPScaleCoreForwardingObservation, CPScaleSiteForwardingObservation
from ...application.cp_scale_live.forwarding_stage import core_forwarding_verified, site_forwarding_verified
from ..execution.serial_orientation_runtime import PacketTracerSerialOrientationRuntime
from ..execution.simulation_trace_runtime import SimulationTraceRuntime
from ..execution.live_bridge import PacketTracerHttpTransport
from ..execution.packet_tracer_physical_runtime import PacketTracerPhysicalTopologyRuntime
from ...application.cp_scale_live.contracts import (
    CPScaleDhcpStatisticsTarget,
    CPScaleObservationRecord,
    CPScaleRealtimeState,
)
from ...application.use_cases.compose_cp_scale_canonical import CPScaleCanonicalStageProjection, CPScaleSiteForwardingCheck
from ...application.use_cases.observe_serial_orientation import SerialOrientationResult
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.physical_deployment import PhysicalWorkspaceObservation
from ...domain.models.plans import TopologyPlan


class PacketTracerCPScaleObservations:
    """A session's named observation adapters; never owns physical deployment."""

    def __init__(self, transport: PacketTracerHttpTransport, physical: PacketTracerPhysicalTopologyRuntime) -> None:
        self.physical = physical
        self.ios = ControlledIosExecutor(transport.send_and_wait)
        self.serial = SerialOrientationObserver(PacketTracerSerialOrientationRuntime(transport.send_and_wait))
        self.simulation = SimulationTraceRuntime(transport.send_and_wait)
        self.ping = TypedPingExecutor(
            transport.send_and_wait, timeout_seconds=30.0, measurement_attempts=3,
        )

    def network_state(self, projection: CPScaleCanonicalStageProjection, *, boundary: str) -> dict[str, object]:
        return _network_state_observation(self.ios, projection, boundary=boundary)

    def serial_orientation(
        self, projection: CPScaleCanonicalStageProjection, manifest: DeploymentManifest,
        verified_topology: TopologyPlan | None, verified_manifest: DeploymentManifest | None,
    ) -> SerialOrientationResult:
        if verified_topology is None:
            return self.serial.observe(projection.topology, manifest)
        return inherit_verified_serial_orientation(
            projection.topology, manifest,
            verified_topology=verified_topology, verified_manifest=verified_manifest,
        )

    def serial_interfaces(self, projection: CPScaleCanonicalStageProjection) -> tuple[bool, list[dict[str, object]]]:
        return _wait_for_serial_interfaces(self.ios, _core_serial_addresses(projection))

    def voice_window_state(self) -> CPScaleRealtimeState:
        state = self.simulation.read_simulation_state()
        return CPScaleRealtimeState(
            observed=state.observed,
            simulation_mode=state.simulation_mode,
            frames=state.frames,
            sim_time=state.sim_time,
            current_index=state.current_index,
            message=state.message,
            present=(
                "observed", "simulation_mode", "frames", "sim_time",
                "current_index", "message",
            ),
        )

    def stp(self, projection: CPScaleCanonicalStageProjection, *, edge: str) -> dict[str, object]:
        return _stp_realtime_evidence(self.ios, projection, edge=edge)

    def bindings(self, projection: CPScaleCanonicalStageProjection) -> list[dict[str, object]]:
        return _dhcp_server_binding_evidence(self.ios, projection.configuration, projection.voice)

    def dhcp_exchange(
        self, bindings: list[dict[str, object]], target: CPScaleDhcpStatisticsTarget,
        baseline: CPScaleObservationRecord,
    ) -> dict[str, object]:
        target_mapping = asdict(target)
        return _dhcp_server_statistics_delta(
            baseline.evidence, _dhcp_server_statistics_point(self.ios, target_mapping),
            voice_binding_count=_voice_binding_count(bindings, target_mapping),
        )

    def core_forwarding(self, checks: dict[str, str]) -> tuple[CPScaleCoreForwardingObservation, ...]:
        return _observe_core_forwarding(self.ping, checks)

    def site_forwarding(self, checks: tuple[CPScaleSiteForwardingCheck, ...]) -> tuple[CPScaleSiteForwardingObservation, ...]:
        return _observe_site_forwarding(self.ping, checks)

    def workspace(self) -> PhysicalWorkspaceObservation:
        return self.physical.observe_workspace()


def _core_serial_addresses(projection) -> dict[str, dict[str, str]]:
    expected: dict[str, dict[str, str]] = {}
    for action in projection.configuration.actions:
        interface = getattr(action, "interface", "")
        if not interface.casefold().startswith("serial"):
            continue
        expected.setdefault(action.device_name, {})[interface] = action.ipv4
    return expected


def _wait_for_serial_interfaces(
    ios: ControlledIosExecutor,
    expected: dict[str, dict[str, str]],
    *,
    attempts: int = 10,
    interval_seconds: float = 2.0,
) -> tuple[bool, list[dict[str, object]]]:
    evidence: list[dict[str, object]] = []
    ready = False
    for attempt in range(attempts):
        ready = True
        evidence = []
        for device_name, interfaces in sorted(expected.items()):
            result = ios.execute(
                device_name, OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
            )
            rows = {
                item.interface.casefold(): item
                for item in parse_show_ip_interface_brief(result.output)
            }
            matched = all(
                (row := rows.get(interface.casefold())) is not None
                and row.ip_address == address
                and row.status.casefold() == "up"
                and row.protocol.casefold() == "up"
                for interface, address in interfaces.items()
            )
            ready = ready and result.fresh_output_observed and matched
            evidence.append({
                "device_name": device_name,
                "fresh_output_observed": result.fresh_output_observed,
                "output_complete": result.output_complete,
                "failure_reason": result.failure_reason,
                "expected_serial_up_up": matched,
                "output": result.output,
            })
        if ready or attempt + 1 == attempts:
            break
        time.sleep(interval_seconds)
    return ready, evidence


def _observe_core_forwarding(
    ping: TypedPingExecutor, checks: dict[str, str], *,
    attempts: int = 4, interval_seconds: float = 5.0,
) -> tuple[CPScaleCoreForwardingObservation, ...]:
    observations = []
    for source, destination in checks.items():
        results = [ping.ping(source, destination)]
        for _ in range(attempts - 1):
            if core_forwarding_verified(results[-1]):
                break
            time.sleep(interval_seconds)
            results.append(ping.ping(source, destination))
        result = results[-1]
        observations.append(CPScaleCoreForwardingObservation(
            source, destination, tuple(results),
            core_forwarding_verified(result),
        ))
    return tuple(observations)


def _wait_for_core_forwarding(
    ping: TypedPingExecutor, checks: dict[str, str], *,
    attempts: int = 4, interval_seconds: float = 5.0,
) -> tuple[bool, dict[str, object]]:
    observations = _observe_core_forwarding(ping, checks, attempts=attempts, interval_seconds=interval_seconds)
    return all(item.verified for item in observations), {
        item.source_device_name: serialize_typed_ping_evidence(item.attempts[-1])
        for item in observations
    }


def _observe_site_forwarding(
    ping: TypedPingExecutor, checks, *,
    attempts: int = 4, interval_seconds: float = 5.0,
) -> tuple[CPScaleSiteForwardingObservation, ...]:
    observations = []
    for check in checks:
        results = [ping.ping(check.source_device_name, check.destination_ipv4)]
        for _ in range(attempts - 1):
            if core_forwarding_verified(results[-1]):
                break
            time.sleep(interval_seconds)
            results.append(ping.ping(check.source_device_name, check.destination_ipv4))
        result = results[-1]
        verified = site_forwarding_verified(check, result)
        observations.append(CPScaleSiteForwardingObservation(check, tuple(results), verified))
    return tuple(observations)


def _wait_for_site_forwarding(
    ping: TypedPingExecutor, checks, *,
    attempts: int = 4, interval_seconds: float = 5.0,
) -> tuple[bool, list[dict[str, object]], str]:
    """Legacy presentation preserves the last attempt and exact check identity."""
    observations = _observe_site_forwarding(ping, checks, attempts=attempts, interval_seconds=interval_seconds)
    failure = next((item.check.id for item in observations if not item.verified), "")
    return not failure, [
        {"check": asdict(item.check), "result": serialize_typed_ping_evidence(item.attempts[-1]), "verified": item.verified}
        for item in observations
    ], failure


def _dhcp_server_binding_evidence(
    ios: ControlledIosExecutor,
    configuration_plan,
    voice_plan,
) -> list[dict[str, object]]:
    """Observe server lease effects without promoting DHCP_POOL read-back."""
    pools = [
        action for action in configuration_plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
    ]
    voice_segments = {
        assignment.voice_segment_id for assignment in voice_plan.phone_assignments
    } if voice_plan is not None else set()
    pools_by_device: dict[str, list[object]] = collections.defaultdict(list)
    for pool in pools:
        pools_by_device[pool.device_name].append(pool)

    evidence: list[dict[str, object]] = []
    for device_name, device_pools in sorted(pools_by_device.items()):
        show = ios.execute(
            device_name, OperationalQueryId.SHOW_IP_DHCP_BINDING,
        )
        rows = parse_show_ip_dhcp_binding(show.output) if show.executed else []
        rejection = ios_rejection_reason(show.output)
        identity_confirmed = bool(
            show.observed_device_name == device_name
            and show.device_identity_provenance == "confirmed_unique"
        )
        # A complete table with at least one typed row proves that the parser
        # can read this build's table. With no rows at all, an unfamiliar empty
        # rendering and a genuinely empty table stay deliberately indistinct.
        table_readable = bool(
            show.executed
            and show.fresh_output_observed
            and show.output_complete
            and not rejection
            and identity_confirmed
            and rows
        )
        addresses = sorted(
            {row.ip_address for row in rows},
            key=lambda value: int(ipaddress.ip_address(value)),
        )
        pool_evidence: list[dict[str, object]] = []
        for pool in sorted(device_pools, key=lambda item: item.segment_id):
            network = ipaddress.ip_network(
                f"{pool.network}/{pool.prefix}", strict=True,
            )
            matched = [
                address for address in addresses
                if ipaddress.ip_address(address) in network
            ]
            pool_evidence.append({
                "segment_id": pool.segment_id,
                "network": str(network),
                "voice": pool.segment_id in voice_segments,
                "binding_count": len(matched) if table_readable else None,
                "bindings": matched if table_readable else [],
            })
        evidence.append({
            "device_name": device_name,
            "query_id": OperationalQueryId.SHOW_IP_DHCP_BINDING.value,
            "executed": show.executed,
            "fresh_output_observed": show.fresh_output_observed,
            "output_complete": show.output_complete,
            "truncated_by_pager": show.truncated_by_pager,
            "pager_pages_captured": show.pager_pages_captured,
            "failure_reason": show.failure_reason,
            "ios_rejection": rejection or "",
            "observed_device_name": show.observed_device_name,
            "device_identity_provenance": show.device_identity_provenance,
            "device_identity_evidence": show.device_identity_evidence,
            "device_identity_confirmed": identity_confirmed,
            "table_readable": table_readable,
            "bindings": addresses if table_readable else [],
            "pools": pool_evidence,
            "output": show.output,
        })
    return evidence


def _scoped_dhcp_subinterface(
    configuration_plan, device_name: str, segment_id: str,
) -> str:
    """Render the one subinterface a segment owns on a device, or nothing."""
    subinterfaces = [
        action for action in configuration_plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_SUBINTERFACE
        and action.device_name == device_name
        and action.segment_id == segment_id
    ]
    if len(subinterfaces) != 1:
        return ""
    return (
        f"{subinterfaces[0].parent_interface}.{subinterfaces[0].vlan_id}"
    )


def _voice_dhcp_statistics_target(
    configuration_plan,
    voice_plan,
) -> dict[str, str] | None:
    """Return one server/interface target only when voice scope is unique.

    The target carries a CONTROL scope beside the voice one, and is refused
    without it. Packet Tracer support for the interface-scoped form is UNKNOWN,
    and a build that accepted the interface token and answered with the GLOBAL
    table would be indistinguishable from a scoped answer -- while carrying the
    data clients that acquire inside this very window. A second pool-backed
    subinterface on the SAME server is what makes that difference observable.
    """
    if voice_plan is None:
        return None
    voice_segments = {
        assignment.voice_segment_id for assignment in voice_plan.phone_assignments
    }
    if len(voice_segments) != 1:
        return None
    segment_id = next(iter(voice_segments))
    pools = [
        action for action in configuration_plan.actions
        if action.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
        and action.segment_id == segment_id
    ]
    if len(pools) != 1:
        return None
    device_name = pools[0].device_name
    interface = _scoped_dhcp_subinterface(
        configuration_plan, device_name, segment_id,
    )
    if not interface:
        return None
    control_segments = sorted(
        candidate for candidate in {
            action.segment_id for action in configuration_plan.actions
            if action.action_type is ConfigurationActionType.CONFIGURE_DHCP_POOL
            and action.device_name == device_name
            and action.segment_id != segment_id
        }
        if _scoped_dhcp_subinterface(configuration_plan, device_name, candidate)
    )
    if not control_segments:
        return None
    control_segment_id = control_segments[0]
    return {
        "device_name": device_name,
        "interface": interface,
        "segment_id": segment_id,
        "control_interface": _scoped_dhcp_subinterface(
            configuration_plan, device_name, control_segment_id,
        ),
        "control_segment_id": control_segment_id,
    }


def _dhcp_server_statistics_observation(
    ios: ControlledIosExecutor,
    target: dict[str, str],
) -> dict[str, object]:
    """Read one voice-scoped cumulative counter set, preserving every gate."""
    device_name = target.get("device_name", "")
    interface = target.get("interface", "")
    show = ios.execute(
        device_name,
        OperationalQueryId.SHOW_IP_DHCP_SERVER_STATISTICS_INTERFACE,
        interface=interface,
    )
    rejection = ios_rejection_reason(show.output)
    statistics = (
        parse_show_ip_dhcp_server_statistics(show.output)
        if show.executed else None
    )
    identity_confirmed = bool(
        show.observed_device_name == device_name
        and show.device_identity_provenance == "confirmed_unique"
    )
    usable = bool(
        show.executed
        and show.fresh_output_observed
        and show.output_complete
        and not rejection
        and identity_confirmed
        and statistics is not None
    )
    counters = (
        {
            "discover_received": statistics.discover_received,
            "offer_sent": statistics.offer_sent,
            "request_received": statistics.request_received,
            "ack_sent": statistics.ack_sent,
            "nak_sent": statistics.nak_sent,
        }
        if usable and statistics is not None else None
    )
    return {
        **target,
        "query_id": (
            OperationalQueryId
            .SHOW_IP_DHCP_SERVER_STATISTICS_INTERFACE.value
        ),
        "executed": show.executed,
        "fresh_output_observed": show.fresh_output_observed,
        "output_complete": show.output_complete,
        "truncated_by_pager": show.truncated_by_pager,
        "pager_pages_captured": show.pager_pages_captured,
        "failure_reason": show.failure_reason,
        "ios_rejection": rejection or "",
        "observed_device_name": show.observed_device_name,
        "device_identity_provenance": show.device_identity_provenance,
        "device_identity_evidence": show.device_identity_evidence,
        "device_identity_confirmed": identity_confirmed,
        "usable": usable,
        "counters": counters,
        "output": show.output,
    }


def _dhcp_server_statistics_point(
    ios: ControlledIosExecutor,
    target: dict[str, str],
) -> dict[str, object]:
    """Read BOTH scopes at one point, never the voice one alone.

    The pair is what carries the scope question through to the delta. Reading
    the voice subinterface by itself cannot say whether this build answered for
    that interface or for the whole server, and the two readings are only
    comparable when they are taken at the same governed point.
    """
    return {
        "voice": _dhcp_server_statistics_observation(ios, target),
        "control": _dhcp_server_statistics_observation(ios, {
            "device_name": target.get("device_name", ""),
            "interface": target.get("control_interface", ""),
            "segment_id": target.get("control_segment_id", ""),
        }),
    }


def _scope_observation(point: object, scope: str) -> dict[str, object]:
    """One scope of a paired point. A missing scope is unusable, not zero."""
    if isinstance(point, dict) and isinstance(point.get(scope), dict):
        return point[scope]
    return {}


_DHCP_STATISTIC_COUNTERS = (
    "discover_received",
    "offer_sent",
    "request_received",
    "ack_sent",
    "nak_sent",
)


def _dhcp_counter_delta(
    baseline: dict[str, object], post: dict[str, object],
) -> tuple[dict[str, int] | None, str]:
    """Subtract two observations of ONE scope, or refuse and say why.

    Every refusal returns None. No path here turns a missing, incompatible or
    decreasing observation into a zero delta: zero is what two real captures of
    the same scope produced, and nothing else may render it.
    """
    for field in ("device_name", "interface", "segment_id"):
        if baseline.get(field) != post.get(field):
            return None, "baseline and post observation target different scopes"
    if not baseline.get("usable") or not post.get("usable"):
        return None, "baseline or post observation was not usable"
    before, after = baseline.get("counters"), post.get("counters")
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None, "counters were not typed"
    if any(
        type(before.get(field)) is not int or type(after.get(field)) is not int
        for field in _DHCP_STATISTIC_COUNTERS
    ):
        return None, "counters were incomplete"
    delta = {
        field: int(after[field]) - int(before[field])
        for field in _DHCP_STATISTIC_COUNTERS
    }
    if any(value < 0 for value in delta.values()):
        # A cumulative counter that went down did not observe negative DHCP.
        # These two captures stopped being two points of one series.
        return None, "counters reset or wrapped inside the acquisition window"
    return delta, ""


def _dhcp_server_statistics_delta(
    baseline: dict[str, object],
    post: dict[str, object],
    *,
    voice_binding_count: int | None,
) -> dict[str, object]:
    """Classify one attributable voice-interface DORA counter delta.

    The classification is only reached once the interface argument is OBSERVED
    to scope. Packet Tracer support for the scoped form stays UNKNOWN until a
    live run says otherwise, and a build that answered every interface with the
    global table would hand this function the data clients that acquire inside
    the same window -- as if the voice subinterface had seen them.
    """
    evidence: dict[str, object] = {
        "baseline": baseline,
        "post": post,
        "voice_binding_count": voice_binding_count,
        "delta_readable": False,
        "counters": None,
        "control_counters": None,
        "scope_discriminated": False,
        "fork": "UNOBSERVABLE",
        "failure_reason": "",
    }
    delta, reason = _dhcp_counter_delta(
        _scope_observation(baseline, "voice"), _scope_observation(post, "voice"),
    )
    if delta is None:
        evidence["failure_reason"] = f"Voice-scoped DHCP statistics {reason}."
        return evidence
    control, control_reason = _dhcp_counter_delta(
        _scope_observation(baseline, "control"),
        _scope_observation(post, "control"),
    )
    if control is None:
        evidence["failure_reason"] = (
            f"The DHCP statistics control scope {control_reason}, so this "
            "build was never observed to scope the read to one interface."
        )
        return evidence
    evidence["control_counters"] = control
    # Two different subinterfaces that reported the SAME counters were not two
    # scopes. That is only harmless when the control scope observed nothing at
    # all: a global table could not have read zero across this window, and a
    # server with no traffic has nothing to confound the voice counters with.
    evidence["scope_discriminated"] = control != delta or not any(control.values())
    if not evidence["scope_discriminated"]:
        evidence["fork"] = "SCOPE_UNPROVEN"
        evidence["failure_reason"] = (
            "The voice and control subinterfaces reported identical non-zero "
            "counters, so the interface argument did not scope this read and "
            "the delta cannot be attributed to the voice exchange."
        )
        return evidence

    discover = delta["discover_received"]
    offer = delta["offer_sent"]
    request = delta["request_received"]
    ack = delta["ack_sent"]
    nak = delta["nak_sent"]
    if discover == 0:
        fork = (
            "A_NO_DISCOVER"
            if offer == request == ack == nak == 0
            else "UNCLASSIFIED_COUNTER_PATTERN"
        )
    elif offer == 0:
        fork = (
            "B_DISCOVER_WITHOUT_OFFER"
            if request == ack == nak == 0
            else "UNCLASSIFIED_COUNTER_PATTERN"
        )
    elif request == 0:
        fork = (
            "C_OFFER_WITHOUT_REQUEST"
            if ack == nak == 0
            else "UNCLASSIFIED_COUNTER_PATTERN"
        )
    elif ack == 0:
        fork = "D_REQUEST_WITHOUT_ACK"
    elif voice_binding_count is None:
        fork = "ACK_OBSERVED_BINDING_UNOBSERVABLE"
    elif voice_binding_count == 0:
        fork = "E_ACK_WITHOUT_BINDING"
    else:
        fork = "SERVER_EXCHANGE_AND_BINDING_OBSERVED"
    evidence.update({
        "delta_readable": True,
        "counters": delta,
        "fork": fork,
    })
    return evidence


def _voice_binding_count(
    binding_evidence: list[dict[str, object]],
    target: dict[str, str],
) -> int | None:
    matches = [
        pool.get("binding_count")
        for device in binding_evidence
        if device.get("device_name") == target.get("device_name")
        for pool in (
            device.get("pools")
            if isinstance(device.get("pools"), list) else []
        )
        if isinstance(pool, dict)
        and pool.get("segment_id") == target.get("segment_id")
        and pool.get("voice") is True
    ]
    return matches[0] if len(matches) == 1 and type(matches[0]) is int else None


# ----------------------------------------------------------------------
# POST_FAILURE_SIMULATION_DIAGNOSTIC
#
# Simulation mode changes EXECUTION SEMANTICS: packets stop progressing on
# their own and have to be stepped. That is why this runs only after the voice
# stage has already failed and been read back -- entering Simulation during the
# realtime acquisition window would not observe the tested condition, it would
# replace it.
#
# This slice classifies NOTHING. CP-SCALE does not yet know how this build
# represents DHCP, and a label invented here would be indistinguishable from an
# observation later. The product is the raw capture.
# ----------------------------------------------------------------------

#: Simulation time is the primary diagnostic bound.  The remaining ceilings
#: are independent fail-safes, not alternate ways to infer a negative result.
def _simulation_state_dict(state) -> dict[str, object]:
    return {
        "observed": state.observed,
        "simulation_mode": state.simulation_mode,
        "frames": state.frames,
        "sim_time": state.sim_time,
        "current_index": state.current_index,
        "message": state.message,
    }


def _simulation_mode_dict(mode) -> dict[str, object]:
    return {
        "observed": mode.observed, "before": mode.before, "after": mode.after,
        "frames": mode.frames, "message": mode.message,
    }


def _simulation_step_dict(step) -> dict[str, object]:
    return {
        "observed": step.observed,
        "simulation_mode": step.simulation_mode,
        "frames_before": step.frames_before,
        "frames_after": step.frames_after,
        "sim_time": step.sim_time,
        "current_index": step.current_index,
        "message": step.message,
    }


def _voice_window_state(runtime) -> dict[str, object]:
    """One PURE boundary observation of the authoritative window."""
    return _simulation_state_dict(runtime.read_simulation_state())


#: Los dos únicos estados que la decisión distingue, exactamente como IOS los
#: imprime en la columna `Sts`. Cualquier otro estado REAL se conserva como
#: OTHER_OBSERVED con su token intacto: leer un `LRN` como FORWARDING o como
#: BLOCKING inventaría justo la mitad del experimento que falta medir.
_STP_FORWARDING_STATE = "fwd"
_STP_BLOCKING_STATE = "blk"


def _phone_edge_port_derivation(projection):
    """Los puertos con teléfono de esta etapa, y lo que quedó fuera de serlos.

    E7 ata cada teléfono a la acción de acceso tipada que lo sostiene, así que
    el conjunto SALE del plan: nombrar `Fa0/1-21` acá convertiría la evidencia
    en su propia hipótesis. Una asignación cuya acción no es un puerto de
    acceso tipado -- un trunk, o una acción que ya no existe -- no es un puerto
    de borde, y se registra como excluida en vez de desaparecer en silencio.
    """
    plan = getattr(projection, "voice", None)
    assignments = list(getattr(plan, "phone_assignments", []) or [])
    if not assignments:
        return [], []
    configuration = getattr(projection, "configuration", None)
    access_by_id = {
        action.id: action
        for action in getattr(configuration, "actions", []) or []
        if isinstance(action, ConfigureAccessPort)
    }
    ports: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for assignment in assignments:
        action_id = getattr(assignment, "access_configuration_action_id", None)
        if not isinstance(action_id, str):
            # Recolectar evidencia NUNCA puede ser el motivo por el que una
            # etapa gobernada se cae. Una asignación que no es del tipo del
            # plan no aporta un puerto y se dice, no revienta.
            excluded.append({
                "access_configuration_action_id": "",
                "reason": "NOT_A_TYPED_PHONE_ASSIGNMENT",
            })
            continue
        access = access_by_id.get(action_id)
        if access is None:
            excluded.append({
                "access_configuration_action_id": action_id,
                "reason": "NOT_A_TYPED_ACCESS_PORT",
            })
            continue
        key = (access.device_name, access.interface)
        if key in seen:
            continue
        seen.add(key)
        ports.append({
            "device_name": access.device_name,
            "interface": access.interface,
            "vlan_id": assignment.voice_vlan_id,
            "access_configuration_action_id": action_id,
        })
    ports.sort(key=lambda item: (item["device_name"], item["interface"]))
    excluded.sort(key=lambda item: item["access_configuration_action_id"])
    return ports, excluded


def _phone_edge_ports(projection) -> list[dict[str, object]]:
    """Cada puerto de acceso con teléfono que esta etapa realmente configuró."""
    return _phone_edge_port_derivation(projection)[0]


def _stp_source_error(show, rejection: str) -> str:
    """Por qué esta lectura no puede sostener NINGUNA afirmación de estado.

    El orden importa: una captura cortada por el pager también viene
    incompleta, y decir sólo `OUTPUT_INCOMPLETE` perdería exactamente el hecho
    que decide si esta consulta necesita cualificación.
    """
    if not show.executed:
        return "QUERY_NOT_EXECUTED"
    if not show.fresh_output_observed:
        return "OUTPUT_NOT_FRESH"
    if rejection:
        return "IOS_REJECTED"
    if show.truncated_by_pager:
        return "PAGER_TRUNCATED"
    if not show.output_complete:
        return "OUTPUT_INCOMPLETE"
    if (
        show.observed_device_name != show.device_name
        or show.device_identity_provenance != "confirmed_unique"
    ):
        return "DEVICE_IDENTITY_NOT_CONFIRMED"
    return ""


def _stp_port_observation(port, instances, source_error: str) -> dict[str, object]:
    """Un puerto, su estado tal como PT lo imprimió, o por qué no se sabe."""
    observation: dict[str, object] = {
        "device_name": port["device_name"],
        "interface": port["interface"],
        "vlan_id": port["vlan_id"],
        "protocol": "",
        "role": "",
        "state": "",
        "cost": None,
        "priority_number": "",
        "link_type": "",
        "classification": "UNOBSERVABLE",
        "failure_reason": source_error,
    }
    if source_error:
        return observation
    instance = next(
        (item for item in instances if item.vlan_id == port["vlan_id"]), None,
    )
    if instance is None:
        # Una instancia ausente NO es un puerto bloqueado. Es una tabla que no
        # dice nada sobre esta VLAN.
        observation["failure_reason"] = "VLAN_INSTANCE_ABSENT"
        return observation
    observation["protocol"] = instance.protocol
    row = next(
        (
            item for item in instance.interfaces
            if same_interface_name(item.interface, str(port["interface"]))
        ),
        None,
    )
    if row is None:
        observation["failure_reason"] = "INTERFACE_ROW_ABSENT"
        return observation
    state = (row.state or "").strip()
    observation.update({
        "role": row.role,
        "state": state,
        "cost": row.cost,
        "priority_number": row.priority_number,
        "link_type": row.link_type,
    })
    if not state:
        observation["failure_reason"] = "MALFORMED_PORT_STATE"
        return observation
    folded = state.casefold()
    observation["classification"] = (
        "FORWARDING" if folded == _STP_FORWARDING_STATE
        else "BLOCKING" if folded == _STP_BLOCKING_STATE
        else "OTHER_OBSERVED"
    )
    observation["failure_reason"] = ""
    return observation


#: Una observacion logica puede ejecutar como mucho dos consultas registradas.
#: No es un lazo hasta el exito: el segundo intento existe solo para UN fallo
#: transitorio de continuacion de pager, y no hay tercero.
_STP_MAX_LOGICAL_ATTEMPTS = 2


def _stp_attempt(show, device_name: str, index: int) -> dict[str, object]:
    """La calidad cruda de UNA ejecucion registrada, sin interpretarla."""
    rejection = ios_rejection_reason(show.output) or ""
    instances = parse_show_spanning_tree(show.output) if show.executed else []
    return {
        "attempt": index,
        "executed": show.executed,
        "fresh_output_observed": show.fresh_output_observed,
        "output_complete": show.output_complete,
        "truncated_by_pager": show.truncated_by_pager,
        "pager_pages_captured": show.pager_pages_captured,
        "pager_continuation": show.pager_continuation,
        "dispatch_classification": show.dispatch_classification,
        "failure_reason": show.failure_reason,
        "observed_device_name": show.observed_device_name,
        "device_identity_provenance": show.device_identity_provenance,
        "device_identity_confirmed": bool(
            show.observed_device_name == device_name
            and show.device_identity_provenance == "confirmed_unique"
        ),
        "ios_rejection": rejection,
        "classification": classify_show_spanning_tree(
            show.output, executed=show.executed,
        ).value,
        "source_error": _stp_source_error(show, rejection),
        "vlan_instances": sorted(item.vlan_id for item in instances),
        "output": show.output,
    }


def _stp_retry_refusal(show, device_name: str) -> str:
    """Vacio solo si ESTE resultado prueba que otra consulta fresca es segura.

    El discriminador es `executed`. Tras una captura cualificada incompleta el
    ejecutor cancela el pager, y el unico camino que llega a `executed=True` es
    el de una cancelacion CONFIRMADA: si no pudo confirmarla, pone el device en
    cuarentena y devuelve `executed=False`. Un resultado ejecutado, con la
    identidad del comando intacta y el device atribuido de forma unica, es
    entonces la prueba de que el terminal volvio a un prompt.

    Todo lo demas se niega. No se debilita nada del ejecutor para permitir el
    reintento: si el terminal sigue mal, su propia guarda atomica rechazara el
    despacho y el segundo intento sera otro `executed=False`, nunca una lectura
    mal atribuida.
    """
    if not show.executed:
        return "TERMINAL_NOT_CONFIRMED_SAFE"
    try:
        dispatch = DispatchClassification(show.dispatch_classification)
    except ValueError:
        # Una clasificacion que no es del enum no prueba que el comando llego
        # intacto, y no probarlo basta para no reintentar.
        return "DISPATCH_CORRUPTED"
    if is_command_corrupted(dispatch):
        return "DISPATCH_CORRUPTED"
    if (
        show.observed_device_name != device_name
        or show.device_identity_provenance != "confirmed_unique"
    ):
        return "DEVICE_IDENTITY_NOT_CONFIRMED"
    if ios_rejection_reason(show.output):
        return "IOS_REJECTED"
    if (
        show.pager_continuation != PagerContinuation.FAILED.value
        or not show.truncated_by_pager
        or show.output_complete
    ):
        # `not_qualified` es una politica, no un fallo transitorio: repetir la
        # consulta daria exactamente la misma primera pagina.
        return "NOT_A_QUALIFIED_PAGER_FAILURE"
    return ""


def _stp_logical_observation(ios, device_name: str):
    """UNA observacion logica del arbol de expansion: dos ejecuciones a lo sumo.

    Dos comandos son dos observaciones, no una tabla reconstruida: las paginas
    y las instancias parseadas nunca se mezclan entre ejecuciones. Se selecciona
    el PRIMER intento completo, fresco y atribuido de forma unica, y es el unico
    del que sale el estado afirmado; el intento fallido se conserva entero como
    su propia evidencia.
    """
    attempts: list[dict[str, object]] = []
    retry_eligible = False
    retry_reason = ""
    for index in range(1, _STP_MAX_LOGICAL_ATTEMPTS + 1):
        show = ios.execute(device_name, OperationalQueryId.SHOW_SPANNING_TREE)
        attempt = _stp_attempt(show, device_name, index)
        attempts.append(attempt)
        if not attempt["source_error"]:
            break
        if index == _STP_MAX_LOGICAL_ATTEMPTS:
            break
        refusal = _stp_retry_refusal(show, device_name)
        if refusal:
            retry_reason = refusal
            break
        retry_eligible = True
        retry_reason = "QUALIFIED_PAGER_CONTINUATION_FAILED"

    selected = next(
        (item for item in attempts if not item["source_error"]), None,
    )
    final = selected if selected is not None else attempts[-1]
    instances = (
        parse_show_spanning_tree(str(final["output"]))
        if selected is not None else []
    )
    device = {key: value for key, value in final.items() if key != "attempt"}
    device.update({
        "device_name": device_name,
        "query_id": OperationalQueryId.SHOW_SPANNING_TREE.value,
        "max_logical_attempts": _STP_MAX_LOGICAL_ATTEMPTS,
        "attempts": attempts,
        "selected_attempt": final["attempt"] if selected is not None else None,
        "retry_eligible": retry_eligible,
        "retry_reason": retry_reason,
    })
    return device, instances


def _stp_realtime_evidence(ios, projection, *, edge: str) -> dict[str, object]:
    """El estado de borde de los puertos con teléfono, medido en Realtime.

    Es la única lectura que puede decir qué hacía el puerto DURANTE la ventana
    autoritativa de voz. Es de sólo lectura y falla cerrada: FORWARDING y
    BLOCKING se afirman sólo desde una fila fresca, completa y atribuida; todo
    lo demás queda UNOBSERVABLE, que no es lo mismo que ausencia.
    """
    ports, excluded = _phone_edge_port_derivation(projection)
    by_device: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
    for port in ports:
        by_device[str(port["device_name"])].append(port)

    devices: list[dict[str, object]] = []
    observations: list[dict[str, object]] = []
    for device_name, device_ports in sorted(by_device.items()):
        device, instances = _stp_logical_observation(ios, device_name)
        devices.append(device)
        source_error = str(device["source_error"])
        for port in device_ports:
            observations.append(
                _stp_port_observation(port, instances, source_error),
            )

    counts = {
        state: sum(
            1 for item in observations if item["classification"] == state
        )
        for state in ("FORWARDING", "BLOCKING", "OTHER_OBSERVED", "UNOBSERVABLE")
    }
    return {
        "edge": edge,
        "window": "NORMAL_WINDOW",
        "mode_required": "realtime",
        "proves": (
            "The phone-facing edge state PT printed at this boundary of the "
            "authoritative window. It does NOT prove the state held for the "
            "whole window, and it is never derived from DHCP behaviour."
        ),
        "phone_ports_total": len(ports),
        "devices": devices,
        "excluded": excluded,
        "ports": observations,
        "counts": counts,
    }


def _network_trunk_expectations(projection, device_name: str = "") -> list:
    expectations = [
        item for item in projection.configuration.verification_expectations
        if item.kind is VerificationKind.TRUNK
        and (not device_name or item.device_name == device_name)
    ]
    return sorted(
        expectations,
        key=lambda item: (
            item.device_name,
            str(item.expected.get("interface") or ""),
            item.id,
        ),
    )


def _stp_network_device_evidence(
    ios,
    projection,
    device_name: str,
) -> dict[str, object]:
    """Correlate one trunk transition with fresh roots and port states."""

    expectations = _network_trunk_expectations(projection, device_name)
    device, instances = _stp_logical_observation(ios, device_name)
    source_error = str(device["source_error"])
    vlan_ids = sorted({
        int(vlan)
        for item in expectations
        for vlan in item.expected.get("allowed_vlans", [])
    })
    interfaces = sorted({
        str(item.expected.get("interface") or "")
        for item in expectations
    })
    by_vlan = {item.vlan_id: item for item in instances}
    observed_instances: list[dict[str, object]] = []
    for vlan_id in vlan_ids:
        instance = by_vlan.get(vlan_id)
        if source_error or instance is None:
            observed_instances.append({
                "vlan_id": vlan_id,
                "authoritative": False,
                "failure_reason": (
                    source_error or "VLAN_INSTANCE_ABSENT"
                ),
                "root": None,
                "ports": [],
            })
            continue
        ports = []
        for interface in interfaces:
            row = next((
                item for item in instance.interfaces
                if same_interface_name(item.interface, interface)
            ), None)
            ports.append({
                "interface": interface,
                "row_present": row is not None,
                "observed_interface": row.interface if row is not None else "",
                "role": row.role if row is not None else "",
                "state": row.state if row is not None else "",
                "cost": row.cost if row is not None else None,
                "priority_number": (
                    row.priority_number if row is not None else ""
                ),
                "link_type": row.link_type if row is not None else "",
                "failure_reason": (
                    "" if row is not None else "INTERFACE_ROW_ABSENT"
                ),
            })
        observed_instances.append({
            "vlan_id": vlan_id,
            "authoritative": True,
            "failure_reason": "",
            "forward_delay_seconds": instance.forward_delay_seconds,
            "root": {
                "protocol": instance.protocol,
                "priority": instance.root_priority,
                "address": instance.root_address,
                "is_local": instance.root_is_local,
                "cost": instance.root_cost,
                "port": instance.root_port,
                "bridge_priority": instance.bridge_priority,
                "bridge_base_priority": instance.bridge_base_priority,
                "bridge_address": instance.bridge_address,
            },
            "ports": ports,
        })
    return {
        "device_name": device_name,
        "authoritative": not source_error,
        "failure_reason": source_error,
        "query": device,
        "instances": observed_instances,
    }


def _network_state_observation(
    ios,
    projection,
    *,
    boundary: str,
) -> dict[str, object]:
    """Read cumulative trunk and PVST state at one causal boundary."""

    expectations = _network_trunk_expectations(projection)
    grouped: dict[str, list] = collections.defaultdict(list)
    for expectation in expectations:
        grouped[expectation.device_name].append(expectation)

    devices: list[dict[str, object]] = []
    for device_name, device_expectations in sorted(grouped.items()):
        try:
            show = ios.execute(
                device_name,
                OperationalQueryId.SHOW_INTERFACES_TRUNK,
            )
            rejection = ios_rejection_reason(show.output) or ""
            authoritative = bool(
                show.executed
                and show.fresh_output_observed
                and show.output_complete
                and show.observed_device_name == device_name
                and show.device_identity_provenance == "confirmed_unique"
                and not rejection
            )
            rows = (
                parse_show_interfaces_trunk(show.output)
                if show.executed else []
            )
            trunks = []
            for expectation in device_expectations:
                interface = str(
                    expectation.expected.get("interface") or ""
                )
                row = next((
                    item for item in rows
                    if same_interface_name(item.interface, interface)
                ), None)
                trunks.append({
                    "expectation_id": expectation.id,
                    "interface": interface,
                    "expected_vlans": sorted({
                        int(vlan)
                        for vlan in expectation.expected.get(
                            "allowed_vlans", []
                        )
                    }),
                    "authoritative": authoritative,
                    "row_present": row is not None,
                    "observed_interface": (
                        row.interface if row is not None else ""
                    ),
                    "status": row.status if row is not None else "",
                    "native_vlan": (
                        row.native_vlan if row is not None else None
                    ),
                    "allowed_vlans": (
                        list(row.allowed_vlans)
                        if row is not None
                        and row.allowed_vlans is not None else None
                    ),
                    "active_vlans": (
                        list(row.active_vlans)
                        if row is not None
                        and row.active_vlans is not None else None
                    ),
                    "forwarding_vlans": (
                        list(row.forwarding_vlans)
                        if row is not None
                        and row.forwarding_vlans is not None else None
                    ),
                    "failure_reason": (
                        rejection
                        or show.failure_reason
                        or (
                            "" if row is not None
                            else "NO_MATCHING_ROW"
                        )
                    ),
                })
            stp = _stp_network_device_evidence(
                ios,
                projection,
                device_name,
            )
            devices.append({
                "device_name": device_name,
                "trunk_query": {
                    "executed": show.executed,
                    "fresh_output_observed": (
                        show.fresh_output_observed
                    ),
                    "output_complete": show.output_complete,
                    "observed_device_name": show.observed_device_name,
                    "device_identity_provenance": (
                        show.device_identity_provenance
                    ),
                    "ios_rejection": rejection,
                    "failure_reason": show.failure_reason,
                    "output": show.output,
                },
                "trunks": trunks,
                "stp": stp,
            })
        except Exception as exc:
            devices.append({
                "device_name": device_name,
                "trunks": [],
                "stp": None,
                "failure_reason": f"{type(exc).__name__}: {exc}",
            })
    return {
        "boundary": boundary,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
        "trunk_expectation_count": len(expectations),
        "device_count": len(grouped),
        "devices": devices,
    }


#: El texto EXACTO con el que PT identifica cada frame que hay que comparar. Un
#: frame se elige por lo que Packet Tracer dijo de el, jamas por su clase cruda
#: de trafico: ningun numero de clase nombra un protocolo en este repositorio, y
#: seguir tratandolos como sinonimos seria el clasificador que no existe.
