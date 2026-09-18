"""One resolution of service capability, shared by every consumer.

Compilation, admission and execution have to agree about what the build
supports. Before this module each of them reached into the capability mapping
with its own key, and the one that mattered most was wrong: a client
expectation resolved the SERVER's profile, so a PC-PT was credited with the
Server-PT's behavioural evidence. "The DNS service is behaviourally supported"
and "this PC can be driven to resolve a name" are separate claims about
separate processes on separate models.

Two questions, two keys, one answer each:

- applying an action resolves `"<host_model>:<action_type>"` first, and falls
  back to the service profile of the same host model. The fallback is not a
  loophole: the profile IS the explicit record for a server-hosted action, and
  a host model with neither record resolves UNKNOWN.
- observing an expectation resolves `"<target_model>:<kind>"`, where the target
  is the CLIENT for a client expectation. A client expectation with no record
  is UNKNOWN. It never falls back to the server profile, because that fallback
  is the defect this module exists to remove.

Readiness stays a property of the service family, so it is read from the
profile in both cases: whether Packet Tracer exposes any registered
observation for NTP is not a fact about the PC that would run it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..models.capabilities import CapabilityStatus
from ..models.evidence import CapabilityReadiness
from ..models.service_plan import (
    ClientOperationCapability,
    ServiceAction,
    ServiceCapabilityProfile,
    ServiceDefinition,
    ServiceEvidenceKind,
    ServiceType,
    ServiceVerificationExpectation,
)


@dataclass(frozen=True)
class CapabilityResolution:
    """What the catalog says about one operation on one target model."""

    key: str
    support: CapabilityStatus
    provenance: str = ""
    readiness: CapabilityReadiness | None = None
    source: str = ""

    @property
    def is_supported(self) -> bool:
        """Whether the operation may be attempted at all."""
        return self.support is CapabilityStatus.SUPPORTED


def profile_for(
    records: Mapping[str, object],
    *,
    model: str,
    service_type: ServiceType,
) -> ServiceCapabilityProfile | None:
    """Return the service profile for one model, if the catalog has one."""
    candidate = records.get(f"{model}:{service_type.value}")
    return candidate if isinstance(candidate, ServiceCapabilityProfile) else None


def _operation(
    records: Mapping[str, object],
    key: str,
) -> ClientOperationCapability | None:
    candidate = records.get(key)
    return candidate if isinstance(candidate, ClientOperationCapability) else None


def resolve_action_capability(
    records: Mapping[str, object],
    action: ServiceAction,
) -> CapabilityResolution:
    """Resolve applying one action on the model that actually hosts it."""
    key = f"{action.host_model}:{action.action_type.value}"
    operation = _operation(records, key)
    if operation is not None:
        return CapabilityResolution(
            key=key,
            support=operation.support,
            provenance=operation.provenance.value,
            source=operation.source,
        )
    profile = profile_for(
        records, model=action.host_model, service_type=action.service_type
    )
    if profile is None:
        return CapabilityResolution(key=key, support=CapabilityStatus.UNKNOWN)
    return CapabilityResolution(
        key=key,
        support=profile.action_application_support.get(
            action.action_type.value, profile.application_support
        ),
        provenance=profile.provenance.value,
        source=profile.source,
    )


def resolve_verification_capability(
    records: Mapping[str, object],
    expectation: ServiceVerificationExpectation,
    service: ServiceDefinition,
) -> CapabilityResolution:
    """Resolve observing one expectation on the model that performs it."""
    target_model = expectation.target_model or service.host_model
    key = f"{target_model}:{expectation.kind.value}"
    profile = profile_for(
        records, model=service.host_model, service_type=service.service_type
    )
    readiness = (
        profile.capability_readiness.get("behavioral_verification")
        if profile is not None
        and expectation.evidence_kind is not ServiceEvidenceKind.DIRECT_STATE
        else None
    )
    operation = _operation(records, key)
    if operation is not None:
        return CapabilityResolution(
            key=key,
            support=operation.support,
            provenance=operation.provenance.value,
            readiness=readiness,
            source=operation.source,
        )
    if expectation.client_device_id:
        # A client expectation with no record of its own resolves UNKNOWN. The
        # server's profile is evidence about the server.
        return CapabilityResolution(
            key=key, support=CapabilityStatus.UNKNOWN, readiness=readiness
        )
    if profile is None:
        return CapabilityResolution(key=key, support=CapabilityStatus.UNKNOWN)
    support = (
        profile.direct_readback_support
        if expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
        else profile.behavioral_verification_support
    )
    return CapabilityResolution(
        key=key,
        support=support,
        provenance=profile.provenance.value,
        readiness=readiness,
        source=profile.source,
    )


def provenance_by_key(records: Mapping[str, object]) -> dict[str, str]:
    """Return the provenance level the catalog declares for every record."""
    levels: dict[str, str] = {}
    for key, record in records.items():
        provenance = getattr(record, "provenance", None)
        if provenance is not None:
            levels[key] = str(getattr(provenance, "value", provenance))
    return dict(sorted(levels.items()))
