"""The Packet Tracer half: the capability audit and the adapter that obeys it.

None of this runs Packet Tracer. What it checks is that the adapter cannot
produce a state the audit does not license, and that the audit itself keeps its
declared shape instead of quietly widening.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.packet_tracer_mcp.application.ports.wireless_connectivity import (
    WirelessConnectivityPort,
)
from src.packet_tracer_mcp.application.use_cases.plan_iot_connectivity import (
    IoTConnectivityAdmission,
    IoTConnectivityClosure,
    plan_iot_connectivity,
    qualify_iot_connectivity,
)
from src.packet_tracer_mcp.domain.enterprise.models.wireless_connectivity import (
    BLOCKED_CAPABILITY_STATUSES,
    MEASURED_CAPABILITY_STATUSES,
    NetworkAttachmentState,
    WirelessAssociationState,
    WirelessCapability,
    WirelessCapabilityStatus,
    WirelessConfigurationStatus,
    WirelessSecurityMode,
    WirelessServiceSetIntent,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from src.packet_tracer_mcp.infrastructure.catalog.wireless_capabilities import (
    EXTENSIONS_API_REFERENCE,
    packet_tracer_wireless_capability_audit,
)
from src.packet_tracer_mcp.infrastructure.execution.packet_tracer_wireless_connectivity import (
    PacketTracerWirelessConnectivityAdapter,
    WirelessRuntimeEndpoint,
)
from tests.support.iot_connectivity_scenarios import medium_topology, segments_for


def _audit():
    return packet_tracer_wireless_capability_audit(MEASURED_BACKEND_VERSION)


def _plan():
    result = plan_iot_connectivity(
        medium_topology(),
        segments=segments_for("site/branch", "10.20.30.0/24", vlan_id=77),
    )
    assert result.is_valid, result.validation.error_messages()
    return result.plan


def test_the_audit_is_declared_for_one_exact_build_only():
    audit = _audit()

    assert audit.backend_version == MEASURED_BACKEND_VERSION
    with pytest.raises(ValueError):
        packet_tracer_wireless_capability_audit("8.2.2")


def test_every_declared_capability_has_a_status_and_a_traceable_ground():
    audit = _audit()

    covered = {item.capability for item in audit.assessments}
    assert covered == set(WirelessCapability)
    for assessment in audit.assessments:
        assert assessment.backend_version == MEASURED_BACKEND_VERSION
        assert assessment.note, assessment.capability
        assert assessment.resolved_by, assessment.capability
        if assessment.status is WirelessCapabilityStatus.SUPPORTED:
            assert assessment.surface, assessment.capability
            assert assessment.evidence_reference, assessment.capability


def test_an_unaudited_capability_subject_falls_back_and_never_invents_support():
    audit = _audit()

    assert audit.status(
        WirelessCapability.RADIO_ENABLEMENT, "Laptop-PT",
    ) is WirelessCapabilityStatus.SUPPORTED
    assert audit.status(
        WirelessCapability.RADIO_ENABLEMENT, "Smoke Detector",
    ) is WirelessCapabilityStatus.UNKNOWN
    assert audit.status(
        WirelessCapability.ENDPOINT_ADDRESS_OBSERVATION, "Webcam",
    ) is WirelessCapabilityStatus.UNKNOWN


def test_documented_wireless_surfaces_are_documented_and_never_unsupported():
    """A vendor reference refutes nothing and establishes nothing."""
    audit = _audit()

    for capability in (
        WirelessCapability.SERVICE_SET_CONFIGURATION,
        WirelessCapability.ENDPOINT_SERVICE_SET_SELECTION,
        WirelessCapability.ASSOCIATION_STATE_OBSERVATION,
        WirelessCapability.ASSOCIATED_ACCESS_POINT_IDENTIFICATION,
        WirelessCapability.NETWORK_ATTACHMENT_OBSERVATION,
    ):
        assert audit.status(capability) is WirelessCapabilityStatus.DOCUMENTED


def test_a_documented_surface_never_licenses_a_claim():
    """DOCUMENTED gates exactly like UNKNOWN wherever a promotion is decided."""
    assert WirelessCapabilityStatus.DOCUMENTED not in BLOCKED_CAPABILITY_STATUSES
    assert WirelessCapabilityStatus.DOCUMENTED not in MEASURED_CAPABILITY_STATUSES


def test_the_audit_keeps_unmeasured_things_unknown():
    audit = _audit()

    assert audit.status(
        WirelessCapability.IOT_FUNCTION_OBSERVATION,
    ) is WirelessCapabilityStatus.UNKNOWN
    assert audit.status(
        WirelessCapability.ACCESS_POINT_RADIO_PORT_IDENTITY, "AccessPoint-PT",
    ) is WirelessCapabilityStatus.UNKNOWN
    assert not any(
        item.status is WirelessCapabilityStatus.UNSUPPORTED
        for item in audit.assessments
    ), "nothing on this build has been measured to be impossible"


def test_every_documented_record_names_the_reference_and_its_gap():
    audit = _audit()

    documented = [
        item for item in audit.assessments
        if item.status is WirelessCapabilityStatus.DOCUMENTED
    ]
    assert documented
    for item in documented:
        assert item.evidence_reference == EXTENSIONS_API_REFERENCE
        assert "8.1.0" in item.evidence_reference
        assert MEASURED_BACKEND_VERSION in item.note
        assert item.surface


def _adapter(bindings, transport=None):
    calls: list[str] = []

    def send_and_wait(script: str, timeout: float) -> str | None:
        calls.append(script)
        return None if transport is None else transport(script)

    adapter = PacketTracerWirelessConnectivityAdapter(
        send_and_wait, bindings, packet_tracer_version=MEASURED_BACKEND_VERSION,
    )
    return adapter, calls


def test_the_adapter_satisfies_the_port_protocol():
    adapter, _ = _adapter({})

    assert isinstance(adapter, WirelessConnectivityPort)


def test_the_default_service_set_is_not_configured_and_not_claimed():
    plan = _plan()
    intent = plan.association_intents[0]
    adapter, calls = _adapter({})

    outcome = adapter.configure_association(intent)

    assert outcome.status is WirelessConfigurationStatus.NOT_ATTEMPTED
    assert not outcome.applied
    assert calls == []


def test_a_custom_service_set_is_refused_rather_than_silently_skipped():
    plan = _plan()
    intent = plan.association_intents[0]
    custom = WirelessServiceSetIntent(
        ssid="branch-iot", security_mode=WirelessSecurityMode.WPA2_PSK,
    )
    adapter, calls = _adapter({})

    outcome = adapter.configure_association(replace(intent, service_set=custom))

    assert outcome.status is WirelessConfigurationStatus.REFUSED
    assert "documented" in outcome.detail
    assert "no wireless mutation" in outcome.detail
    assert calls == []


def test_the_adapter_never_asks_packet_tracer_for_an_association():
    plan = _plan()
    intent = plan.association_intents[0]
    adapter, calls = _adapter({
        intent.endpoint_id: WirelessRuntimeEndpoint(
            endpoint_id=intent.endpoint_id,
            runtime_device_name="BRANCH-WEBCAM-01",
            model="Webcam",
        ),
    })

    reading = adapter.observe_association(intent)

    assert reading.attempted is False
    assert reading.associated is None
    assert reading.access_point_id == ""
    assert reading.error_kind is None
    assert reading.unavailable_reading == "", (
        "an unmeasured capability is not an absent property"
    )
    assert "documented" in reading.detail
    assert calls == []


def test_an_iot_endpoint_has_no_measured_interface_so_addressing_stops_there():
    plan = _plan()
    intent = plan.association_intents[0]
    cluster = plan.cluster(intent.cluster_id)
    adapter, calls = _adapter({
        intent.endpoint_id: WirelessRuntimeEndpoint(
            endpoint_id=intent.endpoint_id,
            runtime_device_name="BRANCH-WEBCAM-01",
            model="Webcam",
        ),
    })

    reading = adapter.observe_attachment(intent, cluster.segment)

    assert reading.attempted is False
    assert reading.unavailable_reading == ""
    assert reading.error_kind is None
    assert reading.ipv4 == ""
    assert "unknown" in reading.detail
    assert calls == []


def test_a_qualified_model_reads_its_address_through_the_qualified_getter():
    plan = _plan()
    intent = plan.association_intents[0]
    cluster = plan.cluster(intent.cluster_id)

    def transport(script: str) -> str:
        if "isWirelessPort" in script:
            return json.dumps({
                "found": True, "port_found": True, "interface": "Wireless0",
                "classification_channel": True, "wireless": True,
            })
        return json.dumps({
            "found": True, "port_found": True, "interface": "Wireless0",
            "address_channel": True, "ipv4": "10.20.30.44",
            "netmask": "255.255.255.0",
        })

    adapter, calls = _adapter(
        {
            intent.endpoint_id: WirelessRuntimeEndpoint(
                endpoint_id=intent.endpoint_id,
                runtime_device_name="BRANCH-LAPTOP-01",
                model="Laptop-PT",
                interface="Wireless0",
            ),
        },
        transport,
    )

    reading = adapter.observe_attachment(intent, cluster.segment)

    assert reading.attempted is True
    assert reading.ipv4 == "10.20.30.44"
    assert reading.fresh is True
    assert "getIpAddress" in calls[0]
    assert json.dumps("BRANCH-LAPTOP-01") in calls[0]


def test_every_generated_script_serializes_its_fields():
    """A device name with a quote must not be able to close the JS literal."""
    plan = _plan()
    intent = plan.association_intents[0]
    hostile = 'BAD"); reportResult("pwned'
    adapter, calls = _adapter(
        {
            intent.endpoint_id: WirelessRuntimeEndpoint(
                endpoint_id=intent.endpoint_id,
                runtime_device_name=hostile,
                model="Laptop-PT",
                interface="Wireless0",
            ),
        },
        lambda script: None,
    )

    adapter.observe_association(intent)
    adapter.observe_attachment(intent, plan.cluster(intent.cluster_id).segment)

    assert calls
    for script in calls:
        assert hostile not in script
        assert json.dumps(hostile) in script


def test_packet_tracer_today_observes_nothing_and_claims_nothing():
    plan = _plan()
    bindings = {
        intent.endpoint_id: WirelessRuntimeEndpoint(
            endpoint_id=intent.endpoint_id,
            runtime_device_name=intent.endpoint_id,
            model="Webcam",
        )
        for intent in plan.association_intents
    }
    adapter, calls = _adapter(bindings)

    qualification = qualify_iot_connectivity(
        plan, audit=_audit(), port=adapter, configure=True,
    )

    assert calls == [], "no measured surface is driven on this build"
    assert qualification.closure is IoTConnectivityClosure.CONFIGURED_NOT_OBSERVED
    for item in qualification.results:
        assert item.association_state is WirelessAssociationState.PLANNED
        assert item.attachment_state is NetworkAttachmentState.PLANNED
        assert item.association.observed_access_point_id == ""
    assert qualification.admission is IoTConnectivityAdmission.ACCEPTED
