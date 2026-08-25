"""E7 voice capability profiles, derived from measured device evidence.

Nothing here promotes a capability because of a model name. Every dimension is
read from the same `DeviceCapabilities` a probe wrote into the snapshot store,
so a router that has not been measured resolves UNKNOWN and its voice actions
are skipped rather than attempted -- the same fail-closed rule PoE now follows.

The mapping is deliberately narrow. `supports_cme` is what a controlled probe
can actually demonstrate on a router: that `telephony-service` is accepted and
reads back. Whether one particular phone has registered is not a property of the
router model and is never answered here -- that is a per-phone observation, and
E7 makes it against a live `show ephone`.
"""

from __future__ import annotations

from ...domain.enterprise.models.capabilities import (
    CapabilityStatus,
    DeviceCapabilities,
)
from ...domain.enterprise.models.voice_plan import (
    VoiceCapabilityDimension,
    VoiceCapabilityProfile,
    VoiceCapabilityStatus,
)


_STATUS = {
    CapabilityStatus.SUPPORTED: VoiceCapabilityStatus.SUPPORTED,
    CapabilityStatus.UNSUPPORTED: VoiceCapabilityStatus.UNSUPPORTED,
    CapabilityStatus.UNKNOWN: VoiceCapabilityStatus.UNKNOWN,
}


def _status(value: CapabilityStatus | None) -> VoiceCapabilityStatus:
    if value is None:
        return VoiceCapabilityStatus.UNKNOWN
    return _STATUS.get(value, VoiceCapabilityStatus.UNKNOWN)


def voice_capability_profile(
    capabilities: DeviceCapabilities,
    *,
    packet_tracer_version: str | None = None,
) -> VoiceCapabilityProfile:
    """Translate one model's measured facts into the dimensions E7 gates on."""
    cme = _status(capabilities.supports_cme)
    dhcp = _status(capabilities.supports_dhcp_server)
    return VoiceCapabilityProfile(
        model=capabilities.model,
        dimensions={
            # Everything written under `telephony-service` rides on one
            # measured fact: that the router accepts it and reads it back.
            VoiceCapabilityDimension.CALL_CONTROL_CONFIG: cme,
            VoiceCapabilityDimension.PHONE_EXTENSION_CONFIG: cme,
            VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP: cme,
            # Reading a registration table is a CME facility. Whether a given
            # phone appears in it, registered or not, is observed per phone.
            VoiceCapabilityDimension.PHONE_REGISTRATION: cme,
            # Option 150 is an attribute of a DHCP pool, so it needs the pool.
            VoiceCapabilityDimension.VOICE_DHCP_OPTIONS: (
                cme if cme is VoiceCapabilityStatus.UNSUPPORTED else dhcp
            ),
            # No call driver exists in this codebase: the only shipped phone
            # control returns UNOBSERVABLE and never dials. Claiming otherwise
            # would let a call expectation look skipped rather than unbuilt.
            VoiceCapabilityDimension.CALL_INITIATION: (
                VoiceCapabilityStatus.UNOBSERVABLE
            ),
            VoiceCapabilityDimension.CALL_STATE_READBACK: (
                VoiceCapabilityStatus.UNOBSERVABLE
            ),
            # The renderer refuses to emit intersite voice: it is not verified
            # on this backend, and that refusal is the honest status.
            VoiceCapabilityDimension.INTERSITE_CALLING: (
                VoiceCapabilityStatus.UNSUPPORTED
            ),
        },
        evidence_source=capabilities.source,
        packet_tracer_version=(
            packet_tracer_version or capabilities.packet_tracer_version
        ),
        capability_readiness=dict(capabilities.capability_readiness),
    )


def voice_capability_profiles(
    capabilities: dict[str, DeviceCapabilities],
    *,
    packet_tracer_version: str | None = None,
) -> dict[str, VoiceCapabilityProfile]:
    """Profiles for every model in a composition, keyed exactly as E7 keys them."""
    return {
        model: voice_capability_profile(
            item, packet_tracer_version=packet_tracer_version,
        )
        for model, item in sorted(capabilities.items())
    }
