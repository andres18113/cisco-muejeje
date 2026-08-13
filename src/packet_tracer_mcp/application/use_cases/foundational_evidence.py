"""Derive control-plane foundational evidence from what the product executed.

`ControlPlaneApplicator` gates every typed action on the configuration it
depends on having been VERIFIED. Nothing in `src/` ever produced those
statuses, so the only existing callers built them by hand -- and the University
Topology Acceptance built them with a comprehension over the gate's own inputs:

    foundational_statuses={i.source_id: ActionExecutionStatus.VERIFIED
                           for i in compiled.plan.foundational_requirements}

That declares every requirement satisfied without consulting any evidence. The
gate is real product code; fed that way it decides nothing. Closing
`TD-ACCEPTANCE-001` row 4 means deriving the same mapping from executed
results, which is what this module does.

The single rule everything here follows: **VERIFIED is only ever copied, never
minted.** A configuration foundation is VERIFIED when its verification result
says so, and a link foundation is VERIFIED when the deployment actually
observed it. Every other disposition is carried through at its own strength,
so the gate refuses instead of being talked into agreeing.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
)
from ...domain.enterprise.models.control_plane import ControlPlanePlan
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentResult,
    PhysicalObjectKind,
)

#: Strength order used only to resolve a conflict, never to upgrade anything.
#: Lower wins, so two sources disagreeing about one foundation fail closed.
_STATUS_STRENGTH: dict[ActionExecutionStatus, int] = {
    ActionExecutionStatus.FAILED: 0,
    ActionExecutionStatus.DEPENDENCY_BLOCKED: 10,
    ActionExecutionStatus.SKIPPED: 20,
    ActionExecutionStatus.UNKNOWN: 20,
    ActionExecutionStatus.UNOBSERVABLE: 30,
    ActionExecutionStatus.INTENDED: 40,
    ActionExecutionStatus.COMPILED: 50,
    ActionExecutionStatus.PARTIAL: 60,
    ActionExecutionStatus.APPLIED: 70,
    ActionExecutionStatus.NO_OP: 80,
    ActionExecutionStatus.REASSERTED: 80,
    ActionExecutionStatus.VERIFIED: 100,
}

#: A physical item becomes a foundation status only through this table. The
#: asymmetry is the point: OBSERVED is the one disposition backed by a fresh
#: read-back of the runtime, so it is the only one that may reach VERIFIED.
#: APPLIED means the payload was accepted, which is exactly the claim
#: `ActionExecutionStatus.APPLIED` already exists to bound.
_PHYSICAL_TO_ACTION: dict[PhysicalDeploymentItemStatus, ActionExecutionStatus] = {
    PhysicalDeploymentItemStatus.OBSERVED: ActionExecutionStatus.VERIFIED,
    PhysicalDeploymentItemStatus.SATISFIED: ActionExecutionStatus.APPLIED,
    PhysicalDeploymentItemStatus.APPLIED: ActionExecutionStatus.APPLIED,
    PhysicalDeploymentItemStatus.NOT_ATTEMPTED: ActionExecutionStatus.INTENDED,
    PhysicalDeploymentItemStatus.FAILED: ActionExecutionStatus.FAILED,
}


def _weakest(
    left: ActionExecutionStatus, right: ActionExecutionStatus,
) -> ActionExecutionStatus:
    """Two sources disagreeing about one foundation resolve to the weaker."""
    unknown = _STATUS_STRENGTH[ActionExecutionStatus.UNKNOWN]
    if _STATUS_STRENGTH.get(right, unknown) < _STATUS_STRENGTH.get(left, unknown):
        return right
    return left


def _merge(
    target: dict[str, ActionExecutionStatus],
    source_id: str,
    status: ActionExecutionStatus,
) -> None:
    if not source_id:
        return
    existing = target.get(source_id)
    target[source_id] = status if existing is None else _weakest(existing, status)


def derive_foundational_statuses(
    *,
    configuration_result: ConfigurationApplicationResult | None = None,
    physical_result: PhysicalDeploymentResult | None = None,
) -> dict[str, ActionExecutionStatus]:
    """Map every foundation `source_id` to the status its evidence supports.

    Configuration foundations (`l3_interface`, `vlan`, `trunk`, `access_port`,
    `endpoint_address`) are keyed by a `ConfigurationAction.id`, and their
    evidence lives in `verification_results` -- **not** in `action_results`,
    whose ceiling is APPLIED because the configuration channel is
    fire-and-forget and cannot sustain a stronger claim.

    Link foundations are keyed by a `LinkPlan.id` and never appear in a
    configuration result at all; their evidence is the physical deployment's
    own read-back, translated through `_PHYSICAL_TO_ACTION`.

    Passing neither result returns an empty mapping, which makes the gate
    refuse. That is the correct answer to "no evidence", and it is why this
    function has no parameter that could supply a status directly.
    """
    statuses: dict[str, ActionExecutionStatus] = {}

    if configuration_result is not None:
        for item in configuration_result.verification_results:
            _merge(statuses, item.action_id, item.status)

    if physical_result is not None:
        for item in physical_result.item_results:
            if item.target_kind is not PhysicalObjectKind.LINK:
                continue
            status = _PHYSICAL_TO_ACTION.get(
                item.status, ActionExecutionStatus.UNKNOWN,
            )
            # `observed` is the field the deployer sets from a real read-back.
            # A row claiming OBSERVED without it is not evidence of anything.
            if status is ActionExecutionStatus.VERIFIED and not item.observed:
                status = ActionExecutionStatus.UNKNOWN
            _merge(statuses, item.target_id, status)

    return statuses


def derive_foundational_hashes(
    plan: ControlPlanePlan,
    *,
    security_plan_hash: str = "",
) -> dict[str, str]:
    """Hashes for the foundations that actually declare one.

    Only `kind="security"` requirements carry a non-empty `source_hash`; every
    other kind leaves it blank and the gate skips the comparison. So an empty
    mapping is the honest answer for a routing-only plan, and inventing entries
    for the other kinds would compare a value against nothing.
    """
    hashes: dict[str, str] = {}
    for requirement in plan.foundational_requirements:
        if not requirement.source_hash:
            continue
        if requirement.kind == "security" and security_plan_hash:
            hashes[requirement.source_id] = security_plan_hash
    return hashes


def unmet_foundations(
    plan: ControlPlanePlan,
    statuses: Mapping[str, ActionExecutionStatus],
    hashes: Mapping[str, str] | None = None,
) -> list[str]:
    """Preview what the gate will reject, without dispatching anything.

    Deliberately mirrors `ControlPlaneApplicator._foundation_errors` rather
    than relaxing it: an orchestrator should be able to see that a foundation
    is missing before it mutates a runtime, and a preview that disagreed with
    the gate would be worse than none.
    """
    resolved = hashes or {}
    unmet: list[str] = []
    for requirement in plan.foundational_requirements:
        status = statuses.get(requirement.source_id)
        if status is not ActionExecutionStatus.VERIFIED:
            observed = status.value if status is not None else "absent"
            unmet.append(
                f"{requirement.kind}:{requirement.source_id} is {observed}, "
                "not verified.",
            )
        if (
            requirement.source_hash
            and resolved.get(requirement.source_id) != requirement.source_hash
        ):
            unmet.append(
                f"{requirement.kind}:{requirement.source_id} source hash "
                "does not match.",
            )
    return sorted(set(unmet))
