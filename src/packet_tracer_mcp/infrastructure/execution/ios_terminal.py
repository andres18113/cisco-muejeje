"""Consultas IOS registradas y lectura operacional sobre TerminalLine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from time import monotonic, sleep
from collections.abc import Callable
from typing import Never

from ...domain.enterprise.models.discovery import DeviceInitializationResult
from .command_dispatch import (
    PAGER_GUARD_JS as _PAGER_GUARD_JS,
    DispatchClassification,
    classify_echo,
    drop_pager_prompt,
    fresh_command_window,
    has_active_pager,
    is_command_corrupted,
    terminal_is_idle,
)
from .device_lifecycle import IosBootWaiter, StateConvergenceWaiter


class OperationalQueryId(str, Enum):
    SHOW_IP_INTERFACE_BRIEF = "show_ip_interface_brief"
    SHOW_INTERFACES_TRUNK = "show_interfaces_trunk"
    SHOW_EPHONE = "show_ephone"
    SHOW_ACCESS_LISTS = "show_access_lists"
    SHOW_IP_INTERFACE = "show_ip_interface"
    SHOW_CONTROLLERS_SERIAL = "show_controllers_serial"
    SHOW_INTERFACE = "show_interface"
    SHOW_IP_NAT_TRANSLATIONS = "show_ip_nat_translations"
    SHOW_IP_NAT_STATISTICS = "show_ip_nat_statistics"
    SHOW_PORT_SECURITY_INTERFACE = "show_port_security_interface"
    SHOW_IP_DHCP_SNOOPING = "show_ip_dhcp_snooping"
    SHOW_IP_ARP_INSPECTION = "show_ip_arp_inspection"
    SHOW_SPANNING_TREE = "show_spanning_tree"
    SHOW_ETHERCHANNEL_SUMMARY = "show_etherchannel_summary"
    SHOW_IP_OSPF_NEIGHBOR = "show_ip_ospf_neighbor"
    SHOW_IP_ROUTE_OSPF = "show_ip_route_ospf"
    SHOW_IP_EIGRP_NEIGHBORS = "show_ip_eigrp_neighbors"
    SHOW_IP_ROUTE_EIGRP = "show_ip_route_eigrp"
    SHOW_IP_PROTOCOLS = "show_ip_protocols"
    SHOW_IP_ROUTE_RIP = "show_ip_route_rip"
    SHOW_INTERFACES_SWITCHPORT = "show_interfaces_switchport"
    SHOW_TELEPHONY_SERVICE = "show_telephony_service"


class TrunkQueryClassification(str, Enum):
    SUPPORTED_WITH_ROWS = "supported_with_rows"
    SUPPORTED_EMPTY = "supported_empty"
    INVALID_COMMAND = "invalid_command"
    UNIMPLEMENTED = "unimplemented"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class StpQueryClassification(str, Enum):
    SUPPORTED_WITH_INSTANCES = "supported_with_instances"
    SUPPORTED_EMPTY = "supported_empty"
    INVALID_COMMAND = "invalid_command"
    UNIMPLEMENTED = "unimplemented"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class EtherChannelQueryClassification(str, Enum):
    SUPPORTED_WITH_GROUPS = "supported_with_groups"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class OspfQueryClassification(str, Enum):
    SUPPORTED_WITH_ROWS = "supported_with_rows"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class EigrpQueryClassification(str, Enum):
    SUPPORTED_EMPTY = "supported_empty"
    PROCESS_MISMATCH = "process_mismatch"
    QUERY_TIMEOUT = "query_timeout"
    PARSER_UNAVAILABLE = "parser_unavailable"


class PagerContinuation(str, Enum):
    """Que le paso al pager durante UNA lectura registrada, no a la consulta."""

    # No hubo pager: la salida entro en una sola pagina.
    NOT_ENCOUNTERED = "not_encountered"
    # Hubo pager y esta consulta registrada no tiene continuacion cualificada.
    # Es el comportamiento por defecto y significa truncado.
    NOT_QUALIFIED = "not_qualified"
    # Hubo pager, se recorrio completo y la lectura cerro en un prompt.
    COMPLETED = "completed"
    # Se intento la continuacion cualificada y una cota la corto. Truncado.
    FAILED = "failed"


class DeviceIdentityProvenance(str, Enum):
    """Quien produjo la salida, separado de a quien se le pidio.

    `NOT_OBSERVED` es el default y no afirma nada. `AMBIGUOUS` es distinto de
    no observar: mas de un device del runtime pudo haber producido la misma
    evidencia, asi que atribuirla a uno seria elegir. `MISMATCHED` es el caso
    que esta clasificacion existe para no dejar pasar -- la sesion que ejecuto
    pertenece a OTRO device, y entonces ninguna consulta puede certificar al
    pedido.
    """

    NOT_OBSERVED = "not_observed"
    CONFIRMED_UNIQUE = "confirmed_unique"
    AMBIGUOUS = "ambiguous"
    MISMATCHED = "mismatched"


class DeviceIdentityEvidence(str, Enum):
    """Por que via se atribuyo la sesion. Ninguna de las dos usa el nombre pedido.

    `TERMINAL_OBJECT_IDENTITY` compara el objeto terminal al que se despacho
    contra el que devuelve la enumeracion de la red. `SESSION_TRANSCRIPT_CONTINUITY`
    ata la sesion por su transcripcion: la linea que ejecuto es la unica cuya
    salida continua exactamente la linea base capturada al despachar.
    """

    NONE = "none"
    TERMINAL_OBJECT_IDENTITY = "terminal_object_identity"
    SESSION_TRANSCRIPT_CONTINUITY = "session_transcript_continuity"


class IosSessionState(str, Enum):
    WAITING_FOR_BOOT = "waiting_for_boot"
    BOOT_COMPLETE = "boot_complete"
    SETUP_DIALOG = "setup_dialog"
    SETUP_RESPONSE_SENT = "setup_response_sent"
    PRESS_RETURN = "press_return"
    RETURN_SENT = "return_sent"
    EXEC_PROMPT_READY = "exec_prompt_ready"
    TIMEOUT = "timeout"
    FAILED = "failed"


_COMMANDS = {
    OperationalQueryId.SHOW_IP_INTERFACE_BRIEF: "show ip interface brief",
    OperationalQueryId.SHOW_INTERFACES_TRUNK: "show interfaces trunk",
    OperationalQueryId.SHOW_EPHONE: "show ephone",
    OperationalQueryId.SHOW_ACCESS_LISTS: "show access-lists",
    OperationalQueryId.SHOW_IP_NAT_TRANSLATIONS: "show ip nat translations",
    OperationalQueryId.SHOW_IP_NAT_STATISTICS: "show ip nat statistics",
    OperationalQueryId.SHOW_IP_DHCP_SNOOPING: "show ip dhcp snooping",
    OperationalQueryId.SHOW_IP_ARP_INSPECTION: "show ip arp inspection",
    OperationalQueryId.SHOW_SPANNING_TREE: "show spanning-tree",
    OperationalQueryId.SHOW_ETHERCHANNEL_SUMMARY: "show etherchannel summary",
    OperationalQueryId.SHOW_IP_OSPF_NEIGHBOR: "show ip ospf neighbor",
    OperationalQueryId.SHOW_IP_ROUTE_OSPF: "show ip route ospf",
    OperationalQueryId.SHOW_IP_EIGRP_NEIGHBORS: "show ip eigrp neighbors",
    OperationalQueryId.SHOW_IP_ROUTE_EIGRP: "show ip route eigrp",
    # Observado en EXEC de usuario durante R2-0; no requiere `enable`.
    OperationalQueryId.SHOW_IP_PROTOCOLS: "show ip protocols",
    OperationalQueryId.SHOW_IP_ROUTE_RIP: "show ip route rip",
    OperationalQueryId.SHOW_TELEPHONY_SERVICE: "show telephony-service",
}
_INTERFACE_COMMANDS = {
    OperationalQueryId.SHOW_IP_INTERFACE: "show ip interface {interface}",
    # DCE/DTE y reloj sólo son observables por el controlador de la serial.
    OperationalQueryId.SHOW_CONTROLLERS_SERIAL: "show controllers {interface}",
    OperationalQueryId.SHOW_INTERFACE: "show interfaces {interface}",
    OperationalQueryId.SHOW_PORT_SECURITY_INTERFACE:
        "show port-security interface {interface}",
    # Acotada a UNA interfaz a proposito: el modo switchport y la VLAN de
    # acceso son propiedades del puerto, y la forma global de esta consulta
    # pagina en cuanto el switch tiene mas de un punado de puertos.
    OperationalQueryId.SHOW_INTERFACES_SWITCHPORT:
        "show interfaces {interface} switchport",
}
_PRIVILEGED_QUERIES = {
    OperationalQueryId.SHOW_EPHONE,
    OperationalQueryId.SHOW_ACCESS_LISTS,
    OperationalQueryId.SHOW_IP_INTERFACE,
    OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
    OperationalQueryId.SHOW_IP_NAT_TRANSLATIONS,
    OperationalQueryId.SHOW_IP_NAT_STATISTICS,
    OperationalQueryId.SHOW_PORT_SECURITY_INTERFACE,
    OperationalQueryId.SHOW_IP_DHCP_SNOOPING,
    OperationalQueryId.SHOW_IP_ARP_INSPECTION,
    OperationalQueryId.SHOW_INTERFACES_SWITCHPORT,
    OperationalQueryId.SHOW_TELEPHONY_SERVICE,
}
_INTERFACE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9./:-]{0,79}$")
_SETUP_DIALOG = "would you like to enter the initial configuration dialog"
_PAGER_MARKER = "--More--"

# Consultas registradas cuya continuacion de pager esta CUALIFICADA.
#
# El default de toda consulta registrada sigue siendo el de siempre: pager
# encontrado -> truncada -> se aplica el techo de la afirmacion. Cualificar es
# un acto explicito por consulta, con su propia evidencia, y entra aca; no es
# una propiedad de "haber encontrado un pager".
#
# `SHOW_CONTROLLERS_SERIAL` entra por TD-ORIENTATION-PAGER-001: en PT 9.0.1.0858
# `show controllers Serial0/0/0` sobre un 2911 con HWIC-2T excede una pagina
# SIEMPRE, la consulta ya esta acotada a una interfaz y no hay forma de
# angostarla mas, y ese build rechaza `terminal length 0`. Sin recorrer el
# pager la orientacion DCE/DTE es inobservable.
#
# Que exista el primitivo NO promueve ninguna otra consulta. En particular
# `SHOW_IP_PROTOCOLS` sigue sin cualificar y su techo de TD-RUNTIME-003 -- un
# device con RIP junto a otro protocolo es UNOBSERVABLE por esta lectura --
# queda exactamente donde estaba.
_PAGINATION_QUALIFIED_QUERIES = frozenset({
    OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
})

# Cotas duras de UNA captura logica. Existen para que no haya forma de que la
# continuacion se vuelva infinita, ni de que una sesion larga se cuele como si
# fuera la salida del comando actual.
_PAGER_MAX_PAGES = 12
_PAGER_MAX_BYTES = 65536
_PAGER_CAPTURE_DEADLINE_SECONDS = 25.0
_PAGER_PAGE_TIMEOUT_SECONDS = 8.0
# La unica tecla que el `--More--` consume para avanzar. No es un comando: el
# pager se la come antes de que llegue al CLI, que es exactamente la mecanica
# que este repositorio ya midio cuando un despacho perdia su primer caracter
# (`DispatchClassification.PREFIX_LOSS`).
_PAGER_CONTINUATION_KEY = "String.fromCharCode(32)"


@dataclass(frozen=True)
class IosCommandResult:
    device_name: str
    query_id: OperationalQueryId
    executed: bool
    output: str = ""
    failure_reason: str = ""
    duration_ms: int = 0
    session_state: IosSessionState = IosSessionState.FAILED
    fresh_output_observed: bool = False
    window_strategy: str = "none"
    truncated_by_pager: bool = False
    # COMPLETA es una dimension propia, separada de EJECUTADA y de FRESCA. Para
    # una sola pagina significa lo mismo que ya significaba en todo consumidor
    # actual: la ventana del comando no traia marcador de pager. Para una
    # lectura paginada significa algo mas fuerte -- se recorrio el pager entero
    # y la salida cerro en un prompt. Por defecto False: incompleta.
    output_complete: bool = False
    pager_pages_captured: int = 1
    pager_continuation: str = PagerContinuation.NOT_ENCOUNTERED.value
    # Identidad de lo despachado, separada del resultado de la consulta. Un
    # comando corrompido NO es una consulta rechazada: IOS nunca recibió lo
    # que se pidió, así que rechazarlo no dice nada sobre la consulta.
    dispatch_classification: str = DispatchClassification.ECHO_UNOBSERVABLE.value
    echo_observed: str = ""
    dispatch_attempts: int = 1
    # Procedencia de la EJECUCION, no del pedido. `device_name` sigue siendo a
    # quien se le pidio; `observed_device_name` sale de enumerar la red y
    # quedarse con el unico device que puede haber producido esta sesion. Los
    # defaults no afirman nada: sin atribucion, la identidad de la fuente sigue
    # siendo inobservable.
    observed_device_name: str = ""
    device_identity_provenance: str = DeviceIdentityProvenance.NOT_OBSERVED.value
    device_identity_evidence: str = DeviceIdentityEvidence.NONE.value


@dataclass(frozen=True)
class InterfaceStatusRow:
    interface: str
    ip_address: str
    status: str
    protocol: str


@dataclass(frozen=True)
class EphoneStatusRow:
    index: int
    mac_address: str
    registered: bool
    ip_address: str
    extension: str
    line_state: str


@dataclass(frozen=True)
class TrunkStatusRow:
    interface: str
    mode: str
    encapsulation: str
    status: str
    native_vlan: str


@dataclass(frozen=True)
class StpPortStatusRow:
    interface: str
    role: str
    state: str
    cost: int
    priority_number: str
    link_type: str


@dataclass(frozen=True)
class StpInstanceStatus:
    vlan_id: int
    protocol: str
    root_priority: int
    root_address: str
    root_is_local: bool
    root_cost: int | None
    root_port: str
    bridge_priority: int
    bridge_base_priority: int | None
    bridge_address: str
    interfaces: tuple[StpPortStatusRow, ...]


@dataclass(frozen=True)
class EtherChannelMemberStatus:
    interface: str
    flag: str


@dataclass(frozen=True)
class EtherChannelGroupStatus:
    group_number: int
    port_channel: str
    port_channel_flags: str
    protocol: str
    members: tuple[EtherChannelMemberStatus, ...]


@dataclass(frozen=True)
class OspfNeighborStatusRow:
    neighbor_id: str
    priority: int
    state: str
    role: str
    dead_time: str
    address: str
    interface: str


@dataclass(frozen=True)
class OspfRouteStatusRow:
    code: str
    prefix: str
    prefix_length: int | None
    administrative_distance: int
    metric: int
    next_hop: str
    age: str
    interface: str


@dataclass(frozen=True)
class RipRouteStatusRow:
    """Una ruta APRENDIDA por RIP, tal como PT 9.0.1.0858 la imprime.

    Sólo campos que la salida real expone. `prefix_length` es opcional porque
    IOS puede imprimir la ruta sin longitud cuando no hay subnetting.
    """

    code: str
    prefix: str
    prefix_length: int | None
    administrative_distance: int
    metric: int
    next_hop: str
    age: str
    interface: str


@dataclass(frozen=True)
class RipProtocolStatus:
    """Estado SEMÁNTICO de RIP leído de `show ip protocols`.

    Los temporizadores (`next due in N seconds`) cambian entre lecturas y no
    son configuración: quedan deliberadamente fuera.
    """

    version_send: int | None
    version_recv: int | None
    auto_summary: bool | None
    networks: tuple[str, ...]
    passive_interfaces: tuple[str, ...]


@dataclass(frozen=True)
class TerminalOutputWindow:
    output: str
    fresh: bool
    strategy: str
    query_echo_found: bool = False


def normalize_terminal_output(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", value).replace("\r\n", "\n").replace("\r", "\n")


def _has_active_pager(value: str) -> bool:
    # Delegado a la frontera de despacho: alli la deteccion aplica los
    # backspaces con los que IOS redibuja su propio `--More--`, que es
    # justamente el estado que consume la primera tecla del comando siguiente.
    return has_active_pager(value)


_SVI_STATE = re.compile(
    r"(?im)^(?P<interface>[A-Za-z][A-Za-z0-9/.-]*)\s+is\s+(?P<admin>[^,]+),\s*"
    r"line protocol is\s+(?P<protocol>\S+)",
)
_SVI_ADDRESS = re.compile(r"(?im)^\s*Internet address is\s+(?P<address>\d+\.\d+\.\d+\.\d+)/(?P<prefix>\d+)")


# Syslog de IOS: `%FACILITY-severidad-MNEMONICO:`. Un `no shutdown` correcto
# devuelve `%LINK-5-CHANGED: ...`, y leer ese `%` como error daria por
# rechazado un comando que si se aplico.
_IOS_SYSLOG = re.compile(r"(?m)^\s*%[A-Z][A-Z0-9_]*-\d+-[A-Z0-9_]+\s*:")

# Rechazos de IOS. No todos dicen "% Invalid input": medido en PT 9.0.1.0858,
# `duplex half` sobre un Gigabit en autonegociacion responde
# "%Duplex cannot be set to half when speed autonegotiation subset contains
# 1Gbps", que es un rechazo con otra forma. Clasificar por "% Invalid" habria
# dado ese comando por aceptado.
_IOS_ERROR = re.compile(r"(?m)^\s*%.*$")


def ios_rejection_reason(value: str) -> str | None:
    """Devuelve el texto del rechazo, o None si IOS no rechazo nada.

    Solo distingue rechazo de no-rechazo. Que un comando no sea rechazado no
    prueba que haya surtido efecto: eso se decide releyendo, no leyendo el eco.
    """
    for line in normalize_terminal_output(value).splitlines():
        if not line.lstrip().startswith("%"):
            continue
        if _IOS_SYSLOG.match(line):
            continue
        stripped = line.strip()
        if stripped != "%":
            return stripped
    return None


@dataclass(frozen=True)
class EthernetLinkModeStatus:
    """Estado fisico y metadata de routing de una interfaz Ethernet.

    Van juntos en la lectura y separados en el tipo porque son independientes:
    con `bandwidth 5000` sobre un enlace negociado a 100 Mbps, PT 9.0.1.0858
    informa "BW 5000 Kbit" y "Full Duplex, 100Mbps" en la misma salida.
    """

    interface: str
    duplex: str            # full | half | auto | ""
    speed_bps: int | None  # lo que la linea informa; ver negotiated_speed_bps
    speed_auto: bool
    routing_bandwidth_kbps: int | None
    line_protocol_up: bool | None

    @property
    def reported_speed_bps(self) -> int | None:
        """Lo que la linea informa, solo con el protocolo arriba.

        NO es la tasa negociada y no debe usarse como tal. Medido en PT
        9.0.1.0858:

        * un uplink Gigabit sin cable informa "Half-duplex, 100Mb/s" mientras
          su BW de routing sigue en 1000000 Kbit;
        * un enlace Gigabit<->Gigabit informa "100Mbps" en los dos extremos
          aunque su BW de routing diga 1000000 Kbit.

        La cifra solo empezo a moverse tras un `speed 1000` explicito. Para la
        tasa efectiva, `routing_bandwidth_kbps` con la autonegociacion activa
        es la mejor evidencia disponible, y aun asi es indirecta.
        """
        return self.speed_bps if self.line_protocol_up else None

    @property
    def reported_duplex(self) -> str:
        return self.duplex if self.line_protocol_up else ""


# Dos formatos en el mismo backend: un 2911 imprime "Full Duplex, 100Mbps" y un
# 3560 "Full-duplex, 100Mb/s". Una regex escrita contra una sola muestra habria
# dejado la otra plataforma sin leer.
_LINK_MODE = re.compile(
    r"(?i)\b(?P<duplex>auto|full|half)[-\s]?duplex\s*,\s*"
    r"(?P<speed>auto[-\s]?speed|\d+\s*[MG]b(?:ps|/s))",
)
_ROUTING_BANDWIDTH = re.compile(r"(?i)\bBW\s+(?P<kbps>\d+)\s*Kbit")
_SPEED_VALUE = re.compile(r"(?i)(?P<value>\d+)\s*(?P<unit>[MG])b")


def parse_ethernet_link_mode(value: str) -> EthernetLinkModeStatus | None:
    """Lee `show interfaces <ethernet>`.

    Ausencia de la linea de duplex no es un fallo de lectura: un puerto que
    nunca negocio no tiene tasa fisica que informar.
    """
    normalized = normalize_terminal_output(value)
    state = _SVI_STATE.search(normalized)
    if state is None:
        return None
    mode = _LINK_MODE.search(normalized)
    duplex, speed_bps, speed_auto = "", None, False
    if mode is not None:
        duplex = mode.group("duplex").casefold()
        raw_speed = mode.group("speed")
        if raw_speed.casefold().replace(" ", "").replace("-", "").startswith("auto"):
            speed_auto = True
        else:
            value_match = _SPEED_VALUE.search(raw_speed)
            if value_match:
                scale = 1_000_000 if value_match.group("unit").upper() == "M" else 1_000_000_000
                speed_bps = int(value_match.group("value")) * scale
    bandwidth = _ROUTING_BANDWIDTH.search(normalized)
    return EthernetLinkModeStatus(
        interface=state.group("interface"),
        duplex=duplex,
        speed_bps=speed_bps,
        speed_auto=speed_auto or duplex == "auto",
        routing_bandwidth_kbps=int(bandwidth.group("kbps")) if bandwidth else None,
        line_protocol_up=state.group("protocol").strip().casefold().startswith("up"),
    )


@dataclass(frozen=True)
class SerialControllerStatus:
    """Rol del extremo y reloj, leidos del controlador de la serial."""

    interface: str
    endpoint_role: str
    clock_rate_bps: int | None


_CONTROLLER_ROLE = re.compile(r"(?im)^\s*(?P<role>DCE|DTE)\b(?P<rest>.*)$")
_CONTROLLER_CLOCK = re.compile(r"(?i)clock rate\s+(?P<rate>\d+)")


def parse_serial_controller(value: str) -> SerialControllerStatus | None:
    """Lee `show controllers <serial>`.

    Medido en PT 9.0.1.0858: el DCE responde "DCE V.35, clock rate 2000000" y
    el DTE "DTE V.35 TX and RX clocks detected". El reloj pertenece al DCE; la
    ausencia en el DTE no es un fallo de lectura, es que no tiene reloj propio.
    """
    normalized = normalize_terminal_output(value)
    role = _CONTROLLER_ROLE.search(normalized)
    if role is None:
        return None
    interface = ""
    header = re.search(r"(?im)^Interface\s+(?P<name>\S+)", normalized)
    if header:
        interface = header.group("name")
    clock = _CONTROLLER_CLOCK.search(role.group("rest"))
    return SerialControllerStatus(
        interface=interface,
        endpoint_role=role.group("role").casefold(),
        clock_rate_bps=int(clock.group("rate")) if clock else None,
    )


def parse_show_ip_interface(value: str) -> InterfaceStatusRow | None:
    """Lee una sola interfaz de ``show ip interface <iface>``.

    `show ip interface brief` pagina en un switch de 24+ puertos y PT 9.0.1
    rechaza ``terminal length 0``, de modo que las interfaces Vlan quedan fuera
    de la primera página. La consulta por interfaz entrega estado y dirección
    dentro de esa primera página, sin depender de cuántos puertos existan.
    """
    normalized = normalize_terminal_output(value)
    state = _SVI_STATE.search(normalized)
    if state is None:
        return None
    address = _SVI_ADDRESS.search(normalized)
    return InterfaceStatusRow(
        state.group("interface"),
        address.group("address") if address else "unassigned",
        state.group("admin").strip(),
        state.group("protocol").strip(),
    )


def parse_show_ip_interface_brief(value: str) -> list[InterfaceStatusRow]:
    rows: list[InterfaceStatusRow] = []
    for line in normalize_terminal_output(value).splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0].casefold() == "interface":
            continue
        if not re.match(r"^[A-Za-z]+[A-Za-z0-9/.-]*$", parts[0]):
            continue
        rows.append(InterfaceStatusRow(parts[0], parts[1], " ".join(parts[4:-1]), parts[-1]))
    return rows


def parse_show_ephone(value: str) -> list[EphoneStatusRow]:
    """Extrae el estado vigente de cada bloque de ``show ephone`` de PT."""
    normalized = normalize_terminal_output(value)
    starts = list(re.finditer(
        r"(?m)^ephone-(?P<index>\d+)\s+Mac:(?P<mac>[0-9A-Fa-f.:-]+).*?"
        r"(?P<registration>UNREGISTERED|REGISTERED)(?:\s|$)",
        normalized,
    ))
    rows: list[EphoneStatusRow] = []
    for position, match in enumerate(starts):
        end = starts[position + 1].start() if position + 1 < len(starts) else len(normalized)
        block = normalized[match.start():end]
        ip_match = re.search(r"(?m)^IP:(?P<ip>\S+)", block)
        line_match = re.search(
            r"(?m)^\s*button\s+\d+:\s+dn\s+\d+\s+number\s+"
            r"(?P<extension>\d+)\s+CH\d+\s+(?P<state>\S+)",
            block,
            re.IGNORECASE,
        )
        if ip_match is None or line_match is None:
            continue
        rows.append(EphoneStatusRow(
            index=int(match.group("index")),
            mac_address=match.group("mac"),
            registered=match.group("registration").upper() == "REGISTERED",
            ip_address=ip_match.group("ip"),
            extension=line_match.group("extension"),
            line_state=line_match.group("state").upper(),
        ))
    return rows


def parse_show_interfaces_trunk(value: str) -> list[TrunkStatusRow]:
    """Parsea solamente filas de trunk del SHOW actual de Packet Tracer."""
    rows: list[TrunkStatusRow] = []
    for line in normalize_terminal_output(value).splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].casefold() in {"port", "switch>"}:
            continue
        if not re.match(r"^[A-Za-z]+[A-Za-z0-9/.-]*$", parts[0]):
            continue
        if parts[1].casefold() not in {"on", "desirable", "auto", "trunk"}:
            continue
        rows.append(TrunkStatusRow(parts[0], parts[1], parts[2], parts[3], parts[4]))
    return rows


def classify_show_interfaces_trunk(value: str, *, executed: bool = True) -> TrunkQueryClassification:
    if not executed:
        return TrunkQueryClassification.QUERY_TIMEOUT
    output = normalize_terminal_output(value).casefold()
    if "invalid input" in output or "% unknown command" in output:
        return TrunkQueryClassification.INVALID_COMMAND
    if "unimplemented" in output or "not supported" in output:
        return TrunkQueryClassification.UNIMPLEMENTED
    if parse_show_interfaces_trunk(value):
        return TrunkQueryClassification.SUPPORTED_WITH_ROWS
    if "show interfaces trunk" in output:
        return TrunkQueryClassification.SUPPORTED_EMPTY
    return TrunkQueryClassification.PARSER_UNAVAILABLE


def parse_show_spanning_tree(value: str) -> list[StpInstanceStatus]:
    """Parse the exact multi-instance layout emitted by PT 9.0.1.0858."""
    normalized = normalize_terminal_output(value)
    starts = list(re.finditer(r"(?m)^VLAN(?P<vlan>\d+)\s*$", normalized))
    instances: list[StpInstanceStatus] = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(normalized)
        block = normalized[start.start():end]
        protocol = re.search(
            r"(?m)^\s*Spanning tree enabled protocol\s+(?P<value>\S+)\s*$",
            block,
        )
        root = re.search(
            r"(?ms)^\s*Root ID\s+Priority\s+(?P<priority>\d+)\s*\n"
            r"\s*Address\s+(?P<address>[0-9A-Fa-f.:-]+)(?P<body>.*?)"
            r"^\s*Bridge ID\s+Priority",
            block,
        )
        bridge = re.search(
            r"(?m)^\s*Bridge ID\s+Priority\s+(?P<priority>\d+)"
            r"(?:\s+\(priority\s+(?P<base>\d+)\s+sys-id-ext\s+\d+\))?\s*\n"
            r"\s*Address\s+(?P<address>[0-9A-Fa-f.:-]+)",
            block,
        )
        if protocol is None or root is None or bridge is None:
            continue
        root_body = root.group("body")
        cost = re.search(r"(?m)^\s*Cost\s+(?P<value>\d+)\s*$", root_body)
        port = re.search(
            r"(?m)^\s*Port\s+\d+\((?P<value>[^)]+)\)\s*$",
            root_body,
        )
        rows: list[StpPortStatusRow] = []
        for line in block.splitlines():
            parts = line.split()
            if len(parts) < 6 or not re.fullmatch(
                r"[A-Za-z]+[A-Za-z0-9/.-]*", parts[0]
            ):
                continue
            if parts[1] not in {"Root", "Desg", "Altn", "Back", "Mstr"}:
                continue
            try:
                row_cost = int(parts[3])
            except ValueError:
                continue
            rows.append(StpPortStatusRow(
                interface=parts[0],
                role=parts[1],
                state=parts[2],
                cost=row_cost,
                priority_number=parts[4],
                link_type=" ".join(parts[5:]),
            ))
        instances.append(StpInstanceStatus(
            vlan_id=int(start.group("vlan")),
            protocol=protocol.group("value").casefold(),
            root_priority=int(root.group("priority")),
            root_address=root.group("address"),
            root_is_local="this bridge is the root" in root_body.casefold(),
            root_cost=int(cost.group("value")) if cost else None,
            root_port=port.group("value") if port else "",
            bridge_priority=int(bridge.group("priority")),
            bridge_base_priority=(
                int(bridge.group("base")) if bridge.group("base") else None
            ),
            bridge_address=bridge.group("address"),
            interfaces=tuple(rows),
        ))
    return instances


def classify_show_spanning_tree(
    value: str,
    *,
    executed: bool = True,
) -> StpQueryClassification:
    if not executed:
        return StpQueryClassification.QUERY_TIMEOUT
    output = normalize_terminal_output(value).casefold()
    if "invalid input" in output or "% unknown command" in output:
        return StpQueryClassification.INVALID_COMMAND
    if "unimplemented" in output or "not supported" in output:
        return StpQueryClassification.UNIMPLEMENTED
    if parse_show_spanning_tree(value):
        return StpQueryClassification.SUPPORTED_WITH_INSTANCES
    if "no spanning tree instance exists" in output:
        return StpQueryClassification.SUPPORTED_EMPTY
    if "show spanning-tree" in output:
        return StpQueryClassification.PARSER_UNAVAILABLE
    return StpQueryClassification.PARSER_UNAVAILABLE


def parse_show_etherchannel_summary(
    value: str,
) -> list[EtherChannelGroupStatus]:
    """Parse the group row observed in PT 9.0.1.0858."""
    groups: list[EtherChannelGroupStatus] = []
    group_row = re.compile(
        r"\s*(?P<group>\d+)\s+"
        r"(?P<port_channel>Po\d+)\((?P<flags>[A-Za-z]+)\)\s+"
        r"(?P<protocol>[A-Za-z0-9-]+)\s+"
        r"(?P<members>.+?)\s*"
    )
    member_value = re.compile(
        r"(?P<interface>[A-Za-z]+[A-Za-z0-9/.-]*)"
        r"\((?P<flag>[A-Za-z]+)\)"
    )
    for line in normalize_terminal_output(value).splitlines():
        match = group_row.fullmatch(line)
        if match is None:
            continue
        # LACP is the only protocol row backed by a captured PT 9.0.1.0858
        # fixture. PAgP and static/on stay unobservable until their real output
        # is captured instead of being accepted by a permissive regex.
        if match.group("protocol").casefold() != "lacp":
            continue
        members = tuple(
            EtherChannelMemberStatus(
                interface=item.group("interface"),
                flag=item.group("flag"),
            )
            for item in member_value.finditer(match.group("members"))
        )
        observed_members = " ".join(match.group("members").split())
        parsed_members = " ".join(
            f"{item.interface}({item.flag})" for item in members
        )
        if not members or parsed_members != observed_members:
            continue
        groups.append(EtherChannelGroupStatus(
            group_number=int(match.group("group")),
            port_channel=match.group("port_channel"),
            port_channel_flags=match.group("flags"),
            protocol=match.group("protocol"),
            members=members,
        ))
    return groups


def classify_show_etherchannel_summary(
    value: str,
    *,
    executed: bool = True,
) -> EtherChannelQueryClassification:
    if not executed:
        return EtherChannelQueryClassification.QUERY_TIMEOUT
    if parse_show_etherchannel_summary(value):
        return EtherChannelQueryClassification.SUPPORTED_WITH_GROUPS
    return EtherChannelQueryClassification.PARSER_UNAVAILABLE


def parse_show_ip_ospf_neighbor(value: str) -> list[OspfNeighborStatusRow]:
    """Parse only the FULL DR/BDR rows observed in PT 9.0.1.0858."""
    rows: list[OspfNeighborStatusRow] = []
    row_pattern = re.compile(
        r"\s*(?P<neighbor>\d{1,3}(?:\.\d{1,3}){3})\s+"
        r"(?P<priority>\d+)\s+"
        r"(?P<state>FULL)/(?P<role>DR|BDR)\s+"
        r"(?P<dead_time>\d{2}:\d{2}:\d{2})\s+"
        r"(?P<address>\d{1,3}(?:\.\d{1,3}){3})\s+"
        r"(?P<interface>GigabitEthernet\d+/\d+)\s*"
    )
    for line in normalize_terminal_output(value).splitlines():
        match = row_pattern.fullmatch(line)
        if match is None:
            continue
        rows.append(OspfNeighborStatusRow(
            neighbor_id=match.group("neighbor"),
            priority=int(match.group("priority")),
            state=match.group("state"),
            role=match.group("role"),
            dead_time=match.group("dead_time"),
            address=match.group("address"),
            interface=match.group("interface"),
        ))
    return rows


def classify_show_ip_ospf_neighbor(
    value: str,
    *,
    executed: bool = True,
) -> OspfQueryClassification:
    if not executed:
        return OspfQueryClassification.QUERY_TIMEOUT
    if parse_show_ip_ospf_neighbor(value):
        return OspfQueryClassification.SUPPORTED_WITH_ROWS
    return OspfQueryClassification.PARSER_UNAVAILABLE


def parse_show_ip_route_ospf(value: str) -> list[OspfRouteStatusRow]:
    """Parse only the OSPF route row observed in PT 9.0.1.0858."""
    rows: list[OspfRouteStatusRow] = []
    row_pattern = re.compile(
        r"\s*(?P<code>O)\s+"
        r"(?P<prefix>\d{1,3}(?:\.\d{1,3}){3})"
        r"(?:/(?P<prefix_length>\d{1,2}))?\s+"
        r"\[(?P<distance>\d+)/(?P<metric>\d+)\]\s+"
        r"via\s+(?P<next_hop>\d{1,3}(?:\.\d{1,3}){3}),\s+"
        r"(?P<age>\d{2}:\d{2}:\d{2}),\s+"
        r"(?P<interface>GigabitEthernet\d+/\d+)\s*"
    )
    for line in normalize_terminal_output(value).splitlines():
        match = row_pattern.fullmatch(line)
        if match is None:
            continue
        prefix_length = (
            int(match.group("prefix_length"))
            if match.group("prefix_length") is not None else None
        )
        if prefix_length is not None and prefix_length > 32:
            continue
        rows.append(OspfRouteStatusRow(
            code=match.group("code"),
            prefix=match.group("prefix"),
            prefix_length=prefix_length,
            administrative_distance=int(match.group("distance")),
            metric=int(match.group("metric")),
            next_hop=match.group("next_hop"),
            age=match.group("age"),
            interface=match.group("interface"),
        ))
    return rows


def classify_show_ip_route_ospf(
    value: str,
    *,
    executed: bool = True,
) -> OspfQueryClassification:
    if not executed:
        return OspfQueryClassification.QUERY_TIMEOUT
    if parse_show_ip_route_ospf(value):
        return OspfQueryClassification.SUPPORTED_WITH_ROWS
    return OspfQueryClassification.PARSER_UNAVAILABLE


def parse_show_ip_eigrp_neighbors(_value: str) -> list[Never]:
    """No EIGRP neighbor row was observed in PT 9.0.1.0858."""
    return []


def classify_show_ip_eigrp_neighbors(
    value: str,
    *,
    executed: bool = True,
    expected_as_number: int | None = None,
) -> EigrpQueryClassification:
    if not executed:
        return EigrpQueryClassification.QUERY_TIMEOUT
    lines = tuple(
        line.strip()
        for line in normalize_terminal_output(value).splitlines()
        if line.strip()
    )
    if len(lines) == 3 and lines[0] == "show ip eigrp neighbors":
        process = re.fullmatch(
            r"IP-EIGRP neighbors for process (?P<as_number>\d+)",
            lines[1],
        )
        if process is not None and re.fullmatch(r"\S+[>#]", lines[2]):
            observed_as = int(process.group("as_number"))
            if expected_as_number is not None and observed_as != expected_as_number:
                return EigrpQueryClassification.PROCESS_MISMATCH
            return EigrpQueryClassification.SUPPORTED_EMPTY
    return EigrpQueryClassification.PARSER_UNAVAILABLE


def parse_show_ip_route_eigrp(_value: str) -> list[Never]:
    """No EIGRP route row was observed in PT 9.0.1.0858."""
    return []


def classify_show_ip_route_eigrp(
    value: str,
    *,
    executed: bool = True,
) -> EigrpQueryClassification:
    if not executed:
        return EigrpQueryClassification.QUERY_TIMEOUT
    lines = tuple(
        line.strip()
        for line in normalize_terminal_output(value).splitlines()
        if line.strip()
    )
    if (
        len(lines) == 2
        and lines[0] == "show ip route eigrp"
        and re.fullmatch(r"\S+[>#]", lines[1])
    ):
        return EigrpQueryClassification.SUPPORTED_EMPTY
    return EigrpQueryClassification.PARSER_UNAVAILABLE


# Packet Tracer indenta las entradas de red e interfaz pasiva con TAB, no con
# dos espacios: exigir espacios las hace invisibles.
_RIP_BLOCK_HEADER = re.compile(r'^\s*Routing Protocol is\s+"(?P<protocol>[^"]*)"')
_RIP_VERSION = re.compile(
    r"send\s+version\s+(?P<send>\d+),\s*receive\s+(?:version\s+)?(?P<recv>\d+)",
    re.IGNORECASE,
)
_RIP_NETWORKS_HEADER = re.compile(r"^\s*Routing for Networks:", re.IGNORECASE)
_RIP_PASSIVE_HEADER = re.compile(r"^\s*Passive Interface\(s\):", re.IGNORECASE)
_RIP_NETWORK_ENTRY = re.compile(r"[ \t]+(?P<network>\d{1,3}(?:\.\d{1,3}){3})[ \t]*")
_RIP_PASSIVE_ENTRY = re.compile(r"[ \t]+(?P<interface>[A-Za-z][A-Za-z0-9/.]*)[ \t]*")


def _rip_entries(
    block: list[str], header: re.Pattern[str], entry: re.Pattern[str],
) -> tuple[str, ...]:
    found: list[str] = []
    inside = False
    for line in block:
        if header.match(line):
            inside = True
            continue
        if not inside:
            continue
        match = entry.fullmatch(line)
        if match is not None:
            found.append(match.group(1))
            continue
        if line.strip():
            break
    return tuple(found)


def parse_show_ip_protocols_rip(value: str) -> RipProtocolStatus | None:
    """Lee el bloque RIP de `show ip protocols` tal como PT 9.0.1.0858 lo emite.

    Devuelve None cuando no hay proceso RIP, que es evidencia de ausencia y no
    un fallo de lectura. `show ip protocols` puede listar varios protocolos,
    así que el bloque se acota hasta el siguiente `Routing Protocol is`.
    """
    lines = normalize_terminal_output(value).splitlines()
    start = next(
        (
            index for index, line in enumerate(lines)
            if (match := _RIP_BLOCK_HEADER.match(line)) is not None
            and match.group("protocol").strip().casefold() == "rip"
        ),
        None,
    )
    if start is None:
        return None
    block = [lines[start]]
    for line in lines[start + 1:]:
        if _RIP_BLOCK_HEADER.match(line):
            break
        block.append(line)
    version_send: int | None = None
    version_recv: int | None = None
    auto_summary: bool | None = None
    for line in block:
        version = _RIP_VERSION.search(line)
        if version is not None and version_send is None:
            version_send = int(version.group("send"))
            version_recv = int(version.group("recv"))
        if "automatic network summarization is" in line.casefold():
            auto_summary = "not in effect" not in line.casefold()
    return RipProtocolStatus(
        version_send=version_send,
        version_recv=version_recv,
        auto_summary=auto_summary,
        networks=_rip_entries(block, _RIP_NETWORKS_HEADER, _RIP_NETWORK_ENTRY),
        passive_interfaces=_rip_entries(
            block, _RIP_PASSIVE_HEADER, _RIP_PASSIVE_ENTRY,
        ),
    )


# Capturado en vivo en R2-B fase 4 sobre PT 9.0.1.0858:
#
#     R       150.1.1.0/27 [120/1] via 150.1.1.86, 00:00:26, Serial0/0/0
#
# La interfaz NO se restringe a GigabitEthernet, como si hace el parser de
# OSPF: la ruta RIP calificada llega por una Serial, y anclar el nombre de
# familia la haria invisible.
_RIP_ROUTE_ROW = re.compile(
    r"\s*(?P<code>R)\s+"
    r"(?P<prefix>\d{1,3}(?:\.\d{1,3}){3})"
    r"(?:/(?P<prefix_length>\d{1,2}))?\s+"
    r"\[(?P<distance>\d+)/(?P<metric>\d+)\]\s+"
    r"via\s+(?P<next_hop>\d{1,3}(?:\.\d{1,3}){3}),\s+"
    r"(?P<age>\d{2}:\d{2}:\d{2}),\s+"
    r"(?P<interface>[A-Za-z][A-Za-z0-9/.]*)\s*"
)


def parse_show_ip_route_rip(value: str) -> list[RipRouteStatusRow]:
    """Lee sólo filas `R` completas de `show ip route rip`.

    Una fila sin distancia, metrica, siguiente salto o interfaz no se
    completa con supuestos: simplemente no es una fila.
    """
    rows: list[RipRouteStatusRow] = []
    for line in normalize_terminal_output(value).splitlines():
        match = _RIP_ROUTE_ROW.fullmatch(line)
        if match is None:
            continue
        length = (
            int(match.group("prefix_length"))
            if match.group("prefix_length") is not None else None
        )
        if length is not None and length > 32:
            continue
        rows.append(RipRouteStatusRow(
            code=match.group("code"),
            prefix=match.group("prefix"),
            prefix_length=length,
            administrative_distance=int(match.group("distance")),
            metric=int(match.group("metric")),
            next_hop=match.group("next_hop"),
            age=match.group("age"),
            interface=match.group("interface"),
        ))
    return rows


def extract_terminal_command_window(before: str, after: str, command: str) -> TerminalOutputWindow:
    """Aísla evidencia de la consulta actual sin confiar en historial IOS.

    Ya no se ancla buscando el texto del comando. Esa estrategia tenía dos
    fallas que sólo aparecen en sesiones largas y bajo corrupción de comandos:
    un comando corrompido no se encontraba nunca, y un comando repetido se
    anclaba a una ejecución ANTERIOR, atribuyendo salida stale como fresca.
    El anclaje ahora es por el mayor sufijo retenido del buffer.

    `query_echo_found` pasó a exigir eco EXACTO: que la ventana contenga el
    texto pedido en alguna línea no prueba que el terminal lo haya recibido.
    """
    window = fresh_command_window(before, after)
    if not window.fresh:
        return TerminalOutputWindow("", False, window.strategy.value)
    classification, _ = classify_echo(command, window.output)
    return TerminalOutputWindow(
        window.output,
        True,
        window.strategy.value,
        classification is DispatchClassification.DISPATCHED,
    )


@dataclass(frozen=True)
class _PagerCapture:
    """Resultado de UNA lectura logica, paginada o no.

    `complete` y `truncated` no son el mismo hecho negado: una captura que
    recorrio tres paginas y cerro en el prompt es COMPLETA aunque hubo
    paginacion, y una que encontro el pager y no pudo cerrar es TRUNCADA aunque
    su primera pagina se conserve como evidencia.
    """

    output: str
    pages: int
    complete: bool
    truncated: bool
    continuation: PagerContinuation
    transcript: str = ""
    failure_reason: str = ""

    @classmethod
    def not_encountered(cls, output: str, transcript: str) -> "_PagerCapture":
        return cls(output, 1, True, False, PagerContinuation.NOT_ENCOUNTERED, transcript)

    @classmethod
    def not_qualified(cls, output: str, transcript: str) -> "_PagerCapture":
        return cls(output, 1, False, True, PagerContinuation.NOT_QUALIFIED, transcript)

    @classmethod
    def completed(cls, output: str, pages: int, transcript: str) -> "_PagerCapture":
        return cls(output, pages, True, False, PagerContinuation.COMPLETED, transcript)

    @classmethod
    def failed(
        cls, output: str, pages: int, transcript: str, reason: str,
    ) -> "_PagerCapture":
        return cls(
            output, pages, False, True, PagerContinuation.FAILED, transcript, reason,
        )


def execution_attribution_js(
    device_literal: str,
    baseline: str,
    command: str,
    *,
    prefer_command_prompt: bool = False,
) -> str:
    """Script que LEE la salida y ATRIBUYE la sesion en la misma enumeracion.

    No pregunta "como se llama el device que pedi". Recorre la red y se queda
    con el unico device que puede haber producido esta sesion, ya sea porque su
    objeto terminal es el mismo al que se despacho, ya sea porque su
    transcripcion retiene el contexto de despacho con el comando detras. La
    salida devuelta sale de ESE device, no de una segunda busqueda por nombre:
    asi la evidencia y su procedencia no pueden venir de dos devices distintos.

    `prefer_command_prompt` existe porque un endpoint responde por
    `getCommandPrompt` y un IOS por `getCommandLine`. El objetivo y los
    candidatos se resuelven SIEMPRE con el mismo orden de accesores: comparar
    terminales obtenidas por caminos distintos no compararia lo mismo.
    """
    resolve = (
        "var __term=function(dev){var r=null;"
        + (
            "try{if(dev&&typeof dev.getCommandPrompt==='function'){"
            "r=dev.getCommandPrompt();if(r)return r;}}catch(pe){}"
            if prefer_command_prompt else ""
        )
        + "try{if(dev&&typeof dev.getCommandLine==='function'){"
        "r=dev.getCommandLine();if(r)return r;}}catch(le){}return null;};"
    )
    return "".join((
        "try{var net=ipc.network();", resolve,
        "var d=net.getDevice(", device_literal, ");var t=__term(d);",
        "if(!t||typeof t.getOutput!=='function'){",
        "reportResult(JSON.stringify({found:false,",
        "failure_reason:'IOS terminal unavailable'}));}else{",
        "var base=", json.dumps(baseline), ";",
        "var cmd=", json.dumps(command), ";",
        # Anclar por el SUFIJO retenido, no por prefijo. Es la misma algebra de
        # frescura que `fresh_command_window` ya midio en este build: `after`
        # puede dejar de empezar por `before` sin haber perdido nada -- el pager
        # borra su `--More--` al salir, y un buffer largo rueda por la cabeza.
        # Exigir prefijo rechazaba justamente esas sesiones, que son frescas y
        # atribuibles.
        "var anchor=base;",
        "while(anchor.length&&anchor.charCodeAt(anchor.length-1)<=32)"
        "{anchor=anchor.substring(0,anchor.length-1);}",
        "if(anchor.length>512){anchor=anchor.substring(anchor.length-512);}",
        "var n=(typeof net.getDeviceCount==='function')?net.getDeviceCount():0;",
        "var byObject=[],byTranscript=[],outObject='',outTranscript='';",
        "for(var i=0;i<n;i++){var dev=null;",
        "try{dev=net.getDeviceAt(i);}catch(de){dev=null;}",
        "if(!dev)continue;var cl=__term(dev);",
        "if(!cl||typeof cl.getOutput!=='function')continue;",
        "var nm='';try{nm=String(dev.getName());}catch(ne){continue;}",
        "var co='';try{co=String(cl.getOutput());}catch(oe){continue;}",
        "if(cl===t){byObject.push(nm);outObject=co;}",
        # Contexto retenido MAS el comando despachado detras de el. El gemelo
        # ocioso no basta con compartir banner: tendria que haber recibido este
        # mismo comando justo despues de este mismo contexto, y los despachos
        # registrados van de a uno.
        "if(anchor!==''){var at=co.indexOf(anchor);",
        "if(at>=0&&co.substring(at+anchor.length).indexOf(cmd)>=0){",
        "byTranscript.push(nm);outTranscript=co;}}}",
        "var owner='',evidence='none',candidates=0,out='';",
        "if(byObject.length===1){owner=byObject[0];",
        "evidence='terminal_object_identity';candidates=1;out=outObject;}",
        "else if(byObject.length>1){candidates=byObject.length;}",
        "else if(byTranscript.length===1){owner=byTranscript[0];",
        "evidence='session_transcript_continuity';candidates=1;",
        "out=outTranscript;}else{candidates=byTranscript.length;}",
        "if(owner===''){out=String(t.getOutput());}",
        "reportResult(JSON.stringify({found:true,",
        "configuration_channel:out!==base,output:out,owner_name:owner,",
        "owner_evidence:evidence,owner_candidates:candidates,",
        "device_count:n}));}}catch(e){reportResult('ERROR:'+e);}",
    ))


def classify_execution_identity(
    device_name: str, attribution: dict,
) -> dict[str, str]:
    """Clasifica la atribucion. Nunca deriva identidad del nombre pedido."""
    owner = str(attribution.get("owner_name") or "")
    candidates = attribution.get("owner_candidates")
    evidence = _identity_evidence(attribution.get("owner_evidence"))
    # Un nombre sin via de atribucion reconocida no es atribucion. Aceptarlo
    # seria confiar en un dato cuya procedencia no se sabe, que es justamente
    # lo que este campo no puede hacer.
    if owner and evidence is not DeviceIdentityEvidence.NONE:
        return {
            "observed_device_name": owner,
            "device_identity_provenance": (
                DeviceIdentityProvenance.CONFIRMED_UNIQUE.value
                if owner == device_name
                else DeviceIdentityProvenance.MISMATCHED.value
            ),
            "device_identity_evidence": evidence.value,
        }
    return {
        "observed_device_name": "",
        "device_identity_provenance": (
            DeviceIdentityProvenance.AMBIGUOUS.value
            if type(candidates) is int and candidates > 1
            else DeviceIdentityProvenance.NOT_OBSERVED.value
        ),
        "device_identity_evidence": DeviceIdentityEvidence.NONE.value,
    }


def _identity_evidence(value: object) -> DeviceIdentityEvidence:
    """Una via de atribucion desconocida no se acepta como si fuera prueba."""
    try:
        evidence = DeviceIdentityEvidence(str(value))
    except ValueError:
        return DeviceIdentityEvidence.NONE
    return evidence


class ControlledIosExecutor:
    """Ejecuta exclusivamente consultas IOS registradas; nunca CLI del usuario."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        *,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._send_and_wait = send_and_wait
        self._pager_quarantine: set[str] = set()
        # Reloj y espera inyectables: las cotas de la captura paginada se miden
        # en lugar de dormirse, y una regresion puede recorrerlas sin gastar el
        # tiempo real que representan.
        self._clock = clock
        self._sleeper = sleeper

    def wait_until_ready(
        self,
        device_name: str,
        *,
        timeout_seconds: float = 90.0,
        interval_seconds: float = 0.25,
    ) -> DeviceInitializationResult:
        """Espera el boot IOS con el waiter compartido, separado del SHOW."""
        name = json.dumps(device_name)
        return IosBootWaiter(
            lambda: self._terminal_state(name),
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        ).wait()

    # Toda consulta registrada es un `show`: no muta nada, así que reintentar
    # es seguro por construcción. El techo es bajo a propósito -- si el
    # terminal corrompe dos despachos seguidos, insistir no lo arregla.
    _READ_ONLY_DISPATCH_ATTEMPTS = 3

    def execute(
        self,
        device_name: str,
        query_id: OperationalQueryId,
        *,
        interface: str = "",
    ) -> IosCommandResult:
        """Despacha una consulta registrada, reintentando sólo corrupción probada."""
        attempts = 1
        result = self._execute_once(device_name, query_id, interface=interface)
        while (
            attempts < self._READ_ONLY_DISPATCH_ATTEMPTS
            and self._is_retryable_corruption(result)
        ):
            attempts += 1
            result = self._execute_once(device_name, query_id, interface=interface)
        return replace(result, dispatch_attempts=attempts)

    @staticmethod
    def _is_retryable_corruption(result: IosCommandResult) -> bool:
        """Exige dos pruebas, no una, antes de reintentar.

        El eco demuestra que el comando llegó corrompido, y el rechazo de IOS
        demuestra que ese comando corrompido no surtió efecto. Sin la segunda,
        reintentar sería reejecutar algo cuyo efecto no se conoce.
        """
        if not is_command_corrupted(DispatchClassification(result.dispatch_classification)):
            return False
        return ios_rejection_reason(result.output) is not None

    def _execute_once(
        self,
        device_name: str,
        query_id: OperationalQueryId,
        *,
        interface: str = "",
    ) -> IosCommandResult:
        started = monotonic()
        try:
            command = self._registered_command(query_id, interface=interface)
        except ValueError as exc:
            return IosCommandResult(
                device_name,
                query_id,
                False,
                failure_reason=str(exc),
                duration_ms=int((monotonic() - started) * 1000),
            )
        name, command_json = json.dumps(device_name), json.dumps(command)
        session = self._prepare_session(name)
        if session is not IosSessionState.EXEC_PROMPT_READY:
            return IosCommandResult(device_name, query_id, False, failure_reason="IOS session state: " + session.value, duration_ms=int((monotonic() - started) * 1000), session_state=session)
        restore_user_mode = False
        if query_id in _PRIVILEGED_QUERIES:
            current = self._terminal_state(name)
            if str(current.get("prompt") or "").strip().endswith(">"):
                if not self._enter(name, "enable") or not self._wait_for(
                    name,
                    lambda state: str(state.get("prompt") or "").strip().endswith("#"),
                ):
                    return IosCommandResult(
                        device_name, query_id, False,
                        failure_reason="IOS privileged EXEC mode was unavailable.",
                        duration_ms=int((monotonic() - started) * 1000),
                        session_state=session,
                    )
                restore_user_mode = True

        def complete(result: IosCommandResult) -> IosCommandResult:
            if restore_user_mode:
                self._enter(name, "disable")
            return result

        js = "".join((
            "try{var d=ipc.network().getDevice(", name, ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
            "if(!t||typeof t.enterCommand!=='function'||typeof t.getOutput!=='function'){reportResult(JSON.stringify({ok:false,reason:'IOS terminal unavailable'}));}",
            "else{var before=String(t.getOutput());",
            _PAGER_GUARD_JS,
            "if(__pager){reportResult(JSON.stringify({ok:false,reason:'prompt_not_ready:pager_active'}));}",
            "else{t.enterCommand(", command_json, ");",
            "reportResult(JSON.stringify({ok:true,before:before}));}}}catch(e){reportResult('ERROR:'+e);}",
        ))
        raw = self._send_and_wait(js, 10.0)
        elapsed = int((monotonic() - started) * 1000)
        if raw is None:
            return complete(IosCommandResult(device_name, query_id, False, failure_reason="IOS command submission timed out.", duration_ms=elapsed, session_state=session))
        if raw.startswith("ERROR:"):
            return complete(IosCommandResult(device_name, query_id, False, failure_reason=raw, duration_ms=elapsed, session_state=session))
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return complete(IosCommandResult(device_name, query_id, False, failure_reason="IOS terminal returned malformed JSON.", duration_ms=elapsed, session_state=session))
        if not state.get("ok"):
            reason = str(state.get("reason") or "IOS terminal unavailable.")
            refused = reason.startswith("prompt_not_ready")
            if refused:
                # El comando NO se envió: la guarda atómica lo impidió. Es un
                # fallo de barrera, no de la consulta, y no deja el terminal en
                # un estado ambiguo.
                self._pager_quarantine.add(name)
            return complete(IosCommandResult(
                device_name, query_id, False, failure_reason=reason,
                duration_ms=elapsed, session_state=session,
                dispatch_classification=(
                    DispatchClassification.PROMPT_NOT_READY.value if refused
                    else DispatchClassification.TRANSPORT_FAILED.value
                ),
            ))
        baseline = str(state.get("before") or "")
        def observe() -> dict:
            read_js = "".join((
                "try{var d=ipc.network().getDevice(", name, ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
                "var o=t&&typeof t.getOutput==='function'?String(t.getOutput()):'';",
                "reportResult(JSON.stringify({found:!!d,configuration_channel:o!==", json.dumps(baseline), ",output:o}));}",
                "catch(e){reportResult('ERROR:'+e);}",
            ))
            observed = self._send_and_wait(read_js, 3.0)
            if observed is None or observed.startswith("ERROR:"):
                return {"found": False, "failure_reason": observed or "IOS output timed out."}
            try:
                return json.loads(observed)
            except json.JSONDecodeError:
                return {"found": False, "failure_reason": "IOS output was malformed."}

        def attribute() -> dict:
            """Lee la salida Y atribuye la sesion en la MISMA enumeracion."""
            attribution_js = execution_attribution_js(name, baseline, command)
            attributed = self._send_and_wait(attribution_js, 5.0)
            if attributed is None or attributed.startswith("ERROR:"):
                return {"found": False}
            try:
                return json.loads(attributed)
            except json.JSONDecodeError:
                return {"found": False}

        convergence = StateConvergenceWaiter(observe, timeout_seconds=8.0).wait()
        elapsed = int((monotonic() - started) * 1000)
        attribution = attribute()
        output = str(attribution.get("output") or "")
        identity = classify_execution_identity(device_name, attribution)
        if (
            identity["device_identity_provenance"]
            == DeviceIdentityProvenance.MISMATCHED.value
        ):
            # La consulta corrio, pero sobre OTRO device. Devolver su salida
            # como evidencia del pedido seria exactamente la sustitucion que
            # esta barrera existe para impedir, asi que no se devuelve: ningun
            # consumidor puede certificar al device pedido con esto.
            return complete(IosCommandResult(
                device_name, query_id, False,
                failure_reason=(
                    f"DEVICE_PROVENANCE_MISMATCH: requested {device_name!r} but "
                    "the executing session is owned by "
                    f"{identity['observed_device_name']!r}."
                ),
                duration_ms=elapsed, session_state=session, **identity,
            ))
        window = extract_terminal_command_window(baseline, output, command)
        classification, echoed = classify_echo(command, window.output)
        capture = _PagerCapture.not_encountered(window.output, output)
        if _PAGER_MARKER in window.output:
            # PT 9.0.1 rejects ``terminal length 0``, so the pager is a real and
            # frequent state. Una consulta CUALIFICADA lo recorre hasta cerrar
            # una lectura logica; cualquier otra conserva el comportamiento de
            # siempre -- primera pagina como evidencia y truncada.
            # `is_command_corrupted` también decide acá: si el eco demuestra
            # que IOS recibió otra cosa, la identidad de la consulta ya no es la
            # cualificada y recorrer su pager sería recorrer el de otro comando.
            if (
                query_id in _PAGINATION_QUALIFIED_QUERIES
                and window.fresh
                and not is_command_corrupted(classification)
            ):
                capture = self._capture_registered_pages(
                    name, window=window.output, transcript=output,
                )
            else:
                capture = _PagerCapture.not_qualified(window.output, output)
        if not capture.complete:
            # Cancel the documented TerminalLine interaction so a paginated SHOW
            # cannot poison the next registered query. Vale igual para la
            # captura cualificada que fallo: lo que quedo a medias es
            # exactamente lo que hay que aislar.
            pager_isolated = self._cancel_pager(name, capture.transcript or output)
            if not pager_isolated:
                self._pager_quarantine.add(name)
                # `complete` también acá: sin esto, una cancelación de pager no
                # confirmada dejaba el device en EXEC privilegiado para siempre,
                # porque era el único retorno que no restauraba el modo.
                return complete(IosCommandResult(
                    device_name,
                    query_id,
                    False,
                    output=normalize_terminal_output(window.output),
                    failure_reason=(
                        "IOS pager cancellation could not be confirmed; "
                        "the terminal session remains isolated from new queries."
                    ),
                    duration_ms=elapsed,
                    session_state=IosSessionState.FAILED,
                    fresh_output_observed=window.fresh,
                    window_strategy=window.strategy,
                    truncated_by_pager=True,
                    pager_pages_captured=capture.pages,
                    pager_continuation=capture.continuation.value,
                    dispatch_classification=classification.value,
                    echo_observed=echoed,
                    **identity,
                ))
        if not convergence.configuration_channel:
            return complete(IosCommandResult(device_name, query_id, False, output=normalize_terminal_output(window.output), failure_reason="IOS command output did not converge.", duration_ms=elapsed, session_state=session, fresh_output_observed=window.fresh, window_strategy=window.strategy, truncated_by_pager=capture.truncated, pager_pages_captured=capture.pages, pager_continuation=capture.continuation.value, dispatch_classification=classification.value, echo_observed=echoed, **identity))
        if not window.fresh:
            return complete(IosCommandResult(device_name, query_id, False, failure_reason="No fresh current-command output window was observed.", duration_ms=elapsed, session_state=session, window_strategy=window.strategy, dispatch_classification=classification.value, echo_observed=echoed, **identity))
        if is_command_corrupted(classification):
            # NO se clasifica como consulta rechazada: IOS jamás recibió la
            # consulta pedida, así que su `% Invalid input` no habla de ella.
            return complete(IosCommandResult(
                device_name, query_id, False,
                output=normalize_terminal_output(window.output),
                failure_reason=(
                    f"COMMAND_DISPATCH_MISMATCH: requested {command!r} but the "
                    f"terminal echoed {echoed!r}."
                ),
                duration_ms=elapsed, session_state=session,
                fresh_output_observed=True, window_strategy=window.strategy,
                truncated_by_pager=capture.truncated,
                pager_pages_captured=capture.pages,
                pager_continuation=capture.continuation.value,
                dispatch_classification=classification.value,
                echo_observed=echoed,
                **identity,
            ))
        return complete(IosCommandResult(device_name, query_id, True, output=normalize_terminal_output(capture.output), failure_reason=capture.failure_reason, duration_ms=elapsed, session_state=session, fresh_output_observed=True, window_strategy=window.strategy, truncated_by_pager=capture.truncated, output_complete=capture.complete, pager_pages_captured=capture.pages, pager_continuation=capture.continuation.value, dispatch_classification=classification.value, echo_observed=echoed, **identity))

    @staticmethod
    def _registered_command(query_id: OperationalQueryId, *, interface: str) -> str:
        if query_id in _INTERFACE_COMMANDS:
            if not _INTERFACE_NAME.fullmatch(interface):
                raise ValueError("A registered interface query requires a valid interface name.")
            return _INTERFACE_COMMANDS[query_id].format(interface=interface)
        if interface:
            raise ValueError("This registered IOS query does not accept an interface.")
        return _COMMANDS[query_id]

    def _capture_registered_pages(
        self,
        name: str,
        *,
        window: str,
        transcript: str,
    ) -> _PagerCapture:
        """Recorre el pager hasta cerrar UNA lectura logica, o falla cerrado.

        Sólo la llaman las consultas de `_PAGINATION_QUALIFIED_QUERIES`. No
        recibe ni acepta ningún comando: la única interacción que emite es la
        tecla que el propio `--More--` consume, y toda la mecánica de páginas
        queda por debajo de quien pide la consulta.

        La captura es de sólo lectura de punta a punta y está atada a la misma
        página inicial: cada página nueva tiene que ser una continuación
        atribuible del transcript anterior, así que ninguna mutación ajena
        puede intercalarse dentro de la misma lectura lógica sin romper esa
        atribución -- y romperla es fallar, no continuar.
        """
        started = self._clock()
        # Identidad de sesión tomada al abrir la captura. `getPrompt()` puede
        # venir vacío mientras el pager está activo, y vacío NO es evidencia de
        # nada: sólo se rechaza cuando ambos prompts existen y difieren.
        session_prompt = str(self._terminal_state(name).get("prompt") or "").strip()
        assembled = drop_pager_prompt(window)
        current = transcript
        previous_page = ""
        pages = 1
        if not has_active_pager(current):
            return _PagerCapture.failed(
                assembled, pages, current,
                "IOS output carried a pager marker without an active pager to "
                "continue; the capture cannot be completed.",
            )
        while True:
            if pages >= _PAGER_MAX_PAGES:
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager continuation exceeded its bounded page limit "
                    f"of {_PAGER_MAX_PAGES}.",
                )
            remaining = _PAGER_CAPTURE_DEADLINE_SECONDS - (self._clock() - started)
            if remaining <= 0:
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager continuation exceeded its bounded deadline of "
                    f"{_PAGER_CAPTURE_DEADLINE_SECONDS:.0f}s.",
                )
            if not self._advance_pager(name):
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager continuation key was not delivered.",
                )
            state = self._await_pager_progress(
                name,
                current,
                timeout_seconds=min(_PAGER_PAGE_TIMEOUT_SECONDS, remaining),
            )
            if state is None:
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager produced no continuation page within the "
                    "bounded wait.",
                )
            if not state.get("found") or not state.get("terminal"):
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager continuation lost the device terminal.",
                )
            prompt = str(state.get("prompt") or "").strip()
            if session_prompt and prompt and prompt != session_prompt:
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager continuation observed a different terminal "
                    f"session: {session_prompt!r} became {prompt!r}.",
                )
            after = str(state.get("output") or "")
            page = fresh_command_window(current, after)
            if not page.fresh:
                # El transcript no continúa al anterior: rodó más allá de todo
                # anclaje o pertenece a otra sesión. Pegarlo igual sería
                # reconstruir una lectura con un agujero adentro.
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager continuation window could not be attributed to "
                    f"this capture ({page.strategy.value}).",
                )
            captured = drop_pager_prompt(page.output)
            if not captured.strip():
                return _PagerCapture.failed(
                    assembled, pages, after,
                    "IOS pager continuation produced no new output.",
                )
            if captured == previous_page:
                return _PagerCapture.failed(
                    assembled, pages, after,
                    "IOS pager continuation repeated the same page without "
                    "progress.",
                )
            assembled += captured
            previous_page = captured
            current = after
            pages += 1
            if len(assembled) > _PAGER_MAX_BYTES:
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager continuation exceeded its bounded byte limit "
                    f"of {_PAGER_MAX_BYTES}.",
                )
            if has_active_pager(after):
                continue
            if not terminal_is_idle(after):
                # Ni pager ni prompt: no hay forma de saber si la salida
                # terminó. Un final ambiguo no es un final.
                return _PagerCapture.failed(
                    assembled, pages, current,
                    "IOS pager continuation ended without a command prompt.",
                )
            return _PagerCapture.completed(assembled, pages, current)

    def _await_pager_progress(
        self,
        name: str,
        previous: str,
        *,
        timeout_seconds: float,
    ) -> dict | None:
        """Espera observable a la página siguiente; nunca un sleep a ciegas."""
        last: dict = {}

        def inspect() -> dict:
            nonlocal last
            state = self._terminal_state(name)
            state["configuration_channel"] = (
                str(state.get("output") or "") != previous
            )
            last = state
            return state

        converged = StateConvergenceWaiter(
            inspect,
            timeout_seconds=timeout_seconds,
            clock=self._clock,
            sleeper=self._sleeper,
        ).wait()
        return last if converged.configuration_channel else None

    def _advance_pager(self, name: str) -> bool:
        """Entrega al `--More--` la única tecla que consume, y nada más.

        Es la misma interacción documentada de `TerminalLine` que ya usa
        `_cancel_pager`, con otra tecla. No es un comando: el pager se come el
        carácter antes de que llegue al CLI -- la mecánica que este repositorio
        midió al ver un despacho perder su primer carácter -- así que esto no
        abre ninguna vía de IOS crudo.
        """
        js = (
            "try{var d=ipc.network().getDevice(" + name + ");"
            "var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;"
            "if(!t||typeof t.enterCommand!=='function'){reportResult('{\"ok\":false}');}"
            "else{t.enterCommand(" + _PAGER_CONTINUATION_KEY + ");"
            "reportResult('{\"ok\":true}');}}catch(e){reportResult('ERROR:'+e);}"
        )
        return self._send_and_wait(js, 5.0) == '{"ok":true}'

    def _cancel_pager(self, name: str, paged_output: str) -> bool:
        js = "try{var d=ipc.network().getDevice(" + name + ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;if(!t||typeof t.enterCommand!=='function'){reportResult('{\"ok\":false}');}else{t.enterCommand(String.fromCharCode(3));reportResult('{\"ok\":true}');}}catch(e){reportResult('ERROR:'+e);}"
        if self._send_and_wait(js, 5.0) != '{"ok":true}':
            return False
        return self._wait_for(
            name,
            lambda state: (
                self._is_exec_prompt(state)
                and str(state.get("output") or "") != paged_output
                and not _has_active_pager(str(state.get("output") or ""))
            ),
        )

    def _prepare_session(self, name: str) -> IosSessionState:
        state = self._terminal_state(name)
        if not state.get("found") or not state.get("terminal"):
            return IosSessionState.FAILED
        if state.get("booting") is True:
            return IosSessionState.WAITING_FOR_BOOT
        if name in self._pager_quarantine or _has_active_pager(
            str(state.get("output") or ""),
        ):
            if not self._cancel_pager(name, str(state.get("output") or "")):
                self._pager_quarantine.add(name)
                return IosSessionState.FAILED
            self._pager_quarantine.discard(name)
            state = self._terminal_state(name)
            if _has_active_pager(str(state.get("output") or "")):
                self._pager_quarantine.add(name)
                return IosSessionState.FAILED
        content = (str(state.get("prompt") or "") + "\n" + str(state.get("output") or "")).casefold()
        if self._is_exec_prompt(state):
            return IosSessionState.EXEC_PROMPT_READY
        if _SETUP_DIALOG in content:
            if not self._enter(name, "no"):
                return IosSessionState.FAILED
            if not self._wait_for(name, lambda current: "press return to get started" in str(current.get("output") or "").casefold()):
                return IosSessionState.TIMEOUT
            if not self._enter(name, ""):
                return IosSessionState.FAILED
            return IosSessionState.EXEC_PROMPT_READY if self._wait_for(name, self._is_exec_prompt) else IosSessionState.TIMEOUT
        if "press return to get started" in content:
            if not self._enter(name, ""):
                return IosSessionState.FAILED
            return IosSessionState.EXEC_PROMPT_READY if self._wait_for(name, self._is_exec_prompt) else IosSessionState.TIMEOUT
        return IosSessionState.FAILED

    @staticmethod
    def _is_exec_prompt(state: dict) -> bool:
        prompt = str(state.get("prompt") or "").strip()
        # getOutput() conserva el transcript completo, incluso el setup dialog
        # ya terminado. El prompt actual es la señal operacional; reinterpretar
        # el histórico como estado presente impedía llegar a Router>/Router#.
        return bool(prompt and prompt.endswith((">", "#")) and _SETUP_DIALOG not in prompt.casefold())

    def _enter(self, name: str, command: str) -> bool:
        """Transición de modo (`enable`/`disable`) o respuesta al setup dialog.

        Lleva la misma guarda atómica que el despacho de consultas: un `enable`
        que llega como `nable` deja la sesión en un estado que después se lee
        como "modo privilegiado no disponible", ocultando la causa real.
        `_cancel_pager` queda deliberadamente fuera: ahí la tecla que el pager
        consume es justamente lo que se quiere entregar.
        """
        js = (
            "try{var d=ipc.network().getDevice(" + name + ");"
            "var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;"
            "if(!t||typeof t.enterCommand!=='function'){reportResult('{\"ok\":false}');}"
            "else{var before=String(t.getOutput());"
            + _PAGER_GUARD_JS +
            "if(__pager){reportResult('{\"ok\":false,\"reason\":\"pager_active\"}');}"
            "else{t.enterCommand(" + json.dumps(command) + ");"
            "reportResult('{\"ok\":true}');}}}catch(e){reportResult('ERROR:'+e);}"
        )
        response = self._send_and_wait(js, 5.0)
        return response == '{"ok":true}'

    def _terminal_state(self, name: str) -> dict:
        js = "try{var d=ipc.network().getDevice(" + name + ");var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;reportResult(JSON.stringify({found:!!d,booting:d&&typeof d.isBooting==='function'?!!d.isBooting():null,terminal:!!t,terminal_available:!!t,terminal_kind:'ios_command_line',prompt:t&&typeof t.getPrompt==='function'?String(t.getPrompt()):'',output:t&&typeof t.getOutput==='function'?String(t.getOutput()):''}));}catch(e){reportResult('ERROR:'+e);}"
        raw = self._send_and_wait(js, 3.0)
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}

    def _wait_for(self, name: str, predicate: Callable[[dict], bool]) -> bool:
        def inspect() -> dict:
            current = self._terminal_state(name)
            current["configuration_channel"] = predicate(current)
            return current
        return StateConvergenceWaiter(inspect, timeout_seconds=8.0).wait().configuration_channel
