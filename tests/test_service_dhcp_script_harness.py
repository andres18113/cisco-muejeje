"""Execute the actual S3 DHCP scripts against a persistent Node stub.

The stub state and call log are the oracle. No row produced by the code under
test is used to decide whether a pool changed, an exclusion was preserved or
`dhcpRun` was called.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from packet_tracer_mcp.domain.enterprise.models.configuration import AddressRange
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionExecutionStatus,
)
from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    FootprintFact,
    PostconditionFact,
    ResultFact,
)
from packet_tracer_mcp.domain.enterprise.models.service_plan import (
    AcquireDhcpLease,
    ConfigureServerDhcpPool,
    EnableServerDhcp,
    ServiceEvidenceKind,
    ServicePhase,
    ServiceType,
    ServiceVerificationExpectation,
    ServiceVerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.service_runtime import ObservationFact
from packet_tracer_mcp.infrastructure.execution.endpoint_dhcp_mode_observer import (
    PacketTracerEndpointDhcpModeObserver,
)
from packet_tracer_mcp.infrastructure.execution.enterprise_service_runtime import (
    PacketTracerEnterpriseServiceRuntime,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

SERVER = "SRV"
CLIENT = "PC"
SERVER_ID = "server-1"
CLIENT_ID = "client-1"
INTERFACE = "FastEthernet0"
POOL = "HQ_DATA"
CLAIM_KEY = f"dhcp_client:{CLIENT_ID}:{INTERFACE}"


_DRIVER_JS = r"""
const readline = require('readline');
const state = JSON.parse(process.argv[2]);
const calls = {};
const log = [];

const before = (name) => {
  calls[name] = (calls[name] || 0) + 1;
  log.push(name);
  const afterCalls = (state.throw_after_calls || {})[name];
  if (afterCalls !== undefined && calls[name] > afterCalls) {
    throw new Error('stub after calls: ' + name);
  }
  if ((state.throw_before || []).indexOf(name) >= 0) {
    throw new Error('stub before: ' + name);
  }
};
const after = (name) => {
  if ((state.throw_after || []).indexOf(name) >= 0) {
    throw new Error('stub after: ' + name);
  }
};

const poolObject = (pool) => ({
  getDhcpPoolName: () => { before('getDhcpPoolName'); return pool.name; },
  getNetworkAddress: () => { before('getNetworkAddress'); return pool.network; },
  getSubnetMask: () => { before('getSubnetMask'); return pool.mask; },
  getDefaultRouter: () => { before('getDefaultRouter'); return pool.gateway; },
  getDnsServerIp: () => { before('getDnsServerIp'); return pool.dns; },
  getStartIp: () => { before('getStartIp'); return pool.start; },
  getEndIp: () => { before('getEndIp'); return pool.end; },
  getMaxUsers: () => { before('getMaxUsers'); return pool.max; },
  setNetworkMask: (network, mask) => {
    before('setNetworkMask:' + network + ':' + mask);
    pool.network = String(network); pool.mask = String(mask); after('setNetworkMask');
  },
  setDefaultRouter: (value) => {
    before('setDefaultRouter:' + value); pool.gateway = String(value); after('setDefaultRouter');
  },
  setDnsServerIp: (value) => {
    before('setDnsServerIp:' + value); pool.dns = String(value); after('setDnsServerIp');
  },
  setStartIp: (value) => {
    before('setStartIp:' + value); pool.start = String(value); after('setStartIp');
  },
  setEndIp: (value) => {
    before('setEndIp:' + value); pool.end = String(value); after('setEndIp');
  },
  setMaxUsers: (value) => {
    before('setMaxUsers:' + value); pool.max = Number(value); after('setMaxUsers');
  },
  getLeaseAt: (index) => {
    before('getLeaseAt:' + index);
    if (state.repeat_lease && pool.leases.length) { return pool.leases[0]; }
    if (state.lease_throw_at === index) { throw new Error('lease read failed'); }
    return index < pool.leases.length ? pool.leases[index] : null;
  },
});

const serverProcess = {
  isEnable: () => {
    before('isEnable');
    if (state.server.enable_behavior === 'throw') { throw new Error('enable read failed'); }
    if (state.server.enable_behavior === 'undefined') { return undefined; }
    return state.server.enabled;
  },
  setEnable: (value) => {
    before('setEnable:' + value); state.server.enabled = !!value; after('setEnable');
  },
  getPool: (name) => {
    before('getPool:' + name);
    const pool = state.server.pools[name];
    return pool ? poolObject(pool) : null;
  },
  addPool: (name) => {
    before('addPool:' + name);
    state.server.pools[name] = {
      name: String(name), network: '', mask: '', gateway: '', dns: '',
      start: '', end: '', max: 0, leases: [],
    };
    after('addPool');
  },
  getExcludedAddressCount: () => {
    before('getExcludedAddressCount'); return state.server.exclusions.length;
  },
  getExcludedAddressAt: (index) => {
    before('getExcludedAddressAt:' + index);
    const item = state.server.exclusions[index];
    return item ? {first: item.start, second: item.end} : null;
  },
  addExcludedAddress: (start, end) => {
    before('addExcludedAddress:' + start + ':' + end);
    state.server.exclusions.push({start: String(start), end: String(end)});
    after('addExcludedAddress');
  },
};
const serverMain = {
  getDhcpServerProcessByPortName: (name) => {
    before('getDhcpServerProcessByPortName:' + name);
    return name === state.server.interface ? serverProcess : null;
  },
};

const portObject = (port) => ({
  getName: () => port.name,
  isDhcpClientOn: () => {
    before('isDhcpClientOn');
    if (port.mode_behavior === 'throw') { throw new Error('mode read failed'); }
    if (port.mode_behavior === 'undefined') { return undefined; }
    return port.mode;
  },
  getIpAddress: () => { before('getIpAddress'); return port.ip; },
  getSubnetMask: () => { before('getSubnetMask:client'); return port.mask; },
  getMacAddress: () => { before('getMacAddress'); return port.mac; },
});
const clientProcess = {
  dhcpRun: (name) => {
    before('dhcpRun:' + name + ':claims=' + JSON.stringify(global.__mcpE6Claims || {}));
    state.client.runs += 1;
    if (state.acquire_address) {
      state.client.port.ip = state.acquire_address;
      state.client.port.mask = state.acquire_mask;
    }
    after('dhcpRun');
  },
  getDataOfPort: (name) => {
    before('getDataOfPort:' + name);
    return name === state.client.port.name
      ? {getLeaseTimeStr: () => { before('getLeaseTimeStr'); return state.client.lease_time; }}
      : null;
  },
};

const serverDevice = {
  getPortCount: () => 1,
  getPortAt: () => portObject(state.server.port),
  getProcess: (name) => name === 'DhcpServer' ? serverMain : null,
};
const clientDevice = {
  getPortCount: () => 1,
  getPortAt: () => portObject(state.client.port),
  getProcess: (name) => name === 'DhcpClient' ? clientProcess : null,
};
global.ipc = {network: () => ({getDevice: (name) => (
  name === state.server.name ? serverDevice : name === state.client.name ? clientDevice : null
)})};
global.__mcpE6Claims = state.claims || {};
let reported = null;
global.reportResult = (value) => { reported = String(value); };

readline.createInterface({input: process.stdin}).on('line', (line) => {
  const message = JSON.parse(line);
  if (message.kind === 'state') {
    Object.assign(state, message.state);
    process.stdout.write(JSON.stringify({ok: true}) + '\n');
    return;
  }
  reported = null;
  let failure = '';
  try { new Function(message.script)(); }
  catch (error) { failure = String(error && error.message ? error.message : error); }
  state.claims = global.__mcpE6Claims || {};
  process.stdout.write(JSON.stringify({
    reported: reported,
    failure: failure,
    state: state,
    claims: state.claims,
    log: log.splice(0, log.length),
  }) + '\n');
});
"""


def _needs_node() -> None:
    if shutil.which("node") is not None:
        return
    if os.environ.get("GITHUB_ACTIONS"):
        pytest.fail("Node is required for the DHCP script harness in CI.")
    pytest.skip("Node is unavailable")


class _DhcpEngine:
    def __init__(self, tmp_path, **overrides) -> None:
        _needs_node()
        self.state = {
            "server": {
                "name": SERVER,
                "interface": INTERFACE,
                "enabled": False,
                "enable_behavior": "value",
                "port": {
                    "name": INTERFACE,
                    "mode": False,
                    "ip": "192.0.2.2",
                    "mask": "255.255.255.0",
                    "mac": "AAAA.BBBB.CCCC",
                },
                "pools": {
                    "UNRELATED": {
                        "name": "UNRELATED",
                        "network": "198.51.100.0",
                        "mask": "255.255.255.0",
                        "gateway": "198.51.100.1",
                        "dns": "",
                        "start": "198.51.100.10",
                        "end": "198.51.100.20",
                        "max": 11,
                        "leases": [],
                    }
                },
                "exclusions": [{"start": "198.51.100.1", "end": "198.51.100.1"}],
            },
            "client": {
                "name": CLIENT,
                "port": {
                    "name": INTERFACE,
                    "mode": True,
                    "mode_behavior": "value",
                    "ip": "",
                    "mask": "",
                    "mac": "0011.2233.4455",
                },
                "lease_time": "",
                "runs": 0,
            },
            "claims": {},
            "throw_before": [],
            "throw_after": [],
            "throw_after_calls": {},
            "acquire_address": "",
            "acquire_mask": "255.255.255.0",
            "repeat_lease": False,
            "lease_throw_at": -1,
        }
        for key, value in overrides.items():
            self.state[key] = value
        driver = tmp_path / "dhcp_driver.js"
        driver.write_text(_DRIVER_JS, encoding="utf-8")
        self.process = subprocess.Popen(
            [shutil.which("node"), str(driver), json.dumps(self.state)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.log: list[str] = []
        self.scripts: list[str] = []
        self.transport: dict[str, str] = {}

    def close(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.close()
        self.process.wait(timeout=10)

    def _exchange(self, value: dict) -> dict:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def dispatch_and_wait(self, script: str, _timeout: float):
        self.scripts.append(script)
        phase = (
            "acquire"
            if "dhcpRun" in script
            else "lease"
            if "getLeaseAt" in script
            else "mutation"
        )
        reply = self._exchange({"kind": "script", "script": script})
        self.state = reply["state"]
        self.log.extend(reply["log"])
        if self.transport.get(phase) == "sent_lost":
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTED,
                result=ResultFact.NOT_OBSERVED,
                detail="stub_deadline",
            )
        body = "PT_ERROR:" + reply["failure"] if reply["failure"] else reply["reported"]
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=body,
        )

    def send_and_wait(self, script: str, _timeout: float) -> str | None:
        """Execute one generated reader and return its correlated body."""
        outcome = self.dispatch_and_wait(script, _timeout)
        return outcome.body

    def sync(self) -> None:
        """Push Python-side fixture changes into the persistent engine."""
        self._exchange({"kind": "state", "state": self.state})


@pytest.fixture
def engine(tmp_path):
    """Create persistent Node engines and close each after the test."""
    made: list[_DhcpEngine] = []

    def factory(**overrides):
        item = _DhcpEngine(tmp_path, **overrides)
        made.append(item)
        return item

    yield factory
    for item in made:
        item.close()


def _runtime(item: _DhcpEngine):
    return PacketTracerEnterpriseServiceRuntime(
        lambda: [],
        lambda _js, _timeout: None,
        dispatch_and_wait=item.dispatch_and_wait,
        convergence_interval_seconds=0.0,
    )


def _common(*, host_id=SERVER_ID, host_name=SERVER, model="Server-PT"):
    return dict(
        service_id="service/hq/dhcp",
        service_type=ServiceType.DHCP,
        host_device_id=host_id,
        host_device_name=host_name,
        host_model=model,
        site_id="hq",
        required_capability="service_dhcp_application",
    )


def _enable():
    return EnableServerDhcp(
        id="enable-dhcp",
        phase=ServicePhase.ENABLE,
        interface=INTERFACE,
        **_common(),
    )


def _pool():
    return ConfigureServerDhcpPool(
        id="pool-dhcp",
        phase=ServicePhase.CONTENT,
        depends_on=["enable-dhcp"],
        interface=INTERFACE,
        pool_name=POOL,
        segment_id="hq-data",
        network="192.0.2.0",
        prefix=24,
        netmask="255.255.255.0",
        gateway="192.0.2.1",
        dns_server="192.0.2.2",
        lease_start="192.0.2.10",
        lease_end="192.0.2.19",
        max_users=10,
        excluded_ranges=[AddressRange(start="192.0.2.1", end="192.0.2.2")],
        **_common(),
    )


def _acquire():
    return AcquireDhcpLease(
        id="acquire-dhcp",
        phase=ServicePhase.ACQUISITION,
        depends_on=["pool-dhcp"],
        interface=INTERFACE,
        segment_id="hq-data",
        server_device_id=SERVER_ID,
        server_device_name=SERVER,
        pool_name=POOL,
        network="192.0.2.0",
        prefix=24,
        netmask="255.255.255.0",
        claim_ref="claim/client-1",
        nonce="nonce-1",
        **_common(host_id=CLIENT_ID, host_name=CLIENT, model="PC-PT"),
    )


def _prime_pool(item: _DhcpEngine, *, network="192.0.2.0") -> None:
    item.state["server"]["pools"][POOL] = {
        "name": POOL,
        "network": network,
        "mask": "255.255.255.0",
        "gateway": "192.0.2.1",
        "dns": "192.0.2.2",
        "start": "192.0.2.10",
        "end": "192.0.2.19",
        "max": 10,
        "leases": [],
    }
    item.state["server"]["exclusions"].append(
        {"start": "192.0.2.1", "end": "192.0.2.2"}
    )
    item.sync()


def test_pool_creation_uses_void_add_then_get_and_preserves_unrelated_state(engine):
    """Create through void addPool, reacquire the pool and preserve other state."""
    item = engine()
    runtime = _runtime(item)

    [mutation] = runtime.apply_actions([_pool()])

    pool = item.state["server"]["pools"][POOL]
    assert pool == {
        "name": POOL,
        "network": "192.0.2.0",
        "mask": "255.255.255.0",
        "gateway": "192.0.2.1",
        "dns": "192.0.2.2",
        "start": "192.0.2.10",
        "end": "192.0.2.19",
        "max": 10,
        "leases": [],
    }
    assert "UNRELATED" in item.state["server"]["pools"]
    assert item.state["server"]["exclusions"][0] == {
        "start": "198.51.100.1",
        "end": "198.51.100.1",
    }
    assert item.log.index("addPool:HQ_DATA") < item.log.index(
        "setNetworkMask:192.0.2.0:255.255.255.0"
    )
    assert item.log.count("getPool:HQ_DATA") >= 2
    assert mutation.footprint is FootprintFact.PARTIAL
    assert mutation.postcondition is PostconditionFact.SATISFIED


def test_external_dhcp_names_are_json_serialized_before_javascript(engine):
    """Keep quotes, newlines and script text as data rather than source."""
    item = engine()
    device_name = 'SRV "quoted"\n</script>'
    interface = 'FastEthernet "0"\n'
    item.state["server"]["name"] = device_name
    item.state["server"]["interface"] = interface
    item.sync()
    action = _enable().model_copy(
        update={"host_device_name": device_name, "interface": interface}
    )

    [mutation] = _runtime(item).apply_actions([action])

    assert mutation.postcondition is PostconditionFact.SATISFIED
    assert json.dumps(device_name) in item.scripts[0]
    assert json.dumps(interface) in item.scripts[0]


def test_matching_pool_is_a_noop_and_conflicting_pool_is_refused(engine):
    """Leave an exact pool alone and never overwrite a conflicting identity."""
    matching = engine()
    _prime_pool(matching)
    [same] = _runtime(matching).apply_actions([_pool()])

    assert not any(
        entry.startswith(("addPool:", "setNetworkMask:")) for entry in matching.log
    )
    assert same.attempted is False

    conflict = engine()
    _prime_pool(conflict, network="192.0.3.0")
    before = json.dumps(conflict.state["server"], sort_keys=True)
    [refused] = _runtime(conflict).apply_actions([_pool()])

    assert json.dumps(conflict.state["server"], sort_keys=True) == before
    assert refused.attempted is False
    assert refused.cause == "pool_conflict"


def test_unreadable_pool_identity_refuses_without_any_setter(engine):
    """Treat a failed pool pre-read as unknown rather than absence."""
    item = engine(throw_before=["getPool:HQ_DATA"])
    before = json.dumps(item.state["server"], sort_keys=True)

    [mutation] = _runtime(item).apply_actions([_pool()])

    assert json.dumps(item.state["server"], sort_keys=True) == before
    assert not any(entry.startswith("addPool:") for entry in item.log)
    assert mutation.attempted is False
    assert mutation.cause == "precondition_unobserved"


def test_setter_effect_then_throw_still_runs_the_post_read(engine):
    """Retain the observed stored fields when a void setter throws afterwards."""
    item = engine(throw_after=["setMaxUsers"])

    [mutation] = _runtime(item).apply_actions([_pool()])

    assert item.state["server"]["pools"][POOL]["max"] == 10
    assert mutation.attempted is True
    assert mutation.postcondition is PostconditionFact.SATISFIED
    assert mutation.footprint is FootprintFact.PARTIAL
    assert "setMaxUsers" in mutation.call_error


def test_missing_post_read_never_claims_the_pool_was_stored(engine):
    """Keep the postcondition unobserved when the mandatory post-read fails."""
    item = engine(throw_after_calls={"getPool:HQ_DATA": 2})

    [mutation] = _runtime(item).apply_actions([_pool()])

    assert mutation.attempted is True
    assert mutation.postcondition is PostconditionFact.UNOBSERVED


@pytest.mark.parametrize(
    "held", [None, False, 0, ""], ids=["null", "false", "zero", "empty"]
)
def test_every_present_malformed_claim_refuses_without_dhcp_run(engine, held):
    """Preserve every falsey claim entry and refuse a new acquisition."""
    item = engine(claims={CLAIM_KEY: held})
    before = json.dumps(item.state["claims"], sort_keys=True)

    [mutation] = _runtime(item).apply_actions([_acquire()])

    assert item.state["client"]["runs"] == 0
    assert json.dumps(item.state["claims"], sort_keys=True) == before
    assert mutation.attempted is False
    assert mutation.cause == "subject_claim_unreadable"


def test_acquisition_claim_precedes_one_void_dhcp_run_and_replay_sends_nothing(engine):
    """Write the claim before one void call and suppress an own replay."""
    item = engine()
    runtime = _runtime(item)

    [first] = runtime.apply_actions([_acquire()])
    [second] = runtime.apply_actions([_acquire()])

    assert item.state["client"]["runs"] == 1
    call = next(entry for entry in item.log if entry.startswith("dhcpRun:"))
    assert CLAIM_KEY in call
    assert item.state["claims"][CLAIM_KEY]["state"] == "completed"
    assert first.attempted is True
    assert second.attempted is None
    assert second.cause == "own_claim_replayed"


@pytest.mark.parametrize(
    "native_value",
    [0, 1, "", "false", None],
    ids=["zero", "one", "empty", "false-string", "null"],
)
def test_generated_mode_observer_rejects_non_boolean_native_values(
    engine, native_value
):
    """Catch truthiness coercion in the actual generated mode reader."""
    item = engine()
    item.state["client"]["port"]["mode"] = native_value
    item.sync()

    observed = PacketTracerEndpointDhcpModeObserver(item.send_and_wait).observe(
        CLIENT, INTERFACE
    )

    assert observed.dhcp_mode is None
    assert observed.fresh_evidence is False
    assert observed.failure_reason == "mode_value_invalid"


@pytest.mark.parametrize("behavior", ["undefined", "throw"])
def test_generated_mode_observer_keeps_unreadable_native_values_unobserved(
    engine, behavior
):
    """Keep undefined and throwing getters distinct from observed false."""
    item = engine()
    item.state["client"]["port"]["mode_behavior"] = behavior
    item.sync()

    observed = PacketTracerEndpointDhcpModeObserver(item.send_and_wait).observe(
        CLIENT, INTERFACE
    )

    assert observed.dhcp_mode is None
    assert observed.fresh_evidence is False
    assert (
        observed.failure_reason
        == {
            "undefined": "mode_value_invalid",
            "throw": "mode_getter_error",
        }[behavior]
    )


@pytest.mark.parametrize(
    "native_value",
    [0, 1, "", "false", None],
    ids=["zero", "one", "empty", "false-string", "null"],
)
def test_invalid_native_mode_never_writes_a_claim_or_runs_dhcp(engine, native_value):
    """Catch a truthy invalid mode admitting the generated acquisition effect."""
    item = engine()
    item.state["client"]["port"]["mode"] = native_value
    item.sync()

    [mutation] = _runtime(item).apply_actions([_acquire()])

    assert item.state["client"]["runs"] == 0
    assert item.state["claims"] == {}
    assert mutation.attempted is False
    assert mutation.cause == "dhcp_mode_invalid"


def test_effect_then_throw_and_lost_reply_both_quarantine_without_retry(engine):
    """Keep ambiguity sticky whether the call throws or its answer is lost."""
    throwing = engine(throw_after=["dhcpRun"])
    runtime = _runtime(throwing)
    [mutation] = runtime.apply_actions([_acquire()])
    runtime.apply_actions([_acquire()])

    assert throwing.state["client"]["runs"] == 1
    assert throwing.state["claims"][CLAIM_KEY]["state"] == "unknown"
    assert mutation.attempted is True

    lost = engine()
    lost.transport["acquire"] = "sent_lost"
    runtime = _runtime(lost)
    runtime.apply_actions([_acquire()])
    lost.transport.clear()
    [replay] = runtime.apply_actions([_acquire()])

    assert lost.state["client"]["runs"] == 1
    assert replay.cause == "own_claim_replayed"


def test_a_new_invocation_nonce_cannot_adopt_the_previous_claim(engine):
    """Treat the same action id under another run nonce as a foreign claim."""
    item = engine()
    runtime = _runtime(item)
    runtime.apply_actions([_acquire()])
    held = json.dumps(item.state["claims"][CLAIM_KEY], sort_keys=True)
    later = _acquire().model_copy(update={"nonce": "nonce-2"})

    [mutation] = runtime.apply_actions([later])

    assert item.state["client"]["runs"] == 1
    assert json.dumps(item.state["claims"][CLAIM_KEY], sort_keys=True) == held
    assert mutation.attempted is False
    assert mutation.cause == "subject_claimed"


def _lease_expectation(kind: ServiceVerificationKind):
    return ServiceVerificationExpectation(
        id=f"verify-{kind.value}",
        service_id="service/hq/dhcp",
        action_id="acquire-dhcp",
        kind=kind,
        evidence_kind=(
            ServiceEvidenceKind.DIRECT_STATE
            if kind is ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED
            else ServiceEvidenceKind.BEHAVIORAL
        ),
        host_device_id=SERVER_ID,
        host_device_name=SERVER,
        host_model="Server-PT",
        client_device_id=CLIENT_ID,
        client_device_name=CLIENT,
        client_model="PC-PT",
        expected={
            "interface": INTERFACE,
            "server_interface": INTERFACE,
            "network": "192.0.2.0",
            "prefix": 24,
            "netmask": "255.255.255.0",
            "configure_only": False,
            "server_device_id": SERVER_ID,
            "server_device_name": SERVER,
            "pool_name": POOL,
            "max_users": 10,
        },
    )


def _server_expectation():
    return ServiceVerificationExpectation(
        id="verify-dhcp-server",
        service_id="service/hq/dhcp",
        action_id="pool-dhcp",
        kind=ServiceVerificationKind.DHCP_SERVER_STATE,
        evidence_kind=ServiceEvidenceKind.DIRECT_STATE,
        host_device_id=SERVER_ID,
        host_device_name=SERVER,
        host_model="Server-PT",
        expected={
            "enabled": True,
            "service_type": "dhcp",
            "interface": INTERFACE,
            "pool_name": POOL,
            "network": "192.0.2.0",
            "prefix": 24,
            "netmask": "255.255.255.0",
            "gateway": "192.0.2.1",
            "dns_server": "192.0.2.2",
            "lease_start": "192.0.2.10",
            "lease_end": "192.0.2.19",
            "max_users": 10,
            "excluded_ranges_json": json.dumps(
                [{"start": "192.0.2.1", "end": "192.0.2.2"}],
                sort_keys=True,
                separators=(",", ":"),
            ),
        },
    )


def test_server_state_reads_every_stored_field_but_not_lease_cleanliness(engine):
    """Verify stored configuration without claiming unchanged allocation state."""
    item = engine()
    _prime_pool(item)
    item.state["server"]["enabled"] = True
    item.sync()

    matched = _runtime(item).verify(_server_expectation())

    assert matched.status is ActionExecutionStatus.VERIFIED
    assert matched.claim_level == "stored_dhcp_configuration"
    assert "lease_allocation_state_unobserved" in matched.limitations

    item.state["server"]["pools"][POOL]["network"] = "192.0.3.0"
    item.sync()
    contradicted = _runtime(item).verify(_server_expectation())

    assert contradicted.status is ActionExecutionStatus.FAILED
    assert contradicted.cause == "dhcp_server_state_mismatch"


def test_unrelated_exclusion_inside_the_lease_window_blocks_acquisition_foundation(
    engine,
):
    """Preserve the range but refuse to call a capacity-conflicted pool ready."""
    item = engine()
    _prime_pool(item)
    item.state["server"]["enabled"] = True
    item.state["server"]["exclusions"].append(
        {"start": "192.0.2.15", "end": "192.0.2.15"}
    )
    item.sync()

    row = _runtime(item).verify(_server_expectation())

    assert row.status is ActionExecutionStatus.FAILED
    assert row.cause == "dhcp_exclusion_conflict"
    assert {"start": "192.0.2.15", "end": "192.0.2.15"} in item.state["server"][
        "exclusions"
    ]


def test_fresh_disabled_server_is_a_contradiction_not_a_malformed_read(engine):
    """Preserve a typed false enable flag as negative evidence."""
    item = engine()
    _prime_pool(item)

    row = _runtime(item).verify(_server_expectation())

    assert row.status is ActionExecutionStatus.FAILED
    assert row.observation is ObservationFact.CONTRADICTED
    assert row.cause == "dhcp_server_state_mismatch"


@pytest.mark.parametrize(
    "native_value",
    [0, 1, "", "false", None],
    ids=["zero", "one", "empty", "false-string", "null"],
)
def test_invalid_native_server_enable_neither_mutates_nor_verifies(
    engine, native_value
):
    """Catch isEnable truthiness coercion in mutation and direct read-back."""
    item = engine()
    _prime_pool(item)
    item.state["server"]["enabled"] = native_value
    item.sync()

    [mutation] = _runtime(item).apply_actions([_enable()])
    readback = _runtime(item).verify(_server_expectation())

    assert not any(entry.startswith("setEnable:") for entry in item.log)
    assert mutation.attempted is False
    assert mutation.cause == "dhcp_enable_invalid"
    assert readback.observation is ObservationFact.MALFORMED
    assert readback.cause == "dhcp_server_shape:enabled"


def test_fresh_in_range_address_is_unattributed_and_foreign_address_contradicts(engine):
    """Separate compatible address read-back from incompatible assignment."""
    item = engine()
    item.state["client"]["port"].update(ip="192.0.2.10", mask="255.255.255.0")
    item.sync()
    row = _runtime(item).verify(_lease_expectation(ServiceVerificationKind.DHCP_LEASE))

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.INCONCLUSIVE
    assert row.cause == "acquisition_unattributed"

    foreign = engine()
    foreign.state["client"]["port"].update(ip="198.51.100.10", mask="255.255.255.0")
    foreign.sync()
    row = _runtime(foreign).verify(
        _lease_expectation(ServiceVerificationKind.DHCP_LEASE)
    )

    assert row.status is ActionExecutionStatus.FAILED
    assert row.observation is ObservationFact.CONTRADICTED
    assert row.cause == "foreign_lease"


def test_absent_address_is_unknown_and_false_mode_is_a_contradiction(engine):
    """Keep absence inconclusive while preserving a fresh false-mode conflict."""
    absent = engine()
    row = _runtime(absent).verify(
        _lease_expectation(ServiceVerificationKind.DHCP_LEASE)
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.cause == "acquisition_not_observed"

    disabled = engine()
    disabled.state["client"]["port"]["mode"] = False
    disabled.sync()
    row = _runtime(disabled).verify(
        _lease_expectation(ServiceVerificationKind.DHCP_LEASE)
    )

    assert row.status is ActionExecutionStatus.FAILED
    assert row.cause == "dhcp_mode_disabled"


@pytest.mark.parametrize(
    "native_value",
    [0, 1, "", "false", None],
    ids=["zero", "one", "empty", "false-string", "null"],
)
def test_generated_client_readback_rejects_non_boolean_mode(engine, native_value):
    """Catch truthiness coercion in the real generated client read-back."""
    item = engine()
    item.state["client"]["port"]["mode"] = native_value
    item.sync()

    row = _runtime(item).verify(_lease_expectation(ServiceVerificationKind.DHCP_LEASE))

    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == "dhcp_client_shape:dhcp_mode"


def test_configure_only_returns_typed_not_attempted_without_a_client_read(engine):
    """Return NOT_ATTEMPTED without performing an acquisition-side read."""
    item = engine()
    expectation = _lease_expectation(ServiceVerificationKind.DHCP_LEASE)
    expectation.expected["configure_only"] = True

    row = _runtime(item).verify(expectation)

    assert item.log == []
    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.observation is ObservationFact.NOT_ATTEMPTED
    assert row.claim_level == "acquisition_not_attempted"


def test_lease_table_match_is_attributed_but_no_match_stays_incomplete(engine):
    """Accept a positive exact row while keeping an uncalibrated miss unknown."""
    matched = engine()
    _prime_pool(matched)
    matched.state["client"]["port"].update(ip="192.0.2.10", mask="255.255.255.0")
    matched.state["server"]["pools"][POOL]["leases"] = [
        {
            "ipAddress": "192.0.2.10",
            "macAddress": "0011.2233.4455",
            "leaseTime": 3600,
            "port": INTERFACE,
        }
    ]
    matched.sync()

    row = _runtime(matched).verify(
        _lease_expectation(ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED)
    )

    assert row.status is ActionExecutionStatus.VERIFIED
    assert row.claim_level == "attributed_to_intended_server"

    missing = engine()
    _prime_pool(missing)
    missing.state["client"]["port"].update(ip="192.0.2.10", mask="255.255.255.0")
    missing.sync()
    row = _runtime(missing).verify(
        _lease_expectation(ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED)
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.cause == "lease_table_incomplete"


def test_same_ip_with_different_valid_mac_is_a_foreign_lease_row(engine):
    """Contradict attribution when the same IP belongs to another valid MAC."""
    item = engine()
    _prime_pool(item)
    item.state["client"]["port"].update(ip="192.0.2.10", mask="255.255.255.0")
    item.state["server"]["pools"][POOL]["leases"] = [
        {
            "ipAddress": "192.0.2.10",
            "macAddress": "AAAA.BBBB.CCCC",
            "leaseTime": 3600,
            "port": INTERFACE,
        }
    ]
    item.sync()

    row = _runtime(item).verify(
        _lease_expectation(ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED)
    )

    assert row.status is ActionExecutionStatus.FAILED
    assert row.cause == "foreign_lease_row"


def test_repeated_rows_and_scan_truncation_never_invent_completion(engine):
    """Report repeated or bounded scans without manufacturing an end condition."""
    repeated = engine(repeat_lease=True)
    _prime_pool(repeated)
    repeated.state["client"]["port"].update(ip="192.0.2.11", mask="255.255.255.0")
    repeated.state["server"]["pools"][POOL]["leases"] = [
        {
            "ipAddress": "192.0.2.10",
            "macAddress": "AAAA.BBBB.CCCC",
            "leaseTime": 3600,
            "port": INTERFACE,
        }
    ]
    repeated.sync()

    row = _runtime(repeated).verify(
        _lease_expectation(ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED)
    )

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert row.cause == "lease_table_incomplete"
    assert "lease_row_repeated" in row.limitations

    truncated = engine()
    _prime_pool(truncated)
    expectation = _lease_expectation(ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED)
    expectation.expected["max_users"] = 300

    row = _runtime(truncated).verify(expectation)

    assert row.status is ActionExecutionStatus.UNKNOWN
    assert "lease_scan_truncated" in row.limitations


def test_unparseable_lease_row_is_malformed_not_absent(engine):
    """Reject a structurally invalid row instead of treating it as no lease."""
    item = engine()
    _prime_pool(item)
    item.state["server"]["pools"][POOL]["leases"] = [
        {
            "ipAddress": "192.0.2.10",
            "macAddress": "0011.2233.4455",
            "leaseTime": "not-a-number",
            "port": INTERFACE,
        }
    ]
    item.sync()

    row = _runtime(item).verify(
        _lease_expectation(ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED)
    )

    assert row.observation is ObservationFact.MALFORMED
    assert row.cause == "lease_row_shape"


def test_generated_corpus_uses_only_the_reviewed_non_destructive_dhcp_surface(engine):
    """Pin the generated vendor-call surface, including forbidden shortcuts."""
    item = engine()
    runtime = _runtime(item)
    runtime.apply_actions([_enable()])
    runtime.apply_actions([_pool()])
    runtime.apply_actions([_acquire()])
    runtime.verify(_lease_expectation(ServiceVerificationKind.DHCP_LEASE))
    runtime.verify(_lease_expectation(ServiceVerificationKind.DHCP_LEASE_ATTRIBUTED))
    corpus = "\n".join(item.scripts)

    for required in (
        "getDhcpServerProcessByPortName",
        "isEnable",
        "setEnable",
        "addPool",
        "getPool",
        "setNetworkMask",
        "addExcludedAddress",
        "isDhcpClientOn",
        "dhcpRun",
        "getDataOfPort",
        "getLeaseTimeStr",
        "getLeaseAt",
    ):
        assert required in corpus
    for forbidden in (
        "dhcpRelease",
        "resetDhcpConfOn",
        "removePool",
        "getLeaseCount",
        "registerEvent",
        "dhcpSucceed",
        "dhcpFailed",
        "ipconfig /release",
        "ipconfig /renew",
    ):
        assert forbidden not in corpus
