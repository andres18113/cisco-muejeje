"""The sole transport-close owner, allocated before acquisition can fail."""
from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .live_bridge import PacketTracerHttpTransport
    from ...application.cp_scale_live.session import CPScaleRuntimeResources
    from ...application.use_cases.deploy_enterprise_topology import PhysicalTopologyRuntime


class PacketTracerCPScaleSession:
    def __init__(
        self,
        *,
        transport_factory: Callable[[], PacketTracerHttpTransport],
        physical_factory: Callable[[PacketTracerHttpTransport], PhysicalTopologyRuntime],
        runtime_factory: Callable[[PacketTracerHttpTransport, PhysicalTopologyRuntime], CPScaleRuntimeResources],
    ) -> None:
        self._transport_factory = transport_factory
        self._physical_factory = physical_factory
        self._runtime_factory = runtime_factory
        self._transport = None
        self._physical = None
        self._runtimes = None
        self._started = False
        self._closed = False

    def start(self) -> bool:
        if self._closed:
            raise RuntimeError("A closed session cannot be acquired again.")
        if self._started:
            return True
        if self._transport is None:
            self._transport = self._transport_factory()
        if not self._transport.start(timeout_seconds=10.0):
            return False
        self._physical = self._physical_factory(self._transport)
        self._started = True
        return True

    @property
    def physical(self) -> PhysicalTopologyRuntime | None:
        return self._physical

    @property
    def transport(self) -> PacketTracerHttpTransport:
        # Concrete composition may bind observation adapters; application uses
        # only status/connected/channel through its session port.
        if self._transport is None:
            raise RuntimeError("Session transport has not been acquired.")
        return self._transport

    @property
    def connected(self) -> bool:
        return self.transport.is_connected

    @property
    def channel(self) -> str:
        return self.transport.bridge_transport

    def status(self) -> dict[str, object]:
        return self.transport.status_dict()

    def acquire_runtimes(self) -> CPScaleRuntimeResources:
        if self._closed or not self._started:
            raise RuntimeError("Runtime acquisition requires an open session.")
        if self._runtimes is None:
            self._runtimes = self._runtime_factory(self.transport, self._physical)
        return self._runtimes

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._transport is not None:
            self._transport.stop()
