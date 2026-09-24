"""Read-only source, CI and receiver preflight for Server-PT LIVE phases.

The campaign decides what source authority a phase needs. A delivery campaign
(C31) reads the exact-SHA CI run of its published HEAD; an experimental one
(FASTLOOP) reads no CI at all, refuses a supplied run ID, and needs only a
clean committed checkpoint. Everything else -- import isolation, the branch,
the process identity, the build and an empty mailbox -- is the same for both.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...application.use_cases.prepare_server_pt_commissioning import SERVER_PT_BUILD
from ...application.use_cases.server_pt_campaign import (
    C31_CAMPAIGN,
    ServerPtCampaign,
)
from ...application.use_cases.server_pt_phase_grant import (
    ServerPtPhaseGrant,
    phase_grant_findings,
)
from ...domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RefusalSubject,
    RepositoryIdentity,
    diagnostic_lifecycle_continuity,
    repository_refusals,
)
from ...infrastructure.execution.file_bridge import FileBridge
from ...infrastructure.execution.import_isolation_preflight import (
    ImportIsolationPreflight,
)
from ...infrastructure.execution.receiver_continuity import (
    HandleBoundReceiverContinuity,
)
from ...infrastructure.execution.server_pt_campaign_authority import (
    ExactCiEvidence,
    read_exact_ci,
)
from ...infrastructure.execution.server_pt_phase_channel import (
    GovernedPhaseChannel,
    PhaseAllowanceExhausted,
)
from ...infrastructure.execution.service_qualification_lifecycle import (
    PacketTracerDiagnosticLifecycleReader,
)
from ...infrastructure.persistence.campaign_coordination import (
    FileCampaignCoordinator,
)
from ...infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from .service_qualification import repository_identity

FEATURE_BRANCH = "feature/server-pt-goal-foundations"


@dataclass(frozen=True)
class PhasePreflight:
    """Read-only observations retained before a channel or claim exists."""

    source: RepositoryIdentity | None = None
    ci: ExactCiEvidence | None = None
    process: DiagnosticLifecycleObservation | None = None
    findings: tuple[str, ...] = ()
    campaign: ServerPtCampaign = C31_CAMPAIGN


def phase_preflight(
    root: Path,
    *,
    ci_run_id: int,
    isolation_reader: Callable = lambda path: ImportIsolationPreflight(
        path
    ).ensure_isolated(),
    source_reader: Callable = repository_identity,
    ci_reader: Callable = lambda run, sha, path: read_exact_ci(run, sha, checkout=path),
    lifecycle_reader: Callable | None = None,
    campaign: ServerPtCampaign = C31_CAMPAIGN,
) -> PhasePreflight:
    """Stop at the first missing authority before opening a mailbox channel."""
    isolation = isolation_reader(root)
    if not isolation.isolated:
        return PhasePreflight(
            findings=("import_isolation_unverified",), campaign=campaign
        )
    if campaign.experimental and ci_run_id:
        # A run ID offered to an experimental phase is a claim it cannot
        # carry. Refusing it keeps a green label from ever riding along.
        return PhasePreflight(
            findings=("experimental_ci_claim_refused",), campaign=campaign
        )
    source = source_reader(root)
    repo_reasons = tuple(
        "repository:" + item.subject.value + ":" + item.kind.value
        for item in repository_refusals(source, source.head, source.tree)
        # Publication is a delivery requirement. An experimental checkpoint
        # may be ahead of its upstream; the upstream is still recorded.
        if not (
            campaign.experimental and item.subject is RefusalSubject.REPOSITORY_UPSTREAM
        )
    )
    if source.branch != FEATURE_BRANCH:
        repo_reasons += ("feature_branch_mismatch",)
    if repo_reasons:
        return PhasePreflight(source=source, findings=repo_reasons, campaign=campaign)
    ci = None
    if not campaign.experimental:
        ci, ci_reasons = ci_reader(ci_run_id, source.head, root)
        if ci_reasons or ci is None:
            return PhasePreflight(
                source=source,
                findings=ci_reasons or ("ci_unobservable",),
                campaign=campaign,
            )
    reader = lifecycle_reader or PacketTracerDiagnosticLifecycleReader().read
    process = reader(time.monotonic() + 10.0)
    reasons: list[str] = []
    if (
        process.error
        or not process.process_id
        or not process.process_path
        or not process.process_incarnation
    ):
        reasons.append("receiver_unobservable:" + (process.error or "identity_missing"))
    if SERVER_PT_BUILD not in (process.product_version, process.file_version):
        reasons.append("packet_tracer_build_mismatch")
    if process.mailbox_entries:
        reasons.append("mailbox_not_empty")
    return PhasePreflight(
        source=source,
        ci=ci,
        process=process,
        findings=tuple(reasons),
        campaign=campaign,
    )


@dataclass
class BoundLivePhase:
    """One owned claim, receiver handle and bounded file channel."""

    grant: ServerPtPhaseGrant
    channel: GovernedPhaseChannel
    claim: object
    receiver: object
    coordinator: FileCampaignCoordinator
    release_findings: tuple[str, ...] = ()

    def __enter__(self) -> BoundLivePhase:
        """Keep ownership until the caller has persisted its phase result."""
        return self

    def __exit__(self, *_exc) -> bool:
        """Release only this holder's lock; keep its permanent attempt marker."""
        reasons: list[str] = []
        try:
            self.channel.stop()
        except Exception as exc:
            reasons.append(f"channel_close_failed:{type(exc).__name__}")
        try:
            self.receiver.close()
        except Exception as exc:
            reasons.append(f"receiver_close_failed:{type(exc).__name__}")
        try:
            reasons.extend(self.coordinator.release(self.claim))
        except Exception as exc:
            reasons.append(f"claim_release_failed:{type(exc).__name__}")
        self.release_findings = tuple(reasons)
        return False


def bind_live_phase(
    preflight: PhasePreflight,
    grant: ServerPtPhaseGrant,
    *,
    store: ServerPtCommissioningStore,
    coordinator: FileCampaignCoordinator | None = None,
    receiver_binder: Callable | None = None,
    bridge_factory: Callable = FileBridge,
    bundle=None,
    clock: Callable[[], float] = time.monotonic,
) -> BoundLivePhase:
    """Seal grant, reserve this phase and bind one receiver before contact."""
    if (
        preflight.findings
        or preflight.source is None
        or (preflight.ci is None) is not preflight.campaign.experimental
        or preflight.process is None
    ):
        raise ValueError("phase preflight is not complete")
    if phase_grant_findings(
        grant,
        grant.phase,
        grant.attempt_id,
        preflight.source,
        preflight.process,
        preflight.ci,
        bundle_sha256=grant.bundle_sha256,
        prequalification_sha256=grant.prequalification_sha256,
        bundle=bundle,
        campaign=preflight.campaign,
    ):
        raise ValueError("phase grant differs from fresh authority")
    started = clock()
    deadline = started + grant.max_seconds
    store.save_phase_grant(grant.attempt_id, grant)
    coordination = coordinator or FileCampaignCoordinator()
    claim = coordination.claim(attempt_id=grant.phase + "-" + grant.attempt_id)
    receiver = None
    bridge = None
    try:
        binder = receiver_binder or (
            lambda process, until: HandleBoundReceiverContinuity.bind(
                process,
                until,
                lifecycle=PacketTracerDiagnosticLifecycleReader().read,
            )
        )
        receiver = binder(preflight.process, deadline)
        if clock() >= deadline:
            raise PhaseAllowanceExhausted("phase seconds exhausted during binding")
        if getattr(receiver, "mode", "") != "handle_bound":
            raise ValueError("bounded receiver mode was not established")
        bridge = bridge_factory()
        if not bridge.pt_alive():
            raise ValueError("file receiver heartbeat is stale")

        def authority() -> tuple[str, ...]:
            reasons = list(coordination.verify(claim))
            if reasons:
                return tuple(reasons)
            try:
                local_seconds = 0.5 if grant.phase == "prequalification" else 0.25
                observed = receiver.observe(min(deadline, clock() + local_seconds))
            except Exception as exc:
                return (f"receiver_observation_failed:{type(exc).__name__}",)
            return diagnostic_lifecycle_continuity(preflight.process, observed)

        channel = GovernedPhaseChannel(
            bridge,
            store.journal_path_for(grant.attempt_id, grant.phase),
            phase=grant.phase,
            max_operations=grant.max_operations,
            max_seconds=grant.max_seconds,
            reserve_operations=grant.reserve_operations,
            reserve_seconds=grant.reserve_seconds,
            authority=authority,
            clock=clock,
            started_at=started,
        )
    except BaseException:
        if receiver is not None:
            receiver.close()
        coordination.release(claim)
        raise
    return BoundLivePhase(grant, channel, claim, receiver, coordination)
