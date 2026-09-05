"""Productive reuse of governed manual PoE delivery snapshots."""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityStatus,
    EvidenceSource,
    PoEAuthorizedBinding,
)
from src.packet_tracer_mcp.domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    CapabilitySnapshot,
    ProbeExecutionStatus,
    ProbeSession,
    ProbeSessionResult,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    PoEDeliveryClaimScope,
    PoEDeliveryTestedBinding,
    encode_poe_delivery_dimensions,
)
from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
    ManualVerificationCapabilityProvider,
    ProbeCapabilityProvider,
    RuntimeCapabilityProvider,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    packet_tracer_enterprise_capability_adapter,
)
from src.packet_tracer_mcp.infrastructure.persistence.capability_snapshot_store import (
    CapabilitySnapshotStore,
)


BUILD = "PT 9.0"


def _manual_delivery_result() -> CapabilityProbeResult:
    binding = PoEAuthorizedBinding("FastEthernet0/1", "7960", "Switch")
    tested = PoEDeliveryTestedBinding(
        switch_port=binding.switch_port,
        comparison_port="FastEthernet0/1",
        endpoint_model=binding.endpoint_model,
        endpoint_port=binding.endpoint_port,
        candidate_state="powered",
        comparison_state="not_powered",
        candidate_indicator="phone display booted",
        comparison_indicator="phone display remained dark",
        candidate_ready=True,
        comparison_ready=True,
    )
    dimensions = encode_poe_delivery_dimensions(PoEDeliveryClaimScope(
        candidate_model="3560-24PS",
        packet_tracer_build=BUILD,
        access_ports=(binding.switch_port,),
        tested_bindings=(tested,),
        active_bindings=(binding,),
        simultaneous_active_ports=1,
        comparison_model="2960-24TT",
        observation_method="manual_visible_power_state",
        observer_id="reviewer-1",
        observed_at="2026-09-04T15:00:00Z",
        cleanup_status="clean",
        inventory_restoration="restored",
    ))
    return CapabilityProbeResult(
        probe_id="poe-delivery-qualification",
        model="3560-24PS",
        capability="supports_poe",
        status=CapabilityStatus.SUPPORTED,
        execution_status=ProbeExecutionStatus.VERIFIED,
        evidence_source=EvidenceSource.MANUAL_VERIFICATION,
        verified=True,
        observed_value=1,
        packet_tracer_version=BUILD,
        dimensions=dimensions,
    )


def _store_manual_snapshot(tmp_path) -> CapabilitySnapshotStore:
    store = CapabilitySnapshotStore(tmp_path / "capabilities")
    result = _manual_delivery_result()
    store.save_runtime(CapabilitySnapshot(
        packet_tracer_version=BUILD,
        session=ProbeSessionResult(
            session=ProbeSession(
                session_id="manual-poe",
                packet_tracer_version=BUILD,
            ),
            results=[result],
        ),
    ))
    return store


def test_manual_provider_preserves_source_and_exact_scope(tmp_path):
    store = _store_manual_snapshot(tmp_path)

    evidence = tuple(
        ManualVerificationCapabilityProvider(store, BUILD).evidence_for(
            "3560-24PS", BUILD,
        )
    )

    assert len(evidence) == 1
    assert evidence[0].source is EvidenceSource.MANUAL_VERIFICATION
    assert evidence[0].dimensions == _manual_delivery_result().dimensions
    assert tuple(RuntimeCapabilityProvider(store, BUILD).evidence_for("3560-24PS", BUILD)) == ()
    assert tuple(ProbeCapabilityProvider(store, BUILD).evidence_for("3560-24PS", BUILD)) == ()


def test_productive_adapter_reuses_manual_snapshot_only_for_exact_model_and_build(tmp_path):
    store = _store_manual_snapshot(tmp_path)
    adapter = packet_tracer_enterprise_capability_adapter(BUILD, store=store)

    exact = adapter.capabilities_for("3560-24PS", BUILD)
    other_model = adapter.capabilities_for("3650-24PS", BUILD)
    other_build = adapter.capabilities_for("3560-24PS", "PT 10.0")

    assert exact is not None
    assert exact.supports_poe is CapabilityStatus.SUPPORTED
    assert exact.poe_ports == 1
    assert exact.poe_authorized_bindings == [
        PoEAuthorizedBinding("FastEthernet0/1", "7960", "Switch"),
    ]
    assert other_model is not None
    assert other_model.supports_poe is CapabilityStatus.UNKNOWN
    assert other_model.poe_authorized_bindings == []
    assert other_build is not None
    assert other_build.supports_poe is CapabilityStatus.UNKNOWN
    assert other_build.poe_ports is None
