"""Canonical step decisions; the sequence mechanism has no such knowledge."""
from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import CPScaleStageContinuity, CPScaleObservationRecord, CPScaleLiveStageResult
from ..use_cases.compose_cp_scale_canonical import CPScaleCanonicalStage, CPScaleCanonicalTarget, CPScaleCanonicalTargetContract


@dataclass(frozen=True)
class CPScaleStepContinuity:
    stage: CPScaleStageContinuity = field(default_factory=CPScaleStageContinuity)
    dhcp_baseline: CPScaleObservationRecord | None = None


@dataclass(frozen=True)
class CPScaleStepDecision:
    floor1_statistics: bool
    acquire_dhcp_baseline: bool
    capture_serial_core: bool
    site_forwarding: bool
    checkpoint_required: bool


def canonical_step_decision(target: CPScaleCanonicalTargetContract, stage: CPScaleCanonicalStage) -> CPScaleStepDecision:
    router0 = target.target is CPScaleCanonicalTarget.ROUTER0_BRANCH
    return CPScaleStepDecision(stage is CPScaleCanonicalStage.FLOOR1,
        stage is CPScaleCanonicalStage.ROUTER4_SWITCH10, stage is CPScaleCanonicalStage.ROUTING_CORE,
        router0 and stage is CPScaleCanonicalStage.ROUTER0_BRANCH,
        not (router0 and stage is target.terminal_stage))


def canonical_step_result_error(result: CPScaleLiveStageResult) -> str:
    projection = result.projection
    if result.voice is None and projection.voice is not None and projection.voice.actions:
        return f"Verified stage {result.stage.value!r} did not retain its Voice application results."
    if result.control_plane is None:
        return f"Verified stage {result.stage.value!r} did not retain its control-plane result."
    return ""


def advance_canonical_continuity(previous: CPScaleStepContinuity, result: CPScaleLiveStageResult,
                                decision: CPScaleStepDecision,
                                baseline: CPScaleObservationRecord | None) -> CPScaleStepContinuity:
    continuity = previous.stage
    return CPScaleStepContinuity(CPScaleStageContinuity(result.projection, result.configuration,
        tuple(result.voice.action_results) if result.voice else continuity.previous_voice_action_results,
        tuple(result.control_plane.action_results),
        result.projection.topology if decision.capture_serial_core else continuity.verified_serial_topology,
        result.manifest if decision.capture_serial_core else continuity.verified_serial_manifest,
        result.workspace), baseline)
