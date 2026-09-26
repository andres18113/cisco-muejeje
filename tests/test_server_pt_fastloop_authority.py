"""Experimental LIVE authority for SERVER-PT-IOS-FASTLOOP-01, and its limits.

The work order replaces C31's testing cadence, not its correctness: an
experimental phase may contact Packet Tracer from a clean committed local
checkpoint without CI, but it must never be mistaken for a delivery, borrow a
CI run, reset its consumption or outgrow the campaign's protected reserve.
Every test here drives the production rule or entry point that decides it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from packet_tracer_mcp.application.use_cases.accept_cold_http import (
    MEASURED_EXIT_CODE,
)
from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign import (
    C31_CAMPAIGN,
    CAMPAIGNS,
    DHCP_AUTONOMY_CAMPAIGN,
    DHCP_FASTLOOP_CAMPAIGN,
    FASTLOOP_CAMPAIGN,
    ExecutionPurpose,
    source_authority_findings,
)
from packet_tracer_mcp.application.use_cases.server_pt_campaign_ledger import (
    FASTLOOP_ALLOWANCE,
    closing_findings,
    ledger_record_findings,
    ledger_totals,
    opening_findings,
    phase_admission_findings,
    unsettled_phases,
)
from packet_tracer_mcp.application.use_cases.server_pt_phase_grant import (
    derive_server_pt_phase_grant,
    phase_grant_findings,
)
from packet_tracer_mcp.application.use_cases.server_pt_process_evidence import (
    exit_evidence_findings,
    exit_was_forced,
    incarnation_ticks,
)
from packet_tracer_mcp.domain.enterprise.models.scalable_http_acceptance import (
    EXPERIMENTAL_ENVELOPE_LIMITATION,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
    ExactCiEvidence,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_process_control import (
    window_identity_digest,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)

ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
OTHER = "1f1e2d3c4b5a69788796a5b4c3d2e1f0"
HEAD = "a" * 40
TREE = "b" * 40
OPENED = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _published() -> RepositoryIdentity:
    return RepositoryIdentity(
        branch="feature/server-pt-goal-foundations",
        head=HEAD,
        tree=TREE,
        clean=True,
        upstream_head=HEAD,
    )


def _checkpoint() -> RepositoryIdentity:
    """Return a clean local commit ahead of its upstream: experimental only."""
    return replace(_published(), upstream_head="c" * 40)


def _process() -> DiagnosticLifecycleObservation:
    return DiagnosticLifecycleObservation(
        process_id=123,
        process_path="C:\\Program Files\\Cisco Packet Tracer 9.0.1\\bin\\PacketTracer.exe",
        process_incarnation="2026-09-24T07:00:00-05:00",
        product_version="9.0.1.0858",
    )


def _ci(head: str = HEAD) -> ExactCiEvidence:
    return ExactCiEvidence(42, head, "https://example.test/42", ("six",))


# -- F1/F2/F3: purpose and source authority -----------------------------------------


def test_each_campaign_names_its_purpose_and_fixed_limits():
    """Identity selects authority; there is no flag that could."""
    assert CAMPAIGNS == {
        C31_CAMPAIGN.campaign_id: C31_CAMPAIGN,
        FASTLOOP_CAMPAIGN.campaign_id: FASTLOOP_CAMPAIGN,
        DHCP_FASTLOOP_CAMPAIGN.campaign_id: DHCP_FASTLOOP_CAMPAIGN,
        DHCP_AUTONOMY_CAMPAIGN.campaign_id: DHCP_AUTONOMY_CAMPAIGN,
    }
    assert C31_CAMPAIGN.purpose is ExecutionPurpose.DELIVERY
    assert C31_CAMPAIGN.complete_attempt_limit == 2
    assert C31_CAMPAIGN.acceptance_cost_pin == (7849, 2792)
    assert FASTLOOP_CAMPAIGN.purpose is ExecutionPurpose.EXPERIMENTAL
    assert FASTLOOP_CAMPAIGN.complete_attempt_limit is None
    assert FASTLOOP_CAMPAIGN.acceptance_cost_pin is None
    assert FASTLOOP_CAMPAIGN.charter_sha256 == (
        "3ed40bd1e3bfc433f340c995d3e5944b010e3099e8e1e1228953d2304646a793"
    )
    # The delegated autonomy mandate: experimental, no attempt quota, and its
    # section 5 lets retirement force-terminate a revalidated owned process.
    assert DHCP_AUTONOMY_CAMPAIGN.purpose is ExecutionPurpose.EXPERIMENTAL
    assert DHCP_AUTONOMY_CAMPAIGN.complete_attempt_limit is None
    assert DHCP_AUTONOMY_CAMPAIGN.acceptance_cost_pin is None
    assert DHCP_AUTONOMY_CAMPAIGN.forced_retirement_authorized is True
    assert DHCP_AUTONOMY_CAMPAIGN.charter_sha256 == (
        "3bb343ef80d75c0ebf37204c8fbfd57da23eea4e5de57a7227ee1ded2e2d1ea2"
    )


def test_delivery_still_needs_the_published_head_and_its_exact_ci():
    """Nothing about C31's source rule is relaxed."""
    assert source_authority_findings(C31_CAMPAIGN, _published(), _ci()) == ()
    assert "source_not_published" in source_authority_findings(
        C31_CAMPAIGN, _checkpoint(), _ci()
    )
    assert "exact_ci_missing" in source_authority_findings(
        C31_CAMPAIGN, _published(), None
    )
    assert "exact_ci_missing" in source_authority_findings(
        C31_CAMPAIGN, _published(), _ci("d" * 40)
    )
    assert "source_not_clean_committed" in source_authority_findings(
        C31_CAMPAIGN, replace(_published(), clean=False), _ci()
    )


def test_experimental_needs_a_frozen_checkpoint_and_refuses_any_ci_claim():
    """Ahead of upstream is fine; dirty, treeless or CI-labelled is not."""
    assert source_authority_findings(FASTLOOP_CAMPAIGN, _checkpoint(), None) == ()
    assert source_authority_findings(FASTLOOP_CAMPAIGN, _checkpoint(), _ci()) == (
        "experimental_ci_claim_refused",
    )
    assert source_authority_findings(
        FASTLOOP_CAMPAIGN, replace(_checkpoint(), clean=False), None
    ) == ("source_not_clean_committed",)
    assert source_authority_findings(
        FASTLOOP_CAMPAIGN, replace(_checkpoint(), tree=""), None
    ) == ("source_not_clean_committed",)
    assert source_authority_findings(
        FASTLOOP_CAMPAIGN, replace(_checkpoint(), clean=None), None
    ) == ("source_not_clean_committed",)


def test_an_experimental_grant_carries_its_purpose_and_no_ci():
    """The sealed record says what it is, and what it is not."""
    grant = derive_server_pt_phase_grant(
        "prequalification",
        ATTEMPT,
        _checkpoint(),
        _process(),
        None,
        campaign=FASTLOOP_CAMPAIGN,
    )

    assert grant.campaign_id == FASTLOOP_CAMPAIGN.campaign_id
    assert grant.charter_sha256 == FASTLOOP_CAMPAIGN.charter_sha256
    assert grant.execution_purpose == "experimental"
    assert (grant.ci_run_id, grant.ci_url) == (0, "")
    assert grant.source_upstream_head == "c" * 40
    assert grant.deployment_id == "server-pt-fastloop-" + ATTEMPT
    with pytest.raises(ValueError):
        derive_server_pt_phase_grant(
            "prequalification",
            ATTEMPT,
            _checkpoint(),
            _process(),
            _ci(),
            campaign=FASTLOOP_CAMPAIGN,
        )


# -- F4: authority never crosses purposes --------------------------------------------


def test_experimental_and_delivery_grants_never_rederive_as_each_other():
    """Re-derivation uses the caller's campaign, so a grant cannot migrate."""
    bundle = prepare_server_pt_commissioning(30, "COLD_HTTP_" + ATTEMPT)
    common = {
        "bundle_sha256": "c" * 64,
        "prequalification_sha256": "d" * 64,
        "bundle": bundle,
    }
    experimental = derive_server_pt_phase_grant(
        "setup",
        ATTEMPT,
        _checkpoint(),
        _process(),
        None,
        campaign=FASTLOOP_CAMPAIGN,
        **common,
    )
    delivery = derive_server_pt_phase_grant(
        "setup", ATTEMPT, _published(), _process(), _ci(), **common
    )

    # A delivery run cannot even derive from the experimental source ...
    assert phase_grant_findings(
        experimental, "setup", ATTEMPT, _checkpoint(), _process(), None, **common
    ) == ("phase_authority_unobservable",)
    # ... and a published, CI-green source still does not produce it.
    assert phase_grant_findings(
        experimental, "setup", ATTEMPT, _published(), _process(), _ci(), **common
    ) == ("phase_grant_mismatch",)
    # The reverse direction is closed too.
    assert phase_grant_findings(
        delivery,
        "setup",
        ATTEMPT,
        _published(),
        _process(),
        None,
        campaign=FASTLOOP_CAMPAIGN,
        **common,
    ) == ("phase_grant_mismatch",)
    assert experimental.max_operations == delivery.max_operations == 4750


def test_the_binder_refuses_a_preflight_whose_ci_contradicts_its_purpose(tmp_path):
    """No receiver is bound for a mixed experimental/delivery preflight."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import (
        PhasePreflight,
        bind_live_phase,
    )

    grant = derive_server_pt_phase_grant(
        "prequalification",
        ATTEMPT,
        _checkpoint(),
        _process(),
        None,
        campaign=FASTLOOP_CAMPAIGN,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a receiver must not be bound")

    store = ServerPtCommissioningStore(tmp_path, FASTLOOP_CAMPAIGN.campaign_id)
    for preflight in (
        PhasePreflight(_checkpoint(), _ci(), _process(), campaign=FASTLOOP_CAMPAIGN),
        PhasePreflight(_published(), None, _process()),
    ):
        with pytest.raises(ValueError, match="preflight is not complete"):
            bind_live_phase(preflight, grant, store=store, receiver_binder=forbidden)


# -- F3: the experimental preflight --------------------------------------------------


class _Isolated:
    isolated = True


def _preflight(tmp_path, source, **kwargs):
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import phase_preflight

    def no_ci(*_args):
        raise AssertionError("an experimental preflight reads no CI")

    return phase_preflight(
        tmp_path,
        isolation_reader=lambda _root: _Isolated(),
        source_reader=lambda _root: source,
        ci_reader=no_ci,
        lifecycle_reader=lambda _deadline: _process(),
        **kwargs,
    )


def test_the_experimental_preflight_accepts_a_local_checkpoint_without_ci(tmp_path):
    """Ahead of upstream, clean, exact process: admitted, and no CI is read."""
    result = _preflight(
        tmp_path, _checkpoint(), ci_run_id=0, campaign=FASTLOOP_CAMPAIGN
    )

    assert result.findings == ()
    assert result.ci is None
    assert result.campaign is FASTLOOP_CAMPAIGN


def test_the_experimental_preflight_refuses_what_a_checkpoint_is_not(tmp_path):
    """Dirty, wrong branch or an offered CI run all stop before any process read."""
    offered = _preflight(
        tmp_path, _checkpoint(), ci_run_id=42, campaign=FASTLOOP_CAMPAIGN
    )
    dirty = _preflight(
        tmp_path,
        replace(_checkpoint(), clean=False),
        ci_run_id=0,
        campaign=FASTLOOP_CAMPAIGN,
    )
    branch = _preflight(
        tmp_path,
        replace(_checkpoint(), branch="main"),
        ci_run_id=0,
        campaign=FASTLOOP_CAMPAIGN,
    )

    assert offered.findings == ("experimental_ci_claim_refused",)
    assert offered.source is None
    assert "repository:repository_clean:not_permitted" in dirty.findings
    assert dirty.process is None
    assert branch.findings == ("feature_branch_mismatch",)


def test_the_delivery_preflight_still_refuses_an_unpublished_checkpoint(tmp_path):
    """The same checkpoint is not a delivery source."""
    from packet_tracer_mcp.adapters.cli.server_pt_live_phase import phase_preflight

    result = phase_preflight(
        tmp_path,
        ci_run_id=42,
        isolation_reader=lambda _root: _Isolated(),
        source_reader=lambda _root: _checkpoint(),
        ci_reader=lambda *_args: (_ci(), ()),
        lifecycle_reader=lambda _deadline: _process(),
    )

    assert "repository:repository_upstream:mismatch" in result.findings


# -- F5/F6: the campaign ledger ------------------------------------------------------


def _opening(episode: int = 1, **overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "kind": "episode_opening",
        "episode": episode,
        "question": "Does a sample finish the two-page table?",
        "stop_rule": "stop after one acceptance and its cleanup",
        "source_sha": HEAD,
        "source_tree": TREE,
        "source_upstream_head": "c" * 40,
        "tests_run": ["tests/test_readiness_native_pagination.py"],
        "attempt_ids": [ATTEMPT],
        "targets": ["HQ-DEFAULT-ACCESS-SW-01"],
        "permitted_effects": ["e4_create_and_readback"],
        "allocated_operations": 10_000,
        "allocated_seconds": 3_600,
        "opened_at_utc": OPENED.isoformat(),
    }
    value.update(overrides)
    return value


def _admission(phase: str, granted: int, seconds: float = 300.0, **extra):
    return {
        "kind": "phase_admission",
        "episode": 1,
        "attempt_id": ATTEMPT,
        "phase": phase,
        "granted_operations": granted,
        "granted_seconds": seconds,
        "draws_protected": False,
        "admitted_at_utc": OPENED.isoformat(),
        **extra,
    }


def _result(phase: str, used: int):
    return {
        "kind": "phase_result",
        "episode": 1,
        "attempt_id": ATTEMPT,
        "phase": phase,
        "used_operations": used,
        "active_seconds": 10.0,
        "outcome": "ready",
        "recorded_at_utc": OPENED.isoformat(),
    }


def test_an_opening_must_fit_the_ordinary_allowance_and_protect_the_tail():
    """The last 1,000 operations and 600 s are never an ordinary allocation."""
    now = OPENED
    assert opening_findings({}, _opening(), FASTLOOP_ALLOWANCE, now) == ()
    assert opening_findings(
        {}, _opening(allocated_operations=49_001), FASTLOOP_ALLOWANCE, now
    ) == ("allocation_exceeds_ordinary_operations",)
    assert opening_findings(
        {}, _opening(allocated_seconds=21_001), FASTLOOP_ALLOWANCE, now
    ) == ("allocation_exceeds_ordinary_seconds",)
    assert "episode_question_missing" in opening_findings(
        {}, _opening(question=""), FASTLOOP_ALLOWANCE, now
    )
    assert "episode_allocation_not_finite_positive" in opening_findings(
        {}, _opening(allocated_seconds=0), FASTLOOP_ALLOWANCE, now
    )
    assert "episode_not_next_in_sequence" in opening_findings(
        {}, _opening(episode=2), FASTLOOP_ALLOWANCE, now
    )


def test_one_episode_at_a_time_and_an_open_one_is_charged_in_full():
    """Time keeps running while open; nothing is refunded before closing."""
    records = {"episode-0001-opening": _opening()}
    later = OPENED + timedelta(hours=2)

    totals = ledger_totals(records, FASTLOOP_ALLOWANCE, later)

    assert totals.open_episode == 1
    assert totals.committed_operations == 10_000
    assert totals.committed_seconds == pytest.approx(7_200.0)
    assert "another_episode_is_open" in opening_findings(
        records, _opening(episode=2), FASTLOOP_ALLOWANCE, later
    )


def test_a_closed_episode_charges_what_it_used_and_its_active_time():
    """Closing replaces the allocation by the recorded use, never by less."""
    closed = OPENED + timedelta(minutes=12)
    records = {
        "episode-0001-opening": _opening(),
        "a": _admission("setup", 4_750, 1_500.0),
        "b": _result("setup", 260),
        "c": _admission("acceptance", 7_849, 2_792.0),
        "episode-0001-closing": {
            "kind": "episode_closing",
            "episode": 1,
            "closed_at_utc": closed.isoformat(),
        },
    }

    totals = ledger_totals(records, FASTLOOP_ALLOWANCE, closed + timedelta(days=1))

    # The acceptance result never arrived, so its whole grant stays charged.
    assert totals.committed_operations == 260 + 7_849
    assert totals.committed_seconds == pytest.approx(720.0)
    assert totals.open_episode is None
    assert unsettled_phases(records, 1) == (f"{ATTEMPT}:acceptance",)


def test_only_cleanup_may_draw_the_protected_reserve():
    """An ordinary phase must fit its episode; cleanup may use the tail."""
    records = {
        "episode-0001-opening": _opening(allocated_operations=5_000),
        "a": _admission("setup", 4_750),
        "b": _result("setup", 4_900),
    }
    now = OPENED + timedelta(minutes=5)
    admit = lambda phase, ops: phase_admission_findings(  # noqa: E731
        records,
        episode=1,
        attempt_id=ATTEMPT,
        phase=phase,
        granted_operations=ops,
        granted_seconds=300.0,
        allowance=FASTLOOP_ALLOWANCE,
        now=now,
        source_sha=HEAD,
        source_tree=TREE,
    )

    assert admit("acceptance", 101) == (("phase_exceeds_episode_allocation",), False)
    assert admit("acceptance", 100) == ((), False)
    assert admit("cleanup", 250) == ((), True)
    assert admit("cleanup", 50_000) == (("campaign_allowance_exhausted",), False)


def test_a_phase_is_admitted_once_for_its_declared_attempt_of_an_open_episode():
    """The ledger records effects before contact, exactly once each."""
    records = {"episode-0001-opening": _opening(), "a": _admission("setup", 100)}
    now = OPENED

    def admit(**kwargs):
        values = {
            "episode": 1,
            "attempt_id": ATTEMPT,
            "phase": "setup",
            "granted_operations": 10,
            "granted_seconds": 10.0,
            "allowance": FASTLOOP_ALLOWANCE,
            "now": now,
            "source_sha": HEAD,
            "source_tree": TREE,
        }
        values.update(kwargs)
        return phase_admission_findings(records, **values)[0]

    assert admit() == ("phase_already_admitted",)
    assert admit(attempt_id=OTHER) == ("attempt_not_declared_by_episode",)
    assert admit(episode=2) == ("episode_not_opened",)
    assert admit(phase="launch") == ("ledger_phase_unknown",)
    # Another commit is not the checkpoint this episode declared.
    assert admit(phase="acceptance", source_sha="d" * 40) == (
        "phase_source_differs_from_episode",
    )
    assert admit(phase="acceptance", source_tree="e" * 40) == (
        "phase_source_differs_from_episode",
    )
    records["z"] = {
        "kind": "episode_closing",
        "episode": 1,
        "closed_at_utc": now.isoformat(),
    }
    assert admit(phase="cleanup") == ("episode_already_closed",)
    assert closing_findings(records, 1, now) == ("episode_already_closed",)


def test_ledger_records_are_write_once_and_totals_survive_a_new_process(tmp_path):
    """No counter resets: another store instance recomputes the same totals."""
    store = ServerPtCommissioningStore(tmp_path, FASTLOOP_CAMPAIGN.campaign_id)
    store.save_ledger_record("episode-0001-opening", _opening())
    store.save_ledger_record(
        f"episode-0001-{ATTEMPT}-setup-admission", _admission("setup", 4750)
    )
    with pytest.raises(ValueError, match="already exists"):
        store.save_ledger_record("episode-0001-opening", _opening(question="other"))
    now = OPENED + timedelta(minutes=30)

    first = ledger_totals(store.ledger_records(), FASTLOOP_ALLOWANCE, now)
    again = ledger_totals(
        ServerPtCommissioningStore(
            tmp_path, FASTLOOP_CAMPAIGN.campaign_id
        ).ledger_records(),
        FASTLOOP_ALLOWANCE,
        now,
    )

    assert first == again
    assert first.committed_operations == 10_000
    assert not (tmp_path / "data" / "commissioning" / C31_CAMPAIGN.campaign_id).exists()


# -- F9: retirement evidence ---------------------------------------------------------


def _launch() -> dict[str, object]:
    process = _process()
    return {
        "pid": process.process_id,
        "process_path": process.process_path,
        "process_incarnation": process.process_incarnation,
        "main_window_title": "Cisco Packet Tracer",
        "command_line": f'"{process.process_path}" ',
        "observed_main_window_title": "Cisco Packet Tracer",
        "observed_command_line": f'"{process.process_path}" ',
        "observed_product_version": "9.0.1.0858",
    }


def _close(**overrides) -> dict[str, object]:
    value: dict[str, object] = {
        **_launch(),
        "method": "CloseMainWindow",
        "requested": True,
        "actual_exit_observed": True,
    }
    value.update(overrides)
    return value


def _document_window(**overrides) -> dict[str, object]:
    """Return the one owned, unnamed document window a retirement closes."""
    value: dict[str, object] = {
        "handle": 4242,
        "owner_pid": _process().process_id,
        "class_name": "Qt687QWindowIcon",
        "title": "Cisco Packet Tracer",
        "visible": True,
        "enabled": True,
        "owner_handle": 0,
    }
    value.update(overrides)
    value["identity_digest"] = window_identity_digest(
        str(value["class_name"]), str(value["title"])
    )
    return value


def _targeted(**overrides) -> dict[str, object]:
    """Return the retirement flow's graceful request: WM_CLOSE to that window."""
    return _close(
        **{"method": "WM_CLOSE", "close_target": _document_window(), **overrides}
    )


def _forced(**overrides) -> dict[str, object]:
    launch = _launch()
    value: dict[str, object] = {
        "method": "Process.Kill",
        "pid": launch["pid"],
        "rechecked_process_path": launch["process_path"],
        "rechecked_process_incarnation": launch["process_incarnation"],
        "rechecked_command_line": launch["observed_command_line"],
        "rechecked_document_window": _document_window(),
        "window_census_complete": True,
        "modal_windows_visible": False,
        "bound_process_start_ticks": incarnation_ticks(launch["process_incarnation"]),
        "bound_window_set_digest": "e" * 64,
        "disposable_workspace_rechecked": True,
        "ownership_basis": "owned_cleanup_restored",
        "requested_at_utc": OPENED.isoformat(),
    }
    value.update(overrides)
    return value


def test_graceful_exit_is_unchanged_and_forced_exit_is_its_own_record():
    """Delivery never accepts a forced exit; experimental records it as forced."""
    graceful = _close()
    forced = _targeted(forced_termination=_forced(), graceful_wait_seconds=30.0)

    assert exit_evidence_findings(_launch(), graceful, process_count=0) == ()
    assert exit_was_forced(graceful) is False
    assert exit_evidence_findings(_launch(), forced, process_count=0) == (
        "forced_termination_not_permitted",
    )
    assert (
        exit_evidence_findings(_launch(), forced, process_count=0, allow_forced=True)
        == ()
    )
    assert exit_was_forced(forced) is True


@pytest.mark.parametrize(
    "change",
    [
        {"forced_termination": _forced(rechecked_process_incarnation="other")},
        {"forced_termination": _forced(pid=999)},
        {"forced_termination": _forced(disposable_workspace_rechecked=False)},
        {"forced_termination": _forced(method="taskkill /IM")},
        {"forced_termination": _forced(method="Stop-Process")},
        # The kill was not bound to the rechecked process and window set.
        {"forced_termination": _forced(bound_process_start_ticks=None)},
        {"forced_termination": _forced(bound_process_start_ticks=1)},
        {"forced_termination": _forced(bound_window_set_digest="")},
        # The rechecked document window is absent, another window, or changed.
        {"forced_termination": _forced(rechecked_document_window=None)},
        {
            "forced_termination": _forced(
                rechecked_document_window=_document_window(handle=9)
            )
        },
        {
            "forced_termination": _forced(
                rechecked_document_window=_document_window(
                    title="Cisco Packet Tracer - C:\\coursework.pkt"
                )
            )
        },
        {"forced_termination": _forced(window_census_complete=False)},
        {"forced_termination": _forced(modal_windows_visible=True)},
        # A force never follows a request that named no document window.
        {"forced_termination": _forced(), "method": "CloseMainWindow"},
        {"forced_termination": _forced(rechecked_command_line="PacketTracer.exe x")},
        {"forced_termination": _forced(ownership_basis="")},
        {"forced_termination": _forced(), "graceful_wait_seconds": 0},
        {"forced_termination": _forced(), "graceful_wait_seconds": 600},
    ],
)
def test_a_forced_exit_must_name_the_rechecked_owned_process(change):
    """Wildcards, another incarnation or an unbounded wait are not ownership."""
    close = _targeted(**{"graceful_wait_seconds": 30.0, **change})

    assert "forced_termination_identity_unproven" in exit_evidence_findings(
        _launch(), close, process_count=0, allow_forced=True
    )


@pytest.mark.parametrize(
    "launch_change",
    [
        {"observed_main_window_title": "Cisco Packet Tracer - C:\\coursework.pkt"},
        {"observed_main_window_title": ""},
        {"observed_command_line": '"C:\\PacketTracer.exe" C:\\coursework.pkt'},
        {"observed_command_line": None},
        # What a capture claimed is never the evidence; only observed fields.
        {"observed_command_line": None, "command_line": '"C:\\x.exe"'},
    ],
)
def test_a_forced_exit_needs_a_launch_that_proves_a_blank_document(launch_change):
    """A launch that opened, or names, a document never permits a force."""
    launch = {**_launch(), **launch_change}
    close = _targeted(
        forced_termination=_forced(
            rechecked_command_line=launch["observed_command_line"]
        ),
        graceful_wait_seconds=30.0,
    )

    assert "forced_termination_identity_unproven" in exit_evidence_findings(
        launch, close, process_count=0, allow_forced=True
    )


def test_a_forced_exit_still_needs_the_independent_zero_census():
    """Recording a termination is not observing an exit."""
    close = _targeted(forced_termination=_forced(), graceful_wait_seconds=30.0)

    assert "process_exit_unobserved" in exit_evidence_findings(
        _launch(), close, process_count=1, allow_forced=True
    )


# -- the CLI boundary ---------------------------------------------------------------


@pytest.fixture
def fastloop_cli(tmp_path: Path, monkeypatch):
    """Bind a test charter to the experimental campaign of the CLI."""
    from importlib import import_module

    cli = import_module("packet_tracer_mcp.adapters.cli.server_pt_commissioning")
    charter = tmp_path / "work-order.md"
    charter.write_text("experimental work order", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "FASTLOOP_CHARTER_SHA256",
        hashlib.sha256(charter.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(cli, "repository_identity", lambda _root: _checkpoint())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("no process may be read by this refusal")

    monkeypatch.setattr(cli, "phase_preflight", forbidden)
    return cli, charter, {"PT_MCP_GOVERNED_ROOT": str(tmp_path)}


def _run(cli, argv, env, capsys):
    code = cli.main(argv, environ=env)
    return code, json.loads(capsys.readouterr().out)


def test_an_experimental_phase_refuses_a_ci_run_and_needs_an_episode(
    fastloop_cli, capsys
):
    """Both refusals happen before any process, mailbox or source read."""
    cli, charter, env = fastloop_cli
    base = ["--campaign", "fastloop", "--attempt", ATTEMPT, "--charter", str(charter)]

    assert _run(cli, ["--setup", *base, "--ci-run", "42"], env, capsys) == (
        2,
        {"outcome": "refused", "reason": "experimental_ci_claim_refused"},
    )
    assert _run(cli, ["--setup", *base], env, capsys) == (
        2,
        {"outcome": "refused", "reason": "episode_required"},
    )
    assert _run(
        cli,
        [
            "--setup",
            "--campaign",
            "fastloop",
            "--attempt",
            ATTEMPT,
            "--episode",
            "1",
            "--charter",
            __file__,
        ],
        env,
        capsys,
    ) == (2, {"outcome": "refused", "reason": "charter_digest_mismatch"})
    assert _run(
        cli,
        ["--record-correction", "--campaign", "fastloop", "--attempt", ATTEMPT],
        env,
        capsys,
    ) == (2, {"outcome": "refused", "reason": "correction_is_a_c31_record"})


def test_the_ledger_opens_and_closes_one_episode_without_contact(
    fastloop_cli, tmp_path: Path, capsys
):
    """Opening binds the checkpoint; a second one waits for the first to close."""
    cli, charter, env = fastloop_cli
    plan = {
        key: value
        for key, value in _opening().items()
        if key
        not in {
            "kind",
            "episode",
            "source_sha",
            "source_tree",
            "source_upstream_head",
            "opened_at_utc",
        }
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    closing_path = tmp_path / "closing.json"
    closing_path.write_text(
        json.dumps({"outcome": "diagnostic", "lab_state": "retired"}), encoding="utf-8"
    )
    ledger = ["--campaign", "fastloop", "--charter", str(charter)]

    code, opened = _run(
        cli, ["--open-episode", *ledger, "--episode-plan", str(plan_path)], env, capsys
    )
    assert code == 0, opened
    assert opened["ledger"]["open_episode"] == 1
    assert opened["ledger"]["committed_operations"] == 10_000
    code, again = _run(
        cli, ["--open-episode", *ledger, "--episode-plan", str(plan_path)], env, capsys
    )
    assert code == 2 and "another_episode_is_open" in again["reasons"]
    code, closed = _run(
        cli,
        [
            "--close-episode",
            *ledger,
            "--episode",
            "1",
            "--episode-closing",
            str(closing_path),
        ],
        env,
        capsys,
    )
    assert code == 0, closed
    assert closed["ledger"]["open_episode"] is None
    assert closed["ledger"]["committed_operations"] == 0

    store = ServerPtCommissioningStore(tmp_path, FASTLOOP_CAMPAIGN.campaign_id)
    record = store.ledger_records()["episode-0001-opening"]
    assert (record["source_sha"], record["source_upstream_head"]) == (HEAD, "c" * 40)
    assert record["execution_purpose"] == "experimental"
    assert store.verify_index() == ()
    assert _run(cli, ["--ledger-status", "--campaign", "c31"], env, capsys) == (
        2,
        {"outcome": "refused", "reason": "ledger_is_experimental_only"},
    )


def test_a_phase_is_refused_by_the_ledger_before_its_mailbox_exists(tmp_path):
    """No opening, no admission: the CLI's admission step names why."""
    from packet_tracer_mcp.adapters.cli.server_pt_commissioning import _ledger_admit

    store = ServerPtCommissioningStore(tmp_path, FASTLOOP_CAMPAIGN.campaign_id)

    assert _ledger_admit(
        store,
        FASTLOOP_CAMPAIGN,
        1,
        ATTEMPT,
        "setup",
        4750,
        1500.0,
        source=_checkpoint(),
    ) == ("episode_not_opened",)
    assert (
        _ledger_admit(
            store, C31_CAMPAIGN, 0, ATTEMPT, "setup", 4750, 1500.0, source=_published()
        )
        == ()
    )
    assert store.ledger_records() == {}


def test_a_ledger_record_stranded_before_indexing_is_adopted_alone(tmp_path):
    """A hard stop between a ledger write and its index must not block cleanup.

    Only ledger records are adopted, and only when every indexed byte is
    unchanged; any other drift stays a refusal.
    """
    store = ServerPtCommissioningStore(tmp_path, FASTLOOP_CAMPAIGN.campaign_id)
    store.save_ledger_record("episode-0001-opening", _opening())
    store.refresh_index()
    store.save_ledger_record(
        f"episode-0001-{ATTEMPT}-setup-admission", _admission("setup", 4750)
    )

    assert store.verify_index() == ("archive_inventory_changed",)
    assert store.adopt_ledger_residue(ledger_record_findings) == ()
    assert store.verify_index() == ()

    # A temporary file of an interrupted write is not a record.
    ledger_dir = store.ledger_path_for("episode-0001-opening").parent
    stray_tmp = ledger_dir / ".episode-0001-closing.json.0f.tmp"
    stray_tmp.write_text("{", encoding="utf-8")
    assert store.adopt_ledger_residue(ledger_record_findings) == (
        "archive_inventory_changed",
    )
    stray_tmp.unlink()
    # A result whose admission is absent does not hang from this ledger.
    store.save_ledger_record(
        f"episode-0001-{OTHER}-cleanup-result",
        {**_result("cleanup", 1), "attempt_id": OTHER},
    )
    assert store.adopt_ledger_residue(ledger_record_findings) == (
        "archive_inventory_changed",
    )
    store.ledger_path_for(f"episode-0001-{OTHER}-cleanup-result").unlink()
    # Two unindexed records cannot vouch for each other: the governed order
    # indexes an admission before its phase can write a result.
    store.save_ledger_record(
        f"episode-0001-{ATTEMPT}-acceptance-admission",
        _admission("acceptance", 7849),
    )
    store.save_ledger_record(
        f"episode-0001-{ATTEMPT}-acceptance-result", _result("acceptance", 400)
    )
    assert store.adopt_ledger_residue(ledger_record_findings) == (
        "archive_inventory_changed",
    )
    store.ledger_path_for(f"episode-0001-{ATTEMPT}-acceptance-admission").unlink()
    assert store.adopt_ledger_residue(ledger_record_findings) == (
        "archive_inventory_changed",
    )
    store.ledger_path_for(f"episode-0001-{ATTEMPT}-acceptance-result").unlink()

    stray = (
        tmp_path / "data" / "commissioning" / FASTLOOP_CAMPAIGN.campaign_id / "x.json"
    )
    stray.write_text("{}", encoding="utf-8")
    assert store.adopt_ledger_residue(ledger_record_findings) == (
        "archive_inventory_changed",
    )
    stray.unlink()
    opening = store.ledger_path_for("episode-0001-opening")
    opening.write_bytes(opening.read_bytes() + b" ")
    assert store.adopt_ledger_residue(ledger_record_findings) == (
        "archive_bytes_changed",
    )


# -- system level: the experimental route through the real product ---------------


def test_an_experimental_setup_seals_and_measures_through_the_same_product(
    tmp_path: Path,
):
    """Real E4/E5 stores, an experimental seal and the unchanged product route.

    Only the Packet Tracer boundary is simulated, exactly as in the C31
    end-to-end test. The seal refuses a delivery reading of the experimental
    setup and an allocation the product cost does not fit.
    """
    from campus_product_simulation import campus_payload, compose_campus
    from cold_http_acceptance_harness import ATTEMPT as HARNESS_ATTEMPT
    from cold_http_acceptance_harness import (
        MARKER,
        SHA,
        paired_process,
        published_checkout,
    )
    from scalable_http_acceptance_harness import build_scalable_harness
    from test_server_pt_commissioning import (
        _BlockedRedundantTrunkConfiguration,
        _EmptyCampusPhysical,
    )
    from test_server_pt_prequalification import _Physical, _TrunkProbe

    from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
        compose_enterprise_reference,
    )
    from packet_tracer_mcp.application.use_cases.prequalify_server_pt import (
        prequalify_server_pt,
    )
    from packet_tracer_mcp.application.use_cases.seal_server_pt_acceptance import (
        seal_server_pt_acceptance,
    )
    from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
        run_server_pt_setup,
    )
    from packet_tracer_mcp.domain.enterprise.models.deployment import (
        EnvironmentFingerprint,
    )
    from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
    from packet_tracer_mcp.domain.models.plans import TopologyPlan
    from packet_tracer_mcp.infrastructure.catalog.server_pt_commissioning_evidence import (
        scoped_setup_evidence,
    )

    attempt = HARNESS_ATTEMPT
    deployment = FASTLOOP_CAMPAIGN.deployment_prefix + attempt
    root = tmp_path / "checkout"
    root.mkdir()
    store = ServerPtCommissioningStore(root, FASTLOOP_CAMPAIGN.campaign_id)
    backend = _Physical()
    preliminary = prequalify_server_pt(
        backend, _TrunkProbe(backend), attempt_token=attempt[:8]
    )
    store.save_prequalification(attempt, preliminary)
    catalog, ports = scoped_setup_evidence(preliminary)
    bundle = prepare_server_pt_commissioning(30, MARKER)
    store.save_bundle(attempt, bundle)
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    setup = run_server_pt_setup(
        attempt,
        deployment_id=deployment,
        store=store,
        physical_runtime=_EmptyCampusPhysical(topology),
        configuration_runtime=_BlockedRedundantTrunkConfiguration(topology),
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version="9.0.1.0858",
            bridge_transport="file",
            runtime_mode="logical-workspace",
        ),
        admission=lambda: (),
        port_inventory=ports,
        capability_catalog=catalog,
    )
    assert setup.ready, setup.reason
    store.save_phase_status(
        attempt,
        "setup",
        {"phase": "setup", "outcome": "ready", "deployment_id": deployment},
    )
    checkpoint = replace(published_checkout(), upstream_head="c" * 40)
    process = paired_process()
    store.save_phase_grant(
        attempt,
        derive_server_pt_phase_grant(
            "setup",
            attempt,
            checkpoint,
            process,
            None,
            bundle_sha256=hashlib.sha256(
                store.bundle_path_for(attempt).read_bytes()
            ).hexdigest(),
            prequalification_sha256="d" * 64,
            bundle=bundle,
            campaign=FASTLOOP_CAMPAIGN,
        ),
    )
    store.update_current_status(
        {"phase": "setup", "outcome": "ready", "attempt_id": attempt}
    )
    store.refresh_index()
    store.save_archive_admission(attempt, "setup")
    store.refresh_index()

    with pytest.raises(ValueError, match="another campaign or purpose"):
        seal_server_pt_acceptance(
            attempt,
            store=store,
            source=published_checkout(),
            process=process,
            ci=_ci(SHA),
        )
    with pytest.raises(ValueError, match="allocation"):
        seal_server_pt_acceptance(
            attempt,
            store=store,
            source=checkpoint,
            process=process,
            ci=None,
            campaign=FASTLOOP_CAMPAIGN,
            allocation=(7_848, 3_000.0),
        )
    sealed = seal_server_pt_acceptance(
        attempt,
        store=store,
        source=checkpoint,
        process=process,
        ci=None,
        campaign=FASTLOOP_CAMPAIGN,
        allocation=(7_849, 2_792.0),
    )
    seal = json.loads(Path(sealed.seal_path).read_text(encoding="utf-8"))
    assert str(sealed.grant["authorization_id"]).startswith("SERVER-PT-FASTLOOP-")
    assert (seal["execution_purpose"], seal["ci_run_id"], seal["ci_url"]) == (
        "experimental",
        0,
        "",
    )
    assert seal["source_upstream_head"] == "c" * 40

    intent = EnterpriseIntent.model_validate_json(bundle.intent_json)
    composed = compose_enterprise_reference(
        intent,
        packet_tracer_version=bundle.build,
        deployment_manifest=setup.physical.manifest,
        services=True,
    )
    plans = compose_campus(campus_payload(30, marker=MARKER))
    plans.manifest = setup.physical.manifest
    plans.intent_json = bundle.intent_json
    plans.configuration_plan = composed.configuration
    plans.service_plan = composed.services
    applied = {
        item.action_id
        for item in setup.configuration.action_results
        if item.status.value in {"applied", "verified"}
    }
    harness = build_scalable_harness(
        tmp_path, 30, plans=plans, foundation_action_ids=applied
    )

    assert sealed.grant["execution_purpose"] == "experimental"

    result = harness.run(grant=sealed.grant)

    # Real product behaviour, published in time, and never a delivery.
    assert result.measured is True
    assert result.accepted is False
    assert result.exit_code == MEASURED_EXIT_CODE
    assert len(result.envelope.clients) == 30
    assert all(client.accepted for client in result.envelope.clients)
    assert EXPERIMENTAL_ENVELOPE_LIMITATION in result.envelope.limitations
    assert result.envelope.grant["execution_purpose"] == "experimental"
    summary = result.compact_summary()
    assert (summary["http_accepted"], summary["experimental_measured"]) == (
        False,
        True,
    )
    assert (summary["execution_purpose"], summary["publication"]) == (
        "experimental",
        "measured",
    )


def _unpublished_harness(tmp_path):
    from cold_http_acceptance_harness import published_checkout
    from scalable_http_acceptance_harness import build_scalable_harness

    harness = build_scalable_harness(tmp_path, 2)
    harness.boundaries = replace(
        harness.boundaries,
        repository=lambda: replace(published_checkout(), upstream_head="c" * 40),
    )
    return harness


def _authority(grant, **overrides):
    from packet_tracer_mcp.application.use_cases.accept_cold_http import (
        ExperimentalSourceAuthority,
    )

    values = {
        "campaign_id": FASTLOOP_CAMPAIGN.campaign_id,
        "episode": 1,
        "attempt_id": grant["attempt_id"],
        "authorization_id": grant["authorization_id"],
        "sha": grant["sha"],
        "tree": grant["tree"],
    }
    values.update(overrides)
    return ExperimentalSourceAuthority(**values)


def test_an_unpublished_experimental_grant_without_authority_is_refused(tmp_path):
    """A purpose field alone never waives publication: the public path."""
    harness = _unpublished_harness(tmp_path)

    result = harness.run(grant=harness.grant(execution_purpose="experimental"))

    assert result.measured is False and result.accepted is False
    assert harness.product_dispatches() == []
    assert any(item.subject.value == "repository" for item in result.envelope.admission)


def test_validated_authority_admits_the_unpublished_checkpoint_it_names(tmp_path):
    """Exact clean HEAD and tree, unpublished, reach the product and measure."""
    harness = _unpublished_harness(tmp_path)
    grant = harness.grant(execution_purpose="experimental")
    harness.boundaries = replace(
        harness.boundaries, experimental_authority=_authority(grant)
    )

    result = harness.run(grant=grant)

    assert result.measured is True
    assert result.accepted is False
    assert result.exit_code == MEASURED_EXIT_CODE
    assert "http_start" in harness.product_dispatches()
    assert result.envelope.source["publication_required"] is False
    assert result.envelope.source["upstream_head"] == "c" * 40
    assert "experimental_source_authority" in result.envelope.checks


@pytest.mark.parametrize(
    "override",
    [
        {"sha": "d" * 40},
        {"tree": "e" * 40},
        {"attempt_id": "f" * 32},
        {"authorization_id": "SERVER-PT-C31-0123456789abcdef"},
        {"campaign_id": ""},
        {"episode": 0},
    ],
)
def test_authority_for_anything_else_refuses_before_contact(tmp_path, override):
    """Foreign, partial or mismatched authority is a refusal, never a waiver."""
    harness = _unpublished_harness(tmp_path)
    grant = harness.grant(execution_purpose="experimental")
    harness.boundaries = replace(
        harness.boundaries, experimental_authority=_authority(grant, **override)
    )

    result = harness.run(grant=grant)

    assert result.measured is False
    assert harness.product_dispatches() == []
    assert any(
        "experimental_authority_does_not_match_grant" in item.detail
        for item in result.envelope.admission
    )


def test_authority_with_a_delivery_grant_is_a_conflict_not_a_waiver(tmp_path):
    """Conflicting purposes refuse before contact, published or not."""
    from scalable_http_acceptance_harness import build_scalable_harness

    harness = build_scalable_harness(tmp_path, 2)
    grant = harness.grant()
    harness.boundaries = replace(
        harness.boundaries, experimental_authority=_authority(grant)
    )

    result = harness.run(grant=grant)

    assert result.accepted is False
    assert harness.product_dispatches() == []


def test_the_published_delivery_path_is_unchanged(tmp_path):
    """Positive control: no authority, delivery grant, published HEAD."""
    from scalable_http_acceptance_harness import build_scalable_harness

    harness = build_scalable_harness(tmp_path, 2)

    result = harness.run()

    assert result.accepted is True
    assert result.exit_code == 0
    assert result.envelope.source["publication_required"] is True
    assert EXPERIMENTAL_ENVELOPE_LIMITATION not in result.envelope.limitations


def test_a_product_grant_names_a_known_purpose_or_is_refused(tmp_path):
    """Absent is delivery; any other word is a malformed grant, before contact."""
    from scalable_http_acceptance_harness import build_scalable_harness

    harness = build_scalable_harness(tmp_path, 2)

    result = harness.run(grant=harness.grant(execution_purpose="release"))

    assert result.accepted is False
    assert harness.product_dispatches() == []
    assert EXPERIMENTAL_ENVELOPE_LIMITATION not in result.envelope.limitations
