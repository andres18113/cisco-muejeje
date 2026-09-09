"""Pure CP-SCALE process version and executable identity policy."""

from __future__ import annotations

from collections.abc import Sequence


ProcessVersionPath = tuple[object, object, object]


def packet_tracer_version_path_error(
    processes: Sequence[ProcessVersionPath],
    expected_version: str,
) -> str:
    """Return the shared fail-closed version/path decision.

    ``ProductVersion`` legitimately falls back to ``FileVersion`` when it is
    absent or empty. Other value types are not evidence and are never coerced.
    """

    if not processes:
        return "No running Packet Tracer process was observed."

    versions: set[str] = set()
    paths: set[str] = set()
    for product_version, file_version, executable_path in processes:
        if product_version is not None and not isinstance(product_version, str):
            return "Packet Tracer version evidence has an invalid type."
        if file_version is not None and not isinstance(file_version, str):
            return "Packet Tracer version evidence has an invalid type."
        if not isinstance(executable_path, str):
            return "Packet Tracer executable path evidence has an invalid type."
        versions.add((product_version or "") or (file_version or ""))
        paths.add(executable_path)

    if (
        not isinstance(expected_version, str)
        or not expected_version
        or len(versions) != 1
        or not all(value.startswith(expected_version) for value in versions)
    ):
        return f"Packet Tracer version mismatch: {sorted(versions)!r}."
    if len(paths) != 1 or not next(iter(paths), ""):
        return f"Packet Tracer executable identity is ambiguous: {sorted(paths)!r}."
    return ""
