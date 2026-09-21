"""Ping tipado sobre el terminal correcto con evidencia de la consulta actual."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Callable
from dataclasses import replace
from time import monotonic, sleep

from ...domain.models.typed_ping import TypedPingResult
from .command_dispatch import (
    IDLE_GUARD_JS,
    PAGER_GUARD_JS,
    DispatchClassification,
    classify_echo,
    terminal_is_idle,
)
from .ios_terminal import (
    DISPATCH_DELTA_ATTRIBUTION_EVIDENCE,
    DeviceIdentityProvenance,
    classify_execution_identity,
    dispatch_delta_attribution_js,
    dispatch_snapshot_js,
    execution_identity_diagnostics,
    extract_terminal_command_window,
)

# El `[^\n]*` final existe para que `group(0)` sea la LINEA de estadistica
# completa: el contrato publico de `pt_ping` venia mostrando `Lost = N` y el
# `(N% loss)`, y recortar en `Received` los perdia. Los grupos numerados no
# cambian, asi que la interpretacion sigue siendo la misma.
_PACKET_COUNTS = re.compile(
    r"Packets:\s*Sent\s*=\s*(\d+),\s*Received\s*=\s*(\d+)[^\n]*",
    re.IGNORECASE,
)
_IOS_SUCCESS_RATE = re.compile(
    r"Success rate is\s+(\d+)\s+percent\s+\((\d+)/(\d+)\)[^\n]*",
    re.IGNORECASE,
)

# Contrato exacto: SAFE_DEFAULT + invariante de callsite productivo.
#
# NO es un minimo forzado: el constructor no lo impone, y los tests pasan 0 a
# proposito porque no esperan a ningun backend. Lo que si se sostiene es que
# ninguna construccion PRODUCTIVA quede por debajo, y eso lo audita un test.
#
# Medido en PT 9.0.1.0858 sobre dispositivos disposable: un ping totalmente
# perdido tarda 25.0 s en publicar su estadistica desde un PC y 10.8 s desde un
# 2911. Con el default anterior de 12 s, un destino inalcanzable desde un PC no
# llegaba a clasificarse como inalcanzable: se reportaba como sin evidencia
# atribuible, que es un error de clasificacion y no una espera corta.
#
# El presupuesto sigue siendo del caller, que puede subirlo por semantica; lo
# que no debe pasar es que alguien tenga que bajarlo para ser correcto.
SAFE_PING_TIMEOUT_S = 30.0


def inspection_schedule(timeout_seconds: float, inspections: int) -> tuple[float, ...]:
    """Return the absolute offsets, from the dispatch, of a finite poll.

    The reads are the `inspections` endpoints of an even partition of the
    CLOSED window ``[0, timeout_seconds]``: the first is immediate and the last
    lands on the deadline itself, so the whole promised window is covered
    instead of closing one interval early.

    One inspection cannot be both immediate and window-covering. The window is
    the promise the safe timeout exists to keep, so a single inspection is
    taken at the deadline; a lone read at zero could not observe a statistic
    that has not been published yet. Building that case separately is also why
    no division by ``inspections - 1`` can reach zero here.
    """
    window = max(0.0, float(timeout_seconds))
    if inspections <= 1:
        return (window,)
    step = window / (inspections - 1)
    # `min` absorbs the float accumulation of the last slot so the schedule
    # never advertises a read after the deadline it is meant to land on.
    return tuple(min(window, step * index) for index in range(inspections))


class TypedPingExecutor:
    """Ejecuta solamente ``ping <ip-validada>``; nunca acepta comandos libres."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        *,
        timeout_seconds: float = SAFE_PING_TIMEOUT_S,
        interval_seconds: float = 0.25,
        measurement_attempts: int = 1,
        max_inspections: int | None = None,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        """Bind one typed ping to its channel, its bounds, its clock and sleeper.

        `max_inspections` defaults to `None`, which is unbounded polling and
        is exactly what every existing caller already does. A caller that has
        to account for each nested call -- a diagnostic spending a counted
        operation ledger -- sets it, and the reads are then placed on the
        finite schedule `inspection_schedule` returns, whose last slot is the
        deadline itself. It bounds how many observations are taken, never the
        window itself: shortening the window would turn a slow destination
        into a premature unreachable claim.
        """
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds < 0
        ):
            raise ValueError("timeout_seconds must be non-negative.")
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or interval_seconds < 0
        ):
            raise ValueError("interval_seconds must be non-negative.")
        if (
            isinstance(measurement_attempts, bool)
            or not isinstance(measurement_attempts, int)
            or measurement_attempts < 1
        ):
            raise ValueError("measurement_attempts must be a positive integer.")
        if max_inspections is not None and (
            isinstance(max_inspections, bool)
            or not isinstance(max_inspections, int)
            or max_inspections < 1
        ):
            raise ValueError("max_inspections must be a positive integer or None.")
        self._measurement_attempts = measurement_attempts
        self._max_inspections = max_inspections
        self._send_and_wait = send_and_wait
        self._timeout = timeout_seconds
        self._interval = interval_seconds
        self._clock = clock
        self._sleep = sleeper

    def ping(self, source_device: str, destination: str) -> TypedPingResult:
        """Ejecuta la medida, reintentando solo mientras no haya ventana fresca.

        La terminal de un endpoint recien creado no atribuye sus primeras
        ejecuciones: medido contra PT 9.0.1.0858, un PC listo devolvio
        ``no_fresh_ping_result`` y luego ``current_ping_echo_not_observed``
        antes de entregar una ventana valida al tercer intento. Sin esto, cada
        probe tendria que repetir un descarte manual antes de medir.

        Un resultado fresco -- alcanzable o no -- se devuelve de inmediato: el
        reintento busca evidencia atribuible, nunca un resultado favorable.
        """
        attempt = 0
        result = self._ping_once(source_device, destination)
        while (
            not result.fresh_output_observed
            and attempt + 1 < self._measurement_attempts
        ):
            # Medido en vivo contra PT 9.0.1.0858: sin esta comprobacion el
            # reintento tipeaba un ping nuevo mientras el anterior seguia
            # imprimiendo, y la ventana resultante pertenecia al comando
            # ANTERIOR. Un comando en vuelo no se pisa: se informa lo que hay.
            if not self._terminal_returned_to_prompt(source_device):
                return replace(
                    result,
                    attempts=attempt + 1,
                    failure_reason=result.failure_reason
                    or "previous_command_still_running",
                )
            attempt += 1
            self._sleep(self._interval)
            result = self._ping_once(source_device, destination)
        return replace(result, attempts=attempt + 1)

    def _terminal_returned_to_prompt(self, source_device: str) -> bool:
        source = json.dumps(source_device)
        observed = self._json_result(
            "".join(
                (
                    "try{var d=ipc.network().getDevice(",
                    source,
                    ");var t=null;",
                    "if(d&&typeof d.getCommandPrompt==='function'){t=d.getCommandPrompt();}",
                    "if(!t&&d&&typeof d.getCommandLine==='function'){t=d.getCommandLine();}",
                    "reportResult(JSON.stringify({output:t?String(t.getOutput()):''}));}",
                    "catch(e){reportResult('ERROR:'+e);}",
                )
            ),
            3.0,
        )
        return terminal_is_idle(str(observed.get("output") or ""))

    def _ping_once(self, source_device: str, destination: str) -> TypedPingResult:
        if not self._valid_device_name(source_device):
            return TypedPingResult(False, False, failure_reason="invalid_source_device")
        try:
            target = str(ipaddress.ip_address(destination))
        except (TypeError, ValueError):
            return TypedPingResult(False, False, failure_reason="invalid_destination")

        source = json.dumps(source_device)
        command = "ping " + target
        # La huella de terminales se toma en ESTE script, justo antes de
        # `enterCommand`, y enumera la red entera como la atribucion. Por eso el
        # tope es el del despacho IOS: si vence con el script todavia corriendo,
        # el ping queda despachado sin que Python lo sepa.
        started = self._json_result(
            "".join(
                (
                    "try{var d=ipc.network().getDevice(",
                    source,
                    ");",
                    "var t=null;var kind='';",
                    "if(d&&typeof d.getCommandPrompt==='function'){",
                    "t=d.getCommandPrompt();if(t){kind='command_prompt';}}",
                    "if(!t&&d&&typeof d.getCommandLine==='function'){",
                    "t=d.getCommandLine();if(t){kind='ios_command_line';}}",
                    "var before=t&&typeof t.getOutput==='function'?String(t.getOutput()):'';",
                    PAGER_GUARD_JS,
                    IDLE_GUARD_JS,
                    # Mismo script que el despacho: si el pager sigue activo, el `p` de
                    # `ping` se gasta en avanzar la pagina y el CLI recibe `ing`. Y si
                    # el terminal todavia imprime, la ventana seria del comando previo.
                    "var started=false;var blocked='';",
                    "if(__pager){blocked='pager_active';}",
                    "else if(!__idle){blocked='command_in_flight';}",
                    "else if(t&&typeof t.enterCommand==='function'){",
                    dispatch_snapshot_js(command, prefer_command_prompt=True),
                    "t.enterCommand(",
                    json.dumps(command),
                    ");started=true;}",
                    "reportResult(JSON.stringify({started:started,blocked:blocked,before:before,",
                    "snapshot:__snap,terminal_kind:kind}));}",
                    "catch(e){reportResult('ERROR:'+e);}",
                )
            ),
            10.0,
        )
        if started.get("blocked"):
            return TypedPingResult(
                False,
                False,
                failure_reason="prompt_not_ready_" + str(started.get("blocked")),
            )
        if not started.get("started"):
            return TypedPingResult(
                False, False, failure_reason="command_prompt_unavailable"
            )
        before = str(started.get("before") or "")

        def inspect() -> dict:
            return self._json_result(
                "".join(
                    (
                        "try{var d=ipc.network().getDevice(",
                        source,
                        ");",
                        "var t=null;var kind='';",
                        "if(d&&typeof d.getCommandPrompt==='function'){",
                        "t=d.getCommandPrompt();if(t){kind='command_prompt';}}",
                        "if(!t&&d&&typeof d.getCommandLine==='function'){",
                        "t=d.getCommandLine();if(t){kind='ios_command_line';}}",
                        "reportResult(JSON.stringify({found:!!t,terminal_kind:kind,",
                        "output:t?String(t.getOutput()):''}));}",
                        "catch(e){reportResult('ERROR:'+e);}",
                    )
                ),
                3.0,
            )

        started_at = self._clock()
        deadline = started_at + self._timeout
        observed: dict = {}
        window = extract_terminal_command_window(before, "", command)
        # Unbounded, the interval is the caller's. Bounded, the reads are the
        # fixed offsets of `inspection_schedule`, held as ABSOLUTE times from
        # the dispatch so that the I/O each read costs is elapsed window and
        # not a delay added on top of it.
        pending: list[float] | None = (
            None
            if self._max_inspections is None
            else list(inspection_schedule(self._timeout, self._max_inspections))
        )
        inspection_budget_spent = False
        while True:
            if pending is not None:
                delay = started_at + pending.pop(0) - self._clock()
                if delay > 0:
                    self._sleep(delay)
            observed = inspect()
            window = extract_terminal_command_window(
                before,
                str(observed.get("output") or ""),
                command,
            )
            normalized = window.output.casefold()
            if "packets: sent" in normalized or "success rate is" in normalized:
                break
            # The slot at `timeout` is taken before this check ends the poll:
            # the window is closed inclusively, and the statistics a slow
            # destination publishes at the very end are inside it.
            if self._clock() >= deadline:
                break
            if pending is None:
                self._sleep(self._interval)
                continue
            now = self._clock()
            # A slot whose time has already passed was missed, not deferred.
            # Reading it now would be a catch-up burst, which is exactly what
            # a finite schedule is for avoiding.
            while pending and started_at + pending[0] <= now:
                del pending[0]
            if not pending:
                # The schedule ran out while the window was still open, which
                # only happens when the injected sleeper could not honour it --
                # a ledger-capped sleep is the real case. The sample is
                # INCOMPLETE by its own bound: a reading that was not taken
                # cannot be reported as a statistic that did not arrive.
                inspection_budget_spent = True
                break

        # La ultima lectura ATRIBUYE: la estadistica que se va a interpretar y
        # el device al que se le atribuye salen de la misma pasada. Una medida
        # de reenvio sin fuente atribuida no es una medida de este device.
        attribution = self._json_result(
            dispatch_delta_attribution_js(
                source,
                before,
                command,
                dispatch_snapshot=started.get("snapshot"),
                prefer_command_prompt=True,
            ),
            5.0,
        )
        identity = classify_execution_identity(
            source_device,
            attribution,
            accepted_evidence=DISPATCH_DELTA_ATTRIBUTION_EVIDENCE,
        )
        identity_evidence = {
            **identity,
            **execution_identity_diagnostics(
                attribution,
                accepted_evidence=DISPATCH_DELTA_ATTRIBUTION_EVIDENCE,
            ),
        }
        if (
            identity["device_identity_provenance"]
            == DeviceIdentityProvenance.MISMATCHED.value
        ):
            # La sesion que respondio es de OTRO device. Su estadistica no dice
            # nada del origen pedido, asi que no se devuelve ninguna medida.
            return TypedPingResult(
                False,
                False,
                window_strategy=window.strategy,
                failure_reason=(
                    "device_provenance_mismatch:" + identity["observed_device_name"]
                ),
                **identity_evidence,
            )
        attributed = str(attribution.get("output") or "")
        if attributed:
            # Reinterpretar sobre la transcripcion del device atribuido, no
            # sobre la de la busqueda por nombre.
            window = extract_terminal_command_window(before, attributed, command)

        incomplete = (
            "ping_inspection_budget_exhausted"
            if inspection_budget_spent
            else "no_fresh_ping_result"
        )
        if not window.fresh:
            return TypedPingResult(
                False,
                False,
                window_strategy=window.strategy,
                failure_reason=incomplete,
                **identity_evidence,
            )
        if not window.query_echo_found:
            # Un eco corrompido y un eco ausente son cosas distintas: el primero
            # prueba que el terminal recibio OTRO comando, el segundo no prueba
            # nada. Colapsarlos ocultaba justamente el defecto que se investiga.
            classification, echoed = classify_echo(command, window.output)
            return TypedPingResult(
                False,
                False,
                window_strategy=window.strategy,
                failure_reason=(
                    "current_ping_echo_not_observed"
                    if classification is DispatchClassification.ECHO_UNOBSERVABLE
                    else f"command_dispatch_mismatch:{classification.value}:{echoed}"
                ),
                **identity_evidence,
            )
        counts = _PACKET_COUNTS.search(window.output)
        if counts is not None:
            sent, received = int(counts.group(1)), int(counts.group(2))
            if sent > 0 and 0 <= received <= sent:
                return TypedPingResult(
                    reachable=received > 0,
                    fresh_output_observed=True,
                    window_strategy=window.strategy,
                    statistics=counts.group(0),
                    dispatched_destination=target,
                    **identity_evidence,
                )
        ios = _IOS_SUCCESS_RATE.search(window.output)
        if ios is not None:
            percent, received, sent = map(int, ios.groups())
            if 0 <= percent <= 100 and sent > 0 and 0 <= received <= sent:
                return TypedPingResult(
                    reachable=received > 0,
                    fresh_output_observed=True,
                    window_strategy=window.strategy,
                    statistics=ios.group(0),
                    dispatched_destination=target,
                    **identity_evidence,
                )
        return TypedPingResult(
            False,
            False,
            window_strategy=window.strategy,
            failure_reason=incomplete,
            **identity_evidence,
        )

    def _json_result(self, script: str, timeout: float) -> dict:
        raw = self._send_and_wait(script, timeout)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            return {}
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _valid_device_name(value: str) -> bool:
        return bool(
            isinstance(value, str)
            and value
            and value == value.strip()
            and len(value) <= 128
            and not any(
                ord(character) < 32 or ord(character) == 127 for character in value
            )
        )
