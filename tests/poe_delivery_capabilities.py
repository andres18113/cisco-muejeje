"""Explicit delivery-backed capability fixture for downstream plan tests.

This is synthetic test evidence, not a governed Packet Tracer observation. It
lets downstream compiler tests state their prerequisite without weakening the
productive fail-closed baseline.
"""

from __future__ import annotations

from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    compose_cp_scale_canonical as _compose_cp_scale_canonical,
)
from src.packet_tracer_mcp.domain.enterprise.models.capabilities import (
    CapabilityEvidence,
    CapabilityStatus,
    EvidenceSource,
)
from src.packet_tracer_mcp.infrastructure.catalog.capability_providers import (
    StaticVerifiedCapabilityProvider,
)
from src.packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_capabilities import (
    measured_capability_evidence,
)
from src.packet_tracer_mcp.infrastructure.catalog.measured_port_inventories import (
    MEASURED_BACKEND_VERSION,
)


class _DeliveryEvidenceProvider:
    def evidence_for(self, model: str, packet_tracer_version: str | None = None):
        if (
            model not in {"3560-24PS", "3650-24PS"}
            or packet_tracer_version != MEASURED_BACKEND_VERSION
        ):
            return ()
        return (CapabilityEvidence(
            capability="supports_poe",
            status=CapabilityStatus.SUPPORTED,
            source=EvidenceSource.STATIC_OVERRIDE,
            source_detail="synthetic downstream-test delivery prerequisite",
            packet_tracer_version=MEASURED_BACKEND_VERSION,
            verified=True,
            observed_value=24,
            notes="Test-only assumption: 24 access ports delivered power.",
            dimensions={
                "poe_access_port_count": "24",
                "poe_delivery_tested_ports": "24",
                "poe_delivery_active_ports": "24",
            },
        ),)


def delivery_qualified_capability_catalog() -> EnterpriseCapabilityAdapter:
    """Return governed non-PoE facts plus an explicit test-only PoE premise."""

    return EnterpriseCapabilityAdapter(
        providers=[
            StaticVerifiedCapabilityProvider(measured_capability_evidence()),
            _DeliveryEvidenceProvider(),
        ],
        bound_packet_tracer_version=MEASURED_BACKEND_VERSION,
    )


def compose_delivery_qualified_cp_scale_canonical(**kwargs):
    """Compose downstream fixtures without claiming the premise was measured."""

    kwargs["capability_catalog"] = delivery_qualified_capability_catalog()
    return _compose_cp_scale_canonical(**kwargs)
