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
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

from ...domain.enterprise.models.capabilities import DeviceCapabilities
from ...domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigurationPlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationRuntimeContext,
    MutationResidue,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    decide_mutation,
)
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.execution import (
    DirtyState,
    DispatchFact,
    MutationDisposition,
    PostconditionFact,
    ResultFact,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.enterprise.models.service_plan import (
    AcquireDhcpLease,
    ConfigureServerDhcpPool,
    EnableHttpService,
    EnableHttpsService,
    EnableServerDhcp,
    ServiceCapabilityRecords,
    ServiceEvidenceKind,
    ServicePhase,
    ServicePlan,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from ...domain.enterprise.models.service_qualification import (
    Q1_PC1,
    Q1_SERVER,
    Q1_SERVER_IPV4,
    Q3_LEASE_IPV4,
    Q3_PC1,
    Q3_PC2,
    Q3_POOL,
    Q3_SERVER,
    READINESS_DEADLINE_SECONDS,
    READINESS_MAX_READS,
    BudgetRecord,
    DefaultPoolObservation,
    EnvironmentIdentity,
    ExecutionMode,
    FixtureRecord,
    MeasurementConclusion,
    MeasurementRecord,
    MeasurementStatus,
    OperationEntry,
    QualificationOutcome,
    QualificationRecord,
    QualificationRefusal,
    QualificationRequest,
    QualificationStage,
    QualificationTransition,
    RefusalKind,
    RefusalSubject,
    ReleaseRecord,
    RepositoryIdentity,
    SourceIdentity,
    StageDefinition,
    TransportIdentity,
    refusal,
    repository_refusals,
    request_refusals,
    stage_definition,
)
from ...domain.enterprise.models.service_runtime import (
    ObservationFact,
    RuntimeServiceVerification,
    ServiceApplicationResult,
)
from ...domain.enterprise.services.configuration_compiler import (
    configuration_plan_semantic_hash,
)
from ...domain.enterprise.services.service_qualification_evidence import (
    BASELINE_OBSERVED_NATIVE_DEFAULT,
    Assessment,
    BaselineAdmission,
    DefaultPoolSnapshot,
    ProbeReading,
    assess_atomicity,
    assess_bag_persistence,
    assess_dhcp_baseline_admission,
    assess_https_listener,
    assess_observer_release,
    assess_page_tables,
    assess_port_readiness,
    default_pool_differences,
    default_pool_snapshot,
    listener_toggle_established,
    marker_page_established,
    page_read_admits_second_write,
    page_write_established,
)
from ...domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from ..ports.service_qualification import (
    BuildReader,
    DispatchOutcome,
    OpenedTransport,
    QualificationRecordPort,
    QualificationTransport,
)
from ..ports.service_run_record import RunRecordPersistenceError
from .apply_configuration import ConfigurationApplicator, ConfigurationRuntime
from .apply_services import ServiceApplicator, ServiceRuntime
from .deploy_enterprise_topology import (
    PhysicalTopologyRuntime,
    disposable_workspace_error,
)
from .foundational_evidence import derive_service_foundational_statuses

SendAndWait = Callable[[str, float], str | None]
MAX_DETAIL = 240
#: The worst case of one production fetch: start, two inspections, release.
FETCH_OPERATIONS = 4
#: The ledger purpose prefix every native default reading is dispatched under.
Q3_DEFAULT_PURPOSE = "q3:native_default"


def _bounded(value: object) -> str:
    """Reduce one value to a bounded single-line diagnostic."""
    return " ".join(str(value or "").split())[:MAX_DETAIL]


# -- ledger --------------------------------------------------------------------


class LedgerPhase(StrEnum):
    """The phase a counted operation belongs to."""

    __str__ = Enum.__str__

    ADMISSION = "admission"
    SETUP = "setup"
    EXPERIMENT = "experiment"
    FINALIZATION = "finalization"


class OperationRefused(RuntimeError):
    """Raised when the ledger refuses a call before it is dispatched.

    The refusal proves that this one call did not run. It says nothing about
    any earlier call, which is why it is never used as evidence of non-effect.
    """

    def __init__(self, reason: str) -> None:
        """Carry the typed reason for the refusal."""
        super().__init__(reason)
        self.reason = reason


class OperationLedger:
    """Count every engine operation against one stage ceiling.

    The counting unit is one command dispatched through the fixed transport,
    whatever its result. Outside finalization the reserve is untouchable, and
    each call's timeout is capped so that the reserved seconds survive too.
    """

    def __init__(
        self,
        *,
        max_operations: int,
        max_seconds: float,
        clock: Callable[[], float],
    ) -> None:
        """Start the ledger clock for one invocation."""
        self._max_operations = max_operations
        self._max_seconds = float(max_seconds)
        self._clock = clock
        self._start = clock()
        self._reserve_operations = 0
        self._reserve_seconds = 0.0
        self._reserved = False
        self._effects_open = True
        self._halt_reason = ""
        self.phase = LedgerPhase.ADMISSION
        self.purpose = ""
        self.used = 0
        self.entries: list[OperationEntry] = []

    @property
    def refused_calls(self) -> int:
        """Return how many calls were refused before dispatch."""
        return sum(1 for item in self.entries if item.refused)

    def elapsed(self) -> float:
        """Return the seconds since the ledger started."""
        return max(0.0, self._clock() - self._start)

    def reserve(self, operations: int, seconds: float) -> None:
        """Set the finalization reserve once, before the first effect."""
        if self._reserved:
            raise RuntimeError("The finalization reserve is set exactly once.")
        self._reserve_operations = operations
        self._reserve_seconds = float(seconds)
        self._reserved = True

    def enter(self, phase: LedgerPhase) -> None:
        """Mark the phase that subsequent calls belong to."""
        self.phase = phase

    def close_effects(self, reason: str) -> None:
        """Admit only finalization calls from now on."""
        self._effects_open = False
        self._halt_reason = reason

    @contextmanager
    def purpose_of(self, purpose: str) -> Iterator[None]:
        """Label every call made inside the block."""
        previous = self.purpose
        self.purpose = purpose
        try:
            yield
        finally:
            self.purpose = previous

    def allowance(self) -> tuple[int, float]:
        """Return the operations and seconds the current phase may still use."""
        final = self.phase is LedgerPhase.FINALIZATION
        operations = self._max_operations - self.used
        seconds = self._max_seconds - self.elapsed()
        if not final:
            operations -= self._reserve_operations
            seconds -= self._reserve_seconds
        return operations, seconds

    def can_afford(self, operations: int) -> bool:
        """Return whether `operations` more calls fit without the reserve."""
        remaining, seconds = self.allowance()
        return remaining >= operations and seconds > 0

    def wait(self, seconds: float, sleep: Callable[[float], None]) -> float:
        """Sleep at most `seconds`, capped by the phase's remaining time."""
        _operations, remaining = self.allowance()
        allowed = max(0.0, min(seconds, remaining))
        if allowed > 0:
            sleep(allowed)
        return allowed

    def admit(self, call: str, requested_timeout: float) -> tuple[int, float]:
        """Count one call and return its index and capped timeout, or refuse it."""
        reason = ""
        if not self._effects_open and self.phase is not LedgerPhase.FINALIZATION:
            reason = f"effects_halted:{self._halt_reason}"
        operations, seconds = self.allowance()
        if not reason and operations < 1:
            reason = "operation_budget_exhausted"
        if not reason and seconds <= 0:
            reason = "time_budget_exhausted"
        if reason:
            self.entries.append(
                OperationEntry(
                    seq=0,
                    phase=self.phase.value,
                    call=call,
                    purpose=self.purpose,
                    started_offset_seconds=round(self.elapsed(), 3),
                    refused=reason,
                )
            )
            raise OperationRefused(reason)
        timeout = max(0.0, min(float(requested_timeout), seconds))
        self.used += 1
        self.entries.append(
            OperationEntry(
                seq=self.used,
                phase=self.phase.value,
                call=call,
                purpose=self.purpose,
                timeout_seconds=round(timeout, 3),
                started_offset_seconds=round(self.elapsed(), 3),
            )
        )
        return len(self.entries) - 1, timeout

    def settle(
        self, index: int, *, dispatch: DispatchFact, result: ResultFact, started: float
    ) -> None:
        """Attach the channel's facts to one counted call."""
        entry = self.entries[index]
        self.entries[index] = entry.model_copy(
            update={
                "dispatch": dispatch.value,
                "result": result.value,
                "elapsed_seconds": round(max(0.0, self.elapsed() - started), 3),
            }
        )


@dataclass(frozen=True)
class _Outcome:
    """A dispatch outcome for a call that raised inside the transport."""

    dispatch: DispatchFact
    result: ResultFact
    body: str | None = None
    detail: str = ""


class LedgeredTransport:
    """The only callables any runtime or probe of one invocation receives."""

    def __init__(
        self,
        ledger: OperationLedger,
        transport: QualificationTransport,
        sleep: Callable[[float], None],
        clock: Callable[[], float],
    ) -> None:
        """Bind the fixed transport to its ledger, clock and sleeper."""
        self._ledger = ledger
        self._transport = transport
        self._sleep = sleep
        self._clock = clock

    def clock(self) -> float:
        """Return the invocation's monotonic time, for runtimes that poll."""
        return self._clock()

    def capped_sleep(self, seconds: float) -> None:
        """Sleep for a runtime's poll, capped by the phase's remaining time."""
        self._ledger.wait(seconds, self._sleep)

    def send(self, js_code: str) -> bool:
        """Queue one counted fire-and-forget command."""
        index, _timeout = self._ledger.admit("send", 0.0)
        started = self._ledger.elapsed()
        try:
            accepted = bool(self._transport.send(js_code))
        except Exception:
            accepted = False
        self._ledger.settle(
            index,
            dispatch=(
                DispatchFact.ACCEPTED if accepted else DispatchFact.ACCEPTANCE_UNKNOWN
            ),
            result=ResultFact.NOT_APPLICABLE,
            started=started,
        )
        return accepted

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        """Dispatch one counted command and return its correlated body."""
        index, capped = self._ledger.admit("send_and_wait", timeout)
        started = self._ledger.elapsed()
        try:
            raw = self._transport.send_and_wait(js_code, capped)
        except Exception:
            raw = None
        self._ledger.settle(
            index,
            dispatch=(
                DispatchFact.ACCEPTED
                if raw is not None
                else DispatchFact.ACCEPTANCE_UNKNOWN
            ),
            result=ResultFact.CORRELATED
            if raw is not None
            else ResultFact.NOT_OBSERVED,
            started=started,
        )
        return raw

    def dispatch_and_wait(self, js_code: str, timeout: float) -> DispatchOutcome:
        """Dispatch one counted command and keep its typed facts."""
        index, capped = self._ledger.admit("dispatch_and_wait", timeout)
        started = self._ledger.elapsed()
        try:
            outcome: DispatchOutcome = self._transport.dispatch_and_wait(
                js_code, capped
            )
        except Exception as exc:
            outcome = _Outcome(
                DispatchFact.ACCEPTANCE_UNKNOWN,
                ResultFact.NOT_OBSERVED,
                detail=f"transport_exception:{type(exc).__name__}",
            )
        self._ledger.settle(
            index, dispatch=outcome.dispatch, result=outcome.result, started=started
        )
        return outcome


# -- boundaries and result -----------------------------------------------------


@dataclass(frozen=True)
class IsolationObservation:
    """What the process-isolation preflight established."""

    isolated: bool
    state: str
    detail: str = ""


@dataclass(frozen=True)
class RuntimeIdentity:
    """The interpreter and package origin of this process."""

    python_executable: str
    package_file: str


@dataclass(frozen=True)
class Q3ProductContract:
    """The real privately-capable product plans bound to the exact Q3 fixture."""

    topology: TopologyPlan
    manifest: DeploymentManifest
    inventory: tuple[RuntimeConfigurationTarget, ...]
    configuration_plan: ConfigurationPlan
    service_plan: ServicePlan
    device_capabilities: dict[str, DeviceCapabilities]
    service_capabilities: ServiceCapabilityRecords


@dataclass
class _Q3ConfigurationRuntime:
    """Give the product E5 runtime the exact manifest-directed Q3 inventory."""

    inner: ConfigurationRuntime
    inventory_rows: tuple[RuntimeConfigurationTarget, ...]

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        return [item.model_copy(deep=True) for item in self.inventory_rows]

    def apply_actions(self, actions) -> list[RuntimeActionMutation]:
        return self.inner.apply_actions(actions)

    def verify(self, expectations):
        return self.inner.verify(expectations)

    def wait_for_voice_access_forwarding(self, expectations):
        return self.inner.wait_for_voice_access_forwarding(expectations)


@dataclass
class _Q3ServiceRuntime:
    """Give the product E6 runtime the same exact Q3 inventory."""

    inner: ServiceRuntime
    inventory_rows: tuple[RuntimeConfigurationTarget, ...]

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        return [item.model_copy(deep=True) for item in self.inventory_rows]

    def apply_actions(self, actions) -> list[RuntimeActionMutation]:
        return self.inner.apply_actions(actions)

    def verify(self, expectation) -> RuntimeServiceVerification:
        return self.inner.verify(expectation)


def _q3_endpoint_plan(contract: Q3ProductContract) -> ConfigurationPlan:
    """Project the real E5 plan to endpoint bootstrap on the prebuilt fixture.

    Q3 creates and verifies the exact physical links itself. Switch VLAN/port
    configuration is not a DHCP native claim, so this projection removes only
    those already-owned fixture dependencies; the endpoint action and reader
    identities remain the ones the real compiler produced.
    """
    action_types = (SetEndpointStaticAddress, SetEndpointDhcp)
    actions = [
        item.model_copy(update={"depends_on": [], "apply_dependencies": []})
        for item in contract.configuration_plan.actions
        if isinstance(item, action_types)
    ]
    action_ids = {item.id for item in actions}
    device_ids = {item.device_id for item in actions}
    plan = ConfigurationPlan(
        id=contract.configuration_plan.id + "/q3-endpoints",
        source_topology_id=contract.configuration_plan.source_topology_id,
        source_topology_hash=contract.configuration_plan.source_topology_hash,
        source_topology_hash_schema=(
            contract.configuration_plan.source_topology_hash_schema
        ),
        actions=actions,
        devices=[
            item.model_copy(deep=True)
            for item in contract.configuration_plan.devices
            if item.device_id in device_ids
        ],
        verification_expectations=[
            item.model_copy(deep=True)
            for item in contract.configuration_plan.verification_expectations
            if item.action_id in action_ids
        ],
    )
    plan.semantic_hash = configuration_plan_semantic_hash(plan)
    return plan


def _q3_server_plan(plan: ServicePlan) -> ServicePlan:
    """Project exact server setup rows without changing source-plan identity."""
    actions = [
        item
        for item in plan.actions
        if isinstance(item, EnableServerDhcp | ConfigureServerDhcpPool)
    ]
    action_ids = {item.id for item in actions}
    expectations = [
        item
        for item in plan.verification_expectations
        if item.action_id in action_ids
        and item.kind is ServiceVerificationKind.DHCP_SERVER_STATE
    ]
    expectation_ids = {item.id for item in expectations}
    service_ids = {item.service_id for item in actions}
    services = [
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
        if item.id in service_ids
    ]
    return plan.model_copy(
        update={
            "services": services,
            "actions": actions,
            "verification_expectations": expectations,
        },
        deep=True,
    )


def _q3_context(contract: Q3ProductContract) -> ConfigurationRuntimeContext:
    return ConfigurationRuntimeContext(
        backend=contract.manifest.backend,
        backend_version=contract.manifest.backend_version,
        environment_fingerprint=contract.manifest.environment_fingerprint,
    )


@dataclass(frozen=True)
class QualificationBoundaries:
    """Every external boundary one invocation reaches, injected.

    The production composition lives in the CLI adapter. A simulation replaces
    only these boundaries and must say so in `execution_mode`; its records can
    never serve as promotion evidence.
    """

    execution_mode: ExecutionMode
    isolation: Callable[[], IsolationObservation]
    runtime_identity: Callable[[], RuntimeIdentity]
    repository: Callable[[], RepositoryIdentity]
    record_store: QualificationRecordPort
    open_transport: Callable[[str], OpenedTransport]
    close_transport: Callable[[OpenedTransport], None]
    fixture_plans: Callable[
        [StageDefinition], tuple[tuple[DevicePlan, ...], tuple[LinkPlan, ...]]
    ]
    build_reader: Callable[[SendAndWait], BuildReader]
    physical_runtime: Callable[[SendAndWait], PhysicalTopologyRuntime]
    probes: Callable[[LedgeredTransport, str, str], Any]
    configuration_runtime: Callable[[LedgeredTransport], ConfigurationRuntime]
    service_runtime: Callable[[LedgeredTransport], ServiceRuntime]
    clock: Callable[[], float]
    sleep: Callable[[float], None]
    now: Callable[[], datetime]
    new_run_id: Callable[[datetime], str]
    new_nonce: Callable[[], str]
    q3_product_contract: Callable[[str, str], Q3ProductContract] | None = None
    q3_required_build: str = ""
    settle_seconds: float = 2.0


@dataclass
class QualificationResult:
    """What one invocation returns to its adapter."""

    outcome: QualificationOutcome
    refusals: list[QualificationRefusal] = field(default_factory=list)
    record: QualificationRecord | None = None
    record_path: str = ""

    @property
    def exit_code(self) -> int:
        """Return the adapter exit code: 0 completed, 1 stopped, 2 refused."""
        return {
            QualificationOutcome.COMPLETED: 0,
            QualificationOutcome.STOPPED: 1,
            QualificationOutcome.REFUSED: 2,
        }[self.outcome]

    def compact_summary(self) -> dict[str, Any]:
        """Return the JSON-ready summary an operator sees."""
        summary: dict[str, Any] = {
            "outcome": self.outcome.value,
            "refusals": [item.model_dump(mode="json") for item in self.refusals],
            "record_path": self.record_path,
        }
        record = self.record
        if record is not None:
            summary.update(
                {
                    "run_id": record.run_id,
                    "stage": record.stage.value,
                    "execution_mode": record.execution_mode.value,
                    "executed_sha": record.source.executed_sha,
                    "channel": record.transport.channel,
                    "observed_build": record.environment.observed_build,
                    "operations_used": record.budget.used_operations,
                    "measurements": [
                        {
                            "id": item.experiment_id,
                            "status": item.status.value,
                            "conclusion": item.conclusion.value,
                        }
                        for item in record.measurements
                    ],
                    "primary_failure": record.primary_failure,
                    "secondary_failures": record.secondary_failures,
                    "restoration_proven": record.restoration_proven,
                    "engine_residue": record.engine_residue,
                    "dirty_state": record.dirty_state.value,
                    "persisted_step": record.persisted_step,
                    "persist_error": record.persist_error,
                }
            )
        return summary


# -- the invocation ------------------------------------------------------------


def _refused(
    refusals: Sequence[QualificationRefusal],
    record: QualificationRecord | None = None,
    record_path: str = "",
) -> QualificationResult:
    return QualificationResult(
        outcome=QualificationOutcome.REFUSED,
        refusals=list(refusals),
        record=record,
        record_path=record_path,
    )


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
    refusals = request_refusals(request)
    if refusals:
        return _refused(refusals)
    definition = stage_definition(request.stage)
    if definition is None:  # pragma: no cover - excluded by request_refusals
        return _refused([refusal(RefusalKind.MALFORMED, RefusalSubject.STAGE)])
    try:
        devices, links = boundaries.fixture_plans(definition)
    except (KeyError, ValueError) as exc:
        return _refused(
            [refusal(RefusalKind.MALFORMED, RefusalSubject.FIXTURE, _bounded(exc))]
        )
    if tuple(plan.name for plan in devices) != definition.fixture_names:
        return _refused(
            [
                refusal(
                    RefusalKind.MISMATCH,
                    RefusalSubject.FIXTURE,
                    "Resolved fixture plans are not the stage fixtures.",
                )
            ]
        )

    isolation = _isolation(boundaries)
    if not isolation.isolated:
        kind = (
            RefusalKind.UNOBSERVABLE
            if isolation.state == "INDETERMINATE"
            else RefusalKind.NOT_PERMITTED
        )
        return _refused(
            [
                refusal(
                    kind,
                    RefusalSubject.PROCESS_ISOLATION,
                    f"{isolation.state}: {isolation.detail}",
                )
            ]
        )
    repository = _repository(boundaries)
    refusals = repository_refusals(repository, request.expected_head)
    if refusals:
        return _refused(refusals)

    moment = boundaries.now()
    run_id = boundaries.new_run_id(moment)
    product_contract: Q3ProductContract | None = None
    if definition.stage is QualificationStage.Q3:
        if not boundaries.q3_required_build:
            return _refused(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "The Q3 Packet Tracer build policy is not composed.",
                    )
                ]
            )
        if request.packet_tracer_build != boundaries.q3_required_build:
            return _refused(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "Q3 is not implemented for the requested Packet Tracer build.",
                    )
                ]
            )
        if boundaries.q3_product_contract is None:
            return _refused(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.FIXTURE,
                        "The executable Q3 product contract is not composed.",
                    )
                ]
            )
        try:
            product_contract = boundaries.q3_product_contract(
                request.packet_tracer_build, run_id
            )
        except Exception as exc:
            return _refused(
                [
                    refusal(
                        RefusalKind.MALFORMED,
                        RefusalSubject.FIXTURE,
                        f"q3_product_contract:{type(exc).__name__}:{_bounded(exc)}",
                    )
                ]
            )

    record = _initial_record(
        request,
        definition,
        boundaries,
        isolation,
        repository,
        experimental_capabilities,
        moment=moment,
        run_id=run_id,
    )
    record.links = [
        {
            "device_a": item.device_a,
            "port_a": item.port_a,
            "device_b": item.device_b,
            "port_b": item.port_b,
        }
        for item in links
    ]
    try:
        record_path = boundaries.record_store.begin(record)
    except RunRecordPersistenceError as exc:
        return _refused(
            [refusal(RefusalKind.NOT_PERMITTED, RefusalSubject.RECORD, _bounded(exc))]
        )
    run = _Run(record, boundaries, record_path)

    opened: OpenedTransport | None = None
    try:
        try:
            opened = boundaries.open_transport(request.channel)
        except Exception as exc:
            opened = OpenedTransport(
                request.channel, None, False, f"open_failed:{type(exc).__name__}"
            )
        record.transport = TransportIdentity(
            channel=opened.channel, fixed_at=boundaries.now(), liveness=opened.detail
        )
        if not opened.live or opened.transport is None:
            return run.refuse_after_contact(
                refusal(
                    RefusalKind.UNOBSERVABLE,
                    RefusalSubject.TRANSPORT,
                    opened.detail or "The authorized channel is not live.",
                )
            )
        ledger = OperationLedger(
            max_operations=definition.budget.max_operations,
            max_seconds=definition.budget.max_seconds,
            clock=boundaries.clock,
        )
        run.ledger = ledger
        bound = LedgeredTransport(
            ledger, opened.transport, boundaries.sleep, boundaries.clock
        )
        return _admitted(
            run,
            request,
            definition,
            devices,
            links,
            bound,
            experimental_capabilities,
            product_contract,
        )
    finally:
        if opened is not None and opened.transport is not None:
            try:
                boundaries.close_transport(opened)
            except Exception as exc:
                record.secondary_failures.append(
                    f"transport_close:{type(exc).__name__}"
                )


def _isolation(boundaries: QualificationBoundaries) -> IsolationObservation:
    try:
        return boundaries.isolation()
    except Exception as exc:
        return IsolationObservation(False, "INDETERMINATE", type(exc).__name__)


def _repository(boundaries: QualificationBoundaries) -> RepositoryIdentity:
    try:
        return boundaries.repository()
    except Exception as exc:
        return RepositoryIdentity(error=f"repository_read_failed:{type(exc).__name__}")


def _initial_record(
    request: QualificationRequest,
    definition: StageDefinition,
    boundaries: QualificationBoundaries,
    isolation: IsolationObservation,
    repository: RepositoryIdentity,
    capabilities: frozenset[str],
    *,
    moment: datetime | None = None,
    run_id: str = "",
) -> QualificationRecord:
    moment = moment or boundaries.now()
    try:
        runtime = boundaries.runtime_identity()
    except Exception:
        runtime = RuntimeIdentity("", "")
    authorization = request.authorization
    measurements = [
        MeasurementRecord(
            experiment_id=item.id,
            hypothesis=item.hypothesis,
            required=item.required,
            status=(
                MeasurementStatus.OMITTED
                if item.omission_reason
                else MeasurementStatus.NOT_RUN
            ),
            reason=item.omission_reason,
        )
        for item in definition.experiments
    ]
    return QualificationRecord(
        run_id=run_id or boundaries.new_run_id(moment),
        stage=definition.stage,
        execution_mode=boundaries.execution_mode,
        created_at=moment,
        authorization=(
            {**asdict(authorization), "targets": list(authorization.targets)}
            if authorization is not None
            else {}
        ),
        source=SourceIdentity(
            expected_head=request.expected_head,
            executed_sha=repository.head,
            executed_tree=repository.tree,
            clean=repository.clean,
            branch=repository.branch,
            upstream=repository.upstream,
            upstream_head=repository.upstream_head,
        ),
        environment=EnvironmentIdentity(
            python_executable=runtime.python_executable,
            package_file=runtime.package_file,
            isolation_state=isolation.state,
            requested_build=request.packet_tracer_build,
        ),
        fixtures=[
            FixtureRecord(
                name=item.name,
                model=item.model,
                ipv4=item.ipv4,
                netmask=item.netmask,
                dns_server=item.dns_server,
            )
            for item in definition.fixtures
        ],
        budget=BudgetRecord(
            max_operations=definition.budget.max_operations,
            max_seconds=definition.budget.max_seconds,
            reserve_operations=definition.reserve_operations,
            reserve_seconds=definition.budget.reserve_seconds,
            planned_minimum_operations=definition.planned_minimum_operations,
        ),
        experimental_capabilities=sorted(capabilities),
        measurements=measurements,
        admission_reads=[
            f"isolation:{isolation.state}",
            f"repository:{repository.head}:{repository.tree}",
        ],
    )


class _Run:
    """The record lifecycle of one admitted invocation."""

    def __init__(
        self,
        record: QualificationRecord,
        boundaries: QualificationBoundaries,
        record_path: str,
    ) -> None:
        self.record = record
        self.boundaries = boundaries
        self.record_path = record_path
        self.ledger: OperationLedger | None = None

    def sync(self) -> None:
        """Copy the ledger into the record before every write."""
        if self.ledger is None:
            return
        self.record.operations = list(self.ledger.entries)
        self.record.budget.used_operations = self.ledger.used
        self.record.budget.refused_calls = self.ledger.refused_calls
        self.record.budget.elapsed_seconds = round(self.ledger.elapsed(), 3)

    def transition(self, step: str, outcome: str = "") -> bool:
        """Write one step boundary ahead of the work it announces.

        A failed write closes the effect gate instead of raising: the primary
        error must survive, and bounded observation plus owned finalization
        still have to run.
        """
        previous = self.record.persisted_step
        self.record.transitions.append(
            QualificationTransition(
                step=step, at=self.boundaries.now(), outcome=outcome
            )
        )
        self.record.persisted_step = step
        self.sync()
        try:
            self.record_path = self.boundaries.record_store.advance(self.record)
        except RunRecordPersistenceError as exc:
            self.record.persisted_step = previous
            if not self.record.persist_error:
                self.record.persist_error = _bounded(exc)
            self.record.limitations.append(f"persist_error:{step}")
            if self.ledger is not None:
                self.ledger.close_effects(f"record_not_advanced_past:{previous}")
            return False
        return True

    def complete(self, outcome: QualificationOutcome) -> None:
        """Write the terminal record; a failure is secondary."""
        self.record.outcome = outcome
        self.record.completed_at = self.boundaries.now()
        self.sync()
        try:
            self.record_path = self.boundaries.record_store.complete(self.record)
        except RunRecordPersistenceError as exc:
            if not self.record.persist_error:
                self.record.persist_error = _bounded(exc)
            self.record.secondary_failures.append("record_completion_failed")

    def refuse_after_contact(self, reason: QualificationRefusal) -> QualificationResult:
        """Refuse once contact began but before any effect."""
        self.record.refusals.append(reason)
        self.record.dirty_state = DirtyState.CLEAN
        self.record.primary_failure = f"refused:{reason.subject.value}"
        self.complete(QualificationOutcome.REFUSED)
        return _refused([reason], self.record, self.record_path)


def _admitted(
    run: _Run,
    request: QualificationRequest,
    definition: StageDefinition,
    devices: tuple[DevicePlan, ...],
    links: tuple[LinkPlan, ...],
    bound: LedgeredTransport,
    capabilities: frozenset[str],
    product_contract: Q3ProductContract | None = None,
) -> QualificationResult:
    record = run.record
    ledger = run.ledger
    assert ledger is not None
    boundaries = run.boundaries
    try:
        with ledger.purpose_of("read:executable_build"):
            build = boundaries.build_reader(bound.send_and_wait).read()
    except Exception as exc:
        return run.refuse_after_contact(
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.EXECUTABLE_BUILD,
                f"build_read_failed:{type(exc).__name__}",
            )
        )
    record.environment.observed_build = build.version
    record.environment.build_reader_id = build.reader_id
    record.environment.build_reader_sha256 = build.reader_sha256
    record.environment.build_observation = build.excerpt
    record.environment.build_reason = build.reason
    record.admission_reads.append(f"build:{build.version or build.reason}")
    if not build.available:
        return run.refuse_after_contact(
            refusal(
                RefusalKind.UNOBSERVABLE, RefusalSubject.EXECUTABLE_BUILD, build.reason
            )
        )
    if build.version != request.packet_tracer_build:
        return run.refuse_after_contact(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.EXECUTABLE_BUILD,
                f"Observed {build.version!r}; authorized {request.packet_tracer_build!r}.",
            )
        )
    physical = boundaries.physical_runtime(bound.send_and_wait)
    try:
        with ledger.purpose_of("read:workspace_baseline"):
            baseline = physical.observe_workspace()
    except Exception as exc:
        return run.refuse_after_contact(
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.WORKSPACE,
                f"workspace_read_failed:{type(exc).__name__}",
            )
        )
    record.workspace_baseline = baseline.compact_summary()
    record.admission_reads.append(
        "workspace:"
        + (
            f"semantic={len(baseline.semantic_devices)},links={len(baseline.links)},"
            f"engine_managed={len(baseline.backend_managed_devices)}"
            if baseline.observed
            else "unobserved"
        )
    )
    workspace_error = disposable_workspace_error(baseline)
    if workspace_error:
        return run.refuse_after_contact(
            refusal(
                (
                    RefusalKind.UNOBSERVABLE
                    if not baseline.observed
                    else RefusalKind.NOT_PERMITTED
                ),
                RefusalSubject.WORKSPACE,
                workspace_error,
            )
        )
    if baseline.backend_managed_devices:
        record.limitations.append(
            "engine_managed_objects_in_baseline:"
            + ",".join(item.name for item in baseline.backend_managed_devices)
        )
    ledger.reserve(definition.reserve_operations, definition.budget.reserve_seconds)
    if not run.transition("admitted"):
        # Nothing was effected yet, so this remains a refusal.
        return run.refuse_after_contact(
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.RECORD,
                "The write-ahead record could not advance before the first effect.",
            )
        )

    nonce = boundaries.new_nonce()
    execution = _Execution(
        run=run,
        nonce=nonce,
        definition=definition,
        devices=devices,
        links=links,
        bound=bound,
        physical=physical,
        baseline=baseline,
        channel=request.channel,
        capabilities=capabilities,
        probes=boundaries.probes(bound, record.run_id, nonce),
        product_contract=product_contract,
    )
    cancelled: BaseException | None = None
    try:
        if definition.stage is QualificationStage.Q0:
            _run_q0(execution)
        elif definition.stage is QualificationStage.Q1:
            _run_q1(execution)
        else:
            _run_q3(execution)
    except KeyboardInterrupt as exc:
        execution.stop("cancelled")
        cancelled = exc
    except Exception as exc:
        execution.interrupt_in_flight(f"exception:{type(exc).__name__}")
        execution.stop(f"exception:{type(exc).__name__}:{_bounded(exc)}")
    finally:
        try:
            _finalize(execution)
        except Exception as exc:
            # A finalization defect is secondary: the record still completes
            # with the primary outcome and whatever finalization established.
            record.secondary_failures.append(
                f"finalization:exception:{type(exc).__name__}"
            )
    completed = (
        not record.primary_failure
        and record.restoration_proven
        and all(
            item.status is MeasurementStatus.RAN
            for item in record.measurements
            if item.required
        )
    )
    run.complete(
        QualificationOutcome.COMPLETED if completed else QualificationOutcome.STOPPED
    )
    if cancelled is not None:
        raise cancelled
    return QualificationResult(
        outcome=record.outcome, record=record, record_path=run.record_path
    )


# -- execution state -----------------------------------------------------------


@dataclass
class _Execution:
    """What one admitted run owns, has concluded and has left behind."""

    run: _Run
    nonce: str
    definition: StageDefinition
    devices: tuple[DevicePlan, ...]
    links: tuple[LinkPlan, ...]
    bound: LedgeredTransport
    physical: PhysicalTopologyRuntime
    baseline: PhysicalWorkspaceObservation
    channel: str
    capabilities: frozenset[str]
    probes: Any
    product_contract: Q3ProductContract | None = None
    removal_candidates: list[DevicePlan] = field(default_factory=list)
    fixtures_ready: bool = False
    #: Run-bag state the finalizer must release. A collision means the run key
    #: is not exclusively ours, and then nothing under it is deleted.
    bag_touched: bool = False
    bag_unreleased: set[str] = field(default_factory=set)
    bag_collision: bool = False
    observers_unresolved: set[str] = field(default_factory=set)
    in_flight: tuple[str, ...] = ()
    e5_accepted: bool = False

    @property
    def record(self) -> QualificationRecord:
        """Return the record under construction."""
        return self.run.record

    @property
    def default_pool_differences(self) -> list[str]:
        """Return every difference the run's default readings revealed.

        The readings live on the record, which is the one authoritative sink,
        so this stays true after a stop and after the procedure that took them
        has concluded.
        """
        seen: list[str] = []
        for entry in self.record.native_default_pool:
            for item in entry.differences:
                if item not in seen:
                    seen.append(item)
        return seen

    @property
    def ledger(self) -> OperationLedger:
        """Return the invocation ledger."""
        assert self.run.ledger is not None
        return self.run.ledger

    @property
    def stopped(self) -> bool:
        """Return whether new effects are no longer started."""
        return bool(self.record.primary_failure)

    def stop(self, reason: str) -> None:
        """Keep the first stop reason as the primary failure."""
        if not self.record.primary_failure:
            self.record.primary_failure = _bounded(reason)

    def measurement(self, experiment_id: str) -> MeasurementRecord:
        """Return one measurement entry of the record."""
        return next(
            item
            for item in self.record.measurements
            if item.experiment_id == experiment_id
        )

    def interrupt_in_flight(self, reason: str) -> None:
        """Mark measurements that were running when the run was cut short."""
        for experiment_id in self.in_flight:
            item = self.measurement(experiment_id)
            if item.status is MeasurementStatus.NOT_RUN:
                item.status = MeasurementStatus.INTERRUPTED
                item.reason = _bounded(reason)
                item.outcome_unknown = True
        self.in_flight = ()

    def not_run(self, ids: Sequence[str], reason: str) -> None:
        """Record why required work did not start."""
        for experiment_id in ids:
            item = self.measurement(experiment_id)
            if item.status is MeasurementStatus.NOT_RUN and not item.reason:
                item.reason = _bounded(reason)

    def begin(self, ids: Sequence[str], procedure: str) -> bool:
        """Decide whether one procedure may start, and announce it durably."""
        return self.admissible(ids, procedure) and self.announce(ids, procedure)

    def admissible(
        self, ids: Sequence[str], procedure: str, extra_operations: int = 0
    ) -> bool:
        """Check stop state, prerequisites, capability scope and budget."""
        specs = [self.definition.experiment(item) for item in ids]
        if self.stopped:
            self.not_run(ids, f"stopped:{self.record.primary_failure}")
            return False
        for spec in specs:
            for prerequisite in spec.prerequisites:
                conclusion = self.measurement(prerequisite).conclusion
                if conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
                    self.not_run(
                        ids, f"prerequisite_unmet:{prerequisite}={conclusion.value}"
                    )
                    return False
            missing = sorted(set(spec.capabilities) - self.capabilities)
            if missing:
                self.not_run(ids, "capability_not_in_scope:" + ",".join(missing))
                return False
        planned = sum(item.planned_operations for item in specs) + extra_operations
        if not self.ledger.can_afford(planned):
            self.not_run(ids, f"budget_insufficient_for:{procedure}")
            self.stop(f"budget:{procedure}")
            return False
        return True

    def announce(self, ids: Sequence[str], procedure: str) -> bool:
        """Write the procedure boundary ahead of its first effect."""
        if self.stopped:
            self.not_run(ids, f"stopped:{self.record.primary_failure}")
            return False
        if not self.run.transition(f"experiment:{procedure}:started"):
            self.not_run(ids, "record_not_advanced")
            self.stop("persistence:record_not_advanced")
            return False
        self.ledger.enter(LedgerPhase.EXPERIMENT)
        self.ledger.purpose = f"experiment:{procedure}"
        self.in_flight = tuple(ids)
        return True

    def conclude(self, experiment_id: str, assessment: Assessment) -> None:
        """Store one assessment and apply the stop rules."""
        item = self.measurement(experiment_id)
        item.status = MeasurementStatus.RAN
        item.conclusion = assessment.conclusion
        item.facts = assessment.facts
        item.causes = assessment.causes
        item.limitations = assessment.limitations
        item.outcome_unknown = assessment.outcome_unknown
        self.in_flight = tuple(
            value for value in self.in_flight if value != experiment_id
        )
        if assessment.conclusion is MeasurementConclusion.CONTRADICTED:
            self.stop(f"contradiction:{experiment_id}")
        if assessment.outcome_unknown:
            self.stop(f"outcome_unknown:{experiment_id}")

    def finish(self, procedure: str) -> None:
        """Write the boundary after a procedure concluded."""
        self.ledger.purpose = ""
        if not self.run.transition(f"experiment:{procedure}:concluded"):
            self.stop("persistence:record_not_advanced")

    def settle(self) -> None:
        """Wait for asynchronous engine work, capped by the phase deadline."""
        self.ledger.wait(self.run.boundaries.settle_seconds, self.run.boundaries.sleep)

    @contextmanager
    def procedure(self, ids: Sequence[str]) -> Iterator[None]:
        """Turn a refused call inside a procedure into an interruption."""
        try:
            yield
        except OperationRefused as exc:
            self.interrupt_in_flight(f"operation_refused:{exc.reason}")
            self.stop(f"operation_refused:{exc.reason}")
        finally:
            self.not_run(ids, "not_reached")


# -- fixtures ------------------------------------------------------------------


def _setup_fixtures(execution: _Execution) -> bool:
    """Create the stage fixtures through the production physical runtime."""
    if execution.stopped:
        return False
    if not execution.run.transition("fixtures:started"):
        execution.stop("persistence:record_not_advanced")
        return False
    ledger = execution.ledger
    ledger.enter(LedgerPhase.SETUP)
    record = execution.record
    try:
        for plan in execution.devices:
            fixture = next(item for item in record.fixtures if item.name == plan.name)
            with ledger.purpose_of(f"create:{plan.name}"):
                result = execution.physical.ensure_device(plan)
            fixture.creation = result.disposition.value
            fixture.detail = _bounded(result.message)
            if result.disposition is MutationDisposition.NO_OP:
                # An existing object with this name is a collision, never
                # permission to adopt or remove it.
                execution.stop(f"fixture_collision:{plan.name}")
                return False
            execution.removal_candidates.append(plan)
            fixture.owned = result.disposition is MutationDisposition.CHANGED
            if result.disposition is MutationDisposition.UNKNOWN:
                execution.stop(f"outcome_unknown:create:{plan.name}")
                return False
            if result.disposition is not MutationDisposition.CHANGED:
                execution.stop(f"fixture_not_created:{plan.name}")
                return False
        for index, link in enumerate(execution.links, start=1):
            with ledger.purpose_of(f"create:link:{index}"):
                result = execution.physical.ensure_link(link)
            if result.disposition is MutationDisposition.UNKNOWN:
                execution.stop(f"outcome_unknown:link:{index}")
                return False
            if result.disposition is not MutationDisposition.CHANGED:
                execution.stop(f"link_not_created:{index}:{result.message}")
                return False
        with ledger.purpose_of("read:fixture_identity"):
            observed = execution.physical.observe_workspace()
    except OperationRefused as exc:
        execution.stop(f"operation_refused:{exc.reason}")
        return False
    identity_error = _fixture_identity_error(execution, observed)
    if identity_error:
        execution.stop(identity_error)
        return False
    if not execution.run.transition("fixtures:ready"):
        execution.stop("persistence:record_not_advanced")
        return False
    execution.fixtures_ready = True
    return True


def _fixture_identity_error(
    execution: _Execution, observed: PhysicalWorkspaceObservation
) -> str:
    if not observed.observed:
        return "fixture_identity_unobserved:" + observed.message
    expected = {plan.name: plan.model for plan in execution.devices}
    semantic = observed.semantic_devices
    names = [item.name for item in semantic]
    foreign = sorted(set(names) - set(expected))
    if foreign:
        return "foreign_device_observed:" + ",".join(foreign)
    for name, model in expected.items():
        matches = [item for item in semantic if item.name == name]
        if len(matches) != 1 or matches[0].model != model:
            return f"fixture_identity_mismatch:{name}"
    return ""


# -- Q0 ------------------------------------------------------------------------


def _run_q0(execution: _Execution) -> None:
    probes = execution.probes
    channel = execution.channel
    ids = ("M-ENG-1",)
    if execution.begin(ids, "ENG"):
        with execution.procedure(ids):
            # The claim may have executed whatever the channel reported back,
            # so the finalizer has to look. Only a reported collision proves
            # that nothing was written, and then there is nothing to look for.
            execution.bag_touched = True
            write = probes.write_bag_sentinel()
            read: ProbeReading | None = None
            if write.observed and write.payload["run_bag_preexisting"]:
                execution.bag_collision = True
            else:
                execution.bag_unreleased.add("sentinel")
                read = probes.read_and_release_bag_sentinel()
                if read.observed and read.payload["released"]:
                    execution.bag_unreleased.discard("sentinel")
            execution.conclude(
                "M-ENG-1", assess_bag_persistence(write, read, channel=channel)
            )
        execution.finish("ENG")

    ids = ("ATOM-1",)
    if execution.begin(ids, "ATOM"):
        with execution.procedure(ids):
            execution.bag_unreleased.add("atom")
            # The second contender is queued only once the first receipt has
            # been interpreted. A dispatch whose acceptance is unknown is not
            # permission to add another contender to the same claim.
            receipts = [probes.queue_atomicity_contender("A")]
            if receipts[0].accepted:
                receipts.append(probes.queue_atomicity_contender("B"))
            execution.settle()
            collect = probes.collect_atomicity()
            if collect.observed and collect.payload["released"]:
                execution.bag_unreleased.discard("atom")
            execution.conclude(
                "ATOM-1", assess_atomicity(receipts, collect, channel=channel)
            )
        execution.finish("ATOM")

    ids = ("M-UNREG-1", "M-UNREG-2")
    # The fixture exists only for this procedure, so it is created only once
    # the procedure itself is admissible, fixture cost included.
    if execution.admissible(
        ids, "UNREG", extra_operations=execution.definition.fixture_operations
    ):
        if not _setup_fixtures(execution):
            execution.not_run(ids, "fixture_setup_failed")
            return
        if execution.announce(ids, "UNREG"):
            _run_unregister(execution, ids)
            execution.finish("UNREG")


def _run_unregister(execution: _Execution, ids: Sequence[str]) -> None:
    probes = execution.probes
    device = execution.definition.fixtures[0].name
    with execution.procedure(ids):
        execution.bag_unreleased.add("unreg")
        register = probes.register_observer_and_trigger(device)
        evidence = release = after = None
        if not register.observed:
            execution.observers_unresolved.add("cb1:registration_unknown")
        elif register.payload["registered1"]:
            execution.observers_unresolved.add("cb1")
            execution.settle()
            evidence = probes.read_observer_and_register_zero_event(device)
            if not evidence.observed:
                execution.observers_unresolved.add("cb2:registration_unknown")
            else:
                if evidence.payload["registered2"]:
                    execution.observers_unresolved.add("cb2")
                release = probes.release_observers_and_trigger(device)
                if not release.observed:
                    execution.observers_unresolved.add("cb3:registration_unknown")
                else:
                    if release.payload["registered3"]:
                        execution.observers_unresolved.add("cb3")
                    execution.settle()
                    after = probes.read_post_release_and_drop()
                    if after.observed and after.payload["dropped"]:
                        execution.bag_unreleased.discard("unreg")
        first, second = assess_observer_release(register, evidence, release, after)
        _observer_releases(execution, first, release, after)
        execution.conclude("M-UNREG-1", first)
        execution.conclude("M-UNREG-2", second)


def _observer_releases(
    execution: _Execution,
    first: Assessment,
    release: ProbeReading | None,
    after: ProbeReading | None,
) -> None:
    """Record observer outcomes; only a supported release resolves one."""
    releases = execution.record.releases
    if (
        first.facts.get("release_conclusion")
        == MeasurementConclusion.SUPPORTED_IN_SAMPLE
    ):
        execution.observers_unresolved.discard("cb1")
        releases.append(
            ReleaseRecord(
                resource="observer:cb1",
                kind="observer",
                outcome="released_in_sample",
                detail="no invocation after a control event",
            )
        )
    elif release is not None and release.observed:
        attempt = release.payload["release1"]
        releases.append(
            ReleaseRecord(
                resource="observer:cb1",
                kind="observer",
                outcome=(
                    "release_threw"
                    if attempt.get("threw")
                    else "release_attempted_unverified"
                    if attempt.get("attempted")
                    else "release_not_attempted"
                ),
            )
        )
    if after is not None and after.observed:
        for name, key in (("cb2", "release2"), ("cb3", "release3")):
            attempt = after.payload[key]
            releases.append(
                ReleaseRecord(
                    resource=f"observer:{name}",
                    kind="observer",
                    outcome=(
                        "release_threw"
                        if attempt.get("threw")
                        else "release_attempted_unverified"
                        if attempt.get("attempted")
                        else "inert_attached"
                    ),
                    detail="marked inert; detachment is not observed",
                )
            )


# -- Q1 ------------------------------------------------------------------------


def _run_q1(execution: _Execution) -> None:
    """Run the repaired Q1 scope: the page tables, then the listeners.

    M-DNS-3 is declared OMITTED, not scheduled. Its reader was measured by the
    Q1-file run at `0850de3`, nothing in this stage depends on that reading,
    and a second sample would be a second sample attributed to its own SHA --
    never additional support for the first one.
    """
    required = [item.id for item in execution.definition.experiments if item.required]
    if not execution.ledger.can_afford(
        execution.definition.fixture_operations
        + execution.definition.required_experiment_operations
    ):
        execution.not_run(required, "budget_insufficient_for:Q1")
        execution.stop("budget:Q1")
        return
    if not _setup_fixtures(execution) or not _configure_q1(execution):
        execution.not_run(required, "fixture_setup_failed")
        return
    ids = ("M-HTTPS-1",)
    if execution.begin(ids, "HTTPS1"):
        with execution.procedure(ids):
            execution.conclude("M-HTTPS-1", _page_tables(execution))
        execution.finish("HTTPS1")
    ids = ("M-HTTPS-2",)
    if execution.begin(ids, "HTTPS2"):
        with execution.procedure(ids):
            execution.conclude("M-HTTPS-2", _https_listener(execution))
        execution.finish("HTTPS2")


def _configure_q1(execution: _Execution) -> bool:
    """Address the endpoints through E5 and enable HTTP/HTTPS through E6."""
    ledger = execution.ledger
    fixtures = {item.name: item for item in execution.definition.fixtures}
    endpoints = [
        SetEndpointStaticAddress(
            id=f"q1-e5-{name}",
            phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
            device_id=name,
            device_name=name,
            site_id="q1",
            interface="FastEthernet0",
            ipv4=fixture.ipv4,
            netmask=fixture.netmask,
            gateway="",
            dns_server=fixture.dns_server or None,
            segment_id="q1",
        )
        for name, fixture in fixtures.items()
        if fixture.ipv4
    ]
    server = fixtures[Q1_SERVER]
    common = {
        "phase": ServicePhase.ENABLE,
        "host_device_id": server.name,
        "host_device_name": server.name,
        "host_model": server.model,
        "site_id": "q1",
        "required_capability": "qualification:Q1",
    }
    services = [
        EnableHttpService(
            id="q1-e6-http",
            service_id="q1-http",
            service_type=ServiceType.HTTP,
            **common,
        ),
        EnableHttpsService(
            id="q1-e6-https",
            service_id="q1-https",
            service_type=ServiceType.HTTPS,
            **common,
        ),
    ]
    try:
        with ledger.purpose_of("apply:e5_endpoints"):
            e5 = execution.run.boundaries.configuration_runtime(
                execution.bound
            ).apply_actions(endpoints)
    except OperationRefused as exc:
        execution.stop(f"operation_refused:{exc.reason}")
        return False
    # E5 is classified before the E6 batch is built. The enables used to be
    # dispatched first and the flag read afterwards, so a refusal could not
    # prevent the effects it was refusing.
    e5_error = _incomplete_batch(
        [item.id for item in endpoints], [item.action_id for item in e5]
    )
    execution.e5_accepted = (
        bool(endpoints) and not e5_error and all(item.applied for item in e5)
    )
    execution.record.limitations.append(
        "e5_endpoint_dispatch:"
        + ("accepted" if execution.e5_accepted else e5_error or "unknown")
    )
    if not execution.e5_accepted:
        execution.stop(f"outcome_unknown:e5_endpoints{e5_error and ':' + e5_error}")
        return False
    try:
        with ledger.purpose_of("apply:e6_enable_http_https"):
            e6 = execution.run.boundaries.service_runtime(
                execution.bound
            ).apply_actions(services)
    except OperationRefused as exc:
        execution.stop(f"operation_refused:{exc.reason}")
        return False
    e6_error = _incomplete_batch(
        [item.id for item in services], [item.action_id for item in e6]
    )
    enabled = not e6_error and all(
        item.applied and item.postcondition is PostconditionFact.SATISFIED
        for item in e6
    )
    if not enabled:
        execution.stop(f"fixture_services_not_enabled{e6_error and ':' + e6_error}")
        return False
    return execution.run.transition("fixtures:configured")


@dataclass(frozen=True)
class _Readiness:
    """What the bounded readiness gate observed before a network attempt."""

    ready: bool
    reads: int
    elapsed_seconds: float
    reason: str
    first: dict[str, Any] = field(default_factory=dict)
    last: dict[str, Any] = field(default_factory=dict)

    def facts(self) -> dict[str, Any]:
        """Return the record shape: the bounds, the reason and both samples."""
        return {
            "ready": self.ready,
            "reads": self.reads,
            "max_reads": READINESS_MAX_READS,
            "deadline_seconds": READINESS_DEADLINE_SECONDS,
            "elapsed_seconds": self.elapsed_seconds,
            "reason": self.reason,
            "first": self.first,
            "last": self.last,
        }


def _await_readiness(
    execution: _Execution,
    endpoints: Sequence[tuple[str, str]],
    read: Callable[[float], ProbeReading],
    *,
    purpose: str,
) -> _Readiness:
    """Read the exact fixture endpoints until one complete sample is ready.

    The gate is a precondition, not a retry budget: at most
    `READINESS_MAX_READS` aggregate reads inside a
    `READINESS_DEADLINE_SECONDS` monotonic window, itself capped by whatever
    the stage still has outside its finalization reserve, and the first
    complete ready sample ends it. Between two reads it waits only while it is
    still allowed to read again, so nothing sleeps unconditionally and nothing
    spins. A gate that never becomes ready is a readiness result: no client is
    created and no acquisition is requested from it.
    """
    ledger = execution.ledger
    started = ledger.elapsed()
    deadline = started + READINESS_DEADLINE_SECONDS
    first: dict[str, Any] = {}
    last: dict[str, Any] = {}
    reads = 0
    reason = "readiness_not_attempted"
    while reads < READINESS_MAX_READS:
        if execution.stopped:
            reason = f"stopped:{execution.record.primary_failure}"
            break
        if not ledger.can_afford(1):
            reason = "readiness_budget_exhausted"
            break
        if ledger.elapsed() >= deadline:
            reason = "readiness_deadline_reached"
            break
        local_remaining = max(0.0, deadline - ledger.elapsed())
        _operations, stage_remaining = ledger.allowance()
        timeout = min(local_remaining, max(0.0, stage_remaining))
        if timeout <= 0:
            reason = "readiness_budget_exhausted"
            break
        with ledger.purpose_of(purpose):
            sample = assess_port_readiness(read(timeout), endpoints)
        reads += 1
        last = dict(sample.facts)
        if reads == 1:
            first = dict(sample.facts)
        if ledger.elapsed() > deadline:
            reason = "readiness_deadline_reached_after_read"
            break
        if sample.ready:
            reason = ""
            break
        reason = sample.cause
        remaining = deadline - ledger.elapsed()
        if reads < READINESS_MAX_READS and remaining > 0:
            ledger.wait(
                min(execution.run.boundaries.settle_seconds, remaining),
                execution.run.boundaries.sleep,
            )
    return _Readiness(
        not reason and reads > 0,
        reads,
        round(ledger.elapsed() - started, 3),
        reason,
        first,
        last,
    )


def _incomplete_batch(requested: Sequence[str], reported: Sequence[str]) -> str:
    """Name why a runtime batch cannot be read as complete, or return `""`.

    A short result set is an unknown outcome, not a success for the rows that
    did come back: `all()` over two rows says nothing about a third action
    nobody reported on.
    """
    if len(reported) != len(requested) or sorted(reported) != sorted(requested):
        return f"incomplete_result_set:{len(reported)}_of_{len(requested)}"
    return ""


def _fetch(
    execution: _Execution, label: str, scheme: str, marker: str
) -> RuntimeServiceVerification | None:
    """One production fetch, started only when its whole lifecycle fits.

    Four operations: the start, at most two inspections (the production
    runtime polls with an interval equal to its timeout) and the release of
    the owned client, which must never be the call the budget refuses.
    """
    if execution.stopped:
        return None
    if not execution.ledger.can_afford(FETCH_OPERATIONS):
        execution.stop(f"budget:fetch:{label}")
        return None
    expectation = ServiceVerificationExpectation(
        id=f"q1-{label}",
        service_id=f"q1-{scheme}",
        action_id="q1-fixture",
        kind=(
            ServiceVerificationKind.HTTPS_FETCH
            if scheme == "https"
            else ServiceVerificationKind.HTTP_FETCH
        ),
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id=Q1_SERVER,
        host_device_name=Q1_SERVER,
        client_device_id=Q1_PC1,
        client_device_name=Q1_PC1,
        expected={"scheme": scheme, "address": Q1_SERVER_IPV4, "marker": marker},
        host_model="Server-PT",
        client_model="PC-PT",
    )
    with execution.ledger.purpose_of(f"fetch:{label}"):
        row = execution.run.boundaries.service_runtime(execution.bound).verify(
            expectation
        )
    released = str(row.observed.get("released", ""))
    execution.record.releases.append(
        ReleaseRecord(
            resource=f"client:{label}",
            kind="client",
            outcome=released or "unknown",
            detail="; ".join(row.limitations)[:MAX_DETAIL],
        )
    )
    if released not in ("released", "nothing_owned"):
        execution.record.engine_residue.append(
            f"client:{label}:{released or 'unknown'}"
        )
        # An owned client whose release nobody observed is an effect with an
        # unknown outcome. It authorizes no further experimental mutation.
        execution.stop(f"outcome_unknown:fetch_client:{label}")
    return row


def _page_tables(execution: _Execution) -> Assessment:
    """Write the existing index page through each handle, reading between.

    Four evaluations, each admitted only after the previous one was
    interpreted: write H through `HttpServer` (bracketed by a complete read of
    both handles), an independent read of both, write S through
    `HttpsServer` (bracketed again), and a final independent read. Nothing is
    written under a new page name, and a step that could not be read stops
    the procedure rather than guessing.
    """
    probes = execution.probes
    texts = probes.page_marker_texts()
    write_http = probes.write_index_marker(Q1_SERVER, "http")
    read_http = write_https = read_https = None
    if page_write_established(write_http):
        read_http = probes.read_index_cells(Q1_SERVER)
    if page_read_admits_second_write(read_http, texts["http_marker"]):
        write_https = probes.write_index_marker(Q1_SERVER, "https")
    if page_write_established(write_https):
        read_https = probes.read_index_cells(Q1_SERVER)
    return assess_page_tables(
        write_http,
        read_http,
        write_https,
        read_https,
        http_marker=texts["http_marker"],
        https_marker=texts["https_marker"],
    )


def _fixture_endpoints(execution: _Execution) -> tuple[tuple[str, str], ...]:
    """Return both ends of every fixture link, in declaration order."""
    return tuple(
        endpoint
        for link in execution.definition.links
        for endpoint in ((link.device_a, link.port_a), (link.device_b, link.port_b))
    )


def _https_listener(execution: _Execution) -> Assessment:
    """Run the listener procedure, admitting each effect only after the last one.

    Nothing reaches the network before the bounded readiness gate reports one
    fresh complete sample in which every fixture link is up. A gate that never
    becomes ready leaves the marked page unwritten and every fetch unstarted:
    that is a readiness result about the measured links, never evidence that
    HTTP or HTTPS is broken.

    A same-mode working positive then comes before every negative: an
    HTTP-mode fetch with both listeners enabled, then HTTP off and an
    HTTPS-mode fetch. A negative whose positive did not retrieve the marker is
    not run, because it could not discriminate anything; a failed positive
    instead spends one read of listener and endpoint readiness, so the record
    says what the fixture looked like when it failed. No wait, timeout or
    status-code meaning is added to force a positive, and a started fetch is
    never retried inside this experiment.
    """
    probes = execution.probes
    marker = f"MCPQ-{execution.nonce[:16]}-INDEX"
    endpoints = _fixture_endpoints(execution)
    urls = {scheme: f"{scheme}://{Q1_SERVER_IPV4}/" for scheme in ("http", "https")}
    gate = _await_readiness(
        execution,
        endpoints,
        lambda timeout: probes.read_listener_readiness(Q1_SERVER, endpoints, timeout),
        purpose="readiness:q1_fixture_links",
    )
    steps: dict[str, Any] = {
        "readiness": gate.facts(),
        "marker_page": None,
        "http_positive": None,
        "http_off": None,
        "https_positive": None,
        "http_negative": None,
        "https_off": None,
        "https_negative": None,
    }

    def assessed(readiness_after: Mapping[str, Any] | None = None) -> Assessment:
        return assess_https_listener(
            **steps, request_urls=urls, readiness_after=readiness_after
        )

    def failed_positive() -> Assessment:
        if execution.stopped or not execution.ledger.can_afford(1):
            return assessed()
        with execution.ledger.purpose_of("readiness:q1_after_failed_positive"):
            reading = probes.read_listener_readiness(Q1_SERVER, endpoints)
        return assessed(dict(assess_port_readiness(reading, endpoints).facts))

    if execution.stopped or not gate.ready:
        return assessed()
    steps["marker_page"] = probes.prepare_marker_page(Q1_SERVER, marker)
    if not marker_page_established(steps["marker_page"]):
        return assessed()
    steps["http_positive"] = _fetch(execution, "http-positive", "http", marker)
    current = assessed()
    if execution.stopped or current.conclusion is MeasurementConclusion.CONTRADICTED:
        return current
    if current.facts["positive_http_mode_both_enabled"]["fetch"] != "marker_retrieved":
        return failed_positive()
    steps["http_off"] = probes.disable_http(Q1_SERVER)
    if not listener_toggle_established(steps["http_off"], http=False, https=True):
        return assessed()
    steps["https_positive"] = _fetch(execution, "https-positive", "https", marker)
    current = assessed()
    if execution.stopped or current.conclusion is MeasurementConclusion.CONTRADICTED:
        return current
    https_worked = current.facts["positive_https_only"]["fetch"] == "marker_retrieved"
    steps["http_negative"] = _fetch(execution, "http-negative", "http", marker)
    current = assessed()
    if execution.stopped or current.conclusion is MeasurementConclusion.CONTRADICTED:
        return current
    if not https_worked:
        return failed_positive()
    if not execution.ledger.can_afford(1 + FETCH_OPERATIONS):
        execution.stop("budget:https_negative")
        return assessed()
    steps["https_off"] = probes.disable_https(Q1_SERVER)
    if listener_toggle_established(steps["https_off"], http=False, https=False):
        steps["https_negative"] = _fetch(execution, "https-negative", "https", marker)
    return assessed()


# -- Q3 ------------------------------------------------------------------------


def _q3_client_rows(reading: ProbeReading | None) -> list[dict[str, Any]] | None:
    """Return the exact two bounded client rows, or None when shape is unusable."""
    if reading is None or not reading.observed:
        return None
    rows = reading.payload.get("clients")
    if not isinstance(rows, list) or len(rows) != 2:
        return None
    expected = {(Q3_PC1, "FastEthernet0"), (Q3_PC2, "FastEthernet0")}
    observed: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        required = {
            "device": str,
            "interface": str,
            "found": bool,
            "port_found": bool,
            "mode_type": str,
            "mac": str,
            "ipv4": str,
            "netmask": str,
            "lease_time": str,
            "error": str,
        }
        if any(
            key not in row or not isinstance(row[key], kind)
            for key, kind in required.items()
        ):
            return None
        if row.get("mode") is not None and not isinstance(row.get("mode"), bool):
            return None
        observed.add((row["device"], row["interface"]))
    return rows if observed == expected else None


def _q3_client_assessments(
    before: ProbeReading | None, after: ProbeReading | None
) -> tuple[Assessment, Assessment]:
    """Judge native MAC and DHCP-mode readers without assigning semantics."""
    before_rows = _q3_client_rows(before)
    after_rows = _q3_client_rows(after)
    facts = {
        "before": before_rows or [],
        "after": after_rows or [],
    }
    if before_rows is None or after_rows is None:
        causes = [
            value
            for value in (
                _bounded(before.cause)
                if before is not None and not before.observed
                else "",
                _bounded(after.cause)
                if after is not None and not after.observed
                else "",
                "dhcp_client_rows_malformed"
                if before_rows is None or after_rows is None
                else "",
            )
            if value
        ]
        inconclusive = Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=causes,
            limitations=["exact_client_reader_sample_not_completed"],
        )
        return inconclusive, inconclusive
    mac_ok = all(
        row["found"]
        and row["port_found"]
        and not row["error"]
        and bool(row["mac"])
        and len(row["mac"]) <= 64
        for row in [*before_rows, *after_rows]
    )
    mode_ok = all(
        row["found"]
        and row["port_found"]
        and not row["error"]
        and row["mode_type"] == "boolean"
        and isinstance(row["mode"], bool)
        for row in [*before_rows, *after_rows]
    )
    mac = Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if mac_ok
        else MeasurementConclusion.CONTRADICTED,
        facts=facts,
        causes=[] if mac_ok else ["native_mac_reader_invalid"],
        limitations=[
            "native_mac_representation_sample_only",
            "no_equivalence_inferred",
        ],
    )
    mode = Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if mode_ok
        else MeasurementConclusion.CONTRADICTED,
        facts=facts,
        causes=[] if mode_ok else ["native_dhcp_mode_not_boolean"],
        limitations=["native_mode_reader_sample_only"],
    )
    return mac, mode


def _snapshot_facts(entry: DefaultPoolObservation) -> dict[str, Any]:
    """Return one persisted default reading exactly as it was recorded."""
    return {
        "label": entry.label,
        "purpose": entry.purpose,
        "operation_seq": entry.operation_seq,
        "observed": entry.observed,
        "cause": entry.cause,
        "pools": [dict(item) for item in entry.pools],
        "intended_pool_present": entry.intended_pool_present,
        "raw": dict(entry.raw),
        "differences": list(entry.differences),
    }


def _native_default_facts(execution: _Execution) -> dict[str, Any]:
    """Return every default reading the record holds and their differences."""
    return {
        "snapshots": [
            _snapshot_facts(item) for item in execution.record.native_default_pool
        ],
        "differences": execution.default_pool_differences,
    }


def _q3_default_purpose(label: str) -> str:
    """Return the ledger purpose one default reading is dispatched under."""
    return f"{Q3_DEFAULT_PURPOSE}:{label}"


def _counted_seq(ledger: OperationLedger, start: int) -> int:
    """Return the sequence of the last call counted since `start`, or 0.

    A refused call carries sequence 0, so a window that only refused reports
    no association rather than borrowing the previous call's number.
    """
    counted = [item.seq for item in ledger.entries[start:] if item.seq]
    return counted[-1] if counted else 0


def _restore_snapshot(entry: DefaultPoolObservation) -> DefaultPoolSnapshot:
    """Return the domain snapshot one persisted reading stands for."""
    return DefaultPoolSnapshot(
        entry.label,
        entry.observed,
        entry.cause,
        tuple(dict(item) for item in entry.pools),
        entry.intended_pool_present,
        dict(entry.raw),
    )


def _q3_default_persist(
    execution: _Execution,
    purpose: str,
    operation_seq: int,
    snapshot: DefaultPoolSnapshot,
) -> DefaultPoolSnapshot:
    """Write one default reading to the record's sink and persist it there.

    The sink is the record itself, so a reading taken after the last
    conclusion, after a stop or during finalization is durable evidence of the
    run rather than a value that disappears with the procedure that took it.
    The write uses the existing step machinery: a failed advance keeps the
    first primary failure, records its own error and closes further effects.
    """
    record = execution.record
    first = record.native_default_pool[0] if record.native_default_pool else None
    differences = (
        default_pool_differences(_restore_snapshot(first), snapshot)
        if first is not None
        else ()
    )
    record.native_default_pool.append(
        DefaultPoolObservation(
            label=snapshot.label,
            purpose=purpose,
            operation_seq=operation_seq,
            observed=snapshot.observed,
            cause=snapshot.cause,
            pools=[dict(item) for item in snapshot.pools],
            intended_pool_present=snapshot.intended_present,
            raw=dict(snapshot.raw),
            differences=list(differences),
        )
    )
    if not snapshot.observed and execution.stopped:
        # The run already has its cause. An unobserved later reading is one
        # more fact about it, never a replacement for it.
        record.secondary_failures.append(
            f"native_default:{snapshot.label}:{snapshot.cause}"
        )
    execution.run.transition(f"native_default:{snapshot.label}")
    return snapshot


def _q3_default_observed(
    execution: _Execution,
    label: str,
    reading: ProbeReading | None,
    *,
    operation_seq: int,
) -> DefaultPoolSnapshot:
    """Classify and persist one default reading this run already performed."""
    return _q3_default_persist(
        execution,
        _q3_default_purpose(label),
        operation_seq,
        default_pool_snapshot(
            label,
            reading,
            intended_pool=Q3_POOL,
            server=Q3_SERVER,
            interface="FastEthernet0",
        ),
    )


def _q3_default_read(execution: _Execution, label: str) -> DefaultPoolSnapshot:
    """Dispatch one bounded default reading under its own purpose and persist it.

    The purpose is set before the call, so the counted operation states what it
    was for instead of being identified afterwards from its ordinal. A reading
    the remaining allowance cannot pay for, and one the ledger refuses, are
    explicitly not observed: no operation is added to the stage to repair the
    record, and the budgets are the ones the stage already planned.
    """
    purpose = _q3_default_purpose(label)
    ledger = execution.ledger
    start = len(ledger.entries)
    if not ledger.can_afford(1):
        return _q3_default_persist(
            execution,
            purpose,
            0,
            DefaultPoolSnapshot(label, False, "default_pool_snapshot_not_affordable"),
        )
    try:
        with ledger.purpose_of(purpose):
            reading = execution.probes.read_dhcp_server_baseline(
                Q3_SERVER, "FastEthernet0"
            )
    except OperationRefused as exc:
        return _q3_default_persist(
            execution,
            purpose,
            0,
            DefaultPoolSnapshot(
                label, False, f"default_pool_snapshot_refused:{exc.reason}"
            ),
        )
    return _q3_default_observed(
        execution, label, reading, operation_seq=_counted_seq(ledger, start)
    )


def _q3_e5_foundation_cause(
    configuration: ConfigurationApplicationResult,
    foundations: Mapping[str, ActionExecutionStatus],
    expected_action_ids: set[str],
) -> str:
    """Return why E5 cannot found an E6 mutation, or "" when it can.

    The classification reuses the applicator's own decided facts. A short
    result set, an unknown dispatch, an unobserved result, an unsatisfied
    postcondition, a contradicted read-back or a foundational status that is
    not VERIFIED all mean the same thing here: the next effect has no
    permission, and none of them is a reason to dispatch it and look later.
    """
    reported = [item.action_id for item in configuration.action_results]
    if (
        len(reported) != len(expected_action_ids)
        or set(reported) != expected_action_ids
        or len(reported) != len(set(reported))
    ):
        return "outcome_unknown:q3_e5_incomplete_result_set"
    for item in sorted(configuration.action_results, key=lambda row: row.action_id):
        snapshot = item.received_mutation
        if snapshot is not None:
            decision = decide_mutation(snapshot)
            if not (
                item.status is decision.status
                and item.failure_code is decision.failure_code
                and item.disposition is decision.disposition
                and item.cause == decision.cause
            ):
                return f"outcome_unknown:q3_e5_endpoints:{item.action_id}"
        if (
            item.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
            or item.result is ResultFact.NOT_OBSERVED
            or item.status is ActionExecutionStatus.UNKNOWN
            or (snapshot is not None and bool(snapshot.call_error))
        ):
            return f"outcome_unknown:q3_e5_endpoints:{item.action_id}"
        if item.postcondition is PostconditionFact.UNSATISFIED:
            return f"contradiction:q3_e5_endpoints:{item.action_id}"
    # E5 read-backs carry a lifecycle status, not an observation fact:
    # FAILED is the re-read that did not match what the action intended.
    contradicted = sorted(
        item.expectation_id
        for item in configuration.verification_results
        if item.status is ActionExecutionStatus.FAILED
    )
    if contradicted:
        return f"contradiction:q3_e5_verification:{contradicted[0]}"
    if not foundations or any(
        item is not ActionExecutionStatus.VERIFIED for item in foundations.values()
    ):
        return "q3_foundations_not_established"
    return ""


def _q3_service_result_cause(
    result: ServiceApplicationResult,
    expected_action_ids: set[str],
    *,
    expected_verification_ids: set[str] | None = None,
    recovered_action_ids: set[str] | None = None,
) -> str:
    """Return why the product result forbids another mutation, or "".

    The exact row identities and the canonical decision retained on every
    mutation are the authority. A later fresh verification may settle a
    correlated execute-once action, but it cannot repair a lost acknowledgement
    or an incoherent result set.
    """
    action_ids = [item.action_id for item in result.action_results]
    if len(action_ids) != len(expected_action_ids) or set(action_ids) != set(
        expected_action_ids
    ):
        return "outcome_unknown:q3_product_incomplete_result_set"
    if len(action_ids) != len(set(action_ids)):
        return "outcome_unknown:q3_product_incomplete_result_set"
    if expected_verification_ids is not None:
        verification_ids = [item.expectation_id for item in result.verification_results]
        if (
            len(verification_ids) != len(expected_verification_ids)
            or set(verification_ids) != expected_verification_ids
            or len(verification_ids) != len(set(verification_ids))
        ):
            return "outcome_unknown:q3_product_incomplete_verification_set"
    if any(
        item.observation is ObservationFact.CONTRADICTED
        for item in result.verification_results
    ):
        return "contradiction:q3_product_readback"
    if any(
        item.observation is ObservationFact.ENGINE_ERROR
        or item.cause.startswith("exception:")
        for item in result.verification_results
    ):
        return "outcome_unknown:q3_product_verification"
    recovered = recovered_action_ids or set()
    for row in result.action_results:
        snapshot = row.received_mutation
        if snapshot is None or snapshot.action_id != row.action_id:
            return "outcome_unknown:q3_product_service"
        decision = decide_mutation(snapshot)
        if not (
            row.status is decision.status
            and row.failure_code is decision.failure_code
            and row.disposition is decision.disposition
            and row.dispatch is snapshot.dispatch
            and row.result is snapshot.result
            and row.postcondition is snapshot.postcondition
            and row.transition is snapshot.transition
            and row.footprint is snapshot.footprint
            and row.attempted is snapshot.attempted
            and row.residual_change is (decision.residue is MutationResidue.CHANGED)
            and row.cause == decision.cause
        ):
            return "outcome_unknown:q3_product_service"
        if (
            row.dispatch is not DispatchFact.ACCEPTED
            or row.result is ResultFact.NOT_OBSERVED
            or row.attempted is None
            or bool(snapshot.call_error)
            or (not decision.frontier and row.action_id not in recovered)
        ):
            return "outcome_unknown:q3_product_service"
    return ""


def _q3_setup_assessment(
    baseline: ProbeReading,
    admission: BaselineAdmission,
    configuration: ConfigurationApplicationResult | None,
    foundations: Mapping[str, ActionExecutionStatus],
    server_mutations: Sequence[RuntimeActionMutation],
    server_readback: RuntimeServiceVerification | None,
    contract: Q3ProductContract,
    native_default: Mapping[str, Any],
    readiness: Mapping[str, Any],
    setup_cause: str,
) -> Assessment:
    """Judge the product configuration path without promoting native support."""
    mutation_facts = [
        {
            "action_id": item.action_id,
            "dispatch": item.dispatch.value,
            "result": item.result.value,
            "postcondition": item.postcondition.value,
            "attempted": item.attempted,
        }
        for item in server_mutations
    ]
    facts = {
        "initial_server": dict(baseline.payload) if baseline.observed else {},
        "baseline_admission": {
            "admitted": admission.admitted,
            "kind": admission.kind,
            "causes": list(admission.causes),
        },
        "native_default": dict(native_default),
        "readiness": dict(readiness),
        "configuration_plan": configuration.config_plan_id if configuration else "",
        "configuration_hash": (
            configuration.config_semantic_hash if configuration else ""
        ),
        "service_plan": contract.service_plan.id,
        "service_hash": contract.service_plan.semantic_hash,
        "foundation_statuses": {
            key: value.value for key, value in sorted(foundations.items())
        },
        "setup_cause": setup_cause,
        "server_mutations": mutation_facts,
        "server_readback": (
            {
                "status": server_readback.status.value,
                "observation": server_readback.observation.value,
                "cause": server_readback.cause,
            }
            if server_readback is not None
            else {}
        ),
    }
    expected_actions = {
        item.id
        for item in contract.service_plan.actions
        if isinstance(item, EnableServerDhcp | ConfigureServerDhcpPool)
    }
    complete_mutations = {
        item.action_id for item in server_mutations
    } == expected_actions and all(
        item.dispatch is DispatchFact.ACCEPTED
        and item.result is ResultFact.CORRELATED
        and item.postcondition is PostconditionFact.SATISFIED
        for item in server_mutations
    )
    foundations_ready = bool(foundations) and all(
        item is ActionExecutionStatus.VERIFIED for item in foundations.values()
    )
    readback_ready = (
        server_readback is not None
        and server_readback.status is ActionExecutionStatus.VERIFIED
        and server_readback.observation is ObservationFact.OBSERVED
    )
    unknown_effect = setup_cause.startswith("outcome_unknown:") or any(
        item.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
        or item.result is ResultFact.NOT_OBSERVED
        for item in server_mutations
    )
    limitations = [
        "stored_configuration_sample_only",
        "serving_behavior_not_inferred",
        f"initial_pool_inventory:{admission.kind}",
    ]
    if admission.kind == BASELINE_OBSERVED_NATIVE_DEFAULT:
        # What the run can state is what it did, not what Packet Tracer did:
        # no explicit setter of this run targeted the native default. Whether
        # its values moved is a separate observation, and the readings above
        # are where a reviewer finds the answer.
        limitations.append("no_explicit_setter_targeted_the_native_default")
        limitations.append("process_enable_is_process_wide_not_pool_scoped")
    if not setup_cause and complete_mutations and foundations_ready and readback_ready:
        return Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE,
            facts=facts,
            limitations=limitations,
        )
    contradicted = (
        setup_cause.startswith("contradiction:")
        or (
            server_readback is not None
            and server_readback.observation is ObservationFact.CONTRADICTED
        )
        or any(
            item.postcondition is PostconditionFact.UNSATISFIED
            for item in server_mutations
        )
    )
    return Assessment(
        MeasurementConclusion.CONTRADICTED
        if contradicted
        else MeasurementConclusion.INCONCLUSIVE,
        facts=facts,
        causes=[
            value
            for value in (setup_cause, "q3_product_configuration_not_established")
            if value
        ],
        limitations=[*limitations, "no_serving_claim"],
        outcome_unknown=unknown_effect,
    )


def _q3_table_assessment(
    empty: ProbeReading | None, full: ProbeReading | None
) -> Assessment:
    facts = {
        "empty": dict(empty.payload) if empty is not None and empty.observed else {},
        "capacity_one": (
            dict(full.payload) if full is not None and full.observed else {}
        ),
    }
    if empty is None or full is None or not empty.observed or not full.observed:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["bounded_lease_table_sample_unobserved"],
            limitations=["no_absence_or_completion_claim"],
        )
    empty_rows = empty.payload.get("rows")
    full_rows = full.payload.get("rows")
    coherent = (
        empty.payload.get("pool_name") == Q3_POOL
        and full.payload.get("pool_name") == Q3_POOL
        and isinstance(empty_rows, list)
        and isinstance(full_rows, list)
        and len(empty_rows) == 0
        and any(
            isinstance(row, dict) and row.get("ipAddress") == Q3_LEASE_IPV4
            for row in full_rows
        )
    )
    return Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if coherent
        else MeasurementConclusion.INCONCLUSIVE,
        facts=facts,
        causes=[] if coherent else ["empty_or_capacity_one_sample_not_discriminating"],
        limitations=[
            "bounded_sample:empty_and_capacity_one",
            "termination_behavior_not_generalized",
            "no_pool_exhaustion_claim",
        ],
    )


def _q3_timing_assessment(
    before_one: ProbeReading | None,
    before_two: ProbeReading | None,
    after_one: ProbeReading | None,
    after_two: ProbeReading | None,
    service_result: ServiceApplicationResult | None,
    guard: RuntimeActionMutation | None,
    guard_not_run: str,
    readiness: Mapping[str, Any],
    native_default: Mapping[str, Any],
) -> Assessment:
    readings = (before_one, before_two, after_one, after_two)
    rows = [_q3_client_rows(item) for item in readings]
    facts = {
        "before_1": rows[0] or [],
        "before_2": rows[1] or [],
        "after_1": rows[2] or [],
        "after_2": rows[3] or [],
        "readiness": dict(readiness),
        "native_default": dict(native_default),
        "guard_not_run": guard_not_run,
        "service_status": service_result.status.value if service_result else "absent",
        "service_actions": (
            [
                {
                    "action_id": item.action_id,
                    "status": item.status.value,
                    "dispatch": item.dispatch.value,
                    "result": item.result.value,
                    "postcondition": item.postcondition.value,
                    "attempted": item.attempted,
                    "cause": item.cause,
                }
                for item in service_result.action_results
            ]
            if service_result is not None
            else []
        ),
        "guard": (
            {
                "attempted": guard.attempted,
                "cause": guard.cause,
                "dispatch": guard.dispatch.value,
            }
            if guard is not None
            else {}
        ),
    }
    guard_refused = (
        guard is not None
        and guard.attempted is not True
        and guard.cause == "own_claim_replayed"
    )
    product_contradictions = (
        [
            item.expectation_id
            for item in service_result.verification_results
            if item.observation is ObservationFact.CONTRADICTED
        ]
        if service_result is not None
        else []
    )
    facts["product_contradictions"] = product_contradictions
    product_outcome_unknown = bool(
        service_result
        and (
            guard_not_run.startswith("outcome_unknown:")
            or any(
                item.dispatch is DispatchFact.ACCEPTANCE_UNKNOWN
                or item.result is ResultFact.NOT_OBSERVED
                or (
                    item.received_mutation is not None
                    and bool(item.received_mutation.call_error)
                )
                for item in service_result.action_results
                if item.attempted is True
            )
        )
    )
    facts["product_outcome_unknown"] = product_outcome_unknown
    if product_contradictions:
        return Assessment(
            MeasurementConclusion.CONTRADICTED,
            facts=facts,
            causes=["product_dhcp_readback_contradicted"],
            limitations=["contradiction_preserved_from_real_product_runtime"],
        )
    if product_outcome_unknown:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["product_dhcp_effect_outcome_unknown"],
            limitations=["no_guard_or_later_mutation_authorized"],
            outcome_unknown=True,
        )
    if guard_not_run:
        # No acquisition was requested at all, so there is nothing to time and
        # nothing to replay. This states what the fixture allowed, never that
        # DHCP acquisition failed.
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=[f"acquisition_not_requested:{guard_not_run}"],
            limitations=[
                "no_client_activated",
                "readiness_result_is_not_an_acquisition_verdict",
            ],
        )
    if not guard_refused:
        return Assessment(
            MeasurementConclusion.CONTRADICTED,
            facts=facts,
            causes=["same_action_guard_control_dispatched_or_unreadable"],
            outcome_unknown=guard is None or guard.attempted is None,
        )
    if any(item is None for item in rows):
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=["lease_time_window_unobserved"],
            limitations=["lease_time_semantics_unqualified"],
        )
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE,
        facts=facts,
        causes=["automatic_renewal_not_discriminated_in_fixed_window"],
        limitations=[
            "lease_time_semantics_unqualified",
            "no_clock_or_lease_manipulation",
            "same_action_guard_refused_without_redispatch",
        ],
    )


def _run_q3(execution: _Execution) -> None:
    """Run the exact Q3 setup, product path and bounded native measurements."""
    required = [item.id for item in execution.definition.experiments if item.required]
    if not execution.ledger.can_afford(
        execution.definition.fixture_operations
        + execution.definition.required_experiment_operations
    ):
        execution.not_run(required, "budget_insufficient_for:Q3")
        execution.stop("budget:Q3")
        return
    if not _setup_fixtures(execution):
        execution.not_run(required, "fixture_setup_failed")
        return
    contract = execution.product_contract
    if contract is None:
        execution.not_run(required, "q3_product_contract_absent")
        execution.stop("q3_product_contract_absent")
        return
    configuration_runtime = _Q3ConfigurationRuntime(
        execution.run.boundaries.configuration_runtime(execution.bound),
        contract.inventory,
    )
    service_runtime = _Q3ServiceRuntime(
        execution.run.boundaries.service_runtime(execution.bound),
        contract.inventory,
    )
    endpoint_plan = _q3_endpoint_plan(contract)
    execution.record.limitations.extend(
        [
            "q3_private_candidate_capabilities:no_public_catalog_mutation",
            "q3_endpoint_projection:physical_fixture_dependencies_owned_by_runner",
        ]
    )
    foundation_plan = contract.service_plan.model_copy(
        update={
            "source_configuration_id": endpoint_plan.id,
            "source_configuration_hash": endpoint_plan.semantic_hash,
        },
        deep=True,
    )
    context = _q3_context(contract)
    clients = ((Q3_PC1, "FastEthernet0"), (Q3_PC2, "FastEthernet0"))
    gate = _Readiness(False, 0, 0.0, "readiness_not_attempted")
    server_application: ServiceApplicationResult | None = None

    setup_ids = ("M-DHCP-1", "M-DHCP-4", "M-DHCP-5")
    if not execution.begin(setup_ids, "Q3_SETUP"):
        return
    foundations: dict[str, ActionExecutionStatus] = {}
    with execution.procedure(setup_ids):
        # One read serves both the typed baseline admission and the run's first
        # default reading, so the first snapshot costs the stage nothing extra.
        baseline_start = len(execution.ledger.entries)
        with execution.ledger.purpose_of(_q3_default_purpose("before_e5")):
            baseline = execution.probes.read_dhcp_server_baseline(
                Q3_SERVER, "FastEthernet0"
            )
        admission = assess_dhcp_baseline_admission(
            baseline,
            server=Q3_SERVER,
            interface="FastEthernet0",
            intended_pool=Q3_POOL,
            observed_build=execution.record.environment.observed_build,
            qualified_build=execution.run.boundaries.q3_required_build,
            observed_channel=execution.channel,
            qualified_channels=execution.definition.allowed_channels,
        )
        _q3_default_observed(
            execution,
            "before_e5",
            baseline,
            operation_seq=_counted_seq(execution.ledger, baseline_start),
        )
        clients_before = execution.probes.read_dhcp_clients(clients)
        if not admission.admitted:
            mac, mode = _q3_client_assessments(clients_before, clients_before)
            execution.conclude(
                "M-DHCP-1",
                Assessment(
                    MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "initial_server": (
                            dict(baseline.payload) if baseline.observed else {}
                        ),
                        "baseline_admission": {
                            "admitted": False,
                            "kind": admission.kind,
                            "causes": list(admission.causes),
                        },
                        "native_default": _native_default_facts(execution),
                    },
                    causes=[
                        "initial_dhcp_server_state_not_admissible",
                        *admission.causes,
                    ],
                    limitations=[
                        "no_setter_dispatched",
                        "observed_state_preserved_untouched",
                    ],
                ),
            )
            execution.conclude("M-DHCP-4", mac)
            execution.conclude("M-DHCP-5", mode)
            execution.stop("q3_initial_server_state_not_admissible")
        else:
            configuration = None
            server_mutations: list[RuntimeActionMutation] = []
            server_readback: RuntimeServiceVerification | None = None
            setup_cause = ""
            endpoints = _fixture_endpoints(execution)
            gate = _await_readiness(
                execution,
                endpoints,
                lambda timeout: execution.probes.read_port_readiness(
                    endpoints, timeout
                ),
                purpose="readiness:q3_fixture_links",
            )
            if not gate.ready:
                setup_cause = f"readiness_not_established:{gate.reason}"
            if gate.ready and not execution.run.transition(
                "experiment:Q3_SETUP:e5_started"
            ):
                execution.stop("persistence:q3_e5_not_announced")
            if gate.ready and not execution.stopped:
                with execution.ledger.purpose_of("q3:product:e5_endpoints"):
                    configuration = ConfigurationApplicator(
                        configuration_runtime
                    ).apply(
                        endpoint_plan,
                        actual_source_topology_hash=(
                            contract.manifest.physical_topology_hash
                        ),
                        capabilities=contract.device_capabilities,
                        runtime_context=context,
                        deployment_manifest=contract.manifest,
                    )
                foundations = derive_service_foundational_statuses(
                    foundation_plan, configuration
                )
                # The E5 result and the foundations it produced decide whether
                # any E6 server mutation is admissible. They used to be judged
                # only after the mutation had already been dispatched.
                setup_cause = _q3_e5_foundation_cause(
                    configuration,
                    foundations,
                    {item.id for item in endpoint_plan.actions},
                )
                if setup_cause:
                    execution.stop(setup_cause)
            if (
                gate.ready
                and not execution.stopped
                and not execution.run.transition("experiment:Q3_SETUP:e6_started")
            ):
                execution.stop("persistence:q3_e6_not_announced")
            if gate.ready and not execution.stopped:
                server_plan = _q3_server_plan(contract.service_plan)
                with execution.ledger.purpose_of("q3:product:e6_server"):
                    server_application = ServiceApplicator(service_runtime).apply(
                        server_plan,
                        actual_source_topology_hash=(
                            contract.manifest.physical_topology_hash
                        ),
                        actual_source_configuration_hash=(
                            contract.service_plan.source_configuration_hash
                        ),
                        foundational_statuses=foundations,
                        capabilities=contract.service_capabilities,
                        runtime_context=context,
                        deployment_manifest=contract.manifest,
                    )
                setup_cause = _q3_service_result_cause(
                    server_application,
                    {item.id for item in server_plan.actions},
                    expected_verification_ids={
                        item.id for item in server_plan.verification_expectations
                    },
                )
                server_mutations = [
                    row.received_mutation
                    for row in server_application.action_results
                    if row.received_mutation is not None
                ]
                server_readback = next(
                    iter(server_application.verification_results), None
                )
                if setup_cause:
                    execution.stop(setup_cause)
            after_snapshot = _q3_default_read(execution, "after_setup")
            if not after_snapshot.observed:
                setup_cause = setup_cause or (
                    "q3_native_default_unobserved:" + after_snapshot.cause
                )
                execution.stop(setup_cause)
            elif execution.default_pool_differences:
                setup_cause = setup_cause or (
                    "q3_native_default_changed:" + execution.default_pool_differences[0]
                )
                execution.stop(setup_cause)
            clients_after = clients_before
            if configuration is not None and execution.ledger.can_afford(1):
                clients_after = execution.probes.read_dhcp_clients(clients)
            mac, mode = _q3_client_assessments(clients_before, clients_after)
            execution.conclude(
                "M-DHCP-1",
                _q3_setup_assessment(
                    baseline,
                    admission,
                    configuration,
                    foundations,
                    server_mutations,
                    server_readback,
                    contract,
                    _native_default_facts(execution),
                    gate.facts(),
                    setup_cause,
                ),
            )
            execution.conclude("M-DHCP-4", mac)
            execution.conclude("M-DHCP-5", mode)
    execution.finish("Q3_SETUP")
    if execution.stopped:
        _q3_default_read(execution, "before_cleanup")
        return

    # M-DHCP-3 is OMITTED in this profile: no observer is registered, so the
    # procedure is the lease table and the lease-time window only.
    measurement_ids = ("M-DHCP-2", "M-DHCP-6")
    if not execution.begin(measurement_ids, "Q3_DHCP"):
        return
    with execution.procedure(measurement_ids):
        claim = execution.probes.write_bag_sentinel()
        if claim.observed and claim.payload.get("run_bag_preexisting"):
            execution.bag_collision = True
        elif (
            claim.observed
            and claim.payload.get("written")
            and claim.payload.get("owned")
        ):
            execution.bag_touched = True
            execution.bag_unreleased.add("sentinel")
        else:
            execution.stop("q3_run_bag_not_owned")
        before_one = before_two = empty_table = None
        service_result = None
        guard = None
        guard_not_run = "" if gate.ready else f"readiness_not_established:{gate.reason}"
        after_one = after_two = full_table = None
        if not execution.stopped:
            before_one = execution.probes.read_dhcp_clients(clients)
            execution.settle()
            before_two = execution.probes.read_dhcp_clients(clients)
            empty_table = execution.probes.read_dhcp_table(
                Q3_SERVER, "FastEthernet0", Q3_POOL
            )
        if not execution.stopped and gate.ready:
            nonces = {
                reference: f"{execution.nonce}:{index}"
                for index, reference in enumerate(
                    contract.service_plan.operation_nonce_refs(), start=1
                )
            }
            bound_plan = contract.service_plan.with_operation_nonces(nonces)
            first_acquisition = next(
                item
                for item in bound_plan.actions
                if isinstance(item, AcquireDhcpLease)
                and item.host_device_name == Q3_PC1
            )
            if not execution.run.transition("experiment:Q3_DHCP:product_started"):
                execution.stop("persistence:q3_product_not_announced")
            if not execution.stopped:
                with execution.ledger.purpose_of("q3:product:service_apply"):
                    service_result = ServiceApplicator(service_runtime).apply(
                        bound_plan,
                        actual_source_topology_hash=(
                            contract.manifest.physical_topology_hash
                        ),
                        actual_source_configuration_hash=(
                            contract.service_plan.source_configuration_hash
                        ),
                        foundational_statuses=foundations,
                        capabilities=contract.service_capabilities,
                        runtime_context=context,
                        deployment_manifest=contract.manifest,
                        retained_action_results=(
                            server_application.action_results
                            if server_application is not None
                            else ()
                        ),
                    )
                verification_by_id = {
                    item.expectation_id: item
                    for item in service_result.verification_results
                }
                recovered_action_ids = {
                    expectation.action_id
                    for expectation in bound_plan.verification_expectations
                    if (
                        (row := verification_by_id.get(expectation.id)) is not None
                        and row.status is ActionExecutionStatus.VERIFIED
                        and row.fresh_evidence
                        and row.observation is ObservationFact.OBSERVED
                    )
                }
                guard_not_run = _q3_service_result_cause(
                    service_result,
                    {item.id for item in bound_plan.actions},
                    expected_verification_ids={
                        item.id for item in bound_plan.verification_expectations
                    },
                    recovered_action_ids=recovered_action_ids,
                )
                if guard_not_run:
                    execution.stop(guard_not_run)
                else:
                    with execution.ledger.purpose_of("q3:guard:acquisition_replay"):
                        [guard] = service_runtime.apply_actions([first_acquisition])
                after_one = execution.probes.read_dhcp_clients(clients)
                execution.settle()
                after_two = execution.probes.read_dhcp_clients(clients)
                full_table = execution.probes.read_dhcp_table(
                    Q3_SERVER, "FastEthernet0", Q3_POOL
                )
        _q3_default_read(execution, "before_cleanup")
        if service_result is not None:
            for action in contract.service_plan.actions:
                if isinstance(action, AcquireDhcpLease):
                    execution.record.releases.append(
                        ReleaseRecord(
                            resource=f"claim:{action.host_device_name}:FastEthernet0",
                            kind="claim",
                            outcome="retained_until_process_retirement",
                            detail="product claims are never reset or deleted",
                        )
                    )
                    execution.record.engine_residue.append(
                        f"claim:{action.host_device_name}:retained"
                    )
        if service_result is None and not gate.ready and not execution.stopped:
            # Nothing was dispatched, so neither measurement was interrupted:
            # both record what the unready fixture allowed them to observe.
            execution.conclude(
                "M-DHCP-2", _q3_table_assessment(empty_table, full_table)
            )
            execution.conclude(
                "M-DHCP-6",
                _q3_timing_assessment(
                    before_one,
                    before_two,
                    after_one,
                    after_two,
                    None,
                    None,
                    guard_not_run,
                    gate.facts(),
                    _native_default_facts(execution),
                ),
            )
        elif service_result is None:
            execution.interrupt_in_flight(
                execution.record.primary_failure or "q3_product_application_not_run"
            )
        else:
            execution.conclude(
                "M-DHCP-2", _q3_table_assessment(empty_table, full_table)
            )
            execution.conclude(
                "M-DHCP-6",
                _q3_timing_assessment(
                    before_one,
                    before_two,
                    after_one,
                    after_two,
                    service_result,
                    guard,
                    guard_not_run,
                    gate.facts(),
                    _native_default_facts(execution),
                ),
            )
    execution.finish("Q3_DHCP")


# -- finalization ----------------------------------------------------------------


def _finalize(execution: _Execution) -> None:
    """Release owned state, remove owned devices and prove restoration twice."""
    ledger = execution.ledger
    ledger.enter(LedgerPhase.FINALIZATION)
    record = execution.record
    execution.in_flight = ()
    execution.run.transition("finalization:started")
    _release_engine_state(execution)
    for plan in reversed(execution.removal_candidates):
        fixture = next(item for item in record.fixtures if item.name == plan.name)
        try:
            with ledger.purpose_of(f"remove:{plan.name}"):
                result = execution.physical.remove_device(plan)
        except OperationRefused as exc:
            record.secondary_failures.append(f"remove:{plan.name}:{exc.reason}")
            record.releases.append(
                ReleaseRecord(
                    resource=f"device:{plan.name}",
                    kind="device",
                    outcome="not_attempted",
                    detail=exc.reason,
                )
            )
            record.engine_residue.append(f"device:{plan.name}:removal_not_attempted")
            continue
        except Exception as exc:
            record.secondary_failures.append(
                f"remove:{plan.name}:exception:{type(exc).__name__}"
            )
            record.engine_residue.append(f"device:{plan.name}:removal_unknown")
            continue
        outcome = {
            MutationDisposition.CHANGED: "removed",
            MutationDisposition.NO_OP: "already_absent",
            MutationDisposition.UNKNOWN: "unknown",
        }.get(result.disposition, "failed")
        record.releases.append(
            ReleaseRecord(
                resource=f"device:{plan.name}",
                kind="device",
                outcome=outcome,
                detail=_bounded(result.message),
            )
        )
        if outcome in ("unknown", "failed"):
            # An ambiguous removal is never repeated as if it had not run.
            record.engine_residue.append(f"device:{plan.name}:removal_{outcome}")
            record.secondary_failures.append(f"remove:{plan.name}:{outcome}")
        fixture.detail = _bounded(f"{fixture.detail} | cleanup:{outcome}")
    observations: list[PhysicalWorkspaceObservation | None] = []
    for index in (1, 2):
        try:
            with ledger.purpose_of(f"read:restoration:{index}"):
                observations.append(execution.physical.observe_workspace())
        except OperationRefused as exc:
            record.secondary_failures.append(f"restoration:{index}:{exc.reason}")
            observations.append(None)
        except Exception as exc:
            record.secondary_failures.append(
                f"restoration:{index}:exception:{type(exc).__name__}"
            )
            observations.append(None)
    record.restoration = [
        item.compact_summary() if item is not None else {"observed": False}
        for item in observations
    ]
    _restoration_scope(execution, observations)
    record.restoration_proven = all(
        item is not None
        and physical_workspace_restoration_matches(execution.baseline, item)
        for item in observations
    )
    for name in sorted(execution.observers_unresolved):
        record.engine_residue.append(f"observer:{name}")
    record.dirty_state = _dirty_state(execution, observations)
    execution.run.transition("finalization:completed")


def _restoration_scope(
    execution: _Execution,
    observations: Sequence[PhysicalWorkspaceObservation | None],
) -> None:
    """State what restoration compares, and name a changed raw count.

    Restoration compares semantic devices and links and permits Packet
    Tracer's own backend-managed devices. That is not equality of the whole
    workspace, so a record whose backend-managed count differs from the
    baseline says so -- the raw reads stay unchanged beside it.
    """
    if execution.baseline is None or not execution.baseline.observed:
        return
    baseline = len(execution.baseline.backend_managed_devices)
    counts = sorted(
        {
            len(item.backend_managed_devices)
            for item in observations
            if item is not None and item.observed
        }
    )
    if not counts:
        return
    limitations = execution.record.limitations
    if "restoration_scope:semantic_devices_and_links" not in limitations:
        limitations.append("restoration_scope:semantic_devices_and_links")
    for count in counts:
        if count != baseline:
            limitations.append(f"backend_managed_devices_changed:{baseline}->{count}")


def _release_engine_state(execution: _Execution) -> None:
    """Delete the run's own bag once; never touch a key it cannot prove it owns.

    Two gates stand in front of the delete and they are not the same one. Here,
    a reported collision means the claim wrote nothing, so there is nothing to
    release and nothing is dispatched. Inside the engine, the release proves
    this invocation's nonce in the evaluation that would delete, so a claim
    whose acknowledgement was lost still cannot make this adopt a key that
    belongs to someone else.
    """
    record = execution.record
    if execution.bag_collision:
        record.engine_residue.append("bag:run_key_not_exclusively_owned")
        record.releases.append(
            ReleaseRecord(
                resource="bag:run",
                kind="bag",
                outcome="not_attempted",
                detail="run key collision; nothing was written and nothing is deleted",
            )
        )
        return
    if not execution.bag_touched:
        return
    # Even when every step released its own entry, the run key itself is
    # still present in the engine, so the finalizer always removes it.
    try:
        with execution.ledger.purpose_of("release:run_bag"):
            reading = execution.probes.release_run_bag()
    except OperationRefused as exc:
        record.secondary_failures.append(f"release:run_bag:{exc.reason}")
        reading = None
    except Exception as exc:
        record.secondary_failures.append(
            f"release:run_bag:exception:{type(exc).__name__}"
        )
        reading = None
    if reading is not None and reading.observed:
        if _bag_released(execution, reading):
            return
    record.releases.append(
        ReleaseRecord(
            resource="bag:run",
            kind="bag",
            outcome="release_unverified",
            detail=reading.cause if reading is not None else "not_dispatched",
        )
    )
    # The run key itself is residue even when every step released its own
    # entry: nothing observed its deletion.
    record.engine_residue.append("bag:run_key:release_unverified")
    _unreleased_residue(execution)


def _bag_released(execution: _Execution, reading: ProbeReading) -> bool:
    """Record what one observed release reading settled, or return False."""
    record = execution.record
    keys = "keys=" + ",".join(str(item) for item in reading.payload["keys"])
    if not reading.payload["had_run_bag"]:
        record.releases.append(
            ReleaseRecord(
                resource="bag:run",
                kind="bag",
                outcome="absent_at_release",
                detail=keys,
            )
        )
        execution.bag_unreleased.clear()
        return True
    if not reading.payload["owned"]:
        # A key exists under this run's name that this invocation cannot prove
        # it wrote. It is reported as residue, never adopted and never deleted.
        record.releases.append(
            ReleaseRecord(
                resource="bag:run",
                kind="bag",
                outcome="not_attempted",
                detail="run key present but not owned by this invocation",
            )
        )
        record.engine_residue.append("bag:run_key_not_owned")
        _unreleased_residue(execution)
        return True
    if reading.payload["deleted"] and not reading.payload["present_after"]:
        record.releases.append(
            ReleaseRecord(
                resource="bag:run", kind="bag", outcome="released", detail=keys
            )
        )
        if execution.bag_unreleased & {"atom"}:
            # A contender that has not run yet can recreate its entry later.
            record.engine_residue.append("bag:atom:contender_may_still_run")
        execution.bag_unreleased.clear()
        return True
    return False


def _unreleased_residue(execution: _Execution) -> None:
    """Report every run-bag entry whose release this run could not observe."""
    for name in sorted(execution.bag_unreleased):
        execution.record.engine_residue.append(f"bag:{name}:release_unverified")


def _dirty_state(
    execution: _Execution, observations: Sequence[PhysicalWorkspaceObservation | None]
) -> DirtyState:
    record = execution.record
    if record.restoration_proven and not record.engine_residue:
        return DirtyState.CLEAN
    owned = {plan.name for plan in execution.removal_candidates}
    known_devices_only = bool(record.engine_residue) and all(
        item.startswith("device:") for item in record.engine_residue
    )
    if (
        known_devices_only
        and all(item is not None and item.observed for item in observations)
        and all(
            {device.name for device in item.semantic_devices} <= owned
            for item in observations
            if item is not None
        )
    ):
        return DirtyState.DIRTY_RECOVERABLE
    return DirtyState.UNKNOWN
