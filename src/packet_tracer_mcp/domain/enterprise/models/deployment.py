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


class SerialEndpointOrientation(str, Enum):
    """Que extremo entrega el reloj, resuelto o todavia sin resolver."""

    DCE = "dce"
    DTE = "dte"
    UNRESOLVED = "unresolved"


class DeploymentLinkEndpoint(BaseModel):
    """Un extremo exacto: dispositivo semantico mas su interfaz observada."""

    semantic_device_id: str
    interface: str
    orientation: SerialEndpointOrientation = SerialEndpointOrientation.UNRESOLVED


class DeploymentLinkBinding(BaseModel):
    """Enlace semantico atado a lo que existe en el backend.

    `runtime_link_identifier` es identidad de runtime y vive solo aqui: no
    entra en el hash fisico ni en la identidad semantica del plan, porque un
    redespliegue del mismo enlace produce otro identificador sin que la red
    haya cambiado.
    """

    semantic_link_id: str
    endpoint_a: DeploymentLinkEndpoint
    endpoint_b: DeploymentLinkEndpoint
    runtime_link_identifier: str = ""
    runtime_link_identity_observed: bool = False

    def endpoint_for(self, semantic_device_id: str) -> DeploymentLinkEndpoint:
        for endpoint in (self.endpoint_a, self.endpoint_b):
            if endpoint.semantic_device_id == semantic_device_id:
                return endpoint
        raise DeploymentIdentityError(
            f"Link {self.semantic_link_id!r} has no endpoint on "
            f"{semantic_device_id!r}."
        )

    @property
    def dce_endpoint(self) -> DeploymentLinkEndpoint | None:
        for endpoint in (self.endpoint_a, self.endpoint_b):
            if endpoint.orientation is SerialEndpointOrientation.DCE:
                return endpoint
        return None


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
    link_bindings: list[DeploymentLinkBinding] = Field(default_factory=list)
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

    def link_binding_for(self, semantic_link_id: str) -> DeploymentLinkBinding:
        matches = [
            item for item in self.link_bindings
            if item.semantic_link_id == semantic_link_id
        ]
        if len(matches) != 1:
            raise DeploymentIdentityError(
                f"Deployment link binding for {semantic_link_id!r} is missing "
                "or ambiguous."
            )
        return matches[0]

    def resolve_serial_clock_target(
        self,
        semantic_link_id: str,
        semantic_device_id: str,
        inventory: list[RuntimeConfigurationTarget],
        *,
        observed_orientation: SerialEndpointOrientation | None = None,
        observed_interface: str | None = None,
    ) -> tuple[RuntimeConfigurationTarget, str]:
        """Resuelve donde aplicar un reloj, o se niega antes de mutar.

        El reloj es del DCE. Un extremo equivocado, una interfaz que el runtime
        no expone o una orientacion que el backend contradice bloquean aqui,
        que es antes de que exista ninguna mutacion.
        """
        link = self.link_binding_for(semantic_link_id)
        endpoint = link.endpoint_for(semantic_device_id)
        if endpoint.orientation is not SerialEndpointOrientation.DCE:
            raise DeploymentIdentityError(
                f"{semantic_device_id!r} is the {endpoint.orientation.value} end of "
                f"{semantic_link_id!r}; a clock belongs to the DCE."
            )
        if (
            observed_orientation is not None
            and observed_orientation is not SerialEndpointOrientation.DCE
        ):
            raise DeploymentIdentityError(
                f"Runtime observed {semantic_device_id!r} as "
                f"{observed_orientation.value} while the manifest binds it as DCE; "
                "refusing to swap orientation."
            )
        return self.resolve_link_endpoint_target(
            semantic_link_id, semantic_device_id, inventory,
            observed_interface=observed_interface,
        )

    def resolve_link_endpoint_target(
        self,
        semantic_link_id: str,
        semantic_device_id: str,
        inventory: list[RuntimeConfigurationTarget],
        *,
        observed_interface: str | None = None,
    ) -> tuple[RuntimeConfigurationTarget, str]:
        """Resuelve el extremo de un enlace, o se niega antes de mutar.

        Independiente del medio: la orientacion DCE/DTE solo importa para un
        reloj serial, y esa comprobacion vive en quien la necesita. Un
        dispositivo ajeno al enlace, una interfaz que el runtime no expone o
        una que no es la observada bloquean aqui, antes de que exista mutacion
        alguna.
        """
        link = self.link_binding_for(semantic_link_id)
        endpoint = link.endpoint_for(semantic_device_id)
        target = self.resolve_target(semantic_device_id, inventory)
        if endpoint.interface not in target.interfaces:
            raise DeploymentIdentityError(
                f"Interface {endpoint.interface!r} is not present on the resolved "
                f"runtime target for {semantic_device_id!r}."
            )
        # Que la interfaz exista en el dispositivo no prueba que sostenga este
        # enlace: un 2911 con HWIC-2T expone Serial0/0/0 y Serial0/0/1, y un
        # 3560 expone veinticuatro FastEthernet. Un manifest apuntando a otra
        # seria auto-consistente.
        if observed_interface is not None and observed_interface != endpoint.interface:
            raise DeploymentIdentityError(
                f"Link {semantic_link_id!r} was observed on "
                f"{observed_interface!r} while the manifest binds it to "
                f"{endpoint.interface!r}."
            )
        return target, endpoint.interface

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
            "link_binding_count": len(self.link_bindings),
            "identity_methods": dict(sorted(methods.items())),
            "semantic_hash": self.semantic_hash,
        }


def build_deployment_manifest(
    topology: TopologyPlan,
    inventory: list[RuntimeConfigurationTarget],
    *,
    fingerprint: EnvironmentFingerprint,
    deployment_id: str = "",
    link_bindings: list[DeploymentLinkBinding] | None = None,
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
    ordered_link_bindings = sorted(
        link_bindings or [],
        key=lambda item: item.semantic_link_id,
    )
    if link_bindings is not None:
        expected_link_ids = {
            item.id or f"{item.device_a}:{item.port_a}->{item.device_b}:{item.port_b}"
            for item in topology.links
        }
        observed_link_ids = [item.semantic_link_id for item in ordered_link_bindings]
        if len(observed_link_ids) != len(set(observed_link_ids)):
            raise DeploymentIdentityError(
                "Deployment link bindings contain duplicate semantic link identities."
            )
        if set(observed_link_ids) != expected_link_ids:
            raise DeploymentIdentityError(
                "Deployment link bindings do not cover the exact semantic link plan."
            )
        device_bindings = {item.semantic_device_id: item for item in bindings}
        planned_by_id = {
            item.id or f"{item.device_a}:{item.port_a}->{item.device_b}:{item.port_b}": item
            for item in topology.links
        }
        for link_binding in ordered_link_bindings:
            planned = planned_by_id[link_binding.semantic_link_id]
            expected_devices = {
                planned.device_a_id or planned.device_a,
                planned.device_b_id or planned.device_b,
            }
            observed_devices = {
                link_binding.endpoint_a.semantic_device_id,
                link_binding.endpoint_b.semantic_device_id,
            }
            if observed_devices != expected_devices:
                raise DeploymentIdentityError(
                    f"Deployment link binding {link_binding.semantic_link_id!r} "
                    "does not match its semantic endpoints."
                )
            expected_interfaces = {
                (planned.device_a_id or planned.device_a): planned.port_a,
                (planned.device_b_id or planned.device_b): planned.port_b,
            }
            for endpoint in (link_binding.endpoint_a, link_binding.endpoint_b):
                if expected_interfaces.get(endpoint.semantic_device_id) != endpoint.interface:
                    raise DeploymentIdentityError(
                        f"Observed interface {endpoint.interface!r} for link "
                        f"{link_binding.semantic_link_id!r} does not match the planned "
                        f"interface for {endpoint.semantic_device_id!r}."
                    )
                device_binding = device_bindings.get(endpoint.semantic_device_id)
                if device_binding is None or endpoint.interface not in device_binding.ports:
                    raise DeploymentIdentityError(
                        f"Observed interface {endpoint.interface!r} for link "
                        f"{link_binding.semantic_link_id!r} is absent from the fresh "
                        f"device binding {endpoint.semantic_device_id!r}."
                    )
    manifest = DeploymentManifest(
        deployment_id=deployment_id or f"deployment/{topology.physical_identity_hash[:16]}",
        physical_topology_hash=topology.physical_identity_hash,
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint,
        bindings=bindings,
        link_bindings=ordered_link_bindings,
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
        "link_bindings": [
            item.model_dump(
                mode="json",
                exclude={
                    "runtime_link_identifier",
                    "runtime_link_identity_observed",
                },
            )
            for item in manifest.link_bindings
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
