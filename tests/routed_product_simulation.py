"""SIMULATED Packet Tracer for an SP-1 routed campus, driven by the real plans.

Nothing here is Packet Tracer. It extends the campus simulation with routers:
their interfaces and static routes are parsed from the exact
`configureIosDevice` payloads the production E5 runtime sends, and their
`show ip interface brief` / `show ip route` answers are rendered from that
state. PCs and servers keep the addresses, gateways and resolvers the product
configured through `configurePcIp`.

The oracle for a request is independent of the product's readiness decision:
an HTTP page or a DNS answer is delivered only if, at that moment, the
simulated tables forward the request AND its reply hop by hop. Knobs break one
fact at a time: an interface down, a withheld route, a wrong next hop, routes
that install only after a delay.
"""

from __future__ import annotations

import ipaddress
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from campus_product_simulation import (
    CampusNetwork,
    CampusPlans,
    CampusTerminal,
    TrunkEnd,
    _json_argument,
)
from cold_http_acceptance_harness import FakeClock

_DEVICE = r"getDevice\((\"(?:\\.|[^\"\\])*\")\)"
_IOS_CALL = re.compile(
    r"configureIosDevice\((\"(?:\\.|[^\"\\])*\"),(\"(?:\\.|[^\"\\])*\")\)"
)
_URL = re.compile(r"\"(https?://[^\"/]+)/\"")
_HTTP_KEY = re.compile(r"__mcpE6HttpClients\[(\"(?:\\.|[^\"\\])*\")\]")
_LEGEND = (
    "Codes: L - local, C - connected, S - static, R - RIP, M - mobile, B - BGP\n"
    "       D - EIGRP, EX - EIGRP external, O - OSPF, IA - OSPF inter area\n"
    "       N1 - OSPF NSSA external type 1, N2 - OSPF NSSA external type 2\n"
    "       E1 - OSPF external type 1, E2 - OSPF external type 2, E - EGP\n"
    "       i - IS-IS, L1 - IS-IS level-1, L2 - IS-IS level-2, ia - IS-IS inter area\n"
    "       * - candidate default, U - per-user static route, o - ODR\n"
    "       P - periodic downloaded static route\n"
)


class RoutedCampusNetwork(CampusNetwork):
    """A campus whose switch ports toward routers forward the trunked VLANs."""

    def __init__(self, configuration_plan: Any, deployed_names: dict[str, str]):
        """Add the single-ended (router-facing) trunks the pairing skips."""
        super().__init__(configuration_plan, deployed_names)
        ends: dict[str, list[Any]] = {}
        for action in configuration_plan.actions:
            if action.action_type.value == "configure_trunk":
                ends.setdefault(action.source_link_id, []).append(action)
        self.edge_trunks: set[tuple[str, str]] = set()
        for link_id, pair in ends.items():
            if len(pair) != 1:
                continue
            action = pair[0]
            name = deployed_names.get(action.device_id, action.device_name)
            owner = self.switches[name]
            owner.trunks[action.interface] = TrunkEnd(
                interface=action.interface,
                peer=deployed_names.get(action.peer_device_id, action.peer_device_id),
                peer_interface="",
                link_id=link_id,
                allowed=frozenset(action.allowed_vlans),
            )
            self.edge_trunks.add((name, action.interface))

    def stp_states(self, vlan: int) -> dict[tuple[str, str], str]:
        """Router-facing trunks forward every allowed VLAN (routers run no STP)."""
        states = super().stp_states(vlan)
        for name, interface in self.edge_trunks:
            end = self.switches[name].trunks[interface]
            if vlan in end.allowed and end.link_id not in self.down_links:
                states[(name, interface)] = "FWD"
        return states


@dataclass
class Router:
    """One simulated router: addressed interfaces and configured routes."""

    name: str
    interfaces: dict[str, tuple[str, str]] = field(default_factory=dict)
    routes: list[tuple[ipaddress.IPv4Network, str]] = field(default_factory=list)


class RoutedCampusTerminal(CampusTerminal):
    """The campus terminal plus routers, bindings, DNS and routed HTTP."""

    def __init__(
        self,
        tmp_path: Path,
        plans: CampusPlans,
        clock: FakeClock,
        *,
        dns_server: str,
        records: dict[str, str],
    ) -> None:
        """Bind to the compiled campus; routers start unconfigured."""
        network = RoutedCampusNetwork(plans.configuration_plan, plans.deployed_names)
        super().__init__(tmp_path, plans.inventory, clock, network)
        self.routers: dict[str, Router] = {
            item.device_name: Router(item.device_name)
            for item in plans.inventory
            if item.model in {"1941", "2911", "1841", "2811", "2901", "4331"}
        }
        self.bindings: dict[str, dict[str, str]] = {}
        self.dns_server = dns_server
        self.records = {key.casefold(): value for key, value in records.items()}
        #: Knobs, each breaking exactly one simulated fact.
        self.down_interfaces: set[tuple[str, str]] = set()
        self.withheld_routes: set[tuple[str, str]] = set()
        self.wrong_next_hops: dict[tuple[str, str], str] = {}
        #: Wall-clock seconds after the first faulted read before routes
        #: install; the production runtimes wait on the real clock.
        self.routes_install_after = 0.0
        self._faulted_since: float | None = None
        #: When True (the default) the knobs act only once E6 has applied its
        #: services, i.e. after E5 read-back and before readiness, so they
        #: test readiness rather than E5. False applies them from the start.
        self.faults_after_service_apply = True
        #: Evidence the tests read.
        self.requests: list[tuple[float, str, str, str, bool]] = []
        self.router_reads: dict[str, int] = {}
        self.fetches: dict[str, tuple[str, str]] = {}

    # -- E5 effects --------------------------------------------------------------

    def send(self, script: str) -> bool:
        """Apply router IOS payloads and full endpoint bindings, then accept."""
        for device_json, payload_json in _IOS_CALL.findall(script):
            device = json.loads(device_json)
            if device in self.routers:
                self._apply_ios(self.routers[device], json.loads(payload_json))
        for arguments in re.findall(r"configurePcIp\((.*?)\);", script):
            values = json.loads("[" + arguments + "]")
            if values[1] is False:
                self.bindings[str(values[0])] = {
                    "ip": str(values[2]),
                    "mask": str(values[3]),
                    "gateway": str(values[4]),
                    "dns": str(values[5]),
                }
        return super().send(script)

    @staticmethod
    def _apply_ios(router: Router, payload: str) -> None:
        current = ""
        for raw in payload.splitlines():
            line = raw.strip()
            if line.startswith("interface "):
                current = line.split(" ", 1)[1]
            elif line.startswith("ip address ") and current:
                _, _, address, mask = line.split()
                router.interfaces[current] = (address, mask)
            elif line.startswith("ip route "):
                _, _, network, mask, next_hop = line.split()
                router.routes.append(
                    (ipaddress.ip_network(f"{network}/{mask}"), next_hop)
                )
            elif line in {"exit", "end"}:
                current = ""

    # -- routing state -----------------------------------------------------------

    def _faults_on(self) -> bool:
        return not self.faults_after_service_apply or "service_apply" in self.events

    def _up(self, router: Router, interface: str) -> bool:
        if not self._faults_on():
            return True
        parent = interface.split(".", 1)[0]
        return (router.name, interface) not in self.down_interfaces and (
            router.name,
            parent,
        ) not in self.down_interfaces

    def _connected(self, router: Router):
        for name, (address, mask) in sorted(router.interfaces.items()):
            if self._up(router, name):
                yield name, ipaddress.ip_interface(f"{address}/{mask}")

    def _installed(self, router: Router) -> list[tuple[ipaddress.IPv4Network, str]]:
        faults = self._faults_on()
        if faults:
            if self._faulted_since is None:
                self._faulted_since = time.monotonic()
            if time.monotonic() - self._faulted_since < self.routes_install_after:
                return []
        connected = [item.network for _, item in self._connected(router)]
        installed = []
        for network, next_hop in router.routes:
            key = (router.name, str(network.network_address))
            if faults and key in self.withheld_routes:
                continue
            hop = self.wrong_next_hops.get(key, next_hop) if faults else next_hop
            if any(ipaddress.ip_address(hop) in item for item in connected):
                installed.append((network, hop))
        return installed

    def _owner_of(self, address: str) -> Router | None:
        for router in self.routers.values():
            for _name, value in self._connected(router):
                if str(value.ip) == address:
                    return router
        return None

    def _host_ips(self) -> set[str]:
        return {item["ip"] for item in self.bindings.values()}

    def _forwards(self, source: str, destination: str) -> bool:
        """Whether one packet from `source` reaches `destination` now."""
        host = next(
            (item for item in self.bindings.values() if item["ip"] == source), None
        )
        if host is None:
            return False
        own = ipaddress.ip_interface(f"{host['ip']}/{host['mask']}")
        target = ipaddress.ip_address(destination)
        if target in own.network:
            return destination in self._host_ips()
        router = self._owner_of(host["gateway"])
        seen: set[str] = set()
        while router is not None and router.name not in seen:
            seen.add(router.name)
            for _, value in self._connected(router):
                if target in value.network:
                    return destination in self._host_ips()
            matches = [item for item in self._installed(router) if target in item[0]]
            if not matches:
                return False
            longest = max(item[0].prefixlen for item in matches)
            hops = {hop for network, hop in matches if network.prefixlen == longest}
            if len(hops) != 1:
                return False
            router = self._owner_of(next(iter(hops)))
        return False

    def reachable(self, source: str, destination: str) -> bool:
        """Whether a request and its reply both travel now (the oracle)."""
        return self._forwards(source, destination) and self._forwards(
            destination, source
        )

    # -- IOS reads ---------------------------------------------------------------

    def _output(self, device: str) -> str:
        router = self.routers.get(device)
        if router is None:
            return super()._output(device)
        command = self.commands.get(device, "")
        self.ios_reads[device] = self.ios_reads.get(device, 0) + 1
        self.router_reads[device] = self.router_reads.get(device, 0) + 1
        self.events.append(f"ios_read:{device}:{command}")
        if command == "show ip interface brief":
            table = self._brief(router)
        elif command == "show ip route":
            table = self._route_table(router)
        else:
            table = ""
        prompt = f"{device}#"
        return json.dumps(
            {
                "found": True,
                "configuration_channel": True,
                "output": "\n".join([f"{prompt}{command}", table, prompt]),
                "owner_name": device,
                "owner_evidence": "terminal_object_identity",
                "owner_candidates": 1,
                "owner_candidate_evidence": "terminal_object_identity",
                "owner_candidate_names": [device],
                "device_count": len(self.inventory),
            }
        )

    def _brief(self, router: Router) -> str:
        lines = [
            "Interface              IP-Address      OK? Method Status"
            "                Protocol"
        ]
        for name, (address, _mask) in sorted(router.interfaces.items()):
            state = (
                "up                    up"
                if self._up(router, name)
                else ("up                    down")
            )
            lines.append(f"{name:<22} {address:<15} YES manual {state}")
        return "\n".join(lines)

    def _route_table(self, router: Router) -> str:
        rows = []
        for name, value in self._connected(router):
            rows.append(
                (
                    value.network,
                    f"C       {value.network} is directly connected, {name}",
                )
            )
            rows.append(
                (
                    ipaddress.ip_network(f"{value.ip}/32"),
                    f"L       {value.ip}/32 is directly connected, {name}",
                )
            )
        for network, hop in self._installed(router):
            rows.append((network, f"S       {network} [1/0] via {hop}"))
        body = "\n".join(line for _, line in sorted(rows, key=lambda item: item[0]))
        return (
            _LEGEND
            + "\nGateway of last resort is not set\n\n"
            + f"     10.0.0.0/8 is variably subnetted, {len(rows)} subnets, 3 masks\n"
            + body
        )

    # -- E6 reads ----------------------------------------------------------------

    def _service_response(self, script: str) -> str:
        if "api:api,value:v" in script:
            device = _json_argument(script, _DEVICE)
            binding = self.bindings.get(device)
            process = "HostIp" if '"HostIp"' in script else "DnsClient"
            value = ""
            if binding is not None:
                value = binding["gateway"] if process == "HostIp" else binding["dns"]
            return json.dumps(
                {
                    "found": binding is not None,
                    "process": binding is not None,
                    "api": binding is not None,
                    "value": value,
                }
            )
        if "content_before:before" in script:
            key = json.loads(_HTTP_KEY.search(script).group(1))
            url = _URL.search(script)
            client = _json_argument(script, _DEVICE)
            host = url.group(1).split("://", 1)[1] if url else ""
            self.fetches[key] = (client, host)
        if "var bag=this.__mcpE6HttpClients" in script and "var found=" not in script:
            key = (
                json.loads(_HTTP_KEY.search(script).group(1))
                if _HTTP_KEY.search(script)
                else ""
            )
            match = re.search(r"var slot=bag\[(\"(?:\\.|[^\"\\])*\")\]", script)
            if match:
                key = json.loads(match.group(1))
            client, host = self.fetches.get(key, ("", ""))
            delivered = self._http_delivered(client, host)
            self.requests.append((self.clock(), "http", client, host, delivered))
            if not delivered:
                return json.dumps({"found": True, "content": ""})
        if "var started=false;var blocked=false" in script:
            return super()._service_response(script)
        if "var cp=d&&typeof d.getCommandPrompt" in script:
            return self._dns_window(_json_argument(script, _DEVICE))
        return super()._service_response(script)

    def _resolve(self, client: str, name: str) -> str:
        binding = self.bindings.get(client)
        if binding is None or binding["dns"] != self.dns_server:
            return ""
        if not self.reachable(binding["ip"], self.dns_server):
            return ""
        return self.records.get(name.casefold(), "")

    def _http_delivered(self, client: str, host: str) -> bool:
        binding = self.bindings.get(client)
        if binding is None or not host:
            return False
        try:
            target = str(ipaddress.ip_address(host))
        except ValueError:
            target = self._resolve(client, host)
        return bool(target) and self.reachable(binding["ip"], target)

    def _dns_window(self, client: str) -> str:
        command = self.last_dns_command
        name = command.removeprefix("ping ")
        address = self._resolve(client, name)
        binding = self.bindings.get(client, {})
        self.requests.append((self.clock(), "dns", client, name, bool(address)))
        if not address:
            output = (
                f"C:\\>{command}\n"
                f"Ping request could not find host {name}. Please check the name "
                "and try again.\nC:\\>"
            )
        else:
            received = 4 if self.reachable(binding.get("ip", ""), address) else 0
            output = (
                f"C:\\>{command}\nPinging {address} with 32 bytes of data:\n"
                f"Packets: Sent = 4, Received = {received}, Lost = {4 - received}"
            )
        return json.dumps({"found": True, "output": output})


def run_public_routed(
    tmp_path: Path,
    monkeypatch: Any,
    plans: CampusPlans,
    *,
    dns_server: str,
    records: dict[str, str],
    configure=None,
    clock: FakeClock | None = None,
    device_candidates: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], RoutedCampusTerminal]:
    """Run the registered MCP tool over the simulated routed campus.

    The tool, its session composition, the use case, both runtimes, the
    readiness gate and the record store are production code. Only what lies
    beyond the bridge is simulated, plus the store locations, the import
    isolation answer a test process cannot give, and - when
    `device_candidates` is given - the device capability catalog, which is
    replaced by the production candidate adapter with exactly those
    capabilities named as unverified candidates.
    """
    import asyncio
    import importlib

    from mcp.server.fastmcp import FastMCP
    from service_entry_fixture import DEPLOYMENT_ID, IsolationPreflight

    from packet_tracer_mcp.adapters.mcp import service_tools
    from packet_tracer_mcp.infrastructure.catalog.enterprise_capabilities import (
        candidate_capability_adapter,
    )
    from packet_tracer_mcp.infrastructure.execution.product_channel import (
        FixedChannelProductTransport,
    )
    from packet_tracer_mcp.infrastructure.persistence.service_run_record_store import (
        ServiceRunRecordStore,
    )

    composition_module = importlib.import_module(
        "packet_tracer_mcp.application.use_cases.compose_enterprise_reference"
    )
    clock = clock or FakeClock()
    terminal = RoutedCampusTerminal(
        tmp_path, plans, clock, dns_server=dns_server, records=records
    )
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
    if device_candidates is not None:
        monkeypatch.setattr(
            composition_module,
            "capability_catalog_for",
            lambda version, **_kwargs: candidate_capability_adapter(
                version, device_candidates, label="sp1-simulation"
            ),
        )
    fixed = FixedChannelProductTransport("file", terminal)
    mcp = FastMCP("routed-campus")
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


def routed_campus_plans(payload: dict[str, Any]) -> CampusPlans:
    """Compose one routed campus exactly as the product will, on the file channel."""
    from service_entry_fixture import BACKEND_VERSION, DEPLOYMENT_ID, FINGERPRINT
    from sp1_routed_fixture import deployed

    from packet_tracer_mcp.application.use_cases.compose_enterprise_reference import (
        compose_enterprise_reference,
    )
    from packet_tracer_mcp.domain.enterprise.models.deployment import (
        build_deployment_manifest,
    )
    from packet_tracer_mcp.domain.enterprise.models.intent import EnterpriseIntent

    topology, inventory = deployed(payload)
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
