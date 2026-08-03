"""Adapter Packet Tracer para aplicar y observar ConfigurationPlan E5."""

from __future__ import annotations

import ipaddress
import json
from collections import defaultdict
from collections.abc import Callable, Sequence

from ...domain.enterprise.models.configuration import (
    ConfigurationAction,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureRoutedInterface,
    ConfigureSubinterface,
    ConfigureSvi,
    ConfigureTrunk,
    CreateVlan,
    SetEndpointDhcp,
    SetEndpointStaticAddress,
    VerificationExpectation,
    VerificationKind,
)
from ...domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
    ConfigurationFailureCode,
    ConvergenceReport,
    FieldVerificationStatus,
    RuntimeActionMutation,
    RuntimeConfigurationTarget,
    RuntimeVerification,
)
from ...domain.enterprise.models.discovery import DeviceInitializationState
from ..generator.configuration_renderer import PacketTracerIosRenderer
from .configuration_runtime import PacketTracerConfigurationRuntime
from .device_lifecycle import StateConvergenceWaiter
from .ios_terminal import (
    ControlledIosExecutor,
    IosCommandResult,
    OperationalQueryId,
    parse_show_interfaces_trunk,
    parse_show_ip_interface_brief,
)


_IOS_ACTIONS = (
    CreateVlan,
    ConfigureAccessPort,
    ConfigureTrunk,
    ConfigureRoutedInterface,
    ConfigureSvi,
    ConfigureSubinterface,
    ConfigureDhcpPool,
)
_ENDPOINT_ACTIONS = (SetEndpointStaticAddress, SetEndpointDhcp)


class PacketTracerEnterpriseConfigurationRuntime:
    """Usa los canales oficiales existentes; no expone IOS/JS arbitrario."""

    def __init__(
        self,
        query_inventory: Callable[[], list[dict] | dict],
        send: Callable[[str], bool],
        send_and_wait: Callable[[str, float], str | None],
        *,
        vlan_timeout_seconds: float = 5.0,
        endpoint_timeout_seconds: float = 30.0,
        trunk_timeout_seconds: float = 8.0,
        l3_timeout_seconds: float = 8.0,
        convergence_interval_seconds: float = 0.25,
        ios_readiness: Callable[[str], bool] | None = None,
    ) -> None:
        self._query_inventory = query_inventory
        self._send = send
        self._send_and_wait = send_and_wait
        self._configuration = PacketTracerConfigurationRuntime(send)
        self._ios = ControlledIosExecutor(send_and_wait)
        self._renderer = PacketTracerIosRenderer()
        self._targets: dict[str, RuntimeConfigurationTarget] = {}
        self._vlan_timeout = vlan_timeout_seconds
        self._endpoint_timeout = endpoint_timeout_seconds
        self._trunk_timeout = trunk_timeout_seconds
        self._l3_timeout = l3_timeout_seconds
        self._convergence_interval = convergence_interval_seconds
        self._ios_readiness = ios_readiness or self._wait_for_ios
        self._ready_ios_devices: set[str] = set()

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        raw = self._query_inventory()
        items = raw.get("devices", []) if isinstance(raw, dict) else raw
        targets: list[RuntimeConfigurationTarget] = []
        for item in items:
            ports = []
            for port in item.get("ports", item.get("interfaces", [])) or []:
                name = port.get("name", "") if isinstance(port, dict) else str(port)
                if name:
                    ports.append(name)
            targets.append(RuntimeConfigurationTarget(
                device_name=str(item.get("name") or item.get("device_name") or ""),
                model=str(item.get("model") or ""),
                interfaces=sorted(set(ports), key=str.casefold),
            ))
        self._targets = {item.device_name: item for item in targets}
        return sorted(targets, key=lambda item: item.device_name)

    def apply_actions(
        self, actions: Sequence[ConfigurationAction],
    ) -> list[RuntimeActionMutation]:
        results: dict[str, RuntimeActionMutation] = {}
        ios_by_device: dict[str, list[ConfigurationAction]] = defaultdict(list)
        endpoints: list[SetEndpointStaticAddress | SetEndpointDhcp] = []
        for action in actions:
            if isinstance(action, _IOS_ACTIONS):
                ios_by_device[action.device_name].append(action)
            elif isinstance(action, _ENDPOINT_ACTIONS):
                endpoints.append(action)

        if ios_by_device and not self._targets:
            self.inventory()
        for device_name, device_actions in sorted(ios_by_device.items()):
            target = self._targets.get(device_name)
            model = target.model if target else ""
            if device_name not in self._ready_ios_devices:
                if not self._ios_readiness(device_name):
                    for action in device_actions:
                        results[action.id] = RuntimeActionMutation(
                            action_id=action.id,
                            applied=False,
                            failure_code=ConfigurationFailureCode.SESSION_FAILED,
                            message="IOS did not reach OPERATIONAL_READY before configuration.",
                        )
                    continue
                self._ready_ios_devices.add(device_name)
            try:
                batches = self._renderer.render_device_batches(
                    device_name, model, device_actions,
                )
            except ValueError as exc:
                for action in device_actions:
                    results[action.id] = RuntimeActionMutation(
                        action_id=action.id, applied=False,
                        failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                        message=str(exc),
                    )
                continue
            for batch in batches:
                applied = self._configuration.configure_ios(device_name, batch.ios_payload)
                batch_id = f"{device_name}:{int(batch.phase)}"
                for action_id in batch.action_ids:
                    results[action_id] = RuntimeActionMutation(
                        action_id=action_id,
                        applied=applied,
                        failure_code=(
                            ConfigurationFailureCode.NONE
                            if applied else ConfigurationFailureCode.APPLICATION_FAILED
                        ),
                        message=(
                            "Configuration batch accepted by Packet Tracer."
                            if applied else "Packet Tracer rejected the configuration batch."
                        ),
                        batch_id=batch_id,
                    )

        if endpoints:
            payload = "".join(self._endpoint_call(action) for action in sorted(
                endpoints, key=lambda item: item.id,
            ))
            applied = bool(payload) and self._send(payload)
            batch_id = "endpoints:" + str(int(endpoints[0].phase))
            for action in endpoints:
                results[action.id] = RuntimeActionMutation(
                    action_id=action.id,
                    applied=applied,
                    failure_code=(
                        ConfigurationFailureCode.NONE
                        if applied else ConfigurationFailureCode.APPLICATION_FAILED
                    ),
                    message=(
                        "Endpoint batch accepted by Packet Tracer."
                        if applied else "Packet Tracer rejected the endpoint batch."
                    ),
                    batch_id=batch_id,
                )
        return [
            results.get(action.id, RuntimeActionMutation(
                action_id=action.id,
                applied=False,
                failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                message="No Packet Tracer adapter exists for this typed action.",
            ))
            for action in actions
        ]

    def _wait_for_ios(self, device_name: str) -> bool:
        readiness = self._ios.wait_until_ready(device_name)
        return readiness.state is DeviceInitializationState.OPERATIONAL_READY

    @staticmethod
    def _endpoint_call(action: SetEndpointStaticAddress | SetEndpointDhcp) -> str:
        name = json.dumps(action.device_name)
        interface = json.dumps(action.interface)
        if isinstance(action, SetEndpointDhcp):
            call = "configurePcIp(" + ",".join((name, "true", "null", "null", "null", "null", interface)) + ");"
        else:
            arguments = ",".join((
                name,
                "false",
                json.dumps(action.ipv4),
                json.dumps(action.netmask),
                json.dumps(action.gateway),
                json.dumps(action.dns_server or ""),
                interface,
            ))
            call = "configurePcIp(" + arguments + ");"
        return "try{" + call + "}catch(__e){}"

    def verify(
        self, expectations: Sequence[VerificationExpectation],
    ) -> list[RuntimeVerification]:
        ios_cache: dict[tuple[str, OperationalQueryId], object] = {}
        results: list[RuntimeVerification] = []
        for expectation in expectations:
            if expectation.kind is VerificationKind.VLAN:
                results.append(self._verify_vlan(expectation))
            elif expectation.kind is VerificationKind.TRUNK:
                results.append(self._verify_trunk(expectation, ios_cache))
            elif expectation.kind is VerificationKind.L3_INTERFACE:
                results.append(self._verify_l3(expectation, ios_cache))
            elif expectation.kind is VerificationKind.ENDPOINT_ADDRESSING:
                results.append(self._verify_endpoint(expectation))
            elif expectation.kind in {VerificationKind.ACCESS_PORT, VerificationKind.DHCP_POOL}:
                results.append(self._unobservable(expectation))
        return results

    def _verify_vlan(self, expectation: VerificationExpectation) -> RuntimeVerification:
        vlan_id = int(expectation.expected["vlan_id"])
        name = json.dumps(expectation.device_name)

        def inspect() -> dict:
            js = "".join((
                "try{var d=ipc.network().getDevice(", name, ");",
                "var vm=d&&typeof d.getProcess==='function'?d.getProcess('VlanManager'):null;",
                "var present=false;if(vm){for(var i=0;i<vm.getVlanCount();i++){var v=vm.getVlanAt(i);",
                "if(v&&v.getVlanNumber()===", str(vlan_id), "){present=true;break;}}}",
                "reportResult(JSON.stringify({found:!!d,configuration_channel:present,present:present}));",
                "}catch(e){reportResult('ERROR:'+e);}",
            ))
            return self._json_result(js, 3.0)

        convergence = StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._vlan_timeout,
            interval_seconds=self._convergence_interval,
        ).wait()
        verified = convergence.configuration_channel
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.VERIFIED if verified else ActionExecutionStatus.FAILED,
            evidence_method="vlan_manager_object_state",
            fresh_evidence=True,
            fields={"vlan_id": (
                FieldVerificationStatus.VERIFIED if verified else FieldVerificationStatus.FAILED
            )},
            convergence=ConvergenceReport(
                attempts=convergence.attempts,
                elapsed_ms=convergence.elapsed_ms,
                final_status=(
                    ActionExecutionStatus.VERIFIED if verified else ActionExecutionStatus.FAILED
                ),
                last_observable_state="present" if verified else "absent",
            ),
        )

    def _verify_trunk(
        self, expectation: VerificationExpectation, cache: dict,
    ) -> RuntimeVerification:
        expected_interface = str(expectation.expected["interface"])
        def find_row(show: IosCommandResult):
            return next((
                item for item in parse_show_interfaces_trunk(show.output)
                if self._same_interface(item.interface, expected_interface)
            ), None) if show.executed else None

        show, convergence, converged = self._converged_ios_query(
            expectation,
            OperationalQueryId.SHOW_INTERFACES_TRUNK,
            cache,
            lambda value: bool(
                (row := find_row(value)) and row.status.casefold() == "trunking"
            ),
            timeout_seconds=self._trunk_timeout,
        )
        row = next((
            item for item in parse_show_interfaces_trunk(show.output)
            if self._same_interface(item.interface, expected_interface)
        ), None) if show.executed else None
        verified = bool(
            converged and row and row.status.casefold() == "trunking"
            and show.fresh_output_observed
        )
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.VERIFIED if verified else ActionExecutionStatus.FAILED,
            evidence_method="fresh_show_interfaces_trunk",
            fresh_evidence=show.fresh_output_observed,
            fields={
                "interface": FieldVerificationStatus.VERIFIED if row else FieldVerificationStatus.FAILED,
                "status": FieldVerificationStatus.VERIFIED if verified else FieldVerificationStatus.FAILED,
                "allowed_vlans": FieldVerificationStatus.UNOBSERVABLE,
            },
            message=show.failure_reason or ("" if converged else "Trunk convergence timed out."),
            convergence=convergence,
        )

    def _verify_l3(
        self, expectation: VerificationExpectation, cache: dict,
    ) -> RuntimeVerification:
        expected_interface = str(expectation.expected["interface"])
        expected_ip = str(expectation.expected["ipv4"])
        expected_up = bool(expectation.expected.get("administrative_up", True))
        def find_row(show: IosCommandResult):
            return next((
                item for item in parse_show_ip_interface_brief(show.output)
                if self._same_interface(item.interface, expected_interface)
            ), None) if show.executed else None

        show, convergence, converged = self._converged_ios_query(
            expectation,
            OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
            cache,
            lambda value: bool(
                (row := find_row(value))
                and row.ip_address == expected_ip
                and (
                    not expected_up
                    or row.status.casefold() == "up"
                    and row.protocol.casefold() == "up"
                )
            ),
            timeout_seconds=self._l3_timeout,
        )
        row = next((
            item for item in parse_show_ip_interface_brief(show.output)
            if self._same_interface(item.interface, expected_interface)
        ), None) if show.executed else None
        address_verified = bool(
            converged and row and row.ip_address == expected_ip
            and show.fresh_output_observed
        )
        status_verified = bool(
            row and (
                not expected_up
                or row.status.casefold() == "up" and row.protocol.casefold() == "up"
            )
        )
        verified = address_verified and status_verified
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.VERIFIED if verified else ActionExecutionStatus.FAILED,
            evidence_method="fresh_show_ip_interface_brief",
            fresh_evidence=show.fresh_output_observed,
            fields={
                "interface": FieldVerificationStatus.VERIFIED if row else FieldVerificationStatus.FAILED,
                "ipv4": FieldVerificationStatus.VERIFIED if address_verified else FieldVerificationStatus.FAILED,
                "status": FieldVerificationStatus.VERIFIED if status_verified else FieldVerificationStatus.FAILED,
                "protocol": FieldVerificationStatus.VERIFIED if status_verified else FieldVerificationStatus.FAILED,
            },
            message=show.failure_reason or ("" if converged else "L3 convergence timed out."),
            convergence=convergence,
        )

    def _converged_ios_query(
        self,
        expectation: VerificationExpectation,
        query_id: OperationalQueryId,
        cache: dict[tuple[str, OperationalQueryId], IosCommandResult],
        predicate: Callable[[IosCommandResult], bool],
        *,
        timeout_seconds: float,
    ) -> tuple[IosCommandResult, ConvergenceReport, bool]:
        key = (expectation.device_name, query_id)
        cached = cache.get(key)
        if cached is not None and cached.fresh_output_observed and predicate(cached):
            return cached, ConvergenceReport(
                attempts=0,
                elapsed_ms=0,
                final_status=ActionExecutionStatus.VERIFIED,
                last_observable_state="cached_current_query",
            ), True

        latest: dict[str, IosCommandResult] = {}
        def inspect() -> dict:
            show = self._ios.execute(expectation.device_name, query_id)
            latest["show"] = show
            matched = bool(show.fresh_output_observed and predicate(show))
            return {
                "found": show.executed,
                "configuration_channel": matched,
                "failure_reason": show.failure_reason,
            }

        observed = StateConvergenceWaiter(
            inspect,
            timeout_seconds=timeout_seconds,
            interval_seconds=self._convergence_interval,
        ).wait()
        show = latest["show"]
        converged = observed.state is DeviceInitializationState.CONFIGURATION_READY
        if show.fresh_output_observed:
            cache[key] = show
        convergence = ConvergenceReport(
            attempts=observed.attempts,
            elapsed_ms=observed.elapsed_ms,
            final_status=(
                ActionExecutionStatus.VERIFIED
                if converged else ActionExecutionStatus.FAILED
            ),
            last_observable_state=(
                "matched" if converged else show.failure_reason or "not_matched"
            ),
        )
        return show, convergence, converged

    def _verify_endpoint(self, expectation: VerificationExpectation) -> RuntimeVerification:
        expected = expectation.expected
        name = json.dumps(expectation.device_name)

        def inspect() -> dict:
            js = "".join((
                "try{var d=ipc.network().getDevice(", name, ");var p=null;",
                "if(d){for(var i=0;i<d.getPortCount();i++){var c=d.getPortAt(i);",
                "if(c&&typeof c.getIpAddress==='function'){p=c;break;}}}",
                "var ip=p?String(p.getIpAddress()):'';var mask=p?String(p.getSubnetMask()):'';",
                # PT 9.0.1 evidence confirms only IP/mask getters. Gateway and DNS
                # remain deliberately unobservable until Cisco API evidence exists.
                "reportResult(JSON.stringify({found:!!d,configuration_channel:!!p,ipv4:ip,netmask:mask,gateway:null,dns:null}));",
                "}catch(e){reportResult('ERROR:'+e);}",
            ))
            observed = self._json_result(js, 3.0)
            observed["configuration_channel"] = self._endpoint_matches(expected, observed)
            return observed

        convergence = StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._endpoint_timeout,
            interval_seconds=self._convergence_interval,
        ).wait()
        observed = inspect()
        ipv4_ok = self._ipv4_matches(expected, str(observed.get("ipv4") or ""))
        mask_ok = str(observed.get("netmask") or "") == str(expected.get("netmask") or "")
        fields = {
            "ipv4": FieldVerificationStatus.VERIFIED if ipv4_ok else FieldVerificationStatus.FAILED,
            "netmask": FieldVerificationStatus.VERIFIED if mask_ok else FieldVerificationStatus.FAILED,
        }
        for field in ("gateway", "dns"):
            value = observed.get(field)
            wanted = expected.get(field)
            if value is None:
                fields[field] = FieldVerificationStatus.UNOBSERVABLE
            elif not wanted:
                fields[field] = FieldVerificationStatus.UNKNOWN
            else:
                fields[field] = (
                    FieldVerificationStatus.VERIFIED
                    if str(value) == str(wanted) else FieldVerificationStatus.FAILED
                )
        converged = convergence.state is DeviceInitializationState.CONFIGURATION_READY
        core_verified = converged and ipv4_ok and mask_ok
        partial = any(value is FieldVerificationStatus.UNOBSERVABLE for value in fields.values())
        status = (
            ActionExecutionStatus.PARTIAL if core_verified and partial
            else ActionExecutionStatus.VERIFIED if core_verified
            else ActionExecutionStatus.FAILED
        )
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_method="structured_endpoint_getters",
            fresh_evidence=True,
            fields=fields,
            convergence=ConvergenceReport(
                attempts=convergence.attempts,
                elapsed_ms=convergence.elapsed_ms,
                final_status=status,
                last_observable_state=(
                    str(observed.get("ipv4") or "no-ip")
                    if converged else "convergence_timeout"
                ),
            ),
        )

    @staticmethod
    def _endpoint_matches(expected: dict, observed: dict) -> bool:
        return (
            PacketTracerEnterpriseConfigurationRuntime._ipv4_matches(
                expected, str(observed.get("ipv4") or ""),
            )
            and str(observed.get("netmask") or "") == str(expected.get("netmask") or "")
        )

    @staticmethod
    def _ipv4_matches(expected: dict, value: str) -> bool:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        if expected.get("mode") == "static":
            return value == expected.get("ipv4")
        try:
            network = ipaddress.ip_network(
                f"{expected.get('network')}/{expected.get('prefix')}", strict=True,
            )
        except ValueError:
            return False
        return address in network and address not in {
            network.network_address, network.broadcast_address,
        }

    @staticmethod
    def _unobservable(expectation: VerificationExpectation) -> RuntimeVerification:
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.PARTIAL,
            evidence_method="runtime_observability_limit",
            fresh_evidence=False,
            fields={
                field: FieldVerificationStatus.UNOBSERVABLE
                for field in expectation.expected
            },
            message=f"No independent getter is registered for {expectation.kind.value}.",
        )

    def _json_result(self, js: str, timeout: float) -> dict:
        raw = self._send_and_wait(js, timeout)
        if raw is None:
            return {"found": False, "configuration_channel": False, "failure_reason": "timeout"}
        if raw.startswith(("ERROR:", "PT_ERROR:")):
            return {"found": False, "configuration_channel": False, "failure_reason": raw}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {"found": False, "configuration_channel": False, "failure_reason": "malformed_json"}
        return value if isinstance(value, dict) else {
            "found": False, "configuration_channel": False, "failure_reason": "non_object_json",
        }

    @staticmethod
    def _same_interface(observed: str, expected: str) -> bool:
        aliases = (
            ("tengigabitethernet", "te"),
            ("tengig", "te"),
            ("gigabitethernet", "gi"),
            ("gig", "gi"),
            ("fastethernet", "fa"),
            ("fast", "fa"),
            ("ethernet", "et"),
            ("eth", "et"),
        )

        def normalize(value: str) -> str:
            result = value.casefold().replace(" ", "")
            for long_name, short_name in aliases:
                if result.startswith(long_name):
                    return short_name + result[len(long_name):]
            return result

        return normalize(observed) == normalize(expected)
