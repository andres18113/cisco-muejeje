"""IoT wireless connectivity: planning, orchestration and acceptance policy.

The same entry points serve a one-access-point lab and a multi-site enterprise.
What changes between them is the cluster scope and how many clusters come back,
never the contract.

Ordering is deliberate and fail-closed. Nothing touches a backend until the
plan validates and the backend authority is settled: an invalid plan or an
audit that does not belong to the port ends the run before the first call.
Configuration only runs when a caller asks for it; observation only after that,
and it can never be skipped into a verified state. A run with no backend ends
at PLAN_ONLY, which is the honest ceiling for it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from ..ports.wireless_connectivity import WirelessConnectivityPort
from ...domain.enterprise.models.evidence import (
    ObservationStatus,
    VerificationMethod,
)
from ...domain.enterprise.models.segments import NetworkSegment, SegmentRole
from ...domain.enterprise.models.wireless_connectivity import (
    AddressingSource,
    BackendIdentity,
    IoTFunctionDeclaration,
    NetworkAttachmentObservation,
    NetworkAttachmentState,
    ReadingProvenance,
    WirelessAssociationObservation,
    WirelessAssociationState,
    WirelessCapability,
    WirelessCapabilityAudit,
    WirelessCapabilityStatus,
    WirelessClusterScope,
    WirelessConfigurationOutcome,
    WirelessConnectivityPlan,
    WirelessEndpointConnectivityResult,
    WirelessServiceSetIntent,
    classify_association_state,
    classify_attachment_state,
    reading_provenance,
)
from ...domain.enterprise.rules.wireless_connectivity import (
    validate_association_observation,
    validate_attachment_observation,
    validate_capability_audit_binding,
    validate_reading_provenance,
    validate_wireless_connectivity_plan,
)
from ...domain.enterprise.services.endpoint_expander import ExpandedEndpoint
from ...domain.enterprise.services.wireless_cluster_planner import (
    WirelessClusterPlanner,
)
from ...domain.models.errors import ErrorCode, ValidationResult


_MODEL_METADATA_KEY = "physical_model"


class IoTConnectivityAdmission(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class IoTConnectivityClosure(str, Enum):
    """The highest thing a run is entitled to say about itself."""

    PLAN_ONLY = "plan_only"
    INADMISSIBLE = "inadmissible"
    CONFIGURED_NOT_OBSERVED = "configured_not_observed"
    PARTIALLY_OBSERVED = "partially_observed"
    UNOBSERVABLE_BACKEND = "unobservable_backend"
    FAILED = "failed"
    OBSERVED = "observed"


@dataclass(frozen=True)
class IoTConnectivityPolicy:
    """Every knob a topology size needs, with no name or count baked in."""

    scope: WirelessClusterScope = WirelessClusterScope.ZONE
    service_set: WirelessServiceSetIntent = WirelessServiceSetIntent()
    service_sets: Mapping[SegmentRole, WirelessServiceSetIntent] = field(
        default_factory=dict,
    )
    pinned_access_points: Mapping[str, str] = field(default_factory=dict)
    require_candidate_access_point: bool = True
    require_observed_association: bool = False
    require_observed_attachment: bool = False


@dataclass(frozen=True)
class IoTConnectivityPlanResult:
    plan: WirelessConnectivityPlan
    validation: ValidationResult

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid


@dataclass(frozen=True)
class IoTConnectivityQualification:
    """One run across every member, with the evidence each state came from."""

    results: tuple[WirelessEndpointConnectivityResult, ...]
    admission: IoTConnectivityAdmission
    closure: IoTConnectivityClosure
    backend: str = ""
    backend_version: str = ""
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    backend_calls_attempted: bool = False

    @property
    def association_summary(self) -> Mapping[str, int]:
        return dict(sorted(
            Counter(item.association_state.value for item in self.results).items()
        ))

    @property
    def attachment_summary(self) -> Mapping[str, int]:
        return dict(sorted(
            Counter(item.attachment_state.value for item in self.results).items()
        ))

    @property
    def iot_function_summary(self) -> Mapping[str, int]:
        return dict(sorted(
            Counter(item.iot_function.function.value for item in self.results).items()
        ))


def plan_iot_connectivity(
    endpoints: Sequence[ExpandedEndpoint],
    *,
    segments: Sequence[NetworkSegment] = (),
    policy: IoTConnectivityPolicy | None = None,
    planner: WirelessClusterPlanner | None = None,
) -> IoTConnectivityPlanResult:
    """Derive the clusters and validate them. Entirely offline."""
    active = policy or IoTConnectivityPolicy()
    plan = (planner or WirelessClusterPlanner()).plan(
        endpoints,
        scope=active.scope,
        segments=segments,
        service_set=active.service_set,
        service_sets=active.service_sets,
        pinned_access_points=active.pinned_access_points,
    )
    validation = validate_wireless_connectivity_plan(plan)
    if not active.require_candidate_access_point:
        validation = _demote_candidate_errors(validation)
    return IoTConnectivityPlanResult(plan=plan, validation=validation)


def qualify_iot_connectivity(
    plan: WirelessConnectivityPlan,
    *,
    audit: WirelessCapabilityAudit,
    port: WirelessConnectivityPort | None = None,
    policy: IoTConnectivityPolicy | None = None,
    configure: bool = False,
) -> IoTConnectivityQualification:
    """Walk every member once, keeping each axis on its own evidence."""
    active = policy or IoTConnectivityPolicy()

    refusal = _admission_refusals(plan, audit=audit, port=port, policy=active)
    if refusal:
        # Nothing has touched the backend yet, and nothing will: a run that
        # cannot state its own contract must not start producing evidence.
        return IoTConnectivityQualification(
            results=(),
            admission=IoTConnectivityAdmission.REJECTED,
            closure=IoTConnectivityClosure.INADMISSIBLE,
            backend=audit.backend,
            backend_version=audit.backend_version,
            reasons=tuple(refusal),
            backend_calls_attempted=False,
        )

    authority = port.capability_audit() if port is not None else audit
    identity = authority.identity
    reasons: list[str] = []
    warnings: list[str] = []
    results: list[WirelessEndpointConnectivityResult] = []
    warnings.extend(validate_wireless_connectivity_plan(plan).warning_messages())

    functions = {item.endpoint_id: item for item in plan.iot_functions}
    for cluster in plan.clusters:
        for member in cluster.members:
            intent = plan.intent_for(member.endpoint_id)
            if intent is None:
                continue
            subject = str(member.metadata.get(_MODEL_METADATA_KEY, ""))
            outcome = (
                port.configure_association(intent)
                if port is not None and configure
                else WirelessConfigurationOutcome(endpoint_id=member.endpoint_id)
            )
            association_reading = (
                port.observe_association(intent) if port is not None else None
            )
            attachment_reading = (
                port.observe_attachment(intent, cluster.segment)
                if port is not None else None
            )
            association_provenance = _provenance(
                association_reading, member.endpoint_id, identity,
            )
            attachment_provenance = _provenance(
                attachment_reading, member.endpoint_id, identity,
            )
            for provenance in (association_provenance, attachment_provenance):
                reasons.extend(validate_reading_provenance(
                    provenance, endpoint_id=member.endpoint_id, expected=identity,
                ).error_messages())

            association = WirelessAssociationObservation(
                endpoint_id=member.endpoint_id,
                cluster_id=cluster.cluster_id,
                state=classify_association_state(
                    configured=outcome.applied,
                    reading=association_reading,
                    observation_capability=authority.status(
                        WirelessCapability.ASSOCIATION_STATE_OBSERVATION, subject,
                    ),
                    provenance=association_provenance,
                ),
                observed_service_set=(
                    association_reading.service_set if association_reading else ""
                ),
                observed_access_point_id=_admissible_access_point(
                    association_reading, authority, subject, association_provenance,
                ),
                method=(
                    association_reading.method if association_reading
                    else VerificationMethod.NONE
                ),
                observation_status=_observation_status(association_reading),
                fresh_evidence=bool(
                    association_reading and association_reading.fresh
                ),
                backend=identity.backend,
                backend_version=identity.backend_version,
                unavailable_reading=(
                    association_reading.unavailable_reading
                    if association_reading else ""
                ),
                error_kind=(
                    association_reading.error_kind if association_reading else None
                ),
                error_stage=(
                    association_reading.error_stage if association_reading else ""
                ),
                provenance=association_provenance,
                detail=(
                    association_reading.detail if association_reading
                    else outcome.detail
                ),
            )
            attachment = NetworkAttachmentObservation(
                endpoint_id=member.endpoint_id,
                cluster_id=cluster.cluster_id,
                segment_id=cluster.segment.segment_id,
                state=classify_attachment_state(
                    configured=outcome.applied,
                    reading=attachment_reading,
                    observation_capability=authority.status(
                        WirelessCapability.NETWORK_ATTACHMENT_OBSERVATION, subject,
                    ),
                    segment=cluster.segment,
                    provenance=attachment_provenance,
                ),
                interface=attachment_reading.interface if attachment_reading else "",
                ipv4=attachment_reading.ipv4 if attachment_reading else "",
                netmask=attachment_reading.netmask if attachment_reading else "",
                addressing_source=_addressing_source(attachment_reading),
                in_intended_segment=(
                    cluster.segment.contains(attachment_reading.ipv4)
                    if attachment_reading and attachment_reading.ipv4 else None
                ),
                method=(
                    attachment_reading.method if attachment_reading
                    else VerificationMethod.NONE
                ),
                observation_status=_observation_status(attachment_reading),
                fresh_evidence=bool(attachment_reading and attachment_reading.fresh),
                backend=identity.backend,
                backend_version=identity.backend_version,
                unavailable_reading=(
                    attachment_reading.unavailable_reading
                    if attachment_reading else ""
                ),
                error_kind=(
                    attachment_reading.error_kind if attachment_reading else None
                ),
                error_stage=(
                    attachment_reading.error_stage if attachment_reading else ""
                ),
                provenance=attachment_provenance,
                detail=attachment_reading.detail if attachment_reading else "",
            )

            association_validation = validate_association_observation(
                association, authority,
            )
            attachment_validation = validate_attachment_observation(
                attachment, authority,
            )
            reasons.extend(association_validation.error_messages())
            reasons.extend(attachment_validation.error_messages())
            warnings.extend(association_validation.warning_messages())
            warnings.extend(attachment_validation.warning_messages())

            results.append(WirelessEndpointConnectivityResult(
                endpoint_id=member.endpoint_id,
                cluster_id=cluster.cluster_id,
                association=association,
                attachment=attachment,
                iot_function=functions.get(
                    member.endpoint_id,
                    IoTFunctionDeclaration(
                        endpoint_id=member.endpoint_id,
                        function=member.iot_function,
                    ),
                ),
            ))

    ordered = tuple(sorted(results, key=lambda item: item.endpoint_id))
    reasons.extend(_unmet_policy_reasons(ordered, active))
    admission = (
        IoTConnectivityAdmission.ACCEPTED
        if not reasons else IoTConnectivityAdmission.REJECTED
    )
    return IoTConnectivityQualification(
        results=ordered,
        admission=admission,
        closure=_closure(ordered, port is not None, admission),
        backend=identity.backend,
        backend_version=identity.backend_version,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        backend_calls_attempted=port is not None,
    )


def _admission_refusals(
    plan: WirelessConnectivityPlan,
    *,
    audit: WirelessCapabilityAudit,
    port: WirelessConnectivityPort | None,
    policy: IoTConnectivityPolicy,
) -> list[str]:
    """Everything that has to hold before the first backend call.

    Checked in one place and before any operation, so a refusal is provably
    free of side effects rather than merely recorded after the fact. Reading
    the port identity and its audit is metadata, not an operation on a
    workspace.
    """
    plan_validation = validate_wireless_connectivity_plan(plan)
    if not policy.require_candidate_access_point:
        plan_validation = _demote_candidate_errors(plan_validation)
    refusals = list(plan_validation.error_messages())
    refusals.extend(validate_capability_audit_binding(audit).error_messages())
    if port is None:
        return refusals

    authority = port.capability_audit()
    refusals.extend(validate_capability_audit_binding(authority).error_messages())
    if (port.backend, port.backend_version) != (
        authority.backend, authority.backend_version,
    ):
        refusals.append(
            f"The backend reports {port.backend} {port.backend_version} while "
            f"its capability audit is for {authority.identity}."
        )
    refusals.extend(
        f"The supplied capability audit is not the backend authority: {conflict}."
        for conflict in authority.equivalence_conflicts(audit)
    )
    return refusals


def _provenance(
    reading, endpoint_id: str, identity: BackendIdentity,
) -> ReadingProvenance:
    if reading is None:
        return ReadingProvenance.MATCHED
    return reading_provenance(
        endpoint_id=endpoint_id,
        reading_endpoint_id=reading.endpoint_id,
        expected=identity,
        reading_backend=reading.backend,
        reading_backend_version=reading.backend_version,
    )


def _observation_status(reading) -> ObservationStatus:
    if reading is None:
        return ObservationStatus.NOT_ATTEMPTED
    if reading.error_kind is not None:
        return ObservationStatus.PROBE_FAILED
    if reading.unavailable_reading:
        return ObservationStatus.UNOBSERVABLE
    if not reading.attempted:
        return ObservationStatus.NOT_ATTEMPTED
    if not reading.fresh:
        return ObservationStatus.PROBE_FAILED
    return ObservationStatus.OBSERVED


def _addressing_source(reading) -> AddressingSource:
    """Only what was observed. An intent is not an observation.

    A DHCP client flag that is off says the port does not ask for a lease. It
    does not say an address was assigned by hand, so it never becomes STATIC.
    """
    if reading is None or reading.dhcp_client_flag is None:
        return AddressingSource.UNKNOWN
    return (
        AddressingSource.DHCP_CLIENT_ENABLED
        if reading.dhcp_client_flag else AddressingSource.DHCP_CLIENT_DISABLED
    )


def _admissible_access_point(
    reading,
    audit: WirelessCapabilityAudit,
    subject: str,
    provenance: ReadingProvenance,
) -> str:
    """Drop an access-point identity the backend is not audited to report.

    Graphical or positional proximity is not an identification, and neither is
    a reference manual: only a measured SUPPORTED surface admits one here.
    """
    if reading is None or not reading.access_point_id:
        return ""
    if provenance is not ReadingProvenance.MATCHED:
        return ""
    identification = audit.status(
        WirelessCapability.ASSOCIATED_ACCESS_POINT_IDENTIFICATION, subject,
    )
    if identification is not WirelessCapabilityStatus.SUPPORTED:
        return ""
    return reading.access_point_id


def _unmet_policy_reasons(
    results: Sequence[WirelessEndpointConnectivityResult],
    policy: IoTConnectivityPolicy,
) -> list[str]:
    reasons: list[str] = []
    if policy.require_observed_association:
        missing = [
            item.endpoint_id for item in results
            if item.association_state is not WirelessAssociationState.ASSOCIATED
        ]
        if missing:
            reasons.append(
                "The policy requires an observed association for every member; "
                f"{len(missing)} member(s) did not reach it."
            )
    if policy.require_observed_attachment:
        missing = [
            item.endpoint_id for item in results
            if item.attachment_state is not NetworkAttachmentState.ATTACHED
        ]
        if missing:
            reasons.append(
                "The policy requires an observed network attachment for every "
                f"member; {len(missing)} member(s) did not reach it."
            )
    return reasons


def _closure(
    results: Sequence[WirelessEndpointConnectivityResult],
    backend_present: bool,
    admission: IoTConnectivityAdmission,
) -> IoTConnectivityClosure:
    """The closure answers for both axes and for the admission together.

    A fresh contradiction on either axis closes the run FAILED rather than
    dissolving into a partial result, and OBSERVED needs every required
    dimension observed on a run that was accepted.
    """
    if not backend_present:
        return IoTConnectivityClosure.PLAN_ONLY
    association = {item.association_state for item in results}
    attachment = {item.attachment_state for item in results}
    if (
        WirelessAssociationState.FAILED in association
        or NetworkAttachmentState.FAILED in attachment
    ):
        return IoTConnectivityClosure.FAILED
    fully_observed = bool(results) and (
        association <= {WirelessAssociationState.ASSOCIATED}
        and attachment <= {NetworkAttachmentState.ATTACHED}
    )
    if fully_observed:
        return (
            IoTConnectivityClosure.OBSERVED
            if admission is IoTConnectivityAdmission.ACCEPTED
            else IoTConnectivityClosure.INADMISSIBLE
        )
    if admission is not IoTConnectivityAdmission.ACCEPTED:
        return IoTConnectivityClosure.INADMISSIBLE
    if bool(results) and (
        association <= {WirelessAssociationState.UNOBSERVABLE}
        and attachment <= {NetworkAttachmentState.UNOBSERVABLE}
    ):
        return IoTConnectivityClosure.UNOBSERVABLE_BACKEND
    if (
        WirelessAssociationState.ASSOCIATED in association
        or NetworkAttachmentState.ATTACHED in attachment
    ):
        return IoTConnectivityClosure.PARTIALLY_OBSERVED
    if (
        association <= {
            WirelessAssociationState.PLANNED, WirelessAssociationState.CONFIGURED,
        }
        and attachment <= {
            NetworkAttachmentState.PLANNED, NetworkAttachmentState.CONFIGURED,
        }
    ):
        return IoTConnectivityClosure.CONFIGURED_NOT_OBSERVED
    return IoTConnectivityClosure.PARTIALLY_OBSERVED


def _demote_candidate_errors(validation: ValidationResult) -> ValidationResult:
    """Only the caller may accept a cluster with no candidate access point.

    Selection is by error code. Matching on the message would make the wording
    of an error part of the policy contract.
    """
    kept = [
        error for error in validation.errors
        if error.code is not ErrorCode.WIRELESS_CLUSTER_WITHOUT_CANDIDATE
    ]
    moved = [
        error for error in validation.errors
        if error.code is ErrorCode.WIRELESS_CLUSTER_WITHOUT_CANDIDATE
    ]
    return ValidationResult(errors=kept, warnings=[*validation.warnings, *moved])
