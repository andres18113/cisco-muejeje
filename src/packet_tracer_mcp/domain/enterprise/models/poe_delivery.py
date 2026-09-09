"""Typed facts for a governed powered-device delivery qualification.

The models in this module are deliberately passive.  Coherence, identity and
claim policy belong to ``domain.enterprise.rules.poe_delivery``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .discovery import (
    CapabilityProbeResult,
    CleanupStatus,
    LiveSessionSafetyAdmissionEvidence,
    ProbeExecutionStatus,
)
from .evidence import ObservationStatus, VerificationStatus


class PoEDeliveryArmState(str, Enum):
    POWERED = "powered"
    NOT_POWERED = "not_powered"
    UNOBSERVABLE = "unobservable"


class PoEDeliveryBindingRequest(BaseModel):
    candidate_port: str
    comparison_port: str
    endpoint_model: str
    endpoint_port: str


class PoEDeliveryQualificationRequest(BaseModel):
    packet_tracer_build: str
    candidate_model: str
    comparison_model: str
    bindings: list[PoEDeliveryBindingRequest] = Field(default_factory=list)


class PoEDeliveryDeviceIdentity(BaseModel):
    name: str
    model: str
    observed_ports: list[str] = Field(default_factory=list)


class PoEDeliveryLinkEndpoint(BaseModel):
    device_name: str
    device_model: str
    port: str


class PoEDeliveryLinkIdentity(BaseModel):
    first: PoEDeliveryLinkEndpoint
    second: PoEDeliveryLinkEndpoint


class PoEDeliveryBindingFixtureIdentity(BaseModel):
    request: PoEDeliveryBindingRequest
    candidate_switch: PoEDeliveryDeviceIdentity
    comparison_switch: PoEDeliveryDeviceIdentity
    candidate_endpoint: PoEDeliveryDeviceIdentity
    comparison_endpoint: PoEDeliveryDeviceIdentity
    candidate_link: PoEDeliveryLinkIdentity
    comparison_link: PoEDeliveryLinkIdentity


class PoEDeliveryFixtureIdentity(BaseModel):
    candidate_switch: PoEDeliveryDeviceIdentity
    comparison_switch: PoEDeliveryDeviceIdentity
    bindings: list[PoEDeliveryBindingFixtureIdentity] = Field(default_factory=list)


class PoEDeliveryArmObservation(BaseModel):
    switch_name: str
    switch_model: str
    switch_port: str
    endpoint_name: str
    endpoint_model: str
    endpoint_port: str
    state: PoEDeliveryArmState = PoEDeliveryArmState.UNOBSERVABLE
    visible_indicator: str = ""
    switch_ready: bool = False
    link_ready: bool = False
    endpoint_settled: bool = False


class PoEDeliveryBindingObservation(BaseModel):
    binding: PoEDeliveryBindingRequest
    candidate: PoEDeliveryArmObservation
    comparison: PoEDeliveryArmObservation


class PoEDeliveryManualObservation(BaseModel):
    observer_id: str = ""
    observed_at: datetime
    method: str = ""
    simultaneous: bool = False
    bindings: list[PoEDeliveryBindingObservation] = Field(default_factory=list)


class PoEDeliveryQualificationResult(BaseModel):
    execution_status: ProbeExecutionStatus
    observation_status: ObservationStatus
    verification_status: VerificationStatus
    capability_result: CapabilityProbeResult
    cleanup_status: CleanupStatus
    initial_inventory_fingerprint: str = ""
    final_inventory_fingerprint: str = ""
    inventory_restored: bool | None = None
    live_session_safety: LiveSessionSafetyAdmissionEvidence
    attempted_identities: list[str] = Field(default_factory=list)
    created_identities: list[str] = Field(default_factory=list)
    deleted_identities: list[str] = Field(default_factory=list)
    cleanup_failed: list[str] = Field(default_factory=list)
    fixture: PoEDeliveryFixtureIdentity | None = None
    observation: PoEDeliveryManualObservation | None = None
    failure_reason: str = ""
    runtime_snapshot_path: str | None = None
