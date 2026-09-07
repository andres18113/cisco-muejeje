"""Ciclo de vida de un request del buzon cuando el caller se rinde.

Por que existe:
El buzon dejaba el `req_*.js` en disco al vencer el timeout, a proposito, para
que el Script Engine lo procesara tarde. Un `enterCommand` asi se tipeaba en la
terminal sin dueno hasta un minuto despues, y contaminaba la ventana de
cualquier comando posterior. Estos tests simulan al Script Engine en vez de
depender de que Packet Tracer este corriendo.

Como se sincroniza con el motor simulado:
La primera version lo simulaba con `time.sleep(...)` y despues leia el nombre
del request, suponiendo que para entonces el buzon ya lo tendria escrito. En un
runner de Windows cargado no lo tenia: el hilo moria con `KeyError` antes de
publicar nada, pytest degradaba esa muerte a warning, y el test leia el
silencio resultante como "no se observo ejecucion". El veredicto dependia de la
velocidad de la maquina, no del protocolo. Ahora cada paso espera el evento
real -- que el request aparezca, que Python lo retire -- y una falla del hilo se
propaga al test en vez de disfrazarse de observacion.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from src.packet_tracer_mcp.infrastructure.execution.file_bridge import (
    FileBridge,
    RequestDisposition,
)


@pytest.fixture
def bridge(tmp_path) -> FileBridge:
    return FileBridge(tmp_path, cancel_observation_seconds=0.25)


@pytest.fixture
def patient_bridge(tmp_path) -> FileBridge:
    """Igual, pero sin apuro por cerrar la ventana de observacion.

    Los casos que esperan EXECUTED_LATE necesitan que la ventana siga abierta
    cuando el motor publica. La ventana se cierra apenas ve la respuesta, asi
    que darle margen no cuesta tiempo real: solo deja de exigir que el runner
    conteste dentro de 250 ms.
    """
    return FileBridge(tmp_path, cancel_observation_seconds=5.0)


def _requests(bridge: FileBridge) -> list[str]:
    return sorted(item.name for item in bridge.dir.glob("req_*.js"))


def _responses(bridge: FileBridge) -> list[str]:
    return sorted(item.name for item in bridge.dir.glob("res_*.txt"))


class _ScriptEngine:
    """El Script Engine, simulado y sincronizado por eventos en vez de sleeps.

    Se engancha en `_write_atomic` porque ese es el instante en que el motor
    real encontraria el archivo listado en el buzon: antes de eso no hay nada
    que leer, y esperar un plazo fijo a que aparezca es justo la suposicion que
    rompio el test en CI.
    """

    def __init__(self, bridge: FileBridge):
        self._bridge = bridge
        self._write = bridge._write_atomic
        self.names: list[str] = []
        self.claimed_source: str | None = None
        self._queued = threading.Event()
        bridge._write_atomic = self._on_write

    def _on_write(self, path: Path, text: str) -> None:
        self._write(path, text)
        if path.name.startswith("req_"):
            self.names.append(path.name[4:-3])
            # El motor lee el contenido en el mismo tick en que lo encuentra:
            # de aca en mas la evaluacion ya no depende del archivo.
            self.claimed_source = text
            self._queued.set()

    def await_request(self, timeout: float = 10.0) -> str:
        assert self._queued.wait(timeout), "el request nunca llego al buzon"
        return self.names[-1]

    def await_withdrawal(self, timeout: float = 10.0) -> str:
        """Espera a que Python retire el req: el instante exacto de la cancelacion."""
        name = self.await_request(timeout)
        req = self._bridge.dir / f"req_{name}.js"
        deadline = time.monotonic() + timeout
        while req.exists():
            assert time.monotonic() < deadline, "el request nunca se retiro"
            time.sleep(0.005)
        return name

    def publish(self, name: str, body: str) -> None:
        # Atomico como el resto del buzon: el caller sondea este archivo desde
        # otro hilo y nunca debe leerlo a medio escribir.
        self._write(self._bridge.dir / f"res_{name}.txt", body)


@contextmanager
def _running(work):
    """Corre al motor simulado en otro hilo y NO deja que falle en silencio.

    Una excepcion en el hilo era solo un warning de pytest, asi que el test
    seguia y evaluaba un buzon donde nunca se publico nada. Aca se recoge y se
    levanta en el hilo principal, donde falla por lo que realmente paso.
    """
    failure: list[BaseException] = []

    def guarded() -> None:
        try:
            work()
        except BaseException as exc:  # se reporta en el hilo principal
            failure.append(exc)

    worker = threading.Thread(target=guarded)
    worker.start()
    try:
        yield
    finally:
        worker.join(timeout=30)
    assert not worker.is_alive(), "el motor simulado quedo colgado"
    if failure:
        raise AssertionError("el motor simulado fallo") from failure[0]


# -- A. timeout antes del claim ------------------------------------------

def test_a_timed_out_request_is_withdrawn_so_it_cannot_run_later(bridge):
    """El caso que origino todo: nadie leyo el req y el caller se rindio."""
    assert bridge.send_and_wait("reportResult('x')", timeout=0.2) is None

    assert bridge.last_disposition is RequestDisposition.WITHDRAWN_NO_EXECUTION_OBSERVED
    assert _requests(bridge) == [], (
        "El request vencido sigue en el buzon: el Script Engine lo ejecutaria "
        "mas tarde, sin dueno."
    )


def test_the_withdrawn_request_leaves_no_response_behind(bridge):
    bridge.send_and_wait("reportResult('x')", timeout=0.2)

    assert _responses(bridge) == []


# -- B. timeout con la evaluacion ya en curso ----------------------------

def test_a_response_arriving_during_cancellation_is_reported_as_executed(patient_bridge):
    """El Script Engine ya habia leido el req: cancelar no deshace nada."""
    engine = _ScriptEngine(patient_bridge)

    def publish_while_the_caller_is_observing():
        # Publicar apenas Python retira el req cae, por construccion, dentro de
        # la ventana de observacion: esa es la carrera que el test quiere fijar.
        engine.publish(engine.await_withdrawal(), "tarde")

    with _running(publish_while_the_caller_is_observing):
        result = patient_bridge.send_and_wait("reportResult('x')", timeout=0.2)

    assert result is None
    assert patient_bridge.last_disposition is RequestDisposition.EXECUTED_LATE
    assert _responses(patient_bridge) == [], "La respuesta tardia debe descartarse, no quedar"


def test_a_request_already_consumed_by_the_engine_is_reported_as_executed(bridge):
    """El Script Engine borra el req solo DESPUES de escribir su respuesta."""
    original = bridge._write_atomic

    def consume_immediately(path, text):
        original(path, text)
        if path.name.startswith("req_"):
            path.unlink()

    bridge._write_atomic = consume_immediately

    assert bridge.send_and_wait("reportResult('x')", timeout=0.2) is None
    assert bridge.last_disposition is RequestDisposition.EXECUTED_LATE


# -- C/D. una respuesta vieja nunca es de una operacion nueva ------------

def test_two_sequential_requests_do_not_share_a_name(bridge):
    engine = _ScriptEngine(bridge)

    bridge.send_and_wait("reportResult('1')", timeout=0.15)
    bridge.send_and_wait("reportResult('2')", timeout=0.15)

    assert len(engine.names) == 2 and engine.names[0] != engine.names[1]


def test_a_stale_response_is_never_delivered_to_a_later_request(bridge, tmp_path):
    """Una respuesta huerfana de otra corrida no puede colarse en la siguiente."""
    (tmp_path / "res_9999_deadbeef_000001.txt").write_text("ajeno", encoding="utf-8")

    assert bridge.send_and_wait("reportResult('x')", timeout=0.2) is None
    assert bridge.last_disposition is RequestDisposition.WITHDRAWN_NO_EXECUTION_OBSERVED


def test_request_names_do_not_repeat_across_process_restarts(tmp_path):
    """El par (pid, seq) se repite al reiniciar; el token de arranque no."""
    first, second = FileBridge(tmp_path), FileBridge(tmp_path)

    assert first._next_name() != second._next_name()


# -- E. el camino feliz sigue intacto ------------------------------------

def test_a_response_that_arrives_in_time_is_returned_and_consumed(bridge):
    engine = _ScriptEngine(bridge)

    with _running(lambda: engine.publish(engine.await_request(), "ok")):
        result = bridge.send_and_wait("reportResult('ok')", timeout=5.0)

    assert result == "ok"
    assert bridge.last_disposition is RequestDisposition.COMPLETED
    assert _responses(bridge) == []
    # El motor real borra el req al terminar, pero ese borrado va en un
    # try/catch que traga el error: si falla, el mismo req se reejecuta en cada
    # tick. El buzon debe quedar limpio aunque el motor no lo haya limpiado.
    assert _requests(bridge) == []


# -- G. nada afirma que el comando no se ejecuto -------------------------

def test_no_disposition_claims_the_command_never_ran():
    """El nombre viejo, CANCELLED_UNCLAIMED, afirmaba mas de lo observable.

    Un `unlink` exitoso prueba que el motor no habia TERMINADO, no que no
    hubiera empezado; y no hay cota superior probada del tiempo de evaluacion,
    asi que no ver la respuesta durante una ventana acotada tampoco lo prueba.
    """
    assert not any(item.proves_no_execution for item in RequestDisposition)


def test_an_engine_that_already_claimed_the_request_is_never_reported_as_cancelled(
    patient_bridge,
):
    """Peor caso: el motor leyo el contenido ANTES de que Python cancelara.

    El archivo desaparece del buzon, pero la evaluacion sigue con el string ya
    en memoria. Retirarlo no deshace nada y no puede reportarse como si si.
    """
    engine = _ScriptEngine(patient_bridge)

    def finish_the_evaluation_after_the_withdrawal():
        name = engine.await_withdrawal()
        assert engine.claimed_source is not None, "el motor no alcanzo a leer el contenido"
        engine.publish(name, "ejecutado")

    with _running(finish_the_evaluation_after_the_withdrawal):
        patient_bridge.send_and_wait("reportResult('x')", timeout=0.05)

    assert patient_bridge.last_disposition is RequestDisposition.EXECUTED_LATE
    assert not patient_bridge.last_disposition.proves_no_execution


# -- H. reejecucion duplicada del motor ----------------------------------

def test_a_request_left_behind_by_the_engine_is_retired_by_the_server(bridge):
    """`removeFile` del motor va en un try/catch que traga el error.

    Si falla, el mismo req se vuelve a evaluar en cada tick hasta la purga de
    huerfanos a los 60 s. El servidor lo retira al cobrar la respuesta, que es
    una mitigacion: no convierte al protocolo en exactly-once.
    """
    engine = _ScriptEngine(bridge)

    # El motor contesta pero NO borra el req: ese es el fallo que se inyecta.
    with _running(lambda: engine.publish(engine.await_request(), "ok")):
        assert bridge.send_and_wait("x", timeout=5.0) == "ok"

    assert _requests(bridge) == []


def test_a_fire_and_forget_request_is_also_retired_from_the_mailbox(bridge):
    """`send()` no espera respuesta, asi que nadie retiraba su req.

    Las mutaciones IOS viajan por este camino. Si el motor no logra borrar el
    archivo, un `configureIosDevice` se reaplica en cada tick.
    """
    assert bridge.send("configureIosDevice('R1','...')")

    pending = _requests(bridge)
    assert len(pending) == 1

    # Simula al motor respondiendo sin poder limpiar.
    name = pending[0][4:-3]
    (bridge.dir / f"res_{name}.txt").write_text("hecho", encoding="utf-8")
    bridge.collect_completed()

    assert _requests(bridge) == []
    assert _responses(bridge) == []


# -- F. limpieza acotada --------------------------------------------------

def test_stale_files_of_this_process_are_purged_but_not_those_of_others(bridge, tmp_path):
    mine = f"req_{__import__('os').getpid()}_{bridge._boot}_000999.js"
    (tmp_path / mine).write_text("viejo", encoding="utf-8")
    foreign = tmp_path / "req_4321_cafebabe_000001.js"
    foreign.write_text("de otro proceso", encoding="utf-8")
    old = time.time() - 600
    for item in (tmp_path / mine, foreign):
        __import__("os").utime(item, (old, old))

    bridge.send_and_wait("reportResult('x')", timeout=0.2)

    assert not (tmp_path / mine).exists(), "el residuo propio deberia purgarse"
    assert foreign.exists(), "nunca se tocan requests de otro proceso"
