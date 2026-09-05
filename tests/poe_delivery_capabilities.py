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
    PoEAuthorizedBinding,
)
from src.packet_tracer_mcp.domain.enterprise.scenarios.cp_scale_physical import (
    cp_scale_physical_design,
)
from src.packet_tracer_mcp.domain.enterprise.models.hardware import (
    EndpointPortBinding,
)
from src.packet_tracer_mcp.domain.enterprise.services.poe_claims import (
    PoEDeliveryClaimScope,
    PoEDeliveryTestedBinding,
    encode_poe_delivery_dimensions,
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


def synthetic_poe_authorized_bindings(
    ports: list[str] | tuple[str, ...],
) -> list[PoEAuthorizedBinding]:
    """Return an explicit test-only premise for generic compiler fixtures."""

    endpoint_profiles = (
        ("7960", "Switch"),
        ("AccessPoint-PT", "Port 0"),
        ("WiredEndDevice-PT", "FastEthernet0"),
    )
    return [
        PoEAuthorizedBinding(port, endpoint_model, endpoint_port)
        for port in ports
        for endpoint_model, endpoint_port in endpoint_profiles
    ]


class _DeliveryEvidenceProvider:
    def evidence_for(self, model: str, packet_tracer_version: str | None = None):
        if (
            model not in {"3560-24PS", "3650-24PS"}
            or packet_tracer_version != MEASURED_BACKEND_VERSION
        ):
            return ()
        return tuple(_synthetic_delivery_evidence()[model])


def _synthetic_delivery_evidence() -> dict[str, list[CapabilityEvidence]]:
    """Describe the exact CP-SCALE premise; never enter production providers."""

    design = cp_scale_physical_design()
    model_by_device = {
        device.id: device.model
        for site in design.sites
        for device in site.devices
    }
    bindings_by_scope: dict[tuple[str, str], list[EndpointPortBinding]] = {}
    for site in design.sites:
        for binding in site.endpoint_bindings:
            if binding.endpoint_model not in {"7960", "AccessPoint-PT"}:
                continue
            model = model_by_device[binding.device_id]
            key = (model, binding.device_id)
            bindings_by_scope.setdefault(key, []).append(binding)

    evidence: dict[str, list[CapabilityEvidence]] = {
        "3560-24PS": [],
        "3650-24PS": [],
    }
    for (model, fixture_id), bindings in sorted(
        bindings_by_scope.items()
    ):
        tested_bindings = tuple(
            PoEDeliveryTestedBinding(
                switch_port=binding.device_port,
                comparison_port=binding.device_port,
                endpoint_model=binding.endpoint_model,
                endpoint_port=binding.endpoint_port,
                candidate_state="powered",
                comparison_state="not_powered",
                candidate_indicator="synthetic downstream fixture powered",
                comparison_indicator="synthetic downstream fixture dark",
                candidate_ready=True,
                comparison_ready=True,
            )
            for binding in sorted(
                bindings, key=lambda item: item.device_port,
            )
        )
        dimensions = encode_poe_delivery_dimensions(PoEDeliveryClaimScope(
            candidate_model=model,
            packet_tracer_build=MEASURED_BACKEND_VERSION,
            access_ports=tuple(
                binding.switch_port for binding in tested_bindings
            ),
            tested_bindings=tested_bindings,
            active_bindings=tuple(
                binding.authorized_binding for binding in tested_bindings
            ),
            simultaneous_active_ports=len(tested_bindings),
            comparison_model="2960-24TT",
            observation_method="manual_visible_power_state",
            observer_id="downstream-test-fixture",
            observed_at="2026-09-04T15:00:00Z",
            cleanup_status="clean",
            inventory_restoration="restored",
        ))
        evidence[model].append(CapabilityEvidence(
            capability="supports_poe",
            status=CapabilityStatus.SUPPORTED,
            source=EvidenceSource.STATIC_OVERRIDE,
            source_detail=(
                "synthetic downstream-test exact delivery prerequisite: "
                f"{fixture_id}"
            ),
            packet_tracer_version=MEASURED_BACKEND_VERSION,
            verified=True,
            observed_value=len(tested_bindings),
            notes="Test-only assumption; not a governed PT observation.",
            dimensions=dimensions,
        ))
    return evidence


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
