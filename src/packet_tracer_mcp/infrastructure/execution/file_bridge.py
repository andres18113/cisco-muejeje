"""Transporte por archivo entre el servidor MCP y el Script Engine de Packet Tracer.

Por qué existe, además del bridge HTTP:
El polling HTTP vive en el webview de la extensión (la ventana). Si el usuario la
cierra, el webview muere y PT deja de ejecutar comandos — aunque la extensión
siga instalada. El Script Engine, en cambio, corre SIEMPRE que PT está abierto
(sin ventana), tiene setInterval y acceso a archivos, pero NO tiene
XMLHttpRequest. Así que el canal con el Script Engine no puede ser HTTP: es un
buzón de archivos.

Coexistencia (no reemplazo): HTTP sigue siendo el canal cuando la ventana está
abierta; este canal toma el relevo cuando está cerrada. El enrutado (elegir uno
por request, nunca ambos) vive en el adaptador; acá solo está el transporte.

Seguridad: el buzón vive bajo %LOCALAPPDATA% con ACL de usuario, igual que el
token. Una página web del navegador no puede escribir un archivo local, así que
este canal no tiene el vector CORS que obligó a autenticar el HTTP. La confianza
es la misma que el modelo de amenaza ya asume: el usuario local.

Protocolo (un archivo por request, escritura atómica tmp+rename):
    Python  ─ escribe req_<seq>.js  (atómico) ─►  Script Engine
    Python  ◄─ lee/borra res_<seq>.txt        ─   escribe res, borra req
    Script Engine toca alive.txt cada tick (heartbeat de vida)

Cancelación y timeout:
Al vencer, Python RETIRA el req en vez de dejarlo. El Script Engine lee y
evalúa dentro del mismo tick y borra el req sólo al terminar, así que el
resultado del `unlink` clasifica el caso: ENOENT prueba que ya se ejecutó, y
un borrado exitoso significa que todavía no se había completado. Ver
`RequestDisposition`.

Límite conocido de esta clasificación:
con el Script Engine desplegado no hay marca de *claim*, así que "leído y
evaluando" no se distingue de "nunca leído" por el filesystem. Para el caso
en que el borrado tuvo éxito, se observa acotadamente si aparece la respuesta;
si no aparece, se clasifica CANCELLED_UNCLAIMED asumiendo que una evaluación
ya iniciada habría publicado su respuesta dentro de esa ventana.

Corrección diferida que vuelve esa clasificación demostrable (requiere
recompilar el .pts, cuyas dependencias de PTBuilder no se redistribuyen desde
este repo, por lo que no se aplicó acá): que el Script Engine escriba un
marcador `run_<name>.txt` ANTES de leer el req, y lo borre al terminar.
Entonces Python, tras un `unlink` exitoso, sólo tiene que mirar el marcador:
ausente prueba que la evaluación no había empezado, porque el `getFileContents`
posterior fallaría sobre un archivo ya retirado. Sólo usa APIs ya confirmadas
del systemFileManager (`writePlainTextToFile`, `removeFile`); en particular NO
depende de un `renameFile`, que no está en la superficie medida.
"""

from __future__ import annotations

import os
import secrets
import time
from enum import Enum
from pathlib import Path

from .bridge_token import token_dir

# Subdirectorio del buzón, bajo el mismo dir del token.
_BRIDGE_SUBDIR = "bridge"

# El Script Engine se considera vivo si tocó alive.txt hace menos que esto.
HEARTBEAT_FRESH_S = 6.0

# Ventana acotada para observar si un request cancelado alcanzó a ejecutarse.
# No es un sleep para "arreglar" la carrera: el request ya fue cancelado antes
# de esperar. Es el tiempo que se le da al Script Engine para publicar la
# respuesta de una evaluación que ya estaba en curso. Su tick rápido es de
# 250 ms y la evaluación es síncrona, así que esto cubre varios ciclos.
_CANCEL_OBSERVATION_S = 1.5

# Los req/res propios más viejos que esto se purgan al cancelar. El Script
# Engine ya purga huérfanos a los 60 s; esto sólo cubre lo que quede si PT no
# está corriendo, y nunca toca archivos de otro proceso.
_OWN_STALE_TTL_S = 120.0


class RequestDisposition(str, Enum):
    """Qué pasó con un request, cuando el resultado no llegó a tiempo.

    Existe porque la ausencia de respuesta no dice si el comando se ejecutó.
    Antes el `req_*.js` se dejaba en disco a propósito para que el Script
    Engine lo procesara tarde, de modo que un comando cuyo caller ya se había
    rendido igual se tipeaba en la terminal, más tarde, sin dueño.
    """

    COMPLETED = "completed"
    # El req se retiró antes de que el Script Engine lo leyera: no se ejecuta.
    CANCELLED_UNCLAIMED = "cancelled_unclaimed"
    # El Script Engine ya lo había ejecutado. La respuesta se descarta, nunca
    # se atribuye a otra operación.
    EXECUTED_LATE = "executed_late"
    # No se pudo decidir. No se afirma que la cancelación haya funcionado.
    IN_FLIGHT_UNKNOWN = "in_flight_unknown"


def bridge_dir() -> Path:
    return token_dir() / _BRIDGE_SUBDIR


def ensure_bridge_dir() -> Path:
    d = bridge_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


class FileBridge:
    """Lado Python del buzón de archivos.

    Sin estado propio salvo un contador de secuencia; el estado real son los
    archivos en disco, para que sobreviva a reinicios del proceso.
    """

    def __init__(
        self,
        directory: Path | None = None,
        *,
        cancel_observation_seconds: float = _CANCEL_OBSERVATION_S,
    ):
        self.dir = Path(directory) if directory else bridge_dir()
        self._observation = cancel_observation_seconds
        self._seq = 0
        # Token de arranque: el par (pid, seq) se repite cuando el proceso MCP
        # reinicia y el SO recicla el pid, y entonces un `res_` viejo puede
        # caer justo en el nombre que espera una operación nueva. Con esto, un
        # nombre de request no se repite nunca entre corridas.
        self._boot = secrets.token_hex(4)
        self.last_disposition = RequestDisposition.COMPLETED

    def _ensure(self) -> None:
        # Crea SIEMPRE self.dir, no el default del módulo: si se pasó un
        # directorio propio (tests, config), la creación y la escritura tienen
        # que apuntar al mismo lugar.
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    # -- vida del Script Engine ----------------------------------------

    def pt_alive(self) -> bool:
        """True si el Script Engine tocó su heartbeat hace poco."""
        alive = self.dir / "alive.txt"
        try:
            age = time.time() - alive.stat().st_mtime
        except OSError:
            return False
        return age < HEARTBEAT_FRESH_S

    # -- envío ----------------------------------------------------------

    def _next_name(self) -> str:
        # Secuencia monotónica dentro del proceso + pid para no chocar entre
        # procesos MCP concurrentes que compartan el mismo buzón, + token de
        # arranque para no reusar un nombre tras reiniciar el proceso.
        self._seq += 1
        return f"{os.getpid()}_{self._boot}_{self._seq:06d}"

    def _write_atomic(self, path: Path, text: str) -> None:
        # tmp + replace: el Script Engine, que lista el directorio, nunca ve un
        # archivo a medio escribir (replace es atómico dentro del volumen).
        #
        # Bytes EXACTOS: escribir en binario, no write_text. En Windows el modo
        # texto traduce \n -> \r\n, y un CR/LF real dentro de un string literal
        # JS es SyntaxError. El comando (p.ej. configureIosDevice con \n entre
        # líneas de CLI) debe llegar al Script Engine tal cual se generó.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(text.encode("utf-8"))
        os.replace(tmp, path)

    def send(self, js_code: str) -> bool:
        """Encola un comando fire-and-forget. No espera resultado."""
        try:
            self._ensure()
            name = self._next_name()
            self._write_atomic(self.dir / f"req_{name}.js", js_code)
            return True
        except OSError:
            return False

    def send_and_wait(self, js_code: str, timeout: float = 12.0) -> str | None:
        """Encola un comando y espera su res_<name>.txt.

        El Script Engine envuelve la ejecución y escribe el resultado; acá se
        sondea la aparición del archivo de respuesta y se lo consume.
        """
        try:
            self._ensure()
        except OSError:
            return None
        name = self._next_name()
        res_path = self.dir / f"res_{name}.txt"
        try:
            self._write_atomic(self.dir / f"req_{name}.js", js_code)
        except OSError:
            return None

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if res_path.exists():
                    body = res_path.read_text(encoding="utf-8")
                    res_path.unlink(missing_ok=True)
                    # El Script Engine borra el req al terminar, pero ese
                    # borrado va dentro de un try/catch que traga el error: si
                    # falla, el mismo req se vuelve a ejecutar en cada tick
                    # hasta la purga de huerfanos. Retirarlo desde aca cierra
                    # esa reejecucion silenciosa.
                    self._discard(self.dir / f"req_{name}.js")
                    self.last_disposition = RequestDisposition.COMPLETED
                    return body
            except OSError:
                pass
            time.sleep(0.1)

        self.last_disposition = self._cancel(self.dir / f"req_{name}.js", res_path)
        return None

    def _cancel(self, req_path: Path, res_path: Path) -> RequestDisposition:
        """Retira un request vencido y clasifica qué alcanzó a pasar.

        Antes el req se dejaba en disco a propósito, "por si el SE lo procesa
        tarde". Eso significaba que un comando cuyo caller ya se había rendido
        seguía ejecutándose después -- hasta un minuto más tarde, cuando la
        purga de huérfanos del Script Engine lo alcanzaba. Un `enterCommand`
        así se tipea en la terminal sin dueño y contamina la ventana de
        cualquier comando posterior.

        El Script Engine borra el `req` sólo DESPUÉS de escribir su respuesta,
        así que el resultado del `unlink` es informativo por sí mismo.
        """
        try:
            req_path.unlink()
            claimed = False
        except FileNotFoundError:
            # El Script Engine ya lo retiró, y sólo lo hace al terminar.
            claimed = True
        except OSError:
            self._discard(res_path)
            return RequestDisposition.IN_FLIGHT_UNKNOWN

        if claimed:
            self._discard(res_path)
            return RequestDisposition.EXECUTED_LATE

        # El req todavía estaba en disco. O nunca se leyó, o se leyó y la
        # evaluación estaba en curso: desde el filesystem son indistinguibles
        # con el Script Engine desplegado. Se observa acotadamente si aparece
        # la respuesta, que es lo único que probaría que sí se ejecutó.
        observed_until = time.time() + self._observation
        while time.time() < observed_until:
            if res_path.exists():
                self._discard(res_path)
                return RequestDisposition.EXECUTED_LATE
            time.sleep(0.05)
        self._purge_own_stale()
        return RequestDisposition.CANCELLED_UNCLAIMED

    @staticmethod
    def _discard(res_path: Path) -> None:
        """Descarta una respuesta huérfana. Nunca se atribuye a otra operación."""
        try:
            res_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _purge_own_stale(self) -> None:
        """Limpieza acotada de residuos propios; nunca toca los de otro proceso."""
        mine = f"{os.getpid()}_{self._boot}_"
        cutoff = time.time() - _OWN_STALE_TTL_S
        try:
            entries = list(self.dir.iterdir())
        except OSError:
            return
        for entry in entries:
            stem = entry.name
            if not (stem.startswith("req_") or stem.startswith("res_")):
                continue
            if not stem[4:].startswith(mine):
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink(missing_ok=True)
            except OSError:
                continue
