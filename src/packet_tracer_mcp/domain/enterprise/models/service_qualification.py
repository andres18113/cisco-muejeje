"""Pure contracts of the Server-PT qualification runner (S4a).

A qualification stage is a separately authorized experiment on Packet Tracer
itself, not a product operation. This module states what one stage is allowed
to do and what its record must say, and it decides the questions that need no
I/O: whether a request is admissible, whether a stage fits its hard budget,
and whether a finished record may ever serve as promotion evidence.

Nothing here reads a repository, opens a channel or knows a vendor call. The
coordinator gathers observations through ports and brings them here to be
judged, so the same rules hold for a LIVE run and for an offline simulation.

The hard ceilings are module constants on purpose. A stage definition cannot
carry a larger budget than its ceiling, and an authorization must name the
ceiling exactly; a run that does not fit is refused and reported, never
silently given more.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, Field

from .execution import DirtyState

#: The exact four-component build form. It is the same bounded rule the product
#: environment reader applies; a shorter or suffixed value is not an exact build.
_EXACT_BUILD = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+")
MAX_BUILD_LENGTH = 64
_SHA = re.compile(r"[0-9a-f]{40}")
#: The shape of a fresh instance token and of an attempt identity: 32
#: lowercase hexadecimal characters, the same form the runner's own nonce has.
_HEX_TOKEN = re.compile(r"[0-9a-f]{32}")
MAX_AUTHORIZATION_ID_LENGTH = 128
ALLOWED_CHANNELS = ("http", "file")
#: The two counted reads every executable stage makes before its first effect.
ADMISSION_READ_STEPS = ("read:executable_build", "read:workspace_baseline")


def is_exact_packet_tracer_build(value: object) -> bool:
    """Return whether a value is one bounded four-component build string."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_BUILD_LENGTH
        and _EXACT_BUILD.fullmatch(value) is not None
    )


def is_full_sha(value: object) -> bool:
    """Return whether a value is exactly 40 lowercase hexadecimal characters."""
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


class QualificationStage(StrEnum):
    """The staged qualification matrix of the plan (5.8)."""

    __str__ = Enum.__str__

    Q0 = "Q0"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    #: The two executable diagnostics. They are stages, not a second
    #: framework: they pass the same request rule, the same repository and
    #: process gates, the same fixed transport, the same ledger and the same
    #: write-ahead record as Q0/Q1/Q3, plus the step binding below.
    D_WEB = "D-WEB"
    D_DHCP = "D-DHCP"
    #: The versioned experimental Q3 profile of campaign
    #: `SERVER-PT-DHCP-FASTLOOP-01`: one procedure over a one-user (C1) and a
    #: two-user (C2) intended pool. The historical Q3 stage, its 60/1200
    #: design bound and its three consumed attempts are unchanged.
    Q3_FL_C1 = "Q3-FL-C1"
    Q3_FL_C2 = "Q3-FL-C2"
    Q3_NATIVE_PROBE = "Q3-NATIVE-PROBE"
    Q3_NATIVE_SIZE = "Q3-NATIVE-SIZE"


class ExecutionMode(StrEnum):
    """Whether a record observed Packet Tracer or a controlled simulation."""

    __str__ = Enum.__str__

    LIVE = "live"
    OFFLINE_SIMULATION = "offline_simulation"


@dataclass(frozen=True)
class FixtureDevice:
    """One device a stage creates, with the addressing it needs, if any."""

    name: str
    model: str
    ipv4: str = ""
    netmask: str = ""
    dns_server: str = ""


@dataclass(frozen=True)
class FixtureLink:
    """One cable a stage creates between two of its own fixtures."""

    device_a: str
    port_a: str
    device_b: str
    port_b: str


@dataclass(frozen=True)
class PlannedStep:
    """A unit of setup or finalization work and its planned operation cost."""

    id: str
    operations: int


class DiagnosticPrecondition(StrEnum):
    """Operational state an executable diagnostic run can establish.

    These are observations about the subject, not conclusions about the
    hypothesis. A measurement may conclude `NEGATIVE_OBSERVED` -- that is
    exactly what a diagnostic looks for -- while still having established the
    state its successor depends on, and it may conclude nothing useful while
    having established none. Keeping the two apart is what lets a coherent
    native-default change at D1 be the finding instead of a gate that stops
    D2 from ever running.
    """

    #: The authorized subject and session are bound and the fixtures this
    #: stage owns exist under it.
    SUBJECT_SESSION = "subject_session_bound"
    #: The retained inventory was read coherently at least once.
    INVENTORY_COHERENT = "inventory_coherent"
    #: The server's static addressing was applied and read back.
    SERVER_ADDRESSING = "server_addressing_established"
    #: The intended pool was written and its stored configuration verified.
    POOL_CONFIGURED = "pool_configuration_established"
    #: The DHCP process was verified to be off.
    PROCESS_DISABLED_VERIFIED = "process_disabled_verified"
    #: The DHCP process was verified to have transitioned on.
    PROCESS_ENABLED_VERIFIED = "process_enabled_verified"
    #: Both listeners reported their enable flags and read-back ports.
    LISTENERS_ESTABLISHED = "listeners_established"
    #: A fresh attributed forwarding sample was admitted for the exact VLAN.
    FORWARDING_OBSERVED = "forwarding_sample_observed"
    #: This run's marker is in the served page.
    MARKER_PAGE = "marker_page_established"
    #: One attributed ping between two verified bindings was taken.
    PING_ATTRIBUTED = "ping_attributed"
    #: Every admitted client's DHCP mode was activated and read back true.
    CLIENT_DHCP_MODE = "client_dhcp_mode_verified"
    #: The versioned native-default policy permitted every interval so far.
    NATIVE_DEFAULT_PERMITS = "native_default_policy_permits"


@dataclass(frozen=True)
class ExperimentSpec:
    """One measurement: its hypothesis and what running it requires.

    Measurements that share one procedure put the whole planned cost on the
    first of them and name the procedure on each, so the stage total counts
    every shared dispatch exactly once. An optional measurement that the stage
    already knows it cannot run carries its omission reason here, so the
    record can say why it did not run rather than silently leaving it out.
    """

    id: str
    hypothesis: str
    required: bool
    procedure: str
    planned_operations: int
    prerequisites: tuple[str, ...] = ()
    #: The operational state a run must have established before this
    #: measurement may be attempted, which is not the same thing as what an
    #: earlier measurement concluded. An executable diagnostic is admitted
    #: from these, because its dependent variable is allowed to be negative:
    #: a coherent native-default change is the finding, not a reason the next
    #: intervention cannot run. `prerequisites` keeps deciding every stage
    #: that declares no diagnostic profile, so Q0/Q1/Q3 and every product
    #: caller are unchanged and no NEGATIVE or UNKNOWN conclusion is globally
    #: admitted anywhere.
    operational_prerequisites: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    omission_reason: str = ""
    #: A read-only terminal observation belongs to the run rather than to its
    #: success, so it is still attempted after a primary failure when subject
    #: authority and the ordinary allowance permit. It dispatches no stimulus
    #: and never spends the finalization reserve.
    terminal_observation: bool = False


@dataclass(frozen=True)
class StageBudget:
    """The hard operation/time ceiling and the time reserved for finalization."""

    max_operations: int
    max_seconds: int
    reserve_seconds: int


@dataclass(frozen=True)
class DiagnosticStageStep:
    """One separately selectable step of an executable diagnostic stage.

    A step is what an authorization may name. `requires` is the ordered
    prerequisite closure the selection has to satisfy, and it is not the same
    thing as the measurement prerequisites the run evaluates: this one decides
    whether the authority is coherent before contact, that one decides whether
    the state the run actually established permits the next effect. Neither
    substitutes for the other.
    """

    id: str
    experiment_id: str
    #: observe | configure | activate | request | release.
    effect: str
    requires: tuple[str, ...] = ()
    #: True when the step activates a process rather than only configuring or
    #: observing one, so an authorization has to name it deliberately.
    separately_authorized: bool = False
    #: Further measurements one step runs. A Q3-FL step performs the shared
    #: procedure whose readings several M-DHCP measurements conclude from, and
    #: selecting it must not omit them as unselected.
    also_experiments: tuple[str, ...] = ()


@dataclass(frozen=True)
class StageDefinition:
    """Everything a stage is allowed to create, run and spend."""

    stage: QualificationStage
    executable: bool
    purpose: str
    fixtures: tuple[FixtureDevice, ...]
    links: tuple[FixtureLink, ...]
    setup: tuple[PlannedStep, ...]
    experiments: tuple[ExperimentSpec, ...]
    reserve: tuple[PlannedStep, ...]
    budget: StageBudget
    unmet_prerequisites: tuple[str, ...] = ()
    allowed_channels: tuple[str, ...] = ALLOWED_CHANNELS
    #: Non-empty only for an executable diagnostic. Its presence is what makes
    #: the extended authority binding mandatory, so Q0/Q1/Q3 keep exactly the
    #: authorization they always had.
    profile_id: str = ""
    profile_version: str = ""
    steps: tuple[DiagnosticStageStep, ...] = ()
    #: The intended pool's capacity for a DHCP qualification profile, and 0
    #: for every other stage. It is part of the product contract the stage
    #: composes, never a value read from the engine.
    dhcp_pool_capacity: int = 0

    @property
    def fixture_names(self) -> tuple[str, ...]:
        """Return the exact fixture names, in creation order."""
        return tuple(item.name for item in self.fixtures)

    @property
    def fixture_models(self) -> tuple[str, ...]:
        """Return each fixture bound to its exact model, in creation order."""
        return tuple(f"{item.name}:{item.model}" for item in self.fixtures)

    @property
    def link_bindings(self) -> tuple[str, ...]:
        """Return each link bound to its exact ports, in creation order."""
        return tuple(
            f"{item.device_a}:{item.port_a}-{item.device_b}:{item.port_b}"
            for item in self.links
        )

    @property
    def step_ids(self) -> tuple[str, ...]:
        """Return every selectable step id, in declared sequence order."""
        return tuple(item.id for item in self.steps)

    def step(self, step_id: str) -> DiagnosticStageStep:
        """Return one selectable step by id."""
        for item in self.steps:
            if item.id == step_id:
                return item
        raise KeyError(step_id)

    def experiments_of_steps(self, step_ids: Sequence[str]) -> tuple[str, ...]:
        """Return the measurements a step selection would run, in order."""
        chosen = set(step_ids)
        seen: dict[str, None] = {}
        for item in self.steps:
            if item.id in chosen:
                seen.setdefault(item.experiment_id, None)
                for extra in item.also_experiments:
                    seen.setdefault(extra, None)
        return tuple(seen)

    @property
    def reserve_operations(self) -> int:
        """Return the operations kept back for owned finalization."""
        return sum(item.operations for item in self.reserve)

    @property
    def setup_operations(self) -> int:
        """Return the planned operations of admission reads and fixture setup."""
        return sum(item.operations for item in self.setup)

    @property
    def fixture_operations(self) -> int:
        """Return the planned setup operations that create or configure fixtures."""
        return sum(
            item.operations
            for item in self.setup
            if item.id not in ADMISSION_READ_STEPS
        )

    @property
    def required_experiment_operations(self) -> int:
        """Return the planned operations of every required measurement."""
        return sum(
            item.planned_operations for item in self.experiments if item.required
        )

    @property
    def planned_minimum_operations(self) -> int:
        """Return the smallest ceiling the whole planned path is proven to fit in.

        Each planned figure is its step's bounded worst case, so this sum is
        the worst case of the complete trace: admission reads, fixture setup,
        every required measurement and the untouchable finalization reserve.
        It is not the luckiest trace, and a stage whose ceiling is below it is
        refused before contact.
        """
        return (
            self.setup_operations
            + self.required_experiment_operations
            + self.reserve_operations
        )

    @property
    def experimental_capabilities(self) -> tuple[str, ...]:
        """Return the unqualified behaviors this stage's probes exercise."""
        seen: dict[str, None] = {}
        for experiment in self.experiments:
            if experiment.omission_reason:
                continue
            for capability in experiment.capabilities:
                seen.setdefault(capability, None)
        return tuple(seen)

    def experiment(self, experiment_id: str) -> ExperimentSpec:
        """Return one declared measurement by id."""
        for item in self.experiments:
            if item.id == experiment_id:
                return item
        raise KeyError(experiment_id)


#: Plan 5.8 ceilings, with the reviewed Q1 design ceiling. Q0, Q1 and Q3 are
#: the executable stages. Q1 keeps the reviewed 60/600; the amended worst case
#: is 56 operations, because the readiness gate is charged to the trace rather
#: than to unlogged preparation, with its 10-operation finalization reserve
#: intact. M-DNS-3 is not repeated, so no operation is spent on a measurement
#: the 0850de3 record already carries, and no reconciliation read was added to
#: replace it. Q3 keeps 60/1200 and its 11-operation reserve: the allowance
#: M-DHCP-3 held is reallocated to readiness and to preserving the observed
#: native default, never to another acquisition. No ceiling is raised, and
#: none of this authorizes a LIVE run or changes declarative Q2.
#:
#: The two diagnostic ceilings are new, proposed limits, not a raise of any
#: existing one. Each is its stage's measured composed worst case plus a
#: stated slack for one additional convergence round in every nested terminal
#: loop it contains: D-DHCP 45 + 5, D-WEB 63 + 5. The measurements come from
#: the real components running against the engine stub: one endpoint E5 batch
#: is one `send` plus one verification read per expectation, one E6 service
#: action is one dispatch plus one read-back per expectation, one native
#: default reading is one dispatch, one `show spanning-tree` sample is four
#: calls, one typed ping is three and one bind-before-ping probe is seven.
#:
#: Their SECONDS are recomputed for the effect gate. Deciding authority before
#: each effect dispatch spends no operation and does spend time: two local
#: process reads per decision, at most one decision per admitted or refused
#: call inside an effect scope, plus one per procedure and four for setup,
#: finalization and the two pairing readings. A complete D-WEB simulation
#: takes 46 of those readings and a D-DHCP one 37, against 9 before the gate
#: existed, and one healthy reading was measured at 0.20-0.24 s.
#:
#: What bounds the TOTAL is this ceiling itself, not a multiplication by
#: `LOCAL_OBSERVATION_TIMEOUT_SECONDS`. The per-read timeout can be spent in
#: full at most once, because an expired read is unobservable authority and
#: the loss is sticky: the run stops and asks nothing further. Every reading
#: that succeeds is charged to the phase's wall clock, and once the phase has
#: no seconds left the ledger refuses the next call. So the seconds move to
#: give the gate room on a slow machine rather than to cover an unreachable
#: worst case: D-DHCP 900 -> 1500 and D-WEB 900 -> 1800, with the
#: finalization reserve 180 -> 300 because owned cleanup is where the
#: per-dispatch decision matters most. Each record reports what it actually
#: spent as `budget.local_observation_seconds`. No operation ceiling moves, no
#: historical Q budget moves, and both remain proposed limits that no
#: authorization has ever been granted against.
STAGE_CEILINGS: dict[QualificationStage, tuple[int, int]] = {
    QualificationStage.Q0: (20, 300),
    QualificationStage.Q1: (60, 600),
    QualificationStage.Q2: (60, 900),
    QualificationStage.Q3: (60, 1200),
    QualificationStage.D_DHCP: (50, 1500),
    QualificationStage.D_WEB: (80, 1800),
    # The versioned Q3-FL profiles: their composed worst case is 439, and
    # 362 of it is the two capped forwarding episodes. See `_q3_fastloop`.
    QualificationStage.Q3_FL_C1: (440, 1500),
    QualificationStage.Q3_FL_C2: (440, 1500),
    QualificationStage.Q3_NATIVE_PROBE: (120, 600),
    QualificationStage.Q3_NATIVE_SIZE: (120, 600),
}

Q0_PC = "__MCP_E6Q_PC1"
Q1_SERVER = "__MCP_E6Q_SRV"
Q1_PC1 = "__MCP_E6Q_PC1"
Q1_PC2 = "__MCP_E6Q_PC2"
Q1_SWITCH = "__MCP_E6Q_SW"
#: TEST-NET-1 (RFC 5737): never routed, so a fixture address cannot collide
#: with an operator's network even if a cable were misplaced.
Q1_NETMASK = "255.255.255.0"
Q1_SERVER_IPV4 = "192.0.2.10"
Q1_PC1_IPV4 = "192.0.2.11"
Q1_PC2_IPV4 = "192.0.2.12"
Q3_SERVER = "__MCP_E6Q_SRV"
Q3_PC1 = "__MCP_E6Q_PC1"
Q3_PC2 = "__MCP_E6Q_PC2"
Q3_SWITCH = "__MCP_E6Q_SW"
Q3_NETMASK = "255.255.255.0"
Q3_SERVER_IPV4 = "192.0.2.10"
Q3_GATEWAY_IPV4 = "192.0.2.1"
Q3_DNS_IPV4 = Q3_SERVER_IPV4
Q3_LEASE_IPV4 = "192.0.2.100"
Q3_POOL = "MCP_E6Q_DHCP"
#: The complete native pool a stock Server-PT carried in the Q3 ordinal-2
#: record (run `2026-09-19T22-52-28Z-6d12894c`, on the reviewed build over the
#: file channel). Every field is compared by value and by type, so a pool that
#: only shares the name is refused. Nothing here says the range is harmless,
#: and the build the policy is qualified for is injected by the composition
#: rather than pinned here: the domain names no backend version.
Q3_OBSERVED_NATIVE_DEFAULT_POOL: dict[str, str | int] = {
    "name": "serverPool",
    "network": "0.0.0.0",
    "mask": "0.0.0.0",
    "gateway": "0.0.0.0",
    "dns": "0.0.0.0",
    "start": "0.0.0.0",
    "end": "0.0.2.0",
    "max": 512,
}

#: The readiness gate both executable network stages share. Four aggregate
#: reads and thirty monotonic seconds is a precondition, not a retry budget:
#: the first complete ready sample wins, and the stage's unspent time and its
#: finalization reserve cap the deadline.
READINESS_MAX_READS = 4
READINESS_DEADLINE_SECONDS = 30.0


def _q0() -> StageDefinition:
    ceiling_operations, ceiling_seconds = STAGE_CEILINGS[QualificationStage.Q0]
    return StageDefinition(
        stage=QualificationStage.Q0,
        executable=True,
        purpose=(
            "Engine facts for S2/S3 runtime design: bag persistence, "
            "evaluation atomicity and event observer release."
        ),
        fixtures=(FixtureDevice(Q0_PC, "PC-PT"),),
        links=(),
        setup=(
            PlannedStep("read:executable_build", 1),
            PlannedStep("read:workspace_baseline", 1),
            PlannedStep(f"create:{Q0_PC}", 2),
            PlannedStep(f"read:identity:{Q0_PC}", 1),
        ),
        experiments=(
            ExperimentSpec(
                id="M-ENG-1",
                hypothesis=(
                    "A value written under the evaluation receiver persists to "
                    "a later, separate evaluation on the same fixed channel."
                ),
                required=True,
                procedure="ENG",
                planned_operations=2,
                capabilities=("engine.bag_persistence",),
            ),
            ExperimentSpec(
                id="ATOM-1",
                hypothesis=(
                    "One script evaluation is not interleaved with another "
                    "queued evaluation (candidate invariant, plan 3.7)."
                ),
                required=True,
                procedure="ATOM",
                planned_operations=3,
                prerequisites=("M-ENG-1",),
                capabilities=("engine.evaluation_atomicity",),
            ),
            ExperimentSpec(
                id="M-UNREG-1",
                hypothesis=(
                    "A HostPort ipChanged callback receives an event, "
                    "and unregistering it with the event-supplied source "
                    "identity stops later invocations."
                ),
                required=True,
                procedure="UNREG",
                planned_operations=4,
                prerequisites=("M-ENG-1",),
                capabilities=(
                    "engine.event_registration",
                    "engine.event_unregister_by_id",
                ),
            ),
            ExperimentSpec(
                id="M-UNREG-2",
                hypothesis=(
                    "An observer that has received no event has no "
                    "identity-free release; the inert fallback keeps it "
                    "attached while bounding what it records."
                ),
                required=True,
                procedure="UNREG",
                planned_operations=0,
                prerequisites=("M-ENG-1",),
                capabilities=("engine.event_registration",),
            ),
            ExperimentSpec(
                id="M-HTTP-1",
                hypothesis="onDone argument semantics of HttpClient (optional).",
                required=False,
                procedure="HTTP",
                planned_operations=0,
                omission_reason=(
                    "prerequisite_absent: the Q0 fixture is one PC-PT and has "
                    "no HTTP server; no dependency is added for an optional "
                    "measurement"
                ),
            ),
        ),
        reserve=(
            PlannedStep("release:run_bag", 1),
            PlannedStep(f"remove:{Q0_PC}", 2),
            PlannedStep("read:restoration:1", 1),
            PlannedStep("read:restoration:2", 1),
        ),
        budget=StageBudget(ceiling_operations, ceiling_seconds, reserve_seconds=60),
    )


def _q3() -> StageDefinition:
    """Return the exact bounded Server-PT DHCP qualification stage."""
    ceiling_operations, ceiling_seconds = STAGE_CEILINGS[QualificationStage.Q3]
    fixtures = (
        FixtureDevice(Q3_SERVER, "Server-PT", Q3_SERVER_IPV4, Q3_NETMASK),
        FixtureDevice(Q3_PC1, "PC-PT"),
        FixtureDevice(Q3_PC2, "PC-PT"),
        FixtureDevice(Q3_SWITCH, "2960-24TT"),
    )
    return StageDefinition(
        stage=QualificationStage.Q3,
        executable=True,
        purpose=(
            "Server-PT DHCP binding, mode, bounded lease-table, acquisition, "
            "event-delivery and lease-time facts on one owned local segment."
        ),
        fixtures=fixtures,
        links=(
            FixtureLink(Q3_SERVER, "FastEthernet0", Q3_SWITCH, "FastEthernet0/1"),
            FixtureLink(Q3_PC1, "FastEthernet0", Q3_SWITCH, "FastEthernet0/2"),
            FixtureLink(Q3_PC2, "FastEthernet0", Q3_SWITCH, "FastEthernet0/3"),
        ),
        setup=(
            PlannedStep("read:executable_build", 1),
            PlannedStep("read:workspace_baseline", 1),
            *(PlannedStep(f"create:{item.name}", 2) for item in fixtures),
            PlannedStep("create:link:1", 2),
            PlannedStep("create:link:2", 2),
            PlannedStep("create:link:3", 2),
            PlannedStep("read:fixture_identity", 1),
        ),
        experiments=(
            ExperimentSpec(
                id="M-DHCP-1",
                hypothesis=(
                    "The exact Server-PT interface binds a DHCP process and "
                    "the product ensure-present pool path stores the one-user pool."
                ),
                required=True,
                procedure="Q3_SETUP",
                # The whole Q3_SETUP worst case: admission baseline and client
                # reads, four readiness reads before E5, the four-call E5
                # application, two staged E6 server actions plus their fresh
                # read-back, and the post-setup default snapshot.
                planned_operations=15,
                capabilities=(
                    "server.dhcp_process_binding",
                    "server.dhcp_pool_configuration",
                ),
            ),
            ExperimentSpec(
                id="M-DHCP-4",
                hypothesis=(
                    "The two exact PC-PT ports expose bounded native MAC text."
                ),
                required=True,
                procedure="Q3_SETUP",
                planned_operations=0,
                capabilities=("client.dhcp_mac_reader",),
            ),
            ExperimentSpec(
                id="M-DHCP-5",
                hypothesis=(
                    "HostPort.isDhcpClientOn returns an actual boolean on each "
                    "manifest-bound client interface."
                ),
                required=True,
                procedure="Q3_SETUP",
                planned_operations=0,
                capabilities=("client.dhcp_mode_reader",),
            ),
            ExperimentSpec(
                id="M-DHCP-2",
                hypothesis=(
                    "Bounded empty and capacity-one getLeaseAt samples preserve "
                    "their observed termination and positive rows separately."
                ),
                required=True,
                procedure="Q3_DHCP",
                # The whole Q3_DHCP worst case: the run-bag sentinel, three
                # bounded client/table reads before the product path, seven
                # calls for the full application with exact setup rows
                # retained, the same-claim guard, three reads after it and the
                # pre-cleanup default snapshot. Retained rows cost no call.
                planned_operations=16,
                prerequisites=("M-DHCP-1",),
                capabilities=("server.dhcp_lease_table",),
            ),
            ExperimentSpec(
                id="M-DHCP-3",
                hypothesis=(
                    "Qualification-only dhcpSucceed/dhcpFailed observers receive "
                    "bounded events and are released or made inert."
                ),
                required=False,
                procedure="Q3_DHCP",
                planned_operations=0,
                prerequisites=("M-DHCP-1",),
                capabilities=("engine.dhcp_event_delivery",),
                omission_reason=(
                    "qualification_event_source_and_release_not_qualified: the "
                    "registration subscribes on the port while Cisco documents "
                    "dhcpSucceed/dhcpFailed on DhcpClientProcess, and an "
                    "unregister attempt that did not throw is not observed "
                    "detachment. No observer is registered in this profile "
                    "until a separately reviewed event change fixes source "
                    "identity, correlation and release evidence"
                ),
            ),
            ExperimentSpec(
                id="M-DHCP-6",
                hypothesis=(
                    "Raw lease-time observations distinguish no-request, one "
                    "requested acquisition and any naturally observed renewal."
                ),
                required=True,
                procedure="Q3_DHCP",
                planned_operations=0,
                prerequisites=("M-DHCP-1", "M-DHCP-5"),
                capabilities=(
                    "client.dhcp_acquisition",
                    "client.dhcp_lease_time_reader",
                ),
            ),
        ),
        reserve=(
            PlannedStep("release:run_bag", 1),
            *(PlannedStep(f"remove:{item.name}", 2) for item in fixtures),
            PlannedStep("read:restoration:1", 1),
            PlannedStep("read:restoration:2", 1),
        ),
        budget=StageBudget(ceiling_operations, ceiling_seconds, reserve_seconds=180),
        allowed_channels=("file",),
    )


def _q1() -> StageDefinition:
    ceiling_operations, ceiling_seconds = STAGE_CEILINGS[QualificationStage.Q1]
    fixtures = (
        FixtureDevice(Q1_SERVER, "Server-PT", Q1_SERVER_IPV4, Q1_NETMASK),
        FixtureDevice(Q1_PC1, "PC-PT", Q1_PC1_IPV4, Q1_NETMASK, Q1_SERVER_IPV4),
        FixtureDevice(Q1_PC2, "PC-PT", Q1_PC2_IPV4, Q1_NETMASK),
        FixtureDevice(Q1_SWITCH, "2960-24TT"),
    )
    return StageDefinition(
        stage=QualificationStage.Q1,
        executable=True,
        purpose=(
            "HTTPS ownership and readers for S1b: page tables, listener "
            "state, client mode and the client resolver reader."
        ),
        fixtures=fixtures,
        links=(
            FixtureLink(Q1_SERVER, "FastEthernet0", Q1_SWITCH, "FastEthernet0/1"),
            FixtureLink(Q1_PC1, "FastEthernet0", Q1_SWITCH, "FastEthernet0/2"),
            FixtureLink(Q1_PC2, "FastEthernet0", Q1_SWITCH, "FastEthernet0/3"),
        ),
        setup=(
            PlannedStep("read:executable_build", 1),
            PlannedStep("read:workspace_baseline", 1),
            *(PlannedStep(f"create:{item.name}", 2) for item in fixtures),
            PlannedStep("create:link:1", 2),
            PlannedStep("create:link:2", 2),
            PlannedStep("create:link:3", 2),
            PlannedStep("read:fixture_identity", 1),
            PlannedStep("apply:e5_endpoints", 1),
            PlannedStep("apply:e6_enable_http_https", 1),
        ),
        experiments=(
            ExperimentSpec(
                id="M-HTTPS-1",
                hypothesis=(
                    "HttpServer and HttpsServer page tables are either one "
                    "shared table or two separate tables."
                ),
                required=True,
                procedure="HTTPS1",
                # Write H, read both, write S, read both: the existing index
                # page only, each step admitted after the previous one.
                planned_operations=4,
                capabilities=("https.page_table",),
            ),
            ExperimentSpec(
                id="M-HTTPS-2",
                hypothesis=(
                    "With a working same-mode positive in each mode, an "
                    "HTTPS-mode client retrieves the page when only HTTPS is "
                    "enabled and fails when HTTPS is disabled; an HTTP-mode "
                    "client fails when HTTP is disabled."
                ),
                required=True,
                procedure="HTTPS2",
                # The readiness gate at its ceiling of four aggregate reads,
                # the marked page, two listener toggles and four production
                # fetches, each budgeted at its worst case of 4 operations:
                # the start, both inspections and the release of the owned
                # client. A failed positive stops the negatives it would
                # qualify and spends one readiness read instead, so every
                # early exit costs less than this complete path.
                planned_operations=23,
                capabilities=("https.listener_toggle", "https.client_mode"),
            ),
            ExperimentSpec(
                id="M-DNS-3",
                hypothesis=(
                    "DnsClient.getServerIp on a PC configured through E5 "
                    "returns the configured resolver; its unset value is "
                    "recorded as measured."
                ),
                required=False,
                procedure="DNS3",
                planned_operations=0,
                capabilities=("client.dns_server_reader",),
                omission_reason=(
                    "already_measured: the Q1-file run at 0850de3 recorded "
                    "this reader's sample, and nothing in the repaired stage "
                    "depends on it. Re-running it would add a second sample "
                    "attributed to its own SHA, not new support for the first"
                ),
            ),
            ExperimentSpec(
                id="M-DNS-1",
                hypothesis="nslookup output lines (optional).",
                required=False,
                procedure="DNS1",
                planned_operations=0,
                omission_reason=(
                    "optional_without_reviewed_probe: omitted explicitly; the "
                    "required set's planned worst case is 56 of 60 operations, "
                    "so this is not a budget refusal"
                ),
            ),
            ExperimentSpec(
                id="M-DNS-2",
                hypothesis="getIpOfHost cache behavior (optional).",
                required=False,
                procedure="DNS2",
                planned_operations=0,
                omission_reason=(
                    "optional_without_reviewed_probe: omitted explicitly; the "
                    "required set's planned worst case is 56 of 60 operations, "
                    "so this is not a budget refusal"
                ),
            ),
        ),
        reserve=(
            *(PlannedStep(f"remove:{item.name}", 2) for item in fixtures),
            PlannedStep("read:restoration:1", 1),
            PlannedStep("read:restoration:2", 1),
        ),
        budget=StageBudget(ceiling_operations, ceiling_seconds, reserve_seconds=120),
    )


#: The diagnostic profile identities the extended authority must bind. The
#: version moves whenever the step sequence, the fixture binding, the budget
#: arithmetic or the execution contract an authorization buys changes, so an
#: authorization written for an earlier contract cannot be replayed against a
#: later one. Version 3 is the contract in which every effect dispatch is
#: admitted only while this invocation still holds its campaign claim and its
#: bound Packet Tracer incarnation, and in which the terminal read-only
#: observation is part of guaranteed pre-cleanup finalization rather than the
#: last ordinary step of the sequence.
D_DHCP_PROFILE = "D-DHCP"
D_WEB_PROFILE = "D-WEB"
DIAGNOSTIC_PROFILE_VERSION = "3"

#: The exact VLAN the access fixture's switch ports belong to on a stock
#: 2960-24TT: nothing in either diagnostic configures a VLAN, so this is the
#: default instance the registered STP query reports, never a configured one.
DIAGNOSTIC_ACCESS_VLAN = 1
#: The finite inspection schedule of the instrumented fetch, as monotonic
#: offsets from the request start. It is deliberately decoupled from the HTTP
#: deadline: three slots, all inside the reader's own 8 s window.
D_WEB_INSPECTION_SCHEDULE = (1.0, 3.0, 6.0)
#: How many inspections one diagnostic ping may take. The safe 30 s window is
#: unchanged, and the reads are the endpoints of an even partition of it --
#: 0, 6, 12, 18, 24 and 30 s -- so the last read lands ON the deadline and a
#: destination that publishes at 29 s is still classified from its own
#: statistics rather than from a wait that closed one interval early.
#: Unbounded, that poll is limited only by the window and the 0.25 s interval,
#: which is tens of counted calls and not the one the earlier figure assumed.
D_WEB_PING_INSPECTIONS = 6
#: How many channel calls one registered spanning-tree sample may make. It
#: mirrors `ACCESS_FORWARDING_SAMPLE_CALLS` in the runtime that enforces
#: it; a contract test pins the two together so the arithmetic here and
#: the bound applied there cannot drift apart.
D_WEB_FORWARDING_SAMPLE_CALLS = 6
#: The bounded samples each neutral forwarding observation takes. Two
#: closely spaced samples do not cover a nominal 30 s convergence window
#: and are not claimed to: they are two observations inside it, and the
#: schedule is stated rather than implied.
D_WEB_FORWARDING_SAMPLES_BEFORE = 2
D_WEB_FORWARDING_SAMPLES_AFTER = 1
#: One bounded late read, after the deadline and before the release.
D_WEB_LATE_READ_OFFSET = 10.0
#: How long one LOCAL authority observation may wait for its own helper
#: process. It contacts Packet Tracer through nothing and spends no counted
#: operation, which bounds neither its wall-clock time nor the phase's, so the
#: wait is finite and declared. It bounds what this run waits for, never
#: operating-system scheduling: process creation and interpreter startup are
#: outside this process's control and nothing here promises a bound on them.
#:
#: The figure is measured, not guessed, and it is deliberately far above the
#: cost of a healthy read. One `Get-Process` through PowerShell answered in
#: 0.20-0.24 s on a warm maintainer machine; the same read exceeded 5 s on a
#: loaded GitHub Windows runner, where a first invocation pays for interpreter
#: start and module loading on contended disk. A bound a healthy environment
#: can cross is worse than no bound at all here: an expired read is
#: unobservable authority, so it stops the run and refuses its own cleanup.
#: 30 s is roughly 130 times the measured healthy cost, which leaves the
#: timeout for the case it exists for -- a helper that is not coming back.
LOCAL_OBSERVATION_TIMEOUT_SECONDS = 30.0
#: What the effect gate is, stated on every diagnostic record so the reading
#: is never mistaken for one. The gate decides authority immediately before a
#: dispatch leaves this process; no existing dispatcher carries a session
#: token the receiver verifies in the evaluation that mutates, so the interval
#: between that decision and the receiver consuming the command is not fenced.
EFFECT_GATE_LIMIT = "effect_gate_is_local_and_not_an_in_band_receiver_fence"


def _d_dhcp() -> StageDefinition:
    """Return the executable D-DHCP diagnostic stage.

    The causal sequence is the contract: a coherent disabled baseline, the
    server's static addressing alone, the intended pool while the process is
    still disabled, the enable, the terminal observation and owned cleanup.
    No client is activated, no lease is acquired, no default-pool setter and
    no event registration exists anywhere in it.
    """
    ceiling_operations, ceiling_seconds = STAGE_CEILINGS[QualificationStage.D_DHCP]
    fixtures = (
        FixtureDevice(Q3_SERVER, "Server-PT", Q3_SERVER_IPV4, Q3_NETMASK),
        FixtureDevice(Q3_PC1, "PC-PT"),
        FixtureDevice(Q3_PC2, "PC-PT"),
        FixtureDevice(Q3_SWITCH, "2960-24TT"),
    )
    return StageDefinition(
        stage=QualificationStage.D_DHCP,
        executable=True,
        purpose=(
            "Which operation of a server-only DHCP setup moves the native "
            "default pool, observed between adjacent counted readings."
        ),
        fixtures=fixtures,
        links=(
            FixtureLink(Q3_SERVER, "FastEthernet0", Q3_SWITCH, "FastEthernet0/1"),
            FixtureLink(Q3_PC1, "FastEthernet0", Q3_SWITCH, "FastEthernet0/2"),
            FixtureLink(Q3_PC2, "FastEthernet0", Q3_SWITCH, "FastEthernet0/3"),
        ),
        setup=(
            PlannedStep("read:executable_build", 1),
            PlannedStep("read:workspace_baseline", 1),
            *(PlannedStep(f"create:{item.name}", 2) for item in fixtures),
            PlannedStep("create:link:1", 2),
            PlannedStep("create:link:2", 2),
            PlannedStep("create:link:3", 2),
            PlannedStep("read:fixture_identity", 1),
        ),
        experiments=(
            ExperimentSpec(
                id="M-DDHCP-0",
                hypothesis=(
                    "A stock Server-PT presents a coherent disabled DHCP "
                    "process, its native default inventory and two clients "
                    "whose DHCP flags this stage never touches."
                ),
                required=True,
                procedure="D_DHCP_BASELINE",
                # One native reading, one client-flag reading, the readiness
                # gate at its ceiling of four aggregate reads, and the second
                # adjacent native reading that is the drift control.
                planned_operations=7,
                capabilities=(
                    "server.dhcp_process_binding",
                    "server.dhcp_default_pool_observation",
                    "client.dhcp_mode_reader",
                ),
            ),
            ExperimentSpec(
                id="M-DDHCP-1",
                hypothesis=(
                    "The server's static addressing alone is one native "
                    "`configurePcIp` intervention that also writes gateway "
                    "and DNS, and the interval around it is attributed to "
                    "that whole call and to nothing narrower."
                ),
                required=True,
                procedure="D_DHCP_E5",
                # The endpoint batch is one `send` plus one verification read
                # for the single addressing expectation, then one reading.
                planned_operations=3,
                operational_prerequisites=(
                    DiagnosticPrecondition.SUBJECT_SESSION,
                    DiagnosticPrecondition.INVENTORY_COHERENT,
                    DiagnosticPrecondition.PROCESS_DISABLED_VERIFIED,
                ),
                capabilities=("server.dhcp_default_pool_observation",),
            ),
            ExperimentSpec(
                id="M-DDHCP-2",
                hypothesis=(
                    "The intended pool can be written while the process is "
                    "still disabled, and the stored configuration verifies "
                    "against `enabled=False` plus its exact pool fields."
                ),
                required=True,
                procedure="D_DHCP_POOL",
                # One pool dispatch, its fresh server-state read-back, and
                # one native reading.
                planned_operations=3,
                operational_prerequisites=(
                    DiagnosticPrecondition.SUBJECT_SESSION,
                    DiagnosticPrecondition.INVENTORY_COHERENT,
                    DiagnosticPrecondition.SERVER_ADDRESSING,
                ),
                capabilities=("server.dhcp_pool_configuration",),
            ),
            ExperimentSpec(
                id="M-DDHCP-3",
                hypothesis=(
                    "Enabling the process is the transition to `enabled=True`, "
                    "and whatever the native default does across that exact "
                    "interval is the dependent variable."
                ),
                required=True,
                procedure="D_DHCP_ENABLE",
                # One enable dispatch, the rebound server-state read-back and
                # one native reading.
                planned_operations=3,
                operational_prerequisites=(
                    DiagnosticPrecondition.SUBJECT_SESSION,
                    DiagnosticPrecondition.INVENTORY_COHERENT,
                    DiagnosticPrecondition.POOL_CONFIGURED,
                ),
                capabilities=("server.dhcp_process_enable",),
            ),
            ExperimentSpec(
                id="M-DDHCP-4",
                hypothesis=(
                    "The pre-cleanup native inventory is preserved whatever "
                    "the sequence did, including after a stop."
                ),
                required=True,
                procedure="D_DHCP_FINAL",
                planned_operations=1,
                operational_prerequisites=(DiagnosticPrecondition.SUBJECT_SESSION,),
                capabilities=("server.dhcp_default_pool_observation",),
                terminal_observation=True,
            ),
        ),
        reserve=(
            *(PlannedStep(f"remove:{item.name}", 2) for item in fixtures),
            PlannedStep("read:restoration:1", 1),
            PlannedStep("read:restoration:2", 1),
            PlannedStep("release:run_bag", 1),
        ),
        budget=StageBudget(ceiling_operations, ceiling_seconds, reserve_seconds=300),
        allowed_channels=("file",),
        profile_id=D_DHCP_PROFILE,
        profile_version=DIAGNOSTIC_PROFILE_VERSION,
        steps=(
            DiagnosticStageStep("D0-baseline", "M-DDHCP-0", "observe"),
            DiagnosticStageStep("D0-control", "M-DDHCP-0", "observe", ("D0-baseline",)),
            DiagnosticStageStep(
                "D1-static", "M-DDHCP-1", "configure", ("D0-baseline", "D0-control")
            ),
            DiagnosticStageStep("D2-pool", "M-DDHCP-2", "configure", ("D1-static",)),
            DiagnosticStageStep(
                "D3-enable",
                "M-DDHCP-3",
                "activate",
                ("D2-pool",),
                separately_authorized=True,
            ),
            DiagnosticStageStep("D4-final", "M-DDHCP-4", "observe", ("D0-baseline",)),
        ),
    )


def _d_web() -> StageDefinition:
    """Return the executable D-WEB diagnostic stage.

    It observes the boundaries the unretrieved page could fail at, in order:
    the endpoint bindings and link readiness, the per-VLAN forwarding state of
    the exact switch ports, the served page, one attributed ping and one
    instrumented fetch of the real background client, then the same boundaries
    again. The ping is an active stimulus and is labelled as one.
    """
    ceiling_operations, ceiling_seconds = STAGE_CEILINGS[QualificationStage.D_WEB]
    fixtures = (
        FixtureDevice(Q1_SERVER, "Server-PT", Q1_SERVER_IPV4, Q1_NETMASK),
        FixtureDevice(Q1_PC1, "PC-PT", Q1_PC1_IPV4, Q1_NETMASK, Q1_SERVER_IPV4),
        FixtureDevice(Q1_PC2, "PC-PT", Q1_PC2_IPV4, Q1_NETMASK),
        FixtureDevice(Q1_SWITCH, "2960-24TT"),
    )
    return StageDefinition(
        stage=QualificationStage.D_WEB,
        executable=True,
        purpose=(
            "Where an unretrieved HTTP page fails: the forwarding path, the "
            "listener and request, or the polling and the reader."
        ),
        fixtures=fixtures,
        links=(
            FixtureLink(Q1_SERVER, "FastEthernet0", Q1_SWITCH, "FastEthernet0/1"),
            FixtureLink(Q1_PC1, "FastEthernet0", Q1_SWITCH, "FastEthernet0/2"),
            FixtureLink(Q1_PC2, "FastEthernet0", Q1_SWITCH, "FastEthernet0/3"),
        ),
        setup=(
            PlannedStep("read:executable_build", 1),
            PlannedStep("read:workspace_baseline", 1),
            *(PlannedStep(f"create:{item.name}", 2) for item in fixtures),
            PlannedStep("create:link:1", 2),
            PlannedStep("create:link:2", 2),
            PlannedStep("create:link:3", 2),
            PlannedStep("read:fixture_identity", 1),
            PlannedStep("apply:e5_endpoints", 1),
            PlannedStep("apply:e6_enable_http_https", 1),
        ),
        experiments=(
            ExperimentSpec(
                id="M-DWEB-0",
                hypothesis=(
                    "Both listeners report their enable flags and their "
                    "read-back port numbers, and every fixture endpoint is "
                    "up with its documented port readers."
                ),
                required=True,
                procedure="D_WEB_BOUNDARIES",
                # One listener/port reading plus the readiness gate at its
                # ceiling of four aggregate reads.
                planned_operations=5,
                capabilities=("https.listener_port_reader", "port.light_status"),
            ),
            ExperimentSpec(
                id="M-DWEB-1",
                hypothesis=(
                    "The exact switch-side access ports are forwarding in the "
                    "actual fixture VLAN, on a fresh, complete and uniquely "
                    "attributed registered spanning-tree sample."
                ),
                required=True,
                procedure="D_WEB_FORWARDING",
                # Two bounded samples, each capped at its own channel call
                # budget, plus one read of simulation time after the loop.
                # A registered query is session preparation, dispatch,
                # convergence reads, attribution and pager handling, and a
                # proved-corrupt dispatch is retried, so four was the
                # intended path rather than the worst case.
                planned_operations=(
                    D_WEB_FORWARDING_SAMPLES_BEFORE * D_WEB_FORWARDING_SAMPLE_CALLS + 1
                ),
                operational_prerequisites=(
                    DiagnosticPrecondition.SUBJECT_SESSION,
                    DiagnosticPrecondition.LISTENERS_ESTABLISHED,
                ),
                capabilities=("switch.access_forwarding_observation",),
            ),
            ExperimentSpec(
                id="M-DWEB-2",
                hypothesis=(
                    "The existing index page carries this run's marker through "
                    "both handles before any request is made."
                ),
                required=True,
                procedure="D_WEB_PAGE",
                planned_operations=1,
                operational_prerequisites=(
                    DiagnosticPrecondition.SUBJECT_SESSION,
                    DiagnosticPrecondition.LISTENERS_ESTABLISHED,
                ),
                capabilities=("https.page_table",),
            ),
            ExperimentSpec(
                id="M-DWEB-3",
                hypothesis=(
                    "One attributed ping between the selected PC and server "
                    "bindings establishes ICMP reachability, and nothing "
                    "about TCP or HTTP."
                ),
                required=True,
                procedure="D_WEB_PING",
                # The bind-before-ping probe: two endpoint address reads,
                # the typed ping, two endpoint address reads after it. The
                # ping is one dispatch, its bounded inspections and one
                # attribution read; the single inspection of the earlier
                # figure was the fastest path, not the worst one.
                planned_operations=4 + 2 + D_WEB_PING_INSPECTIONS,
                operational_prerequisites=(
                    DiagnosticPrecondition.SUBJECT_SESSION,
                    DiagnosticPrecondition.MARKER_PAGE,
                ),
                capabilities=("forwarding.typed_ping",),
            ),
            ExperimentSpec(
                id="M-DWEB-4",
                hypothesis=(
                    "The real owned background client's whole lifecycle is "
                    "observable: owner, mode, native go result, every "
                    "scheduled inspection, one late read and the release."
                ),
                required=True,
                procedure="D_WEB_FETCH",
                # The start, the three scheduled inspections, the late control
                # read and the release of the owned client.
                planned_operations=6,
                operational_prerequisites=(
                    DiagnosticPrecondition.SUBJECT_SESSION,
                    DiagnosticPrecondition.MARKER_PAGE,
                ),
                capabilities=("https.client_mode", "https.client_timeline"),
            ),
            ExperimentSpec(
                id="M-DWEB-5",
                hypothesis=(
                    "The listener and forwarding boundaries after the request "
                    "are the ones observed before it, or the difference is "
                    "retained."
                ),
                required=True,
                procedure="D_WEB_AFTER",
                # One listener/port reading, one bounded forwarding sample
                # and one separate simulation-time read.
                planned_operations=(
                    1
                    + D_WEB_FORWARDING_SAMPLES_AFTER * D_WEB_FORWARDING_SAMPLE_CALLS
                    + 1
                ),
                operational_prerequisites=(DiagnosticPrecondition.SUBJECT_SESSION,),
                terminal_observation=True,
                capabilities=("switch.access_forwarding_observation",),
            ),
        ),
        reserve=(
            *(PlannedStep(f"remove:{item.name}", 2) for item in fixtures),
            PlannedStep("read:restoration:1", 1),
            PlannedStep("read:restoration:2", 1),
        ),
        budget=StageBudget(ceiling_operations, ceiling_seconds, reserve_seconds=300),
        allowed_channels=("file",),
        profile_id=D_WEB_PROFILE,
        profile_version=DIAGNOSTIC_PROFILE_VERSION,
        steps=(
            DiagnosticStageStep("W0-listeners", "M-DWEB-0", "observe"),
            DiagnosticStageStep(
                "W0-readiness", "M-DWEB-0", "observe", ("W0-listeners",)
            ),
            DiagnosticStageStep(
                "W1-forwarding", "M-DWEB-1", "observe", ("W0-readiness",)
            ),
            DiagnosticStageStep("W2-page", "M-DWEB-2", "configure", ("W1-forwarding",)),
            DiagnosticStageStep(
                "W3-ping",
                "M-DWEB-3",
                "request",
                ("W2-page",),
                separately_authorized=True,
            ),
            DiagnosticStageStep("W4-fetch", "M-DWEB-4", "request", ("W3-ping",)),
            DiagnosticStageStep("W5-after", "M-DWEB-5", "observe", ("W4-fetch",)),
        ),
    )


def _declarative(
    stage: QualificationStage, purpose: str, unmet: tuple[str, ...]
) -> StageDefinition:
    ceiling_operations, ceiling_seconds = STAGE_CEILINGS[stage]
    return StageDefinition(
        stage=stage,
        executable=False,
        purpose=purpose,
        fixtures=(),
        links=(),
        setup=(),
        experiments=(),
        reserve=(),
        budget=StageBudget(ceiling_operations, ceiling_seconds, reserve_seconds=0),
        unmet_prerequisites=unmet,
    )


Q3_FL_PROFILE = "Q3-FL"
Q3_FL_PROFILE_VERSION = "1"
#: The versioned native-default policy the Q3-FL coordinator applies. It admits
#: the one reviewed realignment on the server-address interval in its exact
#: context and requires every later interval to be unchanged.
Q3_FL_NATIVE_DEFAULT_POLICY = "q3-fl-native-default/v1"
#: The access VLAN the runner-owned fixture carries. No Q3-FL step configures a
#: switch, so the compiled VLAN 10 placements are rebound to the stock VLAN 1
#: and the rewrite is recorded, never inferred.
Q3_FL_FIXTURE_ACCESS_VLAN = 1
#: Worst case of the forwarding decision: one access group, its own episode
#: and at most one narrowed episode, each capped at `READINESS_EPISODE_CALLS`
#: (181) by the product gate. A contract test pins the two together.
Q3_FL_FORWARDING_OPERATIONS = 2 * 181
#: Bounded observation after one acquisition request: client readings taken
#: at a fixed interval, stopping early only when the address changed.
Q3_FL_SETTLE_READS = 4
Q3_FL_SETTLE_INTERVAL_SECONDS = 2.0
#: Two readings without any request after the server is enabled and before
#: the first acquisition, to see background activity rather than assume none.
Q3_FL_BACKGROUND_INTERVAL_SECONDS = 10.0
#: Two timed readings after the acquisitions with no new request, then the
#: declared natural-renewal horizon: three readings twenty seconds apart. No
#: clock or lease setting is changed to make a renewal happen inside it.
Q3_FL_TIMED_INTERVAL_SECONDS = 15.0
Q3_FL_RENEWAL_HORIZON_READS = 3
Q3_FL_RENEWAL_INTERVAL_SECONDS = 20.0
#: The explicit lease-index window: each intended pool is read at every index
#: below its capacity plus two, the native pool at its first four indexes.
Q3_FL_INTENDED_EXTRA_INDEXES = 2
Q3_FL_NATIVE_SCAN_INDEXES = 4
#: Why requested renewal is not measured. Cisco documents `dhcpRun`,
#: `dhcpRelease` and `resetDhcpConfOn` on `DhcpClientProcess` and no renewal;
#: `dhcpRun` under the same subject claim is replay, which the claim refuses.
REQUESTED_RENEWAL_CONTRACT_ABSENT = (
    "requested_renewal_contract_absent: DhcpClientProcess documents dhcpRun, "
    "dhcpRelease and resetDhcpConfOn and no renewal operation; dhcpRun under "
    "the same subject claim is replay, which the product claim refuses, and "
    "deleting the claim or changing the nonce to force one is not a typed "
    "renewal contract"
)


def _q3_fastloop(stage: QualificationStage, capacity: int) -> StageDefinition:
    """Return one versioned Q3-FL profile over an intended pool of `capacity`.

    Both profiles run one procedure: the server's address alone, forwarding,
    client DHCP mode while the server process is still disabled, the pool and
    the enable, one typed acquisition per admitted client, the same-action
    repeat, timed readings and the natural-renewal horizon. C1's second client
    is the capacity-one negative; C2 discriminates a one-row table from a
    full one. Every planned figure below is its step's bounded worst case.
    """
    ceiling_operations, ceiling_seconds = STAGE_CEILINGS[stage]
    fixtures = (
        FixtureDevice(Q3_SERVER, "Server-PT", Q3_SERVER_IPV4, Q3_NETMASK),
        FixtureDevice(Q3_PC1, "PC-PT"),
        FixtureDevice(Q3_PC2, "PC-PT"),
        FixtureDevice(Q3_SWITCH, "2960-24TT"),
    )
    clients = sum(1 for item in fixtures if item.model == "PC-PT")
    # Baseline 3 (server, clients, native scan); address 3 (E5 send, its
    # read-back, one snapshot); forwarding; client mode 3 + clients (E5 send,
    # one mode read-back per client, the client reading, a snapshot and a
    # scan); server setup 5 (two E6 actions, the server-state read-back, a
    # snapshot and the empty-state scan).
    setup_procedure = 3 + 3 + Q3_FL_FORWARDING_OPERATIONS + (4 + clients) + 5
    # Two background readings, then per client: the pre-request reading, the
    # dispatch, three product read-backs (the server state the acquisition is
    # staged on, the lease and the attribution), the settle readings and a
    # scan.
    per_client = 1 + 1 + 3 + Q3_FL_SETTLE_READS + 1
    acquisition_procedure = 2 + clients * per_client
    repeat_procedure = 2
    timing_procedure = 2 + Q3_FL_RENEWAL_HORIZON_READS + 1
    dhcp_prerequisites = (
        DiagnosticPrecondition.SUBJECT_SESSION,
        DiagnosticPrecondition.INVENTORY_COHERENT,
        DiagnosticPrecondition.SERVER_ADDRESSING,
        DiagnosticPrecondition.POOL_CONFIGURED,
        DiagnosticPrecondition.PROCESS_ENABLED_VERIFIED,
        DiagnosticPrecondition.FORWARDING_OBSERVED,
        DiagnosticPrecondition.CLIENT_DHCP_MODE,
        DiagnosticPrecondition.NATIVE_DEFAULT_PERMITS,
    )
    experiments = [
        ExperimentSpec(
            id="M-DHCP-1",
            hypothesis=(
                "The exact Server-PT interface binds a DHCP process, the "
                "native default moves only by the reviewed realignment and "
                "then stays put, and the ensure-present pool path stores the "
                f"{capacity}-user intended pool."
            ),
            required=True,
            procedure="Q3FL_SERVER",
            planned_operations=setup_procedure,
            operational_prerequisites=(DiagnosticPrecondition.SUBJECT_SESSION,),
            capabilities=(
                "server.dhcp_process_binding",
                "server.dhcp_pool_configuration",
                "server.dhcp_process_enable",
                "server.dhcp_default_pool_observation",
            ),
        ),
        ExperimentSpec(
            id="M-DHCP-4",
            hypothesis="Each exact PC-PT port exposes bounded native MAC text.",
            required=True,
            procedure="Q3FL_SERVER",
            planned_operations=0,
            operational_prerequisites=(DiagnosticPrecondition.SUBJECT_SESSION,),
            capabilities=("client.dhcp_mac_reader",),
        ),
        ExperimentSpec(
            id="M-DHCP-5",
            hypothesis=(
                "HostPort.isDhcpClientOn returns an actual boolean on each "
                "manifest-bound client interface, false before and true after "
                "the typed mode activation, which follows admitted forwarding."
            ),
            required=True,
            procedure="Q3FL_SERVER",
            planned_operations=0,
            operational_prerequisites=(DiagnosticPrecondition.SUBJECT_SESSION,),
            capabilities=(
                "client.dhcp_mode_reader",
                "client.dhcp_mode_activation",
                "network.access_forwarding_observation",
            ),
        ),
        ExperimentSpec(
            id="M-DHCP-2",
            hypothesis=(
                "An explicit getLeaseAt index window keeps each index, return "
                "type, raw row, exception and repetition, and discriminates "
                "the empty, one-row and full states it was calibrated on."
            ),
            required=True,
            procedure="Q3FL_DHCP",
            planned_operations=0,
            operational_prerequisites=dhcp_prerequisites,
            capabilities=("server.dhcp_lease_table",),
        ),
        ExperimentSpec(
            id="M-DHCP-3",
            hypothesis=(
                "Qualification-only dhcpSucceed/dhcpFailed observers receive "
                "bounded events and are released or made inert."
            ),
            required=False,
            procedure="Q3FL_DHCP",
            planned_operations=0,
            capabilities=("engine.dhcp_event_delivery",),
            omission_reason=(
                "qualification_event_source_and_release_not_qualified: the "
                "approved event deferral stands; no observer is registered, "
                "and callbacks, zero-event unregister, dhcpRelease and "
                "resetDhcpConfOn are not qualified by this profile"
            ),
        ),
        ExperimentSpec(
            id="M-DHCP-6",
            hypothesis=(
                "One typed acquisition per admitted client is dispatched at "
                "most once under its claim, and native addressing, an exact "
                "intended or native-default row, calibrated absence and "
                "causal acquisition are established separately."
            ),
            required=True,
            procedure="Q3FL_DHCP",
            planned_operations=acquisition_procedure,
            operational_prerequisites=dhcp_prerequisites,
            capabilities=("client.dhcp_acquisition", "server.dhcp_lease_table"),
        ),
    ]
    steps = [
        DiagnosticStageStep(
            "Q3FL-core",
            "M-DHCP-1",
            "request",
            also_experiments=("M-DHCP-4", "M-DHCP-5", "M-DHCP-2", "M-DHCP-6"),
        ),
    ]
    if capacity == 1:
        experiments.append(
            ExperimentSpec(
                id="M-DHCP-6-CAP",
                hypothesis=(
                    "A second client on the full one-user intended pool gets "
                    "no intended-pool lease, and any address it does get is "
                    "attributed to the pool that holds its row."
                ),
                required=True,
                procedure="Q3FL_DHCP",
                planned_operations=0,
                operational_prerequisites=dhcp_prerequisites,
                capabilities=("client.dhcp_acquisition",),
            )
        )
        steps.append(
            DiagnosticStageStep(
                "Q3FL-capacity", "M-DHCP-6-CAP", "observe", ("Q3FL-core",)
            )
        )
    else:
        experiments.append(
            ExperimentSpec(
                id="M-DHCP-6-CAP",
                hypothesis="The capacity-one negative.",
                required=False,
                procedure="Q3FL_DHCP",
                planned_operations=0,
                omission_reason=(
                    "capacity_one_negative_needs_a_one_user_pool: this "
                    f"profile's intended pool holds {capacity} users; "
                    "Q3-FL-C1 measures it"
                ),
            )
        )
    experiments.extend(
        [
            ExperimentSpec(
                id="M-DHCP-6-REPEAT",
                hypothesis=(
                    "Replaying the identical acquisition after an effect of "
                    "known outcome sends no second dhcpRun."
                ),
                required=True,
                procedure="Q3FL_DHCP",
                planned_operations=repeat_procedure,
                operational_prerequisites=dhcp_prerequisites,
                capabilities=("client.dhcp_acquisition_claim",),
            ),
            ExperimentSpec(
                id="M-DHCP-6-TIME",
                hypothesis=(
                    "Two timed readings with no new request, then the declared "
                    "natural-renewal horizon, keep every raw lease-time value; "
                    "a changed string is not a renewal."
                ),
                required=True,
                procedure="Q3FL_DHCP",
                planned_operations=timing_procedure,
                operational_prerequisites=dhcp_prerequisites,
                capabilities=("client.dhcp_lease_time_reader",),
            ),
            ExperimentSpec(
                id="M-DHCP-6-RENEW",
                hypothesis="A requested renewal under an explicit typed contract.",
                required=False,
                procedure="Q3FL_DHCP",
                planned_operations=0,
                omission_reason=REQUESTED_RENEWAL_CONTRACT_ABSENT,
            ),
            ExperimentSpec(
                id="M-DHCP-1-FINAL",
                hypothesis=(
                    "The pre-cleanup native default and lease tables are "
                    "retained whatever the sequence did, including after a stop."
                ),
                required=True,
                procedure="Q3FL_FINAL",
                planned_operations=2,
                operational_prerequisites=(DiagnosticPrecondition.SUBJECT_SESSION,),
                capabilities=(
                    "server.dhcp_default_pool_observation",
                    "server.dhcp_lease_table",
                ),
                terminal_observation=True,
            ),
        ]
    )
    steps.extend(
        [
            DiagnosticStageStep(
                "Q3FL-repeat", "M-DHCP-6-REPEAT", "request", ("Q3FL-core",)
            ),
            DiagnosticStageStep(
                "Q3FL-timing", "M-DHCP-6-TIME", "observe", ("Q3FL-core",)
            ),
            DiagnosticStageStep(
                "Q3FL-final", "M-DHCP-1-FINAL", "observe", ("Q3FL-core",)
            ),
        ]
    )
    return StageDefinition(
        stage=stage,
        executable=True,
        purpose=(
            "Server-PT DHCP serving pool, calibrated lease table, acquisition "
            f"and attribution on one owned segment with a {capacity}-user "
            "intended pool, under the versioned native-default policy."
        ),
        fixtures=fixtures,
        links=(
            FixtureLink(Q3_SERVER, "FastEthernet0", Q3_SWITCH, "FastEthernet0/1"),
            FixtureLink(Q3_PC1, "FastEthernet0", Q3_SWITCH, "FastEthernet0/2"),
            FixtureLink(Q3_PC2, "FastEthernet0", Q3_SWITCH, "FastEthernet0/3"),
        ),
        setup=(
            PlannedStep("read:executable_build", 1),
            PlannedStep("read:workspace_baseline", 1),
            *(PlannedStep(f"create:{item.name}", 2) for item in fixtures),
            PlannedStep("create:link:1", 2),
            PlannedStep("create:link:2", 2),
            PlannedStep("create:link:3", 2),
            PlannedStep("read:fixture_identity", 1),
        ),
        experiments=tuple(experiments),
        reserve=(
            *(PlannedStep(f"remove:{item.name}", 2) for item in fixtures),
            PlannedStep("read:restoration:1", 1),
            PlannedStep("read:restoration:2", 1),
            PlannedStep("release:run_bag", 1),
        ),
        budget=StageBudget(ceiling_operations, ceiling_seconds, reserve_seconds=300),
        allowed_channels=("file",),
        profile_id=Q3_FL_PROFILE,
        profile_version=Q3_FL_PROFILE_VERSION,
        steps=tuple(steps),
        dhcp_pool_capacity=capacity,
    )


#: The Q3-FL stages, one per intended-pool capacity.
Q3_FL_STAGES = (QualificationStage.Q3_FL_C1, QualificationStage.Q3_FL_C2)
Q3_NATIVE_STAGES = (
    QualificationStage.Q3_NATIVE_PROBE,
    QualificationStage.Q3_NATIVE_SIZE,
)

#: Exact episode-1 physical values, not a formula for a second build or pool.
#: Record SHA-256 1dcf4d95f2c8d20dc22f67950b86c0bb4c0b4dac3e828d88ae4a2d31494fa9c1.
Q3_NATIVE_START_EVIDENCE_SHA256 = (
    "1dcf4d95f2c8d20dc22f67950b86c0bb4c0b4dac3e828d88ae4a2d31494fa9c1"
)
Q3_NATIVE_START_BEFORE = MappingProxyType(
    {
        "name": "serverPool",
        "network": "192.0.2.0",
        "mask": "255.255.255.0",
        "gateway": "0.0.0.0",
        "dns": "0.0.0.0",
        "start": "192.0.2.0",
        "end": "192.0.3.255",
        "max": 512,
    }
)
Q3_NATIVE_START_AFTER = MappingProxyType(
    {**Q3_NATIVE_START_BEFORE, "start": "192.0.2.100", "end": "192.0.2.255", "max": 156}
)


def _q3_native_probe() -> StageDefinition:
    """Probe one documented setter in the existing owned Q3 fixture."""
    base = _q3_fastloop(QualificationStage.Q3_FL_C1, 1)
    return replace(
        base,
        stage=QualificationStage.Q3_NATIVE_PROBE,
        purpose=(
            "Measure whether documented setStartIp changes the physical "
            "native serverPool on an owned Server-PT after static addressing."
        ),
        experiments=(
            ExperimentSpec(
                id="M-NATIVE-START",
                hypothesis=(
                    "The native serverPool start address can be changed and "
                    "read back without altering its other policy fields."
                ),
                required=True,
                procedure="Q3_NATIVE_START",
                planned_operations=6,
                operational_prerequisites=(DiagnosticPrecondition.SUBJECT_SESSION,),
                capabilities=("server.dhcp_native_pool_start",),
            ),
            ExperimentSpec(
                id="M-NATIVE-FINAL",
                hypothesis="The final native-pool inventory is observed before cleanup.",
                required=True,
                procedure="Q3_NATIVE_FINAL",
                planned_operations=1,
                terminal_observation=True,
            ),
        ),
        budget=StageBudget(120, 600, reserve_seconds=300),
        profile_id="Q3-NATIVE",
        profile_version="1",
        steps=(
            DiagnosticStageStep(
                id="NATIVE-start",
                experiment_id="M-NATIVE-START",
                effect="configure",
                also_experiments=("M-NATIVE-FINAL",),
            ),
        ),
    )


def _q3_native_size() -> StageDefinition:
    """Measure the native capacity setter after the exact observed start move."""
    base = _q3_native_probe()
    return replace(
        base,
        stage=QualificationStage.Q3_NATIVE_SIZE,
        purpose=(
            "Repeat the episode-1 coupled native start transition, then "
            "measure one documented setMaxUsers(1) on the same disabled pool."
        ),
        experiments=(
            ExperimentSpec(
                id="M-NATIVE-REPEAT-START",
                hypothesis=(
                    "The exact coupled serverPool start/end/max transition "
                    "of delegated episode 1 repeats on this build."
                ),
                required=True,
                procedure="Q3_NATIVE_REPEAT_START",
                planned_operations=6,
                operational_prerequisites=(DiagnosticPrecondition.SUBJECT_SESSION,),
                capabilities=("server.dhcp_native_pool_start",),
            ),
            ExperimentSpec(
                id="M-NATIVE-MAX",
                hypothesis=(
                    "setMaxUsers(1) makes the effective native allocation "
                    "exactly 192.0.2.100, with no other field or process change."
                ),
                required=True,
                procedure="Q3_NATIVE_MAX",
                planned_operations=2,
                prerequisites=("M-NATIVE-REPEAT-START",),
                capabilities=("server.dhcp_native_pool_max",),
            ),
            ExperimentSpec(
                id="M-NATIVE-FINAL",
                hypothesis="The final native-pool inventory is observed before cleanup.",
                required=True,
                procedure="Q3_NATIVE_FINAL",
                planned_operations=1,
                terminal_observation=True,
            ),
        ),
        profile_id="Q3-NATIVE-SIZE",
        profile_version="1",
        steps=(
            DiagnosticStageStep(
                id="NATIVE-size",
                experiment_id="M-NATIVE-REPEAT-START",
                effect="configure",
                also_experiments=("M-NATIVE-MAX", "M-NATIVE-FINAL"),
            ),
        ),
    )


STAGE_DEFINITIONS: dict[QualificationStage, StageDefinition] = {
    QualificationStage.Q0: _q0(),
    QualificationStage.Q1: _q1(),
    QualificationStage.Q2: _declarative(
        QualificationStage.Q2,
        "Mail engine facts (declarative only in S4a).",
        ("S2 is not implemented", "a Q0 record is required"),
    ),
    QualificationStage.Q3: _q3(),
    QualificationStage.D_DHCP: _d_dhcp(),
    QualificationStage.D_WEB: _d_web(),
    QualificationStage.Q3_FL_C1: _q3_fastloop(QualificationStage.Q3_FL_C1, 1),
    QualificationStage.Q3_FL_C2: _q3_fastloop(QualificationStage.Q3_FL_C2, 2),
    QualificationStage.Q3_NATIVE_PROBE: _q3_native_probe(),
    QualificationStage.Q3_NATIVE_SIZE: _q3_native_size(),
}


def stage_definition(stage: object) -> StageDefinition | None:
    """Return the fixed definition of a known stage, or None."""
    try:
        return STAGE_DEFINITIONS[QualificationStage(str(stage))]
    except ValueError:
        return None


# -- request admission ---------------------------------------------------------


class RefusalKind(StrEnum):
    """Why one admission value failed."""

    __str__ = Enum.__str__

    MISSING = "missing"
    MISMATCH = "mismatch"
    MALFORMED = "malformed"
    UNOBSERVABLE = "unobservable"
    NOT_PERMITTED = "not_permitted"
    INFEASIBLE = "infeasible"


class RefusalSubject(StrEnum):
    """Which admission value failed."""

    __str__ = Enum.__str__

    EXECUTION = "execution"
    STAGE = "stage"
    EXPECTED_HEAD = "expected_head"
    AUTHORIZATION = "authorization"
    AUTHORIZATION_ID = "authorization_id"
    AUTHORIZED_STAGE = "authorized_stage"
    AUTHORIZED_SHA = "authorized_sha"
    TARGETS = "targets"
    AUTHORIZED_TARGETS = "authorized_targets"
    CHANNEL = "channel"
    AUTHORIZED_CHANNEL = "authorized_channel"
    BUILD = "build"
    AUTHORIZED_BUILD = "authorized_build"
    BUDGET = "budget"
    #: Only an executable diagnostic stage binds these. They are the identity
    #: half of the execution authority: what is being run, against which exact
    #: tree, on which exact fixture models and ports, in which order, with
    #: which reserve, and under which single unrepeatable attempt.
    AUTHORIZED_PROFILE = "authorized_profile"
    AUTHORIZED_TREE = "authorized_tree"
    AUTHORIZED_MODELS = "authorized_models"
    AUTHORIZED_LINKS = "authorized_links"
    AUTHORIZED_STEPS = "authorized_steps"
    AUTHORIZED_RESERVE = "authorized_reserve"
    AUTHORIZED_PROCESS = "authorized_process"
    INSTANCE_TOKEN = "instance_token"
    ATTEMPT_IDENTITY = "attempt_identity"
    GOVERNED_ROOT = "governed_root"
    PROCESS_ISOLATION = "process_isolation"
    PROCESS_INSTANCE = "process_instance"
    MAILBOX = "mailbox"
    REPOSITORY_HEAD = "repository_head"
    REPOSITORY_TREE = "repository_tree"
    REPOSITORY_CLEAN = "repository_clean"
    REPOSITORY_UPSTREAM = "repository_upstream"
    FIXTURE = "fixture"
    RECORD = "record"
    TRANSPORT = "transport"
    EXECUTABLE_BUILD = "executable_build"
    WORKSPACE = "workspace"


class QualificationRefusal(BaseModel):
    """One typed admission refusal."""

    kind: RefusalKind
    subject: RefusalSubject
    detail: str = ""


def refusal(
    kind: RefusalKind, subject: RefusalSubject, detail: str = ""
) -> QualificationRefusal:
    """Build one refusal with a bounded detail."""
    return QualificationRefusal(kind=kind, subject=subject, detail=detail[:240])


@dataclass(frozen=True)
class QualificationAuthorization:
    """The reviewer's stage- and SHA-specific scope, as the operator typed it.

    Fields are kept raw so that malformed values can be named precisely rather
    than rejected by a parser before the rule sees them.
    """

    authorization_id: str
    stage: str
    sha: str
    targets: tuple[str, ...]
    channel: str
    build: str
    max_operations: int | None
    max_seconds: int | None
    #: The diagnostic half. Every field is empty for Q0/Q1/Q3, whose
    #: authorization is exactly what it always was, and every field is
    #: required by a stage that declares a profile. None of it is prose: each
    #: one is compared against a value the stage definition or the observed
    #: checkout already fixes.
    profile_id: str = ""
    profile_version: str = ""
    tree: str = ""
    models: tuple[str, ...] = ()
    links: tuple[str, ...] = ()
    step_ids: tuple[str, ...] = ()
    reserve_operations: int | None = None
    instance_token: str = ""
    attempt_id: str = ""
    process_id: int | None = None
    process_path: str = ""


@dataclass(frozen=True)
class DiagnosticLifecycleObservation:
    """Read-only local facts that bind one future diagnostic process.

    The reader reports one process only after it established exclusivity. An
    error represents zero, multiple or unreadable processes. Mailbox entries
    include request, response and temporary command artifacts but exclude the
    heartbeat, whose freshness is liveness rather than process identity.

    `process_incarnation` is the bound process's observed creation identity. A
    PID and a path name a slot the operating system reuses; a second Packet
    Tracer started into the same PID polls the same mailbox and would
    otherwise satisfy a pairing it never earned. An empty value is an
    unobserved incarnation, which is unknown and never a match.
    """

    process_id: int | None = None
    process_path: str = ""
    product_version: str = ""
    file_version: str = ""
    process_incarnation: str = ""
    mailbox_entries: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class QualificationRequest:
    """One explicit request to run one stage; there is no all-stages form."""

    execute: bool
    stage: str
    expected_head: str
    targets: tuple[str, ...]
    channel: str
    packet_tracer_build: str
    authorization: QualificationAuthorization | None


def _target_refusals(
    values: tuple[str, ...],
    expected: tuple[str, ...],
    subject: RefusalSubject,
) -> list[QualificationRefusal]:
    if not values:
        return [refusal(RefusalKind.MISSING, subject, "No fixture target was named.")]
    if any(not isinstance(item, str) or not item.strip() for item in values):
        return [refusal(RefusalKind.MALFORMED, subject, "A target is empty.")]
    if len(set(values)) != len(values):
        return [refusal(RefusalKind.MALFORMED, subject, "A target is repeated.")]
    if set(values) != set(expected):
        return [
            refusal(
                RefusalKind.MISMATCH,
                subject,
                f"Targets {sorted(values)} are not the stage fixtures "
                f"{sorted(expected)}.",
            )
        ]
    return []


def request_refusals(
    request: QualificationRequest,
) -> tuple[QualificationRefusal, ...]:
    """Decide admissibility from the request alone, before any reader runs.

    Every value an authorization must bind is checked here: the explicit
    execution flag, a known and executable stage that fits its ceiling, the
    expected head, the exact fixture list, the channel, the exact build and the
    budget. The repository, process and backend facts are compared later, by
    the rules that consume their observations.
    """
    if request.execute is not True:
        return (
            refusal(
                RefusalKind.MISSING,
                RefusalSubject.EXECUTION,
                "Explicit execution was not requested; nothing is run by default.",
            ),
        )
    definition = stage_definition(request.stage)
    if definition is None:
        return (
            refusal(
                RefusalKind.MALFORMED,
                RefusalSubject.STAGE,
                f"Unknown stage {request.stage!r}; one of "
                f"{[item.value for item in QualificationStage]} is required.",
            ),
        )
    if not definition.executable:
        return (
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.STAGE,
                f"Stage {definition.stage.value} is declarative in S4a; unmet: "
                + "; ".join(definition.unmet_prerequisites),
            ),
        )
    if definition.planned_minimum_operations > definition.budget.max_operations:
        return (
            refusal(
                RefusalKind.INFEASIBLE,
                RefusalSubject.BUDGET,
                f"Stage {definition.stage.value} needs at least "
                f"{definition.planned_minimum_operations} bridge operations "
                f"(setup {definition.setup_operations}, required experiments "
                f"{definition.required_experiment_operations}, finalization "
                f"reserve {definition.reserve_operations}); its ceiling is "
                f"{definition.budget.max_operations}. The ceiling is not raised "
                "here; this is a review decision.",
            ),
        )

    found: list[QualificationRefusal] = []
    if not request.expected_head:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.EXPECTED_HEAD))
    elif not is_full_sha(request.expected_head):
        found.append(
            refusal(
                RefusalKind.MALFORMED,
                RefusalSubject.EXPECTED_HEAD,
                "Expected HEAD must be 40 lowercase hexadecimal characters.",
            )
        )
    found.extend(
        _target_refusals(
            request.targets, definition.fixture_names, RefusalSubject.TARGETS
        )
    )
    if not request.channel:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.CHANNEL))
    elif request.channel not in ALLOWED_CHANNELS:
        found.append(
            refusal(
                RefusalKind.MALFORMED,
                RefusalSubject.CHANNEL,
                f"Channel must be one of {list(ALLOWED_CHANNELS)}.",
            )
        )
    elif request.channel not in definition.allowed_channels:
        return (
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.CHANNEL,
                f"Stage {definition.stage.value} permits only "
                f"{list(definition.allowed_channels)}.",
            ),
        )
    if not request.packet_tracer_build:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.BUILD))
    elif not is_exact_packet_tracer_build(request.packet_tracer_build):
        found.append(
            refusal(
                RefusalKind.MALFORMED,
                RefusalSubject.BUILD,
                "The build must be one exact four-component version.",
            )
        )
    found.extend(_authorization_refusals(request, definition))
    return tuple(found)


def _authorization_refusals(
    request: QualificationRequest, definition: StageDefinition
) -> list[QualificationRefusal]:
    authorization = request.authorization
    if authorization is None:
        return [
            refusal(
                RefusalKind.MISSING,
                RefusalSubject.AUTHORIZATION,
                f"Stage {definition.stage.value} requires its own stage- and "
                "SHA-specific authorization.",
            )
        ]
    found: list[QualificationRefusal] = []
    identifier = authorization.authorization_id
    if not identifier or not identifier.strip():
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZATION_ID))
    elif len(identifier) > MAX_AUTHORIZATION_ID_LENGTH or any(
        not character.isprintable() for character in identifier
    ):
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZATION_ID))
    if not authorization.stage:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_STAGE))
    elif stage_definition(authorization.stage) is None:
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_STAGE))
    elif authorization.stage != definition.stage.value:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_STAGE,
                f"Authorization for {authorization.stage} does not authorize "
                f"{definition.stage.value}.",
            )
        )
    if not authorization.sha:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_SHA))
    elif not is_full_sha(authorization.sha):
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_SHA))
    elif authorization.sha != request.expected_head:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_SHA,
                "The authorized SHA is not the expected HEAD.",
            )
        )
    found.extend(
        _target_refusals(
            authorization.targets,
            definition.fixture_names,
            RefusalSubject.AUTHORIZED_TARGETS,
        )
    )
    if not authorization.channel:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_CHANNEL))
    elif authorization.channel not in ALLOWED_CHANNELS:
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_CHANNEL))
    elif authorization.channel != request.channel:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_CHANNEL,
                "One channel per authorization; the selected channel differs.",
            )
        )
    if not authorization.build:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_BUILD))
    elif not is_exact_packet_tracer_build(authorization.build):
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_BUILD))
    elif authorization.build != request.packet_tracer_build:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_BUILD,
                "The authorized build is not the requested build.",
            )
        )
    budget = (authorization.max_operations, authorization.max_seconds)
    ceiling = (definition.budget.max_operations, definition.budget.max_seconds)
    if None in budget:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.BUDGET))
    elif any(isinstance(item, bool) or not isinstance(item, int) for item in budget):
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.BUDGET))
    elif budget != ceiling:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.BUDGET,
                f"Authorized budget {budget} is not the stage ceiling {ceiling}.",
            )
        )
    found.extend(_diagnostic_authorization_refusals(authorization, definition))
    return found


def step_selection_refusals(
    definition: StageDefinition, selection: Sequence[str]
) -> list[QualificationRefusal]:
    """Decide whether one step selection is a coherent thing to authorize.

    Four independent ways to be incoherent, and each refuses on its own: a
    step the stage does not define, a step named twice, a selection that is
    not in the stage's declared order, and a selection that omits a step
    another selected step requires. A selection made only of separately
    authorized steps refuses too: activating a process without the sequence
    that establishes what it is being activated on measures nothing, and an
    authorization that names only the activation is not a decision about the
    experiment.

    This is admission, not execution. Passing it never means the run may skip
    state it has not established -- that is still decided, in the run, by the
    measurement prerequisites.
    """
    found: list[QualificationRefusal] = []
    chosen = list(selection)
    if not chosen:
        return [refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_STEPS)]
    known = definition.step_ids
    unknown = [item for item in chosen if item not in known]
    if unknown:
        found.append(
            refusal(
                RefusalKind.MALFORMED,
                RefusalSubject.AUTHORIZED_STEPS,
                f"Step {unknown[0]!r} is not defined by {definition.stage.value}.",
            )
        )
        return found
    if len(set(chosen)) != len(chosen):
        found.append(
            refusal(
                RefusalKind.MALFORMED,
                RefusalSubject.AUTHORIZED_STEPS,
                "A step is selected more than once.",
            )
        )
    ordered = [item for item in known if item in set(chosen)]
    if ordered != chosen:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_STEPS,
                "The selection is not in the stage's declared step order.",
            )
        )
    selected = set(chosen)
    for index, item in enumerate(chosen):
        missing = [
            value
            for value in definition.step(item).requires
            if value not in selected or chosen.index(value) > index
        ]
        if missing:
            found.append(
                refusal(
                    RefusalKind.INFEASIBLE,
                    RefusalSubject.AUTHORIZED_STEPS,
                    f"Step {item!r} requires {missing[0]!r} before it.",
                )
            )
            break
    if all(definition.step(item).separately_authorized for item in chosen):
        found.append(
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.AUTHORIZED_STEPS,
                "An activation-only selection authorizes no measurement.",
            )
        )
    return found


def _diagnostic_authorization_refusals(
    authorization: QualificationAuthorization, definition: StageDefinition
) -> list[QualificationRefusal]:
    """Check the identity half an executable diagnostic stage binds.

    A stage without a profile binds none of it, and a value supplied for a
    stage that does not bind it is refused rather than ignored: an
    authorization carrying scope the stage cannot honour is not a coherent
    decision about this run.
    """
    supplied = (
        authorization.profile_id
        or authorization.profile_version
        or authorization.tree
        or authorization.models
        or authorization.links
        or authorization.step_ids
        or authorization.reserve_operations is not None
        or authorization.instance_token
        or authorization.attempt_id
        or authorization.process_id is not None
        or authorization.process_path
    )
    if not definition.profile_id:
        if supplied:
            return [
                refusal(
                    RefusalKind.NOT_PERMITTED,
                    RefusalSubject.AUTHORIZED_PROFILE,
                    f"Stage {definition.stage.value} binds no diagnostic profile.",
                )
            ]
        return []
    found: list[QualificationRefusal] = []
    if not authorization.profile_id or not authorization.profile_version:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_PROFILE))
    elif (authorization.profile_id, authorization.profile_version) != (
        definition.profile_id,
        definition.profile_version,
    ):
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_PROFILE,
                f"Authorization names {authorization.profile_id}"
                f"@{authorization.profile_version}, not "
                f"{definition.profile_id}@{definition.profile_version}.",
            )
        )
    if not authorization.tree:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_TREE))
    elif not is_full_sha(authorization.tree):
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_TREE))
    if not authorization.models:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_MODELS))
    elif tuple(authorization.models) != definition.fixture_models:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_MODELS,
                "The authorized fixture models are not the stage's exact models.",
            )
        )
    if not authorization.links:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_LINKS))
    elif tuple(authorization.links) != definition.link_bindings:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_LINKS,
                "The authorized link ports are not the stage's exact ports.",
            )
        )
    reserve = authorization.reserve_operations
    if reserve is None:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_RESERVE))
    elif isinstance(reserve, bool) or not isinstance(reserve, int):
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_RESERVE))
    elif reserve != definition.reserve_operations:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.AUTHORIZED_RESERVE,
                f"Authorized cleanup reserve {reserve} is not the stage's "
                f"{definition.reserve_operations}.",
            )
        )
    process_id = authorization.process_id
    if process_id is None or not authorization.process_path:
        found.append(refusal(RefusalKind.MISSING, RefusalSubject.AUTHORIZED_PROCESS))
    elif isinstance(process_id, bool) or not isinstance(process_id, int):
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_PROCESS))
    elif process_id <= 0:
        found.append(refusal(RefusalKind.MALFORMED, RefusalSubject.AUTHORIZED_PROCESS))
    found.extend(_identity_token_refusals(authorization))
    found.extend(step_selection_refusals(definition, authorization.step_ids))
    return found


def diagnostic_lifecycle_refusals(
    authorization: QualificationAuthorization,
    observed: DiagnosticLifecycleObservation,
    requested_build: str,
) -> tuple[QualificationRefusal, ...]:
    """Bind a diagnostic authorization to one exclusive local PT process.

    This is a read-only, pre-transport gate. It never launches, stops or
    contacts Packet Tracer and never deletes mailbox artifacts. The later
    workspace observation remains responsible for proving an empty disposable
    document before the first effect.
    """
    if observed.error:
        return (
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.PROCESS_INSTANCE,
                observed.error,
            ),
        )
    found: list[QualificationRefusal] = []
    if (
        observed.process_id != authorization.process_id
        or observed.process_path != authorization.process_path
    ):
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.PROCESS_INSTANCE,
                "The observed Packet Tracer PID/path does not match authorization.",
            )
        )
    if not observed.process_incarnation:
        # A PID and a path name a slot, not a process. Without the creation
        # identity there is nothing later readings could be compared against,
        # so the pairing cannot be bound at all.
        found.append(
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.PROCESS_INSTANCE,
                "The observed Packet Tracer process reports no creation identity.",
            )
        )
    versions = tuple(
        value for value in (observed.product_version, observed.file_version) if value
    )
    if requested_build not in versions:
        found.append(
            refusal(
                RefusalKind.MISMATCH if versions else RefusalKind.UNOBSERVABLE,
                RefusalSubject.PROCESS_INSTANCE,
                "The observed Packet Tracer process does not report the exact build.",
            )
        )
    if observed.mailbox_entries:
        found.append(
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.MAILBOX,
                "The file mailbox contains stale command artifacts: "
                + ", ".join(observed.mailbox_entries[:8]),
            )
        )
    return tuple(found)


def diagnostic_lifecycle_continuity(
    preflight: DiagnosticLifecycleObservation | None,
    observed: DiagnosticLifecycleObservation,
) -> tuple[str, ...]:
    """Name what a second local reading says about the first one, if anything.

    The preflight binds one process before a transport exists. Nothing keeps
    that process alive for the rest of the run: a Packet Tracer that crashes
    is replaced by an instance that polls the same mailbox, and every reading
    taken afterwards, owned cleanup included, would then describe a process
    this authority never bound. Reading the pairing again after finalization
    is what turns that into evidence instead of an assumption.

    This is a read-only comparison of two local observations. It contacts
    nothing, deletes no mailbox artifact and costs no bridge operation, so it
    stays affordable when the ledger is exhausted. It returns residue reasons
    rather than refusals: the run already happened, and what is in question is
    whether its positive claims still describe the authorized instance.
    """
    if preflight is None or preflight.error:
        return ("process_instance:not_paired",)
    if observed.error:
        return (f"process_instance:unobservable:{observed.error}",)
    found: list[str] = []
    if not observed.process_incarnation or not preflight.process_incarnation:
        # An unobserved creation identity is unknown, and unknown is not the
        # same process. A reused PID at the authorized path would otherwise
        # pass this comparison on the strength of the slot alone.
        found.append("process_instance:incarnation_unobserved")
    elif _process_identity(observed) != _process_identity(preflight):
        found.append("process_instance:changed")
    if observed.mailbox_entries:
        found.append("mailbox:not_drained:" + ",".join(observed.mailbox_entries[:8]))
    return tuple(found)


def _process_identity(
    observed: DiagnosticLifecycleObservation,
) -> tuple[int | None, str, str, str, str]:
    """Return the local facts that together name one Packet Tracer incarnation."""
    return (
        observed.process_id,
        observed.process_path,
        observed.product_version,
        observed.file_version,
        observed.process_incarnation,
    )


def _identity_token_refusals(
    authorization: QualificationAuthorization,
) -> list[QualificationRefusal]:
    """Require one fresh instance token and one distinct attempt identity."""
    found: list[QualificationRefusal] = []
    for value, subject in (
        (authorization.instance_token, RefusalSubject.INSTANCE_TOKEN),
        (authorization.attempt_id, RefusalSubject.ATTEMPT_IDENTITY),
    ):
        if not value:
            found.append(refusal(RefusalKind.MISSING, subject))
        elif not _HEX_TOKEN.fullmatch(value):
            found.append(
                refusal(
                    RefusalKind.MALFORMED,
                    subject,
                    "A token must be 32 lowercase hexadecimal characters.",
                )
            )
    if (
        authorization.instance_token
        and authorization.instance_token == authorization.attempt_id
    ):
        # One value cannot be both the process this attempt runs in and the
        # attempt itself: reusing it would make a second attempt in the same
        # process indistinguishable from the first.
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.ATTEMPT_IDENTITY,
                "The attempt identity repeats the instance token.",
            )
        )
    return found


@dataclass(frozen=True)
class RepositoryIdentity:
    """One coherent observation of the executing checkout."""

    branch: str = ""
    head: str = ""
    tree: str = ""
    clean: bool | None = None
    upstream: str = ""
    upstream_head: str = ""
    error: str = ""


def repository_refusals(
    observed: RepositoryIdentity, expected_head: str, expected_tree: str = ""
) -> tuple[QualificationRefusal, ...]:
    """Require the exact, clean, published checkout the authorization names.

    A value that could not be observed is unobservable, never a pass: the
    record must be able to name the executed SHA and tree, and a reviewer must
    be able to inspect that SHA, which is why HEAD must be published.

    `expected_tree` is bound only by an authority that names one. A commit
    identifies a history; the tree identifies the bytes that will actually
    execute, and a diagnostic authorization binds both.
    """
    found: list[QualificationRefusal] = []
    if observed.error or not observed.head:
        found.append(
            refusal(
                RefusalKind.UNOBSERVABLE,
                RefusalSubject.REPOSITORY_HEAD,
                observed.error or "Repository HEAD was not observed.",
            )
        )
    elif observed.head != expected_head:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.REPOSITORY_HEAD,
                f"Observed HEAD {observed.head!r} is not {expected_head!r}.",
            )
        )
    if not observed.tree:
        found.append(refusal(RefusalKind.UNOBSERVABLE, RefusalSubject.REPOSITORY_TREE))
    elif expected_tree and observed.tree != expected_tree:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.REPOSITORY_TREE,
                f"Observed tree {observed.tree!r} is not {expected_tree!r}.",
            )
        )
    if observed.clean is None:
        found.append(refusal(RefusalKind.UNOBSERVABLE, RefusalSubject.REPOSITORY_CLEAN))
    elif observed.clean is False:
        found.append(
            refusal(
                RefusalKind.NOT_PERMITTED,
                RefusalSubject.REPOSITORY_CLEAN,
                "A qualification run requires a clean worktree.",
            )
        )
    if not observed.upstream_head:
        found.append(
            refusal(RefusalKind.UNOBSERVABLE, RefusalSubject.REPOSITORY_UPSTREAM)
        )
    elif observed.upstream_head != observed.head:
        found.append(
            refusal(
                RefusalKind.MISMATCH,
                RefusalSubject.REPOSITORY_UPSTREAM,
                "The executed HEAD must be published as its upstream.",
            )
        )
    return tuple(found)


# -- measurements and records ------------------------------------------------


class MeasurementStatus(StrEnum):
    """Whether one declared measurement ran."""

    __str__ = Enum.__str__

    RAN = "ran"
    OMITTED = "omitted"
    NOT_RUN = "not_run"
    INTERRUPTED = "interrupted"


class MeasurementConclusion(StrEnum):
    """What the observations of one measurement support, and no more."""

    __str__ = Enum.__str__

    SUPPORTED_IN_SAMPLE = "supported_in_sample"
    NEGATIVE_OBSERVED = "negative_observed"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"
    NOT_EVALUATED = "not_evaluated"


class MeasurementRecord(BaseModel):
    """One measurement's hypothesis, what ran and what it supports."""

    experiment_id: str
    hypothesis: str
    required: bool
    status: MeasurementStatus
    conclusion: MeasurementConclusion = MeasurementConclusion.NOT_EVALUATED
    facts: dict[str, Any] = Field(default_factory=dict)
    causes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reason: str = ""
    #: Whether an effect of this measurement has an unknown outcome. It is the
    #: stop signal for later experiments and it is never cleared by cleanup.
    outcome_unknown: bool = False


class QualificationOutcome(StrEnum):
    """How one invocation ended."""

    __str__ = Enum.__str__

    REFUSED = "refused"
    COMPLETED = "completed"
    STOPPED = "stopped"


class OperationEntry(BaseModel):
    """One ledger line: a counted dispatch, or a call refused before dispatch."""

    seq: int
    phase: str
    call: str
    purpose: str
    timeout_seconds: float = 0.0
    started_offset_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    dispatch: str = ""
    result: str = ""
    refused: str = ""


class ReleaseRecord(BaseModel):
    """What happened to one owned resource at finalization."""

    resource: str
    kind: Literal["device", "bag", "observer", "client", "claim"]
    outcome: str
    detail: str = ""


class DefaultPoolObservation(BaseModel):
    """One bounded native default-pool reading, exactly as it was taken.

    The entry is written when the reading returns, not when a measurement is
    concluded, so a reading taken after a stop or during finalization is still
    durable evidence of the run. `purpose` is the label the operation was
    dispatched under and `operation_seq` is the ledger sequence of the counted
    call; `operation_seq` is 0 exactly when no operation was counted, which is
    also when `observed` is false and `cause` says why.
    """

    label: str
    purpose: str = ""
    operation_seq: int = 0
    observed: bool = False
    cause: str = ""
    pools: list[dict[str, Any]] = Field(default_factory=list)
    intended_pool_present: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)
    #: Every difference this reading shows against the run's first reading.
    differences: list[str] = Field(default_factory=list)


class QualificationTransition(BaseModel):
    """One write-ahead step boundary."""

    step: str
    at: datetime
    outcome: str = ""


class SourceIdentity(BaseModel):
    """The checkout that executed the run."""

    expected_head: str = ""
    executed_sha: str = ""
    executed_tree: str = ""
    clean: bool | None = None
    branch: str = ""
    upstream: str = ""
    upstream_head: str = ""


class EnvironmentIdentity(BaseModel):
    """The process and backend the run observed."""

    python_executable: str = ""
    package_file: str = ""
    isolation_state: str = ""
    requested_build: str = ""
    observed_build: str = ""
    build_reader_id: str = ""
    build_reader_sha256: str = ""
    build_observation: str = ""
    build_reason: str = ""


class TransportIdentity(BaseModel):
    """The one channel fixed for the whole invocation."""

    channel: str = ""
    fixed_at: datetime | None = None
    liveness: str = ""


class FixtureRecord(BaseModel):
    """One fixture device, what the run did to it and whether it owns it."""

    name: str
    model: str
    ipv4: str = ""
    netmask: str = ""
    dns_server: str = ""
    creation: str = "not_attempted"
    owned: bool = False
    detail: str = ""


class BudgetRecord(BaseModel):
    """The authorized ceiling, the reserve and what was used."""

    max_operations: int
    max_seconds: int
    reserve_operations: int
    reserve_seconds: int
    planned_minimum_operations: int
    used_operations: int = 0
    refused_calls: int = 0
    elapsed_seconds: float = 0.0
    #: Wall-clock seconds spent on bounded LOCAL authority observations, which
    #: contact Packet Tracer through nothing and spend no operation. Spending
    #: no operation is not the same as costing no time, so the phase that
    #: waited for them says how long it waited.
    local_observation_seconds: float = 0.0


class QualificationRecord(BaseModel):
    """The durable statement of one qualification invocation (plan 4.8).

    Records are written ahead of every effectful step and are never rewritten
    once completed. An `offline_simulation` record is evidence about this
    runner's code only; it can never qualify a Packet Tracer capability.
    """

    schema_version: Literal[1] = 1
    record_kind: Literal["server_services_qualification"] = (
        "server_services_qualification"
    )
    run_id: str
    stage: QualificationStage
    execution_mode: ExecutionMode
    created_at: datetime
    completed_at: datetime | None = None
    authorization: dict[str, Any] = Field(default_factory=dict)
    source: SourceIdentity = Field(default_factory=SourceIdentity)
    environment: EnvironmentIdentity = Field(default_factory=EnvironmentIdentity)
    transport: TransportIdentity = Field(default_factory=TransportIdentity)
    fixtures: list[FixtureRecord] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)
    budget: BudgetRecord
    experimental_capabilities: list[str] = Field(default_factory=list)
    operations: list[OperationEntry] = Field(default_factory=list)
    transitions: list[QualificationTransition] = Field(default_factory=list)
    persisted_step: str = ""
    admission_reads: list[str] = Field(default_factory=list)
    #: Read-only local process and mailbox evidence for executable diagnostics.
    #: Empty by default so historical schema-1 records remain valid without
    #: being upgraded or granted authority they never recorded.
    diagnostic_lifecycle: dict[str, Any] = Field(default_factory=dict)
    #: The same read-only reading taken again after owned finalization.
    #: Nothing keeps the bound process alive for the whole run, so the
    #: cleanup and restoration evidence above is only about the authorized
    #: instance while this reading still names it. Empty on a historical
    #: record, which is an absent observation and never a proven one.
    diagnostic_lifecycle_postflight: dict[str, Any] = Field(default_factory=dict)
    #: The complete pre-creation inventory, engine-managed objects included,
    #: exactly as the restoration reads are later compared against it.
    workspace_baseline: dict[str, Any] = Field(default_factory=dict)
    refusals: list[QualificationRefusal] = Field(default_factory=list)
    #: Every bounded native default-pool reading the run took, in order. This
    #: is the authoritative sink: a measurement projects from it, and nothing
    #: else holds these readings, so one taken after the last conclusion still
    #: reaches the terminal record.
    native_default_pool: list[DefaultPoolObservation] = Field(default_factory=list)
    measurements: list[MeasurementRecord] = Field(default_factory=list)
    primary_failure: str = ""
    secondary_failures: list[str] = Field(default_factory=list)
    releases: list[ReleaseRecord] = Field(default_factory=list)
    restoration: list[dict[str, Any]] = Field(default_factory=list)
    restoration_proven: bool = False
    engine_residue: list[str] = Field(default_factory=list)
    #: What this invocation could not finalize in the LOCAL coordination scope
    #: it shares with other checkouts -- a campaign lock it could not release,
    #: a claim that is no longer its own. It is deliberately not
    #: `engine_residue`: a lock left behind blocks the next campaign, and says
    #: nothing at all about whether the engine workspace was restored. Empty
    #: on a historical record, which is an absent observation, never a clean
    #: one.
    coordination_residue: list[str] = Field(default_factory=list)
    dirty_state: DirtyState = DirtyState.UNKNOWN
    persist_error: str = ""
    limitations: list[str] = Field(default_factory=list)
    outcome: QualificationOutcome = QualificationOutcome.STOPPED


def promotion_evidence_refusal(
    record: QualificationRecord,
    *,
    stage: QualificationStage,
    executed_sha: str,
    build: str,
    channel: str,
) -> str:
    """Return why a record cannot support a promotion, or "" if nothing blocks it.

    This is the gate a later slice must pass a record through; S4a promotes
    nothing. A record measured at another SHA is never relabeled as a later
    SHA's measurement (R-QUAL-05): the reviewer-approved equivalence argument
    is not modelled here, so a mismatch refuses.
    """
    if record.execution_mode is not ExecutionMode.LIVE:
        return "An offline simulation record can never qualify a capability."
    if record.outcome is not QualificationOutcome.COMPLETED:
        return f"The run did not complete (outcome {record.outcome.value})."
    if record.stage is not stage:
        return f"The record is stage {record.stage.value}, not {stage.value}."
    if not is_full_sha(record.source.executed_sha):
        return "The record does not name an executed SHA."
    if record.source.executed_sha != executed_sha:
        return (
            f"The record measured {record.source.executed_sha}, not "
            f"{executed_sha}; a result is never relabeled to another SHA."
        )
    if record.source.clean is not True:
        return "The executed checkout was not proven clean."
    if record.environment.observed_build != build:
        return "The record's observed build differs from the required build."
    if record.transport.channel != channel:
        return "The record's channel differs; no channel authorizes another."
    if stage in (QualificationStage.D_DHCP, QualificationStage.D_WEB):
        lifecycle = record.diagnostic_lifecycle
        if not lifecycle or lifecycle.get("error"):
            return "The diagnostic record has no coherent local process pairing."
        if lifecycle.get("mailbox_entries"):
            return "The diagnostic began with stale file-mailbox artifacts."
        exit_pairing = record.diagnostic_lifecycle_postflight
        if not exit_pairing or exit_pairing.get("error"):
            return (
                "The diagnostic did not observe its process pairing after finalization."
            )
        if exit_pairing.get("mailbox_entries"):
            return "The diagnostic left stale file-mailbox artifacts behind."
        if any(
            exit_pairing.get(name) != lifecycle.get(name)
            for name in ("process_id", "process_path", "product_version")
        ):
            return (
                "The Packet Tracer process changed during the diagnostic, so "
                "its cleanup evidence is not about the authorized instance."
            )
    if not record.restoration_proven:
        return "Restoration was not proven twice."
    if record.coordination_residue:
        unfinished = "; ".join(record.coordination_residue[:4])
        return f"The run could not finalize its shared coordination scope: {unfinished}"
    return ""
