"""Pure read-only checks for the Packet Tracer OS process identity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


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

    if not processes:
        return "No running Packet Tracer process was observed."
    versions = {
        str(item.get("ProductVersion") or item.get("FileVersion") or "")
        for item in processes
    }
    paths = {str(item.get("Path") or "") for item in processes}
    if len(versions) != 1 or not all(
        value.startswith(expected_version) for value in versions
    ):
        return f"Packet Tracer version mismatch: {sorted(versions)!r}."
    if len(paths) != 1 or not next(iter(paths), ""):
        return f"Packet Tracer executable identity is ambiguous: {sorted(paths)!r}."
    return ""
