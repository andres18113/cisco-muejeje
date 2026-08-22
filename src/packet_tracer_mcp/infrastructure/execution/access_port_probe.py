"""Descubre qué observadores de puerto expone ESTE build, sin adivinar ninguno.

`AGENTS.md` regla 6 prohíbe escribir código sobre una firma de la API de Packet
Tracer que este repositorio no haya confirmado. `TD-ACCESSPORT-READBACK-001`
pide exactamente eso y por eso sigue abierta desde run 5: nadie sabe si PT
expone un getter de VLAN de acceso, y escribir un parser para una salida que
nadie capturó sería el mismo error en otro sitio.

Este módulo resuelve la pregunta en vez de asumirla. Hace dos cosas y ninguna
más:

1. **Descubrimiento.** Para una lista de nombres candidatos, reporta cuáles son
   funciones (`typeof x === 'function'`). Preguntar por un nombre no es
   llamarlo: un nombre ausente sale ausente y no rompe nada.
2. **Lectura controlada.** Sólo para los nombres que resultaron ser funciones,
   y sólo si empiezan por `get`/`is`/`has` -- la convención de lectura de PT --,
   los invoca sin argumentos dentro de su propio `try`. Un setter jamás se
   llama.

Lo que devuelve es un mapa de descubrimiento, no una capacidad. Que un getter
exista no dice que su valor signifique lo que su nombre sugiere: eso lo decide
el control positivo/negativo de la pasada de cualificación, comparando contra
un puerto cuyo estado configurado se conoce.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

#: Sólo se invoca lo que se lee como lectura. Un nombre que no case con esto se
#: reporta como presente y NO se llama.
_READ_ONLY_NAME = re.compile(r"^(get|is|has)[A-Z]")

#: Candidatos sobre el objeto puerto. La lista es deliberadamente amplia: el
#: coste de preguntar por un nombre inexistente es cero, y el coste de no
#: preguntar es dejar la deuda abierta otra fase más.
PORT_OBSERVER_CANDIDATES = (
    # Confirmados por enumeración sobre `SwitchPort` en PT 9.0.1.0858. Los
    # nombres que la enumeración NO devolvió se mantienen en la lista: que un
    # build los expusiera sería información, y preguntar cuesta cero.
    "getAccessVlan", "isAccessPort", "getAdminOpMode", "isAdminModeSet",
    "getNativeVlanId", "getVoipVlanId", "isPortUp", "isProtocolUp",
    "getPower", "isPowerOn",
    "getPortNameNumber", "getType", "getClassName",
    "getName", "getMacAddress", "getBandwidth",
    "getVlanId", "getVlan", "getVlanNumber", "getSwitchportMode", "getPortMode",
)

#: Candidatos sobre el `VlanManager` del switch. `getVlanIntCount` ya está
#: confirmado en este repositorio; su pareja `...At(i)` es el idioma que PT usa
#: en todos los demás pares (`getVlanCount`/`getVlanAt`,
#: `getPortCount`/`getPortAt`), pero seguirlo sería inferir, así que se
#: pregunta.
VLAN_MANAGER_OBSERVER_CANDIDATES = (
    "getVlanIntCount", "getVlanIntAt", "getVlanInterfaceAt", "getVlanInterfaceCount",
    "getPortVlan", "getVlanForPort", "getVlanOfPort", "getAccessVlanForPort",
    "getVlanCount", "getVlanAt", "getMaxVlans",
)


@dataclass(frozen=True)
class ObserverProbe:
    """Un nombre candidato y lo que se pudo establecer sobre él."""

    name: str
    present: bool = False
    is_callable: bool = False
    invoked: bool = False
    value: object = None
    error: str = ""


@dataclass(frozen=True)
class PortObserverDiscovery:
    """El resultado de una pasada de descubrimiento sobre UN puerto."""

    device_found: bool = False
    port_found: bool = False
    interface: str = ""
    port_class_name: str = ""
    owner_device_name: str = ""
    enumerated_members: tuple[str, ...] = ()
    port_observers: tuple[ObserverProbe, ...] = ()
    vlan_manager_present: bool = False
    vlan_manager_observers: tuple[ObserverProbe, ...] = ()
    error: str = ""

    @property
    def readable_port_observers(self) -> tuple[ObserverProbe, ...]:
        return tuple(item for item in self.port_observers if item.invoked)

    @property
    def readable_vlan_manager_observers(self) -> tuple[ObserverProbe, ...]:
        return tuple(item for item in self.vlan_manager_observers if item.invoked)


class PacketTracerAccessPortProbe:
    """Introspección de sólo lectura sobre un puerto ya existente."""

    def __init__(self, send_and_wait: Callable[[str, float], str | None]) -> None:
        self._send_and_wait = send_and_wait

    def discover_port_observers(
        self, device_name: str, interface: str, *, timeout: float = 12.0,
    ) -> PortObserverDiscovery:
        device = json.dumps(device_name)
        port = json.dumps(interface)
        port_names = json.dumps(list(PORT_OBSERVER_CANDIDATES))
        vlan_names = json.dumps(list(VLAN_MANAGER_OBSERVER_CANDIDATES))
        readable_port = json.dumps(list(_readable(PORT_OBSERVER_CANDIDATES)))
        readable_vlan = json.dumps(list(_readable(VLAN_MANAGER_OBSERVER_CANDIDATES)))
        js = "".join((
            "try{var __d=ipc.network().getDevice(", device, ");",
            "if(!__d){reportResult(JSON.stringify({device_found:false}));}else{",
            "var __p=(typeof __d.getPort==='function')?__d.getPort(", port, "):null;",
            "var __members=[];try{for(var __k in __p){__members.push(String(__k));}}catch(__me){}",
            "var __cls='';try{__cls=String(__p.getClassName());}catch(__ce){__cls='';}",
            # La identidad del device se lee del PROPIO puerto, no del nombre
            # con el que se pidió: es lo que ata la lectura al objeto observado.
            "var __own='';try{__own=String(__p.getOwnerDevice().getName());}catch(__oe){__own='';}",
            # Presencia: preguntar por un nombre nunca lo ejecuta.
            "var __probe=function(__o,__names,__read){var __out=[];",
            "for(var __i=0;__i<__names.length;__i++){var __n=__names[__i];var __row={name:__n,",
            "present:false,is_callable:false,invoked:false,value:null,error:''};",
            "try{__row.present=(__o!==null&&__o!==undefined&&(__n in __o));}catch(__pe){}",
            "try{__row.is_callable=(__o!==null&&__o!==undefined&&typeof __o[__n]==='function');}catch(__te){}",
            "if(__row.is_callable&&__read.indexOf(__n)>=0){",
            "try{var __v=__o[__n]();__row.invoked=true;",
            "__row.value=(__v===null||__v===undefined)?null:((typeof __v==='object')?String(__v):__v);}",
            "catch(__ie){__row.error=String(__ie);}}",
            "__out.push(__row);}return __out;};",
            "var __ports=__probe(__p,", port_names, ",", readable_port, ");",
            "var __vm=(typeof __d.getProcess==='function')?__d.getProcess('VlanManager'):null;",
            "var __vms=__probe(__vm,", vlan_names, ",", readable_vlan, ");",
            "reportResult(JSON.stringify({device_found:true,port_found:!!__p,",
            "port_class_name:__cls,owner_device_name:__own,",
            "members:__members,port_observers:__ports,",
            "vlan_manager_present:!!__vm,vlan_manager_observers:__vms}));}}",
            "catch(__e){reportResult('ERROR:'+__e);}",
        ))
        try:
            data = self._json_result(js, timeout)
        except Exception as exc:  # noqa: BLE001 - la pasada reporta, no decide
            return PortObserverDiscovery(
                interface=interface, error=f"{type(exc).__name__}: {exc}",
            )
        return PortObserverDiscovery(
            device_found=bool(data.get("device_found")),
            port_found=bool(data.get("port_found")),
            interface=interface,
            port_class_name=str(data.get("port_class_name") or ""),
            owner_device_name=str(data.get("owner_device_name") or ""),
            enumerated_members=tuple(
                str(item) for item in data.get("members", []) or ()
            ),
            port_observers=_rows(data.get("port_observers")),
            vlan_manager_present=bool(data.get("vlan_manager_present")),
            vlan_manager_observers=_rows(data.get("vlan_manager_observers")),
        )

    def _json_result(self, js: str, timeout: float) -> dict:
        raw = self._send_and_wait(js, timeout)
        if raw is None:
            raise TimeoutError("Packet Tracer did not respond before the probe timeout.")
        if raw.startswith(("ERROR:", "PT_ERROR:")):
            raise RuntimeError(raw.split(":", 1)[1].strip())
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError("Packet Tracer returned a non-object probe response.")
        return value


def _readable(names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if _READ_ONLY_NAME.match(name))


def _rows(value: object) -> tuple[ObserverProbe, ...]:
    if not isinstance(value, list):
        return ()
    rows: list[ObserverProbe] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(ObserverProbe(
            name=str(item.get("name", "")),
            present=bool(item.get("present")),
            is_callable=bool(item.get("is_callable")),
            invoked=bool(item.get("invoked")),
            value=item.get("value"),
            error=str(item.get("error") or ""),
        ))
    return tuple(rows)


#: Nombres de proceso candidatos para la telefonía. `VlanManager` es el único
#: confirmado en este repositorio, así que todo lo demás se PREGUNTA. Pedir un
#: proceso inexistente devuelve null y no rompe nada.
TELEPHONY_PROCESS_CANDIDATES = (
    "TelephonyService", "CallManager", "CME", "CallManagerExpress",
    "VoIPService", "Telephony", "SipServer", "TftpServer", "VlanManager",
)


@dataclass(frozen=True)
class DeviceObserverDiscovery:
    """Qué expone un dispositivo, y qué procesos responden por nombre."""

    device_found: bool = False
    device_class_name: str = ""
    enumerated_members: tuple[str, ...] = ()
    processes_present: tuple[str, ...] = ()
    process_members: dict[str, tuple[str, ...]] = None  # type: ignore[assignment]
    error: str = ""

    def __post_init__(self) -> None:
        if self.process_members is None:
            object.__setattr__(self, "process_members", {})


def _device_discovery_js(device_name: str, process_candidates: tuple[str, ...]) -> str:
    """Recibe los valores CRUDOS y los codifica acá dentro.

    La primera versión tomaba texto JS ya codificado, igual de correcta en su
    único llamador y una trampa para el segundo: pasar un nombre sin codificar
    por esa firma es ejecución de código, y la firma no avisaba.
    """
    device = json.dumps(device_name)
    process_names = json.dumps(list(process_candidates))
    return "".join((
        "try{var __d=ipc.network().getDevice(", device, ");",
        "if(!__d){reportResult(JSON.stringify({device_found:false}));}else{",
        "var __m=[];try{for(var __k in __d){__m.push(String(__k));}}catch(__me){}",
        "var __cls='';try{__cls=String(__d.getClassName());}catch(__ce){__cls='';}",
        "var __names=", process_names, ";var __present=[];var __members={};",
        "for(var __i=0;__i<__names.length;__i++){var __p=null;",
        "try{__p=(typeof __d.getProcess==='function')?__d.getProcess(__names[__i]):null;}",
        "catch(__pe){__p=null;}",
        "if(__p){__present.push(__names[__i]);var __pm=[];",
        "try{for(var __q in __p){__pm.push(String(__q));}}catch(__qe){}",
        "__members[__names[__i]]=__pm;}}",
        "reportResult(JSON.stringify({device_found:true,device_class_name:__cls,",
        "members:__m,processes_present:__present,process_members:__members}));}}",
        "catch(__e){reportResult('ERROR:'+__e);}",
    ))


def discover_device_observers(
    send_and_wait: Callable[[str, float], str | None],
    device_name: str,
    *,
    process_candidates: tuple[str, ...] = TELEPHONY_PROCESS_CANDIDATES,
    timeout: float = 12.0,
) -> DeviceObserverDiscovery:
    """Enumera los miembros de un dispositivo y qué procesos responden.

    Misma disciplina que `discover_port_observers`: preguntar por un nombre no
    lo ejecuta, y un proceso ausente sale ausente. Existe porque decidir que
    algo es INOBSERVABLE exige haber buscado, y buscar sin adivinar firmas es
    justamente lo que `AGENTS.md` regla 6 pide.
    """
    probe = PacketTracerAccessPortProbe(send_and_wait)
    js = _device_discovery_js(device_name, process_candidates)
    try:
        data = probe._json_result(js, timeout)  # noqa: SLF001 - mismo módulo
    except Exception as exc:  # noqa: BLE001 - la pasada reporta, no decide
        return DeviceObserverDiscovery(error=f"{type(exc).__name__}: {exc}")
    # El backend responde lo que responde: si `process_members` no viniera como
    # objeto, tratarlo como mapa reventaría FUERA del try que protege al resto.
    members = data.get("process_members")
    if not isinstance(members, dict):
        members = {}
    return DeviceObserverDiscovery(
        device_found=bool(data.get("device_found")),
        device_class_name=str(data.get("device_class_name") or ""),
        enumerated_members=tuple(str(item) for item in data.get("members", []) or ()),
        processes_present=tuple(
            str(item) for item in data.get("processes_present", []) or ()
        ),
        process_members={
            str(key): tuple(str(item) for item in value or ())
            for key, value in (members or {}).items()
        },
    )
