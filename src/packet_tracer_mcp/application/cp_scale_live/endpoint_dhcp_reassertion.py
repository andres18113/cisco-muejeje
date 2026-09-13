"""One state-authorized CP-SCALE DHCP endpoint reassertion."""

from __future__ import annotations

from ..use_cases.qualify_cp_scale_live import (
    canonical_configuration_reread_scope,
    canonical_stage_configuration_error,
)
from ...domain.enterprise.models.configuration import (
    ConfigurationPlan,
    ConfigureAccessPort,
    SetEndpointDhcp,
    VerificationKind,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    FieldVerificationStatus,
)
from ...domain.enterprise.models.execution import satisfies_apply_dependency


_UNADDRESSED_ENDPOINT_VALUES = frozenset({"", "0.0.0.0"})


def _eligible_action_ids(
    plan: ConfigurationPlan,
    application: ConfigurationApplicationResult,
    *,
    allow_deferred_voice_signal: bool,
) -> tuple[str, ...]:
    actions = {item.id: item for item in plan.actions}
    expectations = {
        item.id: item for item in plan.verification_expectations
    }
    action_results = {
        item.action_id: item for item in application.action_results
    }
    verification_by_action = {
        item.action_id: item for item in application.verification_results
    }
    if (
        len(actions) != len(plan.actions)
        or len(expectations) != len(plan.verification_expectations)
        or len(action_results) != len(application.action_results)
        or len(verification_by_action) != len(application.verification_results)
    ):
        return ()

    selected: list[str] = []
    mutation_ids = set(application.mutation_action_ids)
    for item in application.verification_results:
        expectation = expectations.get(item.expectation_id)
        action = actions.get(item.action_id)
        if (
            expectation is None
            or expectation.action_id != item.action_id
            or expectation.kind is not VerificationKind.ENDPOINT_ADDRESSING
            or expectation.expected.get("mode") != "dhcp"
            or not isinstance(action, SetEndpointDhcp)
            or action.id not in mutation_ids
            or item.status is not ActionExecutionStatus.FAILED
            or not item.fresh_evidence
            or item.evidence_method != "structured_endpoint_getters"
            or item.fields != {
                "ipv4": FieldVerificationStatus.FAILED,
                "netmask": FieldVerificationStatus.FAILED,
                "gateway": FieldVerificationStatus.UNOBSERVABLE,
                "dns": FieldVerificationStatus.UNOBSERVABLE,
            }
            or item.convergence is None
            or item.convergence.final_status is not ActionExecutionStatus.FAILED
            or item.convergence.attempts <= 0
        ):
            continue
        details = item.convergence.details
        last = details.get("last_observation")
        if (
            details.get("kind") != "endpoint_addressing"
            or not isinstance(last, dict)
            or last.get("device_found") is not True
            or last.get("port_found") is not True
            or last.get("address_channel") is not True
            or last.get("fresh_evidence") is not True
            or str(last.get("interface") or "")
            != str(expectation.expected.get("interface") or "")
            or str(last.get("ipv4") or "").casefold()
            not in _UNADDRESSED_ENDPOINT_VALUES
            or str(last.get("netmask") or "").casefold()
            not in _UNADDRESSED_ENDPOINT_VALUES
            or str(last.get("failure_reason") or "")
        ):
            continue
        applied = action_results.get(action.id)
        if applied is None or not satisfies_apply_dependency(applied.status):
            continue
        access_dependencies = [
            dependency for dependency in action.depends_on
            if isinstance(actions.get(dependency), ConfigureAccessPort)
        ]
        if len(access_dependencies) != 1:
            continue
        access = verification_by_action.get(access_dependencies[0])
        if (
            access is None
            or access.status is not ActionExecutionStatus.VERIFIED
            or not access.fresh_evidence
            or any(
                value is not FieldVerificationStatus.VERIFIED
                for value in access.fields.values()
            )
        ):
            continue
        selected.append(action.id)

    if not selected:
        return ()
    candidate = application.model_copy(deep=True)
    candidate.status = ConfigurationApplicationStatus.PARTIAL
    selected_set = set(selected)
    for item in candidate.verification_results:
        if item.action_id not in selected_set:
            continue
        item.status = ActionExecutionStatus.PARTIAL
        item.fields = {
            "ipv4": FieldVerificationStatus.VERIFIED,
            "netmask": FieldVerificationStatus.VERIFIED,
            "gateway": FieldVerificationStatus.UNOBSERVABLE,
            "dns": FieldVerificationStatus.UNOBSERVABLE,
        }
    if allow_deferred_voice_signal:
        barrier = candidate.voice_signal_barrier
        if barrier is None or not barrier.deferred_action_ids:
            return ()
        pending_voice_ids = set(barrier.deferred_action_ids)
        barrier.foundation_status = ActionExecutionStatus.VERIFIED
        barrier.signal_status = ActionExecutionStatus.INTENDED
        for item in candidate.verification_results:
            if item.action_id not in pending_voice_ids:
                continue
            item.status = ActionExecutionStatus.PARTIAL
            item.evidence_method = ""
            item.fresh_evidence = False
            item.fields = {}
            item.message = (
                "Voice VLAN verification is pending successful Voice bootstrap."
            )
    if canonical_stage_configuration_error(
        plan,
        candidate,
        allow_deferred_voice_signal=allow_deferred_voice_signal,
    ):
        return ()
    return tuple(
        action.id for action in plan.actions if action.id in selected_set
    )


def retryable_endpoint_dhcp_absence(
    plan: ConfigurationPlan,
    application: ConfigurationApplicationResult,
    *,
    allow_deferred_voice_signal: bool = False,
) -> bool:
    """Whether one journaled delta reassertion follows exact DHCP absence."""

    return bool(_eligible_action_ids(
        plan,
        application,
        allow_deferred_voice_signal=allow_deferred_voice_signal,
    ))


def endpoint_dhcp_reassertion_scope(
    plan: ConfigurationPlan,
    application: ConfigurationApplicationResult,
    *,
    allow_deferred_voice_signal: bool = False,
) -> tuple[tuple[str, ...], tuple[ActionApplicationResult, ...]]:
    """Keep the first attempt immutable and reassert only its failed DHCP delta."""

    mutation_ids = _eligible_action_ids(
        plan,
        application,
        allow_deferred_voice_signal=allow_deferred_voice_signal,
    )
    if not mutation_ids:
        raise ValueError(
            "Configuration DHCP reassertion has no exact eligible absence."
        )
    retained_source = application.model_copy(deep=True)
    if allow_deferred_voice_signal:
        barrier = retained_source.voice_signal_barrier
        if barrier is None or not barrier.deferred_action_ids:
            raise ValueError(
                "Configuration DHCP reassertion lost deferred Voice state."
            )
        barrier.foundation_status = ActionExecutionStatus.VERIFIED
        barrier.signal_status = ActionExecutionStatus.INTENDED
    _, retained = canonical_configuration_reread_scope(
        plan,
        retained_source,
    )
    selected = set(mutation_ids)
    return mutation_ids, tuple(
        item for item in retained if item.action_id not in selected
    )
