from packet_tracer_mcp.domain.enterprise.models.evidence import (
    CapabilityReadiness,
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
        raw_reference="sha256:abc123",
    )

    summary = evidence.compact_summary()

    assert summary["observed_value"] == {
        "direction": "in", "interface": "GigabitEthernet0/0",
    }
    assert "raw_output" not in summary
    assert summary["raw_reference"] == "sha256:abc123"


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
