"""CP-SCALE FULL qualification policy declared for Packet Tracer builds.

Packet Tracer 9.0.1.0858 governs the Voice surfaces E7 observes: typed
`telephony-service` configuration, extension bindings, and registration read
from a fresh `show ephone`. It exposes no governed structured API that dials,
answers, or hangs up a 7960 (docs/architecture/enterprise-voice.md), so call
behavior is UNQUALIFIED on this backend. E7 stays backend-neutral and keeps its
call expectations; FULL records the dimension instead of requiring it.
Wireless association and intersite calling stay outside the product.

Every dimension is declared explicitly. A build without a declaration has no
policy, and FULL admission refuses it instead of inheriting one. The
declaration names its exact backend and build; preflight admits it only when
both equal the backend build the session observes.
"""

from __future__ import annotations

from ...application.cp_scale_live.contracts import (
    CPScaleBackendQualificationPolicy,
    CPScaleQualificationStatus as Status,
)
from ...domain.enterprise.models.discovery import CapabilityBackend


_DECLARED_BUILDS = frozenset({"9.0.1.0858"})


def packet_tracer_cp_scale_qualification_policy(
    packet_tracer_version: str,
) -> CPScaleBackendQualificationPolicy:
    """Return the declared FULL policy for one exact Packet Tracer build."""

    if packet_tracer_version not in _DECLARED_BUILDS:
        raise ValueError(
            "No CP-SCALE qualification policy is declared for Packet Tracer "
            f"{packet_tracer_version!r}."
        )
    return CPScaleBackendQualificationPolicy(
        backend=CapabilityBackend.PACKET_TRACER.value,
        backend_version=packet_tracer_version,
        voice_configuration=Status.QUALIFIED,
        phone_registration=Status.QUALIFIED,
        extension_binding=Status.QUALIFIED,
        call_behavior=Status.UNQUALIFIED,
        wireless_association=Status.UNQUALIFIED,
        intersite_calling=False,
    )
