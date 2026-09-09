"""Narrow backend qualification operations; run state belongs to coordinator."""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from .errors import CanonicalLiveFailure
from .run_contracts import CPScaleCapabilityProbe, CPScaleBridgeStatus
from .session import CPScaleSessionPort
from ..use_cases.qualify_cp_scale_live import (
    canonical_required_capability_probes, canonical_capability_probe_error,
    canonical_cleanup_restoration_error,
    canonical_bridge_polling_error,
)
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ..use_cases.capability_discovery import CapabilityDiscoveryService
from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.discovery import ProbeLevel, ProbeRequest


class CPScaleBackendQualification:
    def __init__(self, *, compose: Callable[..., EnterpriseReferenceComposition],
                 discovery_factory: Callable[[CPScaleSessionPort, str], CapabilityDiscoveryService],
                 requirements=canonical_required_capability_probes,
                 probe_error=canonical_capability_probe_error,
                 restoration_error=canonical_cleanup_restoration_error,
                 file_alive=lambda: False) -> None:
        self.compose = compose
        self.discovery_factory = discovery_factory
        self.requirements = requirements
        self.probe_error = probe_error
        self.restoration_error = restoration_error
        self.file_alive = file_alive

    def polling_failure_status(self, session: CPScaleSessionPort) -> CPScaleBridgeStatus:
        status = session.status()
        try:
            status = replace(status, file_bridge_alive=self.file_alive())
        except Exception:
            pass
        return status

    def polling_error(self, status: CPScaleBridgeStatus) -> str:
        facts = {"connected": status.connected, "last_poll_ago": status.last_poll_ago,
            "unauth_count": status.unauth_count, "unauth_paths": status.unauth_paths,
            "token_id": status.token_id}
        if status.file_bridge_alive is not None:
            facts["file_bridge_alive"] = status.file_bridge_alive
        return canonical_bridge_polling_error(facts)

    def validate_composition(self, composition: EnterpriseReferenceComposition, *, post_probe: bool = False) -> None:
        if not composition.valid:
            prefix = "Canonical post-probe composition failed: " if post_probe else "Canonical composition failed: "
            raise CanonicalLiveFailure(prefix + "; ".join(composition.issues))
        assert composition.topology is not None
        assert composition.configuration is not None
        assert composition.control_plane is not None

    def probe(self, discovery: CapabilityDiscoveryService, version: str,
              model: str, capabilities: tuple[str, ...]) -> CPScaleCapabilityProbe:
        snapshot, cached = discovery.run(ProbeRequest(models=[model], capabilities=list(capabilities),
            probe_level=ProbeLevel.LOGICAL, force=True, packet_tracer_version=version))
        error = self.probe_error(snapshot, model=model, capabilities=list(capabilities), packet_tracer_version=version)
        return CPScaleCapabilityProbe(model, capabilities, snapshot, cached, error)

    def unresolved(self, composition: EnterpriseReferenceComposition,
                   requirements: tuple[tuple[str, tuple[str, ...]], ...]) -> tuple[str, ...]:
        return tuple(sorted(f"{model}:{capability}" for model, capabilities in requirements for capability in capabilities
            if composition.capabilities.get(model) is None
            or getattr(composition.capabilities[model], capability, CapabilityStatus.UNKNOWN) is not CapabilityStatus.SUPPORTED))
