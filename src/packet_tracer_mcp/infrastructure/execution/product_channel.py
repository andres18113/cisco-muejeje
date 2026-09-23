"""The product's channel scripts, and one channel fixed before any runtime exists.

Two routes compose the enterprise-services product: the MCP registry, which
picks a channel lazily after admission, and the cold-HTTP acceptance envelope,
which binds its authorized channel before it builds anything. Both must send
Packet Tracer the same guarded scripts and read the same targeted inventory, or
the envelope would be accepting a different invocation from the one the public
tool performs. The guards and the inventory read therefore live here, and the
registry closures and `FixedChannelProductTransport` both use them.

`FixedChannelProductTransport` exposes the five callables the shared session
composition expects, with the registry's `(script, timeout, channel)` shape.
It never selects: a call naming any channel other than the bound one raises
before anything is dispatched, so a substituted channel cannot be routed, and
there is no fallback to try instead.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

from ...domain.enterprise.models.deployment import EnvironmentFingerprint
from .service_environment import SERVICE_ENVIRONMENT_JS, parse_service_environment
from .transport_outcome import BridgeDispatchOutcome

#: The registry's bound for one environment or inventory read.
ENVIRONMENT_TIMEOUT_SECONDS = 10.0
INVENTORY_TIMEOUT_SECONDS = 10.0


def waited_guard(js_call: str) -> str:
    """Wrap a waited command so an engine error is reported, not raised.

    An uncaught error inside `runCode` opens a modal in Packet Tracer and stops
    the webview from polling; reporting it as `PT_ERROR: ...` keeps the channel
    alive and lets the reader classify the answer.
    """
    return "try{" + js_call + "}catch(__pterr){reportResult('PT_ERROR: '+__pterr);}"


def fire_and_forget_guard(js_call: str) -> str:
    """Wrap a fire-and-forget command so an engine error cannot open a modal."""
    return "try{" + js_call + "}catch(__pterr){}"


def targeted_inventory_js(device_names: Sequence[str]) -> str:
    """Build one target-filtered inventory read that detects ambiguity."""
    names = json.dumps(list(dict.fromkeys(device_names)))
    return (
        "var net=ipc.network();var names="
        + names
        + ",wanted={},arr=[];for(var w=0;w<names.length;w++){wanted[names[w]]=true;}"
        "for(var i=0;i<net.getDeviceCount();i++){var d=net.getDeviceAt(i);"
        "if(!d||!wanted[String(d.getName())]){continue;}"
        "var pc=d.getPortCount(),ports=[];for(var j=0;j<pc;j++){"
        "var p=d.getPortAt(j),ip='',mask='',up=false,linked=false;"
        "try{ip=p.getIpAddress()||'';}catch(pe){}"
        "try{mask=p.getSubnetMask()||'';}catch(pe){}"
        "try{up=(typeof p.isPortUp==='function')?p.isPortUp():false;}catch(pe){}"
        "try{linked=(p.getLink()!=null);}catch(pe){}"
        "ports.push({name:p.getName(),ip:ip,mask:mask,up:up,linked:linked});}"
        "arr.push({name:d.getName(),model:d.getModel(),ports:ports});}"
        "reportResult(JSON.stringify({devices:arr,links:null}));"
    )


def parse_inventory_devices(raw: str | None) -> list[dict]:
    """Return the devices of one inventory answer, or none when it is unusable."""
    if not raw or raw.startswith("PT_ERROR") or raw.startswith("ERROR"):
        return []
    try:
        data = json.loads(raw)
        return data.get("devices", []) or []
    except Exception:
        return []


class ChannelSubstitutionRefused(RuntimeError):
    """A product call named a channel other than the one bound for the run."""


class CommandTransport(Protocol):
    """The three dispatch shapes one fixed channel offers."""

    def send(self, js_code: str) -> bool:
        """Queue one fire-and-forget command."""

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        """Dispatch one command and return its correlated body, or None."""

    def dispatch_and_wait(self, js_code: str, timeout: float) -> BridgeDispatchOutcome:
        """Dispatch one command and keep its typed dispatch and result facts."""


class FixedChannelProductTransport:
    """The product's five channel callables, bound to one channel and transport."""

    def __init__(self, channel: str, transport: CommandTransport) -> None:
        """Bind the channel name and the only transport it may reach."""
        if not channel:
            raise ValueError("A fixed product channel needs a channel name.")
        self._channel = channel
        self._transport = transport

    @property
    def channel(self) -> str:
        """Return the one channel this transport serves."""
        return self._channel

    def _require(self, channel: str | None) -> None:
        if channel != self._channel:
            raise ChannelSubstitutionRefused(
                f"channel {channel!r} is not the bound channel {self._channel!r}"
            )

    def send_and_wait(
        self, script: str, timeout: float, channel: str | None
    ) -> str | None:
        """Dispatch one guarded, waited command on the bound channel."""
        self._require(channel)
        return self._transport.send_and_wait(waited_guard(script), timeout)

    def dispatch_and_wait(
        self, script: str, timeout: float, channel: str | None
    ) -> BridgeDispatchOutcome:
        """Dispatch one guarded command and keep its typed facts."""
        self._require(channel)
        return self._transport.dispatch_and_wait(waited_guard(script), timeout)

    def send_payload(self, script: str, channel: str | None) -> bool:
        """Queue one guarded fire-and-forget command on the bound channel."""
        self._require(channel)
        return bool(self._transport.send(fire_and_forget_guard(script)))

    def query_inventory(
        self, device_names: Sequence[str], channel: str | None
    ) -> list[dict]:
        """Read exactly the named devices; an empty selection is refused."""
        self._require(channel)
        if not device_names:
            raise ValueError("The product inventory read is always target-directed.")
        raw = self.send_and_wait(
            targeted_inventory_js(device_names), INVENTORY_TIMEOUT_SECONDS, channel
        )
        return parse_inventory_devices(raw)

    def observe_environment(self, channel: str) -> EnvironmentFingerprint:
        """Read the current executable build; never copied from a manifest."""
        raw = self.send_and_wait(
            SERVICE_ENVIRONMENT_JS, ENVIRONMENT_TIMEOUT_SECONDS, channel
        )
        return parse_service_environment(raw, channel=channel)
