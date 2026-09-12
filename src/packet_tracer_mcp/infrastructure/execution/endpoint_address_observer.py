"""One qualified Packet Tracer IP/mask getter path for endpoint evidence."""

from __future__ import annotations

import json
from collections.abc import Callable

from ...domain.enterprise.models.forwarding import ForwardingAddressObservation


def endpoint_address_read_js(device_name: str, interface: str) -> str:
    """Build the exact named-interface getter used by E5 and forwarding."""

    name = json.dumps(device_name)
    wanted = json.dumps(interface)
    return "".join((
        "try{var d=ipc.network().getDevice(", name, ");",
        "var want=", wanted, ";var p=null;",
        "if(d){for(var i=0;i<d.getPortCount();i++){var c=d.getPortAt(i);",
        "if(c&&typeof c.getName==='function'&&String(c.getName())===want){p=c;break;}}}",
        "var able=!!p&&typeof p.getIpAddress==='function'",
        "&&typeof p.getSubnetMask==='function';",
        "var ip=able?String(p.getIpAddress()):'';",
        "var mask=able?String(p.getSubnetMask()):'';",
        "reportResult(JSON.stringify({found:!!d,port_found:!!p,interface:want,",
        "address_channel:able,ipv4:ip,netmask:mask}));}",
        "catch(e){reportResult('ERROR:'+e);}",
    ))


class PacketTracerEndpointAddressObserver:
    """Read one endpoint without acquiring gateway/DNS claims."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        *,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._send_and_wait = send_and_wait
        self._timeout = timeout_seconds

    def observe(
        self,
        runtime_device_name: str,
        interface: str,
    ) -> ForwardingAddressObservation:
        try:
            raw = self._send_and_wait(
                endpoint_address_read_js(runtime_device_name, interface),
                self._timeout,
            )
        except Exception as exc:
            return self._unobservable(
                runtime_device_name,
                interface,
                f"{type(exc).__name__}: {exc}",
            )
        if raw is None:
            return self._unobservable(runtime_device_name, interface, "timeout")
        if not isinstance(raw, str) or raw.startswith(("ERROR:", "PT_ERROR:")):
            return self._unobservable(
                runtime_device_name,
                interface,
                str(raw or "endpoint_getter_error"),
            )
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return self._unobservable(
                runtime_device_name,
                interface,
                "malformed_json",
            )
        if not isinstance(value, dict):
            return self._unobservable(
                runtime_device_name,
                interface,
                "non_object_json",
            )
        return ForwardingAddressObservation(
            runtime_device_name=runtime_device_name,
            interface=str(value.get("interface") or interface),
            device_found=value.get("found") is True,
            port_found=value.get("port_found") is True,
            address_channel=value.get("address_channel") is True,
            ipv4=str(value.get("ipv4") or ""),
            netmask=str(value.get("netmask") or ""),
            fresh_evidence=True,
        )

    @staticmethod
    def _unobservable(
        runtime_device_name: str,
        interface: str,
        reason: str,
    ) -> ForwardingAddressObservation:
        return ForwardingAddressObservation(
            runtime_device_name=runtime_device_name,
            interface=interface,
            device_found=False,
            port_found=False,
            address_channel=False,
            fresh_evidence=False,
            failure_reason=reason,
        )
