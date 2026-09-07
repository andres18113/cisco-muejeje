"""Persistencia JSON de snapshots E3.5, confinada fuera del código fuente."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic_core import SchemaError

from ...domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    CapabilitySnapshot,
    SnapshotDiff,
)
from ...shared.utils import resolve_within, safe_name_component


DEFAULT_BASE_DIR = Path("data") / "capabilities"


class UnusableCapabilitySnapshotError(RuntimeError):
    """One enumerated snapshot could not be turned into evidence.

    Callers that only need to know the read did not happen catch this; the
    subclasses say whether the file was unreadable or simply no longer there.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"Unusable capability snapshot {self.path}: {reason}")


class CorruptCapabilitySnapshotError(UnusableCapabilitySnapshotError):
    """A stored snapshot exists but cannot be read as evidence."""


class VanishedCapabilitySnapshotError(UnusableCapabilitySnapshotError):
    """A snapshot was enumerated and then disappeared before it was read."""


class CapabilitySnapshotStore:
    """Almacena observaciones runtime y evidencia revisada separadamente."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        # Read the module default at call time: it is machine state, and the
        # test suite redirects it so no test composes evidence from whatever
        # this checkout happens to have on disk.
        self.base_dir = Path(base_dir) if base_dir is not None else Path(DEFAULT_BASE_DIR)

    def save_runtime(self, snapshot: CapabilitySnapshot) -> Path:
        return self._save("runtime", snapshot)

    def save_verified(self, snapshot: CapabilitySnapshot) -> Path:
        return self._save("verified", snapshot)

    def list_runtime(self, packet_tracer_version: str | None = None) -> list[CapabilitySnapshot]:
        return self._list("runtime", packet_tracer_version)

    def list_verified(self, packet_tracer_version: str | None = None) -> list[CapabilitySnapshot]:
        return self._list("verified", packet_tracer_version)

    def latest_runtime(self, packet_tracer_version: str | None = None) -> CapabilitySnapshot | None:
        snapshots = self.list_runtime(packet_tracer_version)
        return snapshots[-1] if snapshots else None

    def find_cached(
        self,
        packet_tracer_version: str | None,
        models: list[str],
        capabilities: list[str],
        probe_schema_version: int,
        environment_fingerprint: str = "",
        probe_fingerprints: dict[str, str] | None = None,
        initial_inventory_hash: str = "",
    ) -> CapabilitySnapshot | None:
        """Sólo reutiliza la misma versión de PT y el mismo esquema de probe."""
        wanted_models = set(models)
        wanted_capabilities = set(capabilities)
        wanted_probe_fingerprints = probe_fingerprints or {}
        for snapshot in reversed(self.list_runtime(packet_tracer_version)):
            if snapshot.probe_schema_version != probe_schema_version:
                continue
            if not snapshot.reusable:
                continue
            if (
                snapshot.backend_version_provenance
                is BackendVersionProvenance.UNKNOWN
            ):
                # Dos builds distintas de Packet Tracer producen snapshots
                # indistinguibles cuando nadie pudo nombrar la versión. La
                # evidencia sigue siendo válida en su propia sesión, pero no
                # puede cruzar a otra.
                continue
            if (
                environment_fingerprint
                and snapshot.environment_fingerprint != environment_fingerprint
            ):
                continue
            if (
                initial_inventory_hash
                and snapshot.initial_inventory_hash != initial_inventory_hash
            ):
                continue
            if any(
                snapshot.probe_fingerprints.get(key) != fingerprint
                for key, fingerprint in wanted_probe_fingerprints.items()
            ):
                continue
            present_models = {
                descriptor.identity.canonical_id or descriptor.identity.runtime_id
                for descriptor in snapshot.session.devices
            }
            present_capabilities = {
                (result.model, result.capability)
                for result in snapshot.session.results
            }
            if wanted_models <= present_models and all(
                (model, capability) in present_capabilities
                for model in wanted_models for capability in wanted_capabilities
            ):
                return snapshot
        return None

    def _save(self, scope: str, snapshot: CapabilitySnapshot) -> Path:
        version = safe_name_component(snapshot.packet_tracer_version or "unknown", "unknown")
        target_dir = resolve_within(self.base_dir, scope, version)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = resolve_within(target_dir, f"{snapshot.stable_hash()}.json")
        # The temporary must belong to this writer, and that has to be the OS
        # refusing to hand out a name twice rather than a random suffix being
        # unlikely to repeat. `stable_hash` ignores session_id and started_at,
        # so two different snapshots share one target; the loser of a name
        # collision would not get an error, it would get someone else's
        # half-written body. `mkstemp` creates with O_EXCL and retries, in the
        # target's own directory so the replace stays atomic.
        handle, name = tempfile.mkstemp(
            dir=target_dir, prefix=f"{target.name}.", suffix=".tmp",
        )
        temporary = Path(name)
        try:
            # Default newline handling, matching the previous `write_text`, so
            # stored bytes are unchanged on every platform.
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(snapshot.model_dump_json(indent=2))
            temporary.replace(target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def _list(self, scope: str, packet_tracer_version: str | None) -> list[CapabilitySnapshot]:
        root = resolve_within(self.base_dir, scope)
        if not root.exists():
            return []
        if packet_tracer_version is None:
            files = sorted(root.glob("*/*.json"))
        else:
            version = safe_name_component(packet_tracer_version, "unknown")
            files = sorted(resolve_within(root, version).glob("*.json"))
        snapshots: list[CapabilitySnapshot] = []
        for path in files:
            snapshots.append(self._load(path))
        return sorted(snapshots, key=lambda item: item.session.session.started_at)

    def _load(self, path: Path) -> CapabilitySnapshot:
        """Read one enumerated snapshot, or say which file made that impossible.

        Absence and failure are different answers and must stay that way. An
        empty or missing directory is absence, and `_list` answers it with an
        empty list before reaching here. Everything this method sees was
        already enumerated, so it is evidence the store held a moment ago.

        A file that disappears between the listing and the read is therefore
        not absence either: returning the rest would answer with a set the
        store was never in, assembled from two different instants. That is an
        inconsistent read, and it is named rather than smoothed over -- as is
        an unreadable file, invalid JSON, a payload that does not match the
        schema, and a structurally incompatible one. All of them abort the
        whole read, because returning the survivors would quietly downgrade
        evidence that exists into evidence that does not.
        """
        try:
            body = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise VanishedCapabilitySnapshotError(
                path, "enumerated by this read and gone before it could be read",
            ) from exc
        except OSError as exc:
            raise CorruptCapabilitySnapshotError(path, f"unreadable ({exc})") from exc
        try:
            return CapabilitySnapshot.model_validate_json(body)
        except (ValueError, json.JSONDecodeError) as exc:
            raise CorruptCapabilitySnapshotError(
                path, "does not match the capability snapshot schema",
            ) from exc
        except SchemaError as exc:
            # Not a ValueError, so this used to escape the persistence
            # boundary raw, naming nothing the caller could act on.
            raise CorruptCapabilitySnapshotError(
                path, f"structurally incompatible with the snapshot schema ({exc})",
            ) from exc


def compare_snapshots(old: CapabilitySnapshot, new: CapabilitySnapshot) -> SnapshotDiff:
    """Compara hechos observados sin usar timestamps ni texto de diagnóstico."""
    old_models = _model_map(old)
    new_models = _model_map(new)
    common = sorted(set(old_models) & set(new_models))
    old_results = _result_map(old)
    new_results = _result_map(new)
    return SnapshotDiff(
        models_added=sorted(set(new_models) - set(old_models)),
        models_removed=sorted(set(old_models) - set(new_models)),
        ports_changed=[
            model for model in common
            if _port_names(old_models[model]) != _port_names(new_models[model])
        ],
        modules_changed=[
            model for model in common
            if _module_names(old_models[model]) != _module_names(new_models[model])
        ],
        capabilities_changed=sorted(
            f"{model}:{capability}"
            for model, capability in set(old_results) & set(new_results)
            if old_results[(model, capability)] != new_results[(model, capability)]
        ),
    )


def _model_map(snapshot: CapabilitySnapshot) -> dict[str, object]:
    return {
        descriptor.identity.canonical_id or descriptor.identity.runtime_id or descriptor.identity.display_name: descriptor
        for descriptor in snapshot.session.devices
    }


def _result_map(snapshot: CapabilitySnapshot) -> dict[tuple[str, str], str]:
    return {
        (result.model, result.capability): result.status.value
        for result in snapshot.session.results
    }


def _port_names(descriptor: object) -> list[str]:
    return [port.name for port in descriptor.ports]


def _module_names(descriptor: object) -> list[tuple[str, str | None]]:
    return [(module.name, module.slot) for module in descriptor.modules]
