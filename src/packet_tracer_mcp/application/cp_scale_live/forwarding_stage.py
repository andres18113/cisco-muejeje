"""Required forwarding follows E9 and retains ordered evidence and first failure."""

from __future__ import annotations

from .contracts import (
    CPScaleForwardingResult,
    CPScaleSelectedSiteForwardingObservation,
    CPScaleStageExecutionInput,
)
from .observation import CPScaleRequiredObservations
from ..use_cases.compose_cp_scale_canonical import CPScaleSiteForwardingCheck
from ..use_cases.compose_cp_scale_canonical import CPScaleSelectedSiteForwardingCheck
from ...domain.enterprise.models.configuration_runtime import ActionExecutionStatus
from ...domain.models.typed_ping import TypedPingResult


def core_forwarding_verified(result: TypedPingResult) -> bool:
    return bool(result.fresh_output_observed and result.reachable is True)


def site_forwarding_verified(check: CPScaleSiteForwardingCheck, result: TypedPingResult) -> bool:
    return bool(
        core_forwarding_verified(result)
        and result.dispatched_destination == check.destination_ipv4
        and result.observed_device_name == check.source_device_name
        and result.device_identity_provenance == "confirmed_unique"
    )


def _selected_probe_verified(observation, *, source_binding: bool) -> bool:
    if not observation.probes or not observation.attempts:
        return False
    probe = observation.probes[-1]
    return bool(
        getattr(probe, "status", None) is ActionExecutionStatus.VERIFIED
        and getattr(probe, "verified", False) is True
        and getattr(probe, "bindings_stable", False) is True
        and getattr(probe, "communication_observed", False) is True
        and getattr(probe, "ping", None) is observation.attempts[-1]
        and getattr(probe, "destination_binding", None)
        is observation.destination_binding
        and (
            getattr(probe, "source_binding", None) is observation.source_binding
            if source_binding else getattr(probe, "source_binding", None) is None
        )
    )


class CPScaleForwardingStage:
    def __init__(self, observations: CPScaleRequiredObservations) -> None:
        self.observations = observations

    def execute(self, request: CPScaleStageExecutionInput) -> CPScaleForwardingResult:
        stage = request.projection.stage
        core = self.observations.core_forwarding(request.projection.forwarding_checks)
        # Exact ordered coverage is authority: an empty/duplicated adapter reply
        # must not turn a declared requirement into a vacuous success.
        verified = (
            tuple((item.source_device_name, item.destination_ipv4) for item in core)
            == tuple(request.projection.forwarding_checks.items())
            and all(item.verified and item.attempts and core_forwarding_verified(item.attempts[-1]) for item in core)
        )
        if not verified:
            return CPScaleForwardingResult(False, core,
                error=f"Core forwarding regressed at {stage.value!r}.")
        site = ()
        site_verified = None
        first_failure = ""
        if request.site_forwarding_checks:
            site = (
                self.observations.site_forwarding(
                    request.site_forwarding_checks,
                    request.deployment.manifest,
                )
                if any(
                    isinstance(item, CPScaleSelectedSiteForwardingCheck)
                    for item in request.site_forwarding_checks
                )
                else self.observations.site_forwarding(
                    request.site_forwarding_checks,
                )
            )
            first_failure = next((
                check.id for index, check in enumerate(request.site_forwarding_checks)
                if index >= len(site) or site[index].check is not check
                or not site[index].verified or not site[index].attempts
                or (
                    isinstance(check, CPScaleSelectedSiteForwardingCheck)
                    and (
                        not isinstance(
                            site[index],
                            CPScaleSelectedSiteForwardingObservation,
                        )
                        or site[index].status is not ActionExecutionStatus.VERIFIED
                        or site[index].destination_binding is None
                        or not _selected_probe_verified(
                            site[index],
                            source_binding=False,
                        )
                    )
                )
                or (
                    not isinstance(check, CPScaleSelectedSiteForwardingCheck)
                    and not site_forwarding_verified(check, site[index].attempts[-1])
                )
            ), "")
            if not first_failure and len(site) != len(request.site_forwarding_checks):
                first_failure = site[len(request.site_forwarding_checks)].check.id
            site_verified = not first_failure

        user = ()
        user_verified = None
        user_first_failure = ""
        if request.user_forwarding_checks:
            user = self.observations.user_forwarding(
                request.user_forwarding_checks,
                request.deployment.manifest,
            )
            user_first_failure = next((
                check.id
                for index, check in enumerate(request.user_forwarding_checks)
                if index >= len(user)
                or user[index].check is not check
                or user[index].status is not ActionExecutionStatus.VERIFIED
                or not user[index].verified
                or not user[index].attempts
                or not user[index].probes
                or user[index].source_binding is None
                or user[index].destination_binding is None
                or not _selected_probe_verified(
                    user[index],
                    source_binding=True,
                )
            ), "")
            if (
                not user_first_failure
                and len(user) != len(request.user_forwarding_checks)
            ):
                user_first_failure = user[
                    len(request.user_forwarding_checks)
                ].check.id
            user_verified = not user_first_failure

        errors = []
        if site_verified is False:
            errors.append(
                f"Site forwarding failed at {stage.value!r}; first failed check: {first_failure}."
            )
        if user_verified is False:
            errors.append(
                f"User communication failed at {stage.value!r}; first failed check: {user_first_failure}."
            )
        return CPScaleForwardingResult(
            core_verified=True,
            core=core,
            site=site,
            site_verified=site_verified,
            first_failure=first_failure,
            error=" ".join(errors),
            user=user,
            user_verified=user_verified,
            user_first_failure=user_first_failure,
        )
