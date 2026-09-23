"""Run the existing E4 and selected E5 use cases for one disposable campus."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...domain.enterprise.models.configuration import VerificationKind
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationRuntimeContext,
    FieldVerificationStatus,
)
from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from ...domain.enterprise.models.intent import EnterpriseIntent
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentResult,
    PhysicalDeploymentStatus,
)
from ...domain.models.plans import TopologyPlan
from ...infrastructure.catalog.enterprise_capabilities import (
    EnterpriseCapabilityAdapter,
)
from ...infrastructure.catalog.measured_port_inventories import (
    backend_verified_port_inventory,
)
from ...infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
    ManifestPersistenceError,
)
from ...infrastructure.persistence.server_pt_commissioning_store import (
    ServerPtCommissioningStore,
)
from ...shared.utils import safe_name_component
from .apply_configuration import ConfigurationApplicator, ConfigurationRuntime
from .compose_enterprise_reference import compose_enterprise_reference
from .deploy_enterprise_topology import (
    EnterprisePhysicalTopologyDeployer,
    PhysicalTopologyRuntime,
    disposable_workspace_error,
)
from .prepare_server_pt_commissioning import (
    SERVER_PT_BUILD,
    _setup_action_ids,
    prepare_server_pt_commissioning,
)


@dataclass(frozen=True)
class ServerPtSetupResult:
    """What the setup phases actually observed and where they stopped."""

    reason: str = ""
    physical: PhysicalDeploymentResult | None = None
    configuration: ConfigurationApplicationResult | None = None
    manifest_path: str = ""

    @property
    def ready(self) -> bool:
        """Whether exact E4 and the selected L2 structure were established."""
        return (
            not self.reason
            and self.physical is not None
            and self.configuration is not None
        )


def _structural_findings(
    plan, result: ConfigurationApplicationResult, selected: set[str]
) -> list[str]:
    """Classify L2 structure from retained fields, leaving STP to acceptance."""
    found: list[str] = []
    if set(result.mutation_action_ids) != selected or result.retained_action_ids:
        found.append("setup_action_accounting_mismatch")
    actions = {item.action_id: item for item in result.action_results}
    for action_id in sorted(selected):
        item = actions.get(action_id)
        if item is None or item.status not in {
            ActionExecutionStatus.APPLIED,
            ActionExecutionStatus.VERIFIED,
        }:
            found.append(f"setup_action_not_applied:{action_id}")
    verified = {item.expectation_id: item for item in result.verification_results}
    for expectation in plan.verification_expectations:
        if expectation.action_id not in selected:
            continue
        row = verified.get(expectation.id)
        required = (
            {"vlan_id"}
            if expectation.kind is VerificationKind.VLAN
            else {"interface", "status", "allowed_vlans", "active_vlans"}
            if expectation.kind is VerificationKind.TRUNK
            else set()
        )
        if (
            not required
            or row is None
            or not row.fresh_evidence
            or not row.evidence_method
        ):
            found.append(f"setup_readback_unavailable:{expectation.id}")
            continue
        if any(
            row.fields.get(field) is not FieldVerificationStatus.VERIFIED
            for field in required
        ):
            found.append(f"setup_structure_not_verified:{expectation.id}")
        if any(
            status is not FieldVerificationStatus.VERIFIED
            for field, status in row.fields.items()
            if field != "forwarding_vlans"
        ):
            found.append(f"setup_readback_contradiction:{expectation.id}")
    return found


def run_server_pt_setup(
    attempt_id: str,
    *,
    deployment_id: str,
    store: ServerPtCommissioningStore,
    physical_runtime: PhysicalTopologyRuntime,
    configuration_runtime: ConfigurationRuntime,
    environment_fingerprint: EnvironmentFingerprint,
    admission: Callable[[], tuple[str, ...]],
    port_inventory=backend_verified_port_inventory,
    capability_catalog: EnterpriseCapabilityAdapter | None = None,
) -> ServerPtSetupResult:
    """Consume one stored full plan; persist E4 before any E5 effect.

    The caller binds each external runtime to an independently governed,
    bounded file channel. ``admission`` checks source, receiver, process and
    phase authority before the first effect and again before E5. The runtime
    wrapper must repeat receiver and allowance checks before every dispatch.
    """
    if not deployment_id or safe_name_component(deployment_id, "") != deployment_id:
        return ServerPtSetupResult(reason="unsafe_deployment_id")
    if (
        environment_fingerprint.backend != "packet_tracer"
        or environment_fingerprint.backend_version != SERVER_PT_BUILD
        or environment_fingerprint.bridge_transport != "file"
        or environment_fingerprint.runtime_mode != "logical-workspace"
    ):
        return ServerPtSetupResult(reason="setup_environment_mismatch")
    try:
        bundle = store.load_bundle(attempt_id)
        topology = TopologyPlan.model_validate_json(bundle.topology_json)
        expected = prepare_server_pt_commissioning(
            bundle.client_count,
            bundle.marker,
            sites=bundle.site_count,
            build=bundle.build,
        )
        if bundle != expected:
            raise ValueError("sealed bundle differs from the compiled campaign recipe")
        findings = admission()
    except (OSError, ValueError) as exc:
        return ServerPtSetupResult(
            reason=f"setup_input_unavailable:{type(exc).__name__}"
        )
    if findings:
        return ServerPtSetupResult(reason="setup_admission:" + ",".join(findings))
    try:
        baseline = physical_runtime.observe_workspace()
    except Exception as exc:
        return ServerPtSetupResult(reason=f"baseline_unobservable:{type(exc).__name__}")
    try:
        store.save_baseline(attempt_id, baseline)
    except (OSError, ValueError) as exc:
        return ServerPtSetupResult(
            reason=f"baseline_persistence_failed:{type(exc).__name__}"
        )
    workspace_error = disposable_workspace_error(baseline)
    if workspace_error:
        return ServerPtSetupResult(reason=workspace_error)
    physical = EnterprisePhysicalTopologyDeployer(
        physical_runtime, port_inventory=port_inventory
    ).deploy(
        topology,
        environment_fingerprint=environment_fingerprint,
        deployment_id=deployment_id,
        require_empty_workspace=True,
    )
    try:
        store.save_e4(attempt_id, physical)
    except (OSError, ValueError) as exc:
        return ServerPtSetupResult(
            reason=f"e4_persistence_failed:{type(exc).__name__}", physical=physical
        )
    if (
        physical.status is not PhysicalDeploymentStatus.VERIFIED
        or physical.manifest is None
    ):
        return ServerPtSetupResult(
            reason="e4_not_verified:" + ";".join(physical.errors), physical=physical
        )
    manifest_store = DeploymentManifestStore(store.root / "data" / "deployments")
    try:
        manifest_path = manifest_store.save_verified(physical.manifest)
        reloaded = manifest_store.latest_by_deployment_id(deployment_id)
    except (OSError, ValueError, ManifestPersistenceError) as exc:
        return ServerPtSetupResult(
            reason=f"manifest_persistence_failed:{type(exc).__name__}",
            physical=physical,
        )
    if reloaded != physical.manifest:
        return ServerPtSetupResult(reason="manifest_reload_mismatch", physical=physical)
    manifest_path_text = str(manifest_path)
    intent = EnterpriseIntent.model_validate_json(bundle.intent_json)
    composed = compose_enterprise_reference(
        intent,
        packet_tracer_version=bundle.build,
        deployment_manifest=reloaded,
        services=True,
        capability_catalog=capability_catalog,
    )
    if (
        not composed.valid
        or composed.configuration is None
        or composed.topology is None
        or composed.topology.physical_identity_hash != bundle.physical_topology_hash
        or composed.configuration.semantic_hash != bundle.configuration_semantic_hash
    ):
        return ServerPtSetupResult(
            reason="e5_compilation_identity_mismatch",
            physical=physical,
            manifest_path=manifest_path_text,
        )
    plan = composed.configuration
    selected = set(bundle.setup_action_ids)
    if tuple(bundle.setup_action_ids) != _setup_action_ids(plan):
        return ServerPtSetupResult(
            reason="setup_action_selection_changed",
            physical=physical,
            manifest_path=manifest_path_text,
        )
    try:
        store.save_configuration_plan(attempt_id, plan)
    except (OSError, ValueError) as exc:
        return ServerPtSetupResult(
            reason=f"e5_plan_persistence_failed:{type(exc).__name__}",
            physical=physical,
            manifest_path=manifest_path_text,
        )
    findings = admission()
    if findings:
        return ServerPtSetupResult(
            reason="setup_admission:" + ",".join(findings),
            physical=physical,
            manifest_path=manifest_path_text,
        )
    configuration = ConfigurationApplicator(configuration_runtime).apply(
        plan,
        actual_source_topology_hash=bundle.physical_topology_hash,
        capabilities=composed.capabilities,
        runtime_context=ConfigurationRuntimeContext(
            environment_fingerprint=environment_fingerprint
        ),
        deployment_manifest=reloaded,
        mutation_action_ids=bundle.setup_action_ids,
        excluded_action_ids=[
            action.id for action in plan.actions if action.id not in selected
        ],
    )
    try:
        store.save_e5(attempt_id, configuration)
    except (OSError, ValueError) as exc:
        return ServerPtSetupResult(
            reason=f"e5_persistence_failed:{type(exc).__name__}",
            physical=physical,
            configuration=configuration,
            manifest_path=manifest_path_text,
        )
    structural = _structural_findings(plan, configuration, selected)
    return ServerPtSetupResult(
        reason=";".join(structural),
        physical=physical,
        configuration=configuration,
        manifest_path=manifest_path_text,
    )
