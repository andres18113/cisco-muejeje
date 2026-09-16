"""The refusals. Each of these is a way the contract could have been fooled.

Every test here fails on the version of this feature that shipped first, which
is the point: they pin the corrections rather than the implementation.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.packet_tracer_mcp.application.use_cases.plan_iot_connectivity import (
    IoTConnectivityAdmission,
    IoTConnectivityClosure,
    IoTConnectivityPolicy,
    _closure,
    plan_iot_connectivity,
    qualify_iot_connectivity,
)
from src.packet_tracer_mcp.domain.enterprise.models.evidence import (
    ObservationStatus,
    VerificationMethod,
)
from src.packet_tracer_mcp.domain.enterprise.models.requirements import (
    AddressingPreference,
)
from src.packet_tracer_mcp.domain.enterprise.models.roles import DeviceRole
from src.packet_tracer_mcp.domain.enterprise.models.wireless_connectivity import (
    AddressingSource,
    BackendErrorKind,
    IoTFunction,
    IoTFunctionDeclaration,
    NetworkAttachmentObservation,
    NetworkAttachmentState,
    ReadingProvenance,
    WirelessAssociationObservation,
    WirelessAssociationReading,
    WirelessAssociationState,
    WirelessAttachmentReading,
    WirelessCapability,
    WirelessCapabilityAssessment,
    WirelessCapabilityAudit,
    WirelessCapabilityStatus,
    WirelessConfigurationOutcome,
    WirelessEndpointConnectivityResult,
    WirelessParticipation,
    classify_association_state,
    classify_attachment_state,
    wireless_participation,
)
from src.packet_tracer_mcp.domain.models.errors import ErrorCode
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from src.packet_tracer_mcp.infrastructure.catalog.wireless_capabilities import (
    packet_tracer_wireless_capability_audit,
)
from src.packet_tracer_mcp.infrastructure.execution.packet_tracer_wireless_connectivity import (
    PacketTracerWirelessConnectivityAdapter,
    WirelessRuntimeEndpoint,
)
from tests.support.iot_connectivity_scenarios import (
    endpoint,
    medium_topology,
    segments_for,
    simple_topology,
)


BACKEND = "packet_tracer"
BUILD = "0.0.0-test"


def _audit(backend: str = BACKEND, build: str = BUILD, **statuses):
    return WirelessCapabilityAudit(
        backend=backend,
        backend_version=build,
        assessments=tuple(
            WirelessCapabilityAssessment(
                capability=WirelessCapability(capability),
                status=status,
                backend=backend,
                backend_version=build,
                surface="test",
            )
            for capability, status in statuses.items()
        ),
    )


class _CountingPort:
    """Counts every operation so a refusal can be proved side-effect free."""

    def __init__(self, audit, *, association=None, attachment=None):
        self._audit = audit
        self._association = association
        self._attachment = attachment
        self.calls: list[str] = []

    @property
    def backend(self) -> str:
        return self._audit.backend

    @property
    def backend_version(self) -> str:
        return self._audit.backend_version

    def capability_audit(self):
        return self._audit

    def configure_association(self, intent):
        self.calls.append("configure_association")
        return WirelessConfigurationOutcome(endpoint_id=intent.endpoint_id)

    def observe_association(self, intent):
        self.calls.append("observe_association")
        if self._association is None:
            return None
        return self._association(intent)

    def observe_attachment(self, intent, segment):
        self.calls.append("observe_attachment")
        if self._attachment is None:
            return None
        return self._attachment(intent, segment)


def _plan(segments=()):
    result = plan_iot_connectivity(medium_topology(), segments=segments)
    assert result.is_valid, result.validation.error_messages()
    return result.plan


# --- 1. fail-closed -------------------------------------------------------

def test_an_invalid_plan_reaches_no_backend_call_at_all():
    endpoints = [item for item in simple_topology() if item.wireless]
    invalid = plan_iot_connectivity(endpoints)
    assert not invalid.is_valid
    port = _CountingPort(_audit())

    qualification = qualify_iot_connectivity(
        invalid.plan, audit=_audit(), port=port, configure=True,
    )

    assert port.calls == []
    assert qualification.admission is IoTConnectivityAdmission.REJECTED
    assert qualification.closure is IoTConnectivityClosure.INADMISSIBLE
    assert qualification.results == ()
    assert qualification.backend_calls_attempted is False


def test_an_unscoped_endpoint_also_stops_the_run_before_the_backend():
    endpoints = simple_topology()
    endpoints.append(endpoint(DeviceRole.WEBCAM, 9, site_id="site/lab", zone_id=""))
    plan = plan_iot_connectivity(endpoints).plan
    port = _CountingPort(_audit())

    qualification = qualify_iot_connectivity(plan, audit=_audit(), port=port)

    assert port.calls == []
    assert qualification.closure is IoTConnectivityClosure.INADMISSIBLE


# --- 2. backend and audit authority --------------------------------------

def test_an_audit_for_another_build_is_refused_before_any_call():
    port = _CountingPort(_audit(build="9.9.9-other"))

    qualification = qualify_iot_connectivity(
        _plan(), audit=_audit(build=BUILD), port=port,
    )

    assert port.calls == []
    assert qualification.admission is IoTConnectivityAdmission.REJECTED
    assert any("backend identity" in reason for reason in qualification.reasons)


def test_an_audit_that_disagrees_with_the_backend_is_refused_before_any_call():
    authority = _audit(association_state_observation=WirelessCapabilityStatus.UNKNOWN)
    supplied = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
    )
    port = _CountingPort(authority)

    qualification = qualify_iot_connectivity(_plan(), audit=supplied, port=port)

    assert port.calls == []
    assert qualification.admission is IoTConnectivityAdmission.REJECTED
    assert any(
        "not the backend authority" in reason for reason in qualification.reasons
    )


def test_a_backend_whose_identity_contradicts_its_own_audit_is_refused():
    class _Inconsistent(_CountingPort):
        @property
        def backend_version(self) -> str:
            return "1.2.3-claimed"

    port = _Inconsistent(_audit())

    qualification = qualify_iot_connectivity(_plan(), audit=_audit(), port=port)

    assert port.calls == []
    assert any(
        "its capability audit is for" in reason for reason in qualification.reasons
    )


def test_an_audit_holding_a_record_from_another_build_is_refused():
    stray = WirelessCapabilityAudit(
        backend=BACKEND,
        backend_version=BUILD,
        assessments=(
            WirelessCapabilityAssessment(
                capability=WirelessCapability.ASSOCIATION_STATE_OBSERVATION,
                status=WirelessCapabilityStatus.SUPPORTED,
                backend=BACKEND,
                backend_version="8.0.0-elsewhere",
            ),
        ),
    )
    port = _CountingPort(stray)

    qualification = qualify_iot_connectivity(_plan(), audit=stray, port=port)

    assert port.calls == []
    assert any("is recorded for" in reason for reason in qualification.reasons)


# --- 3. reading provenance -----------------------------------------------

@pytest.mark.parametrize(
    "mutation, expected",
    [
        ({"endpoint_id": "endpoint/elsewhere/webcam/001"},
         ReadingProvenance.FOREIGN_ENDPOINT),
        ({"backend": "some_other_simulator"}, ReadingProvenance.FOREIGN_BACKEND),
        ({"backend_version": "7.7.7"}, ReadingProvenance.FOREIGN_BUILD),
    ],
)
def test_a_foreign_reading_is_never_promoted(mutation, expected):
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
    )

    def association(intent):
        return WirelessAssociationReading(**{
            "endpoint_id": intent.endpoint_id,
            "backend": BACKEND,
            "backend_version": BUILD,
            "attempted": True,
            "associated": True,
            "fresh": True,
            "method": VerificationMethod.DIRECT_STATE,
            **mutation,
        })

    port = _CountingPort(audit, association=association)
    qualification = qualify_iot_connectivity(_plan(), audit=audit, port=port)

    assert qualification.admission is IoTConnectivityAdmission.REJECTED
    assert qualification.closure is IoTConnectivityClosure.FAILED
    for item in qualification.results:
        assert item.association.provenance is expected
        assert item.association_state is WirelessAssociationState.FAILED
        assert item.association_state is not WirelessAssociationState.ASSOCIATED
    assert any(
        "never re-attribute" in reason or "came from" in reason
        for reason in qualification.reasons
    )


def test_a_reading_that_cannot_say_where_it_came_from_is_foreign():
    state = classify_association_state(
        configured=False,
        reading=WirelessAssociationReading(
            endpoint_id="e", attempted=True, associated=True, fresh=True,
            method=VerificationMethod.DIRECT_STATE,
        ),
        observation_capability=WirelessCapabilityStatus.SUPPORTED,
        provenance=ReadingProvenance.FOREIGN_BACKEND,
    )

    assert state is WirelessAssociationState.FAILED


def test_a_foreign_reading_cannot_carry_an_access_point_identity():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
        associated_access_point_identification=WirelessCapabilityStatus.SUPPORTED,
    )

    def association(intent):
        return WirelessAssociationReading(
            endpoint_id=intent.endpoint_id,
            backend=BACKEND,
            backend_version="7.7.7",
            attempted=True,
            associated=True,
            fresh=True,
            method=VerificationMethod.DIRECT_STATE,
            access_point_id="ap-from-another-build",
        )

    port = _CountingPort(audit, association=association)
    qualification = qualify_iot_connectivity(_plan(), audit=audit, port=port)

    assert all(
        item.association.observed_access_point_id == ""
        for item in qualification.results
    )


# --- 4 and 5. closure -----------------------------------------------------

def test_an_associated_member_with_a_failed_attachment_never_closes_observed():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
        network_attachment_observation=WirelessCapabilityStatus.SUPPORTED,
    )

    def association(intent):
        return WirelessAssociationReading(
            endpoint_id=intent.endpoint_id, backend=BACKEND, backend_version=BUILD,
            attempted=True, associated=True, fresh=True,
            method=VerificationMethod.DIRECT_STATE,
        )

    def attachment(intent, segment):
        return WirelessAttachmentReading(
            endpoint_id=intent.endpoint_id, backend=BACKEND, backend_version=BUILD,
            attempted=True, fresh=True, method=VerificationMethod.STRUCTURED_API,
            interface="Wireless0", ipv4="192.168.99.5",
        )

    port = _CountingPort(audit, association=association, attachment=attachment)
    qualification = qualify_iot_connectivity(
        _plan(segments_for("site/branch", "10.20.30.0/24", vlan_id=77)),
        audit=audit,
        port=port,
    )

    assert set(qualification.association_summary) == {
        WirelessAssociationState.ASSOCIATED.value,
    }
    assert set(qualification.attachment_summary) == {
        NetworkAttachmentState.FAILED.value,
    }
    assert qualification.closure is IoTConnectivityClosure.FAILED
    assert qualification.closure is not IoTConnectivityClosure.OBSERVED
    assert qualification.closure is not IoTConnectivityClosure.PARTIALLY_OBSERVED


def test_a_rejected_admission_can_never_close_observed():
    """Stated on the closure rule itself, so no guard upstream can hide it.

    Every reachable rejection today is caught before or during observation, so
    the integration paths cannot produce a fully observed rejected run. That is
    a property of the current guards, not of the closure, and the closure has
    to keep the rule on its own.
    """
    observed = _observed_results()

    accepted = _closure(observed, True, IoTConnectivityAdmission.ACCEPTED)
    rejected = _closure(observed, True, IoTConnectivityAdmission.REJECTED)

    assert accepted is IoTConnectivityClosure.OBSERVED
    assert rejected is not IoTConnectivityClosure.OBSERVED
    assert rejected is IoTConnectivityClosure.INADMISSIBLE


def test_a_rejected_policy_run_does_not_close_observed_end_to_end():
    qualification = qualify_iot_connectivity(
        _plan(),
        audit=_audit(),
        port=_CountingPort(_audit()),
        policy=IoTConnectivityPolicy(require_observed_association=True),
    )

    assert qualification.admission is IoTConnectivityAdmission.REJECTED
    assert qualification.closure is IoTConnectivityClosure.INADMISSIBLE
    assert qualification.closure is not IoTConnectivityClosure.OBSERVED


def _observed_results():
    """One member observed on both axes, built straight from the contract."""
    return (
        WirelessEndpointConnectivityResult(
            endpoint_id="e",
            cluster_id="c",
            association=WirelessAssociationObservation(
                endpoint_id="e",
                cluster_id="c",
                state=WirelessAssociationState.ASSOCIATED,
                method=VerificationMethod.DIRECT_STATE,
                observation_status=ObservationStatus.OBSERVED,
                fresh_evidence=True,
                backend=BACKEND,
                backend_version=BUILD,
            ),
            attachment=NetworkAttachmentObservation(
                endpoint_id="e",
                cluster_id="c",
                segment_id="s",
                state=NetworkAttachmentState.ATTACHED,
                interface="Wireless0",
                ipv4="10.20.30.44",
                in_intended_segment=True,
                method=VerificationMethod.STRUCTURED_API,
                observation_status=ObservationStatus.OBSERVED,
                fresh_evidence=True,
                backend=BACKEND,
                backend_version=BUILD,
            ),
            iot_function=IoTFunctionDeclaration(
                endpoint_id="e", function=IoTFunction.SMOKE_DETECTION,
            ),
        ),
    )


def test_an_accepted_fully_observed_run_still_closes_observed():
    """The guard must not make a genuinely clean run unreachable."""
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
        network_attachment_observation=WirelessCapabilityStatus.SUPPORTED,
    )

    def association(intent):
        return WirelessAssociationReading(
            endpoint_id=intent.endpoint_id, backend=BACKEND, backend_version=BUILD,
            attempted=True, associated=True, fresh=True,
            method=VerificationMethod.DIRECT_STATE,
        )

    def attachment(intent, segment):
        return WirelessAttachmentReading(
            endpoint_id=intent.endpoint_id, backend=BACKEND, backend_version=BUILD,
            attempted=True, fresh=True, method=VerificationMethod.STRUCTURED_API,
            interface="Wireless0", ipv4="10.20.30.44", netmask="255.255.255.0",
        )

    port = _CountingPort(audit, association=association, attachment=attachment)
    qualification = qualify_iot_connectivity(
        _plan(segments_for("site/branch", "10.20.30.0/24", vlan_id=77)),
        audit=audit,
        port=port,
        policy=IoTConnectivityPolicy(
            require_observed_association=True, require_observed_attachment=True,
        ),
    )

    assert qualification.admission is IoTConnectivityAdmission.ACCEPTED
    assert qualification.closure is IoTConnectivityClosure.OBSERVED


# --- 6. backend errors ----------------------------------------------------

def _laptop_adapter(transport):
    plan = _plan(segments_for("site/branch", "10.20.30.0/24", vlan_id=77))
    intent = plan.association_intents[0]
    adapter = PacketTracerWirelessConnectivityAdapter(
        lambda script, timeout: transport(script),
        {
            intent.endpoint_id: WirelessRuntimeEndpoint(
                endpoint_id=intent.endpoint_id,
                runtime_device_name="BRANCH-LAPTOP-01",
                model="Laptop-PT",
                interface="Wireless0",
            ),
        },
        packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    return adapter, plan, intent


def _raise(_script):
    raise ConnectionResetError("bridge closed")


@pytest.mark.parametrize(
    "transport, expected_kind",
    [
        (_raise, BackendErrorKind.TRANSPORT_EXCEPTION),
        (lambda script: None, BackendErrorKind.TRANSPORT_TIMEOUT),
        (lambda script: "ERROR: Invalid arguments for IPC call",
         BackendErrorKind.ENGINE_ERROR),
        (lambda script: "{not json", BackendErrorKind.PROTOCOL_ERROR),
        (lambda script: "[1, 2, 3]", BackendErrorKind.PROTOCOL_ERROR),
    ],
)
def test_a_backend_failure_is_named_and_is_never_unobservable(
    transport, expected_kind,
):
    adapter, plan, intent = _laptop_adapter(transport)
    cluster = plan.cluster(intent.cluster_id)

    reading = adapter.observe_attachment(intent, cluster.segment)

    assert reading.error_kind is expected_kind
    assert reading.error_stage, "a failure has to say where it happened"
    assert reading.detail, "a failure has to keep its cause"
    assert reading.unavailable_reading == ""

    state = classify_attachment_state(
        configured=True,
        reading=reading,
        observation_capability=WirelessCapabilityStatus.SUPPORTED,
        segment=cluster.segment,
    )
    assert state is NetworkAttachmentState.UNKNOWN
    assert state is not NetworkAttachmentState.UNOBSERVABLE


def test_a_failed_read_reports_a_probe_failure_not_an_absent_property():
    adapter, plan, intent = _laptop_adapter(_raise)
    audit = packet_tracer_wireless_capability_audit(MEASURED_BACKEND_VERSION)

    qualification = qualify_iot_connectivity(plan, audit=audit, port=adapter)

    failed = [
        item for item in qualification.results
        if item.endpoint_id == intent.endpoint_id
    ]
    assert failed
    for item in failed:
        assert item.attachment.error_kind is BackendErrorKind.TRANSPORT_EXCEPTION
        assert item.attachment.observation_status is ObservationStatus.PROBE_FAILED
        assert item.attachment_state is NetworkAttachmentState.UNKNOWN


def test_the_adapter_no_longer_swallows_exceptions():
    source = (
        "src/packet_tracer_mcp/infrastructure/execution/"
        "packet_tracer_wireless_connectivity.py"
    )
    with open(source, encoding="utf-8") as handle:
        text = handle.read()

    assert "except Exception:\n            return None" not in text
    assert "BackendErrorKind.TRANSPORT_EXCEPTION" in text
    assert "BackendErrorKind.ENGINE_ERROR" in text
    assert "BackendErrorKind.PROTOCOL_ERROR" in text


# --- 7. documented is not measured ---------------------------------------

def test_documented_packet_tracer_surfaces_are_never_treated_as_measured():
    audit = packet_tracer_wireless_capability_audit(MEASURED_BACKEND_VERSION)

    documented = [
        item.capability for item in audit.assessments
        if item.status is WirelessCapabilityStatus.DOCUMENTED
    ]
    assert WirelessCapability.ASSOCIATION_STATE_OBSERVATION in documented
    assert WirelessCapability.SERVICE_SET_CONFIGURATION in documented

    for capability in documented:
        state = classify_association_state(
            configured=True,
            reading=None,
            observation_capability=audit.status(capability),
        )
        assert state is WirelessAssociationState.CONFIGURED
        assert state is not WirelessAssociationState.ASSOCIATED
        assert state is not WirelessAssociationState.UNOBSERVABLE


# --- 8. DHCP disabled is not static --------------------------------------

def test_a_disabled_dhcp_client_is_not_a_static_assignment():
    audit = _audit(
        network_attachment_observation=WirelessCapabilityStatus.SUPPORTED,
    )

    def attachment(intent, segment):
        return WirelessAttachmentReading(
            endpoint_id=intent.endpoint_id, backend=BACKEND, backend_version=BUILD,
            attempted=True, fresh=True, method=VerificationMethod.STRUCTURED_API,
            interface="Wireless0", ipv4="10.20.30.44", netmask="255.255.255.0",
            dhcp_client_flag=False,
        )

    port = _CountingPort(audit, attachment=attachment)
    qualification = qualify_iot_connectivity(
        _plan(segments_for("site/branch", "10.20.30.0/24", vlan_id=77)),
        audit=audit,
        port=port,
    )

    for item in qualification.results:
        assert item.attachment.addressing_source is AddressingSource.DHCP_CLIENT_DISABLED
        assert item.attachment.addressing_source is not AddressingSource.STATIC


def test_a_static_addressing_intent_is_not_an_addressing_observation():
    endpoints = [
        endpoint(DeviceRole.ACCESS_POINT, 1, site_id="site/s", zone_id="zone/z"),
        endpoint(
            DeviceRole.WEBCAM, 1, site_id="site/s", zone_id="zone/z",
            addressing=AddressingPreference.STATIC,
        ),
    ]
    plan = plan_iot_connectivity(endpoints).plan

    qualification = qualify_iot_connectivity(plan, audit=_audit())

    for item in qualification.results:
        assert item.attachment.addressing_source is AddressingSource.UNKNOWN


# --- 9. infrastructure never becomes a client ----------------------------

def test_a_wireless_infrastructure_endpoint_does_not_become_a_client():
    endpoints = simple_topology()
    bridge = endpoint(
        DeviceRole.LAPTOP, 5, site_id="site/lab", zone_id="zone/lab-floor",
        metadata={"infrastructure_class": "wireless_bridge"},
    )
    assert bridge.wireless is True
    endpoints.append(bridge)

    result = plan_iot_connectivity(endpoints)

    members = {
        member.endpoint_id
        for cluster in result.plan.clusters
        for member in cluster.members
    }
    candidates = {
        candidate.access_point_id
        for cluster in result.plan.clusters
        for candidate in cluster.candidates
    }
    assert bridge.id not in members
    assert bridge.id in candidates
    assert result.plan.unclustered_endpoint_ids == ()


def test_an_endpoint_may_declare_its_own_part_explicitly():
    excluded = endpoint(
        DeviceRole.WEBCAM, 3, site_id="site/lab", zone_id="zone/lab-floor",
        metadata={"wireless_participation": "excluded"},
    )
    endpoints = [*simple_topology(), excluded]

    result = plan_iot_connectivity(endpoints)

    members = {
        member.endpoint_id
        for cluster in result.plan.clusters
        for member in cluster.members
    }
    assert excluded.id not in members
    assert excluded.id not in result.plan.unclustered_endpoint_ids


def test_an_unreadable_participation_declaration_is_not_guessed():
    assert wireless_participation(
        DeviceRole.WEBCAM, wireless=True, metadata={"wireless_participation": "maybe"},
    ) is WirelessParticipation.EXCLUDED


def test_a_plain_iot_role_still_joins_without_any_declaration():
    assert wireless_participation(
        DeviceRole.TEMPERATURE_MONITOR, wireless=True,
    ) is WirelessParticipation.CLIENT


# --- 10. candidate policy selects on a code, not on wording --------------

def test_the_missing_candidate_policy_never_parses_an_error_message():
    endpoints = [item for item in simple_topology() if item.wireless]

    refused = plan_iot_connectivity(endpoints)
    accepted = plan_iot_connectivity(
        endpoints,
        policy=IoTConnectivityPolicy(require_candidate_access_point=False),
    )

    assert not refused.is_valid
    assert {error.code for error in refused.validation.errors} == {
        ErrorCode.WIRELESS_CLUSTER_WITHOUT_CANDIDATE,
    }
    assert accepted.is_valid
    assert {warning.code for warning in accepted.validation.warnings} == {
        ErrorCode.WIRELESS_CLUSTER_WITHOUT_CANDIDATE,
    }


def test_rewording_the_candidate_error_does_not_change_the_policy():
    """The policy has to survive a message change, so prove it on the code."""
    endpoints = [item for item in simple_topology() if item.wireless]
    original = plan_iot_connectivity(endpoints).validation

    reworded = [
        replace(error, message="completely different wording")
        for error in original.errors
    ]
    for error in reworded:
        assert error.code is ErrorCode.WIRELESS_CLUSTER_WITHOUT_CANDIDATE

    from src.packet_tracer_mcp.application.use_cases.plan_iot_connectivity import (
        _demote_candidate_errors,
    )
    from src.packet_tracer_mcp.domain.models.errors import ValidationResult

    demoted = _demote_candidate_errors(ValidationResult(errors=reworded))

    assert demoted.is_valid
    assert len(demoted.warnings) == len(reworded)


# --- shared access points claim no backend capability --------------------

def test_a_shared_access_point_is_not_a_multi_service_set_capability_claim():
    from tests.support.iot_connectivity_scenarios import advanced_topology
    from src.packet_tracer_mcp.domain.enterprise.models.segments import SegmentRole
    from src.packet_tracer_mcp.domain.enterprise.models.wireless_connectivity import (
        WirelessServiceSetIntent,
    )

    result = plan_iot_connectivity(
        advanced_topology(),
        policy=IoTConnectivityPolicy(
            service_sets={SegmentRole.CCTV: WirelessServiceSetIntent(ssid="iot")},
        ),
    )

    assert result.is_valid, result.validation.error_messages()
    assert any(
        "no audited capability establishes" in warning.message
        for warning in result.validation.warnings
    ), "sharing an access point across service sets has to be flagged, not assumed"
