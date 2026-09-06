"""Observe the exact Packet Tracer Script Module serving bridge commands."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ActiveWorkspaceIdentitySample:
    """One productive identity sample returned by the executing PT module."""

    path: str
    instance_id: str
    module_id: str
    module_name: str


class PacketTracerActiveWorkspaceObserver:
    """Read module identity through documented IPC self-introspection APIs."""

    _SCRIPT = (
        "try{var __m=ipc.ipcManager().thisInstance();"
        "if(!__m){reportResult(JSON.stringify({error:'script module instance unavailable'}));}"
        "else{var __c=__m.getCep();reportResult(JSON.stringify({"
        "path:String(__m.getCommandLineArg()),"
        "instance_id:String(__m.getInstanceId()),"
        "module_id:__c?String(__c.getId()):'',"
        "module_name:__c?String(__c.getName()):''}));}}"
        "catch(__e){reportResult('ERROR:'+__e);}"
    )

    def __init__(
        self,
        send_and_wait: Callable[[str, float], str | None],
    ) -> None:
        self._send_and_wait = send_and_wait

    def capture(self) -> ActiveWorkspaceIdentitySample:
        raw = self._send_and_wait(self._SCRIPT, 3.0)
        if not raw or raw.startswith(("ERROR:", "PT_ERROR:")):
            raise RuntimeError("Packet Tracer script module identity is unobservable.")
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Packet Tracer script module identity response is malformed."
            ) from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError("Packet Tracer script module identity is unobservable.")
        fields = {
            name: payload.get(name)
            for name in ("path", "instance_id", "module_id", "module_name")
        }
        if any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in fields.values()
        ):
            raise RuntimeError(
                "Packet Tracer script module identity is incomplete or ambiguous."
            )
        return ActiveWorkspaceIdentitySample(**fields)
