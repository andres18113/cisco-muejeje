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

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum

from ..models.configuration import (
    ConfigurationAction,
    ConfigurationPlan,
    ConfigureAccessPort,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
)
from ..models.service_plan import (
    AcquireDhcpLease,
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServicePhase,
    ServicePlan,
    ServiceType,
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
from .service_compiler import service_plan_semantic_hash

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


def sp2_preclient_configuration_plan(
    plan: ConfigurationPlan,
) -> tuple[ConfigurationPlan, tuple[ProjectionRewrite, ...]]:
    """Retain compiled routed foundations while withholding the one PC mode.

    The omitted action and expectation remain in the source plan. No retained
    action may depend on them, and the projection receives its own hash.
    """
    omitted = [item for item in plan.actions if isinstance(item, SetEndpointDhcp)]
    if len(omitted) != 1:
        raise ValueError("SP-2 relay requires exactly one selected DHCP mode action.")
    actions = [
        item.model_copy(deep=True) for item in plan.actions if item.id != omitted[0].id
    ]
    action_ids = {item.id for item in actions}
    if any(
        set(item.depends_on + item.apply_dependencies) - action_ids for item in actions
    ):
        raise ValueError("SP-2 relay preclient plan has a missing dependency.")
    expectations = [
        item.model_copy(deep=True)
        for item in plan.verification_expectations
        if item.action_id in action_ids
    ]
    expectation_ids = {item.id for item in expectations}
    for expectation in expectations:
        for prerequisite in expectation.verification_prerequisites:
            if (
                prerequisite.kind
                in {PrerequisiteKind.ACTION_APPLIED, PrerequisiteKind.ACTION_VERIFIED}
                and prerequisite.reference_id not in action_ids
            ) or (
                prerequisite.kind is PrerequisiteKind.VERIFICATION_VERIFIED
                and prerequisite.reference_id not in expectation_ids
            ):
                raise ValueError(
                    "SP-2 relay preclient readback prerequisite is missing."
                )
    by_device: dict[str, list[ConfigurationAction]] = {}
    for action in actions:
        by_device.setdefault(action.device_id, []).append(action)
    source_device_ids = {item.device_id for item in plan.devices}
    if (
        len(source_device_ids) != len(plan.devices)
        or set(by_device) - source_device_ids
    ):
        raise ValueError("SP-2 relay preclient device row is missing.")
    devices = [
        item.model_copy(
            update={
                "action_ids": [action.id for action in by_device[item.device_id]],
                "required_capabilities": sorted(
                    {
                        action.required_capability
                        for action in by_device[item.device_id]
                        if action.required_capability
                    }
                ),
            },
            deep=True,
        )
        for item in plan.devices
        if by_device.get(item.device_id)
    ]
    projected = plan.model_copy(
        update={
            "id": f"{plan.id}/sp2-preclient",
            "actions": actions,
            "devices": devices,
            "verification_expectations": expectations,
        },
        deep=True,
    )
    projected.semantic_hash = configuration_plan_semantic_hash(projected)
    return projected, (
        ProjectionRewrite("action_omitted", omitted[0].id, "client_mode_deferred"),
    )


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

    The projection keeps its source plan identity and records each rewrite:

    1. a legacy plan may make the pool depend on enable, so any removed edge
       is explicit; the current compiler already places pool before enable;
    2. the compiled plan's foundational requirements include the two client
       `endpoint_dhcp_mode` actions. The executed E5 of this diagnostic is the
       server's static address alone, so those foundations can never become
       VERIFIED and the applicator would refuse before dispatching anything.
       Only foundations whose configuration action the executed plan actually
       contains survive;
    3. the direct DHCP server-state expectation now follows process enable and
       expects `enabled=True`. It is rebound to the retained pool action and
       rewritten to `enabled=False`, while every other pool field is kept.

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
        rebind_to=actions[0].id if actions else "",
    )
    return projected, tuple(rewrites) + more


def d_dhcp_enable_only_plan(
    plan: ServicePlan,
    *,
    executed_configuration_action_ids: frozenset[str] | set[str] | tuple[str, ...] = (),
) -> tuple[ServicePlan, tuple[ProjectionRewrite, ...]]:
    """Project E6 to the enable action alone and verify the transition to true.

    The pool was applied in the preceding diagnostic stage, so this projection
    removes its action dependency and records that rewrite. The current
    compiler attaches the DHCP server-state read-back to the enable action,
    so this projection retains that reader and its `enabled=True` assertion.
    Legacy source plans that attached it to the pool still record a rebinding.
    """
    pool_ids = {
        item.id for item in plan.actions if isinstance(item, ConfigureServerDhcpPool)
    }
    actions = []
    rewrites: list[ProjectionRewrite] = []
    for item in plan.actions:
        if not isinstance(item, EnableServerDhcp):
            continue
        removed = pool_ids & (set(item.depends_on) | set(item.apply_dependencies))
        rewrites.extend(
            ProjectionRewrite("dependency_removed", value, f"of:{item.id}")
            for value in sorted(removed)
        )
        actions.append(
            item.model_copy(
                update={
                    "depends_on": [
                        value for value in item.depends_on if value not in pool_ids
                    ],
                    "apply_dependencies": [
                        value
                        for value in item.apply_dependencies
                        if value not in pool_ids
                    ],
                },
                deep=True,
            )
        )
    projected, more = _projected_service_plan(
        plan,
        actions,
        executed=frozenset(executed_configuration_action_ids),
        projection_id=D_DHCP_ENABLE_PROJECTION,
        expected_enabled=True,
        rebind_to=actions[0].id if actions else "",
    )
    return projected, tuple(rewrites) + more


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


# -- Q3-FL: the versioned DHCP qualification profile -----------------------------

#: The identities the Q3-FL projections carry beside the source plan's.
Q3_FL_SERVER_PROJECTION = "q3-fl-server"
Q3_FL_ACQUISITION_PROJECTION = "q3-fl-acquire"


def q3_fastloop_client_mode_plan(
    plan: ConfigurationPlan, *, device_names: Sequence[str]
) -> ConfigurationPlan:
    """Project E5 to the DHCP mode of the named clients, and to nothing else.

    The same projection idiom as the server's static address: actions and
    already-owned fixture dependencies are dropped, nothing an action means is
    rewritten. Only clients whose forwarding was admitted are named, so a
    refused client is never put into DHCP mode.
    """
    wanted = set(device_names)
    actions = [
        item.model_copy(update={"depends_on": [], "apply_dependencies": []})
        for item in plan.actions
        if isinstance(item, SetEndpointDhcp) and item.device_name in wanted
    ]
    action_ids = {item.id for item in actions}
    device_ids = {item.device_id for item in actions}
    projected = ConfigurationPlan(
        id=f"{plan.id}/q3-fl-client-mode",
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


def q3_fastloop_service_plan(
    plan: ServicePlan, *, client_device_id: str = ""
) -> tuple[ServicePlan, tuple[ProjectionRewrite, ...]]:
    """Project E6 to the server setup, or to one client's acquisition.

    Without a client: the enable and the pool, their compiled server-state
    read-back, and the server's own foundation. With one: the same two server
    actions, which the caller passes as retained rows so they are never
    dispatched twice, that client's acquisition, its lease and attribution
    read-backs, and the server-state read-back the acquisition is staged on.
    The compiler makes every acquisition wait for that read-back to be
    VERIFIED, so it is read fresh before each client rather than borrowed.
    The compiler's dependency chain is kept whole, so no ordering is
    rewritten.

    One assertion does change, and it is returned: a foundation of a device
    this projection does not act on is removed. A client whose forwarding was
    refused has no verified DHCP mode, and it must not block the server setup
    or another client.
    """
    server_ids = {
        item.id
        for item in plan.actions
        if isinstance(item, EnableServerDhcp | ConfigureServerDhcpPool)
    }
    actions = [
        item
        for item in plan.actions
        if item.id in server_ids
        or (
            client_device_id
            and isinstance(item, AcquireDhcpLease)
            and item.host_device_id == client_device_id
        )
    ]
    action_ids = {item.id for item in actions}
    hosts = {item.host_device_id for item in actions}
    rewrites: list[ProjectionRewrite] = []
    expectations = []
    for item in plan.verification_expectations:
        if item.action_id not in action_ids:
            continue
        if item.kind is ServiceVerificationKind.DHCP_SERVER_STATE:
            expectations.append(item.model_copy(deep=True))
            continue
        if not client_device_id or item.client_device_id != client_device_id:
            continue
        expectations.append(item.model_copy(deep=True))
    foundations = []
    for item in plan.foundational_requirements:
        if item.device_id not in hosts:
            rewrites.append(
                ProjectionRewrite(
                    "foundation_removed",
                    item.configuration_action_id,
                    f"kind:{item.kind}:device:{item.device_name}:not_acted_on",
                )
            )
            continue
        foundations.append(item.model_copy(deep=True))
    expectation_ids = {item.id for item in expectations}
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
    suffix = (
        f"{Q3_FL_ACQUISITION_PROJECTION}:{client_device_id}"
        if client_device_id
        else Q3_FL_SERVER_PROJECTION
    )
    rewrites.append(
        ProjectionRewrite(
            "projection_identity",
            f"{plan.id}/{suffix}",
            f"source:{plan.id}:semantic_hash_retained:{plan.semantic_hash}",
        )
    )
    return (
        plan.model_copy(
            update={
                "id": f"{plan.id}/{suffix}",
                "services": services,
                "actions": actions,
                "foundational_requirements": foundations,
                "verification_expectations": expectations,
            },
            deep=True,
        ),
        tuple(rewrites),
    )


# -- SP-2 acquisition discriminator --------------------------------------------

#: The identities the SP-2 acquisition projections carry beside the source's.
SP2_ACQUISITION_REASSERT_PROJECTION = "sp2-acquisition-reassert"
SP2_ACQUISITION_START_PROJECTION = "sp2-acquisition-start"


def sp2_acquisition_reassert_plan(
    plan: ConfigurationPlan, *, device_names: Sequence[str]
) -> ConfigurationPlan:
    """Project E5 to one ordinary DHCP-mode assertion on each named client.

    The arm's clients are already in DHCP mode, which is exactly the state the
    native guarded mode path refuses. This projection therefore clears the
    four native binding fields, so the ordinary setter runs, and keeps every
    other field and the compiled mode read-back. Dependencies on effects the
    product already applied are dropped, as in the Q3-FL projection.
    """
    wanted = set(device_names)
    actions = [
        item.model_copy(
            update={
                "depends_on": [],
                "apply_dependencies": [],
                "native_server_device_name": "",
                "native_server_interface": "",
                "native_effective_pool_name": "",
                "native_inactive_clients": [],
            }
        )
        for item in plan.actions
        if isinstance(item, SetEndpointDhcp) and item.device_name in wanted
    ]
    if {item.device_name for item in actions} != wanted or len(actions) != len(wanted):
        raise ValueError("every reassertion client needs exactly one DHCP-mode action")
    action_ids = {item.id for item in actions}
    device_ids = {item.device_id for item in actions}
    projected = ConfigurationPlan(
        id=f"{plan.id}/{SP2_ACQUISITION_REASSERT_PROJECTION}",
        source_topology_id=plan.source_topology_id,
        source_topology_hash=plan.source_topology_hash,
        source_topology_hash_schema=plan.source_topology_hash_schema,
        actions=actions,
        devices=[
            item.model_copy(
                update={
                    "action_ids": [
                        value for value in item.action_ids if value in action_ids
                    ]
                },
                deep=True,
            )
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


def _acquisition_id(kind: str, *parts: str) -> str:
    semantic = "|".join((kind, *parts))
    return f"svc/{kind}/{hashlib.sha256(semantic.encode('utf-8')).hexdigest()[:16]}"


def sp2_acquisition_start_plan(
    plan: ServicePlan,
    configuration_plan: ConfigurationPlan,
    *,
    device_names: Sequence[str],
    nonce: str,
) -> ServicePlan:
    """Project E6 to the applied DHCP server setup plus one explicit start each.

    The mixed intent is state-only, so its plan holds no acquisition. Each
    named client gets one typed `AcquireDhcpLease` for its own segment's pool,
    derived as the compiler derives one: the pool's service, segment and
    network, a claim reference for that service and client, a dependency on
    the pool and on the service's compiled server-state read-back, and this
    run's nonce. Every DHCP pool and enable action is kept so the caller
    passes the product's rows as retained results; none is dispatched twice.
    Only the server-state read-backs the acquisitions wait on are kept, so
    each is read fresh before its start; the caller reads leases itself. A client without exactly one DHCP-mode action, or a segment
    without exactly one pool, raises ValueError before anything is built.
    """
    if not nonce:
        raise ValueError("an explicit start needs this run's nonce")
    wanted = set(device_names)
    modes = [
        item
        for item in configuration_plan.actions
        if isinstance(item, SetEndpointDhcp) and item.device_name in wanted
    ]
    if {item.device_name for item in modes} != wanted or len(modes) != len(wanted):
        raise ValueError(
            "every explicit-start client needs exactly one DHCP-mode action"
        )
    models = {item.device_id: item.model for item in configuration_plan.devices}
    pools: dict[str, ConfigureServerDhcpPool] = {}
    for item in plan.actions:
        if isinstance(item, ConfigureServerDhcpPool):
            if item.segment_id in pools:
                raise ValueError("a DHCP segment has more than one pool")
            pools[item.segment_id] = item
    server_state = {}
    for item in plan.verification_expectations:
        if item.kind is ServiceVerificationKind.DHCP_SERVER_STATE:
            if item.service_id in server_state:
                raise ValueError("a DHCP service has more than one server state")
            server_state[item.service_id] = item.id
    server_actions = [
        item
        for item in plan.actions
        if isinstance(item, ConfigureServerDhcpPool | EnableServerDhcp)
    ]
    acquisitions = []
    for mode in sorted(modes, key=lambda item: item.device_name):
        pool = pools.get(mode.segment_id)
        if pool is None or pool.service_id not in server_state:
            raise ValueError("an explicit-start client segment has no compiled pool")
        acquisitions.append(
            AcquireDhcpLease(
                id=_acquisition_id("sp2-acquire-dhcp", pool.service_id, mode.device_id),
                phase=ServicePhase.ACQUISITION,
                service_id=pool.service_id,
                service_type=ServiceType.DHCP,
                host_device_id=mode.device_id,
                host_device_name=mode.device_name,
                host_model=models.get(mode.device_id, ""),
                site_id=mode.site_id,
                depends_on=[pool.id],
                verification_dependencies=[server_state[pool.service_id]],
                required_capability="client_dhcp_acquisition",
                interface=mode.interface,
                segment_id=mode.segment_id,
                server_device_id=pool.host_device_id,
                server_device_name=pool.host_device_name,
                pool_name=pool.effective_pool_name or pool.pool_name,
                network=pool.network,
                prefix=pool.prefix,
                netmask=pool.netmask,
                claim_ref=_acquisition_id(
                    "sp2-dhcp-claim", pool.service_id, mode.device_id
                ),
                nonce=nonce,
            )
        )
    actions = [*server_actions, *acquisitions]
    action_ids = {item.id for item in actions}
    hosts = {item.host_device_id for item in actions}
    waited = {
        value for item in acquisitions for value in item.verification_dependencies
    }
    expectations = [
        item.model_copy(deep=True)
        for item in plan.verification_expectations
        if item.id in waited
    ]
    expectation_ids = {item.id for item in expectations}
    acquired_by_service: dict[str, list[str]] = {}
    for item in acquisitions:
        acquired_by_service.setdefault(item.service_id, []).append(item.id)
    services = [
        item.model_copy(
            update={
                "action_ids": [
                    *(value for value in item.action_ids if value in action_ids),
                    *acquired_by_service.get(item.id, []),
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
    foundations = [
        item.model_copy(deep=True)
        for item in plan.foundational_requirements
        if item.device_id in hosts
    ]
    projected = plan.model_copy(
        update={
            "id": f"{plan.id}/{SP2_ACQUISITION_START_PROJECTION}",
            "services": services,
            "actions": actions,
            "foundational_requirements": foundations,
            "verification_expectations": expectations,
        },
        deep=True,
    )
    projected.semantic_hash = service_plan_semantic_hash(projected)
    return projected


def q3_fastloop_fixture_placements(
    plan: ConfigurationPlan, *, vlan_id: int
) -> tuple[list, tuple[ProjectionRewrite, ...]]:
    """Return the compiled access placements bound to the fixture's own VLAN.

    The runner owns the physical fixture and applies no switch action, so the
    ports stay in the stock VLAN. The compiled switch, interface and endpoint
    placement is kept exactly; only the VLAN is rebound, and each rebinding is
    returned. Nothing is inferred from a device name.
    """
    actions = []
    rewrites: list[ProjectionRewrite] = []
    for item in plan.actions:
        if isinstance(item, ConfigureAccessPort) and item.data_vlan_id != vlan_id:
            rewrites.append(
                ProjectionRewrite(
                    "access_vlan_rebound",
                    f"{item.device_name}:{item.interface}",
                    f"{item.data_vlan_id}->{vlan_id}:runner_owned_fixture",
                )
            )
            actions.append(item.model_copy(update={"data_vlan_id": vlan_id}))
            continue
        actions.append(item)
    return actions, tuple(rewrites)


POOL_BEFORE_ENABLE = "pool-configured-before-enable"

_D_DHCP_SEAMS = (
    DiagnosticSeam(
        id=POOL_BEFORE_ENABLE,
        contract="ServicePlan.EnableServerDhcp.depends_on/apply_dependencies",
        current=(
            "the compiled Q3 plan orders the pool before process enable; "
            "the diagnostic still separates those effects and verifies the "
            "disabled pool state before activation"
        ),
        required=(
            "configure only the intended pool with the process still disabled, "
            "so a default transition can be attributed to the pool write alone"
        ),
        minimal_extension=(
            "the pool-only and enable-only projections return every removed "
            "dependency and retain the product setters; the diagnostic step "
            "stays blocked until its own seam is approved"
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
        # Two operations: the enable dispatch and its DHCP server-state
        # read-back. The projection records removal of the already applied
        # pool dependency, then retains the compiled enabled-state read.
        purpose="d-dhcp:e6:enable_only",
        retains=(
            "dispatch",
            "result",
            "postcondition",
            "read_back",
            "dependency_removed",
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
