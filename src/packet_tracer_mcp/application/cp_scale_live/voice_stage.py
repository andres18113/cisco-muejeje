"""Voice application and bounded contradiction policy; models remain typed."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from ..use_cases.apply_voice import VoiceApplicator, VoiceRuntime
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStageProjection
from ..use_cases.compose_enterprise_reference import EnterpriseReferenceComposition
from ...domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult, ActionExecutionStatus, ConfigurationRuntimeContext, ConfigurationApplicationResult,
)
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.voice_plan import VoicePlan
from ...domain.enterprise.models.voice_runtime import VoiceApplicationResult
from .contracts import (
    CP_SCALE_REALTIME_FIELDS,
    CPScaleObservationRecord,
    CPScaleRealtimeState,
    CPScaleVoiceStageResult,
)


def realtime_boundary_error(state: CPScaleRealtimeState | None, edge: str) -> str:
    if state is None or type(state) is not CPScaleRealtimeState:
        return (
            f"The simulation state {edge} the authoritative voice window was not "
            "observable, so the window cannot be attributed to REALTIME."
        )
    if (
        type(state.present) is not tuple
        or any(
            type(name) is not str or name not in CP_SCALE_REALTIME_FIELDS
            for name in state.present
        )
        or "observed" not in state.present
        or "simulation_mode" not in state.present
    ):
        return (
            f"The simulation state {edge} the authoritative voice window did not "
            "explicitly expose both observed and simulation_mode, so the window "
            "cannot be attributed to REALTIME."
        )
    if type(state.observed) is not bool or type(state.simulation_mode) is not bool:
        return (
            f"The simulation state {edge} the authoritative voice window did not "
            "contain explicit boolean observed and simulation_mode values, so the "
            "window cannot be attributed to REALTIME."
        )
    if state.observed is not True:
        return (
            f"The simulation state {edge} the authoritative voice window was not "
            "observable, so the window cannot be attributed to REALTIME."
        )
    if state.simulation_mode is True:
        return (
            f"Packet Tracer was in Simulation mode {edge} the authoritative voice "
            "window. Packets do not progress autonomously there, so the window "
            "is not a REALTIME acquisition."
        )
    return ""


def voice_error(plan: VoicePlan, result: VoiceApplicationResult) -> str:
    if result.preflight_errors:
        return "; ".join(result.preflight_errors)
    refused = sorted(
        f"{item.action_id}: {item.message}" for item in result.action_results
        if item.status is ActionExecutionStatus.FAILED
    )
    if refused:
        return "Packet Tracer refused voice actions: " + "; ".join(refused)
    if Counter(item.id for item in getattr(plan, "call_expectations", [])) != Counter(
        item.call_expectation_id for item in getattr(result, "calls", [])
    ):
        return "Voice call result inventory did not match the typed plan."
    failed_calls = [
        item.call_expectation_id for item in getattr(result, "calls", [])
        if item.status is ActionExecutionStatus.FAILED
    ]
    if failed_calls:
        return "Voice call behavior contradicted the plan for: " + ", ".join(sorted(failed_calls))
    addressing = sorted(
        f"{item.phone_id}: {item.addressing_message}" for item in result.registrations
        if item.addressing_status is ActionExecutionStatus.FAILED
    )
    if addressing:
        return "Observed phone addressing contradicted the plan: " + "; ".join(addressing)
    registration = sorted(
        f"{item.phone_id}: {item.message}" for item in result.registrations
        if item.status is ActionExecutionStatus.FAILED
    )
    if registration:
        return "Observed phone registration contradicted the plan: " + "; ".join(registration)
    return ""


class CPScaleVoiceStage:
    def __init__(self, applicator: VoiceApplicator, runtime: VoiceRuntime) -> None:
        self.applicator = applicator
        self.runtime = runtime

    def apply(
        self, projection: CPScaleCanonicalStageProjection, *,
        composition: EnterpriseReferenceComposition,
        configuration: ConfigurationApplicationResult | None,
        statuses: dict[str, ActionExecutionStatus],
        context: ConfigurationRuntimeContext, manifest: DeploymentManifest | None,
        voice_mutation_ids: tuple[str, ...] | None = None,
        retained_voice_action_results: tuple[ActionApplicationResult, ...] = (),
        complete_voice_signal: Callable[[], dict[str, ActionExecutionStatus]] | None = None,
        lifecycle_observer: Callable[[str], None] | None = None,
    ) -> CPScaleVoiceStageResult:
        plan = getattr(projection, "voice", None)
        if plan is None or not plan.actions:
            return CPScaleVoiceStageResult(None, False, reason="This stage carries no phone.")
        result = self.applicator.apply(
            plan,
            actual_source_topology_hash=projection.topology.physical_identity_hash,
            actual_source_configuration_hash=projection.configuration.semantic_hash,
            foundational_statuses=statuses, capabilities=composition.voice_capabilities,
            runtime_context=context, deployment_manifest=manifest,
            mutation_action_ids=voice_mutation_ids,
            retained_action_results=retained_voice_action_results,
            complete_voice_signal=complete_voice_signal,
            lifecycle_observer=lifecycle_observer,
        )
        drain = getattr(self.runtime, "drain_diagnostic_evidence", None)
        diagnostic_error = ""
        try:
            diagnostic_evidence = drain() if callable(drain) else {}
        except Exception as exc:
            diagnostic_evidence = {}
            diagnostic_error = f"{type(exc).__name__}: {exc}"
        diagnostics = CPScaleObservationRecord(
            "voice_runtime_diagnostics", projection.stage, "voice_runtime", "diagnostic_only",
            diagnostic_evidence, error=diagnostic_error,
        )
        return CPScaleVoiceStageResult(
            result, True, error=voice_error(plan, result), runtime_diagnostics=diagnostics,
        )
