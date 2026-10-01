"""Campaign claim ownership, diagnostic admission and live execution authority.

The claim is taken before any fallible admission check and released exactly
once into the record. Live authority is re-decided from local process
continuity before every effect and never regained once lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...domain.enterprise.models.service_qualification import (
    Q3_FL_STAGES,
    Q3_NATIVE_STAGES,
    SP1_ROUTED_STAGES,
    SP2_STAGES,
    DiagnosticLifecycleObservation,
    QualificationAuthorization,
    QualificationRecord,
    QualificationRefusal,
    QualificationStage,
    RefusalKind,
    RefusalSubject,
    ReleaseRecord,
    StageDefinition,
    diagnostic_lifecycle_refusals,
    refusal,
)
from .contracts import QualificationBoundaries, bounded

#: The boundaries each executable diagnostic requires to have been composed.
#: A missing one is a refusal before contact, never a quieter experiment.
_DIAGNOSTIC_BOUNDARIES: dict[QualificationStage, tuple[str, ...]] = {
    QualificationStage.D_DHCP: ("q3_product_contract", "diagnostic_lifecycle"),
    QualificationStage.D_WEB: (
        "forwarding_probe",
        "diagnostic_service_runtime",
        "diagnostic_lifecycle",
    ),
    **{
        stage: (
            "dhcp_product_contract",
            "diagnostic_lifecycle",
            "native_default_transitions",
        )
        for stage in (*Q3_FL_STAGES, *Q3_NATIVE_STAGES)
    },
}
for _stage in SP2_STAGES:
    _DIAGNOSTIC_BOUNDARIES[_stage] = _DIAGNOSTIC_BOUNDARIES[QualificationStage.Q3_FL_C2]
_DIAGNOSTIC_BOUNDARIES[QualificationStage.SP2_REMOTE_RELAY] = (
    "sp2_remote_relay_contract",
    "native_product_runtimes",
    "diagnostic_lifecycle",
)
_DIAGNOSTIC_BOUNDARIES[QualificationStage.SP2_MIXED_PRODUCT] = (
    "sp2_mixed_product_contract",
    "native_product_runtimes",
    "native_product_import_preflight",
    "native_product_record_store_factory",
    "native_product_endpoint_observer",
    "diagnostic_lifecycle",
)
_DIAGNOSTIC_BOUNDARIES[QualificationStage.SP2_CAPACITY_PRODUCT] = (
    *_DIAGNOSTIC_BOUNDARIES[QualificationStage.SP2_MIXED_PRODUCT][1:],
    "sp2_capacity_product_contract",
)
_DIAGNOSTIC_BOUNDARIES[QualificationStage.Q3_NATIVE_PRODUCT] = (
    "native_product_contract",
    "native_product_runtimes",
    "native_product_import_preflight",
    "native_product_record_store_factory",
    "native_product_endpoint_observer",
    "diagnostic_lifecycle",
)
for _stage in SP1_ROUTED_STAGES:
    _DIAGNOSTIC_BOUNDARIES[_stage] = (
        "sp1_product_contract",
        "sp1_public_product_entry",
        "native_product_runtimes",
        "native_product_record_store_factory",
        "native_product_endpoint_observer",
        "diagnostic_lifecycle",
    )


def diagnostic_admission(
    definition: StageDefinition,
    authorization: QualificationAuthorization | None,
    boundaries: QualificationBoundaries,
    hold: CampaignHold,
) -> tuple[list[QualificationRefusal], DiagnosticLifecycleObservation | None]:
    """Check what an executable diagnostic needs beyond the shared rule.

    Three things the request rule cannot decide on its own: whether this
    campaign is already being run by another writer, which only a scope both
    writers share can answer; whether this attempt identity has ever been used
    before; and whether the boundaries this stage's steps require were composed.
    All three fail closed. A campaign whose exclusivity cannot be taken is not
    exclusive, an attempt whose uniqueness cannot be observed is not unique, and
    a stage whose executor is missing refuses rather than running a narrower
    experiment under the same authority.

    The campaign claim is taken first and held while everything after it is
    decided, so the uniqueness check and the record creation that follows it
    are no longer two steps a second writer can interleave with. The caller
    owns `hold` before this function starts, so the claim is under its
    top-level finalizer before any fallible admission check runs.
    """
    if authorization is None:  # pragma: no cover - request_refusals covers it
        return [refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZATION)], None
    coordinator = boundaries.campaign_coordinator
    if coordinator is None:
        return (
            [
                refusal(
                    RefusalKind.NOT_PERMITTED,
                    RefusalSubject.ATTEMPT_IDENTITY,
                    "No campaign coordination scope is composed, so this run "
                    "cannot exclude a writer in another checkout.",
                )
            ],
            None,
        )
    try:
        claim = coordinator.claim(attempt_id=authorization.attempt_id)
    except Exception as exc:
        return (
            [
                refusal(
                    RefusalKind.NOT_PERMITTED,
                    RefusalSubject.ATTEMPT_IDENTITY,
                    f"campaign_not_exclusive:{bounded(exc)}",
                )
            ],
            None,
        )
    hold.claim = claim
    found, observed = _diagnostic_admission_checks(
        definition, authorization, boundaries
    )
    return found, observed


def _release_claim(coordinator: Any, claim: Any) -> tuple[str, ...]:
    """Release one campaign claim, never raising out of a finalization path."""
    try:
        return tuple(coordinator.release(claim) or ())
    except Exception as exc:
        return (f"campaign_release_failed:{type(exc).__name__}",)


@dataclass
class CampaignHold:
    """One campaign claim, and whether this invocation already released it.

    The release is a finalization result like any other, so it has to reach
    the record before the record is completed. It used to run in the caller's
    outer `finally`, which is after completion, so a lock that stayed held
    left the next campaign blocked with nothing in the record saying so. The
    hold makes the release idempotent: the run releases it inside its own
    lifecycle, and the outer `finally` is the safety net for every path that
    never got that far.
    """

    coordinator: Any = None
    claim: Any = None
    finalized: bool = False
    projected: bool = False
    release_fact: ReleaseRecord | None = None
    release_reasons: tuple[str, ...] = ()

    def finalize(
        self, record: QualificationRecord | None = None
    ) -> ReleaseRecord | None:
        """Release and project this invocation's claim exactly once."""
        if not self.finalized:
            self.finalized = True
            if self.claim is not None and self.coordinator is not None:
                reasons = _release_claim(self.coordinator, self.claim)
                self.release_reasons = reasons
                detail = bounded("; ".join(reasons))
                outcome = "released" if not reasons else "release_unverified"
                if any("held_by_another_writer" in item for item in reasons):
                    outcome = "foreign_claim_retained"
                elif any("malformed" in item for item in reasons):
                    outcome = "malformed_claim_retained"
                self.release_fact = ReleaseRecord(
                    resource="campaign:lock",
                    kind="claim",
                    outcome=outcome,
                    detail=detail,
                )
        fact = self.release_fact
        if record is None or fact is None or self.projected:
            return fact
        self.projected = True
        record.releases.append(fact)
        if fact.outcome == "released":
            return fact
        reasons = self.release_reasons
        record.coordination_residue.extend(reasons)
        record.secondary_failures.extend(f"campaign_release:{item}" for item in reasons)
        record.limitations.append("campaign_lock_still_held_after_this_run")
        return fact


def _diagnostic_admission_checks(
    definition: StageDefinition,
    authorization: QualificationAuthorization,
    boundaries: QualificationBoundaries,
) -> tuple[list[QualificationRefusal], DiagnosticLifecycleObservation | None]:
    """Decide the remaining diagnostic admissions while the campaign is held."""
    found: list[QualificationRefusal] = []
    seen = getattr(boundaries.record_store, "attempt_exists", None)
    if not callable(seen):
        found.append(
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.ATTEMPT_IDENTITY,
                "The record store cannot state whether this attempt is new.",
            )
        )
    else:
        try:
            used = bool(seen(authorization.attempt_id))
        except Exception as exc:
            return (
                [
                    refusal(
                        RefusalKind.UNOBSERVABLE,
                        RefusalSubject.ATTEMPT_IDENTITY,
                        f"attempt_lookup_failed:{type(exc).__name__}",
                    )
                ],
                None,
            )
        if used:
            found.append(
                refusal(
                    RefusalKind.NOT_PERMITTED,
                    RefusalSubject.ATTEMPT_IDENTITY,
                    "This attempt identity already has a record; "
                    "a new SHA or process does not create an attempt.",
                )
            )
    required = _DIAGNOSTIC_BOUNDARIES.get(definition.stage, ())
    missing = [name for name in required if getattr(boundaries, name, None) is None]
    if missing:
        found.append(
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.FIXTURE,
                f"The executable {definition.stage.value} composition is "
                f"incomplete: {', '.join(missing)}.",
            )
        )
    observed: DiagnosticLifecycleObservation | None = None
    lifecycle = boundaries.diagnostic_lifecycle
    if callable(lifecycle):
        deadline = boundaries.clock() + max(
            0.0,
            float(definition.budget.max_seconds - definition.budget.reserve_seconds),
        )
        try:
            observed = lifecycle(deadline)
        except Exception as exc:
            observed = DiagnosticLifecycleObservation(
                error=f"diagnostic_lifecycle_failed:{type(exc).__name__}"
            )
        if boundaries.clock() > deadline and not observed.error:
            observed = DiagnosticLifecycleObservation(
                error="local_observation_deadline_exceeded:lifecycle"
            )
        found.extend(
            diagnostic_lifecycle_refusals(
                authorization,
                observed,
                authorization.build,
            )
        )
        authority = boundaries.campaign_source_authority
        if (
            authority is not None
            and not observed.error
            and observed.process_incarnation != authority.process_incarnation
        ):
            # The launch record pinned one incarnation. A process at the same
            # PID and path that is not that incarnation is another process.
            found.append(
                refusal(
                    RefusalKind.MISMATCH,
                    RefusalSubject.PROCESS_INSTANCE,
                    "The observed process is not the incarnation the campaign "
                    "launch record pinned.",
                )
            )
    return found, observed
