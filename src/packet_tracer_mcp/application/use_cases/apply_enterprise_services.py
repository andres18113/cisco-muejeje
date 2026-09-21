"""The enterprise-services product entry point: admission, effects, evidence.

This is the workflow behind `pt_apply_enterprise_services`. It exists because
every piece of it already existed separately and nothing joined them: E5 could
apply a configuration, E6 could apply services, and the only end-to-end
sequence in the tree (`execute_enterprise_reference`) deploys into an EMPTY
workspace and always cleans up, so it cannot serve an operator's real
deployment.

The shape of the thing is admission, then effects, then evidence:

- **Admission (A1..A10)** reads and computes. It may read a manifest, an
  inventory and an endpoint, and it may not mutate anything. Every refusal is
  typed, and every refusal happens before the first effect. That ordering is
  not a convention here, it is asserted by a recording fake that counts
  mutating calls on both runtimes.
- **Effects (E1, E4)** are the only two steps that touch user state: the
  bounded E5 application and the E6 service application. Between them, E2
  refuses to continue when E5's own outcome is uncertain, and E3 derives
  foundations from what E5 actually recorded.
- **Evidence (E5r, P1)** releases what this run owns and writes the terminal
  record.

Two rules are worth stating where they are implemented rather than only in the
brief:

`no cleanup` means no destruction of the operator's topology or services. It
has never meant skipping the release of clients this verification itself
created, and the release outcomes are reported whether or not they resolved.

The mutation gate is the enforced backstop for persistence loss. The stage
sequencer is the primary control - after a failed rewrite the next effectful
stage is simply not entered - and the gate makes that structural: the injected
runtimes are wrapped, and a mutating call on a closed gate raises before it
reaches the runtime. Reads and releases pass through, because bounded
observation and owned cleanup are exactly what must still be allowed.
"""

from __future__ import annotations

import secrets as _random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from ...domain.enterprise.models.capabilities import CapabilityStatus
from ...domain.enterprise.models.configuration import (
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    ConfigureAccessPort,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    ConfigurationFailureCode,
    ConfigurationRuntimeContext,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.deployment import (
    DeploymentIdentityError,
    DeploymentManifest,
    EnvironmentFingerprint,
    resolve_manifest_targets,
    validate_manifest_environment,
)
from ...domain.enterprise.models.execution import DirtyState, satisfies_apply_dependency
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.service_entry import (
    AdmissionRead,
    AdmissionRefusal,
    AdmissionTrace,
    CapabilitySnapshotSummary,
    ClientCheckOutcome,
    ClientCheckRow,
    ClientServiceOutcome,
    E5EffectScope,
    OwnedResourceRelease,
    ServiceEntryOutcome,
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
    ServiceStageResult,
    StageTransition,
)
from ...domain.enterprise.models.service_plan import (
    ClientOperationCapability,
    ConfigureServerDhcpPool,
    ServiceCapabilityRecords,
    ServiceDefinition,
    ServicePlan,
    ServiceType,
    ServiceVerificationKind,
    SetHttpContent,
    secret_refs,
)
from ...domain.enterprise.models.service_run_record import (
    DhcpServiceAuthorityRecord,
    ServiceRunRecord,
    SharedContentExecutionBinding,
    SourceTreeIdentity,
    generate_run_id,
)
from ...domain.enterprise.models.service_runtime import ServiceApplicationResult
from ...domain.enterprise.services.service_access_readiness import (
    derive_access_readiness_plan,
)
from ...domain.enterprise.services.service_capability_resolution import (
    provenance_by_key,
    resolve_action_capability,
    resolve_verification_capability,
)
from ...infrastructure.catalog.service_capabilities import (
    capability_snapshot_hash,
    packet_tracer_service_capabilities,
)
from ..ports.secret_resolver import SecretResolver
from ..ports.service_run_record import (
    DeploymentManifestPort,
    EndpointDriftObserver,
    RunRecordPersistenceError,
    ServiceRunRecordPort,
)
from .apply_configuration import ConfigurationApplicator, ConfigurationRuntime
from .apply_services import ServiceApplicator, ServiceRuntime
from .compose_enterprise_reference import compose_enterprise_reference
from .execute_enterprise_reference import configuration_application_contradiction
from .foundational_evidence import derive_service_foundational_statuses
from .service_access_readiness_gate import (
    AccessForwardingObserver,
    ServiceAccessReadinessGate,
)

#: The E5 row representations that mean "this action's effect is unknown".
#: The second is the legacy shape documented as D-9: the applicator turns a
#: missing runtime result into a FAILED row with that message, which is not
#: evidence of non-execution and not evidence of a clean run.
_MISSING_RESULT_MESSAGE = "Runtime returned no mutation result."
# Match the authenticated bridge's existing 1 MiB body ceiling so the product
# never presents a larger intent as a workload the runtime path can support.
MAX_INTENT_JSON_BYTES = 1 << 20
# Offline scale acceptance exercises 1000 clients. The fixed response budget
# remains five checks per client: DHCP-only uses two, while a combined
# DNS/HTTP/DHCP seven-row workload is refused explicitly rather than sampled.
# These are response-composition budgets, not Packet Tracer capacity claims.
MAX_REPORTING_CLIENTS = 1000
MAX_CLIENT_CHECK_ROWS = MAX_REPORTING_CLIENTS * 5
#: The only channel a secret-bearing script may travel on (R-SEC-01): a POST
#: body over the authenticated loopback bridge, never a request file on disk.
SECRET_CHANNEL = "http"


def _fresh_nonce() -> str:
    """Return one unpredictable message nonce for one run."""
    return _random.token_hex(8)


class ServiceEffectHalted(RuntimeError):
    """Raised when a mutating call is attempted after effects were halted."""


@dataclass(frozen=True)
class ServiceStageRuntimes:
    """The two runtimes one invocation drives, bound to the same channel."""

    configuration: ConfigurationRuntime
    services: ServiceRuntime


@dataclass(frozen=True)
class TransportSelection:
    """The channel, selected once at admission and never changed mid-run."""

    channel: str
    fixed_at: datetime | None = None
    ready: bool = True
    detail: str = ""


@dataclass(frozen=True)
class ServiceInvocationBinding:
    """Collaborators observed and bound only after process admission.

    Production constructs this value lazily at A5. That keeps transport health
    checks, bridge selection, runtime construction, and record-store
    initialization behind A1 parsing and A4 process isolation while giving the
    rest of the use case one immutable session contract.
    """

    runtimes: ServiceStageRuntimes
    record_store: ServiceRunRecordPort
    environment_fingerprint: EnvironmentFingerprint
    transport_selection: TransportSelection
    source_tree: SourceTreeIdentity
    endpoint_observer: EndpointDriftObserver | None = None
    inventory_reader: (
        Callable[[Sequence[str]], list[RuntimeConfigurationTarget]] | None
    ) = None
    #: The one credential source of this session; the service runtime is bound
    #: to the same instance, so admission and dispatch see one value.
    secret_resolver: SecretResolver | None = None


@dataclass
class ClientRowAssemblyMetrics:
    """Deterministic operation counts for the linear reporting boundary."""

    expectations_indexed: int = 0
    memberships_indexed: int = 0
    pairs_assembled: int = 0
    check_lookups: int = 0


@dataclass
class _MutationGate:
    """The single permission to dispatch a user-state mutation."""

    open: bool = True
    reason: str = ""

    def close(self, reason: str) -> None:
        """Withdraw the permission, naming why."""
        self.open = False
        self.reason = reason

    def ensure_open(self) -> None:
        """Refuse before the call reaches the runtime, never after."""
        if not self.open:
            raise ServiceEffectHalted(self.reason)


@dataclass
class _GatedConfigurationRuntime:
    """E5 runtime whose mutations pass the gate and whose reads do not."""

    inner: ConfigurationRuntime
    gate: _MutationGate

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Read the runtime inventory; always permitted."""
        return self.inner.inventory()

    def apply_actions(self, actions: Sequence[Any]) -> list[RuntimeActionMutation]:
        """Dispatch one batch, only while the gate is open."""
        self.gate.ensure_open()
        return self.inner.apply_actions(actions)

    def verify(self, expectations: Sequence[Any]) -> list[Any]:
        """Observe expectations; always permitted."""
        return self.inner.verify(expectations)

    def wait_for_voice_access_forwarding(
        self, expectations: Sequence[Any]
    ) -> list[Any]:
        """Delegate the Voice barrier; this slice never reaches it."""
        return self.inner.wait_for_voice_access_forwarding(expectations)

    def observe_access_forwarding(
        self,
        device_name: str,
        vlan_id: int,
        interfaces: Sequence[str],
    ) -> Any:
        """Observe one switch/VLAN group; a read, so always permitted.

        Raises `AttributeError` when the composed runtime has no such reader,
        which the readiness gate turns into a named refusal rather than a
        silent pass. It is never synthesized here.
        """
        return self.inner.observe_access_forwarding(device_name, vlan_id, interfaces)


@dataclass
class _GatedServiceRuntime:
    """E6 runtime whose mutations pass the gate and whose reads do not."""

    inner: ServiceRuntime
    gate: _MutationGate

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        """Read the runtime inventory; always permitted."""
        return self.inner.inventory()

    def apply_actions(self, actions: Sequence[Any]) -> list[RuntimeActionMutation]:
        """Dispatch one batch, only while the gate is open."""
        self.gate.ensure_open()
        return self.inner.apply_actions(actions)

    def verify(self, expectation: Any) -> Any:
        """Observe one expectation; owned temporaries release themselves."""
        return self.inner.verify(expectation)


@dataclass
class _Run:
    """Everything one invocation accumulates, in one place."""

    run_id: str
    run_label: str
    started: float
    now: Callable[[], datetime]
    record_store: ServiceRunRecordPort
    record: ServiceRunRecord
    gate: _MutationGate
    trace: AdmissionTrace = field(default_factory=AdmissionTrace)
    persisted_stage: ServiceStage | None = None
    record_path: str = ""
    persist_error: str = ""
    limitations: list[str] = field(default_factory=list)

    def read(self, step: str, subject: str, outcome: str = "") -> None:
        """Record one directed admission read, in the order it happened."""
        self.trace.reads.append(
            AdmissionRead(step=step, subject=subject, outcome=outcome)
        )

    def refuse(self, step: str, code: ServiceEntryRefusal, detail: str) -> None:
        """Record one typed refusal."""
        self.trace.refusals.append(
            AdmissionRefusal(step=step, code=code, detail=detail)
        )

    def transition(self, stage: ServiceStage, outcome: str = "") -> None:
        """Write the stage boundary before the next effectful stage begins.

        A failure closes the mutation gate rather than raising: the primary
        error has to survive, and the run still has owned cleanup and bounded
        observation left to do. The stage sequencer reads the gate, which is
        why this reports nothing of its own.
        """
        moment = self.now()
        self.record.stages.append(
            StageTransition(
                stage=stage, started_at=moment, ended_at=moment, outcome=outcome
            )
        )
        self.record.persisted_stage = stage
        try:
            self.record_path = self.record_store.advance(self.record)
        except RunRecordPersistenceError as exc:
            self.record.persisted_stage = self.persisted_stage
            self.persist_error = str(exc)
            self.gate.close(
                f"The run record could not advance past "
                f"{self.persisted_stage.value if self.persisted_stage else 'admission'}."
            )
            self.limitations.append(f"persist_error:{stage.value}")
            return
        self.persisted_stage = stage


def _refused(
    run: _Run,
    *,
    step: str,
    code: ServiceEntryRefusal,
    detail: str,
    packet_tracer_version: str,
    transport: str,
    deployment_id: str,
) -> ServiceStageResult:
    """Build the terminal result of a run that admission stopped."""
    run.refuse(step, code, detail)
    run.record.refusal_code = code
    run.record.blocked_reason = detail
    run.record.status = ServiceRunStatus.REFUSED
    run.record.admission = run.trace
    run.record.completed_at = run.now()
    # R-ENTRY-06: a refusal after A2 always tries to leave a record. An
    # unbound one still says a run was asked for and refused, which is a
    # fact worth keeping; if the store cannot take it the response says
    # so rather than pretending it was written.
    try:
        run.record_path = run.record_store.complete(run.record)
    except RunRecordPersistenceError as exc:
        run.persist_error = _external_cause(exc)
        run.record_path = ""
    return ServiceStageResult(
        run_id=run.run_id,
        run_label=run.run_label,
        deployment_id=deployment_id,
        stage=ServiceStage.ADMISSION,
        status=ServiceRunStatus.REFUSED,
        refusal_code=code,
        blocked_reason=detail,
        transport=transport,
        packet_tracer_version=packet_tracer_version,
        admission=run.trace,
        persisted_stage=run.persisted_stage,
        record_path=run.record_path,
        persist_error=run.persist_error,
        limitations=list(run.limitations),
        duration_ms=int((monotonic() - run.started) * 1000),
    )


def _unbound_result(
    *,
    run_id: str,
    run_label: str,
    code: ServiceEntryRefusal,
    detail: str,
    step: str,
    packet_tracer_version: str,
    transport: str,
    started: float,
    admission: AdmissionTrace | None = None,
) -> ServiceStageResult:
    """A1 and A2 refuse with no record: no valid bound identity exists yet."""
    trace = (
        admission.model_copy(deep=True) if admission is not None else AdmissionTrace()
    )
    trace.refusals.append(AdmissionRefusal(step=step, code=code, detail=detail))
    return ServiceStageResult(
        run_id=run_id,
        run_label=run_label,
        stage=ServiceStage.ADMISSION,
        status=ServiceRunStatus.REFUSED,
        refusal_code=code,
        blocked_reason=detail,
        transport=transport,
        packet_tracer_version=packet_tracer_version,
        admission=trace,
        duration_ms=int((monotonic() - started) * 1000),
    )


def _selected_clients(
    plan: ServicePlan, services: Sequence[ServiceDefinition]
) -> set[str]:
    """Every client id any eligible service selected."""
    return {
        client_id for service in services for client_id in service.client_device_ids
    }


def _shared_writer_candidate(
    action: SetHttpContent,
    service: ServiceDefinition,
) -> SetHttpContent:
    """Bind one source page action to a candidate admitted writer."""
    return action.model_copy(
        update={
            "service_id": service.id,
            "service_type": service.service_type,
        },
        deep=True,
    )


def _service_eligibility(
    plan: ServicePlan,
    capabilities: ServiceCapabilityRecords,
) -> tuple[
    list[ServiceDefinition],
    dict[str, list[str]],
    dict[str, SetHttpContent],
]:
    """Split the plan's services into eligible ones and named refusals.

    A service is eligible when every action it applies and every REQUIRED
    expectation it declares resolves SUPPORTED on the model that performs it.
    An optional expectation - an advisory reader, or any expectation of a
    service whose verification is not required - never gates: it is still
    compiled and still reported, and R-CAP-06 is exactly the rule that it may
    not report VERIFIED for a capability it lacks either.
    """
    shared_content = {
        action.id: action
        for action in plan.actions
        if isinstance(action, SetHttpContent)
        and len(set(action.shared_service_ids)) > 1
    }
    actions_by_service: dict[str, list[Any]] = {}
    for action in plan.actions:
        if action.id in shared_content:
            continue
        actions_by_service.setdefault(action.service_id, []).append(action)
    expectations_by_service: dict[str, list[Any]] = {}
    for expectation in plan.verification_expectations:
        expectations_by_service.setdefault(expectation.service_id, []).append(
            expectation
        )

    eligible: list[ServiceDefinition] = []
    unknown_operations: dict[str, list[str]] = {}
    for service in plan.services:
        missing: list[str] = []
        for action in actions_by_service.get(service.id, ()):
            resolution = resolve_action_capability(capabilities, action)
            if not resolution.is_supported:
                missing.append(f"{resolution.key}={resolution.support.value}")
        for expectation in expectations_by_service.get(service.id, ()):
            if not expectation.required:
                continue
            resolution = resolve_verification_capability(
                capabilities, expectation, service
            )
            if not resolution.is_supported:
                missing.append(f"{resolution.key}={resolution.support.value}")
        if service.service_type is ServiceType.DHCP:
            mode_foundations = [
                item
                for item in plan.foundational_requirements
                if item.device_id in service.client_device_ids
                and item.kind == "endpoint_dhcp_mode"
            ]
            for foundation in mode_foundations:
                key = (
                    f"{foundation.model}:"
                    f"{ServiceVerificationKind.ENDPOINT_DHCP_MODE.value}"
                )
                record = capabilities.get(key)
                support = (
                    record.support
                    if isinstance(record, ClientOperationCapability)
                    else CapabilityStatus.UNKNOWN
                )
                if support is not CapabilityStatus.SUPPORTED:
                    missing.append(f"{key}={support.value}")
        if missing:
            unknown_operations[service.id] = sorted(set(missing))
            continue
        eligible.append(service)
    dhcp_owner_by_client = {
        client_id: service.id
        for service in plan.services
        if service.service_type is ServiceType.DHCP
        for client_id in service.client_device_ids
    }
    still_eligible: list[ServiceDefinition] = []
    for service in eligible:
        blocked = sorted(
            {
                dhcp_owner_by_client[client_id]
                for client_id in service.client_device_ids
                if client_id in dhcp_owner_by_client
                and dhcp_owner_by_client[client_id] in unknown_operations
            }
        )
        if blocked and service.service_type is not ServiceType.DHCP:
            unknown_operations[service.id] = [
                f"dhcp_prerequisite:{identifier}=ineligible" for identifier in blocked
            ]
            continue
        still_eligible.append(service)
    eligible_by_id = {item.id: item for item in still_eligible}
    selected_shared_writers: dict[str, SetHttpContent] = {}
    shared_ineligible: set[str] = set()
    for action in shared_content.values():
        members = [
            eligible_by_id[service_id]
            for service_id in action.shared_service_ids
            if service_id in eligible_by_id
        ]
        if not members:
            continue
        ordered = sorted(
            members,
            key=lambda item: (
                item.id != action.service_id,
                item.service_type is not ServiceType.HTTP,
                item.id,
            ),
        )
        candidates = []
        for service in ordered:
            candidate = _shared_writer_candidate(action, service)
            candidates.append(
                (candidate, resolve_action_capability(capabilities, candidate))
            )
        selected = next(
            (
                candidate
                for candidate, resolution in candidates
                if resolution.is_supported
            ),
            None,
        )
        if selected is not None:
            selected_shared_writers[action.id] = selected
            continue
        missing = sorted(
            {
                f"{resolution.key}={resolution.support.value}"
                for _candidate, resolution in candidates
            }
        )
        for service in members:
            unknown_operations[service.id] = missing or [
                f"{action.host_model}:{action.action_type.value}=unknown"
            ]
            shared_ineligible.add(service.id)
    if shared_ineligible:
        still_eligible = [
            item for item in still_eligible if item.id not in shared_ineligible
        ]
    return still_eligible, unknown_operations, selected_shared_writers


def _dhcp_authorities(plan: ServicePlan) -> list[DhcpServiceAuthorityRecord]:
    """Project canonical DHCP authority into the durable run record."""
    actions_by_service: dict[str, list[Any]] = {}
    for action in plan.actions:
        actions_by_service.setdefault(action.service_id, []).append(action)
    expectations_by_service: dict[str, list[Any]] = {}
    for expectation in plan.verification_expectations:
        expectations_by_service.setdefault(expectation.service_id, []).append(
            expectation
        )
    records: list[DhcpServiceAuthorityRecord] = []
    for service in plan.services:
        if service.service_type is not ServiceType.DHCP:
            continue
        pool = next(
            (
                item
                for item in actions_by_service.get(service.id, ())
                if isinstance(item, ConfigureServerDhcpPool)
            ),
            None,
        )
        if pool is None:
            continue
        records.append(
            DhcpServiceAuthorityRecord(
                service_id=service.id,
                server_device_id=service.host_device_id,
                segment_id=service.segment_id,
                interface=pool.interface,
                pool_name=pool.pool_name,
                client_device_ids=list(service.client_device_ids),
                action_ids=[item.id for item in actions_by_service[service.id]],
                expectation_ids=[
                    item.id for item in expectations_by_service.get(service.id, ())
                ],
            )
        )
    return records


def _reporting_budget_exceeded(plan: ServicePlan) -> bool:
    """Whether the selected public response exceeds measured offline bounds."""
    clients = _selected_clients(plan, plan.services)
    client_rows = sum(
        bool(item.client_device_id) for item in plan.verification_expectations
    )
    return len(clients) > MAX_REPORTING_CLIENTS or client_rows > MAX_CLIENT_CHECK_ROWS


def _access_forwarding_observer(
    runtime: object,
) -> AccessForwardingObserver | None:
    """Return the composed forwarding observer, or nothing when there is none.

    Structural, because the readiness observation is an optional surface of a
    configuration runtime rather than part of the E5 port every runtime must
    implement. Returning `None` does not relax the gate: the gate refuses a
    group it cannot observe, so an unobservable composition blocks its HTTP
    requests instead of passing them through.

    The support question is asked of the runtime that would actually answer,
    which is the one inside the mutation-gate wrapper. The wrapper forwards
    the reader unconditionally, so asking it instead would report every
    composition as observable and turn a missing reader into a raised call.
    """
    composed = getattr(runtime, "inner", runtime)
    reader = getattr(composed, "observe_access_forwarding", None)
    return runtime if callable(reader) else None  # type: ignore[return-value]


def _e5_closure(
    configuration_plan: Any,
    plan: ServicePlan,
    services: Sequence[ServiceDefinition],
) -> set[str]:
    """Close the eligible services' foundations over the E5 dependency graph."""
    devices = {service.host_device_id for service in services}
    devices |= _selected_clients(plan, services)
    requirements_by_device: dict[str, list[Any]] = {}
    for requirement in plan.foundational_requirements:
        if requirement.device_id in devices:
            requirements_by_device.setdefault(requirement.device_id, []).append(
                requirement
            )
    invalid_devices = sorted(
        device_id
        for device_id in devices
        if len(requirements_by_device.get(device_id, [])) != 1
    )
    if invalid_devices:
        raise ValueError(
            "Selected foundation identity is missing or ambiguous: "
            + ", ".join(invalid_devices)
        )
    seeds = {
        requirements_by_device[device_id][0].configuration_action_id
        for device_id in devices
    }
    by_id = {item.id: item for item in configuration_plan.actions}
    missing = sorted(identifier for identifier in seeds if identifier not in by_id)
    if missing:
        raise ValueError(
            "Selected foundation actions are absent from the configuration plan: "
            + ", ".join(missing)
        )
    closed: set[str] = set()
    frontier = set(seeds)
    while frontier:
        identifier = frontier.pop()
        if identifier in closed:
            continue
        if identifier not in by_id:
            raise ValueError(
                f"Required configuration dependency {identifier!r} is missing."
            )
        closed.add(identifier)
        action = by_id[identifier]
        frontier |= {*action.depends_on, *action.apply_dependencies}
    return closed


def _e5_effect_is_uncertain(
    configuration_result: ConfigurationApplicationResult,
    scope: set[str],
) -> list[str]:
    """Name the in-scope E5 rows whose effect the result cannot settle (R-RET-02).

    D-9 containment, and deliberately narrow. A SESSION_FAILED row and the
    legacy missing-result row both mean the same thing here: the command may
    have run. Neither is evidence of non-execution, so neither may be read as
    a clean run, and both stop this invocation before it dispatches an E6
    effect on top of an E5 state nobody can describe.
    """
    return sorted(
        item.action_id
        for item in configuration_result.action_results
        if item.action_id in scope
        and (
            item.failure_code is ConfigurationFailureCode.SESSION_FAILED
            or item.message == _MISSING_RESULT_MESSAGE
        )
    )


def _e5_contradiction(
    configuration_result: ConfigurationApplicationResult,
    governed_action_ids: set[str],
) -> str:
    """Return the existing contradiction decision for governed E5 rows only."""
    action_results = [
        item
        for item in configuration_result.action_results
        if item.action_id in governed_action_ids
    ]
    verification_results = [
        item
        for item in configuration_result.verification_results
        if item.action_id in governed_action_ids
    ]
    no_result_preflight_failure = (
        configuration_result.status is ConfigurationApplicationStatus.FAILED
        and not configuration_result.action_results
        and not configuration_result.verification_results
    )
    scoped = configuration_result.model_copy(
        update={
            "status": (
                ConfigurationApplicationStatus.FAILED
                if configuration_result.preflight_errors or no_result_preflight_failure
                else ConfigurationApplicationStatus.PARTIAL
            ),
            "action_results": action_results,
            "verification_results": verification_results,
        }
    )
    return configuration_application_contradiction(scoped)


def _drift_conflicts(
    configuration_plan: Any,
    scope: set[str],
    deployed_names: dict[str, str],
    observer: EndpointDriftObserver | None,
    run: _Run,
) -> tuple[list[str], list[str], set[str]]:
    """Pre-read every in-scope endpoint and name conflicts and blind spots.

    An endpoint that already carries a DIFFERENT non-empty address holds
    somebody else's configuration, and applying over it is the one thing this
    product must never do silently. An endpoint that could not be READ is a
    separate answer: it is unknown, not empty, and it refuses too. Treating an
    unreadable endpoint as free is how a run would overwrite exactly the state
    it could not see.
    """
    conflicts: list[str] = []
    unreadable: list[str] = []
    confirmed: set[str] = set()
    for action in configuration_plan.actions:
        if action.id not in scope or not isinstance(
            action, SetEndpointStaticAddress | SetEndpointDhcp
        ):
            continue
        device_name = deployed_names.get(action.device_id, action.device_name)
        if observer is None:
            unreadable.append(f"{action.id}:no_observer")
            continue
        observation = observer.observe(device_name, action.interface)
        run.read("A10", f"{device_name}:{action.interface}", observation.ipv4)
        if not (
            observation.device_found
            and observation.port_found
            and observation.address_channel
            and observation.fresh_evidence
        ):
            unreadable.append(
                f"{action.id}:{observation.failure_reason or 'unobservable'}"
            )
            continue
        current = (observation.ipv4 or "").strip()
        if isinstance(action, SetEndpointDhcp) and current:
            conflicts.append(f"{action.id}:{current}:dhcp_mode_requested")
        elif current and current != action.ipv4:
            conflicts.append(f"{action.id}:{current}!={action.ipv4}")
        elif isinstance(action, SetEndpointStaticAddress) and current == action.ipv4:
            confirmed.add(action.id)
    return conflicts, unreadable, confirmed


def _fresh_retained_results(
    prior: ServiceRunRecord | None,
    configuration_plan: Any,
    scope: set[str],
    endpoint_confirmed: set[str],
    runtime: ConfigurationRuntime,
    run: _Run,
) -> list[ActionApplicationResult]:
    """Return only prior rows whose prerequisites were freshly re-observed."""
    if prior is None or prior.configuration_result is None:
        return []
    prior_rows = {
        item.action_id: item
        for item in prior.configuration_result.action_results
        if item.action_id in scope and satisfies_apply_dependency(item.status)
    }
    actions = {item.id: item for item in configuration_plan.actions}
    expectations_by_action: dict[str, list[Any]] = {}
    for expectation in configuration_plan.verification_expectations:
        if expectation.action_id in prior_rows:
            expectations_by_action.setdefault(expectation.action_id, []).append(
                expectation
            )
    non_endpoint_expectations = [
        expectation
        for action_id, expectations in expectations_by_action.items()
        if not isinstance(actions.get(action_id), SetEndpointStaticAddress)
        for expectation in expectations
    ]
    observed_by_id: dict[str, Any] = {}
    if non_endpoint_expectations:
        try:
            observed_by_id = {
                item.expectation_id: item
                for item in runtime.verify(non_endpoint_expectations)
            }
        except Exception as exc:
            run.read("A10", "retained_prerequisites", _external_cause(exc))
            return []
    preliminarily_valid: set[str] = set()
    for action_id in prior_rows:
        action = actions.get(action_id)
        if isinstance(action, SetEndpointStaticAddress):
            if action_id in endpoint_confirmed:
                preliminarily_valid.add(action_id)
            continue
        expectations = expectations_by_action.get(action_id, [])
        if expectations and all(
            (observed := observed_by_id.get(expectation.id)) is not None
            and observed.fresh_evidence
            and observed.status is ActionExecutionStatus.VERIFIED
            for expectation in expectations
        ):
            preliminarily_valid.add(action_id)

    retained: set[str] = set()
    for action in configuration_plan.actions:
        if action.id not in preliminarily_valid:
            continue
        dependencies = {*action.depends_on, *action.apply_dependencies} & scope
        if dependencies <= retained:
            retained.add(action.id)
    if retained:
        run.read("A10", "retained_prerequisites", str(len(retained)))
    return [
        prior_rows[item.id].model_copy(deep=True)
        for item in configuration_plan.actions
        if item.id in retained
    ]


def _aggregate_required(checks: Sequence[ClientCheckRow]) -> ActionExecutionStatus:
    """Aggregate one set of client rows over the REQUIRED ones only.

    An optional row is reported and never counted. It cannot drag a verified
    service down, and it cannot lift an unverified one either: a reader with no
    evidence contributes no evidence in either direction.
    """
    required = [item for item in checks if item.required]
    if not required:
        return ActionExecutionStatus.UNKNOWN
    if any(item.status is ActionExecutionStatus.FAILED for item in required):
        return ActionExecutionStatus.FAILED
    if all(item.status is ActionExecutionStatus.VERIFIED for item in required):
        return ActionExecutionStatus.VERIFIED
    if any(
        item.status is ActionExecutionStatus.DEPENDENCY_BLOCKED for item in required
    ):
        return ActionExecutionStatus.PARTIAL
    if all(item.status is ActionExecutionStatus.UNKNOWN for item in required):
        return ActionExecutionStatus.UNKNOWN
    return ActionExecutionStatus.PARTIAL


def _client_rows(
    plan: ServicePlan,
    service_result: ServiceApplicationResult | None,
    services: Sequence[ServiceDefinition],
    deployed_names: dict[str, str],
    models: dict[str, str],
    ineligible: dict[str, list[str]] | None = None,
    metrics: ClientRowAssemblyMetrics | None = None,
) -> list[ClientServiceOutcome]:
    """Assemble one row per selected client per service it was selected for.

    R-COV-01 expressed in code: the aggregation walks the SELECTED clients, not
    the rows that happen to exist. A client whose service was skipped, blocked
    or never observed still appears, with the reason, because a client silently
    missing from a response reads as a client that was fine.
    """
    rows_by_expectation = {
        item.expectation_id: item
        for item in (service_result.verification_results if service_result else [])
    }
    ineligible = ineligible or {}
    expectations_by_pair: dict[tuple[str, str], list[Any]] = {}
    for expectation in plan.verification_expectations:
        if metrics is not None:
            metrics.expectations_indexed += 1
        expectations_by_pair.setdefault(
            (expectation.service_id, expectation.client_device_id), []
        ).append(expectation)
    services_by_client: dict[str, list[ServiceDefinition]] = {}
    for service in services:
        for client_id in service.client_device_ids:
            if metrics is not None:
                metrics.memberships_indexed += 1
            services_by_client.setdefault(client_id, []).append(service)

    outcomes: list[ClientServiceOutcome] = []
    for client_id in sorted(services_by_client):
        results: dict[str, ClientCheckOutcome] = {}
        for service in services_by_client[client_id]:
            if metrics is not None:
                metrics.pairs_assembled += 1
            checks: list[ClientCheckRow] = []
            service_limitations = [
                f"service_ineligible:{item}" for item in ineligible.get(service.id, [])
            ]
            for expectation in expectations_by_pair.get((service.id, client_id), ()):
                if metrics is not None:
                    metrics.check_lookups += 1
                row = rows_by_expectation.get(expectation.id)
                if row is None:
                    checks.append(
                        ClientCheckRow(
                            expectation_id=expectation.id,
                            kind=expectation.kind,
                            required=expectation.required,
                            status=ActionExecutionStatus.SKIPPED,
                            cause=(
                                "service_ineligible"
                                if service.id in ineligible
                                else "not_executed"
                            ),
                            limitations=(
                                service_limitations
                                if service.id in ineligible
                                else ["service_not_applied"]
                            ),
                        )
                    )
                    continue
                checks.append(
                    ClientCheckRow(
                        expectation_id=expectation.id,
                        kind=expectation.kind,
                        required=expectation.required,
                        status=row.status,
                        observation=row.observation,
                        cause=row.cause,
                        claim_level=row.claim_level,
                        fresh_evidence=row.fresh_evidence,
                        failure_code=row.failure_code,
                        limitations=list(row.limitations),
                    )
                )
            results[service.id] = ClientCheckOutcome(
                service_id=service.id,
                service_type=service.service_type,
                status=(
                    ActionExecutionStatus.SKIPPED
                    if service.id in ineligible
                    else _aggregate_required(checks)
                ),
                required=service.required,
                checks=checks,
                limitations=sorted(
                    {
                        *service_limitations,
                        *(item for check in checks for item in check.limitations),
                    }
                ),
            )
        outcomes.append(
            ClientServiceOutcome(
                client_device_id=client_id,
                deployed_name=deployed_names.get(client_id, ""),
                model=models.get(client_id, ""),
                results=results,
            )
        )
    return outcomes


def _service_outcomes(
    plan: ServicePlan,
    service_result: ServiceApplicationResult | None,
    eligible: Sequence[ServiceDefinition],
    ineligible: dict[str, list[str]],
) -> list[ServiceEntryOutcome]:
    """Report every requested service, including the ones that were excluded."""
    by_id = {
        item.service_id: item
        for item in (service_result.services if service_result else [])
    }
    eligible_ids = {item.id for item in eligible}
    outcomes: list[ServiceEntryOutcome] = []
    for service in plan.services:
        if service.id not in eligible_ids:
            outcomes.append(
                ServiceEntryOutcome(
                    service_id=service.id,
                    service_type=service.service_type,
                    usability_status=ActionExecutionStatus.SKIPPED,
                    application_status=ActionExecutionStatus.SKIPPED,
                    required=service.required,
                    selected_clients=list(service.client_device_ids),
                    limitations=[
                        f"service_ineligible:{item}"
                        for item in ineligible.get(service.id, ["capability_unknown"])
                    ],
                )
            )
            continue
        observed = by_id.get(service.id)
        unknown = ActionExecutionStatus.UNKNOWN
        outcomes.append(
            ServiceEntryOutcome(
                service_id=service.id,
                service_type=service.service_type,
                usability_status=(observed.usability_status if observed else unknown),
                application_status=(
                    observed.application_status if observed else unknown
                ),
                direct_readback_status=(
                    observed.direct_readback_status if observed else unknown
                ),
                behavioral_status=(observed.behavioral_status if observed else unknown),
                required=service.required,
                selected_clients=list(service.client_device_ids),
            )
        )
    return outcomes


def _overall_status(
    clients: Sequence[ClientServiceOutcome],
    service_result: ServiceApplicationResult | None,
    *,
    e5_effect_uncertain: bool,
) -> ServiceRunStatus:
    """One word for the run, never stronger than its weakest fact supports."""
    if e5_effect_uncertain:
        return ServiceRunStatus.UNKNOWN
    if service_result is None:
        return ServiceRunStatus.FAILED
    if (
        service_result.status is ConfigurationApplicationStatus.FAILED
        or service_result.failure_code
        is ConfigurationFailureCode.POSTCONDITION_UNSATISFIED
    ):
        return ServiceRunStatus.FAILED
    if service_result.failure_code in {
        ConfigurationFailureCode.OUTCOME_UNKNOWN,
        ConfigurationFailureCode.SESSION_FAILED,
    }:
        return ServiceRunStatus.UNKNOWN
    statuses = [
        outcome.status
        for client in clients
        for outcome in client.results.values()
        if outcome.required
    ]
    if any(item is ActionExecutionStatus.FAILED for item in statuses):
        return ServiceRunStatus.FAILED
    if service_result.status in {
        ConfigurationApplicationStatus.PARTIAL,
        ConfigurationApplicationStatus.SKIPPED,
    }:
        return ServiceRunStatus.PARTIAL
    if statuses and all(item is ActionExecutionStatus.VERIFIED for item in statuses):
        return ServiceRunStatus.VERIFIED
    if statuses and all(item is ActionExecutionStatus.UNKNOWN for item in statuses):
        return ServiceRunStatus.UNKNOWN
    return ServiceRunStatus.PARTIAL


def apply_enterprise_services(
    intent_json: str,
    *,
    deployment_id: str,
    packet_tracer_version: str,
    import_preflight: Any,
    manifest_store: DeploymentManifestPort | None = None,
    manifest_store_factory: Callable[[], DeploymentManifestPort] | None = None,
    runtimes: ServiceStageRuntimes | None = None,
    record_store: ServiceRunRecordPort | None = None,
    record_store_factory: Callable[[], ServiceRunRecordPort] | None = None,
    environment_fingerprint: EnvironmentFingerprint | None = None,
    transport_selection: TransportSelection | None = None,
    endpoint_observer: EndpointDriftObserver | None = None,
    session_factory: Callable[[], ServiceInvocationBinding] | None = None,
    capability_catalog: Callable[[str], ServiceCapabilityRecords] = (
        packet_tracer_service_capabilities
    ),
    run_label: str = "",
    run_id: str = "",
    source_tree: SourceTreeIdentity | None = None,
    now: Callable[[], datetime] | None = None,
    secret_resolver: SecretResolver | None = None,
    message_nonce_factory: Callable[[], str] = _fresh_nonce,
) -> ServiceStageResult:
    """Apply and verify the requested services against an existing deployment.

    Takes the tool's own input, the raw intent JSON, rather than a parsed
    intent: A1 is an admission step with its own refusal and its own record
    consequence, so it belongs to the same code the tool calls. That also keeps
    the MCP adapter a translation layer with no orchestration of its own, and
    lets the offline tests prove that invalid JSON reaches no bridge through
    the real production path instead of a helper.
    """
    started = monotonic()
    clock = now or (lambda: datetime.now(UTC))
    resolved_run_id = run_id or _generated_run_id(clock())
    gate = _MutationGate()
    early_trace = AdmissionTrace()

    # -- A1: parse. No identity yet, so no record and no bridge. ----------
    try:
        if len(intent_json.encode("utf-8")) > MAX_INTENT_JSON_BYTES:
            raise ValueError("The service intent exceeds the input budget.")
        intent = EnterpriseIntent.model_validate_json(intent_json)
    except ValueError as exc:
        return _unbound_result(
            run_id=resolved_run_id,
            run_label=run_label,
            code=ServiceEntryRefusal.INTENT_INVALID,
            detail=_external_cause(exc),
            step="A1",
            packet_tracer_version=packet_tracer_version,
            transport="",
            started=started,
        )

    # -- A2: resolve the deployment. Still no bound identity. -------------
    try:
        if manifest_store is None:
            if manifest_store_factory is None:
                raise TypeError("A manifest store or factory is required.")
            manifest_store = manifest_store_factory()
        manifest = manifest_store.latest_by_deployment_id(deployment_id)
    except Exception as exc:
        return _unbound_result(
            run_id=resolved_run_id,
            run_label=run_label,
            code=ServiceEntryRefusal.DEPLOYMENT_MANIFEST_UNREADABLE,
            detail=_external_cause(exc),
            step="A2",
            packet_tracer_version=packet_tracer_version,
            transport="",
            started=started,
            admission=early_trace,
        )
    if manifest is None:
        return _unbound_result(
            run_id=resolved_run_id,
            run_label=run_label,
            code=ServiceEntryRefusal.DEPLOYMENT_MANIFEST_MISSING,
            detail=f"No deployment manifest is stored for {deployment_id!r}.",
            step="A2",
            packet_tracer_version=packet_tracer_version,
            transport="",
            started=started,
            admission=early_trace,
        )
    early_trace.reads.append(
        AdmissionRead(step="A2", subject=deployment_id, outcome=manifest.semantic_hash)
    )

    def early_refusal(
        step: str,
        code: ServiceEntryRefusal,
        detail: str,
    ) -> ServiceStageResult:
        """Persist A3/A4 refusal facts without claiming execution provenance."""
        nonlocal record_store
        if record_store is None:
            try:
                if record_store_factory is None:
                    raise TypeError("An early record store factory is required.")
                record_store = record_store_factory()
            except Exception as exc:
                result = _unbound_result(
                    run_id=resolved_run_id,
                    run_label=run_label,
                    code=code,
                    detail=detail,
                    step=step,
                    packet_tracer_version=packet_tracer_version,
                    transport="",
                    started=started,
                    admission=early_trace,
                )
                result.persist_error = _external_cause(exc)
                result.limitations = ["persist_error:early_refusal"]
                return result
        early_run = _Run(
            run_id=resolved_run_id,
            run_label=run_label,
            started=started,
            now=clock,
            record_store=record_store,
            gate=gate,
            trace=early_trace,
            record=ServiceRunRecord(
                run_id=resolved_run_id,
                run_label=run_label,
                created_at=clock(),
                packet_tracer_version=packet_tracer_version,
            ),
        )
        return _refused(
            early_run,
            step=step,
            code=code,
            detail=detail,
            packet_tracer_version=packet_tracer_version,
            transport="",
            deployment_id=deployment_id,
        )

    # -- A3: the caller and the manifest must agree about the build -------
    if packet_tracer_version != manifest.backend_version:
        return early_refusal(
            "A3",
            ServiceEntryRefusal.VERSION_MISMATCH,
            (
                f"Caller version {packet_tracer_version!r} does not match the "
                f"deployment manifest version {manifest.backend_version!r}."
            ),
        )

    # -- A4: this process must be the isolated live one -------------------
    isolation = import_preflight.ensure_isolated()
    early_trace.reads.append(
        AdmissionRead(
            step="A4", subject="import_isolation", outcome=isolation.state.value
        )
    )
    if not isolation.isolated:
        return early_refusal(
            "A4",
            ServiceEntryRefusal.IMPORT_ISOLATION_REFUSED,
            isolation.render(),
        )

    # -- A5: lazily bind one observed session for both stages -------------
    if session_factory is not None:
        try:
            binding = session_factory()
        except Exception as exc:
            return _unbound_result(
                run_id=resolved_run_id,
                run_label=run_label,
                code=ServiceEntryRefusal.TRANSPORT_UNAVAILABLE,
                detail=_external_cause(exc),
                step="A5",
                packet_tracer_version=packet_tracer_version,
                transport="",
                started=started,
                admission=early_trace,
            )
        runtimes = binding.runtimes
        record_store = binding.record_store
        environment_fingerprint = binding.environment_fingerprint
        transport_selection = binding.transport_selection
        endpoint_observer = binding.endpoint_observer
        source_tree = binding.source_tree
        inventory_reader = binding.inventory_reader
        secret_resolver = binding.secret_resolver
    else:
        inventory_reader = None

    if (
        runtimes is None
        or record_store is None
        or environment_fingerprint is None
        or transport_selection is None
    ):
        raise TypeError("A complete eager binding or session_factory is required.")
    source_tree = source_tree or SourceTreeIdentity()
    observed_environment = bool(
        environment_fingerprint.backend.strip()
        and environment_fingerprint.backend_version.strip()
    )
    run = _Run(
        run_id=resolved_run_id,
        run_label=run_label,
        started=started,
        now=clock,
        record_store=record_store,
        gate=gate,
        trace=early_trace,
        record=ServiceRunRecord(
            run_id=resolved_run_id,
            run_label=run_label,
            created_at=clock(),
            source_tree=source_tree,
            packet_tracer_version=packet_tracer_version,
            transport=transport_selection.channel,
            channel_fixed_at=transport_selection.fixed_at,
            environment_fingerprint_hash=(
                environment_fingerprint.semantic_hash if observed_environment else ""
            ),
        ),
    )
    refuse = _refusal_builder(
        run,
        packet_tracer_version=packet_tracer_version,
        transport=transport_selection.channel,
        deployment_id=deployment_id,
    )
    if not transport_selection.ready or not transport_selection.channel:
        return refuse(
            "A5",
            ServiceEntryRefusal.TRANSPORT_UNAVAILABLE,
            transport_selection.detail or "No transport channel is available.",
        )
    if not source_tree.sha.strip():
        return refuse(
            "A5",
            ServiceEntryRefusal.SOURCE_TREE_UNAVAILABLE,
            "The executing source-tree SHA could not be observed.",
        )
    if (
        not environment_fingerprint.backend.strip()
        or not environment_fingerprint.backend_version.strip()
        or (
            manifest.environment_fingerprint.extension_version.strip()
            and not environment_fingerprint.extension_version.strip()
        )
    ):
        return refuse(
            "A5",
            ServiceEntryRefusal.RUNTIME_PROVENANCE_UNAVAILABLE,
            "Required current runtime provenance could not be observed.",
        )

    # -- A6: the write-ahead record, before anything can have an effect ---
    run.record.deployment_id = deployment_id
    run.record.manifest_hash = manifest.semantic_hash
    run.record.physical_topology_hash = manifest.physical_topology_hash
    run.record.bound = True
    run.record.admission = run.trace
    try:
        run.record_path = record_store.begin(run.record)
        run.persisted_stage = ServiceStage.ADMISSION
    except RunRecordPersistenceError as exc:
        run.record.bound = False
        return refuse(
            "A6",
            ServiceEntryRefusal.RECORD_STORE_UNWRITABLE,
            _external_cause(exc),
        )

    # -- A7: compose, deriving policy once canonical identities exist ------
    capabilities = capability_catalog(manifest.backend_version)
    run.record.capability_snapshot = CapabilitySnapshotSummary(
        packet_tracer_version=manifest.backend_version,
        catalog_hash=capability_snapshot_hash(capabilities),
        provenance_by_key=provenance_by_key(capabilities),
    )
    composition = compose_enterprise_reference(
        intent,
        packet_tracer_version=manifest.backend_version,
        deployment_manifest=manifest,
        services=True,
        service_capabilities=capabilities,
    )
    if composition.service_policy_issues:
        first = next(
            item
            for item in composition.service_policy_issues
            if item.severity is ConfigurationIssueSeverity.ERROR
        )
        codes = {
            ConfigurationIssueCode.DNS_SERVER_ADDRESS_REQUIRED: (
                ServiceEntryRefusal.DNS_SERVER_ADDRESS_REQUIRED
            ),
            ConfigurationIssueCode.DNS_AUTHORITY_CONFLICT: (
                ServiceEntryRefusal.DNS_AUTHORITY_CONFLICT
            ),
            ConfigurationIssueCode.DHCP_AUTHORITY_CONFLICT: (
                ServiceEntryRefusal.DHCP_AUTHORITY_CONFLICT
            ),
            ConfigurationIssueCode.DHCP_RELAY_REQUIRED: (
                ServiceEntryRefusal.DHCP_RELAY_REQUIRED
            ),
        }
        return refuse(
            "A7",
            codes.get(first.code, ServiceEntryRefusal.COMPOSITION_FAILED),
            first.message,
        )
    if composition.issues or composition.services is None:
        return refuse(
            "A7",
            ServiceEntryRefusal.COMPOSITION_FAILED,
            _sanitized(
                "; ".join(composition.issues) or "Composition produced no service plan."
            ),
        )
    service_plan = composition.services
    configuration_plan = composition.configuration
    if _reporting_budget_exceeded(service_plan):
        return refuse(
            "A7",
            ServiceEntryRefusal.COMPOSITION_FAILED,
            "The selected service response exceeds the offline-measured "
            "reporting budget.",
        )
    run.record.configuration_plan_id = configuration_plan.id
    run.record.configuration_semantic_hash = configuration_plan.semantic_hash
    run.record.service_semantic_hash = service_plan.semantic_hash
    run.record.dhcp_authorities = _dhcp_authorities(service_plan)

    # -- A8: the composed identity must be the deployed one ---------------
    if composition.topology.physical_identity_hash != manifest.physical_topology_hash:
        return refuse(
            "A8",
            ServiceEntryRefusal.TARGET_IDENTITY_MISMATCH,
            "The composed physical topology hash does not match the deployment.",
        )
    try:
        validate_manifest_environment(manifest, environment_fingerprint)
    except DeploymentIdentityError as exc:
        return refuse(
            "A8",
            ServiceEntryRefusal.ENVIRONMENT_FINGERPRINT_MISMATCH,
            str(exc),
        )
    run.read("A8", "environment_fingerprint", environment_fingerprint.semantic_hash)

    # -- A9: eligibility, per operation, on its own target ----------------
    # Resolve this before inventory/path admission so an optional excluded
    # service cannot add identities to the governed runtime read or block the
    # closure that is actually authorized to execute.
    eligible, ineligible, shared_writers = _service_eligibility(
        service_plan, capabilities
    )
    required_ineligible = sorted(
        service.id
        for service in service_plan.services
        if service.id in ineligible and service.required
    )
    if required_ineligible:
        return refuse(
            "A9",
            ServiceEntryRefusal.SERVICE_INELIGIBLE,
            _sanitized(
                "; ".join(
                    f"{identifier}: {', '.join(ineligible[identifier])}"
                    for identifier in required_ineligible
                )
            ),
        )
    for identifier, operations in sorted(ineligible.items()):
        run.limitations.append(
            "service_ineligible:" + ",".join(f"{identifier}:{op}" for op in operations)
        )
    if not eligible:
        return refuse(
            "A9",
            ServiceEntryRefusal.CAPABILITY_UNKNOWN,
            "No requested service is eligible on this build.",
        )
    try:
        selected_plan = _plan_for(service_plan, eligible, shared_writers)
        shared_content_bindings = _shared_content_execution_bindings(
            service_plan, selected_plan
        )
    except ValueError as exc:
        return refuse(
            "A9",
            ServiceEntryRefusal.SERVICE_INELIGIBLE,
            _sanitized(str(exc)),
        )
    run.record.selected_clients = sorted(_selected_clients(service_plan, eligible))
    run.record.selected_service_ids = [item.id for item in selected_plan.services]
    run.record.selected_action_ids = [item.id for item in selected_plan.actions]
    run.record.shared_content_bindings = shared_content_bindings

    service_subject_ids = {
        device_id
        for service in eligible
        for device_id in [
            service.host_device_id,
            *service.client_device_ids,
        ]
    }
    unsupported = _unsupported_paths(
        configuration_plan,
        service_plan,
        eligible,
    )
    if unsupported:
        return refuse(
            "A8",
            ServiceEntryRefusal.SERVICE_PATH_UNSUPPORTED,
            "The selected path is outside the static, same-site, same-segment, "
            "single-access-switch S1 contract: " + ", ".join(unsupported),
        )

    # -- A9: credentials, before any user-state mutation (R-SEC-01) -------
    # Only an eligible service can dispatch, so only its references matter,
    # and every one of them must resolve on the authenticated HTTP channel
    # before E5 runs. A refusal names references, never a value or a
    # resolver's own message.
    references = secret_refs(selected_plan.actions)
    if references:
        if transport_selection.channel != SECRET_CHANNEL:
            return refuse(
                "A9",
                ServiceEntryRefusal.SECRET_TRANSPORT_UNAVAILABLE,
                f"Secret-bearing actions require the {SECRET_CHANNEL} channel; "
                f"{transport_selection.channel!r} was selected and no fallback "
                "exists.",
            )
        unresolved: list[str] = []
        for reference in references:
            try:
                if secret_resolver is None:
                    raise LookupError("no secret resolver is bound")
                secret_resolver.resolve(reference)
            except Exception as exc:
                category = getattr(exc, "reason", "") or type(exc).__name__
                unresolved.append(f"{reference}:{category}")
                continue
            run.read("A9", f"secret_ref:{reference}", "resolved")
        if unresolved:
            return refuse(
                "A9",
                ServiceEntryRefusal.SECRET_UNRESOLVED,
                _sanitized("Unresolved secret references: " + ", ".join(unresolved)),
            )

    # A8's one immutable inventory snapshot must already include every owner
    # that A10 can authorize. Computing the pure closure here does not mutate or
    # decide retention; it supplies the complete manifest-bound target universe.
    try:
        scope = _e5_closure(configuration_plan, service_plan, eligible)
    except ValueError as exc:
        return refuse(
            "A10",
            ServiceEntryRefusal.SERVICE_PATH_UNSUPPORTED,
            _sanitized(str(exc)),
        )
    actions_by_id = {item.id: item for item in configuration_plan.actions}
    semantic_ids = sorted(
        service_subject_ids
        | {actions_by_id[identifier].device_id for identifier in scope}
    )
    try:
        runtime_names = [
            manifest.binding_for(identifier).deployed_name
            for identifier in semantic_ids
        ]
        inventory = (
            inventory_reader(runtime_names)
            if inventory_reader is not None
            else runtimes.configuration.inventory()
        )
    except Exception as exc:
        return refuse(
            "A8",
            ServiceEntryRefusal.TARGET_IDENTITY_MISMATCH,
            f"Runtime inventory failed: {_external_cause(exc)}",
        )
    run.read("A8", "runtime_inventory", str(len(inventory)))
    try:
        targets = resolve_manifest_targets(
            manifest,
            physical_topology_hash=service_plan.source_topology_hash,
            semantic_device_ids=semantic_ids,
            inventory=inventory,
        )
    except DeploymentIdentityError as exc:
        return refuse("A8", ServiceEntryRefusal.TARGET_IDENTITY_MISMATCH, str(exc))
    deployed_names = {key: value.device_name for key, value in targets.items()}
    models = {key: value.model for key, value in targets.items()}

    # -- A10: the E5 scope, its drift, and any retained result ------------
    excluded = {item.id for item in configuration_plan.actions} - scope
    conflicts, unreadable, endpoint_confirmed = _drift_conflicts(
        configuration_plan, scope, deployed_names, endpoint_observer, run
    )
    run.record.e5_effect_scope = E5EffectScope(
        mutated=sorted(scope),
        excluded=sorted(excluded),
        conflicts=conflicts,
        declarative_only=sorted(
            action.id
            for action in configuration_plan.actions
            if action.id in scope and not isinstance(action, SetEndpointStaticAddress)
        ),
    )
    if conflicts:
        return refuse(
            "A10",
            ServiceEntryRefusal.EXISTING_CONFIGURATION_CONFLICT,
            "Existing endpoint addressing differs from the plan: "
            + ", ".join(conflicts),
        )
    if unreadable:
        return refuse(
            "A10",
            ServiceEntryRefusal.DRIFT_UNREADABLE,
            "Endpoint drift could not be observed, which is unknown and not "
            "empty: " + ", ".join(unreadable),
        )
    try:
        prior = record_store.retained_result_for(
            deployment_id,
            manifest_hash=manifest.semantic_hash,
            configuration_semantic_hash=configuration_plan.semantic_hash,
            environment_fingerprint_hash=environment_fingerprint.semantic_hash,
        )
    except RunRecordPersistenceError as exc:
        return refuse(
            "A10",
            ServiceEntryRefusal.RETAINED_RESULT_INVALID,
            _external_cause(exc),
        )
    retained_results = _fresh_retained_results(
        prior,
        configuration_plan,
        scope,
        endpoint_confirmed,
        runtimes.configuration,
        run,
    )
    retained_ids = {item.action_id for item in retained_results}
    mutation_scope = scope - retained_ids
    run.record.e5_effect_scope = E5EffectScope(
        mutated=sorted(mutation_scope),
        retained=sorted(retained_ids),
        excluded=sorted(excluded),
        conflicts=conflicts,
        declarative_only=sorted(
            action.id
            for action in configuration_plan.actions
            if action.id in mutation_scope
            and not isinstance(action, SetEndpointStaticAddress)
        ),
    )
    return _execute(
        run,
        runtimes=runtimes,
        manifest=manifest,
        environment_fingerprint=environment_fingerprint,
        configuration_plan=configuration_plan,
        device_capabilities=composition.capabilities,
        service_plan=service_plan,
        selected_plan=selected_plan,
        capabilities=capabilities,
        eligible=eligible,
        ineligible=ineligible,
        mutation_scope=mutation_scope,
        governed_scope=scope,
        retained_action_results=retained_results,
        excluded=excluded,
        deployed_names=deployed_names,
        models=models,
        packet_tracer_version=packet_tracer_version,
        transport=transport_selection.channel,
        deployment_id=deployment_id,
        message_nonce_factory=message_nonce_factory,
    )


def _execute(
    run: _Run,
    *,
    runtimes: ServiceStageRuntimes,
    manifest: DeploymentManifest,
    environment_fingerprint: EnvironmentFingerprint,
    configuration_plan: Any,
    device_capabilities: dict[str, Any],
    service_plan: ServicePlan,
    selected_plan: ServicePlan,
    capabilities: ServiceCapabilityRecords,
    eligible: Sequence[ServiceDefinition],
    ineligible: dict[str, list[str]],
    mutation_scope: set[str],
    governed_scope: set[str],
    retained_action_results: Sequence[ActionApplicationResult],
    excluded: set[str],
    deployed_names: dict[str, str],
    models: dict[str, str],
    packet_tracer_version: str,
    transport: str,
    deployment_id: str,
    message_nonce_factory: Callable[[], str] = _fresh_nonce,
) -> ServiceStageResult:
    """Run the effect stages, in order, behind the mutation gate.

    E1 and E4 are the only two steps here that touch user state. Everything
    between and after them either reads, derives or records, which is why the
    gate can close after a persistence failure without stopping the run from
    finishing honestly.
    """
    context = ConfigurationRuntimeContext(
        backend=manifest.backend,
        backend_version=manifest.backend_version,
        capability_snapshot_hash=run.record.capability_snapshot.catalog_hash,
        environment_fingerprint=environment_fingerprint,
    )
    configuration_runtime = _GatedConfigurationRuntime(runtimes.configuration, run.gate)
    service_runtime = _GatedServiceRuntime(runtimes.services, run.gate)

    # -- E1: the bounded E5 application -----------------------------------
    run.transition(ServiceStage.CONFIGURATION_APPLY, outcome="started")
    try:
        configuration_result = ConfigurationApplicator(configuration_runtime).apply(
            configuration_plan,
            actual_source_topology_hash=manifest.physical_topology_hash,
            capabilities=device_capabilities,
            runtime_context=context,
            deployment_manifest=manifest,
            mutation_action_ids=sorted(mutation_scope),
            excluded_action_ids=sorted(excluded),
            retained_action_results=retained_action_results,
        )
    except ServiceEffectHalted as exc:
        return _halted(
            run,
            detail=str(exc),
            stage=ServiceStage.CONFIGURATION_APPLY,
            packet_tracer_version=packet_tracer_version,
            transport=transport,
            deployment_id=deployment_id,
            service_plan=service_plan,
            eligible=eligible,
            ineligible=ineligible,
            deployed_names=deployed_names,
            models=models,
        )
    run.record.configuration_result = configuration_result
    run.record.e5_effect_scope = E5EffectScope(
        mutated=list(configuration_result.mutation_action_ids),
        retained=list(configuration_result.retained_action_ids),
        excluded=list(configuration_result.excluded_action_ids),
        conflicts=list(run.record.e5_effect_scope.conflicts),
        declarative_only=list(run.record.e5_effect_scope.declarative_only),
    )
    run.transition(ServiceStage.CONFIGURATION_APPLY, outcome="completed")

    # -- E2: refuse to build on an E5 state nobody can describe ------------
    uncertain = _e5_effect_is_uncertain(configuration_result, governed_scope)
    if uncertain:
        run.record.e5_effect_uncertain = True
        run.record.dirty_state = DirtyState.UNKNOWN
        run.limitations.extend(f"e5_effect_uncertain:{item}" for item in uncertain)
        return _finish(
            run,
            configuration_result=configuration_result,
            service_result=None,
            service_plan=service_plan,
            eligible=eligible,
            ineligible=ineligible,
            deployed_names=deployed_names,
            models=models,
            stage=ServiceStage.CONFIGURATION_APPLY,
            packet_tracer_version=packet_tracer_version,
            transport=transport,
            deployment_id=deployment_id,
            refusal_code=ServiceEntryRefusal.E5_EFFECT_UNCERTAIN,
            blocked_reason=(
                "E5 rows in scope left their effect unknown, so no E6 effect "
                "was dispatched: " + ", ".join(uncertain)
            ),
        )

    contradiction = _e5_contradiction(configuration_result, governed_scope)
    if contradiction:
        run.record.dirty_state = configuration_result.dirty_state
        run.limitations.append("e5_contradiction")
        return _finish(
            run,
            configuration_result=configuration_result,
            service_result=None,
            service_plan=service_plan,
            eligible=eligible,
            ineligible=ineligible,
            deployed_names=deployed_names,
            models=models,
            stage=ServiceStage.CONFIGURATION_APPLY,
            packet_tracer_version=packet_tracer_version,
            transport=transport,
            deployment_id=deployment_id,
            refusal_code=ServiceEntryRefusal.E5_CONTRADICTION,
            blocked_reason=(
                "E5 contradicted the governed configuration, so no E6 effect "
                "was dispatched: " + contradiction
            ),
        )

    # -- E3: foundations, from what E5 actually recorded -------------------
    run.transition(ServiceStage.FOUNDATIONAL_EVIDENCE, outcome="started")
    statuses = derive_service_foundational_statuses(service_plan, configuration_result)
    run.record.foundational_statuses = dict(statuses)
    run.transition(ServiceStage.FOUNDATIONAL_EVIDENCE, outcome="completed")

    # -- E3r: the operational-readiness requirement, derived not observed ---
    # Derivation is pure and happens here; the bounded sample happens later,
    # inside the applicator, immediately before the first request that depends
    # on it. Splitting them is what keeps the evidence fresh for its dependent
    # without querying a switch this run may never need to ask about.
    readiness_gate = ServiceAccessReadinessGate(
        derive_access_readiness_plan(
            configuration_actions=configuration_plan.actions,
            verification_expectations=selected_plan.verification_expectations,
        ),
        _access_forwarding_observer(configuration_runtime),
        clock=monotonic,
        device_names=deployed_names,
    )

    # -- E4: the E6 application --------------------------------------------
    if not run.gate.open:
        # Primary control. Entering the stage and letting the applicator
        # absorb the refusal would produce SESSION_FAILED rows for calls
        # that never happened, which is a different and false claim.
        #
        # The derived requirement is still reported, as never observed. A run
        # halted before E6 asked no switch anything, and saying which groups it
        # would have asked is a different statement from omitting them.
        run.record.operational_readiness = readiness_gate.rows()
        return _halted(
            run,
            detail=run.gate.reason,
            stage=ServiceStage.SERVICE_APPLY,
            packet_tracer_version=packet_tracer_version,
            transport=transport,
            deployment_id=deployment_id,
            configuration_result=configuration_result,
            service_plan=service_plan,
            eligible=eligible,
            ineligible=ineligible,
            deployed_names=deployed_names,
            models=models,
        )
    # One fresh nonce per message, bound into a copy of the plan and written
    # ahead with the stage record, so an earlier run's message can never
    # satisfy this run's rows and the compiled plan's hash is untouched.
    run.record.nonces = {
        reference: message_nonce_factory()
        for reference in selected_plan.operation_nonce_refs()
    }
    eligible_plan = selected_plan.with_operation_nonces(run.record.nonces)
    run.transition(ServiceStage.SERVICE_APPLY, outcome="started")
    service_result: ServiceApplicationResult | None = None
    halted_detail = ""
    try:
        service_result = ServiceApplicator(service_runtime).apply(
            eligible_plan,
            actual_source_topology_hash=manifest.physical_topology_hash,
            actual_source_configuration_hash=service_plan.source_configuration_hash,
            foundational_statuses=statuses,
            capabilities=capabilities,
            runtime_context=context,
            deployment_manifest=manifest,
            operational_readiness=readiness_gate,
        )
    except ServiceEffectHalted as exc:
        halted_detail = str(exc)
    # Written whichever way the stage ended. A halted run still observed
    # whatever readiness it reached, and hiding that would make the record
    # say the question was never asked.
    run.record.operational_readiness = readiness_gate.rows()
    run.record.service_result = service_result
    if service_result is not None:
        run.record.dirty_state = service_result.dirty_state
        run.limitations.extend(service_result.limitations)
    run.transition(ServiceStage.SERVICE_APPLY, outcome="completed")

    # -- E5r: release what this run owns, and say what happened ------------
    run.transition(ServiceStage.RELEASE, outcome="started")
    run.record.releases = _releases(service_result)
    run.transition(ServiceStage.RELEASE, outcome="completed")

    if halted_detail:
        return _halted(
            run,
            detail=halted_detail,
            stage=ServiceStage.SERVICE_APPLY,
            packet_tracer_version=packet_tracer_version,
            transport=transport,
            deployment_id=deployment_id,
            configuration_result=configuration_result,
            service_plan=service_plan,
            eligible=eligible,
            ineligible=ineligible,
            deployed_names=deployed_names,
            models=models,
        )
    return _finish(
        run,
        configuration_result=configuration_result,
        service_result=service_result,
        service_plan=service_plan,
        eligible=eligible,
        ineligible=ineligible,
        deployed_names=deployed_names,
        models=models,
        stage=ServiceStage.COMPLETED,
        packet_tracer_version=packet_tracer_version,
        transport=transport,
        deployment_id=deployment_id,
    )


def _finish(
    run: _Run,
    *,
    configuration_result: ConfigurationApplicationResult | None,
    service_result: ServiceApplicationResult | None,
    service_plan: ServicePlan,
    eligible: Sequence[ServiceDefinition],
    ineligible: dict[str, list[str]],
    deployed_names: dict[str, str],
    models: dict[str, str],
    stage: ServiceStage,
    packet_tracer_version: str,
    transport: str,
    deployment_id: str,
    refusal_code: ServiceEntryRefusal = ServiceEntryRefusal.NONE,
    blocked_reason: str = "",
) -> ServiceStageResult:
    """Assemble the response and write the terminal record."""
    clients = _client_rows(
        service_plan,
        service_result,
        service_plan.services,
        deployed_names,
        models,
        ineligible,
    )
    services = _service_outcomes(service_plan, service_result, eligible, ineligible)
    status = (
        ServiceRunStatus.UNKNOWN
        if refusal_code is ServiceEntryRefusal.E5_EFFECT_UNCERTAIN
        else _overall_status(
            clients,
            service_result,
            e5_effect_uncertain=run.record.e5_effect_uncertain,
        )
    )
    limitations = sorted(set(run.limitations))
    if run.record.capability_snapshot.provenance_by_key:
        limitations = sorted({*limitations, "provenance:documentary_baseline"})

    run.record.clients = clients
    run.record.services = services
    run.record.status = status
    run.record.refusal_code = refusal_code
    run.record.blocked_reason = blocked_reason
    run.record.limitations = limitations
    run.record.admission = run.trace
    run.record.completed_at = run.now()
    run.record.stages.append(
        StageTransition(
            stage=stage,
            started_at=run.now(),
            ended_at=run.now(),
            outcome=status.value,
            blocked_reason=blocked_reason,
        )
    )
    run.record.persisted_stage = stage
    try:
        run.record_path = run.record_store.complete(run.record)
        run.persisted_stage = stage
    except RunRecordPersistenceError as exc:
        run.persist_error = str(exc)
        limitations = sorted({*limitations, "persist_error:complete"})

    return ServiceStageResult(
        run_id=run.run_id,
        run_label=run.run_label,
        deployment_id=deployment_id,
        stage=stage,
        status=status,
        refusal_code=refusal_code,
        blocked_reason=blocked_reason,
        transport=transport,
        packet_tracer_version=packet_tracer_version,
        admission=run.trace,
        e5_effect_scope=run.record.e5_effect_scope,
        e5_effect_uncertain=run.record.e5_effect_uncertain,
        configuration_result=configuration_result,
        foundational_statuses=dict(run.record.foundational_statuses),
        service_result=service_result,
        services=services,
        clients=clients,
        releases=list(run.record.releases),
        operational_readiness=[dict(item) for item in run.record.operational_readiness],
        capability_snapshot=run.record.capability_snapshot,
        dirty_state=run.record.dirty_state,
        persisted_stage=run.persisted_stage,
        record_path=run.record_path,
        persist_error=run.persist_error,
        limitations=limitations,
        duration_ms=int((monotonic() - run.started) * 1000),
    )


def _halted(
    run: _Run,
    *,
    detail: str,
    stage: ServiceStage,
    packet_tracer_version: str,
    transport: str,
    deployment_id: str,
    service_plan: ServicePlan,
    eligible: Sequence[ServiceDefinition],
    ineligible: dict[str, list[str]],
    deployed_names: dict[str, str],
    models: dict[str, str],
    configuration_result: ConfigurationApplicationResult | None = None,
) -> ServiceStageResult:
    """Report a run whose effects were stopped by the mutation gate.

    Nothing was dispatched for the halted call: the gate refuses BEFORE the
    runtime is reached. The run still reports what it had already observed and
    the last durable stage, because that is the whole reason the record is
    written ahead.
    """
    run.record.status = ServiceRunStatus.UNKNOWN
    run.record.refusal_code = ServiceEntryRefusal.EFFECT_HALTED
    run.record.blocked_reason = detail
    run.record.dirty_state = DirtyState.UNKNOWN
    run.record.admission = run.trace
    run.record.completed_at = run.now()
    limitations = sorted({*run.limitations, "effect_halted"})
    clients = _client_rows(
        service_plan,
        None,
        service_plan.services,
        deployed_names,
        models,
        ineligible,
    )
    services = _service_outcomes(service_plan, None, eligible, ineligible)
    run.record.clients = clients
    run.record.services = services
    run.record.limitations = limitations
    try:
        run.record_path = run.record_store.complete(run.record)
    except RunRecordPersistenceError as exc:
        run.persist_error = run.persist_error or str(exc)
    return ServiceStageResult(
        run_id=run.run_id,
        run_label=run.run_label,
        deployment_id=deployment_id,
        stage=stage,
        status=ServiceRunStatus.UNKNOWN,
        refusal_code=ServiceEntryRefusal.EFFECT_HALTED,
        blocked_reason=detail,
        transport=transport,
        packet_tracer_version=packet_tracer_version,
        admission=run.trace,
        e5_effect_scope=run.record.e5_effect_scope,
        e5_effect_uncertain=run.record.e5_effect_uncertain,
        configuration_result=configuration_result,
        foundational_statuses=dict(run.record.foundational_statuses),
        services=services,
        clients=clients,
        releases=list(run.record.releases),
        operational_readiness=[dict(item) for item in run.record.operational_readiness],
        capability_snapshot=run.record.capability_snapshot,
        dirty_state=DirtyState.UNKNOWN,
        persisted_stage=run.persisted_stage,
        record_path=run.record_path,
        persist_error=run.persist_error,
        limitations=limitations,
        duration_ms=int((monotonic() - run.started) * 1000),
    )


def _releases(
    service_result: ServiceApplicationResult | None,
) -> list[OwnedResourceRelease]:
    """Collect the owned-client release outcomes the runtime reported.

    S0 records these as limitations on the verification rows, which is where
    the runtime can honestly put them. Surfacing them as their own list is a
    product requirement: an unresolved release is an operator action, and one
    buried in a per-row limitation is one nobody will act on.
    """
    if service_result is None:
        return []
    releases: list[OwnedResourceRelease] = []
    for row in service_result.verification_results:
        marker = row.observed.get("released")
        unresolved = next(
            (
                item
                for item in row.limitations
                if item.startswith("client_ownership_unresolved:")
            ),
            "",
        )
        if marker is None and not unresolved:
            continue
        outcome = str(marker).strip() if isinstance(marker, str) else "malformed"
        detail = ""
        if unresolved:
            _, _, remainder = unresolved.partition(":")
            recorded_outcome, _, recorded_detail = remainder.partition(":")
            if not outcome:
                outcome = recorded_outcome or "unknown"
            detail = recorded_detail
        if not outcome:
            outcome = "unknown"
        releases.append(
            OwnedResourceRelease(
                resource=row.expectation_id,
                outcome=outcome,
                detail=detail,
            )
        )
    return releases


def _plan_for(
    plan: ServicePlan,
    services: Sequence[ServiceDefinition],
    shared_writers: Mapping[str, SetHttpContent],
) -> ServicePlan:
    """Narrow a plan to the eligible services, keeping its identity intact.

    The plan id and both source hashes are preserved deliberately: the E6
    applicator binds them against the deployment and the E5 result, and a
    narrowed plan that re-derived its own identity would be a different plan
    claiming to be this one.
    """
    keep = {item.id for item in services}
    source_actions = {item.id: item for item in plan.actions}
    actions: list[Any] = []
    for action in plan.actions:
        if (
            isinstance(action, SetHttpContent)
            and len(set(action.shared_service_ids)) > 1
        ):
            selected_members = sorted(set(action.shared_service_ids) & keep)
            if not selected_members:
                continue
            writer = shared_writers.get(action.id)
            if writer is None or writer.service_id not in selected_members:
                raise ValueError(
                    f"Shared content action {action.id!r} has no admitted writer."
                )
            source_members = set(action.shared_service_ids)
            selected_member_ids = set(selected_members)

            def selected_dependency(
                identifier: str,
                source_members: set[str] = source_members,
                selected_members: set[str] = selected_member_ids,
            ) -> bool:
                dependency = source_actions.get(identifier)
                return not (
                    dependency is not None
                    and dependency.service_id in source_members
                    and dependency.service_id not in selected_members
                )

            actions.append(
                writer.model_copy(
                    update={
                        "shared_service_ids": selected_members,
                        "depends_on": [
                            item
                            for item in action.depends_on
                            if selected_dependency(item)
                        ],
                        "apply_dependencies": [
                            item
                            for item in action.apply_dependencies
                            if selected_dependency(item)
                        ],
                    },
                    deep=True,
                )
            )
            continue
        if action.service_id in keep:
            actions.append(action)
    action_ids = {action.id for action in actions}
    devices = {item.host_device_id for item in services} | {
        client_id for item in services for client_id in item.client_device_ids
    }
    expectations = [
        item
        for item in plan.verification_expectations
        if item.service_id in keep and item.action_id in action_ids
    ]
    expectation_ids = {item.id for item in expectations}
    for action in actions:
        missing = sorted({*action.depends_on, *action.apply_dependencies} - action_ids)
        if missing:
            raise ValueError(
                f"Selected action {action.id!r} has missing dependencies: "
                + ", ".join(missing)
            )
        missing_verifications = sorted(
            set(action.verification_dependencies) - expectation_ids
        )
        if missing_verifications:
            raise ValueError(
                f"Selected action {action.id!r} has missing verification "
                "dependencies: " + ", ".join(missing_verifications)
            )
    selected_services = [
        item.model_copy(
            update={
                "action_ids": [
                    identifier
                    for identifier in item.action_ids
                    if identifier in action_ids
                ],
                "verification_expectation_ids": [
                    identifier
                    for identifier in item.verification_expectation_ids
                    if identifier in expectation_ids
                ],
            },
            deep=True,
        )
        for item in plan.services
        if item.id in keep
    ]
    return plan.model_copy(
        update={
            "services": selected_services,
            "actions": actions,
            "foundational_requirements": [
                item
                for item in plan.foundational_requirements
                if item.device_id in devices
            ],
            "verification_expectations": expectations,
        }
    )


def _shared_content_execution_bindings(
    source: ServicePlan,
    selected: ServicePlan,
) -> list[SharedContentExecutionBinding]:
    """Persist the source ownership and the exact admitted writer projection."""
    source_by_id = {
        item.id: item for item in source.actions if isinstance(item, SetHttpContent)
    }
    bindings: list[SharedContentExecutionBinding] = []
    for action in selected.actions:
        if not isinstance(action, SetHttpContent):
            continue
        original = source_by_id.get(action.id)
        if original is None:
            raise ValueError(
                f"Selected shared content action {action.id!r} has no source action."
            )
        bindings.append(
            SharedContentExecutionBinding(
                source_action_id=original.id,
                selected_action_id=action.id,
                source_service_ids=sorted(
                    set(original.shared_service_ids or [original.service_id])
                ),
                selected_service_ids=sorted(
                    set(action.shared_service_ids or [action.service_id])
                ),
                writer_service_id=action.service_id,
                writer_service_type=action.service_type,
                dependency_ids=list(action.depends_on),
                content_source_record=action.content_source_record,
            )
        )
    return bindings


def _unsupported_paths(
    configuration_plan: Any,
    plan: ServicePlan,
    services: Sequence[ServiceDefinition],
) -> list[str]:
    """Name selected paths outside the bounded static single-switch contract.

    R-NET-01. Same-subnet addressing is what this slice supports, and saying
    so is different from claiming that a routed client would work. A routed
    path is slice S1c and needs L3 ownership this one does not have; adding a
    routing feature so a fixture passes would be building the wrong product to
    satisfy a test.
    """
    requirements: dict[str, list[Any]] = {}
    for item in plan.foundational_requirements:
        requirements.setdefault(item.device_id, []).append(item)
    actions = {item.id: item for item in configuration_plan.actions}
    delegated_clients = {
        client_id: (service.site_id, service.segment_id)
        for service in services
        if service.service_type is ServiceType.DHCP
        for client_id in service.client_device_ids
    }

    def access_switches(action_id: str) -> set[str]:
        switches: set[str] = set()
        pending = [action_id]
        visited: set[str] = set()
        while pending:
            identifier = pending.pop()
            if identifier in visited:
                continue
            visited.add(identifier)
            action = actions.get(identifier)
            if action is None:
                continue
            if isinstance(action, ConfigureAccessPort):
                switches.add(action.device_id)
            pending.extend([*action.depends_on, *action.apply_dependencies])
        return switches

    unsupported: list[str] = []
    for service in services:
        path_switches: set[str] = set()
        for device_id in [service.host_device_id, *service.client_device_ids]:
            matches = requirements.get(device_id, [])
            if len(matches) != 1:
                unsupported.append(f"{service.id}:{device_id}:foundation_identity")
                continue
            requirement = matches[0]
            expected_model = (
                "Server-PT" if device_id == service.host_device_id else "PC-PT"
            )
            if requirement.model.casefold() != expected_model.casefold():
                unsupported.append(
                    f"{service.id}:{device_id}:model_{requirement.model}"
                )
            action = actions.get(requirement.configuration_action_id)
            if action is None:
                unsupported.append(f"{service.id}:{device_id}:foundation_missing")
                continue
            if isinstance(action, SetEndpointDhcp):
                delegated = delegated_clients.get(device_id)
                if delegated != (service.site_id, service.segment_id):
                    unsupported.append(f"{service.id}:{device_id}:dhcp")
                    continue
            elif not isinstance(action, SetEndpointStaticAddress):
                unsupported.append(f"{service.id}:{device_id}:not_static")
                continue
            if action.site_id != service.site_id:
                unsupported.append(f"{service.id}:{device_id}:foreign_site")
            if requirement.segment_id != service.segment_id:
                unsupported.append(f"{service.id}:{device_id}:routed")
            switches = access_switches(action.id)
            if len(switches) != 1:
                unsupported.append(f"{service.id}:{device_id}:switching_prerequisite")
            path_switches.update(switches)
        if len(path_switches) > 1:
            unsupported.append(f"{service.id}:inter_switch")
    return sorted(unsupported)


def _sanitized(detail: str, limit: int = 240) -> str:
    """Bound a string this process composed before it is published."""
    collapsed = " ".join(str(detail).split())
    return collapsed[:limit]


def _external_cause(error: Exception) -> str:
    """Name the CATEGORY of a foreign failure without echoing its payload.

    The message of an exception raised by a collaborator is unbounded
    external content: a bridge token, a credential or a page body can all
    end up inside one. The typed category is what a caller can act on, and
    it is the only part that is safe to publish.
    """
    return type(error).__name__


def _generated_run_id(moment: datetime) -> str:
    """Generate a run id here so the use case never depends on the store."""
    return generate_run_id(moment)


def _refusal_builder(
    run: _Run,
    *,
    packet_tracer_version: str,
    transport: str,
    deployment_id: str,
) -> Callable[[str, ServiceEntryRefusal, str], ServiceStageResult]:
    """Bind the constant parts of a refusal so each call site states its own."""

    def build(step: str, code: ServiceEntryRefusal, detail: str) -> ServiceStageResult:
        return _refused(
            run,
            step=step,
            code=code,
            detail=detail,
            packet_tracer_version=packet_tracer_version,
            transport=transport,
            deployment_id=deployment_id,
        )

    return build
