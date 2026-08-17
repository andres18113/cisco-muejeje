"""Resolve deployed serial orientation from fresh registered IOS read-back."""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from ...domain.enterprise.models.deployment import (
    DeploymentIdentityError,
    DeploymentManifest,
    SerialEndpointOrientation,
    deployment_manifest_semantic_hash,
)
from ...domain.models.plans import LinkPlan, TopologyPlan


class SerialControllerObservation(BaseModel):
    """One exact serial controller observation from the current command window."""

    device_name: str
    interface: str
    orientation: SerialEndpointOrientation = SerialEndpointOrientation.UNRESOLVED
    clock_rate_bps: int | None = None
    observed: bool = False
    fresh_evidence: bool = False
    truncated: bool = False
    evidence_method: str = ""
    message: str = ""


class SerialOrientationRuntime(Protocol):
    def observe_serial_controller(
        self,
        device_name: str,
        interface: str,
    ) -> SerialControllerObservation: ...


class SerialEndpointOrientationEvidence(BaseModel):
    semantic_link_id: str
    semantic_device_id: str
    device_name: str
    interface: str
    orientation: SerialEndpointOrientation
    clock_rate_bps: int | None = None
    observed: bool
    fresh_evidence: bool
    truncated: bool
    evidence_method: str = ""
    message: str = ""


class SerialOrientationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"


class SerialOrientationResult(BaseModel):
    status: SerialOrientationStatus
    source_manifest_semantic_hash: str
    physical_topology_hash: str
    oriented_manifest: DeploymentManifest | None = None
    observations: list[SerialEndpointOrientationEvidence] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def verified(self) -> bool:
        return (
            self.status is SerialOrientationStatus.VERIFIED
            and self.oriented_manifest is not None
        )

    def compact_summary(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "source_manifest_semantic_hash": self.source_manifest_semantic_hash,
            "physical_topology_hash": self.physical_topology_hash,
            "oriented_manifest_semantic_hash": (
                self.oriented_manifest.semantic_hash if self.oriented_manifest else ""
            ),
            "observation_count": len(self.observations),
            "errors": list(self.errors),
        }


class SerialOrientationObserver:
    """Orient every serial link or return no usable manifest.

    The input topology and manifest are never mutated.  A successful result
    contains a deep-copied manifest whose semantic hash covers the observed
    orientations while its physical topology hash remains the E4 identity.
    """

    def __init__(self, runtime: SerialOrientationRuntime) -> None:
        self._runtime = runtime

    def observe(
        self,
        topology: TopologyPlan,
        manifest: DeploymentManifest,
    ) -> SerialOrientationResult:
        physical_hash = topology.physical_identity_hash
        errors: list[str] = []
        observations: list[SerialEndpointOrientationEvidence] = []

        if not physical_hash:
            errors.append("Topology has no physical topology hash.")
        elif manifest.physical_topology_hash != physical_hash:
            errors.append(
                "DeploymentManifest physical topology hash does not match E4."
            )
        elif manifest.semantic_hash != deployment_manifest_semantic_hash(manifest):
            errors.append("DeploymentManifest semantic hash is invalid.")
        if errors:
            return self._failure(manifest, physical_hash, observations, errors)

        serial_links = sorted(
            (
                link for link in topology.links
                if (link.cable or "").strip().casefold() == "serial"
            ),
            key=lambda item: _link_id(item),
        )
        link_ids = [_link_id(link) for link in serial_links]
        if len(link_ids) != len(set(link_ids)):
            return self._failure(
                manifest,
                physical_hash,
                observations,
                ["Serial topology contains duplicate semantic link identities."],
            )

        resolved: dict[tuple[str, str], SerialEndpointOrientation] = {}
        for link in serial_links:
            link_id = _link_id(link)
            try:
                binding = manifest.link_binding_for(link_id)
                endpoints = _bound_endpoints(link, binding)
            except DeploymentIdentityError as exc:
                errors.append(str(exc))
                continue

            link_evidence: list[SerialEndpointOrientationEvidence] = []
            for semantic_device_id, interface in endpoints:
                try:
                    device_binding = manifest.binding_for(semantic_device_id)
                except DeploymentIdentityError as exc:
                    errors.append(str(exc))
                    continue
                try:
                    observed = self._runtime.observe_serial_controller(
                        device_binding.deployed_name,
                        interface,
                    )
                except Exception as exc:
                    observed = SerialControllerObservation(
                        device_name=device_binding.deployed_name,
                        interface=interface,
                        message=(
                            "Serial controller observation raised "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    )
                evidence = SerialEndpointOrientationEvidence(
                    semantic_link_id=link_id,
                    semantic_device_id=semantic_device_id,
                    device_name=observed.device_name,
                    interface=observed.interface,
                    orientation=observed.orientation,
                    clock_rate_bps=observed.clock_rate_bps,
                    observed=observed.observed,
                    fresh_evidence=observed.fresh_evidence,
                    truncated=observed.truncated,
                    evidence_method=observed.evidence_method,
                    message=observed.message,
                )
                observations.append(evidence)
                link_evidence.append(evidence)
                problem = _evidence_problem(
                    evidence,
                    expected_device_name=device_binding.deployed_name,
                    expected_interface=interface,
                )
                if problem:
                    errors.append(
                        f"Serial endpoint {semantic_device_id!r} on {link_id!r}: "
                        + problem
                    )

            if len(link_evidence) != 2 or any(
                _evidence_problem(
                    item,
                    expected_device_name=manifest.binding_for(
                        item.semantic_device_id,
                    ).deployed_name,
                    expected_interface=next(
                        interface
                        for semantic_id, interface in endpoints
                        if semantic_id == item.semantic_device_id
                    ),
                )
                for item in link_evidence
            ):
                continue
            orientations = [item.orientation for item in link_evidence]
            if (
                orientations.count(SerialEndpointOrientation.DCE) != 1
                or orientations.count(SerialEndpointOrientation.DTE) != 1
            ):
                errors.append(
                    f"Serial link {link_id!r} requires exactly one DCE and one DTE."
                )
                continue
            for item in link_evidence:
                resolved[(link_id, item.semantic_device_id)] = item.orientation

        if errors:
            return self._failure(manifest, physical_hash, observations, errors)

        oriented = manifest.model_copy(deep=True)
        for link_binding in oriented.link_bindings:
            for endpoint in (link_binding.endpoint_a, link_binding.endpoint_b):
                orientation = resolved.get((
                    link_binding.semantic_link_id,
                    endpoint.semantic_device_id,
                ))
                if orientation is not None:
                    endpoint.orientation = orientation
        oriented.semantic_hash = deployment_manifest_semantic_hash(oriented)
        if oriented.physical_topology_hash != physical_hash:
            return self._failure(
                manifest,
                physical_hash,
                observations,
                ["Serial orientation changed the E4 physical topology hash."],
            )
        return SerialOrientationResult(
            status=SerialOrientationStatus.VERIFIED,
            source_manifest_semantic_hash=manifest.semantic_hash,
            physical_topology_hash=physical_hash,
            oriented_manifest=oriented,
            observations=observations,
        )

    @staticmethod
    def _failure(
        manifest: DeploymentManifest,
        physical_hash: str,
        observations: list[SerialEndpointOrientationEvidence],
        errors: list[str],
    ) -> SerialOrientationResult:
        return SerialOrientationResult(
            status=SerialOrientationStatus.FAILED,
            source_manifest_semantic_hash=manifest.semantic_hash,
            physical_topology_hash=physical_hash,
            observations=observations,
            errors=sorted(set(errors)),
        )


def _link_id(link: LinkPlan) -> str:
    return link.id or (
        f"{link.device_a}:{link.port_a}->{link.device_b}:{link.port_b}"
    )


def _bound_endpoints(link: LinkPlan, binding) -> list[tuple[str, str]]:
    expected = [
        (link.device_a_id or link.device_a, link.port_a),
        (link.device_b_id or link.device_b, link.port_b),
    ]
    observed = {
        endpoint.semantic_device_id: endpoint.interface
        for endpoint in (binding.endpoint_a, binding.endpoint_b)
    }
    if len(observed) != 2 or set(observed) != {item[0] for item in expected}:
        raise DeploymentIdentityError(
            f"Deployment link binding {_link_id(link)!r} does not match its "
            "serial topology endpoints."
        )
    for semantic_device_id, interface in expected:
        if observed.get(semantic_device_id) != interface:
            raise DeploymentIdentityError(
                f"Deployment link binding {_link_id(link)!r} does not bind exact "
                f"interface {interface!r} for {semantic_device_id!r}."
            )
    return expected


def _evidence_problem(
    evidence: SerialEndpointOrientationEvidence,
    *,
    expected_device_name: str,
    expected_interface: str,
) -> str:
    if not evidence.observed:
        return evidence.message or "controller state was not observed."
    if not evidence.fresh_evidence:
        return "controller evidence is not fresh."
    if evidence.truncated:
        return "controller evidence was truncated by the pager."
    if evidence.device_name != expected_device_name:
        return "controller evidence came from a different deployed device."
    if evidence.interface.casefold() != expected_interface.casefold():
        return "controller evidence names a different exact interface."
    if evidence.orientation not in {
        SerialEndpointOrientation.DCE,
        SerialEndpointOrientation.DTE,
    }:
        return "controller orientation is unresolved."
    return ""
