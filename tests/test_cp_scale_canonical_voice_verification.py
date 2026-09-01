"""Canonical CP-SCALE Voice evidence is complete, correlated, and fail-closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    compose_cp_scale_canonical,
    project_cp_scale_canonical_stage,
)
from src.packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    CPScaleFinalDisposition,
    archive_cp_scale_canonical_evidence,
    canonical_cp_scale_voice_evidence,
    canonical_final_disposition,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigureAccessPort,
)
from src.packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConvergenceReport,
    FieldVerificationStatus,
    VerificationResult,
    VoiceSignalBarrierResult,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    PhoneRegistrationResult,
    VoiceApplicationResult,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


def _floor1():
    composition = compose_cp_scale_canonical(
        packet_tracer_version=MEASURED_BACKEND_VERSION,
        capability_store=CapabilitySnapshotStore(Path("data/capabilities")),
    )
    assert composition.valid, composition.issues
    return project_cp_scale_canonical_stage(
        composition, CPScaleCanonicalStage.FLOOR1,
    )


def _complete_floor1_evidence():
    projection = _floor1()
    assert projection.voice is not None
    access_actions = {
        item.id: item for item in projection.configuration.actions
        if isinstance(item, ConfigureAccessPort) and item.voice_vlan_id is not None
    }
    access_expectations = [
        item for item in projection.configuration.verification_expectations
        if item.action_id in access_actions
    ]
    interfaces = sorted(item.interface for item in access_actions.values())
    details = {
        "kind": "voice_access_forwarding_group",
        "switch": "Switch5",
        "voice_vlan_id": 20,
        "expected_interfaces": interfaces,
        "verified_fwd_interfaces": interfaces,
        "missing_interfaces": [],
        "non_fwd_interfaces": {},
        "sample_count": 13,
        "elapsed_ms": 31_000,
        "terminal_authority": "AUTHORITATIVE",
        "terminal_failure_dimension": "NONE",
    }
    convergence = ConvergenceReport(
        attempts=13,
        elapsed_ms=31_000,
        final_status=ActionExecutionStatus.VERIFIED,
        last_observable_state="all forwarding",
        details=details,
    )
    forwarding = [
        VerificationResult(
            expectation_id=item.id,
            action_id=item.action_id,
            status=ActionExecutionStatus.VERIFIED,
            evidence_method="fresh_show_spanning_tree_voice_access",
            fresh_evidence=True,
            fields={"voice_forwarding": FieldVerificationStatus.VERIFIED},
            convergence=convergence,
        )
        for item in access_expectations
    ]
    configuration = ConfigurationApplicationResult(
        config_plan_id=projection.configuration.id,
        config_semantic_hash=projection.configuration.semantic_hash,
        source_topology_hash=projection.configuration.source_topology_hash,
        status=ConfigurationApplicationStatus.VERIFIED,
        voice_signal_barrier=VoiceSignalBarrierResult(
            required=True,
            deferred_action_ids=sorted(access_actions),
            foundation_status=ActionExecutionStatus.VERIFIED,
            signal_status=ActionExecutionStatus.VERIFIED,
            post_signal_convergence_results=forwarding,
        ),
    )

    registrations = []
    bindings_by_segment: dict[str, list[str]] = {}
    for index, assignment in enumerate(projection.voice.phone_assignments, 11):
        address = f"172.16.20.{index}"
        bindings_by_segment.setdefault(assignment.voice_segment_id, []).append(address)
        registrations.append(PhoneRegistrationResult(
            expectation_id=f"verify/{assignment.phone_id}",
            phone_id=assignment.phone_id,
            extension=assignment.extension,
            status=ActionExecutionStatus.VERIFIED,
            direct_readback=FieldVerificationStatus.VERIFIED,
            evidence_method="fresh_privileged_show_ephone",
            fresh_evidence=True,
            call_control_ipv4=address,
            endpoint_ipv4=address,
            endpoint_interface="Vlan20",
            endpoint_interface_present=True,
            endpoint_address_channel=True,
            endpoint_dhcp_enabled=True,
            addressing_status=ActionExecutionStatus.VERIFIED,
        ))
    voice = VoiceApplicationResult(
        voice_plan_id=projection.voice.id,
        voice_semantic_hash=projection.voice.semantic_hash,
        source_topology_hash=projection.voice.source_topology_hash,
        source_configuration_hash=projection.voice.source_configuration_hash,
        status=ActionExecutionStatus.VERIFIED,
        application_status=ActionExecutionStatus.APPLIED,
        registrations=registrations,
    )
    binding_evidence = [{
        "device_name": "Router4",
        "table_readable": True,
        "pools": [
            {
                "segment_id": segment_id,
                "voice": True,
                "binding_count": len(addresses),
                "bindings": addresses,
            }
            for segment_id, addresses in bindings_by_segment.items()
        ],
    }]
    lifecycle = [
        "DATA_ONLY_ACCESS_APPLIED",
        "NETWORK_VERIFIED",
        "VOICE_BOOTSTRAP_STARTED",
        "VOICE_BOOTSTRAP_APPLIED",
        "DEFERRED_VOICE_COMPLETION_STARTED",
        "VOICE_SIGNAL_VERIFIED",
        "PHONE_ACCESS_FWD_VERIFIED",
        "DEFERRED_VOICE_COMPLETION_VERIFIED",
        "REGISTRATION_STARTED",
        "REGISTRATION_COMPLETED",
    ]
    return projection, configuration, voice, binding_evidence, lifecycle


def test_complete_floor1_voice_evidence_requires_identities_not_just_counts():
    projection, configuration, voice, bindings, lifecycle = (
        _complete_floor1_evidence()
    )

    evidence = canonical_cp_scale_voice_evidence(
        stage="floor1",
        configuration_plan=projection.configuration,
        configuration_result=configuration,
        voice_plan=projection.voice,
        voice_result=voice,
        dhcp_server_bindings=bindings,
        lifecycle_events=lifecycle,
    )

    assert evidence.complete
    assert evidence.expected_phone_count == 21
    assert evidence.phone_access_group_count == 1
    assert evidence.phone_access_fwd_expected == 21
    assert evidence.phone_access_fwd_verified == 21
    assert evidence.registration_started_after_fwd_barrier is True
    assert evidence.voice_svi_present_count == 21
    assert evidence.dhcp_enabled_count == 21
    assert evidence.addressed_count == 21
    assert evidence.voice_dhcp_binding_count == 21
    assert evidence.matching_binding_count == 21
    assert evidence.sccp_registered_count == 21
    assert evidence.failed_phone_identities == []
    assert evidence.first_contradicted_boundary == "NONE"


def test_missing_matching_binding_fails_the_exact_phone_closed():
    projection, configuration, voice, bindings, lifecycle = (
        _complete_floor1_evidence()
    )
    missing_address = voice.registrations[0].endpoint_ipv4
    bindings[0]["pools"][0]["bindings"].remove(missing_address)
    bindings[0]["pools"][0]["binding_count"] -= 1

    evidence = canonical_cp_scale_voice_evidence(
        stage="floor1",
        configuration_plan=projection.configuration,
        configuration_result=configuration,
        voice_plan=projection.voice,
        voice_result=voice,
        dhcp_server_bindings=bindings,
        lifecycle_events=lifecycle,
    )

    assert not evidence.complete
    assert evidence.matching_binding_count == 20
    assert evidence.first_contradicted_boundary == "DHCP_BINDING"
    assert len(evidence.failed_phone_identities) == 1
    assert evidence.failed_phone_identities[0].binding_state == "MISSING"
    assert evidence.failed_phone_identities[0].ipv4 == missing_address


def test_matching_endpoint_and_binding_localize_missing_ephone_row_to_sccp():
    projection, configuration, voice, bindings, lifecycle = (
        _complete_floor1_evidence()
    )
    registration = voice.registrations[0]
    registration.status = ActionExecutionStatus.UNOBSERVABLE
    registration.direct_readback = FieldVerificationStatus.UNOBSERVABLE
    registration.call_control_ipv4 = ""
    registration.addressing_status = ActionExecutionStatus.PARTIAL
    registration.addressing_message = (
        f"{registration.endpoint_ipv4} was observed on one channel only."
    )
    registration.evidence_method = "show_ephone_complete_without_this_row"

    evidence = canonical_cp_scale_voice_evidence(
        stage="floor1",
        configuration_plan=projection.configuration,
        configuration_result=configuration,
        voice_plan=projection.voice,
        voice_result=voice,
        dhcp_server_bindings=bindings,
        lifecycle_events=lifecycle,
    )

    assert not evidence.complete
    assert evidence.addressed_count == 21
    assert evidence.matching_binding_count == 21
    assert evidence.sccp_registered_count == 20
    assert evidence.sccp_unobservable_count == 1
    assert evidence.first_contradicted_boundary == "SCCP"
    assert evidence.failed_phone_identities[0].first_contradicted_boundary == (
        "SCCP"
    )


def test_missing_structured_group_evidence_never_promotes_per_port_flags():
    projection, configuration, voice, bindings, lifecycle = (
        _complete_floor1_evidence()
    )
    barrier = configuration.voice_signal_barrier
    assert barrier is not None
    for item in barrier.post_signal_convergence_results:
        assert item.convergence is not None
        item.convergence.details = {}

    evidence = canonical_cp_scale_voice_evidence(
        stage="floor1",
        configuration_plan=projection.configuration,
        configuration_result=configuration,
        voice_plan=projection.voice,
        voice_result=voice,
        dhcp_server_bindings=bindings,
        lifecycle_events=lifecycle,
    )

    assert not evidence.complete
    assert evidence.phone_access_fwd_verified == 0
    assert evidence.phone_access_fwd_unobservable == 21
    assert evidence.first_contradicted_boundary == "PHONE_ACCESS_FORWARDING"


def test_unexpected_registration_identity_fails_exact_correlation():
    projection, configuration, voice, bindings, lifecycle = (
        _complete_floor1_evidence()
    )
    voice.registrations.append(voice.registrations[0].model_copy(update={
        "phone_id": "phone/unexpected",
        "expectation_id": "verify/phone/unexpected",
    }))

    evidence = canonical_cp_scale_voice_evidence(
        stage="floor1",
        configuration_plan=projection.configuration,
        configuration_result=configuration,
        voice_plan=projection.voice,
        voice_result=voice,
        dhcp_server_bindings=bindings,
        lifecycle_events=lifecycle,
    )

    assert not evidence.complete
    assert evidence.first_contradicted_boundary == "ENDPOINT_ADDRESS"
    assert evidence.registration_identity_errors == [
        "unexpected:phone/unexpected",
    ]


def test_final_continue_means_verified_cleanup_not_an_artificial_failure():
    assert canonical_final_disposition(
        "continue", retain_authorized=False,
    ) is CPScaleFinalDisposition.CLEANUP
    assert canonical_final_disposition(
        "retain", retain_authorized=True,
    ) is CPScaleFinalDisposition.RETAIN
    with pytest.raises(ValueError, match="retention was not authorized"):
        canonical_final_disposition("retain", retain_authorized=False)


def test_canonical_archive_is_unique_exact_and_never_overwritten(tmp_path):
    evidence = {"run_identity": "canonical-run-24", "value": [1, 2, 3]}

    archived = archive_cp_scale_canonical_evidence(
        evidence,
        base_dir=tmp_path,
        run_identity="canonical-run-24",
        phase="precleanup",
    )

    assert json.loads(archived.path.read_text(encoding="utf-8")) == evidence
    assert len(archived.sha256) == 64
    with pytest.raises(FileExistsError):
        archive_cp_scale_canonical_evidence(
            evidence,
            base_dir=tmp_path,
            run_identity="canonical-run-24",
            phase="precleanup",
        )
