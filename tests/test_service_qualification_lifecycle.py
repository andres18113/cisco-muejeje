"""Read-only local lifecycle evidence for Server-PT diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

from packet_tracer_mcp.application.cp_scale_live.admission import (
    CPScaleProcessObservation,
)
from packet_tracer_mcp.application.cp_scale_live.contracts import CPScaleProcessRecord
from packet_tracer_mcp.infrastructure.execution.service_qualification_lifecycle import (
    PacketTracerDiagnosticLifecycleReader,
)

#: The creation identity a scripted reader answers with.
INCARNATION = "2026-09-20T09:15:00.0000000+00:00"


@dataclass
class _Processes:
    observed: CPScaleProcessObservation

    def read(self) -> CPScaleProcessObservation:
        return self.observed


@dataclass
class _Incarnation:
    """A scripted creation-identity reader, so no helper process is started.

    What these tests measure is how the pairing treats the mailbox and the
    process count. Left to the real reader they would also launch PowerShell
    for a PID that does not exist, whose answer none of them assert and whose
    latency is the environment's: on a loaded CI runner that one launch
    exceeded a five-second bound and turned a healthy preflight into an
    unobservable one. The reader's own bound is measured where it belongs, in
    `test_diagnostic_residual_corrections.py`.
    """

    value: str = INCARNATION

    def read(self, pid: int) -> str:
        assert isinstance(pid, int) and pid > 0
        return self.value


def _reader(processes, directory, incarnation: str = INCARNATION):
    """Compose the lifecycle reader over scripted local sources."""
    return PacketTracerDiagnosticLifecycleReader(
        process_reader=_Processes(CPScaleProcessObservation(processes=processes)),
        mailbox_dir=directory,
        incarnation_reader=_Incarnation(incarnation),
    )


def _process(pid: int = 4242) -> CPScaleProcessRecord:
    return CPScaleProcessRecord(
        pid=pid,
        name="PacketTracer",
        main_window_handle=101,
        product_version="9.0.1.0858",
        file_version="9.0.1.0858",
        executable_path=r"C:\Program Files\Cisco Packet Tracer\bin\PacketTracer.exe",
    )


def test_one_process_and_only_a_heartbeat_is_a_clean_local_preflight(tmp_path):
    """Heartbeat is ignored as liveness metadata, never treated as a command."""
    (tmp_path / "alive.txt").write_text("alive", encoding="utf-8")
    observed = _reader((_process(),), tmp_path).read()

    assert observed.process_id == 4242
    assert observed.mailbox_entries == ()
    assert observed.error == ""
    # The creation identity the pairing binds comes from the reading, and a
    # pairing without one is not a match later.
    assert observed.process_incarnation == INCARNATION


def test_an_unreadable_incarnation_leaves_the_pairing_unbound(tmp_path):
    """Unknown is not a match: the empty answer must survive to the gate."""
    observed = _reader((_process(),), tmp_path, incarnation="").read()

    assert observed.process_id == 4242
    assert observed.process_incarnation == ""
    assert observed.error == ""


def test_stale_request_response_and_temporary_artifacts_are_retained(tmp_path):
    """Containment refuses them later; the reader itself deletes nothing."""
    names = ("req_old.js", "req_old.js.tmp", "res_old.txt", "res_old.txt.tmp")
    for name in names:
        (tmp_path / name).write_text("stale", encoding="utf-8")
    observed = _reader((_process(),), tmp_path).read()

    assert observed.mailbox_entries == names
    assert all((tmp_path / name).exists() for name in names)


def test_zero_or_multiple_processes_are_unobservable(tmp_path):
    """A heartbeat cannot choose one process when OS identity cannot."""
    for processes, expected in (
        ((), "packet_tracer_process_count:0"),
        ((_process(), _process(4343)), "packet_tracer_process_count:2"),
    ):
        observed = _reader(processes, tmp_path).read()
        assert observed.error == expected
