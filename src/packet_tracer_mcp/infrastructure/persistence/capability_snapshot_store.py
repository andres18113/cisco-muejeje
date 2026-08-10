"""Persistencia JSON de snapshots E3.5, confinada fuera del código fuente."""

from __future__ import annotations

import json
from pathlib import Path

from ...domain.enterprise.models.discovery import (
    BackendVersionProvenance,
    CapabilitySnapshot,
    SnapshotDiff,
)
from ...shared.utils import resolve_within, safe_name_component


class CapabilitySnapshotStore:
    """Almacena observaciones runtime y evidencia revisada separadamente."""

    def __init__(self, base_dir: str | Path = Path("data") / "capabilities") -> None:
        self.base_dir = Path(base_dir)

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
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(target)
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
            try:
                snapshots.append(CapabilitySnapshot.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return sorted(snapshots, key=lambda item: item.session.session.started_at)


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
