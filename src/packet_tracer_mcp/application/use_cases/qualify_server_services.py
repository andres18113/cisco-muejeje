"""Governed Server-PT qualification runner: one authorized stage per invocation.

The runner measures Packet Tracer engine, HTTPS and DHCP facts that S2, S3 and S1b
depend on. It is not a product operation, and it never runs by default: a
stage runs only when explicitly requested, under a complete stage- and
SHA-specific authorization, from the exact clean published checkout that the
authorization names.

The order of the work is the contract:

1. **Local admission** needs no channel. The request rule (domain), fixture
   resolution, process isolation and the repository identity are checked, and
   the write-ahead record is created. A refusal here has touched nothing.
2. **Contact.** One transport is opened for the authorized channel. Every
   engine operation, including those made inside the production runtimes,
   goes through one `OperationLedger`, which counts it against the stage
   ceiling. The executable build and the empty workspace are read before any
   effect.
3. **Effects.** Fixtures and experiments run under the ledger reserve and the
   effect gate. The outcome of the preceding effect is evaluated before the
   next one is admitted, so no setup whose result nobody read authorizes a
   further mutation. New experiments stop at the first contradiction, at an
   outcome-unknown effect, when the budget runs out, or when the record cannot
   advance.
4. **Finalization** always runs once any effect was admitted. It releases
   owned engine state, removes only the devices this invocation's runtime
   attempted to create, and reads the workspace twice. Its failures are
   secondary and never replace the primary outcome.

Two things are deliberately impossible. No call reaches Packet Tracer outside
the ledger, and no experiment runs outside the injected experimental-capability
scope, which exists only here and never in a catalog or in the product
composition.

This module is the stable entry façade. The implementation lives in
`application.server_service_qualification`, one owner per responsibility and
one module per workflow family. The façade owns the public entry signature and
re-exports, by explicit import, every public name the module has always had
and the two private helpers the SP-2 operator tooling imports. Each name is
the canonical object of its owner, never a copy.
"""

from __future__ import annotations

from ...domain.enterprise.models.service_qualification import QualificationRequest
from ..server_service_qualification.contracts import (
    MAX_DETAIL,
    CampaignQualificationAuthority,
    IsolationObservation,
    Q3ProductContract,
    QualificationBoundaries,
    QualificationCancelled,
    QualificationResult,
    RuntimeIdentity,
    SendAndWait,
)
from ..server_service_qualification.coordinator import run_qualification
from ..server_service_qualification.dhcp_observations import (
    D_DHCP_DEFAULT_PURPOSE,
    Q3_DEFAULT_PURPOSE,
    Q3_FL_DEFAULT_PURPOSE,
)
from ..server_service_qualification.execution import NOT_SELECTED
from ..server_service_qualification.ledgered_transport import LedgeredTransport
from ..server_service_qualification.operation_budget import (
    LedgerPhase,
    OperationLedger,
    OperationRefused,
)
from ..server_service_qualification.product_support import (
    DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
    SP1_CAPTURE_DEADLINE_SECONDS,
    SP1_CAPTURE_SAMPLE_CALLS,
)
from ..server_service_qualification.product_support import (
    capability_digest as _sp2_capability_digest,
)
from ..server_service_qualification.workflows.https_page import FETCH_OPERATIONS
from ..server_service_qualification.workflows.sp1_routed_product import (
    SP1_BINDING_KINDS,
    SP1_REQUIRED_CLIENT_KINDS,
)
from ..server_service_qualification.workflows.sp2_mixed_product import (
    SP2_CAPACITY_CONFIGURATION_SHA256,
    SP2_CAPACITY_MANIFEST_SHA256,
    SP2_CAPACITY_NORMALIZED_SERVICES_SHA256,
    SP2_CAPACITY_SERVICE_CAPABILITIES_SHA256,
    SP2_CAPACITY_TOPOLOGY_SHA256,
    SP2_MIXED_BUILD,
    SP2_MIXED_CLIENT_KINDS,
    SP2_MIXED_CONFIGURATION_SHA256,
    SP2_MIXED_HELPERS,
    SP2_MIXED_MANIFEST_SHA256,
    SP2_MIXED_NORMALIZED_SERVICES_SHA256,
    SP2_MIXED_PHYSICAL_POOLS,
    SP2_MIXED_ROUTED_PAIRS,
    SP2_MIXED_ROUTERS,
    SP2_MIXED_SERVICE_CAPABILITIES_SHA256,
    SP2_MIXED_TOPOLOGY_SHA256,
)
from ..server_service_qualification.workflows.sp2_mixed_product import (
    sp2_mixed_normalized_services_hash as _sp2_mixed_normalized_services_hash,
)
from ..server_service_qualification.workflows.sp2_remote_relay import (
    SP2_REMOTE_BUILD,
    SP2_REMOTE_CLIENT,
    SP2_REMOTE_CONFIGURATION_SHA256,
    SP2_REMOTE_INTENT_SHA256,
    SP2_REMOTE_MANIFEST_SHA256,
    SP2_REMOTE_POOL,
    SP2_REMOTE_REQUIRED_DEVICE_EVIDENCE,
    SP2_REMOTE_ROUTERS,
    SP2_REMOTE_SERVER,
    SP2_REMOTE_SERVICE_CAPABILITIES_SHA256,
    SP2_REMOTE_SERVICES_SHA256,
    SP2_REMOTE_TOPOLOGY_SHA256,
)

__all__ = [
    "DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE",
    "D_DHCP_DEFAULT_PURPOSE",
    "FETCH_OPERATIONS",
    "MAX_DETAIL",
    "NOT_SELECTED",
    "Q3_DEFAULT_PURPOSE",
    "Q3_FL_DEFAULT_PURPOSE",
    "SP1_BINDING_KINDS",
    "SP1_CAPTURE_DEADLINE_SECONDS",
    "SP1_CAPTURE_SAMPLE_CALLS",
    "SP1_REQUIRED_CLIENT_KINDS",
    "SP2_CAPACITY_CONFIGURATION_SHA256",
    "SP2_CAPACITY_MANIFEST_SHA256",
    "SP2_CAPACITY_NORMALIZED_SERVICES_SHA256",
    "SP2_CAPACITY_SERVICE_CAPABILITIES_SHA256",
    "SP2_CAPACITY_TOPOLOGY_SHA256",
    "SP2_MIXED_BUILD",
    "SP2_MIXED_CLIENT_KINDS",
    "SP2_MIXED_CONFIGURATION_SHA256",
    "SP2_MIXED_HELPERS",
    "SP2_MIXED_MANIFEST_SHA256",
    "SP2_MIXED_NORMALIZED_SERVICES_SHA256",
    "SP2_MIXED_PHYSICAL_POOLS",
    "SP2_MIXED_ROUTED_PAIRS",
    "SP2_MIXED_ROUTERS",
    "SP2_MIXED_SERVICE_CAPABILITIES_SHA256",
    "SP2_MIXED_TOPOLOGY_SHA256",
    "SP2_REMOTE_BUILD",
    "SP2_REMOTE_CLIENT",
    "SP2_REMOTE_CONFIGURATION_SHA256",
    "SP2_REMOTE_INTENT_SHA256",
    "SP2_REMOTE_MANIFEST_SHA256",
    "SP2_REMOTE_POOL",
    "SP2_REMOTE_REQUIRED_DEVICE_EVIDENCE",
    "SP2_REMOTE_ROUTERS",
    "SP2_REMOTE_SERVER",
    "SP2_REMOTE_SERVICES_SHA256",
    "SP2_REMOTE_SERVICE_CAPABILITIES_SHA256",
    "SP2_REMOTE_TOPOLOGY_SHA256",
    "CampaignQualificationAuthority",
    "IsolationObservation",
    "LedgerPhase",
    "LedgeredTransport",
    "OperationLedger",
    "OperationRefused",
    "Q3ProductContract",
    "QualificationBoundaries",
    "QualificationCancelled",
    "QualificationResult",
    "RuntimeIdentity",
    "SendAndWait",
    # The SP-2 operator tooling imports these two private helpers from this
    # path (`data/services/sp2-governed/continuation-tools/make_episode.py`
    # and its archived copies), so they stay exported, bound to their owners.
    "_sp2_capability_digest",
    "_sp2_mixed_normalized_services_hash",
    "qualify_server_services",
]


def qualify_server_services(
    request: QualificationRequest,
    boundaries: QualificationBoundaries,
    *,
    experimental_capabilities: frozenset[str],
) -> QualificationResult:
    """Run one authorized qualification stage, or refuse it before any effect.

    `experimental_capabilities` is the runner-only scope of unqualified
    behaviors the probes may exercise. An experiment that needs a capability
    outside it does not run. Nothing else in the repository reads this scope.
    """
    return run_qualification(
        request, boundaries, experimental_capabilities=experimental_capabilities
    )
