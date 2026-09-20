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
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from .execution import DirtyState

#: The exact four-component build form. It is the same bounded rule the product
#: environment reader applies; a shorter or suffixed value is not an exact build.
_EXACT_BUILD = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+")
MAX_BUILD_LENGTH = 64
_SHA = re.compile(r"[0-9a-f]{40}")
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
    capabilities: tuple[str, ...] = ()
    omission_reason: str = ""


@dataclass(frozen=True)
class StageBudget:
    """The hard operation/time ceiling and the time reserved for finalization."""

    max_operations: int
    max_seconds: int
    reserve_seconds: int


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

    @property
    def fixture_names(self) -> tuple[str, ...]:
        """Return the exact fixture names, in creation order."""
        return tuple(item.name for item in self.fixtures)

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
STAGE_CEILINGS: dict[QualificationStage, tuple[int, int]] = {
    QualificationStage.Q0: (20, 300),
    QualificationStage.Q1: (60, 600),
    QualificationStage.Q2: (60, 900),
    QualificationStage.Q3: (60, 1200),
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


STAGE_DEFINITIONS: dict[QualificationStage, StageDefinition] = {
    QualificationStage.Q0: _q0(),
    QualificationStage.Q1: _q1(),
    QualificationStage.Q2: _declarative(
        QualificationStage.Q2,
        "Mail engine facts (declarative only in S4a).",
        ("S2 is not implemented", "a Q0 record is required"),
    ),
    QualificationStage.Q3: _q3(),
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
    GOVERNED_ROOT = "governed_root"
    PROCESS_ISOLATION = "process_isolation"
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
    observed: RepositoryIdentity, expected_head: str
) -> tuple[QualificationRefusal, ...]:
    """Require the exact, clean, published checkout the authorization names.

    A value that could not be observed is unobservable, never a pass: the
    record must be able to name the executed SHA and tree, and a reviewer must
    be able to inspect that SHA, which is why HEAD must be published.
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
    if not record.restoration_proven:
        return "Restoration was not proven twice."
    return ""
