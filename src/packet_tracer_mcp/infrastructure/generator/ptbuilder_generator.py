"""
Generador de scripts PTBuilder.

Convierte un TopologyPlan validado en JavaScript compatible
con la extensión PTBuilder de Packet Tracer.
"""

from __future__ import annotations
import json
import secrets
from ...domain.models.plans import DevicePlan, LinkPlan, ModulePlan, TopologyPlan
from ...shared.constants import (
    PT_DEVICE_TYPE,
    PT_DEVICE_TYPE_DEFAULT,
    PT_CONNECT_TYPE,
    PT_CONNECT_TYPE_DEFAULT,
)
from ...shared.ios_config import build_configure_ios_call
from ..catalog.modules import resolve_module


def generate_device_command(device: DevicePlan) -> str:
    """Render one trusted PTBuilder device mutation.

    Keeping the per-object renderer here lets the production deployment adapter
    reuse the exact same command as the bulk topology generator.
    """

    device_type = PT_DEVICE_TYPE.get(device.category, PT_DEVICE_TYPE_DEFAULT)
    return (
        f'lwAddDevice({json.dumps(device.name)}, {device_type}, '
        f'{json.dumps(device.model)}, {int(device.x)}, {int(device.y)});'
    )


def generate_link_command(link: LinkPlan) -> str:
    """Render one trusted PTBuilder link mutation with serialized fields."""

    connect_type = PT_CONNECT_TYPE.get(link.cable, PT_CONNECT_TYPE_DEFAULT)
    return (
        f'lwAddLink({json.dumps(link.device_a)}, {json.dumps(link.port_a)}, '
        f'{json.dumps(link.device_b)}, {json.dumps(link.port_b)}, {connect_type});'
    )


def generate_module_command(
    module: ModulePlan,
    *,
    expected_ports: list[str] | tuple[str, ...] | None = None,
    operation_token: str | None = None,
    slot_empty_proven: bool = False,
) -> str:
    """Render a same-request replay-safe module-effect mutation."""

    if expected_ports is None:
        spec = resolve_module(module.module)
        expected_ports = list(spec.ports_added) if spec is not None else []
    expected = sorted(set(expected_ports), key=str.casefold)
    token = operation_token or secrets.token_hex(16)
    name_js = json.dumps(module.device, ensure_ascii=False)
    slot_js = json.dumps(module.slot, ensure_ascii=False)
    model_js = json.dumps(module.module, ensure_ascii=False)
    expected_js = json.dumps(expected, ensure_ascii=False)
    token_js = json.dumps(token, ensure_ascii=False)
    empty_js = "true" if slot_empty_proven else "false"
    return (
        "var __mcpModuleMutationReceipt=(function(){"
        "var __g=(typeof GLOBAL!=='undefined'?GLOBAL:this),__token=" + token_js
        + ",__name=" + name_js + ",__slot=" + slot_js + ",__model=" + model_js
        + ",__expected=" + expected_js + ",__emptyProven=" + empty_js + ";"
        "if(!__g.__mcpModuleReceipts){__g.__mcpModuleReceipts={};"
        "__g.__mcpModuleReceiptOrder=[];}"
        "var __receipts=__g.__mcpModuleReceipts,__order=__g.__mcpModuleReceiptOrder;"
        "function __has(__o,__k){return Object.prototype.hasOwnProperty.call(__o,__k);}"
        "function __contains(__a,__v){for(var __i=0;__i<__a.length;__i++){"
        "if(String(__a[__i])===String(__v)){return true;}}return false;}"
        "function __slotOf(__port){var __m=String(__port).match(/[0-9].*$/);"
        "if(!__m){return '';}var __p=__m[0].lastIndexOf('/');"
        "return __p<0?'':__m[0].substring(0,__p);}"
        "function __inspect(){var __d=ipc.network().getDevice(__name);"
        "if(!__d){return {ok:false,error:'module target missing'};}"
        "var __slotPorts=[];for(var __i=0;__i<__d.getPortCount();__i++){"
        "var __port=__d.getPortAt(__i);if(!__port){"
        "return {ok:false,error:'module port inventory unreadable'};}"
        "var __pn=String(__port.getName());if(__slotOf(__pn)===__slot){"
        "__slotPorts.push(__pn);}}var __exact=__slotPorts.length===__expected.length;"
        "if(__exact){for(var __j=0;__j<__expected.length;__j++){"
        "if(!__contains(__slotPorts,__expected[__j])){__exact=false;break;}}}"
        "return {ok:true,exact:__exact,slotPorts:__slotPorts};}"
        "function __record(__r){if(!__has(__receipts,__token)){__order.push(__token);}"
        "__receipts[__token]=__r;while(__order.length>128){"
        "var __old=__order.shift();delete __receipts[__old];}return __r;}"
        "var __state=__inspect();if(!__state.ok){return {ack:false,changed:false,"
        "outcome:'pre_read_failed',identity_status:'unobservable',error:__state.error};}"
        "if(__has(__receipts,__token)){var __prior=__receipts[__token];"
        "if(__state.exact&&__prior.attempted===true){return {ack:true,changed:true,"
        "outcome:'effect_present_after_prior_attempt',identity_status:'unobservable',"
        "replayed:true};}return {ack:false,changed:false,"
        "outcome:'prior_attempt_ambiguous',identity_status:'unobservable',"
        "replayed:true,error:'module operation token was already attempted'};}"
        "if(__state.exact){return __record({ack:true,changed:false,attempted:false,"
        "outcome:'effect_already_present',identity_status:'unobservable'});}"
        "if(__state.slotPorts.length!==0){return __record({ack:false,changed:false,"
        "attempted:false,outcome:'slot_effect_conflict',identity_status:'unobservable',"
        "error:'partial, superset, or foreign slot effect is present'});}"
        "if(!__emptyProven){return __record({ack:false,changed:false,attempted:false,"
        "outcome:'slot_emptiness_unproven',identity_status:'unobservable',"
        "error:'slot emptiness was not independently proven'});}"
        "__record({ack:false,changed:false,attempted:true,outcome:'attempt_in_progress',"
        "identity_status:'unobservable'});var __accepted=false;"
        "try{__accepted=addModule(__name,__slot,__model)===true;}"
        "catch(__nativeError){return __record({ack:false,changed:false,attempted:true,"
        "outcome:'native_exception',identity_status:'unobservable',"
        "error:String(__nativeError)});}if(!__accepted){return __record({ack:false,"
        "changed:false,attempted:true,outcome:'native_rejected',"
        "identity_status:'unobservable',error:'Packet Tracer rejected module insertion'});}"
        "return __record({ack:true,changed:true,attempted:true,"
        "outcome:'mutation_accepted',identity_status:'unobservable'});})();"
        "if(__mcpModuleMutationReceipt.ack!==true){throw new Error("
        "__mcpModuleMutationReceipt.error||'module insertion was not acknowledged');}"
    )


def generate_ptbuilder_script(plan: TopologyPlan) -> str:
    """Genera un script JS de PTBuilder a partir de un plan validado.

    Usa lwAddDevice/lwAddLink (helpers inyectados como runtime patches) en vez del
    addDevice/addLink global — los helpers escriben al canvas Logical de PT, así
    los devices y cables aparecen inmediatamente sin necesidad de save+reload.
    """
    lines: list[str] = []

    # json.dumps en cada campo de texto: un nombre con comillas o saltos de línea
    # rompía el literal JS y el resto se ejecutaba como código en el Script Engine.
    # Es el mismo patrón que ya usa generate_executable_script() más abajo.
    for dev in plan.devices:
        lines.append(generate_device_command(dev))

    # Laptops WiFi: cambiar el NIC ethernet por uno inalámbrico (→ Wireless0). Debe ir
    # antes de los links/config; la auto-asociación al AP es por RF (SSID default).
    for dev in plan.devices:
        if dev.category == "laptop" and getattr(dev, "wireless", False):
            lines.append(f'swapLaptopToWireless({json.dumps(dev.name)});')

    # `slot_empty_proven` no es un adorno: es la afirmación de que alguien
    # comprobó que el slot estaba vacío. Aquí lo único que este script puede
    # probar es que el dispositivo lo crea él mismo, unas líneas más arriba, así
    # que su slot es de fábrica. Un módulo sobre un dispositivo preexistente no
    # tiene esa prueba y el payload debe rechazarlo, igual que hace el runtime
    # tipado con `_owned_new_devices`.
    created_here = {dev.name for dev in plan.devices}
    for mod in plan.modules:
        lines.append(generate_module_command(
            mod, slot_empty_proven=mod.device in created_here,
        ))

    for link in plan.links:
        lines.append(generate_link_command(link))

    return "\n".join(lines)


def generate_executable_script(plan: TopologyPlan) -> str:
    """
    Genera script JS completo y ejecutable: dispositivos, enlaces,
    configureIosDevice() para routers/switches, y configurePcIp() para PCs.
    """
    from .cli_config_generator import generate_all_configs

    lines: list[str] = []
    lines.append(generate_ptbuilder_script(plan))

    configs = generate_all_configs(plan)
    for device_name, cli_block in configs.items():
        lines.append(build_configure_ios_call(device_name, cli_block))

    from ...shared.utils import prefix_to_mask
    import ipaddress

    pcs = [d for d in plan.devices if d.category in ("pc", "server", "laptop")]

    # Fix F17: con DHCP activo, el ÚLTIMO host cableado por LAN a veces no completa el
    # DHCP DISCOVER. Como fallback determinista le asignamos IP estática (la que el planner
    # ya calculó). Identificamos el último host por subred /24 (el de mayor IP).
    last_host_per_subnet: dict[str, str] = {}
    if plan.dhcp_pools:
        host_ip: dict[str, str] = {}
        by_subnet: dict[str, list[str]] = {}
        for pc in pcs:
            iface_ip = next(iter(pc.interfaces.values()), None) if pc.interfaces else None
            if not iface_ip:
                continue
            host_ip[pc.name] = iface_ip.split("/")[0]
            net = str(ipaddress.ip_interface(iface_ip).network)
            by_subnet.setdefault(net, []).append(pc.name)
        for net, names in by_subnet.items():
            names_sorted = sorted(
                names, key=lambda n: tuple(int(o) for o in host_ip[n].split("."))
            )
            last_host_per_subnet[net] = names_sorted[-1]

    last_names = set(last_host_per_subnet.values())

    for pc in pcs:
        if pc.interfaces:
            iface_ip = next(iter(pc.interfaces.values()), None)
            if iface_ip:
                ip, prefix = iface_ip.split("/")
                mask = prefix_to_mask(int(prefix))
                gw = pc.gateway or ""
                use_dhcp = bool(plan.dhcp_pools) and pc.name not in last_names
                if use_dhcp:
                    lines.append(f'configurePcIp({json.dumps(pc.name)}, true);')
                else:
                    lines.append(
                        f'configurePcIp({json.dumps(pc.name)}, false, '
                        f'{json.dumps(ip)}, {json.dumps(mask)}, {json.dumps(gw)});'
                    )
        elif getattr(pc, "wireless", False) and plan.dhcp_pools:
            # Laptop WiFi sin link cableado: toma DHCP por Wireless0 (asociada al AP).
            lines.append(f'configurePcIp({json.dumps(pc.name)}, true);')
        # IPv6 dual-stack: host por SLAAC (auto-config desde el RA del router)
        if plan.dual_stack:
            lines.append(f'configurePcIpv6({json.dumps(pc.name)});')

    return "\n".join(lines)


def generate_full_script(plan: TopologyPlan) -> str:
    """
    Genera el script completo: PTBuilder + bloque de configuración CLI
    como comentarios (para referencia visual).
    """
    from .cli_config_generator import generate_all_configs

    parts: list[str] = []
    parts.append(generate_ptbuilder_script(plan))

    configs = generate_all_configs(plan)
    if configs:
        parts.append("/* === Configuraciones CLI por dispositivo ===")
        parts.append("Copiar y pegar en la CLI de cada dispositivo. */")
        for device_name, cli_block in configs.items():
            parts.append(f"/* --- {device_name} ---")
            for line in cli_block.splitlines():
                parts.append(line)
            parts.append("*/ ")

    return "\n".join(parts)
