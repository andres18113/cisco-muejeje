"""Deterministic, exact-scope child grants under the activated C31 charter."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal, Protocol

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
from .server_pt_phase_budget import (
    PREQUALIFICATION_MAX_OPERATIONS,
    PREQUALIFICATION_MAX_SECONDS,
    PREQUALIFICATION_RESERVE_OPERATIONS,
    PREQUALIFICATION_RESERVE_SECONDS,
    derive_phase_budget,
)


class ExactCiEvidenceLike(Protocol):
    """Read-only exact-SHA CI result required to seal one phase."""

    run_id: int
    head_sha: str
    url: str


CHARTER_SHA256 = "7dbc5bbcd575bb0e9bcdac49fa003be6597e5b89e0742790c54237222fe8a200"
CAMPAIGN_ID = "SERVER-PT-C31-COMMISSION-01"
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
    ci: ExactCiEvidenceLike,
    *,
    bundle_sha256: str = "",
    prequalification_sha256: str = "",
    prequalification_attempt_id: str = "",
    bundle: ServerPtCommissioningBundle | None = None,
) -> ServerPtPhaseGrant:
    """Derive every target and allowance from the approved recipe and phase."""
    if _ATTEMPT.fullmatch(attempt_id) is None:
        raise ValueError("invalid campaign attempt ID")
    if (
        source.error
        or source.clean is not True
        or not source.head
        or not source.tree
        or source.upstream_head != source.head
        or ci.head_sha != source.head
    ):
        raise ValueError("source is not the clean published CI commit")
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
        phase=phase,
        authorization_id="",
        attempt_id=attempt_id,
        marker=MARKER_PREFIX + attempt_id,
        deployment_id=f"server-pt-c31-{attempt_id}",
        source_sha=source.head,
        source_tree=source.tree,
        ci_run_id=ci.run_id,
        ci_url=ci.url,
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
    ci: ExactCiEvidenceLike,
    *,
    bundle_sha256: str = "",
    prequalification_sha256: str = "",
    prequalification_attempt_id: str = "",
    bundle: ServerPtCommissioningBundle | None = None,
) -> tuple[str, ...]:
    """Re-derive an existing grant against fresh local and CI observations."""
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
        )
    except ValueError:
        return ("phase_authority_unobservable",)
    return () if given == expected else ("phase_grant_mismatch",)
