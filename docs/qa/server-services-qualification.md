# Server-PT services qualification (Q stages)

This page is the operator-facing template for staged Packet Tracer
qualification. It holds **no authorization by itself**. Historical Q0/Q1
records remain archived and attributed to their executed SHA. This page holds
no LIVE result and promotes no capability. Q3's three consumed attempts are
recorded in the Server-PT services brief, and Q3-FL-C1 episode 1 in the
[DHCP fast-loop brief](../engineering/change-briefs/server-pt-dhcp-fastloop.md).

The design, contracts and oracles are in section 12 of the
[Server-PT services brief](../engineering/change-briefs/server-pt-services.md).
The runner is `packet_tracer_mcp.adapters.cli.service_qualification`, and its
use case is `application/use_cases/qualify_server_services.py`.

## What a stage is, and what it is not

A qualification stage is a separately authorized experiment on Packet Tracer
itself. It creates its own `__MCP_E6Q_*` fixtures in an empty workspace,
measures one bounded set of engine or HTTPS facts, removes what it created, and
reads the workspace twice. It is not a product operation, and it never runs on
an operator's topology. A stage only starts from an observed empty workspace.
If a foreign device or link is present, the run refuses; the runner never clears
the workspace and never opens a different project.

A completed stage record supports its sample on one channel, one build and one
executed SHA. It is never relabeled as another SHA's measurement, it never
authorizes the other channel, and an `offline_simulation` record can never
qualify anything.

## Stage matrix

| Stage | Current runner state | Fixtures | Ceiling | Planned worst case | Measurements |
| --- | --- | --- | --- | --- | --- |
| Q0 | executable | `__MCP_E6Q_PC1` (PC-PT) | 20 operations / 300 s | 19 | M-ENG-1, ATOM-1, M-UNREG-1, M-UNREG-2 (M-HTTP-1 omitted: no HTTP server in the fixture) |
| Q1 | executable | `__MCP_E6Q_SRV`, `__MCP_E6Q_PC1`, `__MCP_E6Q_PC2`, `__MCP_E6Q_SW` | 60 operations / 600 s | 56 | M-HTTPS-1, M-HTTPS-2 (M-DNS-1/2 omitted: optional, no reviewed probe; M-DNS-3 omitted: already measured at `0850de3`) |
| Q2 | declarative only | none | 60 / 900 s | not planned | requires S2 and a Q0 record |
| Q3 | executable; file channel only on build 9.0.1.0858 | Server-PT `192.0.2.10/24`, two DHCP PC-PT clients, 2960-24TT on exact Fa0/1..3 links | 60 / 1200 s | 59 (17 setup + 31 measurement/application + 11 reserve) | M-DHCP-1, 2, 4, 5, 6; one-address pool `MCP_E6Q_DHCP`; guarded acquisitions (M-DHCP-3 omitted: the event source and its release are not qualified) |
| D-DHCP | executable diagnostic; file channel only on build 9.0.1.0858 | the Q3 fixture, with no client ever activated | 50 / 900 s | 45 (17 setup + 17 measurement + 11 reserve) | M-DDHCP-0..4: the disabled baseline with its drift control, the server's static addressing alone, the intended pool while still disabled, the enable, the pre-cleanup reading |
| D-WEB | executable diagnostic; file channel only on build 9.0.1.0858 | the Q1 fixture, statically addressed | 80 / 900 s | 74 (19 setup + 45 measurement + 10 reserve) | M-DWEB-0..5: the listener and endpoint boundaries, the per-VLAN forwarding state of the exact switch ports, the marked page, one attributed ping, one instrumented fetch, the same boundaries again |
| Q3-FL-C1 | executable only under campaign `SERVER-PT-DHCP-FASTLOOP-01`; file channel, build 9.0.1.0858 | the Q3 fixture | 440 / 1500 s | 439 (17 setup + 411 measurement + 11 reserve; 362 of it is the gate's two capped forwarding episodes) | M-DHCP-1, 2, 4, 5, 6, 6-CAP, 6-REPEAT, 6-TIME, 1-FINAL on a one-user intended pool (M-DHCP-3 and 6-RENEW omitted with their reasons) |
| Q3-FL-C2 | as Q3-FL-C1 | the Q3 fixture | 440 / 1500 s | 439 | the same on a two-user intended pool, so one row and a full table differ (6-CAP omitted: it needs a one-user pool) |

The two `D-` stages are **diagnostics**: each asks an open question and
measures a boundary or a transition. What they observe confirms no product
capability and learns no allowlist from it. They bind a second half of the
authority that the Q stages do not; the
[Goal contract](server-services-goal-contract.md) holds it, together with the
per-stage budget arithmetic and the ungranted authorization templates.

The planned figure is the stage's **bounded worst case**, not its luckiest
trace: every production fetch is budgeted at its start, both inspections and
the release of its owned client. A stage whose worst case exceeds its ceiling
is refused before contact, with the arithmetic in the refusal.

Q1's 60 / 600 is the reviewed design ceiling. The amended procedure's worst
case is 56 with the 10-operation finalization reserve intact: the readiness
gate's four aggregate reads are charged to the trace rather than to unlogged
preparation. It authorizes no LIVE run, and it changes neither Q0's 20 / 300
nor declarative Q2. The runner never raises a ceiling by itself.

The two `Q3-FL` stages are the versioned experimental Q3 profile of the
[DHCP fast-loop brief](../engineering/change-briefs/server-pt-dhcp-fastloop.md).
They are not a renewal of Q3's 60 / 1200 bound or of its three consumed
attempts. They run only through the qualification CLI's campaign composition:
`--campaign dhcp-fastloop --charter <work order> --episode <n>`, with the
attempt's `--record-launch` record, an open ledger episode at the exact
checkpoint, and the full diagnostic identity (profile `Q3-FL` version 1, tree,
models, links, steps, reserve, process, instance token and attempt). Without
the campaign the CLI refuses them (`stage_requires_its_campaign`). The campaign
waives exactly one rule, publication of the executed HEAD, for exactly that
attempt. Its record is archived in the campaign store by digest, and
retirement goes through `server_pt_commissioning --campaign dhcp-fastloop
--retire`, which never forces.

## Readiness before any network attempt

Both executable network stages share one bounded readiness check over the
exact six fixture ports. It keeps the raw typed `found`, `linked`, `port_up`
and `protocol_up` with the port and device identity, and a value counts as a
boolean only when the engine returned `typeof "boolean"` -- missing, invalid
and `false` stay three different observations, which `!!` used to collapse
into one. A network attempt is admitted only from a fresh complete reading in
which all four are true on every port.

The gate spends at most four aggregate reads inside a 30-second monotonic
window, itself capped by the stage's unspent time and its untouchable
finalization reserve, and stops at the first complete ready sample. Each read
receives the smaller of the probe's normal timeout, the local deadline
remainder and the stage allowance. A sample returned after the local deadline
is retained but grants no permission. Nothing sleeps unconditionally and
nothing spins. The record keeps the read count, elapsed time, first and last
samples and the precise failure reason.

These fields prove readiness of the measured links at the moment they were
read. They prove nothing about STP forwarding, reachability or a successful
request. A gate that never becomes ready is a readiness result: Q1 writes no
marked page and starts no fetch; Q3 performs no `SetEndpointDhcp`, server
setter or acquisition. Both stages finalize, and neither records a service
verdict from the readiness result.

Q3's recalculated exact worst case is 59 operations: 17 admission/fixture
operations, 31 product/native measurement operations and an untouchable
11-operation reserve for the run bag, four owned removals and two restoration
reads. The one operation below the 60-operation ceiling is not a retry
entitlement. The product path is compiled through the real E4/E5/E6
composition with a private candidate capability copy. It applies server setup
once through the service applicator, retains those exact typed action rows for
the full plan and performs fresh read-only verification without rescheduling
the setup setters. The public catalog stays UNKNOWN/UNMEASURED.

The fixture has no router. Gateway option `192.0.2.1` and DNS option
`192.0.2.10` are stored DHCP options, not reachability or DNS-service evidence.
The pool has one usable address, `192.0.2.100`. Each client action runs once
under its product claim, and the declared same-action control must refuse
without another `dhcpRun`.

Q3 classifies the complete E5 result and the foundations derived from it before
any E6 server mutation, and a contradicted product read-back blocks the
same-claim guard control just as an unknown effect does. Missing rows, unknown
dispatch, exceptions and contradicted foundations grant no permission.

## The native default pool Q3 coexists with

Stock Server-PT on build 9.0.1.0858 ships one DHCP pool, and the LIVE Q3
ordinal-2 record measured it exactly: `serverPool`, network, mask, gateway,
DNS and start all `0.0.0.0`, end `0.0.2.0`, 512 users. Q3 admits two baselines
and nothing else: a coherently observed empty inventory under a disabled
process, or exactly that one row under a disabled process. Both also require
the owned newly created Server-PT by name, exact `FastEthernet0`, an actual
boolean `enabled=false`, a complete untruncated inventory, no error and no
`MCP_E6Q_DHCP` already present. Every field is compared by value and by type,
so a pool that only shares the name is refused, and the reviewed build and the
permitted channel come from the composition rather than from the domain.

`serverPool` is never deleted, renamed, reset, replaced, per-pool disabled or
worked around. It is read three times with bounded reads -- before E5, after
setup and before cleanup -- and every snapshot and every difference between
them stays in the record. A default that moved stops the effects that would
have followed it. Enabling the DHCP process is process-wide, so the authorized
experiment may also activate the native pool's behavior; nothing here says the
default stays inert afterwards, and nothing infers that its range or its zero
mask is harmless. Two pools in one process are not two independent DHCP
servers, and which one a native server allocates from is unqualified.

M-DHCP-2 records bounded empty and capacity-one table samples. Null, throw,
repeat and bound termination remain sample facts; none is generalized into a
lease-count API, table completion or pool exhaustion. There is no qualified
end-of-table predicate, so the default pool's lease table is never required or
claimed to be empty. M-DHCP-6 uses fixed observation windows without clock or
lease manipulation, so absent natural renewal remains INCONCLUSIVE.

M-DHCP-3 is **OMITTED / NOT_EVALUATED** in this profile, reason
`qualification_event_source_and_release_not_qualified`. It is not marked
supported and it is not silently removed: no observer is registered or
unregistered, and a regression proves the profile dispatches zero
`registerEvent` calls. The registration subscribes on the port while Cisco
documents `dhcpSucceed`/`dhcpFailed` on `DhcpClientProcess`, and an unregister
attempt that merely did not throw is not observed detachment. The allowance it
held is spent on readiness and on preserving the observed default, never on
another acquisition. R-EVT-05 production gating is unchanged, and the
deferral ends only with a separately reviewed event change that fixes source
identity, correlation and release evidence.

M-DNS-3 is declared OMITTED rather than run again. The Q1-file run at
`0850de3` recorded `DnsClient.getServerIp` for its exact reader, model, build
and channel; nothing in the repaired stage depends on that reading, and a
second run would produce a second sample attributed to its own SHA, never
further support for the first. The probe and its rule stay in the runner for a
future authorized measurement.

M-HTTPS-1 also states what happened to its own effect, as `page_effect`. The
probe sets `written` only after `setPageContents` returns, and the setter can
change `index.html` and then throw, so a caught exception is not evidence that
nothing happened. `not_attempted` means the probe's guard stopped before the
setter; `reconciled` means a setter ran and both handles were read completely
afterwards; `unresolved` means a setter may have run with no complete read
after it. Only `unresolved` ends the experimental phase, leaving the owned
finalization and persistence to complete. Deciding nothing about shared versus
separate tables is a conclusion about the subject and stops nothing.

M-HTTPS-1 writes only the existing `index.html` of the owned server, with
run-specific content: Cisco documents setting a page's contents, not creating
one, and the `0850de3` record measured `File not exist` for two newly named
pages. Each write is bracketed by a complete read through both handles and
followed by an independent read; a failed, empty or truncated read, an
exception or a mixed result is INCONCLUSIVE, never a separate table.

M-HTTPS-2 cannot be SUPPORTED with the readers this build has. Its model says a
listener *fails* when it is disabled, and the web reader reports a refused
request exactly as it reports a slow or lost one -- `no_response_within_deadline`
-- while fresh non-marker content proves a marker mismatch rather than a
refusal. A negative control can therefore contradict the model (the marker was
retrieved while the listener read back as disabled) but never establish it.
The readiness gate runs before the first positive; each negative then runs only
after a working positive in its own mode (an HTTP-mode fetch with both
listeners enabled, then HTTPS-only); a failed positive leaves its negatives
unrun and spends one read of listener flags and fixture-port readiness instead. The record names what no documented reader provides: the
client's request URL, the HTTP reader's mode, and a switch port's STP state.
The measurement records its observations and stays INCONCLUSIVE.

**Counting unit.** One operation is one command dispatched to the engine
through the fixed transport (`send`, `send_and_wait` or `dispatch_and_wait`),
whatever its result. This includes the admission reads, fixture setup,
experiment dispatch and polling, and finalization, and it counts the calls
that production runtimes make internally. Local liveness checks (webview poll
recency, file heartbeat age) execute nothing in the engine and are not
counted. The finalization reserve (owned cleanup and the two restoration
reads) is set before the first effect and is never spent on experiments.

## Authorization template

A reviewer fills in every field below for exactly one stage and one channel.
The runner compares each field exactly and refuses on any missing, malformed,
mismatched or unobservable value.

| Field | Runner argument | Rule |
| --- | --- | --- |
| Authorization identity | `--authorization-id` | printable, at most 128 characters; recorded in the stage record |
| Stage | `--authorized-stage` and `--stage` | one of Q0..Q3, `D-DHCP` or `D-WEB`; Q2 and an infeasible stage refuse. A `D-` stage binds the further fields in the [Goal contract](server-services-goal-contract.md) |
| Executed SHA | `--authorized-sha` and `--expected-head` | 40 lowercase hex; equal to each other, to observed `HEAD`, and to its published upstream; clean worktree |
| Fixture targets | `--authorized-target` and `--target` (repeat) | exactly the stage fixtures, no duplicates |
| Channel | `--authorized-channel` and `--channel` | `http` or `file`; one per authorization, fixed for the whole run; Q3 accepts only `file` |
| Build | `--authorized-build` and `--packet-tracer-build` | one exact four-component build; must equal `AppWindow.getVersion()`; Q3 is fixed to `9.0.1.0858` |
| Budget | `--authorized-max-operations`, `--authorized-max-seconds` | exactly the stage ceiling |
| Explicit execution | `--execute` | without it nothing is read or contacted |
| Governed checkout | environment `PT_MCP_GOVERNED_ROOT` | declared by the operator; never derived |

Preconditions that the runner checks itself: the process is the checkout-local
interpreter with the package loaded from that checkout, and it is not a test
process. The write-ahead record can be created under
`data/services/qualification/` in the governed checkout. The authorized
channel is live. The running build matches. The workspace is observed empty.

Precondition the runner cannot check: Packet Tracer must be a separate
operator-owned instance with an empty workspace dedicated to the stage. The
MCP server must not be running on the HTTP bridge port for an `http` run.

## Record

Each run writes `data/services/qualification/<stage>/<stage>-<run_id>.json`
(gitignored). The write is ahead of every effectful step, atomic (tmp plus
replace), and never rewritten once completed. The record carries:

- the authorization scope;
- the executed SHA and tree and the clean state;
- the interpreter, package origin and isolation state;
- the observed build with its reader identity and a bounded excerpt;
- the fixed channel;
- the fixtures and links;
- the budget, reserve, planned minimum and every operation, including refusals;
- the write-ahead transitions and the last durable step;
- every measurement with its hypothesis, status, conclusion, facts, causes and
  limitations;
- the primary and secondary failures, releases, both restoration observations,
  engine residue and dirty state.

Dirty state is `clean` only when both restoration reads match the baseline,
every owned release resolved and no engine residue remains. An event observer
that stays attached keeps the state `unknown` even when the workspace reads
empty.

## Results

Each row transcribes one completed LIVE record: run id, executed SHA, build,
channel, outcome, and each measurement's conclusion. No row exists.

| Run id | Stage | Executed SHA | Build | Channel | Outcome | Conclusions |
| --- | --- | --- | --- | --- | --- | --- |
| none | none | none | none | none | none | none |
