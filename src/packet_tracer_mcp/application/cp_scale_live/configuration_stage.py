"""Configuration acceptance and its governed mutation-free operational reread."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..use_cases.apply_configuration import ConfigurationApplicator
from ..use_cases.execute_enterprise_reference import configuration_application_contradiction
from ..use_cases.qualify_cp_scale_live import (
    canonical_configuration_reread_scope,
    canonical_configuration_retryable_operational_unknown,
    canonical_stage_configuration_error,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus, ConfigurationApplicationResult, ConfigurationRuntimeContext,
)
from ...domain.enterprise.models.deployment import DeploymentManifest
from .contracts import (
    CPScaleConfigurationReport, CPScaleObservationRecord, CPScaleRereadScope,
    CPScaleStageExecutionInput,
)


@dataclass(frozen=True)
class CPScaleConfigurationStageResult:
    configuration: ConfigurationApplicationResult | None
    attempts: tuple[ConfigurationApplicationResult, ...]
    accepted: bool
    report: CPScaleConfigurationReport
    error: str = ""


class _ConfigurationStopped(RuntimeError):
    pass


class CPScaleConfigurationStage:
    """The caller owns the applicator; all attempt state belongs to one call."""

    def __init__(
        self, applicator: ConfigurationApplicator, *,
        serial_wait: Callable,
        acceptance_policy: Callable = canonical_stage_configuration_error,
        retry_policy: Callable = canonical_configuration_retryable_operational_unknown,
        contradiction_policy: Callable = configuration_application_contradiction,
    ) -> None:
        self.applicator = applicator
        self.serial_wait = serial_wait
        self.acceptance_policy = acceptance_policy
        self.retry_policy = retry_policy
        self.contradiction_policy = contradiction_policy

    def execute(
        self, request: CPScaleStageExecutionInput, manifest: DeploymentManifest,
        configuration_mutation_ids: tuple[str, ...], *,
        defer_voice_signal: bool,
        configuration_phase_observer: Callable[[int, tuple[str, ...]], None],
    ) -> CPScaleConfigurationStageResult:
        projection = request.projection
        plan = projection.configuration
        attempts: list[ConfigurationApplicationResult] = []
        contradictions: list[str] = []
        serial = None
        reread = None
        acceptance_error = None
        error = ""
        previous = request.continuity.previous_configuration
        context = ConfigurationRuntimeContext(environment_fingerprint=request.fingerprint)

        def apply(ids, retained, deferred=()):
            result = self.applicator.apply(
                plan,
                actual_source_topology_hash=projection.topology.physical_identity_hash,
                capabilities=request.composition.capabilities,
                runtime_context=context, deployment_manifest=manifest,
                defer_voice_signal_until_bootstrap=defer_voice_signal,
                mutation_action_ids=ids, retained_action_results=retained,
                retained_deferred_voice_action_ids=deferred,
                phase_observer=configuration_phase_observer,
            )
            attempts.append(result)
            contradiction = self.contradiction_policy(result)
            contradictions.append(contradiction)
            if contradiction:
                label = " re-read" if len(attempts) > 1 else ""
                raise _ConfigurationStopped(
                    f"Configuration{label} at {projection.stage.value!r} contradicted the plan: "
                    + contradiction
                )
            return result

        try:
            configuration = apply(
                configuration_mutation_ids,
                previous.action_results if previous is not None else (),
            )
            ready, readings = self.serial_wait(projection)
            serial = CPScaleObservationRecord(
                "serial_interfaces", projection.stage, "required_serial_readback",
                "verified" if ready else "unobservable", {"readings": readings},
            )
            if not ready:
                raise _ConfigurationStopped(
                    f"Serial interfaces lost up/up convergence at {projection.stage.value!r}."
                )
            candidate_error = self.acceptance_policy(
                plan, configuration, allow_deferred_voice_signal=defer_voice_signal,
            )
            if candidate_error and self.retry_policy(
                plan, configuration, allow_deferred_voice_signal=defer_voice_signal,
            ):
                try:
                    ids, retained = canonical_configuration_reread_scope(plan, configuration)
                except ValueError as exc:
                    reread = CPScaleRereadScope(False, error=str(exc))
                    raise _ConfigurationStopped(str(exc)) from exc
                barrier = configuration.voice_signal_barrier
                deferred = (
                    tuple(barrier.deferred_action_ids)
                    if barrier is not None and barrier.signal_status is ActionExecutionStatus.INTENDED
                    else ()
                )
                reread = CPScaleRereadScope(
                    not ids, tuple(ids), tuple(item.action_id for item in retained), deferred,
                )
                configuration = apply(ids, retained, deferred)
                candidate_error = self.acceptance_policy(
                    plan, configuration, allow_deferred_voice_signal=defer_voice_signal,
                )
            acceptance_error = candidate_error
            if acceptance_error:
                raise _ConfigurationStopped(
                    f"Configuration at {projection.stage.value!r} exceeded its governed "
                    "observability envelope: " + acceptance_error
                )
        except Exception as exc:
            error = str(exc) if isinstance(exc, _ConfigurationStopped) else f"{type(exc).__name__}: {exc}"
        return CPScaleConfigurationStageResult(
            attempts[-1] if attempts else None, tuple(attempts), not error,
            CPScaleConfigurationReport(tuple(contradictions), serial, reread, acceptance_error), error,
        )
