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

The single rule everything here follows: **VERIFIED is derived only from
attributable evidence, never assumed.** A configuration foundation normally
copies its verification result, a link foundation requires deployment
read-back, and an endpoint foundation may resolve the backend's legitimate
PARTIAL ceiling only from its fresh, exact IPv4/netmask observation. Every
other disposition stays bounded so the gate refuses instead of being talked
into agreeing.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    FieldVerificationStatus,
    VerificationResult,
)
from ...domain.enterprise.models.control_plane import (
    ControlPlaneFoundationRequirement,
    ControlPlanePlan,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentResult,
    PhysicalObjectKind,
)
from ...domain.enterprise.models.service_plan import (
    FoundationalServiceRequirement,
    ServicePlan,
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
    left: ActionExecutionStatus,
    right: ActionExecutionStatus,
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


def endpoint_core_is_verified(
    *,
    source_configuration_id: str,
    source_configuration_hash: str,
    requirement_source_id: str,
    requirement_source_hash: str,
    configuration_result: ConfigurationApplicationResult,
    verification: VerificationResult,
) -> bool:
    """Whether one E5 row can satisfy its exact endpoint foundation.

    Plan-agnostic on purpose. E9 and E6 both need exactly this predicate,
    and the one thing that must not happen is two copies of it drifting
    apart: the E9 gate would keep refusing while the E6 gate started
    agreeing, about the same row. The caller supplies the identity it is
    binding against; the predicate never reads a plan.
    """
    if (
        requirement_source_hash != source_configuration_hash
        or configuration_result.config_plan_id != source_configuration_id
        or configuration_result.config_semantic_hash != source_configuration_hash
        or verification.action_id != requirement_source_id
        or not verification.expectation_id
        or verification.status
        not in {
            ActionExecutionStatus.PARTIAL,
            ActionExecutionStatus.VERIFIED,
        }
        or verification.evidence_method != "structured_endpoint_getters"
        or not verification.fresh_evidence
        or verification.fields.get("ipv4") is not FieldVerificationStatus.VERIFIED
        or verification.fields.get("netmask") is not FieldVerificationStatus.VERIFIED
        or verification.convergence is None
        or verification.convergence.final_status is not verification.status
    ):
        return False

    details = verification.convergence.details
    observation = details.get("last_observation")
    if (
        details.get("kind") != "endpoint_addressing"
        or not isinstance(observation, Mapping)
        or observation.get("device_found") is not True
        or observation.get("port_found") is not True
        or observation.get("address_channel") is not True
        or observation.get("fresh_evidence") is not True
        or observation.get("failure_reason") not in (None, "")
    ):
        return False

    device_name = details.get("device_name")
    interface = details.get("interface")
    return bool(
        isinstance(device_name, str)
        and device_name.strip()
        and isinstance(interface, str)
        and interface.strip()
        and observation.get("interface") == interface
        and str(observation.get("ipv4") or "").strip()
        and str(observation.get("netmask") or "").strip()
    )


def _configuration_foundation_status(
    plan: ControlPlanePlan,
    requirement: ControlPlaneFoundationRequirement,
    configuration_result: ConfigurationApplicationResult,
    verification: VerificationResult,
) -> ActionExecutionStatus:
    if requirement.kind != "endpoint_address":
        return verification.status
    if endpoint_core_is_verified(
        source_configuration_id=plan.source_configuration_id,
        source_configuration_hash=plan.source_configuration_hash,
        requirement_source_id=requirement.source_id,
        requirement_source_hash=requirement.source_hash,
        configuration_result=configuration_result,
        verification=verification,
    ):
        return ActionExecutionStatus.VERIFIED
    # A contradictory aggregate VERIFIED cannot outrank missing or stale core
    # evidence. Preserve every already-bounded status at its original strength.
    if verification.status is ActionExecutionStatus.VERIFIED:
        return ActionExecutionStatus.UNKNOWN
    return verification.status


def derive_foundational_statuses(
    plan: ControlPlanePlan,
    *,
    configuration_result: ConfigurationApplicationResult | None = None,
    physical_result: PhysicalDeploymentResult | None = None,
) -> dict[str, ActionExecutionStatus]:
    """Map executed foundation `source_id` values to supported statuses.

    Configuration foundations (`l3_interface`, `vlan`, `trunk`, `access_port`,
    `endpoint_address`) are keyed by a `ConfigurationAction.id`, and their
    evidence lives in `verification_results` -- **not** in `action_results`,
    whose ceiling is APPLIED because the configuration channel is
    fire-and-forget and cannot sustain a stronger claim.

    Link foundations are keyed by a `LinkPlan.id` and never appear in a
    configuration result at all; their evidence is the physical deployment's
    own read-back, translated through `_PHYSICAL_TO_ACTION`.

    Endpoint requirements are the deliberate exception to copying the aggregate
    E5 status: PT 9.0.1 can freshly verify IPv4 and netmask while gateway and DNS
    remain unobservable, leaving the E5 aggregate PARTIAL. That exact,
    attributable core observation satisfies only its matching E9
    `endpoint_address` requirement. No other PARTIAL status is promoted.

    Passing neither result returns an empty mapping, which makes the gate
    refuse. The plan scopes only the endpoint translation; it cannot supply a
    status directly. Other executed rows remain available to downstream gates
    such as Voice, which declare their own required source ids.
    """
    statuses: dict[str, ActionExecutionStatus] = {}
    requirements_by_source: dict[str, list[ControlPlaneFoundationRequirement]] = {}
    for requirement in plan.foundational_requirements:
        if requirement.source_id:
            requirements_by_source.setdefault(requirement.source_id, []).append(
                requirement,
            )

    if configuration_result is not None:
        for item in configuration_result.verification_results:
            requirements = requirements_by_source.get(item.action_id, ())
            if not requirements:
                _merge(statuses, item.action_id, item.status)
                continue
            for requirement in requirements:
                _merge(
                    statuses,
                    requirement.source_id,
                    _configuration_foundation_status(
                        plan,
                        requirement,
                        configuration_result,
                        item,
                    ),
                )

    if physical_result is not None:
        for item in physical_result.item_results:
            if item.target_kind is not PhysicalObjectKind.LINK:
                continue
            status = _PHYSICAL_TO_ACTION.get(
                item.status,
                ActionExecutionStatus.UNKNOWN,
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

    An endpoint requirement may carry the source configuration hash. It is
    projected only when it exactly matches the plan's own configuration hash;
    the requirement cannot bootstrap its arbitrary value into authority.
    Security keeps the same rule against its separately supplied hash.
    """
    hashes: dict[str, str] = {}
    for requirement in plan.foundational_requirements:
        if not requirement.source_hash:
            continue
        if (
            requirement.kind == "endpoint_address"
            and requirement.source_hash == plan.source_configuration_hash
        ):
            hashes[requirement.source_id] = plan.source_configuration_hash
        elif (
            requirement.kind == "security"
            and security_plan_hash
            and requirement.source_hash == security_plan_hash
        ):
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


def derive_service_foundational_statuses(
    plan: ServicePlan,
    configuration_result: ConfigurationApplicationResult,
) -> dict[str, ActionExecutionStatus]:
    """Map one E6 plan's foundational E5 actions to what was actually executed.

    `ServiceApplicator` refuses to apply anything whose foundation is not
    VERIFIED, and until now the only way to produce that mapping was for a
    caller to build it by hand -- which is the same defect this module was
    written to close for E9, in the stage that mutates a server's services.

    The rules are the E9 rules, not softer ones:

    - only rows for an action this plan actually names as a foundation count;
    - the E5 result must be the exact plan and semantic hash the E6 plan was
      compiled against, or nothing is derived and the gate refuses;
    - an `endpoint_address` foundation may be satisfied by a PARTIAL row whose
      IPv4/netmask core is fresh and attributable, through the SAME predicate
      E9 uses. It satisfies only its own action; it never promotes the E5 row
      and never speaks for gateway, DNS or any other field;
    - an aggregate VERIFIED with no attributable core degrades to UNKNOWN;
    - two rows disagreeing about one foundation resolve to the weaker. A
      conflict is never settled by choosing the success.

    Every other foundation kind copies its verification status, because no core
    predicate exists for it and inventing one here would be exactly the
    unattributable promotion the rest of this module refuses.
    """
    statuses: dict[str, ActionExecutionStatus] = {}
    requirements_by_action: dict[str, list[FoundationalServiceRequirement]] = {}
    for requirement in plan.foundational_requirements:
        if requirement.configuration_action_id:
            requirements_by_action.setdefault(
                requirement.configuration_action_id, []
            ).append(requirement)
    if not requirements_by_action:
        return statuses

    identity_matches = (
        configuration_result.config_plan_id == plan.source_configuration_id
        and configuration_result.config_semantic_hash == plan.source_configuration_hash
    )
    for item in configuration_result.verification_results:
        requirements = requirements_by_action.get(item.action_id)
        if not requirements:
            continue
        for requirement in requirements:
            _merge(
                statuses,
                requirement.configuration_action_id,
                _service_foundation_status(
                    plan, requirement, configuration_result, item, identity_matches
                ),
            )
    return statuses


def _service_foundation_status(
    plan: ServicePlan,
    requirement: FoundationalServiceRequirement,
    configuration_result: ConfigurationApplicationResult,
    verification: VerificationResult,
    identity_matches: bool,
) -> ActionExecutionStatus:
    if not identity_matches:
        # The rows describe a different configuration than the one this E6
        # plan was compiled against. They are evidence about something else.
        return ActionExecutionStatus.UNKNOWN
    if requirement.kind != "endpoint_address":
        return verification.status
    if endpoint_core_is_verified(
        source_configuration_id=plan.source_configuration_id,
        source_configuration_hash=plan.source_configuration_hash,
        requirement_source_id=requirement.configuration_action_id,
        requirement_source_hash=plan.source_configuration_hash,
        configuration_result=configuration_result,
        verification=verification,
    ):
        return ActionExecutionStatus.VERIFIED
    if verification.status is ActionExecutionStatus.VERIFIED:
        return ActionExecutionStatus.UNKNOWN
    return verification.status
