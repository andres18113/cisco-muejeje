"""States have to carry the evidence they claim.

The interesting cases are the ones where something is missing: a backend that
applied configuration and nothing else, a reading that stopped somewhere, a
capability nobody ever measured. Each of those has exactly one honest answer
and the contract has to produce it rather than rounding up.
"""

from __future__ import annotations

import pytest

from src.packet_tracer_mcp.application.use_cases.plan_iot_connectivity import (
    IoTConnectivityAdmission,
    IoTConnectivityClosure,
    IoTConnectivityPolicy,
    plan_iot_connectivity,
    qualify_iot_connectivity,
)
from src.packet_tracer_mcp.domain.enterprise.models.evidence import (
    ObservationStatus,
    VerificationMethod,
)
from src.packet_tracer_mcp.domain.enterprise.models.wireless_connectivity import (
    AddressingSource,
    IoTFunction,
    NetworkAttachmentState,
    WirelessAssociationObservation,
    WirelessAssociationReading,
    WirelessAssociationState,
    WirelessAttachmentReading,
    WirelessCapability,
    WirelessCapabilityAssessment,
    WirelessCapabilityAudit,
    WirelessCapabilityStatus,
    WirelessConfigurationOutcome,
    WirelessConfigurationStatus,
    classify_association_state,
    classify_attachment_state,
)
from src.packet_tracer_mcp.domain.enterprise.rules.wireless_connectivity import (
    validate_association_observation,
)
from tests.support.iot_connectivity_scenarios import medium_topology, segments_for


BACKEND = "packet_tracer"
BUILD = "0.0.0-test"


def _audit(**statuses) -> WirelessCapabilityAudit:
    return WirelessCapabilityAudit(
        backend=BACKEND,
        backend_version=BUILD,
        assessments=tuple(
            WirelessCapabilityAssessment(
                capability=WirelessCapability(capability),
                status=status,
                backend=BACKEND,
                backend_version=BUILD,
                surface="test",
            )
            for capability, status in statuses.items()
        ),
    )


class _StubPort:
    """A backend that answers exactly what a test hands it."""

    def __init__(self, audit, *, association=None, attachment=None, outcome=None):
        self._audit = audit
        self._association = association
        self._attachment = attachment
        self._outcome = outcome

    @property
    def backend(self) -> str:
        return self._audit.backend

    @property
    def backend_version(self) -> str:
        return self._audit.backend_version

    def capability_audit(self):
        return self._audit

    def configure_association(self, intent):
        if self._outcome is None:
            return WirelessConfigurationOutcome(endpoint_id=intent.endpoint_id)
        return WirelessConfigurationOutcome(
            endpoint_id=intent.endpoint_id, **self._outcome,
        )

    def observe_association(self, intent):
        if self._association is None:
            return None
        return WirelessAssociationReading(
            endpoint_id=intent.endpoint_id,
            backend=BACKEND,
            backend_version=BUILD,
            **self._association,
        )

    def observe_attachment(self, intent, segment):
        if self._attachment is None:
            return None
        return WirelessAttachmentReading(
            endpoint_id=intent.endpoint_id,
            backend=BACKEND,
            backend_version=BUILD,
            **self._attachment,
        )


def _plan(segments=()):
    result = plan_iot_connectivity(medium_topology(), segments=segments)
    assert result.is_valid, result.validation.error_messages()
    return result.plan


def test_a_run_without_a_backend_stays_planned():
    qualification = qualify_iot_connectivity(_plan(), audit=_audit())

    assert qualification.closure is IoTConnectivityClosure.PLAN_ONLY
    assert qualification.admission is IoTConnectivityAdmission.ACCEPTED
    assert set(qualification.association_summary) == {
        WirelessAssociationState.PLANNED.value,
    }


def test_applied_configuration_never_becomes_a_verified_association():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.UNKNOWN,
        network_attachment_observation=WirelessCapabilityStatus.UNKNOWN,
    )
    port = _StubPort(
        audit,
        outcome={"status": WirelessConfigurationStatus.APPLIED, "surface": "test"},
    )

    qualification = qualify_iot_connectivity(
        _plan(), audit=audit, port=port, configure=True,
    )

    assert set(qualification.association_summary) == {
        WirelessAssociationState.CONFIGURED.value,
    }
    assert qualification.closure is IoTConnectivityClosure.CONFIGURED_NOT_OBSERVED
    assert all(
        item.association.observation_status is ObservationStatus.NOT_ATTEMPTED
        for item in qualification.results
    )


def test_a_reading_that_stopped_somewhere_is_unobservable_not_failed():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.UNKNOWN,
        network_attachment_observation=WirelessCapabilityStatus.UNKNOWN,
    )
    port = _StubPort(
        audit,
        association={"attempted": True, "unavailable_reading": "Port.isAssociated"},
        attachment={"attempted": True, "unavailable_reading": "Port.getIpAddress"},
    )

    qualification = qualify_iot_connectivity(_plan(), audit=audit, port=port)

    assert qualification.closure is IoTConnectivityClosure.UNOBSERVABLE_BACKEND
    for item in qualification.results:
        assert item.association_state is WirelessAssociationState.UNOBSERVABLE
        assert item.attachment_state is NetworkAttachmentState.UNOBSERVABLE
        assert item.association.unavailable_reading == "Port.isAssociated"
        assert item.association.observation_status is ObservationStatus.UNOBSERVABLE


def test_an_unobservable_capability_wins_over_any_reading():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.UNOBSERVABLE,
    )

    state = classify_association_state(
        configured=True,
        reading=WirelessAssociationReading(
            endpoint_id="e",
            attempted=True,
            associated=True,
            fresh=True,
            method=VerificationMethod.DIRECT_STATE,
        ),
        observation_capability=audit.status(
            WirelessCapability.ASSOCIATION_STATE_OBSERVATION,
        ),
    )

    assert state is WirelessAssociationState.UNOBSERVABLE


def test_a_stale_reading_is_unknown_rather_than_associated():
    state = classify_association_state(
        configured=True,
        reading=WirelessAssociationReading(
            endpoint_id="e",
            attempted=True,
            associated=True,
            fresh=False,
            method=VerificationMethod.DIRECT_STATE,
        ),
        observation_capability=WirelessCapabilityStatus.SUPPORTED,
    )

    assert state is WirelessAssociationState.UNKNOWN


def test_a_fresh_direct_reading_reaches_associated():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
        network_attachment_observation=WirelessCapabilityStatus.SUPPORTED,
    )
    port = _StubPort(
        audit,
        association={
            "attempted": True,
            "associated": True,
            "fresh": True,
            "method": VerificationMethod.DIRECT_STATE,
            "service_set": "default",
        },
        attachment={
            "attempted": True,
            "fresh": True,
            "method": VerificationMethod.STRUCTURED_API,
            "interface": "Wireless0",
            "ipv4": "10.20.30.44",
            "netmask": "255.255.255.0",
            "dhcp_client_flag": True,
        },
    )

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
    for item in qualification.results:
        assert item.association_state is WirelessAssociationState.ASSOCIATED
        assert item.attachment_state is NetworkAttachmentState.ATTACHED
        assert item.attachment.addressing_source is AddressingSource.DHCP_CLIENT_FLAG
        assert item.attachment.in_intended_segment is True
        assert item.association.backend_version == BUILD


def test_an_address_outside_the_intended_segment_is_a_failed_attachment():
    state = classify_attachment_state(
        configured=True,
        reading=WirelessAttachmentReading(
            endpoint_id="e",
            attempted=True,
            fresh=True,
            method=VerificationMethod.STRUCTURED_API,
            ipv4="192.168.9.5",
        ),
        observation_capability=WirelessCapabilityStatus.SUPPORTED,
        segment=_plan(
            segments_for("site/branch", "10.20.30.0/24", vlan_id=77),
        ).clusters[0].segment,
    )

    assert state is NetworkAttachmentState.FAILED


def test_an_address_with_no_planned_subnet_stays_unknown():
    state = classify_attachment_state(
        configured=True,
        reading=WirelessAttachmentReading(
            endpoint_id="e",
            attempted=True,
            fresh=True,
            method=VerificationMethod.STRUCTURED_API,
            ipv4="192.168.9.5",
        ),
        observation_capability=WirelessCapabilityStatus.SUPPORTED,
        segment=_plan().clusters[0].segment,
    )

    assert state is NetworkAttachmentState.UNKNOWN


def test_an_access_point_identity_is_dropped_when_the_backend_cannot_report_one():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
        associated_access_point_identification=WirelessCapabilityStatus.UNOBSERVABLE,
    )
    port = _StubPort(
        audit,
        association={
            "attempted": True,
            "associated": True,
            "fresh": True,
            "method": VerificationMethod.DIRECT_STATE,
            "access_point_id": "endpoint/guessed/access_point/001",
        },
    )

    qualification = qualify_iot_connectivity(_plan(), audit=audit, port=port)

    assert qualification.admission is IoTConnectivityAdmission.ACCEPTED
    assert all(
        item.association.observed_access_point_id == ""
        for item in qualification.results
    )


def test_naming_an_unreportable_access_point_is_refused_by_the_rules():
    audit = _audit(
        associated_access_point_identification=WirelessCapabilityStatus.UNOBSERVABLE,
    )
    observation = WirelessAssociationObservation(
        endpoint_id="e",
        cluster_id="c",
        state=WirelessAssociationState.ASSOCIATED,
        observed_access_point_id="ap",
        method=VerificationMethod.DIRECT_STATE,
        observation_status=ObservationStatus.OBSERVED,
        fresh_evidence=True,
        backend=BACKEND,
        backend_version=BUILD,
    )

    result = validate_association_observation(observation, audit)

    assert not result.is_valid
    assert any("identification is unobservable" in item for item in result.error_messages())


def test_a_claimed_association_without_evidence_is_refused_by_the_rules():
    observation = WirelessAssociationObservation(
        endpoint_id="e",
        cluster_id="c",
        state=WirelessAssociationState.ASSOCIATED,
    )

    result = validate_association_observation(observation, _audit())

    assert not result.is_valid
    messages = " ".join(result.error_messages())
    assert "observed reading" in messages
    assert "verification method" in messages
    assert "fresh evidence" in messages
    assert "backend build" in messages


@pytest.mark.parametrize(
    "requirement",
    ["require_observed_association", "require_observed_attachment"],
)
def test_a_policy_that_requires_observation_rejects_a_planned_run(requirement):
    qualification = qualify_iot_connectivity(
        _plan(),
        audit=_audit(),
        policy=IoTConnectivityPolicy(**{requirement: True}),
    )

    assert qualification.admission is IoTConnectivityAdmission.REJECTED
    assert qualification.reasons


def test_iot_function_stays_declared_and_separate_from_association():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
    )
    port = _StubPort(
        audit,
        association={
            "attempted": True,
            "associated": True,
            "fresh": True,
            "method": VerificationMethod.DIRECT_STATE,
        },
    )

    qualification = qualify_iot_connectivity(_plan(), audit=audit, port=port)

    assert set(qualification.association_summary) == {
        WirelessAssociationState.ASSOCIATED.value,
    }
    for item in qualification.results:
        assert item.iot_function.observation_status is ObservationStatus.NOT_ATTEMPTED
        assert item.iot_function.function is not IoTFunction.UNCLASSIFIED
    assert set(qualification.iot_function_summary) == {
        IoTFunction.VIDEO_CAPTURE.value,
        IoTFunction.SMOKE_DETECTION.value,
        IoTFunction.MOTION_DETECTION.value,
    }


def test_a_partially_observed_run_says_so():
    audit = _audit(
        association_state_observation=WirelessCapabilityStatus.SUPPORTED,
    )

    class _Mixed(_StubPort):
        def observe_association(self, intent):
            associated = intent.endpoint_id.endswith("001")
            return WirelessAssociationReading(
                endpoint_id=intent.endpoint_id,
                backend=BACKEND,
                backend_version=BUILD,
                attempted=True,
                associated=associated,
                fresh=True,
                method=VerificationMethod.DIRECT_STATE,
            )

    qualification = qualify_iot_connectivity(
        _plan(), audit=audit, port=_Mixed(audit),
    )

    assert qualification.closure is IoTConnectivityClosure.PARTIALLY_OBSERVED
    assert WirelessAssociationState.FAILED.value in qualification.association_summary
