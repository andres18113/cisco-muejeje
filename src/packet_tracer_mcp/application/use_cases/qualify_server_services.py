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
from ...domain.enterprise.models.forwarding import (
    ForwardingAddressMode,
    ForwardingEndpointSelection,
    ForwardingKnownAddress,
    ForwardingRuntimeEndpoint,
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
    D_WEB_FORWARDING_SAMPLES_AFTER,
    D_WEB_FORWARDING_SAMPLES_BEFORE,
    D_WEB_INSPECTION_SCHEDULE,
    DIAGNOSTIC_ACCESS_VLAN,
    EFFECT_GATE_LIMIT,
    LOCAL_OBSERVATION_TIMEOUT_SECONDS,
    Q1_PC1,
    Q1_SERVER,
    Q1_SERVER_IPV4,
    Q1_SWITCH,
    Q3_FL_BACKGROUND_INTERVAL_SECONDS,
    Q3_FL_FIXTURE_ACCESS_VLAN,
    Q3_FL_INTENDED_EXTRA_INDEXES,
    Q3_FL_NATIVE_DEFAULT_POLICY,
    Q3_FL_NATIVE_SCAN_INDEXES,
    Q3_FL_RENEWAL_HORIZON_READS,
    Q3_FL_RENEWAL_INTERVAL_SECONDS,
    Q3_FL_SETTLE_INTERVAL_SECONDS,
    Q3_FL_SETTLE_READS,
    Q3_FL_STAGES,
    Q3_FL_TIMED_INTERVAL_SECONDS,
    Q3_LEASE_IPV4,
    Q3_NATIVE_STAGES,
    Q3_NATIVE_START_AFTER,
    Q3_NATIVE_START_BEFORE,
    Q3_NATIVE_START_EVIDENCE_SHA256,
    Q3_OBSERVED_NATIVE_DEFAULT_POOL,
    Q3_PC1,
    Q3_PC2,
    Q3_POOL,
    Q3_SERVER,
    READINESS_DEADLINE_SECONDS,
    READINESS_MAX_READS,
    REQUESTED_RENEWAL_CONTRACT_ABSENT,
    BudgetRecord,
    DefaultPoolObservation,
    DiagnosticLifecycleObservation,
    DiagnosticPrecondition,
    EnvironmentIdentity,
    ExecutionMode,
    ExperimentSpec,
    FixtureDevice,
    FixtureRecord,
    MeasurementConclusion,
    MeasurementRecord,
    MeasurementStatus,
    OperationEntry,
    QualificationAuthorization,
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
    diagnostic_lifecycle_continuity,
    diagnostic_lifecycle_refusals,
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
from ...domain.enterprise.services.dhcp_lease_evidence import (
    NO_BACKGROUND_PROOF,
    NOT_DORA,
    SERVED_INTENDED,
    SERVED_NATIVE,
    SERVED_NONE,
    AddressRange,
    CalibrationState,
    ClientAttribution,
    ClientReading,
    LeaseScan,
    assess_capacity_one_negative,
    assess_lease_calibration,
    attribute_client,
    client_readings,
    is_dotted_mac,
    scans_by_pool,
    unobserved_scans,
)
from ...domain.enterprise.services.dhcp_native_default_lifecycle import (
    INTERVAL_REFUSED,
    UNEXPLAINED_DRIFT,
    AdmittedNativeDefaultTransition,
    NativeDefaultReading,
    NativeDefaultSequenceAssessment,
    assess_intended_pool_coexistence,
    assess_native_default_sequence,
)
from ...domain.enterprise.services.service_access_readiness import (
    DHCP_ACQUISITION_KINDS,
    derive_access_readiness_plan,
)
from ...domain.enterprise.services.service_diagnostic_profiles import (
    d_dhcp_enable_only_plan,
    d_dhcp_pool_only_plan,
    d_dhcp_static_only_plan,
    q3_fastloop_client_mode_plan,
    q3_fastloop_fixture_placements,
    q3_fastloop_service_plan,
)
from ...domain.enterprise.services.service_qualification_evidence import (
    ACTIVE_STIMULUS,
    BASELINE_OBSERVED_NATIVE_DEFAULT,
    DIAGNOSTIC_SCOPE,
    Assessment,
    BaselineAdmission,
    DefaultPoolSnapshot,
    ProbeReading,
    assess_access_forwarding,
    assess_atomicity,
    assess_bag_persistence,
    assess_baseline_drift,
    assess_client_timeline,
    assess_dhcp_baseline_admission,
    assess_forwarding_probe,
    assess_https_listener,
    assess_native_default_cumulative,
    assess_native_default_interval,
    assess_native_policy_address_probe,
    assess_native_policy_exclusion_probe,
    assess_native_pool_max_probe,
    assess_native_pool_repeated_start_probe,
    assess_native_pool_start_probe,
    assess_observer_release,
    assess_page_tables,
    assess_port_readiness,
    default_pool_differences,
    default_pool_snapshot,
    listener_toggle_established,
    marker_page_established,
    native_policy_exclusion_inventory_complete,
    native_policy_probe_baseline_admitted,
    native_policy_snapshot_complete,
    native_pool_probe_baseline_admitted,
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
from .server_pt_campaign import DHCP_AUTONOMY_CAMPAIGN, DHCP_FASTLOOP_CAMPAIGN
from .service_access_readiness_gate import (
    ReadinessNotRequired,
    ServiceAccessReadinessGate,
)

SendAndWait = Callable[[str, float], str | None]
MAX_DETAIL = 240
#: The worst case of one production fetch: start, two inspections, release.
FETCH_OPERATIONS = 4
#: The ledger purpose prefix every native default reading is dispatched under.
#: Why the qualification stages run no product readiness gate. They take their
#: own exact-port/VLAN forwarding evidence, keep it in their immutable records
#: with its own admission dimensions, and are budgeted for precisely the
#: operations their profile declares. Adding the product gate inside them would
#: spend unbudgeted operations and publish a second forwarding claim with a
#: different scope beside the measured one.
DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE = ReadinessNotRequired(
    "diagnostic qualification measures access forwarding explicitly, records it "
    "as stage evidence, and is budgeted for its own declared operations"
)

Q3_DEFAULT_PURPOSE = "q3:native_default"
#: The same reading under the D-DHCP diagnostic, so a record can never confuse
#: a Q3 sample with a diagnostic one by its purpose alone.
D_DHCP_DEFAULT_PURPOSE = "d-dhcp:native_default"
#: Why a measurement the authority scoped out did not run. It is the one
#: omission reason that does not keep a stage from completing: the run did
#: everything it was authorized to do.
NOT_SELECTED = "not_selected_by_authorization"


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
    #: A read-only final observation of what the run is about to leave
    #: behind. It is not an effect, so a closed effect gate does not
    #: suppress it -- the gate exists to stop further mutation, and a
    #: persistence failure is a reason to observe rather than to stop
    #: looking. It is not finalization either, so it spends the ordinary
    #: allowance and never the cleanup reserve.
    TERMINAL_OBSERVATION = "terminal_observation"
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
    whatever its result. Outside finalization the reserve is untouchable,
    except to a call admitted inside `protected_release`, and each call's
    timeout is capped so that the reserved seconds survive too.
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
        #: The control every dispatch inside an effect scope is admitted
        #: against, bound once before the invocation's first effect.
        self._effect_guard: Callable[[str, float], str] | None = None
        self._effect_scope = 0
        #: Depth of the protected-release scope. Only a caller that owns an
        #: owned-resource release opens it, and only around that one dispatch.
        self._protected_release = 0
        self.phase = LedgerPhase.ADMISSION
        self.purpose = ""
        self.used = 0
        #: Counted calls that were charged to the reserve rather than to the
        #: ordinary allowance. Zero for every caller that never opens
        #: `protected_release`, which keeps their arithmetic exactly as it was.
        self.reserve_used = 0
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

    def bind_effect_guard(self, guard: Callable[[str, float], str]) -> None:
        """Bind the control every effect dispatch is decided against.

        It is bound exactly once, after the invocation's execution state
        exists and before its first effect. Until then an effect scope has no
        control to satisfy, which `admit` treats as a refusal rather than as
        permission.
        """
        self._effect_guard = guard

    @contextmanager
    def effect_of(self, purpose: str) -> Iterator[None]:
        """Label a block whose dispatches change state in the receiver.

        Read-only work keeps `purpose_of`. What this adds is that each call
        admitted inside the block is decided against the effect guard
        immediately before it is handed to the channel, so one decision
        authorizes one dispatch instead of a whole phase. Scopes nest, because
        a runtime composed inside one may open its own.
        """
        self._effect_scope += 1
        try:
            with self.purpose_of(purpose):
                yield
        finally:
            self._effect_scope -= 1

    @contextmanager
    def protected_release(self) -> Iterator[None]:
        """Admit the calls inside the block against the reserve, one scope at a time.

        This is for a caller that releases a resource the invocation owns
        while ordinary work may still follow, which is why it is a scope and
        not a phase: the invocation is never switched into finalization, and
        the next call after the block is ordinary again. A call admitted here
        is charged to the reserve, may use the absolute deadline, and is still
        decided by the effect guard when one applies. It never makes reserve
        available to anything outside the block.
        """
        self._protected_release += 1
        try:
            yield
        finally:
            self._protected_release -= 1

    def allowance(self) -> tuple[int, float]:
        """Return the operations and seconds the current phase may still use."""
        deadline = self._start + self._max_seconds
        if self._protected_release:
            operations = self._reserve_operations - self.reserve_used
        elif self.phase is LedgerPhase.FINALIZATION:
            operations = self._max_operations - self.used
        else:
            operations = (
                self._max_operations
                - self._reserve_operations
                - (self.used - self.reserve_used)
            )
            deadline -= self._reserve_seconds
        seconds = deadline - self._clock()
        return operations, seconds

    def deadline(self) -> float:
        """Return the absolute monotonic deadline for the active phase."""
        deadline = self._start + self._max_seconds
        if self.phase is not LedgerPhase.FINALIZATION and not self._protected_release:
            deadline -= self._reserve_seconds
        return deadline

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
        """Count one call and return its index and capped timeout, or refuse it.

        A call with no remaining allowance is refused before its potentially
        expensive effect guard. When the guard does run, it receives the one
        absolute deadline for this phase, and allowance is recomputed before
        dispatch because the local authority observation spends wall-clock.
        """
        reason = ""
        protected = bool(self._protected_release)
        exhausted = (
            "protected_reserve_exhausted" if protected else "operation_budget_exhausted"
        )
        phase = "protected_release" if protected else self.phase.value
        halted = (
            not self._effects_open
            and not protected
            and self.phase
            not in (
                LedgerPhase.FINALIZATION,
                LedgerPhase.TERMINAL_OBSERVATION,
            )
        )
        if halted:
            reason = f"effects_halted:{self._halt_reason}"
        operations, seconds = self.allowance()
        if not reason and operations < 1:
            reason = exhausted
        if not reason and seconds <= 0:
            reason = "time_budget_exhausted"
        if not reason and self._effect_scope:
            if self._effect_guard is None:
                # A control that is absent cannot be satisfied, and an effect
                # never proceeds on the strength of a check nobody made.
                reason = "effect_guard_not_bound"
            else:
                lost = self._effect_guard(self.purpose, self.deadline())
                if lost:
                    reason = f"execution_authority_lost:{lost}"
        # The authority read may have spent the phase's last second. A stale
        # pre-read allowance never authorizes the subsequent bridge dispatch.
        operations, seconds = self.allowance()
        if not reason and operations < 1:
            reason = exhausted
        if not reason and seconds <= 0:
            reason = "time_budget_exhausted"
        if reason:
            self.entries.append(
                OperationEntry(
                    seq=0,
                    phase=phase,
                    call=call,
                    purpose=self.purpose,
                    started_offset_seconds=round(self.elapsed(), 3),
                    refused=reason,
                )
            )
            raise OperationRefused(reason)
        timeout = max(0.0, min(float(requested_timeout), seconds))
        self.used += 1
        if protected:
            self.reserve_used += 1
        self.entries.append(
            OperationEntry(
                seq=self.used,
                phase=phase,
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

    def settle_pending_sends(self) -> bool:
        """Retire completed local sends and report any unresolved one fail-closed."""
        collect = getattr(self._transport, "collect_completed", None)
        pending = getattr(self._transport, "has_pending_requests", None)
        if not callable(collect) and not callable(pending):
            return False
        try:
            if callable(collect):
                collect()
            return bool(pending()) if callable(pending) else False
        except Exception:
            return True

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
    #: Only the two diagnostic stages compose these. `forwarding_probe` is the
    #: existing bind-before-ping executor bound to this invocation's ledger,
    #: and `diagnostic_service_runtime` is the product web reader with the
    #: explicit inspection schedule, the late read and the ledger's own
    #: allowance reader. A stage that needs one and does not have it refuses
    #: before contact rather than running a narrower experiment.
    forwarding_probe: Callable[[LedgeredTransport], Any] | None = None
    diagnostic_service_runtime: (
        Callable[[LedgeredTransport, Callable[[], tuple[int, float]]], ServiceRuntime]
        | None
    ) = None
    #: Read-only local process/mailbox identity for executable diagnostics.
    #: It runs before a transport is constructed, launches nothing and deletes
    #: nothing. The workspace gate after contact still proves the active
    #: document is disposable before the first effect.
    diagnostic_lifecycle: (
        Callable[[float | None], DiagnosticLifecycleObservation] | None
    ) = None
    #: Cross-checkout exclusion for one campaign writer, taken in the shared
    #: mailbox scope rather than in this checkout's record directory, and held
    #: from admission through finalization. Two worktrees cannot exclude each
    #: other through record directories they do not share, so a diagnostic
    #: stage without a coordinator refuses before contact.
    campaign_coordinator: Any | None = None
    #: The Q3-FL composition. `dhcp_product_contract` composes the real E4/E5/
    #: E6 plans for an intended pool of the stage's capacity; the reviewed
    #: native-default transitions arrive from the catalog through composition,
    #: keyed by the observed build, with the name of the one intervention the
    #: reviewed record brackets. None of them is a domain constant.
    dhcp_product_contract: Callable[[str, str, int], Q3ProductContract] | None = None
    native_default_transitions: (
        Callable[[str], tuple[AdmittedNativeDefaultTransition, ...]] | None
    ) = None
    reviewed_native_default_intervention: str = ""
    #: Set only by a validated experimental campaign composition. See
    #: `CampaignQualificationAuthority`.
    campaign_source_authority: CampaignQualificationAuthority | None = None


@dataclass(frozen=True)
class CampaignQualificationAuthority:
    """Validated campaign permission for one qualification attempt.

    Only the qualification CLI's campaign composition constructs this, after
    it validated the campaign's charter digest, the open episode, that
    episode's exact HEAD and tree, the attempt's launch record and the
    ledger admission of this qualification phase. It waives exactly one
    rule, that the executed HEAD be published as its upstream, and only for
    the attempt, authorization, HEAD and tree it names. It also carries the
    creation identity of the process the launch record pinned, which the
    local preflight must then observe.
    """

    campaign_id: str
    episode: int
    #: The ledger record the composition wrote before contact. It must be
    #: the qualification admission of exactly this episode and attempt.
    admission_record: str
    attempt_id: str
    authorization_id: str
    sha: str
    tree: str
    process_incarnation: str

    def permits(
        self, request: QualificationRequest, repository: RepositoryIdentity
    ) -> bool:
        """Whether this authority is for exactly this request and checkout."""
        authorization = request.authorization
        definition = stage_definition(request.stage)
        return bool(
            authorization is not None
            and definition is not None
            and (
                (
                    definition.stage in Q3_FL_STAGES
                    and self.campaign_id == DHCP_FASTLOOP_CAMPAIGN.campaign_id
                )
                or (
                    definition.stage in Q3_NATIVE_STAGES
                    and self.campaign_id == DHCP_AUTONOMY_CAMPAIGN.campaign_id
                )
            )
            and self.episode >= 1
            and self.admission_record
            == f"episode-{self.episode:04d}-{self.attempt_id}-qualification-admission"
            and self.process_incarnation
            and (
                self.attempt_id,
                self.authorization_id,
                self.sha,
                self.tree,
            )
            == (
                authorization.attempt_id,
                authorization.authorization_id,
                request.expected_head,
                authorization.tree,
            )
            and (repository.head, repository.tree) == (self.sha, self.tree)
        )


@dataclass
class QualificationResult:
    """What one invocation returns to its adapter."""

    outcome: QualificationOutcome
    refusals: list[QualificationRefusal] = field(default_factory=list)
    record: QualificationRecord | None = None
    record_path: str = ""
    claim_release: ReleaseRecord | None = None

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
        if self.claim_release is not None:
            summary["claim_release"] = self.claim_release.model_dump(mode="json")
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
                    "coordination_residue": record.coordination_residue,
                    "dirty_state": record.dirty_state.value,
                    "persisted_step": record.persisted_step,
                    "persist_error": record.persist_error,
                }
            )
        return summary


class QualificationCancelled(KeyboardInterrupt):
    """A controlled cancellation plus any pre-record claim-release fact."""

    def __init__(
        self,
        original: KeyboardInterrupt,
        claim_release: ReleaseRecord | None,
    ) -> None:
        """Preserve the cancellation while carrying local finalization output."""
        super().__init__(*original.args)
        self.claim_release = claim_release


# -- the invocation ------------------------------------------------------------


#: The boundaries each executable diagnostic requires to have been composed.
#: A missing one is a refusal before contact, never a quieter experiment.
_DIAGNOSTIC_BOUNDARIES: dict[QualificationStage, tuple[str, ...]] = {
    QualificationStage.D_DHCP: ("q3_product_contract", "diagnostic_lifecycle"),
    QualificationStage.D_WEB: (
        "forwarding_probe",
        "diagnostic_service_runtime",
        "diagnostic_lifecycle",
    ),
    **{
        stage: (
            "dhcp_product_contract",
            "diagnostic_lifecycle",
            "native_default_transitions",
        )
        for stage in (*Q3_FL_STAGES, *Q3_NATIVE_STAGES)
    },
}


def _refused(
    refusals: Sequence[QualificationRefusal],
    record: QualificationRecord | None = None,
    record_path: str = "",
    claim_release: ReleaseRecord | None = None,
) -> QualificationResult:
    return QualificationResult(
        outcome=QualificationOutcome.REFUSED,
        refusals=list(refusals),
        record=record,
        record_path=record_path,
        claim_release=claim_release,
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

    if type(boundaries.execution_mode) is not ExecutionMode:
        return _refused(
            [
                refusal(
                    RefusalKind.MALFORMED,
                    RefusalSubject.EXECUTION,
                    "Execution mode must be a typed boundary value.",
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
    authorization = request.authorization
    refusals = repository_refusals(
        repository,
        request.expected_head,
        authorization.tree if authorization is not None else "",
    )
    authority = boundaries.campaign_source_authority
    if (
        boundaries.execution_mode is ExecutionMode.LIVE
        and definition.stage in (*Q3_FL_STAGES, *Q3_NATIVE_STAGES)
        and authority is None
    ):
        return _refused(
            [
                refusal(
                    RefusalKind.MISSING,
                    RefusalSubject.AUTHORIZATION,
                    "This experimental DHCP stage requires its campaign authority.",
                )
            ]
        )
    if authority is not None:
        if not authority.permits(request, repository):
            return _refused(
                [
                    refusal(
                        RefusalKind.MISMATCH,
                        RefusalSubject.AUTHORIZATION,
                        "The campaign authority does not name this attempt, "
                        "authorization, HEAD and tree.",
                    )
                ]
            )
        # Exactly one rule is waived, and only for the attempt it names.
        refusals = tuple(
            item
            for item in refusals
            if item.subject is not RefusalSubject.REPOSITORY_UPSTREAM
        )
    if refusals:
        return _refused(refusals)
    diagnostic_lifecycle: DiagnosticLifecycleObservation | None = None
    hold = _CampaignHold(boundaries.campaign_coordinator)
    try:
        if definition.profile_id:
            refusals, diagnostic_lifecycle = _diagnostic_admission(
                definition, authorization, boundaries, hold
            )
            if refusals:
                return _refused(refusals, claim_release=hold.finalize())
        return _with_campaign_claim(
            request,
            boundaries,
            definition,
            devices,
            links,
            isolation,
            repository,
            experimental_capabilities,
            diagnostic_lifecycle=diagnostic_lifecycle,
            hold=hold,
        )
    except KeyboardInterrupt as exc:
        raise QualificationCancelled(exc, hold.finalize()) from exc
    finally:
        # Every ordinary path finalizes the hold before returning its result.
        # This remains the idempotent safety net for an unexpected exception.
        hold.finalize()


def _with_campaign_claim(
    request: QualificationRequest,
    boundaries: QualificationBoundaries,
    definition: StageDefinition,
    devices: tuple[DevicePlan, ...],
    links: tuple[LinkPlan, ...],
    isolation: IsolationObservation,
    repository: RepositoryIdentity,
    experimental_capabilities: frozenset[str],
    *,
    diagnostic_lifecycle: DiagnosticLifecycleObservation | None,
    hold: _CampaignHold,
) -> QualificationResult:
    """Run the admitted part of one invocation while its campaign claim is held."""
    moment = boundaries.now()
    run_id = boundaries.new_run_id(moment)
    product_contract: Q3ProductContract | None = None
    if definition.stage in (*Q3_FL_STAGES, *Q3_NATIVE_STAGES):
        if (
            not boundaries.q3_required_build
            or request.packet_tracer_build != boundaries.q3_required_build
            or boundaries.dhcp_product_contract is None
        ):
            return _refused(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "Q3-FL has no reviewed product contract for this build.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        try:
            product_contract = boundaries.dhcp_product_contract(
                request.packet_tracer_build, run_id, definition.dhcp_pool_capacity
            )
        except Exception as exc:
            return _refused(
                [
                    refusal(
                        RefusalKind.MALFORMED,
                        RefusalSubject.FIXTURE,
                        f"dhcp_product_contract:{type(exc).__name__}:{_bounded(exc)}",
                    )
                ],
                claim_release=hold.finalize(),
            )
    elif definition.stage in (QualificationStage.Q3, QualificationStage.D_DHCP):
        if not boundaries.q3_required_build:
            return _refused(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "The Q3 Packet Tracer build policy is not composed.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        if request.packet_tracer_build != boundaries.q3_required_build:
            return _refused(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.BUILD,
                        "Q3 is not implemented for the requested Packet Tracer build.",
                    )
                ],
                claim_release=hold.finalize(),
            )
        if boundaries.q3_product_contract is None:
            return _refused(
                [
                    refusal(
                        RefusalKind.NOT_PERMITTED,
                        RefusalSubject.FIXTURE,
                        "The executable Q3 product contract is not composed.",
                    )
                ],
                claim_release=hold.finalize(),
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
                ],
                claim_release=hold.finalize(),
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
        diagnostic_lifecycle=diagnostic_lifecycle,
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
            [refusal(RefusalKind.NOT_PERMITTED, RefusalSubject.RECORD, _bounded(exc))],
            claim_release=hold.finalize(),
        )
    run = _Run(record, boundaries, record_path, diagnostic_lifecycle, hold)

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
            hold=hold,
        )
    finally:
        if opened is not None and opened.transport is not None:
            try:
                boundaries.close_transport(opened)
            except Exception as exc:
                record.secondary_failures.append(
                    f"transport_close:{type(exc).__name__}"
                )


def _diagnostic_admission(
    definition: StageDefinition,
    authorization: QualificationAuthorization | None,
    boundaries: QualificationBoundaries,
    hold: _CampaignHold,
) -> tuple[list[QualificationRefusal], DiagnosticLifecycleObservation | None]:
    """Check what an executable diagnostic needs beyond the shared rule.

    Three things the request rule cannot decide on its own: whether this
    campaign is already being run by another writer, which only a scope both
    writers share can answer; whether this attempt identity has ever been used
    before; and whether the boundaries this stage's steps require were composed.
    All three fail closed. A campaign whose exclusivity cannot be taken is not
    exclusive, an attempt whose uniqueness cannot be observed is not unique, and
    a stage whose executor is missing refuses rather than running a narrower
    experiment under the same authority.

    The campaign claim is taken first and held while everything after it is
    decided, so the uniqueness check and the record creation that follows it
    are no longer two steps a second writer can interleave with. The caller
    owns `hold` before this function starts, so the claim is under its
    top-level finalizer before any fallible admission check runs.
    """
    if authorization is None:  # pragma: no cover - request_refusals covers it
        return [refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZATION)], None
    coordinator = boundaries.campaign_coordinator
    if coordinator is None:
        return (
            [
                refusal(
                    RefusalKind.NOT_PERMITTED,
                    RefusalSubject.ATTEMPT_IDENTITY,
                    "No campaign coordination scope is composed, so this run "
                    "cannot exclude a writer in another checkout.",
                )
            ],
            None,
        )
    try:
        claim = coordinator.claim(attempt_id=authorization.attempt_id)
    except Exception as exc:
        return (
            [
                refusal(
                    RefusalKind.NOT_PERMITTED,
                    RefusalSubject.ATTEMPT_IDENTITY,
                    f"campaign_not_exclusive:{_bounded(exc)}",
                )
            ],
            None,
        )
    hold.claim = claim
    found, observed = _diagnostic_admission_checks(
        definition, authorization, boundaries
    )
    return found, observed


def _release_claim(coordinator: Any, claim: Any) -> tuple[str, ...]:
    """Release one campaign claim, never raising out of a finalization path."""
    try:
        return tuple(coordinator.release(claim) or ())
    except Exception as exc:
        return (f"campaign_release_failed:{type(exc).__name__}",)


@dataclass
class _CampaignHold:
    """One campaign claim, and whether this invocation already released it.

    The release is a finalization result like any other, so it has to reach
    the record before the record is completed. It used to run in the caller's
    outer `finally`, which is after completion, so a lock that stayed held
    left the next campaign blocked with nothing in the record saying so. The
    hold makes the release idempotent: the run releases it inside its own
    lifecycle, and the outer `finally` is the safety net for every path that
    never got that far.
    """

    coordinator: Any = None
    claim: Any = None
    finalized: bool = False
    projected: bool = False
    release_fact: ReleaseRecord | None = None
    release_reasons: tuple[str, ...] = ()

    def finalize(
        self, record: QualificationRecord | None = None
    ) -> ReleaseRecord | None:
        """Release and project this invocation's claim exactly once."""
        if not self.finalized:
            self.finalized = True
            if self.claim is not None and self.coordinator is not None:
                reasons = _release_claim(self.coordinator, self.claim)
                self.release_reasons = reasons
                detail = _bounded("; ".join(reasons))
                outcome = "released" if not reasons else "release_unverified"
                if any("held_by_another_writer" in item for item in reasons):
                    outcome = "foreign_claim_retained"
                elif any("malformed" in item for item in reasons):
                    outcome = "malformed_claim_retained"
                self.release_fact = ReleaseRecord(
                    resource="campaign:lock",
                    kind="claim",
                    outcome=outcome,
                    detail=detail,
                )
        fact = self.release_fact
        if record is None or fact is None or self.projected:
            return fact
        self.projected = True
        record.releases.append(fact)
        if fact.outcome == "released":
            return fact
        reasons = self.release_reasons
        record.coordination_residue.extend(reasons)
        record.secondary_failures.extend(f"campaign_release:{item}" for item in reasons)
        record.limitations.append("campaign_lock_still_held_after_this_run")
        return fact


def _diagnostic_admission_checks(
    definition: StageDefinition,
    authorization: QualificationAuthorization,
    boundaries: QualificationBoundaries,
) -> tuple[list[QualificationRefusal], DiagnosticLifecycleObservation | None]:
    """Decide the remaining diagnostic admissions while the campaign is held."""
    found: list[QualificationRefusal] = []
    seen = getattr(boundaries.record_store, "attempt_exists", None)
    if not callable(seen):
        found.append(
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.ATTEMPT_IDENTITY,
                "The record store cannot state whether this attempt is new.",
            )
        )
    else:
        try:
            used = bool(seen(authorization.attempt_id))
        except Exception as exc:
            return (
                [
                    refusal(
                        RefusalKind.UNOBSERVABLE,
                        RefusalSubject.ATTEMPT_IDENTITY,
                        f"attempt_lookup_failed:{type(exc).__name__}",
                    )
                ],
                None,
            )
        if used:
            found.append(
                refusal(
                    RefusalKind.NOT_PERMITTED,
                    RefusalSubject.ATTEMPT_IDENTITY,
                    "This attempt identity already has a record; "
                    "a new SHA or process does not create an attempt.",
                )
            )
    required = _DIAGNOSTIC_BOUNDARIES.get(definition.stage, ())
    missing = [name for name in required if getattr(boundaries, name, None) is None]
    if missing:
        found.append(
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.FIXTURE,
                f"The executable {definition.stage.value} composition is "
                f"incomplete: {', '.join(missing)}.",
            )
        )
    observed: DiagnosticLifecycleObservation | None = None
    lifecycle = boundaries.diagnostic_lifecycle
    if callable(lifecycle):
        deadline = boundaries.clock() + max(
            0.0,
            float(definition.budget.max_seconds - definition.budget.reserve_seconds),
        )
        try:
            observed = lifecycle(deadline)
        except Exception as exc:
            observed = DiagnosticLifecycleObservation(
                error=f"diagnostic_lifecycle_failed:{type(exc).__name__}"
            )
        if boundaries.clock() > deadline and not observed.error:
            observed = DiagnosticLifecycleObservation(
                error="local_observation_deadline_exceeded:lifecycle"
            )
        found.extend(
            diagnostic_lifecycle_refusals(
                authorization,
                observed,
                authorization.build,
            )
        )
        authority = boundaries.campaign_source_authority
        if (
            authority is not None
            and not observed.error
            and observed.process_incarnation != authority.process_incarnation
        ):
            # The launch record pinned one incarnation. A process at the same
            # PID and path that is not that incarnation is another process.
            found.append(
                refusal(
                    RefusalKind.MISMATCH,
                    RefusalSubject.PROCESS_INSTANCE,
                    "The observed process is not the incarnation the campaign "
                    "launch record pinned.",
                )
            )
    return found, observed


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
    diagnostic_lifecycle: DiagnosticLifecycleObservation | None = None,
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
        diagnostic_lifecycle=(
            asdict(diagnostic_lifecycle) if diagnostic_lifecycle is not None else {}
        ),
    )


class _Run:
    """The record lifecycle of one admitted invocation."""

    def __init__(
        self,
        record: QualificationRecord,
        boundaries: QualificationBoundaries,
        record_path: str,
        diagnostic_lifecycle: DiagnosticLifecycleObservation | None = None,
        hold: _CampaignHold | None = None,
    ) -> None:
        self.record = record
        self.boundaries = boundaries
        self.record_path = record_path
        self.ledger: OperationLedger | None = None
        #: What the admission reading observed, kept so finalization can
        #: state whether that pairing is still the one it is describing.
        self.diagnostic_lifecycle = diagnostic_lifecycle
        self.hold = hold if hold is not None else _CampaignHold()

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
        claim_release = self.hold.finalize(self.record)
        self.complete(QualificationOutcome.REFUSED)
        return _refused(
            [reason], self.record, self.record_path, claim_release=claim_release
        )


def _admitted(
    run: _Run,
    request: QualificationRequest,
    definition: StageDefinition,
    devices: tuple[DevicePlan, ...],
    links: tuple[LinkPlan, ...],
    bound: LedgeredTransport,
    capabilities: frozenset[str],
    product_contract: Q3ProductContract | None = None,
    *,
    hold: _CampaignHold | None = None,
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
    hold = hold if hold is not None else _CampaignHold()
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
        claim=hold.claim,
        hold=hold,
        authorized_steps=(
            tuple(request.authorization.step_ids)
            if definition.steps and request.authorization is not None
            else ()
        ),
    )
    # Constructing the execution bound this ledger's effect guard, so from
    # here on no dispatch inside an effect scope reaches the channel without
    # that decision.
    if definition.profile_id:
        record.limitations.append(EFFECT_GATE_LIMIT)
        record.limitations.append(
            f"local_process_observation_bounded_seconds:{LOCAL_OBSERVATION_TIMEOUT_SECONDS}"
        )
    cancelled: BaseException | None = None
    try:
        if definition.stage is QualificationStage.Q0:
            _run_q0(execution)
        elif definition.stage is QualificationStage.Q1:
            _run_q1(execution)
        elif definition.stage is QualificationStage.D_DHCP:
            _run_d_dhcp(execution)
        elif definition.stage is QualificationStage.D_WEB:
            _run_d_web(execution)
        elif definition.stage in Q3_FL_STAGES:
            _run_q3_fastloop(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_PROBE:
            _run_q3_native_probe(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_SIZE:
            _run_q3_native_size(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_POLICY:
            _run_q3_native_policy(execution)
        elif definition.stage is QualificationStage.Q3_NATIVE_STABILITY:
            _run_q3_native_stability(execution)
        else:
            _run_q3(execution)
    except KeyboardInterrupt as exc:
        execution.cancelled = True
        execution.stop("cancelled")
        cancelled = exc
    except Exception as exc:
        execution.interrupt_in_flight(f"exception:{type(exc).__name__}")
        execution.stop(f"exception:{type(exc).__name__}:{_bounded(exc)}")
    finally:
        # The terminal read-only observation belongs to finalization, not to
        # the sequence that may have raised out of the middle of itself. Every
        # exit that reaches cleanup reaches this first, so the last reading is
        # always taken before the first deletion.
        terminal_cancellation = _observe_terminal(execution)
        if terminal_cancellation is not None and cancelled is None:
            cancelled = terminal_cancellation
        try:
            _finalize(execution)
        except Exception as exc:
            # A finalization defect is secondary: the record still completes
            # with the primary outcome and whatever finalization established.
            record.secondary_failures.append(
                f"finalization:exception:{type(exc).__name__}"
            )
        # The campaign claim is held through finalization and released before
        # the record is completed, so a lock that stayed held is a fact this
        # record carries rather than one that happens after it.
        _release_campaign_claim(execution)
    completed = (
        not record.primary_failure
        and record.restoration_proven
        and not record.coordination_residue
        and all(
            item.status is MeasurementStatus.RAN
            for item in record.measurements
            # A measurement the authority deliberately left out of its step
            # selection is not a measurement this run failed to make. Every
            # other omission still keeps the stage from completing.
            if item.required and item.reason != NOT_SELECTED
        )
    )
    run.complete(
        QualificationOutcome.COMPLETED if completed else QualificationOutcome.STOPPED
    )
    if cancelled is not None:
        raise cancelled
    return QualificationResult(
        outcome=record.outcome,
        record=record,
        record_path=run.record_path,
        claim_release=execution.hold.release_fact,
    )


# -- execution state -----------------------------------------------------------


@dataclass(frozen=True)
class _TerminalPhase:
    """One stage's terminal read-only observation, and what it measures.

    It is registered before the stage's first procedure, over the state object
    the procedures fill in, so the reading still has the baseline, the ordered
    interventions and the declared call footprint it needs to be interpreted
    even when the sequence raised out of the middle of itself.
    """

    ids: tuple[str, ...]
    procedure: str
    observe: Callable[[], None]


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
    #: The campaign claim this invocation holds, or None for a stage that
    #: declares no diagnostic profile. It is re-verified before effects.
    claim: Any | None = None
    #: The releasable hold over that claim. Finalization releases it before
    #: the record is completed; the caller's outer path only mops up.
    hold: _CampaignHold = field(default_factory=_CampaignHold)
    #: The steps this invocation's authority selected, in stage order. Empty
    #: for a stage that declares none, where every procedure runs.
    authorized_steps: tuple[str, ...] = ()
    #: Operational preconditions this run has actually established, which is
    #: not the same thing as what its measurements concluded. A diagnostic
    #: step is admitted from this set; a negative experimental finding is the
    #: result the diagnostic exists to produce and never revokes a state the
    #: run did establish.
    established: set[str] = field(default_factory=set)
    #: The first observed loss of live execution authority. Sticky: authority
    #: is never re-acquired inside a run, because a window in which some other
    #: process answered cannot be closed retroactively.
    authority_lost: str = ""
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
    #: The stage's terminal read-only phase, registered before its first
    #: procedure and taken exactly once from guaranteed finalization.
    terminal: _TerminalPhase | None = None
    terminal_taken: bool = False
    #: Whether the operator interrupted the run. A cancelled run stops doing
    #: work: it declares its terminal reading instead of taking it, and
    #: restarts no stimulus.
    cancelled: bool = False
    #: Wall clock spent on bounded local authority observations, which cost no
    #: bridge operation and still cost the phase time.
    local_observation_seconds: float = 0.0
    #: A phase-local refusal to start another authority observation. Unlike an
    #: observed mismatch it is not sticky across the cleanup-reserve boundary.
    authority_observation_refused: str = ""

    def __post_init__(self) -> None:
        """Bind this execution's effect guard before anything can dispatch.

        Binding here rather than at one call site is deliberate: an execution
        that exists over a ledger is the only thing that can answer for that
        ledger's effects, and a composition that forgot the step would
        otherwise refuse every effect it makes. The ledger still fails closed
        for anything that opens an effect scope without one.
        """
        ledger = self.run.ledger
        if ledger is not None:
            ledger.bind_effect_guard(self.effect_guard)

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

    def selected(self, step_id: str) -> bool:
        """Return whether the authority selected one diagnostic step.

        A stage that declares no steps selects everything it defines, which is
        what Q0/Q1/Q3 have always done. Selecting a step is permission to
        attempt it; it never bypasses the state the run must already have
        established, which the measurement prerequisites still decide.
        """
        if not self.definition.steps:
            return True
        return step_id in self.authorized_steps

    def stop(self, reason: str) -> None:
        """Keep the first stop reason as the primary failure."""
        if not self.record.primary_failure:
            self.record.primary_failure = _bounded(reason)

    def establish(self, *preconditions: str) -> None:
        """Record that this run observed one operational precondition."""
        self.established.update(preconditions)

    def live_authority(self, moment: str, deadline: float | None = None) -> bool:
        """Re-decide whether this invocation still holds execution authority.

        The admission reading bound one Packet Tracer incarnation and one
        campaign claim before any effect existed. Neither is held by anything
        afterwards: a crashed instance is replaced by one that polls the same
        mailbox, and a claim can be removed out from under this run. Every
        later effect, and owned cleanup above all, asks again.

        It enumerates local processes, reads one small file and lists one
        directory. It contacts Packet Tracer through nothing and spends no
        ledger operation, but it still spends wall-clock: the current phase
        must admit the observation and gives every helper the same absolute
        deadline. The first observed loss is kept and authority is never
        regained inside the run.
        """
        if self.authority_lost:
            return False
        if self.definition.profile_id == "":
            return True
        phase_deadline = self.ledger.deadline() if deadline is None else float(deadline)
        clock = self.run.boundaries.clock
        if clock() >= phase_deadline:
            return self._refuse_authority_observation(moment)
        self.authority_observation_refused = ""
        reasons: list[str] = []
        coordinator = self.run.boundaries.campaign_coordinator
        if coordinator is not None and self.claim is not None:
            try:
                reasons.extend(coordinator.verify(self.claim) or ())
            except Exception as exc:
                reasons.append(f"campaign_claim:unverifiable:{type(exc).__name__}")
        lifecycle = self.run.boundaries.diagnostic_lifecycle
        if (
            not reasons
            and callable(lifecycle)
            and self.run.diagnostic_lifecycle is not None
        ):
            if clock() >= phase_deadline:
                return self._refuse_authority_observation(moment)
            observed = self.observe_lifecycle(lifecycle, phase_deadline)
            reasons.extend(
                item
                for item in diagnostic_lifecycle_continuity(
                    self.run.diagnostic_lifecycle, observed
                )
                # A mailbox that still holds artifacts mid-run is this run's
                # own traffic in flight, not a second instance. Only identity
                # decides authority here; drainage is a finalization fact.
                if not item.startswith("mailbox:")
            )
        if not reasons:
            return True
        self.authority_lost = _bounded(f"{moment}:{reasons[0]}")
        record = self.record
        record.engine_residue.extend(reasons)
        record.secondary_failures.extend(f"authority:{item}" for item in reasons)
        record.limitations.append(f"execution_authority_lost_before:{_bounded(moment)}")
        self.stop(f"execution_authority_lost:{reasons[0]}")
        return False

    def _refuse_authority_observation(self, moment: str) -> bool:
        """Record that this phase had no time to observe local authority."""
        refusal = f"{_bounded(moment)}:time_budget_exhausted"
        self.authority_observation_refused = refusal
        failure = f"authority_observation_not_admitted:{refusal}"
        if failure not in self.record.secondary_failures:
            self.record.secondary_failures.append(failure)
        limitation = f"local_authority_observation_not_admitted:{refusal}"
        if limitation not in self.record.limitations:
            self.record.limitations.append(limitation)
        return False

    def observe_lifecycle(
        self,
        lifecycle: Callable[[float | None], DiagnosticLifecycleObservation],
        deadline: float,
    ) -> DiagnosticLifecycleObservation:
        """Read and charge one local pairing under an absolute deadline."""
        clock = self.run.boundaries.clock
        started = clock()
        try:
            observed = lifecycle(deadline)
        except Exception as exc:
            observed = DiagnosticLifecycleObservation(
                error=f"diagnostic_lifecycle_failed:{type(exc).__name__}"
            )
        finished = clock()
        self.local_observation_seconds += max(0.0, finished - started)
        self.record.budget.local_observation_seconds = round(
            self.local_observation_seconds, 3
        )
        if finished > deadline and not observed.error:
            return DiagnosticLifecycleObservation(
                error="local_observation_deadline_exceeded:lifecycle"
            )
        return observed

    def effect_guard(self, purpose: str, deadline: float) -> str:
        """Return why this one effect may not be dispatched, or "".

        The ledger asks this immediately before it admits a call inside an
        effect scope, which is the narrowest point this process controls. It
        is not an in-band receiver fence: no existing dispatcher carries a
        session token the receiver itself verifies in the evaluation that
        mutates, so the interval between this answer and the receiver
        consuming the command stays unfenced and is declared as a limitation
        of every diagnostic record. What it does close is the case the
        finalizer used to cache away -- a receiver replaced between two
        removals, or between a cleanup pre-read and the delete that follows
        it -- because the replacement is already in the local process table
        when the next dispatch asks.
        """
        if self.live_authority(f"effect:{purpose}" if purpose else "effect", deadline):
            return ""
        return (
            self.authority_lost
            or self.authority_observation_refused
            or "execution_authority_lost"
        )

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

    def not_observed(self, ids: Sequence[str], cause: str) -> None:
        """Record why the terminal reading was not taken, over any earlier note.

        The terminal phase is a decision taken after the sequence ended, so
        its absence is its own statement. A generic earlier note -- the stage
        never reached this measurement -- is true about the sequence and says
        nothing about the reading finalization just declined, so the specific
        cause replaces it. The run-level primary failure is untouched and
        still names what actually stopped the run.
        """
        for experiment_id in ids:
            item = self.measurement(experiment_id)
            if item.status is MeasurementStatus.NOT_RUN:
                item.reason = _bounded(f"not_observed:{cause}")

    def begin(self, ids: Sequence[str], procedure: str) -> bool:
        """Decide whether one procedure may start, and announce it durably."""
        if not self.live_authority(f"experiment:{procedure}"):
            reason = self.authority_lost or self.authority_observation_refused
            self.not_run(ids, f"execution_authority_unavailable:{reason}")
            return False
        return self.admissible(ids, procedure) and self.announce(ids, procedure)

    def register_terminal(
        self, ids: Sequence[str], procedure: str, observe: Callable[[], None]
    ) -> None:
        """Declare the stage's terminal reading before its first procedure.

        Registering is not taking. The reading is taken once, from guaranteed
        pre-cleanup finalization, whatever the sequence between here and there
        did -- completed, stopped, raised or lost its persistence.
        """
        self.terminal = _TerminalPhase(tuple(ids), procedure, observe)

    def begin_terminal(self, ids: Sequence[str], procedure: str) -> bool:
        """Admit one read-only terminal observation, success or not.

        The final reading of a diagnostic is evidence about what the run left
        behind, so a primary failure is the reason to take it rather than a
        reason to skip it. What it still requires is everything that makes the
        reading meaningful and safe: the authorized subject and session, the
        operational state the measurement names, its capability scope, and the
        ordinary allowance -- never the finalization reserve, which belongs to
        cleanup alone. A reading that cannot satisfy those is recorded as an
        explicit absence with its cause instead of being silently dropped.
        """
        specs = [self.definition.experiment(item) for item in ids]
        if not all(item.terminal_observation for item in specs):
            return self.begin(ids, procedure)
        if not self.live_authority(f"terminal:{procedure}"):
            if self.authority_observation_refused:
                self.not_observed(ids, "time_budget_exhausted")
            else:
                self.not_observed(ids, f"authority_lost:{self.authority_lost}")
            return False
        reason = self._unmet(specs)
        if reason:
            self.not_observed(ids, reason)
            return False
        planned = sum(item.planned_operations for item in specs)
        if not self.ledger.can_afford(planned):
            self.not_observed(ids, f"unaffordable:{procedure}")
            return False
        # The boundary is still written ahead of the reading. A record that
        # cannot advance loses durability, not the observation: the reading is
        # kept in memory and the record says which of the two it is.
        if not self.run.transition(f"experiment:{procedure}:started"):
            self.record.limitations.append(
                f"terminal_observation_retained_in_memory_only:{_bounded(procedure)}"
            )
        self.ledger.enter(LedgerPhase.TERMINAL_OBSERVATION)
        self.ledger.purpose = f"experiment:{procedure}"
        self.in_flight = tuple(ids)
        return True

    def admissible(
        self, ids: Sequence[str], procedure: str, extra_operations: int = 0
    ) -> bool:
        """Check stop state, prerequisites, capability scope and budget."""
        specs = [self.definition.experiment(item) for item in ids]
        if self.stopped:
            self.not_run(ids, f"stopped:{self.record.primary_failure}")
            return False
        reason = self._unmet(specs)
        if reason:
            self.not_run(ids, reason)
            return False
        planned = sum(item.planned_operations for item in specs) + extra_operations
        if not self.ledger.can_afford(planned):
            self.not_run(ids, f"budget_insufficient_for:{procedure}")
            self.stop(f"budget:{procedure}")
            return False
        return True

    def _unmet(self, specs: Sequence[ExperimentSpec]) -> str:
        """Return why these measurements may not be attempted, or "".

        A stage that declares a diagnostic profile is admitted from the
        operational state the run established; every other stage keeps the
        conclusion rule it always had, so no NEGATIVE or UNKNOWN prerequisite
        is admitted for Q0/Q1/Q3 or for any product caller.
        """
        diagnostic = bool(self.definition.profile_id)
        for spec in specs:
            if diagnostic:
                for precondition in spec.operational_prerequisites:
                    if precondition not in self.established:
                        return f"operational_precondition_unmet:{precondition}"
            else:
                for prerequisite in spec.prerequisites:
                    conclusion = self.measurement(prerequisite).conclusion
                    if conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
                        return f"prerequisite_unmet:{prerequisite}={conclusion.value}"
            missing = sorted(set(spec.capabilities) - self.capabilities)
            if missing:
                return "capability_not_in_scope:" + ",".join(missing)
        return ""

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
    # Setup is the first effect of the run and it happens before any
    # measurement announces itself, so the receiver is decided here too and
    # not only at each dispatch inside the loops below.
    if not execution.live_authority("fixtures:setup"):
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
            with ledger.effect_of(f"create:{plan.name}"):
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
            with ledger.effect_of(f"create:link:{index}"):
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
    # The identity read above proved the exact fixture names and models under
    # the bound session, which is what "correct subject" means operationally.
    execution.establish(DiagnosticPrecondition.SUBJECT_SESSION)
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


def _endpoint_action_id(execution: _Execution, name: str) -> str:
    """Return the exact E5 action id this stage dispatches for one fixture.

    The id names the stage, so a D-WEB forwarding selection can bind to the
    action the run actually applied rather than to a Q1 id it never wrote.
    """
    return f"{execution.definition.stage.value.lower()}-e5-{name}"


def _configure_q1(execution: _Execution) -> bool:
    """Address the endpoints through E5 and enable HTTP/HTTPS through E6.

    Shared by Q1 and by D-WEB, which measures the same fixture and needs the
    same two effects before it can ask anything about them. The action and
    service ids carry the stage's own name, so nothing in either record claims
    to be the other's row.
    """
    ledger = execution.ledger
    scope = execution.definition.stage.value.lower()
    fixtures = {item.name: item for item in execution.definition.fixtures}
    endpoints = [
        SetEndpointStaticAddress(
            id=_endpoint_action_id(execution, name),
            phase=ConfigurationPhase.ENDPOINT_ADDRESSING,
            device_id=name,
            device_name=name,
            site_id=scope,
            interface="FastEthernet0",
            ipv4=fixture.ipv4,
            netmask=fixture.netmask,
            gateway="",
            dns_server=fixture.dns_server or None,
            segment_id=scope,
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
        "site_id": scope,
        "required_capability": f"qualification:{execution.definition.stage.value}",
    }
    services = [
        EnableHttpService(
            id=f"{scope}-e6-http",
            service_id=f"{scope}-http",
            service_type=ServiceType.HTTP,
            **common,
        ),
        EnableHttpsService(
            id=f"{scope}-e6-https",
            service_id=f"{scope}-https",
            service_type=ServiceType.HTTPS,
            **common,
        ),
    ]
    try:
        with ledger.effect_of("apply:e5_endpoints"):
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
        with ledger.effect_of("apply:e6_enable_http_https"):
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


def _q3_default_purpose(label: str, prefix: str = Q3_DEFAULT_PURPOSE) -> str:
    """Return the ledger purpose one default reading is dispatched under."""
    return f"{prefix}:{label}"


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
    prefix: str = Q3_DEFAULT_PURPOSE,
) -> DefaultPoolSnapshot:
    """Classify and persist one default reading this run already performed."""
    return _q3_default_persist(
        execution,
        _q3_default_purpose(label, prefix),
        operation_seq,
        default_pool_snapshot(
            label,
            reading,
            intended_pool=Q3_POOL,
            server=Q3_SERVER,
            interface="FastEthernet0",
        ),
    )


def _q3_default_read(
    execution: _Execution,
    label: str,
    *,
    prefix: str = Q3_DEFAULT_PURPOSE,
    policy: bool = False,
) -> DefaultPoolSnapshot:
    """Dispatch one bounded default reading under its own purpose and persist it.

    The purpose is set before the call, so the counted operation states what it
    was for instead of being identified afterwards from its ordinal. A reading
    the remaining allowance cannot pay for, and one the ledger refuses, are
    explicitly not observed: no operation is added to the stage to repair the
    record, and the budgets are the ones the stage already planned.
    """
    purpose = _q3_default_purpose(label, prefix)
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
            if policy:
                reading = execution.probes.read_dhcp_server_policy(
                    Q3_SERVER, "FastEthernet0"
                )
            else:
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
        execution,
        label,
        reading,
        operation_seq=_counted_seq(ledger, start),
        prefix=prefix,
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
                with execution.ledger.effect_of("q3:product:e5_endpoints"):
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
                with execution.ledger.effect_of("q3:product:e6_server"):
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
                        operational_readiness=(
                            DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE
                        ),
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
                with execution.ledger.effect_of("q3:product:service_apply"):
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
                        operational_readiness=(
                            DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE
                        ),
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
                    with execution.ledger.effect_of("q3:guard:acquisition_replay"):
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


# -- executable diagnostics ------------------------------------------------------


def _diagnostic_start(execution: _Execution) -> bool:
    """Admit one diagnostic stage and omit what its authority did not select.

    An unselected measurement is OMITTED with its reason, not silently left
    NOT_RUN: the record has to say that the authority scoped it out rather
    than that the run failed to reach it. The stage still needs the whole
    selected path to afford itself before the first fixture is created.
    """
    definition = execution.definition
    selected_experiments = set(
        definition.experiments_of_steps(execution.authorized_steps)
        if definition.steps
        else [item.id for item in definition.experiments]
    )
    for item in execution.record.measurements:
        # A measurement the stage already omits keeps its own reason: the
        # authority did not scope it out, the profile never runs it.
        if (
            item.experiment_id not in selected_experiments
            and item.status is not MeasurementStatus.OMITTED
        ):
            item.status = MeasurementStatus.OMITTED
            item.reason = NOT_SELECTED
    planned = sum(
        definition.experiment(item).planned_operations for item in selected_experiments
    )
    required = [
        item.id
        for item in definition.experiments
        if item.required and item.id in selected_experiments
    ]
    if not execution.ledger.can_afford(definition.fixture_operations + planned):
        execution.not_run(required, f"budget_insufficient_for:{definition.stage.value}")
        execution.stop(f"budget:{definition.stage.value}")
        return False
    if not _setup_fixtures(execution):
        execution.not_run(required, "fixture_setup_failed")
        return False
    return True


def _d_dhcp_runtimes(execution: _Execution, contract: Q3ProductContract):
    """Bind the product E5/E6 runtimes to the exact manifest-directed fixture."""
    boundaries = execution.run.boundaries
    return (
        _Q3ConfigurationRuntime(
            boundaries.configuration_runtime(execution.bound), contract.inventory
        ),
        _Q3ServiceRuntime(
            boundaries.service_runtime(execution.bound), contract.inventory
        ),
    )


def _run_d_dhcp(execution: _Execution) -> None:
    """Run the causal server-only DHCP sequence, one bounded step at a time.

    Disabled baseline, the server's static addressing alone, the intended pool
    while the process is still disabled, the enable, the terminal reading. No
    client is activated, no lease is acquired, no default-pool setter is
    dispatched, and every adjacent pair of native readings is what the record
    attributes an interval to.
    """
    state = _DDhcpState()
    # Registered before the first fixture exists. Whatever the sequence below
    # does -- complete, stop, raise, or lose its record -- finalization takes
    # this reading over this exact state object, before it deletes anything.
    execution.register_terminal(
        ("M-DDHCP-4",), "D_DHCP_FINAL", lambda: _d_dhcp_final(execution, state)
    )
    if not _diagnostic_start(execution):
        return
    contract = execution.product_contract
    if contract is None:  # pragma: no cover - admission composes it
        execution.stop("d_dhcp_product_contract_absent")
        return
    configuration_runtime, service_runtime = _d_dhcp_runtimes(execution, contract)
    static_plan = d_dhcp_static_only_plan(
        contract.configuration_plan, device_name=Q3_SERVER
    )
    executed_ids = frozenset(item.id for item in static_plan.actions)
    context = _q3_context(contract)
    execution.record.limitations.extend(
        [
            "d_dhcp_private_candidate_capabilities:no_public_catalog_mutation",
            "d_dhcp_projection:server_static_address_only",
        ]
    )

    ids = ("M-DDHCP-0",)
    if execution.selected("D0-baseline") and execution.begin(ids, "D_DHCP_BASELINE"):
        with execution.procedure(ids):
            _d_dhcp_baseline(execution, state)
        execution.finish("D_DHCP_BASELINE")

    ids = ("M-DDHCP-1",)
    if execution.selected("D1-static") and execution.begin(ids, "D_DHCP_E5"):
        with execution.procedure(ids):
            _d_dhcp_static(
                execution, state, configuration_runtime, contract, static_plan, context
            )
        execution.finish("D_DHCP_E5")

    ids = ("M-DDHCP-2",)
    if execution.selected("D2-pool") and execution.begin(ids, "D_DHCP_POOL"):
        with execution.procedure(ids):
            _d_dhcp_pool(
                execution, state, service_runtime, contract, executed_ids, context
            )
        execution.finish("D_DHCP_POOL")

    ids = ("M-DDHCP-3",)
    if execution.selected("D3-enable") and execution.begin(ids, "D_DHCP_ENABLE"):
        with execution.procedure(ids):
            _d_dhcp_enable(
                execution, state, service_runtime, contract, executed_ids, context
            )
        execution.finish("D_DHCP_ENABLE")


def _d_dhcp_final(execution: _Execution, state: _DDhcpState) -> None:
    """Read the native default inventory one last time, before any cleanup.

    It is a cumulative baseline-to-final summary of the interventions this run
    actually dispatched, not an adjacent interval: the sequence may have
    stopped anywhere, and what the operator needs is what the whole run left
    behind. No baseline is invented from it and no earlier snapshot is
    rewritten by it.
    """
    ids = ("M-DDHCP-4",)
    if not execution.selected("D4-final"):
        return
    if not execution.begin_terminal(ids, "D_DHCP_FINAL"):
        return
    with execution.procedure(ids):
        final = _q3_default_read(
            execution, "d4_before_cleanup", prefix=D_DHCP_DEFAULT_PURPOSE
        )
        execution.conclude(
            "M-DDHCP-4",
            assess_native_default_cumulative(
                label="d4_cumulative",
                baseline=state.baseline,
                final=final,
                interventions=tuple(state.interventions),
                declared_native_calls=tuple(state.declared_native_calls),
            ),
        )
    execution.finish("D_DHCP_FINAL")


@dataclass
class _DDhcpState:
    """What one D-DHCP run has established, carried between its procedures."""

    baseline: DefaultPoolSnapshot | None = None
    control: DefaultPoolSnapshot | None = None
    after_static: DefaultPoolSnapshot | None = None
    after_pool: DefaultPoolSnapshot | None = None
    foundations: dict[str, ActionExecutionStatus] = field(default_factory=dict)
    last_intervention: str = "none:setup_only"
    native_calls: tuple[str, ...] = ()
    fields_written: tuple[str, ...] = ()
    rewrites: list[str] = field(default_factory=list)
    #: Every intervention this run actually dispatched, in order. The final
    #: reading spans all of them, so it is a cumulative summary and naming
    #: only the last one would attribute the whole span to one call.
    interventions: list[str] = field(default_factory=list)
    #: The generated call footprint each intervention declares. It is what
    #: the generator would emit, never a count of observed executions.
    declared_native_calls: list[str] = field(default_factory=list)

    def intervened(self, intervention: str, native_calls: Sequence[str]) -> None:
        """Record one dispatched intervention and its declared call footprint."""
        self.last_intervention = intervention
        self.interventions.append(intervention)
        self.declared_native_calls.extend(
            f"{intervention}:{item}" for item in native_calls
        )


def _d_dhcp_baseline(execution: _Execution, state: _DDhcpState) -> None:
    """Establish a coherent disabled baseline and the drift control beside it."""
    clients = ((Q3_PC1, "FastEthernet0"), (Q3_PC2, "FastEthernet0"))
    # One dispatch serves both the typed admission rule and the run's first
    # native reading, exactly as Q3 does: the baseline costs one operation.
    start = len(execution.ledger.entries)
    with execution.ledger.purpose_of(
        _q3_default_purpose("d0_baseline", D_DHCP_DEFAULT_PURPOSE)
    ):
        reading = execution.probes.read_dhcp_server_baseline(Q3_SERVER, "FastEthernet0")
    admission = assess_dhcp_baseline_admission(
        reading,
        server=Q3_SERVER,
        interface="FastEthernet0",
        intended_pool=Q3_POOL,
        observed_build=execution.record.environment.observed_build,
        qualified_build=execution.run.boundaries.q3_required_build,
        observed_channel=execution.channel,
        qualified_channels=execution.definition.allowed_channels,
    )
    state.baseline = _q3_default_observed(
        execution,
        "d0_baseline",
        reading,
        operation_seq=_counted_seq(execution.ledger, start),
        prefix=D_DHCP_DEFAULT_PURPOSE,
    )
    client_rows = _q3_client_rows(execution.probes.read_dhcp_clients(clients))
    endpoints = _fixture_endpoints(execution)
    gate = _await_readiness(
        execution,
        endpoints,
        lambda timeout: execution.probes.read_port_readiness(endpoints, timeout),
        purpose="readiness:d_dhcp_fixture_links",
    )
    drift: Assessment | None = None
    if execution.selected("D0-control"):
        state.control = _q3_default_read(
            execution, "d0_control", prefix=D_DHCP_DEFAULT_PURPOSE
        )
        drift = assess_baseline_drift(state.baseline, state.control)
    activated = [row for row in (client_rows or ()) if row.get("mode") is True]
    facts: dict[str, Any] = {
        "native_default": _native_default_facts(execution),
        "clients": client_rows if client_rows is not None else [],
        "clients_readable": client_rows is not None,
        "readiness": gate.facts(),
        "baseline_admission": {
            "admitted": admission.admitted,
            "kind": admission.kind,
            "causes": list(admission.causes),
        },
    }
    causes: list[str] = []
    limitations = [
        DIAGNOSTIC_SCOPE,
        "client_dhcp_flags_are_never_written_by_this_stage",
    ]
    if drift is not None:
        facts.update(drift.facts)
        causes.extend(drift.causes)
        limitations.extend(drift.limitations)
    if not admission.admitted:
        causes.extend(["initial_dhcp_server_state_not_admissible", *admission.causes])
    if state.baseline is not None and not state.baseline.observed:
        causes.append(f"native_default_unobserved:{state.baseline.cause}")
    if client_rows is None:
        causes.append("client_rows_not_readable")
    if activated:
        causes.append("client_dhcp_mode_already_on")
    if not gate.ready:
        causes.append(f"readiness_not_established:{gate.reason}")
    conclusion = (
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if not causes
        else (
            MeasurementConclusion.CONTRADICTED
            if drift is not None
            and drift.conclusion is MeasurementConclusion.CONTRADICTED
            else MeasurementConclusion.INCONCLUSIVE
        )
    )
    execution.conclude(
        "M-DDHCP-0",
        Assessment(conclusion, facts=facts, causes=causes, limitations=limitations),
    )
    if causes:
        execution.stop(f"d_dhcp_baseline_not_established:{causes[0]}")
        return
    # A coherent retained inventory and a verified-off process are two
    # separate operational facts, and the admission rule asks for them by
    # name rather than reading this measurement's conclusion.
    execution.establish(
        DiagnosticPrecondition.INVENTORY_COHERENT,
        DiagnosticPrecondition.PROCESS_DISABLED_VERIFIED,
    )


def _d_dhcp_static(
    execution: _Execution,
    state: _DDhcpState,
    configuration_runtime,
    contract: Q3ProductContract,
    static_plan: ConfigurationPlan,
    context: ConfigurationRuntimeContext,
) -> None:
    """Apply the server's static addressing alone and read the default again.

    The applied action is one `configurePcIp` call that writes the address,
    the netmask, the gateway and the DNS server together. That whole call is
    the intervention this interval is attributed to; no narrower cause is
    available from it and none is claimed.
    """
    if not execution.run.transition("experiment:D_DHCP_E5:started"):
        execution.stop("persistence:d_dhcp_e5_not_announced")
        return
    with execution.ledger.effect_of("d-dhcp:product:e5_server_address"):
        configuration = ConfigurationApplicator(configuration_runtime).apply(
            static_plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
        )
    foundation_plan = contract.service_plan.model_copy(
        update={
            "source_configuration_id": static_plan.id,
            "source_configuration_hash": static_plan.semantic_hash,
        },
        deep=True,
    )
    state.foundations = derive_service_foundational_statuses(
        foundation_plan, configuration
    )
    cause = _q3_e5_foundation_cause(
        configuration, state.foundations, {item.id for item in static_plan.actions}
    )
    action = next(iter(static_plan.actions), None)
    state.native_calls = ("configurePcIp",)
    state.fields_written = (
        ("ipv4", "netmask", "gateway", "dns_server")
        if isinstance(action, SetEndpointStaticAddress)
        else ()
    )
    state.intervened("e5:server_static_address:configurePcIp", state.native_calls)
    state.after_static = _q3_default_read(
        execution, "d1_after_server_address", prefix=D_DHCP_DEFAULT_PURPOSE
    )
    assessment = assess_native_default_interval(
        label="d1_interval",
        before=state.control or state.baseline or state.after_static,
        after=state.after_static,
        intervention=state.last_intervention,
        native_calls=state.native_calls,
        fields_written=state.fields_written,
    )
    assessment.facts["e5"] = {
        "plan_id": static_plan.id,
        "actions": [item.id for item in static_plan.actions],
        "reported": [item.action_id for item in configuration.action_results],
        "action_results": [
            item.model_dump(mode="json") for item in configuration.action_results
        ],
        "foundation_cause": cause,
        "gateway": getattr(action, "gateway", ""),
        "dns_server": getattr(action, "dns_server", "") or "",
    }
    if cause:
        assessment.causes.append(cause)
        assessment = Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=assessment.facts,
            causes=assessment.causes,
            limitations=assessment.limitations,
            outcome_unknown=assessment.outcome_unknown,
        )
    execution.conclude("M-DDHCP-1", assessment)
    if cause:
        execution.stop(cause)
        return
    # The E5 row applied and its address read-back succeeded. Whether the
    # native default moved across the interval is the finding this stage
    # exists to report, and it is not a reason D2 cannot be attempted.
    execution.establish(DiagnosticPrecondition.SERVER_ADDRESSING)


def _d_dhcp_service_stage(
    execution: _Execution,
    state: _DDhcpState,
    service_runtime,
    contract: Q3ProductContract,
    plan: ServicePlan,
    rewrites,
    context: ConfigurationRuntimeContext,
    *,
    purpose: str,
    intervention: str,
    native_calls: Sequence[str] = (),
) -> tuple[ServiceApplicationResult | None, str]:
    """Apply one projected E6 stage through the real product applicator."""
    state.rewrites.extend(item.as_text() for item in rewrites)
    with execution.ledger.effect_of(purpose):
        result = ServiceApplicator(service_runtime).apply(
            plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            actual_source_configuration_hash=(
                contract.service_plan.source_configuration_hash
            ),
            foundational_statuses=state.foundations,
            capabilities=contract.service_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
            operational_readiness=DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
        )
    cause = _q3_service_result_cause(
        result,
        {item.id for item in plan.actions},
        expected_verification_ids={item.id for item in plan.verification_expectations},
    ) or _d_dhcp_readback_cause(result)
    state.intervened(intervention, native_calls)
    return result, cause


def _d_dhcp_readback_cause(result: ServiceApplicationResult) -> str:
    """Return why a projected stage's read-back did not observe, or "".

    A stage whose whole point is the stored configuration cannot treat a
    verification that never ran as a pass. `_q3_service_result_cause` refuses
    a contradicted or errored row and a short result set, but a row the
    applicator reported DEPENDENCY_BLOCKED carries `UNSPECIFIED` and slipped
    through: the process was activated and nothing was read back.
    """
    for item in result.verification_results:
        if item.observation is not ObservationFact.OBSERVED:
            return (
                "outcome_unknown:diagnostic_readback_not_observed:"
                f"{item.expectation_id}:{item.observation.value}"
            )
    return ""


def _d_dhcp_pool(
    execution: _Execution,
    state: _DDhcpState,
    service_runtime,
    contract: Q3ProductContract,
    executed_ids: frozenset[str],
    context: ConfigurationRuntimeContext,
) -> None:
    """Write the intended pool with the process still disabled, and verify it."""
    plan, rewrites = d_dhcp_pool_only_plan(
        contract.service_plan, executed_configuration_action_ids=executed_ids
    )
    pool_action = next(
        (item for item in plan.actions if isinstance(item, ConfigureServerDhcpPool)),
        None,
    )
    pool_native_calls = (
        (
            "addPool",
            *(("addExcludedAddress",) if pool_action.excluded_ranges else ()),
            "setNetworkMask",
            "setDefaultRouter",
            *(("setDnsServerIp",) if pool_action.dns_server else ()),
            "setStartIp",
            "setEndIp",
            "setMaxUsers",
        )
        if pool_action is not None
        else ()
    )
    result, cause = _d_dhcp_service_stage(
        execution,
        state,
        service_runtime,
        contract,
        plan,
        rewrites,
        context,
        purpose="d-dhcp:product:e6_pool_disabled",
        intervention="e6:configure_server_dhcp_pool:process_disabled",
        native_calls=pool_native_calls,
    )
    state.after_pool = _q3_default_read(
        execution, "d2_after_pool", prefix=D_DHCP_DEFAULT_PURPOSE
    )
    assessment = assess_native_default_interval(
        label="d2_interval",
        before=state.after_static or state.baseline or state.after_pool,
        after=state.after_pool,
        intervention=state.last_intervention,
        native_calls=pool_native_calls,
        fields_written=(
            "pool_name",
            "excluded_ranges",
            "network",
            "netmask",
            "gateway",
            "dns_server",
            "lease_start",
            "lease_end",
            "max_users",
        ),
    )
    row = next(iter(result.verification_results), None) if result else None
    assessment.facts["e6_pool"] = {
        "plan_id": plan.id,
        "rewrites": list(state.rewrites),
        "expected_enabled": False,
        "action_results": (
            [item.model_dump(mode="json") for item in result.action_results]
            if result is not None
            else []
        ),
        "verification": row.model_dump(mode="json") if row is not None else None,
        "cause": cause,
    }
    if cause:
        assessment.causes.append(cause)
        assessment = Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=assessment.facts,
            causes=assessment.causes,
            limitations=assessment.limitations,
        )
    execution.conclude("M-DDHCP-2", assessment)
    if cause:
        execution.stop(cause)
        return
    # The stored pool verified against `enabled=False` plus its exact fields,
    # which is the state D3's activation depends on.
    execution.establish(DiagnosticPrecondition.POOL_CONFIGURED)


def _d_dhcp_enable(
    execution: _Execution,
    state: _DDhcpState,
    service_runtime,
    contract: Q3ProductContract,
    executed_ids: frozenset[str],
    context: ConfigurationRuntimeContext,
) -> None:
    """Enable the process and verify the transition the projection rebinds."""
    plan, rewrites = d_dhcp_enable_only_plan(
        contract.service_plan, executed_configuration_action_ids=executed_ids
    )
    result, cause = _d_dhcp_service_stage(
        execution,
        state,
        service_runtime,
        contract,
        plan,
        rewrites,
        context,
        purpose="d-dhcp:product:e6_enable",
        intervention="e6:enable_server_dhcp",
        native_calls=("setEnable",),
    )
    after = _q3_default_read(
        execution, "d3_after_enable", prefix=D_DHCP_DEFAULT_PURPOSE
    )
    assessment = assess_native_default_interval(
        label="d3_interval",
        before=state.after_pool or state.baseline or after,
        after=after,
        intervention=state.last_intervention,
        native_calls=("setEnable",),
    )
    row = next(iter(result.verification_results), None) if result else None
    assessment.facts["e6_enable"] = {
        "plan_id": plan.id,
        "rewrites": [item.as_text() for item in rewrites],
        "expected_enabled": True,
        "action_results": (
            [item.model_dump(mode="json") for item in result.action_results]
            if result is not None
            else []
        ),
        "verification": row.model_dump(mode="json") if row is not None else None,
        "cause": cause,
    }
    if cause:
        assessment.causes.append(cause)
        assessment = Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=assessment.facts,
            causes=assessment.causes,
            limitations=assessment.limitations,
        )
    execution.conclude("M-DDHCP-3", assessment)
    if cause:
        execution.stop(cause)
        return
    execution.establish(DiagnosticPrecondition.PROCESS_ENABLED_VERIFIED)


# -- delegated native-pool qualification -------------------------------------------


_Q3_NATIVE_POLICY_STAGES = frozenset(
    {QualificationStage.Q3_NATIVE_POLICY, QualificationStage.Q3_NATIVE_STABILITY}
)


def _register_q3_native_terminal(execution: _Execution) -> None:
    """Keep one final physical read after a stop or normal probe completion."""

    def final_read() -> None:
        ids = ("M-NATIVE-FINAL",)
        if not execution.begin_terminal(ids, "Q3_NATIVE_FINAL"):
            return
        with execution.procedure(ids):
            final = _q3_default_read(
                execution,
                "native_before_cleanup",
                prefix="q3-native",
                policy=execution.definition.stage in _Q3_NATIVE_POLICY_STAGES,
            )
            complete = (
                native_policy_snapshot_complete(
                    final, server=Q3_SERVER, interface="FastEthernet0"
                )
                if execution.definition.stage in _Q3_NATIVE_POLICY_STAGES
                else final.observed
            )
            execution.conclude(
                "M-NATIVE-FINAL",
                Assessment(
                    MeasurementConclusion.SUPPORTED_IN_SAMPLE
                    if complete
                    else MeasurementConclusion.INCONCLUSIVE,
                    facts={
                        "observed": final.observed,
                        "complete": complete,
                        "pools": [dict(item) for item in final.pools],
                        "exclusions": final.raw.get("exclusions"),
                        "excluded_count": final.raw.get("excluded_count"),
                    },
                    causes=(
                        []
                        if complete
                        else [
                            final.cause
                            if not final.observed
                            else "native_policy_final_inventory_incomplete"
                        ]
                    ),
                ),
            )
        execution.finish("Q3_NATIVE_FINAL")

    execution.register_terminal(("M-NATIVE-FINAL",), "Q3_NATIVE_FINAL", final_read)


def _prepare_q3_native_server(
    execution: _Execution,
) -> tuple[Q3ProductContract, DefaultPoolSnapshot, ConfigureServerDhcpPool] | None:
    """Apply the product's server address and admit only its reviewed move."""
    contract = execution.product_contract
    if contract is None:
        execution.stop("q3_native_product_contract_absent")
        return None
    pool_actions = [
        item
        for item in contract.service_plan.actions
        if isinstance(item, ConfigureServerDhcpPool)
    ]
    if (
        len(pool_actions) != 1
        or pool_actions[0].pool_name != Q3_POOL
        or pool_actions[0].host_device_id != "endpoint/q3/default/server/001"
        or pool_actions[0].host_device_name != Q3_SERVER
        or pool_actions[0].interface != "FastEthernet0"
        or pool_actions[0].segment_id != "q3-data"
    ):
        execution.stop("q3_native_requested_pool_ambiguous")
        return None
    state = _Q3FlState()
    policy_mode = execution.definition.stage in _Q3_NATIVE_POLICY_STAGES
    if not _q3fl_snapshot(execution, state, "before_e5", "", policy=policy_mode):
        execution.stop("q3_native_baseline_not_admitted")
        return None
    baseline_admitted = (
        native_policy_probe_baseline_admitted(
            state.snapshots[-1],
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_OBSERVED_NATIVE_DEFAULT_POOL,
            expected_exclusions=(),
        )
        if policy_mode
        else native_pool_probe_baseline_admitted(
            state.snapshots[-1],
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_OBSERVED_NATIVE_DEFAULT_POOL,
        )
    )
    if not baseline_admitted:
        execution.stop("q3_native_baseline_not_admitted")
        return None
    static_plan = d_dhcp_static_only_plan(
        contract.configuration_plan, device_name=Q3_SERVER
    )
    if len(static_plan.actions) != 1:
        execution.stop("q3_native_static_action_ambiguous")
        return None
    configuration_runtime, _ = _d_dhcp_runtimes(execution, contract)
    if not execution.run.transition("experiment:Q3_NATIVE_E5:started"):
        execution.stop("persistence:q3_native_e5_not_announced")
        return None
    with execution.ledger.effect_of("q3-native:product:e5_server_address"):
        configuration = ConfigurationApplicator(configuration_runtime).apply(
            static_plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=_q3_context(contract),
            deployment_manifest=contract.manifest,
        )
    foundation_plan = contract.service_plan.model_copy(
        update={
            "source_configuration_id": static_plan.id,
            "source_configuration_hash": static_plan.semantic_hash,
        },
        deep=True,
    )
    foundations = derive_service_foundational_statuses(foundation_plan, configuration)
    cause = _q3_e5_foundation_cause(
        configuration, foundations, {static_plan.actions[0].id}
    )
    if cause:
        execution.stop(cause)
        return None
    if not _q3fl_snapshot(
        execution,
        state,
        "after_server_address",
        execution.run.boundaries.reviewed_native_default_intervention,
        policy=policy_mode,
    ):
        execution.stop("q3_native_server_address_transition_not_admitted")
        return None
    after_address_admitted = (
        native_policy_probe_baseline_admitted(
            state.snapshots[-1],
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_NATIVE_START_BEFORE,
            expected_exclusions=(),
        )
        if policy_mode
        else native_pool_probe_baseline_admitted(
            state.snapshots[-1],
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=Q3_NATIVE_START_BEFORE,
        )
    )
    if not after_address_admitted:
        execution.stop("q3_native_process_not_disabled_after_e5")
        return None
    return contract, state.snapshots[-1], pool_actions[0]


def _run_q3_native_probe(execution: _Execution) -> None:
    """Bracket one documented native setter inside the governed Q3 fixture."""
    _register_q3_native_terminal(execution)
    if not _diagnostic_start(execution):
        return
    ids = ("M-NATIVE-START",)
    if not execution.selected("NATIVE-start") or not execution.begin(
        ids, "Q3_NATIVE_START"
    ):
        return
    with execution.procedure(ids):
        prepared = _prepare_q3_native_server(execution)
        if prepared is None:
            return
        _, before, pool_action = prepared
        requested_start = pool_action.lease_start
        if not execution.run.transition("experiment:Q3_NATIVE_SETTER:started"):
            execution.stop("persistence:q3_native_setter_not_announced")
            return
        with execution.ledger.effect_of("q3-native:serverPool:setStartIp"):
            with execution.ledger.purpose_of("q3-native:serverPool:setStartIp"):
                probe = execution.probes.probe_native_pool_start(
                    Q3_SERVER, "FastEthernet0", requested_start
                )
        after = _q3_default_read(execution, "after_native_start", prefix="q3-native")
        execution.conclude(
            "M-NATIVE-START",
            assess_native_pool_start_probe(
                before=before,
                probe=probe,
                after=after,
                server=Q3_SERVER,
                interface="FastEthernet0",
                requested_start=requested_start,
            ),
        )
    execution.finish("Q3_NATIVE_START")


def _run_q3_native_size(
    execution: _Execution,
) -> tuple[ConfigureServerDhcpPool, DefaultPoolSnapshot] | None:
    """Measure capacity after a separately proved repeat of episode 1's move."""
    _register_q3_native_terminal(execution)
    if not _diagnostic_start(execution):
        return
    start_ids = ("M-NATIVE-REPEAT-START",)
    if not execution.selected("NATIVE-size") or not execution.begin(
        start_ids, "Q3_NATIVE_REPEAT_START"
    ):
        return
    with execution.procedure(start_ids):
        prepared = _prepare_q3_native_server(execution)
        if prepared is None:
            return
        _, before, pool_action = prepared
        if pool_action.lease_start != Q3_NATIVE_START_AFTER["start"]:
            execution.stop("q3_native_size_intent_differs_from_episode1")
            return
        if not execution.run.transition("experiment:Q3_NATIVE_REPEAT_SETTER:started"):
            execution.stop("persistence:q3_native_repeat_setter_not_announced")
            return
        with execution.ledger.effect_of("q3-native-size:serverPool:setStartIp"):
            with execution.ledger.purpose_of("q3-native-size:serverPool:setStartIp"):
                start_probe = execution.probes.probe_native_pool_start(
                    Q3_SERVER, "FastEthernet0", pool_action.lease_start
                )
        after_start = _q3_default_read(
            execution,
            "after_native_repeat_start",
            prefix="q3-native-size",
            policy=execution.definition.stage in _Q3_NATIVE_POLICY_STAGES,
        )
        execution.conclude(
            "M-NATIVE-REPEAT-START",
            assess_native_pool_repeated_start_probe(
                before=before,
                probe=start_probe,
                after=after_start,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_before=Q3_NATIVE_START_BEFORE,
                expected_after=Q3_NATIVE_START_AFTER,
                evidence_sha256=Q3_NATIVE_START_EVIDENCE_SHA256,
            ),
        )
    execution.finish("Q3_NATIVE_REPEAT_START")
    max_ids = ("M-NATIVE-MAX",)
    repeat = execution.measurement("M-NATIVE-REPEAT-START").conclusion
    if repeat is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.not_run(max_ids, f"repeat_start_not_supported:{repeat.value}")
        execution.stop(f"q3_native_size_repeat_start_not_supported:{repeat.value}")
        return
    if not execution.begin(max_ids, "Q3_NATIVE_MAX"):
        return
    with execution.procedure(max_ids):
        if pool_action.max_users != 1:
            execution.stop("q3_native_size_capacity_differs_from_intent")
            return
        if not execution.run.transition("experiment:Q3_NATIVE_MAX_SETTER:started"):
            execution.stop("persistence:q3_native_max_setter_not_announced")
            return
        with execution.ledger.effect_of("q3-native-size:serverPool:setMaxUsers"):
            with execution.ledger.purpose_of("q3-native-size:serverPool:setMaxUsers"):
                max_probe = execution.probes.probe_native_pool_max(
                    Q3_SERVER, "FastEthernet0", pool_action.max_users
                )
        after_max = _q3_default_read(
            execution,
            "after_native_max",
            prefix="q3-native-size",
            policy=execution.definition.stage in _Q3_NATIVE_POLICY_STAGES,
        )
        execution.conclude(
            "M-NATIVE-MAX",
            assess_native_pool_max_probe(
                before=after_start,
                probe=max_probe,
                after=after_max,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_before=Q3_NATIVE_START_AFTER,
                requested_max=pool_action.max_users,
            ),
        )
    execution.finish("Q3_NATIVE_MAX")
    if (
        execution.measurement("M-NATIVE-MAX").conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    ):
        return pool_action, after_max
    return None


def _run_q3_native_policy(
    execution: _Execution,
) -> tuple[ConfigureServerDhcpPool, DefaultPoolSnapshot] | None:
    """Probe compiled gateway, DNS and exclusions on one disabled native pool."""
    sized = _run_q3_native_size(execution)
    if sized is None:
        if not execution.stopped:
            execution.stop("q3_native_policy_size_not_supported")
        return
    if not execution.selected("NATIVE-policy"):
        return
    pool_action, after_max = sized
    size_row = {
        **dict(Q3_NATIVE_START_AFTER),
        "end": pool_action.lease_end,
        "max": pool_action.max_users,
    }
    if (
        pool_action.max_users != 1
        or pool_action.lease_start != size_row["start"]
        or pool_action.lease_end != size_row["end"]
    ):
        execution.stop("q3_native_policy_intent_differs_from_size_measurement")
        return
    if not native_pool_probe_baseline_admitted(
        after_max,
        server=Q3_SERVER,
        interface="FastEthernet0",
        expected_row=size_row,
    ):
        execution.stop("q3_native_policy_size_readback_not_admitted")
        return
    before_gateway = _q3_default_read(
        execution, "before_native_gateway", prefix="q3-native-policy", policy=True
    )
    if not native_policy_probe_baseline_admitted(
        before_gateway,
        server=Q3_SERVER,
        interface="FastEthernet0",
        expected_row=size_row,
        expected_exclusions=(),
    ):
        execution.stop("q3_native_policy_baseline_not_admitted")
        return
    gateway_row = {**size_row, "gateway": pool_action.gateway}
    ids = ("M-NATIVE-GATEWAY",)
    if not execution.begin(ids, "Q3_NATIVE_GATEWAY"):
        return
    with execution.procedure(ids):
        if not execution.run.transition("experiment:Q3_NATIVE_GATEWAY_SETTER:started"):
            execution.stop("persistence:q3_native_gateway_not_announced")
            return
        with execution.ledger.effect_of("q3-native-policy:serverPool:setDefaultRouter"):
            with execution.ledger.purpose_of(
                "q3-native-policy:serverPool:setDefaultRouter"
            ):
                gateway_probe = execution.probes.probe_native_pool_gateway(
                    Q3_SERVER, "FastEthernet0", pool_action.gateway
                )
        after_gateway = _q3_default_read(
            execution, "after_native_gateway", prefix="q3-native-policy", policy=True
        )
        gateway_result = assess_native_policy_address_probe(
            before=before_gateway,
            probe=gateway_probe,
            after=after_gateway,
            server=Q3_SERVER,
            interface="FastEthernet0",
            field="gateway",
            expected_before=size_row,
            expected_after=gateway_row,
            expected_exclusions=(),
        )
        execution.conclude("M-NATIVE-GATEWAY", gateway_result)
    execution.finish("Q3_NATIVE_GATEWAY")
    if gateway_result.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_policy_gateway_not_supported")
        return

    dns_row = {**gateway_row, "dns": pool_action.dns_server}
    ids = ("M-NATIVE-DNS",)
    if not execution.begin(ids, "Q3_NATIVE_DNS"):
        return
    with execution.procedure(ids):
        if not execution.run.transition("experiment:Q3_NATIVE_DNS_SETTER:started"):
            execution.stop("persistence:q3_native_dns_not_announced")
            return
        with execution.ledger.effect_of("q3-native-policy:serverPool:setDnsServerIp"):
            with execution.ledger.purpose_of(
                "q3-native-policy:serverPool:setDnsServerIp"
            ):
                dns_probe = execution.probes.probe_native_pool_dns(
                    Q3_SERVER, "FastEthernet0", pool_action.dns_server
                )
        after_dns = _q3_default_read(
            execution, "after_native_dns", prefix="q3-native-policy", policy=True
        )
        dns_result = assess_native_policy_address_probe(
            before=after_gateway,
            probe=dns_probe,
            after=after_dns,
            server=Q3_SERVER,
            interface="FastEthernet0",
            field="dns",
            expected_before=gateway_row,
            expected_after=dns_row,
            expected_exclusions=(),
        )
        execution.conclude("M-NATIVE-DNS", dns_result)
    execution.finish("Q3_NATIVE_DNS")
    if dns_result.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_policy_dns_not_supported")
        return

    ranges = [item.model_dump(mode="json") for item in pool_action.excluded_ranges]
    if (
        len(ranges) != 2
        or ranges[0] != {"start": pool_action.gateway, "end": pool_action.gateway}
        or ranges[1] != {"start": pool_action.dns_server, "end": pool_action.dns_server}
    ):
        execution.stop("q3_native_policy_exclusions_differ_from_intent")
        return
    ids = ("M-NATIVE-EXCLUSIONS",)
    if not execution.begin(ids, "Q3_NATIVE_EXCLUSIONS"):
        return
    before_exclusion = after_dns
    completed: list[Assessment] = []
    with execution.procedure(ids):
        for index, wanted in enumerate(ranges, start=1):
            if not execution.run.transition(
                f"experiment:Q3_NATIVE_EXCLUSION_{index}:started"
            ):
                execution.stop("persistence:q3_native_exclusion_not_announced")
                return
            purpose = f"q3-native-policy:exclude:{index}"
            with execution.ledger.effect_of(purpose):
                with execution.ledger.purpose_of(purpose):
                    exclusion_probe = execution.probes.probe_native_exclusion(
                        Q3_SERVER,
                        "FastEthernet0",
                        wanted["start"],
                        wanted["end"],
                        expected_prior=ranges[: index - 1],
                    )
            after_exclusion = _q3_default_read(
                execution,
                f"after_native_exclusion_{index}",
                prefix="q3-native-policy",
                policy=True,
            )
            assessment = assess_native_policy_exclusion_probe(
                before=before_exclusion,
                probe=exclusion_probe,
                after=after_exclusion,
                server=Q3_SERVER,
                interface="FastEthernet0",
                expected_row=dns_row,
                expected_before=ranges[: index - 1],
                added=wanted,
            )
            completed.append(assessment)
            if assessment.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
                execution.conclude("M-NATIVE-EXCLUSIONS", assessment)
                execution.stop(f"q3_native_policy_exclusion_{index}_not_supported")
                break
            before_exclusion = after_exclusion
        else:
            execution.conclude(
                "M-NATIVE-EXCLUSIONS",
                Assessment(
                    MeasurementConclusion.SUPPORTED_IN_SAMPLE,
                    facts={
                        **completed[-1].facts,
                        "steps": [item.facts for item in completed],
                        "compiled_exclusions": ranges,
                    },
                    limitations=[
                        "stored_policy_is_not_serving_or_reapplication_evidence"
                    ],
                ),
            )
    execution.finish("Q3_NATIVE_EXCLUSIONS")
    if (
        execution.measurement("M-NATIVE-EXCLUSIONS").conclusion
        is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    ):
        return pool_action, before_exclusion
    return None


def _run_q3_native_stability(execution: _Execution) -> None:
    """Reapply E5 and compare the complete disabled native policy."""
    prepared = _run_q3_native_policy(execution)
    if prepared is None:
        if not execution.stopped:
            execution.stop("q3_native_stability_policy_not_supported")
        return
    if not execution.selected("NATIVE-stability"):
        return
    pool_action, before = prepared
    expected_row = {
        **dict(Q3_NATIVE_START_AFTER),
        "end": pool_action.lease_end,
        "max": pool_action.max_users,
        "gateway": pool_action.gateway,
        "dns": pool_action.dns_server,
    }
    exclusions = [item.model_dump(mode="json") for item in pool_action.excluded_ranges]
    if not native_policy_probe_baseline_admitted(
        before,
        server=Q3_SERVER,
        interface="FastEthernet0",
        expected_row=expected_row,
        expected_exclusions=exclusions,
    ):
        execution.stop("q3_native_stability_precondition_unobserved")
        return
    contract = execution.product_contract
    if contract is None:
        execution.stop("q3_native_stability_product_contract_absent")
        return
    static_plan = d_dhcp_static_only_plan(
        contract.configuration_plan, device_name=Q3_SERVER
    )
    if len(static_plan.actions) != 1:
        execution.stop("q3_native_stability_static_action_ambiguous")
        return
    ids = ("M-NATIVE-STABILITY",)
    if not execution.begin(ids, "Q3_NATIVE_STABILITY"):
        return
    with execution.procedure(ids):
        if not execution.run.transition("experiment:Q3_NATIVE_STABILITY_E5:started"):
            execution.stop("persistence:q3_native_stability_e5_not_announced")
            return
        configuration_runtime, _ = _d_dhcp_runtimes(execution, contract)
        e5_start = len(execution.ledger.entries)
        with execution.ledger.effect_of(
            "q3-native-stability:product:e5_server_address"
        ):
            result = ConfigurationApplicator(configuration_runtime).apply(
                static_plan,
                actual_source_topology_hash=contract.manifest.physical_topology_hash,
                capabilities=contract.device_capabilities,
                runtime_context=_q3_context(contract),
                deployment_manifest=contract.manifest,
            )
        e5_operations = execution.ledger.entries[e5_start:]
        unknown_dispatches = [
            item.seq
            for item in e5_operations
            if item.dispatch == DispatchFact.ACCEPTANCE_UNKNOWN.value
        ]
        foundations = _q3fl_foundations(contract, static_plan, result)
        cause = _q3_e5_foundation_cause(
            result, foundations, {static_plan.actions[0].id}
        )
        if unknown_dispatches:
            cause = "outcome_unknown:q3_native_stability_e5_dispatch"
        after = _q3_default_read(
            execution,
            "after_native_e5_reapplication",
            prefix="q3-native-stability",
            policy=True,
        )
        after_exact = native_policy_probe_baseline_admitted(
            after,
            server=Q3_SERVER,
            interface="FastEthernet0",
            expected_row=expected_row,
            expected_exclusions=exclusions,
        )
        facts = {
            "before": dict(before.raw),
            "after": dict(after.raw),
            "product_action_results": [
                item.model_dump(mode="json") for item in result.action_results
            ],
            "product_verification_results": [
                item.model_dump(mode="json") for item in result.verification_results
            ],
            "e5_operations": [item.model_dump(mode="json") for item in e5_operations],
            "unknown_dispatch_seqs": unknown_dispatches,
        }
        conclusion = (
            MeasurementConclusion.INCONCLUSIVE
            if cause
            or not after.observed
            or not native_policy_exclusion_inventory_complete(after)
            else MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if after_exact
            else MeasurementConclusion.CONTRADICTED
        )
        assessment = Assessment(
            conclusion,
            facts=facts,
            causes=(
                [cause]
                if cause
                else [f"native_policy_after_unobserved:{after.cause}"]
                if not after.observed
                else ["native_policy_after_exclusions_incomplete"]
                if not native_policy_exclusion_inventory_complete(after)
                else []
                if after_exact
                else ["native_policy_changed_or_incomplete_after_e5_reapplication"]
            ),
            limitations=[
                "e5_fire_and_forget_does_not_prove_setter_success",
                "unchanged_state_does_not_prove_native_setter_idempotence",
                "restart_reload_not_measured",
            ],
            outcome_unknown=cause.startswith("outcome_unknown"),
        )
        execution.conclude("M-NATIVE-STABILITY", assessment)
    execution.finish("Q3_NATIVE_STABILITY")
    if assessment.conclusion is not MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.stop("q3_native_stability_not_supported")


# -- Q3-FL: the versioned DHCP qualification profile ------------------------------

Q3_FL_DEFAULT_PURPOSE = "q3-fl:native_default"
_Q3FL_CLIENT_MODE = "e5:client_dhcp_mode:configurePcIp_dhcp_flag"
_Q3FL_SERVER_SETUP = "e6:configure_pool_and_enable"
_Q3FL_TERMINAL = "acquisitions_repeat_and_timing"
_Q3FL_DHCP_IDS = (
    "M-DHCP-2",
    "M-DHCP-6",
    "M-DHCP-6-CAP",
    "M-DHCP-6-REPEAT",
    "M-DHCP-6-TIME",
)


@dataclass(frozen=True)
class _Q3FlClient:
    """One client of the compiled DHCP service, by its product identities."""

    device_id: str
    name: str
    interface: str
    acquisition_id: str
    lease_expectation_id: str


@dataclass
class _Q3FlState:
    """What one Q3-FL run has established, carried between its procedures."""

    clients: tuple[_Q3FlClient, ...] = ()
    native_pools: tuple[str, ...] = ()
    readings: list[NativeDefaultReading] = field(default_factory=list)
    snapshots: list[DefaultPoolSnapshot] = field(default_factory=list)
    sequence: NativeDefaultSequenceAssessment | None = None
    scans: list[tuple[str, dict[str, LeaseScan]]] = field(default_factory=list)
    client_reads: list[tuple[str, dict[str, ClientReading]]] = field(
        default_factory=list
    )
    foundations: dict[str, ActionExecutionStatus] = field(default_factory=dict)
    admitted: tuple[str, ...] = ()
    mode_verified: tuple[str, ...] = ()
    gate_rows: list[dict[str, object]] = field(default_factory=list)
    rewrites: list[str] = field(default_factory=list)
    server_application: ServiceApplicationResult | None = None
    server_facts: dict[str, Any] = field(default_factory=dict)
    acquisitions: dict[str, dict[str, Any]] = field(default_factory=dict)
    repeat: dict[str, Any] = field(default_factory=dict)
    timing_labels: list[str] = field(default_factory=list)

    def reading(self, label: str) -> dict[str, ClientReading]:
        """Return one labelled client reading, or an empty mapping."""
        return next((value for name, value in self.client_reads if name == label), {})

    def latest_scans(self) -> dict[str, LeaseScan]:
        """Return the most recent scan set, or none."""
        return self.scans[-1][1] if self.scans else {}


def _q3fl_clients(contract: Q3ProductContract) -> tuple[_Q3FlClient, ...]:
    """Return every compiled acquisition's client, in plan order."""
    leases = {
        item.action_id: item.id
        for item in contract.service_plan.verification_expectations
        if item.kind is ServiceVerificationKind.DHCP_LEASE
    }
    return tuple(
        _Q3FlClient(
            device_id=item.host_device_id,
            name=item.host_device_name,
            interface=item.interface,
            acquisition_id=item.id,
            lease_expectation_id=leases.get(item.id, ""),
        )
        for item in contract.service_plan.actions
        if isinstance(item, AcquireDhcpLease)
    )


def _q3fl_pools(execution: _Execution, state: _Q3FlState) -> list[tuple[str, int]]:
    """Return the explicit index window of every pool a scan names."""
    capacity = execution.definition.dhcp_pool_capacity
    return [
        (Q3_POOL, capacity + Q3_FL_INTENDED_EXTRA_INDEXES),
        *((name, Q3_FL_NATIVE_SCAN_INDEXES) for name in state.native_pools),
    ]


def _q3fl_scan(
    execution: _Execution, state: _Q3FlState, label: str
) -> dict[str, LeaseScan]:
    """Take one calibrated scan of every pool and keep it under its label."""
    pools = _q3fl_pools(execution, state)
    names = [name for name, _window in pools]
    if not execution.ledger.can_afford(1):
        scans = unobserved_scans(names, "lease_scan_not_affordable")
    else:
        try:
            with execution.ledger.purpose_of(f"q3-fl:lease_scan:{label}"):
                reading = execution.probes.read_dhcp_lease_calibration(
                    Q3_SERVER, "FastEthernet0", pools
                )
        except OperationRefused as exc:
            scans = unobserved_scans(names, f"lease_scan_refused:{exc.reason}")
        else:
            payload = reading.payload if reading.observed else {}
            subject_ok = (
                reading.observed
                and payload.get("device") == Q3_SERVER
                and payload.get("interface") == "FastEthernet0"
                and payload.get("found") is True
                and payload.get("process_found") is True
                and not payload.get("error")
            )
            scans = (
                scans_by_pool(payload, names)
                if subject_ok
                else unobserved_scans(
                    names,
                    reading.cause if not reading.observed else "scan_subject_invalid",
                )
            )
    state.scans.append((label, scans))
    return scans


def _q3fl_read_clients(
    execution: _Execution, state: _Q3FlState, label: str
) -> dict[str, ClientReading]:
    """Take one typed reading of every client and keep it under its label."""
    names = [item.name for item in state.clients]
    if not execution.ledger.can_afford(1):
        readings = {
            name: ClientReading(name, False, cause="client_read_not_affordable")
            for name in names
        }
    else:
        try:
            with execution.ledger.purpose_of(f"q3-fl:clients:{label}"):
                reading = execution.probes.read_dhcp_clients(
                    [(item.name, item.interface) for item in state.clients]
                )
        except OperationRefused as exc:
            readings = {
                name: ClientReading(
                    name, False, cause=f"client_read_refused:{exc.reason}"
                )
                for name in names
            }
        else:
            readings = (
                client_readings(reading.payload, names)
                if reading.observed
                else {
                    name: ClientReading(name, False, cause=_bounded(reading.cause))
                    for name in names
                }
            )
    state.client_reads.append((label, readings))
    return readings


def _q3fl_sequence(execution: _Execution, state: _Q3FlState) -> bool:
    """Re-decide the whole native-default sequence under the versioned policy."""
    boundaries = execution.run.boundaries
    transitions = boundaries.native_default_transitions
    state.sequence = assess_native_default_sequence(
        state.readings,
        policy=Q3_FL_NATIVE_DEFAULT_POLICY,
        model="Server-PT",
        backend_version=execution.record.environment.observed_build,
        interface="FastEthernet0",
        reviewed_intervention=boundaries.reviewed_native_default_intervention,
        admitted=(
            transitions(execution.record.environment.observed_build)
            if callable(transitions)
            else ()
        ),
    )
    return state.sequence.permits_continuation


def _q3fl_snapshot(
    execution: _Execution,
    state: _Q3FlState,
    label: str,
    intervention: str,
    *,
    policy: bool = False,
) -> bool:
    """Take one native-default reading after `intervention` and re-decide."""
    snapshot = _q3_default_read(
        execution, label, prefix=Q3_FL_DEFAULT_PURPOSE, policy=policy
    )
    state.snapshots.append(snapshot)
    state.readings.append(
        NativeDefaultReading(
            label=label,
            observed=snapshot.observed,
            rows=tuple(dict(item) for item in snapshot.pools),
            intervention=intervention,
            cause=snapshot.cause,
        )
    )
    return _q3fl_sequence(execution, state)


def _q3fl_policy_cause(state: _Q3FlState) -> str:
    """Return the first interval the policy refused, or ""."""
    if state.sequence is None or state.sequence.permits_continuation:
        return ""
    return "q3fl_native_default_policy:" + state.sequence.causes[0]


def _q3fl_sequence_facts(state: _Q3FlState) -> dict[str, Any]:
    """Return every interval the policy decided, with its assessment."""
    sequence = state.sequence
    if sequence is None:
        return {"policy": Q3_FL_NATIVE_DEFAULT_POLICY, "intervals": []}
    return {
        "policy": sequence.policy,
        "permits_continuation": sequence.permits_continuation,
        "causes": list(sequence.causes),
        "limitations": list(sequence.limitations),
        "authorizes_allocation": sequence.authorizes_allocation,
        "intervals": [
            {
                "before": item.before_label,
                "after": item.after_label,
                "intervention": item.intervention,
                "classification": item.assessment.classification,
                "changed_fields": list(item.assessment.changed_fields),
                "assessment_causes": list(item.assessment.causes),
                "matched_evidence": item.assessment.matched_evidence,
                "decision": item.decision,
                "cause": item.cause,
            }
            for item in sequence.intervals
        ],
    }


def _q3fl_foundations(
    contract: Q3ProductContract,
    plan: ConfigurationPlan,
    result: ConfigurationApplicationResult,
) -> dict[str, ActionExecutionStatus]:
    """Derive the foundations one E5 projection established, by its identity."""
    rebound = contract.service_plan.model_copy(
        update={
            "source_configuration_id": plan.id,
            "source_configuration_hash": plan.semantic_hash,
        },
        deep=True,
    )
    return derive_service_foundational_statuses(rebound, result)


def _q3fl_rows(result: Any) -> dict[str, Any]:
    """Return one application result's rows exactly as the product reported them."""
    if result is None:
        return {}
    return {
        "status": getattr(getattr(result, "status", None), "value", ""),
        "preflight_errors": list(getattr(result, "preflight_errors", []) or []),
        "action_results": [
            item.model_dump(mode="json") for item in result.action_results
        ],
        "verification_results": [
            item.model_dump(mode="json") for item in result.verification_results
        ],
    }


def _q3fl_request(result: ServiceApplicationResult, action_id: str) -> str:
    """Classify one acquisition's dispatch from its own canonical row.

    This is the Q3-FL decision predicate the brief records. The product keeps
    a void `dhcpRun` unsettled for product dependents until a read-back
    verifies it, and nothing here changes that. What this profile needs is
    narrower: whether the claim script's single evaluation is known. A row
    that reproduces its canonical decision, was accepted and correlated,
    reported `attempted=true` and carried no call error is a known dispatch.
    `attempted=false` is a known non-dispatch with its skip reason. A
    preflight refusal dispatched nothing. Anything else is an unknown outcome,
    which stops every later effect and is never retried.
    """
    row = next(
        (item for item in result.action_results if item.action_id == action_id), None
    )
    if row is None:
        if result.preflight_errors and not result.action_results:
            return "not_dispatched:preflight:" + _bounded(result.preflight_errors[0])
        return "outcome_unknown:acquisition_row_absent"
    snapshot = row.received_mutation
    if snapshot is None or snapshot.action_id != action_id:
        return "outcome_unknown:acquisition_snapshot_absent"
    decision = decide_mutation(snapshot)
    if not (
        row.status is decision.status
        and row.failure_code is decision.failure_code
        and row.disposition is decision.disposition
        and row.dispatch is snapshot.dispatch
        and row.result is snapshot.result
        and row.attempted is snapshot.attempted
        and row.cause == decision.cause
    ):
        return "outcome_unknown:acquisition_row_incoherent"
    if snapshot.attempted is False and not snapshot.call_error:
        return "not_dispatched:" + _bounded(row.cause or snapshot.cause or "skipped")
    if (
        row.dispatch is not DispatchFact.ACCEPTED
        or row.result is not ResultFact.CORRELATED
        or snapshot.attempted is not True
        or bool(snapshot.call_error)
    ):
        return "outcome_unknown:acquisition_dispatch"
    return "dispatched"


def _run_q3_fastloop(execution: _Execution) -> None:
    """Run the versioned Q3-FL profile: server, forwarding, clients, tables.

    The E5 bootstrap is split by subject so the native-default transition falls
    inside its one reviewed context, and client DHCP mode is activated while
    the server's process is still disabled so a background discover finds no
    server. Every later reading is a stability check under the versioned
    policy. Acquisitions follow an admitted forwarding decision, one typed
    request per client under its claim, each bracketed by readings and scans.
    """
    state = _Q3FlState()
    execution.register_terminal(
        ("M-DHCP-1-FINAL",), "Q3FL_FINAL", lambda: _q3fl_final(execution, state)
    )
    if not _diagnostic_start(execution):
        return
    contract = execution.product_contract
    if contract is None:  # pragma: no cover - admission composes it
        execution.stop("q3fl_product_contract_absent")
        return
    state.clients = _q3fl_clients(contract)
    if not state.clients or any(
        not item.lease_expectation_id for item in state.clients
    ):
        execution.stop("q3fl_contract_has_no_attributable_client")
        return
    configuration_runtime, service_runtime = _d_dhcp_runtimes(execution, contract)
    context = _q3_context(contract)
    execution.record.limitations.extend(
        [
            "q3fl_private_candidate_capabilities:no_public_catalog_mutation",
            "q3fl_physical_fixture_owned_by_runner:no_switch_action_applied",
            f"q3fl_native_default_policy:{Q3_FL_NATIVE_DEFAULT_POLICY}",
            "q3fl_dhcp_lease_never_promoted_to_verified:r_evt_05_fallback_active",
        ]
    )
    ids = ("M-DHCP-1", "M-DHCP-4", "M-DHCP-5")
    if execution.selected("Q3FL-core") and execution.begin(ids, "Q3FL_SERVER"):
        with execution.procedure(ids):
            _q3fl_server(
                execution,
                state,
                contract,
                configuration_runtime,
                service_runtime,
                context,
            )
        execution.finish("Q3FL_SERVER")
    ids = tuple(
        item
        for item in _Q3FL_DHCP_IDS
        if any(row.experiment_id == item for row in execution.record.measurements)
        and execution.measurement(item).status is MeasurementStatus.NOT_RUN
    )
    if ids and execution.selected("Q3FL-core") and execution.begin(ids, "Q3FL_DHCP"):
        with execution.procedure(ids):
            _q3fl_dhcp(execution, state, contract, service_runtime, context, ids)
        execution.finish("Q3FL_DHCP")


def _q3fl_server(
    execution: _Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    configuration_runtime,
    service_runtime,
    context: ConfigurationRuntimeContext,
) -> None:
    """Baseline, the server's address, forwarding, client mode, then the pool."""
    ledger = execution.ledger
    start = len(ledger.entries)
    with ledger.purpose_of(_q3_default_purpose("before_e5", Q3_FL_DEFAULT_PURPOSE)):
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
    first = _q3_default_observed(
        execution,
        "before_e5",
        baseline,
        operation_seq=_counted_seq(ledger, start),
        prefix=Q3_FL_DEFAULT_PURPOSE,
    )
    state.readings.append(
        NativeDefaultReading(
            label="before_e5",
            observed=first.observed,
            rows=tuple(dict(item) for item in first.pools),
            cause=first.cause,
        )
    )
    state.native_pools = tuple(str(item["name"]) for item in first.pools)
    before = _q3fl_read_clients(execution, state, "baseline")
    _q3fl_scan(execution, state, "baseline")
    causes: list[str] = []
    if not admission.admitted:
        causes.extend(["initial_dhcp_server_state_not_admissible", *admission.causes])
    for name, reading in before.items():
        if not reading.observed:
            causes.append(f"client_not_readable:{name}:{reading.cause}")
        elif reading.mode is not False:
            causes.append(f"client_dhcp_mode_not_off:{name}")
    state.server_facts["baseline_admission"] = {
        "admitted": admission.admitted,
        "kind": admission.kind,
        "causes": list(admission.causes),
    }
    cause = ""
    if causes:
        cause = "q3fl_baseline_not_established:" + causes[0]
        state.server_facts["baseline_causes"] = causes
    else:
        execution.establish(
            DiagnosticPrecondition.INVENTORY_COHERENT,
            DiagnosticPrecondition.PROCESS_DISABLED_VERIFIED,
        )
        cause = _q3fl_server_address(
            execution, state, contract, configuration_runtime, context
        )
    if not cause:
        _q3fl_forwarding(execution, state, contract)
        if state.admitted:
            cause = _q3fl_client_mode(
                execution, state, contract, configuration_runtime, context
            )
    if not cause:
        cause = _q3fl_server_setup(execution, state, contract, service_runtime, context)
    if cause:
        execution.stop(cause)
    _q3fl_conclude_server(execution, state, cause)


def _q3fl_server_address(
    execution: _Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    configuration_runtime,
    context: ConfigurationRuntimeContext,
) -> str:
    """Apply the server's static address alone, inside the reviewed context."""
    static_plan = d_dhcp_static_only_plan(
        contract.configuration_plan, device_name=Q3_SERVER
    )
    if not execution.run.transition("experiment:Q3FL_SERVER:e5_server_address"):
        return "persistence:q3fl_e5_server_address_not_announced"
    with execution.ledger.effect_of("q3-fl:product:e5_server_address"):
        result = ConfigurationApplicator(configuration_runtime).apply(
            static_plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
        )
    foundations = _q3fl_foundations(contract, static_plan, result)
    state.foundations.update(foundations)
    state.server_facts["e5_server_address"] = {
        "plan_id": static_plan.id,
        "action_results": [
            item.model_dump(mode="json") for item in result.action_results
        ],
        "verification_results": [
            item.model_dump(mode="json") for item in result.verification_results
        ],
    }
    cause = _q3_e5_foundation_cause(
        result, foundations, {item.id for item in static_plan.actions}
    )
    reviewed = execution.run.boundaries.reviewed_native_default_intervention
    permitted = _q3fl_snapshot(execution, state, "after_server_address", reviewed)
    if cause:
        return cause
    if not permitted:
        return _q3fl_policy_cause(state)
    execution.establish(DiagnosticPrecondition.SERVER_ADDRESSING)
    return ""


def _q3fl_forwarding(
    execution: _Execution, state: _Q3FlState, contract: Q3ProductContract
) -> None:
    """Decide every client's forwarding through the product gate, before activity."""
    actions, rewrites = q3_fastloop_fixture_placements(
        contract.configuration_plan, vlan_id=Q3_FL_FIXTURE_ACCESS_VLAN
    )
    state.rewrites.extend(item.as_text() for item in rewrites)
    wanted = {item.lease_expectation_id for item in state.clients}
    plan = derive_access_readiness_plan(
        configuration_actions=actions,
        verification_expectations=[
            item
            for item in contract.service_plan.verification_expectations
            if item.id in wanted
        ],
        request_kinds=DHCP_ACQUISITION_KINDS,
    )
    gate = ServiceAccessReadinessGate(
        plan,
        execution.run.boundaries.configuration_runtime(execution.bound),
        clock=execution.bound.clock,
    )
    gate.begin_invocation()
    admitted: list[str] = []
    verdicts: dict[str, dict[str, object]] = {}
    with execution.ledger.purpose_of("q3-fl:forwarding"):
        for client in state.clients:
            verdict = gate.decide(client.lease_expectation_id)
            verdicts[client.name] = (
                verdict.as_row() if verdict is not None else {"admitted": False}
            )
            if verdict is not None and verdict.admitted:
                admitted.append(client.name)
    state.gate_rows = gate.rows()
    state.admitted = tuple(admitted)
    state.server_facts["forwarding"] = {
        "verdicts": verdicts,
        "groups": state.gate_rows,
        "unplaced": [item.expectation_id for item in plan.unplaced],
    }
    if admitted:
        execution.establish(DiagnosticPrecondition.FORWARDING_OBSERVED)


def _q3fl_client_mode(
    execution: _Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    configuration_runtime,
    context: ConfigurationRuntimeContext,
) -> str:
    """Activate DHCP mode on admitted clients while the server is still off."""
    plan = q3_fastloop_client_mode_plan(
        contract.configuration_plan, device_names=state.admitted
    )
    if not execution.run.transition("experiment:Q3FL_SERVER:e5_client_mode"):
        return "persistence:q3fl_e5_client_mode_not_announced"
    with execution.ledger.effect_of("q3-fl:product:e5_client_mode"):
        result = ConfigurationApplicator(configuration_runtime).apply(
            plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            capabilities=contract.device_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
        )
    foundations = _q3fl_foundations(contract, plan, result)
    state.foundations.update(foundations)
    state.server_facts["e5_client_mode"] = {
        "plan_id": plan.id,
        "clients": list(state.admitted),
        "action_results": [
            item.model_dump(mode="json") for item in result.action_results
        ],
        "verification_results": [
            item.model_dump(mode="json") for item in result.verification_results
        ],
    }
    cause = _q3_e5_foundation_cause(
        result, foundations, {item.id for item in plan.actions}
    )
    after = _q3fl_read_clients(execution, state, "after_client_mode")
    permitted = _q3fl_snapshot(execution, state, "after_client_mode", _Q3FL_CLIENT_MODE)
    _q3fl_scan(execution, state, "after_client_mode")
    state.mode_verified = tuple(
        name
        for name in state.admitted
        if after.get(name) is not None
        and after[name].observed
        and after[name].mode is True
    )
    if cause:
        return cause
    if not permitted:
        return _q3fl_policy_cause(state)
    if state.mode_verified:
        execution.establish(DiagnosticPrecondition.CLIENT_DHCP_MODE)
    return ""


def _q3fl_server_setup(
    execution: _Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    service_runtime,
    context: ConfigurationRuntimeContext,
) -> str:
    """Write the intended pool and enable the process, once, then read."""
    plan, rewrites = q3_fastloop_service_plan(contract.service_plan)
    state.rewrites.extend(item.as_text() for item in rewrites)
    if not execution.run.transition("experiment:Q3FL_SERVER:e6_server"):
        return "persistence:q3fl_e6_server_not_announced"
    with execution.ledger.effect_of("q3-fl:product:e6_server"):
        result = ServiceApplicator(service_runtime).apply(
            plan,
            actual_source_topology_hash=contract.manifest.physical_topology_hash,
            actual_source_configuration_hash=(
                contract.service_plan.source_configuration_hash
            ),
            foundational_statuses=state.foundations,
            capabilities=contract.service_capabilities,
            runtime_context=context,
            deployment_manifest=contract.manifest,
            operational_readiness=DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
        )
    state.server_application = result
    state.server_facts["e6_server"] = {"plan_id": plan.id, **_q3fl_rows(result)}
    cause = _q3_service_result_cause(
        result,
        {item.id for item in plan.actions},
        expected_verification_ids={item.id for item in plan.verification_expectations},
    ) or _d_dhcp_readback_cause(result)
    permitted = _q3fl_snapshot(
        execution, state, "after_server_setup", _Q3FL_SERVER_SETUP
    )
    _q3fl_scan(execution, state, "empty_after_enable")
    if cause:
        return cause
    if not permitted:
        return _q3fl_policy_cause(state)
    execution.establish(
        DiagnosticPrecondition.POOL_CONFIGURED,
        DiagnosticPrecondition.PROCESS_ENABLED_VERIFIED,
        DiagnosticPrecondition.NATIVE_DEFAULT_PERMITS,
    )
    return ""


def _q3fl_conclude_server(execution: _Execution, state: _Q3FlState, cause: str) -> None:
    """Conclude M-DHCP-1, M-DHCP-4 and M-DHCP-5 from what the run observed."""
    sequence = _q3fl_sequence_facts(state)
    drift = state.sequence is not None and any(
        item.decision == INTERVAL_REFUSED
        and item.assessment.classification == UNEXPLAINED_DRIFT
        for item in state.sequence.intervals
    )
    server_facts = {
        **state.server_facts,
        "native_default": _native_default_facts(execution),
        "native_default_sequence": sequence,
        "projection_rewrites": list(state.rewrites),
        "coexistence": _q3fl_coexistence(execution),
        "scans": [
            {
                "label": label,
                "pools": {name: scan.as_facts() for name, scan in scans.items()},
            }
            for label, scans in state.scans
        ],
    }
    established = {
        DiagnosticPrecondition.SERVER_ADDRESSING,
        DiagnosticPrecondition.POOL_CONFIGURED,
        DiagnosticPrecondition.PROCESS_ENABLED_VERIFIED,
        DiagnosticPrecondition.NATIVE_DEFAULT_PERMITS,
    } <= execution.established
    if drift:
        conclusion = MeasurementConclusion.CONTRADICTED
    elif established and not cause:
        conclusion = MeasurementConclusion.SUPPORTED_IN_SAMPLE
    else:
        conclusion = MeasurementConclusion.INCONCLUSIVE
    execution.conclude(
        "M-DHCP-1",
        Assessment(
            conclusion,
            facts=server_facts,
            causes=[cause] if cause else [],
            limitations=[
                "no_explicit_setter_targeted_the_native_default",
                "enabling_the_process_is_process_wide",
                "stored_pool_configuration_is_not_service",
            ],
        ),
    )
    readings = _q3fl_reading_series(state)
    execution.conclude("M-DHCP-4", _q3fl_mac_assessment(state, readings))
    execution.conclude("M-DHCP-5", _q3fl_mode_assessment(state, readings))


def _q3fl_coexistence(execution: _Execution) -> dict[str, Any]:
    """State how the intended pool sits beside the native default, as fact."""
    entries = execution.record.native_default_pool
    last = entries[-1] if entries else None
    if last is None or not last.observed:
        return {"stated": False, "cause": "no_observed_reading"}
    raw_rows = last.raw.get("pools") if isinstance(last.raw, Mapping) else None
    intended = next(
        (
            row
            for row in (raw_rows if isinstance(raw_rows, list) else [])
            if isinstance(row, Mapping) and row.get("name") == Q3_POOL
        ),
        None,
    )
    native = next(iter(last.pools), None)
    if intended is None or native is None:
        return {"stated": False, "cause": "intended_or_native_row_absent"}
    coexistence = assess_intended_pool_coexistence(native=native, intended=intended)
    return {
        "stated": True,
        "reading": last.label,
        "native_pool": coexistence.native_pool_name,
        "intended_pool": coexistence.intended_pool_name,
        "shares_subnet": coexistence.shares_subnet,
        "ranges_overlap": coexistence.ranges_overlap,
        "overlapping_addresses": list(coexistence.overlapping_addresses),
        "causes": list(coexistence.causes),
        "limitations": list(coexistence.limitations),
    }


def _q3fl_mac_assessment(
    state: _Q3FlState, readings: list[dict[str, Any]]
) -> Assessment:
    """Judge the MAC reader: typed text, stable across every reading taken."""
    macs: dict[str, set[str]] = {}
    unread: list[str] = []
    for _label, values in state.client_reads:
        for name, item in values.items():
            if item.observed:
                macs.setdefault(name, set()).add(item.mac)
            else:
                unread.append(name)
    causes = []
    for client in state.clients:
        seen = macs.get(client.name, set())
        if not seen:
            causes.append(f"mac_never_read:{client.name}")
        elif len(seen) > 1:
            causes.append(f"mac_changed_between_readings:{client.name}")
        elif not all(is_dotted_mac(item) for item in seen):
            causes.append(f"mac_text_not_dotted_hex:{client.name}")
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE
        if causes
        else MeasurementConclusion.SUPPORTED_IN_SAMPLE,
        facts={"readings": readings},
        causes=causes,
        limitations=[
            "native_mac_representation_sample_only",
            "no_equivalence_inferred",
        ],
    )


def _q3fl_mode_assessment(
    state: _Q3FlState, readings: list[dict[str, Any]]
) -> Assessment:
    """Judge the mode reader: off before, on after activation, boolean always."""
    baseline = state.reading("baseline")
    after = state.reading("after_client_mode")
    causes: list[str] = []
    for client in state.clients:
        first = baseline.get(client.name)
        if first is None or not first.observed:
            causes.append(f"baseline_mode_unread:{client.name}")
        elif first.mode is not False:
            causes.append(f"baseline_mode_not_off:{client.name}")
        if client.name not in state.admitted:
            causes.append(f"forwarding_not_admitted:{client.name}")
            continue
        second = after.get(client.name)
        if second is None or not second.observed:
            causes.append(f"activated_mode_unread:{client.name}")
        elif second.mode is not True:
            causes.append(f"activated_mode_not_on:{client.name}")
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE
        if causes
        else MeasurementConclusion.SUPPORTED_IN_SAMPLE,
        facts={
            "readings": readings,
            "forwarding": state.server_facts.get("forwarding", {}),
            "admitted": list(state.admitted),
            "mode_verified": list(state.mode_verified),
        },
        causes=causes,
        limitations=[
            "native_mode_reader_sample_only",
            "mode_activation_is_potentially_effectful",
            "readiness_is_a_property_of_the_measured_ports_at_that_moment",
        ],
    )


def _q3fl_dhcp(
    execution: _Execution,
    state: _Q3FlState,
    contract: Q3ProductContract,
    service_runtime,
    context: ConfigurationRuntimeContext,
    ids: tuple[str, ...],
) -> None:
    """Acquire per admitted client, repeat once, time, then conclude the tables."""
    ledger = execution.ledger
    sleep = execution.run.boundaries.sleep
    _q3fl_read_clients(execution, state, "background_1")
    ledger.wait(Q3_FL_BACKGROUND_INTERVAL_SECONDS, sleep)
    _q3fl_read_clients(execution, state, "background_2")
    nonces = {
        reference: f"{execution.nonce}:{index}"
        for index, reference in enumerate(
            contract.service_plan.operation_nonce_refs(), start=1
        )
    }
    bound_plan = contract.service_plan.with_operation_nonces(nonces)
    acquisitions = {
        item.host_device_id: item
        for item in bound_plan.actions
        if isinstance(item, AcquireDhcpLease)
    }
    retained = (
        state.server_application.action_results
        if state.server_application is not None
        else ()
    )
    for client in state.clients:
        if client.name not in state.mode_verified:
            state.acquisitions[client.name] = {
                "request": "not_dispatched:mode_or_forwarding_not_established",
            }
            continue
        if execution.stopped:
            state.acquisitions[client.name] = {
                "request": "not_dispatched:stopped:" + execution.record.primary_failure,
            }
            continue
        before_label = f"before:{client.name}"
        before = _q3fl_read_clients(execution, state, before_label)
        prior_label = state.scans[-1][0] if state.scans else ""
        plan, rewrites = q3_fastloop_service_plan(
            bound_plan, client_device_id=client.device_id
        )
        state.rewrites.extend(item.as_text() for item in rewrites)
        if not execution.run.transition(f"experiment:Q3FL_DHCP:acquire:{client.name}"):
            execution.stop("persistence:q3fl_acquisition_not_announced")
            break
        with ledger.effect_of(f"q3-fl:product:acquire:{client.name}"):
            result = ServiceApplicator(service_runtime).apply(
                plan,
                actual_source_topology_hash=contract.manifest.physical_topology_hash,
                actual_source_configuration_hash=(
                    contract.service_plan.source_configuration_hash
                ),
                foundational_statuses=state.foundations,
                capabilities=contract.service_capabilities,
                runtime_context=context,
                deployment_manifest=contract.manifest,
                operational_readiness=DIAGNOSTIC_TAKES_ITS_OWN_FORWARDING_EVIDENCE,
                retained_action_results=retained,
            )
        request = _q3fl_request(result, client.acquisition_id)
        entry: dict[str, Any] = {
            "request": request,
            "plan_id": plan.id,
            "before_label": before_label,
            "prior_scan_label": prior_label,
            "product": _q3fl_rows(result),
        }
        state.acquisitions[client.name] = entry
        if request.startswith("outcome_unknown"):
            # Never retried. Reads may still say what happened, but no later
            # effect of this run is admitted after an unknown outcome.
            execution.stop(f"outcome_unknown:q3fl_acquisition:{client.name}:{request}")
        before_reading = before.get(client.name)
        settle_labels: list[str] = []
        for index in range(1, Q3_FL_SETTLE_READS + 1):
            ledger.wait(Q3_FL_SETTLE_INTERVAL_SECONDS, sleep)
            label = f"settle:{client.name}:{index}"
            settle_labels.append(label)
            current = _q3fl_read_clients(execution, state, label).get(client.name)
            if (
                current is not None
                and current.observed
                and before_reading is not None
                and before_reading.observed
                and current.ipv4 != before_reading.ipv4
            ):
                break
        entry["settle_labels"] = settle_labels
        entry["after_label"] = settle_labels[-1] if settle_labels else before_label
        entry["scan_label"] = f"after:{client.name}"
        _q3fl_scan(execution, state, entry["scan_label"])
        if (
            not state.repeat
            and request == "dispatched"
            and not execution.stopped
            and execution.measurement("M-DHCP-6-REPEAT").status
            is MeasurementStatus.NOT_RUN
            and "M-DHCP-6-REPEAT" in ids
        ):
            _q3fl_repeat(
                execution,
                state,
                client,
                acquisitions[client.device_id],
                service_runtime,
            )
    for client in state.clients:
        acquired = state.acquisitions.get(client.name, {})
        if acquired.get("request") == "dispatched":
            execution.record.releases.append(
                ReleaseRecord(
                    resource=f"claim:{client.name}:{client.interface}",
                    kind="claim",
                    outcome="retained_until_process_retirement",
                    detail="product claims are never reset or deleted",
                )
            )
            execution.record.engine_residue.append(f"claim:{client.name}:retained")
    if "M-DHCP-6-TIME" in ids and not execution.stopped:
        _q3fl_timing(execution, state)
    _q3fl_conclude_dhcp(execution, state, ids)


def _q3fl_repeat(
    execution: _Execution,
    state: _Q3FlState,
    client: _Q3FlClient,
    action: AcquireDhcpLease,
    service_runtime,
) -> None:
    """Replay the identical acquisition once; the claim must send no dhcpRun."""
    with execution.ledger.effect_of("q3-fl:guard:acquisition_replay"):
        [guard] = service_runtime.apply_actions([action])
    post = _q3fl_read_clients(execution, state, f"after_repeat:{client.name}")
    state.repeat = {
        "client": client.name,
        "action_id": action.id,
        "attempted": guard.attempted,
        "cause": guard.cause,
        "call_error": bool(guard.call_error),
        "dispatch": guard.dispatch.value,
        "result": guard.result.value,
        "after_label": f"after_repeat:{client.name}",
        "after": {
            "observed": post[client.name].observed,
            "ipv4": post[client.name].ipv4,
            "lease_time": post[client.name].lease_time,
        }
        if client.name in post
        else {},
    }
    # The runtime reports an own-claim replay as `attempted=None`: this
    # evaluation cannot speak for the earlier one. Its branch report is the
    # evidence that THIS evaluation reached no dhcpRun, because the claim
    # script calls it only on the no-claim path.
    refused = (
        guard.attempted is not True
        and guard.cause == "own_claim_replayed"
        and not guard.call_error
        and guard.dispatch is DispatchFact.ACCEPTED
        and guard.result is ResultFact.CORRELATED
    )
    if not refused:
        execution.stop("contradiction:q3fl_same_action_repeat_not_refused")


def _q3fl_timing(execution: _Execution, state: _Q3FlState) -> None:
    """Two timed readings with no request, then the declared renewal horizon."""
    ledger = execution.ledger
    sleep = execution.run.boundaries.sleep
    _q3fl_read_clients(execution, state, "timed_1")
    state.timing_labels.append("timed_1")
    ledger.wait(Q3_FL_TIMED_INTERVAL_SECONDS, sleep)
    _q3fl_read_clients(execution, state, "timed_2")
    state.timing_labels.append("timed_2")
    for index in range(1, Q3_FL_RENEWAL_HORIZON_READS + 1):
        ledger.wait(Q3_FL_RENEWAL_INTERVAL_SECONDS, sleep)
        label = f"horizon_{index}"
        _q3fl_read_clients(execution, state, label)
        state.timing_labels.append(label)
    _q3fl_scan(execution, state, "timing_end")


def _q3fl_scan_named(state: _Q3FlState, label: str) -> dict[str, LeaseScan]:
    return next((value for name, value in state.scans if name == label), {})


def _q3fl_conclude_dhcp(
    execution: _Execution, state: _Q3FlState, ids: tuple[str, ...]
) -> None:
    """Conclude the table, acquisition, capacity, repeat and timing measurements."""
    capacity = execution.definition.dhcp_pool_capacity
    macs = [
        item.mac
        for _label, values in state.client_reads
        for item in values.values()
        if item.observed and item.mac
    ]
    labels_with_intended = [
        label
        for label, scans in state.scans
        if Q3_POOL in scans and scans[Q3_POOL].termination != "pool_absent"
    ]
    intended_calibration = assess_lease_calibration(
        [
            CalibrationState(label, _q3fl_scan_named(state, label)[Q3_POOL])
            for label in labels_with_intended
        ],
        pool=Q3_POOL,
        capacity=capacity,
        fixture_macs=macs,
    )
    native_calibrations = {
        name: assess_lease_calibration(
            [
                CalibrationState(label, scans[name])
                for label, scans in state.scans
                if name in scans
            ],
            pool=name,
            capacity=next(
                (
                    scans[name].capacity
                    for _label, scans in state.scans
                    if name in scans and scans[name].capacity is not None
                ),
                None,
            ),
            fixture_macs=macs,
        )
        for name in state.native_pools
    }
    if "M-DHCP-2" in ids:
        execution.conclude(
            "M-DHCP-2",
            Assessment(
                intended_calibration.conclusion,
                facts={
                    "intended": intended_calibration.as_facts(),
                    "native": {
                        name: item.as_facts()
                        for name, item in native_calibrations.items()
                    },
                    "scans": [
                        {
                            "label": label,
                            "pools": {
                                name: scan.as_facts() for name, scan in scans.items()
                            },
                        }
                        for label, scans in state.scans
                    ],
                },
                causes=list(intended_calibration.causes),
                limitations=list(intended_calibration.limitations),
            ),
        )
    intended_range, native_range, netmask = _q3fl_ranges(execution, state)
    native_name = state.native_pools[0] if state.native_pools else ""
    attributions: dict[str, ClientAttribution] = {}
    for client in state.clients:
        entry = state.acquisitions.get(client.name, {})
        if "after_label" not in entry:
            continue
        before = state.reading(entry["before_label"]).get(
            client.name, ClientReading(client.name, False, cause="unread")
        )
        after = state.reading(entry["after_label"]).get(
            client.name, ClientReading(client.name, False, cause="unread")
        )
        prior = _q3fl_scan_named(state, entry["prior_scan_label"])
        post = _q3fl_scan_named(state, entry["scan_label"])
        missing = LeaseScan(Q3_POOL, False, "scan_absent")
        attributions[client.name] = attribute_client(
            client.name,
            request=entry["request"],
            before=before,
            after=after,
            prior_intended=prior.get(Q3_POOL, missing),
            prior_native=prior.get(
                native_name, LeaseScan(native_name, False, "scan_absent")
            ),
            intended=post.get(Q3_POOL, missing),
            native=post.get(native_name, LeaseScan(native_name, False, "scan_absent")),
            intended_range=intended_range,
            native_range=native_range,
            netmask=netmask,
            intended_calibration=intended_calibration,
            native_calibration=native_calibrations.get(native_name),
        )
    if "M-DHCP-6" in ids:
        execution.conclude(
            "M-DHCP-6", _q3fl_acquisition_assessment(state, attributions)
        )
    # A measurement whose procedure was never reached did not run: it is
    # NOT_RUN with the reason, never a RAN row that says nothing happened.
    stopped = execution.record.primary_failure or "not_reached"
    if "M-DHCP-6-CAP" in ids:
        if len(attributions) < 2:
            execution.not_run(
                ["M-DHCP-6-CAP"], f"capacity_negative_not_reached:{stopped}"
            )
        else:
            execution.conclude(
                "M-DHCP-6-CAP",
                _q3fl_capacity_assessment(state, attributions, capacity),
            )
    if "M-DHCP-6-REPEAT" in ids:
        if not state.repeat:
            execution.not_run(["M-DHCP-6-REPEAT"], f"repeat_not_reached:{stopped}")
        else:
            execution.conclude("M-DHCP-6-REPEAT", _q3fl_repeat_assessment(state))
    if "M-DHCP-6-TIME" in ids:
        if not state.timing_labels:
            execution.not_run(["M-DHCP-6-TIME"], f"timing_not_reached:{stopped}")
        else:
            execution.conclude("M-DHCP-6-TIME", _q3fl_timing_assessment(state))


def _q3fl_ranges(
    execution: _Execution, state: _Q3FlState
) -> tuple[AddressRange, AddressRange | None, str]:
    """Return the compiled intended window and the observed native range."""
    contract = execution.product_contract
    pool = next(
        (
            item
            for item in (contract.service_plan.actions if contract is not None else [])
            if isinstance(item, ConfigureServerDhcpPool)
        ),
        None,
    )
    intended = (
        AddressRange(pool.lease_start, pool.lease_end)
        if pool is not None
        else AddressRange("0.0.0.0", "0.0.0.0")
    )
    netmask = pool.netmask if pool is not None else ""
    latest = next(
        (item for item in reversed(state.readings) if item.observed and item.rows), None
    )
    native = (
        AddressRange(str(latest.rows[0]["start"]), str(latest.rows[0]["end"]))
        if latest is not None
        else None
    )
    return intended, native, netmask


def _q3fl_reading_series(state: _Q3FlState) -> list[dict[str, Any]]:
    """Return every labelled client reading the run took, in order."""
    return [
        {
            "label": label,
            "clients": {
                name: {
                    "observed": item.observed,
                    "mode": item.mode,
                    "mac": item.mac,
                    "ipv4": item.ipv4,
                    "netmask": item.netmask,
                    "lease_time": item.lease_time,
                    "cause": item.cause,
                }
                for name, item in values.items()
            },
        }
        for label, values in state.client_reads
    ]


def _q3fl_acquisition_assessment(
    state: _Q3FlState, attributions: Mapping[str, ClientAttribution]
) -> Assessment:
    """Keep every client's claims separate; conclude only from all of them."""
    facts = {
        # Every reading, background and settle included: when an address
        # first appeared is itself evidence about autonomous acquisition.
        "client_readings": _q3fl_reading_series(state),
        "clients": {
            name: {**state.acquisitions.get(name, {}), "attribution": item.as_facts()}
            for name, item in attributions.items()
        },
        "not_requested": {
            name: entry
            for name, entry in state.acquisitions.items()
            if name not in attributions
        },
    }
    contradictions = [
        f"{name}:{item}"
        for name, value in attributions.items()
        for item in value.contradictions
    ]
    unknown = [
        name
        for name, entry in state.acquisitions.items()
        if str(entry.get("request", "")).startswith("outcome_unknown")
    ]
    requested = [
        name for name, value in attributions.items() if value.request == "dispatched"
    ]
    causes: list[str] = []
    if contradictions:
        return Assessment(
            MeasurementConclusion.CONTRADICTED,
            facts=facts,
            causes=contradictions,
            limitations=[NO_BACKGROUND_PROOF, NOT_DORA],
        )
    if unknown:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts=facts,
            causes=[f"acquisition_outcome_unknown:{name}" for name in unknown],
            limitations=["no_later_effect_after_an_unknown_outcome"],
            outcome_unknown=True,
        )
    if not requested:
        causes.append("no_acquisition_dispatched")
    for name in requested:
        value = attributions[name]
        if value.served_by not in (SERVED_INTENDED, SERVED_NATIVE, SERVED_NONE):
            causes.append(f"serving_pool_not_attributed:{name}:{value.served_by}")
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE
        if causes
        else MeasurementConclusion.SUPPORTED_IN_SAMPLE,
        facts=facts,
        causes=causes,
        limitations=[
            NO_BACKGROUND_PROOF,
            NOT_DORA,
            "dhcp_lease_read_back_is_never_promoted_to_verified",
            "an_in_range_address_alone_identifies_no_serving_pool",
        ],
    )


def _q3fl_capacity_assessment(
    state: _Q3FlState,
    attributions: Mapping[str, ClientAttribution],
    capacity: int,
) -> Assessment:
    """Decide the capacity-one negative from the first two clients, in order."""
    ordered = [
        attributions[item.name] for item in state.clients if item.name in attributions
    ]
    if len(ordered) < 2:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts={"clients": [item.as_facts() for item in ordered]},
            causes=["two_acquisitions_not_observed"],
        )
    final_scans = _q3fl_scan_named(
        state, state.acquisitions[ordered[1].client].get("scan_label", "")
    )
    result = assess_capacity_one_negative(
        first=ordered[0],
        second=ordered[1],
        intended=final_scans.get(Q3_POOL, LeaseScan(Q3_POOL, False, "scan_absent")),
        capacity=capacity,
    )
    return Assessment(
        result.conclusion,
        facts={**dict(result.facts), "result": result.result},
        causes=list(result.causes),
        limitations=[
            "a_timeout_without_an_address_is_not_pool_exhaustion",
            "native_default_service_is_not_intended_pool_success",
            "the_native_default_was_never_modified_to_rescue_the_control",
        ],
    )


def _q3fl_repeat_assessment(state: _Q3FlState) -> Assessment:
    """Judge the identical replay: its own claim reported, nothing sent."""
    repeat = state.repeat
    if not repeat:
        return Assessment(
            MeasurementConclusion.INCONCLUSIVE,
            facts={},
            causes=["repeat_not_run:no_known_dispatch_to_replay"],
        )
    refused = (
        repeat.get("attempted") is not True
        and repeat.get("cause") == "own_claim_replayed"
        and not repeat.get("call_error")
        and repeat.get("dispatch") == DispatchFact.ACCEPTED.value
        and repeat.get("result") == ResultFact.CORRELATED.value
    )
    return Assessment(
        MeasurementConclusion.SUPPORTED_IN_SAMPLE
        if refused
        else MeasurementConclusion.CONTRADICTED,
        facts=dict(repeat),
        causes=[] if refused else ["same_action_repeat_dispatched_or_unreadable"],
        limitations=[
            "evidence_is_the_claim_scripts_own_branch_report",
            "requested_renewal_is_a_different_operation_and_is_not_measured",
        ],
    )


def _q3fl_timing_assessment(state: _Q3FlState) -> Assessment:
    """Keep every raw lease-time reading; a changed string is not a renewal."""
    series: dict[str, list[dict[str, Any]]] = {}
    for label in ["timed_1", "timed_2", *state.timing_labels[2:]]:
        for name, item in state.reading(label).items():
            series.setdefault(name, []).append(
                {
                    "label": label,
                    "observed": item.observed,
                    "ipv4": item.ipv4,
                    "lease_time": item.lease_time,
                }
            )
    unread = [
        f"{name}:{row['label']}"
        for name, rows in series.items()
        for row in rows
        if not row["observed"]
    ]
    changed = [
        name
        for name, rows in series.items()
        if len({row["lease_time"] for row in rows if row["observed"]}) > 1
    ]
    causes = [f"timed_reading_unobserved:{item}" for item in unread] or [
        (
            "lease_time_string_changed_renewal_unproven"
            if changed
            else "automatic_renewal_not_observed_within_declared_horizon"
        )
    ]
    return Assessment(
        MeasurementConclusion.INCONCLUSIVE,
        facts={
            "series": series,
            "timed_interval_seconds": Q3_FL_TIMED_INTERVAL_SECONDS,
            "horizon_seconds": Q3_FL_RENEWAL_HORIZON_READS
            * Q3_FL_RENEWAL_INTERVAL_SECONDS,
            "changed_lease_strings": changed,
            "requested_renewal": REQUESTED_RENEWAL_CONTRACT_ABSENT,
        },
        causes=causes,
        limitations=[
            "no_clock_or_lease_manipulation",
            "no_explicit_request_is_not_proof_of_absent_background_traffic",
            "a_lease_string_change_is_not_renewal",
        ],
    )


def _q3fl_final(execution: _Execution, state: _Q3FlState) -> None:
    """Read the native default and both tables once more, before cleanup."""
    ids = ("M-DHCP-1-FINAL",)
    if not execution.selected("Q3FL-final"):
        return
    if not execution.begin_terminal(ids, "Q3FL_FINAL"):
        return
    with execution.procedure(ids):
        permitted = _q3fl_snapshot(execution, state, "before_cleanup", _Q3FL_TERMINAL)
        scans = _q3fl_scan(execution, state, "before_cleanup")
        last = state.readings[-1] if state.readings else None
        observed = last is not None and last.observed and last.label == "before_cleanup"
        terminal = (
            state.sequence.intervals[-1]
            if state.sequence and state.sequence.intervals
            else None
        )
        drift = (
            terminal is not None
            and terminal.decision == INTERVAL_REFUSED
            and terminal.assessment.classification == UNEXPLAINED_DRIFT
        )
        if drift:
            conclusion = MeasurementConclusion.CONTRADICTED
        elif observed and permitted:
            conclusion = MeasurementConclusion.SUPPORTED_IN_SAMPLE
        else:
            conclusion = MeasurementConclusion.INCONCLUSIVE
        execution.conclude(
            "M-DHCP-1-FINAL",
            Assessment(
                conclusion,
                facts={
                    "native_default": _native_default_facts(execution),
                    "native_default_sequence": _q3fl_sequence_facts(state),
                    "scans": {name: scan.as_facts() for name, scan in scans.items()},
                },
                causes=[]
                if conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
                else [_q3fl_policy_cause(state) or "final_reading_not_observed"],
                limitations=["terminal_reading_is_taken_whatever_the_sequence_did"],
            ),
        )
    execution.finish("Q3FL_FINAL")


@dataclass
class _DWebState:
    """What one D-WEB run has established, carried between its procedures."""

    endpoints: dict[str, ForwardingRuntimeEndpoint] = field(default_factory=dict)
    forwarding_admitted: bool = False
    listeners_before: dict[str, Any] = field(default_factory=dict)
    marker: str = ""


def _d_web_selection(
    execution: _Execution, fixture: FixtureDevice
) -> ForwardingRuntimeEndpoint:
    """Bind one fixture endpoint to the E5 action this stage dispatched.

    The provenance is the stage's own, and it is real: the address comes from
    the fixture the authorization named, the action id is the one the endpoint
    batch this run applied actually carried, and the co-observed addresses are
    the other addressed fixtures of the same segment, so a duplicate address
    conflicts instead of binding.
    """
    definition = execution.definition
    scope = definition.stage.value.lower()
    network = ".".join([*fixture.ipv4.split(".")[:3], "0"])
    known = tuple(
        ForwardingKnownAddress(
            item.ipv4, _endpoint_action_id(execution, item.name), item.name
        )
        for item in definition.fixtures
        if item.ipv4
    )
    selection = ForwardingEndpointSelection(
        policy_id=scope,
        policy_version=definition.profile_version,
        source_topology_id=definition.stage.value,
        source_topology_hash="",
        source_configuration_id=definition.stage.value,
        source_configuration_hash="",
        site_id=scope,
        routing_device_id="",
        endpoint_device_id=fixture.name,
        endpoint_device_name=fixture.name,
        endpoint_model=fixture.model,
        endpoint_role="fixture",
        link_id="",
        endpoint_interface="FastEthernet0",
        peer_device_id=Q1_SWITCH,
        peer_interface="",
        segment_id=scope,
        address_mode=ForwardingAddressMode.STATIC,
        configuration_action_id=_endpoint_action_id(execution, fixture.name),
        planned_ipv4=fixture.ipv4,
        network=network,
        prefix_length=24,
        netmask=fixture.netmask,
        known_plan_addresses=known,
    )
    return ForwardingRuntimeEndpoint(
        selection=selection,
        runtime_device_name=fixture.name,
        identity_method="stage_fixture_binding",
        deployment_id=execution.record.run_id,
        deployment_manifest_hash="",
    )


def _run_d_web(execution: _Execution) -> None:
    """Observe every boundary an unretrieved page can fail at, in order."""
    state = _DWebState()
    # The after-boundaries are this stage's terminal observation and they are
    # registered before its first effect. An HTTP timeout is precisely the
    # case the diagnostic was asked about, and so is an exception raised out
    # of the middle of the sequence: neither may delete the fixtures without
    # the readings that locate it. They are read-only and dispatch no second
    # request.
    execution.register_terminal(
        ("M-DWEB-5",), "D_WEB_AFTER", lambda: _d_web_terminal(execution, state)
    )
    if not _diagnostic_start(execution):
        return
    if not _configure_q1(execution):
        execution.not_run(
            [item.id for item in execution.definition.experiments if item.required],
            "fixture_setup_failed",
        )
        return
    for fixture in execution.definition.fixtures:
        if fixture.ipv4:
            state.endpoints[fixture.name] = _d_web_selection(execution, fixture)

    ids = ("M-DWEB-0",)
    if execution.selected("W0-listeners") and execution.begin(ids, "D_WEB_BOUNDARIES"):
        with execution.procedure(ids):
            _d_web_boundaries(execution, state, label="before")
        execution.finish("D_WEB_BOUNDARIES")

    ids = ("M-DWEB-1",)
    if execution.selected("W1-forwarding") and execution.begin(ids, "D_WEB_FORWARDING"):
        with execution.procedure(ids):
            _d_web_forwarding(
                execution,
                state,
                label="before",
                samples=D_WEB_FORWARDING_SAMPLES_BEFORE,
            )
        execution.finish("D_WEB_FORWARDING")

    ids = ("M-DWEB-2",)
    if execution.selected("W2-page") and execution.begin(ids, "D_WEB_PAGE"):
        with execution.procedure(ids):
            _d_web_page(execution, state)
        execution.finish("D_WEB_PAGE")

    ids = ("M-DWEB-3",)
    if execution.selected("W3-ping") and execution.begin(ids, "D_WEB_PING"):
        with execution.procedure(ids):
            _d_web_ping(execution, state)
        execution.finish("D_WEB_PING")

    ids = ("M-DWEB-4",)
    if execution.selected("W4-fetch") and execution.begin(ids, "D_WEB_FETCH"):
        with execution.procedure(ids):
            _d_web_fetch(execution, state)
        execution.finish("D_WEB_FETCH")


def _d_web_terminal(execution: _Execution, state: _DWebState) -> None:
    """Take this stage's terminal reading, from finalization and only there."""
    ids = ("M-DWEB-5",)
    if not execution.selected("W5-after"):
        return
    if not execution.begin_terminal(ids, "D_WEB_AFTER"):
        return
    with execution.procedure(ids):
        _d_web_after(execution, state)
    execution.finish("D_WEB_AFTER")


def _d_web_listener_reading(execution: _Execution, label: str) -> dict[str, Any]:
    """Read both listeners, their port numbers and every fixture endpoint."""
    endpoints = _fixture_endpoints(execution)
    with execution.ledger.purpose_of(f"d-web:listeners:{label}"):
        reading = execution.probes.read_listener_readiness(Q1_SERVER, endpoints)
    return dict(assess_port_readiness(reading, endpoints).facts)


def _d_web_boundaries(execution: _Execution, state: _DWebState, *, label: str) -> None:
    """Establish the listener and endpoint boundaries before any request."""
    facts = _d_web_listener_reading(execution, label)
    state.listeners_before = facts
    endpoints = _fixture_endpoints(execution)
    gate = _Readiness(False, 0, 0.0, "readiness_not_selected")
    if execution.selected("W0-readiness"):
        gate = _await_readiness(
            execution,
            endpoints,
            lambda timeout: execution.probes.read_port_readiness(endpoints, timeout),
            purpose="readiness:d_web_fixture_links",
        )
    listeners = facts.get("listeners") or {}
    causes: list[str] = []
    if not facts.get("observed"):
        causes.append(f"listener_reading_unobserved:{facts.get('cause', '')}")
    for key in ("http_enabled", "https_enabled"):
        if listeners.get(key) is not True:
            causes.append(f"listener_not_enabled:{key}")
    for key in ("http_port_number", "https_port_number"):
        if not isinstance(listeners.get(key), int) or isinstance(
            listeners.get(key), bool
        ):
            causes.append(f"listener_port_not_read_back:{key}")
    if execution.selected("W0-readiness") and not gate.ready:
        causes.append(f"readiness_not_established:{gate.reason}")
    execution.conclude(
        "M-DWEB-0",
        Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if not causes
            else MeasurementConclusion.INCONCLUSIVE,
            facts={f"listeners_{label}": facts, "readiness": gate.facts()},
            causes=causes,
            limitations=[
                DIAGNOSTIC_SCOPE,
                "light_status_and_port_up_are_auxiliary_and_grant_no_forwarding",
            ],
        ),
    )
    if causes:
        execution.stop(f"d_web_boundaries_not_established:{causes[0]}")
        return
    execution.establish(DiagnosticPrecondition.LISTENERS_ESTABLISHED)


def _d_web_switch_ports(execution: _Execution) -> tuple[str, ...]:
    """Return the exact switch-side access ports of this stage's fixture."""
    return tuple(
        item.port_b if item.device_b == Q1_SWITCH else item.port_a
        for item in execution.definition.links
        if Q1_SWITCH in (item.device_a, item.device_b)
    )


def _d_web_forwarding(
    execution: _Execution, state: _DWebState, *, label: str, samples: int
) -> None:
    """Observe the exact switch ports' per-VLAN forwarding state, neutrally."""
    interfaces = _d_web_switch_ports(execution)
    runtime = execution.run.boundaries.configuration_runtime(execution.bound)
    with execution.ledger.purpose_of(f"d-web:forwarding:{label}"):
        observation = runtime.observe_access_forwarding(
            Q1_SWITCH,
            DIAGNOSTIC_ACCESS_VLAN,
            interfaces,
            max_samples=samples,
        )
    lights = {
        key: {
            "light_status": value.get("light_status"),
            "light_status_type": value.get("light_status_type"),
            "light_status_name": value.get("light_status_name"),
        }
        for key, value in (state.listeners_before.get("ports") or {}).items()
    }
    assessment = assess_access_forwarding(
        observation, label=f"forwarding_{label}", lights=lights
    )
    state.forwarding_admitted = (
        assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE
    )
    if state.forwarding_admitted:
        execution.establish(DiagnosticPrecondition.FORWARDING_OBSERVED)
    execution.conclude("M-DWEB-1", assessment)
    if not state.forwarding_admitted:
        # No permission is granted by an unadmitted sample, and the stage says
        # so rather than continuing as if it had one.
        execution.record.limitations.append(
            f"forwarding_not_admitted:{assessment.causes[0] if assessment.causes else 'unknown'}"
        )


def _d_web_page(execution: _Execution, state: _DWebState) -> None:
    """Write this run's marker into the existing index page through both handles."""
    texts = execution.probes.page_marker_texts()
    state.marker = texts["http_marker"]
    with execution.ledger.effect_of("d-web:marker_page"):
        reading = execution.probes.prepare_marker_page(Q1_SERVER, state.marker)
    established = marker_page_established(reading)
    execution.conclude(
        "M-DWEB-2",
        Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if established
            else MeasurementConclusion.INCONCLUSIVE,
            facts={
                "marker_page": {
                    "marker": state.marker,
                    "observed": reading.observed,
                    "cause": reading.cause,
                    "payload": dict(reading.payload) if reading.observed else {},
                }
            },
            causes=[] if established else ["marker_page_not_established"],
            limitations=[DIAGNOSTIC_SCOPE],
        ),
    )
    if not established:
        execution.stop("d_web_marker_page_not_established")
        return
    execution.establish(DiagnosticPrecondition.MARKER_PAGE)


def _d_web_ping(execution: _Execution, state: _DWebState) -> None:
    """Take exactly one attributed ping between the two selected bindings."""
    probe = execution.run.boundaries.forwarding_probe
    source = state.endpoints.get(Q1_PC1)
    destination = state.endpoints.get(Q1_SERVER)
    if probe is None or source is None or destination is None:
        execution.conclude(
            "M-DWEB-3",
            assess_forwarding_probe(
                None, forwarding_admitted=state.forwarding_admitted
            ),
        )
        execution.stop("d_web_forwarding_probe_not_composed")
        return
    execution.record.limitations.append(ACTIVE_STIMULUS)
    with execution.ledger.effect_of("d-web:ping"):
        evidence = probe(execution.bound).probe_once(
            source_device_name=Q1_PC1,
            destination_endpoint=destination,
            source_endpoint=source,
            expected_reachable=True,
        )
    probe_assessment = assess_forwarding_probe(
        evidence, forwarding_admitted=state.forwarding_admitted
    )
    if probe_assessment.conclusion is MeasurementConclusion.SUPPORTED_IN_SAMPLE:
        execution.establish(DiagnosticPrecondition.PING_ATTRIBUTED)
    execution.conclude("M-DWEB-3", probe_assessment)


def _d_web_fetch(execution: _Execution, state: _DWebState) -> None:
    """Instrument one real owned background client, start to release."""
    factory = execution.run.boundaries.diagnostic_service_runtime
    if factory is None:
        execution.conclude(
            "M-DWEB-4",
            assess_client_timeline(
                None, marker=state.marker, schedule=D_WEB_INSPECTION_SCHEDULE
            ),
        )
        execution.stop("d_web_service_runtime_not_composed")
        return
    expectation = ServiceVerificationExpectation(
        id="d-web-http",
        service_id="d-web-http",
        action_id="d-web-fixture",
        kind=ServiceVerificationKind.HTTP_FETCH,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id=Q1_SERVER,
        host_device_name=Q1_SERVER,
        client_device_id=Q1_PC1,
        client_device_name=Q1_PC1,
        expected={
            "scheme": "http",
            "address": Q1_SERVER_IPV4,
            "marker": state.marker,
        },
        host_model="Server-PT",
        client_model="PC-PT",
    )
    with execution.ledger.effect_of("d-web:fetch:http"):
        row = factory(execution.bound, execution.ledger.allowance).verify(expectation)
    released = str(row.observed.get("released", ""))
    execution.record.releases.append(
        ReleaseRecord(
            resource="client:d-web-http",
            kind="client",
            outcome=released or "unknown",
            detail="; ".join(row.limitations)[:MAX_DETAIL],
        )
    )
    if released not in ("released", "nothing_owned"):
        execution.record.engine_residue.append(
            f"client:d-web-http:{released or 'unknown'}"
        )
    execution.conclude(
        "M-DWEB-4",
        assess_client_timeline(
            row, marker=state.marker, schedule=D_WEB_INSPECTION_SCHEDULE
        ),
    )
    if released not in ("released", "nothing_owned"):
        execution.stop("outcome_unknown:fetch_client:d-web-http")


def _d_web_after(execution: _Execution, state: _DWebState) -> None:
    """Read the same boundaries again and retain whatever moved."""
    after = _d_web_listener_reading(execution, "after")
    # This completed sub-read is evidence even when the next terminal reader
    # is cancelled. Keep it on the existing measurement before starting that
    # reader; a complete assessment below replaces these partial facts.
    execution.measurement("M-DWEB-5").facts["listeners_after"] = after
    execution.run.transition("experiment:D_WEB_AFTER:listeners_observed")
    interfaces = _d_web_switch_ports(execution)
    runtime = execution.run.boundaries.configuration_runtime(execution.bound)
    with execution.ledger.purpose_of("d-web:forwarding:after"):
        observation = runtime.observe_access_forwarding(
            Q1_SWITCH,
            DIAGNOSTIC_ACCESS_VLAN,
            interfaces,
            max_samples=D_WEB_FORWARDING_SAMPLES_AFTER,
        )
    forwarding = assess_access_forwarding(observation, label="forwarding_after")
    before = state.listeners_before.get("listeners") or {}
    listeners = after.get("listeners") or {}
    limitations = [DIAGNOSTIC_SCOPE, ACTIVE_STIMULUS, *forwarding.limitations]
    causes = list(forwarding.causes)
    moved: list[str] = []
    if not before:
        # Without the earlier reading there is nothing to compare against.
        # Reporting every field as changed would manufacture a difference out
        # of an observation that was never taken.
        limitations.append("listener_comparison_unavailable:no_reading_before")
        causes.append("listeners_before_not_observed")
    else:
        moved = sorted(
            key
            for key in set(before) | set(listeners)
            if before.get(key) != listeners.get(key)
        )
        causes.extend(f"listener_changed:{item}" for item in moved)
    execution.conclude(
        "M-DWEB-5",
        Assessment(
            MeasurementConclusion.SUPPORTED_IN_SAMPLE
            if not causes
            else MeasurementConclusion.INCONCLUSIVE,
            facts={
                "listeners_after": after,
                **forwarding.facts,
                "listener_differences": moved,
                "listener_comparison_observed": bool(before),
            },
            causes=causes,
            limitations=limitations,
        ),
    )


# -- finalization ----------------------------------------------------------------


def _observe_terminal(execution: _Execution) -> KeyboardInterrupt | None:
    """Take the stage's terminal reading once, before anything is deleted.

    This is the only place the reading happens. Registering it and taking it
    are separate so that every exit which reaches cleanup reaches the reading
    first: a normal completion, a handled stop, an `OperationRefused` inside a
    procedure, an ordinary Python exception raised out of the middle of the
    sequence, and a run whose record stopped advancing.

    Three rules it never breaks. A cancelled run does not take it: the
    operator asked the run to stop doing work, so the measurement is declared
    `not_observed:cancelled` and no stimulus is restarted or re-dispatched. A
    failure inside the reading is secondary -- it never replaces the primary
    error and never stops owned cleanup, which is why nothing raises out of
    here. And the reading itself is read-only and paid for out of the ordinary
    allowance, which `begin_terminal` already enforces.
    """
    phase = execution.terminal
    if phase is None or execution.terminal_taken:
        return None
    execution.terminal_taken = True
    if execution.cancelled:
        execution.not_observed(phase.ids, "cancelled")
        return None
    try:
        phase.observe()
    except KeyboardInterrupt as exc:
        execution.cancelled = True
        execution.stop("cancelled")
        execution.not_observed(phase.ids, "cancelled")
        execution.record.secondary_failures.append(
            f"terminal_observation:{phase.procedure}:cancelled"
        )
        return exc
    except OperationRefused as exc:
        execution.not_observed(phase.ids, f"operation_refused:{exc.reason}")
        execution.record.secondary_failures.append(
            f"terminal_observation:{phase.procedure}:refused:{exc.reason}"
        )
    except Exception as exc:
        execution.not_observed(phase.ids, f"exception:{type(exc).__name__}")
        execution.record.secondary_failures.append(
            f"terminal_observation:{phase.procedure}:exception:{type(exc).__name__}"
        )
    finally:
        execution.in_flight = ()
    return None


def _release_campaign_claim(execution: _Execution) -> None:
    """Release the campaign claim into this record, before it is completed.

    A claim this run cannot release keeps the next campaign out of the shared
    scope, so it is a finalization result the record has to carry rather than
    something that happens to the filesystem after the record is closed. It is
    deliberately not engine residue: a lock left behind says nothing about
    whether the engine workspace was restored, and the two claims stay apart.
    """
    execution.hold.finalize(execution.record)


def _finalize(execution: _Execution) -> None:
    """Release owned state, remove owned devices and prove restoration twice.

    The receiver is proven before anything is deleted, not afterwards. A
    Packet Tracer that was replaced mid-run polls the same mailbox, so a
    removal dispatched now would land in a workspace this authority never
    bound; learning that after the fact invalidates the report without undoing
    the deletion. With authority lost this finalization deletes nothing, names
    every action it did not take, and still reads what it can. The postflight
    reading below keeps its detection role for everything that came earlier.
    """
    ledger = execution.ledger
    ledger.enter(LedgerPhase.FINALIZATION)
    record = execution.record
    execution.in_flight = ()
    execution.run.transition("finalization:started")
    owned = execution.live_authority("finalization:owned_cleanup")
    if not owned:
        _refuse_owned_cleanup(execution)
    else:
        _release_engine_state(execution)
    for plan in reversed(execution.removal_candidates) if owned else ():
        fixture = next(item for item in record.fixtures if item.name == plan.name)
        try:
            with ledger.effect_of(f"remove:{plan.name}"):
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
    # Authority held at the start of finalization is not authority held at the
    # end of it: the effect gate can refuse a removal halfway through the loop
    # above. A restoration claim needs the receiver to still be the bound one
    # when the last reading was taken, so the two are one condition here.
    attributable = owned and not execution.authority_lost
    record.restoration_proven = attributable and all(
        item is not None
        and physical_workspace_restoration_matches(execution.baseline, item)
        for item in observations
    )
    if not attributable:
        # These reads describe whatever answers the mailbox now. They are kept
        # as observations and they prove nothing about the bound instance's
        # workspace, so they never become a restoration claim.
        record.limitations.append(
            "restoration_reads_not_attributable_to_the_authorized_process"
        )
    if owned and not attributable:
        # The run entered cleanup holding the receiver and lost it partway.
        # Whatever it had not deleted by then was not dispatched at all.
        record.limitations.append(
            "owned_cleanup_not_dispatched_to_an_unproven_receiver"
        )
    if execution.bound.settle_pending_sends():
        record.engine_residue.append("transport:pending_fire_and_forget")
        record.secondary_failures.append("transport:pending_fire_and_forget")
        record.limitations.append("transport_pending_send_not_replayed")
        record.restoration_proven = False
    _lifecycle_postflight(execution)
    for name in sorted(execution.observers_unresolved):
        record.engine_residue.append(f"observer:{name}")
    record.dirty_state = _dirty_state(execution, observations)
    execution.run.transition("finalization:completed")


def _refuse_owned_cleanup(execution: _Execution) -> None:
    """Name every owned deletion this run declined to dispatch, and why.

    Nothing here is a guess about what the replacement receiver holds. The
    fixtures this run created are still reported as residue, because that is
    what an operator has to reconcile; they are simply not deleted through a
    session whose identity can no longer be proven.
    """
    record = execution.record
    cause = (
        execution.authority_lost
        or execution.authority_observation_refused
        or "execution_authority_lost"
    )
    if execution.bag_touched:
        # Only state is left behind that this run actually wrote. A bag
        # it never claimed is not residue it declined to clean.
        record.releases.append(
            ReleaseRecord(
                resource="bag:run",
                kind="bag",
                outcome="not_attempted",
                detail=f"execution authority lost before cleanup: {cause}",
            )
        )
    for plan in reversed(execution.removal_candidates):
        record.releases.append(
            ReleaseRecord(
                resource=f"device:{plan.name}",
                kind="device",
                outcome="not_attempted",
                detail=f"execution authority lost before cleanup: {cause}",
            )
        )
        record.engine_residue.append(
            f"device:{plan.name}:removal_refused_unproven_receiver"
        )
    record.limitations.append("owned_cleanup_not_dispatched_to_an_unproven_receiver")


def _lifecycle_postflight(execution: _Execution) -> None:
    """Read the local process pairing again, after owned finalization.

    The admission reading bound one Packet Tracer before a transport
    existed. Nothing holds that process for the rest of the run: a crashed
    instance is replaced by one that polls the same mailbox, and the
    removals and both restoration reads above would then have been answered
    by a process this authority never bound. Reading the pairing again is
    what decides whether that evidence is still about the authorized
    instance, and whether this run left anything a later one could execute.

    It enumerates local processes and lists one directory. It contacts
    Packet Tracer through nothing, launches and stops nothing, deletes no
    artifact and spends no ledger operation, but it does spend finalization
    wall-clock. Every helper is bounded by the remaining finalization deadline;
    when none remains, the record retains an explicit unobserved postflight
    instead of launching another helper. A broken or unavailable pairing is
    not a new primary failure -- the run already happened -- but restoration
    stops being proven, because the final evidence is not attributable to the
    process under authority.
    """
    record = execution.record
    lifecycle = execution.run.boundaries.diagnostic_lifecycle
    if not callable(lifecycle) or execution.run.diagnostic_lifecycle is None:
        return
    deadline = execution.ledger.deadline()
    if execution.run.boundaries.clock() >= deadline:
        observed = DiagnosticLifecycleObservation(
            error="local_observation_not_admitted:time_budget_exhausted"
        )
    else:
        observed = execution.observe_lifecycle(lifecycle, deadline)
    record.diagnostic_lifecycle_postflight = asdict(observed)
    reasons = diagnostic_lifecycle_continuity(
        execution.run.diagnostic_lifecycle, observed
    )
    if not reasons:
        return
    record.engine_residue.extend(reasons)
    record.secondary_failures.extend(f"lifecycle:{item}" for item in reasons)
    record.limitations.append(
        "finalization_evidence_not_paired_to_the_authorized_process"
    )
    record.restoration_proven = False


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
        with execution.ledger.effect_of("release:run_bag"):
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
