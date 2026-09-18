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

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from ...domain.enterprise.models.configuration import (
    ConfigurationIssueCode,
    ConfigurationIssueSeverity,
    SetEndpointStaticAddress,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
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
from ...domain.enterprise.models.execution import DirtyState
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
    ServiceCapabilityRecords,
    ServiceDefinition,
    ServicePlan,
)
from ...domain.enterprise.models.service_run_record import (
    ServiceRunRecord,
    SourceTreeIdentity,
)
from ...domain.enterprise.models.service_runtime import ServiceApplicationResult
from ...domain.enterprise.services.service_capability_resolution import (
    provenance_by_key,
    resolve_action_capability,
    resolve_verification_capability,
)
from ...domain.enterprise.services.service_policy import derive_service_policy
from ...infrastructure.catalog.service_capabilities import (
    capability_snapshot_hash,
    packet_tracer_service_capabilities,
)
from ..ports.service_run_record import (
    DeploymentManifestPort,
    EndpointDriftObserver,
    RunRecordPersistenceError,
    ServiceRunRecordPort,
)
from .apply_configuration import ConfigurationApplicator, ConfigurationRuntime
from .apply_services import ServiceApplicator, ServiceRuntime
from .compose_enterprise_reference import compose_enterprise_reference
from .foundational_evidence import derive_service_foundational_statuses

#: The E5 row representations that mean "this action's effect is unknown".
#: The second is the legacy shape documented as D-9: the applicator turns a
#: missing runtime result into a FAILED row with that message, which is not
#: evidence of non-execution and not evidence of a clean run.
_MISSING_RESULT_MESSAGE = "Runtime returned no mutation result."


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

    def transition(self, stage: ServiceStage, outcome: str = "") -> bool:
        """Write the stage boundary before the next effectful stage begins.

        Returns whether the record is still durable. A failure after the first
        effect closes the mutation gate instead of raising: the primary error
        must survive, and the run still has cleanup and bounded observation to
        do.
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
            self.persist_error = str(exc)
            self.gate.close(
                f"The run record could not advance past "
                f"{self.persisted_stage.value if self.persisted_stage else 'admission'}."
            )
            self.limitations.append(f"persist_error:{stage.value}")
            return False
        self.persisted_stage = stage
        return True


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
) -> ServiceStageResult:
    """A1 and A2 refuse with no record: no valid bound identity exists yet."""
    return ServiceStageResult(
        run_id=run_id,
        run_label=run_label,
        stage=ServiceStage.ADMISSION,
        status=ServiceRunStatus.REFUSED,
        refusal_code=code,
        blocked_reason=detail,
        transport=transport,
        packet_tracer_version=packet_tracer_version,
        admission=AdmissionTrace(
            refusals=[AdmissionRefusal(step=step, code=code, detail=detail)]
        ),
        duration_ms=int((monotonic() - started) * 1000),
    )


def _selected_clients(
    plan: ServicePlan, services: Sequence[ServiceDefinition]
) -> set[str]:
    """Every client id any eligible service selected."""
    return {
        client_id for service in services for client_id in service.client_device_ids
    }


def _service_eligibility(
    plan: ServicePlan,
    capabilities: ServiceCapabilityRecords,
) -> tuple[list[ServiceDefinition], dict[str, list[str]]]:
    """Split the plan's services into eligible ones and named refusals.

    A service is eligible when every action it applies and every REQUIRED
    expectation it declares resolves SUPPORTED on the model that performs it.
    An optional expectation - an advisory reader, or any expectation of a
    service whose verification is not required - never gates: it is still
    compiled and still reported, and R-CAP-06 is exactly the rule that it may
    not report VERIFIED for a capability it lacks either.
    """
    actions_by_service: dict[str, list[Any]] = {}
    for action in plan.actions:
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
        if missing:
            unknown_operations[service.id] = sorted(set(missing))
            continue
        eligible.append(service)
    return eligible, unknown_operations


def _e5_closure(
    configuration_plan: Any,
    plan: ServicePlan,
    services: Sequence[ServiceDefinition],
) -> set[str]:
    """Close the eligible services' foundations over the E5 dependency graph."""
    devices = {service.host_device_id for service in services}
    devices |= _selected_clients(plan, services)
    seeds = {
        requirement.configuration_action_id
        for requirement in plan.foundational_requirements
        if requirement.device_id in devices and requirement.configuration_action_id
    }
    by_id = {item.id: item for item in configuration_plan.actions}
    closed: set[str] = set()
    frontier = set(seeds)
    while frontier:
        identifier = frontier.pop()
        if identifier in closed or identifier not in by_id:
            continue
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


def _drift_conflicts(
    configuration_plan: Any,
    scope: set[str],
    deployed_names: dict[str, str],
    observer: EndpointDriftObserver | None,
    run: _Run,
) -> tuple[list[str], list[str]]:
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
    for action in configuration_plan.actions:
        if action.id not in scope or not isinstance(action, SetEndpointStaticAddress):
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
        if current and current != action.ipv4:
            conflicts.append(f"{action.id}:{current}!={action.ipv4}")
    return conflicts, unreadable


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
    expectations_by_service: dict[str, list[Any]] = {}
    for expectation in plan.verification_expectations:
        expectations_by_service.setdefault(expectation.service_id, []).append(
            expectation
        )

    outcomes: list[ClientServiceOutcome] = []
    for client_id in sorted(_selected_clients(plan, services)):
        results: dict[str, ClientCheckOutcome] = {}
        for service in services:
            if client_id not in service.client_device_ids:
                continue
            checks: list[ClientCheckRow] = []
            for expectation in expectations_by_service.get(service.id, ()):
                if expectation.client_device_id != client_id:
                    continue
                row = rows_by_expectation.get(expectation.id)
                if row is None:
                    checks.append(
                        ClientCheckRow(
                            expectation_id=expectation.id,
                            kind=expectation.kind,
                            required=expectation.required,
                            status=ActionExecutionStatus.SKIPPED,
                            cause="not_executed",
                            limitations=["service_not_applied"],
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
                status=_aggregate_required(checks),
                required=service.required,
                checks=checks,
                limitations=sorted(
                    {item for check in checks for item in check.limitations}
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
    statuses = [
        outcome.status
        for client in clients
        for outcome in client.results.values()
        if outcome.required
    ]
    if any(item is ActionExecutionStatus.FAILED for item in statuses):
        return ServiceRunStatus.FAILED
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
    runtimes: ServiceStageRuntimes,
    manifest_store: DeploymentManifestPort,
    record_store: ServiceRunRecordPort,
    import_preflight: Any,
    environment_fingerprint: EnvironmentFingerprint,
    transport_selection: TransportSelection,
    endpoint_observer: EndpointDriftObserver | None = None,
    capability_catalog: Callable[[str], ServiceCapabilityRecords] = (
        packet_tracer_service_capabilities
    ),
    run_label: str = "",
    run_id: str = "",
    source_tree: SourceTreeIdentity | None = None,
    now: Callable[[], datetime] | None = None,
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

    run = _Run(
        run_id=resolved_run_id,
        run_label=run_label,
        started=started,
        now=clock,
        record_store=record_store,
        gate=gate,
        record=ServiceRunRecord(
            run_id=resolved_run_id,
            run_label=run_label,
            created_at=clock(),
            source_tree=source_tree or SourceTreeIdentity(),
            packet_tracer_version=packet_tracer_version,
            transport=transport_selection.channel,
            channel_fixed_at=transport_selection.fixed_at,
            environment_fingerprint_hash=environment_fingerprint.semantic_hash,
        ),
    )

    # -- A1: parse. No identity yet, so no record and no bridge. ----------
    try:
        intent = EnterpriseIntent.model_validate_json(intent_json)
    except ValueError as exc:
        return _unbound_result(
            run_id=resolved_run_id,
            run_label=run_label,
            code=ServiceEntryRefusal.INTENT_INVALID,
            detail=_external_cause(exc),
            step="A1",
            packet_tracer_version=packet_tracer_version,
            transport=transport_selection.channel,
            started=started,
        )

    # -- A2: resolve the deployment. Still no bound identity. -------------
    try:
        manifest = manifest_store.latest_by_deployment_id(deployment_id)
    except Exception as exc:
        return _unbound_result(
            run_id=resolved_run_id,
            run_label=run_label,
            code=ServiceEntryRefusal.DEPLOYMENT_MANIFEST_UNREADABLE,
            detail=_external_cause(exc),
            step="A2",
            packet_tracer_version=packet_tracer_version,
            transport=transport_selection.channel,
            started=started,
        )
    if manifest is None:
        return _unbound_result(
            run_id=resolved_run_id,
            run_label=run_label,
            code=ServiceEntryRefusal.DEPLOYMENT_MANIFEST_MISSING,
            detail=f"No deployment manifest is stored for {deployment_id!r}.",
            step="A2",
            packet_tracer_version=packet_tracer_version,
            transport=transport_selection.channel,
            started=started,
        )
    run.read("A2", deployment_id, manifest.semantic_hash)

    refuse = _refusal_builder(
        run,
        packet_tracer_version=packet_tracer_version,
        transport=transport_selection.channel,
        deployment_id=deployment_id,
    )

    # -- A3: the caller and the manifest must agree about the build -------
    if packet_tracer_version != manifest.backend_version:
        return refuse(
            "A3",
            ServiceEntryRefusal.VERSION_MISMATCH,
            f"Caller version {packet_tracer_version!r} does not match the "
            f"deployment manifest version {manifest.backend_version!r}.",
        )

    # -- A4: this process must be the isolated live one -------------------
    isolation = import_preflight.ensure_isolated()
    run.read("A4", "import_isolation", isolation.state.value)
    if not isolation.isolated:
        return refuse(
            "A4",
            ServiceEntryRefusal.IMPORT_ISOLATION_REFUSED,
            isolation.render(),
        )

    # -- A5: one channel, fixed, for both stages --------------------------
    if not transport_selection.ready or not transport_selection.channel:
        return refuse(
            "A5",
            ServiceEntryRefusal.TRANSPORT_UNAVAILABLE,
            transport_selection.detail or "No transport channel is available.",
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

    # -- A7: compose, with the policy the requested services imply --------
    policy = derive_service_policy(intent)
    if not policy.is_valid:
        first = next(
            item
            for item in policy.issues
            if item.severity is ConfigurationIssueSeverity.ERROR
        )
        code = (
            ServiceEntryRefusal.DNS_SERVER_ADDRESS_REQUIRED
            if first.code is ConfigurationIssueCode.DNS_SERVER_ADDRESS_REQUIRED
            else ServiceEntryRefusal.DNS_AUTHORITY_CONFLICT
        )
        return refuse("A7", code, first.message)

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
        configuration_policy=policy.policy,
        services=True,
        service_capabilities=capabilities,
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
    run.record.configuration_plan_id = configuration_plan.id
    run.record.configuration_semantic_hash = configuration_plan.semantic_hash
    run.record.service_semantic_hash = service_plan.semantic_hash

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

    try:
        inventory = runtimes.configuration.inventory()
    except Exception as exc:
        return refuse(
            "A8",
            ServiceEntryRefusal.TARGET_IDENTITY_MISMATCH,
            f"Runtime inventory failed: {_external_cause(exc)}",
        )
    run.read("A8", "runtime_inventory", str(len(inventory)))

    semantic_ids = sorted(
        {item.device_id for item in service_plan.foundational_requirements}
        | {item.host_device_id for item in service_plan.services}
        | {
            client_id
            for item in service_plan.services
            for client_id in item.client_device_ids
        }
    )
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

    unsupported = _unsupported_paths(service_plan)
    if unsupported:
        return refuse(
            "A8",
            ServiceEntryRefusal.SERVICE_PATH_UNSUPPORTED,
            "Service clients outside the host segment need routed support that "
            "this slice does not provide: " + ", ".join(unsupported),
        )

    # -- A9: eligibility, per operation, on its own target ----------------
    eligible, ineligible = _service_eligibility(service_plan, capabilities)
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

    # -- A10: the E5 scope, its drift, and any retained result ------------
    scope = _e5_closure(configuration_plan, service_plan, eligible)
    excluded = {item.id for item in configuration_plan.actions} - scope
    conflicts, unreadable = _drift_conflicts(
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
    run.record.selected_clients = sorted(_selected_clients(service_plan, eligible))

    return _execute(
        run,
        runtimes=runtimes,
        manifest=manifest,
        environment_fingerprint=environment_fingerprint,
        configuration_plan=configuration_plan,
        device_capabilities=composition.capabilities,
        service_plan=service_plan,
        capabilities=capabilities,
        eligible=eligible,
        ineligible=ineligible,
        scope=scope,
        excluded=excluded,
        deployed_names=deployed_names,
        models=models,
        packet_tracer_version=packet_tracer_version,
        transport=transport_selection.channel,
        deployment_id=deployment_id,
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
    capabilities: ServiceCapabilityRecords,
    eligible: Sequence[ServiceDefinition],
    ineligible: dict[str, list[str]],
    scope: set[str],
    excluded: set[str],
    deployed_names: dict[str, str],
    models: dict[str, str],
    packet_tracer_version: str,
    transport: str,
    deployment_id: str,
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
            mutation_action_ids=sorted(scope),
            excluded_action_ids=sorted(excluded),
        )
    except ServiceEffectHalted as exc:
        return _halted(
            run,
            detail=str(exc),
            stage=ServiceStage.CONFIGURATION_APPLY,
            packet_tracer_version=packet_tracer_version,
            transport=transport,
            deployment_id=deployment_id,
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
    uncertain = _e5_effect_is_uncertain(configuration_result, scope)
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

    # -- E3: foundations, from what E5 actually recorded -------------------
    run.transition(ServiceStage.FOUNDATIONAL_EVIDENCE, outcome="started")
    statuses = derive_service_foundational_statuses(service_plan, configuration_result)
    run.record.foundational_statuses = dict(statuses)
    run.transition(ServiceStage.FOUNDATIONAL_EVIDENCE, outcome="completed")

    # -- E4: the E6 application --------------------------------------------
    if not run.gate.open:
        # Primary control. Entering the stage and letting the applicator
        # absorb the refusal would produce SESSION_FAILED rows for calls
        # that never happened, which is a different and false claim.
        return _halted(
            run,
            detail=run.gate.reason,
            stage=ServiceStage.SERVICE_APPLY,
            packet_tracer_version=packet_tracer_version,
            transport=transport,
            deployment_id=deployment_id,
            configuration_result=configuration_result,
        )
    eligible_plan = _plan_for(service_plan, eligible)
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
        )
    except ServiceEffectHalted as exc:
        halted_detail = str(exc)
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
        service_plan, service_result, eligible, deployed_names, models
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
        releases=list(run.record.releases),
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
        for limitation in row.limitations:
            if not limitation.startswith("release"):
                continue
            outcome, _, detail = limitation.partition(":")
            releases.append(
                OwnedResourceRelease(
                    resource=row.expectation_id, outcome=outcome, detail=detail
                )
            )
    return releases


def _plan_for(plan: ServicePlan, services: Sequence[ServiceDefinition]) -> ServicePlan:
    """Narrow a plan to the eligible services, keeping its identity intact.

    The plan id and both source hashes are preserved deliberately: the E6
    applicator binds them against the deployment and the E5 result, and a
    narrowed plan that re-derived its own identity would be a different plan
    claiming to be this one.
    """
    keep = {item.id for item in services}
    if keep == {item.id for item in plan.services}:
        return plan
    action_ids = {action.id for action in plan.actions if action.service_id in keep}
    devices = {item.host_device_id for item in services} | {
        client_id for item in services for client_id in item.client_device_ids
    }
    return plan.model_copy(
        update={
            "services": [item for item in plan.services if item.id in keep],
            "actions": [item for item in plan.actions if item.service_id in keep],
            "foundational_requirements": [
                item
                for item in plan.foundational_requirements
                if item.device_id in devices
            ],
            "verification_expectations": [
                item
                for item in plan.verification_expectations
                if item.service_id in keep and item.action_id in action_ids
            ],
        }
    )


def _unsupported_paths(plan: ServicePlan) -> list[str]:
    """Name every selected client that is not on its service host segment.

    R-NET-01. Same-subnet addressing is what this slice supports, and saying
    so is different from claiming that a routed client would work. A routed
    path is slice S1c and needs L3 ownership this one does not have; adding a
    routing feature so a fixture passes would be building the wrong product to
    satisfy a test.
    """
    segments = {
        item.device_id: item.segment_id for item in plan.foundational_requirements
    }
    unsupported: list[str] = []
    for service in plan.services:
        for client_id in service.client_device_ids:
            client_segment = segments.get(client_id)
            if client_segment is not None and client_segment != service.segment_id:
                unsupported.append(f"{service.id}:{client_id}")
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
    from ...infrastructure.persistence.service_run_record_store import (
        generate_run_id,
    )

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
