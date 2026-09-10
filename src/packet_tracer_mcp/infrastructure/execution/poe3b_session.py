"""Bounded Packet Tracer session used by the POE-3B capacity runner.

The operator runner sees only this typed surface. Raw JavaScript, the local IPC
mailbox, HTTP control listener, IOS executor and fixture runtimes remain private
to the live transport composed here. Mailbox files are IPC, not Packet Tracer
workspace-file operations; the latter have their own fail-closed ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from secrets import token_urlsafe
from typing import Protocol, TypeVar
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ...domain.enterprise.models.capabilities import PoEAuthorizedBinding
from ...domain.enterprise.models.discovery import DeviceInitializationResult
from ...domain.enterprise.models.poe2 import PoE2Capture
from ...domain.enterprise.models.poe_delivery import (
    PoEDeliveryDeviceIdentity,
    PoEDeliveryLinkIdentity,
)
from .configuration_runtime import PacketTracerConfigurationRuntime
from .file_bridge import FileBridge
from .ios_terminal import ControlledIosExecutor
from .live_bridge import PTCommandBridge
from .poe2_evidence import BUILD, completeness
from .poe_delivery_runtime import PacketTracerPoEDeliveryFixtureRuntime
from .poe_inline_observer import GovernedPoEInlineObserver
from .pt_file_operations import (
    PacketTracerFileOperationGuard,
    PacketTracerFileOperationLedger,
    PacketTracerFileOperationResult,
)


_T = TypeVar("_T")


class PoEInlineMode(str, Enum):
    """Closed IOS mutation set for the governed qualification."""

    AUTO = "auto"
    NEVER = "never"


class PoE3BSessionOperation(str, Enum):
    """Every kind of Packet Tracer access available to the runner session."""

    TRANSPORT_HEALTH = "transport_health"
    MAILBOX_OBSERVATION = "mailbox_observation"
    CONTROL_BRIDGE_START = "control_bridge_start"
    CONTROL_BRIDGE_STOP = "control_bridge_stop"
    ENVIRONMENT_OBSERVATION = "environment_observation"
    INVENTORY_OBSERVATION = "inventory_observation"
    DEVICE_NAMES_OBSERVATION = "device_names_observation"
    FIXTURE_DEVICE_CREATE = "fixture_device_create"
    FIXTURE_LINK_CREATE = "fixture_link_create"
    DEVICE_READINESS = "device_readiness"
    INLINE_MODE_APPLY = "inline_mode_apply"
    INLINE_CAPTURE = "inline_capture"
    FIXTURE_DEVICE_DELETE = "fixture_device_delete"
    RESIDUE_RETIRE = "residue_retire"
    INVENTORY_RESTORATION = "inventory_restoration"
    IPC_DRAIN = "ipc_drain"
    TRANSPORT_PROBLEMS = "transport_problems"
    WORKSPACE_FILE_OPERATION = "workspace_file_operation"


@dataclass(frozen=True)
class PoE3BSessionDispatch:
    """One observed invocation of the bounded transport surface."""

    sequence: int
    operation: PoE3BSessionOperation


@dataclass(frozen=True)
class PoE3BCleanupResult:
    deleted: tuple[str, ...]
    problems: tuple[str, ...]


class PoE3BSessionTransport(Protocol):
    """Narrow backend contract; deliberately exposes no raw send primitive."""

    def bridge_healthy(self) -> bool: ...
    def mailbox_entries(self) -> tuple[str, ...]: ...
    def start_control_bridge(self) -> dict: ...
    def stop_control_bridge(self) -> None: ...
    def environment(self) -> dict: ...
    def inventory_fingerprint(self) -> str: ...
    def device_names(self) -> frozenset[str]: ...
    def create_device(
        self, model: str, name: str, required_ports: tuple[str, ...], *, arm: str,
    ) -> PoEDeliveryDeviceIdentity: ...
    def create_link(
        self,
        switch: PoEDeliveryDeviceIdentity,
        switch_port: str,
        endpoint: PoEDeliveryDeviceIdentity,
        endpoint_port: str,
    ) -> PoEDeliveryLinkIdentity: ...
    def wait_until_ready(
        self, switch_name: str, *, timeout_seconds: float,
    ) -> DeviceInitializationResult: ...
    def apply_inline_mode(
        self, switch_name: str, switch_ports: tuple[str, ...], mode: PoEInlineMode,
    ) -> None: ...
    def capture_inline_status(
        self, switch_name: str, switch_ports: tuple[str, ...], label: str,
    ) -> PoE2Capture: ...
    def delete_device(self, name: str) -> bool: ...
    def retire_session_residue(
        self, preexisting: frozenset[str],
    ) -> tuple[str, ...]: ...
    def wait_for_inventory_fingerprint(self, expected: str) -> str: ...
    def collect_completed(self) -> None: ...
    def transport_problems(self) -> tuple[str, ...]: ...


class PacketTracerPoE3BSession:
    """Govern one POE-3B fixture lifecycle and hide every raw PT capability."""

    def __init__(
        self,
        run_id: str,
        *,
        switch_ports: tuple[str, ...],
        endpoint_role: str = "PH",
        transport: PoE3BSessionTransport | None = None,
    ) -> None:
        if (
            type(run_id) is not str
            or not run_id
            or run_id != run_id.strip()
            or type(endpoint_role) is not str
            or not endpoint_role
            or endpoint_role != endpoint_role.strip()
        ):
            raise ValueError("Session and endpoint identities must be exact.")
        if (
            not isinstance(switch_ports, tuple)
            or not switch_ports
            or any(
                type(port) is not str
                or _PORT_NAME.fullmatch(port) is None
                for port in switch_ports
            )
            or len(set(switch_ports)) != len(switch_ports)
        ):
            raise ValueError("switch_ports must be an ordered, nonempty unique tuple")
        self.switch_ports = switch_ports
        self.switch_name = "MCP-POE3B-SW-" + run_id
        self.endpoint_prefix = "MCP-POE3B-" + endpoint_role + "-" + run_id
        self._transport = transport or PacketTracerPoE3BLiveTransport()
        self._file_operations = PacketTracerFileOperationGuard.ephemeral()
        self._dispatches: list[PoE3BSessionDispatch] = []
        self._attempted: list[str] = []
        self._created: list[str] = []

    @property
    def dispatches(self) -> tuple[PoE3BSessionDispatch, ...]:
        return tuple(self._dispatches)

    @property
    def attempted_device_names(self) -> tuple[str, ...]:
        return tuple(self._attempted)

    @property
    def created_device_names(self) -> tuple[str, ...]:
        return tuple(self._created)

    def file_operation_ledger(self) -> PacketTracerFileOperationLedger:
        return self._file_operations.snapshot()

    def attempt_workspace_file_operation(
        self,
        operation: str,
        callback: Callable[[], PacketTracerFileOperationResult[_T]],
    ) -> _T:
        """Route any PT workspace-file request through the session-owned guard."""

        self._observe(PoE3BSessionOperation.WORKSPACE_FILE_OPERATION)
        return self._file_operations.attempt(operation, callback)

    def bridge_healthy(self) -> bool:
        return self._call(
            PoE3BSessionOperation.TRANSPORT_HEALTH,
            self._transport.bridge_healthy,
        )

    def mailbox_entries(self) -> tuple[str, ...]:
        return self._call(
            PoE3BSessionOperation.MAILBOX_OBSERVATION,
            self._transport.mailbox_entries,
        )

    def start_control_bridge(self) -> dict:
        return self._call(
            PoE3BSessionOperation.CONTROL_BRIDGE_START,
            self._transport.start_control_bridge,
        )

    def stop_control_bridge(self) -> None:
        self._call(
            PoE3BSessionOperation.CONTROL_BRIDGE_STOP,
            self._transport.stop_control_bridge,
        )

    def environment(self) -> dict:
        return self._call(
            PoE3BSessionOperation.ENVIRONMENT_OBSERVATION,
            self._transport.environment,
        )

    def inventory_fingerprint(self) -> str:
        return self._call(
            PoE3BSessionOperation.INVENTORY_OBSERVATION,
            self._transport.inventory_fingerprint,
        )

    def device_names(self) -> frozenset[str]:
        return self._call(
            PoE3BSessionOperation.DEVICE_NAMES_OBSERVATION,
            self._transport.device_names,
        )

    def create_fixture(
        self,
        switch_model: str,
        bindings: tuple[PoEAuthorizedBinding, ...],
    ) -> dict:
        """Create only the exact ordered simultaneous fixture passed by the plan."""

        if (
            not isinstance(bindings, tuple)
            or not bindings
            or tuple(binding.switch_port for binding in bindings) != self.switch_ports
            or len(set(bindings)) != len(bindings)
        ):
            raise ValueError("Fixture bindings differ from the governed session ports.")
        self._attempted.append(self.switch_name)
        switch = self._call(
            PoE3BSessionOperation.FIXTURE_DEVICE_CREATE,
            lambda: self._transport.create_device(
                switch_model,
                self.switch_name,
                self.switch_ports,
                arm="candidate",
            ),
        )
        self._created.append(self.switch_name)
        if switch.model != switch_model:
            raise RuntimeError("Fixture switch model readback mismatch")

        endpoints = []
        links = []
        for index, binding in enumerate(bindings, start=1):
            name = self.endpoint_prefix + "-" + str(index)
            self._attempted.append(name)
            endpoint = self._call(
                PoE3BSessionOperation.FIXTURE_DEVICE_CREATE,
                lambda binding=binding, name=name: self._transport.create_device(
                    binding.endpoint_model,
                    name,
                    (binding.endpoint_port,),
                    arm="candidate",
                ),
            )
            self._created.append(name)
            if endpoint.model != binding.endpoint_model:
                raise RuntimeError("Fixture endpoint model readback mismatch")
            link = self._call(
                PoE3BSessionOperation.FIXTURE_LINK_CREATE,
                lambda binding=binding, endpoint=endpoint: self._transport.create_link(
                    switch,
                    binding.switch_port,
                    endpoint,
                    binding.endpoint_port,
                ),
            )
            endpoints.append(_model_dump(endpoint))
            links.append(_model_dump(link))
        return {
            "switch": _model_dump(switch),
            "endpoints": endpoints,
            "links": links,
        }

    def wait_until_ready(
        self, *, timeout_seconds: float,
    ) -> DeviceInitializationResult:
        return self._call(
            PoE3BSessionOperation.DEVICE_READINESS,
            lambda: self._transport.wait_until_ready(
                self.switch_name, timeout_seconds=timeout_seconds,
            ),
        )

    def apply_inline_mode(self, mode: PoEInlineMode) -> None:
        if not isinstance(mode, PoEInlineMode):
            raise TypeError("The inline power mode must come from the closed enum.")
        self._call(
            PoE3BSessionOperation.INLINE_MODE_APPLY,
            lambda: self._transport.apply_inline_mode(
                self.switch_name, self.switch_ports, mode,
            ),
        )

    def capture_inline_status(self, label: str) -> PoE2Capture:
        return self._call(
            PoE3BSessionOperation.INLINE_CAPTURE,
            lambda: self._transport.capture_inline_status(
                self.switch_name, self.switch_ports, label,
            ),
        )

    def cleanup_fixture(self) -> PoE3BCleanupResult:
        deleted: list[str] = []
        problems: list[str] = []
        for name in reversed(self._attempted):
            try:
                removed = self._call(
                    PoE3BSessionOperation.FIXTURE_DEVICE_DELETE,
                    lambda name=name: self._transport.delete_device(name),
                )
            except Exception as exc:
                problems.append(f"Cleanup {name}: {exc}")
                continue
            if removed:
                deleted.append(name)
            else:
                problems.append("Cleanup did not verify deletion: " + name)
        return PoE3BCleanupResult(tuple(deleted), tuple(problems))

    def retire_session_residue(
        self, preexisting: frozenset[str],
    ) -> tuple[str, ...]:
        return self._call(
            PoE3BSessionOperation.RESIDUE_RETIRE,
            lambda: self._transport.retire_session_residue(preexisting),
        )

    def wait_for_inventory_fingerprint(self, expected: str) -> str:
        return self._call(
            PoE3BSessionOperation.INVENTORY_RESTORATION,
            lambda: self._transport.wait_for_inventory_fingerprint(expected),
        )

    def collect_completed(self) -> None:
        self._call(
            PoE3BSessionOperation.IPC_DRAIN,
            self._transport.collect_completed,
        )

    def transport_problems(self) -> tuple[str, ...]:
        return self._call(
            PoE3BSessionOperation.TRANSPORT_PROBLEMS,
            self._transport.transport_problems,
        )

    def _observe(self, operation: PoE3BSessionOperation) -> None:
        self._dispatches.append(PoE3BSessionDispatch(
            sequence=len(self._dispatches) + 1,
            operation=operation,
        ))

    def _call(self, operation: PoE3BSessionOperation, callback: Callable[[], _T]) -> _T:
        self._observe(operation)
        return callback()


class PacketTracerPoE3BLiveTransport:
    """Private composition of the existing productive Packet Tracer runtimes."""

    def __init__(
        self,
        *,
        bridge: FileBridge | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._bridge = bridge or FileBridge()
        self._sleeper = sleeper
        self._fixture = PacketTracerPoEDeliveryFixtureRuntime(
            self._send_and_wait, BUILD,
        )
        self._executor = ControlledIosExecutor(self._send_and_wait)
        self._observer = GovernedPoEInlineObserver(self._executor)
        self._configuration = PacketTracerConfigurationRuntime(self._bridge.send)
        self._control_bridge: PTCommandBridge | None = None
        self._transport_problems: list[str] = []

    def bridge_healthy(self) -> bool:
        return self._bridge.pt_alive()

    def mailbox_entries(self) -> tuple[str, ...]:
        return tuple(sorted(
            path.name
            for pattern in ("req_*.js", "res_*.txt")
            for path in self._bridge.dir.glob(pattern)
        ))

    def start_control_bridge(self) -> dict:
        if self._control_bridge is not None:
            raise RuntimeError("The POE-3B control bridge was already started.")
        bridge = PTCommandBridge(port=54321, token=token_urlsafe(32))
        bridge.start()
        self._control_bridge = bridge
        return _authenticated_status(bridge)

    def stop_control_bridge(self) -> None:
        bridge, self._control_bridge = self._control_bridge, None
        if bridge is not None:
            bridge.stop()

    def environment(self) -> dict:
        return self._read_json(_ENVIRONMENT_JS, timeout=15.0)

    def inventory_fingerprint(self) -> str:
        return self._fixture.inventory_fingerprint()

    def device_names(self) -> frozenset[str]:
        names = self._read_json(_DEVICE_NAMES_JS, timeout=15.0).get("devices")
        if not isinstance(names, list) or not all(type(name) is str for name in names):
            raise RuntimeError("Packet Tracer returned malformed device names.")
        return frozenset(names)

    def create_device(
        self, model: str, name: str, required_ports: tuple[str, ...], *, arm: str,
    ) -> PoEDeliveryDeviceIdentity:
        return self._fixture.create_device(
            model, name, required_ports, arm=arm,
        )

    def create_link(
        self,
        switch: PoEDeliveryDeviceIdentity,
        switch_port: str,
        endpoint: PoEDeliveryDeviceIdentity,
        endpoint_port: str,
    ) -> PoEDeliveryLinkIdentity:
        return self._fixture.create_link(
            switch, switch_port, endpoint, endpoint_port,
        )

    def wait_until_ready(
        self, switch_name: str, *, timeout_seconds: float,
    ) -> DeviceInitializationResult:
        return self._executor.wait_until_ready(
            switch_name, timeout_seconds=timeout_seconds,
        )

    def apply_inline_mode(
        self, switch_name: str, switch_ports: tuple[str, ...], mode: PoEInlineMode,
    ) -> None:
        for port in switch_ports:
            if not self._configuration.configure_ios(
                switch_name, _inline_mode_payload(port, mode),
            ):
                raise RuntimeError("Inline power mode was not queued.")
            self._sleeper(6.0)
            self._bridge.collect_completed()
            if self._bridge._pending:
                raise RuntimeError("Inline power mode dispatch is still pending.")

    def capture_inline_status(
        self, switch_name: str, switch_ports: tuple[str, ...], label: str,
    ) -> PoE2Capture:
        started = _utc()
        first = self._observer.observe_poe_inline_status(
            switch_name, switch_ports,
        )
        prompt = first.command_result.expected_prompt if first.command_result else ""
        self._sleeper(2.0)
        second = self._observer.observe_poe_inline_status(
            switch_name, switch_ports,
        )
        first_payload = _serialize_observation(first)
        second_payload = _serialize_observation(second)
        stable = first.raw_output == second.raw_output
        return PoE2Capture(
            label=label,
            started_at_utc=started,
            completed_at_utc=_utc(),
            expected_prompt=prompt,
            observation=first_payload,
            repeat_observation=second_payload,
            table_completeness=completeness(
                first_payload, prompt, stable, switch_name,
            ),
            stable=stable,
            raw_file=label.lower() + ".txt",
            raw_sha256=hashlib.sha256(first.raw_output.encode()).hexdigest(),
        )

    def delete_device(self, name: str) -> bool:
        return self._fixture.delete_device(name)

    def retire_session_residue(
        self, preexisting: frozenset[str],
    ) -> tuple[str, ...]:
        return self._fixture.retire_session_residue(preexisting)

    def wait_for_inventory_fingerprint(self, expected: str) -> str:
        return self._fixture.wait_for_inventory_fingerprint(expected)

    def collect_completed(self) -> None:
        self._bridge.collect_completed()

    def transport_problems(self) -> tuple[str, ...]:
        return tuple(self._transport_problems)

    def _send_and_wait(self, script: str, timeout: float = 12.0) -> str | None:
        result = self._bridge.send_and_wait(script, timeout)
        if result is None:
            self._transport_problems.append(self._bridge.last_disposition.value)
        return result

    def _read_json(self, script: str, *, timeout: float) -> dict:
        raw = self._send_and_wait(script, timeout)
        if raw is None or raw.startswith(("ERROR:", "PT_ERROR:")):
            raise RuntimeError("Governed environment read failed: " + str(raw))
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError("Packet Tracer returned a non-object environment read.")
        return value


def _inline_mode_payload(interface: str, mode: PoEInlineMode) -> str:
    return "\n".join((
        "enable",
        "configure terminal",
        f"interface {interface}",
        f" power inline {mode.value}",
        " exit",
        "end",
    ))


def _model_dump(value) -> dict:
    return value.model_dump(mode="json")


def _serialize_observation(value) -> dict:
    return json.loads(json.dumps(
        asdict(value),
        default=lambda item: item.value if isinstance(item, Enum) else str(item),
    ))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _authenticated_status(bridge: PTCommandBridge) -> dict:
    url = f"http://127.0.0.1:{bridge.port}/status"
    try:
        urlopen(url, timeout=3)
    except HTTPError as exc:
        unauthenticated = exc.code
    else:
        raise RuntimeError("Unauthenticated bridge accepted request.")
    with urlopen(
        Request(url, headers={"X-PT-Token": bridge.token}), timeout=3,
    ) as response:
        authenticated = response.status
    if unauthenticated != 401 or authenticated != 200:
        raise RuntimeError("Authentication gate failed.")
    return {
        "pid": os.getpid(),
        "token_fingerprint": bridge.token_id,
        "authenticated_status": authenticated,
        "unauthenticated_status": unauthenticated,
        "active_pt_transport": "file_bridge_user_acl",
        "webview_http_connection_claimed": False,
    }


_DEVICE_NAMES_JS = (
    "try{var net=ipc.network();var n=net.getDeviceCount();var a=[];"
    "for(var i=0;i<n;i++){a.push(String(net.getDeviceAt(i).getName()));}"
    "reportResult(JSON.stringify({devices:a}));}catch(e){reportResult('ERROR:'+e);}"
)

_ENVIRONMENT_JS = (
    "try{var a=ipc.appWindow();var f=a.getActiveFile();var s=ipc.simulation();"
    "var net=ipc.network();reportResult(JSON.stringify({"
    "found:(f?true:false),saved_filename:(f?String(f.getSavedFilename()||''):''),"
    "pt_version:(f?String(f.getVersion()||''):''),"
    "simulation_mode:(typeof s.isSimulationMode==='function'?s.isSimulationMode():null),"
    "devices:net.getDeviceCount(),links:net.getLinkCount()}));}"
    "catch(e){reportResult('ERROR:'+e);}"
)

_PORT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9./:-]{0,79}$")
