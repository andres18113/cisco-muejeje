"""SP-1 A-6: the client gateway and resolver readers, run as real scripts.

The script is exactly what `PacketTracerEnterpriseServiceRuntime` generates,
evaluated by Node against a stub `ipc` whose PC exposes the documented
`HostIp.getDefaultGateway()` and `DnsClient.getServerIp()` (IpcAPI reference
bundled with Packet Tracer). The getters are documented, not measured, so the
stub answers both as plain strings and as objects that stringify, and a
missing process or getter must never read as a pass.

Skipped only when Node is missing locally; under `GITHUB_ACTIONS` it fails.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    ServiceEvidenceKind,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import ObservationFact
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

PC = "BR2-DEFAULT-PC-01"

_STUB = r"""
const S = __hState;
const makeIp = (value) => S.as_object
  ? {toString: () => value, getIpString: () => value}
  : value;
const processes = {
  HostIp: () => S.gateway === undefined ? null
    : (S.gateway_getter ? {getDefaultGateway: () => makeIp(S.gateway)} : {}),
  DnsClient: () => S.dns === undefined ? null
    : {getServerIp: () => makeIp(S.dns)},
};
global.ipc = {network: () => ({getDevice: (n) => {
  if (String(n) !== S.device) { return null; }
  return {getProcess: (p) => {
    S.asked.push(String(p));
    const make = processes[String(p)];
    return make ? make() : null;
  }};
}})};
let reported = null;
try {
  (new Function('reportResult', __hScript))((v) => { reported = String(v); });
} catch (error) {
  reported = 'PT_ERROR: ' + error;
}
process.stdout.write(JSON.stringify({reported: reported, asked: S.asked}));
"""


def _needs_node() -> None:
    if shutil.which("node") is not None:
        return
    if os.environ.get("GITHUB_ACTIONS"):
        pytest.fail("Node is required for the generated-script harness in CI.")
    pytest.skip("Node is unavailable")


class _Engine:
    def __init__(self, **state: Any) -> None:
        self.state = {"device": PC, "asked": [], "gateway_getter": True, **state}
        self.asked: list[str] = []
        self.scripts: list[str] = []

    def dispatch_and_wait(self, script: str, _timeout: float) -> BridgeDispatchOutcome:
        self.scripts.append(script)
        program = (
            f"const __hState = {json.dumps(self.state)};\n"
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
        observed = json.loads(completed.stdout)
        self.asked = observed["asked"]
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=observed["reported"],
        )


def _expectation(kind: ServiceVerificationKind, value: str):
    field = (
        "gateway"
        if kind is ServiceVerificationKind.CLIENT_GATEWAY
        else ("server_address")
    )
    return ServiceVerificationExpectation(
        id=f"verify-{kind.value}",
        service_id="service/hq/sp1-web",
        action_id="enable",
        kind=kind,
        evidence_kind=ServiceEvidenceKind.BEHAVIORAL,
        host_device_id="web",
        host_device_name="HQ-DEFAULT-WEB-01",
        client_device_id="pc",
        client_device_name=PC,
        required=False,
        expected={field: value},
    )


def _verify(engine: _Engine, kind: ServiceVerificationKind, value: str):
    _needs_node()
    runtime = PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda script, timeout: None,
        dispatch_and_wait=engine.dispatch_and_wait,
    )
    return runtime.verify(_expectation(kind, value))


@pytest.mark.parametrize("as_object", [False, True])
@pytest.mark.parametrize(
    ("kind", "state"),
    [
        (ServiceVerificationKind.CLIENT_GATEWAY, {"gateway": "10.40.0.25"}),
        (ServiceVerificationKind.CLIENT_DNS_SERVER, {"dns": "10.40.0.25"}),
    ],
)
def test_the_planned_binding_is_read_back(kind, state, as_object):
    """The documented getter returns the planned address: fresh and verified."""
    engine = _Engine(as_object=as_object, **state)

    row = _verify(engine, kind, "10.40.0.25")

    assert row.status is ActionExecutionStatus.VERIFIED
    assert row.observation is ObservationFact.OBSERVED and row.fresh_evidence
    expected_process = (
        "HostIp" if kind is ServiceVerificationKind.CLIENT_GATEWAY else "DnsClient"
    )
    assert engine.asked == [expected_process]


@pytest.mark.parametrize("value", ["10.40.0.1", "0.0.0.0", ""])
def test_another_or_an_unset_resolver_is_fresh_contradiction(value):
    """A wrong resolver is observed and refutes the plan; it is not unknown."""
    engine = _Engine(dns=value)

    row = _verify(engine, ServiceVerificationKind.CLIENT_DNS_SERVER, "10.40.0.9")

    assert row.status is ActionExecutionStatus.FAILED
    assert row.observation is ObservationFact.CONTRADICTED
    assert row.cause == "server_address_differs"
    assert row.observed == {"server_address": value}


@pytest.mark.parametrize(
    ("state", "cause"),
    [
        ({}, "process_unavailable:HostIp"),
        (
            {"gateway": "10.40.0.25", "gateway_getter": False},
            "getter_unavailable:HostIp.getDefaultGateway",
        ),
        ({"device": "OTHER", "gateway": "10.40.0.25"}, "client_not_found"),
    ],
)
def test_an_absent_process_getter_or_client_is_unobservable(state, cause):
    """Documented is not measured: an absent surface never passes."""
    engine = _Engine(**state)

    row = _verify(engine, ServiceVerificationKind.CLIENT_GATEWAY, "10.40.0.25")

    assert row.status is ActionExecutionStatus.UNOBSERVABLE
    assert row.cause == cause
    assert not row.fresh_evidence


def test_the_script_serializes_the_client_name_and_sends_nothing_else():
    """One read, the name as JSON, no command typed on the client."""
    engine = _Engine(gateway="10.40.0.25")

    _verify(engine, ServiceVerificationKind.CLIENT_GATEWAY, "10.40.0.25")

    [script] = engine.scripts
    assert json.dumps(PC) in script
    assert "enterCommand" not in script and "\n" not in script
