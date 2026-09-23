"""A deterministic Packet Tracer terminal for the real product composition.

The product route is exercised with everything real except what lies beyond
the bridge: this module answers the exact scripts the production runtimes
dispatch, the way the measured engine answers them, and records what it was
asked. It is shared by the public-route tests and the cold-HTTP acceptance
tests so both drive one controlled terminal rather than two diverging ones.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from service_entry_fixture import BACKEND_VERSION

from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)


def run_environment_javascript(
    script: str,
    *,
    application_version: str = BACKEND_VERSION,
    saved_file_version: str = BACKEND_VERSION,
    active_file: bool = True,
    application_getter: bool = True,
    application_raises: bool = False,
) -> str:
    """Execute the registry's exact observation source against a Node stub."""
    app_getter = ""
    if application_getter:
        app_getter = (
            "getVersion:function(){throw new Error('version unavailable');},"
            if application_raises
            else "getVersion:function(){return "
            + json.dumps(application_version)
            + ";},"
        )
    active = (
        "null"
        if not active_file
        else "{getVersion:function(){return " + json.dumps(saved_file_version) + ";}}"
    )
    harness = (
        "var reported='';"
        "var app={" + app_getter + "getActiveFile:function(){return " + active + ";}};"
        "global.ipc={appWindow:function(){return app;}};"
        "global.reportResult=function(value){reported=String(value);};"
        + script
        + ";process.stdout.write(reported);"
    )
    completed = subprocess.run(
        [shutil.which("node"), "-e", harness],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout


#: The access ports the compiled plan puts on VLAN 10 of the fixture switch.
#: The readiness gate asks about exactly these, so the simulated switch has to
#: answer about exactly these; a simulation that reported a different set would
#: be proving the gate wrong rather than proving the route.
SIMULATED_ACCESS_PORTS = ("FastEthernet1/1", "FastEthernet1/2", "FastEthernet1/3")
SIMULATED_SWITCH_PROMPT = "HQ-DEFAULT-ACCESS-SW-01#"


def simulated_spanning_tree_output(state: str = "FWD") -> str:
    """Render one complete `show spanning-tree` page for the fixture switch.

    The layout is the exact one `parse_show_spanning_tree` was written against,
    Root ID and Bridge ID blocks included: a page missing either is skipped by
    the parser, which the gate would then correctly report as an absent VLAN
    instance rather than as a forwarding refusal.
    """
    rows = [
        f"{port.replace('FastEthernet', 'Fa'):<16} Desg {state:<3} "
        "19        128.1    P2p"
        for port in SIMULATED_ACCESS_PORTS
    ]
    return "\n".join(
        [
            f"{SIMULATED_SWITCH_PROMPT}show spanning-tree",
            "VLAN0010",
            "  Spanning tree enabled protocol ieee",
            "  Root ID    Priority    32778",
            "             Address     0001.4392.0108",
            "             This bridge is the root",
            "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
            "",
            "  Bridge ID  Priority    32778  (priority 32768 sys-id-ext 10)",
            "             Address     0030.A3A1.89E8",
            "             Hello Time  2 sec  Max Age 20 sec  Forward Delay 15 sec",
            "             Aging Time  20",
            "",
            "Interface        Role Sts Cost      Prio.Nbr Type",
            "---------------- ---- --- --------- -------- ----------------------",
            *rows,
            SIMULATED_SWITCH_PROMPT,
        ]
    )


class SimulatedProductTransport:
    """Deterministic external bridge answers for the real product wiring."""

    def __init__(
        self,
        tmp_path: Path,
        inventory: list,
        *,
        application_version: str = BACKEND_VERSION,
        saved_file_version: str = "8.2.2.0400",
    ) -> None:
        """Bind the terminal to one deployed inventory and its answers."""
        self.dir = tmp_path / "mailbox"
        self.inventory = {item.device_name: item for item in inventory}
        self.application_version = application_version
        self.saved_file_version = saved_file_version
        self.inventory_requests: list[tuple[str, ...]] = []
        self.send_payloads: list[str] = []
        self.dispatch_payloads: list[str] = []
        self.addresses: dict[str, tuple[str, str]] = {}
        self.last_dns_command = ""
        self.page_content = "STALE_WEB_PAGE"
        self.events: list[str] = []
        #: Which spanning-tree state the simulated switch reports. Tests that
        #: say nothing get a forwarding switch, which is the state the public
        #: route needs; a test that wants the gate to refuse sets this.
        self.spanning_tree_state = "FWD"
        self.spanning_tree_queries: list[str] = []
        self.unhandled: list[str] = []

    def pt_alive(self) -> bool:
        """Report a fresh heartbeat."""
        return True

    def send(self, script: str) -> bool:
        """Accept one fire-and-forget payload and apply what it addresses."""
        self.send_payloads.append(script)
        self.events.append("e5_apply")
        for arguments in re.findall(r"configurePcIp\((.*?)\);", script):
            values = json.loads("[" + arguments + "]")
            if values[1] is False:
                self.addresses[str(values[0])] = (str(values[2]), str(values[3]))
        return True

    def send_and_wait(self, script: str, timeout: float) -> str:
        """Answer one waited read the way the measured engine does."""
        del timeout
        if "application_version_unavailable" in script:
            self.events.append("environment")
            return run_environment_javascript(
                script,
                application_version=self.application_version,
                saved_file_version=self.saved_file_version,
            )
        inventory_match = re.search(r"var names=(\[.*?\]),wanted=", script)
        if inventory_match:
            names = tuple(json.loads(inventory_match.group(1)))
            self.inventory_requests.append(names)
            self.events.append("inventory")
            devices = []
            for name in names:
                target = self.inventory.get(name)
                if target is None:
                    continue
                ipv4, mask = self.addresses.get(name, ("", ""))
                devices.append(
                    {
                        "name": name,
                        "model": target.model,
                        "ports": [
                            {
                                "name": interface,
                                "ip": ipv4,
                                "mask": mask,
                                "up": True,
                                "linked": True,
                            }
                            for interface in target.interfaces
                        ],
                    }
                )
            return json.dumps({"devices": devices, "links": None})
        if "terminal_kind:'ios_command_line'" in script:
            return json.dumps(
                {
                    "found": True,
                    "booting": False,
                    "terminal": True,
                    "terminal_available": True,
                    "terminal_kind": "ios_command_line",
                    "prompt": "Switch#",
                    "output": "Switch#",
                }
            )
        if "getVlanCount" in script:
            return json.dumps(
                {"found": True, "configuration_channel": True, "present": True}
            )
        if "owner_device_name" in script and "getAccessVlan" in script:
            device = self._json_argument(script, r"getDevice\((\"(?:\\.|[^\"\\])*\")\)")
            interface = self._json_argument(
                script,
                r"getPort\((\"(?:\\.|[^\"\\])*\")\)",
            )
            return json.dumps(
                {
                    "device_found": True,
                    "port_found": True,
                    "complete": True,
                    "owner_device_name": device,
                    "interface": interface,
                    "admin_op_mode": 3,
                    "access_vlan": 10,
                }
            )
        if "address_channel:able" in script:
            device = self._json_argument(script, r"getDevice\((\"(?:\\.|[^\"\\])*\")\)")
            interface = self._json_argument(
                script,
                r"var want=(\"(?:\\.|[^\"\\])*\")",
            )
            ipv4, mask = self.addresses.get(device, ("", ""))
            self.events.append(f"e5_readback:{device}")
            return json.dumps(
                {
                    "found": True,
                    "port_found": True,
                    "interface": interface,
                    "address_channel": True,
                    "ipv4": ipv4,
                    "netmask": mask,
                }
            )
        if "getCurrentFrameInstanceIndex" in script:
            # The readiness observation names the simulation clock beside its
            # sample. It is a read of already measured primitives and moves
            # nothing; answering it keeps the sample self-describing.
            return json.dumps(
                {
                    "mode": False,
                    "frames": 0,
                    "sim_time": 118718,
                    "current_index": -1,
                }
            )
        if "enterCommand" in script and "expected_prompt" in script:
            self.spanning_tree_queries.append(
                self._json_argument(script, r"getDevice\((\"(?:\\.|[^\"\\])*\")\)")
            )
            return json.dumps(
                {
                    "ok": True,
                    "before": SIMULATED_SWITCH_PROMPT,
                    "expected_prompt": SIMULATED_SWITCH_PROMPT,
                }
            )
        if "owner_name:owner" in script:
            device = self._json_argument(script, r"getDevice\((\"(?:\\.|[^\"\\])*\")\)")
            self.events.append(f"readiness:{self.spanning_tree_state}")
            return json.dumps(
                {
                    "found": True,
                    "configuration_channel": True,
                    "output": simulated_spanning_tree_output(self.spanning_tree_state),
                    "owner_name": device,
                    "owner_evidence": "terminal_object_identity",
                    "owner_candidates": 1,
                    "owner_candidate_evidence": "terminal_object_identity",
                    "owner_candidate_names": [device],
                    "device_count": len(self.inventory),
                }
            )
        if "configuration_channel:o!==" in script:
            return json.dumps(
                {
                    "found": True,
                    "configuration_channel": True,
                    "output": simulated_spanning_tree_output(self.spanning_tree_state),
                }
            )
        self.unhandled.append(script)
        return "ERROR:unhandled simulated file read"

    def dispatch_and_wait(
        self,
        script: str,
        timeout: float,
    ) -> BridgeDispatchOutcome:
        """Answer one typed dispatch with a correlated body."""
        del timeout
        self.dispatch_payloads.append(script)
        body = self._service_response(script)
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=body,
        )

    def _service_response(self, script: str) -> str:
        if "var results=[]" in script:
            self.events.append("service_apply")
            for path_json, content_json in re.findall(
                r"p\.setPageContents\((\"(?:\\.|[^\"\\])*\"),(\"(?:\\.|[^\"\\])*\")\)",
                script,
            ):
                if json.loads(path_json) == "index.html":
                    self.page_content = str(json.loads(content_json))
                    self.events.append(f"http_content_set:{self.page_content}")
            identifiers = [
                json.loads(item)
                for item in re.findall(
                    r"var r=\{id:(\"(?:\\.|[^\"\\])*\")",
                    script,
                )
            ]
            return json.dumps(
                {
                    "results": [
                        {
                            "id": identifier,
                            "attempted": True,
                            "skip_reason": "",
                            "call_error": "",
                            "call_result": True,
                            "pre_read": True,
                            "post_read": True,
                            "ok": True,
                            "changed": True,
                            "pre": "before",
                            "post": "after",
                        }
                        for identifier in identifiers
                    ]
                }
            )
        if "out.records={}" in script:
            encoded = re.search(r"JSON.parse\((\"(?:\\.|[^\"\\])*\")\)", script)
            records = json.loads(json.loads(encoded.group(1))) if encoded else {}
            return json.dumps({"found": True, "enabled": True, "records": records})
        if "out.content=String(p.getPage" in script:
            self.events.append("http_direct_readback")
            return json.dumps(
                {"found": True, "enabled": True, "content": self.page_content}
            )
        if "var started=false;var blocked=false" in script:
            command = self._json_argument(
                script,
                r"enterCommand\((\"(?:\\.|[^\"\\])*\")\)",
            )
            self.last_dns_command = command
            self.events.append(f"dns_start:{command}")
            return json.dumps({"started": True, "blocked": False, "before": "C:\\>"})
        if "var cp=d&&typeof d.getCommandPrompt" in script:
            hostname = self.last_dns_command.removeprefix("ping ")
            if hostname == "www.lab.example":
                output = (
                    f"C:\\>{self.last_dns_command}\n"
                    "Pinging 198.18.160.2 with 32 bytes of data:\n"
                    "Packets: Sent = 4, Received = 4, Lost = 0"
                )
            else:
                output = (
                    f"C:\\>{self.last_dns_command}\n"
                    f"Ping request could not find host {hostname}.\nC:\\>"
                )
            return json.dumps({"found": True, "output": output})
        if "content_before:before" in script:
            owner = self._json_argument(
                script,
                r"getDevice\((\"(?:\\.|[^\"\\])*\")\)",
            )
            self.events.append(f"http_start:{owner}")
            return json.dumps(
                {
                    "started": True,
                    "go_result": True,
                    "go_result_type": "boolean",
                    "content_before": "",
                    "https_mode": "p.setHttps(true)" in script,
                    "https_mode_type": "boolean",
                    "owner_device": owner,
                    "owner_read": True,
                    "owned": True,
                }
            )
        if "var found=!!(slot&&slot.manager&&slot.client)" in script:
            self.events.append("http_release")
            return json.dumps(
                {"found": True, "deleted": True, "present": False, "error": ""}
            )
        if "var bag=this.__mcpE6HttpClients" in script:
            self.events.append("http_inspect")
            return json.dumps({"found": True, "content": self.page_content})
        self.unhandled.append(script)
        return "ERROR:unhandled simulated service read"

    @staticmethod
    def _json_argument(script: str, pattern: str) -> str:
        match = re.search(pattern, script)
        if match is None:
            raise AssertionError(f"Expected JSON argument was absent: {pattern}")
        return str(json.loads(match.group(1)))
