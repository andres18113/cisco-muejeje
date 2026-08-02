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
        """No ejecuta CLI hasta contar con una vía configure/read-back confirmada.

        El registry sí modela las dependencias. Devolver `SKIPPED` conserva
        `UNKNOWN`, que es más seguro que convertir una ausencia de API en false.
        """
        return CapabilityProbeResult(
            probe_id=definition.id,
            model="",
            capability=capability,
            execution_status=ProbeExecutionStatus.SKIPPED,
            evidence_source=EvidenceSource.CONTROLLED_PROBE,
            failure_reason="No verified configure/read-back API is available for this logical probe in the current PT bridge.",
        )

    def _json_result(self, js: str, timeout: float) -> dict:
        raw = self._send_and_wait(js, timeout)
        if raw is None:
            raise TimeoutError("Packet Tracer bridge did not respond before the probe timeout.")
        if raw.startswith("ERROR:"):
            raise RuntimeError(raw[6:])
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Packet Tracer returned malformed probe JSON.") from exc
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
