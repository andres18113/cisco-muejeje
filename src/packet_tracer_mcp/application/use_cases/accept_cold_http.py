"""One governed cold-HTTP acceptance attempt around one product invocation.

This coordinator adds an envelope and nothing else. The product use case
`apply_enterprise_services` runs unchanged, over the same shared session
composition the MCP tool uses; there is no second compiler, applicator,
readiness gate, HTTP reader or fixture runner here. What the envelope owns is
the order around that call:

1. **Local admission, no contact.** The grant is parsed against the frozen
   proposal, import isolation is decided in this process, the checkout must be
   the granted clean published SHA and tree, the campaign claim and permanent
   attempt reservation are taken in the shared scope, one Packet Tracer
   incarnation is paired with an empty mailbox, the deployment must have no
   stored run of any status, and the stored manifest must be the granted one.
   A refusal here dispatched nothing. The write-ahead envelope is begun as
   soon as the attempt identity is reserved, so every later refusal is kept
   with its reason.
2. **One fixed channel.** The paired receiver is bound, then the granted
   channel is opened and its liveness read before a ledger or a runtime
   exists. Every product dispatch then passes one `OperationLedger`: counted
   once, admitted against one absolute deadline, decided against the held
   campaign claim and a fresh reading of the paired receiver, and labelled by
   the product boundary that made it. The compiled closure is compared with
   the grant before E1. Only owned client releases may spend the protected
   reserve.
3. **Finalization and judgement.** The mailbox is paired again, the run record
   is reloaded and compared with the public result, the dispatch order is
   checked from the ledger, the one absolute deadline is checked at the
   publication boundary, and the envelope is completed once. An interruption
   after the claim is finalized the same way, as a cancellation, and then
   re-raised.

The local checks are not an in-band receiver fence, and nothing here claims
exactly-once execution or the exclusion of a replacement process. The grant
accepts that limitation and an exclusive disposable laboratory explicitly.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from functools import partial
from typing import Any

from ...domain.enterprise.models.cold_http_acceptance import (
    COLD_HTTP_ARITHMETIC,
    COLD_HTTP_PROPOSAL,
    ENVELOPE_LIMITATIONS,
    AcceptanceBudget,
    AcceptanceRefusal,
    AcceptanceSubject,
    CampaignOutcome,
    ColdHttpAcceptanceEnvelope,
    ColdHttpGrant,
    ColdHttpProposal,
    acceptance_refusal,
    closure_identity_findings,
    effect_scope_findings,
    manifest_refusals,
    parse_grant,
    process_refusals,
    receiver_continuity_findings,
    repository_acceptance_refusals,
)
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.scalable_http_acceptance import (
    SCALABLE_ENVELOPE_LIMITATIONS,
    SCALABLE_GRANT_SCHEMA_VERSION,
    AcceptanceScope,
    ScalableHttpGrant,
    derive_scope,
    parse_scalable_grant,
    scope_findings,
)
from ...domain.enterprise.models.service_entry import (
    ServiceEffectClosure,
    ServiceStage,
    ServiceStageResult,
)
from ...domain.enterprise.models.service_qualification import (
    LOCAL_OBSERVATION_TIMEOUT_SECONDS,
    DiagnosticLifecycleObservation,
    RefusalKind,
    RepositoryIdentity,
    diagnostic_lifecycle_continuity,
    repository_refusals,
)
from ...domain.enterprise.models.service_run_record import ServiceRunRecord
from ...domain.enterprise.services.cold_http_acceptance_evidence import (
    E6_VERIFY_PREFIX,
    OWNED_RELEASE_PREFIX,
    PURPOSE_DRIFT,
    PURPOSE_E5_APPLY,
    PURPOSE_E5_VERIFY,
    PURPOSE_E6_APPLY,
    PURPOSE_ENVIRONMENT,
    PURPOSE_INVENTORY,
    PURPOSE_READINESS,
    AcceptanceEvaluation,
    bounded_answer,
    evaluate_attempt,
)
from ...domain.enterprise.services.scalable_http_acceptance_evidence import (
    READINESS_PREFIX,
    evaluate_scalable_attempt,
)
from ...domain.enterprise.services.service_access_readiness import (
    access_group_key,
    continuity_group_key,
)
from ..ports.cold_http_acceptance import (
    AcceptanceEnvelopePort,
    AcceptanceRunRecordPort,
    ReceiverContinuity,
)
from ..ports.service_qualification import OpenedTransport, QualificationTransport
from ..ports.service_run_record import DeploymentManifestPort
from .apply_enterprise_services import (
    MAX_INTENT_JSON_BYTES,
    ServiceEffectHalted,
    ServiceInvocationBinding,
    ServiceStageRuntimes,
    apply_enterprise_services,
)
from .qualify_server_services import (
    LedgeredTransport,
    LedgerPhase,
    OperationLedger,
    RuntimeIdentity,
)

MAX_DETAIL = 240
#: A dispatch refused by the ledger after the product began is a stop fact.
#: Only the first few are named in the verdict; the ledger keeps all of them.
MAX_NAMED_REFUSALS = 4
#: A receiver reading that cannot even start because the phase has no time
#: left refuses that one dispatch without deciding authority: nothing was
#: observed, and the next phase (a protected release) may still observe.
RECEIVER_NOT_ADMITTED = "receiver_observation_not_admitted:time_budget_exhausted"


def _bounded(value: object) -> str:
    return " ".join(str(value or "").split())[:MAX_DETAIL]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AcceptanceRequest:
    """One explicit request to run one granted attempt."""

    execute: bool
    grant_document: object
    grant_text: str
    intent_json: str


@dataclass(frozen=True)
class AcceptanceChannel:
    """The bound channel and controls the adapter composes the session over.

    `transport` is already the ledgered transport: the adapter can only reach
    Packet Tracer through it, on `channel`, and it never selects a channel of
    its own.
    """

    channel: str
    bound_at: datetime
    transport: QualificationTransport
    record_store: AcceptanceRunRecordPort
    clock: Callable[[], float]
    sleeper: Callable[[float], None]
    wait_allowance: Callable[[], float]
    owned_release: Callable[[str], AbstractContextManager[None]]
    effect_admission: Callable[[ServiceEffectClosure], str]


@dataclass(frozen=True)
class AcceptanceBoundaries:
    """Every external boundary one attempt reaches, injected by the adapter."""

    import_preflight: Any
    runtime_identity: Callable[[], RuntimeIdentity]
    repository: Callable[[], RepositoryIdentity]
    lifecycle: Callable[[float | None], DiagnosticLifecycleObservation]
    campaign_coordinator: Any
    manifest_store: DeploymentManifestPort
    record_store: AcceptanceRunRecordPort
    envelope_store: AcceptanceEnvelopePort
    open_channel: Callable[[str], OpenedTransport]
    close_channel: Callable[[OpenedTransport], None]
    session_factory: Callable[
        [AcceptanceChannel], Callable[[], ServiceInvocationBinding]
    ]
    clock: Callable[[], float]
    sleep: Callable[[float], None]
    now: Callable[[], datetime]
    proposal: ColdHttpProposal = COLD_HTTP_PROPOSAL
    local_observation_seconds: float = LOCAL_OBSERVATION_TIMEOUT_SECONDS
    #: Binds the paired receiver for the per-dispatch reading. `None` reads
    #: the full lifecycle for every dispatch, which is correct and slow.
    bind_receiver: (
        Callable[[DiagnosticLifecycleObservation, float], ReceiverContinuity] | None
    ) = None


#: The only receiver mode a governed attempt may run with: a bounded local
#: reading per dispatch. Both profiles' time budgets are priced on it.
BOUNDED_RECEIVER_MODE = "handle_bound"


class LifecycleReceiverContinuity:
    """Answer every governed dispatch with one full lifecycle reading.

    It is a correct check and the fallback where no handle can be held, but a
    full reading launches local helpers and has no per-dispatch bound, so
    neither profile's time budget covers it; an attempt refuses before
    contact when this is the only binding available.
    """

    mode = "lifecycle_per_dispatch"

    def __init__(
        self, lifecycle: Callable[[float | None], DiagnosticLifecycleObservation]
    ) -> None:
        """Bind the full lifecycle reader."""
        self._lifecycle = lifecycle

    def observe(self, deadline: float) -> DiagnosticLifecycleObservation:
        """Return one full reading within the dispatch deadline."""
        return self._lifecycle(deadline)

    def close(self) -> None:
        """Hold nothing, release nothing."""


@dataclass
class AcceptanceResult:
    """What one attempt returns to its adapter."""

    envelope: ColdHttpAcceptanceEnvelope
    envelope_path: str = ""
    product_summary: dict[str, Any] | None = None
    #: Whether the terminal envelope reached the store. `None` means no
    #: envelope was due, because nothing was reserved; `False` after a
    #: reservation is a persistence failure, never an ordinary refusal.
    persisted: bool | None = None
    #: Wall clock the terminal write itself took, after the publication
    #: boundary. It cannot be inside the envelope it wrote.
    completion_seconds: float = 0.0

    @property
    def exit_code(self) -> int:
        """Return 0 accepted, 1 completed or stopped without acceptance, 2 refused."""
        if self.envelope.http_accepted:
            return 0
        if self.envelope.campaign_outcome is CampaignOutcome.REFUSED:
            return 2
        return 1

    def compact_summary(self) -> dict[str, Any]:
        """Return the JSON-ready summary an operator sees."""
        envelope = self.envelope
        return {
            "attempt_id": envelope.attempt_id,
            "campaign_outcome": envelope.campaign_outcome.value,
            "http_accepted": envelope.http_accepted,
            "primary_failure": envelope.primary_failure,
            "reasons": list(envelope.reasons),
            "admission": [item.model_dump(mode="json") for item in envelope.admission],
            "release_failures": list(envelope.release_failures),
            "persistence_failures": list(envelope.persistence_failures),
            "postflight_failures": list(envelope.postflight_failures),
            "product_run_id": envelope.product.get("run_id", ""),
            "product_record_path": envelope.product.get("record_path", ""),
            "operations_used": (
                envelope.budget.used_operations if envelope.budget else 0
            ),
            "cancellation": envelope.cancellation,
            "profile": envelope.scope.get("profile", "cold_http_two_client_v1"),
            "selected_clients": len(envelope.clients),
            "accepted_clients": sum(1 for item in envelope.clients if item.accepted),
            "envelope_path": self.envelope_path,
            "envelope_persisted": self.persisted,
            "completion_seconds": round(self.completion_seconds, 3),
        }


# -- controls the coordinator owns ---------------------------------------------


class _EvidenceTap:
    """Keep each client's raw start and release answers as they arrived.

    It sits under the ledger, so a refused call never reaches it, and it keys
    what it keeps by the ledger purpose the product boundary set. It never
    parses, filters or changes an answer.
    """

    def __init__(self, transport: QualificationTransport, ledger: OperationLedger):
        self._transport = transport
        self._ledger = ledger
        self.answers: dict[str, list[str]] = {}

    def _keep(self, body: str | None) -> None:
        purpose = self._ledger.purpose
        if purpose.startswith((E6_VERIFY_PREFIX, OWNED_RELEASE_PREFIX)):
            kept = self.answers.setdefault(purpose, [])
            if len(kept) < 2:
                kept.append(bounded_answer(body))

    def send(self, js_code: str) -> bool:
        return self._transport.send(js_code)

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        body = self._transport.send_and_wait(js_code, timeout)
        self._keep(body)
        return body

    def dispatch_and_wait(self, js_code: str, timeout: float):
        outcome = self._transport.dispatch_and_wait(js_code, timeout)
        self._keep(getattr(outcome, "body", None))
        return outcome

    def __getattr__(self, name: str) -> Any:
        # Settling pending fire-and-forget sends is the channel's own local
        # bookkeeping; it is delegated, never counted and never tapped.
        if name in {"collect_completed", "has_pending_requests"}:
            return getattr(self._transport, name)
        raise AttributeError(name)


class _Halted:
    """Stop a labelled boundary once the attempt has lost authority.

    After the first loss every later dispatch would be refused by the ledger
    anyway. Stopping at the boundary instead means the product sees one halt
    per boundary rather than a refused call per client, so a lost receiver or
    claim stops the whole invocation without a single further dispatch.
    """

    def __init__(self, ledger: OperationLedger, lost: Callable[[], str]) -> None:
        self._ledger = ledger
        self._lost = lost

    def check(self) -> None:
        reason = self._lost()
        if reason:
            raise ServiceEffectHalted(f"execution_authority_lost:{reason}")


class _LabelledConfiguration:
    """The E5 runtime, with each boundary's dispatches named in the ledger.

    A scalable attempt labels each readiness dispatch with the identity of the
    group it observes, so the ordering oracle can require every group a
    client's path names before that client's first request.
    """

    def __init__(
        self,
        inner: Any,
        ledger: OperationLedger,
        halted: _Halted,
        *,
        by_group: bool = False,
    ) -> None:
        self._inner = inner
        self._ledger = ledger
        self._halted = halted
        self._by_group = by_group

    def inventory(self):
        self._halted.check()
        with self._ledger.purpose_of(PURPOSE_INVENTORY):
            return self._inner.inventory()

    def apply_actions(self, actions):
        self._halted.check()
        with self._ledger.purpose_of(PURPOSE_E5_APPLY):
            return self._inner.apply_actions(actions)

    def verify(self, expectations):
        self._halted.check()
        with self._ledger.purpose_of(PURPOSE_E5_VERIFY):
            return self._inner.verify(expectations)

    def wait_for_voice_access_forwarding(self, expectations):
        self._halted.check()
        with self._ledger.purpose_of("e5_voice_forwarding"):
            return self._inner.wait_for_voice_access_forwarding(expectations)

    def observe_access_forwarding(self, device_name, vlan_id, *args, **kwargs):
        self._halted.check()
        purpose = (
            READINESS_PREFIX + access_group_key(device_name, vlan_id)
            if self._by_group
            else PURPOSE_READINESS
        )
        with self._ledger.purpose_of(purpose):
            return self._inner.observe_access_forwarding(
                device_name, vlan_id, *args, **kwargs
            )

    def observe_trunk_continuity(self, switches, vlan_id, *args, **kwargs):
        self._halted.check()
        purpose = (
            READINESS_PREFIX
            + continuity_group_key(vlan_id, [name for name, _ in switches])
            if self._by_group
            else PURPOSE_READINESS
        )
        with self._ledger.purpose_of(purpose):
            return self._inner.observe_trunk_continuity(
                switches, vlan_id, *args, **kwargs
            )


class _LabelledServices:
    """The E6 runtime, with each boundary's dispatches named in the ledger."""

    def __init__(self, inner: Any, ledger: OperationLedger, halted: _Halted) -> None:
        self._inner = inner
        self._ledger = ledger
        self._halted = halted

    def inventory(self):
        self._halted.check()
        with self._ledger.purpose_of(PURPOSE_INVENTORY):
            return self._inner.inventory()

    def apply_actions(self, actions):
        self._halted.check()
        with self._ledger.purpose_of(PURPOSE_E6_APPLY):
            return self._inner.apply_actions(actions)

    def verify(self, expectation):
        self._halted.check()
        with self._ledger.purpose_of(E6_VERIFY_PREFIX + expectation.id):
            return self._inner.verify(expectation)


class _LabelledObserver:
    """The admission drift reader, named as such in the ledger."""

    def __init__(self, inner: Any, ledger: OperationLedger, halted: _Halted) -> None:
        self._inner = inner
        self._ledger = ledger
        self._halted = halted

    def observe(self, runtime_device_name: str, interface: str):
        self._halted.check()
        with self._ledger.purpose_of(PURPOSE_DRIFT):
            return self._inner.observe(runtime_device_name, interface)


class _PinnedManifest:
    """Answer the product with exactly the manifest admission compared."""

    def __init__(self, manifest: DeploymentManifest) -> None:
        self._manifest = manifest

    def latest_by_deployment_id(self, deployment_id: str) -> DeploymentManifest | None:
        return self._manifest if deployment_id == self._manifest.deployment_id else None


@dataclass
class _Attempt:
    """What one admitted attempt owns and has observed."""

    grant: ColdHttpGrant
    envelope: ColdHttpAcceptanceEnvelope
    boundaries: AcceptanceBoundaries
    ledger: OperationLedger
    claim: Any = None
    envelope_begun: bool = False
    envelope_path: str = ""
    preflight: DiagnosticLifecycleObservation | None = None
    local_observation_seconds: float = 0.0
    authority_lost: str = ""
    closure: ServiceEffectClosure | None = None
    effects_began: bool = False
    stop_facts: list[str] = field(default_factory=list)
    receiver: ReceiverContinuity | None = None
    receiver_observations: int = 0
    receiver_seconds: float = 0.0
    #: `cancelled:<type>@<boundary>` once an interruption was caught.
    cancelled: str = ""
    #: The scalable scope derived from the admitted closure, or None.
    scope: AcceptanceScope | None = None
    #: Set once the terminal envelope write was attempted, whatever it gave.
    completed: bool = False
    #: Where the attempt is: admission, product, finalization or publication.
    #: An interruption is named by it when no dispatch names it better.
    phase: str = "admission"

    def authority(self, purpose: str, deadline: float) -> str:
        """Decide one dispatch against the claim and the paired receiver.

        Both are re-read for every governed dispatch, protected releases
        included. The first loss is sticky: a window in which another process
        may have answered cannot be closed retroactively. A reading that could
        not start for lack of time refuses only this dispatch.
        """
        del purpose
        if self.authority_lost:
            return self.authority_lost
        try:
            reasons = tuple(
                self.boundaries.campaign_coordinator.verify(self.claim) or ()
            )
        except Exception as exc:
            reasons = (f"campaign_claim:unverifiable:{type(exc).__name__}",)
        if not reasons:
            reasons = self.receiver_findings(deadline)
            if reasons == (RECEIVER_NOT_ADMITTED,):
                return RECEIVER_NOT_ADMITTED
        if reasons:
            self.authority_lost = _bounded(reasons[0])
            self.stop_facts.append(f"authority_lost:{self.authority_lost}")
        return self.authority_lost

    def receiver_findings(self, deadline: float) -> tuple[str, ...]:
        """Take one bounded reading of the paired receiver and judge it."""
        if self.receiver is None:
            return ("process_instance:receiver_not_bound",)
        clock = self.boundaries.clock
        bound = min(
            float(deadline), clock() + self.boundaries.local_observation_seconds
        )
        if clock() >= bound:
            return (RECEIVER_NOT_ADMITTED,)
        started = clock()
        try:
            observed = self.receiver.observe(bound)
        except Exception as exc:
            observed = DiagnosticLifecycleObservation(
                error=f"receiver_read_failed:{type(exc).__name__}"
            )
        finished = clock()
        spent = max(0.0, finished - started)
        self.receiver_observations += 1
        self.receiver_seconds += spent
        self.local_observation_seconds += spent
        if finished > bound and not observed.error:
            observed = DiagnosticLifecycleObservation(
                error="local_observation_deadline_exceeded:receiver"
            )
        return receiver_continuity_findings(self.grant.build, self.preflight, observed)

    def lost(self) -> str:
        """Return the sticky authority loss, or ""."""
        return self.authority_lost

    def cancel(self, error: BaseException, boundary: str = "") -> None:
        """Keep the first interruption, named by the boundary it hit.

        Inside the product the boundary is the purpose of the last dispatch
        the ledger saw, which is the one in flight or the one just finished.
        """
        if self.cancelled:
            return
        last = boundary or next(
            (item.purpose for item in reversed(self.ledger.entries) if item.purpose),
            "",
        )
        self.cancelled = _bounded(
            f"cancelled:{type(error).__name__}@{last or 'coordinator'}"
        )

    def wait_allowance(self) -> float:
        """Report what a nested product wait may still spend; nothing after loss."""
        if self.authority_lost:
            return 0.0
        operations, seconds = self.ledger.allowance()
        return max(0.0, seconds) if operations >= 1 else 0.0

    @contextmanager
    def owned_release(self, expectation_id: str) -> Iterator[None]:
        """Admit exactly one owned client release against the protected reserve."""
        with self.ledger.protected_release():
            with self.ledger.purpose_of(OWNED_RELEASE_PREFIX + expectation_id):
                yield

    def admit_closure(self, closure: ServiceEffectClosure) -> str:
        """Compare the compiled closure with the grant, immediately before E1."""
        self.closure = closure
        if isinstance(self.grant, ScalableHttpGrant):
            findings = [*closure_identity_findings(self.grant, closure)]
            scope, derived = derive_scope(closure, self.grant.marker)
            findings.extend(derived)
            if scope is not None:
                self.scope = scope
                self.envelope.scope = {
                    "profile": scope.profile,
                    "scope_sha256": scope.digest(),
                    "clients": len(scope.clients),
                    "servers": [item.name for item in scope.servers],
                    "groups": len(scope.groups),
                    "cost": scope.cost.document(),
                }
                findings.extend(scope_findings(self.grant, scope))
            findings = tuple(findings)
        else:
            findings = effect_scope_findings(self.grant, closure)
        self.envelope.closure = closure
        self.envelope.closure_findings = list(findings)
        if not findings:
            self.effects_began = True
        return "; ".join(findings)

    def observe_lifecycle(self, deadline: float) -> DiagnosticLifecycleObservation:
        """Read and charge one local process pairing under an absolute deadline."""
        clock = self.boundaries.clock
        started = clock()
        try:
            observed = self.boundaries.lifecycle(deadline)
        except Exception as exc:
            observed = DiagnosticLifecycleObservation(
                error=f"lifecycle_read_failed:{type(exc).__name__}"
            )
        finished = clock()
        self.local_observation_seconds += max(0.0, finished - started)
        if finished > deadline and not observed.error:
            return DiagnosticLifecycleObservation(
                error="local_observation_deadline_exceeded:lifecycle"
            )
        return observed


# -- the attempt ---------------------------------------------------------------


def accept_cold_http(
    request: AcceptanceRequest, boundaries: AcceptanceBoundaries
) -> AcceptanceResult:
    """Run one granted attempt, or refuse it before anything is dispatched."""
    envelope = ColdHttpAcceptanceEnvelope(
        attempt_id="",
        started_at=boundaries.now(),
        limitations=list(ENVELOPE_LIMITATIONS),
    )
    if request.execute is not True:
        return _refused(
            envelope,
            [
                acceptance_refusal(
                    RefusalKind.MISSING,
                    AcceptanceSubject.GRANT,
                    "explicit execution was not requested; nothing was read",
                )
            ],
        )
    envelope.grant = (
        dict(request.grant_document)
        if isinstance(request.grant_document, Mapping)
        else {}
    )
    envelope.grant_sha256 = _sha256(request.grant_text)
    grant, refusals = _parse(request.grant_document, boundaries.proposal)
    if grant is None:
        return _refused(envelope, list(refusals))
    if isinstance(grant, ScalableHttpGrant):
        envelope.limitations = list(SCALABLE_ENVELOPE_LIMITATIONS)
    envelope.attempt_id = grant.attempt_id
    envelope.authorization_id = grant.authorization_id
    envelope.product_input = {
        "intent_sha256": _sha256(request.intent_json),
        "intent_json": request.intent_json,
        "deployment_id": grant.deployment_id,
        "packet_tracer_version": grant.build,
        "run_label": grant.run_label,
    }
    if len(request.intent_json.encode("utf-8")) > MAX_INTENT_JSON_BYTES:
        return _refused(
            envelope,
            [
                acceptance_refusal(
                    RefusalKind.MALFORMED, AcceptanceSubject.INTENT, "input budget"
                )
            ],
        )
    if envelope.product_input["intent_sha256"] != grant.intent_sha256:
        return _refused(
            envelope,
            [
                acceptance_refusal(
                    RefusalKind.MISMATCH,
                    AcceptanceSubject.INTENT,
                    "the intent is not the granted input",
                )
            ],
        )
    # The attempt's one absolute deadline starts here and covers everything
    # that follows, local observations included.
    ledger = OperationLedger(
        max_operations=grant.max_operations,
        max_seconds=grant.max_seconds,
        clock=boundaries.clock,
    )
    ledger.reserve(grant.reserve_operations, grant.reserve_seconds)
    attempt = _Attempt(grant, envelope, boundaries, ledger)
    envelope.budget = _budget(grant, ledger, attempt)

    isolation = boundaries.import_preflight.ensure_isolated()
    state = getattr(getattr(isolation, "state", None), "value", "INDETERMINATE")
    envelope.isolation = {"state": str(state), "detail": _bounded(isolation.render())}
    envelope.checks.append("isolation")
    if not isolation.isolated:
        return _refused(
            envelope,
            [
                acceptance_refusal(
                    RefusalKind.NOT_PERMITTED,
                    AcceptanceSubject.ISOLATION,
                    isolation.render(),
                )
            ],
        )
    identity = boundaries.runtime_identity()
    envelope.runtime = {
        "python_executable": identity.python_executable,
        "package_file": identity.package_file,
    }
    repository = boundaries.repository()
    envelope.source = asdict(repository)
    envelope.checks.append("repository")
    found = repository_acceptance_refusals(
        repository_refusals(repository, grant.sha, grant.tree)
    )
    if found:
        return _refused(envelope, list(found))
    try:
        attempt.claim = boundaries.campaign_coordinator.claim(
            attempt_id=grant.attempt_id
        )
    except Exception as exc:
        return _refused(
            envelope,
            [
                acceptance_refusal(
                    RefusalKind.NOT_PERMITTED,
                    AcceptanceSubject.CAMPAIGN,
                    f"campaign_not_exclusive:{exc}",
                )
            ],
        )
    try:
        envelope.checks.append("campaign_claim")
        summary = getattr(attempt.claim, "compact_summary", None)
        envelope.campaign = {"claim": summary() if callable(summary) else {}}
        return _claimed(request, attempt)
    except Exception:
        raise
    except BaseException as exc:
        # An interruption after the reservation and outside the product call
        # (a local admission read, the receiver binding, the channel) still
        # ends in one terminal envelope, as a cancellation, and propagates.
        if not attempt.completed:
            _cancelled_outside_the_product(attempt, exc)
        raise
    finally:
        # Every ordinary path released the claim before completing the
        # envelope; this only covers a path that raised out of the attempt.
        if "release" not in envelope.campaign:
            _release_claim(attempt)


def _cancelled_outside_the_product(attempt: _Attempt, error: BaseException) -> None:
    """Complete the envelope of an attempt interrupted outside the product.

    It covers every interval after the reservation that the product's own
    cancellation path does not: local admission, receiver binding, channel
    opening, and a second interruption during the verdict or the terminal
    write. The first interruption stays the named one; nothing here can turn
    the attempt into an acceptance.
    """
    envelope = attempt.envelope
    if attempt.phase == "admission":
        boundary = "after:" + (
            envelope.checks[-1] if envelope.checks else "reservation"
        )
    else:
        boundary = attempt.phase
    attempt.cancel(error, boundary)
    envelope.cancellation = attempt.cancelled
    envelope.reasons = [
        attempt.cancelled,
        *(item for item in envelope.reasons if item != attempt.cancelled),
    ]
    envelope.primary_failure = attempt.cancelled
    envelope.http_accepted = False
    envelope.campaign_outcome = CampaignOutcome.STOPPED
    _close_receiver(attempt)
    _complete(attempt)


def _parse(document: object, proposal: ColdHttpProposal):
    """Parse a grant by its declared schema; schema 1 is the legacy profile."""
    version = document.get("schema_version") if isinstance(document, Mapping) else None
    if version == SCALABLE_GRANT_SCHEMA_VERSION:
        return parse_scalable_grant(document)
    return parse_grant(document, proposal)


def _claimed(request: AcceptanceRequest, attempt: _Attempt) -> AcceptanceResult:
    """Finish local admission while the campaign claim is held."""
    grant, envelope, boundaries = attempt.grant, attempt.envelope, attempt.boundaries
    # The attempt identity is spent from here on, so its write-ahead envelope
    # exists before the next read: whatever refuses it later is kept with its
    # reason instead of disappearing with an unbegun envelope.
    try:
        attempt.envelope_path = boundaries.envelope_store.begin(envelope)
        attempt.envelope_begun = True
    except Exception as exc:
        return _refused_after_claim(
            attempt,
            [
                acceptance_refusal(
                    RefusalKind.NOT_PERMITTED,
                    AcceptanceSubject.ENVELOPE,
                    f"envelope_not_writable:{type(exc).__name__}",
                )
            ],
        )
    envelope.checks.append("envelope_begun")
    deadline = min(
        boundaries.clock() + boundaries.local_observation_seconds,
        attempt.ledger.deadline(),
    )
    attempt.preflight = attempt.observe_lifecycle(deadline)
    envelope.process_preflight = asdict(attempt.preflight)
    envelope.checks.append("process_preflight")
    found = list(process_refusals(grant, attempt.preflight))
    if found:
        return _refused_after_claim(attempt, found)
    try:
        history = boundaries.record_store.deployment_history(grant.deployment_id)
    except Exception as exc:
        return _refused_after_claim(
            attempt,
            [
                acceptance_refusal(
                    RefusalKind.UNOBSERVABLE,
                    AcceptanceSubject.HISTORY,
                    f"history_unreadable:{type(exc).__name__}",
                )
            ],
        )
    envelope.checks.append("deployment_history")
    if history:
        return _refused_after_claim(
            attempt,
            [
                acceptance_refusal(
                    RefusalKind.NOT_PERMITTED,
                    AcceptanceSubject.HISTORY,
                    "the deployment already has stored runs: " + ", ".join(history[:8]),
                )
            ],
        )
    try:
        manifest = boundaries.manifest_store.latest_by_deployment_id(
            grant.deployment_id
        )
    except Exception as exc:
        return _refused_after_claim(
            attempt,
            [
                acceptance_refusal(
                    RefusalKind.UNOBSERVABLE,
                    AcceptanceSubject.MANIFEST,
                    f"manifest_unreadable:{type(exc).__name__}",
                )
            ],
        )
    if manifest is None:
        return _refused_after_claim(
            attempt,
            [acceptance_refusal(RefusalKind.MISSING, AcceptanceSubject.MANIFEST)],
        )
    envelope.manifest = {
        "deployment_id": manifest.deployment_id,
        "semantic_hash": manifest.semantic_hash,
        "physical_topology_hash": manifest.physical_topology_hash,
        "backend_version": manifest.backend_version,
    }
    envelope.checks.append("manifest")
    found = list(
        manifest_refusals(
            grant,
            deployment_id=manifest.deployment_id,
            semantic_hash=manifest.semantic_hash,
            physical_topology_hash=manifest.physical_topology_hash,
            backend_version=manifest.backend_version,
        )
    )
    if found:
        return _refused_after_claim(attempt, found)
    return _contact(request, attempt, manifest)


def _bind_receiver(attempt: _Attempt) -> str:
    """Bind the paired receiver before any channel exists; return why not."""
    boundaries = attempt.boundaries
    deadline = min(
        boundaries.clock() + boundaries.local_observation_seconds,
        attempt.ledger.deadline(),
    )
    bind = boundaries.bind_receiver
    started = boundaries.clock()
    try:
        if bind is None:
            attempt.receiver = LifecycleReceiverContinuity(boundaries.lifecycle)
        else:
            attempt.receiver = bind(attempt.preflight, deadline)
    except Exception as exc:
        return f"receiver_binding_failed:{type(exc).__name__}"
    finally:
        attempt.local_observation_seconds += max(0.0, boundaries.clock() - started)
    attempt.envelope.checks.append("receiver_bound")
    attempt.envelope.process_preflight["receiver_binding"] = type(
        attempt.receiver
    ).__name__
    mode = str(getattr(attempt.receiver, "mode", "") or "unknown")
    attempt.envelope.process_preflight["receiver_mode"] = mode
    if mode != BOUNDED_RECEIVER_MODE:
        # A correct reading whose cost the granted budget does not price is
        # not admitted: the run would stop on time, never complete honestly.
        return f"receiver_mode_not_bounded:{mode}"
    return ""


def _close_receiver(attempt: _Attempt) -> None:
    receiver, attempt.receiver = attempt.receiver, None
    if receiver is None:
        return
    try:
        receiver.close()
    except Exception as exc:
        attempt.envelope.postflight_failures.append(
            f"receiver_close:{type(exc).__name__}"
        )


def _contact(
    request: AcceptanceRequest, attempt: _Attempt, manifest: DeploymentManifest
) -> AcceptanceResult:
    """Bind the paired receiver, then run the product over the granted channel."""
    unbound = _bind_receiver(attempt)
    if unbound:
        return _refused_after_claim(
            attempt,
            [
                acceptance_refusal(
                    RefusalKind.UNOBSERVABLE, AcceptanceSubject.PROCESS, unbound
                )
            ],
        )
    try:
        return _contact_bound(request, attempt, manifest)
    finally:
        _close_receiver(attempt)


def _contact_bound(
    request: AcceptanceRequest, attempt: _Attempt, manifest: DeploymentManifest
) -> AcceptanceResult:
    """Run the product over the granted channel while the receiver is bound."""
    grant, envelope, boundaries = attempt.grant, attempt.envelope, attempt.boundaries
    ledger = attempt.ledger
    try:
        opened = boundaries.open_channel(grant.channel)
    except Exception as exc:
        opened = OpenedTransport(
            grant.channel, None, False, f"open_failed:{type(exc).__name__}"
        )
    envelope.channel = {
        "channel": opened.channel,
        "liveness": opened.detail,
        "bound_at": boundaries.now().isoformat(),
    }
    if opened.channel != grant.channel or not opened.live or opened.transport is None:
        _close(attempt, opened)
        return _refused_after_claim(
            attempt,
            [
                acceptance_refusal(
                    RefusalKind.UNOBSERVABLE
                    if opened.channel == grant.channel
                    else RefusalKind.MISMATCH,
                    AcceptanceSubject.CHANNEL,
                    opened.detail or "the granted channel is not live",
                )
            ],
        )
    tap = _EvidenceTap(opened.transport, ledger)
    bound = LedgeredTransport(ledger, tap, boundaries.sleep, boundaries.clock)
    ledger.bind_effect_guard(attempt.authority)
    ledger.enter(LedgerPhase.EXPERIMENT)
    channel = AcceptanceChannel(
        channel=grant.channel,
        bound_at=boundaries.now(),
        transport=bound,
        record_store=boundaries.record_store,
        clock=bound.clock,
        sleeper=bound.capped_sleep,
        wait_allowance=attempt.wait_allowance,
        owned_release=attempt.owned_release,
        effect_admission=attempt.admit_closure,
    )
    result: ServiceStageResult | None = None
    product_error = ""
    interrupted: BaseException | None = None
    try:
        session = boundaries.session_factory(channel)

        def labelled_session() -> ServiceInvocationBinding:
            with ledger.purpose_of(PURPOSE_ENVIRONMENT):
                binding = session()
            return _labelled(binding, attempt)

        attempt.phase = "product"
        with ledger.effect_of("product"):
            result = apply_enterprise_services(
                request.intent_json,
                deployment_id=grant.deployment_id,
                packet_tracer_version=grant.build,
                import_preflight=boundaries.import_preflight,
                manifest_store=_PinnedManifest(manifest),
                record_store_factory=lambda: boundaries.record_store,
                session_factory=labelled_session,
                run_label=grant.run_label,
            )
    except Exception as exc:
        # The product never raises by contract; if it did, the primary fact
        # is that the invocation did not return, and that is what is kept.
        product_error = f"product_invocation_raised:{type(exc).__name__}"
    except BaseException as exc:
        # An interruption is not an error to absorb. The product's own client
        # finalizer already made its one release attempt on the way out; this
        # stops ordinary work, finalizes the envelope as a cancellation and
        # re-raises the original exception.
        attempt.cancel(exc)
        interrupted = exc
    ledger.enter(LedgerPhase.FINALIZATION)
    try:
        if bound.settle_pending_sends():
            attempt.stop_facts.append("fire_and_forget_send_unresolved")
        _close(attempt, opened)
        _close_receiver(attempt)
        completed = _finalize(attempt, tap, result, product_error)
    except BaseException as late:
        # `_finalize` completes the envelope on its own interruption and
        # re-raises it; the first interruption stays the one that propagates.
        if interrupted is None:
            raise
        attempt.envelope.postflight_failures.append(
            f"interrupted_again:{type(late).__name__}"
        )
        raise interrupted from late
    if interrupted is not None:
        raise interrupted
    return completed


def _labelled(binding: ServiceInvocationBinding, attempt: _Attempt):
    """Name every product boundary in the ledger and hold the bound controls."""
    ledger = attempt.ledger
    if binding.transport_selection.channel != attempt.grant.channel:
        raise RuntimeError("The composed session is not on the granted channel.")
    reader = binding.inventory_reader

    def labelled_inventory(names: Sequence[str]):
        with ledger.purpose_of(PURPOSE_INVENTORY):
            if reader is None:
                raise RuntimeError("The composed session has no inventory reader.")
            return reader(names)

    halted = _Halted(ledger, attempt.lost)
    return replace(
        binding,
        runtimes=ServiceStageRuntimes(
            configuration=_LabelledConfiguration(
                binding.runtimes.configuration,
                ledger,
                halted,
                by_group=isinstance(attempt.grant, ScalableHttpGrant),
            ),
            services=_LabelledServices(binding.runtimes.services, ledger, halted),
        ),
        record_store=attempt.boundaries.record_store,
        endpoint_observer=(
            _LabelledObserver(binding.endpoint_observer, ledger, halted)
            if binding.endpoint_observer is not None
            else None
        ),
        inventory_reader=labelled_inventory,
        # Whatever the adapter composed, the admission that decides this
        # attempt's closure is this attempt's own.
        effect_admission=attempt.admit_closure,
    )


class _TemporalContract:
    """Carry the one absolute deadline through every controlled boundary.

    A local operation cannot always be preempted, so the contract is not that
    it stops on time; it is that its lateness is observed. The first boundary
    reached after the deadline is kept, and acceptance is refused from it.
    """

    def __init__(self, deadline: float, clock: Callable[[], float]) -> None:
        self.deadline = deadline
        self._clock = clock
        self.exceeded_at = ""

    def cross(self, boundary: str) -> None:
        if not self.exceeded_at and self._clock() > self.deadline:
            self.exceeded_at = boundary


def _finalize(
    attempt: _Attempt,
    tap: _EvidenceTap,
    result: ServiceStageResult | None,
    product_error: str,
) -> AcceptanceResult:
    """Pair the process again, reload the record, judge, and complete once.

    An interruption anywhere in here still completes the envelope, as a
    cancellation, and is then re-raised; it never becomes an acceptance.
    """
    ledger = attempt.ledger
    attempt.phase = "finalization"
    temporal = _TemporalContract(ledger.deadline(), attempt.boundaries.clock)
    summary = result.compact_summary() if result is not None else None
    interrupted: BaseException | None = None
    ledger_refusals: list[str] = []
    evaluation = AcceptanceEvaluation()
    try:
        record, record_path, record_problems = _collect_evidence(
            attempt, result, product_error, temporal
        )
        # The claim is released before the verdict, because its release is a
        # finalization result like any other: a lock that another writer holds
        # or that cannot be read says the exclusion did not cover this run to
        # its end.
        _release_claim(attempt)
        temporal.cross("claim_release")
        ledger_refusals = [
            f"ledger_refused:{item.refused}@{item.purpose or 'none'}"
            for item in ledger.entries
            if item.refused
        ]
        evaluation = _evaluate(
            attempt,
            tap,
            record=record,
            record_path=record_path,
            record_problems=record_problems,
            summary=summary,
            ledger_refusals=ledger_refusals,
        )
        temporal.cross("verdict")
    except Exception:
        raise
    except BaseException as exc:
        attempt.cancel(exc, "finalization")
        interrupted = exc
    # An interruption from here on is caught by the attempt's own handler,
    # which completes the envelope as a cancellation if this did not.
    attempt.phase = "publication"
    _judge(attempt, result, evaluation, ledger_refusals, temporal)
    completed = _complete(attempt, product_summary=summary)
    if interrupted is not None:
        raise interrupted
    return completed


def _collect_evidence(
    attempt: _Attempt,
    result: ServiceStageResult | None,
    product_error: str,
    temporal: _TemporalContract,
) -> tuple[ServiceRunRecord | None, str, list[str]]:
    """Take the postflight reading and reload the durable record, once each."""
    grant, envelope, boundaries = attempt.grant, attempt.envelope, attempt.boundaries
    deadline = attempt.ledger.deadline()
    if boundaries.clock() >= deadline:
        envelope.postflight_failures.append(
            "postflight_not_admitted:time_budget_exhausted"
        )
        postflight = DiagnosticLifecycleObservation(
            error="postflight_not_admitted:time_budget_exhausted"
        )
    else:
        postflight = attempt.observe_lifecycle(
            min(boundaries.clock() + boundaries.local_observation_seconds, deadline)
        )
    envelope.process_postflight = asdict(postflight)
    envelope.continuity = list(
        diagnostic_lifecycle_continuity(attempt.preflight, postflight)
    )
    envelope.postflight_failures.extend(
        f"continuity:{item}" for item in envelope.continuity
    )
    temporal.cross("postflight")

    record: ServiceRunRecord | None = None
    record_path = ""
    record_problems: list[str] = []
    if product_error:
        record_problems.append(product_error)
    if result is None:
        # The product never returned, so no run id reached this coordinator.
        # Whatever it wrote ahead is still cited by path and bytes.
        _cite_unreturned_records(attempt)
        temporal.cross("record_reload")
        return record, record_path, record_problems
    envelope.product = {
        "run_id": result.run_id,
        "record_path": result.record_path,
        "status": result.status.value,
        "refusal_code": result.refusal_code.value,
        "blocked_reason": result.blocked_reason,
        "persisted_stage": (
            result.persisted_stage.value if result.persisted_stage else None
        ),
        "persist_error": result.persist_error,
        "duration_ms": result.duration_ms,
    }
    if result.persist_error:
        envelope.persistence_failures.append(
            f"product_record:{_bounded(result.persist_error)}"
        )
    try:
        record, record_path, digest = boundaries.record_store.load_evidence(
            grant.deployment_id, result.run_id
        )
        envelope.product["record_sha256"] = digest
        envelope.product["reloaded_record_path"] = record_path
        if isinstance(grant, ScalableHttpGrant):
            # Shared evidence is kept once: the rows stay in the record this
            # envelope cites by path and digest, and are referenced here.
            rows = [dict(item) for item in record.operational_readiness]
            envelope.product["readiness_rows"] = len(rows)
            envelope.product["readiness_sha256"] = _sha256(
                json.dumps(rows, sort_keys=True, default=str)
            )
        else:
            envelope.readiness = [dict(item) for item in record.operational_readiness]
    except Exception as exc:
        problem = f"record_reload_failed:{type(exc).__name__}"
        record_problems.append(problem)
        envelope.persistence_failures.append(problem)
    temporal.cross("record_reload")
    return record, record_path, record_problems


#: At most this many unreturned product records are cited; a fresh-history
#: attempt can have written exactly one.
MAX_CITED_UNRETURNED_RECORDS = 4


def _cite_unreturned_records(attempt: _Attempt) -> None:
    """Cite, by path and digest, what a product that never returned wrote."""
    grant, envelope = attempt.grant, attempt.envelope
    store = attempt.boundaries.record_store
    try:
        names = store.deployment_history(grant.deployment_id)
    except Exception as exc:
        envelope.persistence_failures.append(
            f"product_history_unreadable:{type(exc).__name__}"
        )
        return
    cited: list[dict[str, Any]] = []
    for name in names[:MAX_CITED_UNRETURNED_RECORDS]:
        if not name.endswith(".json"):
            continue
        try:
            record, path, digest = store.load_evidence(
                grant.deployment_id, name.removesuffix(".json")
            )
        except Exception as exc:
            cited.append({"entry": name, "error": type(exc).__name__})
            continue
        cited.append(
            {
                "run_id": record.run_id,
                "record_path": path,
                "record_sha256": digest,
                "persisted_stage": (
                    record.persisted_stage.value if record.persisted_stage else None
                ),
                "completed": record.completed_at is not None,
            }
        )
    envelope.product["unreturned_records"] = cited


def _evaluate(
    attempt: _Attempt,
    tap: _EvidenceTap,
    *,
    record: ServiceRunRecord | None,
    record_path: str,
    record_problems: list[str],
    summary: dict[str, Any] | None,
    ledger_refusals: list[str],
) -> AcceptanceEvaluation:
    """Run the judge over every independent source; a judge failure is kept."""
    envelope = attempt.envelope
    stop_facts = [
        *attempt.stop_facts,
        *ledger_refusals[:MAX_NAMED_REFUSALS],
        *(f"postflight:{item}" for item in envelope.postflight_failures),
    ]
    judge = (
        partial(evaluate_scalable_attempt, attempt.grant, attempt.scope)
        if isinstance(attempt.grant, ScalableHttpGrant)
        else partial(evaluate_attempt, attempt.grant)
    )
    try:
        return judge(
            closure=attempt.closure,
            record=record,
            record_problems=record_problems,
            summary=summary,
            record_path=record_path,
            entries=attempt.ledger.entries,
            answers=tap.answers,
            stop_facts=stop_facts,
        )
    except Exception as exc:
        # Evidence the judge cannot even read is not evidence of acceptance.
        # The attempt still ends with a recorded, terminal envelope.
        return AcceptanceEvaluation(
            reasons=[*stop_facts, f"evaluation_failed:{type(exc).__name__}"]
        )


def _judge(
    attempt: _Attempt,
    result: ServiceStageResult | None,
    evaluation: AcceptanceEvaluation,
    ledger_refusals: list[str],
    temporal: _TemporalContract,
) -> None:
    """Write the verdict and the facts it rests on into the envelope."""
    envelope, ledger = attempt.envelope, attempt.ledger
    envelope.clients = evaluation.clients
    envelope.ordering = evaluation.ordering
    envelope.release_failures = [
        f"{item.client}:{item.release_outcome or 'no_release'}"
        for item in evaluation.clients
        if item.release_outcome != "released"
    ]
    reasons = list(evaluation.reasons)
    if attempt.cancelled:
        reasons.insert(0, attempt.cancelled)
    # The publication boundary: nothing after this point can change the
    # verdict, and the terminal write that follows is not claimed to be
    # preemptible. It is still inside the one absolute deadline or it is late.
    temporal.cross("publication")
    started = attempt.boundaries.clock() - ledger.elapsed()
    envelope.temporal = {
        "deadline_offset_seconds": round(temporal.deadline - started, 3),
        "publication_offset_seconds": round(ledger.elapsed(), 3),
        "exceeded_at": temporal.exceeded_at,
    }
    if temporal.exceeded_at:
        reasons.append(f"acceptance_deadline_exceeded:{temporal.exceeded_at}")
    envelope.reasons = reasons
    envelope.cancellation = attempt.cancelled
    envelope.http_accepted = not reasons
    envelope.campaign_outcome = _campaign_outcome(attempt, result, ledger_refusals)
    envelope.primary_failure = _primary_failure(attempt, result, reasons)


def _campaign_outcome(
    attempt: _Attempt, result: ServiceStageResult | None, ledger_refusals: list[str]
) -> CampaignOutcome:
    """Separate how the campaign ended from whether HTTP was accepted."""
    if attempt.cancelled:
        return CampaignOutcome.STOPPED
    if not attempt.effects_began and (
        result is None or result.stage is ServiceStage.ADMISSION
    ):
        return CampaignOutcome.REFUSED
    if (
        result is None
        or attempt.authority_lost
        or ledger_refusals
        or result.persisted_stage is not ServiceStage.COMPLETED
    ):
        return CampaignOutcome.STOPPED
    return CampaignOutcome.COMPLETED


def _primary_failure(
    attempt: _Attempt, result: ServiceStageResult | None, reasons: Sequence[str]
) -> str:
    """Keep the first fact that stopped or failed the attempt, unchanged."""
    if attempt.cancelled:
        return attempt.cancelled
    if attempt.authority_lost:
        return _bounded(f"authority_lost:{attempt.authority_lost}")
    refused = next((item for item in attempt.ledger.entries if item.refused), None)
    if refused is not None:
        return _bounded(f"ledger_refused:{refused.refused}@{refused.purpose}")
    if result is not None and result.refusal_code.value != "none":
        return _bounded(f"product_refusal:{result.refusal_code.value}")
    if result is not None and result.status.value != "verified":
        return _bounded(f"product_status:{result.status.value}")
    return _bounded(reasons[0]) if reasons else ""


def _budget(
    grant: ColdHttpGrant, ledger: OperationLedger, attempt: _Attempt
) -> AcceptanceBudget:
    return AcceptanceBudget(
        max_operations=grant.max_operations,
        max_seconds=grant.max_seconds,
        reserve_operations=grant.reserve_operations,
        reserve_seconds=grant.reserve_seconds,
        arithmetic=(
            dict(attempt.scope.cost.operation_lines)
            if attempt.scope is not None
            else {}
            if isinstance(grant, ScalableHttpGrant)
            else dict(COLD_HTTP_ARITHMETIC)
        ),
        used_operations=ledger.used,
        refused_calls=ledger.refused_calls,
        reserve_used=ledger.reserve_used,
        elapsed_seconds=round(ledger.elapsed(), 3),
        local_observation_seconds=round(attempt.local_observation_seconds, 3),
        receiver_observations=attempt.receiver_observations,
        receiver_observation_seconds=round(attempt.receiver_seconds, 3),
        entries=list(ledger.entries),
    )


def _close(attempt: _Attempt, opened: OpenedTransport) -> None:
    if opened.transport is None:
        return
    try:
        attempt.boundaries.close_channel(opened)
    except Exception as exc:
        attempt.envelope.postflight_failures.append(
            f"channel_close:{type(exc).__name__}"
        )


def _release_claim(attempt: _Attempt) -> None:
    """Release the campaign lock once; the attempt reservation stays spent."""
    envelope = attempt.envelope
    if attempt.claim is None or "release" in envelope.campaign:
        return
    try:
        reasons = tuple(
            attempt.boundaries.campaign_coordinator.release(attempt.claim) or ()
        )
    except Exception as exc:
        reasons = (f"campaign_release_failed:{type(exc).__name__}",)
    envelope.campaign["release"] = "released" if not reasons else "not_released"
    envelope.campaign["release_reasons"] = list(reasons)
    envelope.postflight_failures.extend(f"campaign_release:{item}" for item in reasons)


def _complete(
    attempt: _Attempt, product_summary: dict[str, Any] | None = None
) -> AcceptanceResult:
    """Release the claim, then write the terminal envelope exactly once.

    The store's order is kept: a write-ahead envelope exists before a terminal
    one. If the early begin failed, it is attempted once more here, as a
    write-ahead envelope, before `completed_at` is set. What still cannot be
    kept is a persistence failure: nothing on disk claims acceptance and the
    caller is told the envelope was not persisted.
    """
    envelope = attempt.envelope
    boundaries = attempt.boundaries
    _release_claim(attempt)
    envelope.budget = _budget(attempt.grant, attempt.ledger, attempt)
    path = attempt.envelope_path
    persisted = False
    try:
        if not attempt.envelope_begun:
            path = boundaries.envelope_store.begin(envelope)
            attempt.envelope_begun = True
    except Exception as exc:
        envelope.persistence_failures.append(f"envelope_not_begun:{type(exc).__name__}")
    envelope.completed_at = boundaries.now()
    started = boundaries.clock()
    if attempt.envelope_begun:
        try:
            path = boundaries.envelope_store.complete(envelope)
            persisted = True
        except Exception as exc:
            envelope.persistence_failures.append(
                f"envelope_not_completed:{type(exc).__name__}"
            )
    if not persisted and envelope.http_accepted:
        # The verdict cannot stand on evidence that was not kept.
        envelope.http_accepted = False
        envelope.reasons.append("envelope_not_persisted")
    attempt.completed = True
    return AcceptanceResult(
        envelope=envelope,
        envelope_path=path,
        product_summary=product_summary,
        persisted=persisted,
        completion_seconds=max(0.0, boundaries.clock() - started),
    )


def _refused(
    envelope: ColdHttpAcceptanceEnvelope, refusals: list[AcceptanceRefusal]
) -> AcceptanceResult:
    """Refuse before any claim: nothing was reserved, so nothing is written."""
    envelope.admission = refusals
    envelope.campaign_outcome = CampaignOutcome.REFUSED
    envelope.primary_failure = _bounded(
        f"{refusals[0].subject.value}:{refusals[0].kind.value}:{refusals[0].detail}"
    )
    envelope.reasons = [
        f"{item.subject.value}:{item.kind.value}:{item.detail}" for item in refusals
    ]
    return AcceptanceResult(envelope=envelope)


def _refused_after_claim(
    attempt: _Attempt, refusals: list[AcceptanceRefusal]
) -> AcceptanceResult:
    """Refuse a reserved attempt and record why, since its identity is spent."""
    envelope = attempt.envelope
    envelope.admission = refusals
    envelope.campaign_outcome = CampaignOutcome.REFUSED
    envelope.primary_failure = _bounded(
        f"{refusals[0].subject.value}:{refusals[0].kind.value}:{refusals[0].detail}"
    )
    envelope.reasons = [
        f"{item.subject.value}:{item.kind.value}:{item.detail}" for item in refusals
    ]
    return _complete(attempt)
