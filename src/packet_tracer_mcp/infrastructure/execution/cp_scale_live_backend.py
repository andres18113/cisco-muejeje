"""Concrete local readers and capability adapters for CLI composition."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ...application.cp_scale_live.checkpoint import CPScaleCheckpointRepository
from ...application.cp_scale_live.errors import CanonicalLiveFailure
from ...application.use_cases.capability_discovery import CapabilityDiscoveryService
from ...application.use_cases.compose_cp_scale_canonical import compose_cp_scale_canonical
from ...application.use_cases.qualify_cp_scale_live import read_git_repository_state
from ..catalog.enterprise_capabilities import EnterpriseCapabilityAdapter
from ..persistence.capability_snapshot_store import CapabilitySnapshotStore
from .probe_runtime import PacketTracerBridgeProbeRuntime


GOVERNED_SOURCE_PATHS = (
    "src", "tests", "tools/cp_scale_canonical_live.py",
    "docs/reference/cp-scale/diseno_logico_IMP.md", "docs/reference/cp-scale/topologia_completa_IMP.md",
)


class CPScaleCheckpointRepositoryReader:
    def __init__(self, governed_root: Path) -> None:
        self.root = governed_root

    def read(self):
        return read_git_repository_state(self.root)

    def _git(self, *arguments: str) -> str:
        return subprocess.run(["git", *arguments], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def resumed(self, source_head: str) -> CPScaleCheckpointRepository:
        repository = self.read()
        try:
            upstream_head = self._git("rev-parse", "@{upstream}")
            dirty = bool(self._git("status", "--porcelain"))
            diff = subprocess.run(["git", "diff", "--quiet", source_head, "--", *GOVERNED_SOURCE_PATHS],
                cwd=self.root, check=False, capture_output=True, text=True)
            if diff.returncode not in {0, 1}:
                raise CanonicalLiveFailure("Governed source comparison failed: " + diff.stderr.strip())
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CanonicalLiveFailure(f"Checkpoint repository revalidation failed: {exc}") from exc
        return CPScaleCheckpointRepository(repository, upstream_head, dirty, diff.returncode == 1)


class CPScaleCapabilityAdapters:
    """Lazy store creation preserves the baseline-before-store acquisition order."""
    def __init__(self, governed_root: Path) -> None:
        self.root = governed_root
        self._store = None

    @property
    def store(self):
        if self._store is None:
            self._store = CapabilitySnapshotStore(self.root / "data" / "capabilities")
        return self._store

    def compose(self, *, packet_tracer_version: str):
        return compose_cp_scale_canonical(packet_tracer_version=packet_tracer_version, capability_store=self.store)

    def discovery(self, session, version: str):
        transport = session.transport
        runtime = PacketTracerBridgeProbeRuntime(transport.send_and_wait, packet_tracer_version=version,
            send=transport.send, transport_channel=transport.bridge_transport)
        return CapabilityDiscoveryService(runtime=runtime, snapshots=self.store,
            identity_for=EnterpriseCapabilityAdapter().identity_for,
            access_ports_for=EnterpriseCapabilityAdapter().access_ports_for)
