"""The reviewed Server-PT native default transitions, keyed by backend build.

One record, from one measurement. D-DHCP v3 attempt 2 of campaign
`SERVER-PT-DIAG-0EA-01` ran at commit `5296984` on build `9.0.1.0858` and took
six bounded readings of the stock `serverPool` around each intervention. The
first difference falls in the interval of the WHOLE `configurePcIp` call that
gives the Server-PT its static address, and it moves exactly four fields:
`network`, `mask`, `start` and `end`. Writing the intended pool while the
process was still disabled and enabling the process each added no further
difference.

What this table is for: the domain decision compares an observed pair against
these records and admits nothing it cannot match field for field. The values
are therefore the point. They are copied from the immutable record, not
recomputed, and a reader who wants to check them reads the record named in
`evidence`.

What this table is not: it is not a capability, not an allocation permission
and not a general rule. Product DHCP capabilities stay UNKNOWN. Another build,
another model, another interface or another intervention is a different
question that needs its own authorized measurement and its own record here; the
absence of a record is a refusal, which is why this file has exactly one.
"""

from __future__ import annotations

from ...domain.enterprise.services.dhcp_native_default_lifecycle import (
    AdmittedNativeDefaultTransition,
    NativeDefaultContext,
)

#: The backend call the measurement brackets. Named as the whole call on
#: purpose: the six readings bracket an interval, and no reading inside it
#: attributes the change to one internal setter.
WHOLE_CONFIGURE_PC_IP = "whole_configure_pc_ip_call"

#: The record identity the values below were copied from.
D_DHCP_ATTEMPT_2_RECORD = (
    "SERVER-PT-DIAG-0EA-01:D-DHCP:v3:attempt-2:d-dhcp-2026-09-21T20-01-43Z-dffd6c3b"
)

_SERVER_PT_9_0_1_0858 = AdmittedNativeDefaultTransition(
    context=NativeDefaultContext(
        model="Server-PT",
        backend_version="9.0.1.0858",
        interface="FastEthernet0",
        intervention=WHOLE_CONFIGURE_PC_IP,
    ),
    pool_name="serverPool",
    # The stock disabled state, readings `d0_baseline` and `d0_control`.
    before={
        "name": "serverPool",
        "network": "0.0.0.0",
        "mask": "0.0.0.0",
        "gateway": "0.0.0.0",
        "dns": "0.0.0.0",
        "start": "0.0.0.0",
        "end": "0.0.2.0",
        "max": 512,
    },
    # Reading `d1_after_server_address`, and unchanged through `d4`.
    after={
        "name": "serverPool",
        "network": "192.0.2.0",
        "mask": "255.255.255.0",
        "gateway": "0.0.0.0",
        "dns": "0.0.0.0",
        "start": "192.0.2.0",
        "end": "192.0.3.255",
        "max": 512,
    },
    changed_fields=("end", "mask", "network", "start"),
    evidence=D_DHCP_ATTEMPT_2_RECORD,
)

#: Reviewed transitions per exact backend build. A build absent from this table
#: has no admitted transition, and the domain decision refuses accordingly.
_BY_BACKEND_VERSION: dict[str, tuple[AdmittedNativeDefaultTransition, ...]] = {
    "9.0.1.0858": (_SERVER_PT_9_0_1_0858,),
}


def admitted_native_default_transitions(
    backend_version: str,
) -> tuple[AdmittedNativeDefaultTransition, ...]:
    """Return the reviewed transitions of one exact build, or none.

    Exact string match, with no normalization and no nearest-version fallback:
    a build this project never measured must produce an empty tuple, because an
    empty tuple is what makes the domain decision refuse.
    """
    return _BY_BACKEND_VERSION.get(backend_version, ())
