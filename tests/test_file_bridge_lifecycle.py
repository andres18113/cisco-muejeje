"""Ciclo de vida de un request del buzon cuando el caller se rinde.

Por que existe:
El buzon dejaba el `req_*.js` en disco al vencer el timeout, a proposito, para
que el Script Engine lo procesara tarde. Un `enterCommand` asi se tipeaba en la
terminal sin dueno hasta un minuto despues, y contaminaba la ventana de
cualquier comando posterior. Estos tests simulan al Script Engine en vez de
depender de que Packet Tracer este corriendo.
"""

from __future__ import annotations

import time

import pytest

from src.packet_tracer_mcp.infrastructure.execution.file_bridge import (
    FileBridge,
    RequestDisposition,
)


@pytest.fixture
def bridge(tmp_path) -> FileBridge:
    return FileBridge(tmp_path, cancel_observation_seconds=0.25)


def _requests(bridge: FileBridge) -> list[str]:
    return sorted(item.name for item in bridge.dir.glob("req_*.js"))


def _responses(bridge: FileBridge) -> list[str]:
    return sorted(item.name for item in bridge.dir.glob("res_*.txt"))


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

def test_a_response_arriving_during_cancellation_is_reported_as_executed(bridge):
    """El Script Engine ya habia leido el req: cancelar no deshace nada."""
    name_holder = {}
    original = bridge._write_atomic

    def capture(path, text):
        original(path, text)
        if path.name.startswith("req_"):
            name_holder["name"] = path.name[4:-3]

    bridge._write_atomic = capture

    # Simula al Script Engine publicando la respuesta justo cuando el caller
    # ya se rindio y esta observando.
    import threading

    def late_response():
        time.sleep(0.25)
        (bridge.dir / f"res_{name_holder['name']}.txt").write_text("tarde", encoding="utf-8")

    worker = threading.Thread(target=late_response)
    worker.start()
    try:
        result = bridge.send_and_wait("reportResult('x')", timeout=0.2)
    finally:
        worker.join()

    assert result is None
    assert bridge.last_disposition is RequestDisposition.EXECUTED_LATE
    assert _responses(bridge) == [], "La respuesta tardia debe descartarse, no quedar"


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
    seen = []
    original = bridge._write_atomic

    def record(path, text):
        original(path, text)
        if path.name.startswith("req_"):
            seen.append(path.name)

    bridge._write_atomic = record

    bridge.send_and_wait("reportResult('1')", timeout=0.15)
    bridge.send_and_wait("reportResult('2')", timeout=0.15)

    assert len(seen) == 2 and seen[0] != seen[1]


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
    import threading

    names = []
    original = bridge._write_atomic

    def answer(path, text):
        original(path, text)
        if path.name.startswith("req_"):
            names.append(path.name[4:-3])

    bridge._write_atomic = answer

    def engine():
        while not names:
            time.sleep(0.01)
        (bridge.dir / f"res_{names[0]}.txt").write_text("ok", encoding="utf-8")

    worker = threading.Thread(target=engine)
    worker.start()
    try:
        result = bridge.send_and_wait("reportResult('ok')", timeout=5.0)
    finally:
        worker.join()

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


def test_an_engine_that_already_claimed_the_request_is_never_reported_as_cancelled(bridge):
    """Peor caso: el motor leyo el contenido ANTES de que Python cancelara.

    El archivo desaparece del buzon, pero la evaluacion sigue con el string ya
    en memoria. Retirarlo no deshace nada y no puede reportarse como si si.
    """
    import threading

    claimed = {}
    original = bridge._write_atomic

    def engine_reads_immediately(path, text):
        original(path, text)
        if path.name.startswith("req_"):
            claimed["name"] = path.name[4:-3]
            claimed["source"] = text  # el motor ya tiene el contenido

    bridge._write_atomic = engine_reads_immediately

    def finish_evaluation_late():
        # La evaluacion termina despues de que el caller se rindio y cancelo.
        time.sleep(0.15)
        (bridge.dir / f"res_{claimed['name']}.txt").write_text("ejecutado", encoding="utf-8")

    worker = threading.Thread(target=finish_evaluation_late)
    worker.start()
    try:
        bridge.send_and_wait("reportResult('x')", timeout=0.05)
    finally:
        worker.join()

    assert bridge.last_disposition is RequestDisposition.EXECUTED_LATE
    assert not bridge.last_disposition.proves_no_execution


# -- H. reejecucion duplicada del motor ----------------------------------

def test_a_request_left_behind_by_the_engine_is_retired_by_the_server(bridge):
    """`removeFile` del motor va en un try/catch que traga el error.

    Si falla, el mismo req se vuelve a evaluar en cada tick hasta la purga de
    huerfanos a los 60 s. El servidor lo retira al cobrar la respuesta, que es
    una mitigacion: no convierte al protocolo en exactly-once.
    """
    import threading

    names = []
    original = bridge._write_atomic

    def engine_answers_but_does_not_clean(path, text):
        original(path, text)
        if path.name.startswith("req_"):
            names.append(path.name[4:-3])

    bridge._write_atomic = engine_answers_but_does_not_clean

    def engine():
        while not names:
            time.sleep(0.01)
        (bridge.dir / f"res_{names[0]}.txt").write_text("ok", encoding="utf-8")
        # El motor NO borra el req: ese es el fallo que se inyecta.

    worker = threading.Thread(target=engine)
    worker.start()
    try:
        assert bridge.send_and_wait("x", timeout=5.0) == "ok"
    finally:
        worker.join()

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
