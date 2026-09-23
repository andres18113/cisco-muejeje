"""Empty workspace through real E4/E5 stores and schema-2 product acceptance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from campus_product_simulation import campus_payload, compose_campus
from cold_http_acceptance_harness import (
    ATTEMPT,
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

from packet_tracer_mcp.application.ports.service_qualification import OpenedTransport
from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.application.use_cases.prepare_server_pt_commissioning import (
    prepare_server_pt_commissioning,
)
from packet_tracer_mcp.application.use_cases.prequalify_server_pt import (
    prequalify_server_pt,
)
from packet_tracer_mcp.application.use_cases.server_pt_phase_grant import (
    derive_server_pt_phase_grant,
)
from packet_tracer_mcp.application.use_cases.setup_server_pt_commissioning import (
    run_server_pt_setup,
)
from packet_tracer_mcp.domain.enterprise.models.cold_http_acceptance import (
    publication_claim,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import EnvironmentFingerprint
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.models.plans import TopologyPlan
from packet_tracer_mcp.infrastructure.catalog.server_pt_commissioning_evidence import (
    scoped_setup_evidence,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_campaign_authority import (
    ExactCiEvidence,
)
from packet_tracer_mcp.infrastructure.execution.server_pt_phase_channel import (
    GovernedPhaseChannel,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from packet_tracer_mcp.infrastructure.persistence.server_pt_raw_archive import (
    build_raw_answer_index,
)


def test_empty_commissioning_reaches_the_product_and_all_30_clients(
    tmp_path: Path, capsys
):
    """Only the PT boundary is simulated; each production phase retains data."""
    root = tmp_path / "checkout"
    root.mkdir()
    store = ServerPtCommissioningStore(root)
    preliminary_backend = _Physical()
    preliminary = prequalify_server_pt(
        preliminary_backend,
        _TrunkProbe(preliminary_backend),
        attempt_token=ATTEMPT[:8],
    )
    assert preliminary.ready_for_catalog_review
    assert preliminary_backend.devices == {}
    store.save_prequalification(ATTEMPT, preliminary)
    scoped_catalog, scoped_ports = scoped_setup_evidence(preliminary)
    bundle = prepare_server_pt_commissioning(30, MARKER)
    store.save_bundle(ATTEMPT, bundle)
    topology = TopologyPlan.model_validate_json(bundle.topology_json)
    physical = _EmptyCampusPhysical(topology)
    configuration = _BlockedRedundantTrunkConfiguration(topology)
    assert physical.created == set()
    assert physical.linked == set()
    assert not (root / "data" / "services").exists()

    setup = run_server_pt_setup(
        ATTEMPT,
        deployment_id="server-pt-c31-" + ATTEMPT,
        store=store,
        physical_runtime=physical,
        configuration_runtime=configuration,
        environment_fingerprint=EnvironmentFingerprint(
            backend="packet_tracer",
            backend_version="9.0.1.0858",
            bridge_transport="file",
            runtime_mode="logical-workspace",
        ),
        admission=lambda: (),
        port_inventory=scoped_ports,
        capability_catalog=scoped_catalog,
    )
    assert setup.ready, setup.reason
    assert len(physical.created) == 35
    assert len(physical.linked) == 36
    assert not (root / "data" / "services").exists()
    assert setup.physical is not None
    assert setup.physical.manifest is not None
    assert store.load_e4(ATTEMPT) == setup.physical
    assert store.load_e5(ATTEMPT) == setup.configuration
    assert setup.configuration.deployment_id == setup.physical.deployment_id
    assert (
        setup.configuration.source_topology_hash
        == setup.physical.physical_topology_hash
    )
    assert set(setup.configuration.mutation_action_ids) == set(bundle.setup_action_ids)
    assert setup.configuration.retained_action_ids == []
    store.save_phase_status(
        ATTEMPT,
        "setup",
        {
            "phase": "setup",
            "outcome": "ready",
            "deployment_id": "server-pt-c31-" + ATTEMPT,
        },
    )
    source = published_checkout()
    process = paired_process()
    ci = ExactCiEvidence(42, SHA, "https://example.test/42", ("six",))
    store.save_phase_grant(
        ATTEMPT,
        derive_server_pt_phase_grant(
            "setup",
            ATTEMPT,
            source,
            process,
            ci,
            bundle_sha256=hashlib.sha256(
                store.bundle_path_for(ATTEMPT).read_bytes()
            ).hexdigest(),
            prequalification_sha256="d" * 64,
            bundle=bundle,
        ),
    )
    store.update_current_status(
        {"phase": "setup", "outcome": "ready", "attempt_id": ATTEMPT}
    )
    store.refresh_index()

    from packet_tracer_mcp.adapters.cli.cold_http_acceptance import (
        main as acceptance_main,
    )

    assert (
        acceptance_main(
            [
                "--prepare",
                "--intent",
                str(store.intent_path_for(ATTEMPT)),
                "--deployment",
                "server-pt-c31-" + ATTEMPT,
                "--build",
                "9.0.1.0858",
                "--attempt",
                ATTEMPT,
            ],
            environ={"PT_MCP_GOVERNED_ROOT": str(root)},
            repository_reader=lambda _root: source,
        )
        == 0
    )
    prepared_cli = json.loads(capsys.readouterr().out)
    assert prepared_cli["grant_fields"]["max_operations"] == 7849
    assert prepared_cli["grant_fields"]["max_seconds"] == 2792
    store.save_archive_admission(ATTEMPT, "setup")
    store.refresh_index()

    intent = EnterpriseIntent.model_validate_json(bundle.intent_json)
    composed = compose_enterprise_reference(
        intent,
        packet_tracer_version=bundle.build,
        deployment_manifest=setup.physical.manifest,
        services=True,
    )
    assert composed.valid, composed.issues
    plans = compose_campus(campus_payload(30, marker=MARKER))
    assert plans.manifest.physical_topology_hash == bundle.physical_topology_hash
    plans.manifest = setup.physical.manifest
    plans.intent_json = bundle.intent_json
    plans.configuration_plan = composed.configuration
    plans.service_plan = composed.services

    from packet_tracer_mcp.application.use_cases.seal_server_pt_acceptance import (
        seal_server_pt_acceptance,
    )

    sealed = seal_server_pt_acceptance(
        ATTEMPT,
        store=store,
        source=source,
        process=process,
        ci=ci,
    )
    assert sealed.grant["max_operations"] == 7849
    assert sealed.grant["max_seconds"] == 2792
    assert sealed.grant["reserve_operations"] == 30
    assert sealed.grant["reserve_seconds"] == 40
    assert store.load_acceptance_grant(ATTEMPT) == sealed.grant

    applied_foundations = {
        item.action_id
        for item in setup.configuration.action_results
        if item.status.value in {"applied", "verified"}
    }
    assert set(bundle.setup_action_ids) <= applied_foundations
    harness = build_scalable_harness(
        tmp_path, 30, plans=plans, foundation_action_ids=applied_foundations
    )
    assert harness.prepared.findings == ()
    assert harness.prepared.scope is not None
    assert harness.prepared.scope.cost.max_operations == 7849
    original_open = harness.boundaries.open_channel
    raw_path = store.journal_path_for(ATTEMPT, "acceptance")

    def open_recorded(channel: str):
        opened = original_open(channel)
        assert opened.transport is not None
        return OpenedTransport(
            channel,
            GovernedPhaseChannel(
                opened.transport,
                raw_path,
                phase="acceptance",
                max_operations=7849,
                max_seconds=2792,
                authority=lambda: (),
            ),
            opened.live,
            opened.detail,
        )

    harness.boundaries = replace(harness.boundaries, open_channel=open_recorded)
    result = harness.run(grant=sealed.grant)

    assert result.accepted is True
    assert len(result.envelope.clients) == 30
    assert all(client.accepted for client in result.envelope.clients)
    assert all(
        client.release_outcome == "released" for client in result.envelope.clients
    )
    stored = harness.envelope_store.load_publication(ATTEMPT)
    assert publication_claim(harness.envelope_store.load(ATTEMPT), stored) == (True, "")
    raw_index = build_raw_answer_index(raw_path, result.envelope)
    assert raw_index["counted_operations"] == result.envelope.budget.used_operations
    assert any(
        item["purpose"].startswith("readiness:") for item in raw_index["entries"]
    )


def test_acceptance_does_not_start_http_without_the_l2_setup_effects(tmp_path: Path):
    """The external boundary begins with no VLAN or trunk foundation."""
    plans = compose_campus(campus_payload(30, marker=MARKER))
    harness = build_scalable_harness(
        tmp_path, 30, plans=plans, foundation_action_ids=set()
    )

    result = harness.run()

    assert result.accepted is False
    assert "http_start" not in harness.product_dispatches()
