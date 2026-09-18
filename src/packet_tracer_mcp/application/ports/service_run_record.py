"""Ports the enterprise-services use case orchestrates through.

The use case must be able to run against a temporary directory, a recording
fake or the real store without knowing which, and the domain must not learn
about filesystems to make that possible. So the contracts live here, the
concrete store lives in infrastructure, and neither imports the other.
"""

from __future__ import annotations

from typing import Protocol

from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.forwarding import ForwardingAddressObservation
from ...domain.enterprise.models.service_run_record import ServiceRunRecord


class RunRecordPersistenceError(RuntimeError):
    """Raised when a run record cannot be written or read without data loss.

    It is a typed failure rather than a bare OSError because the use case has
    to tell three situations apart: it could not create the record before any
    effect (refuse the run), it could not advance the record after an effect
    (stop dispatching, keep the last durable stage), and it could not read a
    record back (refuse to reuse it).
    """


class DeploymentManifestPort(Protocol):
    """Read access to the manifests the physical deployment path produced."""

    def latest_by_deployment_id(
        self,
        deployment_id: str,
    ) -> DeploymentManifest | None:
        """Return the newest manifest for that exact id, or None."""


class ServiceRunRecordPort(Protocol):
    """The write-ahead record lifecycle of one invocation."""

    def begin(self, record: ServiceRunRecord) -> str:
        """Create the record before any effect; raise if it cannot be written."""

    def advance(self, record: ServiceRunRecord) -> str:
        """Rewrite the record atomically at a stage boundary."""

    def complete(self, record: ServiceRunRecord) -> str:
        """Write the terminal record."""

    def load(self, deployment_id: str, run_id: str) -> ServiceRunRecord:
        """Read one record back, validating it; raise if it is unusable."""

    def retained_result_for(
        self,
        deployment_id: str,
        *,
        manifest_hash: str,
        configuration_semantic_hash: str,
        environment_fingerprint_hash: str,
    ) -> ServiceRunRecord | None:
        """Return a completed record whose bound identity matches exactly."""


class EndpointDriftObserver(Protocol):
    """A directed, read-only observation of one endpoint's current address.

    Admission needs this to refuse a conflicting endpoint before any effect.
    An observation that could not be made is UNREADABLE, which is a refusal
    input; it is never an empty endpoint.
    """

    def observe(
        self,
        runtime_device_name: str,
        interface: str,
    ) -> ForwardingAddressObservation:
        """Observe one endpoint's address on one interface."""
