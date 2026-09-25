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
  `getPage` the HTTP or HTTPS handle refuses, so a read can fail on one cell
  without failing the others;
- `setpage_throws_http` / `setpage_throws_https`: URL substrings whose
  `setPageContents` the handle refuses although the page exists. Independently
  of these, `setPageContents` only UPDATES a page: an unknown URL throws
  `File not exist: <url>`, which is what the Q1 record at `0850de3` measured
  for two newly named pages. The stub never creates a page;
- `setpage_throws_after_http` / `setpage_throws_after_https`: URL substrings
  whose `setPageContents` writes the contents and THEN throws, so a caught
  exception coincides with a page that did change;
- `ports_up` / `protocol_up`: what a linked port's `isPortUp()` and
  `isProtocolUp()` report (an unlinked port reports false);
- `ports_down_calls`: how many of the first `isPortUp`/`isProtocolUp` calls
  answer false before the flags above apply, so a fixture can come up between
  two aggregate readiness reads;
- `port_up_return` / `protocol_up_return`: `boolean`, or `number`, `string`,
  `undefined` or `null` to answer with something that is not a boolean;
- `dhcp_default_pool`: `native` for the exact pool the LIVE Q3 record observed
  on stock Server-PT, `arbitrary` (or the legacy `true`) for a different
  unreviewed default, `false` for none;
- `dhcp_pool_selection`: which pool `dhcpRun` allocates from -- `first` by
  sorted name, `intended` for `MCP_E6Q_DHCP`, `default` for any other pool.
  Nothing measured says which one a native server picks;
- `default_pool_change_on_enable`: fields merged into every non-intended pool
  when the DHCP process is enabled;
- `default_pool_drift_reads`: the Nth native inventory read moves every
  non-intended pool on its own, with no intervention between the readings.
  It is the autonomous-drift scenario the D-DHCP control observation has to
  tell apart from an effect;
- `default_pool_realigns_on_address`: addressing a Server-PT through
  `configurePcIp` realigns every non-intended pool to the address's network,
  start at the network, end `max` addresses later -- the transition D-DHCP
  attempt 2 recorded, reproduced here as a scenario, never as evidence;
- `dhcp_mode_acquires`: activating a client's DHCP mode runs one background
  acquisition when an enabled server exists, which is the confound Q3-FL has
  to observe rather than assume away;
- `dhcp_failure_address`: the address a failed acquisition leaves on the
  port (for example a link-local one), or empty to leave it unchanged;
- `dhcp_pool_selection`: also `intended_then_default`, which falls back to
  the other pool when the intended one is full;
- `drop_product_claims_after_eval`: the product claim store vanishes after
  every evaluation, so a replay finds no claim and dispatches again -- the
  negative control of the same-action repeat;
- `fetch_failure`: `error_page` renders fresh non-marker content for a refused
  fetch; `unchanged` leaves the client page as it was (a timeout);
- `serve_nothing`: no fetch is served whatever the listeners say, which with
  `fetch_failure=unchanged` is the all-timeouts trace Q1 recorded at `0850de3`;
- `fetch_content_override`: when set to a string, a served fetch returns that
  fresh content instead of the server page, modelling a wrong completed read;
- `serve_https_when_disabled` / `serve_http_when_disabled`: contradict the
  candidate listener model on purpose;
- `terminal_response_delay_reads`: how many `getOutput` reads a dispatched
  command withholds its response for. A real terminal prints while the
  caller polls, so an instantly complete command is the fastest path and
  never the worst case a budget has to survive;
- `delete_client_throws` / `delete_client_inert`: the owned background
  client's release refuses, or reports success while the client stays.
  Either way the run ends with an unresolved effect it has to declare;
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
  fetch_content_override: null,
  serve_https_when_disabled: false, serve_http_when_disabled: false,
  unset_dns: '0.0.0.0', reset_claim_between_queued: false, go_returns: true,
  create_throws: false, remove_throws: false, readdress_throws: false,
  getpage_throws_http: [], getpage_throws_https: [],
  setpage_throws_http: [], setpage_throws_https: [],
  setpage_throws_after_http: [], setpage_throws_after_https: [],
  ports_up: true, protocol_up: true, serve_nothing: false,
  ports_down_calls: 0, port_up_return: 'boolean', protocol_up_return: 'boolean',
  dhcp_table_end: 'null', dhcp_acquire_throws: false,
  dhcp_emit_events: true, dhcp_lease_time: '3600', dhcp_lease_time_ticks: false,
  dhcp_client_address_override: null, dhcp_default_pool: false,
  dhcp_pool_selection: 'first', default_pool_change_on_enable: null,
  default_pool_drift_reads: 0, default_pool_realigns_on_address: false,
  dhcp_mode_acquires: false, dhcp_failure_address: '',
  dhcp_native_start_behavior: 'change',
  dhcp_native_max_behavior: 'change',
  dhcp_server_initial_enabled: false, dhcp_pool_count_invalid: false,
  dhcp_enable_on_server_address: false,
  dhcp_native_gateway_behavior: 'change', dhcp_native_dns_behavior: 'change',
  dhcp_native_exclusion_behavior: 'change',
  dhcp_initial_exclusions: [],
  drop_product_claims_after_eval: false,
  terminals: false, terminal_refuses: false, ping_reachable: true,
  terminal_response_delay_reads: 0,
  delete_client_throws: false, delete_client_inert: false,
  ping_unsupported: false, stp_unsupported: false, stp_vlan: 1,
  stp_forward_delay: 15, stp_rows: {}, stp_extra_rows: [],
  light_status: 2, light_status_return: 'number', port_number_http: 80,
  port_number_https: 443, port_number_return: 'number',
}, JSON.parse(process.argv[2] || '{}'));

// What a non-boolean reader returns. Packet Tracer is free to answer with
// something that is not a boolean, and the readiness rule has to tell that
// apart from an actual false instead of coercing both into one.
const NON_BOOLEAN = {number: 1, string: 'up', undefined: undefined, null: null};
const readinessCalls = {portUp: 0, protocolUp: 0};

// The exact native pool a stock Server-PT carried in the Q3 ordinal-2 LIVE
// record. `arbitrary` is a different, unreviewed default that must refuse.
const DEFAULT_POOLS = {
  native: {name: 'serverPool', network: '0.0.0.0', mask: '0.0.0.0',
    gateway: '0.0.0.0', dns: '0.0.0.0', start: '0.0.0.0', end: '0.0.2.0',
    max: 512, leases: []},
  arbitrary: {name: 'DEFAULT', network: '10.0.0.0', mask: '255.255.255.0',
    gateway: '10.0.0.1', dns: '', start: '10.0.0.10', end: '10.0.0.20',
    max: 11, leases: []},
};

const guardPage = (patterns, url) => {
  for (const pattern of (patterns || [])) {
    if (String(url).indexOf(pattern) >= 0) {
      throw new Error('page read refused: ' + pattern);
    }
  }
};
const updatePage = (table, patterns, url, contents, afterPatterns) => {
  for (const pattern of (patterns || [])) {
    if (String(url).indexOf(pattern) >= 0) {
      throw new Error('page write refused: ' + pattern);
    }
  }
  if (!Object.prototype.hasOwnProperty.call(table, String(url))) {
    throw new Error('File not exist: ' + url);
  }
  table[String(url)] = String(contents);
  for (const pattern of (afterPatterns || [])) {
    if (String(url).indexOf(pattern) >= 0) {
      throw new Error('page write failed after the change: ' + pattern);
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
const dhcpRuns = [];
const backgroundAcquisitions = [];
const staticAddresses = [];
const ipToInt = (value) => String(value).split('.').reduce(
  (total, part) => (total * 256) + Number(part), 0);
const intToIp = (value) => [24, 16, 8, 0].map(
  (shift) => Math.floor(value / Math.pow(2, shift)) % 256).join('.');
const dhcpSetterCalls = {
  setDhcpFlag: 0, configurePcIpDhcp: 0, setEnable: 0, addPool: 0,
  setNetworkMask: 0,
  setDefaultRouter: 0, setDnsServerIp: 0, setStartIp: 0, setEndIp: 0,
  setMaxUsers: 0, addExcludedAddress: 0,
};
let clientSeq = 0;
let defaultPoolReads = 0;

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
      getPortNumber: () => (config.port_number_return === 'number'
        ? config.port_number_http : NON_BOOLEAN[config.port_number_return]),
      setPageContents: (url, contents) => {
        updatePage(web.tables.http, config.setpage_throws_http, url, contents,
          config.setpage_throws_after_http);
      },
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
      getPortNumber: () => (config.port_number_return === 'number'
        ? config.port_number_https : NON_BOOLEAN[config.port_number_return]),
      setPageContents: (url, contents) => {
        updatePage(web.tables.https, config.setpage_throws_https, url, contents,
          config.setpage_throws_after_https);
      },
      getPage: (url) => {
        guardPage(config.getpage_throws_https, url);
        return web.tables.https[String(url)] || '';
      },
    };
  }
  return web.httpsApi;
};

const makeClient = (owner) => {
  const id = 'client-' + (++clientSeq);
  const c = {id: id, https: false, page: ''};
  clients[id] = c;
  c.api = {
    id: id,
    getOwnerDevice: () => (owner ? owner.api : null),
    setHttps: (v) => { c.https = !!v; },
    isHttps: () => c.https,
    getLastPageContent: () => c.page,
    go: (url) => {
      const host = String(url).replace(/^https?:\/\//, '').split('/')[0];
      const server = byAddress(host);
      let served = false;
      if (server && server.model === 'Server-PT' && !config.serve_nothing) {
        const web = serverState(server);
        served = c.https
          ? (web.httpsEnabled || config.serve_https_when_disabled)
          : (web.httpEnabled || config.serve_http_when_disabled);
        if (served) {
          c.page = (c.https ? web.tables.https : web.tables.http)['index.html'] || '';
          if (typeof config.fetch_content_override === 'string') {
            c.page = config.fetch_content_override;
          }
        }
      }
      if (!served && config.fetch_failure === 'error_page') { c.page = 'Request Timeout'; }
      return config.go_returns;
    },
  };
  return c.api;
};

const dhcpState = (dev) => {
  if (!dev.dhcpServer) {
    dev.dhcpServer = {
      enabled: config.dhcp_server_initial_enabled === true,
      exclusions: (config.dhcp_initial_exclusions || []).map((x) => ({
        start: String(x.start), end: String(x.end)
      })), pools: {}
    };
    const kind = config.dhcp_default_pool === true
      ? 'arbitrary' : config.dhcp_default_pool;
    const template = kind ? DEFAULT_POOLS[kind] : null;
    if (template) {
      dev.dhcpServer.pools[template.name] =
        Object.assign({}, template, {leases: []});
    }
  }
  return dev.dhcpServer;
};

const dhcpPool = (dev, pool) => ({
  getDhcpPoolName: () => pool.name,
  getNetworkAddress: () => pool.network,
  getSubnetMask: () => pool.mask,
  getDefaultRouter: () => pool.gateway,
  getDnsServerIp: () => pool.dns,
  getStartIp: () => pool.start,
  getEndIp: () => pool.end,
  getMaxUsers: () => pool.max,
  setNetworkMask: (network, mask) => {
    dhcpSetterCalls.setNetworkMask++;
    pool.network = String(network); pool.mask = String(mask);
  },
  setDefaultRouter: (value) => {
    dhcpSetterCalls.setDefaultRouter++;
    if (pool.name === 'serverPool' && config.dhcp_native_gateway_behavior === 'throw') {
      throw new Error('native gateway setter refused');
    }
    if (pool.name === 'serverPool' && config.dhcp_native_gateway_behavior === 'noop') {
      return;
    }
    pool.gateway = String(value);
  },
  setDnsServerIp: (value) => {
    dhcpSetterCalls.setDnsServerIp++;
    if (pool.name === 'serverPool' && config.dhcp_native_dns_behavior === 'throw') {
      throw new Error('native dns setter refused');
    }
    if (pool.name === 'serverPool' && config.dhcp_native_dns_behavior === 'noop') {
      return;
    }
    pool.dns = String(value);
  },
  setStartIp: (value) => {
    dhcpSetterCalls.setStartIp++;
    if (pool.name === 'serverPool' && config.dhcp_native_start_behavior === 'throw') {
      throw new Error('native start setter refused');
    }
    if (pool.name === 'serverPool' && config.dhcp_native_start_behavior === 'noop') {
      return;
    }
    pool.start = String(value);
    if (pool.name === 'serverPool'
        && ['coupled', 'coupled_extra_pool', 'coupled_with_exclusion']
          .includes(config.dhcp_native_start_behavior)) {
      // Exact episode-1 observation, not a claimed general backend algorithm.
      pool.end = '192.0.2.255'; pool.max = 156;
    }
    if (pool.name === 'serverPool'
        && config.dhcp_native_start_behavior === 'coupled_extra_pool') {
      dhcpState(dev).pools.MCP_E6Q_DHCP = {
        name: 'MCP_E6Q_DHCP', network: '192.0.2.0', mask: '255.255.255.0',
        gateway: '192.0.2.1', dns: '192.0.2.10', start: '192.0.2.100',
        end: '192.0.2.100', max: 1, leases: []
      };
    }
    if (pool.name === 'serverPool'
        && config.dhcp_native_start_behavior === 'coupled_with_exclusion') {
      dhcpState(dev).exclusions.push({start: '192.0.2.77', end: '192.0.2.77'});
    }
  },
  setEndIp: (value) => {
    dhcpSetterCalls.setEndIp++; pool.end = String(value);
  },
  setMaxUsers: (value) => {
    dhcpSetterCalls.setMaxUsers++;
    if (pool.name === 'serverPool' && config.dhcp_native_max_behavior === 'throw') {
      throw new Error('native max setter refused');
    }
    if (pool.name === 'serverPool' && config.dhcp_native_max_behavior === 'noop') {
      return;
    }
    pool.max = Number(value);
    if (pool.name === 'serverPool' && config.dhcp_native_max_behavior === 'resize'
        && Number(value) === 1) {
      pool.end = pool.start;
    }
  },
  getLeaseAt: (index) => {
    if (index < pool.leases.length) { return pool.leases[index]; }
    if (config.dhcp_table_end === 'throw') { throw new Error('lease table end'); }
    if (config.dhcp_table_end === 'repeat' && pool.leases.length) {
      return pool.leases[pool.leases.length - 1];
    }
    return null;
  },
});

const dhcpServerProcess = (dev) => {
  const state = dhcpState(dev);
  return {
    isEnable: () => state.enabled,
    setEnable: (value) => {
      dhcpSetterCalls.setEnable++;
      state.enabled = !!value;
      // Enabling the process is process-wide. The stub can be told that the
      // native default moves when it happens, because nothing measured says
      // it does not.
      const drift = value ? config.default_pool_change_on_enable : null;
      if (drift) {
        for (const name of Object.keys(state.pools)) {
          if (name !== 'MCP_E6Q_DHCP') { Object.assign(state.pools[name], drift); }
        }
      }
    },
    getPoolCount: () => {
      if (config.dhcp_pool_count_invalid) { return 'unreadable'; }
      // Autonomous drift: the workspace moves on its own between two
      // readings with no intervention between them. It is a scenario the
      // control observation has to be able to tell from an effect, so the
      // stub can be told to move the default on the Nth inventory read.
      defaultPoolReads += 1;
      const at = config.default_pool_drift_reads;
      if (at && defaultPoolReads === Number(at)) {
        for (const name of Object.keys(state.pools)) {
          if (name !== 'MCP_E6Q_DHCP') { state.pools[name].end = '0.0.7.7'; }
        }
      }
      return Object.keys(state.pools).length;
    },
    getPoolAt: (index) => {
      const name = Object.keys(state.pools).sort()[index];
      return name === undefined ? null : dhcpPool(dev, state.pools[name]);
    },
    getPool: (name) => {
      const pool = state.pools[String(name)];
      return pool ? dhcpPool(dev, pool) : null;
    },
    addPool: (name) => {
      dhcpSetterCalls.addPool++;
      state.pools[String(name)] = {name: String(name), network: '', mask: '',
        gateway: '', dns: '', start: '', end: '', max: 0, leases: []};
    },
    getExcludedAddressCount: () => state.exclusions.length,
    getExcludedAddressAt: (index) => {
      const item = state.exclusions[index];
      return item ? {first: item.start, second: item.end} : null;
    },
    addExcludedAddress: (start, end) => {
      dhcpSetterCalls.addExcludedAddress++;
      if (config.dhcp_native_exclusion_behavior === 'throw_second'
          && dhcpSetterCalls.addExcludedAddress === 2) {
        throw new Error('native second exclusion refused');
      }
      if (config.dhcp_native_exclusion_behavior === 'noop_first'
          && dhcpSetterCalls.addExcludedAddress === 1) {
        return;
      }
      state.exclusions.push({start: String(start), end: String(end)});
      if (config.dhcp_native_exclusion_behavior === 'extra_first'
          && dhcpSetterCalls.addExcludedAddress === 1) {
        state.exclusions.push({start: '192.0.2.77', end: '192.0.2.77'});
      }
    },
  };
};

const emitDhcp = (port, eventName, args) => {
  if (!config.dhcp_emit_events) { return; }
  const event = {uuid: port.uuid, className: 'HostPort', event: eventName, args: args};
  if (config.deliver_events === 'sync') { deliver(event); }
  else if (config.deliver_events === 'after_eval') { pending.push(event); }
};

// The next free address of one pool: inside its range, not its network
// address, not held by another lease and not configured on any port.
const nextFree = (pool) => {
  const used = new Set(pool.leases.map((row) => row.ipAddress));
  for (const d of devices) { for (const p of d.ports) { if (p.ip) { used.add(p.ip); } } }
  for (let value = ipToInt(pool.start); value <= ipToInt(pool.end); value += 1) {
    const address = intToIp(value);
    if (address !== pool.network && !used.has(address)) { return address; }
  }
  return '';
};

const acquire = (dev, port) => {
  const server = devices.find((item) => item.model === 'Server-PT' && item.dhcpServer);
  const state = server ? dhcpState(server) : null;
  // Which pool a native server answers from is unqualified, so the stub
  // never hard-codes the intended one: the selection is configured.
  const names = state ? Object.keys(state.pools).sort() : [];
  const other = names.filter((name) => name !== 'MCP_E6Q_DHCP')[0];
  const order = config.dhcp_pool_selection === 'intended'
    ? ['MCP_E6Q_DHCP']
    : (config.dhcp_pool_selection === 'default'
      ? [other]
      : (config.dhcp_pool_selection === 'intended_then_default'
        ? ['MCP_E6Q_DHCP', other] : [names[0]]));
  for (const chosen of order) {
    const pool = state && chosen ? state.pools[chosen] : null;
    if (!state || !state.enabled || !pool) { continue; }
    const existing = pool.leases.find((row) => row.macAddress === port.mac);
    if (!existing && pool.leases.length >= pool.max) { continue; }
    const leaseAddress = existing ? existing.ipAddress : nextFree(pool);
    if (!leaseAddress) { continue; }
    const address = config.dhcp_client_address_override || leaseAddress;
    const row = existing || {ipAddress: leaseAddress, macAddress: port.mac,
      leaseTime: 3600, port: port.name};
    if (!existing) { pool.leases.push(row); }
    port.ip = address; port.mask = pool.mask; port.leaseTime = config.dhcp_lease_time;
    emitDhcp(port, 'dhcpSucceed', {deviceName: dev.name, portName: port.name,
      newip: port.ip, newmask: port.mask});
    return true;
  }
  if (config.dhcp_failure_address) {
    port.ip = config.dhcp_failure_address; port.mask = '255.255.0.0';
  }
  emitDhcp(port, 'dhcpFailed', {deviceName: dev.name, portName: port.name});
  return false;
};

const dhcpClientProcess = (dev) => ({
  dhcpRun: (portName) => {
    if (config.dhcp_acquire_throws) { throw new Error('dhcp acquisition failed'); }
    const port = dev.ports.find((item) => item.name === String(portName));
    dhcpRuns.push({device: dev.name, port: String(portName)});
    if (!port) { throw new Error('dhcp client port missing'); }
    acquire(dev, port);
  },
  getDataOfPort: (portName) => {
    const port = dev.ports.find((item) => item.name === String(portName));
    if (!port) { return null; }
    return {getLeaseTimeStr: () => {
      if (!config.dhcp_lease_time_ticks || !port.leaseTime) { return port.leaseTime; }
      port.leaseReads = (port.leaseReads || 0) + 1;
      return `${port.leaseTime} #${port.leaseReads}`;
    }};
  },
});

const processFor = (dev, name) => {
  if (name === 'HttpBackgroundClientManager' && dev.model !== '2960-24TT') {
    return {
      createClient: () => makeClient(dev),
      // A release the engine refuses leaves an owned client behind,
      // which is an unresolved effect and not a clean exit.
      deleteClient: (client) => {
        if (config.delete_client_throws) { throw new Error('delete refused'); }
        if (config.delete_client_inert) { return; }
        if (client && client.id) { delete clients[client.id]; }
      },
    };
  }
  if (name === 'DnsClient' && dev.model !== '2960-24TT') {
    return {getServerIp: () => (dev.ports[0] && dev.ports[0].dns) || config.unset_dns};
  }
  if (dev.model === 'Server-PT' && name === 'HttpServer') { return httpServer(dev); }
  if (dev.model === 'Server-PT' && name === 'HttpsServer') { return httpsServer(dev); }
  if (dev.model === 'Server-PT' && name === 'DhcpServerMain') {
    return {getDhcpServerProcessByPortName: (portName) => (
      dev.ports.some((port) => port.name === String(portName))
        ? dhcpServerProcess(dev) : null
    )};
  }
  if (dev.model === 'PC-PT' && name === 'DhcpClient') {
    return dhcpClientProcess(dev);
  }
  return null;
};

// -- terminal ---------------------------------------------------------------
//
// One transcript per device, appended to by `enterCommand` exactly as Packet
// Tracer's own TerminalLine does: the echoed command, the response, and the
// prompt the session returns to. The real IOS executor and the real typed
// ping run against this, so their dispatch, freshness, echo, attribution and
// parsing contracts execute here instead of being mocked away.
//
// `stp_rows` maps a switch interface to its reported spanning-tree state;
// `stp_extra_rows` adds rows that name the SAME interface again, which is the
// ambiguity the admission rule has to refuse. `ping_reachable` selects the PC
// statistic line, and `terminal_commands` counts what was typed.
const SHORT_INTERFACE = (name) => String(name)
  .replace(/^FastEthernet/, 'Fa')
  .replace(/^GigabitEthernet/, 'Gi');
const terminalCommands = [];

const stpBlock = () => {
  const vlan = Number(config.stp_vlan || 1);
  const rows = Object.assign({}, config.stp_rows || {});
  const extra = (config.stp_extra_rows || []);
  const lines = [
    'VLAN' + String(vlan).padStart(4, '0'),
    '  Spanning tree enabled protocol ieee',
    '  Root ID    Priority    32769',
    '             Address     0001.0203.0405',
    '             This bridge is the root',
    '             Hello Time 2 sec  Max Age 20 sec  Forward Delay ' +
      String(config.stp_forward_delay || 15) + ' sec',
    '',
    '  Bridge ID  Priority    32769  (priority 32768 sys-id-ext 1)',
    '             Address     0001.0203.0405',
    '             Hello Time 2 sec  Max Age 20 sec  Forward Delay ' +
      String(config.stp_forward_delay || 15) + ' sec',
    '             Aging Time 20',
    '',
    'Interface        Role Sts Cost      Prio.Nbr Type',
    '---------------- ---- --- --------- -------- ------------------------',
  ];
  const row = (iface, state) => SHORT_INTERFACE(iface).padEnd(16, ' ') +
    ' Desg ' + String(state) + ' 19        128.1    P2p';
  for (const iface of Object.keys(rows)) { lines.push(row(iface, rows[iface])); }
  for (const item of extra) { lines.push(row(item[0], item[1])); }
  lines.push('');
  return lines.join('\n') + '\n';
};

const pingBlock = (target) => {
  const sent = 4;
  const received = config.ping_reachable ? 4 : 0;
  return [
    'Pinging ' + target + ' with 32 bytes of data:',
    '',
    'Ping statistics for ' + target + ':',
    '    Packets: Sent = ' + sent + ', Received = ' + received +
      ', Lost = ' + (sent - received) + ' (' +
      Math.round(((sent - received) / sent) * 100) + '% loss),',
    '',
  ].join('\n') + '\n';
};

const terminalRespond = (dev, command) => {
  const text = String(command).trim();
  terminalCommands.push({device: dev.name, command: text});
  if (text === '') { return ''; }
  if (/^ping\s+\S+$/.test(text)) {
    if (config.ping_unsupported) { return '% Invalid input detected.\n'; }
    return pingBlock(text.split(/\s+/)[1]);
  }
  if (text === 'show spanning-tree') {
    if (config.stp_unsupported) { return '% Invalid input detected.\n'; }
    return stpBlock();
  }
  return '% Invalid input detected at \'^\' marker.\n';
};

const makeTerminal = (dev) => {
  if (!dev.terminal) {
    const prompt = dev.model === '2960-24TT' ? 'Switch>' : 'C:\\>';
    const state = {prompt: prompt, output: prompt};
    state.pending = '';
    state.pendingReads = 0;
    state.api = {
      getPrompt: () => state.prompt,
      // A real terminal renders while the caller polls. Releasing the
      // response after N reads is what turns one inspection into the
      // several that a slow command actually costs.
      getOutput: () => {
        if (state.pendingReads > 0) {
          state.pendingReads -= 1;
          if (state.pendingReads === 0) {
            state.output += state.pending;
            state.pending = '';
          }
        }
        return state.output;
      },
      enterCommand: (command) => {
        if (config.terminal_refuses) { throw new Error('terminal refused'); }
        const response = terminalRespond(dev, command) + state.prompt;
        const delay = Number(config.terminal_response_delay_reads || 0);
        state.output += String(command) + '\n';
        if (delay > 0) {
          state.pending = response;
          state.pendingReads = delay;
        } else {
          state.output += response;
        }
        return true;
      },
    };
    dev.terminal = state;
  }
  return dev.terminal.api;
};

const makeDevice = (name, model) => {
  const dev = {name: String(name), model: String(model), ports: [], web: null,
    dhcpServer: null, terminal: null};
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
    setDhcpFlag: (v) => {
      dhcpSetterCalls.setDhcpFlag++;
      dev.dhcp = !!v;
      for (const port of dev.ports) { port.dhcpMode = !!v; }
    },
    getProcess: (value) => processFor(dev, String(value)),
  };
  if (config.terminals) {
    // A switch answers on `getCommandLine`, an endpoint on
    // `getCommandPrompt`: the resolver order of the production readers is
    // exactly what distinguishes them, so the stub keeps them apart.
    if (dev.model === '2960-24TT') {
      api.getCommandLine = () => makeTerminal(dev);
    } else {
      api.getCommandPrompt = () => makeTerminal(dev);
    }
  }
  dev.api = api;
  for (const portName of PORTS[dev.model] || []) {
    const port = {name: portName, link: null, ip: '', mask: '', dns: '',
      uuid: newUuid(), dhcpMode: false,
      mac: ('0000.0000.' + String(uuidSeq).padStart(4, '0')).slice(-14),
      leaseTime: ''};
    port.api = {
      getName: () => port.name,
      getOwnerDevice: () => api,
      getLink: () => (port.link ? port.link.api : null),
      isPortUp: () => {
        readinessCalls.portUp++;
        if (config.port_up_return !== 'boolean') {
          return NON_BOOLEAN[config.port_up_return];
        }
        if (readinessCalls.portUp <= config.ports_down_calls) { return false; }
        return !!port.link && !!config.ports_up;
      },
      isProtocolUp: () => {
        readinessCalls.protocolUp++;
        if (config.protocol_up_return !== 'boolean') {
          return NON_BOOLEAN[config.protocol_up_return];
        }
        if (readinessCalls.protocolUp <= config.ports_down_calls) { return false; }
        return !!port.link && !!config.protocol_up;
      },
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
      isDhcpClientOn: () => port.dhcpMode,
      getMacAddress: () => port.mac,
      // Cisco documents `eOffLight = 0, eAmberLight = 1, eGreenLight = 2,
      // eBlink = 3`. `light_status_return` answers with something that is not
      // a number so the strict reading can be exercised too.
      getLightStatus: () => {
        if (config.light_status_return !== 'number') {
          return NON_BOOLEAN[config.light_status_return];
        }
        return port.link ? config.light_status : 0;
      },
    };
    if (dev.model !== '2960-24TT') {
      port.api.getIpAddress = () => port.ip;
      port.api.getSubnetMask = () => port.mask;
    }
    dev.ports.push(port);
  }
  return dev;
};

const removeCalls = [];
const removeDevice = (name) => {
  removeCalls.push(String(name));
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
  simulation: () => ({
    isSimulationMode: () => false,
    getFrameInstanceCount: () => Number(config.simulation_frames || 0),
    getCurrentSimTime: () => Number(config.simulation_time || 0),
    getCurrentFrameInstanceIndex: () => 0,
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
  const dev = findDevice(String(name));
  if (dhcp) { dhcpSetterCalls.configurePcIpDhcp++; }
  port.dhcpMode = !!dhcp;
  if (ip && mask) {
    port.ip = String(ip); port.mask = String(mask);
    staticAddresses.push({device: String(name), ip: port.ip});
  }
  if (dns) { port.dns = String(dns); }
  if (ip && mask && dev && dev.model === 'Server-PT' && config.default_pool_realigns_on_address) {
    const state = dhcpState(dev);
    if (config.dhcp_enable_on_server_address) { state.enabled = true; }
    const network = intToIp(ipToInt(ip) - (ipToInt(ip) % (4294967296 - ipToInt(mask))));
    for (const poolName of Object.keys(state.pools)) {
      if (poolName === 'MCP_E6Q_DHCP') { continue; }
      const pool = state.pools[poolName];
      pool.network = network; pool.mask = String(mask); pool.start = network;
      pool.end = intToIp(ipToInt(network) + Number(pool.max) - 1);
    }
  }
  if (dhcp && dev && config.dhcp_mode_acquires) {
    backgroundAcquisitions.push({device: dev.name, port: port.name});
    acquire(dev, port);
  }
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
  const dhcpServers = {};
  for (const d of devices) {
    if (d.web) {
      servers[d.name] = {http_enabled: d.web.httpEnabled, https_enabled: d.web.httpsEnabled,
        http_pages: Object.keys(d.web.tables.http), https_pages: Object.keys(d.web.tables.https)};
    }
    if (d.dhcpServer) {
      dhcpServers[d.name] = {enabled: d.dhcpServer.enabled,
        exclusions: d.dhcpServer.exclusions.slice(),
        pools: Object.fromEntries(Object.entries(d.dhcpServer.pools).map(
          ([name, pool]) => [name, Object.assign({}, pool, {leases: pool.leases.slice()})]
        ))};
    }
  }
  return {
    devices: devices.map((d) => ({name: d.name, model: d.model,
      ports: d.ports.filter((p) => p.ip || p.dns || p.link)
        .map((p) => ({name: p.name, ip: p.ip, mask: p.mask, dns: p.dns,
          mac: p.mac, dhcp_mode: p.dhcpMode, lease_time: p.leaseTime,
          linked: !!p.link}))})),
    links: links.length,
    run_bags: runs,
    registrations: registrations.map((r) => ({device: r.device, event: r.event,
      active: r.active})),
    unregister_calls: unregisterCalls.slice(),
    servers: servers,
    dhcp_servers: dhcpServers,
    dhcp_runs: dhcpRuns.slice(),
    background_acquisitions: backgroundAcquisitions.slice(),
    static_addresses: staticAddresses.slice(),
    dhcp_setter_calls: Object.assign({}, dhcpSetterCalls),
    terminal_commands: terminalCommands.slice(),
    remove_calls: removeCalls.slice(),
    terminals: Object.fromEntries(devices.filter((d) => d.terminal)
      .map((d) => [d.name, d.terminal.output])),
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
    if (config.drop_product_claims_after_eval) { delete globalThis.__mcpE6Claims; }
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
SIM_PROCESS_ID = 4242
SIM_PROCESS_PATH = r"C:\Program Files\Cisco Packet Tracer\bin\PacketTracer.exe"
#: One simulated process incarnation. A PID names a slot the operating
#: system reuses, so the pairing binds the creation identity too.
SIM_PROCESS_INCARNATION = "2026-09-20T09:15:00.0000000+00:00"


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

    def attempt_exists(self, attempt_id: str) -> bool:
        """Answer the real store's uniqueness question, unchanged."""
        self.writes.append("attempt_exists")
        return self.inner.attempt_exists(attempt_id)


#: The forwarding states a coherent access fixture reports for the three
#: switch-side ports both diagnostics link.
FORWARDING_ROWS = {
    "FastEthernet0/1": "FWD",
    "FastEthernet0/2": "FWD",
    "FastEthernet0/3": "FWD",
}


class MilestoneTransport:
    """One mailbox answered by one engine, then by whatever a milestone picks.

    `when(script)` is asked about each dispatched command. The first script it
    accepts is a transport milestone: `before` runs immediately ahead of that
    command and `after` immediately behind it, so a test places a receiver
    replacement at a point the RUN reaches -- the first `removeDevice`, a
    fixture creation, the cleanup pre-readback -- instead of at a count of
    authority callbacks. Counting those callbacks would place the injection
    inside the very control under test, and would move every time the control
    asks one more question.
    """

    def __init__(self, target, *, when=None, before=None, after=None) -> None:
        """Start on the engine the run was admitted against."""
        self.target = target
        self.when = when
        self._before = before
        self._after = after
        self.fired = False
        self.calls: list[tuple[str, str]] = []

    def _reached(self, js_code: str) -> None:
        if self.fired or self.when is None or not self.when(js_code):
            return
        self.fired = True
        if self._before is not None:
            self._before()

    def _passed(self) -> None:
        if self.fired and self._after is not None:
            hook, self._after = self._after, None
            hook()

    def send(self, js_code: str) -> bool:
        """Queue one command on whichever engine answers now."""
        self.calls.append(("send", js_code))
        self._reached(js_code)
        try:
            return self.target.send(js_code)
        finally:
            self._passed()

    def send_and_wait(self, js_code: str, timeout: float) -> str | None:
        """Dispatch one command on whichever engine answers now."""
        self.calls.append(("send_and_wait", js_code))
        self._reached(js_code)
        try:
            return self.target.send_and_wait(js_code, timeout)
        finally:
            self._passed()

    def dispatch_and_wait(self, js_code: str, timeout: float):
        """Dispatch with typed facts on whichever engine answers now."""
        self.calls.append(("dispatch_and_wait", js_code))
        self._reached(js_code)
        try:
            return self.target.dispatch_and_wait(js_code, timeout)
        finally:
            self._passed()


class SwitchableLifecycle:
    """Local pairing readings that change only when a milestone says so.

    Nothing here counts how often the run asks. The reading changes because
    the run reached a transport milestone, which is what a Packet Tracer that
    is replaced mid-run actually looks like to this process.
    """

    def __init__(self, first, later=None) -> None:
        """Answer `first` until `switch()`, then `later`."""
        self.first = first
        self.later = later if later is not None else first
        self.switched = False
        self.calls = 0

    def switch(self) -> None:
        """Start answering as the replacement instance."""
        self.switched = True

    def __call__(self, _deadline: float | None = None):
        """Return whichever pairing this instant has."""
        self.calls += 1
        return self.later if self.switched else self.first


class DiagnosticStageRun:
    """One stub engine, one transport and one completed stage invocation."""

    def __init__(self, directory: Path, stage: str, engine_config, **overrides):
        """Run the stage through the real CLI and keep everything it produced."""
        self.directory = directory
        config = {
            "terminals": True,
            "ping_reachable": True,
            "stp_rows": dict(FORWARDING_ROWS),
            "dhcp_default_pool": "native",
        }
        config.update(engine_config or {})
        wrap = overrides.pop("wrap_transport", None)
        self.engine = NodeEngine(directory, **config)
        self.transport: Any = NodeEngineTransport(self.engine)
        if wrap is not None:
            # The channel the run is handed, so a test can place a milestone
            # on it before the first command instead of after the fact.
            self.transport = wrap(self.transport)
        self.clock = FakeClock()
        self.opened: list[str] = []
        self.argv = overrides.pop("argv", None)
        self.boundaries = self._boundaries(**overrides)
        self.exit_code: int | None = None
        self.summary: dict = {}

    def _boundaries(self, **overrides):
        from packet_tracer_mcp.application.ports.service_qualification import (
            OpenedTransport,
        )

        def open_transport(channel: str):
            self.opened.append(channel)
            return OpenedTransport(channel, self.transport, True, "stub_engine")

        values = {"open_transport": open_transport, "clock": self.clock}
        values.update(overrides)
        return simulated_boundaries(self.directory, self.transport, **values)

    def run(self, argv) -> int:
        """Invoke the adapter exactly as an operator would."""
        from packet_tracer_mcp.adapters.cli.service_qualification import main

        self.exit_code = main(
            argv,
            environ={"PT_MCP_GOVERNED_ROOT": str(self.directory)},
            boundaries_factory=lambda root: self.boundaries,
        )
        return self.exit_code

    def record(self):
        """Return the record exactly as the store wrote it last."""
        from packet_tracer_mcp.domain.enterprise.models.service_qualification import (
            QualificationRecord,
        )

        (path,) = list((self.directory / "records").rglob("*.json"))
        return QualificationRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def scripts(self, needle: str) -> list[str]:
        """Return every dispatched script containing `needle`."""
        return [script for _kind, script in self.transport.calls if needle in script]

    def measurement(self, experiment_id: str):
        """Return one measurement of the stored record."""
        return next(
            item
            for item in self.record().measurements
            if item.experiment_id == experiment_id
        )

    def close(self) -> None:
        """Stop the engine process."""
        self.engine.close()


@pytest.fixture
def stage(tmp_path, capsys):
    """Yield a factory that runs one stage and cleans up its engine."""
    started: list[DiagnosticStageRun] = []

    def make(stage_name: str, engine_config=None, *, argv=None, **overrides):
        directory = tmp_path / f"{stage_name}{len(started)}"
        directory.mkdir()
        item = DiagnosticStageRun(directory, stage_name, engine_config, **overrides)
        started.append(item)
        item.run(
            argv
            if argv is not None
            else request_args(stage_name) + authorization_args(stage_name)
        )
        printed = capsys.readouterr().out.strip().splitlines()
        item.summary = json.loads(printed[-1]) if printed else {}
        return item

    yield make
    for item in started:
        item.close()


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
        DiagnosticLifecycleObservation,
        ExecutionMode,
        RepositoryIdentity,
    )
    from packet_tracer_mcp.infrastructure.persistence.campaign_coordination import (
        FileCampaignCoordinator,
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
        "diagnostic_lifecycle": lambda _deadline=None: DiagnosticLifecycleObservation(
            process_id=SIM_PROCESS_ID,
            process_path=SIM_PROCESS_PATH,
            product_version=SIM_BUILD,
            process_incarnation=SIM_PROCESS_INCARNATION,
        ),
        # The production coordinator claims beside the operator's real
        # mailbox. A simulation gets its own scope under the test
        # directory so it can never take or release that claim.
        "campaign_coordinator": FileCampaignCoordinator(directory / "campaign"),
    }
    values.update(overrides)
    return dataclasses.replace(production_boundaries(directory), **values)


#: One fresh instance token, plus a distinct attempt identity per stage. The
#: repository boundary reports `SIM_TREE`, and a diagnostic authorization
#: binds it, so the two values have to agree here too.
SIM_INSTANCE_TOKEN = "1" * 32


def _attempt_id(stage: str) -> str:
    """Return a stable, distinct attempt identity for one simulated stage."""
    import hashlib

    return hashlib.sha256(stage.encode("utf-8")).hexdigest()[:32]


def authorization_args(
    stage: str = "Q0",
    *,
    sha: str = SIM_SHA,
    channel: str = "file",
    build: str = SIM_BUILD,
    targets: tuple[str, ...] | None = None,
    operations: str | None = None,
    seconds: str | None = None,
    tree: str = SIM_TREE,
    steps: tuple[str, ...] | None = None,
    attempt_id: str | None = None,
) -> list[str]:
    """Return a complete, matching authorization for one stage as CLI arguments.

    A stage that declares a diagnostic profile also gets its identity half:
    profile, tree, fixture models, link ports, ordered steps, cleanup reserve,
    instance token and attempt identity. A stage that declares none gets
    exactly what it always got.
    """
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
    if definition.profile_id:
        args += [
            "--authorized-profile",
            definition.profile_id,
            "--authorized-profile-version",
            definition.profile_version,
            "--authorized-tree",
            tree,
            "--authorized-reserve-operations",
            str(definition.reserve_operations),
            "--instance-token",
            SIM_INSTANCE_TOKEN,
            "--authorized-process-id",
            str(SIM_PROCESS_ID),
            "--authorized-process-path",
            SIM_PROCESS_PATH,
            "--attempt-id",
            attempt_id or _attempt_id(stage),
        ]
        for model in definition.fixture_models:
            args += ["--authorized-model", model]
        for link in definition.link_bindings:
            args += ["--authorized-link", link]
        for step in steps if steps is not None else definition.step_ids:
            args += ["--authorized-step", step]
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
