"""SIMULATED Packet Tracer for a compiler-derived wired campus.

Nothing here is Packet Tracer. It is a deterministic stand-in for what lies
beyond the bridge, driven entirely by the plans the real product compiles: the
access ports and VLANs, the trunk links and the endpoint addresses the product
sends. It answers the exact scripts the production runtimes dispatch, as the
single-switch simulator does, for any number of switches and clients.

Spanning tree is simulated per VLAN from the compiled trunk links: in each
connected part the switch with the smallest name is the root, a breadth-first
tree forwards on both ends of its links, and every other link forwards on the
end nearer the root and blocks on the other. So the planner's redundant uplinks
produce the blocked trunk ports a real campus would show, and a path either
exists through forwarding trunks or it does not.

Faults are explicit knobs: a trunk link that is down, an access port that never
forwards, a switch whose terminal cannot be attributed, and per-switch delays
before access ports or trunks forward. Every answer keeps the same timing model
as `ColdHttpTerminal`: questions and dispatches can take simulated time, and
"after" knobs are measured from the first time that kind of question was asked.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cold_http_acceptance_harness import ColdHttpTerminal, FakeClock, _json_argument

_DEVICE = r"getDevice\((\"(?:\\.|[^\"\\])*\")\)"
_COMMAND = r"enterCommand\((\"(?:\\.|[^\"\\])*\")\)"


def _short(interface: str, *, trunk_table: bool = False) -> str:
    """Abbreviate an interface the way the measured PT pages print it."""
    for full, stp, trunk in (
        ("GigabitEthernet", "Gi", "Gig"),
        ("FastEthernet", "Fa", "Fa"),
    ):
        if interface.startswith(full):
            return (trunk if trunk_table else stp) + interface[len(full) :]
    return interface


def _vlan_list(values) -> str:
    return ",".join(str(item) for item in sorted(values)) or "none"


@dataclass
class TrunkEnd:
    """One compiled trunk end on one simulated switch."""

    interface: str
    peer: str
    peer_interface: str
    link_id: str
    allowed: frozenset[int]


@dataclass
class SimulatedSwitch:
    """One switch as the compiled plan configures it."""

    name: str
    vlans: set[int] = field(default_factory=set)
    access: dict[str, int] = field(default_factory=dict)
    trunks: dict[str, TrunkEnd] = field(default_factory=dict)


class CampusNetwork:
    """The wired network one compiled configuration plan describes."""

    def __init__(
        self,
        configuration_plan: Any,
        deployed_names: dict[str, str],
        foundation_action_ids: set[str] | None = None,
    ):
        """Build every switch from the compiled E5 actions and deployed names."""
        self.switches: dict[str, SimulatedSwitch] = {}
        self.down_links: set[str] = set()
        self.blocked_access: set[tuple[str, str]] = set()
        trunk_rows: dict[str, list[Any]] = {}

        def switch(device_id: str, fallback: str) -> SimulatedSwitch:
            name = deployed_names.get(device_id, fallback)
            return self.switches.setdefault(name, SimulatedSwitch(name))

        for action in configuration_plan.actions:
            kind = action.action_type.value
            if (
                foundation_action_ids is not None
                and kind in {"create_vlan", "configure_trunk"}
                and action.id not in foundation_action_ids
            ):
                continue
            if kind == "create_vlan":
                switch(action.device_id, action.device_name).vlans.add(action.vlan_id)
            elif kind == "configure_access_port":
                owner = switch(action.device_id, action.device_name)
                owner.access[action.interface] = action.data_vlan_id
            elif kind == "configure_trunk":
                trunk_rows.setdefault(action.source_link_id, []).append(action)
        for link_id, pair in trunk_rows.items():
            if len(pair) != 2:
                continue
            left, right = pair
            allowed = frozenset(left.allowed_vlans) & frozenset(right.allowed_vlans)
            for this, other in ((left, right), (right, left)):
                owner = switch(this.device_id, this.device_name)
                owner.trunks[this.interface] = TrunkEnd(
                    interface=this.interface,
                    peer=deployed_names.get(other.device_id, other.device_name),
                    peer_interface=other.interface,
                    link_id=link_id,
                    allowed=allowed,
                )

    def stp_states(self, vlan: int) -> dict[tuple[str, str], str]:
        """Return the simulated port state of every trunk end in one VLAN."""
        members = sorted(
            name for name, item in self.switches.items() if vlan in item.vlans
        )
        member_set = set(members)
        adjacency: dict[str, list[TrunkEnd]] = {name: [] for name in members}
        for name in members:
            for end in sorted(
                self.switches[name].trunks.values(), key=lambda item: item.interface
            ):
                if (
                    vlan in end.allowed
                    and end.peer in member_set
                    and end.link_id not in self.down_links
                ):
                    adjacency[name].append(end)
        depth: dict[str, int] = {}
        tree: set[str] = set()
        for root in members:
            if root in depth:
                continue
            depth[root] = 0
            queue = deque([root])
            while queue:
                current = queue.popleft()
                for end in adjacency[current]:
                    if end.peer not in depth:
                        depth[end.peer] = depth[current] + 1
                        tree.add(end.link_id)
                        queue.append(end.peer)
        states: dict[tuple[str, str], str] = {}
        for name in members:
            for end in adjacency[name]:
                if end.link_id in tree:
                    states[(name, end.interface)] = "FWD"
                    continue
                # A redundant link forwards on the end nearer the root and
                # blocks on the other; ties go to the smaller switch name.
                mine = (depth.get(name, 0), name)
                theirs = (depth.get(end.peer, 0), end.peer)
                states[(name, end.interface)] = "FWD" if mine < theirs else "BLK"
        return states


class CampusTerminal(ColdHttpTerminal):
    """The shared timed terminal, answering for every switch of a campus."""

    def __init__(
        self,
        tmp_path: Path,
        inventory: list,
        clock: FakeClock,
        network: CampusNetwork,
    ) -> None:
        """Bind the terminal to the network the compiled plan describes."""
        super().__init__(tmp_path, inventory, clock)
        self.network = network
        #: Seconds, from the first readiness read of a switch, before its
        #: access ports forward; `math.inf` never. Missing switches: 0.
        self.access_forwarding_after: dict[str, float] = {}
        #: Seconds, from the first trunk-table read of any switch, before any
        #: trunk forwards; `math.inf` never.
        self.trunk_forwarding_after = 0.0
        #: Switches whose terminal answers with an unattributable owner.
        self.unreadable: set[str] = set()
        self.commands: dict[str, str] = {}
        self.ios_reads: dict[str, int] = {}

    # -- answers ------------------------------------------------------------------

    def send_and_wait(self, script: str, timeout: float) -> str | None:
        """Answer IOS, access-port and readiness reads for any switch."""
        kind = self._kind(script)
        if kind not in {"ios_state", "access_port", "readiness"}:
            return super().send_and_wait(script, timeout)
        if not self._dispatched(script, kind, timeout):
            return None
        device = _json_argument(script, _DEVICE)
        if kind == "ios_state":
            if self._since_first("ios_state") < self.ios_ready_after:
                return json.dumps(
                    {"found": True, "booting": True, "terminal": False, "prompt": ""}
                )
            prompt = f"{device}#"
            return json.dumps(
                {
                    "found": True,
                    "booting": False,
                    "terminal": True,
                    "terminal_available": True,
                    "terminal_kind": "ios_command_line",
                    "prompt": prompt,
                    "output": prompt,
                }
            )
        if kind == "access_port":
            interface = _json_argument(script, r"getPort\((\"(?:\\.|[^\"\\])*\")\)")
            owner = self.network.switches.get(device)
            vlan = owner.access.get(interface) if owner else None
            return json.dumps(
                {
                    "device_found": owner is not None,
                    "port_found": vlan is not None,
                    "complete": True,
                    "owner_device_name": device,
                    "interface": interface,
                    "admin_op_mode": 3,
                    "access_vlan": vlan if vlan is not None else 1,
                }
            )
        if "enterCommand" in script and "expected_prompt" in script:
            command = _json_argument(script, _COMMAND)
            self.commands[device] = command
            prompt = f"{device}#"
            return json.dumps({"ok": True, "before": prompt, "expected_prompt": prompt})
        return self._output(device)

    def _output(self, device: str) -> str:
        command = self.commands.get(device, "")
        self.ios_reads[device] = self.ios_reads.get(device, 0) + 1
        self.events.append(f"ios_read:{device}:{command}")
        if command == "show interfaces trunk":
            table = self._trunk_table(device)
        else:
            table = self._spanning_tree(device)
        prompt = f"{device}#"
        attributable = device not in self.unreadable
        return json.dumps(
            {
                "found": True,
                "configuration_channel": True,
                "output": "\n".join([f"{prompt}{command}", table, prompt]),
                "owner_name": device,
                "owner_evidence": "terminal_object_identity",
                "owner_candidates": 1 if attributable else 2,
                "owner_candidate_evidence": "terminal_object_identity",
                "owner_candidate_names": [device] if attributable else [device, "?"],
                "device_count": len(self.inventory),
            }
        )

    # -- simulated pages -----------------------------------------------------------

    def _access_forwarding(self, device: str) -> bool:
        after = self.access_forwarding_after.get(device, 0.0)
        return self._since_first(f"stp:{device}") >= after

    def _trunks_forwarding(self) -> bool:
        return self._since_first("trunk_table") >= self.trunk_forwarding_after

    def _spanning_tree(self, device: str) -> str:
        owner = self.network.switches.get(device)
        if owner is None:
            return ""
        forwarding = self._access_forwarding(device)
        blocks: list[str] = []
        for vlan in sorted(owner.vlans):
            states = self.network.stp_states(vlan)
            rows = []
            for interface, access_vlan in sorted(owner.access.items()):
                if access_vlan != vlan:
                    continue
                state = (
                    "FWD"
                    if forwarding
                    and (device, interface) not in self.network.blocked_access
                    else "LIS"
                )
                rows.append(
                    f"{_short(interface):<16} Desg {state:<3} 19        128.1    P2p"
                )
            for interface in sorted(owner.trunks):
                state = states.get((device, interface))
                if state is None:
                    continue
                role = "Desg" if state == "FWD" else "Altn"
                rows.append(
                    f"{_short(interface):<16} {role} {state:<3} 4         128.25   P2p"
                )
            blocks.extend(
                [
                    f"VLAN{vlan:04d}",
                    "  Spanning tree enabled protocol ieee",
                    f"  Root ID    Priority    {32768 + vlan}",
                    "             Address     0001.4392.0108",
                    "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
                    "",
                    f"  Bridge ID  Priority    {32768 + vlan}  (priority 32768 sys-id-ext {vlan})",
                    "             Address     0030.A3A1.89E8",
                    "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
                    "             Aging Time  20",
                    "",
                    "Interface        Role Sts Cost      Prio.Nbr Type",
                    "---------------- ---- --- --------- -------- ----------------------",
                    *rows,
                    "",
                ]
            )
        return "\n".join(blocks)

    def _trunk_table(self, device: str) -> str:
        owner = self.network.switches.get(device)
        if owner is None:
            return ""
        forwarding = self._trunks_forwarding()
        ends = [
            end
            for _, end in sorted(owner.trunks.items())
            if end.link_id not in self.network.down_links
        ]
        states = {vlan: self.network.stp_states(vlan) for vlan in sorted(owner.vlans)}
        lines = ["Port        Mode         Encapsulation  Status        Native vlan"]
        lines += [
            f"{_short(end.interface, trunk_table=True):<11} on           802.1q"
            "         trunking      1"
            for end in ends
        ]
        lines += ["", "Port        Vlans allowed on trunk"]
        lines += [
            f"{_short(end.interface, trunk_table=True):<11} {_vlan_list(end.allowed)}"
            for end in ends
        ]
        lines += ["", "Port        Vlans allowed and active in management domain"]
        lines += [
            f"{_short(end.interface, trunk_table=True):<11} "
            f"{_vlan_list(end.allowed & owner.vlans)}"
            for end in ends
        ]
        lines += [
            "",
            "Port        Vlans in spanning tree forwarding state and not pruned",
        ]
        lines += [
            f"{_short(end.interface, trunk_table=True):<11} "
            + _vlan_list(
                {
                    vlan
                    for vlan in end.allowed & owner.vlans
                    if forwarding
                    and states.get(vlan, {}).get((device, end.interface)) == "FWD"
                }
            )
            for end in ends
        ]
        return "\n".join(lines)


NEVER = math.inf


# -- the plans the product compiles for one campus -----------------------------------


@dataclass
class CampusPlans:
    """One campus deployment as the real planner, compiler and manifest see it."""

    payload: dict[str, Any]
    intent_json: str
    manifest: Any
    inventory: list
    configuration_plan: Any
    service_plan: Any
    deployed_names: dict[str, str]
    device_count: int
    link_count: int


def campus_payload(
    clients: int,
    *,
    marker: str = "COLD_HTTP_0f1e2d3c4b5a69788796a5b4c3d2e1f0",
    server_segment_role: str = "data",
    sites: int = 1,
    address_space: str = "",
) -> dict[str, Any]:
    """Return an HTTP-by-IP intent for `clients` static PCs over `sites` sites.

    Each site has its own Server-PT and its own HTTP service, and its share of
    the clients, so every client-to-server path stays inside one site: the
    planner's access capacity per site is what bounds a site, not this
    fixture. The first site keeps the maintained single-site fixture names.
    """
    from service_entry_fixture import intent_payload

    base = intent_payload()
    template = base["sites"][0]
    service = dict(
        next(item for item in template["services"] if item["service_type"] == "http"),
        http_content=marker,
    )
    template["endpoints"][1]["segment_role"] = server_segment_role
    shares = [
        clients // sites + (1 if index < clients % sites else 0)
        for index in range(sites)
    ]
    built = []
    for index, share in enumerate(shares):
        site = json.loads(json.dumps(template))
        site["endpoints"][0]["count"] = share
        if index == 0:
            site["services"] = [service]
        else:
            site["name"] = f"BR{index:02d}"
            site["type"] = "branch"
            site["services"] = [
                dict(
                    service,
                    name=f"lab-web-{index:02d}",
                    hostname=f"www{index}.lab.example",
                )
            ]
        built.append(site)
    base["sites"] = built
    if address_space:
        base["address_space"] = address_space
    elif sites > 1 or clients > 400:
        base["address_space"] = "10.0.0.0/16"
    return base


def compose_campus(payload: dict[str, Any]) -> CampusPlans:
    """Compose, compile and bind one campus exactly as the product will."""
    from service_entry_fixture import (
        BACKEND_VERSION,
        DEPLOYMENT_ID,
        FINGERPRINT,
        deployed_topology,
    )

    from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
        compose_enterprise_reference,
    )
    from packet_tracer_mcp.domain.enterprise.models.deployment import (
        build_deployment_manifest,
    )
    from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent

    topology, inventory = deployed_topology(payload)
    manifest = build_deployment_manifest(
        topology,
        inventory,
        fingerprint=FINGERPRINT.model_copy(
            update={"bridge_transport": "file", "runtime_mode": "logical-workspace"}
        ),
        deployment_id=DEPLOYMENT_ID,
    )
    intent_json = json.dumps(payload)
    composition = compose_enterprise_reference(
        EnterpriseIntent.model_validate_json(intent_json),
        packet_tracer_version=BACKEND_VERSION,
        deployment_manifest=manifest,
        services=True,
    )
    assert composition.configuration is not None, composition.issues
    return CampusPlans(
        payload=payload,
        intent_json=intent_json,
        manifest=manifest,
        inventory=inventory,
        configuration_plan=composition.configuration,
        service_plan=composition.services,
        deployed_names={item.id: item.name for item in topology.devices},
        device_count=len(topology.devices),
        link_count=len(topology.links),
    )


def campus_terminal(
    tmp_path: Path,
    plans: CampusPlans,
    clock: FakeClock,
    foundation_action_ids: set[str] | None = None,
) -> CampusTerminal:
    """Return a simulated terminal for exactly this campus."""
    return CampusTerminal(
        tmp_path,
        plans.inventory,
        clock,
        CampusNetwork(
            plans.configuration_plan,
            plans.deployed_names,
            foundation_action_ids=foundation_action_ids,
        ),
    )


def run_public_campus(
    tmp_path: Path,
    monkeypatch: Any,
    plans: CampusPlans,
    *,
    configure=None,
    clock: FakeClock | None = None,
) -> tuple[dict[str, Any], CampusTerminal]:
    """Run the public MCP tool over the simulated campus; return its JSON result.

    Only what lies beyond the bridge is simulated, plus the stores' locations
    and the import-isolation answer a test process cannot give. The tool, its
    shared session composition, the product use case, both runtimes and the
    readiness gate are the production ones.
    """
    import asyncio

    from mcp.server.fastmcp import FastMCP
    from service_entry_fixture import DEPLOYMENT_ID, IsolationPreflight

    from packet_tracer_mcp.adapters.mcp import service_tools
    from packet_tracer_mcp.infrastructure.execution.product_channel import (
        FixedChannelProductTransport,
    )
    from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
        ServiceRunRecordStore,
    )

    clock = clock or FakeClock()
    terminal = campus_terminal(tmp_path, plans, clock)
    if configure is not None:
        configure(terminal)

    class Manifests:
        def latest_by_deployment_id(self, deployment_id):
            return plans.manifest if deployment_id == DEPLOYMENT_ID else None

    store_root = tmp_path / "services"
    monkeypatch.setattr(service_tools, "DeploymentManifestStore", Manifests)
    monkeypatch.setattr(
        service_tools,
        "ServiceRunRecordStore",
        lambda *args, **kwargs: ServiceRunRecordStore(store_root),
    )
    monkeypatch.setattr(
        service_tools, "ImportIsolationPreflight", lambda _root: IsolationPreflight()
    )
    fixed = FixedChannelProductTransport("file", terminal)
    mcp = FastMCP("campus")
    service_tools.register_service_tools(
        mcp,
        send_and_wait=fixed.send_and_wait,
        dispatch_and_wait=fixed.dispatch_and_wait,
        send_payload=fixed.send_payload,
        query_inventory=fixed.query_inventory,
        pick_channel=lambda: "file",
        observe_environment=fixed.observe_environment,
    )
    rendered = asyncio.run(
        mcp.call_tool(
            "pt_apply_enterprise_services",
            {
                "intent_json": plans.intent_json,
                "deployment_id": DEPLOYMENT_ID,
                "packet_tracer_version": plans.manifest.backend_version,
                "run_label": "",
            },
        )
    )
    return json.loads(rendered[0][0].text), terminal
