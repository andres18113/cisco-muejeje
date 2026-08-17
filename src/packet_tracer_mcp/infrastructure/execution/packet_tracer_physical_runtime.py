"""Packet Tracer adapter for verified E4 physical deployment.

The adapter reuses the trusted PTBuilder renderers and requires independent
read-back for devices, ports and both ends of every link.  One instance is
bound to one caller-provided transport callback, so ambiguous mutations are
never replayed on a different bridge channel.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import json

from ...domain.enterprise.models.deployment import runtime_target_fingerprint
from ...domain.enterprise.models.evidence import (
    EvidenceFreshness,
    ObservationStatus,
    SupportStatus,
)
from ...domain.enterprise.models.execution import MutationDisposition
from ...domain.enterprise.models.physical_deployment import (
    PhysicalDeviceObservation,
    PhysicalLinkObservation,
    PhysicalModuleEffectCapability,
    PhysicalModuleObservation,
    PhysicalModuleSlotObservation,
    PhysicalMutationResult,
    PhysicalObjectKind,
    PhysicalWorkspaceDeviceObservation,
    PhysicalWorkspaceLinkObservation,
    PhysicalWorkspaceObservation,
)
from ...domain.models.plans import DevicePlan, LinkPlan, ModulePlan
from ..catalog.modules import resolve_module
from ..generator.ptbuilder_generator import (
    generate_device_command,
    generate_link_command,
    generate_module_command,
)
from .topology_observation import (
    LinkEndpoint,
    LinkExpectation,
    LinkObservationStatus,
    build_exact_link_readback_js,
    parse_exact_link_readback,
    verify_exact_link_convergence,
)


SendAndWait = Callable[[str, float], str | None]


class _MutationAckStatus(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class _ObservedModuleSlot:
    observed_module_number: str = ""
    slot_type_code: str = ""
    port_count: int | None = None
    observed_module_identity: str = ""
    identity_observable: bool = False


@dataclass(frozen=True)
class _ModuleRuntimeState:
    observed: bool
    device_name: str = ""
    model: str = ""
    ports: tuple[str, ...] = ()
    slots: tuple[_ObservedModuleSlot, ...] = ()
    module_tree_observed: bool = False
    message: str = ""


class PacketTracerPhysicalTopologyRuntime:
    """Production Packet Tracer implementation of ``PhysicalTopologyRuntime``."""

    def __init__(
        self,
        send_and_wait: SendAndWait,
        *,
        mutation_timeout_seconds: float = 5.0,
        observation_timeout_seconds: float = 4.0,
    ) -> None:
        self._send_and_wait = send_and_wait
        self._mutation_timeout_seconds = max(0.1, mutation_timeout_seconds)
        self._observation_timeout_seconds = max(0.1, observation_timeout_seconds)
        self._module_baselines: dict[str, _ModuleRuntimeState] = {}
        self._owned_new_devices: set[str] = set()

    def ensure_device(self, device: DevicePlan) -> PhysicalMutationResult:
        target_id = _device_id(device)
        observation = self.observe_device(device)
        if observation.observed:
            if observation.model != device.model:
                return _failure(
                    target_id,
                    PhysicalObjectKind.DEVICE,
                    f"Existing device {device.name!r} has model "
                    f"{observation.model!r}, expected {device.model!r}.",
                )
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.DEVICE,
                disposition=MutationDisposition.NO_OP,
                message="Exact device identity already exists.",
            )
        if observation.message != "not_found":
            return _failure(
                target_id,
                PhysicalObjectKind.DEVICE,
                "Device pre-readback was inconclusive: " + observation.message,
            )
        ack_status, ack_message = self._mutation_ack(generate_device_command(device))
        if ack_status is _MutationAckStatus.UNKNOWN:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.DEVICE,
                disposition=MutationDisposition.UNKNOWN,
                message=(
                    f"Device creation outcome for {device.name!r} is ambiguous; "
                    f"the mutation will not be replayed. {ack_message}"
                ).strip(),
            )
        if ack_status is _MutationAckStatus.REJECTED:
            return _failure(
                target_id,
                PhysicalObjectKind.DEVICE,
                f"Packet Tracer rejected creation of {device.name!r}: {ack_message}",
            )
        self._owned_new_devices.add(device.name)
        return PhysicalMutationResult(
            target_id=target_id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            inverse_available=True,
            inverse_action_id=f"remove-device:{target_id}",
            message="Device creation acknowledged; independent read-back required.",
        )

    def observe_device(self, device: DevicePlan) -> PhysicalDeviceObservation:
        target_id = _device_id(device)
        raw = self._send_and_wait(
            _device_observation_js(device.name),
            self._observation_timeout_seconds,
        )
        payload = _json_object(raw)
        if payload is None:
            return PhysicalDeviceObservation(
                target_id=target_id,
                observed=False,
                deployed_name=device.name,
                model="",
                interfaces_observed=False,
                message="timeout_or_malformed_response",
            )
        if payload.get("found") is not True:
            return PhysicalDeviceObservation(
                target_id=target_id,
                observed=False,
                deployed_name=device.name,
                model="",
                interfaces_observed=False,
                message="not_found",
            )
        name = payload.get("name")
        model = payload.get("model")
        ports = payload.get("ports")
        if not isinstance(name, str) or not isinstance(model, str) or not isinstance(ports, list):
            return PhysicalDeviceObservation(
                target_id=target_id,
                observed=False,
                deployed_name=device.name,
                model="",
                interfaces_observed=False,
                message="malformed_device_observation",
            )
        interfaces = sorted({item for item in ports if isinstance(item, str)})
        if len(interfaces) != len(ports):
            return PhysicalDeviceObservation(
                target_id=target_id,
                observed=False,
                deployed_name=name,
                model=model,
                interfaces=interfaces,
                interfaces_observed=False,
                message="malformed_port_inventory",
            )
        return PhysicalDeviceObservation(
            target_id=target_id,
            deployed_name=name,
            model=model,
            interfaces=interfaces,
            interfaces_observed=True,
            runtime_identifier="",
            runtime_identifier_stable=False,
            runtime_fingerprint=runtime_target_fingerprint(name, model, interfaces),
            message="fresh_packet_tracer_readback",
        )

    def remove_device(self, device: DevicePlan) -> PhysicalMutationResult:
        """Remove only the exact disposable device identity supplied by caller."""

        target_id = _device_id(device)
        observation = self.observe_device(device)
        if not observation.observed:
            if observation.message == "not_found":
                return PhysicalMutationResult(
                    target_id=target_id,
                    target_kind=PhysicalObjectKind.DEVICE,
                    disposition=MutationDisposition.NO_OP,
                    message="Exact disposable device is already absent.",
                )
            return _failure(
                target_id,
                PhysicalObjectKind.DEVICE,
                "Cleanup pre-readback was inconclusive: " + observation.message,
            )
        if observation.deployed_name != device.name or observation.model != device.model:
            return _failure(
                target_id,
                PhysicalObjectKind.DEVICE,
                "Refusing cleanup because the observed name/model does not match "
                "the exact disposable device identity.",
            )
        ack_status, ack_message = self._mutation_ack(_remove_device_command(device))
        if ack_status is _MutationAckStatus.UNKNOWN:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.DEVICE,
                disposition=MutationDisposition.UNKNOWN,
                message=(
                    f"Cleanup outcome for {device.name!r} is ambiguous and will not "
                    f"be replayed. {ack_message}"
                ).strip(),
            )
        if ack_status is _MutationAckStatus.REJECTED:
            return _failure(
                target_id,
                PhysicalObjectKind.DEVICE,
                f"Packet Tracer rejected exact device cleanup: {ack_message}",
            )
        self._owned_new_devices.discard(device.name)
        return PhysicalMutationResult(
            target_id=target_id,
            target_kind=PhysicalObjectKind.DEVICE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            message="Exact disposable device cleanup was acknowledged.",
        )

    def supports_module_observation(self) -> bool:
        """Packet Tracer has no verified exact module/slot getter in this backend."""

        return False

    def observe_workspace(self) -> PhysicalWorkspaceObservation:
        """Inventory the whole workspace without mutating Packet Tracer."""

        raw = self._send_and_wait(
            _workspace_observation_js(),
            self._observation_timeout_seconds,
        )
        payload = _json_object(raw)
        if payload is None:
            return PhysicalWorkspaceObservation(
                observed=False,
                message="timeout_or_malformed_workspace_response",
            )
        inventory_error = payload.get("inventory_error")
        if isinstance(inventory_error, str) and inventory_error:
            return PhysicalWorkspaceObservation(
                observed=False,
                message="workspace_inventory_error: " + inventory_error,
            )
        raw_devices = payload.get("items")
        raw_links = payload.get("links")
        if not isinstance(raw_devices, list) or not isinstance(raw_links, list):
            return PhysicalWorkspaceObservation(
                observed=False,
                message="malformed_workspace_inventory",
            )

        devices: list[PhysicalWorkspaceDeviceObservation] = []
        links: list[PhysicalWorkspaceLinkObservation] = []
        for item in raw_devices:
            if not isinstance(item, dict) or item.get("unreadable") is True:
                return PhysicalWorkspaceObservation(
                    observed=False,
                    devices=devices,
                    links=links,
                    message="unreadable_workspace_device",
                )
            name = item.get("name")
            model = item.get("model")
            ports = item.get("ports")
            if (
                item.get("kind") != "device"
                or not isinstance(name, str)
                or not isinstance(model, str)
                or not isinstance(ports, list)
                or any(not isinstance(port, str) for port in ports)
            ):
                return PhysicalWorkspaceObservation(
                    observed=False,
                    devices=devices,
                    links=links,
                    message="malformed_workspace_device",
                )
            normalized_ports = sorted(set(ports), key=str.casefold)
            devices.append(PhysicalWorkspaceDeviceObservation(
                name=name,
                model=model,
                ports=normalized_ports,
                backend_managed=(
                    model.strip().casefold() == "power distribution device"
                    and not normalized_ports
                ),
            ))

        for item in raw_links:
            if not isinstance(item, dict) or item.get("unreadable") is True:
                return PhysicalWorkspaceObservation(
                    observed=False,
                    devices=devices,
                    links=links,
                    message="unreadable_workspace_link",
                )
            values = [
                item.get("class_name"), item.get("a_device"), item.get("a_port"),
                item.get("b_device"), item.get("b_port"),
            ]
            if item.get("kind") != "link" or any(
                not isinstance(value, str) for value in values
            ):
                return PhysicalWorkspaceObservation(
                    observed=False,
                    devices=devices,
                    links=links,
                    message="malformed_workspace_link",
                )
            class_name, device_a, port_a, device_b, port_b = values
            links.append(PhysicalWorkspaceLinkObservation(
                class_name=class_name,
                device_a=device_a,
                port_a=port_a,
                device_b=device_b,
                port_b=port_b,
            ))

        return PhysicalWorkspaceObservation(
            devices=sorted(devices, key=lambda item: item.identity_key()),
            links=sorted(links, key=lambda item: item.identity_key()),
            message="fresh_complete_workspace_inventory",
        )

    def module_effect_capability(
        self,
        module: ModulePlan,
        device: DevicePlan,
    ) -> PhysicalModuleEffectCapability:
        """Describe the narrow effect proof available for a catalogued module."""

        target_id = _module_id(module)
        spec = resolve_module(module.module)
        if spec is None:
            return PhysicalModuleEffectCapability(
                target_id=target_id,
                operation_support=SupportStatus.UNSUPPORTED,
                effect_observation_support=SupportStatus.UNKNOWN,
                identity_observation_status=ObservationStatus.UNOBSERVABLE,
                message=f"Module {module.module!r} is absent from the trusted catalog.",
            )
        if spec.compatible_with and device.model not in spec.compatible_with:
            return PhysicalModuleEffectCapability(
                target_id=target_id,
                operation_support=SupportStatus.UNSUPPORTED,
                effect_observation_support=SupportStatus.UNKNOWN,
                identity_observation_status=ObservationStatus.UNOBSERVABLE,
                message=(
                    f"Module {module.module!r} is not catalogued for model "
                    f"{device.model!r}."
                ),
            )
        expected_ports = sorted(set(spec.ports_added), key=str.casefold)
        if not expected_ports:
            return PhysicalModuleEffectCapability(
                target_id=target_id,
                operation_support=SupportStatus.SUPPORTED,
                effect_observation_support=SupportStatus.UNSUPPORTED,
                identity_observation_status=ObservationStatus.UNOBSERVABLE,
                message="This module has no catalogued port effect that can be verified safely.",
            )
        if not _expected_ports_match_requested_slot(expected_ports, module.slot):
            return PhysicalModuleEffectCapability(
                target_id=target_id,
                operation_support=SupportStatus.SUPPORTED,
                effect_observation_support=SupportStatus.UNSUPPORTED,
                expected_ports=expected_ports,
                expected_port_classes=_port_classes(expected_ports),
                identity_observation_status=ObservationStatus.UNOBSERVABLE,
                message=(
                    "The catalogued port names do not prove an effect in the "
                    "requested slot namespace; mutation is refused."
                ),
            )
        return PhysicalModuleEffectCapability(
            target_id=target_id,
            operation_support=SupportStatus.SUPPORTED,
            effect_observation_support=SupportStatus.SUPPORTED,
            expected_ports=expected_ports,
            expected_port_classes=_port_classes(expected_ports),
            identity_observation_status=ObservationStatus.UNOBSERVABLE,
            message=(
                "Packet Tracer can verify fresh port effects; exact installed "
                "module identity remains unobservable."
            ),
        )

    def ensure_module(self, module: ModulePlan) -> PhysicalMutationResult:
        """Ensure a catalogued module effect without replaying ambiguous mutation."""

        target_id = _module_id(module)
        spec = resolve_module(module.module)
        if spec is None or not spec.ports_added:
            return _failure(
                target_id,
                PhysicalObjectKind.MODULE,
                "Module has no trusted catalogued port effect.",
            )
        if not _expected_ports_match_requested_slot(spec.ports_added, module.slot):
            return _failure(
                target_id,
                PhysicalObjectKind.MODULE,
                "Catalogued port effects do not match the requested slot namespace.",
            )
        before = self._read_module_state(module.device)
        if not before.observed:
            return _failure(
                target_id,
                PhysicalObjectKind.MODULE,
                "Module pre-readback was inconclusive: " + before.message,
            )
        if spec.compatible_with and before.model not in spec.compatible_with:
            return _failure(
                target_id,
                PhysicalObjectKind.MODULE,
                f"Device model {before.model!r} is incompatible with {module.module!r}.",
            )

        self._module_baselines[target_id] = before
        expected = set(spec.ports_added)
        slot_ports = set(_ports_in_requested_slot(before.ports, module.slot))
        present = expected.intersection(slot_ports)
        if slot_ports == expected:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.MODULE,
                disposition=MutationDisposition.NO_OP,
                message=(
                    "The complete requested module port effect already exists; "
                    "exact installed identity remains unobservable."
                ),
            )
        if present and slot_ports.issubset(expected):
            return _failure(
                target_id,
                PhysicalObjectKind.MODULE,
                "A partial requested module port effect already exists; refusing to overwrite it.",
            )

        if slot_ports:
            return _failure(
                target_id,
                PhysicalObjectKind.MODULE,
                "A conflicting or superset effect exists in the requested slot; "
                "refusing to mutate it.",
            )
        if module.device not in self._owned_new_devices:
            return _failure(
                target_id,
                PhysicalObjectKind.MODULE,
                "Slot emptiness is not independently proven by an owned new-device "
                "transaction; module insertion is refused.",
            )

        ack_status, ack_message, changed = self._module_mutation_ack(
            generate_module_command(
                module,
                expected_ports=spec.ports_added,
                slot_empty_proven=True,
            )
        )
        if ack_status is _MutationAckStatus.UNKNOWN:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.MODULE,
                disposition=MutationDisposition.UNKNOWN,
                message=(
                    f"Module insertion outcome for {target_id!r} is ambiguous; "
                    f"the mutation will not be replayed. {ack_message}"
                ).strip(),
            )
        if ack_status is _MutationAckStatus.REJECTED:
            return _failure(
                target_id,
                PhysicalObjectKind.MODULE,
                f"Packet Tracer rejected module insertion for {target_id!r}: {ack_message}",
            )
        if changed is False:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.MODULE,
                disposition=MutationDisposition.NO_OP,
                message=(
                    "The guarded payload observed the complete module port effect "
                    "without invoking native insertion; identity remains unobservable."
                ),
            )
        return PhysicalMutationResult(
            target_id=target_id,
            target_kind=PhysicalObjectKind.MODULE,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            message="Module insertion acknowledged; independent port-effect read-back required.",
        )

    def observe_module_effect(self, module: ModulePlan) -> PhysicalModuleObservation:
        """Read a fresh port inventory and keep requested and observed identity separate."""

        target_id = _module_id(module)
        baseline = self._module_baselines.get(target_id)
        if baseline is None:
            return PhysicalModuleObservation(
                target_id=target_id,
                observed=False,
                device_name=module.device,
                requested_slot=module.slot,
                requested_module=module.module,
                message="module_effect_baseline_unavailable",
            )
        spec = resolve_module(module.module)
        if spec is None or not spec.ports_added:
            return PhysicalModuleObservation(
                target_id=target_id,
                observed=False,
                device_name=module.device,
                requested_slot=module.slot,
                requested_module=module.module,
                message="module_effect_catalog_unavailable",
            )
        after = self._read_module_state(module.device)
        if not after.observed:
            return PhysicalModuleObservation(
                target_id=target_id,
                observed=False,
                device_name=module.device,
                requested_slot=module.slot,
                requested_module=module.module,
                ports_before=list(baseline.ports),
                message="module_effect_readback_failed:" + after.message,
            )

        expected_ports = sorted(set(spec.ports_added), key=str.casefold)
        expected_set = set(expected_ports)
        after_set = set(after.ports)
        observed_expected = sorted(expected_set.intersection(after_set), key=str.casefold)
        added = sorted(after_set.difference(baseline.ports), key=str.casefold)
        observed_classes = _port_classes(observed_expected)
        expected_classes = _port_classes(expected_ports)

        matching_slots = [
            item for item in after.slots
            if item.observed_module_number == module.slot and item.identity_observable
        ]
        observed_identity = (
            matching_slots[0].observed_module_identity
            if len(matching_slots) == 1 else ""
        )
        identity_status = (
            ObservationStatus.OBSERVED
            if observed_identity else ObservationStatus.UNOBSERVABLE
        )
        slot_ports_after = set(_ports_in_requested_slot(after.ports, module.slot))
        effect_observed = (
            slot_ports_after == expected_set
            and set(expected_classes).issubset(observed_classes)
        )
        slot_effect_observed = bool(
            effect_observed
            and after.module_tree_observed
            and any(
                item.observed_module_number == module.slot
                for item in after.slots
            )
        )
        return PhysicalModuleObservation(
            target_id=target_id,
            device_name=after.device_name,
            requested_slot=module.slot,
            requested_module=module.module,
            freshness=EvidenceFreshness.FRESH,
            port_inventory_observed=True,
            expected_ports=expected_ports,
            expected_port_classes=expected_classes,
            ports_before=list(baseline.ports),
            ports_after=list(after.ports),
            observed_expected_ports=observed_expected,
            added_ports=added,
            observed_port_classes=observed_classes,
            slot_observations=[
                PhysicalModuleSlotObservation(
                    observed_module_number=item.observed_module_number,
                    slot_type_code=item.slot_type_code,
                    port_count=item.port_count,
                    observed_module_identity=item.observed_module_identity,
                    identity_observable=item.identity_observable,
                )
                for item in after.slots
            ],
            slot_effect_observed=slot_effect_observed,
            effect_observed=effect_observed,
            identity_observation_status=identity_status,
            observed_module_identity=observed_identity,
            message="fresh_packet_tracer_module_port_effect_readback",
        )

    def _read_module_state(self, device_name: str) -> _ModuleRuntimeState:
        raw = self._send_and_wait(
            _module_effect_observation_js(device_name),
            self._observation_timeout_seconds,
        )
        payload = _json_object(raw)
        if payload is None:
            return _ModuleRuntimeState(
                observed=False,
                device_name=device_name,
                message="timeout_or_malformed_response",
            )
        if payload.get("found") is not True:
            error = payload.get("error")
            return _ModuleRuntimeState(
                observed=False,
                device_name=device_name,
                message=(
                    str(error) if isinstance(error, str) and error else "not_found"
                ),
            )
        name = payload.get("name")
        model = payload.get("model")
        ports = payload.get("ports")
        modules = payload.get("modules")
        modules_observed = payload.get("modules_observed")
        if (
            not isinstance(name, str)
            or not isinstance(model, str)
            or not isinstance(ports, list)
            or not isinstance(modules, list)
            or not isinstance(modules_observed, bool)
            or any(not isinstance(item, str) for item in ports)
        ):
            return _ModuleRuntimeState(
                observed=False,
                device_name=device_name,
                message="malformed_module_effect_observation",
            )
        slots: list[_ObservedModuleSlot] = []
        for item in modules:
            if not isinstance(item, dict):
                return _ModuleRuntimeState(
                    observed=False,
                    device_name=device_name,
                    message="malformed_module_tree_observation",
                )
            number = item.get("observed_module_number")
            slot_type = item.get("slot_type_code")
            port_count = item.get("port_count")
            raw_identity = item.get("observed_module_identity")
            if number is not None and not isinstance(number, str):
                return _ModuleRuntimeState(
                    observed=False,
                    device_name=device_name,
                    message="malformed_module_number_observation",
                )
            if slot_type is not None and not isinstance(slot_type, str):
                return _ModuleRuntimeState(
                    observed=False,
                    device_name=device_name,
                    message="malformed_module_slot_type_observation",
                )
            if (
                port_count is not None
                and (isinstance(port_count, bool) or not isinstance(port_count, (int, float)))
            ):
                return _ModuleRuntimeState(
                    observed=False,
                    device_name=device_name,
                    message="malformed_module_port_count_observation",
                )
            identity = _observable_module_identity(raw_identity)
            slots.append(_ObservedModuleSlot(
                observed_module_number=number or "",
                slot_type_code=slot_type or "",
                port_count=(int(port_count) if port_count is not None else None),
                observed_module_identity=identity,
                identity_observable=bool(identity),
            ))
        return _ModuleRuntimeState(
            observed=True,
            device_name=name,
            model=model,
            ports=tuple(sorted(set(ports), key=str.casefold)),
            slots=tuple(slots),
            module_tree_observed=modules_observed,
            message="fresh_packet_tracer_module_state",
        )

    def ensure_link(self, link: LinkPlan) -> PhysicalMutationResult:
        target_id = _link_id(link)
        expectation = _link_expectation(link)
        precheck = parse_exact_link_readback(
            self._send_and_wait(
                build_exact_link_readback_js(expectation),
                self._observation_timeout_seconds,
            )
        )
        if precheck.exact:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.LINK,
                disposition=MutationDisposition.NO_OP,
                message="Exact two-ended link already exists.",
            )
        if precheck.port_a_bound or precheck.port_b_bound:
            return _failure(
                target_id,
                PhysicalObjectKind.LINK,
                "A planned endpoint is already bound to a different or unreadable link.",
            )
        if precheck.status is not LinkObservationStatus.NO_LINK:
            return _failure(
                target_id,
                PhysicalObjectKind.LINK,
                "Link pre-readback is not safe for mutation: " + precheck.status.value,
            )
        ack_status, ack_message = self._mutation_ack(generate_link_command(link))
        if ack_status is _MutationAckStatus.UNKNOWN:
            return PhysicalMutationResult(
                target_id=target_id,
                target_kind=PhysicalObjectKind.LINK,
                disposition=MutationDisposition.UNKNOWN,
                message=(
                    f"Link creation outcome for {target_id!r} is ambiguous; "
                    f"the mutation will not be replayed. {ack_message}"
                ).strip(),
            )
        if ack_status is _MutationAckStatus.REJECTED:
            return _failure(
                target_id,
                PhysicalObjectKind.LINK,
                f"Packet Tracer rejected creation of link {target_id!r}: {ack_message}",
            )
        return PhysicalMutationResult(
            target_id=target_id,
            target_kind=PhysicalObjectKind.LINK,
            disposition=MutationDisposition.CHANGED,
            applied=True,
            message="Link creation acknowledged; exact two-ended read-back required.",
        )

    def observe_link(self, link: LinkPlan) -> PhysicalLinkObservation:
        target_id = _link_id(link)
        convergence = verify_exact_link_convergence(
            self._send_and_wait,
            _link_expectation(link),
            timeout_seconds=self._observation_timeout_seconds,
        )
        observed_endpoints = convergence.observation.observed_link_a
        if convergence.verified and len(observed_endpoints) == 2:
            device_a = observed_endpoints[0].device
            port_a = observed_endpoints[0].port
            device_b = observed_endpoints[1].device
            port_b = observed_endpoints[1].port
        else:
            device_a, port_a = link.device_a, link.port_a
            device_b, port_b = link.device_b, link.port_b
        identifier_a = convergence.observation.runtime_link_identifier_a
        identifier_b = convergence.observation.runtime_link_identifier_b
        identifier_observed = bool(
            convergence.verified
            and identifier_a
            and identifier_a == identifier_b
        )
        return PhysicalLinkObservation(
            target_id=target_id,
            observed=convergence.verified,
            device_a=device_a,
            port_a=port_a,
            device_b=device_b,
            port_b=port_b,
            cable="",
            cable_observed=False,
            runtime_link_identifier=(identifier_a if identifier_observed else ""),
            runtime_link_identity_observed=identifier_observed,
            message=(
                "fresh_exact_two_ended_readback"
                if convergence.verified
                else "link_readback_" + convergence.observation.status.value.casefold()
            ),
        )

    def _mutation_ack(
        self,
        trusted_command: str,
    ) -> tuple[_MutationAckStatus, str]:
        script = (
            "try{" + trusted_command
            + "reportResult(JSON.stringify({ack:true}));}"
            + "catch(__e){reportResult(JSON.stringify({ack:false,error:String(__e)}));}"
        )
        raw = self._send_and_wait(script, self._mutation_timeout_seconds)
        payload = _json_object(raw)
        if payload is None:
            return (
                _MutationAckStatus.UNKNOWN,
                "The bridge returned no well-formed mutation acknowledgement.",
            )
        if payload.get("ack") is True:
            return _MutationAckStatus.ACKNOWLEDGED, ""
        if payload.get("ack") is False:
            error = payload.get("error")
            return (
                _MutationAckStatus.REJECTED,
                error if isinstance(error, str) and error else "explicit negative acknowledgement",
            )
        return (
            _MutationAckStatus.UNKNOWN,
            "The bridge response did not contain an explicit acknowledgement.",
        )

    def _module_mutation_ack(
        self,
        trusted_command: str,
    ) -> tuple[_MutationAckStatus, str, bool | None]:
        script = (
            "try{" + trusted_command
            + "reportResult(JSON.stringify(__mcpModuleMutationReceipt));}"
            + "catch(__e){reportResult(JSON.stringify({ack:false,error:String(__e)}));}"
        )
        raw = self._send_and_wait(script, self._mutation_timeout_seconds)
        payload = _json_object(raw)
        if payload is None:
            return (
                _MutationAckStatus.UNKNOWN,
                "The bridge returned no well-formed module receipt.",
                None,
            )
        if payload.get("ack") is True and isinstance(payload.get("changed"), bool):
            outcome = payload.get("outcome")
            return (
                _MutationAckStatus.ACKNOWLEDGED,
                outcome if isinstance(outcome, str) else "",
                bool(payload["changed"]),
            )
        if payload.get("ack") is False:
            error = payload.get("error")
            return (
                _MutationAckStatus.REJECTED,
                error if isinstance(error, str) and error else "explicit negative receipt",
                False,
            )
        return (
            _MutationAckStatus.UNKNOWN,
            "The module receipt did not contain typed ack/changed fields.",
            None,
        )


def _remove_device_command(device: DevicePlan) -> str:
    """Build checked cleanup JavaScript from serialized caller-controlled fields."""

    name = json.dumps(device.name, ensure_ascii=False)
    model = json.dumps(device.model, ensure_ascii=False)
    return (
        "var __cleanupName=" + name + ",__cleanupModel=" + model + ";"
        "var __cleanupDevice=ipc.network().getDevice(__cleanupName);"
        "if(!__cleanupDevice){throw new Error('cleanup target disappeared before mutation');}"
        "var __observedCleanupModel=(typeof __cleanupDevice.getModel==='function'"
        "?String(__cleanupDevice.getModel()):'');"
        "if(String(__cleanupDevice.getName())!==__cleanupName||"
        "__observedCleanupModel!==__cleanupModel){"
        "throw new Error('cleanup identity changed before mutation');}"
        "var __logicalWorkspace=ipc.appWindow().getActiveWorkspace().getLogicalWorkspace();"
        "if(typeof __logicalWorkspace.removeDevice!=='function'){"
        "throw new Error('removeDevice unavailable');}"
        "__logicalWorkspace.removeDevice(__cleanupName);"
        "if(ipc.network().getDevice(__cleanupName)){"
        "throw new Error('cleanup target still present');}"
    )


def _workspace_observation_js() -> str:
    """Build the strict read-only inventory used by the live safety gate."""

    return (
        "try{var __n=ipc.network(),__items=[],__links=[];"
        "for(var __i=0;__i<__n.getDeviceCount();__i++){try{"
        "var __d=__n.getDeviceAt(__i);if(!__d){throw new Error('missing device');}"
        "var __ports=[];for(var __p=0;__p<__d.getPortCount();__p++){"
        "var __port=__d.getPortAt(__p);if(!__port){throw new Error('missing port');}"
        "__ports.push(String(__port.getName()));}"
        "__items.push({kind:'device',name:String(__d.getName()),"
        "model:(typeof __d.getModel==='function'?String(__d.getModel()):''),"
        "ports:__ports});}catch(__de){__items.push({kind:'device',index:__i,"
        "unreadable:true,error:String(__de)});}}"
        "for(var __l=0;__l<__n.getLinkCount();__l++){try{"
        "var __link=__n.getLinkAt(__l);if(!__link){throw new Error('missing link');}"
        "if(typeof __link.getPort1!=='function'||typeof __link.getPort2!=='function'){"
        "throw new Error('link endpoints unavailable');}"
        "var __p1=__link.getPort1(),__p2=__link.getPort2();"
        "if(!__p1||!__p2){throw new Error('missing link endpoint');}"
        "__links.push({kind:'link',"
        "class_name:(typeof __link.getClassName==='function'?String(__link.getClassName()):''),"
        "a_device:String(__p1.getOwnerDevice().getName()),a_port:String(__p1.getName()),"
        "b_device:String(__p2.getOwnerDevice().getName()),b_port:String(__p2.getName())});}"
        "catch(__le){__links.push({kind:'link',index:__l,unreadable:true,"
        "error:String(__le)});}}"
        "reportResult(JSON.stringify({items:__items,links:__links}));}"
        "catch(__e){reportResult(JSON.stringify({inventory_error:String(__e)}));}"
    )


def _device_observation_js(device_name: str) -> str:
    name = json.dumps(device_name, ensure_ascii=False)
    return (
        "try{var __d=ipc.network().getDevice(" + name + ");"
        "if(!__d){reportResult(JSON.stringify({found:false}));}else{"
        "var __ports=[];for(var __i=0;__i<__d.getPortCount();__i++){"
        "var __p=__d.getPortAt(__i);if(__p){__ports.push(String(__p.getName()));}}"
        "reportResult(JSON.stringify({found:true,name:String(__d.getName()),"
        "model:(typeof __d.getModel==='function'?String(__d.getModel()):''),"
        "ports:__ports}));}}catch(__e){"
        "reportResult(JSON.stringify({found:false,error:String(__e)}));}"
    )


def _module_effect_observation_js(device_name: str) -> str:
    """Build read-only module-tree and device-port observation JavaScript."""

    name = json.dumps(device_name, ensure_ascii=False)
    return (
        "try{var __d=ipc.network().getDevice(" + name + ");"
        "if(!__d){reportResult(JSON.stringify({found:false}));}else{"
        "var __ports=[];for(var __i=0;__i<__d.getPortCount();__i++){"
        "var __p=__d.getPortAt(__i);if(__p){__ports.push(String(__p.getName()));}}"
        "var __mods=[],__modsObserved=false;try{var __root=__d.getRootModule();"
        "if(__root){__modsObserved=true;for(var __s=0;__s<__root.getModuleCount();__s++){"
        "var __m=__root.getModuleAt(__s);if(!__m){continue;}var __entry={};"
        "try{__entry.observed_module_identity=String(__m.getModuleNameAsString());}"
        "catch(__me){__entry.observed_module_identity='';}"
        "try{__entry.observed_module_number=String(__m.getModuleNumber());}"
        "catch(__me){__entry.observed_module_number='';}"
        "try{__entry.slot_type_code=String(__root.getSlotTypeAt(__s));}"
        "catch(__me){__entry.slot_type_code='';}"
        "try{__entry.port_count=Number(__m.getPortCount());}"
        "catch(__me){__entry.port_count=null;}__mods.push(__entry);}}}catch(__re){}"
        "reportResult(JSON.stringify({found:true,name:String(__d.getName()),"
        "model:(typeof __d.getModel==='function'?String(__d.getModel()):''),"
        "ports:__ports,modules_observed:__modsObserved,modules:__mods}));}}"
        "catch(__e){reportResult(JSON.stringify({found:false,error:String(__e)}));}"
    )


def _json_object(raw: str | None) -> dict[str, object] | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _link_expectation(link: LinkPlan) -> LinkExpectation:
    return LinkExpectation(
        endpoint_a=LinkEndpoint(link.device_a, link.port_a),
        endpoint_b=LinkEndpoint(link.device_b, link.port_b),
    )


def _device_id(device: DevicePlan) -> str:
    return device.id or device.name


def _module_id(module: ModulePlan) -> str:
    return f"{module.device}:{module.slot}:{module.module}"


def _link_id(link: LinkPlan) -> str:
    return link.id or (
        f"{link.device_a}:{link.port_a}->{link.device_b}:{link.port_b}"
    )


def _observable_module_identity(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    if normalized.casefold() in {"", "none", "null"}:
        return ""
    return normalized


def _port_classes(ports: list[str] | tuple[str, ...]) -> list[str]:
    classes: set[str] = set()
    for port in ports:
        lowered = port.casefold()
        if lowered.startswith("serial"):
            classes.add("serial")
        elif "ethernet" in lowered:
            classes.add("ethernet")
        elif lowered.startswith("async"):
            classes.add("async")
        elif lowered.startswith("modem"):
            classes.add("modem")
        else:
            classes.add("other")
    return sorted(classes)


def _expected_ports_match_requested_slot(
    ports: list[str] | tuple[str, ...],
    requested_slot: str,
) -> bool:
    """Require every catalogued interface name to encode the requested slot."""

    slot = requested_slot.strip()
    if not slot or not ports:
        return False
    for port in ports:
        first_digit = next(
            (index for index, character in enumerate(port) if character.isdigit()),
            -1,
        )
        if first_digit < 0:
            return False
        numeric_path = port[first_digit:]
        if "/" not in numeric_path or numeric_path.rsplit("/", 1)[0] != slot:
            return False
    return True


def _ports_in_requested_slot(
    ports: list[str] | tuple[str, ...],
    requested_slot: str,
) -> list[str]:
    """Return ports in the exact numeric namespace governed by one slot."""

    result: list[str] = []
    slot = requested_slot.strip()
    for port in ports:
        first_digit = next(
            (index for index, character in enumerate(port) if character.isdigit()),
            -1,
        )
        if first_digit < 0:
            continue
        numeric_path = port[first_digit:]
        if "/" in numeric_path and numeric_path.rsplit("/", 1)[0] == slot:
            result.append(port)
    return sorted(set(result), key=str.casefold)


def _failure(
    target_id: str,
    kind: PhysicalObjectKind,
    message: str,
) -> PhysicalMutationResult:
    return PhysicalMutationResult(
        target_id=target_id,
        target_kind=kind,
        disposition=MutationDisposition.FAILED,
        message=message,
    )
