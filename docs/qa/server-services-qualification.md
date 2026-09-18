# Server-PT services qualification (Q stages)

This page is the operator-facing template for the staged Packet Tracer
qualification that S4a prepared. It holds **no active authorization and no
measurement**. As of this revision, no qualification stage has run against
Packet Tracer, so no stage record exists and no capability has been promoted
by one.

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

| Stage | Status in S4a | Fixtures | Ceiling | Planned worst case | Measurements |
| --- | --- | --- | --- | --- | --- |
| Q0 | executable | `__MCP_E6Q_PC1` (PC-PT) | 20 operations / 300 s | 19 | M-ENG-1, ATOM-1, M-UNREG-1, M-UNREG-2 (M-HTTP-1 omitted: no HTTP server in the fixture) |
| Q1 | executable | `__MCP_E6Q_SRV`, `__MCP_E6Q_PC1`, `__MCP_E6Q_PC2`, `__MCP_E6Q_SW` | 60 operations / 600 s | 46 | M-HTTPS-1, M-HTTPS-2, M-DNS-3 (M-DNS-1/2 omitted) |
| Q2 | declarative only | none | 60 / 900 s | not planned | requires S2 and a Q0 record |
| Q3 | declarative only | none | 60 / 1200 s | not planned | requires S3 and a Q0 record |

The planned figure is the stage's **bounded worst case**, not its luckiest
trace: every production fetch is budgeted at its start, both inspections and
the release of its owned client. A stage whose worst case exceeds its ceiling
is refused before contact, with the arithmetic in the refusal.

Q1's 60 / 600 is a reviewed design ceiling for the offline correction, decided
against the worst case of 46 with the 10-operation finalization reserve intact.
It authorizes no LIVE run, and it changes neither Q0's 20 / 300 nor the
declarative Q2/Q3. The runner never raises a ceiling by itself.

M-HTTPS-2 cannot be SUPPORTED with the readers this build has. Its model says a
listener *fails* when it is disabled, and the web reader reports a refused
request exactly as it reports a slow or lost one -- `no_response_within_deadline`
-- while fresh non-marker content proves a marker mismatch rather than a
refusal. A negative control can therefore contradict the model (the marker was
retrieved while the listener read back as disabled) but never establish it, and
the HTTP-mode negative has no HTTP-mode positive control in this stage. The
measurement records its observations and stays INCONCLUSIVE.

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
| Stage | `--authorized-stage` and `--stage` | one of Q0..Q3; Q2/Q3 and an infeasible stage refuse |
| Executed SHA | `--authorized-sha` and `--expected-head` | 40 lowercase hex; equal to each other, to observed `HEAD`, and to its published upstream; clean worktree |
| Fixture targets | `--authorized-target` and `--target` (repeat) | exactly the stage fixtures, no duplicates |
| Channel | `--authorized-channel` and `--channel` | `http` or `file`; one per authorization, fixed for the whole run |
| Build | `--authorized-build` and `--packet-tracer-build` | one exact four-component build; must equal the running application's `AppWindow.getVersion()` |
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
