"""IoT-0: the read-only wireless surface probe. Prepared, never yet executed.

The probe answers one question per documented surface: does Packet Tracer
9.0.1.0858 actually expose it, on the exact models in use, through the script
engine. It reads and reports; it changes nothing.

Three properties are structural, not conventions:

* **Read-only.** Every step is a getter or a count. No setter, no `add*`, no
  `remove*`, no `reset*` appears in any generated script, and
  `tests/test_iot0_wireless_probe.py` fails if one ever does.
* **Bounded.** The steps are a fixed list, the receiver walk is capped, and one
  device yields one script per block. Nothing recurses and nothing enumerates
  the workspace.
* **Exact-build scoped.** The probe refuses to build for any build other than
  the one it was written against, the same way the capability audit does.

Every step records where it stopped. A step that finds the process but not the
member reports the member it stopped at; a step that cannot reach the process
reports that instead. Nothing is inferred from position on the canvas: an
access point is identified by a MAC or by an antenna receiver walk, never by
being near something.

Credentials are never read. `WirelessProfile` carries `key`, `password` and
`userID`, and the profile projection below names the fields it takes, so those
three cannot reach the evidence by accident.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from ..catalog.measured_port_inventories import MEASURED_BACKEND_VERSION


#: Profile fields the probe reads. Credentials are deliberately absent.
PROFILE_FIELDS: tuple[str, ...] = (
    "name", "ssid", "macAddress", "networkType", "authenType", "radioBand",
    "isDhcpEnabled", "ipAddress", "subnetMask", "defaultGateway", "vlan",
    "strength",
)

#: Never read, never reported, whatever a future step might want.
FORBIDDEN_PROFILE_FIELDS: frozenset[str] = frozenset({
    "key", "password", "userID",
})

#: Upper bound on the antenna receiver walk. A cap makes the probe bounded
#: without deciding in advance how many receivers a radio has.
MAX_RECEIVERS = 16


class ProbeRole(str, Enum):
    ENDPOINT = "endpoint"
    ACCESS_POINT = "access_point"
    ANTENNA = "antenna"


class ProbeStep(str, Enum):
    """One question, named after the surface it asks."""

    ENDPOINT_WIRELESS_CLIENT_PROCESS = "endpoint_wireless_client_process"
    ENDPOINT_CURRENT_PROFILE = "endpoint_current_profile"
    ENDPOINT_SSID = "endpoint_ssid"
    ENDPOINT_CURRENT_AP_MAC = "endpoint_current_ap_mac"
    ENDPOINT_WIRELESS_PORT = "endpoint_wireless_port"
    ENDPOINT_PORT_INVENTORY = "endpoint_port_inventory"
    ACCESS_POINT_WIRELESS_SERVER_PROCESS = "access_point_wireless_server_process"
    ACCESS_POINT_SERVICE_SET = "access_point_service_set"
    ACCESS_POINT_RADIO_PORT = "access_point_radio_port"
    ACCESS_POINT_PORT_INVENTORY = "access_point_port_inventory"
    ANTENNA_RECEIVERS = "antenna_receivers"


@dataclass(frozen=True)
class ProbeTarget:
    """One device the probe may read, named exactly as the workspace holds it."""

    runtime_device_name: str
    role: ProbeRole
    model: str = ""


@dataclass(frozen=True)
class ProbeScript:
    """One bounded read, with the surface it asks about attached."""

    step: ProbeStep
    role: ProbeRole
    runtime_device_name: str
    source: str
    surface: str
    reads_only: bool = True


@dataclass(frozen=True)
class IoT0ProbeContract:
    """What the probe will ask, before anything asks it."""

    backend: str
    backend_version: str
    targets: tuple[ProbeTarget, ...]
    scripts: tuple[ProbeScript, ...] = field(default_factory=tuple)
    max_receivers: int = MAX_RECEIVERS

    @property
    def steps(self) -> tuple[ProbeStep, ...]:
        return tuple(script.step for script in self.scripts)

    def scripts_for(self, role: ProbeRole) -> tuple[ProbeScript, ...]:
        return tuple(item for item in self.scripts if item.role is role)


class IoT0WirelessProbe:
    """Builds the IoT-0 contract. Building is not running."""

    BACKEND = "packet_tracer"
    DECLARED_BUILDS = frozenset({MEASURED_BACKEND_VERSION})

    def __init__(self, packet_tracer_version: str = MEASURED_BACKEND_VERSION) -> None:
        if packet_tracer_version not in self.DECLARED_BUILDS:
            raise ValueError(
                "IoT-0 is scoped to Packet Tracer "
                f"{sorted(self.DECLARED_BUILDS)}, not {packet_tracer_version!r}."
            )
        self._version = packet_tracer_version

    def contract(self, targets: tuple[ProbeTarget, ...]) -> IoT0ProbeContract:
        """The full read plan for these targets, in the order it will run.

        The most authoritative surface goes first on each device: the process
        object, then what it reports, then the port-level facts that stand on
        their own if the process turns out to be unreachable.
        """
        scripts: list[ProbeScript] = []
        for target in targets:
            if target.role is ProbeRole.ENDPOINT:
                scripts.extend(self._endpoint_scripts(target))
            elif target.role is ProbeRole.ACCESS_POINT:
                scripts.extend(self._access_point_scripts(target))
            else:
                scripts.append(self._antenna_script(target))
        return IoT0ProbeContract(
            backend=self.BACKEND,
            backend_version=self._version,
            targets=tuple(targets),
            scripts=tuple(scripts),
        )

    def _endpoint_scripts(self, target: ProbeTarget) -> list[ProbeScript]:
        name = target.runtime_device_name
        return [
            ProbeScript(
                step=ProbeStep.ENDPOINT_WIRELESS_CLIENT_PROCESS,
                role=target.role,
                runtime_device_name=name,
                surface='Device.getProcess("WirelessClient")',
                source=_process_presence_js(name, "WirelessClient"),
            ),
            ProbeScript(
                step=ProbeStep.ENDPOINT_CURRENT_PROFILE,
                role=target.role,
                runtime_device_name=name,
                surface="WirelessClientProcess.getCurrentProfile() -> WirelessProfile",
                source=_current_profile_js(name),
            ),
            ProbeScript(
                step=ProbeStep.ENDPOINT_SSID,
                role=target.role,
                runtime_device_name=name,
                surface="WirelessCommon.getSsid()",
                source=_process_string_js(name, "WirelessClient", "getSsid"),
            ),
            ProbeScript(
                step=ProbeStep.ENDPOINT_CURRENT_AP_MAC,
                role=target.role,
                runtime_device_name=name,
                surface="WirelessClientProcess.getCurrentApMac()",
                source=_process_string_js(name, "WirelessClient", "getCurrentApMac"),
            ),
            ProbeScript(
                step=ProbeStep.ENDPOINT_WIRELESS_PORT,
                role=target.role,
                runtime_device_name=name,
                surface="WirelessCommon.getPort() -> Port",
                source=_process_port_js(name, "WirelessClient"),
            ),
            ProbeScript(
                step=ProbeStep.ENDPOINT_PORT_INVENTORY,
                role=target.role,
                runtime_device_name=name,
                surface=(
                    "Device.getPortCount() / getPortAt(int); Port.getName, "
                    "getMacAddress, isWirelessPort, isDhcpClientOn, "
                    "getIpAddress, getSubnetMask"
                ),
                source=_port_inventory_js(name),
            ),
        ]

    def _access_point_scripts(self, target: ProbeTarget) -> list[ProbeScript]:
        name = target.runtime_device_name
        return [
            ProbeScript(
                step=ProbeStep.ACCESS_POINT_WIRELESS_SERVER_PROCESS,
                role=target.role,
                runtime_device_name=name,
                surface='Device.getProcess("WirelessServer")',
                source=_process_presence_js(name, "WirelessServer"),
            ),
            ProbeScript(
                step=ProbeStep.ACCESS_POINT_SERVICE_SET,
                role=target.role,
                runtime_device_name=name,
                surface=(
                    "WirelessCommon.getSsid / getAuthenType / getEncryptType; "
                    "WirelessServerProcess.isSsidBrdCastEnabled"
                ),
                source=_service_set_js(name),
            ),
            ProbeScript(
                step=ProbeStep.ACCESS_POINT_RADIO_PORT,
                role=target.role,
                runtime_device_name=name,
                surface="WirelessCommon.getPort() -> Port",
                source=_process_port_js(name, "WirelessServer"),
            ),
            ProbeScript(
                step=ProbeStep.ACCESS_POINT_PORT_INVENTORY,
                role=target.role,
                runtime_device_name=name,
                surface=(
                    "Device.getPortCount() / getPortAt(int); Port.getName, "
                    "getMacAddress, isWirelessPort"
                ),
                source=_port_inventory_js(name),
            ),
        ]

    def _antenna_script(self, target: ProbeTarget) -> ProbeScript:
        return ProbeScript(
            step=ProbeStep.ANTENNA_RECEIVERS,
            role=target.role,
            runtime_device_name=target.runtime_device_name,
            surface=(
                "Link.getClassName() == 'Antenna'; Antenna.getPort(); "
                "Antenna.getReceiverCount() / getReceiverAt(int)"
            ),
            source=_antenna_receivers_js(target.runtime_device_name),
        )


# --- script builders ------------------------------------------------------
#
# Every value is serialized with `json.dumps`. Packet Tracer runs these through
# `new Function()`, so an unescaped device name would be executable code. Each
# script reports `stopped_at` with the exact member it could not reach, so a
# negative result names a surface instead of a guess.


_PREAMBLE = (
    "try{var d=ipc.network().getDevice("
)


def _process_presence_js(device_name: str, process_name: str) -> str:
    name = json.dumps(device_name)
    process = json.dumps(process_name)
    return "".join((
        _PREAMBLE, name, ");var pn=", process, ";",
        "var out={device:", name, ",process:pn,device_found:!!d,",
        "process_channel:false,process_found:false,stopped_at:''};",
        "if(!d){out.stopped_at='Network.getDevice';}",
        "else if(typeof d.getProcess!=='function'){out.stopped_at='Device.getProcess';}",
        "else{out.process_channel=true;var p=d.getProcess(pn);",
        "out.process_found=!!p;if(!p){out.stopped_at='Device.getProcess('+pn+')';}}",
        "reportResult(JSON.stringify(out));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))


def _process_string_js(device_name: str, process_name: str, member: str) -> str:
    name = json.dumps(device_name)
    process = json.dumps(process_name)
    getter = json.dumps(member)
    return "".join((
        _PREAMBLE, name, ");var pn=", process, ";var m=", getter, ";",
        "var out={device:", name, ",process:pn,member:m,device_found:!!d,",
        "process_found:false,member_channel:false,value:null,stopped_at:''};",
        "if(!d){out.stopped_at='Network.getDevice';}",
        "else if(typeof d.getProcess!=='function'){out.stopped_at='Device.getProcess';}",
        "else{var p=d.getProcess(pn);out.process_found=!!p;",
        "if(!p){out.stopped_at='Device.getProcess('+pn+')';}",
        "else if(typeof p[m]!=='function'){out.stopped_at=pn+'.'+m;}",
        "else{out.member_channel=true;var v=p[m]();",
        "out.value=(v===null||v===undefined)?null:String(v);}}",
        "reportResult(JSON.stringify(out));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))


def _current_profile_js(device_name: str) -> str:
    name = json.dumps(device_name)
    fields = json.dumps(list(PROFILE_FIELDS))
    return "".join((
        _PREAMBLE, name, ");var picks=", fields, ";",
        "var out={device:", name, ",process:'WirelessClient',device_found:!!d,",
        "process_found:false,member_channel:false,profile:null,stopped_at:''};",
        "if(!d){out.stopped_at='Network.getDevice';}",
        "else if(typeof d.getProcess!=='function'){out.stopped_at='Device.getProcess';}",
        "else{var p=d.getProcess('WirelessClient');out.process_found=!!p;",
        "if(!p){out.stopped_at='Device.getProcess(WirelessClient)';}",
        "else if(typeof p.getCurrentProfile!=='function'){",
        "out.stopped_at='WirelessClientProcess.getCurrentProfile';}",
        "else{out.member_channel=true;var pr=p.getCurrentProfile();",
        "if(!pr){out.stopped_at='WirelessProfile';}",
        "else{var picked={};for(var i=0;i<picks.length;i++){var k=picks[i];",
        "var v=pr[k];picked[k]=(v===null||v===undefined)?null:",
        "((typeof v==='boolean')?v:String(v));}out.profile=picked;}}}",
        "reportResult(JSON.stringify(out));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))


def _process_port_js(device_name: str, process_name: str) -> str:
    name = json.dumps(device_name)
    process = json.dumps(process_name)
    return "".join((
        _PREAMBLE, name, ");var pn=", process, ";",
        "var out={device:", name, ",process:pn,device_found:!!d,",
        "process_found:false,member_channel:false,port_name:null,",
        "port_mac:null,wireless:null,stopped_at:''};",
        "if(!d){out.stopped_at='Network.getDevice';}",
        "else if(typeof d.getProcess!=='function'){out.stopped_at='Device.getProcess';}",
        "else{var p=d.getProcess(pn);out.process_found=!!p;",
        "if(!p){out.stopped_at='Device.getProcess('+pn+')';}",
        "else if(typeof p.getPort!=='function'){out.stopped_at=pn+'.getPort';}",
        "else{out.member_channel=true;var pt=p.getPort();",
        "if(!pt){out.stopped_at='WirelessCommon.getPort';}",
        "else{if(typeof pt.getName==='function'){out.port_name=String(pt.getName());}",
        "if(typeof pt.getMacAddress==='function'){",
        "out.port_mac=String(pt.getMacAddress());}",
        "if(typeof pt.isWirelessPort==='function'){out.wireless=!!pt.isWirelessPort();}",
        "}}}",
        "reportResult(JSON.stringify(out));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))


def _service_set_js(device_name: str) -> str:
    name = json.dumps(device_name)
    return "".join((
        _PREAMBLE, name, ");",
        "var out={device:", name, ",process:'WirelessServer',device_found:!!d,",
        "process_found:false,ssid:null,authen_type:null,encrypt_type:null,",
        "ssid_broadcast:null,stopped_at:''};",
        "if(!d){out.stopped_at='Network.getDevice';}",
        "else if(typeof d.getProcess!=='function'){out.stopped_at='Device.getProcess';}",
        "else{var p=d.getProcess('WirelessServer');out.process_found=!!p;",
        "if(!p){out.stopped_at='Device.getProcess(WirelessServer)';}",
        "else{if(typeof p.getSsid==='function'){out.ssid=String(p.getSsid());}",
        "else{out.stopped_at='WirelessCommon.getSsid';}",
        "if(typeof p.getAuthenType==='function'){",
        "out.authen_type=String(p.getAuthenType());}",
        "if(typeof p.getEncryptType==='function'){",
        "out.encrypt_type=String(p.getEncryptType());}",
        "if(typeof p.isSsidBrdCastEnabled==='function'){",
        "out.ssid_broadcast=!!p.isSsidBrdCastEnabled();}}}",
        "reportResult(JSON.stringify(out));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))


def _port_inventory_js(device_name: str) -> str:
    name = json.dumps(device_name)
    return "".join((
        _PREAMBLE, name, ");",
        "var out={device:", name, ",device_found:!!d,port_channel:false,",
        "ports:[],stopped_at:''};",
        "if(!d){out.stopped_at='Network.getDevice';}",
        "else if(typeof d.getPortCount!=='function'||typeof d.getPortAt!=='function'){",
        "out.stopped_at='Device.getPortAt';}",
        "else{out.port_channel=true;var n=d.getPortCount();",
        "for(var i=0;i<n;i++){var p=d.getPortAt(i);if(!p){continue;}",
        "out.ports.push({",
        "name:(typeof p.getName==='function')?String(p.getName()):null,",
        "mac:(typeof p.getMacAddress==='function')?String(p.getMacAddress()):null,",
        "wireless:(typeof p.isWirelessPort==='function')?!!p.isWirelessPort():null,",
        "dhcp_client:(typeof p.isDhcpClientOn==='function')?!!p.isDhcpClientOn():null,",
        "ipv4:(typeof p.getIpAddress==='function')?String(p.getIpAddress()):null,",
        "netmask:(typeof p.getSubnetMask==='function')?String(p.getSubnetMask()):null",
        "});}}",
        "reportResult(JSON.stringify(out));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))


def _antenna_receivers_js(device_name: str) -> str:
    """Walk the antenna links whose transmitter belongs to this device.

    The walk is capped and the identity of each end comes from the port owner,
    never from a coordinate.
    """
    name = json.dumps(device_name)
    cap = json.dumps(MAX_RECEIVERS)
    return "".join((
        "try{var want=", name, ";var cap=", cap, ";",
        "var net=ipc.network();",
        "var out={device:want,link_channel:false,antennas:[],stopped_at:''};",
        "if(typeof net.getLinkCount!=='function'||typeof net.getLinkAt!=='function'){",
        "out.stopped_at='Network.getLinkAt';}",
        "else{out.link_channel=true;var n=net.getLinkCount();",
        "for(var i=0;i<n;i++){var l=net.getLinkAt(i);if(!l){continue;}",
        "if(typeof l.getClassName!=='function'||String(l.getClassName())!=='Antenna'){",
        "continue;}",
        "if(typeof l.getPort!=='function'){out.stopped_at='Antenna.getPort';continue;}",
        "var tp=l.getPort();if(!tp){continue;}",
        "var td=(typeof tp.getOwnerDevice==='function')?tp.getOwnerDevice():null;",
        "var tn=(td&&typeof td.getName==='function')?String(td.getName()):null;",
        "if(tn!==want){continue;}",
        "var entry={transmitter:tn,",
        "transmitter_port:(typeof tp.getName==='function')?String(tp.getName()):null,",
        "receiver_channel:false,receiver_count:null,receivers:[]};",
        "if(typeof l.getReceiverCount!=='function'||",
        "typeof l.getReceiverAt!=='function'){",
        "out.stopped_at='Antenna.getReceiverAt';}",
        "else{entry.receiver_channel=true;var rc=l.getReceiverCount();",
        "entry.receiver_count=rc;var limit=(rc<cap)?rc:cap;",
        "for(var j=0;j<limit;j++){var r=l.getReceiverAt(j);if(!r){continue;}",
        "var rp=(typeof r.getPort==='function')?r.getPort():null;",
        "var rd=(rp&&typeof rp.getOwnerDevice==='function')?rp.getOwnerDevice():null;",
        "entry.receivers.push({",
        "device:(rd&&typeof rd.getName==='function')?String(rd.getName()):null,",
        "port:(rp&&typeof rp.getName==='function')?String(rp.getName()):null,",
        "mac:(rp&&typeof rp.getMacAddress==='function')?String(rp.getMacAddress()):null",
        "});}}",
        "out.antennas.push(entry);}}",
        "reportResult(JSON.stringify(out));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))
