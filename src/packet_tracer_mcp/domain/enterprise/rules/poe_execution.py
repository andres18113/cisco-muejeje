"""Reconcile executable power uncertainty without creating delivery evidence."""
from __future__ import annotations

from ...models.errors import ErrorCode, PlanError, ValidationResult
from ..models.capabilities import PoEAuthorizedBinding
from ..models.hardware import PlannedNetworkDevice


def validate_poe_execution_uncertainty(
    device: PlannedNetworkDevice,
    required_bindings: list[PoEAuthorizedBinding],
) -> ValidationResult:
    """Require exact accounting of the attachments E5 actually compiled.

    A collection of individually authorized ports does not increase the
    measured simultaneous ceiling. Missing or malformed uncertainty cannot
    turn that evidence gap into a resolved plan.
    """
    required = set(required_bindings)
    authorized = (
        set(device.poe_authorized_bindings)
        if device.poe_capacity is not None else set()
    )
    unverified = required - authorized
    exceeds_capacity = bool(required) and (
        device.poe_capacity is None or len(required) > device.poe_capacity
    )
    uncertainty = device.poe_uncertainty
    problems = []
    if uncertainty is None:
        if unverified or exceeds_capacity:
            problems.append("missing exact binding or simultaneous-demand uncertainty")
    else:
        if (
            not required
            or set(uncertainty.required_bindings) != required
            or len(uncertainty.required_bindings) != len(required)
        ):
            problems.append("required bindings do not match the compiled powered attachments")
        if (
            set(uncertainty.unverified_bindings) != unverified
            or len(uncertainty.unverified_bindings) != len(unverified)
        ):
            problems.append("unverified bindings do not reconcile with exact claim authority")
        if uncertainty.required_simultaneous_ports != len(required):
            problems.append("simultaneous demand does not match the compiled powered attachments")
        if not uncertainty.reason.strip():
            problems.append("uncertainty has no attributable reason")
    return ValidationResult(errors=[PlanError(
        code=ErrorCode.CAPABILITY_PROBE_FAILED,
        message=f"{device.id}: inconsistent PoE execution uncertainty: {problem}.",
        suggestion="Rederive exact demand and uncertainty without promoting PoE claims.",
    ) for problem in problems])
