"""The R-NET-01 acceptance fixture: one segment, one server, two PCs.

Built through the REAL designer, compilers and manifest builder rather than
hand-assembled, because a fixture that skips them proves nothing about the
product path. The only things injected are the two runtimes and the endpoint
observer, which are exactly the external boundaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
    compose_enterprise_reference,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import VerificationKind
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConvergenceReport,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentManifest,
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    FootprintFact,
    PostconditionFact,
    ResultFact,
    TransitionFact,
)
from packet_tracer_mcp.domain.enterprise.models.forwarding import (
    AccessForwardingObservation,
    AccessForwardingRow,
    ForwardingAddressObservation,
)
from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent
from packet_tracer_mcp.domain.enterprise.models.service_plan import ServiceEvidenceKind
from packet_tracer_mcp.domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
)
from packet_tracer_mcp.infrastructure.execution.import_isolation_preflight import (
    ImportIsolationResult,
    ImportIsolationState,
)

DEPLOYMENT_ID = "deploy-hq-1"
BACKEND_VERSION = "9.0.1.0858"
#: The address E5 actually assigns the server on this segment. The service has
#: to name it, because the compiler refuses a service address that does not
#: belong to its host, and that refusal is a feature.
SERVER_ADDRESS = "198.18.160.2"
FINGERPRINT = EnvironmentFingerprint(
    backend="packet_tracer", backend_version=BACKEND_VERSION
)


def intent_payload(
    *,
    dns_address: str = SERVER_ADDRESS,
    include_https: bool = False,
    https_required: bool = False,
    second_dns_address: str = "",
) -> dict[str, Any]:
    """One site, one segment, static server and static clients."""
    services: list[dict[str, Any]] = [
        {
            "name": "lab-dns",
            "service_type": "dns",
            "address": dns_address,
            "dns_records": [{"hostname": "www.lab.example", "address": SERVER_ADDRESS}],
        },
        {
            "name": "lab-web",
            "service_type": "http",
            "hostname": "www.lab.example",
            "http_content": "SAMPLE_WEB_PAGE",
        },
    ]
    if include_https:
        services.append(
            {
                "name": "lab-web-tls",
                "service_type": "https",
                "required": https_required,
            }
        )
    if second_dns_address:
        services.append(
            {
                "name": "other-dns",
                "service_type": "dns",
                "address": second_dns_address,
            }
        )
    return {
        "name": "SAMPLE-LAB",
        "address_space": "198.18.160.0/20",
        "sites": [
            {
                "name": "HQ",
                "type": "hq",
                "endpoints": [
                    {
                        "role": "user_pc",
                        "count": 2,
                        "addressing_preference": "static",
                    },
                    {
                        "role": "server",
                        "count": 1,
                        "addressing_preference": "static",
                        "segment_role": "data",
                    },
                ],
                "services": services,
            }
        ],
    }


def intent_json(**kwargs: Any) -> str:
    """Serialize the fixture intent as the MCP tool would receive it."""
    return json.dumps(intent_payload(**kwargs))


def deployed_topology(payload: dict[str, Any] | None = None):
    """Compose to E4 and build the inventory a real deployment would expose."""
    intent = EnterpriseIntent.model_validate_json(
        json.dumps(payload or intent_payload())
    )
    composed = compose_enterprise_reference(
        intent, packet_tracer_version=BACKEND_VERSION
    )
    assert composed.topology is not None, composed.issues
    inventory = [
        RuntimeConfigurationTarget(
            device_name=device.name,
            model=device.model,
            interfaces=sorted(
                {
                    port
                    for link in composed.topology.links
                    for endpoint_id, port in (
                        (link.device_a_id, link.port_a),
                        (link.device_b_id, link.port_b),
                    )
                    if endpoint_id == device.id
                }
            ),
        )
        for device in composed.topology.devices
    ]
    return composed.topology, inventory


def deployment_manifest(
    payload: dict[str, Any] | None = None,
) -> tuple[DeploymentManifest, list[RuntimeConfigurationTarget]]:
    """Build the manifest the physical deployment path would have produced."""
    topology, inventory = deployed_topology(payload)
    manifest = build_deployment_manifest(
        topology,
        inventory,
        fingerprint=FINGERPRINT,
        deployment_id=DEPLOYMENT_ID,
    )
    return manifest, inventory


@dataclass
class ManifestStore:
    """A read-only manifest port over one known deployment."""

    manifest: DeploymentManifest | None
    error: Exception | None = None
    reads: list[str] = field(default_factory=list)

    def latest_by_deployment_id(self, deployment_id: str) -> DeploymentManifest | None:
        """Return the manifest for that id, or raise the configured error."""
        self.reads.append(deployment_id)
        if self.error is not None:
            raise self.error
        if self.manifest is None or deployment_id != self.manifest.deployment_id:
            return None
        return self.manifest


@dataclass
class IsolationPreflight:
    """A preflight that reports whichever isolation state a test needs."""

    state: ImportIsolationState = ImportIsolationState.ISOLATED
    calls: int = 0

    def ensure_isolated(self) -> ImportIsolationResult:
        """Report the configured state, counting the call."""
        self.calls += 1
        return ImportIsolationResult(self.state, "fixture")


@dataclass
class RecordingConfigurationRuntime:
    """An E5 runtime that records every call and fabricates nothing."""

    targets: list[RuntimeConfigurationTarget]
    applied: list[list[str]] = field(default_factory=list)
    rendered: list[Any] = field(default_factory=list)
    verified: list[list[str]] = field(default_factory=list)
    raise_after_dispatch: bool = False
    endpoint_ipv4: str = SERVER_ADDRESS
    #: The independently timed forwarding backend this runtime answers from.
    #: Its default already forwards, so a test that says nothing about
    #: readiness keeps the behaviour it had before the gate existed.
    forwarding: ForwardingBackend = field(default_factory=lambda: ForwardingBackend())

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Return the deployed targets."""
        return list(self.targets)

    def apply_actions(self, actions: Any) -> list[RuntimeActionMutation]:
        """Record the batch, then either answer it or raise after dispatch."""
        self.applied.append([item.id for item in actions])
        self.rendered.extend(actions)
        if self.raise_after_dispatch:
            raise RuntimeError("the channel dropped after the request was sent")
        return [
            RuntimeActionMutation(action_id=item.id, applied=True, message="applied")
            for item in actions
        ]

    def verify(self, expectations: Any) -> list[RuntimeVerification]:
        """Answer with the fresh attributable endpoint core E5 can produce."""
        self.verified.append([item.id for item in expectations])
        return [
            RuntimeVerification(
                expectation_id=item.id,
                status=(
                    ActionExecutionStatus.PARTIAL
                    if item.kind is VerificationKind.ENDPOINT_ADDRESSING
                    else ActionExecutionStatus.VERIFIED
                ),
                evidence_method="structured_endpoint_getters",
                fresh_evidence=True,
                fields={
                    "ipv4": FieldVerificationStatus.VERIFIED,
                    "netmask": FieldVerificationStatus.VERIFIED,
                    **{
                        name: FieldVerificationStatus.VERIFIED for name in item.expected
                    },
                },
                convergence=ConvergenceReport(
                    attempts=1,
                    final_status=(
                        ActionExecutionStatus.PARTIAL
                        if item.kind is VerificationKind.ENDPOINT_ADDRESSING
                        else ActionExecutionStatus.VERIFIED
                    ),
                    details={
                        "kind": "endpoint_addressing",
                        "device_name": item.device_name,
                        "interface": "FastEthernet0",
                        "last_observation": {
                            "device_found": True,
                            "port_found": True,
                            "address_channel": True,
                            "interface": "FastEthernet0",
                            "ipv4": self.endpoint_ipv4,
                            "netmask": "255.255.255.248",
                            "fresh_evidence": True,
                            "failure_reason": "",
                        },
                    },
                ),
            )
            for item in expectations
        ]

    def wait_for_voice_access_forwarding(self, expectations: Any) -> list[Any]:
        """Return nothing; this slice never reaches the Voice barrier."""
        return []

    def observe_access_forwarding(
        self,
        device_name: str,
        vlan_id: int,
        interfaces: Any,
        **bounds: Any,
    ) -> AccessForwardingObservation:
        """Delegate the grouped forwarding query to the timed backend."""
        return self.forwarding.observe_access_forwarding(
            device_name, vlan_id, interfaces, **bounds
        )


@dataclass
class RecordingServiceRuntime:
    """An E6 runtime that records every call and states its observations."""

    targets: list[RuntimeConfigurationTarget]
    applied: list[list[str]] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    behavior_status: ActionExecutionStatus = ActionExecutionStatus.VERIFIED
    behavior_observation: ObservationFact = ObservationFact.OBSERVED
    failing_clients: frozenset[str] = frozenset()
    release_outcome: str = ""
    release_cause: str = ""
    dispatch: DispatchFact = DispatchFact.UNSPECIFIED
    result: ResultFact = ResultFact.NOT_APPLICABLE
    postcondition: PostconditionFact = PostconditionFact.NOT_APPLICABLE
    transition: TransitionFact = TransitionFact.NOT_APPLICABLE
    footprint: FootprintFact = FootprintFact.NOT_APPLICABLE
    attempted: bool | None = None

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Return the deployed targets."""
        return list(self.targets)

    def apply_actions(self, actions: Any) -> list[RuntimeActionMutation]:
        """Record the batch and report it applied."""
        self.applied.append([item.id for item in actions])
        return [
            RuntimeActionMutation(
                action_id=item.id,
                applied=True,
                message="applied",
                dispatch=self.dispatch,
                result=self.result,
                postcondition=self.postcondition,
                transition=self.transition,
                footprint=self.footprint,
                attempted=self.attempted,
            )
            for item in actions
        ]

    def verify(self, expectation: Any) -> RuntimeServiceVerification:
        """Observe one expectation, per the configured behaviour."""
        self.verified.append(expectation.id)
        direct = expectation.evidence_kind is ServiceEvidenceKind.DIRECT_STATE
        contradicted = expectation.client_device_id in self.failing_clients
        status = (
            ActionExecutionStatus.FAILED
            if contradicted
            else ActionExecutionStatus.VERIFIED
            if direct
            else self.behavior_status
        )
        observation = (
            ObservationFact.CONTRADICTED
            if contradicted
            else ObservationFact.OBSERVED
            if direct
            else self.behavior_observation
        )
        limitations = []
        observed: dict[str, str | int | bool] = {}
        if self.release_outcome and not direct:
            observed["released"] = self.release_outcome
            if self.release_outcome != "released":
                limitations.append(
                    "client_ownership_unresolved:"
                    + self.release_outcome
                    + (f":{self.release_cause}" if self.release_cause else "")
                )
        return RuntimeServiceVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_kind=expectation.evidence_kind,
            evidence_method="fake_fresh_service_observation",
            fresh_evidence=status
            in {ActionExecutionStatus.VERIFIED, ActionExecutionStatus.FAILED},
            observation=observation,
            claim_level="read_back" if direct else "behavioral",
            observed=observed,
            limitations=limitations,
        )


@dataclass
class EndpointObserver:
    """A directed endpoint reader with a configurable answer."""

    address: str = ""
    addresses: dict[str, str] = field(default_factory=dict)
    readable: bool = True
    reads: list[tuple[str, str]] = field(default_factory=list)

    def observe(
        self, runtime_device_name: str, interface: str
    ) -> ForwardingAddressObservation:
        """Report the configured observation for one endpoint."""
        self.reads.append((runtime_device_name, interface))
        if not self.readable:
            return ForwardingAddressObservation(
                runtime_device_name=runtime_device_name,
                interface=interface,
                device_found=False,
                port_found=False,
                address_channel=False,
                fresh_evidence=False,
                failure_reason="timeout",
            )
        address = self.addresses.get(runtime_device_name, self.address)
        return ForwardingAddressObservation(
            runtime_device_name=runtime_device_name,
            interface=interface,
            device_found=True,
            port_found=True,
            address_channel=True,
            ipv4=address,
            netmask="255.255.255.248" if address else "",
            fresh_evidence=True,
        )


@dataclass
class SimulatedClock:
    """A monotonic clock the test advances, never the code under test.

    The forwarding backend reads this clock, so its answer follows elapsed
    simulated time and not how many times it was asked. A fake whose state
    advanced per query would make "the third sample forwards" pass while
    "forwarding arrives after four seconds" was never actually exercised.
    """

    now: float = 0.0

    def __call__(self) -> float:
        """Return the current simulated instant."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Move simulated time forward."""
        self.now += seconds


@dataclass
class ForwardingBackend:
    """An independently timed spanning-tree backend for one switch and VLAN.

    Before `forwards_at` every requested interface answers `LIS` on an
    otherwise fresh, complete and uniquely attributed sample, so the only
    thing that refuses is the port state. From `forwards_at` onward the same
    interfaces answer `FWD`. Every other dimension is settable on its own, so
    a test can drive identity, freshness, completeness or a missing row
    without also changing the port state.
    """

    clock: SimulatedClock = field(default_factory=SimulatedClock)
    forwards_at: float | None = 0.0
    calls: list[tuple[str, int, tuple[str, ...]]] = field(default_factory=list)
    limits: list[dict[str, Any]] = field(default_factory=list)
    observed_device_name: str | None = None
    device_identity_provenance: str = "confirmed_unique"
    fresh_output_observed: bool = True
    output_complete: bool = True
    executed: bool = True
    vlan_present: bool = True
    missing_interfaces: frozenset[str] = frozenset()
    duplicated_interfaces: frozenset[str] = frozenset()
    raises: Exception | None = None
    #: Simulated seconds one observation costs, charged to the clock so a
    #: caller with a total budget can actually exhaust it.
    seconds_per_observation: float = 0.0

    def forwarding_now(self) -> bool:
        """Whether the simulated switch is forwarding at this instant."""
        return self.forwards_at is not None and self.clock.now >= self.forwards_at

    def observe_access_forwarding(
        self,
        device_name: str,
        vlan_id: int,
        interfaces: Any,
        **bounds: Any,
    ) -> AccessForwardingObservation:
        """Answer one grouped query from the clock, not from the call count."""
        requested = tuple(str(item) for item in interfaces)
        self.calls.append((device_name, vlan_id, requested))
        self.limits.append(dict(bounds))
        if self.raises is not None:
            raise self.raises
        self.clock.advance(self.seconds_per_observation)
        state = "FWD" if self.forwarding_now() else "LIS"
        rows = tuple(
            AccessForwardingRow(
                interface=item,
                matches=(
                    0
                    if item in self.missing_interfaces
                    else 2
                    if item in self.duplicated_interfaces
                    else 1
                ),
                state=state,
                role="Desg",
            )
            for item in requested
        )
        return AccessForwardingObservation(
            switch_name=device_name,
            vlan_id=vlan_id,
            requested_interfaces=requested,
            rows=rows,
            executed=self.executed,
            fresh_output_observed=self.fresh_output_observed,
            output_complete=self.output_complete,
            observed_device_name=(
                device_name
                if self.observed_device_name is None
                else self.observed_device_name
            ),
            device_identity_provenance=self.device_identity_provenance,
            vlan_present=self.vlan_present,
            samples=1,
            max_samples=3,
            deadline_seconds=30.0,
            elapsed_ms=int(self.seconds_per_observation * 1000),
            sample_call_budget=6,
            channel_calls=1,
            simulation_time=f"sim_time:{self.clock.now:g}",
        )
