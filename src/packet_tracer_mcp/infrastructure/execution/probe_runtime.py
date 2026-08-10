"""Adaptador bridge E3.5 con operaciones estructuradas sobre devices temporales."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable

from ...application.use_cases.capability_discovery import PacketTracerProbeRuntime
from ...domain.enterprise.models.capabilities import CapabilityStatus, EvidenceSource
from ...domain.enterprise.models.discovery import (
    CapabilityBackend,
    CapabilityVerificationMethod,
    CapabilityProbeResult,
    DeviceInitializationState,
    ProbeDefinition,
    ProbeEnvironment,
    ProbeExecutionStatus,
    RuntimeDeviceDescriptor,
    RuntimeDeviceObservation,
    Layer3ProbeStrategy,
    MultilayerDimension,
    RuntimeModuleDescriptor,
    RuntimePortDescriptor,
    encode_inventory_observation,
    inventory_restoration_matches,
    semantic_inventory_fingerprint,
)
from ...infrastructure.catalog.devices import resolve_model
from ...shared.constants import PT_CONNECT_TYPE, PT_DEVICE_TYPE, PT_DEVICE_TYPE_DEFAULT
from .configuration_runtime import PacketTracerConfigurationRuntime
from .device_lifecycle import DeviceReadinessWaiter, IosBootWaiter, StateConvergenceWaiter
from .ios_terminal import (
    ControlledIosExecutor,
    InterfaceStatusRow,
    OperationalQueryId,
    parse_show_ip_interface,
    parse_show_ip_interface_brief,
)
from ...shared.constants import (
    CAPABILITY_PROBE_IPV4_ADDRESS,
    CAPABILITY_PROBE_IPV4_MASK,
    CAPABILITY_PROBE_VLAN_ID,
    CAPABILITY_PROBE_VLAN_NAME,
)


_INTERFACE_TYPE = re.compile(r"^[A-Za-z-]+")

# Packet Tracer materializa un "Power Distribution Device" por su cuenta cuando
# aparece el primer dispositivo alimentable, y lo conserva después de que el
# probe borre los suyos. No lo crea el probe, no tiene puertos y ningún plan lo
# direcciona; además el probe tiene prohibido borrar objetos que no son suyos.
# Si contara para la huella, la restauración quedaría permanentemente indecidible
# y toda sesión live sería irreutilizable. Se excluye sólo con el modelo exacto y
# cero puertos, para no ocultar nunca un dispositivo real del usuario.
_BACKEND_MANAGED_MODELS = frozenset({"power distribution device"})


def _is_backend_managed_device(item: dict) -> bool:
    if item.get("kind") != "device":
        return False
    model = str(item.get("model") or "").strip().casefold()
    return model in _BACKEND_MANAGED_MODELS and not item.get("ports")


def _backend_managed_identity(item: dict) -> str:
    """Identidad estable para poder detectar que uno preexistente desapareció."""
    return f"{str(item.get('model') or '').strip()}/{str(item.get('name') or '').strip()}"


# Estrategia L3 por modelo. Declarada, no deducida: un 2960 soporta VLANs sin
# poder enrutar entre ellas, así que `supports_vlan` no implica multilayer.
_LAYER3_STRATEGY_BY_MODEL: dict[str, Layer3ProbeStrategy] = {
    "2911": Layer3ProbeStrategy.ROUTED_PHYSICAL_INTERFACE,
    "3560-24PS": Layer3ProbeStrategy.SVI,
    "3650-24PS": Layer3ProbeStrategy.SVI,
}


def layer3_strategy_for(runtime_model: str) -> Layer3ProbeStrategy:
    """Resuelve por nombre de catálogo exacto, no por subcadena del modelo."""
    resolved = resolve_model(runtime_model)
    key = resolved.pt_type if resolved else runtime_model
    return _LAYER3_STRATEGY_BY_MODEL.get(
        key, _LAYER3_STRATEGY_BY_MODEL.get(runtime_model, Layer3ProbeStrategy.NONE),
    )


# Slice multilayer: dos VLANs con SVI en rango de laboratorio, sin colisionar
# con las redes que ya usan los probes de interfaz física y SVI simple.
_MULTILAYER_PROBE_VLAN_ID = 901
_MULTILAYER_SLICE_VLAN_A = 10
_MULTILAYER_SLICE_VLAN_B = 20
_MULTILAYER_SLICE_MASK = "255.255.255.0"
_MULTILAYER_SLICE_GATEWAY_A = "198.18.140.1"
_MULTILAYER_SLICE_HOST_A = "198.18.140.10"
_MULTILAYER_SLICE_GATEWAY_B = "198.18.141.1"
_MULTILAYER_SLICE_HOST_B = "198.18.141.10"
_MULTILAYER_PROBE_IPV4_ADDRESS = "198.18.130.1"
_MULTILAYER_PROBE_IPV4_MASK = "255.255.255.0"


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
        transport_channel: str | Callable[[], str] = "",
        extension_version: str = "",
    ) -> None:
        self._send_and_wait = send_and_wait
        self._packet_tracer_version = packet_tracer_version
        self._transport_channel = transport_channel
        self._extension_version = extension_version
        self._configuration = PacketTracerConfigurationRuntime(send or (lambda _: False))
        self._ios = ControlledIosExecutor(send_and_wait)

    def packet_tracer_version(self) -> str | None:
        return self._packet_tracer_version

    def probe_environment(self) -> ProbeEnvironment:
        transport = (
            self._transport_channel()
            if callable(self._transport_channel)
            else self._transport_channel
        )
        return ProbeEnvironment(
            backend=CapabilityBackend.PACKET_TRACER,
            backend_version=self._packet_tracer_version or "",
            transport_channel=transport,
            extension_version=self._extension_version,
        )

    def inventory_fingerprint(self) -> str:
        """Lee identidad fisica minima con APIs PT ya usadas por el MCP."""
        js = (
            "try{var __n=ipc.network();var __items=[];var __links=[];"
            "for(var __i=0;__i<__n.getDeviceCount();__i++){var __d=__n.getDeviceAt(__i);"
            "if(!__d){continue;}var __ports=[];"
            "for(var __p=0;__p<__d.getPortCount();__p++){try{var __port=__d.getPortAt(__p);"
            "if(__port){__ports.push(__port.getName());}}catch(__pe){}}"
            "__items.push({kind:'device',name:__d.getName(),model:(typeof __d.getModel==='function'?__d.getModel():''),ports:__ports});}"
            "for(var __l=0;__l<__n.getLinkCount();__l++){try{var __link=__n.getLinkAt(__l);"
            "var __class=(typeof __link.getClassName==='function'?__link.getClassName():'');"
            "if(typeof __link.getPort1==='function'&&typeof __link.getPort2==='function'){"
            "var __p1=__link.getPort1();var __p2=__link.getPort2();"
            "__links.push({kind:'link',class_name:__class,a_device:__p1.getOwnerDevice().getName(),a_port:__p1.getName(),b_device:__p2.getOwnerDevice().getName(),b_port:__p2.getName()});}"
            "else{__links.push({kind:'link',class_name:__class,index:__l});}}"
            "catch(__le){__links.push({kind:'link',index:__l,unreadable:true});}}"
            "reportResult(JSON.stringify({items:__items,links:__links}));}"
            "catch(__e){reportResult('ERROR:'+__e);}"
        )
        data = self._json_result(js, timeout=10.0)
        items = data.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError("Packet Tracer returned malformed inventory data.")
        links = data.get("links", [])
        if not isinstance(links, list):
            raise RuntimeError("Packet Tracer returned malformed link inventory data.")
        normalized: list[dict] = []
        backend_managed: list[str] = []
        for item in [*items, *links]:
            if not isinstance(item, dict):
                continue
            if _is_backend_managed_device(item):
                backend_managed.append(_backend_managed_identity(item))
            else:
                normalized.append(item)
        return encode_inventory_observation(
            semantic_inventory_fingerprint(normalized), backend_managed,
        )

    def wait_for_inventory_fingerprint(
        self,
        expected: str,
        timeout_seconds: float = 5.0,
    ) -> str:
        """Espera acotadamente el retiro asíncrono de objetos temporales PT."""
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        observed = ""
        while True:
            observed = self.inventory_fingerprint()
            if (
                inventory_restoration_matches(expected, observed)
                or time.monotonic() >= deadline
            ):
                return observed
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

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
            # La lectura de módulos va en su propio try: si falla, la creación
            # sigue siendo válida y el slot simplemente queda sin observar.
            "var __mods=[];try{var __root=__d.getRootModule();"
            "if(__root){for(var __s=0;__s<__root.getModuleCount();__s++){"
            "var __m=__root.getModuleAt(__s);if(!__m){continue;}var __entry={};"
            "try{__entry.name=String(__m.getModuleNameAsString());}catch(__me){__entry.name='';}"
            "try{__entry.slot=String(__m.getModuleNumber());}catch(__me){__entry.slot='';}"
            "try{__entry.slot_type_code=String(__root.getSlotTypeAt(__s));}catch(__me){__entry.slot_type_code='';}"
            "try{__entry.port_count=__m.getPortCount();}catch(__me){__entry.port_count=0;}"
            "__mods.push(__entry);}}}catch(__re){__mods=[];}"
            "reportResult(JSON.stringify({found:true,runtime_id:(typeof __d.getModel==='function')?__d.getModel():__model,display_name:__d.getName(),ports:__ports,modules:__mods}));}}"
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
            modules=[
                self._module_descriptor(item)
                for item in data.get("modules", [])
                if isinstance(item, dict)
            ],
        )
        if observation.found:
            return observation.model_copy(update={
                "initialization": self._wait_for_operational_readiness(temporary_name, runtime_model),
            })
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
        if capability == "multilayer_intervlan":
            return self._probe_multilayer_intervlan(temporary_name, definition)
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
                f"{readiness.attempts} readiness check(s); independent terminal observation is deferred to IOS/PC probes."
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
        session_show = self._ios.execute(temporary_name, OperationalQueryId.SHOW_IP_INTERFACE_BRIEF)
        if not session_show.executed:
            return self._failure(
                definition, ProbeExecutionStatus.VERIFY_FAILED,
                "IOS session could not reach a fresh operational SHOW before configuration: " + session_show.failure_reason,
            )
        address, mask, vlan_id = self._layer3_probe_values(is_svi)
        lines = ["enable", "configure terminal"]
        if is_svi:
            lines.append(f"vlan {vlan_id}")
        lines.extend((f"interface {interface}", f"ip address {address} {mask}", "no shutdown", "end"))
        if not self._configuration.configure_ios(temporary_name, "\n".join(lines)):
            return self._failure(definition, ProbeExecutionStatus.BRIDGE_ERROR, "Official configuration channel rejected the IPv4 payload.")
        show_configured = self._wait_for_ios_address(temporary_name, interface, address, present=True)
        configured = bool(show_configured and self._show_has_address(show_configured, interface, address, present=True))
        cleanup = "\n".join(("enable", "configure terminal", f"interface {interface}", "no ip address", "shutdown", "end"))
        cleanup_sent = self._configuration.configure_ios(temporary_name, cleanup)
        show_cleaned = self._wait_for_ios_address(temporary_name, interface, address, present=False) if cleanup_sent else None
        cleaned = bool(show_cleaned and self._show_has_address(show_cleaned, interface, address, present=False))
        if not configured or not cleaned:
            details = ["IPv4 configure/read-back/cleanup evidence was incomplete."]
            if not show_configured.executed:
                details.append("configured show: " + show_configured.failure_reason)
            elif not configured:
                details.append("configured show rows: " + self._show_summary(show_configured))
            if show_cleaned is not None and not show_cleaned.executed:
                details.append("cleanup show: " + show_cleaned.failure_reason)
            elif show_cleaned is not None and not cleaned:
                details.append("cleanup show rows: " + self._show_summary(show_cleaned))
            return self._failure(definition, ProbeExecutionStatus.VERIFY_FAILED, " ".join(details), configured=configured)
        return CapabilityProbeResult(
            probe_id=definition.id, model="", capability=definition.capability, status=CapabilityStatus.SUPPORTED,
            execution_status=ProbeExecutionStatus.VERIFIED, evidence_source=EvidenceSource.CONTROLLED_PROBE,
            configured=True, verified=True, verification_method=CapabilityVerificationMethod.CLI_PLUS_READBACK,
            raw_summary="IPv4 interface configured through configureIosDevice, read back through registered IOS show, and cleared successfully.",
        )

    def _wait_for_ios_address(self, temporary_name: str, interface: str, address: str, *, present: bool):
        """Espera evidencia operacional fresca, no sólo la aceptación asíncrona del CLI."""
        latest = None

        def inspect() -> dict:
            nonlocal latest
            latest = self._ios.execute(temporary_name, OperationalQueryId.SHOW_IP_INTERFACE_BRIEF)
            return {
                "found": latest.executed,
                "configuration_channel": latest.executed and self._show_has_address(latest, interface, address, present=present),
            }

        StateConvergenceWaiter(inspect, timeout_seconds=8.0).wait()
        return latest

    @staticmethod
    def _show_has_address(show, interface: str, address: str, *, present: bool) -> bool:
        observed = any(
            row.interface.casefold() == interface.casefold()
            and row.ip_address == address
            for row in parse_show_ip_interface_brief(show.output)
        )
        return observed if present else not observed

    @staticmethod
    def _show_summary(show) -> str:
        rows = parse_show_ip_interface_brief(show.output)
        return ", ".join(row.interface + "=" + row.ip_address for row in rows[:8]) or "no parsed rows"

    @staticmethod
    def _layer3_probe_values(is_svi: bool) -> tuple[str, str, int]:
        if is_svi:
            return _MULTILAYER_PROBE_IPV4_ADDRESS, _MULTILAYER_PROBE_IPV4_MASK, _MULTILAYER_PROBE_VLAN_ID
        return CAPABILITY_PROBE_IPV4_ADDRESS, CAPABILITY_PROBE_IPV4_MASK, CAPABILITY_PROBE_VLAN_ID

    def _wait_for_readiness(self, temporary_name: str):
        return DeviceReadinessWaiter(lambda: self._initialization_state(temporary_name)).wait()

    def _wait_for_operational_readiness(self, temporary_name: str, runtime_model: str):
        terminal_kind = self._terminal_kind_for(runtime_model)
        return IosBootWaiter(lambda: self._initialization_state(temporary_name, terminal_kind)).wait()

    @staticmethod
    def _terminal_kind_for(runtime_model: str) -> str:
        model = resolve_model(runtime_model)
        return "pc_command_prompt" if model and model.category in {"pc", "server", "laptop"} else "ios_command_line"

    def _initialization_state(self, temporary_name: str, terminal_kind: str = "ios_command_line") -> dict:
        name = json.dumps(temporary_name)
        getter = "getCommandPrompt" if terminal_kind == "pc_command_prompt" else "getCommandLine"
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");",
            "var __terminal=__d&&typeof __d.", getter, "==='function'?__d.", getter, "():null;",
            "var __vm=__d&&typeof __d.getProcess==='function'?__d.getProcess('VlanManager'):null;",
            "var __power=__d&&typeof __d.getPower==='function'?!!__d.getPower():null;",
            "var __booting=__d&&typeof __d.isBooting==='function'?!!__d.isBooting():null;",
            "reportResult(JSON.stringify({found:!!__d,power:__power,booting:__booting,command_prompt:", "true" if terminal_kind == "pc_command_prompt" else "false", "&&!!__terminal,terminal_available:!!__terminal,terminal_kind:", json.dumps(terminal_kind), ",configuration_channel:!!__d&&typeof configureIosDevice==='function',components_seen:__vm?['VlanManager']:[]}));",
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

    def _probe_multilayer_intervlan(
        self, temporary_name: str, definition: ProbeDefinition,
    ) -> CapabilityProbeResult:
        """Construye dos VLANs con SVI y demuestra (o no) el forwarding entre ellas.

        Cada propiedad se observa por separado: una SVI configurada sin line
        protocol, un `ip routing` no observable y un forwarding que falla son
        tres resultados distintos y no pueden colapsarse en uno.
        """
        model = self._observed_model(temporary_name)
        if layer3_strategy_for(model) is not Layer3ProbeStrategy.SVI:
            return self._failure(
                definition, ProbeExecutionStatus.SKIPPED,
                f"Model {model!r} does not declare the SVI layer-3 strategy.",
            )
        access_ports = self._physical_access_ports(temporary_name, 2)
        if len(access_ports) < 2:
            return self._failure(
                definition, ProbeExecutionStatus.VERIFY_FAILED,
                "Fewer than two physical access ports were observed for the slice.",
            )

        dimensions: dict[str, str] = {}
        endpoints = (f"{temporary_name}_PCA", f"{temporary_name}_PCB")
        try:
            built = self._build_multilayer_slice(
                temporary_name, access_ports, endpoints, dimensions,
            )
            if not built:
                return self._multilayer_result(definition, dimensions, model)
            self._observe_multilayer_state(temporary_name, dimensions)
            self._observe_multilayer_behavior(endpoints, dimensions)
        finally:
            self._teardown_multilayer_slice(temporary_name, endpoints)
        return self._multilayer_result(definition, dimensions, model)

    def _build_multilayer_slice(
        self, switch: str, ports: list[str], endpoints: tuple[str, str],
        dimensions: dict[str, str],
    ) -> bool:
        vlans = (_MULTILAYER_SLICE_VLAN_A, _MULTILAYER_SLICE_VLAN_B)
        gateways = (_MULTILAYER_SLICE_GATEWAY_A, _MULTILAYER_SLICE_GATEWAY_B)
        hosts = (_MULTILAYER_SLICE_HOST_A, _MULTILAYER_SLICE_HOST_B)

        lines = ["enable", "configure terminal"]
        for vlan in vlans:
            lines.append(f"vlan {vlan}")
            lines.append("exit")
        for port, vlan in zip(ports, vlans):
            lines.extend((
                f"interface {port}", "switchport mode access",
                f"switchport access vlan {vlan}", "no shutdown", "exit",
            ))
        for vlan, gateway in zip(vlans, gateways):
            lines.extend((
                f"interface Vlan{vlan}",
                f"ip address {gateway} {_MULTILAYER_SLICE_MASK}",
                "no shutdown", "exit",
            ))
        lines.extend(("ip routing", "end"))
        if not self._configuration.configure_ios(switch, "\n".join(lines)):
            dimensions[MultilayerDimension.SVI_CONFIGURATION.value] = "config_apply_failed"
            return False
        dimensions[MultilayerDimension.SVI_CONFIGURATION.value] = "applied"

        for name, host, gateway in zip(endpoints, hosts, gateways):
            if not self._create_probe_endpoint(name):
                dimensions[MultilayerDimension.ENDPOINT_GATEWAY.value] = "endpoint_create_failed"
                return False
        for name, port in zip(endpoints, ports):
            if not self._link_probe_endpoint(name, switch, port):
                dimensions[MultilayerDimension.ENDPOINT_GATEWAY.value] = "endpoint_link_failed"
                return False
        for name, host, gateway in zip(endpoints, hosts, gateways):
            self._configuration.configure_endpoint_ipv4(
                name, host, _MULTILAYER_SLICE_MASK, gateway,
            )
        dimensions[MultilayerDimension.ENDPOINT_GATEWAY.value] = "configured"
        return True

    def _observe_multilayer_state(
        self, switch: str, dimensions: dict[str, str],
    ) -> None:
        """Espera acotada a que las SVI aparezcan y converjan."""
        expected = (
            (_MULTILAYER_SLICE_VLAN_A, _MULTILAYER_SLICE_GATEWAY_A),
            (_MULTILAYER_SLICE_VLAN_B, _MULTILAYER_SLICE_GATEWAY_B),
        )
        started = time.monotonic()
        deadline = started + 20.0
        attempts = 0
        rows: dict[int, InterfaceStatusRow | None] = {}
        while True:
            attempts += 1
            for vlan, _gateway in expected:
                show = self._ios.execute(
                    switch, OperationalQueryId.SHOW_IP_INTERFACE,
                    interface=f"Vlan{vlan}",
                )
                rows[vlan] = parse_show_ip_interface(show.output) if show.executed else None
            ready = all(
                rows.get(vlan) is not None
                and rows[vlan].protocol.casefold() == "up"
                for vlan, _gateway in expected
            )
            if ready or time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        dimensions["convergence_attempts"] = str(attempts)
        dimensions["convergence_elapsed_ms"] = str(int((time.monotonic() - started) * 1000))

        present, addressed, admin_up, protocol_up = [], [], [], []
        for vlan, gateway in expected:
            row = rows.get(vlan)
            present.append(row is not None)
            addressed.append(bool(row) and row.ip_address.strip() == gateway)
            admin_up.append(bool(row) and "administratively down" not in row.status.casefold())
            protocol_up.append(bool(row) and row.protocol.casefold() == "up")
        dimensions[MultilayerDimension.SVI_CONFIGURATION.value] = (
            "observed" if all(present) else "svi_absent_from_readback"
        )
        dimensions[MultilayerDimension.SVI_ADDRESS_READBACK.value] = (
            "observed" if all(addressed) else "address_not_read_back"
        )
        dimensions[MultilayerDimension.SVI_ADMIN_STATE.value] = (
            "up" if all(admin_up) else "down"
        )
        dimensions[MultilayerDimension.SVI_OPERATIONAL_STATE.value] = (
            "up" if all(protocol_up) else "down"
        )

    def _observe_multilayer_behavior(
        self, endpoints: tuple[str, str], dimensions: dict[str, str],
    ) -> None:
        from .typed_ping import TypedPingExecutor

        # La terminal del endpoint no atribuye sus primeras ejecuciones; el
        # reintento acotado vive en el executor, no repetido en cada probe.
        ping = TypedPingExecutor(self._send_and_wait, measurement_attempts=4)

        def reach(source: str, destination: str, budget: float):
            """Reintento acotado adicional: el ARP inicial puede perder el primer eco."""
            deadline = time.monotonic() + budget
            attempts = 0
            result = ping.ping(source, destination)
            while not result.reachable and time.monotonic() < deadline:
                attempts += 1
                time.sleep(1.0)
                result = ping.ping(source, destination)
            return result, attempts

        gateway_a, retries_a = reach(endpoints[0], _MULTILAYER_SLICE_GATEWAY_A, 20.0)
        gateway_b, retries_b = reach(endpoints[1], _MULTILAYER_SLICE_GATEWAY_B, 20.0)
        dimensions["gateway_ping_retries"] = f"{retries_a}/{retries_b}"
        dimensions["endpoint_a_to_svi"] = "reachable" if gateway_a.reachable else "unreachable"
        dimensions["endpoint_b_to_svi"] = "reachable" if gateway_b.reachable else "unreachable"
        if not (gateway_a.reachable and gateway_b.reachable):
            # Sin baseline hacia la propia puerta de enlace, un fallo entre VLANs
            # no probaría nada sobre el enrutamiento.
            dimensions[MultilayerDimension.INTERVLAN_FORWARDING.value] = "no_gateway_baseline"
            dimensions[MultilayerDimension.IP_ROUTING.value] = "unproven"
            return
        crossed, retries_x = reach(endpoints[0], _MULTILAYER_SLICE_HOST_B, 20.0)
        dimensions["intervlan_ping_retries"] = str(retries_x)
        dimensions[MultilayerDimension.INTERVLAN_FORWARDING.value] = (
            "reachable" if crossed.reachable else "unreachable"
        )
        dimensions[MultilayerDimension.IP_ROUTING.value] = (
            "proven_by_forwarding" if crossed.reachable else "unproven"
        )
        if not crossed.fresh_output_observed:
            dimensions[MultilayerDimension.INTERVLAN_FORWARDING.value] = "stale_output"

    def _multilayer_result(
        self, definition: ProbeDefinition, dimensions: dict[str, str], model: str,
    ) -> CapabilityProbeResult:
        forwarding = dimensions.get(MultilayerDimension.INTERVLAN_FORWARDING.value)
        verified = forwarding == "reachable"
        summary = "; ".join(f"{key}={value}" for key, value in sorted(dimensions.items()))
        return CapabilityProbeResult(
            probe_id=definition.id, model=model, capability=definition.capability,
            status=CapabilityStatus.SUPPORTED if verified else CapabilityStatus.UNKNOWN,
            execution_status=(
                ProbeExecutionStatus.VERIFIED if verified
                else ProbeExecutionStatus.VERIFY_FAILED
            ),
            evidence_source=EvidenceSource.CONTROLLED_PROBE,
            configured=dimensions.get(
                MultilayerDimension.SVI_CONFIGURATION.value,
            ) in {"applied", "observed"},
            verified=verified,
            verification_method=CapabilityVerificationMethod.SIMULATION_TRACE,
            raw_summary=summary,
            failure_reason="" if verified else f"Inter-VLAN forwarding was not demonstrated: {summary}",
            dimensions=dimensions,
        )

    def _physical_access_ports(self, temporary_name: str, count: int) -> list[str]:
        name = json.dumps(temporary_name)
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");var __out=[];",
            "for(var __i=0;__d&&__i<__d.getPortCount();__i++){var __p=__d.getPortAt(__i);",
            "if(!__p){continue;}var __n=String(__p.getName());",
            "if(__n.indexOf('Vlan')===0||__n.indexOf('Loopback')===0){continue;}",
            "if(__n.indexOf('Ethernet')<0){continue;}__out.push(__n);}",
            "reportResult(JSON.stringify({ports:__out}));}catch(__e){reportResult('ERROR:'+__e);}",
        ))
        ports = self._json_result(js, timeout=5.0).get("ports", [])
        return [str(item) for item in ports][:count] if isinstance(ports, list) else []

    def _create_probe_endpoint(self, name: str) -> bool:
        payload = json.dumps(name)
        js = "".join((
            "try{if(typeof lwAddDevice!=='function'){reportResult(JSON.stringify({created:false}));}",
            "else{lwAddDevice(", payload, ",", str(PT_DEVICE_TYPE.get("pc", PT_DEVICE_TYPE_DEFAULT)), ",\"PC-PT\",9100,9100);",
            "reportResult(JSON.stringify({created:!!ipc.network().getDevice(", payload, ")}));}}",
            "catch(__e){reportResult('ERROR:'+__e);}",
        ))
        if not self._json_result(js, timeout=15.0).get("created"):
            return False
        # Un endpoint recién creado existe antes de que su CommandPrompt sirva.
        # Sin esta espera, el primer `ping` vuelve sin ventana atribuible y un
        # camino que funciona se mide como inalcanzable. Es la misma barrera que
        # `create_temporary_device` ya aplica; aquí sólo se reutiliza.
        readiness = self._wait_for_operational_readiness(name, "PC-PT")
        return readiness.state is DeviceInitializationState.OPERATIONAL_READY

    def _link_probe_endpoint(self, endpoint: str, switch: str, port: str) -> bool:
        js = "".join((
            "try{if(typeof lwAddLink!=='function'){reportResult(JSON.stringify({linked:false}));}",
            "else{lwAddLink(", json.dumps(endpoint), ",\"FastEthernet0\",",
            json.dumps(switch), ",", json.dumps(port), ",",
            str(PT_CONNECT_TYPE["straight"]), ");",
            "var __p=ipc.network().getDevice(", json.dumps(endpoint), ").getPort(\"FastEthernet0\");",
            "reportResult(JSON.stringify({linked:!!(__p&&__p.getLink())}));}}",
            "catch(__e){reportResult('ERROR:'+__e);}",
        ))
        return bool(self._json_result(js, timeout=15.0).get("linked"))

    def _teardown_multilayer_slice(
        self, switch: str, endpoints: tuple[str, str],
    ) -> None:
        """Borra sólo lo que creó este slice; el switch lo retira el framework."""
        for name in endpoints:
            try:
                self.delete_temporary_device(name)
            except Exception:
                continue

    def _layer3_target(self, temporary_name: str) -> tuple[str, bool] | None:
        """Resuelve la interfaz IPv4 según la estrategia declarada del modelo."""
        observed_model = self._observed_model(temporary_name)
        strategy = layer3_strategy_for(observed_model)
        if strategy is Layer3ProbeStrategy.SVI:
            return f"Vlan{_MULTILAYER_PROBE_VLAN_ID}", True
        if strategy is Layer3ProbeStrategy.ROUTED_PHYSICAL_INTERFACE:
            interface = self._first_ethernet_port(temporary_name)
            return (interface, False) if interface else None
        return None

    def _observed_model(self, temporary_name: str) -> str:
        name = json.dumps(temporary_name)
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");",
            "reportResult(JSON.stringify({model:__d&&typeof __d.getModel==='function'?String(__d.getModel()):''}));}",
            "catch(__e){reportResult('ERROR:'+__e);}",
        ))
        return str(self._json_result(js, timeout=5.0).get("model") or "")

    def _first_ethernet_port(self, temporary_name: str) -> str:
        name = json.dumps(temporary_name)
        js = "".join((
            "try{var __d=ipc.network().getDevice(", name, ");var __iface='';",
            "for(var __i=0;__d&&__i<__d.getPortCount();__i++){var __p=__d.getPortAt(__i);",
            "if(__p&&String(__p.getName()).indexOf('Ethernet')>=0){__iface=__p.getName();break;}}",
            "reportResult(JSON.stringify({interface:__iface}));}catch(__e){reportResult('ERROR:'+__e);}",
        ))
        return str(self._json_result(js, timeout=5.0).get("interface") or "")

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
    def _module_descriptor(value: dict) -> RuntimeModuleDescriptor:
        # "None" es literalmente lo que devuelve el getter de nombre, también
        # para un módulo con puertos. No es un nombre: es la ausencia de uno.
        raw_name = str(value.get("name") or "").strip()
        named = bool(raw_name) and raw_name.casefold() not in {"none", "null"}
        port_count = value.get("port_count")
        return RuntimeModuleDescriptor(
            name=raw_name if named else "",
            slot=str(value.get("slot") or "") or None,
            installed=True,
            slot_type_code=str(value.get("slot_type_code") or ""),
            port_count=int(port_count) if isinstance(port_count, int) else 0,
            identity_observable=named,
            evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
        )

    @staticmethod
    def _port_descriptor(value: dict) -> RuntimePortDescriptor:
        name = str(value.get("name", ""))
        match = _INTERFACE_TYPE.match(name)
        bandwidth = value.get("bandwidth_kbps")
        logical = bool(re.match(r"^(Vlan|Loopback|Tunnel|Port-channel|BVI)", name, re.IGNORECASE))
        return RuntimePortDescriptor(
            name=name,
            interface_type=match.group(0) if match else "",
            speed=f"{bandwidth}kbps" if isinstance(bandwidth, (int, float)) else "",
            physical=not logical,
            logical=logical,
            evidence_source=EvidenceSource.PACKET_TRACER_RUNTIME,
            poe_status=CapabilityStatus.UNKNOWN,
        )
