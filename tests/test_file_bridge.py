"""Protocolo del transporte por archivo, sin Packet Tracer.

Un hilo simula el Script Engine: lista el buzón, procesa req_*, escribe res_*,
toca el heartbeat. Verifica el round-trip, la atomicidad y el heartbeat.
"""

import threading
import time

import pytest

from packet_tracer_mcp.infrastructure.execution.file_bridge import (
    HEARTBEAT_FRESH_S,
    FileBridge,
)

#: What a measured duration may read below the duration that actually
#: elapsed, once it is measured in integer nanoseconds: the clock's own
#: resolution and nothing else. A float difference of two `time.monotonic()`
#: samples carries one more term -- the representation granularity of
#: seconds-since-boot -- which an exact lower bound has no margin for.
CLOCK_RESOLUTION_NS = max(1, round(time.get_clock_info("monotonic").resolution * 1e9))


class FakeScriptEngine:
    """Emula el lado PT: procesa el buzón en un hilo, como haría el setInterval."""

    def __init__(self, directory, handler=lambda js: "OK"):
        """Bind the mailbox directory and what the fake engine answers."""
        self.dir = directory
        self.handler = handler
        self._stop = threading.Event()
        self._thread = None

    def start(self, heartbeat=True):
        """Run the mailbox loop in a thread, with or without a heartbeat."""

        def loop():
            while not self._stop.is_set():
                if heartbeat:
                    (self.dir / "alive.txt").write_text(
                        str(time.time()), encoding="utf-8"
                    )
                for req in sorted(self.dir.glob("req_*.js")):
                    name = req.stem[len("req_") :]
                    try:
                        js = req.read_text(encoding="utf-8")
                    except OSError:
                        continue
                    result = self.handler(js)
                    (self.dir / f"res_{name}.txt").write_text(result, encoding="utf-8")
                    req.unlink(missing_ok=True)
                time.sleep(0.05)

        self.dir.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the loop and join the thread."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)


@pytest.fixture
def bridge_dir(tmp_path):
    """Return a mailbox path inside the test's own directory."""
    return tmp_path / "bridge"


def test_send_and_wait_round_trip(bridge_dir):
    """One command reaches the engine and its answer comes back correlated."""
    fb = FileBridge(bridge_dir)
    se = FakeScriptEngine(bridge_dir, handler=lambda js: f"ran:{js.strip()}")
    se.start()
    try:
        result = fb.send_and_wait("getDeviceCount();", timeout=5)
    finally:
        se.stop()
    assert result == "ran:getDeviceCount();"


def test_fire_and_forget_is_consumed(bridge_dir):
    """A fire-and-forget command is processed and leaves no request behind."""
    seen = []
    fb = FileBridge(bridge_dir)
    se = FakeScriptEngine(bridge_dir, handler=lambda js: seen.append(js) or "OK")
    se.start()
    try:
        assert fb.send("addDevice('R1','2911',0,0);")
        time.sleep(0.5)
    finally:
        se.stop()
    assert seen == ["addDevice('R1','2911',0,0);"]
    # El SE borra el req tras procesarlo: el buzón no crece.
    assert list(bridge_dir.glob("req_*")) == []


def test_timeout_when_no_script_engine(bridge_dir):
    """Sin nadie procesando, send_and_wait agota el timeout y devuelve None.

    The bound is measured in integer nanoseconds: a float difference of two
    `time.monotonic()` samples can read one ulp of the clock value below the
    duration that actually elapsed, and an exact lower bound has no margin
    for that.
    """
    fb = FileBridge(bridge_dir)
    t0 = time.monotonic_ns()
    result = fb.send_and_wait("x();", timeout=0.5)
    elapsed = time.monotonic_ns() - t0
    assert result is None
    assert elapsed >= 500_000_000 - CLOCK_RESOLUTION_NS


def test_pt_alive_reflects_heartbeat(bridge_dir):
    """Liveness follows the heartbeat file, and a stale one is not alive."""
    fb = FileBridge(bridge_dir)
    assert not fb.pt_alive()  # aún no existe el buzón

    se = FakeScriptEngine(bridge_dir)
    se.start(heartbeat=True)
    try:
        time.sleep(0.2)
        assert fb.pt_alive()
    finally:
        se.stop()

    # Tras parar el heartbeat, envejece y deja de considerarse vivo.
    stale = time.time() - HEARTBEAT_FRESH_S - 1
    import os

    os.utime(bridge_dir / "alive.txt", (stale, stale))
    assert not fb.pt_alive()


def test_newlines_are_written_as_exact_bytes(bridge_dir):
    r"""El req conserva los bytes exactos del comando.

    Regresión: en Windows `write_text` traducía \n a \r\n, y un CR/LF real
    dentro de un string literal JS es SyntaxError, así que un
    `configureIosDevice` con saltos de línea llegaba corrupto al Script
    Engine.
    """
    fb = FileBridge(bridge_dir)
    fb._ensure()
    payload = 'configureIosDevice("R1","enable\nhostname R1\nend");'
    target = bridge_dir / "probe.js"
    fb._write_atomic(target, payload)

    raw = target.read_bytes()
    assert b"\r\n" not in raw, "el \\n se tradujo a \\r\\n — corrompe strings JS"
    assert raw == payload.encode("utf-8"), "los bytes no son exactos"


def test_no_partial_reads_under_concurrency(bridge_dir):
    """La escritura atómica: el SE nunca ve un req a medio escribir.

    Se encadenan muchos round-trips con un payload grande; si hubiera lecturas
    parciales, el eco no coincidiría.
    """
    payload = "configureIosDevice('R1', '" + "x" * 5000 + "');"
    fb = FileBridge(bridge_dir)
    se = FakeScriptEngine(bridge_dir, handler=lambda js: str(len(js)))
    se.start()
    try:
        for _ in range(20):
            r = fb.send_and_wait(payload, timeout=5)
            assert r == str(len(payload)), "lectura parcial detectada"
    finally:
        se.stop()
