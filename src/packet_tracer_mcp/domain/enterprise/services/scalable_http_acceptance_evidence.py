"""Judge one scalable HTTP-by-IP attempt from its ledger, record and scope.

The derived scope says what each selected client needed: its one request, its
server's URL, its access placements and every readiness group its path names.
The reloaded record says what the product concluded; the ledger says, in
order, what was dispatched under which boundary. A client is accepted only
when all three agree, and the attempt only when every selected client is.

Every judgement reads prebuilt indexes, so the assembly is linear in the
retained evidence plus the selected relationships. Every selected client is
represented, whether or not it ever dispatched anything.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..models.cold_http_acceptance import ClientAcceptance
from ..models.scalable_http_acceptance import (
    AcceptanceScope,
    ScalableHttpGrant,
    ScopedClient,
)
from ..models.service_entry import ServiceEffectClosure
from ..models.service_qualification import OperationEntry
from ..models.service_run_record import ServiceRunRecord
from .acceptance_evidence_index import (
    E6_VERIFY_PREFIX,
    OWNED_RELEASE_PREFIX,
    LedgerIndex,
    ReadinessIndex,
    verification_rows,
)
from .access_forwarding import CONFIRMED_UNIQUE, FORWARDING_STATES
from .cold_http_acceptance_evidence import (
    AcceptanceEvaluation,
    judge_client_request,
    product_outcome_findings,
    record_identity_findings,
    reload_differences,
)

#: The readiness purpose prefix the scalable composition labels with; the
#: group key the closure named follows it.
READINESS_PREFIX = "readiness:"
_FIXED_PURPOSES = frozenset(
    {"a5_environment", "a8_inventory", "a10_drift", "e5_apply", "e5_verify", "e6_apply"}
)

_AUTHORITATIVE_SAMPLE = {
    "executed": True,
    "fresh_output_observed": True,
    "output_complete": True,
    "vlan_present": True,
    "sample_budget_exhausted": False,
    "deadline_reached": False,
}


def _port_forwards(rows: object, port: str) -> bool:
    for item in rows if isinstance(rows, list) else []:
        if isinstance(item, Mapping) and item.get("interface") == port:
            return item.get("matches") == 1 and (
                str(item.get("state")).upper() in FORWARDING_STATES
            )
    return False


def _access_findings(
    row: Mapping[str, Any], switch: str, vlan: int, port: str
) -> list[str]:
    """Re-read one admitting access sample for one port of one client."""
    found: list[str] = []
    if row.get("status") != "admitted":
        found.append(f"access_group_not_admitted:{switch}")
    sample = row.get("sample")
    if not isinstance(sample, Mapping) or not sample:
        return [*found, f"access_sample_absent:{switch}"]
    if sample.get("switch") != switch or sample.get("vlan_id") != vlan:
        found.append(f"access_sample_is_not_the_group:{switch}")
    if sample.get("observed_device_name") != switch:
        found.append(f"access_observed_device_is_not_the_switch:{switch}")
    if sample.get("device_identity_provenance") != CONFIRMED_UNIQUE:
        found.append(f"access_identity_not_confirmed_unique:{switch}")
    if sample.get("sample_after_deadline") is not False:
        found.append(f"access_sample_after_deadline:{switch}")
    for key, expected in _AUTHORITATIVE_SAMPLE.items():
        if sample.get(key) is not expected:
            found.append(f"access_{key}_not_{str(expected).lower()}:{switch}")
    if not _port_forwards(sample.get("rows"), port):
        found.append(f"access_port_not_forwarding:{switch}:{port}")
    history = sample.get("sample_history")
    deciding = history[-1] if isinstance(history, list) and history else {}
    if not isinstance(deciding, Mapping) or not _port_forwards(
        deciding.get("rows"), port
    ):
        found.append(f"access_deciding_sample_port_not_forwarding:{switch}:{port}")
    return found


def _joined(row: Mapping[str, Any], dependent: Mapping[str, Any]) -> bool:
    """Re-derive one pair's join from the deciding round of a continuity row."""
    sample = row.get("sample")
    if not isinstance(sample, Mapping):
        return False
    rounds = sample.get("rounds")
    if (
        sample.get("episode_end_reason") != "required_pairs_joined"
        or not isinstance(rounds, list)
        or not rounds
    ):
        return False
    deciding = rounds[-1]
    if not isinstance(deciding, Mapping) or deciding.get("complete") is not True:
        return False
    readings = deciding.get("readings")
    if not isinstance(readings, list) or any(
        not isinstance(item, Mapping) or item.get("after_deadline") is not False
        for item in readings
    ):
        return False
    usable = set(deciding.get("usable_links") or [])
    parent: dict[str, str] = {}

    def root(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for link in row.get("links") or []:
        if isinstance(link, Mapping) and link.get("link_id") in usable:
            left = root(str(link.get("switch_a_id")))
            right = root(str(link.get("switch_b_id")))
            if left != right:
                parent[max(left, right)] = min(left, right)
    client = str(dependent.get("client_switch_id") or "")
    host = str(dependent.get("host_switch_id") or "")
    return bool(client and host and root(client) == root(host))


def readiness_findings_for(
    client: ScopedClient, scope: AcceptanceScope, readiness: ReadinessIndex
) -> list[str]:
    """Require every group the client's path names to have admitted it."""
    found: list[str] = []
    groups = {item.key: item for item in scope.groups}
    for key in client.groups:
        group = groups.get(key)
        if group is None:
            found.append(f"group_not_in_scope:{key}")
            continue
        if group.kind == "access":
            switch = group.switches[0]
            rows = readiness.access.get((switch, group.vlan_id), [])
            row = readiness.admitting_row(rows, client.expectation_id)
            if row is None:
                found.append(f"access_group_did_not_admit:{switch}")
                continue
            ports = [
                port
                for owner, port in (
                    (client.switch, client.port),
                    (client.server_switch, client.server_port),
                )
                if owner == switch
            ]
            for port in ports:
                found.extend(_access_findings(row, switch, group.vlan_id, port))
        else:
            rows = readiness.continuity.get(
                (group.vlan_id, frozenset(group.switches)), []
            )
            row = readiness.admitting_row(rows, client.expectation_id)
            if row is None:
                found.append(f"continuity_group_did_not_admit:{group.vlan_id}")
                continue
            dependent = readiness.dependent(row, client.expectation_id) or {}
            if row.get("status") != "admitted":
                found.append(f"continuity_group_not_admitted:{group.vlan_id}")
            if not _joined(row, dependent):
                found.append(f"continuity_pair_not_rederived:{group.vlan_id}")
    if not client.groups:
        found.append("no_readiness_group")
    return found


def scalable_ordering_findings(
    scope: AcceptanceScope, ledger: LedgerIndex
) -> list[str]:
    """Check the dispatch order every client requires, from the ledger alone."""
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
    e5_verify = ledger.positions("e5_verify")
    e6_apply = ledger.positions("e6_apply")
    readiness_first = min(
        (
            position
            for purpose in ledger.purposes()
            if purpose.startswith(READINESS_PREFIX)
            for position in ledger.positions(purpose)
        ),
        default=None,
    )
    if readiness_first is not None and e5_verify and readiness_first < max(e5_verify):
        found.append("forwarding_observed_before_e5_readback_finished")
    windows: list[tuple[int, ScopedClient, list[int], list[int]]] = []
    for client in scope.clients:
        requests = ledger.positions(E6_VERIFY_PREFIX + client.expectation_id)
        releases = ledger.positions(OWNED_RELEASE_PREFIX + client.expectation_id)
        if requests:
            windows.append((requests[0], client, requests, releases))
    previous_end: int | None = None
    for first, client, requests, releases in sorted(windows, key=lambda item: item[0]):
        name = client.name
        if not e5_verify or max(e5_verify) > first:
            found.append(f"request_not_after_e5_readback:{name}")
        if not e6_apply or max(e6_apply) > first:
            found.append(f"request_before_e6_apply:{name}")
        for key in client.groups:
            observed = ledger.positions(READINESS_PREFIX + key)
            if not observed or observed[0] > first:
                found.append(f"request_without_prior_group_observation:{name}:{key}")
        if previous_end is not None and first < previous_end:
            found.append(f"request_before_previous_client_finished:{name}")
        if len(releases) != 1:
            found.append(f"owned_release_dispatches:{name}:{len(releases)}")
        elif releases[0] < requests[-1]:
            found.append(f"release_before_last_request_dispatch:{name}")
        previous_end = max([*requests, *releases])
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
    rows = verification_rows(record)
    readiness = ReadinessIndex.build(record.operational_readiness if record else [])
    if record is None or summary is None:
        reasons.append("durable_record_unavailable")
    else:
        reasons.extend(reload_differences(record, summary, expected_path=record_path))
        reasons.extend(record_identity_findings(grant, record, closure))
        reasons.extend(product_outcome_findings(record))
    evaluation.ordering = scalable_ordering_findings(scope, ledger)
    reasons.extend(evaluation.ordering)
    firsts = sorted(
        (ledger.positions(E6_VERIFY_PREFIX + item.expectation_id) or [None])[0]
        for item in scope.clients
        if ledger.positions(E6_VERIFY_PREFIX + item.expectation_id)
    )
    order = {position: rank + 1 for rank, position in enumerate(firsts)}
    for client in scope.clients:
        request_purpose = E6_VERIFY_PREFIX + client.expectation_id
        release_purpose = OWNED_RELEASE_PREFIX + client.expectation_id
        requests = ledger.dispatches(request_purpose)
        positions = ledger.positions(request_purpose)
        outcome = judge_client_request(
            name=client.name,
            switch_port=client.port,
            expectation_id=client.expectation_id,
            url=client.url,
            marker=grant.marker,
            row=rows.get(client.expectation_id),
            requests=requests,
            releases=ledger.dispatches(release_purpose),
            refused_releases=ledger.refusals(release_purpose),
            start_answers=answers.get(request_purpose) or (),
            release_answers=answers.get(release_purpose) or (),
            request_order=order.get(positions[0]) if positions else None,
        )
        if record is not None:
            outcome.findings.extend(readiness_findings_for(client, scope, readiness))
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
