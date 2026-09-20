"""Ports the Server-PT qualification runner orchestrates through.

The runner must be able to drive a real bridge, a Node-backed stub engine or a
recording fake without knowing which. The contracts therefore live here; the
probes, the version reader and the record store are infrastructure, and the
readings they return are domain values, so no infrastructure type crosses into
the coordinator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ...domain.enterprise.models.execution import DispatchFact, ResultFact
from ...domain.enterprise.models.service_qualification import QualificationRecord
from ...domain.enterprise.services.service_qualification_evidence import (
    ProbeReading,
    QueueReceipt,
)


class DispatchOutcome(Protocol):
    """The typed facts one correlated dispatch reports."""

    dispatch: DispatchFact
    result: ResultFact
    body: str | None
    detail: str


class QualificationTransport(Protocol):
    """One fixed command channel: the only way the runner reaches the engine."""

    def send(self, js_code: str) -> bool:
        """Queue one fire-and-forget command; True means the channel took it."""

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        """Dispatch one command and return its correlated body, or None."""

    def dispatch_and_wait(self, js_code: str, timeout: float) -> DispatchOutcome:
        """Dispatch one command and report its typed dispatch/result facts."""


@dataclass(frozen=True)
class OpenedTransport:
    """A transport fixed for one invocation, with its liveness observation."""

    channel: str
    transport: QualificationTransport | None
    live: bool
    detail: str = ""


class QualificationRecordPort(Protocol):
    """The write-ahead lifecycle of one qualification record."""

    def begin(self, record: QualificationRecord) -> str:
        """Create the record before any contact; raise if it cannot."""

    def advance(self, record: QualificationRecord) -> str:
        """Rewrite the record atomically at a step boundary."""

    def complete(self, record: QualificationRecord) -> str:
        """Write the terminal record; it is never rewritten afterwards."""

    def attempt_exists(self, attempt_id: str) -> bool:
        """Whether a record already names this attempt identity.

        Only an executable diagnostic stage asks, and it fails closed: a store
        that cannot answer refuses the run rather than assuming the attempt is
        new. A new SHA, a new process and a new run id do not create an
        attempt; the authority's attempt identity does, exactly once.
        """


class ForwardingProbePort(Protocol):
    """One bind-before-ping probe, already serialized to typed evidence.

    The coordinator never sees the executor's own result type: the adapter
    that composes the probe also serializes it, so no infrastructure value
    crosses into the application layer.
    """

    def probe_once(
        self,
        *,
        source_device_name: str,
        destination_endpoint: Any,
        source_endpoint: Any = None,
        expected_reachable: bool = True,
    ) -> Mapping[str, Any]:
        """Observe both bindings, one typed ping and both bindings again."""


@dataclass(frozen=True)
class BuildReading:
    """One bounded executable-version observation and its reader identity."""

    available: bool
    version: str
    reason: str
    excerpt: str
    reader_id: str
    reader_sha256: str


class BuildReader(Protocol):
    """The shared `AppWindow.getVersion()` reader, bound to one channel."""

    def read(self) -> BuildReading:
        """Observe the running executable's version once."""


class EngineProbes(Protocol):
    """The Q0 engine probes, bound to one run and one fixed channel."""

    def write_bag_sentinel(self) -> ProbeReading:
        """Write the run nonce under the evaluation receiver."""

    def read_and_release_bag_sentinel(self) -> ProbeReading:
        """Read the nonce in a separate evaluation; release it only if it matches."""

    def queue_atomicity_contender(self, contender: str) -> QueueReceipt:
        """Queue one contender for the run-owned claim without waiting."""

    def collect_atomicity(self) -> ProbeReading:
        """Collect the ordered contender log; release it only when complete."""

    def register_observer_and_trigger(self, device: str) -> ProbeReading:
        """Register cb1 on the device's port and trigger X by re-addressing it."""

    def read_observer_and_register_zero_event(self, device: str) -> ProbeReading:
        """Read cb1's evidence and register cb2, which has seen no event."""

    def release_observers_and_trigger(self, device: str) -> ProbeReading:
        """Release cb1 by its observed identity, mark cb2 inert, add cb3, trigger Y."""

    def read_post_release_and_drop(self) -> ProbeReading:
        """Read every counter after Y and drop the run's observer bookkeeping."""

    def release_run_bag(self) -> ProbeReading:
        """Mark remaining observers inert and delete the run bag (finalizer)."""


class ServiceProbes(Protocol):
    """The Q1 private probes on owned fixtures, bound to one fixed channel."""

    def write_page_markers(self, server: str) -> ProbeReading:
        """Write distinct run pages through the HTTP and HTTPS handles."""

    def cross_read_page_markers(self, server: str) -> ProbeReading:
        """Read every handle/page combination in a separate evaluation."""

    def prepare_https_only(self, server: str, marker: str) -> ProbeReading:
        """Write the marked index through both handles and disable HTTP."""

    def disable_https(self, server: str) -> ProbeReading:
        """Disable the HTTPS listener and read both states back."""

    def read_client_resolvers(self, clients: Sequence[str]) -> ProbeReading:
        """Read `DnsClient.getServerIp()` on the named clients."""
