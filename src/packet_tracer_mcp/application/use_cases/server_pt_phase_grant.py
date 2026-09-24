"""Deterministic, exact-scope child grants under the activated C31 charter."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from ...domain.enterprise.models.cold_http_acceptance import MARKER_PREFIX
from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)
from ...domain.models.plans import TopologyPlan
from .prepare_server_pt_commissioning import (
    SERVER_PT_BUILD,
    ServerPtCommissioningBundle,
)
from .server_pt_campaign import (
    C31_CAMPAIGN,
    ExactCiEvidenceLike,
    ServerPtCampaign,
    source_authority_findings,
)
from .server_pt_phase_budget import (
    PREQUALIFICATION_MAX_OPERATIONS,
    PREQUALIFICATION_MAX_SECONDS,
    PREQUALIFICATION_RESERVE_OPERATIONS,
    PREQUALIFICATION_RESERVE_SECONDS,
    derive_phase_budget,
)

__all__ = [
    "CAMPAIGN_ID",
    "CHARTER_SHA256",
    "ExactCiEvidenceLike",
    "ServerPtPhaseGrant",
    "derive_server_pt_phase_grant",
    "phase_grant_findings",
]

CHARTER_SHA256 = C31_CAMPAIGN.charter_sha256
CAMPAIGN_ID = C31_CAMPAIGN.campaign_id
RECOVERY_PREQUALIFICATION_ATTEMPT = "5b09a9c35fd572f00945bdb18040d2fb"
_ATTEMPT = re.compile(r"[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ServerPtPhaseGrant(BaseModel):
    """One sealed preliminary, setup or cleanup phase; no implied support."""

    schema_version: int = 1
    campaign_id: str = CAMPAIGN_ID
    phase: Literal["prequalification", "setup", "cleanup"]
    authorization_id: str
    charter_sha256: str = CHARTER_SHA256
    operator_extensions: list[str] = Field(
        default_factory=lambda: [
            "server_pt_port_qualification",
            "2950t_24_trunk_qualification",
        ]
    )
    attempt_id: str
    marker: str
    deployment_id: str
    source_sha: str
    source_tree: str
    #: The upstream observed with the source. Delivery requires it to equal
    #: `source_sha`; experimental records it without requiring publication.
    source_upstream_head: str = ""
    #: `delivery` carries an exact-SHA CI run; `experimental` carries none
    #: (`ci_run_id` 0, empty URL) and can never be re-derived as delivery.
    execution_purpose: Literal["delivery", "experimental"] = "delivery"
    ci_run_id: int
    ci_url: str
    build: str = SERVER_PT_BUILD
    channel: str = "file"
    process_id: int
    process_path: str
    process_incarnation: str
    bundle_sha256: str = ""
    prequalification_sha256: str = ""
    prequalification_attempt_id: str = ""
    max_operations: int
    max_seconds: int
    reserve_operations: int = 0
    reserve_seconds: int = 0
    device_targets: list[str] = Field(default_factory=list)
    link_targets: list[str] = Field(default_factory=list)
    configuration_actions: list[str] = Field(default_factory=list)
    permitted_effects: list[str] = Field(default_factory=list)
    exclusive_disposable_lab: bool = True
    local_fence_limitation_accepted: bool = True


def derive_server_pt_phase_grant(
    phase: Literal["prequalification", "setup", "cleanup"],
    attempt_id: str,
    source: RepositoryIdentity,
    process: DiagnosticLifecycleObservation,
    ci: ExactCiEvidenceLike | None,
    *,
    bundle_sha256: str = "",
    prequalification_sha256: str = "",
    prequalification_attempt_id: str = "",
    bundle: ServerPtCommissioningBundle | None = None,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
) -> ServerPtPhaseGrant:
    """Derive every target and allowance from the approved recipe and phase.

    `campaign` decides the source authority: delivery needs the clean
    published HEAD and its exact-SHA CI run; experimental needs a clean
    committed checkpoint and refuses any CI claim.
    """
    if _ATTEMPT.fullmatch(attempt_id) is None:
        raise ValueError("invalid campaign attempt ID")
    if source_authority_findings(campaign, source, ci):
        raise ValueError("source is not admissible for this campaign's purpose")
    if (
        process.error
        or process.mailbox_entries
        or not process.process_id
        or not process.process_path
        or not process.process_incarnation
        or SERVER_PT_BUILD not in (process.product_version, process.file_version)
    ):
        raise ValueError("receiver identity is unbound or mailbox is not empty")
    token = attempt_id[:8]
    qualification_id = prequalification_attempt_id or attempt_id
    if _ATTEMPT.fullmatch(qualification_id) is None:
        raise ValueError("invalid preliminary evidence attempt ID")
    if phase == "prequalification":
        limits = (PREQUALIFICATION_MAX_OPERATIONS, PREQUALIFICATION_MAX_SECONDS)
        reserve = (
            PREQUALIFICATION_RESERVE_OPERATIONS,
            PREQUALIFICATION_RESERVE_SECONDS,
        )
        devices = [f"__MCP_PORTQUAL_{token}_00", f"__MCP_PROBE_C31_{token}_TRUNK"]
        links: list[str] = []
        actions: list[str] = []
        effects = ["qualify_server_pt_port_inventory", "qualify_2950t_24_trunk"]
    else:
        if (
            bundle is None
            or bundle.client_count != 30
            or bundle.site_count != 1
            or bundle.marker != MARKER_PREFIX + attempt_id
            or _SHA256.fullmatch(bundle_sha256) is None
            or _SHA256.fullmatch(prequalification_sha256) is None
        ):
            raise ValueError("sealed bundle or preliminary evidence is missing")
        topology = TopologyPlan.model_validate_json(bundle.topology_json)
        budget = derive_phase_budget(bundle)
        devices = sorted(device.name for device in topology.devices)
        links = sorted(link.id for link in topology.links)
        actions = list(bundle.setup_action_ids) if phase == "setup" else []
        limits = (
            (budget.setup_max_operations, budget.setup_max_seconds)
            if phase == "setup"
            else (budget.cleanup_max_operations, budget.cleanup_max_seconds)
        )
        reserve = (0, 0)
        effects = (
            ["e4_create_and_readback", "e5_vlan_trunk_foundations"]
            if phase == "setup"
            else ["remove_owned_campus_devices", "observe_workspace_restoration_twice"]
        )
    grant = ServerPtPhaseGrant(
        campaign_id=campaign.campaign_id,
        charter_sha256=campaign.charter_sha256,
        phase=phase,
        authorization_id="",
        operator_extensions=(
            [
                "server_pt_port_qualification",
                "2950t_24_trunk_qualification",
                "zero_contact_prequalification_recovery",
            ]
            if qualification_id == RECOVERY_PREQUALIFICATION_ATTEMPT
            else ["server_pt_port_qualification", "2950t_24_trunk_qualification"]
        ),
        attempt_id=attempt_id,
        marker=MARKER_PREFIX + attempt_id,
        deployment_id=campaign.deployment_prefix + attempt_id,
        source_sha=source.head,
        source_tree=source.tree,
        source_upstream_head=source.upstream_head,
        execution_purpose=campaign.purpose.value,
        ci_run_id=ci.run_id if ci is not None else 0,
        ci_url=ci.url if ci is not None else "",
        process_id=process.process_id,
        process_path=process.process_path,
        process_incarnation=process.process_incarnation,
        bundle_sha256=bundle_sha256,
        prequalification_sha256=prequalification_sha256,
        prequalification_attempt_id=qualification_id,
        max_operations=limits[0],
        max_seconds=limits[1],
        reserve_operations=reserve[0],
        reserve_seconds=reserve[1],
        device_targets=devices,
        link_targets=links,
        configuration_actions=actions,
        permitted_effects=effects,
    )
    canonical = json.dumps(
        grant.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return grant.model_copy(
        update={"authorization_id": hashlib.sha256(canonical.encode()).hexdigest()}
    )


def phase_grant_findings(
    given: ServerPtPhaseGrant,
    phase: Literal["prequalification", "setup", "cleanup"],
    attempt_id: str,
    source: RepositoryIdentity,
    process: DiagnosticLifecycleObservation,
    ci: ExactCiEvidenceLike | None,
    *,
    bundle_sha256: str = "",
    prequalification_sha256: str = "",
    prequalification_attempt_id: str = "",
    bundle: ServerPtCommissioningBundle | None = None,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
) -> tuple[str, ...]:
    """Re-derive an existing grant against fresh local and CI observations.

    The caller's campaign is the one derived under, so a grant sealed for
    another campaign or purpose never matches.
    """
    try:
        expected = derive_server_pt_phase_grant(
            phase,
            attempt_id,
            source,
            process,
            ci,
            bundle_sha256=bundle_sha256,
            prequalification_sha256=prequalification_sha256,
            prequalification_attempt_id=prequalification_attempt_id
            or given.prequalification_attempt_id,
            bundle=bundle,
            campaign=campaign,
        )
    except ValueError:
        return ("phase_authority_unobservable",)
    return () if given == expected else ("phase_grant_mismatch",)
