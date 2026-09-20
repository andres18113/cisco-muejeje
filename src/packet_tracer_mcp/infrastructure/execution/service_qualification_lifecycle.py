"""Read-only local lifecycle evidence for executable service diagnostics."""

from __future__ import annotations

from pathlib import Path

from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
)
from .cp_scale_live_preflight import PowerShellPacketTracerProcessReader
from .file_bridge import bridge_dir


class PacketTracerDiagnosticLifecycleReader:
    """Bind one exact PT process and an empty mailbox before any transport.

    Reading OS process metadata and directory entries does not contact Packet
    Tracer. The reader never launches or stops a process and never removes a
    stale artifact; ambiguity is returned as an error for the domain gate.
    """

    def __init__(
        self,
        *,
        process_reader=None,
        mailbox_dir: Path | None = None,
    ) -> None:
        """Inject the two read-only sources used by this preflight."""
        self._process_reader = process_reader or PowerShellPacketTracerProcessReader()
        self._mailbox_dir = Path(mailbox_dir) if mailbox_dir else bridge_dir()

    def read(self) -> DiagnosticLifecycleObservation:
        """Return one exclusive process plus every stale command artifact."""
        process = self._process_reader.read()
        if process.error:
            return DiagnosticLifecycleObservation(error=process.error)
        if len(process.processes) != 1:
            return DiagnosticLifecycleObservation(
                error=f"packet_tracer_process_count:{len(process.processes)}"
            )
        try:
            entries = self._mailbox_entries()
        except OSError as exc:
            return DiagnosticLifecycleObservation(
                error=f"mailbox_inspection_failed:{type(exc).__name__}"
            )
        item = process.processes[0]
        return DiagnosticLifecycleObservation(
            process_id=item.pid,
            process_path=item.executable_path,
            product_version=item.product_version,
            file_version=item.file_version,
            mailbox_entries=entries,
        )

    def _mailbox_entries(self) -> tuple[str, ...]:
        """Return pending/temporary command artifacts, excluding heartbeat."""
        if not self._mailbox_dir.exists():
            return ()
        names: set[str] = set()
        for pattern in ("req_*", "res_*"):
            for path in self._mailbox_dir.glob(pattern):
                if path.is_file():
                    names.add(path.name)
        return tuple(sorted(names))
