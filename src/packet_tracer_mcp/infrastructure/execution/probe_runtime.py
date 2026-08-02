"""Adaptador bridge E3.5 con operaciones estructuradas sobre devices temporales."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from ...application.use_cases.capability_discovery import PacketTracerProbeRuntime
from ...domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from ...domain.enterprise.models.discovery import (
    CapabilityProbeResult,
    ProbeDefinition,
    ProbeExecutionStatus,
    RuntimeDeviceDescriptor,
    RuntimeDeviceObservation,
    RuntimePortDescriptor,
)
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
    ) -> None:
        self._send_and_wait = send_and_wait
        self._packet_tracer_version = packet_tracer_version

    def packet_tracer_version(self) -> str | None:
        return self._packet_tracer_version

    def discover_models(self) -> list[RuntimeDeviceDescriptor] | None:
        return None

    def create_temporary_device(self, runtime_model: str, temporary_name: str) -> RuntimeDeviceObservation:
        model = json.dumps(runtime_model)
        name = json.dumps(temporary_name)
        js = (
            "try{"
            f"var __model={model};var __name={name};var __net=ipc.network();"
            "if(__net.getDevice(__name)){reportResult(JSON.stringify({error:'duplicate probe name'}));}"
            "else if(typeof addDevice!=='function'){reportResult(JSON.stringify({error:'addDevice unavailable'}));}"
            "else{addDevice(__name,__model,9000,9000);var __d=__net.getDevice(__name);"
            "if(!__d){reportResult(JSON.stringify({found:false}));}else{var __ports=[];"
            "for(var __i=0;__i<__d.getPortCount();__i++){try{var __p=__d.getPortAt(__i);"
            "if(__p){__ports.push({name:__p.getName(),bandwidth_kbps:(typeof __p.getBandwidth==='function')?__p.getBandwidth():null});}}catch(__pe){}}"
            "reportResult(JSON.stringify({found:true,runtime_id:(typeof __d.getModel==='function')?__d.getModel():__model,display_name:__d.getName(),ports:__ports}));}}"
            "}catch(__e){reportResult('ERROR:'+__e); }"
        )
        data = self._json_result(js, timeout=15.0)
        if data.get("error"):
            return RuntimeDeviceObservation(error=str(data["error"]))
        return RuntimeDeviceObservation(
            found=bool(data.get("found")),
            runtime_id=data.get("runtime_id"),
            display_name=data.get("display_name", ""),
            ports=[self._port_descriptor(item) for item in data.get("ports", [])],
        )

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
            raw_summary="VlanManager present." if status is CapabilityStatus.SUPPORTED else "VlanManager is absent on the probe device.",
        )

    def _probe_vlan(self, temporary_name: str, definition: ProbeDefinition) -> CapabilityProbeResult:
        name = json.dumps(temporary_name)
        enable = json.dumps("enable")
        configure = json.dumps("configure terminal")
        create_vlan = json.dumps("vlan " + str(CAPABILITY_PROBE_VLAN_ID))
        vlan_name = json.dumps("name " + CAPABILITY_PROBE_VLAN_NAME)
        end = json.dumps("end")
        remove_vlan = json.dumps("no vlan " + str(CAPABILITY_PROBE_VLAN_ID))
        vlan_id = json.dumps(CAPABILITY_PROBE_VLAN_ID)
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");",
            "var __vm=__d&&typeof __d.getProcess==='function'?__d.getProcess('VlanManager'):null;",
            "var __cp=__d&&typeof __d.getCommandPrompt==='function'?__d.getCommandPrompt():null;",
            "if(!__d||!__vm||!__cp||typeof __cp.enterCommand!=='function'){reportResult(JSON.stringify({ready:false,reason:'Temporary device lacks a usable CommandPrompt.'}));}",
            "else{__cp.enterCommand(", enable, ");__cp.enterCommand(", configure, ");",
            "__cp.enterCommand(", create_vlan, ");__cp.enterCommand(", vlan_name, ");__cp.enterCommand(", end, ");",
            "var __present=false;for(var __i=0;__i<__vm.getVlanCount();__i++){",
            "var __v=__vm.getVlanAt(__i);if(__v&&__v.getVlanNumber()===", vlan_id, "){__present=true;}}",
            "__cp.enterCommand(", enable, ");__cp.enterCommand(", configure, ");__cp.enterCommand(", remove_vlan, ");__cp.enterCommand(", end, ");",
            "var __left=false;for(var __j=0;__j<__vm.getVlanCount();__j++){",
            "var __cv=__vm.getVlanAt(__j);if(__cv&&__cv.getVlanNumber()===", vlan_id, "){__left=true;}}",
            "reportResult(JSON.stringify({ready:true,configured:__present,cleanup:!__left}));}",
            "}catch(__e){reportResult('ERROR:'+__e);}",
        ))
        try:
            data = self._json_result(js, timeout=20.0)
        except TimeoutError as exc:
            return self._failure(definition, ProbeExecutionStatus.TIMEOUT, str(exc))
        except RuntimeError as exc:
            return self._failure(definition, ProbeExecutionStatus.PACKET_TRACER_ERROR, str(exc))
        if not data.get("ready"):
            return self._failure(
                definition, ProbeExecutionStatus.SKIPPED,
                str(data.get("reason") or "VlanManager or CommandPrompt is unavailable."),
            )
        if not data.get("configured") or not data.get("cleanup"):
            return self._failure(
                definition, ProbeExecutionStatus.VERIFY_FAILED,
                "VLAN configure/read-back/cleanup evidence was incomplete.", configured=bool(data.get("configured")),
            )
        return CapabilityProbeResult(
            probe_id=definition.id, model="", capability=definition.capability,
            status=CapabilityStatus.SUPPORTED, execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE, configured=True, verified=True,
            observed_value=CAPABILITY_PROBE_VLAN_ID,
            raw_summary="VLAN configured, read back through VlanManager, and removed successfully.",
        )

    def _probe_layer3(self, temporary_name: str, definition: ProbeDefinition) -> CapabilityProbeResult:
        name = json.dumps(temporary_name)
        address = json.dumps(CAPABILITY_PROBE_IPV4_ADDRESS)
        mask = json.dumps(CAPABILITY_PROBE_IPV4_MASK)
        vlan_id = json.dumps(CAPABILITY_PROBE_VLAN_ID)
        enable = json.dumps("enable")
        configure = json.dumps("configure terminal")
        end = json.dumps("end")
        no_shutdown = json.dumps("no shutdown")
        no_ip = json.dumps("no ip address")
        shutdown = json.dumps("shutdown")
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");",
            "var __model=__d&&typeof __d.getModel==='function'?String(__d.getModel()):'';",
            "var __ip=", address, ";var __mask=", mask, ";var __vlanId=", vlan_id, ";",
            "var __cp=__d&&typeof __d.getCommandPrompt==='function'?__d.getCommandPrompt():null;",
            "if(!__d||!__cp||typeof __cp.enterCommand!=='function'){reportResult(JSON.stringify({ready:false,reason:'Temporary device lacks a usable CommandPrompt.'}));}",
            "else if(__model.indexOf('2911')>=0){var __p=null;for(var __n=0;__n<__d.getPortCount();__n++){var __candidate=__d.getPortAt(__n);if(__candidate&&String(__candidate.getName()).indexOf('Ethernet')>=0){__p=__candidate;break;}}var __if=__p&&__p.getName();",
            "if(!__if){reportResult(JSON.stringify({ready:false}));}else{",
            "__cp.enterCommand(", enable, ");__cp.enterCommand(", configure, ");__cp.enterCommand('interface '+__if);__cp.enterCommand('ip address '+__ip+' '+__mask);__cp.enterCommand(", no_shutdown, ");__cp.enterCommand(", end, ");",
            "var __configured=__p.getIpAddress()===__ip&&__p.getSubnetMask()===__mask;",
            "__cp.enterCommand(", enable, ");__cp.enterCommand(", configure, ");__cp.enterCommand('interface '+__if);__cp.enterCommand(", no_ip, ");__cp.enterCommand(", shutdown, ");__cp.enterCommand(", end, ");",
            "var __cleanup=__p.getIpAddress()!==__ip;",
            "reportResult(JSON.stringify({ready:true,configured:__configured,cleanup:__cleanup,model:__model}));}}",
            "else if(__model.indexOf('3560')>=0){",
            "__cp.enterCommand(", enable, ");__cp.enterCommand(", configure, ");__cp.enterCommand('vlan '+__vlanId);__cp.enterCommand('interface vlan '+__vlanId);__cp.enterCommand('ip address '+__ip+' '+__mask);__cp.enterCommand(", no_shutdown, ");__cp.enterCommand(", end, ");",
            "var __vp=null;for(var __i=0;__i<__d.getPortCount();__i++){var __x=__d.getPortAt(__i);if(__x&&String(__x.getName()).toLowerCase()==='vlan'+__vlanId){__vp=__x;}}",
            "var __configured=!!__vp&&__vp.getIpAddress()===__ip&&__vp.getSubnetMask()===__mask;",
            "__cp.enterCommand(", enable, ");__cp.enterCommand(", configure, ");__cp.enterCommand('interface vlan '+__vlanId);__cp.enterCommand(", no_ip, ");__cp.enterCommand(", shutdown, ");__cp.enterCommand(", end, ");",
            "var __cleanup=!__vp||__vp.getIpAddress()!==__ip;",
            "reportResult(JSON.stringify({ready:true,configured:__configured,cleanup:__cleanup,model:__model}));}",
            "else{reportResult(JSON.stringify({ready:false,model:__model}));}",
            "}catch(__e){reportResult('ERROR:'+__e);}",
        ))
        try:
            data = self._json_result(js, timeout=20.0)
        except TimeoutError as exc:
            return self._failure(definition, ProbeExecutionStatus.TIMEOUT, str(exc))
        except RuntimeError as exc:
            return self._failure(definition, ProbeExecutionStatus.PACKET_TRACER_ERROR, str(exc))
        if not data.get("ready"):
            return self._failure(
                definition, ProbeExecutionStatus.SKIPPED,
                str(data.get("reason") or "No model-specific IPv4 configure/read-back probe is registered for this device."),
            )
        if not data.get("configured") or not data.get("cleanup"):
            return self._failure(
                definition, ProbeExecutionStatus.VERIFY_FAILED,
                "IPv4 configure/read-back/cleanup evidence was incomplete.", configured=bool(data.get("configured")),
            )
        return CapabilityProbeResult(
            probe_id=definition.id, model="", capability=definition.capability,
            status=CapabilityStatus.SUPPORTED, execution_status=ProbeExecutionStatus.VERIFIED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE, configured=True, verified=True,
            raw_summary="IPv4 interface configured, read back, and cleared successfully.",
        )

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
