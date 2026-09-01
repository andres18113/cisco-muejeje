"""Frontera unica de despacho de comandos sobre terminales de Packet Tracer.

Por que existe:
El laboratorio sobre una topologia real mostro que el CLI recibio `ing ...` por
`ping ...` y `how ...` por `show ...`. IOS respondio `% Invalid input`, de modo
que no fue truncamiento de salida: el terminal recibio realmente un comando sin
su primer caracter.

La arquitectura anterior no podia ni siquiera nombrar ese fallo. Clasificaba por
el texto de la respuesta, asi que un comando corrompido se reportaba como
`IOS_COMMAND_REJECTED("show")` cuando IOS nunca habia recibido `show`. Este
modulo separa cuatro hechos que antes estaban colapsados en uno:

    REQUESTED   lo que el producto quiso ejecutar
    DISPATCHED  lo que el terminal realmente hizo eco
    EXECUTED    que IOS no lo rechazo
    OBSERVED    el efecto releido de forma independiente

Ninguno implica el siguiente. En particular, que `enterCommand` haya retornado
no prueba nada: es un fire-and-forget sobre un buzon de archivos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# Cota del ancla usada para re-sincronizar un buffer que rodo. Acotada a
# proposito: el algoritmo es lineal sobre esta ventana, nunca sobre el
# transcript completo, que en sesiones largas crece sin limite util.
_ROLL_ANCHOR_LIMIT = 65536
_PAGER_ROLL_MIN_ANCHOR = 512

_PAGER_MARKER = "--More--"


class DispatchClassification(str, Enum):
    """Que le paso a la identidad del comando, no a su resultado."""

    DISPATCHED = "dispatched"
    # El eco existe y difiere de lo pedido. NO es un rechazo de IOS.
    DISPATCH_MISMATCH = "dispatch_mismatch"
    # Caso particular y medido de MISMATCH: se perdio el primer caracter.
    PREFIX_LOSS = "prefix_loss"
    # No hay eco legible. Indecidible: nunca se promueve a exito ni a fallo.
    ECHO_UNOBSERVABLE = "echo_unobservable"
    # La barrera se nego a despachar. El comando no se envio.
    PROMPT_NOT_READY = "prompt_not_ready"
    TRANSPORT_FAILED = "transport_failed"


class PromptReadiness(str, Enum):
    """Condicion observable del terminal antes de despachar."""

    READY = "ready"
    PAGER_ACTIVE = "pager_active"
    BOOTING = "booting"
    SETUP_DIALOG = "setup_dialog"
    AWAITING_RETURN = "awaiting_return"
    # El prompt cambio entre observaciones consecutivas: hay una transicion en
    # curso y despachar ahora es exactamente la carrera que se investiga.
    UNSTABLE = "unstable"
    UNAVAILABLE = "unavailable"


class FreshWindowStrategy(str, Enum):
    PREFIX_DELTA = "prefix_delta"
    # El terminal reescribio su propia cola -- medido: al salir del pager, IOS
    # borra el `--More--` que el mismo habia impreso. El buffer NO rodo.
    PAGER_TAIL_REWRITE = "pager_tail_rewrite"
    # El buffer rodo por la cabeza y, en la misma transición, IOS borró su
    # marcador de pager de la cola. El ancla excluye sólo ese marcador.
    PAGER_ROLLED_SUFFIX_ANCHOR = "pager_rolled_suffix_anchor"
    # El buffer rodo y se re-sincronizo por el mayor sufijo retenido.
    ROLLED_SUFFIX_ANCHOR = "rolled_suffix_anchor"
    # El buffer rodo y no quedo anclaje: condicion explicita, no string vacio.
    ROLLED_UNATTRIBUTABLE = "rolled_unattributable"
    NONE = "no_fresh_window"


_SETUP_DIALOG = "would you like to enter the initial configuration dialog"
_ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_IOS_SYSLOG = re.compile(r"^\s*%[A-Z][A-Z0-9_]*-\d+-[A-Z0-9_]+\s*:")

# Guarda de pager evaluada DENTRO del mismo script que despacha.
#
# Chequear el pager en un round trip y despachar en otro deja un hueco entre
# ambos, y ese hueco es exactamente la carrera investigada: si el `--More--`
# sigue activo, el primer caracter del comando siguiente se consume en avanzar
# la pagina en vez de llegar al CLI. El Script Engine ejecuta el script entero
# de corrido, asi que comprobarlo aca elimina el hueco en vez de angostarlo.
#
# Espera una variable `before` ya definida y define `__pager`. Resuelve los
# backspaces con los que IOS redibuja su propio `--More--`.
PAGER_GUARD_JS = (
    "var __clean=before.replace(/\\x1b\\[[0-?]*[ -/]*[@-~]/g,'');"
    "var __o=[];for(var __i=0;__i<__clean.length;__i++){"
    "var __c=__clean.charAt(__i);"
    "if(__c==='\\b'){if(__o.length&&__o[__o.length-1]!=='\\n'){__o.pop();}}"
    "else{__o.push(__c);}}"
    "var __r=__o.join('').replace(/[ \\t\\r\\n]+$/,'');"
    "var __pm=__r.lastIndexOf('--More--');var __pager=__pm>=0;"
    "if(__pager){var __pt=__r.substring(__pm+8).split(/\\n/);"
    "var __ps=/^%[A-Z][A-Z0-9_]*-\\d+-[A-Z0-9_]+\\s*:/;"
    "for(var __pi=0;__pi<__pt.length;__pi++){"
    "var __pl=__pt[__pi].replace(/^\\s+|\\s+$/g,'');"
    "if(__pl!==''&&!__ps.test(__pl)){__pager=false;break;}}}"
)

# Segunda condicion de readiness, tambien dentro del script de despacho: el
# terminal volvio a su prompt y no hay un comando todavia imprimiendo.
#
# Medido en vivo: un `ping` que falla tarda ~13s en PT, y despachar el
# siguiente antes de que termine produce una ventana que pertenece al comando
# ANTERIOR. Eso se leia como "eco no observado" y escondia el verdadero
# problema, que era haber tipeado sobre un terminal ocupado.
#
# Requiere `__r` (definido por PAGER_GUARD_JS) y define `__idle`. NO se usa en
# las transiciones de modo ni al contestar el setup dialog: ahi el terminal
# legitimamente no esta en un prompt.
# Descarta las lineas de syslog de la cola antes de buscar el prompt, con la
# misma regla que el lado Python: IOS emite `%SYS-5-CONFIG_I` DESPUES de haber
# devuelto el control, y exigir el prompt al final dejaba esto en False para
# siempre. Corre dentro del script de despacho, asi que la guarda atomica y el
# helper de Python no pueden divergir.
IDLE_GUARD_JS = (
    "var __syslog=/^%[A-Z][A-Z0-9_]*-\\d+-[A-Z0-9_]+\\s*:/;"
    "var __il=__r.split('\\n');"
    "while(__il.length){var __lt=__il[__il.length-1].replace(/^\\s+|\\s+$/g,'');"
    "if(__lt===''||__syslog.test(__lt)){__il.pop();}else{break;}}"
    "var __idle=__il.length>0&&"
    "/(?:[A-Za-z]:\\\\>|\\S*[>#])\\s*$/.test(__il.join('\\n'));"
)


def resolve_backspaces(value: str) -> str:
    """Aplica los backspaces en vez de conservarlos como texto.

    IOS borra su propio `--More--` emitiendo `\\x08 \\x08` por caracter. Un
    `endswith("--More--")` sobre el texto crudo no ve un pager que sigue activo
    si el terminal lo redibujo, y esa ceguera deja pasar el despacho que come el
    primer caracter. Resolver los backspaces reconstruye lo que la linea
    realmente muestra.
    """
    out: list[str] = []
    for character in value:
        if character == "\b":
            if out and out[-1] != "\n":
                out.pop()
            continue
        out.append(character)
    return "".join(out)


def rendered_terminal_text(value: str) -> str:
    """Lo que la linea muestra: sin CSI, con backspaces aplicados, LF normalizado."""
    return resolve_backspaces(
        _ANSI_CSI.sub("", value).replace("\r\n", "\n").replace("\r", "\n"),
    )


def _active_pager_boundary(value: str) -> tuple[str, int] | None:
    """Return rendered text and its active marker index, ignoring only syslogs."""

    rendered = rendered_terminal_text(value)
    marker = rendered.rfind(_PAGER_MARKER)
    if marker < 0:
        return None
    for line in rendered[marker + len(_PAGER_MARKER):].splitlines():
        stripped = line.strip()
        if stripped and _IOS_SYSLOG.match(stripped) is None:
            return None
    return rendered, marker


def has_active_pager(value: str) -> bool:
    """True si la linea quedo detenida en `--More--`.

    Se evalua sobre el texto renderizado: en PT 9.0.1 `terminal length 0` no
    esta disponible, asi que el pager es un estado real y frecuente, y es el
    unico estado del CLI que consume exactamente una tecla para continuar.
    """
    return _active_pager_boundary(value) is not None


def terminal_has_command_content(value: str) -> bool:
    """Reject whitespace, pager redraw, and asynchronous syslog-only deltas."""

    for line in rendered_terminal_text(value).splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped == _PAGER_MARKER
            or _IOS_SYSLOG.match(stripped) is not None
        ):
            continue
        return True
    return False


@dataclass(frozen=True)
class FreshWindow:
    """Ventana atribuible al comando actual, o la razon de que no la haya."""

    output: str
    fresh: bool
    strategy: FreshWindowStrategy
    rolled: bool = False


def _longest_retained_suffix(before: str, after: str) -> int:
    """Mayor k tal que ``before[-k:] == after[:k]``, en tiempo lineal.

    Cuando el buffer del terminal rueda, PT descarta un prefijo de lo ya visto:
    lo que queda de `before` pasa a ser el comienzo de `after`. Ese k reconstruye
    el punto de corte sin buscar el texto del comando, que es justamente lo que
    no se puede asumir intacto cuando se investiga corrupcion de comandos.
    """
    limit = min(len(before), len(after), _ROLL_ANCHOR_LIMIT)
    if limit <= 0:
        return 0
    # Funcion prefijo de KMP sobre `after[:limit] + sep + before[-limit:]`. El
    # separador no puede aparecer en salida de terminal renderizada.
    combined = after[:limit] + "\x00" + before[-limit:]
    failure = [0] * len(combined)
    for index in range(1, len(combined)):
        candidate = failure[index - 1]
        while candidate and combined[index] != combined[candidate]:
            candidate = failure[candidate - 1]
        if combined[index] == combined[candidate]:
            candidate += 1
        failure[index] = candidate
    return min(failure[-1], limit)


def fresh_command_window(before: str, after: str) -> FreshWindow:
    """Aisla lo que el terminal agrego desde `before`, sin confiar en el comando.

    Deliberadamente NO busca el texto del comando para anclarse. La version
    anterior caia a ``after.rfind(command)``, lo que tenia dos consecuencias
    malas: un comando corrompido no se encontraba nunca, y un comando repetido
    en una sesion larga se anclaba a una ejecucion VIEJA y atribuia salida stale
    como fresca.
    """
    if not after:
        return FreshWindow("", False, FreshWindowStrategy.NONE)
    rendered_before = rendered_terminal_text(before)
    rendered_after = rendered_terminal_text(after)
    if rendered_before == rendered_after:
        return FreshWindow("", False, FreshWindowStrategy.NONE)
    # Medido en PT 9.0.1.0858: al salir del pager, IOS borra el `--More--` que
    # habia impreso, asi que `after` deja de empezar con `before` aunque no se
    # haya perdido ni una linea. Tratar eso como buffer rodado descartaba la
    # ventana entera -- y era justamente la ventana que contenia la evidencia
    # del comando corrompido.
    if rendered_before.rstrip() == rendered_after.rstrip():
        return FreshWindow("", False, FreshWindowStrategy.NONE)
    pager_boundary = _active_pager_boundary(before)
    if pager_boundary is not None:
        rendered_before, marker_index = pager_boundary
        before_marker = rendered_before[:marker_index]
        if not before_marker.strip():
            return FreshWindow(
                "",
                False,
                FreshWindowStrategy.ROLLED_UNATTRIBUTABLE,
                rolled=True,
            )
        pager_bases = [before_marker]
        # Measured PT form: one display-space prefixes `--More--` and is erased
        # with it. Exact continuity wins; this alternate is considered only
        # when preserving that byte cannot anchor the rendered transcript.
        if before_marker.endswith(" "):
            pager_bases.append(before_marker[:-1])
        for pager_base in pager_bases:
            if pager_base and rendered_after.startswith(pager_base):
                output = rendered_after[len(pager_base):]
                if not output:
                    return FreshWindow("", False, FreshWindowStrategy.NONE)
                return FreshWindow(
                    output,
                    True,
                    FreshWindowStrategy.PAGER_TAIL_REWRITE,
                )
        for pager_base in pager_bases:
            retained = _longest_retained_suffix(
                pager_base,
                rendered_after,
            )
            retained_fragment = pager_base[-retained:]
            if (
                retained >= _PAGER_ROLL_MIN_ANCHOR
                and "\n" in retained_fragment
            ):
                return FreshWindow(
                    rendered_after[retained:],
                    True,
                    FreshWindowStrategy.PAGER_ROLLED_SUFFIX_ANCHOR,
                    rolled=True,
                )
        return FreshWindow(
            "",
            False,
            FreshWindowStrategy.ROLLED_UNATTRIBUTABLE,
            rolled=True,
        )
    if after.startswith(before):
        if len(after) == len(before):
            return FreshWindow("", False, FreshWindowStrategy.NONE)
        return FreshWindow(
            after[len(before):],
            True,
            FreshWindowStrategy.PREFIX_DELTA,
        )
    if not before:
        return FreshWindow(after, True, FreshWindowStrategy.PREFIX_DELTA)
    retained = _longest_retained_suffix(before, after)
    if retained <= 0:
        # El buffer rodo mas alla de todo lo conocido. Es una condicion de
        # frescura explicita, no una ventana vacia que alguien pueda confundir
        # con "el comando no imprimio nada".
        return FreshWindow("", False, FreshWindowStrategy.ROLLED_UNATTRIBUTABLE, rolled=True)
    return FreshWindow(
        after[retained:], True, FreshWindowStrategy.ROLLED_SUFFIX_ANCHOR, rolled=True,
    )


def first_echo_line(window: str) -> str:
    """Primera linea de la ventana que puede ser el eco del comando.

    El terminal repite lo que recibio antes de responder, y esa linea es la
    unica evidencia directa de la identidad de lo despachado.

    Las lineas de syslog se saltean porque son asincronas: un
    `%LINK-5-CHANGED: ...` que llega justo despues del prompt quedaria primero
    y haria ilegible el eco de un comando que se despacho perfectamente. Se
    saltea SOLO ese formato reconocible; cualquier otra linea sigue contando
    como la primera, para que el cotejo siga siendo exacto y no una busqueda.
    """
    for line in rendered_terminal_text(window).splitlines():
        stripped = line.strip()
        if not stripped or _IOS_SYSLOG.match(stripped):
            continue
        return stripped
    return ""


def _strip_prompt(line: str) -> str:
    """Quita un prompt pegado al eco (`Router#show ...` -> `show ...`)."""
    match = re.match(r"^\S*[>#]\s*(?P<rest>.*)$", line)
    return match.group("rest").strip() if match else line


def _looks_like_corrupted_echo(wanted: str, echoed: str) -> bool:
    """Distingue un eco corrompido de una linea que simplemente no es un eco.

    Hace falta porque no todo terminal hace eco, y afirmar corrupcion cuando
    solo hubo ausencia de eco es tan incorrecto como no detectarla: convertiria
    cada consulta de un terminal silencioso en un fallo de despacho.
    """
    if not wanted or not echoed or echoed == wanted:
        return False
    # Caracteres iniciales perdidos: el eco es un sufijo propio de lo pedido.
    if wanted.endswith(echoed) and len(echoed) >= max(3, len(wanted) // 2):
        return True
    # Misma longitud con pocas diferencias: sustitucion o transposicion.
    if len(echoed) == len(wanted):
        differences = sum(1 for want, echo in zip(wanted, echoed) if want != echo)
        return 0 < differences <= 2
    return False


def classify_echo(requested: str, window: str) -> tuple[DispatchClassification, str]:
    """Compara lo pedido contra lo que el terminal hizo eco.

    Devuelve la clasificacion y el eco observado. La comparacion es exacta: un
    `in` habria dado por bueno `how controllers Serial0/0/1` dentro de una
    ventana que contiene el texto pedido en otra linea.

    Una linea que no se parece a lo pedido NO se declara corrupcion: queda
    ECHO_UNOBSERVABLE, que es indecidible y nunca se promueve ni a exito ni a
    fallo de despacho.
    """
    echoed = _strip_prompt(first_echo_line(window))
    if not echoed:
        return DispatchClassification.ECHO_UNOBSERVABLE, ""
    wanted = requested.strip()
    if echoed == wanted:
        return DispatchClassification.DISPATCHED, echoed
    if wanted and echoed == wanted[1:]:
        # La firma medida en laboratorio. Se nombra aparte porque tiene una
        # causa fisica distinta de un eco arbitrariamente distinto: un estado
        # del CLI que consumio exactamente una tecla.
        return DispatchClassification.PREFIX_LOSS, echoed
    if _looks_like_corrupted_echo(wanted, echoed):
        return DispatchClassification.DISPATCH_MISMATCH, echoed
    return DispatchClassification.ECHO_UNOBSERVABLE, echoed


def is_command_corrupted(classification: DispatchClassification) -> bool:
    """True si la identidad del comando quedo demostrada como distinta."""
    return classification in {
        DispatchClassification.PREFIX_LOSS,
        DispatchClassification.DISPATCH_MISMATCH,
    }


# Cola de un terminal que devolvio el control: prompt IOS (`Router>`, `Router#`)
# o prompt del CommandPrompt de un PC (`C:\>`).
_IDLE_PROMPT_TAIL = re.compile(r"(?:[A-Za-z]:\\>|\S*[>#])\s*$")


def terminal_is_idle(output: str) -> bool:
    """True si el terminal volvio al prompt y no hay comando en vuelo.

    Medido en vivo: reintentar sin comprobar esto despachaba un `ping` nuevo
    mientras el anterior seguia imprimiendo, y la ventana resultante pertenecia
    al comando ANTERIOR. El eco entonces faltaba, y el fallo se reportaba como
    "eco no observado" en vez de "se reintento sobre un comando en curso".

    Las lineas de syslog de la COLA se descartan antes de buscar el prompt.
    Medido durante R2-0: al terminar `configureIosDevice`, IOS imprime su
    prompt y recien despues emite `%SYS-5-CONFIG_I`, de modo que el buffer deja
    de terminar en prompt aunque el CLI ya devolvio el control. Exigir el
    prompt al final dejaba esto en False para siempre -- sin cambios a t+35s.

    Se saltea SOLO el formato reconocible de syslog, la misma regla que usa
    `first_echo_line`. Cualquier otra cola -- un comando en vuelo, un `%
    Invalid input`, texto arbitrario -- sigue significando que el terminal no
    esta listo, y el pager se rechaza antes de mirar nada.
    """
    rendered = rendered_terminal_text(output).rstrip()
    if not rendered or rendered.endswith(_PAGER_MARKER):
        return False
    lines = rendered.splitlines()
    while lines:
        tail = lines[-1].strip()
        if tail and not _IOS_SYSLOG.match(tail):
            break
        lines.pop()
    if not lines:
        # Solo habia avisos asincronos: no hay prompt al que haber vuelto.
        return False
    return bool(_IDLE_PROMPT_TAIL.search("\n".join(lines).rstrip()))


def assess_prompt_readiness(
    previous: dict | None,
    current: dict,
) -> PromptReadiness:
    """Convergencia observable previa al despacho; nunca un sleep fijo.

    `previous` es la observacion inmediatamente anterior. Exigir que el prompt
    no haya cambiado entre dos lecturas consecutivas es lo que descarta estar
    en mitad de una transicion de modo.
    """
    if not current.get("found") or not current.get("terminal"):
        return PromptReadiness.UNAVAILABLE
    if current.get("booting") is True:
        return PromptReadiness.BOOTING
    output = str(current.get("output") or "")
    prompt = str(current.get("prompt") or "").strip()
    if has_active_pager(output):
        return PromptReadiness.PAGER_ACTIVE
    content = (prompt + "\n" + rendered_terminal_text(output)).casefold()
    if _SETUP_DIALOG in content:
        return PromptReadiness.SETUP_DIALOG
    if "press return to get started" in content and not prompt.endswith((">", "#")):
        return PromptReadiness.AWAITING_RETURN
    if not prompt or not prompt.endswith((">", "#")):
        return PromptReadiness.UNAVAILABLE
    if previous is not None and str(previous.get("prompt") or "").strip() != prompt:
        return PromptReadiness.UNSTABLE
    return PromptReadiness.READY


def drop_pager_prompt(value: str) -> str:
    """Quita de la cola el `--More--`, que lo escribe el pager y no el device.

    El marcador es una peticion de tecla del terminal, no salida del comando,
    asi que no puede quedar dentro de una lectura logica reconstruida a partir
    de varias paginas. Se quita SOLO de la cola y sin tocar el salto de linea
    que lo precede: cuando el pager corta a mitad de una linea, concatenar las
    paginas tal cual es lo unico que la vuelve a unir como estaba.

    Que hubo paginacion NO se borra aca. Eso vive en campos tipados del
    resultado -- cuantas paginas se capturaron y como termino la continuacion --
    precisamente para que el texto pueda quedar limpio sin perder el hecho.
    """
    boundary = _active_pager_boundary(value)
    if boundary is None:
        return rendered_terminal_text(value)
    rendered, marker = boundary
    return rendered[:marker]
