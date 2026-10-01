"""Boundary contracts of one governed server-service qualification invocation.

The injected boundaries, the typed product contract a stage is composed
with, the campaign authority that may waive one repository rule, and the
result an adapter receives. None of them depends on a workflow.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ...domain.enterprise.models.capabilities import DeviceCapabilities
from ...domain.enterprise.models.configuration import ConfigurationPlan
from ...domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from ...domain.enterprise.models.deployment import DeploymentManifest
from ...domain.enterprise.models.service_entry import ServiceStageResult
from ...domain.enterprise.models.service_plan import (
    ServiceCapabilityRecords,
    ServicePlan,
)
from ...domain.enterprise.models.service_qualification import (
    Q3_FL_STAGES,
    Q3_NATIVE_STAGES,
    SP1_ROUTED_STAGES,
    SP2_STAGES,
    DiagnosticLifecycleObservation,
    ExecutionMode,
    QualificationOutcome,
    QualificationRecord,
    QualificationRefusal,
    QualificationRequest,
    ReleaseRecord,
    RepositoryIdentity,
    StageDefinition,
    stage_definition,
)
from ...domain.enterprise.services.dhcp_native_default_lifecycle import (
    AdmittedNativeDefaultTransition,
)
from ...domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from ..ports.service_qualification import (
    BuildReader,
    OpenedTransport,
    QualificationRecordPort,
)
from ..use_cases.apply_configuration import ConfigurationRuntime
from ..use_cases.apply_enterprise_services import (
    ServiceInvocationBinding,
    ServiceStageRuntimes,
)
from ..use_cases.apply_services import ServiceRuntime
from ..use_cases.deploy_enterprise_topology import PhysicalTopologyRuntime
from ..use_cases.server_pt_campaign import (
    DHCP_AUTONOMY_CAMPAIGN,
    DHCP_FASTLOOP_CAMPAIGN,
    SP1_ROUTED_CAMPAIGN,
    SP2_CAMPAIGN,
)
from .ledgered_transport import LedgeredTransport

SendAndWait = Callable[[str, float], str | None]
MAX_DETAIL = 240


def bounded(value: object) -> str:
    """Reduce one value to a bounded single-line diagnostic."""
    return " ".join(str(value or "").split())[:MAX_DETAIL]


@dataclass(frozen=True)
class IsolationObservation:
    """What the process-isolation preflight established."""

    isolated: bool
    state: str
    detail: str = ""


@dataclass(frozen=True)
class RuntimeIdentity:
    """The interpreter and package origin of this process."""

    python_executable: str
    package_file: str


@dataclass(frozen=True)
class Q3ProductContract:
    """The real privately-capable product plans bound to the exact Q3 fixture."""

    topology: TopologyPlan
    manifest: DeploymentManifest
    inventory: tuple[RuntimeConfigurationTarget, ...]
    configuration_plan: ConfigurationPlan
    service_plan: ServicePlan
    device_capabilities: dict[str, DeviceCapabilities]
    service_capabilities: ServiceCapabilityRecords
    intent_json: str = ""
    #: Device evidence the product must be composed with instead of the
    #: default catalog, or None for the default. Only an SP-1 contract whose
    #: build lacks measured static-route support sets it, to candidate
    #: evidence the product record then names.
    device_capability_catalog: Any = None
    #: The exact candidate evidence entries that catalog adds (build, model,
    #: capability, status, source and label), recorded by the stage so an
    #: injected override is reviewable; empty with the default catalog.
    device_capability_evidence: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class QualificationBoundaries:
    """Every external boundary one invocation reaches, injected.

    The production composition lives in the CLI adapter. A simulation replaces
    only these boundaries and must say so in `execution_mode`; its records can
    never serve as promotion evidence.
    """

    execution_mode: ExecutionMode
    isolation: Callable[[], IsolationObservation]
    runtime_identity: Callable[[], RuntimeIdentity]
    repository: Callable[[], RepositoryIdentity]
    record_store: QualificationRecordPort
    open_transport: Callable[[str], OpenedTransport]
    close_transport: Callable[[OpenedTransport], None]
    fixture_plans: Callable[
        [StageDefinition], tuple[tuple[DevicePlan, ...], tuple[LinkPlan, ...]]
    ]
    build_reader: Callable[[SendAndWait], BuildReader]
    physical_runtime: Callable[[SendAndWait], PhysicalTopologyRuntime]
    probes: Callable[[LedgeredTransport, str, str], Any]
    configuration_runtime: Callable[[LedgeredTransport], ConfigurationRuntime]
    service_runtime: Callable[[LedgeredTransport], ServiceRuntime]
    clock: Callable[[], float]
    sleep: Callable[[float], None]
    now: Callable[[], datetime]
    new_run_id: Callable[[datetime], str]
    new_nonce: Callable[[], str]
    q3_product_contract: Callable[[str, str], Q3ProductContract] | None = None
    q3_required_build: str = ""
    settle_seconds: float = 2.0
    #: Only the two diagnostic stages compose these. `forwarding_probe` is the
    #: existing bind-before-ping executor bound to this invocation's ledger,
    #: and `diagnostic_service_runtime` is the product web reader with the
    #: explicit inspection schedule, the late read and the ledger's own
    #: allowance reader. A stage that needs one and does not have it refuses
    #: before contact rather than running a narrower experiment.
    forwarding_probe: Callable[[LedgeredTransport], Any] | None = None
    diagnostic_service_runtime: (
        Callable[[LedgeredTransport, Callable[[], tuple[int, float]]], ServiceRuntime]
        | None
    ) = None
    #: Read-only local process/mailbox identity for executable diagnostics.
    #: It runs before a transport is constructed, launches nothing and deletes
    #: nothing. The workspace gate after contact still proves the active
    #: document is disposable before the first effect.
    diagnostic_lifecycle: (
        Callable[[float | None], DiagnosticLifecycleObservation] | None
    ) = None
    #: Cross-checkout exclusion for one campaign writer, taken in the shared
    #: mailbox scope rather than in this checkout's record directory, and held
    #: from admission through finalization. Two worktrees cannot exclude each
    #: other through record directories they do not share, so a diagnostic
    #: stage without a coordinator refuses before contact.
    campaign_coordinator: Any | None = None
    #: The Q3-FL composition. `dhcp_product_contract` composes the real E4/E5/
    #: E6 plans for an intended pool of the stage's capacity; the reviewed
    #: native-default transitions arrive from the catalog through composition,
    #: keyed by the observed build, with the name of the one intervention the
    #: reviewed record brackets. None of them is a domain constant.
    dhcp_product_contract: Callable[[str, str, int], Q3ProductContract] | None = None
    native_product_contract: Callable[[str, str], Q3ProductContract] | None = None
    native_product_runtimes: (
        Callable[
            [LedgeredTransport, tuple[RuntimeConfigurationTarget, ...]],
            ServiceStageRuntimes,
        ]
        | None
    ) = None
    native_product_import_preflight: Callable[[], Any] | None = None
    native_product_record_store_factory: Callable[[], Any] | None = None
    native_product_endpoint_observer: Callable[[LedgeredTransport], Any] | None = None
    native_public_product_entry: (
        Callable[
            [
                LedgeredTransport,
                Callable[[], ServiceInvocationBinding],
                DeploymentManifest,
                str,
                str,
                str,
            ],
            ServiceStageResult,
        ]
        | None
    ) = None
    native_default_transitions: (
        Callable[[str], tuple[AdmittedNativeDefaultTransition, ...]] | None
    ) = None
    #: SP-1: the routed contract composed for a stage's selected clients, and
    #: the registered four-input product tool it always runs through. Its
    #: runtimes, import preflight, record store and endpoint observer are the
    #: native product ones above; nothing about them is SP-1 specific.
    sp2_remote_relay_contract: Callable[[str, str], Q3ProductContract] | None = None
    sp2_mixed_product_contract: Callable[[str, str], Q3ProductContract] | None = None
    sp2_capacity_product_contract: Callable[[str, str], Q3ProductContract] | None = None
    sp1_product_contract: (
        Callable[[str, str, tuple[str, ...]], Q3ProductContract] | None
    ) = None
    sp1_public_product_entry: (
        Callable[
            [
                LedgeredTransport,
                Callable[[], ServiceInvocationBinding],
                DeploymentManifest,
                str,
                str,
                str,
            ],
            ServiceStageResult,
        ]
        | None
    ) = None
    reviewed_native_default_intervention: str = ""
    #: Set only by a validated experimental campaign composition. See
    #: `CampaignQualificationAuthority`.
    campaign_source_authority: CampaignQualificationAuthority | None = None


@dataclass(frozen=True)
class CampaignQualificationAuthority:
    """Validated campaign permission for one qualification attempt.

    Only the qualification CLI's campaign composition constructs this, after
    it validated the campaign's charter digest, the open episode, that
    episode's exact HEAD and tree, the attempt's launch record and the
    ledger admission of this qualification phase. It waives exactly one
    rule, that the executed HEAD be published as its upstream, and only for
    the attempt, authorization, HEAD and tree it names. It also carries the
    creation identity of the process the launch record pinned, which the
    local preflight must then observe.
    """

    campaign_id: str
    episode: int
    #: The ledger record the composition wrote before contact. It must be
    #: the qualification admission of exactly this episode and attempt.
    admission_record: str
    attempt_id: str
    authorization_id: str
    sha: str
    tree: str
    process_incarnation: str

    def permits(
        self, request: QualificationRequest, repository: RepositoryIdentity
    ) -> bool:
        """Whether this authority is for exactly this request and checkout."""
        authorization = request.authorization
        definition = stage_definition(request.stage)
        return bool(
            authorization is not None
            and definition is not None
            and (
                (
                    definition.stage in Q3_FL_STAGES
                    and self.campaign_id == DHCP_FASTLOOP_CAMPAIGN.campaign_id
                )
                or (
                    definition.stage in Q3_NATIVE_STAGES
                    and self.campaign_id == DHCP_AUTONOMY_CAMPAIGN.campaign_id
                )
                or (
                    definition.stage in SP1_ROUTED_STAGES
                    and self.campaign_id == SP1_ROUTED_CAMPAIGN.campaign_id
                )
                or (
                    definition.stage in SP2_STAGES
                    and self.campaign_id == SP2_CAMPAIGN.campaign_id
                )
            )
            and self.episode >= 1
            and self.admission_record
            == f"episode-{self.episode:04d}-{self.attempt_id}-qualification-admission"
            and self.process_incarnation
            and (
                self.attempt_id,
                self.authorization_id,
                self.sha,
                self.tree,
            )
            == (
                authorization.attempt_id,
                authorization.authorization_id,
                request.expected_head,
                authorization.tree,
            )
            and (repository.head, repository.tree) == (self.sha, self.tree)
        )


@dataclass
class QualificationResult:
    """What one invocation returns to its adapter."""

    outcome: QualificationOutcome
    refusals: list[QualificationRefusal] = field(default_factory=list)
    record: QualificationRecord | None = None
    record_path: str = ""
    claim_release: ReleaseRecord | None = None

    @property
    def exit_code(self) -> int:
        """Return the adapter exit code: 0 completed, 1 stopped, 2 refused."""
        return {
            QualificationOutcome.COMPLETED: 0,
            QualificationOutcome.STOPPED: 1,
            QualificationOutcome.REFUSED: 2,
        }[self.outcome]

    def compact_summary(self) -> dict[str, Any]:
        """Return the JSON-ready summary an operator sees."""
        summary: dict[str, Any] = {
            "outcome": self.outcome.value,
            "refusals": [item.model_dump(mode="json") for item in self.refusals],
            "record_path": self.record_path,
        }
        if self.claim_release is not None:
            summary["claim_release"] = self.claim_release.model_dump(mode="json")
        record = self.record
        if record is not None:
            summary.update(
                {
                    "run_id": record.run_id,
                    "stage": record.stage.value,
                    "execution_mode": record.execution_mode.value,
                    "executed_sha": record.source.executed_sha,
                    "channel": record.transport.channel,
                    "observed_build": record.environment.observed_build,
                    "operations_used": record.budget.used_operations,
                    "measurements": [
                        {
                            "id": item.experiment_id,
                            "status": item.status.value,
                            "conclusion": item.conclusion.value,
                        }
                        for item in record.measurements
                    ],
                    "primary_failure": record.primary_failure,
                    "secondary_failures": record.secondary_failures,
                    "restoration_proven": record.restoration_proven,
                    "engine_residue": record.engine_residue,
                    "coordination_residue": record.coordination_residue,
                    "dirty_state": record.dirty_state.value,
                    "persisted_step": record.persisted_step,
                    "persist_error": record.persist_error,
                }
            )
        return summary


class QualificationCancelled(KeyboardInterrupt):
    """A controlled cancellation plus any pre-record claim-release fact."""

    def __init__(
        self,
        original: KeyboardInterrupt,
        claim_release: ReleaseRecord | None,
    ) -> None:
        """Preserve the cancellation while carrying local finalization output."""
        super().__init__(*original.args)
        self.claim_release = claim_release


def refused_result(
    refusals: Sequence[QualificationRefusal],
    record: QualificationRecord | None = None,
    record_path: str = "",
    claim_release: ReleaseRecord | None = None,
) -> QualificationResult:
    """Return a refusal result with its record and claim-release fact, if any."""
    return QualificationResult(
        outcome=QualificationOutcome.REFUSED,
        refusals=list(refusals),
        record=record,
        record_path=record_path,
        claim_release=claim_release,
    )
