"""Seal the exact schema-2 proposal and grant after a retained campaign setup.

The campaign decides two things here. Its purpose decides the source
authority (delivery: published HEAD and exact-SHA CI; experimental: a clean
committed checkpoint and no CI claim), and the setup grant must carry the
same campaign and purpose, so authority never crosses between them. A
charter that pinned an exact acceptance cost (C31) keeps that pin; an
experimental campaign instead requires the product's own derived cost to fit
the allocation its ledger admitted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ...domain.enterprise.models.physical_deployment import PhysicalDeploymentStatus
from ...domain.enterprise.models.scalable_http_acceptance import parse_scalable_grant
from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)
from ...domain.enterprise.models.service_run_record import SourceTreeIdentity
from ...infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
)
from ...infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from ...shared.utils import resolve_within, safe_name_component
from .prepare_http_acceptance import prepare_http_acceptance
from .prepare_server_pt_commissioning import SERVER_PT_BUILD
from .server_pt_campaign import (
    C31_CAMPAIGN,
    ExactCiEvidenceLike,
    ServerPtCampaign,
    source_authority_findings,
)


@dataclass(frozen=True)
class ServerPtAcceptanceSeal:
    """The immutable product grant and its read-only proposal inputs."""

    grant: dict[str, object]
    grant_path: str
    prepare_path: str
    seal_path: str


def seal_server_pt_acceptance(
    attempt_id: str,
    *,
    store: ServerPtCommissioningStore,
    source: RepositoryIdentity,
    process: DiagnosticLifecycleObservation,
    ci: ExactCiEvidenceLike | None,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
    allocation: tuple[int, float] | None = None,
) -> ServerPtAcceptanceSeal:
    """Derive unchanged `--prepare` fields; write the grant before contact.

    `allocation` is the operations and seconds the experimental ledger still
    admits for this phase; the product's derived cost must fit inside it.
    """
    bundle = store.load_bundle(attempt_id)
    store.require_archived_phase(attempt_id, "setup", "ready")
    if store.cleanup_started(attempt_id):
        raise ValueError("acceptance cannot follow an owned cleanup attempt")
    setup = store.load_phase_status(attempt_id, "setup")
    setup_grant = store.load_phase_grant(attempt_id, "setup")
    store.require_bundle_sha256(attempt_id, setup_grant.bundle_sha256)
    physical = store.load_e4(attempt_id)
    configuration_plan = store.load_configuration_plan(attempt_id)
    configuration = store.load_e5(attempt_id)
    if (
        setup.get("outcome") != "ready"
        or physical.status is not PhysicalDeploymentStatus.VERIFIED
        or physical.manifest is None
        or physical.deployment_id != setup_grant.deployment_id
        or configuration.deployment_id != physical.deployment_id
        or configuration.source_topology_hash != physical.physical_topology_hash
        or configuration.config_semantic_hash != bundle.configuration_semantic_hash
        or configuration_plan.semantic_hash != bundle.configuration_semantic_hash
        or len(configuration.mutation_action_ids) != len(bundle.setup_action_ids)
        or set(configuration.mutation_action_ids) != set(bundle.setup_action_ids)
        or configuration.retained_action_ids
    ):
        raise ValueError("retained setup is not ready for acceptance")
    if (
        setup_grant.campaign_id != campaign.campaign_id
        or setup_grant.charter_sha256 != campaign.charter_sha256
        or setup_grant.execution_purpose != campaign.purpose.value
    ):
        raise ValueError("setup was sealed under another campaign or purpose")
    if (
        source.head != setup_grant.source_sha
        or source.tree != setup_grant.source_tree
        or source_authority_findings(campaign, source, ci)
        or process.error
        or process.mailbox_entries
        or process.process_id != setup_grant.process_id
        or process.process_path != setup_grant.process_path
        or process.process_incarnation != setup_grant.process_incarnation
        or SERVER_PT_BUILD not in (process.product_version, process.file_version)
    ):
        raise ValueError("source or receiver differs from retained setup")
    deployment = physical.deployment_id
    history = resolve_within(
        store.root,
        "data",
        "services",
        safe_name_component(deployment, "deployment"),
    )
    try:
        if history.exists() and any(history.iterdir()):
            raise ValueError("deployment already has service history")
    except OSError as exc:
        raise ValueError("service history is unreadable") from exc
    manifest_store = DeploymentManifestStore(store.root / "data" / "deployments")
    reloaded = manifest_store.latest_by_deployment_id(deployment)
    if reloaded != physical.manifest:
        raise ValueError("setup manifest reload differs from E4")
    prepared = prepare_http_acceptance(
        bundle.intent_json,
        deployment_id=deployment,
        build=bundle.build,
        marker=bundle.marker,
        manifest_store=manifest_store,
        source_tree=SourceTreeIdentity(
            sha=source.head, tree=source.tree, dirty=source.clean is not True
        ),
    )
    if prepared.scope is None or prepared.findings:
        raise ValueError("schema-2 product prepare refused the retained setup")
    cost = prepared.scope.cost
    if (
        len(prepared.scope.clients) != 30
        or cost.reserve_operations != 30
        or cost.reserve_seconds != 40
    ):
        raise ValueError("acceptance proposal exceeds or changes the charter")
    if campaign.acceptance_cost_pin is not None:
        if (cost.max_operations, cost.max_seconds) != campaign.acceptance_cost_pin:
            raise ValueError("acceptance proposal exceeds or changes the charter")
    elif (
        allocation is None
        or cost.max_operations > allocation[0]
        or cost.max_seconds > allocation[1]
    ):
        raise ValueError("acceptance cost does not fit the admitted allocation")
    prepare_document: dict[str, object] = {
        "mode": "prepare",
        "findings": list(prepared.findings),
        "product_refusal": prepared.product_refusal,
        "grant_fields": prepared.grant_skeleton(),
        "intent_sha256": bundle.intent_sha256,
        "cost": cost.document(),
    }
    prepare_path = store.save_acceptance_prepare(attempt_id, prepare_document)
    binding = json.dumps(
        {
            "charter": campaign.charter_sha256,
            "attempt": attempt_id,
            "source": source.head,
            "tree": source.tree,
            "scope": prepared.scope.digest(),
            "process": process.process_incarnation,
        },
        sort_keys=True,
    )
    authorization_id = (
        campaign.authorization_prefix
        + hashlib.sha256(binding.encode("utf-8")).hexdigest()[:16]
    )
    grant: dict[str, object] = {
        **prepared.grant_skeleton(),
        "authorization_id": authorization_id,
        "attempt_id": attempt_id,
        "sha": source.head,
        "tree": source.tree,
        "build": bundle.build,
        "channel": "file",
        "intent_sha256": bundle.intent_sha256,
        "marker": bundle.marker,
        "process_id": process.process_id,
        "process_path": process.process_path,
        "process_incarnation": process.process_incarnation,
        "exclusive_disposable_lab": True,
        "local_fence_limitation_accepted": True,
    }
    parsed, findings = parse_scalable_grant(grant)
    if parsed is None or findings:
        raise ValueError("derived acceptance grant is malformed")
    grant_path = store.save_acceptance_grant(attempt_id, grant)
    setup_path = store.record_path_for(attempt_id, "setup-grant")
    seal = {
        "campaign_id": campaign.campaign_id,
        "charter_sha256": campaign.charter_sha256,
        "execution_purpose": campaign.purpose.value,
        "source_sha": source.head,
        "source_tree": source.tree,
        "source_upstream_head": source.upstream_head,
        "ci_run_id": ci.run_id if ci is not None else 0,
        "ci_url": ci.url if ci is not None else "",
        "process_id": process.process_id,
        "process_path": process.process_path,
        "process_incarnation": process.process_incarnation,
        "attempt_id": attempt_id,
        "deployment_id": deployment,
        "setup_grant_sha256": hashlib.sha256(setup_path.read_bytes()).hexdigest(),
        "prepare_sha256": hashlib.sha256(prepare_path.read_bytes()).hexdigest(),
        "grant_sha256": hashlib.sha256(grant_path.read_bytes()).hexdigest(),
    }
    seal_path = store.save_acceptance_seal(attempt_id, seal)
    return ServerPtAcceptanceSeal(
        grant, str(grant_path), str(prepare_path), str(seal_path)
    )
