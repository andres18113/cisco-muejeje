"""Controlled boundaries for the cold-HTTP acceptance route.

Only what lies outside this process is controlled: the Packet Tracer terminal,
the monotonic clock and the sleeper, the git checkout, the process table and
the location of the shared campaign scope. The acceptance coordinator, the
shared session composition, the product use case, both runtimes, the readiness
loop, the ledger and every store are the production ones.

The terminal extends the public-route simulator with time: each answer can
depend on how long ago the question was first asked, and each dispatch can
take simulated time, so bounded waits run to their real limits in a few
milliseconds.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from service_entry_fixture import (
    BACKEND_VERSION,
    DEPLOYMENT_ID,
    FINGERPRINT,
    IsolationPreflight,
    deployed_topology,
    intent_payload,
)
from service_product_simulation import SimulatedProductTransport

from packet_tracer_mcp.adapters.cli.cold_http_acceptance import (
    acceptance_session,
    production_boundaries,
)
from packet_tracer_mcp.application.ports.service_qualification import OpenedTransport
from packet_tracer_mcp.application.use_cases.accept_cold_http import (
    AcceptanceBoundaries,
    AcceptanceRequest,
    AcceptanceResult,
    accept_cold_http,
)
from packet_tracer_mcp.application.use_cases.qualify_server_services import (
    RuntimeIdentity,
)
from packet_tracer_mcp.domain.enterprise.models.deployment import (
    DeploymentManifest,
    build_deployment_manifest,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
    DiagnosticLifecycleObservation,
    RepositoryIdentity,
)
from packet_tracer_mcp.domain.enterprise.models.service_run_record import (
    SourceTreeIdentity,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)
from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
    FileCampaignCoordinator,
)
from packet_tracer_mcp.infrastructure.persistence.cold_http_acceptance_store import (
    ColdHttpAcceptanceStore,
)
from packet_tracer_mcp.infrastructure.persistence.deployment_manifest_store import (
    DeploymentManifestStore,
)
from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
    ServiceRunRecordStore,
)

SHA = "0123456789abcdef0123456789abcdef01234567"
TREE = "89abcdef0123456789abcdef0123456789abcdef"
ATTEMPT = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
MARKER = "COLD_HTTP_" + ATTEMPT
PROCESS_ID = 4242
PROCESS_PATH = r"C:\Program Files\Cisco Packet Tracer 9.0.1\bin\PacketTracer.exe"
INCARNATION = "2026-09-22T09:00:00.0000000-05:00"
SWITCH = "HQ-DEFAULT-ACCESS-SW-01"
SERVER = "HQ-DEFAULT-SERVER-01"
PC1 = "HQ-DEFAULT-PC-01"
PC2 = "HQ-DEFAULT-PC-02"
SERVER_IP = "198.18.160.2"


#: Stands for the fixture grant, so `None` can mean a missing grant.
DEFAULT_GRANT = object()


class FakeClock:
    """A monotonic clock only sleeps and simulated latency advance."""

    def __init__(self, start: float = 1000.0) -> None:
        """Start the clock at an arbitrary monotonic origin."""
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        """Return the current monotonic time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Record one sleep and let exactly that much time pass."""
        self.sleeps.append(seconds)
        self.now += max(0.0, seconds)


def cold_http_intent(marker: str = MARKER) -> str:
    """Return the HTTP-only intent with the attempt marker compiled in."""
    payload = intent_payload()
    services = [
        dict(service)
        for service in payload["sites"][0]["services"]
        if service["service_type"] == "http"
    ]
    services[0]["http_content"] = marker
    payload["sites"][0]["services"] = services
    return json.dumps(payload)


def acceptance_manifest() -> DeploymentManifest:
    """Build the manifest a file-channel physical deployment would record."""
    topology, inventory = deployed_topology()
    return build_deployment_manifest(
        topology,
        inventory,
        fingerprint=FINGERPRINT.model_copy(
            update={"bridge_transport": "file", "runtime_mode": "logical-workspace"}
        ),
        deployment_id=DEPLOYMENT_ID,
    )


def grant_document(
    manifest: DeploymentManifest, intent_json: str, **overrides: Any
) -> dict[str, Any]:
    """Return the exact grant the fixture deployment and intent require."""
    document: dict[str, Any] = {
        "schema_version": 1,
        "authorization_id": "AUTH-COLD-HTTP-OFFLINE",
        "attempt_id": ATTEMPT,
        "sha": SHA,
        "tree": TREE,
        "build": BACKEND_VERSION,
        "channel": "file",
        "deployment_id": DEPLOYMENT_ID,
        "manifest_hash": manifest.semantic_hash,
        "physical_topology_hash": manifest.physical_topology_hash,
        "intent_sha256": hashlib.sha256(intent_json.encode("utf-8")).hexdigest(),
        "switch": SWITCH,
        "switch_model": "IE-2000",
        "vlan_id": 10,
        "prefix_length": 29,
        "gateway": "198.18.160.1",
        "server": {
            "name": SERVER,
            "interface": "FastEthernet0",
            "ipv4": SERVER_IP,
            "switch_port": "FastEthernet1/3",
        },
        "clients": [
            {
                "name": PC1,
                "interface": "FastEthernet0",
                "ipv4": "198.18.160.3",
                "switch_port": "FastEthernet1/1",
            },
            {
                "name": PC2,
                "interface": "FastEthernet0",
                "ipv4": "198.18.160.4",
                "switch_port": "FastEthernet1/2",
            },
        ],
        "marker": MARKER,
        "url": f"http://{SERVER_IP}/",
        "max_operations": 1015,
        "max_seconds": 420,
        "reserve_operations": 2,
        "reserve_seconds": 40,
        "process_id": PROCESS_ID,
        "process_path": PROCESS_PATH,
        "process_incarnation": INCARNATION,
        "exclusive_disposable_lab": True,
        "local_fence_limitation_accepted": True,
    }
    document.update(overrides)
    return document


def _json_argument(script: str, pattern: str) -> str:
    match = re.search(pattern, script)
    return str(json.loads(match.group(1))) if match else ""


class ColdHttpTerminal(SimulatedProductTransport):
    """The shared simulated terminal, answering as a function of time.

    Every `*_after` knob is measured from the first time that kind of question
    was asked, so "forwarding after 26 seconds" means 26 seconds into the
    readiness episode, whatever preceded it. `math.inf` means never.
    """

    def __init__(self, tmp_path: Path, inventory: list, clock: FakeClock) -> None:
        """Bind the terminal to the attempt's clock."""
        super().__init__(tmp_path, inventory)
        self.clock = clock
        self.ios_ready_after = 0.0
        self.vlan_present_after = 0.0
        self.endpoint_ready_after = 0.0
        self.forwarding_after: float | None = 0.0
        self.page_visible_after = 0.0
        self.alive = True
        self.pending = False
        self.latency: Callable[[str], float] = lambda script: 0.0
        self.start_overrides: dict[str, Any] = {}
        self.start_undelivered = False
        self.readiness_overrides: dict[str, Any] = {}
        self.release_answer: dict[str, Any] | str | None = None
        self.on_dispatch: Callable[[str], None] | None = None
        self.first_asked: dict[str, float] = {}
        self.last_start_at: float | None = None
        #: Clients a delivered start created and no release deleted yet.
        self.owned_clients: set[str] = set()
        self.log: list[tuple[float, str]] = []

    # -- time -----------------------------------------------------------------

    def _since_first(self, kind: str) -> float:
        first = self.first_asked.setdefault(kind, self.clock())
        return self.clock() - first

    def _dispatched(self, script: str, kind: str, timeout: float) -> bool:
        """Spend the answer's latency; report whether it came within timeout.

        An answer slower than the caller's timeout is not delivered, which is
        what the file channel does: the caller gets no correlated answer.
        """
        self.log.append((self.clock(), kind))
        if self.on_dispatch is not None:
            self.on_dispatch(kind)
        latency = max(0.0, float(self.latency(script)))
        if latency > timeout > 0:
            self.clock.now += timeout
            return False
        self.clock.now += latency
        return True

    # -- channel ----------------------------------------------------------------

    def pt_alive(self) -> bool:
        """Report the heartbeat the test chose."""
        return self.alive

    def has_pending_requests(self) -> bool:
        """Report whether a fire-and-forget command is still unresolved."""
        return self.pending

    def collect_completed(self) -> int:
        """Retire nothing; the simulated engine answers synchronously."""
        return 0

    def send(self, script: str) -> bool:
        """Accept one fire-and-forget payload."""
        self._dispatched(script, "send", 0.0)
        return super().send(script)

    def send_and_wait(self, script: str, timeout: float) -> str:
        """Answer one waited read, as it would be answered at this moment."""
        kind = self._kind(script)
        if not self._dispatched(script, kind, timeout):
            return None
        if kind == "environment":
            return json.dumps(
                {
                    "found": True,
                    "backend": "packet_tracer",
                    "backend_version": BACKEND_VERSION,
                    "extension_version": "",
                    "runtime_mode": "logical-workspace",
                }
            )
        if kind == "ios_state" and self._since_first(kind) < self.ios_ready_after:
            return json.dumps(
                {"found": True, "booting": True, "terminal": False, "prompt": ""}
            )
        if kind == "vlan" and self._since_first(kind) < self.vlan_present_after:
            return json.dumps(
                {"found": True, "configuration_channel": False, "present": False}
            )
        device = _json_argument(script, r"getDevice\((\"(?:\\.|[^\"\\])*\")\)")
        readback = f"endpoint:{device}" if self.send_payloads else "endpoint:drift"
        if kind == "endpoint" and (
            self._since_first(readback) < self.endpoint_ready_after
            and self.send_payloads
        ):
            return json.dumps(
                {
                    "found": True,
                    "port_found": True,
                    "interface": "FastEthernet0",
                    "address_channel": True,
                    "ipv4": "",
                    "netmask": "",
                    "device": device,
                }
            )
        if kind == "readiness":
            if self.forwarding_after is None:
                self.spanning_tree_state = "FWD"
            else:
                elapsed = self._since_first(kind)
                self.spanning_tree_state = (
                    "FWD" if elapsed >= self.forwarding_after else "LIS"
                )
            answer = super().send_and_wait(script, timeout)
            if self.readiness_overrides and "owner_name:owner" in script:
                payload = json.loads(answer)
                payload.update(self.readiness_overrides)
                return json.dumps(payload)
            return answer
        return super().send_and_wait(script, timeout)

    def dispatch_and_wait(self, script: str, timeout: float):
        """Answer one typed dispatch, as it would be answered at this moment."""
        kind = self._kind(script)
        delivered = self._dispatched(script, kind, timeout)
        key = _json_argument(script, r"__mcpE6HttpClients\[(\"(?:\\.|[^\"\\])*\")\]")
        if kind == "http_release":
            key = _json_argument(script, r"var slot=bag\[(\"(?:\\.|[^\"\\])*\")\]")
        outcome = super().dispatch_and_wait(script, timeout)
        if kind == "http_start":
            self.last_start_at = self.clock()
            payload = json.loads(outcome.body)
            payload.update(self.start_overrides)
            if payload.get("owned") is True:
                self.owned_clients.add(key)
            if self.start_undelivered:
                delivered = False
            outcome = replace(outcome, body=json.dumps(payload))
        elif kind == "http_inspect":
            started = self.last_start_at if self.last_start_at is not None else 0.0
            if self.clock() - started < self.page_visible_after:
                outcome = replace(
                    outcome, body=json.dumps({"found": True, "content": ""})
                )
        elif kind == "http_release":
            if self.release_answer is not None:
                body = (
                    self.release_answer
                    if isinstance(self.release_answer, str)
                    else json.dumps(self.release_answer)
                )
            elif key in self.owned_clients:
                self.owned_clients.discard(key)
                body = json.dumps(
                    {"found": True, "deleted": True, "present": False, "error": ""}
                )
            else:
                body = json.dumps(
                    {"found": False, "deleted": False, "present": False, "error": ""}
                )
            outcome = replace(outcome, body=body)
        if not delivered:
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                result=ResultFact.NOT_OBSERVED,
                detail="response_timeout",
            )
        return outcome

    @staticmethod
    def _kind(script: str) -> str:
        if "application_version_unavailable" in script:
            return "environment"
        if "var names=" in script and "wanted=" in script:
            return "inventory"
        if "terminal_kind:'ios_command_line'" in script:
            return "ios_state"
        if "getVlanCount" in script:
            return "vlan"
        if "owner_device_name" in script and "getAccessVlan" in script:
            return "access_port"
        if "address_channel:able" in script:
            return "endpoint"
        if "owner_name:owner" in script or (
            "enterCommand" in script and "expected_prompt" in script
        ):
            return "readiness"
        if "getCurrentFrameInstanceIndex" in script:
            return "readiness_auxiliary"
        if "var results=[]" in script:
            return "e6_apply"
        if "out.content=String(p.getPage" in script:
            return "e6_direct"
        if "content_before:before" in script:
            return "http_start"
        if "var found=!!(slot&&slot.manager&&slot.client)" in script:
            return "http_release"
        if "var bag=this.__mcpE6HttpClients" in script:
            return "http_inspect"
        return "other"


@dataclass
class FakeLifecycle:
    """The local process table and mailbox, read before and after the run."""

    clock: FakeClock
    observations: list[DiagnosticLifecycleObservation] = field(default_factory=list)
    duration: float = 0.5
    deadlines: list[float | None] = field(default_factory=list)

    def read(self, deadline: float | None = None) -> DiagnosticLifecycleObservation:
        """Return the next scripted observation, spending local time."""
        self.deadlines.append(deadline)
        self.clock.now += self.duration
        if len(self.observations) > 1:
            return self.observations.pop(0)
        return self.observations[0]


@dataclass
class FakeReceiver:
    """The paired receiver as each governed dispatch reads it.

    It answers from the same observation shape the production readers use.
    `replace_with` stands for whatever happened to the process table: a new
    PID, a new incarnation under the same PID, no process, two processes, or
    an identity that cannot be read. `cost` is the local time one reading
    spends, so feasibility is never shown only by a zero-latency trace.
    """

    clock: FakeClock
    observation: DiagnosticLifecycleObservation
    cost: float = 0.0
    checks: int = 0
    deadlines: list[float] = field(default_factory=list)
    bound_to: DiagnosticLifecycleObservation | None = None
    closed: bool = False
    bind_error: Exception | None = None

    def bind(self, preflight: DiagnosticLifecycleObservation, deadline: float):
        """Bind to the preflight pairing, as the composition would."""
        if self.bind_error is not None:
            raise self.bind_error
        self.bound_to = preflight
        return self

    def observe(self, deadline: float) -> DiagnosticLifecycleObservation:
        """Return the current reading, spending its local cost."""
        self.checks += 1
        self.deadlines.append(deadline)
        self.clock.now += self.cost
        return self.observation

    def replace_with(self, observation: DiagnosticLifecycleObservation) -> None:
        """Make every later reading describe another process state."""
        self.observation = observation

    def close(self) -> None:
        """Release the binding."""
        self.closed = True


def paired_process(**overrides: Any) -> DiagnosticLifecycleObservation:
    """Return the granted Packet Tracer incarnation with a quiet mailbox."""
    values: dict[str, Any] = {
        "process_id": PROCESS_ID,
        "process_path": PROCESS_PATH,
        "product_version": BACKEND_VERSION,
        "file_version": BACKEND_VERSION,
        "process_incarnation": INCARNATION,
        "mailbox_entries": (),
    }
    values.update(overrides)
    return DiagnosticLifecycleObservation(**values)


def published_checkout(**overrides: Any) -> RepositoryIdentity:
    """Return the clean, published checkout the grant names."""
    values: dict[str, Any] = {
        "branch": "feature/server-pt-goal-foundations",
        "head": SHA,
        "tree": TREE,
        "clean": True,
        "upstream": "cisco/feature/server-pt-goal-foundations",
        "upstream_head": SHA,
    }
    values.update(overrides)
    return RepositoryIdentity(**values)


@dataclass
class Harness:
    """One attempt's controlled world, with the production composition inside."""

    root: Path
    clock: FakeClock
    terminal: ColdHttpTerminal
    manifest: DeploymentManifest
    lifecycle: FakeLifecycle
    record_store: ServiceRunRecordStore
    envelope_store: ColdHttpAcceptanceStore
    coordinator: FileCampaignCoordinator
    boundaries: AcceptanceBoundaries
    source: SourceTreeIdentity
    intent_json: str
    receiver: FakeReceiver
    opened_channels: list[str] = field(default_factory=list)

    def grant(self, **overrides: Any) -> dict[str, Any]:
        """Return the fixture grant, with any field overridden."""
        return grant_document(self.manifest, self.intent_json, **overrides)

    def run(
        self,
        *,
        grant: object = DEFAULT_GRANT,
        intent_json: str | None = None,
        execute: bool = True,
    ) -> AcceptanceResult:
        """Run one attempt through the production coordinator."""
        document = self.grant() if grant is DEFAULT_GRANT else grant
        return accept_cold_http(
            AcceptanceRequest(
                execute=execute,
                grant_document=document,
                grant_text=json.dumps(document, sort_keys=True),
                intent_json=intent_json
                if intent_json is not None
                else self.intent_json,
            ),
            self.boundaries,
        )

    def product_dispatches(self) -> list[str]:
        """Return the kinds the terminal was asked, in order."""
        return [kind for _, kind in self.terminal.log]


def build_harness(tmp_path: Path, **boundary_overrides: Any) -> Harness:
    """Compose the production boundaries with only the external ones controlled."""
    root = tmp_path / "checkout"
    clock = FakeClock()
    manifest = acceptance_manifest()
    _topology, inventory = deployed_topology()
    terminal = ColdHttpTerminal(tmp_path, inventory, clock)
    lifecycle = FakeLifecycle(clock, [paired_process()])
    receiver = FakeReceiver(clock, paired_process())
    source = SourceTreeIdentity(sha=SHA, tree=TREE, dirty=False)
    harness_holder: dict[str, Harness] = {}

    def open_channel(channel: str) -> OpenedTransport:
        harness_holder["h"].opened_channels.append(channel)
        live = terminal.pt_alive()
        return OpenedTransport(
            channel, terminal, live, "heartbeat_fresh" if live else "heartbeat_stale"
        )

    boundaries = production_boundaries(root)
    manifest_store = DeploymentManifestStore(root / "data" / "deployments")
    manifest_store.save_verified(manifest)
    coordinator = FileCampaignCoordinator(tmp_path / "campaign")
    boundaries = replace(
        boundaries,
        import_preflight=IsolationPreflight(),
        runtime_identity=lambda: RuntimeIdentity("python", "packet_tracer_mcp"),
        repository=published_checkout,
        lifecycle=lifecycle.read,
        campaign_coordinator=coordinator,
        manifest_store=manifest_store,
        open_channel=open_channel,
        close_channel=lambda opened: None,
        session_factory=partial(
            acceptance_session, observe_source=lambda: harness_holder["h"].source
        ),
        clock=clock,
        sleep=clock.sleep,
        now=lambda: datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
        bind_receiver=receiver.bind,
    )
    boundaries = replace(boundaries, **boundary_overrides)
    harness = Harness(
        root=root,
        clock=clock,
        terminal=terminal,
        manifest=manifest,
        lifecycle=lifecycle,
        record_store=boundaries.record_store,
        envelope_store=boundaries.envelope_store,
        coordinator=coordinator,
        boundaries=boundaries,
        source=source,
        intent_json=cold_http_intent(),
        receiver=receiver,
    )
    harness_holder["h"] = harness
    return harness


NEVER = math.inf
