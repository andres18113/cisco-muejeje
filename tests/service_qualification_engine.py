"""A long-lived Node stub of the Packet Tracer engine for the S4a tests.

Every script the qualification runner can send is executed for real by one
Node process: the S1 build reader, the physical runtime's PTBuilder and
inventory scripts, the Q0/Q1 probes, and the E5/E6 production runtime scripts.
The process outlives individual evaluations because the run bag lives on the
engine global between `new Function()` calls, exactly as in Packet Tracer.

The stub answers the documented call surface with plain state that the test
can read back independently through `snapshot()`. That snapshot, never the
row the runner reports, is the oracle. Nothing here observes Packet Tracer:
whether the real engine behaves like any configuration of this stub is exactly
what Q0/Q1 would measure.

Behaviour switches (`config`) select the engine facts under test:

- `receiver`: `global` evaluates with the engine global as `this` (the file
  channel's wrapper); `fresh` gives every evaluation a new receiver, so a bag
  written under `this` does not persist;
- `queue`: `fifo` runs queued commands one evaluation each before the next
  synchronous command; `coalesce` joins them into one evaluation, as the HTTP
  webview batch does; `drop` never runs them;
- `deliver_events`: `after_eval`, `sync` or `never`;
- `unregister_available`, `unregister_effective`, `unregister_throws`,
  `register_throws` and `readdress_throws` (the port setter that triggers
  `ipChanged`);
- `https_identity` (`distinct`/`same`) and `page_tables` (`separate`/`shared`);
- `getpage_throws_http` / `getpage_throws_https`: URL substrings whose
  `getPage` the HTTP or HTTPS handle refuses, so a cross read can fail on one
  cell without failing the others;
- `fetch_failure`: `error_page` renders fresh non-marker content for a refused
  fetch; `unchanged` leaves the client page as it was (a timeout);
- `serve_https_when_disabled` / `serve_http_when_disabled`: contradict the
  candidate listener model on purpose;
- `version`, `version_getter`, `active_file`, `unset_dns`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from packet_tracer_mcp.domain.enterprise.models.execution import (
    DispatchFact,
    ResultFact,
)
from packet_tracer_mcp.infrastructure.execution.transport_outcome import (
    BridgeDispatchOutcome,
)

_DRIVER_JS = r"""
const readline = require('readline');
const config = Object.assign({
  version: '9.0.1.0858', version_getter: true, active_file: true,
  saved_version: '9.0.1.0001', receiver: 'global', queue: 'fifo',
  deliver_events: 'after_eval', unregister_available: true,
  unregister_effective: true, unregister_throws: false, register_throws: false,
  https_identity: 'distinct', page_tables: 'separate', fetch_failure: 'error_page',
  serve_https_when_disabled: false, serve_http_when_disabled: false,
  unset_dns: '0.0.0.0', reset_claim_between_queued: false, go_returns: true,
  create_throws: false, remove_throws: false, readdress_throws: false,
  getpage_throws_http: [], getpage_throws_https: [],
}, JSON.parse(process.argv[2] || '{}'));

const guardPage = (patterns, url) => {
  for (const pattern of (patterns || [])) {
    if (String(url).indexOf(pattern) >= 0) {
      throw new Error('page read refused: ' + pattern);
    }
  }
};

let uuidSeq = 0;
const newUuid = () => '{stub-' + (++uuidSeq) + '}';
const devices = [];
const links = [];
const pending = [];
const queue = [];
const registrations = [];
const unregisterCalls = [];
const clients = {};
let clientSeq = 0;

const PORTS = {
  'PC-PT': ['FastEthernet0'],
  'Server-PT': ['FastEthernet0'],
  '2960-24TT': Array.from({length: 24}, (_, i) => 'FastEthernet0/' + (i + 1))
    .concat(['GigabitEthernet0/1', 'GigabitEthernet0/2']),
};
const findDevice = (name) => devices.find((d) => d.name === name) || null;
const findPort = (device, port) => {
  const d = findDevice(device);
  return d ? (d.ports.find((p) => p.name === port) || null) : null;
};
const byAddress = (address) => {
  for (const d of devices) {
    if (d.ports.some((p) => p.ip === address)) { return d; }
  }
  return null;
};

const deliver = (event) => {
  for (const r of registrations.slice()) {
    if (r.active && r.uuid === event.uuid && r.event === event.event) {
      try {
        r.cb.call(r.obj, {className: event.className, objectUuid: event.uuid,
          eventName: event.event}, event.args);
      } catch (e) { /* a throwing callback does not stop delivery */ }
    }
  }
};
const flushEvents = () => { while (pending.length) { deliver(pending.shift()); } };

const serverState = (dev) => {
  if (!dev.web) {
    const http = {'index.html': '<html><body>Cisco Packet Tracer</body></html>'};
    const shared = config.page_tables === 'shared' || config.https_identity === 'same';
    dev.web = {httpEnabled: true, httpsEnabled: true, httpsProcessEnabled: true,
      tables: {http: http, https: shared ? http : Object.assign({}, http)}};
  }
  return dev.web;
};

const httpServer = (dev) => {
  const web = serverState(dev);
  if (!web.httpApi) {
    web.httpApi = {
      setEnable: (v) => { web.httpEnabled = !!v; },
      isEnabled: () => web.httpEnabled,
      setPageContents: (url, contents) => { web.tables.http[String(url)] = String(contents); },
      getPage: (url) => {
        guardPage(config.getpage_throws_http, url);
        return web.tables.http[String(url)] || '';
      },
    };
    if (config.https_identity === 'same') {
      web.httpApi.setHttpsEnable = (v) => { web.httpsEnabled = !!v; };
      web.httpApi.isHttpsEnabled = () => web.httpsEnabled;
      web.httpsApi = web.httpApi;
    }
  }
  return web.httpApi;
};

const httpsServer = (dev) => {
  const web = serverState(dev);
  if (config.https_identity === 'same') { return httpServer(dev); }
  if (!web.httpsApi) {
    web.httpsApi = {
      setEnable: (v) => { web.httpsProcessEnabled = !!v; },
      isEnabled: () => web.httpsProcessEnabled,
      setHttpsEnable: (v) => { web.httpsEnabled = !!v; },
      isHttpsEnabled: () => web.httpsEnabled,
      setPageContents: (url, contents) => { web.tables.https[String(url)] = String(contents); },
      getPage: (url) => {
        guardPage(config.getpage_throws_https, url);
        return web.tables.https[String(url)] || '';
      },
    };
  }
  return web.httpsApi;
};

const makeClient = () => {
  const id = 'client-' + (++clientSeq);
  const c = {id: id, https: false, page: ''};
  clients[id] = c;
  c.api = {
    id: id,
    setHttps: (v) => { c.https = !!v; },
    isHttps: () => c.https,
    getLastPageContent: () => c.page,
    go: (url) => {
      const host = String(url).replace(/^https?:\/\//, '').split('/')[0];
      const server = byAddress(host);
      let served = false;
      if (server && server.model === 'Server-PT') {
        const web = serverState(server);
        served = c.https
          ? (web.httpsEnabled || config.serve_https_when_disabled)
          : (web.httpEnabled || config.serve_http_when_disabled);
        if (served) {
          c.page = (c.https ? web.tables.https : web.tables.http)['index.html'] || '';
        }
      }
      if (!served && config.fetch_failure === 'error_page') { c.page = 'Request Timeout'; }
      return config.go_returns;
    },
  };
  return c.api;
};

const processFor = (dev, name) => {
  if (name === 'HttpBackgroundClientManager' && dev.model !== '2960-24TT') {
    return {
      createClient: () => makeClient(),
      deleteClient: (client) => { if (client && client.id) { delete clients[client.id]; } },
    };
  }
  if (name === 'DnsClient' && dev.model !== '2960-24TT') {
    return {getServerIp: () => (dev.ports[0] && dev.ports[0].dns) || config.unset_dns};
  }
  if (dev.model === 'Server-PT' && name === 'HttpServer') { return httpServer(dev); }
  if (dev.model === 'Server-PT' && name === 'HttpsServer') { return httpsServer(dev); }
  return null;
};

const makeDevice = (name, model) => {
  const dev = {name: String(name), model: String(model), ports: [], web: null};
  const api = {
    getName: () => dev.name,
    setName: (value) => { dev.name = String(value); },
    getModel: () => dev.model,
    getPortCount: () => dev.ports.length,
    getPortAt: (i) => (dev.ports[i] ? dev.ports[i].api : null),
    getPort: (value) => {
      const p = dev.ports.find((x) => x.name === value);
      return p ? p.api : null;
    },
    getPorts: () => dev.ports.map((p) => p.name),
    setDhcpFlag: (v) => { dev.dhcp = !!v; },
    getProcess: (value) => processFor(dev, String(value)),
  };
  dev.api = api;
  for (const portName of PORTS[dev.model] || []) {
    const port = {name: portName, link: null, ip: '', mask: '', dns: '', uuid: newUuid()};
    port.api = {
      getName: () => port.name,
      getOwnerDevice: () => api,
      getLink: () => (port.link ? port.link.api : null),
      registerEvent: (event, obj, cb) => {
        if (config.register_throws) { throw new Error('registration refused'); }
        registrations.push({uuid: port.uuid, event: String(event), obj: obj, cb: cb,
          device: dev.name, active: true});
      },
      setIpSubnetMask: (ip, mask) => {
        if (config.readdress_throws) { throw new Error('setter refused'); }
        const oldIp = port.ip;
        const oldMask = port.mask;
        port.ip = String(ip);
        port.mask = String(mask);
        if (oldIp === port.ip && oldMask === port.mask) { return; }
        const event = {uuid: port.uuid, className: 'HostPort', event: 'ipChanged',
          args: {newIp: port.ip, newMask: port.mask, oldIp: oldIp, oldMask: oldMask}};
        if (config.deliver_events === 'sync') { deliver(event); }
        else if (config.deliver_events === 'after_eval') { pending.push(event); }
      },
      setDnsServerIp: (value) => { port.dns = String(value); },
      setDefaultGateway: (value) => { port.gateway = String(value); },
    };
    dev.ports.push(port);
  }
  return dev;
};

const removeDevice = (name) => {
  if (config.remove_throws) { throw new Error('remove refused'); }
  const index = devices.findIndex((d) => d.name === name);
  if (index < 0) { return; }
  const dev = devices[index];
  for (const port of dev.ports) {
    if (port.link) {
      const link = port.link;
      link.a.link = null;
      link.b.link = null;
      links.splice(links.indexOf(link), 1);
    }
  }
  devices.splice(index, 1);
};

const workspace = {removeDevice: removeDevice};
global.ipc = {
  network: () => ({
    getDevice: (name) => { const d = findDevice(String(name)); return d ? d.api : null; },
    getDeviceCount: () => devices.length,
    getDeviceAt: (i) => (devices[i] ? devices[i].api : null),
    getLinkCount: () => links.length,
    getLinkAt: (i) => (links[i] ? links[i].api : null),
  }),
  appWindow: () => {
    const app = {
      getActiveFile: () => (config.active_file
        ? {getVersion: () => config.saved_version} : null),
      getActiveWorkspace: () => ({getLogicalWorkspace: () => workspace}),
    };
    if (config.version_getter) { app.getVersion = () => config.version; }
    return app;
  },
};
global.lwAddDevice = (name, type, model, x, y) => {
  if (config.create_throws) { throw new Error('creation refused'); }
  devices.push(makeDevice(name, model));
  return name;
};
global.lwAddLink = (d1, p1, d2, p2, cable) => {
  const a = findPort(String(d1), String(p1));
  const b = findPort(String(d2), String(p2));
  if (!a || !b || a.link || b.link) { return false; }
  const link = {uuid: newUuid(), a: a, b: b};
  link.api = {getClassName: () => 'Link', getPort1: () => a.api,
    getPort2: () => b.api, getObjectUuid: () => link.uuid};
  a.link = link;
  b.link = link;
  links.push(link);
  return true;
};
global.configurePcIp = (name, dhcp, ip, mask, gateway, dns, iface) => {
  const port = findPort(String(name), String(iface || 'FastEthernet0'));
  if (!port) { return false; }
  if (ip && mask) { port.ip = String(ip); port.mask = String(mask); }
  if (dns) { port.dns = String(dns); }
  return true;
};
if (config.unregister_available) {
  global._ScriptModule = {unregisterIpcEventByID: (className, uuid, event, obj, cb) => {
    unregisterCalls.push({className: String(className), uuid: String(uuid),
      event: String(event)});
    if (config.unregister_throws) { throw new Error('unregister refused'); }
    if (config.unregister_effective) {
      for (const r of registrations) {
        if (r.uuid === uuid && r.event === event && r.cb === cb) { r.active = false; }
      }
    }
  }};
}

const evaluate = (script) => {
  let reported = null;
  const report = (value) => { reported = String(value); };
  const receiver = config.receiver === 'global' ? globalThis : {};
  try { (new Function('reportResult', script)).call(receiver, report); }
  catch (error) { reported = 'PT_ERROR: ' + error; }
  return reported;
};
const resetClaims = () => {
  const bag = globalThis.__mcpE6Q || {};
  for (const key of Object.keys(bag)) {
    if (bag[key] && bag[key].atom) { bag[key].atom.claim = ''; }
  }
};
const runQueued = () => {
  if (!queue.length) { return; }
  if (config.queue === 'coalesce') {
    evaluate(queue.splice(0, queue.length).join('\n'));
  } else {
    while (queue.length) {
      evaluate(queue.shift());
      if (config.reset_claim_between_queued) { resetClaims(); }
    }
  }
  if (config.deliver_events === 'after_eval') { flushEvents(); }
};

const snapshot = () => {
  const bag = globalThis.__mcpE6Q || {};
  const runs = {};
  for (const key of Object.keys(bag)) { runs[key] = Object.keys(bag[key] || {}); }
  const servers = {};
  for (const d of devices) {
    if (d.web) {
      servers[d.name] = {http_enabled: d.web.httpEnabled, https_enabled: d.web.httpsEnabled,
        http_pages: Object.keys(d.web.tables.http), https_pages: Object.keys(d.web.tables.https)};
    }
  }
  return {
    devices: devices.map((d) => ({name: d.name, model: d.model,
      ports: d.ports.filter((p) => p.ip || p.dns || p.link)
        .map((p) => ({name: p.name, ip: p.ip, dns: p.dns, linked: !!p.link}))})),
    links: links.length,
    run_bags: runs,
    registrations: registrations.map((r) => ({device: r.device, event: r.event,
      active: r.active})),
    unregister_calls: unregisterCalls.slice(),
    servers: servers,
    live_clients: Object.keys(clients).length,
    queued: queue.length,
    production_globals: ['__mcpE6Claims', '__mcpE6Inert', '__mcpE6HttpClients']
      .filter((key) => Object.prototype.hasOwnProperty.call(globalThis, key)),
  };
};

readline.createInterface({input: process.stdin}).on('line', (line) => {
  const message = JSON.parse(line);
  let reply;
  if (message.kind === 'config') {
    Object.assign(config, message.config);
    reply = {ok: true};
  } else if (message.kind === 'snapshot') {
    reply = snapshot();
  } else if (message.kind === 'queue') {
    if (config.queue !== 'drop') { queue.push(message.script); }
    reply = {accepted: true};
  } else if (message.kind === 'eval') {
    runQueued();
    const reported = evaluate(message.script);
    if (config.deliver_events === 'after_eval') { flushEvents(); }
    reply = {reported: reported};
  } else if (message.kind === 'seed_device') {
    const dev = makeDevice(message.name, message.model);
    devices.push(dev);
    reply = {ok: true};
  } else {
    reply = {error: 'unknown message'};
  }
  process.stdout.write(JSON.stringify(reply) + '\n');
});
"""


def require_node() -> str:
    """Return the Node executable; skip locally without it, fail in CI."""
    node = shutil.which("node")
    if node is not None:
        return node
    if os.environ.get("GITHUB_ACTIONS"):
        pytest.fail("Node is required for the qualification engine stub in CI.")
    pytest.skip("Node is unavailable")
    raise AssertionError("unreachable")


class NodeEngine:
    """One stub engine process; every call is one synchronous exchange."""

    def __init__(self, directory: Path, **config: Any) -> None:
        """Start the engine with its behaviour switches."""
        node = require_node()
        driver = directory / "qualification_engine.js"
        driver.write_text(_DRIVER_JS, encoding="utf-8")
        self._process = subprocess.Popen(
            [node, str(driver), json.dumps(config)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

    def _exchange(self, message: dict[str, Any]) -> dict[str, Any]:
        assert self._process.stdin is not None and self._process.stdout is not None
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()
        line = self._process.stdout.readline()
        if not line:
            raise RuntimeError("The stub engine exited.")
        return json.loads(line)

    def configure(self, **config: Any) -> None:
        """Change behaviour switches between evaluations."""
        self._exchange({"kind": "config", "config": config})

    def evaluate(self, script: str) -> str | None:
        """Run queued commands, then one script, and return what it reported."""
        return self._exchange({"kind": "eval", "script": script})["reported"]

    def queue(self, script: str) -> bool:
        """Queue one fire-and-forget script."""
        return bool(self._exchange({"kind": "queue", "script": script})["accepted"])

    def seed_device(self, name: str, model: str) -> None:
        """Place a device that the runner did not create (a foreign device)."""
        self._exchange({"kind": "seed_device", "name": name, "model": model})

    def snapshot(self) -> dict[str, Any]:
        """Return the stub's independent state: the oracle of every test."""
        return self._exchange({"kind": "snapshot"})

    def close(self) -> None:
        """Stop the engine process."""
        if self._process.stdin is not None:
            self._process.stdin.close()
        self._process.wait(timeout=10)


class NodeEngineTransport:
    """A controlled channel over the stub engine.

    `lose` names 1-based call numbers whose script still executes while the
    response is lost; `not_submitted` names calls that never reach the engine;
    `before` runs a hook just before a numbered call (to seed a foreign device
    mid-run, for example). `calls` records every script in order, so a test can
    count and inspect exactly what crossed the boundary.
    """

    def __init__(
        self,
        engine: NodeEngine,
        *,
        lose: set[int] | None = None,
        not_submitted: set[int] | None = None,
        before: dict[int, Any] | None = None,
    ) -> None:
        """Bind the channel to one engine."""
        self.engine = engine
        self.lose = lose or set()
        self.not_submitted = not_submitted or set()
        self.before = before or {}
        self.calls: list[tuple[str, str]] = []

    def _number(self, kind: str, script: str) -> int:
        number = len(self.calls) + 1
        hook = self.before.get(number)
        if hook is not None:
            hook()
        self.calls.append((kind, script))
        return number

    def send(self, js_code: str) -> bool:
        """Queue one command; a not-submitted call reports False."""
        number = self._number("send", js_code)
        if number in self.not_submitted:
            return False
        accepted = self.engine.queue(js_code)
        return accepted and number not in self.lose

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        """Execute one command and return its body unless it is lost."""
        outcome = self.dispatch_and_wait(js_code, timeout)
        return outcome.body if outcome.result is ResultFact.CORRELATED else None

    def dispatch_and_wait(self, js_code: str, timeout: float) -> BridgeDispatchOutcome:
        """Execute one command and report typed facts like the real channels."""
        number = self._number("dispatch", js_code)
        if number in self.not_submitted:
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.NOT_SUBMITTED,
                result=ResultFact.NOT_OBSERVED,
                detail="stub_not_submitted",
            )
        body = self.engine.evaluate(js_code)
        if number in self.lose:
            return BridgeDispatchOutcome(
                dispatch=DispatchFact.ACCEPTANCE_UNKNOWN,
                result=ResultFact.NOT_OBSERVED,
                detail="stub_response_lost",
            )
        return BridgeDispatchOutcome(
            dispatch=DispatchFact.ACCEPTED,
            result=ResultFact.CORRELATED,
            body=body,
        )


# -- simulation boundaries -------------------------------------------------------

SIM_SHA = "a" * 40
SIM_TREE = "f" * 40
SIM_BUILD = "9.0.1.0858"


class FakeClock:
    """A monotonic clock that only moves when the runner sleeps or a test says so."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance the fake time instead of waiting."""
        self.sleeps.append(seconds)
        self.now += seconds


class RecordingStore:
    """The real record store, with injectable write failures per step."""

    def __init__(
        self,
        directory: Path,
        *,
        fail_at: set[str] | None = None,
        fail_from: str | None = None,
    ) -> None:
        """Wrap a real store; `fail_from` loses persistence from that step on."""
        from packet_tracer_mcp.infrastructure.persistence.service_qualification_store import (
            QualificationRecordStore,
        )

        self.inner = QualificationRecordStore(directory)
        self.fail_at = fail_at or set()
        self.fail_from = fail_from
        self.lost = False
        self.writes: list[str] = []

    def _fail(self, step: str) -> None:
        from packet_tracer_mcp.application.ports.service_run_record import (
            RunRecordPersistenceError,
        )

        if step == self.fail_from:
            self.lost = True
        if self.lost or step in self.fail_at:
            raise RunRecordPersistenceError(f"injected write failure at {step}")

    def begin(self, record):
        """Create the record unless `begin` is set to fail."""
        self.writes.append("begin")
        self._fail("begin")
        return self.inner.begin(record)

    def advance(self, record):
        """Advance the record unless its step is set to fail."""
        self.writes.append(record.persisted_step)
        self._fail(record.persisted_step)
        return self.inner.advance(record)

    def complete(self, record):
        """Complete the record unless `complete` is set to fail."""
        self.writes.append("complete")
        self._fail("complete")
        return self.inner.complete(record)


def simulated_boundaries(directory: Path, transport: Any, **overrides: Any):
    """Return the production composition with only external boundaries replaced.

    The record is always marked `offline_simulation`; a test that needs a
    different boundary passes it as an override.
    """
    import dataclasses

    from packet_tracer_mcp.adapters.cli.service_qualification import (
        production_boundaries,
    )
    from packet_tracer_mcp.application.ports.service_qualification import (
        OpenedTransport,
    )
    from packet_tracer_mcp.application.use_cases.qualify_server_services import (
        IsolationObservation,
    )
    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        ExecutionMode,
        RepositoryIdentity,
    )

    clock = overrides.pop("clock", None) or FakeClock()
    values: dict[str, Any] = {
        "execution_mode": ExecutionMode.OFFLINE_SIMULATION,
        "isolation": lambda: IsolationObservation(True, "ISOLATED", "simulated"),
        "repository": lambda: RepositoryIdentity(
            branch="feature/sim",
            head=SIM_SHA,
            tree=SIM_TREE,
            clean=True,
            upstream="cisco/feature/sim",
            upstream_head=SIM_SHA,
        ),
        "record_store": RecordingStore(directory / "records"),
        "open_transport": lambda channel: OpenedTransport(
            channel, transport, True, "stub_engine"
        ),
        "close_transport": lambda opened: None,
        "clock": clock,
        "sleep": clock.sleep,
    }
    values.update(overrides)
    return dataclasses.replace(production_boundaries(directory), **values)


def authorization_args(
    stage: str = "Q0",
    *,
    sha: str = SIM_SHA,
    channel: str = "file",
    build: str = SIM_BUILD,
    targets: tuple[str, ...] | None = None,
    operations: str | None = None,
    seconds: str | None = None,
) -> list[str]:
    """Return a complete, matching authorization for one stage as CLI arguments."""
    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        STAGE_CEILINGS,
        QualificationStage,
        stage_definition,
    )

    definition = stage_definition(stage)
    names = targets if targets is not None else definition.fixture_names
    ceiling = STAGE_CEILINGS[QualificationStage(stage)]
    args = [
        "--authorization-id",
        f"TD-{stage}-simulated",
        "--authorized-stage",
        stage,
        "--authorized-sha",
        sha,
        "--authorized-channel",
        channel,
        "--authorized-build",
        build,
        "--authorized-max-operations",
        operations or str(ceiling[0]),
        "--authorized-max-seconds",
        seconds or str(ceiling[1]),
    ]
    for name in names:
        args += ["--authorized-target", name]
    return args


def request_args(
    stage: str = "Q0",
    *,
    sha: str = SIM_SHA,
    channel: str = "file",
    build: str = SIM_BUILD,
    targets: tuple[str, ...] | None = None,
) -> list[str]:
    """Return the request half of a stage invocation as CLI arguments."""
    from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
        stage_definition,
    )

    definition = stage_definition(stage)
    names = targets if targets is not None else definition.fixture_names
    args = [
        "--execute",
        "--stage",
        stage,
        "--expected-head",
        sha,
        "--channel",
        channel,
        "--packet-tracer-build",
        build,
    ]
    for name in names:
        args += ["--target", name]
    return args
