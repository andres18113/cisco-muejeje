"""Judge one scalable HTTP-by-IP attempt from its ledger, record and scope.

The derived scope says what each selected client needed: its one request, its
server's URL, its access placements and every readiness group its path names.
The reloaded record says what the product concluded; the ledger says, in
order, what was dispatched under which boundary. A client is accepted only
when all three agree, and the attempt only when every selected client is.
Readiness is never taken from the record's labels: `readiness_evidence`
re-derives each client's permission from the raw observation of the episode
that decided it.

Every judgement reads indexes and evidence built once, so the assembly is
linear in the retained evidence plus the selected relationships. Every
selected client is represented, whether or not it ever dispatched anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..models.cold_http_acceptance import ClientAcceptance
from ..models.scalable_http_acceptance import AcceptanceScope, ScalableHttpGrant
from ..models.service_entry import ServiceEffectClosure
from ..models.service_qualification import OperationEntry
from ..models.service_run_record import ServiceRunRecord
from .acceptance_evidence_index import (
    E6_VERIFY_PREFIX,
    OWNED_RELEASE_PREFIX,
    READINESS_PREFIX,
    LedgerIndex,
    readiness_episode_spans,
    verification_rows,
)
from .cold_http_acceptance_evidence import (
    AcceptanceEvaluation,
    judge_client_request,
    product_outcome_findings,
    record_identity_findings,
    reload_differences,
)
from .readiness_evidence import ReadinessEvidence

_FIXED_PURPOSES = frozenset(
    {"a5_environment", "a8_inventory", "a10_drift", "e5_apply", "e5_verify", "e6_apply"}
)


def _in_scope(
    purpose: str, groups: set[str], requests: set[str], checks: set[str]
) -> bool:
    """Whether one dispatched purpose names the derived scope exactly."""
    if purpose in _FIXED_PURPOSES:
        return True
    if purpose.startswith(READINESS_PREFIX):
        key, marker, ordinal = purpose[len(READINESS_PREFIX) :].rpartition("#")
        return bool(marker) and key in groups and ordinal.isdigit() and int(ordinal) > 0
    if purpose.startswith(E6_VERIFY_PREFIX):
        return purpose[len(E6_VERIFY_PREFIX) :] in checks
    if purpose.startswith(OWNED_RELEASE_PREFIX):
        return purpose[len(OWNED_RELEASE_PREFIX) :] in requests
    # Reported as unlabelled, not twice.
    return True


def scalable_ordering_findings(
    scope: AcceptanceScope,
    ledger: LedgerIndex,
    spans: Mapping[str, Mapping[int, tuple[int, int]]] | None = None,
) -> list[str]:
    """Check the dispatch order every client requires, from the ledger alone.

    This is the ledger's own view: labels, fixed boundaries, the E5 readback
    before any readiness, E6 before every request, one client at a time and
    one release each. Which episode admitted each client, and when, is bound
    per client by `readiness_evidence`.
    """
    spans = readiness_episode_spans(ledger) if spans is None else spans
    found: list[str] = []
    unlabelled = sorted(
        {
            purpose or "<none>"
            for purpose in ledger.purposes()
            if purpose not in _FIXED_PURPOSES
            and not purpose.startswith(
                (READINESS_PREFIX, E6_VERIFY_PREFIX, OWNED_RELEASE_PREFIX)
            )
        }
    )
    if unlabelled:
        found.append("unlabelled_dispatches:" + ",".join(unlabelled[:8]))
    # A labelled dispatch still has to name the derived scope: a readiness
    # episode of one of its groups, or a request, release or direct check of
    # one of its expectations. Anything else was done outside the scope.
    groups = {item.key for item in scope.groups}
    selected = {item.expectation_id for item in scope.clients}
    checks = selected | {
        item.direct_check for item in scope.servers if item.direct_check
    }
    outside = sorted(
        purpose
        for purpose in ledger.purposes()
        if not _in_scope(purpose, groups, selected, checks)
    )
    if outside:
        found.append("dispatches_outside_scope:" + ",".join(outside[:8]))
    e5_verify = ledger.positions("e5_verify")
    e6_apply = ledger.positions("e6_apply")
    # Positions are in ledger order, so each boundary's last dispatch is its
    # last element; nothing below scans a boundary per client.
    e5_last = e5_verify[-1] if e5_verify else None
    e6_last = e6_apply[-1] if e6_apply else None
    first_episode = {
        key: min(span[0] for span in episodes.values())
        for key, episodes in spans.items()
        if episodes
    }
    readiness_first = min(first_episode.values(), default=None)
    if (
        readiness_first is not None
        and e5_last is not None
        and readiness_first < e5_last
    ):
        found.append("forwarding_observed_before_e5_readback_finished")
    windows = []
    for client in scope.clients:
        requests = ledger.positions(E6_VERIFY_PREFIX + client.expectation_id)
        releases = ledger.positions(OWNED_RELEASE_PREFIX + client.expectation_id)
        if requests:
            windows.append((requests[0], client, requests, releases))
    previous_end: int | None = None
    for first, client, requests, releases in sorted(windows, key=lambda item: item[0]):
        name = client.name
        if e5_last is None or e5_last > first:
            found.append(f"request_not_after_e5_readback:{name}")
        if e6_last is None or e6_last > first:
            found.append(f"request_before_e6_apply:{name}")
        for key in client.groups:
            observed = first_episode.get(key)
            if observed is None or observed > first:
                found.append(f"request_without_prior_group_observation:{name}:{key}")
        if previous_end is not None and first < previous_end:
            found.append(f"request_before_previous_client_finished:{name}")
        if len(releases) != 1:
            found.append(f"owned_release_dispatches:{name}:{len(releases)}")
        elif releases[0] < requests[-1]:
            found.append(f"release_before_last_request_dispatch:{name}")
        previous_end = max(requests[-1], releases[-1] if releases else requests[-1])
    return found


def evaluate_scalable_attempt(
    grant: ScalableHttpGrant,
    scope: AcceptanceScope | None,
    *,
    closure: ServiceEffectClosure | None,
    record: ServiceRunRecord | None,
    record_problems: Sequence[str],
    summary: Mapping[str, Any] | None,
    record_path: str,
    entries: Sequence[OperationEntry],
    answers: Mapping[str, Sequence[str]],
    stop_facts: Sequence[str],
) -> AcceptanceEvaluation:
    """Decide acceptance for every selected client from indexed evidence."""
    evaluation = AcceptanceEvaluation()
    reasons = evaluation.reasons
    reasons.extend(stop_facts)
    reasons.extend(record_problems)
    if scope is None:
        reasons.append("scope_not_derived")
        return evaluation
    ledger = LedgerIndex.build(entries)
    spans = readiness_episode_spans(ledger)
    rows = verification_rows(record)
    readiness = ReadinessEvidence.build(
        record.operational_readiness if record else [], scope, ledger, spans
    )
    if record is None or summary is None:
        reasons.append("durable_record_unavailable")
    else:
        reasons.extend(reload_differences(record, summary, expected_path=record_path))
        reasons.extend(record_identity_findings(grant, record, closure))
        reasons.extend(product_outcome_findings(record))
        # Faults of the record's readiness evidence itself, each named once;
        # the clients they touch carry one bounded reference each.
        reasons.extend(readiness.evidence_findings())
    evaluation.ordering = scalable_ordering_findings(scope, ledger, spans)
    reasons.extend(evaluation.ordering)
    firsts: dict[str, int] = {}
    for item in scope.clients:
        positions = ledger.positions(E6_VERIFY_PREFIX + item.expectation_id)
        if positions:
            firsts[item.expectation_id] = positions[0]
    order = {
        position: rank + 1 for rank, position in enumerate(sorted(firsts.values()))
    }
    for client in scope.clients:
        request_purpose = E6_VERIFY_PREFIX + client.expectation_id
        release_purpose = OWNED_RELEASE_PREFIX + client.expectation_id
        first = firsts.get(client.expectation_id)
        outcome = judge_client_request(
            name=client.name,
            switch_port=client.port,
            expectation_id=client.expectation_id,
            url=client.url,
            marker=grant.marker,
            row=rows.get(client.expectation_id),
            requests=ledger.dispatches(request_purpose),
            releases=ledger.dispatches(release_purpose),
            refused_releases=ledger.refusals(release_purpose),
            start_answers=answers.get(request_purpose) or (),
            release_answers=answers.get(release_purpose) or (),
            request_order=order.get(first) if first is not None else None,
        )
        if record is not None:
            outcome.findings.extend(readiness.findings_for(client, first))
            outcome.accepted = not outcome.findings
        evaluation.clients.append(outcome)
        reasons.extend(f"{client.name}:{item}" for item in outcome.findings)
    return evaluation


def client_rows_summary(clients: Sequence[ClientAcceptance]) -> dict[str, int]:
    """Count accepted, refused and never-started clients for a compact report."""
    return {
        "selected": len(clients),
        "accepted": sum(1 for item in clients if item.accepted),
        "never_started": sum(1 for item in clients if item.dispatches == 0),
    }
