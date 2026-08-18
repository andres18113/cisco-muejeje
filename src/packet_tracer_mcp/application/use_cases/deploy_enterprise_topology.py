"""Apply and independently observe an E4 physical topology.

This use case is the backend-neutral production seam for physical deployment.
Adapters may use Packet Tracer, CML or another backend, but a manifest is only
emitted after every planned device, port and link has fresh exact read-back.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Protocol

from ...domain.enterprise.models.configuration_runtime import RuntimeConfigurationTarget
from ...domain.enterprise.models.deployment import (
    DeploymentLinkBinding,
    DeploymentLinkEndpoint,
    DeploymentIdentityError,
    EnvironmentFingerprint,
    build_deployment_manifest,
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
from ...domain.enterprise.models.execution import (
    ApplicationExecutionJournal,
    ExecutionJournalEntry,
    MutationDisposition,
    OperationSemantics,
)
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentFailureCode,
    PhysicalDeploymentItemResult,
    PhysicalDeploymentItemStatus,
    PhysicalDeploymentResult,
    PhysicalDeploymentStatus,
    PhysicalDeviceObservation,
    PhysicalLinkObservation,
    PhysicalModuleEffectCapability,
    PhysicalModuleObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceObservation,
)
from ...domain.enterprise.services.topology_identity import compute_topology_hashes
from ...domain.models.plans import DevicePlan, LinkPlan, ModulePlan, TopologyPlan
from ...domain.enterprise.models.port_inventory import PortInventoryResolution
from ...infrastructure.catalog.measured_port_inventories import (
    backend_verified_port_inventory,
    module_state_token,
)


class PortInventoryResolver(Protocol):
    """Authorises concrete port names for one model, build and module state."""

    def __call__(
        self,
        model: str,
        *,
        backend: str = ...,
        backend_version: str = ...,
        installed_modules: list[str] | tuple[str, ...] | None = ...,
    ) -> PortInventoryResolution: ...


_SUCCESSFUL_DISPOSITIONS = {
    MutationDisposition.CHANGED,
    MutationDisposition.NO_OP,
    MutationDisposition.REASSERTED,
}


class PhysicalTopologyRuntime(Protocol):
    """Minimal structured runtime required by E4 physical deployment."""

    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult: ...

    def observe_device(self, device: DevicePlan) -> PhysicalDeviceObservation: ...

    def module_effect_capability(
        self,
        module: ModulePlan,
        device: DevicePlan,
    ) -> PhysicalModuleEffectCapability: ...

    def ensure_module(self, module: ModulePlan) -> PhysicalMutationResult: ...

    def observe_module_effect(self, module: ModulePlan) -> PhysicalModuleObservation: ...

    def ensure_link(self, link: LinkPlan) -> PhysicalMutationResult: ...

    def observe_link(self, link: LinkPlan) -> PhysicalLinkObservation: ...

    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...


def disposable_workspace_error(observation: PhysicalWorkspaceObservation) -> str:
    """Return the hard-stop reason for a complete disposable-workspace inventory."""

    if not observation.observed:
        return (
            "Read-only workspace inventory was incomplete: "
            + (observation.message or "unknown observation failure")
        )
    invalid_backend_managed = [
        item
        for item in observation.backend_managed_devices
        if item.model.strip().casefold() != "power distribution device"
        or bool(item.ports)
    ]
    if invalid_backend_managed:
        return (
            "Workspace inventory used an invalid backend-managed classification; "
            "only an exact zero-port Power Distribution Device may be excluded."
        )
    if observation.semantic_devices or observation.links:
        return (
            "Workspace is not empty: observed "
            f"{len(observation.semantic_devices)} semantic device(s) and "
            f"{len(observation.links)} link(s). User/manual/graded topology "
            "must never be mutated."
        )
    return ""


class EnterprisePhysicalTopologyDeployer:
    """Ensure E4 physical state and issue a manifest only after exact read-back."""

    def __init__(
        self,
        runtime: PhysicalTopologyRuntime,
        *,
        port_inventory: PortInventoryResolver = backend_verified_port_inventory,
    ) -> None:
        self._runtime = runtime
        #: Where concrete port names are authorised from.  It is injectable for
        #: the same reason the runtime is: a caller driving a substitute backend
        #: must supply the port evidence of *that* backend rather than borrow
        #: measurements taken against a real one.  The default is the measured
        #: catalogue, so a caller that says nothing gets the strict contract.
        self._port_inventory = port_inventory

    def deploy(
        self,
        topology: TopologyPlan,
        *,
        environment_fingerprint: EnvironmentFingerprint,
        deployment_id: str = "",
        require_empty_workspace: bool = False,
    ) -> PhysicalDeploymentResult:
        physical_hash = topology.physical_identity_hash
        resolved_deployment_id = deployment_id or (
            f"deployment/{physical_hash[:16]}" if physical_hash else "deployment/unverified"
        )
        journal = ApplicationExecutionJournal(
            plan_id=topology.id or topology.name,
            deployment_id=resolved_deployment_id,
        )
        item_results: dict[tuple[PhysicalObjectKind, str], PhysicalDeploymentItemResult] = {}
        evidence: list[EvidenceRecord] = []

        preflight_errors, failure_code = _preflight(
            topology,
            environment_fingerprint=environment_fingerprint,
            port_inventory=self._port_inventory,
        )
        if preflight_errors:
            for message in preflight_errors:
                journal.mark_preflight_failure(message)
            return _result(
                topology=topology,
                deployment_id=resolved_deployment_id,
                environment_fingerprint=environment_fingerprint,
                failure_code=failure_code,
                item_results=item_results,
                evidence=evidence,
                journal=journal,
                errors=preflight_errors,
            )

        if require_empty_workspace:
            workspace, workspace_error = self._observe_workspace()
            evidence.append(_workspace_evidence(
                workspace,
                error=workspace_error,
                fingerprint=environment_fingerprint,
            ))
            if workspace_error:
                journal.mark_preflight_failure(workspace_error)
                return _result(
                    topology=topology,
                    deployment_id=resolved_deployment_id,
                    environment_fingerprint=environment_fingerprint,
                    failure_code=(
                        PhysicalDeploymentFailureCode.WORKSPACE_OBSERVATION_FAILED
                        if workspace is None or not workspace.observed
                        else PhysicalDeploymentFailureCode.WORKSPACE_NOT_EMPTY
                    ),
                    item_results=item_results,
                    evidence=evidence,
                    journal=journal,
                    errors=[workspace_error],
                )

        devices = sorted(topology.devices, key=_device_id)
        modules = sorted(topology.modules, key=_module_id)
        devices_by_name = {item.name: item for item in devices}
        module_capabilities: dict[str, PhysicalModuleEffectCapability] = {}
        module_capability_errors: list[str] = []
        for module in modules:
            target_id = _module_id(module)
            capability, error = self._module_effect_capability(
                module,
                devices_by_name[module.device],
            )
            if capability is not None:
                module_capabilities[target_id] = capability
            evidence.append(_module_capability_evidence(
                module,
                capability,
                error=error,
                fingerprint=environment_fingerprint,
            ))
            if error:
                module_capability_errors.append(error)
                journal.mark_preflight_failure(error)

        if module_capability_errors:
            return _result(
                topology=topology,
                deployment_id=resolved_deployment_id,
                environment_fingerprint=environment_fingerprint,
                failure_code=(
                    PhysicalDeploymentFailureCode.MODULE_OBSERVATION_UNAVAILABLE
                ),
                item_results=item_results,
                evidence=evidence,
                journal=journal,
                errors=module_capability_errors,
            )

        links = sorted(topology.links, key=_link_id)

        for device in devices:
            target_id = _device_id(device)
            mutation, error = self._ensure_device(device)
            _append_mutation(journal, mutation, error=error)
            item_results[(PhysicalObjectKind.DEVICE, target_id)] = _item_from_mutation(
                mutation, error=error,
            )
            if error:
                return _result(
                    topology=topology,
                    deployment_id=resolved_deployment_id,
                    environment_fingerprint=environment_fingerprint,
                    failure_code=PhysicalDeploymentFailureCode.DEVICE_APPLICATION_FAILED,
                    item_results=item_results,
                    evidence=evidence,
                    journal=journal,
                    errors=[error],
                )

        for module in modules:
            target_id = _module_id(module)
            mutation, error = self._ensure_module(module)
            _append_mutation(journal, mutation, error=error)
            item_results[(PhysicalObjectKind.MODULE, target_id)] = _item_from_mutation(
                mutation,
                error=error,
            )
            if error:
                return _result(
                    topology=topology,
                    deployment_id=resolved_deployment_id,
                    environment_fingerprint=environment_fingerprint,
                    failure_code=PhysicalDeploymentFailureCode.MODULE_APPLICATION_FAILED,
                    item_results=item_results,
                    evidence=evidence,
                    journal=journal,
                    errors=[error],
                )

        module_observation_errors: list[str] = []
        for module in modules:
            target_id = _module_id(module)
            observation, error = self._observe_module_effect(
                module,
                module_capabilities[target_id],
            )
            evidence.append(_module_effect_evidence(
                module,
                module_capabilities[target_id],
                observation,
                error=error,
                fingerprint=environment_fingerprint,
            ))
            evidence.append(_module_identity_evidence(
                module,
                observation,
                error=error,
                fingerprint=environment_fingerprint,
            ))
            evidence.append(_module_placement_evidence(
                module,
                observation,
                fingerprint=environment_fingerprint,
            ))
            item = item_results[(PhysicalObjectKind.MODULE, target_id)]
            if error:
                item.status = PhysicalDeploymentItemStatus.FAILED
                item.observed = False
                item.message = error
                _append_observation_failure(
                    journal,
                    action_id=f"observe-module:{target_id}",
                    message=error,
                )
                module_observation_errors.append(error)
            else:
                item.status = PhysicalDeploymentItemStatus.OBSERVED
                item.observed = True

        if module_observation_errors:
            return _result(
                topology=topology,
                deployment_id=resolved_deployment_id,
                environment_fingerprint=environment_fingerprint,
                failure_code=PhysicalDeploymentFailureCode.MODULE_OBSERVATION_FAILED,
                item_results=item_results,
                evidence=evidence,
                journal=journal,
                errors=module_observation_errors,
            )

        device_observations: dict[str, PhysicalDeviceObservation] = {}
        observation_errors: list[tuple[PhysicalDeploymentFailureCode, str]] = []
        planned_ports = _planned_ports(topology)
        for device in devices:
            target_id = _device_id(device)
            observation, error, failure_code = self._observe_device(
                device,
                required_ports=planned_ports.get(target_id, set()),
            )
            if observation is not None:
                device_observations[target_id] = observation
            evidence.append(_device_evidence(
                device,
                observation,
                error=error,
                fingerprint=environment_fingerprint,
            ))
            item = item_results[(PhysicalObjectKind.DEVICE, target_id)]
            if error:
                item.status = PhysicalDeploymentItemStatus.FAILED
                item.observed = False
                item.message = error
                _append_observation_failure(
                    journal,
                    action_id=f"observe-device:{target_id}",
                    message=error,
                )
                observation_errors.append((failure_code, error))
            else:
                item.status = PhysicalDeploymentItemStatus.OBSERVED
                item.observed = True

        if observation_errors:
            return _result(
                topology=topology,
                deployment_id=resolved_deployment_id,
                environment_fingerprint=environment_fingerprint,
                failure_code=observation_errors[0][0],
                item_results=item_results,
                evidence=evidence,
                journal=journal,
                errors=[message for _, message in observation_errors],
            )

        for link in links:
            target_id = _link_id(link)
            mutation, error = self._ensure_link(link)
            _append_mutation(journal, mutation, error=error)
            item_results[(PhysicalObjectKind.LINK, target_id)] = _item_from_mutation(
                mutation, error=error,
            )
            if error:
                return _result(
                    topology=topology,
                    deployment_id=resolved_deployment_id,
                    environment_fingerprint=environment_fingerprint,
                    failure_code=PhysicalDeploymentFailureCode.LINK_APPLICATION_FAILED,
                    item_results=item_results,
                    evidence=evidence,
                    journal=journal,
                    errors=[error],
                )

        link_observations: dict[str, PhysicalLinkObservation] = {}
        link_observation_errors: list[str] = []
        for link in links:
            target_id = _link_id(link)
            observation, error = self._observe_link(link)
            if observation is not None:
                link_observations[target_id] = observation
            evidence.append(_link_evidence(
                link,
                observation,
                error=error,
                fingerprint=environment_fingerprint,
            ))
            if observation is not None and not observation.cable_observed:
                evidence.append(_link_cable_evidence(
                    link,
                    observation,
                    fingerprint=environment_fingerprint,
                ))
            item = item_results[(PhysicalObjectKind.LINK, target_id)]
            if error:
                item.status = PhysicalDeploymentItemStatus.FAILED
                item.observed = False
                item.message = error
                _append_observation_failure(
                    journal,
                    action_id=f"observe-link:{target_id}",
                    message=error,
                )
                link_observation_errors.append(error)
            else:
                item.status = PhysicalDeploymentItemStatus.OBSERVED
                item.observed = True

        if link_observation_errors:
            return _result(
                topology=topology,
                deployment_id=resolved_deployment_id,
                environment_fingerprint=environment_fingerprint,
                failure_code=PhysicalDeploymentFailureCode.LINK_OBSERVATION_FAILED,
                item_results=item_results,
                evidence=evidence,
                journal=journal,
                errors=link_observation_errors,
            )

        inventory = [
            RuntimeConfigurationTarget(
                device_name=observation.deployed_name,
                model=observation.model,
                interfaces=sorted(set(observation.interfaces)),
                runtime_identifier=observation.runtime_identifier,
                runtime_identifier_stable=observation.runtime_identifier_stable,
                runtime_fingerprint=observation.runtime_fingerprint,
            )
            for _, observation in sorted(device_observations.items())
        ]
        try:
            link_bindings = [
                _link_binding_from_observation(
                    link,
                    link_observations[_link_id(link)],
                )
                for link in links
            ]
            manifest = build_deployment_manifest(
                topology,
                inventory,
                fingerprint=environment_fingerprint,
                deployment_id=resolved_deployment_id,
                link_bindings=link_bindings,
            )
        except DeploymentIdentityError as exc:
            message = f"DeploymentManifest creation failed after observation: {exc}"
            _append_observation_failure(
                journal,
                action_id="manifest:create",
                message=message,
            )
            return _result(
                topology=topology,
                deployment_id=resolved_deployment_id,
                environment_fingerprint=environment_fingerprint,
                failure_code=PhysicalDeploymentFailureCode.MANIFEST_CREATION_FAILED,
                item_results=item_results,
                evidence=evidence,
                journal=journal,
                errors=[message],
            )

        evidence_by_subject = {item.subject: item.id for item in evidence if item.verifies_claim}
        for binding in manifest.bindings:
            binding.creation_evidence = evidence_by_subject.get(
                binding.semantic_device_id,
                binding.creation_evidence,
            )
        return PhysicalDeploymentResult(
            topology_id=topology.id or topology.name,
            physical_topology_hash=physical_hash,
            deployment_id=resolved_deployment_id,
            environment_fingerprint=environment_fingerprint,
            status=PhysicalDeploymentStatus.VERIFIED,
            item_results=_ordered_items(item_results),
            manifest=manifest,
            execution_journal=journal,
            dirty_state=journal.dirty_state,
            evidence_records=evidence,
        )

    def _observe_workspace(
        self,
    ) -> tuple[PhysicalWorkspaceObservation | None, str]:
        try:
            observation = self._runtime.observe_workspace()
        except Exception as exc:
            return None, f"Read-only workspace inventory failed: {exc}"
        if not isinstance(observation, PhysicalWorkspaceObservation):
            return None, "Runtime returned an invalid workspace inventory type."
        if not observation.observed:
            return observation, (
                "Read-only workspace inventory was incomplete: "
                + (observation.message or "unknown observation failure")
            )
        error = disposable_workspace_error(observation)
        return observation, error

    def _ensure_device(
        self,
        device: DevicePlan,
    ) -> tuple[PhysicalMutationResult, str]:
        target_id = _device_id(device)
        try:
            mutation = self._runtime.ensure_device(device)
        except Exception as exc:
            return _failed_mutation(
                target_id,
                PhysicalObjectKind.DEVICE,
                f"Device ensure failed for {target_id!r}: {exc}",
            )
        error = _mutation_error(
            mutation,
            expected_id=target_id,
            expected_kind=PhysicalObjectKind.DEVICE,
        )
        if error and (
            mutation.target_id != target_id
            or mutation.target_kind is not PhysicalObjectKind.DEVICE
        ):
            mutation = mutation.model_copy(update={
                "target_id": target_id,
                "target_kind": PhysicalObjectKind.DEVICE,
            })
        return mutation, error

    def _module_effect_capability(
        self,
        module: ModulePlan,
        device: DevicePlan,
    ) -> tuple[PhysicalModuleEffectCapability | None, str]:
        target_id = _module_id(module)
        provider = getattr(self._runtime, "module_effect_capability", None)
        if not callable(provider):
            return None, (
                "The selected backend has no typed module-effect capability; "
                "refusing modular deployment before mutation."
            )
        try:
            capability = provider(module, device)
        except Exception as exc:
            return None, f"Module capability failed for {target_id!r}: {exc}"
        if capability.target_id != target_id:
            return capability, (
                f"Module capability returned target {capability.target_id!r}; "
                f"expected {target_id!r}."
            )
        if capability.operation_support is not SupportStatus.SUPPORTED:
            return capability, (
                f"Module operation for {target_id!r} is "
                f"{capability.operation_support.value}; refusing mutation."
            )
        if capability.effect_observation_support is not SupportStatus.SUPPORTED:
            return capability, (
                f"Module effect observation for {target_id!r} is "
                f"{capability.effect_observation_support.value}; refusing mutation."
            )
        if not capability.expected_ports:
            return capability, (
                f"Module effect capability for {target_id!r} declares no expected ports."
            )
        return capability, ""

    def _ensure_module(
        self,
        module: ModulePlan,
    ) -> tuple[PhysicalMutationResult, str]:
        target_id = _module_id(module)
        ensure = getattr(self._runtime, "ensure_module", None)
        if not callable(ensure):
            return _failed_mutation(
                target_id,
                PhysicalObjectKind.MODULE,
                "Backend declared module observation but has no typed module ensure operation.",
            )
        try:
            mutation = ensure(module)
        except Exception as exc:
            return _failed_mutation(
                target_id,
                PhysicalObjectKind.MODULE,
                f"Module ensure failed for {target_id!r}: {exc}",
            )
        error = _mutation_error(
            mutation,
            expected_id=target_id,
            expected_kind=PhysicalObjectKind.MODULE,
        )
        return mutation, error

    def _observe_module_effect(
        self,
        module: ModulePlan,
        capability: PhysicalModuleEffectCapability,
    ) -> tuple[PhysicalModuleObservation | None, str]:
        target_id = _module_id(module)
        observe = getattr(self._runtime, "observe_module_effect", None)
        if not callable(observe):
            return None, "Backend has no typed module-effect observation operation."
        try:
            observation = observe(module)
        except Exception as exc:
            return None, f"Module-effect observation failed for {target_id!r}: {exc}"
        if observation.target_id != target_id:
            return observation, (
                f"Module-effect observation returned target {observation.target_id!r}; "
                f"expected {target_id!r}."
            )
        if (
            observation.device_name != module.device
            or observation.requested_slot != module.slot
            or observation.requested_module != module.module
        ):
            return observation, (
                f"Module-effect observation for {target_id!r} crossed its requested target."
            )
        if not observation.observed:
            return observation, f"Module effect for {target_id!r} was not observed."
        if observation.freshness is not EvidenceFreshness.FRESH:
            return observation, f"Module effect for {target_id!r} is stale or undated."
        if not observation.port_inventory_observed:
            return observation, f"Module effect port inventory for {target_id!r} was unobservable."
        expected_ports = set(capability.expected_ports)
        if set(observation.expected_ports) != expected_ports:
            return observation, (
                f"Module-effect observation for {target_id!r} changed the expected port set."
            )
        if not expected_ports.issubset(observation.ports_after):
            missing = sorted(expected_ports - set(observation.ports_after))
            return observation, (
                f"Module effect for {target_id!r} is missing expected port(s): "
                + ", ".join(missing)
            )
        if not expected_ports.issubset(observation.observed_expected_ports):
            return observation, f"Module effect for {target_id!r} is only partially observed."
        if not set(capability.expected_port_classes).issubset(
            observation.observed_port_classes,
        ):
            return observation, (
                f"Module effect for {target_id!r} lacks the expected port class evidence."
            )
        # What a module requirement really asks for is that the ports exist and
        # that this transaction caused them.  Exact placement is UNOBSERVABLE on
        # this backend and is not required here -- see TD-MODULE-SLOT-001 -- so
        # the gate demands the port effect and claims nothing about the slot.
        if observation.effect_verification_status is not VerificationStatus.VERIFIED:
            return observation, (
                f"Module port effect for {target_id!r} is not VERIFIED "
                f"({observation.effect_verification_status.value}); "
                "only a fresh, complete, transaction-caused effect is evidence."
            )
        if (
            observation.identity_observation_status is ObservationStatus.OBSERVED
            and observation.observed_module_identity != module.module
        ):
            return observation, (
                f"Observed module identity {observation.observed_module_identity!r} "
                f"contradicts requested identity {module.module!r} for {target_id!r}."
            )
        return observation, ""

    def _ensure_link(self, link: LinkPlan) -> tuple[PhysicalMutationResult, str]:
        target_id = _link_id(link)
        try:
            mutation = self._runtime.ensure_link(link)
        except Exception as exc:
            return _failed_mutation(
                target_id,
                PhysicalObjectKind.LINK,
                f"Link ensure failed for {target_id!r}: {exc}",
            )
        error = _mutation_error(
            mutation,
            expected_id=target_id,
            expected_kind=PhysicalObjectKind.LINK,
        )
        if error and (
            mutation.target_id != target_id
            or mutation.target_kind is not PhysicalObjectKind.LINK
        ):
            mutation = mutation.model_copy(update={
                "target_id": target_id,
                "target_kind": PhysicalObjectKind.LINK,
            })
        return mutation, error

    def _observe_device(
        self,
        device: DevicePlan,
        *,
        required_ports: set[str],
    ) -> tuple[
        PhysicalDeviceObservation | None,
        str,
        PhysicalDeploymentFailureCode,
    ]:
        target_id = _device_id(device)
        try:
            observation = self._runtime.observe_device(device)
        except Exception as exc:
            return (
                None,
                f"Device observation failed for {target_id!r}: {exc}",
                PhysicalDeploymentFailureCode.DEVICE_OBSERVATION_FAILED,
            )
        if observation.target_id != target_id:
            return (
                observation,
                f"Device observation returned target {observation.target_id!r}; expected {target_id!r}.",
                PhysicalDeploymentFailureCode.DEVICE_OBSERVATION_FAILED,
            )
        if not observation.observed:
            return (
                observation,
                f"Device {target_id!r} was not observed after ensure.",
                PhysicalDeploymentFailureCode.DEVICE_OBSERVATION_FAILED,
            )
        if observation.deployed_name != device.name:
            return (
                observation,
                f"Device {target_id!r} name {observation.deployed_name!r} does not match {device.name!r}.",
                PhysicalDeploymentFailureCode.DEVICE_OBSERVATION_FAILED,
            )
        if observation.model != device.model:
            return (
                observation,
                f"Device {target_id!r} model {observation.model!r} does not match {device.model!r}.",
                PhysicalDeploymentFailureCode.DEVICE_OBSERVATION_FAILED,
            )
        if not observation.interfaces_observed:
            return (
                observation,
                f"Device {target_id!r} port inventory was not observed.",
                PhysicalDeploymentFailureCode.PORT_OBSERVATION_FAILED,
            )
        missing_ports = sorted(required_ports - set(observation.interfaces))
        if missing_ports:
            return (
                observation,
                f"Device {target_id!r} is missing planned physical port(s): {', '.join(missing_ports)}.",
                PhysicalDeploymentFailureCode.PORT_OBSERVATION_FAILED,
            )
        return observation, "", PhysicalDeploymentFailureCode.NONE

    def _observe_link(
        self,
        link: LinkPlan,
    ) -> tuple[PhysicalLinkObservation | None, str]:
        target_id = _link_id(link)
        try:
            observation = self._runtime.observe_link(link)
        except Exception as exc:
            return None, f"Link observation failed for {target_id!r}: {exc}"
        if observation.target_id != target_id:
            return observation, (
                f"Link observation returned target {observation.target_id!r}; expected {target_id!r}."
            )
        if not observation.observed:
            return observation, f"Link {target_id!r} was not observed after ensure."
        expected = (
            link.device_a,
            link.port_a,
            link.device_b,
            link.port_b,
        )
        observed = (
            observation.device_a,
            observation.port_a,
            observation.device_b,
            observation.port_b,
        )
        reversed_observed = (
            observation.device_b,
            observation.port_b,
            observation.device_a,
            observation.port_a,
        )
        if expected not in {observed, reversed_observed}:
            return observation, (
                f"Link {target_id!r} does not match its exact planned endpoints and ports."
            )
        if observation.cable_observed and observation.cable != link.cable:
            return observation, (
                f"Link {target_id!r} cable {observation.cable!r} does not match "
                f"the planned cable {link.cable!r}."
            )
        return observation, ""


def _preflight(
    topology: TopologyPlan,
    *,
    environment_fingerprint: EnvironmentFingerprint,
    port_inventory: PortInventoryResolver = backend_verified_port_inventory,
) -> tuple[list[str], PhysicalDeploymentFailureCode]:
    errors: list[str] = []
    if topology.errors:
        errors.extend(f"Topology error: {message}" for message in topology.errors)
    if topology.hash_schema_version != "2" or not topology.physical_topology_hash:
        errors.append("E4 physical deployment requires an explicit physical-topology-v2 hash.")
        return errors, PhysicalDeploymentFailureCode.PHYSICAL_HASH_MISMATCH
    recomputed = compute_topology_hashes(topology).physical_topology_hash
    if recomputed != topology.physical_topology_hash:
        errors.append("Stored physical topology hash does not match the current E4 physical plan.")
        return errors, PhysicalDeploymentFailureCode.PHYSICAL_HASH_MISMATCH
    if not environment_fingerprint.backend.strip() or not environment_fingerprint.backend_version.strip():
        errors.append("A real backend and backend version fingerprint must be injected before deployment.")
        return errors, PhysicalDeploymentFailureCode.ENVIRONMENT_FINGERPRINT_INVALID

    device_ids = [_device_id(item) for item in topology.devices]
    device_names = [item.name for item in topology.devices]
    if any(not item.strip() for item in device_ids):
        errors.append("Every physical device requires a semantic identifier.")
    if len(device_ids) != len(set(device_ids)):
        errors.append("Physical device semantic identifiers must be unique.")
    if len(device_names) != len(set(device_names)):
        errors.append("Deployed device names must be unique within one topology.")

    known_ids = set(device_ids)
    known_names = set(device_names)
    id_to_name = {
        identifier: device.name
        for identifier, device in zip(device_ids, topology.devices, strict=True)
    }
    module_slots: set[tuple[str, str]] = set()
    for module in topology.modules:
        module_id = _module_id(module)
        if module.device not in known_names:
            errors.append(
                f"Module {module_id!r} references unknown device {module.device!r}."
            )
        if not module.slot.strip() or not module.module.strip():
            errors.append(
                f"Module {module_id!r} requires a concrete slot and module model."
            )
        slot_key = (module.device, module.slot)
        if slot_key in module_slots:
            errors.append(
                f"Physical module slot {module.device!r}:{module.slot!r} is assigned "
                "more than once."
            )
        module_slots.add(slot_key)

    link_ids = [_link_id(item) for item in topology.links]
    if any(not item.strip() for item in link_ids):
        errors.append("Every physical link requires a semantic identifier.")
    if len(link_ids) != len(set(link_ids)):
        errors.append("Physical link semantic identifiers must be unique.")
    used_ports: set[tuple[str, str]] = set()
    for link in topology.links:
        endpoints = (
            (link.device_a_id or link.device_a, link.device_a, link.port_a),
            (link.device_b_id or link.device_b, link.device_b, link.port_b),
        )
        for identifier, name, port in endpoints:
            if identifier not in known_ids or name not in known_names:
                errors.append(
                    f"Link {_link_id(link)!r} references unknown endpoint {identifier!r}/{name!r}."
                )
            elif id_to_name[identifier] != name:
                errors.append(
                    f"Link {_link_id(link)!r} crosses semantic endpoint {identifier!r} "
                    f"with deployed name {name!r}; expected {id_to_name[identifier]!r}."
                )
            if not port.strip():
                errors.append(f"Link {_link_id(link)!r} has an empty physical port.")
            port_key = (identifier, port)
            if port_key in used_ports:
                errors.append(
                    f"Physical port {identifier!r}:{port!r} is assigned to more than one link."
                )
            used_ports.add(port_key)
        if not link.cable.strip():
            errors.append(f"Link {_link_id(link)!r} has no cable identity.")
    if errors:
        return errors, PhysicalDeploymentFailureCode.INVALID_TOPOLOGY

    port_evidence_errors = _port_evidence_errors(
        topology,
        environment_fingerprint=environment_fingerprint,
        port_inventory=port_inventory,
    )
    if port_evidence_errors:
        return (
            port_evidence_errors,
            PhysicalDeploymentFailureCode.PORT_EVIDENCE_UNAVAILABLE,
        )
    return [], PhysicalDeploymentFailureCode.NONE


def _port_evidence_errors(
    topology: TopologyPlan,
    *,
    environment_fingerprint: EnvironmentFingerprint,
    port_inventory: PortInventoryResolver,
) -> list[str]:
    """Refuse concrete port names no backend evidence authorises.

    A declared catalogue says what a model should have; only a measurement says
    what this build actually reports.  Binding a link to a name from the first
    is how a run reaches Packet Tracer asking for a port that does not exist,
    so the check runs in preflight, before anything is mutated.

    The query carries the module state the device will be in at binding time,
    because a port that only exists once a card is installed is not evidence
    about the same device without it.
    """

    planned = _planned_ports(topology)
    modules_by_device: dict[str, list[str]] = {}
    for module in topology.modules:
        modules_by_device.setdefault(module.device, []).append(
            module_state_token(module.module, module.slot),
        )

    errors: list[str] = []
    for device in sorted(topology.devices, key=_device_id):
        required = sorted(planned.get(_device_id(device), set()), key=str.casefold)
        if not required:
            continue
        resolution = port_inventory(
            device.model,
            backend=environment_fingerprint.backend,
            backend_version=environment_fingerprint.backend_version,
            installed_modules=modules_by_device.get(device.name, ()),
        )
        unsupported = resolution.unsupported_ports(required)
        if not unsupported:
            continue
        errors.append(
            f"Device {_device_id(device)!r} ({device.model}) plans port(s) "
            f"{', '.join(unsupported)} that no backend-verified port inventory "
            f"authorises on {environment_fingerprint.backend} "
            f"{environment_fingerprint.backend_version}: {resolution.reason or 'declared only'}"
        )
    return errors


def _device_id(device: DevicePlan) -> str:
    return device.id or device.name


def _module_id(module: ModulePlan) -> str:
    return f"{module.device}:{module.slot}:{module.module}"


def _link_id(link: LinkPlan) -> str:
    return link.id or (
        f"{link.device_a}:{link.port_a}->{link.device_b}:{link.port_b}"
    )


def _planned_ports(topology: TopologyPlan) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for link in topology.links:
        result.setdefault(link.device_a_id or link.device_a, set()).add(link.port_a)
        result.setdefault(link.device_b_id or link.device_b, set()).add(link.port_b)
    return result


def _link_binding_from_observation(
    link: LinkPlan,
    observation: PhysicalLinkObservation,
) -> DeploymentLinkBinding:
    """Bind semantic endpoints to the interfaces returned by exact read-back."""

    if observation.device_a == link.device_a and observation.device_b == link.device_b:
        interface_a, interface_b = observation.port_a, observation.port_b
    elif observation.device_a == link.device_b and observation.device_b == link.device_a:
        interface_a, interface_b = observation.port_b, observation.port_a
    else:
        raise DeploymentIdentityError(
            f"Observed link {_link_id(link)!r} cannot be mapped to its semantic endpoints."
        )
    return DeploymentLinkBinding(
        semantic_link_id=_link_id(link),
        endpoint_a=DeploymentLinkEndpoint(
            semantic_device_id=link.device_a_id or link.device_a,
            interface=interface_a,
        ),
        endpoint_b=DeploymentLinkEndpoint(
            semantic_device_id=link.device_b_id or link.device_b,
            interface=interface_b,
        ),
        runtime_link_identifier=observation.runtime_link_identifier,
        runtime_link_identity_observed=(
            observation.runtime_link_identity_observed
            and bool(observation.runtime_link_identifier)
        ),
    )


def _mutation_error(
    mutation: PhysicalMutationResult,
    *,
    expected_id: str,
    expected_kind: PhysicalObjectKind,
) -> str:
    if mutation.target_id != expected_id or mutation.target_kind is not expected_kind:
        return (
            f"Runtime ensure result identity {mutation.target_kind.value}:{mutation.target_id!r} "
            f"does not match {expected_kind.value}:{expected_id!r}."
        )
    if mutation.disposition not in _SUCCESSFUL_DISPOSITIONS:
        return mutation.message or f"Runtime did not ensure {expected_kind.value} {expected_id!r}."
    if mutation.disposition in {
        MutationDisposition.CHANGED,
        MutationDisposition.REASSERTED,
    } and not mutation.applied:
        return (
            f"Runtime reported {mutation.disposition.value} for {expected_id!r} "
            "without confirming application."
        )
    return ""


def _failed_mutation(
    target_id: str,
    target_kind: PhysicalObjectKind,
    message: str,
) -> tuple[PhysicalMutationResult, str]:
    return PhysicalMutationResult(
        target_id=target_id,
        target_kind=target_kind,
        disposition=MutationDisposition.FAILED,
        message=message,
    ), message


def _append_mutation(
    journal: ApplicationExecutionJournal,
    mutation: PhysicalMutationResult,
    *,
    error: str,
) -> None:
    journal.append(ExecutionJournalEntry(
        ordinal=len(journal.entries) + 1,
        action_id=f"ensure-{mutation.target_kind.value}:{mutation.target_id}",
        operation=OperationSemantics.ENSURE_PRESENT,
        disposition=(
            MutationDisposition.UNKNOWN
            if mutation.disposition is MutationDisposition.UNKNOWN
            else MutationDisposition.FAILED
            if error
            else mutation.disposition
        ),
        inverse_action_id=mutation.inverse_action_id,
        inverse_available=mutation.inverse_available,
        message=error or mutation.message,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    ))


def _append_observation_failure(
    journal: ApplicationExecutionJournal,
    *,
    action_id: str,
    message: str,
) -> None:
    journal.append(ExecutionJournalEntry(
        ordinal=len(journal.entries) + 1,
        action_id=action_id,
        operation=OperationSemantics.TRANSITION,
        disposition=MutationDisposition.FAILED,
        message=message,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    ))


def _item_from_mutation(
    mutation: PhysicalMutationResult,
    *,
    error: str,
) -> PhysicalDeploymentItemResult:
    if error:
        status = PhysicalDeploymentItemStatus.FAILED
    elif mutation.disposition is MutationDisposition.NO_OP:
        status = PhysicalDeploymentItemStatus.SATISFIED
    else:
        status = PhysicalDeploymentItemStatus.APPLIED
    return PhysicalDeploymentItemResult(
        target_id=mutation.target_id,
        target_kind=mutation.target_kind,
        status=status,
        disposition=mutation.disposition,
        applied=mutation.applied,
        message=error or mutation.message,
    )


def _workspace_evidence(
    observation: PhysicalWorkspaceObservation | None,
    *,
    error: str,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    completed = observation is not None and observation.observed
    verified = completed and not error and observation.safe_for_disposable_mutation
    return EvidenceRecord(
        id="e4/workspace/pre-mutation",
        subject="physical-workspace",
        claim="workspace inventory is complete and contains no semantic topology",
        method=(VerificationMethod.STRUCTURED_API if observation else VerificationMethod.NONE),
        strength=(EvidenceStrength.CLAIM_DIRECT if observation else EvidenceStrength.NONE),
        source="physical_topology_runtime.observe_workspace",
        freshness=(EvidenceFreshness.FRESH if completed else EvidenceFreshness.UNKNOWN),
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value=(observation.compact_summary() if observation else None),
        support_status=(SupportStatus.SUPPORTED if completed else SupportStatus.UNKNOWN),
        observation_status=(
            ObservationStatus.OBSERVED if completed else ObservationStatus.PROBE_FAILED
        ),
        verification_status=(
            VerificationStatus.VERIFIED if verified
            else VerificationStatus.FAILED if completed
            else VerificationStatus.UNVERIFIED
        ),
        limitations=[error] if error else [],
    )


def _device_evidence(
    device: DevicePlan,
    observation: PhysicalDeviceObservation | None,
    *,
    error: str,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    observed_value = observation.model_dump(mode="json") if observation else None
    runtime_completed = observation is not None and observation.observed
    unobservable = bool(error) and "port inventory was not observed" in error
    return EvidenceRecord(
        id=f"e4/device/{_device_id(device)}",
        subject=_device_id(device),
        claim="planned physical device identity and required ports match runtime",
        method=VerificationMethod.STRUCTURED_API,
        strength=EvidenceStrength.CLAIM_DIRECT,
        source="physical_topology_runtime.observe_device",
        freshness=(EvidenceFreshness.FRESH if runtime_completed else EvidenceFreshness.UNKNOWN),
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value=observed_value,
        support_status=(SupportStatus.SUPPORTED if runtime_completed else SupportStatus.UNKNOWN),
        observation_status=(
            ObservationStatus.UNOBSERVABLE
            if unobservable
            else ObservationStatus.OBSERVED
            if runtime_completed
            else ObservationStatus.PROBE_FAILED
        ),
        verification_status=(
            VerificationStatus.VERIFIED
            if not error
            else VerificationStatus.UNVERIFIED
            if unobservable or not runtime_completed
            else VerificationStatus.FAILED
        ),
        limitations=[error] if error else [],
    )


def _module_capability_evidence(
    module: ModulePlan,
    capability: PhysicalModuleEffectCapability | None,
    *,
    error: str,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    observed_value = capability.model_dump(mode="json") if capability else None
    support = (
        capability.operation_support
        if capability is not None
        and capability.operation_support is not SupportStatus.SUPPORTED
        else capability.effect_observation_support
        if capability is not None
        else SupportStatus.UNKNOWN
    )
    verified = (
        capability is not None
        and not error
        and capability.operation_support is SupportStatus.SUPPORTED
        and capability.effect_observation_support is SupportStatus.SUPPORTED
    )
    explicitly_negative = support is SupportStatus.UNSUPPORTED
    return EvidenceRecord(
        id=f"e4/module-capability/{_module_id(module)}",
        subject=_module_id(module),
        claim="backend supports requested module operation and physical-effect observation",
        method=(VerificationMethod.STRUCTURED_API if capability else VerificationMethod.NONE),
        strength=(EvidenceStrength.CLAIM_DIRECT if capability else EvidenceStrength.NONE),
        source="physical_topology_runtime.module_effect_capability",
        freshness=(EvidenceFreshness.FRESH if capability else EvidenceFreshness.UNKNOWN),
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value=observed_value,
        support_status=support,
        observation_status=(
            ObservationStatus.OBSERVED if capability else ObservationStatus.PROBE_FAILED
        ),
        verification_status=(
            VerificationStatus.VERIFIED if verified
            else VerificationStatus.FAILED if explicitly_negative
            else VerificationStatus.UNVERIFIED
        ),
        limitations=[error] if error else [],
    )


def _module_effect_evidence(
    module: ModulePlan,
    capability: PhysicalModuleEffectCapability,
    observation: PhysicalModuleObservation | None,
    *,
    error: str,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    observed_value = observation.model_dump(mode="json") if observation else None
    freshness = observation.freshness if observation else EvidenceFreshness.UNKNOWN
    observed = bool(
        observation is not None
        and observation.observed
        and observation.port_inventory_observed
    )
    # One derivation, not two.  The observation already grades its own evidence;
    # re-grading it here is how the two halves drifted apart before.  The only
    # thing this layer adds is its capability cross-check: an error outranks a
    # self-reported VERIFIED.
    status = (
        observation.effect_verification_status if observation is not None
        else VerificationStatus.UNVERIFIED
    )
    if error and status is VerificationStatus.VERIFIED:
        status = VerificationStatus.FAILED
    return EvidenceRecord(
        id=f"e4/module-effect/{_module_id(module)}",
        subject=_module_id(module),
        claim=(
            "this transaction caused the requested module's complete port "
            "effect, proven by fresh before/after runtime state"
        ),
        method=(VerificationMethod.STRUCTURED_API if observation else VerificationMethod.NONE),
        strength=(EvidenceStrength.CLAIM_DIRECT if observation else EvidenceStrength.NONE),
        source="physical_topology_runtime.observe_module_effect",
        freshness=freshness,
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value=observed_value,
        support_status=capability.effect_observation_support,
        observation_status=(
            ObservationStatus.OBSERVED if observed else ObservationStatus.PROBE_FAILED
        ),
        verification_status=status,
        limitations=[error] if error else [],
    )


def _module_placement_evidence(
    module: ModulePlan,
    observation: PhysicalModuleObservation | None,
    *,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    """Record the placement dimension explicitly, including when it is unknown.

    A verified port effect says the ports exist and that this transaction caused
    them.  It says nothing about which slot the card physically occupies, and a
    manifest that stayed silent about that would read as if it did.
    """

    placement_status = (
        observation.placement_observation_status
        if observation is not None
        else ObservationStatus.PROBE_FAILED
    )
    return EvidenceRecord(
        id=f"e4/module-placement/{_module_id(module)}",
        subject=_module_id(module),
        claim="requested module physically occupies the requested slot",
        method=(
            VerificationMethod.STRUCTURED_API
            if placement_status is ObservationStatus.OBSERVED
            else VerificationMethod.NONE
        ),
        strength=(
            EvidenceStrength.CLAIM_DIRECT
            if placement_status is ObservationStatus.OBSERVED
            else EvidenceStrength.NONE
        ),
        source="physical_topology_runtime.observe_module_effect",
        freshness=(observation.freshness if observation else EvidenceFreshness.UNKNOWN),
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value={
            "requested_slot": module.slot,
            "observed_module_numbers": [
                item.observed_module_number
                for item in (observation.slot_observations if observation else [])
            ],
            "module_tree_observed": bool(observation and observation.module_tree_observed),
        },
        support_status=SupportStatus.UNKNOWN,
        observation_status=placement_status,
        verification_status=VerificationStatus.UNVERIFIED,
        limitations=[
            "Packet Tracer reports module-tree numbers in a namespace this "
            "repository cannot map to the requested slot; exact physical "
            "placement is not claimed. TD-MODULE-SLOT-001."
        ] if placement_status is not ObservationStatus.OBSERVED else [],
    )


def _module_identity_evidence(
    module: ModulePlan,
    observation: PhysicalModuleObservation | None,
    *,
    error: str,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    identity_status = (
        observation.identity_observation_status
        if observation is not None
        else ObservationStatus.PROBE_FAILED
    )
    observed_identity = observation.observed_module_identity if observation else ""
    identity_matches = (
        identity_status is ObservationStatus.OBSERVED
        and observed_identity == module.module
    )
    limitation = (
        "Packet Tracer did not directly identify the module installed for the "
        "requested slot; requested identity is not observed identity."
        if identity_status is ObservationStatus.UNOBSERVABLE
        else error
    )
    return EvidenceRecord(
        id=f"e4/module-identity/{_module_id(module)}",
        subject=_module_id(module),
        claim="requested exact module identity matches runtime",
        method=(
            VerificationMethod.STRUCTURED_API
            if identity_status is ObservationStatus.OBSERVED
            else VerificationMethod.NONE
        ),
        strength=(
            EvidenceStrength.CLAIM_DIRECT
            if identity_status is ObservationStatus.OBSERVED
            else EvidenceStrength.NONE
        ),
        source="physical_topology_runtime.observe_module_effect",
        freshness=(observation.freshness if observation else EvidenceFreshness.UNKNOWN),
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value={
            "requested_slot": module.slot,
            "requested_module": module.module,
            "observed_module_identity": observed_identity,
        },
        support_status=(
            SupportStatus.SUPPORTED
            if identity_status is ObservationStatus.OBSERVED
            else SupportStatus.PARTIAL
            if identity_status is ObservationStatus.UNOBSERVABLE
            else SupportStatus.UNKNOWN
        ),
        observation_status=identity_status,
        verification_status=(
            VerificationStatus.VERIFIED if identity_matches
            else VerificationStatus.FAILED
            if identity_status is ObservationStatus.OBSERVED
            else VerificationStatus.UNVERIFIED
        ),
        limitations=[limitation] if limitation else [],
    )


def _link_evidence(
    link: LinkPlan,
    observation: PhysicalLinkObservation | None,
    *,
    error: str,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    observed_value = observation.model_dump(mode="json") if observation else None
    runtime_completed = observation is not None and observation.observed
    unobservable = bool(error) and "unobservable" in error
    return EvidenceRecord(
        id=f"e4/link/{_link_id(link)}",
        subject=_link_id(link),
        claim="planned link peers and ports match runtime",
        method=VerificationMethod.STRUCTURED_API,
        strength=EvidenceStrength.CLAIM_DIRECT,
        source="physical_topology_runtime.observe_link",
        freshness=(EvidenceFreshness.FRESH if runtime_completed else EvidenceFreshness.UNKNOWN),
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value=observed_value,
        support_status=(SupportStatus.SUPPORTED if runtime_completed else SupportStatus.UNKNOWN),
        observation_status=(
            ObservationStatus.UNOBSERVABLE
            if unobservable
            else ObservationStatus.OBSERVED
            if runtime_completed
            else ObservationStatus.PROBE_FAILED
        ),
        verification_status=(
            VerificationStatus.VERIFIED
            if not error
            else VerificationStatus.UNVERIFIED
            if unobservable or not runtime_completed
            else VerificationStatus.FAILED
        ),
        limitations=[error] if error else [],
    )


def _link_cable_evidence(
    link: LinkPlan,
    observation: PhysicalLinkObservation,
    *,
    fingerprint: EnvironmentFingerprint,
) -> EvidenceRecord:
    limitation = (
        "Packet Tracer exposes the exact linked peers and ports, but no reliable "
        "getter for the semantic cable type."
    )
    return EvidenceRecord(
        id=f"e4/link-cable/{_link_id(link)}",
        subject=_link_id(link),
        claim="planned semantic cable type matches runtime",
        method=VerificationMethod.NONE,
        strength=EvidenceStrength.NONE,
        source="physical_topology_runtime.observe_link",
        freshness=EvidenceFreshness.FRESH,
        backend=fingerprint.backend,
        backend_version=fingerprint.backend_version,
        environment_fingerprint=fingerprint.semantic_hash,
        observed_value={
            "planned_cable": link.cable,
            "runtime_cable": observation.cable or None,
        },
        support_status=SupportStatus.UNKNOWN,
        observation_status=ObservationStatus.UNOBSERVABLE,
        verification_status=VerificationStatus.UNVERIFIED,
        limitations=[limitation],
    )


def _ordered_items(
    items: dict[tuple[PhysicalObjectKind, str], PhysicalDeploymentItemResult],
) -> list[PhysicalDeploymentItemResult]:
    return [items[key] for key in sorted(items, key=lambda item: (item[0].value, item[1]))]


def _result(
    *,
    topology: TopologyPlan,
    deployment_id: str,
    environment_fingerprint: EnvironmentFingerprint,
    failure_code: PhysicalDeploymentFailureCode,
    item_results: dict[tuple[PhysicalObjectKind, str], PhysicalDeploymentItemResult],
    evidence: Sequence[EvidenceRecord],
    journal: ApplicationExecutionJournal,
    errors: Sequence[str],
) -> PhysicalDeploymentResult:
    partial = any(
        item.applied or item.observed or item.status is PhysicalDeploymentItemStatus.SATISFIED
        for item in item_results.values()
    )
    return PhysicalDeploymentResult(
        topology_id=topology.id or topology.name,
        physical_topology_hash=topology.physical_identity_hash,
        deployment_id=deployment_id,
        environment_fingerprint=environment_fingerprint,
        status=(PhysicalDeploymentStatus.PARTIAL if partial else PhysicalDeploymentStatus.FAILED),
        failure_code=failure_code,
        item_results=_ordered_items(item_results),
        execution_journal=journal,
        dirty_state=journal.dirty_state,
        evidence_records=list(evidence),
        errors=list(errors),
    )
