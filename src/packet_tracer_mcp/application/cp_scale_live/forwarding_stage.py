"""Required forwarding follows E9 and retains ordered evidence and first failure."""

from __future__ import annotations

from .contracts import CPScaleForwardingResult, CPScaleStageExecutionInput
from .observation import CPScaleRequiredObservations
from ..use_cases.compose_cp_scale_canonical import CPScaleSiteForwardingCheck
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
        if request.site_forwarding_checks:
            site = self.observations.site_forwarding(request.site_forwarding_checks)
            first_failure = next((
                check.id for index, check in enumerate(request.site_forwarding_checks)
                if index >= len(site) or site[index].check is not check
                or not site[index].verified or not site[index].attempts
                or not site_forwarding_verified(check, site[index].attempts[-1])
            ), "")
            if not first_failure and len(site) != len(request.site_forwarding_checks):
                first_failure = site[len(request.site_forwarding_checks)].check.id
            verified = not first_failure
            return CPScaleForwardingResult(
                True, core, site, verified, first_failure,
                "" if verified else f"Site forwarding failed at {stage.value!r}; first failed check: {first_failure}.",
            )
        return CPScaleForwardingResult(True, core)
