"""Judge one cold-HTTP acceptance attempt from its ledger and its durable record.

The product reports its own result, and that report is the thing under test.
Nothing here trusts it on its word. The ledger says, dispatch by dispatch and
in the order they happened, which product boundary asked the engine for what;
the reloaded `ServiceRunRecord` says what the product concluded and kept. An
attempt is accepted only when the two agree with each other, with the public
result and with the grant, and when the order of the dispatches is the order
the acceptance requires: E5 readback, then an admitted exact FWD observation,
then each client's first request, PC1 released before PC2 starts.

A missing, malformed, late, foreign-owner or contradictory fact is never read
as a pass. An HTTP timeout is inconclusive, not a refusal by the listener.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models.cold_http_acceptance import (
    MAX_ANSWER_CHARS,
    ClientAcceptance,
    ColdHttpGrant,
)
from ..models.configuration_runtime import ActionExecutionStatus
from ..models.service_entry import ServiceEffectClosure, ServiceStage
from ..models.service_qualification import OperationEntry
from ..models.service_run_record import ServiceRunRecord
from ..models.service_runtime import ObservationFact
from .access_forwarding import CONFIRMED_UNIQUE, FORWARDING_STATES
from .service_access_readiness import READINESS_ADMITTED

#: The ledger purposes the acceptance composition labels product calls with.
PURPOSE_ENVIRONMENT = "a5_environment"
PURPOSE_INVENTORY = "a8_inventory"
PURPOSE_DRIFT = "a10_drift"
PURPOSE_E5_APPLY = "e5_apply"
PURPOSE_E5_VERIFY = "e5_verify"
PURPOSE_READINESS = "readiness"
PURPOSE_E6_APPLY = "e6_apply"
E6_VERIFY_PREFIX = "e6_verify:"
OWNED_RELEASE_PREFIX = "owned_release:"
_KNOWN_PURPOSES = frozenset(
    {
        PURPOSE_ENVIRONMENT,
        PURPOSE_INVENTORY,
        PURPOSE_DRIFT,
        PURPOSE_E5_APPLY,
        PURPOSE_E5_VERIFY,
        PURPOSE_READINESS,
        PURPOSE_E6_APPLY,
    }
)

#: The public-result keys whose value the durable record must reproduce.
_RECORD_PROJECTION = (
    "run_id",
    "run_label",
    "deployment_id",
    "status",
    "refusal_code",
    "blocked_reason",
    "transport",
    "packet_tracer_version",
    "provenance",
    "e5_effect_scope",
    "e5_effect_uncertain",
    "services",
    "clients",
    "operational_readiness",
    "releases",
    "dirty_state",
    "persisted_stage",
    "limitations",
)


def bounded_answer(body: str | None) -> str:
    """Keep one raw terminal answer as evidence, bounded and unparsed."""
    return str(body or "")[:MAX_ANSWER_CHARS]


def record_projection(record: ServiceRunRecord) -> dict[str, Any]:
    """Project a stored record onto the public result's interpretive keys."""
    return {
        "run_id": record.run_id,
        "run_label": record.run_label,
        "deployment_id": record.deployment_id,
        "status": record.status.value,
        "refusal_code": record.refusal_code.value,
        "blocked_reason": record.blocked_reason,
        "transport": record.transport,
        "packet_tracer_version": record.packet_tracer_version,
        "provenance": dict(record.capability_snapshot.provenance_by_key),
        "e5_effect_scope": record.e5_effect_scope.model_dump(mode="json"),
        "e5_effect_uncertain": record.e5_effect_uncertain,
        "services": [item.model_dump(mode="json") for item in record.services],
        "clients": [item.model_dump(mode="json") for item in record.clients],
        "operational_readiness": [dict(item) for item in record.operational_readiness],
        "releases": [item.model_dump(mode="json") for item in record.releases],
        "dirty_state": record.dirty_state.value,
        "persisted_stage": (
            record.persisted_stage.value if record.persisted_stage else None
        ),
        "limitations": list(record.limitations),
    }


def reload_differences(
    record: ServiceRunRecord,
    summary: Mapping[str, Any],
    *,
    expected_path: str,
) -> list[str]:
    """Name every public-result field the reloaded record does not reproduce."""
    found: list[str] = []
    projected = json.loads(json.dumps(record_projection(record)))
    public = json.loads(json.dumps(dict(summary), default=str))
    for key in _RECORD_PROJECTION:
        if key not in public:
            found.append(f"public_result_lacks:{key}")
        elif projected[key] != public[key]:
            found.append(f"record_differs_from_public_result:{key}")
    if str(summary.get("record_path") or "") != expected_path:
        found.append("public_record_path_is_not_the_reloaded_record")
    if summary.get("persist_error"):
        found.append("public_result_reports_persist_error")
    return found


def record_identity_findings(
    grant: ColdHttpGrant,
    record: ServiceRunRecord,
    closure: ServiceEffectClosure | None,
) -> list[str]:
    """Bind the stored run to the grant and to the admitted closure."""
    found: list[str] = []
    for observed, expected, name in (
        (record.deployment_id, grant.deployment_id, "deployment_id"),
        (record.manifest_hash, grant.manifest_hash, "manifest_hash"),
        (
            record.physical_topology_hash,
            grant.physical_topology_hash,
            "physical_topology_hash",
        ),
        (record.transport, grant.channel, "transport"),
        (record.packet_tracer_version, grant.build, "packet_tracer_version"),
        (record.run_label, grant.run_label, "run_label"),
        (record.source_tree.sha, grant.sha, "source_sha"),
    ):
        if observed != expected:
            found.append(f"record_{name}_mismatch")
    if not record.source_tree.tree:
        # A schema-1 record written before the tree was retained still loads,
        # and says nothing about the bytes that executed. It cannot satisfy an
        # exact provenance requirement, whatever else it says.
        found.append("record_source_tree_absent")
    elif record.source_tree.tree != grant.tree:
        found.append("record_source_tree_mismatch")
    if record.source_tree.dirty:
        found.append("record_source_tree_dirty")
    if record.persisted_stage is not ServiceStage.COMPLETED:
        found.append("record_not_completed")
    if record.persist_error:
        found.append("record_persist_error")
    if record.e5_effect_scope.retained:
        found.append("record_retained_e5_actions")
    if closure is None:
        found.append("no_admitted_closure")
    else:
        if sorted(record.e5_effect_scope.mutated) != sorted(closure.mutated):
            found.append("record_mutated_scope_differs_from_admitted_closure")
        if sorted(record.e5_effect_scope.excluded) != sorted(closure.excluded):
            found.append("record_excluded_scope_differs_from_admitted_closure")
        if record.configuration_semantic_hash != closure.configuration_semantic_hash:
            found.append("record_configuration_hash_differs_from_closure")
        if record.service_semantic_hash != closure.service_semantic_hash:
            found.append("record_service_hash_differs_from_closure")
        if sorted(record.selected_action_ids) != sorted(
            item.action_id for item in closure.service_actions
        ):
            found.append("record_service_actions_differ_from_closure")
        if sorted(record.selected_service_ids) != sorted(closure.selected_service_ids):
            found.append("record_services_differ_from_closure")
    return found


#: Field verdicts an E5 readback may carry and still support its action. A
#: field the engine cannot report, such as an endpoint's gateway, stays
#: unobservable; it is never promoted, and it never refutes the others.
_ADMISSIBLE_FIELDS = frozenset({"verified", "unobservable"})
_ENDPOINT_FIELDS = ("ipv4", "netmask")


def product_outcome_findings(record: ServiceRunRecord) -> list[str]:
    """Require the product's own verdict and a supporting E5 readback per action."""
    found: list[str] = []
    if record.status.value != "verified":
        found.append(f"product_status:{record.status.value}")
    if record.refusal_code.value != "none":
        found.append(f"product_refusal:{record.refusal_code.value}")
    if record.e5_effect_uncertain:
        found.append("product_e5_effect_uncertain")
    if record.service_result is None:
        found.append("no_e6_result")
    result = record.configuration_result
    if result is None:
        return [*found, "no_e5_result"]
    applied = {
        item.action_id: item.status
        for item in result.action_results
        if item.action_id in record.e5_effect_scope.mutated
    }
    readback: dict[str, list[Any]] = {}
    for row in result.verification_results:
        readback.setdefault(row.action_id, []).append(row)
    for action_id in record.e5_effect_scope.mutated:
        status = applied.get(action_id)
        if status not in (
            ActionExecutionStatus.APPLIED,
            ActionExecutionStatus.VERIFIED,
        ):
            found.append(f"e5_action_not_applied:{action_id}")
        rows = readback.get(action_id, [])
        if len(rows) != 1:
            found.append(f"e5_readback_rows:{action_id}:{len(rows)}")
            continue
        row = rows[0]
        fields = {name: str(value.value) for name, value in row.fields.items()}
        if row.status not in (
            ActionExecutionStatus.VERIFIED,
            ActionExecutionStatus.PARTIAL,
        ):
            found.append(f"e5_readback_status:{action_id}:{row.status.value}")
        elif not fields or not set(fields.values()) <= _ADMISSIBLE_FIELDS:
            found.append(f"e5_readback_fields:{action_id}")
        elif "verified" not in fields.values():
            found.append(f"e5_readback_nothing_verified:{action_id}")
        elif set(_ENDPOINT_FIELDS) & set(fields) and any(
            fields.get(name) != "verified" for name in _ENDPOINT_FIELDS
        ):
            found.append(f"e5_readback_address_unverified:{action_id}")
    return found


def _texts(value: object) -> list[str]:
    """Read a recorded list of names without trusting its element types."""
    return sorted(str(item) for item in value) if isinstance(value, list) else []


def _forwarding_findings(label: str, rows: object, ports: Sequence[str]) -> list[str]:
    """Require every granted port to appear exactly once, forwarding."""
    states = {
        str(item.get("interface")): (item.get("matches"), str(item.get("state")))
        for item in (rows if isinstance(rows, list) else [])
        if isinstance(item, Mapping)
    }
    found: list[str] = []
    for port in ports:
        matches, state = states.get(port, (0, ""))
        if matches != 1 or state.upper() not in FORWARDING_STATES:
            found.append(f"{label}_port_not_forwarding:{port}:{state or 'absent'}")
    return found


#: The facts a sample must carry before any of its rows mean anything. They
#: are the admission rule's own dimensions, re-read from the record rather
#: than taken from the verdict it recorded next to them.
_AUTHORITATIVE_SAMPLE = {
    "executed": True,
    "fresh_output_observed": True,
    "output_complete": True,
    "vlan_present": True,
    "sample_budget_exhausted": False,
    "deadline_reached": False,
}


def readiness_findings(grant: ColdHttpGrant, record: ServiceRunRecord) -> list[str]:
    """Require one timely, authoritative FWD sample of exactly the granted group.

    The recorded `admitted` flag is necessary and never sufficient: the sample
    itself must have executed fresh and complete, on the granted switch with
    a confirmed unique identity, for the granted VLAN and ports, inside its
    window, and its deciding sample must show every granted port forwarding.
    """
    rows = record.operational_readiness
    if len(rows) != 1 or not isinstance(rows[0], Mapping):
        return [f"readiness_groups:{len(rows)}"]
    row = rows[0]
    found: list[str] = []
    ports = sorted(item.switch_port for item in grant.endpoints)
    if row.get("status") != READINESS_ADMITTED:
        found.append(f"readiness_not_admitted:{row.get('status')}")
    if row.get("dimension") != "NONE":
        found.append(f"readiness_dimension:{row.get('dimension')}")
    if row.get("vlan_id") != grant.vlan_id:
        found.append("readiness_vlan_mismatch")
    if _texts(row.get("requested_interfaces")) != ports:
        found.append("readiness_interfaces_differ_from_grant")
    sample = row.get("sample")
    if not isinstance(sample, Mapping) or not sample:
        return [*found, "readiness_sample_absent"]
    if sample.get("switch") != grant.switch:
        found.append("readiness_switch_mismatch")
    if sample.get("vlan_id") != grant.vlan_id:
        found.append("readiness_sample_vlan_mismatch")
    if _texts(sample.get("requested_interfaces")) != ports:
        found.append("readiness_sample_interfaces_differ_from_grant")
    if sample.get("observed_device_name") != grant.switch:
        found.append("readiness_observed_device_is_not_the_switch")
    if sample.get("device_identity_provenance") != CONFIRMED_UNIQUE:
        found.append("readiness_device_identity_not_confirmed_unique")
    if sample.get("sample_after_deadline") is not False:
        found.append("readiness_sample_after_deadline")
    for key, expected in _AUTHORITATIVE_SAMPLE.items():
        if sample.get(key) is not expected:
            found.append(f"readiness_{key}_not_{str(expected).lower()}")
    found.extend(_forwarding_findings("readiness", sample.get("rows"), ports))
    history = sample.get("sample_history")
    if not isinstance(history, list) or not history:
        return [*found, "readiness_history_absent"]
    if len(history) != sample.get("samples"):
        found.append("readiness_history_incomplete")
    deciding = history[-1] if isinstance(history[-1], Mapping) else {}
    for key, expected in _AUTHORITATIVE_SAMPLE.items():
        if deciding.get(key) is not expected:
            found.append(f"readiness_deciding_{key}_not_{str(expected).lower()}")
    if deciding.get("observed_device_name") != grant.switch:
        found.append("readiness_deciding_device_is_not_the_switch")
    found.extend(
        _forwarding_findings("readiness_deciding", deciding.get("rows"), ports)
    )
    dependents = {
        str(item.get("expectation_id")): item.get("admitted")
        for item in (row.get("dependents") or [])
        if isinstance(item, Mapping)
    }
    if not dependents or not all(value is True for value in dependents.values()):
        found.append("readiness_dependents_not_all_admitted")
    return found


def ordering_findings(
    grant: ColdHttpGrant,
    expectation_by_client: Mapping[str, str],
    entries: Sequence[OperationEntry],
) -> list[str]:
    """Check the dispatch order the acceptance requires, from the ledger alone.

    It reads purposes and positions, never script text. The readiness purpose
    is the product's own forwarding observation; if it never dispatched before
    a client's first request, no admitted FWD existed at that moment, however
    the page answered afterwards.
    """
    dispatched = [(index, item) for index, item in enumerate(entries) if item.seq > 0]
    found: list[str] = []
    unlabelled = sorted(
        {
            item.purpose or "<none>"
            for _, item in dispatched
            if item.purpose not in _KNOWN_PURPOSES
            and not item.purpose.startswith((E6_VERIFY_PREFIX, OWNED_RELEASE_PREFIX))
        }
    )
    if unlabelled:
        found.append("unlabelled_dispatches:" + ",".join(unlabelled))

    def positions(purpose: str) -> list[int]:
        return [index for index, item in dispatched if item.purpose == purpose]

    e5_verify = positions(PURPOSE_E5_VERIFY)
    readiness = positions(PURPOSE_READINESS)
    e6_apply = positions(PURPOSE_E6_APPLY)
    if readiness and e5_verify and min(readiness) < max(e5_verify):
        # A forwarding sample taken before the E5 readback finished describes
        # ports that may not yet carry the granted VLAN; it admits nothing.
        found.append("forwarding_observed_before_e5_readback_finished")
    windows: list[tuple[int, str, list[int], list[int]]] = []
    for client in grant.clients:
        expectation = expectation_by_client.get(client.name, "")
        if not expectation:
            found.append(f"no_request_expectation:{client.name}")
            continue
        requests = positions(E6_VERIFY_PREFIX + expectation)
        releases = positions(OWNED_RELEASE_PREFIX + expectation)
        if not requests:
            found.append(f"no_request_dispatched:{client.name}")
            continue
        windows.append((requests[0], client.name, requests, releases))
    # The product tests one client after the other, in its own order. Which
    # client goes first is the product's choice; that the first one is
    # finished and released before the second one starts is the requirement.
    previous_end: int | None = None
    for first, name, requests, releases in sorted(windows):
        if not e5_verify or max(e5_verify) > first:
            found.append(f"request_not_after_e5_readback:{name}")
        if not readiness or max(readiness) > first:
            found.append(f"request_without_prior_forwarding_observation:{name}")
        if not e6_apply or max(e6_apply) > first:
            found.append(f"request_before_e6_apply:{name}")
        if previous_end is not None and first < previous_end:
            found.append(f"request_before_previous_client_finished:{name}")
        if len(releases) != 1:
            found.append(f"owned_release_dispatches:{name}:{len(releases)}")
        elif releases[0] < requests[-1]:
            found.append(f"release_before_last_request_dispatch:{name}")
        previous_end = max([*requests, *releases])
    return found


def _start_answer_facts(answer: str) -> tuple[str | None, dict[str, Any]]:
    """Read the raw start answer's own before-content, when it has one."""
    try:
        payload = json.loads(answer)
    except (TypeError, ValueError):
        return None, {}
    if not isinstance(payload, dict):
        return None, {}
    before = payload.get("content_before")
    return (before[:MAX_ANSWER_CHARS] if isinstance(before, str) else None), payload


def _answer_payload(answer: str) -> dict[str, Any]:
    try:
        payload = json.loads(answer)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def ledger_release_outcome(
    requests: Sequence[OperationEntry],
    releases: Sequence[OperationEntry],
    refused_releases: Sequence[OperationEntry],
    start_answer: str,
    release_answer: str,
) -> str:
    """Say what the ledger and the raw answers establish about one release.

    Used when the product never returned a row for the client, as after an
    interruption. It mirrors the product's own finalization vocabulary and
    never infers a deletion the answer did not report.
    """
    if not requests:
        return ""
    if releases:
        payload = _answer_payload(release_answer)
        if not payload:
            return "release_unanswered"
        if payload.get("deleted") is True:
            return "released"
        if _answer_payload(start_answer).get("owned") is True:
            return "release_unverified"
        return "ownership_unknown"
    if refused_releases:
        return "release_refused"
    return "release_not_dispatched"


def client_outcome(
    grant: ColdHttpGrant,
    client_index: int,
    expectation_id: str,
    record: ServiceRunRecord | None,
    entries: Sequence[OperationEntry],
    answers: Mapping[str, Sequence[str]],
    request_order: int | None = None,
) -> ClientAcceptance:
    """Judge one client's first request from the ledger, the answers and the row."""
    client = grant.clients[client_index]
    requests = [
        item
        for item in entries
        if item.seq > 0 and item.purpose == E6_VERIFY_PREFIX + expectation_id
    ]
    releases = [
        item
        for item in entries
        if item.seq > 0 and item.purpose == OWNED_RELEASE_PREFIX + expectation_id
    ]
    start_answers = answers.get(E6_VERIFY_PREFIX + expectation_id) or ()
    release_answers = answers.get(OWNED_RELEASE_PREFIX + expectation_id) or ()
    start_answer = start_answers[0] if start_answers else ""
    content_before, start_payload = _start_answer_facts(start_answer)
    outcome = ClientAcceptance(
        client=client.name,
        expectation_id=expectation_id,
        switch_port=client.switch_port,
        first_dispatch_seq=requests[0].seq if requests else None,
        request_order=request_order,
        dispatches=len(requests),
        start_answer=start_answer,
        content_before=content_before,
        release_answer=release_answers[0] if release_answers else "",
        release_dispatches=len(releases),
    )
    findings: list[str] = []
    row = None
    if record is not None and record.service_result is not None:
        row = next(
            (
                item
                for item in record.service_result.verification_results
                if item.expectation_id == expectation_id
            ),
            None,
        )
    if row is None:
        refused_releases = [
            item
            for item in entries
            if item.refused and item.purpose == OWNED_RELEASE_PREFIX + expectation_id
        ]
        outcome.release_outcome = ledger_release_outcome(
            requests,
            releases,
            refused_releases,
            start_answer,
            outcome.release_answer,
        )
        outcome.findings = ["no_verification_row"]
        if requests and outcome.release_outcome != "released":
            outcome.findings.append("client_ownership_unresolved")
        return outcome
    observed = row.observed
    go_result = observed.get("go_result")
    performed = [step for step in row.trace if step.performed]
    inspections = [step for step in performed if step.label == "inspect"]
    outcome.selected_url = str(observed.get("selected_url") or "")
    outcome.selected_url_is_input = observed.get("selected_url_is_input") is True
    outcome.go_result = go_result if isinstance(go_result, bool) else None
    outcome.go_result_type = str(observed.get("go_result_type") or "")
    outcome.owner_device = str(observed.get("owner_device") or "")
    outcome.owner_read = observed.get("owner_read") is True
    outcome.client_mode = str(observed.get("client_mode") or "")
    outcome.status = row.status.value
    outcome.observation = row.observation.value
    outcome.cause = row.cause
    outcome.inspections_performed = len(inspections)
    outcome.marker_observations = [step.marker_present for step in inspections]
    outcome.trace = [step.model_dump(mode="json") for step in row.trace]
    outcome.release_outcome = str(observed.get("released") or "")

    if row.status is not ActionExecutionStatus.VERIFIED:
        findings.append(f"row_status:{row.status.value}")
    if row.observation is not ObservationFact.OBSERVED:
        # A timeout stays what it is: nothing was observed in the window. It
        # is inconclusive, and it is never evidence that the listener refused.
        findings.append(f"row_observation:{row.observation.value}:{row.cause}")
    if outcome.selected_url != grant.url or not outcome.selected_url_is_input:
        findings.append("selected_url_is_not_the_granted_input")
    if outcome.go_result is not True or outcome.go_result_type != "boolean":
        findings.append("native_go_result_not_boolean_true")
    if outcome.owner_device != client.name or not outcome.owner_read:
        findings.append("owner_not_observed_as_this_client")
    if outcome.client_mode != "http":
        findings.append("client_mode_not_http")
    if observed.get("marker") != grant.marker:
        findings.append("row_marker_is_not_the_attempt_marker")
    if not performed or performed[0].label != "start":
        findings.append("first_dispatch_is_not_the_start")
    if sum(1 for step in performed if step.label == "start") != 1:
        findings.append("not_exactly_one_start")
    if len(requests) != len(performed):
        # Every performed step is one dispatch under this request's purpose.
        # A trace longer or shorter than the ledger is a trace nobody made.
        findings.append("row_trace_disagrees_with_ledger")
    if not inspections or not inspections[-1].marker_present:
        findings.append("no_fresh_marker_observation")
    elif not inspections[-1].content_changed:
        findings.append("deciding_inspection_not_fresh_content")
    if content_before is None:
        findings.append("before_content_not_observed")
    elif grant.marker in content_before:
        findings.append("marker_present_before_request")
    if start_payload and start_payload.get("go_result") is not go_result:
        findings.append("row_go_result_contradicts_start_answer")
    if start_payload and start_payload.get("owner_device") != outcome.owner_device:
        findings.append("row_owner_contradicts_start_answer")
    if outcome.release_outcome != "released" or len(releases) != 1:
        findings.append(f"release:{outcome.release_outcome or 'absent'}")
    if any(item.startswith("client_ownership_unresolved:") for item in row.limitations):
        findings.append("client_ownership_unresolved")
    outcome.findings = findings
    outcome.accepted = not findings
    return outcome


@dataclass
class AcceptanceEvaluation:
    """Everything the verdict was decided from, and the verdict."""

    clients: list[ClientAcceptance] = field(default_factory=list)
    ordering: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        """Accept only an attempt against which nothing was found."""
        return not self.reasons


def evaluate_attempt(
    grant: ColdHttpGrant,
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
    """Decide HTTP acceptance from every independent source at once.

    `stop_facts` carries what the coordinator itself observed and that no
    product source can overrule: a refused or halted dispatch, a lost claim, a
    process that changed, a mailbox left undrained, an envelope that could not
    be persisted. Any of them is a reason; none of them is weighed away.
    """
    evaluation = AcceptanceEvaluation()
    reasons = evaluation.reasons
    reasons.extend(stop_facts)
    reasons.extend(record_problems)
    expectation_by_client: dict[str, str] = {}
    if closure is not None:
        expectation_by_client = {
            item.client_device_name: item.expectation_id
            for item in closure.checks
            if item.kind == "http_fetch"
        }
    if record is None or summary is None:
        reasons.append("durable_record_unavailable")
    else:
        reasons.extend(reload_differences(record, summary, expected_path=record_path))
        reasons.extend(record_identity_findings(grant, record, closure))
        reasons.extend(product_outcome_findings(record))
        reasons.extend(readiness_findings(grant, record))
    evaluation.ordering = ordering_findings(grant, expectation_by_client, entries)
    reasons.extend(evaluation.ordering)
    firsts = sorted(
        (item.seq, item.purpose.removeprefix(E6_VERIFY_PREFIX))
        for item in entries
        if item.seq > 0 and item.purpose.startswith(E6_VERIFY_PREFIX)
    )
    order: dict[str, int] = {}
    for _seq, expectation in firsts:
        if expectation in expectation_by_client.values() and expectation not in order:
            order[expectation] = len(order) + 1
    for index, client in enumerate(grant.clients):
        expectation = expectation_by_client.get(client.name, "")
        outcome = client_outcome(
            grant,
            index,
            expectation,
            record,
            entries,
            answers,
            request_order=order.get(expectation),
        )
        evaluation.clients.append(outcome)
        reasons.extend(f"{client.name}:{item}" for item in outcome.findings)
    return evaluation
