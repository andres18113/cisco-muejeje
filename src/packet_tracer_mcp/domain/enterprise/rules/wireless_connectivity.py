"""Fail-closed validation for wireless connectivity plans and observations.

Two separate contracts. The plan validation asks whether the intent is
realizable at all; the observation validation asks whether a claimed state is
backed by the evidence it would need. Neither promotes anything: they return a
`ValidationResult` and the use case decides.
"""

from __future__ import annotations

from collections import Counter

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.evidence import ObservationStatus, VerificationMethod
from ..models.wireless_connectivity import (
    AccessPointSelection,
    NetworkAttachmentObservation,
    NetworkAttachmentState,
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
            f"The wireless endpoint {endpoint_id} is not placed deeply enough "
            f"for the {plan.scope.value} cluster scope.",
            device=endpoint_id,
            suggestion="Place the endpoint in the hierarchy or widen the cluster scope.",
        ))

    cluster_ids = Counter(cluster.cluster_id for cluster in plan.clusters)
    for cluster_id, count in sorted(cluster_ids.items()):
        if count > 1:
            errors.append(_error(
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
                f"The endpoint {endpoint_id} belongs to {count} clusters.",
                device=endpoint_id,
                suggestion="One endpoint has exactly one wireless cluster membership.",
            ))

    for cluster in plan.clusters:
        if not cluster.segment.segment_id:
            errors.append(_error(
                f"The cluster {cluster.cluster_id} has no intended network segment.",
                device=cluster.cluster_id,
            ))
        if not cluster.has_candidate:
            errors.append(_error(
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
                f"The access point {identity} is listed twice in "
                f"{cluster.cluster_id}.",
                device=cluster.cluster_id,
            ))
        for member in cluster.members:
            if member.cluster_id != cluster.cluster_id:
                errors.append(_error(
                    f"The member {member.endpoint_id} names the cluster "
                    f"{member.cluster_id} while it belongs to {cluster.cluster_id}.",
                    device=member.endpoint_id,
                ))
            if member.segment_id != cluster.segment.segment_id:
                errors.append(_error(
                    f"The member {member.endpoint_id} names the segment "
                    f"{member.segment_id} while its cluster intends "
                    f"{cluster.segment.segment_id}.",
                    device=member.endpoint_id,
                ))

    intents = {intent.endpoint_id: intent for intent in plan.association_intents}
    if len(intents) != len(plan.association_intents):
        errors.append(_error(
            "An endpoint carries more than one association intent.",
        ))
    for cluster in plan.clusters:
        for member in cluster.members:
            intent = intents.get(member.endpoint_id)
            if intent is None:
                errors.append(_error(
                    f"The member {member.endpoint_id} has no association intent.",
                    device=member.endpoint_id,
                ))
                continue
            if intent.cluster_id != cluster.cluster_id:
                errors.append(_error(
                    f"The association intent of {member.endpoint_id} names the "
                    f"cluster {intent.cluster_id}, not {cluster.cluster_id}.",
                    device=member.endpoint_id,
                ))
            if intent.selection is AccessPointSelection.BACKEND_SELECTED:
                if intent.pinned_access_point_id:
                    errors.append(_error(
                        f"The backend-selected intent of {member.endpoint_id} "
                        "cannot also pin an access point.",
                        device=member.endpoint_id,
                    ))
                if not intent.candidate_access_point_ids:
                    errors.append(_error(
                        f"The backend-selected intent of {member.endpoint_id} "
                        "carries no candidate access point.",
                        device=member.endpoint_id,
                    ))
            elif intent.selection is AccessPointSelection.PINNED:
                if intent.pinned_access_point_id not in cluster.candidate_ids:
                    errors.append(_error(
                        f"The intent of {member.endpoint_id} pins "
                        f"{intent.pinned_access_point_id!r}, which is not a "
                        f"candidate of {cluster.cluster_id}.",
                        device=member.endpoint_id,
                    ))
                elif len(cluster.candidate_ids) > 1:
                    warnings.append(_error(
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
                    f"The member {member.endpoint_id} has no IoT function "
                    "declaration.",
                    device=member.endpoint_id,
                ))

    return ValidationResult(errors=errors, warnings=warnings)


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
                f"An observed association for {subject} has to name the exact "
                "backend build it was observed on.",
                device=subject,
            ))
    if observation.state is WirelessAssociationState.FAILED:
        errors.extend(_fresh_direct_evidence_errors(
            observation.observation_status,
            observation.method,
            observation.fresh_evidence,
            subject=subject,
            claim="association failure",
        ))
    if observation.state is WirelessAssociationState.UNOBSERVABLE:
        capability = audit.status(
            WirelessCapability.ASSOCIATION_STATE_OBSERVATION, subject,
        )
        blocked = capability in {
            WirelessCapabilityStatus.UNSUPPORTED,
            WirelessCapabilityStatus.UNOBSERVABLE,
        }
        if not observation.unavailable_reading and not blocked:
            errors.append(_error(
                f"An unobservable association for {subject} has to name the "
                "reading it stopped at, or an audited backend limit.",
                device=subject,
                suggestion="Record the interface member the read stopped at.",
            ))
    if observation.observed_access_point_id:
        identification = audit.status(
            WirelessCapability.ASSOCIATED_ACCESS_POINT_IDENTIFICATION, subject,
        )
        if identification is not WirelessCapabilityStatus.SUPPORTED:
            errors.append(_error(
                f"The observation of {subject} names the access point "
                f"{observation.observed_access_point_id!r} while access-point "
                f"identification is {identification.value} on "
                f"{audit.backend} {audit.backend_version}.",
                device=subject,
                suggestion="Leave the associated access point empty until a surface reports it.",
            ))
        if observation.state is not WirelessAssociationState.ASSOCIATED:
            errors.append(_error(
                f"The observation of {subject} names an access point without "
                "an observed association.",
                device=subject,
            ))
    if (
        observation.state is WirelessAssociationState.CONFIGURED
        and observation.observation_status is ObservationStatus.OBSERVED
    ):
        warnings.append(_error(
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
                f"An attached endpoint {subject} has to carry the observed address.",
                device=subject,
            ))
        if observation.in_intended_segment is not True:
            errors.append(_error(
                f"The endpoint {subject} is reported attached without an address "
                "proven to be inside the intended segment.",
                device=subject,
            ))
    if observation.state is NetworkAttachmentState.UNOBSERVABLE:
        capability = audit.status(
            WirelessCapability.NETWORK_ATTACHMENT_OBSERVATION, subject,
        )
        blocked = capability in {
            WirelessCapabilityStatus.UNSUPPORTED,
            WirelessCapabilityStatus.UNOBSERVABLE,
        }
        if not observation.unavailable_reading and not blocked:
            errors.append(_error(
                f"An unobservable attachment for {subject} has to name the "
                "reading it stopped at, or an audited backend limit.",
                device=subject,
            ))
    if observation.ipv4 and not observation.interface:
        warnings.append(_error(
            f"The attachment observation of {subject} carries an address "
            "without the interface it was read from.",
            device=subject,
        ))
    return ValidationResult(errors=errors, warnings=warnings)


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
            f"A claimed {claim} for {subject} requires an observed reading, "
            f"not {observation_status.value}.",
            device=subject,
        ))
    if method is VerificationMethod.NONE:
        errors.append(_error(
            f"A claimed {claim} for {subject} requires a named verification method.",
            device=subject,
        ))
    if not fresh_evidence:
        errors.append(_error(
            f"A claimed {claim} for {subject} requires fresh evidence.",
            device=subject,
            suggestion="Re-read the state instead of reusing a stored answer.",
        ))
    return errors


def _error(message: str, *, device: str = "", suggestion: str = "") -> PlanError:
    return PlanError(
        code=ErrorCode.VALIDATION_ERROR,
        message=message,
        device=device,
        suggestion=(
            suggestion
            or "Keep the state at its evidenced level instead of promoting it."
        ),
    )
