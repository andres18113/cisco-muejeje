"""Closeout of completed fire-and-forget file-mailbox responses."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from packet_tracer_mcp.infrastructure.execution.file_bridge import FileBridge


def _names(directory: Path, pattern: str) -> list[str]:
    """Return the sorted names matching one mailbox pattern."""
    return sorted(path.name for path in directory.glob(pattern))


def _answer_next_request(bridge: FileBridge, failures: list[BaseException]) -> None:
    """Answer the next synchronous request using the deployed mailbox protocol."""
    try:
        deadline = time.monotonic() + 10.0
        names = _names(bridge.dir, "req_*.js")
        while not names:
            assert time.monotonic() < deadline, "request was not published"
            time.sleep(0.005)
            names = _names(bridge.dir, "req_*.js")
        (request_name,) = names
        response = bridge.dir / f"res_{request_name[4:-3]}.txt"
        bridge._write_atomic(response, "sync")
        (bridge.dir / request_name).unlink(missing_ok=True)
    except BaseException as exc:
        failures.append(exc)


@pytest.mark.parametrize("method", ("send_and_wait", "dispatch_and_wait"))
def test_synchronous_request_retires_an_earlier_completed_send(tmp_path, method):
    """Later synchronous traffic closes an earlier fire-and-forget response."""
    bridge = FileBridge(tmp_path)
    assert bridge.send("configurePcIp('Server','FastEthernet0','192.0.2.10')")
    (request_name,) = _names(tmp_path, "req_*.js")
    fire_name = request_name[4:-3]
    # The engine completed the asynchronous evaluation: it removed the request
    # and published the response. Python still owns its pending name.
    (tmp_path / request_name).unlink()
    (tmp_path / f"res_{fire_name}.txt").write_text("done", encoding="utf-8")
    failures: list[BaseException] = []
    engine = threading.Thread(
        target=_answer_next_request,
        args=(bridge, failures),
        daemon=True,
    )
    engine.start()

    result = getattr(bridge, method)("reportResult('sync')", timeout=5.0)
    engine.join(timeout=10.0)

    assert not engine.is_alive()
    assert failures == []
    assert result == "sync" or result.body == "sync"
    assert _names(tmp_path, "req_*.js") == []
    assert _names(tmp_path, "res_*.txt") == []
    assert not bridge.has_pending_requests()
