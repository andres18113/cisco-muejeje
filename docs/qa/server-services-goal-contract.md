# Server-PT diagnostics: operator and Goal contract

What a reviewer has to decide, what an operator would type, and what a later
Codex Goal is allowed to conclude, for the two executable diagnostic stages
`D-DHCP` and `D-WEB`.

**Nothing in this file is a permission.** Every authorization below is a
template with its identity fields blank. No LIVE run is authorized, no bridge
is started, no Packet Tracer instance is contacted, and no capability is
promoted by anything recorded here. The design delta is
[`server-pt-goal-foundations.md`](../engineering/change-briefs/server-pt-goal-foundations.md);
the shared stage rules are in
[`server-services-qualification.md`](server-services-qualification.md).

## What each diagnostic asks

| Stage | Question | Dependent variable | What a result would *not* establish |
| --- | --- | --- | --- |
| D-DHCP | Which operation of a server-only DHCP setup moves the native default pool, if any single one does? | the observed transition of the native inventory between two adjacent counted readings | that a client can acquire a lease, that the server is serving, that the backend's internal algorithm did anything in particular |
| D-WEB | Where does an unretrieved HTTP page fail: the forwarding path, the listener and request, or the polling and the reader? | the boundary a same-fixture comparison locates | that TCP or HTTP works, that a listener refused anything, that a timeout is a negative |

## Hypotheses and the outcomes that would settle them

| Measurement | Hypothesis | Supported by | Refuted or left open by |
| --- | --- | --- | --- |
| M-DDHCP-0 | a stock Server-PT presents a coherent disabled process, its native inventory, and two clients this stage never touches | an admissible baseline, readable client flags, a ready fixture, and two adjacent readings that agree | any difference between the two adjacent readings, which is autonomous drift and closes every later attribution in the run |
| M-DDHCP-1 | the server's static addressing alone is one `configurePcIp` intervention that also writes gateway and DNS | the E5 row applied with its fresh address read-back | a difference across the interval, which belongs to the whole call and never to the IP field alone |
| M-DDHCP-2 | the intended pool can be written while the process is still disabled | a `DHCP_SERVER_STATE` read-back matching `enabled=False` plus the exact pool fields | a contradicted read-back, a blocked read-back, or any difference in the native inventory across the interval |
| M-DDHCP-3 | enabling the process is the transition to `enabled=True` | the rebound read-back matching `enabled=True` | a native default difference across this interval, which is the finding, not a setup failure |
| M-DDHCP-4 | the pre-cleanup inventory is preserved whatever the sequence did | the reading reaching the terminal record | an unaffordable or refused reading, which is explicitly not observed |
| M-DWEB-0 | both listeners report their flags and their read-back port numbers, and every endpoint is up | a complete listener reading plus a ready gate | a port number that is not a number, which is a named absence and not a default of 80 |
| M-DWEB-1 | the exact switch ports are forwarding in the fixture VLAN | one fresh, complete, uniquely attributed sample in which every requested port appears exactly once in `FWD` | a missing, duplicate, learning, listening, blocking, wrong-VLAN, stale, paged or late row; a green light and a port-up flag grant nothing |
| M-DWEB-2 | the existing index page carries this run's marker through both handles | the write plus the read-back containing the marker | a failed write, which stops the sequence rather than being fetched around |
| M-DWEB-3 | one attributed ping establishes ICMP reachability | a fresh attributed ping between two validated bindings, stable before and after | an unattributed or drifted binding; and even a success establishes nothing about TCP or HTTP |
| M-DWEB-4 | the real owned background client's whole lifecycle is observable | owner, mode, native `go` result with its type, every scheduled inspection, one late read, the release | anything short of a retrieved marker, which leaves the listener/request/client/reader boundary unresolved |
| M-DWEB-5 | the boundaries after the request are the ones observed before it | both readings agreeing | any difference, which is retained rather than normalized away |

## Budget arithmetic

Measured against the engine stub with the real components, not summed from
placeholder steps. One endpoint E5 batch is one `send` plus one verification
read per expectation; one E6 service action is one dispatch plus one read-back
per expectation; one native default reading is one dispatch; one
`show spanning-tree` sample is four counted calls (the terminal state read, the
dispatch, one output convergence read and the attribution read); one typed ping
is three; one bind-before-ping probe is seven. Each bounded neutral-forwarding
observation also performs one separate simulation-state read after its STP
sample loop; that read never extends the wall-clock or sample bounds.

| D-DHCP | Operations |
| --- | --- |
| admission reads | 2 |
| four fixtures at two calls each | 8 |
| three links at two calls each | 6 |
| fixture identity read | 1 |
| M-DDHCP-0: baseline, client flags, readiness ceiling, drift control | 7 |
| M-DDHCP-1: E5 send, address read-back, native reading | 3 |
| M-DDHCP-2: pool dispatch, server-state read-back, native reading | 3 |
| M-DDHCP-3: enable dispatch, rebound read-back, native reading | 3 |
| M-DDHCP-4: pre-cleanup native reading | 1 |
| finalization reserve: run bag, four removals, two restoration reads | 11 |
| **planned worst case** | **45** of a proposed **50 / 900 s** |

| D-WEB | Operations |
| --- | --- |
| admission reads | 2 |
| four fixtures at two calls each | 8 |
| three links at two calls each | 6 |
| fixture identity read | 1 |
| E5 endpoint batch, E6 listener enables | 2 |
| M-DWEB-0: listener reading, readiness ceiling | 5 |
| M-DWEB-1: two four-call forwarding samples, one simulation-state read | 9 |
| M-DWEB-2: marker page | 1 |
| M-DWEB-3: bind-before-ping probe | 7 |
| M-DWEB-4: start, three scheduled inspections, late read, release | 6 |
| M-DWEB-5: listener reading, one four-call forwarding sample, one simulation-state read | 6 |
| finalization reserve: four removals, two restoration reads | 10 |
| **planned worst case** | **63** of a proposed **68 / 900 s** |

Both ceilings are new, proposed limits for review, not a raise of any existing
one: Q0 stays 20 / 300, Q1 stays 60 / 600, Q3 stays 60 / 1200. The five-call
slack above each planned worst case covers one additional convergence round in
every nested terminal loop the stage contains. The ledger, not the plan, is the
hard bound: a call past the ceiling is refused before dispatch, and the
finalization reserve is never spent on an effect. The old 43/47 planning
figures of the prepared profiles and the old 60-operation ceiling are not
evidence that any of this fits.

## The authority a diagnostic stage binds

Everything a Q stage binds, unchanged, **plus** the identity half below. Each
field is compared against a value the stage definition or the observed checkout
already fixes. A text precondition is not proof, and setting any flag to
`GRANTED` grants nothing: `DiagnosticAuthorization` in
`service_diagnostic_profiles.py` is planning data that nothing executable
reads.

| Field | Runner argument | Rule |
| --- | --- | --- |
| Profile | `--authorized-profile`, `--authorized-profile-version` | exactly the stage's profile id and version; the version moves whenever the step sequence, the fixture binding or the budget arithmetic changes |
| Executed tree | `--authorized-tree` | 40 lowercase hex; compared against the observed source tree, because a commit names a history and the tree names the bytes that execute |
| Fixture models | `--authorized-model` (repeat) | exactly `name:model` per fixture, in creation order |
| Link ports | `--authorized-link` (repeat) | exactly `devA:portA-devB:portB` per link, in creation order |
| Step selection | `--authorized-step` (repeat) | a subset of the stage's steps, in the stage's declared order, with every prerequisite present before the step that needs it; reordered, duplicated, incomplete and activation-only selections refuse |
| Cleanup reserve | `--authorized-reserve-operations` | exactly the stage's finalization reserve |
| Fresh instance | `--instance-token` | 32 lowercase hex, naming the dedicated Packet Tracer process this attempt runs against |
| Process identity | `--authorized-process-id`, `--authorized-process-path` | exact PID and executable path of the one locally observed Packet Tracer process; its product/file version must report the authorized build, at admission and again after finalization |
| Attempt identity | `--attempt-id` | 32 lowercase hex, distinct from the instance token, and never used by any stored record. A new SHA, a new process and a new run id do not create an attempt |

The runner also performs and fails closed on three local controls before
constructing a transport: the record store must state that the attempt identity
is new; every boundary the selected stage needs must be composed; and the
read-only lifecycle reader must observe exactly the authorized PID/path/build
with no `req_*` or `res_*` mailbox artifacts. A fresh heartbeat is only
liveness. It cannot select a process, clear a stale request, or prove an empty
workspace.

### Prepared lifecycle preflight for a later authorized run

This delivery does not launch or restart Packet Tracer. For a future reviewed
run, the operator first closes any user document and starts one dedicated
instance from the exact executable named by the authorization. The mailbox is
inspected, never cleaned by the runner: any request, response or temporary
artifact is a blocker that must be investigated outside the attempt. The
reviewer binds the observed PID/path plus a fresh instance token. At invocation,
the runner repeats the local process/build/mailbox checks before opening the
file channel. After read-only contact, it admits no effect until the existing
workspace observer proves the active workspace is disposable and empty. A
process change, nonempty mailbox, existing semantic device/link or unreadable
workspace refuses; no heartbeat or authorization text overrides those facts.

### The pairing is confirmed again on the way out

Binding a process before the transport exists says nothing about which
process answered afterwards. Packet Tracer can be closed or can crash
mid-run, and the replacement polls the same mailbox, so the owned removals
and both restoration reads would be served by an instance the authorization
never named. After finalization the runner therefore takes the same
read-only local reading a second time and stores it beside the first.

It costs no bridge operation, so an exhausted budget cannot suppress it and
the cleanup reserve is never borrowed for it. It still launches, stops and
deletes nothing: an artifact left in the mailbox is reported, not cleaned,
because it is exactly what a later instance could re-execute. A changed
PID, path or build, an unreadable second reading, or any remaining `req_*`
or `res_*` artifact is recorded as engine residue, drops
`restoration_proven` and leaves the run `stopped`. The measurements are
kept as taken; what they lose is the claim that the cleanup evidence
describes the authorized instance. The promotion gate reads both readings,
so a diagnostic that cannot show the same pairing at both ends supports
nothing.

## Diagnostic commands (all ungranted)

The identity fields are deliberately empty. Filling them in is a reviewer's
decision that does not exist yet, and a filled-in command still refuses unless
the checkout, the process, the build, the channel and the workspace all agree.

```powershell
# D-DHCP -- UNGRANTED TEMPLATE. Nothing here authorizes a run.
.\.venv\Scripts\python.exe -m packet_tracer_mcp.adapters.cli.service_qualification `
  --execute --stage D-DHCP --channel file --packet-tracer-build 9.0.1.0858 `
  --expected-head <40-hex-sha> `
  --target __MCP_E6Q_SRV --target __MCP_E6Q_PC1 --target __MCP_E6Q_PC2 --target __MCP_E6Q_SW `
  --authorization-id <reviewer-scoped-id> --authorized-stage D-DHCP `
  --authorized-sha <40-hex-sha> --authorized-tree <40-hex-tree> `
  --authorized-channel file --authorized-build 9.0.1.0858 `
  --authorized-max-operations 50 --authorized-max-seconds 900 `
  --authorized-reserve-operations 11 `
  --authorized-profile D-DHCP --authorized-profile-version 2 `
  --authorized-target __MCP_E6Q_SRV --authorized-target __MCP_E6Q_PC1 `
  --authorized-target __MCP_E6Q_PC2 --authorized-target __MCP_E6Q_SW `
  --authorized-model __MCP_E6Q_SRV:Server-PT --authorized-model __MCP_E6Q_PC1:PC-PT `
  --authorized-model __MCP_E6Q_PC2:PC-PT --authorized-model __MCP_E6Q_SW:2960-24TT `
  --authorized-link "__MCP_E6Q_SRV:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/1" `
  --authorized-link "__MCP_E6Q_PC1:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/2" `
  --authorized-link "__MCP_E6Q_PC2:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/3" `
  --authorized-step D0-baseline --authorized-step D0-control `
  --authorized-step D1-static --authorized-step D2-pool `
  --authorized-step D3-enable --authorized-step D4-final `
  --authorized-process-id <packet-tracer-pid> `
  --authorized-process-path "<exact-packet-tracer-executable>" `
  --instance-token <32-hex> --attempt-id <32-hex>
```

```powershell
# D-WEB -- UNGRANTED TEMPLATE. Nothing here authorizes a run.
.\.venv\Scripts\python.exe -m packet_tracer_mcp.adapters.cli.service_qualification `
  --execute --stage D-WEB --channel file --packet-tracer-build 9.0.1.0858 `
  --expected-head <40-hex-sha> `
  --target __MCP_E6Q_SRV --target __MCP_E6Q_PC1 --target __MCP_E6Q_PC2 --target __MCP_E6Q_SW `
  --authorization-id <reviewer-scoped-id> --authorized-stage D-WEB `
  --authorized-sha <40-hex-sha> --authorized-tree <40-hex-tree> `
  --authorized-channel file --authorized-build 9.0.1.0858 `
  --authorized-max-operations 68 --authorized-max-seconds 900 `
  --authorized-reserve-operations 10 `
  --authorized-profile D-WEB --authorized-profile-version 2 `
  --authorized-target __MCP_E6Q_SRV --authorized-target __MCP_E6Q_PC1 `
  --authorized-target __MCP_E6Q_PC2 --authorized-target __MCP_E6Q_SW `
  --authorized-model __MCP_E6Q_SRV:Server-PT --authorized-model __MCP_E6Q_PC1:PC-PT `
  --authorized-model __MCP_E6Q_PC2:PC-PT --authorized-model __MCP_E6Q_SW:2960-24TT `
  --authorized-link "__MCP_E6Q_SRV:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/1" `
  --authorized-link "__MCP_E6Q_PC1:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/2" `
  --authorized-link "__MCP_E6Q_PC2:FastEthernet0-__MCP_E6Q_SW:FastEthernet0/3" `
  --authorized-step W0-listeners --authorized-step W0-readiness `
  --authorized-step W1-forwarding --authorized-step W2-page `
  --authorized-step W3-ping --authorized-step W4-fetch --authorized-step W5-after `
  --authorized-process-id <packet-tracer-pid> `
  --authorized-process-path "<exact-packet-tracer-executable>" `
  --instance-token <32-hex> --attempt-id <32-hex>
```

Dropping `--authorized-step W3-ping`, `--authorized-step W4-fetch` and
`--authorized-step W5-after` together, or dropping `--authorized-step
D3-enable`, is a coherent narrower authority: the stage runs what it was
authorized to run, records the rest as
`not_selected_by_authorization`, and still completes. Dropping a step that a
later selected step requires is refused.

## What a later Codex Goal may conclude

Codex owns thread-scoped Goals; this repository owns verifiable results and
permissions. A Goal's success is the reviewed product outcome below, never CI
alone and never the existence of a report.

| Outcome | What it means | What it permits |
| --- | --- | --- |
| `READY_FOR_REVIEW` | the offline delivery is complete, the full suite, quality gate, namespace inventory, MkDocs and whitespace pass, and exact-SHA CI is green | an independent review; nothing else |
| `ACCEPTED_NATIVE` | an independently reviewed LIVE record, at the exact SHA and tree, on the qualified build and channel, answers the stage's question with an observed result | citing that record for that question, at that SHA, on that build and channel |
| `ACCEPTED_PRODUCT` | a product flow reproduces the accepted native result without any diagnostic-only warming | a separately proposed capability change, reviewed on its own |
| `BLOCKED` | a precondition outside this repository is missing: no authorized instance, no reviewer decision, an unobservable control | nothing; the Goal is not completed |
| `EXPERIMENT_BUDGET_EXHAUSTED` | the predeclared attempts of the current campaign are used up | nothing; a new campaign with new predeclared families and exact-attempt bindings is a separate decision |
| `OBSERVER_LIMIT_UNRESOLVED` | the question needs an observation no qualified reader provides | recording the limit; never inferring the answer from its absence |

Offline autofix may continue causally inside the approved contract at any time.
Any LIVE iteration needs a new campaign with finite, predeclared experiment
families and exact-attempt bindings. The previous campaign is exhausted (Q3
3/3, Q1 2/2) and its counters are immutable. A blocked or budget-limited Goal
is not a completed Goal, and no automatic capability promotion or merge follows
from any outcome above.

## Inactive `/goal` draft

Recorded as text, not created. `codex-cli 0.155.1` is installed here and its
non-interactive command surface lists no `goal` entry; the official guide
places `/goal` support at 0.128.0, which is not proof either way about the
interactive slash command in this installation. Availability is therefore
**observed-version-only, interactive listing pending**.

```text
/goal Server-PT diagnostic execution readiness

Outcome that counts as success:
  an independently reviewed LIVE record for D-DHCP or D-WEB, at the exact SHA
  and tree its authorization names, on build 9.0.1.0858 over the file channel,
  whose measurements answer the stage's question with an observed result.
  CI being green is READY_FOR_REVIEW and nothing more.

Bounded scope:
  - offline: causal autofix inside the approved contract, the full suite, the
    quality gate on the enumerated changed files, the namespace inventory,
    MkDocs and the whitespace check;
  - LIVE: only under a new campaign with finite, predeclared experiment
    families and exact-attempt bindings, one operator-confirmed dedicated
    Packet Tracer instance, and one attempt identity per attempt.

Never:
  merge, force push, global configuration change, capability promotion,
  continuation of the exhausted Q campaign, reconstruction of the missing
  pre-cleanup payload of the historical a02c1e0 Q3, or any edit to an archived
  record.

Report exactly one of:
  READY_FOR_REVIEW | ACCEPTED_NATIVE | ACCEPTED_PRODUCT | BLOCKED |
  EXPERIMENT_BUDGET_EXHAUSTED | OBSERVER_LIMIT_UNRESOLVED
with the branch, the delivery SHA and tree, the CI run for that exact SHA, and
every blocker that remains.
```

## Remaining blockers

1. No LIVE authorization exists for either stage. Both templates above are
   ungranted, and the operator-confirmed dedicated Packet Tracer instance they
   would need has not been observed.
2. Offline CI cannot verify Packet Tracer, the webview CORS boundary, the
   `this-sm:` origin or Script Engine reachability. Everything both stages
   would measure stays UNKNOWN/UNMEASURED.
3. R-EVT-05 still gates event-driven product verification; neither stage
   registers an event source, so neither lifts it.
4. The causal trigger of the native default change observed across server and
   client E5 plus E6 setup is not known. The stub that moves it on process
   enable is a controlled test scenario, not a measured attribution.
5. `/goal` availability in this Codex installation is pending, as recorded
   above.
