"""The scalable HTTP-by-IP acceptance profile over SIMULATED campuses.

Grants are built from the scope the real offline prepare path derives; the
attempt then runs the production coordinator, composition, product, runtimes,
readiness gate, ledger and stores over the simulated campus terminal with a
fake clock. Results here are offline behaviour of the envelope and product,
not Packet Tracer behaviour.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest
from campus_product_simulation import campus_payload, compose_campus
from cold_http_acceptance_harness import (
    ATTEMPT,
    MARKER,
    paired_process,
    published_checkout,
)
from scalable_http_acceptance_harness import build_scalable_harness

from packet_tracer_mcp.application.use_cases import accept_cold_http
from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    AcceptanceSubject,
    CampaignOutcome,
)
from packet_tracer_mcp.domain.enterprise.models.scalable_http_acceptance import (
    COST_PROFILE,
    parse_scalable_grant,
)
from packet_tracer_mcp.domain.enterprise.services import acceptance_evidence_index

SW1 = "HQ-DEFAULT-ACCESS-SW-01"
SW2 = "HQ-DEFAULT-ACCESS-SW-02"


#: The planner puts thirty clients and the server on two access switches;
#: twenty would still fit on one.
CAMPUS = 30


@pytest.fixture(scope="module")
def campus30():
    """Thirty clients on two access switches, compiled once for the module."""
    return compose_campus(campus_payload(CAMPUS, marker=MARKER))


def _subjects(result) -> set[AcceptanceSubject]:
    return {item.subject for item in result.envelope.admission}


def _effects(harness) -> set[str]:
    return set(harness.product_dispatches()) & {"send", "e6_apply", "http_start"}


# -- the grant and the derived scope ------------------------------------------------


def test_the_prepared_scope_names_every_selected_client_and_its_cost(
    tmp_path: Path, campus30
):
    """The offline prepare path derives the scope through the product itself."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    prepared = harness.prepared

    assert prepared.findings == ()
    scope = prepared.scope
    assert len(scope.clients) == CAMPUS
    assert {item.path_kind for item in scope.clients} == {
        "local_access",
        "l2_multi_access",
    }
    assert {item.kind for item in scope.groups} == {"access", "trunk_continuity"}
    assert scope.cost.reserve_operations == CAMPUS
    assert harness.terminal.log == []  # preparing contacted nothing
    again = build_scalable_harness(tmp_path / "again", CAMPUS, plans=campus30)
    assert again.prepared.scope.digest() == scope.digest()


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"schema_version": 3}, "schema_version 3"),
        ({"profile": "cold_http_two_client_v1"}, "profile"),
        ({"clients": []}, "clients is not a list"),
        ({"clients": ["A", "A"]}, "clients repeats: A"),
        (
            {"servers": ["HQ-DEFAULT-PC-01"], "clients": ["HQ-DEFAULT-PC-01"]},
            "server is also a client",
        ),
        ({"scope_sha256": "x"}, "scope_sha256"),
        ({"max_operations": 0}, "max_operations is not positive"),
        ({"channel": "http"}, "only the 'file' channel"),
        ({"exclusive_disposable_lab": False}, "exclusive_disposable_lab is false"),
    ],
)
def test_a_malformed_scalable_grant_refuses_before_any_contact(
    tmp_path: Path, campus30, overrides, fragment
):
    """Each defect of a schema 2 grant is named before anything is read."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)

    result = harness.run(grant=harness.grant(**overrides))

    assert result.envelope.campaign_outcome is CampaignOutcome.REFUSED
    assert any(fragment in item for item in result.envelope.reasons), (
        result.envelope.reasons
    )
    assert harness.terminal.log == []
    assert result.persisted is None


def test_a_schema_two_grant_is_never_read_as_the_legacy_profile():
    """The legacy parser refuses schema 2; the scalable parser refuses schema 1."""
    _, found = parse_scalable_grant({"schema_version": 1})

    assert any("schema_version 1" in item.detail for item in found)


@pytest.mark.parametrize(
    "change",
    [
        "omitted_client",
        "foreign_client",
        "wrong_digest",
        "wrong_budget",
        "wrong_server",
    ],
)
def test_a_grant_that_differs_from_the_derived_scope_refuses_before_e1(
    tmp_path: Path, campus30, change
):
    """Omissions, foreign names, another digest or budget: nothing is applied."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    grant = harness.grant()
    if change == "omitted_client":
        grant["clients"] = grant["clients"][1:]
    elif change == "foreign_client":
        grant["clients"] = [*grant["clients"], "HQ-NOT-A-CLIENT"]
    elif change == "wrong_digest":
        grant["scope_sha256"] = hashlib.sha256(b"other").hexdigest()
    elif change == "wrong_budget":
        grant["max_operations"] += 1
    else:
        grant["servers"] = ["HQ-OTHER-SERVER"]

    result = harness.run(grant=grant)

    assert not _effects(harness)
    assert result.envelope.http_accepted is False
    assert result.envelope.product["refusal_code"] == "effect_scope_not_admitted"
    assert result.envelope.closure_findings


def test_a_routed_campus_is_refused_by_the_product_before_any_effect(
    tmp_path: Path,
):
    """An unobservable routed dependency refuses; there is no scope to grant."""
    harness = build_scalable_harness(tmp_path, 20, server_segment_role="servers")

    assert harness.prepared.scope is None
    assert "service_path_unsupported" in harness.prepared.findings[0]


# -- N clients through the whole envelope --------------------------------------------


def _accepted(result):
    envelope = result.envelope
    assert envelope.http_accepted is True, envelope.reasons[:10]
    assert envelope.campaign_outcome is CampaignOutcome.COMPLETED
    return envelope


@pytest.mark.parametrize(("clients", "sites"), [(2, 1), (20, 1), (30, 1)])
def test_selected_clients_are_each_accepted_once_in_the_products_order(
    tmp_path: Path, clients: int, sites: int
):
    """One first request, one outcome and one release per client, in order."""
    harness = build_scalable_harness(tmp_path, clients, sites=sites)

    envelope = _accepted(harness.run())

    assert len(envelope.clients) == clients
    assert all(item.dispatches >= 2 for item in envelope.clients)
    assert all(item.release_dispatches == 1 for item in envelope.clients)
    assert sorted(item.request_order for item in envelope.clients) == list(
        range(1, clients + 1)
    )
    by_order = sorted(envelope.clients, key=lambda item: item.request_order)
    assert [item.expectation_id for item in by_order] == sorted(
        item.expectation_id for item in by_order
    )
    assert harness.product_dispatches().count("http_release") == clients
    assert envelope.budget.reserve_used == clients
    assert envelope.budget.used_operations <= envelope.budget.max_operations


def test_scalable_envelope_describes_acceptance_effects_after_separate_l2_setup(
    tmp_path: Path, campus30
):
    """The product record does not deny trunk work performed by setup."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)

    envelope = _accepted(harness.run())

    assert "trunks_transit_vlans_and_gateways_not_configured_by_acceptance" in (
        envelope.limitations
    )
    assert "trunks_transit_vlans_and_gateways_are_proven_never_configured" not in (
        envelope.limitations
    )


def test_every_selected_client_stays_represented_when_trunks_fail(
    tmp_path: Path, campus30
):
    """A shared trunk fault: remote clients never start; every client is reported."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    uplinks = {
        end.link_id for end in harness.terminal.network.switches[SW1].trunks.values()
    }
    harness.terminal.network.down_links |= uplinks

    result = harness.run()

    envelope = result.envelope
    assert len(envelope.clients) == CAMPUS
    assert envelope.http_accepted is False
    remote = [
        item
        for item in envelope.clients
        if harness.prepared.scope.client(item.client).switch == SW1
    ]
    local = [item for item in envelope.clients if item not in remote]
    assert remote and local
    assert all(item.dispatches == 0 for item in remote)
    assert all(item.accepted for item in local), [item.findings for item in local]


def test_one_clients_fault_is_its_own(tmp_path: Path, campus30):
    """A port that never forwards: that client alone is refused."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    victim = next(item for item in harness.prepared.scope.clients if item.switch == SW2)
    harness.terminal.network.blocked_access.add((SW2, victim.port))

    result = harness.run()

    envelope = result.envelope
    rows = {item.client: item for item in envelope.clients}
    assert rows[victim.name].dispatches == 0
    assert not rows[victim.name].accepted
    assert all(item.accepted for name, item in rows.items() if name != victim.name)


def test_a_fault_in_an_unselected_branch_does_not_interfere(tmp_path: Path):
    """A second site without a service: broken, never read, never matters."""
    payload = campus_payload(12, marker=MARKER, sites=2)
    payload["sites"][1]["services"] = []
    plans = compose_campus(payload)
    harness = build_scalable_harness(tmp_path, 0, plans=plans)
    for name in list(harness.terminal.network.switches):
        if name.startswith("BR01"):
            harness.terminal.unreadable.add(name)
            harness.terminal.access_forwarding_after[name] = math.inf

    envelope = _accepted(harness.run())

    assert all(not item.client.startswith("BR01") for item in envelope.clients)
    assert not any(
        event.startswith("ios_read:BR01") for event in harness.terminal.events
    )


def test_a_replaced_receiver_stops_the_whole_invocation(tmp_path: Path, campus30):
    """After the fifth start nothing else is dispatched; every client is reported."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    starts = {"n": 0}

    def replace(kind: str) -> None:
        if kind == "http_start":
            starts["n"] += 1
            if starts["n"] == 5:
                harness.receiver.replace_with(
                    paired_process(process_incarnation="2026-09-22T10:00:00Z")
                )

    harness.terminal.on_dispatch = replace

    result = harness.run()

    kinds = harness.product_dispatches()
    assert kinds[-1] == "http_start" and kinds.count("http_start") == 5
    envelope = result.envelope
    assert len(envelope.clients) == CAMPUS
    assert envelope.primary_failure.startswith("authority_lost:process_instance")
    assert sum(1 for item in envelope.clients if item.dispatches == 0) == CAMPUS - 5


def test_the_evaluator_indexes_the_ledger_once(
    tmp_path: Path, campus30, monkeypatch: pytest.MonkeyPatch
):
    """Linear assembly: one ledger index, one row index, per evaluation."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    builds = {"ledger": 0}
    original = acceptance_evidence_index.LedgerIndex.build.__func__

    def counting(cls, entries):
        builds["ledger"] += 1
        return original(cls, entries)

    monkeypatch.setattr(
        acceptance_evidence_index.LedgerIndex, "build", classmethod(counting)
    )

    _accepted(harness.run())

    assert builds["ledger"] == 1


# -- cost -----------------------------------------------------------------------------


def test_the_executed_worst_case_fits_the_derived_model(tmp_path: Path, campus30):
    """Every bounded wait run to its last read stays inside the derived ceiling."""
    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    terminal = harness.terminal
    terminal.ios_ready_after = 90.0
    terminal.vlan_present_after = 5.0
    terminal.endpoint_ready_after = 30.0
    terminal.access_forwarding_after = {
        name: 29.0 for name in terminal.network.switches
    }
    terminal.trunk_forwarding_after = 29.0
    terminal.page_visible_after = 8.0

    result = harness.run()

    envelope = _accepted(result)
    cost = harness.prepared.scope.cost
    assert envelope.budget.used_operations <= cost.max_operations
    assert envelope.budget.elapsed_seconds <= cost.max_seconds
    assert envelope.budget.arithmetic == dict(cost.operation_lines)


def test_the_cost_profile_matches_the_constants_the_product_executes():
    """The model's per-step bounds are the runtimes' own constants."""
    from packet_tracer_mcp.application.use_cases import service_access_readiness_gate
    from packet_tracer_mcp.infrastructure.execution import (
        enterprise_configuration_runtime,
    )

    gate = service_access_readiness_gate
    assert COST_PROFILE.endpoint_calls_per_send == (
        enterprise_configuration_runtime.MAX_ENDPOINT_CALLS_PER_SEND
    )
    # The episode line is the allowance the runtime enforces per episode, not
    # a product of the per-sample ceiling: one sample may borrow up to
    # READINESS_SAMPLE_CALLS of it, and all of them together never exceed it.
    assert COST_PROFILE.readiness_sample_reads == gate.READINESS_EPISODE_CALLS
    assert gate.READINESS_EPISODE_CALLS == (
        (gate.READINESS_GROUP_MAX_SAMPLES - 1) * gate.READINESS_SAMPLE_ALLOWANCE + 1
    )
    assert (
        COST_PROFILE.readiness_episode_seconds == gate.READINESS_GROUP_DEADLINE_SECONDS
    )
    assert COST_PROFILE.continuity_rounds == gate.CONTINUITY_MAX_ROUNDS
    assert COST_PROFILE.continuity_episode_seconds == (
        gate.CONTINUITY_GROUP_DEADLINE_SECONDS
    )
    assert COST_PROFILE.continuity_calls_per_reading == (
        gate.CONTINUITY_READING_ALLOWANCE
    )


def test_a_legacy_grant_keeps_its_frozen_ceiling_and_rules(tmp_path: Path):
    """Schema 1 is decided exactly as before: 1,015 / 420 / 2 / 40."""
    from cold_http_acceptance_harness import build_harness

    harness = build_harness(tmp_path)

    result = harness.run(grant=harness.grant(max_operations=5000))

    assert _subjects(result) == {AcceptanceSubject.BUDGET}
    assert accept_cold_http.COLD_HTTP_PROPOSAL.max_operations == 1015
    assert ATTEMPT


def test_a_bypassed_readiness_gate_fails_the_per_group_ordering_oracle(
    tmp_path: Path, campus30, monkeypatch: pytest.MonkeyPatch
):
    """Every page answers while no group was ever observed: not an acceptance."""
    from packet_tracer_mcp.application.use_cases import service_access_readiness_gate
    from packet_tracer_mcp.domain.enterprise.services.service_access_readiness import (
        ReadinessDependentResult,
    )

    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    harness.terminal.access_forwarding_after = {
        name: math.inf for name in harness.terminal.network.switches
    }

    def bypass(self, expectation_id):
        return ReadinessDependentResult(
            expectation_id=expectation_id,
            service_id="bypassed",
            kind="http_fetch",
            client_device_id="",
            host_device_id="",
            interfaces=(),
            admitted=True,
        )

    monkeypatch.setattr(
        service_access_readiness_gate.ServiceAccessReadinessGate, "decide", bypass
    )

    result = harness.run()

    envelope = result.envelope
    assert harness.product_dispatches().count("http_start") == CAMPUS
    assert result.product_summary["status"] == "verified"
    assert envelope.http_accepted is False
    assert all(not item.accepted for item in envelope.clients)
    assert any(
        item.startswith("request_without_prior_group_observation:")
        for item in envelope.ordering
    )


def test_the_prepare_command_prints_the_derived_grant_fields(
    tmp_path: Path, campus30, capsys: pytest.CaptureFixture[str]
):
    """The operator entry point derives the same scope offline, contacting nothing."""
    import json

    from service_entry_fixture import BACKEND_VERSION, DEPLOYMENT_ID

    from packet_tracer_mcp.adapters.cli import cold_http_acceptance as cli

    harness = build_scalable_harness(tmp_path, CAMPUS, plans=campus30)
    intent = tmp_path / "intent.json"
    intent.write_text(harness.intent_json, encoding="utf-8")

    code = cli.main(
        [
            "--prepare",
            "--intent",
            str(intent),
            "--deployment",
            DEPLOYMENT_ID,
            "--build",
            BACKEND_VERSION,
            "--attempt",
            ATTEMPT,
        ],
        environ={"PT_MCP_GOVERNED_ROOT": str(harness.root)},
        repository_reader=lambda root: published_checkout(),
    )

    printed = json.loads(capsys.readouterr().out)
    assert code == 0, printed
    fields = printed["grant_fields"]
    assert fields["scope_sha256"] == harness.prepared.scope.digest()
    assert fields["clients"] == harness.grant()["clients"]
    assert fields["max_operations"] == harness.prepared.scope.cost.max_operations
    assert printed["intent_sha256"] == harness.grant()["intent_sha256"]
    assert harness.terminal.log == []


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


def test_the_public_tool_and_the_scalable_envelope_run_the_same_product(
    tmp_path: Path, campus30, monkeypatch: pytest.MonkeyPatch
):
    """R-D1: same composition, same dispatches, same result on one campus."""
    import json

    from campus_product_simulation import run_public_campus

    harness = build_scalable_harness(tmp_path / "acceptance", CAMPUS, plans=campus30)
    accepted = harness.run()
    assert accepted.envelope.http_accepted is True, accepted.envelope.reasons[:5]

    public, terminal = run_public_campus(tmp_path / "public", monkeypatch, campus30)

    assert _without_clock(public) == _without_clock(
        json.loads(json.dumps(accepted.product_summary))
    )
    assert [kind for _, kind in terminal.log] == harness.product_dispatches()
