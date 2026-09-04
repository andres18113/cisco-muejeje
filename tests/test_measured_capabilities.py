"""Versioned capability evidence must survive a clean checkout.

The mutable discovery store under ``data/capabilities`` is useful runtime
state, but it is gitignored and therefore cannot be the shipped baseline for
plans that the product itself exposes.  These tests pin the narrower contract:
only governed, exact-build observations are portable; everything else remains
UNKNOWN, and newer runtime evidence keeps precedence.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityEvidence,
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilitySnapshot,
    CapabilityVerificationMethod,
    ProbeExecutionStatus,
    ProbeSession,
    ProbeSessionResult,
)
from src.packet_tracer_mcp.domain.enterprise.services.capability_resolver import (
    CapabilityResolver,
    CatalogDeviceFacts,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
    packet_tracer_enterprise_capability_adapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_capabilities import (
    MEASURED_CAPABILITY_RECORDS,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


BUILD = MEASURED_BACKEND_VERSION


def _delivery_dimensions(*, active: int, tested: int = 24) -> dict[str, str]:
    return {
        "poe_access_port_count": "24",
        "poe_delivery_tested_ports": str(tested),
        "poe_delivery_active_ports": str(active),
    }

EXPECTED = {
    "1941": {"layer3": CapabilityStatus.SUPPORTED},
    "2811": {
        "layer3": CapabilityStatus.SUPPORTED,
        "supports_cme": CapabilityStatus.SUPPORTED,
        "supports_dhcp_server": CapabilityStatus.SUPPORTED,
    },
    "2911": {"layer3": CapabilityStatus.SUPPORTED},
    "2950T-24": {
        "layer2": CapabilityStatus.SUPPORTED,
        "supports_vlan": CapabilityStatus.SUPPORTED,
    },
    "2960-24TT": {
        "layer2": CapabilityStatus.SUPPORTED,
        "supports_poe": CapabilityStatus.UNKNOWN,
        "supports_trunk": CapabilityStatus.SUPPORTED,
        "supports_vlan": CapabilityStatus.SUPPORTED,
    },
    "3560-24PS": {
        "layer2": CapabilityStatus.SUPPORTED,
        "layer3": CapabilityStatus.SUPPORTED,
        "supports_poe": CapabilityStatus.UNKNOWN,
        "supports_trunk": CapabilityStatus.SUPPORTED,
        "supports_vlan": CapabilityStatus.SUPPORTED,
    },
    "3650-24PS": {
        "layer2": CapabilityStatus.SUPPORTED,
        "supports_poe": CapabilityStatus.UNKNOWN,
        "supports_trunk": CapabilityStatus.SUPPORTED,
        "supports_vlan": CapabilityStatus.SUPPORTED,
    },
    "IE-2000": {
        "layer2": CapabilityStatus.SUPPORTED,
        "supports_vlan": CapabilityStatus.SUPPORTED,
    },
}
EXPECTED_RECORD_IDENTITIES = {
    (model, capability)
    for model, statuses in EXPECTED.items()
    for capability in statuses
} - {("3560-24PS", "layer3")} | {
    ("3560-24PS", "multilayer_intervlan"),
}


def test_governed_capabilities_do_not_depend_on_cwd_machine_state(
    tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    adapter = packet_tracer_enterprise_capability_adapter(BUILD)

    for model, statuses in EXPECTED.items():
        resolved = adapter.capabilities_for(model, BUILD)
        assert resolved is not None
        for capability, status in statuses.items():
            assert getattr(resolved, capability) is status, (model, capability)

    assert adapter.capabilities_for("3560-24PS", BUILD).poe_ports is None
    assert adapter.capabilities_for("3650-24PS", BUILD).poe_ports is None
    assert adapter.capabilities_for("2960-24TT", BUILD).poe_ports is None


def test_every_portable_fact_is_exact_build_verified_and_traceable():
    assert MEASURED_CAPABILITY_RECORDS

    identities = set()
    for record in MEASURED_CAPABILITY_RECORDS:
        identity = (record.model, record.capability)
        assert identity not in identities
        identities.add(identity)

        evidence = record.as_evidence()
        assert evidence.source is EvidenceSource.STATIC_OVERRIDE
        assert evidence.packet_tracer_version == BUILD
        assert evidence.verified is True
        assert evidence.confidence == "live_qualified"
        assert len(record.snapshot_hash) == 64
        int(record.snapshot_hash, 16)
        assert record.snapshot_hash in evidence.source_detail
        assert record.producer in evidence.source_detail
        assert evidence.notes

    assert identities == EXPECTED_RECORD_IDENTITIES


def test_absent_facts_and_other_builds_remain_unknown(tmp_path):
    empty = CapabilitySnapshotStore(tmp_path / "empty")
    exact = packet_tracer_enterprise_capability_adapter(BUILD, store=empty)
    other = packet_tracer_enterprise_capability_adapter("9.0.2.0000", store=empty)

    assert exact.capabilities_for("3650-24PS", BUILD).layer3 is CapabilityStatus.UNKNOWN
    assert exact.capabilities_for("2950T-24", BUILD).supports_poe is CapabilityStatus.UNKNOWN
    for model, statuses in EXPECTED.items():
        resolved = other.capabilities_for(model, "9.0.2.0000")
        assert resolved is not None
        for capability in statuses:
            assert getattr(resolved, capability) is CapabilityStatus.UNKNOWN


def test_runtime_negative_without_delivery_test_remains_unknown(tmp_path):
    store = CapabilitySnapshotStore(tmp_path / "runtime")
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=BUILD,
        session=ProbeSessionResult(
            session=ProbeSession(
                session_id="newer-negative",
                packet_tracer_version=BUILD,
            ),
            results=[CapabilityProbeResult(
                probe_id="fresh-supports-poe",
                model="3560-24PS",
                capability="supports_poe",
                status=CapabilityStatus.UNSUPPORTED,
                execution_status=ProbeExecutionStatus.VERIFIED,
                evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
                verified=True,
                packet_tracer_version=BUILD,
                verification_method=CapabilityVerificationMethod.OBJECT_STATE,
            )],
        ),
    ))

    resolved = packet_tracer_enterprise_capability_adapter(
        BUILD, store=store,
    ).capabilities_for("3560-24PS", BUILD)

    assert resolved is not None
    assert resolved.supports_poe is CapabilityStatus.UNKNOWN
    assert resolved.poe_ports is None


def test_execution_snapshot_reuses_the_first_resolution_when_a_provider_changes():
    class ChangingProvider:
        def __init__(self) -> None:
            self.requests = 0

        def evidence_for(self, model, packet_tracer_version=None):
            if model != "3560-24PS":
                return ()
            self.requests += 1
            status = (
                CapabilityStatus.SUPPORTED
                if self.requests == 1
                else CapabilityStatus.UNSUPPORTED
            )
            return (CapabilityEvidence(
                capability="supports_poe",
                status=status,
                source=EvidenceSource.PACKET_TRACER_RUNTIME,
                packet_tracer_version=BUILD,
                verified=True,
                observed_value=24 if status is CapabilityStatus.SUPPORTED else None,
                dimensions=_delivery_dimensions(
                    active=24 if status is CapabilityStatus.SUPPORTED else 0,
                ),
            ),)

    provider = ChangingProvider()
    mutable = EnterpriseCapabilityAdapter(
        providers=[provider],
        bound_packet_tracer_version=BUILD,
    )
    execution = mutable.execution_snapshot()

    first = next(
        item
        for item in execution.all_capabilities("switch", BUILD)
        if item.model == "3560-24PS"
    )
    second = execution.capabilities_for("3560-24PS", BUILD)
    later_mutable_read = mutable.capabilities_for("3560-24PS", BUILD)

    assert first is not None and first.supports_poe is CapabilityStatus.SUPPORTED
    assert first.poe_ports == 24
    assert second is not None and second.supports_poe is CapabilityStatus.SUPPORTED
    assert second.poe_ports == 24
    assert later_mutable_read is not None
    assert later_mutable_read.supports_poe is CapabilityStatus.UNSUPPORTED
    assert later_mutable_read.poe_ports is None


def test_execution_snapshot_preserves_injected_adapter_semantics():
    class RestrictiveCatalog(EnterpriseCapabilityAdapter):
        def hardware_candidates(self, category, packet_tracer_version=None):
            return []

    execution = RestrictiveCatalog().execution_snapshot()

    assert isinstance(execution, RestrictiveCatalog)
    assert execution.hardware_candidates("switch", BUILD) == []


def test_execution_snapshot_does_not_alias_an_empty_version_to_the_bound_build(
    tmp_path,
):
    mutable = packet_tracer_enterprise_capability_adapter(
        BUILD,
        store=CapabilitySnapshotStore(tmp_path / "empty"),
    )
    execution = mutable.execution_snapshot()

    invalid = execution.capabilities_for("3560-24PS", "")
    exact = execution.capabilities_for("3560-24PS", BUILD)

    assert invalid is not None
    assert invalid.supports_poe is CapabilityStatus.UNKNOWN
    assert exact is not None
    assert exact.supports_poe is CapabilityStatus.UNKNOWN


def test_execution_result_mutation_cannot_change_a_later_execution(tmp_path):
    mutable = packet_tracer_enterprise_capability_adapter(
        BUILD,
        store=CapabilitySnapshotStore(tmp_path / "empty"),
    )
    first = mutable.execution_snapshot().capabilities_for("2960-24TT", BUILD)

    assert first is not None
    poe = next(item for item in first.evidence if item.capability == "supports_poe")
    poe.status = CapabilityStatus.SUPPORTED
    poe.observed_value = 24

    later = mutable.execution_snapshot().capabilities_for("2960-24TT", BUILD)

    assert later is not None
    assert later.supports_poe is CapabilityStatus.UNKNOWN
    assert later.poe_ports is None


def test_runtime_multilayer_contradiction_suppresses_static_layer3_implication(
    tmp_path,
):
    store = CapabilitySnapshotStore(tmp_path / "runtime")
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=BUILD,
        session=ProbeSessionResult(
            session=ProbeSession(
                session_id="newer-multilayer-negative",
                packet_tracer_version=BUILD,
            ),
            results=[CapabilityProbeResult(
                probe_id="fresh-multilayer-intervlan",
                model="3560-24PS",
                capability="multilayer_intervlan",
                status=CapabilityStatus.UNSUPPORTED,
                execution_status=ProbeExecutionStatus.VERIFIED,
                evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
                verified=True,
                packet_tracer_version=BUILD,
                verification_method=CapabilityVerificationMethod.SIMULATION_TRACE,
            )],
        ),
    ))

    resolved = packet_tracer_enterprise_capability_adapter(
        BUILD, store=store,
    ).capabilities_for("3560-24PS", BUILD)

    assert resolved is not None
    assert CapabilityResolver.resolve_evidence(
        "multilayer_intervlan", resolved.evidence, BUILD,
    ) is CapabilityStatus.UNSUPPORTED
    assert resolved.layer3 is CapabilityStatus.UNKNOWN


def test_poe_projection_and_conflict_share_the_authoritative_winner():
    evidence = [
        CapabilityEvidence(
            capability="supports_poe",
            status=CapabilityStatus.SUPPORTED,
            source=EvidenceSource.CONTROLLED_PROBE,
            packet_tracer_version=BUILD,
            verified=True,
            observed_value=24,
            dimensions=_delivery_dimensions(active=24),
        ),
        CapabilityEvidence(
            capability="supports_poe",
            status=CapabilityStatus.UNSUPPORTED,
            source=EvidenceSource.PACKET_TRACER_RUNTIME,
            packet_tracer_version=BUILD,
            verified=True,
            dimensions=_delivery_dimensions(active=0),
        ),
    ]
    resolver = CapabilityResolver()
    base = resolver.resolve(CatalogDeviceFacts(model="tie", category="switch"))

    resolved = resolver.with_evidence(base, evidence, BUILD)
    conflicts = resolver.conflicts("tie", evidence, BUILD)

    assert resolved.supports_poe is CapabilityStatus.UNSUPPORTED
    assert resolved.poe_ports is None
    assert len(conflicts) == 1
    assert conflicts[0].winner is EvidenceSource.PACKET_TRACER_RUNTIME


def test_decided_delivery_claim_wins_same_authority_legacy_unknown():
    legacy = CapabilityEvidence(
        capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.PACKET_TRACER_RUNTIME,
        packet_tracer_version=BUILD,
        verified=True,
        observed_value=24,
    )
    delivery = CapabilityEvidence(
        capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        source=EvidenceSource.PACKET_TRACER_RUNTIME,
        packet_tracer_version=BUILD,
        verified=True,
        observed_value=2,
        dimensions=_delivery_dimensions(active=2, tested=2),
    )
    resolver = CapabilityResolver()
    base = resolver.resolve(CatalogDeviceFacts(model="tie", category="switch"))

    winner = resolver.winning_evidence("supports_poe", [legacy, delivery], BUILD)
    resolved = resolver.with_evidence(base, [legacy, delivery], BUILD)

    assert winner is not None and winner is delivery
    assert resolved.supports_poe is CapabilityStatus.SUPPORTED
    assert resolved.poe_ports == 2


def test_dynamic_adapter_result_mutation_cannot_change_a_later_execution(tmp_path):
    mutable = packet_tracer_enterprise_capability_adapter(
        BUILD,
        store=CapabilitySnapshotStore(tmp_path / "empty"),
    )
    first = mutable.capabilities_for("2960-24TT", BUILD)

    assert first is not None
    poe = next(item for item in first.evidence if item.capability == "supports_poe")
    poe.status = CapabilityStatus.SUPPORTED
    poe.observed_value = 24

    later = mutable.execution_snapshot().capabilities_for("2960-24TT", BUILD)

    assert later is not None
    assert later.supports_poe is CapabilityStatus.UNKNOWN
    assert later.poe_ports is None
