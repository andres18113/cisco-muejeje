"""Scope preliminary port and trunk measurements to the C31 setup run."""

from __future__ import annotations

from collections.abc import Callable

from ...application.use_cases.prequalify_server_pt import (
    ServerPtPrequalificationResult,
)
from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.port_inventory import (
    PortInventoryResolution,
    resolve_port_inventory,
)
from ..catalog.capability_providers import StaticVerifiedCapabilityProvider
from ..catalog.enterprise_capabilities import EnterpriseCapabilityAdapter
from ..catalog.measured_capabilities import measured_capability_evidence
from ..catalog.measured_port_inventories import backend_verified_port_inventory

BUILD = "9.0.1.0858"


def scoped_setup_evidence(
    result: ServerPtPrequalificationResult,
) -> tuple[EnterpriseCapabilityAdapter, Callable[..., PortInventoryResolution]]:
    """Use exact stored measurements in one setup without catalog promotion."""
    if not result.ready_for_catalog_review:
        raise ValueError("preliminary measurements do not authorize setup")
    ports = result.server_port_inventory
    probe = result.trunk_probe
    if ports is None or probe is None:
        raise ValueError("preliminary evidence is incomplete")
    evidence = probe.evidence()
    if (
        ports.model != "Server-PT"
        or ports.backend_version != BUILD
        or ports.installed_modules
        or "FastEthernet0" not in ports.ports
        or evidence is None
        or evidence.capability != "supports_trunk"
        or evidence.status is not CapabilityStatus.SUPPORTED
        or evidence.verified is not True
        or evidence.packet_tracer_version != BUILD
    ):
        raise ValueError("preliminary evidence does not bind the exact setup targets")
    catalog = EnterpriseCapabilityAdapter(
        providers=[
            StaticVerifiedCapabilityProvider(measured_capability_evidence()),
            StaticVerifiedCapabilityProvider({"2950T-24": [evidence]}),
        ],
        bound_packet_tracer_version=BUILD,
    )

    def port_inventory(
        model: str,
        *,
        backend: str = "packet_tracer",
        backend_version: str = "",
        installed_modules: list[str] | tuple[str, ...] | None = None,
    ) -> PortInventoryResolution:
        if model == "Server-PT":
            return resolve_port_inventory(
                (ports,),
                model,
                backend=backend,
                backend_version=backend_version,
                installed_modules=installed_modules,
            )
        return backend_verified_port_inventory(
            model,
            backend=backend,
            backend_version=backend_version,
            installed_modules=installed_modules,
        )

    return catalog, port_inventory
