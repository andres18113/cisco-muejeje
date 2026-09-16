"""IoT wireless connectivity: planning, orchestration and acceptance policy.

The same entry points serve a one-access-point lab and a multi-site enterprise.
What changes between them is the cluster scope and how many clusters come back,
never the contract.

Ordering is deliberate. Planning is offline and always runs; configuration only
runs when a caller asks for it and a backend is injected; observation only runs
after that and can never be skipped into a verified state. A run with no
backend ends at PLAN_ONLY, which is the honest ceiling for it.
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
from ...domain.enterprise.models.requirements import AddressingPreference
from ...domain.enterprise.models.segments import NetworkSegment, SegmentRole
from ...domain.enterprise.models.wireless_connectivity import (
    AddressingSource,
    IoTFunctionDeclaration,
    NetworkAttachmentObservation,
    NetworkAttachmentState,
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
)
from ...domain.enterprise.rules.wireless_connectivity import (
    validate_association_observation,
    validate_attachment_observation,
    validate_wireless_connectivity_plan,
)
from ...domain.enterprise.services.endpoint_expander import ExpandedEndpoint
from ...domain.enterprise.services.wireless_cluster_planner import (
    WirelessClusterPlanner,
)
from ...domain.models.errors import ValidationResult


_MODEL_METADATA_KEY = "physical_model"


class IoTConnectivityAdmission(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class IoTConnectivityClosure(str, Enum):
    """The highest thing a run is entitled to say about itself."""

    PLAN_ONLY = "plan_only"
    CONFIGURED_NOT_OBSERVED = "configured_not_observed"
    PARTIALLY_OBSERVED = "partially_observed"
    OBSERVED = "observed"
    UNOBSERVABLE_BACKEND = "unobservable_backend"


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
    reasons: list[str] = []
    warnings: list[str] = []
    results: list[WirelessEndpointConnectivityResult] = []

    plan_validation = validate_wireless_connectivity_plan(plan)
    reasons.extend(plan_validation.error_messages())
    warnings.extend(plan_validation.warning_messages())

    functions = {item.endpoint_id: item for item in plan.iot_functions}
    for cluster in plan.clusters:
        for member in cluster.members:
            intent = plan.intent_for(member.endpoint_id)
            if intent is None:
                # Already reported by the plan validation; nothing to observe.
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

            association_capability = audit.status(
                WirelessCapability.ASSOCIATION_STATE_OBSERVATION, subject,
            )
            attachment_capability = audit.status(
                WirelessCapability.NETWORK_ATTACHMENT_OBSERVATION, subject,
            )
            association = WirelessAssociationObservation(
                endpoint_id=member.endpoint_id,
                cluster_id=cluster.cluster_id,
                state=classify_association_state(
                    configured=outcome.applied,
                    reading=association_reading,
                    observation_capability=association_capability,
                ),
                observed_service_set=(
                    association_reading.service_set if association_reading else ""
                ),
                observed_access_point_id=_admissible_access_point(
                    association_reading, audit, subject,
                ),
                method=(
                    association_reading.method if association_reading
                    else VerificationMethod.NONE
                ),
                observation_status=_observation_status(association_reading),
                fresh_evidence=bool(
                    association_reading and association_reading.fresh
                ),
                backend=audit.backend,
                backend_version=audit.backend_version,
                unavailable_reading=(
                    association_reading.unavailable_reading
                    if association_reading else ""
                ),
                detail=association_reading.detail if association_reading else outcome.detail,
            )
            attachment = NetworkAttachmentObservation(
                endpoint_id=member.endpoint_id,
                cluster_id=cluster.cluster_id,
                segment_id=cluster.segment.segment_id,
                state=classify_attachment_state(
                    configured=outcome.applied,
                    reading=attachment_reading,
                    observation_capability=attachment_capability,
                    segment=cluster.segment,
                ),
                interface=attachment_reading.interface if attachment_reading else "",
                ipv4=attachment_reading.ipv4 if attachment_reading else "",
                netmask=attachment_reading.netmask if attachment_reading else "",
                addressing_source=_addressing_source(attachment_reading, member),
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
                backend=audit.backend,
                backend_version=audit.backend_version,
                unavailable_reading=(
                    attachment_reading.unavailable_reading
                    if attachment_reading else ""
                ),
                detail=attachment_reading.detail if attachment_reading else "",
            )

            association_validation = validate_association_observation(association, audit)
            attachment_validation = validate_attachment_observation(attachment, audit)
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
    closure = _closure(ordered, port is not None)
    admission = (
        IoTConnectivityAdmission.ACCEPTED
        if not reasons else IoTConnectivityAdmission.REJECTED
    )
    return IoTConnectivityQualification(
        results=ordered,
        admission=admission,
        closure=closure,
        backend=audit.backend,
        backend_version=audit.backend_version,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def _observation_status(reading) -> ObservationStatus:
    if reading is None:
        return ObservationStatus.NOT_ATTEMPTED
    if reading.unavailable_reading:
        return ObservationStatus.UNOBSERVABLE
    if not reading.attempted:
        return ObservationStatus.NOT_ATTEMPTED
    if not reading.fresh:
        return ObservationStatus.PROBE_FAILED
    return ObservationStatus.OBSERVED


def _addressing_source(reading, member) -> AddressingSource:
    if reading is not None and reading.dhcp_client_flag is True:
        return AddressingSource.DHCP_CLIENT_FLAG
    if reading is not None and reading.dhcp_client_flag is False:
        return AddressingSource.STATIC
    if member.addressing_preference is AddressingPreference.STATIC:
        return AddressingSource.STATIC
    return AddressingSource.UNKNOWN


def _admissible_access_point(reading, audit: WirelessCapabilityAudit, subject: str) -> str:
    """Drop an access-point identity the backend is not audited to report.

    Graphical or positional proximity is not an identification, so a reading
    that carries one without an audited surface is discarded here rather than
    surviving into evidence and failing validation later.
    """
    if reading is None or not reading.access_point_id:
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
) -> IoTConnectivityClosure:
    if not backend_present:
        return IoTConnectivityClosure.PLAN_ONLY
    states = {item.association_state for item in results}
    if states and states <= {WirelessAssociationState.UNOBSERVABLE}:
        return IoTConnectivityClosure.UNOBSERVABLE_BACKEND
    if states and states <= {WirelessAssociationState.ASSOCIATED}:
        return IoTConnectivityClosure.OBSERVED
    if WirelessAssociationState.ASSOCIATED in states:
        return IoTConnectivityClosure.PARTIALLY_OBSERVED
    if states <= {
        WirelessAssociationState.PLANNED, WirelessAssociationState.CONFIGURED,
    }:
        return IoTConnectivityClosure.CONFIGURED_NOT_OBSERVED
    return IoTConnectivityClosure.PARTIALLY_OBSERVED


def _demote_candidate_errors(validation: ValidationResult) -> ValidationResult:
    """Only the caller may accept a cluster with no candidate access point."""
    kept = [
        error for error in validation.errors
        if "no candidate access point" not in error.message
    ]
    moved = [
        error for error in validation.errors
        if "no candidate access point" in error.message
    ]
    return ValidationResult(errors=kept, warnings=[*validation.warnings, *moved])
