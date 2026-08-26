"""Descubre qué expone un `frameInstance` de Simulación en ESTE build.

CP-SCALE Floor 1 quedó atascado en una pregunta que ninguna superficie actual
responde: el DHCP Discover de PHONE-02 y la BPDU de configuración que sale por
el MISMO puerto físico de ese teléfono, ¿llevan identidad de VLAN distinta? El
texto de decisión de Packet Tracer nunca nombra una VLAN -- dice "the active
VLAN interface" y nada más --, así que hay que preguntarle al objeto.

`AGENTS.md` regla 6 prohíbe escribir código sobre una firma de la API de PT que
este repositorio no haya confirmado, y el contrato de campos que
`SimulationTraceRuntime` documenta es el que ESE módulo usa, no una enumeración
exhaustiva del objeto. De la ausencia de un getter de VLAN en esa lista no se
sigue que PT no lo exponga. Este módulo resuelve la diferencia en vez de
asumirla, con la misma disciplina que `access_port_probe`:

1. **Descubrimiento.** Enumera los NOMBRES de los miembros del frame y la forma
   de cada uno (`typeof`, si es invocable, su aridad declarada). Preguntar por
   un nombre no es llamarlo.
2. **Atribución.** Invoca únicamente los getters que este repositorio YA midió
   sobre `frameInstance` -- `getDevice`, `getInPort`, `getStartSimTime`,
   `getUserTrafficType` -- y sólo para probar que el índice sigue nombrando el
   frame que se eligió. Ningún miembro descubierto se invoca en esta pasada.

Lo que devuelve es un mapa de descubrimiento, no una capacidad. Que exista un
nombre no dice qué significa su valor: eso lo decide después un control
positivo/negativo contra un frame cuya VLAN se conozca por otra vía.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

#: Cotas duras de UNA enumeración. Existen para que el descubrimiento no pueda
#: convertirse en un volcado del objeto ni en una respuesta sin techo.
MAX_FRAME_TARGETS = 4
MAX_MEMBER_NAMES = 128
MAX_MEMBER_NAME_LENGTH = 64

#: Los DOS unicos nombres que esta fase puede invocar, medidos sobre
#: `frameInstance` en el build exacto: ambos `function`, aridad declarada 0.
#: Que sean invocables NO dice que devuelvan un PDU -- eso es justo lo que esta
#: enumeracion va a observar. Se escriben literales en el script: elegir un
#: nombre de una lista en tiempo de ejecucion seria el invocador generico que
#: este modulo existe para no tener, y el objeto expone mutadores.
CHILD_FRAME_GETTERS = ("getInFrame", "getOutFrame")
MAX_CHILD_OBJECTS_PER_FRAME = 2

#: Convención de lectura de PT, igual que en `access_port_probe`. Sólo se usa
#: para CLASIFICAR lo descubierto; en esta fase no se invoca ninguno.
_READ_ONLY_NAME = re.compile(r"^(get|is|has)[A-Z]")


@dataclass(frozen=True)
class FrameMemberProbe:
    """Un miembro del frame: su nombre y su forma, nunca su valor."""

    name: str
    type_name: str = ""
    is_callable: bool = False
    #: `Function.prototype.length`: cuántos argumentos DECLARA. Se lee como
    #: propiedad, no se llama nada para obtenerla.
    arity: int | None = None

    @property
    def read_only_name(self) -> bool:
        """Si su nombre sigue la convención de lectura. No es permiso todavía."""
        return bool(_READ_ONLY_NAME.match(self.name))


@dataclass(frozen=True)
class FrameChildDiscovery:
    """Lo que devolvio UNO de los dos getters medidos, y su forma."""

    getter: str
    invoked: bool = False
    returned_null: bool = False
    type_name: str = ""
    error: str = ""
    members: tuple[str, ...] = ()
    observers: tuple[FrameMemberProbe, ...] = ()
    truncated: bool = False

    def candidates(self, needles: Iterable[str]) -> tuple[str, ...]:
        """Nombres que MERECEN mirarse, no nombres que prueben algo.

        Coincidir con `vlan` no hace que un getter devuelva una VLAN. Esto es
        una ayuda de descubrimiento y su resultado no entra en ninguna
        afirmacion sobre el trafico.
        """
        wanted = tuple(str(item).casefold() for item in needles)
        return tuple(
            item.name for item in self.observers
            if any(needle in item.name.casefold() for needle in wanted)
        )


@dataclass(frozen=True)
class FrameInstanceDiscovery:
    """Lo enumerado sobre UN frame, junto con la prueba de que es ese frame."""

    index: int
    in_bounds: bool = False
    frame_found: bool = False
    #: Atribución leída con getters YA medidos. Sin esto, el índice sería una
    #: promesa: el event list puede haber cambiado entre la captura y esta
    #: lectura, y enumerar otro frame sería exactamente la sustitución que esta
    #: comprobación existe para impedir.
    observed_device: str = ""
    observed_in_port: str = ""
    observed_sim_time: int | None = None
    observed_traffic_type: int | None = None
    members: tuple[str, ...] = ()
    observers: tuple[FrameMemberProbe, ...] = ()
    #: La enumeración tocó una cota. Lo capturado sigue siendo evidencia; lo que
    #: no se puede es leer la lista como completa.
    truncated: bool = False
    #: Lo devuelto por cada uno de los dos getters medidos. Ningun miembro
    #: descubierto aca se invoca en esta pasada.
    children: tuple[FrameChildDiscovery, ...] = ()
    failure_reason: str = ""

    def matches(
        self, *, device: str = "", sim_time: int | None = None,
        traffic_type: int | None = None,
    ) -> bool:
        """True sólo si cada dimensión pedida fue observada e igual."""
        if not self.frame_found:
            return False
        if device and self.observed_device != device:
            return False
        if sim_time is not None and self.observed_sim_time != sim_time:
            return False
        return not (
            traffic_type is not None and self.observed_traffic_type != traffic_type
        )


@dataclass(frozen=True)
class FrameObserverDiscovery:
    """El resultado de una enumeración acotada, o por qué no hubo ninguna."""

    observed: bool = False
    simulation_mode: bool = False
    frame_count: int = 0
    frames: tuple[FrameInstanceDiscovery, ...] = field(default_factory=tuple)
    failure_reason: str = ""


def _discovery_js(indices: tuple[int, ...]) -> str:
    """El script de UNA enumeración acotada.

    Sólo se llaman getters medidos, y sólo sobre el frame. Los miembros
    descubiertos se leen como propiedad (`typeof`), nunca se invocan: no hay
    ninguna forma `obj[name]()` en este script, y esa ausencia es parte del
    contrato que su regresión comprueba.
    """
    targets = json.dumps(list(indices))
    return (
        "try {"
        "  var __s = ipc.simulation();"
        "  if (!__s || typeof __s.isSimulationMode !== 'function') {"
        "    reportResult(JSON.stringify({observed:false,"
        "      failure_reason:'Packet Tracer exposed no simulation object.'}));"
        "  } else if (!__s.isSimulationMode()) {"
        "    reportResult(JSON.stringify({observed:true,simulation_mode:false,"
        "      frame_count:0,frames:[]}));"
        "  } else {"
        f"    var __want = {targets};"
        f"    var __maxNames = {MAX_MEMBER_NAMES};"
        f"    var __maxLen = {MAX_MEMBER_NAME_LENGTH};"
        # Enumera NOMBRES y forma. Lee propiedades; no invoca ninguna.
        "    var __enum = function (__o) {"
        "      var __names = []; var __cut = false;"
        "      try {"
        "        for (var __k in __o) {"
        "          if (__names.length >= __maxNames) { __cut = true; break; }"
        "          __names.push(String(__k).substring(0, __maxLen));"
        "        }"
        "      } catch (__ke) {}"
        "      var __rows = [];"
        "      for (var __m = 0; __m < __names.length; __m++) {"
        "        var __name = __names[__m];"
        "        var __row = {name:__name,type_name:'',is_callable:false,arity:null};"
        "        try {"
        "          var __v = __o[__name];"
        "          __row.type_name = typeof __v;"
        "          __row.is_callable = (typeof __v === 'function');"
        "          if (__row.is_callable && typeof __v.length === 'number') {"
        "            __row.arity = __v.length;"
        "          }"
        "        } catch (__ve) { __row.type_name = 'unreadable'; }"
        "        __rows.push(__row);"
        "      }"
        "      return {members:__names,observers:__rows,truncated:__cut};"
        "    };"
        # Forma de lo devuelto por UN getter medido, sin volcar el objeto.
        "    var __shape = function (__name, __c, __err) {"
        "      var __row = {getter:__name,invoked:(__err===''),returned_null:false,"
        "        type_name:'',error:__err,members:[],observers:[],truncated:false};"
        "      if (__err !== '') { return __row; }"
        "      __row.type_name = typeof __c;"
        "      if (__c === null || __c === undefined) {"
        "        __row.returned_null = true; return __row;"
        "      }"
        "      if (typeof __c === 'object' || typeof __c === 'function') {"
        "        var __e = __enum(__c);"
        "        __row.members = __e.members; __row.observers = __e.observers;"
        "        __row.truncated = __e.truncated;"
        "      }"
        "      return __row;"
        "    };"
        "    var __n = __s.getFrameInstanceCount();"
        "    var __frames = [];"
        "    for (var __t = 0; __t < __want.length; __t++) {"
        "      var __i = __want[__t];"
        "      if (__i < 0 || __i >= __n) {"
        "        __frames.push({index:__i,in_bounds:false,frame_found:false});"
        "        continue;"
        "      }"
        "      var __f = null;"
        "      try { __f = __s.getFrameInstanceAt(__i); } catch (__fe) { __f = null; }"
        "      if (!__f) {"
        "        __frames.push({index:__i,in_bounds:true,frame_found:false});"
        "        continue;"
        "      }"
        # Atribución con getters medidos. Cada uno en su try: un frame en
        # buffer no tiene puerto de entrada y eso no invalida la enumeracion.
        "      var __dev = '';"
        "      try { var __d = __f.getDevice(); __dev = __d ? String(__d.getName()) : ''; }"
        "      catch (__de) { __dev = ''; }"
        "      var __port = '';"
        "      try { var __p = __f.getInPort(); __port = __p ? String(__p.getName()) : ''; }"
        "      catch (__pe) { __port = ''; }"
        "      var __time = null;"
        "      try { __time = __f.getStartSimTime(); } catch (__te) { __time = null; }"
        "      var __type = null;"
        "      try { __type = __f.getUserTrafficType(); } catch (__ye) { __type = null; }"
        # Enumeracion del frame: SOLO nombres y forma, acotada.
        "      var __own = __enum(__f);"
        # Los DOS getters medidos, escritos literales, cada uno en su try. Es
        # todo lo que esta fase invoca sobre el frame ademas de la atribucion.
        "      var __kids = [];"
        "      var __c1 = null; var __e1 = '';"
        "      try { __c1 = __f.getInFrame(); } catch (__x1) { __e1 = String(__x1); }"
        "      __kids.push(__shape('getInFrame', __c1, __e1));"
        "      var __c2 = null; var __e2 = '';"
        "      try { __c2 = __f.getOutFrame(); } catch (__x2) { __e2 = String(__x2); }"
        "      __kids.push(__shape('getOutFrame', __c2, __e2));"
        "      __frames.push({index:__i,in_bounds:true,frame_found:true,"
        "        observed_device:__dev,observed_in_port:__port,"
        "        observed_sim_time:__time,observed_traffic_type:__type,"
        "        members:__own.members,observers:__own.observers,"
        "        truncated:__own.truncated,children:__kids});"
        "    }"
        "    reportResult(JSON.stringify({observed:true,simulation_mode:true,"
        "      frame_count:__n,frames:__frames}));"
        "  }"
        "} catch (__e) { reportResult('ERROR:' + __e); }"
    )


def _member_rows(value: object) -> tuple[FrameMemberProbe, ...]:
    rows: list[FrameMemberProbe] = []
    for item in value if isinstance(value, list) else ():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        arity = item.get("arity")
        rows.append(FrameMemberProbe(
            name=name,
            type_name=str(item.get("type_name") or ""),
            is_callable=bool(item.get("is_callable")),
            arity=int(arity) if isinstance(arity, (int, float)) else None,
        ))
    return tuple(rows)


def _child_rows(value: object) -> tuple[FrameChildDiscovery, ...]:
    rows: list[FrameChildDiscovery] = []
    for item in value if isinstance(value, list) else ():
        if not isinstance(item, dict):
            continue
        rows.append(FrameChildDiscovery(
            getter=str(item.get("getter") or ""),
            invoked=bool(item.get("invoked")),
            returned_null=bool(item.get("returned_null")),
            type_name=str(item.get("type_name") or ""),
            error=str(item.get("error") or ""),
            members=tuple(str(name) for name in item.get("members", []) or ()),
            observers=_member_rows(item.get("observers")),
            truncated=bool(item.get("truncated")),
        ))
    return tuple(rows)


def _frame_rows(value: object) -> tuple[FrameInstanceDiscovery, ...]:
    frames: list[FrameInstanceDiscovery] = []
    for item in value if isinstance(value, list) else ():
        if not isinstance(item, dict):
            continue
        raw_time = item.get("observed_sim_time")
        raw_type = item.get("observed_traffic_type")
        frames.append(FrameInstanceDiscovery(
            index=int(item.get("index", -1)),
            in_bounds=bool(item.get("in_bounds")),
            frame_found=bool(item.get("frame_found")),
            observed_device=str(item.get("observed_device") or ""),
            observed_in_port=str(item.get("observed_in_port") or ""),
            observed_sim_time=(
                int(raw_time) if isinstance(raw_time, (int, float)) else None
            ),
            observed_traffic_type=(
                int(raw_type) if isinstance(raw_type, (int, float)) else None
            ),
            members=tuple(
                str(name) for name in item.get("members", []) or ()
            ),
            observers=_member_rows(item.get("observers")),
            truncated=bool(item.get("truncated")),
            children=_child_rows(item.get("children")),
            failure_reason=str(item.get("failure_reason") or ""),
        ))
    return tuple(frames)


class PacketTracerFrameObserverProbe:
    """Enumera miembros de `frameInstance`. No lee valores desconocidos."""

    def __init__(self, send_and_wait: Callable[[str, float], str | None]) -> None:
        self._send_and_wait = send_and_wait

    def discover_frame_observers(
        self, indices: Iterable[int], *, timeout: float = 10.0,
    ) -> FrameObserverDiscovery:
        targets = tuple(int(item) for item in indices)
        if not targets or len(targets) > MAX_FRAME_TARGETS:
            return FrameObserverDiscovery(failure_reason=(
                "A frame index list of 1 to "
                f"{MAX_FRAME_TARGETS} entries is required."
            ))
        if any(item < 0 for item in targets):
            return FrameObserverDiscovery(failure_reason=(
                "A negative frame index names no event-list entry."
            ))

        raw = self._send_and_wait(_discovery_js(targets), timeout)
        if raw is None:
            return FrameObserverDiscovery(
                failure_reason="Frame observer discovery timed out.",
            )
        text = str(raw)
        if text.startswith(("ERROR:", "PT_ERROR:")):
            return FrameObserverDiscovery(failure_reason=text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return FrameObserverDiscovery(
                failure_reason="Frame observer discovery returned malformed JSON.",
            )
        if not isinstance(data, dict):
            return FrameObserverDiscovery(
                failure_reason="Frame observer discovery returned a non-object.",
            )
        frame_count = data.get("frame_count")
        return FrameObserverDiscovery(
            observed=bool(data.get("observed")),
            simulation_mode=bool(data.get("simulation_mode")),
            frame_count=(
                int(frame_count) if isinstance(frame_count, (int, float)) else 0
            ),
            frames=_frame_rows(data.get("frames")),
            failure_reason=str(data.get("failure_reason") or ""),
        )
