"""Derive PoE capacity qualification scopes from governed CP-SCALE truth."""

from __future__ import annotations

from ...domain.enterprise.models.capabilities import PoEAuthorizedBinding
from ...domain.enterprise.models.poe_capacity import (
    PoECapacityQualificationPlan,
    PoEModelQualificationPlan,
)
from ...domain.enterprise.scenarios.cp_scale import cp_scale_intent
from ...domain.enterprise.scenarios.cp_scale_physical import (
    cp_scale_physical_design,
)
from ...domain.enterprise.services.endpoint_expander import EndpointGroupExpander
from ...domain.enterprise.services.enterprise_designer import EnterpriseDesigner
from ...domain.enterprise.services.naming import DeterministicNamingService
from .compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    cp_scale_canonical_stage_includes_device,
)


def cp_scale_poe_capacity_qualification_plan(
    packet_tracer_build: str,
    target_stage: CPScaleCanonicalStage = CPScaleCanonicalStage.ROUTER0_BRANCH,
) -> PoECapacityQualificationPlan:
    """Derive exact unique powered-binding scopes in governed occurrence order."""

    designed = EnterpriseDesigner().design(cp_scale_intent())
    if not designed.validation.is_valid or designed.plan is None:
        raise ValueError(
            "CP-SCALE E4 design is invalid: "
            + "; ".join(item.message for item in designed.validation.errors)
        )

    powered_endpoint_ids = {
        endpoint.id
        for endpoint in EndpointGroupExpander().expand(
            designed.plan, DeterministicNamingService(),
        )
        if endpoint.requires_poe
    }
    physical = cp_scale_physical_design()
    devices = {
        device.id: device
        for site in physical.sites
        for device in site.devices
        if cp_scale_canonical_stage_includes_device(
            target_stage,
            device.id,
            device.site_id,
            device.parent_group,
        )
    }

    by_model: dict[str, list[PoEAuthorizedBinding]] = {}
    seen_by_model: dict[str, set[PoEAuthorizedBinding]] = {}
    for site in physical.sites:
        for binding in site.endpoint_bindings:
            device = devices.get(binding.device_id)
            if device is None or binding.endpoint_id not in powered_endpoint_ids:
                continue
            exact = PoEAuthorizedBinding(
                binding.device_port,
                binding.endpoint_model,
                binding.endpoint_port,
            )
            seen = seen_by_model.setdefault(device.model, set())
            if exact in seen:
                continue
            seen.add(exact)
            by_model.setdefault(device.model, []).append(exact)

    models = tuple(
        PoEModelQualificationPlan(
            packet_tracer_build=packet_tracer_build,
            candidate_model=model,
            bindings=tuple(bindings),
            simultaneous_active_ports=len(bindings),
        )
        for model, bindings in by_model.items()
    )
    return PoECapacityQualificationPlan(
        packet_tracer_build=packet_tracer_build,
        target_stage=target_stage.value,
        models=models,
    )
