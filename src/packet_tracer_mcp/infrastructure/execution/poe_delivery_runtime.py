"""Packet Tracer fixture adapter for governed PoE delivery qualification.

This module observes fixture identity, exact link endpoints, and read-only
factory structure diagnostics. Visible powered-device delivery is supplied by
the independent observer owned by the application use case; PT's administrative power getters
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
from ...infrastructure.catalog.cables import infer_cable
from ...infrastructure.catalog.devices import resolve_model
from ...shared.constants import (
    PT_CONNECT_TYPE,
    PT_CONNECT_TYPE_DEFAULT,
    PT_DEVICE_TYPE,
    PT_DEVICE_TYPE_DEFAULT,
)
from .probe_runtime import PacketTracerBridgeProbeRuntime
from .topology_observation import (
    LinkEndpoint,
    LinkExpectation,
    verify_exact_link_convergence,
)


_LINK_READBACK_TIMEOUT_SECONDS = 4.0


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
        self._creation_attempt_count = 0

    def packet_tracer_build(self) -> str | None:
        return self._packet_tracer_build

    def inventory_fingerprint(self) -> str:
        return self._inventory_runtime.inventory_fingerprint()

    def wait_for_inventory_fingerprint(self, expected: str) -> str:
        return self._inventory_runtime.wait_for_inventory_fingerprint(expected)

    def observe_factory_structure(
        self, model: str, *, module_type: int,
    ) -> dict[str, object]:
        """Read exact factory metadata without instantiating or powering a device.

        Cisco PT 9.0.1 IpcAPI: HardwareFactory.devices(),
        DeviceFactory.getDescriptor(DeviceType, string), DeviceDescriptor
        getModel/getType/isModuleTypeSupported/getRootModule, and the
        ModuleDescriptor getters below. A descriptor is NOT a runtime Module.
        No returned field establishes power delivery or installed hardware.
        """
        catalog_model = resolve_model(model)
        if (
            catalog_model is None
            or catalog_model.pt_type != model
            or catalog_model.category not in PT_DEVICE_TYPE
            or type(module_type) is not int
            or module_type < 0
        ):
            raise ValueError("Factory diagnosis requires an exact known model and module type.")
        device_type = PT_DEVICE_TYPE[catalog_model.category]
        script = "".join((
            "try{var __model=", json.dumps(model, ensure_ascii=False),
            ",__type=", json.dumps(device_type),
            ",__mt=", json.dumps(module_type), ",__nodes=0;",
            "function __count(v){if(typeof v!=='number'||v<0||v>64||v%1!==0){throw new Error('invalid descriptor count');}return v;}",
            "function __tree(m,depth){if(!m||depth>8||++__nodes>64){throw new Error('incomplete or oversized descriptor tree');}",
            "var slots=[],children=[],s=__count(m.getSlotCount()),n=__count(m.getModuleCount());",
            "for(var i=0;i<s;i++){slots.push(m.getSlotTypeAt(i));}",
            "for(var j=0;j<n;j++){children.push(__tree(m.getModuleAt(j),depth+1));}",
            "return {model:m.getModel(),module_type:m.getType(),hot_swappable:m.isHotSwappable(),slot_types:slots,modules:children};}",
            "var __d=ipc.hardwareFactory().devices().getDescriptor(__type,__model);",
            "if(!__d){throw new Error('factory descriptor unavailable');}",
            "reportResult(JSON.stringify({observed:true,model:__d.getModel(),device_type:__d.getType(),",
            "queried_module_type:__mt,module_type_supported:__d.isModuleTypeSupported(__mt),root:__tree(__d.getRootModule(),0)}));}",
            "catch(__e){reportResult(JSON.stringify({observed:false,error:String(__e)}));}",
        ))
        data = self._json_object(script, timeout=10.0)
        if data.get("error"):
            raise RuntimeError("Packet Tracer factory diagnosis failed: " + str(data["error"]))
        if (
            data.get("observed") is not True
            or data.get("model") != model
            or type(data.get("device_type")) is not int
            or data.get("device_type") != device_type
            or type(data.get("queried_module_type")) is not int
            or data.get("queried_module_type") != module_type
            or type(data.get("module_type_supported")) is not bool
        ):
            raise RuntimeError("Packet Tracer returned unattributable factory metadata.")

        nodes = 0

        def validate_tree(value: object, depth: int = 0) -> None:
            nonlocal nodes
            nodes += 1
            if not isinstance(value, dict) or depth > 8 or nodes > 64:
                raise RuntimeError("Packet Tracer returned an incomplete factory tree.")
            slots, children = value.get("slot_types"), value.get("modules")
            if (
                not isinstance(value.get("model"), str)
                or not value["model"]
                or type(value.get("module_type")) is not int
                or type(value.get("hot_swappable")) is not bool
                or not isinstance(slots, list)
                or len(slots) > 64
                or not all(type(slot) is int for slot in slots)
                or not isinstance(children, list)
                or len(children) > 64
            ):
                raise RuntimeError("Packet Tracer returned malformed factory tree metadata.")
            for child in children:
                validate_tree(child, depth + 1)

        validate_tree(data.get("root"))
        return {
            "evidence_role": "FACTORY_STRUCTURE_ONLY_NOT_POWER_DELIVERY",
            "model": model, "device_type": device_type,
            "queried_module_type": module_type,
            "module_type_supported": data["module_type_supported"],
            "root": data["root"],
        }

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
        # Keep simultaneous endpoints individually accessible to the visible
        # observer. PT clamps the former off-canvas (9000, 9000) onto one point.
        # Reserve before dispatch: an ambiguous acknowledgement cannot make a
        # later endpoint reuse a potentially occupied presentation position.
        ordinal = self._creation_attempt_count
        self._creation_attempt_count += 1
        x_literal = json.dumps(160 + 320 * (ordinal % 4))
        y_literal = json.dumps(160 + 140 * (ordinal // 4))
        script = "".join((
            "var __attempted=false;try{var __model=", model_literal, ",__name=", name_literal,
            ",__required=", ports_literal, ",__type=", type_literal,
            ",__net=ipc.network();",
            "if(__net.getDevice(__name)){reportResult(JSON.stringify({found:false,creation_attempted:false,error:'duplicate fixture name'}));}",
            "else if(typeof lwAddDevice!=='function'){reportResult(JSON.stringify({found:false,creation_attempted:false,error:'lwAddDevice unavailable'}));}",
            "else{__attempted=true;lwAddDevice(__name,__type,__model,",
            x_literal, ",", y_literal, ");var __d=__net.getDevice(__name);",
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
        switch_catalog = resolve_model(switch.model)
        endpoint_catalog = resolve_model(endpoint.model)
        cable_name = infer_cable(
            switch_catalog.category if switch_catalog is not None else "",
            endpoint_catalog.category if endpoint_catalog is not None else "",
        )
        cable = json.dumps(
            PT_CONNECT_TYPE.get(cable_name, PT_CONNECT_TYPE_DEFAULT)
        )
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
            "else{var __accepted=lwAddLink(__sn,__sp,__en,__ep,", cable, ");",
            "if(__accepted!==true){reportResult(JSON.stringify({requested:false,error:'lwAddLink rejected exact fixture link'}));}",
            "else{reportResult(JSON.stringify({requested:true}));}}}}",
            "catch(__e){reportResult(JSON.stringify({linked:false,error:String(__e)}));}",
        ))
        data = self._json_object(script, timeout=15.0)
        error = data.get("error")
        if error:
            raise RuntimeError(f"Packet Tracer could not create PoE fixture link: {error}")
        if data.get("requested") is not True:
            raise RuntimeError("Packet Tracer did not acknowledge the PoE link request.")

        convergence = verify_exact_link_convergence(
            self._send_and_wait,
            LinkExpectation(
                endpoint_a=LinkEndpoint(
                    device=switch.name, port=switch_port, model=switch.model,
                ),
                endpoint_b=LinkEndpoint(
                    device=endpoint.name, port=endpoint_port, model=endpoint.model,
                ),
            ),
            timeout_seconds=_LINK_READBACK_TIMEOUT_SECONDS,
        )
        if not convergence.verified:
            raise RuntimeError(
                "Packet Tracer did not observe the requested PoE fixture link "
                "bilaterally: " + convergence.observation.status.value
            )

        by_location = {
            (item.device, item.port): item
            for item in convergence.observation.observed_link_a
        }
        observed_switch = by_location[(switch.name, switch_port)]
        observed_endpoint = by_location[(endpoint.name, endpoint_port)]
        return PoEDeliveryLinkIdentity(
            first=PoEDeliveryLinkEndpoint(
                device_name=observed_switch.device,
                device_model=observed_switch.model,
                port=observed_switch.port,
            ),
            second=PoEDeliveryLinkEndpoint(
                device_name=observed_endpoint.device,
                device_model=observed_endpoint.model,
                port=observed_endpoint.port,
            ),
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
