"""Adapter Packet Tracer para aplicar y observar ConfigurationPlan E5."""

from __future__ import annotations

import ipaddress
import json
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ...domain.enterprise.models.configuration import (
    ConfigurationAction,
    ConfigureAccessPort,
    ConfigureDhcpPool,
    ConfigureEthernetLinkMode,
    ConfigureHostname,
    ConfigureInterfaceBandwidth,
    ConfigureRoutedInterface,
    ConfigureSerialClock,
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
    parse_serial_controller,
)
from .runtime_inventory import normalize_runtime_inventory
from ...shared.utils import same_interface_name


# Acciones que se aplican por el canal IOS. Faltaban aqui las tres de
# rendimiento de enlace, de modo que el runtime las descartaba antes
# incluso de llegar al renderer: el mismo fallo mudo, una capa mas abajo.
_IOS_ACTIONS = (
    ConfigureHostname,
    CreateVlan,
    ConfigureAccessPort,
    ConfigureTrunk,
    ConfigureRoutedInterface,
    ConfigureSvi,
    ConfigureSubinterface,
    ConfigureDhcpPool,
    ConfigureSerialClock,
    ConfigureInterfaceBandwidth,
    ConfigureEthernetLinkMode,
)
_ENDPOINT_ACTIONS = (SetEndpointStaticAddress, SetEndpointDhcp)


# A trunk verification now claims operational STP forwarding, not merely that
# IOS accepted `switchport mode trunk`.  A fresh PT 9.0.1.0858 run still had all
# expected VLANs allowed and active, but none forwarding, when the former 8 s
# budget expired after 25 complete reads.  Keep the wait bounded while giving
# the independent forwarding read-back its own lifecycle-sized budget.
TRUNK_FORWARDING_CONVERGENCE_TIMEOUT_SECONDS = 45.0


@dataclass(frozen=True)
class TrunkReadbackObservation:
    """One exact, registered and read-only trunk observation.

    The four VLAN dimensions intentionally remain independent. ``None`` means
    that dimension was not exposed by a fresh complete query; an empty tuple is
    an observed empty IOS section.
    """

    device_name: str
    requested_interface: str
    interface: str = ""
    status: str = ""
    native_vlan: int | None = None
    allowed_vlans: tuple[int, ...] | None = None
    active_vlans: tuple[int, ...] | None = None
    forwarding_vlans: tuple[int, ...] | None = None
    fresh_evidence: bool = False
    output_complete: bool = False
    failure_reason: str = ""


#: `SwitchPort.getAdminOpMode()` para `switchport mode access`. MEDIDO, no
#: supuesto: cualificación en vivo sobre PT `9.0.1.0858` / `2950T-24`, tres
#: puertos en la misma pasada, cada código corroborado por la lectura IOS
#: independiente `show interfaces <if> switchport` de esa misma sesión.
#:
#: Se mide el CÓDIGO, no un nombre. Un código fuera de esta tabla no es un modo
#: desconocido que se pueda tratar como no-acceso: es un modo que nadie midió,
#: y el campo sale UNOBSERVABLE.
#:
#: `isAccessPort()` existe en el mismo objeto y NO sirve para esto: devuelve
#: True tanto para `static access` como para `dynamic desirable`. Usarlo como
#: gate del modo convertiría un puerto sin configurar en un puerto de acceso
#: verificado.
ADMIN_OP_MODE_ACCESS = 3
MEASURED_ADMIN_OP_MODES = {
    0: "dynamic desirable",
    2: "trunk",
    ADMIN_OP_MODE_ACCESS: "static access",
}


class PacketTracerEnterpriseConfigurationRuntime:
    """Usa los canales oficiales existentes; no expone IOS/JS arbitrario."""

    def __init__(
        self,
        query_inventory: Callable[[], list[dict] | dict],
        send: Callable[[str], bool],
        send_and_wait: Callable[[str, float], str | None],
        *,
        hostname_timeout_seconds: float = 8.0,
        vlan_timeout_seconds: float = 5.0,
        endpoint_timeout_seconds: float = 30.0,
        trunk_timeout_seconds: float = TRUNK_FORWARDING_CONVERGENCE_TIMEOUT_SECONDS,
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
        self._hostname_timeout = hostname_timeout_seconds
        self._vlan_timeout = vlan_timeout_seconds
        self._endpoint_timeout = endpoint_timeout_seconds
        self._trunk_timeout = trunk_timeout_seconds
        self._l3_timeout = l3_timeout_seconds
        self._convergence_interval = convergence_interval_seconds
        self._ios_readiness = ios_readiness or self._wait_for_ios
        self._ready_ios_devices: set[str] = set()

    def inventory(self) -> list[RuntimeConfigurationTarget]:
        targets = normalize_runtime_inventory(self._query_inventory())
        self._targets = {item.device_name: item for item in targets}
        return targets

    def read_trunk(
        self, device_name: str, interface: str,
    ) -> TrunkReadbackObservation:
        """Read one trunk through the existing registered paged SHOW only."""
        show = self._ios.execute(
            device_name, OperationalQueryId.SHOW_INTERFACES_TRUNK,
        )
        row = next((
            item for item in parse_show_interfaces_trunk(show.output)
            if same_interface_name(item.interface, interface)
        ), None) if show.executed else None
        fresh = bool(show.executed and show.fresh_output_observed)
        complete = bool(show.output_complete)
        reason = show.failure_reason
        if not reason and not fresh:
            reason = "No fresh current show interfaces trunk output was observed."
        if not reason and not complete:
            reason = "The show interfaces trunk output was incomplete."
        if not reason and row is None:
            reason = f"The fresh trunk table did not contain {interface!r}."
        return TrunkReadbackObservation(
            device_name=device_name,
            requested_interface=interface,
            interface=row.interface if row is not None else "",
            status=row.status if row is not None else "",
            native_vlan=row.native_vlan if row is not None else None,
            allowed_vlans=row.allowed_vlans if row is not None else None,
            active_vlans=row.active_vlans if row is not None else None,
            forwarding_vlans=(
                row.forwarding_vlans if row is not None else None
            ),
            fresh_evidence=fresh,
            output_complete=complete,
            failure_reason=reason,
        )

    @staticmethod
    def _refuse_batch(
        actions: Sequence[ConfigurationAction], message: str,
    ) -> list[RuntimeActionMutation]:
        """Rechaza el lote entero sin haber tocado ningun dispositivo."""
        return [
            RuntimeActionMutation(
                action_id=action.id,
                applied=False,
                failure_code=ConfigurationFailureCode.APPLICATION_FAILED,
                message=message,
            )
            for action in actions
        ]

    def apply_actions(
        self, actions: Sequence[ConfigurationAction],
    ) -> list[RuntimeActionMutation]:
        results: dict[str, RuntimeActionMutation] = {}
        ios_by_device: dict[str, list[ConfigurationAction]] = defaultdict(list)
        endpoints: list[SetEndpointStaticAddress | SetEndpointDhcp] = []
        unroutable: list[ConfigurationAction] = []
        for action in actions:
            if isinstance(action, _IOS_ACTIONS):
                ios_by_device[action.device_name].append(action)
            elif isinstance(action, _ENDPOINT_ACTIONS):
                endpoints.append(action)
            else:
                unroutable.append(action)

        # Enrutabilidad y renderizabilidad se comprueban sobre TODO el lote
        # antes de la primera mutacion. Fallar a mitad dejaria la red en un
        # estado que nadie pidio, y ese estado es peor que no haber empezado.
        if unroutable:
            return self._refuse_batch(
                actions,
                "No runtime channel handles "
                + ", ".join(sorted({type(item).__name__ for item in unroutable}))
                + "; the batch was refused before any device was touched.",
            )

        if ios_by_device and not self._targets:
            self.inventory()

        prerendered: dict[str, list] = {}
        for device_name, device_actions in sorted(ios_by_device.items()):
            target = self._targets.get(device_name)
            try:
                prerendered[device_name] = self._renderer.render_device_batches(
                    device_name, target.model if target else "", device_actions,
                )
            except ValueError as exc:
                return self._refuse_batch(
                    actions,
                    f"{device_name}: {exc}; the batch was refused before any "
                    "device was touched.",
                )

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
            # Ya renderizado en el preflight: aqui solo queda aplicar.
            for batch in prerendered[device_name]:
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
            if expectation.kind is VerificationKind.HOSTNAME:
                results.append(self._verify_hostname(expectation))
            elif expectation.kind is VerificationKind.VLAN:
                results.append(self._verify_vlan(expectation))
            elif expectation.kind is VerificationKind.TRUNK:
                results.append(self._verify_trunk(expectation, ios_cache))
            elif expectation.kind is VerificationKind.L3_INTERFACE:
                results.append(self._verify_l3(expectation, ios_cache))
            elif expectation.kind is VerificationKind.SERIAL_CONTROLLER:
                results.append(self._verify_serial_controller(expectation))
            elif expectation.kind is VerificationKind.ENDPOINT_ADDRESSING:
                results.append(self._verify_endpoint(expectation))
            elif expectation.kind is VerificationKind.ACCESS_PORT:
                results.append(self._verify_access_port(expectation))
            elif expectation.kind is VerificationKind.DHCP_POOL:
                results.append(self._unobservable(expectation))
        return results

    def _verify_hostname(
        self, expectation: VerificationExpectation,
    ) -> RuntimeVerification:
        expected = str(expectation.expected["hostname"])
        name = json.dumps(expectation.device_name)
        last_observed: dict = {}

        def inspect() -> dict:
            js = "".join((
                "try{var d=ipc.network().getDevice(", name, ");",
                "var t=d&&typeof d.getCommandLine==='function'?d.getCommandLine():null;",
                "var hs=!!d&&typeof d.getHostName==='function';",
                "var h=hs?String(d.getHostName()):'';",
                "var p=t&&typeof t.getPrompt==='function'?String(t.getPrompt()):'';",
                "var o=t&&typeof t.getOutput==='function'?String(t.getOutput()):'';",
                "reportResult(JSON.stringify({found:!!d,terminal:!!t,",
                "hostname_supported:hs,hostname:h,prompt:p,output:o}));",
                "}catch(e){reportResult('ERROR:'+e);}",
            ))
            current = self._json_result(js, 3.0)
            actual = str(current.get("hostname") or "").strip()
            method = "packet_tracer_device_hostname_getter"
            if not actual:
                prompt = str(current.get("prompt") or "").strip()
                actual = self._hostname_from_prompt(prompt)
                method = "ios_terminal_prompt_identity"
                if not actual:
                    actual = self._hostname_from_output(
                        str(current.get("output") or "")
                    )
                    method = "ios_terminal_output_prompt_identity"
            current["actual_hostname"] = actual
            current["evidence_method"] = method
            current["configuration_channel"] = actual == expected
            last_observed.clear()
            last_observed.update(current)
            return current

        convergence = StateConvergenceWaiter(
            inspect,
            timeout_seconds=self._hostname_timeout,
            interval_seconds=self._convergence_interval,
        ).wait()
        actual = str(last_observed.get("actual_hostname") or "")
        evidence_method = str(
            last_observed.get("evidence_method")
            or "ios_terminal_prompt_identity"
        )
        if (
            not last_observed.get("found")
            or not actual
        ):
            return self._unobservable(expectation)
        verified = (
            convergence.state is DeviceInitializationState.CONFIGURATION_READY
            and actual == expected
        )
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=(
                ActionExecutionStatus.VERIFIED
                if verified else ActionExecutionStatus.FAILED
            ),
            evidence_method=evidence_method,
            fresh_evidence=True,
            fields={
                "hostname": (
                    FieldVerificationStatus.VERIFIED
                    if verified else FieldVerificationStatus.FAILED
                ),
            },
            message="" if verified else f"IOS prompt identity is {actual!r}.",
            convergence=ConvergenceReport(
                attempts=convergence.attempts,
                elapsed_ms=convergence.elapsed_ms,
                final_status=(
                    ActionExecutionStatus.VERIFIED
                    if verified else ActionExecutionStatus.FAILED
                ),
                last_observable_state=actual or "unobservable",
            ),
        )

    @staticmethod
    def _hostname_from_prompt(prompt: str) -> str:
        match = re.fullmatch(r"([^\s()]+)[>#]", prompt.strip())
        return match.group(1) if match else ""

    @classmethod
    def _hostname_from_output(cls, output: str) -> str:
        # PT 9.0.1 may expose an empty getPrompt() on a 3560 while getOutput()
        # still retains the current IOS prompt. Ignore asynchronous syslog at
        # the tail and select the latest complete EXEC prompt, never a device
        # display name or an inferred model default.
        for line in reversed(output.splitlines()):
            candidate = line.strip()
            if not candidate or candidate.startswith("%"):
                continue
            hostname = cls._hostname_from_prompt(candidate)
            if hostname:
                return hostname
        return ""

    def _verify_serial_controller(
        self,
        expectation: VerificationExpectation,
    ) -> RuntimeVerification:
        """Verify the physical DCE role and exact configured clock independently."""
        expected_interface = str(expectation.expected["interface"])
        expected_role = str(expectation.expected["serial_endpoint_role"]).casefold()
        expected_rate = int(expectation.expected["clock_rate_bps"])
        show = self._ios.execute(
            expectation.device_name,
            OperationalQueryId.SHOW_CONTROLLERS_SERIAL,
            interface=expected_interface,
        )
        # `output_complete` es estrictamente mas fuerte que "no truncada": para
        # esta consulta, cualificada para continuacion acotada, exige ademas que
        # la lectura logica haya cerrado en un prompt.
        complete = bool(
            show.executed
            and show.fresh_output_observed
            and show.output_complete
        )
        row = parse_serial_controller(show.output) if complete else None
        if row is None:
            return RuntimeVerification(
                expectation_id=expectation.id,
                status=ActionExecutionStatus.UNOBSERVABLE,
                evidence_method=(
                    "registered_ios_output_truncated"
                    if show.truncated_by_pager
                    else "fresh_show_controllers_serial"
                ),
                fresh_evidence=complete,
                fields={
                    field: FieldVerificationStatus.UNOBSERVABLE
                    for field in expectation.expected
                },
                message=(
                    show.failure_reason
                    or "Fresh, complete serial-controller output was unavailable."
                ),
            )
        interface_ok = self._same_interface(row.interface, expected_interface)
        role_ok = row.endpoint_role == expected_role
        rate_ok = row.clock_rate_bps == expected_rate
        verified = interface_ok and role_ok and rate_ok
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=(
                ActionExecutionStatus.VERIFIED
                if verified else ActionExecutionStatus.FAILED
            ),
            evidence_method="fresh_show_controllers_serial",
            fresh_evidence=True,
            fields={
                "interface": (
                    FieldVerificationStatus.VERIFIED
                    if interface_ok else FieldVerificationStatus.FAILED
                ),
                "serial_endpoint_role": (
                    FieldVerificationStatus.VERIFIED
                    if role_ok else FieldVerificationStatus.FAILED
                ),
                "clock_rate_bps": (
                    FieldVerificationStatus.VERIFIED
                    if rate_ok else FieldVerificationStatus.FAILED
                ),
            },
            message=(
                ""
                if verified
                else "Serial controller does not match the planned DCE role and clock."
            ),
        )

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
        expected_vlans = frozenset(
            int(item) for item in expectation.expected.get("allowed_vlans", [])
        )

        def find_row(show: IosCommandResult):
            return next((
                item for item in parse_show_interfaces_trunk(show.output)
                if self._same_interface(item.interface, expected_interface)
            ), None) if show.executed else None

        def vlan_status(
            show: IosCommandResult, row, attribute: str,
        ) -> FieldVerificationStatus:
            if (
                row is None
                or not show.fresh_output_observed
                or not show.output_complete
            ):
                return FieldVerificationStatus.UNOBSERVABLE
            observed = getattr(row, attribute)
            if observed is None:
                return FieldVerificationStatus.UNOBSERVABLE
            return (
                FieldVerificationStatus.VERIFIED
                if expected_vlans.issubset(observed)
                else FieldVerificationStatus.FAILED
            )

        def traverses_expected_vlans(show: IosCommandResult) -> bool:
            row = find_row(show)
            return bool(
                row
                and row.status.casefold() == "trunking"
                and all(
                    vlan_status(show, row, attribute)
                    is FieldVerificationStatus.VERIFIED
                    for attribute in (
                        "allowed_vlans", "active_vlans", "forwarding_vlans",
                    )
                )
            )

        show, convergence, converged = self._converged_ios_query(
            expectation,
            OperationalQueryId.SHOW_INTERFACES_TRUNK,
            cache,
            traverses_expected_vlans,
            timeout_seconds=self._trunk_timeout,
        )
        row = next((
            item for item in parse_show_interfaces_trunk(show.output)
            if self._same_interface(item.interface, expected_interface)
        ), None) if show.executed else None
        interface_status = (
            FieldVerificationStatus.VERIFIED
            if row else FieldVerificationStatus.FAILED
        )
        operational_status = (
            FieldVerificationStatus.VERIFIED
            if row and row.status.casefold() == "trunking"
            else FieldVerificationStatus.FAILED
        )
        fields = {
            "interface": interface_status,
            "status": operational_status,
            "allowed_vlans": vlan_status(show, row, "allowed_vlans"),
            "active_vlans": vlan_status(show, row, "active_vlans"),
            "forwarding_vlans": vlan_status(show, row, "forwarding_vlans"),
        }
        if FieldVerificationStatus.FAILED in fields.values():
            status = ActionExecutionStatus.FAILED
        elif converged and all(
            item is FieldVerificationStatus.VERIFIED for item in fields.values()
        ):
            status = ActionExecutionStatus.VERIFIED
        else:
            status = ActionExecutionStatus.UNOBSERVABLE

        message = show.failure_reason
        if not message and status is ActionExecutionStatus.FAILED and row is not None:
            omissions = []
            for field_name, attribute in (
                ("allowed", "allowed_vlans"),
                ("active", "active_vlans"),
                ("forwarding", "forwarding_vlans"),
            ):
                observed = getattr(row, attribute)
                if observed is None:
                    continue
                missing = sorted(expected_vlans - set(observed))
                if missing:
                    omissions.append(
                        f"{field_name} omitted " + ",".join(map(str, missing))
                    )
            message = "; ".join(omissions)
        if not message and status is ActionExecutionStatus.UNOBSERVABLE:
            message = (
                "The complete registered show interfaces trunk output did not "
                "expose every VLAN traversal section."
            )
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_method="fresh_show_interfaces_trunk",
            fresh_evidence=show.fresh_output_observed,
            fields=fields,
            message=message or ("" if converged else "Trunk convergence timed out."),
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

        def administrative_state_matches(row) -> bool:
            if row is None:
                return False
            status = row.status.casefold()
            if expected_up:
                return status != "administratively down"
            return status == "administratively down"

        show, convergence, converged = self._converged_ios_query(
            expectation,
            OperationalQueryId.SHOW_IP_INTERFACE_BRIEF,
            cache,
            lambda value: bool(
                (row := find_row(value))
                and row.ip_address == expected_ip
                and administrative_state_matches(row)
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
        administrative_state_verified = administrative_state_matches(row)
        operational_up = bool(
            row
            and row.status.casefold() == "up"
            and row.protocol.casefold() == "up"
        )
        verified = address_verified and administrative_state_verified
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.VERIFIED if verified else ActionExecutionStatus.FAILED,
            evidence_method="fresh_show_ip_interface_brief",
            fresh_evidence=show.fresh_output_observed,
            fields={
                "interface": FieldVerificationStatus.VERIFIED if row else FieldVerificationStatus.FAILED,
                "ipv4": FieldVerificationStatus.VERIFIED if address_verified else FieldVerificationStatus.FAILED,
                "administrative_state": (
                    FieldVerificationStatus.VERIFIED
                    if administrative_state_verified else FieldVerificationStatus.FAILED
                ),
                # Carrier/protocol are deliberately absent: this expectation
                # claims interface/IP/admin configuration, not reachability.
                # Serial up/up and end-to-end behavior have their own typed
                # operational gates; emitting supplemental UNKNOWN fields here
                # made an absent future LAN link look like unknown E5 state.
            },
            message=(
                show.failure_reason
                or ("" if operational_up else "Configuration verified; operational link is not up/up.")
                if converged else "L3 configuration convergence timed out."
            ),
            convergence=convergence,
        )

    def _verify_access_port(
        self, expectation: VerificationExpectation,
    ) -> RuntimeVerification:
        """Lee el puerto como OBJETO, que es donde este backend lo expone.

        `show interfaces <if> switchport` trae los mismos campos y fue capturado
        en la misma cualificación, pero pagina incluso acotado a UNA interfaz:
        la captura cerró en `--More--` con `output_complete=False`. Esa consulta
        NO está en `_PAGINATION_QUALIFIED_QUERIES` y no se la agrega por
        conveniencia, así que no puede sostener una afirmación completa. La
        lectura de objeto no tiene pager y devuelve el registro entero o nada.

        Cada campo se decide por separado. Una observación parcial no verifica
        el todo: modo sin VLAN es una afirmación más angosta y se reporta así.

        La VLAN de voz sólo se lee cuando la expectativa la reclama, y con el
        getter MEDIDO sobre este build: `getVoipVlanId` responde `function` en
        los puertos físicos de un switch en PT 9.0.1.0858 y `undefined` en una
        SVI o en un puerto de AP. Que el getter exista no dice que su valor
        signifique lo que su nombre sugiere, así que el lector COMPARA contra lo
        esperado; un valor ilegible o ausente queda UNOBSERVABLE y nunca
        contradice.
        """
        expected_interface = str(expectation.expected["interface"])
        expected_vlan = int(expectation.expected["vlan_id"])
        expected_voice = expectation.expected.get("voice_vlan_id")
        device = json.dumps(expectation.device_name)
        port = json.dumps(expected_interface)
        js = "".join((
            "try{var __d=ipc.network().getDevice(", device, ");",
            "if(!__d){reportResult(JSON.stringify({device_found:false,port_found:false}));}",
            "else{var __p=(typeof __d.getPort===", json.dumps("function"), ")?__d.getPort(", port, "):null;",
            "if(!__p){reportResult(JSON.stringify({device_found:true,port_found:false}));}",
            "else{var __r={device_found:true,port_found:true,complete:true};",
            "try{__r.owner_device_name=String(__p.getOwnerDevice().getName());}catch(__oe){__r.complete=false;}",
            "try{__r.interface=String(__p.getName());}catch(__ne){__r.complete=false;}",
            "try{__r.admin_op_mode=__p.getAdminOpMode();}catch(__me){__r.complete=false;}",
            "try{__r.access_vlan=__p.getAccessVlan();}catch(__ve){__r.complete=false;}",
            # El error del getter de voz se retiene aparte y NO baja `complete`:
            # un puerto sin ese getter no invalida lo que los otros cuatro sí
            # establecieron.
            (
                "try{__r.voice_vlan=__p.getVoipVlanId();}"
                "catch(__vve){__r.voice_vlan_error=String(__vve);}"
                if expected_voice is not None else ""
            ),
            "reportResult(JSON.stringify(__r));}}}",
            "catch(__e){reportResult(", json.dumps("ERROR:"), "+__e);}",
        ))
        observation = self._access_port_observation(js)
        if observation is None or observation.get("port_found") is not True:
            return self._unobservable(
                expectation,
                message=(
                    "The switch port object could not be observed."
                    if observation is not None
                    else "The access-port read-back returned no usable observation."
                ),
                extra_fields=("switchport_mode", "device_identity"),
            )

        # Completa significa dos cosas, y las dos hacen falta: que ningún getter
        # haya fallado, y que estén TODAS las claves del contrato. Un getter que
        # devuelve `undefined` no dispara el `catch`, así que no baja el flag --
        # pero `JSON.stringify` le borra la clave, y esa ausencia es la única
        # señal que queda.
        required_keys = [
            "owner_device_name", "interface", "admin_op_mode", "access_vlan",
        ]
        if expected_voice is not None:
            required_keys.append("voice_vlan")
        complete = observation.get("complete") is True and all(
            key in observation for key in required_keys
        )
        fields = {
            "device_identity": _field_status(
                observation.get("owner_device_name"), _as_text,
                lambda value: value == expectation.device_name,
            ),
            "interface": _field_status(
                observation.get("interface"), _as_text,
                lambda value: self._same_interface(value, expected_interface),
            ),
            "switchport_mode": self._switchport_mode_field(
                observation.get("admin_op_mode"),
            ),
            "vlan_id": _field_status(
                observation.get("access_vlan"), _as_vlan_id,
                lambda value: value == expected_vlan,
            ),
        }
        if expected_voice is not None:
            # Decidido sobre SU propia evidencia. Ningún campo se marca desde
            # otro: `vlan_id` VERIFIED con `voice_vlan_id` UNOBSERVABLE es un
            # resultado válido y más angosto, no una verificación a medias que
            # se pueda redondear hacia arriba.
            fields["voice_vlan_id"] = _field_status(
                observation.get("voice_vlan"), _as_vlan_id,
                lambda value: value == int(expected_voice),
            )
        statuses = set(fields.values())
        if FieldVerificationStatus.FAILED in statuses:
            status = ActionExecutionStatus.FAILED
        elif statuses == {FieldVerificationStatus.VERIFIED} and complete:
            status = ActionExecutionStatus.VERIFIED
        else:
            status = ActionExecutionStatus.PARTIAL
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=status,
            evidence_method="switch_port_object_state",
            fresh_evidence=True,
            fields=fields,
            message=(
                "" if status is ActionExecutionStatus.VERIFIED
                else "The access-port observation did not establish every field."
                + (
                    # Una contradicción conserva el número observado, pero un
                    # payload ilegible sólo expone su tipo. El bridge no puede
                    # convertir un objeto arbitrario en un volcado sin límite.
                    _voice_vlan_evidence_message(observation, int(expected_voice))
                    if expected_voice is not None else ""
                )
            ),
        )

    @staticmethod
    def _switchport_mode_field(value: object) -> FieldVerificationStatus:
        """Un código medido decide; uno que nadie midió no afirma nada."""
        if not isinstance(value, int) or isinstance(value, bool):
            return FieldVerificationStatus.UNOBSERVABLE
        if value == ADMIN_OP_MODE_ACCESS:
            return FieldVerificationStatus.VERIFIED
        if value in MEASURED_ADMIN_OP_MODES:
            return FieldVerificationStatus.FAILED
        return FieldVerificationStatus.UNOBSERVABLE

    def _access_port_observation(self, js: str) -> dict | None:
        raw = self._send_and_wait(js, 6.0)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

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
        """Read back the exact interface the action addressed.

        Walking the port list and taking the first one exposing `getIpAddress`
        only ever agreed with the plan by accident: on a single-port endpoint the
        addressed port IS the first port. On a 7960 (`Switch`, `PC`, logical
        `Vlan1`) or an AccessPoint-PT it is not, and the mismatch was reported as
        a contradiction -- an observation about a port nobody configured, which
        is a strictly stronger claim than the evidence supported.

        A named interface that cannot be found or cannot expose an address is
        UNOBSERVABLE, never FAILED: not having looked at the right thing is not
        the same as having looked and seen the opposite.
        """
        expected = expectation.expected
        name = json.dumps(expectation.device_name)
        interface = str(expected.get("interface") or "")
        if not interface:
            return self._unobservable(
                expectation,
                message="The expectation names no addressed interface to read.",
            )
        wanted = json.dumps(interface)

        def inspect() -> dict:
            js = "".join((
                "try{var d=ipc.network().getDevice(", name, ");",
                "var want=", wanted, ";var p=null;",
                "if(d){for(var i=0;i<d.getPortCount();i++){var c=d.getPortAt(i);",
                "if(c&&typeof c.getName==='function'&&String(c.getName())===want){p=c;break;}}}",
                "var able=!!p&&typeof p.getIpAddress==='function';",
                "var ip=able?String(p.getIpAddress()):'';",
                "var mask=able?String(p.getSubnetMask()):'';",
                # PT 9.0.1 evidence confirms only IP/mask getters. Gateway and DNS
                # remain deliberately unobservable until Cisco API evidence exists.
                "reportResult(JSON.stringify({found:!!d,port_found:!!p,interface:want,",
                # Whether this port has an address channel at all is a separate
                # fact from whether the address on it matches, and it has to
                # survive: `configuration_channel` is overwritten below with the
                # match, and an overwritten flag cannot say "unreadable".
                "address_channel:able,ipv4:ip,netmask:mask,gateway:null,dns:null}));",
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
        if not observed.get("port_found"):
            return self._unobservable(
                expectation,
                message=(
                    f"{interface} was not exposed by {expectation.device_name}, so "
                    "its addressing was never read."
                ),
            )
        if not observed.get("address_channel"):
            # The port exists and carries traffic; it just has no address to
            # read. An AccessPoint-PT is the measured case on build 9.0.1.0858:
            # both its ports come up powered and neither exposes `getIpAddress`,
            # because it bridges rather than hosts. Treating the empty string
            # that comes back as a wrong address states more than was seen.
            return self._unobservable(
                expectation,
                # Distinct from a generic observability limit and from an
                # interface that was not found: this port is present, and the
                # device model has no address getter to ask. A governed ceiling
                # can admit that exact case without also admitting a missing
                # interface, which would hide a real topology error.
                evidence_method="structured_endpoint_getters_absent",
                message=(
                    f"{interface} on {expectation.device_name} exposes no address "
                    "channel, so nothing about its addressing was read."
                ),
            )
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
    def _unobservable(
        expectation: VerificationExpectation,
        *,
        message: str = "",
        extra_fields: tuple[str, ...] = (),
        evidence_method: str = "runtime_observability_limit",
    ) -> RuntimeVerification:
        fields = {
            field: FieldVerificationStatus.UNOBSERVABLE
            for field in (*expectation.expected, *extra_fields)
        }
        return RuntimeVerification(
            expectation_id=expectation.id,
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_method=evidence_method,
            fresh_evidence=False,
            fields=fields,
            message=message or (
                f"No independent getter is registered for {expectation.kind.value}."
            ),
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
        return same_interface_name(observed, expected)


def _field_status(value: object, read, matches) -> FieldVerificationStatus:
    """Ausente no es contradicho. ILEGIBLE tampoco. Legible y distinto sí.

    Los tres estados son distintos y colapsarlos en dos fue un defecto real:
    `getAccessVlan()` vuelve sin envolver, así que un retorno que
    `JSON.stringify` renderice como `"742"` o `{}` llegaba acá y salía FAILED
    -- diciéndole al operador que el puerto CONTRADICE lo esperado a partir de
    una observación que no estableció nada. `read` devuelve el valor
    normalizado o `None` si el tipo no es el que el getter promete.
    """
    if value is None:
        return FieldVerificationStatus.UNOBSERVABLE
    readable = read(value)
    if readable is None:
        return FieldVerificationStatus.UNOBSERVABLE
    return (
        FieldVerificationStatus.VERIFIED if matches(readable)
        else FieldVerificationStatus.FAILED
    )


def _voice_vlan_evidence_message(observation: dict, expected: int) -> str:
    """Describe evidencia de voz con forma tipada y acotada.

    Un número legible se conserva para diagnosticar una contradicción. Un error
    del getter o un valor estructurado sólo aporta su clase de evidencia; nunca
    se interpola el error ni el objeto entregado por Packet Tracer.
    """
    if "voice_vlan" not in observation:
        observed = (
            "getter unavailable"
            if "voice_vlan_error" in observation else "unavailable"
        )
    else:
        raw = observation["voice_vlan"]
        readable = _as_vlan_id(raw)
        observed = (
            f"observed {readable}"
            if readable is not None
            else f"unreadable {type(raw).__name__[:32]}"
        )
    return f" Voice VLAN evidence: {observed} (expected {expected})."


def _as_text(value: object) -> str | None:
    """Un nombre es una cadena. Un número o un objeto no es un nombre ilegible:
    es algo que no se puede leer como nombre."""
    return value if isinstance(value, str) and value else None


def _as_vlan_id(value: object) -> int | None:
    """Un id de VLAN es un entero. Un float íntegro es el mismo número; una
    cadena, un booleano o un objeto no son un id que se pueda comparar."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None
