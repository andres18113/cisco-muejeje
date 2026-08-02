"""Adaptador bridge E3.5 con operaciones estructuradas sobre devices temporales."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from ...application.use_cases.capability_discovery import PacketTracerProbeRuntime
from ...domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from ...domain.enterprise.models.discovery import (
    CapabilityVerificationMethod,
    CapabilityProbeResult,
    ProbeDefinition,
    ProbeExecutionStatus,
    RuntimeDeviceDescriptor,
    RuntimeDeviceObservation,
    RuntimePortDescriptor,
)
from ...infrastructure.catalog.devices import resolve_model
from ...shared.constants import PT_DEVICE_TYPE, PT_DEVICE_TYPE_DEFAULT
from .configuration_runtime import PacketTracerConfigurationRuntime
from .device_lifecycle import DeviceReadinessWaiter, StateConvergenceWaiter
from ...shared.constants import (
    CAPABILITY_PROBE_IPV4_ADDRESS,
    CAPABILITY_PROBE_IPV4_MASK,
    CAPABILITY_PROBE_VLAN_ID,
    CAPABILITY_PROBE_VLAN_NAME,
)


_INTERFACE_TYPE = re.compile(r"^[A-Za-z-]+")


class PacketTracerBridgeProbeRuntime(PacketTracerProbeRuntime):
    """Implementación live mínima basada exclusivamente en APIs ya usadas aquí.

    Packet Tracer no expone una enumeración de modelos ni una versión verificable
    en la superficie confirmada del bridge. Por eso ambas quedan ausentes hasta
    que una futura build aporte evidencia, en vez de inventar una API.
    """

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        packet_tracer_version: str | None = None,
        send: Callable[[str], bool] | None = None,
    ) -> None:
        self._send_and_wait = send_and_wait
        self._packet_tracer_version = packet_tracer_version
        self._configuration = PacketTracerConfigurationRuntime(send or (lambda _: False))

    def packet_tracer_version(self) -> str | None:
        return self._packet_tracer_version

    def discover_models(self) -> list[RuntimeDeviceDescriptor] | None:
        return None

    def create_temporary_device(self, runtime_model: str, temporary_name: str) -> RuntimeDeviceObservation:
        model = json.dumps(runtime_model)
        name = json.dumps(temporary_name)
        catalog_model = resolve_model(runtime_model)
        device_type = PT_DEVICE_TYPE.get(catalog_model.category, PT_DEVICE_TYPE_DEFAULT) if catalog_model else PT_DEVICE_TYPE_DEFAULT
        js = (
            "try{"
            f"var __model={model};var __name={name};var __type={device_type};var __net=ipc.network();"
            "if(__net.getDevice(__name)){reportResult(JSON.stringify({error:'duplicate probe name'}));}"
            "else if(typeof lwAddDevice!=='function'){reportResult(JSON.stringify({error:'lwAddDevice unavailable'}));}"
            "else{lwAddDevice(__name,__type,__model,9000,9000);var __d=__net.getDevice(__name);"
            "if(!__d){reportResult(JSON.stringify({found:false}));}else{var __ports=[];"
            "for(var __i=0;__i<__d.getPortCount();__i++){try{var __p=__d.getPortAt(__i);"
            "if(__p){__ports.push({name:__p.getName(),bandwidth_kbps:(typeof __p.getBandwidth==='function')?__p.getBandwidth():null});}}catch(__pe){}}"
            "reportResult(JSON.stringify({found:true,runtime_id:(typeof __d.getModel==='function')?__d.getModel():__model,display_name:__d.getName(),ports:__ports}));}}"
            "}catch(__e){reportResult('ERROR:'+__e); }"
        )
        data = self._json_result(js, timeout=15.0)
        if data.get("error"):
            return RuntimeDeviceObservation(error=str(data["error"]))
        observation = RuntimeDeviceObservation(
            found=bool(data.get("found")),
            runtime_id=data.get("runtime_id"),
            display_name=data.get("display_name", ""),
            ports=[self._port_descriptor(item) for item in data.get("ports", [])],
        )
        if observation.found:
            return observation.model_copy(update={"initialization": self._wait_for_readiness(temporary_name)})
        return observation

    def delete_temporary_device(self, temporary_name: str) -> bool:
        name = json.dumps(temporary_name)
        js = (
            "try{"
            f"var __name={name};var __d=ipc.network().getDevice(__name);"
            "if(!__d){reportResult(JSON.stringify({deleted:true}));}"
            "else{var __lw=ipc.appWindow().getActiveWorkspace().getLogicalWorkspace();"
            "if(typeof __lw.removeDevice!=='function'){reportResult(JSON.stringify({deleted:false}));}"
            "else{__lw.removeDevice(__d.getName());reportResult(JSON.stringify({deleted:!ipc.network().getDevice(__name)}));}}"
            "}catch(__e){reportResult('ERROR:'+__e); }"
        )
        return bool(self._json_result(js, timeout=10.0).get("deleted"))

    def probe_capability(
        self, temporary_name: str, capability: str, definition: ProbeDefinition
    ) -> CapabilityProbeResult:
        """Ejecuta sólo probes configure/read-back con APIs ya presentes en MCP."""
        if capability == "layer2":
            return self._probe_vlan_manager(temporary_name, definition)
        if capability == "configuration_channel":
            return self._probe_configuration_channel(temporary_name, definition)
        if capability == "supports_vlan":
            return self._probe_vlan(temporary_name, definition)
        if capability == "layer3":
            return self._probe_layer3(temporary_name, definition)
        return CapabilityProbeResult(
            probe_id=definition.id,
            model="",
            capability=capability,
            execution_status=ProbeExecutionStatus.SKIPPED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE,
            failure_reason=(
                "No verified configure/read-back API is available for this logical probe "
                "in the current PT bridge."
            ),
        )

    def _probe_configuration_channel(self, temporary_name: str, definition: ProbeDefinition) -> CapabilityProbeResult:
        readiness = self._wait_for_readiness(temporary_name)
        if not readiness.configuration_channel:
            return self._failure(
                definition, ProbeExecutionStatus.TIMEOUT if readiness.state.value == "timeout" else ProbeExecutionStatus.SKIPPED,
                readiness.failure_reason or "The official configureIosDevice channel was not ready for the temporary device.",
            )
        return CapabilityProbeResult(
            probe_id=definition.id, model="", capability=definition.capability,
            status=CapabilityStatus.SUPPORTED, execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME, verified=True,
            verification_method=CapabilityVerificationMethod.DIRECT_RUNTIME_API,
            raw_summary=(
                "Official configureIosDevice channel available after "
                f"{readiness.attempts} readiness check(s); CommandPrompt present={readiness.command_prompt}."
            ),
        )

    def _probe_vlan_manager(self, temporary_name: str, definition: ProbeDefinition) -> CapabilityProbeResult:
        name = json.dumps(temporary_name)
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");",
            "var __vm=__d&&typeof __d.getProcess==='function'?__d.getProcess('VlanManager'):null;",
            "reportResult(JSON.stringify({found:!!__d,vlan_manager:!!__vm}));",
            "}catch(__e){reportResult('ERROR:'+__e);}",
        ))
        try:
            data = self._json_result(js, timeout=12.0)
        except TimeoutError as exc:
            return self._failure(definition, ProbeExecutionStatus.TIMEOUT, str(exc))
        except RuntimeError as exc:
            return self._failure(definition, ProbeExecutionStatus.PACKET_TRACER_ERROR, str(exc))
        status = CapabilityStatus.SUPPORTED if data.get("vlan_manager") else CapabilityStatus.UNSUPPORTED
        return CapabilityProbeResult(
            probe_id=definition.id, model="", capability=definition.capability, status=status,
            execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE, verified=True,
            verification_method=CapabilityVerificationMethod.OBJECT_STATE,
            raw_summary="VlanManager present." if status is CapabilityStatus.SUPPORTED else "VlanManager is absent on the probe device.",
        )

    def _probe_vlan(self, temporary_name: str, definition: ProbeDefinition) -> CapabilityProbeResult:
        create = "\n".join(("enable", "configure terminal", f"vlan {CAPABILITY_PROBE_VLAN_ID}", f"name {CAPABILITY_PROBE_VLAN_NAME}", "end"))
        if not self._configuration.configure_ios(temporary_name, create):
            return self._failure(definition, ProbeExecutionStatus.BRIDGE_ERROR, "Official configuration channel rejected the VLAN payload.")
        configured = self._wait_for_vlan(temporary_name, present=True)
        cleanup_payload = "\n".join(("enable", "configure terminal", f"no vlan {CAPABILITY_PROBE_VLAN_ID}", "end"))
        cleanup_sent = self._configuration.configure_ios(temporary_name, cleanup_payload)
        cleanup = cleanup_sent and self._wait_for_vlan(temporary_name, present=False)
        if not configured or not cleanup:
            return self._failure(definition, ProbeExecutionStatus.VERIFY_FAILED, "VLAN configure/read-back/cleanup evidence was incomplete.", configured=configured)
        return CapabilityProbeResult(
            probe_id=definition.id, model="", capability=definition.capability, status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED, evidence_source=EvidenceSource.CONTROLLED_PROBE,
            configured=True, verified=True, observed_value=CAPABILITY_PROBE_VLAN_ID,
            verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
            raw_summary="VLAN configured through configureIosDevice, read back through VlanManager, and removed successfully.",
        )

    def _probe_layer3(self, temporary_name: str, definition: ProbeDefinition) -> CapabilityProbeResult:
        target = self._layer3_target(temporary_name)
        if target is None:
            return self._failure(definition, ProbeExecutionStatus.SKIPPED, "No model-specific IPv4 probe target is available for this device.")
        interface, is_svi = target
        lines = ["enable", "configure terminal"]
        if is_svi:
            lines.append(f"vlan {CAPABILITY_PROBE_VLAN_ID}")
        lines.extend((f"interface {interface}", f"ip address {CAPABILITY_PROBE_IPV4_ADDRESS} {CAPABILITY_PROBE_IPV4_MASK}", "no shutdown", "end"))
        if not self._configuration.configure_ios(temporary_name, "\n".join(lines)):
            return self._failure(definition, ProbeExecutionStatus.BRIDGE_ERROR, "Official configuration channel rejected the IPv4 payload.")
        configured = self._wait_for_ip(temporary_name, interface, present=True)
        cleanup = "\n".join(("enable", "configure terminal", f"interface {interface}", "no ip address", "shutdown", "end"))
        cleanup_sent = self._configuration.configure_ios(temporary_name, cleanup)
        cleaned = cleanup_sent and self._wait_for_ip(temporary_name, interface, present=False)
        if not configured or not cleaned:
            return self._failure(definition, ProbeExecutionStatus.VERIFY_FAILED, "IPv4 configure/read-back/cleanup evidence was incomplete.", configured=configured)
        return CapabilityProbeResult(
            probe_id=definition.id, model="", capability=definition.capability, status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED, evidence_source=EvidenceSource.CONTROLLED_PROBE,
            configured=True, verified=True, verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
            raw_summary="IPv4 interface configured through configureIosDevice, read back through port state, and cleared successfully.",
        )

    def _wait_for_readiness(self, temporary_name: str):
        return DeviceReadinessWaiter(lambda: self._initialization_state(temporary_name)).wait()

    def _initialization_state(self, temporary_name: str) -> dict:
        name = json.dumps(temporary_name)
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");",
            "var __cp=__d&&typeof __d.getCommandPrompt==='function'?__d.getCommandPrompt():null;",
            "var __vm=__d&&typeof __d.getProcess==='function'?__d.getProcess('VlanManager'):null;",
            "var __power=__d&&typeof __d.getPower==='function'?!!__d.getPower():null;",
            "reportResult(JSON.stringify({found:!!__d,power:__power,command_prompt:!!__cp,configuration_channel:!!__d&&typeof configureIosDevice==='function',components_seen:__vm?['VlanManager']:[]}));",
            "}catch(__e){reportResult('ERROR:'+__e);}",
        ))
        return self._json_result(js, timeout=3.0)

    def _wait_for_vlan(self, temporary_name: str, *, present: bool) -> bool:
        name = json.dumps(temporary_name)
        vlan = json.dumps(CAPABILITY_PROBE_VLAN_ID)
        def inspect() -> dict:
            js = "".join((
                "try{var __d=ipc.network().getDevice(", name, ");var __vm=__d&&typeof __d.getProcess==='function'?__d.getProcess('VlanManager'):null;var __found=false;",
                "if(__vm){for(var __i=0;__i<__vm.getVlanCount();__i++){var __v=__vm.getVlanAt(__i);if(__v&&__v.getVlanNumber()===", vlan, "){__found=true;}}}",
                "reportResult(JSON.stringify({found:!!__d,configuration_channel:__found===", "true" if present else "false", "}));}catch(__e){reportResult('ERROR:'+__e);}",
            ))
            return self._json_result(js, timeout=3.0)
        return StateConvergenceWaiter(inspect, timeout_seconds=8.0).wait().configuration_channel

    def _layer3_target(self, temporary_name: str) -> tuple[str, bool] | None:
        name = json.dumps(temporary_name)
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");var __model=__d&&typeof __d.getModel==='function'?String(__d.getModel()):'';var __iface='';var __svi=false;",
            "if(__model.indexOf('2911')>=0){for(var __i=0;__d&&__i<__d.getPortCount();__i++){var __p=__d.getPortAt(__i);if(__p&&String(__p.getName()).indexOf('Ethernet')>=0){__iface=__p.getName();break;}}}",
            "else if(__model.indexOf('3560')>=0){__iface='Vlan", str(CAPABILITY_PROBE_VLAN_ID), "';__svi=true;}",
            "reportResult(JSON.stringify({interface:__iface,svi:__svi}));}catch(__e){reportResult('ERROR:'+__e);}",
        ))
        data = self._json_result(js, timeout=5.0)
        interface = str(data.get("interface") or "")
        return (interface, bool(data.get("svi"))) if interface else None

    def _wait_for_ip(self, temporary_name: str, interface: str, *, present: bool) -> bool:
        name, port = json.dumps(temporary_name), json.dumps(interface)
        def inspect() -> dict:
            js = "".join((
                "try{var __d=ipc.network().getDevice(", name, ");var __p=__d&&typeof __d.getPort==='function'?__d.getPort(", port, "):null;",
                "if(!__p&&__d){for(var __i=0;__i<__d.getPortCount();__i++){var __candidate=__d.getPortAt(__i);if(__candidate&&String(__candidate.getName()).toLowerCase()===String(", port, ").toLowerCase()){__p=__candidate;break;}}}",
                "var __match=!!__p&&__p.getIpAddress()===", json.dumps(CAPABILITY_PROBE_IPV4_ADDRESS), "&&__p.getSubnetMask()===", json.dumps(CAPABILITY_PROBE_IPV4_MASK), ";",
                "reportResult(JSON.stringify({found:!!__d,configuration_channel:__match===", "true" if present else "false", "}));}catch(__e){reportResult('ERROR:'+__e);}",
            ))
            return self._json_result(js, timeout=3.0)
        return StateConvergenceWaiter(inspect, timeout_seconds=8.0).wait().configuration_channel

    @staticmethod
    def _failure(
        definition: ProbeDefinition, execution_status: ProbeExecutionStatus, reason: str, configured: bool = False,
    ) -> CapabilityProbeResult:
        return CapabilityProbeResult(
            probe_id=definition.id, model="", capability=definition.capability,
            execution_status=execution_status, evidence_source=EvidenceSource.CONTROLLED_PROBE,
            configured=configured, failure_reason=reason,
        )

    def _json_result(self, js: str, timeout: float) -> dict:
        raw = self._send_and_wait(js, timeout)
        if raw is None:
            raise TimeoutError("Packet Tracer bridge did not respond before the probe timeout.")
        if raw.startswith(("ERROR:", "PT_ERROR:")):
            raise RuntimeError(raw.split(":", 1)[1].strip())
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            summary = raw.replace("\r", " ").replace("\n", " ")[:300]
            raise RuntimeError("Packet Tracer returned malformed probe JSON: " + summary) from exc
        if not isinstance(value, dict):
            raise RuntimeError("Packet Tracer returned a non-object probe response.")
        return value

    @staticmethod
    def _port_descriptor(value: dict) -> RuntimePortDescriptor:
        name = str(value.get("name", ""))
        match = _INTERFACE_TYPE.match(name)
        bandwidth = value.get("bandwidth_kbps")
        return RuntimePortDescriptor(
            name=name,
            interface_type=match.group(0) if match else "",
            speed=f"{bandwidth}kbps" if isinstance(bandwidth, (int, float)) else "",
            evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
            poe_status=CapabilityStatus.UNKNOWN,
        )
