"""Read-only cumulative reconciliation for a retained canonical LIVE stage."""

from __future__ import annotations

from typing import Protocol

from ...domain.enterprise.models.configuration_runtime import (
    RuntimeConfigurationTarget,
)
from ...domain.enterprise.models.deployment import (
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    EnvironmentFingerprint,
    build_deployment_manifest,
)
from ...domain.enterprise.models.execution import (
    ApplicationExecutionJournal,
    MutationDisposition,
)
from ...domain.enterprise.models.evidence import (
    EvidenceFreshness,
    EvidenceRecord,
    EvidenceStrength,
    ObservationStatus,
    SupportStatus,
    VerificationMethod,
    VerificationStatus,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentFailureCode,
    PhysicalDeploymentItemResult,
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentResult,
    PhysicalDeploymentStatus,
    PhysicalDeviceObservation,
    PhysicalLinkObservation,
    PhysicalObjectKind,
    PhysicalWorkspaceObservation,
)
from ...domain.models.plans import DevicePlan, LinkPlan, TopologyPlan
from ...infrastructure.catalog.modules import resolve_module
from .qualify_cp_scale_live import canonical_stage_workspace_error


class CanonicalStageObservationRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...

    def observe_device(self, device: DevicePlan) -> PhysicalDeviceObservation: ...

    def observe_link(self, link: LinkPlan) -> PhysicalLinkObservation: ...


def canonical_delta_deployment_error(
    previous_topology: TopologyPlan | None,
    delta_topology: TopologyPlan,
    result: PhysicalDeploymentResult,
) -> str:
    """Require ownership of every new object and NO_OP only for prior anchors."""

    if result.status is not PhysicalDeploymentStatus.VERIFIED:
        return f"Physical delta is {result.status.value}, not VERIFIED."
    if result.physical_topology_hash != delta_topology.physical_identity_hash:
        return "Physical delta result hash does not match the typed delta plan."

    prior_device_ids = {
        item.id or item.name for item in (previous_topology.devices if previous_topology else [])
    }
    expected = {
        (PhysicalObjectKind.DEVICE, item.id or item.name)
        for item in delta_topology.devices
    } | {
        (PhysicalObjectKind.MODULE, f"{item.device}:{item.slot}:{item.module}")
        for item in delta_topology.modules
    } | {
        (
            PhysicalObjectKind.LINK,
            item.id or f"{item.device_a}:{item.port_a}->{item.device_b}:{item.port_b}",
        )
        for item in delta_topology.links
    }
    observed = [(item.target_kind, item.target_id) for item in result.item_results]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        return "Physical delta item inventory did not exactly match the typed delta."

    for item in result.item_results:
        if (
            item.status is not PhysicalDeploymentItemStatus.OBSERVED
            or not item.observed
        ):
            return (
                f"Physical delta {item.target_kind.value} {item.target_id!r} "
                "lacks fresh OBSERVED read-back."
            )
        is_anchor = (
            item.target_kind is PhysicalObjectKind.DEVICE
            and item.target_id in prior_device_ids
        )
        if is_anchor:
            if item.disposition is not MutationDisposition.NO_OP or item.applied:
                return (
                    f"Prior anchor device {item.target_id!r} was not an exact NO_OP."
                )
            continue
        if item.disposition is not MutationDisposition.CHANGED or not item.applied:
            return (
                f"New physical {item.target_kind.value} {item.target_id!r} was "
                f"{item.disposition.value}, not session-owned CHANGED/APPLIED."
            )
    return ""


def _fresh_evidence(
    *,
    identifier: str,
    subject: str,
    claim: str,
    source: str,
    observed_value: object,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    return EvidenceRecord(
        id=identifier,
        subject=subject,
        claim=claim,
        method=VerificationMethod.STRUCTURED_API,
        strength=EvidenceStrength.CLAIM_DIRECT,
        source=source,
        freshness=EvidenceFreshness.FRESH,
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value=observed_value,
        support_status=SupportStatus.SUPPORTED,
        observation_status=ObservationStatus.OBSERVED,
        verification_status=VerificationStatus.VERIFIED,
    )


def _verified_core_module_provenance(
    core_topology: TopologyPlan,
    core_deployment: PhysicalDeploymentResult,
    *,
    environment_fingerprint: EnvironmentFingerprint,
) -> tuple[
    dict[str, PhysicalDeploymentItemResult],
    dict[str, EvidenceRecord],
    dict[str, list[str]],
    list[str],
]:
    expected_ids = {
        f"{item.device}:{item.slot}:{item.module}" for item in core_topology.modules
    }
    errors: list[str] = []
    if (
        core_deployment.status is not PhysicalDeploymentStatus.VERIFIED
        or core_deployment.manifest is None
        or core_deployment.physical_topology_hash
        != core_topology.physical_identity_hash
    ):
        errors.append("Original core deployment provenance is not VERIFIED and hash-bound.")
    if (
        core_deployment.environment_fingerprint.semantic_hash
        != environment_fingerprint.semantic_hash
    ):
        errors.append("Original core module evidence belongs to another environment.")

    items = {
        item.target_id: item
        for item in core_deployment.item_results
        if item.target_kind is PhysicalObjectKind.MODULE
    }
    if set(items) != expected_ids or any(
        item.status is not PhysicalDeploymentItemStatus.OBSERVED
        or item.disposition is not MutationDisposition.CHANGED
        or not item.applied
        or not item.observed
        for item in items.values()
    ):
        errors.append(
            "Original core module items do not prove session-owned CHANGED effects."
        )

    effect_records = {
        item.subject: item
        for item in core_deployment.evidence_records
        if item.id.startswith("e4/module-effect/")
    }
    modules_by_id = {
        f"{item.device}:{item.slot}:{item.module}": item
        for item in core_topology.modules
    }
    expected_ports: dict[str, list[str]] = {}
    for module_id in sorted(expected_ids):
        record = effect_records.get(module_id)
        module = modules_by_id[module_id]
        specification = resolve_module(module.module)
        catalog_ports = (
            sorted(set(specification.ports_added), key=str.casefold)
            if specification is not None else []
        )
        if (
            record is None
            or not record.verifies_claim
            or record.environment_fingerprint != environment_fingerprint.semantic_hash
            or record.id != f"e4/module-effect/{module_id}"
            or not isinstance(record.observed_value, dict)
        ):
            errors.append(
                f"Original causal module-effect evidence for {module_id!r} is missing."
            )
            continue
        ports = record.observed_value.get("expected_ports")
        if (
            not isinstance(ports, list)
            or sorted(set(ports), key=str.casefold) != catalog_ports
            or record.observed_value.get("device_name") != module.device
            or record.observed_value.get("requested_slot") != module.slot
            or record.observed_value.get("requested_module") != module.module
            or record.observed_value.get("device_newly_owned") is not True
            or record.observed_value.get("effect_verification_status") != "verified"
        ):
            errors.append(
                f"Original module-effect evidence for {module_id!r} does not "
                "match its exact catalogued, newly-caused effect."
            )
            continue
        expected_ports[module_id] = catalog_ports
    return items, effect_records, expected_ports, errors


def reconcile_canonical_stage_deployment(
    topology: TopologyPlan,
    runtime: CanonicalStageObservationRuntime,
    *,
    environment_fingerprint: EnvironmentFingerprint,
    verified_core_topology: TopologyPlan,
    verified_core_deployment: PhysicalDeploymentResult,
    deployment_id: str,
) -> PhysicalDeploymentResult:
    """Build a fresh cumulative manifest without replaying module causation.

    The three router modules are installed and causally VERIFIED in the first
    core transaction.  Later stages bind that whole provenance ledger and also
    freshly require every retained module port, cumulative device, and link.
    """

    journal = ApplicationExecutionJournal(
        plan_id=topology.id or topology.name,
        deployment_id=deployment_id,
    )
    errors: list[str] = []
    module_items_by_id, module_effect_records, module_ports, module_errors = (
        _verified_core_module_provenance(
            verified_core_topology,
            verified_core_deployment,
            environment_fingerprint=environment_fingerprint,
        )
    )
    errors.extend(module_errors)
    current_module_ids = {
        f"{item.device}:{item.slot}:{item.module}" for item in topology.modules
    }
    if current_module_ids != set(module_items_by_id):
        errors.append("Cumulative topology module inventory changed from the VERIFIED core.")
    try:
        workspace = runtime.observe_workspace()
    except Exception as exc:
        workspace = None
        errors.append(f"Canonical workspace observation failed: {exc}")
    if workspace is not None:
        workspace_error = canonical_stage_workspace_error(workspace, topology)
        if workspace_error:
            errors.append(workspace_error)

    inventory: list[RuntimeConfigurationTarget] = []
    device_items: list[PhysicalDeploymentItemResult] = []
    fresh_evidence: list[EvidenceRecord] = []
    observed_interfaces: dict[str, set[str]] = {}
    if not errors:
        for device in topology.devices:
            try:
                observed = runtime.observe_device(device)
            except Exception as exc:
                observed = None
                errors.append(f"Device {device.name!r} observation failed: {exc}")
            if (
                observed is None
                or not observed.observed
                or not observed.interfaces_observed
                or observed.deployed_name != device.name
                or observed.model != device.model
            ):
                if observed is not None:
                    errors.append(
                        f"Device {device.name!r} cumulative identity was not observed."
                    )
                continue
            inventory.append(RuntimeConfigurationTarget(
                device_name=observed.deployed_name,
                model=observed.model,
                interfaces=sorted(set(observed.interfaces)),
                runtime_identifier=observed.runtime_identifier,
                runtime_identifier_stable=observed.runtime_identifier_stable,
                runtime_fingerprint=observed.runtime_fingerprint,
            ))
            observed_interfaces[device.name] = set(observed.interfaces)
            device_items.append(PhysicalDeploymentItemResult(
                target_id=device.id or device.name,
                target_kind=PhysicalObjectKind.DEVICE,
                status=PhysicalDeploymentItemStatus.OBSERVED,
                disposition=MutationDisposition.NO_OP,
                observed=True,
                message="Fresh cumulative device identity read-back.",
            ))
            fresh_evidence.append(_fresh_evidence(
                identifier=f"e4/cumulative-device/{device.id or device.name}",
                subject=device.id or device.name,
                claim="retained canonical device identity and port inventory match runtime",
                source="physical_topology_runtime.observe_device",
                observed_value=observed.model_dump(mode="json"),
                fingerprint=environment_fingerprint,
            ))

    modules_by_device = {
        f"{item.device}:{item.slot}:{item.module}": item.device
        for item in topology.modules
    }
    if not errors:
        for module_id, ports in sorted(module_ports.items()):
            device_name = modules_by_device[module_id]
            missing = sorted(
                set(ports) - observed_interfaces.get(device_name, set()),
                key=str.casefold,
            )
            if missing:
                errors.append(
                    f"Retained module {module_id!r} is missing fresh port(s): "
                    + ", ".join(missing)
                )
                continue
            fresh_evidence.append(_fresh_evidence(
                identifier=f"e4/cumulative-module-presence/{module_id}",
                subject=module_id,
                claim="all causally verified module-effect ports remain present",
                source="physical_topology_runtime.observe_device",
                observed_value={
                    "device_name": device_name,
                    "expected_ports": ports,
                    "observed_ports": sorted(observed_interfaces[device_name]),
                },
                fingerprint=environment_fingerprint,
            ))

    link_items: list[PhysicalDeploymentItemResult] = []
    link_bindings: list[DeploymentLinkBinding] = []
    if not errors:
        for link in topology.links:
            target_id = link.id or (
                f"{link.device_a}:{link.port_a}->{link.device_b}:{link.port_b}"
            )
            try:
                observed = runtime.observe_link(link)
            except Exception as exc:
                observed = None
                errors.append(f"Link {target_id!r} observation failed: {exc}")
            if observed is None or not observed.observed:
                if observed is not None:
                    errors.append(f"Link {target_id!r} was not freshly observed.")
                continue
            expected_endpoints = {
                (link.device_a, link.port_a),
                (link.device_b, link.port_b),
            }
            observed_endpoints = {
                (observed.device_a, observed.port_a),
                (observed.device_b, observed.port_b),
            }
            if observed_endpoints != expected_endpoints:
                errors.append(f"Link {target_id!r} endpoint read-back contradicted plan.")
                continue
            link_items.append(PhysicalDeploymentItemResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.LINK,
                status=PhysicalDeploymentItemStatus.OBSERVED,
                disposition=MutationDisposition.NO_OP,
                observed=True,
                message="Fresh cumulative link endpoint read-back.",
            ))
            fresh_evidence.append(_fresh_evidence(
                identifier=f"e4/cumulative-link/{target_id}",
                subject=target_id,
                claim="retained canonical link endpoints and ports match runtime",
                source="physical_topology_runtime.observe_link",
                observed_value=observed.model_dump(mode="json"),
                fingerprint=environment_fingerprint,
            ))
            link_bindings.append(DeploymentLinkBinding(
                semantic_link_id=target_id,
                endpoint_a=DeploymentLinkEndpoint(
                    semantic_device_id=link.device_a_id or link.device_a,
                    interface=link.port_a,
                ),
                endpoint_b=DeploymentLinkEndpoint(
                    semantic_device_id=link.device_b_id or link.device_b,
                    interface=link.port_b,
                ),
                runtime_link_identifier=observed.runtime_link_identifier,
                runtime_link_identity_observed=(
                    observed.runtime_link_identity_observed
                ),
            ))

    module_items = [
        module_items_by_id[module_id].model_copy(update={
            "message": "Original causal module effect retained; ports freshly observed.",
        })
        for module_id in sorted(current_module_ids)
        if module_id in module_items_by_id
    ]

    manifest = None
    if not errors:
        try:
            manifest = build_deployment_manifest(
                topology,
                inventory,
                fingerprint=environment_fingerprint,
                deployment_id=deployment_id,
                link_bindings=link_bindings,
            )
        except Exception as exc:
            errors.append(f"Cumulative manifest creation failed: {exc}")

    if errors:
        for error in errors:
            journal.mark_preflight_failure(error)
    return PhysicalDeploymentResult(
        topology_id=topology.id or topology.name,
        physical_topology_hash=topology.physical_identity_hash,
        deployment_id=deployment_id,
        environment_fingerprint=environment_fingerprint,
        status=(
            PhysicalDeploymentStatus.VERIFIED
            if manifest is not None and not errors
            else PhysicalDeploymentStatus.FAILED
        ),
        failure_code=(
            PhysicalDeploymentFailureCode.NONE
            if manifest is not None and not errors
            else PhysicalDeploymentFailureCode.MANIFEST_CREATION_FAILED
        ),
        item_results=[*device_items, *module_items, *link_items],
        manifest=manifest,
        execution_journal=journal,
        dirty_state=journal.dirty_state,
        evidence_records=[
            *(
                module_effect_records[module_id].model_copy(deep=True)
                for module_id in sorted(current_module_ids)
                if module_id in module_effect_records
            ),
            *fresh_evidence,
        ],
        errors=errors,
    )
