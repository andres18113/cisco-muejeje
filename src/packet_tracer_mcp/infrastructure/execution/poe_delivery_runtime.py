"""Packet Tracer fixture adapter for governed PoE delivery qualification.

This module deliberately observes only fixture identity and exact link
endpoints.  Visible powered-device delivery is supplied by the independent
observer owned by the application use case; PT's administrative power getters
are not delivery evidence and are never queried here.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from ...domain.enterprise.models.poe_delivery import (
    PoEDeliveryDeviceIdentity,
    PoEDeliveryLinkEndpoint,
    PoEDeliveryLinkIdentity,
)
from ...infrastructure.catalog.devices import resolve_model
from ...shared.constants import (
    PT_CONNECT_TYPE_DEFAULT,
    PT_DEVICE_TYPE,
    PT_DEVICE_TYPE_DEFAULT,
)
from .probe_runtime import PacketTracerBridgeProbeRuntime


class PacketTracerPoEDeliveryFixtureRuntime:
    """Create and read back the narrow temporary PoE qualification fixture."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        packet_tracer_build: str | None = None,
    ) -> None:
        self._send_and_wait = send_and_wait
        self._packet_tracer_build = packet_tracer_build
        self._inventory_runtime = PacketTracerBridgeProbeRuntime(
            send_and_wait,
            packet_tracer_version=packet_tracer_build,
        )
        # A creation timeout can mean that PT mutated before the acknowledgement
        # was lost.  Record the name before transport so cleanup remains possible.
        self._attempted_device_names: set[str] = set()

    def packet_tracer_build(self) -> str | None:
        return self._packet_tracer_build

    def inventory_fingerprint(self) -> str:
        return self._inventory_runtime.inventory_fingerprint()

    def wait_for_inventory_fingerprint(self, expected: str) -> str:
        return self._inventory_runtime.wait_for_inventory_fingerprint(expected)

    def create_device(
        self,
        model: str,
        temporary_name: str,
        required_ports: tuple[str, ...],
    ) -> PoEDeliveryDeviceIdentity:
        """Create one device and observe its exact model/name/required ports.

        This is intentionally separate from ``create_temporary_device``: the
        ordinary probe readiness path reads power control getters, which are not
        an observation of powered-endpoint delivery.
        """

        catalog_model = resolve_model(model)
        device_type = (
            PT_DEVICE_TYPE.get(catalog_model.category, PT_DEVICE_TYPE_DEFAULT)
            if catalog_model is not None
            else PT_DEVICE_TYPE_DEFAULT
        )
        model_literal = json.dumps(model, ensure_ascii=False)
        name_literal = json.dumps(temporary_name, ensure_ascii=False)
        ports_literal = json.dumps(
            list(required_ports), ensure_ascii=False, separators=(",", ":"),
        )
        type_literal = json.dumps(device_type)
        script = "".join((
            "var __attempted=false;try{var __model=", model_literal, ",__name=", name_literal,
            ",__required=", ports_literal, ",__type=", type_literal,
            ",__net=ipc.network();",
            "if(__net.getDevice(__name)){reportResult(JSON.stringify({found:false,creation_attempted:false,error:'duplicate fixture name'}));}",
            "else if(typeof lwAddDevice!=='function'){reportResult(JSON.stringify({found:false,creation_attempted:false,error:'lwAddDevice unavailable'}));}",
            "else{__attempted=true;lwAddDevice(__name,__type,__model,9000,9000);var __d=__net.getDevice(__name);",
            "if(!__d){reportResult(JSON.stringify({found:false,creation_attempted:true,error:'created device not found'}));}",
            "else{var __ports=[],__missing=[];for(var __i=0;__i<__required.length;__i++){",
            "var __requested=__required[__i],__p=null;try{__p=__d.getPort(__requested);}catch(__pe){}",
            "if(!__p){__missing.push(__requested);}else{__ports.push(String(__p.getName()));}}",
            "reportResult(JSON.stringify({found:true,creation_attempted:true,name:String(__d.getName()),",
            "model:(typeof __d.getModel==='function'?String(__d.getModel()):''),",
            "ports:__ports,missing_ports:__missing}));}}}",
            "catch(__e){reportResult(JSON.stringify({found:false,creation_attempted:__attempted,error:String(__e)}));}",
        ))
        self._attempted_device_names.add(temporary_name)
        data = self._json_object(script, timeout=15.0)
        if data.get("creation_attempted") is False:
            self._attempted_device_names.discard(temporary_name)
        error = data.get("error")
        if error:
            raise RuntimeError(f"Packet Tracer could not create PoE fixture device: {error}")
        if data.get("found") is not True or data.get("creation_attempted") is not True:
            raise RuntimeError("Packet Tracer did not observe the created PoE fixture device.")

        name = data.get("name")
        observed_model = data.get("model")
        ports = data.get("ports")
        missing_ports = data.get("missing_ports")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(observed_model, str)
            or not observed_model
            or not isinstance(ports, list)
            or not all(isinstance(item, str) and item for item in ports)
            or len(set(ports)) != len(ports)
            or not isinstance(missing_ports, list)
            or not all(isinstance(item, str) for item in missing_ports)
        ):
            raise RuntimeError("Packet Tracer returned malformed PoE fixture identity data.")
        if missing_ports or not set(required_ports).issubset(ports):
            raise RuntimeError(
                "Packet Tracer did not observe every required PoE fixture port."
            )
        return PoEDeliveryDeviceIdentity(
            name=name,
            model=observed_model,
            observed_ports=ports,
        )

    def create_link(
        self,
        switch: PoEDeliveryDeviceIdentity,
        switch_port: str,
        endpoint: PoEDeliveryDeviceIdentity,
        endpoint_port: str,
    ) -> PoEDeliveryLinkIdentity:
        """Create a link and require matching two-ended endpoint read-back."""

        switch_name = json.dumps(switch.name, ensure_ascii=False)
        switch_model = json.dumps(switch.model, ensure_ascii=False)
        switch_port_literal = json.dumps(switch_port, ensure_ascii=False)
        endpoint_name = json.dumps(endpoint.name, ensure_ascii=False)
        endpoint_model = json.dumps(endpoint.model, ensure_ascii=False)
        endpoint_port_literal = json.dumps(endpoint_port, ensure_ascii=False)
        cable = json.dumps(PT_CONNECT_TYPE_DEFAULT)
        script = "".join((
            "try{var __sn=", switch_name, ",__sm=", switch_model,
            ",__sp=", switch_port_literal, ",__en=", endpoint_name,
            ",__em=", endpoint_model, ",__ep=", endpoint_port_literal,
            ",__net=ipc.network(),__sd=__net.getDevice(__sn),__ed=__net.getDevice(__en);",
            "if(!__sd||!__ed){reportResult(JSON.stringify({linked:false,error:'fixture device missing'}));}",
            "else if(String(__sd.getModel())!==__sm||String(__ed.getModel())!==__em){reportResult(JSON.stringify({linked:false,error:'fixture model drift'}));}",
            "else{var __spp=__sd.getPort(__sp),__epp=__ed.getPort(__ep);",
            "if(!__spp||!__epp){reportResult(JSON.stringify({linked:false,error:'fixture port missing'}));}",
            "else if(__spp.getLink()||__epp.getLink()){reportResult(JSON.stringify({linked:false,error:'fixture port already linked'}));}",
            "else if(typeof lwAddLink!=='function'){reportResult(JSON.stringify({linked:false,error:'lwAddLink unavailable'}));}",
            "else{lwAddLink(__sn,__sp,__en,__ep,", cable, ");",
            "var __sl=__spp.getLink(),__el=__epp.getLink();",
            "if(!__sl||!__el){reportResult(JSON.stringify({linked:false,error:'created link not observed at both ports'}));}",
            "else{function __endpoint(__p){var __owner=__p.getOwnerDevice();return {",
            "device_name:String(__owner.getName()),device_model:(typeof __owner.getModel==='function'?String(__owner.getModel()):''),port:String(__p.getName())};}",
            "function __ends(__link){return [__endpoint(__link.getPort1()),__endpoint(__link.getPort2())];}",
            "reportResult(JSON.stringify({linked:true,observed_from_switch:__ends(__sl),observed_from_endpoint:__ends(__el)}));}}}}",
            "catch(__e){reportResult(JSON.stringify({linked:false,error:String(__e)}));}",
        ))
        data = self._json_object(script, timeout=15.0)
        error = data.get("error")
        if error:
            raise RuntimeError(f"Packet Tracer could not create PoE fixture link: {error}")
        if data.get("linked") is not True:
            raise RuntimeError("Packet Tracer did not observe the created PoE fixture link.")

        switch_view = self._parse_endpoint_view(data.get("observed_from_switch"))
        endpoint_view = self._parse_endpoint_view(data.get("observed_from_endpoint"))
        expected = {
            (switch.name, switch.model, switch_port),
            (endpoint.name, endpoint.model, endpoint_port),
        }
        if (
            self._endpoint_keys(switch_view) != expected
            or self._endpoint_keys(endpoint_view) != expected
        ):
            raise RuntimeError(
                "Packet Tracer link read-back did not match both requested endpoints."
            )

        by_key = {
            (item.device_name, item.device_model, item.port): item
            for item in switch_view
        }
        return PoEDeliveryLinkIdentity(
            first=by_key[(switch.name, switch.model, switch_port)],
            second=by_key[(endpoint.name, endpoint.model, endpoint_port)],
        )

    def delete_device(self, temporary_name: str) -> bool:
        """Delete only a name previously attempted through this runtime."""

        if temporary_name not in self._attempted_device_names:
            return False
        name_literal = json.dumps(temporary_name, ensure_ascii=False)
        script = "".join((
            "try{var __name=", name_literal,
            ",__net=ipc.network(),__d=__net.getDevice(__name);",
            "if(!__d){reportResult(JSON.stringify({deleted:true}));}",
            "else{var __lw=ipc.appWindow().getActiveWorkspace().getLogicalWorkspace();",
            "if(typeof __lw.removeDevice!=='function'){reportResult(JSON.stringify({deleted:false,error:'removeDevice unavailable'}));}",
            "else{__lw.removeDevice(__d.getName());reportResult(JSON.stringify({deleted:!__net.getDevice(__name)}));}}}",
            "catch(__e){reportResult(JSON.stringify({deleted:false,error:String(__e)}));}",
        ))
        data = self._json_object(script, timeout=10.0)
        deleted = data.get("deleted") is True
        if deleted:
            self._attempted_device_names.discard(temporary_name)
        return deleted

    def _json_object(self, script: str, *, timeout: float) -> dict[str, object]:
        raw = self._send_and_wait(script, timeout)
        if raw is None:
            raise TimeoutError(
                "Packet Tracer bridge did not respond before the PoE fixture timeout."
            )
        if raw.startswith(("ERROR:", "PT_ERROR:")):
            raise RuntimeError(raw.split(":", 1)[1].strip())
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            summary = raw.replace("\r", " ").replace("\n", " ")[:300]
            raise RuntimeError(
                "Packet Tracer returned malformed PoE fixture JSON: " + summary
            ) from exc
        if not isinstance(value, dict):
            raise RuntimeError(
                "Packet Tracer returned a non-object PoE fixture response."
            )
        return value

    @staticmethod
    def _parse_endpoint_view(value: object) -> tuple[PoEDeliveryLinkEndpoint, ...]:
        if not isinstance(value, list) or len(value) != 2:
            raise RuntimeError("Packet Tracer returned malformed PoE link endpoints.")
        parsed: list[PoEDeliveryLinkEndpoint] = []
        for item in value:
            if not isinstance(item, dict):
                raise RuntimeError("Packet Tracer returned malformed PoE link endpoints.")
            name = item.get("device_name")
            model = item.get("device_model")
            port = item.get("port")
            if not all(isinstance(field, str) and field for field in (name, model, port)):
                raise RuntimeError("Packet Tracer returned malformed PoE link endpoints.")
            parsed.append(PoEDeliveryLinkEndpoint(
                device_name=name,
                device_model=model,
                port=port,
            ))
        return tuple(parsed)

    @staticmethod
    def _endpoint_keys(
        endpoints: tuple[PoEDeliveryLinkEndpoint, ...],
    ) -> set[tuple[str, str, str]]:
        return {
            (item.device_name, item.device_model, item.port)
            for item in endpoints
        }
