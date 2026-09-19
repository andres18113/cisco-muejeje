"""The durable record of one enterprise-services invocation.

Persistence is part of this product, not a save call at the end of it. The
record is written BEFORE the first effect and rewritten at every stage
boundary, so that a run which stops in the middle leaves behind what it had
done rather than nothing at all.

It holds the FULL typed E5 and E6 results, not compact counts. Two reasons,
both of which have bitten this project before:

- retained reuse (R-RET-01) needs the actual rows to decide whether an action
  may be trusted without re-applying it, and a count cannot support that;
- the TD-12 `received_mutation` snapshot, its canonical cause and its separate
  `call_error` are the evidence that a classification was honest. They survive
  the round trip because the whole typed row does.

What the record deliberately does NOT claim: per-action crash recovery. Only
stage boundaries are durable, so an interrupted record says which stage was
last written and nothing about the actions inside it. An interrupted record is
never proof that work did not execute, and it is never auto-resumed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from .configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
)
from .execution import DirtyState
from .service_entry import (
    AdmissionTrace,
    CapabilitySnapshotSummary,
    ClientServiceOutcome,
    E5EffectScope,
    OwnedResourceRelease,
    ServiceEntryOutcome,
    ServiceEntryRefusal,
    ServiceRunStatus,
    ServiceStage,
    StageTransition,
)
from .service_runtime import ServiceApplicationResult


def generate_run_id(now: datetime | None = None) -> str:
    """Generate one sortable, collision-resistant product run identity."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    return f"{moment.strftime('%Y-%m-%dT%H-%M-%SZ')}-{uuid4().hex[:8]}"


class SourceTreeIdentity(BaseModel):
    """The tree that executed the run, and whether it was clean.

    A dirty tree does not invalidate the record; it changes what the record
    proves. A measurement attributed to a SHA whose working files differed from
    it is attributed to something that was never committed.
    """

    sha: str = ""
    dirty: bool = True


class DhcpServiceAuthorityRecord(BaseModel):
    """Canonical Server-PT DHCP authority persisted independently of outcomes."""

    service_id: str
    server_device_id: str
    segment_id: str
    interface: str
    pool_name: str
    client_device_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    expectation_ids: list[str] = Field(default_factory=list)


class ServiceRunRecord(BaseModel):
    """One run, from the identity it bound to the outcome it observed."""

    schema_version: int = 1
    run_id: str
    run_label: str = ""
    created_at: datetime
    completed_at: datetime | None = None

    source_tree: SourceTreeIdentity = Field(default_factory=SourceTreeIdentity)
    packet_tracer_version: str = ""
    transport: str = ""
    channel_fixed_at: datetime | None = None

    #: Empty for an unbound admission record: A3 to A5 can refuse before any
    #: deployment identity has been established, and inventing one so the file
    #: looks complete would be the opposite of what the record is for.
    deployment_id: str = ""
    manifest_hash: str = ""
    physical_topology_hash: str = ""
    configuration_plan_id: str = ""
    configuration_semantic_hash: str = ""
    service_semantic_hash: str = ""
    environment_fingerprint_hash: str = ""
    capability_snapshot: CapabilitySnapshotSummary = Field(
        default_factory=CapabilitySnapshotSummary
    )

    bound: bool = False
    stages: list[StageTransition] = Field(default_factory=list)
    persisted_stage: ServiceStage | None = None
    status: ServiceRunStatus = ServiceRunStatus.REFUSED
    refusal_code: ServiceEntryRefusal = ServiceEntryRefusal.NONE
    blocked_reason: str = ""

    admission: AdmissionTrace = Field(default_factory=AdmissionTrace)
    e5_effect_scope: E5EffectScope = Field(default_factory=E5EffectScope)
    e5_effect_uncertain: bool = False
    configuration_result: ConfigurationApplicationResult | None = None
    foundational_statuses: dict[str, ActionExecutionStatus] = Field(
        default_factory=dict
    )
    service_result: ServiceApplicationResult | None = None
    services: list[ServiceEntryOutcome] = Field(default_factory=list)
    clients: list[ClientServiceOutcome] = Field(default_factory=list)
    selected_clients: list[str] = Field(default_factory=list)
    releases: list[OwnedResourceRelease] = Field(default_factory=list)
    nonces: dict[str, str] = Field(default_factory=dict)
    dhcp_authorities: list[DhcpServiceAuthorityRecord] = Field(default_factory=list)
    dirty_state: DirtyState = DirtyState.CLEAN
    limitations: list[str] = Field(default_factory=list)
    persist_error: str = ""

    @property
    def interrupted(self) -> bool:
        """Whether the run stopped without reaching a terminal stage.

        A record whose last durable stage is not `completed` says the process
        stopped there. It does NOT say the work in that stage did not happen:
        the stage boundary is the durable unit, and everything inside it is
        exactly as uncertain as the run's own facts make it.
        """
        return self.persisted_stage is not ServiceStage.COMPLETED

    def identity_matches(
        self,
        *,
        deployment_id: str,
        manifest_hash: str,
        configuration_semantic_hash: str,
        environment_fingerprint_hash: str,
    ) -> bool:
        """Whether this record describes the exact same bound identity.

        All four must agree, and none may be empty. An empty value on either
        side is an unknown, and two unknowns are not a match; that is how a
        record with no fingerprint could otherwise be reused in an environment
        nobody checked.
        """
        expected = (
            deployment_id,
            manifest_hash,
            configuration_semantic_hash,
            environment_fingerprint_hash,
        )
        if not all(expected):
            return False
        return expected == (
            self.deployment_id,
            self.manifest_hash,
            self.configuration_semantic_hash,
            self.environment_fingerprint_hash,
        )
