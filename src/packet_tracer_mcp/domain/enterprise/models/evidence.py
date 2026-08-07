"""Shared E9.5 evidence and readiness vocabulary.

The axes in this module are deliberately orthogonal.  A backend feature may be
supported while its current state is unobservable, and a failed behavioral
verification does not imply that the feature itself is unsupported.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VerificationMethod(str, Enum):
    DIRECT_STATE = "direct_state"
    STRUCTURED_API = "structured_api"
    OPERATIONAL_CLI = "operational_cli"
    BEHAVIORAL = "behavioral"
    EVENT_STREAM = "event_stream"
    INFERRED = "inferred"
    NONE = "none"


class EvidenceStrength(str, Enum):
    """Relevance to the particular claim, not a universal method ranking."""

    CLAIM_DIRECT = "claim_direct"
    CLAIM_SUPPORTING = "claim_supporting"
    INFERRED = "inferred"
    NONE = "none"


class EvidenceFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class SupportStatus(str, Enum):
    UNKNOWN = "unknown"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    PARTIAL = "partial"


class ObservationStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    OBSERVED = "observed"
    UNOBSERVABLE = "unobservable"
    PROBE_FAILED = "probe_failed"
    SKIPPED = "skipped"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILED = "failed"
    CONFLICTED = "conflicted"


class ReadinessStatus(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    UNOBSERVABLE = "unobservable"
    BLOCKED = "blocked"


class EvidenceRecord(BaseModel):
    id: str
    subject: str
    claim: str
    method: VerificationMethod
    strength: EvidenceStrength = EvidenceStrength.NONE
    source: str = ""
    freshness: EvidenceFreshness = EvidenceFreshness.UNKNOWN
    backend: str = ""
    backend_version: str = ""
    environment_fingerprint: str = ""
    probe_fingerprint: str = ""
    observed_value: Any = None
    support_status: SupportStatus = SupportStatus.UNKNOWN
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    observation_status: ObservationStatus = ObservationStatus.NOT_ATTEMPTED
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    limitations: list[str] = Field(default_factory=list)
    raw_reference: str = ""

    @property
    def verifies_claim(self) -> bool:
        return (
            self.freshness is EvidenceFreshness.FRESH
            and self.observation_status is ObservationStatus.OBSERVED
            and self.verification_status is VerificationStatus.VERIFIED
        )

    @property
    def classification(self) -> str:
        if self.support_status is SupportStatus.UNSUPPORTED:
            return "unsupported"
        if self.observation_status is ObservationStatus.UNOBSERVABLE:
            return "unobservable"
        if self.verification_status is VerificationStatus.FAILED:
            return "failed"
        if (
            self.support_status is SupportStatus.UNKNOWN
            or self.observation_status is ObservationStatus.NOT_ATTEMPTED
        ):
            return "unknown"
        if self.verifies_claim:
            return "verified"
        return "unverified"

    def compact_summary(self) -> dict[str, object]:
        return {
            "id": self.id,
            "subject": self.subject,
            "claim": self.claim,
            "method": self.method.value,
            "strength": self.strength.value,
            "freshness": self.freshness.value,
            "support_status": self.support_status.value,
            "observation_status": self.observation_status.value,
            "verification_status": self.verification_status.value,
            "observed_value": _canonical_value(self.observed_value),
            "backend": self.backend,
            "backend_version": self.backend_version,
            "environment_fingerprint": self.environment_fingerprint,
            "probe_fingerprint": self.probe_fingerprint,
            "limitations": list(self.limitations),
            "raw_reference": self.raw_reference,
        }


class CapabilityReadiness(BaseModel):
    capability: str
    compile: ReadinessStatus = ReadinessStatus.UNKNOWN
    apply: ReadinessStatus = ReadinessStatus.UNKNOWN
    verify: ReadinessStatus = ReadinessStatus.UNKNOWN
    reasons: dict[str, list[str]] = Field(default_factory=dict)
    evidence_ids: dict[str, list[str]] = Field(default_factory=dict)


def evidence_from_legacy_result(
    *,
    identifier: str,
    subject: str,
    claim: str,
    status: Any,
    evidence_method: str = "",
    fresh_evidence: bool = False,
    observed_value: Any = None,
    backend: str = "",
    backend_version: str = "",
    environment_fingerprint: str = "",
    limitations: list[str] | None = None,
) -> EvidenceRecord:
    """Lossless-enough adapter while E5-E9 legacy result fields remain public."""
    status_value = status.value if isinstance(status, Enum) else str(status)
    observation = {
        "verified": ObservationStatus.OBSERVED,
        "failed": ObservationStatus.OBSERVED,
        "partial": ObservationStatus.OBSERVED,
        "unobservable": ObservationStatus.UNOBSERVABLE,
        "dependency_blocked": ObservationStatus.SKIPPED,
        "skipped": ObservationStatus.SKIPPED,
    }.get(status_value, ObservationStatus.NOT_ATTEMPTED)
    verification = {
        "verified": VerificationStatus.VERIFIED,
        "failed": VerificationStatus.FAILED,
    }.get(status_value, VerificationStatus.UNVERIFIED)
    support = (
        SupportStatus.SUPPORTED
        if status_value == "verified"
        else SupportStatus.PARTIAL
        if status_value == "partial"
        else SupportStatus.UNKNOWN
    )
    method, method_limitation = _legacy_method(evidence_method)
    merged_limitations = list(limitations or [])
    if method_limitation:
        merged_limitations.append(method_limitation)
    return EvidenceRecord(
        id=identifier,
        subject=subject,
        claim=claim,
        method=method,
        strength=(
            EvidenceStrength.CLAIM_DIRECT
            if method in {
                VerificationMethod.DIRECT_STATE,
                VerificationMethod.STRUCTURED_API,
                VerificationMethod.OPERATIONAL_CLI,
                VerificationMethod.BEHAVIORAL,
                VerificationMethod.EVENT_STREAM,
            }
            else EvidenceStrength.INFERRED
            if method is VerificationMethod.INFERRED
            else EvidenceStrength.NONE
        ),
        source=evidence_method,
        freshness=(
            EvidenceFreshness.FRESH if fresh_evidence else EvidenceFreshness.UNKNOWN
        ),
        backend=backend,
        backend_version=backend_version,
        environment_fingerprint=environment_fingerprint,
        observed_value=observed_value,
        support_status=support,
        observation_status=observation,
        verification_status=verification,
        limitations=sorted(set(merged_limitations)),
    )


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def _legacy_method(value: str) -> tuple[VerificationMethod, str]:
    normalized = value.casefold().strip()
    if not normalized:
        return VerificationMethod.NONE, "Legacy result did not identify an evidence method."
    if any(token in normalized for token in ("ping", "dns", "http", "call", "behavior")):
        return VerificationMethod.BEHAVIORAL, ""
    if any(token in normalized for token in ("terminal", "ios", "cli", "show")):
        return VerificationMethod.OPERATIONAL_CLI, ""
    if any(token in normalized for token in ("structured", "getter", "api")):
        return VerificationMethod.STRUCTURED_API, ""
    if "event" in normalized:
        return VerificationMethod.EVENT_STREAM, ""
    if "direct" in normalized or "readback" in normalized:
        return VerificationMethod.DIRECT_STATE, ""
    return VerificationMethod.NONE, f"Unmapped legacy evidence method: {value}."
