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
   The write-ahead envelope is created last. A refusal here dispatched nothing.
2. **One fixed channel.** The granted channel is opened and its liveness read
   before a ledger or a runtime exists. Every product dispatch then passes one
   `OperationLedger`: counted once, admitted against one absolute deadline,
   decided against the held campaign claim, and labelled by the product
   boundary that made it. The compiled closure is compared with the grant
   before E1. Only owned client releases may spend the protected reserve.
3. **Finalization and judgement.** The mailbox is paired again, the run record
   is reloaded and compared with the public result, the dispatch order is
   checked from the ledger, and the envelope is completed once.

The local checks are not an in-band receiver fence, and nothing here claims
exactly-once execution or the exclusion of a replacement process. The grant
accepts that limitation and an exclusive disposable laboratory explicitly.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
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
    effect_scope_findings,
    manifest_refusals,
    parse_grant,
    process_refusals,
    repository_acceptance_refusals,
)
from ...domain.enterprise.models.deployment import DeploymentManifest
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
from ..ports.cold_http_acceptance import AcceptanceEnvelopePort, AcceptanceRunRecordPort
from ..ports.service_qualification import OpenedTransport, QualificationTransport
from ..ports.service_run_record import DeploymentManifestPort
from .apply_enterprise_services import (
    MAX_INTENT_JSON_BYTES,
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


@dataclass
class AcceptanceResult:
    """What one attempt returns to its adapter."""

    envelope: ColdHttpAcceptanceEnvelope
    envelope_path: str = ""
    product_summary: dict[str, Any] | None = None

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
            "envelope_path": self.envelope_path,
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


class _LabelledConfiguration:
    """The E5 runtime, with each boundary's dispatches named in the ledger."""

    def __init__(self, inner: Any, ledger: OperationLedger) -> None:
        self._inner = inner
        self._ledger = ledger

    def inventory(self):
        with self._ledger.purpose_of(PURPOSE_INVENTORY):
            return self._inner.inventory()

    def apply_actions(self, actions):
        with self._ledger.purpose_of(PURPOSE_E5_APPLY):
            return self._inner.apply_actions(actions)

    def verify(self, expectations):
        with self._ledger.purpose_of(PURPOSE_E5_VERIFY):
            return self._inner.verify(expectations)

    def wait_for_voice_access_forwarding(self, expectations):
        with self._ledger.purpose_of("e5_voice_forwarding"):
            return self._inner.wait_for_voice_access_forwarding(expectations)

    def observe_access_forwarding(self, *args, **kwargs):
        with self._ledger.purpose_of(PURPOSE_READINESS):
            return self._inner.observe_access_forwarding(*args, **kwargs)


class _LabelledServices:
    """The E6 runtime, with each boundary's dispatches named in the ledger."""

    def __init__(self, inner: Any, ledger: OperationLedger) -> None:
        self._inner = inner
        self._ledger = ledger

    def inventory(self):
        with self._ledger.purpose_of(PURPOSE_INVENTORY):
            return self._inner.inventory()

    def apply_actions(self, actions):
        with self._ledger.purpose_of(PURPOSE_E6_APPLY):
            return self._inner.apply_actions(actions)

    def verify(self, expectation):
        with self._ledger.purpose_of(E6_VERIFY_PREFIX + expectation.id):
            return self._inner.verify(expectation)


class _LabelledObserver:
    """The admission drift reader, named as such in the ledger."""

    def __init__(self, inner: Any, ledger: OperationLedger) -> None:
        self._inner = inner
        self._ledger = ledger

    def observe(self, runtime_device_name: str, interface: str):
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

    def authority(self, purpose: str, deadline: float) -> str:
        """Decide one dispatch against the held claim; the first loss is sticky."""
        del purpose, deadline
        if self.authority_lost:
            return self.authority_lost
        try:
            reasons = tuple(
                self.boundaries.campaign_coordinator.verify(self.claim) or ()
            )
        except Exception as exc:
            reasons = (f"campaign_claim:unverifiable:{type(exc).__name__}",)
        if reasons:
            self.authority_lost = _bounded(reasons[0])
            self.stop_facts.append(f"authority_lost:{self.authority_lost}")
        return self.authority_lost

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
    grant, refusals = parse_grant(request.grant_document, boundaries.proposal)
    if grant is None:
        return _refused(envelope, list(refusals))
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
    envelope.checks.append("campaign_claim")
    summary = getattr(attempt.claim, "compact_summary", None)
    envelope.campaign = {"claim": summary() if callable(summary) else {}}
    try:
        return _claimed(request, attempt)
    finally:
        # Every ordinary path released the claim before completing the
        # envelope; this only covers a path that raised out of the attempt.
        if "release" not in envelope.campaign:
            _release_claim(attempt)


def _claimed(request: AcceptanceRequest, attempt: _Attempt) -> AcceptanceResult:
    """Finish local admission while the campaign claim is held."""
    grant, envelope, boundaries = attempt.grant, attempt.envelope, attempt.boundaries
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
    return _contact(request, attempt, manifest)


def _contact(
    request: AcceptanceRequest, attempt: _Attempt, manifest: DeploymentManifest
) -> AcceptanceResult:
    """Open the granted channel and run the one product invocation over it."""
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
    try:
        session = boundaries.session_factory(channel)

        def labelled_session() -> ServiceInvocationBinding:
            with ledger.purpose_of(PURPOSE_ENVIRONMENT):
                binding = session()
            return _labelled(binding, attempt)

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
    ledger.enter(LedgerPhase.FINALIZATION)
    if bound.settle_pending_sends():
        attempt.stop_facts.append("fire_and_forget_send_unresolved")
    _close(attempt, opened)
    return _finalize(attempt, tap, result, product_error)


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

    return replace(
        binding,
        runtimes=ServiceStageRuntimes(
            configuration=_LabelledConfiguration(
                binding.runtimes.configuration, ledger
            ),
            services=_LabelledServices(binding.runtimes.services, ledger),
        ),
        record_store=attempt.boundaries.record_store,
        endpoint_observer=(
            _LabelledObserver(binding.endpoint_observer, ledger)
            if binding.endpoint_observer is not None
            else None
        ),
        inventory_reader=labelled_inventory,
        # Whatever the adapter composed, the admission that decides this
        # attempt's closure is this attempt's own.
        effect_admission=attempt.admit_closure,
    )


def _finalize(
    attempt: _Attempt,
    tap: _EvidenceTap,
    result: ServiceStageResult | None,
    product_error: str,
) -> AcceptanceResult:
    """Pair the process again, reload the record, judge, and complete once."""
    grant, envelope, boundaries = attempt.grant, attempt.envelope, attempt.boundaries
    ledger = attempt.ledger
    deadline = ledger.deadline()
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

    summary = result.compact_summary() if result is not None else None
    record: ServiceRunRecord | None = None
    record_path = ""
    record_problems: list[str] = []
    if product_error:
        record_problems.append(product_error)
    if result is not None:
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
            envelope.readiness = [dict(item) for item in record.operational_readiness]
        except Exception as exc:
            problem = f"record_reload_failed:{type(exc).__name__}"
            record_problems.append(problem)
            envelope.persistence_failures.append(problem)

    # The claim is released before the verdict, because its release is a
    # finalization result like any other: a lock that another writer holds or
    # that cannot be read says the exclusion did not cover this run to its end.
    _release_claim(attempt)
    ledger_refusals = [
        f"ledger_refused:{item.refused}@{item.purpose or 'none'}"
        for item in ledger.entries
        if item.refused
    ]
    stop_facts = [
        *attempt.stop_facts,
        *ledger_refusals[:MAX_NAMED_REFUSALS],
        *(f"postflight:{item}" for item in envelope.postflight_failures),
    ]
    try:
        evaluation = evaluate_attempt(
            grant,
            closure=attempt.closure,
            record=record,
            record_problems=record_problems,
            summary=summary,
            record_path=record_path,
            entries=ledger.entries,
            answers=tap.answers,
            stop_facts=stop_facts,
        )
    except Exception as exc:
        # Evidence the judge cannot even read is not evidence of acceptance.
        # The attempt still ends with a recorded, terminal envelope.
        evaluation = AcceptanceEvaluation(
            reasons=[*stop_facts, f"evaluation_failed:{type(exc).__name__}"]
        )
    envelope.clients = evaluation.clients
    envelope.ordering = evaluation.ordering
    envelope.release_failures = [
        f"{item.client}:{item.release_outcome or 'no_release'}"
        for item in evaluation.clients
        if item.release_outcome != "released"
    ]
    envelope.reasons = list(evaluation.reasons)
    envelope.http_accepted = evaluation.accepted
    envelope.campaign_outcome = _campaign_outcome(attempt, result, ledger_refusals)
    envelope.primary_failure = _primary_failure(attempt, result, evaluation.reasons)
    return _complete(attempt, product_summary=summary)


def _campaign_outcome(
    attempt: _Attempt, result: ServiceStageResult | None, ledger_refusals: list[str]
) -> CampaignOutcome:
    """Separate how the campaign ended from whether HTTP was accepted."""
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
        arithmetic=dict(COLD_HTTP_ARITHMETIC),
        used_operations=ledger.used,
        refused_calls=ledger.refused_calls,
        reserve_used=ledger.reserve_used,
        elapsed_seconds=round(ledger.elapsed(), 3),
        local_observation_seconds=round(attempt.local_observation_seconds, 3),
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
    """Release the claim, then write the terminal envelope exactly once."""
    envelope = attempt.envelope
    _release_claim(attempt)
    envelope.budget = _budget(attempt.grant, attempt.ledger, attempt)
    envelope.completed_at = attempt.boundaries.now()
    path = attempt.envelope_path
    try:
        if not attempt.envelope_begun:
            path = attempt.boundaries.envelope_store.begin(envelope)
            attempt.envelope_begun = True
        path = attempt.boundaries.envelope_store.complete(envelope)
    except Exception as exc:
        # The verdict cannot stand on evidence that was not kept. The outcome
        # is reported to the caller, and nothing on disk claims acceptance.
        envelope.persistence_failures.append(
            f"envelope_not_completed:{type(exc).__name__}"
        )
        if envelope.http_accepted:
            envelope.http_accepted = False
            envelope.reasons.append("envelope_not_persisted")
    return AcceptanceResult(
        envelope=envelope,
        envelope_path=path,
        product_summary=product_summary,
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
