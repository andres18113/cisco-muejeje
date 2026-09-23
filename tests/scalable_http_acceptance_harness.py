"""Controlled boundaries for the scalable acceptance route over a campus.

Everything the legacy harness keeps real stays real here: the acceptance
coordinator, the shared session composition, the product use case, both
runtimes, the readiness gate, the ledger and every store. The terminal is the
SIMULATED campus of `campus_product_simulation`, and the grant is built from
the scope the real offline prepare path derives from the persisted manifest
and the intent, exactly as an operator would obtain it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from campus_product_simulation import (
    CampusPlans,
    CampusTerminal,
    campus_payload,
    campus_terminal,
    compose_campus,
)
from cold_http_acceptance_harness import (
    ATTEMPT,
    INCARNATION,
    MARKER,
    PROCESS_ID,
    PROCESS_PATH,
    SHA,
    TREE,
    FakeClock,
    FakeLifecycle,
    FakeReceiver,
    paired_process,
    published_checkout,
)
from service_entry_fixture import BACKEND_VERSION, IsolationPreflight

from packet_tracer_mcp.adapters.cli.cold_http_acceptance import (
    acceptance_session,
    production_boundaries,
)
from packet_tracer_mcp.application.ports.service_qualification import OpenedTransport
from packet_tracer_mcp.application.use_cases.accept_cold_http import (
    AcceptanceBoundaries,
    AcceptanceRequest,
    AcceptanceResult,
    accept_cold_http,
)
from packet_tracer_mcp.application.use_cases.prepare_http_acceptance import (
    PreparedScope,
    prepare_http_acceptance,
)
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    RuntimeIdentity,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
)
from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    FileCampaignCoordinator,
)
from packet_tracer_mcp.infrastructure.persistence.cold_http_acceptance_store import (
    ColdHttpAcceptanceStore,
)
from packet_tracer_mcp.infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)


@dataclass
class ScalableHarness:
    """One scalable attempt's controlled world over one compiled campus."""

    root: Path
    clock: FakeClock
    plans: CampusPlans
    terminal: CampusTerminal
    lifecycle: FakeLifecycle
    receiver: FakeReceiver
    record_store: ServiceRunRecordStore
    envelope_store: ColdHttpAcceptanceStore
    coordinator: FileCampaignCoordinator
    manifest_store: DeploymentManifestStore
    boundaries: AcceptanceBoundaries
    prepared: PreparedScope
    opened_channels: list[str] = field(default_factory=list)

    @property
    def intent_json(self) -> str:
        """Return the exact intent the grant digests."""
        return self.plans.intent_json

    def grant(self, **overrides: Any) -> dict[str, Any]:
        """Return the schema 2 grant the prepared scope and fixture require."""
        document: dict[str, Any] = {
            **self.prepared.grant_skeleton(),
            "authorization_id": "AUTH-SCALABLE-HTTP-OFFLINE",
            "attempt_id": ATTEMPT,
            "sha": SHA,
            "tree": TREE,
            "build": BACKEND_VERSION,
            "channel": "file",
            "intent_sha256": hashlib.sha256(
                self.intent_json.encode("utf-8")
            ).hexdigest(),
            "marker": MARKER,
            "process_id": PROCESS_ID,
            "process_path": PROCESS_PATH,
            "process_incarnation": INCARNATION,
            "exclusive_disposable_lab": True,
            "local_fence_limitation_accepted": True,
        }
        document.update(overrides)
        return document

    def run(self, *, grant: dict[str, Any] | None = None) -> AcceptanceResult:
        """Run one attempt through the production coordinator."""
        document = self.grant() if grant is None else grant
        return accept_cold_http(
            AcceptanceRequest(
                execute=True,
                grant_document=document,
                grant_text=json.dumps(document, sort_keys=True),
                intent_json=self.intent_json,
            ),
            self.boundaries,
        )

    def product_dispatches(self) -> list[str]:
        """Return the kinds the terminal was asked, in order."""
        return [kind for _, kind in self.terminal.log]


def build_scalable_harness(
    tmp_path: Path,
    clients: int,
    *,
    sites: int = 1,
    server_segment_role: str = "data",
    plans: CampusPlans | None = None,
    foundation_action_ids: set[str] | None = None,
    **boundary_overrides: Any,
) -> ScalableHarness:
    """Compose the production boundaries over one simulated campus."""
    plans = plans or compose_campus(
        campus_payload(
            clients, marker=MARKER, sites=sites, server_segment_role=server_segment_role
        )
    )
    root = tmp_path / "checkout"
    clock = FakeClock()
    terminal = campus_terminal(
        tmp_path, plans, clock, foundation_action_ids=foundation_action_ids
    )
    lifecycle = FakeLifecycle(clock, [paired_process()])
    receiver = FakeReceiver(clock, paired_process())
    source = SourceTreeIdentity(sha=SHA, tree=TREE, dirty=False)
    holder: dict[str, ScalableHarness] = {}

    def open_channel(channel: str) -> OpenedTransport:
        holder["h"].opened_channels.append(channel)
        live = terminal.pt_alive()
        return OpenedTransport(
            channel, terminal, live, "heartbeat_fresh" if live else "heartbeat_stale"
        )

    manifest_store = DeploymentManifestStore(root / "data" / "deployments")
    manifest_store.save_verified(plans.manifest)
    prepared = prepare_http_acceptance(
        plans.intent_json,
        deployment_id=plans.manifest.deployment_id,
        build=BACKEND_VERSION,
        marker=MARKER,
        manifest_store=manifest_store,
        source_tree=source,
    )
    coordinator = FileCampaignCoordinator(tmp_path / "campaign")
    boundaries = replace(
        production_boundaries(root),
        import_preflight=IsolationPreflight(),
        runtime_identity=lambda: RuntimeIdentity("python", "packet_tracer_mcp"),
        repository=published_checkout,
        lifecycle=lifecycle.read,
        campaign_coordinator=coordinator,
        manifest_store=manifest_store,
        open_channel=open_channel,
        close_channel=lambda opened: None,
        session_factory=partial(acceptance_session, observe_source=lambda: source),
        clock=clock,
        sleep=clock.sleep,
        now=lambda: datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
        bind_receiver=receiver.bind,
    )
    boundaries = replace(boundaries, **boundary_overrides)
    harness = ScalableHarness(
        root=root,
        clock=clock,
        plans=plans,
        terminal=terminal,
        lifecycle=lifecycle,
        receiver=receiver,
        record_store=boundaries.record_store,
        envelope_store=boundaries.envelope_store,
        coordinator=coordinator,
        manifest_store=manifest_store,
        boundaries=boundaries,
        prepared=prepared,
    )
    holder["h"] = harness
    return harness
