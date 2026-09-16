"""Typed boundary between the IoT connectivity use case and any real backend.

The port returns readings, never states. Classification lives in the domain so
that a backend adapter cannot decide on its own that something is associated,
and so that a second backend answers the same four questions in the same shape.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...domain.enterprise.models.wireless_connectivity import (
    IntendedNetworkSegment,
    WirelessAssociationIntent,
    WirelessAssociationReading,
    WirelessAttachmentReading,
    WirelessCapabilityAudit,
    WirelessConfigurationOutcome,
)


@runtime_checkable
class WirelessConnectivityPort(Protocol):
    """Configure and read one wireless endpoint, with no judgment attached."""

    @property
    def backend(self) -> str: ...

    @property
    def backend_version(self) -> str: ...

    def capability_audit(self) -> WirelessCapabilityAudit: ...

    def configure_association(
        self, intent: WirelessAssociationIntent,
    ) -> WirelessConfigurationOutcome: ...

    def observe_association(
        self, intent: WirelessAssociationIntent,
    ) -> WirelessAssociationReading: ...

    def observe_attachment(
        self,
        intent: WirelessAssociationIntent,
        segment: IntendedNetworkSegment,
    ) -> WirelessAttachmentReading: ...
