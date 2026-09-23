"""The cold-HTTP acceptance route over the real product composition.

Every attempt here runs the production coordinator, the shared session
composition, the unchanged product use case, both runtimes, the readiness loop,
the operation ledger and the real stores. Only the terminal, the clock, git,
the process table and the campaign scope are controlled (see the harness).
Each test states the requirement it pins in the change brief's terms.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from cold_http_acceptance_harness import (
    ATTEMPT,
    INCARNATION,
    NEVER,
    PC1,
    PC2,
    SERVER_IP,
    SHA,
    TREE,
    ColdHttpTerminal,
    FakeClock,
    FakeLifecycle,
    acceptance_manifest,
    build_harness,
    paired_process,
    published_checkout,
)
from mcp.server.fastmcp import FastMCP
from service_entry_fixture import (
    DEPLOYMENT_ID,
    IsolationPreflight,
    deployed_topology,
    intent_json,
)
from service_product_simulation import simulated_spanning_tree_output

from packet_tracer_mcp.adapters.mcp import service_tools
from packet_tracer_mcp.application.ports.service_qualification import OpenedTransport
from packet_tracer_mcp.application.ports.service_run_record import (
    RunRecordPersistenceError,
)
from packet_tracer_mcp.application.use_cases import service_access_readiness_gate
from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    AcceptanceSubject,
    CampaignOutcome,
    ColdHttpProposal,
)
from packet_tracer_mcp.domain.enterprise.models.service_entry import (
    ServiceEntryRefusal,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    RefusalKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
    SourceTreeIdentity,
)
from packet_tracer_mcp.domain.enterprise.services.service_access_readiness import (
    ReadinessDependentResult,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationState,
)
from packet_tracer_mcp.infrastructure.execution.product_channel import (
    FixedChannelProductTransport,
)
from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    LOCK_NAME,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

_EFFECT_KINDS = {"send", "e6_apply", "http_start", "http_release"}


def _subjects(result) -> set[AcceptanceSubject]:
    return {item.subject for item in result.envelope.admission}


def _effects(harness) -> list[str]:
    return [kind for kind in harness.product_dispatches() if kind in _EFFECT_KINDS]


def _stored_records(harness) -> list[Path]:
    root = harness.record_store.base_dir / DEPLOYMENT_ID
    return sorted(root.glob("*.json")) if root.exists() else []


# -- C1/C4: grant and channel, before anything --------------------------------


def test_explicit_execution_is_required_and_nothing_is_read(tmp_path: Path):
    """Without the flag nothing is parsed, claimed, opened or written."""
    harness = build_harness(tmp_path)

    result = harness.run(execute=False)

    assert result.exit_code == 2
    assert result.envelope.campaign_outcome is CampaignOutcome.REFUSED
    assert harness.opened_channels == []
    assert harness.terminal.log == []
    assert not harness.coordinator.scope.exists()


@pytest.mark.parametrize(
    ("document", "subject"),
    [
        (None, AcceptanceSubject.GRANT),
        ({"attempt_id": "not-hex"}, AcceptanceSubject.ATTEMPT),
        ({"channel": "http"}, AcceptanceSubject.CHANNEL),
        ({"max_operations": 1016}, AcceptanceSubject.BUDGET),
        ({"max_seconds": 600}, AcceptanceSubject.BUDGET),
        ({"marker": "COLD_HTTP_other"}, AcceptanceSubject.MARKER),
        ({"url": "http://www.lab.example/"}, AcceptanceSubject.URL),
        ({"exclusive_disposable_lab": False}, AcceptanceSubject.LABORATORY),
        ({"local_fence_limitation_accepted": False}, AcceptanceSubject.LABORATORY),
        ({"sha": "HEAD"}, AcceptanceSubject.SOURCE),
        ({"clients": []}, AcceptanceSubject.SELECTION),
    ],
)
def test_an_invalid_or_missing_grant_refuses_before_any_contact(
    tmp_path: Path, document, subject
):
    """C1: every grant defect refuses before a claim, a channel or a write."""
    harness = build_harness(tmp_path)
    grant = None if document is None else harness.grant(**document)

    result = harness.run(grant=grant)

    assert result.envelope.campaign_outcome is CampaignOutcome.REFUSED
    assert subject in _subjects(result)
    assert harness.opened_channels == []
    assert harness.terminal.log == []
    assert not harness.coordinator.scope.exists()
    assert not harness.envelope_store.base_dir.exists()


def test_an_intent_other_than_the_granted_input_refuses(tmp_path: Path):
    """C1: the grant binds the exact product input by digest."""
    harness = build_harness(tmp_path)

    result = harness.run(intent_json=harness.intent_json + " ")

    assert _subjects(result) == {AcceptanceSubject.INTENT}
    assert harness.terminal.log == []


def test_an_unavailable_granted_channel_refuses_without_fallback(tmp_path: Path):
    """C4: a stale heartbeat refuses; no other channel is tried."""
    harness = build_harness(tmp_path)
    harness.terminal.alive = False

    result = harness.run()

    assert harness.opened_channels == ["file"]
    assert harness.terminal.log == []
    assert _subjects(result) == {AcceptanceSubject.CHANNEL}
    assert result.envelope.admission[0].kind is RefusalKind.UNOBSERVABLE
    assert _stored_records(harness) == []
    # The attempt identity was reserved, so its refusal is recorded durably.
    stored = harness.envelope_store.load(ATTEMPT)
    assert stored.completed_at is not None
    assert stored.campaign_outcome is CampaignOutcome.REFUSED


def test_a_substituted_channel_refuses_before_any_dispatch(tmp_path: Path):
    """C4: an opened channel that is not the granted one is never used."""
    harness = build_harness(tmp_path)
    terminal = harness.terminal
    harness.boundaries = replace(
        harness.boundaries,
        open_channel=lambda channel: OpenedTransport("http", terminal, True, "live"),
    )

    result = harness.run()

    assert terminal.log == []
    assert _subjects(result) == {AcceptanceSubject.CHANNEL}
    assert result.envelope.admission[0].kind is RefusalKind.MISMATCH


def test_a_product_call_naming_another_channel_raises_before_dispatch():
    """C4: the fixed channel never routes a call it was not bound for."""
    dispatched: list[str] = []

    class Recording:
        def send(self, js_code: str) -> bool:
            dispatched.append(js_code)
            return True

        def send_and_wait(self, js_code: str, timeout: float):
            dispatched.append(js_code)
            return "{}"

        def dispatch_and_wait(self, js_code: str, timeout: float):
            dispatched.append(js_code)
            raise AssertionError("never reached")

    fixed = FixedChannelProductTransport("file", Recording())

    for call in (
        lambda: fixed.send_and_wait("x", 1.0, "http"),
        lambda: fixed.dispatch_and_wait("x", 1.0, None),
        lambda: fixed.send_payload("x", "http"),
        lambda: fixed.query_inventory(["A"], "http"),
        lambda: fixed.observe_environment("http"),
    ):
        with pytest.raises(RuntimeError, match="not the bound channel"):
            call()
    assert dispatched == []
    assert fixed.send_and_wait("x", 1.0, "file") == "{}"
    assert dispatched == ["try{x}catch(__pterr){reportResult('PT_ERROR: '+__pterr);}"]


# -- C2: source, process, isolation and manifest -------------------------------


@pytest.mark.parametrize(
    "checkout",
    [
        {"head": "f" * 40},
        {"tree": "e" * 40},
        {"clean": False},
        {"upstream_head": "d" * 40},
        {"error": "git unavailable", "head": ""},
    ],
)
def test_a_source_mismatch_refuses_before_the_claim(tmp_path: Path, checkout):
    """C2: the checkout must be the granted clean, published SHA and tree."""
    harness = build_harness(tmp_path, repository=lambda: published_checkout(**checkout))

    result = harness.run()

    assert _subjects(result) == {AcceptanceSubject.REPOSITORY}
    assert harness.terminal.log == []
    assert not harness.coordinator.scope.exists()


@pytest.mark.parametrize(
    ("process", "subject"),
    [
        ({"process_incarnation": "2026-09-22T09:00:01.0000000-05:00"}, "process"),
        ({"process_incarnation": ""}, "process"),
        ({"process_id": 4243}, "process"),
        ({"product_version": "9.0.0.0810", "file_version": ""}, "process"),
        ({"mailbox_entries": ("req_1.js",)}, "mailbox"),
        ({"error": "packet_tracer_process_count:2"}, "process"),
    ],
)
def test_a_process_mismatch_refuses_before_contact(tmp_path: Path, process, subject):
    """C2: one exact incarnation, the granted build and a quiet mailbox."""
    harness = build_harness(tmp_path)
    harness.lifecycle.observations = [paired_process(**process)]

    result = harness.run()

    assert AcceptanceSubject(subject) in _subjects(result)
    assert harness.opened_channels == []
    assert harness.terminal.log == []


@pytest.mark.parametrize(
    "state",
    [ImportIsolationState.TEST_PROCESS, ImportIsolationState.FOREIGN_TREE],
)
def test_a_pytest_or_foreign_process_refuses(tmp_path: Path, state):
    """C2: isolation is decided in the process that would execute."""
    harness = build_harness(tmp_path, import_preflight=IsolationPreflight(state))

    result = harness.run()

    assert _subjects(result) == {AcceptanceSubject.ISOLATION}
    assert harness.terminal.log == []


@pytest.mark.parametrize(
    "grant",
    [{"manifest_hash": "a" * 64}, {"physical_topology_hash": "b" * 64}],
)
def test_a_manifest_other_than_the_granted_one_refuses(tmp_path: Path, grant):
    """C2: the persisted manifest must be exactly the granted identity."""
    harness = build_harness(tmp_path)

    result = harness.run(grant=harness.grant(**grant))

    assert _subjects(result) == {AcceptanceSubject.MANIFEST}
    assert harness.terminal.log == []


# -- C3: one attempt, fresh history ---------------------------------------------


def test_an_attempt_identity_is_spent_once_and_never_reset(tmp_path: Path):
    """C3: a second run of the same attempt refuses at the permanent reservation."""
    harness = build_harness(tmp_path)
    first = harness.run()
    dispatched = len(harness.terminal.log)

    second = harness.run()

    assert first.envelope.http_accepted is True
    assert _subjects(second) == {AcceptanceSubject.CAMPAIGN}
    assert "campaign_attempt_already_reserved" in second.envelope.primary_failure
    assert len(harness.terminal.log) == dispatched


def test_a_held_campaign_lock_refuses_and_is_left_as_found(tmp_path: Path):
    """C3: no recovery by age; another writer's lock is never removed."""
    harness = build_harness(tmp_path)
    scope = harness.coordinator.scope
    scope.mkdir(parents=True)
    foreign = scope / LOCK_NAME
    foreign.write_text('{"holder": "other", "attempt_id": "x"}', encoding="utf-8")

    result = harness.run()

    assert _subjects(result) == {AcceptanceSubject.CAMPAIGN}
    assert (
        foreign.read_text(encoding="utf-8") == '{"holder": "other", "attempt_id": "x"}'
    )
    assert harness.terminal.log == []


@pytest.mark.parametrize("status", ["verified", "refused", "unknown"])
def test_any_prior_run_of_the_deployment_refuses_before_a_product_record(
    tmp_path: Path, status: str
):
    """C3: history of any status is history; nothing is deleted."""
    harness = build_harness(tmp_path)
    earlier = ServiceRunRecord(
        run_id="earlier",
        created_at="2026-09-01T00:00:00Z",
        deployment_id=DEPLOYMENT_ID,
        status=status,
    )
    harness.record_store.begin(earlier)

    result = harness.run()

    assert _subjects(result) == {AcceptanceSubject.HISTORY}
    assert [path.name for path in _stored_records(harness)] == ["earlier.json"]
    assert harness.terminal.log == []


def test_unreadable_history_is_not_empty_history(tmp_path: Path):
    """C3: a history that cannot be listed refuses as unobservable."""
    harness = build_harness(tmp_path)
    harness.record_store.base_dir.mkdir(parents=True)
    (harness.record_store.base_dir / DEPLOYMENT_ID).write_text("x", encoding="utf-8")

    result = harness.run()

    assert _subjects(result) == {AcceptanceSubject.HISTORY}
    assert result.envelope.admission[0].kind is RefusalKind.UNOBSERVABLE


# -- C5: the exact closure, before E1 -------------------------------------------


def test_a_source_identity_without_a_tree_refuses_before_effects(tmp_path: Path):
    """C5/C9: an absent tree cannot satisfy exact provenance, even pre-effect."""
    harness = build_harness(tmp_path)
    harness.source = SourceTreeIdentity(sha=SHA, tree="", dirty=False)

    result = harness.run()

    envelope = result.envelope
    assert "source_tree_absent" in envelope.closure_findings
    assert envelope.product["refusal_code"] == (
        ServiceEntryRefusal.EFFECT_SCOPE_NOT_ADMITTED.value
    )
    assert _effects(harness) == []
    assert envelope.campaign_outcome is CampaignOutcome.REFUSED
    assert envelope.http_accepted is False


def test_a_closure_the_grant_does_not_name_refuses_before_effects(tmp_path: Path):
    """C5: DNS added to the intent changes the closure; nothing is dispatched."""
    harness = build_harness(tmp_path)
    dns_and_http = intent_json()
    grant = harness.grant(
        intent_sha256=hashlib.sha256(dns_and_http.encode("utf-8")).hexdigest()
    )

    result = harness.run(grant=grant, intent_json=dns_and_http)

    findings = result.envelope.closure_findings
    assert any(item.startswith("unexpected_checks:") for item in findings)
    assert _effects(harness) == []
    assert result.envelope.campaign_outcome is CampaignOutcome.REFUSED


def test_a_dirty_executing_tree_refuses_before_effects(tmp_path: Path):
    """C5: the product's own source observation must be clean and granted."""
    harness = build_harness(tmp_path)
    harness.source = SourceTreeIdentity(sha=SHA, tree=TREE, dirty=True)

    result = harness.run()

    assert "source_tree_dirty" in result.envelope.closure_findings
    assert _effects(harness) == []


# -- C8: readiness timing and the first requests --------------------------------


def _positions(harness, wanted: str) -> list[int]:
    return [
        index
        for index, kind in enumerate(harness.product_dispatches())
        if kind == wanted
    ]


def test_forwarding_at_the_first_sample_is_accepted(tmp_path: Path):
    """C8/C10: the positive path, judged from every independent source."""
    harness = build_harness(tmp_path)

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons
    assert result.exit_code == 0
    assert envelope.campaign_outcome is CampaignOutcome.COMPLETED
    assert envelope.ordering == []
    assert envelope.primary_failure == ""
    assert [item.request_order for item in envelope.clients] in ([1, 2], [2, 1])
    for client in envelope.clients:
        assert client.accepted, client.findings
        assert client.selected_url == f"http://{SERVER_IP}/"
        assert client.go_result is True
        assert client.go_result_type == "boolean"
        assert client.owner_device == client.client
        assert client.client_mode == "http"
        assert client.content_before == ""
        assert client.release_outcome == "released"
        assert client.marker_observations[-1] is True
    samples = envelope.readiness[0]["sample"]["sample_history"]
    assert {row["state"] for row in samples[-1]["rows"]} == {"FWD"}


@pytest.mark.parametrize("after", [4.0, 26.0])
def test_delayed_forwarding_is_accepted_only_after_it_was_observed(
    tmp_path: Path, after: float
):
    """C8: LIS samples first, then FWD; every request follows the FWD sample."""
    harness = build_harness(tmp_path)
    harness.terminal.forwarding_after = after

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons
    history = envelope.readiness[0]["sample"]["sample_history"]
    states = [{row["state"] for row in sample["rows"]} for sample in history]
    assert states[0] == {"LIS"}
    assert states[-1] == {"FWD"}
    assert len(history) == int(after) + 1
    assert min(_positions(harness, "http_start")) > max(
        _positions(harness, "readiness")
    )


def test_persistent_listening_dispatches_no_request(tmp_path: Path):
    """C8: LIS for the whole window admits nothing and starts no client."""
    harness = build_harness(tmp_path)
    harness.terminal.forwarding_after = NEVER

    result = harness.run()

    envelope = result.envelope
    assert "http_start" not in harness.product_dispatches()
    assert envelope.http_accepted is False
    assert any("readiness_not_admitted" in item for item in envelope.reasons)
    assert all(item.dispatches == 0 for item in envelope.clients)


def test_forwarding_evidence_that_arrives_late_dispatches_no_request(
    tmp_path: Path,
):
    """C8: a FWD answer after the window is late evidence and grants nothing."""
    harness = build_harness(tmp_path)
    terminal = harness.terminal
    terminal.latency = lambda script: 29.0 if "owner_name:owner" in script else 0.0
    terminal.forwarding_after = 0.0

    result = harness.run()

    assert "http_start" not in harness.product_dispatches()
    assert result.envelope.http_accepted is False
    row = result.envelope.readiness[0]
    assert row["status"] != "admitted"


def _duplicated_row_output() -> str:
    lines = simulated_spanning_tree_output("FWD").splitlines()
    row = next(line for line in lines if line.startswith("Fa1/1"))
    lines.insert(lines.index(row), row)
    return "\n".join(lines)


@pytest.mark.parametrize(
    "override",
    [
        {"owner_name": "HQ-OTHER-SWITCH"},
        {"output": _duplicated_row_output()},
    ],
    ids=["foreign_owner", "ambiguous_interface"],
)
def test_foreign_or_ambiguous_forwarding_evidence_dispatches_no_request(
    tmp_path: Path, override
):
    """C8: a sample of another device, or of a port twice, admits nothing."""
    harness = build_harness(tmp_path)
    harness.terminal.readiness_overrides = override

    result = harness.run()

    assert "http_start" not in harness.product_dispatches()
    assert result.envelope.http_accepted is False
    assert result.envelope.readiness[0]["status"] != "admitted"


def test_each_client_has_exactly_one_first_request_in_the_products_order(
    tmp_path: Path,
):
    """C8: one start per client, the first finished and released before the next."""
    harness = build_harness(tmp_path)

    result = harness.run()

    kinds = harness.product_dispatches()
    assert kinds.count("http_start") == 2
    first_start = kinds.index("http_start")
    first_release = kinds.index("http_release")
    second_start = kinds.index("http_start", first_start + 1)
    assert first_start < first_release < second_start
    assert "dns" not in " ".join(kinds)
    by_order = sorted(result.envelope.clients, key=lambda item: item.request_order)
    assert by_order[0].first_dispatch_seq < by_order[1].first_dispatch_seq
    for client in result.envelope.clients:
        assert json.loads(client.start_answer)["owner_device"] == client.client


def test_an_http_timeout_is_inconclusive_and_never_a_listener_refusal(
    tmp_path: Path,
):
    """C10: no content in the window is inconclusive; releases still happen."""
    harness = build_harness(tmp_path)
    harness.terminal.page_visible_after = NEVER

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is False
    assert envelope.campaign_outcome is CampaignOutcome.COMPLETED
    for client in envelope.clients:
        assert client.observation == "inconclusive"
        assert client.cause == "no_response_within_deadline"
        assert client.inspections_performed == 33
        assert client.release_outcome == "released"
    assert not any("refus" in item for item in envelope.reasons)


# -- C7: every owned release exit -----------------------------------------------


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (
            {"found": True, "deleted": False, "present": True, "error": "boom"},
            "release_unverified",
        ),
        (
            {"found": False, "deleted": False, "present": True, "error": ""},
            "release_unverified",
        ),
        (
            {"found": False, "deleted": False, "present": False, "error": ""},
            "release_unverified",
        ),
        (
            {"found": True, "deleted": True, "present": True, "error": ""},
            "release_unverified",
        ),
        ({"found": True}, "release_unverified"),
        ("not json", "release_failed"),
    ],
)
def test_every_unresolved_release_exit_withholds_acceptance(
    tmp_path: Path, answer, outcome
):
    """C7: only a confirmed deletion releases; every other exit is unresolved."""
    harness = build_harness(tmp_path)
    harness.terminal.release_answer = answer

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is False
    assert {client.release_outcome for client in envelope.clients} == {outcome}
    assert len(envelope.release_failures) == 2
    for client in envelope.clients:
        assert "client_ownership_unresolved" in client.findings
        assert client.release_dispatches == 1


@pytest.mark.parametrize(
    ("created", "outcome"),
    [(True, "released"), (False, "ownership_unknown")],
    ids=["created_then_answer_lost", "lost_before_evaluation"],
)
def test_an_undelivered_start_is_still_finalized_by_one_release(
    tmp_path: Path, created: bool, outcome: str
):
    """C7: a start with no answer may own a client; the release looks and says so."""
    harness = build_harness(tmp_path)
    harness.terminal.start_undelivered = True
    if not created:
        harness.terminal.start_overrides = {"owned": False}

    result = harness.run()

    envelope = result.envelope
    assert {client.release_outcome for client in envelope.clients} == {outcome}
    assert harness.product_dispatches().count("http_start") == 2
    assert harness.product_dispatches().count("http_release") == 2
    assert {client.observation for client in envelope.clients} == {"acceptance_unknown"}
    assert envelope.http_accepted is False


def test_a_client_that_was_never_created_needs_no_release_dispatch(tmp_path: Path):
    """C7: an explicit, coherent denial owns nothing and dispatches no release."""
    harness = build_harness(tmp_path)
    harness.terminal.start_overrides = {
        "owned": False,
        "started": False,
        "content_before": "",
        "go_result": None,
        "go_result_type": "absent",
        "https_mode": None,
        "https_mode_type": "absent",
        "owner_read": False,
        "owner_device": "",
    }

    result = harness.run()

    assert "http_release" not in harness.product_dispatches()
    for client in result.envelope.clients:
        assert client.release_outcome == "nothing_owned"
        assert client.release_dispatches == 0
    assert result.envelope.http_accepted is False


def test_an_early_release_leaves_ordinary_work_to_the_next_client(tmp_path: Path):
    """C7: PC1's release comes out of the reserve and PC2 then runs ordinarily."""
    harness = build_harness(tmp_path)

    result = harness.run()

    entries = [item for item in result.envelope.budget.entries if item.seq]
    phases = [(item.phase, item.purpose.split(":")[0]) for item in entries]
    first_release = phases.index(("protected_release", "owned_release"))
    assert phases[first_release + 1] == ("experiment", "e6_verify")
    assert result.envelope.budget.reserve_used == 2
    assert result.envelope.http_accepted is True


def _small_budget(harness, operations: int, seconds: int = 420):
    proposal = ColdHttpProposal(operations, seconds, 2, 40)
    harness.boundaries = replace(harness.boundaries, proposal=proposal)
    return harness.grant(max_operations=operations, max_seconds=seconds)


def test_after_ordinary_exhaustion_only_owned_releases_dispatch(tmp_path: Path):
    """C7: the reserve pays the owned releases and nothing else, without a spin."""
    harness = build_harness(tmp_path)
    harness.terminal.page_visible_after = NEVER
    grant = _small_budget(harness, 29)

    result = harness.run(grant=grant)

    envelope = result.envelope
    refused = [item for item in envelope.budget.entries if item.refused]
    assert {item.refused for item in refused} == {"operation_budget_exhausted"}
    assert len(refused) == 2
    kinds = harness.product_dispatches()
    exhausted_at = kinds.index("http_inspect") + 2
    assert kinds[exhausted_at:] == ["http_release", "http_release"]
    assert envelope.budget.reserve_used == 2
    assert envelope.campaign_outcome is CampaignOutcome.STOPPED
    assert envelope.primary_failure.startswith("ledger_refused:operation_budget")
    never_started = [item for item in envelope.clients if item.dispatches == 0]
    assert len(never_started) == 1
    assert never_started[0].release_outcome == "ownership_unknown"


def test_lost_authority_declines_every_later_dispatch_including_releases(
    tmp_path: Path,
):
    """C7: once the claim is gone, remaining reserve authorizes nothing."""
    harness = build_harness(tmp_path)
    lock = harness.coordinator.scope / LOCK_NAME

    def lose_claim(kind: str) -> None:
        if kind == "http_start" and lock.exists():
            lock.unlink()

    harness.terminal.on_dispatch = lose_claim

    result = harness.run()

    envelope = result.envelope
    kinds = harness.product_dispatches()
    assert kinds[-1] == "http_start"
    assert kinds.count("http_start") == 1
    assert envelope.primary_failure.startswith("authority_lost:")
    assert envelope.campaign_outcome is CampaignOutcome.STOPPED
    started = next(item for item in envelope.clients if item.dispatches)
    assert started.release_outcome == "release_failed"
    assert "client_ownership_unresolved" in started.findings
    assert envelope.campaign["release"] == "not_released"
    assert envelope.http_accepted is False


# -- C6: bounded, truthful execution at nested boundaries ------------------------


def _expire_after(harness, ordinary_seconds: int):
    return _small_budget(harness, 1015, ordinary_seconds + 40)


def test_expiry_during_the_e5_boot_wait_stops_without_a_spin(tmp_path: Path):
    """C6: the 90-second boot wait ends with the attempt's allowance."""
    harness = build_harness(tmp_path)
    harness.terminal.ios_ready_after = NEVER
    grant = _expire_after(harness, 20)

    result = harness.run(grant=grant)

    envelope = result.envelope
    kinds = harness.product_dispatches()
    assert kinds.count("ios_state") <= 20 / 0.25 + 1
    assert "e6_apply" not in kinds and "http_start" not in kinds
    assert len(harness.clock.sleeps) <= 20 / 0.25 + 1
    assert all(
        item.refused == "time_budget_exhausted"
        for item in envelope.budget.entries
        if item.refused
    )
    assert 1 <= envelope.budget.refused_calls <= 3
    assert envelope.campaign_outcome is CampaignOutcome.STOPPED
    assert envelope.http_accepted is False


def test_expiry_during_readiness_stops_the_episode_and_starts_no_client(
    tmp_path: Path,
):
    """C6: a refused sample call ends the episode; nothing polls a closed ledger."""
    harness = build_harness(tmp_path)
    harness.terminal.forwarding_after = NEVER
    grant = _expire_after(harness, 12)

    result = harness.run(grant=grant)

    envelope = result.envelope
    assert "http_start" not in harness.product_dispatches()
    sample = envelope.readiness[0]["sample"]
    assert sample["episode_end_reason"].startswith("channel_refused")
    assert envelope.budget.refused_calls == 1
    assert envelope.campaign_outcome is CampaignOutcome.STOPPED


def test_expiry_during_http_polling_keeps_the_protected_releases(tmp_path: Path):
    """C6/C7: the inspection is refused, the owned client is still released."""
    harness = build_harness(tmp_path)
    harness.terminal.page_visible_after = NEVER
    grant = _expire_after(harness, 5)

    result = harness.run(grant=grant)

    envelope = result.envelope
    kinds = harness.product_dispatches()
    assert kinds.count("http_start") == 1
    assert kinds[-2:] == ["http_inspect", "http_release"] or kinds[-1] == "http_release"
    assert kinds.count("http_release") == 2
    started = next(item for item in envelope.clients if item.dispatches)
    assert started.release_outcome == "released"
    assert envelope.budget.reserve_used == 2
    assert {item.refused for item in envelope.budget.entries if item.refused} == {
        "time_budget_exhausted"
    }
    assert envelope.budget.refused_calls <= 2
    assert envelope.campaign_outcome is CampaignOutcome.STOPPED


def test_every_bounded_wait_run_to_its_last_read_fits_the_frozen_ceiling(
    tmp_path: Path,
):
    """C6: the recomputed worst case, executed, stays inside 1,015 dispatches."""
    harness = build_harness(tmp_path)
    terminal = harness.terminal
    terminal.ios_ready_after = 90.0
    terminal.vlan_present_after = 5.0
    terminal.endpoint_ready_after = 30.0
    terminal.forwarding_after = 29.0
    terminal.page_visible_after = 8.0

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons
    kinds = harness.product_dispatches()
    readiness = [
        item
        for item in envelope.budget.entries
        if item.seq and item.purpose == "readiness"
    ]
    samples = envelope.readiness[0]["sample"]["samples"]
    per_sample = (len(readiness) - 1) // samples
    assert samples == 30
    assert kinds.count("ios_state") - samples == 361
    assert kinds.count("vlan") == 21
    assert kinds.count("endpoint") == 3 + 3 * 121
    assert kinds.count("http_inspect") == 2 * 33
    expected = 5 + (361 + 3 + 21 + 3 + 363) + (30 * per_sample + 1) + 3 + 70
    assert envelope.budget.used_operations == expected
    assert 30 * 6 + 1 == 181
    assert expected <= 1015


# -- C9/C10: persistence, postflight and durable reload ----------------------------


def test_the_durable_record_is_reloaded_and_cited_by_its_bytes(tmp_path: Path):
    """C9: the envelope cites the record by path and SHA-256 and never rewrites it."""
    harness = build_harness(tmp_path)

    result = harness.run()

    envelope = result.envelope
    path = Path(envelope.product["reloaded_record_path"])
    assert path == Path(envelope.product["record_path"])
    assert (
        envelope.product["record_sha256"]
        == hashlib.sha256(path.read_bytes()).hexdigest()
    )
    stored = harness.envelope_store.load(ATTEMPT)
    assert stored.http_accepted is True
    assert stored.completed_at is not None
    assert stored.product["record_sha256"] == envelope.product["record_sha256"]
    with pytest.raises(RunRecordPersistenceError, match="immutable"):
        harness.envelope_store.complete(stored)


def test_a_record_that_contradicts_the_public_result_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C9: the durable interpretation must be the one the product published."""
    harness = build_harness(tmp_path)
    original = ServiceRunRecordStore.load_evidence

    def tampered(self, deployment_id, run_id):
        record, path, digest = original(self, deployment_id, run_id)
        return record.model_copy(update={"releases": []}), path, digest

    monkeypatch.setattr(ServiceRunRecordStore, "load_evidence", tampered)

    result = harness.run()

    assert "record_differs_from_public_result:releases" in result.envelope.reasons
    assert result.envelope.http_accepted is False


def test_a_record_that_cannot_be_reloaded_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C9/C10: an unreadable record is a persistence failure, kept apart."""
    harness = build_harness(tmp_path)

    def unreadable(self, deployment_id, run_id):
        raise RunRecordPersistenceError("unreadable")

    monkeypatch.setattr(ServiceRunRecordStore, "load_evidence", unreadable)

    result = harness.run()

    envelope = result.envelope
    assert "record_reload_failed:RunRecordPersistenceError" in (
        envelope.persistence_failures
    )
    assert envelope.http_accepted is False


def test_a_product_persistence_failure_is_classified_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C10: the product's own persist error is a persistence failure."""
    harness = build_harness(tmp_path)

    def failing(self, record):
        raise RunRecordPersistenceError("disk full")

    monkeypatch.setattr(ServiceRunRecordStore, "complete", failing)

    result = harness.run()

    envelope = result.envelope
    assert any(
        item.startswith("product_record:") for item in envelope.persistence_failures
    )
    assert envelope.http_accepted is False


def test_an_envelope_that_cannot_be_completed_withdraws_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C10: a verdict that was not kept is not an acceptance."""
    harness = build_harness(tmp_path)
    store = harness.envelope_store

    def failing(envelope, **_checkpoint):
        raise RunRecordPersistenceError("read-only")

    monkeypatch.setattr(store, "complete", failing)

    result = harness.run()

    assert result.envelope.http_accepted is False
    assert "envelope_not_completed:RunRecordPersistenceError" in (
        result.envelope.persistence_failures
    )
    assert store.load(ATTEMPT).completed_at is None


@pytest.mark.parametrize(
    ("after", "finding"),
    [
        ({"process_incarnation": "2026-09-22T09:05:00.0000000-05:00"}, "changed"),
        ({"mailbox_entries": ("res_7.txt",)}, "mailbox:not_drained"),
        ({"error": "packet_tracer_process_count:0"}, "unobservable"),
    ],
)
def test_a_postflight_that_does_not_pair_is_a_postflight_failure(
    tmp_path: Path, after, finding
):
    """C10: the process read after the run must still be the granted one."""
    harness = build_harness(tmp_path)
    harness.lifecycle.observations = [paired_process(), paired_process(**after)]

    result = harness.run()

    envelope = result.envelope
    assert any(finding in item for item in envelope.postflight_failures)
    assert envelope.http_accepted is False
    assert envelope.primary_failure


def test_an_unresolved_fire_and_forget_send_withholds_acceptance(tmp_path: Path):
    """C10: a mailbox command the channel still holds is not a finished run."""
    harness = build_harness(tmp_path)
    harness.terminal.pending = True

    result = harness.run()

    assert "fire_and_forget_send_unresolved" in result.envelope.reasons
    assert result.envelope.http_accepted is False


# -- C8: the counterfactual gate bypass -------------------------------------------


def test_a_bypassed_readiness_gate_fails_the_ordering_oracle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C8: a page that answers while the ports stay LIS is not an acceptance."""
    harness = build_harness(tmp_path)
    harness.terminal.forwarding_after = NEVER

    def bypass(self, expectation_id):
        return ReadinessDependentResult(
            expectation_id=expectation_id,
            service_id="bypassed",
            kind="http_fetch",
            client_device_id="",
            host_device_id="",
            interfaces=(),
            admitted=True,
            cause="",
        )

    monkeypatch.setattr(
        service_access_readiness_gate.ServiceAccessReadinessGate, "decide", bypass
    )

    result = harness.run()

    envelope = result.envelope
    assert result.product_summary["status"] == "verified"
    assert harness.product_dispatches().count("http_start") == 2
    assert envelope.http_accepted is False
    for name in (PC1, PC2):
        assert (
            f"request_without_prior_forwarding_observation:{name}" in envelope.ordering
        )


# -- C11: parity with the public MCP route ------------------------------------------


_CLOCK_KEYS = {"elapsed_ms", "duration_ms", "run_id", "run_label", "record_path"}


def _without_clock(value):
    if isinstance(value, dict):
        return {
            key: _without_clock(item)
            for key, item in value.items()
            if key not in _CLOCK_KEYS
        }
    if isinstance(value, list):
        return [_without_clock(item) for item in value]
    return value


def test_the_mcp_route_and_the_acceptance_route_run_the_same_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C11: same composition, same dispatches, same result; only overhead differs."""
    harness = build_harness(tmp_path / "acceptance")
    accepted = harness.run()
    assert accepted.envelope.http_accepted is True

    manifest = acceptance_manifest()
    _topology, inventory = deployed_topology()
    clock = FakeClock()
    terminal = ColdHttpTerminal(tmp_path / "mcp", inventory, clock)
    store_root = tmp_path / "mcp" / "services"

    class Manifests:
        def latest_by_deployment_id(self, deployment_id):
            return manifest if deployment_id == DEPLOYMENT_ID else None

    monkeypatch.setattr(service_tools, "DeploymentManifestStore", Manifests)
    monkeypatch.setattr(
        service_tools,
        "ServiceRunRecordStore",
        lambda *args, **kwargs: ServiceRunRecordStore(store_root),
    )
    monkeypatch.setattr(
        service_tools, "ImportIsolationPreflight", lambda _root: IsolationPreflight()
    )
    fixed = FixedChannelProductTransport("file", terminal)
    mcp = FastMCP("parity")
    service_tools.register_service_tools(
        mcp,
        send_and_wait=fixed.send_and_wait,
        dispatch_and_wait=fixed.dispatch_and_wait,
        send_payload=fixed.send_payload,
        query_inventory=fixed.query_inventory,
        pick_channel=lambda: "file",
        observe_environment=fixed.observe_environment,
    )
    rendered = asyncio.run(
        mcp.call_tool(
            "pt_apply_enterprise_services",
            {
                "intent_json": harness.intent_json,
                "deployment_id": DEPLOYMENT_ID,
                "packet_tracer_version": harness.manifest.backend_version,
                "run_label": "",
            },
        )
    )
    public = json.loads(rendered[0][0].text)

    assert _without_clock(public) == _without_clock(
        json.loads(json.dumps(accepted.product_summary))
    )
    # The envelope adds no bridge operation: the terminal saw the same questions.
    assert [kind for _, kind in terminal.log] == harness.product_dispatches()
    assert re.fullmatch(r"[0-9a-f]{64}", accepted.envelope.product["record_sha256"])


def test_the_envelope_names_what_it_does_not_claim(tmp_path: Path):
    """C10: the limitations travel with every envelope, accepted or not."""
    harness = build_harness(tmp_path)

    result = harness.run()

    limitations = set(result.envelope.limitations)
    assert "effect_gate_is_local_and_not_an_in_band_receiver_fence" in limitations
    assert "client_release_is_not_workspace_restoration" in limitations
    assert "no_exactly_once_execution_claim" in limitations
    assert result.envelope.process_preflight["process_incarnation"] == INCARNATION


def test_the_lifecycle_reads_share_the_attempt_deadline(tmp_path: Path):
    """C6: each local observation is bounded by the attempt's own deadline."""
    harness = build_harness(tmp_path)
    lifecycle = FakeLifecycle(harness.clock, [paired_process()])
    harness.boundaries = replace(harness.boundaries, lifecycle=lifecycle.read)

    harness.run()

    assert len(lifecycle.deadlines) == 2
    assert all(deadline is not None for deadline in lifecycle.deadlines)
    start = 1000.0
    assert lifecycle.deadlines[0] <= start + 30.0 + 1e-6
    assert lifecycle.deadlines[1] <= start + 420.0 + 1e-6


# -- regressions from the independent review ------------------------------------------


def test_an_unreadable_verdict_still_completes_a_terminal_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C10: a judge that cannot read the evidence withholds acceptance durably."""
    from packet_tracer_mcp.application.use_cases import accept_cold_http

    harness = build_harness(tmp_path)

    def unreadable(*args, **kwargs):
        raise TypeError("'<' not supported between instances of 'int' and 'str'")

    monkeypatch.setattr(accept_cold_http, "evaluate_attempt", unreadable)

    result = harness.run()

    stored = harness.envelope_store.load(ATTEMPT)
    assert stored.completed_at is not None
    assert stored.http_accepted is False
    assert "evaluation_failed:TypeError" in stored.reasons
    assert result.envelope.campaign["release"] == "released"


def test_a_claim_that_cannot_be_released_withholds_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """C3/C10: the claim is released before the verdict and a failure counts."""
    harness = build_harness(tmp_path)
    monkeypatch.setattr(
        type(harness.coordinator),
        "release",
        lambda self, claim: ("campaign_claim:release_unverified",),
    )

    result = harness.run()

    envelope = result.envelope
    assert envelope.http_accepted is False
    assert envelope.campaign["release"] == "not_released"
    assert (
        "postflight:campaign_release:campaign_claim:release_unverified"
        in envelope.reasons
    )
    assert harness.envelope_store.load(ATTEMPT).http_accepted is False
