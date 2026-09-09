"""Backend qualification policy after local preflight, before build stages."""
from __future__ import annotations
from dataclasses import replace
from typing import Callable

from .errors import CanonicalLiveFailure
from .run_contracts import CPScaleRunReport, CPScaleBackendProgress, CPScaleCapabilityQualification, CPScaleCapabilityProbe
from .session import CPScaleSessionPort
from ..use_cases.qualify_cp_scale_live import (
    canonical_required_capability_probes, canonical_capability_probe_error,
    canonical_cleanup_restoration_error,
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

    def polling_failure_status(self, session: CPScaleSessionPort) -> dict[str, object]:
        status = session.status()
        try:
            status["file_bridge_alive"] = self.file_alive()
        except Exception:
            pass
        return status

    def qualify(self, session: CPScaleSessionPort, report: CPScaleRunReport, progress: CPScaleBackendProgress) -> EnterpriseReferenceComposition:
        version = report.packet_tracer_version
        progress.composition = self.compose(packet_tracer_version=version)
        if not progress.composition.valid:
            raise CanonicalLiveFailure("Canonical composition failed: " + "; ".join(progress.composition.issues))
        assert progress.composition.topology is not None
        assert progress.composition.configuration is not None
        assert progress.composition.control_plane is not None
        required = self.requirements(progress.composition)
        discovery = self.discovery_factory(session, version)
        sessions: tuple[CPScaleCapabilityProbe, ...] = ()
        requirements = tuple((model, tuple(capabilities)) for model, capabilities in required.items())
        for model, capabilities in required.items():
            snapshot, cached = discovery.run(ProbeRequest(models=[model], capabilities=capabilities,
                probe_level=ProbeLevel.LOGICAL, force=True, packet_tracer_version=version))
            error = self.probe_error(snapshot, model=model, capabilities=capabilities, packet_tracer_version=version)
            sessions += (CPScaleCapabilityProbe(model, tuple(capabilities), snapshot, cached, error),)
            if error:
                report.capability_prequalification = CPScaleCapabilityQualification(requirements, sessions)
                raise CanonicalLiveFailure(error)
        first = session.physical.observe_workspace()
        second = session.physical.observe_workspace()
        error = self.restoration_error(report.baseline, first, second)
        report.capability_prequalification = CPScaleCapabilityQualification(requirements, sessions, first, second, error)
        if error:
            raise CanonicalLiveFailure(error)
        progress.composition = self.compose(packet_tracer_version=version)
        if not progress.composition.valid:
            raise CanonicalLiveFailure("Canonical post-probe composition failed: " + "; ".join(progress.composition.issues))
        unresolved = sorted(f"{model}:{capability}" for model, capabilities in required.items() for capability in capabilities
            if progress.composition.capabilities.get(model) is None
            or getattr(progress.composition.capabilities[model], capability, CapabilityStatus.UNKNOWN) is not CapabilityStatus.SUPPORTED)
        report.capability_prequalification = replace(report.capability_prequalification, unresolved=tuple(unresolved))
        if unresolved:
            raise CanonicalLiveFailure("Canonical composition did not consume VERIFIED capability evidence: " + ", ".join(unresolved))
        return progress.composition
