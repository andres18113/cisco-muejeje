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

# A real chassis descriptor tree is bigger than a toy ceiling: reading the
# exact 7960 hit the first 64-node bound and came back as "oversized",
# discarding a valid answer. The read still has to stay finite, so the
# bound is raised rather than removed.
_FACTORY_TREE_MAX_NODES = 512
_FACTORY_TREE_MAX_DEPTH = 12

# One canvas carries both arms of a simultaneous episode. Interleaving them by
# creation order forces the observer to identify 46 identical endpoints by name
# one at a time; giving each arm its own horizontal band turns the reading into
# a comparison of two blocks. Presentation only -- position is never authority.
_ARM_BAND_ORIGIN_X = {"candidate": 100, "comparison": 720, None: 1340}
_ARM_BAND_COLUMNS = 4
_ARM_BAND_COLUMN_SPACING = 120
_ARM_BAND_ROW_SPACING = 120
_ARM_BAND_ORIGIN_Y = 100

# Enumeracion de nombres para el retiro de residuo. Sólo lee: decidir qué se
# retira es del llamador, contra el inventario de apertura.
_DEVICE_NAMES_JS = (
    "try{var __net=ipc.network(),__n=__net.getDeviceCount(),__a=[];"
    "for(var __i=0;__i<__n;__i++){__a.push(String(__net.getDeviceAt(__i).getName()));}"
    "reportResult(JSON.stringify({devices:__a}));}"
    "catch(__e){reportResult(JSON.stringify({devices:null,error:String(__e)}));}"
)


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
        self._creation_attempt_counts: dict[str | None, int] = {}

    def packet_tracer_build(self) -> str | None:
        return self._packet_tracer_build

    def inventory_fingerprint(self) -> str:
        return self._inventory_runtime.inventory_fingerprint()

    def wait_for_inventory_fingerprint(self, expected: str) -> str:
        return self._inventory_runtime.wait_for_inventory_fingerprint(expected)

    def observe_factory_structure(
        self, model: str, *, module_type: int, device_type: int | None = None,
        max_depth: int | None = None,
    ) -> dict[str, object]:
        """Read exact factory metadata without instantiating or powering a device.

        Cisco PT 9.0.1 IpcAPI: HardwareFactory.devices(),
        DeviceFactory.getDescriptor(DeviceType, string), DeviceDescriptor
        getModel/getType/isModuleTypeSupported/getRootModule, and the
        ModuleDescriptor getters below. A descriptor is NOT a runtime Module.
        No returned field establishes power delivery or installed hardware.

        ``device_type`` overrides the catalog category for models the factory
        files elsewhere -- 3560-24PS and 3650-24PS answer nothing under
        eSwitch. It only accepts a value Packet Tracer documents, so which
        DeviceType holds a model stays something this reads, never something
        it asserts, and the response still has to echo it back exactly.

        ``max_depth`` bounds the walk. A 24-port switch descriptor overflows
        any complete traversal, and refusing the whole read left its slot
        inventory unreadable. A bounded read carries ``truncated`` so an
        omitted subtree stays visibly absent and can never be read as an
        observed absence.
        """
        catalog_model = resolve_model(model)
        documented = set(PT_DEVICE_TYPE.values())
        if (
            catalog_model is None
            or catalog_model.pt_type != model
            or catalog_model.category not in PT_DEVICE_TYPE
            or type(module_type) is not int
            or module_type < 0
            or (device_type is not None
                and (type(device_type) is not int or device_type not in documented))
            or (max_depth is not None
                and (type(max_depth) is not int
                     or not 0 <= max_depth <= _FACTORY_TREE_MAX_DEPTH))
        ):
            raise ValueError("Factory diagnosis requires an exact known model and module type.")
        if device_type is None:
            device_type = PT_DEVICE_TYPE[catalog_model.category]
        if max_depth is None:
            max_depth = _FACTORY_TREE_MAX_DEPTH
        max_nodes_literal = json.dumps(_FACTORY_TREE_MAX_NODES)
        max_depth_literal = json.dumps(max_depth)
        script = "".join((
            "try{var __model=", json.dumps(model, ensure_ascii=False),
            ",__type=", json.dumps(device_type),
            ",__mt=", json.dumps(module_type), ",__nodes=0;",
            "function __count(v){if(typeof v!=='number'||v<0||v>", max_nodes_literal, "||v%1!==0){throw new Error('invalid descriptor count');}return v;}",
            "function __tree(m,depth){if(!m||depth>", max_depth_literal,"||++__nodes>", max_nodes_literal, "){throw new Error('incomplete or oversized descriptor tree');}",
            "var slots=[],children=[],s=__count(m.getSlotCount()),n=__count(m.getModuleCount());",
            "var cut=(depth>=", max_depth_literal, ");",
            "for(var i=0;i<s;i++){slots.push(m.getSlotTypeAt(i));}",
            "if(!cut){for(var j=0;j<n;j++){children.push(__tree(m.getModuleAt(j),depth+1));}}",
            "return {model:m.getModel(),module_type:m.getType(),hot_swappable:m.isHotSwappable(),",
            "slot_types:slots,modules:children,truncated:(cut&&n>0)};}",
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
        truncated = False

        def validate_tree(value: object, depth: int = 0) -> None:
            nonlocal nodes, truncated
            nodes += 1
            if (
                not isinstance(value, dict)
                or depth > _FACTORY_TREE_MAX_DEPTH
                or nodes > _FACTORY_TREE_MAX_NODES
            ):
                raise RuntimeError("Packet Tracer returned an incomplete factory tree.")
            slots, children = value.get("slot_types"), value.get("modules")
            # A chassis descriptor legitimately reports an empty model: on
            # 9.0.1 the AccessPoint-PT root and its second slot both do. The
            # tree is attributed by the top-level identity checked above, so
            # requiring a name here discarded real metadata as malformed.
            if (
                not isinstance(value.get("model"), str)
                or type(value.get("module_type")) is not int
                or type(value.get("hot_swappable")) is not bool
                or type(value.get("truncated")) is not bool
                or not isinstance(slots, list)
                or len(slots) > _FACTORY_TREE_MAX_NODES
                or not all(type(slot) is int for slot in slots)
                or not isinstance(children, list)
                or len(children) > _FACTORY_TREE_MAX_NODES
            ):
                raise RuntimeError("Packet Tracer returned malformed factory tree metadata.")
            truncated = truncated or value["truncated"]
            for child in children:
                validate_tree(child, depth + 1)

        validate_tree(data.get("root"))
        return {
            "evidence_role": "FACTORY_STRUCTURE_ONLY_NOT_POWER_DELIVERY",
            "model": model, "device_type": device_type,
            "queried_module_type": module_type,
            "module_type_supported": data["module_type_supported"],
            "max_depth": max_depth, "truncated": truncated,
            "root": data["root"],
        }

    def create_device(
        self,
        model: str,
        temporary_name: str,
        required_ports: tuple[str, ...],
        *,
        arm: str | None = None,
    ) -> PoEDeliveryDeviceIdentity:
        """Create one device and observe its exact model/name/required ports.

        This is intentionally separate from ``create_temporary_device``: the
        ordinary probe readiness path reads power control getters, which are not
        an observation of powered-endpoint delivery.

        ``arm`` places the device in that arm's presentation band so a large
        simultaneous fixture stays readable. It carries no authority: identity,
        links and the observation itself are unchanged by where a device sits.
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
        band = arm if arm in _ARM_BAND_ORIGIN_X else None
        ordinal = self._creation_attempt_counts.get(band, 0)
        self._creation_attempt_counts[band] = ordinal + 1
        x_literal = json.dumps(
            _ARM_BAND_ORIGIN_X[band]
            + _ARM_BAND_COLUMN_SPACING * (ordinal % _ARM_BAND_COLUMNS)
        )
        y_literal = json.dumps(
            _ARM_BAND_ORIGIN_Y
            + _ARM_BAND_ROW_SPACING * (ordinal // _ARM_BAND_COLUMNS)
        )
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

    def retire_session_residue(
        self, preexisting_device_names: frozenset[str],
    ) -> tuple[str, ...]:
        """Retire what Packet Tracer added on its own during this session.

        A disposable fixture's footprint is not only what this runtime created.
        Measured live in run `poe1-4d342a1a`: deleting both created devices
        still left the inventory short of its opening fingerprint, because PT
        had placed a `Power Distribution Device0` of its own when the 7960
        appeared. ``delete_device`` refused it -- correctly, it only removes
        names it registered at creation -- so nothing retired it, and the next
        governed run would open on a dirty canvas its own precondition rejects.

        The authority here is narrower than "delete anything": the only name
        that can be retired is one absent from the opening inventory. A device
        that predates the session belongs to the user and is never touched, so
        a wrong caller-supplied set can fail to clean up but can never delete
        somebody's work. Returns the names actually retired.
        """

        listing = self._json_object(_DEVICE_NAMES_JS, timeout=10.0)
        names = listing.get("devices")
        if not isinstance(names, list):
            return ()
        retired: list[str] = []
        for entry in names:
            if not isinstance(entry, str) or entry in preexisting_device_names:
                continue
            name_literal = json.dumps(entry, ensure_ascii=False)
            script = "".join((
                "try{var __name=", name_literal,
                ",__net=ipc.network(),__d=__net.getDevice(__name);",
                "if(!__d){reportResult(JSON.stringify({removed:true}));}",
                "else{var __lw=ipc.appWindow().getActiveWorkspace().getLogicalWorkspace();",
                "if(typeof __lw.removeDevice!=='function'){reportResult(JSON.stringify({removed:false,error:'removeDevice unavailable'}));}",
                "else{__lw.removeDevice(__d.getName());reportResult(JSON.stringify({removed:!__net.getDevice(__name)}));}}}",
                "catch(__e){reportResult(JSON.stringify({removed:false,error:String(__e)}));}",
            ))
            if self._json_object(script, timeout=10.0).get("removed") is True:
                retired.append(entry)
                self._attempted_device_names.discard(entry)
        return tuple(retired)

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
