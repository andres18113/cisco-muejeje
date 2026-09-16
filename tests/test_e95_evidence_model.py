from packet_tracer_mcp.domain.enterprise.models.evidence import (
    CapabilityReadiness,
    EvidenceStrength,
    EvidenceFreshness,
    EvidenceRecord,
    ObservationStatus,
    ReadinessStatus,
    SupportStatus,
    VerificationMethod,
    VerificationStatus,
    evidence_from_legacy_result,
)


def test_support_observation_and_verification_statuses_are_not_interchangeable():
    unknown = EvidenceRecord(
        id="e/unknown",
        subject="3560-24PS:svi",
        claim="svi is supported",
        method=VerificationMethod.NONE,
        support_status=SupportStatus.UNKNOWN,
        observation_status=ObservationStatus.NOT_ATTEMPTED,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    unsupported = unknown.model_copy(update={
        "id": "e/unsupported",
        "support_status": SupportStatus.UNSUPPORTED,
        "observation_status": ObservationStatus.OBSERVED,
        "verification_status": VerificationStatus.VERIFIED,
    })
    unobservable = unknown.model_copy(update={
        "id": "e/unobservable",
        "support_status": SupportStatus.UNKNOWN,
        "observation_status": ObservationStatus.UNOBSERVABLE,
    })
    failed = unknown.model_copy(update={
        "id": "e/failed",
        "support_status": SupportStatus.SUPPORTED,
        "observation_status": ObservationStatus.OBSERVED,
        "verification_status": VerificationStatus.FAILED,
    })

    assert unknown.classification == "unknown"
    assert unsupported.classification == "unsupported"
    assert unobservable.classification == "unobservable"
    assert failed.classification == "failed"
    assert len({item.classification for item in (unknown, unsupported, unobservable, failed)}) == 4


def test_stale_or_unobserved_evidence_cannot_verify_a_claim():
    stale = EvidenceRecord(
        id="e/stale", subject="r1", claim="current route exists",
        method=VerificationMethod.OPERATIONAL_CLI,
        freshness=EvidenceFreshness.STALE,
        support_status=SupportStatus.SUPPORTED,
        observation_status=ObservationStatus.OBSERVED,
        verification_status=VerificationStatus.VERIFIED,
    )
    missing = stale.model_copy(update={
        "id": "e/missing",
        "freshness": EvidenceFreshness.FRESH,
        "observation_status": ObservationStatus.UNOBSERVABLE,
    })

    assert stale.verifies_claim is False
    assert missing.verifies_claim is False


def test_compact_evidence_does_not_dump_full_transcript():
    evidence = EvidenceRecord(
        id="e/cli", subject="r1", claim="ACL attached",
        method=VerificationMethod.OPERATIONAL_CLI,
        freshness=EvidenceFreshness.FRESH,
        support_status=SupportStatus.SUPPORTED,
        observation_status=ObservationStatus.OBSERVED,
        verification_status=VerificationStatus.VERIFIED,
        observed_value={"interface": "GigabitEthernet0/0", "direction": "in"},
        environment_fingerprint="environment/sha256",
        capability_snapshot_hash="capability/sha256",
        raw_reference="sha256:abc123",
    )

    summary = evidence.compact_summary()

    assert summary["observed_value"] == {
        "direction": "in", "interface": "GigabitEthernet0/0",
    }
    assert "raw_output" not in summary
    assert summary["raw_reference"] == "sha256:abc123"
    assert summary["environment_fingerprint"] == "environment/sha256"
    assert summary["capability_snapshot_hash"] == "capability/sha256"


def test_compile_ready_can_coexist_with_apply_unknown_and_verify_unobservable():
    readiness = CapabilityReadiness(
        capability="3560-24PS:svi",
        compile=ReadinessStatus.READY,
        apply=ReadinessStatus.UNKNOWN,
        verify=ReadinessStatus.UNOBSERVABLE,
    )

    assert readiness.compile is ReadinessStatus.READY
    assert readiness.apply is ReadinessStatus.UNKNOWN
    assert readiness.verify is ReadinessStatus.UNOBSERVABLE


def test_legacy_failed_behavior_does_not_become_unsupported_capability():
    evidence = evidence_from_legacy_result(
        identifier="e/ping",
        subject="path/a-b",
        claim="forwarding succeeds",
        status="failed",
        evidence_method="behavioral_ping",
        fresh_evidence=True,
    )

    assert evidence.method is VerificationMethod.BEHAVIORAL
    assert evidence.observation_status is ObservationStatus.OBSERVED
    assert evidence.verification_status is VerificationStatus.FAILED
    assert evidence.support_status is SupportStatus.UNKNOWN
    assert evidence.classification == "failed"


def test_legacy_nonfresh_results_do_not_fabricate_an_observation():
    unknown = evidence_from_legacy_result(
        identifier="e/unknown", subject="svc", claim="ntp_sync",
        status="partial", evidence_method="", fresh_evidence=False,
    )
    unobservable = evidence_from_legacy_result(
        identifier="e/unobservable", subject="svc", claim="tftp_retrieve",
        status="unobservable",
        evidence_method="packet_tracer_client_observation_unavailable",
        fresh_evidence=False,
    )
    failed_probe = evidence_from_legacy_result(
        identifier="e/failed", subject="svc", claim="https_fetch",
        status="failed", evidence_method="typed_client_operation",
        fresh_evidence=False,
    )

    assert unknown.observation_status is ObservationStatus.NOT_ATTEMPTED
    assert unobservable.observation_status is ObservationStatus.UNOBSERVABLE
    assert failed_probe.observation_status is ObservationStatus.PROBE_FAILED
    assert failed_probe.verification_status is VerificationStatus.UNVERIFIED
    assert failed_probe.classification == "probe_failed"


def test_verified_axes_without_method_strength_or_support_cannot_verify_claim():
    incoherent = EvidenceRecord(
        id="e/incoherent",
        subject="r1",
        claim="runtime device exists",
        method=VerificationMethod.NONE,
        strength=EvidenceStrength.NONE,
        freshness=EvidenceFreshness.FRESH,
        support_status=SupportStatus.UNKNOWN,
        observation_status=ObservationStatus.OBSERVED,
        verification_status=VerificationStatus.VERIFIED,
    )

    assert incoherent.verifies_claim is False
    assert incoherent.classification == "unknown"


def test_legacy_vlan_manager_object_state_maps_to_structured_direct_evidence():
    evidence = evidence_from_legacy_result(
        identifier="e/vlan",
        subject="sw1:vlan10",
        claim="VLAN exists",
        status="verified",
        evidence_method="vlan_manager_object_state",
        fresh_evidence=True,
    )

    assert evidence.method is VerificationMethod.STRUCTURED_API
    assert evidence.strength is EvidenceStrength.CLAIM_DIRECT
    assert evidence.verifies_claim
    assert evidence.classification == "verified"
