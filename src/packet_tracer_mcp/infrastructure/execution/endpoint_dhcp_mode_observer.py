"""Exact-interface Packet Tracer DHCP-mode observation for delegated E5."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DhcpModeObservation:
    """One bounded reading of `HostPort.isDhcpClientOn()`."""

    runtime_device_name: str
    interface: str
    device_found: bool = False
    port_found: bool = False
    mode_channel: bool = False
    dhcp_mode: bool | None = None
    fresh_evidence: bool = False
    failure_reason: str = ""


def endpoint_dhcp_mode_read_js(device_name: str, interface: str) -> str:
    """Build the exact named-interface DHCP-mode getter."""
    name = json.dumps(device_name)
    wanted = json.dumps(interface)
    return "".join(
        (
            "try{var d=ipc.network().getDevice(",
            name,
            ");var want=",
            wanted,
            ";var p=null;",
            "if(d){for(var i=0;i<d.getPortCount();i++){var c=d.getPortAt(i);",
            "if(c&&typeof c.getName==='function'&&String(c.getName())===want)",
            "{p=c;break;}}}",
            "var able=!!p&&typeof p.isDhcpClientOn==='function';",
            "var mode=able?!!p.isDhcpClientOn():null;",
            "reportResult(JSON.stringify({found:!!d,port_found:!!p,interface:want,",
            "mode_channel:able,dhcp_mode:mode}));}",
            "catch(e){reportResult('ERROR:dhcp_mode_reader');}",
        )
    )


class PacketTracerEndpointDhcpModeObserver:
    """Read DHCP mode without treating address acquisition as part of it."""

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
        *,
        timeout_seconds: float = 3.0,
    ) -> None:
        """Bind the correlated reader and its finite timeout."""
        self._send_and_wait = send_and_wait
        self._timeout = timeout_seconds

    def observe(
        self,
        runtime_device_name: str,
        interface: str,
    ) -> DhcpModeObservation:
        """Read DHCP mode from one exact runtime device and interface."""
        try:
            raw = self._send_and_wait(
                endpoint_dhcp_mode_read_js(runtime_device_name, interface),
                self._timeout,
            )
        except Exception as exc:
            return self._unobservable(
                runtime_device_name, interface, f"exception:{type(exc).__name__}"
            )
        if raw is None:
            return self._unobservable(runtime_device_name, interface, "timeout")
        if not isinstance(raw, str) or raw.startswith(("ERROR:", "PT_ERROR:")):
            return self._unobservable(
                runtime_device_name, interface, "endpoint_dhcp_mode_error"
            )
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return self._unobservable(runtime_device_name, interface, "malformed_json")
        if not isinstance(value, dict):
            return self._unobservable(runtime_device_name, interface, "non_object_json")
        expected_types = {
            "found": bool,
            "port_found": bool,
            "interface": str,
            "mode_channel": bool,
        }
        if any(
            key not in value or not isinstance(value[key], expected)
            for key, expected in expected_types.items()
        ) or (
            value.get("dhcp_mode") is not None
            and not isinstance(value.get("dhcp_mode"), bool)
        ):
            return self._unobservable(runtime_device_name, interface, "malformed_shape")
        usable = value["mode_channel"] and isinstance(value.get("dhcp_mode"), bool)
        return DhcpModeObservation(
            runtime_device_name=runtime_device_name,
            interface=value["interface"],
            device_found=value["found"],
            port_found=value["port_found"],
            mode_channel=value["mode_channel"],
            dhcp_mode=value.get("dhcp_mode") if usable else None,
            fresh_evidence=usable,
            failure_reason="" if usable else "mode_channel_unavailable",
        )

    @staticmethod
    def _unobservable(
        runtime_device_name: str,
        interface: str,
        reason: str,
    ) -> DhcpModeObservation:
        return DhcpModeObservation(
            runtime_device_name=runtime_device_name,
            interface=interface,
            failure_reason=reason,
        )
