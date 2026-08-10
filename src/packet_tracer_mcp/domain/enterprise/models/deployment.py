"""Backend-neutral binding between semantic plans and deployed runtime objects."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ...models.plans import TopologyPlan

if TYPE_CHECKING:
    from .configuration_runtime import RuntimeConfigurationTarget


class IdentityMethod(str, Enum):
    RUNTIME_ID = "runtime_id"
    SEMANTIC_BINDING = "semantic_binding"
    COMPOSITE_FINGERPRINT = "composite_fingerprint"
    NAME_ONLY = "name_only"


class EnvironmentFingerprint(BaseModel):
    backend: str = "packet_tracer"
    backend_version: str = ""
    bridge_transport: str = ""
    extension_version: str = ""
    platform: str = ""
    capability_snapshot_version: str = ""
    runtime_mode: str = ""

    @property
    def semantic_hash(self) -> str:
        return _digest(self.model_dump(mode="json"))


class DeploymentBinding(BaseModel):
    semantic_device_id: str
    deployed_name: str
    model: str
    runtime_identifier: str = ""
    runtime_fingerprint: str = ""
    ports: list[str] = Field(default_factory=list)
    identity_method: IdentityMethod = IdentityMethod.SEMANTIC_BINDING
    creation_evidence: str = ""


class DeploymentIdentityError(ValueError):
    """Raised when a semantic target cannot be safely mapped to runtime."""


def requires_deployment_manifest(source_topology_hash_schema: str) -> bool:
    """Only the explicitly declared legacy schema may use name-based lookup."""

    return source_topology_hash_schema != "legacy-full-v1"


def validate_manifest_environment(
    manifest: DeploymentManifest,
    runtime_environment: EnvironmentFingerprint | None,
) -> None:
    """Require independently supplied runtime provenance to match deployment."""

    if runtime_environment is None:
        raise DeploymentIdentityError(
            "Runtime EnvironmentFingerprint is required for a DeploymentManifest."
        )
    if (
        runtime_environment.semantic_hash
        != manifest.environment_fingerprint.semantic_hash
        or runtime_environment.backend != manifest.backend
        or runtime_environment.backend_version != manifest.backend_version
    ):
        raise DeploymentIdentityError(
            "Runtime EnvironmentFingerprint does not match DeploymentManifest."
        )


class DeploymentManifest(BaseModel):
    deployment_id: str
    physical_topology_hash: str
    backend: str = "packet_tracer"
    backend_version: str = ""
    environment_fingerprint: EnvironmentFingerprint = Field(
        default_factory=EnvironmentFingerprint,
    )
    bindings: list[DeploymentBinding] = Field(default_factory=list)
    semantic_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def binding_for(self, semantic_device_id: str) -> DeploymentBinding:
        matches = [
            item for item in self.bindings
            if item.semantic_device_id == semantic_device_id
        ]
        if len(matches) != 1:
            raise DeploymentIdentityError(
                f"Deployment binding for {semantic_device_id!r} is missing or ambiguous."
            )
        return matches[0]

    def resolve_target(
        self,
        semantic_device_id: str,
        inventory: list[RuntimeConfigurationTarget],
    ) -> RuntimeConfigurationTarget:
        binding = self.binding_for(semantic_device_id)
        if binding.identity_method is IdentityMethod.RUNTIME_ID:
            if not binding.runtime_identifier:
                raise DeploymentIdentityError(
                    f"Manifest binding {semantic_device_id!r} declares runtime-ID "
                    "identity without a runtime identifier."
                )
            matches = [
                item for item in inventory
                if item.runtime_identifier == binding.runtime_identifier
            ]
            if not matches:
                raise DeploymentIdentityError(
                    f"Stable runtime identifier for {semantic_device_id!r} is no longer "
                    "present; refusing to downgrade to a name-only lookup."
                )
        else:
            if (
                binding.identity_method is IdentityMethod.COMPOSITE_FINGERPRINT
                and not binding.runtime_fingerprint
            ):
                raise DeploymentIdentityError(
                    f"Manifest binding {semantic_device_id!r} declares composite "
                    "fingerprint identity without a fingerprint."
                )
            matches = [
                item for item in inventory
                if item.device_name == binding.deployed_name
            ]
        if len(matches) != 1:
            raise DeploymentIdentityError(
                f"Runtime target for binding {semantic_device_id!r} is missing or ambiguous."
            )
        target = matches[0]
        if target.model != binding.model:
            raise DeploymentIdentityError(
                f"Runtime target model {target.model!r} does not match manifest model "
                f"{binding.model!r} for {semantic_device_id!r}."
            )
        if binding.runtime_fingerprint:
            if not target.runtime_fingerprint:
                raise DeploymentIdentityError(
                    f"Runtime fingerprint for {semantic_device_id!r} is unavailable; "
                    "the manifest binding cannot be revalidated."
                )
            if binding.runtime_fingerprint != target.runtime_fingerprint:
                raise DeploymentIdentityError(
                    f"Runtime fingerprint does not match manifest binding for {semantic_device_id!r}."
                )
        return target

    def compact_summary(self) -> dict[str, object]:
        methods: dict[str, int] = {}
        for binding in self.bindings:
            methods[binding.identity_method.value] = methods.get(binding.identity_method.value, 0) + 1
        return {
            "deployment_id": self.deployment_id,
            "physical_topology_hash": self.physical_topology_hash,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "environment_fingerprint": self.environment_fingerprint.semantic_hash,
            "binding_count": len(self.bindings),
            "identity_methods": dict(sorted(methods.items())),
            "semantic_hash": self.semantic_hash,
        }


def build_deployment_manifest(
    topology: TopologyPlan,
    inventory: list[RuntimeConfigurationTarget],
    *,
    fingerprint: EnvironmentFingerprint,
    deployment_id: str = "",
    created_at: datetime | None = None,
) -> DeploymentManifest:
    if not topology.physical_identity_hash:
        raise DeploymentIdentityError("Topology has no physical identity hash.")
    by_name: dict[str, list[RuntimeConfigurationTarget]] = {}
    for target in inventory:
        by_name.setdefault(target.device_name, []).append(target)
    bindings: list[DeploymentBinding] = []
    for device in sorted(topology.devices, key=lambda item: item.id or item.name):
        semantic_id = device.id or device.name
        matches = by_name.get(device.name, [])
        if len(matches) != 1:
            raise DeploymentIdentityError(
                f"Runtime target for {semantic_id!r} is missing or ambiguous during manifest creation."
            )
        target = matches[0]
        if target.model != device.model:
            raise DeploymentIdentityError(
                f"Runtime target model {target.model!r} does not match planned model "
                f"{device.model!r} for {semantic_id!r}."
            )
        if target.runtime_identifier and target.runtime_identifier_stable:
            method = IdentityMethod.RUNTIME_ID
        elif target.runtime_fingerprint:
            method = IdentityMethod.COMPOSITE_FINGERPRINT
        else:
            method = IdentityMethod.SEMANTIC_BINDING
        bindings.append(DeploymentBinding(
            semantic_device_id=semantic_id,
            deployed_name=device.name,
            model=device.model,
            runtime_identifier=(
                target.runtime_identifier if target.runtime_identifier_stable else ""
            ),
            runtime_fingerprint=target.runtime_fingerprint,
            ports=sorted(set(target.interfaces)),
            identity_method=method,
            creation_evidence="inventory_readback",
        ))
    manifest = DeploymentManifest(
        deployment_id=deployment_id or f"deployment/{topology.physical_identity_hash[:16]}",
        physical_topology_hash=topology.physical_identity_hash,
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint,
        bindings=bindings,
        created_at=created_at or datetime.now(timezone.utc),
    )
    manifest.semantic_hash = _digest({
        "schema": "deployment-manifest-v1",
        "physical_topology_hash": manifest.physical_topology_hash,
        "backend": manifest.backend,
        "backend_version": manifest.backend_version,
        "environment_fingerprint": manifest.environment_fingerprint.model_dump(mode="json"),
        "bindings": [
            item.model_dump(
                mode="json",
                exclude={"creation_evidence", "runtime_identifier"},
            )
            for item in manifest.bindings
        ],
    })
    return manifest


def resolve_manifest_targets(
    manifest: DeploymentManifest,
    *,
    physical_topology_hash: str,
    semantic_device_ids: list[str],
    inventory: list[RuntimeConfigurationTarget],
) -> dict[str, RuntimeConfigurationTarget]:
    """Resolve a plan's semantic devices without falling back to display names."""
    if manifest.physical_topology_hash != physical_topology_hash:
        raise DeploymentIdentityError(
            "DeploymentManifest physical topology hash does not match the plan source hash."
        )
    return {
        identifier: manifest.resolve_target(identifier, inventory)
        for identifier in sorted(set(semantic_device_ids))
    }


def runtime_target_fingerprint(
    device_name: str,
    model: str,
    interfaces: list[str],
) -> str:
    """Build the backend-neutral composite used by deployment and applicators."""

    return _digest({
        "schema": "runtime-target-fingerprint-v1",
        "device_name": device_name,
        "model": model,
        "interfaces": sorted(set(interfaces), key=str.casefold),
    })


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
