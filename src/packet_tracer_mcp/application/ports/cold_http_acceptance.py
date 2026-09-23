"""Ports the cold-HTTP acceptance envelope reaches its stores through.

The envelope reads the product's run history and reads back one run record;
it writes only its own envelope. Both contracts live here so the coordinator
can run against temporary directories or the real stores without knowing
which, and so the domain never learns about files.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ...domain.enterprise.models.cold_http_acceptance import (
    AcceptancePublication,
    ColdHttpAcceptanceEnvelope,
)
from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
)
from ...domain.enterprise.models.service_run_record import ServiceRunRecord
from .service_run_record import ServiceRunRecordPort


class AcceptanceRunRecordPort(ServiceRunRecordPort, Protocol):
    """The product store, plus the two reads the envelope needs from it."""

    def deployment_history(self, deployment_id: str) -> tuple[str, ...]:
        """Name every stored entry of one deployment; raise when unlistable."""

    def load_evidence(
        self, deployment_id: str, run_id: str
    ) -> tuple[ServiceRunRecord, str, str]:
        """Read one record once and return it with its path and byte digest."""


class AcceptanceEnvelopePort(Protocol):
    """The write-ahead lifecycle of one immutable acceptance envelope."""

    def begin(self, envelope: ColdHttpAcceptanceEnvelope) -> str:
        """Create the envelope before any contact; raise if it exists."""

    def complete(
        self,
        envelope: ColdHttpAcceptanceEnvelope,
        *,
        checkpoint: Callable[[str], None] | None = None,
    ) -> str:
        """Write the terminal envelope once; a completed one is immutable.

        `checkpoint(boundary)` is called after each controlled step that
        shapes the published bytes (`envelope_reload`,
        `envelope_serialization`, `envelope_flush`, the last immediately before
        the terminal link). If it raises, nothing is linked and the exception
        propagates.
        """

    def stored(
        self, envelope: ColdHttpAcceptanceEnvelope, *, completed: bool
    ) -> str | None:
        """Return the path this invocation stored at one stage, or None.

        It decides an interrupted write whose outcome is unknown; an
        unreadable stored file raises instead of answering.
        """

    def record_publication(
        self, publication: AcceptancePublication
    ) -> tuple[str, AcceptancePublication]:
        """Record, once, when this invocation's terminal envelope was linked.

        The store binds the fact to the terminal file's digest and returns
        the path and the recorded fact.
        """

    def stored_publication(self, envelope: ColdHttpAcceptanceEnvelope) -> str | None:
        """Return this invocation's publication fact path, or None."""

    def load_publication(self, attempt_id: str) -> AcceptancePublication:
        """Return one attempt's recorded publication fact; raise if unreadable."""


class ReceiverContinuity(Protocol):
    """One fresh local reading of the bound receiver, taken per governed dispatch.

    `observe` answers with the same observation shape the lifecycle reader
    produces, so the one continuity rule decides it. It never contacts Packet
    Tracer, never caches a verdict and reports ambiguity as an error; it must
    return within `deadline` or say that it overran. `close` releases whatever
    local resources the binding holds.
    """

    def observe(self, deadline: float) -> DiagnosticLifecycleObservation:
        """Return one fresh reading of the receiver the attempt bound."""

    def close(self) -> None:
        """Release the binding's local resources; never raises."""
