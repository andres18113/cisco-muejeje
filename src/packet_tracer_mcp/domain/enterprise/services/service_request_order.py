"""The product's request order: cold HTTP by address before any other traffic.

SP-1 (SP1-03). In one invocation every selected client's first HTTP-by-IP
request must precede any DNS query, hostname request or other intentional
client traffic that could warm the paths it crosses. Reads that send nothing
(server state, a client's configured gateway or resolver, DHCP state) may run
at any time.

The rule is a rank on the verification DAG, not a harness step: rank 0 holds
HTTP-by-IP requests and traffic-free reads, rank 1 every other client-traffic
kind and everything that depends on one. The applicator orders by rank first,
so rank 1 starts only after every rank-0 expectation has been decided,
whatever its outcome. A dependency is never broken to honor the rank; ranks
propagate along dependencies instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..models.service_plan import ServiceVerificationKind
from ..models.verification import PrerequisiteKind, order_verification_expectations

DHCP_SETTLEMENT_PHASE = -1
COLD_REQUEST_PHASE = 0
LATER_TRAFFIC_PHASE = 1

#: Kinds that put client traffic on the network other than HTTP by address.
LATER_TRAFFIC_KINDS = frozenset(
    {
        ServiceVerificationKind.DNS_RESOLUTION,
        ServiceVerificationKind.DNS_NEGATIVE_CONTROL,
        ServiceVerificationKind.HTTP_BY_HOSTNAME,
        ServiceVerificationKind.HTTPS_FETCH,
        ServiceVerificationKind.NTP_SYNC,
        ServiceVerificationKind.TFTP_RETRIEVE,
        ServiceVerificationKind.SMTP_SEND,
        ServiceVerificationKind.POP3_RETRIEVE,
        ServiceVerificationKind.EMAIL_END_TO_END,
    }
)


def request_phases(expectations: Sequence[Any]) -> dict[str, int]:
    """Return each expectation's phase, raised to the phase of its dependencies.

    `expectations` must carry their verification prerequisites (the DAG form
    the applicator orders). An expectation that depends on a later-traffic
    expectation is itself later traffic, so no rank can ever point backwards.
    """
    phases: dict[str, int] = {}
    for item in order_verification_expectations(expectations):
        phase = (
            DHCP_SETTLEMENT_PHASE
            if item.kind is ServiceVerificationKind.DHCP_LEASE
            else LATER_TRAFFIC_PHASE
            if item.kind in LATER_TRAFFIC_KINDS
            else COLD_REQUEST_PHASE
        )
        for prerequisite in item.verification_prerequisites:
            if prerequisite.kind is PrerequisiteKind.VERIFICATION_VERIFIED:
                phase = max(phase, phases.get(prerequisite.reference_id, 0))
        phases[item.id] = phase
    return phases
