"""Fail-closed validation for wireless connectivity plans and observations.

Three separate contracts. The plan validation asks whether the intent is
realizable at all; the provenance validation asks whether a reading may be
attributed to the endpoint and build it is about to be credited to; the
observation validation asks whether a claimed state is backed by the evidence
it would need. None of them promotes anything: they return a `ValidationResult`
and the use case decides.

Every error carries a stable `ErrorCode`. Callers select on the code, never on
the message text, so wording can change without breaking a policy decision.
"""

from __future__ import annotations

from collections import Counter

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.evidence import ObservationStatus, VerificationMethod
from ..models.wireless_connectivity import (
    AccessPointOwnership,
    AccessPointSelection,
    BLOCKED_CAPABILITY_STATUSES,
    BackendIdentity,
    NetworkAttachmentObservation,
    NetworkAttachmentState,
    ReadingProvenance,
    WirelessAssociationObservation,
    WirelessAssociationState,
    WirelessCapability,
    WirelessCapabilityAudit,
    WirelessCapabilityStatus,
    WirelessConnectivityPlan,
)


def validate_wireless_connectivity_plan(
    plan: WirelessConnectivityPlan,
) -> ValidationResult:
    """Refuse a plan that cannot be executed or that silently drops endpoints."""
    errors: list[PlanError] = []
    warnings: list[PlanError] = []

    for endpoint_id in plan.unclustered_endpoint_ids:
        errors.append(_error(
            ErrorCode.WIRELESS_ENDPOINT_UNSCOPED,
            f"The wireless endpoint {endpoint_id} is not placed deeply enough "
            f"for the {plan.scope.value} cluster scope.",
            device=endpoint_id,
            suggestion="Place the endpoint in the hierarchy or widen the cluster scope.",
        ))

    cluster_ids = Counter(cluster.cluster_id for cluster in plan.clusters)
    for cluster_id, count in sorted(cluster_ids.items()):
        if count > 1:
            errors.append(_error(
                ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                f"The cluster identity {cluster_id} is declared {count} times.",
                device=cluster_id,
            ))

    memberships = Counter(
        member.endpoint_id
        for cluster in plan.clusters
        for member in cluster.members
    )
    for endpoint_id, count in sorted(memberships.items()):
        if count > 1:
            errors.append(_error(
                ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                f"The endpoint {endpoint_id} belongs to {count} clusters.",
                device=endpoint_id,
                suggestion="One endpoint has exactly one wireless cluster membership.",
            ))

    for cluster in plan.clusters:
        if not cluster.segment.segment_id:
            errors.append(_error(
                ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                f"The cluster {cluster.cluster_id} has no intended network segment.",
                device=cluster.cluster_id,
            ))
        if not cluster.has_candidate:
            errors.append(_error(
                ErrorCode.WIRELESS_CLUSTER_WITHOUT_CANDIDATE,
                f"The cluster {cluster.cluster_id} has no candidate access point.",
                device=cluster.cluster_id,
                suggestion="Add an access point in the cluster scope or its site.",
            ))
        duplicated = [
            identity for identity, count
            in Counter(cluster.candidate_ids).items() if count > 1
        ]
        for identity in sorted(duplicated):
            errors.append(_error(
                ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                f"The access point {identity} is listed twice in "
                f"{cluster.cluster_id}.",
                device=cluster.cluster_id,
            ))
        for member in cluster.members:
            if member.cluster_id != cluster.cluster_id:
                errors.append(_error(
                    ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                    f"The member {member.endpoint_id} names the cluster "
                    f"{member.cluster_id} while it belongs to {cluster.cluster_id}.",
                    device=member.endpoint_id,
                ))
            if member.segment_id != cluster.segment.segment_id:
                errors.append(_error(
                    ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                    f"The member {member.endpoint_id} names the segment "
                    f"{member.segment_id} while its cluster intends "
                    f"{cluster.segment.segment_id}.",
                    device=member.endpoint_id,
                ))

    warnings.extend(_shared_candidate_warnings(plan))

    intents = {intent.endpoint_id: intent for intent in plan.association_intents}
    if len(intents) != len(plan.association_intents):
        errors.append(_error(
            ErrorCode.WIRELESS_PLAN_INCONSISTENT,
            "An endpoint carries more than one association intent.",
        ))
    for cluster in plan.clusters:
        for member in cluster.members:
            intent = intents.get(member.endpoint_id)
            if intent is None:
                errors.append(_error(
                    ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                    f"The member {member.endpoint_id} has no association intent.",
                    device=member.endpoint_id,
                ))
                continue
            if intent.cluster_id != cluster.cluster_id:
                errors.append(_error(
                    ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                    f"The association intent of {member.endpoint_id} names the "
                    f"cluster {intent.cluster_id}, not {cluster.cluster_id}.",
                    device=member.endpoint_id,
                ))
            if intent.selection is AccessPointSelection.BACKEND_SELECTED:
                if intent.pinned_access_point_id:
                    errors.append(_error(
                        ErrorCode.WIRELESS_SELECTION_INVALID,
                        f"The backend-selected intent of {member.endpoint_id} "
                        "cannot also pin an access point.",
                        device=member.endpoint_id,
                    ))
                if not intent.candidate_access_point_ids:
                    # The same fact as the cluster-level error, stated per
                    # endpoint, so one policy decision covers both.
                    errors.append(_error(
                        ErrorCode.WIRELESS_CLUSTER_WITHOUT_CANDIDATE,
                        f"The backend-selected intent of {member.endpoint_id} "
                        "carries no candidate access point.",
                        device=member.endpoint_id,
                    ))
            elif intent.selection is AccessPointSelection.PINNED:
                if intent.pinned_access_point_id not in cluster.candidate_ids:
                    errors.append(_error(
                        ErrorCode.WIRELESS_SELECTION_INVALID,
                        f"The intent of {member.endpoint_id} pins "
                        f"{intent.pinned_access_point_id!r}, which is not a "
                        f"candidate of {cluster.cluster_id}.",
                        device=member.endpoint_id,
                    ))
                elif len(cluster.candidate_ids) > 1:
                    warnings.append(_error(
                        ErrorCode.WIRELESS_SELECTION_INVALID,
                        f"The intent of {member.endpoint_id} pins one of "
                        f"{len(cluster.candidate_ids)} candidates; the backend "
                        "can no longer choose.",
                        device=member.endpoint_id,
                        suggestion="Pin only when the backend cannot decide.",
                    ))

    declared_functions = {item.endpoint_id for item in plan.iot_functions}
    for cluster in plan.clusters:
        for member in cluster.members:
            if member.endpoint_id not in declared_functions:
                errors.append(_error(
                    ErrorCode.WIRELESS_PLAN_INCONSISTENT,
                    f"The member {member.endpoint_id} has no IoT function "
                    "declaration.",
                    device=member.endpoint_id,
                ))

    return ValidationResult(errors=errors, warnings=warnings)


def validate_reading_provenance(
    provenance: ReadingProvenance,
    *,
    endpoint_id: str,
    expected: BackendIdentity,
) -> ValidationResult:
    """A reading from elsewhere is a contradiction, never a weaker answer."""
    if provenance is ReadingProvenance.MATCHED:
        return ValidationResult()
    reason = {
        ReadingProvenance.FOREIGN_ENDPOINT: "another endpoint",
        ReadingProvenance.FOREIGN_BACKEND: "another backend",
        ReadingProvenance.FOREIGN_BUILD: "another backend build",
    }[provenance]
    return ValidationResult(errors=[_error(
        ErrorCode.WIRELESS_READING_PROVENANCE_CONFLICT,
        f"The reading credited to {endpoint_id} on {expected} came from "
        f"{reason}.",
        device=endpoint_id,
        suggestion="Discard the reading; never re-attribute it to the expected subject.",
    )])


def validate_capability_audit_binding(
    audit: WirelessCapabilityAudit,
) -> ValidationResult:
    """An audit has to be about the build it claims to be about."""
    errors = [
        _error(
            ErrorCode.WIRELESS_BACKEND_AUTHORITY_CONFLICT,
            f"The audit for {audit.identity} contains a record that {conflict}.",
        )
        for conflict in audit.binding_conflicts()
    ]
    if not audit.backend or not audit.backend_version:
        errors.append(_error(
            ErrorCode.WIRELESS_BACKEND_AUTHORITY_CONFLICT,
            "A capability audit needs both a backend and an exact build.",
        ))
    return ValidationResult(errors=errors)


def validate_association_observation(
    observation: WirelessAssociationObservation,
    audit: WirelessCapabilityAudit,
) -> ValidationResult:
    """Refuse a state the evidence does not carry."""
    errors: list[PlanError] = []
    warnings: list[PlanError] = []
    subject = observation.endpoint_id

    if observation.state is WirelessAssociationState.ASSOCIATED:
        errors.extend(_fresh_direct_evidence_errors(
            observation.observation_status,
            observation.method,
            observation.fresh_evidence,
            subject=subject,
            claim="association",
        ))
        if not observation.backend_version:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"An observed association for {subject} has to name the exact "
                "backend build it was observed on.",
                device=subject,
            ))
        if observation.provenance is not ReadingProvenance.MATCHED:
            errors.append(_error(
                ErrorCode.WIRELESS_READING_PROVENANCE_CONFLICT,
                f"An observed association for {subject} cannot rest on a "
                f"{observation.provenance.value} reading.",
                device=subject,
            ))
    if observation.state is WirelessAssociationState.UNOBSERVABLE:
        capability = audit.status(
            WirelessCapability.ASSOCIATION_STATE_OBSERVATION, subject,
        )
        blocked = capability in BLOCKED_CAPABILITY_STATUSES
        if not observation.unavailable_reading and not blocked:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"An unobservable association for {subject} has to name the "
                "reading it stopped at, or an audited backend limit.",
                device=subject,
                suggestion="Record the interface member the read stopped at.",
            ))
        if observation.error_kind is not None:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"The association of {subject} is reported unobservable while "
                f"the read failed with {observation.error_kind.value}; a probe "
                "failure is not a statement about the backend.",
                device=subject,
            ))
    if observation.observed_access_point_id:
        identification = audit.status(
            WirelessCapability.ASSOCIATED_ACCESS_POINT_IDENTIFICATION, subject,
        )
        if identification is not WirelessCapabilityStatus.SUPPORTED:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"The observation of {subject} names the access point "
                f"{observation.observed_access_point_id!r} while access-point "
                f"identification is {identification.value} on {audit.identity}.",
                device=subject,
                suggestion="Leave the associated access point empty until a measured surface reports it.",
            ))
        if observation.state is not WirelessAssociationState.ASSOCIATED:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"The observation of {subject} names an access point without "
                "an observed association.",
                device=subject,
            ))
    if (
        observation.state is WirelessAssociationState.CONFIGURED
        and observation.observation_status is ObservationStatus.OBSERVED
    ):
        warnings.append(_error(
            ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
            f"The observation of {subject} reports a completed read but keeps "
            "the configured state; the reading answered nothing.",
            device=subject,
        ))
    return ValidationResult(errors=errors, warnings=warnings)


def validate_attachment_observation(
    observation: NetworkAttachmentObservation,
    audit: WirelessCapabilityAudit,
) -> ValidationResult:
    """Same contract on the addressing axis."""
    errors: list[PlanError] = []
    warnings: list[PlanError] = []
    subject = observation.endpoint_id

    if observation.state is NetworkAttachmentState.ATTACHED:
        errors.extend(_fresh_direct_evidence_errors(
            observation.observation_status,
            observation.method,
            observation.fresh_evidence,
            subject=subject,
            claim="network attachment",
        ))
        if not observation.ipv4:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"An attached endpoint {subject} has to carry the observed address.",
                device=subject,
            ))
        if observation.in_intended_segment is not True:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"The endpoint {subject} is reported attached without an address "
                "proven to be inside the intended segment.",
                device=subject,
            ))
        if observation.provenance is not ReadingProvenance.MATCHED:
            errors.append(_error(
                ErrorCode.WIRELESS_READING_PROVENANCE_CONFLICT,
                f"An observed attachment for {subject} cannot rest on a "
                f"{observation.provenance.value} reading.",
                device=subject,
            ))
    if observation.state is NetworkAttachmentState.UNOBSERVABLE:
        capability = audit.status(
            WirelessCapability.NETWORK_ATTACHMENT_OBSERVATION, subject,
        )
        blocked = capability in BLOCKED_CAPABILITY_STATUSES
        if not observation.unavailable_reading and not blocked:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"An unobservable attachment for {subject} has to name the "
                "reading it stopped at, or an audited backend limit.",
                device=subject,
            ))
        if observation.error_kind is not None:
            errors.append(_error(
                ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
                f"The attachment of {subject} is reported unobservable while "
                f"the read failed with {observation.error_kind.value}.",
                device=subject,
            ))
    if observation.ipv4 and not observation.interface:
        warnings.append(_error(
            ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
            f"The attachment observation of {subject} carries an address "
            "without the interface it was read from.",
            device=subject,
        ))
    return ValidationResult(errors=errors, warnings=warnings)


def _shared_candidate_warnings(plan: WirelessConnectivityPlan) -> list[PlanError]:
    """Say when a plan asks one access point to serve two service sets.

    Sharing is a statement about the plan, not about the backend: nothing here
    establishes that an access point can hold more than one service set or more
    than one segment. Until a measured audit says it can, the demand is worth
    naming.
    """
    service_sets: dict[str, set[tuple[str, str]]] = {}
    for cluster in plan.clusters:
        for candidate in cluster.candidates:
            if candidate.ownership is AccessPointOwnership.CLUSTER_OWNED:
                continue
            service_sets.setdefault(candidate.access_point_id, set()).add(
                (cluster.service_set.ssid, cluster.segment.segment_id),
            )
    return [
        _error(
            ErrorCode.WIRELESS_PLAN_INCONSISTENT,
            f"The access point {identity} is asked to serve {len(demands)} "
            "service set or segment combinations; no audited capability "
            "establishes that one access point can.",
            device=identity,
            suggestion="Measure multi-service-set support or split the clusters.",
        )
        for identity, demands in sorted(service_sets.items())
        if len(demands) > 1
    ]


def _fresh_direct_evidence_errors(
    observation_status: ObservationStatus,
    method: VerificationMethod,
    fresh_evidence: bool,
    *,
    subject: str,
    claim: str,
) -> list[PlanError]:
    errors: list[PlanError] = []
    if observation_status is not ObservationStatus.OBSERVED:
        errors.append(_error(
            ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
            f"A claimed {claim} for {subject} requires an observed reading, "
            f"not {observation_status.value}.",
            device=subject,
        ))
    if method is VerificationMethod.NONE:
        errors.append(_error(
            ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
            f"A claimed {claim} for {subject} requires a named verification method.",
            device=subject,
        ))
    if not fresh_evidence:
        errors.append(_error(
            ErrorCode.WIRELESS_EVIDENCE_INSUFFICIENT,
            f"A claimed {claim} for {subject} requires fresh evidence.",
            device=subject,
            suggestion="Re-read the state instead of reusing a stored answer.",
        ))
    return errors


def _error(
    code: ErrorCode, message: str, *, device: str = "", suggestion: str = "",
) -> PlanError:
    return PlanError(
        code=code,
        message=message,
        device=device,
        suggestion=(
            suggestion
            or "Keep the state at its evidenced level instead of promoting it."
        ),
    )
