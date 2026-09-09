"""Pure read-only checks for the Packet Tracer OS process identity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ...application.cp_scale_live.process_identity import (
    packet_tracer_version_path_error,
)


def packet_tracer_process_error(
    processes: Sequence[Mapping[str, object]],
    expected_version: str,
) -> str:
    """Return a fail-closed process identity error, or an empty string.

    Packet Tracer's Qt windows are not reliably surfaced through
    ``Process.MainWindowHandle``: the exact running build can expose two
    same-binary processes with zero handles while its windows and file bridge
    remain live.  Window ownership is therefore not inferred from that field.
    The mutating runner separately requires a fresh bridge heartbeat and a
    complete semantic workspace observation.
    """

    return packet_tracer_version_path_error(
        tuple(
            (
                item.get("ProductVersion"),
                item.get("FileVersion"),
                item.get("Path"),
            )
            for item in processes
        ),
        expected_version,
    )
