"""SP-1 terminal binding probe, run as the real generated script under Node.

LIVE at 6e5e527 `getProcess('HostIp')` threw `invalid string position` on
PC-PT, and because one guard covered every getter the resolver read was lost
with it. The stub reproduces that throw: each getter must now answer or fail
on its own, both documented gateway process names are tried and recorded,
and a failure never reads as a value.

Skipped only when Node is missing locally; under `GITHUB_ACTIONS` it fails.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

import pytest

from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.infrastructure.execution.service_qualification_probes import (
    PacketTracerQualificationProbes,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

_STUB = r"""
const S = __hState;
const port = {getName: () => 'FastEthernet0', getIpAddress: () => S.ip,
  getSubnetMask: () => '255.255.255.248'};
global.ipc = {network: () => ({getDevice: (n) => {
  if (String(n) !== S.device) { return null; }
  return {
    getPortCount: () => 1,
    getPortAt: () => port,
    getProcess: (p) => {
      const name = String(p);
      if (S.throwing.indexOf(name) >= 0) { throw new Error('invalid string position'); }
      if (name === 'DnsClient') { return {getServerIp: () => S.dns}; }
      if (S.gateway_process === name) { return {getDefaultGateway: () => S.gateway}; }
      return null;
    },
  };
}})};
let reported = null;
try {
  (new Function('reportResult', __hScript))((v) => { reported = String(v); });
} catch (error) {
  reported = 'PT_ERROR: ' + error;
}
process.stdout.write(JSON.stringify({reported: reported}));
"""


def _needs_node() -> None:
    if shutil.which("node") is not None:
        return
    if os.environ.get("GITHUB_ACTIONS"):
        pytest.fail("Node is required for the generated-script harness in CI.")
    pytest.skip("Node is unavailable")


def _read(**state: Any) -> dict:
    _needs_node()
    state = {
        "device": "HQ-DEFAULT-PC-01",
        "ip": "10.125.0.2",
        "dns": "10.125.0.10",
        "gateway": "10.125.0.1",
        "gateway_process": "",
        "throwing": [],
        **state,
    }

    def dispatch_and_wait(script: str, _timeout: float) -> BridgeDispatchOutcome:
        program = (
            f"const __hState = {json.dumps(state)};\n"
            f"const __hScript = {json.dumps(script)};\n{_STUB}"
        )
        completed = subprocess.run(
            [shutil.which("node"), "-"],
            input=program,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=json.loads(completed.stdout)["reported"],
        )

    probes = PacketTracerQualificationProbes(
        run_id="run",
        nonce="nonce",
        dispatch_and_wait=dispatch_and_wait,
        send=lambda _script: True,
    )
    reading = probes.read_client_bindings(["HQ-DEFAULT-PC-01"])
    assert reading.observed, reading.cause
    (row,) = reading.payload["clients"]
    return row


def test_a_throwing_gateway_process_keeps_the_resolver_answer():
    """The LIVE shape: HostIp throws; DnsClient still answers."""
    row = _read(throwing=["HostIp", "HostIpProcess"])

    assert row["ipv4"] == "10.125.0.2" and row["error"] == ""
    assert row["dns_api"] is True and row["dns_server"] == "10.125.0.10"
    assert [item["process"] for item in row["gateway_reads"]] == [
        "HostIp",
        "HostIpProcess",
    ]
    for item in row["gateway_reads"]:
        assert item["error"] == "invalid string position"
        assert item["value"] == "" and item["api"] is False


def test_the_suffixed_process_name_answers_on_its_own_row():
    """Whichever documented name answers is recorded as that name, alone."""
    row = _read(throwing=["HostIp"], gateway_process="HostIpProcess")

    first, second = row["gateway_reads"]
    assert first["error"] == "invalid string position" and first["value"] == ""
    assert second == {
        "process": "HostIpProcess",
        "found": True,
        "api": True,
        "value": "10.125.0.1",
        "error": "",
    }
