"""Validation of reusable E7 call-observability capability evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from ..models.capabilities import CapabilityEvidence, CapabilityStatus, EvidenceSource
from ..models.discovery import CapabilityProbeResult, ProbeExecutionStatus
from ..models.voice_runtime import PhoneExecutionMethod
from ..rules.live_session_safety import validate_live_session_positive_admission


CALL_OBSERVABILITY_CAPABILITY = "supports_call_observability"
CALL_OBSERVABILITY_SCHEMA = "call-observability-qualification-v1"
CALL_OBSERVABILITY_PROVIDER_ID = "packet-tracer-native-ui-mailbox-v1"
CALL_OBSERVABILITY_EXPECTATION_RESULTS = ("established", "not_connected")
CALL_OBSERVABILITY_CALL_CONTROL_MODELS = ("2811",)
CALL_OBSERVABILITY_PHONE_MODELS = ("7960",)

_DIMENSION_KEYS = frozenset({
    "schema",
    "provider_id",
    "execution_method",
    "driver_source_sha256",
    "call_control_models",
    "phone_models",
    "expectation_results",
    "exact_identity",
    "fresh_evidence",
    "teardown_verified",
    "cleanup_empty_observations",
    "realtime_restored",
    "evidence_path",
    "evidence_sha256",
    "executed_sha",
    "run_identity",
})


@dataclass(frozen=True)
class QualifiedCallObservability:
    provider_id: str
    execution_method: PhoneExecutionMethod
    packet_tracer_version: str
    driver_source_sha256: str
    call_control_models: tuple[str, ...]
    phone_models: tuple[str, ...]
    expectation_results: tuple[str, ...]
    evidence_path: str
    evidence_sha256: str
    executed_sha: str
    run_identity: str


def decode_call_observability_probe(
    result: CapabilityProbeResult,
    *,
    packet_tracer_version: str,
    driver_source_sha256: str,
) -> QualifiedCallObservability | None:
    """Decode one LIVE result only when its source and cleanup are admissible."""

    authority = _decode(
        capability=result.capability,
        status=result.status,
        source=result.evidence_source,
        verified=result.verified,
        evidence_version=result.packet_tracer_version,
        dimensions=result.dimensions,
        packet_tracer_version=packet_tracer_version,
        driver_source_sha256=driver_source_sha256,
    )
    context = result.context
    if authority is None or context is None or context.live_session_safety is None:
        return None
    if (
        result.execution_status is not ProbeExecutionStatus.VERIFIED
        or result.model not in authority.call_control_models
        or context.device_model != result.model
        or context.backend_version != packet_tracer_version
        or context.execution_status is not ProbeExecutionStatus.VERIFIED
        or context.result_status is not CapabilityStatus.SUPPORTED
        or not context.reusable
        or not validate_live_session_positive_admission(
            context.live_session_safety,
        ).is_valid
    ):
        return None
    safety = context.live_session_safety
    if (
        getattr(safety, "source_head_before", "") != authority.executed_sha
        or getattr(safety, "source_head_after", "") != authority.executed_sha
        or result.probe_id != authority.run_identity
    ):
        return None
    return authority


def decode_call_observability_evidence(
    evidence: CapabilityEvidence,
    *,
    packet_tracer_version: str,
) -> QualifiedCallObservability | None:
    """Decode the semantic capability projection consumed by E7 profiles."""

    if evidence.source_detail != (
        "verified-store:" + evidence.dimensions.get("run_identity", "")
    ):
        return None
    return _decode(
        capability=evidence.capability,
        status=evidence.status,
        source=evidence.source,
        verified=evidence.verified,
        evidence_version=evidence.packet_tracer_version,
        dimensions=evidence.dimensions,
        packet_tracer_version=packet_tracer_version,
        driver_source_sha256=evidence.dimensions.get("driver_source_sha256", ""),
    )


def _decode(
    *,
    capability: str,
    status: CapabilityStatus,
    source: EvidenceSource,
    verified: bool,
    evidence_version: str | None,
    dimensions: dict[str, str],
    packet_tracer_version: str,
    driver_source_sha256: str,
) -> QualifiedCallObservability | None:
    if (
        capability != CALL_OBSERVABILITY_CAPABILITY
        or status is not CapabilityStatus.SUPPORTED
        or source not in {
            EvidenceSource.CONTROLLED_PROBE,
            EvidenceSource.MANUAL_VERIFICATION,
        }
        or verified is not True
        or not packet_tracer_version
        or evidence_version != packet_tracer_version
        or frozenset(dimensions) != _DIMENSION_KEYS
        or dimensions.get("schema") != CALL_OBSERVABILITY_SCHEMA
        or dimensions.get("provider_id") != CALL_OBSERVABILITY_PROVIDER_ID
        or dimensions.get("execution_method")
        != PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI.value
        or dimensions.get("driver_source_sha256") != driver_source_sha256
        or not _is_sha256(driver_source_sha256)
        or dimensions.get("call_control_models")
        != ",".join(CALL_OBSERVABILITY_CALL_CONTROL_MODELS)
        or dimensions.get("phone_models")
        != ",".join(CALL_OBSERVABILITY_PHONE_MODELS)
        or dimensions.get("expectation_results")
        != ",".join(CALL_OBSERVABILITY_EXPECTATION_RESULTS)
        or dimensions.get("exact_identity") != "true"
        or dimensions.get("fresh_evidence") != "true"
        or dimensions.get("teardown_verified") != "true"
        or dimensions.get("cleanup_empty_observations") != "2"
        or dimensions.get("realtime_restored") != "true"
        or not _relative_evidence_path(dimensions.get("evidence_path", ""))
        or not _is_sha256(dimensions.get("evidence_sha256", ""))
        or not _is_git_sha(dimensions.get("executed_sha", ""))
        or not _exact_text(dimensions.get("run_identity", ""))
    ):
        return None
    return QualifiedCallObservability(
        provider_id=dimensions["provider_id"],
        execution_method=PhoneExecutionMethod(dimensions["execution_method"]),
        packet_tracer_version=packet_tracer_version,
        driver_source_sha256=driver_source_sha256,
        call_control_models=CALL_OBSERVABILITY_CALL_CONTROL_MODELS,
        phone_models=CALL_OBSERVABILITY_PHONE_MODELS,
        expectation_results=CALL_OBSERVABILITY_EXPECTATION_RESULTS,
        evidence_path=dimensions["evidence_path"],
        evidence_sha256=dimensions["evidence_sha256"],
        executed_sha=dimensions["executed_sha"],
        run_identity=dimensions["run_identity"],
    )


def _relative_evidence_path(value: str) -> bool:
    if not _exact_text(value) or "\\" in value:
        return False
    path = PurePosixPath(value)
    return bool(not path.is_absolute() and ".." not in path.parts)


def _exact_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _is_sha256(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_git_sha(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )
