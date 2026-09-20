"""Prepared measurement profiles for two open Server-PT questions.

A profile is a question, not a contract. It states the exact sequence one
diagnostic would dispatch, what each step may affect, what its record must
retain, what it costs including finalization, which existing seams it cannot
use as they are, and the authority it would need first. The transition or the
failure boundary each one asks about is its dependent variable: observing it
confirms no product invariant and learns no allowlist from it.

Nothing here dispatches anything. `diagnostic_dispatch_refusal` is fail-closed
and refuses every draft, and the plan projections below are pure
transformations of plans the real compiler already produced. Where an existing
product writer cannot support a decomposition without changing its meaning,
the profile names that seam and the minimal extension it would need instead of
copying the writer's setters.

The two questions are now also executable, as the `D-DHCP` and `D-WEB`
qualification stages. That does not make this module an execution path: the
stages carry their own fixtures, budgets and steps in
`service_qualification.py`, they are admitted by the ordinary qualification
request rule, and no coordinator reads a `DiagnosticProfile` or a
`DiagnosticAuthorization`. What lives here is the reviewer-facing question,
its vendor findings, its seams and the plan projections the stage reuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

from ..models.configuration import ConfigurationPlan, SetEndpointStaticAddress
from ..models.service_plan import (
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServicePlan,
    ServiceVerificationKind,
)
from ..models.service_qualification import (
    Q3_PC1,
    Q3_PC2,
    Q3_POOL,
    Q3_SERVER,
    Q3_SWITCH,
)
from ..models.verification import PrerequisiteKind
from .configuration_compiler import configuration_plan_semantic_hash

D_DHCP = "D-DHCP"
D_WEB = "D-WEB"
DRAFT = "DRAFT"
GRANTED = "GRANTED"
#: The four fixtures both profiles reuse, in the order the runner creates them.
DIAGNOSTIC_FIXTURES = (Q3_SERVER, Q3_PC1, Q3_PC2, Q3_SWITCH)


class DiagnosticEffect(StrEnum):
    """What one step may do to the workspace, from reads to activation."""

    __str__ = Enum.__str__

    OBSERVE = "observe"
    CREATE = "create"
    CONFIGURE = "configure"
    ACTIVATE = "activate"
    REQUEST = "request"
    RELEASE = "release"


@dataclass(frozen=True)
class DiagnosticStep:
    """One proposed step: its effect, its targets, its record and its cost.

    `retains` is the observation contract: every field the record must carry
    for this step. A field the reader did not observe is never inferred, so a
    step that cannot retain a value names its absence instead.
    """

    id: str
    effect: DiagnosticEffect
    targets: tuple[str, ...]
    purpose: str
    retains: tuple[str, ...]
    operations: int
    #: Seam ids that must be approved before this step may run at all.
    blocked_by: tuple[str, ...] = ()
    #: True when the step needs to be named explicitly by the authorization,
    #: because it activates a process rather than only configuring one.
    separately_authorized: bool = False


@dataclass(frozen=True)
class DiagnosticSeam:
    """One contract extension the profile exposes for explicit review.

    `current` states whether the executable diagnostic has resolved the seam;
    `required` and `minimal_extension` preserve what was reviewed. A resolved
    seam remains listed because the planning profile records the design delta,
    not because its draft authorization can gate executable code.
    """

    id: str
    contract: str
    current: str
    required: str
    minimal_extension: str


@dataclass(frozen=True)
class VendorMemberFinding:
    """One documented member checked against the installed reference.

    `disposition` is `read` when the diagnostic would call it, `unused` when it
    exists and the diagnostic deliberately does not, and `refused` when it
    cannot be used at all. Documentation is never a support claim.
    """

    member: str
    reference: str
    disposition: str
    reason: str = ""


@dataclass(frozen=True)
class DiagnosticBudget:
    """The ceiling a profile would ask for and the reserve it keeps back."""

    max_operations: int
    max_seconds: int
    reserve_operations: int
    reserve_seconds: int


@dataclass(frozen=True)
class DiagnosticAuthorization:
    """Planning data about the authority one dispatch would need.

    **This is not the execution gate.** It has no SHA or tree binding, it
    enforces no ordered prerequisite closure, and nothing executable consults
    it. The stages that actually run these questions -- `D-DHCP` and `D-WEB`
    in `service_qualification.py` -- are gated by the ordinary
    `QualificationAuthorization`, extended with the profile, tree, fixture
    model, link port, ordered step, reserve and attempt bindings, and by every
    existing repository, process, transport, ledger and record control. Making
    this object `GRANTED` grants nothing there.

    A draft carries `status` `DRAFT`, `granted` false and no identity, so the
    planning-side refusal gate declines it for several independent reasons at
    once. A granted record has to name its reviewer, the exact profile, build,
    channel, fixtures, steps, ceiling and every seam it approves -- and that
    is still a reviewer's worksheet, never an execution permission.
    """

    profile_id: str
    status: str = DRAFT
    granted: bool = False
    authorization_id: str = ""
    reviewer: str = ""
    build: str = ""
    channel: str = ""
    fixtures: tuple[str, ...] = ()
    step_ids: tuple[str, ...] = ()
    max_operations: int = 0
    max_seconds: int = 0
    approved_seams: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticProfile:
    """One prepared, unauthorized measurement and everything it would need."""

    id: str
    question: str
    dependent_variable: str
    build: str
    channels: tuple[str, ...]
    fixtures: tuple[str, ...]
    steps: tuple[DiagnosticStep, ...]
    budget: DiagnosticBudget
    authorization: DiagnosticAuthorization
    seams: tuple[DiagnosticSeam, ...] = ()
    vendor_findings: tuple[VendorMemberFinding, ...] = ()
    controls: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def step_ids(self) -> tuple[str, ...]:
        """Return every proposed step id, in sequence order."""
        return tuple(item.id for item in self.steps)

    @property
    def seam_ids(self) -> tuple[str, ...]:
        """Return every declared seam id."""
        return tuple(item.id for item in self.seams)

    def step(self, step_id: str) -> DiagnosticStep:
        """Return one proposed step by id."""
        for item in self.steps:
            if item.id == step_id:
                return item
        raise KeyError(step_id)

    def worst_case_operations(self, step_ids: tuple[str, ...] | None = None) -> int:
        """Return the worst case of a selection, finalization reserve included.

        The reserve is part of every arithmetic here: a sequence that fits only
        by spending what finalization needs does not fit.
        """
        chosen = self.step_ids if step_ids is None else step_ids
        return (
            sum(self.step(item).operations for item in chosen)
            + self.budget.reserve_operations
        )

    @property
    def fits(self) -> bool:
        """Return whether the complete proposed sequence fits the ceiling."""
        return self.worst_case_operations() <= self.budget.max_operations


def diagnostic_dispatch_refusal(
    profile: DiagnosticProfile, authorization: DiagnosticAuthorization | None
) -> str:
    """Return why this profile may not be dispatched, or "" when it may.

    Fail-closed, and every reason is independent: an absent or draft authority,
    one that names another profile, build, channel, fixture set or ceiling, one
    that selects a step the profile does not define, one that leaves a declared
    seam unapproved and one whose selection does not fit the ceiling each
    refuse on their own. A missing value is unknown, never permission.
    """
    if authorization is None:
        return "diagnostic_authorization_absent"
    if authorization.status != GRANTED or not authorization.granted:
        return f"diagnostic_authorization_not_granted:{authorization.status or 'none'}"
    if not authorization.authorization_id or not authorization.reviewer:
        return "diagnostic_authorization_identity_missing"
    if authorization.profile_id != profile.id:
        return f"diagnostic_authorization_names:{authorization.profile_id or 'none'}"
    if not profile.build or authorization.build != profile.build:
        return f"diagnostic_build_not_authorized:{authorization.build or 'unknown'}"
    if authorization.channel not in profile.channels:
        return f"diagnostic_channel_not_authorized:{authorization.channel or 'unknown'}"
    if tuple(authorization.fixtures) != profile.fixtures:
        return "diagnostic_fixture_set_not_authorized"
    if (
        authorization.max_operations != profile.budget.max_operations
        or authorization.max_seconds != profile.budget.max_seconds
    ):
        return "diagnostic_ceiling_not_authorized"
    selection = tuple(authorization.step_ids)
    if not selection:
        return "diagnostic_no_step_authorized"
    unknown = [item for item in selection if item not in profile.step_ids]
    if unknown:
        return f"diagnostic_step_not_defined:{unknown[0]}"
    approved = set(authorization.approved_seams)
    for item in selection:
        missing = [
            seam for seam in profile.step(item).blocked_by if seam not in approved
        ]
        if missing:
            return f"diagnostic_seam_not_approved:{missing[0]}"
    if profile.worst_case_operations(selection) > profile.budget.max_operations:
        return "diagnostic_selection_exceeds_ceiling"
    return ""


# -- D-DHCP: when does the native default change? -------------------------------


def d_dhcp_static_only_plan(
    plan: ConfigurationPlan, *, device_name: str = Q3_SERVER
) -> ConfigurationPlan:
    """Project E5 to one endpoint's static address, and to nothing else.

    This is the same projection idiom Q3 already uses for its endpoint
    bootstrap: it drops actions and already-owned fixture dependencies without
    rewriting what an action means. No `SetEndpointDhcp` survives, so no client
    is put into DHCP mode by this step.
    """
    actions = [
        item.model_copy(update={"depends_on": [], "apply_dependencies": []})
        for item in plan.actions
        if isinstance(item, SetEndpointStaticAddress)
        and item.device_name == device_name
    ]
    action_ids = {item.id for item in actions}
    device_ids = {item.device_id for item in actions}
    projected = ConfigurationPlan(
        id=f"{plan.id}/d-dhcp-static",
        source_topology_id=plan.source_topology_id,
        source_topology_hash=plan.source_topology_hash,
        source_topology_hash_schema=plan.source_topology_hash_schema,
        actions=actions,
        devices=[
            item.model_copy(deep=True)
            for item in plan.devices
            if item.device_id in device_ids
        ],
        verification_expectations=[
            item.model_copy(deep=True)
            for item in plan.verification_expectations
            if item.action_id in action_ids
        ],
    )
    projected.semantic_hash = configuration_plan_semantic_hash(projected)
    return projected


@dataclass(frozen=True)
class ProjectionRewrite:
    """One exact change a projection made to what the compiler asserted.

    A projection that only dropped rows states nothing here. Every rewrite
    that changes an assertion -- a removed ordering dependency, a foundation
    the executed configuration cannot satisfy, an expectation field, an
    expectation rebound to another action -- is recorded as its own entry, so
    a record can never present the modified plan as a fresh execution of the
    unmodified one.
    """

    kind: str
    target: str
    detail: str = ""

    def as_text(self) -> str:
        """Return the compact single-line form a record stores."""
        return f"{self.kind}:{self.target}" + (f":{self.detail}" if self.detail else "")


#: The identities the diagnostic projections carry beside the source plan's.
D_DHCP_POOL_PROJECTION = "d-dhcp-pool-disabled"
D_DHCP_ENABLE_PROJECTION = "d-dhcp-enable"
D_DHCP_PROJECTION_VERSION = "2"


def d_dhcp_pool_only_plan(
    plan: ServicePlan,
    *,
    executed_configuration_action_ids: frozenset[str] | set[str] | tuple[str, ...] = (),
) -> tuple[ServicePlan, tuple[ProjectionRewrite, ...]]:
    """Project E6 to the pool action alone, configured while still disabled.

    Three rewrites are needed, not one, and each is returned explicitly:

    1. the compiler makes the pool action depend on the enable action in both
       lists, so a plan that keeps only the pool would carry a dependency on
       an action nobody runs;
    2. the compiled plan's foundational requirements include the two client
       `endpoint_dhcp_mode` actions. The executed E5 of this diagnostic is the
       server's static address alone, so those foundations can never become
       VERIFIED and the applicator would refuse before dispatching anything.
       Only foundations whose configuration action the executed plan actually
       contains survive;
    3. the direct DHCP server-state expectation the compiler wrote expects
       `enabled=True`, which is exactly what this stage must not assume. Its
       expectation is rewritten to `enabled=False` and keeps every other pool
       field, so the disabled stage verifies the configuration it wrote rather
       than the transition the next stage makes.

    Nothing here calls a setter, and no expectation is invented: the fields
    are the compiler's own, with one boolean stated as the stage means it.
    """
    executed = frozenset(executed_configuration_action_ids)
    enable_ids = {
        item.id for item in plan.actions if isinstance(item, EnableServerDhcp)
    }
    rewrites: list[ProjectionRewrite] = []
    actions = []
    for item in plan.actions:
        if not isinstance(item, ConfigureServerDhcpPool):
            continue
        removed = enable_ids & (set(item.depends_on) | set(item.apply_dependencies))
        rewrites.extend(
            ProjectionRewrite("dependency_removed", value, f"of:{item.id}")
            for value in sorted(removed)
        )
        actions.append(
            item.model_copy(
                update={
                    "depends_on": [
                        value for value in item.depends_on if value not in enable_ids
                    ],
                    "apply_dependencies": [
                        value
                        for value in item.apply_dependencies
                        if value not in enable_ids
                    ],
                },
                deep=True,
            )
        )
    projected, more = _projected_service_plan(
        plan,
        actions,
        executed=executed,
        projection_id=D_DHCP_POOL_PROJECTION,
        expected_enabled=False,
    )
    return projected, tuple(rewrites) + more


def d_dhcp_enable_only_plan(
    plan: ServicePlan,
    *,
    executed_configuration_action_ids: frozenset[str] | set[str] | tuple[str, ...] = (),
) -> tuple[ServicePlan, tuple[ProjectionRewrite, ...]]:
    """Project E6 to the enable action alone and verify the transition to true.

    The compiler attaches the DHCP server-state read-back to the pool action,
    so an enable-only projection would carry no product verification at all.
    The expectation is therefore rebound to the enable action with
    `enabled=True`: the same reader, the same fields, asserting exactly the
    transition this stage makes. The rebinding is returned as the rewrite it
    is; it is never presented as what the compiler wrote.
    """
    actions = [item for item in plan.actions if isinstance(item, EnableServerDhcp)]
    return _projected_service_plan(
        plan,
        actions,
        executed=frozenset(executed_configuration_action_ids),
        projection_id=D_DHCP_ENABLE_PROJECTION,
        expected_enabled=True,
        rebind_to=actions[0].id if actions else "",
    )


def _projected_prerequisites(
    expectation, action_ids: set[str], *, rebind_to: str
) -> tuple[list, tuple[ProjectionRewrite, ...]]:
    """Keep only prerequisites the projected plan can still satisfy.

    The compiler writes an `ACTION_APPLIED` prerequisite naming the action the
    expectation was attached to, plus one `VERIFICATION_VERIFIED` per declared
    dependency. A projection that keeps a subset of the actions leaves those
    references pointing at rows nobody runs, and the applicator then reports
    the read-back as DEPENDENCY_BLOCKED -- a stage that activates a process
    and verifies nothing while looking like it verified something.

    So a prerequisite whose reference the projection dropped is removed and
    recorded; a rebound expectation's `ACTION_APPLIED` is rewritten to the
    action it is now attached to, because that is the effect this read-back
    actually follows.
    """
    kept = []
    rewrites: list[ProjectionRewrite] = []
    for prerequisite in expectation.verification_prerequisites:
        if prerequisite.kind is PrerequisiteKind.ACTION_APPLIED:
            if rebind_to and prerequisite.reference_id != rebind_to:
                kept.append(prerequisite.model_copy(update={"reference_id": rebind_to}))
                rewrites.append(
                    ProjectionRewrite(
                        "prerequisite_rebound",
                        expectation.id,
                        f"action_applied:{prerequisite.reference_id}->{rebind_to}",
                    )
                )
                continue
            if prerequisite.reference_id in action_ids:
                kept.append(prerequisite)
                continue
        elif prerequisite.kind is not PrerequisiteKind.VERIFICATION_VERIFIED:
            kept.append(prerequisite)
            continue
        rewrites.append(
            ProjectionRewrite(
                "prerequisite_removed",
                expectation.id,
                f"{prerequisite.kind.value}:{prerequisite.reference_id}",
            )
        )
    return kept, tuple(rewrites)


def _projected_service_plan(
    plan: ServicePlan,
    actions: list,
    *,
    executed: frozenset[str] = frozenset(),
    projection_id: str = "",
    expected_enabled: bool | None = None,
    rebind_to: str = "",
) -> tuple[ServicePlan, tuple[ProjectionRewrite, ...]]:
    """Return the plan reduced to `actions`, and every rewrite that required.

    Only the direct DHCP server-state expectation survives. An attribution
    expectation needs a lease, and no step of this profile acquires one, so
    keeping it would schedule a verification the sequence excludes and budgets
    nothing for.
    """
    rewrites: list[ProjectionRewrite] = []
    action_ids = {item.id for item in actions}
    expectations = []
    for item in plan.verification_expectations:
        if item.kind is not ServiceVerificationKind.DHCP_SERVER_STATE:
            continue
        if item.action_id not in action_ids and not rebind_to:
            continue
        update: dict[str, object] = {}
        if rebind_to and item.action_id != rebind_to:
            update["action_id"] = rebind_to
            rewrites.append(
                ProjectionRewrite(
                    "expectation_rebound", item.id, f"{item.action_id}->{rebind_to}"
                )
            )
        prerequisites, dropped = _projected_prerequisites(
            item, action_ids, rebind_to=rebind_to
        )
        if dropped:
            update["verification_prerequisites"] = prerequisites
            rewrites.extend(dropped)
        if expected_enabled is not None and item.expected.get("enabled") is not (
            expected_enabled
        ):
            update["expected"] = {**item.expected, "enabled": expected_enabled}
            rewrites.append(
                ProjectionRewrite(
                    "expectation_field",
                    item.id,
                    f"enabled={item.expected.get('enabled')}->{expected_enabled}",
                )
            )
        expectations.append(
            item.model_copy(update=update, deep=True) if update else item
        )
    expectation_ids = {item.id for item in expectations}
    foundations = []
    for item in plan.foundational_requirements:
        if executed and item.configuration_action_id not in executed:
            rewrites.append(
                ProjectionRewrite(
                    "foundation_removed",
                    item.configuration_action_id,
                    f"kind:{item.kind}:device:{item.device_name}",
                )
            )
            continue
        foundations.append(item.model_copy(deep=True))
    services = [
        item.model_copy(
            update={
                "action_ids": [
                    value for value in item.action_ids if value in action_ids
                ],
                "verification_expectation_ids": [
                    value
                    for value in item.verification_expectation_ids
                    if value in expectation_ids
                ],
            },
            deep=True,
        )
        for item in plan.services
        if item.id in {row.service_id for row in actions}
    ]
    update = {
        "services": services,
        "actions": actions,
        "foundational_requirements": foundations,
        "verification_expectations": expectations,
    }
    if projection_id:
        update["id"] = f"{plan.id}/{projection_id}"
        rewrites.append(
            ProjectionRewrite(
                "projection_identity",
                f"{plan.id}/{projection_id}",
                # The source identities are untouched: the projection is named
                # beside them, never in place of them.
                f"source:{plan.id}:semantic_hash_retained:{plan.semantic_hash}",
            )
        )
    return plan.model_copy(update=update, deep=True), tuple(rewrites)


POOL_BEFORE_ENABLE = "pool-configured-before-enable"

_D_DHCP_SEAMS = (
    DiagnosticSeam(
        id=POOL_BEFORE_ENABLE,
        contract="ServicePlan.ConfigureServerDhcpPool.depends_on/apply_dependencies",
        current=(
            "the compiled Q3 plan makes the pool action depend on the enable "
            "action in both lists, so the pool cannot be configured while the "
            "process stays disabled"
        ),
        required=(
            "configure only the intended pool with the process still disabled, "
            "so a default transition can be attributed to the pool write alone"
        ),
        minimal_extension=(
            "`d_dhcp_pool_only_plan` drops the enable action and returns the "
            "exact dependency ids it removed; the setters are the product's, "
            "never copied, and the step stays blocked until this is approved"
        ),
    ),
)

_D_DHCP_STEPS = (
    DiagnosticStep(
        id="admission",
        effect=DiagnosticEffect.OBSERVE,
        targets=("executable_build", "workspace_baseline"),
        purpose="d-dhcp:admission",
        retains=("observed_build", "build_reader_identity", "workspace_inventory"),
        operations=2,
    ),
    DiagnosticStep(
        id="fixtures",
        effect=DiagnosticEffect.CREATE,
        targets=(*DIAGNOSTIC_FIXTURES, "link:1", "link:2", "link:3"),
        purpose="d-dhcp:fixtures",
        retains=("creation_disposition", "owned", "fixture_identity"),
        operations=15,
    ),
    DiagnosticStep(
        id="D0-a",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_SERVER}/FastEthernet0:DhcpServerMain",),
        purpose="d-dhcp:native_default:baseline",
        retains=(
            "process_found",
            "enabled_boolean",
            "pool_count",
            "bounded_pool_rows",
            "truncated",
            "error",
        ),
        operations=1,
    ),
    DiagnosticStep(
        id="D0-b",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_PC1}/FastEthernet0", f"{Q3_PC2}/FastEthernet0"),
        purpose="d-dhcp:clients:not_activated",
        retains=("dhcp_mode", "mode_type", "mac", "address", "lease_text"),
        operations=1,
    ),
    DiagnosticStep(
        id="D0-c",
        effect=DiagnosticEffect.OBSERVE,
        targets=("link:1", "link:2", "link:3"),
        purpose="d-dhcp:readiness",
        retains=("reads", "deadline_seconds", "first_sample", "last_sample", "reason"),
        operations=4,
    ),
    DiagnosticStep(
        id="D1-a",
        effect=DiagnosticEffect.CONFIGURE,
        targets=(f"{Q3_SERVER}:SetEndpointStaticAddress",),
        purpose="d-dhcp:e5:server_address_only",
        retains=("dispatch", "result", "postcondition", "read_back"),
        operations=2,
    ),
    DiagnosticStep(
        id="D1-b",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_SERVER}/FastEthernet0:DhcpServerMain",),
        purpose="d-dhcp:native_default:after_server_address",
        retains=("bounded_pool_rows", "differences_against_D0-a", "operation_seq"),
        operations=1,
    ),
    DiagnosticStep(
        id="D2-a",
        effect=DiagnosticEffect.CONFIGURE,
        targets=(f"{Q3_SERVER}:ConfigureServerDhcpPool:{Q3_POOL}",),
        purpose="d-dhcp:e6:pool_only",
        retains=("dispatch", "result", "postcondition", "read_back", "process_enabled"),
        operations=2,
        blocked_by=(POOL_BEFORE_ENABLE,),
    ),
    DiagnosticStep(
        id="D2-b",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_SERVER}/FastEthernet0:DhcpServerMain",),
        purpose="d-dhcp:native_default:after_pool",
        retains=(
            "bounded_pool_rows",
            "intended_pool_present",
            "differences_against_D0-a",
            "differences_against_D1-b",
        ),
        operations=1,
    ),
    DiagnosticStep(
        id="D3-a",
        effect=DiagnosticEffect.ACTIVATE,
        targets=(f"{Q3_SERVER}:EnableServerDhcp",),
        # Two operations: the enable dispatch and the DHCP server-state
        # read-back the projection rebinds to it. The compiler attaches that
        # read-back to the pool action, so an enable-only projection that
        # dropped it would activate a process and verify nothing.
        purpose="d-dhcp:e6:enable_only",
        retains=(
            "dispatch",
            "result",
            "postcondition",
            "read_back",
            "expectation_rebound",
        ),
        operations=2,
        separately_authorized=True,
    ),
    DiagnosticStep(
        id="D3-b",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_SERVER}/FastEthernet0:DhcpServerMain",),
        purpose="d-dhcp:native_default:after_enable",
        retains=("enabled_boolean", "bounded_pool_rows", "differences_against_D2-b"),
        operations=1,
        separately_authorized=True,
    ),
    DiagnosticStep(
        id="D4",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_SERVER}/FastEthernet0:DhcpServerMain",),
        purpose="d-dhcp:native_default:before_cleanup",
        retains=(
            "bounded_pool_rows",
            "differences_against_D0-a",
            "cause_if_unobserved",
        ),
        operations=1,
    ),
)


def d_dhcp_profile(*, build: str, channels: tuple[str, ...]) -> DiagnosticProfile:
    """Return the prepared D-DHCP profile for one build and channel set.

    The domain names no backend version, so the composition supplies the build
    the sequence would be measured on and the channels it may use.
    """
    return DiagnosticProfile(
        id=D_DHCP,
        question=(
            "Which operation moves the native default pool of a stock "
            "Server-PT, if any single one of them does?"
        ),
        dependent_variable=(
            "the observed transition of the native pool between two bounded "
            "readings, which confirms no invariant and authorizes no allowlist"
        ),
        build=build,
        channels=channels,
        fixtures=DIAGNOSTIC_FIXTURES,
        steps=_D_DHCP_STEPS,
        budget=DiagnosticBudget(
            max_operations=60,
            max_seconds=900,
            reserve_operations=11,
            reserve_seconds=180,
        ),
        authorization=DiagnosticAuthorization(profile_id=D_DHCP),
        seams=_D_DHCP_SEAMS,
        controls=(
            "the disabled native baseline with no client activated is the "
            "before-oracle of every later reading",
            "each reading names the operation that produced it, so a "
            "transition falls between two adjacent counted calls",
            "a reading that cannot be afforded or performed is not observed, "
            "and the sequence stops rather than dispatching a repair",
        ),
        excluded=(
            "client acquisition",
            "DHCP event observer registration",
            "default-pool setter, removal or reset",
            "restoring the default by rewriting its values",
            "renaming an exhausted Q3 attempt",
        ),
        limitations=(
            "an unknown effect, a wrong subject identity, a malformed or "
            "incomplete inventory and a foreign fixture each stop the sequence",
            "a finite native default transition is neither client acquisition "
            "nor serving authority, and this profile measures neither",
            "without the seam approval the pool step cannot run, so the "
            "sequence would stop after the server address alone",
        ),
    )


# -- D-WEB: reachability or the client reader? ----------------------------------

HTTP_MODE_NOT_READ = "http-client-mode-not-read"
POLL_DISCARDS_READINGS = "poll-discards-intermediate-readings"
NO_LATE_CONTROL_READ = "no-late-control-read"
LISTENER_PORT_NOT_READ = "listener-port-number-not-read"

_D_WEB_SEAMS = (
    DiagnosticSeam(
        id=HTTP_MODE_NOT_READ,
        contract="the background client start evaluation",
        current=(
            "resolved in executable D-WEB: both starts read `isHttps()` and "
            "retain the native mode and its type"
        ),
        required="the mode the client actually held when the request started",
        minimal_extension=(
            "read `isHttps()` in the same start evaluation for both modes, "
            "which adds no operation and changes no request"
        ),
    ),
    DiagnosticSeam(
        id=POLL_DISCARDS_READINGS,
        contract="the bounded polling helper of the web reader",
        current=(
            "resolved in executable D-WEB: the diagnostic composition retains "
            "every attempted inspection and every missed schedule slot"
        ),
        required=(
            "each inspection with its timestamp, its outcome and the operation "
            "and time budget still remaining when it ran"
        ),
        minimal_extension=(
            "collect the readings the poll already takes; no extra inspection, "
            "no unconditional wait and no second fetch"
        ),
    ),
    DiagnosticSeam(
        id=NO_LATE_CONTROL_READ,
        contract="the owned client's lifecycle between the deadline and release",
        current=(
            "resolved in executable D-WEB: one separately labelled late read "
            "runs before release without a second request"
        ),
        required=(
            "one late content read, before release, that separates content "
            "arriving after the window from content never arriving"
        ),
        minimal_extension=(
            "one counted read per fetch, budgeted here as the fifth operation "
            "of the fetch; it starts no request and retries nothing"
        ),
    ),
    DiagnosticSeam(
        id=LISTENER_PORT_NOT_READ,
        contract="the listener readiness reader",
        current=(
            "resolved in executable D-WEB: each listener reports its native "
            "port value and type beside the enable flags"
        ),
        required="the actual port number each handle is listening on",
        minimal_extension=(
            "add `getPortNumber()` per handle to the same evaluation, which "
            "adds no operation"
        ),
    ),
)

_D_WEB_FINDINGS = (
    VendorMemberFinding(
        member="HttpClient::getOwnerDevice()",
        reference="inherited from Process",
        disposition="read",
        reason="states which device owns the client this record speaks for",
    ),
    VendorMemberFinding(
        member="HttpClient::isHttps()",
        reference="returns true for HTTPS mode, false for HTTP",
        disposition="read",
        reason="already used by the HTTPS reader; reading it in HTTP mode too "
        "closes the record's own `client_mode: not_read_back`",
    ),
    VendorMemberFinding(
        member="HttpClient::go(string)",
        reference="creates a request to a URL; returns whether it succeeded",
        disposition="read",
        reason="success is about the request, never about a response",
    ),
    VendorMemberFinding(
        member="HttpClient::getLastPageContent()",
        reference="returns the last page content retrieved from a response",
        disposition="read",
        reason="the only documented reader of what came back",
    ),
    VendorMemberFinding(
        member="HttpClient::cancel()",
        reference="cancels the request and closes the TCP connection",
        disposition="unused",
        reason="it discriminates none of the three alternatives",
    ),
    VendorMemberFinding(
        member="HttpClient::http_get/http_post/http_put/http_delete",
        reference="signature only: no parameter names, semantics or return",
        disposition="refused",
        reason="an undocumented signature is never guessed",
    ),
    VendorMemberFinding(
        member="HttpClient::onStart/onDone",
        reference="IPC events; HttpResponseType has no page in the reference",
        disposition="refused",
        reason="the one contract that could separate the network path from the "
        "listener needs its own qualification and its own authorization",
    ),
    VendorMemberFinding(
        member="HttpServer::getPortNumber()",
        reference="returns the port number of the HTTP service",
        disposition="read",
        reason="the record must carry actual port numbers, not assumed ones",
    ),
    VendorMemberFinding(
        member="HttpServer::isEnabled()",
        reference="returns whether the HTTP service is enabled",
        disposition="read",
    ),
    VendorMemberFinding(
        member="HttpsServer::isHttpsEnabled()",
        reference="returns whether the HTTPS service is enabled",
        disposition="read",
        reason="retained per handle beside `isEnabled`",
    ),
    VendorMemberFinding(
        member="HttpServer::getUsername/getPassword",
        reference="documented readers",
        disposition="refused",
        reason="no credential work is in scope",
    ),
    VendorMemberFinding(
        member="HttpServer::onRequest(string, TcpConnection)",
        reference="IPC event",
        disposition="refused",
        reason="an unqualified event source, like onDone",
    ),
)

_D_WEB_STEPS = (
    DiagnosticStep(
        id="admission",
        effect=DiagnosticEffect.OBSERVE,
        targets=("executable_build", "workspace_baseline"),
        purpose="d-web:admission",
        retains=("observed_build", "build_reader_identity", "workspace_inventory"),
        operations=2,
    ),
    DiagnosticStep(
        id="fixtures",
        effect=DiagnosticEffect.CREATE,
        targets=(*DIAGNOSTIC_FIXTURES, "link:1", "link:2", "link:3", "e5", "e6"),
        purpose="d-web:fixtures",
        retains=("creation_disposition", "fixture_identity", "listener_application"),
        operations=17,
    ),
    DiagnosticStep(
        id="W0-a",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_SERVER}:HttpServer", f"{Q3_SERVER}:HttpsServer"),
        purpose="d-web:listeners:before",
        retains=(
            "http_enabled",
            "https_enabled",
            "https_process_enabled",
            "http_port_number",
            "https_port_number",
            "page_read_back_per_handle",
        ),
        operations=1,
        blocked_by=(LISTENER_PORT_NOT_READ,),
    ),
    DiagnosticStep(
        id="W0-b",
        effect=DiagnosticEffect.OBSERVE,
        targets=("link:1", "link:2", "link:3"),
        purpose="d-web:readiness",
        retains=("reads", "deadline_seconds", "first_sample", "last_sample", "reason"),
        operations=4,
    ),
    DiagnosticStep(
        id="W1",
        effect=DiagnosticEffect.CONFIGURE,
        targets=(f"{Q3_SERVER}:index.html",),
        purpose="d-web:marker_page",
        retains=("written_per_handle", "read_back_per_handle", "marker", "length"),
        operations=1,
    ),
    DiagnosticStep(
        id="W2-a",
        effect=DiagnosticEffect.REQUEST,
        targets=(f"{Q3_PC1}:HttpBackgroundClient:http",),
        purpose="d-web:fetch:http:start",
        retains=(
            "owner_device",
            "client_mode",
            "content_before",
            "marker_in_content_before",
            "selected_url",
            "selected_path",
            "go_result",
        ),
        operations=1,
        blocked_by=(HTTP_MODE_NOT_READ,),
    ),
    DiagnosticStep(
        id="W2-b",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_PC1}:HttpBackgroundClient:http",),
        purpose="d-web:fetch:http:poll",
        retains=(
            "inspection_offset_seconds",
            "inspection_outcome",
            "remaining_operations",
            "remaining_seconds",
        ),
        operations=2,
        blocked_by=(POLL_DISCARDS_READINGS,),
    ),
    DiagnosticStep(
        id="W2-c",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_PC1}:HttpBackgroundClient:http",),
        purpose="d-web:fetch:http:late_control",
        retains=("offset_seconds", "content", "changed_after_deadline"),
        operations=1,
        blocked_by=(NO_LATE_CONTROL_READ,),
    ),
    DiagnosticStep(
        id="W2-d",
        effect=DiagnosticEffect.RELEASE,
        targets=(f"{Q3_PC1}:HttpBackgroundClient:http",),
        purpose="d-web:fetch:http:release",
        retains=("found", "deleted", "present_after", "error"),
        operations=1,
    ),
    DiagnosticStep(
        id="W3",
        effect=DiagnosticEffect.REQUEST,
        targets=(f"{Q3_PC1}:HttpBackgroundClient:https",),
        purpose="d-web:fetch:https",
        retains=(
            "owner_device",
            "client_mode",
            "content_before",
            "selected_url",
            "go_result",
            "inspection_offset_seconds",
            "inspection_outcome",
            "late_control_read",
            "release_outcome",
        ),
        operations=5,
        blocked_by=(POLL_DISCARDS_READINGS, NO_LATE_CONTROL_READ),
    ),
    DiagnosticStep(
        id="W4-a",
        effect=DiagnosticEffect.OBSERVE,
        targets=(f"{Q3_SERVER}:HttpServer", f"{Q3_SERVER}:HttpsServer"),
        purpose="d-web:listeners:after",
        retains=(
            "http_enabled",
            "https_enabled",
            "http_port_number",
            "https_port_number",
        ),
        operations=1,
        blocked_by=(LISTENER_PORT_NOT_READ,),
    ),
    DiagnosticStep(
        id="W4-b",
        effect=DiagnosticEffect.OBSERVE,
        targets=("link:1", "link:2", "link:3"),
        purpose="d-web:readiness:after",
        retains=("port_up", "protocol_up", "link_type", "ip", "mask"),
        operations=1,
    ),
)


def d_web_profile(*, build: str, channels: tuple[str, ...]) -> DiagnosticProfile:
    """Return the prepared D-WEB profile for one build and channel set."""
    return DiagnosticProfile(
        id=D_WEB,
        question=(
            "Where does the unretrieved HTTP page fail: the network path, the "
            "listener and request, or the polling and the reader?"
        ),
        dependent_variable=(
            "the boundary the same-fixture comparison locates, which is not a "
            "listener refusal and not a timeout interpretation"
        ),
        build=build,
        channels=channels,
        fixtures=DIAGNOSTIC_FIXTURES,
        steps=_D_WEB_STEPS,
        budget=DiagnosticBudget(
            max_operations=60,
            max_seconds=600,
            reserve_operations=10,
            reserve_seconds=120,
        ),
        authorization=DiagnosticAuthorization(profile_id=D_WEB),
        seams=_D_WEB_SEAMS,
        vendor_findings=_D_WEB_FINDINGS,
        controls=(
            "same fixture, same page and same marker under two client modes: "
            "a retrieved HTTPS marker beside an unretrieved HTTP one places "
            "the boundary at the HTTP listener or request",
            "neither retrieved, with both listeners enabled on their read-back "
            "port numbers and every fixture port up, places it at the network "
            "path or at the reader",
            "a late control read that finds the marker after the deadline "
            "places it at the polling window",
        ),
        excluded=(
            "PortFast or any forwarding change",
            "switching the transport",
            "unconditional waits",
            "unqualified event registration",
            "automatic second fetches",
            "repeating the shared page-table measurement",
        ),
        limitations=(
            "with documented read-only members alone the network path and the "
            "listener cannot be separated: only layer-1 and layer-2 readiness "
            "is observable",
            "the measured link fields are carried as themselves and never as a "
            "forwarding or reachability observation. Two observations this "
            "profile does not take DO exist and the executable D-WEB stage "
            "takes them: the registered `show spanning-tree` query with the "
            "maintained parser, and `Port::getLightStatus()` with its "
            "documented enumeration (off=0, amber=1, green=2, blink=3), which "
            "is auxiliary evidence and never a per-VLAN forwarding claim",
            "a timeout is never a negative listener claim",
            "no TLS property is asserted by an HTTPS-mode retrieval",
            "every owned client is named, released once and reported; an "
            "unresolved release stays unresolved",
        ),
    )


#: What every prepared profile would still need before any dispatch. None of
#: it exists: these are the preconditions a reviewer would have to satisfy.
DIAGNOSTIC_PRECONDITIONS: tuple[str, ...] = (
    "an independent reviewer's exact-scope approval naming this sequence",
    "a clean delivery commit with exact-SHA CI green",
    "an operator-confirmed dedicated Packet Tracer process",
    "the measured build and one fixed channel for the whole invocation",
    "a separate decision on every seam the selected steps declare",
)


def prepared_profiles(
    *, build: str, channels: tuple[str, ...]
) -> tuple[DiagnosticProfile, ...]:
    """Return every prepared profile, each with its ungranted draft."""
    return (
        d_dhcp_profile(build=build, channels=channels),
        d_web_profile(build=build, channels=channels),
    )
