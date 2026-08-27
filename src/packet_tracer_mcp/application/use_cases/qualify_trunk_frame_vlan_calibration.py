"""Calibrate ``getInFrame().vlanId`` on an independently read trunk ingress.

The expected VLAN is never borrowed from the opposite side of a forwarded
frame.  Each control uses one target-switch ingress trunk whose complete current
``show interfaces trunk`` readback proves an exact singleton allowed set, the
target active and forwarding/not-pruned, and a different native VLAN.  The
selected child is compared only after separately establishing its end-to-end
identity; source-to-target hop identity alone is insufficient.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from typing import Protocol

from ...domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigureAccessPort,
    ConfigureTrunk,
    CreateVlan,
    VerificationExpectation,
    VerificationKind,
)
from ...domain.enterprise.models.execution import MutationDisposition
from ...domain.enterprise.models.physical_deployment import (
    PhysicalWorkspaceObservation,
    physical_workspace_restoration_matches,
)
from ...domain.models.plans import DevicePlan, LinkPlan


TRUNK_CALIBRATION_PREFIX = "__MCP_TRUNKCAL_"
CONTROL_VLAN_IDS = (742, 743)
NATIVE_VLAN_ID = 1
TRACE_LIMIT = 200
MAX_ENUMERATED = len(CONTROL_VLAN_IDS)
TAG_FIELD_NAMES = ("vlanId", "tpid", "cfi", "userPriority")


def _finite_vlan(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value)).casefold()


@dataclass(frozen=True)
class TrunkVlanCalibrationControl:
    target_vlan_id: int
    switch_interface: str = ""
    source_switch_name: str = ""
    convergence_verified: bool = False
    readback_fresh: bool = False
    readback_complete: bool = False
    trunk_status: str = ""
    native_vlan: int | None = None
    allowed_vlans: tuple[int, ...] | None = None
    active_vlans: tuple[int, ...] | None = None
    forwarding_vlans: tuple[int, ...] | None = None
    endpoint_armed: bool = False
    frame_index: int | None = None
    frame_observed_in_port: str = ""
    frame_previous_device: str = ""
    source_to_target_hop_identity_reconfirmed: bool = False
    selected_frame_end_to_end_dhcp_identity_established: bool = False
    child_returned: bool = False
    child_members: tuple[str, ...] = ()
    tag_fields_present: tuple[str, ...] = ()
    observed_vlan: object = None
    failure_reason: str = ""

    @property
    def expected_vlan(self) -> int | None:
        """Return only the singleton VLAN established by all direct readbacks."""
        if not (
            self.convergence_verified
            and self.readback_fresh
            and self.readback_complete
            and self.trunk_status.casefold() == "trunking"
            and self.allowed_vlans is not None
            and len(self.allowed_vlans) == 1
        ):
            return None
        expected = self.allowed_vlans[0]
        if expected != self.target_vlan_id:
            return None
        if self.active_vlans != (expected,):
            return None
        if self.forwarding_vlans != (expected,):
            return None
        if self.native_vlan is None or self.native_vlan == expected:
            return None
        return expected

    @property
    def single_allowed_non_native_trunk_policy_proven(self) -> bool:
        return self.expected_vlan is not None

    @property
    def frame_entered_policy_qualified_trunk(self) -> bool:
        return bool(
            self.single_allowed_non_native_trunk_policy_proven
            and self.endpoint_armed
            and self.source_to_target_hop_identity_reconfirmed
        )

    @property
    def frame_admitted_for_target_vlan(self) -> bool:
        """Physical arrival is insufficient until the VLAN value matches."""
        return self.match == "YES"

    @property
    def match(self) -> str:
        expected = self.expected_vlan
        if (
            expected is None
            or not self.endpoint_armed
            or not self.source_to_target_hop_identity_reconfirmed
            or not self.selected_frame_end_to_end_dhcp_identity_established
        ):
            return "UNOBSERVABLE"
        observed = _finite_vlan(self.observed_vlan)
        if observed is None:
            return "UNOBSERVABLE"
        return "YES" if observed == expected else "NO"


@dataclass(frozen=True)
class TrunkFrameVlanCalibrationResult:
    model: str = ""
    source_switch_name: str = ""
    target_switch_name: str = ""
    controls: tuple[TrunkVlanCalibrationControl, ...] = ()
    baseline_inventory: PhysicalWorkspaceObservation | None = None
    final_inventory: PhysicalWorkspaceObservation | None = None
    workspace_restored: bool | None = None
    realtime_restored: bool | None = None
    owned_links: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    parallel_trunk_control_independence_established: bool = False

    @property
    def semantics(self) -> str:
        judged = [item for item in self.controls if item.match != "UNOBSERVABLE"]
        if any(item.match == "NO" for item in judged):
            return "CONTRADICTED_BY_CONTROL"
        matched = [item for item in judged if item.match == "YES"]
        if (
            self.parallel_trunk_control_independence_established
            and len(matched) >= 2
            and len({item.expected_vlan for item in matched}) >= 2
        ):
            return "STRONGLY_SUPPORTED_BY_MULTIVLAN_CONTROL"
        if matched:
            return "SUPPORTED_BY_CONTROL"
        return "DIRECT_PROPERTY_ONLY_NOT_GLOBALLY_QUALIFIED"


class CalibrationPhysicalRuntime(Protocol):
    def observe_workspace(self) -> PhysicalWorkspaceObservation: ...
    def ensure_device(self, device: DevicePlan): ...
    def observe_device(self, device: DevicePlan): ...
    def remove_device(self, device: DevicePlan): ...
    def ensure_link(self, link: LinkPlan): ...


class CalibrationConfigurationRuntime(Protocol):
    def apply_actions(self, actions) -> list: ...
    def verify(self, expectations) -> list: ...
    def read_trunk(self, device_name: str, interface: str): ...


class CalibrationEndpointRuntime(Protocol):
    def configure_endpoint_dhcp(
        self, device: str, interface: str = "FastEthernet0",
    ) -> bool: ...


class CalibrationSimulationRuntime(Protocol):
    def read_simulation_state(self): ...
    def set_simulation_mode(self, on: bool): ...
    def step(self, action: str = "forward", times: int = 1): ...
    def read_trace(self, limit: int = 200, device: str = ""): ...


class CalibrationFrameProbe(Protocol):
    def discover_frame_observers(self, indices, *, timeout: float = 10.0): ...


class TrunkFrameVlanCalibrationQualifier:
    """Run two owned singleton/non-native trunk-ingress controls."""

    def __init__(
        self,
        physical: CalibrationPhysicalRuntime,
        configuration: CalibrationConfigurationRuntime,
        endpoints: CalibrationEndpointRuntime,
        simulation: CalibrationSimulationRuntime,
        probe: CalibrationFrameProbe,
        *,
        name_token: str = "",
        step_batches: int = 6,
        step_batch_size: int = 40,
    ) -> None:
        self._physical = physical
        self._configuration = configuration
        self._endpoints = endpoints
        self._simulation = simulation
        self._probe = probe
        self._token = name_token or secrets.token_hex(3)
        self._step_batches = step_batches
        self._step_batch_size = step_batch_size

    def _switch_name(self, role: str) -> str:
        return f"{TRUNK_CALIBRATION_PREFIX}{self._token}_{role}"

    def _endpoint_name(self, position: int) -> str:
        return f"{TRUNK_CALIBRATION_PREFIX}{self._token}_PC{position}"

    def qualify(
        self,
        switch_model: str,
        endpoint_model: str,
        *,
        require_empty_workspace: bool = True,
    ) -> TrunkFrameVlanCalibrationResult:
        errors: list[str] = []
        try:
            baseline = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001
            return TrunkFrameVlanCalibrationResult(
                model=switch_model,
                errors=(f"Read-only workspace inventory failed: {exc}",),
            )
        if require_empty_workspace and not baseline.safe_for_disposable_mutation:
            return TrunkFrameVlanCalibrationResult(
                model=switch_model,
                baseline_inventory=baseline,
                errors=(
                    "The workspace inventory is not a complete empty baseline "
                    f"(observed={baseline.observed}, "
                    f"semantic_devices={len(baseline.semantic_devices)}, "
                    f"links={len(baseline.links)}); the calibration refuses to "
                    "mutate a workspace it did not find empty.",
                ),
            )

        created: list[DevicePlan] = []
        owned_links: list[str] = []
        controls: tuple[TrunkVlanCalibrationControl, ...] = ()
        original_simulation: bool | None = None
        try:
            original_simulation, controls, measured_errors = self._measure(
                switch_model, endpoint_model, created, owned_links,
            )
            errors.extend(measured_errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"calibration_raised: {type(exc).__name__}: {exc}")
        finally:
            realtime_restored, restore_errors = self._restore_mode(original_simulation)
            errors.extend(restore_errors)
            removed, cleanup_errors, final, restored = self._cleanup(created, baseline)
            errors.extend(cleanup_errors)

        return TrunkFrameVlanCalibrationResult(
            model=switch_model,
            source_switch_name=self._switch_name("TX"),
            target_switch_name=self._switch_name("RX"),
            controls=controls,
            baseline_inventory=baseline,
            final_inventory=final,
            workspace_restored=restored,
            realtime_restored=realtime_restored,
            owned_links=tuple(owned_links),
            removed=tuple(removed),
            errors=tuple(errors),
        )

    def _measure(
        self, switch_model: str, endpoint_model: str, created, owned_links,
    ):
        errors: list[str] = []
        source = DevicePlan(
            id="trunkcal/tx", name=self._switch_name("TX"), model=switch_model,
            category="", x=9000, y=9400,
        )
        target = DevicePlan(
            id="trunkcal/rx", name=self._switch_name("RX"), model=switch_model,
            category="", x=9600, y=9400,
        )
        for device in (source, target):
            if not self._create(device, created, errors):
                return None, (), errors

        source_ports = self._switch_ports(source, errors)
        target_ports = self._switch_ports(target, errors)
        if len(source_ports) < 4 or len(target_ports) < 2:
            errors.append(
                "The two disposable switches did not expose the four source "
                "and two target switchports required by the bounded control."
            )
            return None, (), errors
        source_access = source_ports[:2]
        source_trunks = source_ports[2:4]
        target_trunks = target_ports[:2]

        endpoints: list[tuple[str, str, int]] = []
        for position, vlan_id in enumerate(CONTROL_VLAN_IDS):
            endpoint = DevicePlan(
                id=f"trunkcal/pc{position}",
                name=self._endpoint_name(position),
                model=endpoint_model,
                category="",
                x=9000 + position * 240,
                y=9700,
            )
            if not self._create(endpoint, created, errors):
                return None, (), errors
            if not self._link(LinkPlan(
                id=f"trunkcal/access-link/{position}",
                device_a=endpoint.name,
                port_a="FastEthernet0",
                device_b=source.name,
                port_b=source_access[position],
                cable="straight",
            ), owned_links, errors):
                return None, (), errors
            endpoints.append((endpoint.name, source_access[position], vlan_id))

        for position in range(len(CONTROL_VLAN_IDS)):
            if not self._link(LinkPlan(
                id=f"trunkcal/trunk-link/{position}",
                device_a=source.name,
                port_a=source_trunks[position],
                device_b=target.name,
                port_b=target_trunks[position],
                cable="cross",
            ), owned_links, errors):
                return None, (), errors

        convergence, readbacks = self._configure_and_read_back(
            source, target, source_access, source_trunks, target_trunks, errors,
        )
        armed = self._arm_endpoints(endpoints, errors)
        original, frames, simulation_errors = self._observe_ingress(
            target.name, source.name, target_trunks,
        )
        errors.extend(simulation_errors)
        controls = tuple(
            self._control(
                vlan_id,
                target_trunks[position],
                source.name,
                convergence,
                readbacks,
                armed,
                frames,
            )
            for position, vlan_id in enumerate(CONTROL_VLAN_IDS)
        )
        return original, controls, errors

    def _create(self, device: DevicePlan, created, errors) -> bool:
        try:
            result = self._physical.ensure_device(device)
        except Exception as exc:  # noqa: BLE001
            created.append(device)
            errors.append(f"device_creation_raised: {type(exc).__name__}: {exc}")
            return False
        if not result.applied:
            if result.disposition is MutationDisposition.UNKNOWN:
                created.append(device)
            errors.append(f"device_not_created: {result.message}")
            return False
        created.append(device)
        return True

    def _switch_ports(self, device: DevicePlan, errors: list[str]) -> tuple[str, ...]:
        try:
            observation = self._physical.observe_device(device)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"switch_observation_raised for {device.name!r}: {exc}")
            return ()
        names = tuple(
            str(getattr(item, "name", item))
            for item in getattr(observation, "interfaces", ()) or ()
        )
        return tuple(
            name for name in names
            if name.casefold().startswith(("fastethernet", "gigabitethernet"))
        )

    def _link(
        self, link: LinkPlan, owned_links: list[str], errors: list[str],
    ) -> bool:
        # The empty-baseline gate and reserved endpoint names make this link
        # ours. Record that ownership before the mutation because an exception
        # can mean "effect unknown", not "nothing happened".
        owned_links.append(link.id)
        try:
            result = self._physical.ensure_link(link)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"link_raised for {link.id!r}: {exc}")
            return False
        if not result.applied:
            errors.append(f"link_not_created for {link.id!r}: {result.message}")
            return False
        return True

    def _configure_and_read_back(
        self,
        source: DevicePlan,
        target: DevicePlan,
        source_access: tuple[str, ...],
        source_trunks: tuple[str, ...],
        target_trunks: tuple[str, ...],
        errors: list[str],
    ) -> tuple[dict[str, bool], dict[str, object]]:
        actions: list = []
        for switch in (source, target):
            for vlan_id in CONTROL_VLAN_IDS:
                actions.append(CreateVlan(
                    id=f"trunkcal/vlan/{switch.id}/{vlan_id}",
                    phase=ConfigurationPhase.L2_DEFINITIONS,
                    device_id=switch.id,
                    device_name=switch.name,
                    site_id="trunkcal",
                    vlan_id=vlan_id,
                    name=f"TRUNKCAL{vlan_id}",
                ))
        for position, vlan_id in enumerate(CONTROL_VLAN_IDS):
            actions.append(ConfigureAccessPort(
                id=f"trunkcal/access/{position}",
                phase=ConfigurationPhase.L2_INTERFACES,
                device_id=source.id,
                device_name=source.name,
                site_id="trunkcal",
                interface=source_access[position],
                data_vlan_id=vlan_id,
                voice_vlan_id=None,
            ))
            for switch, interface, peer in (
                (source, source_trunks[position], target),
                (target, target_trunks[position], source),
            ):
                actions.append(ConfigureTrunk(
                    id=f"trunkcal/trunk/{switch.id}/{position}",
                    phase=ConfigurationPhase.L2_INTERFACES,
                    device_id=switch.id,
                    device_name=switch.name,
                    site_id="trunkcal",
                    interface=interface,
                    allowed_vlans=[vlan_id],
                    native_vlan_id=NATIVE_VLAN_ID,
                    peer_device_id=peer.id,
                    source_link_id=f"trunkcal/trunk-link/{position}",
                ))
        try:
            self._configuration.apply_actions(actions)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"configuration_raised: {type(exc).__name__}: {exc}")
            return {}, {}

        expectations = [
            VerificationExpectation(
                id=f"trunkcal/verify/{position}",
                action_id=f"trunkcal/trunk/{target.id}/{position}",
                kind=VerificationKind.TRUNK,
                device_id=target.id,
                device_name=target.name,
                expected={
                    "interface": target_trunks[position],
                    "allowed_vlans": [vlan_id],
                },
                required_query="show_interfaces_trunk",
            )
            for position, vlan_id in enumerate(CONTROL_VLAN_IDS)
        ]
        convergence: dict[str, bool] = {}
        try:
            results = self._configuration.verify(expectations)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"trunk_convergence_raised: {type(exc).__name__}: {exc}")
            results = []
        by_id = {
            expectation.id: target_trunks[position]
            for position, expectation in enumerate(expectations)
        }
        required_fields = (
            "interface", "status", "allowed_vlans", "active_vlans",
            "forwarding_vlans",
        )
        for item in results or ():
            interface = by_id.get(getattr(item, "expectation_id", ""))
            if interface is None:
                continue
            fields = getattr(item, "fields", {}) or {}
            convergence[interface] = bool(
                getattr(item, "fresh_evidence", False)
                and _status_value(getattr(item, "status", "")) == "verified"
                and all(
                    _status_value(fields.get(field)) == "verified"
                    for field in required_fields
                )
            )

        readbacks: dict[str, object] = {}
        for interface in target_trunks:
            try:
                readbacks[interface] = self._configuration.read_trunk(
                    target.name, interface,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"trunk_readback_raised for {interface!r}: {exc}")
        return convergence, readbacks

    def _arm_endpoints(self, endpoints, errors) -> dict[int, bool]:
        armed: dict[int, bool] = {}
        for name, _interface, vlan_id in endpoints:
            try:
                armed[vlan_id] = bool(self._endpoints.configure_endpoint_dhcp(name))
            except Exception as exc:  # noqa: BLE001
                armed[vlan_id] = False
                errors.append(f"endpoint_arming_raised for {name!r}: {exc}")
        return armed

    def _observe_ingress(
        self,
        target_switch: str,
        source_switch: str,
        target_trunks: tuple[str, ...],
    ):
        errors: list[str] = []
        try:
            state = self._simulation.read_simulation_state()
        except Exception as exc:  # noqa: BLE001
            return None, {}, [f"simulation_state_raised: {exc}"]
        original = bool(getattr(state, "simulation_mode", False))
        if not original:
            try:
                self._simulation.set_simulation_mode(True)
            except Exception as exc:  # noqa: BLE001
                return original, {}, [f"simulation_mode_raised: {exc}"]
        try:
            self._simulation.step("reset")
            for _batch in range(self._step_batches):
                self._simulation.step("forward", self._step_batch_size)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"simulation_step_raised: {exc}")
        try:
            trace = self._simulation.read_trace(
                limit=TRACE_LIMIT, device=target_switch,
            )
        except Exception as exc:  # noqa: BLE001
            return original, {}, [*errors, f"trace_raised: {exc}"]

        wanted = set(target_trunks)
        targets: dict[str, dict[str, object]] = {}
        for hop in getattr(trace, "hops", ()) or ():
            interface = str(getattr(hop, "in_port", "") or "")
            if interface not in wanted or interface in targets:
                continue
            if str(getattr(hop, "previous_device", "") or "") != source_switch:
                continue
            index = getattr(hop, "index", None)
            if not isinstance(index, int):
                continue
            targets[interface] = {
                "index": index,
                "in_port": interface,
                "previous_device": source_switch,
                "sim_time": getattr(hop, "sim_time", None),
                "traffic_type_raw": getattr(hop, "traffic_type_raw", None),
            }
        if not targets:
            errors.append(
                "No frame entered either calibration trunk in this bounded "
                "window; the absence is not a VLAN-policy verdict."
            )
            return original, {}, errors

        indices = [item["index"] for item in list(targets.values())[:MAX_ENUMERATED]]
        try:
            discovery = self._probe.discover_frame_observers(indices)
        except Exception as exc:  # noqa: BLE001
            return original, {}, [*errors, f"frame_probe_raised: {exc}"]
        by_index = {item.index: item for item in getattr(discovery, "frames", ())}
        for row in targets.values():
            frame = by_index.get(row["index"])
            row["frame"] = frame
            row["source_to_target_hop_identity_reconfirmed"] = bool(
                frame is not None
                and frame.matches(
                    device=target_switch,
                    sim_time=row.get("sim_time"),
                    traffic_type=row.get("traffic_type_raw"),
                    in_port=str(row["in_port"]),
                )
            )
        return original, targets, errors

    @staticmethod
    def _readback_reason(control: TrunkVlanCalibrationControl) -> str:
        if not control.convergence_verified:
            return "The target trunk never reached the existing governed convergence gate."
        if not control.readback_fresh:
            return "The target trunk had no fresh direct readback."
        if not control.readback_complete:
            return "The target trunk readback was incomplete."
        if control.trunk_status.casefold() != "trunking":
            return "The exact target port was not operationally trunking."
        if control.allowed_vlans is None or len(control.allowed_vlans) != 1:
            return "The direct readback did not expose exactly one allowed VLAN."
        if control.allowed_vlans[0] != control.target_vlan_id:
            return "The singleton allowed VLAN did not match the disposable control VLAN."
        if control.active_vlans != control.allowed_vlans:
            return "The target VLAN was not the exact active VLAN observation."
        if control.forwarding_vlans != control.allowed_vlans:
            return "The target VLAN was not the exact forwarding/not-pruned observation."
        if control.native_vlan is None:
            return "The native VLAN was not independently observable."
        if control.native_vlan == control.target_vlan_id:
            return "The only allowed VLAN was native and therefore cannot calibrate a tag."
        return ""

    def _control(
        self,
        vlan_id: int,
        interface: str,
        source_switch: str,
        convergence: dict[str, bool],
        readbacks: dict[str, object],
        armed: dict[int, bool],
        frames: dict[str, dict[str, object]],
    ) -> TrunkVlanCalibrationControl:
        readback = readbacks.get(interface)
        row = frames.get(interface) or {}
        frame = row.get("frame")
        observed = None
        child_returned = False
        members: tuple[str, ...] = ()
        present: tuple[str, ...] = ()
        frame_reason = ""
        if frame is not None and row.get(
            "source_to_target_hop_identity_reconfirmed"
        ):
            child = next((
                item for item in getattr(frame, "children", ())
                if item.getter == "getInFrame"
            ), None)
            if child is None or child.returned_null:
                frame_reason = "getInFrame returned no object, so there is no tag."
            else:
                child_returned = True
                members = tuple(child.members)
                present = tuple(name for name in TAG_FIELD_NAMES if name in members)
                field = child.tag_by_name.get("vlanId")
                if field is not None and field.observed:
                    observed = field.numeric_value
                elif "vlanId" not in present:
                    frame_reason = "The trunk ingress child exposed no vlanId member."
                else:
                    frame_reason = "The trunk ingress vlanId did not read as a number."
        elif not row:
            frame_reason = f"No frame entered {interface!r} from {source_switch!r}."
        else:
            frame_reason = "The frame could not be re-attributed to the exact trunk ingress."

        control = TrunkVlanCalibrationControl(
            target_vlan_id=vlan_id,
            switch_interface=interface,
            source_switch_name=source_switch,
            convergence_verified=bool(convergence.get(interface, False)),
            readback_fresh=bool(getattr(readback, "fresh_evidence", False)),
            readback_complete=bool(getattr(readback, "output_complete", False)),
            trunk_status=str(getattr(readback, "status", "") or ""),
            native_vlan=getattr(readback, "native_vlan", None),
            allowed_vlans=getattr(readback, "allowed_vlans", None),
            active_vlans=getattr(readback, "active_vlans", None),
            forwarding_vlans=getattr(readback, "forwarding_vlans", None),
            endpoint_armed=bool(armed.get(vlan_id, False)),
            frame_index=row.get("index"),
            frame_observed_in_port=str(row.get("in_port") or ""),
            frame_previous_device=str(row.get("previous_device") or ""),
            source_to_target_hop_identity_reconfirmed=bool(row.get(
                "source_to_target_hop_identity_reconfirmed"
            )),
            selected_frame_end_to_end_dhcp_identity_established=False,
            child_returned=child_returned,
            child_members=members,
            tag_fields_present=present,
            observed_vlan=observed,
        )
        readback_reason = self._readback_reason(control)
        if not control.endpoint_armed:
            frame_reason = frame_reason or "The endpoint DHCP client could not be armed."
        elif (
            control.source_to_target_hop_identity_reconfirmed
            and not control.selected_frame_end_to_end_dhcp_identity_established
        ):
            frame_reason = frame_reason or (
                "Selected trunk frame end-to-end DHCP identity was not established."
            )
        return replace(
            control,
            failure_reason=readback_reason or frame_reason,
        )

    def _restore_mode(self, original: bool | None):
        if original is None:
            return None, []
        errors: list[str] = []
        try:
            self._simulation.set_simulation_mode(original)
            state = self._simulation.read_simulation_state()
        except Exception as exc:  # noqa: BLE001
            return False, [f"mode_restoration_raised: {exc}"]
        restored = bool(
            getattr(state, "observed", False)
            and bool(getattr(state, "simulation_mode", False)) == original
        )
        if not restored:
            errors.append("The original Simulation/Realtime mode was not restored.")
        return restored, errors

    def _cleanup(self, created: list[DevicePlan], baseline):
        removed: list[str] = []
        errors: list[str] = []
        for device in reversed(created):
            try:
                result = self._physical.remove_device(device)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Cleanup failed for {device.name!r}: {exc}")
                continue
            if result.applied:
                removed.append(device.name)
            elif result.disposition is not MutationDisposition.NO_OP:
                errors.append(
                    f"Cleanup did not apply for {device.name!r}: {result.message}"
                )
        try:
            final = self._physical.observe_workspace()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Final workspace inventory failed: {exc}")
            return removed, errors, None, None
        return (
            removed,
            errors,
            final,
            physical_workspace_restoration_matches(baseline, final),
        )
